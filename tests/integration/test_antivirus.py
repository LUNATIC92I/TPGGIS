"""Analyse antivirus : protocole clamd (INSTREAM), indisponibilite et demon reel.

Le test contre un demon ClamAV reel s'execute si TPGIS_TEST_CLAMD_SOCKET
designe la socket d'un clamd en fonctionnement.
"""

from __future__ import annotations

import os
import socket
import struct
import threading

import pytest

from tpgis.server.services.antivirus import EICAR, AnalyseurClamd

API = "/api/v1"


def _faux_clamd(reponse: bytes):
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)
    recu = {}

    def _servir():
        conn, _ = serveur.accept()
        with conn:
            commande = conn.recv(10)
            donnees = b""
            while True:
                taille = struct.unpack("!L", conn.recv(4))[0]
                if taille == 0:
                    break
                bloc = b""
                while len(bloc) < taille:
                    bloc += conn.recv(taille - len(bloc))
                donnees += bloc
            recu.update(commande=commande, donnees=donnees)
            conn.sendall(reponse)
        serveur.close()

    threading.Thread(target=_servir, daemon=True).start()
    return serveur.getsockname()[1], recu


def test_protocole_instream_fichier_sain():
    port, recu = _faux_clamd(b"stream: OK\0")
    r = AnalyseurClamd("127.0.0.1", port, None).analyser(b"x" * 200_000)
    assert r.sain and not r.erreur
    assert recu["commande"] == b"zINSTREAM\0" and len(recu["donnees"]) == 200_000


def test_protocole_instream_menace():
    port, _ = _faux_clamd(b"stream: Win.Test.Exemple FOUND\0")
    r = AnalyseurClamd("127.0.0.1", port, None).analyser(b"contenu")
    assert not r.sain and not r.erreur and r.detail == "Win.Test.Exemple"


def test_antivirus_indisponible_piece_bloquee(client, connexions, parametres):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port_ferme = s.getsockname()[1]
    parametres.antivirus, parametres.clamd_port = "clamd", port_ferme
    h = connexions.entetes("officier.ndj")
    plainte = client.get(f"{API}/plaintes", headers=h, params={"taille": 1}).json()["elements"][0]
    r = client.post(
        f"{API}/documents",
        headers=h,
        data={"intitule": "Pièce", "type_piece": "AUTRE", "plainte_id": plainte["id"]},
        files={"fichier": ("a.txt", b"contenu", "text/plain")},
    )
    assert r.status_code == 201
    assert r.json()["versions"][0]["statut_analyse"] == "ERREUR" and not r.json()["disponible"]
    assert client.get(f"{API}/documents/{r.json()['id']}/contenu", headers=h).status_code == 409


@pytest.mark.skipif(not os.environ.get("TPGIS_TEST_CLAMD_SOCKET"), reason="démon clamd non disponible")
def test_demon_clamd_reel():
    analyseur = AnalyseurClamd("", 0, os.environ["TPGIS_TEST_CLAMD_SOCKET"])
    assert analyseur.analyser(b"%PDF-1.4 document ordinaire").sain
    r = analyseur.analyser(EICAR)
    assert not r.sain and not r.erreur and "Eicar" in r.detail
