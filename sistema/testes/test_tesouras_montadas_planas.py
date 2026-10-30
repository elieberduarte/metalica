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


# --- 30/10 (N.3): a reincidência do mesmo dia (montador M08) — a T1 de 20 m (MT1 + MT5) e a T2 de 16,5 m da Sala de
# Tintas, duas treliças planas em linha com o pilar entre elas, e a T3 de 14,7 m (MT13 + MT14), a TS02 emendada no nó

def _trelica_longa(doc, x0, comp, inst, maos_francesas=False, paineis=None):
    """treliça plana com diagonais e o papel de cada barra (papel_trelica), como a execução grava; `maos_francesas`:
    as duas da ponta, descendo do banzo de baixo para o pilar (fazem parte do conjunto da meia na Sala de Tintas)"""
    def barra(a, b, perfil, pos, papel):
        br = Barra(inicio=a, fim=b, perfil=perfil, papel="barra", nome=pos)
        br.atributos = {"marcas": {"posicao": pos, "conjunto": "TS", "perfil": perfil, "instancia": inst},
                        "tipo_ifc": "IfcMember", "papel_trelica": papel}
        doc.add(br)
    barra((x0, 0.0, 0.0), (x0 + comp, 0.0, 0.0), BANZO, "BI", "banzo")
    barra((x0, 0.0, 500.0), (x0 + comp, 0.0, 500.0), BANZO, "BS", "banzo")
    n = paineis or max(2, int(comp // 900))
    for i in range(n + 1):
        x = x0 + comp * i / n
        barra((x, 0.0, 0.0), (x, 0.0, 500.0), ALMA, "M", "montante")
        if i < n:
            barra((x, 0.0, 0.0), (x + comp / n, 0.0, 500.0), ALMA, "D", "diagonal")
    if maos_francesas:
        for xp, s in ((x0, 1.0), (x0 + comp, -1.0)):
            br = Barra(inicio=(xp + s * 450.0, 0.0, 0.0), fim=(xp + s * 30.0, 0.0, -480.0), perfil="L 50×5,00", papel="barra",
                       nome="MF")
            br.atributos = {"marcas": {"posicao": "MF", "conjunto": "TS", "perfil": "L 50×5,00", "instancia": inst},
                            "tipo_ifc": "IfcMember", "funcao": "mao_francesa"}
            doc.add(br)


def test_ts02_emendada_no_no_nao_vira_tesoura():
    """11,9 m + 2,9 m planas em linha: com os pontos a cada 1/8 da aresta, o banzo de 11,9 m deixava faixas sem o
    contorno de cima e a "faixa reta" falhava (a T3 de 14,7 m)"""
    doc = Documento(nome="ts02")
    _trelica_longa(doc, 0.0, 11864.0, "TS02-01A", paineis=13)
    _trelica_longa(doc, 11864.0 + 5.0, 2874.0, "TS02-01B", paineis=3)
    montadas, _ = _montadas_varias(doc)
    assert montadas == [], montadas


def test_trelicas_planas_com_maos_francesas_e_pilar_no_meio_nao_viram_tesoura():
    """duas de 10 m em linha encostadas no pilar do meio, cada uma com as mãos-francesas (abaixo do banzo) no conjunto"""
    doc = Documento(nome="sala-de-tintas")
    _trelica_longa(doc, 0.0, 9890.0, "ST-05-10", maos_francesas=True)
    _trelica_longa(doc, 9900.0, 10120.0, "ST-01-05", maos_francesas=True)
    montadas, _ = _montadas_varias(doc)
    assert montadas == [], montadas


def _montadas_varias(doc):
    """como `_montadas`, com cada instância como uma meia (as composições diferem entre os trechos)"""
    pecas, _ = base._pecas(doc)
    por_inst = collections.defaultdict(list)
    for e in pecas:
        por_inst[base._marcas(e)["instancia"]].append(e)
    meias = []
    for inst, lista in por_inst.items():
        for e in lista:
            m = dict(base._marcas(e))
            m["conjunto"] = inst
            e.atributos = dict(e.atributos or {}, marcas=m)
        meias.append((inst, lista, collections.Counter(base._marcas(e)["posicao"] for e in lista)))
    return conjuntos.tesouras_montadas(meias)
