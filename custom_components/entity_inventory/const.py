"""Constantes de l'intégration Entity Inventory."""

DOMAIN = "entity_inventory"

CONF_OUTPUT_PATH = "output_path"
DEFAULT_OUTPUT_PATH = "entity_inventory.yaml"  # relatif au dossier /config (hors HAOS)
DEFAULT_OUTPUT_PATH_SUPERVISED = "/share/entity_inventory.yaml"  # HAOS / Supervised

SERVICE_EXPORT = "export"
SERVICE_VALIDATE = "validate"
ATTR_YAML = "yaml"
ATTR_PATH = "path"

# Filtres (options de l'intégration)
CONF_INCLUDE_CONFIG = "include_config"
CONF_INCLUDE_DIAGNOSTIC = "include_diagnostic"
CONF_EXCLUDED_INTEGRATIONS = "excluded_integrations"
CONF_REDACT_EMAILS = "redact_emails"
CONF_NOTIFY_ENTITY = "notify_entity"
CONF_INCLUDE_PACKAGES = "include_packages"
CONF_AREA_BUTTONS = "area_buttons"
DEFAULT_INCLUDE_CONFIG = False
DEFAULT_INCLUDE_DIAGNOSTIC = False
DEFAULT_REDACT_EMAILS = True
DEFAULT_INCLUDE_PACKAGES = True
DEFAULT_AREA_BUTTONS = True

# Gardées même quand leur catégorie est exclue (utiles aux automatisations)
ALWAYS_KEEP_DEVICE_CLASSES: frozenset[str] = frozenset({"battery"})

# Attributs « structurels » : ils décrivent ce qu'une entité SAIT faire,
# jamais ce qu'elle mesure. Liste blanche volontaire : tout le reste
# (états, coordonnées GPS, IP, valeurs courantes…) n'est jamais exporté.
STATIC_ATTRIBUTES: tuple[str, ...] = (
    "state_class",
    "options",  # select, input_select, sensor enum
    "event_types",  # entités event (télécommandes, boutons)
    "hvac_modes",
    "preset_modes",
    "fan_modes",
    "swing_modes",
    "min_temp",
    "max_temp",
    "target_temp_step",
    "min",
    "max",
    "step",
    "supported_color_modes",
    "min_color_temp_kelvin",
    "max_color_temp_kelvin",
    "effect_list",
    "source_list",
    "sound_mode_list",
    "operation_list",  # water_heater
    "available_modes",  # humidifier
    "min_humidity",
    "max_humidity",
)
