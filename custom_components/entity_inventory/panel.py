"""Panneau latéral (0.10.0) : générer, télécharger et copier l'inventaire.

Pour tout le monde, y compris sans Samba : le fichier se télécharge depuis le
navigateur (ou l'application Companion) et se copie dans le presse-papiers.

Sécurité :
- panneau enregistré avec require_admin, commandes WebSocket require_admin ;
- téléchargement par une adresse SIGNÉE (async_sign_path), valable quelques
  minutes et liée à la session de l'administrateur ; la vue vérifie encore que
  l'utilisateur est administrateur ;
- seuls les fichiers produits par Entity Inventory sont servis :
  <nom de l'export>[_cible].yaml, dans le dossier de l'export, sans lien
  symbolique ni sous-dossier.
"""

from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus
import logging
from pathlib import Path
import re
from typing import Any

from aiohttp import web
from homeassistant.components import frontend as ha_frontend, panel_custom, websocket_api
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    entity_registry as er,
    floor_registry as fr,
    label_registry as lr,
)
import voluptuous as vol

from .const import DOMAIN, VERSION
from .exporter import resolve_output_path
from .runner import async_run_export

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "entity-inventory"
PANEL_ELEMENT = "entity-inventory-panel"
FRONTEND_URL = "/entity_inventory_static"
DOWNLOAD_URL = "/api/entity_inventory/download"
LINK_LIFETIME = timedelta(minutes=5)
_SCOPE_KEYS = ("areas", "floors", "labels", "domains")


def _entry(hass: HomeAssistant) -> ConfigEntry | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry
    return None


def export_files(main: Path) -> list[Path]:
    """Fichiers d'export présents : le principal et les exports ciblés (executor)."""
    folder = main.parent
    if not folder.is_dir():
        return []
    pattern = re.compile(rf"^{re.escape(main.stem)}(_[a-z0-9_]+)?{re.escape(main.suffix)}$")
    return sorted(
        path
        for path in folder.iterdir()
        if pattern.match(path.name) and path.is_file() and not path.is_symlink()
    )


def _describe(files: list[Path]) -> list[dict[str, Any]]:
    result = []
    for path in files:
        stat = path.stat()
        result.append({"name": path.name, "size": stat.st_size, "modified": stat.st_mtime})
    return result


@callback
def _signed(hass: HomeAssistant, connection: websocket_api.ActiveConnection, name: str) -> str:
    return async_sign_path(
        hass,
        f"{DOWNLOAD_URL}/{name}",
        LINK_LIFETIME,
        refresh_token_id=connection.refresh_token_id,
    )


@callback
def _choices(hass: HomeAssistant) -> dict[str, list[dict[str, str]]]:
    """Cibles possibles pour un export ciblé : id technique et nom lisible."""
    domains = sorted({entry.domain for entry in er.async_get(hass).entities.values()})
    return {
        "floors": sorted(
            ({"id": f.floor_id, "name": f.name} for f in fr.async_get(hass).async_list_floors()),
            key=lambda item: item["name"].lower(),
        ),
        "areas": sorted(
            ({"id": a.id, "name": a.name} for a in ar.async_get(hass).async_list_areas()),
            key=lambda item: item["name"].lower(),
        ),
        "labels": sorted(
            (
                {"id": lab.label_id, "name": lab.name}
                for lab in lr.async_get(hass).async_list_labels()
            ),
            key=lambda item: item["name"].lower(),
        ),
        "domains": [{"id": d, "name": d} for d in domains],
    }


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/overview"})
@websocket_api.async_response
async def ws_overview(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Entity Inventory n'est pas chargé")
        return
    main = resolve_output_path(hass, entry)
    files = await hass.async_add_executor_job(lambda: _describe(export_files(main)))
    for item in files:
        item["url"] = _signed(hass, connection, item["name"])
    connection.send_result(
        msg["id"],
        {
            "version": VERSION,
            "output_path": str(main),
            "files": files,
            "choices": _choices(hass),
            "package_keeper": "package_keeper" in hass.config.components,
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/generate",
        **{vol.Optional(key): [str] for key in _SCOPE_KEYS},
    }
)
@websocket_api.async_response
async def ws_generate(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    # Import ici : évite une boucle d'import avec __init__ (qui enregistre ce module)
    from . import _check_scope

    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Entity Inventory n'est pas chargé")
        return
    scope = {key: msg[key] for key in _SCOPE_KEYS if msg.get(key)}
    try:
        _check_scope(hass, scope)
        result = await async_run_export(hass, entry, scope or None)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "export_failed", str(err))
        return
    name = Path(result["path"]).name
    connection.send_result(
        msg["id"], {**result, "name": name, "url": _signed(hass, connection, name)}
    )


class DownloadView(HomeAssistantView):
    """Sert un fichier d'export, aux administrateurs, par une adresse signée."""

    url = DOWNLOAD_URL + "/{name}"
    name = f"api:{DOMAIN}:download"
    requires_auth = True

    async def get(self, request: web.Request, name: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.Response(status=HTTPStatus.FORBIDDEN)
        entry = _entry(hass)
        if entry is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        main = resolve_output_path(hass, entry)
        files = await hass.async_add_executor_job(export_files, main)
        path = next((p for p in files if p.name == name), None)
        if path is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        return web.FileResponse(
            path,
            headers={
                "Content-Type": "text/yaml; charset=utf-8",
                "Content-Disposition": f'attachment; filename="{path.name}"',
                "Cache-Control": "no-store",
            },
        )


@callback
def async_register_api(hass: HomeAssistant) -> None:
    """Commandes WebSocket et vue de téléchargement (une seule fois)."""
    websocket_api.async_register_command(hass, ws_overview)
    websocket_api.async_register_command(hass, ws_generate)
    hass.http.register_view(DownloadView())


async def async_register_panel(hass: HomeAssistant) -> None:
    """Panneau latéral réservé aux administrateurs."""
    if "frontend" not in hass.config.components:
        _LOGGER.info("Interface web absente : panneau Entity Inventory non ajouté")
        return
    if not hass.data.get(f"{DOMAIN}_static"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, str(Path(__file__).parent / "frontend"), False)]
        )
        hass.data[f"{DOMAIN}_static"] = True
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="Entity Inventory",
        sidebar_icon="mdi:clipboard-list-outline",
        module_url=f"{FRONTEND_URL}/entity-inventory-panel.js?v={VERSION}",
        require_admin=True,
        config={},
    )


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    if "frontend" in hass.config.components:
        ha_frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
