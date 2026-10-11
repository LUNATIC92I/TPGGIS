# -*- mode: python ; coding: utf-8 -*-
# Construction du client de bureau TPGIS avec PyInstaller.
# Usage (depuis la racine du depot) : pyinstaller deployment/windows/tpgis_client.spec
# Le client n'embarque aucun composant serveur ni pilote de base de donnees.
import importlib.util
from pathlib import Path

RACINE = Path(SPECPATH).resolve().parents[1]

# Extensions Qt indispensables (affichage Windows, styles, images, SVG, TLS).
# Elles sont collectees explicitement, sans dependre de l'import de QtCore par
# le crochet PyInstaller : le resultat reste correct meme si cet import echoue
# sur le poste de construction.
PYSIDE6 = Path(importlib.util.find_spec("PySide6").submodule_search_locations[0])
EXTENSIONS_QT = ["platforms", "styles", "imageformats", "iconengines", "tls"]
binaires_qt = []
for base in (PYSIDE6 / "plugins", PYSIDE6 / "Qt" / "plugins"):
    for nom in EXTENSIONS_QT:
        for fichier in (base / nom).glob("*"):
            if fichier.suffix.lower() in (".dll", ".so", ".dylib") and "qpdf" not in fichier.name.lower():
                binaires_qt.append((str(fichier), str(fichier.parent.relative_to(PYSIDE6.parent))))

a = Analysis(
    [str(RACINE / "tpgis" / "client" / "main.py")],
    pathex=[str(RACINE)],
    binaries=binaires_qt,
    datas=[
        (str(RACINE / "tpgis" / "client" / "resources"), "tpgis/client/resources"),
        (str(RACINE / "tpgis" / "shared" / "geodata"), "tpgis/shared/geodata"),
    ],
    hiddenimports=["PySide6.QtSvg"],
    excludes=[
        "tpgis.server", "sqlalchemy", "alembic", "psycopg", "fastapi", "starlette", "uvicorn",
        "argon2", "pyotp", "reportlab", "cryptography", "tkinter", "PySide6.QtWebEngineCore",
        "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TPGIS",
    console=False,
    icon=str(RACINE / "tpgis" / "client" / "resources" / "icons" / "tpgis.ico"),
    version=str(RACINE / "deployment" / "windows" / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="TPGIS")
