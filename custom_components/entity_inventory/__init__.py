"""Entity Inventory : exporte la structure de Home Assistant en YAML pour une IA."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .alerts import notification_id
from .const import ATTR_PATH, ATTR_YAML, DOMAIN, SERVICE_EXPORT, SERVICE_VALIDATE
from .exporter import async_export, export_options, resolve_output_path
from .validator import async_validate_yaml, read_draft, resolve_draft_path
from .watchman import async_check as async_check_watchman
from .watchman import issue_id as watchman_issue_id

PLATFORMS: list[Platform] = [Platform.BUTTON]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Enregistre le service entity_inventory.export."""

    async def _handle_export(call: ServiceCall) -> ServiceResponse:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not entries:
            raise HomeAssistantError("Entity Inventory n'est pas configuré")
        entry = entries[0]
        path = resolve_output_path(hass, entry)
        result = await async_export(hass, path, export_options(entry))
        async_check_watchman(hass, entry, path)
        return result if call.return_response else None

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT,
        _handle_export,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def _handle_validate(call: ServiceCall) -> ServiceResponse:
        # Fichier : rien n'est évalué comme template en chemin (cas du YAML qui
        # contient {{ trigger… }}, que les outils de développement interpréteraient).
        if ATTR_PATH in call.data:
            path = resolve_draft_path(hass, call.data[ATTR_PATH])
            text = await hass.async_add_executor_job(read_draft, path)
        else:
            text = call.data[ATTR_YAML]
        return async_validate_yaml(hass, text)

    hass.services.async_register(
        DOMAIN,
        SERVICE_VALIDATE,
        _handle_validate,
        schema=vol.All(
            vol.Schema(
                {
                    vol.Exclusive(ATTR_YAML, "source"): cv.string,
                    vol.Exclusive(ATTR_PATH, "source"): cv.string,
                }
            ),
            cv.has_at_least_one_key(ATTR_YAML, ATTR_PATH),
        ),
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Met en place le bouton d'export."""
    entry.runtime_data = dict(entry.options)  # pour ne recharger qu'au changement d'options
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    @callback
    def _check_watchman(_hass: HomeAssistant) -> None:
        async_check_watchman(hass, entry, resolve_output_path(hass, entry))

    # Après le démarrage : Watchman peut être chargé après nous
    entry.async_on_unload(async_at_started(hass, _check_watchman))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge l'intégration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Suppression de l'intégration : retirer la réparation éventuelle."""
    ir.async_delete_issue(hass, DOMAIN, watchman_issue_id(entry))
    persistent_notification.async_dismiss(hass, notification_id(entry, "watchman"))


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if dict(entry.options) != getattr(entry, "runtime_data", None):
        await hass.config_entries.async_reload(entry.entry_id)
