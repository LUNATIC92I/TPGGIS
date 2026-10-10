"""Routes d'administration : unites, roles, utilisateurs, referentiels,
parametres, audit, validations, conservation et supervision."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.api.deps import base, contexte, parametres, valider
from tpgis.server.config import ParametresServeur
from tpgis.server.database.models import EvenementAudit
from tpgis.server.services import administration, audit, retention, validations
from tpgis.server.services.auth import exiger_reauthentification_recente
from tpgis.server.services.commun import PARAMETRES_DEFAUT, ecrire_parametre, lire_parametre, paginer
from tpgis.server.services.contexte import Contexte
from tpgis.shared import schemas
from tpgis.shared.permissions import LIBELLES_PERMISSIONS, Permission

routeur = APIRouter()


# Unites


@routeur.get("/unites", tags=["Unités"])
def lister_unites(actives: bool = False, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return administration.lister_unites(bd, ctx, actives)


@routeur.post("/unites", tags=["Unités"], status_code=201)
def creer_unite(donnees: schemas.UniteCreation, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, administration.creer_unite(bd, ctx, donnees))


@routeur.patch("/unites/{unite_id}", tags=["Unités"])
def modifier_unite(
    unite_id: str, donnees: schemas.UniteModification, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)
):
    return valider(bd, administration.modifier_unite(bd, ctx, unite_id, donnees))


@routeur.get("/unites/{unite_id}/agents", tags=["Unités"])
def agents_unite(unite_id: str, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return administration.agents_assignables(bd, ctx, unite_id)


# Roles et permissions


@routeur.get("/permissions", tags=["Habilitations"])
def catalogue_permissions(ctx: Contexte = Depends(contexte)):
    ctx.exiger(Permission.ROLE_GERER)
    return [{"code": p.value, "libelle": LIBELLES_PERMISSIONS[p]} for p in Permission]


@routeur.get("/roles", tags=["Habilitations"])
def lister_roles(ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return administration.lister_roles(bd, ctx)


@routeur.post("/roles", tags=["Habilitations"], status_code=201)
def creer_role(donnees: schemas.RoleCreation, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, administration.creer_role(bd, ctx, donnees))


@routeur.patch("/roles/{role_id}", tags=["Habilitations"])
def modifier_role(
    role_id: str,
    donnees: schemas.RoleModification,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    return valider(bd, administration.modifier_role(bd, ctx, p, role_id, donnees))


# Utilisateurs


@routeur.get("/utilisateurs", tags=["Utilisateurs"])
def lister_utilisateurs(
    texte: str | None = Query(None, max_length=64),
    unite_id: str | None = None,
    page: int = 1,
    taille: int = 50,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    return administration.lister_utilisateurs(bd, ctx, texte, page, taille, unite_id)


@routeur.post("/utilisateurs", tags=["Utilisateurs"], status_code=201)
def creer_utilisateur(
    donnees: schemas.UtilisateurCreation,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    return valider(bd, administration.creer_utilisateur(bd, ctx, p, donnees))


@routeur.patch("/utilisateurs/{utilisateur_id}", tags=["Utilisateurs"])
def modifier_utilisateur(
    utilisateur_id: str,
    donnees: schemas.UtilisateurModification,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    return valider(bd, administration.modifier_utilisateur(bd, ctx, utilisateur_id, donnees))


@routeur.post("/utilisateurs/{utilisateur_id}/desactivation", tags=["Utilisateurs"])
def desactiver(
    utilisateur_id: str,
    donnees: schemas.Desactivation,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    return valider(bd, administration.desactiver_utilisateur(bd, ctx, utilisateur_id, donnees.motif))


@routeur.post("/utilisateurs/{utilisateur_id}/reactivation", tags=["Utilisateurs"])
def reactiver(
    utilisateur_id: str,
    donnees: schemas.Desactivation,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    return valider(bd, administration.reactiver_utilisateur(bd, ctx, utilisateur_id, donnees.motif))


@routeur.post("/utilisateurs/{utilisateur_id}/revocation-sessions", tags=["Utilisateurs"])
def revoquer(utilisateur_id: str, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, administration.revoquer_sessions_utilisateur(bd, ctx, utilisateur_id))


@routeur.post("/utilisateurs/{utilisateur_id}/reinitialisation-mot-de-passe", tags=["Utilisateurs"])
def reinitialiser_mdp(
    utilisateur_id: str,
    donnees: schemas.ReinitialisationMotDePasse,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    return valider(bd, administration.reinitialiser_mot_de_passe(bd, ctx, p, utilisateur_id, donnees))


@routeur.post("/utilisateurs/{utilisateur_id}/reinitialisation-mfa", tags=["Utilisateurs"])
def reinitialiser_mfa(
    utilisateur_id: str,
    donnees: schemas.Desactivation,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    return valider(bd, administration.reinitialiser_mfa(bd, ctx, p, utilisateur_id, donnees.motif))


@routeur.post("/utilisateurs/{utilisateur_id}/role", tags=["Utilisateurs"])
def changer_role(
    utilisateur_id: str,
    donnees: schemas.ChangementRole,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    return valider(bd, administration.demander_changement_role(bd, ctx, utilisateur_id, donnees))


# Referentiel des categories


@routeur.get("/categories", tags=["Référentiel"])
def lister_categories(toutes: bool = False, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return administration.lister_categories(bd, ctx, not toutes)


@routeur.post("/categories", tags=["Référentiel"], status_code=201)
def creer_categorie(
    donnees: schemas.CategorieCreation, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)
):
    return valider(bd, administration.creer_categorie(bd, ctx, donnees))


@routeur.patch("/categories/{categorie_id}", tags=["Référentiel"])
def modifier_categorie(
    categorie_id: str,
    donnees: schemas.CategorieModification,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    return valider(bd, administration.modifier_categorie(bd, ctx, categorie_id, donnees))


# Parametres


@routeur.get("/parametres", tags=["Administration"])
def lister_parametres(ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    # Les finalites sont lisibles par tous ; les autres parametres par les administrateurs.
    if not ctx.a(Permission.PARAMETRES_GERER):
        return {"recherche.finalites": lire_parametre(bd, "recherche.finalites")}
    return {
        cle: {"valeur": lire_parametre(bd, cle), "description": d["description"]}
        for cle, d in PARAMETRES_DEFAUT.items()
    }


@routeur.put("/parametres/{cle}", tags=["Administration"])
def modifier_parametre(
    cle: str,
    donnees: schemas.ModificationParametre,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    ctx.exiger(Permission.PARAMETRES_GERER)
    exiger_reauthentification_recente(ctx, p)
    avant = lire_parametre(bd, cle)
    ecrire_parametre(bd, cle, donnees.valeur, ctx.utilisateur.identifiant)
    audit.enregistrer_ctx(
        bd,
        ctx,
        "PARAMETRE_MODIFICATION",
        type_ressource="parametre",
        ressource_id=cle,
        details={"avant": avant, "apres": donnees.valeur},
    )
    return valider(bd, {"cle": cle, "valeur": donnees.valeur})


# Journal d'audit


def _serialiser_audit(e: EvenementAudit) -> dict:
    return {
        "id": e.id,
        "horodatage": e.horodatage,
        "identifiant": e.identifiant,
        "action": e.action,
        "type_ressource": e.type_ressource,
        "ressource_id": e.ressource_id,
        "unite_id": e.unite_id,
        "resultat": e.resultat,
        "finalite": e.finalite,
        "trace_id": e.trace_id,
        "adresse_ip": e.adresse_ip,
        "details": e.details,
        "empreinte": e.empreinte,
    }


@routeur.get("/audit", tags=["Audit"])
def consulter_audit(
    identifiant: str | None = None,
    action: str | None = None,
    resultat: str | None = None,
    ressource_id: str | None = None,
    trace_id: str | None = None,
    page: int = 1,
    taille: int = 100,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    ctx.exiger(Permission.AUDIT_LIRE)
    requete = select(EvenementAudit).order_by(EvenementAudit.id.desc())
    if identifiant:
        requete = requete.where(EvenementAudit.identifiant == identifiant)
    if action:
        requete = requete.where(EvenementAudit.action == action)
    if resultat:
        requete = requete.where(EvenementAudit.resultat == resultat)
    if ressource_id:
        requete = requete.where(EvenementAudit.ressource_id == ressource_id)
    if trace_id:
        requete = requete.where(EvenementAudit.trace_id == trace_id)
    elements, total = paginer(bd, requete, page, taille)
    resultat_page = {
        "elements": [_serialiser_audit(e) for e in elements],
        "total": total,
        "page": page,
        "taille": taille,
    }
    audit.enregistrer_ctx(
        bd,
        ctx,
        "AUDIT_CONSULTATION",
        type_ressource="audit",
        details={"identifiant": identifiant, "action": action, "page": page},
    )
    return valider(bd, resultat_page)


@routeur.get("/audit/verification", tags=["Audit"])
def verifier_audit(ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    ctx.exiger(Permission.AUDIT_LIRE)
    from sqlalchemy.orm import Session as S

    with S(bind=bd.get_bind()) as lecture:
        resultat = audit.verifier_chaine(lecture)
    audit.enregistrer_ctx(bd, ctx, "AUDIT_VERIFICATION", type_ressource="audit", details=resultat)
    return valider(bd, resultat)


# Double validation


@routeur.get("/validations", tags=["Double validation"])
def lister_validations(
    statut: str | None = None,
    page: int = 1,
    taille: int = 50,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    return validations.lister(bd, ctx, statut, page, taille)


@routeur.post("/validations/{demande_id}/decision", tags=["Double validation"])
def decider(
    demande_id: str,
    donnees: schemas.DecisionValidation,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    exiger_reauthentification_recente(ctx, p)
    return valider(bd, validations.decider(bd, ctx, demande_id, donnees.approuver, donnees.commentaire))


# Conservation des donnees


@routeur.get("/conservation/rapport", tags=["Conservation"])
def rapport_conservation(ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return retention.rapport(bd, ctx)


@routeur.post("/conservation/purge", tags=["Conservation"])
def demander_purge(donnees: schemas.DemandePurge, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, retention.demander_purge(bd, ctx, donnees.motif))
