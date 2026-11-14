"""Bouton « Exporter l'inventaire »."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .runner import async_run_export


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ExportInventoryButton(entry)])


class ExportInventoryButton(ButtonEntity):
    """Déclenche un export ; son état = date du dernier export."""

    _attr_has_entity_name = True
    _attr_translation_key = "export"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_export"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Entity Inventory",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        await async_run_export(self.hass, self._entry)
