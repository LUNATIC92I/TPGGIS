"""Generation des documents administratifs (PDF) et des exports (CSV).

Les modeles reprennent l'en tete et la mention de bas de page configurees
par l'institution. Chaque document genere recoit un numero unique et chaque
generation est tracee dans le journal d'audit.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session as SessionBD
from xml.sax.saxutils import escape

from tpgis.server.config import ParametresServeur
from tpgis.server.database.base import maintenant
from tpgis.server.services import audit, plaintes, statistiques
from tpgis.server.services.auth import exiger_reauthentification_recente
from tpgis.server.services.commun import lire_parametre, prochain_numero
from tpgis.server.services.contexte import Contexte
from tpgis.shared.enums import LIBELLES_ROLE_PERSONNE, LIBELLES_STATUT_PLAINTE
from tpgis.shared.permissions import Permission

BLEU_NUIT = colors.HexColor("#0B1F3A")
GRIS = colors.HexColor("#E6E9EF")


def _styles():
    base = getSampleStyleSheet()
    return {
        "entete": ParagraphStyle("entete", parent=base["Normal"], alignment=TA_CENTER, fontSize=9, leading=11),
        "titre": ParagraphStyle("titre", parent=base["Title"], fontSize=15, textColor=BLEU_NUIT, spaceAfter=6),
        "sous_titre": ParagraphStyle("st", parent=base["Heading3"], textColor=BLEU_NUIT, spaceBefore=8),
        "normal": ParagraphStyle("n", parent=base["Normal"], fontSize=9.5, leading=12),
        "petit": ParagraphStyle("p", parent=base["Normal"], fontSize=7.5, textColor=colors.grey),
    }


def _p(texte, style) -> Paragraph:
    return Paragraph(escape(str(texte if texte is not None else "")).replace("\n", "<br/>"), style)


def _document(bd: SessionBD, titre: str, numero: str, ctx: Contexte, corps: list) -> bytes:
    s = _styles()
    tampon = io.BytesIO()
    pied = lire_parametre(bd, "institution.pied_page")

    def _pied_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(2 * cm, 1.2 * cm, f"{numero}  |  {pied}"[:150])
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.5 * cm,
                            bottomMargin=2 * cm, title=titre, author="TPGIS")
    elements = [_p(ligne, s["entete"]) for ligne in lire_parametre(bd, "institution.entete")]
    elements += [
        Spacer(1, 0.4 * cm),
        _p(titre, s["titre"]),
        _p(f"Document n° {numero}  |  Généré le {maintenant():%d/%m/%Y à %H:%M} UTC par "
           f"{ctx.utilisateur.grade or ''} {ctx.utilisateur.nom} ({ctx.utilisateur.identifiant})", s["petit"]),
        Spacer(1, 0.3 * cm),
    ]
    doc.build(elements + corps, onFirstPage=_pied_page, onLaterPages=_pied_page)
    return tampon.getvalue()


def _tableau(lignes: list[list], largeurs=None, entete=True) -> Table:
    s = _styles()
    donnees = [[_p(c, s["normal"]) for c in ligne] for ligne in lignes]
    t = Table(donnees, colWidths=largeurs, repeatRows=1 if entete else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if entete:
        style += [("BACKGROUND", (0, 0), (-1, 0), GRIS)]
    else:
        style += [("BACKGROUND", (0, 0), (0, -1), GRIS)]
    t.setStyle(TableStyle(style))
    return t


def fiche_plainte(bd: SessionBD, ctx: Contexte, plainte_id: str) -> tuple[str, bytes]:
    ctx.exiger(Permission.PLAINTE_LIRE)
    d = plaintes.detail(bd, ctx, plainte_id)
    numero = prochain_numero(bd, "FP", d["numero"].split("-")[1] if "-" in d["numero"] else None)
    s = _styles()
    infos = [
        ["Numéro de plainte", d["numero"]],
        ["Reçue le", f"{d['recue_le']:%d/%m/%Y %H:%M} UTC"],
        ["Service d'enregistrement", d["service_enregistrement"]],
        ["Unité", d["unite_nom"]],
        ["Agent responsable", d["agent_responsable"] or "Non désigné"],
        ["Type de plainte", d["categorie"] or "Non catégorisé"],
        ["Date déclarée des faits", d["date_faits"].strftime("%d/%m/%Y") if d["date_faits"] else "Non précisée"],
        ["Lieu déclaré des faits", d["lieu_faits"] or "Non précisé"],
        ["Statut", LIBELLES_STATUT_PLAINTE.get(d["statut"], d["statut"])],
        ["Références de procédure", d["references_procedure"] or ""],
    ]
    corps = [
        _tableau(infos, [5.5 * cm, 11.5 * cm], entete=False),
        _p("Faits allégués (déclaration du plaignant, non vérifiée)", s["sous_titre"]),
        _p(d["description"], s["normal"]),
    ]
    if d["personnes"]:
        corps += [_p("Personnes concernées", s["sous_titre"]),
                  _tableau([["N° interne", "Nom et prénoms", "Rôle procédural"]] + [
                      [x["numero_interne"], f"{x['nom']} {x['prenoms'] or ''}",
                       LIBELLES_ROLE_PERSONNE.get(x["role"], x["role"])] for x in d["personnes"]
                  ], [3.5 * cm, 7 * cm, 6.5 * cm])]
    corps += [
        Spacer(1, 0.4 * cm),
        _p("Rappel : l'enregistrement d'une plainte ne vaut pas reconnaissance de culpabilité. Toute personne mise "
           "en cause est présumée innocente tant que sa culpabilité n'a pas été établie par une juridiction.",
           s["petit"]),
        Spacer(1, 1 * cm),
        _tableau([["Signature du plaignant", "Signature et cachet de l'agent"], ["\n\n\n", "\n\n\n"]],
                 [8.5 * cm, 8.5 * cm]),
    ]
    contenu = _document(bd, "FICHE DE PLAINTE", numero, ctx, corps)
    audit.enregistrer_ctx(bd, ctx, "EXPORT_FICHE_PLAINTE", type_ressource="plainte", ressource_id=plainte_id,
                          details={"numero_document": numero})
    return f"{numero}.pdf", contenu


def bordereau_transmission(bd: SessionBD, ctx: Contexte, plainte_id: str) -> tuple[str, bytes]:
    ctx.exiger(Permission.PLAINTE_LIRE)
    d = plaintes.detail(bd, ctx, plainte_id)
    numero = prochain_numero(bd, "BT", None)
    s = _styles()
    corps = [
        _tableau([
            ["Expéditeur", d["unite_nom"]],
            ["Destinataire", d["service_destinataire"] or "À compléter"],
            ["Objet", f"Transmission de la plainte {d['numero']}"],
            ["Motif", d["motif_statut"] or ""],
        ], [5 * cm, 12 * cm], entete=False),
        _p("Pièces transmises", s["sous_titre"]),
        _tableau([["N°", "Désignation", "Nombre"], ["1", f"Fiche de plainte {d['numero']}", "1"],
                  ["2", "Pièces justificatives (voir inventaire du dossier)", ""]], [1.5 * cm, 12 * cm, 3.5 * cm]),
        Spacer(1, 1.2 * cm),
        _tableau([["Pour l'expéditeur (nom, grade, signature)", "Accusé de réception (date, signature)"],
                  ["\n\n\n", "\n\n\n"]], [8.5 * cm, 8.5 * cm]),
    ]
    contenu = _document(bd, "BORDEREAU DE TRANSMISSION", numero, ctx, corps)
    audit.enregistrer_ctx(bd, ctx, "EXPORT_BORDEREAU", type_ressource="plainte", ressource_id=plainte_id,
                          details={"numero_document": numero})
    return f"{numero}.pdf", contenu


def rapport_statistique_pdf(bd: SessionBD, ctx: Contexte, p: ParametresServeur, du: date | None, au: date | None,
                            unite_id: str | None, categorie_id: str | None) -> tuple[str, bytes]:
    ctx.exiger(Permission.EXPORT_REALISER, Permission.STATISTIQUES_LIRE)
    exiger_reauthentification_recente(ctx, p)
    stats = statistiques.tableau_de_bord(bd, ctx, du, au, unite_id, categorie_id)
    numero = prochain_numero(bd, "RA", None)
    s = _styles()
    i = stats["indicateurs"]
    corps = [
        _p(f"Période : {du or 'origine'} au {au or 'ce jour'}  |  Données agrégées, sans information nominative.",
           s["normal"]),
        _p("Indicateurs", s["sous_titre"]),
        _tableau([["Indicateur", "Valeur"],
                  ["Plaintes enregistrées", i["plaintes_total"]],
                  ["Plaintes en attente de traitement", i["plaintes_en_attente"]],
                  ["En attente depuis plus de 30 jours", i["plaintes_en_attente_plus_30_jours"]],
                  ["Dossiers en cours", i["dossiers_en_cours"]],
                  ["Plaintes clôturées", i["plaintes_cloturees"]]], [11 * cm, 6 * cm]),
        _p("Répartition par catégorie de faits", s["sous_titre"]),
        _tableau([["Catégorie", "Nombre"]] + [[c["categorie"], c["nombre"]] for c in stats["par_categorie"]],
                 [13 * cm, 4 * cm]),
        _p("Évolution mensuelle", s["sous_titre"]),
        _tableau([["Mois", "Plaintes"]] + [[m["mois"], m["nombre"]] for m in stats["evolution_mensuelle"]],
                 [8.5 * cm, 8.5 * cm]),
        _p("Qualité et complétude des données", s["sous_titre"]),
        _tableau([["Mesure", "Taux (%)"]] + [[k.replace("_", " ").replace(" pct", ""), v]
                                            for k, v in stats["qualite_donnees"].items()], [13 * cm, 4 * cm]),
    ]
    contenu = _document(bd, "RAPPORT STATISTIQUE D'ACTIVITÉ", numero, ctx, corps)
    audit.enregistrer_ctx(bd, ctx, "EXPORT_RAPPORT_PDF", type_ressource="statistiques",
                          details={"numero_document": numero, "du": du, "au": au})
    return f"{numero}.pdf", contenu


def export_statistiques_csv(bd: SessionBD, ctx: Contexte, p: ParametresServeur, du: date | None, au: date | None,
                            unite_id: str | None, categorie_id: str | None) -> tuple[str, bytes]:
    ctx.exiger(Permission.EXPORT_REALISER, Permission.STATISTIQUES_LIRE)
    exiger_reauthentification_recente(ctx, p)
    stats = statistiques.tableau_de_bord(bd, ctx, du, au, unite_id, categorie_id)
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";")
    w.writerow(["section", "libelle", "valeur"])
    for k, v in stats["indicateurs"].items():
        w.writerow(["indicateur", k, v])
    for c in stats["par_categorie"]:
        w.writerow(["categorie", c["categorie"], c["nombre"]])
    for pr in stats["par_province"]:
        w.writerow(["province", pr["province_code"] or "non renseignee", pr["nombre"]])
    for m in stats["evolution_mensuelle"]:
        w.writerow(["mois", m["mois"], m["nombre"]])
    for u in stats["activite_unites"]:
        w.writerow(["unite", u["unite"], u["plaintes"]])
    for k, v in stats["qualite_donnees"].items():
        w.writerow(["qualite", k, v])
    numero = prochain_numero(bd, "EX", None)
    audit.enregistrer_ctx(bd, ctx, "EXPORT_STATISTIQUES_CSV", type_ressource="statistiques",
                          details={"numero_document": numero, "du": du, "au": au})
    # BOM UTF 8 pour une ouverture correcte dans les tableurs Windows.
    return f"{numero}.csv", ("﻿" + tampon.getvalue()).encode("utf-8")
