# Entity Inventory

🇬🇧 [English](README.md) · 🇫🇷 **Français**

[![Validate](https://github.com/systemedomotiqueresilient/ha-entity-inventory/actions/workflows/validate.yml/badge.svg)](https://github.com/systemedomotiqueresilient/ha-entity-inventory/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/systemedomotiqueresilient/ha-entity-inventory)](https://github.com/systemedomotiqueresilient/ha-entity-inventory/releases)

**Donnez à une IA le plan de votre maison, pas les clés.**

Entity Inventory exporte la *structure* de votre Home Assistant — étages, pièces, appareils, entités et les valeurs qu'elles acceptent — dans un fichier YAML compact. Vous le joignez à une conversation avec l'IA de votre choix pour qu'elle rédige automatisations, scripts ou packages avec les **bons `entity_id`** et les **bons modes**, sans qu'elle ait le moindre accès à votre instance.

- 🔒 **Aucun accès distant** : pas de MCP, pas de jeton, pas d'API ouverte. L'IA ne voit qu'un fichier que vous relisez.
- 🧹 **Aucune donnée de vie privée** : ni états, ni historique, ni coordonnées GPS, ni IP. Les attributs passent par une liste blanche.
- 🧠 **Pensé pour les LLM** : hiérarchie pièce → appareil → entité, listes compactes, en-tête qui explique à l'IA comment lire le fichier.

## Installation

### Marketplace (Home Assistant 2026.11+)

*Paramètres → Marketplace* → rechercher **Entity Inventory** → Installer.

Tant que l'intégration n'est pas dans le catalogue par défaut : *Marketplace → ⋮ → Dépôts personnalisés* → `https://github.com/systemedomotiqueresilient/ha-entity-inventory`, type **Intégration**.

### HACS (avant 2026.11)

[![Ouvrir dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=systemedomotiqueresilient&repository=ha-entity-inventory&category=integration)

Ou *HACS → ⋮ → Dépôts personnalisés* → l'URL du dépôt, type **Intégration**.

### Manuelle

Copier `custom_components/entity_inventory/` dans `/config/custom_components/` et redémarrer.

## Configuration

*Paramètres → Appareils et services → Ajouter une intégration → Entity Inventory*, puis choisir le fichier de sortie :

- défaut : `/share/entity_inventory.yaml` sur HAOS / Supervised (accessible par Samba, hors de portée de Watchman), `/config/entity_inventory.yaml` sinon ;
- chemin relatif = relatif à `/config`, chemin absolu accepté (ex. `/share/entity_inventory.yaml`) ;
- **`/config/www` est refusé** : ce dossier est servi sans authentification sur `/local/`.
- le dossier est vérifié dès la saisie : hors de `/config`, il doit déjà exister (sur une installation Docker ou Core, `/share` n'existe pas et n'est jamais créé). Sous `/config`, un sous-dossier manquant est créé au premier export.

| Option | Défaut | Effet |
|---|---|---|
| Inclure les entités de configuration | non | calibrations, mode LED, boutons « vérifier la mise à jour »… |
| Inclure les entités de diagnostic | non | signal, LQI, tension, dernière vue… — **les batteries sont toujours gardées** |
| Intégrations à exclure | aucune | ex. `proxmoxve`, `sentinel`, `sentinel_report` : aucune de leurs entités n'est exportée |
| Masquer les adresses e-mail | oui | toute adresse présente dans un nom devient `[email]` |
| Analyser les packages | oui | liste les fichiers de packages, ce qu'ils créent et ce qu'ils citent qui n'existe plus |
| Un bouton d'export par pièce | oui | un bouton rangé dans chaque pièce, affiché par les tableaux de bord des pièces |
| Téléphone admin | prérempli si une autre intégration SDR en a déjà un | service `notify.mobile_app_*` ou entité `notify.*` (app Compagnon) prévenu quand une action est requise |

Le fichier indique dans `meta.filters` et `meta.counts.excluded` ce qui a été filtré : l'IA sait qu'une entité absente peut exister. Les entités désactivées ne sont jamais listées (seulement comptées).

Ordre de grandeur sur une installation réelle de 2 400 entités : **470 Ko → 170 Ko** (≈ 146k → 55k tokens) avec les filtres par défaut, **≈ 135 Ko** (≈ 42k tokens) en excluant en plus les intégrations de surveillance. Un export ciblé sur une pièce tient en quelques Ko.

Tout se modifie ensuite via *Configurer*.

### Téléphone admin, commun aux intégrations SDR

Entity Inventory partage une convention avec les autres intégrations SDR (Sentinel Report, Deferred Restart, Partition Map…) : chacune crée sa propre entité **Téléphone admin** (capteur de diagnostic) qui indique où elle envoie ses alertes.

- **À l'installation**, le champ est prérempli avec le téléphone déjà choisi dans une autre intégration SDR. S'il y en a plusieurs différents, ils sont proposés au choix. S'il n'y en a aucun, ce sont les téléphones de l'application Companion qui sont proposés.
- **La valeur est copiée dans Entity Inventory.** Supprimer l'intégration qui l'avait proposée ne la fait pas perdre, et vous pouvez la changer à tout moment via *Configurer*.
- **Lecture seule** : Entity Inventory lit l'entité des autres intégrations, mais n'y écrit jamais.
- **Mise à jour depuis la 0.8.x** : le « téléphone à prévenir » déjà réglé est repris automatiquement, sans rien ressaisir.

## Utilisation

- le bouton **Exporter l'inventaire** (son état indique la date du dernier export) ;
- un bouton **Exporter l'inventaire *Pièce*** dans chaque pièce, qui produit l'export ciblé de cette pièce (`entity_inventory_salle_de_bain.yaml`). Il est rangé dans sa pièce : les tableaux de bord automatiques et celui des pièces l'affichent sans carte à ajouter. Les boutons suivent les pièces (création, renommage, suppression) ; un bouton déplacé à la main n'est jamais remis en place de force ;
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

Si un export échoue (dossier disparu, disque en lecture seule…), une **notification persistante** l'indique, et le téléphone admin est prévenu : sans cela, un export nocturne raté passerait inaperçu et l'IA travaillerait sur un inventaire périmé. Le dossier est aussi contrôlé à chaque démarrage. Une seule alerte par situation ; elle disparaît au premier export réussi.

### Export ciblé

Pour ne confier à l'IA que ce dont elle a besoin, l'action accepte une cible :

```yaml
action: entity_inventory.export
data:
  areas: [salle_de_bain]      # pièces (area_id)
  floors: [etage]             # étages : toutes leurs pièces
  labels: [chauffage]         # étiquettes portées par l'entité ou son appareil
  domains: [climate]          # domaines d'entités
```

- Dans un même critère, une valeur suffit (`areas: [wc, couloir]` = l'une ou l'autre) ; entre critères, tous doivent être remplis (`areas` + `domains` = les thermostats de ces pièces).
- Le résultat va dans un **fichier séparé** nommé d'après la cible (`entity_inventory_salle_de_bain.yaml`) : l'export complet n'est pas modifié.
- L'en-tête complet est conservé, et `meta.scope` indique à l'IA que l'inventaire est **partiel** : elle sait qu'une entité absente peut exister ailleurs, et qu'il faut l'export complet pour une catégorie entière ou pour repérer un conflit.
- Les packages qui créent ou citent une entité de la cible sont listés, ainsi que **tous les packages cassés** de l'installation : une sonde disparue ne peut plus être rattachée à une pièce, et un package cassé ne doit pas passer inaperçu dans un extrait.
- Une pièce, un étage ou une étiquette inconnus sont refusés avec la liste des valeurs possibles, plutôt que de produire un fichier vide.
- `write: false` n'écrit rien : l'inventaire est seulement renvoyé dans la réponse de l'action, à copier depuis les outils de développement.

Le débutant donne l'export complet ; l'utilisateur plus avancé choisit ce qu'il transmet.

Puis, dans la conversation avec l'IA : *« Voici l'inventaire de ma maison. Écris un package qui passe tous les radiateurs de l'étage en eco quand l'alarme est armée. »*

## Cohabitation avec Watchman

[Watchman](https://github.com/dummylabs/thewatchman) parcourt les fichiers `.yaml` de `/config` et signale toute entité citée qui est introuvable, indisponible ou inconnue. Un export placé dans `/config` y ajouterait des centaines de faux positifs (boutons, scènes, synthèse vocale… sont normalement `unknown`).

- Par défaut sur HAOS, l'export va dans `/share` : Watchman ne le voit pas.
- Si vous choisissez un chemin dans `/config` et que Watchman est installé, une **réparation** apparaît (*Paramètres → Système → Réparations*). Après confirmation, Entity Inventory ajoute aux fichiers ignorés de Watchman un motif qui couvre l'export complet et les exports ciblés (`entity_inventory*.yaml`). Une exception posée avant la 0.7.0 avec le chemin exact est remplacée par ce motif via la même réparation. Si vous changez le chemin plus tard, la réparation revient et remplace l'ancien chemin.
- Pour ne pas la manquer parmi d'autres réparations, une **notification persistante** (avec un lien vers les réparations) est créée, et, si vous avez choisi un **téléphone admin** dans les options, il reçoit une notification. Une seule fois par situation : pas de relance à chaque export ou redémarrage.
- Rien n'est jamais modifié dans Watchman sans cette confirmation. Si son format de configuration n'est pas reconnu, rien n'est touché et la réparation l'indique.
- Les brouillons à valider peuvent aussi aller dans `/share/ia/` (`path: /share/ia/brouillon.yaml`) pour la même raison.

## Vérifier ce que l'IA a écrit

L'action `entity_inventory.validate` contrôle un YAML produit par une IA contre votre instance réelle. Deux façons de lui donner le YAML :

**1. Par fichier (recommandé).** Enregistrez la réponse de l'IA, par exemple dans `/config/ia/brouillon.yaml` (éditeur de fichiers, Samba…), puis dans *Outils de développement → Actions* :

```yaml
action: entity_inventory.validate
data:
  path: ia/brouillon.yaml
```

Le chemin est relatif à `/config` (ou absolu dans `/share`). Seuls les fichiers `.yaml`/`.yml` sont acceptés, jamais `secrets.yaml`.

Le fichier contient **uniquement** le YAML de l'IA (`alias:`, `triggers:`, `actions:`…), pas l'appel `action: entity_inventory.validate` ni de bloc `raw`. La réponse indique `entities_checked` et `actions_checked` : un YAML où rien n'a pu être vérifié est déclaré invalide plutôt que faussement correct.

**2. Par copier-coller.** Les outils de développement évaluent les templates `{{ … }}` *avant* d'appeler l'action : un YAML qui contient `{{ trigger.to_state.name }}` échoue avec `'trigger' is undefined`. Entourez-le d'un bloc `raw` :

```yaml
action: entity_inventory.validate
data:
  yaml: |
    {% raw %}
    triggers:
      - trigger: numeric_state
        entity_id: sensor.0x30fb10fffe74e11b_battery
        below: 15
    actions:
      - action: notify.send_message
        target:
          entity_id: notify.iphone
        data:
          message: "{{ trigger.to_state.name }} : {{ trigger.to_state.state }} %"
    {% endraw %}
```

La réponse liste, sans rien modifier :

- **erreurs** : entité ou action inexistante, entité appelée comme une action (ex. `action: notify.mon_telephone` au lieu de `notify.send_message`) (y compris dans les templates `states('…')`), `preset_mode` / `option` / `hvac_mode` hors des valeurs permises (avec la liste correcte), `off` non quoté interprété comme booléen, `numeric_state` sur une entité non numérique (`group.*`, `binary_sensor`…) ;
- **avertissements** : entité désactivée, action appliquée à une entité d'un autre domaine, syntaxe ancienne (`platform:`, `service:`, `trigger:` au lieu de `triggers:`…), **mise à jour automatisée** (`update.install`, `hassio.addon_update`, OTA Zigbee2MQTT), avec un avertissement renforcé pour `update.install` sur `all` ou sans cible, et sans `backup: true`.

> **Mises à jour : toujours une décision humaine.** Beaucoup de tutoriels proposent d'installer les mises à jour automatiquement, la nuit. Une mise à jour peut casser une intégration, exiger une migration ou un redémarrage : elle doit être lancée à la main, quand on peut réagir. L'en-tête de l'inventaire demande à l'IA de ne fournir aucun YAML d'installation dans sa première réponse, de proposer une notification « mise à jour disponible » et d'attendre une confirmation explicite ; la validation le signale par un avertissement. Rien n'est interdit : la décision reste à l'occupant.

Ce que la validation ne peut pas voir : une liste incomplète (« toutes les piles » à qui il en manque) ou une logique discutable. Relisez quand même.

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
        via: Coordinateur Zigbee   # passerelle : c'est là qu'on renomme ou supprime l'appareil
        entities:
          - id: climate.radiateur_salon
            hvac_modes: [heat, 'off']
            preset_modes: [comfort, eco, away, none]
unassigned:    # appareils / entités sans pièce
no_registry:   # entités YAML sans unique_id
packages:      # fichiers de packages : ce qu'ils créent, ce qu'ils citent qui a disparu
  derivee_wc:
    file: packages/derivee_wc.yaml
    description: Package : Dérivées WC        # première ligne de commentaire du fichier
    defines: [sensor.tdeg_wc_sonoff_package]
    missing: [sensor.0x00124b002a50b200_temperature]   # → package cassé
```

| Exporté | Jamais exporté |
|---|---|
| entity_id, nom, pièce, étage, étiquettes, alias | états courants, historique |
| appareil : nom, fabricant, modèle, intégration, passerelle (`via`) | coordonnées GPS, IP, attributs dynamiques |
| device_class, unité, state_class, catégorie | identifiants internes d'appareils |
| `options`, `hvac_modes`, `preset_modes`, `event_types`, min/max… | |

La liste blanche des attributs est dans [`const.py`](custom_components/entity_inventory/const.py).

> ⚠️ Les **noms** sont exportés tels quels (pièces, appareils, calendriers…). Certaines intégrations de surveillance nomment leurs capteurs d'après le titre des comptes qu'elles surveillent : les adresses e-mail sont masquées dans les noms, mais un `entity_id` peut en contenir une forme « slugifiée » (il doit rester exact pour l'IA). Excluez ces intégrations si besoin, et relisez le fichier avant de le partager.

## Packages

Une IA ne répare que ce qu'on lui montre. Quand une sonde est remplacée, tous les packages qui la citent cassent en silence, et rien n'indique à l'IA qu'ils existent. La section `packages` les lui désigne : pour chaque fichier déclaré dans `homeassistant: packages:` (quel que soit le dossier, `!include_dir_named`, `!include_dir_merge_named` ou bloc direct), elle donne :

- `defines` : les entités que le fichier crée (inutile de les recréer ailleurs, source des doublons en `_2`) ;
- `missing` : les entités citées qui **n'existent plus** ;
- `disabled` : les entités citées mais désactivées ;
- `description` : la première ligne de commentaire du fichier.

Le **contenu des fichiers n'est jamais exporté**, seulement leur nom et des `entity_id`. Les fichiers sont lus en lecture seule avec le chargeur de Home Assistant ; les valeurs de `!secret` ne sortent jamais. Si `configuration.yaml` est illisible, la section est omise (`meta.packages_error`) sans bloquer l'export.

### Convention de nommage conseillée

Deux habitudes rendent cette section bien plus utile, à l'IA comme à vous :

1. **Un nom de fichier qui dit la pièce et la fonction** : `wc_derivees.yaml`, `appartement_temperature_moyenne.yaml` plutôt que `derivee_wc.yaml` ou `test2.yaml`.
2. **Une première ligne de commentaire** qui décrit le package, reprise telle quelle :

```yaml
# Package : WC — dérivées de température et d'humidité (sonde SNZB-02P)
sensor:
  - platform: derivative
    ...
```

## État de démarrage

Un export lancé pendant le démarrage de Home Assistant (par exemple par une automatisation déclenchée au démarrage) peut être incomplet : entités YAML sans `unique_id` pas encore créées, quelques valeurs absentes. Il est marqué `meta.ha_state: starting`, et l'en-tête demande à l'IA de le signaler.

## Développement

```bash
pip install -r requirements_test.txt
pytest
```

Publier une version : créer une release GitHub taguée `vX.Y.Z`. Le workflow `release.yml` écrit la version dans `manifest.json` et attache `entity_inventory.zip`.

## Licence

MIT
