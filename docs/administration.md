# Guide d'administration et d'exploitation

## 1. Répartition des responsabilités

| Fonction | Rôle TPGIS | Remarque |
|---|---|---|
| Comptes, rôles, unités, référentiel des faits | Administrateur fonctionnel | N'accède pas aux données opérationnelles |
| Paramètres techniques, sauvegardes, supervision | Administrateur technique | N'accède pas aux dossiers sensibles |
| Contrôle des traces | Auditeur autorisé | Lecture seule du journal |
| Double validation | Responsables désignés (permission `validation.approuver`) | Toujours une personne différente du demandeur |
| Secrets (clés, mots de passe de service) | Dépositaires désignés hors application | Double contrôle, coffre de secrets |

## 2. Outil d'administration `tpgis-admin`

| Commande | Usage |
|---|---|
| `generer-cles` | Produit un jeu de clés à placer dans le coffre de secrets |
| `migrer` | Applique les migrations de schéma |
| `initialiser` | Migre, crée les rôles initiaux et lie la base à son environnement |
| `creer-administrateur` | Amorçage du premier administrateur fonctionnel (une seule fois) |
| `charger-demonstration` | Données synthétiques (refusé en production) |
| `verifier-audit` | Vérifie l'intégrité de la chaîne du journal d'audit (code retour 2 en cas de rupture) |
| `sauvegarder` | Sauvegarde chiffrée de la base et du stockage |
| `verifier-sauvegarde DOSSIER` | Contrôle d'intégrité d'une sauvegarde |
| `restaurer DOSSIER --confirmer` | Restauration (écrase les données actuelles) |
| `codes-demo` | Codes TOTP des comptes de démonstration (refusé en production) |

Les commandes lisent la même configuration que le serveur (`/etc/tpgis/tpgis.env`).

## 3. Gestion des comptes

1. **Création** : module « Utilisateurs et habilitations ». Un compte est créé avec un rôle non privilégié et un mot de passe initial conforme (12 caractères, trois types de caractères, sans l'identifiant), à changer à la première connexion.
2. **Rôle privilégié** : l'attribution génère une demande de double validation, exécutée seulement après approbation d'un second responsable. Tout changement de rôle révoque les sessions du compte.
3. **Second facteur** : obligatoire pour tout rôle comportant une permission privilégiée (administration, audit, biométrie, recherche nationale, validation, fusion). L'utilisateur l'enrôle lui même à la connexion avec l'application d'authentification fournie par l'institution. En cas de perte du terminal : « Réinitialiser la MFA » (confirmation d'identité requise), puis nouvel enrôlement.
4. **Désactivation immédiate** : « Désactiver » révoque toutes les sessions ; les appels suivants du compte sont refusés dans la seconde.
5. **Réinitialisation du mot de passe** : par un administrateur fonctionnel après confirmation de son identité ; un mot de passe temporaire est remis en main propre et doit être changé à la connexion ; toutes les sessions sont révoquées. Aucune réinitialisation par courriel n'est proposée.
6. **Revue périodique** : chaque trimestre, l'auditeur et les responsables d'unité revoient la liste des comptes actifs, leurs rôles et leurs périmètres.

## 4. Rôles et permissions

Les rôles initiaux sont décrits dans [architecture.md](architecture.md). Le module « Rôles et permissions » permet de créer des rôles et de modifier leurs permissions (confirmation d'identité requise). Rendre privilégié un rôle existant est refusé : il faut créer un nouveau rôle puis l'attribuer par double validation. Un administrateur ne peut modifier ni son propre rôle ni son propre périmètre.

## 5. Référentiels et paramètres

1. **Catégories de faits** (Paramètres, « Référentiel des faits ») : création, désactivation, référence légale et autorité de validation. Une catégorie ne peut être marquée validée qu'avec le nom de l'autorité. Les catégories fournies dans la démonstration sont des exemples à faire valider.
2. **Paramètres techniques** (administrateur technique, confirmation d'identité) :

| Paramètre | Défaut | Rôle |
|---|---|---|
| `documents.extensions_autorisees` | pdf, png, jpg, jpeg, tif, tiff, docx, odt, txt | Formats acceptés |
| `documents.taille_max_octets` | 20 Mo | Taille maximale d'une pièce |
| `institution.entete` | République du Tchad, devise, ministère | En tête des documents générés |
| `institution.pied_page` | Mention de diffusion restreinte | Bas de page des documents générés |
| `retention.plaintes_archivees_annees` | 10 | Conservation des plaintes archivées (à fixer par l'institution) |
| `retention.biometrie_annees` | 5 | Conservation par défaut d'une capture biométrique |
| `retention.audit_annees` | 10 | Conservation du journal d'audit |
| `retention.sessions_jours` | 90 | Conservation des sessions expirées |
| `recherche.finalites` | Quatre finalités types | Finalités proposées lors des consultations |
| `statistiques.seuil_confidentialite` | 0 (désactivé) | Masque sur la carte les effectifs inférieurs au seuil |

Toute modification de paramètre est journalisée avec la valeur avant et après.

## 6. Conservation et purge

1. Le rapport de conservation (Paramètres, « Conservation des données ») indique les sessions expirées, les captures biométriques échues et les plaintes archivées au delà de la durée fixée.
2. La purge est demandée avec un motif et la référence de la décision institutionnelle, puis exécutée après double validation. Elle supprime les sessions expirées, supprime les captures échues (y compris dans le système biométrique) et purge le contenu des plaintes archivées échues (description, observations, liens aux personnes, fichiers), en conservant le numéro et le statut pour la continuité statistique.
3. **Le journal d'audit n'est jamais purgé par l'application.** À l'échéance fixée par l'institution : exporter le segment concerné et l'empreinte de chaîne correspondante, archiver l'export sur support protégé, puis faire réaliser la suppression du segment par le DBA sous double contrôle, en consignant l'opération. La vérification de chaîne repart alors de l'empreinte archivée.

## 7. Journal d'audit

1. Sont tracés : connexions (réussies et refusées), verrouillages, déconnexions, consultations de plaintes, dossiers, faits et fiches personnes, recherches (avec finalité et critères, numéro de document masqué), créations, modifications, changements de statut, dépôts et téléchargements de pièces, exports, générations de documents, refus d'accès, changements de droits, modifications de paramètres, demandes et décisions de double validation, sauvegardes, restaurations, purges.
2. Ne sont jamais tracés : mots de passe, jetons, secrets TOTP, codes, clés, modèles ou références biométriques. Les détails sont nettoyés automatiquement.
3. Chaque événement contient l'empreinte SHA 256 de l'événement précédent. `tpgis-admin verifier-audit` (et le bouton « Vérifier l'intégrité ») recalcule toute la chaîne. Les déclencheurs PostgreSQL interdisent toute mise à jour, suppression ou troncature, y compris pour le compte applicatif.
4. L'empreinte du dernier événement est inscrite dans chaque manifeste de sauvegarde : elle constitue un ancrage externe permettant de détecter une réécriture complète de la chaîne par un administrateur de base de données.

## 8. Maintenance courante

| Fréquence | Opération |
|---|---|
| Quotidienne | Sauvegarde chiffrée et vérifiée (minuterie systemd), vérification de la chaîne d'audit, contrôle de l'espace disque, mise à jour des signatures ClamAV |
| Hebdomadaire | Revue des refus d'accès et des verrouillages dans le journal d'audit ; relance des analyses antivirus en échec (Supervision) |
| Mensuelle | Test de restauration sur un serveur isolé ; mises à jour de sécurité du système ; `pip-audit -r requirements-serveur.txt` |
| Trimestrielle | Revue des comptes et habilitations ; revue des catégories de faits ; exercice du plan de réponse aux incidents |
| Annuelle | Renouvellement des certificats ; rotation des clés de chiffrement ; audit de sécurité |

**Rotation d'une clé de données** : ajouter la nouvelle clé au trousseau (`TPGIS_CLES_DONNEES=k1:...,k2:...`), la déclarer active (`TPGIS_CLE_DONNEES_ACTIVE=k2`), redémarrer. Les nouvelles écritures utilisent `k2` ; les anciennes valeurs restent lisibles tant que `k1` est conservée. La clé d'index aveugle ne peut pas être changée sans recalcul des index.

**Mise à jour applicative** : sauvegarde vérifiée, arrêt du service, installation de la nouvelle version, `tpgis-admin migrer` avec le compte propriétaire, redémarrage, contrôle `/api/v1/sante` et `verifier-audit`.
