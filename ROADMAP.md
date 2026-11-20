# Feuille de route

## Fait
- **0.9.0**, convention « Téléphone admin » :
  - module commun `admin_phone.py` 1.1.0 ;
  - migration 1.1 → 1.2 ;
  - consigne d'initiative resserrée ;
  - clés `example` ignorées par le scanner.

## Prochaines versions
- **0.10.0, panneau latéral** :
  - boutons Générer / Télécharger / Copier ;
  - réservé aux administrateurs, avec téléchargement authentifié.
- **Soumission à hacs/default.** Mathieu doit soumettre la PR lui-même, depuis son compte.
- **Suivre les évolutions du module `admin_phone`.** Entity Inventory est l'intégration désignée pour publier les nouvelles versions dans `ha-sdr`, puis les recopier.

## Intégrations liées
- **Package Keeper**, dépôt `ha-package-keeper`, domaine `package_keeper` : une intégration séparée qui écrit les packages proposés par une IA, avec un panneau réservé aux administrateurs. Entity Inventory reste en lecture seule.
- **Sentinel Report, Deferred Restart et Partition Map** : elles reprennent `admin_phone.py` depuis `ha-sdr`.

## Idées
- Hors-série Substack « Local first ne veut pas dire confidentiel ».
