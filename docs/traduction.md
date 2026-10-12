# Interface bilingue (français et anglais)

Le client de bureau s'affiche en français (langue par défaut) ou en anglais. Les messages d'erreur renvoyés par le serveur suivent la langue de l'interface.

## 1. Choix de la langue

| Moyen | Effet |
|---|---|
| Liste « Français / English » de l'écran de connexion | Change la langue immédiatement, avant toute connexion |
| Bouton « English » ou « Français » du bandeau supérieur | Change la langue sans se reconnecter : la fenêtre est reconstruite avec la même session |
| `langue = fr` ou `langue = en` dans la section `[affichage]` de `client.ini` | Langue par défaut du poste, fixée par l'administration |

Le choix de l'utilisateur est mémorisé sur le poste et prime sur la valeur de `client.ini`.

## 2. Ce qui est traduit et ce qui ne l'est pas

| Traduit | Reste en français |
|---|---|
| Menus, titres, boutons, formulaires, colonnes, messages, info bulles | Données saisies (récits, noms, lieux, unités, observations) |
| Libellés des statuts, rôles, natures de l'information, types de pièces | Documents administratifs PDF (fiche de plainte, bordereau, rapport) et exports CSV |
| Libellés initiaux des rôles, des permissions et des catégories de faits | Rôles et catégories créés ou renommés par l'administration |
| Messages d'erreur du serveur (en tête `Accept-Language`) | Journal d'audit et journaux techniques |

Les documents administratifs et le journal d'audit restent en français, langue des procédures.

## 3. Fonctionnement technique

1. Le français est la langue source : chaque texte affiché est écrit en français dans le code et passe par la fonction `tr()` (`tpgis/shared/i18n.py`).
2. Le catalogue `tpgis/shared/i18n/en.json` associe chaque texte français à sa traduction anglaise. Un texte absent du catalogue s'affiche en français, jamais vide.
3. Les parties variables sont des paramètres nommés : `tr("Plainte {numero}", numero=...)`.
4. Les tables de libellés (`tpgis/client/libelles.py`), les titres de pages, les noms de modules et les en têtes de colonnes sont traduits au moment de l'affichage, ce qui permet de changer de langue sans redémarrer.
5. Côté serveur, les erreurs métier sont des modèles français à paramètres nommés (`DonneesInvalides("... {cle}", parametres={...})`), traduits dans la réponse selon l'en tête `Accept-Language` envoyé par le client.

## 4. Ajouter ou modifier un texte

1. Écrire le texte en français dans `tr("...")`.
2. Ajouter sa traduction dans `tpgis/shared/i18n/en.json`.
3. Lancer `python -m pytest tests/i18n` : les tests signalent toute traduction manquante, toute entrée inutilisée, tout écart de paramètres entre les deux langues, et parcourent toutes les pages en anglais pour détecter un texte resté en français.
