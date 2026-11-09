# -*- coding: utf-8 -*-
"""Porcas e arruelas: só as avulsas (usuário, 09/11, pelo GESTÃO N.6 — Padrao-quantitativo-orcamento.md, "PORCAS E ARRUELAS:
SÓ AS AVULSAS"; vale para todas as obras).

O parafuso estrutural é comprado em KIT ("+ porca e arruela"). O resumo de compra somava 1 porca + 1 arruela por parafuso
nas linhas "Porca"/"Arruela" e a lista de materiais as punha em linhas "(dos parafusos)" — em dobro: na Sala de Compressores
da Sooro a porca 1/2" saía 906 = 280 + 24 + 602 parafusos M12, todas dos kits. Agora essas linhas levam só as avulsas
(barras roscadas, tirantes, ganchos, chumbadores); o químico do chumbador (furos/ml) não muda."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from saida import resumos  # noqa: E402
from saida.lista_producao import acessorios_da_lista  # noqa: E402


def _sala():
    """Os parafusos e as avulsas da Sala de Compressores (planilha do GESTÃO, ME-Sooro/Comum rev4)."""
    kit = lambda nome, q: {"nome": nome, "descricao": "Parafuso sextavado Ø1/2\" + porca e arruela", "qtd": q,  # noqa: E731
                           "parafuso": True, "d": 12.0}
    solta = lambda nome, q, d: {"nome": nome, "descricao": "", "qtd": q, "parafuso": False, "d": d}  # noqa: E731
    return [kit("Parafuso M12x35", 280), kit("Parafuso M12x40", 24), kit("Parafuso M12x45", 602),
            solta('Porca 3/8"', 84, 9.5), solta('Arruela 3/8"', 168, 9.5), solta('Porca 5/8"', 64, 15.9),
            solta('Arruela 5/8"', 104, 15.9), solta('Porca 3/4"', 56, 19.05), solta('Arruela 3/4"', 28, 19.05)]


def test_a_compra_leva_so_as_porcas_e_arruelas_avulsas():
    C = resumos._compra({"perfis": [], "posicoes": []}, _sala(), {}, {})
    assert dict(C["porcas"]) == {'3/8"': 84, '5/8"': 64, '3/4"': 56}, C["porcas"]          # sem as 906 dos kits M12
    assert dict(C["arruelas"]) == {'3/8"': 168, '5/8"': 104, '3/4"': 28}, C["arruelas"]
    assert sum(p["qtd"] for p in C["parafusos"]) == 906                                    # os kits seguem na linha deles


def test_o_quimico_do_chumbador_nao_muda():
    hitv = {"nome": "Chumbador", "descricao": "+ porca e arruela", "qtd": 10, "parafuso": True, "d": 12.7,
            "embutimento": 150.0, "quimico": "HIT-RE 500"}
    C = resumos._compra({"perfis": [], "posicoes": []}, [hitv], {}, {})
    assert dict(C["porcas"]) == {} and dict(C["arruelas"]) == {}
    (q,) = C["quimicos"]
    assert q["furos"] == 10 and q["cartuchos"] == 1


def test_a_lista_de_materiais_sem_as_porcas_dos_parafusos():
    L = acessorios_da_lista({"BOLT (A307) 12x35": 280, "BOLT (A307) 12x45": 602,
                             'Porca sextavada Ø5/8" UNC': 64, 'Arruela lisa Ø5/8"': 104})
    nomes = {a["nome"]: a["quantidade"] for a in L}
    assert not any("dos parafusos" in n for n in nomes), nomes
    assert nomes['Porca sextavada Ø5/8" UNC'] == 64 and nomes['Arruela lisa Ø5/8"'] == 104
    assert sum(q for n, q in nomes.items() if n.startswith("Parafuso")) == 882
    assert not any(n.startswith(("Porca", "Arruela")) and "M12" in n for n in nomes), nomes
