"""Connexion, changement de mot de passe, enrolement MFA et reauthentification."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from tpgis.client.api_client.client import ClientAPI, ErreurAPI, ErreurReseau
from tpgis.client.widgets.communs import chemin_ressource


def _champ_secret(placeholder: str = "") -> QLineEdit:
    champ = QLineEdit()
    champ.setEchoMode(QLineEdit.Password)
    champ.setPlaceholderText(placeholder)
    return champ


class DialogueConnexion(QDialog):
    def __init__(self, api: ClientAPI, environnement: str = "", parent=None):
        super().__init__(parent)
        self.api = api
        self.resultat: dict | None = None
        self.setWindowTitle("TPGIS : connexion sécurisée")
        self.setMinimumWidth(430)
        couche = QVBoxLayout(self)
        couche.setContentsMargins(26, 22, 26, 20)
        entete = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(
            QPixmap(str(chemin_ressource("icons/embleme_sombre.svg"))).scaled(
                44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        entete.addWidget(logo)
        titres = QVBoxLayout()
        titre = QLabel("TCHAD POLICE & GENDARMERIE\nINFORMATION SYSTEM")
        titre.setObjectName("titrePage")
        titres.addWidget(titre)
        sous = QLabel("Accès réservé aux personnels habilités. Toute connexion est journalisée.")
        sous.setObjectName("sousTitrePage")
        sous.setWordWrap(True)
        titres.addWidget(sous)
        entete.addLayout(titres, 1)
        couche.addLayout(entete)
        if environnement and environnement != "production":
            bandeau = QLabel(f"Environnement : {environnement.upper()}. Données fictives uniquement.")
            bandeau.setObjectName("avertissement")
            couche.addWidget(bandeau)
        formulaire = QFormLayout()
        self.identifiant = QLineEdit()
        self.identifiant.setPlaceholderText("identifiant")
        self.mot_de_passe = _champ_secret()
        self.code_mfa = QLineEdit()
        self.code_mfa.setPlaceholderText("6 chiffres")
        self.code_mfa.setMaxLength(6)
        self.libelle_mfa = QLabel("Code de vérification")
        formulaire.addRow("Identifiant", self.identifiant)
        formulaire.addRow("Mot de passe", self.mot_de_passe)
        formulaire.addRow(self.libelle_mfa, self.code_mfa)
        self.libelle_mfa.hide()
        self.code_mfa.hide()
        couche.addLayout(formulaire)
        self.message = QLabel("")
        self.message.setObjectName("messageErreur")
        self.message.setWordWrap(True)
        couche.addWidget(self.message)
        self.serveur = QLabel(f"Serveur : {api.url}")
        self.serveur.setObjectName("sousTitrePage")
        couche.addWidget(self.serveur)
        boutons = QHBoxLayout()
        boutons.addStretch()
        annuler = QPushButton("Quitter")
        annuler.clicked.connect(self.reject)
        self.valider = QPushButton("Se connecter")
        self.valider.setObjectName("boutonPrincipal")
        self.valider.setDefault(True)
        self.valider.clicked.connect(self.connecter)
        boutons.addWidget(annuler)
        boutons.addWidget(self.valider)
        couche.addLayout(boutons)

    def connecter(self) -> None:
        self.message.setText("")
        if not self.identifiant.text().strip() or not self.mot_de_passe.text():
            self.message.setText("Saisissez votre identifiant et votre mot de passe.")
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
                self.message.setText("Saisissez le code à 6 chiffres de votre application d'authentification.")
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
        self.setWindowTitle("Changement du mot de passe")
        couche = QVBoxLayout(self)
        if obligatoire:
            info = QLabel("Votre mot de passe doit être changé avant de poursuivre.")
            info.setObjectName("avertissement")
            couche.addWidget(info)
        regles = QLabel(
            "Au moins 12 caractères, combinant trois types parmi : minuscules, majuscules, chiffres, "
            "caractères spéciaux. Ne doit pas contenir votre identifiant."
        )
        regles.setWordWrap(True)
        regles.setObjectName("sousTitrePage")
        couche.addWidget(regles)
        formulaire = QFormLayout()
        self.ancien, self.nouveau, self.confirmation = _champ_secret(), _champ_secret(), _champ_secret()
        formulaire.addRow("Mot de passe actuel", self.ancien)
        formulaire.addRow("Nouveau mot de passe", self.nouveau)
        formulaire.addRow("Confirmation", self.confirmation)
        couche.addLayout(formulaire)
        self.message = QLabel("")
        self.message.setObjectName("messageErreur")
        self.message.setWordWrap(True)
        couche.addWidget(self.message)
        bouton = QPushButton("Changer le mot de passe")
        bouton.setObjectName("boutonPrincipal")
        bouton.clicked.connect(self.valider)
        couche.addWidget(bouton)

    def valider(self) -> None:
        if self.nouveau.text() != self.confirmation.text():
            self.message.setText("La confirmation ne correspond pas au nouveau mot de passe.")
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
        self.setWindowTitle("Activation de l'authentification multifacteur")
        self.setMinimumWidth(480)
        couche = QVBoxLayout(self)
        info = QLabel(
            "Votre rôle impose l'authentification multifacteur.\n\n"
            "1. Ouvrez l'application d'authentification fournie par l'institution.\n"
            "2. Ajoutez un compte en saisissant la clé ci-dessous.\n"
            "3. Saisissez le code à 6 chiffres affiché pour confirmer."
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
        formulaire.addRow("Code de vérification", self.code)
        couche.addLayout(formulaire)
        self.message = QLabel("")
        self.message.setObjectName("messageErreur")
        couche.addWidget(self.message)
        bouton = QPushButton("Activer")
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
        self.setWindowTitle("Confirmation d'identité")
        couche = QVBoxLayout(self)
        couche.addWidget(QLabel("Cette opération sensible nécessite de confirmer votre identité."))
        formulaire = QFormLayout()
        self.mot_de_passe = _champ_secret()
        formulaire.addRow("Mot de passe", self.mot_de_passe)
        self.code = QLineEdit()
        self.code.setMaxLength(6)
        if mfa:
            formulaire.addRow("Code de vérification", self.code)
        couche.addLayout(formulaire)
        self.message = QLabel("")
        self.message.setObjectName("messageErreur")
        couche.addWidget(self.message)
        bouton = QPushButton("Confirmer")
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
