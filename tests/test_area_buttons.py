"""0.8.0 : un bouton d'export par pièce, qui suit les pièces."""

from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er

from custom_components.entity_inventory.const import CONF_AREA_BUTTONS, CONF_OUTPUT_PATH, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _setup(hass: HomeAssistant, tmp_path: Path, **options) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_OUTPUT_PATH: str(tmp_path / "entity_inventory.yaml"), **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _area_buttons(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, er.RegistryEntry]:
    reg = er.async_get(hass)
    return {
        e.unique_id.rsplit("_export_area_", 1)[1]: e
        for e in er.async_entries_for_config_entry(reg, entry.entry_id)
        if "_export_area_" in e.unique_id
    }


async def test_one_button_per_area(hass: HomeAssistant, tmp_path: Path) -> None:
    areas = ar.async_get(hass)
    sdb = areas.async_create("Salle de bain")
    areas.async_create("WC")
    entry = await _setup(hass, tmp_path)

    buttons = _area_buttons(hass, entry)
    assert set(buttons) == {"salle_de_bain", "wc"}
    assert buttons["salle_de_bain"].area_id == "salle_de_bain"  # rangé dans sa pièce
    state = hass.states.get(buttons["salle_de_bain"].entity_id)
    assert "Salle de bain" in state.attributes["friendly_name"]

    await hass.services.async_call("button", "press", {"entity_id": buttons["salle_de_bain"].entity_id}, blocking=True)
    assert (tmp_path / "entity_inventory_salle_de_bain.yaml").exists()
    assert not (tmp_path / "entity_inventory.yaml").exists()

    # Une pièce créée → un bouton ; renommée → nom suivi ; supprimée → bouton retiré
    areas.async_create("Couloir")
    await hass.async_block_till_done()
    assert "couloir" in _area_buttons(hass, entry)

    areas.async_update(sdb.id, name="Salle d'eau")
    await hass.async_block_till_done()
    assert "Salle d'eau" in hass.states.get(buttons["salle_de_bain"].entity_id).attributes["friendly_name"]

    areas.async_delete("wc")
    await hass.async_block_till_done()
    assert "wc" not in _area_buttons(hass, entry)


async def test_manual_move_respected(hass: HomeAssistant, tmp_path: Path) -> None:
    areas = ar.async_get(hass)
    areas.async_create("Cuisine")
    areas.async_create("Entrée")
    entry = await _setup(hass, tmp_path)
    button = _area_buttons(hass, entry)["cuisine"]
    er.async_get(hass).async_update_entity(button.entity_id, area_id="entree")

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _area_buttons(hass, entry)["cuisine"].area_id == "entree"  # pas remis de force


async def test_option_off_removes_buttons(hass: HomeAssistant, tmp_path: Path) -> None:
    ar.async_get(hass).async_create("Salon")
    entry = await _setup(hass, tmp_path)
    assert _area_buttons(hass, entry)

    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_AREA_BUTTONS: False})
    await hass.async_block_till_done()
    assert not _area_buttons(hass, entry)
    # le bouton global reste
    assert any(e.unique_id.endswith("_export") for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id))
