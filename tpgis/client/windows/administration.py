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


class PageUnites(Page):
    titre = "Unités et commissariats"
    sous_titre = "Référentiel des commissariats, brigades et services de la Police et de la Gendarmerie."

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        barre = QHBoxLayout()
        nouvelle = QPushButton("Nouvelle unité")
        nouvelle.setObjectName("boutonPrincipal")
        nouvelle.setEnabled(session.a("unite.gerer"))
        nouvelle.clicked.connect(lambda: self.editer(None))
        modifier = QPushButton("Modifier")
        modifier.setEnabled(session.a("unite.gerer"))
        modifier.clicked.connect(lambda: self.editer(self.tableau.selection()))
        barre.addStretch()
        barre.addWidget(nouvelle)
        barre.addWidget(modifier)
        self.couche.addLayout(barre)
        noms_provinces = provinces()
        self.tableau = TableauDonnees(
            [
                ("code", "Code", None),
                ("nom", "Nom", None),
                ("corps", "Corps", lambda v, _: L.libelle(L.CORPS, v)),
                ("type_unite", "Type", lambda v, _: L.libelle(L.TYPE_UNITE, v)),
                ("province_code", "Province", lambda v, _: noms_provinces.get(v or "", v or "")),
                ("ville", "Ville", None),
                ("active", "Active", None),
            ],
            pagine=False,
        )
        self.tableau.ligne_activee.connect(lambda u: session.a("unite.gerer") and self.editer(u))
        self.couche.addWidget(self.tableau, 1)

    def charger(self) -> None:
        self.session.invalider_caches()
        self.executer(lambda: self.api.get("/unites"), self.tableau.definir_lignes)

    def editer(self, unite: dict | None) -> None:
        f = FormulaireDialogue("Modifier l'unité" if unite else "Nouvelle unité", self)
        code = f.ajouter("Code", QLineEdit(unite["code"] if unite else ""), True)
        code.setEnabled(unite is None)
        nom = f.ajouter("Nom", QLineEdit(unite["nom"] if unite else ""), True)
        type_unite = f.ajouter("Type", Choix(L.TYPE_UNITE))
        corps = f.ajouter("Corps", Choix(L.CORPS))
        parents = {u["id"]: u["nom"] for u in self.tableau.modele.lignes if not unite or u["id"] != unite["id"]}
        parent = f.ajouter("Unité de rattachement", Choix(parents, "Aucune"))
        province = f.ajouter("Province", Choix(provinces(), "Non renseignée"))
        ville = f.ajouter("Ville", QLineEdit(unite.get("ville") or "" if unite else ""))
        lat, lon = QDoubleSpinBox(), QDoubleSpinBox()
        lat.setRange(7.0, 24.0)
        lon.setRange(13.0, 24.5)
        for champ in (lat, lon):
            champ.setDecimals(4)
        f.ajouter("Latitude", lat)
        f.ajouter("Longitude", lon)
        active = f.ajouter("Active", QCheckBox())
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
        self.texte.setPlaceholderText("Identifiant, nom ou matricule")
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

        barre.addWidget(bouton("Rechercher", lambda: self.charger(1)))
        barre.addWidget(bouton("Nouveau compte", self.creer, gerer, "boutonPrincipal"))
        c.addLayout(barre)
        # Actions sur le compte selectionne, sur deux lignes pour rester lisibles
        # a la largeur minimale de la fenetre.
        actions = QGridLayout()
        for indice, (libelle, rappel, nom_objet) in enumerate(
            (
                ("Changer le rôle", self.changer_role, None),
                ("Révoquer les sessions", self.revoquer, None),
                ("Réinitialiser le mot de passe", self.reinitialiser, None),
                ("Réactiver", self.reactiver, None),
                ("Réinitialiser la MFA", self.reinitialiser_mfa, None),
                ("Désactiver", self.desactiver, "boutonDanger"),
            )
        ):
            actions.addWidget(bouton(libelle, rappel, gerer, nom_objet), indice // 3, indice % 3)
        c.addLayout(actions)
        self.tableau = TableauDonnees(
            [
                ("identifiant", "Identifiant", None),
                ("nom", "Nom", None),
                ("prenoms", "Prénoms", None),
                ("grade", "Grade", None),
                ("unite_nom", "Unité", None),
                ("role_libelle", "Rôle", None),
                ("portee", "Périmètre", lambda v, _: L.libelle(L.PORTEE, v)),
                ("actif", "Actif", None),
                ("mfa_active", "MFA", None),
                ("derniere_connexion", "Dernière connexion", lambda v, _: fmt_date(v)),
            ]
        )
        self.tableau.page_demandee.connect(self.charger)
        c.addWidget(self.tableau, 1)
        self.onglets.addTab(comptes, "Comptes")
        self.roles = TableauDonnees(
            [
                ("libelle", "Rôle", None),
                ("code", "Code", None),
                ("portee_defaut", "Périmètre par défaut", lambda v, _: L.libelle(L.PORTEE, v)),
                ("privilegie", "Privilégié (MFA)", None),
                ("actif", "Actif", None),
                ("permissions", "Permissions", lambda v, _: str(len(v))),
            ],
            pagine=False,
        )
        self.roles.ligne_activee.connect(self.editer_role)
        conteneur = QWidget()
        r = QVBoxLayout(conteneur)
        r.addWidget(self.roles, 1)
        ligne = QHBoxLayout()
        nouveau = QPushButton("Nouveau rôle")
        nouveau.setEnabled(session.a("role.gerer"))
        nouveau.clicked.connect(lambda: self.editer_role(None))
        ligne.addWidget(QLabel("Double-cliquez sur un rôle pour consulter ou modifier ses permissions."))
        ligne.addStretch()
        ligne.addWidget(nouveau)
        r.addLayout(ligne)
        self.onglets.addTab(conteneur, "Rôles et permissions")

    def charger(self, page: int = 1) -> None:
        params = {"texte": self.texte.text().strip(), "page": page, "taille": 50}
        self.executer(lambda: self.api.get("/utilisateurs", params), self.tableau.definir_page)
        self.executer(lambda: self.api.get("/roles"), self.roles.definir_lignes)

    def _cible(self) -> dict | None:
        u = self.tableau.selection()
        if not u:
            QMessageBox.information(self, "Utilisateurs", "Sélectionnez d'abord un compte.")
        return u

    def creer(self) -> None:
        f = FormulaireDialogue("Nouveau compte utilisateur", self)
        ident = f.ajouter("Identifiant", QLineEdit(), True)
        nom, prenoms = f.ajouter("Nom", QLineEdit(), True), f.ajouter("Prénoms", QLineEdit(), True)
        matricule, grade = f.ajouter("Matricule", QLineEdit()), f.ajouter("Grade", QLineEdit())
        unite = f.ajouter("Unité", Choix({u["id"]: u["nom"] for u in self.session.unites()}))
        roles = {r["id"]: r["libelle"] for r in self.roles.modele.lignes if not r["privilegie"] and r["actif"]}
        role = f.ajouter("Rôle (non privilégié)", Choix(roles))
        mdp = f.ajouter("Mot de passe initial", QLineEdit(), True)
        mdp.setEchoMode(QLineEdit.Password)
        note = QLabel(
            "Le mot de passe devra être changé à la première connexion. Les rôles privilégiés s'attribuent "
            "ensuite par une demande soumise à double validation."
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
        f = FormulaireDialogue(f"Changer le rôle de {u['identifiant']}", self)
        role = f.ajouter(
            "Nouveau rôle",
            Choix(
                {
                    r["id"]: r["libelle"] + (" (privilégié)" if r["privilegie"] else "")
                    for r in self.roles.modele.lignes
                    if r["actif"]
                }
            ),
        )
        motif = f.ajouter("Motif", QPlainTextEdit(), True)
        f.action = lambda: self.api.post(
            f"/utilisateurs/{u['id']}/role", {"role_id": role.valeur(), "motif": motif.toPlainText().strip()}
        )
        if f.exec() == QDialog.Accepted:
            if f.resultat.get("statut") == "EN_ATTENTE":
                QMessageBox.information(
                    self,
                    "Double validation",
                    "Le rôle demandé est privilégié : la demande doit être approuvée par un second responsable.",
                )
            self.charger(self.tableau.page)

    def desactiver(self) -> None:
        u = self._cible()
        if u and confirmer(
            self,
            "Désactivation",
            f"Désactiver immédiatement le compte {u['identifiant']} ?\nToutes ses sessions seront révoquées.",
        ):
            motif = demander_motif(self, "Motif de désactivation", "Motif :")
            if motif and self.appel_direct(
                lambda: self.api.post(f"/utilisateurs/{u['id']}/desactivation", {"motif": motif})
            ):
                self.charger(self.tableau.page)

    def reactiver(self) -> None:
        u = self._cible()
        motif = demander_motif(self, "Réactivation", "Motif de la réactivation :") if u else None
        if motif and self.appel_direct(
            lambda: self.api.post(f"/utilisateurs/{u['id']}/reactivation", {"motif": motif})
        ):
            self.charger(self.tableau.page)

    def revoquer(self) -> None:
        u = self._cible()
        if u and confirmer(self, "Révocation", f"Fermer toutes les sessions de {u['identifiant']} ?"):
            r = self.appel_direct(lambda: self.api.post(f"/utilisateurs/{u['id']}/revocation-sessions"))
            if r:
                QMessageBox.information(self, "Révocation", f"{r['sessions_revoquees']} session(s) révoquée(s).")

    def reinitialiser(self) -> None:
        u = self._cible()
        if not u:
            return
        f = FormulaireDialogue(f"Réinitialiser le mot de passe de {u['identifiant']}", self)
        mdp = f.ajouter("Mot de passe temporaire", QLineEdit(), True)
        mdp.setEchoMode(QLineEdit.Password)
        motif = f.ajouter("Motif", QLineEdit(), True)
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
        motif = demander_motif(self, "Réinitialisation MFA", "Motif (perte du terminal, etc.) :") if u else None
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
        f = FormulaireDialogue("Rôle" if role else "Nouveau rôle", self, 640)
        code = f.ajouter("Code", QLineEdit(role["code"] if role else ""), True)
        code.setEnabled(role is None)
        libelle = f.ajouter("Libellé", QLineEdit(role["libelle"] if role else ""), True)
        portee = f.ajouter("Périmètre par défaut", Choix(L.PORTEE))
        liste = QListWidget()
        liste.setMinimumHeight(260)
        actuelles = set(role["permissions"]) if role else set()
        for p in catalogue or [{"code": x, "libelle": x} for x in sorted(actuelles)]:
            item = QListWidgetItem(f"{p['libelle']}  ({p['code']})")
            item.setData(Qt.UserRole, p["code"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if p["code"] in actuelles else Qt.Unchecked)
            liste.addItem(item)
        f.ajouter("Permissions", liste)
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
        self.identifiant.setPlaceholderText("Identifiant")
        self.action.setPlaceholderText("Action (ex. RECHERCHE)")
        self.trace.setPlaceholderText("Identifiant de trace")
        self.resultat = Choix({"SUCCES": "Succès", "REFUS": "Refus", "ECHEC": "Échec"}, "Tous résultats")
        filtrer = QPushButton("Filtrer")
        filtrer.clicked.connect(lambda: self.charger(1))
        verifier = QPushButton("Vérifier l'intégrité")
        verifier.clicked.connect(self.verifier)
        for w in (self.identifiant, self.action, self.trace, self.resultat, filtrer, verifier):
            barre.addWidget(w)
        self.couche.addLayout(barre)
        self.tableau = TableauDonnees(
            [
                ("id", "N°", None),
                ("horodatage", "Horodatage", lambda v, _: fmt_date(v)),
                ("identifiant", "Utilisateur", None),
                ("action", "Action", None),
                ("resultat", "Résultat", None),
                ("type_ressource", "Ressource", None),
                ("finalite", "Finalité", None),
                ("adresse_ip", "Adresse", None),
                ("trace_id", "Trace", None),
                ("details", "Détails", lambda v, _: json.dumps(v, ensure_ascii=False) if v else ""),
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
                self, "Intégrité du journal", f"Chaîne intègre : {r['evenements_verifies']} événements vérifiés."
            )
        else:
            QMessageBox.critical(
                self,
                "Intégrité du journal",
                f"RUPTURE DÉTECTÉE à l'événement n° {r['rupture_a_id']}. Déclencher la procédure "
                "de réponse aux incidents.",
            )


class PageParametres(Page):
    titre = "Paramètres et administration"
    sous_titre = "Compte personnel, référentiels, double validation, conservation des données et supervision."

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self.onglets = QTabWidget()
        self.couche.addWidget(self.onglets, 1)
        self.onglets.addTab(self._onglet_compte(), "Mon compte")
        # Chacun suit ses propres demandes ; les valideurs voient celles de leur perimetre.
        self.validations = TableauDonnees(
            [
                ("cree_le", "Demandée le", lambda v, _: fmt_date(v)),
                ("type_action", "Type", lambda v, _: L.libelle(L.TYPE_VALIDATION, v)),
                ("resume", "Objet", None),
                ("motif", "Motif", None),
                ("statut", "Statut", lambda v, _: L.libelle(L.STATUT_VALIDATION, v)),
                ("resultat", "Résultat", None),
            ]
        )
        conteneur = QWidget()
        v = QVBoxLayout(conteneur)
        v.addWidget(self.validations, 1)
        ligne = QHBoxLayout()
        for texte, approuver in (("Approuver", True), ("Rejeter", False)):
            b = QPushButton(texte)
            b.setEnabled(session.a("validation.approuver"))
            b.clicked.connect(lambda _, a=approuver: self.decider(a))
            ligne.addWidget(b)
        ligne.addStretch()
        v.addLayout(ligne)
        self.validations.page_demandee.connect(self.charger_validations)
        self.onglets.addTab(conteneur, "Demandes de double validation")
        if session.a("categorie.gerer"):
            self.categories = TableauDonnees(
                [
                    ("code", "Code", None),
                    ("libelle", "Libellé", None),
                    ("reference_legale", "Référence légale", None),
                    ("validee", "Validée", None),
                    ("validee_par", "Validée par", None),
                    ("active", "Active", None),
                ],
                pagine=False,
            )
            self.categories.ligne_activee.connect(self.editer_categorie)
            conteneur = QWidget()
            v = QVBoxLayout(conteneur)
            v.addWidget(self.categories, 1)
            b = QPushButton("Nouvelle catégorie")
            b.clicked.connect(lambda: self.editer_categorie(None))
            v.addWidget(b)
            self.onglets.addTab(conteneur, "Référentiel des faits")
        if session.a("parametres.gerer"):
            self.parametres = TableauDonnees(
                [
                    ("cle", "Paramètre", None),
                    ("description", "Description", None),
                    ("valeur", "Valeur", lambda v, _: json.dumps(v, ensure_ascii=False)),
                ],
                pagine=False,
            )
            self.parametres.ligne_activee.connect(self.editer_parametre)
            self.onglets.addTab(self.parametres, "Paramètres techniques")
        if session.a("validation.approuver"):
            conteneur = QWidget()
            v = QVBoxLayout(conteneur)
            self.conservation = QLabel("")
            self.conservation.setWordWrap(True)
            self.conservation.setObjectName("panneau")
            self.conservation.setMargin(12)
            v.addWidget(self.conservation)
            b = QPushButton("Demander la purge des données échues")
            b.setObjectName("boutonDanger")
            b.clicked.connect(self.purge)
            v.addWidget(b)
            v.addStretch()
            self.onglets.addTab(conteneur, "Conservation des données")
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
                b = QPushButton("Lancer une sauvegarde chiffrée")
                b.clicked.connect(self.sauvegarder)
                ligne.addWidget(b)
            b = QPushButton("Relancer l'analyse antivirus en échec")
            b.clicked.connect(lambda: self.appel_direct(lambda: self.api.post("/systeme/documents/reanalyse")))
            ligne.addWidget(b)
            ligne.addStretch()
            v.addLayout(ligne)
            self.onglets.addTab(conteneur, "Supervision")

    def _onglet_compte(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        m = self.session.moi
        infos = QLabel(
            f"<b>{m['prenoms']} {m['nom']}</b> ({m['identifiant']})<br/>Rôle : {m['role']}<br/>"
            f"Unité : {m['unite_nom']}<br/>Périmètre : {L.libelle(L.PORTEE, m['portee'])}<br/>"
            f"Authentification multifacteur : {'activée' if m['mfa_active'] else 'non activée'}<br/><br/>"
            "<b>Habilitations</b><br/>" + "<br/>".join(sorted(m["libelles_permissions"].values()))
        )
        infos.setObjectName("panneau")
        infos.setMargin(12)
        infos.setWordWrap(True)
        v.addWidget(infos)
        b = QPushButton("Changer mon mot de passe")
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
                    f"Sessions expirées à purger : {r['sessions_expirees']}\n"
                    f"Captures biométriques arrivées à échéance : {r['captures_biometriques_echues']}\n"
                    f"Plaintes archivées au delà de la durée de conservation : {r['plaintes_archivees_echues']}\n\n"
                    "Les durées sont fixées par l'institution (paramètres « retention »). La purge est soumise à "
                    "double validation. Le journal d'audit n'est jamais purgé par l'application."
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
        if not confirmer(self, "Double validation", f"{'Approuver' if approuver else 'Rejeter'} : {d['resume']} ?"):
            return
        try:
            avec_reauthentification(
                self, self.session, lambda: self.api.post(f"/validations/{d['id']}/decision", {"approuver": approuver})
            )
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
        self.charger_validations(self.validations.page)

    def editer_categorie(self, c: dict | None) -> None:
        f = FormulaireDialogue("Catégorie de faits", self)
        code = f.ajouter("Code", QLineEdit(c["code"] if c else ""), True)
        code.setEnabled(c is None)
        libelle = f.ajouter("Libellé", QLineEdit(c["libelle"] if c else ""), True)
        reference = f.ajouter("Référence légale", QLineEdit((c or {}).get("reference_legale") or ""))
        validee = f.ajouter("Validée par l'autorité compétente", QCheckBox())
        validee.setChecked(bool(c and c["validee"]))
        par = f.ajouter("Autorité de validation", QLineEdit((c or {}).get("validee_par") or ""))
        active = f.ajouter("Active", QCheckBox())
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
        f = FormulaireDialogue(f"Paramètre {p['cle']}", self)
        texte = f.ajouter("Valeur (JSON)", QPlainTextEdit(json.dumps(p["valeur"], ensure_ascii=False, indent=2)))

        def _action():
            try:
                valeur = json.loads(texte.toPlainText())
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON invalide : {exc}") from exc
            return avec_reauthentification(
                self, self.session, lambda: self.api.put(f"/parametres/{p['cle']}", {"valeur": valeur})
            )

        f.action = _action
        if f.exec() == QDialog.Accepted:
            self.charger()

    def purge(self) -> None:
        motif = demander_motif(self, "Purge des données échues", "Motif et référence de la décision institutionnelle :")
        if motif and self.appel_direct(lambda: self.api.post("/conservation/purge", {"motif": motif})):
            QMessageBox.information(self, "Purge", "Demande enregistrée : elle sera exécutée après double validation.")

    def sauvegarder(self) -> None:
        try:
            r = avec_reauthentification(self, self.session, lambda: self.api.post("/systeme/sauvegardes"))
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return
        if r:
            QMessageBox.information(self, "Sauvegarde", f"Sauvegarde créée : {r['sauvegarde']}")
            self.charger()
