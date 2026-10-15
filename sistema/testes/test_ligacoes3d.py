# -*- coding: utf-8 -*-
"""As ligações da biblioteca aplicadas no modelo 3D (F13, 14/10/2026): placa de base com chumbadores, chapa de topo
viga × pilar e chapas no topo do pilar — posição, furação, corte da barra, conjunto, solda e a ligação paramétrica
(refazer com parâmetros novos, apagar devolvendo as barras)."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import ErroDeDados  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402
from nucleo3d import ligacoes3d  # noqa: E402

W = "W 310×38,7"            # d 310, bf 165, tf 9,7


def _doc(*ents):
    d = Documento()
    for e in ents:
        d.add(e)
    return d


def _aplicar(doc, r):
    """o que o editor faz com a resposta"""
    for i in r.get("remover", []):
        doc.entidades.pop(i, None)
    for i, campos in r.get("alterar", {}).items():
        for k, v in campos.items():
            setattr(doc.entidades[i], k, v)
    for e in Documento.de_dict({"entidades": r.get("novas", [])}).entidades.values():
        doc.add(e)


def _da_ligacao(doc, lid):
    return [e for e in doc.entidades.values() if ((e.atributos or {}).get("ligacao") or {}).get("id") == lid]


def test_placa_de_base_rotulada_no_pe_do_pilar():
    pilar = Barra(inicio=(0, 0, 0), fim=(0, 0, 4000), perfil=W, rotacao=90, papel="pilar")
    doc = _doc(pilar)
    r = ligacoes3d.aplicar(doc, "placa_base_rotulada", [pilar.id])
    assert doc.entidades[pilar.id].recorte_inicio == 0          # o documento recebido não muda
    _aplicar(doc, r)
    lid = r["ligacoes"][0]["id"]
    pecas = _da_ligacao(doc, lid)
    placa = next(e for e in pecas if e.tipo == "chapa")
    chumb = [e for e in pecas if e.tipo == "barra"]
    assert placa.origem[2] == 0 and placa.espessura == 25.4
    assert placa.contorno[2] == (320.0, 500.0)                  # bf 165 + 150 → 320; d 310 + 190 → 500
    assert len(placa.furos) == 2 and len(chumb) == 2
    assert pilar.recorte_inicio == 25.4                          # o pilar começa em cima da placa
    for c in chumb:
        assert c.papel == "chumbador" and abs(c.inicio[0] - c.fim[0]) < 1e-6 and c.inicio[2] > 25.4 > c.fim[2]
    mp, mc = pilar.atributos["marcas"], placa.atributos["marcas"]
    assert mp["instancia"] == mc["instancia"] and mp["conjunto"] == mc["conjunto"] and mp["principal"]
    assert pilar.atributos["soldas"][mc["posicao"]]["local"] == "fabrica"
    assert placa.atributos["soldas"][mp["posicao"]]["perna"] > 0
    assert r["ligacoes"][0]["verificacao"] is not None


def test_placa_engastada_tem_quatro_chumbadores_e_varios_pilares_de_uma_vez():
    p1 = Barra(inicio=(0, 0, 0), fim=(0, 0, 4000), perfil=W, rotacao=90, papel="pilar")
    p2 = Barra(inicio=(6000, 0, 0), fim=(6000, 0, 4000), perfil=W, rotacao=90, papel="pilar")
    doc = _doc(p1, p2)
    r = ligacoes3d.aplicar(doc, "placa_base_engastada", [p1.id, p2.id])
    _aplicar(doc, r)
    assert len(r["ligacoes"]) == 2
    chapas = [e for e in doc.entidades.values() if e.tipo == "chapa"]
    assert len(chapas) == 2 and all(len(c.furos) == 4 for c in chapas)
    assert chapas[0].atributos["marcas"]["posicao"] == chapas[1].atributos["marcas"]["posicao"]
    assert p1.atributos["marcas"]["conjunto"] == p2.atributos["marcas"]["conjunto"]   # as duas cópias iguais


def _viga_e_pilar():
    pilar = Barra(inicio=(0, 0, 0), fim=(0, 0, 4000), perfil=W, rotacao=90, papel="pilar")   # d em Y: mesas em y = ±155
    viga = Barra(inicio=(0, 0, 3500), fim=(0, 6000, 3500), perfil=W, papel="viga")
    return pilar, viga, _doc(pilar, viga)


def test_chapa_de_topo_na_mesa_do_pilar():
    pilar, viga, doc = _viga_e_pilar()
    r = ligacoes3d.aplicar(doc, "chapa_topo_joelho", [viga.id, pilar.id])
    _aplicar(doc, r)
    lid = r["ligacoes"][0]["id"]
    pecas = _da_ligacao(doc, lid)
    chapa = next(e for e in pecas if e.tipo == "chapa")
    pars = [e for e in pecas if e.tipo == "solido"]
    assert abs(chapa.origem[1] - 155.0) < 0.01                  # encostada na mesa do pilar
    assert len(chapa.furos) == 8 and len(pars) == 8
    assert all(abs(abs(p.atributos["parafuso"]["eixo"][1]) - 1) < 1e-6 for p in pars)   # atravessam ao longo de Y
    corte = viga.cortes_inicio[0]
    assert corte["normal"] == [0.0, 1.0, 0.0] and abs(corte["ponto"][1] - (155 + 25.4)) < 0.01
    assert viga.atributos["marcas"]["conjunto"] == chapa.atributos["marcas"]["conjunto"]
    assert chapa.atributos["marcas"]["posicao"] in viga.atributos["soldas"]


def test_detalhamento_fura_o_pilar_pelos_parafusos_da_chapa_de_topo():
    from nucleo2d.detalhar import detalhar
    pilar, viga, doc = _viga_e_pilar()
    _aplicar(doc, ligacoes3d.aplicar(doc, "chapa_topo_joelho", [viga.id, pilar.id]))
    from nucleo3d import producao
    for i, patch in producao.numerar(doc)["mudancas"].items():
        doc.entidades[i].atributos = dict(doc.entidades[i].atributos or {}, **{k: v for k, v in patch.items() if v is not None})
    from nucleo2d.detalhar import levantar
    pos_pilar = pilar.atributos["marcas"]["posicao"]
    lev = levantar(doc, regra_tercas=False)
    p = next(x for x in lev["posicoes"] if x.marca == pos_pilar or pos_pilar in (getattr(x, "marcas", None) or []))
    assert len(p.furos) == 8
    r = detalhar(doc, regra_tercas=False, converter=False)
    cj = [c for c in r["conjuntos"] if viga.atributos["marcas"]["conjunto"] in c.get("marcas", [])]
    assert cj and cj[0]["pecas"] == 2                           # a viga com a chapa


def test_refazer_com_parametro_novo_e_apagar_devolve_as_barras():
    pilar, viga, doc = _viga_e_pilar()
    r = ligacoes3d.aplicar(doc, "chapa_topo_joelho", [viga.id, pilar.id])
    _aplicar(doc, r)
    lid = r["ligacoes"][0]["id"]
    antigas = {e.id for e in _da_ligacao(doc, lid)}
    r2 = ligacoes3d.aplicar(doc, "chapa_topo_joelho", [], {"t": 19.0}, ligacao=lid)
    assert set(r2["remover"]) == antigas
    _aplicar(doc, r2)
    chapa = next(e for e in _da_ligacao(doc, lid) if e.tipo == "chapa")
    assert chapa.espessura == 19.0 and abs(viga.cortes_inicio[0]["ponto"][1] - 174.0) < 0.01
    assert len([e for e in doc.entidades.values() if e.tipo == "chapa"]) == 1
    r3 = ligacoes3d.remover(doc, lid)
    _aplicar(doc, r3)
    assert not _da_ligacao(doc, lid)
    assert viga.cortes_inicio == [] and "soldas" not in viga.atributos


def test_topo_do_pilar_sob_a_viga():
    pilar = Barra(inicio=(0, 0, 0), fim=(0, 0, 3000), perfil=W, rotacao=90, papel="pilar")
    viga = Barra(inicio=(-2000, 0, 3250), fim=(4000, 0, 3250), perfil="W 250×32,7", papel="viga")   # d 258
    doc = _doc(pilar, viga)
    r = ligacoes3d.aplicar(doc, "tesoura_topo_pilar", [pilar.id, viga.id])
    _aplicar(doc, r)
    chapas = sorted((e for e in doc.entidades.values() if e.tipo == "chapa"), key=lambda c: c.origem[2])
    assert len(chapas) == 2
    face = 3250 - 258 / 2
    assert abs(chapas[1].origem[2] - (face - 12.7)) < 0.01 and abs(chapas[0].origem[2] - (face - 25.4)) < 0.01
    corte = pilar.cortes_fim[0]
    assert corte["normal"] == [0.0, 0.0, -1.0] and abs(corte["ponto"][2] - (face - 25.4 - 3000)) < 0.01
    assert chapas[0].atributos["marcas"]["conjunto"] == pilar.atributos["marcas"]["conjunto"]
    assert chapas[1].atributos["marcas"]["conjunto"] == viga.atributos["marcas"]["conjunto"]


def test_recusa_a_selecao_que_nao_serve():
    pilar, viga, doc = _viga_e_pilar()
    with pytest.raises(ErroDeDados):
        ligacoes3d.aplicar(doc, "chapa_topo_joelho", [viga.id])
    deitada = Barra(inicio=(0, 0, 0), fim=(3000, 0, 0), perfil=W)
    doc.add(deitada)
    with pytest.raises(ErroDeDados):
        ligacoes3d.aplicar(doc, "placa_base_rotulada", [deitada.id])


def test_aceitacao_base_e_chapa_de_topo_feitas_a_mao_saem_no_detalhamento():
    """O teste de aceitação da análise de 14/10: base de pilar e ligação viga × pilar com chapa de topo, do zero, sem
    gerador — marcas, os dois conjuntos (pilar + placa, viga + chapa), a solda definida, o pilar furado pelos parafusos,
    os chumbadores na planta de chumbação."""
    from nucleo2d.detalhar import detalhar, levantar
    from nucleo3d import producao
    pilar, viga, doc = _viga_e_pilar()
    _aplicar(doc, ligacoes3d.aplicar(doc, "placa_base_engastada", [pilar.id]))
    _aplicar(doc, ligacoes3d.aplicar(doc, "chapa_topo_joelho", [viga.id, pilar.id]))
    for i, patch in producao.numerar(doc)["mudancas"].items():
        doc.entidades[i].atributos = dict(doc.entidades[i].atributos or {}, **{k: v for k, v in patch.items() if v is not None})
    assert producao.numerar(doc)["mudancas"] == {}                       # tudo numerado
    lev = levantar(doc, regra_tercas=False)
    marca_p = pilar.atributos["marcas"]["posicao"]
    pos_p = next(x for x in lev["posicoes"] if x.marca == marca_p or marca_p in (getattr(x, "marcas", None) or []))
    assert len(pos_p.furos) == 8                                          # os furos da chapa de topo na mesa
    r = detalhar(doc, regra_tercas=False, converter=False)
    conj = {c["marcas"][0]: c for c in r["conjuntos"]}
    assert pilar.atributos["marcas"]["conjunto"] in conj and viga.atributos["marcas"]["conjunto"] in conj
    textos = [e.texto for e in r["desenhos"]["conjuntos"].entidades.values()
              if getattr(e, "camada", "") == "SOLDA" and hasattr(e, "texto")]
    assert any("conforme os símbolos" in t for t in textos)
    chumb = [e.texto for e in r["desenhos"]["chumbacao"].entidades.values() if getattr(e, "texto", None)]
    assert any(t.startswith("4 chumbador(es) e 1 chapa(s) de base") for t in chumb), chumb


UE = "Ue 150×60×20×2,25"


def test_cadeirinha_em_cada_cruzamento_terca_banzo():
    banzo = Barra(inicio=(0, -3000, 0), fim=(0, 3000, 0), perfil="W 250×32,7", papel="banzo")     # topo em z = 129
    t1 = Barra(inicio=(-3000, -1000, 222), fim=(3000, -1000, 222), perfil=UE, papel="terça")       # centro 90 acima da base
    t2 = Barra(inicio=(-3000, 1000, 222), fim=(3000, 1000, 222), perfil=UE, papel="terça")
    doc = _doc(banzo, t1, t2)
    r = ligacoes3d.aplicar(doc, "suporte_terca_cadeirinha", [banzo.id, t1.id, t2.id])
    _aplicar(doc, r)
    assert len(r["ligacoes"]) == 2
    lid = next(l["id"] for l in r["ligacoes"] if t1.id in l["barras"])
    pecas = _da_ligacao(doc, lid)
    ch7 = next(e for e in pecas if e.nome == "Suporte de terça (chapa)")
    ch8 = next(e for e in pecas if e.nome == "Suporte de terça (base)")
    pars = [e for e in pecas if e.tipo == "solido"]
    assert abs(ch8.origem[2] - 129.0) < 0.01 and ch8.espessura == 3.0
    assert ch7.contorno[2] == (150.0, 145.0)                    # furos a 65 e 115 da base: 115 + 30 = 145
    assert sorted(round(f["y"]) for f in ch7.furos) == [65, 65, 115, 115]
    assert all("largura" in f and f["largura"] > f["altura"] for f in ch7.furos)   # oblongo deitado
    assert len(pars) == 4 and all(abs(abs(p.atributos["parafuso"]["eixo"][1]) - 1) < 1e-6 for p in pars)
    # a chapa em pé fica por fora da alma da terça (a alma é o lado de menor y ou de maior y)
    from nucleo3d.geometria import malha_barra
    ys = [v[1] for v in malha_barra(t1)[0]]
    assert ch7.origem[1] < min(ys) or ch7.origem[1] > max(ys)
    m = banzo.atributos["marcas"]
    assert ch7.atributos["marcas"]["conjunto"] == ch8.atributos["marcas"]["conjunto"] == m["conjunto"]
    assert ch8.atributos["marcas"]["posicao"] in banzo.atributos["soldas"]
    assert ch8.atributos["marcas"]["posicao"] in ch7.atributos["soldas"]          # a chapa em pé na base


def test_cadeirinha_com_terca_de_250_usa_o_gabarito_de_100():
    banzo = Barra(inicio=(0, -3000, 0), fim=(0, 3000, 0), perfil="W 250×32,7", papel="banzo")
    terca = Barra(inicio=(-3000, 0, 300), fim=(3000, 0, 300), perfil="Ue 250×85×25×2,65", papel="terça")
    doc = _doc(banzo, terca)
    r = ligacoes3d.aplicar(doc, "suporte_terca_cadeirinha", [banzo.id, terca.id])
    assert r["ligacoes"][0]["parametros"]["gab_v"] == 100.0


def test_ligacao_flexivel_viga_no_pilar():
    from nucleo2d.detalhar import levantar
    from nucleo3d import producao
    pilar = Barra(inicio=(0, 0, 0), fim=(0, 0, 4000), perfil=W, rotacao=90, papel="pilar")
    viga = Barra(inicio=(0, 0, 3000), fim=(0, 5000, 3000), perfil="W 250×32,7", papel="viga")
    doc = _doc(pilar, viga)
    r = ligacoes3d.aplicar(doc, "ligacao_flexivel", [pilar.id, viga.id])     # a ordem não importa
    _aplicar(doc, r)
    pecas = _da_ligacao(doc, r["ligacoes"][0]["id"])
    cants = [e for e in pecas if e.tipo == "barra"]
    pars = [e for e in pecas if e.tipo == "solido"]
    assert len(cants) == 2 and len(pars) == 9
    assert abs(viga.cortes_inicio[0]["ponto"][1] - 165.0) < 0.01           # 10 mm antes da mesa do pilar
    for c in cants:                                                         # cada cantoneira encostada na mesa e na alma
        from nucleo3d.geometria import malha_barra
        vs = malha_barra(c)[0]
        assert abs(min(v[1] for v in vs) - 155.0) < 0.5
        xs = [v[0] for v in vs]
        assert min(abs(min(xs)), abs(max(xs))) == pytest.approx(6.1 / 2, abs=0.5)
    for i, patch in producao.numerar(doc)["mudancas"].items():
        doc.entidades[i].atributos = dict(doc.entidades[i].atributos or {}, **{k: v for k, v in patch.items() if v is not None})
    lev = levantar(doc, regra_tercas=False)
    pp = pilar.atributos["marcas"]["posicao"]
    pos = next(x for x in lev["posicoes"] if x.marca == pp or pp in (getattr(x, "marcas", None) or []))
    assert len(pos.furos) == 6                                              # 3 por cantoneira na mesa do pilar


def test_emenda_de_banzo_com_talas():
    a = Barra(inicio=(0, 0, 0), fim=(3000, 0, 0), perfil="W 250×32,7", papel="banzo")
    b = Barra(inicio=(3000, 0, 0), fim=(6000, 0, 0), perfil="W 250×32,7", papel="banzo")
    doc = _doc(a, b)
    r = ligacoes3d.aplicar(doc, "emenda_banzo", [a.id, b.id])
    _aplicar(doc, r)
    pecas = _da_ligacao(doc, r["ligacoes"][0]["id"])
    talas = [e for e in pecas if e.tipo == "chapa"]
    pars = [e for e in pecas if e.tipo == "solido"]
    assert len(talas) == 2 and len(pars) == 6
    ys = sorted(t.origem[1] for t in talas)
    assert ys[0] == pytest.approx(-3.05, abs=0.01) and ys[1] == pytest.approx(3.05, abs=0.01)
    assert all(len(t.furos) == 6 for t in talas)
    with pytest.raises(ErroDeDados):
        c = Barra(inicio=(0, 500, 0), fim=(3000, 500, 0), perfil="W 250×32,7")
        doc.add(c)
        ligacoes3d.aplicar(doc, "emenda_banzo", [a.id, c.id])


def _analise_falsa(pilar, viga):
    """o resultado gravado da análise (analise_estrutural.json) no formato real, só com o que a ligação lê"""
    return {"instavel": False, "nos": [[0, 0, 0], [0, 0, 3500], [0, 0, 4000], [0, 6000, 3500]],
            "barras": [{"a": 0, "b": 1, "papel": "pilar", "ids": [pilar.id]}, {"a": 1, "b": 2, "papel": "pilar", "ids": [pilar.id]},
                       {"a": 1, "b": 3, "papel": "viga", "ids": [viga.id]}],
            "combinacoes": {"C1": {"tipo": "ELU"}, "C2": {"tipo": "ELU"}, "S1": {"tipo": "ELS"}},
            "por_comb": {"C1": {"reacoes": {"0": [3.0, 4.0, 120.0, 1.0, 2.0, 0.0]}},
                         "C2": {"reacoes": {"0": [1.0, 0.0, -18.0, 0.0, 0.0, 0.0]}},
                         "S1": {"reacoes": {"0": [0.0, 0.0, 999.0, 0.0, 0.0, 0.0]}}},
            "ligacoes": [{"viga": 2, "no": 1, "max": {"Mz": [85.0, {}], "V": [52.5, {}], "Nt": [3.0, {}], "Nc": [11.0, {}]}}],
            "topos_pilares": []}


def test_verificacao_com_os_esforcos_da_analise_do_projeto():
    pilar, viga, doc = _viga_e_pilar()
    an = _analise_falsa(pilar, viga)
    e = ligacoes3d.esforcos_da_analise(an, "placa_base_rotulada", [pilar])
    assert e == {"N_Sd": 120.0, "H_Sd": 5.0, "N_min": -18.0}             # só as últimas (a S1 de serviço fica fora)
    e = ligacoes3d.esforcos_da_analise(an, "chapa_topo_joelho", [viga, pilar])
    assert e == {"M_Sd": 85.0, "V_Sd": 52.5, "N_Sd": 11.0}
    assert ligacoes3d.esforcos_da_analise(an, "ligacao_flexivel", [viga, pilar]) == {"V_Sd": 52.5}
    assert ligacoes3d.esforcos_da_analise(None, "chapa_topo_joelho", [viga, pilar]) is None
    r = ligacoes3d.aplicar(doc, "chapa_topo_joelho", [viga.id, pilar.id], analise=an)
    lg = r["ligacoes"][0]
    assert lg["origem_esforcos"] == "análise do projeto" and lg["esforcos"]["M_Sd"] == 85.0
    r = ligacoes3d.aplicar(doc, "chapa_topo_joelho", [viga.id, pilar.id])
    assert r["ligacoes"][0]["origem_esforcos"] == "padrão da biblioteca"


def test_gusset_do_contravento_sem_colisao():
    from nucleo3d import conferencia_producao as CP
    from nucleo3d.producao import _proxy
    pilar = Barra(inicio=(0, 0, 0), fim=(0, 0, 4000), perfil=W, rotacao=90, papel="pilar")            # mesas em y = ±155
    diag = Barra(inicio=(0, 0, 3000), fim=(0, 5000, 0), perfil="L 2 1/2'' X 1/4''", papel="contraventamento")
    doc = _doc(pilar, diag)
    r = ligacoes3d.aplicar(doc, "gusset_contravento", [diag.id, pilar.id])
    _aplicar(doc, r)
    pecas = _da_ligacao(doc, r["ligacoes"][0]["id"])
    ch = next(e for e in pecas if e.tipo == "chapa")
    pars = [e for e in pecas if e.tipo == "solido"]
    assert len(ch.furos) == 2 and len(pars) == 2
    assert all(abs(abs(p.atributos["parafuso"]["eixo"][0]) - 1) < 1e-6 for p in pars)          # atravessam a aba (ao longo de X)
    from nucleo3d.geometria import malha_chapa
    ys = [v[1] for v in malha_chapa(ch)[0]]
    assert abs(min(ys) - 155.0) < 0.5                                                         # soldada na mesa do pilar
    assert abs(diag.cortes_inicio[0]["ponto"][1] - 175.0) < 0.5                               # a diagonal 20 mm antes da mesa
    assert pilar.atributos["marcas"]["conjunto"] == ch.atributos["marcas"]["conjunto"]
    col = CP.colisoes([_proxy(ch), _proxy(diag), _proxy(pilar)])["achados"]
    assert col == [], col


def test_chumbadores_nos_furos_da_placa():
    from nucleo3d.modelo import Chapa
    placa = Chapa(origem=(-200, -200, 0), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0), contorno=[(0, 0), (400, 0), (400, 400), (0, 400)],
                  espessura=25, centrada=False, furos=[{"x": x, "y": y, "diametro": 25} for x in (60, 340) for y in (60, 340)])
    doc = _doc(placa)
    r = ligacoes3d.aplicar(doc, "chumbador_placa", [placa.id])
    _aplicar(doc, r)
    pecas = _da_ligacao(doc, r["ligacoes"][0]["id"])
    cbs = [e for e in pecas if e.tipo == "barra"]
    ancs = [e for e in pecas if e.tipo == "chapa"]
    assert len(cbs) == 4 and len(ancs) == 4
    assert all(abs(c.inicio[2] - 120) < 0.01 and abs(c.fim[2] - (120 - 996)) < 0.01 for c in cbs)
    assert {(round(c.inicio[0]), round(c.inicio[1])) for c in cbs} == {(-140, -140), (-140, 140), (140, -140), (140, 140)}
    r2 = ligacoes3d.aplicar(doc, "chumbador_gancho", [placa.id], {"diametro": '1"'})
    assert any("menor que o chumbador" in a for l in r2["ligacoes"] for a in l["avisos"])     # furo 25 < 25,4 + 1
