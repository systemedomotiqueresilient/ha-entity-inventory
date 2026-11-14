"""Construction et écriture de l'inventaire YAML."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
import os
import re
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
from homeassistant.helpers.hassio import is_hassio
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util
from homeassistant.util.file import write_utf8_file_atomic

from .const import (
    ALWAYS_KEEP_DEVICE_CLASSES,
    CONF_EXCLUDED_INTEGRATIONS,
    CONF_INCLUDE_CONFIG,
    CONF_INCLUDE_DIAGNOSTIC,
    CONF_OUTPUT_PATH,
    CONF_REDACT_EMAILS,
    DEFAULT_INCLUDE_CONFIG,
    DEFAULT_INCLUDE_DIAGNOSTIC,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH_SUPERVISED,
    DEFAULT_REDACT_EMAILS,
    DOMAIN,
    STATIC_ATTRIBUTES,
)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

HEADER = """\
# Inventaire Home Assistant — généré par l'intégration Entity Inventory.
# Contexte destiné à une IA pour rédiger automatisations, scripts et packages.
# Ne contient AUCUN état ni historique : uniquement la structure de l'instance
# (étages, pièces, appareils, entités) et les valeurs possibles (options, modes, plages).
#
# Règles de lecture :
#  - "id" est l'entity_id exact à utiliser dans le YAML.
#  - Sous un appareil, "name" est le nom COURT de l'entité : son nom affiché est
#    "<nom de l'appareil> <name>". Sans "name", elle porte le nom de l'appareil.
#  - Les clés de "areas" sont des area_id (utilisables dans target: area_id).
#  - Les clés de "floors" et "labels" sont des floor_id / label_id.
#  - "area" sur une entité = elle est placée dans une autre pièce que son appareil.
#  - category: diagnostic|config = entité technique (batterie, signal, réglage…).
#  - hidden: true = masquée dans l'interface mais pleinement fonctionnelle.
#  - "unassigned" = appareils/entités sans pièce.
#  - "no_registry" = entités sans unique_id (YAML historique), non assignables à une pièce.
#  - L'export peut être FILTRÉ (voir meta.filters et meta.counts.excluded) : une entité
#    absente d'ici peut exister. Ne jamais inventer d'entity_id.
#  - Les entités désactivées ne sont pas listées : elles n'existent pas à l'exécution.
#  - "integration" absent = intégration de l'appareil, ou celle du domaine de l'entity_id.
#  - "via" = passerelle par laquelle l'appareil communique (coordinateur Zigbee2MQTT, pont
#    Zigbee, hub…). Deux appareils de même intégration (ex. mqtt) peuvent passer par des
#    passerelles différentes : c'est dans celle-ci qu'on renomme ou supprime l'appareil.
#  - "[email]" dans un nom = adresse e-mail masquée (l'entity_id, lui, reste exact).
#
# Consignes pour rédiger du YAML à partir de ce fichier :
#  - N'utilise QUE des entity_id présents ici. S'il en manque un, dis-le au lieu de l'inventer.
#  - Les valeurs (preset_modes, options, hvac_modes…) sont exactes : casse et espaces comptent.
#  - Syntaxe actuelle de Home Assistant : "triggers:" / "- trigger: state",
#    "conditions:", "actions:" / "- action: domaine.service" (pas "platform:" ni "service:").
#  - Si plusieurs entités conviennent (ex. deux thermostats pour un même radiateur), demande laquelle.
#  - Les automatisations, scripts et scènes existants sont listés : signale ceux qui agissent
#    déjà sur les mêmes entités (risque de conflit) et, si utile, mémorise puis restaure l'état
#    avec scene.create plutôt que d'imposer une valeur fixe.
#  - Pour une catégorie ("toutes les piles", "toutes les fenêtres"), parcours TOUT le fichier :
#    filtre par domaine + device_class (+ unit), dans toutes les pièces et dans "unassigned".
#  - Une entité notify.* n'est PAS une action : on l'appelle avec "action: notify.send_message"
#    et "target: entity_id: notify.xxx" (données : message, title).
#  - numeric_state exige une entité à état numérique (sensor, number, input_number…) :
#    jamais un group.*, binary_sensor ou switch. Pour un minimum, utiliser un capteur min_max.
#  - Le YAML produit peut être vérifié dans Home Assistant avec l'action entity_inventory.validate.

"""


def export_options(entry: ConfigEntry) -> dict[str, Any]:
    """Options de filtrage, avec valeurs par défaut pour les anciennes configurations."""
    return {
        CONF_INCLUDE_CONFIG: entry.options.get(CONF_INCLUDE_CONFIG, DEFAULT_INCLUDE_CONFIG),
        CONF_INCLUDE_DIAGNOSTIC: entry.options.get(
            CONF_INCLUDE_DIAGNOSTIC, DEFAULT_INCLUDE_DIAGNOSTIC
        ),
        CONF_EXCLUDED_INTEGRATIONS: sorted(
            entry.options.get(CONF_EXCLUDED_INTEGRATIONS) or []
        ),
        CONF_REDACT_EMAILS: entry.options.get(CONF_REDACT_EMAILS, DEFAULT_REDACT_EMAILS),
    }


# --------------------------------------------------------------------------- #
# Chemin de sortie
# --------------------------------------------------------------------------- #
def default_output_path(hass: HomeAssistant) -> str:
    """/share sur HAOS/Supervised : hors de /config, donc hors de portée de Watchman."""
    return DEFAULT_OUTPUT_PATH_SUPERVISED if is_hassio(hass) else DEFAULT_OUTPUT_PATH


def resolve_output_path(hass: HomeAssistant, entry: ConfigEntry) -> Path:
    """Chemin absolu du fichier de sortie (relatif = relatif à /config)."""
    raw = entry.options.get(CONF_OUTPUT_PATH) or default_output_path(hass)
    return Path(os.path.abspath(hass.config.path(raw)))


def is_forbidden_path(hass: HomeAssistant, raw: str) -> bool:
    """Refuse /config/www : ce dossier est servi SANS authentification sur /local/."""
    path = os.path.abspath(hass.config.path(raw))
    www = os.path.abspath(hass.config.path("www"))
    return path == www or path.startswith(www + os.sep)


def destination_problem(hass: HomeAssistant, path: Path) -> tuple[str, str] | None:
    """Vérifie que le fichier pourra être écrit : (code, dossier) en cas de problème.

    Un dossier manquant n'est créé que sous /config : ailleurs, c'est presque toujours
    une erreur (ex. /share sur une installation sans Supervisor) et le créer donnerait
    un fichier perdu dans le conteneur. Fait des E/S : à appeler dans l'exécuteur.
    """
    directory = path.parent
    if path.is_dir():
        return "is_dir", str(path)
    if not directory.exists():
        config_dir = os.path.realpath(hass.config.config_dir)
        if not os.path.realpath(directory).startswith(config_dir + os.sep):
            return "dir_missing", str(directory)
        existing = directory  # sous /config : le premier parent existant doit être inscriptible
        while not existing.exists():
            existing = existing.parent
        directory = existing
    if not directory.is_dir():
        return "dir_missing", str(directory)
    if not os.access(directory, os.W_OK | os.X_OK):
        return "dir_not_writable", str(directory)
    return None


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


def _aliases(values: Any) -> list[str]:
    """Alias texte uniquement.

    Depuis HA 2026.x la liste peut contenir un marqueur interne (« utiliser le nom
    de l'entité ») qui n'est pas un alias : sans ce filtre il sortait en « 0 ».
    """
    return sorted(v for v in values or () if isinstance(v, str) and v)


def _short_name(full: str, device_name: str) -> str | None:
    """Retire le préfixe « nom de l'appareil » (déjà porté par le parent)."""
    if full == device_name:
        return None
    if full.startswith(device_name + " "):
        return full[len(device_name) + 1 :]
    return full


@callback
def async_build_inventory(
    hass: HomeAssistant,
    options: Mapping[str, Any] | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Construit l'inventaire (à appeler dans la boucle d'événements)."""
    options = options or {}
    include_config = options.get(CONF_INCLUDE_CONFIG, DEFAULT_INCLUDE_CONFIG)
    include_diagnostic = options.get(CONF_INCLUDE_DIAGNOSTIC, DEFAULT_INCLUDE_DIAGNOSTIC)
    excluded_integrations = set(options.get(CONF_EXCLUDED_INTEGRATIONS) or ())
    redact_emails = options.get(CONF_REDACT_EMAILS, DEFAULT_REDACT_EMAILS)

    def _txt(value: str | None) -> str | None:
        """Espaces normalisés (noms « ' Switch Sensor' ») et e-mails masqués."""
        if not value:
            return value
        value = " ".join(str(value).split())
        return EMAIL_RE.sub("[email]", value) if redact_emails else value

    def _txts(values: Any) -> list[str]:
        return [_txt(v) for v in _aliases(values)]

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
        item: dict[str, Any] = {"name": _txt(floor.name)}
        _set(item, "level", floor.level)
        _set(item, "aliases", _txts(floor.aliases))
        floors[floor.floor_id] = item

    labels = {
        label.label_id: _txt(label.name)
        for label in sorted(label_reg.async_list_labels(), key=lambda l: l.name.casefold())
    }

    # --- Pièces (triées par niveau d'étage puis par nom) ----------------- #
    def _area_sort(area: ar.AreaEntry) -> tuple[int, str]:
        floor = floors_by_id.get(area.floor_id) if area.floor_id else None
        level = floor.level if floor and floor.level is not None else 999
        return (level, area.name.casefold())

    areas: dict[str, dict[str, Any]] = {}
    for area in sorted(area_reg.async_list_areas(), key=_area_sort):
        item = {"name": _txt(area.name)}
        _set(item, "floor", area.floor_id)
        _set(item, "aliases", _txts(area.aliases))
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
    disabled_count = 0
    excluded = {"config": 0, "diagnostic": 0, "integrations": 0}
    entities_by_device: dict[str, list[dict[str, Any]]] = {}
    entity_count = 0

    for entry in sorted(ent_reg.entities.values(), key=lambda e: e.entity_id):
        if entry.disabled_by:
            disabled_count += 1
            continue

        if entry.platform == DOMAIN:  # le bouton de cette intégration : sans intérêt
            continue

        device = dev_reg.async_get(entry.device_id) if entry.device_id else None
        device_integration = _device_integration(device) if device else None
        if excluded_integrations & {entry.platform, device_integration}:
            excluded["integrations"] += 1
            continue

        state = hass.states.get(entry.entity_id)
        attributes = state.attributes if state else {}
        device_class = _clean(
            entry.device_class or entry.original_device_class or attributes.get("device_class")
        )
        category = _clean(entry.entity_category)
        if device_class not in ALWAYS_KEEP_DEVICE_CLASSES:
            if category == "config" and not include_config:
                excluded["config"] += 1
                continue
            if category == "diagnostic" and not include_diagnostic:
                excluded["diagnostic"] += 1
                continue

        full_name = attributes.get("friendly_name") or _entity_fallback_name(entry, device)
        item: dict[str, Any] = {"id": entry.entity_id}
        _set(
            item,
            "name",
            _short_name(_txt(full_name), _txt(_device_name(device))) if device else _txt(full_name),
        )
        _set(item, "device_class", device_class)
        _set(
            item,
            "unit",
            entry.unit_of_measurement or attributes.get("unit_of_measurement"),
        )
        _set(item, "category", category)
        if entry.hidden_by:
            item["hidden"] = True
        _set(item, "aliases", _txts(entry.aliases))
        _set(item, "labels", entry.labels)
        item.update(_capabilities(entry.capabilities, attributes))
        entity_count += 1

        if device:
            if entry.platform != device_integration:
                item["integration"] = entry.platform
            if entry.area_id and entry.area_id != device.area_id:
                item["area"] = entry.area_id
            entities_by_device.setdefault(device.id, []).append(item)
        else:
            if entry.platform != entry.domain:
                item["integration"] = entry.platform
            _bucket(entry.area_id).setdefault("entities", []).append(item)

    # --- Appareils (seulement ceux qui ont des entités actives) ----------- #
    device_count = 0
    for device in sorted(dev_reg.devices.values(), key=lambda d: _device_name(d).casefold()):
        device_entities = entities_by_device.get(device.id)
        if not device_entities:
            continue
        item = {"name": _txt(_device_name(device))}
        _set(item, "manufacturer", device.manufacturer)
        _set(item, "model", device.model)
        _set(item, "integration", _device_integration(device))
        if device.via_device_id and (via := dev_reg.async_get(device.via_device_id)):
            _set(item, "via", _txt(_device_name(via)))
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
        _set(item, "name", _txt(state.attributes.get("friendly_name")))
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
        "generator_version": version,
        "ha_version": HA_VERSION,
        "exported_at": dt_util.now().isoformat(timespec="seconds"),
        "language": hass.config.language,
        "temperature_unit": hass.config.units.temperature_unit,
        "filters": {
            "config_entities": "included" if include_config else "excluded",
            "diagnostic_entities": "included" if include_diagnostic else "excluded",
            "always_kept_device_classes": sorted(ALWAYS_KEEP_DEVICE_CLASSES),
            "emails_in_names": "redacted" if redact_emails else "kept",
            "excluded_integrations": sorted(excluded_integrations),
        },
        "counts": {
            "floors": len(floors),
            "areas": len(areas),
            "devices": device_count,
            "entities": entity_count,
            "disabled": disabled_count,
            "excluded": excluded,
        },
    }

    # Étiquettes : seulement celles réellement portées par un élément exporté
    used_labels: set[str] = set()
    for node in (*areas.values(), unassigned, no_registry):
        stack = [node]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                used_labels.update(current.get("labels") or ())
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
    labels = {key: value for key, value in labels.items() if key in used_labels}

    data: dict[str, Any] = {"meta": _clean(meta)}
    _set(data, "floors", floors)
    _set(data, "labels", labels)
    _set(data, "areas", areas)
    _set(data, "unassigned", unassigned)
    _set(data, "no_registry", no_registry)
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
async def async_export(
    hass: HomeAssistant, path: Path, options: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Construit l'inventaire et l'écrit de façon atomique."""
    if is_forbidden_path(hass, str(path)):
        raise HomeAssistantError(
            f"Export refusé vers {path} : /config/www est public (servi sans authentification)"
        )

    integration = await async_get_integration(hass, DOMAIN)
    data = async_build_inventory(hass, options, str(integration.version))

    def _write() -> int:
        content = dump_inventory(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_utf8_file_atomic(str(path), content)
        return len(content.encode("utf-8"))

    try:
        size = await hass.async_add_executor_job(_write)
    except OSError as err:
        raise HomeAssistantError(f"Impossible d'écrire {path} : {err}") from err

    return {"path": str(path), "size_bytes": size, **data["meta"]["counts"]}
