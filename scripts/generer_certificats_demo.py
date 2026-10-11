"""Genere une autorite de certification et un certificat serveur de DEMONSTRATION.

Usage : python scripts/generer_certificats_demo.py var/tls

Produit ac_demo.crt (a fournir au client), serveur.crt et serveur.key (pour
le serveur). Ces certificats ne doivent jamais etre utilises en production.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tpgis.server.security.certificats_demo import generer  # noqa: E402

if __name__ == "__main__":
    cible = Path(sys.argv[1] if len(sys.argv) > 1 else "var/tls")
    generer(cible)
    print(f"Certificats de démonstration écrits dans {cible}")
