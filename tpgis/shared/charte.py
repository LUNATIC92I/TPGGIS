"""Charte graphique TPGIS : palette de reference et motif bigarre.

La palette s'inspire des tenues bigarrees de la Gendarmerie nationale du
Tchad sans reproduire aucun embleme, insigne ni grade. Elle est partagee par
le client de bureau (Qt) et par les documents PDF generes par le serveur.

Le motif bigarre est decrit ici de facon purement geometrique (formes
irregulieres et couleurs), sans dependance graphique, afin d'etre dessine a
l'identique par QPainter et par ReportLab. Il est reserve a l'ecran de
connexion, aux bandeaux decoratifs et aux couvertures de rapports ; il n'est
jamais place derriere un formulaire, un tableau ou une donnee personnelle.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

VERT_OLIVE = "#26382A"
VERT_KAKI = "#536344"
SABLE = "#C5B58A"
BRUN_TERRE = "#806348"
ANTHRACITE = "#202521"
IVOIRE = "#F2F0E7"

PALETTE = {
    "vert_olive": VERT_OLIVE,
    "vert_kaki": VERT_KAKI,
    "sable": SABLE,
    "brun_terre": BRUN_TERRE,
    "anthracite": ANTHRACITE,
    "ivoire": IVOIRE,
}

COULEURS_MOTIF = (VERT_KAKI, SABLE, BRUN_TERRE, VERT_OLIVE)


def rgb(couleur: str) -> tuple[int, int, int]:
    c = couleur.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def luminance(couleur: str) -> float:
    """Luminance relative selon WCAG 2.1."""

    def canal(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(v) for v in rgb(couleur))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(premier: str, second: str) -> float:
    """Rapport de contraste WCAG 2.1 (de 1 a 21)."""
    a, b = sorted((luminance(premier), luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def melanger(couleur: str, fond: str, opacite: float) -> str:
    """Couleur obtenue en posant `couleur` avec l'opacite donnee sur `fond`."""
    c, f = rgb(couleur), rgb(fond)
    return "#" + "".join(f"{round(a * opacite + b * (1 - opacite)):02X}" for a, b in zip(c, f, strict=True))


@dataclass(frozen=True)
class Forme:
    couleur: str
    points: tuple[tuple[float, float], ...]


def motif_bigarre(
    largeur: float,
    hauteur: float,
    *,
    graine: int = 1960,
    taille: float = 46.0,
    couleurs: tuple[str, ...] = COULEURS_MOTIF,
) -> list[Forme]:
    """Formes irregulieres couvrant un rectangle, en repere ecran (origine en haut a gauche).

    Le resultat est deterministe pour une graine donnee : le motif ne change
    pas d'un affichage a l'autre. Chaque forme est un contour ferme a lisser
    (voir `contour_lisse`).
    """
    hasard = random.Random(graine)
    formes: list[Forme] = []
    pas = taille * 0.9
    colonnes = int(largeur / pas) + 3
    lignes = int(hauteur / pas) + 3
    for j in range(-1, lignes):
        for i in range(-1, colonnes):
            if hasard.random() < 0.18:
                continue
            cx = i * pas + hasard.uniform(-0.45, 0.45) * pas
            cy = j * pas + hasard.uniform(-0.45, 0.45) * pas
            rx = taille * hasard.uniform(0.45, 0.95)
            ry = taille * hasard.uniform(0.30, 0.65)
            rotation = hasard.uniform(0, math.pi)
            sommets = hasard.randint(7, 11)
            points = []
            for k in range(sommets):
                angle = 2 * math.pi * k / sommets + hasard.uniform(-0.25, 0.25)
                rayon = hasard.uniform(0.55, 1.0)
                x = rx * rayon * math.cos(angle)
                y = ry * rayon * math.sin(angle)
                points.append(
                    (
                        cx + x * math.cos(rotation) - y * math.sin(rotation),
                        cy + x * math.sin(rotation) + y * math.cos(rotation),
                    )
                )
            formes.append(Forme(hasard.choice(couleurs), tuple(points)))
    return formes


def contour_lisse(points: tuple[tuple[float, float], ...]) -> list[tuple[tuple[float, float], ...]]:
    """Decompose un contour ferme en courbes quadratiques passant par les milieux des cotes.

    Renvoie une liste de segments (controle, arrivee) ; le point de depart est
    le milieu du dernier cote. Le meme decoupage sert a Qt et a ReportLab.
    """
    n = len(points)
    milieux = [
        ((points[k][0] + points[(k + 1) % n][0]) / 2, (points[k][1] + points[(k + 1) % n][1]) / 2) for k in range(n)
    ]
    segments = [(milieux[-1],)]
    for k in range(n):
        segments.append((points[k], milieux[k]))
    return segments
