# -*- coding: utf-8 -*-
"""O tipo e o tamanho da ponta da cota (usuário, 26/10, ME Sooro, na T1 da Sala: "como faço para trocar o tipo e tamanho
dos arrowheads?" — o DIMBLK e a DIMASZ do AutoCAD): a cota guarda `seta` (mm de papel) e o desenho `estilo.seta`; sem
nenhum, 2,5 como sempre. Vale no PDF das pranchas (o para_dxf), no DXF do CAD (DIMASZ / DIMTSZ da DIMENSION), nas cotas
especiais e na tela (web/cad/nucleo/desenho2d.js setaNaCota, pelo node). A cota é a da prancha da obra (texto 4,89,
escala 25), perto do zero e em UTM; o painel e o Estilos estão no verif_cad_ponta_cota."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nucleo2d.desenho as D                                                    # noqa: E402
from nucleo2d.desenho import Cota, CotaEspecial, Desenho, entidade_de_dict, seta_da_cota   # noqa: E402

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
SITUACOES = [(0.0, 0.0), (1218181.0, 211836.0)]


def _cota(ox=0.0, oy=0.0, **kw):
    return Cota(id=kw.pop("id", "xc3ed5zr83vs"), camada="COTA", modo="alinhada", p1=(ox + 2016.8092165815967, oy + 403.58208168476835),
                p2=(ox + 2022.3007193701787, oy + 376.1218486953851), deslocamento=-2.228301235520105, texto=None,
                altura=4.89, escala=25, **kw)


def test_qual_vale():
    assert seta_da_cota(Cota()) == 2.5
    assert seta_da_cota(Cota(), {"seta": 4}) == 4.0
    assert seta_da_cota(Cota(seta=1.5), {"seta": 4}) == 1.5
    assert seta_da_cota(Cota(seta=0), {"seta": "x"}) == 2.5                 # zero ou lixo: a padrão
    assert entidade_de_dict(dict(_cota(seta=3.0).__dict__)).seta == 3.0      # grava e lê


def _pontas(c, estilo=None, k=1.0):
    reg = []
    orig = D._terminador_dxf
    D._terminador_dxf = lambda d, x, y, ang, tam, cam, tipo: reg.append((round(tam, 4), tipo))
    try:
        class _G:
            def __getattr__(self, n):
                return lambda *a, **kw: None
        D._cota_dxf(_G(), c, k, "COTA", terminador=c.terminador or (estilo or {}).get("terminador") or D.TERMINADOR_PADRAO, estilo=estilo or {})
    finally:
        D._terminador_dxf = orig
    return reg


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_pdf_das_pranchas(ox, oy):
    assert _pontas(_cota(ox, oy)) == [(2.5, "traco")] * 2                          # como era
    assert _pontas(_cota(ox, oy, seta=4.0, terminador="seta")) == [(4.0, "seta")] * 2
    assert _pontas(_cota(ox, oy), {"seta": 1.5, "terminador": "bola"}) == [(1.5, "bola")] * 2
    assert _pontas(_cota(ox, oy, seta=3.0, fator=2.0)) == [(6.0, "traco")] * 2      # × o fator, como o texto
    assert _pontas(_cota(ox, oy, seta=10.0)) == [(7.001, "traco")] * 2             # a cota de 28 mm: até ¼ dela


def _dimasz(cotas, estilo=None):
    import ezdxf
    from nucleo2d.dxf_cad import exportar
    d = Desenho(nome="t", escala=1.0)
    if estilo:
        d.metadados["estilo"] = estilo
    for c in cotas:
        d.add(c)
    pasta = tempfile.mkdtemp(prefix="cota_ponta_")
    try:
        doc = ezdxf.readfile(exportar(d, os.path.join(pasta, "t.dxf")))
        out = {}
        for dim in doc.modelspace().query("DIMENSION"):
            o = dim.override()
            out[round(dim.dxf.defpoint[0] - 2016.8, -1)] = (o.get("dimasz"), o.get("dimtsz"), o.get("dimblk"))
        return out
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_dxf_do_cad(ox, oy):
    from nucleo2d.dxf_cad import FATOR_TRACO
    r = _dimasz([_cota(ox, oy), _cota(ox + 100.0, oy, id="seta4", seta=4.0, terminador="seta")])
    (a, b) = [r[k] for k in sorted(r)]
    assert a[0] == pytest.approx(2.5) and a[1] == pytest.approx(FATOR_TRACO * 2.5)    # o traço de antes
    assert b[0] == pytest.approx(4.0) and not b[1]                                    # a seta de 4 mm
    r = _dimasz([_cota(ox, oy)], {"seta": 3.0})
    assert list(r.values())[0][0] == pytest.approx(3.0)                              # o do desenho


def test_cota_especial():
    from nucleo2d.cota_especial import primitivas
    c = CotaEspecial(modo="raio", centro=(0, 0), p1=(12.7, 0), posicao=(40, 0), seta=4.0)
    assert {p["tam"] for p in primitivas(c, 1.0)["pontas"]} == {4.0}
    c = CotaEspecial(modo="raio", centro=(0, 0), p1=(12.7, 0), posicao=(40, 0))
    assert {p["tam"] for p in primitivas(c, 1.0, {"seta": 3.0})["pontas"]} == {3.0}
    assert {p["tam"] for p in primitivas(c, 1.0)["pontas"]} == {2.5}


def test_tela_pelo_node():
    pasta = tempfile.mkdtemp(prefix="cota_ponta_js_")
    try:
        script = os.path.join(pasta, "t.mjs")
        url = "file:///" + os.path.join(WEB, "cad", "nucleo", "desenho2d.js").replace("\\", "/")
        url_esp = "file:///" + os.path.join(WEB, "cad", "nucleo", "cota_especial.js").replace("\\", "/")
        c = _cota(1218181.0, 211836.0)
        reg = {"tipo": "cota", "modo": c.modo, "p1": list(c.p1), "p2": list(c.p2), "deslocamento": c.deslocamento,
               "texto": None, "altura": c.altura, "escala": 25, "seta": 4}
        open(script, "w", encoding="utf-8").write(
            "import { setaDaCota as s, setaNaCota as n, criar, textoDaCota } from %s;\n"
            "import { primitivasDaCotaEspecial as p } from %s;\n"
            "const c = criar(%s);\n"
            "console.log(JSON.stringify([c.seta, s({}), s({}, { seta: 3 }), s({ seta: 1.5 }, { seta: 3 }), s({ seta: 0 }),\n"
            "  n(c, 1, 1000), n({}, 1, 1000), n({ seta: 4 }, 20, 100000), n({ seta: 4 }, 1, 6), n({ seta: 0.5 }, 1, 1),\n"
            "  textoDaCota(c, 1).seta, p({ modo: 'raio', centro: [0, 0], p1: [12.7, 0], posicao: [40, 0], seta: 4 }).pontas[0].tam]));\n"
            % (json.dumps(url), json.dumps(url_esp), json.dumps(reg)))
        r = subprocess.run(["node", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert r.returncode == 0, r.stderr
        a = json.loads(r.stdout)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    # 4 escolhida; 2,5 sem nada; a do desenho; a da cota vence; em 1:20 × 20; na cota curta encolhe até ¼ dela (6/4 = 1,5),
    # nunca abaixo de 1 mm, nem acima da escolhida (0,5)
    assert a == [4, 2.5, 3, 1.5, 2.5, 4, 2.5, 80, 1.5, 0.5, 4, 4], a
