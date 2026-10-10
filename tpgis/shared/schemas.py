"""Schemas Pydantic de validation des entrees de l'API.

Tous les schemas refusent les champs inconnus (extra="forbid") afin
d'empecher l'affectation de champs non prevus (elevation de privileges par
injection d'attributs).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tpgis.shared.enums import (
    Corps,
    EtatVerification,
    NatureInformation,
    Portee,
    RolePersonne,
    Sexe,
    SourceInformation,
    StatutDossier,
    StatutPlainte,
    StatutVerificationIdentite,
    TypeActe,
    TypeDocumentIdentite,
    TypePiece,
    TypeProcedure,
    TypeUnite,
)

TexteCourt = str
CODE_PROVINCE = r"^TD-[A-Z0-9]{2,3}~?$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# Authentification


class DemandeConnexion(Strict):
    identifiant: str = Field(min_length=3, max_length=64)
    mot_de_passe: str = Field(min_length=1, max_length=256)
    code_mfa: str | None = Field(default=None, max_length=8)


class ChangementMotDePasse(Strict):
    ancien_mot_de_passe: str = Field(min_length=1, max_length=256)
    nouveau_mot_de_passe: str = Field(min_length=1, max_length=256)


class CodeMFA(Strict):
    code_mfa: str = Field(min_length=6, max_length=8)


class Reauthentification(Strict):
    mot_de_passe: str = Field(min_length=1, max_length=256)
    code_mfa: str | None = Field(default=None, max_length=8)


# Organisation


class UniteCreation(Strict):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Z0-9\-]+$")
    nom: str = Field(min_length=3, max_length=200)
    type_unite: TypeUnite
    corps: Corps
    parent_id: str | None = None
    province_code: str | None = Field(default=None, pattern=CODE_PROVINCE)
    ville: str | None = Field(default=None, max_length=120)
    latitude: float | None = Field(default=None, ge=7.0, le=24.0)
    longitude: float | None = Field(default=None, ge=13.0, le=24.5)
    telephone: str | None = Field(default=None, max_length=40)


class UniteModification(Strict):
    nom: str | None = Field(default=None, min_length=3, max_length=200)
    parent_id: str | None = None
    province_code: str | None = Field(default=None, pattern=CODE_PROVINCE)
    ville: str | None = Field(default=None, max_length=120)
    latitude: float | None = Field(default=None, ge=7.0, le=24.0)
    longitude: float | None = Field(default=None, ge=13.0, le=24.5)
    telephone: str | None = Field(default=None, max_length=40)
    active: bool | None = None


class UtilisateurCreation(Strict):
    identifiant: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9._\-]+$")
    nom: str = Field(min_length=1, max_length=120)
    prenoms: str = Field(min_length=1, max_length=160)
    matricule: str | None = Field(default=None, max_length=40)
    grade: str | None = Field(default=None, max_length=80)
    unite_id: str
    role_id: str
    portee: Portee | None = None
    mot_de_passe_initial: str = Field(min_length=1, max_length=256)


class UtilisateurModification(Strict):
    nom: str | None = Field(default=None, min_length=1, max_length=120)
    prenoms: str | None = Field(default=None, min_length=1, max_length=160)
    grade: str | None = Field(default=None, max_length=80)
    unite_id: str | None = None
    portee: Portee | None = None


class ChangementRole(Strict):
    role_id: str
    motif: str = Field(min_length=10, max_length=1000)


class Desactivation(Strict):
    motif: str = Field(min_length=10, max_length=1000)


class ReinitialisationMotDePasse(Strict):
    mot_de_passe_temporaire: str = Field(min_length=1, max_length=256)
    motif: str = Field(min_length=10, max_length=1000)


class RoleCreation(Strict):
    code: str = Field(min_length=3, max_length=48, pattern=r"^[A-Z0-9_]+$")
    libelle: str = Field(min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    portee_defaut: Portee
    permissions: list[str] = Field(default_factory=list)


class RoleModification(Strict):
    libelle: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    portee_defaut: Portee | None = None
    permissions: list[str] | None = None
    actif: bool | None = None


class CategorieCreation(Strict):
    code: str = Field(min_length=2, max_length=48, pattern=r"^[A-Z0-9_]+$")
    libelle: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    reference_legale: str | None = Field(default=None, max_length=255)
    parent_id: str | None = None
    validee: bool = False
    validee_par: str | None = Field(default=None, max_length=200)


class CategorieModification(Strict):
    libelle: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    reference_legale: str | None = Field(default=None, max_length=255)
    active: bool | None = None
    validee: bool | None = None
    validee_par: str | None = Field(default=None, max_length=200)


# Personnes


class Coordonnees(Strict):
    telephone: str | None = Field(default=None, max_length=40)
    adresse: str | None = Field(default=None, max_length=300)
    courriel: str | None = Field(default=None, max_length=160)


class PersonneCreation(Strict):
    nom: str = Field(min_length=1, max_length=120)
    prenoms: str | None = Field(default=None, max_length=200)
    date_naissance: date | None = None
    lieu_naissance: str | None = Field(default=None, max_length=160)
    nationalite: str | None = Field(default=None, max_length=80)
    sexe: Sexe | None = None
    alias: list[str] | None = Field(default=None, max_length=10)
    coordonnees: Coordonnees | None = None
    type_document: TypeDocumentIdentite | None = None
    numero_document: str | None = Field(default=None, max_length=60)
    statut_verification: StatutVerificationIdentite = StatutVerificationIdentite.NON_VERIFIEE
    confirmer_malgre_doublons: bool = False

    @field_validator("date_naissance")
    @classmethod
    def _naissance_passee(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError("La date de naissance ne peut pas être dans le futur.")
        if v and v.year < 1900:
            raise ValueError("Date de naissance invraisemblable.")
        return v


class PersonneModification(Strict):
    version: int
    nom: str | None = Field(default=None, min_length=1, max_length=120)
    prenoms: str | None = Field(default=None, max_length=200)
    date_naissance: date | None = None
    lieu_naissance: str | None = Field(default=None, max_length=160)
    nationalite: str | None = Field(default=None, max_length=80)
    sexe: Sexe | None = None
    alias: list[str] | None = Field(default=None, max_length=10)
    coordonnees: Coordonnees | None = None
    type_document: TypeDocumentIdentite | None = None
    numero_document: str | None = Field(default=None, max_length=60)
    statut_verification: StatutVerificationIdentite | None = None


class CritereDoublon(Strict):
    nom: str = Field(min_length=1, max_length=120)
    prenoms: str | None = Field(default=None, max_length=200)
    date_naissance: date | None = None
    lieu_naissance: str | None = Field(default=None, max_length=160)
    numero_document: str | None = Field(default=None, max_length=60)
    exclure_id: str | None = None


class DemandeFusion(Strict):
    personne_conservee_id: str
    personne_absorbee_id: str
    motif: str = Field(min_length=10, max_length=2000)


class LienPersonne(Strict):
    personne_id: str
    role: RolePersonne
    observations: str | None = Field(default=None, max_length=2000)


# Plaintes


class PlainteCreation(Strict):
    recue_le: datetime | None = None
    service_enregistrement: str = Field(min_length=2, max_length=200)
    unite_id: str | None = None
    agent_responsable_id: str | None = None
    categorie_id: str | None = None
    description: str = Field(min_length=10, max_length=20000)
    date_faits: date | None = None
    lieu_faits: str | None = Field(default=None, max_length=255)
    province_code: str | None = Field(default=None, pattern=CODE_PROVINCE)
    references_procedure: str | None = Field(default=None, max_length=2000)
    observations: str | None = Field(default=None, max_length=10000)
    temoins_non_identifies: str | None = Field(default=None, max_length=5000)
    personnes: list[LienPersonne] = Field(default_factory=list, max_length=50)

    @field_validator("date_faits")
    @classmethod
    def _faits_passes(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError("La date déclarée des faits ne peut pas être dans le futur.")
        return v


class PlainteModification(Strict):
    version: int
    agent_responsable_id: str | None = None
    categorie_id: str | None = None
    description: str | None = Field(default=None, min_length=10, max_length=20000)
    date_faits: date | None = None
    lieu_faits: str | None = Field(default=None, max_length=255)
    province_code: str | None = Field(default=None, pattern=CODE_PROVINCE)
    references_procedure: str | None = Field(default=None, max_length=2000)
    observations: str | None = Field(default=None, max_length=10000)
    temoins_non_identifies: str | None = Field(default=None, max_length=5000)


class ChangementStatutPlainte(Strict):
    version: int
    statut: StatutPlainte
    motif: str | None = Field(default=None, max_length=2000)
    service_destinataire: str | None = Field(default=None, max_length=200)


# Faits


class FaitCreation(Strict):
    categorie_id: str
    date_declaree: date | None = None
    lieu: str | None = Field(default=None, max_length=255)
    province_code: str | None = Field(default=None, pattern=CODE_PROVINCE)
    description: str = Field(min_length=10, max_length=20000)
    source_information: SourceInformation
    nature_information: NatureInformation = NatureInformation.FAIT_RAPPORTE
    etat_verification: EtatVerification = EtatVerification.NON_VERIFIE
    references_actes: str | None = Field(default=None, max_length=2000)
    unite_id: str | None = None
    plainte_id: str | None = None
    dossier_id: str | None = None
    personnes: list[LienPersonne] = Field(default_factory=list, max_length=50)


class FaitModification(Strict):
    version: int
    categorie_id: str | None = None
    date_declaree: date | None = None
    lieu: str | None = Field(default=None, max_length=255)
    province_code: str | None = Field(default=None, pattern=CODE_PROVINCE)
    description: str | None = Field(default=None, min_length=10, max_length=20000)
    nature_information: NatureInformation | None = None
    etat_verification: EtatVerification | None = None
    references_actes: str | None = Field(default=None, max_length=2000)
    dossier_id: str | None = None


# Dossiers


class DossierCreation(Strict):
    intitule: str = Field(min_length=3, max_length=255)
    type_procedure: TypeProcedure
    unite_id: str | None = None
    enqueteur_id: str | None = None
    date_ouverture: date | None = None
    juridiction: str | None = Field(default=None, max_length=200)
    observations: str | None = Field(default=None, max_length=10000)
    plaintes_ids: list[str] = Field(default_factory=list, max_length=100)


class DossierModification(Strict):
    version: int
    intitule: str | None = Field(default=None, min_length=3, max_length=255)
    type_procedure: TypeProcedure | None = None
    enqueteur_id: str | None = None
    statut: StatutDossier | None = None
    juridiction: str | None = Field(default=None, max_length=200)
    observations: str | None = Field(default=None, max_length=10000)
    motif_cloture: str | None = Field(default=None, max_length=2000)


class ActeCreation(Strict):
    type_acte: TypeActe
    reference: str = Field(min_length=2, max_length=80)
    date_acte: date
    resume: str | None = Field(default=None, max_length=10000)


class RattachementPlainte(Strict):
    plainte_id: str


# Documents


class MetadonneesDocument(Strict):
    intitule: str = Field(min_length=2, max_length=255)
    type_piece: TypePiece
    plainte_id: str | None = None
    dossier_id: str | None = None
    personne_id: str | None = None


# Biometrie


class CaptureCreation(Strict):
    personne_id: str
    position_doigt: str = Field(
        pattern=r"^(POUCE|INDEX|MAJEUR|ANNULAIRE|AURICULAIRE)_(DROIT|GAUCHE)$"
    )
    equipement: str = Field(min_length=2, max_length=120)
    fondement_legal: str = Field(min_length=10, max_length=2000)
    consentement_recueilli: bool
    conserver_annees: int | None = Field(default=None, ge=1, le=30)


class VerificationBiometrique(Strict):
    capture_id: str
    equipement: str = Field(min_length=2, max_length=120)


class SuppressionCapture(Strict):
    motif: str = Field(min_length=10, max_length=2000)


# Recherche


class DemandeRecherche(Strict):
    finalite: str = Field(min_length=5, max_length=255)
    numero_plainte: str | None = Field(default=None, max_length=48)
    numero_dossier: str | None = Field(default=None, max_length=48)
    numero_interne: str | None = Field(default=None, max_length=32)
    nom: str | None = Field(default=None, max_length=120)
    prenoms: str | None = Field(default=None, max_length=200)
    date_naissance: date | None = None
    lieu_naissance: str | None = Field(default=None, max_length=160)
    numero_document: str | None = Field(default=None, max_length=60)
    etendre_national: bool = False


# Validations et administration


class DecisionValidation(Strict):
    approuver: bool
    commentaire: str | None = Field(default=None, max_length=2000)


class ModificationParametre(Strict):
    valeur: list | dict | str | int | bool | None


class DemandePurge(Strict):
    motif: str = Field(min_length=10, max_length=2000)
