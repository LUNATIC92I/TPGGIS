# Environnement de démonstration

## 1. Séparation stricte avec la production

1. L'environnement `demonstration` utilise sa propre base (`var/demo`), ses propres clés (générées localement dans `var/cles_demonstration.json`, droits 600) et son propre stockage.
2. La base est marquée comme base de démonstration contenant des données synthétiques. Un serveur configuré en production refuse de l'ouvrir ; une sauvegarde de démonstration ne peut pas être restaurée en production.
3. Le chargement des données synthétiques est refusé sur une base de production.
4. Toutes les données sont **fictives** : noms combinés aléatoirement à partir de listes fictives, numéros de document préfixés `FICTIF`, téléphones marqués `(fictif)`, unités suffixées `(fictif)`, récits indiquant `récit fictif`, empreintes biométriques simulées. Aucune donnée réelle de citoyen n'a été collectée.
5. Les unités de démonstration sont placées sur les villes issues de Natural Earth ; elles ne correspondent pas à des implantations réelles.

## 2. Lancement

Linux : `./scripts/lancer_demo.sh` ; Windows : `scripts\lancer_demo.ps1`.

Le script génère une autorité de certification de démonstration (`var/tls`), démarre le serveur en HTTPS sur `127.0.0.1:8443`, charge le jeu synthétique au premier lancement (400 personnes, 600 plaintes, 250 faits, 120 dossiers, 40 captures simulées, 41 unités), affiche les codes MFA courants puis ouvre le client.

## 3. Comptes de démonstration

Mot de passe commun : `Demo-Tpgis-2026!`. Les comptes marqués MFA demandent un code : `python -m tpgis.server.cli codes-demo` affiche les codes courants (secrets TOTP publics de démonstration, définis dans `tpgis/server/database/seed/demonstration.py`).

| Identifiant | Rôle | Unité | MFA |
|---|---|---|---|
| `admin.technique` | Administrateur technique | Direction générale de la police (fictive) | Oui |
| `admin.fonctionnel` | Administrateur fonctionnel | Direction générale de la police (fictive) | Oui |
| `auditeur` | Auditeur autorisé | Direction générale de la police (fictive) | Oui |
| `responsable.ndj` | Responsable d'unité | Commissariat de N'Djamena et arrondissement | Oui |
| `officier.ndj` | Officier ou agent habilité | Commissariat de N'Djamena | Oui |
| `accueil.ndj` | Agent d'accueil | Commissariat de N'Djamena | Non |
| `enqueteur.ndj` | Enquêteur habilité | Commissariat de N'Djamena (dossiers attribués) | Oui |
| `consultation.ndj` | Consultation seule | Commissariat de N'Djamena | Non |
| `accueil.ndj.a1` | Agent d'accueil | Commissariat du 1er arrondissement | Non |
| `officier.abc` | Officier ou agent habilité | Commissariat d'Abéché | Oui |
| `accueil.abc` | Agent d'accueil | Commissariat d'Abéché | Non |
| `gendarme.mdo` | Agent d'accueil | Brigade de gendarmerie de Moundou | Non |

## 4. Scénarios suggérés

1. Connectez vous en `accueil.ndj`, enregistrez une plainte avec un plaignant : observez la numérotation et la détection de doublons.
2. Connectez vous en `officier.abc` : les plaintes de N'Djamena sont invisibles, y compris par recherche de numéro.
3. Connectez vous en `responsable.ndj` : tableau de bord, carte, export CSV (confirmation d'identité), clôture d'une plainte avec motif.
4. Connectez vous en `officier.ndj` : demandez une fusion de deux fiches ; approuvez la avec `responsable.ndj`.
5. Connectez vous en `auditeur` : retrouvez toutes ces actions dans le journal d'audit et vérifiez l'intégrité de la chaîne.
6. Connectez vous en `admin.technique` : constatez l'absence d'accès aux plaintes et aux personnes.
