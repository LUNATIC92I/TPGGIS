"""Graphiques simples dessines avec QPainter (aucune dependance externe)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from tpgis.client.theme import notificateur, theme_courant
from tpgis.client.theme.jetons import RAYONS


def _couleurs() -> tuple[QColor, QColor, QColor, QColor, QColor]:
    """Serie, texte secondaire, grille, fond et titre, lus dans le theme actif."""
    t = theme_courant()
    return (
        QColor(t["graphique_serie"]),
        QColor(t["texte_secondaire"]),
        QColor(t["graphique_grille"]),
        QColor(t["surface"]),
        QColor(t["texte_titre"]),
    )


class _Graphique(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Methode liee (et non lambda) : la connexion disparait avec le composant.
        notificateur.theme_change.connect(self._theme_change)

    def _theme_change(self, _theme) -> None:
        self.update()

    def _fond(self, p: QPainter, fond: QColor) -> None:
        """Panneau a coins legerement arrondis, comme les cartes de l'interface."""
        p.setPen(QPen(QColor(theme_courant()["bordure"]), 1))
        p.setBrush(fond)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RAYONS["moyen"], RAYONS["moyen"])


class GraphiqueColonnes(_Graphique):
    """Colonnes verticales (evolution mensuelle)."""

    def __init__(self, titre: str, parent=None):
        super().__init__(parent)
        self.titre, self.donnees = titre, []
        self.setMinimumHeight(200)

    def definir(self, donnees: list[tuple[str, float]]) -> None:
        self.donnees = donnees
        self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        SERIE, GRIS_TEXTE, GRILLE, FOND, TITRE = _couleurs()  # noqa: N806
        self._fond(p, FOND)
        p.setPen(TITRE)
        p.setFont(QFont(self.font().family(), 10, QFont.DemiBold))
        p.drawText(QRectF(12, 6, self.width() - 24, 20), Qt.AlignLeft, self.titre)
        if not self.donnees:
            p.setPen(GRIS_TEXTE)
            p.drawText(self.rect(), Qt.AlignCenter, "Aucune donnée sur la période")
            return
        zone = QRectF(40, 34, self.width() - 56, self.height() - 70)
        maximum = max(4, -(-max(v for _, v in self.donnees) // 4) * 4)
        p.setFont(QFont(self.font().family(), 7))
        for i in range(5):
            y = zone.bottom() - zone.height() * i / 4
            p.setPen(QPen(GRILLE, 1))
            p.drawLine(int(zone.left()), int(y), int(zone.right()), int(y))
            p.setPen(GRIS_TEXTE)
            p.drawText(QRectF(0, y - 7, 36, 14), Qt.AlignRight | Qt.AlignVCenter, f"{maximum * i / 4:.0f}")
        largeur = zone.width() / len(self.donnees)
        # Une etiquette sur n, pour qu'elles ne se chevauchent jamais.
        largeur_texte = max(p.fontMetrics().horizontalAdvance(e) for e, _ in self.donnees) + 6
        pas_etiquettes = max(1, -(-int(largeur_texte) // max(1, int(largeur))))
        for i, (etiquette, valeur) in enumerate(self.donnees):
            h = zone.height() * valeur / maximum
            barre = QRectF(zone.left() + i * largeur + largeur * 0.15, zone.bottom() - h, largeur * 0.7, h)
            p.fillRect(barre, SERIE)
            p.setPen(GRIS_TEXTE)
            if i % pas_etiquettes == 0:
                p.drawText(
                    QRectF(barre.left() - 12, zone.bottom() + 4, barre.width() + 24, 14), Qt.AlignCenter, etiquette
                )


class GraphiqueBarres(_Graphique):
    """Barres horizontales (repartition par categorie)."""

    def __init__(self, titre: str, parent=None, maximum_lignes: int = 8):
        super().__init__(parent)
        self.titre, self.donnees, self.maximum_lignes = titre, [], maximum_lignes
        self.setMinimumHeight(200)

    def definir(self, donnees: list[tuple[str, float]]) -> None:
        self.donnees = donnees[: self.maximum_lignes]
        self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        SERIE, GRIS_TEXTE, GRILLE, FOND, TITRE = _couleurs()  # noqa: N806
        self._fond(p, FOND)
        p.setPen(TITRE)
        p.setFont(QFont(self.font().family(), 10, QFont.DemiBold))
        p.drawText(QRectF(12, 6, self.width() - 24, 20), Qt.AlignLeft, self.titre)
        if not self.donnees:
            p.setPen(GRIS_TEXTE)
            p.drawText(self.rect(), Qt.AlignCenter, "Aucune donnée sur la période")
            return
        maximum = max(v for _, v in self.donnees) or 1
        hauteur = (self.height() - 40) / len(self.donnees)
        libelle_l = min(220, self.width() * 0.42)
        p.setFont(QFont(self.font().family(), 8))
        for i, (etiquette, valeur) in enumerate(self.donnees):
            y = 32 + i * hauteur
            p.setPen(GRIS_TEXTE)
            p.drawText(
                QRectF(8, y, libelle_l - 12, hauteur),
                Qt.AlignRight | Qt.AlignVCenter,
                p.fontMetrics().elidedText(etiquette, Qt.ElideRight, int(libelle_l - 12)),
            )
            largeur = (self.width() - libelle_l - 50) * valeur / maximum
            p.fillRect(QRectF(libelle_l, y + hauteur * 0.2, largeur, hauteur * 0.6), SERIE)
            p.drawText(QRectF(libelle_l + largeur + 4, y, 46, hauteur), Qt.AlignLeft | Qt.AlignVCenter, f"{valeur:.0f}")
