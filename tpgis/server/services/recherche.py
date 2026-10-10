"""Recherche et verification autorisees.

Chaque recherche est rattachee a un utilisateur authentifie, un horodatage,
une finalite declaree et un identifiant de trace d'audit restitue au client.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.database.models import Dossier, Personne, Plainte
from tpgis.server.security.crypto import index_aveugle
from tpgis.server.services import audit
from tpgis.server.services.contexte import Contexte, filtre_dossiers, filtre_personnes, filtre_plaintes
from tpgis.server.services.erreurs import DonneesInvalides
from tpgis.server.services.personnes import rechercher_candidats, serialiser_resume
from tpgis.shared import schemas
from tpgis.shared.enums import StatutPersonne
from tpgis.shared.permissions import Permission


def _masquer(valeur: str | None) -> str | None:
    if not valeur:
        return None
    return "*" * max(0, len(valeur) - 3) + valeur[-3:]


def rechercher(bd: SessionBD, ctx: Contexte, demande: schemas.DemandeRecherche) -> dict:
    ctx.exiger(Permission.RECHERCHE_EFFECTUER)
    if demande.etendre_national:
        ctx.exiger(Permission.RECHERCHE_NATIONALE)
    ctx.finalite = demande.finalite
    criteres = demande.model_dump(exclude={"finalite", "etendre_national"}, exclude_none=True)
    if not criteres:
        raise DonneesInvalides("Indiquez au moins un critère de recherche.")
    resultats: dict[str, list] = {"plaintes": [], "dossiers": [], "personnes": []}

    if demande.numero_plainte:
        if ctx.a(Permission.PLAINTE_LIRE):
            for p in bd.execute(select(Plainte).where(Plainte.numero == demande.numero_plainte.strip().upper(),
                                                      filtre_plaintes(ctx))).unique().scalars():
                resultats["plaintes"].append({"id": p.id, "numero": p.numero, "statut": p.statut,
                                              "unite": p.unite.nom, "niveau": "EXACT"})
    if demande.numero_dossier:
        if ctx.a(Permission.DOSSIER_LIRE):
            for d in bd.execute(select(Dossier).where(Dossier.numero == demande.numero_dossier.strip().upper(),
                                                      filtre_dossiers(ctx))).unique().scalars():
                resultats["dossiers"].append({"id": d.id, "numero": d.numero, "intitule": d.intitule,
                                              "statut": d.statut, "niveau": "EXACT"})
    if ctx.a(Permission.PERSONNE_LIRE):
        if demande.numero_interne:
            for p in bd.execute(select(Personne).where(
                Personne.numero_interne == demande.numero_interne.strip().upper(),
                filtre_personnes(ctx, recherche_nationale=demande.etendre_national),
            )).unique().scalars():
                ligne = {**serialiser_resume(p), "score": 100, "niveau": "EXACT",
                         "attributs_concordants": ["numero_interne"], "ambiguites": []}
                if p.statut == StatutPersonne.FUSIONNEE:
                    ligne["ambiguites"].append("Fiche fusionnée dans une autre fiche.")
                resultats["personnes"].append(ligne)
        if demande.nom or demande.numero_document or demande.date_naissance:
            if demande.numero_document and not demande.nom:
                idx = index_aveugle().calculer(demande.numero_document)
                for p in bd.execute(select(Personne).where(
                    Personne.index_document == idx,
                    filtre_personnes(ctx, recherche_nationale=demande.etendre_national),
                )).unique().scalars():
                    resultats["personnes"].append({**serialiser_resume(p), "score": 60, "niveau": "MOYEN",
                                                   "attributs_concordants": ["numero_document"],
                                                   "ambiguites": ["Seul le numéro de document concorde : "
                                                                  "vérifier l'identité sur pièce."]})
            elif demande.nom:
                resultats["personnes"].extend(rechercher_candidats(
                    bd, ctx, demande.nom, demande.prenoms, demande.date_naissance, demande.lieu_naissance,
                    demande.numero_document, seuil=25, nationale=demande.etendre_national,
                ))
            else:
                raise DonneesInvalides("La date de naissance seule ne constitue pas un critère suffisant.")

    details = {k: v for k, v in criteres.items() if k != "numero_document"}
    if demande.numero_document:
        details["numero_document"] = _masquer(demande.numero_document)
    details["nombre_resultats"] = sum(len(v) for v in resultats.values())
    details["national"] = demande.etendre_national
    ev = audit.enregistrer_ctx(bd, ctx, "RECHERCHE", type_ressource="recherche", details=details)
    return {
        "resultats": resultats,
        "trace_audit": ev.trace_id,
        "horodatage": ev.horodatage,
        "avertissement": (
            "Les niveaux de correspondance sont indicatifs. Une concordance de nom ne suffit pas à établir "
            "l'identité : toute identification doit être confirmée par une vérification humaine sur pièces."
        ),
    }
