"""Réparations proposées par Entity Inventory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

from .watchman import async_add_exception


class WatchmanExceptionFlow(RepairsFlow):
    """Ajoute l'export aux fichiers ignorés de Watchman, après confirmation."""

    def __init__(self, entry_id: str, path: str) -> None:
        self._entry_id = entry_id
        self._path = path

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is None:
                return self.async_abort(reason="entry_missing")
            if not async_add_exception(self.hass, entry, Path(self._path)):
                return self.async_abort(reason="unsupported")
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"path": self._path},
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    data = data or {}
    return WatchmanExceptionFlow(str(data.get("entry_id")), str(data.get("path")))
