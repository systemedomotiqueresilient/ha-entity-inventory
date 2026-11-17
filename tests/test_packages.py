"""0.6.0 : section packages, état de démarrage."""

from pathlib import Path

import pytest
import yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.entity_inventory.const import (
    CONF_INCLUDE_PACKAGES,
    CONF_OUTPUT_PATH,
    DOMAIN,
)
from custom_components.entity_inventory.exporter import async_build_inventory


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


CONFIGURATION = """
homeassistant:
  packages: !include_dir_named packages
http:
  api_password: !secret pw
"""

DERIVEE_WC = """# =============================================================
# Package : Dérivées WC
# =============================================================
sensor:
  - platform: derivative
    source: sensor.0x00124b002a50b200_temperature
    name: T° WC Sonoff (Package)
    unique_id: sensor.tdeg_wc_sonoff_package
"""

TEMPERATURE = """# Package : Température globale - contact@example.org
template:
  - sensor:
      - name: Température Appartement Globale (Package)
        unique_id: sensor_home_temperature_combined
        state: >
          {{ [states('sensor.sejour'), states.sensor.lqi_off.state] | join }}
input_boolean:
  fenetre_wc_virtual:
    name: Fenêtre WC Virtuelle
automation:
  - id: "1700000000001"
    alias: Alerte
    triggers:
      - trigger: state
        entity_id: input_boolean.fenetre_wc_virtual
    actions:
      - action: notify.send_message
        target:
          entity_id: notify.tel
        data:
          message: "Fenêtre {{ states('sensor.sejour') }} — voir config.yaml"
"""


@pytest.fixture
async def config_dir(hass: HomeAssistant, tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    (cfg / "packages").mkdir(parents=True)
    (cfg / "configuration.yaml").write_text(CONFIGURATION, encoding="utf-8")
    (cfg / "secrets.yaml").write_text("pw: ne-doit-jamais-sortir\n", encoding="utf-8")
    (cfg / "packages" / "derivee_wc.yaml").write_text(DERIVEE_WC, encoding="utf-8")
    (cfg / "packages" / "temperature.yaml").write_text(TEMPERATURE, encoding="utf-8")
    hass.config.config_dir = str(cfg)

    reg = er.async_get(hass)
    reg.async_get_or_create("sensor", "derivative", "sensor.tdeg_wc_sonoff_package",
                            suggested_object_id="tdeg_wc_sonoff_package")
    reg.async_get_or_create("sensor", "template", "sensor_home_temperature_combined",
                            suggested_object_id="temperature_appartement")
    reg.async_get_or_create("automation", "automation", "1700000000001",
                            suggested_object_id="alerte")
    off = reg.async_get_or_create("sensor", "zha", "lqi", suggested_object_id="lqi_off")
    reg.async_update_entity(off.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    hass.states.async_set("sensor.sejour", "19.5")
    hass.states.async_set("input_boolean.fenetre_wc_virtual", "off")
    hass.states.async_set("notify.tel", "unknown")
    hass.services.async_register("notify", "send_message", lambda call: None)
    return cfg


async def _export(hass: HomeAssistant, tmp_path: Path, **options) -> tuple[dict, str]:
    out = tmp_path / "out" / "e.yaml"
    out.parent.mkdir(exist_ok=True)
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_OUTPUT_PATH: str(out), **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "export", {}, blocking=True)
    text = out.read_text(encoding="utf-8")
    return yaml.safe_load(text), text


async def test_packages_section(hass: HomeAssistant, config_dir: Path, tmp_path: Path) -> None:
    data, text = await _export(hass, tmp_path)
    pkgs = data["packages"]

    wc = pkgs["derivee_wc"]
    assert wc["file"] == "packages/derivee_wc.yaml"
    assert wc["description"] == "Package : Dérivées WC"
    assert wc["defines"] == ["sensor.tdeg_wc_sonoff_package"]
    assert wc["missing"] == ["sensor.0x00124b002a50b200_temperature"]

    temp = pkgs["temperature"]
    assert temp["description"] == "Package : Température globale - [email]"
    assert temp["defines"] == [
        "automation.alerte", "input_boolean.fenetre_wc_virtual", "sensor.temperature_appartement"
    ]
    assert temp["disabled"] == ["sensor.lqi_off"]  # citée via states.sensor.lqi_off.state
    assert "missing" not in temp  # notify.send_message (action), config.yaml (texte) ignorés

    assert data["meta"]["counts"]["packages"] == 2
    assert data["meta"]["counts"]["packages_with_missing"] == 1
    assert data["meta"]["filters"]["packages"] == "included"
    assert "ne-doit-jamais-sortir" not in text  # !secret jamais exporté
    assert "N'EXISTENT PLUS" in text  # règle de lecture dans l'en-tête


async def test_packages_option_off(hass: HomeAssistant, config_dir: Path, tmp_path: Path) -> None:
    data, _ = await _export(hass, tmp_path, **{CONF_INCLUDE_PACKAGES: False})
    assert "packages" not in data
    assert data["meta"]["filters"]["packages"] == "excluded"


async def test_unreadable_configuration(hass: HomeAssistant, config_dir: Path, tmp_path: Path) -> None:
    (config_dir / "secrets.yaml").unlink()  # !secret introuvable
    data, _ = await _export(hass, tmp_path)
    assert "packages" not in data
    assert "illisible" in data["meta"]["packages_error"]
    assert data["meta"]["counts"]["entities"] >= 1  # l'export n'est pas bloqué


async def test_ha_state_starting(hass: HomeAssistant) -> None:
    assert async_build_inventory(hass)["meta"]["ha_state"] == "running"
    hass.set_state(CoreState.starting)
    try:
        assert async_build_inventory(hass)["meta"]["ha_state"] == "starting"
    finally:
        hass.set_state(CoreState.running)


def test_description_skips_code_like_comments(tmp_path: Path) -> None:
    from custom_components.entity_inventory.packages import _description

    cases = {
        "# packages/chauffage_mobile.yaml\n# coreelec_odroidhc4:\n# Package : Chauffage mobile\n": "Package : Chauffage mobile",
        "# ======\n#   platform: derivative\n# ======\nsensor:\n": None,
        "# Package: Scène Nuit Couloir (Package)\n": "Package: Scène Nuit Couloir (Package)",
    }
    for text, expected in cases.items():
        f = tmp_path / "p.yaml"
        f.write_text(text, encoding="utf-8")
        assert _description(str(f)) == expected


async def test_header_asks_to_report_broken_packages(hass: HomeAssistant, config_dir: Path, tmp_path: Path) -> None:
    _, text = await _export(hass, tmp_path)
    assert "AVANT de répondre, consulte la section \"packages\"" in text
