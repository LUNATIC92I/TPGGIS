"""Donnees operationnelles : plaintes, personnes, faits, dossiers et actes."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tpgis.server.database.base import (
    Base,
    DateHeureUTC,
    Horodatage,
    JSONChiffre,
    TexteChiffre,
    colonne_id,
)
from tpgis.server.database.models.organisation import Unite, Utilisateur


class CategorieFait(Horodatage, Base):
    """Referentiel configurable des categories de faits et d'infractions."""

    __tablename__ = "categories_faits"

    id: Mapped[str] = colonne_id()
    code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    libelle: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_legale: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("categories_faits.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validee: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validee_par: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Plainte(Horodatage, Base):
    __tablename__ = "plaintes"
    __table_args__ = (
        Index("ix_plaintes_unite_statut", "unite_id", "statut"),
        Index("ix_plaintes_recue_le", "recue_le"),
    )

    id: Mapped[str] = colonne_id()
    numero: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    recue_le: Mapped[datetime] = mapped_column(DateHeureUTC(), nullable=False)
    service_enregistrement: Mapped[str] = mapped_column(String(200), nullable=False)
    unite_id: Mapped[str] = mapped_column(ForeignKey("unites.id"), nullable=False)
    agent_responsable_id: Mapped[str | None] = mapped_column(ForeignKey("utilisateurs.id"), nullable=True, index=True)
    categorie_id: Mapped[str | None] = mapped_column(ForeignKey("categories_faits.id"), nullable=True, index=True)
    description: Mapped[str] = mapped_column(TexteChiffre(), nullable=False)
    date_faits: Mapped[date | None] = mapped_column(Date, nullable=True)
    lieu_faits: Mapped[str | None] = mapped_column(String(255), nullable=True)
    province_code: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    references_procedure: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[str] = mapped_column(String(24), nullable=False)
    motif_statut: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_destinataire: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observations: Mapped[str | None] = mapped_column(TexteChiffre(), nullable=True)
    temoins_non_identifies: Mapped[str | None] = mapped_column(TexteChiffre(), nullable=True)
    cree_par_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    est_synthetique: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    unite: Mapped[Unite] = relationship(lazy="joined")
    categorie: Mapped[CategorieFait | None] = relationship(lazy="joined")
    agent_responsable: Mapped[Utilisateur | None] = relationship(foreign_keys=[agent_responsable_id], lazy="joined")
    liens_personnes: Mapped[list[LienPlaintePersonne]] = relationship(
        back_populates="plainte", cascade="all, delete-orphan"
    )

    __mapper_args__ = {"version_id_col": version}


class Personne(Horodatage, Base):
    __tablename__ = "personnes"
    __table_args__ = (
        Index("ix_personnes_nom_normalise", "nom_normalise"),
        Index("ix_personnes_naissance", "date_naissance"),
    )

    id: Mapped[str] = colonne_id()
    numero_interne: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    nom: Mapped[str] = mapped_column(String(120), nullable=False)
    prenoms: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nom_normalise: Mapped[str] = mapped_column(String(330), nullable=False)
    date_naissance: Mapped[date | None] = mapped_column(Date, nullable=True)
    lieu_naissance: Mapped[str | None] = mapped_column(String(160), nullable=True)
    nationalite: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sexe: Mapped[str | None] = mapped_column(String(4), nullable=True)
    alias: Mapped[list | None] = mapped_column(JSON, nullable=True)
    coordonnees: Mapped[dict | None] = mapped_column(JSONChiffre(), nullable=True)
    type_document: Mapped[str | None] = mapped_column(String(32), nullable=True)
    numero_document: Mapped[str | None] = mapped_column(TexteChiffre(), nullable=True)
    index_document: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    statut_verification: Mapped[str] = mapped_column(String(32), nullable=False)
    photo_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    unite_creation_id: Mapped[str] = mapped_column(ForeignKey("unites.id"), nullable=False, index=True)
    cree_par_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)
    statut: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    fusionnee_dans_id: Mapped[str | None] = mapped_column(ForeignKey("personnes.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    est_synthetique: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    unite_creation: Mapped[Unite] = relationship(lazy="joined")

    __mapper_args__ = {"version_id_col": version}


class LienPlaintePersonne(Base):
    __tablename__ = "plainte_personnes"
    __table_args__ = (UniqueConstraint("plainte_id", "personne_id", "role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plainte_id: Mapped[str] = mapped_column(ForeignKey("plaintes.id", ondelete="CASCADE"), nullable=False, index=True)
    personne_id: Mapped[str] = mapped_column(ForeignKey("personnes.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    observations: Mapped[str | None] = mapped_column(TexteChiffre(), nullable=True)

    plainte: Mapped[Plainte] = relationship(back_populates="liens_personnes")
    personne: Mapped[Personne] = relationship(lazy="joined")


class Dossier(Horodatage, Base):
    __tablename__ = "dossiers"
    __table_args__ = (Index("ix_dossiers_unite_statut", "unite_id", "statut"),)

    id: Mapped[str] = colonne_id()
    numero: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    intitule: Mapped[str] = mapped_column(String(255), nullable=False)
    type_procedure: Mapped[str] = mapped_column(String(32), nullable=False)
    unite_id: Mapped[str] = mapped_column(ForeignKey("unites.id"), nullable=False)
    enqueteur_id: Mapped[str | None] = mapped_column(ForeignKey("utilisateurs.id"), nullable=True, index=True)
    statut: Mapped[str] = mapped_column(String(24), nullable=False)
    date_ouverture: Mapped[date] = mapped_column(Date, nullable=False)
    date_cloture: Mapped[date | None] = mapped_column(Date, nullable=True)
    motif_cloture: Mapped[str | None] = mapped_column(Text, nullable=True)
    juridiction: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observations: Mapped[str | None] = mapped_column(TexteChiffre(), nullable=True)
    cree_par_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    est_synthetique: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    unite: Mapped[Unite] = relationship(lazy="joined")
    enqueteur: Mapped[Utilisateur | None] = relationship(foreign_keys=[enqueteur_id], lazy="joined")

    __mapper_args__ = {"version_id_col": version}


class LienDossierPlainte(Base):
    __tablename__ = "dossier_plaintes"
    __table_args__ = (UniqueConstraint("dossier_id", "plainte_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True)
    plainte_id: Mapped[str] = mapped_column(ForeignKey("plaintes.id"), nullable=False, index=True)


class LienDossierPersonne(Base):
    __tablename__ = "dossier_personnes"
    __table_args__ = (UniqueConstraint("dossier_id", "personne_id", "role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True)
    personne_id: Mapped[str] = mapped_column(ForeignKey("personnes.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)

    personne: Mapped[Personne] = relationship(lazy="joined")


class ActeProcedure(Horodatage, Base):
    __tablename__ = "actes_procedure"

    id: Mapped[str] = colonne_id()
    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True)
    type_acte: Mapped[str] = mapped_column(String(32), nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    date_acte: Mapped[date] = mapped_column(Date, nullable=False)
    resume: Mapped[str | None] = mapped_column(TexteChiffre(), nullable=True)
    redige_par_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)


class Fait(Horodatage, Base):
    __tablename__ = "faits"
    __table_args__ = (Index("ix_faits_unite_categorie", "unite_id", "categorie_id"),)

    id: Mapped[str] = colonne_id()
    reference: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    categorie_id: Mapped[str] = mapped_column(ForeignKey("categories_faits.id"), nullable=False)
    date_declaree: Mapped[date | None] = mapped_column(Date, nullable=True)
    lieu: Mapped[str | None] = mapped_column(String(255), nullable=True)
    province_code: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    description: Mapped[str] = mapped_column(TexteChiffre(), nullable=False)
    source_information: Mapped[str] = mapped_column(String(32), nullable=False)
    nature_information: Mapped[str] = mapped_column(String(32), nullable=False)
    etat_verification: Mapped[str] = mapped_column(String(24), nullable=False)
    references_actes: Mapped[str | None] = mapped_column(Text, nullable=True)
    unite_id: Mapped[str] = mapped_column(ForeignKey("unites.id"), nullable=False)
    plainte_id: Mapped[str | None] = mapped_column(ForeignKey("plaintes.id"), nullable=True, index=True)
    dossier_id: Mapped[str | None] = mapped_column(ForeignKey("dossiers.id"), nullable=True, index=True)
    cree_par_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    est_synthetique: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    categorie: Mapped[CategorieFait] = relationship(lazy="joined")
    unite: Mapped[Unite] = relationship(lazy="joined")

    __mapper_args__ = {"version_id_col": version}


class LienFaitPersonne(Base):
    __tablename__ = "fait_personnes"
    __table_args__ = (UniqueConstraint("fait_id", "personne_id", "role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fait_id: Mapped[str] = mapped_column(ForeignKey("faits.id", ondelete="CASCADE"), nullable=False, index=True)
    personne_id: Mapped[str] = mapped_column(ForeignKey("personnes.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)

    personne: Mapped[Personne] = relationship(lazy="joined")
