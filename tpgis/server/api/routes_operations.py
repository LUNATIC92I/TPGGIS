"""Routes operationnelles : plaintes, personnes, faits, dossiers, documents,
biometrie et recherche."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.api.deps import base, contexte, parametres, valider
from tpgis.server.config import ParametresServeur
from tpgis.server.services import biometrie, documents, dossiers, faits, personnes, plaintes, rapports, recherche
from tpgis.server.services.contexte import Contexte
from tpgis.server.services.erreurs import DonneesInvalides
from tpgis.shared import schemas
from tpgis.shared.enums import TypePiece

routeur = APIRouter()


def reponse_fichier(nom: str, type_mime: str, contenu: bytes) -> Response:
    return Response(
        content=contenu,
        media_type=type_mime,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# Plaintes


@routeur.get("/plaintes", tags=["Plaintes"])
def lister_plaintes(statut: str | None = None, unite_id: str | None = None, categorie_id: str | None = None,
                    du: date | None = None, au: date | None = None, numero: str | None = Query(None, max_length=48),
                    page: int = 1, taille: int = 50, ctx: Contexte = Depends(contexte),
                    bd: SessionBD = Depends(base)):
    return valider(bd, plaintes.lister(bd, ctx, statut=statut, unite_id=unite_id, categorie_id=categorie_id, du=du,
                                       au=au, numero=numero, page=page, taille=taille))


@routeur.post("/plaintes", tags=["Plaintes"], status_code=201)
def creer_plainte(donnees: schemas.PlainteCreation, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, plaintes.creer(bd, ctx, donnees))


@routeur.get("/plaintes/{plainte_id}", tags=["Plaintes"])
def detail_plainte(plainte_id: str, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, plaintes.detail(bd, ctx, plainte_id))


@routeur.patch("/plaintes/{plainte_id}", tags=["Plaintes"])
def modifier_plainte(plainte_id: str, donnees: schemas.PlainteModification, ctx: Contexte = Depends(contexte),
                     bd: SessionBD = Depends(base)):
    return valider(bd, plaintes.modifier(bd, ctx, plainte_id, donnees))


@routeur.post("/plaintes/{plainte_id}/statut", tags=["Plaintes"])
def statut_plainte(plainte_id: str, donnees: schemas.ChangementStatutPlainte, ctx: Contexte = Depends(contexte),
                   bd: SessionBD = Depends(base)):
    return valider(bd, plaintes.changer_statut(bd, ctx, plainte_id, donnees))


@routeur.post("/plaintes/{plainte_id}/personnes", tags=["Plaintes"], status_code=201)
def lier_personne_plainte(plainte_id: str, lien: schemas.LienPersonne, ctx: Contexte = Depends(contexte),
                          bd: SessionBD = Depends(base)):
    return valider(bd, plaintes.ajouter_personne(bd, ctx, plainte_id, lien))


@routeur.delete("/plaintes/{plainte_id}/personnes/{lien_id}", tags=["Plaintes"])
def delier_personne_plainte(plainte_id: str, lien_id: int, motif: str = Query(min_length=10, max_length=500),
                            ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, plaintes.retirer_personne(bd, ctx, plainte_id, lien_id, motif))


@routeur.get("/plaintes/{plainte_id}/fiche.pdf", tags=["Plaintes"])
def fiche_plainte(plainte_id: str, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    nom, contenu = rapports.fiche_plainte(bd, ctx, plainte_id)
    bd.commit()
    return reponse_fichier(nom, "application/pdf", contenu)


@routeur.get("/plaintes/{plainte_id}/bordereau.pdf", tags=["Plaintes"])
def bordereau(plainte_id: str, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    nom, contenu = rapports.bordereau_transmission(bd, ctx, plainte_id)
    bd.commit()
    return reponse_fichier(nom, "application/pdf", contenu)


# Personnes


@routeur.get("/personnes", tags=["Personnes"])
def lister_personnes(texte: str | None = Query(None, max_length=120), page: int = 1, taille: int = 50,
                     ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, personnes.lister(bd, ctx, texte, page, taille))


@routeur.post("/personnes", tags=["Personnes"], status_code=201)
def creer_personne(donnees: schemas.PersonneCreation, ctx: Contexte = Depends(contexte),
                   bd: SessionBD = Depends(base)):
    return valider(bd, personnes.creer(bd, ctx, donnees))


@routeur.post("/personnes/doublons", tags=["Personnes"])
def doublons(criteres: schemas.CritereDoublon, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    from tpgis.shared.permissions import Permission

    ctx.exiger(Permission.PERSONNE_LIRE)
    resultat = personnes.rechercher_candidats(bd, ctx, criteres.nom, criteres.prenoms, criteres.date_naissance,
                                              criteres.lieu_naissance, criteres.numero_document,
                                              criteres.exclure_id)
    from tpgis.server.services import audit

    audit.enregistrer_ctx(bd, ctx, "PERSONNE_DOUBLONS", type_ressource="personne",
                          details={"candidats": len(resultat)})
    return valider(bd, resultat)


@routeur.post("/personnes/fusions", tags=["Personnes"], status_code=202)
def demander_fusion(donnees: schemas.DemandeFusion, ctx: Contexte = Depends(contexte),
                    bd: SessionBD = Depends(base)):
    return valider(bd, personnes.demander_fusion(bd, ctx, donnees))


@routeur.get("/personnes/{personne_id}", tags=["Personnes"])
def detail_personne(personne_id: str, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, personnes.detail(bd, ctx, personne_id))


@routeur.patch("/personnes/{personne_id}", tags=["Personnes"])
def modifier_personne(personne_id: str, donnees: schemas.PersonneModification, ctx: Contexte = Depends(contexte),
                      bd: SessionBD = Depends(base)):
    return valider(bd, personnes.modifier(bd, ctx, personne_id, donnees))


# Faits


@routeur.get("/faits", tags=["Faits et infractions"])
def lister_faits(categorie_id: str | None = None, etat: str | None = None, nature: str | None = None,
                 du: date | None = None, au: date | None = None, page: int = 1, taille: int = 50,
                 ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, faits.lister(bd, ctx, categorie_id=categorie_id, etat=etat, nature=nature, du=du, au=au,
                                    page=page, taille=taille))


@routeur.post("/faits", tags=["Faits et infractions"], status_code=201)
def creer_fait(donnees: schemas.FaitCreation, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, faits.creer(bd, ctx, donnees))


@routeur.get("/faits/{fait_id}", tags=["Faits et infractions"])
def detail_fait(fait_id: str, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, faits.detail(bd, ctx, fait_id))


@routeur.patch("/faits/{fait_id}", tags=["Faits et infractions"])
def modifier_fait(fait_id: str, donnees: schemas.FaitModification, ctx: Contexte = Depends(contexte),
                  bd: SessionBD = Depends(base)):
    return valider(bd, faits.modifier(bd, ctx, fait_id, donnees))


@routeur.post("/faits/{fait_id}/personnes", tags=["Faits et infractions"], status_code=201)
def lier_personne_fait(fait_id: str, lien: schemas.LienPersonne, ctx: Contexte = Depends(contexte),
                       bd: SessionBD = Depends(base)):
    return valider(bd, faits.ajouter_personne(bd, ctx, fait_id, lien))


# Dossiers


@routeur.get("/dossiers", tags=["Dossiers et procédures"])
def lister_dossiers(statut: str | None = None, unite_id: str | None = None,
                    numero: str | None = Query(None, max_length=48), page: int = 1, taille: int = 50,
                    ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, dossiers.lister(bd, ctx, statut=statut, unite_id=unite_id, numero=numero, page=page,
                                       taille=taille))


@routeur.post("/dossiers", tags=["Dossiers et procédures"], status_code=201)
def creer_dossier(donnees: schemas.DossierCreation, ctx: Contexte = Depends(contexte),
                  bd: SessionBD = Depends(base)):
    return valider(bd, dossiers.creer(bd, ctx, donnees))


@routeur.get("/dossiers/{dossier_id}", tags=["Dossiers et procédures"])
def detail_dossier(dossier_id: str, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, dossiers.detail(bd, ctx, dossier_id))


@routeur.patch("/dossiers/{dossier_id}", tags=["Dossiers et procédures"])
def modifier_dossier(dossier_id: str, donnees: schemas.DossierModification, ctx: Contexte = Depends(contexte),
                     bd: SessionBD = Depends(base)):
    return valider(bd, dossiers.modifier(bd, ctx, dossier_id, donnees))


@routeur.post("/dossiers/{dossier_id}/actes", tags=["Dossiers et procédures"], status_code=201)
def ajouter_acte(dossier_id: str, donnees: schemas.ActeCreation, ctx: Contexte = Depends(contexte),
                 bd: SessionBD = Depends(base)):
    return valider(bd, dossiers.ajouter_acte(bd, ctx, dossier_id, donnees))


@routeur.post("/dossiers/{dossier_id}/plaintes", tags=["Dossiers et procédures"])
def rattacher_plainte(dossier_id: str, donnees: schemas.RattachementPlainte, ctx: Contexte = Depends(contexte),
                      bd: SessionBD = Depends(base)):
    return valider(bd, dossiers.rattacher_plainte(bd, ctx, dossier_id, donnees.plainte_id))


@routeur.post("/dossiers/{dossier_id}/personnes", tags=["Dossiers et procédures"], status_code=201)
def lier_personne_dossier(dossier_id: str, lien: schemas.LienPersonne, ctx: Contexte = Depends(contexte),
                          bd: SessionBD = Depends(base)):
    return valider(bd, dossiers.ajouter_personne(bd, ctx, dossier_id, lien))


# Documents


@routeur.get("/documents", tags=["Pièces et documents"])
def lister_documents(plainte_id: str | None = None, dossier_id: str | None = None, personne_id: str | None = None,
                     ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, documents.lister(bd, ctx, plainte_id, dossier_id, personne_id))


async def _lire_limite(fichier: UploadFile, limite: int) -> bytes:
    donnees = await fichier.read(limite + 1)
    if len(donnees) > limite:
        raise DonneesInvalides("Fichier trop volumineux.")
    return donnees


@routeur.post("/documents", tags=["Pièces et documents"], status_code=201)
async def deposer_document(fichier: UploadFile = File(...), intitule: str = Form(..., max_length=255),
                           type_piece: TypePiece = Form(...), plainte_id: str | None = Form(None),
                           dossier_id: str | None = Form(None), personne_id: str | None = Form(None),
                           ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base),
                           p: ParametresServeur = Depends(parametres)):
    meta = schemas.MetadonneesDocument(intitule=intitule, type_piece=type_piece, plainte_id=plainte_id,
                                       dossier_id=dossier_id, personne_id=personne_id)
    donnees = await _lire_limite(fichier, 200 * 1024 * 1024)
    return valider(bd, documents.deposer(bd, ctx, p, meta, fichier.filename or "fichier", donnees))


@routeur.post("/documents/{document_id}/versions", tags=["Pièces et documents"], status_code=201)
async def nouvelle_version(document_id: str, fichier: UploadFile = File(...), ctx: Contexte = Depends(contexte),
                           bd: SessionBD = Depends(base), p: ParametresServeur = Depends(parametres)):
    donnees = await _lire_limite(fichier, 200 * 1024 * 1024)
    return valider(bd, documents.deposer_version(bd, ctx, p, document_id, fichier.filename or "fichier", donnees))


@routeur.get("/documents/{document_id}/contenu", tags=["Pièces et documents"])
def telecharger_document(document_id: str, version: int | None = None, ctx: Contexte = Depends(contexte),
                         bd: SessionBD = Depends(base), p: ParametresServeur = Depends(parametres)):
    nom, type_mime, contenu = documents.telecharger(bd, ctx, p, document_id, version)
    bd.commit()
    return reponse_fichier(nom, type_mime, contenu)


# Biometrie


@routeur.get("/biometrie/personnes/{personne_id}/captures", tags=["Biométrie"])
def captures(personne_id: str, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, biometrie.lister(bd, ctx, personne_id))


@routeur.post("/biometrie/captures", tags=["Biométrie"], status_code=201)
def enregistrer_capture(donnees: schemas.CaptureCreation, ctx: Contexte = Depends(contexte),
                        bd: SessionBD = Depends(base), p: ParametresServeur = Depends(parametres)):
    return valider(bd, biometrie.enregistrer(bd, ctx, p, donnees))


@routeur.post("/biometrie/verifications", tags=["Biométrie"])
def verifier_capture(donnees: schemas.VerificationBiometrique, ctx: Contexte = Depends(contexte),
                     bd: SessionBD = Depends(base), p: ParametresServeur = Depends(parametres)):
    return valider(bd, biometrie.verifier(bd, ctx, p, donnees))


@routeur.post("/biometrie/captures/{capture_id}/suppression", tags=["Biométrie"], status_code=202)
def supprimer_capture(capture_id: str, donnees: schemas.SuppressionCapture, ctx: Contexte = Depends(contexte),
                      bd: SessionBD = Depends(base)):
    return valider(bd, biometrie.demander_suppression(bd, ctx, capture_id, donnees.motif))


@routeur.post("/biometrie/recherches", tags=["Biométrie"])
def recherche_biometrique(ctx: Contexte = Depends(contexte), p: ParametresServeur = Depends(parametres)):
    biometrie.recherche_un_contre_n(p)


# Recherche


@routeur.post("/recherche", tags=["Recherche et vérification"])
def rechercher(demande: schemas.DemandeRecherche, ctx: Contexte = Depends(contexte), bd: SessionBD = Depends(base)):
    return valider(bd, recherche.rechercher(bd, ctx, demande))
