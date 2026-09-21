; Instalador do Metálica (Inno Setup 6). Chamado por construir.py, que passa
; /DVersao, /DOrigem (a pasta gerada pelo PyInstaller) e /DSaida.
;
; Instala por usuário, sem pedir senha de administrador: em escritório de engenharia o
; usuário raramente é administrador da própria máquina. Quem for pode escolher "para
; todos os usuários" na primeira tela. Os projetos nunca ficam aqui: o programa grava
; em Documentos\Metálica, que sobrevive à desinstalação.

#ifndef Versao
  #define Versao "0.0.0"
#endif
#ifndef Origem
  #define Origem "dist\Metalica"
#endif
#ifndef Saida
  #define Saida "saida"
#endif

[Setup]
AppId={{6F3B1C5E-8D2A-4E47-9B61-3A7C0D5E2F14}
AppName=Metálica
AppVersion={#Versao}
AppPublisher=Vizin
AppComments=Dimensionamento e detalhamento de estruturas metálicas
DefaultDirName={autopf}\Metalica
DefaultGroupName=Metálica
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#Saida}
OutputBaseFilename=Metalica-{#Versao}-instalador
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=Metálica {#Versao}
UninstallDisplayIcon={app}\Metalica.exe
CloseApplications=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "{#Origem}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Metálica"; Filename: "{app}\Metalica.exe"
Name: "{group}\Desinstalar o Metálica"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Metálica"; Filename: "{app}\Metalica.exe"; Tasks: atalho

[Run]
Filename: "{app}\Metalica.exe"; Description: "Abrir o Metálica agora"; Flags: nowait postinstall skipifsilent
