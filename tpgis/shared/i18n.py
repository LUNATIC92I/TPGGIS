"""Traduction de l'interface (francais, langue source, et anglais).

Le francais est la langue de reference : chaque texte est ecrit en francais
dans le code et sert de cle au catalogue `tpgis/shared/i18n/en.json`. Un texte
absent du catalogue s'affiche en francais (jamais de texte vide).

Les documents administratifs (fiche de plainte, bordereau, rapport PDF) et le
journal d'audit restent en francais, langue officielle des procedures.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

LANGUES = {"fr": "Français", "en": "English"}
LANGUE_DEFAUT = "fr"

_langue = LANGUE_DEFAUT


def repertoire_catalogues() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    candidat = base / "tpgis" / "shared" / "i18n"
    return candidat if candidat.exists() else Path(__file__).resolve().parent / "i18n"


@lru_cache
def catalogue(langue: str) -> dict[str, str]:
    if langue == LANGUE_DEFAUT:
        return {}
    chemin = repertoire_catalogues() / f"{langue}.json"
    if not chemin.exists():
        return {}
    return json.loads(chemin.read_text(encoding="utf-8"))


def normaliser(langue: str | None) -> str:
    """Code de langue pris en charge, a partir d'une valeur libre ou d'un en tete Accept-Language."""
    if not langue:
        return LANGUE_DEFAUT
    for morceau in langue.replace(" ", "").split(","):
        code = morceau.split(";")[0].split("-")[0].lower()
        if code in LANGUES:
            return code
    return LANGUE_DEFAUT


def definir_langue(langue: str | None) -> str:
    global _langue
    _langue = normaliser(langue)
    return _langue


def langue_courante() -> str:
    return _langue


def traduire(texte: str, langue: str | None = None, **parametres) -> str:
    """Traduction d'un texte source francais, puis remplacement des parametres nommes."""
    if not isinstance(texte, str) or not texte:
        return texte
    resultat = catalogue(langue or _langue).get(texte, texte)
    return resultat.format(**parametres) if parametres else resultat


def tr(texte: str, **parametres) -> str:
    """Raccourci pour la langue courante de l'interface."""
    return traduire(texte, None, **parametres)
