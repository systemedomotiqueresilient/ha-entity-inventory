"""0.5.2 : passerelle des appareils, vérification du dossier, alerte d'export."""

from pathlib import Path

import pytest
import yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.entity_inventory.const import CONF_OUTPUT_PATH, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _setup(hass: HomeAssistant, path: str, **options) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_OUTPUT_PATH: path, **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _notifications(hass: HomeAssistant) -> dict:
    return persistent_notification._async_get_or_create_notifications(hass)


async def test_via_device(hass: HomeAssistant, tmp_path: Path) -> None:
    mqtt = MockConfigEntry(domain="mqtt")
    mqtt.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    bridge = dev_reg.async_get_or_create(
        config_entry_id=mqtt.entry_id, identifiers={("mqtt", "bridge")}, name="ZBBridge-U"
    )
    probe = dev_reg.async_get_or_create(
        config_entry_id=mqtt.entry_id,
        identifiers={("mqtt", "probe")},
        name="WC",
        via_device=("mqtt", "bridge"),
    )
    alone = dev_reg.async_get_or_create(
        config_entry_id=mqtt.entry_id, identifiers={("mqtt", "alone")}, name="Prise"
    )
    for dev, uid in ((bridge, "b"), (probe, "p"), (alone, "a")):
        ent_reg.async_get_or_create("sensor", "mqtt", uid, device_id=dev.id)

    await _setup(hass, str(tmp_path / "e.yaml"))
    await hass.services.async_call(DOMAIN, "export", {}, blocking=True)
    text = (tmp_path / "e.yaml").read_text(encoding="utf-8")
    devices = {d["name"]: d for d in yaml.safe_load(text)["unassigned"]["devices"]}
    assert devices["WC"]["via"] == "ZBBridge-U"
    assert "via" not in devices["Prise"] and "via" not in devices["ZBBridge-U"]
    assert '"via" = passerelle' in text


async def test_config_flow_checks_folder(hass: HomeAssistant, tmp_path: Path) -> None:
    async def submit(path: str) -> dict:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_OUTPUT_PATH: path}
        )

    # /share absent (installation sans Supervisor) : refusé, jamais créé
    missing = tmp_path / "share" / "entity_inventory.yaml"
    result = await submit(str(missing))
    assert result["errors"] == {CONF_OUTPUT_PATH: "dir_missing"}
    assert not missing.parent.exists()

    result = await submit(str(tmp_path))
    assert result["errors"] == {CONF_OUTPUT_PATH: "is_dir"}

    # Sous /config, un sous-dossier manquant reste accepté (il sera créé)
    result = await submit("ia/entity_inventory.yaml")
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_export_failure_alerts_once(hass: HomeAssistant, tmp_path: Path) -> None:
    sent = []
    hass.services.async_register("notify", "send_message", lambda call: sent.append(call.data))
    hass.states.async_set("notify.iphone", "unknown")
    target = tmp_path / "share" / "e.yaml"
    entry = await _setup(hass, str(target), notify_entity="notify.iphone")
    notif_id = f"{DOMAIN}_export_{entry.entry_id}"

    # Dossier absent : signalé dès le démarrage, sans attendre un export
    await hass.async_start()
    await hass.async_block_till_done()
    assert notif_id in _notifications(hass)
    assert "n'existe pas" in _notifications(hass)[notif_id]["message"] or "does not exist" in (
        _notifications(hass)[notif_id]["message"]
    )
    assert len(sent) == 1

    # Exports ratés (ex. automatisation nocturne) : erreur, mais pas de nouvelle alerte
    for _ in range(2):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(DOMAIN, "export", {}, blocking=True)
    await hass.async_block_till_done()
    assert len(sent) == 1

    # Dossier rétabli : export réussi, alerte retirée
    target.parent.mkdir()
    await hass.services.async_call(DOMAIN, "export", {}, blocking=True)
    await hass.async_block_till_done()
    assert target.exists()
    assert notif_id not in _notifications(hass)
    assert not hass.config_entries.async_get_entry(entry.entry_id).data.get("alerted")


async def test_button_failure_raises(hass: HomeAssistant, tmp_path: Path) -> None:
    entry = await _setup(hass, str(tmp_path / "absent" / "e.yaml"))
    button = next(
        e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "button"  # 0.9.0 : l'entrée a aussi un capteur « Téléphone admin »
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert f"{DOMAIN}_export_{entry.entry_id}" in _notifications(hass)
