"""Services transverses : historique, numerotation, parametres, pagination."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.database.base import maintenant
from tpgis.server.database.models import Compteur, HistoriqueModification, Parametre
from tpgis.server.services.erreurs import DonneesInvalides

# Champs dont la valeur n'est jamais recopiee dans l'historique (seul le fait
# qu'ils ont change est trace).
CHAMPS_MASQUES_HISTORIQUE = {
    "description",
    "observations",
    "coordonnees",
    "numero_document",
    "resume",
    "temoins_non_identifies",
    "mot_de_passe_hash",
    "mfa_secret",
    "reference_modele",
}


def _serialiser(valeur: Any) -> Any:
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, (list, dict, int, float, bool)) or valeur is None:
        return valeur
    return str(valeur)


def appliquer_modifications(objet: Any, donnees: dict[str, Any]) -> dict[str, Any]:
    """Applique les champs fournis et retourne le differentiel pour l'historique."""
    changements: dict[str, Any] = {}
    for champ, nouvelle in donnees.items():
        ancienne = getattr(objet, champ)
        if ancienne == nouvelle:
            continue
        setattr(objet, champ, nouvelle)
        if champ in CHAMPS_MASQUES_HISTORIQUE:
            changements[champ] = {"modifie": True}
        else:
            changements[champ] = {"avant": _serialiser(ancienne), "apres": _serialiser(nouvelle)}
    return changements


def historiser(bd: SessionBD, ctx, type_entite: str, entite_id: str, action: str, changements: dict | None) -> None:
    bd.add(
        HistoriqueModification(
            type_entite=type_entite,
            entite_id=entite_id,
            action=action,
            modifie_par_id=ctx.uid,
            modifie_par_identifiant=ctx.utilisateur.identifiant,
            modifie_le=maintenant(),
            changements=changements or None,
        )
    )


def historique(bd: SessionBD, type_entite: str, entite_id: str) -> list[dict]:
    lignes = (
        bd.execute(
            select(HistoriqueModification)
            .where(HistoriqueModification.type_entite == type_entite, HistoriqueModification.entite_id == entite_id)
            .order_by(HistoriqueModification.id)
        )
        .scalars()
        .all()
    )
    return [
        {
            "action": h.action,
            "modifie_par": h.modifie_par_identifiant,
            "modifie_le": h.modifie_le,
            "changements": h.changements,
        }
        for h in lignes
    ]


def prochain_numero(bd: SessionBD, prefixe: str, code_unite: str | None, annee: int | None = None) -> str:
    """Numerotation unique et sequentielle, verrouillee dans la transaction."""
    annee = annee or maintenant().year
    cle = f"{prefixe}:{code_unite or 'NAT'}:{annee}"
    if bd.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as insert_pg

        bd.execute(insert_pg(Compteur).values(cle=cle, valeur=0).on_conflict_do_nothing(index_elements=["cle"]))
        compteur = bd.execute(select(Compteur).where(Compteur.cle == cle).with_for_update()).scalar_one()
    else:
        compteur = bd.get(Compteur, cle)
        if compteur is None:
            compteur = Compteur(cle=cle, valeur=0)
            bd.add(compteur)
    compteur.valeur += 1
    bd.flush()
    milieu = f"{code_unite}-" if code_unite else ""
    return f"{prefixe}-{milieu}{annee}-{compteur.valeur:06d}"


PARAMETRES_DEFAUT: dict[str, dict] = {
    "documents.extensions_autorisees": {
        "valeur": ["pdf", "png", "jpg", "jpeg", "tif", "tiff", "docx", "odt", "txt"],
        "description": "Extensions de fichiers acceptées pour les pièces.",
    },
    "documents.taille_max_octets": {
        "valeur": 20 * 1024 * 1024,
        "description": "Taille maximale d'une pièce (octets).",
    },
    "institution.entete": {
        "valeur": [
            "RÉPUBLIQUE DU TCHAD",
            "Unité, Travail, Progrès",
            "MINISTÈRE DE LA SÉCURITÉ PUBLIQUE",
        ],
        "description": "Lignes d'en tête des documents générés (modèle institutionnel).",
    },
    "institution.pied_page": {
        "valeur": "Document administratif à diffusion restreinte. Toute reproduction non autorisée est interdite.",
        "description": "Mention de bas de page des documents générés.",
    },
    "retention.plaintes_archivees_annees": {
        "valeur": 10,
        "description": "Durée de conservation des plaintes archivées (à fixer par l'institution).",
    },
    "retention.biometrie_annees": {
        "valeur": 5,
        "description": "Durée de conservation par défaut d'une capture biométrique.",
    },
    "retention.audit_annees": {
        "valeur": 10,
        "description": "Durée de conservation du journal d'audit.",
    },
    "retention.sessions_jours": {
        "valeur": 90,
        "description": "Durée de conservation des sessions expirées.",
    },
    "recherche.finalites": {
        "valeur": [
            "Vérification d'identité dans le cadre d'une plainte",
            "Enquête judiciaire en cours",
            "Réquisition de l'autorité judiciaire",
            "Contrôle administratif autorisé",
        ],
        "description": "Finalités proposées lors des consultations sensibles.",
    },
    "statistiques.seuil_confidentialite": {
        "valeur": 0,
        "description": "Les effectifs strictement inférieurs à ce seuil sont masqués sur la carte (0 : désactivé).",
    },
}


def lire_parametre(bd: SessionBD, cle: str) -> Any:
    ligne = bd.get(Parametre, cle)
    if ligne is not None:
        return ligne.valeur
    if cle in PARAMETRES_DEFAUT:
        return PARAMETRES_DEFAUT[cle]["valeur"]
    raise DonneesInvalides("Paramètre inconnu : {cle}", parametres={"cle": cle})


def ecrire_parametre(bd: SessionBD, cle: str, valeur: Any, identifiant: str) -> Parametre:
    if cle not in PARAMETRES_DEFAUT:
        raise DonneesInvalides("Paramètre inconnu : {cle}", parametres={"cle": cle})
    attendu = type(PARAMETRES_DEFAUT[cle]["valeur"])
    if not isinstance(valeur, attendu) or (attendu is int and isinstance(valeur, bool)):
        raise DonneesInvalides(
            "Le paramètre {cle} attend une valeur de type {type}.", parametres={"cle": cle, "type": attendu.__name__}
        )
    ligne = bd.get(Parametre, cle)
    if ligne is None:
        ligne = Parametre(cle=cle, description=PARAMETRES_DEFAUT[cle]["description"])
        bd.add(ligne)
    ligne.valeur = valeur
    ligne.modifie_par = identifiant
    ligne.modifie_le = maintenant()
    bd.flush()
    return ligne


def paginer(bd: SessionBD, requete, page: int, taille: int) -> tuple[list, int]:
    if page < 1:
        raise DonneesInvalides("Le numéro de page doit être supérieur ou égal à 1.")
    if not 1 <= taille <= 200:
        raise DonneesInvalides("La taille de page doit être comprise entre 1 et 200.")
    total = bd.execute(select(func.count()).select_from(requete.order_by(None).subquery())).scalar_one()
    elements = bd.execute(requete.limit(taille).offset((page - 1) * taille)).unique().scalars().all()
    return list(elements), total
