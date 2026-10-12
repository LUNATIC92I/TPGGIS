"""Connexion, changement de mot de passe, enrolement MFA et reauthentification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tpgis.client.api_client.client import ClientAPI, ErreurAPI, ErreurReseau
from tpgis.client.theme import identite
from tpgis.client.theme.bigarre import PanneauBigarre
from tpgis.shared.i18n import LANGUES, langue_courante, tr


@dataclass(frozen=True)
class CompteDemo:
    """Compte fictif propose par l'executable de demonstration (jamais en production)."""

    identifiant: str
    libelle: str
    mot_de_passe: str
    code_mfa: Callable[[], str] | None = None


def _champ_secret(placeholder: str = "") -> QLineEdit:
    champ = QLineEdit()
    champ.setEchoMode(QLineEdit.Password)
    champ.setPlaceholderText(placeholder)
    return champ


class DialogueConnexion(QDialog):
    """Ecran de connexion : panneau decoratif bigarre a gauche, formulaire sur fond uni a droite."""

    def __init__(
        self,
        api: ClientAPI,
        environnement: str = "",
        parent=None,
        comptes_demo: list[CompteDemo] | None = None,
    ):
        super().__init__(parent)
        self.api = api
        self.resultat: dict | None = None
        self.comptes_demo = comptes_demo if environnement == "demonstration" else None
        ident = identite()
        self.setWindowTitle(tr("{nom} : connexion sécurisée", nom=ident.nom))
        self.setMinimumSize(780, 460)
        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)

        # Panneau decoratif : uniquement le logo et le nom du logiciel, sur la zone unie.
        decor = PanneauBigarre()
        decor.setFixedWidth(300)
        d = QVBoxLayout(decor)
        d.setContentsMargins(28, 28, 28, 28)
        d.addStretch(3)
        logo = QLabel()
        logo.setPixmap(ident.pixmap_logo(64))
        logo.setAccessibleName(tr("Logo {nom}", nom=ident.nom))
        d.addWidget(logo)
        nom = QLabel(ident.nom)
        nom.setObjectName("nomDecor")
        complet = QLabel(tr(ident.nom_complet))
        complet.setObjectName("texteDecor")
        complet.setWordWrap(True)
        sous = QLabel(tr(ident.sous_titre))
        sous.setObjectName("texteDecorSecondaire")
        sous.setWordWrap(True)
        for w in (nom, complet, sous):
            d.addWidget(w)
        d.addStretch(1)
        racine.addWidget(decor)

        panneau = QWidget()
        panneau.setObjectName("panneauConnexion")
        panneau.setAttribute(Qt.WA_StyledBackground, True)
        couche = QVBoxLayout(panneau)
        couche.setContentsMargins(36, 32, 36, 26)
        couche.setSpacing(10)
        titre = QLabel(tr("Connexion sécurisée"))
        titre.setObjectName("titreConnexion")
        ligne_titre = QHBoxLayout()
        ligne_titre.addWidget(titre, 1)
        # Choix de la langue, visible avant toute connexion (Langue / Language).
        self.choix_langue = QComboBox()
        self.choix_langue.setAccessibleName("Langue / Language")
        self.choix_langue.setToolTip("Langue de l'interface / Interface language")
        for code, nom_langue in LANGUES.items():
            self.choix_langue.addItem(nom_langue, code)
        self.choix_langue.setCurrentIndex(self.choix_langue.findData(langue_courante()))
        self.choix_langue.currentIndexChanged.connect(self._changer_langue)
        ligne_titre.addWidget(self.choix_langue, 0, Qt.AlignTop)
        couche.addLayout(ligne_titre)
        consigne = QLabel(tr("Accès réservé aux personnels habilités. Toute connexion est journalisée."))
        consigne.setObjectName("sousTitrePage")
        consigne.setWordWrap(True)
        couche.addWidget(consigne)
        if environnement and environnement != "production":
            bandeau = QLabel(tr("Environnement : {upper}. Données fictives uniquement.", upper=environnement.upper()))
            bandeau.setObjectName("avertissement")
            bandeau.setWordWrap(True)
            couche.addWidget(bandeau)
        couche.addSpacing(6)
        formulaire = QFormLayout()
        formulaire.setVerticalSpacing(10)
        self.identifiant = QLineEdit()
        self.identifiant.setPlaceholderText(tr("identifiant"))
        self.mot_de_passe = _champ_secret()
        self.code_mfa = QLineEdit()
        self.code_mfa.setPlaceholderText(tr("6 chiffres"))
        self.code_mfa.setMaxLength(6)
        self.libelle_mfa = QLabel(tr("Code de vérification"))
        formulaire.addRow(tr("Identifiant"), self.identifiant)
        formulaire.addRow(tr("Mot de passe"), self.mot_de_passe)
        formulaire.addRow(self.libelle_mfa, self.code_mfa)
        self.libelle_mfa.hide()
        self.code_mfa.hide()
        couche.addLayout(formulaire)
        if self.comptes_demo:
            couche.addLayout(self._aide_demonstration())
        self.message = QLabel("")
        self.message.setObjectName("messageErreur")
        self.message.setWordWrap(True)
        couche.addWidget(self.message)
        couche.addStretch()
        self.serveur = QLabel(tr("Serveur : {url}", url=api.url))
        self.serveur.setObjectName("sousTitrePage")
        couche.addWidget(self.serveur)
        boutons = QHBoxLayout()
        boutons.addStretch()
        annuler = QPushButton(tr("Quitter"))
        annuler.clicked.connect(self.reject)
        self.valider = QPushButton(tr("Se connecter"))
        self.valider.setObjectName("boutonPrincipal")
        self.valider.setDefault(True)
        self.valider.clicked.connect(self.connecter)
        boutons.addWidget(annuler)
        boutons.addWidget(self.valider)
        couche.addLayout(boutons)
        racine.addWidget(panneau, 1)

    # Code de retour : la fenetre doit etre reconstruite dans la nouvelle langue.
    CHANGEMENT_LANGUE = 2

    def _changer_langue(self) -> None:
        from tpgis.client.langue import enregistrer_langue

        enregistrer_langue(self.choix_langue.currentData())
        self.done(self.CHANGEMENT_LANGUE)

    def _aide_demonstration(self) -> QHBoxLayout:
        """Executable de demonstration uniquement : remplit un compte fictif et son code MFA courant."""
        ligne = QHBoxLayout()
        ligne.addWidget(QLabel(tr("Compte fictif")))
        self.choix_compte = QComboBox()
        for compte in self.comptes_demo:
            self.choix_compte.addItem(compte.libelle, compte)
        ligne.addWidget(self.choix_compte, 1)
        remplir = QPushButton(tr("Remplir"))
        remplir.setToolTip(
            tr("Renseigne l'identifiant, le mot de passe et, si nécessaire, le code MFA du compte fictif")
        )
        remplir.clicked.connect(self.remplir_compte_demo)
        ligne.addWidget(remplir)
        return ligne

    def remplir_compte_demo(self) -> None:
        compte: CompteDemo = self.choix_compte.currentData()
        self.identifiant.setText(compte.identifiant)
        self.mot_de_passe.setText(compte.mot_de_passe)
        code = compte.code_mfa() if compte.code_mfa else ""
        self.code_mfa.setText(code)
        self.libelle_mfa.setVisible(bool(code))
        self.code_mfa.setVisible(bool(code))
        self.valider.setFocus()

    def connecter(self) -> None:
        self.message.setText("")
        if not self.identifiant.text().strip() or not self.mot_de_passe.text():
            self.message.setText(tr("Saisissez votre identifiant et votre mot de passe."))
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.resultat = self.api.connecter(
                self.identifiant.text().strip(), self.mot_de_passe.text(), self.code_mfa.text().strip() or None
            )
        except ErreurReseau as exc:
            self.message.setText(str(exc))
            return
        except ErreurAPI as exc:
            if exc.code == "MFA_REQUISE":
                self.libelle_mfa.show()
                self.code_mfa.show()
                self.code_mfa.setFocus()
                self.message.setText(tr("Saisissez le code à 6 chiffres de votre application d'authentification."))
            else:
                self.message.setText(str(exc))
                self.code_mfa.clear()
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.mot_de_passe.clear()
        self.accept()


class DialogueChangementMotDePasse(QDialog):
    def __init__(self, api: ClientAPI, parent=None, obligatoire: bool = True):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle(tr("Changement du mot de passe"))
        couche = QVBoxLayout(self)
        if obligatoire:
            info = QLabel(tr("Votre mot de passe doit être changé avant de poursuivre."))
            info.setObjectName("avertissement")
            couche.addWidget(info)
        regles = QLabel(
            tr(
                "Au moins 12 caractères, combinant trois types parmi : minuscules, majuscules, chiffres, "
                "caractères spéciaux. Ne doit pas contenir votre identifiant."
            )
        )
        regles.setWordWrap(True)
        regles.setObjectName("sousTitrePage")
        couche.addWidget(regles)
        formulaire = QFormLayout()
        self.ancien, self.nouveau, self.confirmation = _champ_secret(), _champ_secret(), _champ_secret()
        formulaire.addRow(tr("Mot de passe actuel"), self.ancien)
        formulaire.addRow(tr("Nouveau mot de passe"), self.nouveau)
        formulaire.addRow(tr("Confirmation"), self.confirmation)
        couche.addLayout(formulaire)
        self.message = QLabel("")
        self.message.setObjectName("messageErreur")
        self.message.setWordWrap(True)
        couche.addWidget(self.message)
        bouton = QPushButton(tr("Changer le mot de passe"))
        bouton.setObjectName("boutonPrincipal")
        bouton.clicked.connect(self.valider)
        couche.addWidget(bouton)

    def valider(self) -> None:
        if self.nouveau.text() != self.confirmation.text():
            self.message.setText(tr("La confirmation ne correspond pas au nouveau mot de passe."))
            return
        try:
            self.api.post(
                "/auth/mot-de-passe",
                {"ancien_mot_de_passe": self.ancien.text(), "nouveau_mot_de_passe": self.nouveau.text()},
            )
        except ErreurAPI as exc:
            self.message.setText(str(exc))
            return
        self.accept()


class DialogueEnrolementMFA(QDialog):
    """Enrolement d'une application d'authentification (TOTP, RFC 6238)."""

    def __init__(self, api: ClientAPI, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle(tr("Activation de l'authentification multifacteur"))
        self.setMinimumWidth(480)
        couche = QVBoxLayout(self)
        info = QLabel(
            tr(
                "Votre rôle impose l'authentification multifacteur.\n\n"
                "1. Ouvrez l'application d'authentification fournie par l'institution.\n"
                "2. Ajoutez un compte en saisissant la clé ci-dessous.\n"
                "3. Saisissez le code à 6 chiffres affiché pour confirmer."
            )
        )
        info.setWordWrap(True)
        couche.addWidget(info)
        self.cle = QLineEdit()
        self.cle.setReadOnly(True)
        couche.addWidget(self.cle)
        self.uri = QLabel("")
        self.uri.setWordWrap(True)
        self.uri.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.uri.setObjectName("sousTitrePage")
        couche.addWidget(self.uri)
        formulaire = QFormLayout()
        self.code = QLineEdit()
        self.code.setMaxLength(6)
        formulaire.addRow(tr("Code de vérification"), self.code)
        couche.addLayout(formulaire)
        self.message = QLabel("")
        self.message.setObjectName("messageErreur")
        couche.addWidget(self.message)
        bouton = QPushButton(tr("Activer"))
        bouton.setObjectName("boutonPrincipal")
        bouton.clicked.connect(self.activer)
        couche.addWidget(bouton)
        try:
            donnees = self.api.post("/auth/mfa/preparation")
            self.cle.setText(donnees["secret"])
            self.uri.setText(donnees["uri"])
        except ErreurAPI as exc:
            self.message.setText(str(exc))

    def activer(self) -> None:
        try:
            self.api.post("/auth/mfa/activation", {"code_mfa": self.code.text().strip()})
        except ErreurAPI as exc:
            self.message.setText(str(exc))
            return
        self.accept()


class DialogueReauthentification(QDialog):
    """Confirmation d'identite avant une operation sensible."""

    def __init__(self, api: ClientAPI, mfa: bool, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle(tr("Confirmation d'identité"))
        couche = QVBoxLayout(self)
        couche.addWidget(QLabel(tr("Cette opération sensible nécessite de confirmer votre identité.")))
        formulaire = QFormLayout()
        self.mot_de_passe = _champ_secret()
        formulaire.addRow(tr("Mot de passe"), self.mot_de_passe)
        self.code = QLineEdit()
        self.code.setMaxLength(6)
        if mfa:
            formulaire.addRow(tr("Code de vérification"), self.code)
        couche.addLayout(formulaire)
        self.message = QLabel("")
        self.message.setObjectName("messageErreur")
        couche.addWidget(self.message)
        bouton = QPushButton(tr("Confirmer"))
        bouton.setObjectName("boutonPrincipal")
        bouton.clicked.connect(self.valider)
        couche.addWidget(bouton)

    def valider(self) -> None:
        try:
            self.api.post(
                "/auth/reauthentification",
                {"mot_de_passe": self.mot_de_passe.text(), "code_mfa": self.code.text().strip() or None},
            )
        except ErreurAPI as exc:
            self.message.setText(str(exc))
            return
        self.accept()


def avec_reauthentification(parent, session, fonction):
    """Execute une operation sensible ; demande la reauthentification si requise."""
    try:
        return fonction()
    except ErreurAPI as exc:
        if exc.code != "REAUTHENTIFICATION_REQUISE":
            raise
    if DialogueReauthentification(session.api, session.moi.get("mfa_active", False), parent).exec() != QDialog.Accepted:
        return None
    return fonction()
