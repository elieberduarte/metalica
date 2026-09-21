# -*- coding: utf-8 -*-
"""Gera o programa instalável do Metálica.

    python empacotar/construir.py              # executável + instalador
    python empacotar/construir.py --sem-instalador

Passos:
  1. calcula a impressão digital do núcleo de cálculo e grava `impressao_nucleo.txt`,
     porque no executável os fontes não existem mais para calcular na hora;
  2. roda o PyInstaller sobre `sistema/app.py`, em pasta (onedir) e sem console,
     levando junto o que não é código: `web/`, `dados/perfis.json`, `saida/memorial.css`.
     Os módulos acham esses arquivos por caminho relativo ao próprio `__file__`, então
     basta repetir a estrutura de pastas dentro do pacote;
  3. compila o instalador com o Inno Setup (`instalador.iss`).

Saídas: `empacotar/dist/Metalica/Metalica.exe` e
`empacotar/saida/Metalica-<versão>-instalador.exe`.

Requisitos: `pip install pyinstaller` e o Inno Setup 6 (winget install JRSoftware.InnoSetup).
O nome do executável vai sem acento de propósito: atalho e pasta de instalação com
acento dão problema em scripts e em alguns antivírus.
"""
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SISTEMA = os.path.join(RAIZ, "sistema")
sys.path.insert(0, SISTEMA)

import versao                                   # noqa: E402

GERADO = os.path.join(AQUI, "_gerado")
DIST = os.path.join(AQUI, "dist")
TRABALHO = os.path.join(AQUI, "build")
SAIDA = os.path.join(AQUI, "saida")

ISCC = [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe"]


def impressao() -> str:
    os.makedirs(GERADO, exist_ok=True)
    valor = versao.calcular_impressao(os.path.join(SISTEMA, "nucleo"))
    with open(os.path.join(GERADO, versao.ARQUIVO_IMPRESSAO), "w", encoding="utf-8") as f:
        f.write(valor + "\n")
    return valor


def executavel():
    dados = [
        (os.path.join(SISTEMA, "web"), "web"),
        (os.path.join(SISTEMA, "dados", "perfis.json"), "dados"),
        (os.path.join(SISTEMA, "saida", "memorial.css"), "saida"),
        # a paginação do memorial e da lista em PDF: no desenvolvimento o sistema a
        # acha na pasta do manual, que não vai no pacote; aqui entra em saida/lib,
        # o primeiro lugar onde saida/printpdf.py procura
        (os.path.join(RAIZ, "manual", "lib", "paged.polyfill.js"), os.path.join("saida", "lib")),
        (os.path.join(GERADO, versao.ARQUIVO_IMPRESSAO), "."),
    ]
    for origem, _ in dados:
        if not os.path.exists(origem):
            raise SystemExit("recurso do pacote não encontrado: " + origem)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--name", "Metalica", "--windowed", "--onedir",
           "--distpath", DIST, "--workpath", TRABALHO, "--specpath", TRABALHO,
           "--paths", SISTEMA,
           # importados dentro de funções (o servidor só carrega o que a rota pede)
           "--collect-submodules", "nucleo", "--collect-submodules", "nucleo3d",
           "--collect-submodules", "saida", "--collect-submodules", "ifc",
           "--hidden-import", "versao",
           # o matplotlib só desenha em arquivo (Agg): interface gráfica e testes ficam fora
           "--exclude-module", "tkinter", "--exclude-module", "pytest",
           "--exclude-module", "IPython", "--exclude-module", "PyQt5",
           "--exclude-module", "PyQt6", "--exclude-module", "PySide6"]
    icone = os.path.join(AQUI, "metalica.ico")
    if os.path.exists(icone):
        cmd += ["--icon", icone]
    for origem, destino in dados:
        cmd += ["--add-data", f"{origem}{os.pathsep}{destino}"]
    cmd.append(os.path.join(SISTEMA, "app.py"))
    print(">", " ".join(f'"{c}"' if " " in c else c for c in cmd[:12]), "...")
    subprocess.run(cmd, check=True, cwd=SISTEMA)
    exe = os.path.join(DIST, "Metalica", "Metalica.exe")
    if not os.path.exists(exe):
        raise SystemExit("o PyInstaller terminou sem gerar " + exe)
    return exe


def instalador():
    iscc = next((c for c in ISCC if os.path.exists(c)), None)
    if not iscc:
        print("Inno Setup não encontrado: instalador não gerado "
              "(winget install JRSoftware.InnoSetup).")
        return None
    os.makedirs(SAIDA, exist_ok=True)
    subprocess.run([iscc, f"/DVersao={versao.VERSAO}", f"/DOrigem={os.path.join(DIST, 'Metalica')}",
                    f"/DSaida={SAIDA}", os.path.join(AQUI, "instalador.iss")], check=True)
    return os.path.join(SAIDA, f"Metalica-{versao.VERSAO}-instalador.exe")


def tamanho_mb(caminho: str) -> float:
    if os.path.isfile(caminho):
        return os.path.getsize(caminho) / 1048576
    total = 0
    for pasta, _, arquivos in os.walk(caminho):
        total += sum(os.path.getsize(os.path.join(pasta, a)) for a in arquivos)
    return total / 1048576


def main():
    for pasta in (os.path.join(DIST, "Metalica"), TRABALHO):
        shutil.rmtree(pasta, ignore_errors=True)
    print(f"{versao.NOME} {versao.VERSAO} — núcleo {impressao()[:12]}")
    exe = executavel()
    print(f"executável: {exe}  ({tamanho_mb(os.path.dirname(exe)):.0f} MB na pasta)")
    if "--sem-instalador" not in sys.argv:
        inst = instalador()
        if inst and os.path.exists(inst):
            print(f"instalador: {inst}  ({tamanho_mb(inst):.0f} MB)")


if __name__ == "__main__":
    main()
