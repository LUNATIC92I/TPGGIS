#!/usr/bin/env bash
# Installation du serveur TPGIS sur Debian 12 ou Ubuntu 24.04 (a executer en root).
# Le script est idempotent. Il ne genere ni ne stocke aucun secret de production :
# le fichier /etc/tpgis/tpgis.env doit etre complete a partir du coffre de secrets.
set -euo pipefail
SOURCE="$(cd "$(dirname "$0")/../.." && pwd)"

apt-get update
apt-get install -y python3 python3-venv postgresql nginx clamav-daemon rsync

id tpgis >/dev/null 2>&1 || useradd --system --home /opt/tpgis --shell /usr/sbin/nologin tpgis
install -d -o tpgis -g tpgis -m 0750 /opt/tpgis /opt/tpgis/var
install -d -o tpgis -g tpgis -m 0700 /var/lib/tpgis /var/lib/tpgis/stockage /var/backups/tpgis
install -d -o root -g tpgis -m 0750 /etc/tpgis /etc/tpgis/tls

rsync -a --delete --exclude '.git' --exclude 'var' "$SOURCE/" /opt/tpgis/
chown -R tpgis:tpgis /opt/tpgis
sudo -u tpgis python3 -m venv /opt/tpgis/venv
sudo -u tpgis /opt/tpgis/venv/bin/pip install --no-cache-dir -r /opt/tpgis/requirements-serveur.txt
sudo -u tpgis /opt/tpgis/venv/bin/pip install --no-cache-dir --no-deps /opt/tpgis

if [[ ! -f /etc/tpgis/tpgis.env ]]; then
    install -o root -g tpgis -m 0640 /opt/tpgis/.env.example /etc/tpgis/tpgis.env
    echo "ATTENTION : completer /etc/tpgis/tpgis.env avec les secrets du coffre avant le demarrage."
fi

usermod -aG clamav tpgis || true
install -m 0644 /opt/tpgis/deployment/server/tpgis-serveur.service /etc/systemd/system/
install -m 0644 /opt/tpgis/deployment/server/tpgis-sauvegarde.service /etc/systemd/system/
install -m 0644 /opt/tpgis/deployment/server/tpgis-sauvegarde.timer /etc/systemd/system/
install -m 0644 /opt/tpgis/deployment/server/nginx-tpgis.conf /etc/nginx/sites-available/tpgis
ln -sf /etc/nginx/sites-available/tpgis /etc/nginx/sites-enabled/tpgis
systemctl daemon-reload
echo "Installation terminée. Étapes suivantes : base PostgreSQL, secrets, certificats TLS, puis :"
echo "  sudo -u tpgis env \$(cat /etc/tpgis/tpgis.env | xargs) /opt/tpgis/venv/bin/tpgis-admin initialiser"
echo "  systemctl enable --now tpgis-serveur tpgis-sauvegarde.timer && systemctl reload nginx"
