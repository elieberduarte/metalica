# -*- coding: utf-8 -*-
"""Apontar vários itens de uma vez (FERRAMENTA · CONTROLE DE PRODUÇÃO, 13/11/2026).

O usuário escolhe os itens na lista (caixinhas, Ctrl+clique) ou no 3D ao lado (Ctrl+clique numa peça) e aponta tudo o que
falta na etapa em cada um — as 6 MT71 de uma vez em vez de 6 janelas. Um evento por item: o ERP, a nuvem e o estorno
seguem iguais ao apontar de um."""
import json
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from producao import controle as C                      # noqa: E402
from test_producao_controle import NOMES, _H, _lista     # noqa: E402


def _feito(pasta, nomes=NOMES):
    s = C.situacao(_lista(), C.ler_eventos(pasta), nomes)
    return {x["id"]: x["feito"] for x in s["itens"]}


def test_aponta_tudo_o_que_falta_em_cada_um(tmp_path):
    pasta = str(tmp_path)
    C.apontar(pasta, _lista(), "T.C.1", "producao", 40, "x", nomes=NOMES)            # faltam 6 das 46 terças
    r = C.apontar_varios(pasta, _lista(), ["MT71-1", "MT71-2", "MT71-3", "T.C.1", "T38-2"], "producao", "Fernando",
                         data="2026-11-12", obs="lote 1", nomes=NOMES)
    assert r["pulados"] == []
    assert [(e["item"], e["quantidade"]) for e in r["eventos"]] == [("MT71-1", 1), ("MT71-2", 1), ("MT71-3", 1),
                                                                   ("T.C.1", 6), ("T38-2", 1)]
    assert all(e["quem"] == "Fernando" and e["data"] == "2026-11-12" and e["obs"] == "lote 1" for e in r["eventos"])
    f = _feito(pasta)
    assert f["T.C.1"]["producao"] == 46 and f["MT71-2"]["producao"] == 1 and f["T38-1"]["producao"] == 0
    # cada item vira um apontamento no arquivo (o ERP e a nuvem leem um por um) e o estorno desfaz só o dele
    assert len(C.ler_eventos(pasta)) == 6
    C.estornar(pasta, r["eventos"][0]["id"], "x")
    f = _feito(pasta)
    assert f["MT71-1"]["producao"] == 0 and f["MT71-2"]["producao"] == 1


def test_o_completo_e_pulado_e_o_repetido_conta_uma_vez(tmp_path):
    pasta = str(tmp_path)
    C.apontar(pasta, _lista(), "T74", "pintura", 1, "x", nomes=NOMES)
    r = C.apontar_varios(pasta, _lista(), ["T74", "CV.2", "CV.2", "T74"], "pintura", "x", nomes=NOMES)
    assert r["pulados"] == ["T74"] and [(e["item"], e["quantidade"]) for e in r["eventos"]] == [("CV.2", 6)]
    with pytest.raises(C.ErroControle, match="completos na pintura"):
        C.apontar_varios(pasta, _lista(), ["T74", "CV.2"], "pintura", "x", nomes=NOMES)
    with pytest.raises(C.ErroControle, match="T74 já está completo"):
        C.apontar_varios(pasta, _lista(), ["T74"], "pintura", "x", nomes=NOMES)


@pytest.mark.parametrize("ids, etapa, msg", [
    ([], "producao", "nenhum item"),
    (["T38-1", "NÃO EXISTE"], "producao", "fora da lista"),
    (["T38-1"], "montagem", "etapa desconhecida"),
])
def test_recusa_sem_gravar_nada(tmp_path, ids, etapa, msg):
    pasta = str(tmp_path)
    with pytest.raises(C.ErroControle, match=msg):
        C.apontar_varios(pasta, _lista(), ids, etapa, "x", nomes=NOMES)
    assert C.ler_eventos(pasta) == []                  # o T38-1 do pedido com um item errado não foi gravado


def test_a_ancora_vai_em_cada_apontamento(tmp_path):
    """o apontamento de vários segue a peça como o de um (âncora: as peças da unidade no 3D)"""
    pasta = str(tmp_path)
    nomes = dict(NOMES, unidades={"M51": [{"nome": "T38-1", "ids": ["b2", "b1"], "meio": [0, 0, 0]},
                                          {"nome": "T38-2", "ids": ["c1"], "meio": [0, 9000, 0]}]})
    r = C.apontar_varios(pasta, _lista(), ["T38-1", "T38-2", "T.C.1"], "producao", "x", nomes=nomes)
    anc = {e["item"]: e.get("ancora") for e in r["eventos"]}
    assert anc == {"T38-1": ["b1", "b2"], "T38-2": ["c1"], "T.C.1": None}


def test_rota_aponta_varios_e_a_tela_tem_a_escolha(monkeypatch, tmp_path):
    from producao import web
    pasta = tmp_path / "obra"
    (pasta / "detalhamento").mkdir(parents=True)
    (pasta / "detalhamento" / "lista-de-materiais.json").write_text(json.dumps(_lista()), encoding="utf-8")
    (pasta / "detalhamento" / "nomes.json").write_text(json.dumps(NOMES), encoding="utf-8")
    monkeypatch.setattr(web, "_pasta", lambda s: str(pasta))
    monkeypatch.setattr(web, "_quem", lambda: "Fulano")
    monkeypatch.setattr(web, "_sincronizar", lambda p: None)
    h = _H("/api/producao/apontar-varios")
    assert web.rota_post(h, "/api/producao/apontar-varios",
                         {"projeto": "obra", "itens": ["MT71-1", "MT71-2"], "etapa": "producao", "data": "2026-11-13"})
    assert h.resposta["ok"] and h.resposta["pulados"] == []
    assert [e["item"] for e in h.resposta["eventos"]] == ["MT71-1", "MT71-2"] and h.resposta["eventos"][0]["quem"] == "Fulano"
    # a tela: as caixinhas, a faixa e a rota; o 3D soma pelo Ctrl+clique
    js = open(os.path.join(os.path.dirname(AQUI), "web", "producao", "controle.js"), encoding="utf-8").read()
    assert "/api/producao/apontar-varios" in js and "ctl-marcar-todos" in js and "controle:alternar" in js
    js3 = open(os.path.join(os.path.dirname(AQUI), "web", "producao", "controle3d.js"), encoding="utf-8").read()
    assert "controle:varios" in js3 and "controle:alternar" in js3
