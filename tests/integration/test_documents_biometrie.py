"""Pieces jointes (validation, antivirus, integrite, versions) et biometrie simulee."""

from __future__ import annotations

import io
import zipfile

from tpgis.server.database.models import VersionDocument
from tpgis.server.services.antivirus import EICAR
from tests.conftest import FINALITE

API = "/api/v1"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _plainte(client, h):
    return client.get(f"{API}/plaintes", headers=h, params={"taille": 1}).json()["elements"][0]


def _deposer(client, h, plainte_id, nom, contenu, type_piece="PIECE_JUSTIFICATIVE"):
    return client.post(f"{API}/documents", headers=h, data={"intitule": "Pièce de test", "type_piece": type_piece,
                                                            "plainte_id": plainte_id},
                       files={"fichier": (nom, contenu, "application/octet-stream")})


def test_depot_et_telechargement_avec_integrite(client, connexions, app, parametres):
    h = connexions.entetes("officier.ndj")
    p = _plainte(client, h)
    r = _deposer(client, h, p["id"], "certificat.pdf", PDF)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["disponible"] and doc["versions"][0]["statut_analyse"] == "SAIN"
    r = client.get(f"{API}/documents/{doc['id']}/contenu", headers=h)
    assert r.status_code == 200 and r.content == PDF
    # Le fichier stocke est chiffre : son contenu en clair n'apparait pas.
    with app.state.fabrique.transaction() as bd:
        chemin = bd.query(VersionDocument).filter_by(document_id=doc["id"]).one().chemin_stockage
    brut = (parametres.repertoire_stockage / chemin).read_bytes()
    assert b"%PDF" not in brut
    # Alteration du stockage : detectee au telechargement.
    (parametres.repertoire_stockage / chemin).write_bytes(brut[:-1] + bytes([brut[-1] ^ 1]))
    assert client.get(f"{API}/documents/{doc['id']}/contenu", headers=h).status_code == 400


def test_extension_et_signature_controlees(client, connexions):
    h = connexions.entetes("officier.ndj")
    p = _plainte(client, h)
    assert _deposer(client, h, p["id"], "script.exe", b"MZ\x90\x00").status_code == 422
    r = _deposer(client, h, p["id"], "faux.pdf", b"MZ\x90\x00 executable deguise")
    assert r.status_code == 422 and "ne correspond pas" in r.json()["detail"]
    assert _deposer(client, h, p["id"], "vide.pdf", b"").status_code == 422
    assert _deposer(client, h, p["id"], "binaire.txt", b"abc\x00def").status_code == 422
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w/>")
        z.writestr("word/vbaProject.bin", "macro")
    assert _deposer(client, h, p["id"], "macro.docx", tampon.getvalue()).status_code == 422


def test_taille_maximale_configurable(client, connexions):
    h_admin = connexions.entetes("admin.technique")
    connexions.reauthentifier("admin.technique", h_admin)
    r = client.put(f"{API}/parametres/documents.taille_max_octets", headers=h_admin, json={"valeur": 100})
    assert r.status_code == 200, r.text
    h = connexions.entetes("officier.ndj")
    r = _deposer(client, h, _plainte(client, h)["id"], "gros.pdf", PDF + b"0" * 200)
    assert r.status_code == 422 and "volumineux" in r.json()["detail"]


def test_fichier_infecte_jamais_disponible(client, connexions, app):
    h = connexions.entetes("officier.ndj")
    r = _deposer(client, h, _plainte(client, h)["id"], "note.txt", EICAR)
    assert r.status_code == 201
    doc = r.json()
    assert doc["versions"][0]["statut_analyse"] == "INFECTE" and not doc["disponible"]
    assert client.get(f"{API}/documents/{doc['id']}/contenu", headers=h).status_code == 409
    with app.state.fabrique.transaction() as bd:
        assert bd.query(VersionDocument).filter_by(document_id=doc["id"]).one().chemin_stockage == ""


def test_versions_et_acces_selon_dossier(client, connexions):
    h = connexions.entetes("officier.ndj")
    p = _plainte(client, h)
    doc = _deposer(client, h, p["id"], "v1.txt", "version 1".encode()).json()
    r = client.post(f"{API}/documents/{doc['id']}/versions", headers=h,
                    files={"fichier": ("v2.txt", "version 2".encode(), "text/plain")})
    assert r.status_code == 201 and r.json()["version_courante"] == 2
    assert client.get(f"{API}/documents/{doc['id']}/contenu", headers=h).content == b"version 2"
    assert client.get(f"{API}/documents/{doc['id']}/contenu", headers=h, params={"version": 1}).content == b"version 1"
    h_abc = connexions.entetes("officier.abc")
    assert client.get(f"{API}/documents/{doc['id']}/contenu", headers=h_abc).status_code == 404
    assert client.get(f"{API}/documents", headers=h_abc, params={"plainte_id": p["id"]}).status_code == 404


def test_biometrie_simulee_verification_un_pour_un(client, connexions):
    h = connexions.entetes("officier.ndj", FINALITE)
    personne = client.get(f"{API}/personnes", headers=h, params={"taille": 1}).json()["elements"][0]
    r = client.post(f"{API}/biometrie/captures", headers=h, json={
        "personne_id": personne["id"], "position_doigt": "POUCE_DROIT", "equipement": "Capteur simulé",
        "fondement_legal": "Fondement juridique fictif pour le test", "consentement_recueilli": True})
    assert r.status_code == 201, r.text
    capture = r.json()
    assert capture["est_synthetique"] is True and capture["adaptateur"] == "simulation"
    assert "reference_modele" not in capture
    r = client.post(f"{API}/biometrie/verifications", headers=h,
                    json={"capture_id": capture["id"], "equipement": "Capteur simulé"})
    assert r.status_code == 200 and r.json()["synthetique"] is True
    assert "SIMULÉ" in r.json()["commentaire"]
    # Recherche 1 contre N : desactivee.
    assert client.post(f"{API}/biometrie/recherches", headers=h).status_code == 503


def test_biometrie_exige_finalite(client, connexions):
    h = connexions.entetes("officier.ndj")
    personne = client.get(f"{API}/personnes", headers=h, params={"taille": 1}).json()["elements"][0]
    r = client.get(f"{API}/biometrie/personnes/{personne['id']}/captures", headers=h)
    assert r.status_code == 422 and r.json()["code"] == "FINALITE_REQUISE"


def test_suppression_capture_double_validation(client, connexions):
    h = connexions.entetes("officier.ndj", FINALITE)
    personne = client.get(f"{API}/personnes", headers=h, params={"taille": 1}).json()["elements"][0]
    capture = client.post(f"{API}/biometrie/captures", headers=h, json={
        "personne_id": personne["id"], "position_doigt": "INDEX_GAUCHE", "equipement": "Capteur simulé",
        "fondement_legal": "Fondement juridique fictif pour le test", "consentement_recueilli": True}).json()
    # L'officier n'a pas la permission de demander une suppression.
    r = client.post(f"{API}/biometrie/captures/{capture['id']}/suppression", headers=h,
                    json={"motif": "Fin de la procédure fictive"})
    assert r.status_code == 403
