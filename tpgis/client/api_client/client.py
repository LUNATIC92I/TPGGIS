"""Client de l'API TPGIS utilise par l'application de bureau.

Le poste client ne se connecte jamais a la base de donnees : toutes les
operations passent par l'API, sur une connexion TLS verifiee. Le jeton de
session est conserve uniquement en memoire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from tpgis.shared.i18n import langue_courante, tr

MESSAGES_STATUT = {
    401: "Votre session n'est plus valide. Veuillez vous reconnecter.",
    403: "Vous ne disposez pas de l'habilitation nécessaire.",
    404: "Élément introuvable ou hors de votre périmètre.",
    429: "Trop de requêtes. Patientez quelques instants.",
    500: "Erreur interne du serveur.",
    502: "Le serveur est momentanément indisponible.",
    503: "Le service demandé est indisponible.",
}


@dataclass
class ErreurAPI(Exception):
    message: str
    statut: int = 0
    code: str = "ERREUR"
    details: dict = field(default_factory=dict)
    trace_id: str | None = None

    def __str__(self) -> str:
        texte = self.message
        champs = self.details.get("champs") if isinstance(self.details, dict) else None
        if champs:
            texte += "\n" + "\n".join(f"  {c['champ']} : {c['message']}" for c in champs)
        if self.trace_id and self.statut >= 500:
            texte += tr("\n\nIdentifiant de trace : {trace_id}", trace_id=self.trace_id)
        return texte


class ErreurReseau(ErreurAPI):
    pass


class ClientAPI:
    def __init__(
        self,
        url_serveur: str,
        *,
        certificat_ca: str | None = None,
        delai: float = 30.0,
        autoriser_http_local: bool = False,
        http: httpx.Client | None = None,
    ):
        url = url_serveur.rstrip("/")
        schema = urlparse(url).scheme
        hote = urlparse(url).hostname or ""
        if http is None and schema != "https":
            if not (autoriser_http_local and hote in ("127.0.0.1", "localhost")):
                raise ValueError(
                    tr("Connexion non chiffrée refusée : l'adresse du serveur doit commencer par https://")
                )
        self.url = url
        self.jeton: str | None = None
        self.finalite: str | None = None
        verification: Any = certificat_ca if certificat_ca else True
        self._http = http or httpx.Client(
            base_url=url, verify=verification, timeout=delai, headers={"User-Agent": "TPGIS-Client/0.1"}
        )
        self._prefixe = "/api/v1"

    # Session

    def connecter(self, identifiant: str, mot_de_passe: str, code_mfa: str | None = None) -> dict:
        resultat = self.post(
            "/auth/connexion",
            {"identifiant": identifiant, "mot_de_passe": mot_de_passe, "code_mfa": code_mfa or None},
            authentifie=False,
        )
        self.jeton = resultat["jeton"]
        return resultat

    def deconnecter(self) -> None:
        if self.jeton:
            try:
                self.post("/auth/deconnexion", {})
            except ErreurAPI:
                pass
        self.jeton = None

    def verifier_disponibilite(self) -> dict:
        return self.get("/sante", authentifie=False)

    # Requetes

    def _entetes(self, authentifie: bool, finalite: str | None) -> dict:
        # Les messages d'erreur du serveur sont rendus dans la langue de l'interface.
        entetes = {"Accept-Language": langue_courante()}
        if authentifie and self.jeton:
            entetes["Authorization"] = f"Bearer {self.jeton}"
        finalite = finalite or self.finalite
        if finalite:
            entetes["X-TPGIS-Finalite"] = quote(finalite)
        return entetes

    def _envoyer(
        self, methode: str, chemin: str, *, authentifie: bool = True, finalite: str | None = None, **kwargs
    ) -> httpx.Response:
        try:
            reponse = self._http.request(
                methode, self._prefixe + chemin, headers=self._entetes(authentifie, finalite), **kwargs
            )
        except httpx.ConnectError as exc:
            if "CERTIFICATE_VERIFY_FAILED" in str(exc) or "certificate" in str(exc).lower():
                raise ErreurReseau(
                    tr(
                        "Le certificat du serveur n'a pas pu être vérifié. La connexion a été interrompue pour "
                        "protéger vos données (risque d'interception). Contactez l'administration technique."
                    ),
                    code="CERTIFICAT_INVALIDE",
                ) from exc
            raise ErreurReseau(
                tr(
                    "Le serveur TPGIS est injoignable. Vérifiez la connexion au réseau institutionnel ou "
                    "contactez l'administration technique."
                ),
                code="SERVEUR_INJOIGNABLE",
            ) from exc
        except httpx.ProxyError as exc:
            raise ErreurReseau(
                tr(
                    "Le serveur TPGIS est injoignable à travers le proxy réseau du poste. "
                    "Vérifiez l'adresse du serveur et la configuration du proxy, "
                    "ou contactez l'administration technique."
                ),
                code="SERVEUR_INJOIGNABLE",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ErreurReseau(
                tr("Le serveur n'a pas répondu dans le délai imparti. Réessayez plus tard."), code="DELAI_DEPASSE"
            ) from exc
        except httpx.HTTPError as exc:
            raise ErreurReseau(
                tr("Erreur de communication avec le serveur ({name}).", name=exc.__class__.__name__),
                code="ERREUR_RESEAU",
            ) from exc
        if reponse.status_code >= 400:
            try:
                contenu = reponse.json()
            except ValueError:
                contenu = {}
            raise ErreurAPI(
                contenu.get("detail")
                or tr(MESSAGES_STATUT.get(reponse.status_code, "Erreur {statut}"), statut=reponse.status_code),
                statut=reponse.status_code,
                code=contenu.get("code", "ERREUR"),
                details=contenu.get("details") or {},
                trace_id=contenu.get("trace_id") or reponse.headers.get("x-trace-id"),
            )
        return reponse

    def get(self, chemin: str, params: dict | None = None, **kw) -> Any:
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        return self._envoyer("GET", chemin, params=params, **kw).json()

    def post(self, chemin: str, donnees: dict | None = None, **kw) -> Any:
        return self._envoyer("POST", chemin, json=donnees if donnees is not None else {}, **kw).json()

    def patch(self, chemin: str, donnees: dict, **kw) -> Any:
        return self._envoyer("PATCH", chemin, json=donnees, **kw).json()

    def put(self, chemin: str, donnees: dict, **kw) -> Any:
        return self._envoyer("PUT", chemin, json=donnees, **kw).json()

    def delete(self, chemin: str, params: dict | None = None, **kw) -> Any:
        return self._envoyer("DELETE", chemin, params=params, **kw).json()

    def telecharger(self, chemin: str, params: dict | None = None, **kw) -> tuple[str, bytes]:
        reponse = self._envoyer("GET", chemin, params=params, **kw)
        disposition = reponse.headers.get("content-disposition", "")
        nom = "document"
        if "filename*=UTF-8''" in disposition:
            from urllib.parse import unquote

            nom = unquote(disposition.split("filename*=UTF-8''", 1)[1])
        return nom, reponse.content

    def deposer(self, chemin: str, champs: dict, nom_fichier: str, contenu: bytes) -> Any:
        return self._envoyer(
            "POST",
            chemin,
            data={k: v for k, v in champs.items() if v is not None},
            files={"fichier": (nom_fichier, contenu, "application/octet-stream")},
        ).json()
