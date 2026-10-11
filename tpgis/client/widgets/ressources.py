"""Localisation des ressources embarquees (icones, styles), y compris dans l'executable autonome."""

from __future__ import annotations

import sys
from pathlib import Path


def chemin_ressource(relatif: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    candidat = base / "tpgis" / "client" / "resources" / relatif
    if candidat.exists():
        return candidat
    return Path(__file__).resolve().parents[1] / "resources" / relatif
