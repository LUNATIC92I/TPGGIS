# -*- mode: python ; coding: utf-8 -*-
# Construction du client de bureau TPGIS avec PyInstaller.
# Usage (depuis la racine du depot) : pyinstaller deployment/windows/tpgis_client.spec
# Le client n'embarque aucun composant serveur ni pilote de base de donnees.
from pathlib import Path

RACINE = Path(SPECPATH).resolve().parents[1]

a = Analysis(
    [str(RACINE / "tpgis" / "client" / "main.py")],
    pathex=[str(RACINE)],
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
