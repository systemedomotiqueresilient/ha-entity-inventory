"""Cohabitation avec Watchman : réparation, correction, changement de chemin."""

from pathlib import Path
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.entity_inventory.const import CONF_OUTPUT_PATH, DOMAIN
from custom_components.entity_inventory.repairs import async_create_fix_flow


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _watchman(hass: HomeAssistant, **kwargs) -> MockConfigEntry:
    entry = MockConfigEntry(domain="watchman", **kwargs)
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, path: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_OUTPUT_PATH: path})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _issue(hass: HomeAssistant, entry: MockConfigEntry):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"watchman_scans_export_{entry.entry_id}")


async def _fix(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    issue = _issue(hass, entry)
    flow = await async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass = hass
    form = await flow.async_step_init()
    assert form["step_id"] == "confirm"
    result = await flow.async_step_confirm({})
    await hass.async_block_till_done()
    return result


async def test_issue_fix_and_path_change(hass: HomeAssistant) -> None:
    watchman = _watchman(hass, data={"ignored_files": ["*/secrets.yaml"]})
    entry = await _setup(hass, "entity_inventory.yaml")
    export = str(Path(hass.config.path("entity_inventory*.yaml")))  # couvre aussi les exports ciblés

    issue = _issue(hass, entry)
    assert issue is not None and issue.is_fixable
    assert issue.translation_placeholders == {"path": export}

    assert (await _fix(hass, entry))["type"] == "create_entry"
    assert watchman.data["ignored_files"] == ["*/secrets.yaml", export]
    assert _issue(hass, entry) is None

    # Changement de chemin ultérieur : réparation proposée à nouveau, ancien motif remplacé
    entry = hass.config_entries.async_get_entry(entry.entry_id)
    hass.config_entries.async_update_entry(entry, options={CONF_OUTPUT_PATH: "ia/export.yaml"})
    await hass.async_block_till_done()
    assert _issue(hass, entry) is not None
    await _fix(hass, entry)
    new_export = str(Path(hass.config.path("ia/export*.yaml")))
    assert watchman.data["ignored_files"] == ["*/secrets.yaml", new_export]


async def test_no_issue_outside_config_or_already_ignored(hass: HomeAssistant, tmp_path) -> None:
    _watchman(hass, data={"ignored_files": ["*/entity_inventory*.yaml"]})
    covered = await _setup(hass, "entity_inventory.yaml")
    assert _issue(hass, covered) is None


async def test_exact_path_upgraded_to_pattern(hass: HomeAssistant) -> None:
    """Exception posée avant la 0.7.0 (chemin exact) : les exports ciblés ne seraient pas couverts."""
    exact = str(Path(hass.config.path("entity_inventory.yaml")))
    watchman = _watchman(hass, data={"ignored_files": [exact]})
    entry = await _setup(hass, "entity_inventory.yaml")
    hass.config_entries.async_update_entry(entry, data={**entry.data, "watchman_pattern": exact})
    assert _issue(hass, entry) is not None
    await _fix(hass, entry)
    assert watchman.data["ignored_files"] == [str(Path(hass.config.path("entity_inventory*.yaml")))]


async def test_no_issue_on_share(hass: HomeAssistant, tmp_path: Path) -> None:
    _watchman(hass, data={"ignored_files": []})
    entry = await _setup(hass, str(tmp_path / "share" / "entity_inventory.yaml"))
    assert _issue(hass, entry) is None


async def test_no_watchman_no_issue(hass: HomeAssistant) -> None:
    entry = await _setup(hass, "entity_inventory.yaml")
    assert _issue(hass, entry) is None


async def test_legacy_text_format(hass: HomeAssistant) -> None:
    """Anciennes versions de Watchman : options['ignored_files'] = 'a, b'."""
    watchman = _watchman(hass, options={"ignored_files": "*/secrets.yaml, */ui-lovelace.yaml"})
    entry = await _setup(hass, "entity_inventory.yaml")
    await _fix(hass, entry)
    export = str(Path(hass.config.path("entity_inventory*.yaml")))
    assert watchman.options["ignored_files"] == f"*/secrets.yaml, */ui-lovelace.yaml, {export}"


async def test_unknown_format_untouched(hass: HomeAssistant) -> None:
    watchman = _watchman(hass, data={"ignored_files": {"inattendu": True}})
    entry = await _setup(hass, "entity_inventory.yaml")
    result = await _fix(hass, entry)
    assert result["type"] == "abort" and result["reason"] == "unsupported"
    assert watchman.data["ignored_files"] == {"inattendu": True}


async def test_default_path_on_haos(hass: HomeAssistant) -> None:
    from custom_components.entity_inventory.exporter import default_output_path

    with patch("custom_components.entity_inventory.exporter.is_hassio", return_value=True):
        assert default_output_path(hass) == "/share/entity_inventory.yaml"
    with patch("custom_components.entity_inventory.exporter.is_hassio", return_value=False):
        assert default_output_path(hass) == "entity_inventory.yaml"


async def test_alerts_once_per_situation(hass: HomeAssistant) -> None:
    from homeassistant.components import persistent_notification

    sent = []
    hass.services.async_register("notify", "send_message", lambda call: sent.append(call.data))
    hass.states.async_set("notify.iphone", "unknown")
    _watchman(hass, data={"ignored_files": []})
    entry = MockConfigEntry(domain=DOMAIN, options={
        CONF_OUTPUT_PATH: "entity_inventory.yaml", "notify_entity": "notify.iphone"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    notif_id = f"{DOMAIN}_watchman_{entry.entry_id}"
    assert notif_id in persistent_notification._async_get_or_create_notifications(hass)
    assert len(sent) == 1 and sent[0]["entity_id"] == "notify.iphone"
    assert "Réparations" in sent[0]["message"] or "Repairs" in sent[0]["message"]

    # Exports suivants : pas de nouvelle alerte, et pas de rechargement
    for _ in range(3):
        await hass.services.async_call(DOMAIN, "export", {}, blocking=True)
    await hass.async_block_till_done()
    assert len(sent) == 1

    # Correction : notification retirée, situation oubliée
    await _fix(hass, entry)
    assert notif_id not in persistent_notification._async_get_or_create_notifications(hass)
    assert not hass.config_entries.async_get_entry(entry.entry_id).data.get("alerted")


async def test_meta_has_version(hass: HomeAssistant, tmp_path: Path) -> None:
    import yaml as _yaml
    entry = await _setup(hass, str(tmp_path / "e.yaml"))
    await hass.services.async_call(DOMAIN, "export", {}, blocking=True)
    meta = _yaml.safe_load((tmp_path / "e.yaml").read_text(encoding="utf-8"))["meta"]
    from homeassistant.loader import async_get_integration
    assert meta["generator_version"] == str((await async_get_integration(hass, DOMAIN)).version)
