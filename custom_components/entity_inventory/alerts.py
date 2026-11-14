"""Alertes : notification persistante + (option) notification mobile, une fois par situation."""

from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import CONF_NOTIFY_ENTITY, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_ALERTED = "alerted"  # data de l'entrée : {clé de situation: valeur déjà signalée}

# Textes par situation : (titre, message persistant, message court pour le téléphone)
TEXTS: dict[str, dict[str, tuple[str, str, str]]] = {
    "watchman": {
        "fr": (
            "Entity Inventory : action requise",
            "Watchman analyse le fichier d'export **{path}** et va signaler à tort des centaines "
            "d'entités. [Ouvrir les réparations](/config/repairs) pour l'ajouter aux fichiers "
            "ignorés de Watchman en un clic, ou choisir un chemin hors de /config.",
            "Watchman analyse l'export {path}. Une réparation vous attend : "
            "Paramètres → Système → Réparations.",
        ),
        "en": (
            "Entity Inventory: action required",
            "Watchman scans the export file **{path}** and will wrongly report hundreds of "
            "entities. [Open repairs](/config/repairs) to add it to Watchman's ignored files "
            "in one click, or choose a path outside /config.",
            "Watchman scans the export {path}. A repair is waiting: Settings → System → Repairs.",
        ),
    },
    "export": {
        "fr": (
            "Entity Inventory : export impossible",
            "L'inventaire n'a pas pu être écrit dans **{path}** : {error}\n\n"
            "Le fichier fourni à l'IA n'est donc plus à jour. Vérifiez que le dossier existe, "
            "ou choisissez un autre chemin dans les options d'Entity Inventory.",
            "Export impossible vers {path} : {error}",
        ),
        "en": (
            "Entity Inventory: export failed",
            "The inventory could not be written to **{path}**: {error}\n\n"
            "The file given to the AI is therefore out of date. Check that the folder exists, "
            "or choose another path in the Entity Inventory options.",
            "Export to {path} failed: {error}",
        ),
    },
}


# Causes d'échec d'export, lisibles par l'occupant
REASONS: dict[str, dict[str, str]] = {
    "dir_missing": {
        "fr": "le dossier {dir} n'existe pas",
        "en": "folder {dir} does not exist",
    },
    "dir_not_writable": {
        "fr": "le dossier {dir} n'est pas accessible en écriture",
        "en": "folder {dir} is not writable",
    },
    "is_dir": {
        "fr": "{dir} est un dossier, pas un fichier",
        "en": "{dir} is a folder, not a file",
    },
}


def reason_text(hass: HomeAssistant, code: str, directory: str) -> str:
    lang = "fr" if (hass.config.language or "").startswith("fr") else "en"
    return REASONS[code][lang].format(dir=directory)


def notification_id(entry: ConfigEntry, key: str) -> str:
    return f"{DOMAIN}_{key}_{entry.entry_id}"


def _texts(hass: HomeAssistant, key: str) -> tuple[str, str, str]:
    lang = "fr" if (hass.config.language or "").startswith("fr") else "en"
    return TEXTS[key][lang]


@callback
def async_raise(
    hass: HomeAssistant, entry: ConfigEntry, key: str, value: str, **placeholders: str
) -> None:
    """Signale une situation, sauf si elle l'a déjà été pour cette même valeur.

    `value` identifie la situation (le chemin) ; `placeholders` complète le texte.
    """
    alerted = dict(entry.data.get(DATA_ALERTED) or {})
    if alerted.get(key) == value:
        return

    title, message, short = _texts(hass, key)
    fields = {"path": value, **placeholders}
    persistent_notification.async_create(
        hass, message.format(**fields), title, notification_id(entry, key)
    )

    target = entry.options.get(CONF_NOTIFY_ENTITY)
    if target:
        if hass.services.has_service("notify", "send_message") and hass.states.get(target):
            hass.async_create_task(
                hass.services.async_call(
                    "notify",
                    "send_message",
                    {"entity_id": target, "title": title, "message": short.format(**fields)},
                    blocking=False,
                ),
                f"{DOMAIN} notification mobile",
            )
        else:
            _LOGGER.warning("Notification mobile impossible : %s introuvable", target)

    alerted[key] = value
    hass.config_entries.async_update_entry(entry, data={**entry.data, DATA_ALERTED: alerted})


@callback
def async_clear(hass: HomeAssistant, entry: ConfigEntry, key: str) -> None:
    """La situation est résolue : retirer la notification et oublier qu'elle a été signalée."""
    persistent_notification.async_dismiss(hass, notification_id(entry, key))
    alerted = dict(entry.data.get(DATA_ALERTED) or {})
    if alerted.pop(key, None) is not None:
        hass.config_entries.async_update_entry(entry, data={**entry.data, DATA_ALERTED: alerted})
