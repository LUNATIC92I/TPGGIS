# Sécurité et confidentialité

Ce document décrit les mesures de sécurité intégrées dès la conception, le résultat de la revue de sécurité interne réalisée sur cette version, les risques résiduels et le plan de réponse aux incidents. **Il ne remplace pas l'audit de sécurité indépendant exigé avant tout déploiement réel.**

## 1. Mesures en place

| Exigence | Mise en œuvre | Vérification automatisée |
|---|---|---|
| Chiffrement des communications | HTTPS obligatoire (TLS 1.2 minimum, TLS 1.3 négocié lors des essais) ; le client refuse toute adresse `http://` et tout certificat non reconnu ; en têtes HSTS | `tests/client` (certificat inconnu refusé, http refusé) ; essai manuel TLS 1.3 de bout en bout |
| Mots de passe | Argon2id (64 Mo, 3 passes, parallélisme 4), politique de complexité, renouvellement à 180 jours, mot de passe initial à changer | `tests/unit/test_securite_unitaire.py`, `tests/security/test_sessions.py` |
| Authentification multifacteur | TOTP (RFC 6238) obligatoire pour les rôles privilégiés, enrôlement forcé, anti rejeu, secret chiffré au repos | `test_mfa_obligatoire_pour_compte_privilegie`, `test_rejeu_code_mfa_refuse`, `test_secret_totp_chiffre_au_repos` |
| Force brute | Verrouillage après 5 échecs (mot de passe, code MFA, confirmation d'identité) ; limitation par adresse IP ; temps de réponse homogène ; message identique pour un compte inconnu | `test_verrouillage_apres_echecs_repetes`, `test_codes_mfa_errones_verrouillent_le_compte`, `test_reauthentification_par_force_brute_bloquee`, `test_limitation_debit_connexion` |
| Sessions | Jeton aléatoire de 256 bits, seule l'empreinte est stockée ; expiration (8 h) et inactivité (30 min) ; révocation immédiate (déconnexion, désactivation, changement de rôle ou de périmètre, réinitialisation) | `test_expiration_et_inactivite`, `test_desactivation_revoque_immediatement`, `test_jeton_stocke_sous_forme_d_empreinte` |
| Contrôle d'accès côté serveur | Permissions et périmètres appliqués à chaque requête ; éléments hors périmètre traités comme inexistants ; tests négatifs par appel direct de l'API | `tests/security/test_controle_acces.py` |
| Élévation de privilèges | Champs inconnus refusés (pas d'affectation de masse) ; rôle privilégié par double validation uniquement ; interdiction de modifier son propre rôle ou périmètre ; périmètre attribué limité au sien | `test_elevation_privileges_par_attribution_role_refusee`, `test_perimetre_plus_large_que_le_sien_refuse_a_la_creation`, `test_validation_entrees` |
| Injections SQL | Requêtes paramétrées SQLAlchemy exclusivement ; aucune concaténation de saisie | `test_injection_sql_inoperante` |
| Validation des entrées | Schémas Pydantic stricts (longueurs, motifs, dates non futures, énumérations) | `test_validation_entrees` |
| Chiffrement au repos | AES 256 GCM par champ sensible et pour toutes les pièces ; trousseau avec rotation ; index aveugle HMAC pour la recherche exacte des documents d'identité | `test_chiffrement_aller_retour_et_rotation`, `test_depot_et_telechargement_avec_integrite` |
| Secrets hors du code | Variables d'environnement issues du coffre de secrets ; aucune valeur par défaut acceptée en production ; `.env.example` sans secret | `test_production_refuse_configuration_faible` |
| Fichiers | Liste blanche d'extensions, taille maximale, signature réelle, contrôle des archives bureautiques (macros, chemins, taille décompressée), antivirus clamd avant mise à disposition, stockage chiffré hors web, SHA 256 vérifié à chaque téléchargement | `test_extension_et_signature_controlees`, `test_fichier_infecte_jamais_disponible`, `test_demon_clamd_reel` |
| Journal d'audit | Chaîné par SHA 256, ajout seul (déclencheurs PostgreSQL), nettoyé des secrets, ancré dans chaque sauvegarde ; refus d'accès tracés dans une transaction indépendante | `tests/security/test_audit.py` |
| Séparation des environnements | Base liée à son environnement ; données synthétiques interdites en production ; sauvegarde non restaurable dans un autre environnement | `tests/unit/test_configuration.py`, `test_restauration_refusee_dans_un_autre_environnement` |
| Dépendances vulnérables | Versions verrouillées ; `pip-audit` sans vulnérabilité connue à la date de la version ; audit intégré à l'intégration continue | `.github/workflows/tests.yml` |
| Erreurs | Messages explicites en français, sans pile d'exécution ni détail interne ; identifiant de trace pour le support | `test_erreurs_api_traduites` |
| Exports | Réservés à la permission `export.realiser`, confirmation d'identité, tracés ; cellules CSV neutralisées contre l'injection de formules | `test_exports_reserves_et_traces`, `test_cellules_csv_neutralisees` |
| Données nominatives | Exclues des statistiques et de la carte ; finalité obligatoire avant toute consultation de fiche ; seuil de confidentialité statistique configurable | `test_statistiques_sans_donnees_nominatives`, `test_seuil_de_confidentialite`, `test_consultation_personne_exige_finalite` |

## 2. Revue de sécurité interne de la version 0.1.0

La revue a porté sur le code du serveur et du client, en recherchant activement les contournements. Les écarts trouvés ont été corrigés et couverts par un test avant publication.

| N° | Constat | Gravité | Correction |
|---|---|---|---|
| 1 | Les codes MFA erronés étaient comptés sans déclencher le verrouillage : un attaquant connaissant le mot de passe pouvait essayer des codes de façon prolongée (limité par adresse IP seulement) | Élevée | Verrouillage commun à tous les facteurs (`compter_echec`) |
| 2 | La confirmation d'identité ne comptait pas les échecs : un jeton de session volé permettait de deviner le mot de passe sans verrouillage | Élevée | Échecs comptés, verrouillage et révocation de toutes les sessions au seuil |
| 3 | À la création d'un compte, un administrateur au périmètre limité pouvait attribuer un périmètre national | Moyenne | Contrôle identique à celui de la modification |
| 4 | L'export CSV n'était pas protégé contre l'injection de formules dans les tableurs | Faible | Neutralisation des cellules commençant par `=`, `+`, `-`, `@` |
| 5 | Un certificat serveur non reconnu produisait un message « serveur injoignable » trompeur | Faible | Message spécifique alertant sur un risque d'interception |
| 6 | Le journal d'audit pouvait en théorie être entièrement réécrit (chaîne recalculée) par un super utilisateur PostgreSQL | Moyenne | Empreinte du dernier événement inscrite dans chaque sauvegarde (ancrage externe) ; séparation des rôles d'administration recommandée |

Outils utilisés : règles de sécurité de Ruff (sous ensemble Bandit), `pip-audit`, tests négatifs automatisés, essais TLS manuels, essais contre un démon ClamAV réel.

## 3. Risques résiduels et mesures organisationnelles

| Risque | Mesure attendue |
|---|---|
| Noms, prénoms et dates de naissance stockés en clair pour permettre la recherche | Chiffrement intégral des disques du serveur, accès PostgreSQL limité au compte applicatif, sauvegardes chiffrées, journalisation PostgreSQL |
| Limitation de débit et compteurs en mémoire d'un processus | Suffisant pour une instance ; pour plusieurs instances derrière un répartiteur, utiliser un magasin partagé et limiter aussi au niveau de nginx |
| Clés de chiffrement fournies par variables d'environnement | Coffre de secrets institutionnel ou module matériel de sécurité (HSM) ; dépositaires multiples |
| Administrateur système disposant d'un accès complet au serveur | Séparation des tâches (système, base de données, application, audit), journalisation des accès d'administration, revue par l'auditeur |
| Poste client compromis | Postes gérés par l'institution, comptes Windows nominatifs, antivirus, mises à jour, verrouillage de session ; authentification mutuelle par certificat de poste (nginx) |
| Fond de carte en ligne | Désactivé par défaut ; à n'activer qu'avec un fournisseur dont la licence et la politique de journalisation sont validées |
| Dépendances futures vulnérables | `pip-audit` mensuel et à chaque intégration continue ; procédure de mise à jour testée |

## 4. Plan de réponse aux incidents

1. **Détection** : alertes de supervision (service indisponible, rupture de chaîne d'audit signalée par `tpgis-admin verifier-audit`, vagues de refus d'accès ou de verrouillages, menaces détectées par l'antivirus, échec de sauvegarde).
2. **Qualification** (responsable de la sécurité, sous 1 heure) : nature, périmètre, données concernées, gravité. Ouverture d'une fiche d'incident numérotée.
3. **Confinement** : désactiver immédiatement les comptes suspects (révocation des sessions incluse) ; si nécessaire, isoler le serveur du réseau des postes au niveau du pare feu en conservant l'accès d'administration ; préserver les journaux (copie du journal d'audit, journaux système et PostgreSQL) avant toute action corrective.
4. **Analyse** : exploiter le journal d'audit (filtres par utilisateur, action, identifiant de trace), vérifier l'intégrité de la chaîne et la comparer aux empreintes des sauvegardes.
5. **Éradication et restauration** : corriger la cause, renouveler les secrets exposés (rotation des clés de données, mots de passe de service, certificats), restaurer si nécessaire depuis la dernière sauvegarde intègre (voir [sauvegarde_restauration.md](sauvegarde_restauration.md)).
6. **Notification** : informer la hiérarchie et les responsables de traitement selon les procédures et textes applicables.
7. **Retour d'expérience** sous 15 jours : mesures correctives, mise à jour de ce document, exercice planifié.

## 5. Avant tout déploiement réel

1. Audit de sécurité indépendant (revue de code, test d'intrusion de l'API et du client, revue de configuration du serveur).
2. Validation par les responsables habilités de la politique d'habilitations, de conservation et de journalisation.
3. Test complet de restauration sur infrastructure isolée, chronométré.
4. Vérification que la configuration de production est acceptée par le serveur (contrôles bloquants listés dans [installation.md](installation.md)).
