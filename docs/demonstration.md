# Environnement de démonstration

## 1. Séparation stricte avec la production

1. L'environnement `demonstration` utilise sa propre base (`var/demo`), ses propres clés (générées localement dans `var/cles_demonstration.json`, droits 600) et son propre stockage.
2. La base est marquée comme base de démonstration contenant des données synthétiques. Un serveur configuré en production refuse de l'ouvrir ; une sauvegarde de démonstration ne peut pas être restaurée en production.
3. Le chargement des données synthétiques est refusé sur une base de production.
4. Toutes les données sont **fictives** : noms combinés aléatoirement à partir de listes fictives, numéros de document préfixés `FICTIF`, téléphones marqués `(fictif)`, unités suffixées `(fictif)`, récits indiquant `récit fictif`, empreintes biométriques simulées. Aucune donnée réelle de citoyen n'a été collectée.
5. Les unités de démonstration sont placées sur les villes issues de Natural Earth ; elles ne correspondent pas à des implantations réelles.

## 2. Lancement

### 2.1 Sous Windows, en un clic : `TPGIS_Demonstration.exe`

Un exécutable unique, sans installation ni droits administrateur, regroupe le serveur, la base SQLite, le jeu de données fictif et le client.

1. Double cliquez sur `TPGIS_Demonstration.exe`. Un écran d'attente indique la progression ; le premier lancement crée les données fictives (quelques secondes).
2. L'écran de connexion propose une liste **Compte fictif** : choisissez un profil, cliquez sur **Remplir** (identifiant, mot de passe et code MFA courant sont renseignés), puis sur **Se connecter**.
3. Pour changer de profil, utilisez **Se déconnecter**. **Quitter** ferme le client et arrête le serveur local.

Fonctionnement :

| Élément | Comportement |
|---|---|
| Données | Dossier `%LOCALAPPDATA%\TPGIS_Demonstration` (base, clés locales, certificats, pièces, journal `demonstration.log`). Supprimer ce dossier remet la démonstration à zéro. |
| Réseau | Serveur HTTPS sur `127.0.0.1` uniquement, port libre choisi à chaque lancement, certificat de démonstration généré sur le poste ; aucune connexion vers l'extérieur |
| Séparation | Environnement `demonstration` : mentions « Chiffres fictifs » partout, base marquée synthétique et refusée par un serveur de production. L'aide **Compte fictif** n'existe que dans cet environnement. |
| Système | Windows 10 (version 1809 et suivantes) ou Windows 11, 64 bits. L'exécutable n'est pas signé : Windows SmartScreen peut afficher « Windows a protégé votre ordinateur » ; cliquez sur « Informations complémentaires » puis « Exécuter quand même », après avoir vérifié l'empreinte SHA 256 publiée avec le fichier. |

Construction : `deployment\windows\construire_demonstration.ps1` sur un poste Windows, ou le workflow `construction-windows.yml` (artefact `TPGIS-Demonstration-Windows`). Fichier de construction : `deployment/windows/tpgis_demonstration.spec`.

Cet exécutable est réservé à la démonstration et à la formation. Le déploiement institutionnel utilise le client seul (`TPGIS.exe` et son installateur) relié au serveur central.

### 2.2 Depuis les sources

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
