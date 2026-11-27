# Feuille de route

## Fait
- **0.10.0**, panneau latéral : générer (complet ou ciblé), télécharger, copier, packages cassés signalés.
- **0.9.0**, convention « Téléphone admin » :
  - module commun `admin_phone.py` 1.1.0 ;
  - migration 1.1 → 1.2 ;
  - consigne d'initiative resserrée ;
  - clés `example` ignorées par le scanner.

## Prochaines versions
- **0.11.0, fichier des intégrations** (`entity_inventory_integrations.yaml`, décisions de Mathieu du 2026-11-25). But : qu'une IA sache exactement quelle intégration est installée et puisse lire son code source à la bonne adresse, sans recherche web qui la ferait confondre deux intégrations aux noms proches.
  - **Une fiche d'identité par intégration** : domaine, nom lisible, version, native ou personnalisée, mode de configuration (interface ou YAML), `iot_class`, entrées de configuration (titre masqué comme dans l'export principal, état), actions proposées avec leurs champs, réparations ouvertes.
  - **Provenance tirée du manifest uniquement** (pas des données internes de HACS) : `documentation`, `issue_tracker`, `codeowners`. Pour une intégration native, lien direct vers `homeassistant/components/<domaine>` du dépôt `home-assistant/core` à la version installée de HA.
  - **Entités** : seulement le nombre d'actives (elles sont déjà dans l'export principal) ; liste complète des **désactivées**, avec la raison (`user` ou `integration`, donc activable), pour que l'IA puisse recommander leur activation.
  - **Jamais** les options ni les données des entrées de configuration (jetons, mots de passe).
  - **Index en tête** avec le numéro de ligne de chaque fiche, et numéro de ligne de l'index à la fin de chaque fiche (lecture partielle par une IA qui lit les fichiers elle-même ; écriture en deux passes).
  - **Consigne dans l'export principal** : ne demander ce fichier à l'humain que si la question porte sur une intégration.
  - **Export ciblé par intégration** (une seule fiche), sur le modèle de l'export ciblé par pièce ou par domaine.
  - **Dans le panneau** : générer, télécharger et copier ce fichier comme l'inventaire.
- **Soumission à hacs/default.** Mathieu doit soumettre la PR lui-même, depuis son compte.
- **Suivre les évolutions du module `admin_phone`.** Entity Inventory est l'intégration désignée pour publier les nouvelles versions dans `ha-sdr`, puis les recopier.

## Intégrations liées
- **Package Keeper**, dépôt `ha-package-keeper`, domaine `package_keeper` : une intégration séparée qui écrit les packages proposés par une IA, avec un panneau réservé aux administrateurs. Entity Inventory reste en lecture seule.
- **Sentinel Report, Deferred Restart et Partition Map** : elles reprennent `admin_phone.py` depuis `ha-sdr`.

## Idées
- Hors-série Substack « Local first ne veut pas dire confidentiel ».
