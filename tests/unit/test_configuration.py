"""Garde fous de configuration : production, separation des environnements,
interdiction des donnees de demonstration en production."""

from __future__ import annotations

import pytest

from tpgis.server.config import ErreurConfiguration, ParametresServeur, verifier_configuration_production
from tpgis.server.database.initialisation import ErreurEnvironnement
from tpgis.server.database.seed.demonstration import generer
from tpgis.server.main import creer_application
from tpgis.server.security.crypto import generer_cle


def test_production_refuse_configuration_faible():
    p = ParametresServeur(environnement="production", database_url="sqlite:///x.db")
    erreurs = verifier_configuration_production(p)
    assert any("SQLite" in e for e in erreurs)
    assert any("antivirus" in e for e in erreurs)
    assert any("biometrique simule" in e for e in erreurs)
    assert any("TLS" in e for e in erreurs)
    with pytest.raises(ErreurConfiguration):
        creer_application(p)


def test_production_conforme():
    p = ParametresServeur(
        environnement="production",
        database_url="postgresql+psycopg://u:p@h/b",
        cles_donnees=f"k1:{generer_cle()}",
        cle_index=generer_cle(),
        cle_sauvegarde=generer_cle(),
        antivirus="clamd",
        biometrie_adaptateur="aucun",
        tls_termine_par_proxy=True,
    )
    assert verifier_configuration_production(p) == []


def test_base_liee_a_son_environnement(parametres):
    app = creer_application(parametres)
    app.state.fabrique.moteur.dispose()
    autre = parametres.model_copy(update={"environnement": "demonstration"})
    with pytest.raises(ErreurEnvironnement):
        creer_application(autre)


def test_donnees_demo_interdites_en_production(parametres):
    app = creer_application(parametres)
    production = parametres.model_copy(update={"environnement": "production"})
    with app.state.fabrique.transaction() as bd, pytest.raises(RuntimeError, match="production"):
        generer(bd, production)
    app.state.fabrique.moteur.dispose()
