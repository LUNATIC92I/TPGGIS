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
from tpgis.shared.i18n import tr

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
        lambda v, ligne: tr(
            "{libelle} ({get})", libelle=L.libelle(L.NIVEAU_CORRESPONDANCE, v), get=ligne.get("score", "")
        ),
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
        self.setWindowTitle(tr("Fiches potentiellement identiques"))
        self.setMinimumSize(860, 360)
        self.choix: dict | None = None
        couche = QVBoxLayout(self)
        avertissement = QLabel(
            tr(
                "Le système a détecté des fiches proches. Une concordance de nom ne suffit pas à "
                "établir l'identité : vérifiez les pièces avant toute décision. Aucune fiche n'est "
                "fusionnée automatiquement."
            )
        )
        avertissement.setObjectName("avertissement")
        avertissement.setWordWrap(True)
        couche.addWidget(avertissement)
        self.tableau = TableauDonnees(COLONNES_CANDIDATS, pagine=False)
        self.tableau.definir_lignes(candidats)
        couche.addWidget(self.tableau, 1)
        boutons = QHBoxLayout()
        boutons.addStretch()
        fermer = QPushButton(tr("Fermer") if not creation else tr("Annuler"))
        fermer.clicked.connect(self.reject)
        boutons.addWidget(fermer)
        if creation:
            utiliser = QPushButton(tr("Utiliser la fiche sélectionnée"))
            utiliser.clicked.connect(self._utiliser)
            creer = QPushButton(tr("Créer une nouvelle fiche malgré tout"))
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
        super().__init__(tr("Modifier la fiche") if existante else tr("Nouvelle personne"), parent)
        self.session, self.existante = session, existante
        avis = QLabel(
            tr("Les informations inconnues peuvent rester vides. Ne saisir que les données nécessaires à la procédure.")
        )
        avis.setWordWrap(True)
        avis.setObjectName("sousTitrePage")
        self.formulaire.addRow(avis)
        self.nom = self.ajouter(tr("Nom"), QLineEdit(), True)
        self.prenoms = self.ajouter(tr("Prénoms"), QLineEdit())
        self.naissance = self.ajouter(tr("Date de naissance"), ChampDate())
        self.lieu = self.ajouter(tr("Lieu de naissance"), QLineEdit())
        self.nationalite = self.ajouter(tr("Nationalité déclarée"), QLineEdit())
        self.sexe = self.ajouter(tr("Sexe (si justifié)"), Choix(L.SEXE, tr("Non collecté")))
        self.alias = self.ajouter(tr("Alias documentés"), QLineEdit())
        self.alias.setPlaceholderText(tr("séparés par des virgules"))
        self.telephone = self.ajouter(tr("Téléphone"), QLineEdit())
        self.adresse = self.ajouter(tr("Adresse"), QLineEdit())
        self.type_document = self.ajouter(tr("Type de document"), Choix(L.TYPE_DOCUMENT_IDENTITE, tr("Aucun")))
        self.numero_document = self.ajouter(tr("Référence du document"), QLineEdit())
        self.verification = self.ajouter(tr("Vérification de l'identité"), Choix(L.VERIFICATION_IDENTITE))
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
            raise ValueError(tr("Le nom est obligatoire."))
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
            raise ValueError(tr("Création annulée : vérifiez les fiches existantes.")) from None


class DialogueSelectionPersonne(QDialog):
    """Recherche d'une personne existante ou creation, puis choix du role procedural."""

    def __init__(self, session, parent=None, avec_role: bool = True):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(tr("Associer une personne"))
        self.setMinimumSize(760, 440)
        self.personne: dict | None = None
        couche = QVBoxLayout(self)
        recherche = QHBoxLayout()
        self.texte = QLineEdit()
        self.texte.setPlaceholderText(tr("Nom ou numéro interne"))
        self.texte.returnPressed.connect(self.chercher)
        bouton = QPushButton(tr("Rechercher"))
        bouton.clicked.connect(self.chercher)
        nouvelle = QPushButton(tr("Nouvelle personne"))
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
            formulaire.addRow(tr("Rôle procédural"), self.role)
            note = QLabel(
                tr(
                    "Rappel : une personne mise en cause est présumée innocente. Le rôle ne vaut pas "
                    "qualification pénale."
                )
            )
            note.setObjectName("sousTitrePage")
            formulaire.addRow(note)
        couche.addLayout(formulaire)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.button(QDialogButtonBox.Ok).setText(tr("Associer"))
        boutons.button(QDialogButtonBox.Cancel).setText(tr("Annuler"))
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
        self.setWindowTitle(tr("Fiche personne"))
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
        self.modifier = QPushButton(tr("Modifier la fiche"))
        self.modifier.clicked.connect(self._modifier)
        self.modifier.setEnabled(session.a("personne.modifier"))
        boutons.addWidget(self.modifier)
        boutons.addStretch()
        fermer = QPushButton(tr("Fermer"))
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
        self.entete.setText(
            tr(
                "{nom} {v2}  ({numero_interne})",
                nom=f["nom"],
                v2=f.get("prenoms") or "",
                numero_interne=f["numero_interne"],
            )
        )
        self.trace.setText(
            tr(
                "Consultation journalisée. Finalité : {finalite}. Trace : {trace_audit}",
                finalite=self.finalite,
                trace_audit=f["trace_audit"],
            )
        )
        self.onglets.clear()
        identite = QWidget()
        formulaire = QFormLayout(identite)
        coord = f.get("coordonnees") or {}
        for libelle, valeur in [
            (tr("Nom"), f["nom"]),
            (tr("Prénoms"), f.get("prenoms")),
            (tr("Date de naissance"), fmt_date(f.get("date_naissance"))),
            (tr("Lieu de naissance"), f.get("lieu_naissance")),
            (tr("Nationalité déclarée"), f.get("nationalite")),
            (tr("Sexe"), L.libelle(L.SEXE, f.get("sexe"))),
            (tr("Alias"), ", ".join(f.get("alias") or [])),
            (tr("Téléphone"), coord.get("telephone")),
            (tr("Adresse"), coord.get("adresse")),
            (tr("Document"), L.libelle(L.TYPE_DOCUMENT_IDENTITE, f.get("type_document"))),
            (tr("Référence du document"), f.get("numero_document")),
            (tr("Vérification de l'identité"), L.libelle(L.VERIFICATION_IDENTITE, f.get("statut_verification"))),
            (tr("Unité d'enregistrement"), f.get("unite_creation")),
            (tr("Statut de la fiche"), f.get("statut")),
            (tr("Créée le"), fmt_date(f.get("cree_le"))),
            (tr("Modifiée le"), fmt_date(f.get("modifie_le"))),
        ]:
            champ = QLabel(valeur or tr("Non renseigné"))
            champ.setWordWrap(True)
            formulaire.addRow(libelle, champ)
        self.onglets.addTab(identite, tr("Identité"))
        liens = TableauDonnees(
            [
                ("type", tr("Type"), None),
                ("reference", tr("Référence"), None),
                ("role", tr("Rôle"), lambda v, _: L.libelle(L.ROLE_PERSONNE, v)),
                ("statut", tr("Statut"), None),
            ],
            pagine=False,
        )
        liens.definir_lignes(f["liens"])
        self.onglets.addTab(liens, tr("Dossiers liés ({len})", len=len(f["liens"])))
        if self.session.a("biometrie.lire"):
            self.onglets.addTab(OngletBiometrie(self.session, self.personne_id, self.finalite, self), tr("Biométrie"))
        historique = TableauDonnees(
            [
                ("modifie_le", tr("Date"), lambda v, _: fmt_date(v)),
                ("modifie_par", tr("Par"), None),
                ("action", tr("Action"), None),
                ("changements", tr("Détails"), lambda v, _: str(v or "")),
            ],
            pagine=False,
        )
        historique.definir_lignes(f["historique"])
        self.onglets.addTab(historique, tr("Historique"))

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
            tr(
                "Module biométrique en mode SIMULATION : aucune empreinte réelle n'est capturée ni comparée. "
                "Seules des vérifications une à une sont possibles ; la recherche biométrique est désactivée."
            )
        )
        avis.setObjectName("avertissement")
        avis.setWordWrap(True)
        couche.addWidget(avis)
        self.tableau = TableauDonnees(
            [
                ("position_doigt", tr("Doigt"), None),
                ("collectee_le", tr("Collectée le"), lambda v, _: fmt_date(v)),
                ("equipement", tr("Équipement"), None),
                ("fondement_legal", tr("Fondement juridique"), None),
                ("consentement_recueilli", tr("Consentement"), None),
                ("qualite", tr("Qualité"), None),
                ("conserver_jusqua", tr("Conservation jusqu'au"), lambda v, _: fmt_date(v)),
                ("statut", tr("Statut"), None),
                ("est_synthetique", tr("Synthétique"), None),
            ],
            pagine=False,
        )
        couche.addWidget(self.tableau, 1)
        boutons = QHBoxLayout()
        enregistrer = QPushButton(tr("Enregistrer une capture (simulée)"))
        enregistrer.setEnabled(session.a("biometrie.enregistrer"))
        enregistrer.clicked.connect(self.enregistrer)
        verifier = QPushButton(tr("Vérification une à une"))
        verifier.setEnabled(session.a("biometrie.verifier"))
        verifier.clicked.connect(self.verifier)
        supprimer = QPushButton(tr("Demander la suppression"))
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
        formulaire = FormulaireDialogue(tr("Capture biométrique (simulation)"), self)
        doigt = formulaire.ajouter(tr("Doigt"), Choix({d: d.replace("_", " ").capitalize() for d in L.DOIGTS}), True)
        equipement = formulaire.ajouter(tr("Équipement"), QLineEdit(tr("Capteur simulé (aucun matériel)")), True)
        fondement = formulaire.ajouter(tr("Fondement juridique"), QLineEdit(), True)
        consentement = formulaire.ajouter(tr("Consentement recueilli"), Choix({True: tr("Oui"), False: tr("Non")}))
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
                {"capture_id": capture["id"], "equipement": tr("Capteur simulé")},
                finalite=self.finalite,
            )
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        QMessageBox.information(
            self,
            tr("Résultat de vérification"),
            tr(
                "Concordance : {v1} (score {score})\n\n{commentaire}\n\nTrace d'audit : {trace_audit}",
                v1="oui" if r["concordance"] else "non",
                score=r["score"],
                commentaire=r["commentaire"],
                trace_audit=r["trace_audit"],
            ),
        )

    def supprimer(self) -> None:
        capture = self.tableau.selection()
        if not capture:
            return
        motif = demander_motif(
            self, tr("Suppression d'une capture"), tr("Motif de la demande (soumise à double validation) :")
        )
        if motif:
            try:
                self.session.api.post(
                    f"/biometrie/captures/{capture['id']}/suppression", {"motif": motif}, finalite=self.finalite
                )
                QMessageBox.information(
                    self,
                    tr("Demande enregistrée"),
                    tr("La demande sera exécutée après validation par un second responsable."),
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
        self.texte.setPlaceholderText(tr("Nom, prénoms ou numéro interne"))
        self.texte.returnPressed.connect(lambda: self.charger(1))
        chercher = QPushButton(tr("Rechercher"))
        chercher.clicked.connect(lambda: self.charger(1))
        nouvelle = QPushButton(tr("Nouvelle personne"))
        nouvelle.setObjectName("boutonPrincipal")
        nouvelle.setEnabled(session.a("personne.creer"))
        nouvelle.clicked.connect(self.creer)
        ouvrir = QPushButton(tr("Ouvrir la fiche"))
        ouvrir.clicked.connect(lambda: self.ouvrir(self.tableau.selection()))
        doublons = QPushButton(tr("Rechercher des doublons"))
        doublons.clicked.connect(self.doublons)
        fusion = QPushButton(tr("Demander une fusion"))
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
            QMessageBox.information(self, tr("Doublons"), tr("Sélectionnez d'abord une fiche."))
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
            QMessageBox.information(self, tr("Fusion"), tr("Sélectionnez la fiche à conserver."))
            return
        selection = DialogueSelectionPersonne(self.session, self, avec_role=False)
        selection.setWindowTitle(tr("Fiche à absorber dans la fiche sélectionnée"))
        if selection.exec() != QDialog.Accepted or not selection.personne:
            return
        absorbee = selection.personne
        if not confirmer(
            self,
            tr("Demande de fusion"),
            tr(
                "Fusionner {numero_interne} dans {numero_interne2} ?\nLa fusion ne sera exécutée "
                "qu'après validation par un second responsable.",
                numero_interne=absorbee["numero_interne"],
                numero_interne2=conservee["numero_interne"],
            ),
        ):
            return
        motif = demander_motif(self, tr("Motif de la fusion"), tr("Justifiez la fusion (vérification sur pièces) :"))
        if motif and self.appel_direct(
            lambda: self.api.post(
                "/personnes/fusions",
                {"personne_conservee_id": conservee["id"], "personne_absorbee_id": absorbee["id"], "motif": motif},
            )
        ):
            QMessageBox.information(
                self, tr("Demande enregistrée"), tr("Demande de fusion soumise à double validation.")
            )
