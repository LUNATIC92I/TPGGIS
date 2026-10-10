"""Chiffrement des donnees sensibles au repos.

AES 256 GCM avec trousseau de cles identifiees, permettant la rotation :
les nouvelles valeurs sont chiffrees avec la cle active, les anciennes restent
lisibles tant que leur cle figure dans le trousseau.

Format stocke : "<id_cle>$<base64(nonce 12 octets + texte chiffre + tag)>".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import unicodedata
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TAILLE_CLE = 32


class ErreurChiffrement(RuntimeError):
    pass


def generer_cle() -> str:
    return base64.b64encode(os.urandom(TAILLE_CLE)).decode()


def _decoder_cle(valeur: str) -> bytes:
    cle = base64.b64decode(valeur.strip())
    if len(cle) != TAILLE_CLE:
        raise ErreurChiffrement("Une cle de chiffrement doit faire 32 octets (256 bits).")
    return cle


def analyser_trousseau(texte: str) -> dict[str, bytes]:
    trousseau: dict[str, bytes] = {}
    for element in filter(None, (e.strip() for e in texte.split(","))):
        if ":" not in element:
            raise ErreurChiffrement("Format de cle attendu : identifiant:base64")
        ident, valeur = element.split(":", 1)
        if not ident.isalnum():
            raise ErreurChiffrement("Identifiant de cle invalide.")
        trousseau[ident] = _decoder_cle(valeur)
    return trousseau


class ChiffreurChamps:
    def __init__(self, trousseau: dict[str, bytes], cle_active: str, contexte: bytes = b"tpgis-champ"):
        if cle_active not in trousseau:
            raise ErreurChiffrement(f"La cle active {cle_active!r} est absente du trousseau.")
        self._trousseau = {k: AESGCM(v) for k, v in trousseau.items()}
        self._active = cle_active
        self._contexte = contexte

    @property
    def cle_active(self) -> str:
        return self._active

    def chiffrer(self, texte: str) -> str:
        nonce = os.urandom(12)
        donnees = self._trousseau[self._active].encrypt(nonce, texte.encode("utf-8"), self._contexte)
        return f"{self._active}${base64.b64encode(nonce + donnees).decode()}"

    def dechiffrer(self, valeur: str) -> str:
        try:
            ident, charge = valeur.split("$", 1)
            brut = base64.b64decode(charge)
            aes = self._trousseau[ident]
        except (ValueError, KeyError) as exc:
            raise ErreurChiffrement("Valeur chiffree illisible ou cle inconnue.") from exc
        try:
            return aes.decrypt(brut[:12], brut[12:], self._contexte).decode("utf-8")
        except Exception as exc:  # InvalidTag
            raise ErreurChiffrement("Integrite de la valeur chiffree non verifiee.") from exc

    def chiffrer_octets(self, donnees: bytes) -> tuple[str, bytes]:
        nonce = os.urandom(12)
        return self._active, nonce + self._trousseau[self._active].encrypt(nonce, donnees, b"tpgis-fichier")

    def dechiffrer_octets(self, ident: str, donnees: bytes) -> bytes:
        try:
            return self._trousseau[ident].decrypt(donnees[:12], donnees[12:], b"tpgis-fichier")
        except KeyError as exc:
            raise ErreurChiffrement("Cle de fichier inconnue.") from exc
        except Exception as exc:
            raise ErreurChiffrement("Integrite du fichier non verifiee.") from exc


def normaliser_texte(texte: str) -> str:
    """Normalisation pour comparaison : majuscules, sans accents, espaces reduits."""
    decompose = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    propre = "".join(c if c.isalnum() else " " for c in sans_accents.upper())
    return " ".join(propre.split())


class IndexAveugle:
    """HMAC SHA 256 permettant une recherche exacte sans stocker la valeur en clair."""

    def __init__(self, cle: bytes):
        self._cle = cle

    def calculer(self, valeur: str | None) -> str | None:
        if not valeur:
            return None
        normalise = normaliser_texte(valeur).replace(" ", "")
        return hmac.new(self._cle, normalise.encode(), hashlib.sha256).hexdigest()


_chiffreur: ChiffreurChamps | None = None
_index: IndexAveugle | None = None


def configurer(chiffreur: ChiffreurChamps, index: IndexAveugle) -> None:
    global _chiffreur, _index
    _chiffreur = chiffreur
    _index = index


def chiffreur() -> ChiffreurChamps:
    if _chiffreur is None:
        raise ErreurChiffrement("Le module de chiffrement n'est pas initialise.")
    return _chiffreur


def index_aveugle() -> IndexAveugle:
    if _index is None:
        raise ErreurChiffrement("Le module d'index aveugle n'est pas initialise.")
    return _index


def charger_ou_creer_cles_locales(chemin: Path) -> dict[str, str]:
    """Cles locales pour developpement et demonstration uniquement.

    Le fichier est cree avec des droits restreints. Interdit en production.
    """
    if chemin.exists():
        return json.loads(chemin.read_text())
    chemin.parent.mkdir(parents=True, exist_ok=True)
    cles = {
        "cles_donnees": f"k1:{generer_cle()}",
        "cle_index": generer_cle(),
        "cle_sauvegarde": generer_cle(),
    }
    descripteur = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descripteur, "w") as f:
        json.dump(cles, f)
    return cles
