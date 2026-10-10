"""Gestion documentaire securisee.

Controles a l'entree : extension autorisee, taille maximale, signature reelle
du fichier, structure des archives bureautiques, analyse antivirus. Les
fichiers sont stockes chiffres hors de tout repertoire public et ne sont
restitues qu'a travers l'API, apres controle des droits sur le dossier parent
et verification de l'empreinte SHA 256.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.config import ParametresServeur
from tpgis.server.database.base import maintenant, nouvel_id
from tpgis.server.database.models import Document, Personne, VersionDocument
from tpgis.server.security.crypto import ErreurChiffrement, chiffreur
from tpgis.server.services import audit
from tpgis.server.services.antivirus import creer_analyseur
from tpgis.server.services.commun import historiser, lire_parametre
from tpgis.server.services.contexte import Contexte
from tpgis.server.services.erreurs import Conflit, DonneesInvalides, ErreurMetier, Introuvable
from tpgis.shared import schemas
from tpgis.shared.enums import StatutAnalyse, TypePiece
from tpgis.shared.permissions import Permission

TYPES_MIME = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "txt": "text/plain",
}
TAILLE_DECOMPRESSEE_MAX = 200 * 1024 * 1024


def _nom_sur(nom: str) -> str:
    nom = Path(nom.replace("\\", "/")).name
    nom = re.sub(r"[^\w.\- ]", "_", nom, flags=re.UNICODE).strip(" .")
    return (nom or "fichier")[:200]


def _verifier_archive(donnees: bytes, extension: str) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(donnees)) as z:
            noms = z.namelist()
            total = sum(i.file_size for i in z.infolist())
            if total > TAILLE_DECOMPRESSEE_MAX:
                raise DonneesInvalides("Archive bureautique suspecte (taille décompressée excessive).")
            if any(n.startswith("/") or ".." in n.split("/") for n in noms):
                raise DonneesInvalides("Archive bureautique contenant des chemins non autorisés.")
            if extension == "docx":
                if "[Content_Types].xml" not in noms or not any(n.startswith("word/") for n in noms):
                    raise DonneesInvalides("Le fichier n'est pas un document Word valide.")
                if any(n.lower().endswith("vbaproject.bin") for n in noms):
                    raise DonneesInvalides("Les documents contenant des macros sont interdits.")
            if extension == "odt":
                if "mimetype" not in noms or z.read("mimetype").strip() != TYPES_MIME["odt"].encode():
                    raise DonneesInvalides("Le fichier n'est pas un document OpenDocument texte valide.")
    except zipfile.BadZipFile as exc:
        raise DonneesInvalides("Archive bureautique corrompue.") from exc


def verifier_signature(donnees: bytes, extension: str) -> None:
    """Verifie que le contenu correspond reellement a l'extension annoncee."""
    signatures = {
        "pdf": [b"%PDF-"],
        "png": [b"\x89PNG\r\n\x1a\n"],
        "jpg": [b"\xff\xd8\xff"],
        "jpeg": [b"\xff\xd8\xff"],
        "tif": [b"II*\x00", b"MM\x00*"],
        "tiff": [b"II*\x00", b"MM\x00*"],
        "docx": [b"PK\x03\x04"],
        "odt": [b"PK\x03\x04"],
    }
    if extension == "txt":
        if b"\x00" in donnees:
            raise DonneesInvalides("Fichier texte invalide (contenu binaire).")
        try:
            donnees.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DonneesInvalides("Fichier texte invalide : encodage UTF-8 attendu.") from exc
        return
    attendues = signatures.get(extension)
    if attendues is None:
        raise DonneesInvalides(f"Aucun contrôle de signature défini pour l'extension .{extension}.")
    if not any(donnees.startswith(s) for s in attendues):
        raise DonneesInvalides("Le contenu du fichier ne correspond pas à son extension.")
    if extension in ("docx", "odt"):
        _verifier_archive(donnees, extension)


def valider_fichier(bd: SessionBD, nom_fichier: str, donnees: bytes) -> tuple[str, str]:
    nom = _nom_sur(nom_fichier)
    extension = nom.rsplit(".", 1)[-1].lower() if "." in nom else ""
    autorisees = [e.lower() for e in lire_parametre(bd, "documents.extensions_autorisees")]
    if extension not in autorisees or extension not in TYPES_MIME:
        raise DonneesInvalides(f"Format non autorisé. Formats acceptés : {', '.join(autorisees)}.")
    taille_max = int(lire_parametre(bd, "documents.taille_max_octets"))
    if len(donnees) == 0:
        raise DonneesInvalides("Le fichier est vide.")
    if len(donnees) > taille_max:
        raise DonneesInvalides(f"Fichier trop volumineux (maximum {taille_max // (1024 * 1024)} Mo).")
    verifier_signature(donnees, extension)
    return nom, extension


def _parent_accessible(bd: SessionBD, ctx: Contexte, doc_ou_meta) -> str:
    """Controle l'acces au parent et retourne l'unite proprietaire."""
    from tpgis.server.services import dossiers, personnes, plaintes

    parents = [x for x in (doc_ou_meta.plainte_id, doc_ou_meta.dossier_id, doc_ou_meta.personne_id) if x]
    if len(parents) != 1:
        raise DonneesInvalides("Une pièce doit être rattachée à exactement un élément (plainte, dossier ou personne).")
    if doc_ou_meta.plainte_id:
        return plaintes.obtenir(bd, ctx, doc_ou_meta.plainte_id, "DOCUMENT_ACCES").unite_id
    if doc_ou_meta.dossier_id:
        return dossiers.obtenir(bd, ctx, doc_ou_meta.dossier_id).unite_id
    return personnes.obtenir(bd, ctx, doc_ou_meta.personne_id).unite_creation_id


def _ecrire(p: ParametresServeur, donnees: bytes) -> tuple[str, str]:
    cle_id, chiffre = chiffreur().chiffrer_octets(donnees)
    ident = nouvel_id()
    relatif = f"{ident[:2]}/{ident[2:4]}/{ident}.bin"
    chemin = p.repertoire_stockage / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(".tmp")
    temporaire.write_bytes(chiffre)
    temporaire.replace(chemin)
    return relatif, cle_id


def _analyser_et_stocker(bd: SessionBD, p: ParametresServeur, version: VersionDocument, donnees: bytes) -> None:
    resultat = creer_analyseur(p).analyser(donnees)
    version.analyse_le = maintenant()
    version.resultat_analyse = resultat.detail[:255]
    if resultat.erreur:
        version.statut_analyse = StatutAnalyse.ERREUR
    elif resultat.sain:
        version.statut_analyse = StatutAnalyse.SAIN
    else:
        version.statut_analyse = StatutAnalyse.INFECTE
    if version.statut_analyse == StatutAnalyse.INFECTE:
        # Le contenu infecte n'est jamais conserve.
        version.chemin_stockage = ""
        return
    version.chemin_stockage, version.cle_id = _ecrire(p, donnees)


def serialiser(doc: Document) -> dict:
    courante = doc.versions[-1] if doc.versions else None
    return {
        "id": doc.id,
        "intitule": doc.intitule,
        "type_piece": doc.type_piece,
        "plainte_id": doc.plainte_id,
        "dossier_id": doc.dossier_id,
        "personne_id": doc.personne_id,
        "version_courante": doc.version_courante,
        "cree_le": doc.cree_le,
        "versions": [
            {
                "numero_version": v.numero_version,
                "nom_fichier": v.nom_fichier,
                "type_mime": v.type_mime,
                "taille": v.taille,
                "sha256": v.sha256,
                "statut_analyse": v.statut_analyse,
                "resultat_analyse": v.resultat_analyse,
                "deposee_le": v.deposee_le,
            }
            for v in doc.versions
        ],
        "disponible": bool(courante and courante.statut_analyse == StatutAnalyse.SAIN),
    }


def deposer(
    bd: SessionBD,
    ctx: Contexte,
    p: ParametresServeur,
    meta: schemas.MetadonneesDocument,
    nom_fichier: str,
    donnees: bytes,
) -> dict:
    ctx.exiger(Permission.DOCUMENT_AJOUTER)
    unite_id = _parent_accessible(bd, ctx, meta)
    nom, extension = valider_fichier(bd, nom_fichier, donnees)
    if meta.type_piece == TypePiece.PHOTOGRAPHIE_IDENTIFICATION:
        if not meta.personne_id:
            raise DonneesInvalides("Une photographie d'identification doit être rattachée à une personne.")
        if extension not in ("png", "jpg", "jpeg"):
            raise DonneesInvalides("Une photographie d'identification doit être au format PNG ou JPEG.")
    doc = Document(
        intitule=meta.intitule,
        type_piece=meta.type_piece,
        plainte_id=meta.plainte_id,
        dossier_id=meta.dossier_id,
        personne_id=meta.personne_id,
        unite_id=unite_id,
        version_courante=1,
        cree_par_id=ctx.uid,
    )
    bd.add(doc)
    bd.flush()
    version = _nouvelle_version(bd, ctx, p, doc, 1, nom, extension, donnees)
    if meta.type_piece == TypePiece.PHOTOGRAPHIE_IDENTIFICATION and version.statut_analyse == StatutAnalyse.SAIN:
        personne = bd.get(Personne, meta.personne_id)
        personne.photo_document_id = doc.id
    bd.refresh(doc)
    return serialiser(doc)


def _nouvelle_version(
    bd, ctx, p, doc: Document, numero: int, nom: str, extension: str, donnees: bytes
) -> VersionDocument:
    version = VersionDocument(
        document_id=doc.id,
        numero_version=numero,
        nom_fichier=nom,
        extension=extension,
        type_mime=TYPES_MIME[extension],
        taille=len(donnees),
        sha256=hashlib.sha256(donnees).hexdigest(),
        chemin_stockage="",
        cle_id="",
        statut_analyse=StatutAnalyse.EN_ATTENTE,
        deposee_par_id=ctx.uid,
    )
    _analyser_et_stocker(bd, p, version, donnees)
    bd.add(version)
    doc.version_courante = numero
    bd.flush()
    historiser(
        bd,
        ctx,
        "document",
        doc.id,
        "DEPOT_VERSION",
        {"version": numero, "sha256": version.sha256, "analyse": version.statut_analyse},
    )
    audit.enregistrer_ctx(
        bd,
        ctx,
        "DOCUMENT_DEPOT",
        type_ressource="document",
        ressource_id=doc.id,
        unite_id=doc.unite_id,
        details={
            "version": numero,
            "sha256": version.sha256,
            "taille": version.taille,
            "analyse": version.statut_analyse,
        },
    )
    return version


def deposer_version(
    bd: SessionBD, ctx: Contexte, p: ParametresServeur, document_id: str, nom_fichier: str, donnees: bytes
) -> dict:
    ctx.exiger(Permission.DOCUMENT_AJOUTER)
    doc = _obtenir(bd, ctx, document_id)
    nom, extension = valider_fichier(bd, nom_fichier, donnees)
    _nouvelle_version(bd, ctx, p, doc, doc.version_courante + 1, nom, extension, donnees)
    bd.refresh(doc)
    return serialiser(doc)


def _obtenir(bd: SessionBD, ctx: Contexte, document_id: str) -> Document:
    doc = bd.get(Document, document_id)
    if doc is None:
        raise Introuvable("Pièce introuvable ou hors périmètre.")
    _parent_accessible(bd, ctx, doc)
    return doc


def lister(
    bd: SessionBD, ctx: Contexte, plainte_id: str | None, dossier_id: str | None, personne_id: str | None
) -> list[dict]:
    ctx.exiger(Permission.DOCUMENT_LIRE)
    meta = schemas.MetadonneesDocument(
        intitule="filtre",
        type_piece=TypePiece.AUTRE,
        plainte_id=plainte_id,
        dossier_id=dossier_id,
        personne_id=personne_id,
    )
    _parent_accessible(bd, ctx, meta)
    requete = select(Document).order_by(Document.cree_le)
    if plainte_id:
        requete = requete.where(Document.plainte_id == plainte_id)
    elif dossier_id:
        requete = requete.where(Document.dossier_id == dossier_id)
    else:
        requete = requete.where(Document.personne_id == personne_id)
    return [serialiser(d) for d in bd.execute(requete).scalars()]


def telecharger(
    bd: SessionBD, ctx: Contexte, p: ParametresServeur, document_id: str, numero_version: int | None = None
) -> tuple[str, str, bytes]:
    ctx.exiger(Permission.DOCUMENT_LIRE)
    doc = _obtenir(bd, ctx, document_id)
    numero = numero_version or doc.version_courante
    version = next((v for v in doc.versions if v.numero_version == numero), None)
    if version is None:
        raise Introuvable("Version introuvable.")
    if version.statut_analyse != StatutAnalyse.SAIN:
        audit.enregistrer_ctx(
            bd,
            ctx,
            "DOCUMENT_TELECHARGEMENT",
            resultat="REFUS",
            type_ressource="document",
            ressource_id=doc.id,
            details={"raison": f"analyse_{version.statut_analyse}"},
        )
        bd.commit()
        raise Conflit("Cette pièce n'est pas disponible : l'analyse antivirus n'a pas confirmé son innocuité.")
    chemin = p.repertoire_stockage / version.chemin_stockage
    try:
        donnees = chiffreur().dechiffrer_octets(version.cle_id, chemin.read_bytes())
    except FileNotFoundError as exc:
        raise ErreurMetier("Fichier absent du stockage sécurisé. Contactez l'administration.") from exc
    except ErreurChiffrement:
        donnees = None
    if donnees is None or hashlib.sha256(donnees).hexdigest() != version.sha256:
        audit.enregistrer_ctx(
            bd, ctx, "DOCUMENT_INTEGRITE", resultat="ECHEC", type_ressource="document", ressource_id=doc.id
        )
        bd.commit()
        raise ErreurMetier("Échec du contrôle d'intégrité de la pièce. Contactez l'administration.")
    audit.enregistrer_ctx(
        bd,
        ctx,
        "DOCUMENT_TELECHARGEMENT",
        type_ressource="document",
        ressource_id=doc.id,
        unite_id=doc.unite_id,
        details={"version": numero, "sha256": version.sha256},
    )
    return version.nom_fichier, version.type_mime, donnees


def reanalyser_en_erreur(bd: SessionBD, p: ParametresServeur) -> dict:
    """Relance l'analyse des versions dont l'analyse a echoue (antivirus indisponible)."""
    compte = {"analysees": 0, "saines": 0, "infectees": 0, "erreurs": 0}
    for version in bd.execute(
        select(VersionDocument).where(VersionDocument.statut_analyse == StatutAnalyse.ERREUR)
    ).scalars():
        chemin = p.repertoire_stockage / version.chemin_stockage
        donnees = chiffreur().dechiffrer_octets(version.cle_id, chemin.read_bytes())
        resultat = creer_analyseur(p).analyser(donnees)
        version.analyse_le = maintenant()
        version.resultat_analyse = resultat.detail[:255]
        compte["analysees"] += 1
        if resultat.erreur:
            compte["erreurs"] += 1
        elif resultat.sain:
            version.statut_analyse = StatutAnalyse.SAIN
            compte["saines"] += 1
        else:
            version.statut_analyse = StatutAnalyse.INFECTE
            chemin.unlink(missing_ok=True)
            version.chemin_stockage = ""
            compte["infectees"] += 1
    return compte
