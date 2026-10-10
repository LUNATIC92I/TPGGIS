"""Carte interactive du Tchad (rendu vectoriel natif Qt, sans navigateur).

Mode hors ligne (par defaut) : frontiere, provinces et villes issues des
fichiers GeoJSON Natural Earth embarques (domaine public).
Mode connecte ou tuiles locales (facultatif) : fond de carte raster XYZ dont
l'adresse est fournie par la configuration ; a n'activer qu'avec un
fournisseur dont la licence et les regles de securite ont ete validees.

La carte n'affiche que des agregats statistiques et l'implantation des unites.
Aucune personne, aucun domicile ni aucun deplacement n'y est represente.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTransform
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
)

from tpgis.shared.geographie import charger

ZOOM_BASE = 6
TAILLE_TUILE = 256
MONDE = TAILLE_TUILE * 2**ZOOM_BASE

PALETTE_SEQUENTIELLE = ["#EEF3F8", "#C9DBEC", "#9DBEDD", "#6A9BC8", "#3D73A8", "#1F4E7E"]
COULEUR_SANS_DONNEE = "#E4E6EA"
COULEUR_BAISSE, COULEUR_STABLE, COULEUR_HAUSSE = "#6A9BC8", "#F1F1EF", "#B08D57"
COULEUR_POLICE, COULEUR_GENDARMERIE = "#1F4E7E", "#3A3F47"


def projeter(lon: float, lat: float) -> QPointF:
    """Projection Web Mercator en pixels au niveau de zoom de base."""
    x = (lon + 180.0) / 360.0 * MONDE
    s = math.sin(math.radians(max(min(lat, 85.0), -85.0)))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * MONDE
    return QPointF(x, y)


def _chemin_geometrie(geometrie: dict) -> QPainterPath:
    chemin = QPainterPath()
    chemin.setFillRule(Qt.OddEvenFill)
    polygones = [geometrie["coordinates"]] if geometrie["type"] == "Polygon" else geometrie["coordinates"]
    for polygone in polygones:
        for anneau in polygone:
            chemin.addPolygon(QPolygonF([projeter(x, y) for x, y in anneau]))
            chemin.closeSubpath()
    return chemin


def _centre_etiquette(geometrie: dict) -> QPointF:
    polygones = [geometrie["coordinates"]] if geometrie["type"] == "Polygon" else geometrie["coordinates"]
    plus_grand = max(polygones, key=lambda p: len(p[0]))[0]
    # Centroide de surface du plus grand anneau.
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(plus_grand, plus_grand[1:] + plus_grand[:1], strict=False):
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if abs(a) < 1e-12:
        x, y = plus_grand[0]
        return projeter(x, y)
    return projeter(cx / (3 * a), cy / (3 * a))


def _stylo(couleur: str, largeur: float) -> QPen:
    stylo = QPen(QColor(couleur), largeur)
    stylo.setCosmetic(True)
    return stylo


class Province(QGraphicsPathItem):
    def __init__(self, code: str, nom: str, chemin: QPainterPath):
        super().__init__(chemin)
        self.code, self.nom = code, nom
        self.setPen(_stylo("#FFFFFF", 0.8))
        self.setBrush(QBrush(QColor(COULEUR_SANS_DONNEE)))
        self.setAcceptHoverEvents(True)
        self.setToolTip(nom)
        self.setZValue(1)

    def hoverEnterEvent(self, event):  # noqa: N802
        self.setPen(_stylo("#5DA9E9", 2.0))
        self.setZValue(2)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):  # noqa: N802
        self.setPen(_stylo("#FFFFFF", 0.8))
        self.setZValue(1)
        super().hoverLeaveEvent(event)


class Marqueur(QGraphicsPathItem):
    def __init__(self, unite: dict):
        chemin = QPainterPath()
        if unite["corps"] == "GENDARMERIE":
            # Decalage de quelques pixels pour ne pas masquer le commissariat voisin.
            chemin.addPolygon(QPolygonF([QPointF(7, -12), QPointF(13, -6), QPointF(7, 0), QPointF(1, -6)]))
            chemin.closeSubpath()
            couleur = COULEUR_GENDARMERIE
        else:
            chemin.addRect(QRectF(-11.5, -10.5, 9, 9))
            couleur = COULEUR_POLICE
        super().__init__(chemin)
        self.unite = unite
        self.setPos(projeter(unite["longitude"], unite["latitude"]))
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        dans = unite.get("dans_perimetre", True)
        self.setBrush(QBrush(QColor(couleur if dans else "#FFFFFF")))
        self.setPen(QPen(QColor(couleur), 1.6))
        self.setZValue(6)
        self.setToolTip(
            f"{unite['nom']}\n{unite.get('ville') or ''}"
            f"{'' if dans else chr(10) + 'Hors de votre périmètre de consultation'}"
        )


class CoucheTuiles:
    """Fond de carte raster XYZ facultatif (serveur institutionnel ou dossier local).

    Modeles d'adresse acceptes :
      https://serveur/tuiles/{z}/{x}/{y}.png
      fichier:C:/TPGIS/tuiles/{z}/{x}/{y}.png
    """

    def __init__(self, scene: QGraphicsScene, modele_url: str, attribution: str = ""):
        self.scene, self.modele_url, self.attribution = scene, modele_url, attribution
        self.reseau = QNetworkAccessManager()
        self.tuiles: dict[tuple[int, int, int], QGraphicsPixmapItem] = {}
        self.en_cours: set[tuple[int, int, int]] = set()
        self.visible = True

    def _placer(self, cle, pixmap: QPixmap) -> None:
        z, x, y = cle
        facteur = 2 ** (z - ZOOM_BASE)
        item = QGraphicsPixmapItem(pixmap)
        item.setPos(x * TAILLE_TUILE / facteur, y * TAILLE_TUILE / facteur)
        item.setScale(1 / facteur)
        item.setZValue(-10 + z / 100)
        item.setVisible(self.visible)
        self.scene.addItem(item)
        self.tuiles[cle] = item

    def mettre_a_jour(self, rect_scene: QRectF, echelle: float) -> None:
        z = max(ZOOM_BASE - 2, min(14, ZOOM_BASE + round(math.log2(max(echelle, 1e-3)))))
        facteur = 2 ** (z - ZOOM_BASE)
        n = 2**z
        x0 = max(0, int(rect_scene.left() * facteur // TAILLE_TUILE))
        x1 = min(n - 1, int(rect_scene.right() * facteur // TAILLE_TUILE))
        y0 = max(0, int(rect_scene.top() * facteur // TAILLE_TUILE))
        y1 = min(n - 1, int(rect_scene.bottom() * facteur // TAILLE_TUILE))
        if (x1 - x0 + 1) * (y1 - y0 + 1) > 64:
            return
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                cle = (z, x, y)
                if cle in self.tuiles or cle in self.en_cours:
                    continue
                adresse = self.modele_url.format(z=z, x=x, y=y)
                if adresse.startswith("fichier:"):
                    chemin = Path(adresse[len("fichier:") :])
                    if chemin.exists():
                        pixmap = QPixmap(str(chemin))
                        if not pixmap.isNull():
                            self._placer(cle, pixmap)
                    continue
                self.en_cours.add(cle)
                reponse = self.reseau.get(QNetworkRequest(QUrl(adresse)))
                reponse.finished.connect(lambda r=reponse, c=cle: self._recue(r, c))

    def _recue(self, reponse: QNetworkReply, cle) -> None:
        self.en_cours.discard(cle)
        if reponse.error() == QNetworkReply.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(reponse.readAll()):
                self._placer(cle, pixmap)
        reponse.deleteLater()

    def definir_visible(self, visible: bool) -> None:
        self.visible = visible
        for item in self.tuiles.values():
            item.setVisible(visible)


class CarteTchad(QGraphicsView):
    province_survolee = Signal(str)

    def __init__(self, parent=None, url_tuiles: str | None = None, attribution_tuiles: str = ""):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor("#F4F6F9"))
        self.setMinimumSize(320, 260)
        self.scene_carte = QGraphicsScene(self)
        self.setScene(self.scene_carte)
        self.provinces: dict[str, Province] = {}
        self.etiquettes_provinces: list[QGraphicsSimpleTextItem] = []
        self.villes: list[QGraphicsItem] = []
        self.marqueurs: list[Marqueur] = []
        self.indicateur = "plaintes"
        self.donnees: dict = {}
        self._construire_fond()
        self.tuiles = CoucheTuiles(self.scene_carte, url_tuiles, attribution_tuiles) if url_tuiles else None
        self.legende = QLabel(self)
        self.legende.setObjectName("panneau")
        self.legende.setStyleSheet(
            "background: rgba(255,255,255,0.92); border: 1px solid #DDE2EA; "
            "border-radius: 4px; padding: 6px; font-size: 8pt;"
        )
        self.source = QLabel("Fond : Natural Earth (domaine public). Limites indicatives.", self)
        self.source.setStyleSheet("background: rgba(255,255,255,0.8); font-size: 7pt; color: #5A6472; padding: 2px;")
        self._maj_legende([])

    # Construction

    def _construire_fond(self) -> None:
        for f in charger("tchad_provinces.geojson")["features"]:
            code, nom = f["properties"]["code"], f["properties"]["nom"]
            province = Province(code, nom, _chemin_geometrie(f["geometry"]))
            self.scene_carte.addItem(province)
            self.provinces[code] = province
            etiquette = QGraphicsSimpleTextItem(nom.split(" (")[0])
            etiquette.setFont(QFont("Segoe UI", 7))
            etiquette.setBrush(QBrush(QColor("#2B2F36")))
            etiquette.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            centre = _centre_etiquette(f["geometry"])
            etiquette.setPos(centre)
            rect = etiquette.boundingRect()
            etiquette.setTransform(QTransform.fromTranslate(-rect.width() / 2, -rect.height() / 2))
            etiquette.setZValue(4)
            self.scene_carte.addItem(etiquette)
            self.etiquettes_provinces.append(etiquette)
        for f in charger("tchad_frontiere.geojson")["features"]:
            frontiere = QGraphicsPathItem(_chemin_geometrie(f["geometry"]))
            stylo = QPen(QColor("#0B1F3A"), 2.2)
            stylo.setCosmetic(True)
            frontiere.setPen(stylo)
            frontiere.setBrush(Qt.NoBrush)
            frontiere.setZValue(3)
            self.scene_carte.addItem(frontiere)
        for f in charger("tchad_villes.geojson")["features"]:
            x, y = f["geometry"]["coordinates"]
            p = projeter(x, y)
            capitale = f["properties"]["capitale"]
            rayon = 4.0 if capitale else 2.6
            point = self.scene_carte.addEllipse(
                -rayon,
                -rayon,
                2 * rayon,
                2 * rayon,
                QPen(QColor("#FFFFFF"), 1),
                QBrush(QColor("#0B1F3A" if capitale else "#2B2F36")),
            )
            point.setPos(p)
            point.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            point.setZValue(5)
            point.setToolTip(f["properties"]["nom"])
            texte = QGraphicsSimpleTextItem(f["properties"]["nom"])
            texte.setFont(QFont("Segoe UI", 8, QFont.Bold if capitale else QFont.Normal))
            texte.setBrush(QBrush(QColor("#0B1F3A")))
            texte.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            texte.setPos(p)
            texte.setTransform(QTransform.fromTranslate(6, 1))
            texte.setZValue(5)
            self.scene_carte.addItem(texte)
            self.villes += [point, texte]
        self.emprise = self.scene_carte.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        self.scene_carte.setSceneRect(self.emprise.adjusted(-400, -400, 400, 400))

    # Donnees

    def definir_donnees(self, donnees: dict, indicateur: str | None = None) -> None:
        self.donnees = donnees
        if indicateur:
            self.indicateur = indicateur
        for m in self.marqueurs:
            self.scene_carte.removeItem(m)
        self.marqueurs = []
        for unite in donnees.get("unites", []):
            if unite.get("latitude") is None:
                continue
            m = Marqueur(unite)
            self.scene_carte.addItem(m)
            self.marqueurs.append(m)
        self._colorer()

    def _valeur(self, p: dict):
        if self.indicateur == "dossiers":
            return p.get("dossiers_en_cours")
        if self.indicateur == "tendance":
            return p.get("tendance_pct")
        return p.get("plaintes")

    def _colorer(self) -> None:
        par_code = {p["province_code"]: p for p in self.donnees.get("provinces", [])}
        valeurs = [v for v in (self._valeur(p) for p in par_code.values()) if v is not None]
        bornes = self._bornes(valeurs)
        for code, province in self.provinces.items():
            p = par_code.get(code)
            valeur = self._valeur(p) if p else None
            province.setBrush(QBrush(QColor(self._couleur(valeur, bornes))))
            infos = [province.nom]
            if p:
                if p.get("plaintes_masquees"):
                    infos.append("Effectif inférieur au seuil de confidentialité")
                else:
                    infos.append(f"Plaintes sur la période : {p.get('plaintes', 0)}")
                    if p.get("plaintes_periode_precedente") is not None:
                        infos.append(f"Période précédente : {p['plaintes_periode_precedente']}")
                    if p.get("tendance_pct") is not None:
                        infos.append(f"Tendance : {p['tendance_pct']:+.1f} %")
                infos.append(f"Dossiers en cours : {p.get('dossiers_en_cours', 0)}")
            else:
                infos.append("Aucune donnée dans votre périmètre")
            province.setToolTip("\n".join(infos))
        self._maj_legende(bornes)

    def _bornes(self, valeurs: list) -> list:
        if not valeurs:
            return []
        if self.indicateur == "tendance":
            return [-10, 10]
        maximum = max(valeurs)
        if maximum <= 0:
            return []
        n = len(PALETTE_SEQUENTIELLE) - 1
        bornes = sorted({max(1, round(maximum * (i + 1) / n)) for i in range(n)})
        return bornes

    def _couleur(self, valeur, bornes) -> str:
        if valeur is None or not bornes:
            return COULEUR_SANS_DONNEE
        if self.indicateur == "tendance":
            return COULEUR_BAISSE if valeur < bornes[0] else COULEUR_HAUSSE if valeur > bornes[1] else COULEUR_STABLE
        if valeur == 0:
            return PALETTE_SEQUENTIELLE[0]
        for i, borne in enumerate(bornes):
            if valeur <= borne:
                return PALETTE_SEQUENTIELLE[i + 1]
        return PALETTE_SEQUENTIELLE[-1]

    def _maj_legende(self, bornes: list) -> None:
        titres = {
            "plaintes": "Plaintes enregistrées",
            "dossiers": "Dossiers en cours",
            "tendance": "Évolution par rapport à la période précédente",
        }
        lignes = [f"<b>{titres[self.indicateur]}</b>"]

        def case(couleur):
            return f"<span style='background:{couleur};color:{couleur}'>&nbsp;&nbsp;&nbsp;&nbsp;</span>"

        if self.indicateur == "tendance" and bornes:
            lignes += [
                f"{case(COULEUR_BAISSE)} baisse de plus de 10 %",
                f"{case(COULEUR_STABLE)} stable",
                f"{case(COULEUR_HAUSSE)} hausse de plus de 10 %",
            ]
        elif bornes:
            lignes.append(f"{case(PALETTE_SEQUENTIELLE[0])} 0")
            precedent = 0
            for couleur, borne in zip(PALETTE_SEQUENTIELLE[1:], bornes, strict=False):
                debut = precedent + 1
                lignes.append(f"{case(couleur)} {debut}" + (f" à {borne}" if borne > debut else ""))
                precedent = borne
        lignes.append(f"{case(COULEUR_SANS_DONNEE)} aucune donnée")
        lignes.append(
            f"<span style='color:{COULEUR_POLICE}'>&#9632;</span> Police  "
            f"<span style='color:{COULEUR_GENDARMERIE}'>&#9670;</span> Gendarmerie"
        )
        self.legende.setText("<br/>".join(lignes))
        self.legende.adjustSize()
        self._placer_superpositions()

    # Couches et navigation

    def afficher_couche(self, couche: str, visible: bool) -> None:
        elements = {"unites": self.marqueurs, "villes": self.villes, "etiquettes": self.etiquettes_provinces}
        if couche == "fond" and self.tuiles:
            self.tuiles.definir_visible(visible)
            return
        for e in elements.get(couche, []):
            e.setVisible(visible)

    def recentrer(self) -> None:
        self.resetTransform()
        self.fitInView(self.emprise, Qt.KeepAspectRatio)
        self._tuiles()

    def zoomer(self, facteur: float) -> None:
        echelle = self.transform().m11() * facteur
        if 0.2 < echelle < 400:
            self.scale(facteur, facteur)
            self._tuiles()

    def wheelEvent(self, event):  # noqa: N802
        self.zoomer(1.25 if event.angleDelta().y() > 0 else 0.8)

    def mouseReleaseEvent(self, event):  # noqa: N802
        super().mouseReleaseEvent(event)
        self._tuiles()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.recentrer()
        self._placer_superpositions()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.recentrer()

    def _tuiles(self) -> None:
        if self.tuiles:
            visible = self.mapToScene(self.viewport().rect()).boundingRect()
            self.tuiles.mettre_a_jour(visible, self.transform().m11())

    def _placer_superpositions(self) -> None:
        self.legende.move(10, max(10, self.height() - self.legende.height() - 30))
        self.source.adjustSize()
        self.source.move(max(0, self.width() - self.source.width() - 6), self.height() - self.source.height() - 4)
