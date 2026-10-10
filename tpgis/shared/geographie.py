"""Acces aux donnees geographiques hors ligne du Tchad (Natural Earth)."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path


def repertoire_geodata() -> Path:
    # Compatible avec l'executable autonome Windows (PyInstaller).
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    candidat = base / "tpgis" / "shared" / "geodata"
    return candidat if candidat.exists() else Path(__file__).resolve().parent / "geodata"


@lru_cache
def charger(nom: str) -> dict:
    return json.loads((repertoire_geodata() / nom).read_text(encoding="utf-8"))


def provinces() -> dict[str, str]:
    return {f["properties"]["code"]: f["properties"]["nom"] for f in charger("tchad_provinces.geojson")["features"]}


def villes() -> list[dict]:
    return [
        {**f["properties"], "longitude": f["geometry"]["coordinates"][0], "latitude": f["geometry"]["coordinates"][1]}
        for f in charger("tchad_villes.geojson")["features"]
    ]
