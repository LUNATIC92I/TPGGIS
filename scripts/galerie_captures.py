"""Assemble toutes les captures d'ecran dans docs/captures/galerie_interfaces.pdf."""

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

RACINE = Path(__file__).resolve().parents[1] / "docs" / "captures"
DOSSIER = RACINE / "interfaces"

SECTIONS = [
    (
        "Connexion sécurisée",
        [
            ("00_connexion", "Fenêtre de connexion (environnement de démonstration signalé)"),
            ("00_connexion_code_mfa", "Second facteur demandé pour un compte privilégié"),
            ("21_changement_mot_de_passe", "Changement de mot de passe obligatoire"),
            ("20_confirmation_identite", "Confirmation d'identité avant une opération sensible"),
        ],
    ),
    ("Modules (responsable d'unité)", [(p.stem, None) for p in sorted(DOSSIER.glob("responsable_*.png"))]),
    (
        "Plaintes",
        [
            ("10_formulaire_nouvelle_plainte", "Enregistrement d'une plainte"),
            *[(f"11_detail_plainte_onglet_{j}", f"Détail d'une plainte, onglet {j}") for j in range(1, 6)],
        ],
    ),
    (
        "Personnes",
        [
            ("12_formulaire_personne", "Nouvelle personne (informations inconnues laissées vides)"),
            ("13_detection_doublons", "Détection des doublons : décision humaine obligatoire"),
            ("15_associer_une_personne", "Association d'une personne avec son rôle procédural"),
            *[
                (f"14_fiche_personne_onglet_{j}", f"Fiche personne (finalité journalisée), onglet {j}")
                for j in range(1, 5)
            ],
        ],
    ),
    (
        "Faits et dossiers",
        [
            ("16_formulaire_fait", "Enregistrement d'un fait signalé"),
            ("17_detail_fait", "Détail d'un fait"),
            ("18_formulaire_dossier", "Ouverture d'un dossier"),
            *[(f"19_detail_dossier_onglet_{j}", f"Détail d'un dossier, onglet {j}") for j in range(1, 8)],
        ],
    ),
    (
        "Recherche et pièces",
        [
            ("22_recherche_avec_resultats", "Recherche avec niveaux de correspondance et trace d'audit"),
            ("23_pieces_d_une_plainte", "Pièces d'une plainte (antivirus, SHA 256, versions)"),
        ],
    ),
    (
        "Autres profils",
        [(p.stem, None) for p in sorted(DOSSIER.glob("admin_fonctionnel_*.png"))]
        + [(p.stem, None) for p in sorted(DOSSIER.glob("admin_technique_*.png"))]
        + [
            ("auditeur_05_journal_d_audit", "Journal d'audit (auditeur)"),
            ("agent_accueil_01_tableau_de_bord", "Accueil d'un agent sans accès aux statistiques"),
        ],
    ),
    (
        "Exécutable Windows (sous Wine)",
        [
            ("../windows_connexion", "TPGIS.exe : connexion"),
            ("../windows_tableau_de_bord", "TPGIS.exe : tableau de bord après MFA"),
            ("../windows_serveur_indisponible", "TPGIS.exe : serveur injoignable"),
        ],
    ),
]


def titre_auto(stem: str) -> str:
    profils = {
        "responsable": "Responsable d'unité",
        "admin_fonctionnel": "Administrateur fonctionnel",
        "admin_technique": "Administrateur technique",
    }
    for cle, libelle in profils.items():
        if stem.startswith(cle + "_"):
            reste = stem[len(cle) + 4 :]
            onglet = ""
            if "_onglet_" in reste:
                reste, n = reste.split("_onglet_")
                onglet = f", onglet {n}"
            return f"{libelle} : {reste.replace('_', ' ').strip().capitalize()}{onglet}"
    return stem


def main(sortie: Path) -> None:
    largeur, hauteur = landscape(A4)
    c = canvas.Canvas(str(sortie), pagesize=(largeur, hauteur))
    c.setTitle("TPGIS : galerie des interfaces")
    c.setFillColor(colors.HexColor("#0B1F3A"))
    c.rect(0, 0, largeur, hauteur, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(largeur / 2, hauteur / 2 + 30, "TPGIS : galerie des interfaces")
    c.setFont("Helvetica", 13)
    c.drawCentredString(
        largeur / 2, hauteur / 2 - 5, "Client de bureau, captures réelles sur données fictives de démonstration"
    )
    c.showPage()
    n = 0
    for section, elements in SECTIONS:
        for stem, titre in elements:
            chemin = (DOSSIER / f"{stem}.png").resolve()
            if not chemin.exists():
                continue
            n += 1
            c.setFillColor(colors.HexColor("#0B1F3A"))
            c.rect(0, hauteur - 46, largeur, 46, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(24, hauteur - 29, f"{section}  |  {titre or titre_auto(stem)}")
            c.setFont("Helvetica", 9)
            c.drawRightString(largeur - 24, hauteur - 29, f"{n}")
            image = ImageReader(str(chemin))
            iw, ih = image.getSize()
            echelle = min((largeur - 48) / iw, (hauteur - 80) / ih)
            w, h = iw * echelle, ih * echelle
            c.drawImage(image, (largeur - w) / 2, (hauteur - 56 - h) / 2 + 4, w, h)
            c.setStrokeColor(colors.HexColor("#DDE2EA"))
            c.rect((largeur - w) / 2, (hauteur - 56 - h) / 2 + 4, w, h)
            c.showPage()
    c.save()
    print(f"{n} captures dans {sortie}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else RACINE / "galerie_interfaces.pdf")
