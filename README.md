# Entity Inventory

🇬🇧 **English** · 🇫🇷 [Français](README.fr.md)

[![Validate](https://github.com/systemedomotiqueresilient/ha-entity-inventory/actions/workflows/validate.yml/badge.svg)](https://github.com/systemedomotiqueresilient/ha-entity-inventory/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/systemedomotiqueresilient/ha-entity-inventory)](https://github.com/systemedomotiqueresilient/ha-entity-inventory/releases)

**Give an AI the floor plan of your home, not the keys.**

Entity Inventory exports the *structure* of your Home Assistant — floors, areas, devices, entities and the values they accept — to a compact YAML file. You attach it to a conversation with the AI of your choice so it can write automations, scripts or packages with the **right `entity_id`s** and the **right modes**, without any access to your instance.

- 🔒 **No remote access**: no MCP, no token, no open API. The AI only sees a file you can read first.
- 🧹 **No private-life data**: no states, no history, no GPS coordinates, no IP addresses. Attributes go through an allow-list.
- 🧠 **Built for LLMs**: area → device → entity hierarchy, compact lists, and a header that tells the AI how to read the file.

## Installation

### Marketplace (Home Assistant 2026.11+)

*Settings → Marketplace* → search for **Entity Inventory** → Install.

Until the integration is in the default catalog: *Marketplace → ⋮ → Custom repositories* → `https://github.com/systemedomotiqueresilient/ha-entity-inventory`, type **Integration**.

### HACS (before 2026.11)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=systemedomotiqueresilient&repository=ha-entity-inventory&category=integration)

Or *HACS → ⋮ → Custom repositories* → the repository URL, type **Integration**.

### Manual

Copy `custom_components/entity_inventory/` into `/config/custom_components/` and restart.

## Configuration

*Settings → Devices & services → Add integration → Entity Inventory*, then choose the output file:

- default: `/share/entity_inventory.yaml` on HAOS / Supervised (reachable over Samba, out of Watchman's reach), `/config/entity_inventory.yaml` otherwise;
- a relative path is relative to `/config`; absolute paths are accepted (e.g. `/share/entity_inventory.yaml`);
- **`/config/www` is refused**: that folder is served without authentication under `/local/`;
- the folder is checked as soon as you enter it: outside `/config` it must already exist (on a Docker or Core install, `/share` does not exist and is never created). Under `/config`, a missing sub-folder is created on the first export.

| Option | Default | Effect |
|---|---|---|
| Include configuration entities | no | calibrations, LED mode, "check for update" buttons… |
| Include diagnostic entities | no | signal, LQI, voltage, last seen… — **batteries are always kept** |
| Integrations to exclude | none | e.g. `proxmoxve`, `sentinel`, `sentinel_report`: none of their entities are exported |
| Hide e-mail addresses | yes | any address found in a name becomes `[email]` |
| Analyse packages | yes | lists package files, what they create and what they cite that no longer exists |
| One export button per area | yes | a button placed in each area, shown by area dashboards |
| Phone to notify | none | `notify.*` entity (Companion app) alerted when action is required |

The file states in `meta.filters` and `meta.counts.excluded` what was filtered out, so the AI knows a missing entity may still exist. Disabled entities are never listed (only counted).

Order of magnitude on a real 2,400-entity installation: **470 KB → 170 KB** (≈ 146k → 55k tokens) with the default filters, **≈ 135 KB** (≈ 42k tokens) when monitoring integrations are also excluded. A targeted export of one area fits in a few KB.

Everything can be changed later through *Configure*.

## Usage

- the **Export inventory** button (its state shows the date of the last export);
- an **Export inventory *Area*** button in each area, producing the targeted export of that area (`entity_inventory_bathroom.yaml`). It is placed in its area: the automatic dashboards and the areas dashboard show it without any card to add. Buttons follow areas (creation, renaming, deletion); a button you move by hand is never moved back;
- or the `entity_inventory.export` action, which returns the path and the counters.

Automatic export every night:

```yaml
automation:
  - alias: Nightly inventory
    triggers:
      - trigger: time
        at: "03:00:00"
    actions:
      - action: entity_inventory.export
```

If an export fails (folder gone, read-only disk…), a **persistent notification** says so and the phone chosen in the options is notified: otherwise a failed nightly export would go unnoticed and the AI would work on an outdated inventory. The folder is also checked at every startup. One alert per situation; it disappears with the next successful export.

### Targeted export

To give the AI only what it needs, the action accepts a target:

```yaml
action: entity_inventory.export
data:
  areas: [bathroom]           # areas (area_id)
  floors: [upstairs]          # floors: all their areas
  labels: [heating]           # labels carried by the entity or its device
  domains: [climate]          # entity domains
```

- Within one criterion, any value matches (`areas: [toilet, hallway]` = either one); across criteria, all must match (`areas` + `domains` = the thermostats of those areas).
- The result goes to a **separate file** named after the target (`entity_inventory_bathroom.yaml`): the full export is left untouched.
- The full header is kept, and `meta.scope` tells the AI the inventory is **partial**: it knows a missing entity may exist elsewhere, and that a whole category or a conflict check needs the full export.
- Only packages that create or cite an entity of the target are listed.
- An unknown area, floor or label is refused with the list of valid values, instead of producing an empty file.
- `write: false` writes nothing: the inventory is only returned in the action response, to copy from the developer tools.

Beginners give the full export; more advanced users choose what they share.

Then, in the conversation with the AI: *"Here is my home inventory. Write a package that sets every radiator upstairs to eco when the alarm is armed."*

## Living with Watchman

[Watchman](https://github.com/dummylabs/thewatchman) scans the `.yaml` files in `/config` and reports every cited entity that is missing, unavailable or unknown. An export stored in `/config` would add hundreds of false positives (buttons, scenes, text-to-speech… are normally `unknown`).

- On HAOS the export goes to `/share` by default: Watchman does not see it.
- If you choose a path inside `/config` and Watchman is installed, a **repair** appears (*Settings → System → Repairs*). Once confirmed, Entity Inventory adds a pattern to Watchman's ignored files that covers the full export and targeted exports (`entity_inventory*.yaml`). An exception set before 0.7.0 with the exact path is replaced by this pattern through the same repair. If you change the path later, the repair comes back and replaces the old one.
- So you don't miss it among other repairs, a **persistent notification** (with a link to repairs) is created and, if you chose a **phone to notify** in the options (Companion app `notify.*` entity), it receives a notification. Only once per situation: no reminder at every export or restart.
- Nothing is ever changed in Watchman without this confirmation. If its configuration format is not recognised, nothing is touched and the repair says so.
- Drafts to validate can also go to `/share/ai/` (`path: /share/ai/draft.yaml`) for the same reason.

## Checking what the AI wrote

The `entity_inventory.validate` action checks AI-written YAML against your real instance. Two ways to give it the YAML:

**1. As a file (recommended).** Save the AI's answer, for example to `/config/ai/draft.yaml` (file editor, Samba…), then in *Developer tools → Actions*:

```yaml
action: entity_inventory.validate
data:
  path: ai/draft.yaml
```

The path is relative to `/config` (or absolute under `/share`). Only `.yaml`/`.yml` files are accepted, never `secrets.yaml`.

The file contains **only** the AI's YAML (`alias:`, `triggers:`, `actions:`…), not the `action: entity_inventory.validate` call nor a `raw` block. The response reports `entities_checked` and `actions_checked`: YAML in which nothing could be checked is declared invalid rather than wrongly correct.

**2. By copy-paste.** The developer tools render `{{ … }}` templates *before* calling the action: YAML containing `{{ trigger.to_state.name }}` fails with `'trigger' is undefined`. Wrap it in a `raw` block:

```yaml
action: entity_inventory.validate
data:
  yaml: |
    {% raw %}
    triggers:
      - trigger: numeric_state
        entity_id: sensor.living_room_battery
        below: 15
    actions:
      - action: notify.send_message
        target:
          entity_id: notify.my_phone
        data:
          message: "{{ trigger.to_state.name }}: {{ trigger.to_state.state }} %"
    {% endraw %}
```

Without changing anything, the response lists:

- **errors**: unknown entity or action, an entity called as an action (e.g. `action: notify.my_phone` instead of `notify.send_message`) (including inside `states('…')` templates), `preset_mode` / `option` / `hvac_mode` outside the allowed values (with the correct list), unquoted `off` read as a boolean, `numeric_state` on a non-numeric entity (`group.*`, `binary_sensor`…);
- **warnings**: disabled entity, action applied to an entity of another domain, legacy syntax (`platform:`, `service:`, `trigger:` instead of `triggers:`…), **automated updates** (`update.install`, `hassio.addon_update`, Zigbee2MQTT OTA), with a stronger warning for `update.install` on `all` or without a target, and without `backup: true`.

> **Updates: always a human decision.** Many tutorials suggest installing updates automatically at night. An update can break an integration, require a migration or a restart: it should be started by hand, when someone can react. The inventory header asks the AI not to provide any installation YAML in its first answer, to suggest an "update available" notification instead and to wait for explicit confirmation; validation flags it with a warning. Nothing is forbidden: the decision stays with the occupant.

What validation cannot see: an incomplete list ("all batteries" with some missing) or questionable logic. Read it anyway.

## File content

```yaml
meta:          # HA version, date, counters
floors:        # floor_id → name, level
labels:        # label_id → name
areas:         # area_id → devices → entities (+ entities without a device)
  living_room:
    name: Living room
    floor: ground_floor
    devices:
      - name: Living room radiator
        manufacturer: NodOn
        integration: zha
        via: Zigbee coordinator   # gateway: where the device is renamed or removed
        entities:
          - id: climate.living_room_radiator
            hvac_modes: [heat, 'off']
            preset_modes: [comfort, eco, away, none]
unassigned:    # devices / entities without an area
no_registry:   # YAML entities without unique_id
packages:      # package files: what they create, what they cite that is gone
  toilet_derivatives:
    file: packages/toilet_derivatives.yaml
    description: "Package: toilet derivatives"   # first comment line of the file
    defines: [sensor.toilet_temperature_rate]
    missing: [sensor.0x00124b002a50b200_temperature]   # → broken package
```

| Exported | Never exported |
|---|---|
| entity_id, name, area, floor, labels, aliases | current states, history |
| device: name, manufacturer, model, integration, gateway (`via`) | GPS coordinates, IP addresses, dynamic attributes |
| device_class, unit, state_class, category | internal device identifiers |
| `options`, `hvac_modes`, `preset_modes`, `event_types`, min/max… | |

The attribute allow-list lives in [`const.py`](custom_components/entity_inventory/const.py).

> ⚠️ **Names** are exported as they are (areas, devices, calendars…). Some monitoring integrations name their sensors after the title of the accounts they watch: e-mail addresses are masked in names, but an `entity_id` may contain a "slugified" form of one (it must stay exact for the AI). Exclude those integrations if needed, and read the file before sharing it.

## Packages

An AI only fixes what it is shown. When a sensor is replaced, every package that cites it breaks silently, and nothing tells the AI those packages exist. The `packages` section points them out: for each file declared under `homeassistant: packages:` (any folder, `!include_dir_named`, `!include_dir_merge_named` or inline), it gives:

- `defines`: the entities the file creates (no need to recreate them elsewhere — the usual source of `_2` duplicates);
- `missing`: cited entities that **no longer exist**;
- `disabled`: cited entities that are disabled;
- `description`: the first comment line of the file.

**File contents are never exported**, only their names and `entity_id`s. Files are read-only, using Home Assistant's own loader; `!secret` values never leave. If `configuration.yaml` cannot be read, the section is omitted (`meta.packages_error`) without blocking the export.

### Suggested naming convention

Two habits make this section much more useful, to the AI and to you:

1. **A file name that says the area and the purpose**: `toilet_derivatives.yaml`, `home_average_temperature.yaml` rather than `deriv_wc.yaml` or `test2.yaml`.
2. **A first comment line** describing the package, copied as is:

```yaml
# Package: toilet — temperature and humidity derivatives (SNZB-02P sensor)
sensor:
  - platform: derivative
    ...
```

## Startup state

An export started while Home Assistant is still starting (for example by an automation triggered at startup) may be incomplete: YAML entities without `unique_id` not created yet, some values missing. It is marked `meta.ha_state: starting`, and the header asks the AI to point it out.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

Releasing a version: create a GitHub release tagged `vX.Y.Z`. The `release.yml` workflow writes the version into `manifest.json` and attaches `entity_inventory.zip`.

## License

MIT
