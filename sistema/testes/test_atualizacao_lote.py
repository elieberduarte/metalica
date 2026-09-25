# -*- coding: utf-8 -*-
"""O .cmd da atualização roda de verdade num caminho com acento (usuário "José"): o
instalador é chamado com os argumentos do modo silencioso, apagado depois, e o programa
reaberto. No lugar do instalador e do programa entra um executável mínimo, compilado na
hora pelo csc do .NET Framework, que anota o próprio caminho e os argumentos."""
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSC = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Microsoft.NET", "Framework64", "v4.0.30319", "csc.exe")

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not os.path.exists(CSC),
                                reason="só no Windows com o .NET Framework (csc)")

MARCADOR = r"""
using System; using System.IO; using System.Text;
class P { static void Main(string[] a) {
  string eu = System.Reflection.Assembly.GetExecutingAssembly().Location;
  File.AppendAllText(Path.Combine(Path.GetDirectoryName(eu), "marca.txt"),
                     Path.GetFileName(eu) + "|" + string.Join(" ", a) + "\n", new UTF8Encoding(false));
} }
"""


def _compilar(destino):
    fonte = destino + ".cs"
    with open(fonte, "w", encoding="utf-8") as f:
        f.write(MARCADOR)
    subprocess.run([CSC, "/nologo", "/target:winexe", "/out:" + destino, fonte], check=True, capture_output=True)


def test_lote_da_atualizacao_com_acento_no_caminho(tmp_path):
    import app
    pasta = tmp_path / "José Ação" / "Metálica"
    pasta.mkdir(parents=True)
    base = str(tmp_path / "marcador.exe")
    _compilar(base)
    instalador = str(pasta / "Metalica-9.9.9-instalador-1.exe")
    programa = str(pasta / "Metálica-programa.exe")
    for destino in (instalador, programa):
        with open(base, "rb") as f, open(destino, "wb") as g:
            g.write(f.read())
    lote = app.gravar_lote_de_atualizacao(str(pasta / "metalica-atualizar.cmd"), instalador, programa, espera=0)
    with open(lote, "rb") as f:
        bruto = f.read()
    assert b"chcp 65001" in bruto and "José Ação".encode("utf-8") in bruto      # UTF-8 no disco
    subprocess.run(["cmd.exe", "/c", lote], check=False, capture_output=True, timeout=60)
    marca = pasta / "marca.txt"
    t0 = time.time()
    while time.time() - t0 < 15:                          # o "start" reabre sem esperar
        if marca.exists() and "Metálica-programa.exe" in marca.read_text(encoding="utf-8"):
            break
        time.sleep(0.3)
    assert marca.exists(), "o .cmd não chamou nada: caminho com acento lido na página de código errada"
    linhas = marca.read_text(encoding="utf-8").splitlines()
    assert "Metalica-9.9.9-instalador-1.exe|/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS" in linhas
    assert any(l.startswith("Metálica-programa.exe|") for l in linhas), linhas     # reaberto
    assert not os.path.exists(instalador)                                            # apagado
