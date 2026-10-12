"""Gestion des plaintes et onglet des pieces jointes (reutilise par les dossiers)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
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
    fmt_date,
    texte_ou_none,
)
from tpgis.client.windows.base import Page
from tpgis.client.windows.personnes import DialogueSelectionPersonne
from tpgis.shared.geographie import provinces
from tpgis.shared.i18n import tr

COLONNES_PLAINTES = [
    ("numero", "Numéro", None),
    ("recue_le", "Reçue le", lambda v, _: fmt_date(v)),
    ("categorie", "Type de plainte", lambda v, _: tr(v) if v else ""),
    ("statut", "Statut", lambda v, _: L.libelle(L.STATUT_PLAINTE, v)),
    ("unite_nom", "Unité", None),
    ("agent_responsable", "Agent responsable", None),
    ("lieu_faits", "Lieu déclaré", None),
]


class OngletPieces(QWidget):
    """Pieces jointes d'une plainte, d'un dossier ou d'une personne."""

    def __init__(self, session, parent_cle: str, parent_id: str, parent=None):
        super().__init__(parent)
        self.session, self.cle, self.ident = session, parent_cle, parent_id
        couche = QVBoxLayout(self)
        self.tableau = TableauDonnees(
            [
                ("intitule", tr("Intitulé"), None),
                ("type_piece", tr("Type"), lambda v, _: L.libelle(L.TYPE_PIECE, v)),
                ("version_courante", tr("Version"), None),
                ("versions", tr("Fichier"), lambda v, _: v[-1]["nom_fichier"] if v else ""),
                (
                    "versions",
                    tr("Analyse antivirus"),
                    lambda v, _: L.libelle(L.STATUT_ANALYSE, v[-1]["statut_analyse"]) if v else "",
                ),
                ("versions", tr("Empreinte SHA-256"), lambda v, _: v[-1]["sha256"][:16] + "…" if v else ""),
                ("cree_le", tr("Déposée le"), lambda v, _: fmt_date(v)),
            ],
            pagine=False,
        )
        couche.addWidget(self.tableau, 1)
        boutons = QHBoxLayout()
        deposer = QPushButton(tr("Déposer une pièce"))
        deposer.setEnabled(session.a("document.ajouter"))
        deposer.clicked.connect(self.deposer)
        version = QPushButton(tr("Nouvelle version"))
        version.setEnabled(session.a("document.ajouter"))
        version.clicked.connect(self.nouvelle_version)
        telecharger = QPushButton(tr("Télécharger"))
        telecharger.clicked.connect(self.telecharger)
        for b in (deposer, version, telecharger):
            boutons.addWidget(b)
        boutons.addStretch()
        couche.addLayout(boutons)
        self.charger()

    def charger(self) -> None:
        try:
            self.tableau.definir_lignes(self.session.api.get("/documents", {self.cle: self.ident}))
        except ErreurAPI as exc:
            afficher_erreur(self, exc)

    def _choisir_fichier(self) -> tuple[str, bytes] | None:
        chemin, _ = QFileDialog.getOpenFileName(
            self,
            tr("Choisir une pièce"),
            str(Path.home()),
            tr("Documents (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.docx *.odt *.txt)"),
        )
        if not chemin:
            return None
        return Path(chemin).name, Path(chemin).read_bytes()

    def deposer(self) -> None:
        formulaire = FormulaireDialogue(tr("Déposer une pièce"), self)
        intitule = formulaire.ajouter(tr("Intitulé"), QLineEdit(), True)
        type_piece = formulaire.ajouter(tr("Type de pièce"), Choix(L.TYPE_PIECE))

        def _action():
            fichier = self._choisir_fichier()
            if not fichier:
                raise ValueError(tr("Aucun fichier sélectionné."))
            resultat = self.session.api.deposer(
                "/documents",
                {"intitule": intitule.text(), "type_piece": type_piece.valeur(), self.cle: self.ident},
                *fichier,
            )
            if not resultat["disponible"]:
                QMessageBox.warning(
                    self,
                    tr("Pièce non disponible"),
                    tr(
                        "L'analyse antivirus n'a pas confirmé l'innocuité du fichier : {resultat_analyse}",
                        resultat_analyse=resultat["versions"][-1]["resultat_analyse"],
                    ),
                )
            return resultat

        formulaire.action = _action
        if formulaire.exec() == QDialog.Accepted:
            self.charger()

    def nouvelle_version(self) -> None:
        doc = self.tableau.selection()
        fichier = self._choisir_fichier() if doc else None
        if fichier:
            try:
                self.session.api.deposer(f"/documents/{doc['id']}/versions", {}, *fichier)
            except ErreurAPI as exc:
                afficher_erreur(self, exc)
            self.charger()

    def telecharger(self) -> None:
        doc = self.tableau.selection()
        if not doc:
            return
        try:
            nom, contenu = self.session.api.telecharger(f"/documents/{doc['id']}/contenu")
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        destination, _ = QFileDialog.getSaveFileName(self, tr("Enregistrer la pièce"), str(Path.home() / nom))
        if destination:
            Path(destination).write_bytes(contenu)


class FormulairePlainte(FormulaireDialogue):
    def __init__(self, session, parent=None, existante: dict | None = None):
        super().__init__(tr("Modifier la plainte") if existante else tr("Enregistrer une plainte"), parent, 680)
        self.session, self.existante = session, existante
        self.personnes: list[dict] = []
        if not existante:
            self.recue_le = self.ajouter(tr("Date et heure de réception"), QDateTimeEdit(QDateTime.currentDateTime()))
            self.recue_le.setDisplayFormat("dd/MM/yyyy HH:mm")
            self.recue_le.setMaximumDateTime(QDateTime.currentDateTime())
            self.service = self.ajouter(
                tr("Service d'enregistrement"),
                QLineEdit(f"Accueil, {session.moi['unite_nom']}"),
                True,
            )
            self.unite = self.ajouter(
                tr("Unité concernée"), Choix({u["id"]: u["nom"] for u in session.unites() if u["active"]})
            )
            self.unite.choisir(session.moi["unite_id"])
        self.categorie = self.ajouter(
            tr("Type de plainte"), Choix({c["id"]: c["libelle"] for c in session.categories()}, tr("Non catégorisé"))
        )
        self.description = self.ajouter(tr("Description des faits allégués"), QPlainTextEdit())
        self.description.setMinimumHeight(110)
        self.date_faits = self.ajouter(tr("Date déclarée des faits"), ChampDate())
        self.lieu = self.ajouter(tr("Lieu déclaré des faits"), QLineEdit())
        self.province = self.ajouter(tr("Province des faits"), Choix(provinces(), tr("Province de l'unité")))
        self.references = self.ajouter(tr("Procès-verbaux et références"), QLineEdit())
        self.temoins = self.ajouter(tr("Témoins non identifiés"), QPlainTextEdit())
        self.temoins.setMaximumHeight(60)
        self.observations = self.ajouter(tr("Observations"), QPlainTextEdit())
        self.observations.setMaximumHeight(70)
        if not existante:
            ligne = QHBoxLayout()
            self.resume_personnes = QLabel(tr("Aucune personne associée"))
            ajouter = QPushButton(tr("Associer une personne"))
            ajouter.clicked.connect(self._ajouter_personne)
            ligne.addWidget(self.resume_personnes, 1)
            ligne.addWidget(ajouter)
            conteneur = QWidget()
            conteneur.setLayout(ligne)
            self.formulaire.addRow(tr("Personnes concernées"), conteneur)
        rappel = QLabel(
            tr(
                "L'enregistrement d'une plainte rapporte des faits allégués : il ne désigne aucun auteur "
                "reconnu d'une infraction."
            )
        )
        rappel.setWordWrap(True)
        rappel.setObjectName("sousTitrePage")
        self.formulaire.addRow(rappel)
        if existante:
            self.categorie.choisir(existante.get("categorie_id"))
            self.description.setPlainText(existante.get("description") or "")
            self.date_faits.definir(existante.get("date_faits"))
            self.lieu.setText(existante.get("lieu_faits") or "")
            self.province.choisir(existante.get("province_code"))
            self.references.setText(existante.get("references_procedure") or "")
            self.temoins.setPlainText(existante.get("temoins_non_identifies") or "")
            self.observations.setPlainText(existante.get("observations") or "")
        self.action = self._enregistrer

    def _ajouter_personne(self) -> None:
        dialogue = DialogueSelectionPersonne(self.session, self)
        if dialogue.exec() == QDialog.Accepted and dialogue.personne:
            self.personnes.append(
                {
                    "personne_id": dialogue.personne["id"],
                    "role": dialogue.role_choisi(),
                    "_nom": tr("{nom} {v2}", nom=dialogue.personne["nom"], v2=dialogue.personne.get("prenoms") or ""),
                }
            )
            self.resume_personnes.setText(
                "\n".join(f"{p['_nom']} ({L.libelle(L.ROLE_PERSONNE, p['role'])})" for p in self.personnes)
            )

    def _enregistrer(self):
        description = self.description.toPlainText().strip()
        if len(description) < 10:
            raise ValueError(tr("La description des faits doit comporter au moins 10 caractères."))
        donnees = {
            "categorie_id": self.categorie.valeur(),
            "description": description,
            "date_faits": self.date_faits.valeur(),
            "lieu_faits": texte_ou_none(self.lieu),
            "province_code": self.province.valeur(),
            "references_procedure": texte_ou_none(self.references),
            "temoins_non_identifies": texte_ou_none(self.temoins),
            "observations": texte_ou_none(self.observations),
        }
        if self.existante:
            return self.session.api.patch(
                f"/plaintes/{self.existante['id']}", {**donnees, "version": self.existante["version"]}
            )
        donnees.update(
            {
                "recue_le": self.recue_le.dateTime().toUTC().toString("yyyy-MM-ddTHH:mm:ssZ"),
                "service_enregistrement": self.service.text().strip(),
                "unite_id": self.unite.valeur(),
                "personnes": [{k: v for k, v in p.items() if not k.startswith("_")} for p in self.personnes],
            }
        )
        return self.session.api.post("/plaintes", donnees)


class DialoguePlainte(QDialog):
    def __init__(self, session, plainte_id: str, parent=None):
        super().__init__(parent)
        self.session, self.ident, self.api = session, plainte_id, session.api
        self.setWindowTitle(tr("Plainte"))
        self.setMinimumSize(920, 600)
        self.couche = QVBoxLayout(self)
        self.titre = QLabel("")
        self.titre.setObjectName("titrePage")
        self.couche.addWidget(self.titre)
        self.onglets = QTabWidget()
        self.couche.addWidget(self.onglets, 1)
        boutons = QHBoxLayout()
        self.b_modifier = QPushButton(tr("Modifier"))
        self.b_modifier.clicked.connect(self.modifier)
        self.b_statut = QPushButton(tr("Changer le statut"))
        self.b_statut.clicked.connect(self.changer_statut)
        self.b_personne = QPushButton(tr("Associer une personne"))
        self.b_personne.clicked.connect(self.associer)
        self.b_fiche = QPushButton(tr("Fiche de plainte (PDF)"))
        self.b_fiche.clicked.connect(lambda: self.pdf("fiche.pdf"))
        self.b_bordereau = QPushButton(tr("Bordereau de transmission (PDF)"))
        self.b_bordereau.clicked.connect(lambda: self.pdf("bordereau.pdf"))
        for b in (self.b_modifier, self.b_statut, self.b_personne, self.b_fiche, self.b_bordereau):
            boutons.addWidget(b)
        boutons.addStretch()
        fermer = QPushButton(tr("Fermer"))
        fermer.clicked.connect(self.accept)
        boutons.addWidget(fermer)
        self.couche.addLayout(boutons)
        self.b_modifier.setEnabled(session.a("plainte.modifier"))
        self.b_statut.setEnabled(session.a("plainte.modifier", "plainte.cloturer", "plainte.archiver"))
        self.b_personne.setEnabled(session.a("plainte.modifier", "plainte.creer") and session.a("personne.lire"))
        self.recharger()

    def recharger(self) -> None:
        try:
            self.p = self.api.get(f"/plaintes/{self.ident}")
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        p = self.p
        self.titre.setText(
            tr("Plainte {numero}  |  {libelle}", numero=p["numero"], libelle=L.libelle(L.STATUT_PLAINTE, p["statut"]))
        )
        self.onglets.clear()
        infos = QWidget()
        f = QFormLayout(infos)
        for libelle, valeur in [
            (tr("Reçue le"), fmt_date(p["recue_le"])),
            (tr("Service d'enregistrement"), p["service_enregistrement"]),
            (tr("Unité"), p["unite_nom"]),
            (tr("Agent responsable"), p.get("agent_responsable")),
            (tr("Type de plainte"), tr(p.get("categorie"))),
            (tr("Date déclarée des faits"), fmt_date(p.get("date_faits"))),
            (tr("Lieu déclaré"), p.get("lieu_faits")),
            (tr("Province"), provinces().get(p.get("province_code") or "", "")),
            (tr("Faits allégués"), p["description"]),
            (tr("Références de procédure"), p.get("references_procedure")),
            (tr("Témoins non identifiés"), p.get("temoins_non_identifies")),
            (tr("Observations"), p.get("observations")),
            (tr("Motif du dernier statut"), p.get("motif_statut")),
            (tr("Service destinataire"), p.get("service_destinataire")),
        ]:
            champ = QLabel(valeur or "")
            champ.setWordWrap(True)
            f.addRow(libelle, champ)
        self.onglets.addTab(infos, tr("Informations"))
        personnes = TableauDonnees(
            [
                ("numero_interne", tr("N° interne"), None),
                ("nom", tr("Nom"), None),
                ("prenoms", tr("Prénoms"), None),
                ("role", tr("Rôle procédural"), lambda v, _: L.libelle(L.ROLE_PERSONNE, v)),
            ],
            pagine=False,
        )
        personnes.definir_lignes(p["personnes"])
        self.onglets.addTab(personnes, tr("Personnes ({len})", len=len(p["personnes"])))
        liens = TableauDonnees(
            [("type", tr("Type"), None), ("reference", tr("Référence"), None), ("statut", tr("Statut"), None)],
            pagine=False,
        )
        liens.definir_lignes(
            [{"type": tr("Dossier"), "reference": d["numero"], "statut": d["statut"]} for d in p["dossiers"]]
            + [
                {
                    "type": tr("Fait"),
                    "reference": x["reference"],
                    "statut": L.libelle(L.NATURE_INFORMATION, x["nature_information"]),
                }
                for x in p["faits"]
            ]
        )
        self.onglets.addTab(liens, tr("Dossiers et faits liés"))
        if self.session.a("document.lire"):
            self.onglets.addTab(OngletPieces(self.session, "plainte_id", self.ident, self), tr("Pièces"))
        historique = TableauDonnees(
            [
                ("modifie_le", tr("Date"), lambda v, _: fmt_date(v)),
                ("modifie_par", tr("Par"), None),
                ("action", tr("Action"), None),
                ("changements", tr("Détails"), lambda v, _: str(v or "")),
            ],
            pagine=False,
        )
        historique.definir_lignes(p["historique"])
        self.onglets.addTab(historique, tr("Historique des modifications"))

    def modifier(self) -> None:
        if FormulairePlainte(self.session, self, self.p).exec() == QDialog.Accepted:
            self.recharger()

    def changer_statut(self) -> None:
        formulaire = FormulaireDialogue(tr("Changer le statut"), self)
        statut = formulaire.ajouter(
            tr("Nouveau statut"), Choix({s: L.libelle(L.STATUT_PLAINTE, s) for s in self.p["transitions_possibles"]})
        )
        motif = formulaire.ajouter(tr("Motif"), QPlainTextEdit())
        destinataire = formulaire.ajouter(tr("Service destinataire (transmission)"), QLineEdit())
        note = QLabel(tr("La clôture, l'archivage et la réouverture exigent un motif et une habilitation spécifique."))
        note.setObjectName("sousTitrePage")
        note.setWordWrap(True)
        formulaire.formulaire.addRow(note)
        formulaire.action = lambda: self.api.post(
            f"/plaintes/{self.ident}/statut",
            {
                "version": self.p["version"],
                "statut": statut.valeur(),
                "motif": texte_ou_none(motif),
                "service_destinataire": texte_ou_none(destinataire),
            },
        )
        if formulaire.exec() == QDialog.Accepted:
            self.recharger()

    def associer(self) -> None:
        dialogue = DialogueSelectionPersonne(self.session, self)
        if dialogue.exec() == QDialog.Accepted and dialogue.personne:
            try:
                self.api.post(
                    f"/plaintes/{self.ident}/personnes",
                    {"personne_id": dialogue.personne["id"], "role": dialogue.role_choisi()},
                )
            except ErreurAPI as exc:
                afficher_erreur(self, exc)
            self.recharger()

    def pdf(self, nom: str) -> None:
        try:
            fichier, contenu = self.api.telecharger(f"/plaintes/{self.ident}/{nom}")
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, tr("Enregistrer le document"), str(Path.home() / fichier), tr("PDF (*.pdf)")
        )
        if destination:
            Path(destination).write_bytes(contenu)


class PagePlaintes(Page):
    titre = "Gestion des plaintes"
    sous_titre = "Enregistrement, suivi et clôture des plaintes de votre périmètre."

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        filtres = QHBoxLayout()
        self.numero = QLineEdit()
        self.numero.setPlaceholderText(tr("Numéro de plainte"))
        self.numero.setMinimumWidth(190)
        self.numero.returnPressed.connect(lambda: self.charger(1))
        self.statut = Choix(L.STATUT_PLAINTE, tr("Tous les statuts"))
        self.categorie = Choix({}, tr("Toutes les catégories"))
        self.du, self.au = ChampDate(tr("Du")), ChampDate(tr("Au"))
        rechercher = QPushButton(tr("Filtrer"))
        rechercher.clicked.connect(lambda: self.charger(1))
        nouvelle = QPushButton(tr("Nouvelle plainte"))
        nouvelle.setObjectName("boutonPrincipal")
        nouvelle.setEnabled(session.a("plainte.creer"))
        nouvelle.clicked.connect(self.creer)
        # Deux lignes : la page reste lisible a la largeur minimale de la fenetre.
        filtres.addWidget(self.numero, 2)
        filtres.addWidget(self.statut, 1)
        filtres.addWidget(self.categorie, 1)
        actions = QHBoxLayout()
        actions.addWidget(self.du)
        actions.addWidget(self.au)
        actions.addWidget(rechercher)
        actions.addStretch()
        actions.addWidget(nouvelle)
        self.couche.addLayout(filtres)
        self.couche.addLayout(actions)
        self.tableau = TableauDonnees(COLONNES_PLAINTES)
        self.tableau.ligne_activee.connect(lambda p: self.ouvrir(p["id"]))
        self.tableau.page_demandee.connect(self.charger)
        self.couche.addWidget(self.tableau, 1)

    def charger(self, page: int = 1) -> None:
        if self.categorie.count() == 1:
            try:
                self.categorie.remplir(
                    {c["id"]: c["libelle"] for c in self.session.categories()}, tr("Toutes les catégories")
                )
            except ErreurAPI:
                pass
        params = {
            "numero": self.numero.text().strip(),
            "statut": self.statut.valeur(),
            "categorie_id": self.categorie.valeur(),
            "du": self.du.valeur(),
            "au": self.au.valeur(),
            "page": page,
            "taille": 50,
        }
        self.executer(lambda: self.api.get("/plaintes", params), self.tableau.definir_page)

    def creer(self) -> None:
        formulaire = FormulairePlainte(self.session, self)
        if formulaire.exec() == QDialog.Accepted and formulaire.resultat:
            QMessageBox.information(
                self,
                tr("Plainte enregistrée"),
                tr("Plainte enregistrée sous le numéro {numero}.", numero=formulaire.resultat["numero"]),
            )
            self.charger(1)

    def ouvrir(self, plainte_id: str) -> None:
        DialoguePlainte(self.session, plainte_id, self).exec()
        self.charger(self.tableau.page)
