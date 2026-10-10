"""Jetons de session opaques.

Le jeton remis au client est aleatoire (256 bits). Seule son empreinte
SHA 256 est stockee, ce qui permet la revocation immediate cote serveur.
"""

from __future__ import annotations

import hashlib
import secrets


def generer_jeton() -> str:
    return secrets.token_urlsafe(32)


def empreinte_jeton(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()
