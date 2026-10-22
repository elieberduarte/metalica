# -*- coding: utf-8 -*-
"""Regras da cobertura conferidas por propriedade (catálogo sistema/testes/REGRAS.md): o caso não é o desenho de um dia,
o Hypothesis sorteia a forma — o ângulo da parede, a distância, a inclinação, o vão, a terça emendada — num modelo
mínimo (só a água e a parede) e a regra tem de valer em todas. A meta é achar a "próxima forma" do erro antes do
usuário (21/10: "a telha vai até a parede" corrigida 4 vezes, cada vez com uma forma nova).

Sorteio fixo por padrão (derandomize: o mesmo resultado no antes_de_publicar); METALICA_HIPOTESE=aleatorio sorteia
casos novos a cada rodada (para a conferência da noite procurar formas novas)."""
import math
import os

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import assume, given, settings, strategies as st  # noqa: E402

from nucleo3d.modelo import Barra, Documento  # noqa: E402
from nucleo3d import telhas_cobertura as T  # noqa: E402

PERFIL = "U 100×40×2,65 (FF)"
ALEATORIO = os.environ.get("METALICA_HIPOTESE") == "aleatorio"
POUCOS = settings(max_examples=40 if not ALEATORIO else 200, deadline=None, derandomize=not ALEATORIO,
                  print_blob=True)

COMPRIMENTO = 6000.0         # mm: as terças de y 0 a 6000
ALCANCE = 1600.0             # mm: até onde a telha passa da última terça sem outra terça junto (test_telhas_cobertura)
FOLGA_PAREDE = T.AFASTAMENTO_PAREDE   # a ponta da telha até a face da parede (a calha/o rufo encostado nela)
TOL = 50.0                   # mm: o recorte em pedaços retos ao longo da face


def _terca(doc, x, z, sigla, y0=0.0, y1=COMPRIMENTO):
    b = Barra(inicio=(x, y0, z), fim=(x, y1, z), perfil=PERFIL, papel="terça", camada="Terças")
    b.atributos = {"origem": {"sigla": sigla}}
    doc.add(b)
    return b


def _banzo(doc, a, b, nome, perfil="U 150×70×4,75 (FF)"):
    tr = Barra(inicio=a, fim=b, perfil=perfil, papel="banzo", camada="Treliças")
    tr.atributos = {"origem": {"planta": nome, "peca": nome + "#1"}}
    doc.add(tr)
    return tr


def _telhado(doc):
    return [s for s in doc.solidos if s.camada == "Telhas" and not (s.atributos or {}).get("fechamento")]


def _casco(pts):
    """o contorno convexo em planta (a chapa vista de cima)"""
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def giro(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    baixo, cima = [], []
    for p in pts:
        while len(baixo) >= 2 and giro(baixo[-2], baixo[-1], p) <= 0:
            baixo.pop()
        baixo.append(p)
    for p in reversed(pts):
        while len(cima) >= 2 and giro(cima[-2], cima[-1], p) <= 0:
            cima.pop()
        cima.append(p)
    return baixo[:-1] + cima[:-1]


def _alcance_em(cascos, y):
    """o x mais longe que a telha cobre na linha y (o corte de cada chapa pela reta y = const)"""
    melhor = -math.inf
    for c in cascos:
        for (x0, y0), (x1, y1) in zip(c, c[1:] + c[:1]):
            if min(y0, y1) - 1e-6 <= y <= max(y0, y1) + 1e-6:
                x = x0 if abs(y1 - y0) < 1e-9 else x0 + (x1 - x0) * (y - y0) / (y1 - y0)
                melhor = max(melhor, x if abs(y1 - y0) >= 1e-9 else max(x0, x1))
    return melhor


@POUCOS
@given(n=st.integers(2, 5),
       passo=st.floats(900.0, 1800.0),
       inclinacao=st.floats(0.02, 0.30),
       d0=st.floats(150.0, 1400.0),                      # a face, a partir da última terça, em y = 0
       angulo=st.floats(T.PAREDE_PARALELA + 0.1, 12.0),  # graus da parede fora da direção das terças
       lado=st.sampled_from((-1.0, 1.0)),
       emenda=st.one_of(st.none(), st.floats(800.0, 5200.0)))   # a última terça emendada no apoio em y
def test_cob03_telha_vai_ate_a_parede_reta(n, passo, inclinacao, d0, angulo, lado, emenda):
    """COB-03: a telha chega até a face da parede (menos o afastamento da calha/rufo) em toda a borda ao alcance, e nada
    passa da face — a parede paralela, quase paralela (a PAINEL 12 do Posto, 9,6°) ou diagonal, com ou sem a última terça
    emendada (a TRANSIÇÃO 16). A parede a menos de PAREDE_PARALELA (3°) é a "borda comum": a telha para na última terça
    qualquer que seja a distância — a decidir com o usuário (REGRAS.md, COB-03), fora deste sorteio."""
    doc = Documento()
    z0 = 7000.0
    for i in range(n):
        x, z = i * passo, z0 + i * passo * inclinacao
        if i == n - 1 and emenda is not None:
            _terca(doc, x, z, "TC%d" % (i + 1), y1=emenda)
            _terca(doc, x, z, "TC%d" % (i + 1), y0=emenda)
        else:
            _terca(doc, x, z, "TC%d" % (i + 1))
    ultima = (n - 1) * passo
    t = lado * math.tan(math.radians(angulo))
    face = lambda y: ultima + d0 + t * y                                    # noqa: E731
    assume(all(150.0 <= face(y) - ultima <= ALCANCE for y in (0.0, COMPRIMENTO)))   # fora do alcance: outra regra
    z_parede = z0 + (ultima + d0) * inclinacao + 600.0
    _banzo(doc, (face(0.0), 0.0, z_parede), (face(COMPRIMENTO), COMPRIMENTO, z_parede), "PAINEL 1")
    T.lancar(doc)

    tel = _telhado(doc)
    assert tel, "nenhuma telha lançada"
    for s in tel:
        for v in s.vertices:
            assert v[0] <= face(v[1]) + 1.0, "telha passa da face da parede em y %.0f (%.0f mm)" % (v[1], v[0] - face(v[1]))
    cascos = [_casco([(v[0], v[1]) for v in s.vertices]) for s in tel]
    for k in range(1, 12):                                                   # longe das pontas das terças
        y = COMPRIMENTO * k / 12.0
        falta = face(y) - FOLGA_PAREDE - _alcance_em(cascos, y)
        assert falta <= TOL, "a telha para %.0f mm antes da parede em y %.0f (face a %.0f mm da última terça)" % (
            falta, y, face(y) - ultima)
