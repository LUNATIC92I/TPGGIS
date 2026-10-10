"""Moteur de base de donnees et fabrique de sessions transactionnelles."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from tpgis.server.config import ParametresServeur


def creer_moteur(parametres: ParametresServeur) -> Engine:
    url = parametres.database_url
    options: dict = {"echo": parametres.database_echo, "future": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url == "sqlite://":
            from sqlalchemy.pool import StaticPool

            options["poolclass"] = StaticPool
    else:
        options.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
    moteur = create_engine(url, **options)
    if url.startswith("sqlite"):

        @event.listens_for(moteur, "connect")
        def _pragmas(connexion, _):
            curseur = connexion.cursor()
            curseur.execute("PRAGMA foreign_keys=ON")
            curseur.execute("PRAGMA journal_mode=WAL")
            curseur.close()

    return moteur


class FabriqueSessions:
    def __init__(self, moteur: Engine):
        self.moteur = moteur
        self._fabrique = sessionmaker(bind=moteur, expire_on_commit=False, autoflush=True)

    def __call__(self) -> Session:
        return self._fabrique()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        session = self._fabrique()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
