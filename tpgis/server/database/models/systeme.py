"""Documents, biometrie, audit, historique, validations et parametres."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tpgis.server.database.base import Base, DateHeureUTC, Horodatage, TexteChiffre, colonne_id, maintenant


class Document(Horodatage, Base):
    """Piece rattachee a une plainte, un dossier ou une personne."""

    __tablename__ = "documents"

    id: Mapped[str] = colonne_id()
    intitule: Mapped[str] = mapped_column(String(255), nullable=False)
    type_piece: Mapped[str] = mapped_column(String(40), nullable=False)
    plainte_id: Mapped[str | None] = mapped_column(ForeignKey("plaintes.id"), nullable=True, index=True)
    dossier_id: Mapped[str | None] = mapped_column(ForeignKey("dossiers.id"), nullable=True, index=True)
    personne_id: Mapped[str | None] = mapped_column(ForeignKey("personnes.id"), nullable=True, index=True)
    unite_id: Mapped[str] = mapped_column(ForeignKey("unites.id"), nullable=False)
    version_courante: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cree_par_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)
    est_synthetique: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    versions: Mapped[list[VersionDocument]] = relationship(
        back_populates="document", order_by="VersionDocument.numero_version", cascade="all, delete-orphan"
    )


class VersionDocument(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "numero_version"),)

    id: Mapped[str] = colonne_id()
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    numero_version: Mapped[int] = mapped_column(Integer, nullable=False)
    nom_fichier: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    type_mime: Mapped[str] = mapped_column(String(100), nullable=False)
    taille: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chemin_stockage: Mapped[str] = mapped_column(String(255), nullable=False)
    cle_id: Mapped[str] = mapped_column(String(16), nullable=False)
    statut_analyse: Mapped[str] = mapped_column(String(16), nullable=False)
    resultat_analyse: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analyse_le: Mapped[datetime | None] = mapped_column(DateHeureUTC(), nullable=True)
    deposee_par_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)
    deposee_le: Mapped[datetime] = mapped_column(DateHeureUTC(), default=maintenant, nullable=False)

    document: Mapped[Document] = relationship(back_populates="versions")


class CaptureBiometrique(Horodatage, Base):
    """Reference d'une capture biometrique.

    Le modele biometrique n'est jamais stocke ici en clair : seule une
    reference opaque, chiffree, vers le systeme biometrique est conservee.
    """

    __tablename__ = "captures_biometriques"

    id: Mapped[str] = colonne_id()
    personne_id: Mapped[str] = mapped_column(ForeignKey("personnes.id"), nullable=False, index=True)
    modalite: Mapped[str] = mapped_column(String(32), nullable=False)
    position_doigt: Mapped[str | None] = mapped_column(String(32), nullable=True)
    adaptateur: Mapped[str] = mapped_column(String(64), nullable=False)
    equipement: Mapped[str] = mapped_column(String(120), nullable=False)
    collectee_le: Mapped[datetime] = mapped_column(DateHeureUTC(), nullable=False)
    fondement_legal: Mapped[str] = mapped_column(Text, nullable=False)
    consentement_recueilli: Mapped[bool] = mapped_column(Boolean, nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)
    unite_id: Mapped[str] = mapped_column(ForeignKey("unites.id"), nullable=False)
    reference_modele: Mapped[str] = mapped_column(TexteChiffre(), nullable=False)
    qualite: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conserver_jusqua: Mapped[date] = mapped_column(Date, nullable=False)
    statut: Mapped[str] = mapped_column(String(16), nullable=False)
    supprimee_le: Mapped[datetime | None] = mapped_column(DateHeureUTC(), nullable=True)
    motif_suppression: Mapped[str | None] = mapped_column(Text, nullable=True)
    est_synthetique: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class EvenementAudit(Base):
    """Journal d'audit chaine (chaque entree contient l'empreinte de la precedente).

    En PostgreSQL, un declencheur interdit toute modification ou suppression.
    """

    __tablename__ = "journal_audit"
    __table_args__ = (
        Index("ix_audit_horodatage", "horodatage"),
        Index("ix_audit_utilisateur", "utilisateur_id"),
        Index("ix_audit_ressource", "type_ressource", "ressource_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    horodatage: Mapped[datetime] = mapped_column(DateHeureUTC(), default=maintenant, nullable=False)
    utilisateur_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    identifiant: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    type_ressource: Mapped[str | None] = mapped_column(String(48), nullable=True)
    ressource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unite_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resultat: Mapped[str] = mapped_column(String(12), nullable=False)
    finalite: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    adresse_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    empreinte_precedente: Mapped[str] = mapped_column(String(64), nullable=False)
    empreinte: Mapped[str] = mapped_column(String(64), nullable=False)


class HistoriqueModification(Base):
    __tablename__ = "historique_modifications"
    __table_args__ = (Index("ix_historique_entite", "type_entite", "entite_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_entite: Mapped[str] = mapped_column(String(48), nullable=False)
    entite_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    modifie_par_id: Mapped[str] = mapped_column(String(36), nullable=False)
    modifie_par_identifiant: Mapped[str] = mapped_column(String(64), nullable=False)
    modifie_le: Mapped[datetime] = mapped_column(DateHeureUTC(), default=maintenant, nullable=False)
    changements: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DemandeValidation(Horodatage, Base):
    """Double validation : une action critique est executee seulement apres
    approbation par un second utilisateur habilite, distinct du demandeur."""

    __tablename__ = "demandes_validation"

    id: Mapped[str] = colonne_id()
    type_action: Mapped[str] = mapped_column(String(48), nullable=False)
    charge_utile: Mapped[dict] = mapped_column(JSON, nullable=False)
    resume: Mapped[str] = mapped_column(String(255), nullable=False)
    motif: Mapped[str] = mapped_column(Text, nullable=False)
    demandeur_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)
    unite_id: Mapped[str] = mapped_column(ForeignKey("unites.id"), nullable=False)
    statut: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    valideur_id: Mapped[str | None] = mapped_column(ForeignKey("utilisateurs.id"), nullable=True)
    decidee_le: Mapped[datetime | None] = mapped_column(DateHeureUTC(), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    resultat: Mapped[str | None] = mapped_column(Text, nullable=True)


class Parametre(Base):
    __tablename__ = "parametres"

    cle: Mapped[str] = mapped_column(String(80), primary_key=True)
    valeur: Mapped[dict | list | str | int | bool | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    modifie_par: Mapped[str | None] = mapped_column(String(64), nullable=True)
    modifie_le: Mapped[datetime] = mapped_column(DateHeureUTC(), default=maintenant, onupdate=maintenant)


class Compteur(Base):
    """Compteurs de numerotation (plaintes, dossiers, faits, documents)."""

    __tablename__ = "compteurs"

    cle: Mapped[str] = mapped_column(String(80), primary_key=True)
    valeur: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MetadonneeInstance(Base):
    """Identite de l'instance : environnement, presence de donnees synthetiques."""

    __tablename__ = "metadonnees_instance"

    cle: Mapped[str] = mapped_column(String(64), primary_key=True)
    valeur: Mapped[str] = mapped_column(String(255), nullable=False)

