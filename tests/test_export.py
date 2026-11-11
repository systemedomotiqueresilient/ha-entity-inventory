"""Tests d'Entity Inventory sur une instance HA de test."""

from pathlib import Path

import pytest
import yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
    label_registry as lr,
)
from homeassistant.setup import async_setup_component

from custom_components.entity_inventory.const import CONF_OUTPUT_PATH, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _populate(hass: HomeAssistant) -> None:
    floor = fr.async_get(hass).async_create("Rez-de-chaussée", level=0)
    fr.async_get(hass).async_create("Étage", level=1)
    salon = ar.async_get(hass).async_create("Salon", floor_id=floor.floor_id, aliases={"séjour"})
    cuisine = ar.async_get(hass).async_create("Cuisine", floor_id=floor.floor_id)
    label = lr.async_get(hass).async_create("Chauffage")

    src = MockConfigEntry(domain="zha")
    src.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)

    radiateur = dev_reg.async_get_or_create(
        config_entry_id=src.entry_id,
        identifiers={("zha", "rad1")},
        name="SIN-4-FP-21",
        manufacturer="NodOn",
        model="SIN-4-FP-21",
    )
    dev_reg.async_update_device(radiateur.id, name_by_user="Radiateur salon", area_id=salon.id)

    clim = ent_reg.async_get_or_create(
        "climate", "zha", "rad1-climate", device_id=radiateur.id,
        original_name=None, has_entity_name=True,
        capabilities={"hvac_modes": ["heat", "off"], "preset_modes": ["comfort", "eco", "away", "none"],
                      "min_temp": 7, "max_temp": 30},
    )
    ent_reg.async_update_entity(clim.entity_id, labels={label.label_id})
    hass.states.async_set(clim.entity_id, "heat", {"friendly_name": "Radiateur salon",
                                                   "current_temperature": 19.5, "preset_mode": "eco"})

    batt = ent_reg.async_get_or_create(
        "sensor", "zha", "rad1-batt", device_id=radiateur.id, original_name="Batterie",
        has_entity_name=True, original_device_class="battery", unit_of_measurement="%",
        entity_category=er.EntityCategory.DIAGNOSTIC, capabilities={"state_class": "measurement"},
    )
    hass.states.async_set(batt.entity_id, "87", {"unit_of_measurement": "%"})

    # entité de l'appareil placée dans une autre pièce
    temp = ent_reg.async_get_or_create(
        "sensor", "zha", "rad1-temp", device_id=radiateur.id, original_name="Température",
        has_entity_name=True, original_device_class="temperature", unit_of_measurement="°C",
    )
    ent_reg.async_update_entity(temp.entity_id, area_id=cuisine.id)

    # entité désactivée
    off = ent_reg.async_get_or_create("sensor", "zha", "rad1-lqi", device_id=radiateur.id,
                                      original_name="LQI", has_entity_name=True)
    ent_reg.async_update_entity(off.entity_id, disabled_by=er.RegistryEntryDisabler.USER)

    # traqueur GPS : les coordonnées ne doivent JAMAIS sortir
    gps = ent_reg.async_get_or_create("device_tracker", "mobile_app", "phone", original_name="Téléphone")
    hass.states.async_set(gps.entity_id, "home", {"latitude": 12.3456, "longitude": -65.4321,
                                                  "ip": "192.168.0.42"})

    # helper sans appareil, dans une pièce
    sel = ent_reg.async_get_or_create("select", "template", "mode", original_name="Mode maison")
    ent_reg.async_update_entity(sel.entity_id, area_id=salon.id)
    hass.states.async_set(sel.entity_id, "Absent", {"options": ["Présent", "Absent", "Vacances"]})

    # entité YAML sans unique_id (hors registre)
    hass.states.async_set("sensor.legacy_template", "12", {"friendly_name": "Vieux template",
                                                          "unit_of_measurement": "kWh"})


async def _setup(hass: HomeAssistant, path: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_OUTPUT_PATH: path})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_export_service(hass: HomeAssistant, tmp_path: Path) -> None:
    await _populate(hass)
    out = tmp_path / "sub" / "inventory.yaml"
    await _setup(hass, str(out))

    resp = await hass.services.async_call(DOMAIN, "export", {}, blocking=True, return_response=True)
    assert resp["path"] == str(out)

    text = out.read_text(encoding="utf-8")
    print(text)
    data = yaml.safe_load(text)

    # aucune donnée d'état ne fuit
    for leak in ("12.3456", "192.168.0.42", "19.5", "current_temperature", "preset_mode:", "Absent\n"):
        assert leak not in text, leak

    salon = next(v for v in data["areas"].values() if v["name"] == "Salon")
    assert salon["aliases"] == ["séjour"]
    rad = salon["devices"][0]
    assert rad["name"] == "Radiateur salon" and rad["integration"] == "zha"
    ents = {e["name"]: e for e in rad["entities"]}
    assert ents["Radiateur salon"]["id"].startswith("climate.")
    assert ents["Radiateur salon"]["preset_modes"] == ["comfort", "eco", "away", "none"]
    assert ents["Radiateur salon"]["labels"] == ["chauffage"]
    assert ents["Radiateur salon Batterie"]["category"] == "diagnostic"
    assert ents["Radiateur salon Température"]["area"] == "cuisine"
    assert ents["Radiateur salon Température"]["unit"] == "°C"
    assert salon["entities"][0]["options"] == ["Présent", "Absent", "Vacances"]
    assert len(data["disabled"]) == 1
    assert {e["id"] for e in data["no_registry"]} >= {"sensor.legacy_template"}
    assert data["unassigned"]["entities"][0]["id"].startswith("device_tracker.")
    assert data["unassigned"]["devices"][0]["name"] == "Entity Inventory"


async def test_button_press(hass: HomeAssistant, tmp_path: Path) -> None:
    out = tmp_path / "inv.yaml"
    await _setup(hass, str(out))
    button = next(s.entity_id for s in hass.states.async_all("button"))
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert out.exists()
    assert hass.states.get(button).state not in ("unknown", "unavailable")


async def test_config_flow_rejects_www(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_OUTPUT_PATH: "www/inv.yaml"})
    assert result["errors"] == {CONF_OUTPUT_PATH: "forbidden_www"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_OUTPUT_PATH: "inv.yaml"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_OUTPUT_PATH: "inv.yaml"}


async def test_options_flow(hass: HomeAssistant, tmp_path: Path) -> None:
    entry = await _setup(hass, str(tmp_path / "a.yaml"))
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_OUTPUT_PATH: "www"})
    assert result["errors"] == {CONF_OUTPUT_PATH: "forbidden_www"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_OUTPUT_PATH: "/share/b.yaml"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_OUTPUT_PATH] == "/share/b.yaml"
