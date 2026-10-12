"""Middlewares : identifiant de trace, en tetes de securite, limitation de debit."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from tpgis.server.services.erreurs import TropDeRequetes
from tpgis.shared.i18n import normaliser

EN_TETES_SECURITE = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


class LimiteurDebit:
    """Fenetre glissante d'une minute par cle (adresse IP, compte).

    Implementation en memoire, adaptee a une instance unique. Pour plusieurs
    instances derriere un repartiteur, utiliser un magasin partage (voir
    docs/architecture.md).
    """

    def __init__(self):
        self._evenements: dict[str, deque] = defaultdict(deque)
        self._verrou = threading.Lock()

    def verifier(self, cle: str, limite: int, fenetre: float = 60.0) -> None:
        instant = time.monotonic()
        with self._verrou:
            file = self._evenements[cle]
            while file and file[0] <= instant - fenetre:
                file.popleft()
            if len(file) >= limite:
                attente = int(fenetre - (instant - file[0])) + 1
                raise TropDeRequetes(
                    "Trop de requêtes. Réessayez dans {attente} secondes.",
                    details={"reessayer_apres": attente},
                    parametres={"attente": attente},
                )
            file.append(instant)

    def reinitialiser(self) -> None:
        with self._verrou:
            self._evenements.clear()


def installer(app) -> None:
    @app.middleware("http")
    async def _securite(request: Request, suivant):
        trace = request.headers.get("x-trace-id", "")
        try:
            trace = str(uuid.UUID(trace))
        except ValueError:
            trace = str(uuid.uuid4())
        request.state.trace_id = trace
        p = request.app.state.parametres
        ip = request.client.host if request.client else "inconnu"
        try:
            request.app.state.limiteur.verifier(f"global:{ip}", p.limite_requetes_par_minute)
        except TropDeRequetes as exc:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": exc.message_traduit(normaliser(request.headers.get("accept-language"))),
                    "code": exc.code,
                    "trace_id": trace,
                },
                headers={"Retry-After": str(exc.details["reessayer_apres"]), **EN_TETES_SECURITE},
            )
        reponse = await suivant(request)
        for cle, valeur in EN_TETES_SECURITE.items():
            reponse.headers.setdefault(cle, valeur)
        reponse.headers["X-Trace-Id"] = trace
        return reponse
