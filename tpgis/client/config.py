"""Configuration du poste client.

Ordre de lecture : variables d'environnement TPGIS_CLIENT_*, puis fichier
client.ini dans le dossier de configuration de l'utilisateur
(%APPDATA%\\TPGIS\\client.ini sous Windows), puis client.ini installe a cote
de l'executable (configuration deployee par l'administration).
Ce fichier ne contient aucun secret.
"""

from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConfigurationClient:
    url_serveur: str = "https://tpgis.institution.td:8443"
    certificat_ca: str | None = None
    delai_secondes: float = 30.0
    autoriser_http_local: bool = False
    url_tuiles: str | None = None
    attribution_tuiles: str = ""
    theme: str = "clair"
    nom_logiciel: str | None = None
    nom_complet: str | None = None
    sous_titre: str | None = None
    logo: str | None = None


def _emplacements() -> list[Path]:
    chemins = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        chemins.append(Path(appdata) / "TPGIS" / "client.ini")
    chemins.append(Path.home() / ".config" / "tpgis" / "client.ini")
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    chemins.append(base / "client.ini")
    return chemins


def charger_configuration() -> ConfigurationClient:
    config = ConfigurationClient()
    for chemin in _emplacements():
        if chemin.exists():
            lecteur = configparser.ConfigParser()
            lecteur.read(chemin, encoding="utf-8")
            section = lecteur["serveur"] if lecteur.has_section("serveur") else {}
            config.url_serveur = section.get("url", config.url_serveur)
            config.certificat_ca = section.get("certificat_ca", config.certificat_ca) or None
            config.delai_secondes = float(section.get("delai_secondes", config.delai_secondes))
            if lecteur.has_section("carte"):
                config.url_tuiles = lecteur["carte"].get("url_tuiles") or None
                config.attribution_tuiles = lecteur["carte"].get("attribution", "")
            if lecteur.has_section("affichage"):
                config.theme = lecteur["affichage"].get("theme", config.theme).strip().lower()
            if lecteur.has_section("identite"):
                identite = lecteur["identite"]
                config.nom_logiciel = identite.get("nom") or None
                config.nom_complet = identite.get("nom_complet") or None
                config.sous_titre = identite.get("sous_titre") or None
                config.logo = identite.get("logo") or None
            break
    config.url_serveur = os.environ.get("TPGIS_CLIENT_URL", config.url_serveur)
    config.certificat_ca = os.environ.get("TPGIS_CLIENT_CA", config.certificat_ca)
    config.autoriser_http_local = os.environ.get("TPGIS_CLIENT_HTTP_LOCAL", "") == "1"
    config.url_tuiles = os.environ.get("TPGIS_CLIENT_TUILES", config.url_tuiles)
    config.theme = os.environ.get("TPGIS_CLIENT_THEME", config.theme)
    return config
