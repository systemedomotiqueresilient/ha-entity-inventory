"""Entity Inventory : exporte la structure de Home Assistant en YAML pour une IA."""

from __future__ import annotations

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
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    floor_registry as fr,
    issue_registry as ir,
    label_registry as lr,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .admin_phone import CONF_ADMIN_NOTIFY_TARGET, normalize_target
from .alerts import notification_id
from .const import (
    ATTR_PATH,
    ATTR_YAML,
    DOMAIN,
    LEGACY_CONF_NOTIFY_ENTITY,
    SERVICE_EXPORT,
    SERVICE_VALIDATE,
)
from .exporter import resolve_output_path
from .runner import ALERT_EXPORT, async_check_destination, async_run_export
from .validator import async_validate_yaml, read_draft, resolve_draft_path
from .watchman import async_check as async_check_watchman, issue_id as watchman_issue_id

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR]

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
        scope = {
            key: call.data[key]
            for key in ("areas", "floors", "labels", "domains")
            if call.data.get(key)
        }
        _check_scope(hass, scope)
        write = call.data.get("write", True)
        if not write and not call.return_response:
            raise ServiceValidationError(
                "write: false ne renvoie l'inventaire que dans la réponse de l'action : "
                "activez la réponse (outils de développement) ou retirez write: false"
            )
        result = await async_run_export(hass, entries[0], scope or None, write)
        if scope:
            result = {**result, "scope": scope}
        return result if call.return_response else None

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT,
        _handle_export,
        schema=vol.Schema(
            {
                vol.Optional("areas"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("floors"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("labels"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("domains"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("write", default=True): cv.boolean,
            }
        ),
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


def _check_scope(hass: HomeAssistant, scope: dict[str, list[str]]) -> None:
    """Une cible inconnue donnerait un export vide sans explication : on refuse clairement."""
    known = {
        "areas": {a.id for a in ar.async_get(hass).async_list_areas()},
        "floors": {f.floor_id for f in fr.async_get(hass).async_list_floors()},
        "labels": {lab.label_id for lab in lr.async_get(hass).async_list_labels()},
    }
    for key, valid in known.items():
        unknown = sorted(set(scope.get(key, ())) - valid)
        if unknown:
            raise ServiceValidationError(
                f"{key} inconnu(s) : {', '.join(unknown)}. Valeurs possibles : "
                f"{', '.join(sorted(valid)) or 'aucune'}"
            )


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migre les entrées existantes, sans perte.

    1.1 → 1.2 : l'option « notify_entity » (≤ 0.8.x, une entité notify) devient
    entry.data["admin_notify_target"] (convention admin_phone). La valeur est
    reprise telle quelle : admin_phone ≥ 1.1.0 accepte les entités notify.
    """
    if entry.version > 1:
        return False  # entrée créée par une version plus récente
    if entry.minor_version < 2:
        options = dict(entry.options)
        legacy = options.pop(LEGACY_CONF_NOTIFY_ENTITY, None)
        target = normalize_target(entry.data.get(CONF_ADMIN_NOTIFY_TARGET)) or normalize_target(
            legacy
        )
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_ADMIN_NOTIFY_TARGET: target},
            options=options,
            minor_version=2,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Met en place les boutons d'export et le capteur « Téléphone admin »."""
    entry.runtime_data = dict(entry.options)  # pour ne recharger qu'au changement d'options
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    @callback
    def _check_at_start(_hass: HomeAssistant) -> None:
        async_check_watchman(hass, entry, resolve_output_path(hass, entry))
        entry.async_create_task(
            hass, async_check_destination(hass, entry), f"{DOMAIN} vérification du dossier"
        )

    # Après le démarrage : Watchman peut être chargé après nous
    entry.async_on_unload(async_at_started(hass, _check_at_start))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge l'intégration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Suppression de l'intégration : retirer la réparation éventuelle."""
    ir.async_delete_issue(hass, DOMAIN, watchman_issue_id(entry))
    for key in ("watchman", ALERT_EXPORT):
        persistent_notification.async_dismiss(hass, notification_id(entry, key))


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if dict(entry.options) != getattr(entry, "runtime_data", None):
        await hass.config_entries.async_reload(entry.entry_id)
