"""Outil d'administration du serveur TPGIS.

Usage : python -m tpgis.server.cli <commande> [options]

Commandes :
  generer-cles              Affiche un jeu de cles a placer dans le coffre de secrets.
  migrer                    Applique les migrations de schema.
  initialiser               Migre, cree les roles initiaux et associe la base a l'environnement.
  creer-administrateur      Cree le premier administrateur fonctionnel (amorcage unique).
  charger-demonstration     Charge le jeu de donnees synthetiques (interdit en production).
  verifier-audit            Verifie l'integrite de la chaine du journal d'audit.
  sauvegarder               Realise une sauvegarde chiffree.
  verifier-sauvegarde DIR   Controle l'integrite d'une sauvegarde.
  restaurer DIR             Restaure une sauvegarde (ecrase les donnees actuelles).
  codes-demo                Affiche les codes TOTP courants des comptes de demonstration.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from sqlalchemy import select

from tpgis.server.config import ParametresServeur, obtenir_parametres, verifier_configuration_production
from tpgis.server.database.initialisation import (
    initialiser_metadonnees,
    initialiser_roles,
    migrer,
    revision_courante,
)
from tpgis.server.database.session import FabriqueSessions, creer_moteur
from tpgis.server.main import initialiser_chiffrement
from tpgis.server.security import crypto, passwords
from tpgis.server.services import audit
from tpgis.shared.enums import Environnement


def _preparer(p: ParametresServeur) -> FabriqueSessions:
    erreurs = verifier_configuration_production(p)
    if erreurs:
        sys.exit("Configuration non conforme :\n  " + "\n  ".join(erreurs))
    initialiser_chiffrement(p)
    if p.est_sqlite:
        Path(p.database_url.split("///", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)
    return FabriqueSessions(creer_moteur(p))


def cmd_generer_cles(_args, _p) -> None:
    print("# A placer dans le coffre de secrets (jamais dans le depot de code) :")
    print(f"TPGIS_CLES_DONNEES=k1:{crypto.generer_cle()}")
    print("TPGIS_CLE_DONNEES_ACTIVE=k1")
    print(f"TPGIS_CLE_INDEX={crypto.generer_cle()}")
    print(f"TPGIS_CLE_SAUVEGARDE={crypto.generer_cle()}")


def cmd_migrer(_args, p) -> None:
    fabrique = _preparer(p)
    migrer(fabrique.moteur)
    with fabrique.transaction() as bd:
        print(f"Schéma à jour (révision {revision_courante(bd)}).")


def cmd_initialiser(_args, p) -> None:
    fabrique = _preparer(p)
    migrer(fabrique.moteur)
    with fabrique.transaction() as bd:
        initialiser_metadonnees(bd, p)
        n = initialiser_roles(bd)
    print(f"Instance initialisée ({p.environnement}). Rôles créés : {n}.")


def cmd_creer_administrateur(args, p) -> None:
    from tpgis.server.database.models import Role, Unite, Utilisateur
    from tpgis.shared.enums import Corps, Portee, TypeUnite

    fabrique = _preparer(p)
    with fabrique.transaction() as bd:
        role = bd.execute(select(Role).where(Role.code == "ADMIN_FONCTIONNEL")).scalar_one()
        if bd.execute(select(Utilisateur.id).where(Utilisateur.role_id == role.id)).first():
            sys.exit("Un administrateur fonctionnel existe déjà : l'amorçage n'est possible qu'une fois.")
        unite = bd.execute(select(Unite).where(Unite.code == args.code_unite)).scalar_one_or_none()
        if unite is None:
            unite = Unite(
                code=args.code_unite,
                nom=args.nom_unite,
                type_unite=TypeUnite.DIRECTION,
                corps=Corps(args.corps),
                province_code="TD-ND",
                ville="N'Djamena",
            )
            bd.add(unite)
            bd.flush()
        mot_de_passe = getpass.getpass("Mot de passe initial : ")
        if mot_de_passe != getpass.getpass("Confirmation : "):
            sys.exit("Les mots de passe ne correspondent pas.")
        erreurs = passwords.controler_politique(mot_de_passe, p.mot_de_passe_longueur_min, args.identifiant)
        if erreurs:
            sys.exit(" ".join(erreurs))
        u = Utilisateur(
            identifiant=args.identifiant,
            nom=args.nom,
            prenoms=args.prenoms,
            unite_id=unite.id,
            role_id=role.id,
            portee=Portee.NATIONALE,
            mot_de_passe_hash=passwords.hacher(mot_de_passe),
            doit_changer_mot_de_passe=True,
        )
        bd.add(u)
        bd.flush()
        audit.enregistrer(
            bd,
            action="AMORCAGE_ADMINISTRATEUR",
            trace_id="00000000-0000-0000-0000-000000000000",
            identifiant="cli",
            type_ressource="utilisateur",
            ressource_id=u.id,
            details={"identifiant": u.identifiant},
        )
    print("Administrateur créé. Changement de mot de passe et enrôlement MFA exigés à la première connexion.")


def cmd_charger_demonstration(args, p) -> None:
    from tpgis.server.database.seed.demonstration import Volumes, generer

    if p.environnement not in (Environnement.DEMONSTRATION, Environnement.DEVELOPPEMENT, Environnement.TEST):
        sys.exit("Les données de démonstration ne peuvent être chargées qu'en démonstration, test ou développement.")
    fabrique = _preparer(p)
    migrer(fabrique.moteur)
    with fabrique.transaction() as bd:
        initialiser_metadonnees(bd, p)
        initialiser_roles(bd)
        volumes = Volumes(
            personnes=args.personnes,
            plaintes=args.plaintes,
            faits=args.faits,
            dossiers=args.dossiers,
            captures=args.captures,
        )
        resultat = generer(bd, p, volumes)
    print(json.dumps(resultat, ensure_ascii=False, indent=2))


def cmd_verifier_audit(_args, p) -> None:
    fabrique = _preparer(p)
    with fabrique.transaction() as bd:
        resultat = audit.verifier_chaine(bd)
    print(json.dumps(resultat, ensure_ascii=False))
    if not resultat["integre"]:
        sys.exit(2)


def cmd_sauvegarder(_args, p) -> None:
    from tpgis.server.services import sauvegarde

    fabrique = _preparer(p)
    with fabrique.transaction() as bd:
        revision = revision_courante(bd)
        empreinte = audit.derniere_empreinte(bd)
    dossier = sauvegarde.sauvegarder(p, revision, empreinte)
    with fabrique.transaction() as bd:
        audit.enregistrer(
            bd,
            action="SAUVEGARDE",
            trace_id="00000000-0000-0000-0000-000000000000",
            identifiant="cli",
            type_ressource="systeme",
            details={"dossier": dossier.name},
        )
    print(f"Sauvegarde créée : {dossier}")


def cmd_verifier_sauvegarde(args, p) -> None:
    from tpgis.server.services import sauvegarde

    _preparer(p)
    manifeste = sauvegarde.verifier(p, Path(args.dossier))
    print(f"Sauvegarde intègre : {manifeste['cree_le']} ({manifeste['environnement']}).")


def cmd_restaurer(args, p) -> None:
    from tpgis.server.services import sauvegarde

    fabrique = _preparer(p)
    if not args.confirmer:
        sys.exit("Ajoutez --confirmer pour écraser les données actuelles.")
    fabrique.moteur.dispose()
    manifeste = sauvegarde.restaurer(p, Path(args.dossier), confirmer_ecrasement=True)
    with fabrique.transaction() as bd:
        audit.enregistrer(
            bd,
            action="RESTAURATION",
            trace_id="00000000-0000-0000-0000-000000000000",
            identifiant="cli",
            type_ressource="systeme",
            details={"sauvegarde": manifeste["cree_le"]},
        )
    print(f"Restauration effectuée depuis la sauvegarde du {manifeste['cree_le']}.")


def cmd_codes_demo(_args, p) -> None:
    from tpgis.server.database.seed.demonstration import SECRETS_TOTP_DEMO, code_totp_demo

    if p.est_production:
        sys.exit("Commande indisponible en production.")
    for ident in SECRETS_TOTP_DEMO:
        print(f"{ident:20s} {code_totp_demo(ident)}")


def main(argv: list[str] | None = None) -> None:
    analyseur = argparse.ArgumentParser(prog="tpgis-admin", description="Administration du serveur TPGIS")
    sous = analyseur.add_subparsers(dest="commande", required=True)
    sous.add_parser("generer-cles").set_defaults(fn=cmd_generer_cles)
    sous.add_parser("migrer").set_defaults(fn=cmd_migrer)
    sous.add_parser("initialiser").set_defaults(fn=cmd_initialiser)
    a = sous.add_parser("creer-administrateur")
    a.add_argument("--identifiant", required=True)
    a.add_argument("--nom", required=True)
    a.add_argument("--prenoms", required=True)
    a.add_argument("--code-unite", default="DIRECTION-SI")
    a.add_argument("--nom-unite", default="Direction des systèmes d'information")
    a.add_argument("--corps", choices=["POLICE", "GENDARMERIE"], default="POLICE")
    a.set_defaults(fn=cmd_creer_administrateur)
    d = sous.add_parser("charger-demonstration")
    d.add_argument("--personnes", type=int, default=400)
    d.add_argument("--plaintes", type=int, default=600)
    d.add_argument("--faits", type=int, default=250)
    d.add_argument("--dossiers", type=int, default=120)
    d.add_argument("--captures", type=int, default=40)
    d.set_defaults(fn=cmd_charger_demonstration)
    sous.add_parser("verifier-audit").set_defaults(fn=cmd_verifier_audit)
    sous.add_parser("sauvegarder").set_defaults(fn=cmd_sauvegarder)
    v = sous.add_parser("verifier-sauvegarde")
    v.add_argument("dossier")
    v.set_defaults(fn=cmd_verifier_sauvegarde)
    r = sous.add_parser("restaurer")
    r.add_argument("dossier")
    r.add_argument("--confirmer", action="store_true")
    r.set_defaults(fn=cmd_restaurer)
    sous.add_parser("codes-demo").set_defaults(fn=cmd_codes_demo)
    args = analyseur.parse_args(argv)
    args.fn(args, obtenir_parametres())


if __name__ == "__main__":
    main()
