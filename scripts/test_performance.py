"""Tests de performance sur volumes SYNTHETIQUES importants.

Usage :
  TPGIS_PERF_DATABASE_URL=postgresql+psycopg://tpgis:...@localhost/tpgis_perf \\
  python scripts/test_performance.py --personnes 100000 --plaintes 200000 --sortie docs/performances.md

La base cible est entierement videe. Les mesures sont faites a travers l'API
(application FastAPI en processus, sans reseau) et incluent donc la
validation, le controle d'acces, le dechiffrement et la journalisation.
"""

from __future__ import annotations

import argparse
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyotp  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, select, text  # noqa: E402

from tpgis.server.config import ParametresServeur  # noqa: E402
from tpgis.server.database.models import Personne, Plainte, Role, Utilisateur  # noqa: E402
from tpgis.server.database.seed.demonstration import MOT_DE_PASSE_DEMO, SECRETS_TOTP_DEMO, Volumes, generer  # noqa
from tpgis.server.main import creer_application  # noqa: E402
from tpgis.server.security.crypto import generer_cle  # noqa: E402

API = "/api/v1"


def mesurer(fonction, repetitions: int) -> dict:
    durees = []
    for _ in range(repetitions):
        debut = time.perf_counter()
        fonction()
        durees.append((time.perf_counter() - debut) * 1000)
    durees.sort()
    return {
        "mediane_ms": round(statistics.median(durees), 1),
        "p95_ms": round(durees[max(0, int(len(durees) * 0.95) - 1)], 1),
        "max_ms": round(durees[-1], 1),
    }


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--personnes", type=int, default=100_000)
    a.add_argument("--plaintes", type=int, default=200_000)
    a.add_argument("--faits", type=int, default=50_000)
    a.add_argument("--dossiers", type=int, default=20_000)
    a.add_argument("--repetitions", type=int, default=20)
    a.add_argument("--sortie", default=None)
    args = a.parse_args()
    url = os.environ.get("TPGIS_PERF_DATABASE_URL")
    if not url:
        sys.exit("Définir TPGIS_PERF_DATABASE_URL (base dédiée, elle sera vidée).")
    moteur = create_engine(url)
    with moteur.begin() as c:
        if c.dialect.name == "postgresql":
            c.execute(text("DROP SCHEMA public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
    moteur.dispose()

    tmp = Path(tempfile.mkdtemp(prefix="tpgis_perf_"))
    p = ParametresServeur(
        environnement="test",
        database_url=url,
        cles_donnees=f"k1:{generer_cle()}",
        cle_index=generer_cle(),
        cle_sauvegarde=generer_cle(),
        repertoire_stockage=tmp / "stockage",
        repertoire_sauvegardes=tmp / "sauvegardes",
        limite_requetes_par_minute=10**9,
        limite_connexion_par_minute_ip=10**9,
    )
    app = creer_application(p)
    debut = time.perf_counter()
    with app.state.fabrique.transaction() as bd:
        volumes = Volumes(
            personnes=args.personnes,
            plaintes=args.plaintes,
            faits=args.faits,
            dossiers=args.dossiers,
            captures=200,
        )
        generer(bd, p, volumes)
        # Compte de mesure a perimetre national (donnees synthetiques).
        role = bd.execute(select(Role).where(Role.code == "RESPONSABLE_UNITE")).scalar_one()
        u = bd.execute(select(Utilisateur).where(Utilisateur.identifiant == "responsable.ndj")).scalar_one()
        u.portee = "NATIONALE"
        u.role_id = role.id
    duree_generation = time.perf_counter() - debut
    with app.state.fabrique.moteur.begin() as c:
        if c.dialect.name == "postgresql":
            c.execute(text("ANALYZE"))
    with app.state.fabrique.transaction() as bd:
        nb_plaintes = bd.execute(select(func.count(Plainte.id))).scalar_one()
        nb_personnes = bd.execute(select(func.count(Personne.id))).scalar_one()
        exemple_plainte = bd.execute(select(Plainte.numero).limit(1).offset(nb_plaintes // 2)).scalar_one()
        exemple_personne = bd.execute(select(Personne).limit(1).offset(nb_personnes // 2)).scalar_one()
        doc = bd.execute(
            select(Personne.numero_document).where(Personne.numero_document.is_not(None)).limit(1)
        ).scalar_one()

    client = TestClient(app)

    def entetes(identifiant: str) -> dict:
        with app.state.fabrique.transaction() as bd:
            bd.execute(
                select(Utilisateur).where(Utilisateur.identifiant == identifiant)
            ).scalar_one().mfa_dernier_pas = None
        code = pyotp.TOTP(SECRETS_TOTP_DEMO[identifiant]).now() if identifiant in SECRETS_TOTP_DEMO else None
        r = client.post(
            f"{API}/auth/connexion",
            json={"identifiant": identifiant, "mot_de_passe": MOT_DE_PASSE_DEMO, "code_mfa": code},
        )
        r.raise_for_status()
        return {"Authorization": f"Bearer {r.json()['jeton']}", "X-TPGIS-Finalite": "Mesure%20de%20performance"}

    national = entetes("responsable.ndj")
    unite = entetes("officier.ndj")

    def verifier(r):
        assert r.status_code < 400, r.text
        return r

    n = args.repetitions
    mesures = {
        "Connexion (Argon2id + TOTP)": mesurer(lambda: entetes("officier.ndj"), max(5, n // 4)),
        "Liste des plaintes, page 1 (périmètre national)": mesurer(
            lambda: verifier(client.get(f"{API}/plaintes", headers=national, params={"taille": 50})), n
        ),
        "Liste des plaintes, page 200 (périmètre national)": mesurer(
            lambda: verifier(client.get(f"{API}/plaintes", headers=national, params={"taille": 50, "page": 200})), n
        ),
        "Liste des plaintes, page 1 (périmètre unité)": mesurer(
            lambda: verifier(client.get(f"{API}/plaintes", headers=unite, params={"taille": 50})), n
        ),
        "Filtre par statut et période (national)": mesurer(
            lambda: verifier(
                client.get(
                    f"{API}/plaintes",
                    headers=national,
                    params={"statut": "EN_TRAITEMENT", "du": "2026-01-01", "au": "2026-06-30"},
                )
            ),
            n,
        ),
        "Recherche exacte par numéro de plainte": mesurer(
            lambda: verifier(
                client.post(
                    f"{API}/recherche",
                    headers=national,
                    json={"finalite": "Mesure de performance", "numero_plainte": exemple_plainte},
                )
            ),
            n,
        ),
        "Recherche par nom, prénoms et date de naissance": mesurer(
            lambda: verifier(
                client.post(
                    f"{API}/recherche",
                    headers=national,
                    json={
                        "finalite": "Mesure de performance",
                        "nom": exemple_personne.nom,
                        "prenoms": exemple_personne.prenoms,
                        "date_naissance": exemple_personne.date_naissance.isoformat()
                        if exemple_personne.date_naissance
                        else None,
                    },
                )
            ),
            n,
        ),
        "Recherche par référence de document (index aveugle)": mesurer(
            lambda: verifier(
                client.post(
                    f"{API}/recherche",
                    headers=national,
                    json={"finalite": "Mesure de performance", "numero_document": doc},
                )
            ),
            n,
        ),
        "Liste des personnes filtrée par nom": mesurer(
            lambda: verifier(client.get(f"{API}/personnes", headers=national, params={"texte": exemple_personne.nom})),
            n,
        ),
        "Fiche personne (déchiffrement et audit)": mesurer(
            lambda: verifier(client.get(f"{API}/personnes/{exemple_personne.id}", headers=national)), n
        ),
        "Tableau de bord (national, 12 mois)": mesurer(
            lambda: verifier(client.get(f"{API}/statistiques/tableau-de-bord", headers=national)), max(5, n // 2)
        ),
        "Données cartographiques (national)": mesurer(
            lambda: verifier(client.get(f"{API}/carte/donnees", headers=national)), max(5, n // 2)
        ),
        "Création d'une plainte (transaction complète)": mesurer(
            lambda: verifier(
                client.post(
                    f"{API}/plaintes",
                    headers=unite,
                    json={
                        "service_enregistrement": "Accueil",
                        "description": "Plainte synthétique de mesure de performance.",
                    },
                )
            ),
            n,
        ),
    }
    with app.state.fabrique.transaction() as bd:
        nb_audit = bd.execute(text("SELECT COUNT(*) FROM journal_audit")).scalar_one()
    app.state.fabrique.moteur.dispose()

    lignes = [
        "# Résultats des tests de performance",
        "",
        "Document généré automatiquement par `scripts/test_performance.py`. Données exclusivement synthétiques.",
        "",
        f"Date d'exécution : {datetime.now(UTC):%d/%m/%Y %H:%M} UTC",
        "",
        "## Environnement de mesure",
        "",
        f"Système : {platform.platform()}",
        f"Processeur : {platform.processor() or platform.machine()} ({os.cpu_count()} cœurs logiques)",
        f"Python : {platform.python_version()}",
        f"Base de données : {url.split('://')[0]} (serveur local, même machine)",
        "Client : application FastAPI appelée en processus (sans réseau ni TLS).",
        "",
        "## Volumes synthétiques",
        "",
        "| Élément | Volume |",
        "|---|---|",
        f"| Plaintes | {nb_plaintes:,} |".replace(",", " "),
        f"| Personnes | {nb_personnes:,} |".replace(",", " "),
        f"| Faits | {args.faits:,} |".replace(",", " "),
        f"| Dossiers | {args.dossiers:,} |".replace(",", " "),
        f"| Événements d'audit après mesures | {nb_audit:,} |".replace(",", " "),
        "",
        f"Durée de génération et d'insertion chiffrée : {duree_generation:.0f} secondes.",
        "",
        "## Temps de réponse mesurés",
        "",
        "| Opération | Médiane (ms) | 95e centile (ms) | Maximum (ms) |",
        "|---|---|---|---|",
    ]
    for nom, m in mesures.items():
        lignes.append(f"| {nom} | {m['mediane_ms']} | {m['p95_ms']} | {m['max_ms']} |")
    lignes += [
        "",
        "## Lecture des résultats",
        "",
        "Les listes sont paginées côté serveur (50 éléments par page) : le poste client ne charge jamais le "
        "registre complet. Les recherches exactes s'appuient sur des index (numéros uniques, index aveugle "
        "HMAC des documents). La connexion est volontairement coûteuse (Argon2id, 64 Mo, 3 passes) pour "
        "ralentir les attaques par force brute.",
        "",
        "Ces mesures doivent être reproduites sur l'infrastructure cible (serveur dédié, réseau, TLS, "
        "volumétrie nationale estimée) avant la mise en production.",
        "",
    ]
    texte = "\n".join(lignes)
    if args.sortie:
        Path(args.sortie).write_text(texte, encoding="utf-8")
    print(texte)


if __name__ == "__main__":
    main()
