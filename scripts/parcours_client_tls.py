"""Parcours de verification du client reel en TLS (mode asynchrone) et captures d'ecran.

Prerequis : serveur de demonstration demarre en HTTPS sur 127.0.0.1:8443
(scripts/lancer_demo.sh). Usage : QT_QPA_PLATFORM=offscreen python scripts/parcours_client_tls.py
Les captures sont ecrites dans docs/captures (donnees synthetiques uniquement).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from tpgis.client.api_client.client import ClientAPI
from tpgis.client.api_client.travail import Executeur
from tpgis.client.main import appliquer_theme
from tpgis.client.windows.base import SessionClient
from tpgis.client.windows.connexion import DialogueConnexion
from tpgis.client.windows.principale import FenetrePrincipale
from tpgis.server.database.seed.demonstration import code_totp_demo

app = QApplication(sys.argv)
appliquer_theme(app)
api = ClientAPI("https://127.0.0.1:8443", certificat_ca="var/tls/ac_demo.crt")
print(api.verifier_disponibilite())
d = DialogueConnexion(api, "demonstration")
d.identifiant.setText("responsable.ndj")
d.mot_de_passe.setText("Demo-Tpgis-2026!")
d.connecter()
print("Message:", d.message.text())
d.grab().save("docs/captures/connexion.png")
d.code_mfa.setText(code_totp_demo("responsable.ndj"))
d.connecter()
print("Session:", d.resultat["type_session"])
session = SessionClient(api=api, moi=api.get("/auth/moi"), executeur=Executeur())
f = FenetrePrincipale(session)
f.resize(1440, 860)
f.show()


def attendre(s):
    boucle = QEventLoop()
    QTimer.singleShot(int(s * 1000), boucle.quit)
    boucle.exec()


attendre(4)
print("Plaintes (indicateur):", f.pages.widget(0).indicateurs["plaintes_total"].valeur.text())
f.grab().save("docs/captures/tableau_de_bord.png")
f.navigation.setCurrentRow(1)
attendre(3)
f.grab().save("docs/captures/plaintes.png")
f.navigation.setCurrentRow(8)
attendre(3)
f.grab().save("docs/captures/cartographie.png")
f.navigation.setCurrentRow(6)
attendre(1)
f.grab().save("docs/captures/recherche.png")
api.deconnecter()
print("ok")
