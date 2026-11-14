# -*- coding: utf-8 -*-
"""Pintura só do que foi produzido, e a cor do 3D igual ao número da tabela (risco 3 do GESTÃO, 13/11/2026, antes de o
Fernando apontar no Posto).

Antes: o servidor aceitava pintar o que não tinha a produção apontada; o 3D (controle3d.js) contava a peça pintada como
produzida e a coluna Produção e o cartão não — a cor e o número diziam coisas diferentes. Agora:
  * o servidor recusa pintar mais do que o produzido, com o recado "falta apontar a produção de N antes da pintura";
  * apontar vários na pintura leva só o produzido; o item sem produção fica de fora ("sem_anterior");
  * a montada só se pinta com as partes que faltam produzidas;
  * a tabela, o cartão, o andamento em kg e a cor do 3D saem da MESMA conta (controle.contagem → "conta" de cada item);
    o pintado sem produção que já estiver no arquivo (de antes, ou da nuvem) não conta e fica à vista ("sem_anterior")."""
import json
import os
import re
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from producao import controle as C                      # noqa: E402
from test_producao_controle import NOMES, _lista        # noqa: E402
from test_montadas_no_controle import DEPOIS, LISTA     # noqa: E402

WEB = os.path.join(os.path.dirname(AQUI), "web", "producao")


def _sit(pasta, lista=None, nomes=NOMES):
    s = C.situacao(lista or _lista(), C.ler_eventos(pasta), nomes)
    return s, {x["id"]: x for x in s["itens"]}


def test_pintura_sem_producao_e_recusada_sem_gravar(tmp_path):
    pasta = str(tmp_path)
    with pytest.raises(C.ErroControle, match="T.C.1: falta apontar a produção de 30 antes da pintura"):
        C.apontar(pasta, _lista(), "T.C.1", "pintura", 30, "x", nomes=NOMES)
    with pytest.raises(C.ErroControle, match="T38-1: falta apontar a produção de 1 antes da pintura"):
        C.apontar(pasta, _lista(), "T38-1", "pintura", 1, "x", nomes=NOMES)
    assert C.ler_eventos(pasta) == []


def test_pinta_ate_o_produzido(tmp_path):
    pasta = str(tmp_path)
    C.apontar(pasta, _lista(), "T.C.1", "producao", 20, "x", nomes=NOMES)
    with pytest.raises(C.ErroControle, match=r"falta apontar a produção de 10 antes da pintura \(só 20 com a produção"):
        C.apontar(pasta, _lista(), "T.C.1", "pintura", 30, "x", nomes=NOMES)
    C.apontar(pasta, _lista(), "T.C.1", "pintura", 20, "x", nomes=NOMES)
    with pytest.raises(C.ErroControle, match="falta apontar a produção de 1 antes da pintura"):
        C.apontar(pasta, _lista(), "T.C.1", "pintura", 1, "x", nomes=NOMES)
    _, por = _sit(pasta)
    assert por["T.C.1"]["conta"] == {"producao": 20, "pintura": 20}


def test_varios_na_pintura_leva_so_o_produzido(tmp_path):
    pasta = str(tmp_path)
    C.apontar(pasta, _lista(), "T38-1", "producao", 1, "x", nomes=NOMES)
    C.apontar(pasta, _lista(), "T.C.1", "producao", 20, "x", nomes=NOMES)
    r = C.apontar_varios(pasta, _lista(), ["T38-1", "T38-2", "T.C.1"], "pintura", "x", nomes=NOMES)
    assert [(e["item"], e["quantidade"]) for e in r["eventos"]] == [("T38-1", 1), ("T.C.1", 20)]
    assert r["sem_anterior"] == ["T38-2"] and r["pulados"] == []
    with pytest.raises(C.ErroControle, match="falta apontar a produção antes da pintura: T38-2, CV.2"):
        C.apontar_varios(pasta, _lista(), ["T38-2", "CV.2"], "pintura", "x", nomes=NOMES)


def test_montada_so_se_pinta_com_as_partes_produzidas(tmp_path):
    pasta = str(tmp_path)
    with pytest.raises(C.ErroControle, match="falta apontar a produção antes da pintura: T52"):
        C.apontar(pasta, LISTA, "T52", "pintura", 1, "x", nomes=DEPOIS)
    C.apontar(pasta, LISTA, "T52", "producao", 1, "x", nomes=DEPOIS)
    ev = C.apontar(pasta, LISTA, "T52", "pintura", 1, "x", nomes=DEPOIS)
    assert ev["montada"] == "T52" and len(ev["junto"]) == 1
    _, por = _sit(pasta, LISTA, DEPOIS)
    assert por["T52"]["conta"] == {"producao": 1, "pintura": 1}


def test_a_pintura_antiga_sem_producao_nao_conta_e_fica_a_vista(tmp_path):
    """um apontamento de pintura sem produção que já está no arquivo (de antes de 14/11, ou chegado da nuvem): a coluna,
    o cartão e a cor do 3D (todos pela `conta`) não o contam, e a tela diz "N sem produção\""""
    pasta = str(tmp_path)
    os.makedirs(os.path.join(pasta, C.PASTA))
    with open(C.caminho(pasta), "w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "antigo", "quando": "2026-11-13T14:00:00", "data": "2026-11-13", "quem": "x",
                            "etapa": "pintura", "item": "T.C.1", "refs": ["P22"], "quantidade": 10, "kg": 136.0,
                            "estorno_de": None, "obs": ""}) + "\n")
    s, por = _sit(pasta)
    tc = por["T.C.1"]
    assert tc["feito"] == {"producao": 0, "pintura": 10}            # o apontado (o ERP lê)
    assert tc["conta"] == {"producao": 0, "pintura": 0}             # o que vale na tela e no 3D
    assert tc["sem_anterior"] == {"pintura": 10}
    assert s["andamento"]["pintura"]["kg"] == 0 and s["andamento"]["pintura"]["itens_completos"] == 0
    # produzidas 4: contam 4 pintadas, 6 seguem "sem produção"
    C.apontar(pasta, _lista(), "T.C.1", "producao", 4, "x", nomes=NOMES)
    s, por = _sit(pasta)
    assert por["T.C.1"]["conta"] == {"producao": 4, "pintura": 4} and por["T.C.1"]["sem_anterior"] == {"pintura": 6}
    assert s["andamento"]["pintura"]["kg"] == pytest.approx(4 * 13.6, abs=0.1)


def test_contagem_e_a_conta_unica():
    assert C.contagem({"producao": 3, "pintura": 5}, 4) == {"producao": 3, "pintura": 3}
    assert C.contagem({"producao": 9, "pintura": 2}, 4) == {"producao": 4, "pintura": 2}
    assert C.contagem({}, 1) == {"producao": 0, "pintura": 0}


def _corpo(js: str, inicio: str) -> str:
    i = js.index(inicio)
    return js[i:js.index("\n  }\n", i)]


def test_a_cor_do_3d_e_o_numero_da_tabela_leem_a_mesma_conta():
    """a divergência era o defeito: o 3D somava max(produção, pintura) e a coluna lia só a produção. Agora os dois leem a
    `conta` do servidor e nenhum refaz a conta pelo `feito`."""
    js3 = open(os.path.join(WEB, "controle3d.js"), encoding="utf-8").read()
    pintar = _corpo(js3, "function pintar()")
    assert "x.conta" in pintar and not re.search(r"\.feito\b|f\.pintura|f\.producao", pintar), pintar
    js = open(os.path.join(WEB, "controle.js"), encoding="utf-8").read()
    cel = _corpo(js, "function situacaoCelula(")
    assert "x.conta" in cel
    mont = _corpo(js, "function situacaoMontada(")
    assert "x.conta" in mont and "p.conta" in mont
    # o cartão vem do andamento do servidor (a mesma conta)
    assert "D.andamento[et.chave]" in js
