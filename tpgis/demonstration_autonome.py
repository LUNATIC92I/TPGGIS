"""TPGIS Demonstration : executable autonome lance d'un double clic (Windows 10 et 11).

Au lancement :
  1. un dossier propre a la demonstration est prepare sur le poste
     (%LOCALAPPDATA%\\TPGIS_Demonstration), totalement separe de toute
     installation de production ;
  2. au premier lancement, des certificats TLS de demonstration, des cles de
     chiffrement locales et le jeu de donnees entierement fictif sont crees ;
  3. le serveur TPGIS demarre en HTTPS sur 127.0.0.1 uniquement (port libre
     choisi automatiquement), dans l'environnement "demonstration" ;
  4. le client de bureau s'ouvre ; l'ecran de connexion propose les comptes
     fictifs et remplit leur code MFA courant.

Le serveur s'arrete a la fermeture du client. Cet executable ne doit jamais
recevoir de donnees reelles : il n'accepte aucune autre base que la sienne.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path

NOM_DOSSIER = "TPGIS_Demonstration"

# Comptes proposes a l'ecran de connexion (identifiant, libelle).
COMPTES = [
    ("responsable.ndj", "Responsable d'unité, N'Djamena (tous les modules de l'unité)"),
    ("officier.ndj", "Officier habilité, N'Djamena"),
    ("enqueteur.ndj", "Enquêteur, N'Djamena (dossiers attribués)"),
    ("accueil.ndj", "Agent d'accueil, N'Djamena"),
    ("consultation.ndj", "Consultation seule, N'Djamena"),
    ("officier.abc", "Officier habilité, Abéché"),
    ("gendarme.mdo", "Gendarmerie, brigade de Moundou"),
    ("auditeur", "Auditeur (journal d'audit)"),
    ("admin.fonctionnel", "Administrateur fonctionnel (comptes et rôles)"),
    ("admin.technique", "Administrateur technique"),
]


def dossier_demonstration() -> Path:
    if os.environ.get("TPGIS_DEMO_DOSSIER"):
        return Path(os.environ["TPGIS_DEMO_DOSSIER"])
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / NOM_DOSSIER if base else Path.home() / ".local" / "share" / NOM_DOSSIER.lower()


def _journalisation(dossier: Path) -> Path:
    """Executable sans console : les messages vont dans un fichier du dossier de demonstration."""
    journal = dossier / "demonstration.log"
    if sys.stdout is None or sys.stderr is None:
        flux = open(journal, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or flux
        sys.stderr = sys.stderr or flux
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(journal, encoding="utf-8")],
        force=True,
    )
    return journal


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _certificats(dossier: Path) -> Path:
    from cryptography import x509

    from tpgis.server.security.certificats_demo import generer

    tls = dossier / "tls"
    certificat = tls / "serveur.crt"
    valide = False
    if certificat.exists():
        expiration = x509.load_pem_x509_certificate(certificat.read_bytes()).not_valid_after_utc
        valide = expiration > datetime.now(UTC) + timedelta(days=2)
    if not valide:
        generer(tls)
    return tls


def preparer_serveur(dossier: Path, signaler=lambda _m: None):
    """Prepare le dossier, la base et les donnees fictives ; renvoie (application, parametres)."""
    from tpgis.server.config import ParametresServeur
    from tpgis.server.database.seed.demonstration import Volumes, generer
    from tpgis.server.main import creer_application

    dossier.mkdir(parents=True, exist_ok=True)
    # Les cles locales de demonstration sont creees sous ./var : on travaille dans le dossier dedie.
    os.chdir(dossier)
    signaler("Certificats de démonstration…")
    tls = _certificats(dossier)
    base = dossier / "tpgis_demo.sqlite3"
    premiere_fois = not base.exists()
    p = ParametresServeur(
        environnement="demonstration",
        database_url=f"sqlite:///{base.as_posix()}",
        repertoire_stockage=dossier / "stockage",
        repertoire_sauvegardes=dossier / "sauvegardes",
        tls_certificat=tls / "serveur.crt",
        tls_cle=tls / "serveur.key",
        hote="127.0.0.1",
        port=_port_libre(),
        antivirus="simulation",
        biometrie_adaptateur="simulation",
    )
    signaler("Base de démonstration…")
    app = creer_application(p)
    if premiere_fois:
        signaler("Création des données fictives (premier lancement)…")
        with app.state.fabrique.transaction() as bd:
            generer(bd, p, Volumes())
    return app, p


class ServeurLocal:
    """Serveur uvicorn dans un fil d'execution, ecoutant uniquement sur 127.0.0.1."""

    def __init__(self, app, p):
        import uvicorn

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=p.port,
            ssl_certfile=str(p.tls_certificat),
            ssl_keyfile=str(p.tls_cle),
            log_config=None,
            # Le client garde une connexion ouverte : l'arret n'attend pas plus de 2 secondes.
            timeout_graceful_shutdown=2,
            server_header=False,
            date_header=False,
        )
        self.serveur = uvicorn.Server(config)
        self.fil = threading.Thread(target=self.serveur.run, name="serveur-tpgis", daemon=True)

    def demarrer(self, delai: float = 30.0) -> None:
        self.fil.start()
        limite = time.monotonic() + delai
        while not self.serveur.started:
            if not self.fil.is_alive() or time.monotonic() > limite:
                raise RuntimeError("Le serveur local de démonstration n'a pas pu démarrer.")
            time.sleep(0.05)

    def arreter(self) -> None:
        self.serveur.should_exit = True
        self.fil.join(timeout=10)


def comptes_demo():
    from tpgis.client.windows.connexion import CompteDemo
    from tpgis.server.database.seed.demonstration import MOT_DE_PASSE_DEMO, SECRETS_TOTP_DEMO, code_totp_demo

    comptes = []
    for identifiant, libelle in COMPTES:
        mfa = identifiant in SECRETS_TOTP_DEMO
        comptes.append(
            CompteDemo(
                identifiant=identifiant,
                libelle=f"{libelle}{'  [MFA]' if mfa else ''}",
                mot_de_passe=MOT_DE_PASSE_DEMO,
                code_mfa=(lambda i=identifiant: code_totp_demo(i)) if mfa else None,
            )
        )
    return comptes


def _executer_avec_attente(app_qt, ecran, fonction):
    """Execute une preparation longue sans figer l'ecran d'attente."""
    resultat: dict = {}

    def _travail():
        try:
            resultat["valeur"] = fonction(lambda m: resultat.__setitem__("message", m))
        except BaseException as exc:  # noqa: BLE001
            resultat["erreur"] = exc
            resultat["trace"] = traceback.format_exc()

    fil = threading.Thread(target=_travail, daemon=True)
    fil.start()
    dernier = None
    while fil.is_alive():
        message = resultat.get("message")
        if message and message != dernier:
            ecran.message(message)
            dernier = message
        app_qt.processEvents()
        time.sleep(0.03)
    if "erreur" in resultat:
        logging.getLogger("tpgis").error(resultat["trace"])
        raise resultat["erreur"]
    return resultat["valeur"]


def _image_attente():
    """Ecran d'attente uni (sans motif) : logo, nom du logiciel et mention des donnees fictives."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

    from tpgis.client.theme import identite, theme_courant

    theme = theme_courant()
    image = QPixmap(520, 260)
    image.fill(QColor(theme["navigation_fond"]))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.drawPixmap(36, 64, identite().pixmap_logo(104))
    p.setPen(QColor(theme["navigation_texte"]))
    p.setFont(QFont("Segoe UI", 26, QFont.Bold))
    p.drawText(QRectF(164, 60, 330, 44), Qt.AlignLeft | Qt.AlignVCenter, identite().nom)
    p.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
    p.drawText(QRectF(164, 106, 330, 24), Qt.AlignLeft | Qt.AlignVCenter, "Démonstration autonome")
    p.setPen(QColor(theme["navigation_indicateur"]))
    p.setFont(QFont("Segoe UI", 9))
    mention = "Données entièrement fictives, aucune donnée réelle"
    p.drawText(QRectF(164, 132, 330, 40), Qt.AlignLeft | Qt.TextWordWrap, mention)
    p.end()
    return image


def main() -> int:
    dossier = dossier_demonstration()
    dossier.mkdir(parents=True, exist_ok=True)
    journal = _journalisation(dossier)

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QMessageBox, QSplashScreen

    from tpgis.client import main as client
    from tpgis.client.config import ConfigurationClient
    from tpgis.client.theme import identite, theme_courant

    app_qt = client.creer_application_qt()
    config = ConfigurationClient(theme="clair")
    client.appliquer_identite(config)
    app_qt.setApplicationName(f"{identite().nom} Démonstration")
    client.appliquer_theme(app_qt, client.preference_theme(config))

    class Ecran(QSplashScreen):
        def message(self, texte: str) -> None:
            self.showMessage(texte, Qt.AlignBottom | Qt.AlignHCenter, QColor(theme_courant()["navigation_texte"]))

    ecran = Ecran(_image_attente())
    ecran.show()
    ecran.message("Démarrage…")
    app_qt.processEvents()

    serveur = None
    try:
        application, p = _executer_avec_attente(app_qt, ecran, lambda signaler: preparer_serveur(dossier, signaler))
        serveur = ServeurLocal(application, p)
        ecran.message("Démarrage du serveur local sécurisé…")
        _executer_avec_attente(app_qt, ecran, lambda _s: serveur.demarrer())
        config.url_serveur = f"https://127.0.0.1:{p.port}"
        config.certificat_ca = str(p.tls_certificat.parent / "ac_demo.crt")
        ecran.close()
        return client.main(config, comptes_demo=comptes_demo())
    except Exception as exc:  # noqa: BLE001
        ecran.close()
        logging.getLogger("tpgis").exception("Echec de la demonstration")
        QMessageBox.critical(
            None,
            "Démonstration indisponible",
            f"La démonstration TPGIS n'a pas pu démarrer :\n{exc}\n\nJournal : {journal}",
        )
        return 1
    finally:
        if serveur is not None:
            serveur.arreter()


if __name__ == "__main__":
    sys.exit(main())
