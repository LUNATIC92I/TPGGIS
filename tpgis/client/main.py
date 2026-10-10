"""Point d'entree du client de bureau TPGIS (Windows 10 et 11)."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from tpgis.client.api_client.client import ClientAPI, ErreurAPI
from tpgis.client.api_client.travail import Executeur
from tpgis.client.config import ConfigurationClient, charger_configuration
from tpgis.client.widgets.communs import chemin_ressource
from tpgis.client.windows.base import SessionClient
from tpgis.client.windows.connexion import DialogueChangementMotDePasse, DialogueConnexion, DialogueEnrolementMFA
from tpgis.client.windows.principale import FenetrePrincipale


def appliquer_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(chemin_ressource("styles/tpgis.qss").read_text(encoding="utf-8"))
    app.setWindowIcon(QIcon(str(chemin_ressource("icons/embleme_sombre.svg"))))


def ouvrir_session(api: ClientAPI, parent=None, environnement: str = "") -> SessionClient | None:
    """Connexion complete : identifiants, MFA, changement de mot de passe, enrolement."""
    while True:
        dialogue = DialogueConnexion(api, environnement, parent)
        if dialogue.exec() != QDialog.Accepted:
            return None
        type_session = dialogue.resultat["type_session"]
        if type_session == "CHANGEMENT_MOT_DE_PASSE":
            DialogueChangementMotDePasse(api, parent).exec()
            api.jeton = None
            continue
        if type_session == "ENROLEMENT_MFA":
            if DialogueEnrolementMFA(api, parent).exec() == QDialog.Accepted:
                QMessageBox.information(parent, "MFA activée", "Reconnectez-vous avec votre code de vérification.")
            api.jeton = None
            continue
        return SessionClient(api=api, moi=api.get("/auth/moi"), executeur=Executeur())


def main(config: ConfigurationClient | None = None) -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("TPGIS")
    app.setOrganizationName("TPGIS")
    appliquer_theme(app)
    config = config or charger_configuration()
    try:
        api = ClientAPI(
            config.url_serveur,
            certificat_ca=config.certificat_ca,
            delai=config.delai_secondes,
            autoriser_http_local=config.autoriser_http_local,
        )
    except ValueError as exc:
        QMessageBox.critical(None, "Configuration invalide", str(exc))
        return 2
    try:
        sante = api.verifier_disponibilite()
    except ErreurAPI as exc:
        QMessageBox.critical(
            None,
            "Serveur indisponible",
            f"{exc}\n\nAdresse configurée : {config.url_serveur}\n"
            "Aucune donnée n'est stockée sur ce poste : l'application ne peut pas fonctionner "
            "sans le serveur institutionnel.",
        )
        return 3
    if sante.get("statut") != "ok":
        QMessageBox.warning(None, "Service dégradé", "Le serveur signale un fonctionnement dégradé.")

    fenetre = None
    while True:
        session = ouvrir_session(api)
        if session is None:
            return 0
        fenetre = FenetrePrincipale(session, config)
        boucle_fin = {"deconnexion": False}

        def _deconnexion(f=fenetre, etat=boucle_fin):
            etat["deconnexion"] = True
            f.close()

        fenetre.deconnexion_demandee.connect(_deconnexion)
        fenetre.showMaximized()
        app.exec()
        if not boucle_fin["deconnexion"]:
            api.deconnecter()
            return 0


if __name__ == "__main__":
    sys.exit(main())
