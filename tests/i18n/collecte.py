"""Collecte des textes francais a traduire (client, libelles, messages du serveur)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CLASSES_ERREUR = {
    "ErreurMetier", "NonAuthentifie", "AccesRefuse", "Introuvable", "Conflit", "DonneesInvalides",
    "TropDeRequetes", "ServiceIndisponible",
}  # fmt: skip
# Constantes de module ou de classe affichees apres traduction (titres, colonnes, menus...).
CONSTANTES_AFFICHEES = {
    "titre", "sous_titre", "MODULES", "MESSAGES_STATUT", "TEXTE", "COMPTES", "NOM_COMPLET_DEFAUT",
    "SOUS_TITRE_DEFAUT", "HORS_PERIMETRE",
}  # fmt: skip


def _fichiers(*chemins: str):
    for c in chemins:
        p = RACINE / c
        yield from ([p] if p.is_file() else sorted(p.rglob("*.py")))


def _textes(noeud) -> list[str]:
    return [
        n.value for n in ast.walk(noeud) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip()
    ]


TEXTES_TR: dict[str, str] = {}


def cles_client() -> dict[str, str]:
    """Textes passes a tr(), constantes affichees, colonnes de tableaux et libelles."""
    cles: dict[str, str] = {}
    for f in _fichiers("tpgis/client", "tpgis/demonstration_autonome.py"):
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        origine = str(f.relative_to(RACINE))
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("tr", "traduire"):
                if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    cles.setdefault(n.args[0].value, origine)
                    TEXTES_TR.setdefault(n.args[0].value, origine)
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
                noms = {t.id for t in cibles if isinstance(t, ast.Name)}
                if not n.value:
                    continue
                if noms & CONSTANTES_AFFICHEES:
                    for t in _textes(n.value):
                        if any(c.islower() for c in t):
                            cles.setdefault(t, origine)
                elif any(nom.startswith("COLONNES") for nom in noms):
                    for elt in ast.walk(n.value):
                        if isinstance(elt, ast.Tuple) and len(elt.elts) >= 2 and isinstance(elt.elts[1], ast.Constant):
                            cles.setdefault(elt.elts[1].value, origine)
        if f.name == "libelles.py":
            for n in arbre.body:
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
                    for v in n.value.values:
                        if isinstance(v, ast.Constant):
                            cles.setdefault(v.value, origine)
    # Colonnes declarees dans les fonctions (TableauDonnees([...]))
    for f in _fichiers("tpgis/client/windows"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "TableauDonnees" and n.args:
                for elt in ast.walk(n.args[0]):
                    if isinstance(elt, ast.Tuple) and len(elt.elts) >= 2 and isinstance(elt.elts[1], ast.Constant):
                        cles.setdefault(elt.elts[1].value, str(f.relative_to(RACINE)))
    # Libelles partages (statuts, roles, natures de l'information)
    for n in ast.walk(ast.parse((RACINE / "tpgis/shared/enums.py").read_text(encoding="utf-8"))):
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "").startswith("LIBELLES_") for t in n.targets):
            if isinstance(n.value, ast.Dict):
                for v in n.value.values:
                    if isinstance(v, ast.Constant):
                        cles.setdefault(v.value, "tpgis/shared/enums.py")
    # Referentiels initiaux traduits a l'affichage : roles, permissions, categories de faits.
    for chemin, noms in (
        ("tpgis/shared/permissions.py", {"LIBELLES_PERMISSIONS", "ROLES_INITIAUX"}),
        ("tpgis/server/database/seed/demonstration.py", {"CATEGORIES"}),
    ):
        for n in ast.parse((RACINE / chemin).read_text(encoding="utf-8")).body:
            cibles = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.AnnAssign) else []
            if not any(getattr(t, "id", "") in noms for t in cibles):
                continue
            if isinstance(n.value, ast.Dict):
                textes = [v.value for v in n.value.values if isinstance(v, ast.Constant)]
            elif any(getattr(t, "id", "") == "ROLES_INITIAUX" for t in cibles):
                textes = [
                    v.value
                    for d in n.value.elts
                    for k, v in zip(d.keys, d.values, strict=True)
                    if getattr(k, "value", "") == "libelle" and isinstance(v, ast.Constant)
                ]
            else:
                textes = [e.elts[1].value for e in n.value.elts if isinstance(e, ast.Tuple)]
            for t in textes:
                cles.setdefault(t, chemin)
    return cles


def cles_serveur() -> dict[str, str]:
    """Messages d'erreur renvoyes par le serveur (modeles a parametres nommes)."""
    cles: dict[str, str] = {}
    for f in _fichiers("tpgis/server"):
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        origine = str(f.relative_to(RACINE))
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call):
                nom = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                if nom in CLASSES_ERREUR and n.args and isinstance(n.args[0], ast.Constant):
                    cles.setdefault(n.args[0].value, origine)
                if nom == "_reponse_erreur" and len(n.args) >= 3 and isinstance(n.args[2], ast.Constant):
                    cles.setdefault(n.args[2].value, origine)
            if isinstance(n, ast.Assign) and any(getattr(t, "id", "") in CONSTANTES_AFFICHEES for t in n.targets):
                for t in _textes(n.value):
                    cles.setdefault(t, origine)
    return cles


def _affichable(texte: str) -> bool:
    """Exclut les identifiants techniques (icones, permissions, comptes de demonstration)."""
    return not re.fullmatch(r"[a-z0-9_.]+", texte)


def toutes_les_cles() -> dict[str, str]:
    toutes = {**cles_serveur(), **cles_client()}
    # Un texte explicitement passe a tr() est toujours affiche, meme court et en minuscules.
    return {k: v for k, v in toutes.items() if _affichable(k) or k in TEXTES_TR}
