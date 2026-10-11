# Construction du client Windows TPGIS et de son installateur.
# A executer depuis la racine du depot, dans PowerShell, sur Windows 10 ou 11 :
#   powershell -ExecutionPolicy Bypass -File deployment\windows\construire.ps1 -Serveur https://tpgis.institution.td
param(
    [string]$Serveur = "https://tpgis.institution.td",
    [string]$Python = "py -3.12"
)
$ErrorActionPreference = "Stop"

Write-Host "1. Environnement de construction isole"
Invoke-Expression "$Python -m venv .venv-construction"
& .\.venv-construction\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-construction\Scripts\pip.exe install -r requirements-client.txt pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8 altgraph==0.17.5 pefile==2024.8.26 pywin32-ctypes==0.2.3 pytest==9.1.1

Write-Host "2. Tests du client (sans serveur reel)"
& .\.venv-construction\Scripts\python.exe -c "import tpgis.client.main"

Write-Host "3. Executable PyInstaller"
& .\.venv-construction\Scripts\pyinstaller.exe --noconfirm --clean deployment\windows\tpgis_client.spec

Write-Host "4. Installateur Inno Setup"
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 introuvable : installer depuis https://jrsoftware.org/isinfo.php" }
& $iscc "/DServeur=$Serveur" deployment\windows\installateur.iss

Write-Host "5. Empreinte de l'installateur (a publier avec le paquet)"
Get-ChildItem deployment\windows\sortie\*.exe | ForEach-Object { Get-FileHash $_.FullName -Algorithm SHA256 }
