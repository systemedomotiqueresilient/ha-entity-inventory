"""Config flow et options flow d'Entity Inventory."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import CONF_OUTPUT_PATH, DEFAULT_OUTPUT_PATH, DOMAIN
from .exporter import is_forbidden_path

SCHEMA = vol.Schema({vol.Required(CONF_OUTPUT_PATH): str})


class EntityInventoryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout de l'intégration depuis l'interface."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            path = user_input[CONF_OUTPUT_PATH].strip()
            if is_forbidden_path(self.hass, path):
                errors[CONF_OUTPUT_PATH] = "forbidden_www"
            else:
                return self.async_create_entry(
                    title="Entity Inventory",
                    data={},
                    options={CONF_OUTPUT_PATH: path},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                SCHEMA, user_input or {CONF_OUTPUT_PATH: DEFAULT_OUTPUT_PATH}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EntityInventoryOptionsFlow()


class EntityInventoryOptionsFlow(OptionsFlow):
    """Modification du chemin de sortie."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            path = user_input[CONF_OUTPUT_PATH].strip()
            if is_forbidden_path(self.hass, path):
                errors[CONF_OUTPUT_PATH] = "forbidden_www"
            else:
                return self.async_create_entry(data={CONF_OUTPUT_PATH: path})

        current = self.config_entry.options.get(CONF_OUTPUT_PATH, DEFAULT_OUTPUT_PATH)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                SCHEMA, user_input or {CONF_OUTPUT_PATH: current}
            ),
            errors=errors,
        )
