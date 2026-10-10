#!/usr/bin/env bash
# Sauvegarde chiffree, verification, rotation locale et copie hors site.
# La copie hors site (DESTINATION_HORS_SITE) doit viser un stockage protege
# contre la modification (support WORM, coffre de sauvegarde, copie hors ligne).
set -euo pipefail
ADMIN=/opt/tpgis/venv/bin/tpgis-admin
RETENTION_LOCALE_JOURS="${RETENTION_LOCALE_JOURS:-14}"

sortie=$("$ADMIN" sauvegarder)
dossier=$(echo "$sortie" | sed -n 's/^Sauvegarde créée : //p')
"$ADMIN" verifier-sauvegarde "$dossier"
"$ADMIN" verifier-audit

if [[ -n "${DESTINATION_HORS_SITE:-}" ]]; then
    rsync -a --chmod=D500,F400 "$dossier" "$DESTINATION_HORS_SITE/"
fi

find "$TPGIS_REPERTOIRE_SAUVEGARDES" -maxdepth 1 -type d -name 'tpgis_sauvegarde_*' \
     -mtime "+$RETENTION_LOCALE_JOURS" -exec chmod -R u+w {} \; -exec rm -rf {} +
echo "Sauvegarde terminée et vérifiée : $dossier"
