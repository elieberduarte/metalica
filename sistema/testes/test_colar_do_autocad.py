"""Colar no CAD 2D o que foi copiado no AutoCAD (usuário, 23/10: "criar a funcionalidade de copiar elementos de dentro
do autocad e colar na nossa área 2D") — nucleo2d/do_autocad.py e a rota colar-autocad.

O Ctrl+C do AutoCAD deixa na área de transferência o ClipboardInfo (o caminho do A$C….DWG e o ponto de base) e o DWG
na pasta Temp; o servidor converte o DWG pelo accoreconsole do AutoCAD instalado. A área de transferência é simulada
(o teste não mexe na do usuário); a conversão é a de verdade quando o AutoCAD está na máquina. dados_cad/
amostra_autocad.dwg: um retângulo, uma linha, um furo e o texto "CH1" na camada "PECA CIANO", em mm, em x ≈ 50 m."""
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo.base import ErroDeDados  # noqa: E402
from nucleo2d import do_autocad  # noqa: E402

AMOSTRA = os.path.join(os.path.dirname(__file__), "dados_cad", "amostra_autocad.dwg")


def _clipboard_info(caminho, base, origem=r"C:\obras\ORTOBIO FERNANDO.dwg"):
    """o ClipboardInfo do ObjectARX: szTempFile e szSourceFile (MAX_PATH em UTF-16), szSignature, nFlags, dptInsert"""
    cam = lambda t: t.encode("utf-16-le").ljust(2 * do_autocad.MAX_PATH, b"\0")   # noqa: E731
    return cam(caminho) + cam(origem) + "R15".encode("utf-16-le").ljust(8, b"\0") + struct.pack("<i", 0) + b"\0" * 4 + \
        struct.pack("<3d", *base, 0.0) + b"\0" * 64


def test_le_o_caminho_e_o_ponto_de_base():
    c, b = do_autocad.ler_clipboard_info(_clipboard_info(r"C:\Users\x\AppData\Local\Temp\A$C1F2E3D4C.DWG", (50000.0, 20000.0)))
    assert c.endswith("A$C1F2E3D4C.DWG") and b == (50000.0, 20000.0)
    # outra estrutura: o caminho achado nos bytes, sem ponto de base de confiança
    c, _b = do_autocad.ler_clipboard_info(b"\x01\x02lixo" + r"D:\tmp\A$C77.dwg".encode("utf-16-le") + b"\0" * 8)
    assert c == r"D:\tmp\A$C77.dwg"


def test_o_que_colar(monkeypatch, tmp_path):
    dwg = tmp_path / "A$C123.DWG"
    dwg.write_bytes(b"x")
    monkeypatch.setattr(do_autocad, "conteudo", lambda: {"formatos": ["AutoCAD.r25", "imagem"], "arquivos": [],
                                                          "autocad": {"formato": "AutoCAD.r25", "bytes": _clipboard_info(str(dwg), (1.0, 2.0))}})
    o = do_autocad.o_que_colar()
    assert o["tipo"] == "dwg" and o["caminho"] == str(dwg) and o["base"] == (1.0, 2.0) and "AutoCAD" in o["origem"]
    # o DXF copiado no Explorer
    dxf = tmp_path / "planta.dxf"
    dxf.write_text("0\nEOF\n")
    monkeypatch.setattr(do_autocad, "conteudo", lambda: {"formatos": ["arquivos"], "arquivos": [str(tmp_path / "a.zip"), str(dxf)], "autocad": None})
    o = do_autocad.o_que_colar()
    assert o["tipo"] == "dxf" and o["caminho"] == str(dxf)
    # só a imagem do print: diz o que tem e o que fazer
    monkeypatch.setattr(do_autocad, "conteudo", lambda: {"formatos": ["imagem", "PNG"], "arquivos": [], "autocad": None})
    with pytest.raises(ErroDeDados) as e:
        do_autocad.o_que_colar()
    assert "não tem objetos do AutoCAD" in str(e.value) and "imagem" in str(e.value) and "Ctrl+C" in str(e.value)


@pytest.mark.skipif(do_autocad.accoreconsole() is None, reason="sem o AutoCAD instalado")
def test_colar_de_verdade_pelo_autocad_sem_janela(monkeypatch, tmp_path):
    import shutil
    import app
    temp = tmp_path / "A$C9ABC.DWG"
    shutil.copyfile(AMOSTRA, temp)
    monkeypatch.setattr(do_autocad, "conteudo", lambda: {"formatos": ["AutoCAD.r25"], "arquivos": [],
                                                          "autocad": {"formato": "AutoCAD.r25", "bytes": _clipboard_info(str(temp), (50000.0, 20000.0))}})
    r = app.colar_do_autocad("teste-colar", {"escala": 10})
    tipos = sorted(e["tipo"] for e in r["entidades"])
    assert tipos == ["circulo", "linha", "polilinha", "texto"], tipos
    assert {e["camada"] for e in r["entidades"]} == {"PECA CIANO"} and "PECA CIANO" in r["camadas"]
    from nucleo2d.dxf_ler import cor_aci
    assert r["camadas"]["PECA CIANO"]["cor"].lower() == cor_aci(4).lower()          # o ciano do AutoCAD (ACI 4)
    linha = next(e for e in r["entidades"] if e["tipo"] == "linha")
    assert (round(linha["a"][0]), round(linha["b"][0])) == (50000, 51200)             # mm, nas coordenadas de origem
    assert r["base"] == [50000.0, 20000.0] and r["resumo"]["fator"] == 1.0
    texto = next(e for e in r["entidades"] if e["tipo"] == "texto")
    assert texto["texto"] == "CH1" and texto["altura"] == pytest.approx(2.5)          # 25 mm no desenho de 1:10


def test_copia_do_programa_vale_enquanto_nada_foi_copiado_fora(monkeypatch):
    """o Ctrl+C do CAD guarda o número da área de transferência do Windows; no Ctrl+V, o mesmo número = a cópia do CAD
    (sem ler a área de transferência); outro número = a do AutoCAD (23/10, copiar e colar entre desenhos)"""
    import app
    monkeypatch.setattr(do_autocad, "sequencia", lambda: 41)
    assert app.colar_do_autocad("teste-colar", {"so_sequencia": True}) == {"sequencia": 41}
    assert app.colar_do_autocad("teste-colar", {"sequencia": 41}) == {"interno": True, "sequencia": 41}
    lido = []
    monkeypatch.setattr(do_autocad, "o_que_colar", lambda: lido.append(1) or (_ for _ in ()).throw(ErroDeDados("nada do AutoCAD")))
    with pytest.raises(ErroDeDados):
        app.colar_do_autocad("teste-colar", {"sequencia": 40})      # mudou: vai ler a do Windows
    assert lido == [1]
