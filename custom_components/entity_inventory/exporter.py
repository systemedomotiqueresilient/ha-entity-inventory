"""Construction et écriture de l'inventaire YAML."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
import os
from pathlib import Path
from typing import Any

import yaml

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
    label_registry as lr,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.file import write_utf8_file_atomic

from .const import CONF_OUTPUT_PATH, DEFAULT_OUTPUT_PATH, STATIC_ATTRIBUTES

HEADER = """\
# Inventaire Home Assistant — généré par l'intégration Entity Inventory.
# Contexte destiné à une IA pour rédiger automatisations, scripts et packages.
# Ne contient AUCUN état ni historique : uniquement la structure de l'instance
# (étages, pièces, appareils, entités) et les valeurs possibles (options, modes, plages).
#
# Règles de lecture :
#  - "id" est l'entity_id exact à utiliser dans le YAML.
#  - Les clés de "areas" sont des area_id (utilisables dans target: area_id).
#  - Les clés de "floors" et "labels" sont des floor_id / label_id.
#  - "area" sur une entité = elle est placée dans une autre pièce que son appareil.
#  - category: diagnostic|config = entité technique (batterie, signal, réglage…).
#  - hidden: true = masquée dans l'interface mais pleinement fonctionnelle.
#  - "unassigned" = appareils/entités sans pièce.
#  - "no_registry" = entités sans unique_id (YAML historique), non assignables à une pièce.
#  - "disabled" = entités désactivées : elles n'existent pas à l'exécution, ne pas les utiliser.

"""


# --------------------------------------------------------------------------- #
# Chemin de sortie
# --------------------------------------------------------------------------- #
def resolve_output_path(hass: HomeAssistant, entry: ConfigEntry) -> Path:
    """Chemin absolu du fichier de sortie (relatif = relatif à /config)."""
    raw = entry.options.get(CONF_OUTPUT_PATH) or DEFAULT_OUTPUT_PATH
    return Path(os.path.abspath(hass.config.path(raw)))


def is_forbidden_path(hass: HomeAssistant, raw: str) -> bool:
    """Refuse /config/www : ce dossier est servi SANS authentification sur /local/."""
    path = os.path.abspath(hass.config.path(raw))
    www = os.path.abspath(hass.config.path("www"))
    return path == www or path.startswith(www + os.sep)


# --------------------------------------------------------------------------- #
# Construction des données
# --------------------------------------------------------------------------- #
def _clean(value: Any) -> Any:
    """Convertit en types YAML simples (enums, sets, tuples, mappingproxy…)."""
    if isinstance(value, Enum):
        value = value.value
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((_clean(v) for v in value), key=str)
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return str(value)


def _set(target: dict[str, Any], key: str, value: Any) -> None:
    """N'ajoute la clé que si la valeur est significative (fichier plus compact)."""
    if value is None or (
        isinstance(value, (str, list, tuple, set, frozenset, Mapping)) and not value
    ):
        return
    target[key] = _clean(value)


def _device_name(device: dr.DeviceEntry) -> str:
    return device.name_by_user or device.name or device.id


def _entity_fallback_name(entry: er.RegistryEntry, device: dr.DeviceEntry | None) -> str:
    if entry.name:
        return entry.name
    if entry.has_entity_name and device:
        base = _device_name(device)
        return f"{base} {entry.original_name}" if entry.original_name else base
    return entry.original_name or entry.entity_id


def _capabilities(
    capabilities: Mapping[str, Any] | None, attributes: Mapping[str, Any]
) -> dict[str, Any]:
    """Attributs structurels : registre d'abord, état ensuite (liste blanche)."""
    caps = capabilities or {}
    out: dict[str, Any] = {}
    for key in STATIC_ATTRIBUTES:
        _set(out, key, caps[key] if key in caps else attributes.get(key))
    return out


@callback
def async_build_inventory(hass: HomeAssistant) -> dict[str, Any]:
    """Construit l'inventaire (à appeler dans la boucle d'événements)."""
    area_reg = ar.async_get(hass)
    floor_reg = fr.async_get(hass)
    label_reg = lr.async_get(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    # --- Étages et étiquettes -------------------------------------------- #
    floors_by_id = {f.floor_id: f for f in floor_reg.async_list_floors()}
    floors: dict[str, Any] = {}
    for floor in sorted(
        floors_by_id.values(),
        key=lambda f: (f.level if f.level is not None else 999, f.name.casefold()),
    ):
        item: dict[str, Any] = {"name": floor.name}
        _set(item, "level", floor.level)
        _set(item, "aliases", floor.aliases)
        floors[floor.floor_id] = item

    labels = {
        label.label_id: label.name
        for label in sorted(label_reg.async_list_labels(), key=lambda l: l.name.casefold())
    }

    # --- Pièces (triées par niveau d'étage puis par nom) ----------------- #
    def _area_sort(area: ar.AreaEntry) -> tuple[int, str]:
        floor = floors_by_id.get(area.floor_id) if area.floor_id else None
        level = floor.level if floor and floor.level is not None else 999
        return (level, area.name.casefold())

    areas: dict[str, dict[str, Any]] = {}
    for area in sorted(area_reg.async_list_areas(), key=_area_sort):
        item = {"name": area.name}
        _set(item, "floor", area.floor_id)
        _set(item, "aliases", area.aliases)
        _set(item, "labels", area.labels)
        areas[area.id] = item

    unassigned: dict[str, Any] = {}

    def _bucket(area_id: str | None) -> dict[str, Any]:
        return areas[area_id] if area_id and area_id in areas else unassigned

    # --- Intégration d'un appareil (avec cache) -------------------------- #
    integration_cache: dict[str, str | None] = {}

    def _device_integration(device: dr.DeviceEntry) -> str | None:
        if device.id not in integration_cache:
            entry_id = getattr(device, "primary_config_entry", None) or next(
                iter(device.config_entries), None
            )
            config_entry = (
                hass.config_entries.async_get_entry(entry_id) if entry_id else None
            )
            integration_cache[device.id] = config_entry.domain if config_entry else None
        return integration_cache[device.id]

    # --- Entités du registre ---------------------------------------------- #
    disabled: list[str] = []
    entities_by_device: dict[str, list[dict[str, Any]]] = {}
    entity_count = 0

    for entry in sorted(ent_reg.entities.values(), key=lambda e: e.entity_id):
        if entry.disabled_by:
            disabled.append(entry.entity_id)
            continue

        device = dev_reg.async_get(entry.device_id) if entry.device_id else None
        state = hass.states.get(entry.entity_id)
        attributes = state.attributes if state else {}

        item: dict[str, Any] = {"id": entry.entity_id}
        _set(
            item,
            "name",
            attributes.get("friendly_name") or _entity_fallback_name(entry, device),
        )
        _set(
            item,
            "device_class",
            entry.device_class or entry.original_device_class or attributes.get("device_class"),
        )
        _set(
            item,
            "unit",
            entry.unit_of_measurement or attributes.get("unit_of_measurement"),
        )
        _set(item, "category", entry.entity_category)
        if entry.hidden_by:
            item["hidden"] = True
        _set(item, "aliases", [a for a in entry.aliases if a])
        _set(item, "labels", entry.labels)
        item.update(_capabilities(entry.capabilities, attributes))
        entity_count += 1

        if device:
            if entry.platform != _device_integration(device):
                item["integration"] = entry.platform
            if entry.area_id and entry.area_id != device.area_id:
                item["area"] = entry.area_id
            entities_by_device.setdefault(device.id, []).append(item)
        else:
            item["integration"] = entry.platform
            _bucket(entry.area_id).setdefault("entities", []).append(item)

    # --- Appareils (seulement ceux qui ont des entités actives) ----------- #
    device_count = 0
    for device in sorted(dev_reg.devices.values(), key=lambda d: _device_name(d).casefold()):
        device_entities = entities_by_device.get(device.id)
        if not device_entities:
            continue
        item = {"name": _device_name(device)}
        _set(item, "manufacturer", device.manufacturer)
        _set(item, "model", device.model)
        _set(item, "integration", _device_integration(device))
        _set(item, "labels", device.labels)
        item["entities"] = device_entities
        _bucket(device.area_id).setdefault("devices", []).append(item)
        device_count += 1

    # --- Entités hors registre (YAML sans unique_id) ----------------------- #
    no_registry: list[dict[str, Any]] = []
    for state in sorted(hass.states.async_all(), key=lambda s: s.entity_id):
        if ent_reg.async_get(state.entity_id) is not None:
            continue
        item = {"id": state.entity_id}
        _set(item, "name", state.attributes.get("friendly_name"))
        _set(item, "device_class", state.attributes.get("device_class"))
        _set(item, "unit", state.attributes.get("unit_of_measurement"))
        item.update(_capabilities(None, state.attributes))
        no_registry.append(item)
        entity_count += 1

    # --- Assemblage -------------------------------------------------------- #
    # Ordre de lecture : appareils d'abord, entités isolées ensuite
    for bucket in (*areas.values(), unassigned):
        if "entities" in bucket:
            bucket["entities"] = bucket.pop("entities")
    meta = {
        "generator": "entity_inventory",
        "ha_version": HA_VERSION,
        "exported_at": dt_util.now().isoformat(timespec="seconds"),
        "language": hass.config.language,
        "temperature_unit": hass.config.units.temperature_unit,
        "counts": {
            "floors": len(floors),
            "areas": len(areas),
            "devices": device_count,
            "entities": entity_count,
            "disabled": len(disabled),
        },
    }

    data: dict[str, Any] = {"meta": _clean(meta)}
    _set(data, "floors", floors)
    _set(data, "labels", labels)
    _set(data, "areas", areas)
    _set(data, "unassigned", unassigned)
    _set(data, "no_registry", no_registry)
    _set(data, "disabled", disabled)
    return data


# --------------------------------------------------------------------------- #
# Sérialisation YAML compacte
# --------------------------------------------------------------------------- #
class _CompactDumper(yaml.SafeDumper):
    """Listes de scalaires sur une ligne ([heat, off]) : moins de tokens."""

    def ignore_aliases(self, data: Any) -> bool:  # pas d'ancres &id001
        return True


def _represent_list(dumper: yaml.SafeDumper, data: list[Any]) -> yaml.Node:
    flow = all(not isinstance(i, (dict, list)) for i in data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_CompactDumper.add_representer(list, _represent_list)


def dump_inventory(data: dict[str, Any]) -> str:
    """Sérialise l'inventaire en YAML avec l'en-tête explicatif."""
    return HEADER + yaml.dump(
        data,
        Dumper=_CompactDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
async def async_export(hass: HomeAssistant, path: Path) -> dict[str, Any]:
    """Construit l'inventaire et l'écrit de façon atomique."""
    if is_forbidden_path(hass, str(path)):
        raise HomeAssistantError(
            f"Export refusé vers {path} : /config/www est public (servi sans authentification)"
        )

    data = async_build_inventory(hass)

    def _write() -> None:
        content = dump_inventory(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_utf8_file_atomic(str(path), content)

    try:
        await hass.async_add_executor_job(_write)
    except OSError as err:
        raise HomeAssistantError(f"Impossible d'écrire {path} : {err}") from err

    return {"path": str(path), **data["meta"]["counts"]}
