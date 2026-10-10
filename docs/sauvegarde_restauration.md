# Sauvegarde, restauration et reprise après incident

## 1. Contenu d'une sauvegarde

Chaque sauvegarde est un répertoire `tpgis_sauvegarde_AAAAMMJJTHHMMSSZ` en lecture seule contenant :

| Fichier | Contenu |
|---|---|
| `base.enc` | Export complet de la base (format personnalisé `pg_dump`, ou copie SQLite en démonstration), chiffré par blocs en AES 256 GCM |
| `stockage.tar.enc` | Archive du stockage des pièces (déjà chiffrées individuellement), chiffrée à nouveau |
| `manifeste.json` | Environnement, date, révision du schéma, empreintes SHA 256 (en clair et chiffrées), empreinte du dernier événement d'audit |
| `manifeste.hmac` | Sceau HMAC SHA 256 du manifeste, calculé avec la clé de sauvegarde |

La clé de sauvegarde (`TPGIS_CLE_SAUVEGARDE`) est distincte des clés de données. Le chiffrement par blocs authentifie chaque bloc et détecte toute troncature ou altération.

**Important** : la restauration exige aussi les clés de données (`TPGIS_CLES_DONNEES`, `TPGIS_CLE_INDEX`) en vigueur au moment de la sauvegarde. Les clés sont conservées dans le coffre de secrets, séparément des sauvegardes, avec leur historique.

## 2. Sauvegarde automatique

La minuterie `tpgis-sauvegarde.timer` déclenche chaque nuit `deployment/server/sauvegarde_quotidienne.sh`, qui :

1. réalise la sauvegarde (`tpgis-admin sauvegarder`) ;
2. vérifie aussitôt son intégrité (`tpgis-admin verifier-sauvegarde`) ;
3. vérifie la chaîne d'audit (`tpgis-admin verifier-audit`) ;
4. copie la sauvegarde vers `DESTINATION_HORS_SITE` si elle est définie ;
5. supprime les sauvegardes locales de plus de 14 jours (paramètre `RETENTION_LOCALE_JOURS`).

Une sauvegarde manuelle peut être lancée par l'administrateur technique depuis le client (Paramètres, Supervision, confirmation d'identité) ou en ligne de commande.

## 3. Protection des sauvegardes

1. Copie quotidienne hors site sur un support protégé contre la modification (stockage à rétention verrouillée, bande ou disque hors ligne) : une sauvegarde chiffrée ne protège pas contre sa propre suppression.
2. Règle 3 2 1 recommandée : trois copies, deux supports, une copie hors site.
3. Accès aux sauvegardes réservé au compte `tpgis` et aux opérateurs de sauvegarde ; fichiers en lecture seule.
4. Les empreintes du dernier événement d'audit inscrites dans les manifestes sont relevées périodiquement par l'auditeur.

## 4. Restauration

1. Arrêter le service : `systemctl stop tpgis-serveur`.
2. Vérifier la sauvegarde : `tpgis-admin verifier-sauvegarde /var/backups/tpgis/tpgis_sauvegarde_...`.
3. Restaurer : `tpgis-admin restaurer /var/backups/tpgis/tpgis_sauvegarde_... --confirmer`.
   La commande contrôle le sceau du manifeste et chaque empreinte, refuse une sauvegarde provenant d'un autre environnement, restaure la base (`pg_restore --clean --single-transaction`) puis le stockage des pièces, et trace l'opération dans le journal d'audit.
4. Contrôler : `tpgis-admin verifier-audit`, démarrage du service, `/api/v1/sante`, consultation d'une plainte et téléchargement d'une pièce par un utilisateur habilité.
5. Consigner l'opération (date, sauvegarde utilisée, durée, contrôles) dans le registre d'exploitation.

## 5. Tests de restauration réalisés

| Essai | Base | Résultat |
|---|---|---|
| Test automatisé `test_sauvegarde_puis_restauration` : création de données après sauvegarde, suppression du stockage, restauration, relecture d'une pièce | SQLite et PostgreSQL 16 | Réussi : données revenues à l'état sauvegardé, pièce relue et vérifiée par SHA 256 |
| Test automatisé `test_sauvegarde_alteree_refusee` : altération d'un octet | SQLite et PostgreSQL 16 | Réussi : restauration refusée |
| Test automatisé `test_restauration_refusee_dans_un_autre_environnement` | SQLite et PostgreSQL 16 | Réussi : refus |
| Essai en ligne de commande : sauvegarde, suppression de liens en base, restauration | PostgreSQL 16 | Réussi : 0 lien après suppression, 94 liens après restauration, chaîne d'audit intègre |

Un test de restauration mensuel sur un serveur isolé est exigé en exploitation.

## 6. Stratégie de reprise après incident

| Objectif | Valeur cible proposée (à valider) |
|---|---|
| Perte de données maximale admissible | 24 heures avec la sauvegarde quotidienne ; 15 minutes avec l'archivage continu des journaux PostgreSQL (WAL) recommandé en production |
| Durée maximale d'interruption | 4 heures pour le site central |

Scénarios :

1. **Panne du serveur applicatif** : réinstallation par `installer_serveur.sh`, restauration de `/etc/tpgis` depuis le coffre, redémarrage ; la base n'est pas affectée.
2. **Corruption ou perte de la base** : restauration de la dernière sauvegarde intègre (ou restauration à un instant donné avec l'archivage WAL).
3. **Perte du site central** : serveur de secours sur un second site, restauration de la dernière copie hors site, bascule du nom DNS `tpgis.institution.td` ; les postes n'ont rien à reconfigurer.
4. **Compromission** : suivre le plan de réponse aux incidents ([securite.md](securite.md)), restaurer depuis une sauvegarde antérieure à la compromission, renouveler tous les secrets.
