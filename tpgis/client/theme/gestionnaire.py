"""Application du theme : feuille QSS generee, palette Qt, icones et notification des changements."""

from __future__ import annotations

import re
import tempfile
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from tpgis.client.theme.jetons import (
    CLAIR,
    DIMENSIONS,
    ESPACEMENTS,
    POLICE,
    RAYONS,
    TAILLES_POLICE,
    THEMES,
    Theme,
)
from tpgis.client.widgets.ressources import chemin_ressource

_MOTIF_JETON = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


class _Notificateur(QObject):
    theme_change = Signal(object)


notificateur = _Notificateur()
_actif: Theme = CLAIR


def theme_courant() -> Theme:
    return _actif


def _fichier_icone(nom: str, couleur: str) -> str:
    """Icone coloree ecrite dans le dossier temporaire du poste (QSS n'accepte que des fichiers).

    Seuls des pictogrammes d'interface y sont ecrits, jamais de donnees.
    """
    dossier = Path(tempfile.gettempdir()) / "tpgis_theme"
    dossier.mkdir(exist_ok=True)
    chemin = dossier / f"{nom}_{couleur.lstrip('#').lower()}.svg"
    if not chemin.exists():
        chemin.write_bytes(_svg_colore(nom, couleur))
    return chemin.as_posix()


def valeurs_jetons(theme: Theme) -> dict[str, str]:
    valeurs = dict(theme.couleurs)
    valeurs["fichier_fleche_bas"] = _fichier_icone("chevron_bas", theme["texte_secondaire"])
    valeurs["fichier_fleche_haut"] = _fichier_icone("chevron_haut", theme["texte_secondaire"])
    valeurs["fichier_fleche_haut_desactivee"] = _fichier_icone("chevron_haut", theme["texte_desactive"])
    valeurs["fichier_coche"] = _fichier_icone("coche", theme["accent_texte"])
    valeurs["fichier_fleche_bas_desactivee"] = _fichier_icone("chevron_bas", theme["texte_desactive"])
    valeurs["police"] = POLICE
    valeurs.update({f"police_{k}": str(v) for k, v in TAILLES_POLICE.items()})
    valeurs.update({f"espace_{k}": str(v) for k, v in ESPACEMENTS.items()})
    valeurs.update({f"rayon_{k}": str(v) for k, v in RAYONS.items()})
    valeurs.update({k: str(v) for k, v in DIMENSIONS.items()})
    return valeurs


def feuille_de_style(theme: Theme) -> str:
    """Rend le modele QSS avec les jetons du theme ; un jeton inconnu est une erreur."""
    modele = chemin_ressource("styles/tpgis.qss").read_text(encoding="utf-8")
    valeurs = valeurs_jetons(theme)

    def remplacer(m: re.Match) -> str:
        try:
            return valeurs[m.group(1)]
        except KeyError as exc:
            raise KeyError(f"Jeton de style inconnu : {m.group(1)}") from exc

    return _MOTIF_JETON.sub(remplacer, modele)


def palette_qt(theme: Theme) -> QPalette:
    """Palette Fusion coherente avec la feuille de style (boites de message, menus, calendriers)."""
    c = theme.couleurs
    p = QPalette()
    roles = {
        QPalette.Window: c["fond"],
        QPalette.WindowText: c["texte"],
        QPalette.Base: c["surface"],
        QPalette.AlternateBase: c["surface_alternee"],
        QPalette.Text: c["texte"],
        QPalette.Button: c["surface"],
        QPalette.ButtonText: c["texte"],
        QPalette.Highlight: c["selection"],
        QPalette.HighlightedText: c["selection_texte"],
        QPalette.ToolTipBase: c["info_bulle_fond"],
        QPalette.ToolTipText: c["info_bulle_texte"],
        QPalette.PlaceholderText: c["texte_secondaire"],
        QPalette.Link: c["texte_titre"],
        QPalette.Mid: c["bordure"],
        QPalette.Dark: c["bordure_champ"],
    }
    for role, couleur in roles.items():
        p.setColor(role, QColor(couleur))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["texte_desactive"]))
    return p


def appliquer_theme(app: QApplication, nom: str = "clair") -> Theme:
    """Applique le theme demande a toute l'application et previent les composants dessines."""
    global _actif
    theme = THEMES.get(nom, CLAIR)
    _actif = theme
    app.setStyle("Fusion")
    app.setPalette(palette_qt(theme))
    app.setStyleSheet(feuille_de_style(theme))
    from tpgis.client.theme.identite import identite

    app.setWindowIcon(identite().icone_application())
    notificateur.theme_change.emit(theme)
    return theme


@lru_cache(maxsize=256)
def _svg_colore(nom: str, couleur: str) -> bytes:
    texte = chemin_ressource(f"icons/{nom}.svg").read_text(encoding="utf-8")
    return texte.replace("currentColor", couleur).encode("utf-8")


def pixmap_svg(contenu: bytes, taille: QSize, ratio: float = 2.0) -> QPixmap:
    rendu = QSvgRenderer(QByteArray(contenu))
    pixmap = QPixmap(int(taille.width() * ratio), int(taille.height() * ratio))
    pixmap.fill(Qt.transparent)
    peintre = QPainter(pixmap)
    peintre.setRenderHint(QPainter.Antialiasing)
    rendu.render(peintre, QRectF(0, 0, pixmap.width(), pixmap.height()))
    peintre.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icone(nom: str, jeton: str = "icone", taille: int = 24) -> QIcon:
    """Icone vectorielle de la bibliotheque TPGIS, coloree selon le jeton du theme actif."""
    return QIcon(pixmap_svg(_svg_colore(nom, _actif[jeton]), QSize(taille, taille)))
