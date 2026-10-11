"""Fenetre principale : bandeau, navigation laterale et pages selon les droits."""

from __future__ import annotations

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
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
from tpgis.client.theme import appliquer_theme, icone, identite, notificateur, theme_courant
from tpgis.client.theme.bigarre import LisereBigarre
from tpgis.client.theme.jetons import DIMENSIONS
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
        self.setWindowTitle(identite().titre_fenetre)
        self.setMinimumSize(1100, 680)
        central = QWidget()
        couche = QVBoxLayout(central)
        couche.setContentsMargins(0, 0, 0, 0)
        couche.setSpacing(0)
        couche.addWidget(self._bandeau())
        couche.addWidget(LisereBigarre(DIMENSIONS["hauteur_lisere"]))
        corps = QHBoxLayout()
        corps.setSpacing(0)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(DIMENSIONS["largeur_navigation"])
        cote = DIMENSIONS["icone_navigation"]
        self.navigation.setIconSize(QSize(cote, cote))
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
        if session.donnees_fictives:
            mention = QLabel(f"Environnement {session.environnement.upper()} : données et chiffres fictifs")
            mention.setObjectName("mentionFictive")
            self.statusBar().addPermanentWidget(mention)
        notificateur.theme_change.connect(self._theme_change)

    def _bandeau(self) -> QWidget:
        bandeau = QWidget()
        bandeau.setObjectName("bandeau")
        h = QHBoxLayout(bandeau)
        h.setContentsMargins(16, 6, 16, 6)
        logo = QLabel()
        logo.setPixmap(identite().pixmap_logo(38))
        logo.setAccessibleName(f"Logo {identite().nom}")
        h.addWidget(logo)
        h.addSpacing(6)
        titres = QVBoxLayout()
        titres.setSpacing(0)
        t = QLabel(identite().nom)
        t.setObjectName("titreApplication")
        s = QLabel(identite().sous_titre)
        s.setObjectName("sousTitreApplication")
        titres.addWidget(t)
        titres.addWidget(s)
        h.addLayout(titres)
        h.addStretch()
        m = self.session.moi
        info = QLabel(f"{m.get('grade') or ''} {m['prenoms']} {m['nom']}  |  {m['role']}  |  {m['unite_nom']}")
        info.setObjectName("infoUtilisateur")
        h.addWidget(info)
        self.bouton_theme = QPushButton()
        self.bouton_theme.clicked.connect(self.basculer_theme)
        h.addWidget(self.bouton_theme)
        self.bouton_deconnexion = QPushButton("Se déconnecter")
        self.bouton_deconnexion.clicked.connect(self.deconnecter)
        h.addWidget(self.bouton_deconnexion)
        self._icones_bandeau()
        return bandeau

    def _icones_bandeau(self) -> None:
        sombre = theme_courant().sombre
        self.bouton_theme.setText("Affichage clair" if sombre else "Affichage sombre")
        self.bouton_theme.setToolTip("Basculer entre l'affichage clair (par défaut) et l'affichage sombre")
        self.bouton_theme.setIcon(icone("theme_clair" if sombre else "theme_sombre", "bandeau_texte", 16))
        self.bouton_deconnexion.setIcon(icone("deconnexion", "bandeau_texte", 16))

    def basculer_theme(self) -> None:
        nom = "clair" if theme_courant().sombre else "sombre"
        appliquer_theme(QApplication.instance(), nom)
        QSettings("TPGIS", "client").setValue("affichage/theme", nom)

    def _theme_change(self, _theme) -> None:
        self._icones_bandeau()
        for i in range(self.navigation.count()):
            item = self.navigation.item(i)
            item.setIcon(icone(item.data(Qt.UserRole)))

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
            item.setData(Qt.UserRole, nom_icone)
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
