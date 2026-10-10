# Installation

Ce document décrit l'installation du serveur central sur une infrastructure institutionnelle sécurisée, puis l'installation du client sur les postes Windows. Aucune donnée réelle ne doit être chargée avant la réalisation des conditions décrites dans [conditions_mise_en_production.md](conditions_mise_en_production.md).

## 1. Prérequis du serveur central

| Élément | Recommandation |
|---|---|
| Système | Debian 12 ou Ubuntu Server 24.04 LTS, à jour, sans interface graphique |
| Processeur et mémoire | 4 cœurs et 16 Go au minimum pour un site national pilote ; à dimensionner selon [performances.md](performances.md) |
| Disques | Volume système et volume de données distincts, chiffrés (LUKS), RAID 1 ou mieux |
| Logiciels | Python 3.12, PostgreSQL 16, nginx, ClamAV (clamd), rsync |
| Horloge | Synchronisation NTP obligatoire (codes TOTP et horodatage de l'audit) |
| Réseau | Serveur dans une zone réseau institutionnelle, sans exposition directe à Internet |

## 2. Ports et flux réseau

| Port | Service | Ouvert à |
|---|---|---|
| 443/tcp | nginx (HTTPS, API) | Réseaux des commissariats, brigades et directions autorisés uniquement |
| 80/tcp | Redirection vers HTTPS | Facultatif, mêmes réseaux |
| 8000/tcp | API TPGIS (uvicorn) | Boucle locale 127.0.0.1 uniquement |
| 5432/tcp | PostgreSQL | Boucle locale, ou réseau privé d'administration si la base est sur un hôte distinct (TLS obligatoire) |
| 3310/tcp ou socket | ClamAV clamd | Boucle locale ou socket Unix |
| 22/tcp | SSH d'administration | Postes d'administration désignés uniquement, par clé |

Le fichier `deployment/server/pare-feu.nft` fournit un modèle nftables appliquant ces règles. **Le port PostgreSQL n'est jamais exposé à Internet ni au réseau des postes.**

## 3. Comptes de service

| Compte | Rôle | Droits |
|---|---|---|
| `tpgis` (système) | Exécute l'API et les sauvegardes | Lecture du code, écriture dans `/var/lib/tpgis` et `/var/backups/tpgis` uniquement ; aucun shell |
| `tpgis_proprio` (PostgreSQL) | Propriétaire du schéma, utilisé pour les migrations | DDL ; pas de connexion applicative courante |
| `tpgis_app` (PostgreSQL) | Compte de l'application | SELECT, INSERT, UPDATE, DELETE sur les tables ; sur `journal_audit` : INSERT et SELECT uniquement |
| `clamav` | Démon antivirus | Lecture des flux transmis par l'API |

Les secrets (mots de passe PostgreSQL, clés de chiffrement) sont détenus par au moins deux dépositaires désignés (principe du double contrôle) et ne sont jamais stockés dans le dépôt de code.

## 4. Installation du serveur

1. Copier le dépôt sur le serveur puis exécuter en root :
   `deployment/server/installer_serveur.sh`
   Le script crée le compte `tpgis`, les répertoires aux droits restreints, l'environnement Python avec les dépendances verrouillées, et installe les unités systemd et la configuration nginx.
2. Créer la base et les comptes PostgreSQL en suivant `deployment/server/postgresql_recommandations.conf` (authentification `scram-sha-256`, écoute locale).
3. Générer les clés : `sudo -u tpgis /opt/tpgis/venv/bin/tpgis-admin generer-cles`. Les déposer dans le coffre de secrets de l'institution et dans `/etc/tpgis/tpgis.env` (droits 640, propriétaire root, groupe tpgis). Le modèle commenté est `.env.example`.
4. Installer les certificats TLS émis par l'infrastructure de gestion de clés de l'institution dans `/etc/tpgis/tls/` (`serveur.crt`, `serveur.key` en droits 600). Recommandation forte : activer l'authentification mutuelle des postes par certificat client (lignes `ssl_verify_client` de `nginx-tpgis.conf`).
5. Configurer ClamAV : mise à jour des signatures depuis un miroir institutionnel (freshclam), socket `/run/clamav/clamd.ctl`, compte `tpgis` membre du groupe `clamav`.
6. Initialiser l'instance avec le compte propriétaire du schéma :
   `tpgis-admin initialiser` (migrations, rôles initiaux, marquage de la base en environnement `production`).
7. Créer le premier administrateur fonctionnel (amorçage unique, mot de passe saisi au clavier) :
   `tpgis-admin creer-administrateur --identifiant <identifiant> --nom <NOM> --prenoms <Prénoms>`
   Il devra changer son mot de passe et enrôler son second facteur à la première connexion.
8. Démarrer : `systemctl enable --now tpgis-serveur tpgis-sauvegarde.timer` puis `systemctl reload nginx`.
9. Contrôler : `curl https://tpgis.institution.td/api/v1/sante` doit répondre `"statut": "ok"`.

Au démarrage, le serveur **refuse de fonctionner en production** si : la base est SQLite, une clé manque, l'antivirus n'est pas clamd, l'adaptateur biométrique simulé est configuré, TLS n'est assuré ni directement ni par le proxy, la base appartient à un autre environnement, ou des données synthétiques sont présentes.

## 5. Installation des postes Windows 10 et 11

### 5.1 Construction de l'installateur (service informatique)

Sur un poste de construction Windows avec Python 3.12 et Inno Setup 6 :

```
powershell -ExecutionPolicy Bypass -File deployment\windows\construire.ps1 -Serveur https://tpgis.institution.td
```

Le script crée un environnement isolé, construit l'exécutable avec PyInstaller (`deployment/windows/tpgis_client.spec`) puis l'installateur `deployment/windows/sortie/TPGIS_Client_0.1.0_Installation.exe`, et affiche son empreinte SHA 256 à publier avec le paquet. Le workflow `.github/workflows/construction-windows.yml` réalise la même construction sur un exécuteur Windows. L'installateur doit être signé avec le certificat de signature de code de l'institution (ligne `SignTool` de `installateur.iss`).

### 5.2 Déploiement sur les postes

1. Exécuter l'installateur (droits administrateur), ou en silencieux : `TPGIS_Client_0.1.0_Installation.exe /VERYSILENT /SUPPRESSMSGBOXES`.
2. L'installateur dépose `client.ini` dans le dossier du programme avec l'adresse du serveur. Les paramètres facultatifs sont : `certificat_ca` (si l'autorité de l'institution n'est pas déjà dans le magasin Windows), `delai_secondes`, et la section `[carte]` pour un fond de carte raster validé.
3. Au lancement, le client vérifie la disponibilité du serveur et affiche un message clair s'il est injoignable ou si son certificat n'est pas reconnu. Il refuse toute adresse non chiffrée (`http://`).

## 6. Environnement de démonstration

Voir [demonstration.md](demonstration.md). L'environnement de démonstration utilise une base, des clés et un stockage distincts ; une base marquée `demonstration` ne peut pas être ouverte par un serveur de production.
