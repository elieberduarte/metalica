# -*- coding: utf-8 -*-
"""As variantes da mesma peça acendem sozinhas no 3D do Controle (13/11/2026).

No Posto, as chapas "Suporte de terça ST1 (aa)", "(ab)"… são variantes que a lista separa pela forma; no 3D todas se
chamam "Suporte de terça ST1" e não têm marca de posição. O 3D do Controle as juntava num grupo só (pintado na proporção).
O Detalhar já guarda no nomes.json quais peças são cada variante ("variantes" {id: [posição, conjunto]}): o item da
variante leva essas peças (pecas3d) e o 3D acende cada uma sozinha."""
import os
import re
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from producao import controle as C                      # noqa: E402

LISTA = {"posicoes": [
    {"marca": "Suporte de terça ST1", "nome": "CH36", "categoria": "CHAPAS", "quantidade": 5, "peso": 1.0, "perfil": "CH 6,3"},
    {"marca": "Suporte de terça ST1 (aa)", "nome": "CH37", "categoria": "CHAPAS", "quantidade": 1, "peso": 1.0, "perfil": "CH 6,3"},
    {"marca": "Suporte de terça ST1 (ac) / Suporte de terça ST1 (x)", "nome": "CH38", "categoria": "CHAPAS", "quantidade": 2,
     "peso": 1.0, "perfil": "CH 6,3"},
    {"marca": "Suporte de terça ST1 (b)", "nome": "CH39", "categoria": "CHAPAS", "quantidade": 2, "peso": 1.0, "perfil": "CH 6,3"},
], "conjuntos": []}
NOMES = {"variantes": {"e1": ["Suporte de terça ST1 (aa)", ""], "e2": ["Suporte de terça ST1 (ac)", ""],
                       "e3": ["Suporte de terça ST1 (x)", ""],
                       "e4": ["Suporte de terça ST1 (b)", ""],                 # a (b) tem 2 na lista e 1 peça aqui: não fecha
                       "e5": ["Suporte de terça ST1 (aa)", "M7"]}}            # dentro de um conjunto: não é a avulsa


def test_a_variante_leva_as_pecas_dela():
    por = {x["id"]: x for x in C.itens(LISTA, NOMES)}
    assert por["CH37"]["pecas3d"] == ["e1"]
    assert por["CH38"]["pecas3d"] == ["e2", "e3"]             # a linha fundida junta as peças das duas partes
    assert "pecas3d" not in por["CH39"]                       # não fecha com a quantidade: fica no grupo, como antes
    assert "pecas3d" not in por["CH36"]                       # a peça-base continua pelo nome
    assert C.ancora(por["CH38"]) == ["e2", "e3"]              # e o apontamento dela segue a peça


def test_a_tela_usa_as_pecas_da_variante_antes_do_nome():
    js = open(os.path.join(os.path.dirname(AQUI), "web", "producao", "controle3d.js"), encoding="utf-8").read()
    i_var = js.index("x.origem !== 'pecas' || !(x.pecas3d || []).length")
    i_nome = js.index("for (const p of partes(x))")
    assert i_var < i_nome


def test_posto_cada_variante_com_as_suas_pecas():
    from test_producao_controle import POSTO
    if not os.path.exists(os.path.join(POSTO, "detalhamento", "nomes.json")):
        pytest.skip("o Posto só existe na máquina do usuário")
    N = C.ler_nomes(POSTO)
    if not N.get("variantes"):
        pytest.skip("o Posto sem variantes gravadas")
    its = C.itens(C.ler_lista(POSTO), N)
    # as linhas inteiras de variantes ("CH36" junta a peça-base com as variantes (b), (e), (i): continua pelo nome)
    var = [x for x in its if x["origem"] == "pecas" and all(re.search(r" \([a-z]{1,2}\)$", m) for m in x["refs"][0].split(" / "))]
    assert var and all(len(x.get("pecas3d") or []) == x["quantidade"] for x in var), \
        [(x["id"], x["quantidade"], len(x.get("pecas3d") or [])) for x in var if len(x.get("pecas3d") or []) != x["quantidade"]]
    todas = [i for x in var for i in x["pecas3d"]]
    assert len(todas) == len(set(todas))                      # nenhuma peça em duas variantes
    # e a peça-base fica com o resto: as 331 "Suporte de terça ST1" do 3D = 38 nas variantes + 293 no CH36 (a lista)
    import json
    m = json.load(open(os.path.join(POSTO, "modelo.json"), encoding="utf-8"))
    nome = {str(e["id"]): e.get("nome") for e in m["entidades"]}
    st1 = sum(1 for e in m["entidades"] if e.get("nome") == "Suporte de terça ST1" and not (e.get("atributos") or {}).get("marcas"))
    nas_var = sum(1 for i in todas if nome.get(i) == "Suporte de terça ST1")
    base = next(x for x in its if x["refs"][0].split(" / ")[0] == "Suporte de terça ST1")
    assert st1 - nas_var == base["quantidade"], (st1, nas_var, base["quantidade"])
