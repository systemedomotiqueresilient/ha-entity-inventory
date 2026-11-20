# Entity Inventory : consignes pour les agents

Intégration Home Assistant (domaine `entity_inventory`). Elle exporte la structure de l'instance en YAML pour une IA, **sans aucun état**, et valide le YAML écrit par l'IA (action `validate`).

## Règles
- **Lecture seule** : on n'écrit jamais dans la configuration de l'occupant, dans une autre intégration ni dans l'entité d'une autre intégration. L'écriture de packages relève de Package Keeper, une intégration séparée.
- **Jamais de contenu de package ni de valeur `!secret` dans l'export.** Les adresses e-mail sont masquées par défaut.
- **Aucune donnée personnelle dans le dépôt public**, ni dans les README, les tests ou les messages de commit : pas d'e-mail, de nom d'appareil réel, d'IP ni de coordonnées. Les commits utilisent l'adresse GitHub noreply.
- **Ne jamais modifier le code de Sentinel ni de Spook.**
- **Mathieu pousse lui-même les commits de ce dépôt**, à partir des patches qu'on lui fournit (`git am`).

## Module commun `admin_phone.py`
- **Référence** : dépôt GitHub privé `systemedomotiqueresilient/ha-sdr`, fichier `admin_phone/admin_phone.py`.
- **Il est copié TEL QUEL ici.** Ne jamais le modifier dans ce dépôt : toute évolution se fait dans `ha-sdr`, avec une nouvelle `MODULE_VERSION`, une entrée au CHANGELOG et des tests, puis le fichier est recopié.
- **Vérifier la copie** : son SHA-256 doit être identique à celui de `ha-sdr`. Le test `test_module_copy_and_versions` le contrôle.
- **Entity Inventory est l'intégration désignée pour publier les évolutions du module.**
- **Synchronisation entre agents** : carnet Evernote dédié. Note 00 : le protocole. Note 01 : la spécification. Note 02 : le journal, où l'on ajoute ses entrées à la fin.
- **Convention** :
  - capteur de catégorie diagnostic, unique_id `<entry_id>_admin_notify_target` ;
  - état et attribut `notify_service` = la cible, ou None ;
  - valeur rangée dans `entry.data["admin_notify_target"]` ;
  - envoi par `async_notify_admin`.

## Versions
La version doit être identique dans `manifest.json`, `const.py` (`VERSION`) et le fichier `VERSION`. Un test le vérifie. Il faut aussi tenir à jour `CHANGELOG.md` et `ROADMAP.md`.

## Vérifications avant de livrer
```bash
python3 -m pytest -q --cov=custom_components/entity_inventory   # couverture ≥ 50 %
ruff check custom_components/
cd ../ha-core && python3 -m script.hassfest --action validate --integration-path ../ha-entity-inventory/custom_components/entity_inventory
```
