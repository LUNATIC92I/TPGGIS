"""Client de bureau : erreurs reseau, cloisonnement de l'interface et parcours
fonctionnels executes hors ecran contre le serveur reel (donnees synthetiques)."""

from __future__ import annotations

import os
import socket
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from tpgis.client.api_client.client import ClientAPI, ErreurAPI, ErreurReseau  # noqa: E402
from tpgis.client.api_client.travail import Executeur  # noqa: E402
from tpgis.client.main import appliquer_theme  # noqa: E402
from tpgis.client.windows.base import SessionClient  # noqa: E402
from tpgis.client.windows.principale import FenetrePrincipale  # noqa: E402
from tpgis.server.database.seed.demonstration import MOT_DE_PASSE_DEMO  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    appliquer_theme(app)
    Executeur.synchrone = True
    return app


@pytest.fixture
def messages(monkeypatch):
    """Les boites de dialogue modales sont interceptees (aucun blocage)."""
    journal = []
    for nom in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, nom, lambda *a, _n=nom, **k: journal.append((_n, a[1:3])))
    return journal


def _session(client, connexions, identifiant) -> SessionClient:
    api = ClientAPI("http://testserver", http=client)
    api.connecter(identifiant, MOT_DE_PASSE_DEMO, connexions.code(identifiant))
    return SessionClient(api=api, moi=api.get("/auth/moi"), executeur=Executeur())


# Erreurs reseau


def test_connexion_non_chiffree_refusee():
    with pytest.raises(ValueError, match="https"):
        ClientAPI("http://serveur.institution.td")
    ClientAPI("http://127.0.0.1:8000", autoriser_http_local=True)


def test_serveur_injoignable():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    api = ClientAPI(f"https://127.0.0.1:{port}", delai=2)
    with pytest.raises(ErreurReseau) as exc:
        api.verifier_disponibilite()
    assert exc.value.code == "SERVEUR_INJOIGNABLE"
    assert "injoignable" in str(exc.value)


def test_delai_depasse():
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)
    connexions = []
    threading.Thread(target=lambda: connexions.append(serveur.accept()), daemon=True).start()
    api = ClientAPI(f"https://127.0.0.1:{serveur.getsockname()[1]}", delai=0.5)
    with pytest.raises(ErreurReseau) as exc:
        api.verifier_disponibilite()
    assert exc.value.code == "DELAI_DEPASSE"
    serveur.close()


def test_certificat_non_reconnu_refuse(tmp_path):
    """Un serveur presentant un certificat d'une autorite inconnue est refuse."""
    import ssl
    import subprocess
    import sys
    import time
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, str(racine / "scripts" / "generer_certificats_demo.py"), str(tmp_path)], check=True)
    contexte = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    contexte.load_cert_chain(tmp_path / "serveur.crt", tmp_path / "serveur.key")
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)

    def _accepter():
        try:
            conn, _ = serveur.accept()
            with contexte.wrap_socket(conn, server_side=True):
                time.sleep(0.5)
        except (ssl.SSLError, OSError):
            pass

    threading.Thread(target=_accepter, daemon=True).start()
    api = ClientAPI(f"https://127.0.0.1:{serveur.getsockname()[1]}", delai=3)
    with pytest.raises(ErreurReseau) as exc:
        api.verifier_disponibilite()
    assert exc.value.code == "CERTIFICAT_INVALIDE"
    serveur.close()


def test_erreurs_api_traduites(client, donnees):
    api = ClientAPI("http://testserver", http=client)
    with pytest.raises(ErreurAPI) as exc:
        api.get("/plaintes")
    assert exc.value.statut == 401 and exc.value.trace_id
    with pytest.raises(ErreurAPI) as exc:
        api.connecter("accueil.ndj", "mauvais")
    assert "incorrect" in exc.value.message


# Interface


def test_navigation_filtree_selon_les_droits(qapp, client, connexions, messages):
    attendus = {
        "admin.technique": {"Tableau de bord", "Unités et commissariats", "Paramètres et administration"},
        "accueil.ndj": {
            "Tableau de bord",
            "Plaintes",
            "Personnes",
            "Unités et commissariats",
            "Pièces et documents",
            "Paramètres et administration",
        },
    }
    for identifiant, modules in attendus.items():
        fenetre = FenetrePrincipale(_session(client, connexions, identifiant))
        libelles = {fenetre.navigation.item(i).text() for i in range(fenetre.navigation.count())}
        assert libelles == modules, identifiant
        fenetre.close()


def test_toutes_les_pages_se_chargent(qapp, client, connexions, messages, tmp_path):
    for identifiant in ("responsable.ndj", "officier.ndj", "admin.fonctionnel", "auditeur", "admin.technique"):
        fenetre = FenetrePrincipale(_session(client, connexions, identifiant))
        fenetre.resize(1366, 768)
        fenetre.show()
        for i in range(fenetre.navigation.count()):
            fenetre.navigation.setCurrentRow(i)
            qapp.processEvents()
        fenetre.close()
    assert [m for m in messages if m[0] != "information"] == []


def test_tableau_de_bord_et_carte_alimentes(qapp, client, connexions, messages):
    fenetre = FenetrePrincipale(_session(client, connexions, "responsable.ndj"))
    fenetre.show()
    qapp.processEvents()
    page = fenetre.pages.widget(0)
    assert page.indicateurs["plaintes_total"].valeur.text().isdigit()
    assert len(page.carte.provinces) == 23
    assert {"TD-EE", "TD-EO"} <= set(page.carte.provinces)
    assert page.carte.marqueurs, "les unités doivent être placées sur la carte"
    nd = page.carte.provinces["TD-ND"]
    assert "Plaintes sur la période" in nd.toolTip()
    fenetre.close()


def test_parcours_enregistrement_plainte(qapp, client, connexions, messages):
    from tpgis.client.windows.plaintes import FormulairePlainte

    session = _session(client, connexions, "accueil.ndj")
    avant = session.api.get("/plaintes")["total"]
    formulaire = FormulairePlainte(session)
    formulaire.description.setPlainText("Plainte saisie depuis l'interface lors du test automatisé.")
    formulaire.lieu.setText("Quartier fictif")
    formulaire._soumettre()
    assert formulaire.erreur.text() == ""
    assert formulaire.resultat["numero"].startswith("PL-CP-NDJ-")
    assert session.api.get("/plaintes")["total"] == avant + 1


def test_formulaire_affiche_erreur_serveur(qapp, client, connexions, messages):
    from tpgis.client.windows.plaintes import FormulairePlainte

    formulaire = FormulairePlainte(_session(client, connexions, "accueil.ndj"))
    formulaire.description.setPlainText("court")
    formulaire._soumettre()
    assert "10 caractères" in formulaire.erreur.text()
    assert formulaire.resultat is None


def test_captures_ecran_documentation(qapp, client, connexions, messages, tmp_path):
    """Produit les captures d'ecran de la documentation (donnees synthetiques)."""
    from pathlib import Path

    # Captures ecrites dans un dossier temporaire (TPGIS_CAPTURES pour un autre dossier).
    cible = Path(os.environ.get("TPGIS_CAPTURES", tmp_path))
    cible.mkdir(parents=True, exist_ok=True)
    fenetre = FenetrePrincipale(_session(client, connexions, "responsable.ndj"))
    fenetre.resize(1440, 860)
    fenetre.show()
    for i, nom in ((0, "tableau_de_bord"), (1, "plaintes"), (8, "cartographie")):
        fenetre.navigation.setCurrentRow(i)
        qapp.processEvents()
        assert fenetre.grab().save(str(cible / f"{nom}.png"))
    fenetre.close()
