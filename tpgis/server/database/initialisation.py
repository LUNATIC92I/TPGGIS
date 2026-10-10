"""Migrations, donnees de reference et garde fous d'environnement."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.config import ParametresServeur
from tpgis.server.database.models import (
    MetadonneeInstance,
    Personne,
    Plainte,
    Role,
    RolePermission,
    Unite,
    Utilisateur,
)
from tpgis.shared.enums import Environnement
from tpgis.shared.permissions import ROLES_INITIAUX

RACINE = Path(__file__).resolve().parents[3]


class ErreurEnvironnement(RuntimeError):
    pass


def configuration_alembic(url: str) -> Config:
    cfg = Config(str(RACINE / "alembic.ini")) if (RACINE / "alembic.ini").exists() else Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.attributes["database_url"] = url
    return cfg


def migrer(moteur: Engine, revision: str = "head") -> None:
    cfg = configuration_alembic(str(moteur.url))
    with moteur.begin() as connexion:
        cfg.attributes["connection"] = connexion
        command.upgrade(cfg, revision)


def revision_courante(bd: SessionBD) -> str | None:
    try:
        return bd.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        bd.rollback()
        return None


def initialiser_metadonnees(bd: SessionBD, p: ParametresServeur) -> None:
    """Associe definitivement la base a un environnement.

    Une base creee pour la demonstration ne peut jamais etre ouverte par un
    serveur de production, et inversement.
    """
    meta = bd.get(MetadonneeInstance, "environnement")
    if meta is None:
        bd.add(MetadonneeInstance(cle="environnement", valeur=str(p.environnement)))
        bd.add(MetadonneeInstance(cle="contient_donnees_synthetiques", valeur="non"))
        bd.flush()
        return
    if meta.valeur != str(p.environnement):
        raise ErreurEnvironnement(
            f"Cette base appartient à l'environnement {meta.valeur!r} et ne peut pas être utilisée en "
            f"{str(p.environnement)!r}. Séparation des environnements."
        )


def controler_absence_donnees_synthetiques(bd: SessionBD, p: ParametresServeur) -> None:
    if p.environnement != Environnement.PRODUCTION:
        return
    marque = bd.get(MetadonneeInstance, "contient_donnees_synthetiques")
    synthetiques = sum(
        bd.execute(select(func.count()).select_from(m).where(m.est_synthetique.is_(True))).scalar_one()
        for m in (Unite, Utilisateur, Personne, Plainte)
    )
    if (marque and marque.valeur != "non") or synthetiques:
        raise ErreurEnvironnement("Des données de démonstration ont été détectées dans la base de production.")


def initialiser_roles(bd: SessionBD) -> int:
    crees = 0
    for definition in ROLES_INITIAUX:
        if bd.execute(select(Role.id).where(Role.code == definition["code"])).first():
            continue
        role = Role(
            code=definition["code"],
            libelle=definition["libelle"],
            description=definition["description"],
            portee_defaut=definition["portee_defaut"],
            systeme=True,
            actif=True,
        )
        role.permissions = [RolePermission(permission=str(x)) for x in definition["permissions"]]
        bd.add(role)
        crees += 1
    bd.flush()
    return crees
