"""Catalogue des permissions et definition des roles initiaux.

Les roles sont configurables en base par l'administration fonctionnelle.
Les definitions ci dessous ne servent qu'a l'initialisation d'une instance.
"""

from enum import StrEnum

from tpgis.shared.enums import Portee


class Permission(StrEnum):
    PLAINTE_LIRE = "plainte.lire"
    PLAINTE_CREER = "plainte.creer"
    PLAINTE_MODIFIER = "plainte.modifier"
    PLAINTE_CLOTURER = "plainte.cloturer"
    PLAINTE_ARCHIVER = "plainte.archiver"

    FAIT_LIRE = "fait.lire"
    FAIT_CREER = "fait.creer"
    FAIT_MODIFIER = "fait.modifier"

    PERSONNE_LIRE = "personne.lire"
    PERSONNE_CREER = "personne.creer"
    PERSONNE_MODIFIER = "personne.modifier"
    PERSONNE_FUSIONNER = "personne.fusionner"

    DOSSIER_LIRE = "dossier.lire"
    DOSSIER_CREER = "dossier.creer"
    DOSSIER_MODIFIER = "dossier.modifier"
    DOSSIER_CLOTURER = "dossier.cloturer"

    DOCUMENT_LIRE = "document.lire"
    DOCUMENT_AJOUTER = "document.ajouter"

    BIOMETRIE_LIRE = "biometrie.lire"
    BIOMETRIE_ENREGISTRER = "biometrie.enregistrer"
    BIOMETRIE_VERIFIER = "biometrie.verifier"
    BIOMETRIE_SUPPRIMER = "biometrie.supprimer"

    RECHERCHE_EFFECTUER = "recherche.effectuer"
    RECHERCHE_NATIONALE = "recherche.nationale"

    STATISTIQUES_LIRE = "statistiques.lire"
    CARTE_LIRE = "carte.lire"
    EXPORT_REALISER = "export.realiser"

    UNITE_LIRE = "unite.lire"
    UNITE_GERER = "unite.gerer"
    UTILISATEUR_LIRE = "utilisateur.lire"
    UTILISATEUR_GERER = "utilisateur.gerer"
    ROLE_GERER = "role.gerer"
    CATEGORIE_GERER = "categorie.gerer"

    AUDIT_LIRE = "audit.lire"
    PARAMETRES_GERER = "parametres.gerer"
    SAUVEGARDE_GERER = "sauvegarde.gerer"
    SYSTEME_SUPERVISER = "systeme.superviser"
    VALIDATION_APPROUVER = "validation.approuver"


LIBELLES_PERMISSIONS: dict[str, str] = {
    Permission.PLAINTE_LIRE: "Consulter les plaintes du périmètre",
    Permission.PLAINTE_CREER: "Enregistrer une plainte",
    Permission.PLAINTE_MODIFIER: "Modifier une plainte",
    Permission.PLAINTE_CLOTURER: "Clôturer une plainte (motif obligatoire)",
    Permission.PLAINTE_ARCHIVER: "Archiver une plainte",
    Permission.FAIT_LIRE: "Consulter les faits signalés",
    Permission.FAIT_CREER: "Enregistrer un fait",
    Permission.FAIT_MODIFIER: "Modifier un fait",
    Permission.PERSONNE_LIRE: "Consulter les personnes concernées",
    Permission.PERSONNE_CREER: "Enregistrer une personne",
    Permission.PERSONNE_MODIFIER: "Modifier une personne",
    Permission.PERSONNE_FUSIONNER: "Demander la fusion de deux fiches",
    Permission.DOSSIER_LIRE: "Consulter les dossiers et procédures",
    Permission.DOSSIER_CREER: "Ouvrir un dossier",
    Permission.DOSSIER_MODIFIER: "Modifier un dossier",
    Permission.DOSSIER_CLOTURER: "Clôturer un dossier",
    Permission.DOCUMENT_LIRE: "Consulter et télécharger les pièces",
    Permission.DOCUMENT_AJOUTER: "Déposer une pièce",
    Permission.BIOMETRIE_LIRE: "Consulter les références biométriques",
    Permission.BIOMETRIE_ENREGISTRER: "Enregistrer une capture biométrique",
    Permission.BIOMETRIE_VERIFIER: "Effectuer une vérification biométrique 1 pour 1",
    Permission.BIOMETRIE_SUPPRIMER: "Demander la suppression d'une capture",
    Permission.RECHERCHE_EFFECTUER: "Effectuer des recherches de vérification",
    Permission.RECHERCHE_NATIONALE: "Étendre les recherches au périmètre national",
    Permission.STATISTIQUES_LIRE: "Consulter les statistiques agrégées",
    Permission.CARTE_LIRE: "Consulter la cartographie agrégée",
    Permission.EXPORT_REALISER: "Exporter des rapports (CSV, PDF)",
    Permission.UNITE_LIRE: "Consulter le référentiel des unités",
    Permission.UNITE_GERER: "Administrer les unités",
    Permission.UTILISATEUR_LIRE: "Consulter les comptes utilisateurs",
    Permission.UTILISATEUR_GERER: "Administrer les comptes utilisateurs",
    Permission.ROLE_GERER: "Administrer les rôles et habilitations",
    Permission.CATEGORIE_GERER: "Administrer le référentiel des faits",
    Permission.AUDIT_LIRE: "Consulter le journal d'audit",
    Permission.PARAMETRES_GERER: "Administrer les paramètres techniques",
    Permission.SAUVEGARDE_GERER: "Superviser les sauvegardes",
    Permission.SYSTEME_SUPERVISER: "Superviser l'état du système",
    Permission.VALIDATION_APPROUVER: "Approuver les demandes de double validation",
}

P = Permission

# Permissions dont la presence rend un role privilegie (MFA obligatoire,
# double validation lors de l'attribution).
PERMISSIONS_PRIVILEGIEES = {
    P.UTILISATEUR_GERER,
    P.ROLE_GERER,
    P.PARAMETRES_GERER,
    P.SAUVEGARDE_GERER,
    P.AUDIT_LIRE,
    P.BIOMETRIE_LIRE,
    P.BIOMETRIE_ENREGISTRER,
    P.BIOMETRIE_SUPPRIMER,
    P.RECHERCHE_NATIONALE,
    P.VALIDATION_APPROUVER,
    P.PERSONNE_FUSIONNER,
}

ROLES_INITIAUX: list[dict] = [
    {
        "code": "ADMIN_TECHNIQUE",
        "libelle": "Administrateur technique",
        "description": "Exploitation technique. Aucun accès aux dossiers opérationnels.",
        "portee_defaut": Portee.UNITE,
        "permissions": [P.PARAMETRES_GERER, P.SAUVEGARDE_GERER, P.SYSTEME_SUPERVISER, P.UNITE_LIRE],
    },
    {
        "code": "ADMIN_FONCTIONNEL",
        "libelle": "Administrateur fonctionnel",
        "description": "Gestion des comptes, rôles, unités et référentiels. Aucun accès aux dossiers.",
        "portee_defaut": Portee.NATIONALE,
        "permissions": [
            P.UTILISATEUR_LIRE,
            P.UTILISATEUR_GERER,
            P.ROLE_GERER,
            P.UNITE_LIRE,
            P.UNITE_GERER,
            P.CATEGORIE_GERER,
            P.VALIDATION_APPROUVER,
        ],
    },
    {
        "code": "RESPONSABLE_UNITE",
        "libelle": "Responsable d'unité",
        "description": "Pilotage de l'unité et de ses unités subordonnées.",
        "portee_defaut": Portee.UNITE_ET_SUBORDONNEES,
        "permissions": [
            P.PLAINTE_LIRE,
            P.PLAINTE_MODIFIER,
            P.PLAINTE_CLOTURER,
            P.PLAINTE_ARCHIVER,
            P.FAIT_LIRE,
            P.FAIT_MODIFIER,
            P.PERSONNE_LIRE,
            P.PERSONNE_FUSIONNER,
            P.DOSSIER_LIRE,
            P.DOSSIER_MODIFIER,
            P.DOSSIER_CLOTURER,
            P.DOCUMENT_LIRE,
            P.RECHERCHE_EFFECTUER,
            P.STATISTIQUES_LIRE,
            P.CARTE_LIRE,
            P.EXPORT_REALISER,
            P.UNITE_LIRE,
            P.UTILISATEUR_LIRE,
            P.VALIDATION_APPROUVER,
        ],
    },
    {
        "code": "OFFICIER_HABILITE",
        "libelle": "Officier ou agent habilité",
        "description": "Traitement complet des plaintes et procédures de l'unité.",
        "portee_defaut": Portee.UNITE,
        "permissions": [
            P.PLAINTE_LIRE,
            P.PLAINTE_CREER,
            P.PLAINTE_MODIFIER,
            P.PLAINTE_CLOTURER,
            P.FAIT_LIRE,
            P.FAIT_CREER,
            P.FAIT_MODIFIER,
            P.PERSONNE_LIRE,
            P.PERSONNE_CREER,
            P.PERSONNE_MODIFIER,
            P.PERSONNE_FUSIONNER,
            P.DOSSIER_LIRE,
            P.DOSSIER_CREER,
            P.DOSSIER_MODIFIER,
            P.DOCUMENT_LIRE,
            P.DOCUMENT_AJOUTER,
            P.BIOMETRIE_LIRE,
            P.BIOMETRIE_ENREGISTRER,
            P.BIOMETRIE_VERIFIER,
            P.RECHERCHE_EFFECTUER,
            P.STATISTIQUES_LIRE,
            P.CARTE_LIRE,
            P.UNITE_LIRE,
        ],
    },
    {
        "code": "AGENT_ACCUEIL",
        "libelle": "Agent chargé de l'enregistrement des plaintes",
        "description": "Enregistrement des plaintes et des personnes. Aucun accès biométrique.",
        "portee_defaut": Portee.UNITE,
        "permissions": [
            P.PLAINTE_LIRE,
            P.PLAINTE_CREER,
            P.PERSONNE_LIRE,
            P.PERSONNE_CREER,
            P.DOCUMENT_LIRE,
            P.DOCUMENT_AJOUTER,
            P.UNITE_LIRE,
        ],
    },
    {
        "code": "ENQUETEUR",
        "libelle": "Enquêteur habilité",
        "description": "Accès limité aux plaintes et dossiers qui lui sont attribués.",
        "portee_defaut": Portee.ASSIGNES,
        "permissions": [
            P.PLAINTE_LIRE,
            P.PLAINTE_MODIFIER,
            P.FAIT_LIRE,
            P.FAIT_CREER,
            P.FAIT_MODIFIER,
            P.PERSONNE_LIRE,
            P.PERSONNE_CREER,
            P.PERSONNE_MODIFIER,
            P.DOSSIER_LIRE,
            P.DOSSIER_MODIFIER,
            P.DOCUMENT_LIRE,
            P.DOCUMENT_AJOUTER,
            P.BIOMETRIE_LIRE,
            P.BIOMETRIE_VERIFIER,
            P.RECHERCHE_EFFECTUER,
            P.UNITE_LIRE,
        ],
    },
    {
        "code": "CONSULTATION",
        "libelle": "Consultation seule",
        "description": "Lecture des plaintes et dossiers du périmètre, sans modification.",
        "portee_defaut": Portee.UNITE,
        "permissions": [
            P.PLAINTE_LIRE,
            P.FAIT_LIRE,
            P.DOSSIER_LIRE,
            P.STATISTIQUES_LIRE,
            P.CARTE_LIRE,
            P.UNITE_LIRE,
        ],
    },
    {
        "code": "AUDITEUR",
        "libelle": "Auditeur autorisé",
        "description": "Examen du journal d'audit sans modification des dossiers.",
        "portee_defaut": Portee.NATIONALE,
        "permissions": [P.AUDIT_LIRE, P.UTILISATEUR_LIRE, P.UNITE_LIRE, P.STATISTIQUES_LIRE],
    },
]


def est_privilegie(permissions: set[str] | list[str]) -> bool:
    return any(p in PERMISSIONS_PRIVILEGIEES for p in permissions)
