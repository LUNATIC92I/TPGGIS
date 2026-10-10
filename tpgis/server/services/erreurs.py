"""Erreurs metier converties en reponses HTTP explicites (en francais)."""

from __future__ import annotations


class ErreurMetier(Exception):
    statut_http = 400
    code = "ERREUR"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}


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
