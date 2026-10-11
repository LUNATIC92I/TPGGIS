"""Executable de demonstration autonome : serveur local TLS, donnees fictives, connexion assistee."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tpgis import demonstration_autonome as demo  # noqa: E402
from tpgis.client.api_client.client import ClientAPI  # noqa: E402


@pytest.fixture
def serveur_demo(tmp_path, monkeypatch):
    repertoire = os.getcwd()
    monkeypatch.setenv("TPGIS_DEMO_DOSSIER", str(tmp_path / "demo"))
    app, p = demo.preparer_serveur(demo.dossier_demonstration())
    serveur = demo.ServeurLocal(app, p)
    serveur.demarrer()
    yield p
    serveur.arreter()
    os.chdir(repertoire)


def test_serveur_local_tls_sur_boucle_locale_uniquement(serveur_demo):
    p = serveur_demo
    assert p.hote == "127.0.0.1" and str(p.environnement) == "demonstration"
    api = ClientAPI(f"https://127.0.0.1:{p.port}", certificat_ca=str(p.tls_certificat.parent / "ac_demo.crt"))
    assert api.verifier_disponibilite()["environnement"] == "demonstration"
    # Le dossier de demonstration contient sa propre base, ses cles et ses certificats.
    dossier = demo.dossier_demonstration()
    assert (dossier / "tpgis_demo.sqlite3").exists()
    assert (dossier / "var" / "cles_demonstration.json").exists()
    assert (dossier / "tls" / "ac_demo.crt").exists()


def test_connexion_assistee_avec_compte_fictif_et_mfa(serveur_demo):
    from tpgis.client.windows.connexion import DialogueConnexion

    QApplication.instance() or QApplication([])
    p = serveur_demo
    api = ClientAPI(f"https://127.0.0.1:{p.port}", certificat_ca=str(p.tls_certificat.parent / "ac_demo.crt"))
    dialogue = DialogueConnexion(api, "demonstration", comptes_demo=demo.comptes_demo())
    assert dialogue.choix_compte.count() == len(demo.COMPTES)
    dialogue.choix_compte.setCurrentIndex(0)  # responsable.ndj, compte avec MFA
    dialogue.remplir_compte_demo()
    assert dialogue.identifiant.text() == "responsable.ndj" and len(dialogue.code_mfa.text()) == 6
    dialogue.connecter()
    assert dialogue.message.text() == ""
    assert dialogue.resultat["type_session"] == "COMPLETE"
    assert api.get("/plaintes")["total"] > 0


def test_aide_absente_hors_demonstration(serveur_demo):
    from tpgis.client.windows.connexion import DialogueConnexion

    QApplication.instance() or QApplication([])
    api = ClientAPI("https://127.0.0.1:1")
    for environnement in ("production", "test", ""):
        dialogue = DialogueConnexion(api, environnement, comptes_demo=demo.comptes_demo())
        assert not hasattr(dialogue, "choix_compte")
