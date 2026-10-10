"""Sessions, revocation, force brute, MFA et reauthentification."""

from __future__ import annotations

from datetime import timedelta

import pyotp

from tpgis.server.database.base import maintenant
from tpgis.server.database.models import Session, Utilisateur
from tpgis.server.database.seed.demonstration import MOT_DE_PASSE_DEMO, SECRETS_TOTP_DEMO

API = "/api/v1"


def test_connexion_et_deconnexion(client, connexions):
    h = connexions.entetes("accueil.ndj")
    assert client.get(f"{API}/auth/moi", headers=h).json()["identifiant"] == "accueil.ndj"
    assert client.post(f"{API}/auth/deconnexion", headers=h).status_code == 200
    assert client.get(f"{API}/auth/moi", headers=h).status_code == 401


def test_desactivation_revoque_immediatement(client, connexions):
    h_cible = connexions.entetes("accueil.abc")
    assert client.get(f"{API}/plaintes", headers=h_cible).status_code == 200
    h_admin = connexions.entetes("admin.fonctionnel")
    cible = client.get(f"{API}/utilisateurs", headers=h_admin, params={"texte": "accueil.abc"}).json()["elements"][0]
    r = client.post(f"{API}/utilisateurs/{cible['id']}/desactivation", headers=h_admin,
                    json={"motif": "Départ de l'agent (test)"})
    assert r.status_code == 200 and r.json()["actif"] is False
    assert client.get(f"{API}/plaintes", headers=h_cible).status_code == 401
    r = client.post(f"{API}/auth/connexion", json={"identifiant": "accueil.abc", "mot_de_passe": MOT_DE_PASSE_DEMO})
    assert r.status_code == 401 and r.json()["code"] == "COMPTE_DESACTIVE"


def test_revocation_administrative_des_sessions(client, connexions):
    h_cible = connexions.entetes("accueil.ndj")
    h_admin = connexions.entetes("admin.fonctionnel")
    cible = client.get(f"{API}/utilisateurs", headers=h_admin, params={"texte": "accueil.ndj"}).json()["elements"][0]
    r = client.post(f"{API}/utilisateurs/{cible['id']}/revocation-sessions", headers=h_admin)
    assert r.json()["sessions_revoquees"] >= 1
    assert client.get(f"{API}/plaintes", headers=h_cible).status_code == 401


def test_expiration_et_inactivite(client, connexions, app):
    h = connexions.entetes("accueil.ndj")
    with app.state.fabrique.transaction() as bd:
        s = bd.query(Session).filter(Session.revoquee_le.is_(None)).order_by(Session.creee_le.desc()).first()
        s.derniere_activite = maintenant() - timedelta(hours=2)
    r = client.get(f"{API}/plaintes", headers=h)
    assert r.status_code == 401 and r.json()["code"] == "SESSION_INACTIVE"
    h = connexions.entetes("accueil.ndj")
    with app.state.fabrique.transaction() as bd:
        s = bd.query(Session).filter(Session.revoquee_le.is_(None)).order_by(Session.creee_le.desc()).first()
        s.expire_le = maintenant() - timedelta(seconds=1)
    r = client.get(f"{API}/plaintes", headers=h)
    assert r.status_code == 401 and r.json()["code"] == "SESSION_EXPIREE"


def test_jeton_stocke_sous_forme_d_empreinte(client, connexions, app):
    h = connexions.entetes("accueil.ndj")
    jeton = h["Authorization"].split()[1]
    with app.state.fabrique.transaction() as bd:
        empreintes = [s.empreinte_jeton for s in bd.query(Session).all()]
    assert jeton not in empreintes


def test_verrouillage_apres_echecs_repetes(client, donnees, parametres):
    for _ in range(parametres.connexion_max_echecs):
        r = client.post(f"{API}/auth/connexion", json={"identifiant": "accueil.ndj", "mot_de_passe": "mauvais"})
        assert r.status_code == 401
    r = client.post(f"{API}/auth/connexion", json={"identifiant": "accueil.ndj", "mot_de_passe": MOT_DE_PASSE_DEMO})
    assert r.status_code == 401 and r.json()["code"] == "COMPTE_VERROUILLE"


def test_message_identique_compte_inconnu(client, donnees):
    a = client.post(f"{API}/auth/connexion", json={"identifiant": "inexistant", "mot_de_passe": "x"}).json()
    b = client.post(f"{API}/auth/connexion", json={"identifiant": "accueil.ndj", "mot_de_passe": "x"}).json()
    assert a["detail"] == b["detail"]


def test_limitation_debit_connexion(app, client, donnees, parametres):
    parametres.limite_connexion_par_minute_ip = 3
    codes = [client.post(f"{API}/auth/connexion", json={"identifiant": "xyz", "mot_de_passe": "y"}).status_code
             for _ in range(5)]
    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429


def test_mfa_obligatoire_pour_compte_privilegie(client, donnees):
    r = client.post(f"{API}/auth/connexion", json={"identifiant": "officier.ndj", "mot_de_passe": MOT_DE_PASSE_DEMO})
    assert r.status_code == 401 and r.json()["code"] == "MFA_REQUISE"
    r = client.post(f"{API}/auth/connexion", json={"identifiant": "officier.ndj", "mot_de_passe": MOT_DE_PASSE_DEMO,
                                                   "code_mfa": "000000"})
    assert r.status_code == 401


def test_rejeu_code_mfa_refuse(client, connexions):
    code = connexions.code("officier.abc")
    corps = {"identifiant": "officier.abc", "mot_de_passe": MOT_DE_PASSE_DEMO, "code_mfa": code}
    assert client.post(f"{API}/auth/connexion", json=corps).status_code == 200
    assert client.post(f"{API}/auth/connexion", json=corps).status_code == 401


def test_enrolement_mfa_exige_pour_nouveau_compte_privilegie(client, connexions, app):
    # Retire la MFA d'un compte privilegie : la session obtenue ne permet que l'enrolement.
    with app.state.fabrique.transaction() as bd:
        u = bd.query(Utilisateur).filter_by(identifiant="officier.abc").one()
        u.mfa_active, u.mfa_secret = False, None
    r = client.post(f"{API}/auth/connexion", json={"identifiant": "officier.abc", "mot_de_passe": MOT_DE_PASSE_DEMO})
    assert r.json()["type_session"] == "ENROLEMENT_MFA"
    h = {"Authorization": f"Bearer {r.json()['jeton']}"}
    assert client.get(f"{API}/plaintes", headers=h).json()["code"] == "ENROLEMENT_MFA_REQUIS"
    secret = client.post(f"{API}/auth/mfa/preparation", headers=h).json()["secret"]
    r = client.post(f"{API}/auth/mfa/activation", headers=h, json={"code_mfa": pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    # Toutes les sessions sont revoquees apres activation.
    assert client.get(f"{API}/auth/moi", headers=h).status_code == 401


def test_changement_mot_de_passe_obligatoire(client, connexions, app):
    with app.state.fabrique.transaction() as bd:
        bd.query(Utilisateur).filter_by(identifiant="accueil.ndj").one().doit_changer_mot_de_passe = True
    r = client.post(f"{API}/auth/connexion", json={"identifiant": "accueil.ndj", "mot_de_passe": MOT_DE_PASSE_DEMO})
    h = {"Authorization": f"Bearer {r.json()['jeton']}"}
    assert r.json()["type_session"] == "CHANGEMENT_MOT_DE_PASSE"
    assert client.get(f"{API}/plaintes", headers=h).status_code == 403
    r = client.post(f"{API}/auth/mot-de-passe", headers=h,
                    json={"ancien_mot_de_passe": MOT_DE_PASSE_DEMO, "nouveau_mot_de_passe": "court"})
    assert r.status_code == 422
    r = client.post(f"{API}/auth/mot-de-passe", headers=h,
                    json={"ancien_mot_de_passe": MOT_DE_PASSE_DEMO, "nouveau_mot_de_passe": "Nouveau-Mot2Passe!Sur"})
    assert r.status_code == 200
    r = client.post(f"{API}/auth/connexion", json={"identifiant": "accueil.ndj",
                                                   "mot_de_passe": "Nouveau-Mot2Passe!Sur"})
    assert r.json()["type_session"] == "COMPLETE"


def test_operation_critique_exige_reauthentification(client, connexions, app):
    h = connexions.entetes("admin.fonctionnel")
    with app.state.fabrique.transaction() as bd:
        for s in bd.query(Session).all():
            s.reauthentifiee_le = maintenant() - timedelta(hours=1)
    cible = client.get(f"{API}/utilisateurs", headers=h, params={"texte": "accueil.ndj"}).json()["elements"][0]
    corps = {"mot_de_passe_temporaire": "Temporaire-2026!Sur", "motif": "Oubli du mot de passe (test)"}
    r = client.post(f"{API}/utilisateurs/{cible['id']}/reinitialisation-mot-de-passe", headers=h, json=corps)
    assert r.status_code == 403 and r.json()["code"] == "REAUTHENTIFICATION_REQUISE"
    connexions.reauthentifier("admin.fonctionnel", h)
    r = client.post(f"{API}/utilisateurs/{cible['id']}/reinitialisation-mot-de-passe", headers=h, json=corps)
    assert r.status_code == 200
    r = client.post(f"{API}/auth/connexion", json={"identifiant": "accueil.ndj",
                                                   "mot_de_passe": "Temporaire-2026!Sur"})
    assert r.json()["type_session"] == "CHANGEMENT_MOT_DE_PASSE"


def test_secret_totp_chiffre_au_repos(app, donnees):
    from sqlalchemy import text

    with app.state.fabrique.transaction() as bd:
        brut = bd.execute(text("SELECT mfa_secret FROM utilisateurs WHERE identifiant='officier.ndj'")).scalar()
    assert brut and SECRETS_TOTP_DEMO["officier.ndj"] not in brut and brut.startswith("k1$")
