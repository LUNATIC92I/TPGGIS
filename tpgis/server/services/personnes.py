"""Registre des personnes concernees, detection des doublons et fusion validee."""

from __future__ import annotations

from datetime import date
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.database.models import (
    CaptureBiometrique,
    Document,
    Dossier,
    Fait,
    LienDossierPersonne,
    LienFaitPersonne,
    LienPlaintePersonne,
    Personne,
    Plainte,
)
from tpgis.server.security.crypto import index_aveugle, normaliser_texte
from tpgis.server.services import audit
from tpgis.server.services.commun import appliquer_modifications, historique, historiser, paginer, prochain_numero
from tpgis.server.services.contexte import (
    Contexte,
    filtre_dossiers,
    filtre_faits,
    filtre_personnes,
    filtre_plaintes,
)
from tpgis.server.services.erreurs import HORS_PERIMETRE, Conflit, DonneesInvalides, Introuvable
from tpgis.shared import schemas
from tpgis.shared.enums import StatutPersonne, TypeValidation
from tpgis.shared.permissions import Permission

SEUIL_CANDIDAT = 40


def nom_complet_normalise(nom: str, prenoms: str | None) -> str:
    return normaliser_texte(f"{nom} {prenoms or ''}")


def _similarite(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    ta, tb = " ".join(sorted(a.split())), " ".join(sorted(b.split()))
    return SequenceMatcher(None, ta, tb).ratio()


def niveau(score: int) -> str:
    if score >= 80:
        return "ELEVE"
    if score >= 55:
        return "MOYEN"
    return "FAIBLE"


def evaluer_correspondance(
    p: Personne,
    nom: str | None,
    prenoms: str | None,
    date_naissance: date | None,
    lieu_naissance: str | None,
    index_doc: str | None,
) -> tuple[int, list[str], list[str]]:
    """Score multi attributs. Retourne (score, attributs concordants, ambiguites).

    Un nom identique seul ne depasse jamais le niveau FAIBLE : l'homonymie
    n'etablit pas l'identite.
    """
    score, concordants, ambiguites = 0, [], []
    if index_doc and p.index_document:
        if index_doc == p.index_document:
            score += 60
            concordants.append("numero_document")
        else:
            ambiguites.append("Numéros de document différents")
    if nom:
        n_cible, n_p = normaliser_texte(nom), normaliser_texte(p.nom)
        if n_cible == n_p:
            score += 25
            concordants.append("nom")
        elif _similarite(n_cible, n_p) >= 0.85:
            score += 15
            concordants.append("nom_approchant")
    if prenoms and p.prenoms:
        pr_cible, pr_p = normaliser_texte(prenoms), normaliser_texte(p.prenoms)
        if set(pr_cible.split()) == set(pr_p.split()):
            score += 20
            concordants.append("prenoms")
        elif _similarite(pr_cible, pr_p) >= 0.8:
            score += 10
            concordants.append("prenoms_approchants")
    if date_naissance and p.date_naissance:
        if date_naissance == p.date_naissance:
            score += 25
            concordants.append("date_naissance")
        elif date_naissance.year == p.date_naissance.year:
            score += 5
            ambiguites.append("Même année de naissance mais date différente")
        else:
            ambiguites.append("Dates de naissance différentes")
            score -= 15
    if lieu_naissance and p.lieu_naissance:
        if normaliser_texte(lieu_naissance) == normaliser_texte(p.lieu_naissance):
            score += 10
            concordants.append("lieu_naissance")
    if concordants and set(concordants) <= {"nom", "prenoms", "nom_approchant", "prenoms_approchants"}:
        ambiguites.append("Correspondance fondée uniquement sur le nom : homonymie possible")
    return max(0, min(score, 100)), concordants, ambiguites


def serialiser_resume(p: Personne) -> dict:
    return {
        "id": p.id,
        "numero_interne": p.numero_interne,
        "nom": p.nom,
        "prenoms": p.prenoms,
        "date_naissance": p.date_naissance,
        "lieu_naissance": p.lieu_naissance,
        "nationalite": p.nationalite,
        "sexe": p.sexe,
        "statut_verification": p.statut_verification,
        "statut": p.statut,
        "unite_creation": p.unite_creation.nom if p.unite_creation else None,
        "version": p.version,
    }


def rechercher_candidats(
    bd: SessionBD,
    ctx: Contexte,
    nom: str,
    prenoms: str | None,
    date_naissance: date | None,
    lieu_naissance: str | None,
    numero_document: str | None,
    exclure_id: str | None = None,
    seuil: int = SEUIL_CANDIDAT,
    nationale: bool = True,
) -> list[dict]:
    idx = index_aveugle().calculer(numero_document)
    nom_norm = normaliser_texte(nom or "")
    conditions = []
    if nom_norm:
        conditions.append(Personne.nom_normalise.like(f"{nom_norm[:3]}%"))
    if date_naissance:
        conditions.append(Personne.date_naissance == date_naissance)
    if idx:
        conditions.append(Personne.index_document == idx)
    if not conditions:
        return []
    requete = (
        select(Personne)
        .where(
            or_(*conditions),
            Personne.statut == StatutPersonne.ACTIVE,
            filtre_personnes(ctx, recherche_nationale=nationale),
        )
        .limit(1000)
    )
    if exclure_id:
        requete = requete.where(Personne.id != exclure_id)
    resultats = []
    for p in bd.execute(requete).unique().scalars():
        score, concordants, ambiguites = evaluer_correspondance(p, nom, prenoms, date_naissance, lieu_naissance, idx)
        if score >= seuil:
            resultats.append(
                {
                    **serialiser_resume(p),
                    "score": score,
                    "niveau": niveau(score),
                    "attributs_concordants": concordants,
                    "ambiguites": ambiguites,
                }
            )
    resultats.sort(key=lambda r: r["score"], reverse=True)
    return resultats[:25]


def obtenir(bd: SessionBD, ctx: Contexte, personne_id: str) -> Personne:
    p = (
        bd.execute(select(Personne).where(Personne.id == personne_id, filtre_personnes(ctx)))
        .unique()
        .scalar_one_or_none()
    )
    if p is None:
        audit.enregistrer_ctx(
            bd, ctx, "PERSONNE_CONSULTATION", resultat="REFUS", type_ressource="personne", ressource_id=personne_id
        )
        bd.commit()
        raise Introuvable(HORS_PERIMETRE)
    return p


def lister(bd: SessionBD, ctx: Contexte, texte: str | None, page: int, taille: int) -> dict:
    ctx.exiger(Permission.PERSONNE_LIRE)
    requete = select(Personne).where(filtre_personnes(ctx), Personne.statut == StatutPersonne.ACTIVE)
    if texte:
        t = normaliser_texte(texte)
        requete = requete.where(or_(Personne.nom_normalise.like(f"%{t}%"), Personne.numero_interne == texte.strip()))
    requete = requete.order_by(Personne.nom_normalise)
    elements, total = paginer(bd, requete, page, taille)
    audit.enregistrer_ctx(
        bd, ctx, "PERSONNE_LISTE", type_ressource="personne", details={"filtre": bool(texte), "page": page}
    )
    return {"elements": [serialiser_resume(p) for p in elements], "total": total, "page": page, "taille": taille}


def _liens(bd: SessionBD, ctx: Contexte, personne_id: str) -> list[dict]:
    liens = []
    for lien, plainte in bd.execute(
        select(LienPlaintePersonne, Plainte)
        .join(Plainte, Plainte.id == LienPlaintePersonne.plainte_id)
        .where(LienPlaintePersonne.personne_id == personne_id, filtre_plaintes(ctx))
    ).unique():
        liens.append(
            {
                "type": "plainte",
                "id": plainte.id,
                "reference": plainte.numero,
                "role": lien.role,
                "statut": plainte.statut,
            }
        )
    for lien, dossier in bd.execute(
        select(LienDossierPersonne, Dossier)
        .join(Dossier, Dossier.id == LienDossierPersonne.dossier_id)
        .where(LienDossierPersonne.personne_id == personne_id, filtre_dossiers(ctx))
    ).unique():
        liens.append(
            {
                "type": "dossier",
                "id": dossier.id,
                "reference": dossier.numero,
                "role": lien.role,
                "statut": dossier.statut,
            }
        )
    for lien, fait in bd.execute(
        select(LienFaitPersonne, Fait)
        .join(Fait, Fait.id == LienFaitPersonne.fait_id)
        .where(LienFaitPersonne.personne_id == personne_id, filtre_faits(ctx))
    ).unique():
        liens.append(
            {
                "type": "fait",
                "id": fait.id,
                "reference": fait.reference,
                "role": lien.role,
                "statut": fait.etat_verification,
            }
        )
    return liens


def detail(bd: SessionBD, ctx: Contexte, personne_id: str) -> dict:
    """Consultation nominative : finalite obligatoire et trace d'audit."""
    ctx.exiger(Permission.PERSONNE_LIRE)
    if not ctx.finalite:
        raise DonneesInvalides("La finalité de la consultation doit être déclarée.", code="FINALITE_REQUISE")
    p = obtenir(bd, ctx, personne_id)
    nb_captures = None
    if ctx.a(Permission.BIOMETRIE_LIRE):
        nb_captures = len(
            bd.execute(
                select(CaptureBiometrique.id).where(
                    CaptureBiometrique.personne_id == p.id, CaptureBiometrique.statut == "ACTIVE"
                )
            ).all()
        )
    resultat = {
        **serialiser_resume(p),
        "alias": p.alias or [],
        "coordonnees": p.coordonnees or {},
        "type_document": p.type_document,
        "numero_document": p.numero_document,
        "photo_document_id": p.photo_document_id,
        "cree_le": p.cree_le,
        "modifie_le": p.modifie_le,
        "liens": _liens(bd, ctx, p.id),
        "captures_biometriques": nb_captures,
        "historique": historique(bd, "personne", p.id),
    }
    ev = audit.enregistrer_ctx(bd, ctx, "PERSONNE_CONSULTATION", type_ressource="personne", ressource_id=p.id)
    resultat["trace_audit"] = ev.trace_id
    return resultat


def creer(bd: SessionBD, ctx: Contexte, donnees: schemas.PersonneCreation) -> dict:
    ctx.exiger(Permission.PERSONNE_CREER)
    candidats = rechercher_candidats(
        bd,
        ctx,
        donnees.nom,
        donnees.prenoms,
        donnees.date_naissance,
        donnees.lieu_naissance,
        donnees.numero_document,
        seuil=55,
    )
    if candidats and not donnees.confirmer_malgre_doublons:
        raise Conflit(
            "Des fiches potentiellement identiques existent. Vérifiez-les avant de créer une nouvelle fiche.",
            code="DOUBLONS_POTENTIELS",
            details={"candidats": candidats},
        )
    valeurs = donnees.model_dump(exclude={"confirmer_malgre_doublons"})
    if valeurs.get("coordonnees") is not None:
        valeurs["coordonnees"] = {k: v for k, v in valeurs["coordonnees"].items() if v}
    p = Personne(
        **valeurs,
        numero_interne=prochain_numero(bd, "P", None),
        nom_normalise=nom_complet_normalise(donnees.nom, donnees.prenoms),
        index_document=index_aveugle().calculer(donnees.numero_document),
        unite_creation_id=ctx.utilisateur.unite_id,
        cree_par_id=ctx.uid,
        statut=StatutPersonne.ACTIVE,
    )
    bd.add(p)
    bd.flush()
    historiser(bd, ctx, "personne", p.id, "CREATION", {"doublons_signales": len(candidats)})
    audit.enregistrer_ctx(
        bd,
        ctx,
        "PERSONNE_CREATION",
        type_ressource="personne",
        ressource_id=p.id,
        details={"doublons_signales_ignores": len(candidats)},
    )
    return serialiser_resume(p)


def modifier(bd: SessionBD, ctx: Contexte, personne_id: str, donnees: schemas.PersonneModification) -> dict:
    ctx.exiger(Permission.PERSONNE_MODIFIER)
    p = obtenir(bd, ctx, personne_id)
    if p.version != donnees.version:
        raise Conflit(
            "La fiche a été modifiée entre temps par un autre utilisateur. Rechargez-la.", code="VERSION_OBSOLETE"
        )
    if p.statut != StatutPersonne.ACTIVE:
        raise Conflit("Cette fiche a été fusionnée et ne peut plus être modifiée.")
    valeurs = donnees.model_dump(exclude_unset=True, exclude={"version"})
    if "coordonnees" in valeurs and valeurs["coordonnees"] is not None:
        valeurs["coordonnees"] = {k: v for k, v in valeurs["coordonnees"].items() if v}
    if "numero_document" in valeurs:
        valeurs["index_document"] = index_aveugle().calculer(valeurs["numero_document"])
    changements = appliquer_modifications(p, valeurs)
    if {"nom", "prenoms"} & set(changements):
        p.nom_normalise = nom_complet_normalise(p.nom, p.prenoms)
    changements.pop("index_document", None)
    historiser(bd, ctx, "personne", p.id, "MODIFICATION", changements)
    audit.enregistrer_ctx(
        bd,
        ctx,
        "PERSONNE_MODIFICATION",
        type_ressource="personne",
        ressource_id=p.id,
        details={"champs": sorted(changements)},
    )
    bd.flush()
    return serialiser_resume(p)


def demander_fusion(bd: SessionBD, ctx: Contexte, donnees: schemas.DemandeFusion) -> dict:
    from tpgis.server.services.validations import creer_demande

    ctx.exiger(Permission.PERSONNE_FUSIONNER)
    if donnees.personne_conservee_id == donnees.personne_absorbee_id:
        raise DonneesInvalides("Les deux fiches doivent être différentes.")
    a = obtenir(bd, ctx, donnees.personne_conservee_id)
    b = obtenir(bd, ctx, donnees.personne_absorbee_id)
    if a.statut != StatutPersonne.ACTIVE or b.statut != StatutPersonne.ACTIVE:
        raise Conflit("Une des fiches a déjà été fusionnée.")
    return creer_demande(
        bd,
        ctx,
        TypeValidation.FUSION_PERSONNES,
        {"personne_conservee_id": a.id, "personne_absorbee_id": b.id},
        f"Fusion de {b.numero_interne} dans {a.numero_interne}",
        donnees.motif,
    )


def executer_fusion(bd: SessionBD, ctx: Contexte, conservee_id: str, absorbee_id: str, motif: str) -> str:
    a = obtenir(bd, ctx, conservee_id)
    b = obtenir(bd, ctx, absorbee_id)
    if a.statut != StatutPersonne.ACTIVE or b.statut != StatutPersonne.ACTIVE:
        raise Conflit("Une des fiches a déjà été fusionnée.")
    for modele, colonne_parent in (
        (LienPlaintePersonne, "plainte_id"),
        (LienDossierPersonne, "dossier_id"),
        (LienFaitPersonne, "fait_id"),
    ):
        existants = {
            (getattr(lien, colonne_parent), lien.role)
            for lien in bd.execute(select(modele).where(modele.personne_id == a.id)).scalars()
        }
        for lien in bd.execute(select(modele).where(modele.personne_id == b.id)).scalars():
            if (getattr(lien, colonne_parent), lien.role) in existants:
                bd.delete(lien)
            else:
                lien.personne_id = a.id
    for capture in bd.execute(select(CaptureBiometrique).where(CaptureBiometrique.personne_id == b.id)).scalars():
        capture.personne_id = a.id
    for doc in bd.execute(select(Document).where(Document.personne_id == b.id)).scalars():
        doc.personne_id = a.id
    alias = set(a.alias or [])
    if normaliser_texte(f"{b.nom} {b.prenoms or ''}") != normaliser_texte(f"{a.nom} {a.prenoms or ''}"):
        alias.add(f"{b.nom} {b.prenoms or ''}".strip())
    alias.update(b.alias or [])
    a.alias = sorted(alias)[:10]
    b.statut = StatutPersonne.FUSIONNEE
    b.fusionnee_dans_id = a.id
    bd.flush()
    historiser(bd, ctx, "personne", a.id, "FUSION", {"absorbee": b.numero_interne, "motif": motif})
    historiser(bd, ctx, "personne", b.id, "FUSIONNEE", {"dans": a.numero_interne, "motif": motif})
    audit.enregistrer_ctx(
        bd, ctx, "PERSONNE_FUSION", type_ressource="personne", ressource_id=a.id, details={"absorbee_id": b.id}
    )
    return f"Fiche {b.numero_interne} fusionnée dans {a.numero_interne}."
