"""0.9.0 : « Téléphone admin » (module commun admin_phone 1.1.0) et petites corrections."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.entity_inventory import admin_phone
from custom_components.entity_inventory.admin_phone import (
    ATTR_NOTIFY_SERVICE,
    CONF_ADMIN_NOTIFY_TARGET,
)
from custom_components.entity_inventory.const import CONF_OUTPUT_PATH, DOMAIN, VERSION

MOBILE = "notify.mobile_app_pixel_9"
OTHER = "notify.mobile_app_tablette"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _sibling(hass: HomeAssistant, platform: str, value: str | None, entry_id: str = "s") -> str:
    """Entité « téléphone admin » d'une intégration sœur."""
    entity = er.async_get(hass).async_get_or_create(
        "sensor", platform, f"{entry_id}_admin_notify_target",
        suggested_object_id=f"{platform}_{entry_id}_admin_phone",
    )
    hass.states.async_set(entity.entity_id, value or "unknown", {ATTR_NOTIFY_SERVICE: value})
    return entity.entity_id


def _field(result: dict) -> tuple[str | None, list[str]]:
    """(valeur suggérée, choix) du champ téléphone admin du formulaire."""
    for key, selector in result["data_schema"].schema.items():
        if key == CONF_ADMIN_NOTIFY_TARGET:
            suggested = (key.description or {}).get("suggested_value")
            return suggested, list(selector.config["options"])
    raise AssertionError("champ admin_notify_target absent")


async def _start_flow(hass: HomeAssistant) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def _create(hass: HomeAssistant, tmp_path: Path, target: str | None) -> config_entries.ConfigEntry:
    result = await _start_flow(hass)
    user_input = {CONF_OUTPUT_PATH: str(tmp_path / "e.yaml")}
    if target is not None:
        user_input[CONF_ADMIN_NOTIFY_TARGET] = target
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]


def _sensor_id(hass: HomeAssistant, entry: config_entries.ConfigEntry) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_admin_notify_target"
    )
    assert entity_id
    return entity_id


# --- Config flow : proposition à la première installation ------------------


async def test_none_found_offers_mobile_services(hass: HomeAssistant, tmp_path: Path) -> None:
    hass.services.async_register("notify", "mobile_app_pixel_9", lambda call: None)
    hass.services.async_register("notify", "smtp_mail", lambda call: None)
    suggested, choices = _field(await _start_flow(hass))
    assert suggested is None
    assert choices == [MOBILE]

    entry = await _create(hass, tmp_path, None)
    assert entry.data[CONF_ADMIN_NOTIFY_TARGET] is None
    assert CONF_ADMIN_NOTIFY_TARGET not in entry.options
    state = hass.states.get(_sensor_id(hass, entry))
    assert state.state == "unknown"
    assert state.attributes[ATTR_NOTIFY_SERVICE] is None


async def test_one_found_is_prefilled(hass: HomeAssistant, tmp_path: Path) -> None:
    _sibling(hass, "partition_map", MOBILE)
    suggested, choices = _field(await _start_flow(hass))
    assert suggested == MOBILE
    assert choices[0] == MOBILE

    entry = await _create(hass, tmp_path, MOBILE)
    assert entry.data[CONF_ADMIN_NOTIFY_TARGET] == MOBILE
    state = hass.states.get(_sensor_id(hass, entry))
    assert state.state == MOBILE
    assert state.attributes[ATTR_NOTIFY_SERVICE] == MOBILE
    assert state.attributes["admin_phone_convention"] == 1


async def test_several_values_give_a_choice(hass: HomeAssistant) -> None:
    _sibling(hass, "partition_map", MOBILE, "a")
    _sibling(hass, "sentinel_report", OTHER, "b")
    suggested, choices = _field(await _start_flow(hass))
    assert suggested is None
    assert choices == [MOBILE, OTHER]


async def test_unlisted_platform_ignored(hass: HomeAssistant) -> None:
    _sibling(hass, "spook", MOBILE, "a")
    _sibling(hass, "sentinel", OTHER, "b")
    suggested, choices = _field(await _start_flow(hass))
    assert suggested is None
    assert choices == []


async def test_invalid_target_refused(hass: HomeAssistant, tmp_path: Path) -> None:
    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_OUTPUT_PATH: str(tmp_path / "e.yaml"), CONF_ADMIN_NOTIFY_TARGET: "mon_telephone"},
    )
    assert result["errors"] == {CONF_ADMIN_NOTIFY_TARGET: "invalid_target"}


async def test_sibling_removed_value_kept(hass: HomeAssistant, tmp_path: Path) -> None:
    """La valeur est copiée dans entry.data : la suppression de la sœur ne la perd pas."""
    sibling = _sibling(hass, "sentinel_report", MOBILE)
    entry = await _create(hass, tmp_path, MOBILE)

    er.async_get(hass).async_remove(sibling)
    hass.states.async_remove(sibling)
    await hass.async_block_till_done()

    assert entry.data[CONF_ADMIN_NOTIFY_TARGET] == MOBILE
    assert hass.states.get(_sensor_id(hass, entry)).state == MOBILE
    # L'options flow repropose la valeur actuelle
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert _field(result)[0] == MOBILE


# --- Options flow, capteur, lecture seule -----------------------------------


async def test_options_flow_updates_data_and_sensor(hass: HomeAssistant, tmp_path: Path) -> None:
    entry = await _create(hass, tmp_path, MOBILE)
    sensor = _sensor_id(hass, entry)
    output = entry.options[CONF_OUTPUT_PATH]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_OUTPUT_PATH: output, CONF_ADMIN_NOTIFY_TARGET: OTHER}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data[CONF_ADMIN_NOTIFY_TARGET] == OTHER
    assert CONF_ADMIN_NOTIFY_TARGET not in entry.options
    assert hass.states.get(sensor).state == OTHER

    # Champ vidé : plus de téléphone admin
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_OUTPUT_PATH: output}
    )
    await hass.async_block_till_done()
    assert entry.data[CONF_ADMIN_NOTIFY_TARGET] is None
    assert hass.states.get(sensor).state == "unknown"


async def test_sensor_convention(hass: HomeAssistant, tmp_path: Path) -> None:
    entry = await _create(hass, tmp_path, MOBILE)
    reg_entry = er.async_get(hass).async_get(_sensor_id(hass, entry))
    assert reg_entry.unique_id == f"{entry.entry_id}_admin_notify_target"
    assert reg_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert reg_entry.platform == DOMAIN
    # Entity Inventory est lui-même une sœur : une autre intégration le retrouvera
    assert admin_phone.find_admin_targets(hass) == [MOBILE]


async def test_sibling_entity_never_written(hass: HomeAssistant, tmp_path: Path) -> None:
    sibling = _sibling(hass, "partition_map", MOBILE)
    before = hass.states.get(sibling)
    entry = await _create(hass, tmp_path, OTHER)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_OUTPUT_PATH: entry.options[CONF_OUTPUT_PATH], CONF_ADMIN_NOTIFY_TARGET: MOBILE},
    )
    await hass.async_block_till_done()
    after = hass.states.get(sibling)
    assert after.state == before.state and after.last_updated == before.last_updated


# --- Migration 1.1 → 1.2 -----------------------------------------------------


async def test_migration_moves_legacy_option(hass: HomeAssistant, tmp_path: Path) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        data={"alerted": {}},
        options={CONF_OUTPUT_PATH: str(tmp_path / "e.yaml"), "notify_entity": "notify.iphone"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 2
    assert entry.data == {"alerted": {}, CONF_ADMIN_NOTIFY_TARGET: "notify.iphone"}
    assert "notify_entity" not in entry.options
    assert entry.options[CONF_OUTPUT_PATH] == str(tmp_path / "e.yaml")
    assert hass.states.get(_sensor_id(hass, entry)).state == "notify.iphone"


async def test_migration_without_legacy_option(hass: HomeAssistant, tmp_path: Path) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=1,
        options={CONF_OUTPUT_PATH: str(tmp_path / "e.yaml")},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.minor_version == 2
    assert entry.data[CONF_ADMIN_NOTIFY_TARGET] is None


async def test_future_version_refused(hass: HomeAssistant, tmp_path: Path) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, options={CONF_OUTPUT_PATH: str(tmp_path / "e.yaml")}
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.MIGRATION_ERROR


# --- Envoi des alertes par le module commun ---------------------------------


async def test_alert_sent_to_mobile_service(hass: HomeAssistant, tmp_path: Path) -> None:
    """Forme « service » (notify.mobile_app_*) : appel direct, en plus de la notification."""
    calls: list[ServiceCall] = []

    async def _handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("notify", "mobile_app_pixel_9", _handler)
    target = tmp_path / "absent" / "e.yaml"
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=2,
        data={CONF_ADMIN_NOTIFY_TARGET: MOBILE},
        options={CONF_OUTPUT_PATH: str(target)},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_start()
    await hass.async_block_till_done()

    assert f"{DOMAIN}_export_{entry.entry_id}" in (
        persistent_notification._async_get_or_create_notifications(hass)
    )
    assert len(calls) == 1
    assert "absent" in calls[0].data["message"]


async def test_alert_phone_unreachable_does_not_break(hass: HomeAssistant, tmp_path: Path) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=2,
        data={CONF_ADMIN_NOTIFY_TARGET: "notify.mobile_app_disparu"},
        options={CONF_OUTPUT_PATH: str(tmp_path / "absent" / "e.yaml")},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_start()
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert f"{DOMAIN}_export_{entry.entry_id}" in (
        persistent_notification._async_get_or_create_notifications(hass)
    )


# --- Module copié à l'identique, versions cohérentes ------------------------


def test_module_copy_and_versions() -> None:
    import hashlib
    import json

    root = Path(__file__).parents[1]
    module = root / "custom_components" / DOMAIN / "admin_phone.py"
    assert admin_phone.MODULE_VERSION == "1.3.0"
    assert hashlib.sha256(module.read_bytes()).hexdigest() == (
        "38f74609b319ceb0c56395ff13454d8bbdc72246b1dc02bcf6ad4babf768ddf8"
    )
    manifest = json.loads((root / "custom_components" / DOMAIN / "manifest.json").read_text())
    assert manifest["version"] == VERSION == (root / "VERSION").read_text().strip()


# --- Corrections incluses dans la 0.9.0 --------------------------------------


def test_scanner_ignores_example_values(tmp_path: Path) -> None:
    from custom_components.entity_inventory.packages import scan_packages

    (tmp_path / "packages").mkdir()
    (tmp_path / "configuration.yaml").write_text(
        "homeassistant:\n  packages: !include_dir_named packages\n", encoding="utf-8"
    )
    (tmp_path / "packages" / "watchman_scripts.yaml").write_text(
        "script:\n"
        "  watchman_delete_entity:\n"
        "    fields:\n"
        "      entity:\n"
        "        example: sensor.entite_manquante\n"
        "        default: sensor.vraie_cible\n"
        "    sequence:\n"
        "      - action: homeassistant.update_entity\n"
        "        target:\n"
        "          entity_id: sensor.utilisee\n",
        encoding="utf-8",
    )
    (pkg,) = scan_packages(str(tmp_path))
    assert "sensor.entite_manquante" not in pkg.cited
    # Une valeur par défaut peut être réellement utilisée : elle reste vérifiée
    assert {"sensor.vraie_cible", "sensor.utilisee"} <= set(pkg.cited)


def test_header_initiative_rule_wording() -> None:
    from custom_components.entity_inventory.exporter import HEADER

    assert "ta réponse COMMENCE par les signaler" in HEADER
    assert "nomme-les TOUS" in HEADER
    assert "TERMINE en lui proposant de corriger" in HEADER
