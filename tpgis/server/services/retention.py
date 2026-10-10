"""Politique de conservation et purge des donnees.

Les durees sont des parametres a fixer par l'institution. La purge est
toujours precedee d'un rapport (simulation) et son execution est soumise a
double validation. Le journal d'audit n'est jamais purge par l'application :
son archivage suit une procedure documentee (docs/administration.md).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.config import obtenir_parametres
from tpgis.server.database.base import maintenant
from tpgis.server.database.models import (
    CaptureBiometrique,
    Document,
    LienPlaintePersonne,
    Plainte,
    Session,
)
from tpgis.server.services import audit
from tpgis.server.services.commun import lire_parametre
from tpgis.server.services.contexte import Contexte
from tpgis.shared.enums import StatutCapture, StatutPlainte, TypeValidation
from tpgis.shared.permissions import Permission

MENTION_PURGE = "[Contenu purgé conformément à la politique de conservation]"


def _limites(bd: SessionBD) -> dict:
    instant = maintenant()
    return {
        "sessions": instant - timedelta(days=int(lire_parametre(bd, "retention.sessions_jours"))),
        "plaintes": instant - timedelta(days=365 * int(lire_parametre(bd, "retention.plaintes_archivees_annees"))),
        "biometrie": date.today(),
    }


def rapport(bd: SessionBD, ctx: Contexte) -> dict:
    ctx.exiger(Permission.VALIDATION_APPROUVER)
    lim = _limites(bd)
    return {
        "sessions_expirees": bd.execute(select(func.count(Session.id)).where(Session.expire_le < lim["sessions"]))
        .scalar_one(),
        "captures_biometriques_echues": bd.execute(select(func.count(CaptureBiometrique.id)).where(
            CaptureBiometrique.statut == StatutCapture.ACTIVE,
            CaptureBiometrique.conserver_jusqua < lim["biometrie"])).scalar_one(),
        "plaintes_archivees_echues": bd.execute(select(func.count(Plainte.id)).where(
            Plainte.statut == StatutPlainte.ARCHIVEE, Plainte.modifie_le < lim["plaintes"],
            Plainte.description != None)).scalar_one(),  # noqa: E711
        "limites": {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in lim.items()},
    }


def demander_purge(bd: SessionBD, ctx: Contexte, motif: str) -> dict:
    from tpgis.server.services.validations import creer_demande

    simulation = rapport(bd, ctx)
    return creer_demande(bd, ctx, TypeValidation.PURGE_DONNEES, {"simulation": simulation},
                         "Purge des données échues", motif)


def executer_purge(bd: SessionBD, ctx: Contexte, motif: str) -> str:
    from tpgis.server.services.biometrie import executer_suppression

    lim = _limites(bd)
    nb_sessions = bd.execute(delete(Session).where(Session.expire_le < lim["sessions"])).rowcount or 0
    nb_captures = 0
    for c in bd.execute(select(CaptureBiometrique).where(
            CaptureBiometrique.statut == StatutCapture.ACTIVE,
            CaptureBiometrique.conserver_jusqua < lim["biometrie"])).scalars().all():
        executer_suppression(bd, ctx, c.id, f"Durée de conservation échue. {motif}")
        nb_captures += 1
    nb_plaintes = 0
    p = obtenir_parametres()
    for plainte in bd.execute(select(Plainte).where(
            Plainte.statut == StatutPlainte.ARCHIVEE, Plainte.modifie_le < lim["plaintes"])).scalars().all():
        if plainte.description == MENTION_PURGE:
            continue
        plainte.description = MENTION_PURGE
        plainte.observations = None
        plainte.temoins_non_identifies = None
        bd.execute(delete(LienPlaintePersonne).where(LienPlaintePersonne.plainte_id == plainte.id))
        for doc in bd.execute(select(Document).where(Document.plainte_id == plainte.id)).scalars():
            for v in doc.versions:
                if v.chemin_stockage:
                    (p.repertoire_stockage / v.chemin_stockage).unlink(missing_ok=True)
                    v.chemin_stockage = ""
                    v.statut_analyse = "ERREUR"
                    v.resultat_analyse = "Contenu purgé"
        nb_plaintes += 1
    resultat = {"sessions": nb_sessions, "captures": nb_captures, "plaintes": nb_plaintes}
    audit.enregistrer_ctx(bd, ctx, "PURGE_DONNEES", type_ressource="systeme", details={**resultat, "motif": motif})
    return f"Purge effectuée : {nb_sessions} sessions, {nb_captures} captures, {nb_plaintes} plaintes."
