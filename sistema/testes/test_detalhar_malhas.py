# -*- coding: utf-8 -*-
"""O desenho dos conjuntos faz a malha de cada peça do modelo uma vez só (29/10/2026, Edifício Administrativo da Hora
Certa: "desenhando conjuntos" levou 36 dos 41 min do Detalhar — _vizinhos_no_plano e _cortes_das_tercas faziam a malha
de todas as 5.562 peças, 12,8 s, duas vezes em cada um dos 82 conjuntos). O desenho tem de sair igual ao de antes, e a
etapa diz o andamento "(i de n)" (o vigia do dev e a barra)."""
import collections
import contextlib
import copy
import json
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nucleo3d import geometria as G  # noqa: E402
from nucleo2d import detalhar as DT  # noqa: E402
from test_calculo_ifc import _modelo  # noqa: E402


def _sem_ids(x):
    """o desenho sem os ids sorteados das entidades 2D"""
    if isinstance(x, dict):
        return {k: _sem_ids(v) for k, v in x.items() if k != "id"}
    if isinstance(x, list):
        return [_sem_ids(v) for v in x]
    return x


def _rodar(doc, monkeypatch, com_cache: bool):
    contagem = collections.Counter()
    real = G.malha

    def contar(e):
        contagem[id(e)] += 1
        return real(e)
    monkeypatch.setattr(G, "malha", contar)
    if not com_cache:
        monkeypatch.setattr(DT, "malhas_guardadas", contextlib.nullcontext, raising=False)
    etapas = []
    r = DT.detalhar(doc, ["tesouras"], avisar=lambda etapa, *a: etapas.append(etapa))
    monkeypatch.undo()
    texto = json.dumps(_sem_ids(r["desenhos"]["tesouras"].dict()), sort_keys=True, default=str)
    return texto, contagem, etapas


def test_conjuntos_fazem_a_malha_de_cada_peca_uma_vez(monkeypatch):
    base = _modelo()[0]
    antes, cont_antes, _ = _rodar(copy.deepcopy(base), monkeypatch, com_cache=False)
    depois, cont_depois, etapas = _rodar(copy.deepcopy(base), monkeypatch, com_cache=True)
    assert depois == antes, "o desenho das tesouras mudou com as malhas guardadas"
    assert max(cont_antes.values()) >= 2, "o caso tem de refazer malha sem o cache (senão o teste não prova nada)"
    assert max(cont_depois.values()) == 1, "cada peça uma malha só: %d" % max(cont_depois.values())
    assert any(re.match(r"desenhando tesouras \(\d+ de \d+\)…$", e) for e in etapas), etapas
