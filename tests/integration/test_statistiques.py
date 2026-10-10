"""Tableau de bord, cartographie agregee et exports traces."""

from __future__ import annotations

API = "/api/v1"


def test_tableau_de_bord_calcule_sur_donnees_reelles(client, connexions, app):
    from sqlalchemy import text

    h = connexions.entetes("responsable.ndj")
    stats = client.get(f"{API}/statistiques/tableau-de-bord", headers=h).json()
    unites = {u["id"] for u in client.get(f"{API}/unites", headers=h).json()
              if u["code"] in ("CP-NDJ", "CP-NDJ-A1")}
    marqueurs = ",".join(f"'{u}'" for u in unites)
    with app.state.fabrique.moteur.connect() as c:
        attendu = c.execute(text(f"SELECT COUNT(*) FROM plaintes WHERE unite_id IN ({marqueurs})")).scalar()
    assert stats["indicateurs"]["plaintes_total"] == attendu
    assert sum(stats["par_statut"].values()) == attendu
    assert sum(c["nombre"] for c in stats["par_categorie"]) == attendu
    assert 0 <= stats["qualite_donnees"]["plaintes_avec_categorie_pct"] <= 100


def test_statistiques_sans_donnees_nominatives(client, connexions):
    h = connexions.entetes("responsable.ndj")
    texte = client.get(f"{API}/statistiques/tableau-de-bord", headers=h).text
    carte = client.get(f"{API}/carte/donnees", headers=h).text
    for nom in ("ABAKAR", "MAHAMAT", "Achta", "\"prenoms\"", "\"date_naissance\"", "numero_interne"):
        assert nom not in texte and nom not in carte


def test_carte_agregats_par_province_et_filtres(client, connexions):
    h = connexions.entetes("responsable.ndj")
    carte = client.get(f"{API}/carte/donnees", headers=h, params={"du": "2020-01-01"}).json()
    provinces = {p["province_code"]: p for p in carte["provinces"]}
    assert set(provinces) == {"TD-ND"}  # perimetre : N'Djamena uniquement
    assert any(u["code"] == "CP-ABC" and not u["dans_perimetre"] for u in carte["unites"])
    categorie = client.get(f"{API}/categories", headers=h).json()[0]["id"]
    filtree = client.get(f"{API}/carte/donnees", headers=h,
                         params={"du": "2020-01-01", "categorie_id": categorie}).json()
    total_filtre = sum(p["plaintes"] or 0 for p in filtree["provinces"])
    assert total_filtre <= provinces["TD-ND"]["plaintes"]
    assert client.get(f"{API}/carte/donnees", headers=h, params={"du": "2026-05-01", "au": "2026-01-01"}
                      ).status_code == 422


def test_seuil_de_confidentialite(client, connexions):
    h_admin = connexions.entetes("admin.technique")
    connexions.reauthentifier("admin.technique", h_admin)
    client.put(f"{API}/parametres/statistiques.seuil_confidentialite", headers=h_admin, json={"valeur": 100000})
    h = connexions.entetes("responsable.ndj")
    carte = client.get(f"{API}/carte/donnees", headers=h, params={"du": "2020-01-01"}).json()
    assert all(p["plaintes"] is None and p["plaintes_masquees"] for p in carte["provinces"] if p["plaintes"] != 0)


def test_exports_reserves_et_traces(client, connexions):
    h_off = connexions.entetes("officier.ndj")
    assert client.get(f"{API}/statistiques/export.csv", headers=h_off).status_code == 403
    h = connexions.entetes("responsable.ndj")
    r = client.get(f"{API}/statistiques/export.csv", headers=h)
    assert r.status_code == 200, r.text
    assert r.content.startswith("﻿".encode()) and b"indicateur;plaintes_total" in r.content
    r = client.get(f"{API}/statistiques/rapport.pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    h_aud = connexions.entetes("auditeur")
    actions = {e["action"] for e in client.get(f"{API}/audit", headers=h_aud, params={"taille": 200}).json()["elements"]}
    assert {"EXPORT_STATISTIQUES_CSV", "EXPORT_RAPPORT_PDF"} <= actions


def test_consultation_seule_voit_indicateurs_de_son_unite(client, connexions):
    h = connexions.entetes("consultation.ndj")
    assert client.get(f"{API}/statistiques/tableau-de-bord", headers=h).status_code == 200
    h_acc = connexions.entetes("accueil.ndj")
    assert client.get(f"{API}/statistiques/tableau-de-bord", headers=h_acc).status_code == 403
