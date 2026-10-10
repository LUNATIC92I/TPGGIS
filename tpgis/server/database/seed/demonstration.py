"""Jeu de donnees SYNTHETIQUES de demonstration et de test.

Tous les noms, numeros et empreintes sont fictifs et generes aleatoirement.
Aucune donnee reelle de citoyen n'est utilisee. Ce module refuse de
s'executer sur une base de production et marque la base comme contenant des
donnees synthetiques, ce qui interdit ensuite son ouverture en production.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionBD

from tpgis.server.config import ParametresServeur
from tpgis.server.database.models import (
    ActeProcedure,
    CaptureBiometrique,
    CategorieFait,
    Compteur,
    Dossier,
    Fait,
    LienDossierPersonne,
    LienDossierPlainte,
    LienFaitPersonne,
    LienPlaintePersonne,
    MetadonneeInstance,
    Personne,
    Plainte,
    Role,
    Unite,
    Utilisateur,
)
from tpgis.server.security import passwords
from tpgis.server.security.crypto import index_aveugle, normaliser_texte
from tpgis.shared.enums import (
    Corps,
    EtatVerification,
    NatureInformation,
    RolePersonne,
    SourceInformation,
    StatutCapture,
    StatutDossier,
    StatutPersonne,
    StatutPlainte,
    StatutVerificationIdentite,
    TypeActe,
    TypeProcedure,
    TypeUnite,
)
from tpgis.shared.geographie import villes

MOT_DE_PASSE_DEMO = "Demo-Tpgis-2026!"

# Secrets TOTP de DEMONSTRATION uniquement (publics, documentes).
SECRETS_TOTP_DEMO = {
    "admin.technique": "TPGISDEMOADMINTECHNIQUE2",
    "admin.fonctionnel": "TPGISDEMOADMINFONCTION22",
    "auditeur": "TPGISDEMOAUDITEURDEMO222",
    "officier.ndj": "TPGISDEMOOFFICIERNDJAMEN",
    "responsable.ndj": "TPGISDEMORESPONSABLENDJA",
    "enqueteur.ndj": "TPGISDEMOENQUETEURNDJAME",
    "officier.abc": "TPGISDEMOOFFICIERABECHEA",
}

CATEGORIES = [
    ("VOL_SIMPLE", "Vol simple"),
    ("VOL_AGGRAVE", "Vol aggravé"),
    ("VOL_BETAIL", "Vol de bétail"),
    ("COUPS_BLESSURES", "Coups et blessures volontaires"),
    ("VIOLENCES_FAMILIALES", "Violences au sein de la famille"),
    ("MENACES", "Menaces"),
    ("ESCROQUERIE", "Escroquerie"),
    ("ABUS_CONFIANCE", "Abus de confiance"),
    ("DEGRADATION_BIENS", "Destruction ou dégradation de biens"),
    ("ACCIDENT_CIRCULATION", "Accident de la circulation"),
    ("PERTE_DOCUMENTS", "Déclaration de perte de documents"),
    ("TROUBLE_ORDRE_PUBLIC", "Trouble à l'ordre public"),
    ("CYBERCRIMINALITE", "Infraction commise au moyen d'un système informatique"),
    ("AUTRE", "Autre fait signalé"),
]

# Listes de noms fictifs servant uniquement a generer des combinaisons aleatoires.
NOMS = [
    "ABAKAR",
    "ADOUM",
    "BRAHIM",
    "DJIMET",
    "HASSANE",
    "KAMOUGUE",
    "MAHAMAT",
    "NGARTA",
    "OUSMANE",
    "TCHERE",
    "YAYA",
    "ZAKARIA",
    "NODJI",
    "MBAIRO",
    "DJASRA",
    "GOLDOUM",
    "ALLAMINE",
    "KOULAMALLAH",
    "NGARMBAYE",
    "RIMADJI",
    "SOUGUI",
    "TAHIR",
    "DOUTOUM",
    "BEASSOUM",
    "MOUSSA",
    "NDOUBA",
]
PRENOMS_M = [
    "Ahmat",
    "Ali",
    "Idriss",
    "Moussa",
    "Saleh",
    "Issa",
    "Djibrine",
    "Abdelkerim",
    "Ngueto",
    "Nadji",
    "Rimtebaye",
    "Mbaiki",
    "Doumbe",
    "Haroun",
    "Oumar",
    "Hissein",
    "Adam",
    "Youssouf",
]
PRENOMS_F = [
    "Achta",
    "Fatime",
    "Hawa",
    "Khadidja",
    "Zenaba",
    "Mariam",
    "Ndilbe",
    "Neloumta",
    "Remadji",
    "Asnané",
    "Halimé",
    "Kaltouma",
    "Djénéba",
    "Amina",
    "Mbaïrassem",
    "Haoua",
]


@dataclass
class Volumes:
    personnes: int = 400
    plaintes: int = 600
    faits: int = 250
    dossiers: int = 120
    captures: int = 40


def _ajouter_metadonnee(bd: SessionBD, cle: str, valeur: str) -> None:
    m = bd.get(MetadonneeInstance, cle)
    if m is None:
        bd.add(MetadonneeInstance(cle=cle, valeur=valeur))
    else:
        m.valeur = valeur


def _de(nom: str) -> str:
    """Elision francaise : de Sarh, d'Abeche."""
    return f"d'{nom}" if normaliser_texte(nom)[:1] in "AEIOUY" else f"de {nom}"


def _unites(bd: SessionBD) -> list[Unite]:
    if bd.execute(select(Unite.id).limit(1)).first():
        return list(bd.execute(select(Unite)).scalars())
    lieux = villes()
    unites: list[Unite] = []
    dgpn = Unite(
        code="DGPN",
        nom="Direction générale de la police nationale (fictive)",
        type_unite=TypeUnite.DIRECTION,
        corps=Corps.POLICE,
        province_code="TD-ND",
        ville="N'Djamena",
        latitude=12.1150,
        longitude=15.0470,
        est_synthetique=True,
    )
    dggn = Unite(
        code="DGGN",
        nom="Direction générale de la gendarmerie nationale (fictive)",
        type_unite=TypeUnite.DIRECTION,
        corps=Corps.GENDARMERIE,
        province_code="TD-ND",
        ville="N'Djamena",
        latitude=12.1080,
        longitude=15.0390,
        est_synthetique=True,
    )
    bd.add_all([dgpn, dggn])
    bd.flush()
    unites += [dgpn, dggn]
    abreviations = {
        "N'Djamena": "NDJ",
        "Abéché": "ABC",
        "Moundou": "MDO",
        "Sarh": "SRH",
        "Bongor": "BGR",
        "Kelo": "KLO",
        "Pala": "PLA",
        "Am Timan": "AMT",
        "Doba": "DBA",
        "Mongo": "MGO",
        "Ati": "ATI",
        "Laï": "LAI",
        "Oum Hadjer": "OHJ",
        "Mao": "MAO",
        "Faya Largeau": "FYA",
        "Biltine": "BLT",
        "Bol": "BOL",
        "Fada": "FDA",
        "Zouar": "ZOU",
    }
    for v in lieux:
        abr = abreviations.get(v["nom"], normaliser_texte(v["nom"])[:3])
        cp = Unite(
            code=f"CP-{abr}",
            nom=f"Commissariat {_de(v['nom'])} (fictif)",
            type_unite=TypeUnite.COMMISSARIAT_CENTRAL if v["capitale"] else TypeUnite.COMMISSARIAT,
            corps=Corps.POLICE,
            parent_id=dgpn.id,
            province_code=v["province_code"],
            ville=v["nom"],
            latitude=round(v["latitude"] + 0.006, 4),
            longitude=round(v["longitude"] - 0.006, 4),
            est_synthetique=True,
        )
        bg = Unite(
            code=f"BG-{abr}",
            nom=f"Brigade de gendarmerie {_de(v['nom'])} (fictive)",
            type_unite=TypeUnite.BRIGADE,
            corps=Corps.GENDARMERIE,
            parent_id=dggn.id,
            province_code=v["province_code"],
            ville=v["nom"],
            latitude=round(v["latitude"] - 0.006, 4),
            longitude=round(v["longitude"] + 0.006, 4),
            est_synthetique=True,
        )
        bd.add_all([cp, bg])
        unites += [cp, bg]
    bd.flush()
    # Un commissariat d'arrondissement subordonne pour illustrer la hierarchie.
    central = next(u for u in unites if u.code == "CP-NDJ")
    arr = Unite(
        code="CP-NDJ-A1",
        nom="Commissariat du 1er arrondissement de N'Djamena (fictif)",
        type_unite=TypeUnite.COMMISSARIAT,
        corps=Corps.POLICE,
        parent_id=central.id,
        province_code="TD-ND",
        ville="N'Djamena",
        latitude=12.1300,
        longitude=15.0550,
        est_synthetique=True,
    )
    bd.add(arr)
    bd.flush()
    unites.append(arr)
    return unites


def _utilisateurs(bd: SessionBD, unites: dict[str, Unite]) -> dict[str, Utilisateur]:
    roles = {r.code: r for r in bd.execute(select(Role)).scalars()}
    empreinte = passwords.hacher(MOT_DE_PASSE_DEMO)
    definitions = [
        ("admin.technique", "ADMIN_TECHNIQUE", "DGPN", "Technicien", "SYSTEME", "Adoum", None),
        ("admin.fonctionnel", "ADMIN_FONCTIONNEL", "DGPN", "Commissaire", "HABILITATIONS", "Mariam", None),
        ("auditeur", "AUDITEUR", "DGPN", "Inspecteur", "CONTROLE", "Issa", None),
        ("responsable.ndj", "RESPONSABLE_UNITE", "CP-NDJ", "Commissaire principal", "RESPONSABLE", "Hawa", None),
        ("officier.ndj", "OFFICIER_HABILITE", "CP-NDJ", "Officier de police", "OFFICIER", "Moussa", None),
        ("accueil.ndj", "AGENT_ACCUEIL", "CP-NDJ", "Agent de police", "ACCUEIL", "Achta", None),
        ("enqueteur.ndj", "ENQUETEUR", "CP-NDJ", "Inspecteur de police", "ENQUETEUR", "Ali", None),
        ("consultation.ndj", "CONSULTATION", "CP-NDJ", "Agent", "CONSULTATION", "Zenaba", None),
        ("accueil.ndj.a1", "AGENT_ACCUEIL", "CP-NDJ-A1", "Agent de police", "ARRONDISSEMENT", "Saleh", None),
        ("officier.abc", "OFFICIER_HABILITE", "CP-ABC", "Officier de police", "OFFICIER", "Idriss", None),
        ("accueil.abc", "AGENT_ACCUEIL", "CP-ABC", "Agent de police", "ACCUEIL", "Fatime", None),
        ("gendarme.mdo", "AGENT_ACCUEIL", "BG-MDO", "Maréchal des logis", "BRIGADE", "Djibrine", None),
    ]
    resultat = {}
    for ident, code_role, code_unite, grade, nom, prenom, _ in definitions:
        existant = bd.execute(select(Utilisateur).where(Utilisateur.identifiant == ident)).scalar_one_or_none()
        if existant:
            resultat[ident] = existant
            continue
        role = roles[code_role]
        u = Utilisateur(
            identifiant=ident,
            nom=f"{nom} (FICTIF)",
            prenoms=prenom,
            grade=grade,
            matricule=f"DEMO-{len(resultat) + 1:04d}",
            unite_id=unites[code_unite].id,
            role_id=role.id,
            portee=role.portee_defaut,
            mot_de_passe_hash=empreinte,
            doit_changer_mot_de_passe=False,
            mot_de_passe_modifie_le=datetime.now(UTC),
            actif=True,
            est_synthetique=True,
        )
        if ident in SECRETS_TOTP_DEMO:
            u.mfa_secret = SECRETS_TOTP_DEMO[ident]
            u.mfa_active = True
        bd.add(u)
        resultat[ident] = u
    bd.flush()
    return resultat


def _categories(bd: SessionBD) -> list[CategorieFait]:
    existantes = {c.code: c for c in bd.execute(select(CategorieFait)).scalars()}
    for code, libelle in CATEGORIES:
        if code not in existantes:
            c = CategorieFait(
                code=code,
                libelle=libelle,
                active=True,
                validee=False,
                description="Catégorie d'exemple, à valider par les autorités compétentes.",
            )
            bd.add(c)
            existantes[code] = c
    bd.flush()
    return list(existantes.values())


def _personne_aleatoire(r: random.Random, numero: int, unite: Unite, createur: Utilisateur) -> Personne:
    feminin = r.random() < 0.45
    nom = r.choice(NOMS)
    prenoms = r.choice(PRENOMS_F if feminin else PRENOMS_M)
    if r.random() < 0.3:
        prenoms += " " + r.choice(PRENOMS_F if feminin else PRENOMS_M)
    naissance = date(1950, 1, 1) + timedelta(days=r.randint(0, 365 * 55)) if r.random() < 0.8 else None
    doc = None
    if r.random() < 0.55:
        doc = f"FICTIF{r.randint(10**7, 10**8 - 1)}"
    lieu = r.choice([v["nom"] for v in villes()]) if r.random() < 0.7 else None
    return Personne(
        numero_interne=f"P-{date.today().year}-{numero:06d}",
        nom=nom,
        prenoms=prenoms,
        nom_normalise=normaliser_texte(f"{nom} {prenoms}"),
        date_naissance=naissance,
        lieu_naissance=lieu,
        nationalite="Tchadienne" if r.random() < 0.9 else None,
        sexe="F" if feminin else "M",
        coordonnees={
            "telephone": f"+235 6{r.randint(0, 9)} {r.randint(10, 99)} {r.randint(10, 99)} {r.randint(10, 99)} (fictif)"
        }
        if r.random() < 0.6
        else None,
        type_document="CARTE_NATIONALE" if doc else None,
        numero_document=doc,
        index_document=index_aveugle().calculer(doc),
        statut_verification=r.choice(list(StatutVerificationIdentite)),
        unite_creation_id=unite.id,
        cree_par_id=createur.id,
        statut=StatutPersonne.ACTIVE,
        est_synthetique=True,
    )


DESCRIPTIONS = [
    "Le plaignant déclare avoir constaté la disparition de biens personnels à son domicile (récit fictif).",
    "La plaignante rapporte une altercation sur un marché ayant occasionné des blessures légères (récit fictif).",
    "Déclaration de la perte de pièces administratives lors d'un déplacement (récit fictif).",
    "Le déclarant signale la disparition de plusieurs têtes de bétail au pâturage (récit fictif).",
    "Signalement d'une transaction frauduleuse lors de la vente d'un véhicule (récit fictif).",
    "Le déclarant rapporte des menaces verbales répétées de la part d'un voisin (récit fictif).",
    "Accident matériel entre deux véhicules à une intersection, sans blessé (récit fictif).",
]


def generer(bd: SessionBD, p: ParametresServeur, volumes: Volumes | None = None, graine: int = 2026) -> dict:
    """Genere le jeu de donnees synthetiques. Idempotent pour le referentiel."""
    if p.est_production:
        raise RuntimeError("Interdit : les données de démonstration ne peuvent pas être chargées en production.")
    env = bd.get(MetadonneeInstance, "environnement")
    if env is not None and env.valeur == "production":
        raise RuntimeError("Interdit : cette base est marquée comme base de production.")
    volumes = volumes or Volumes()
    r = random.Random(graine)
    _ajouter_metadonnee(bd, "contient_donnees_synthetiques", "oui")

    liste_unites = _unites(bd)
    unites = {u.code: u for u in liste_unites}
    utilisateurs = _utilisateurs(bd, unites)
    categories = _categories(bd)
    operationnelles = [u for u in liste_unites if u.type_unite != TypeUnite.DIRECTION]
    agents_par_unite: dict[str, list[Utilisateur]] = {}
    for u in utilisateurs.values():
        agents_par_unite.setdefault(u.unite_id, []).append(u)
    createur_defaut = utilisateurs["officier.ndj"]

    # Unites ponderees : plus d'activite dans les grandes villes.
    poids = [
        6 if u.ville == "N'Djamena" else 2 if u.ville in ("Moundou", "Abéché", "Sarh") else 1 for u in operationnelles
    ]

    base_numero = bd.execute(select(Compteur.valeur).where(Compteur.cle == f"P:NAT:{date.today().year}")).scalar() or 0
    personnes = []
    for i in range(volumes.personnes):
        unite = r.choices(operationnelles, poids)[0]
        createur = r.choice(agents_par_unite.get(unite.id, [createur_defaut]))
        personnes.append(_personne_aleatoire(r, base_numero + i + 1, unite, createur))
    bd.add_all(personnes)
    _fixer_compteur(bd, f"P:NAT:{date.today().year}", base_numero + volumes.personnes)
    bd.flush()

    maintenant = datetime.now(UTC)
    compteurs: dict[str, int] = {}
    plaintes = []
    for _ in range(volumes.plaintes):
        unite = r.choices(operationnelles, poids)[0]
        recue = maintenant - timedelta(days=r.randint(0, 540), hours=r.randint(0, 23), minutes=r.randint(0, 59))
        cle = f"PL:{unite.code}:{recue.year}"
        compteurs[cle] = compteurs.get(cle, _valeur_compteur(bd, cle)) + 1
        agents = agents_par_unite.get(unite.id, [createur_defaut])
        statut = r.choices(list(StatutPlainte), [18, 12, 30, 8, 25, 7])[0]
        plaintes.append(
            Plainte(
                numero=f"PL-{unite.code}-{recue.year}-{compteurs[cle]:06d}",
                recue_le=recue,
                service_enregistrement=f"Accueil {unite.nom}",
                unite_id=unite.id,
                agent_responsable_id=r.choice(agents).id if unite.id in agents_par_unite else None,
                categorie_id=r.choice(categories).id if r.random() < 0.92 else None,
                description=r.choice(DESCRIPTIONS),
                date_faits=(recue - timedelta(days=r.randint(0, 10))).date() if r.random() < 0.85 else None,
                lieu_faits=f"Quartier fictif {r.randint(1, 40)}, {unite.ville}" if r.random() < 0.8 else None,
                province_code=unite.province_code,
                statut=statut,
                motif_statut="Clôture administrative fictive pour démonstration."
                if statut in (StatutPlainte.CLOTUREE, StatutPlainte.ARCHIVEE)
                else None,
                service_destinataire="Parquet (fictif)" if statut == StatutPlainte.TRANSMISE else None,
                cree_par_id=r.choice(agents).id,
                est_synthetique=True,
            )
        )
    bd.add_all(plaintes)
    for cle, valeur in compteurs.items():
        _fixer_compteur(bd, cle, valeur)
    bd.flush()

    liens = []
    for pl in plaintes:
        choisies = r.sample(personnes, k=r.randint(1, 3))
        roles = [RolePersonne.PLAIGNANT] + [
            r.choice(
                [RolePersonne.MIS_EN_CAUSE, RolePersonne.TEMOIN, RolePersonne.VICTIME, RolePersonne.PERSONNE_CITEE]
            )
            for _ in choisies[1:]
        ]
        for personne, role in zip(choisies, roles, strict=False):
            liens.append(LienPlaintePersonne(plainte_id=pl.id, personne_id=personne.id, role=role))
    bd.add_all(liens)
    liens_par_plainte: dict[str, list[LienPlaintePersonne]] = {}
    for lien in liens:
        liens_par_plainte.setdefault(lien.plainte_id, []).append(lien)
    unites_par_id = {u.id: u for u in liste_unites}

    dossiers = []
    compteurs = {}
    enqueteur = utilisateurs["enqueteur.ndj"]
    for i in range(volumes.dossiers):
        pl = r.choice(plaintes)
        unite = unites_par_id[pl.unite_id]
        ouverture = (pl.recue_le + timedelta(days=r.randint(0, 20))).date()
        ouverture = min(ouverture, date.today())
        cle = f"DO:{unite.code}:{ouverture.year}"
        compteurs[cle] = compteurs.get(cle, _valeur_compteur(bd, cle)) + 1
        statut = r.choices(list(StatutDossier), [20, 40, 15, 20, 5])[0]
        d = Dossier(
            numero=f"DO-{unite.code}-{ouverture.year}-{compteurs[cle]:06d}",
            intitule=f"Procédure fictive relative à la plainte {pl.numero}",
            type_procedure=r.choice(list(TypeProcedure)),
            unite_id=unite.id,
            enqueteur_id=enqueteur.id if unite.code == "CP-NDJ" and i % 2 == 0 else None,
            statut=statut,
            date_ouverture=ouverture,
            date_cloture=date.today() if statut in (StatutDossier.CLOTURE, StatutDossier.ARCHIVE) else None,
            motif_cloture="Clôture fictive." if statut in (StatutDossier.CLOTURE, StatutDossier.ARCHIVE) else None,
            juridiction="Tribunal de grande instance (fictif)" if r.random() < 0.5 else None,
            cree_par_id=createur_defaut.id,
            est_synthetique=True,
        )
        bd.add(d)
        bd.flush()
        bd.add(LienDossierPlainte(dossier_id=d.id, plainte_id=pl.id))
        for lien in liens_par_plainte.get(pl.id, []):
            bd.add(LienDossierPersonne(dossier_id=d.id, personne_id=lien.personne_id, role=lien.role))
        bd.add(
            ActeProcedure(
                dossier_id=d.id,
                type_acte=TypeActe.PROCES_VERBAL,
                reference=f"PV-FICTIF-{i + 1:05d}",
                date_acte=ouverture,
                resume="Procès-verbal fictif de démonstration.",
                redige_par_id=createur_defaut.id,
            )
        )
        dossiers.append(d)
    for cle, valeur in compteurs.items():
        _fixer_compteur(bd, cle, valeur)
    bd.flush()

    compteurs = {}
    for _ in range(volumes.faits):
        pl = r.choice(plaintes)
        unite = unites_par_id[pl.unite_id]
        annee = date.today().year
        cle = f"FT:{unite.code}:{annee}"
        compteurs[cle] = compteurs.get(cle, _valeur_compteur(bd, cle)) + 1
        nature = r.choices(list(NatureInformation), [55, 30, 15, 0])[0]
        f = Fait(
            reference=f"FT-{unite.code}-{annee}-{compteurs[cle]:06d}",
            categorie_id=pl.categorie_id or categories[0].id,
            date_declaree=pl.date_faits,
            lieu=pl.lieu_faits,
            province_code=pl.province_code,
            description="Fait fictif rapporté pour la démonstration.",
            source_information=SourceInformation.PLAINTE,
            nature_information=nature,
            etat_verification=EtatVerification.VERIFIE
            if nature == NatureInformation.FAIT_VERIFIE
            else r.choice([EtatVerification.NON_VERIFIE, EtatVerification.EN_VERIFICATION]),
            unite_id=unite.id,
            plainte_id=pl.id,
            cree_par_id=createur_defaut.id,
            est_synthetique=True,
        )
        bd.add(f)
        bd.flush()
        for lien in liens_par_plainte.get(pl.id, [])[:2]:
            bd.add(LienFaitPersonne(fait_id=f.id, personne_id=lien.personne_id, role=lien.role))
    for cle, valeur in compteurs.items():
        _fixer_compteur(bd, cle, valeur)

    for personne in r.sample(personnes, k=min(volumes.captures, len(personnes))):
        bd.add(
            CaptureBiometrique(
                personne_id=personne.id,
                modalite="EMPREINTE_DIGITALE",
                position_doigt="INDEX_DROIT",
                adaptateur="simulation",
                equipement="Capteur simulé (aucun matériel)",
                collectee_le=maintenant - timedelta(days=r.randint(1, 300)),
                fondement_legal="Fondement juridique fictif (démonstration).",
                consentement_recueilli=True,
                agent_id=createur_defaut.id,
                unite_id=personne.unite_creation_id,
                reference_modele=f"SIM-DEMO-{r.getrandbits(48):012x}",
                qualite=r.randint(60, 99),
                conserver_jusqua=date.today() + timedelta(days=365 * 5),
                statut=StatutCapture.ACTIVE,
                est_synthetique=True,
            )
        )
    bd.flush()
    return {
        "unites": len(liste_unites),
        "utilisateurs": len(utilisateurs),
        "personnes": len(personnes),
        "plaintes": len(plaintes),
        "dossiers": len(dossiers),
        "faits": volumes.faits,
        "captures": volumes.captures,
    }


def _valeur_compteur(bd: SessionBD, cle: str) -> int:
    c = bd.get(Compteur, cle)
    return c.valeur if c else 0


def _fixer_compteur(bd: SessionBD, cle: str, valeur: int) -> None:
    c = bd.get(Compteur, cle)
    if c is None:
        bd.add(Compteur(cle=cle, valeur=valeur))
    else:
        c.valeur = max(c.valeur, valeur)


def code_totp_demo(identifiant: str) -> str:
    return pyotp.TOTP(SECRETS_TOTP_DEMO[identifiant]).now()
