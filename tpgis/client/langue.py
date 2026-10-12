"""Langue de l'interface : choix de l'utilisateur, valeur deployee, application."""

from __future__ import annotations

from PySide6.QtCore import QLocale, QSettings

from tpgis.shared.i18n import LANGUES, definir_langue, langue_courante, normaliser

CLE_PREFERENCE = "affichage/langue"


def preference_langue(defaut: str = "fr") -> str:
    """Le choix fait par l'utilisateur sur ce poste prime sur la valeur deployee (client.ini)."""
    choix = QSettings("TPGIS", "client").value(CLE_PREFERENCE, "")
    return choix if choix in LANGUES else normaliser(defaut)


def appliquer_langue(langue: str) -> str:
    langue = definir_langue(langue)
    QLocale.setDefault(QLocale(QLocale.English if langue == "en" else QLocale.French))
    return langue


def enregistrer_langue(langue: str) -> str:
    """Applique la langue et la memorise pour les prochains lancements sur ce poste."""
    langue = appliquer_langue(langue)
    QSettings("TPGIS", "client").setValue(CLE_PREFERENCE, langue)
    return langue


__all__ = ["LANGUES", "appliquer_langue", "enregistrer_langue", "langue_courante", "preference_langue"]
