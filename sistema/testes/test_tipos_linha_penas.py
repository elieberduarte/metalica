"""Tipos de linha, espessuras e penas de impressão (usuário, 23/10: "precisamos criar outros tipos de linhas
(tracejada, pontilhada....) igual existe no autocad, e a opção de mexer nas espessuras..." e "criar as penas igual
existe no autocad para configurar como vai para impressão").

O objeto tem o tipo de linha e a espessura dele ou os da camada ("pela camada"); o PDF sai com eles (antes: três larguras
fixas pelo nome da camada do DXF e só 4 tracejados) e com as penas por cima (a cor do CAD → espessura e cor no papel,
como o CTB); o DXF para o AutoCAD leva o do objeto e o $LTSCALE pela escala dos tracejados. A tela é conferida em
verificadores/verif_cad_linhas_penas.py."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo2d import dxf_cad, tipos_linha  # noqa: E402
from nucleo2d.desenho import Desenho, Linha, Polilinha, Camada2D  # noqa: E402
from saida import dxf_render  # noqa: E402

PT = 72.0 / 25.4


def _desenho():
    d = Desenho(nome="t", escala=10.0)
    d.camadas["OCULTA"] = Camada2D(nome="OCULTA", cor="#8a94a6", tipo_linha="HIDDEN", espessura=0.18)
    d.add(Linha(id="pela", a=(0, 0), b=(1000, 0), camada="OCULTA"))
    d.add(Linha(id="propria", a=(0, 100), b=(1000, 100), camada="OCULTA", tipo_linha="DOT", espessura=0.7))
    d.add(Polilinha(id="poli", vertices=[(0, 200), (500, 300), (1000, 200)], camada="VISTA", tipo_linha="DASHDOT"))
    return d


def test_tipos_do_autocad():
    assert {"CONTINUOUS", "DASHED", "DASHED2", "DASHEDX2", "HIDDEN", "DOT", "DASHDOT", "CENTER", "DIVIDE", "PHANTOM",
            "BORDER"} <= set(tipos_linha.TIPOS_DE_LINHA)
    assert tipos_linha.padrao("DASHED") == [12.7, -6.35] and tipos_linha.padrao("DASHED2") == [6.35, -3.175]
    assert tipos_linha.padrao("desconhecido") == []
    assert 0.0 in tipos_linha.ESPESSURAS and 2.11 in tipos_linha.ESPESSURAS


def test_o_objeto_pela_camada_ou_o_dele_no_json():
    d = _desenho()
    js = {e["id"]: e for e in d.dict()["entidades"]}
    assert "tipo_linha" not in js["pela"] and "espessura" not in js["pela"]          # pela camada: nada gravado
    assert js["propria"]["tipo_linha"] == "DOT" and js["propria"]["espessura"] == 0.7
    d2 = Desenho.de_dict(json.loads(json.dumps(d.dict())))
    assert d2.entidades["propria"].tipo_linha == "DOT" and d2.entidades["pela"].tipo_linha is None
    assert tipos_linha.estilo_da_linha(d2.entidades["pela"], d2.camadas["OCULTA"]) == ("HIDDEN", 0.18)
    assert tipos_linha.estilo_da_linha(d2.entidades["propria"], d2.camadas["OCULTA"]) == ("DOT", 0.7)


def _linhas_no_pdf(d, tmp_path, penas=None, k=10.0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nucleo2d import pranchas
    arq = d.para_dxf(k, texto_unicode=True).gravar(str(tmp_path / "t.dxf"))
    fig, ax = plt.subplots()
    dxf_render.desenhar(arq, ax, cores=pranchas._cores_do_pdf(d), estilos=pranchas._estilos_do_pdf(d),
                        fator_tracejado=tipos_linha.escala_tracejado(d.metadados.get("estilo")), penas=penas)
    out = []
    for ln in ax.lines:
        ys = list(ln.get_ydata())
        out.append((ys[0], ln.get_linewidth(), ln.get_dashes() if hasattr(ln, "get_dashes") else None, ln.get_linestyle(),
                    matplotlib.colors.to_hex(ln.get_color()), ln))
    plt.close(fig)
    return {round(o[0]): o for o in out}


def test_pdf_com_a_espessura_e_o_tracejado_do_cad(tmp_path):
    ls = _linhas_no_pdf(_desenho(), tmp_path)
    assert ls[0][1] == pytest.approx(0.18 * PT)          # a da camada OCULTA (antes: 0,9 pt fixo)
    assert ls[100][1] == pytest.approx(0.7 * PT)         # a do objeto
    assert ls[0][3] != "-" and ls[100][3] != "-" and ls[200][3] != "-"   # tracejadas (HIDDEN, DOT, DASHDOT)
    # o tracejado no papel: o HIDDEN de 6,35 mm × 0,5 (a escala dos tracejados) = 3,175 mm de traço
    on_off = ls[0][5]._dash_pattern[1]
    assert on_off[0] == pytest.approx(3.175 * PT, rel=1e-3)        # o matplotlib guarda em pontos


def test_escala_dos_tracejados_do_desenho(tmp_path):
    d = _desenho()
    d.metadados["estilo"] = {"escala_tracejado": 1.0}
    on_off = _linhas_no_pdf(d, tmp_path)[0][5]._dash_pattern[1]
    assert on_off[0] == pytest.approx(6.35 * PT, rel=1e-3)


def test_pena_troca_a_espessura_e_a_cor_pela_cor_do_cad(tmp_path):
    ls = _linhas_no_pdf(_desenho(), tmp_path, penas={"#8a94a6": {"espessura": 1.0, "cor": "#000000"}})
    assert ls[0][1] == pytest.approx(1.0 * PT) and ls[0][4] == "#000000"
    assert ls[100][1] == pytest.approx(1.0 * PT)         # a pena vale também para o objeto com espessura própria
    assert ls[200][4] != "#000000"                       # a VISTA (outra cor) fica como estava


def test_dxf_do_autocad_com_o_tipo_do_objeto(tmp_path):
    import ezdxf
    d = _desenho()
    doc = ezdxf.readfile(dxf_cad.exportar(d, str(tmp_path / "a.dxf"), escala=10))
    linhas = {round(e.dxf.start.y): e for e in doc.modelspace().query("LINE")}
    assert linhas[100].dxf.linetype.upper() == "DOT" and linhas[100].dxf.lineweight == 70
    assert linhas[0].dxf.linetype.upper() == "BYLAYER"
    assert doc.layers.get("OCULTA").dxf.linetype.upper() == "HIDDEN"
    poli = next(iter(doc.modelspace().query("LWPOLYLINE")))
    assert poli.dxf.linetype.upper() == "DASHDOT"
    assert doc.header["$LTSCALE"] == pytest.approx(10 * 0.5)


def test_penas_validas_e_gravadas(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, "ARQ_PENAS", str(tmp_path / "penas-de-impressao.json"))
    assert app._ler_penas() == {}
    p = app._gravar_penas({"#1C7A43": {"espessura": "0.13", "cor": "#000000"}, "#ffffff": {"espessura": None, "cor": None},
                           "verde": {"espessura": 1}, "#123456": {"espessura": 99}})
    assert p == {"#1c7a43": {"espessura": 0.13, "cor": "#000000"}}
    assert app._ler_penas() == p
    assert app.rota_impressao("x", "penas", {})["penas"] == p
