"""Environnement Alembic : migrations du schema TPGIS."""

from __future__ import annotations

from alembic import context
from sqlalchemy import TypeDecorator, create_engine, pool

from tpgis.server.config import obtenir_parametres
from tpgis.server.database import models  # noqa: F401  (enregistre les tables)
from tpgis.server.database.base import Base

config = context.config
cible = Base.metadata


def _url() -> str:
    return config.attributes.get("database_url") or obtenir_parametres().database_url


def _rendu(type_, objet, autogen_context):
    # Les types chiffres sont stockes comme du texte : la migration reste
    # independante du code applicatif.
    if type_ == "type" and isinstance(objet, TypeDecorator):
        return repr(objet.impl).replace("DateTime(", "sa.DateTime(").replace("Text(", "sa.Text(")
    return False


def executer_hors_ligne() -> None:
    context.configure(url=_url(), target_metadata=cible, literal_binds=True, render_item=_rendu)
    with context.begin_transaction():
        context.run_migrations()


def executer_en_ligne() -> None:
    connexion_existante = config.attributes.get("connection")
    if connexion_existante is not None:
        context.configure(connection=connexion_existante, target_metadata=cible, render_item=_rendu,
                          render_as_batch=connexion_existante.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
        return
    moteur = create_engine(_url(), poolclass=pool.NullPool)
    with moteur.connect() as connexion:
        context.configure(connection=connexion, target_metadata=cible, render_item=_rendu,
                          render_as_batch=connexion.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    executer_hors_ligne()
else:
    executer_en_ligne()
