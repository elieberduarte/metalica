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
