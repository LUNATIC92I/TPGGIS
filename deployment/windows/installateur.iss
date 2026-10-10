; Installateur Windows du client TPGIS (Inno Setup 6).
; Compilation : iscc /DServeur=https://tpgis.institution.td deployment\windows\installateur.iss
; Prerequis : dossier dist\TPGIS produit par PyInstaller.

#ifndef Serveur
  #define Serveur "https://tpgis.institution.td"
#endif
#define NomApp "TPGIS"
#define VersionApp "0.1.0"

[Setup]
AppId={{6F5E3C1A-7D42-4B8E-9A61-2C7B0E5D9F13}
AppName={#NomApp}
AppVersion={#VersionApp}
AppVerName=TPGIS {#VersionApp}
AppPublisher=Institution habilitée
DefaultDirName={autopf}\TPGIS
DefaultGroupName=TPGIS
DisableProgramGroupPage=yes
OutputDir=sortie
OutputBaseFilename=TPGIS_Client_{#VersionApp}_Installation
SetupIconFile=..\..\tpgis\client\resources\icons\tpgis.ico
UninstallDisplayIcon={app}\TPGIS.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Signature de code (a activer avec le certificat de l'institution) :
; SignTool=signtool sign /fd sha256 /tr http://horodatage.institution.td /td sha256 /f "$qcert.pfx$q" $f

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\..\dist\TPGIS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "client.ini.modele"; DestDir: "{app}"; DestName: "client.ini"; Flags: onlyifdoesntexist uninsneveruninstall

[INI]
Filename: "{app}\client.ini"; Section: "serveur"; Key: "url"; String: "{#Serveur}"; Flags: createkeyifdoesntexist

[Icons]
Name: "{group}\TPGIS"; Filename: "{app}\TPGIS.exe"
Name: "{group}\Désinstaller TPGIS"; Filename: "{uninstallexe}"
Name: "{autodesktop}\TPGIS"; Filename: "{app}\TPGIS.exe"; Tasks: bureau

[Run]
Filename: "{app}\TPGIS.exe"; Description: "Lancer TPGIS"; Flags: nowait postinstall skipifsilent
