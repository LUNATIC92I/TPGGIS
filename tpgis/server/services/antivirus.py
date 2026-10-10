"""Analyse antivirus des pieces deposees.

Production : demon ClamAV (clamd) via le protocole INSTREAM.
Developpement : analyseur de simulation qui detecte uniquement la chaine de
test normalisee EICAR. Il est refuse en production par la configuration.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

from tpgis.server.config import ParametresServeur

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@dataclass
class ResultatAnalyse:
    sain: bool
    detail: str
    erreur: bool = False


class AnalyseurSimulation:
    nom = "simulation"

    def analyser(self, donnees: bytes) -> ResultatAnalyse:
        if EICAR in donnees:
            return ResultatAnalyse(False, "Eicar-Test-Signature (simulation)")
        return ResultatAnalyse(True, "Aucune menace détectée (analyseur de simulation, non probant)")


class AnalyseurClamd:
    nom = "clamd"
    TAILLE_BLOC = 64 * 1024

    def __init__(self, hote: str, port: int, socket_unix: str | None, delai: float = 30.0):
        self.hote, self.port, self.socket_unix, self.delai = hote, port, socket_unix, delai

    def _connexion(self) -> socket.socket:
        if self.socket_unix:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self.delai)
            s.connect(self.socket_unix)
            return s
        return socket.create_connection((self.hote, self.port), timeout=self.delai)

    def analyser(self, donnees: bytes) -> ResultatAnalyse:
        try:
            with self._connexion() as s:
                s.sendall(b"zINSTREAM\0")
                for debut in range(0, len(donnees), self.TAILLE_BLOC):
                    bloc = donnees[debut : debut + self.TAILLE_BLOC]
                    s.sendall(struct.pack("!L", len(bloc)) + bloc)
                s.sendall(struct.pack("!L", 0))
                reponse = b""
                while not reponse.endswith(b"\0"):
                    morceau = s.recv(4096)
                    if not morceau:
                        break
                    reponse += morceau
        except OSError as exc:
            return ResultatAnalyse(False, f"Service antivirus indisponible : {exc.__class__.__name__}", erreur=True)
        texte = reponse.rstrip(b"\0").decode(errors="replace")
        if texte.endswith("OK"):
            return ResultatAnalyse(True, "Aucune menace détectée (ClamAV)")
        if texte.endswith("FOUND"):
            return ResultatAnalyse(False, texte.split(":", 1)[-1].replace("FOUND", "").strip())
        return ResultatAnalyse(False, f"Réponse antivirus inattendue : {texte[:120]}", erreur=True)


def creer_analyseur(p: ParametresServeur):
    if p.antivirus == "clamd":
        return AnalyseurClamd(p.clamd_hote, p.clamd_port, p.clamd_socket)
    if p.antivirus == "simulation" and not p.est_production:
        return AnalyseurSimulation()
    raise RuntimeError("Analyseur antivirus non configuré ou interdit dans cet environnement.")
