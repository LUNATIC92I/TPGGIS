"""Erreurs metier converties en reponses HTTP explicites.

Le message est un modele francais (cle du catalogue de traduction) dont les
parties variables sont des parametres nommes : la reponse est traduite dans la
langue demandee par le client (en tete Accept-Language).
"""

from __future__ import annotations

from tpgis.shared.i18n import traduire


class ErreurMetier(Exception):
    statut_http = 400
    code = "ERREUR"

    def __init__(
        self, message: str, *, code: str | None = None, details: dict | None = None, parametres: dict | None = None
    ):
        self.modele = message
        self.parametres = parametres or {}
        self.message = message.format(**self.parametres) if self.parametres else message
        super().__init__(self.message)
        if code:
            self.code = code
        self.details = details or {}

    def message_traduit(self, langue: str | None) -> str:
        return traduire(self.modele, langue, **self.parametres)


class NonAuthentifie(ErreurMetier):
    statut_http = 401
    code = "NON_AUTHENTIFIE"


class AccesRefuse(ErreurMetier):
    statut_http = 403
    code = "ACCES_REFUSE"


class Introuvable(ErreurMetier):
    statut_http = 404
    code = "INTROUVABLE"


class Conflit(ErreurMetier):
    statut_http = 409
    code = "CONFLIT"


class DonneesInvalides(ErreurMetier):
    statut_http = 422
    code = "DONNEES_INVALIDES"


class TropDeRequetes(ErreurMetier):
    statut_http = 429
    code = "TROP_DE_REQUETES"


class ServiceIndisponible(ErreurMetier):
    statut_http = 503
    code = "SERVICE_INDISPONIBLE"


HORS_PERIMETRE = "Ressource introuvable ou hors de votre périmètre d'habilitation."
