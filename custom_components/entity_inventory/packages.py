"""Section « packages » : ce que chaque fichier de package crée, et ce qu'il cite qui a disparu.

Une IA ne répare que ce qu'on lui montre. En listant les packages avec les entités citées
qui n'existent plus, l'inventaire désigne lui-même les fichiers cassés (ex. après le
remplacement d'une sonde), sans que l'occupant ait à les retrouver.

Lecture seule, avec le chargeur YAML de Home Assistant (!include, !secret…). Le contenu
des fichiers n'est jamais exporté : seulement leur nom, leur première ligne de commentaire
et des entity_id. Les valeurs de !secret sont chargées par le chargeur mais jamais lues ici.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util.yaml.loader import Secrets, load_yaml_dict

# Clés dont la valeur n'est jamais une entité citée
_SKIP_KEYS = frozenset({
    "action", "service", "service_template", "platform", "unique_id", "id", "name",
    "alias", "description", "icon", "unit_of_measurement", "device_class", "state_class",
    "friendly_name", "event_type", "mode",
})
# Domaines dont les clés de premier niveau sont des object_id (input_boolean: {x: …})
_KEYED_DOMAINS = frozenset({
    "input_boolean", "input_button", "input_datetime", "input_number", "input_select",
    "input_text", "counter", "timer", "script", "zone", "schedule",
})
_EXTRA_DOMAINS = frozenset({
    "automation", "script", "scene", "group", "zone", "person", "sun", "schedule",
    "counter", "timer", "input_boolean", "input_button", "input_datetime",
    "input_number", "input_select", "input_text", "device_tracker", "proximity",
})
_ENTITY_RE = re.compile(r"(?<![\w.])([a-z_]+)\.([a-z0-9_]+)\b")
_COMMENT_RE = re.compile(r"^\s*#+\s*(.*?)\s*$")
# Commentaires qui ressemblent à du code ou à un chemin, pas à une description :
# « sensor: », « platform: derivative », « - service: x », « packages/chauffage.yaml »
_CODE_RE = re.compile(r"^(?:-\s|[a-z0-9_]+:(?:\s|$)|\S*(?:/|\.ya?ml)\S*$)")


@dataclass
class RawPackage:
    """Ce qui a été lu sur disque, avant comparaison avec les registres."""

    name: str
    file: str
    description: str | None = None
    unique_ids: set[str] = field(default_factory=set)
    automation_ids: set[str] = field(default_factory=set)
    keyed: set[str] = field(default_factory=set)  # domain.object_id déclarés
    cited: set[str] = field(default_factory=set)  # chaînes « domaine.objet » rencontrées


def _strings(node: Any, key: str | None = None) -> Iterator[str]:
    """Toutes les chaînes du package, sauf celles des clés qui ne citent pas d'entité."""
    if key in _SKIP_KEYS:
        return
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, str(k))
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, key)


def _walk_dicts(node: Any) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_dicts(v)


def _description(path: str) -> str | None:
    """Première ligne de commentaire qui contient du texte (les lignes « # ==== » sont sautées)."""
    try:
        with open(path, encoding="utf-8") as handle:
            for _, line in zip(range(40), handle):
                match = _COMMENT_RE.match(line)
                if match is None:
                    if line.strip():
                        return None  # le contenu commence : pas d'en-tête
                    continue
                text = match.group(1).strip("=-*_~ ")
                if any(c.isalpha() for c in text) and not _CODE_RE.match(text):
                    return text[:150]
    except OSError:
        return None
    return None


def scan_packages(config_dir: str) -> list[RawPackage] | None:
    """Lit les packages déclarés dans configuration.yaml. E/S : à lancer dans l'exécuteur.

    None si la configuration est illisible (on n'empêche pas l'export pour autant).
    """
    config_path = Path(config_dir, "configuration.yaml")
    if not config_path.is_file():
        return []
    try:
        config = load_yaml_dict(config_path, Secrets(Path(config_dir)))
    except Exception:  # noqa: BLE001 — YAML invalide, !secret manquant… : section omise
        return None
    core = config.get("homeassistant")
    packages = core.get("packages") if isinstance(core, dict) else None
    if not isinstance(packages, dict):
        return []

    result: list[RawPackage] = []
    for name, content in packages.items():
        if not isinstance(content, dict):
            continue
        source = getattr(content, "__config_file__", None) or str(config_path)
        raw = RawPackage(
            name=str(name),
            file=os.path.relpath(source, config_dir) if source.startswith(config_dir) else source,
            description=_description(source),
        )
        for domain, block in content.items():
            domain = str(domain)
            if domain in _KEYED_DOMAINS and isinstance(block, dict):
                raw.keyed.update(f"{domain}.{key}" for key in block)
            if domain == "automation":
                for item in block if isinstance(block, list) else [block]:
                    if isinstance(item, dict) and isinstance(item.get("id"), (str, int)):
                        raw.automation_ids.add(str(item["id"]))
            for node in _walk_dicts(block):
                if isinstance(node.get("unique_id"), (str, int)):
                    raw.unique_ids.add(str(node["unique_id"]))
        for text in _strings(content):
            text = text.replace("states.", " ")  # states.sensor.x → sensor.x
            raw.cited.update(f"{d}.{o}" for d, o in _ENTITY_RE.findall(text))
        result.append(raw)
    return sorted(result, key=lambda p: p.name.casefold())


@callback
def async_resolve_packages(
    hass: HomeAssistant,
    raw_packages: list[RawPackage],
    txt: Any,
    only_touching: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Compare chaque package aux registres : entités créées, citées disparues, désactivées.

    only_touching : export ciblé, ne garder que les packages qui créent ou citent l'une de
    ces entités, plus tous les packages cassés.
    """
    ent_reg = er.async_get(hass)
    yaml_uids: dict[str, str] = {}
    automation_uids: dict[str, str] = {}
    for entry in ent_reg.entities.values():
        if entry.config_entry_id is not None:
            continue
        if entry.platform == "automation":
            automation_uids[entry.unique_id] = entry.entity_id
        else:
            yaml_uids.setdefault(entry.unique_id, entry.entity_id)

    domains = {state.domain for state in hass.states.async_all()}
    domains |= {entry.domain for entry in ent_reg.entities.values()}
    domains |= {str(p) for p in Platform} | _EXTRA_DOMAINS

    def exists(entity_id: str) -> bool:
        return hass.states.get(entity_id) is not None or ent_reg.async_get(entity_id) is not None

    out: dict[str, dict[str, Any]] = {}
    for raw in raw_packages:
        defines = {yaml_uids[u] for u in raw.unique_ids if u in yaml_uids}
        defines |= {automation_uids[a] for a in raw.automation_ids if a in automation_uids}
        defines |= {e for e in raw.keyed if exists(e)}

        missing: set[str] = set()
        disabled: set[str] = set()
        for entity_id in raw.cited - defines - raw.keyed:
            if entity_id.split(".", 1)[0] not in domains:
                continue
            entry = ent_reg.async_get(entity_id)
            if entry is not None and entry.disabled_by:
                disabled.add(entity_id)
            elif not exists(entity_id):
                missing.add(entity_id)

        item: dict[str, Any] = {"file": raw.file}
        if raw.description:
            item["description"] = txt(raw.description)
        # Export ciblé : les packages qui touchent la cible, et TOUJOURS les packages cassés,
        # dont les entités disparues ne peuvent plus être rattachées à une pièce.
        if (
            only_touching is not None
            and not missing
            and not (defines | raw.cited | raw.keyed) & only_touching
        ):
            continue
        for key, values in (("defines", defines), ("missing", missing), ("disabled", disabled)):
            if values:
                item[key] = sorted(values)
        out[raw.name] = item
    return out
