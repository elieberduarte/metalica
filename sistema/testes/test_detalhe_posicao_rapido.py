# -*- coding: utf-8 -*-
"""O detalhe de uma posição (o Editar chapa, o duplo clique) só monta as peças da marca e os parafusos perto delas
(15/10/2026: montar a obra inteira levava 15 s na PRATI): o desenho tem de sair igual ao do caminho completo."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Barra, Chapa, Documento, Solido  # noqa: E402
from nucleo3d import geometria as G  # noqa: E402
from nucleo2d.detalhe import celulas  # noqa: E402
from nucleo2d.detalhe.base import _pecas, _fixadores, _posicoes_de, _marcas  # noqa: E402


def _parafuso(x, y, z, comp=60.0, d=16.0):
    """um parafuso em pé (eixo em z) como sólido, do jeito que vem do IFC"""
    r = d / 2.0
    pts = [(x + r * dx, y + r * dy, z) for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))]
    s = G.prisma(pts, (0.0, 0.0, comp), nome="BOLT %gx%g" % (d, comp), camada="Parafusos", material="Aço")
    s.atributos = {"tipo_ifc": "IfcMechanicalFastener"}
    return s


def _modelo():
    doc = Documento()
    for k, x in enumerate((0.0, 5000.0)):
        ch = Chapa(nome="CH 200×160×9,5", origem=(x, 0.0, 0.0), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0),
                   contorno=[(0, 0), (200, 0), (200, 160), (0, 160)], espessura=9.5, centrada=False,
                   furos=[{"x": 100, "y": 80, "diametro": 18}], atributos={"marcas": {"posicao": "P1"}})
        doc.add(ch)
    doc.add(_parafuso(100.0, 80.0, -20.0))          # atravessa a primeira P1
    doc.add(_parafuso(20000.0, 0.0, 0.0))           # longe de tudo
    # barras sem marca: o mesmo nome com dois comprimentos (as variantes "nome · comprimento")
    for k in range(30):
        L = 3000.0 if k % 2 else 4500.0
        doc.add(Barra(nome="Terça", inicio=(0, 1000 + 100 * k, 500), fim=(L, 1000 + 100 * k, 500), perfil="Ue 150×60×20×2,25", papel="terça"))
    return doc


def _completo(doc, marca):
    """o caminho antigo: a obra inteira montada e todos os parafusos"""
    pecas, _ = _pecas(doc)
    lista = [e for e in pecas if str(_marcas(e).get("posicao") or e.nome or e.id) == marca]
    posicoes, _c = _posicoes_de(lista, _fixadores(doc))
    return posicoes[0]


def _foto(pos):
    return json.dumps({"q": pos.quantidade, "L": round(pos.L, 2), "H": round(pos.H, 2), "T": round(pos.T, 2),
                       "furos": sorted((round(f.x, 1), round(f.y, 1), round(f.d, 1), f.vista) for f in pos.furos)}, sort_keys=True)


def test_a_chapa_sai_igual_ao_caminho_completo_com_o_furo_do_parafuso_perto():
    doc = _modelo()
    _d, pos = celulas.detalhar_posicao(doc, "P1")
    assert _foto(pos) == _foto(_completo(doc, "P1"))
    assert pos.quantidade == 2 and pos.furos


def test_as_barras_sem_marca_com_variantes_saem_iguais():
    doc = _modelo()
    pecas, _ = _pecas(doc)
    marcas = sorted({str(_marcas(e).get("posicao") or e.nome or e.id) for e in pecas if "Terça" in (e.nome or "")})
    assert len(marcas) == 2                          # os dois comprimentos, cada um uma posição
    for m in marcas:
        _d, pos = celulas.detalhar_posicao(doc, m)
        assert _foto(pos) == _foto(_completo(doc, m)), m


def test_so_os_parafusos_perto_entram():
    doc = _modelo()
    pecas, _ = _pecas(doc)
    lista = [e for e in pecas if _marcas(e).get("posicao") == "P1"]
    perto = celulas._fixadores_perto(_fixadores(doc), lista)
    assert len(perto) == 1 and len(_fixadores(doc)) == 2
