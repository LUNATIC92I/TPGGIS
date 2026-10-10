# Demonstration locale sous Windows : serveur TLS local et client de bureau.
# A executer depuis la racine du depot apres : py -3.12 -m pip install -r requirements.txt
$ErrorActionPreference = "Stop"
$env:TPGIS_ENVIRONNEMENT = "demonstration"
$env:TPGIS_DATABASE_URL = "sqlite:///./var/demo/tpgis_demo.sqlite3"
$env:TPGIS_REPERTOIRE_STOCKAGE = "./var/demo/stockage"
$env:TPGIS_REPERTOIRE_SAUVEGARDES = "./var/demo/sauvegardes"
$env:TPGIS_TLS_CERTIFICAT = "./var/tls/serveur.crt"
$env:TPGIS_TLS_CLE = "./var/tls/serveur.key"
$env:TPGIS_HOTE = "127.0.0.1"
$env:TPGIS_PORT = "8443"
if (-not (Test-Path var\tls\serveur.crt)) { py -3.12 scripts\generer_certificats_demo.py var\tls }
if (-not (Test-Path var\demo\tpgis_demo.sqlite3)) {
    New-Item -ItemType Directory -Force var\demo | Out-Null
    py -3.12 -m tpgis.server.cli charger-demonstration
}
$serveur = Start-Process py -ArgumentList "-3.12", "-m", "tpgis.server.main" -PassThru -NoNewWindow
Start-Sleep -Seconds 4
py -3.12 -m tpgis.server.cli codes-demo
$env:TPGIS_CLIENT_URL = "https://127.0.0.1:8443"
$env:TPGIS_CLIENT_CA = "./var/tls/ac_demo.crt"
py -3.12 -m tpgis.client.main
Stop-Process -Id $serveur.Id
