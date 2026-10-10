# Modèle de déploiement multisite

## 1. Principe retenu : centralisation

TPGIS est conçu pour un **serveur central unique** (avec un site de secours), auquel se connectent tous les commissariats, brigades et directions par le réseau institutionnel. Ce modèle :

1. évite toute copie locale de données sensibles dans les unités ;
2. applique les mêmes règles d'accès, la même numérotation et le même journal d'audit à tout le territoire ;
3. permet la révocation instantanée d'un compte sur tout le territoire.

Le cloisonnement entre unités n'est pas physique mais logique : chaque utilisateur est rattaché à une unité et à un périmètre (éléments attribués, unité, unité et subordonnées, national). Le serveur applique ce périmètre à chaque requête.

## 2. Architecture cible

| Site | Composants | Rôle |
|---|---|---|
| Site central (N'Djamena) | 2 serveurs applicatifs derrière un répartiteur nginx, PostgreSQL principal, ClamAV, stockage des pièces | Production |
| Site de secours (seconde ville) | PostgreSQL en réplication en flux (streaming replication), copie du stockage, serveur applicatif prêt | Reprise après sinistre |
| Directions générales et régionales | Postes clients | Pilotage, statistiques nationales ou régionales |
| Commissariats et brigades | Postes clients | Saisie et traitement |
| Coffre de sauvegarde | Support à rétention verrouillée, hors site | Copies quotidiennes chiffrées |

## 3. Connectivité des unités

| Situation de l'unité | Solution |
|---|---|
| Raccordée au réseau institutionnel | Accès direct au nom `tpgis.institution.td` |
| Raccordée par Internet | Tunnel VPN institutionnel (IPsec ou WireGuard) vers le site central ; le serveur n'est jamais publié directement sur Internet |
| Liaison faible débit | Le client échange de petites réponses paginées ; les pièces volumineuses sont à numériser avec une résolution adaptée |
| Sans liaison | Enregistrement sur registre papier puis saisie différée au retour de la liaison (voir le paragraphe 5) |

## 4. Montée en charge

1. Le serveur applicatif est sans état : plusieurs instances peuvent fonctionner derrière nginx. Dans ce cas, la limitation de débit et les compteurs de verrouillage doivent être partagés (limitation complémentaire au niveau de nginx ; magasin partagé pour la limitation applicative), ce qui constitue une évolution identifiée.
2. Le stockage des pièces doit alors être un volume partagé (NFS sécurisé ou stockage objet interne), le chemin étant configuré par `TPGIS_REPERTOIRE_STOCKAGE`.
3. Les identifiants UUID et la numérotation par unité évitent les collisions entre sites.

## 5. Postes hors ligne : désactivé par défaut

Aucune synchronisation hors ligne n'est implémentée ni activée dans cette version. Si elle devait être ajoutée, le cahier des charges minimal serait :

1. chiffrement local intégral des données synchronisées, lié à l'identité de l'agent et au poste ;
2. périmètre de synchronisation minimal (unité, période courte), jamais le registre national ;
3. gestion explicite des conflits (verrouillage optimiste par version déjà en place côté serveur, file de modifications à rejouer, arbitrage humain) ;
4. numérotation provisoire puis définitive à la synchronisation ;
5. révocation à distance et effacement des données du poste en cas de perte ou de vol ;
6. journalisation de toutes les opérations hors ligne, rejouées dans le journal central.

## 6. Étapes de déploiement recommandées

1. **Pilote** : site central et 2 à 3 unités de N'Djamena, données réelles uniquement après autorisation ; mesure de performance sur l'infrastructure réelle.
2. **Extension régionale** : chefs-lieux de province, formation des formateurs, revue des habilitations.
3. **Généralisation** : ensemble des unités raccordées ; mise en service du site de secours et exercice de bascule.
4. À chaque étape : audit de sécurité ciblé, test de restauration, bilan d'usage.
