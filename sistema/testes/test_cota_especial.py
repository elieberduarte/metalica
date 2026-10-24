"""As cotas angular, de raio, de diâmetro e ordenada (usuário, 23/10: "pode seguir" — a leva das cotas da lista das
ferramentas que faltam). A conta de web/cad/nucleo/cota_especial.js (a tela) e a de nucleo2d/cota_especial.py (o PDF)
dão as mesmas linhas, arcos, pontas e números — o teste roda a da tela pelo Node; o DXF do AutoCAD leva cotas de
verdade (DIMENSION angular, de raio, de diâmetro e ordenada); a prancha leva a cota para o papel com o número da peça.
A tela é conferida em verificadores/verif_cad_cotas_novas.py."""
import json
import math
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo2d import cota_especial, dxf_cad  # noqa: E402
from nucleo2d.desenho import CotaEspecial, Desenho  # noqa: E402

JS = os.path.join(os.path.dirname(__file__), "..", "web", "cad", "nucleo", "cota_especial.js")

CASOS = [
    dict(modo="angular", centro=(0, 0), p1=(1000, 0), p2=(0, 600), posicao=(300, 300)),          # 90°, o arco aquém dos pontos
    dict(modo="angular", centro=(0, 0), p1=(1000, 0), p2=(707.1068, 707.1068), posicao=(-200, -10)),   # o outro setor: 315°
    dict(modo="angular", centro=(100, 50), p1=(400, 50), p2=(100 + 300 * math.cos(math.radians(30)), 50 + 300 * math.sin(math.radians(30))),
         posicao=(900, 300), casas=1),                                                           # 30,0°, o arco além dos pontos
    dict(modo="raio", centro=(0, 0), p1=(50, 0), posicao=(20, 10)),                              # dentro
    dict(modo="raio", centro=(0, 0), p1=(0, 50), posicao=(-300, 200)),                           # fora, à esquerda
    dict(modo="diametro", centro=(10, 10), p1=(10, 60), posicao=(10, 30)),
    dict(modo="diametro", centro=(0, 0), p1=(35.355, 35.355), posicao=(400, 400), escala=10),
    dict(modo="ordenada", centro=(0, 0), p1=(250, 100), posicao=(250, 600), eixo="x"),           # para cima, reta
    dict(modo="ordenada", centro=(0, 0), p1=(250, 100), posicao=(320, -500), eixo="x"),          # para baixo, com o degrau
    dict(modo="ordenada", centro=(1000, 0), p1=(1250, 400), posicao=(1900, 380), eixo="y", fator=2),
]


def _cota(**kw):
    kw.setdefault("altura", 2.5)
    return CotaEspecial(**{k: (tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in kw.items()})


def _js(casos, k, estilo):
    node = shutil.which("node")
    if not node:
        pytest.skip("sem o Node: a conta da tela não roda aqui")
    url = "file:///" + os.path.abspath(JS).replace("\\", "/")
    roteiro = ("import { primitivasDaCotaEspecial } from %s;\n"
               "let t = ''; process.stdin.on('data', d => t += d); process.stdin.on('end', () => {\n"
               "  const { casos, k, estilo } = JSON.parse(t);\n"
               "  process.stdout.write(JSON.stringify(casos.map(c => primitivasDaCotaEspecial(c, k, estilo))));\n"
               "});\n" % json.dumps(url.replace(" ", "%20")))
    r = subprocess.run([node, "--input-type=module", "-e", roteiro], input=json.dumps({"casos": casos, "k": k, "estilo": estilo}),
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _plano(x):
    """a estrutura com os números arredondados (pontos como listas)"""
    if isinstance(x, dict):
        return {k: _plano(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plano(v) for v in x]
    if isinstance(x, float):
        return round(x, 4) + 0.0
    return x


@pytest.mark.parametrize("k,estilo", [(1.0, None), (25.0, {"folga_texto": 1.0, "terminador": "seta"})])
def test_tela_e_pdf_desenham_igual(k, estilo):
    js = _js([dict(c, texto=None) for c in CASOS], k, estilo)
    for caso, pj in zip(CASOS, js):
        py = cota_especial.primitivas(_cota(**caso), k, estilo)
        assert _plano(py) == _plano(pj), caso


def test_numeros():
    m = lambda **kw: cota_especial.medida(_cota(**kw))      # noqa: E731
    assert m(**CASOS[0]) == "90°" and m(**CASOS[1]) == "315°" and m(**CASOS[2]) == "30,0°"
    assert m(**CASOS[3]) == "R50" and m(**CASOS[6]) == "Ø1000"       # o diâmetro de 50 desenhado em 1:10 da peça
    assert m(**CASOS[7]) == "250" and m(**CASOS[9]) == "400"


def test_pdf_e_json(tmp_path):
    d = Desenho(nome="t", escala=1.0)
    for i, c in enumerate(CASOS):
        d.add(_cota(id="c%d" % i, **c))
    d2 = Desenho.de_dict(json.loads(json.dumps(d.dict())))
    assert isinstance(d2.entidades["c0"], CotaEspecial) and d2.entidades["c9"].eixo == "y" and d2.entidades["c0"].p2 == (0, 600)
    from saida import dxf_render
    doc = dxf_render.ler_dxf(d.para_dxf(1.0, texto_unicode=True).gravar(str(tmp_path / "t.dxf")))
    textos = {e.get("texto") for e in doc["entidades"] if e["tipo"] == "TEXT"}
    assert {"90°", "315°", "R50", "Ø100", "250"} <= textos
    assert sum(1 for e in doc["entidades"] if e["tipo"] == "ARC") == 3              # os três arcos dos ângulos


def test_dxf_do_autocad_com_dimension(tmp_path):
    import ezdxf
    d = Desenho(nome="t", escala=1.0)
    for i, c in enumerate(CASOS):
        d.add(_cota(id="c%d" % i, **c))
    doc = ezdxf.readfile(dxf_cad.exportar(d, str(tmp_path / "a.dxf"), 1.0))
    dims = list(doc.modelspace().query("DIMENSION"))
    tipos = sorted(x.dimtype & 7 for x in dims)
    # 5 = angular de 3 pontos, 4 = raio, 3 = diâmetro, 6 = ordenada
    assert tipos.count(5) == 3 and tipos.count(4) == 2 and tipos.count(3) == 2 and tipos.count(6) == 3, tipos
    medidas = sorted(round(x.get_measurement(), 3) for x in dims if (x.dimtype & 7) == 4)
    assert medidas == [50.0, 50.0]


def test_prancha_leva_o_numero_da_peca():
    from nucleo2d.pranchas import _para_papel
    c = _cota(id="r", modo="raio", centro=(1000, 1000), p1=(1250, 1000), posicao=(1100, 1050))
    n = _para_papel(c, 25.0, 10.0, 20.0, "detalhamento-x")
    assert n.texto == "R250" and n.centro == (50.0, 60.0) and n.p1 == (60.0, 60.0)
