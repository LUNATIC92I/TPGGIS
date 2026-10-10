"""Sauvegardes chiffrees et restauration.

Une sauvegarde est un repertoire contenant :
1. base.enc : export de la base (pg_dump format personnalise, ou copie SQLite),
2. stockage.tar.enc : archive du stockage documentaire (deja chiffre),
3. manifeste.json : empreintes SHA 256, revision du schema, horodatage,
4. manifeste.hmac : sceau HMAC SHA 256 du manifeste (detection d'alteration).

Les fichiers sont chiffres par blocs en AES 256 GCM avec la cle de sauvegarde,
distincte des cles de donnees.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tpgis.server.config import ParametresServeur

MAGIE = b"TPGISSV1"
TAILLE_BLOC = 4 * 1024 * 1024


class ErreurSauvegarde(RuntimeError):
    pass


def _cle(p: ParametresServeur) -> bytes:
    if not p.cle_sauvegarde:
        raise ErreurSauvegarde("Cle de sauvegarde absente (TPGIS_CLE_SAUVEGARDE).")
    cle = base64.b64decode(p.cle_sauvegarde)
    if len(cle) != 32:
        raise ErreurSauvegarde("La cle de sauvegarde doit faire 32 octets.")
    return cle


def chiffrer_fichier(cle: bytes, source: Path, cible: Path) -> str:
    """Chiffre par blocs ; retourne le SHA 256 du contenu en clair."""
    aes = AESGCM(cle)
    prefixe = os.urandom(8)
    empreinte = hashlib.sha256()
    with source.open("rb") as entree, cible.open("wb") as sortie:
        sortie.write(MAGIE + prefixe)
        compteur = 0
        while True:
            bloc = entree.read(TAILLE_BLOC)
            final = len(bloc) < TAILLE_BLOC
            empreinte.update(bloc)
            nonce = prefixe + struct.pack(">I", compteur)
            donnees = aes.encrypt(nonce, bloc, b"final" if final else b"bloc")
            sortie.write(struct.pack(">I", len(donnees)) + donnees)
            compteur += 1
            if final:
                break
    return empreinte.hexdigest()


def dechiffrer_fichier(cle: bytes, source: Path, cible: Path) -> str:
    aes = AESGCM(cle)
    empreinte = hashlib.sha256()
    with source.open("rb") as entree, cible.open("wb") as sortie:
        if entree.read(8) != MAGIE:
            raise ErreurSauvegarde("Fichier de sauvegarde non reconnu.")
        prefixe = entree.read(8)
        compteur, termine = 0, False
        while not termine:
            longueur_brute = entree.read(4)
            if len(longueur_brute) < 4:
                raise ErreurSauvegarde("Sauvegarde tronquée.")
            donnees = entree.read(struct.unpack(">I", longueur_brute)[0])
            nonce = prefixe + struct.pack(">I", compteur)
            try:
                bloc = aes.decrypt(nonce, donnees, b"bloc")
            except Exception:
                try:
                    bloc = aes.decrypt(nonce, donnees, b"final")
                    termine = True
                except Exception as exc:
                    raise ErreurSauvegarde("Sauvegarde altérée ou clé incorrecte.") from exc
            empreinte.update(bloc)
            sortie.write(bloc)
            compteur += 1
        if entree.read(1):
            raise ErreurSauvegarde("Données inattendues après la fin de la sauvegarde.")
    return empreinte.hexdigest()


def _sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def _env_pg(url: str) -> tuple[list[str], dict]:
    u = urlparse(url.replace("postgresql+psycopg", "postgresql"))
    env = dict(os.environ)
    if u.password:
        env["PGPASSWORD"] = unquote(u.password)
    args = [
        "-h",
        u.hostname or "localhost",
        "-p",
        str(u.port or 5432),
        "-U",
        unquote(u.username or ""),
        "-d",
        u.path.lstrip("/"),
    ]
    return args, env


def _chemin_sqlite(url: str) -> Path:
    return Path(url.split("///", 1)[1])


def _sceller(cle: bytes, manifeste: bytes) -> str:
    return hmac.new(cle, manifeste, hashlib.sha256).hexdigest()


def sauvegarder(p: ParametresServeur, revision_schema: str | None = None) -> Path:
    cle = _cle(p)
    horodatage = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dossier = p.repertoire_sauvegardes / f"tpgis_sauvegarde_{horodatage}"
    dossier.mkdir(parents=True, exist_ok=False)
    os.chmod(dossier, 0o700)
    with tempfile.TemporaryDirectory() as tmp:
        brut = Path(tmp) / "base.bin"
        if p.est_sqlite:
            source = sqlite3.connect(_chemin_sqlite(p.database_url))
            cible = sqlite3.connect(brut)
            with cible:
                source.backup(cible)
            source.close()
            cible.close()
            format_base = "sqlite"
        else:
            args, env = _env_pg(p.database_url)
            resultat = subprocess.run(
                ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "-f", str(brut), *args],
                env=env,
                capture_output=True,
                text=True,
            )
            if resultat.returncode != 0:
                shutil.rmtree(dossier)
                raise ErreurSauvegarde(f"pg_dump a échoué : {resultat.stderr.strip()[:500]}")
            format_base = "pg_dump_custom"
        sha_base = chiffrer_fichier(cle, brut, dossier / "base.enc")

        archive = Path(tmp) / "stockage.tar"
        with tarfile.open(archive, "w") as tar:
            if p.repertoire_stockage.exists():
                tar.add(p.repertoire_stockage, arcname="stockage")
        sha_stockage = chiffrer_fichier(cle, archive, dossier / "stockage.tar.enc")

    manifeste = {
        "application": "TPGIS",
        "environnement": str(p.environnement),
        "cree_le": horodatage,
        "format_base": format_base,
        "revision_schema": revision_schema,
        "fichiers": {
            "base.enc": {"sha256_clair": sha_base, "sha256_chiffre": _sha256_fichier(dossier / "base.enc")},
            "stockage.tar.enc": {
                "sha256_clair": sha_stockage,
                "sha256_chiffre": _sha256_fichier(dossier / "stockage.tar.enc"),
            },
        },
    }
    contenu = json.dumps(manifeste, indent=2, sort_keys=True).encode()
    (dossier / "manifeste.json").write_bytes(contenu)
    (dossier / "manifeste.hmac").write_text(_sceller(cle, contenu))
    for f in dossier.iterdir():
        os.chmod(f, 0o400)
    return dossier


def verifier(p: ParametresServeur, dossier: Path) -> dict:
    cle = _cle(p)
    contenu = (dossier / "manifeste.json").read_bytes()
    sceau = (dossier / "manifeste.hmac").read_text().strip()
    if not hmac.compare_digest(sceau, _sceller(cle, contenu)):
        raise ErreurSauvegarde("Le manifeste de sauvegarde a été altéré ou la clé est incorrecte.")
    manifeste = json.loads(contenu)
    for nom, info in manifeste["fichiers"].items():
        if _sha256_fichier(dossier / nom) != info["sha256_chiffre"]:
            raise ErreurSauvegarde(f"Empreinte incorrecte pour {nom} : fichier altéré.")
    return manifeste


def restaurer(p: ParametresServeur, dossier: Path, *, confirmer_ecrasement: bool = False) -> dict:
    """Restaure la base et le stockage documentaire de l'instance configuree."""
    if not confirmer_ecrasement:
        raise ErreurSauvegarde("La restauration écrase les données actuelles : confirmation explicite requise.")
    manifeste = verifier(p, dossier)
    if manifeste["environnement"] != str(p.environnement):
        raise ErreurSauvegarde(
            f"Sauvegarde issue de l'environnement {manifeste['environnement']!r} : restauration refusée "
            f"dans l'environnement {str(p.environnement)!r} (séparation des environnements)."
        )
    cle = _cle(p)
    with tempfile.TemporaryDirectory() as tmp:
        brut = Path(tmp) / "base.bin"
        if dechiffrer_fichier(cle, dossier / "base.enc", brut) != manifeste["fichiers"]["base.enc"]["sha256_clair"]:
            raise ErreurSauvegarde("Contrôle d'intégrité de la base échoué.")
        if manifeste["format_base"] == "sqlite":
            if not p.est_sqlite:
                raise ErreurSauvegarde("Sauvegarde SQLite incompatible avec une instance PostgreSQL.")
            cible = _chemin_sqlite(p.database_url)
            for suffixe in ("-wal", "-shm"):
                Path(str(cible) + suffixe).unlink(missing_ok=True)
            shutil.copyfile(brut, cible)
        else:
            args, env = _env_pg(p.database_url)
            resultat = subprocess.run(
                [
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-privileges",
                    "--single-transaction",
                    *args,
                    str(brut),
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            if resultat.returncode != 0:
                raise ErreurSauvegarde(f"pg_restore a échoué : {resultat.stderr.strip()[:500]}")
        archive = Path(tmp) / "stockage.tar"
        sha = dechiffrer_fichier(cle, dossier / "stockage.tar.enc", archive)
        if sha != manifeste["fichiers"]["stockage.tar.enc"]["sha256_clair"]:
            raise ErreurSauvegarde("Contrôle d'intégrité du stockage échoué.")
        extraction = Path(tmp) / "extraction"
        with tarfile.open(archive) as tar:
            tar.extractall(extraction, filter="data")
        if p.repertoire_stockage.exists():
            shutil.rmtree(p.repertoire_stockage)
        source = extraction / "stockage"
        if source.exists():
            shutil.copytree(source, p.repertoire_stockage)
        else:
            p.repertoire_stockage.mkdir(parents=True, exist_ok=True)
    return manifeste
