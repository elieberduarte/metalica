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
AppPublisher=Elieber
AppComments=Dimensionamento e detalhamento de estruturas metálicas
DefaultDirName={autopf}\Metalica
DefaultGroupName=Metálica
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#Saida}
; nome sem a versão de propósito: é sempre o mesmo arquivo, sobrescrito a cada
; build, para não acumular um instalador de 30 MB por versão na pasta (e no OneDrive)
OutputBaseFilename=Metalica-instalador
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
; instalação silenciosa (atualização de dentro do programa): reabre o programa sozinho
Filename: "{app}\Metalica.exe"; Flags: nowait; Check: WizardSilent

[Code]
// O link de instalação (21/10/2026, o usuário: "um link direto para enviar para o usuário baixar o sistema já com a
// chave ativada"): o instalador baixado pelo convite vem com a chave no nome ("Metalica-instalador MTL-XXXX-XXXX-XXXX.exe",
// servicos/licencas/src/api.js); ele a grava em %LOCALAPPDATA%\Metálica\convite.txt e o Metálica se ativa sozinho na
// primeira abertura (sistema/licenca.py, ativar_pelo_convite). Sem a chave no nome (a atualização de dentro do
// programa), nada muda.
function ChaveDoNome(Nome: String): String;
var
  I, J: Integer;
  C: Char;
  S: String;
begin
  Result := '';
  S := Uppercase(Nome);
  I := Pos('MTL-', S);
  if I = 0 then Exit;
  S := Copy(S, I, 18);
  if Length(S) <> 18 then Exit;
  for J := 1 to 18 do begin
    C := S[J];
    if (J = 4) or (J = 9) or (J = 14) then begin
      if C <> '-' then Exit;
    end else if J > 4 then begin
      if not (((C >= 'A') and (C <= 'Z')) or ((C >= '0') and (C <= '9'))) then Exit;
    end;
  end;
  Result := S;
end;

function PastaDoConvite(): String;
begin
  #ifdef PastaConvite
  Result := '{#PastaConvite}';
  #else
  // a pasta do Metálica em %LOCALAPPDATA% (a mesma da licença); o "á" por código, sem depender da codificação do .iss
  Result := ExpandConstant('{localappdata}') + '\Met' + Chr(225) + 'lica';
  #endif
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Chave, Pasta: String;
begin
  if CurStep = ssPostInstall then begin
    Chave := ChaveDoNome(ExtractFileName(ExpandConstant('{srcexe}')));
    if Chave <> '' then begin
      Pasta := PastaDoConvite();
      ForceDirectories(Pasta);
      SaveStringToFile(Pasta + '\convite.txt', Chave, False);
    end;
  end;
end;
