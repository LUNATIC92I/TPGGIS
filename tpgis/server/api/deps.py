"""Dependances FastAPI : base de donnees, authentification, contexte."""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import unquote

from fastapi import Depends, Request
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.config import ParametresServeur
from tpgis.server.services.auth import valider_jeton
from tpgis.server.services.contexte import Contexte, calculer_unites_accessibles
from tpgis.server.services.erreurs import AccesRefuse, NonAuthentifie
from tpgis.shared.enums import TypeSession


def parametres(request: Request) -> ParametresServeur:
    return request.app.state.parametres


def base(request: Request) -> Iterator[SessionBD]:
    bd = request.app.state.fabrique()
    request.state.bd = bd
    try:
        yield bd
    finally:
        # Toute transaction non validee explicitement est annulee.
        bd.rollback()
        bd.close()


def adresse_client(request: Request) -> str | None:
    p: ParametresServeur = request.app.state.parametres
    if p.tls_termine_par_proxy:
        transmis = request.headers.get("x-forwarded-for")
        if transmis:
            return transmis.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def _jeton(request: Request) -> str:
    entete = request.headers.get("authorization", "")
    if not entete.lower().startswith("bearer "):
        raise NonAuthentifie("Authentification requise.")
    return entete[7:].strip()


def _construire_contexte(request: Request, bd: SessionBD, types_autorises: set[str]) -> Contexte:
    p: ParametresServeur = request.app.state.parametres
    session = valider_jeton(bd, p, _jeton(request))
    if session.type_session not in types_autorises:
        if session.type_session == TypeSession.CHANGEMENT_MOT_DE_PASSE:
            raise AccesRefuse(
                "Vous devez changer votre mot de passe avant de continuer.", code="CHANGEMENT_MOT_DE_PASSE_REQUIS"
            )
        raise AccesRefuse(
            "Vous devez activer l'authentification multifacteur avant de continuer.", code="ENROLEMENT_MFA_REQUIS"
        )
    utilisateur = session.utilisateur
    if not utilisateur.role.actif:
        raise AccesRefuse("Votre rôle est désactivé.")
    finalite = request.headers.get("x-tpgis-finalite")
    ctx = Contexte(
        utilisateur=utilisateur,
        session=session,
        permissions=utilisateur.role.codes_permissions,
        unites_accessibles=calculer_unites_accessibles(bd, utilisateur),
        trace_id=request.state.trace_id,
        adresse_ip=adresse_client(request),
        finalite=unquote(finalite)[:255].strip() if finalite else None,
    )
    request.state.contexte = ctx
    # La mise a jour de l'activite de session est validee immediatement.
    bd.commit()
    return ctx


def contexte(request: Request, bd: SessionBD = Depends(base)) -> Contexte:
    return _construire_contexte(request, bd, {TypeSession.COMPLETE})


def contexte_partiel(request: Request, bd: SessionBD = Depends(base)) -> Contexte:
    return _construire_contexte(request, bd, {t.value for t in TypeSession})


def contexte_mfa(request: Request, bd: SessionBD = Depends(base)) -> Contexte:
    return _construire_contexte(request, bd, {TypeSession.COMPLETE, TypeSession.ENROLEMENT_MFA})


def valider(bd: SessionBD, resultat):
    """Valide la transaction puis retourne le resultat."""
    bd.commit()
    return resultat
