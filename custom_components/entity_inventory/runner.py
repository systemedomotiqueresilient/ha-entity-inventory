"""Lancement d'un export (bouton, action) avec alerte en cas d'échec."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .alerts import async_clear, async_raise, reason_text
from .exporter import (
    async_export,
    destination_problem,
    export_options,
    resolve_output_path,
    scoped_path,
)
from .watchman import async_check as async_check_watchman

ALERT_EXPORT = "export"


async def async_run_export(
    hass: HomeAssistant,
    entry: ConfigEntry,
    scope: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Exporte ; un échec est signalé (notification + téléphone) au lieu de passer inaperçu.

    Indispensable quand l'export est lancé par une automatisation : personne ne voit
    l'erreur, et l'IA travaillerait sur un inventaire périmé.
    """
    main_path = resolve_output_path(hass, entry)
    path = scoped_path(main_path, scope) if scope else main_path
    if not write:  # rien d'écrit sur le disque : ni vérification de dossier, ni Watchman
        return await async_export(hass, path, export_options(entry), scope, write=False)
    problem = await hass.async_add_executor_job(destination_problem, hass, path)
    if problem:
        error = reason_text(hass, *problem)
        async_raise(hass, entry, ALERT_EXPORT, str(path), error=error)
        raise HomeAssistantError(f"Export impossible vers {path} : {error}")
    try:
        result = await async_export(hass, path, export_options(entry), scope)
    except HomeAssistantError as err:
        cause = err.__cause__ or err
        async_raise(hass, entry, ALERT_EXPORT, str(path), error=str(cause))
        raise
    async_clear(hass, entry, ALERT_EXPORT)
    async_check_watchman(hass, entry, main_path)  # le motif couvre aussi les exports ciblés
    return result


async def async_check_destination(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Au démarrage : prévenir tout de suite si le dossier de sortie a disparu
    (ex. configuration restaurée sur une installation sans /share)."""
    path = resolve_output_path(hass, entry)
    problem = await hass.async_add_executor_job(destination_problem, hass, path)
    if problem:
        async_raise(hass, entry, ALERT_EXPORT, str(path), error=reason_text(hass, *problem))


@callback
def async_forget_export_alert(hass: HomeAssistant, entry: ConfigEntry) -> None:
    async_clear(hass, entry, ALERT_EXPORT)
