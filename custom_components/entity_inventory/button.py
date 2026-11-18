"""Boutons d'export : un pour tout le logement, un par pièce (option).

Chaque bouton de pièce est rangé dans sa pièce : les tableaux de bord automatiques et
celui des pièces l'affichent au bon endroit, sans carte à installer ni YAML à copier.
Les boutons suivent les pièces (création, renommage, suppression).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_AREA_BUTTONS, DEFAULT_AREA_BUTTONS, DOMAIN
from .runner import async_run_export

AREA_UID = "{entry_id}_export_area_{area_id}"
DATA_PLACED = "area_buttons_placed"  # pièces dont le bouton a déjà été rangé


def _device(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Entity Inventory",
        entry_type=DeviceEntryType.SERVICE,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ExportInventoryButton(entry)])

    area_reg = ar.async_get(hass)
    ent_reg = er.async_get(hass)
    enabled = entry.options.get(CONF_AREA_BUTTONS, DEFAULT_AREA_BUTTONS)
    buttons: dict[str, AreaExportButton] = {}
    prefix = AREA_UID.format(entry_id=entry.entry_id, area_id="")

    @callback
    def _forget(*area_ids: str) -> None:
        placed = set(entry.data.get(DATA_PLACED) or ())
        if placed & set(area_ids):
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, DATA_PLACED: sorted(placed - set(area_ids))}
            )

    # Nettoyage : pièces supprimées pendant l'arrêt, ou option désactivée
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if reg_entry.unique_id.startswith(prefix):
            area_id = reg_entry.unique_id.removeprefix(prefix)
            if not enabled or area_reg.async_get_area(area_id) is None:
                ent_reg.async_remove(reg_entry.entity_id)
                _forget(area_id)

    if not enabled:
        _forget(*(entry.data.get(DATA_PLACED) or ()))
        return

    def _add(area: ar.AreaEntry) -> None:
        button = AreaExportButton(entry, area)
        buttons[area.id] = button
        async_add_entities([button])

    for area in area_reg.async_list_areas():
        _add(area)

    @callback
    def _area_changed(event: Event[ar.EventAreaRegistryUpdatedData]) -> None:
        area_id = event.data["area_id"]
        action = event.data["action"]
        if action == "create" and area_id and (area := area_reg.async_get_area(area_id)):
            _add(area)
        elif action == "remove" and area_id in buttons:
            button = buttons.pop(area_id)
            if button.entity_id and ent_reg.async_get(button.entity_id):
                ent_reg.async_remove(button.entity_id)
            _forget(area_id)
        elif action == "update" and area_id in buttons and (area := area_reg.async_get_area(area_id)):
            buttons[area_id].async_rename(area.name)

    entry.async_on_unload(hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, _area_changed))


class ExportInventoryButton(ButtonEntity):
    """Export complet ; son état = date du dernier export."""

    _attr_has_entity_name = True
    _attr_translation_key = "export"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_export"
        self._attr_device_info = _device(entry)

    async def async_press(self) -> None:
        await async_run_export(self.hass, self._entry)


class AreaExportButton(ButtonEntity):
    """Export ciblé sur une pièce, rangé dans cette pièce."""

    _attr_has_entity_name = True
    _attr_translation_key = "export_area"

    def __init__(self, entry: ConfigEntry, area: ar.AreaEntry) -> None:
        self._entry = entry
        self._area_id = area.id
        self._attr_unique_id = AREA_UID.format(entry_id=entry.entry_id, area_id=area.id)
        self._attr_translation_placeholders = {"area": area.name}
        self._attr_device_info = _device(entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"area_id": self._area_id}

    async def async_added_to_hass(self) -> None:
        """Ranger le bouton dans sa pièce, une seule fois : un déplacement manuel est respecté."""
        placed = set(self._entry.data.get(DATA_PLACED) or ())
        if self._area_id in placed:
            return
        reg = er.async_get(self.hass)
        if (reg_entry := reg.async_get(self.entity_id)) and reg_entry.area_id is None:
            reg.async_update_entity(self.entity_id, area_id=self._area_id)
        self.hass.config_entries.async_update_entry(
            self._entry, data={**self._entry.data, DATA_PLACED: sorted(placed | {self._area_id})}
        )

    @callback
    def async_rename(self, name: str) -> None:
        self._attr_translation_placeholders = {"area": name}
        try:  # le nom traduit est mis en cache par Home Assistant : l'invalider
            del self.name
        except AttributeError:
            pass
        if self.hass:
            self.async_write_ha_state()

    async def async_press(self) -> None:
        await async_run_export(self.hass, self._entry, {"areas": [self._area_id]})
