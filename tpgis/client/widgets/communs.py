"""Composants graphiques communs du client TPGIS."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QDate, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from tpgis.client.api_client.client import ErreurAPI
from tpgis.client.widgets.ressources import chemin_ressource  # noqa: F401  (reexport)


def fmt_date(valeur: Any) -> str:
    if not valeur:
        return ""
    if isinstance(valeur, str):
        try:
            valeur = (
                datetime.fromisoformat(valeur.replace("Z", "+00:00")) if "T" in valeur else date.fromisoformat(valeur)
            )
        except ValueError:
            return valeur
    if isinstance(valeur, datetime):
        return valeur.astimezone().strftime("%d/%m/%Y %H:%M")
    return valeur.strftime("%d/%m/%Y")


class TitrePage(QWidget):
    def __init__(self, titre: str, sous_titre: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        couche = QVBoxLayout(self)
        couche.setContentsMargins(0, 0, 0, 6)
        t = QLabel(titre)
        t.setObjectName("titrePage")
        couche.addWidget(t)
        if sous_titre:
            s = QLabel(sous_titre)
            s.setObjectName("sousTitrePage")
            s.setWordWrap(True)
            couche.addWidget(s)


class MentionFictive(QLabel):
    """Pastille signalant des chiffres fictifs (environnements de test et de demonstration)."""

    TEXTE = "Chiffres fictifs : données de démonstration"

    def __init__(self, texte: str | None = None, parent: QWidget | None = None):
        super().__init__(texte or self.TEXTE, parent)
        self.setObjectName("mentionFictive")
        self.setToolTip(
            "Environnement hors production : toutes les données et tous les chiffres affichés sont fictifs "
            "et générés pour la démonstration."
        )


Colonne = tuple[str, str, Callable[[Any, dict], str] | None]


class ModeleDictionnaires(QAbstractTableModel):
    def __init__(self, colonnes: list[Colonne], parent=None):
        super().__init__(parent)
        self.colonnes = colonnes
        self.lignes: list[dict] = []

    def definir(self, lignes: list[dict]) -> None:
        self.beginResetModel()
        self.lignes = list(lignes)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.lignes)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return len(self.colonnes)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        ligne = self.lignes[index.row()]
        cle, _, formateur = self.colonnes[index.column()]
        valeur = ligne.get(cle)
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            if formateur:
                return formateur(valeur, ligne)
            if isinstance(valeur, bool):
                return "Oui" if valeur else "Non"
            return "" if valeur is None else str(valeur)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.colonnes[section][1]
        return None


class TableauDonnees(QWidget):
    """Tableau pagine : les donnees sont chargees page par page depuis le serveur."""

    ligne_activee = Signal(dict)
    page_demandee = Signal(int)

    def __init__(self, colonnes: list[Colonne], pagine: bool = True, parent=None):
        super().__init__(parent)
        self.modele = ModeleDictionnaires(colonnes, self)
        self.vue = QTableView()
        self.vue.setModel(self.modele)
        self.vue.setAlternatingRowColors(True)
        self.vue.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.vue.setSelectionMode(QAbstractItemView.SingleSelection)
        self.vue.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.vue.verticalHeader().setVisible(False)
        self.vue.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.vue.horizontalHeader().setStretchLastSection(True)
        self.vue.doubleClicked.connect(lambda i: self.ligne_activee.emit(self.modele.lignes[i.row()]))
        self.page, self.taille, self.total = 1, 50, 0
        couche = QVBoxLayout(self)
        couche.setContentsMargins(0, 0, 0, 0)
        couche.addWidget(self.vue)
        self.etat = QLabel("")
        self.etat.setObjectName("sousTitrePage")
        barre = QHBoxLayout()
        barre.addWidget(self.etat)
        barre.addStretch()
        self.precedent = QPushButton("Page précédente")
        self.suivant = QPushButton("Page suivante")
        self.precedent.clicked.connect(lambda: self.page_demandee.emit(self.page - 1))
        self.suivant.clicked.connect(lambda: self.page_demandee.emit(self.page + 1))
        if pagine:
            barre.addWidget(self.precedent)
            barre.addWidget(self.suivant)
        couche.addLayout(barre)

    def definir_page(self, resultat: dict) -> None:
        self.page, self.taille, self.total = resultat["page"], resultat["taille"], resultat["total"]
        self.modele.definir(resultat["elements"])
        pages = max(1, -(-self.total // self.taille))
        self.etat.setText(f"Page {self.page} sur {pages}  ({self.total} élément{'s' if self.total > 1 else ''})")
        self.precedent.setEnabled(self.page > 1)
        self.suivant.setEnabled(self.page < pages)
        self.vue.resizeColumnsToContents()

    def definir_lignes(self, lignes: list[dict]) -> None:
        self.modele.definir(lignes)
        self.etat.setText(f"{len(lignes)} élément{'s' if len(lignes) > 1 else ''}")
        self.vue.resizeColumnsToContents()

    def selection(self) -> dict | None:
        indices = self.vue.selectionModel().selectedRows()
        return self.modele.lignes[indices[0].row()] if indices else None


class Choix(QComboBox):
    """Liste deroulante de couples (libelle, valeur)."""

    # Largeur minimale en caracteres : la liste peut retrecir pour tenir dans la fenetre
    # (sinon elle exige la largeur de son plus long libelle et deborde aux petites tailles).
    CARACTERES_MINIMUM = 12

    def __init__(self, options: dict | list, vide: str | None = None, parent=None):
        super().__init__(parent)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(self.CARACTERES_MINIMUM)
        self.remplir(options, vide)

    def remplir(self, options: dict | list, vide: str | None = None) -> None:
        self.clear()
        if vide is not None:
            self.addItem(vide, None)
        elements = options.items() if isinstance(options, dict) else options
        for valeur, texte in elements:
            self.addItem(texte, valeur)
            self.setItemData(self.count() - 1, texte, Qt.ToolTipRole)
        # La liste deroulante affiche toujours les libelles en entier.
        self.view().setMinimumWidth(self.view().sizeHintForColumn(0) + 24)

    def valeur(self):
        return self.currentData()

    def choisir(self, valeur) -> None:
        index = self.findData(valeur)
        if index >= 0:
            self.setCurrentIndex(index)


class ChampDate(QWidget):
    """Date facultative : la case permet de laisser l'information inconnue."""

    def __init__(self, texte_case: str = "Renseignée", parent=None):
        super().__init__(parent)
        couche = QHBoxLayout(self)
        couche.setContentsMargins(0, 0, 0, 0)
        self.connue = QCheckBox(texte_case)
        self.connue.setToolTip("Cochez pour renseigner la date ; laissez décoché si elle est inconnue.")
        self.date = QDateEdit()
        self.date.setMinimumWidth(118)
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.date.setMaximumDate(QDate.currentDate())
        self.date.setDate(QDate.currentDate())
        self.date.setEnabled(False)
        self.connue.toggled.connect(self.date.setEnabled)
        couche.addWidget(self.connue)
        couche.addWidget(self.date, 1)

    def valeur(self) -> str | None:
        return self.date.date().toString("yyyy-MM-dd") if self.connue.isChecked() else None

    def definir(self, valeur: str | None) -> None:
        if valeur:
            self.date.setDate(QDate.fromString(valeur[:10], "yyyy-MM-dd"))
            self.connue.setChecked(True)
        else:
            self.connue.setChecked(False)


def afficher_erreur(parent: QWidget | None, exc: Exception, titre: str = "Opération impossible") -> None:
    texte = str(exc) if isinstance(exc, ErreurAPI) else f"Erreur inattendue : {exc}"
    QMessageBox.warning(parent, titre, texte)


def confirmer(parent: QWidget | None, titre: str, message: str) -> bool:
    boite = QMessageBox(QMessageBox.Question, titre, message, QMessageBox.Yes | QMessageBox.No, parent)
    boite.button(QMessageBox.Yes).setText("Confirmer")
    boite.button(QMessageBox.No).setText("Annuler")
    boite.setDefaultButton(QMessageBox.No)
    return boite.exec() == QMessageBox.Yes


def demander_motif(parent: QWidget | None, titre: str, consigne: str, minimum: int = 10) -> str | None:
    dialogue = QDialog(parent)
    dialogue.setWindowTitle(titre)
    couche = QVBoxLayout(dialogue)
    couche.addWidget(QLabel(consigne))
    texte = QPlainTextEdit()
    texte.setMinimumHeight(90)
    couche.addWidget(texte)
    erreur = QLabel("")
    erreur.setObjectName("messageErreur")
    couche.addWidget(erreur)
    boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    boutons.button(QDialogButtonBox.Ok).setText("Valider")
    boutons.button(QDialogButtonBox.Cancel).setText("Annuler")
    couche.addWidget(boutons)

    def _valider():
        if len(texte.toPlainText().strip()) < minimum:
            erreur.setText(f"Le motif doit comporter au moins {minimum} caractères.")
            return
        dialogue.accept()

    boutons.accepted.connect(_valider)
    boutons.rejected.connect(dialogue.reject)
    return texte.toPlainText().strip() if dialogue.exec() == QDialog.Accepted else None


def demander_finalite(parent: QWidget | None, finalites: list[str]) -> str | None:
    """La finalite est obligatoire avant toute consultation nominative ou recherche sensible."""
    choix, ok = QInputDialog.getItem(
        parent,
        "Finalité de la consultation",
        "Déclarez la finalité de cette consultation.\nElle est enregistrée dans le journal d'audit.",
        finalites,
        0,
        True,
    )
    choix = (choix or "").strip()
    return choix if ok and len(choix) >= 5 else None


class FormulaireDialogue(QDialog):
    """Dialogue de formulaire avec validation et message d'erreur integre."""

    def __init__(self, titre: str, parent=None, largeur: int = 560):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.setMinimumWidth(largeur)
        self.couche = QVBoxLayout(self)
        self.formulaire = QFormLayout()
        self.formulaire.setLabelAlignment(Qt.AlignRight)
        self.couche.addLayout(self.formulaire)
        self.erreur = QLabel("")
        self.erreur.setObjectName("messageErreur")
        self.erreur.setWordWrap(True)
        self.couche.addWidget(self.erreur)
        self.boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.boutons.button(QDialogButtonBox.Ok).setText("Enregistrer")
        self.boutons.button(QDialogButtonBox.Ok).setObjectName("boutonPrincipal")
        self.boutons.button(QDialogButtonBox.Cancel).setText("Annuler")
        self.boutons.accepted.connect(self._soumettre)
        self.boutons.rejected.connect(self.reject)
        self.couche.addWidget(self.boutons)
        self.resultat: Any = None
        self.action: Callable[[], Any] | None = None

    def ajouter(self, libelle: str, champ: QWidget, obligatoire: bool = False) -> QWidget:
        if obligatoire and isinstance(champ, QLineEdit):
            champ.setProperty("obligatoire", True)
        self.formulaire.addRow(f"{libelle}{' *' if obligatoire else ''}", champ)
        return champ

    def _soumettre(self) -> None:
        if self.action is None:
            self.accept()
            return
        try:
            self.resultat = self.action()
        except ErreurAPI as exc:
            self.erreur.setText(str(exc))
            return
        except ValueError as exc:
            self.erreur.setText(str(exc))
            return
        self.accept()


def texte_ou_none(champ: QLineEdit | QPlainTextEdit) -> str | None:
    valeur = champ.toPlainText() if isinstance(champ, QPlainTextEdit) else champ.text()
    valeur = valeur.strip()
    return valeur or None
