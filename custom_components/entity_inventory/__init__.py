"""Entity Inventory : exporte la structure de Home Assistant en YAML pour une IA."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_PATH, ATTR_YAML, DOMAIN, SERVICE_EXPORT, SERVICE_VALIDATE
from .exporter import async_export, export_options, resolve_output_path
from .validator import async_validate_yaml, read_draft, resolve_draft_path

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
        result = await async_export(
            hass, resolve_output_path(hass, entry), export_options(entry)
        )
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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge l'intégration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
