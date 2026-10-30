# -*- coding: utf-8 -*-
"""A tesoura montada não pega o nome de um conjunto (Hora Certa · Galpão Existente, 29/10, auditor N04).

As montadas eram numeradas "T1, T2…" sem olhar os nomes que os conjuntos já tinham: a PR.04 "T2 – 01x" (MT1 + MT20,
~331 kg) e a PR.06 "T2 – 03x" (M1095, 79,5 kg); a PR.05 "T3" (MT13 + MT14) e a PR.07 "T3" (a TS01).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from nucleo2d.detalhe.nomes import numerar_estavel  # noqa: E402


def test_montadas_pulam_os_nomes_dos_conjuntos():
    conjuntos = {"M1095": "T2", "M109": "T3", "M200": "MT1", "M201": "MT20"}
    r = numerar_estavel(["MT1 + MT5", "MT1 + MT20", "MT13 + MT14"], None, "T", reservados=set(conjuntos.values()))
    assert set(r.values()).isdisjoint({"T2", "T3"})
    assert len(set(r.values())) == 3
    assert r == {"MT1 + MT5": "T1", "MT1 + MT20": "T4", "MT13 + MT14": "T5"}


def test_nome_guardado_que_virou_de_conjunto_e_trocado():
    """o "T2" guardado no nomes.json da montada (D9) não vale se um conjunto passou a usá-lo"""
    r = numerar_estavel(["MT1 + MT20"], {"MT1 + MT20": "T2"}, "T", reservados={"T2"})
    assert r["MT1 + MT20"] != "T2"


def test_sem_reservados_a_numeracao_estavel_de_antes():
    assert numerar_estavel(["a", "b"], {"a": "T1", "b": "T2"}, "T") == {"a": "T1", "b": "T2"}
    assert numerar_estavel(["a", "b", "c"], {"b": "T5"}, "T") == {"b": "T5", "a": "T6", "c": "T7"}
