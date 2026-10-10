"""Journal d'audit : traces des consultations sensibles, immuabilite, absence de secrets."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from tpgis.server.database.models import EvenementAudit
from tpgis.server.database.seed.demonstration import MOT_DE_PASSE_DEMO
from tests.conftest import FINALITE

API = "/api/v1"


def _evenements(client, connexions, **filtres):
    h = connexions.entetes("auditeur")
    return client.get(f"{API}/audit", headers=h, params={"taille": 200, **filtres}).json()["elements"]


def test_consultation_sensible_journalisee_avec_finalite(client, connexions):
    h = connexions.entetes("officier.ndj", FINALITE)
    personne = client.get(f"{API}/personnes", headers=h, params={"taille": 1}).json()["elements"][0]
    r = client.get(f"{API}/personnes/{personne['id']}", headers=h)
    trace = r.json()["trace_audit"]
    ev = _evenements(client, connexions, action="PERSONNE_CONSULTATION", trace_id=trace)
    assert len(ev) == 1
    assert ev[0]["identifiant"] == "officier.ndj"
    assert ev[0]["finalite"] == "Enquete judiciaire en cours"
    assert ev[0]["ressource_id"] == personne["id"]


def test_recherche_journalisee(client, connexions):
    h = connexions.entetes("officier.ndj")
    r = client.post(f"{API}/recherche", headers=h, json={"finalite": "Contrôle d'identité", "nom": "MAHAMAT",
                                                        "numero_document": "FICTIF12345678"})
    trace = r.json()["trace_audit"]
    ev = _evenements(client, connexions, action="RECHERCHE", trace_id=trace)[0]
    assert ev["finalite"] == "Contrôle d'identité"
    assert ev["details"]["nom"] == "MAHAMAT"
    assert ev["details"]["numero_document"].endswith("678") and "FICTIF" not in ev["details"]["numero_document"]


def test_actions_principales_journalisees(client, connexions):
    h = connexions.entetes("officier.ndj")
    client.post(f"{API}/plaintes", headers=h, json={"service_enregistrement": "Accueil",
                                                    "description": "Plainte fictive pour test d'audit."})
    client.post(f"{API}/auth/connexion", json={"identifiant": "officier.ndj", "mot_de_passe": "faux"})
    actions = {e["action"] for e in _evenements(client, connexions)}
    assert {"CONNEXION", "PLAINTE_CREATION"} <= actions
    refus = [e for e in _evenements(client, connexions, action="CONNEXION", resultat="REFUS")]
    assert refus and refus[0]["details"]["raison"] == "mot_de_passe_incorrect"


def test_journal_sans_secret(client, connexions, app):
    h = connexions.entetes("officier.ndj", FINALITE)
    client.post(f"{API}/auth/reauthentification", headers=h, json={"mot_de_passe": MOT_DE_PASSE_DEMO,
                                                                   "code_mfa": connexions.code("officier.ndj")})
    jeton = h["Authorization"].split()[1]
    with app.state.fabrique.transaction() as bd:
        contenu = json.dumps([e.details for e in bd.query(EvenementAudit).all()], ensure_ascii=False)
    assert MOT_DE_PASSE_DEMO not in contenu
    assert jeton not in contenu
    assert "SIM-" not in contenu  # aucune reference de modele biometrique


def test_chaine_integre_puis_alteration_detectee(client, connexions, app):
    h = connexions.entetes("auditeur")
    r = client.get(f"{API}/audit/verification", headers=h).json()
    assert r["integre"] is True and r["evenements_verifies"] > 0
    with app.state.fabrique.moteur.begin() as c:
        if c.dialect.name == "sqlite":
            c.exec_driver_sql("DROP TRIGGER tpgis_audit_sans_modification")
            c.exec_driver_sql("UPDATE journal_audit SET identifiant='falsifie' WHERE id=1")
        else:
            c.exec_driver_sql("ALTER TABLE journal_audit DISABLE TRIGGER tpgis_audit_sans_modification")
            c.exec_driver_sql("UPDATE journal_audit SET identifiant='falsifie' WHERE id=1")
            c.exec_driver_sql("ALTER TABLE journal_audit ENABLE TRIGGER tpgis_audit_sans_modification")
    r = client.get(f"{API}/audit/verification", headers=h).json()
    assert r["integre"] is False and r["rupture_a_id"] == 1


def test_journal_non_modifiable(app, connexions):
    connexions.entetes("accueil.ndj")  # au moins un evenement journalise
    with pytest.raises(Exception):
        with app.state.fabrique.moteur.begin() as c:
            c.execute(text("UPDATE journal_audit SET action='X'"))
    with pytest.raises(Exception):
        with app.state.fabrique.moteur.begin() as c:
            c.execute(text("DELETE FROM journal_audit"))


def test_changement_de_droits_journalise(client, connexions):
    h = connexions.entetes("admin.fonctionnel")
    roles = {r["code"]: r for r in client.get(f"{API}/roles", headers=h).json()}
    cible = client.get(f"{API}/utilisateurs", headers=h, params={"texte": "accueil.abc"}).json()["elements"][0]
    r = client.post(f"{API}/utilisateurs/{cible['id']}/role", headers=h,
                    json={"role_id": roles["CONSULTATION"]["id"], "motif": "Réaffectation fictive de l'agent"})
    assert r.json()["statut"] == "APPLIQUE"
    ev = _evenements(client, connexions, action="DROITS_MODIFICATION")
    assert ev[0]["details"]["role_apres"] == "CONSULTATION"
