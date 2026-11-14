# -*- coding: utf-8 -*-
"""O apontamento segue a peça quando o Detalhar muda os nomes (13/11/2026).

O apontamento guarda o NOME do item, e o número pela ordem dos eixos (cd111d8) trocou 35 nomes no Posto: a TESOURA 1-1
de antes é a 1-7 de agora, e o nome "TESOURA 1-1" passou a ser OUTRA tesoura. Sem isto, o apontado ficava "fora da lista"
ou, pior, contava na tesoura errada. O arquivo de apontamentos nunca é reescrito: a leitura liga cada apontamento ao item
de agora — pela âncora (as peças da unidade no 3D), pelo nome na mesma marca, pela marca (peça avulsa; unidade sem lugar)."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from producao import controle as C                      # noqa: E402

A = ["a%d" % i for i in range(20)]                       # as peças da tesoura do eixo A
L = ["l%d" % i for i in range(20)]                       # as da tesoura do eixo L
LISTA = {"posicoes": [{"marca": "P7", "nome": "T.C.1", "categoria": "TERÇAS", "quantidade": 10, "peso": 12.0, "perfil": "Ue 150"},
                      {"marca": "P8", "nome": "CH3", "categoria": "CHAPAS", "quantidade": 4, "peso": 1.0, "perfil": "CH 6"}],
         "conjuntos": [{"marca": "M25", "nome": "TESOURA 1", "instancias": 1, "peso_total": 120.0, "pecas_unidade": 20, "composicao": {}},
                       {"marca": "M122", "nome": "TESOURA 1", "instancias": 1, "peso_total": 120.0, "pecas_unidade": 20, "composicao": {}},
                       {"marca": "M90", "nome": "PAINEL 3", "instancias": 2, "peso_total": 100.0, "pecas_unidade": 5, "composicao": {}}]}
#: antes (pela ordem das marcas): M25 (eixo L) era a 1-1; depois (pelos eixos): M122 (eixo A) é a 1-1
ANTES = {"unidades": {"M25": [{"nome": "TESOURA 1-1", "ids": L, "meio": [0, 2000, 0]}],
                      "M122": [{"nome": "TESOURA 1-2", "ids": A, "meio": [0, 56000, 0]}]}}
DEPOIS = {"unidades": {"M122": [{"nome": "TESOURA 1-1", "ids": A, "meio": [0, 56000, 0]}],
                       "M25": [{"nome": "TESOURA 1-2", "ids": L, "meio": [0, 2000, 0]}]}}


def _por(s):
    return {x["id"]: x for x in s["itens"]}


def test_a_tesoura_apontada_segue_a_peca_e_nao_o_nome(tmp_path):
    pasta = str(tmp_path)
    ev = C.apontar(pasta, LISTA, "TESOURA 1-1", "producao", 1, "Fernando", nomes=ANTES)
    assert ev["ancora"] == sorted(L)[:C.ANCORA] and ev["refs"] == ["M25"]          # a do eixo L
    s = C.situacao(LISTA, C.ler_eventos(pasta), DEPOIS)
    por = _por(s)
    # depois do Detalhar a do eixo L chama-se TESOURA 1-2: o apontado está nela, e a nova 1-1 (eixo A) segue sem nada
    assert por["TESOURA 1-2"]["feito"]["producao"] == 1 and por["TESOURA 1-1"]["feito"]["producao"] == 0
    assert s["fora_da_lista"] == [] and s["seguiram"] == [{"era": "TESOURA 1-1", "agora": "TESOURA 1-2"}]
    assert s["eventos"][0]["item_atual"] == "TESOURA 1-2"
    # e o apontar confere o que falta na peça certa: a 1-2 já está feita, a 1-1 não
    try:
        C.apontar(pasta, LISTA, "TESOURA 1-2", "producao", 1, "Fernando", nomes=DEPOIS)
        assert False, "a 1-2 (a do eixo L) já foi produzida"
    except C.ErroControle as e:
        assert "completo" in str(e)
    C.apontar(pasta, LISTA, "TESOURA 1-1", "producao", 1, "Fernando", nomes=DEPOIS)
    # o arquivo nunca é reescrito: o primeiro apontamento continua com o nome de antes
    eventos = C.ler_eventos(pasta)
    assert eventos[0]["item"] == "TESOURA 1-1" and eventos[0]["ancora"] == sorted(L)[:C.ANCORA]
    # o estorno do apontamento de antes desfaz na peça certa
    C.estornar(pasta, eventos[0]["id"], "Fernando")
    por = _por(C.situacao(LISTA, C.ler_eventos(pasta), DEPOIS))
    assert por["TESOURA 1-2"]["feito"]["producao"] == 0 and por["TESOURA 1-1"]["feito"]["producao"] == 1


def test_peca_avulsa_segue_a_posicao_e_unidade_sem_lugar_segue_a_marca(tmp_path):
    pasta = str(tmp_path)
    C.apontar(pasta, LISTA, "T.C.1", "producao", 4, "x")        # só se pinta o que foi produzido (risco 3, 14/11)
    C.apontar(pasta, LISTA, "T.C.1", "pintura", 4, "x")
    C.apontar(pasta, LISTA, "PAINEL 3-1", "producao", 1, "x")
    C.apontar(pasta, LISTA, "PAINEL 3-2", "producao", 1, "x")
    # o detalhamento renomeou a terça (T.C.1 → T.C.4) e o painel (PAINEL 3 → PAINEL 30): as marcas são as mesmas
    nova = {"posicoes": [dict(LISTA["posicoes"][0], nome="T.C.4"), LISTA["posicoes"][1]],
            "conjuntos": LISTA["conjuntos"][:2] + [dict(LISTA["conjuntos"][2], nome="PAINEL 30")]}
    s = C.situacao(nova, C.ler_eventos(pasta), DEPOIS)
    por = _por(s)
    assert por["T.C.4"]["feito"]["producao"] == 4 and por["T.C.4"]["feito"]["pintura"] == 4
    assert por["PAINEL 30-1"]["feito"]["producao"] == 1 and por["PAINEL 30-2"]["feito"]["producao"] == 1
    assert s["fora_da_lista"] == []
    assert {"era": "T.C.1", "agora": "T.C.4"} in s["seguiram"]


def test_o_que_saiu_do_projeto_fica_fora_da_lista(tmp_path):
    pasta = str(tmp_path)
    C.apontar(pasta, LISTA, "CH3", "producao", 2, "x")
    sem_ch = {"posicoes": LISTA["posicoes"][:1], "conjuntos": LISTA["conjuntos"]}
    s = C.situacao(sem_ch, C.ler_eventos(pasta), DEPOIS)
    assert s["fora_da_lista"] == ["CH3"] and s["seguiram"] == []


def test_o_erp_ve_o_nome_de_antes_e_o_de_agora(tmp_path):
    pasta = str(tmp_path)
    C.apontar(pasta, LISTA, "TESOURA 1-1", "producao", 1, "x", nomes=ANTES)
    r = C.para_erp("obra", "OBRA", LISTA, C.ler_eventos(pasta), DEPOIS)
    assert r["eventos"][0]["marca"] == "TESOURA 1-1" and r["eventos"][0]["marca_atual"] == "TESOURA 1-2"
    assert {x["marca"]: x["producao"] for x in r["itens"]}["TESOURA 1-2"] == 1
