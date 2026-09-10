# Release v0.1.5

## Objectif

Première version publique stabilisée de l'intégration Home Assistant **m2A Eau** pour le portail Eaupla!/Service des Eaux de Mulhouse Alsace Agglomération.

## Fonctionnalités

- configuration 100 % via l'interface Home Assistant ;
- authentification automatique au portail m2A ;
- sélection stricte d'un compteur par son numéro physique ;
- récupération de l'index officiel et de la dernière télérelève ;
- consommation journalière et mensuelle ;
- comparaison N / N-1 ;
- import historique complet, du plus récent vers le plus ancien ;
- reprise tolérante des mois indisponibles ;
- statistiques longues durées Recorder pour le tableau de bord Énergie / Eau ;
- bouton d'actualisation forcée ;
- bouton de resynchronisation complète de l'historique ;
- protections de confidentialité pour ignorer tout abonnement ne correspondant pas au compteur configuré.

## Packaging public

- dépôt compatible HACS ;
- `hacs.json` ;
- métadonnées `manifest.json` complètes ;
- traduction française et anglaise ;
- branding local ;
- README public ;
- changelog ;
- licence MIT ;
- guides de contribution, sécurité et publication ;
- templates d'issues et de pull requests.

## Qualité

Validation GitHub Actions sur la branche `dev` :

- **HACS : OK** ;
- **Hassfest : OK**.

Le manifest déclare explicitement la dépendance `recorder` et respecte l'ordre de clés attendu par Hassfest (`domain`, `name`, puis ordre alphabétique).

## Publication

La branche `main` contient la version stable `0.1.5`. Le workflow de publication crée automatiquement la GitHub Release `v0.1.5` à partir de cette note de release si elle n'existe pas déjà.
