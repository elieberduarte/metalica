# -*- coding: utf-8 -*-
"""A revisão V12 do Hangar Almayer (21/10/2026: "O projeto do hangar mudou algumas coisas está na V12 … as principais
mudanças foram nas chapas"): a revisão alinhada à anterior pelos eixos, as leituras da Identificação no arranjo novo das
folhas (a tesoura numa folha só, com as vistas numeradas e a legenda dos perfis; a legenda das plantas de
contraventamento no alto à esquerda; o detalhe dos chumbadores sem a folha APOIO DAS TESOURAS) e as peças novas (a emenda
por tipo de tesoura, a chapa CV1 da VC, a castanha CA1) — a leitura e o 3D."""
import collections
import math
import os

import pytest

from nucleo2d.desenho import Desenho, Linha
from nucleo3d import de_planta_estrutura as DPE
from nucleo3d.modelo import Barra, Chapa, Solido

PASTA = os.path.join(os.path.dirname(__file__), "..", "..", "Projeto", "OBRAS", "Hangar-Almayer")
V5 = os.path.join(PASTA, "Hangar-Allmayer_Projeto de fabricacao_V5.dxf")
V12 = os.path.join(PASTA, "Hangar-Allmayer_Projeto de fabricacao_V12.dxf")


@pytest.fixture(scope="module")
def v12():
    if not (os.path.exists(V5) and os.path.exists(V12)):
        pytest.skip("sem os DXF V5 e V12 do Hangar em Projeto/OBRAS/Hangar-Almayer")
    from nucleo3d import identificacao as I, lancamento
    d5, _ = lancamento.ler_arquitetonico(open(V5, "rb").read(), "dxf")
    d12, _ = lancamento.ler_arquitetonico(open(V12, "rb").read(), "dxf")
    alin = I.alinhar_revisao(d12, d5)
    return d12, I.varrer(d12), I.folhas_com_moldura(d12), alin


def test_revisao_alinhada_pelos_eixos(v12):
    """a V12 tem as folhas noutro lugar do desenho: os eixos de mesmo nome dão o deslocamento (o mais comum em cada
    família) e o eixo que o projeto mudou (o 1, a T3: 81,5 mm mais perto da T2-A) é apontado"""
    _d, v, _fs, alin = v12
    assert (alin["dx"], alin["dy"]) == (-39733.5, 11985.0)
    assert [(m_["nome"], m_["antes"], m_["depois"]) for m_ in alin["mudaram"]] == [("1", 82226.0, 82307.5)]
    assert [(e["nome"], e["pos"]) for e in v["locacao"]["eixos"]["numeros"]][1:] == [("2", 82845.0), ("3", 87695.0), ("4", 92495.0),
                                                                                      ("5", 97295.0), ("6", 102220.0)]


def test_tesoura_pela_vista_do_gabarito_e_os_perfis_pela_legenda(v12):
    """a folha "T2 - 4 PÇ" tem a tesoura três vezes (gabarito, suportes, chapas): a vista é a do gabarito; a T2-A sem
    folha usa a da T2; a T3 não vai mais para a folha das mãos-francesas; os perfis pela legenda ("U100x50#3,00 (TRELIÇA,
    PERNA E CHANFRO)": a diagonal da T2 é U100, a "2L INTERNO" é a subtreliça)"""
    from nucleo3d import identificacao as I
    d, v, fs, _a = v12
    ts = {t["tipo"]: t for t in v["tesouras"]}
    assert all("GABARITO" in ts[k]["vista"]["titulo"] for k in ("T1", "T2", "T2-A", "T3"))
    assert ts["T2-A"].get("pela_folha_de") == "T2"
    p2 = {k: x["perfil"] for k, x in I.perfis_da_tesoura(d, "T2", fs).items()}
    assert (p2["banzo"], p2["montante"], p2["diagonal"], p2["interno"]) == ("U 127×50×3,75 (FF)", "U 100×50×3,00 (FF)",
                                                                           "U 100×50×3,00 (FF)", "L 25×3 (FF)")
    p1 = {k: x["perfil"] for k, x in I.perfis_da_tesoura(d, "T1", fs).items()}
    assert (p1["diagonal"], p1["emenda"]) == ("L 32×3 (FF)", "U 127×50×3,00 (FF)")
    des = I.desenho_da_tesoura(d, ts["T2"]["vista"]["caixa"], {})
    assert des["contagem"]["montante"] == 17                 # uma tesoura só (eram as três vistas juntas)


def test_contraventos_pela_legenda_nova_e_a_vt_da_cumeeira(v12):
    """a legenda da planta de contraventamento no alto à esquerda (antes só à direita: nenhum contravento era lido), "agulh.
    diagonal" abreviado, a linha de amostra da legenda não vira peça, a marca da barra redonda pela tabela da planta
    ("AG3 - Ø3/8\\" L=275"); a cota do banzo da T1 desenhado com linhas soltas; e a VT da cumeeira no banzo de baixo (a
    linha caía na folga da junta e ia para a cota do apoio, 64 mm abaixo — também na V5)"""
    from nucleo3d import identificacao as I
    d, v, _fs, _a = v12
    tes = [{"tipo": t["tipo"], "eixos": t["eixos"], "caixa": t["vista"]["caixa"]} for t in v["tesouras"] if t.get("vista") and t["eixos"]]
    r = I.outras_pecas(d, v["folhas"], v["locacao"], v["locacao"]["eixos"], tes, 5000.0)
    res = r["resumo"]
    assert all(res.get("CV%d" % k) == 4 for k in range(1, 9))
    assert (res.get("CR"), res.get("AG3"), res.get("AG3?"), res.get("VT")) == (50, 17, 16, 6)
    assert all(b.get("marca") for b in r["barras"])
    assert {b["z_a"] for b in r["barras"] if b["marca"] == "VT"} == {5063.5}
    assert not any("sem a tesoura do eixo" in a for a in r["avisos"])
    cv_t1 = [b for b in r["barras"] if b["marca"] == "CV3"]
    assert all(b["z_a"] != b["z_b"] for b in cv_t1)          # a ponta na T1 com a cota dela


def test_apoios_pela_folha_de_chumbadores_da_v12(v12):
    """sem a folha APOIO DAS TESOURAS: a marca "PB1 + 4 CH. Ø5/8\\"" (sem a letra do apoio) e o detalhe "CHUMBADORES -
    15x" — a PB sobre o pilar e a CB 40,5 mm acima dela (o graute): o topo do pilar sob a tesoura em +4,942"""
    from nucleo2d.desenho import Polilinha
    from nucleo3d import identificacao as I
    d, _v, fs, _a = v12
    pil = {"PM1": (82895, -4900), "PM2": (82895, -24300), "PM3": (87695, -4900), "PM4": (87695, -24300), "PM5": (92495, -4900),
           "PM6": (92495, -24300), "PM7": (97295, -4900), "PM8": (97295, -24300), "PM9": (102095, -4900), "PM10": (102095, -24300),
           "PM11": (102095, -9750), "PM12": (102095, -14600), "PM13": (102095, -19450), "PM14": (102120, -6250),
           "PM15": (82895, -1300), "PM16": (82930, -27875)}
    planta = Desenho(nome="montagem", escala=1.0)
    for m_, (x, y) in pil.items():
        planta.add(Polilinha(camada="ESTRUTURA", fechada=True, vertices=[(x - 150, y - 200), (x + 150, y - 200), (x + 150, y + 200), (x - 150, y + 200)],
                             atributos={"elemento": "pilar", "material": "concreto", "marca": m_, "nivel_base": -1000, "nivel_topo": 5000}))
    for x, m_ in ((82845, "T2-A"), (87695, "T2"), (92495, "T2"), (97295, "T2"), (102220, "T1")):
        planta.add(Linha(camada="ESTRUTURA", a=(x, -4900), b=(x, -24300), atributos={"elemento": "trelica", "material": "aco", "marca": m_}))
    r = I.apoios_das_tesouras(d, fs, planta, 5000.0)
    assert r["resumo"] == {"PB1": 13, "PB1+2CQ1": 2}
    sob = [a for a in r["apoios"] if a["cb"]]
    assert sob and {(a["folga_cb"], a["topo_pb"], a["topo_pilar"]) for a in sob} == {(40.5, 4951.5, 4942.0)}
    assert any("graute" in a for a in r["avisos"])


def test_suporte_a_definir_no_texto_novo(v12):
    """"perna de 50: furação A DEFINIR" (a V12; a V5 dizia "perna de 50 (apoio no banzo): furação A DEFINIR")"""
    from nucleo3d import identificacao as I
    d, _v, fs, _a = v12
    st = I.suportes_das_tercas(d, fs)["suportes"]["ST1"]
    assert "DEFINIR" in (st.get("a_definir") or "")


def test_emenda_cv1_e_castanha_pelo_projeto(v12):
    """a emenda por tipo (a CE1 em cada banzo da T2 — 300×240, 7 furos Ø22 sem parafuso escrito; o U em pé da T1 e da T3,
    alma com alma, 8 furos Ø15 e 8 parafusos de 1/2"), a CV1 da ponta da VC e a castanha CA1 (só no banzo de baixo)"""
    from nucleo3d import identificacao as I
    d, _v, fs, _a = v12
    r = I.chapas_das_emendas(d, fs)
    assert r["formato"] == "v12"
    e = r["emendas"]
    assert (e["T2"]["tipo_emenda"], e["T2"]["largura"], e["T2"]["altura"], e["T2"]["quantidade"]) == ("chapa_por_banzo", 300.0, 240.0, 16)
    assert len(e["T2"]["vistas"]["inf"]["furos"]) == 7 and e["T2"]["vistas"]["inf"]["fora"] == 63.0 and e["T2"]["parafusos"] is None
    assert (e["T1"]["tipo_emenda"], e["T1"]["perfil"], len(e["T1"]["furos"]), e["T1"]["parafusos"]["n"]) == ("perfil_vertical", "U 127×50×3,00 (FF)", 8, 8)
    assert (e["T3"]["perfil"], len(e["T3"]["furos"])) == ("U 75×38×3,00 (FF)", 8)
    assert any("sem o parafuso escrito" in a for a in r["avisos"])
    cv = r["ligacao_vc"]
    assert (cv["marca"], cv["quantidade"], cv["largura"], cv["altura"], cv["soldada"]) == ("CV1", 24, 150.0, 127.0, True)
    a = I.aletas_dos_contraventos(d, fs)
    ca = a["castanha"]
    assert (ca["marca"], ca["quantidade"], ca["peca"]["comprimento"], ca["aba"]["comprimento"], ca["banzos"]) == ("CA1", 64, 150.0, 50.0, ["inf"])
    assert a["contraventos"]["CV1"]["comprimento"] == 6600.0


# ------------------------------------------- o 3D das peças novas, numa tesoura pequena

def _tesoura(emenda=None, aletas=None, extras=()):
    """uma tesoura de 6 m em U127 simples partida no meio (o banzo de baixo para a 10 mm da junta, como a T1 da V5)"""
    barras = [[0, 0, 2990, 0, "banzo_inf"], [3010, 0, 6000, 0, "banzo_inf"], [0, 600, 3000, 900, "banzo_sup"],
              [3000, 900, 6000, 600, "banzo_sup"], [0, 0, 0, 600, "extremidade"], [6000, 0, 6000, 600, "extremidade"],
              [3000, 0, 3000, 900, "montante"], [1500, 0, 1500, 750, "montante"], [4500, 0, 4500, 750, "montante"],
              [0, 600, 1500, 0, "diagonal"], [1500, 750, 3000, 0, "diagonal"], [3000, 0, 4500, 750, "diagonal"],
              [4500, 0, 6000, 600, "diagonal"]]
    des = Desenho(nome="planta", escala=1.0)
    at = {"elemento": "trelica", "material": "aco", "marca": "T1",
          "perfis": {"banzo_sup": "U 127×50×3,00 (FF)", "banzo_inf": "U 127×50×3,00 (FF)", "montante": "L 32×3 (FF)", "diagonal": "L 32×3 (FF)"},
          "nivel_base": 5000, "desenho": {"barras": barras, "vao": 6000, "altura": 900}}
    if emenda is not None:
        at["chapas"] = emenda
    if aletas is not None:
        at["aletas"] = aletas
    des.add(Linha(camada="E", a=(0.0, 0.0), b=(0.0, 6000.0), atributos=at))
    for e in extras:
        des.add(e)
    return DPE.modelo_da_planta(des, [])


def test_emenda_por_u_em_pe_alma_com_alma():
    """o U em pé em cada meia-tesoura (a T1 e a T3 da V12): a costa da alma no meio da junta, as abas para a metade dele,
    do pé do banzo de baixo até 1330; os 8 parafusos atravessando as duas almas; o montante da junta sai; o banzo de
    baixo vai até a alma"""
    from nucleo3d import regras_trelica as rt
    from nucleo3d.de_planta_estrutura import _faixa_da_secao
    furos = [{"x": x, "y": y, "d": 15.0} for x in (38.5, 88.5) for y in (200.0, 260.0, 1070.0, 1130.0)]
    ev = {"tipo_emenda": "perfil_vertical", "perfil": "U 127×50×3,00 (FF)", "comprimento": 1330.0, "quantidade": 2, "furos": furos,
          "alma_com_alma": True, "parafusos": {"n": 8, "texto": '1/2"', "diametro": 12.7}}
    doc, av = _tesoura(emenda={"emenda_v12": ev, "ligacao_vc": None})
    ents = list(doc.entidades.values())
    us = [b for b in ents if isinstance(b, Barra) and (b.atributos or {}).get("papel_trelica") == "emenda"]
    assert len(us) == 2 and all(b.perfil == "U 127×50×3,00 (FF)" for b in us)
    for b in us:
        lo, hi = _faixa_da_secao(b, (0, 1, 0))
        assert min(abs(b.meio[1] + lo - 3000.0), abs(b.meio[1] + hi - 3000.0)) < 0.5        # a costa da alma na junta
        assert abs(abs(b.inicio[2] - b.fim[2]) - 1330.0) < 0.5
    par = [s for s in ents if isinstance(s, Solido) and (s.atributos or {}).get("parafuso")]
    assert len(par) == 8 and all(abs(s.atributos["parafuso"]["ponto"][1] - 3000.0) < 0.01 for s in par)
    assert not any(isinstance(b, Barra) and b.papel == "montante" and abs(b.meio[1] - 3000.0) < 1 and not (b.atributos or {}).get("emenda") for b in ents)
    bi = sorted((b for b in ents if isinstance(b, Barra) and (b.atributos or {}).get("papel_trelica") == "banzo_inf"), key=lambda b: b.meio[1])
    assert abs(max(bi[0].inicio[1], bi[0].fim[1]) - 2997.0) < 0.5 and abs(min(bi[1].inicio[1], bi[1].fim[1]) - 3003.0) < 0.5
    assert rt.conferir(ents) == []


def test_emenda_por_chapa_em_cada_banzo():
    """a CE1 da T2 da V12: uma chapa em cada banzo de cada meia-tesoura (4), encostadas na junta, passando 63 mm do banzo
    para fora da tesoura; sem parafuso escrito, só os furos"""
    vis = {"inf": {"furos": [{"x": 30.0, "y": 30.0, "d": 22.0}], "fora": 63.0, "dentro": 50.0},
           "sup": {"furos": [{"x": 30.0, "y": 210.0, "d": 22.0}], "fora": 63.0, "dentro": 50.0}}
    ev = {"tipo_emenda": "chapa_por_banzo", "marca": "CE1", "quantidade": 16, "espessura": 9.5, "largura": 300.0, "altura": 240.0,
          "aco": "CIVIL 300", "vistas": vis, "parafusos": None}
    doc, av = _tesoura(emenda={"emenda_v12": ev, "ligacao_vc": None})
    ents = list(doc.entidades.values())
    ce = [c for c in ents if isinstance(c, Chapa) and (c.atributos or {}).get("marca") == "CE1"]
    assert len(ce) == 4 and sorted({round(c.origem[1], 2) for c in ce}) == [2995.25, 3004.75]
    bi = next(b for b in ents if isinstance(b, Barra) and (b.atributos or {}).get("papel_trelica") == "banzo_inf")
    from nucleo3d.de_planta_estrutura import _faixa_da_secao
    pe = bi.meio[2] + _faixa_da_secao(bi, (0, 0, 1))[0]
    assert {round(c.origem[2] - (pe - 63.0), 1) for c in ce if c.atributos["banzo"] == "inf"} == {0.0}
    assert not any(isinstance(s, Solido) and (s.atributos or {}).get("parafuso") for s in ents)


def test_chapa_da_vc_e_castanha_no_3d():
    """a CV1 em pé na face de fora do banzo onde a VC chega (centrada nela); a castanha embaixo do banzo de baixo, presa
    a 30 mm da borda de fora, a ponta do contravento 25 mm abaixo do banzo, a barra no comprimento de corte do projeto;
    o contravento do banzo de cima sem castanha vira apontamento"""
    cv1 = {"marca": "CV1", "quantidade": 24, "espessura": 9.5, "largura": 150.0, "altura": 127.0, "soldada": True, "sem_furos": True,
           "a_definir": "ESPESSURA A DEFINIR", "texto": "CV1"}
    ca = {"marca": "CA1", "quantidade": 64, "peca": {"perfil": "L 2\"×3/16\"", "comprimento": 150.0},
          "aba": {"perfil": "L 2\"×3/16\"", "comprimento": 50.0}, "furo": 14.0,
          "parafuso": {"texto": '1/2"', "diametro": 12.7, "quantidade": 64}, "banzos": ["inf"], "a_definir": "banzo superior A DEFINIR"}
    vc = Linha(camada="E", a=(73.5, 1500.0), b=(4000.0, 1500.0), atributos={"elemento": "viga", "material": "aco", "papel": "banzo",
               "marca": "VC01", "secao": {"perfil": "U 127×50×2,65 (FF)"}, "nivel_topo": 5000.0, "alinhamento": "eixo"})
    rod = Linha(camada="E", a=(150.0, 4000.0), b=(3000.0, 1150.0), atributos={"elemento": "viga", "material": "aco", "papel": "contraventamento",
                "marca": "CV5", "secao": {"perfil": "Barra redonda ø 1/2\""}, "nivel_topo": 5000.0, "alinhamento": "eixo"})
    rod_sup = Linha(camada="E", a=(150.0, 2000.0), b=(3000.0, 4850.0), atributos={"elemento": "viga", "material": "aco", "papel": "contraventamento",
                    "marca": "CV1", "secao": {"perfil": "Barra redonda ø 1/2\""}, "nivel_topo": 5700.0, "alinhamento": "eixo"})
    doc, av = _tesoura(emenda={"emenda_v12": None, "ligacao_vc": cv1}, aletas={"castanha": ca, "contraventos": {"CV5": {"comprimento": 4100.0}}},
                       extras=(vc, rod, rod_sup))
    ents = list(doc.entidades.values())
    pl = [c for c in ents if isinstance(c, Chapa) and (c.atributos or {}).get("marca") == "CV1"]
    assert len(pl) == 1 and abs(pl[0].origem[1] - (1500.0 - 75.0)) < 0.5
    cast = [b for b in ents if isinstance(b, Barra) and b.papel == "castanha"]
    assert len(cast) == 2                                     # a cantoneira e a aba, numa ponta só (a do banzo de baixo)
    cv5 = next(b for b in ents if isinstance(b, Barra) and (b.atributos or {}).get("marca") == "CV5")
    bi = next(b for b in ents if isinstance(b, Barra) and (b.atributos or {}).get("papel_trelica") == "banzo_inf")
    from nucleo3d.de_planta_estrutura import _faixa_da_secao
    pe = bi.meio[2] + _faixa_da_secao(bi, (0, 0, 1))[0]
    ponta = min((cv5.inicio, cv5.fim), key=lambda p: abs(p[0]))
    assert abs(cv5.comprimento - 4100.0) < 0.5
    par = [s for s in ents if isinstance(s, Solido) and str((s.atributos or {}).get("marca", "")) == "PAR CA1"]
    assert len(par) == 1 and abs(par[0].atributos["parafuso"]["ponto"][2] - pe) < 0.5
    assert abs(abs(par[0].atributos["parafuso"]["ponto"][0]) - (63.5 - 30.0)) < 0.5
    assert any("CA1 da T1: 1 ponta(s) de contravento no banzo de cima sem castanha" in a for a in av)
    assert any("CV1: espessura a definir" in a for a in av)
    assert ponta[2] < pe                                      # a ponta abaixo do banzo, no furo da aba
    # 22/10 (usuário: "o que são esses elementos voando"): a castanha e a aba com o topo na face de baixo do banzo —
    # antes a altura do banzo entrava duas vezes e as 64 da V12 ficavam 5 m acima dele
    for b in cast:
        assert abs(b.meio[2] + _faixa_da_secao(b, (0, 0, 1))[1] - pe) < 0.5, b.nome
    from nucleo3d import conferencia_3d
    assert conferencia_3d.pecas_voando(list(doc.barras), list(doc.solidos), list(doc.chapas)) == []
