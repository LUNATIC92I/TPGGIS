"""Personnes (doublons, fusion validee), faits et dossiers."""

from __future__ import annotations

from tests.conftest import FINALITE

API = "/api/v1"

PERSONNE = {"nom": "DJIMTOLOUM", "prenoms": "Fictif Exemple", "date_naissance": "1985-03-12",
            "lieu_naissance": "Sarh", "type_document": "CARTE_NATIONALE", "numero_document": "TEST-000111"}


def test_detection_doublons_et_validation_humaine(client, connexions):
    h = connexions.entetes("officier.ndj", FINALITE)
    r = client.post(f"{API}/personnes", headers=h, json=PERSONNE)
    assert r.status_code == 201, r.text
    premiere = r.json()
    # Meme identite : la creation est bloquee tant que l'agent ne confirme pas.
    r = client.post(f"{API}/personnes", headers=h, json={**PERSONNE, "prenoms": "Fictif  exemple"})
    assert r.status_code == 409 and r.json()["code"] == "DOUBLONS_POTENTIELS"
    candidats = r.json()["details"]["candidats"]
    assert candidats[0]["id"] == premiere["id"]
    assert candidats[0]["niveau"] == "ELEVE"
    assert "numero_document" in candidats[0]["attributs_concordants"]
    r = client.post(f"{API}/personnes", headers=h, json={**PERSONNE, "confirmer_malgre_doublons": True})
    assert r.status_code == 201
    assert r.json()["id"] != premiere["id"]


def test_homonymie_seule_ne_cree_pas_de_correspondance_forte(client, connexions):
    h = connexions.entetes("officier.ndj", FINALITE)
    client.post(f"{API}/personnes", headers=h, json={"nom": "HOMONYME", "prenoms": "Jean",
                                                    "date_naissance": "1970-01-01"})
    # Meme nom, autre date de naissance : creation sans blocage.
    r = client.post(f"{API}/personnes", headers=h, json={"nom": "HOMONYME", "prenoms": "Jean",
                                                        "date_naissance": "1999-09-09"})
    assert r.status_code == 201
    candidats = client.post(f"{API}/personnes/doublons", headers=h,
                            json={"nom": "HOMONYME", "prenoms": "Jean"}).json()
    assert len(candidats) == 2
    assert all(c["niveau"] == "FAIBLE" for c in candidats)
    assert any("homonymie" in a for c in candidats for a in c["ambiguites"])


def test_fusion_soumise_a_double_validation(client, connexions):
    h_off = connexions.entetes("officier.ndj", FINALITE)
    a = client.post(f"{API}/personnes", headers=h_off, json={"nom": "FUSION", "prenoms": "Alpha",
                                                            "date_naissance": "1980-02-02"}).json()
    b = client.post(f"{API}/personnes", headers=h_off, json={"nom": "FUSIONN", "prenoms": "Alpha",
                                                            "date_naissance": "1980-02-02",
                                                            "confirmer_malgre_doublons": True}).json()
    plainte = client.post(f"{API}/plaintes", headers=h_off, json={
        "service_enregistrement": "Accueil", "description": "Plainte fictive liée à la fiche B.",
        "personnes": [{"personne_id": b["id"], "role": "VICTIME"}]}).json()
    r = client.post(f"{API}/personnes/fusions", headers=h_off, json={
        "personne_conservee_id": a["id"], "personne_absorbee_id": b["id"],
        "motif": "Même personne : erreur de saisie du nom confirmée sur pièce"})
    assert r.status_code == 202
    demande = r.json()
    # Aucun effet avant validation.
    assert client.get(f"{API}/personnes/{b['id']}", headers=h_off).json()["statut"] == "ACTIVE"
    assert client.post(f"{API}/validations/{demande['id']}/decision", headers=h_off,
                       json={"approuver": True}).status_code == 403
    h_resp = connexions.entetes("responsable.ndj", FINALITE)
    r = client.post(f"{API}/validations/{demande['id']}/decision", headers=h_resp,
                    json={"approuver": True, "commentaire": "Vérifié"})
    assert r.status_code == 200, r.text
    assert r.json()["statut"] == "EXECUTEE"
    assert client.get(f"{API}/personnes/{b['id']}", headers=h_off).json()["statut"] == "FUSIONNEE"
    detail_a = client.get(f"{API}/personnes/{a['id']}", headers=h_off).json()
    assert any(lien["id"] == plainte["id"] for lien in detail_a["liens"])
    assert "FUSIONN Alpha" in detail_a["alias"]


def test_roles_multiples_d_une_meme_personne(client, connexions):
    h = connexions.entetes("officier.ndj", FINALITE)
    p = client.post(f"{API}/personnes", headers=h, json={"nom": "MULTIROLE", "prenoms": "Test",
                                                        "confirmer_malgre_doublons": True}).json()
    for role in ("PLAIGNANT", "TEMOIN"):
        client.post(f"{API}/plaintes", headers=h, json={
            "service_enregistrement": "Accueil", "description": f"Plainte fictive où la personne est {role}.",
            "personnes": [{"personne_id": p["id"], "role": role}]})
    roles = {lien["role"] for lien in client.get(f"{API}/personnes/{p['id']}", headers=h).json()["liens"]}
    assert roles == {"PLAIGNANT", "TEMOIN"}


def test_donnees_inconnues_peuvent_rester_vides(client, connexions):
    h = connexions.entetes("accueil.ndj", FINALITE)
    r = client.post(f"{API}/personnes", headers=h, json={"nom": "INCONNU"})
    assert r.status_code == 201
    d = client.get(f"{API}/personnes/{r.json()['id']}", headers=h).json()
    assert d["date_naissance"] is None and d["sexe"] is None and d["numero_document"] is None


def test_modification_dossier_et_actes(client, connexions):
    h = connexions.entetes("officier.ndj", FINALITE)
    plainte = client.get(f"{API}/plaintes", headers=h, params={"taille": 1}).json()["elements"][0]
    d = client.post(f"{API}/dossiers", headers=h, json={
        "intitule": "Dossier fictif de test", "type_procedure": "ENQUETE_PRELIMINAIRE",
        "plaintes_ids": [plainte["id"]]}).json()
    assert d["numero"].startswith("DO-CP-NDJ-")
    r = client.post(f"{API}/dossiers/{d['id']}/actes", headers=h, json={
        "type_acte": "AUDITION", "reference": "PV-TEST-001", "date_acte": "2026-02-01",
        "resume": "Audition fictive."})
    assert r.status_code == 201
    r = client.patch(f"{API}/dossiers/{d['id']}", headers=h, json={"version": d["version"], "statut": "EN_COURS"})
    assert r.status_code == 200
    v = r.json()["version"]
    r = client.patch(f"{API}/dossiers/{d['id']}", headers=h, json={"version": v, "statut": "CLOTURE",
                                                                   "motif_cloture": "Classement fictif"})
    assert r.status_code == 403  # l'officier n'a pas dossier.cloturer
    h_resp = connexions.entetes("responsable.ndj")
    r = client.patch(f"{API}/dossiers/{d['id']}", headers=h_resp, json={
        "version": v, "statut": "CLOTURE", "motif_cloture": "Transmission et classement fictifs"})
    assert r.status_code == 200, r.text
    detail = client.get(f"{API}/dossiers/{d['id']}", headers=h_resp).json()
    assert detail["date_cloture"] and detail["actes"][0]["reference"] == "PV-TEST-001"
    assert detail["plaintes"][0]["id"] == plainte["id"]


def test_fait_decision_judiciaire_exige_reference(client, connexions):
    h = connexions.entetes("officier.ndj")
    categorie = client.get(f"{API}/categories", headers=h).json()[0]["id"]
    corps = {"categorie_id": categorie, "description": "Fait fictif pour le test de nature.",
             "source_information": "CONSTAT_AGENT", "nature_information": "DECISION_JUDICIAIRE"}
    assert client.post(f"{API}/faits", headers=h, json=corps).status_code == 422
    r = client.post(f"{API}/faits", headers=h, json={**corps, "references_actes": "Jugement fictif n° 12/2026"})
    assert r.status_code == 201
    f = r.json()
    assert f["nature_information"] == "DECISION_JUDICIAIRE" and f["etat_verification"] == "NON_VERIFIE"
    # Aucun score de dangerosite ni qualification automatique n'existe dans la reponse.
    assert not any("danger" in k or "score" in k or "coupable" in k for k in f)


def test_categories_administrables_sans_code(client, connexions):
    h = connexions.entetes("admin.fonctionnel")
    r = client.post(f"{API}/categories", headers=h, json={"code": "TEST_NOUVELLE", "libelle": "Catégorie test",
                                                          "validee": True})
    assert r.status_code == 422
    r = client.post(f"{API}/categories", headers=h, json={
        "code": "TEST_NOUVELLE", "libelle": "Catégorie test", "validee": True,
        "validee_par": "Autorité fictive"})
    assert r.status_code == 201
    r = client.patch(f"{API}/categories/{r.json()['id']}", headers=h, json={"active": False})
    assert r.json()["active"] is False
    h_off = connexions.entetes("officier.ndj")
    assert "TEST_NOUVELLE" not in {c["code"] for c in client.get(f"{API}/categories", headers=h_off).json()}
