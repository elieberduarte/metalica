# -*- coding: utf-8 -*-
"""Malhas locais de eixos (Hora Certa · Galpão Existente, montador 29/10, M15): a obra com frentes fora da malha
principal — a ampliação girada −2,25° a 70 m do mezanino — ganha uma malha própria por frente (`eixos.malhas`), e a
planta de chumbação loca cada base pela malha dela, numa planta por malha. Antes: "8790 do eixo A para fora da malha;
73481 do eixo 1 para fora da malha", a obra inteira numa planta a 1:500."""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Solido                        # noqa: E402
from nucleo3d import eixos as E                                      # noqa: E402
from nucleo2d.desenho import Texto                                   # noqa: E402
from nucleo2d.detalhe.conjuntos import desenho_de_chumbacao          # noqa: E402

GIRO = math.radians(-2.25)
G = (math.cos(GIRO), math.sin(GIRO))            # ao longo da ampliação girada
P = (-G[1], G[0])


def _caixa(cx, cy, z0, z1, meia, nome, posicao):
    v = [(cx + dx, cy + dy, z) for z in (z0, z1) for dx, dy in ((-meia, -meia), (meia, -meia), (meia, meia), (-meia, meia))]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return Solido(nome=nome, camada="Chumbadores", vertices=v, faces=f,
                  atributos={"tipo_ifc": "IfcBeam", "marcas": {"posicao": posicao, "conjunto": posicao, "perfil": nome}})


def _eixos():
    """Mezanino 1–2 × A–B (ortogonal, perto da origem) e a ampliação AP1–AP3 × APA a ~70 m, girada: as linhas
    numeradas atravessam a ampliação (eixo_g ao longo dela, P)."""
    pos_ap = [0.0, 4850.0, 9560.0]
    base = (-70000.0, 2000.0)                               # o cruzamento AP1/APA
    q = base[0] * P[0] + base[1] * P[1]                     # posição de AP1 ao longo da ampliação
    l_apa = base[0] * (-G[0]) + base[1] * (-G[1])           # perp de P = (-P[1], P[0]) = -G
    bruto = {"eixo_g": [1.0, 0.0], "z_base": 0.0, "origem": "planta",
             "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6000.0}],
             "letras": [{"nome": "A", "pos": 8000.0}, {"nome": "B", "pos": 0.0}],
             "malhas": [{"nome": "Ampliação", "descricao": "eixos nossos, a conferir com o projetista",
                         "eixo_g": [P[0], P[1]],
                         "numeros": [{"nome": "AP%d" % (k + 1), "pos": q + s} for k, s in enumerate(pos_ap)],
                         "letras": [{"nome": "APA", "pos": l_apa}, {"nome": "APB", "pos": l_apa - 6880.0}]}]}
    pontos_ap = [(base[0] + P[0] * s, base[1] + P[1] * s) for s in pos_ap]
    return bruto, pontos_ap


def _modelo(pontos_ap):
    doc = Documento(nome="malhas")
    for x, y in ((0.0, 0.0), (6000.0, 0.0), (0.0, 8000.0), (6000.0, 8000.0)):
        doc.add(_caixa(x, y, -500, 100, 15, "FE RED 1/2''", "M1"))
    for k, (x, y) in enumerate(pontos_ap):
        # a ampliação: a base do AP2 a 120 mm da linha APA (para o lado da APB), as outras no eixo
        dx = -G[0] * 0.0 + (G[0] * 120.0 if k == 1 else 0.0)
        dy = (G[1] * 120.0 if k == 1 else 0.0)
        doc.add(_caixa(x + dx, y + dy, -900, 100, 18, "FE RED 36", "M2"))
    nomes = {"tipos": {"M1": "chumbador", "M2": "chumbador"}, "ifc": {"M1": "CB1", "M2": "CB3"}}
    return doc, nomes


def test_de_dict_guarda_as_malhas_locais():
    bruto, _pts = _eixos()
    ex = E.de_dict(bruto)
    assert len(ex.get("malhas") or []) == 1
    m = ex["malhas"][0]
    assert m["nome"] == "Ampliação" and [n["nome"] for n in m["numeros"]] == ["AP1", "AP2", "AP3"]
    assert m["descricao"].startswith("eixos nossos")
    segs = E.segmentos(ex)
    assert sum(1 for s in segs if s.get("malha") == "Ampliação") == 5 and sum(1 for s in segs if not s.get("malha")) == 4
    ref = E.referencia_da_malha(m, E.malhas_de(ex)[0])
    assert "AP1/APA" in ref and "girada -2,25°" in ref, ref


def test_onde_pela_malha_do_ponto():
    bruto, pts = _eixos()
    segs = E.segmentos(E.de_dict(bruto))
    assert E.onde(pts[2], segs) == "eixos AP3 / APA"
    assert E.onde((6000.0, 8000.0), segs) == "eixos 2 / A"


def test_chumbacao_uma_planta_por_malha_e_locacao_pela_malha_local():
    bruto, pts = _eixos()
    doc, nomes = _modelo(pts)
    pecas = [e for e in doc.entidades.values() if isinstance(e, Solido)]
    ch = desenho_de_chumbacao(doc, pecas, nomes, eixos=bruto, nomes=nomes["ifc"])
    titulos = [v["nome"] for v in ch.vistas]
    assert titulos == ["PLANTA DE CHUMBAÇÃO", "PLANTA DE CHUMBAÇÃO — AMPLIAÇÃO"], titulos
    assert len(ch.metadados["celulas"]) == 2
    textos = [e.texto for e in ch.entidades.values() if isinstance(e, Texto)]
    quadro = [t for t in textos if t.startswith("CB3 em")]
    assert len(quadro) == 3, quadro
    # nenhuma base locada a mais de 15 m de um eixo, nenhuma "para fora da malha"
    for t in quadro + [t for t in textos if t.startswith("CB1 em")]:
        assert "fora da malha" not in t, t
        assert all(int(n) <= 15000 for n in re.findall(r"(\d+) do eixo", t)), t
    assert any("APA-AP2" in t and "120 do eixo APA para o APB" in t for t in quadro), quadro
    assert any(t.startswith("MALHA LOCAL") and "a conferir com o projetista" in t for t in textos)
    # a planta da ampliação na escala dela: a obra inteira numa planta só ia a 1:500
    assert ch.escala <= 100.0, ch.escala


def test_sem_malhas_locais_a_chumbacao_fica_como_era():
    bruto, pts = _eixos()
    sem = {k: v for k, v in bruto.items() if k != "malhas"}
    doc, nomes = _modelo([])
    pecas = [e for e in doc.entidades.values() if isinstance(e, Solido)]
    ch = desenho_de_chumbacao(doc, pecas, nomes, eixos=sem, nomes=nomes["ifc"])
    assert [v["nome"] for v in ch.vistas] == ["PLANTA DE CHUMBAÇÃO"] and len(ch.metadados["celulas"]) == 1


def test_gravar_no_dialogo_nao_apaga_as_malhas_locais():
    """O diálogo de eixos manda só a malha principal: gravar lá não pode levar embora as malhas das frentes."""
    import tempfile
    import app
    from projetos import Projetos
    antigo = app.PROJETOS
    app.PROJETOS = tempfile.mkdtemp(prefix="malhas_locais_")
    try:
        g = Projetos(app.PROJETOS)
        s = g.criar("Malhas", tipo="desenho")["slug"]
        bruto, _pts = _eixos()
        g._atualizar(s, eixos=bruto)
        app.gravar_eixos_projeto(s, {"eixos": {k: v for k, v in bruto.items() if k != "malhas"}})
        lido = E.de_dict(g.ler(s)["eixos"])
        assert [m["nome"] for m in lido.get("malhas") or []] == ["Ampliação"]
    finally:
        app.PROJETOS = antigo


def test_base_no_canto_de_duas_malhas_fica_inteira_numa_planta():
    """O P5 da ampliação, no canto em que ela encosta na marquise (30/10): cada chumbador ia para a malha da linha mais
    perto e os 14 CB3 da base se dividiam entre as duas plantas. A base vai inteira, pelo centro do grupo."""
    bruto = {"eixo_g": [1.0, 0.0], "z_base": 0.0,
             "numeros": [{"nome": "1", "pos": 100000.0}, {"nome": "2", "pos": 106000.0}], "letras": [{"nome": "A", "pos": 0.0}],
             "malhas": [{"nome": "X", "eixo_g": [1.0, 0.0], "numeros": [{"nome": "X1", "pos": 0.0}, {"nome": "X2", "pos": 5000.0}],
                         "letras": [{"nome": "XA", "pos": 0.0}]},
                        {"nome": "Y", "eixo_g": [0.0, 1.0], "numeros": [{"nome": "Y1", "pos": 200.0}, {"nome": "Y2", "pos": 5000.0}],
                         "letras": [{"nome": "YA", "pos": -300.0}]}]}
    doc = Documento(nome="canto")
    for dx, dy in ((-100, -100), (100, -100), (100, 100), (-100, 100)):
        doc.add(_caixa(120.0 + dx, 40.0 + dy, -900, 100, 18, "FE RED 36", "M2"))
    nomes = {"tipos": {"M2": "chumbador"}, "ifc": {"M2": "CB3"}}
    pecas = [e for e in doc.entidades.values() if isinstance(e, Solido)]
    segs = E.segmentos(E.de_dict(bruto))
    lados = {E.malha_do_ponto((120.0 + dx, 40.0 + dy), segs)[0].get("malha") for dx, dy in ((-100, -100), (100, 100))}
    assert lados == {"X", "Y"}                        # um chumbador sozinho iria para cada uma
    ch = desenho_de_chumbacao(doc, pecas, nomes, eixos=bruto, nomes=nomes["ifc"])
    assert [v["nome"] for v in ch.vistas] == ["PLANTA DE CHUMBAÇÃO — X"], [v["nome"] for v in ch.vistas]
