"""Routes d'analyse : tableau de bord, cartographie, exports et supervision."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session as SessionBD

from tpgis import __version__
from tpgis.server.api.deps import base, contexte, parametres, valider
from tpgis.server.api.routes_operations import reponse_fichier
from tpgis.server.config import ParametresServeur
from tpgis.server.services import audit, rapports, sauvegarde, statistiques
from tpgis.server.services.auth import exiger_reauthentification_recente
from tpgis.server.services.contexte import Contexte
from tpgis.server.services.documents import reanalyser_en_erreur
from tpgis.shared.permissions import Permission

routeur = APIRouter()


@routeur.get("/statistiques/tableau-de-bord", tags=["Statistiques"])
def tableau_de_bord(
    du: date | None = None,
    au: date | None = None,
    unite_id: str | None = None,
    categorie_id: str | None = None,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    return valider(bd, statistiques.tableau_de_bord(bd, ctx, du, au, unite_id, categorie_id))


@routeur.get("/carte/donnees", tags=["Cartographie"])
def donnees_carte(
    du: date | None = None,
    au: date | None = None,
    unite_id: str | None = None,
    categorie_id: str | None = None,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
):
    return valider(bd, statistiques.donnees_carte(bd, ctx, du, au, unite_id, categorie_id))


@routeur.get("/statistiques/export.csv", tags=["Statistiques"])
def export_csv(
    du: date | None = None,
    au: date | None = None,
    unite_id: str | None = None,
    categorie_id: str | None = None,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    nom, contenu = rapports.export_statistiques_csv(bd, ctx, p, du, au, unite_id, categorie_id)
    bd.commit()
    return reponse_fichier(nom, "text/csv; charset=utf-8", contenu)


@routeur.get("/statistiques/rapport.pdf", tags=["Statistiques"])
def rapport_pdf(
    du: date | None = None,
    au: date | None = None,
    unite_id: str | None = None,
    categorie_id: str | None = None,
    ctx: Contexte = Depends(contexte),
    bd: SessionBD = Depends(base),
    p: ParametresServeur = Depends(parametres),
):
    nom, contenu = rapports.rapport_statistique_pdf(bd, ctx, p, du, au, unite_id, categorie_id)
    bd.commit()
    return reponse_fichier(nom, "application/pdf", contenu)


@routeur.get("/sante", tags=["Supervision"])
def sante(request: Request):
    """Point de controle public : ne divulgue aucune information sensible."""
    try:
        with request.app.state.fabrique() as bd:
            bd.execute(text("SELECT 1"))
        etat_base = "disponible"
    except Exception:
        etat_base = "indisponible"
    return {
        "application": "TPGIS",
        "version": __version__,
        "base_de_donnees": etat_base,
        "statut": "ok" if etat_base == "disponible" else "degrade",
    }


@routeur.get("/systeme/etat", tags=["Supervision"])
def etat_systeme(
    ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base), p: ParametresServeur = Depends(parametres)
):
    ctx.exiger(Permission.SYSTEME_SUPERVISER)
    from tpgis.server.database.models import MetadonneeInstance

    meta = {m.cle: m.valeur for m in bd.query(MetadonneeInstance).all()}
    sauvegardes = (
        sorted(p.repertoire_sauvegardes.glob("tpgis_sauvegarde_*")) if p.repertoire_sauvegardes.exists() else []
    )
    return {
        "version": __version__,
        "environnement": str(p.environnement),
        "base": "postgresql" if not p.est_sqlite else "sqlite",
        "antivirus": p.antivirus,
        "biometrie": p.biometrie_adaptateur,
        "metadonnees_instance": meta,
        "derniere_sauvegarde": sauvegardes[-1].name if sauvegardes else None,
        "nombre_sauvegardes": len(sauvegardes),
    }


@routeur.post("/systeme/sauvegardes", tags=["Supervision"], status_code=201)
def lancer_sauvegarde(
    ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base), p: ParametresServeur = Depends(parametres)
):
    ctx.exiger(Permission.SAUVEGARDE_GERER)
    exiger_reauthentification_recente(ctx, p)
    from tpgis.server.database.initialisation import revision_courante

    dossier = sauvegarde.sauvegarder(p, revision_courante(bd))
    audit.enregistrer_ctx(bd, ctx, "SAUVEGARDE", type_ressource="systeme", details={"dossier": dossier.name})
    return valider(bd, {"sauvegarde": dossier.name})


@routeur.post("/systeme/documents/reanalyse", tags=["Supervision"])
def reanalyser(
    ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base), p: ParametresServeur = Depends(parametres)
):
    ctx.exiger(Permission.SYSTEME_SUPERVISER)
    resultat = reanalyser_en_erreur(bd, p)
    audit.enregistrer_ctx(bd, ctx, "DOCUMENTS_REANALYSE", type_ressource="systeme", details=resultat)
    return valider(bd, resultat)
