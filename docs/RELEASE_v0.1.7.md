# Release v0.1.7

## Objectif

Rendre l'expiration de session du portail m2A transparente pour Home Assistant.

## Changements

- renouvellement proactif de l'authentification après 90 minutes, avant la limite de session observée d'environ deux heures ;
- réutilisation automatique des identifiants déjà stockés dans la ConfigEntry Home Assistant ;
- verrou d'authentification pour éviter plusieurs logins simultanés lorsque le polling et la synchronisation historique rencontrent la même expiration ;
- prise en charge des expirations renvoyées en HTTP 401, 403, 419 ou 440 ;
- détection des redirections et pages HTML de login renvoyées à la place du JSON API ;
- purge de la session/cookies m2A avant création d'une nouvelle session ;
- rejeu automatique de la requête une seule fois après relogin ;
- une session rejetée après relogin est traitée comme une erreur temporaire de service, pas comme un mot de passe invalide ;
- la demande de réauthentification Home Assistant est désormais réservée aux identifiants réellement refusés par le endpoint de login.

## Impact

Aucun changement sur les entités, les statistiques Recorder, l'historique ou le numéro de compteur configuré.

La mise à jour est conçue pour être transparente : après installation de la v0.1.7 et redémarrage de Home Assistant, l'intégration continue avec la ConfigEntry existante.

## Qualité

La release doit être publiée uniquement après validation HACS et Hassfest.
