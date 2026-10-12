"""Administration : unites, roles, utilisateurs et referentiel des faits."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.config import ParametresServeur
from tpgis.server.database.base import maintenant
from tpgis.server.database.models import CategorieFait, Role, RolePermission, Unite, Utilisateur
from tpgis.server.security import passwords
from tpgis.server.services import audit
from tpgis.server.services.auth import revoquer_sessions
from tpgis.server.services.commun import appliquer_modifications, historiser, paginer
from tpgis.server.services.contexte import Contexte
from tpgis.server.services.erreurs import AccesRefuse, Conflit, DonneesInvalides, Introuvable
from tpgis.shared import schemas
from tpgis.shared.enums import Portee, StatutValidation, TypeValidation
from tpgis.shared.permissions import Permission, est_privilegie

# Unites


def serialiser_unite(u: Unite) -> dict:
    return {
        "id": u.id,
        "code": u.code,
        "nom": u.nom,
        "type_unite": u.type_unite,
        "corps": u.corps,
        "parent_id": u.parent_id,
        "province_code": u.province_code,
        "ville": u.ville,
        "latitude": u.latitude,
        "longitude": u.longitude,
        "telephone": u.telephone,
        "active": u.active,
    }


def lister_unites(bd: SessionBD, ctx: Contexte, actives_seulement: bool = False) -> list[dict]:
    ctx.exiger(Permission.UNITE_LIRE)
    requete = select(Unite).order_by(Unite.corps, Unite.code)
    if actives_seulement:
        requete = requete.where(Unite.active.is_(True))
    return [serialiser_unite(u) for u in bd.execute(requete).scalars()]


def _verifier_parent(bd: SessionBD, parent_id: str | None, unite_id: str | None = None) -> None:
    if parent_id is None:
        return
    if bd.get(Unite, parent_id) is None:
        raise DonneesInvalides("Unité parente inconnue.")
    # Empeche les cycles dans l'arborescence.
    courant = parent_id
    vus = set()
    while courant:
        if courant == unite_id or courant in vus:
            raise DonneesInvalides("Cette rattachement créerait une boucle dans la hiérarchie des unités.")
        vus.add(courant)
        courant = bd.execute(select(Unite.parent_id).where(Unite.id == courant)).scalar()


def creer_unite(bd: SessionBD, ctx: Contexte, donnees: schemas.UniteCreation) -> dict:
    ctx.exiger(Permission.UNITE_GERER)
    if bd.execute(select(Unite.id).where(Unite.code == donnees.code)).first():
        raise Conflit("Une unité porte déjà ce code.")
    _verifier_parent(bd, donnees.parent_id)
    unite = Unite(**donnees.model_dump())
    bd.add(unite)
    bd.flush()
    historiser(bd, ctx, "unite", unite.id, "CREATION", donnees.model_dump())
    audit.enregistrer_ctx(bd, ctx, "UNITE_CREATION", type_ressource="unite", ressource_id=unite.id)
    return serialiser_unite(unite)


def modifier_unite(bd: SessionBD, ctx: Contexte, unite_id: str, donnees: schemas.UniteModification) -> dict:
    ctx.exiger(Permission.UNITE_GERER)
    unite = bd.get(Unite, unite_id)
    if unite is None:
        raise Introuvable("Unité introuvable.")
    valeurs = donnees.model_dump(exclude_unset=True)
    if "parent_id" in valeurs:
        _verifier_parent(bd, valeurs["parent_id"], unite.id)
    changements = appliquer_modifications(unite, valeurs)
    historiser(bd, ctx, "unite", unite.id, "MODIFICATION", changements)
    audit.enregistrer_ctx(
        bd,
        ctx,
        "UNITE_MODIFICATION",
        type_ressource="unite",
        ressource_id=unite.id,
        details={"champs": list(changements)},
    )
    return serialiser_unite(unite)


# Roles


def serialiser_role(r: Role) -> dict:
    return {
        "id": r.id,
        "code": r.code,
        "libelle": r.libelle,
        "description": r.description,
        "portee_defaut": r.portee_defaut,
        "systeme": r.systeme,
        "actif": r.actif,
        "permissions": sorted(r.codes_permissions),
        "privilegie": est_privilegie(r.codes_permissions),
    }


def lister_roles(bd: SessionBD, ctx: Contexte) -> list[dict]:
    if not (ctx.a(Permission.ROLE_GERER) or ctx.a(Permission.UTILISATEUR_LIRE)):
        ctx.exiger(Permission.ROLE_GERER)
    return [serialiser_role(r) for r in bd.execute(select(Role).order_by(Role.libelle)).scalars()]


def _valider_permissions(permissions: list[str]) -> set[str]:
    connues = {p.value for p in Permission}
    inconnues = set(permissions) - connues
    if inconnues:
        raise DonneesInvalides("Permissions inconnues : {liste}", parametres={"liste": ", ".join(sorted(inconnues))})
    return set(permissions)


def creer_role(bd: SessionBD, ctx: Contexte, donnees: schemas.RoleCreation) -> dict:
    ctx.exiger(Permission.ROLE_GERER)
    if bd.execute(select(Role.id).where(Role.code == donnees.code)).first():
        raise Conflit("Un rôle porte déjà ce code.")
    perms = _valider_permissions(donnees.permissions)
    role = Role(
        code=donnees.code,
        libelle=donnees.libelle,
        description=donnees.description,
        portee_defaut=donnees.portee_defaut,
        systeme=False,
        actif=True,
    )
    role.permissions = [RolePermission(permission=p) for p in sorted(perms)]
    bd.add(role)
    bd.flush()
    historiser(bd, ctx, "role", role.id, "CREATION", {"permissions": sorted(perms)})
    audit.enregistrer_ctx(
        bd,
        ctx,
        "ROLE_CREATION",
        type_ressource="role",
        ressource_id=role.id,
        details={"code": role.code, "permissions": sorted(perms)},
    )
    return serialiser_role(role)


def modifier_role(
    bd: SessionBD, ctx: Contexte, p: ParametresServeur, role_id: str, donnees: schemas.RoleModification
) -> dict:
    from tpgis.server.services.auth import exiger_reauthentification_recente

    ctx.exiger(Permission.ROLE_GERER)
    exiger_reauthentification_recente(ctx, p)
    role = bd.get(Role, role_id)
    if role is None:
        raise Introuvable("Rôle introuvable.")
    if role.id == ctx.utilisateur.role_id:
        raise AccesRefuse("Vous ne pouvez pas modifier votre propre rôle.")
    valeurs = donnees.model_dump(exclude_unset=True)
    changements = {}
    if "permissions" in valeurs:
        nouvelles = _valider_permissions(valeurs.pop("permissions"))
        anciennes = role.codes_permissions
        if nouvelles != anciennes:
            if est_privilegie(nouvelles) and not est_privilegie(anciennes):
                raise DonneesInvalides(
                    "Rendre un rôle privilégié exige une double validation : créer un nouveau rôle "
                    "puis demander l'attribution aux comptes concernés."
                )
            role.permissions = [RolePermission(permission=x) for x in sorted(nouvelles)]
            changements["permissions"] = {
                "ajoutees": sorted(nouvelles - anciennes),
                "retirees": sorted(anciennes - nouvelles),
            }
            # Les droits sont recalcules a chaque requete ; on revoque tout de
            # meme les sessions pour forcer une reconnexion consciente.
            for (uid,) in bd.execute(select(Utilisateur.id).where(Utilisateur.role_id == role.id)):
                revoquer_sessions(bd, uid, "modification_role")
    changements.update(appliquer_modifications(role, valeurs))
    historiser(bd, ctx, "role", role.id, "MODIFICATION", changements)
    audit.enregistrer_ctx(
        bd, ctx, "ROLE_MODIFICATION", type_ressource="role", ressource_id=role.id, details=changements
    )
    return serialiser_role(role)


# Utilisateurs


def serialiser_utilisateur(u: Utilisateur) -> dict:
    return {
        "id": u.id,
        "identifiant": u.identifiant,
        "nom": u.nom,
        "prenoms": u.prenoms,
        "matricule": u.matricule,
        "grade": u.grade,
        "unite_id": u.unite_id,
        "unite_nom": u.unite.nom if u.unite else None,
        "role_id": u.role_id,
        "role_libelle": u.role.libelle if u.role else None,
        "portee": u.portee,
        "actif": u.actif,
        "mfa_active": u.mfa_active,
        "verrouille_jusqua": u.verrouille_jusqua,
        "derniere_connexion": u.derniere_connexion,
        "doit_changer_mot_de_passe": u.doit_changer_mot_de_passe,
    }


def lister_utilisateurs(
    bd: SessionBD, ctx: Contexte, texte: str | None, page: int, taille: int, unite_id: str | None = None
) -> dict:
    ctx.exiger(Permission.UTILISATEUR_LIRE)
    requete = select(Utilisateur).order_by(Utilisateur.nom, Utilisateur.prenoms)
    if ctx.unites_accessibles is not None:
        requete = requete.where(Utilisateur.unite_id.in_(ctx.unites_accessibles))
    if unite_id:
        requete = requete.where(Utilisateur.unite_id == unite_id)
    if texte:
        motif = f"%{texte.strip()}%"
        requete = requete.where(
            or_(Utilisateur.identifiant.ilike(motif), Utilisateur.nom.ilike(motif), Utilisateur.matricule.ilike(motif))
        )
    elements, total = paginer(bd, requete, page, taille)
    return {"elements": [serialiser_utilisateur(u) for u in elements], "total": total, "page": page, "taille": taille}


def agents_assignables(bd: SessionBD, ctx: Contexte, unite_id: str) -> list[dict]:
    """Liste minimale des agents d'une unite pour l'attribution d'un dossier."""
    if not ctx.unite_accessible(unite_id):
        raise Introuvable("Unité hors de votre périmètre.")
    lignes = bd.execute(
        select(Utilisateur)
        .where(Utilisateur.unite_id == unite_id, Utilisateur.actif.is_(True))
        .order_by(Utilisateur.nom)
    ).scalars()
    return [{"id": u.id, "nom_complet": f"{u.grade or ''} {u.nom} {u.prenoms}".strip()} for u in lignes]


def _obtenir_utilisateur(bd: SessionBD, ctx: Contexte, utilisateur_id: str) -> Utilisateur:
    u = bd.get(Utilisateur, utilisateur_id)
    if u is None or not ctx.unite_accessible(u.unite_id):
        raise Introuvable("Compte utilisateur introuvable ou hors périmètre.")
    return u


def creer_utilisateur(bd: SessionBD, ctx: Contexte, p: ParametresServeur, donnees: schemas.UtilisateurCreation) -> dict:
    ctx.exiger(Permission.UTILISATEUR_GERER)
    if bd.execute(select(Utilisateur.id).where(Utilisateur.identifiant == donnees.identifiant)).first():
        raise Conflit("Cet identifiant est déjà utilisé.")
    if (
        donnees.matricule
        and bd.execute(select(Utilisateur.id).where(Utilisateur.matricule == donnees.matricule)).first()
    ):
        raise Conflit("Ce matricule est déjà associé à un compte.")
    role = bd.get(Role, donnees.role_id)
    if role is None or not role.actif:
        raise DonneesInvalides("Rôle inconnu ou inactif.")
    if est_privilegie(role.codes_permissions):
        raise DonneesInvalides(
            "Un rôle privilégié ne peut pas être attribué directement : créer le compte avec un rôle "
            "standard puis déposer une demande d'attribution soumise à double validation."
        )
    unite = bd.get(Unite, donnees.unite_id)
    if unite is None or not ctx.unite_accessible(unite.id):
        raise DonneesInvalides("Unité inconnue ou hors de votre périmètre.")
    if (donnees.portee or role.portee_defaut) == Portee.NATIONALE and ctx.portee != Portee.NATIONALE:
        raise AccesRefuse("Vous ne pouvez pas attribuer un périmètre plus large que le vôtre.")
    erreurs = passwords.controler_politique(
        donnees.mot_de_passe_initial, p.mot_de_passe_longueur_min, donnees.identifiant
    )
    if erreurs:
        raise DonneesInvalides(" ".join(erreurs))
    u = Utilisateur(
        identifiant=donnees.identifiant,
        nom=donnees.nom,
        prenoms=donnees.prenoms,
        matricule=donnees.matricule,
        grade=donnees.grade,
        unite_id=unite.id,
        role_id=role.id,
        portee=donnees.portee or role.portee_defaut,
        mot_de_passe_hash=passwords.hacher(donnees.mot_de_passe_initial),
        doit_changer_mot_de_passe=True,
        actif=True,
    )
    bd.add(u)
    bd.flush()
    historiser(bd, ctx, "utilisateur", u.id, "CREATION", {"role": role.code, "unite": unite.code, "portee": u.portee})
    audit.enregistrer_ctx(
        bd,
        ctx,
        "UTILISATEUR_CREATION",
        type_ressource="utilisateur",
        ressource_id=u.id,
        details={"identifiant": u.identifiant, "role": role.code},
    )
    return serialiser_utilisateur(u)


def modifier_utilisateur(
    bd: SessionBD, ctx: Contexte, utilisateur_id: str, donnees: schemas.UtilisateurModification
) -> dict:
    ctx.exiger(Permission.UTILISATEUR_GERER)
    u = _obtenir_utilisateur(bd, ctx, utilisateur_id)
    valeurs = donnees.model_dump(exclude_unset=True)
    if u.id == ctx.uid and ("portee" in valeurs or "unite_id" in valeurs):
        raise AccesRefuse("Vous ne pouvez pas modifier votre propre périmètre.")
    if "unite_id" in valeurs:
        if bd.get(Unite, valeurs["unite_id"]) is None or not ctx.unite_accessible(valeurs["unite_id"]):
            raise DonneesInvalides("Unité inconnue ou hors de votre périmètre.")
    if valeurs.get("portee") == Portee.NATIONALE and ctx.portee != Portee.NATIONALE:
        raise AccesRefuse("Vous ne pouvez pas attribuer un périmètre plus large que le vôtre.")
    changements = appliquer_modifications(u, valeurs)
    if {"portee", "unite_id"} & set(changements):
        revoquer_sessions(bd, u.id, "modification_perimetre")
    historiser(bd, ctx, "utilisateur", u.id, "MODIFICATION", changements)
    audit.enregistrer_ctx(
        bd, ctx, "UTILISATEUR_MODIFICATION", type_ressource="utilisateur", ressource_id=u.id, details=changements
    )
    return serialiser_utilisateur(u)


def desactiver_utilisateur(bd: SessionBD, ctx: Contexte, utilisateur_id: str, motif: str) -> dict:
    ctx.exiger(Permission.UTILISATEUR_GERER)
    u = _obtenir_utilisateur(bd, ctx, utilisateur_id)
    if u.id == ctx.uid:
        raise AccesRefuse("Vous ne pouvez pas désactiver votre propre compte.")
    u.actif = False
    u.desactive_le = maintenant()
    u.motif_desactivation = motif
    nb = revoquer_sessions(bd, u.id, "desactivation_compte")
    historiser(bd, ctx, "utilisateur", u.id, "DESACTIVATION", {"motif": motif})
    audit.enregistrer_ctx(
        bd,
        ctx,
        "UTILISATEUR_DESACTIVATION",
        type_ressource="utilisateur",
        ressource_id=u.id,
        details={"motif": motif, "sessions_revoquees": nb},
    )
    return serialiser_utilisateur(u)


def reactiver_utilisateur(bd: SessionBD, ctx: Contexte, utilisateur_id: str, motif: str) -> dict:
    ctx.exiger(Permission.UTILISATEUR_GERER)
    u = _obtenir_utilisateur(bd, ctx, utilisateur_id)
    u.actif = True
    u.desactive_le = None
    u.motif_desactivation = None
    u.doit_changer_mot_de_passe = True
    historiser(bd, ctx, "utilisateur", u.id, "REACTIVATION", {"motif": motif})
    audit.enregistrer_ctx(
        bd, ctx, "UTILISATEUR_REACTIVATION", type_ressource="utilisateur", ressource_id=u.id, details={"motif": motif}
    )
    return serialiser_utilisateur(u)


def revoquer_sessions_utilisateur(bd: SessionBD, ctx: Contexte, utilisateur_id: str) -> dict:
    ctx.exiger(Permission.UTILISATEUR_GERER)
    u = _obtenir_utilisateur(bd, ctx, utilisateur_id)
    nb = revoquer_sessions(bd, u.id, "revocation_administrative")
    audit.enregistrer_ctx(
        bd,
        ctx,
        "SESSIONS_REVOCATION",
        type_ressource="utilisateur",
        ressource_id=u.id,
        details={"sessions_revoquees": nb},
    )
    return {"sessions_revoquees": nb}


def reinitialiser_mot_de_passe(
    bd: SessionBD, ctx: Contexte, p: ParametresServeur, utilisateur_id: str, donnees: schemas.ReinitialisationMotDePasse
) -> dict:
    """Reinitialisation par un administrateur : mot de passe temporaire a
    changer a la premiere connexion, sessions revoquees, MFA conservee."""
    from tpgis.server.services.auth import exiger_reauthentification_recente

    ctx.exiger(Permission.UTILISATEUR_GERER)
    exiger_reauthentification_recente(ctx, p)
    u = _obtenir_utilisateur(bd, ctx, utilisateur_id)
    if u.id == ctx.uid:
        raise AccesRefuse("Utilisez la fonction de changement de votre propre mot de passe.")
    erreurs = passwords.controler_politique(donnees.mot_de_passe_temporaire, p.mot_de_passe_longueur_min, u.identifiant)
    if erreurs:
        raise DonneesInvalides(" ".join(erreurs))
    u.mot_de_passe_hash = passwords.hacher(donnees.mot_de_passe_temporaire)
    u.doit_changer_mot_de_passe = True
    u.echecs_connexion = 0
    u.verrouille_jusqua = None
    nb = revoquer_sessions(bd, u.id, "reinitialisation_mot_de_passe")
    historiser(bd, ctx, "utilisateur", u.id, "REINITIALISATION_MOT_DE_PASSE", {"motif": donnees.motif})
    audit.enregistrer_ctx(
        bd,
        ctx,
        "MOT_DE_PASSE_REINITIALISATION",
        type_ressource="utilisateur",
        ressource_id=u.id,
        details={"motif": donnees.motif, "sessions_revoquees": nb},
    )
    return {"message": "Mot de passe temporaire défini. L'utilisateur devra le changer à la connexion."}


def reinitialiser_mfa(bd: SessionBD, ctx: Contexte, p: ParametresServeur, utilisateur_id: str, motif: str) -> dict:
    from tpgis.server.services.auth import exiger_reauthentification_recente

    ctx.exiger(Permission.UTILISATEUR_GERER)
    exiger_reauthentification_recente(ctx, p)
    u = _obtenir_utilisateur(bd, ctx, utilisateur_id)
    if u.id == ctx.uid:
        raise AccesRefuse("Vous ne pouvez pas réinitialiser votre propre second facteur.")
    u.mfa_active = False
    u.mfa_secret = None
    u.mfa_dernier_pas = None
    revoquer_sessions(bd, u.id, "reinitialisation_mfa")
    audit.enregistrer_ctx(
        bd, ctx, "MFA_REINITIALISATION", type_ressource="utilisateur", ressource_id=u.id, details={"motif": motif}
    )
    return {"message": "Second facteur réinitialisé : l'utilisateur devra en enrôler un nouveau."}


def demander_changement_role(
    bd: SessionBD, ctx: Contexte, utilisateur_id: str, donnees: schemas.ChangementRole
) -> dict:
    """Un role standard est attribue immediatement ; un role privilegie fait
    l'objet d'une demande de double validation."""
    from tpgis.server.services.validations import creer_demande

    ctx.exiger(Permission.UTILISATEUR_GERER)
    u = _obtenir_utilisateur(bd, ctx, utilisateur_id)
    if u.id == ctx.uid:
        raise AccesRefuse("Vous ne pouvez pas modifier votre propre rôle.")
    role = bd.get(Role, donnees.role_id)
    if role is None or not role.actif:
        raise DonneesInvalides("Rôle inconnu ou inactif.")
    if est_privilegie(role.codes_permissions):
        demande = creer_demande(
            bd,
            ctx,
            TypeValidation.ATTRIBUTION_ROLE_PRIVILEGIE,
            {"utilisateur_id": u.id, "role_id": role.id},
            f"Attribution du rôle {role.libelle} à {u.identifiant}",
            donnees.motif,
        )
        return {"statut": StatutValidation.EN_ATTENTE, "demande_validation": demande}
    appliquer_changement_role(bd, ctx, u, role, donnees.motif)
    return {"statut": "APPLIQUE", "utilisateur": serialiser_utilisateur(u)}


def appliquer_changement_role(bd: SessionBD, ctx: Contexte, u: Utilisateur, role: Role, motif: str) -> None:
    ancien = u.role.code if u.role else None
    u.role_id = role.id
    u.role = role
    u.portee = role.portee_defaut
    revoquer_sessions(bd, u.id, "changement_role")
    historiser(bd, ctx, "utilisateur", u.id, "CHANGEMENT_ROLE", {"avant": ancien, "apres": role.code, "motif": motif})
    audit.enregistrer_ctx(
        bd,
        ctx,
        "DROITS_MODIFICATION",
        type_ressource="utilisateur",
        ressource_id=u.id,
        details={"role_avant": ancien, "role_apres": role.code, "motif": motif},
    )


# Referentiel des categories de faits


def serialiser_categorie(c: CategorieFait) -> dict:
    return {
        "id": c.id,
        "code": c.code,
        "libelle": c.libelle,
        "description": c.description,
        "reference_legale": c.reference_legale,
        "parent_id": c.parent_id,
        "active": c.active,
        "validee": c.validee,
        "validee_par": c.validee_par,
    }


def lister_categories(bd: SessionBD, ctx: Contexte, actives_seulement: bool = True) -> list[dict]:
    requete = select(CategorieFait).order_by(CategorieFait.libelle)
    if actives_seulement:
        requete = requete.where(CategorieFait.active.is_(True))
    return [serialiser_categorie(c) for c in bd.execute(requete).scalars()]


def creer_categorie(bd: SessionBD, ctx: Contexte, donnees: schemas.CategorieCreation) -> dict:
    ctx.exiger(Permission.CATEGORIE_GERER)
    if bd.execute(select(CategorieFait.id).where(CategorieFait.code == donnees.code)).first():
        raise Conflit("Une catégorie porte déjà ce code.")
    if donnees.parent_id and bd.get(CategorieFait, donnees.parent_id) is None:
        raise DonneesInvalides("Catégorie parente inconnue.")
    if donnees.validee and not donnees.validee_par:
        raise DonneesInvalides("Indiquer l'autorité ayant validé la catégorie.")
    c = CategorieFait(**donnees.model_dump(), active=True)
    bd.add(c)
    bd.flush()
    historiser(bd, ctx, "categorie", c.id, "CREATION", donnees.model_dump())
    audit.enregistrer_ctx(bd, ctx, "CATEGORIE_CREATION", type_ressource="categorie", ressource_id=c.id)
    return serialiser_categorie(c)


def modifier_categorie(bd: SessionBD, ctx: Contexte, categorie_id: str, donnees: schemas.CategorieModification) -> dict:
    ctx.exiger(Permission.CATEGORIE_GERER)
    c = bd.get(CategorieFait, categorie_id)
    if c is None:
        raise Introuvable("Catégorie introuvable.")
    changements = appliquer_modifications(c, donnees.model_dump(exclude_unset=True))
    if c.validee and not c.validee_par:
        raise DonneesInvalides("Indiquer l'autorité ayant validé la catégorie.")
    historiser(bd, ctx, "categorie", c.id, "MODIFICATION", changements)
    audit.enregistrer_ctx(
        bd, ctx, "CATEGORIE_MODIFICATION", type_ressource="categorie", ressource_id=c.id, details=changements
    )
    return serialiser_categorie(c)
