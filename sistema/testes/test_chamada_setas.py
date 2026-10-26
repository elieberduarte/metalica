# -*- coding: utf-8 -*-
"""As setas a mais da chamada (usuário, 26/10, ME Sooro, na chamada "CH3": "criar essa opção de puxar mais de uma seta
da mesma linha de chamada"): cada ramo sai de um ponto da linha (`de`, de 0 na seta a 1 no joelho) e vai ao alvo dele.
Do lado do servidor: gravar e ler, mover junto, a cópia do bloco, o DXF do CAD (um LEADER por seta) e o desenho do
PDF / DXF das pranchas (a linha e a seta de cada ramo) — longe do zero também (o SESI está em UTM)."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Bloco, Chamada, Desenho, entidade_de_dict, filhos_do_bloco, transladar, _chamada_dxf  # noqa: E402

SITUACOES = [(0.0, 0.0), (1218181.0, 211836.0)]


def _chamada(ox, oy):
    return Chamada(id="ch3", alvo=(ox + 1000.0, oy + 0.0), posicao=(ox + 0.0, oy + 1000.0), texto="CH3", altura=2.5,
                   ramos=[{"de": 0.5, "alvo": (ox + 900.0, oy - 300.0)}])


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_grava_e_le_os_ramos(ox, oy):
    c = _chamada(ox, oy)
    d = Desenho(nome="t", escala=1.0)
    d.add(c)
    reg = d.dict()["entidades"][0] if isinstance(d.dict()["entidades"], list) else d.dict()["entidades"]["ch3"]
    volta = entidade_de_dict(reg)
    assert volta.ramos == [{"de": 0.5, "alvo": (ox + 900.0, oy - 300.0)}]
    # a origem do ramo: o meio da linha da seta ao joelho
    (o, a), = volta.segmentos_dos_ramos()
    assert o == pytest.approx((ox + 500.0, oy + 500.0)) and a == pytest.approx((ox + 900.0, oy - 300.0))
    assert (ox + 900.0, oy - 300.0) in volta.pontos()


def test_chamada_antiga_sem_ramos():
    volta = entidade_de_dict({"tipo": "chamada", "alvo": [0, 0], "posicao": [10, 10], "texto": "A"})
    assert volta.ramos == [] and volta.segmentos_dos_ramos() == []


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_mover_e_bloco_levam_os_ramos(ox, oy):
    m = transladar(_chamada(ox, oy), 100.0, -50.0)
    assert m.ramos[0]["alvo"] == pytest.approx((ox + 1000.0, oy - 350.0)) and m.ramos[0]["de"] == 0.5
    reg = _chamada(0.0, 0.0)
    blocos = {"B": {"entidades": [dict(reg.__dict__, ramos=[{"de": 0.5, "alvo": [900.0, -300.0]}], alvo=[1000.0, 0.0], posicao=[0.0, 1000.0])]}}
    f, = filhos_do_bloco(Bloco(id="b", nome="B", posicao=(ox, oy), angulo=90.0), blocos)
    assert f.ramos[0]["alvo"] == pytest.approx((ox + 300.0, oy + 900.0))


class _Gravador:
    def __init__(self):
        self.linhas, self.setas = [], []

    def linha(self, x1, y1, x2, y2, camada):
        self.linhas.append(((x1, y1), (x2, y2)))

    def seta(self, x, y, ang, tam, camada):
        self.setas.append(((x, y), ang))

    def texto(self, *a, **k):
        pass


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_pdf_e_dxf_das_pranchas_desenham_a_seta_a_mais(ox, oy):
    """o PDF das pranchas é o para_dxf renderizado: sem isto a seta a mais sumia no papel"""
    g = _Gravador()
    _chamada_dxf(g, _chamada(ox, oy), 1.0, "TEXTO")
    assert len(g.setas) == 2
    (p, ang) = g.setas[1]
    assert p == pytest.approx((ox + 900.0, oy - 300.0))
    assert ang == pytest.approx(-63.4349, abs=1e-3)      # de (500, 500) a (900, -300)
    assert ((ox + 500.0, oy + 500.0), (ox + 900.0, oy - 300.0)) in [(tuple(a), tuple(b)) for a, b in g.linhas]


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_dxf_do_cad_tem_um_leader_por_seta(ox, oy):
    import ezdxf
    from nucleo2d.dxf_cad import exportar
    d = Desenho(nome="t", escala=1.0)
    d.add(_chamada(ox, oy))
    with tempfile.TemporaryDirectory() as pasta:
        caminho = exportar(d, os.path.join(pasta, "t.dxf"))
        leaders = [list(e.vertices) for e in ezdxf.readfile(caminho).modelspace().query("LEADER")]
    assert len(leaders) == 2
    assert [tuple(v)[:2] for v in leaders[1]] == pytest.approx([(ox + 900.0, oy - 300.0), (ox + 500.0, oy + 500.0)])
