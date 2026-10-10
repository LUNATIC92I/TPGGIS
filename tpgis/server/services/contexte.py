"""Contexte de securite d'une requete : utilisateur, permissions et perimetre.

Toutes les regles d'acces sont appliquees cote serveur a partir de ce
contexte. Le client ne fait que refleter ces droits dans l'interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import and_, exists, false, or_, select, true
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.database.models import (
    Dossier,
    Fait,
    LienDossierPersonne,
    LienDossierPlainte,
    LienFaitPersonne,
    LienPlaintePersonne,
    Personne,
    Plainte,
    Session,
    Unite,
    Utilisateur,
)
from tpgis.server.services.erreurs import AccesRefuse
from tpgis.shared.enums import Portee
from tpgis.shared.permissions import Permission


@dataclass
class Contexte:
    utilisateur: Utilisateur
    session: Session | None
    permissions: set[str]
    unites_accessibles: set[str] | None  # None : perimetre national
    trace_id: str
    adresse_ip: str | None = None
    finalite: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return self.utilisateur.id

    @property
    def portee(self) -> str:
        return self.utilisateur.portee

    @property
    def assignes_seulement(self) -> bool:
        return self.utilisateur.portee == Portee.ASSIGNES

    def a(self, permission: Permission | str) -> bool:
        return str(permission) in self.permissions

    def exiger(self, *permissions: Permission | str) -> None:
        manquantes = [str(p) for p in permissions if str(p) not in self.permissions]
        if manquantes:
            raise AccesRefuse(
                "Vous ne disposez pas de l'habilitation nécessaire pour cette opération.",
                details={"permissions_manquantes": manquantes},
            )

    def unite_accessible(self, unite_id: str | None) -> bool:
        if unite_id is None:
            return False
        return self.unites_accessibles is None or unite_id in self.unites_accessibles


def calculer_unites_accessibles(bd: SessionBD, utilisateur: Utilisateur) -> set[str] | None:
    portee = utilisateur.portee
    if portee == Portee.NATIONALE:
        return None
    if portee in (Portee.UNITE, Portee.ASSIGNES):
        return {utilisateur.unite_id}
    # Unite et unites subordonnees : parcours de l'arborescence.
    enfants: dict[str | None, list[str]] = {}
    for uid, parent in bd.execute(select(Unite.id, Unite.parent_id)).all():
        enfants.setdefault(parent, []).append(uid)
    resultat, pile = set(), [utilisateur.unite_id]
    while pile:
        courant = pile.pop()
        if courant in resultat:
            continue
        resultat.add(courant)
        pile.extend(enfants.get(courant, []))
    return resultat


# Filtres de perimetre appliques a toutes les requetes de lecture.


def _plaintes_assignees(ctx: Contexte):
    return select(LienDossierPlainte.plainte_id).join(Dossier, Dossier.id == LienDossierPlainte.dossier_id).where(
        Dossier.enqueteur_id == ctx.uid
    )


def filtre_plaintes(ctx: Contexte):
    if ctx.assignes_seulement:
        return or_(Plainte.agent_responsable_id == ctx.uid, Plainte.id.in_(_plaintes_assignees(ctx)))
    if ctx.unites_accessibles is None:
        return true()
    return Plainte.unite_id.in_(ctx.unites_accessibles)


def filtre_dossiers(ctx: Contexte):
    if ctx.assignes_seulement:
        return Dossier.enqueteur_id == ctx.uid
    if ctx.unites_accessibles is None:
        return true()
    return Dossier.unite_id.in_(ctx.unites_accessibles)


def filtre_faits(ctx: Contexte):
    if ctx.assignes_seulement:
        return or_(
            Fait.cree_par_id == ctx.uid,
            Fait.plainte_id.in_(select(Plainte.id).where(filtre_plaintes(ctx))),
            Fait.dossier_id.in_(select(Dossier.id).where(filtre_dossiers(ctx))),
        )
    if ctx.unites_accessibles is None:
        return true()
    return Fait.unite_id.in_(ctx.unites_accessibles)


def filtre_personnes(ctx: Contexte, *, recherche_nationale: bool = False):
    if ctx.unites_accessibles is None and not ctx.assignes_seulement:
        return true()
    if recherche_nationale and ctx.a(Permission.RECHERCHE_NATIONALE):
        return true()
    liee_plainte = exists().where(
        and_(
            LienPlaintePersonne.personne_id == Personne.id,
            LienPlaintePersonne.plainte_id.in_(select(Plainte.id).where(filtre_plaintes(ctx))),
        )
    )
    liee_dossier = exists().where(
        and_(
            LienDossierPersonne.personne_id == Personne.id,
            LienDossierPersonne.dossier_id.in_(select(Dossier.id).where(filtre_dossiers(ctx))),
        )
    )
    liee_fait = exists().where(
        and_(
            LienFaitPersonne.personne_id == Personne.id,
            LienFaitPersonne.fait_id.in_(select(Fait.id).where(filtre_faits(ctx))),
        )
    )
    if ctx.assignes_seulement:
        propre = Personne.cree_par_id == ctx.uid
    elif ctx.unites_accessibles:
        propre = Personne.unite_creation_id.in_(ctx.unites_accessibles)
    else:
        propre = false()
    return or_(propre, liee_plainte, liee_dossier, liee_fait)
