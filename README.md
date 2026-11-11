# Entity Inventory

[![Validate](https://github.com/GITHUB_USER/ha-entity-inventory/actions/workflows/validate.yml/badge.svg)](https://github.com/GITHUB_USER/ha-entity-inventory/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/GITHUB_USER/ha-entity-inventory)](https://github.com/GITHUB_USER/ha-entity-inventory/releases)

**Donnez à une IA le plan de votre maison, pas les clés.**

Entity Inventory exporte la *structure* de votre Home Assistant — étages, pièces, appareils, entités et les valeurs qu'elles acceptent — dans un fichier YAML compact. Vous le joignez à une conversation avec l'IA de votre choix pour qu'elle rédige automatisations, scripts ou packages avec les **bons `entity_id`** et les **bons modes**, sans qu'elle ait le moindre accès à votre instance.

- 🔒 **Aucun accès distant** : pas de MCP, pas de jeton, pas d'API ouverte. L'IA ne voit qu'un fichier que vous relisez.
- 🧹 **Aucune donnée de vie privée** : ni états, ni historique, ni coordonnées GPS, ni IP. Les attributs passent par une liste blanche.
- 🧠 **Pensé pour les LLM** : hiérarchie pièce → appareil → entité, listes compactes, en-tête qui explique à l'IA comment lire le fichier.

## Installation

### Marketplace (Home Assistant 2026.11+)

*Paramètres → Marketplace* → rechercher **Entity Inventory** → Installer.

Tant que l'intégration n'est pas dans le catalogue par défaut : *Marketplace → ⋮ → Dépôts personnalisés* → `https://github.com/GITHUB_USER/ha-entity-inventory`, type **Intégration**.

### HACS (avant 2026.11)

[![Ouvrir dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=GITHUB_USER&repository=ha-entity-inventory&category=integration)

Ou *HACS → ⋮ → Dépôts personnalisés* → l'URL du dépôt, type **Intégration**.

### Manuelle

Copier `custom_components/entity_inventory/` dans `/config/custom_components/` et redémarrer.

## Configuration

*Paramètres → Appareils et services → Ajouter une intégration → Entity Inventory*, puis choisir le fichier de sortie :

- défaut : `/config/entity_inventory.yaml` ;
- chemin relatif = relatif à `/config`, chemin absolu accepté (ex. `/share/entity_inventory.yaml`) ;
- **`/config/www` est refusé** : ce dossier est servi sans authentification sur `/local/`.

Le chemin se modifie ensuite via *Configurer*.

## Utilisation

- le bouton **Exporter l'inventaire** (son état indique la date du dernier export) ;
- ou l'action `entity_inventory.export`, qui renvoie le chemin et les compteurs.

Export automatique chaque nuit :

```yaml
automation:
  - alias: Inventaire nocturne
    triggers:
      - trigger: time
        at: "03:00:00"
    actions:
      - action: entity_inventory.export
```

Puis, dans la conversation avec l'IA : *« Voici l'inventaire de ma maison. Écris un package qui passe tous les radiateurs de l'étage en eco quand l'alarme est armée. »*

## Contenu du fichier

```yaml
meta:          # version HA, date, compteurs
floors:        # floor_id → nom, niveau
labels:        # label_id → nom
areas:         # area_id → appareils → entités (+ entités sans appareil)
  salon:
    name: Salon
    floor: rez_de_chaussee
    devices:
      - name: Radiateur salon
        manufacturer: NodOn
        integration: zha
        entities:
          - id: climate.radiateur_salon
            hvac_modes: [heat, 'off']
            preset_modes: [comfort, eco, away, none]
unassigned:    # appareils / entités sans pièce
no_registry:   # entités YAML sans unique_id
disabled:      # entités désactivées (à ne pas utiliser)
```

| Exporté | Jamais exporté |
|---|---|
| entity_id, nom, pièce, étage, étiquettes, alias | états courants, historique |
| appareil : nom, fabricant, modèle, intégration | coordonnées GPS, IP, attributs dynamiques |
| device_class, unité, state_class, catégorie | identifiants internes, titres des config entries |
| `options`, `hvac_modes`, `preset_modes`, `event_types`, min/max… | |

La liste blanche des attributs est dans [`const.py`](custom_components/entity_inventory/const.py).

> ⚠️ Les **noms** que vous avez donnés à vos pièces et appareils sont exportés tels quels. Relisez le fichier avant de le partager.

## Développement

```bash
pip install -r requirements_test.txt
pytest
```

Publier une version : créer une release GitHub taguée `vX.Y.Z`. Le workflow `release.yml` écrit la version dans `manifest.json` et attache `entity_inventory.zip`.

## Licence

MIT
