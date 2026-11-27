"""0.10.0 : panneau latéral (générer, télécharger, copier), réservé aux administrateurs."""

from __future__ import annotations

from pathlib import Path
import re
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.setup import async_setup_component

from custom_components.entity_inventory import panel
from custom_components.entity_inventory.const import CONF_OUTPUT_PATH, DOMAIN, VERSION


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _setup(hass: HomeAssistant, tmp_path: Path) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, options={CONF_OUTPUT_PATH: str(tmp_path / "entity_inventory.yaml")}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_generate_download_and_list(
    hass: HomeAssistant, tmp_path: Path, hass_ws_client, hass_client
) -> None:
    ar.async_get(hass).async_create("Salon")
    await _setup(hass, tmp_path)
    ws = await hass_ws_client(hass)

    await ws.send_json_auto_id({"type": f"{DOMAIN}/overview"})
    reply = await ws.receive_json()
    assert reply["success"], reply
    overview = reply["result"]
    assert overview["version"] == VERSION and overview["files"] == []
    assert [a["name"] for a in overview["choices"]["areas"]] == ["Salon"]

    await ws.send_json_auto_id({"type": f"{DOMAIN}/generate"})
    result = (await ws.receive_json())["result"]
    assert result["name"] == "entity_inventory.yaml" and result["size_bytes"] > 0
    assert result["broken_packages"] == {}
    assert "authSig=" in result["url"]

    salon = overview["choices"]["areas"][0]["id"]
    await ws.send_json_auto_id({"type": f"{DOMAIN}/generate", "areas": [salon]})
    scoped = (await ws.receive_json())["result"]
    assert scoped["name"] == f"entity_inventory_{salon}.yaml"

    await ws.send_json_auto_id({"type": f"{DOMAIN}/generate", "areas": ["inconnue"]})
    reply = await ws.receive_json()
    assert not reply["success"] and reply["error"]["code"] == "export_failed"

    await ws.send_json_auto_id({"type": f"{DOMAIN}/overview"})
    files = (await ws.receive_json())["result"]["files"]
    assert [f["name"] for f in files] == ["entity_inventory.yaml", f"entity_inventory_{salon}.yaml"]

    client = await hass_client()
    response = await client.get(result["url"])
    assert response.status == 200
    assert "attachment" in response.headers["Content-Disposition"]
    text = await response.text()
    assert text == (tmp_path / "entity_inventory.yaml").read_text(encoding="utf-8")


async def test_only_export_files_are_served(
    hass: HomeAssistant, tmp_path: Path, hass_client
) -> None:
    await _setup(hass, tmp_path)
    (tmp_path / "secrets.yaml").write_text("mot_de_passe: x\n", encoding="utf-8")
    (tmp_path / "entity_inventory.yaml").write_text("a: 1\n", encoding="utf-8")
    (tmp_path / "entity_inventory_lien.yaml").symlink_to(tmp_path / "secrets.yaml")
    client = await hass_client()
    for name in (
        "secrets.yaml",
        "entity_inventory_lien.yaml",
        "..%2Fsecrets.yaml",
        "entity_inventory.yaml.bak",
    ):
        response = await client.get(f"{panel.DOWNLOAD_URL}/{name}")
        assert response.status in (400, 404), name  # refusé (HA filtre déjà ..)
    assert (await client.get(f"{panel.DOWNLOAD_URL}/entity_inventory.yaml")).status == 200


async def test_non_admin_refused(
    hass: HomeAssistant,
    tmp_path: Path,
    hass_ws_client,
    hass_client,
    hass_read_only_access_token: str,
) -> None:
    await _setup(hass, tmp_path)
    (tmp_path / "entity_inventory.yaml").write_text("a: 1\n", encoding="utf-8")
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    for kind in ("overview", "generate"):
        await ws.send_json_auto_id({"type": f"{DOMAIN}/{kind}"})
        reply = await ws.receive_json()
        assert not reply["success"] and reply["error"]["code"] == "unauthorized"
    client = await hass_client(hass_read_only_access_token)
    response = await client.get(f"{panel.DOWNLOAD_URL}/entity_inventory.yaml")
    assert response.status == 403


async def test_panel_registered_admin_only(hass: HomeAssistant, tmp_path: Path) -> None:
    hass.config.components.add("frontend")
    assert await async_setup_component(hass, "http", {})
    with (
        patch.object(panel.panel_custom, "async_register_panel", AsyncMock()) as register,
        patch.object(hass.http, "async_register_static_paths", AsyncMock()) as static,
        patch.object(panel.ha_frontend, "async_remove_panel") as remove,
    ):
        entry = await _setup(hass, tmp_path)
        assert await hass.config_entries.async_unload(entry.entry_id)
    kwargs = register.call_args.kwargs
    assert kwargs["require_admin"] is True
    assert kwargs["frontend_url_path"] == panel.PANEL_URL_PATH
    assert kwargs["module_url"].endswith(f"?v={VERSION}")
    assert static.call_count == 1 and remove.called


def test_panel_version_matches() -> None:
    js = (
        Path(__file__).parents[1]
        / "custom_components"
        / DOMAIN
        / "frontend"
        / "entity-inventory-panel.js"
    ).read_text(encoding="utf-8")
    assert re.search(r'const PANEL_VERSION = "([^"]+)";', js).group(1) == VERSION
    assert 'innerHTML = ""' in js and "innerHTML = `" not in js  # jamais de HTML venant du serveur
