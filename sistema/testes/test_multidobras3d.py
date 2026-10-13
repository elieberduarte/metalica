# -*- coding: utf-8 -*-
"""Multidobra no 3D (13/10): a telha do beiral do modelo reescrita com o raio comercial girando no vértice das
retas, e o volta ao original."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Solido                 # noqa: E402
from nucleo3d import multidobras3d as M                       # noqa: E402
from nucleo2d.detalhe.telhas import multidobras, RAIO_INTERNO_COMERCIAL   # noqa: E402

H = 40.0           # altura da onda
W = 1000.0         # largura da telha (eixo y)
R_MODELO = 800.0   # o raio das facetas do TecnoMETAL


def _caixa(centro, eixos, dims, marcas):
    """Prisma retangular: `eixos` (u ao longo, w na largura, n na espessura), `dims` (L, W, h)."""
    u, w, n = eixos
    L, Wd, h = dims
    vs = []
    for su in (-1, 1):
        for sw in (-1, 1):
            for sn in (-1, 1):
                vs.append(tuple(centro[i] + u[i] * su * L / 2 + w[i] * sw * Wd / 2 + n[i] * sn * h / 2 for i in range(3)))
    faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return Solido(nome="TELHA TP40 0.65MM", camada="Telhas", vertices=vs, faces=faces,
                  atributos={"tipo_ifc": "IfcPlate", "marcas": dict(marcas, perfil="TELHA TP40 0.65MM")})


def _multidobra(y, conjunto="M1", facetas=6, reta_agua=3000.0, reta_parede=600.0):
    """A fileira do TecnoMETAL: reta da água (horizontal, de x=-reta_agua a 0), arco de 90° com R_MODELO (linha
    média) e reta da parede descendo. O vértice das retas em (R, −R) relativo ao começo do arco."""
    w = (0.0, 1.0, 0.0)
    pecas = []
    # reta da água: ao longo de +x, termina na tangência (0, 0, 0)
    pecas.append(_caixa((-reta_agua / 2, y, 0.0), ((1, 0, 0), w, (0, 0, 1)), (reta_agua, W, H), {"posicao": "PA", "conjunto": conjunto}))
    # arco: centro (0, −R); de 90° (ponto (0,0)) a 0° (ponto (R, −R))
    C = (0.0, -R_MODELO)
    for k in range(facetas):
        a0 = math.radians(90.0 - 90.0 * k / facetas)
        a1 = math.radians(90.0 - 90.0 * (k + 1) / facetas)
        p0 = (C[0] + R_MODELO * math.cos(a0), C[1] + R_MODELO * math.sin(a0))
        p1 = (C[0] + R_MODELO * math.cos(a1), C[1] + R_MODELO * math.sin(a1))
        L = math.dist(p0, p1)
        u = ((p1[0] - p0[0]) / L, 0.0, (p1[1] - p0[1]) / L)
        n = (-u[2], 0.0, u[0])
        pecas.append(_caixa(((p0[0] + p1[0]) / 2, y, (p0[1] + p1[1]) / 2), (u, w, n), (L, W, H), {"posicao": "FA", "conjunto": conjunto}))
    # reta da parede: vertical, de (R, −R) para baixo
    pecas.append(_caixa((R_MODELO, y, -R_MODELO - reta_parede / 2), ((0, 0, -1), w, (1, 0, 0)), (reta_parede, W, H), {"posicao": "PR", "conjunto": conjunto}))
    return pecas


def _doc(n_inst=2):
    doc = Documento()
    for i in range(n_inst):
        for e in _multidobra(y=i * 1200.0):
            doc.add(e)
    return doc


def _livres(doc):
    """As pontas livres (x mínimo da água, z mínimo da parede) e o vértice das retas: devem ficar onde estão."""
    xs = [v[0] for e in doc.entidades.values() for v in e.vertices]
    zs = [v[2] for e in doc.entidades.values() for v in e.vertices]
    return round(min(xs), 3), round(min(zs), 3)


def test_reescreve_com_o_raio_comercial_e_mantem_pontas_e_quantidades():
    doc = _doc()
    antes = multidobras(list(doc.entidades.values()))["telhas"][0]
    livres = _livres(doc)
    assert abs(antes["raio_modelo"] - R_MODELO) < 0.03 * R_MODELO
    an = M.analisar_modelo(doc)
    assert len(an) == 1 and an[0]["instancias"] == 2 and an[0]["ajustadas"] == 0 and an[0]["facetas"] == 6
    r = M.ajustar_modelo(doc)
    assert r["instancias"] == 2 and r["pecas"] == 16 and not r["falhas"] and r["raio_int"] == RAIO_INTERNO_COMERCIAL
    depois = multidobras(list(doc.entidades.values()))["telhas"][0]
    Rc = RAIO_INTERNO_COMERCIAL + H / 2
    # o modelo passa a ter o raio comercial na linha média (as facetas são cordas: um pouco abaixo do arco)
    assert abs(depois["raio_modelo"] - Rc) < 0.02 * Rc, depois["raio_modelo"]
    assert abs(depois["angulo"] - 90.0) < 0.5
    # as quantidades do detalhamento não mudam: pontas livres e vértice são os mesmos
    assert _livres(doc) == livres
    for k in ("reta1", "reta2", "desenv_int", "desenv_ext", "raio_int", "raio_ext"):
        assert abs(depois[k] - antes[k]) < 2.0, (k, antes[k], depois[k])
    # as facetas encostam umas nas outras (a fileira continua contínua para o detalhamento) e giraram junto
    assert M.analisar_modelo(doc)[0]["ajustadas"] == 2
    # cada peça guarda os vértices originais e as faces ficaram como eram
    for e in doc.entidades.values():
        g = e.atributos[M.CHAVE]
        assert len(g["original"]["vertices"]) == len(e.vertices) == 8 and len(e.faces) == 6
        assert g["raio_int"] == RAIO_INTERNO_COMERCIAL and abs(g["raio_modelo"] - R_MODELO) < 0.03 * R_MODELO
    # a largura (eixo y) não muda
    ys = sorted({round(v[1], 3) for e in doc.entidades.values() for v in e.vertices})
    assert ys == [-500.0, 500.0, 700.0, 1700.0]


def test_aplicar_de_novo_parte_do_original_e_voltar_restaura():
    doc = _doc(1)
    orig = {e.id: [tuple(v) for v in e.vertices] for e in doc.entidades.values()}
    M.ajustar_modelo(doc)
    r2 = M.ajustar_modelo(doc, raio_int=600.0)                 # outro raio: parte do original guardado
    assert r2["instancias"] == 1
    t = multidobras(list(doc.entidades.values()))["telhas"][0]
    assert abs(t["raio_modelo"] - (600.0 + H / 2)) < 0.02 * 620
    d = M.desfazer_modelo(doc)
    assert d["pecas"] == 8
    for e in doc.entidades.values():
        assert [tuple(v) for v in e.vertices] == orig[e.id]
        assert M.CHAVE not in e.atributos
    assert M.analisar_modelo(doc)[0]["ajustadas"] == 0
    # só os conjuntos pedidos
    assert M.ajustar_modelo(doc, conjuntos=["M9"])["instancias"] == 0
    assert M.ajustar_modelo(doc, conjuntos=["M1"])["instancias"] == 1
