# -*- coding: utf-8 -*-
"""A prancha arrumada à mão volta na remontagem também girada e com partes mexidas (ME Sooro · Sala de Compressores,
12/11: o usuário revisou a prancha das telhas — a FACE 1 deitada a −90° ao lado dos tipos, com a moldura num canto,
o desenho da CU1 e do MD1 puxados dentro da célula, a FACES 2 E 3 apagada — e a remontagem desfez tudo: "célula
montada de outro jeito: nada aprendido" e "descartado: o gerador mudou a célula"). nucleo2d/ajustes_pranchas:
o movimento da célula é o que a maioria das entidades fez (movimento_da_celula), com o giro; o giro leva os textos,
os arcos e a cota h↔v; a célula que o gerador mudou continua onde o usuário a pôs (test_ajustes_pranchas).

A revisão de verdade está em testes/dados_cad/sooro_telhas_revisao_12-11.json (as células dela, com o que o gerador
tinha feito); a remontagem inteira da Sala, numa cópia, voltou 100 % no lugar nas células TIPOS, FACE 1, MD1 e CU1."""
import copy
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import ajustes_pranchas as AP                                         # noqa: E402
from nucleo2d.desenho import Cota, Desenho, Linha, Polilinha, Texto                 # noqa: E402

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_cad", "sooro_telhas_revisao_12-11.json")


def _revisao():
    r = json.load(open(DADOS, encoding="utf-8"))
    return Desenho.de_dict(r["desenho"]), {"impressoes": r["impressoes"]}


def _cel(aj, trecho):
    return next(v for k, v in aj["celulas"].items() if trecho in k)


def test_a_revisao_da_sala_e_aprendida():
    antigo, aj = _revisao()
    r = AP.aprender(antigo, aj)
    face1 = _cel(r, "FACE 1 – COBERTURA")
    assert face1.get("r") == -90.0 and face1["s"] == 1.0                        # deitada, sem escala
    assert len(face1["ents"]) == 4                                             # a moldura e o título à parte
    md1 = _cel(r, "MD1 – 64x")
    assert md1["s"] == 1.0 and "r" not in md1 and md1["d"] == pytest.approx([-7.8, 18.6], abs=0.05)   # era "× 1,031"
    cu1 = _cel(r, "|titulo:CU1")
    assert cu1["s"] == 1.0 and cu1["d"] == pytest.approx([522.7, 268.0], abs=0.05)                    # era "× 0,734"
    assert sum(1 for v in cu1["ents"].values() if "d" in v) == 4                 # o desenho puxado 24 mm para dentro
    assert any(v.get("x") == "CUM1 – 32x" for v in cu1["ents"].values())         # e o título trocado
    assert _cel(r, "FACES 2 E 3").get("apagada")
    assert not any("montada de outro jeito" in x["ajuste"] for x in r["diario"])


def test_movimento_pela_maioria():
    o = (100.0, 100.0)
    G = [(100.0 + i * 10.0, 100.0 + (i % 3) * 7.0) for i in range(10)]
    # 7 andaram (30, −5); 3 (o texto) andaram mais 20 para a direita
    C = [(g[0] + 30.0 + (20.0 if i >= 7 else 0.0), g[1] - 5.0) for i, g in enumerate(G)]
    s, giro, d, k = AP.movimento_da_celula(G, C, o)
    assert (s, giro, k) == (1.0, 0.0, 7) and d == pytest.approx((30.0, -5.0))
    # girada 90° em volta da origem e levada (0, 50): todas seguem
    C = [(o[0] - (g[1] - o[1]), o[1] + (g[0] - o[0]) + 50.0) for g in G]
    s, giro, d, k = AP.movimento_da_celula(G, C, o)
    assert (s, giro, k) == (1.0, 90.0, 10) and d == pytest.approx((0.0, 50.0), abs=1e-6)


SITUACOES = [(0.0, 0.0), (1218181.0, 211836.0)]


def _gerado(ox, oy, geracao):
    """uma célula de telha (o desenho, uma cota h, um texto) e a moldura com o título, como a montagem deixa"""
    d = Desenho(nome="Pranchas", escala=1.0)
    d.metadados["geracao"] = geracao
    cel = "detalhamento-telhas|titulo:FACE 1"
    at = {"cel": cel, "fonte": "detalhamento-telhas", "prancha_numero": 1}
    x0, y0 = ox + 100.0, oy + 100.0
    d.add(Polilinha(id="moldura", camada="PRANCHA", vertices=[(x0, y0), (x0 + 200, y0), (x0 + 200, y0 + 120), (x0, y0 + 120)],
                    fechada=True, atributos=dict(at, prancha="celula")))
    d.add(Texto(id="titulo", camada="TEXTO", posicao=(x0 + 3, y0 + 112), texto="FACE 1 – COBERTURA", altura=3.0, atributos=dict(at)))
    for i in range(6):
        d.add(Polilinha(id="tl%d" % i, camada="TELHAS", vertices=[(x0 + 20 + 25 * i, y0 + 10), (x0 + 40 + 25 * i, y0 + 10),
                                                                    (x0 + 40 + 25 * i, y0 + 90), (x0 + 20 + 25 * i, y0 + 90)],
                        fechada=True, atributos=dict(at)))
        d.add(Texto(id="m%d" % i, camada="TEXTO", posicao=(x0 + 22 + 25 * i, y0 + 50), texto="TL%d" % (i + 1), altura=2.0, atributos=dict(at)))
    d.add(Cota(id="cota", camada="COTA", modo="h", p1=(x0 + 20, y0 + 10), p2=(x0 + 165, y0 + 10), deslocamento=-6.0,
               texto="5800", altura=2.5, atributos=dict(at)))
    d.metadados["pranchas"] = [{"numero": 1, "celulas": [{"titulo": cel, "id": cel, "caixa": [x0, y0, x0 + 200, y0 + 120]}]}]
    return d, cel


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_girada_com_a_moldura_a_parte_volta_igual(ox, oy):
    g1, cel = _gerado(ox, oy, "g1")
    imp = AP.marcar(g1)
    ed = Desenho.de_dict(copy.deepcopy(g1.dict()))
    centro = (ox + 300.0, oy + 400.0)
    gira = AP._levar(centro, 1.0, -90.0, (0.0, 0.0))                 # o desenho deitado a −90° em volta de um ponto
    for e in list(ed.entidades.values()):
        if e.id in ("moldura", "titulo"):
            AP._transformar(e, lambda p: (p[0] + 500.0, p[1] - 30.0))   # a moldura e o título num canto à parte
        else:
            AP._transformar(e, gira, 1.0, -90.0)
    aj = AP.aprender(ed, {"impressoes": {"g1": imp}})
    assert aj["celulas"][cel]["r"] == -90.0 and len(aj["celulas"][cel]["ents"]) == 2
    g2, _ = _gerado(ox, oy, "g2")
    AP.marcar(g2)
    rel = AP.aplicar(g2, aj)
    assert rel["celulas"] == 1 and not rel.get("descartadas")
    for e in ed.entidades.values():
        n = g2.entidades[e.id]
        assert AP._pontos(n) == pytest.approx(AP._pontos(e), abs=1e-3), e.id
    assert g2.entidades["m0"].angulo == pytest.approx(270.0)              # o texto deitado junto (−90°, como o CAD escreve)
    assert g2.entidades["titulo"].angulo == pytest.approx(0.0)            # o título só andou
    assert g2.entidades["cota"].modo == "v"                               # a cota horizontal virou vertical
    assert g2.entidades["cota"].texto == "5800"


def test_giro_nos_objetos():
    t = Texto(posicao=(10.0, 0.0), texto="A", angulo=30.0)
    AP._transformar(t, AP._levar((0.0, 0.0), 1.0, 90.0), 1.0, 90.0)
    assert t.posicao == pytest.approx((0.0, 10.0)) and t.angulo == pytest.approx(120.0)
    c = Cota(modo="v", p1=(0.0, 0.0), p2=(0.0, 10.0))
    AP._transformar(c, AP._levar((0.0, 0.0), 1.0, -90.0), 1.0, -90.0)
    assert c.modo == "h" and c.p2 == pytest.approx((10.0, 0.0))
    c = Cota(modo="h", p1=(0.0, 0.0), p2=(10.0, 0.0))
    AP._transformar(c, AP._levar((0.0, 0.0), 1.0, 180.0), 1.0, 180.0)
    assert c.modo == "h"
    linha = Linha(a=(0.0, 0.0), b=(10.0, 0.0))
    AP._transformar(linha, AP._levar((0.0, 0.0), 2.0, 90.0, (5.0, 5.0)), 2.0, 90.0)
    assert linha.b == pytest.approx((5.0, 25.0))


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_o_solto_cai_quando_o_gerador_poe_a_celula_em_outro_lugar(ox, oy):
    """A prancha padrão de telhas (12/11) põe a FACE 1 de pé noutro lugar: o movimento e o giro aprendidos caem, e a
    moldura "solta" (medida na folha) cai junto — ficava no alto da prancha, longe da célula."""
    g1, cel = _gerado(ox, oy, "g1")
    imp = AP.marcar(g1)
    ed = Desenho.de_dict(copy.deepcopy(g1.dict()))
    gira = AP._levar((ox + 300.0, oy + 400.0), 1.0, -90.0, (0.0, 0.0))
    for e in list(ed.entidades.values()):
        if e.id in ("moldura", "titulo"):
            AP._transformar(e, lambda p: (p[0] + 500.0, p[1] - 30.0))
        else:
            AP._transformar(e, gira, 1.0, -90.0)
    aj = AP.aprender(ed, {"impressoes": {"g1": imp}})
    g2, _ = _gerado(ox + 400.0, oy, "g2")                                # a montagem nova põe a célula 400 mm adiante
    AP.marcar(g2)
    antes = {k: AP._pontos(e) for k, e in g2.entidades.items()}
    rel = AP.aplicar(g2, aj)
    assert rel["descartadas"] == 1
    assert all(AP._pontos(g2.entidades[k]) == pytest.approx(antes[k]) for k in antes)   # como a montagem a pôs
