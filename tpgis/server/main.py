"""Point d'entree du serveur applicatif TPGIS (API FastAPI)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from tpgis import __version__
from tpgis.server.api import routes_admin, routes_analyse, routes_auth, routes_operations
from tpgis.server.config import (
    ErreurConfiguration,
    ParametresServeur,
    obtenir_parametres,
    verifier_configuration_production,
)
from tpgis.server.database.initialisation import (
    controler_absence_donnees_synthetiques,
    initialiser_metadonnees,
    initialiser_roles,
    migrer,
)
from tpgis.server.database.session import FabriqueSessions, creer_moteur
from tpgis.server.middleware.securite import LimiteurDebit, installer
from tpgis.server.security import crypto
from tpgis.server.services import audit
from tpgis.server.services.erreurs import AccesRefuse, ErreurMetier
from tpgis.shared.i18n import normaliser, traduire

journal = logging.getLogger("tpgis")
PREFIXE = "/api/v1"


def initialiser_chiffrement(p: ParametresServeur) -> None:
    if not (p.cles_donnees and p.cle_index and p.cle_sauvegarde):
        if p.est_production:
            raise ErreurConfiguration("Cles de chiffrement absentes en production.")
        # Developpement et demonstration : cles locales generees une fois.
        locales = crypto.charger_ou_creer_cles_locales(Path("var") / f"cles_{p.environnement}.json")
        p.cles_donnees = p.cles_donnees or locales["cles_donnees"]
        p.cle_index = p.cle_index or locales["cle_index"]
        p.cle_sauvegarde = p.cle_sauvegarde or locales["cle_sauvegarde"]
    trousseau = crypto.analyser_trousseau(p.cles_donnees)
    crypto.configurer(
        crypto.ChiffreurChamps(trousseau, p.cle_donnees_active),
        crypto.IndexAveugle(base64.b64decode(p.cle_index)),
    )


def _reponse_erreur(request: Request, statut: int, message: str | ErreurMetier, code: str, details: dict | None = None):
    """Reponse d'erreur ; le message (modele francais) est traduit selon l'en tete Accept-Language."""
    if not isinstance(message, ErreurMetier):
        message = traduire(message, normaliser(request.headers.get("accept-language")))
    else:
        message = message.message_traduit(normaliser(request.headers.get("accept-language")))
    contenu = {"detail": message, "code": code, "trace_id": getattr(request.state, "trace_id", None)}
    if details:
        contenu["details"] = details
    return JSONResponse(status_code=statut, content=jsonable_encoder(contenu))


def _tracer_refus(request: Request, exc: ErreurMetier) -> None:
    """Les refus d'acces sont journalises dans une transaction independante."""
    ctx = getattr(request.state, "contexte", None)
    try:
        with request.app.state.fabrique.transaction() as bd:
            audit.enregistrer(
                bd,
                action="ACCES_REFUSE",
                resultat="REFUS",
                trace_id=request.state.trace_id,
                utilisateur_id=ctx.uid if ctx else None,
                identifiant=ctx.utilisateur.identifiant if ctx else None,
                unite_id=ctx.utilisateur.unite_id if ctx else None,
                adresse_ip=request.client.host if request.client else None,
                finalite=ctx.finalite if ctx else None,
                details={
                    "methode": request.method,
                    "chemin": request.url.path,
                    "code": exc.code,
                    **(
                        {"permissions_manquantes": exc.details.get("permissions_manquantes")}
                        if exc.details.get("permissions_manquantes")
                        else {}
                    ),
                },
            )
    except Exception:  # pragma: no cover  (ne jamais masquer l'erreur initiale)
        journal.exception("Impossible de journaliser un refus d'accès")


def creer_application(p: ParametresServeur | None = None, *, migrer_au_demarrage: bool = True) -> FastAPI:
    p = p or obtenir_parametres()
    erreurs = verifier_configuration_production(p)
    if erreurs:
        raise ErreurConfiguration("Configuration non conforme pour la production :\n  " + "\n  ".join(erreurs))
    initialiser_chiffrement(p)
    if p.est_sqlite:
        Path(p.database_url.split("///", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)
    p.repertoire_stockage.mkdir(parents=True, exist_ok=True)

    moteur = creer_moteur(p)
    fabrique = FabriqueSessions(moteur)
    if migrer_au_demarrage:
        migrer(moteur)
    with fabrique.transaction() as bd:
        initialiser_metadonnees(bd, p)
        controler_absence_donnees_synthetiques(bd, p)
        initialiser_roles(bd)

    app = FastAPI(
        title="TPGIS : Tchad Police & Gendarmerie Information System",
        version=__version__,
        description="API sécurisée réservée aux services habilités. Toute utilisation est journalisée.",
        docs_url=None if p.est_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if p.est_production else "/api/openapi.json",
    )
    app.state.parametres = p
    app.state.fabrique = fabrique
    app.state.limiteur = LimiteurDebit()
    installer(app)

    @app.exception_handler(ErreurMetier)
    async def _erreur_metier(request: Request, exc: ErreurMetier):
        if isinstance(exc, AccesRefuse):
            _tracer_refus(request, exc)
        return _reponse_erreur(request, exc.statut_http, exc, exc.code, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _erreur_validation(request: Request, exc: RequestValidationError):
        champs = [
            {"champ": ".".join(str(x) for x in e.get("loc", [])[1:]), "message": e.get("msg")} for e in exc.errors()
        ]
        return _reponse_erreur(
            request, 422, "Données invalides : vérifiez les champs signalés.", "DONNEES_INVALIDES", {"champs": champs}
        )

    @app.exception_handler(Exception)
    async def _erreur_interne(request: Request, exc: Exception):
        journal.exception("Erreur interne (trace %s)", getattr(request.state, "trace_id", "?"))
        return _reponse_erreur(
            request,
            500,
            "Erreur interne du serveur. Communiquez l'identifiant de trace à l'administration.",
            "ERREUR_INTERNE",
        )

    for module in (routes_auth, routes_admin, routes_operations, routes_analyse):
        app.include_router(module.routeur, prefix=PREFIXE)
    return app


def lancer() -> None:
    """Demarrage avec uvicorn, TLS active si certificat et cle sont fournis."""
    import uvicorn

    p = obtenir_parametres()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = creer_application(p)
    options = {
        "host": p.hote,
        "port": p.port,
        "proxy_headers": p.tls_termine_par_proxy,
        "server_header": False,
        "date_header": False,
    }
    if p.tls_certificat and p.tls_cle:
        options.update(ssl_certfile=str(p.tls_certificat), ssl_keyfile=str(p.tls_cle))
    elif not p.tls_termine_par_proxy:
        journal.warning("Serveur démarré SANS TLS : usage limité au développement local.")
    uvicorn.run(app, **options)


if __name__ == "__main__":
    lancer()
