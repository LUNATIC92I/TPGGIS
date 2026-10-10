"""Faits signales et infractions.

Le logiciel ne qualifie jamais automatiquement une personne de coupable et
ne calcule aucun score de dangerosite individuelle. La nature de chaque
information (fait rapporte, verifie, soupcon, decision judiciaire) est
explicite et saisie par un agent habilite.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.database.models import CategorieFait, Dossier, Fait, LienFaitPersonne, Plainte, Unite
from tpgis.server.services import audit
from tpgis.server.services.commun import appliquer_modifications, historique, historiser, paginer, prochain_numero
from tpgis.server.services.contexte import Contexte, filtre_dossiers, filtre_faits, filtre_plaintes
from tpgis.server.services.erreurs import HORS_PERIMETRE, AccesRefuse, Conflit, DonneesInvalides, Introuvable
from tpgis.server.services.plaintes import _personne_accessible
from tpgis.shared import schemas
from tpgis.shared.enums import NatureInformation
from tpgis.shared.permissions import Permission


def serialiser_resume(f: Fait) -> dict:
    return {
        "id": f.id,
        "reference": f.reference,
        "categorie_id": f.categorie_id,
        "categorie": f.categorie.libelle if f.categorie else None,
        "date_declaree": f.date_declaree,
        "lieu": f.lieu,
        "province_code": f.province_code,
        "source_information": f.source_information,
        "nature_information": f.nature_information,
        "etat_verification": f.etat_verification,
        "unite_id": f.unite_id,
        "unite_nom": f.unite.nom if f.unite else None,
        "plainte_id": f.plainte_id,
        "dossier_id": f.dossier_id,
        "version": f.version,
    }


def obtenir(bd: SessionBD, ctx: Contexte, fait_id: str) -> Fait:
    f = bd.execute(select(Fait).where(Fait.id == fait_id, filtre_faits(ctx))).unique().scalar_one_or_none()
    if f is None:
        audit.enregistrer_ctx(
            bd, ctx, "FAIT_CONSULTATION", resultat="REFUS", type_ressource="fait", ressource_id=fait_id
        )
        bd.commit()
        raise Introuvable(HORS_PERIMETRE)
    return f


def lister(
    bd: SessionBD,
    ctx: Contexte,
    *,
    categorie_id: str | None = None,
    etat: str | None = None,
    nature: str | None = None,
    du: date | None = None,
    au: date | None = None,
    page: int = 1,
    taille: int = 50,
) -> dict:
    ctx.exiger(Permission.FAIT_LIRE)
    requete = select(Fait).where(filtre_faits(ctx))
    if categorie_id:
        requete = requete.where(Fait.categorie_id == categorie_id)
    if etat:
        requete = requete.where(Fait.etat_verification == etat)
    if nature:
        requete = requete.where(Fait.nature_information == nature)
    if du:
        requete = requete.where(Fait.date_declaree >= du)
    if au:
        requete = requete.where(Fait.date_declaree <= au)
    requete = requete.order_by(Fait.cree_le.desc())
    elements, total = paginer(bd, requete, page, taille)
    return {"elements": [serialiser_resume(f) for f in elements], "total": total, "page": page, "taille": taille}


def _verifier_rattachements(bd: SessionBD, ctx: Contexte, plainte_id: str | None, dossier_id: str | None) -> None:
    if (
        plainte_id
        and bd.execute(select(Plainte.id).where(Plainte.id == plainte_id, filtre_plaintes(ctx))).first() is None
    ):
        raise DonneesInvalides("Plainte inconnue ou hors périmètre.")
    if (
        dossier_id
        and bd.execute(select(Dossier.id).where(Dossier.id == dossier_id, filtre_dossiers(ctx))).first() is None
    ):
        raise DonneesInvalides("Dossier inconnu ou hors périmètre.")


def _verifier_nature(ctx: Contexte, nature: NatureInformation | None, references: str | None) -> None:
    if nature == NatureInformation.DECISION_JUDICIAIRE and not (references or "").strip():
        raise DonneesInvalides(
            "Une décision judiciaire doit être documentée par la référence de l'acte de la juridiction."
        )


def creer(bd: SessionBD, ctx: Contexte, donnees: schemas.FaitCreation) -> dict:
    ctx.exiger(Permission.FAIT_CREER)
    unite_id = donnees.unite_id or ctx.utilisateur.unite_id
    if not ctx.unite_accessible(unite_id):
        raise AccesRefuse("Vous ne pouvez pas enregistrer un fait pour cette unité.")
    unite = bd.get(Unite, unite_id)
    if unite is None:
        raise DonneesInvalides("Unité inconnue.")
    categorie = bd.get(CategorieFait, donnees.categorie_id)
    if categorie is None or not categorie.active:
        raise DonneesInvalides("Catégorie inconnue ou désactivée.")
    _verifier_rattachements(bd, ctx, donnees.plainte_id, donnees.dossier_id)
    _verifier_nature(ctx, donnees.nature_information, donnees.references_actes)
    fait = Fait(
        reference=prochain_numero(bd, "FT", unite.code),
        categorie_id=categorie.id,
        date_declaree=donnees.date_declaree,
        lieu=donnees.lieu,
        province_code=donnees.province_code or unite.province_code,
        description=donnees.description,
        source_information=donnees.source_information,
        nature_information=donnees.nature_information,
        etat_verification=donnees.etat_verification,
        references_actes=donnees.references_actes,
        unite_id=unite.id,
        plainte_id=donnees.plainte_id,
        dossier_id=donnees.dossier_id,
        cree_par_id=ctx.uid,
    )
    bd.add(fait)
    bd.flush()
    for lien in donnees.personnes:
        _personne_accessible(bd, ctx, lien.personne_id)
        bd.add(LienFaitPersonne(fait_id=fait.id, personne_id=lien.personne_id, role=lien.role))
    historiser(
        bd,
        ctx,
        "fait",
        fait.id,
        "CREATION",
        {"reference": fait.reference, "nature_information": fait.nature_information},
    )
    audit.enregistrer_ctx(bd, ctx, "FAIT_CREATION", type_ressource="fait", ressource_id=fait.id, unite_id=unite.id)
    bd.flush()
    return serialiser_resume(fait)


def detail(bd: SessionBD, ctx: Contexte, fait_id: str) -> dict:
    ctx.exiger(Permission.FAIT_LIRE)
    f = obtenir(bd, ctx, fait_id)
    personnes = []
    if ctx.a(Permission.PERSONNE_LIRE):
        personnes = [
            {
                "lien_id": lien.id,
                "personne_id": lien.personne_id,
                "numero_interne": lien.personne.numero_interne,
                "nom": lien.personne.nom,
                "prenoms": lien.personne.prenoms,
                "role": lien.role,
            }
            for lien in bd.execute(select(LienFaitPersonne).where(LienFaitPersonne.fait_id == f.id)).scalars()
        ]
    resultat = {
        **serialiser_resume(f),
        "description": f.description,
        "references_actes": f.references_actes,
        "personnes": personnes,
        "historique": historique(bd, "fait", f.id),
        "cree_le": f.cree_le,
    }
    audit.enregistrer_ctx(bd, ctx, "FAIT_CONSULTATION", type_ressource="fait", ressource_id=f.id)
    return resultat


def modifier(bd: SessionBD, ctx: Contexte, fait_id: str, donnees: schemas.FaitModification) -> dict:
    ctx.exiger(Permission.FAIT_MODIFIER)
    f = obtenir(bd, ctx, fait_id)
    if f.version != donnees.version:
        raise Conflit("Le fait a été modifié entre temps. Rechargez-le.", code="VERSION_OBSOLETE")
    valeurs = donnees.model_dump(exclude_unset=True, exclude={"version"})
    if "categorie_id" in valeurs:
        c = bd.get(CategorieFait, valeurs["categorie_id"])
        if c is None or not c.active:
            raise DonneesInvalides("Catégorie inconnue ou désactivée.")
    if "dossier_id" in valeurs:
        _verifier_rattachements(bd, ctx, None, valeurs["dossier_id"])
    _verifier_nature(ctx, valeurs.get("nature_information"), valeurs.get("references_actes", f.references_actes))
    changements = appliquer_modifications(f, valeurs)
    bd.flush()
    historiser(bd, ctx, "fait", f.id, "MODIFICATION", changements)
    audit.enregistrer_ctx(
        bd, ctx, "FAIT_MODIFICATION", type_ressource="fait", ressource_id=f.id, details={"champs": sorted(changements)}
    )
    return serialiser_resume(f)


def ajouter_personne(bd: SessionBD, ctx: Contexte, fait_id: str, lien: schemas.LienPersonne) -> dict:
    ctx.exiger(Permission.FAIT_MODIFIER)
    f = obtenir(bd, ctx, fait_id)
    personne = _personne_accessible(bd, ctx, lien.personne_id)
    if bd.execute(
        select(LienFaitPersonne.id).where(
            LienFaitPersonne.fait_id == f.id,
            LienFaitPersonne.personne_id == personne.id,
            LienFaitPersonne.role == lien.role,
        )
    ).first():
        raise Conflit("Cette personne est déjà associée au fait avec ce rôle.")
    nouveau = LienFaitPersonne(fait_id=f.id, personne_id=personne.id, role=lien.role)
    bd.add(nouveau)
    bd.flush()
    historiser(bd, ctx, "fait", f.id, "AJOUT_PERSONNE", {"personne": personne.numero_interne, "role": lien.role})
    audit.enregistrer_ctx(
        bd,
        ctx,
        "FAIT_LIEN_PERSONNE",
        type_ressource="fait",
        ressource_id=f.id,
        details={"personne_id": personne.id, "role": lien.role},
    )
    return {"lien_id": nouveau.id}
