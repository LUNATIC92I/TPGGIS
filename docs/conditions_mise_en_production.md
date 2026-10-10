# Conditions préalables à la mise en production

TPGIS est un outil institutionnel soumis à autorisation. Le présent document liste les conditions à réunir **avant tout chargement de données réelles**. Il ne constitue pas un avis juridique : les textes applicables au Tchad doivent être identifiés et interprétés par les responsables juridiques compétents.

## 1. Cadre juridique à établir

1. Identifier et valider les textes applicables : protection des données à caractère personnel, fichiers de police et de gendarmerie, procédure pénale, conservation des archives, données biométriques, cybersécurité.
2. Obtenir les autorisations ou avis requis auprès des autorités compétentes, le cas échéant de l'autorité de protection des données à caractère personnel.
3. Formaliser par un acte réglementaire ou une décision : la finalité du traitement, les catégories de données et de personnes, les destinataires, les durées de conservation, les droits des personnes et leurs modalités d'exercice.
4. Encadrer spécifiquement la biométrie : fondement légal, finalités autorisées, interdiction des usages non prévus, durées de conservation, procédure de suppression.

## 2. Gouvernance

1. Désigner le ou les **responsables de traitement** et le responsable de la sécurité du système.
2. Définir la **politique d'habilitation** : qui reçoit quel rôle et quel périmètre, qui approuve les rôles privilégiés, revue trimestrielle.
3. Fixer la **politique de conservation et de purge** et renseigner les paramètres `retention` en conséquence.
4. Établir les **procédures de contrôle** : revue du journal d'audit par l'auditeur, traitement des alertes, exercices de restauration et de réponse aux incidents.
5. Valider le **référentiel des catégories de faits** et les **modèles de documents**.

## 3. Hébergement et sécurité

1. Valider l'hébergement : locaux sécurisés de l'institution, réseau isolé, alimentation secourue, site de secours.
2. Mettre en place l'infrastructure de gestion de clés, le coffre de secrets, les certificats et la signature de code.
3. Réaliser un **audit de sécurité indépendant** (revue de code, tests d'intrusion, revue de configuration) et corriger les constats.
4. Vérifier que le serveur démarre en configuration `production` (les contrôles bloquants refusent toute configuration non conforme).
5. Réaliser et chronométrer un **test de restauration complet** sur infrastructure isolée.

## 4. Mise en service

1. Pilote limité, avec un nombre réduit d'unités et d'utilisateurs formés.
2. Formation des utilisateurs (guide utilisateur), des administrateurs (guide d'administration) et des auditeurs.
3. Bilan du pilote et validation formelle par les responsables habilités avant toute extension.

## 5. Liste de contrôle avant chargement de données réelles

| N° | Condition | Responsable | Fait |
|---|---|---|---|
| 1 | Textes applicables identifiés et validés | Direction juridique | |
| 2 | Acte autorisant le traitement adopté | Autorité compétente | |
| 3 | Responsables de traitement désignés | Direction générale | |
| 4 | Politique d'habilitation approuvée | Responsable de traitement | |
| 5 | Durées de conservation fixées et paramétrées | Responsable de traitement | |
| 6 | Hébergement validé | Direction des systèmes d'information | |
| 7 | Audit de sécurité indépendant réalisé, constats corrigés | Responsable de la sécurité | |
| 8 | Test de restauration réussi | Exploitation | |
| 9 | Référentiel des faits validé | Autorités compétentes | |
| 10 | Utilisateurs pilotes formés | Formation | |
| 11 | Module biométrique : désactivé (`aucun`) ou intégration validée | Responsable de traitement | |
| 12 | Base de production vierge de toute donnée de démonstration (contrôle automatique au démarrage) | Exploitation | |
