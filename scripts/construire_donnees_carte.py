"""Construit les fichiers cartographiques hors ligne du Tchad.

Source : Natural Earth (https://www.naturalearthdata.com), domaine public.
Fichiers d'entree attendus dans le repertoire indique :
  ne_10m_admin_0_countries.geojson
  ne_10m_admin_1_states_provinces.geojson
  ne_10m_populated_places_simple.geojson

Usage : python scripts/construire_donnees_carte.py <repertoire_sources>

Les geometries sont simplifiees (Douglas Peucker, tolerance 0,004 degre,
soit environ 400 m) et les coordonnees arrondies a 4 decimales, ce qui suffit
pour un affichage a l'echelle nationale ou provinciale.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

CIBLE = Path(__file__).resolve().parents[1] / "tpgis" / "shared" / "geodata"
TOLERANCE = 0.004

# Natural Earth 10m (v5) regroupe encore Ennedi Est et Ennedi Ouest.
CORRECTIONS_CODES = {"TD-X01~": "TD-EN"}
CORRECTIONS_NOMS = {
    "TD-EN": "Ennedi (Ennedi-Est et Ennedi-Ouest, non distingués dans la source)",
    "TD-ND": "Ville de N'Djamena",
    "TD-LR": "Logone Oriental",
    "TD-LO": "Logone Occidental",
}
# Le point source de Moundou, chef lieu du Logone Occidental, tombe a
# proximite immediate de la limite provinciale de la source : rattachement
# corrige explicitement.
CORRECTIONS_VILLES = {"Moundou": "TD-LO"}


def _distance_segment(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    px, py = x1 + t * dx, y1 + t * dy
    return ((x - px) ** 2 + (y - py) ** 2) ** 0.5


def douglas_peucker(points: list, tolerance: float) -> list:
    if len(points) < 3:
        return points
    garder = [False] * len(points)
    garder[0] = garder[-1] = True
    pile = [(0, len(points) - 1)]
    while pile:
        debut, fin = pile.pop()
        dmax, indice = 0.0, 0
        for i in range(debut + 1, fin):
            d = _distance_segment(points[i], points[debut], points[fin])
            if d > dmax:
                dmax, indice = d, i
        if dmax > tolerance:
            garder[indice] = True
            pile.extend([(debut, indice), (indice, fin)])
    return [p for p, g in zip(points, garder) if g]


def simplifier_anneau(anneau: list) -> list:
    simplifie = douglas_peucker(anneau, TOLERANCE)
    if len(simplifie) < 4:
        simplifie = anneau
    return [[round(x, 4), round(y, 4)] for x, y in simplifie]


def simplifier_geometrie(g: dict) -> dict:
    if g["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [simplifier_anneau(a) for a in g["coordinates"]]}
    if g["type"] == "MultiPolygon":
        return {"type": "MultiPolygon",
                "coordinates": [[simplifier_anneau(a) for a in poly] for poly in g["coordinates"]]}
    raise ValueError(g["type"])


def point_dans_anneau(x: float, y: float, anneau: list) -> bool:
    dedans = False
    j = len(anneau) - 1
    for i in range(len(anneau)):
        xi, yi = anneau[i]
        xj, yj = anneau[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dedans = not dedans
        j = i
    return dedans


def point_dans_geometrie(x: float, y: float, g: dict) -> bool:
    polygones = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    for poly in polygones:
        if point_dans_anneau(x, y, poly[0]) and not any(point_dans_anneau(x, y, t) for t in poly[1:]):
            return True
    return False


def main(sources: Path) -> None:
    CIBLE.mkdir(parents=True, exist_ok=True)
    pays = json.loads((sources / "ne_10m_admin_0_countries.geojson").read_text())
    adm1 = json.loads((sources / "ne_10m_admin_1_states_provinces.geojson").read_text())
    lieux = json.loads((sources / "ne_10m_populated_places_simple.geojson").read_text())

    frontiere = next(f for f in pays["features"] if f["properties"].get("ADM0_A3") == "TCD")
    frontiere_geo = {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "properties": {"nom": "République du Tchad", "code": "TD"},
        "geometry": simplifier_geometrie(frontiere["geometry"]),
    }]}

    provinces = []
    for f in adm1["features"]:
        pr = f["properties"]
        if pr.get("adm0_a3") != "TCD":
            continue
        code = CORRECTIONS_CODES.get(pr["iso_3166_2"], pr["iso_3166_2"])
        provinces.append({
            "type": "Feature",
            "properties": {"code": code, "nom": CORRECTIONS_NOMS.get(code, pr["name"])},
            "geometry": simplifier_geometrie(f["geometry"]),
            "_brut": f["geometry"],
        })
    provinces.sort(key=lambda f: f["properties"]["nom"])

    villes = []
    for f in lieux["features"]:
        pr = f["properties"]
        if pr.get("adm0_a3") != "TCD":
            continue
        x, y = f["geometry"]["coordinates"]
        code = CORRECTIONS_VILLES.get(pr["name"]) or next(
            (p["properties"]["code"] for p in provinces if point_dans_geometrie(x, y, p["_brut"])), None)
        villes.append({
            "type": "Feature",
            "properties": {
                "nom": pr["name"],
                "province_code": code,
                "population_estimee": pr.get("pop_max"),
                "capitale": pr.get("featurecla") == "Admin-0 capital",
            },
            "geometry": {"type": "Point", "coordinates": [round(x, 4), round(y, 4)]},
        })
    villes.sort(key=lambda f: -(f["properties"]["population_estimee"] or 0))
    for p in provinces:
        del p["_brut"]

    fichiers = {
        "tchad_frontiere.geojson": frontiere_geo,
        "tchad_provinces.geojson": {"type": "FeatureCollection", "features": provinces},
        "tchad_villes.geojson": {"type": "FeatureCollection", "features": villes},
    }
    empreintes = {}
    for nom, contenu in fichiers.items():
        texte = json.dumps(contenu, ensure_ascii=False, separators=(",", ":"))
        (CIBLE / nom).write_text(texte, encoding="utf-8")
        empreintes[nom] = hashlib.sha256(texte.encode()).hexdigest()
    (CIBLE / "SOURCES.json").write_text(json.dumps({
        "source": "Natural Earth 10m (admin 0, admin 1, populated places simple)",
        "url": "https://www.naturalearthdata.com",
        "depot": "https://github.com/nvkelso/natural-earth-vector",
        "licence": "Domaine public (Natural Earth Terms of Use)",
        "construit_le": date.today().isoformat(),
        "tolerance_simplification_degres": TOLERANCE,
        "limites_connues": [
            "La source regroupe Ennedi-Est et Ennedi-Ouest en une seule unité (22 unités au lieu de 23).",
            "Rattachement de Moundou corrigé manuellement (TD-LO) : point source en limite de province.",
            "Populations : estimations Natural Earth, à usage d'affichage uniquement.",
            "Les limites sont indicatives et ne font pas foi : à remplacer par les données officielles "
            "de l'administration territoriale tchadienne dès leur validation.",
        ],
        "sha256": empreintes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(provinces)} provinces, {len(villes)} villes écrites dans {CIBLE}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
