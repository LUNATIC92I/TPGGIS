"""Base declarative SQLAlchemy et types de colonnes communs."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, String, Text, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tpgis.server.security import crypto

CONVENTION_NOMMAGE = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def maintenant() -> datetime:
    return datetime.now(UTC)


def nouvel_id() -> str:
    return str(uuid.uuid4())


class DateHeureUTC(TypeDecorator):
    """Horodatage toujours stocke et restitue en UTC, y compris sous SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class TexteChiffre(TypeDecorator):
    """Colonne texte chiffree de maniere transparente (AES 256 GCM)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return None
        return crypto.chiffreur().chiffrer(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return crypto.chiffreur().dechiffrer(value)


class JSONChiffre(TypeDecorator):
    """Objet JSON chiffre."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return crypto.chiffreur().chiffrer(json.dumps(value, ensure_ascii=False))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(crypto.chiffreur().dechiffrer(value))


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENTION_NOMMAGE)


class Horodatage:
    cree_le: Mapped[datetime] = mapped_column(DateHeureUTC(), default=maintenant, nullable=False)
    modifie_le: Mapped[datetime] = mapped_column(
        DateHeureUTC(), default=maintenant, onupdate=maintenant, nullable=False
    )


def colonne_id() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=nouvel_id)
