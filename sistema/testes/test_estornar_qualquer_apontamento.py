# -*- coding: utf-8 -*-
"""O estorno alcança QUALQUER apontamento, não só os 30 últimos da obra (risco 2 do GESTÃO, 13/11/2026, antes de o Fernando
apontar no Posto).

Antes: a tela só tinha Estornar na tabela "Últimos apontamentos", que mostra os 30 mais novos da obra (situacao(...,
ultimos=30)). O Posto já tinha 30 linhas: o 1º apontamento do Fernando tirava o mais antigo da tela, e um erro mais velho
não se desfazia por ali. Agora a janela Apontar de cada item mostra TODOS os apontamentos dele, com Estornar
(controle.historico, GET /api/producao/historico), e os nomes "fora da lista" abrem os deles."""
import json
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from producao import controle as C                      # noqa: E402
from test_producao_controle import NOMES, _H, _lista    # noqa: E402
from test_montadas_no_controle import DEPOIS, LISTA     # noqa: E402


def _35_apontamentos(pasta):
    """o 1º é de CV.2; depois 34 de uma terça por vez — 35 eventos, o 1º fora dos 30 da tela"""
    primeiro = C.apontar(pasta, _lista(), "CV.2", "producao", 1, "x", nomes=NOMES)
    for _ in range(34):
        C.apontar(pasta, _lista(), "T.C.1", "producao", 1, "x", nomes=NOMES)
    return primeiro


def test_o_primeiro_de_35_some_da_tabela_mas_o_item_o_mostra_e_estorna(tmp_path):
    pasta = str(tmp_path)
    primeiro = _35_apontamentos(pasta)
    s = C.situacao(_lista(), C.ler_eventos(pasta), NOMES)
    assert primeiro["id"] not in {e["id"] for e in s["eventos"]}           # a tabela de baixo não o tem mais
    h = C.historico(_lista(), C.ler_eventos(pasta), "CV.2", NOMES)
    assert [e["id"] for e in h] == [primeiro["id"]] and not h[0]["estornado"]
    C.estornar(pasta, primeiro["id"], "x")
    h = C.historico(_lista(), C.ler_eventos(pasta), "CV.2", NOMES)
    assert [e.get("estorno_de") for e in h] == [primeiro["id"], None] and h[1]["estornado"]   # o estorno em cima
    s = C.situacao(_lista(), C.ler_eventos(pasta), NOMES)
    assert {x["id"]: x["feito"]["producao"] for x in s["itens"]}["CV.2"] == 0
    # a terça tem os 34 dela, o mais novo em cima
    ht = C.historico(_lista(), C.ler_eventos(pasta), "T.C.1", NOMES)
    assert len(ht) == 34 and ht[0]["quando"] >= ht[-1]["quando"]


def test_a_montada_mostra_os_das_partes_e_o_nome_fora_da_lista_os_dele(tmp_path):
    pasta = str(tmp_path)
    C.apontar(pasta, LISTA, "T52", "producao", 1, "x", nomes=DEPOIS)
    h = C.historico(LISTA, C.ler_eventos(pasta), "T52", DEPOIS)
    assert sorted(e["item"] for e in h) == ["TESOURA 1-2", "TESOURA 5"] and all(e["montada_atual"] == "T52" for e in h)
    # um apontamento de um item que sumiu da lista
    with open(C.caminho(pasta), "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": "velho", "quando": "2026-11-12T08:00:00", "data": "2026-11-12", "item": "T99-1",
                            "etapa": "producao", "quantidade": 1, "kg": 10, "estorno_de": None}) + "\n")
    assert [e["id"] for e in C.historico(LISTA, C.ler_eventos(pasta), "T99-1", DEPOIS)] == ["velho"]
    with pytest.raises(C.ErroControle, match="não está na lista"):
        C.historico(LISTA, C.ler_eventos(pasta), "NÃO EXISTE", DEPOIS)


def test_rota_do_historico_e_a_tela_estorna_pelo_item(monkeypatch, tmp_path):
    from producao import web
    pasta = tmp_path / "obra"
    (pasta / "detalhamento").mkdir(parents=True)
    (pasta / "detalhamento" / "lista-de-materiais.json").write_text(json.dumps(_lista()), encoding="utf-8")
    (pasta / "detalhamento" / "nomes.json").write_text(json.dumps(NOMES), encoding="utf-8")
    primeiro = _35_apontamentos(str(pasta))
    monkeypatch.setattr(web, "_pasta", lambda s: str(pasta))
    monkeypatch.setattr(web, "_app", lambda: type("_AppDev", (), {"DEV": True}))
    h = _H("/api/producao/historico?projeto=obra&item=CV.2")
    assert web.rota_get(h, "/api/producao/historico")
    assert [e["id"] for e in h.resposta["eventos"]] == [primeiro["id"]]
    # a tela: a janela Apontar do item traz o histórico dele, com Estornar; o "fora da lista" abre o do nome
    js = open(os.path.join(os.path.dirname(AQUI), "web", "producao", "controle.js"), encoding="utf-8").read()
    corpo = js[js.index("function abrirDialogo("):js.index("async function estornar(")]
    assert "secaoHistorico(item.id)" in corpo
    sec = js[js.index("function secaoHistorico("):js.index("function dialogoHistorico(")]
    assert "/api/producao/historico" in sec and "tabelaEventos(" in sec
    assert "dialogoHistorico(nome)" in js
