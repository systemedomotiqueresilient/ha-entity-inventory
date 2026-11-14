"""Validation d'un YAML écrit par une IA contre l'instance réelle (lecture seule)."""

from __future__ import annotations

from collections.abc import Iterator
import re
from typing import Any

import yaml

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
import os

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
TEMPLATE_REFS = (
    re.compile(
        r"""(?:states|is_state|state_attr|is_state_attr|has_value|expand)\(\s*['"]([a-z0-9_]+\.[a-z0-9_]+)['"]"""
    ),
    re.compile(r"\bstates\.([a-z0-9_]+\.[a-z0-9_]+)\b"),
)

# (domaine, service) -> (clé dans data, attribut qui liste les valeurs permises)
VALUE_CHECKS: dict[tuple[str, str], tuple[str, str]] = {
    ("climate", "set_preset_mode"): ("preset_mode", "preset_modes"),
    ("climate", "set_hvac_mode"): ("hvac_mode", "hvac_modes"),
    ("climate", "set_fan_mode"): ("fan_mode", "fan_modes"),
    ("climate", "set_swing_mode"): ("swing_mode", "swing_modes"),
    ("fan", "set_preset_mode"): ("preset_mode", "preset_modes"),
    ("select", "select_option"): ("option", "options"),
    ("input_select", "select_option"): ("option", "options"),
    ("water_heater", "set_operation_mode"): ("operation_mode", "operation_list"),
    ("humidifier", "set_mode"): ("mode", "available_modes"),
    ("light", "turn_on"): ("effect", "effect_list"),
    ("media_player", "select_source"): ("source", "source_list"),
}
NON_NUMERIC_DOMAINS = {"group", "binary_sensor", "switch", "light", "input_boolean"}


def resolve_draft_path(hass: HomeAssistant, raw: str) -> str:
    """Fichier à valider : .yaml/.yml dans /config ou /share, jamais secrets.yaml."""
    path = os.path.realpath(hass.config.path(raw.strip()))
    roots = [os.path.realpath(hass.config.config_dir), "/share"]
    inside = any(path == root or path.startswith(root + os.sep) for root in roots)
    if (
        not inside
        or not path.endswith((".yaml", ".yml"))
        or os.path.basename(path) == "secrets.yaml"
    ):
        raise ServiceValidationError(
            f"Chemin refusé : {raw} (fichier .yaml dans /config ou /share, hors secrets.yaml)"
        )
    return path


def read_draft(path: str) -> str:
    """Lecture (à exécuter dans l'executor)."""
    try:
        with open(path, encoding="utf-8") as file:
            return file.read()
    except OSError as err:
        raise ServiceValidationError(f"Lecture impossible de {path} : {err}") from err


class _Loader(yaml.SafeLoader):
    """Accepte les balises HA (!input, !secret, !include…) sans les résoudre."""


def _any_tag(loader: yaml.SafeLoader, suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_mapping(node, deep=True)


_Loader.add_multi_constructor("!", _any_tag)


def _walk(node: Any, path: str = "") -> Iterator[tuple[Any, str]]:
    yield node, path
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def _entity_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        parts = [part.strip() for part in value if isinstance(part, str)]
    else:
        return []
    return [p for p in parts if ENTITY_RE.match(p) and p not in ("all", "none")]


def _is_template(value: Any) -> bool:
    return isinstance(value, str) and "{{" in value


UPDATE_WARNING = (
    "{where} : « {what} » déclenche une mise à jour automatique. Déconseillé : une mise à jour "
    "peut casser l'installation (intégration incompatible, migration, redémarrage) et doit rester "
    "une décision humaine, prise quand l'occupant peut réagir. Préférer une notification "
    "« mise à jour disponible » et installer à la main."
)


def _is_update_action(domain: str, name: str, data: dict[str, Any]) -> bool:
    """Actions qui installent une mise à jour (Home Assistant, modules, firmwares)."""
    if (domain, name) == ("update", "install"):
        return True
    if domain == "hassio" and "update" in name:  # hassio.addon_update…
        return True
    # Zigbee2MQTT : mise à jour OTA d'un appareil via MQTT
    topic = data.get("topic")
    return domain == "mqtt" and isinstance(topic, str) and "ota_update/update" in topic


@callback
def async_validate_yaml(hass: HomeAssistant, text: str) -> dict[str, Any]:
    """Analyse le YAML et renvoie erreurs (bloquantes) et avertissements."""
    errors: list[str] = []
    warnings: list[str] = []
    checked: set[str] = set()
    legacy: set[str] = set()
    actions_checked = 0
    ent_reg = er.async_get(hass)

    try:
        documents = [doc for doc in yaml.load_all(text, Loader=_Loader) if doc is not None]
    except yaml.YAMLError as err:
        return {"valid": False, "errors": [f"YAML illisible : {err}"], "warnings": [],
                "entities_checked": 0, "actions_checked": 0}

    def check_entity(entity_id: str, where: str) -> None:
        if entity_id in checked:
            return
        checked.add(entity_id)
        entry = ent_reg.async_get(entity_id)
        if hass.states.get(entity_id) is None and entry is None:
            errors.append(f"{where} : entité inexistante « {entity_id} »")
        elif entry is not None and entry.disabled_by:
            warnings.append(f"{where} : « {entity_id} » est désactivée, elle n'a pas d'état")

    for doc in documents:
        for node, path in _walk(doc):
            where = path or "racine"

            # Références dans les templates
            if isinstance(node, str):
                if "{{" in node or "{%" in node:
                    for pattern in TEMPLATE_REFS:
                        for entity_id in pattern.findall(node):
                            check_entity(entity_id, where)
                continue
            if not isinstance(node, dict):
                continue

            # Syntaxe historique (fonctionne encore, mais signe d'une IA qui écrit de mémoire)
            if isinstance(node.get("service"), str):
                legacy.add("« service: » → « action: »")
            if isinstance(node.get("platform"), str) and "trigger" not in node:
                legacy.add("« platform: » dans un déclencheur → « trigger: »")
            for old, new in (("trigger", "triggers"), ("condition", "conditions"), ("action", "actions")):
                if isinstance(node.get(old), list):
                    legacy.add(f"« {old}: » (liste) → « {new}: »")

            # entity_id explicites
            if "entity_id" in node and not _is_template(node["entity_id"]):
                for entity_id in _entity_ids(node["entity_id"]):
                    check_entity(entity_id, where)

            # Appels d'action
            service = node.get("action") if isinstance(node.get("action"), str) else None
            service = service or (node.get("service") if isinstance(node.get("service"), str) else None)
            if service and not _is_template(service) and "." in service:
                domain, name = service.split(".", 1)
                if domain == "entity_inventory" and name == "validate":
                    errors.append(
                        f"{where} : ce YAML est un appel à entity_inventory.validate lui-même. "
                        "Le fichier (ou le champ yaml) doit contenir uniquement le YAML produit "
                        "par l'IA, sans action/data/yaml ni bloc raw."
                    )
                    continue
                actions_checked += 1
                node_data = node.get("data") if isinstance(node.get("data"), dict) else {}
                if _is_update_action(domain, name, node_data):
                    warnings.append(UPDATE_WARNING.format(where=where, what=service))
                if not hass.services.has_service(domain, name):
                    if hass.states.get(service) is not None:
                        # Erreur classique : appeler une entité comme si c'était une action
                        if domain == "notify":
                            hint = (
                                f"utiliser « action: notify.send_message » avec "
                                f"« target: entity_id: {service} »"
                            )
                            if hass.services.has_service("notify", f"mobile_app_{name}"):
                                hint += f", ou l'ancienne action « notify.mobile_app_{name} »"
                        else:
                            hint = "une action s'écrit domaine.service (ex. switch.turn_on) avec cette entité en target"
                        errors.append(
                            f"{where} : « {service} » est une entité, pas une action — {hint}"
                        )
                    else:
                        errors.append(f"{where} : action inexistante « {service} »")
                data = node.get("data") if isinstance(node.get("data"), dict) else {}
                target = node.get("target") if isinstance(node.get("target"), dict) else {}
                targets = [
                    *_entity_ids(target.get("entity_id")),
                    *_entity_ids(data.get("entity_id")),
                    *_entity_ids(node.get("entity_id")),
                ]
                for entity_id in targets:
                    check_entity(entity_id, where)
                    if entity_id.split(".", 1)[0] != domain and domain not in ("homeassistant", "notify", "persistent_notification"):
                        warnings.append(f"{where} : « {service} » appliquée à « {entity_id} » (autre domaine)")
                rule = VALUE_CHECKS.get((domain, name))
                if rule and rule[0] in data and not _is_template(data[rule[0]]):
                    key, attribute = rule
                    value = data[key]
                    for entity_id in targets:
                        state = hass.states.get(entity_id)
                        allowed = state.attributes.get(attribute) if state else None
                        if not allowed:
                            continue
                        if isinstance(value, bool):
                            errors.append(
                                f"{where} : {key} vaut le booléen {value} — mettre la valeur "
                                f"entre guillemets (ex. 'off')"
                            )
                        elif str(value) not in [str(a) for a in allowed]:
                            errors.append(
                                f"{where} : {key} « {value} » invalide pour « {entity_id} » "
                                f"(valeurs possibles : {', '.join(map(str, allowed))})"
                            )

            # numeric_state sur une entité non numérique
            if "numeric_state" in (node.get("trigger"), node.get("platform"), node.get("condition")) \
                    and "attribute" not in node and "value_template" not in node:
                for entity_id in _entity_ids(node.get("entity_id")):
                    state = hass.states.get(entity_id)
                    numeric = False
                    if state is not None:
                        try:
                            float(state.state)
                            numeric = True
                        except ValueError:
                            numeric = state.state in ("unknown", "unavailable") and \
                                entity_id.split(".", 1)[0] not in NON_NUMERIC_DOMAINS
                    if state is not None and not numeric:
                        errors.append(
                            f"{where} : numeric_state sur « {entity_id} », dont l'état "
                            f"« {state.state} » n'est pas numérique"
                        )

    warnings.extend(f"Syntaxe ancienne : {item}" for item in sorted(legacy))
    if not documents:
        errors.append("Rien à vérifier : le texte ou le fichier est vide (ou ne contient que des commentaires).")
    elif not checked and not actions_checked and not errors:
        errors.append(
            "Rien à vérifier : aucune entité ni action trouvée. Le YAML de l'IA est-il bien "
            "présent (automatisation, script ou package) ?"
        )
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "entities_checked": len(checked),
        "actions_checked": actions_checked,
    }
