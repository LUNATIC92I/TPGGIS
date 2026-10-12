"""Genere les captures de toutes les interfaces du client (donnees synthetiques).

Prerequis : serveur de demonstration en HTTPS sur 127.0.0.1:8443.
Usage : QT_QPA_PLATFORM=offscreen python scripts/captures_interfaces.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QTabWidget  # noqa: E402

from tpgis.client.api_client.client import ClientAPI, ErreurAPI  # noqa: E402
from tpgis.client.api_client.travail import Executeur  # noqa: E402
from tpgis.client.main import appliquer_theme  # noqa: E402
from tpgis.client.windows.base import SessionClient  # noqa: E402
from tpgis.server.database.seed.demonstration import MOT_DE_PASSE_DEMO, code_totp_demo  # noqa: E402

CIBLE = Path(__file__).resolve().parents[1] / "docs" / "captures" / "interfaces"
CIBLE.mkdir(parents=True, exist_ok=True)
app = QApplication(sys.argv)
appliquer_theme(app)
Executeur.synchrone = True
for nom in ("warning", "information", "critical"):
    setattr(QMessageBox, nom, lambda *a, **k: None)


def attendre(s=0.5):
    b = QEventLoop()
    QTimer.singleShot(int(s * 1000), b.quit)
    b.exec()


def session(ident):
    api = ClientAPI("https://127.0.0.1:8443", certificat_ca="var/tls/ac_demo.crt")
    for _ in range(6):
        code = None
        try:
            code = code_totp_demo(ident)
        except KeyError:
            pass
        try:
            api.connecter(ident, MOT_DE_PASSE_DEMO, code)
            break
        except ErreurAPI as exc:
            if exc.statut == 429:  # limitation de debit des connexions
                time.sleep(15)
                continue
            # Un code TOTP ne sert qu'une fois (anti rejeu) : attendre la periode suivante.
            if code is None or "Code de vérification" not in exc.message:
                raise
            time.sleep(31 - time.time() % 30)
    return SessionClient(api=api, moi=api.get("/auth/moi"), executeur=Executeur())


def capturer(widget, nom, taille=(1440, 860)):
    if taille:
        widget.resize(*taille)
    widget.show()
    attendre(0.6)
    widget.grab().save(str(CIBLE / f"{nom}.png"))
    print("capture", nom)


def modules(ident, prefixe, seulement=None):
    from tpgis.client.windows.principale import FenetrePrincipale

    f = FenetrePrincipale(session(ident))
    f.resize(1440, 860)
    f.show()
    for i in range(f.navigation.count()):
        libelle = f.navigation.item(i).text()
        if seulement and libelle not in seulement:
            continue
        f.navigation.setCurrentRow(i)
        attendre(0.8)
        nom = f"{prefixe}_{i + 1:02d}_" + "".join(c if c.isalnum() else "_" for c in libelle.lower())
        f.grab().save(str(CIBLE / f"{nom}.png"))
        print("capture", nom)
        page = f.pages.currentWidget()
        for onglets in page.findChildren(QTabWidget):
            for j in range(1, onglets.count()):
                onglets.setCurrentIndex(j)
                attendre(0.5)
                f.grab().save(str(CIBLE / f"{nom}_onglet_{j + 1}.png"))
                print("capture", f"{nom}_onglet_{j + 1}")
            onglets.setCurrentIndex(0)
    return f


# 1. Connexion
from tpgis.client.windows.connexion import (  # noqa: E402
    DialogueChangementMotDePasse,
    DialogueConnexion,
    DialogueReauthentification,
)

api = ClientAPI("https://127.0.0.1:8443", certificat_ca="var/tls/ac_demo.crt")
d = DialogueConnexion(api, "demonstration")
capturer(d, "00_connexion", None)
d.identifiant.setText("officier.ndj")
d.mot_de_passe.setText(MOT_DE_PASSE_DEMO)
d.connecter()
capturer(d, "00_connexion_code_mfa", None)

# 2. Tous les modules, selon les roles
modules("responsable.ndj", "responsable")
modules("admin.fonctionnel", "admin_fonctionnel", {"Utilisateurs et habilitations", "Paramètres et administration"})
modules("admin.technique", "admin_technique", {"Paramètres et administration"})
modules("auditeur", "auditeur", {"Journal d'audit"})
modules("accueil.ndj", "agent_accueil", {"Tableau de bord"})

# 3. Fenetres de detail et formulaires
s = session("officier.ndj")
s.api.finalite = "Enquete judiciaire en cours"
from tpgis.client.windows.faits_dossiers import DialogueDossier, DialogueFait, FormulaireDossier, FormulaireFait  # noqa
from tpgis.client.windows.personnes import (  # noqa: E402
    DialogueDoublons,
    DialogueFichePersonne,
    DialogueSelectionPersonne,
    FormulairePersonne,
)
from tpgis.client.windows.plaintes import DialoguePlainte, FormulairePlainte  # noqa: E402

capturer(FormulairePlainte(s), "10_formulaire_nouvelle_plainte", (760, 860))
plainte = s.api.get("/plaintes", {"taille": 1})["elements"][0]
dp = DialoguePlainte(s, plainte["id"])
for j in range(dp.onglets.count()):
    dp.onglets.setCurrentIndex(j)
    capturer(dp, f"11_detail_plainte_onglet_{j + 1}", (1000, 680))
capturer(FormulairePersonne(s), "12_formulaire_personne", (640, 760))
personne = s.api.get("/personnes", {"taille": 1})["elements"][0]
candidats = s.api.post("/personnes/doublons", {"nom": personne["nom"], "prenoms": personne.get("prenoms")})
capturer(DialogueDoublons(candidats), "13_detection_doublons", (1100, 480))
fp = DialogueFichePersonne(s, personne["id"], "Enquete judiciaire en cours")
for j in range(fp.onglets.count()):
    fp.onglets.setCurrentIndex(j)
    capturer(fp, f"14_fiche_personne_onglet_{j + 1}", (1000, 640))
sel = DialogueSelectionPersonne(s)
sel.chercher()
capturer(sel, "15_associer_une_personne", (880, 520))
fait = s.api.get("/faits", {"taille": 1})["elements"][0]
capturer(FormulaireFait(s), "16_formulaire_fait", (720, 720))
df = DialogueFait(s, fait["id"])
capturer(df, "17_detail_fait", (920, 600))
capturer(FormulaireDossier(s), "18_formulaire_dossier", (700, 560))
dossier = s.api.get("/dossiers", {"taille": 1})["elements"][0]
dd = DialogueDossier(s, dossier["id"])
for j in range(dd.onglets.count()):
    dd.onglets.setCurrentIndex(j)
    capturer(dd, f"19_detail_dossier_onglet_{j + 1}", (1000, 680))
capturer(DialogueReauthentification(s.api, True), "20_confirmation_identite", None)
capturer(DialogueChangementMotDePasse(s.api), "21_changement_mot_de_passe", None)
print("termine")

# 4. Recherche avec resultats et pieces d'une plainte
from tpgis.client.windows.recherche import PageDocuments, PageRecherche  # noqa: E402

sr = session("responsable.ndj")
pr = PageRecherche(sr)
pr.show()
pr.finalite.setCurrentIndex(0)
personne = sr.api.get("/personnes", {"taille": 1})["elements"][0]
pr.nom.setText(personne["nom"])
pr.rechercher()
capturer(pr, "22_recherche_avec_resultats", (1300, 820))
plainte = sr.api.get("/plaintes", {"taille": 1})["elements"][0]
so = session("officier.ndj")
so.api.deposer(
    "/documents",
    {"intitule": "Certificat médical (fictif)", "type_piece": "PIECE_JUSTIFICATIVE", "plainte_id": plainte["id"]},
    "certificat_fictif.pdf",
    b"%PDF-1.4\n%%EOF\n",
)
pd = PageDocuments(sr)
pd.show()
pd.numero.setText(plainte["numero"])
pd.ouvrir()
capturer(pd, "23_pieces_d_une_plainte", (1300, 600))
print("termine 2")

# 5. Charte graphique : affichages clair et sombre
from tpgis.client.windows.plaintes import FormulairePlainte  # noqa: E402
from tpgis.client.windows.principale import FenetrePrincipale  # noqa: E402

CHARTE = CIBLE.parent / "charte"
CHARTE.mkdir(exist_ok=True)
fenetre = FenetrePrincipale(sr)
fenetre.resize(1440, 860)
fenetre.show()
for theme in ("clair", "sombre"):
    appliquer_theme(app, theme)
    d = DialogueConnexion(api, "demonstration")
    d.resize(820, 480)
    d.show()
    attendre(0.6)
    d.grab().save(str(CHARTE / f"connexion_{theme}.png"))
    d.close()
    for i, nom in ((0, "tableau_de_bord"), (1, "plaintes"), (8, "cartographie"), (9, "rapports")):
        fenetre.navigation.setCurrentRow(i)
        attendre(1.0)
        fenetre.grab().save(str(CHARTE / f"{nom}_{theme}.png"))
    formulaire = FormulairePlainte(so)
    capturer(formulaire, f"../charte/formulaire_plainte_{theme}", (760, 860))
    formulaire.close()
    print("charte", theme)
appliquer_theme(app, "clair")
fenetre.close()
print("termine 3")

# 6. Interface en anglais (choix de la langue)
from tpgis.client.langue import appliquer_langue  # noqa: E402
from tpgis.client.windows.plaintes import DialoguePlainte  # noqa: E402

ANGLAIS = CIBLE.parent / "anglais"
ANGLAIS.mkdir(exist_ok=True)
appliquer_langue("en")
d = DialogueConnexion(api, "demonstration")
d.resize(820, 480)
d.show()
attendre(0.6)
d.grab().save(str(ANGLAIS / "connexion.png"))
d.close()
se = session("responsable.ndj")
fenetre = FenetrePrincipale(se)
fenetre.resize(1440, 860)
fenetre.show()
for i in range(fenetre.navigation.count()):
    fenetre.navigation.setCurrentRow(i)
    attendre(1.0)
    nom = "".join(c if c.isalnum() else "_" for c in fenetre.navigation.item(i).text().lower())
    fenetre.grab().save(str(ANGLAIS / f"{i + 1:02d}_{nom}.png"))
    print("anglais", nom)
fenetre.close()
plainte = se.api.get("/plaintes", {"taille": 1})["elements"][0]
capturer(DialoguePlainte(se, plainte["id"]), "../anglais/detail_plainte", (1000, 680))
capturer(FormulairePlainte(se), "../anglais/formulaire_plainte", (760, 860))
appliquer_langue("fr")
print("termine 4")

# Fin : fenetres detruites dans le fil principal avant l'arret de Python (ordre de
# destruction maitrise, sinon Qt peut planter a la sortie de l'interpreteur).
import gc  # noqa: E402

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

for w in app.topLevelWidgets():
    w.close()
    w.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
gc.collect()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
