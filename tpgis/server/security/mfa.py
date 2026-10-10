"""Authentification multifacteur par code a usage unique (TOTP, RFC 6238)."""

from __future__ import annotations

import time

import pyotp

EMETTEUR = "TPGIS Tchad"


def generer_secret() -> str:
    return pyotp.random_base32()


def uri_provisionnement(secret: str, identifiant: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=identifiant, issuer_name=EMETTEUR)


def verifier_code(secret: str, code: str, dernier_pas_utilise: int | None = None) -> int | None:
    """Verifie le code et retourne le pas temporel utilise, ou None si refuse.

    Un code deja utilise (meme pas temporel ou anterieur) est refuse pour
    empecher le rejeu.
    """
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    maintenant = int(time.time())
    for decalage in (-1, 0, 1):
        instant = maintenant + decalage * totp.interval
        pas = instant // totp.interval
        if totp.verify(code, for_time=instant, valid_window=0):
            if dernier_pas_utilise is not None and pas <= dernier_pas_utilise:
                return None
            return pas
    return None
