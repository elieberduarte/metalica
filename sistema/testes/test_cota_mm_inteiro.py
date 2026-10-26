# -*- coding: utf-8 -*-
"""A cota ao mm inteiro (REGRA do usuário, 26/10, na T1 da Sala de Compressores da ME Sooro, prancha ajustada à mão: a
cota "700,1" vira 700): no automático o número é sempre ao mm; decimal só com as casas escolhidas à mão (a chapa, raro).
Vale na tela (web/cad/nucleo/desenho2d.js numeroDaCota, pelo node), no PDF das pranchas (o para_dxf) e no DXF do CAD
(DIMENSION com dimdec 0). A cota é a da prancha da obra: dentro da célula em 1:25 (28,004 desenhados × 25 = 700,099)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Cota, CotaEspecial, Desenho, formatar_cota  # noqa: E402
from nucleo2d.cota_especial import medida  # noqa: E402

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

# a cota da prancha da Sala de Compressores (pranchas.desenho.json, xc3ed5zr83vs), perto do zero e longe dele
SITUACOES = [(0.0, 0.0), (1218181.0, 211836.0)]


def _cota_da_obra(ox=0.0, oy=0.0, casas=None):
    return Cota(id="xc3ed5zr83vs", camada="COTA", modo="alinhada", p1=(ox + 2016.8092165815967, oy + 403.58208168476835),
                p2=(ox + 2022.3007193701787, oy + 376.1218486953851), deslocamento=-2.228301235520105, texto=None,
                altura=4.89, escala=25, casas=casas)


def test_numero_ao_mm():
    assert formatar_cota(700.099) == "700"
    assert formatar_cota(772.5) == "773" and formatar_cota(1545.49) == "1545" and formatar_cota(-0.3) == "0"
    assert formatar_cota(700.099, "auto") == "700" and formatar_cota(700.099, "") == "700"
    # as casas escolhidas à mão continuam
    assert formatar_cota(700.099, 1) == "700,1" and formatar_cota(12.5, 2) == "12,50"


class _Gravador:
    def __init__(self):
        self.textos = []

    def __getattr__(self, nome):
        return lambda *a, **k: None

    def texto(self, x, y, t, *a, **k):
        self.textos.append(t)


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_pdf_das_pranchas_ao_mm(ox, oy):
    """o PDF das pranchas é o para_dxf: a cota da obra saía "700,1" """
    from nucleo2d.desenho import _cota_dxf
    for casas, esperado in ((None, "700"), (1, "700,1")):
        g = _Gravador()
        _cota_dxf(g, _cota_da_obra(ox, oy, casas), 1.0, "COTA")
        assert g.textos == [esperado]


def test_cotas_especiais_ao_mm():
    assert medida(CotaEspecial(modo="raio", centro=(0, 0), p1=(12.7, 0), posicao=(20, 0))) == "R13"
    assert medida(CotaEspecial(modo="diametro", centro=(0, 0), p1=(12.7, 0), posicao=(20, 0))) == "Ø25"
    assert medida(CotaEspecial(modo="ordenada", centro=(0, 0), p1=(700.099, 5), posicao=(700, 50), eixo="x")) == "700"
    # o ângulo segue com uma casa quando não é inteiro
    assert medida(CotaEspecial(modo="angular", centro=(0, 0), p1=(100, 0), p2=(100, 33.0), posicao=(50, 5))).endswith("°")


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_dxf_do_cad_ao_mm(ox, oy):
    import ezdxf
    from nucleo2d.dxf_cad import exportar
    d = Desenho(nome="t", escala=1.0)
    d.add(_cota_da_obra(ox, oy))
    c1 = _cota_da_obra(ox + 100.0, oy, casas=1)
    c1.id = "com_casas"
    d.add(c1)
    pasta = tempfile.mkdtemp(prefix="cota_mm_")
    try:
        doc = ezdxf.readfile(exportar(d, os.path.join(pasta, "t.dxf")))
        textos = []
        for dim in doc.modelspace().query("DIMENSION"):
            blk = doc.blocks.get(dim.dxf.geometry)
            textos += [m.plain_text() if m.dxftype() == "MTEXT" else m.dxf.text for m in blk if m.dxftype() in ("MTEXT", "TEXT")]
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    assert sorted(textos) == ["700", "700,1"], textos


def test_tela_ao_mm_pelo_node():
    pasta = tempfile.mkdtemp(prefix="cota_mm_js_")
    try:
        script = os.path.join(pasta, "t.mjs")
        url = "file:///" + os.path.join(WEB, "cad", "nucleo", "desenho2d.js").replace("\\", "/")
        url_esp = "file:///" + os.path.join(WEB, "cad", "nucleo", "cota_especial.js").replace("\\", "/")
        c = _cota_da_obra()
        reg = {"tipo": "cota", "modo": c.modo, "p1": list(c.p1), "p2": list(c.p2), "deslocamento": c.deslocamento,
               "texto": None, "altura": c.altura, "escala": 25, "casas": None}
        open(script, "w", encoding="utf-8").write(
            "import { numeroDaCota as n, textoDaCota, criar } from %s;\n"
            "import { medidaDaCotaEspecial as m } from %s;\n"
            "const c = criar(%s);\n"
            "console.log(JSON.stringify([n(700.099), n(700.099, 'auto'), n(700.099, 1), n(772.5), n(-0.3),\n"
            "  textoDaCota(c, 1).txt, textoDaCota({ ...c, casas: 1 }, 1).txt,\n"
            "  m({ modo: 'raio', centro: [0, 0], p1: [12.7, 0], posicao: [20, 0] })]));\n"
            % (json.dumps(url), json.dumps(url_esp), json.dumps(reg)))
        r = subprocess.run(["node", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert r.returncode == 0, r.stderr
        a = json.loads(r.stdout)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    assert a == ["700", "700", "700,1", "773", "0", "700", "700,1", "R13"], a
