"""Tests de l'action entity_inventory.validate (cas tirés d'un vrai test avec Copilot)."""

from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.entity_inventory.const import CONF_OUTPUT_PATH, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def setup(hass: HomeAssistant, tmp_path: Path) -> None:
    for domain, service in (("climate", "set_preset_mode"), ("climate", "set_hvac_mode"),
                            ("notify", "iphone"), ("light", "turn_on")):
        hass.services.async_register(domain, service, lambda call: None)
    hass.states.async_set("climate.sdb", "heat", {
        "hvac_modes": ["heat", "off"], "preset_modes": ["comfort", "comfort_1", "eco", "away"]})
    hass.states.async_set("climate.mobile", "heat", {
        "hvac_modes": ["heat", "off", "auto"], "preset_modes": ["comfort", "eco", "Comfort 1", "boost"]})
    hass.states.async_set("binary_sensor.fenetre_sdb", "off", {"device_class": "window"})
    hass.states.async_set("sensor.pile_porte", "87", {"unit_of_measurement": "%"})
    off = er.async_get(hass).async_get_or_create("sensor", "zha", "x", original_name="LQI")
    er.async_get(hass).async_update_entity(off.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_OUTPUT_PATH: str(tmp_path / "i.yaml")})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _validate(hass: HomeAssistant, text: str) -> dict:
    return await hass.services.async_call(
        DOMAIN, "validate", {"yaml": text}, blocking=True, return_response=True
    )


COPILOT_1 = """
alias: SDB - Sèche-serviette selon fenêtre
mode: single
trigger:
  - platform: state
    entity_id: binary_sensor.fenetre_sdb
action:
  - choose:
      - conditions:
          - condition: state
            entity_id: binary_sensor.fenetre_sdb
            state: "on"
        sequence:
          - service: climate.set_preset_mode
            target:
              entity_id: climate.sdb
            data:
              preset_mode: eco
"""


async def test_copilot_answer_valid_but_legacy(hass: HomeAssistant, setup) -> None:
    result = await _validate(hass, COPILOT_1)
    assert result["valid"] is True and result["errors"] == []
    assert result["entities_checked"] == 2
    assert any("service:" in w for w in result["warnings"])
    assert any("platform:" in w for w in result["warnings"])
    assert any("trigger:" in w for w in result["warnings"])


async def test_modern_syntax_no_warning(hass: HomeAssistant, setup) -> None:
    result = await _validate(hass, """
triggers:
  - trigger: state
    entity_id: binary_sensor.fenetre_sdb
    to: "on"
actions:
  - action: climate.set_preset_mode
    target: {entity_id: climate.mobile}
    data: {preset_mode: "Comfort 1"}
""")
    assert result == {"valid": True, "errors": [], "warnings": [], "entities_checked": 2,
                      "actions_checked": 1}


async def test_wrong_values(hass: HomeAssistant, setup) -> None:
    result = await _validate(hass, """
actions:
  - action: climate.set_preset_mode
    target: {entity_id: climate.mobile}
    data: {preset_mode: comfort_1}
  - action: climate.set_hvac_mode
    target: {entity_id: climate.sdb}
    data: {hvac_mode: off}
  - action: climate.set_party_mode
    target: {entity_id: climate.sdb}
""")
    errors = "\n".join(result["errors"])
    assert result["valid"] is False
    assert "comfort_1" in errors and "Comfort 1" in errors  # liste des valeurs possibles
    assert "booléen False" in errors
    assert "action inexistante « climate.set_party_mode »" in errors


async def test_copilot_answer_3_group(hass: HomeAssistant, setup) -> None:
    result = await _validate(hass, """
triggers:
  - trigger: numeric_state
    entity_id: group.batteries_zigbee
    below: 15
  - trigger: numeric_state
    entity_id: binary_sensor.fenetre_sdb
    below: 15
  - trigger: numeric_state
    entity_id: sensor.pile_porte
    below: 15
actions:
  - action: notify.iphone
    data:
      message: "{{ states('sensor.pile_inconnue') }} {{ states.sensor.pile_porte.state }}"
""")
    errors = "\n".join(result["errors"])
    assert "entité inexistante « group.batteries_zigbee »" in errors
    assert "numeric_state sur « binary_sensor.fenetre_sdb »" in errors
    assert "entité inexistante « sensor.pile_inconnue »" in errors
    assert "sensor.pile_porte" not in errors


async def test_tags_disabled_and_broken_yaml(hass: HomeAssistant, setup) -> None:
    result = await _validate(hass, """
blueprint:
  input:
    cible: !input cible
actions:
  - action: light.turn_on
    target:
      entity_id: sensor.zha_x
""")
    assert any("désactivée" in w for w in result["warnings"])
    assert any("autre domaine" in w for w in result["warnings"])
    broken = await _validate(hass, "actions: [unclosed")
    assert broken["valid"] is False and broken["errors"][0].startswith("YAML illisible")


# --- Cas réel : outils de développement (le YAML passe par le moteur de templates) --- #
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.script import Script

COPILOT_3 = """triggers:
  - trigger: numeric_state
    entity_id:
      - sensor.pile_porte
      - sensor.30fb10fffe74e11b_battery
    below: 15
actions:
  - action: notify.iphone
    data:
      message: "{{ trigger.to_state.name }} est à {{ trigger.to_state.state }} %."
"""


async def _run_like_devtools(hass: HomeAssistant, data: dict) -> dict:
    """Même chemin que Outils de développement → Actions (websocket execute_script)."""
    script = Script(
        hass,
        cv.SCRIPT_SCHEMA([{"action": f"{DOMAIN}.validate", "data": data, "response_variable": "r"}]),
        "devtools",
        DOMAIN,
    )
    run = await script.async_run(context=Context())
    return run.variables["r"]


async def test_devtools_template_error_reproduced(hass: HomeAssistant, setup) -> None:
    with pytest.raises(HomeAssistantError, match="trigger"):
        await _run_like_devtools(hass, {"yaml": COPILOT_3})


async def test_devtools_raw_block(hass: HomeAssistant, setup) -> None:
    result = await _run_like_devtools(hass, {"yaml": "{% raw %}\n" + COPILOT_3 + "{% endraw %}"})
    assert result["valid"] is False
    assert result["errors"] == [
        "triggers[0] : entité inexistante « sensor.30fb10fffe74e11b_battery »"
    ]
    assert result["warnings"] == []


async def test_devtools_path(hass: HomeAssistant, setup) -> None:
    draft = Path(hass.config.path("ia"))
    draft.mkdir(exist_ok=True)
    (draft / "brouillon.yaml").write_text(COPILOT_3, encoding="utf-8")
    result = await _run_like_devtools(hass, {"path": "ia/brouillon.yaml"})
    assert result["valid"] is False and len(result["errors"]) == 1


async def test_path_refused(hass: HomeAssistant, setup) -> None:
    Path(hass.config.path("secrets.yaml")).write_text("a: b\n", encoding="utf-8")
    for bad in ("secrets.yaml", "../etc/passwd", "/etc/hosts.yaml", "notes.txt"):
        with pytest.raises(ServiceValidationError, match="Chemin refusé"):
            await hass.services.async_call(DOMAIN, "validate", {"path": bad},
                                           blocking=True, return_response=True)
    with pytest.raises(ServiceValidationError, match="Lecture impossible"):
        await hass.services.async_call(DOMAIN, "validate", {"path": "absent.yaml"},
                                       blocking=True, return_response=True)


async def test_notify_entity_called_as_action(hass: HomeAssistant, setup) -> None:
    """Cas réel Copilot : service: notify.mon_telephone (c'est une entité)."""
    hass.states.async_set("notify.iphone_tel", "unknown")
    hass.services.async_register("notify", "send_message", lambda call: None)
    hass.services.async_register("notify", "mobile_app_iphone_tel", lambda call: None)
    hass.states.async_set("switch.prise", "off")
    result = await _validate(hass, """
actions:
  - action: notify.iphone_tel
    data: {message: test}
  - action: switch.prise
  - action: notify.send_message
    target: {entity_id: notify.iphone_tel}
    data: {message: test}
""")
    errors = result["errors"]
    assert len(errors) == 2
    assert "« notify.iphone_tel » est une entité, pas une action" in errors[0]
    assert "notify.send_message" in errors[0] and "notify.mobile_app_iphone_tel" in errors[0]
    assert "« switch.prise » est une entité" in errors[1]


async def test_nothing_checked_is_not_valid(hass: HomeAssistant, setup) -> None:
    """Cas réel : brouillon.yaml contenant l'appel validate complet → faux « valid: true »."""
    wrapped = (
        "action: entity_inventory.validate\n"
        "data:\n"
        "  yaml: |\n"
        "    triggers:\n"
        "      - trigger: numeric_state\n"
        "        entity_id: sensor.inconnu\n"
        "        below: 15\n"
    )
    for text, expected in (
        (wrapped, "appel à entity_inventory.validate lui-même"),
        ("", "le texte ou le fichier est vide"),
        ("# rien que des commentaires\n", "le texte ou le fichier est vide"),
        ("alias: test\ndescription: rien\n", "aucune entité ni action trouvée"),
    ):
        result = await _validate(hass, text)
        assert result["valid"] is False, text
        assert expected in result["errors"][0], (text, result)


async def test_update_automation_warned(hass: HomeAssistant, setup) -> None:
    """Tutoriels « mises à jour automatiques » : avertir sans interdire."""
    for domain, service in (("update", "install"), ("hassio", "addon_update"),
                            ("mqtt", "publish"), ("notify", "send_message")):
        hass.services.async_register(domain, service, lambda call: None)
    hass.states.async_set("update.home_assistant_core_update", "on")
    hass.states.async_set("notify.tel", "unknown")
    result = await _validate(hass, """
triggers:
  - trigger: time
    at: "03:00:00"
actions:
  - action: update.install
    target: {entity_id: update.home_assistant_core_update}
  - action: hassio.addon_update
    data: {addon: core_mosquitto}
  - action: mqtt.publish
    data: {topic: zigbee2mqtt/bridge/request/device/ota_update/update, payload: prise}
  - action: mqtt.publish
    data: {topic: zigbee2mqtt/prise/set, payload: '{"state": "ON"}'}
""")
    assert result["valid"] is True  # décision laissée à l'occupant
    updates = [w for w in result["warnings"] if "mise à jour automatique" in w]
    assert len(updates) == 3
    assert "« update.install »" in updates[0] and "« hassio.addon_update »" in updates[1]

    # Alternative recommandée : une simple notification ne déclenche rien
    result = await _validate(hass, """
triggers:
  - trigger: state
    entity_id: update.home_assistant_core_update
    to: "on"
actions:
  - action: notify.send_message
    target: {entity_id: notify.tel}
    data: {message: Mise à jour disponible}
""")
    assert result["valid"] is True and result["warnings"] == []


async def test_header_discourages_update_automation(hass: HomeAssistant, setup, tmp_path: Path) -> None:
    await hass.services.async_call(DOMAIN, "export", {}, blocking=True)
    text = (tmp_path / "i.yaml").read_text(encoding="utf-8")
    assert "ne JAMAIS les automatiser" in text and "PREMIÈRE réponse ne contient AUCUN YAML" in text


async def test_update_all_gemini_case(hass: HomeAssistant, setup) -> None:
    """Cas réel Gemini : update.install sur entity_id: all, sans sauvegarde."""
    hass.services.async_register("update", "install", lambda call: None)
    hass.states.async_set("update.zigbee2mqtt_update", "on")
    result = await _validate(hass, """
alias: "Système - Installation automatique des mises à jour à 3h"
trigger:
  - platform: time
    at: "03:00:00"
action:
  - action: update.install
    target:
      entity_id: all
mode: single
""")
    warnings = " | ".join(result["warnings"])
    assert result["valid"] is True
    assert "TOUTES les mises à jour" in warnings
    assert "backup: true" in warnings
    assert "platform:" in warnings  # ancienne syntaxe toujours signalée

    # Cible précise + sauvegarde : seul l'avertissement de principe reste
    result = await _validate(hass, """
actions:
  - action: update.install
    target: {entity_id: update.zigbee2mqtt_update}
    data: {backup: true}
""")
    assert len(result["warnings"]) == 1 and "mise à jour automatique" in result["warnings"][0]
