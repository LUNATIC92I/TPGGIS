"""Configuration du serveur TPGIS.

Toute la configuration provient de variables d'environnement prefixees par
TPGIS_ ou d'un fichier .env place hors du depot. Aucun secret n'est code en dur.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tpgis.shared.enums import Environnement


class ParametresServeur(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TPGIS_",
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    environnement: Environnement = Environnement.DEVELOPPEMENT
    nom_instance: str = "TPGIS"

    database_url: str = "sqlite:///./var/tpgis_dev.sqlite3"
    database_echo: bool = False

    # Cles de chiffrement des donnees au repos, format "id:base64,id:base64".
    cles_donnees: str = Field(default="", repr=False)
    cle_donnees_active: str = "k1"
    # Cle HMAC pour les index aveugles (recherche exacte sur champs chiffres).
    cle_index: str = Field(default="", repr=False)
    # Cle de chiffrement des sauvegardes (base64, 32 octets).
    cle_sauvegarde: str = Field(default="", repr=False)

    repertoire_stockage: Path = Path("./var/stockage")
    repertoire_sauvegardes: Path = Path("./var/sauvegardes")

    # Sessions
    session_duree_max_minutes: int = 480
    session_inactivite_minutes: int = 30
    reauthentification_validite_minutes: int = 5

    # Protection contre la force brute
    connexion_max_echecs: int = 5
    connexion_verrou_minutes: int = 15
    limite_connexion_par_minute_ip: int = 10
    limite_requetes_par_minute: int = 300

    # Politique de mot de passe
    mot_de_passe_longueur_min: int = 12
    mot_de_passe_validite_jours: int = 180

    # Antivirus : "clamd" en production, "simulation" en developpement.
    antivirus: str = "simulation"
    clamd_hote: str = "127.0.0.1"
    clamd_port: int = 3310
    clamd_socket: str | None = None

    # Biometrie : seul l'adaptateur "simulation" est fourni dans cette version.
    biometrie_adaptateur: str = "simulation"
    biometrie_recherche_active: bool = False

    # TLS
    tls_certificat: Path | None = None
    tls_cle: Path | None = None
    tls_termine_par_proxy: bool = False
    hote: str = "127.0.0.1"
    port: int = 8443

    @field_validator("database_url")
    @classmethod
    def _url_non_vide(cls, v: str) -> str:
        if not v:
            raise ValueError("TPGIS_DATABASE_URL est obligatoire")
        return v

    @property
    def est_production(self) -> bool:
        return self.environnement == Environnement.PRODUCTION

    @property
    def est_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


class ErreurConfiguration(RuntimeError):
    pass


def verifier_configuration_production(p: ParametresServeur) -> list[str]:
    """Retourne la liste des non conformites bloquantes pour la production."""
    erreurs: list[str] = []
    if not p.est_production:
        return erreurs
    if p.est_sqlite:
        erreurs.append("SQLite est interdit en production : utiliser PostgreSQL.")
    if not p.cles_donnees or not p.cle_index or not p.cle_sauvegarde:
        erreurs.append("Les cles de chiffrement doivent etre fournies par le coffre de secrets.")
    if p.antivirus != "clamd":
        erreurs.append("L'analyse antivirus reelle (clamd) est obligatoire en production.")
    if p.biometrie_adaptateur == "simulation":
        erreurs.append(
            "L'adaptateur biometrique simule est interdit en production. "
            "Configurer un adaptateur institutionnel valide ou desactiver le module (aucun)."
        )
    if not p.tls_termine_par_proxy and not (p.tls_certificat and p.tls_cle):
        erreurs.append("TLS obligatoire : fournir certificat et cle ou un proxy TLS.")
    return erreurs


@lru_cache
def obtenir_parametres() -> ParametresServeur:
    return ParametresServeur()
