# -*- coding: utf-8 -*-
"""Treliças planas em linha não viram uma "tesoura montada" (Hora Certa · Galpão Existente, 29/10: as 12 treliças de
ligação TS01, de 3,05 a 3,90 m entre as faces dos pilares, saíram na prancha como uma "T4" de 46,3 m). A tesoura montada
junta as duas águas no mesmo plano; a faixa reta (contorno de cima e de baixo constantes — as vigas emendadas em linha do
Vicente) não. A chapa de apoio de cada ponta, mais alta que a treliça (830 × 650), quebrava a faixa: agora ela olha só as
barras."""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Barra, Chapa, Documento  # noqa: E402
from nucleo2d.detalhe import base, conjuntos  # noqa: E402

BANZO, ALMA = "U 75×40×3,00 (FF)", "U 50×25×2,00 (FF)"
L, H, VAO = 3700.0, 650.0, 250.0           # a treliça, a altura entre eixos dos banzos, a largura do pilar entre duas


def _barra(doc, a, b, perfil, pos, inst):
    br = Barra(inicio=a, fim=b, perfil=perfil, papel="barra", nome=pos)
    br.atributos = {"marcas": {"posicao": pos, "conjunto": "TS", "perfil": perfil, "instancia": inst}, "tipo_ifc": "IfcMember"}
    doc.add(br)


def _chapa(doc, x, pos, inst):
    ch = Chapa(origem=(x, -97.5, -90.0), eixo_x=(0.0, 1.0, 0.0), eixo_y=(0.0, 0.0, 1.0),
               contorno=[(0.0, 0.0), (195.0, 0.0), (195.0, 830.0), (0.0, 830.0)], espessura=8.0, centrada=True)
    ch.atributos = {"marcas": {"posicao": pos, "conjunto": "TS", "perfil": "CH 8", "instancia": inst}, "tipo_ifc": "IfcPlate"}
    doc.add(ch)


def _trelica(doc, x0, inst, inclinada=0.0):
    """treliça plana no plano y = 0, de x0 a x0 + L; `inclinada` sobe o banzo de cima (mm por mm) — a água"""
    z1 = lambda x: H + (x - x0) * inclinada                      # noqa: E731
    _barra(doc, (x0, 0.0, 0.0), (x0 + L, 0.0, 0.0), BANZO, "BI", inst)
    _barra(doc, (x0, 0.0, z1(x0)), (x0 + L, 0.0, z1(x0 + L)), BANZO, "BS", inst)
    n = 6
    for i in range(n + 1):
        x = x0 + L * i / n
        _barra(doc, (x, 0.0, 0.0), (x, 0.0, z1(x)), ALMA, "M", inst)
    if not inclinada:
        _chapa(doc, x0 - 4.0, "CHA", inst)
        _chapa(doc, x0 + L + 4.0, "CHA", inst)


def _montadas(doc):
    pecas, _ = base._pecas(doc)
    lista = [e for e in pecas if base._marcas(e).get("conjunto") == "TS"]
    por_inst = collections.defaultdict(collections.Counter)
    for e in lista:
        por_inst[base._marcas(e)["instancia"]][base._marcas(e)["posicao"]] += 1
    unidade = next(iter(por_inst.values()))
    return conjuntos.tesouras_montadas([("TS", lista, unidade)])


def test_trelicas_planas_em_linha_com_chapa_de_apoio_nao_viram_uma_tesoura():
    doc = Documento(nome="ts01")
    for k in range(4):                                           # quatro vãos entre pilares, na mesma linha
        _trelica(doc, k * (L + VAO), "TS#%d" % k)
    montadas, cobertas = _montadas(doc)
    assert montadas == [] and cobertas == set(), montadas


def test_as_duas_aguas_continuam_uma_tesoura_montada():
    # o controle: as duas meias de uma tesoura com caída, no mesmo plano e encostadas, continuam juntas
    doc = Documento(nome="tesoura")
    _trelica(doc, 0.0, "T#0", inclinada=0.10)
    _trelica(doc, L + 50.0, "T#1", inclinada=-0.10)
    montadas, _ = _montadas(doc)
    assert len(montadas) == 1 and montadas[0]["n"] == 1
