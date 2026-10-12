"""Faits signales, infractions, dossiers et procedures."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from tpgis.client.windows.plaintes import OngletPieces
from tpgis.shared.geographie import provinces
from tpgis.shared.i18n import tr

COLONNES_FAITS = [
    ("reference", "Référence", None),
    ("categorie", "Catégorie", lambda v, _: tr(v) if v else ""),
    ("date_declaree", "Date déclarée", lambda v, _: fmt_date(v)),
    ("nature_information", "Nature de l'information", lambda v, _: L.libelle(L.NATURE_INFORMATION, v)),
    ("etat_verification", "Vérification", lambda v, _: L.libelle(L.ETAT_VERIFICATION, v)),
    ("source_information", "Source", lambda v, _: L.libelle(L.SOURCE_INFORMATION, v)),
    ("unite_nom", "Unité", None),
]

COLONNES_DOSSIERS = [
    ("numero", "Numéro", None),
    ("intitule", "Intitulé", None),
    ("type_procedure", "Procédure", lambda v, _: L.libelle(L.TYPE_PROCEDURE, v)),
    ("statut", "Statut", lambda v, _: L.libelle(L.STATUT_DOSSIER, v)),
    ("date_ouverture", "Ouverture", lambda v, _: fmt_date(v)),
    ("enqueteur", "Enquêteur", None),
    ("unite_nom", "Unité", None),
]


def _historique() -> TableauDonnees:
    return TableauDonnees(
        [
            ("modifie_le", tr("Date"), lambda v, _: fmt_date(v)),
            ("modifie_par", tr("Par"), None),
            ("action", tr("Action"), None),
            ("changements", tr("Détails"), lambda v, _: str(v or "")),
        ],
        pagine=False,
    )


class FormulaireFait(FormulaireDialogue):
    def __init__(self, session, parent=None, existant: dict | None = None):
        super().__init__(tr("Modifier le fait") if existant else tr("Enregistrer un fait signalé"), parent, 640)
        self.session, self.existant = session, existant
        self.categorie = self.ajouter(
            tr("Catégorie"), Choix({c["id"]: c["libelle"] for c in session.categories()}), True
        )
        self.date = self.ajouter(tr("Date déclarée"), ChampDate())
        self.lieu = self.ajouter(tr("Lieu"), QLineEdit())
        self.province = self.ajouter(tr("Province"), Choix(provinces(), tr("Province de l'unité")))
        self.description = self.ajouter(tr("Description"), QPlainTextEdit(), True)
        self.description.setMinimumHeight(100)
        if not existant:
            self.source = self.ajouter(tr("Source de l'information"), Choix(L.SOURCE_INFORMATION))
        self.nature = self.ajouter(tr("Nature de l'information"), Choix(L.NATURE_INFORMATION))
        self.etat = self.ajouter(tr("État de vérification"), Choix(L.ETAT_VERIFICATION))
        self.references = self.ajouter(tr("Références des actes"), QLineEdit())
        note = QLabel(
            tr(
                "Distinguer strictement faits rapportés, faits vérifiés, soupçons et décisions judiciaires. "
                "Une décision judiciaire doit citer la référence de l'acte de la juridiction."
            )
        )
        note.setWordWrap(True)
        note.setObjectName("sousTitrePage")
        self.formulaire.addRow(note)
        if existant:
            self.categorie.choisir(existant["categorie_id"])
            self.date.definir(existant.get("date_declaree"))
            self.lieu.setText(existant.get("lieu") or "")
            self.province.choisir(existant.get("province_code"))
            self.description.setPlainText(existant.get("description") or "")
            self.nature.choisir(existant["nature_information"])
            self.etat.choisir(existant["etat_verification"])
            self.references.setText(existant.get("references_actes") or "")
        self.action = self._enregistrer

    def _enregistrer(self):
        donnees = {
            "categorie_id": self.categorie.valeur(),
            "date_declaree": self.date.valeur(),
            "lieu": texte_ou_none(self.lieu),
            "province_code": self.province.valeur(),
            "description": self.description.toPlainText().strip(),
            "nature_information": self.nature.valeur(),
            "etat_verification": self.etat.valeur(),
            "references_actes": texte_ou_none(self.references),
        }
        if self.existant:
            return self.session.api.patch(
                f"/faits/{self.existant['id']}", {**donnees, "version": self.existant["version"]}
            )
        return self.session.api.post("/faits", {**donnees, "source_information": self.source.valeur()})


class DialogueFait(QDialog):
    def __init__(self, session, fait_id: str, parent=None):
        super().__init__(parent)
        self.session, self.ident = session, fait_id
        self.setWindowTitle(tr("Fait signalé"))
        self.setMinimumSize(820, 520)
        couche = QVBoxLayout(self)
        self.titre = QLabel("")
        self.titre.setObjectName("titrePage")
        couche.addWidget(self.titre)
        self.onglets = QTabWidget()
        couche.addWidget(self.onglets, 1)
        boutons = QHBoxLayout()
        modifier = QPushButton(tr("Modifier"))
        modifier.setEnabled(session.a("fait.modifier"))
        modifier.clicked.connect(self.modifier)
        associer = QPushButton(tr("Associer une personne"))
        associer.setEnabled(session.a("fait.modifier") and session.a("personne.lire"))
        associer.clicked.connect(self.associer)
        fermer = QPushButton(tr("Fermer"))
        fermer.clicked.connect(self.accept)
        boutons.addWidget(modifier)
        boutons.addWidget(associer)
        boutons.addStretch()
        boutons.addWidget(fermer)
        couche.addLayout(boutons)
        self.recharger()

    def recharger(self) -> None:
        try:
            self.f = self.session.api.get(f"/faits/{self.ident}")
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        f = self.f
        self.titre.setText(
            tr(
                "Fait {reference}  |  {libelle}",
                reference=f["reference"],
                libelle=L.libelle(L.NATURE_INFORMATION, f["nature_information"]),
            )
        )
        self.onglets.clear()
        infos = QWidget()
        formulaire = QFormLayout(infos)
        for libelle, valeur in [
            (tr("Catégorie"), tr(f["categorie"])),
            (tr("Date déclarée"), fmt_date(f.get("date_declaree"))),
            (tr("Lieu"), f.get("lieu")),
            (tr("Province"), provinces().get(f.get("province_code") or "", "")),
            (tr("Source"), L.libelle(L.SOURCE_INFORMATION, f["source_information"])),
            (tr("Nature"), L.libelle(L.NATURE_INFORMATION, f["nature_information"])),
            (tr("Vérification"), L.libelle(L.ETAT_VERIFICATION, f["etat_verification"])),
            (tr("Description"), f["description"]),
            (tr("Références des actes"), f.get("references_actes")),
            (tr("Unité"), f["unite_nom"]),
        ]:
            champ = QLabel(valeur or "")
            champ.setWordWrap(True)
            formulaire.addRow(libelle, champ)
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
        personnes.definir_lignes(f["personnes"])
        self.onglets.addTab(personnes, tr("Personnes concernées"))
        historique = _historique()
        historique.definir_lignes(f["historique"])
        self.onglets.addTab(historique, tr("Historique"))

    def modifier(self) -> None:
        if FormulaireFait(self.session, self, self.f).exec() == QDialog.Accepted:
            self.recharger()

    def associer(self) -> None:
        dialogue = DialogueSelectionPersonne(self.session, self)
        if dialogue.exec() == QDialog.Accepted and dialogue.personne:
            try:
                self.session.api.post(
                    f"/faits/{self.ident}/personnes",
                    {"personne_id": dialogue.personne["id"], "role": dialogue.role_choisi()},
                )
            except ErreurAPI as exc:
                afficher_erreur(self, exc)
            self.recharger()


class PageFaits(Page):
    titre = "Infractions et faits signalés"
    sous_titre = (
        "Référentiel des faits rapportés, vérifiés ou soupçonnés. Aucune qualification automatique de "
        "culpabilité ni aucun score individuel n'est calculé."
    )

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        barre = QHBoxLayout()
        self.categorie = Choix({}, tr("Toutes les catégories"))
        self.nature = Choix(L.NATURE_INFORMATION, tr("Toutes natures"))
        self.etat = Choix(L.ETAT_VERIFICATION, tr("Tous états"))
        filtrer = QPushButton(tr("Filtrer"))
        filtrer.clicked.connect(lambda: self.charger(1))
        nouveau = QPushButton(tr("Nouveau fait"))
        nouveau.setObjectName("boutonPrincipal")
        nouveau.setEnabled(session.a("fait.creer"))
        nouveau.clicked.connect(self.creer)
        for liste in (self.categorie, self.nature, self.etat):
            liste.setMinimumContentsLength(8)
            barre.addWidget(liste, 1)
        barre.addWidget(filtrer)
        # Action principale a droite du titre, comme sur les autres pages.
        self.entete.addWidget(nouveau, 0, Qt.AlignTop)
        self.couche.addLayout(barre)
        self.tableau = TableauDonnees(COLONNES_FAITS)
        self.tableau.ligne_activee.connect(
            lambda f: (DialogueFait(self.session, f["id"], self).exec(), self.charger(self.tableau.page))
        )
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
            "categorie_id": self.categorie.valeur(),
            "nature": self.nature.valeur(),
            "etat": self.etat.valeur(),
            "page": page,
            "taille": 50,
        }
        self.executer(lambda: self.api.get("/faits", params), self.tableau.definir_page)

    def creer(self) -> None:
        if FormulaireFait(self.session, self).exec() == QDialog.Accepted:
            self.charger(1)


class FormulaireDossier(FormulaireDialogue):
    def __init__(self, session, parent=None, existant: dict | None = None):
        super().__init__(tr("Modifier le dossier") if existant else tr("Ouvrir un dossier"), parent, 620)
        self.session, self.existant = session, existant
        self.intitule = self.ajouter(tr("Intitulé"), QLineEdit(), True)
        self.procedure = self.ajouter(tr("Type de procédure"), Choix(L.TYPE_PROCEDURE))
        agents = {}
        try:
            unite = existant["unite_id"] if existant else session.moi["unite_id"]
            agents = {a["id"]: a["nom_complet"] for a in session.api.get(f"/unites/{unite}/agents")}
        except ErreurAPI:
            pass
        self.enqueteur = self.ajouter(tr("Enquêteur désigné"), Choix(agents, tr("Non désigné")))
        self.juridiction = self.ajouter(tr("Juridiction"), QLineEdit())
        self.observations = self.ajouter(tr("Observations"), QPlainTextEdit())
        self.observations.setMaximumHeight(80)
        if existant:
            self.statut = self.ajouter(tr("Statut"), Choix(L.STATUT_DOSSIER))
            self.motif = self.ajouter(tr("Motif (clôture, archivage, réouverture)"), QLineEdit())
            self.intitule.setText(existant["intitule"])
            self.procedure.choisir(existant["type_procedure"])
            self.enqueteur.choisir(existant.get("enqueteur_id"))
            self.juridiction.setText(existant.get("juridiction") or "")
            self.observations.setPlainText(existant.get("observations") or "")
            self.statut.choisir(existant["statut"])
        else:
            self.plaintes = self.ajouter(tr("Plaintes à rattacher (numéros)"), QLineEdit())
            self.plaintes.setPlaceholderText(tr("PL-...; séparés par des points-virgules"))
        self.action = self._enregistrer

    def _enregistrer(self):
        api = self.session.api
        donnees = {
            "intitule": self.intitule.text().strip(),
            "type_procedure": self.procedure.valeur(),
            "enqueteur_id": self.enqueteur.valeur(),
            "juridiction": texte_ou_none(self.juridiction),
            "observations": texte_ou_none(self.observations),
        }
        if self.existant:
            if self.statut.valeur() != self.existant["statut"]:
                donnees["statut"] = self.statut.valeur()
                donnees["motif_cloture"] = texte_ou_none(self.motif)
            if self.enqueteur.valeur() == self.existant.get("enqueteur_id"):
                donnees.pop("enqueteur_id")
            return api.patch(f"/dossiers/{self.existant['id']}", {**donnees, "version": self.existant["version"]})
        ids = []
        for numero in filter(None, (n.strip() for n in self.plaintes.text().split(";"))):
            trouvees = api.get("/plaintes", {"numero": numero, "taille": 2})["elements"]
            exactes = [p for p in trouvees if p["numero"] == numero.upper()]
            if not exactes:
                raise ValueError(tr("Plainte {numero} introuvable dans votre périmètre.", numero=numero))
            ids.append(exactes[0]["id"])
        return api.post("/dossiers", {**donnees, "plaintes_ids": ids})


class DialogueDossier(QDialog):
    def __init__(self, session, dossier_id: str, parent=None):
        super().__init__(parent)
        self.session, self.ident, self.api = session, dossier_id, session.api
        self.setWindowTitle(tr("Dossier et procédure"))
        self.setMinimumSize(920, 600)
        couche = QVBoxLayout(self)
        self.titre = QLabel("")
        self.titre.setObjectName("titrePage")
        couche.addWidget(self.titre)
        self.onglets = QTabWidget()
        couche.addWidget(self.onglets, 1)
        boutons = QHBoxLayout()
        actions = [
            (tr("Modifier"), self.modifier, session.a("dossier.modifier")),
            (tr("Ajouter un acte"), self.ajouter_acte, session.a("dossier.modifier")),
            (tr("Associer une personne"), self.associer, session.a("dossier.modifier") and session.a("personne.lire")),
            (tr("Rattacher une plainte"), self.rattacher, session.a("dossier.modifier")),
        ]
        for texte, rappel, actif in actions:
            b = QPushButton(texte)
            b.setEnabled(actif)
            b.clicked.connect(rappel)
            boutons.addWidget(b)
        boutons.addStretch()
        fermer = QPushButton(tr("Fermer"))
        fermer.clicked.connect(self.accept)
        boutons.addWidget(fermer)
        couche.addLayout(boutons)
        self.recharger()

    def recharger(self) -> None:
        try:
            self.d = self.api.get(f"/dossiers/{self.ident}")
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        d = self.d
        self.titre.setText(
            tr("Dossier {numero}  |  {libelle}", numero=d["numero"], libelle=L.libelle(L.STATUT_DOSSIER, d["statut"]))
        )
        self.onglets.clear()
        infos = QWidget()
        formulaire = QFormLayout(infos)
        for libelle, valeur in [
            (tr("Intitulé"), d["intitule"]),
            (tr("Procédure"), L.libelle(L.TYPE_PROCEDURE, d["type_procedure"])),
            (tr("Unité"), d["unite_nom"]),
            (tr("Enquêteur"), d.get("enqueteur")),
            (tr("Ouverture"), fmt_date(d["date_ouverture"])),
            (tr("Clôture"), fmt_date(d.get("date_cloture"))),
            (tr("Motif de clôture"), d.get("motif_cloture")),
            (tr("Juridiction"), d.get("juridiction")),
            (tr("Observations"), d.get("observations")),
        ]:
            champ = QLabel(valeur or "")
            champ.setWordWrap(True)
            formulaire.addRow(libelle, champ)
        self.onglets.addTab(infos, tr("Informations"))
        actes = TableauDonnees(
            [
                ("date_acte", tr("Date"), lambda v, _: fmt_date(v)),
                ("type_acte", tr("Type"), lambda v, _: L.libelle(L.TYPE_ACTE, v)),
                ("reference", tr("Référence"), None),
                ("resume", tr("Résumé"), None),
            ],
            pagine=False,
        )
        actes.definir_lignes(d["actes"])
        self.onglets.addTab(actes, tr("Actes de procédure ({len})", len=len(d["actes"])))
        plaintes = TableauDonnees(
            [
                ("numero", tr("Plainte"), None),
                ("recue_le", tr("Reçue le"), lambda v, _: fmt_date(v)),
                ("statut", tr("Statut"), lambda v, _: L.libelle(L.STATUT_PLAINTE, v)),
            ],
            pagine=False,
        )
        plaintes.definir_lignes(d["plaintes"])
        self.onglets.addTab(plaintes, tr("Plaintes rattachées"))
        personnes = TableauDonnees(
            [
                ("numero_interne", tr("N° interne"), None),
                ("nom", tr("Nom"), None),
                ("prenoms", tr("Prénoms"), None),
                ("role", tr("Rôle procédural"), lambda v, _: L.libelle(L.ROLE_PERSONNE, v)),
            ],
            pagine=False,
        )
        personnes.definir_lignes(d["personnes"])
        self.onglets.addTab(personnes, tr("Personnes"))
        faits = TableauDonnees(
            [
                ("reference", tr("Fait"), None),
                ("categorie", tr("Catégorie"), lambda v, _: tr(v) if v else ""),
                ("nature_information", tr("Nature"), lambda v, _: L.libelle(L.NATURE_INFORMATION, v)),
            ],
            pagine=False,
        )
        faits.definir_lignes(d["faits"])
        self.onglets.addTab(faits, tr("Faits"))
        if self.session.a("document.lire"):
            self.onglets.addTab(OngletPieces(self.session, "dossier_id", self.ident, self), tr("Pièces"))
        historique = _historique()
        historique.definir_lignes(d["historique"])
        self.onglets.addTab(historique, tr("Historique"))

    def modifier(self) -> None:
        if FormulaireDossier(self.session, self, self.d).exec() == QDialog.Accepted:
            self.recharger()

    def ajouter_acte(self) -> None:
        formulaire = FormulaireDialogue(tr("Ajouter un acte de procédure"), self)
        type_acte = formulaire.ajouter(tr("Type d'acte"), Choix(L.TYPE_ACTE))
        reference = formulaire.ajouter(tr("Référence"), QLineEdit(), True)
        date_acte = formulaire.ajouter(tr("Date de l'acte"), ChampDate())
        date_acte.connue.setChecked(True)
        resume = formulaire.ajouter(tr("Résumé"), QPlainTextEdit())
        formulaire.action = lambda: self.api.post(
            f"/dossiers/{self.ident}/actes",
            {
                "type_acte": type_acte.valeur(),
                "reference": reference.text().strip(),
                "date_acte": date_acte.valeur(),
                "resume": texte_ou_none(resume),
            },
        )
        if formulaire.exec() == QDialog.Accepted:
            self.recharger()

    def associer(self) -> None:
        dialogue = DialogueSelectionPersonne(self.session, self)
        if dialogue.exec() == QDialog.Accepted and dialogue.personne:
            try:
                self.api.post(
                    f"/dossiers/{self.ident}/personnes",
                    {"personne_id": dialogue.personne["id"], "role": dialogue.role_choisi()},
                )
            except ErreurAPI as exc:
                afficher_erreur(self, exc)
            self.recharger()

    def rattacher(self) -> None:
        formulaire = FormulaireDialogue(tr("Rattacher une plainte"), self)
        numero = formulaire.ajouter(tr("Numéro de plainte"), QLineEdit(), True)

        def _action():
            trouvees = self.api.get("/plaintes", {"numero": numero.text().strip(), "taille": 2})["elements"]
            exactes = [p for p in trouvees if p["numero"] == numero.text().strip().upper()]
            if not exactes:
                raise ValueError(tr("Plainte introuvable dans votre périmètre."))
            return self.api.post(f"/dossiers/{self.ident}/plaintes", {"plainte_id": exactes[0]["id"]})

        formulaire.action = _action
        if formulaire.exec() == QDialog.Accepted:
            self.recharger()


class PageDossiers(Page):
    titre = "Dossiers et procédures"
    sous_titre = "Suivi des procédures, des actes et des pièces. Les enquêteurs ne voient que leurs dossiers."

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        barre = QHBoxLayout()
        self.numero = QLineEdit()
        self.numero.setPlaceholderText(tr("Numéro de dossier"))
        self.numero.returnPressed.connect(lambda: self.charger(1))
        self.statut = Choix(L.STATUT_DOSSIER, tr("Tous les statuts"))
        filtrer = QPushButton(tr("Filtrer"))
        filtrer.clicked.connect(lambda: self.charger(1))
        nouveau = QPushButton(tr("Ouvrir un dossier"))
        nouveau.setObjectName("boutonPrincipal")
        nouveau.setEnabled(session.a("dossier.creer"))
        nouveau.clicked.connect(self.creer)
        barre.addWidget(self.numero, 1)
        for w in (self.statut, filtrer, nouveau):
            barre.addWidget(w)
        self.couche.addLayout(barre)
        self.tableau = TableauDonnees(COLONNES_DOSSIERS)
        self.tableau.ligne_activee.connect(
            lambda d: (DialogueDossier(self.session, d["id"], self).exec(), self.charger(self.tableau.page))
        )
        self.tableau.page_demandee.connect(self.charger)
        self.couche.addWidget(self.tableau, 1)

    def charger(self, page: int = 1) -> None:
        params = {"numero": self.numero.text().strip(), "statut": self.statut.valeur(), "page": page, "taille": 50}
        self.executer(lambda: self.api.get("/dossiers", params), self.tableau.definir_page)

    def creer(self) -> None:
        if FormulaireDossier(self.session, self).exec() == QDialog.Accepted:
            self.charger(1)
