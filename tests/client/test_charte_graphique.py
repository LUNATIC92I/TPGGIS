"""Charte graphique : systeme de themes, contrastes, motif bigarre, identite et carte verifiee."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QTableView  # noqa: E402

from tpgis.client.api_client.client import ClientAPI  # noqa: E402
from tpgis.client.api_client.travail import Executeur  # noqa: E402
from tpgis.client.theme import CLAIR, SOMBRE, THEMES, appliquer_theme, feuille_de_style, theme_courant  # noqa: E402
from tpgis.client.theme.jetons import PAIRES_CONTRASTE  # noqa: E402
from tpgis.client.windows.base import SessionClient  # noqa: E402
from tpgis.server.database.seed.demonstration import MOT_DE_PASSE_DEMO  # noqa: E402
from tpgis.shared import charte  # noqa: E402

RACINE = Path(__file__).resolve().parents[2]
CLIENT = RACINE / "tpgis" / "client"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    Executeur.synchrone = True
    appliquer_theme(app, "clair")
    yield app
    appliquer_theme(app, "clair")


def _session(client, connexions, identifiant, environnement="demonstration") -> SessionClient:
    api = ClientAPI("http://testserver", http=client)
    api.connecter(identifiant, MOT_DE_PASSE_DEMO, connexions.code(identifiant))
    return SessionClient(api=api, moi=api.get("/auth/moi"), executeur=Executeur(), environnement=environnement)


# Palette et jetons


def test_palette_de_reference_de_la_charte():
    assert charte.PALETTE == {
        "vert_olive": "#26382A",
        "vert_kaki": "#536344",
        "sable": "#C5B58A",
        "brun_terre": "#806348",
        "anthracite": "#202521",
        "ivoire": "#F2F0E7",
    }
    assert CLAIR["navigation_fond"] == charte.VERT_OLIVE
    assert CLAIR["fond"] == charte.IVOIRE
    assert CLAIR["texte"] == charte.ANTHRACITE


@pytest.mark.parametrize("theme", list(THEMES.values()), ids=list(THEMES))
def test_contrastes_wcag(theme):
    echecs = [
        f"{texte} sur {fond} : {charte.contraste(theme[texte], theme[fond]):.2f} < {minimum}"
        for texte, fond, minimum in PAIRES_CONTRASTE
        if charte.contraste(theme[texte], theme[fond]) < minimum
    ]
    assert echecs == []


def test_contraste_calcule_selon_wcag():
    assert charte.contraste("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert charte.contraste("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize("theme", list(THEMES.values()), ids=list(THEMES))
def test_les_deux_themes_definissent_les_memes_jetons(theme):
    assert set(theme.couleurs) == set(CLAIR.couleurs)
    assert len(theme.carte_sequentielle) == 6 and len(theme.carte_tendance) == 3
    assert all(re.fullmatch(r"#[0-9A-F]{6}", v) for v in theme.couleurs.values())


@pytest.mark.parametrize("theme", list(THEMES.values()), ids=list(THEMES))
def test_feuille_de_style_entierement_resolue(qapp, theme):
    qss = feuille_de_style(theme)
    assert "{{" not in qss and "}}" not in qss
    assert theme["navigation_fond"] in qss and theme["accent"] in qss
    assert "Segoe UI" in qss


def test_aucune_couleur_codee_en_dur_hors_du_systeme_de_themes():
    """Les couleurs ne sont definies que dans les jetons ; QSS, carte, graphiques et fenetres les lisent."""
    modele = (CLIENT / "resources" / "styles" / "tpgis.qss").read_text(encoding="utf-8")
    assert re.findall(r"#[0-9A-Fa-f]{3,6}\b", modele) == []
    fautifs = []
    for fichier in CLIENT.rglob("*.py"):
        if fichier.parent.name == "theme":
            continue
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"[\"']#[0-9A-Fa-f]{6}[\"']|rgba?\(", ligne):
                fautifs.append(f"{fichier.relative_to(RACINE)}:{numero}")
    assert fautifs == []


def test_icones_vectorielles_coherentes():
    icones = CLIENT / "resources" / "icons"
    for svg in icones.glob("*.svg"):
        if svg.name == "logo_tpgis.svg":
            continue
        contenu = svg.read_text(encoding="utf-8")
        assert 'viewBox="0 0 24 24"' in contenu, svg.name
        assert "currentColor" in contenu and not re.search(r"#[0-9A-Fa-f]{3,6}", contenu), svg.name


# Application du theme


def test_bascule_clair_sombre_a_chaud(qapp, client, connexions):
    from tpgis.client.windows.principale import FenetrePrincipale

    fenetre = FenetrePrincipale(_session(client, connexions, "responsable.ndj"))
    fenetre.show()
    qapp.processEvents()
    assert theme_courant() is CLAIR
    assert "Affichage sombre" in fenetre.bouton_theme.text()
    appliquer_theme(qapp, "sombre")
    qapp.processEvents()
    assert theme_courant() is SOMBRE
    assert qapp.palette().color(QPalette.Window) == QColor(SOMBRE["fond"])
    assert "Affichage clair" in fenetre.bouton_theme.text()
    carte = fenetre.pages.widget(0).carte
    assert carte.backgroundBrush().color() == QColor(SOMBRE["carte_fond"])
    appliquer_theme(qapp, "clair")
    qapp.processEvents()
    assert carte.backgroundBrush().color() == QColor(CLAIR["carte_fond"])
    fenetre.close()


def test_changement_de_theme_sans_erreur_apres_destruction_des_composants(qapp, monkeypatch):
    """Les composants detruits (deconnexion, fermeture) ne recoivent plus les changements de theme."""
    import sys

    import shiboken6

    from tpgis.client.map.carte import CarteTchad
    from tpgis.client.theme.bigarre import LisereBigarre, PanneauBigarre
    from tpgis.client.widgets.graphiques import GraphiqueBarres, GraphiqueColonnes

    erreurs = []
    monkeypatch.setattr(sys, "excepthook", lambda *exc: erreurs.append(exc))
    composants = [GraphiqueBarres("a"), GraphiqueColonnes("b"), CarteTchad(), LisereBigarre(), PanneauBigarre()]
    for composant in composants:
        shiboken6.delete(composant)
    appliquer_theme(qapp, "sombre")
    appliquer_theme(qapp, "clair")
    qapp.processEvents()
    assert erreurs == []


def test_theme_inconnu_retombe_sur_le_theme_clair(qapp):
    assert appliquer_theme(qapp, "inexistant") is CLAIR


# Motif bigarre


def test_motif_bigarre_discret_deterministe_et_dans_la_palette():
    a = charte.motif_bigarre(400, 120, graine=3)
    b = charte.motif_bigarre(400, 120, graine=3)
    assert a == b and a != charte.motif_bigarre(400, 120, graine=4)
    assert {f.couleur for f in a} <= {charte.VERT_OLIVE, charte.VERT_KAKI, charte.SABLE, charte.BRUN_TERRE}
    assert all(len(f.points) >= 7 for f in a)
    segments = charte.contour_lisse(a[0].points)
    assert len(segments) == len(a[0].points) + 1


def test_motif_jamais_derriere_les_formulaires(qapp, client, donnees):
    """Ecran de connexion : le motif n'occupe que le panneau decoratif, sans aucun champ."""
    from tpgis.client.theme.bigarre import LisereBigarre, PanneauBigarre
    from tpgis.client.windows.connexion import DialogueConnexion

    dialogue = DialogueConnexion(ClientAPI("http://testserver", http=client), "demonstration")
    decor = dialogue.findChild(PanneauBigarre)
    assert decor is not None
    assert decor.findChildren(QLineEdit) == []
    for champ in dialogue.findChildren(QLineEdit):
        parent = champ.parentWidget()
        while parent is not None:
            assert not isinstance(parent, (PanneauBigarre, LisereBigarre))
            parent = parent.parentWidget()
    assert LisereBigarre(6).findChildren(QTableView) == []


# Mentions des donnees fictives


def test_chiffres_signales_fictifs_hors_production(qapp, client, connexions):
    from tpgis.client.widgets.communs import MentionFictive
    from tpgis.client.windows.principale import FenetrePrincipale

    fenetre = FenetrePrincipale(_session(client, connexions, "responsable.ndj", "demonstration"))
    tableau = fenetre.pages.widget(0)
    assert tableau.findChildren(MentionFictive), "le tableau de bord doit signaler des chiffres fictifs"
    assert tableau.carte.mention is not None and tableau.carte.mention.text() == "Chiffres fictifs"
    fenetre.close()

    fenetre = FenetrePrincipale(_session(client, connexions, "responsable.ndj", "production"))
    tableau = fenetre.pages.widget(0)
    assert tableau.findChildren(MentionFictive) == [] and tableau.carte.mention is None
    fenetre.close()


def test_rapport_pdf_couverture_et_mention_fictive(client, connexions):
    import base64
    import zlib

    r = client.get("/api/v1/statistiques/rapport.pdf", headers=connexions.entetes("responsable.ndj"))
    assert r.status_code == 200
    texte = b""
    for m in re.finditer(rb"/Filter\s*(\[[^\]]*\]|/\w+)[^>]*>>\s*stream\r?\n(.*?)endstream", r.content, re.S):
        filtre, flux = m.group(1), m.group(2)
        if b"ASCII85" in filtre:
            flux = base64.a85decode(flux.strip(), adobe=True)
        if b"Flate" in filtre:
            flux = zlib.decompress(flux)
        texte += flux
    assert b"FICTIVES" in texte
    # Couverture : formes remplies aux couleurs de la charte (olive puis motif).
    olive = " ".join(f"{c / 255:.6g}".lstrip("0") for c in charte.rgb(charte.VERT_OLIVE)).encode()
    assert olive + b" rg" in texte
    assert texte.count(b" c ") > 100  # contours courbes des formes irregulieres


# Identite configurable


def test_nom_et_logo_configurables(qapp, client, connexions, tmp_path, monkeypatch):
    from tpgis.client.config import charger_configuration
    from tpgis.client.main import appliquer_identite
    from tpgis.client.theme import IdentiteVisuelle, definir_identite, identite
    from tpgis.client.windows.principale import FenetrePrincipale

    logo = tmp_path / "logo.svg"
    logo.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>',
        encoding="utf-8",
    )
    (tmp_path / "TPGIS").mkdir()
    (tmp_path / "TPGIS" / "client.ini").write_text(
        f"[serveur]\nurl = https://exemple.invalid\n\n[identite]\nnom = SIGEP\n"
        f"nom_complet = Système de démonstration\nlogo = {logo}\n\n[affichage]\ntheme = sombre\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config = charger_configuration()
    assert config.theme == "sombre" and config.nom_logiciel == "SIGEP"
    try:
        appliquer_identite(config)
        assert identite().chemin_logo() == logo
        fenetre = FenetrePrincipale(_session(client, connexions, "responsable.ndj"))
        assert fenetre.windowTitle() == "SIGEP : Système de démonstration"
        fenetre.close()
    finally:
        definir_identite(IdentiteVisuelle())
    assert identite().chemin_logo().name == "logo_tpgis.svg"


def test_logo_par_defaut_sans_embleme_officiel():
    logo = (CLIENT / "resources" / "icons" / "logo_tpgis.svg").read_text(encoding="utf-8")
    assert "<image" not in logo and "<text" not in logo
    assert not (CLIENT / "resources" / "icons" / "embleme.svg").exists()


# Carte du Tchad : donnees geographiques verifiees


def test_donnees_geographiques_verifiees():
    from tpgis.shared.geographie import charger, repertoire_geodata

    sources = json.loads((repertoire_geodata() / "SOURCES.json").read_text(encoding="utf-8"))
    for nom, empreinte in sources["sha256"].items():
        assert hashlib.sha256((repertoire_geodata() / nom).read_bytes()).hexdigest() == empreinte, nom

    provinces = charger("tchad_provinces.geojson")["features"]
    codes = {f["properties"]["code"] for f in provinces}
    # ISO 3166-2:TD, decoupage de 2018 en 23 provinces.
    assert codes == {
        "TD-BA", "TD-BG", "TD-BO", "TD-CB", "TD-EE", "TD-EO", "TD-GR", "TD-HL", "TD-KA", "TD-LC", "TD-LO",
        "TD-LR", "TD-MA", "TD-MC", "TD-ME", "TD-MO", "TD-ND", "TD-OD", "TD-SA", "TD-SI", "TD-TA", "TD-TI",
        "TD-WF",
    }  # fmt: skip

    def sommets(geometrie):
        polygones = [geometrie["coordinates"]] if geometrie["type"] == "Polygon" else geometrie["coordinates"]
        return [pt for poly in polygones for anneau in poly for pt in anneau]

    tous = [pt for f in provinces for pt in sommets(f["geometry"])]
    assert 13.3 < min(x for x, _ in tous) and max(x for x, _ in tous) < 24.1
    assert 7.3 < min(y for _, y in tous) and max(y for _, y in tous) < 23.5

    def contient(geometrie, x, y):
        polygones = [geometrie["coordinates"]] if geometrie["type"] == "Polygon" else geometrie["coordinates"]
        for poly in polygones:
            anneau, dedans = poly[0], False
            for (x1, y1), (x2, y2) in zip(anneau, anneau[1:] + anneau[:1], strict=False):
                if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    dedans = not dedans
            if dedans:
                return True
        return False

    ndjamena = next(f for f in provinces if f["properties"]["code"] == "TD-ND")
    assert contient(ndjamena["geometry"], 15.04, 12.11)  # N'Djamena, capitale
    abeche = next(f for f in provinces if f["properties"]["code"] == "TD-OD")
    assert contient(abeche["geometry"], 20.83, 13.83)  # Abeche, chef lieu du Ouaddai
