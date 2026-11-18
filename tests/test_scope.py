"""0.7.0 : export ciblé par pièces, étages, étiquettes, domaines."""

from pathlib import Path

import pytest
import yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
    label_registry as lr,
)

from custom_components.entity_inventory.const import CONF_OUTPUT_PATH, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


PACKAGES = {
    "sdb_chauffage.yaml": "# Package : SDB chauffage\nautomation:\n  - id: a1\n    actions:\n"
    "      - action: climate.set_preset_mode\n        target: {entity_id: climate.seche_serviette}\n",
    "wc_derivees.yaml": "# Package : WC dérivées\nsensor:\n  - platform: derivative\n"
    "    source: sensor.wc_temperature\n",
    # Cas réel : package cassé dont la sonde disparue ne peut plus être rattachée à une pièce
    "chambre_derivees.yaml": "# Package : Chambre dérivées\nsensor:\n  - platform: derivative\n"
    "    source: sensor.ancienne_sonde_temperature\n",
}


@pytest.fixture
async def home(hass: HomeAssistant, tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    (cfg / "packages").mkdir(parents=True)
    (cfg / "configuration.yaml").write_text(
        "homeassistant:\n  packages: !include_dir_named packages\n", encoding="utf-8"
    )
    for name, text in PACKAGES.items():
        (cfg / "packages" / name).write_text(text, encoding="utf-8")
    hass.config.config_dir = str(cfg)

    etage = fr.async_get(hass).async_create("Étage", level=1)
    areas = ar.async_get(hass)
    sdb = areas.async_create("Salle de bain", floor_id=etage.floor_id)
    wc = areas.async_create("WC")
    couloir = areas.async_create("Couloir")
    chauffage = lr.async_get(hass).async_create("Chauffage")

    mqtt = MockConfigEntry(domain="mqtt")
    mqtt.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)

    def device(uid, name, area, labels=()):
        dev = dev_reg.async_get_or_create(config_entry_id=mqtt.entry_id, identifiers={("mqtt", uid)}, name=name)
        dev_reg.async_update_device(dev.id, area_id=area.id, labels=set(labels))
        return dev

    seche = device("seche", "Sèche-serviette", sdb, [chauffage.label_id])
    ent_reg.async_get_or_create("climate", "mqtt", "seche", device_id=seche.id,
                                suggested_object_id="seche_serviette")
    ent_reg.async_get_or_create("sensor", "mqtt", "seche_power", device_id=seche.id,
                                suggested_object_id="seche_serviette_puissance")
    sonde = device("sonde_wc", "WC", wc)
    ent_reg.async_get_or_create("sensor", "mqtt", "wc_t", device_id=sonde.id,
                                suggested_object_id="wc_temperature")
    lampe = device("lampe", "Lampe SDB", sdb)
    veilleuse = ent_reg.async_get_or_create("light", "mqtt", "veilleuse", device_id=lampe.id,
                                            suggested_object_id="veilleuse")
    ent_reg.async_update_entity(veilleuse.entity_id, area_id=couloir.id)  # entité déplacée
    hass.states.async_set("sun.sun", "above_horizon")  # hors registre

    out = tmp_path / "out"
    out.mkdir()
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_OUTPUT_PATH: str(out / "entity_inventory.yaml")})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return out


async def _export(hass: HomeAssistant, **data) -> dict:
    return await hass.services.async_call(DOMAIN, "export", data, blocking=True, return_response=True)


def _ids(inventory: dict) -> set[str]:
    found: set[str] = set()
    stack = [inventory.get("areas", {}), inventory.get("unassigned", {}), inventory.get("no_registry", [])]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if isinstance(cur.get("id"), str):
                found.add(cur["id"])
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return found


async def test_area_scope(hass: HomeAssistant, home: Path) -> None:
    result = await _export(hass, areas=["salle_de_bain"])
    path = home / "entity_inventory_salle_de_bain.yaml"
    assert result["path"] == str(path) and result["scope"] == {"areas": ["salle_de_bain"]}
    assert not (home / "entity_inventory.yaml").exists()  # l'export complet n'est pas touché

    text = path.read_text(encoding="utf-8")
    inv = yaml.safe_load(text)
    assert _ids(inv) == {"climate.seche_serviette", "sensor.seche_serviette_puissance"}
    assert set(inv["areas"]) == {"salle_de_bain"} and set(inv["floors"]) == {"etage"}
    assert "no_registry" not in inv  # sans registre : pas de pièce connue
    assert inv["meta"]["scope"] == {"areas": ["salle_de_bain"]}
    assert inv["meta"]["counts"]["excluded"]["scope"] == 2
    # le package qui touche la cible, et TOUJOURS les packages cassés de l'installation
    assert list(inv["packages"]) == ["chambre_derivees", "sdb_chauffage"]
    assert inv["packages"]["chambre_derivees"]["missing"] == ["sensor.ancienne_sonde_temperature"]
    assert inv["meta"]["counts"]["packages_with_missing"] == 1
    # compteurs du fichier, pas de toute l'instance
    assert inv["meta"]["counts"]["areas"] == 1 and inv["meta"]["counts"]["floors"] == 1
    assert "inventaire PARTIEL" in text and "SAUF les packages cassés" in text


async def test_combined_and_floor_scope(hass: HomeAssistant, home: Path) -> None:
    await _export(hass, floors=["etage"], domains=["climate"])
    inv = yaml.safe_load((home / "entity_inventory_etage_climate.yaml").read_text(encoding="utf-8"))
    assert _ids(inv) == {"climate.seche_serviette"}  # critères combinés : ET


async def test_label_and_moved_entity(hass: HomeAssistant, home: Path) -> None:
    await _export(hass, labels=["chauffage"])
    inv = yaml.safe_load((home / "entity_inventory_chauffage.yaml").read_text(encoding="utf-8"))
    assert _ids(inv) == {"climate.seche_serviette", "sensor.seche_serviette_puissance"}

    # Entité placée dans le couloir alors que son appareil est dans la salle de bain
    await _export(hass, areas=["couloir"])
    inv = yaml.safe_load((home / "entity_inventory_couloir.yaml").read_text(encoding="utf-8"))
    assert _ids(inv) == {"light.veilleuse"}


async def test_domain_only_keeps_no_registry(hass: HomeAssistant, home: Path) -> None:
    result = await _export(hass, domains=["sun"], write=False)
    assert "sun.sun" in result["yaml"]


async def test_unknown_target_refused(hass: HomeAssistant, home: Path) -> None:
    with pytest.raises(ServiceValidationError, match="salon"):
        await _export(hass, areas=["salon"])


async def test_write_false(hass: HomeAssistant, home: Path) -> None:
    result = await _export(hass, areas=["wc"], write=False)
    assert "sensor.wc_temperature" in result["yaml"] and "inventaire PARTIEL" in result["yaml"]
    assert not list(home.iterdir())  # rien d'écrit
    with pytest.raises(ServiceValidationError, match="write: false"):
        await hass.services.async_call(DOMAIN, "export", {"write": False}, blocking=True)
