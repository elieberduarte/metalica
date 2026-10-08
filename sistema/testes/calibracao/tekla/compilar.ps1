# Compila a ponte com o Tekla (TeklaPonte.cs) com o csc do .NET Framework 4 do Windows, sem instalar nada.
# Saida: %LOCALAPPDATA%\Metalica-ferramentas\tekla\TeklaPonte.exe (fora do repositorio).
# As DLLs do Tekla 2026 sao .NET Standard 2.0: a fachada netstandard.dll do GAC entra como referencia.
$ErrorActionPreference = "Stop"
$bin = "C:\Program Files\Tekla Structures\2026.0\bin"
$net48 = Join-Path $bin "Net48Runtime"
$destino = Join-Path $env:LOCALAPPDATA "Metalica-ferramentas\tekla"
New-Item -ItemType Directory -Force $destino | Out-Null
$fx = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319"
$netstd = "C:\Windows\Microsoft.NET\assembly\GAC_MSIL\netstandard\v4.0_2.0.0.0__cc7b13ffcd2ddd51\netstandard.dll"
$refs = @("$bin\Tekla.Structures.Model.dll", "$net48\Tekla.Structures.dll", "$bin\Tekla.Structures.Catalogs.dll",
          "$bin\Tekla.Structures.Datatype.dll", "$bin\Tekla.Structures.Analysis.dll", "$fx\System.Web.Extensions.dll", $netstd)
$argumentos = @("/nologo", "/target:exe", "/platform:x64", "/codepage:65001", "/out:$destino\TeklaPonte.exe") + ($refs | ForEach-Object { "/reference:$_" }) + @("$PSScriptRoot\TeklaPonte.cs")
& "$fx\csc.exe" @argumentos
if ($LASTEXITCODE -ne 0) { throw "falhou a compilacao" }
"compilado: $destino\TeklaPonte.exe"
