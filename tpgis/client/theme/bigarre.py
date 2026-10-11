"""Composants decoratifs au motif bigarre (ecran de connexion et liseres de bandeau).

Ces composants sont les seuls endroits de l'interface ou le motif apparait.
Ils ne recoivent jamais de champ de saisie, de tableau ni de donnee
personnelle : le texte pose dessus se limite au nom du logiciel et repose
sur une zone unie garantissant le contraste.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from tpgis.client.theme.gestionnaire import notificateur, theme_courant
from tpgis.shared.charte import contour_lisse, motif_bigarre


def chemin_forme(points) -> QPainterPath:
    segments = contour_lisse(points)
    chemin = QPainterPath(QPointF(*segments[0][0]))
    for controle, arrivee in segments[1:]:
        chemin.quadTo(QPointF(*controle), QPointF(*arrivee))
    chemin.closeSubpath()
    return chemin


def peindre_motif(
    peintre: QPainter, rect: QRectF, base: str, opacite: float, *, graine: int = 1960, taille: float = 46.0
) -> None:
    """Fond uni `base` recouvert de formes irregulieres a l'opacite donnee."""
    peintre.save()
    peintre.setClipRect(rect)
    peintre.fillRect(rect, QColor(base))
    peintre.setPen(Qt.NoPen)
    peintre.setOpacity(opacite)
    peintre.translate(rect.topLeft())
    for forme in motif_bigarre(rect.width(), rect.height(), graine=graine, taille=taille):
        peintre.setBrush(QBrush(QColor(forme.couleur)))
        peintre.drawPath(chemin_forme(forme.points))
    peintre.restore()


class _Decor(QWidget):
    """Base : rendu mis en cache et regenere au redimensionnement ou au changement de theme."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: QPixmap | None = None
        self.setAttribute(Qt.WA_StyledBackground, False)
        notificateur.theme_change.connect(self._invalider)

    def _invalider(self, *_):
        self._cache = None
        self.update()

    def resizeEvent(self, event):  # noqa: N802
        self._cache = None
        super().resizeEvent(event)

    def dessiner(self, peintre: QPainter, rect: QRectF) -> None:  # pragma: no cover - surcharge
        raise NotImplementedError

    def paintEvent(self, _):  # noqa: N802
        ratio = self.devicePixelRatioF()
        if self._cache is None or self._cache.size() != self.size() * ratio:
            pixmap = QPixmap(self.size() * ratio)
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(Qt.transparent)
            p = QPainter(pixmap)
            p.setRenderHint(QPainter.Antialiasing)
            self.dessiner(p, QRectF(0, 0, self.width(), self.height()))
            p.end()
            self._cache = pixmap
        QPainter(self).drawPixmap(0, 0, self._cache)


class LisereBigarre(_Decor):
    """Lisere decoratif de quelques pixels sous le bandeau superieur."""

    def __init__(self, hauteur: int = 6, parent=None):
        super().__init__(parent)
        self.setFixedHeight(hauteur)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName("Lisere decoratif")

    def dessiner(self, peintre: QPainter, rect: QRectF) -> None:
        peindre_motif(peintre, rect, theme_courant()["navigation_fond"], 0.9, graine=7, taille=22)


class PanneauBigarre(_Decor):
    """Panneau lateral de l'ecran de connexion.

    Le motif occupe la partie haute et s'efface progressivement vers une zone
    unie ou s'affichent le logo et le nom du logiciel.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(260)

    def dessiner(self, peintre: QPainter, rect: QRectF) -> None:
        base = theme_courant()["navigation_fond"]
        peindre_motif(peintre, rect, base, 0.42, graine=1960, taille=58)
        degrade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        uni = QColor(base)
        transparent = QColor(base)
        transparent.setAlpha(0)
        degrade.setColorAt(0.0, transparent)
        degrade.setColorAt(0.30, transparent)
        degrade.setColorAt(0.52, uni)
        degrade.setColorAt(1.0, uni)
        peintre.fillRect(rect, degrade)
