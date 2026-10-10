"""Fenetre principale : bandeau, navigation laterale et pages selon les droits."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from tpgis.client.api_client.client import ErreurAPI
from tpgis.client.widgets.communs import chemin_ressource, icone
from tpgis.client.windows.administration import PageAudit, PageParametres, PageUnites, PageUtilisateurs
from tpgis.client.windows.analyse import PageCartographie, PageRapports, PageTableauDeBord
from tpgis.client.windows.base import SessionClient
from tpgis.client.windows.faits_dossiers import PageDossiers, PageFaits
from tpgis.client.windows.personnes import PagePersonnes
from tpgis.client.windows.plaintes import PagePlaintes
from tpgis.client.windows.recherche import PageDocuments, PageRecherche

# (libelle, icone, classe, permissions dont l'une suffit ; None : toujours visible)
MODULES = [
    ("Tableau de bord", "tableau", PageTableauDeBord, None),
    ("Plaintes", "plainte", PagePlaintes, ["plainte.lire"]),
    ("Infractions et faits", "fait", PageFaits, ["fait.lire"]),
    ("Personnes", "personne", PagePersonnes, ["personne.lire"]),
    ("Dossiers et procédures", "dossier", PageDossiers, ["dossier.lire"]),
    ("Unités et commissariats", "unite", PageUnites, ["unite.lire"]),
    ("Recherche et vérification", "recherche", PageRecherche, ["recherche.effectuer"]),
    ("Pièces et documents", "documents", PageDocuments, ["document.lire"]),
    ("Cartographie du Tchad", "carte", PageCartographie, ["carte.lire"]),
    ("Rapports et statistiques", "rapports", PageRapports, ["statistiques.lire"]),
    ("Utilisateurs et habilitations", "utilisateurs", PageUtilisateurs, ["utilisateur.lire", "role.gerer"]),
    ("Journal d'audit", "audit", PageAudit, ["audit.lire"]),
    ("Paramètres et administration", "parametres", PageParametres, None),
]


class FenetrePrincipale(QMainWindow):
    deconnexion_demandee = Signal()

    def __init__(self, session: SessionClient, config=None):
        super().__init__()
        self.session = session
        self.config = config
        self.setWindowTitle("TPGIS : Tchad Police & Gendarmerie Information System")
        self.setMinimumSize(1100, 680)
        central = QWidget()
        couche = QVBoxLayout(central)
        couche.setContentsMargins(0, 0, 0, 0)
        couche.setSpacing(0)
        couche.addWidget(self._bandeau())
        corps = QHBoxLayout()
        corps.setSpacing(0)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(272)
        self.navigation.setIconSize(QSize(18, 18))
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pages = QStackedWidget()
        corps.addWidget(self.navigation)
        corps.addWidget(self.pages, 1)
        couche.addLayout(corps, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self._construire_modules()
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        # Verification periodique de la session (revocation, expiration).
        self.minuterie = QTimer(self)
        self.minuterie.timeout.connect(self._verifier_session)
        self.minuterie.start(60_000)
        self.statusBar().showMessage(f"Connecté au serveur {session.api.url}  |  Toutes les actions sont journalisées.")

    def _bandeau(self) -> QWidget:
        bandeau = QWidget()
        bandeau.setObjectName("bandeau")
        h = QHBoxLayout(bandeau)
        h.setContentsMargins(16, 6, 16, 6)
        logo = QLabel()
        logo.setPixmap(
            QPixmap(str(chemin_ressource("icons/embleme.svg"))).scaled(
                34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        h.addWidget(logo)
        titres = QVBoxLayout()
        titres.setSpacing(0)
        t = QLabel("TPGIS")
        t.setObjectName("titreApplication")
        s = QLabel("Police nationale et Gendarmerie nationale du Tchad")
        s.setObjectName("sousTitreApplication")
        titres.addWidget(t)
        titres.addWidget(s)
        h.addLayout(titres)
        h.addStretch()
        m = self.session.moi
        info = QLabel(f"{m.get('grade') or ''} {m['prenoms']} {m['nom']}  |  {m['role']}  |  {m['unite_nom']}")
        info.setObjectName("infoUtilisateur")
        h.addWidget(info)
        bouton = QPushButton("Se déconnecter")
        bouton.clicked.connect(self.deconnecter)
        h.addWidget(bouton)
        return bandeau

    def _construire_modules(self) -> None:
        options = {}
        if self.config is not None and getattr(self.config, "url_tuiles", None):
            options = {"url_tuiles": self.config.url_tuiles, "attribution": self.config.attribution_tuiles}
        for libelle, nom_icone, classe, permissions in MODULES:
            if permissions is not None and not self.session.a(*permissions):
                continue
            page = classe(self.session, **(options if classe is PageCartographie else {}))
            self.pages.addWidget(page)
            item = QListWidgetItem(icone(nom_icone), libelle)
            self.navigation.addItem(item)

    def _verifier_session(self) -> None:
        try:
            self.session.api.get("/auth/moi")
        except ErreurAPI as exc:
            if exc.statut == 401:
                self.minuterie.stop()
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(self, "Session terminée", str(exc))
                self.deconnexion_demandee.emit()
            else:
                self.statusBar().showMessage(f"Serveur indisponible : {exc.message}")

    def deconnecter(self) -> None:
        self.minuterie.stop()
        self.session.api.deconnecter()
        self.deconnexion_demandee.emit()
