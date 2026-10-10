"""Creation, modification, statuts et recherche des plaintes (donnees synthetiques)."""

from __future__ import annotations

from tests.conftest import FINALITE

API = "/api/v1"


def _categorie(client, h):
    return client.get(f"{API}/categories", headers=h).json()[0]["id"]


def _nouvelle_plainte(client, h, **extra):
    corps = {
        "service_enregistrement": "Accueil du commissariat (test)",
        "categorie_id": _categorie(client, h),
        "description": "Description fictive des faits allégués pour le test automatisé.",
        "date_faits": "2026-01-15",
        "lieu_faits": "Quartier fictif 12",
        **extra,
    }
    return client.post(f"{API}/plaintes", headers=h, json=corps)


def test_creation_plainte_numero_unique_et_statut_initial(client, connexions):
    h = connexions.entetes("accueil.ndj")
    r1 = _nouvelle_plainte(client, h)
    r2 = _nouvelle_plainte(client, h)
    assert r1.status_code == 201, r1.text
    p1, p2 = r1.json(), r2.json()
    assert p1["statut"] == "NOUVELLE"
    assert p1["numero"].startswith("PL-CP-NDJ-")
    assert p1["numero"] != p2["numero"]
    assert int(p2["numero"].rsplit("-", 1)[1]) == int(p1["numero"].rsplit("-", 1)[1]) + 1


def test_creation_avec_personnes_et_roles(client, connexions):
    h = connexions.entetes("officier.ndj")
    personne = client.post(
        f"{API}/personnes",
        headers=h,
        json={
            "nom": "TESTNOM",
            "prenoms": "Unique",
            "date_naissance": "1990-05-04",
            "confirmer_malgre_doublons": True,
        },
    ).json()
    r = _nouvelle_plainte(client, h, personnes=[{"personne_id": personne["id"], "role": "PLAIGNANT"}])
    assert r.status_code == 201
    detail = client.get(f"{API}/plaintes/{r.json()['id']}", headers=h).json()
    assert detail["personnes"][0]["role"] == "PLAIGNANT"
    assert detail["description"].startswith("Description fictive")


def test_validation_entrees(client, connexions):
    h = connexions.entetes("accueil.ndj")
    r = client.post(f"{API}/plaintes", headers=h, json={"service_enregistrement": "x", "description": "court"})
    assert r.status_code == 422
    assert r.json()["code"] == "DONNEES_INVALIDES"
    r = _nouvelle_plainte(client, h, date_faits="2999-01-01")
    assert r.status_code == 422
    # Champ inconnu refuse (protection contre l'affectation de masse).
    r = _nouvelle_plainte(client, h, statut="CLOTUREE")
    assert r.status_code == 422


def test_modification_avec_controle_de_version(client, connexions):
    h = connexions.entetes("officier.ndj")
    p = _nouvelle_plainte(client, h).json()
    r = client.patch(
        f"{API}/plaintes/{p['id']}", headers=h, json={"version": p["version"], "lieu_faits": "Nouveau lieu fictif"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == p["version"] + 1
    # Une seconde modification fondee sur l'ancienne version est refusee.
    r = client.patch(f"{API}/plaintes/{p['id']}", headers=h, json={"version": p["version"], "lieu_faits": "Autre"})
    assert r.status_code == 409
    assert r.json()["code"] == "VERSION_OBSOLETE"
    historique = client.get(f"{API}/plaintes/{p['id']}", headers=h).json()["historique"]
    assert [x["action"] for x in historique] == ["CREATION", "MODIFICATION"]
    assert historique[1]["changements"]["lieu_faits"]["apres"] == "Nouveau lieu fictif"


def test_cloture_exige_motif_et_habilitation(client, connexions):
    h_accueil = connexions.entetes("accueil.ndj")
    p = _nouvelle_plainte(client, h_accueil).json()
    r = client.post(
        f"{API}/plaintes/{p['id']}/statut",
        headers=h_accueil,
        json={"version": p["version"], "statut": "CLOTUREE", "motif": "Motif suffisamment long"},
    )
    assert r.status_code == 403
    h = connexions.entetes("officier.ndj")
    r = client.post(f"{API}/plaintes/{p['id']}/statut", headers=h, json={"version": p["version"], "statut": "CLOTUREE"})
    assert r.status_code == 422
    r = client.post(
        f"{API}/plaintes/{p['id']}/statut",
        headers=h,
        json={"version": p["version"], "statut": "CLOTUREE", "motif": "Désistement écrit du plaignant"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["statut"] == "CLOTUREE"
    # Une plainte cloturee n'est plus modifiable.
    r = client.patch(f"{API}/plaintes/{p['id']}", headers=h, json={"version": r.json()["version"], "lieu_faits": "x"})
    assert r.status_code == 409


def test_transitions_interdites_et_transmission(client, connexions):
    h = connexions.entetes("officier.ndj")
    p = _nouvelle_plainte(client, h).json()
    r = client.post(
        f"{API}/plaintes/{p['id']}/statut",
        headers=h,
        json={"version": p["version"], "statut": "ARCHIVEE", "motif": "Archivage direct interdit"},
    )
    assert r.status_code == 422
    r = client.post(
        f"{API}/plaintes/{p['id']}/statut", headers=h, json={"version": p["version"], "statut": "TRANSMISE"}
    )
    assert r.status_code == 422
    r = client.post(
        f"{API}/plaintes/{p['id']}/statut",
        headers=h,
        json={"version": p["version"], "statut": "TRANSMISE", "service_destinataire": "Parquet fictif"},
    )
    assert r.status_code == 200


def test_recherche_par_numero(client, connexions):
    h = connexions.entetes("officier.ndj", FINALITE)
    p = _nouvelle_plainte(client, h).json()
    liste = client.get(f"{API}/plaintes", headers=h, params={"numero": p["numero"]}).json()
    assert liste["total"] == 1 and liste["elements"][0]["id"] == p["id"]
    r = client.post(
        f"{API}/recherche", headers=h, json={"finalite": "Vérification test", "numero_plainte": p["numero"]}
    )
    assert r.status_code == 200
    resultat = r.json()
    assert resultat["resultats"]["plaintes"][0]["niveau"] == "EXACT"
    assert resultat["trace_audit"]


def test_pagination(client, connexions):
    h = connexions.entetes("responsable.ndj")
    page1 = client.get(f"{API}/plaintes", headers=h, params={"taille": 5, "page": 1}).json()
    page2 = client.get(f"{API}/plaintes", headers=h, params={"taille": 5, "page": 2}).json()
    assert len(page1["elements"]) == 5
    assert {x["id"] for x in page1["elements"]}.isdisjoint({x["id"] for x in page2["elements"]})
    assert client.get(f"{API}/plaintes", headers=h, params={"taille": 5000}).status_code == 422


def test_fiche_et_bordereau_pdf(client, connexions):
    h = connexions.entetes("officier.ndj")
    p = _nouvelle_plainte(client, h).json()
    r = client.get(f"{API}/plaintes/{p['id']}/fiche.pdf", headers=h)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    assert "attachment" in r.headers["content-disposition"]
    r = client.get(f"{API}/plaintes/{p['id']}/bordereau.pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
