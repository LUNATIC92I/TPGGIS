"""Dossiers et procedures, actes de procedure et rattachements."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.database.models import (
    ActeProcedure,
    Dossier,
    Fait,
    LienDossierPersonne,
    LienDossierPlainte,
    Plainte,
    Unite,
    Utilisateur,
)
from tpgis.server.services import audit
from tpgis.server.services.commun import appliquer_modifications, historique, historiser, paginer, prochain_numero
from tpgis.server.services.contexte import Contexte, filtre_dossiers, filtre_plaintes
from tpgis.server.services.erreurs import HORS_PERIMETRE, AccesRefuse, Conflit, DonneesInvalides, Introuvable
from tpgis.server.services.plaintes import _personne_accessible
from tpgis.shared import schemas
from tpgis.shared.enums import StatutDossier
from tpgis.shared.permissions import Permission

STATUTS_FINAUX = {StatutDossier.CLOTURE, StatutDossier.ARCHIVE}


def serialiser_resume(d: Dossier) -> dict:
    return {
        "id": d.id,
        "numero": d.numero,
        "intitule": d.intitule,
        "type_procedure": d.type_procedure,
        "unite_id": d.unite_id,
        "unite_nom": d.unite.nom if d.unite else None,
        "enqueteur_id": d.enqueteur_id,
        "enqueteur": f"{d.enqueteur.grade or ''} {d.enqueteur.nom} {d.enqueteur.prenoms}".strip()
        if d.enqueteur else None,
        "statut": d.statut,
        "date_ouverture": d.date_ouverture,
        "date_cloture": d.date_cloture,
        "juridiction": d.juridiction,
        "version": d.version,
    }


def obtenir(bd: SessionBD, ctx: Contexte, dossier_id: str) -> Dossier:
    d = bd.execute(select(Dossier).where(Dossier.id == dossier_id, filtre_dossiers(ctx))).unique().scalar_one_or_none()
    if d is None:
        audit.enregistrer_ctx(bd, ctx, "DOSSIER_CONSULTATION", resultat="REFUS", type_ressource="dossier",
                              ressource_id=dossier_id)
        bd.commit()
        raise Introuvable(HORS_PERIMETRE)
    return d


def lister(bd: SessionBD, ctx: Contexte, *, statut: str | None = None, unite_id: str | None = None,
           numero: str | None = None, page: int = 1, taille: int = 50) -> dict:
    ctx.exiger(Permission.DOSSIER_LIRE)
    requete = select(Dossier).where(filtre_dossiers(ctx))
    if statut:
        requete = requete.where(Dossier.statut == statut)
    if unite_id:
        requete = requete.where(Dossier.unite_id == unite_id)
    if numero:
        requete = requete.where(Dossier.numero.ilike(f"%{numero.strip()}%"))
    requete = requete.order_by(Dossier.date_ouverture.desc(), Dossier.numero.desc())
    elements, total = paginer(bd, requete, page, taille)
    return {"elements": [serialiser_resume(d) for d in elements], "total": total, "page": page, "taille": taille}


def _verifier_enqueteur(bd: SessionBD, enqueteur_id: str | None, unite_id: str) -> None:
    if enqueteur_id is None:
        return
    u = bd.get(Utilisateur, enqueteur_id)
    if u is None or not u.actif or u.unite_id != unite_id:
        raise DonneesInvalides("L'enquêteur doit être un compte actif de l'unité en charge du dossier.")
    if Permission.DOSSIER_LIRE not in u.role.codes_permissions:
        raise DonneesInvalides("Ce compte n'est pas habilité à traiter des dossiers.")


def creer(bd: SessionBD, ctx: Contexte, donnees: schemas.DossierCreation) -> dict:
    ctx.exiger(Permission.DOSSIER_CREER)
    unite_id = donnees.unite_id or ctx.utilisateur.unite_id
    if not ctx.unite_accessible(unite_id) or ctx.assignes_seulement:
        raise AccesRefuse("Vous ne pouvez pas ouvrir un dossier pour cette unité.")
    unite = bd.get(Unite, unite_id)
    if unite is None or not unite.active:
        raise DonneesInvalides("Unité inconnue ou inactive.")
    _verifier_enqueteur(bd, donnees.enqueteur_id, unite_id)
    ouverture = donnees.date_ouverture or date.today()
    d = Dossier(
        numero=prochain_numero(bd, "DO", unite.code, ouverture.year),
        intitule=donnees.intitule,
        type_procedure=donnees.type_procedure,
        unite_id=unite_id,
        enqueteur_id=donnees.enqueteur_id,
        statut=StatutDossier.OUVERT,
        date_ouverture=ouverture,
        juridiction=donnees.juridiction,
        observations=donnees.observations,
        cree_par_id=ctx.uid,
    )
    bd.add(d)
    bd.flush()
    for plainte_id in dict.fromkeys(donnees.plaintes_ids):
        if bd.execute(select(Plainte.id).where(Plainte.id == plainte_id, filtre_plaintes(ctx))).first() is None:
            raise DonneesInvalides("Une des plaintes à rattacher est inconnue ou hors périmètre.")
        bd.add(LienDossierPlainte(dossier_id=d.id, plainte_id=plainte_id))
    historiser(bd, ctx, "dossier", d.id, "CREATION", {"numero": d.numero, "plaintes": len(donnees.plaintes_ids)})
    audit.enregistrer_ctx(bd, ctx, "DOSSIER_CREATION", type_ressource="dossier", ressource_id=d.id, unite_id=unite_id)
    bd.flush()
    return serialiser_resume(d)


def detail(bd: SessionBD, ctx: Contexte, dossier_id: str) -> dict:
    ctx.exiger(Permission.DOSSIER_LIRE)
    d = obtenir(bd, ctx, dossier_id)
    plaintes = [
        {"id": p.id, "numero": p.numero, "statut": p.statut, "recue_le": p.recue_le}
        for p in bd.execute(
            select(Plainte).join(LienDossierPlainte, LienDossierPlainte.plainte_id == Plainte.id)
            .where(LienDossierPlainte.dossier_id == d.id)
        ).unique().scalars()
    ]
    personnes = []
    if ctx.a(Permission.PERSONNE_LIRE):
        personnes = [
            {"lien_id": lien.id, "personne_id": lien.personne_id, "numero_interne": lien.personne.numero_interne,
             "nom": lien.personne.nom, "prenoms": lien.personne.prenoms, "role": lien.role}
            for lien in bd.execute(select(LienDossierPersonne).where(LienDossierPersonne.dossier_id == d.id)).scalars()
        ]
    actes = [
        {"id": a.id, "type_acte": a.type_acte, "reference": a.reference, "date_acte": a.date_acte,
         "resume": a.resume}
        for a in bd.execute(select(ActeProcedure).where(ActeProcedure.dossier_id == d.id)
                            .order_by(ActeProcedure.date_acte)).scalars()
    ]
    faits = [
        {"id": f.id, "reference": f.reference, "categorie": f.categorie.libelle,
         "nature_information": f.nature_information, "etat_verification": f.etat_verification}
        for f in bd.execute(select(Fait).where(Fait.dossier_id == d.id)).unique().scalars()
    ] if ctx.a(Permission.FAIT_LIRE) else []
    resultat = {
        **serialiser_resume(d),
        "observations": d.observations,
        "motif_cloture": d.motif_cloture,
        "plaintes": plaintes,
        "personnes": personnes,
        "actes": actes,
        "faits": faits,
        "historique": historique(bd, "dossier", d.id),
    }
    audit.enregistrer_ctx(bd, ctx, "DOSSIER_CONSULTATION", type_ressource="dossier", ressource_id=d.id,
                          unite_id=d.unite_id)
    return resultat


def modifier(bd: SessionBD, ctx: Contexte, dossier_id: str, donnees: schemas.DossierModification) -> dict:
    ctx.exiger(Permission.DOSSIER_MODIFIER)
    d = obtenir(bd, ctx, dossier_id)
    if d.version != donnees.version:
        raise Conflit("Le dossier a été modifié entre temps. Rechargez-le.", code="VERSION_OBSOLETE")
    valeurs = donnees.model_dump(exclude_unset=True, exclude={"version"})
    if "enqueteur_id" in valeurs and ctx.assignes_seulement:
        raise AccesRefuse("Vous ne pouvez pas réattribuer ce dossier.")
    if d.statut in STATUTS_FINAUX and donnees.statut not in (StatutDossier.EN_COURS, StatutDossier.ARCHIVE):
        raise Conflit("Un dossier clôturé ne peut être que rouvert ou archivé.")
    cible = valeurs.get("statut")
    if cible in STATUTS_FINAUX or (d.statut in STATUTS_FINAUX and cible):
        ctx.exiger(Permission.DOSSIER_CLOTURER)
        if len((valeurs.get("motif_cloture") or "").strip()) < 10:
            raise DonneesInvalides("La clôture, l'archivage ou la réouverture exige un motif (10 caractères minimum).")
        if cible == StatutDossier.CLOTURE:
            valeurs["date_cloture"] = date.today()
        if cible == StatutDossier.EN_COURS:
            valeurs["date_cloture"] = None
    if "enqueteur_id" in valeurs:
        _verifier_enqueteur(bd, valeurs["enqueteur_id"], d.unite_id)
    changements = appliquer_modifications(d, valeurs)
    bd.flush()
    historiser(bd, ctx, "dossier", d.id, "MODIFICATION", changements)
    audit.enregistrer_ctx(bd, ctx, "DOSSIER_MODIFICATION", type_ressource="dossier", ressource_id=d.id,
                          unite_id=d.unite_id, details={"champs": sorted(changements)})
    return serialiser_resume(d)


def ajouter_acte(bd: SessionBD, ctx: Contexte, dossier_id: str, donnees: schemas.ActeCreation) -> dict:
    ctx.exiger(Permission.DOSSIER_MODIFIER)
    d = obtenir(bd, ctx, dossier_id)
    if d.statut in STATUTS_FINAUX:
        raise Conflit("Impossible d'ajouter un acte à un dossier clôturé.")
    if donnees.date_acte > date.today():
        raise DonneesInvalides("La date de l'acte ne peut pas être dans le futur.")
    acte = ActeProcedure(dossier_id=d.id, redige_par_id=ctx.uid, **donnees.model_dump())
    bd.add(acte)
    bd.flush()
    historiser(bd, ctx, "dossier", d.id, "AJOUT_ACTE", {"type": donnees.type_acte, "reference": donnees.reference})
    audit.enregistrer_ctx(bd, ctx, "DOSSIER_ACTE", type_ressource="dossier", ressource_id=d.id,
                          details={"acte_id": acte.id})
    return {"id": acte.id}


def rattacher_plainte(bd: SessionBD, ctx: Contexte, dossier_id: str, plainte_id: str) -> dict:
    ctx.exiger(Permission.DOSSIER_MODIFIER)
    d = obtenir(bd, ctx, dossier_id)
    if bd.execute(select(Plainte.id).where(Plainte.id == plainte_id, filtre_plaintes(ctx))).first() is None:
        raise DonneesInvalides("Plainte inconnue ou hors périmètre.")
    if bd.execute(select(LienDossierPlainte.id).where(LienDossierPlainte.dossier_id == d.id,
                                                      LienDossierPlainte.plainte_id == plainte_id)).first():
        raise Conflit("Cette plainte est déjà rattachée au dossier.")
    bd.add(LienDossierPlainte(dossier_id=d.id, plainte_id=plainte_id))
    historiser(bd, ctx, "dossier", d.id, "RATTACHEMENT_PLAINTE", {"plainte_id": plainte_id})
    audit.enregistrer_ctx(bd, ctx, "DOSSIER_RATTACHEMENT", type_ressource="dossier", ressource_id=d.id,
                          details={"plainte_id": plainte_id})
    return {"message": "Plainte rattachée."}


def ajouter_personne(bd: SessionBD, ctx: Contexte, dossier_id: str, lien: schemas.LienPersonne) -> dict:
    ctx.exiger(Permission.DOSSIER_MODIFIER)
    d = obtenir(bd, ctx, dossier_id)
    personne = _personne_accessible(bd, ctx, lien.personne_id)
    if bd.execute(select(LienDossierPersonne.id).where(LienDossierPersonne.dossier_id == d.id,
                                                       LienDossierPersonne.personne_id == personne.id,
                                                       LienDossierPersonne.role == lien.role)).first():
        raise Conflit("Cette personne est déjà associée au dossier avec ce rôle.")
    nouveau = LienDossierPersonne(dossier_id=d.id, personne_id=personne.id, role=lien.role)
    bd.add(nouveau)
    bd.flush()
    historiser(bd, ctx, "dossier", d.id, "AJOUT_PERSONNE", {"personne": personne.numero_interne, "role": lien.role})
    audit.enregistrer_ctx(bd, ctx, "DOSSIER_LIEN_PERSONNE", type_ressource="dossier", ressource_id=d.id,
                          details={"personne_id": personne.id, "role": lien.role})
    return {"lien_id": nouveau.id}

