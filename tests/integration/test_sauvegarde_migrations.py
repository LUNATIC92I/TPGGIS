"""Sauvegardes chiffrees, restauration et migrations de schema."""

from __future__ import annotations

import os
import shutil

import pytest
from sqlalchemy import create_engine, inspect, text

from tpgis.server.database.initialisation import configuration_alembic, migrer
from tpgis.server.services import sauvegarde

API = "/api/v1"


def _nombre_plaintes(app) -> int:
    with app.state.fabrique.moteur.connect() as c:
        return c.execute(text("SELECT COUNT(*) FROM plaintes")).scalar()


def test_sauvegarde_puis_restauration(client, connexions, app, parametres):
    h = connexions.entetes("officier.ndj")
    plainte = client.get(f"{API}/plaintes", headers=h, params={"taille": 1}).json()["elements"][0]
    doc = client.post(
        f"{API}/documents",
        headers=h,
        data={"intitule": "Pièce", "type_piece": "AUTRE", "plainte_id": plainte["id"]},
        files={"fichier": ("piece.txt", b"contenu de la piece fictive", "text/plain")},
    ).json()
    avant = _nombre_plaintes(app)
    dossier = sauvegarde.sauvegarder(parametres, "0001")
    assert (dossier / "base.enc").exists() and (dossier / "manifeste.hmac").exists()
    assert b"contenu de la piece" not in (dossier / "stockage.tar.enc").read_bytes()
    sauvegarde.verifier(parametres, dossier)

    # Incident : nouvelles donnees puis perte du stockage documentaire.
    client.post(
        f"{API}/plaintes",
        headers=h,
        json={"service_enregistrement": "Accueil", "description": "Plainte créée après la sauvegarde."},
    )
    assert _nombre_plaintes(app) == avant + 1
    shutil.rmtree(parametres.repertoire_stockage)

    app.state.fabrique.moteur.dispose()
    with pytest.raises(sauvegarde.ErreurSauvegarde):
        sauvegarde.restaurer(parametres, dossier)  # confirmation obligatoire
    sauvegarde.restaurer(parametres, dossier, confirmer_ecrasement=True)
    app.state.fabrique.moteur.dispose()
    assert _nombre_plaintes(app) == avant
    h = connexions.entetes("officier.ndj")
    r = client.get(f"{API}/documents/{doc['id']}/contenu", headers=h)
    assert r.status_code == 200 and r.content == b"contenu de la piece fictive"


def test_sauvegarde_alteree_refusee(app, parametres, donnees):
    dossier = sauvegarde.sauvegarder(parametres, "0001")
    cible = dossier / "base.enc"
    os.chmod(cible, 0o600)
    contenu = bytearray(cible.read_bytes())
    contenu[100] ^= 0xFF
    cible.write_bytes(bytes(contenu))
    with pytest.raises(sauvegarde.ErreurSauvegarde, match="altéré"):
        sauvegarde.verifier(parametres, dossier)


def test_restauration_refusee_dans_un_autre_environnement(app, parametres, donnees):
    dossier = sauvegarde.sauvegarder(parametres, "0001")
    autre = parametres.model_copy(update={"environnement": "demonstration"})
    with pytest.raises(sauvegarde.ErreurSauvegarde, match="environnement"):
        sauvegarde.restaurer(autre, dossier, confirmer_ecrasement=True)


def test_chiffrement_par_blocs_aller_retour(tmp_path):
    cle = os.urandom(32)
    source = tmp_path / "source.bin"
    source.write_bytes(os.urandom(sauvegarde.TAILLE_BLOC * 2 + 123))
    sha = sauvegarde.chiffrer_fichier(cle, source, tmp_path / "c.enc")
    assert sauvegarde.dechiffrer_fichier(cle, tmp_path / "c.enc", tmp_path / "d.bin") == sha
    assert (tmp_path / "d.bin").read_bytes() == source.read_bytes()
    # Troncature detectee (suppression du dernier bloc).
    brut = (tmp_path / "c.enc").read_bytes()
    (tmp_path / "t.enc").write_bytes(brut[: len(brut) - 200])
    with pytest.raises(sauvegarde.ErreurSauvegarde):
        sauvegarde.dechiffrer_fichier(cle, tmp_path / "t.enc", tmp_path / "x.bin")


def test_migration_montee_et_descente(tmp_path):
    from alembic import command

    url = os.environ.get("TPGIS_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'migr.sqlite3'}"
    if url.startswith("postgresql"):
        from tests.conftest import _vider_postgresql

        _vider_postgresql(url)
    moteur = create_engine(url)
    migrer(moteur)
    tables = set(inspect(moteur).get_table_names())
    assert {"plaintes", "personnes", "journal_audit", "captures_biometriques", "alembic_version"} <= tables
    with moteur.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
        if c.dialect.name == "postgresql":
            index = c.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_personnes_nom_normalise_motif'")
            )
            assert "varchar_pattern_ops" in index.scalar()
    cfg = configuration_alembic(url)
    with moteur.begin() as connexion:
        cfg.attributes["connection"] = connexion
        command.downgrade(cfg, "base")
    assert set(inspect(moteur).get_table_names()) <= {"alembic_version"}
    migrer(moteur)  # remontee complete apres descente
    assert "plaintes" in inspect(moteur).get_table_names()
    moteur.dispose()


def test_schema_conforme_aux_modeles(tmp_path):
    """Aucune difference entre les migrations et les modeles (autogeneration vide)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from tpgis.server.database.base import Base

    url = f"sqlite:///{tmp_path / 'conf.sqlite3'}"
    moteur = create_engine(url)
    migrer(moteur)
    with moteur.connect() as c:
        differences = compare_metadata(MigrationContext.configure(c), Base.metadata)
    moteur.dispose()
    assert differences == []
