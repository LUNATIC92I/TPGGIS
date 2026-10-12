"""Interface bilingue : catalogue complet, serveur traduit, parcours de toutes les pages en anglais."""

from __future__ import annotations

import json
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QComboBox,
    QGroupBox,
    QLabel,
    QTableView,
    QTabWidget,
)

from tests.i18n.collecte import toutes_les_cles  # noqa: E402
from tpgis.client.api_client.client import ClientAPI  # noqa: E402
from tpgis.client.api_client.travail import Executeur  # noqa: E402
from tpgis.client.windows.base import SessionClient  # noqa: E402
from tpgis.server.database.seed.demonstration import MOT_DE_PASSE_DEMO  # noqa: E402
from tpgis.shared import i18n  # noqa: E402

CATALOGUE = json.loads((i18n.repertoire_catalogues() / "en.json").read_text(encoding="utf-8"))


def _parametres(texte: str) -> set[str]:
    return set(re.findall(r"\{(\w+)", texte))


# Catalogue


def test_chaque_texte_affiche_a_sa_traduction_anglaise():
    manquants = {k: v for k, v in toutes_les_cles().items() if k not in CATALOGUE}
    assert manquants == {}, "\n".join(f"{v} : {k!r}" for k, v in manquants.items())


def test_catalogue_sans_entree_orpheline():
    orphelines = set(CATALOGUE) - set(toutes_les_cles())
    assert orphelines == set()


def test_parametres_identiques_et_traductions_non_vides():
    for francais, anglais in CATALOGUE.items():
        assert anglais.strip(), francais
        assert _parametres(francais) == _parametres(anglais), francais


def test_traduction_et_repli_sur_le_francais():
    assert i18n.traduire("Tableau de bord", "en") == "Dashboard"
    assert i18n.traduire("Tableau de bord", "fr") == "Tableau de bord"
    assert i18n.traduire("Texte absent du catalogue", "en") == "Texte absent du catalogue"
    assert i18n.traduire("Plainte {numero}  |  {libelle}", "en", numero="PL-1", libelle="Open") == (
        "Complaint PL-1  |  Open"
    )
    assert i18n.normaliser("en-GB,en;q=0.9,fr;q=0.8") == "en"
    assert i18n.normaliser("de-DE") == "fr"
    assert i18n.normaliser(None) == "fr"


# Serveur


def test_messages_du_serveur_dans_la_langue_demandee(client, donnees):
    francais = client.get("/api/v1/plaintes").json()
    anglais = client.get("/api/v1/plaintes", headers={"Accept-Language": "en-GB,en;q=0.9"}).json()
    assert francais["detail"] == "Authentification requise."
    assert anglais["detail"] == "Authentication required."
    assert anglais["code"] == francais["code"]


def test_message_a_parametres_traduit(client, connexions):
    h = connexions.entetes("responsable.ndj")
    plainte = client.get("/api/v1/plaintes", headers=h, params={"statut": "ARCHIVEE"}).json()["elements"][0]
    r = client.post(
        f"/api/v1/plaintes/{plainte['id']}/statut",
        headers={**h, "Accept-Language": "en"},
        json={"statut": "NOUVELLE", "version": plainte.get("version", 1)},
    )
    assert r.status_code in (409, 422), r.text
    assert "é" not in r.json()["detail"], r.json()["detail"]


# Client


@pytest.fixture
def qapp_anglais(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    app = QApplication.instance() or QApplication([])
    from tpgis.client.langue import appliquer_langue
    from tpgis.client.main import appliquer_theme

    appliquer_theme(app)
    Executeur.synchrone = True
    appliquer_langue("en")
    yield app
    appliquer_langue("fr")


def _session(client, connexions, identifiant):
    api = ClientAPI("http://testserver", http=client)
    api.connecter(identifiant, MOT_DE_PASSE_DEMO, connexions.code(identifiant))
    return SessionClient(api=api, moi=api.get("/auth/moi"), executeur=Executeur(), environnement="demonstration")


def _textes_visibles(fenetre) -> list[str]:
    textes = [fenetre.windowTitle()]
    for w in fenetre.findChildren(QLabel) + fenetre.findChildren(QAbstractButton):
        if w.isVisibleTo(fenetre):
            textes += [w.text(), w.toolTip()]
    textes += [g.title() for g in fenetre.findChildren(QGroupBox)]
    for onglets in fenetre.findChildren(QTabWidget):
        textes += [onglets.tabText(i) for i in range(onglets.count())]
    for liste in fenetre.findChildren(QComboBox):
        textes += [liste.itemText(i) for i in range(liste.count())]
    for vue in fenetre.findChildren(QTableView):
        modele = vue.model()
        if modele is not None:
            textes += [str(modele.headerData(c, 1)) for c in range(modele.columnCount())]
    return [t for t in textes if t]


def _francais_restant(textes: list[str]) -> list[str]:
    """Un texte affiche egal a une cle francaise dont la traduction differe n'a pas ete traduit."""
    restes = []
    for t in textes:
        brut = re.sub(r"<[^>]+>", "", t)
        for francais, anglais in CATALOGUE.items():
            if francais != anglais and len(francais) > 3 and "{" not in francais:
                if brut == francais or (len(francais) > 15 and francais in brut):
                    restes.append(f"{t!r} (attendu : {anglais!r})")
                    break
    return restes


def test_toutes_les_pages_en_anglais(qapp_anglais, client, connexions, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from tpgis.client.windows.principale import FenetrePrincipale

    for nom in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, nom, lambda *a, **k: None)
    restes = []
    for identifiant in ("responsable.ndj", "admin.fonctionnel", "admin.technique", "auditeur", "accueil.ndj"):
        fenetre = FenetrePrincipale(_session(client, connexions, identifiant))
        fenetre.resize(1440, 860)
        fenetre.show()
        assert fenetre.navigation.item(0).text() == "Dashboard"
        for i in range(fenetre.navigation.count()):
            fenetre.navigation.setCurrentRow(i)
            qapp_anglais.processEvents()
            for onglets in fenetre.pages.currentWidget().findChildren(QTabWidget):
                for j in range(onglets.count()):
                    onglets.setCurrentIndex(j)
                    qapp_anglais.processEvents()
                    restes += [f"{identifiant} / {fenetre.navigation.item(i).text()} : {r}"
                               for r in _francais_restant(_textes_visibles(fenetre))]  # fmt: skip
            restes += [f"{identifiant} / {fenetre.navigation.item(i).text()} : {r}"
                       for r in _francais_restant(_textes_visibles(fenetre))]  # fmt: skip
        fenetre.close()
    assert restes == [], "\n".join(sorted(set(restes)))


def test_fenetres_de_detail_et_formulaires_en_anglais(qapp_anglais, client, connexions):
    from tpgis.client.windows.faits_dossiers import DialogueDossier, FormulaireDossier, FormulaireFait
    from tpgis.client.windows.personnes import FormulairePersonne
    from tpgis.client.windows.plaintes import DialoguePlainte, FormulairePlainte

    session = _session(client, connexions, "officier.ndj")
    plainte = session.api.get("/plaintes", {"taille": 1})["elements"][0]
    dossier = session.api.get("/dossiers", {"taille": 1})["elements"][0]
    restes = []
    for fenetre in (
        FormulairePlainte(session),
        DialoguePlainte(session, plainte["id"]),
        FormulairePersonne(session),
        FormulaireFait(session),
        FormulaireDossier(session),
        DialogueDossier(session, dossier["id"]),
    ):
        fenetre.show()
        qapp_anglais.processEvents()
        restes += [f"{type(fenetre).__name__} : {r}" for r in _francais_restant(_textes_visibles(fenetre))]
        fenetre.close()
    assert restes == [], "\n".join(restes)


def test_choix_de_la_langue_a_la_connexion(qapp_anglais, client, donnees):
    from tpgis.client.windows.connexion import DialogueConnexion

    dialogue = DialogueConnexion(ClientAPI("http://testserver", http=client), "demonstration")
    assert dialogue.valider.text() == "Sign in"
    dialogue.choix_langue.setCurrentIndex(dialogue.choix_langue.findData("fr"))
    assert dialogue.result() == DialogueConnexion.CHANGEMENT_LANGUE
    assert i18n.langue_courante() == "fr"
    assert QSettings("TPGIS", "client").value("affichage/langue") == "fr"
    nouveau = DialogueConnexion(ClientAPI("http://testserver", http=client), "demonstration")
    assert nouveau.valider.text() == "Se connecter"


def test_bascule_de_langue_depuis_le_bandeau(qapp_anglais, client, connexions):
    from tpgis.client.windows.principale import FenetrePrincipale

    fenetre = FenetrePrincipale(_session(client, connexions, "responsable.ndj"))
    assert fenetre.bouton_langue.text() == "Français"
    signaux = []
    fenetre.langue_changee.connect(lambda: signaux.append(True))
    fenetre.bouton_langue.click()
    assert signaux == [True] and i18n.langue_courante() == "fr"
    fenetre.close()
    reconstruite = FenetrePrincipale(fenetre.session)
    assert reconstruite.navigation.item(0).text() == "Tableau de bord"
    assert reconstruite.bouton_langue.text() == "English"
    reconstruite.close()
