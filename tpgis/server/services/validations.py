"""Double validation des actions critiques.

Une demande est deposee par un premier utilisateur puis approuvee par un
second utilisateur habilite, different du demandeur. L'action n'est executee
qu'au moment de l'approbation, dans la meme transaction.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.database.base import maintenant
from tpgis.server.database.models import DemandeValidation, Role, Utilisateur
from tpgis.server.services import audit
from tpgis.server.services.commun import paginer
from tpgis.server.services.contexte import Contexte
from tpgis.server.services.erreurs import AccesRefuse, Conflit, ErreurMetier, Introuvable
from tpgis.shared.enums import StatutValidation, TypeValidation
from tpgis.shared.permissions import Permission

# Permission metier requise, en plus de VALIDATION_APPROUVER, pour approuver.
PERMISSION_APPROBATION = {
    TypeValidation.FUSION_PERSONNES: Permission.PERSONNE_FUSIONNER,
    TypeValidation.ATTRIBUTION_ROLE_PRIVILEGIE: Permission.UTILISATEUR_GERER,
    TypeValidation.SUPPRESSION_CAPTURE_BIOMETRIQUE: Permission.VALIDATION_APPROUVER,
    TypeValidation.PURGE_DONNEES: Permission.VALIDATION_APPROUVER,
}


def serialiser(d: DemandeValidation) -> dict:
    return {
        "id": d.id,
        "type_action": d.type_action,
        "resume": d.resume,
        "motif": d.motif,
        "demandeur_id": d.demandeur_id,
        "unite_id": d.unite_id,
        "statut": d.statut,
        "valideur_id": d.valideur_id,
        "decidee_le": d.decidee_le,
        "commentaire": d.commentaire,
        "resultat": d.resultat,
        "cree_le": d.cree_le,
    }


def creer_demande(
    bd: SessionBD, ctx: Contexte, type_action: TypeValidation, charge: dict, resume: str, motif: str
) -> dict:
    d = DemandeValidation(
        type_action=type_action,
        charge_utile=charge,
        resume=resume[:255],
        motif=motif,
        demandeur_id=ctx.uid,
        unite_id=ctx.utilisateur.unite_id,
        statut=StatutValidation.EN_ATTENTE,
    )
    bd.add(d)
    bd.flush()
    audit.enregistrer_ctx(
        bd,
        ctx,
        "VALIDATION_DEMANDE",
        type_ressource="demande_validation",
        ressource_id=d.id,
        details={"type_action": str(type_action), "resume": resume},
    )
    return serialiser(d)


def lister(bd: SessionBD, ctx: Contexte, statut: str | None, page: int, taille: int) -> dict:
    requete = select(DemandeValidation).order_by(DemandeValidation.cree_le.desc())
    if not ctx.a(Permission.VALIDATION_APPROUVER):
        requete = requete.where(DemandeValidation.demandeur_id == ctx.uid)
    elif ctx.unites_accessibles is not None:
        requete = requete.where(DemandeValidation.unite_id.in_(ctx.unites_accessibles))
    if statut:
        requete = requete.where(DemandeValidation.statut == statut)
    elements, total = paginer(bd, requete, page, taille)
    return {"elements": [serialiser(d) for d in elements], "total": total, "page": page, "taille": taille}


def _executer(bd: SessionBD, ctx: Contexte, d: DemandeValidation, demandeur: Utilisateur) -> str:
    charge = d.charge_utile
    if d.type_action == TypeValidation.ATTRIBUTION_ROLE_PRIVILEGIE:
        from tpgis.server.services.administration import appliquer_changement_role

        u = bd.get(Utilisateur, charge["utilisateur_id"])
        role = bd.get(Role, charge["role_id"])
        if u is None or role is None:
            raise Introuvable("Compte ou rôle disparu depuis la demande.")
        appliquer_changement_role(bd, ctx, u, role, d.motif)
        return f"Rôle {role.code} attribué à {u.identifiant}."
    if d.type_action == TypeValidation.FUSION_PERSONNES:
        from tpgis.server.services.personnes import executer_fusion

        return executer_fusion(bd, ctx, charge["personne_conservee_id"], charge["personne_absorbee_id"], d.motif)
    if d.type_action == TypeValidation.SUPPRESSION_CAPTURE_BIOMETRIQUE:
        from tpgis.server.services.biometrie import executer_suppression

        return executer_suppression(bd, ctx, charge["capture_id"], d.motif)
    if d.type_action == TypeValidation.PURGE_DONNEES:
        from tpgis.server.services.retention import executer_purge

        return executer_purge(bd, ctx, d.motif)
    raise ErreurMetier("Type d'action inconnu.")


def decider(bd: SessionBD, ctx: Contexte, demande_id: str, approuver: bool, commentaire: str | None) -> dict:
    ctx.exiger(Permission.VALIDATION_APPROUVER)
    d = bd.get(DemandeValidation, demande_id)
    if d is None or not ctx.unite_accessible(d.unite_id):
        raise Introuvable("Demande introuvable ou hors périmètre.")
    if d.statut != StatutValidation.EN_ATTENTE:
        raise Conflit("Cette demande a déjà été traitée.")
    if d.demandeur_id == ctx.uid:
        audit.enregistrer_ctx(
            bd,
            ctx,
            "VALIDATION_DECISION",
            resultat="REFUS",
            type_ressource="demande_validation",
            ressource_id=d.id,
            details={"raison": "auto_validation"},
        )
        bd.commit()
        raise AccesRefuse("Une demande ne peut pas être validée par son auteur (double validation).")
    ctx.exiger(PERMISSION_APPROBATION[TypeValidation(d.type_action)])
    d.valideur_id = ctx.uid
    d.decidee_le = maintenant()
    d.commentaire = commentaire
    if not approuver:
        d.statut = StatutValidation.REJETEE
    else:
        demandeur = bd.get(Utilisateur, d.demandeur_id)
        d.resultat = _executer(bd, ctx, d, demandeur)
        d.statut = StatutValidation.EXECUTEE
    audit.enregistrer_ctx(
        bd,
        ctx,
        "VALIDATION_DECISION",
        type_ressource="demande_validation",
        ressource_id=d.id,
        details={"approuvee": approuver, "type_action": d.type_action},
    )
    return serialiser(d)
