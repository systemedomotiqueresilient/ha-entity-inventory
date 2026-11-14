"""Cohabitation avec Watchman (dummylabs/thewatchman).

Watchman parcourt les fichiers .yaml de /config et signale toute entité citée qui est
introuvable, indisponible ou inconnue. L'export cite des centaines d'entités, dont
beaucoup sont normalement « unknown » (boutons, scènes, tts…) : sans exception, il
pollue le rapport. On le signale par une réparation ; la correction (ajout du chemin
dans les fichiers ignorés de Watchman) n'est appliquée qu'après confirmation.
"""

from __future__ import annotations

from fnmatch import fnmatch
import logging
import os
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

WATCHMAN_DOMAIN = "watchman"
WATCHMAN_KEY = "ignored_files"
DATA_WATCHMAN_PATTERN = "watchman_pattern"  # motif ajouté par nous (data de notre entrée)


def issue_id(entry: ConfigEntry) -> str:
    return f"watchman_scans_export_{entry.entry_id}"


def _watchman_entry(hass: HomeAssistant) -> ConfigEntry | None:
    for entry in hass.config_entries.async_entries(WATCHMAN_DOMAIN):
        if entry.disabled_by is None and entry.state is not ConfigEntryState.SETUP_ERROR:
            return entry
    return None


def _read_ignored(entry: ConfigEntry) -> tuple[str, list[str], bool] | None:
    """(emplacement, motifs, stocké en texte) — None si format inconnu."""
    for location in ("data", "options"):
        container = getattr(entry, location)
        if WATCHMAN_KEY in container:
            value = container[WATCHMAN_KEY]
            if isinstance(value, list):
                return location, [str(v).strip() for v in value if str(v).strip()], False
            if isinstance(value, str):  # anciennes versions : "a.yaml, b.yaml"
                return location, [v.strip() for v in value.split(",") if v.strip()], True
            return None
    return "data", [], False  # clé absente : format actuel (0.8+)


def _is_covered(hass: HomeAssistant, path: Path, patterns: list[str]) -> bool:
    absolute = str(path)
    relative = os.path.relpath(absolute, hass.config.config_dir)
    return any(fnmatch(absolute, p) or fnmatch(relative, p) for p in patterns)


def _inside_config(hass: HomeAssistant, path: Path) -> bool:
    config = os.path.realpath(hass.config.config_dir)
    return os.path.realpath(path).startswith(config + os.sep)


@callback
def async_check(hass: HomeAssistant, entry: ConfigEntry, path: Path) -> None:
    """Crée ou retire la réparation selon la situation actuelle."""
    watchman = _watchman_entry(hass)
    needed = False
    if watchman is not None and _inside_config(hass, path):
        current = _read_ignored(watchman)
        needed = current is None or not _is_covered(hass, path, current[1])

    if needed:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id(entry),
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="watchman_scans_export",
            translation_placeholders={"path": str(path)},
            data={"entry_id": entry.entry_id, "path": str(path)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry))


@callback
def async_add_exception(hass: HomeAssistant, entry: ConfigEntry, path: Path) -> bool:
    """Ajoute le chemin aux fichiers ignorés de Watchman (et retire notre ancien motif)."""
    watchman = _watchman_entry(hass)
    if watchman is None:
        return False
    current = _read_ignored(watchman)
    if current is None:
        _LOGGER.warning("Format des fichiers ignorés de Watchman non reconnu : rien n'a été modifié")
        return False
    location, patterns, as_text = current

    new_pattern = str(path)
    old_pattern = entry.data.get(DATA_WATCHMAN_PATTERN)
    patterns = [p for p in patterns if p != old_pattern]
    if new_pattern not in patterns:
        patterns.append(new_pattern)
    value: Any = ", ".join(patterns) if as_text else patterns

    container = dict(getattr(watchman, location))
    container[WATCHMAN_KEY] = value
    hass.config_entries.async_update_entry(watchman, **{location: container})
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, DATA_WATCHMAN_PATTERN: new_pattern}
    )
    ir.async_delete_issue(hass, DOMAIN, issue_id(entry))
    _LOGGER.info("Watchman : %s ajouté aux fichiers ignorés", new_pattern)
    return True
