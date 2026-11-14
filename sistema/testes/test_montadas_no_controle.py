# -*- coding: utf-8 -*-
"""As tesouras montadas no Controle de produção (usuário, Posto 13/11/2026).

"É assim?" respondido (Projeto/ANALISES/Controle-de-producao/Montadas-no-controle-e-assim-2026-11-13.pdf): cada tesoura
montada vira um item só (T52 = TESOURA 1-1 + TESOURA 5), "as partes só serão apontadas juntas com o conjunto inteiro", e
a montada fica pintada "só quando todas as partes estiverem pintadas". O apontamento continua gravado em cada parte: o que
já foi apontado numa metade (a TESOURA 1-1, 13/11 14:38) conta como "1 de 2 partes" e o Apontar da T52 grava só a que falta.
Os três casos do PDF: T52 (2 partes, uma já apontada), T45 (3 partes, duas apontadas), T58 (BASE 1 + BASE 1, 4 iguais)."""
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from producao import controle as C                      # noqa: E402

A = lambda p, n: ["%s%d" % (p, i) for i in range(n)]    # noqa: E731 — as peças de uma meia no 3D

LISTA = {"posicoes": [{"marca": "P241", "nome": "CV.2", "categoria": "TIRANTES", "quantidade": 6, "peso": 4.0, "perfil": "BR 12,5"}],
         "conjuntos": [
             {"marca": "M25", "nome": "TESOURA 1", "instancias": 1, "peso_total": 124.6, "pecas_unidade": 96, "composicao": {}},
             {"marca": "M122", "nome": "TESOURA 1", "instancias": 1, "peso_total": 124.4, "pecas_unidade": 96, "composicao": {}},
             {"marca": "M123", "nome": "TESOURA 5", "instancias": 1, "peso_total": 58.6, "pecas_unidade": 54, "composicao": {}},
             {"marca": "M110", "nome": "TESOURA 3", "instancias": 1, "peso_total": 206.8, "pecas_unidade": 128, "composicao": {}},
             {"marca": "M111", "nome": "TESOURA 14", "instancias": 1, "peso_total": 230.6, "pecas_unidade": 66, "composicao": {}},
             {"marca": "M112", "nome": "TESOURA 14", "instancias": 1, "peso_total": 230.9, "pecas_unidade": 66, "composicao": {}},
             {"marca": "M158", "nome": "BASE 1", "instancias": 8, "peso_total": 8 * 52.8, "pecas_unidade": 8, "composicao": {}},
         ]}
#: o que o Detalhar grava (nomes.json): as unidades das BASE 1 e o lugar de cada montada
UNIDADES = {"M158": [{"nome": "BASE 1-%d" % (k + 1), "ids": A("b%d_" % (k + 1), 8), "meio": [1000.0 * k, 0, 0]} for k in range(8)]}
MONTADAS = {
    "T52": [{"nome": "T52", "meias": [{"marca": "M122", "ids": A("a", 96)}, {"marca": "M123", "ids": A("c", 54)}], "meio": [0, 0, 0]}],
    "T45": [{"nome": "T45", "meias": [{"marca": "M110", "ids": A("d", 128)}, {"marca": "M111", "ids": A("e", 66)},
                                       {"marca": "M112", "ids": A("f", 66)}], "meio": [0, 0, 0]}],
    "T58": [{"nome": "T58-%d" % (k + 1), "meias": [{"marca": "M158", "ids": UNIDADES["M158"][2 * k]["ids"]},
                                                    {"marca": "M158", "ids": UNIDADES["M158"][2 * k + 1]["ids"]}],
             "meio": [2000.0 * k, 0, 0]} for k in range(4)],
}
ANTES = {"unidades": UNIDADES}                                         # o nomes.json de antes do Detalhar com as montadas
DEPOIS = {"unidades": UNIDADES, "montadas_unidades": MONTADAS}


def _por(its):
    return {x["id"]: x for x in its}


def test_a_montada_vira_um_item_com_as_partes_dentro():
    its = C.itens(LISTA, DEPOIS)
    por = _por(its)
    ids = [x["id"] for x in its]
    assert {"T52", "T45", "T58-1", "T58-2", "T58-3", "T58-4"} <= set(ids)
    # as partes saem da lista solta; a TESOURA 1-1 (M25), fora de montada, fica
    assert not {"TESOURA 1-2", "TESOURA 5", "TESOURA 3", "TESOURA 14-1", "TESOURA 14-2"} & set(ids) and "TESOURA 1-1" in ids
    assert not any(i.startswith("BASE 1-") for i in ids)
    t52 = por["T52"]
    assert [p["id"] for p in t52["partes"]] == ["TESOURA 1-2", "TESOURA 5"] and t52["descricao"] == "TESOURA 1-2 + TESOURA 5"
    assert t52["quantidade"] == 1 and t52["kg"] == pytest.approx(124.4 + 58.6) and t52["tipo"] == "tesoura montada"
    assert [p["id"] for p in por["T58-3"]["partes"]] == ["BASE 1-5", "BASE 1-6"]
    # o peso da obra não muda
    assert sum(x["kg"] for x in its) == pytest.approx(sum(x["kg"] for x in C.itens(LISTA, ANTES)))
    # sem o lugar das montadas (o Detalhar de antes), tudo como era
    assert "T52" not in [x["id"] for x in C.itens(LISTA, ANTES)]


def test_o_ja_apontado_na_metade_conta_como_parte_e_o_apontar_grava_so_a_que_falta(tmp_path):
    pasta = str(tmp_path)
    C.apontar(pasta, LISTA, "TESOURA 1-2", "producao", 1, "Elieber", nomes=ANTES)     # 13/11 14:38, antes das montadas
    s = C.situacao(LISTA, C.ler_eventos(pasta), DEPOIS)
    t52 = _por(s["itens"])["T52"]
    assert t52["feito"]["producao"] == 0 and t52["partes_feitas"]["producao"] == 1          # "1 de 2 partes"
    assert s["fora_da_lista"] == [] and s["andamento"]["producao"]["kg"] == pytest.approx(124.4, abs=0.1)
    ev = C.apontar(pasta, LISTA, "T52", "producao", 1, "Elieber", nomes=DEPOIS)
    assert ev["item"] == "TESOURA 5" and ev["montada"] == "T52" and ev.get("junto") == []
    assert _por(C.situacao(LISTA, C.ler_eventos(pasta), DEPOIS)["itens"])["T52"]["feito"]["producao"] == 1
    with pytest.raises(C.ErroControle, match="completo"):
        C.apontar(pasta, LISTA, "T52", "producao", 1, "x", nomes=DEPOIS)
    # a parte sozinha não se aponta mais
    with pytest.raises(C.ErroControle, match="parte da tesoura montada T52"):
        C.apontar(pasta, LISTA, "TESOURA 5", "pintura", 1, "x", nomes=DEPOIS)


def test_as_tres_partes_juntas_e_o_estorno_desfaz_o_lote(tmp_path):
    pasta = str(tmp_path)
    r = C.apontar_varios(pasta, LISTA, ["T45", "CV.2"], "producao", "x", nomes=DEPOIS)
    t45 = [e for e in r["eventos"] if e.get("montada") == "T45"]
    assert [e["item"] for e in t45] == ["TESOURA 3", "TESOURA 14-1", "TESOURA 14-2"] and len({e["lote"] for e in t45}) == 1
    assert all(e.get("ancora") for e in t45)                                 # cada parte segue a peça (as da meia)
    est = C.estornar(pasta, t45[1]["id"], "x")
    assert len(est["junto"]) == 2
    s = C.situacao(LISTA, C.ler_eventos(pasta), DEPOIS)
    por = _por(s["itens"])
    assert por["T45"]["partes_feitas"]["producao"] == 0 and por["CV.2"]["feito"]["producao"] == 6


def test_pintada_so_com_todas_as_partes_pintadas(tmp_path):
    pasta = str(tmp_path)
    C.apontar_varios(pasta, LISTA, ["BASE 1-5", "BASE 1-6"], "producao", "x", nomes=ANTES)   # só se pinta o produzido (14/11)
    C.apontar(pasta, LISTA, "BASE 1-5", "pintura", 1, "x", nomes=ANTES)       # uma BASE pintada antes
    s = C.situacao(LISTA, C.ler_eventos(pasta), DEPOIS)
    t = _por(s["itens"])["T58-3"]
    assert t["feito"]["pintura"] == 0 and t["partes_feitas"]["pintura"] == 1 and s["andamento"]["pintura"]["itens_completos"] == 0
    C.apontar(pasta, LISTA, "T58-3", "pintura", 1, "x", nomes=DEPOIS)
    s = C.situacao(LISTA, C.ler_eventos(pasta), DEPOIS)
    assert _por(s["itens"])["T58-3"]["feito"]["pintura"] == 1 and s["andamento"]["pintura"]["itens_completos"] == 1
    # o ERP vê a montada em cada parte
    erp = C.para_erp("posto", "POSTO", LISTA, C.ler_eventos(pasta), DEPOIS)
    assert {e["marca"]: e["montada"] for e in erp["eventos"]} == {"BASE 1-5": "T58-3", "BASE 1-6": "T58-3"}
    assert {x["marca"]: x["pintura"] for x in erp["itens"]}["T58-3"] == 1


def test_meia_que_nao_se_acha_deixa_as_partes_soltas():
    m = {"T99": [{"nome": "T99", "meias": [{"marca": "M122", "ids": A("a", 96)}, {"marca": "M999", "ids": A("z", 9)}], "meio": [0, 0, 0]}]}
    ids = [x["id"] for x in C.itens(LISTA, {"unidades": UNIDADES, "montadas_unidades": m})]
    assert "T99" not in ids and "TESOURA 1-2" in ids


def test_o_detalhar_guarda_cada_montada_com_as_meias_e_o_meio():
    from test_tesouras_montadas_planas import L, _montadas, _trelica
    from nucleo3d.modelo import Documento
    doc = Documento(nome="tesoura")
    _trelica(doc, 0.0, "T#0", inclinada=0.10)
    _trelica(doc, L + 50.0, "T#1", inclinada=-0.10)
    montadas, _ = _montadas(doc)
    (inst,) = montadas[0]["instancias"]
    assert [m["marca"] for m in inst["meias"]] == ["TS", "TS"] and all(m["ids"] for m in inst["meias"])
    assert not set(inst["meias"][0]["ids"]) & set(inst["meias"][1]["ids"])
    assert inst["meio"][0] == pytest.approx(L + 25.0, abs=200)


def test_a_tela_mostra_a_montada_pelas_partes():
    js = open(os.path.join(os.path.dirname(AQUI), "web", "producao", "controle.js"), encoding="utf-8").read()
    assert "partes_feitas" in js and "de ${n(x.partes.length)} partes" in js
    js3 = open(os.path.join(os.path.dirname(AQUI), "web", "producao", "controle3d.js"), encoding="utf-8").read()
    assert "x.partes" in js3
    app = open(os.path.join(os.path.dirname(AQUI), "app.py"), encoding="utf-8").read()
    assert '"montadas_unidades")' in app                                    # o nomes.json guarda o lugar das montadas
