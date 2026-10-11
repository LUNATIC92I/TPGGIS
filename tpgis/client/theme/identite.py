"""Identite visuelle configurable : nom du logiciel, sous titre et logo.

Aucun embleme, insigne, grade ni logo institutionnel n'est fourni avec le
logiciel. L'institution peut, apres autorisation, indiquer son propre logo
dans la section [identite] du fichier client.ini :

    [identite]
    nom = TPGIS
    nom_complet = Tchad Police & Gendarmerie Information System
    sous_titre = Police nationale et Gendarmerie nationale du Tchad
    logo = C:\\TPGIS\\identite\\logo.svg

    [affichage]
    theme = clair            (ou sombre)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap

from tpgis.client.widgets.ressources import chemin_ressource

NOM_DEFAUT = "TPGIS"
NOM_COMPLET_DEFAUT = "Tchad Police & Gendarmerie Information System"
SOUS_TITRE_DEFAUT = "Police nationale et Gendarmerie nationale du Tchad"


@dataclass
class IdentiteVisuelle:
    nom: str = NOM_DEFAUT
    nom_complet: str = NOM_COMPLET_DEFAUT
    sous_titre: str = SOUS_TITRE_DEFAUT
    logo: str | None = None

    def chemin_logo(self) -> Path:
        if self.logo:
            chemin = Path(self.logo)
            if chemin.is_file() and chemin.suffix.lower() in (".svg", ".png"):
                return chemin
        return chemin_ressource("icons/logo_tpgis.svg")

    def pixmap_logo(self, cote: int) -> QPixmap:
        chemin = self.chemin_logo()
        if chemin.suffix.lower() == ".svg":
            from tpgis.client.theme.gestionnaire import pixmap_svg

            return pixmap_svg(chemin.read_bytes(), QSize(cote, cote))
        return QPixmap(str(chemin)).scaled(cote, cote)

    def icone_application(self) -> QIcon:
        icone = QIcon()
        for cote in (16, 24, 32, 48, 64, 256):
            icone.addPixmap(self.pixmap_logo(cote))
        return icone

    @property
    def titre_fenetre(self) -> str:
        return f"{self.nom} : {self.nom_complet}" if self.nom_complet else self.nom


_identite = IdentiteVisuelle()


def identite() -> IdentiteVisuelle:
    return _identite


def definir_identite(valeur: IdentiteVisuelle) -> None:
    global _identite
    _identite = valeur
