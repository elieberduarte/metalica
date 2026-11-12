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


def _oitao(y0=-480.0, x0=600.0, x1=780.0, conjunto="OIT"):
    """A telha do oitão em pé no plano y = y0, debaixo da curva do TecnoMETAL: o topo cortado na face de baixo do arco
    de R_MODELO (o raio de dentro, R − H/2, centro (0, −R)) e o pé na base da parede."""
    def topo(x):
        return -R_MODELO + math.sqrt((R_MODELO - H / 2) ** 2 - x ** 2)
    vs = []
    for y in (y0 - 10.0, y0 + 10.0):
        vs += [(x0, y, -R_MODELO - 600.0), (x1, y, -R_MODELO - 600.0), (x1, y, topo(x1)), (x0, y, topo(x0))]
    faces = [[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
    return Solido(nome="TELHA TP40 0.50MM", camada="Telhas", vertices=vs, faces=faces,
                  atributos={"tipo_ifc": "IfcPlate", "marcas": {"posicao": "OI", "conjunto": conjunto, "perfil": "TELHA TP40 0.50MM"}})


def test_oitao_acompanha_a_curva_nova_sem_abrir_vao():
    """Sala de Compressores (12/11, "ficou uma abertura, olhando no original não tinha isso"): o R450 levanta o arco
    junto da parede e o topo do oitão, cortado no arco do modelo, ficava até 30 cm abaixo dele. O topo sobe com a curva
    e o voltar ao original o devolve."""
    doc = _doc(1)
    oit = _oitao()
    doc.add(oit)
    orig = [tuple(v) for v in oit.vertices]
    r = M.ajustar_modelo(doc)
    assert r["oitao"] == 1
    # a face de baixo do arco novo: raio de dentro RAIO_INTERNO_COMERCIAL, centro a R da linha média do vértice (800, 0)
    Rm = RAIO_INTERNO_COMERCIAL + H / 2
    cx, cz = R_MODELO - Rm, -Rm

    def fundo_novo(x):
        return cz + math.sqrt(RAIO_INTERNO_COMERCIAL ** 2 - (x - cx) ** 2)
    for v, v0 in zip(oit.vertices, orig):
        if v0[2] > -R_MODELO - 600.0 + 1:                       # os do topo
            assert abs(v[2] - fundo_novo(v[0])) < 20.0, (v, fundo_novo(v[0]))
            assert v[2] - v0[2] > 150.0                         # sem isso ficava o vão (192 mm em x = 600)
        else:
            assert v == v0                                      # o pé não se move
    assert M.desfazer_modelo(doc)["pecas"] == 9
    assert [tuple(v) for v in oit.vertices] == orig and M.CHAVE not in oit.atributos


def test_oitao_longe_do_arco_antigo_tambem_sobe_ate_a_curva_nova():
    """Sala de Compressores (12/11, "A telha precisa seguir a multidobra"): o TecnoMETAL deixa pontos do topo do oitão
    longe do arco antigo, por dentro da reta da parede; a conta pelo arco antigo não os movia e, junto da parede, eles
    ficavam até 100 mm abaixo do arco novo — uma abertura. Todo ponto do topo perto da curva sobe até ela (e entra na
    onda); o pé não sobe."""
    doc = _doc(1)
    x = 700.0
    z_velho = -R_MODELO + math.sqrt((R_MODELO - H / 2) ** 2 - x ** 2) + 150.0     # 150 acima do arco antigo
    vs = []
    for y in (-490.0, -470.0):
        vs += [(x - 20, y, -R_MODELO - 600.0), (x + 20, y, -R_MODELO - 600.0), (x + 20, y, z_velho), (x - 20, y, z_velho)]
    oit = Solido(nome="TELHA TP40 0.50MM", camada="Telhas", vertices=vs,
                 faces=[[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]],
                 atributos={"tipo_ifc": "IfcPlate", "marcas": {"posicao": "OI", "conjunto": "OIT", "perfil": "TELHA TP40 0.50MM"}})
    doc.add(oit)
    M.ajustar_modelo(doc)
    Rm = RAIO_INTERNO_COMERCIAL + H / 2
    cx, cz = R_MODELO - Rm, -Rm
    for v in oit.vertices:
        if v[2] > -R_MODELO - 600.0 + 1:
            fundo = cz + math.sqrt(RAIO_INTERNO_COMERCIAL ** 2 - (v[0] - cx) ** 2)
            assert v[2] >= fundo - 15.0, (v, fundo)          # sem a correção: 92 mm abaixo do arco novo
        else:
            assert abs(v[2] - (-R_MODELO - 600.0)) < 1e-6
