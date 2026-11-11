"""Tests d'Entity Inventory sur une instance HA de test."""

from enum import Enum
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

from custom_components.entity_inventory.const import (
    CONF_EXCLUDED_INTEGRATIONS,
    CONF_INCLUDE_CONFIG,
    CONF_INCLUDE_DIAGNOSTIC,
    CONF_OUTPUT_PATH,
    DOMAIN,
)
from custom_components.entity_inventory.exporter import _aliases, _short_name


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _populate(hass: HomeAssistant) -> None:
    floor = fr.async_get(hass).async_create("Rez-de-chaussée", level=0)
    fr.async_get(hass).async_create("Étage", level=1)
    salon = ar.async_get(hass).async_create("Salon", floor_id=floor.floor_id, aliases={"séjour"})
    cuisine = ar.async_get(hass).async_create("Cuisine", floor_id=floor.floor_id)
    label = lr.async_get(hass).async_create("Chauffage")

    zha = MockConfigEntry(domain="zha")
    zha.add_to_hass(hass)
    pve = MockConfigEntry(domain="proxmoxve")
    pve.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)

    radiateur = dev_reg.async_get_or_create(
        config_entry_id=zha.entry_id,
        identifiers={("zha", "rad1")},
        name="SIN-4-FP-21",
        manufacturer="NodOn",
        model="SIN-4-FP-21",
    )
    dev_reg.async_update_device(radiateur.id, name_by_user="Radiateur salon", area_id=salon.id)

    def ent(domain, uid, **kw):
        return ent_reg.async_get_or_create(
            domain, "zha", uid, device_id=radiateur.id, has_entity_name=True, **kw
        )

    clim = ent("climate", "rad1-climate", original_name=None,
               capabilities={"hvac_modes": ["heat", "off"],
                             "preset_modes": ["comfort", "eco", "away", "none"],
                             "min_temp": 7, "max_temp": 30})
    ent_reg.async_update_entity(clim.entity_id, labels={label.label_id})
    hass.states.async_set(clim.entity_id, "heat", {"friendly_name": "Radiateur salon",
                                                   "current_temperature": 19.5, "preset_mode": "eco"})

    ent("sensor", "rad1-batt", original_name="Batterie", original_device_class="battery",
        unit_of_measurement="%", entity_category=er.EntityCategory.DIAGNOSTIC)
    ent("sensor", "rad1-lqi", original_name="LQI", entity_category=er.EntityCategory.DIAGNOSTIC)
    ent("select", "rad1-led", original_name="Mode LED", entity_category=er.EntityCategory.CONFIG,
        capabilities={"options": ["on", "off"]})
    temp = ent("sensor", "rad1-temp", original_name="Température",
               original_device_class="temperature", unit_of_measurement="°C")
    ent_reg.async_update_entity(temp.entity_id, area_id=cuisine.id)
    off = ent("sensor", "rad1-rssi", original_name="RSSI")
    ent_reg.async_update_entity(off.entity_id, disabled_by=er.RegistryEntryDisabler.USER)

    # Proxmox : un nœud et son CPU
    node = dev_reg.async_get_or_create(config_entry_id=pve.entry_id,
                                       identifiers={("proxmoxve", "pve0")}, name="PVE0")
    ent_reg.async_get_or_create("sensor", "proxmoxve", "pve0-cpu", device_id=node.id,
                                has_entity_name=True, original_name="CPU", unit_of_measurement="%")

    # traqueur GPS : les coordonnées ne doivent JAMAIS sortir
    gps = ent_reg.async_get_or_create("device_tracker", "mobile_app", "phone", original_name="Téléphone")
    hass.states.async_set(gps.entity_id, "home", {"latitude": 12.3456, "longitude": -65.4321,
                                                  "ip": "192.168.0.42"})

    sel = ent_reg.async_get_or_create("select", "template", "mode", original_name="Mode maison")
    ent_reg.async_update_entity(sel.entity_id, area_id=salon.id)
    hass.states.async_set(sel.entity_id, "Absent", {"options": ["Présent", "Absent", "Vacances"]})

    hass.states.async_set("sensor.legacy_template", "12", {"friendly_name": "Vieux template",
                                                          "unit_of_measurement": "kWh"})


async def _setup(hass: HomeAssistant, path: str, **options) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_OUTPUT_PATH: path, **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _export(hass: HomeAssistant) -> tuple[dict, str, dict]:
    resp = await hass.services.async_call(DOMAIN, "export", {}, blocking=True, return_response=True)
    text = Path(resp["path"]).read_text(encoding="utf-8")
    return yaml.safe_load(text), text, resp


def _radiateur(data: dict) -> dict:
    salon = next(v for v in data["areas"].values() if v["name"] == "Salon")
    return {e.get("name", "<device>"): e for e in salon["devices"][0]["entities"]}


async def test_export_defaults(hass: HomeAssistant, tmp_path: Path) -> None:
    await _populate(hass)
    await _setup(hass, str(tmp_path / "sub" / "inventory.yaml"))
    data, text, resp = await _export(hass)
    print(text)

    for leak in ("12.3456", "192.168.0.42", "19.5", "current_temperature", "preset_mode:", "Absent\n"):
        assert leak not in text, leak

    ents = _radiateur(data)
    # nom court : l'entité principale n'a pas de name, les autres seulement le suffixe
    assert ents["<device>"]["preset_modes"] == ["comfort", "eco", "away", "none"]
    assert ents["<device>"]["labels"] == ["chauffage"]
    assert ents["Température"]["area"] == "cuisine"
    # filtres par défaut : batterie gardée, LQI (diagnostic) et LED (config) exclus
    assert ents["Batterie"]["category"] == "diagnostic"
    assert "LQI" not in ents and "Mode LED" not in ents
    assert data["meta"]["counts"]["excluded"] == {"config": 1, "diagnostic": 1, "integrations": 0}
    assert data["meta"]["counts"]["disabled"] == 1
    assert "disabled" not in data
    assert data["meta"]["filters"]["config_entities"] == "excluded"
    assert resp["size_bytes"] == len(text.encode())
    # pas d'alias parasites
    assert "aliases: [0]" not in text


async def test_export_all_and_exclusions(hass: HomeAssistant, tmp_path: Path) -> None:
    await _populate(hass)
    await _setup(hass, str(tmp_path / "inv.yaml"), **{
        CONF_INCLUDE_CONFIG: True,
        CONF_INCLUDE_DIAGNOSTIC: True,
        CONF_EXCLUDED_INTEGRATIONS: ["proxmoxve"],
    })
    data, text, _ = await _export(hass)
    ents = _radiateur(data)
    assert ents["Mode LED"]["options"] == ["on", "off"] and "LQI" in ents
    assert "PVE0" not in text and "proxmoxve" in data["meta"]["filters"]["excluded_integrations"]
    assert data["meta"]["counts"]["excluded"]["integrations"] == 1


def test_helpers() -> None:
    class Sentinel(Enum):
        COMPUTED_NAME = 0

    assert _aliases({"Kodi", Sentinel.COMPUTED_NAME, "", None}) == ["Kodi"]
    assert _short_name("Chambre parents Humidité", "Chambre parents") == "Humidité"
    assert _short_name("Chambre parents", "Chambre parents") is None
    assert _short_name("Chambre parentsxx", "Chambre parents") == "Chambre parentsxx"


async def test_button_press(hass: HomeAssistant, tmp_path: Path) -> None:
    out = tmp_path / "inv.yaml"
    await _setup(hass, str(out))
    button = next(s.entity_id for s in hass.states.async_all("button"))
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert out.exists()
    assert hass.states.get(button).state not in ("unknown", "unavailable")


async def test_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_OUTPUT_PATH: "www/inv.yaml"})
    assert result["errors"] == {CONF_OUTPUT_PATH: "forbidden_www"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_OUTPUT_PATH: " inv.yaml ", CONF_EXCLUDED_INTEGRATIONS: ["sentinel", " "]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {
        CONF_OUTPUT_PATH: "inv.yaml",
        CONF_INCLUDE_CONFIG: False,
        CONF_INCLUDE_DIAGNOSTIC: False,
        CONF_EXCLUDED_INTEGRATIONS: ["sentinel"],
    }


async def test_options_flow(hass: HomeAssistant, tmp_path: Path) -> None:
    # ancienne configuration 0.1.0 : seulement le chemin
    entry = await _setup(hass, str(tmp_path / "a.yaml"))
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_OUTPUT_PATH: "www"})
    assert result["errors"] == {CONF_OUTPUT_PATH: "forbidden_www"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_OUTPUT_PATH: "/share/b.yaml", CONF_INCLUDE_DIAGNOSTIC: True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_OUTPUT_PATH] == "/share/b.yaml"
    assert entry.options[CONF_INCLUDE_DIAGNOSTIC] is True
