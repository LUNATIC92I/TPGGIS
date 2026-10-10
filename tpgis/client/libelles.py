"""Libelles francais des valeurs codees affichees dans l'interface."""

from __future__ import annotations

from tpgis.shared.enums import LIBELLES_NATURE_INFORMATION, LIBELLES_ROLE_PERSONNE, LIBELLES_STATUT_PLAINTE

STATUT_PLAINTE = {str(k): v for k, v in LIBELLES_STATUT_PLAINTE.items()}
ROLE_PERSONNE = {str(k): v for k, v in LIBELLES_ROLE_PERSONNE.items()}
NATURE_INFORMATION = {str(k): v for k, v in LIBELLES_NATURE_INFORMATION.items()}

STATUT_DOSSIER = {
    "OUVERT": "Ouvert",
    "EN_COURS": "En cours",
    "TRANSMIS_PARQUET": "Transmis au parquet",
    "CLOTURE": "Clôturé",
    "ARCHIVE": "Archivé",
}
TYPE_PROCEDURE = {
    "ENQUETE_PRELIMINAIRE": "Enquête préliminaire",
    "ENQUETE_FLAGRANCE": "Enquête de flagrance",
    "COMMISSION_ROGATOIRE": "Commission rogatoire",
    "MAIN_COURANTE": "Main courante",
    "AUTRE": "Autre",
}
TYPE_ACTE = {
    "PROCES_VERBAL": "Procès-verbal",
    "AUDITION": "Audition",
    "CONSTATATION": "Constatation",
    "REQUISITION": "Réquisition",
    "TRANSMISSION": "Transmission",
    "DECISION_JUDICIAIRE": "Décision judiciaire",
    "AUTRE": "Autre acte",
}
ETAT_VERIFICATION = {
    "NON_VERIFIE": "Non vérifié",
    "EN_VERIFICATION": "En cours de vérification",
    "VERIFIE": "Vérifié",
    "NON_ETABLI": "Non établi",
}
SOURCE_INFORMATION = {
    "PLAINTE": "Plainte",
    "CONSTAT_AGENT": "Constat d'un agent",
    "SIGNALEMENT": "Signalement",
    "TRANSMISSION_SERVICE": "Transmission d'un service",
    "AUTRE": "Autre source",
}
SEXE = {"M": "Masculin", "F": "Féminin", "NR": "Non renseigné"}
VERIFICATION_IDENTITE = {
    "NON_VERIFIEE": "Non vérifiée",
    "DECLARATIVE": "Déclarative",
    "VERIFIEE_DOCUMENT": "Vérifiée sur document",
    "CONTESTEE": "Contestée",
}
TYPE_DOCUMENT_IDENTITE = {
    "CARTE_NATIONALE": "Carte nationale d'identité",
    "PASSEPORT": "Passeport",
    "ACTE_NAISSANCE": "Acte de naissance",
    "CARTE_CONSULAIRE": "Carte consulaire",
    "PERMIS_CONDUIRE": "Permis de conduire",
    "AUTRE": "Autre document",
}
TYPE_PIECE = {
    "PIECE_JUSTIFICATIVE": "Pièce justificative",
    "PROCES_VERBAL": "Procès-verbal",
    "PHOTOGRAPHIE_IDENTIFICATION": "Photographie d'identification",
    "RAPPORT": "Rapport",
    "CORRESPONDANCE": "Correspondance",
    "AUTRE": "Autre pièce",
}
STATUT_ANALYSE = {
    "EN_ATTENTE": "Analyse en attente",
    "SAIN": "Analysé, sain",
    "INFECTE": "Menace détectée",
    "ERREUR": "Analyse impossible",
}
PORTEE = {
    "ASSIGNES": "Dossiers attribués uniquement",
    "UNITE": "Unité",
    "UNITE_ET_SUBORDONNEES": "Unité et unités subordonnées",
    "NATIONALE": "Nationale",
}
TYPE_UNITE = {
    "DIRECTION": "Direction",
    "REGION": "Région",
    "LEGION": "Légion",
    "COMPAGNIE": "Compagnie",
    "COMMISSARIAT_CENTRAL": "Commissariat central",
    "COMMISSARIAT": "Commissariat",
    "BRIGADE": "Brigade",
    "POSTE": "Poste",
    "SERVICE_SPECIALISE": "Service spécialisé",
}
CORPS = {"POLICE": "Police nationale", "GENDARMERIE": "Gendarmerie nationale"}
STATUT_VALIDATION = {
    "EN_ATTENTE": "En attente",
    "APPROUVEE": "Approuvée",
    "REJETEE": "Rejetée",
    "EXECUTEE": "Exécutée",
    "ECHEC": "Échec",
}
TYPE_VALIDATION = {
    "FUSION_PERSONNES": "Fusion de fiches personnes",
    "ATTRIBUTION_ROLE_PRIVILEGIE": "Attribution d'un rôle privilégié",
    "SUPPRESSION_CAPTURE_BIOMETRIQUE": "Suppression d'une capture biométrique",
    "PURGE_DONNEES": "Purge des données échues",
}
NIVEAU_CORRESPONDANCE = {"EXACT": "Exacte", "ELEVE": "Élevée", "MOYEN": "Moyenne", "FAIBLE": "Faible"}
DOIGTS = [f"{d}_{c}" for c in ("DROIT", "GAUCHE") for d in ("POUCE", "INDEX", "MAJEUR", "ANNULAIRE", "AURICULAIRE")]


def libelle(table: dict, valeur) -> str:
    if valeur is None or valeur == "":
        return ""
    return table.get(str(valeur), str(valeur))
