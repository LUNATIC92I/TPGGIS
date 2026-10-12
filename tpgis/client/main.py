"""Point d'entree du client de bureau TPGIS (Windows 10 et 11)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from tpgis.client.api_client.client import ClientAPI, ErreurAPI
from tpgis.client.api_client.travail import Executeur
from tpgis.client.config import ConfigurationClient, charger_configuration
from tpgis.client.langue import appliquer_langue, preference_langue
from tpgis.client.theme import IdentiteVisuelle, definir_identite, identite
from tpgis.client.theme import appliquer_theme as _appliquer_theme
from tpgis.client.windows.base import SessionClient
from tpgis.client.windows.connexion import DialogueChangementMotDePasse, DialogueConnexion, DialogueEnrolementMFA
from tpgis.client.windows.principale import FenetrePrincipale
from tpgis.shared.i18n import tr


def declarer_extensions_qt() -> None:
    """Executable autonome : indique a Qt l'emplacement des extensions embarquees."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return
    from pathlib import Path

    from PySide6.QtCore import QCoreApplication

    for candidat in (Path(base) / "PySide6" / "plugins", Path(base) / "PySide6" / "Qt" / "plugins"):
        if candidat.exists():
            QCoreApplication.addLibraryPath(str(candidat))


def appliquer_theme(app: QApplication, nom: str = "clair") -> None:
    _appliquer_theme(app, nom)


def preference_theme(config: ConfigurationClient) -> str:
    """Le choix fait par l'utilisateur sur ce poste prime sur la valeur deployee."""
    choix = QSettings("TPGIS", "client").value("affichage/theme", "")
    return choix if choix in ("clair", "sombre") else config.theme


def appliquer_identite(config: ConfigurationClient) -> None:
    defaut = IdentiteVisuelle()
    definir_identite(
        IdentiteVisuelle(
            nom=config.nom_logiciel or defaut.nom,
            nom_complet=config.nom_complet or defaut.nom_complet,
            sous_titre=config.sous_titre or defaut.sous_titre,
            logo=config.logo,
        )
    )


def ouvrir_session(api: ClientAPI, parent=None, environnement: str = "", comptes_demo=None) -> SessionClient | None:
    """Connexion complete : identifiants, MFA, changement de mot de passe, enrolement."""
    while True:
        dialogue = DialogueConnexion(api, environnement, parent, comptes_demo=comptes_demo)
        code = dialogue.exec()
        # Destruction explicite dans le fil principal (jamais par le ramasse miettes d'un autre fil).
        dialogue.deleteLater()
        if code == DialogueConnexion.CHANGEMENT_LANGUE:
            continue
        if code != QDialog.Accepted:
            return None
        type_session = dialogue.resultat["type_session"]
        if type_session == "CHANGEMENT_MOT_DE_PASSE":
            DialogueChangementMotDePasse(api, parent).exec()
            api.jeton = None
            continue
        if type_session == "ENROLEMENT_MFA":
            if DialogueEnrolementMFA(api, parent).exec() == QDialog.Accepted:
                QMessageBox.information(
                    parent, tr("MFA activée"), tr("Reconnectez-vous avec votre code de vérification.")
                )
            api.jeton = None
            continue
        return SessionClient(
            api=api, moi=api.get("/auth/moi"), executeur=Executeur(), environnement=environnement or None
        )


def creer_application_qt() -> QApplication:
    declarer_extensions_qt()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("TPGIS")
    return app


def main(config: ConfigurationClient | None = None, comptes_demo=None) -> int:
    app = creer_application_qt()
    config = config or charger_configuration()
    appliquer_identite(config)
    app.setApplicationName(identite().nom)
    appliquer_theme(app, preference_theme(config))
    appliquer_langue(preference_langue(config.langue))
    try:
        api = ClientAPI(
            config.url_serveur,
            certificat_ca=config.certificat_ca,
            delai=config.delai_secondes,
            autoriser_http_local=config.autoriser_http_local,
        )
    except ValueError as exc:
        QMessageBox.critical(None, tr("Configuration invalide"), str(exc))
        return 2
    try:
        sante = api.verifier_disponibilite()
    except ErreurAPI as exc:
        QMessageBox.critical(
            None,
            tr("Serveur indisponible"),
            tr(
                "{exc}\n\nAdresse configurée : {url_serveur}\nAucune donnée n'est stockée sur ce "
                "poste : l'application ne peut pas fonctionner sans le serveur institutionnel.",
                exc=exc,
                url_serveur=config.url_serveur,
            ),
        )
        return 3
    if sante.get("statut") != "ok":
        QMessageBox.warning(None, tr("Service dégradé"), tr("Le serveur signale un fonctionnement dégradé."))

    fenetre = None
    while True:
        session = ouvrir_session(api, environnement=sante.get("environnement", ""), comptes_demo=comptes_demo)
        if session is None:
            return 0
        while True:
            fenetre = FenetrePrincipale(session, config)
            etat = {"deconnexion": False, "langue": False}

            def _fin(cle, f=fenetre, etat=etat):
                etat[cle] = True
                f.close()

            fenetre.deconnexion_demandee.connect(lambda: _fin("deconnexion"))
            fenetre.langue_changee.connect(lambda: _fin("langue"))
            fenetre.showMaximized()
            app.exec()
            fenetre.deleteLater()
            if etat["langue"]:
                # Nouvelle langue : meme session, fenetre reconstruite.
                continue
            if etat["deconnexion"]:
                break
            api.deconnecter()
            return 0


if __name__ == "__main__":
    sys.exit(main())
