"""Tests negatifs : un utilisateur sans habilitation ne peut rien obtenir en
appelant directement l'API, quels que soient les boutons masques du client."""

from __future__ import annotations

import pytest

from tests.conftest import FINALITE

API = "/api/v1"


def _une_plainte(client, h):
    return client.get(f"{API}/plaintes", headers=h, params={"taille": 1}).json()["elements"][0]


def test_acces_sans_authentification_refuse(client, donnees):
    for methode, chemin in [
        ("get", "/plaintes"),
        ("get", "/personnes"),
        ("get", "/audit"),
        ("get", "/utilisateurs"),
        ("post", "/recherche"),
        ("get", "/statistiques/tableau-de-bord"),
        ("get", "/carte/donnees"),
        ("get", "/dossiers"),
    ]:
        r = getattr(client, methode)(f"{API}{chemin}")
        assert r.status_code == 401, chemin


def test_jeton_invente_refuse(client, donnees):
    r = client.get(f"{API}/plaintes", headers={"Authorization": "Bearer jeton-invente-par-un-attaquant"})
    assert r.status_code == 401


@pytest.mark.parametrize("chemin", ["/plaintes", "/personnes", "/dossiers", "/faits"])
def test_admin_technique_sans_acces_aux_dossiers(client, connexions, chemin):
    h = connexions.entetes("admin.technique", FINALITE)
    assert client.get(f"{API}{chemin}", headers=h).status_code == 403


def test_admin_fonctionnel_sans_acces_aux_donnees_operationnelles(client, connexions):
    h = connexions.entetes("admin.fonctionnel", FINALITE)
    assert client.get(f"{API}/plaintes", headers=h).status_code == 403
    assert (
        client.post(f"{API}/recherche", headers=h, json={"finalite": "Curiosité", "nom": "ABAKAR"}).status_code == 403
    )
    assert client.get(f"{API}/audit", headers=h).status_code == 403


def test_agent_accueil_sans_biometrie(client, connexions):
    h_off = connexions.entetes("officier.ndj", FINALITE)
    personne = client.get(f"{API}/personnes", headers=h_off, params={"taille": 1}).json()["elements"][0]
    h = connexions.entetes("accueil.ndj", FINALITE)
    assert client.get(f"{API}/biometrie/personnes/{personne['id']}/captures", headers=h).status_code == 403
    r = client.post(
        f"{API}/biometrie/captures",
        headers=h,
        json={
            "personne_id": personne["id"],
            "position_doigt": "INDEX_DROIT",
            "equipement": "Capteur simulé",
            "fondement_legal": "Fondement fictif de test",
            "consentement_recueilli": True,
        },
    )
    assert r.status_code == 403


def test_auditeur_ne_peut_pas_modifier(client, connexions):
    h = connexions.entetes("auditeur")
    assert client.get(f"{API}/audit", headers=h).status_code == 200
    assert client.get(f"{API}/plaintes", headers=h).status_code == 403
    assert (
        client.post(
            f"{API}/plaintes",
            headers=h,
            json={"service_enregistrement": "x" * 5, "description": "Tentative de création par un auditeur"},
        ).status_code
        == 403
    )


def test_consultation_seule_ne_peut_pas_ecrire(client, connexions):
    h = connexions.entetes("consultation.ndj")
    p = _une_plainte(client, h)
    r = client.patch(f"{API}/plaintes/{p['id']}", headers=h, json={"version": p["version"], "lieu_faits": "x"})
    assert r.status_code == 403
    assert (
        client.post(
            f"{API}/plaintes",
            headers=h,
            json={"service_enregistrement": "Accueil", "description": "Tentative en lecture seule"},
        ).status_code
        == 403
    )


def test_separation_des_donnees_entre_unites(client, connexions):
    h_ndj = connexions.entetes("officier.ndj")
    h_abc = connexions.entetes("officier.abc")
    plaintes_abc = client.get(f"{API}/plaintes", headers=h_abc, params={"taille": 200}).json()["elements"]
    assert plaintes_abc, "jeu de données attendu"
    assert all(p["unite_nom"].startswith("Commissariat d'Abéché") for p in plaintes_abc)
    cible = plaintes_abc[0]
    # Acces direct par identifiant : refuse sans revelation d'existence.
    r = client.get(f"{API}/plaintes/{cible['id']}", headers=h_ndj)
    assert r.status_code == 404
    r = client.patch(
        f"{API}/plaintes/{cible['id']}", headers=h_ndj, json={"version": cible["version"], "lieu_faits": "intrusion"}
    )
    assert r.status_code == 404
    r = client.get(f"{API}/plaintes/{cible['id']}/fiche.pdf", headers=h_ndj)
    assert r.status_code == 404
    # Le filtre par unite ne contourne pas le perimetre.
    r = client.get(f"{API}/plaintes", headers=h_ndj, params={"unite_id": cible["unite_id"]})
    assert r.json()["total"] == 0
    # Le numero exact ne revele pas une plainte hors perimetre.
    r = client.post(
        f"{API}/recherche", headers=h_ndj, json={"finalite": "Test de cloisonnement", "numero_plainte": cible["numero"]}
    )
    assert r.json()["resultats"]["plaintes"] == []


def test_creation_pour_une_autre_unite_refusee(client, connexions):
    h_abc = connexions.entetes("officier.abc")
    unite_abc = client.get(f"{API}/plaintes", headers=h_abc, params={"taille": 1}).json()["elements"][0]["unite_id"]
    h_ndj = connexions.entetes("accueil.ndj")
    r = client.post(
        f"{API}/plaintes",
        headers=h_ndj,
        json={
            "service_enregistrement": "Accueil",
            "description": "Tentative d'écriture hors périmètre",
            "unite_id": unite_abc,
        },
    )
    assert r.status_code == 403


def test_responsable_voit_unites_subordonnees(client, connexions):
    h_a1 = connexions.entetes("accueil.ndj.a1")
    cree = client.post(
        f"{API}/plaintes",
        headers=h_a1,
        json={
            "service_enregistrement": "Accueil arrondissement",
            "description": "Plainte fictive enregistrée dans l'arrondissement.",
        },
    ).json()
    h_resp = connexions.entetes("responsable.ndj")
    assert client.get(f"{API}/plaintes/{cree['id']}", headers=h_resp).status_code == 200
    # L'agent de l'arrondissement ne voit pas les plaintes du commissariat central.
    central = _une_plainte(client, connexions.entetes("officier.ndj"))
    assert client.get(f"{API}/plaintes/{central['id']}", headers=h_a1).status_code == 404


def test_enqueteur_limite_aux_dossiers_attribues(client, connexions):
    h_enq = connexions.entetes("enqueteur.ndj")
    h_off = connexions.entetes("officier.ndj")
    tous = client.get(f"{API}/dossiers", headers=h_off, params={"taille": 200}).json()["elements"]
    attribues = client.get(f"{API}/dossiers", headers=h_enq, params={"taille": 200}).json()["elements"]
    ids_attribues = {d["id"] for d in attribues}
    assert all(d["enqueteur_id"] is not None for d in attribues)
    non_attribue = next((d for d in tous if d["id"] not in ids_attribues), None)
    assert non_attribue is not None
    assert client.get(f"{API}/dossiers/{non_attribue['id']}", headers=h_enq).status_code == 404
    # L'enqueteur ne peut pas se reattribuer un dossier.
    if attribues:
        d = attribues[0]
        r = client.patch(
            f"{API}/dossiers/{d['id']}", headers=h_enq, json={"version": d["version"], "enqueteur_id": None}
        )
        assert r.status_code == 403


def test_consultation_personne_exige_finalite(client, connexions):
    h = connexions.entetes("officier.ndj")
    personne = client.get(f"{API}/personnes", headers=h, params={"taille": 1}).json()["elements"][0]
    r = client.get(f"{API}/personnes/{personne['id']}", headers=h)
    assert r.status_code == 422 and r.json()["code"] == "FINALITE_REQUISE"
    h["X-TPGIS-Finalite"] = FINALITE
    r = client.get(f"{API}/personnes/{personne['id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["trace_audit"]


def test_recherche_nationale_reservee(client, connexions):
    h = connexions.entetes("officier.ndj")
    r = client.post(
        f"{API}/recherche", headers=h, json={"finalite": "Test de portée", "nom": "ABAKAR", "etendre_national": True}
    )
    assert r.status_code == 403


def test_injection_sql_inoperante(client, connexions):
    h = connexions.entetes("officier.ndj", FINALITE)
    for charge in ["' OR '1'='1", "%'; DROP TABLE plaintes; --", '" OR 1=1 --']:
        r = client.get(f"{API}/plaintes", headers=h, params={"numero": charge})
        assert r.status_code == 200 and r.json()["total"] == 0
        r = client.get(f"{API}/personnes", headers=h, params={"texte": charge})
        assert r.status_code == 200
        r = client.post(f"{API}/recherche", headers=h, json={"finalite": "Test injection", "nom": charge})
        assert r.status_code == 200
    assert client.get(f"{API}/plaintes", headers=h).json()["total"] > 0


def test_elevation_privileges_par_attribution_role_refusee(client, connexions):
    h = connexions.entetes("admin.fonctionnel")
    roles = {r["code"]: r for r in client.get(f"{API}/roles", headers=h).json()}
    utilisateurs = client.get(f"{API}/utilisateurs", headers=h, params={"texte": "accueil.abc"}).json()["elements"]
    cible = utilisateurs[0]
    # Attribution d'un role privilegie : demande de double validation, pas d'effet immediat.
    r = client.post(
        f"{API}/utilisateurs/{cible['id']}/role",
        headers=h,
        json={"role_id": roles["ADMIN_FONCTIONNEL"]["id"], "motif": "Demande de test de privilège"},
    )
    assert r.status_code == 200
    assert r.json()["statut"] == "EN_ATTENTE"
    demande = r.json()["demande_validation"]
    # Le demandeur ne peut pas valider sa propre demande.
    r = client.post(f"{API}/validations/{demande['id']}/decision", headers=h, json={"approuver": True})
    assert r.status_code == 403
    apres = client.get(f"{API}/utilisateurs", headers=h, params={"texte": "accueil.abc"}).json()["elements"][0]
    assert apres["role_id"] == cible["role_id"]
    # Un compte ne peut pas modifier son propre role.
    moi = client.get(f"{API}/auth/moi", headers=h).json()
    r = client.post(
        f"{API}/utilisateurs/{moi['id']}/role",
        headers=h,
        json={"role_id": roles["AUDITEUR"]["id"], "motif": "Auto attribution interdite"},
    )
    assert r.status_code == 403


def test_refus_journalises(client, connexions, app):
    h = connexions.entetes("accueil.ndj")
    client.get(f"{API}/audit", headers=h)
    h_aud = connexions.entetes("auditeur")
    evenements = client.get(f"{API}/audit", headers=h_aud, params={"action": "ACCES_REFUSE"}).json()["elements"]
    assert any(e["identifiant"] == "accueil.ndj" and e["details"]["chemin"] == "/api/v1/audit" for e in evenements)
