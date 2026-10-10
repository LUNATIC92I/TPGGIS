"""Stockage des mots de passe avec Argon2id et politique de complexite."""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Parametres conformes aux recommandations OWASP pour Argon2id.
_hacheur = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID)

# Empreinte factice utilisee quand le compte n'existe pas, pour un temps de
# reponse homogene (limite l'enumeration des comptes).
_EMPREINTE_FACTICE = _hacheur.hash("compte-inexistant-tpgis")


def hacher(mot_de_passe: str) -> str:
    return _hacheur.hash(mot_de_passe)


def verifier(empreinte: str | None, mot_de_passe: str) -> bool:
    try:
        return _hacheur.verify(empreinte or _EMPREINTE_FACTICE, mot_de_passe) and empreinte is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def doit_etre_rehache(empreinte: str) -> bool:
    return _hacheur.check_needs_rehash(empreinte)


def controler_politique(mot_de_passe: str, longueur_min: int, identifiant: str | None = None) -> list[str]:
    """Retourne la liste des regles non respectees (vide si conforme)."""
    erreurs = []
    if len(mot_de_passe) < longueur_min:
        erreurs.append(f"Le mot de passe doit contenir au moins {longueur_min} caractères.")
    if len(mot_de_passe) > 256:
        erreurs.append("Le mot de passe ne doit pas dépasser 256 caractères.")
    classes = [
        any(c.islower() for c in mot_de_passe),
        any(c.isupper() for c in mot_de_passe),
        any(c.isdigit() for c in mot_de_passe),
        any(not c.isalnum() for c in mot_de_passe),
    ]
    if sum(classes) < 3:
        erreurs.append(
            "Le mot de passe doit combiner au moins trois types de caractères "
            "(minuscules, majuscules, chiffres, caractères spéciaux)."
        )
    if identifiant and identifiant.lower() in mot_de_passe.lower():
        erreurs.append("Le mot de passe ne doit pas contenir l'identifiant.")
    return erreurs
