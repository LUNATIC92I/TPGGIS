"""Journal d'audit chaine et protege.

Chaque evenement contient l'empreinte SHA 256 de l'evenement precedent : toute
modification ou suppression d'une entree est detectable par verification de
la chaine. Les details sont nettoyes : jamais de mot de passe, de secret,
de jeton ni de donnee biometrique.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.database.base import maintenant
from tpgis.server.database.models import EvenementAudit
from tpgis.shared.enums import ResultatAudit

EMPREINTE_INITIALE = "0" * 64

_FRAGMENTS_INTERDITS = re.compile(r"(mot_de_passe|password|secret|jeton|token|totp|template)", re.IGNORECASE)
_MOTS_INTERDITS = {"cle", "key", "hash", "modele", "echantillon", "code", "mfa", "biometrique"}


def _cle_interdite(cle: str) -> bool:
    if _FRAGMENTS_INTERDITS.search(cle):
        return True
    return any(mot in _MOTS_INTERDITS for mot in cle.lower().split("_"))


_TAILLE_MAX_VALEUR = 500


def nettoyer_details(details: dict | None) -> dict | None:
    if not details:
        return None

    def _nettoyer(valeur, profondeur=0):
        if profondeur > 4:
            return "[tronqué]"
        if isinstance(valeur, dict):
            return {
                str(k): ("[masqué]" if _cle_interdite(str(k)) else _nettoyer(v, profondeur + 1))
                for k, v in valeur.items()
            }
        if isinstance(valeur, (list, tuple, set)):
            return [_nettoyer(v, profondeur + 1) for v in list(valeur)[:50]]
        if isinstance(valeur, (int, float, bool)) or valeur is None:
            return valeur
        texte_valeur = str(valeur)
        return texte_valeur[:_TAILLE_MAX_VALEUR]

    return _nettoyer(details)


def _calculer_empreinte(precedente: str, ev: EvenementAudit) -> str:
    contenu = {
        "horodatage": ev.horodatage.isoformat(),
        "utilisateur_id": ev.utilisateur_id,
        "identifiant": ev.identifiant,
        "action": ev.action,
        "type_ressource": ev.type_ressource,
        "ressource_id": ev.ressource_id,
        "unite_id": ev.unite_id,
        "resultat": ev.resultat,
        "finalite": ev.finalite,
        "trace_id": ev.trace_id,
        "adresse_ip": ev.adresse_ip,
        "details": ev.details,
    }
    canonique = json.dumps(contenu, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256((precedente + canonique).encode("utf-8")).hexdigest()


def enregistrer(
    bd: SessionBD,
    *,
    action: str,
    resultat: ResultatAudit | str = ResultatAudit.SUCCES,
    trace_id: str,
    utilisateur_id: str | None = None,
    identifiant: str | None = None,
    type_ressource: str | None = None,
    ressource_id: str | None = None,
    unite_id: str | None = None,
    finalite: str | None = None,
    adresse_ip: str | None = None,
    details: dict | None = None,
) -> EvenementAudit:
    """Ajoute un evenement dans la transaction courante."""
    if bd.get_bind().dialect.name == "postgresql":
        # Serialise l'ecriture du journal pour garantir une chaine lineaire.
        bd.execute(text("SELECT pg_advisory_xact_lock(7300235)"))
    derniere = bd.execute(select(EvenementAudit.empreinte).order_by(EvenementAudit.id.desc()).limit(1)).scalar()
    precedente = derniere or EMPREINTE_INITIALE
    ev = EvenementAudit(
        horodatage=maintenant(),
        utilisateur_id=utilisateur_id,
        identifiant=identifiant,
        action=action,
        type_ressource=type_ressource,
        ressource_id=str(ressource_id) if ressource_id is not None else None,
        unite_id=unite_id,
        resultat=str(resultat),
        finalite=(finalite or None) and finalite[:255],
        trace_id=trace_id,
        adresse_ip=adresse_ip,
        details=nettoyer_details(details),
        empreinte_precedente=precedente,
        empreinte="",
    )
    ev.empreinte = _calculer_empreinte(precedente, ev)
    bd.add(ev)
    bd.flush()
    return ev


def enregistrer_ctx(bd: SessionBD, ctx, action: str, **kwargs) -> EvenementAudit:
    kwargs.setdefault("finalite", ctx.finalite)
    kwargs.setdefault("unite_id", ctx.utilisateur.unite_id)
    return enregistrer(
        bd,
        action=action,
        trace_id=ctx.trace_id,
        utilisateur_id=ctx.uid,
        identifiant=ctx.utilisateur.identifiant,
        adresse_ip=ctx.adresse_ip,
        **kwargs,
    )


def derniere_empreinte(bd: SessionBD) -> str:
    derniere = bd.execute(select(EvenementAudit.empreinte).order_by(EvenementAudit.id.desc()).limit(1)).scalar()
    return derniere or EMPREINTE_INITIALE


def verifier_chaine(bd: SessionBD, taille_lot: int = 5000) -> dict:
    """Recalcule toute la chaine et signale la premiere rupture eventuelle."""
    precedente = EMPREINTE_INITIALE
    nombre = 0
    dernier_id = 0
    while True:
        lot = (
            bd.execute(
                select(EvenementAudit)
                .where(EvenementAudit.id > dernier_id)
                .order_by(EvenementAudit.id)
                .limit(taille_lot)
            )
            .scalars()
            .all()
        )
        if not lot:
            break
        for ev in lot:
            attendue = _calculer_empreinte(precedente, ev)
            if ev.empreinte_precedente != precedente or ev.empreinte != attendue:
                return {"integre": False, "evenements_verifies": nombre, "rupture_a_id": ev.id}
            precedente = ev.empreinte
            nombre += 1
            dernier_id = ev.id
        bd.expunge_all()
    return {"integre": True, "evenements_verifies": nombre, "rupture_a_id": None}


def horodatage_iso(d: datetime) -> str:
    return d.isoformat()
