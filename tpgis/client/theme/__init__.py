"""Systeme de themes du client TPGIS (charte graphique centralisee)."""

from tpgis.client.theme.gestionnaire import (
    appliquer_theme,
    feuille_de_style,
    icone,
    notificateur,
    theme_courant,
)
from tpgis.client.theme.identite import IdentiteVisuelle, definir_identite, identite
from tpgis.client.theme.jetons import CLAIR, SOMBRE, THEMES, Theme

__all__ = [
    "CLAIR",
    "SOMBRE",
    "THEMES",
    "IdentiteVisuelle",
    "Theme",
    "appliquer_theme",
    "definir_identite",
    "feuille_de_style",
    "icone",
    "identite",
    "notificateur",
    "theme_courant",
]
