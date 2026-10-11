"""Recherche et verification autorisees ; acces aux pieces par numero."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from tpgis.client import libelles as L
from tpgis.client.api_client.client import ErreurAPI
from tpgis.client.widgets.communs import ChampDate, TableauDonnees, afficher_erreur, fmt_date
from tpgis.client.windows.base import Page
from tpgis.client.windows.faits_dossiers import DialogueDossier
from tpgis.client.windows.personnes import COLONNES_CANDIDATS, DialogueFichePersonne
from tpgis.client.windows.plaintes import DialoguePlainte, OngletPieces


class PageRecherche(Page):
    titre = "Recherche et vérification"
    sous_titre = (
        "Recherches réservées aux personnels habilités. Chaque recherche est associée à votre compte, "
        "à une finalité déclarée et à un identifiant de trace d'audit."
    )

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        boite = QGroupBox("Critères")
        f = QFormLayout(boite)
        self.finalite = QComboBox()
        self.finalite.setEditable(True)
        self.finalite.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.finalite.setMinimumContentsLength(16)
        self.numero_plainte, self.numero_dossier, self.numero_interne = QLineEdit(), QLineEdit(), QLineEdit()
        self.nom, self.prenoms, self.lieu, self.document = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.naissance = ChampDate()
        self.national = QCheckBox("Étendre au périmètre national (habilitation spécifique)")
        self.national.setEnabled(session.a("recherche.nationale"))
        f.addRow("Finalité déclarée *", self.finalite)
        f.addRow("Numéro de plainte", self.numero_plainte)
        f.addRow("Numéro de dossier", self.numero_dossier)
        f.addRow("Identifiant interne de personne", self.numero_interne)
        f.addRow("Nom", self.nom)
        f.addRow("Prénoms", self.prenoms)
        f.addRow("Date de naissance", self.naissance)
        f.addRow("Lieu de naissance", self.lieu)
        f.addRow("Référence de document", self.document)
        f.addRow("", self.national)
        bouton = QPushButton("Lancer la recherche")
        bouton.setObjectName("boutonPrincipal")
        bouton.clicked.connect(self.rechercher)
        f.addRow("", bouton)
        haut = QHBoxLayout()
        haut.addWidget(boite, 2)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setObjectName("avertissement")
        self.info.hide()
        haut.addWidget(self.info, 1)
        self.couche.addLayout(haut)
        self.onglets = QTabWidget()
        self.personnes = TableauDonnees(COLONNES_CANDIDATS, pagine=False)
        self.personnes.ligne_activee.connect(self.ouvrir_personne)
        self.plaintes = TableauDonnees(
            [
                ("numero", "Plainte", None),
                ("statut", "Statut", lambda v, _: L.libelle(L.STATUT_PLAINTE, v)),
                ("unite", "Unité", None),
                ("niveau", "Correspondance", None),
            ],
            pagine=False,
        )
        self.plaintes.ligne_activee.connect(lambda p: DialoguePlainte(self.session, p["id"], self).exec())
        self.dossiers = TableauDonnees(
            [
                ("numero", "Dossier", None),
                ("intitule", "Intitulé", None),
                ("statut", "Statut", None),
                ("niveau", "Correspondance", None),
            ],
            pagine=False,
        )
        self.dossiers.ligne_activee.connect(lambda d: DialogueDossier(self.session, d["id"], self).exec())
        self.onglets.addTab(self.personnes, "Personnes")
        self.onglets.addTab(self.plaintes, "Plaintes")
        self.onglets.addTab(self.dossiers, "Dossiers")
        self.couche.addWidget(self.onglets, 1)

    def charger(self) -> None:
        try:
            finalites = self.api.get("/parametres").get("recherche.finalites", [])
            if isinstance(finalites, dict):
                finalites = finalites.get("valeur", [])
        except ErreurAPI:
            finalites = []
        self.finalite.clear()
        self.finalite.addItems(finalites)

    def rechercher(self) -> None:
        finalite = self.finalite.currentText().strip()
        if len(finalite) < 5:
            self.info.setText("Déclarez la finalité de la recherche (5 caractères minimum).")
            self.info.show()
            return
        demande = {"finalite": finalite, "etendre_national": self.national.isChecked()}
        for cle, champ in (
            ("numero_plainte", self.numero_plainte),
            ("numero_dossier", self.numero_dossier),
            ("numero_interne", self.numero_interne),
            ("nom", self.nom),
            ("prenoms", self.prenoms),
            ("lieu_naissance", self.lieu),
            ("numero_document", self.document),
        ):
            if champ.text().strip():
                demande[cle] = champ.text().strip()
        if self.naissance.valeur():
            demande["date_naissance"] = self.naissance.valeur()
        self.finalite_courante = finalite
        self.executer(lambda: self.api.post("/recherche", demande), self._afficher)

    def _afficher(self, r: dict) -> None:
        res = r["resultats"]
        self.personnes.definir_lignes(res["personnes"])
        self.plaintes.definir_lignes(res["plaintes"])
        self.dossiers.definir_lignes(res["dossiers"])
        self.info.setText(
            f"{r['avertissement']}\n\nTrace d'audit : {r['trace_audit']}\nHorodatage : {fmt_date(r['horodatage'])}"
        )
        self.info.show()
        for i, t in enumerate((res["personnes"], res["plaintes"], res["dossiers"])):
            if t:
                self.onglets.setCurrentIndex(i)
                break

    def ouvrir_personne(self, personne: dict) -> None:
        DialogueFichePersonne(self.session, personne["id"], self.finalite_courante, self).exec()


class PageDocuments(Page):
    titre = "Pièces et documents"
    sous_titre = (
        "Les pièces sont analysées par l'antivirus, chiffrées et contrôlées par empreinte SHA-256. "
        "Elles ne sont accessibles qu'à travers le serveur, selon vos droits sur le dossier."
    )

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        barre = QHBoxLayout()
        self.type = QComboBox()
        self.type.addItem("Plainte", "plainte")
        self.type.addItem("Dossier", "dossier")
        self.numero = QLineEdit()
        self.numero.setPlaceholderText("Numéro exact (PL-... ou DO-...)")
        self.numero.returnPressed.connect(self.ouvrir)
        bouton = QPushButton("Afficher les pièces")
        bouton.setObjectName("boutonPrincipal")
        bouton.clicked.connect(self.ouvrir)
        barre.addWidget(self.type)
        barre.addWidget(self.numero, 1)
        barre.addWidget(bouton)
        self.couche.addLayout(barre)
        self.titre_parent = QLabel("")
        self.titre_parent.setObjectName("sousTitrePage")
        self.couche.addWidget(self.titre_parent)
        self.zone = QVBoxLayout()
        self.couche.addLayout(self.zone, 1)
        self.onglet = None

    def ouvrir(self) -> None:
        numero = self.numero.text().strip().upper()
        if not numero:
            return
        type_parent = self.type.currentData()
        try:
            elements = self.api.get(f"/{type_parent}s", {"numero": numero, "taille": 5})["elements"]
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        trouve = next((e for e in elements if e["numero"] == numero), None)
        if not trouve:
            self.titre_parent.setText("Aucun élément ne correspond à ce numéro dans votre périmètre.")
            return
        if self.onglet:
            self.onglet.setParent(None)
        self.onglet = OngletPieces(self.session, f"{type_parent}_id", trouve["id"], self)
        self.zone.addWidget(self.onglet)
        self.titre_parent.setText(f"Pièces de {'la plainte' if type_parent == 'plainte' else 'du dossier'} {numero}")
