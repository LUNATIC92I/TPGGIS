"""Tableau de bord, cartographie et rapports statistiques (donnees agregees uniquement)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tpgis.client.api_client.client import ErreurAPI
from tpgis.client.map.carte import CarteTchad
from tpgis.client.widgets.communs import Choix, TableauDonnees, afficher_erreur
from tpgis.client.widgets.graphiques import GraphiqueBarres, GraphiqueColonnes
from tpgis.client.windows.base import Page
from tpgis.client.windows.connexion import avec_reauthentification


class CarteIndicateur(QFrame):
    def __init__(self, libelle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("carteIndicateur")
        couche = QVBoxLayout(self)
        couche.setContentsMargins(14, 10, 14, 10)
        self.valeur = QLabel("…")
        self.valeur.setObjectName("valeurIndicateur")
        texte = QLabel(libelle)
        texte.setObjectName("libelleIndicateur")
        texte.setWordWrap(True)
        couche.addWidget(self.valeur)
        couche.addWidget(texte)


class Filtres(QWidget):
    """Periode, unite et categorie de faits."""

    def __init__(self, session, rappel, parent=None, periode_defaut_jours: int = 365):
        super().__init__(parent)
        couche = QHBoxLayout(self)
        couche.setContentsMargins(0, 0, 0, 0)
        self.du, self.au = QDateEdit(), QDateEdit()
        for champ in (self.du, self.au):
            champ.setCalendarPopup(True)
            champ.setDisplayFormat("dd/MM/yyyy")
        self.au.setDate(QDate.currentDate())
        self.du.setDate(QDate.currentDate().addDays(-periode_defaut_jours))
        self.unite = Choix({}, "Toutes les unités du périmètre")
        self.categorie = Choix({}, "Toutes les catégories")
        for liste in (self.unite, self.categorie):
            liste.setMinimumContentsLength(8)
        try:
            self.unite.remplir({u["id"]: u["nom"] for u in session.unites()}, "Toutes les unités du périmètre")
            self.categorie.remplir({c["id"]: c["libelle"] for c in session.categories()}, "Toutes les catégories")
        except ErreurAPI:  # filtres facultatifs : la page reste utilisable sans eux
            self.unite.setEnabled(False)
        appliquer = QPushButton("Appliquer")
        appliquer.setObjectName("boutonPrincipal")
        appliquer.clicked.connect(rappel)
        for libelle, champ in (("Du", self.du), ("au", self.au)):
            couche.addWidget(QLabel(libelle))
            couche.addWidget(champ)
        couche.addWidget(self.unite, 1)
        couche.addWidget(self.categorie, 1)
        couche.addWidget(appliquer)

    def parametres(self) -> dict:
        return {
            "du": self.du.date().toString("yyyy-MM-dd"),
            "au": self.au.date().toString("yyyy-MM-dd"),
            "unite_id": self.unite.valeur(),
            "categorie_id": self.categorie.valeur(),
        }


class PageTableauDeBord(Page):
    affiche_chiffres = True
    titre = "Tableau de bord"
    sous_titre = "Indicateurs agrégés de votre périmètre, calculés à partir des données enregistrées."

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        if not session.a("statistiques.lire", "carte.lire"):
            message = QLabel(
                f"Bienvenue {session.moi['prenoms']} {session.moi['nom']}.\n\n"
                f"Rôle : {session.moi['role']}\nUnité : {session.moi['unite_nom']}\n\n"
                "Votre profil ne comporte pas l'accès aux statistiques. Utilisez le menu latéral "
                "pour accéder aux fonctions autorisées."
            )
            message.setObjectName("panneau")
            message.setWordWrap(True)
            message.setAlignment(Qt.AlignTop)
            message.setMargin(16)
            self.couche.addWidget(message)
            self.couche.addStretch()
            return
        self.filtres = Filtres(session, self.charger)
        self.couche.addWidget(self.filtres)
        grille = QGridLayout()
        self.indicateurs = {
            "plaintes_total": CarteIndicateur("Plaintes enregistrées sur la période"),
            "plaintes_en_attente": CarteIndicateur("Plaintes en attente de traitement"),
            "plaintes_en_attente_plus_30_jours": CarteIndicateur("En attente depuis plus de 30 jours"),
            "dossiers_en_cours": CarteIndicateur("Dossiers et procédures en cours"),
            "qualite": CarteIndicateur("Complétude moyenne des plaintes (%)"),
        }
        for i, carte in enumerate(self.indicateurs.values()):
            grille.addWidget(carte, 0, i)
        self.couche.addLayout(grille)
        corps = QHBoxLayout()
        self.carte = CarteTchad(mention_fictive=session.donnees_fictives) if session.a("carte.lire") else None
        if self.carte:
            corps.addWidget(self.carte, 3)
        colonne = QVBoxLayout()
        self.evolution = GraphiqueColonnes("Évolution mensuelle des plaintes")
        self.repartition = GraphiqueBarres("Répartition par catégorie de faits")
        colonne.addWidget(self.evolution)
        colonne.addWidget(self.repartition)
        corps.addLayout(colonne, 2)
        self.couche.addLayout(corps, 1)

    def charger(self) -> None:
        if not hasattr(self, "filtres"):
            return
        params = self.filtres.parametres()
        if self.session.a("statistiques.lire"):
            self.executer(lambda: self.api.get("/statistiques/tableau-de-bord", params), self._afficher)
        if self.carte is not None:
            self.executer(lambda: self.api.get("/carte/donnees", params), self.carte.definir_donnees)

    def _afficher(self, stats: dict) -> None:
        for cle, carte in self.indicateurs.items():
            if cle == "qualite":
                q = stats["qualite_donnees"]
                mesures = [
                    q["plaintes_avec_categorie_pct"],
                    q["plaintes_avec_date_faits_pct"],
                    q["plaintes_avec_province_pct"],
                    q["plaintes_avec_lieu_pct"],
                ]
                carte.valeur.setText(f"{sum(mesures) / len(mesures):.0f}")
            else:
                carte.valeur.setText(str(stats["indicateurs"][cle]))
        self.evolution.definir([(m["mois"][2:].replace("-", "/"), m["nombre"]) for m in stats["evolution_mensuelle"]])
        self.repartition.definir([(c["categorie"], c["nombre"]) for c in stats["par_categorie"]])


class PageCartographie(Page):
    affiche_chiffres = True
    titre = "Cartographie du Tchad"
    sous_titre = (
        "Indicateurs agrégés par province et implantation des unités. Aucune donnée nominative "
        "n'est représentée sur la carte."
    )

    def __init__(self, session, parent=None, url_tuiles: str | None = None, attribution: str = ""):
        super().__init__(session, parent)
        self.filtres = Filtres(session, self.charger)
        self.couche.addWidget(self.filtres)
        options = QHBoxLayout()
        self.indicateur = Choix(
            {
                "plaintes": "Plaintes enregistrées",
                "dossiers": "Dossiers en cours",
                "tendance": "Tendance par rapport à la période précédente",
            }
        )
        self.indicateur.currentIndexChanged.connect(
            lambda: self.carte.definir_donnees(self.carte.donnees, self.indicateur.valeur())
        )
        options.addWidget(QLabel("Indicateur"))
        options.addWidget(self.indicateur, 1)
        couches = QHBoxLayout()
        couches.addWidget(QLabel("Afficher"))
        self.carte = CarteTchad(
            url_tuiles=url_tuiles, attribution_tuiles=attribution, mention_fictive=session.donnees_fictives
        )
        for couche, libelle in (("unites", "Unités"), ("villes", "Villes"), ("etiquettes", "Noms des provinces")):
            case = QCheckBox(libelle)
            case.setChecked(True)
            case.toggled.connect(lambda v, c=couche: self.carte.afficher_couche(c, v))
            couches.addWidget(case)
        if url_tuiles:
            fond = QCheckBox("Fond de carte raster")
            fond.setChecked(True)
            fond.toggled.connect(lambda v: self.carte.afficher_couche("fond", v))
            couches.addWidget(fond)
        couches.addStretch()
        for texte, action in (
            ("+", lambda: self.carte.zoomer(1.4)),
            ("-", lambda: self.carte.zoomer(0.7)),
            ("Vue d'ensemble", self.carte.recentrer),
        ):
            b = QPushButton(texte)
            b.clicked.connect(action)
            options.addWidget(b)
        self.couche.addLayout(options)
        self.couche.addLayout(couches)
        corps = QHBoxLayout()
        corps.addWidget(self.carte, 3)
        self.tableau = TableauDonnees(
            [
                ("province", "Province", None),
                ("plaintes", "Plaintes", lambda v, ligne: "masqué" if ligne.get("plaintes_masquees") else str(v or 0)),
                ("tendance_pct", "Tendance", lambda v, ligne: "" if v is None else f"{v:+.1f} %"),
                ("dossiers_en_cours", "Dossiers en cours", None),
            ],
            pagine=False,
        )
        corps.addWidget(self.tableau, 2)
        self.couche.addLayout(corps, 1)

    def charger(self) -> None:
        self.executer(lambda: self.api.get("/carte/donnees", self.filtres.parametres()), self._afficher)

    def _afficher(self, donnees: dict) -> None:
        self.carte.definir_donnees(donnees, self.indicateur.valeur())
        noms = {code: p.nom for code, p in self.carte.provinces.items()}
        lignes = [
            {**p, "province": noms.get(p["province_code"], p["province_code"] or "Non renseignée")}
            for p in donnees["provinces"]
        ]
        self.tableau.definir_lignes(sorted(lignes, key=lambda x: -(x["plaintes"] or 0)))


class PageRapports(Page):
    affiche_chiffres = True
    titre = "Rapports et statistiques"
    sous_titre = (
        "Statistiques agrégées. Les exports CSV et PDF sont réservés aux utilisateurs autorisés, "
        "exigent une confirmation d'identité et sont tracés dans le journal d'audit."
    )

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self.filtres = Filtres(session, self.charger)
        self.couche.addWidget(self.filtres)
        actions = QHBoxLayout()
        actions.addStretch()
        self.export_csv = QPushButton("Exporter en CSV")
        self.export_pdf = QPushButton("Générer le rapport PDF")
        self.export_csv.clicked.connect(lambda: self.exporter("/statistiques/export.csv"))
        self.export_pdf.clicked.connect(lambda: self.exporter("/statistiques/rapport.pdf"))
        for b in (self.export_csv, self.export_pdf):
            b.setEnabled(session.a("export.realiser"))
            actions.addWidget(b)
        self.couche.addLayout(actions)
        grille = QGridLayout()
        self.statuts = TableauDonnees([("libelle", "Statut", None), ("nombre", "Plaintes", None)], pagine=False)
        self.unites = TableauDonnees(
            [("unite", "Unité", None), ("plaintes", "Plaintes", None), ("en_attente", "En attente", None)], pagine=False
        )
        self.qualite = TableauDonnees(
            [("mesure", "Indicateur de qualité", None), ("valeur", "Taux (%)", None)], pagine=False
        )
        self.categories = GraphiqueBarres("Répartition par catégorie", maximum_lignes=12)
        grille.addWidget(self.statuts, 0, 0)
        grille.addWidget(self.qualite, 0, 1)
        grille.addWidget(self.unites, 1, 0)
        grille.addWidget(self.categories, 1, 1)
        self.couche.addLayout(grille, 1)

    def charger(self) -> None:
        self.executer(lambda: self.api.get("/statistiques/tableau-de-bord", self.filtres.parametres()), self._afficher)

    def _afficher(self, s: dict) -> None:
        from tpgis.client.libelles import STATUT_PLAINTE

        self.statuts.definir_lignes(
            [{"libelle": STATUT_PLAINTE.get(k, k), "nombre": v} for k, v in s["par_statut"].items()]
        )
        self.unites.definir_lignes(s["activite_unites"])
        libelles = {
            "plaintes_avec_categorie_pct": "Plaintes catégorisées",
            "plaintes_avec_date_faits_pct": "Plaintes avec date des faits",
            "plaintes_avec_province_pct": "Plaintes localisées (province)",
            "plaintes_avec_lieu_pct": "Plaintes avec lieu des faits",
            "personnes_avec_date_naissance_pct": "Personnes avec date de naissance",
            "personnes_avec_document_pct": "Personnes avec document d'identité",
            "faits_verifies_pct": "Faits vérifiés",
        }
        self.qualite.definir_lignes(
            [{"mesure": libelles.get(k, k), "valeur": v} for k, v in s["qualite_donnees"].items()]
        )
        self.categories.definir([(c["categorie"], c["nombre"]) for c in s["par_categorie"]])

    def exporter(self, chemin: str) -> None:
        try:
            resultat = avec_reauthentification(
                self, self.session, lambda: self.api.telecharger(chemin, self.filtres.parametres())
            )
        except Exception as exc:  # noqa: BLE001
            afficher_erreur(self, exc)
            return
        if resultat is None:
            return
        nom, contenu = resultat
        destination, _ = QFileDialog.getSaveFileName(self, "Enregistrer l'export", str(Path.home() / nom))
        if destination:
            Path(destination).write_bytes(contenu)
