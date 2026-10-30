# -*- coding: utf-8 -*-
"""Quantas cópias de uma montagem a prancha do conjunto leva (Hora Certa · Galpão Existente, 29/10, auditor N02).

A conta era o MÁXIMO de uma parte presente: basta o CH1 estar na prancha para o S.T.2 (CH1 + CH35) sair "59x" nas
tesouras que só levam S.T.1 (CH1 + CH2); 20 das 29 cópias de montagem das pranchas de conjunto estavam erradas.
Os números são os da tabela do auditor (Projeto/ANALISES/Consistencia/Auditor-galpao-existente-2026-10-29/).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest  # noqa: E402

from nucleo2d.pranchas import _copias_da_montagem  # noqa: E402


@pytest.mark.parametrize("montagem, por_nome, esperado", [
    ("CH1 + CH35", {"CH1": 59, "CH2": 59}, 0),                   # PR.04: S.T.2 dizia 59, as T1/T2 só levam S.T.1
    ("CH1 + CH2", {"CH1": 59, "CH2": 59}, 59),                   # o S.T.1 da mesma prancha continua 59
    ("CH1 + CH2", {"CH1": 35, "CH2": 23, "CH35": 12}, 23),       # PR.06: dizia 35
    ("CH1 + CH35", {"CH1": 35, "CH2": 23, "CH35": 12}, 12),      # PR.06: dizia 35
    ("CB2 + CB2 + CH5 + CH12", {"CB2": 36, "CH5": 18, "CH12": 18}, 18),   # PR.16: dizia 36 (2 chumbadores por base)
    ("CH2 + DP.3.2", {"CH2": 28}, 0),                            # PR.17: a parte DP.3.2 não está na prancha
    ("", {"CH1": 3}, 0),
])
def test_copias_pelo_minimo_das_partes(montagem, por_nome, esperado):
    assert _copias_da_montagem(montagem, por_nome) == esperado
