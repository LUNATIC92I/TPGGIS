"""Enumerations partagees entre le serveur et le client TPGIS.

Les valeurs sont stockees telles quelles en base de donnees : ne pas les
renommer sans migration.
"""

from enum import StrEnum


class Environnement(StrEnum):
    DEVELOPPEMENT = "developpement"
    TEST = "test"
    DEMONSTRATION = "demonstration"
    PRODUCTION = "production"


class Corps(StrEnum):
    POLICE = "POLICE"
    GENDARMERIE = "GENDARMERIE"


class TypeUnite(StrEnum):
    DIRECTION = "DIRECTION"
    REGION = "REGION"
    LEGION = "LEGION"
    COMPAGNIE = "COMPAGNIE"
    COMMISSARIAT_CENTRAL = "COMMISSARIAT_CENTRAL"
    COMMISSARIAT = "COMMISSARIAT"
    BRIGADE = "BRIGADE"
    POSTE = "POSTE"
    SERVICE_SPECIALISE = "SERVICE_SPECIALISE"


class Portee(StrEnum):
    """Perimetre de donnees d'un utilisateur (controle d'acces par attributs)."""

    ASSIGNES = "ASSIGNES"
    UNITE = "UNITE"
    UNITE_ET_SUBORDONNEES = "UNITE_ET_SUBORDONNEES"
    NATIONALE = "NATIONALE"


class TypeSession(StrEnum):
    COMPLETE = "COMPLETE"
    ENROLEMENT_MFA = "ENROLEMENT_MFA"
    CHANGEMENT_MOT_DE_PASSE = "CHANGEMENT_MOT_DE_PASSE"


class StatutPlainte(StrEnum):
    NOUVELLE = "NOUVELLE"
    EN_VERIFICATION = "EN_VERIFICATION"
    EN_TRAITEMENT = "EN_TRAITEMENT"
    TRANSMISE = "TRANSMISE"
    CLOTUREE = "CLOTUREE"
    ARCHIVEE = "ARCHIVEE"


LIBELLES_STATUT_PLAINTE = {
    StatutPlainte.NOUVELLE: "Nouvelle plainte",
    StatutPlainte.EN_VERIFICATION: "En cours de vérification",
    StatutPlainte.EN_TRAITEMENT: "En cours de traitement",
    StatutPlainte.TRANSMISE: "Transmise à un autre service",
    StatutPlainte.CLOTUREE: "Clôturée administrativement",
    StatutPlainte.ARCHIVEE: "Archivée",
}

# Transitions autorisees du cycle de vie d'une plainte.
TRANSITIONS_PLAINTE: dict[StatutPlainte, set[StatutPlainte]] = {
    StatutPlainte.NOUVELLE: {
        StatutPlainte.EN_VERIFICATION,
        StatutPlainte.EN_TRAITEMENT,
        StatutPlainte.TRANSMISE,
        StatutPlainte.CLOTUREE,
    },
    StatutPlainte.EN_VERIFICATION: {
        StatutPlainte.EN_TRAITEMENT,
        StatutPlainte.TRANSMISE,
        StatutPlainte.CLOTUREE,
    },
    StatutPlainte.EN_TRAITEMENT: {
        StatutPlainte.EN_VERIFICATION,
        StatutPlainte.TRANSMISE,
        StatutPlainte.CLOTUREE,
    },
    StatutPlainte.TRANSMISE: {StatutPlainte.EN_TRAITEMENT, StatutPlainte.CLOTUREE},
    StatutPlainte.CLOTUREE: {StatutPlainte.ARCHIVEE, StatutPlainte.EN_TRAITEMENT},
    StatutPlainte.ARCHIVEE: set(),
}


class RolePersonne(StrEnum):
    """Role procedural d'une personne dans un dossier donne.

    MIS_EN_CAUSE ne signifie jamais auteur reconnu : seule une decision
    judiciaire enregistree comme telle peut etablir une culpabilite.
    """

    PLAIGNANT = "PLAIGNANT"
    VICTIME = "VICTIME"
    TEMOIN = "TEMOIN"
    MIS_EN_CAUSE = "MIS_EN_CAUSE"
    PERSONNE_CITEE = "PERSONNE_CITEE"
    AUTRE = "AUTRE"


LIBELLES_ROLE_PERSONNE = {
    RolePersonne.PLAIGNANT: "Plaignant",
    RolePersonne.VICTIME: "Victime",
    RolePersonne.TEMOIN: "Témoin",
    RolePersonne.MIS_EN_CAUSE: "Personne mise en cause (présumée innocente)",
    RolePersonne.PERSONNE_CITEE: "Personne citée",
    RolePersonne.AUTRE: "Autre personne concernée",
}


class Sexe(StrEnum):
    MASCULIN = "M"
    FEMININ = "F"
    NON_RENSEIGNE = "NR"


class StatutVerificationIdentite(StrEnum):
    NON_VERIFIEE = "NON_VERIFIEE"
    DECLARATIVE = "DECLARATIVE"
    VERIFIEE_DOCUMENT = "VERIFIEE_DOCUMENT"
    CONTESTEE = "CONTESTEE"


class TypeDocumentIdentite(StrEnum):
    CARTE_NATIONALE = "CARTE_NATIONALE"
    PASSEPORT = "PASSEPORT"
    ACTE_NAISSANCE = "ACTE_NAISSANCE"
    CARTE_CONSULAIRE = "CARTE_CONSULAIRE"
    PERMIS_CONDUIRE = "PERMIS_CONDUIRE"
    AUTRE = "AUTRE"


class StatutPersonne(StrEnum):
    ACTIVE = "ACTIVE"
    FUSIONNEE = "FUSIONNEE"


class SourceInformation(StrEnum):
    PLAINTE = "PLAINTE"
    CONSTAT_AGENT = "CONSTAT_AGENT"
    SIGNALEMENT = "SIGNALEMENT"
    TRANSMISSION_SERVICE = "TRANSMISSION_SERVICE"
    AUTRE = "AUTRE"


class NatureInformation(StrEnum):
    """Distinction obligatoire entre faits rapportes, verifies, soupcons et decisions."""

    FAIT_RAPPORTE = "FAIT_RAPPORTE"
    FAIT_VERIFIE = "FAIT_VERIFIE"
    SOUPCON = "SOUPCON"
    DECISION_JUDICIAIRE = "DECISION_JUDICIAIRE"


LIBELLES_NATURE_INFORMATION = {
    NatureInformation.FAIT_RAPPORTE: "Fait rapporté (déclaration non vérifiée)",
    NatureInformation.FAIT_VERIFIE: "Fait vérifié par le service",
    NatureInformation.SOUPCON: "Soupçon (à confirmer)",
    NatureInformation.DECISION_JUDICIAIRE: "Décision judiciaire",
}


class EtatVerification(StrEnum):
    NON_VERIFIE = "NON_VERIFIE"
    EN_VERIFICATION = "EN_VERIFICATION"
    VERIFIE = "VERIFIE"
    NON_ETABLI = "NON_ETABLI"


class TypeProcedure(StrEnum):
    ENQUETE_PRELIMINAIRE = "ENQUETE_PRELIMINAIRE"
    ENQUETE_FLAGRANCE = "ENQUETE_FLAGRANCE"
    COMMISSION_ROGATOIRE = "COMMISSION_ROGATOIRE"
    MAIN_COURANTE = "MAIN_COURANTE"
    AUTRE = "AUTRE"


class StatutDossier(StrEnum):
    OUVERT = "OUVERT"
    EN_COURS = "EN_COURS"
    TRANSMIS_PARQUET = "TRANSMIS_PARQUET"
    CLOTURE = "CLOTURE"
    ARCHIVE = "ARCHIVE"


class TypeActe(StrEnum):
    PROCES_VERBAL = "PROCES_VERBAL"
    AUDITION = "AUDITION"
    CONSTATATION = "CONSTATATION"
    REQUISITION = "REQUISITION"
    TRANSMISSION = "TRANSMISSION"
    DECISION_JUDICIAIRE = "DECISION_JUDICIAIRE"
    AUTRE = "AUTRE"


class TypePiece(StrEnum):
    PIECE_JUSTIFICATIVE = "PIECE_JUSTIFICATIVE"
    PROCES_VERBAL = "PROCES_VERBAL"
    PHOTOGRAPHIE_IDENTIFICATION = "PHOTOGRAPHIE_IDENTIFICATION"
    RAPPORT = "RAPPORT"
    CORRESPONDANCE = "CORRESPONDANCE"
    AUTRE = "AUTRE"


class StatutAnalyse(StrEnum):
    EN_ATTENTE = "EN_ATTENTE"
    SAIN = "SAIN"
    INFECTE = "INFECTE"
    ERREUR = "ERREUR"


class ModaliteBiometrique(StrEnum):
    EMPREINTE_DIGITALE = "EMPREINTE_DIGITALE"


class StatutCapture(StrEnum):
    ACTIVE = "ACTIVE"
    SUPPRIMEE = "SUPPRIMEE"


class ResultatAudit(StrEnum):
    SUCCES = "SUCCES"
    REFUS = "REFUS"
    ECHEC = "ECHEC"


class TypeValidation(StrEnum):
    FUSION_PERSONNES = "FUSION_PERSONNES"
    ATTRIBUTION_ROLE_PRIVILEGIE = "ATTRIBUTION_ROLE_PRIVILEGIE"
    SUPPRESSION_CAPTURE_BIOMETRIQUE = "SUPPRESSION_CAPTURE_BIOMETRIQUE"
    PURGE_DONNEES = "PURGE_DONNEES"


class StatutValidation(StrEnum):
    EN_ATTENTE = "EN_ATTENTE"
    APPROUVEE = "APPROUVEE"
    REJETEE = "REJETEE"
    EXECUTEE = "EXECUTEE"
    ECHEC = "ECHEC"
