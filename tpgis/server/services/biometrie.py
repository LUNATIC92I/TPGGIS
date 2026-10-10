"""Module d'integration biometrique.

Cette version ne fournit QU'UN ADAPTATEUR SIMULE fonctionnant sur des donnees
synthetiques. Aucune capacite reelle de reconnaissance n'est revendiquee.
L'integration operationnelle devra utiliser le SDK officiel et documente du
fournisseur retenu, apres validation juridique, technique et operationnelle,
en implementant l'interface AdaptateurBiometrique.

Garanties appliquees :
1. seules des verifications 1 pour 1 (une capture enregistree contre une
   nouvelle capture de la meme personne) sont possibles ;
2. aucune recherche 1 contre N, aucune identification automatisee ;
3. les modeles biometriques ne transitent jamais par l'API, les journaux ou
   les exports : seule une reference opaque chiffree est stockee ;
4. chaque consultation est tracee avec sa finalite.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.config import ParametresServeur
from tpgis.server.database.base import maintenant
from tpgis.server.database.models import CaptureBiometrique
from tpgis.server.services import audit
from tpgis.server.services.commun import lire_parametre
from tpgis.server.services.contexte import Contexte
from tpgis.server.services.erreurs import Conflit, DonneesInvalides, Introuvable, ServiceIndisponible
from tpgis.shared import schemas
from tpgis.shared.enums import ModaliteBiometrique, StatutCapture, TypeValidation
from tpgis.shared.permissions import Permission


@dataclass
class ResultatEnrolement:
    reference: str  # reference opaque vers le stockage du systeme biometrique
    qualite: int


@dataclass
class ResultatVerification:
    concordance: bool
    score: int
    commentaire: str


class AdaptateurBiometrique(ABC):
    nom: str
    synthetique: bool

    @abstractmethod
    def capturer_et_enroler(self, equipement: str, position_doigt: str) -> ResultatEnrolement: ...

    @abstractmethod
    def verifier(self, reference: str, equipement: str) -> ResultatVerification: ...

    @abstractmethod
    def supprimer(self, reference: str) -> None: ...


class AdaptateurSimule(AdaptateurBiometrique):
    """Adaptateur de simulation : genere des modeles SYNTHETIQUES aleatoires.

    Les modeles sont conserves en memoire du processus uniquement, et ne
    representent aucune empreinte reelle. La verification simulee est
    deterministe a partir de la reference (resultat de demonstration).
    """

    nom = "simulation"
    synthetique = True

    def __init__(self):
        self._magasin: dict[str, bytes] = {}
        self._sel = os.urandom(16)

    def capturer_et_enroler(self, equipement: str, position_doigt: str) -> ResultatEnrolement:
        reference = f"SIM-{secrets.token_hex(12)}"
        self._magasin[reference] = os.urandom(256)  # modele synthetique, jamais expose
        qualite = 60 + secrets.randbelow(40)
        return ResultatEnrolement(reference=reference, qualite=qualite)

    def verifier(self, reference: str, equipement: str) -> ResultatVerification:
        if not reference.startswith("SIM-"):
            return ResultatVerification(False, 0, "Référence non issue de l'adaptateur simulé.")
        empreinte = hmac.new(self._sel, reference.encode(), hashlib.sha256).digest()
        score = 70 + empreinte[0] % 30
        return ResultatVerification(True, score, "Résultat SIMULÉ sur données synthétiques, sans valeur probante.")

    def supprimer(self, reference: str) -> None:
        self._magasin.pop(reference, None)


_ADAPTATEUR: AdaptateurBiometrique | None = None


def adaptateur(p: ParametresServeur) -> AdaptateurBiometrique:
    global _ADAPTATEUR
    if p.biometrie_adaptateur in ("", "aucun"):
        raise ServiceIndisponible("Le module biométrique n'est pas activé sur cette instance.")
    if p.biometrie_adaptateur == "simulation":
        if p.est_production:
            raise ServiceIndisponible("L'adaptateur simulé est interdit en production.")
        if _ADAPTATEUR is None:
            _ADAPTATEUR = AdaptateurSimule()
        return _ADAPTATEUR
    raise ServiceIndisponible(
        f"Adaptateur biométrique {p.biometrie_adaptateur!r} non disponible : intégration institutionnelle à valider."
    )


def _ajouter_annees(d: date, annees: int) -> date:
    try:
        return d.replace(year=d.year + annees)
    except ValueError:  # 29 fevrier
        return d.replace(year=d.year + annees, day=28)


def serialiser(c: CaptureBiometrique) -> dict:
    # La reference du modele n'est jamais restituee.
    return {
        "id": c.id,
        "personne_id": c.personne_id,
        "modalite": c.modalite,
        "position_doigt": c.position_doigt,
        "adaptateur": c.adaptateur,
        "equipement": c.equipement,
        "collectee_le": c.collectee_le,
        "fondement_legal": c.fondement_legal,
        "consentement_recueilli": c.consentement_recueilli,
        "agent_id": c.agent_id,
        "qualite": c.qualite,
        "conserver_jusqua": c.conserver_jusqua,
        "statut": c.statut,
        "est_synthetique": c.est_synthetique,
    }


def _exiger_finalite(ctx: Contexte) -> None:
    if not ctx.finalite:
        raise DonneesInvalides("La finalité de l'opération biométrique doit être déclarée.", code="FINALITE_REQUISE")


def enregistrer(bd: SessionBD, ctx: Contexte, p: ParametresServeur, donnees: schemas.CaptureCreation) -> dict:
    from tpgis.server.services.personnes import obtenir as obtenir_personne

    ctx.exiger(Permission.BIOMETRIE_ENREGISTRER)
    _exiger_finalite(ctx)
    personne = obtenir_personne(bd, ctx, donnees.personne_id)
    a = adaptateur(p)
    resultat = a.capturer_et_enroler(donnees.equipement, donnees.position_doigt)
    annees = donnees.conserver_annees or int(lire_parametre(bd, "retention.biometrie_annees"))
    aujourd_hui = date.today()
    capture = CaptureBiometrique(
        personne_id=personne.id,
        modalite=ModaliteBiometrique.EMPREINTE_DIGITALE,
        position_doigt=donnees.position_doigt,
        adaptateur=a.nom,
        equipement=donnees.equipement,
        collectee_le=maintenant(),
        fondement_legal=donnees.fondement_legal,
        consentement_recueilli=donnees.consentement_recueilli,
        agent_id=ctx.uid,
        unite_id=ctx.utilisateur.unite_id,
        reference_modele=resultat.reference,
        qualite=resultat.qualite,
        conserver_jusqua=_ajouter_annees(aujourd_hui, annees),
        statut=StatutCapture.ACTIVE,
        est_synthetique=a.synthetique,
    )
    bd.add(capture)
    bd.flush()
    audit.enregistrer_ctx(
        bd,
        ctx,
        "BIOMETRIE_ENREGISTREMENT",
        type_ressource="capture_biometrique",
        ressource_id=capture.id,
        details={"personne_id": personne.id, "adaptateur": a.nom, "doigt": donnees.position_doigt},
    )
    return serialiser(capture)


def lister(bd: SessionBD, ctx: Contexte, personne_id: str) -> list[dict]:
    from tpgis.server.services.personnes import obtenir as obtenir_personne

    ctx.exiger(Permission.BIOMETRIE_LIRE)
    _exiger_finalite(ctx)
    personne = obtenir_personne(bd, ctx, personne_id)
    captures = (
        bd.execute(
            select(CaptureBiometrique)
            .where(CaptureBiometrique.personne_id == personne.id)
            .order_by(CaptureBiometrique.collectee_le)
        )
        .scalars()
        .all()
    )
    audit.enregistrer_ctx(
        bd,
        ctx,
        "BIOMETRIE_CONSULTATION",
        type_ressource="personne",
        ressource_id=personne.id,
        details={"captures": len(captures)},
    )
    return [serialiser(c) for c in captures]


def _capture_accessible(bd: SessionBD, ctx: Contexte, capture_id: str) -> CaptureBiometrique:
    from tpgis.server.services.personnes import obtenir as obtenir_personne

    c = bd.get(CaptureBiometrique, capture_id)
    if c is None:
        raise Introuvable("Capture introuvable.")
    obtenir_personne(bd, ctx, c.personne_id)
    return c


def verifier(bd: SessionBD, ctx: Contexte, p: ParametresServeur, donnees: schemas.VerificationBiometrique) -> dict:
    """Verification 1 pour 1 uniquement."""
    ctx.exiger(Permission.BIOMETRIE_VERIFIER)
    _exiger_finalite(ctx)
    c = _capture_accessible(bd, ctx, donnees.capture_id)
    if c.statut != StatutCapture.ACTIVE:
        raise Conflit("Cette capture a été supprimée.")
    a = adaptateur(p)
    if c.adaptateur != a.nom:
        raise Conflit("Capture enregistrée avec un autre système biométrique.")
    r = a.verifier(c.reference_modele, donnees.equipement)
    ev = audit.enregistrer_ctx(
        bd,
        ctx,
        "BIOMETRIE_VERIFICATION",
        type_ressource="capture_biometrique",
        ressource_id=c.id,
        details={"concordance": r.concordance, "score": r.score},
    )
    return {
        "concordance": r.concordance,
        "score": r.score,
        "commentaire": r.commentaire,
        "synthetique": a.synthetique,
        "trace_audit": ev.trace_id,
    }


def recherche_un_contre_n(p: ParametresServeur) -> None:
    """Point d'entree volontairement desactive."""
    if not p.biometrie_recherche_active:
        raise ServiceIndisponible(
            "La recherche biométrique est désactivée : elle ne pourra être activée qu'après intégration d'un "
            "système approuvé et validation juridique et technique."
        )
    raise ServiceIndisponible("Aucun système biométrique approuvé n'est intégré.")


def demander_suppression(bd: SessionBD, ctx: Contexte, capture_id: str, motif: str) -> dict:
    from tpgis.server.services.validations import creer_demande

    ctx.exiger(Permission.BIOMETRIE_SUPPRIMER)
    c = _capture_accessible(bd, ctx, capture_id)
    if c.statut != StatutCapture.ACTIVE:
        raise Conflit("Capture déjà supprimée.")
    return creer_demande(
        bd,
        ctx,
        TypeValidation.SUPPRESSION_CAPTURE_BIOMETRIQUE,
        {"capture_id": c.id},
        f"Suppression de la capture biométrique {c.id[:8]}",
        motif,
    )


def executer_suppression(
    bd: SessionBD, ctx: Contexte, capture_id: str, motif: str, p: ParametresServeur | None = None
) -> str:
    from tpgis.server.config import obtenir_parametres

    c = bd.get(CaptureBiometrique, capture_id)
    if c is None or c.statut != StatutCapture.ACTIVE:
        raise Conflit("Capture introuvable ou déjà supprimée.")
    try:
        adaptateur(p or obtenir_parametres()).supprimer(c.reference_modele)
    except ServiceIndisponible:
        pass
    c.reference_modele = "SUPPRIMEE"
    c.statut = StatutCapture.SUPPRIMEE
    c.supprimee_le = maintenant()
    c.motif_suppression = motif
    audit.enregistrer_ctx(
        bd,
        ctx,
        "BIOMETRIE_SUPPRESSION",
        type_ressource="capture_biometrique",
        ressource_id=c.id,
        details={"motif": motif},
    )
    return "Capture biométrique supprimée."
