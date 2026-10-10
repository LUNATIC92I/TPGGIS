"""Genere une autorite de certification et un certificat serveur de DEMONSTRATION.

Usage : python scripts/generer_certificats_demo.py var/tls

Produit ac_demo.crt (a fournir au client), serveur.crt et serveur.key (pour
le serveur). Ces certificats ne doivent jamais etre utilises en production :
la production utilise les certificats emis par l'infrastructure de gestion
de cles de l'institution.
"""

from __future__ import annotations

import ipaddress
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _nom(cn: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "TD"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TPGIS DEMONSTRATION"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ]
    )


def generer(cible: Path) -> None:
    cible.mkdir(parents=True, exist_ok=True)
    maintenant = datetime.now(UTC)
    cle_ac = ec.generate_private_key(ec.SECP256R1())
    ac = (
        x509.CertificateBuilder()
        .subject_name(_nom("AC de demonstration TPGIS"))
        .issuer_name(_nom("AC de demonstration TPGIS"))
        .public_key(cle_ac.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - timedelta(minutes=5))
        .not_valid_after(maintenant + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(cle_ac.public_key()), critical=False)
        .sign(cle_ac, hashes.SHA256())
    )
    cle_srv = ec.generate_private_key(ec.SECP256R1())
    srv = (
        x509.CertificateBuilder()
        .subject_name(_nom("localhost"))
        .issuer_name(ac.subject)
        .public_key(cle_srv.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - timedelta(minutes=5))
        .not_valid_after(maintenant + timedelta(days=90))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(cle_ac.public_key()), critical=False)
        .sign(cle_ac, hashes.SHA256())
    )
    (cible / "ac_demo.crt").write_bytes(ac.public_bytes(serialization.Encoding.PEM))
    (cible / "serveur.crt").write_bytes(srv.public_bytes(serialization.Encoding.PEM))
    cle = cible / "serveur.key"
    cle.write_bytes(
        cle_srv.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    os.chmod(cle, 0o600)
    print(f"Certificats de démonstration écrits dans {cible}")


if __name__ == "__main__":
    generer(Path(sys.argv[1] if len(sys.argv) > 1 else "var/tls"))
