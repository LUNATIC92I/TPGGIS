"""Routes d'authentification et de gestion de la session courante."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.api.deps import adresse_client, base, contexte_mfa, contexte_partiel, parametres, valider
from tpgis.server.config import ParametresServeur
from tpgis.server.services import audit, auth
from tpgis.server.services.contexte import Contexte
from tpgis.shared import schemas
from tpgis.shared.permissions import LIBELLES_PERMISSIONS

routeur = APIRouter(prefix="/auth", tags=["Authentification"])


@routeur.post("/connexion")
def connexion(
    donnees: schemas.DemandeConnexion,
    request: Request,
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    request.app.state.limiteur.verifier(f"connexion:{adresse_client(request)}", p.limite_connexion_par_minute_ip)
    resultat = auth.connecter(
        bd,
        p,
        donnees.identifiant,
        donnees.mot_de_passe,
        donnees.code_mfa,
        adresse_client(request),
        request.headers.get("user-agent"),
        request.state.trace_id,
    )
    return valider(bd, resultat)


@routeur.post("/deconnexion")
def deconnexion(ctx: Contexte = Depends(contexte_partiel), bd: SessionBD = Depends(base)):
    auth.deconnecter(bd, ctx.session)
    audit.enregistrer_ctx(bd, ctx, "DECONNEXION")
    return valider(bd, {"message": "Session fermée."})


@routeur.get("/moi")
def moi(ctx: Contexte = Depends(contexte_partiel)):
    u = ctx.utilisateur
    return {
        "id": u.id,
        "identifiant": u.identifiant,
        "nom": u.nom,
        "prenoms": u.prenoms,
        "grade": u.grade,
        "unite_id": u.unite_id,
        "unite_nom": u.unite.nom,
        "role": u.role.libelle,
        "role_code": u.role.code,
        "portee": u.portee,
        "permissions": sorted(ctx.permissions),
        "libelles_permissions": {k: v for k, v in LIBELLES_PERMISSIONS.items() if k in ctx.permissions},
        "mfa_active": u.mfa_active,
        "mfa_requise": auth.mfa_requise(u),
        "type_session": ctx.session.type_session,
        "session_expire_le": ctx.session.expire_le,
    }


@routeur.post("/mot-de-passe")
def changer_mot_de_passe(
    donnees: schemas.ChangementMotDePasse,
    ctx: Contexte = Depends(contexte_partiel),
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    return valider(bd, auth.changer_mot_de_passe(bd, p, ctx, donnees.ancien_mot_de_passe, donnees.nouveau_mot_de_passe))


@routeur.post("/mfa/preparation")
def preparer_mfa(ctx: Contexte = Depends(contexte_mfa), bd: SessionBD = Depends(base)):
    return valider(bd, auth.preparer_mfa(bd, ctx))


@routeur.post("/mfa/activation")
def activer_mfa(donnees: schemas.CodeMFA, ctx: Contexte = Depends(contexte_mfa), bd: SessionBD = Depends(base)):
    return valider(bd, auth.activer_mfa(bd, ctx, donnees.code_mfa))


@routeur.post("/reauthentification")
def reauthentifier(
    donnees: schemas.Reauthentification, ctx: Contexte = Depends(contexte_partiel), bd: SessionBD = Depends(base)
):
    return valider(bd, auth.reauthentifier(bd, ctx, donnees.mot_de_passe, donnees.code_mfa))
