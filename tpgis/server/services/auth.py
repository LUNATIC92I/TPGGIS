"""Authentification, sessions, MFA et reauthentification."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.config import ParametresServeur
from tpgis.server.database.base import maintenant
from tpgis.server.database.models import Session, Utilisateur
from tpgis.server.security import mfa, passwords, tokens
from tpgis.server.services import audit
from tpgis.server.services.erreurs import AccesRefuse, DonneesInvalides, NonAuthentifie
from tpgis.shared.enums import ResultatAudit, TypeSession
from tpgis.shared.permissions import est_privilegie

MESSAGE_ECHEC = "Identifiant ou mot de passe incorrect."


def mfa_requise(utilisateur: Utilisateur) -> bool:
    return est_privilegie(utilisateur.role.codes_permissions)


def compter_echec(bd: SessionBD, p: ParametresServeur, utilisateur: Utilisateur, trace_id: str, ip: str | None) -> bool:
    """Comptabilise un echec d'authentification (mot de passe, code MFA,
    confirmation d'identite). Verrouille le compte au seuil et retourne True."""
    utilisateur.echecs_connexion += 1
    if utilisateur.echecs_connexion < p.connexion_max_echecs:
        return False
    utilisateur.verrouille_jusqua = maintenant() + timedelta(minutes=p.connexion_verrou_minutes)
    utilisateur.echecs_connexion = 0
    revoquer_sessions(bd, utilisateur.id, "verrouillage_echecs_repetes")
    audit.enregistrer(
        bd,
        action="VERROUILLAGE_COMPTE",
        trace_id=trace_id,
        utilisateur_id=utilisateur.id,
        identifiant=utilisateur.identifiant,
        adresse_ip=ip,
    )
    return True


def _ouvrir_session(
    bd: SessionBD, p: ParametresServeur, utilisateur: Utilisateur, type_session: TypeSession, ip, agent
) -> tuple[str, Session]:
    jeton = tokens.generer_jeton()
    instant = maintenant()
    duree = p.session_duree_max_minutes if type_session == TypeSession.COMPLETE else 15
    session = Session(
        utilisateur_id=utilisateur.id,
        empreinte_jeton=tokens.empreinte_jeton(jeton),
        type_session=type_session,
        creee_le=instant,
        expire_le=instant + timedelta(minutes=duree),
        derniere_activite=instant,
        reauthentifiee_le=instant,
        adresse_ip=ip,
        agent_utilisateur=(agent or "")[:255],
    )
    bd.add(session)
    bd.flush()
    return jeton, session


def connecter(
    bd: SessionBD,
    p: ParametresServeur,
    identifiant: str,
    mot_de_passe: str,
    code_mfa: str | None,
    ip: str | None,
    agent: str | None,
    trace_id: str,
) -> dict:
    """Authentifie un utilisateur. Les echecs sont audites et comptabilises.

    Retourne le jeton et le type de session (complete, enrolement MFA ou
    changement de mot de passe obligatoire).
    """
    identifiant = identifiant.strip().lower()
    utilisateur = bd.execute(select(Utilisateur).where(Utilisateur.identifiant == identifiant)).scalar_one_or_none()
    instant = maintenant()

    def refuser(raison: str, message: str = MESSAGE_ECHEC, code: str = "ECHEC_CONNEXION"):
        audit.enregistrer(
            bd,
            action="CONNEXION",
            resultat=ResultatAudit.REFUS,
            trace_id=trace_id,
            utilisateur_id=utilisateur.id if utilisateur else None,
            identifiant=identifiant[:64],
            adresse_ip=ip,
            details={"raison": raison},
        )
        bd.commit()
        raise NonAuthentifie(message, code=code)

    if utilisateur is None:
        passwords.verifier(None, mot_de_passe)  # temps de reponse homogene
        refuser("compte_inconnu")
    if utilisateur.verrouille_jusqua and utilisateur.verrouille_jusqua > instant:
        refuser(
            "compte_verrouille",
            "Compte temporairement verrouillé suite à plusieurs échecs. Réessayez plus tard "
            "ou contactez l'administration.",
            "COMPTE_VERROUILLE",
        )
    if not passwords.verifier(utilisateur.mot_de_passe_hash, mot_de_passe):
        compter_echec(bd, p, utilisateur, trace_id, ip)
        refuser("mot_de_passe_incorrect")
    if not utilisateur.actif:
        refuser("compte_desactive", "Ce compte est désactivé. Contactez l'administration.", "COMPTE_DESACTIVE")
    if not utilisateur.role.actif:
        refuser("role_inactif", "Le rôle associé à ce compte est désactivé.", "ROLE_INACTIF")

    if utilisateur.mfa_active:
        if not code_mfa:
            raise NonAuthentifie("Code de vérification à usage unique requis.", code="MFA_REQUISE")
        pas = mfa.verifier_code(utilisateur.mfa_secret or "", code_mfa, utilisateur.mfa_dernier_pas)
        if pas is None:
            compter_echec(bd, p, utilisateur, trace_id, ip)
            refuser("code_mfa_invalide", "Code de vérification invalide.", "MFA_INVALIDE")
        utilisateur.mfa_dernier_pas = pas

    if passwords.doit_etre_rehache(utilisateur.mot_de_passe_hash):
        utilisateur.mot_de_passe_hash = passwords.hacher(mot_de_passe)

    utilisateur.echecs_connexion = 0
    utilisateur.verrouille_jusqua = None
    utilisateur.derniere_connexion = instant

    expire_mdp = (
        utilisateur.mot_de_passe_modifie_le is not None
        and utilisateur.mot_de_passe_modifie_le + timedelta(days=p.mot_de_passe_validite_jours) < instant
    )
    if utilisateur.doit_changer_mot_de_passe or expire_mdp:
        type_session = TypeSession.CHANGEMENT_MOT_DE_PASSE
    elif mfa_requise(utilisateur) and not utilisateur.mfa_active:
        type_session = TypeSession.ENROLEMENT_MFA
    else:
        type_session = TypeSession.COMPLETE

    jeton, session = _ouvrir_session(bd, p, utilisateur, type_session, ip, agent)
    audit.enregistrer(
        bd,
        action="CONNEXION",
        trace_id=trace_id,
        utilisateur_id=utilisateur.id,
        identifiant=identifiant,
        unite_id=utilisateur.unite_id,
        adresse_ip=ip,
        details={"type_session": str(type_session), "session_id": session.id},
    )
    return {"jeton": jeton, "type_session": str(type_session), "expire_le": session.expire_le}


def valider_jeton(bd: SessionBD, p: ParametresServeur, jeton: str) -> Session:
    if not jeton:
        raise NonAuthentifie("Authentification requise.")
    session = bd.execute(
        select(Session).where(Session.empreinte_jeton == tokens.empreinte_jeton(jeton))
    ).scalar_one_or_none()
    instant = maintenant()
    if session is None or session.revoquee_le is not None:
        raise NonAuthentifie("Session invalide ou révoquée. Veuillez vous reconnecter.", code="SESSION_INVALIDE")
    if session.expire_le <= instant:
        raise NonAuthentifie("Session expirée. Veuillez vous reconnecter.", code="SESSION_EXPIREE")
    if session.derniere_activite + timedelta(minutes=p.session_inactivite_minutes) <= instant:
        session.revoquee_le = instant
        session.motif_revocation = "inactivite"
        bd.commit()
        raise NonAuthentifie("Session fermée pour inactivité. Veuillez vous reconnecter.", code="SESSION_INACTIVE")
    utilisateur = session.utilisateur
    if not utilisateur.actif:
        raise NonAuthentifie("Compte désactivé.", code="COMPTE_DESACTIVE")
    session.derniere_activite = instant
    return session


def revoquer_sessions(bd: SessionBD, utilisateur_id: str, motif: str, sauf_session_id: str | None = None) -> int:
    requete = (
        update(Session)
        .where(Session.utilisateur_id == utilisateur_id, Session.revoquee_le.is_(None))
        .values(revoquee_le=maintenant(), motif_revocation=motif[:200])
    )
    if sauf_session_id:
        requete = requete.where(Session.id != sauf_session_id)
    return bd.execute(requete).rowcount or 0


def deconnecter(bd: SessionBD, session: Session) -> None:
    session.revoquee_le = maintenant()
    session.motif_revocation = "deconnexion"


def changer_mot_de_passe(bd: SessionBD, p: ParametresServeur, ctx, ancien: str, nouveau: str) -> dict:
    utilisateur: Utilisateur = ctx.utilisateur
    if not passwords.verifier(utilisateur.mot_de_passe_hash, ancien):
        audit.enregistrer_ctx(bd, ctx, "CHANGEMENT_MOT_DE_PASSE", resultat=ResultatAudit.REFUS)
        verrouille = compter_echec(bd, p, utilisateur, ctx.trace_id, ctx.adresse_ip)
        bd.commit()
        if verrouille:
            raise NonAuthentifie("Compte verrouillé suite à plusieurs échecs.", code="COMPTE_VERROUILLE")
        raise AccesRefuse("Mot de passe actuel incorrect.")
    erreurs = passwords.controler_politique(nouveau, p.mot_de_passe_longueur_min, utilisateur.identifiant)
    if ancien == nouveau:
        erreurs.append("Le nouveau mot de passe doit être différent de l'ancien.")
    if erreurs:
        raise DonneesInvalides(" ".join(erreurs), details={"regles": erreurs})
    utilisateur.mot_de_passe_hash = passwords.hacher(nouveau)
    utilisateur.doit_changer_mot_de_passe = False
    utilisateur.mot_de_passe_modifie_le = maintenant()
    revoquer_sessions(bd, utilisateur.id, "changement_mot_de_passe")
    audit.enregistrer_ctx(bd, ctx, "CHANGEMENT_MOT_DE_PASSE")
    return {"message": "Mot de passe modifié. Veuillez vous reconnecter."}


def preparer_mfa(bd: SessionBD, ctx) -> dict:
    utilisateur: Utilisateur = ctx.utilisateur
    if utilisateur.mfa_active:
        raise DonneesInvalides("L'authentification multifacteur est déjà activée pour ce compte.")
    secret = mfa.generer_secret()
    utilisateur.mfa_secret = secret
    audit.enregistrer_ctx(bd, ctx, "MFA_PREPARATION")
    return {"secret": secret, "uri": mfa.uri_provisionnement(secret, utilisateur.identifiant)}


def activer_mfa(bd: SessionBD, ctx, code: str) -> dict:
    utilisateur: Utilisateur = ctx.utilisateur
    if not utilisateur.mfa_secret or utilisateur.mfa_active:
        raise DonneesInvalides("Aucune activation MFA en attente.")
    pas = mfa.verifier_code(utilisateur.mfa_secret, code)
    if pas is None:
        audit.enregistrer_ctx(bd, ctx, "MFA_ACTIVATION", resultat=ResultatAudit.REFUS)
        bd.commit()
        raise DonneesInvalides("Code de vérification invalide.")
    utilisateur.mfa_active = True
    utilisateur.mfa_dernier_pas = pas
    revoquer_sessions(bd, utilisateur.id, "activation_mfa")
    audit.enregistrer_ctx(bd, ctx, "MFA_ACTIVATION")
    return {"message": "Authentification multifacteur activée. Veuillez vous reconnecter."}


def reauthentifier(bd: SessionBD, p: ParametresServeur, ctx, mot_de_passe: str, code_mfa: str | None) -> dict:
    """Confirmation d'identite exigee avant les operations critiques."""
    utilisateur: Utilisateur = ctx.utilisateur
    ok = passwords.verifier(utilisateur.mot_de_passe_hash, mot_de_passe)
    if ok and utilisateur.mfa_active:
        pas = mfa.verifier_code(utilisateur.mfa_secret or "", code_mfa or "", utilisateur.mfa_dernier_pas)
        ok = pas is not None
        if ok:
            utilisateur.mfa_dernier_pas = pas
    if not ok:
        audit.enregistrer_ctx(bd, ctx, "REAUTHENTIFICATION", resultat=ResultatAudit.REFUS)
        verrouille = compter_echec(bd, p, utilisateur, ctx.trace_id, ctx.adresse_ip)
        bd.commit()
        if verrouille:
            raise NonAuthentifie(
                "Compte verrouillé suite à plusieurs échecs : session fermée.", code="COMPTE_VERROUILLE"
            )
        raise AccesRefuse("Confirmation d'identité refusée.", code="REAUTHENTIFICATION_REFUSEE")
    utilisateur.echecs_connexion = 0
    ctx.session.reauthentifiee_le = maintenant()
    audit.enregistrer_ctx(bd, ctx, "REAUTHENTIFICATION")
    return {"message": "Identité confirmée."}


def exiger_reauthentification_recente(ctx, p: ParametresServeur) -> None:
    session = ctx.session
    limite = maintenant() - timedelta(minutes=p.reauthentification_validite_minutes)
    if session is None or session.reauthentifiee_le is None or session.reauthentifiee_le < limite:
        raise AccesRefuse(
            "Cette opération sensible nécessite une confirmation récente de votre identité.",
            code="REAUTHENTIFICATION_REQUISE",
        )
