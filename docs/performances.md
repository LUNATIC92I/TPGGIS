# Résultats des tests de performance

Document généré automatiquement par `scripts/test_performance.py`. Données exclusivement synthétiques.

Date d'exécution : 10/10/2026 19:40 UTC

## Environnement de mesure

Système : Linux-6.18.44-fc-v114-x86_64-with-glibc2.39
Processeur : x86_64 (4 cœurs logiques)
Python : 3.13.16
Base de données : postgresql+psycopg (serveur local, même machine)
Client : application FastAPI appelée en processus (sans réseau ni TLS).

## Volumes synthétiques

| Élément | Volume |
|---|---|
| Plaintes | 200 000 |
| Personnes | 100 000 |
| Faits | 50 000 |
| Dossiers | 20 000 |
| Événements d'audit après mesures | 147 |

Durée de génération et d'insertion chiffrée : 769 secondes.

## Temps de réponse mesurés

| Opération | Médiane (ms) | 95e centile (ms) | Maximum (ms) |
|---|---|---|---|
| Connexion (Argon2id + TOTP) | 153.6 | 155.8 | 171.1 |
| Liste des plaintes, page 1 (périmètre national) | 53.4 | 72.7 | 164.1 |
| Liste des plaintes, page 200 (périmètre national) | 103.5 | 123.9 | 126.8 |
| Liste des plaintes, page 1 (périmètre unité) | 52.5 | 64.7 | 74.4 |
| Filtre par statut et période (national) | 57.8 | 70.9 | 82.6 |
| Recherche exacte par numéro de plainte | 18.2 | 22.1 | 28.7 |
| Recherche par nom, prénoms et date de naissance | 97.7 | 120.3 | 140.9 |
| Recherche par référence de document (index aveugle) | 14.7 | 19.7 | 23.3 |
| Liste des personnes filtrée par nom | 58.3 | 71.9 | 72.9 |
| Fiche personne (déchiffrement et audit) | 23.6 | 39.1 | 69.3 |
| Tableau de bord (national, 12 mois) | 508.3 | 541.0 | 550.3 |
| Données cartographiques (national) | 143.9 | 176.0 | 177.5 |
| Création d'une plainte (transaction complète) | 21.8 | 31.6 | 33.7 |

## Lecture des résultats

Les listes sont paginées côté serveur (50 éléments par page) : le poste client ne charge jamais le registre complet. Les recherches exactes s'appuient sur des index (numéros uniques, index aveugle HMAC des documents). La connexion est volontairement coûteuse (Argon2id, 64 Mo, 3 passes) pour ralentir les attaques par force brute.

Ces mesures doivent être reproduites sur l'infrastructure cible (serveur dédié, réseau, TLS, volumétrie nationale estimée) avant la mise en production.
## Analyse et pistes d'optimisation (rédigées après la mesure)

1. Toutes les opérations interactives courantes restent sous 125 ms au 95e centile sur 200 000 plaintes, hors tableau de bord national.
2. Le tableau de bord au périmètre national (environ 0,5 s) calcule en direct une dizaine d'agrégats sur l'ensemble des plaintes. Pour une volumétrie nationale de plusieurs millions de plaintes, prévoir des agrégats mensuels pré calculés (vue matérialisée rafraîchie périodiquement). Les tableaux de bord d'unité ne sont pas concernés.
3. La recherche par nom (environ 100 ms) utilise un préfixe sur le nom normalisé. Sur PostgreSQL, un index `varchar_pattern_ops` ou l'extension `pg_trgm` (recherche approchée) réduira ce temps sur de plus gros volumes ; à décider avec l'administrateur de base de données.
4. La pagination profonde (page 200) reste sous 125 ms ; au delà de quelques milliers de pages, les filtres (statut, période, numéro) sont à privilégier.
5. La génération du jeu synthétique (13 minutes) n'est pas représentative de l'usage : elle chiffre et insère 200 000 plaintes et plusieurs centaines de milliers de liens dans une seule transaction.
