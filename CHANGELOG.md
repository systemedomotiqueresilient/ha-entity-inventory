# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions selon [SemVer](https://semver.org/lang/fr/). Les versions antérieures à la 0.9.0 sont résumées d'après l'historique git.

## [0.9.0] - 2026-11-20

### Ajouté
- **Téléphone admin**, la convention commune aux intégrations SDR. Le module `admin_phone.py` **1.1.0** est copié tel quel depuis le dépôt de référence `ha-sdr`. Son SHA-256 est `32b3619e975eaeb0606252b4cdca9f3d2402854193f88619cd4bde383b30e1f9`.
  - **Nouveau capteur « Téléphone admin »** : catégorie diagnostic, unique_id `<entry_id>_admin_notify_target`. Son état et son attribut `notify_service` valent la cible, ou `unknown` (None) si elle n'est pas définie.
  - **À l'installation**, la cible est préremplie avec la valeur publiée par une intégration sœur (Sentinel Report, Deferred Restart, Partition Map, Package Keeper). Plusieurs valeurs différentes donnent une liste de choix. Sans aucune valeur, ce sont les services `notify.mobile_app_*` puis les entités notify de l'app mobile qui sont proposés.
  - **La valeur est copiée dans `entry.data`**. Elle survit à la suppression d'une sœur, et l'options flow la modifie. Entity Inventory n'écrit jamais dans une autre intégration.
  - **Deux formes de cible sont acceptées**, un service `notify.mobile_app_*` ou une entité notify. L'envoi passe par `async_notify_admin`, qui ne bloque jamais une alerte en cas d'échec.
- **`ruff.toml`**, avec les mêmes règles que `ha-sdr`.
- **`VERSION`**, `CHANGELOG.md`, `ROADMAP.md` et `CLAUDE.md`.

### Modifié
- **L'option « Téléphone à prévenir » (`notify_entity`) devient « Téléphone admin » (`admin_notify_target`).** Elle est rangée dans `entry.data` au lieu des options.
- **Consigne d'initiative de l'en-tête.** La réponse de l'IA **commence** par signaler les packages cassés, les nomme **tous** (en commençant par le chauffage et la sécurité), puis **se termine** en proposant de les corriger. Un test réel avec Copilot avait montré une alerte placée en fin de réponse, incomplète et sans proposition de correction.
- **Le scanner de packages ignore les clés `example`**, c'est-à-dire les valeurs d'exemple des champs de script. On évite ainsi un faux « missing », comme `sensor.entite_manquante` dans `watchman_scripts`. Les clés `default` restent analysées, parce qu'une valeur par défaut peut servir à l'exécution.

### Migration
- **Entrée de config 1.1 → 1.2.** `options["notify_entity"]` est déplacé vers `data["admin_notify_target"]` avec la même valeur, et l'ancienne clé est retirée des options. Sans téléphone réglé, la cible vaut None. Rien n'est à ressaisir.

## [0.8.1] - 2026-11-18
- Export ciblé : les packages cassés sont toujours listés, et les compteurs de pièces et d'étages sont corrects.

## [0.8.0] - 2026-11-18
- Un bouton d'export par pièce, rangé dans la pièce, qui suit les créations, renommages et suppressions.

## [0.7.1] - 2026-11-17
- L'IA signale d'elle-même les packages cassés (consigne d'initiative).

## [0.7.0] - 2026-11-15
- Export ciblé par pièces, étages, étiquettes et domaines (action `export`, `write: false`).
- README en anglais et en français.

## [0.6.0] - 2026-11-15
- Section `packages` (defines / missing / disabled), `meta.ha_state` (démarrage), passerelles sans entrée.

## [0.5.4] - 2026-11-14
- Consigne sur les mises à jour durcie après un test réel.

## [0.5.3] - 2026-11-14
- Dissuader l'automatisation des mises à jour (consigne et avertissement de `validate`).

## [0.5.2] - 2026-11-14
- Passerelle des appareils (`via`), vérification du dossier de destination, alerte en cas d'export raté.

## [0.5.1] - 2026-11-14
- Notifications pour les actions requises, version de l'intégration dans `meta`.

## [0.5.0] - 2026-11-14
- Cohabitation avec Watchman (réparation en un clic), export dans `/share` par défaut.

## [0.4.0] - [0.4.3] - 2026-11-11 / 2026-11-12
- Action `entity_inventory.validate` et consignes pour l'IA. Elle accepte un fichier (`path`), détecte une entité notify appelée comme une action, et ne renvoie plus « valid: true » quand rien n'a été vérifié.

## [0.3.0] - 2026-11-11
- Adresses e-mail masquées, sortie allégée.

## [0.2.0] - 2026-11-11
- Filtres configurables, noms courts, correction des alias.

## [0.1.0] - 2026-11-11
- Première version : export YAML de la structure de Home Assistant pour une IA.
