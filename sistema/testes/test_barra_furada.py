# -*- coding: utf-8 -*-
"""A barra furada: os marcadores de furo (ferramenta Furo/Parafuso, `atributos.furo`) viram furo de verdade na
malha da barra (usuário, 13/10: "ele não furou a terça, só pintou de outra cor o local dos furos")."""
import collections
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Barra  # noqa: E402
from nucleo3d import geometria as G  # noqa: E402


def _terca():
    # Ue 200×75 deitada, boca para baixo: alma em cima (z 0 a 2,65 abaixo do topo), ao longo de X
    return Barra(inicio=(0.0, 0.0, 0.0), fim=(2000.0, 0.0, 0.0), perfil="Ue 200×75×25×2,65", papel="terça", rotacao=0.0)


def _fechada(vs, fs):
    k = lambda p: tuple(round(c, 3) for c in p)
    arestas = collections.Counter()
    for f in fs:
        for a, b in zip(f, f[1:] + f[:1]):
            arestas[(k(vs[a]), k(vs[b]))] += 1
    return all(arestas.get((b, a), 0) == n for (a, b), n in arestas.items())


def _face_de_cima(b):
    vs, _ = G.malha_barra(b)
    return max(p[2] for p in vs)


def test_furo_oblongo_abre_a_alma():
    b = _terca()
    z = _face_de_cima(b)
    vs0, fs0 = G.malha_barra(b)
    # o furo vertical que atravessa a parede de cima (o marcador começa na face de cima e desce)
    lisa_vs, _ = vs0, fs0
    ys = sorted({round(p[1], 3) for p in lisa_vs})
    furo = {"d": 10.53, "comp": 23.0, "dir": [1.0, 0.0, 0.0], "ponto": [1000.0, 0.0, z], "eixo": [0.0, 0.0, -1.0],
            "profundidade": 2.65}
    # descobre a espessura da parede atravessada pela própria malha: a de cima
    vs, fs = G.malha_barra_furada(b, [furo])
    assert len(fs) > len(fs0)
    assert _fechada(vs, fs)
    v0, v1 = G.volume_malha(vs0, fs0), G.volume_malha(vs, fs)
    area = math.pi * (10.53 / 2) ** 2 + (23.0 - 10.53) * 10.53
    assert v0 - v1 > 0
    # a parede de cima da seção deitada tem a espessura do perfil
    assert abs((v0 - v1) / area - 2.65) < 0.2, (v0 - v1) / area
    assert ys  # a malha lisa tem pontos


def test_sem_furo_na_parede_fica_a_lisa():
    b = _terca()
    vs0, fs0 = G.malha_barra(b)
    longe = {"d": 11.0, "ponto": [1000.0, 0.0, 500.0], "eixo": [0.0, 0.0, -1.0], "profundidade": 3.0}
    vs, fs = G.malha_barra_furada(b, [longe])
    assert len(fs) == len(fs0)


def test_barra_com_corte_no_angulo_nao_e_furada():
    b = _terca()
    b.cortes_inicio = [{"normal": [-1.0, 0.0, 0.2], "ponto": [0.0, 0.0, 0.0]}]
    assert not G.barra_furavel(b)


def test_pacote_tira_o_marcador_e_fura_a_barra():
    from saida import pacote_celular as PC
    b = _terca()
    z = _face_de_cima(b)
    reg_b = dict(b.dict() if hasattr(b, "dict") else b.__dict__, tipo="barra", id="b1", camada="Terças")
    marcador = {"tipo": "solido", "id": "f1", "camada": "Furos", "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "faces": [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]],
                "atributos": {"furo": {"d": 11.0, "ponto": [500.0, 0.0, z], "eixo": [0.0, 0.0, -1.0], "profundidade": 2.65, "peca": "b1"}}}
    por, marcadores = PC._furos_das_barras([reg_b, marcador])
    assert marcadores == {"f1"} and len(por["b1"]) == 1
    vs, fs = PC._malha(reg_b, por["b1"])
    assert len(fs) > len(G.malha_barra(b)[1])
