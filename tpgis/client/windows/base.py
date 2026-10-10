"""Session cliente et classe de base des pages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from tpgis.client.api_client.client import ClientAPI, ErreurAPI
from tpgis.client.api_client.travail import Executeur
from tpgis.client.widgets.communs import TitrePage, afficher_erreur, demander_finalite


@dataclass
class SessionClient:
    api: ClientAPI
    moi: dict
    executeur: Executeur
    finalites: list[str] = field(default_factory=list)
    _categories: list[dict] | None = None
    _unites: list[dict] | None = None

    @property
    def permissions(self) -> set[str]:
        return set(self.moi.get("permissions", []))

    def a(self, *permissions: str) -> bool:
        return any(p in self.permissions for p in permissions)

    def categories(self) -> list[dict]:
        if self._categories is None:
            self._categories = self.api.get("/categories")
        return self._categories

    def unites(self) -> list[dict]:
        if self._unites is None:
            self._unites = self.api.get("/unites") if self.a("unite.lire") else []
        return self._unites

    def invalider_caches(self) -> None:
        self._categories = self._unites = None

    def finalite(self, parent) -> str | None:
        """Demande la finalite de consultation (journalisee cote serveur)."""
        if not self.finalites:
            try:
                self.finalites = self.api.get("/parametres").get("recherche.finalites", [])
                if isinstance(self.finalites, dict):
                    self.finalites = self.finalites.get("valeur", [])
            except ErreurAPI:
                self.finalites = []
        return demander_finalite(parent, self.finalites or ["Enquête judiciaire en cours"])


class Page(QWidget):
    """Page de l'application. Le chargement est differe jusqu'a l'affichage."""

    titre = ""
    sous_titre = ""

    def __init__(self, session: SessionClient, parent=None):
        super().__init__(parent)
        self.session = session
        self.api = session.api
        self.couche = QVBoxLayout(self)
        self.couche.setContentsMargins(22, 18, 22, 14)
        self.couche.setSpacing(10)
        self.entete = QHBoxLayout()
        self.entete.addWidget(TitrePage(self.titre, self.sous_titre), 1)
        self.couche.addLayout(self.entete)
        self._charge = False

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._charge:
            self._charge = True
            self.charger()

    def charger(self) -> None:
        pass

    def executer(self, fonction: Callable, succes: Callable | None = None, echec: Callable | None = None) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)

        def _ok(resultat):
            QApplication.restoreOverrideCursor()
            if succes:
                succes(resultat)

        def _ko(exc):
            QApplication.restoreOverrideCursor()
            if echec:
                echec(exc)
            else:
                afficher_erreur(self, exc)

        self.session.executeur.lancer(fonction, _ok, _ko)

    def appel_direct(self, fonction: Callable):
        """Appel bloquant court (validation de formulaire), erreurs affichees."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return fonction()
        except ErreurAPI as exc:
            afficher_erreur(self, exc)
            return None
        finally:
            QApplication.restoreOverrideCursor()
