# -*- coding: utf-8 -*-
"""A conferência do modelo antes de detalhar (onda 4, 14/10/2026): colisão pela forma, execução das ligações (borda,
passo, parafuso sem furo, furo sem parafuso, espaço da chave) e produção (sem marca, a conferir, fora da lista, conjunto
sem principal)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Barra, Chapa, Documento, Solido  # noqa: E402
from nucleo3d import conferencia_producao as CP  # noqa: E402
from nucleo3d.lancamento import _parafuso_solido  # noqa: E402

W = "W 250×32,7"          # d 258, bf 146


def _doc(*ents):
    d = Documento()
    for e in ents:
        d.add(e)
    return d


def _regras(r):
    return sorted({a["regra"] for a in r["achados"]})


def _bolt(c, eixo, d, L):
    s = _parafuso_solido(c, eixo, d, L, "ASTM A325")
    s.atributos["parafuso"].update(ponto=list(c), eixo=list(eixo))
    return s


def test_barras_se_atravessando_e_barra_apoiada_em_outra():
    a = Barra(inicio=(0, 0, 0), fim=(4000, 0, 0), perfil=W)
    b = Barra(inicio=(2000, -2000, 0), fim=(2000, 2000, 0), perfil=W)              # cruza no mesmo nível: colisão
    c = Barra(inicio=(1000, -2000, 129 + 129), fim=(1000, 2000, 129 + 129), perfil=W)  # em cima, encostada: não
    r = CP.conferir(_doc(a, b, c), quais=("colisao",))
    pares = [set(x["ids"]) for x in r["achados"]]
    assert {a.id, b.id} in pares and {a.id, c.id} not in pares
    assert any(x["regra"] == "colisao_funda" for x in r["achados"])


def test_chapa_soldada_encostada_nao_e_colisao_mas_enterrada_e():
    viga = Barra(inicio=(0, 0, 0), fim=(4000, 0, 0), perfil=W)
    encostada = Chapa(origem=(1000, -73, 129), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0), contorno=[(0, 0), (200, 0), (200, 146), (0, 146)],
                      espessura=10, centrada=False)
    enterrada = Chapa(origem=(2500, -73, 124), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0), contorno=[(0, 0), (200, 0), (200, 146), (0, 146)],
                      espessura=10, centrada=False)                                   # 5 mm dentro da mesa
    r = CP.conferir(_doc(viga, encostada, enterrada), quais=("colisao",))
    pares = [set(x["ids"]) for x in r["achados"]]
    assert {viga.id, enterrada.id} in pares and {viga.id, encostada.id} not in pares


def _chapa_com_furos(furos, origem=(0, 0, 0)):
    return Chapa(origem=origem, eixo_x=(1, 0, 0), eixo_y=(0, 1, 0), contorno=[(0, 0), (200, 0), (200, 150), (0, 150)],
                 espessura=12.5, centrada=False, furos=[{"x": x, "y": y, "diametro": 17.5} for x, y in furos])


def test_execucao_borda_passo_furo_e_parafuso():
    ch = _chapa_com_furos([(15, 75), (100, 75), (130, 75), (170, 120)])
    b1 = _bolt((15, 75, 6), (0, 0, 1), 16, 40)        # furo a 15 da borda: mínimo 28 (M16 cortada)
    b2 = _bolt((100, 75, 6), (0, 0, 1), 16, 40)
    b3 = _bolt((130, 75, 6), (0, 0, 1), 16, 40)       # 30 do b2: mínimo 2,7 × 16 = 43
    b4 = _bolt((60, 30, 6), (0, 0, 1), 16, 40)        # sem furo nessa posição
    r = CP.conferir(_doc(ch, b1, b2, b3, b4), quais=("execucao",))
    regras = _regras(r)
    assert "borda" in regras and "passo" in regras and "parafuso_sem_furo" in regras
    assert "furo_sem_parafuso" in regras                                          # o furo de (170, 120)
    borda = next(a for a in r["achados"] if a["regra"] == "borda")
    assert b1.id in borda["ids"]


def test_furo_do_chumbador_nao_e_furo_sem_parafuso():
    ch = _chapa_com_furos([(100, 75)])
    ch.furos = [{"x": 100, "y": 75, "diametro": 25}]
    cb = Barra(inicio=(100, 75, 120), fim=(100, 75, -480), perfil="FE RED 3/4''", papel="chumbador")
    r = CP.conferir(_doc(ch, cb), quais=("execucao",))
    assert "furo_sem_parafuso" not in _regras(r)


def test_parafuso_sem_espaco_para_a_chave():
    ch = _chapa_com_furos([(100, 75)])
    b = _bolt((100, 75, 6), (0, 0, 1), 16, 40)
    # uma barra logo acima da porca, colada nela
    tampa = Barra(inicio=(0, 75, 26 + 129 + 2), fim=(200, 75, 26 + 129 + 2), perfil=W)
    r = CP.conferir(_doc(ch, b, tampa), quais=("execucao",))
    assert "chave" in _regras(r)
    r = CP.conferir(_doc(_chapa_com_furos([(100, 75)]), _bolt((100, 75, 6), (0, 0, 1), 16, 40)), quais=("execucao",))
    assert "chave" not in _regras(r)


def test_producao_sem_marca_conferir_fora_da_lista_e_principal():
    a = Barra(inicio=(0, 0, 0), fim=(3000, 0, 0), perfil=W)
    b = Barra(inicio=(0, 1000, 0), fim=(3000, 1000, 0), perfil=W,
              atributos={"marcas": {"posicao": "P1", "conjunto": "M1", "instancia": "c1"}, "marca_a_conferir": True})
    vs = [(x, y, z) for z in (0, 50) for (x, y) in ((0, 0), (100, 0), (100, 100), (0, 100))]
    fs = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    calco = Solido(nome="calço", vertices=vs, faces=fs)
    r = CP.conferir(_doc(a, b, calco), quais=("producao",))
    assert _regras(r) == ["fora_da_lista", "marca_a_conferir", "sem_marca", "sem_principal"]
    sem = next(x for x in r["achados"] if x["regra"] == "sem_marca")
    assert sem["ids"] == [a.id]
