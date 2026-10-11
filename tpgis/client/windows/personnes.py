"""Registre des personnes concernees, doublons, fusion et biometrie."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tpgis.client import libelles as L
from tpgis.client.api_client.client import ErreurAPI
from tpgis.client.widgets.communs import (
    ChampDate,
    Choix,
    FormulaireDialogue,
    TableauDonnees,
    afficher_erreur,
    confirmer,
    demander_motif,
    fmt_date,
    texte_ou_none,
)
from tpgis.client.windows.base import Page

COLONNES_PERSONNES = [
    ("numero_interne", "N° interne", None),
    ("nom", "Nom", None),
    ("prenoms", "Prénoms", None),
    ("date_naissance", "Naissance", lambda v, _: fmt_date(v)),
    ("lieu_naissance", "Lieu de naissance", None),
    ("statut_verification", "Identité", lambda v, _: L.libelle(L.VERIFICATION_IDENTITE, v)),
    ("unite_creation", "Unité d'enregistrement", None),
]

COLONNES_CANDIDATS = [
    (
        "niveau",
        "Correspondance",
        lambda v, ligne: f"{L.libelle(L.NIVEAU_CORRESPONDANCE, v)} ({ligne.get('score', '')})",
    ),
    ("numero_interne", "N° interne", None),
    ("nom", "Nom", None),
    ("prenoms", "Prénoms", None),
    ("date_naissance", "Naissance", lambda v, _: fmt_date(v)),
    ("attributs_concordants", "Attributs concordants", lambda v, _: ", ".join(v or [])),
    ("ambiguites", "Ambiguïtés", lambda v, _: " ; ".join(v or [])),
]


class DialogueDoublons(QDialog):
    """Presentation des fiches potentiellement identiques : decision humaine obligatoire."""

    UTILISER, CREER = 1, 2

    def __init__(self, candidats: list[dict], parent=None, creation: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Fiches potentiellement identiques")
        self.setMinimumSize(860, 360)
        self.choix: dict | None = None
        couche = QVBoxLayout(self)
        avertissement = QLabel(
            "Le système a détecté des fiches proches. Une concordance de nom ne suffit pas à "
            "établir l'identité : vérifiez les pièces avant toute décision. Aucune fiche n'est "
            "fusionnée automatiquement."
        )
        avertissement.setObjectName("avertissement")
        avertissement.setWordWrap(True)
        couche.addWidget(avertissement)
        self.tableau = TableauDonnees(COLONNES_CANDIDATS, pagine=False)
        self.tableau.definir_lignes(candidats)
        couche.addWidget(self.tableau, 1)
        boutons = QHBoxLayout()
        boutons.addStretch()
        fermer = QPushButton("Fermer" if not creation else "Annuler")
        fermer.clicked.connect(self.reject)
        boutons.addWidget(fermer)
        if creation:
            utiliser = QPushButton("Utiliser la fiche sélectionnée")
            utiliser.clicked.connect(self._utiliser)
            creer = QPushButton("Créer une nouvelle fiche malgré tout")
            creer.setObjectName("boutonPrincipal")
            creer.clicked.connect(lambda: self.done(self.CREER))
            boutons.addWidget(utiliser)
            boutons.addWidget(creer)
        couche.addLayout(boutons)

    def _utiliser(self) -> None:
        self.choix = self.tableau.selection()
        if self.choix:
            self.done(self.UTILISER)


class FormulairePersonne(FormulaireDialogue):
    def __init__(self, session, parent=None, existante: dict | None = None):
        super().__init__("Modifier la fiche" if existante else "Nouvelle personne", parent)
        self.session, self.existante = session, existante
        avis = QLabel(
            "Les informations inconnues peuvent rester vides. Ne saisir que les données nécessaires à la procédure."
        )
        avis.setWordWrap(True)
        avis.setObjectName("sousTitrePage")
        self.formulaire.addRow(avis)
        self.nom = self.ajouter("Nom", QLineEdit(), True)
        self.prenoms = self.ajouter("Prénoms", QLineEdit())
        self.naissance = self.ajouter("Date de naissance", ChampDate())
        self.lieu = self.ajouter("Lieu de naissance", QLineEdit())
        self.nationalite = self.ajouter("Nationalité déclarée", QLineEdit())
        self.sexe = self.ajouter("Sexe (si justifié)", Choix(L.SEXE, "Non collecté"))
        self.alias = self.ajouter("Alias documentés", QLineEdit())
        self.alias.setPlaceholderText("séparés par des virgules")
        self.telephone = self.ajouter("Téléphone", QLineEdit())
        self.adresse = self.ajouter("Adresse", QLineEdit())
        self.type_document = self.ajouter("Type de document", Choix(L.TYPE_DOCUMENT_IDENTITE, "Aucun"))
        self.numero_document = self.ajouter("Référence du document", QLineEdit())
        self.verification = self.ajouter("Vérification de l'identité", Choix(L.VERIFICATION_IDENTITE))
        if existante:
            self.nom.setText(existante["nom"])
            self.prenoms.setText(existante.get("prenoms") or "")
            self.naissance.definir(existante.get("date_naissance"))
            self.lieu.setText(existante.get("lieu_naissance") or "")
            self.nationalite.setText(existante.get("nationalite") or "")
            self.sexe.choisir(existante.get("sexe"))
            self.alias.setText(", ".join(existante.get("alias") or []))
            self.telephone.setText((existante.get("coordonnees") or {}).get("telephone") or "")
            self.adresse.setText((existante.get("coordonnees") or {}).get("adresse") or "")
            self.type_document.choisir(existante.get("type_document"))
            self.numero_document.setText(existante.get("numero_document") or "")
            self.verification.choisir(existante.get("statut_verification"))
        self.action = self._enregistrer

    def donnees(self) -> dict:
        if not self.nom.text().strip():
            raise ValueError("Le nom est obligatoire.")
        alias = [a.strip() for a in self.alias.text().split(",") if a.strip()]
        coordonnees = {"telephone": texte_ou_none(self.telephone), "adresse": texte_ou_none(self.adresse)}
        return {
            "nom": self.nom.text().strip().upper(),
            "prenoms": texte_ou_none(self.prenoms),
            "date_naissance": self.naissance.valeur(),
            "lieu_naissance": texte_ou_none(self.lieu),
            "nationalite": texte_ou_none(self.nationalite),
            "sexe": self.sexe.valeur(),
            "alias": alias or None,
            "coordonnees": coordonnees if any(coordonnees.values()) else None,
            "type_document": self.type_document.valeur(),
            "numero_document": texte_ou_none(self.numero_document),
            "statut_verification": self.verification.valeur(),
        }

    def _enregistrer(self):
        donnees = self.donnees()
        api = self.session.api
        if self.existante:
            return api.patch(f"/personnes/{self.existante['id']}", {**donnees, "version": self.existante["version"]})
        try:
            return api.post("/personnes", donnees)
        except ErreurAPI as exc:
            if exc.code != "DOUBLONS_POTENTIELS":
                raise
            dialogue = DialogueDoublons(exc.details.get("candidats", []), self)
            decision = dialogue.exec()
            if decision == DialogueDoublons.UTILISER:
                return dialogue.choix
            if decision == DialogueDoublons.CREER:
                return api.post("/personnes", {**donnees, "confirmer_malgre_doublons": True})
            raise ValueError("Création annulée : vérifiez les fiches existantes.") from None


class DialogueSelectionPersonne(QDialog):
    """Recherche d'une personne existante ou creation, puis choix du role procedural."""

    def __init__(self, session, parent=None, avec_role: bool = True):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Associer une personne")
        self.setMinimumSize(760, 440)
        self.personne: dict | None = None
        couche = QVBoxLayout(self)
        recherche = QHBoxLayout()
        self.texte = QLineEdit()
        self.texte.setPlaceholderText("Nom ou numéro interne")
        self.texte.returnPressed.connect(self.chercher)
        bouton = QPushButton("Rechercher")
        bouton.clicked.connect(self.chercher)
        nouvelle = QPushButton("Nouvelle personne")
        nouvelle.clicked.connect(self.creer)
        nouvelle.setEnabled(session.a("personne.creer"))
        recherche.addWidget(self.texte, 1)
        recherche.addWidget(bouton)
        recherche.addWidget(nouvelle)
        couche.addLayout(recherche)
        self.tableau = TableauDonnees(COLONNES_PERSONNES, pagine=False)
        self.tableau.ligne_activee.connect(lambda _: self.valider())
        couche.addWidget(self.tableau, 1)
        formulaire = QFormLayout()
        self.role = Choix(L.ROLE_PERSONNE)
        if avec_role:
            formulaire.addRow("Rôle procédural", self.role)
            note = QLabel(
                "Rappel : une personne mise en cause est présumée innocente. Le rôle ne vaut pas qualification pénale."
            )
            note.setObjectName("sousTitrePage")
            formulaire.addRow(note)
        couche.addLayout(formulaire)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.button(QDialogButtonBox.Ok).setText("Associer")
        boutons.button(QDialogButtonBox.Cancel).setText("Annuler")
        boutons.accepted.connect(self.valider)
        boutons.rejected.connect(self.reject)
        couche.addWidget(boutons)

    def chercher(self) -> None:
        try:
            resultat = self.session.api.get("/personnes", {"texte": self.texte.text().strip(), "taille": 50})
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        self.tableau.definir_lignes(resultat["elements"])

    def creer(self) -> None:
        formulaire = FormulairePersonne(self.session, self)
        if formulaire.exec() == QDialog.Accepted and formulaire.resultat:
            self.personne = formulaire.resultat
            self.accept()

    def valider(self) -> None:
        self.personne = self.personne or self.tableau.selection()
        if self.personne:
            self.accept()

    def role_choisi(self) -> str:
        return self.role.valeur()


class DialogueFichePersonne(QDialog):
    def __init__(self, session, personne_id: str, finalite: str, parent=None):
        super().__init__(parent)
        self.session, self.personne_id, self.finalite = session, personne_id, finalite
        self.api = session.api
        self.setWindowTitle("Fiche personne")
        self.setMinimumSize(880, 560)
        self.couche = QVBoxLayout(self)
        self.entete = QLabel("")
        self.entete.setObjectName("titrePage")
        self.couche.addWidget(self.entete)
        self.trace = QLabel("")
        self.trace.setObjectName("sousTitrePage")
        self.couche.addWidget(self.trace)
        self.onglets = QTabWidget()
        self.couche.addWidget(self.onglets, 1)
        boutons = QHBoxLayout()
        self.modifier = QPushButton("Modifier la fiche")
        self.modifier.clicked.connect(self._modifier)
        self.modifier.setEnabled(session.a("personne.modifier"))
        boutons.addWidget(self.modifier)
        boutons.addStretch()
        fermer = QPushButton("Fermer")
        fermer.clicked.connect(self.accept)
        boutons.addWidget(fermer)
        self.couche.addLayout(boutons)
        self.recharger()

    def recharger(self) -> None:
        try:
            self.fiche = self.api.get(f"/personnes/{self.personne_id}", finalite=self.finalite)
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            self.fiche = None
            return
        f = self.fiche
        self.entete.setText(f"{f['nom']} {f.get('prenoms') or ''}  ({f['numero_interne']})")
        self.trace.setText(f"Consultation journalisée. Finalité : {self.finalite}. Trace : {f['trace_audit']}")
        self.onglets.clear()
        identite = QWidget()
        formulaire = QFormLayout(identite)
        coord = f.get("coordonnees") or {}
        for libelle, valeur in [
            ("Nom", f["nom"]),
            ("Prénoms", f.get("prenoms")),
            ("Date de naissance", fmt_date(f.get("date_naissance"))),
            ("Lieu de naissance", f.get("lieu_naissance")),
            ("Nationalité déclarée", f.get("nationalite")),
            ("Sexe", L.libelle(L.SEXE, f.get("sexe"))),
            ("Alias", ", ".join(f.get("alias") or [])),
            ("Téléphone", coord.get("telephone")),
            ("Adresse", coord.get("adresse")),
            ("Document", L.libelle(L.TYPE_DOCUMENT_IDENTITE, f.get("type_document"))),
            ("Référence du document", f.get("numero_document")),
            ("Vérification de l'identité", L.libelle(L.VERIFICATION_IDENTITE, f.get("statut_verification"))),
            ("Unité d'enregistrement", f.get("unite_creation")),
            ("Statut de la fiche", f.get("statut")),
            ("Créée le", fmt_date(f.get("cree_le"))),
            ("Modifiée le", fmt_date(f.get("modifie_le"))),
        ]:
            champ = QLabel(valeur or "Non renseigné")
            champ.setWordWrap(True)
            formulaire.addRow(libelle, champ)
        self.onglets.addTab(identite, "Identité")
        liens = TableauDonnees(
            [
                ("type", "Type", None),
                ("reference", "Référence", None),
                ("role", "Rôle", lambda v, _: L.libelle(L.ROLE_PERSONNE, v)),
                ("statut", "Statut", None),
            ],
            pagine=False,
        )
        liens.definir_lignes(f["liens"])
        self.onglets.addTab(liens, f"Dossiers liés ({len(f['liens'])})")
        if self.session.a("biometrie.lire"):
            self.onglets.addTab(OngletBiometrie(self.session, self.personne_id, self.finalite, self), "Biométrie")
        historique = TableauDonnees(
            [
                ("modifie_le", "Date", lambda v, _: fmt_date(v)),
                ("modifie_par", "Par", None),
                ("action", "Action", None),
                ("changements", "Détails", lambda v, _: str(v or "")),
            ],
            pagine=False,
        )
        historique.definir_lignes(f["historique"])
        self.onglets.addTab(historique, "Historique")

    def _modifier(self) -> None:
        if self.fiche and FormulairePersonne(self.session, self, self.fiche).exec() == QDialog.Accepted:
            self.recharger()


class OngletBiometrie(QWidget):
    """References biometriques : adaptateur SIMULE, donnees synthetiques uniquement."""

    def __init__(self, session, personne_id: str, finalite: str, parent=None):
        super().__init__(parent)
        self.session, self.personne_id, self.finalite = session, personne_id, finalite
        couche = QVBoxLayout(self)
        avis = QLabel(
            "Module biométrique en mode SIMULATION : aucune empreinte réelle n'est capturée ni comparée. "
            "Seules des vérifications une à une sont possibles ; la recherche biométrique est désactivée."
        )
        avis.setObjectName("avertissement")
        avis.setWordWrap(True)
        couche.addWidget(avis)
        self.tableau = TableauDonnees(
            [
                ("position_doigt", "Doigt", None),
                ("collectee_le", "Collectée le", lambda v, _: fmt_date(v)),
                ("equipement", "Équipement", None),
                ("fondement_legal", "Fondement juridique", None),
                ("consentement_recueilli", "Consentement", None),
                ("qualite", "Qualité", None),
                ("conserver_jusqua", "Conservation jusqu'au", lambda v, _: fmt_date(v)),
                ("statut", "Statut", None),
                ("est_synthetique", "Synthétique", None),
            ],
            pagine=False,
        )
        couche.addWidget(self.tableau, 1)
        boutons = QHBoxLayout()
        enregistrer = QPushButton("Enregistrer une capture (simulée)")
        enregistrer.setEnabled(session.a("biometrie.enregistrer"))
        enregistrer.clicked.connect(self.enregistrer)
        verifier = QPushButton("Vérification une à une")
        verifier.setEnabled(session.a("biometrie.verifier"))
        verifier.clicked.connect(self.verifier)
        supprimer = QPushButton("Demander la suppression")
        supprimer.setObjectName("boutonDanger")
        supprimer.setEnabled(session.a("biometrie.supprimer"))
        supprimer.clicked.connect(self.supprimer)
        for b in (enregistrer, verifier, supprimer):
            boutons.addWidget(b)
        boutons.addStretch()
        couche.addLayout(boutons)
        self.charger()

    def charger(self) -> None:
        try:
            self.tableau.definir_lignes(
                self.session.api.get(f"/biometrie/personnes/{self.personne_id}/captures", finalite=self.finalite)
            )
        except ErreurAPI as exc:
            afficher_erreur(self, exc)

    def enregistrer(self) -> None:
        formulaire = FormulaireDialogue("Capture biométrique (simulation)", self)
        doigt = formulaire.ajouter("Doigt", Choix({d: d.replace("_", " ").capitalize() for d in L.DOIGTS}), True)
        equipement = formulaire.ajouter("Équipement", QLineEdit("Capteur simulé (aucun matériel)"), True)
        fondement = formulaire.ajouter("Fondement juridique", QLineEdit(), True)
        consentement = formulaire.ajouter("Consentement recueilli", Choix({True: "Oui", False: "Non"}))
        formulaire.action = lambda: self.session.api.post(
            "/biometrie/captures",
            {
                "personne_id": self.personne_id,
                "position_doigt": doigt.valeur(),
                "equipement": equipement.text(),
                "fondement_legal": fondement.text(),
                "consentement_recueilli": consentement.valeur(),
            },
            finalite=self.finalite,
        )
        if formulaire.exec() == QDialog.Accepted:
            self.charger()

    def verifier(self) -> None:
        capture = self.tableau.selection()
        if not capture:
            return
        try:
            r = self.session.api.post(
                "/biometrie/verifications",
                {"capture_id": capture["id"], "equipement": "Capteur simulé"},
                finalite=self.finalite,
            )
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        QMessageBox.information(
            self,
            "Résultat de vérification",
            f"Concordance : {'oui' if r['concordance'] else 'non'} (score {r['score']})\n\n"
            f"{r['commentaire']}\n\nTrace d'audit : {r['trace_audit']}",
        )

    def supprimer(self) -> None:
        capture = self.tableau.selection()
        if not capture:
            return
        motif = demander_motif(self, "Suppression d'une capture", "Motif de la demande (soumise à double validation) :")
        if motif:
            try:
                self.session.api.post(
                    f"/biometrie/captures/{capture['id']}/suppression", {"motif": motif}, finalite=self.finalite
                )
                QMessageBox.information(
                    self, "Demande enregistrée", "La demande sera exécutée après validation par un second responsable."
                )
            except ErreurAPI as exc:
                afficher_erreur(self, exc)


class PagePersonnes(Page):
    titre = "Gestion des personnes"
    sous_titre = (
        "Registre sécurisé des personnes citées dans les dossiers. Toute consultation de fiche "
        "exige une finalité et est journalisée."
    )

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        barre = QHBoxLayout()
        self.texte = QLineEdit()
        self.texte.setPlaceholderText("Nom, prénoms ou numéro interne")
        self.texte.returnPressed.connect(lambda: self.charger(1))
        chercher = QPushButton("Rechercher")
        chercher.clicked.connect(lambda: self.charger(1))
        nouvelle = QPushButton("Nouvelle personne")
        nouvelle.setObjectName("boutonPrincipal")
        nouvelle.setEnabled(session.a("personne.creer"))
        nouvelle.clicked.connect(self.creer)
        ouvrir = QPushButton("Ouvrir la fiche")
        ouvrir.clicked.connect(lambda: self.ouvrir(self.tableau.selection()))
        doublons = QPushButton("Rechercher des doublons")
        doublons.clicked.connect(self.doublons)
        fusion = QPushButton("Demander une fusion")
        fusion.setEnabled(session.a("personne.fusionner"))
        fusion.clicked.connect(self.fusion)
        barre.addWidget(self.texte, 1)
        barre.addWidget(chercher)
        barre.addWidget(nouvelle)
        self.couche.addLayout(barre)
        actions = QHBoxLayout()
        for b in (ouvrir, doublons, fusion):
            actions.addWidget(b)
        actions.addStretch()
        self.couche.addLayout(actions)
        self.tableau = TableauDonnees(COLONNES_PERSONNES)
        self.tableau.ligne_activee.connect(self.ouvrir)
        self.tableau.page_demandee.connect(self.charger)
        self.couche.addWidget(self.tableau, 1)

    def charger(self, page: int = 1) -> None:
        params = {"texte": self.texte.text().strip(), "page": page, "taille": 50}
        self.executer(lambda: self.api.get("/personnes", params), self.tableau.definir_page)

    def creer(self) -> None:
        if FormulairePersonne(self.session, self).exec() == QDialog.Accepted:
            self.charger(self.tableau.page)

    def ouvrir(self, personne: dict | None) -> None:
        if not personne:
            return
        finalite = self.session.finalite(self)
        if finalite:
            DialogueFichePersonne(self.session, personne["id"], finalite, self).exec()

    def doublons(self) -> None:
        p = self.tableau.selection()
        if not p:
            QMessageBox.information(self, "Doublons", "Sélectionnez d'abord une fiche.")
            return
        candidats = self.appel_direct(
            lambda: self.api.post(
                "/personnes/doublons",
                {
                    "nom": p["nom"],
                    "prenoms": p.get("prenoms"),
                    "date_naissance": p.get("date_naissance"),
                    "lieu_naissance": p.get("lieu_naissance"),
                    "exclure_id": p["id"],
                },
            )
        )
        if candidats is not None:
            DialogueDoublons(candidats, self, creation=False).exec()

    def fusion(self) -> None:
        conservee = self.tableau.selection()
        if not conservee:
            QMessageBox.information(self, "Fusion", "Sélectionnez la fiche à conserver.")
            return
        selection = DialogueSelectionPersonne(self.session, self, avec_role=False)
        selection.setWindowTitle("Fiche à absorber dans la fiche sélectionnée")
        if selection.exec() != QDialog.Accepted or not selection.personne:
            return
        absorbee = selection.personne
        if not confirmer(
            self,
            "Demande de fusion",
            f"Fusionner {absorbee['numero_interne']} dans {conservee['numero_interne']} ?\n"
            "La fusion ne sera exécutée qu'après validation par un second responsable.",
        ):
            return
        motif = demander_motif(self, "Motif de la fusion", "Justifiez la fusion (vérification sur pièces) :")
        if motif and self.appel_direct(
            lambda: self.api.post(
                "/personnes/fusions",
                {"personne_conservee_id": conservee["id"], "personne_absorbee_id": absorbee["id"], "motif": motif},
            )
        ):
            QMessageBox.information(self, "Demande enregistrée", "Demande de fusion soumise à double validation.")
