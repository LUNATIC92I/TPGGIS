"""Jetons de conception du client : couleurs semantiques, espacements, rayons et tailles.

Toutes les couleurs de l'interface proviennent de ce fichier. Les feuilles de
style QSS, la carte, les graphiques et les icones les lisent par leur nom
semantique, jamais par une valeur codee en dur.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tpgis.shared.charte import ANTHRACITE, BRUN_TERRE, IVOIRE, SABLE, VERT_KAKI, VERT_OLIVE

POLICE = '"Segoe UI", "Segoe UI Variable Text", "Noto Sans", "DejaVu Sans", sans-serif'
POLICE_CARTE = "Segoe UI"

ESPACEMENTS = {"xs": 4, "s": 8, "m": 12, "l": 16, "xl": 24}
RAYONS = {"petit": 4, "moyen": 6, "grand": 8}
TAILLES_POLICE = {
    "petite": 9,
    "normale": 10,
    "titre_section": 11,
    "titre_application": 13,
    "titre_page": 16,
    "indicateur": 22,
}
DIMENSIONS = {
    "largeur_navigation": 272,
    "hauteur_bandeau": 58,
    "hauteur_lisere": 6,
    "hauteur_champ": 22,
    "icone_navigation": 18,
}


@dataclass(frozen=True)
class Theme:
    nom: str
    libelle: str
    sombre: bool
    couleurs: dict[str, str]
    carte_sequentielle: tuple[str, ...]
    carte_tendance: tuple[str, str, str] = field(default=("", "", ""))

    def __getitem__(self, cle: str) -> str:
        return self.couleurs[cle]


CLAIR = Theme(
    nom="clair",
    libelle="Clair",
    sombre=False,
    couleurs={
        # Fonds et surfaces
        "fond": IVOIRE,
        "surface": "#FFFFFF",
        "surface_alternee": "#F7F5EE",
        "surface_entete": "#E9E4D4",
        "surface_desactivee": "#EDEBE3",
        "bordure": "#D8D2C0",
        "bordure_champ": "#8A8473",
        # Textes
        "texte": ANTHRACITE,
        "texte_secondaire": "#4F5649",
        "texte_desactive": "#7C7B72",
        "texte_titre": VERT_OLIVE,
        # Action principale
        "accent": VERT_OLIVE,
        "accent_survol": VERT_KAKI,
        "accent_texte": IVOIRE,
        "bouton_survol": "#F1EDE0",
        "bouton_appui": "#E4DCC4",
        "focus": BRUN_TERRE,
        "selection": "#E2D8B8",
        "selection_texte": ANTHRACITE,
        # Navigation laterale et bandeau
        "navigation_fond": VERT_OLIVE,
        "navigation_texte": IVOIRE,
        "navigation_survol": "#334A37",
        "navigation_selection": VERT_KAKI,
        "navigation_indicateur": SABLE,
        "bandeau_fond": ANTHRACITE,
        "bandeau_texte": IVOIRE,
        "bandeau_texte_secondaire": SABLE,
        "bandeau_bordure": "#5E6656",
        "bandeau_survol": "#2F362F",
        # Etats
        "erreur": "#9A2B1E",
        "erreur_fond": "#F8E9E4",
        "danger_bordure": "#C99A8F",
        "avertissement_fond": "#F6EDD2",
        "avertissement_bordure": SABLE,
        "avertissement_texte": "#584322",
        "fictif_fond": "#EFE6CD",
        "fictif_texte": "#5C4526",
        "succes": "#3B6436",
        # Carte et graphiques
        "carte_fond": IVOIRE,
        "carte_frontiere": ANTHRACITE,
        "carte_limite_province": "#FFFFFF",
        "carte_survol": BRUN_TERRE,
        "carte_libelle": ANTHRACITE,
        "carte_halo": "#FFFFFF",
        "carte_sans_donnee": "#E3E0D6",
        "carte_ville": ANTHRACITE,
        "carte_police": "#2F3A4A",
        "carte_gendarmerie": BRUN_TERRE,
        "graphique_serie": VERT_KAKI,
        "graphique_grille": "#E6E1D3",
        "info_bulle_fond": ANTHRACITE,
        "info_bulle_texte": IVOIRE,
        "icone": IVOIRE,
        "icone_contenu": VERT_OLIVE,
    },
    carte_sequentielle=("#F4F0E1", "#DDD5B4", "#BDB68E", "#8E966A", "#5E7049", VERT_OLIVE),
    carte_tendance=("#7E9471", "#F2EFE4", BRUN_TERRE),
)

SOMBRE = Theme(
    nom="sombre",
    libelle="Sombre",
    sombre=True,
    couleurs={
        "fond": "#171B17",
        "surface": ANTHRACITE,
        "surface_alternee": "#262B25",
        "surface_entete": "#2D352C",
        "surface_desactivee": "#22261F",
        "bordure": "#3A4238",
        "bordure_champ": "#7D8672",
        "texte": "#ECE9DE",
        "texte_secondaire": "#BDB8A6",
        "texte_desactive": "#868A7D",
        "texte_titre": SABLE,
        "accent": SABLE,
        "accent_survol": "#D6C9A2",
        "accent_texte": ANTHRACITE,
        "bouton_survol": "#2B3229",
        "bouton_appui": "#353E33",
        "focus": SABLE,
        "selection": "#3F4C36",
        "selection_texte": "#F2F0E7",
        "navigation_fond": "#1B281E",
        "navigation_texte": "#E7E3D6",
        "navigation_survol": "#24352A",
        "navigation_selection": VERT_OLIVE,
        "navigation_indicateur": SABLE,
        "bandeau_fond": "#111411",
        "bandeau_texte": IVOIRE,
        "bandeau_texte_secondaire": SABLE,
        "bandeau_bordure": "#4A5246",
        "bandeau_survol": "#252B24",
        "erreur": "#F0A08F",
        "erreur_fond": "#3A2420",
        "danger_bordure": "#8F5A4E",
        "avertissement_fond": "#352E1F",
        "avertissement_bordure": BRUN_TERRE,
        "avertissement_texte": "#EADCB3",
        "fictif_fond": "#3B3322",
        "fictif_texte": "#EADCB3",
        "succes": "#9CC48F",
        "carte_fond": "#171B17",
        "carte_frontiere": SABLE,
        "carte_limite_province": "#171B17",
        "carte_survol": SABLE,
        "carte_libelle": "#F2F0E7",
        "carte_halo": "#171B17",
        "carte_sans_donnee": "#2E332C",
        "carte_ville": "#F2F0E7",
        "carte_police": "#A9B9CC",
        "carte_gendarmerie": "#D9B98F",
        "graphique_serie": "#A7B58C",
        "graphique_grille": "#343B32",
        "info_bulle_fond": "#F2F0E7",
        "info_bulle_texte": ANTHRACITE,
        "icone": "#E7E3D6",
        "icone_contenu": SABLE,
    },
    carte_sequentielle=("#2B312A", "#3C4A36", "#536344", "#7A7F55", "#A39A6E", SABLE),
    carte_tendance=("#6F8A63", "#3A3F37", "#A9805A"),
)

THEMES = {t.nom: t for t in (CLAIR, SOMBRE)}

# Paires (texte, fond, minimum WCAG 2.1) a respecter dans chaque theme.
# 4,5 pour le texte courant ; 3 pour les grands titres et les composants d'interface.
PAIRES_CONTRASTE = [
    ("texte", "fond", 4.5),
    ("texte", "surface", 4.5),
    ("texte", "surface_alternee", 4.5),
    ("texte", "surface_entete", 4.5),
    ("texte_secondaire", "fond", 4.5),
    ("texte_secondaire", "surface", 4.5),
    ("texte_titre", "fond", 4.5),
    ("texte_titre", "surface", 4.5),
    ("texte_desactive", "surface_desactivee", 3.0),
    ("accent_texte", "accent", 4.5),
    ("accent_texte", "accent_survol", 4.5),
    ("navigation_texte", "navigation_fond", 4.5),
    ("navigation_texte", "navigation_survol", 4.5),
    ("navigation_texte", "navigation_selection", 4.5),
    ("navigation_indicateur", "navigation_selection", 3.0),
    ("navigation_indicateur", "navigation_fond", 4.5),
    ("bandeau_texte", "bandeau_fond", 4.5),
    ("bandeau_texte_secondaire", "bandeau_fond", 4.5),
    ("selection_texte", "selection", 4.5),
    ("erreur", "surface", 4.5),
    ("erreur", "fond", 4.5),
    ("avertissement_texte", "avertissement_fond", 4.5),
    ("fictif_texte", "fictif_fond", 4.5),
    ("info_bulle_texte", "info_bulle_fond", 4.5),
    ("bordure_champ", "surface", 3.0),
    ("focus", "surface", 3.0),
    ("carte_frontiere", "carte_fond", 3.0),
    ("carte_libelle", "carte_halo", 4.5),
    ("graphique_serie", "surface", 3.0),
    ("carte_police", "carte_fond", 3.0),
    ("carte_gendarmerie", "carte_fond", 3.0),
]
