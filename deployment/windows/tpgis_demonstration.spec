# -*- mode: python ; coding: utf-8 -*-
# Executable autonome de DEMONSTRATION : un seul fichier, lance d'un double clic.
# Usage (depuis la racine du depot) : pyinstaller deployment/windows/tpgis_demonstration.spec
#
# Contrairement au client de production (tpgis_client.spec), cet executable
# embarque le serveur TPGIS, SQLite et le jeu de donnees fictif : il demarre
# un serveur HTTPS sur 127.0.0.1 puis ouvre le client. Il ne se connecte a
# aucun serveur institutionnel et ne doit jamais recevoir de donnees reelles.
import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RACINE = Path(SPECPATH).resolve().parents[1]

PYSIDE6 = Path(importlib.util.find_spec("PySide6").submodule_search_locations[0])
EXTENSIONS_QT = ["platforms", "styles", "imageformats", "iconengines", "tls"]
binaires_qt = []
for base in (PYSIDE6 / "plugins", PYSIDE6 / "Qt" / "plugins"):
    for nom in EXTENSIONS_QT:
        for fichier in (base / nom).glob("*"):
            if fichier.suffix.lower() in (".dll", ".so", ".dylib") and "qpdf" not in fichier.name.lower():
                binaires_qt.append((str(fichier), str(fichier.parent.relative_to(PYSIDE6.parent))))

a = Analysis(
    [str(RACINE / "deployment" / "windows" / "lanceur_demonstration.py")],
    pathex=[str(RACINE)],
    binaries=binaires_qt,
    datas=[
        (str(RACINE / "tpgis" / "client" / "resources"), "tpgis/client/resources"),
        (str(RACINE / "tpgis" / "shared" / "geodata"), "tpgis/shared/geodata"),
    ]
    # Alembic lit les scripts de migration sur le disque (sources uniquement, sans cache).
    + [
        (str(f), str(f.parent.relative_to(RACINE)))
        for f in (RACINE / "tpgis" / "server" / "database" / "migrations").rglob("*")
        if f.suffix in (".py", ".mako") and "__pycache__" not in f.parts
    ]
    + collect_data_files("reportlab"),
    hiddenimports=["PySide6.QtSvg"]
    + collect_submodules("tpgis")
    + collect_submodules("uvicorn")
    + collect_submodules("alembic", filter=lambda nom: ".testing" not in nom)
    + ["sqlalchemy.dialects.sqlite", "argon2", "pyotp", "multipart"],
    excludes=[
        "psycopg", "psycopg_binary", "uvloop", "tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore",
        "PySide6.QtQuick", "PySide6.QtQml", "pytest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TPGIS_Demonstration",
    console=False,
    upx=False,
    icon=str(RACINE / "tpgis" / "client" / "resources" / "icons" / "tpgis.ico"),
    version=str(RACINE / "deployment" / "windows" / "version_info_demonstration.txt"),
)
