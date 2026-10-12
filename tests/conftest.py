"""Fixtures communes. Toutes les donnees utilisees sont synthetiques.

Par defaut les tests utilisent SQLite. Definir TPGIS_TEST_DATABASE_URL pour
les executer sur PostgreSQL (base dediee, videe a chaque test).
"""

from __future__ import annotations

import os
import warnings

import pyotp
import pytest
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore", category=DeprecationWarning)

from fastapi.testclient import TestClient  # noqa: E402

from tpgis.server.config import ParametresServeur  # noqa: E402
from tpgis.server.database.models import Utilisateur  # noqa: E402
from tpgis.server.database.seed.demonstration import MOT_DE_PASSE_DEMO, SECRETS_TOTP_DEMO, Volumes, generer  # noqa
from tpgis.server.main import creer_application  # noqa: E402
from tpgis.server.security.crypto import generer_cle  # noqa: E402

URL_PG = os.environ.get("TPGIS_TEST_DATABASE_URL")


def _vider_postgresql(url: str) -> None:
    moteur = create_engine(url)
    with moteur.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    moteur.dispose()


@pytest.fixture
def parametres(tmp_path) -> ParametresServeur:
    if URL_PG:
        _vider_postgresql(URL_PG)
    return ParametresServeur(
        environnement="test",
        database_url=URL_PG or f"sqlite:///{tmp_path / 'test.sqlite3'}",
        cles_donnees=f"k1:{generer_cle()}",
        cle_donnees_active="k1",
        cle_index=generer_cle(),
        cle_sauvegarde=generer_cle(),
        repertoire_stockage=tmp_path / "stockage",
        repertoire_sauvegardes=tmp_path / "sauvegardes",
        limite_requetes_par_minute=100000,
        limite_connexion_par_minute_ip=100000,
    )


@pytest.fixture
def app(parametres):
    application = creer_application(parametres)
    yield application
    application.state.fabrique.moteur.dispose()


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def donnees(app, parametres):
    with app.state.fabrique.transaction() as bd:
        return generer(bd, parametres, Volumes(personnes=40, plaintes=60, faits=20, dossiers=15, captures=6))


class Connexions:
    """Ouvre des sessions reelles via l'API pour les comptes de demonstration."""

    def __init__(self, app, client):
        self.app, self.client = app, client

    def code(self, identifiant: str) -> str | None:
        secret = SECRETS_TOTP_DEMO.get(identifiant)
        if not secret:
            return None
        # Les codes deja utilises sont refuses (anti rejeu) : on libere le pas
        # memorise pour permettre plusieurs connexions rapprochees en test.
        with self.app.state.fabrique.transaction() as bd:
            u = bd.query(Utilisateur).filter_by(identifiant=identifiant).one()
            u.mfa_dernier_pas = None
        return pyotp.TOTP(secret).now()

    def entetes(self, identifiant: str, finalite: str | None = None) -> dict:
        r = self.client.post(
            "/api/v1/auth/connexion",
            json={"identifiant": identifiant, "mot_de_passe": MOT_DE_PASSE_DEMO, "code_mfa": self.code(identifiant)},
        )
        assert r.status_code == 200, r.text
        entetes = {"Authorization": f"Bearer {r.json()['jeton']}"}
        if finalite:
            entetes["X-TPGIS-Finalite"] = finalite
        return entetes

    def reauthentifier(self, identifiant: str, entetes: dict) -> None:
        r = self.client.post(
            "/api/v1/auth/reauthentification",
            headers=entetes,
            json={"mot_de_passe": MOT_DE_PASSE_DEMO, "code_mfa": self.code(identifiant)},
        )
        assert r.status_code == 200, r.text


@pytest.fixture
def connexions(app, client, donnees) -> Connexions:
    return Connexions(app, client)


FINALITE = "Enquete%20judiciaire%20en%20cours"


@pytest.fixture(autouse=True)
def _liberer_fenetres_qt():
    """Detruit les fenetres Qt de chaque test dans le fil principal.

    Sans cela, le ramasse miettes de Python peut liberer une fenetre (cycles crees
    par les connexions de signaux) plus tard, depuis un fil d'execution du serveur
    de test : Qt exige que ses objets graphiques soient detruits dans le fil principal.
    """
    yield
    import sys

    if "PySide6.QtWidgets" not in sys.modules:
        return
    import gc

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for fenetre in app.topLevelWidgets():
        fenetre.close()
        fenetre.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
