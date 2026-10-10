"""Execution des appels reseau hors du fil graphique (interface toujours reactive)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signaux(QObject):
    succes = Signal(object)
    echec = Signal(object)


class _Tache(QRunnable):
    def __init__(self, fonction: Callable, signaux: _Signaux):
        super().__init__()
        self.fonction, self.signaux = fonction, signaux

    def run(self) -> None:
        try:
            resultat = self.fonction()
        except Exception as exc:  # transmis a l'interface
            self.signaux.echec.emit(exc)
        else:
            self.signaux.succes.emit(resultat)


class Executeur(QObject):
    """Lance une fonction dans le pool de fils et rappelle l'interface.

    En mode synchrone (tests automatises), la fonction est executee directement.
    """

    synchrone = False

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._actifs: set[_Signaux] = set()

    def lancer(self, fonction: Callable, succes: Callable | None = None, echec: Callable | None = None) -> None:
        if Executeur.synchrone:
            try:
                resultat = fonction()
            except Exception as exc:
                if echec:
                    echec(exc)
                return
            if succes:
                succes(resultat)
            return
        signaux = _Signaux()
        self._actifs.add(signaux)

        def _fin_succes(r):
            self._actifs.discard(signaux)
            if succes:
                succes(r)

        def _fin_echec(e):
            self._actifs.discard(signaux)
            if echec:
                echec(e)

        signaux.succes.connect(_fin_succes)
        signaux.echec.connect(_fin_echec)
        self._pool.start(_Tache(fonction, signaux))
