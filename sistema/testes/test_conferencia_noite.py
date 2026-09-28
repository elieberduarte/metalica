# -*- coding: utf-8 -*-
"""A conferência seletiva por área e a rodada da noite (empacotar/publicar_noite.py), 28/09."""
import importlib.util
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))

import selecao  # noqa: E402


def _noite():
    caminho = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "empacotar", "publicar_noite.py")
    spec = importlib.util.spec_from_file_location("publicar_noite", caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_detalhamento_nao_dispara_a_completa(monkeypatch):
    """Mudança só no detalhamento (nucleo2d/): os verificadores do 2D e a bateria das obras — o 3D
    fica de fora. O núcleo de cálculo continua pedindo a completa."""
    monkeypatch.setattr(selecao, "versoes_desde_completa", lambda: 0)
    monkeypatch.setattr(selecao, "mudados", lambda base: ["nucleo2d/detalhar.py", "testes/test_detalhar2d.py"])
    e = selecao.escolher(False, "v0.0.1")
    assert not e["completa"] and e["bateria_ifc"] and not e["bateria_planta"]
    assert "verif_cad" in e["verificadores"] and "verif_detalhar" in e["verificadores"]
    assert "verificar_zoom" not in e["verificadores"] and "verif_reabrir" not in e["verificadores"]
    monkeypatch.setattr(selecao, "mudados", lambda base: ["nucleo/calculo.py"])
    assert selecao.escolher(False, "v0.0.1")["completa"]


def test_bateria_da_noite_so_publica_igual(tmp_path):
    n = _noite()
    n.PROJETO = str(tmp_path)
    (tmp_path / "bateria").mkdir()
    arq = tmp_path / "bateria" / "ultima-comparacao.txt"
    arq.write_text("x\n\n== a\n  igual à rodada aceita\n\n== b\n  primeira rodada\n", encoding="utf-8")
    assert n.bateria_igual(0)[0]
    arq.write_text("x\n\n== a\n  igual à rodada aceita\n\n== b\n  desenho x: 10 → 12 entidades\n", encoding="utf-8")
    assert not n.bateria_igual(0)[0]
    assert not n.bateria_igual(os.path.getmtime(arq) + 60)[0]      # relatório de antes desta rodada


def test_frase_e_proxima_versao():
    n = _noite()
    assert n._proxima("0.8.49") == "0.8.50"
    assert n._frase("Corte: o forro não entra (pedido do usuário, 28/09). O resto") == "Corte: o forro não entra"
