"""Unites, roles, utilisateurs et sessions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tpgis.server.database.base import Base, DateHeureUTC, Horodatage, TexteChiffre, colonne_id, maintenant


class Unite(Horodatage, Base):
    __tablename__ = "unites"

    id: Mapped[str] = colonne_id()
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    nom: Mapped[str] = mapped_column(String(200), nullable=False)
    type_unite: Mapped[str] = mapped_column(String(32), nullable=False)
    corps: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("unites.id"), nullable=True, index=True)
    province_code: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    ville: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    est_synthetique: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    parent: Mapped[Unite | None] = relationship(remote_side="Unite.id")


class Role(Horodatage, Base):
    __tablename__ = "roles"

    id: Mapped[str] = colonne_id()
    code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    libelle: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    portee_defaut: Mapped[str] = mapped_column(String(32), nullable=False)
    systeme: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def codes_permissions(self) -> set[str]:
        return {p.permission for p in self.permissions}


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(64), nullable=False)

    role: Mapped[Role] = relationship(back_populates="permissions")


class Utilisateur(Horodatage, Base):
    __tablename__ = "utilisateurs"

    id: Mapped[str] = colonne_id()
    identifiant: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    nom: Mapped[str] = mapped_column(String(120), nullable=False)
    prenoms: Mapped[str] = mapped_column(String(160), nullable=False)
    matricule: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(80), nullable=True)
    unite_id: Mapped[str] = mapped_column(ForeignKey("unites.id"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    portee: Mapped[str] = mapped_column(String(32), nullable=False)

    mot_de_passe_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    doit_changer_mot_de_passe: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mot_de_passe_modifie_le: Mapped[datetime | None] = mapped_column(DateHeureUTC(), nullable=True)

    mfa_secret: Mapped[str | None] = mapped_column(TexteChiffre(), nullable=True)
    mfa_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_dernier_pas: Mapped[int | None] = mapped_column(Integer, nullable=True)

    actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    desactive_le: Mapped[datetime | None] = mapped_column(DateHeureUTC(), nullable=True)
    motif_desactivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    echecs_connexion: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verrouille_jusqua: Mapped[datetime | None] = mapped_column(DateHeureUTC(), nullable=True)
    derniere_connexion: Mapped[datetime | None] = mapped_column(DateHeureUTC(), nullable=True)
    est_synthetique: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    unite: Mapped[Unite] = relationship(lazy="joined")
    role: Mapped[Role] = relationship(lazy="joined")


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_utilisateur_actives", "utilisateur_id", "revoquee_le"),)

    id: Mapped[str] = colonne_id()
    utilisateur_id: Mapped[str] = mapped_column(ForeignKey("utilisateurs.id"), nullable=False)
    empreinte_jeton: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    type_session: Mapped[str] = mapped_column(String(32), nullable=False)
    creee_le: Mapped[datetime] = mapped_column(DateHeureUTC(), default=maintenant, nullable=False)
    expire_le: Mapped[datetime] = mapped_column(DateHeureUTC(), nullable=False)
    derniere_activite: Mapped[datetime] = mapped_column(DateHeureUTC(), default=maintenant, nullable=False)
    reauthentifiee_le: Mapped[datetime | None] = mapped_column(DateHeureUTC(), nullable=True)
    revoquee_le: Mapped[datetime | None] = mapped_column(DateHeureUTC(), nullable=True)
    motif_revocation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    adresse_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_utilisateur: Mapped[str | None] = mapped_column(String(255), nullable=True)

    utilisateur: Mapped[Utilisateur] = relationship(lazy="joined")
