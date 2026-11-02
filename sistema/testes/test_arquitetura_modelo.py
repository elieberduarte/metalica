# -*- coding: utf-8 -*-
"""Módulo de arquitetura — a parede dentro do modelo 3D (fase 1b, 30/10/2026): a definição em `atributos.arq`, o
`regenerar` pelo motor, a altura pelos níveis (ARQ-03), a área do ambiente pelas faces internas (ARQ-06), os códigos das
esquadrias e a casa piloto."""
import json

import pytest

from arquitetura import modelo as M
from arquitetura.piloto import montar_casa
from nucleo3d.modelo import Documento

NIVEIS = [{"nome": "Térreo", "cota": 0, "laje": 100}, {"nome": "Superior", "cota": 3350, "laje": 350}]


def _doc():
    d = Documento(nome="teste")
    M.definir_niveis(d, NIVEIS)
    return d


def test_parede_vai_do_piso_ao_fundo_da_laje_de_cima():
    """ARQ-03: base no piso do térreo (0), topo no fundo da laje do superior (3350 − 350 = 3000)"""
    d = _doc()
    p = M.nova_parede(d, (0, 0), (4000, 0), "EXT20", "Térreo", "Superior")
    M.regenerar(d)
    zs = [v[2] for v in p.vertices]
    assert (min(zs), max(zs)) == (0, 3000)
    assert p.atributos["arq"]["altura"] == [0, 3000]


def test_nivel_que_nao_existe_vira_aviso_e_nao_quebra():
    d = _doc()
    M.nova_parede(d, (0, 0), (4000, 0), "EXT20", "Térreo", "Mezanino", nome="P1")
    r = M.regenerar(d)
    assert any("Mezanino" in a for a in r["avisos"])


def test_ambiente_tem_area_pelas_faces_internas():
    """sala de 4,00 × 3,00 pelos eixos, cercada de internas de 15: por dentro 3,85 × 2,85 = 10,97 m²"""
    d = _doc()
    for a, b in [((0, 0), (4000, 0)), ((4000, 0), (4000, 3000)), ((4000, 3000), (0, 3000)), ((0, 3000), (0, 0))]:
        M.nova_parede(d, a, b, "INT15", "Térreo", "Superior")
    amb = M.novo_ambiente(d, "Sala", (0, 4000, 0, 3000), "Térreo", "porcelanato")
    M.regenerar(d)
    assert amb.atributos["arq"]["interno"] == [75, 3925, 75, 2925]
    assert amb.atributos["arq"]["area"] == pytest.approx(10.97)
    assert amb.nome == "Sala — 10,97 m²"


def test_ambiente_pela_face_de_fora_da_externa():
    """o retângulo pela face de fora (como a planta da casa): a externa de 20 recua 20 cm inteiros"""
    d = _doc()
    M.nova_parede(d, (100, 0), (100, 3000), "EXT20", "Térreo", "Superior")
    amb = M.novo_ambiente(d, "Quarto", (0, 3000, 0, 3000), "Térreo")
    M.regenerar(d)
    assert amb.atributos["arq"]["interno"][0] == 200


def test_esquadrias_saem_da_parede_com_codigo_por_tipo_e_medida():
    d = _doc()
    M.nova_parede(d, (0, 0), (6000, 0), "EXT20", "Térreo", "Superior", vaos=[
        {"tipo": "janela", "u": 500, "largura": 1500, "altura": 1200, "peitoril": 1100},
        {"tipo": "janela", "u": 3000, "largura": 1500, "altura": 1200, "peitoril": 1100},
        {"tipo": "porta", "u": 5000, "largura": 800, "altura": 2100}])
    r = M.regenerar(d)
    esq = [e for e in d.entidades.values() if (e.atributos.get("arq") or {}).get("elemento") == "esquadria"]
    assert r["esquadrias"] == 3 and len(esq) == 3
    assert sorted(e.atributos["arq"]["codigo"] for e in esq) == ["J1", "J1", "P1"]
    # refazer não duplica
    M.regenerar(d)
    assert len([e for e in d.entidades.values() if (e.atributos.get("arq") or {}).get("elemento") == "esquadria"]) == 3


def test_ida_e_volta_pelo_modelo_json():
    """a definição sobrevive à gravação: o modelo lido de volta regenera igual"""
    d = montar_casa()
    d2 = Documento.de_dict(json.loads(json.dumps(d.dict())))
    assert M.regenerar(d2) == d.metadados["arquitetura"]["piloto"]["resumo"]


def test_paredes_de_alturas_diferentes_que_nascem_no_mesmo_piso_se_unem():
    """a platibanda (até +8,20) continua na casinha das caixas d'água (até +9,00): três pontas no mesmo ponto, as duas
    em linha seguem e a frente da casinha chega em T — sem peça uma dentro da outra, cada uma com a sua altura"""
    shapely = pytest.importorskip("shapely")
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from arquitetura.paredes import Parede, montar
    ws = [Parede("plat", (100, 7700), (100, 100), "EXT20", 7000, 8200),
          Parede("cas_esq", (100, 10900), (100, 7700), "EXT20", 7000, 9000),
          Parede("cas_frente", (100, 7700), (3800, 7700), "EXT20", 7000, 9000)]
    m = montar(ws)
    u = unary_union([Polygon(p.poligono) for p in m.pecas])
    assert abs(sum(p.area for p in m.pecas) - u.area) < 1.0
    assert {p.z1 for p in m.da_parede("plat")} == {8200} and {p.z1 for p in m.da_parede("cas_frente")} == {9000}
    # e no regenerar elas ficam no mesmo grupo de uniões (a base, não o topo)
    d = _doc()
    M.definir_niveis(d, [{"nome": "Cob", "cota": 7000, "laje": 650}, {"nome": "Plat", "cota": 8200, "laje": 0},
                         {"nome": "Cas", "cota": 9150, "laje": 150}])
    a = M.nova_parede(d, (100, 7700), (100, 100), "EXT20", "Cob", "Plat")
    b = M.nova_parede(d, (100, 7700), (3800, 7700), "EXT20", "Cob", "Cas")
    M.regenerar(d)
    # duas pontas no mesmo ponto: o L em meia-esquadria fecha o canto de fora (y 7800, x 0); separadas por altura, a
    # platibanda pararia reta em 7700 e a casinha em x 100
    assert max(v[1] for v in a.vertices) == pytest.approx(7800)
    assert min(v[0] for v in b.vertices) == pytest.approx(0)


def test_escada_confere_o_degrau_e_o_patamar():
    """proposta ARQ-08: 63 ≤ 2e + p ≤ 64 e o patamar com a largura do lance. A da casa (19 × 176,3 / 280) passa no
    degrau e avisa o patamar de 68 cm; com o patamar de 1,00 m não avisa; com piso de 250 avisa o degrau"""
    def escada(prof, piso=280):
        d = _doc()
        e = M.nova_escada(d, [{"p0": [1500, 0], "dir": [0, 1], "largura": 1000, "espelhos": 10},
                              {"p0": [1700, 2520], "dir": [0, -1], "largura": 1000, "espelhos": 9}],
                          "Térreo", "Superior", patamares=[{"ret": [500, 2700, 2520, 2520 + prof], "apos": 10}], piso=piso)
        M.regenerar(d)
        return e.atributos["arq"]
    a = escada(680)
    assert a["espelho"] == pytest.approx(176.3) and len(a["avisos"]) == 1 and "patamar" in a["avisos"][0]
    assert escada(1000)["avisos"] == []
    assert any("2e + p" in x for x in escada(1000, piso=250)["avisos"])


def test_telhado_sobe_dez_por_cento_ate_a_cumeeira():
    d = _doc()
    t = M.novo_telhado(d, [{"ret": [0, 10000, 0, 5000], "beiral_y": 0, "z_beiral": 7000, "inclinacao": 0.10}])
    M.regenerar(d)
    zs = [v[2] for v in t.vertices]
    assert (min(zs), max(zs)) == (pytest.approx(7000), pytest.approx(7500 + 50))


def test_area_pela_parede_que_mais_corre_pelo_lado():
    """a garagem encosta na lateral da casa (5,8 m) e, mais adiante, na parede própria (2,6 m): vale a face da casa"""
    d = _doc()
    M.definir_niveis(d, NIVEIS + [{"nome": "Garagem", "cota": -350, "laje": 100}])
    M.nova_parede(d, (13900, 1900), (13900, 10900), "EXT20", "Térreo", "Superior")
    M.nova_parede(d, (14100, 11000), (14100, 13600), "EXT20", "Garagem", "Superior")
    amb = M.novo_ambiente(d, "Garagem", (14000, 21000, 5200, 13700), "Garagem")
    M.regenerar(d)
    assert amb.atributos["arq"]["interno"][0] == 14000


def test_casa_piloto():
    """a casa alto padrão (com a garagem, o estúdio, o telhado, a casinha e a escada de 02/11): as camadas ARQ —, as
    áreas da sugestão de planta e o único aviso esperado (o patamar da escada, decisão do usuário em aberto)"""
    d = montar_casa()
    r = d.metadados["arquitetura"]["piloto"]["resumo"]
    assert (r["paredes"], r["ambientes"], r.get("telhados"), r.get("escadas")) == (37, 17, 1, 1)
    assert r["avisos"] == ["Escada em U: patamar com 68 cm, menor que a largura do lance (100 cm)"]
    assert all(c.startswith("ARQ — ") for c in {e.camada for e in d.entidades.values()})
    areas = {(e.atributos["arq"]["nivel"], e.atributos["arq"]["nome"]): e.atributos["arq"]["area"]
             for e in d.entidades.values() if e.atributos["arq"]["elemento"] == "ambiente"}
    assert areas[("Superior", "Suíte master")] == pytest.approx(21.04)        # a mesma da prova (c)
    assert areas[("Superior", "Closet")] == pytest.approx(5.51)
    assert areas[("Garagem", "Garagem (3 vagas)")] == pytest.approx(55.08)
    # todas as malhas com vértices e faces
    assert all(e.vertices and e.faces for e in d.entidades.values())
