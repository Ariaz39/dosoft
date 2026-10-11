; ============================================================
;  DOSOFT - Script Inno Setup
;  Prerequis : Inno Setup 6+
; ============================================================

#define AppName      "DOSOFT BETA"
#define AppPublisher "Dosoft"
#define AppExeName   "Dosoft_BETA.exe"
#define SourceDir    "dist"
#ifndef AppVersion
  #error AppVersion absent. Compilez avec build_release.ps1, qui transmet /DAppVersion.
#endif

[Setup]
AppId={{C34D9D8E-1B7A-45D4-93D2-7A522E4A5311}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}

; --- Dossier d'installation ---
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; --- Sortie de l'installeur ---
OutputDir=installer_output
OutputBaseFilename=Dosoft_BETA_Setup_v{#AppVersion}

; --- Apparence ---
SetupIconFile=logo.ico
WizardStyle=modern
WizardSizePercent=120

; --- Compression maximale ---
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; --- Droits administrateur obligatoires ---
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=
CloseApplications=yes
; Filter installed resources, not process names. Watching DLLs lets Windows
; Restart Manager detect OBS while the connector module is loaded.
CloseApplicationsFilter=*.exe,*.dll,*.chm
RestartApplications=yes

; --- Divers ---
ShowLanguageDialog=no
LanguageDetectionMethod=uilanguage
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Gestionnaire multi-compte Dofus - {#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktopIcon}"; GroupDescription: "{cm:TaskShortcuts}"
Name: "startmenuicon"; Description: "{cm:TaskStartMenuIcon}"; GroupDescription: "{cm:TaskShortcuts}"
Name: "obsplugin"; Description: "{cm:TaskObsPlugin}"; GroupDescription: "{cm:TaskExtensions}"

[Files]
; --- Executable principal ---
Source: "{#SourceDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; --- Métadonnées utiles au diagnostic et aux mises à jour manuelles ---
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

; --- Connecteur OBS local (option sélectionnée par défaut) ---
; Restart Manager ferme proprement OBS si sa DLL est en cours d'utilisation.
Source: "obs-plugin\dofus-scene-guard.dll"; DestDir: "{commonappdata}\obs-studio\plugins\dofus-scene-guard\bin\64bit"; Flags: ignoreversion; Tasks: obsplugin

[Icons]
; --- Raccourcis ---
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\logo.ico"; Tasks: startmenuicon

Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"; Tasks: startmenuicon

[Run]
; --- Lancement après installation ---
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchNow,{#AppName}}"; Flags: nowait postinstall skipifsilent runascurrentuser

[CustomMessages]
english.TaskDesktopIcon=Create a desktop shortcut
english.TaskStartMenuIcon=Create a Start menu shortcut
english.TaskShortcuts=Shortcuts:
english.TaskObsPlugin=Install the connector for OBS Studio 32
english.TaskExtensions=OBS extension:
english.LaunchNow=Launch %1 now
french.TaskDesktopIcon=Créer un raccourci sur le Bureau
french.TaskStartMenuIcon=Créer un raccourci dans le menu Démarrer
french.TaskShortcuts=Raccourcis :
french.TaskObsPlugin=Installer le connecteur pour OBS Studio 32
french.TaskExtensions=Extension OBS :
french.LaunchNow=Lancer %1 maintenant
spanish.TaskDesktopIcon=Crear un acceso directo en el escritorio
spanish.TaskStartMenuIcon=Crear un acceso directo en el menú Inicio
spanish.TaskShortcuts=Accesos directos:
spanish.TaskObsPlugin=Instalar el conector para OBS Studio 32
spanish.TaskExtensions=Extensión OBS:
spanish.LaunchNow=Iniciar %1 ahora
brazilianportuguese.TaskDesktopIcon=Criar um atalho na área de trabalho
brazilianportuguese.TaskStartMenuIcon=Criar um atalho no menu Iniciar
brazilianportuguese.TaskShortcuts=Atalhos:
brazilianportuguese.TaskObsPlugin=Instalar o conector para OBS Studio 32
brazilianportuguese.TaskExtensions=Extensão OBS:
brazilianportuguese.LaunchNow=Iniciar %1 agora
german.TaskDesktopIcon=Desktop-Verknüpfung erstellen
german.TaskStartMenuIcon=Verknüpfung im Startmenü erstellen
german.TaskShortcuts=Verknüpfungen:
german.TaskObsPlugin=Connector für OBS Studio 32 installieren
german.TaskExtensions=OBS-Erweiterung:
german.LaunchNow=%1 jetzt starten
