"""Gestion des plaintes : enregistrement, suivi, statuts et liens."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as SessionBD
from sqlalchemy.orm.exc import StaleDataError

from tpgis.server.database.base import maintenant
from tpgis.server.database.models import (
    CategorieFait,
    Dossier,
    Fait,
    LienDossierPlainte,
    LienPlaintePersonne,
    Personne,
    Plainte,
    Unite,
    Utilisateur,
)
from tpgis.server.services import audit
from tpgis.server.services.commun import appliquer_modifications, historique, historiser, paginer, prochain_numero
from tpgis.server.services.contexte import Contexte, filtre_dossiers, filtre_personnes, filtre_plaintes
from tpgis.server.services.erreurs import HORS_PERIMETRE, AccesRefuse, Conflit, DonneesInvalides, Introuvable
from tpgis.shared import schemas
from tpgis.shared.enums import TRANSITIONS_PLAINTE, StatutPersonne, StatutPlainte
from tpgis.shared.permissions import Permission


def serialiser_resume(p: Plainte) -> dict:
    return {
        "id": p.id,
        "numero": p.numero,
        "recue_le": p.recue_le,
        "unite_id": p.unite_id,
        "unite_nom": p.unite.nom if p.unite else None,
        "categorie_id": p.categorie_id,
        "categorie": p.categorie.libelle if p.categorie else None,
        "statut": p.statut,
        "date_faits": p.date_faits,
        "lieu_faits": p.lieu_faits,
        "province_code": p.province_code,
        "agent_responsable_id": p.agent_responsable_id,
        "agent_responsable": (
            f"{p.agent_responsable.grade or ''} {p.agent_responsable.nom} {p.agent_responsable.prenoms}".strip()
            if p.agent_responsable
            else None
        ),
        "version": p.version,
    }


def obtenir(bd: SessionBD, ctx: Contexte, plainte_id: str, action: str = "PLAINTE_CONSULTATION") -> Plainte:
    p = bd.execute(select(Plainte).where(Plainte.id == plainte_id, filtre_plaintes(ctx))).unique().scalar_one_or_none()
    if p is None:
        audit.enregistrer_ctx(bd, ctx, action, resultat="REFUS", type_ressource="plainte", ressource_id=plainte_id)
        bd.commit()
        raise Introuvable(HORS_PERIMETRE)
    return p


def lister(
    bd: SessionBD,
    ctx: Contexte,
    *,
    statut: str | None = None,
    unite_id: str | None = None,
    categorie_id: str | None = None,
    du: date | None = None,
    au: date | None = None,
    numero: str | None = None,
    page: int = 1,
    taille: int = 50,
) -> dict:
    ctx.exiger(Permission.PLAINTE_LIRE)
    requete = select(Plainte).where(filtre_plaintes(ctx))
    if statut:
        requete = requete.where(Plainte.statut == statut)
    if unite_id:
        requete = requete.where(Plainte.unite_id == unite_id)
    if categorie_id:
        requete = requete.where(Plainte.categorie_id == categorie_id)
    if du:
        requete = requete.where(Plainte.recue_le >= datetime.combine(du, datetime.min.time()))
    if au:
        requete = requete.where(Plainte.recue_le <= datetime.combine(au, datetime.max.time()))
    if numero:
        requete = requete.where(Plainte.numero.ilike(f"%{numero.strip()}%"))
    requete = requete.order_by(Plainte.recue_le.desc(), Plainte.numero.desc())
    elements, total = paginer(bd, requete, page, taille)
    return {"elements": [serialiser_resume(p) for p in elements], "total": total, "page": page, "taille": taille}


def _verifier_agent(bd: SessionBD, agent_id: str | None, unite_id: str) -> None:
    if agent_id is None:
        return
    agent = bd.get(Utilisateur, agent_id)
    if agent is None or not agent.actif or agent.unite_id != unite_id:
        raise DonneesInvalides("L'agent responsable doit être un compte actif de l'unité concernée.")


def _verifier_categorie(bd: SessionBD, categorie_id: str | None) -> None:
    if categorie_id is None:
        return
    c = bd.get(CategorieFait, categorie_id)
    if c is None or not c.active:
        raise DonneesInvalides("Catégorie de faits inconnue ou désactivée.")


def _personne_accessible(bd: SessionBD, ctx: Contexte, personne_id: str) -> Personne:
    p = (
        bd.execute(select(Personne).where(Personne.id == personne_id, filtre_personnes(ctx, recherche_nationale=True)))
        .unique()
        .scalar_one_or_none()
    )
    if p is None:
        raise DonneesInvalides("Personne inconnue ou hors périmètre.")
    if p.statut != StatutPersonne.ACTIVE:
        raise DonneesInvalides(
            "La fiche {numero} a été fusionnée : utiliser la fiche conservée.", parametres={"numero": p.numero_interne}
        )
    return p


def creer(bd: SessionBD, ctx: Contexte, donnees: schemas.PlainteCreation) -> dict:
    ctx.exiger(Permission.PLAINTE_CREER)
    unite_id = donnees.unite_id or ctx.utilisateur.unite_id
    if not ctx.unite_accessible(unite_id) or (ctx.assignes_seulement and unite_id != ctx.utilisateur.unite_id):
        raise AccesRefuse("Vous ne pouvez pas enregistrer une plainte pour cette unité.")
    unite = bd.get(Unite, unite_id)
    if unite is None or not unite.active:
        raise DonneesInvalides("Unité inconnue ou inactive.")
    _verifier_agent(bd, donnees.agent_responsable_id, unite_id)
    _verifier_categorie(bd, donnees.categorie_id)
    recue_le = donnees.recue_le or maintenant()
    if recue_le > maintenant():
        raise DonneesInvalides("La date de réception ne peut pas être dans le futur.")
    plainte = Plainte(
        numero=prochain_numero(bd, "PL", unite.code, recue_le.year),
        recue_le=recue_le,
        service_enregistrement=donnees.service_enregistrement,
        unite_id=unite_id,
        agent_responsable_id=donnees.agent_responsable_id or ctx.uid,
        categorie_id=donnees.categorie_id,
        description=donnees.description,
        date_faits=donnees.date_faits,
        lieu_faits=donnees.lieu_faits,
        province_code=donnees.province_code or unite.province_code,
        references_procedure=donnees.references_procedure,
        observations=donnees.observations,
        temoins_non_identifies=donnees.temoins_non_identifies,
        statut=StatutPlainte.NOUVELLE,
        cree_par_id=ctx.uid,
    )
    bd.add(plainte)
    bd.flush()
    for lien in donnees.personnes:
        _personne_accessible(bd, ctx, lien.personne_id)
        bd.add(
            LienPlaintePersonne(
                plainte_id=plainte.id, personne_id=lien.personne_id, role=lien.role, observations=lien.observations
            )
        )
    historiser(bd, ctx, "plainte", plainte.id, "CREATION", {"numero": plainte.numero, "statut": plainte.statut})
    audit.enregistrer_ctx(
        bd,
        ctx,
        "PLAINTE_CREATION",
        type_ressource="plainte",
        ressource_id=plainte.id,
        unite_id=unite_id,
        details={"numero": plainte.numero},
    )
    bd.flush()
    return serialiser_resume(plainte)


def detail(bd: SessionBD, ctx: Contexte, plainte_id: str) -> dict:
    ctx.exiger(Permission.PLAINTE_LIRE)
    p = obtenir(bd, ctx, plainte_id)
    personnes = []
    if ctx.a(Permission.PERSONNE_LIRE):
        for lien in bd.execute(select(LienPlaintePersonne).where(LienPlaintePersonne.plainte_id == p.id)).scalars():
            personnes.append(
                {
                    "lien_id": lien.id,
                    "personne_id": lien.personne_id,
                    "numero_interne": lien.personne.numero_interne,
                    "nom": lien.personne.nom,
                    "prenoms": lien.personne.prenoms,
                    "role": lien.role,
                    "observations": lien.observations,
                }
            )
    dossiers = [
        {"id": d.id, "numero": d.numero, "intitule": d.intitule, "statut": d.statut}
        for d in bd.execute(
            select(Dossier)
            .join(LienDossierPlainte, LienDossierPlainte.dossier_id == Dossier.id)
            .where(LienDossierPlainte.plainte_id == p.id, filtre_dossiers(ctx))
        )
        .unique()
        .scalars()
    ]
    faits = (
        [
            {
                "id": f.id,
                "reference": f.reference,
                "categorie": f.categorie.libelle,
                "nature_information": f.nature_information,
                "etat_verification": f.etat_verification,
            }
            for f in bd.execute(select(Fait).where(Fait.plainte_id == p.id)).unique().scalars()
        ]
        if ctx.a(Permission.FAIT_LIRE)
        else []
    )
    resultat = {
        **serialiser_resume(p),
        "service_enregistrement": p.service_enregistrement,
        "description": p.description,
        "references_procedure": p.references_procedure,
        "observations": p.observations,
        "temoins_non_identifies": p.temoins_non_identifies,
        "motif_statut": p.motif_statut,
        "service_destinataire": p.service_destinataire,
        "cree_le": p.cree_le,
        "modifie_le": p.modifie_le,
        "personnes": personnes,
        "dossiers": dossiers,
        "faits": faits,
        "historique": historique(bd, "plainte", p.id),
        "transitions_possibles": sorted(TRANSITIONS_PLAINTE[StatutPlainte(p.statut)]),
    }
    audit.enregistrer_ctx(
        bd, ctx, "PLAINTE_CONSULTATION", type_ressource="plainte", ressource_id=p.id, unite_id=p.unite_id
    )
    return resultat


def _controle_version(p: Plainte, version: int) -> None:
    if p.version != version:
        raise Conflit(
            "La plainte a été modifiée entre temps par un autre utilisateur. Rechargez-la.", code="VERSION_OBSOLETE"
        )


def modifier(bd: SessionBD, ctx: Contexte, plainte_id: str, donnees: schemas.PlainteModification) -> dict:
    ctx.exiger(Permission.PLAINTE_MODIFIER)
    p = obtenir(bd, ctx, plainte_id, "PLAINTE_MODIFICATION")
    _controle_version(p, donnees.version)
    if p.statut in (StatutPlainte.CLOTUREE, StatutPlainte.ARCHIVEE):
        raise Conflit("Une plainte clôturée ou archivée ne peut plus être modifiée.")
    valeurs = donnees.model_dump(exclude_unset=True, exclude={"version"})
    if "agent_responsable_id" in valeurs:
        _verifier_agent(bd, valeurs["agent_responsable_id"], p.unite_id)
    if "categorie_id" in valeurs:
        _verifier_categorie(bd, valeurs["categorie_id"])
    changements = appliquer_modifications(p, valeurs)
    if not changements:
        return serialiser_resume(p)
    try:
        bd.flush()
    except StaleDataError as exc:
        raise Conflit("Modification concurrente détectée. Rechargez la plainte.", code="VERSION_OBSOLETE") from exc
    historiser(bd, ctx, "plainte", p.id, "MODIFICATION", changements)
    audit.enregistrer_ctx(
        bd,
        ctx,
        "PLAINTE_MODIFICATION",
        type_ressource="plainte",
        ressource_id=p.id,
        unite_id=p.unite_id,
        details={"champs": sorted(changements)},
    )
    return serialiser_resume(p)


def changer_statut(bd: SessionBD, ctx: Contexte, plainte_id: str, donnees: schemas.ChangementStatutPlainte) -> dict:
    p = obtenir(bd, ctx, plainte_id, "PLAINTE_STATUT")
    _controle_version(p, donnees.version)
    actuel, cible = StatutPlainte(p.statut), donnees.statut
    if cible not in TRANSITIONS_PLAINTE[actuel]:
        raise DonneesInvalides(
            "Transition interdite : {actuel} vers {cible}.", parametres={"actuel": actuel.value, "cible": cible.value}
        )
    motif = (donnees.motif or "").strip()
    if cible == StatutPlainte.CLOTUREE:
        ctx.exiger(Permission.PLAINTE_CLOTURER)
        if len(motif) < 10:
            raise DonneesInvalides("La clôture exige un motif détaillé (10 caractères minimum).")
    elif cible == StatutPlainte.ARCHIVEE:
        ctx.exiger(Permission.PLAINTE_ARCHIVER)
        if len(motif) < 10:
            raise DonneesInvalides("L'archivage exige un motif (10 caractères minimum).")
    elif actuel == StatutPlainte.CLOTUREE:
        ctx.exiger(Permission.PLAINTE_CLOTURER)
        if len(motif) < 10:
            raise DonneesInvalides("La réouverture exige un motif (10 caractères minimum).")
    else:
        ctx.exiger(Permission.PLAINTE_MODIFIER)
    if cible == StatutPlainte.TRANSMISE:
        if not donnees.service_destinataire:
            raise DonneesInvalides("Indiquer le service destinataire de la transmission.")
        p.service_destinataire = donnees.service_destinataire
    p.statut = cible
    p.motif_statut = motif or None
    bd.flush()
    historiser(
        bd,
        ctx,
        "plainte",
        p.id,
        "CHANGEMENT_STATUT",
        {
            "avant": actuel.value,
            "apres": cible.value,
            "motif": motif or None,
            "service_destinataire": donnees.service_destinataire,
        },
    )
    audit.enregistrer_ctx(
        bd,
        ctx,
        "PLAINTE_STATUT",
        type_ressource="plainte",
        ressource_id=p.id,
        unite_id=p.unite_id,
        details={"avant": actuel.value, "apres": cible.value},
    )
    return serialiser_resume(p)


def ajouter_personne(bd: SessionBD, ctx: Contexte, plainte_id: str, lien: schemas.LienPersonne) -> dict:
    ctx.exiger(Permission.PLAINTE_MODIFIER if not ctx.a(Permission.PLAINTE_CREER) else Permission.PLAINTE_CREER)
    p = obtenir(bd, ctx, plainte_id, "PLAINTE_MODIFICATION")
    if p.statut in (StatutPlainte.CLOTUREE, StatutPlainte.ARCHIVEE):
        raise Conflit("Une plainte clôturée ou archivée ne peut plus être modifiée.")
    personne = _personne_accessible(bd, ctx, lien.personne_id)
    existe = bd.execute(
        select(LienPlaintePersonne.id).where(
            LienPlaintePersonne.plainte_id == p.id,
            LienPlaintePersonne.personne_id == personne.id,
            LienPlaintePersonne.role == lien.role,
        )
    ).first()
    if existe:
        raise Conflit("Cette personne est déjà associée à la plainte avec ce rôle.")
    nouveau = LienPlaintePersonne(
        plainte_id=p.id, personne_id=personne.id, role=lien.role, observations=lien.observations
    )
    bd.add(nouveau)
    bd.flush()
    historiser(bd, ctx, "plainte", p.id, "AJOUT_PERSONNE", {"personne": personne.numero_interne, "role": lien.role})
    audit.enregistrer_ctx(
        bd,
        ctx,
        "PLAINTE_LIEN_PERSONNE",
        type_ressource="plainte",
        ressource_id=p.id,
        details={"personne_id": personne.id, "role": lien.role},
    )
    return {"lien_id": nouveau.id}


def retirer_personne(bd: SessionBD, ctx: Contexte, plainte_id: str, lien_id: int, motif: str) -> dict:
    ctx.exiger(Permission.PLAINTE_MODIFIER)
    p = obtenir(bd, ctx, plainte_id, "PLAINTE_MODIFICATION")
    lien = bd.get(LienPlaintePersonne, lien_id)
    if lien is None or lien.plainte_id != p.id:
        raise Introuvable("Lien introuvable.")
    historiser(
        bd,
        ctx,
        "plainte",
        p.id,
        "RETRAIT_PERSONNE",
        {"personne": lien.personne.numero_interne, "role": lien.role, "motif": motif},
    )
    bd.delete(lien)
    audit.enregistrer_ctx(bd, ctx, "PLAINTE_LIEN_PERSONNE_RETRAIT", type_ressource="plainte", ressource_id=p.id)
    return {"message": "Lien retiré."}
