#!/usr/bin/env bash
# Demonstration locale complete : serveur TLS sur 127.0.0.1:8443 avec donnees
# synthetiques, puis client de bureau. Environnement "demonstration" separe de
# la production (base, cles et stockage distincts dans var/demo).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
export TPGIS_ENVIRONNEMENT=demonstration
export TPGIS_DATABASE_URL="sqlite:///./var/demo/tpgis_demo.sqlite3"
export TPGIS_REPERTOIRE_STOCKAGE=./var/demo/stockage
export TPGIS_REPERTOIRE_SAUVEGARDES=./var/demo/sauvegardes
export TPGIS_TLS_CERTIFICAT=./var/tls/serveur.crt
export TPGIS_TLS_CLE=./var/tls/serveur.key
export TPGIS_HOTE=127.0.0.1 TPGIS_PORT=8443

[[ -f var/tls/serveur.crt ]] || "$PY" scripts/generer_certificats_demo.py var/tls
if [[ ! -f var/demo/tpgis_demo.sqlite3 ]]; then
    mkdir -p var/demo
    "$PY" -m tpgis.server.cli charger-demonstration
fi
"$PY" -m tpgis.server.main &
SERVEUR=$!
trap 'kill $SERVEUR' EXIT
sleep 3
echo "Codes MFA de démonstration :"
"$PY" -m tpgis.server.cli codes-demo
TPGIS_CLIENT_URL=https://127.0.0.1:8443 TPGIS_CLIENT_CA=./var/tls/ac_demo.crt "$PY" -m tpgis.client.main
