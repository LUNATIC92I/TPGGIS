"""Statistiques agregees et donnees cartographiques.

Toutes les valeurs sont calculees a partir des donnees reellement enregistrees
dans le perimetre de l'utilisateur. Aucune donnee nominative n'est restituee.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.database.models import CategorieFait, Dossier, Fait, Personne, Plainte, Unite
from tpgis.server.services import audit
from tpgis.server.services.commun import lire_parametre
from tpgis.server.services.contexte import Contexte, filtre_dossiers, filtre_faits, filtre_personnes, filtre_plaintes
from tpgis.server.services.erreurs import DonneesInvalides
from tpgis.shared.enums import EtatVerification, StatutDossier, StatutPlainte
from tpgis.shared.permissions import Permission

STATUTS_EN_ATTENTE = (StatutPlainte.NOUVELLE, StatutPlainte.EN_VERIFICATION)
STATUTS_DOSSIER_ACTIFS = (StatutDossier.OUVERT, StatutDossier.EN_COURS, StatutDossier.TRANSMIS_PARQUET)


def _mois(bd: SessionBD, colonne):
    if bd.get_bind().dialect.name == "postgresql":
        return func.to_char(colonne, "YYYY-MM")
    return func.strftime("%Y-%m", colonne)


def _filtres_plaintes(
    ctx: Contexte, du: date | None, au: date | None, unite_id: str | None, categorie_id: str | None
) -> list:
    conditions = [filtre_plaintes(ctx)]
    if du:
        conditions.append(Plainte.recue_le >= datetime.combine(du, datetime.min.time()))
    if au:
        conditions.append(Plainte.recue_le <= datetime.combine(au, datetime.max.time()))
    if unite_id:
        conditions.append(Plainte.unite_id == unite_id)
    if categorie_id:
        conditions.append(Plainte.categorie_id == categorie_id)
    return conditions


def _pourcentage(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def tableau_de_bord(
    bd: SessionBD,
    ctx: Contexte,
    du: date | None = None,
    au: date | None = None,
    unite_id: str | None = None,
    categorie_id: str | None = None,
) -> dict:
    ctx.exiger(Permission.STATISTIQUES_LIRE)
    if du and au and du > au:
        raise DonneesInvalides("La date de début doit précéder la date de fin.")
    cond = _filtres_plaintes(ctx, du, au, unite_id, categorie_id)

    total = bd.execute(select(func.count(Plainte.id)).where(*cond)).scalar_one()
    par_statut = dict(bd.execute(select(Plainte.statut, func.count()).where(*cond).group_by(Plainte.statut)).all())
    en_attente = sum(par_statut.get(s, 0) for s in STATUTS_EN_ATTENTE)
    limite_retard = datetime.now() - timedelta(days=30)
    en_retard = bd.execute(
        select(func.count(Plainte.id)).where(
            *cond, Plainte.statut.in_(STATUTS_EN_ATTENTE), Plainte.recue_le < limite_retard
        )
    ).scalar_one()

    par_categorie = [
        {"categorie": libelle or "Non catégorisé", "nombre": n}
        for libelle, n in bd.execute(
            select(CategorieFait.libelle, func.count(Plainte.id))
            .select_from(Plainte)
            .outerjoin(CategorieFait, CategorieFait.id == Plainte.categorie_id)
            .where(*cond)
            .group_by(CategorieFait.libelle)
            .order_by(func.count(Plainte.id).desc())
        ).all()
    ]
    par_province = [
        {"province_code": code, "nombre": n}
        for code, n in bd.execute(
            select(Plainte.province_code, func.count()).where(*cond).group_by(Plainte.province_code)
        ).all()
    ]
    mois = _mois(bd, Plainte.recue_le)
    debut_serie = du or (date.today().replace(day=1) - timedelta(days=335)).replace(day=1)
    evolution = [
        {"mois": m, "nombre": n}
        for m, n in bd.execute(
            select(mois.label("mois"), func.count())
            .where(*_filtres_plaintes(ctx, debut_serie, au, unite_id, categorie_id))
            .group_by("mois")
            .order_by("mois")
        ).all()
    ]
    activite_unites = [
        {"unite": nom, "corps": corps, "plaintes": n, "en_attente": int(att or 0)}
        for nom, corps, n, att in bd.execute(
            select(
                Unite.nom,
                Unite.corps,
                func.count(Plainte.id),
                func.sum(case((Plainte.statut.in_(STATUTS_EN_ATTENTE), 1), else_=0)),
            )
            .join(Unite, Unite.id == Plainte.unite_id)
            .where(*cond)
            .group_by(Unite.nom, Unite.corps)
            .order_by(func.count(Plainte.id).desc())
            .limit(30)
        ).all()
    ]
    dossiers_en_cours = bd.execute(
        select(func.count(Dossier.id)).where(
            filtre_dossiers(ctx),
            Dossier.statut.in_(STATUTS_DOSSIER_ACTIFS),
            *([Dossier.unite_id == unite_id] if unite_id else []),
        )
    ).scalar_one()

    completude = bd.execute(
        select(
            func.count(Plainte.id),
            func.sum(case((Plainte.categorie_id.is_not(None), 1), else_=0)),
            func.sum(case((Plainte.date_faits.is_not(None), 1), else_=0)),
            func.sum(case((Plainte.province_code.is_not(None), 1), else_=0)),
            func.sum(case((Plainte.lieu_faits.is_not(None), 1), else_=0)),
        ).where(*cond)
    ).one()
    nb, avec_cat, avec_date, avec_prov, avec_lieu = (int(x or 0) for x in completude)
    personnes = bd.execute(
        select(
            func.count(Personne.id),
            func.sum(case((Personne.date_naissance.is_not(None), 1), else_=0)),
            func.sum(case((Personne.index_document.is_not(None), 1), else_=0)),
        ).where(filtre_personnes(ctx))
    ).one()
    nb_p, p_naiss, p_doc = (int(x or 0) for x in personnes)
    faits = bd.execute(
        select(
            func.count(Fait.id),
            func.sum(case((Fait.etat_verification == EtatVerification.VERIFIE, 1), else_=0)),
        ).where(filtre_faits(ctx))
    ).one()
    nb_f, f_verif = (int(x or 0) for x in faits)

    audit.enregistrer_ctx(
        bd,
        ctx,
        "STATISTIQUES_CONSULTATION",
        type_ressource="statistiques",
        details={"du": du, "au": au, "unite_id": unite_id, "categorie_id": categorie_id},
    )
    return {
        "periode": {"du": du, "au": au},
        "indicateurs": {
            "plaintes_total": total,
            "plaintes_en_attente": en_attente,
            "plaintes_en_attente_plus_30_jours": en_retard,
            "dossiers_en_cours": dossiers_en_cours,
            "plaintes_cloturees": par_statut.get(StatutPlainte.CLOTUREE, 0),
        },
        "par_statut": par_statut,
        "par_categorie": par_categorie,
        "par_province": par_province,
        "evolution_mensuelle": evolution,
        "activite_unites": activite_unites,
        "qualite_donnees": {
            "plaintes_avec_categorie_pct": _pourcentage(avec_cat, nb),
            "plaintes_avec_date_faits_pct": _pourcentage(avec_date, nb),
            "plaintes_avec_province_pct": _pourcentage(avec_prov, nb),
            "plaintes_avec_lieu_pct": _pourcentage(avec_lieu, nb),
            "personnes_avec_date_naissance_pct": _pourcentage(p_naiss, nb_p),
            "personnes_avec_document_pct": _pourcentage(p_doc, nb_p),
            "faits_verifies_pct": _pourcentage(f_verif, nb_f),
        },
    }


def donnees_carte(
    bd: SessionBD,
    ctx: Contexte,
    du: date | None = None,
    au: date | None = None,
    unite_id: str | None = None,
    categorie_id: str | None = None,
) -> dict:
    """Agregats par province et implantation des unites. Aucune donnee nominative."""
    ctx.exiger(Permission.CARTE_LIRE)
    au_effectif = au or date.today()
    du_effectif = du or (au_effectif - timedelta(days=365))
    if du_effectif > au_effectif:
        raise DonneesInvalides("La date de début doit précéder la date de fin.")
    duree = (au_effectif - du_effectif).days + 1
    cond = _filtres_plaintes(ctx, du_effectif, au_effectif, unite_id, categorie_id)
    cond_prec = _filtres_plaintes(
        ctx, du_effectif - timedelta(days=duree), du_effectif - timedelta(days=1), unite_id, categorie_id
    )
    seuil = int(lire_parametre(bd, "statistiques.seuil_confidentialite"))

    courant = dict(
        bd.execute(select(Plainte.province_code, func.count()).where(*cond).group_by(Plainte.province_code)).all()
    )
    precedent = dict(
        bd.execute(select(Plainte.province_code, func.count()).where(*cond_prec).group_by(Plainte.province_code)).all()
    )
    dossiers = dict(
        bd.execute(
            select(Unite.province_code, func.count(Dossier.id))
            .join(Unite, Unite.id == Dossier.unite_id)
            .where(filtre_dossiers(ctx), Dossier.statut.in_(STATUTS_DOSSIER_ACTIFS))
            .group_by(Unite.province_code)
        ).all()
    )
    provinces = []
    for code in sorted({c for c in list(courant) + list(precedent) + list(dossiers) if c}):
        n, n_prec = courant.get(code, 0), precedent.get(code, 0)
        masque = 0 < n < seuil
        provinces.append(
            {
                "province_code": code,
                "plaintes": None if masque else n,
                "plaintes_masquees": masque,
                "plaintes_periode_precedente": n_prec if not masque else None,
                "tendance_pct": None if masque or not n_prec else round(100.0 * (n - n_prec) / n_prec, 1),
                "dossiers_en_cours": dossiers.get(code, 0),
            }
        )
    unites = []
    for u in bd.execute(select(Unite).where(Unite.active.is_(True), Unite.latitude.is_not(None))).scalars():
        visible = ctx.unite_accessible(u.id) or ctx.unites_accessibles is None
        unites.append(
            {
                "id": u.id,
                "code": u.code,
                "nom": u.nom,
                "type_unite": u.type_unite,
                "corps": u.corps,
                "province_code": u.province_code,
                "ville": u.ville,
                "latitude": u.latitude,
                "longitude": u.longitude,
                "dans_perimetre": visible,
            }
        )
    audit.enregistrer_ctx(
        bd,
        ctx,
        "CARTE_CONSULTATION",
        type_ressource="carte",
        details={"du": du_effectif, "au": au_effectif, "unite_id": unite_id, "categorie_id": categorie_id},
    )
    return {
        "periode": {"du": du_effectif, "au": au_effectif},
        "seuil_confidentialite": seuil,
        "provinces": provinces,
        "unites": unites,
    }
