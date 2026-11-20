"""Config flow et options flow d'Entity Inventory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .admin_phone import (
    CONF_ADMIN_NOTIFY_TARGET,
    is_valid_target,
    normalize_target,
    suggest_admin_target,
)
from .const import (
    CONF_AREA_BUTTONS,
    CONF_EXCLUDED_INTEGRATIONS,
    CONF_INCLUDE_CONFIG,
    CONF_INCLUDE_DIAGNOSTIC,
    CONF_INCLUDE_PACKAGES,
    CONF_OUTPUT_PATH,
    CONF_REDACT_EMAILS,
    DEFAULT_AREA_BUTTONS,
    DEFAULT_INCLUDE_CONFIG,
    DEFAULT_INCLUDE_DIAGNOSTIC,
    DEFAULT_INCLUDE_PACKAGES,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_REDACT_EMAILS,
    DOMAIN,
)
from .exporter import default_output_path, destination_problem, is_forbidden_path

DEFAULTS: dict[str, Any] = {
    CONF_OUTPUT_PATH: DEFAULT_OUTPUT_PATH,
    CONF_INCLUDE_CONFIG: DEFAULT_INCLUDE_CONFIG,
    CONF_INCLUDE_DIAGNOSTIC: DEFAULT_INCLUDE_DIAGNOSTIC,
    CONF_EXCLUDED_INTEGRATIONS: [],
    CONF_REDACT_EMAILS: DEFAULT_REDACT_EMAILS,
    CONF_INCLUDE_PACKAGES: DEFAULT_INCLUDE_PACKAGES,
    CONF_AREA_BUTTONS: DEFAULT_AREA_BUTTONS,
}


def _schema(hass: HomeAssistant, values: dict[str, Any], target: str | None) -> vol.Schema:
    """Formulaire commun à l'ajout et aux options, pré-rempli avec `values`.

    `target` : téléphone admin actuel (options) ou None (ajout). La proposition
    vient du module commun admin_phone (valeurs des intégrations sœurs, sinon
    téléphones de l'application mobile).
    """
    suggested, choices = suggest_admin_target(hass, target)
    domains = sorted(
        {entry.domain for entry in hass.config_entries.async_entries() if entry.domain != DOMAIN}
        | set(values.get(CONF_EXCLUDED_INTEGRATIONS) or ())
    )
    return vol.Schema(
        {
            vol.Required(CONF_OUTPUT_PATH, default=values[CONF_OUTPUT_PATH]): TextSelector(),
            vol.Required(
                CONF_INCLUDE_CONFIG, default=values[CONF_INCLUDE_CONFIG]
            ): BooleanSelector(),
            vol.Required(
                CONF_INCLUDE_DIAGNOSTIC, default=values[CONF_INCLUDE_DIAGNOSTIC]
            ): BooleanSelector(),
            vol.Optional(
                CONF_EXCLUDED_INTEGRATIONS, default=values[CONF_EXCLUDED_INTEGRATIONS]
            ): SelectSelector(
                SelectSelectorConfig(
                    options=domains,
                    multiple=True,
                    custom_value=True,
                    sort=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_REDACT_EMAILS, default=values[CONF_REDACT_EMAILS]
            ): BooleanSelector(),
            vol.Required(
                CONF_INCLUDE_PACKAGES,
                default=values.get(CONF_INCLUDE_PACKAGES, DEFAULT_INCLUDE_PACKAGES),
            ): BooleanSelector(),
            vol.Required(
                CONF_AREA_BUTTONS,
                default=values.get(CONF_AREA_BUTTONS, DEFAULT_AREA_BUTTONS),
            ): BooleanSelector(),
            vol.Optional(
                CONF_ADMIN_NOTIFY_TARGET,
                description={"suggested_value": suggested},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=choices,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


async def _validate(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> tuple[dict, str | None, dict]:
    """Nettoie la saisie ; renvoie (options, téléphone admin, erreurs).

    Le téléphone admin ne va pas dans les options mais dans entry.data
    (convention admin_phone).
    """
    user_input = dict(user_input)
    raw_target = user_input.pop(CONF_ADMIN_NOTIFY_TARGET, None)
    options = {**DEFAULTS, CONF_OUTPUT_PATH: default_output_path(hass), **user_input}
    options[CONF_OUTPUT_PATH] = options[CONF_OUTPUT_PATH].strip()
    options[CONF_EXCLUDED_INTEGRATIONS] = sorted(
        {d.strip() for d in options[CONF_EXCLUDED_INTEGRATIONS] if d.strip()}
    )
    errors: dict[str, str] = {}
    target = normalize_target(raw_target)
    if raw_target and str(raw_target).strip() and not is_valid_target(raw_target):
        errors[CONF_ADMIN_NOTIFY_TARGET] = "invalid_target"
    if is_forbidden_path(hass, options[CONF_OUTPUT_PATH]):
        errors[CONF_OUTPUT_PATH] = "forbidden_www"
    else:
        path = Path(os.path.abspath(hass.config.path(options[CONF_OUTPUT_PATH])))
        if problem := await hass.async_add_executor_job(destination_problem, hass, path):
            errors[CONF_OUTPUT_PATH] = problem[0]
    return options, target, errors


class EntityInventoryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout de l'intégration depuis l'interface."""

    VERSION = 1
    MINOR_VERSION = 2  # 1.2 : téléphone admin dans entry.data (convention admin_phone)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        values = {**DEFAULTS, CONF_OUTPUT_PATH: default_output_path(self.hass)}
        target: str | None = None
        if user_input is not None:
            values, target, errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title="Entity Inventory",
                    data={CONF_ADMIN_NOTIFY_TARGET: target},
                    options=values,
                )

        return self.async_show_form(
            step_id="user", data_schema=_schema(self.hass, values, target), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EntityInventoryOptionsFlow()


class EntityInventoryOptionsFlow(OptionsFlow):
    """Modification du chemin et des filtres."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.config_entry
        values = {**DEFAULTS, **entry.options}
        target = normalize_target(entry.data.get(CONF_ADMIN_NOTIFY_TARGET))
        if user_input is not None:
            values, target, errors = await _validate(self.hass, user_input)
            if not errors:
                # Le téléphone admin vit dans entry.data : on le réécrit ici
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_ADMIN_NOTIFY_TARGET: target}
                )
                return self.async_create_entry(data=values)

        return self.async_show_form(
            step_id="init", data_schema=_schema(self.hass, values, target), errors=errors
        )
