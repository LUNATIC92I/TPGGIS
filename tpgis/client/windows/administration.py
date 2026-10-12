"""Unites, utilisateurs et habilitations, journal d'audit, parametres et administration."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from tpgis.client.windows.connexion import DialogueChangementMotDePasse, avec_reauthentification
from tpgis.shared.geographie import provinces
from tpgis.shared.i18n import tr


class PageUnites(Page):
    titre = "Unités et commissariats"
    sous_titre = "Référentiel des commissariats, brigades et services de la Police et de la Gendarmerie."

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        barre = QHBoxLayout()
        nouvelle = QPushButton(tr("Nouvelle unité"))
        nouvelle.setObjectName("boutonPrincipal")
        nouvelle.setEnabled(session.a("unite.gerer"))
        nouvelle.clicked.connect(lambda: self.editer(None))
        modifier = QPushButton(tr("Modifier"))
        modifier.setEnabled(session.a("unite.gerer"))
        modifier.clicked.connect(lambda: self.editer(self.tableau.selection()))
        barre.addStretch()
        barre.addWidget(nouvelle)
        barre.addWidget(modifier)
        self.couche.addLayout(barre)
        noms_provinces = provinces()
        self.tableau = TableauDonnees(
            [
                ("code", tr("Code"), None),
                ("nom", tr("Nom"), None),
                ("corps", tr("Corps"), lambda v, _: L.libelle(L.CORPS, v)),
                ("type_unite", tr("Type"), lambda v, _: L.libelle(L.TYPE_UNITE, v)),
                ("province_code", tr("Province"), lambda v, _: noms_provinces.get(v or "", v or "")),
                ("ville", tr("Ville"), None),
                ("active", tr("Active"), None),
            ],
            pagine=False,
        )
        self.tableau.ligne_activee.connect(lambda u: session.a("unite.gerer") and self.editer(u))
        self.couche.addWidget(self.tableau, 1)

    def charger(self) -> None:
        self.session.invalider_caches()
        self.executer(lambda: self.api.get("/unites"), self.tableau.definir_lignes)

    def editer(self, unite: dict | None) -> None:
        f = FormulaireDialogue(tr("Modifier l'unité") if unite else tr("Nouvelle unité"), self)
        code = f.ajouter(tr("Code"), QLineEdit(unite["code"] if unite else ""), True)
        code.setEnabled(unite is None)
        nom = f.ajouter(tr("Nom"), QLineEdit(unite["nom"] if unite else ""), True)
        type_unite = f.ajouter(tr("Type"), Choix(L.TYPE_UNITE))
        corps = f.ajouter(tr("Corps"), Choix(L.CORPS))
        parents = {u["id"]: u["nom"] for u in self.tableau.modele.lignes if not unite or u["id"] != unite["id"]}
        parent = f.ajouter(tr("Unité de rattachement"), Choix(parents, tr("Aucune")))
        province = f.ajouter(tr("Province"), Choix(provinces(), tr("Non renseignée")))
        ville = f.ajouter(tr("Ville"), QLineEdit(unite.get("ville") or "" if unite else ""))
        lat, lon = QDoubleSpinBox(), QDoubleSpinBox()
        lat.setRange(7.0, 24.0)
        lon.setRange(13.0, 24.5)
        for champ in (lat, lon):
            champ.setDecimals(4)
        f.ajouter(tr("Latitude"), lat)
        f.ajouter(tr("Longitude"), lon)
        active = f.ajouter(tr("Active"), QCheckBox())
        active.setChecked(unite["active"] if unite else True)
        if unite:
            type_unite.choisir(unite["type_unite"])
            corps.choisir(unite["corps"])
            type_unite.setEnabled(False)
            corps.setEnabled(False)
            parent.choisir(unite.get("parent_id"))
            province.choisir(unite.get("province_code"))
            lat.setValue(unite.get("latitude") or 12.1)
            lon.setValue(unite.get("longitude") or 15.0)
        else:
            lat.setValue(12.1)
            lon.setValue(15.0)

        def _action():
            donnees = {
                "nom": nom.text().strip(),
                "parent_id": parent.valeur(),
                "province_code": province.valeur(),
                "ville": texte_ou_none(ville),
                "latitude": lat.value(),
                "longitude": lon.value(),
            }
            if unite:
                return self.api.patch(f"/unites/{unite['id']}", {**donnees, "active": active.isChecked()})
            return self.api.post(
                "/unites",
                {
                    **donnees,
                    "code": code.text().strip().upper(),
                    "type_unite": type_unite.valeur(),
                    "corps": corps.valeur(),
                },
            )

        f.action = _action
        if f.exec() == QDialog.Accepted:
            self.charger()


class PageUtilisateurs(Page):
    titre = "Utilisateurs et habilitations"
    sous_titre = (
        "Comptes, rôles et périmètres. L'attribution d'un rôle privilégié est soumise à double "
        "validation ; les opérations sensibles exigent une confirmation d'identité."
    )

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self.onglets = QTabWidget()
        self.couche.addWidget(self.onglets, 1)
        comptes = QWidget()
        c = QVBoxLayout(comptes)
        barre = QHBoxLayout()
        self.texte = QLineEdit()
        self.texte.setPlaceholderText(tr("Identifiant, nom ou matricule"))
        self.texte.returnPressed.connect(lambda: self.charger(1))
        barre.addWidget(self.texte, 1)
        gerer = session.a("utilisateur.gerer")

        def bouton(libelle, rappel, actif=True, nom_objet=None):
            b = QPushButton(libelle)
            b.clicked.connect(rappel)
            b.setEnabled(actif)
            if nom_objet:
                b.setObjectName(nom_objet)
            return b

        barre.addWidget(bouton(tr("Rechercher"), lambda: self.charger(1)))
        barre.addWidget(bouton(tr("Nouveau compte"), self.creer, gerer, "boutonPrincipal"))
        c.addLayout(barre)
        # Actions sur le compte selectionne, sur deux colonnes pour rester lisibles
        # a la largeur minimale de la fenetre.
        actions = QGridLayout()
        for indice, (libelle, rappel, nom_objet) in enumerate(
            (
                (tr("Changer le rôle"), self.changer_role, None),
                (tr("Révoquer les sessions"), self.revoquer, None),
                (tr("Réinitialiser le mot de passe"), self.reinitialiser, None),
                (tr("Réactiver"), self.reactiver, None),
                (tr("Réinitialiser la MFA"), self.reinitialiser_mfa, None),
                (tr("Désactiver"), self.desactiver, "boutonDanger"),
            )
        ):
            actions.addWidget(bouton(libelle, rappel, gerer, nom_objet), indice // 2, indice % 2)
        c.addLayout(actions)
        self.tableau = TableauDonnees(
            [
                ("identifiant", tr("Identifiant"), None),
                ("nom", tr("Nom"), None),
                ("prenoms", tr("Prénoms"), None),
                ("grade", tr("Grade"), None),
                ("unite_nom", tr("Unité"), None),
                ("role_libelle", tr("Rôle"), lambda v, _: tr(v)),
                ("portee", tr("Périmètre"), lambda v, _: L.libelle(L.PORTEE, v)),
                ("actif", tr("Actif"), None),
                ("mfa_active", "MFA", None),
                ("derniere_connexion", tr("Dernière connexion"), lambda v, _: fmt_date(v)),
            ]
        )
        self.tableau.page_demandee.connect(self.charger)
        c.addWidget(self.tableau, 1)
        self.onglets.addTab(comptes, tr("Comptes"))
        self.roles = TableauDonnees(
            [
                ("libelle", tr("Rôle"), None),
                ("code", tr("Code"), None),
                ("portee_defaut", tr("Périmètre par défaut"), lambda v, _: L.libelle(L.PORTEE, v)),
                ("privilegie", tr("Privilégié (MFA)"), None),
                ("actif", tr("Actif"), None),
                ("permissions", tr("Permissions"), lambda v, _: str(len(v))),
            ],
            pagine=False,
        )
        self.roles.ligne_activee.connect(self.editer_role)
        conteneur = QWidget()
        r = QVBoxLayout(conteneur)
        r.addWidget(self.roles, 1)
        ligne = QHBoxLayout()
        nouveau = QPushButton(tr("Nouveau rôle"))
        nouveau.setEnabled(session.a("role.gerer"))
        nouveau.clicked.connect(lambda: self.editer_role(None))
        ligne.addWidget(QLabel(tr("Double-cliquez sur un rôle pour consulter ou modifier ses permissions.")))
        ligne.addStretch()
        ligne.addWidget(nouveau)
        r.addLayout(ligne)
        self.onglets.addTab(conteneur, tr("Rôles et permissions"))

    def charger(self, page: int = 1) -> None:
        params = {"texte": self.texte.text().strip(), "page": page, "taille": 50}
        self.executer(lambda: self.api.get("/utilisateurs", params), self.tableau.definir_page)
        self.executer(lambda: self.api.get("/roles"), self.roles.definir_lignes)

    def _cible(self) -> dict | None:
        u = self.tableau.selection()
        if not u:
            QMessageBox.information(self, tr("Utilisateurs"), tr("Sélectionnez d'abord un compte."))
        return u

    def creer(self) -> None:
        f = FormulaireDialogue(tr("Nouveau compte utilisateur"), self)
        ident = f.ajouter(tr("Identifiant"), QLineEdit(), True)
        nom, prenoms = f.ajouter(tr("Nom"), QLineEdit(), True), f.ajouter(tr("Prénoms"), QLineEdit(), True)
        matricule, grade = f.ajouter(tr("Matricule"), QLineEdit()), f.ajouter(tr("Grade"), QLineEdit())
        unite = f.ajouter(tr("Unité"), Choix({u["id"]: u["nom"] for u in self.session.unites()}))
        roles = {r["id"]: tr(r["libelle"]) for r in self.roles.modele.lignes if not r["privilegie"] and r["actif"]}
        role = f.ajouter(tr("Rôle (non privilégié)"), Choix(roles))
        mdp = f.ajouter(tr("Mot de passe initial"), QLineEdit(), True)
        mdp.setEchoMode(QLineEdit.Password)
        note = QLabel(
            tr(
                "Le mot de passe devra être changé à la première connexion. Les rôles privilégiés s'attribuent "
                "ensuite par une demande soumise à double validation."
            )
        )
        note.setWordWrap(True)
        note.setObjectName("sousTitrePage")
        f.formulaire.addRow(note)
        f.action = lambda: self.api.post(
            "/utilisateurs",
            {
                "identifiant": ident.text().strip().lower(),
                "nom": nom.text().strip(),
                "prenoms": prenoms.text().strip(),
                "matricule": texte_ou_none(matricule),
                "grade": texte_ou_none(grade),
                "unite_id": unite.valeur(),
                "role_id": role.valeur(),
                "mot_de_passe_initial": mdp.text(),
            },
        )
        if f.exec() == QDialog.Accepted:
            self.charger(1)

    def changer_role(self) -> None:
        u = self._cible()
        if not u:
            return
        f = FormulaireDialogue(tr("Changer le rôle de {identifiant}", identifiant=u["identifiant"]), self)
        role = f.ajouter(
            tr("Nouveau rôle"),
            Choix(
                {
                    r["id"]: tr(r["libelle"]) + (tr(" (privilégié)") if r["privilegie"] else "")
                    for r in self.roles.modele.lignes
                    if r["actif"]
                }
            ),
        )
        motif = f.ajouter(tr("Motif"), QPlainTextEdit(), True)
        f.action = lambda: self.api.post(
            f"/utilisateurs/{u['id']}/role", {"role_id": role.valeur(), "motif": motif.toPlainText().strip()}
        )
        if f.exec() == QDialog.Accepted:
            if f.resultat.get("statut") == "EN_ATTENTE":
                QMessageBox.information(
                    self,
                    tr("Double validation"),
                    tr("Le rôle demandé est privilégié : la demande doit être approuvée par un second responsable."),
                )
            self.charger(self.tableau.page)

    def desactiver(self) -> None:
        u = self._cible()
        if u and confirmer(
            self,
            tr("Désactivation"),
            tr(
                "Désactiver immédiatement le compte {identifiant} ?\nToutes ses sessions seront révoquées.",
                identifiant=u["identifiant"],
            ),
        ):
            motif = demander_motif(self, tr("Motif de désactivation"), tr("Motif :"))
            if motif and self.appel_direct(
                lambda: self.api.post(f"/utilisateurs/{u['id']}/desactivation", {"motif": motif})
            ):
                self.charger(self.tableau.page)

    def reactiver(self) -> None:
        u = self._cible()
        motif = demander_motif(self, tr("Réactivation"), tr("Motif de la réactivation :")) if u else None
        if motif and self.appel_direct(
            lambda: self.api.post(f"/utilisateurs/{u['id']}/reactivation", {"motif": motif})
        ):
            self.charger(self.tableau.page)

    def revoquer(self) -> None:
        u = self._cible()
        if u and confirmer(
            self, tr("Révocation"), tr("Fermer toutes les sessions de {identifiant} ?", identifiant=u["identifiant"])
        ):
            r = self.appel_direct(lambda: self.api.post(f"/utilisateurs/{u['id']}/revocation-sessions"))
            if r:
                QMessageBox.information(
                    self,
                    tr("Révocation"),
                    tr("{sessions_revoquees} session(s) révoquée(s).", sessions_revoquees=r["sessions_revoquees"]),
                )

    def reinitialiser(self) -> None:
        u = self._cible()
        if not u:
            return
        f = FormulaireDialogue(tr("Réinitialiser le mot de passe de {identifiant}", identifiant=u["identifiant"]), self)
        mdp = f.ajouter(tr("Mot de passe temporaire"), QLineEdit(), True)
        mdp.setEchoMode(QLineEdit.Password)
        motif = f.ajouter(tr("Motif"), QLineEdit(), True)
        f.action = lambda: avec_reauthentification(
            self,
            self.session,
            lambda: self.api.post(
                f"/utilisateurs/{u['id']}/reinitialisation-mot-de-passe",
                {"mot_de_passe_temporaire": mdp.text(), "motif": motif.text().strip()},
            ),
        )
        f.exec()

    def reinitialiser_mfa(self) -> None:
        u = self._cible()
        motif = demander_motif(self, tr("Réinitialisation MFA"), tr("Motif (perte du terminal, etc.) :")) if u else None
        if motif:
            try:
                avec_reauthentification(
                    self,
                    self.session,
                    lambda: self.api.post(f"/utilisateurs/{u['id']}/reinitialisation-mfa", {"motif": motif}),
                )
            except ErreurAPI as exc:
                afficher_erreur(self, exc)

    def editer_role(self, role: dict | None) -> None:
        try:
            catalogue = self.api.get("/permissions") if self.session.a("role.gerer") else []
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        f = FormulaireDialogue(tr("Rôle") if role else tr("Nouveau rôle"), self, 640)
        code = f.ajouter(tr("Code"), QLineEdit(role["code"] if role else ""), True)
        code.setEnabled(role is None)
        libelle = f.ajouter(tr("Libellé"), QLineEdit(role["libelle"] if role else ""), True)
        portee = f.ajouter(tr("Périmètre par défaut"), Choix(L.PORTEE))
        liste = QListWidget()
        liste.setMinimumHeight(260)
        actuelles = set(role["permissions"]) if role else set()
        for p in catalogue or [{"code": x, "libelle": x} for x in sorted(actuelles)]:
            item = QListWidgetItem(tr("{libelle}  ({code})", libelle=tr(p["libelle"]), code=p["code"]))
            item.setData(Qt.UserRole, p["code"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if p["code"] in actuelles else Qt.Unchecked)
            liste.addItem(item)
        f.ajouter(tr("Permissions"), liste)
        if role:
            portee.choisir(role["portee_defaut"])
        if not self.session.a("role.gerer"):
            f.boutons.button(f.boutons.Ok).setEnabled(False)

        def _action():
            permissions = [
                liste.item(i).data(Qt.UserRole)
                for i in range(liste.count())
                if liste.item(i).checkState() == Qt.Checked
            ]
            donnees = {"libelle": libelle.text().strip(), "portee_defaut": portee.valeur(), "permissions": permissions}
            if role:
                return avec_reauthentification(
                    self, self.session, lambda: self.api.patch(f"/roles/{role['id']}", donnees)
                )
            return self.api.post("/roles", {**donnees, "code": code.text().strip().upper()})

        f.action = _action
        if f.exec() == QDialog.Accepted:
            self.charger(self.tableau.page)


class PageAudit(Page):
    titre = "Journal d'audit"
    sous_titre = (
        "Connexions, consultations sensibles, créations, modifications, exports, refus d'accès et "
        "changements de droits. Journal chaîné par empreintes, non modifiable."
    )

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        barre = QHBoxLayout()
        self.identifiant, self.action, self.trace = QLineEdit(), QLineEdit(), QLineEdit()
        self.identifiant.setPlaceholderText(tr("Identifiant"))
        self.action.setPlaceholderText(tr("Action (ex. RECHERCHE)"))
        self.trace.setPlaceholderText(tr("Identifiant de trace"))
        self.resultat = Choix(
            {"SUCCES": tr("Succès"), "REFUS": tr("Refus"), "ECHEC": tr("Échec")}, tr("Tous résultats")
        )
        filtrer = QPushButton(tr("Filtrer"))
        filtrer.clicked.connect(lambda: self.charger(1))
        verifier = QPushButton(tr("Vérifier l'intégrité"))
        verifier.clicked.connect(self.verifier)
        for w in (self.identifiant, self.action, self.trace, self.resultat, filtrer, verifier):
            barre.addWidget(w)
        self.couche.addLayout(barre)
        self.tableau = TableauDonnees(
            [
                ("id", "N°", None),
                ("horodatage", tr("Horodatage"), lambda v, _: fmt_date(v)),
                ("identifiant", tr("Utilisateur"), None),
                ("action", tr("Action"), None),
                ("resultat", tr("Résultat"), None),
                ("type_ressource", tr("Ressource"), None),
                ("finalite", tr("Finalité"), None),
                ("adresse_ip", tr("Adresse"), None),
                ("trace_id", tr("Trace"), None),
                ("details", tr("Détails"), lambda v, _: json.dumps(v, ensure_ascii=False) if v else ""),
            ]
        )
        self.tableau.page_demandee.connect(self.charger)
        self.couche.addWidget(self.tableau, 1)

    def charger(self, page: int = 1) -> None:
        params = {
            "identifiant": self.identifiant.text().strip(),
            "action": self.action.text().strip().upper(),
            "trace_id": self.trace.text().strip(),
            "resultat": self.resultat.valeur(),
            "page": page,
            "taille": 100,
        }
        self.executer(lambda: self.api.get("/audit", params), self.tableau.definir_page)

    def verifier(self) -> None:
        r = self.appel_direct(lambda: self.api.get("/audit/verification"))
        if r is None:
            return
        if r["integre"]:
            QMessageBox.information(
                self,
                tr("Intégrité du journal"),
                tr(
                    "Chaîne intègre : {evenements_verifies} événements vérifiés.",
                    evenements_verifies=r["evenements_verifies"],
                ),
            )
        else:
            QMessageBox.critical(
                self,
                tr("Intégrité du journal"),
                tr(
                    "RUPTURE DÉTECTÉE à l'événement n° {rupture_a_id}. Déclencher la procédure de "
                    "réponse aux incidents.",
                    rupture_a_id=r["rupture_a_id"],
                ),
            )


class PageParametres(Page):
    titre = "Paramètres et administration"
    sous_titre = "Compte personnel, référentiels, double validation, conservation des données et supervision."

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self.onglets = QTabWidget()
        self.couche.addWidget(self.onglets, 1)
        self.onglets.addTab(self._onglet_compte(), tr("Mon compte"))
        # Chacun suit ses propres demandes ; les valideurs voient celles de leur perimetre.
        self.validations = TableauDonnees(
            [
                ("cree_le", tr("Demandée le"), lambda v, _: fmt_date(v)),
                ("type_action", tr("Type"), lambda v, _: L.libelle(L.TYPE_VALIDATION, v)),
                ("resume", tr("Objet"), None),
                ("motif", tr("Motif"), None),
                ("statut", tr("Statut"), lambda v, _: L.libelle(L.STATUT_VALIDATION, v)),
                ("resultat", tr("Résultat"), None),
            ]
        )
        conteneur = QWidget()
        v = QVBoxLayout(conteneur)
        v.addWidget(self.validations, 1)
        ligne = QHBoxLayout()
        for texte, approuver in ((tr("Approuver"), True), (tr("Rejeter"), False)):
            b = QPushButton(texte)
            b.setEnabled(session.a("validation.approuver"))
            b.clicked.connect(lambda _, a=approuver: self.decider(a))
            ligne.addWidget(b)
        ligne.addStretch()
        v.addLayout(ligne)
        self.validations.page_demandee.connect(self.charger_validations)
        self.onglets.addTab(conteneur, tr("Demandes de double validation"))
        if session.a("categorie.gerer"):
            self.categories = TableauDonnees(
                [
                    ("code", tr("Code"), None),
                    ("libelle", tr("Libellé"), None),
                    ("reference_legale", tr("Référence légale"), None),
                    ("validee", tr("Validée"), None),
                    ("validee_par", tr("Validée par"), None),
                    ("active", tr("Active"), None),
                ],
                pagine=False,
            )
            self.categories.ligne_activee.connect(self.editer_categorie)
            conteneur = QWidget()
            v = QVBoxLayout(conteneur)
            v.addWidget(self.categories, 1)
            b = QPushButton(tr("Nouvelle catégorie"))
            b.clicked.connect(lambda: self.editer_categorie(None))
            v.addWidget(b)
            self.onglets.addTab(conteneur, tr("Référentiel des faits"))
        if session.a("parametres.gerer"):
            self.parametres = TableauDonnees(
                [
                    ("cle", tr("Paramètre"), None),
                    ("description", tr("Description"), None),
                    ("valeur", tr("Valeur"), lambda v, _: json.dumps(v, ensure_ascii=False)),
                ],
                pagine=False,
            )
            self.parametres.ligne_activee.connect(self.editer_parametre)
            self.onglets.addTab(self.parametres, tr("Paramètres techniques"))
        if session.a("validation.approuver"):
            conteneur = QWidget()
            v = QVBoxLayout(conteneur)
            self.conservation = QLabel("")
            self.conservation.setWordWrap(True)
            self.conservation.setObjectName("panneau")
            self.conservation.setMargin(12)
            v.addWidget(self.conservation)
            b = QPushButton(tr("Demander la purge des données échues"))
            b.setObjectName("boutonDanger")
            b.clicked.connect(self.purge)
            v.addWidget(b)
            v.addStretch()
            self.onglets.addTab(conteneur, tr("Conservation des données"))
        if session.a("systeme.superviser"):
            self.supervision = QLabel("")
            self.supervision.setObjectName("panneau")
            self.supervision.setMargin(12)
            self.supervision.setAlignment(Qt.AlignTop)
            conteneur = QWidget()
            v = QVBoxLayout(conteneur)
            v.addWidget(self.supervision, 1)
            ligne = QHBoxLayout()
            if session.a("sauvegarde.gerer"):
                b = QPushButton(tr("Lancer une sauvegarde chiffrée"))
                b.clicked.connect(self.sauvegarder)
                ligne.addWidget(b)
            b = QPushButton(tr("Relancer l'analyse antivirus en échec"))
            b.clicked.connect(lambda: self.appel_direct(lambda: self.api.post("/systeme/documents/reanalyse")))
            ligne.addWidget(b)
            ligne.addStretch()
            v.addLayout(ligne)
            self.onglets.addTab(conteneur, tr("Supervision"))

    def _onglet_compte(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        m = self.session.moi
        infos = QLabel(
            tr(
                "<b>{prenoms} {nom}</b> ({identifiant})<br/>Rôle : {role}<br/>Unité : "
                "{unite_nom}<br/>Périmètre : {libelle}<br/>Authentification multifacteur : "
                "{v13}<br/><br/><b>Habilitations</b><br/>",
                prenoms=m["prenoms"],
                nom=m["nom"],
                identifiant=m["identifiant"],
                role=tr(m["role"]),
                unite_nom=m["unite_nom"],
                libelle=L.libelle(L.PORTEE, m["portee"]),
                v13=tr("activée") if m["mfa_active"] else tr("non activée"),
            )
            + "<br/>".join(sorted(tr(v) for v in m["libelles_permissions"].values()))
        )
        infos.setObjectName("panneau")
        infos.setMargin(12)
        infos.setWordWrap(True)
        v.addWidget(infos)
        b = QPushButton(tr("Changer mon mot de passe"))
        b.clicked.connect(lambda: DialogueChangementMotDePasse(self.api, self, obligatoire=False).exec())
        v.addWidget(b)
        v.addStretch()
        return w

    def charger(self) -> None:
        self.charger_validations(1)
        if hasattr(self, "categories"):
            self.executer(lambda: self.api.get("/categories", {"toutes": "true"}), self.categories.definir_lignes)
        if hasattr(self, "parametres"):
            self.executer(
                lambda: self.api.get("/parametres"),
                lambda r: self.parametres.definir_lignes([{"cle": k, **v} for k, v in r.items()]),
            )
        if hasattr(self, "conservation"):
            self.executer(
                lambda: self.api.get("/conservation/rapport"),
                lambda r: self.conservation.setText(
                    tr(
                        "Sessions expirées à purger : {sessions_expirees}\nCaptures biométriques arrivées "
                        "à échéance : {captures_biometriques_echues}\nPlaintes archivées au delà de la "
                        "durée de conservation : {plaintes_archivees_echues}\n\nLes durées sont fixées par "
                        "l'institution (paramètres « retention »). La purge est soumise à double "
                        "validation. Le journal d'audit n'est jamais purgé par l'application.",
                        sessions_expirees=r["sessions_expirees"],
                        captures_biometriques_echues=r["captures_biometriques_echues"],
                        plaintes_archivees_echues=r["plaintes_archivees_echues"],
                    )
                ),
            )
        if hasattr(self, "supervision"):
            self.executer(
                lambda: self.api.get("/systeme/etat"),
                lambda r: self.supervision.setText("\n".join(f"{k} : {v}" for k, v in r.items())),
            )

    def charger_validations(self, page: int = 1) -> None:
        self.executer(lambda: self.api.get("/validations", {"page": page, "taille": 50}), self.validations.definir_page)

    def decider(self, approuver: bool) -> None:
        d = self.validations.selection()
        if not d:
            return
        if not confirmer(
            self,
            tr("Double validation"),
            tr("{v0} : {resume} ?", v0="Approuver" if approuver else "Rejeter", resume=d["resume"]),
        ):
            return
        try:
            avec_reauthentification(
                self, self.session, lambda: self.api.post(f"/validations/{d['id']}/decision", {"approuver": approuver})
            )
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
        self.charger_validations(self.validations.page)

    def editer_categorie(self, c: dict | None) -> None:
        f = FormulaireDialogue(tr("Catégorie de faits"), self)
        code = f.ajouter(tr("Code"), QLineEdit(c["code"] if c else ""), True)
        code.setEnabled(c is None)
        libelle = f.ajouter(tr("Libellé"), QLineEdit(c["libelle"] if c else ""), True)
        reference = f.ajouter(tr("Référence légale"), QLineEdit((c or {}).get("reference_legale") or ""))
        validee = f.ajouter(tr("Validée par l'autorité compétente"), QCheckBox())
        validee.setChecked(bool(c and c["validee"]))
        par = f.ajouter(tr("Autorité de validation"), QLineEdit((c or {}).get("validee_par") or ""))
        active = f.ajouter(tr("Active"), QCheckBox())
        active.setChecked(c["active"] if c else True)
        donnees = lambda: {
            "libelle": libelle.text().strip(),
            "reference_legale": texte_ou_none(reference),  # noqa
            "validee": validee.isChecked(),
            "validee_par": texte_ou_none(par),
        }
        f.action = (
            (lambda: self.api.patch(f"/categories/{c['id']}", {**donnees(), "active": active.isChecked()}))
            if c
            else (lambda: self.api.post("/categories", {**donnees(), "code": code.text().strip().upper()}))
        )
        if f.exec() == QDialog.Accepted:
            self.session.invalider_caches()
            self.charger()

    def editer_parametre(self, p: dict) -> None:
        f = FormulaireDialogue(tr("Paramètre {cle}", cle=p["cle"]), self)
        texte = f.ajouter(tr("Valeur (JSON)"), QPlainTextEdit(json.dumps(p["valeur"], ensure_ascii=False, indent=2)))

        def _action():
            try:
                valeur = json.loads(texte.toPlainText())
            except json.JSONDecodeError as exc:
                raise ValueError(tr("JSON invalide : {exc}", exc=exc)) from exc
            return avec_reauthentification(
                self, self.session, lambda: self.api.put(f"/parametres/{p['cle']}", {"valeur": valeur})
            )

        f.action = _action
        if f.exec() == QDialog.Accepted:
            self.charger()

    def purge(self) -> None:
        motif = demander_motif(
            self, tr("Purge des données échues"), tr("Motif et référence de la décision institutionnelle :")
        )
        if motif and self.appel_direct(lambda: self.api.post("/conservation/purge", {"motif": motif})):
            QMessageBox.information(
                self, tr("Purge"), tr("Demande enregistrée : elle sera exécutée après double validation.")
            )

    def sauvegarder(self) -> None:
        try:
            r = avec_reauthentification(self, self.session, lambda: self.api.post("/systeme/sauvegardes"))
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        if r:
            QMessageBox.information(
                self, tr("Sauvegarde"), tr("Sauvegarde créée : {sauvegarde}", sauvegarde=r["sauvegarde"])
            )
            self.charger()
