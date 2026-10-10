"""Tests unitaires : chiffrement, mots de passe, MFA, nettoyage d'audit,
detection de doublons et controle des signatures de fichiers."""

from __future__ import annotations

import base64
from datetime import date

import pyotp
import pytest

from tpgis.server.security import crypto, mfa, passwords
from tpgis.server.services.audit import nettoyer_details
from tpgis.server.services.documents import verifier_signature
from tpgis.server.services.erreurs import DonneesInvalides
from tpgis.server.services.personnes import evaluer_correspondance, niveau


def test_chiffrement_aller_retour_et_rotation():
    k1, k2 = crypto.generer_cle(), crypto.generer_cle()
    ancien = crypto.ChiffreurChamps(crypto.analyser_trousseau(f"k1:{k1}"), "k1")
    valeur = ancien.chiffrer("Donnée sensible é")
    assert valeur.startswith("k1$") and "sensible" not in valeur
    nouveau = crypto.ChiffreurChamps(crypto.analyser_trousseau(f"k1:{k1},k2:{k2}"), "k2")
    assert nouveau.dechiffrer(valeur) == "Donnée sensible é"
    assert nouveau.chiffrer("x").startswith("k2$")
    assert ancien.chiffrer("x") != ancien.chiffrer("x")  # nonce aleatoire


def test_alteration_detectee():
    c = crypto.ChiffreurChamps(crypto.analyser_trousseau(f"k1:{crypto.generer_cle()}"), "k1")
    v = c.chiffrer("abc")
    ident, charge = v.split("$")
    brut = bytearray(base64.b64decode(charge))
    brut[-1] ^= 1
    with pytest.raises(crypto.ErreurChiffrement):
        c.dechiffrer(f"{ident}${base64.b64encode(bytes(brut)).decode()}")


def test_cle_invalide_refusee():
    with pytest.raises(crypto.ErreurChiffrement):
        crypto.analyser_trousseau("k1:" + base64.b64encode(b"court").decode())


def test_index_aveugle_normalise():
    idx = crypto.IndexAveugle(b"x" * 32)
    assert idx.calculer("ab-123 456") == idx.calculer("AB123456")
    assert idx.calculer("AB123456") != crypto.IndexAveugle(b"y" * 32).calculer("AB123456")
    assert idx.calculer(None) is None


def test_argon2id_et_politique():
    empreinte = passwords.hacher("Mot-De-Passe-Solide-1")
    assert empreinte.startswith("$argon2id$")
    assert passwords.verifier(empreinte, "Mot-De-Passe-Solide-1")
    assert not passwords.verifier(empreinte, "autre")
    assert not passwords.verifier(None, "x")
    assert passwords.controler_politique("court", 12)
    assert passwords.controler_politique("toutenminusculeslong", 12)
    assert passwords.controler_politique("Agent.Dupont-2026", 12, "agent.dupont")
    assert passwords.controler_politique("Correct-Horse-9", 12) == []


def test_totp_anti_rejeu():
    secret = mfa.generer_secret()
    code = pyotp.TOTP(secret).now()
    pas = mfa.verifier_code(secret, code)
    assert pas is not None
    assert mfa.verifier_code(secret, code, pas) is None
    assert mfa.verifier_code(secret, "12a456") is None


def test_nettoyage_audit():
    details = nettoyer_details({"mot_de_passe": "secret", "jeton_session": "abc", "reference_modele": "SIM-1",
                                "nom": "ABAKAR", "imbrique": {"code_mfa": "123456", "statut": "OK"},
                                "texte": "x" * 2000})
    assert details["mot_de_passe"] == details["jeton_session"] == details["reference_modele"] == "[masqué]"
    assert details["imbrique"] == {"code_mfa": "[masqué]", "statut": "OK"}
    assert details["nom"] == "ABAKAR" and len(details["texte"]) == 500


class _P:
    def __init__(self, nom, prenoms=None, date_naissance=None, lieu=None, idx=None):
        self.nom, self.prenoms, self.date_naissance = nom, prenoms, date_naissance
        self.lieu_naissance, self.index_document = lieu, idx


def test_score_doublons_multi_attributs():
    p = _P("MAHAMAT", "Ali Saleh", date(1980, 1, 2), "Abéché", "IDX")
    score, concordants, _ = evaluer_correspondance(p, "Mahamat", "Saleh Ali", date(1980, 1, 2), "ABECHE", "IDX")
    assert score == 100 and niveau(score) == "ELEVE"
    assert {"nom", "prenoms", "date_naissance", "lieu_naissance", "numero_document"} <= set(concordants)
    score, _, ambiguites = evaluer_correspondance(p, "MAHAMAT", "Ali Saleh", None, None, None)
    assert niveau(score) == "FAIBLE" and any("homonymie" in a for a in ambiguites)
    score, _, ambiguites = evaluer_correspondance(p, "MAHAMAT", "Ali Saleh", date(1990, 5, 5), None, None)
    assert score < 40 and "Dates de naissance différentes" in ambiguites


@pytest.mark.parametrize("extension,contenu", [
    ("pdf", b"%PDF-1.7 ..."), ("png", b"\x89PNG\r\n\x1a\nxxxx"), ("jpg", b"\xff\xd8\xff\xe0xx"),
    ("tif", b"II*\x00xx"), ("txt", "texte accentué".encode()),
])
def test_signatures_valides(extension, contenu):
    verifier_signature(contenu, extension)


@pytest.mark.parametrize("extension,contenu", [
    ("pdf", b"MZ\x90"), ("png", b"%PDF"), ("jpg", b"GIF89a"), ("txt", b"\xff\xfe\x00"), ("docx", b"PK\x03\x04abc"),
])
def test_signatures_invalides(extension, contenu):
    with pytest.raises(DonneesInvalides):
        verifier_signature(contenu, extension)
