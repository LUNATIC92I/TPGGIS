# Construction de l'executable autonome de DEMONSTRATION (TPGIS_Demonstration.exe).
# A executer depuis la racine du depot, dans PowerShell, sur Windows 10 ou 11 :
#   powershell -ExecutionPolicy Bypass -File deployment\windows\construire_demonstration.ps1
# Resultat : dist\TPGIS_Demonstration.exe, un seul fichier a lancer d'un double clic.
param([string]$Python = "py -3.12")
$ErrorActionPreference = "Stop"

Write-Host "1. Environnement de construction isole"
Invoke-Expression "$Python -m venv .venv-demonstration"
& .\.venv-demonstration\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-demonstration\Scripts\pip.exe install -r requirements-client.txt -r requirements-serveur.txt pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8 pytest==9.1.1

Write-Host "2. Test du lanceur (serveur local TLS, connexion assistee)"
$env:QT_QPA_PLATFORM = "offscreen"
& .\.venv-demonstration\Scripts\python.exe -m pytest tests\client\test_demonstration_autonome.py
Remove-Item Env:\QT_QPA_PLATFORM

Write-Host "3. Executable PyInstaller (un seul fichier)"
& .\.venv-demonstration\Scripts\pyinstaller.exe --noconfirm --clean deployment\windows\tpgis_demonstration.spec

Write-Host "4. Empreinte de l'executable"
Get-FileHash dist\TPGIS_Demonstration.exe -Algorithm SHA256
