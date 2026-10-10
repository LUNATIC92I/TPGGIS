# Architecture technique de TPGIS

## 1. Vue d'ensemble

TPGIS suit une architecture client serveur centralisée en trois niveaux.

| Niveau | Composant | Communique avec | Protocole et protection |
|---|---|---|---|
| Poste de travail | Client de bureau PySide6 (aucune donnée locale) | Proxy TLS du serveur central | HTTPS, TLS 1.2 minimum, certificat vérifié, jeton de session en mémoire |
| Frontal | nginx (terminaison TLS, filtrage réseau, taille des envois) | API sur la boucle locale | HTTP local uniquement (127.0.0.1) |
| Application | API FastAPI (contrôle d'accès, audit, chiffrement) | PostgreSQL, ClamAV, stockage des pièces | Connexion locale ; socket clamd ; fichiers chiffrés hors de tout répertoire web |
| Données | PostgreSQL 16 | Serveur applicatif seulement | Compte dédié, jamais exposé au réseau des postes |

1. **Client de bureau** (`tpgis/client`) : application PySide6 pour Windows 10 et 11. Elle n'accède qu'à l'API, en HTTPS avec vérification du certificat (autorité de certification de l'institution). Le jeton de session n'est conservé qu'en mémoire ; aucune donnée opérationnelle n'est écrite sur le poste, sauf les fichiers que l'utilisateur choisit explicitement d'enregistrer (exports, pièces).
2. **Serveur applicatif** (`tpgis/server`) : API REST FastAPI. Il porte toutes les règles métier et toutes les règles d'accès, le chiffrement des données sensibles, la journalisation d'audit, la numérotation, les contrôles de fichiers et la génération des documents.
3. **Base de données** PostgreSQL 16 : jamais exposée au réseau des postes ; seul le serveur applicatif s'y connecte, avec un compte dédié.

## 2. Organisation du code

```
tpgis/
  client/            application de bureau
    api_client/      client HTTP (erreurs réseau explicites) et exécution hors fil graphique
    map/             carte vectorielle du Tchad (Qt, sans navigateur) et couche de tuiles facultative
    widgets/         tableaux paginés, formulaires, graphiques
    windows/         fenêtre principale et 13 modules
    resources/       feuille de style QSS, icônes
  server/
    api/             routes (authentification, administration, opérations, analyse)
    services/        règles métier (plaintes, personnes, faits, dossiers, documents, biométrie,
                     recherche, statistiques, rapports, validations, conservation, sauvegarde, audit)
    security/        Argon2id, TOTP, jetons, chiffrement AES 256 GCM, index aveugles
    middleware/      trace, en têtes de sécurité, limitation de débit
    database/        modèles, migrations Alembic, initialisation, données synthétiques
    cli.py           outil d'administration (tpgis-admin)
  shared/            énumérations, permissions et rôles initiaux, schémas Pydantic, données géographiques
tests/               unit, integration, security, client
deployment/          windows (PyInstaller, Inno Setup), server (systemd, nginx, nftables, PostgreSQL)
scripts/             démonstration, certificats de démonstration, données cartographiques, performances
docs/                documentation
```

L'arborescence proposée dans le cahier des charges a été conservée dans son esprit. Les dossiers `repositories` et `schemas` séparés n'ont pas été multipliés : l'accès aux données passe par SQLAlchemy dans la couche `services`, ce qui garde au même endroit la requête et le filtre de périmètre qui la protège.

## 3. Modèle de données

Toutes les clés primaires sont des identifiants UUID (portables entre sites). Les horodatages sont en UTC.

| Domaine | Tables | Points clés |
|---|---|---|
| Organisation | `unites`, `roles`, `role_permissions`, `utilisateurs`, `sessions` | Unités hiérarchiques (Police, Gendarmerie), rôles configurables, sessions révocables (empreinte du jeton seulement) |
| Plaintes | `plaintes`, `plainte_personnes` | Numéro unique `PL-<unité>-<année>-<séquence>`, statut, motif, verrouillage optimiste par version |
| Personnes | `personnes` | Identifiant interne `P-<année>-<séquence>`, champs facultatifs, index aveugle du document, statut de fusion |
| Faits | `categories_faits`, `faits`, `fait_personnes` | Référentiel administrable, nature de l'information (rapporté, vérifié, soupçon, décision judiciaire) |
| Procédures | `dossiers`, `dossier_plaintes`, `dossier_personnes`, `actes_procedure` | Enquêteur désigné, actes, clôture motivée |
| Pièces | `documents`, `document_versions` | Versions, SHA 256, statut antivirus, chemin opaque, clé de chiffrement |
| Biométrie | `captures_biometriques` | Référence opaque chiffrée, fondement juridique, consentement, durée de conservation |
| Traçabilité | `journal_audit`, `historique_modifications` | Journal chaîné non modifiable ; historique des changements par entité |
| Administration | `demandes_validation`, `parametres`, `compteurs`, `metadonnees_instance` | Double validation, paramètres typés, numérotation, environnement de la base |

**Données chiffrées au repos** (AES 256 GCM, trousseau avec rotation) : description et observations des plaintes, témoins non identifiés, coordonnées et numéro de document des personnes, observations des dossiers, résumés d'actes, descriptions des faits, observations des liens, secrets TOTP, références de modèles biométriques et contenu de toutes les pièces. Les noms et dates de naissance restent en clair pour permettre la recherche ; ils sont protégés par le cloisonnement réseau, les droits PostgreSQL et le chiffrement du disque du serveur (voir [securite.md](securite.md)).

## 4. Contrôle d'accès

Le contrôle combine des rôles (RBAC) et des attributs (ABAC) ; il est exécuté par le serveur pour chaque requête.

1. **Permission** : chaque route exige une permission fine (`plainte.lire`, `biometrie.verifier`, `export.realiser`...). Le catalogue complet figure dans `tpgis/shared/permissions.py`. Les rôles sont des ensembles de permissions administrables.
2. **Périmètre** de l'utilisateur : `ASSIGNES` (éléments attribués), `UNITE`, `UNITE_ET_SUBORDONNEES` ou `NATIONALE`. Toutes les requêtes de lecture appliquent le filtre de périmètre correspondant (`tpgis/server/services/contexte.py`). Un élément hors périmètre est traité comme inexistant (réponse 404), sans révéler son existence ; la tentative est journalisée.
3. **Type de session** : une session ouverte avec un mot de passe à changer ou sans second facteur obligatoire n'autorise que l'opération de mise en conformité.
4. **Finalité** : consultations de fiches personnes, biométrie et recherches exigent une finalité déclarée, enregistrée dans l'audit.
5. **Confirmation d'identité récente** (5 minutes) pour les opérations critiques : exports, réinitialisation de mot de passe ou de MFA, modification des rôles et des paramètres, décisions de double validation, sauvegarde.
6. **Double validation** par un second responsable distinct pour : attribution d'un rôle privilégié, fusion de fiches personnes, suppression d'une capture biométrique, purge des données échues.

| Rôle initial | Périmètre par défaut | Ce qu'il peut faire | Ce qu'il ne peut pas faire |
|---|---|---|---|
| Administrateur technique | Unité | Paramètres techniques, sauvegardes, supervision | Consulter plaintes, personnes, dossiers, audit |
| Administrateur fonctionnel | Nationale | Comptes, rôles, unités, référentiel des faits, validations | Consulter les données opérationnelles |
| Responsable d'unité | Unité et subordonnées | Pilotage, clôture, archivage, exports, statistiques | Biométrie, enregistrement de personnes |
| Officier ou agent habilité | Unité | Traitement complet, biométrie simulée en vérification 1 pour 1 | Exports, administration |
| Agent d'accueil | Unité | Enregistrer plaintes et personnes, déposer des pièces | Biométrie, modification, clôture |
| Enquêteur | Éléments attribués | Dossiers et plaintes qui lui sont attribués | Le reste de l'unité, réattribution |
| Consultation seule | Unité | Lecture et statistiques | Toute écriture, fiches personnes |
| Auditeur | Nationale | Journal d'audit, comptes, statistiques | Modifier quoi que ce soit, données opérationnelles |

## 5. Flux principaux

1. **Connexion** : identifiant et mot de passe (Argon2id), puis code TOTP pour les rôles privilégiés ; verrouillage temporaire après 5 échecs, limitation par adresse IP, message identique pour un compte inconnu.
2. **Enregistrement d'une plainte** : validation stricte (champs inconnus refusés), numérotation transactionnelle verrouillée, liens aux personnes avec rôle procédural, historique et audit dans la même transaction.
3. **Création d'une personne** : détection des doublons multi attributs ; la création est suspendue tant que l'agent n'a pas décidé (utiliser la fiche existante ou créer malgré tout). Aucune fusion automatique.
4. **Dépôt d'une pièce** : extension autorisée, taille maximale, signature réelle du fichier, contrôle des archives bureautiques (macros, chemins, taille décompressée), analyse antivirus, chiffrement, empreinte SHA 256. Une pièce non confirmée saine n'est jamais téléchargeable.
5. **Statistiques et carte** : agrégats calculés en base sur le périmètre ; seuil de confidentialité configurable masquant les faibles effectifs.

## 6. Cartographie

La carte est rendue nativement par Qt (QGraphicsView), sans QtWebEngine. Les données géographiques sont simplifiées et embarquées (`tpgis/shared/geodata`, script de construction `scripts/construire_donnees_carte.py`, sources, licences, empreintes et limites dans `SOURCES.json`) : frontière nationale et 23 provinces conformes au découpage de 2018 (codes ISO 3166-2:TD, dont Ennedi Est et Ennedi Ouest) issues de geoBoundaries (données OpenStreetMap, licence ODbL 1.0, attribution affichée sur la carte), et 19 villes issues de Natural Earth (domaine public). Le script sait revenir à Natural Earth seul (22 unités) si les fichiers geoBoundaries ne sont pas fournis. Mode hors ligne par défaut ; un fond raster facultatif (serveur de tuiles institutionnel ou dossier local) peut être configuré dans `client.ini`. La carte ne représente que l'implantation des unités et des agrégats par province.

## 7. Choix techniques et justifications

| Choix | Justification |
|---|---|
| Jetons de session opaques stockés par empreinte | Révocation immédiate côté serveur (désactivation, changement de rôle), contrairement à des jetons autoporteurs |
| Chiffrement applicatif AES 256 GCM par champ | Protège les champs sensibles même en cas de copie de la base ; rotation de clés par identifiant |
| Index aveugle HMAC pour les documents d'identité | Recherche exacte sans stocker le numéro en clair |
| Journal d'audit chaîné et déclencheurs PostgreSQL | Toute altération est détectable ; modification et suppression bloquées en base |
| Verrouillage optimiste (version) | Empêche l'écrasement silencieux d'une modification concurrente |
| Carte Qt native | Fonctionne hors ligne, sans moteur web embarqué |
| Appels réseau hors du fil graphique | L'interface reste réactive ; erreurs réseau explicites |
| SQLite limité aux tests et à la démonstration | Refusé par la configuration de production |
