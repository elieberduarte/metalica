# -*- coding: utf-8 -*-
"""A barra comercial por perfil (o usuário, 09/10: "os TQ e TR são barras de 6 m, apenas perfil W são comprados em
barras de 12 m") e a quantidade "com recorte" do orçamento ao lado da "sem recorte" (o peso teórico)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import lista_producao as lp                         # noqa: E402
from saida import orcamento as orc                             # noqa: E402


def test_tubo_redondo_e_polegada_em_6m_w_em_12m_dobrado_como_antes():
    assert lp._barra_para([9219.0], 0, "TR 250x100x9,5") == 6000.0        # a viga de 9,2 m sai com emenda
    assert lp._barra_para([2500.0], 0, "TQ 50x50x3,0") == 6000.0
    assert lp._barra_para([8000.0], 0, "250x250x10SHS") == 6000.0
    assert lp._barra_para([480.0], 0, 'FE RED 1"') == 6000.0
    assert lp._barra_para([1900.0], 0, "L1.1/4''X1/8''") == 6000.0
    assert lp._barra_para([3000.0], 0, "W150X13") == 12000.0
    assert lp._barra_para([6300.0], 0, "U150X60X20X2.25") == 12000.0      # o dobrado maior que 6 m: a dobradeira
    assert lp._barra_para([5000.0], 0, "U150X60X20X2.25") == 6000.0
    r = lp.encaixar([9219.0], 6000.0)
    assert r["quantidade"] == 2 and r["emendas"] == 1


def test_com_recorte_ao_lado_do_teorico():
    lista = {
        "posicoes": [
            {"marca": "T1", "classe": "Barra", "perfil": "TQ 50x50x3,0", "quantidade": 10, "comprimento": 2500, "peso_total": 106.3},
            {"marca": "C1", "classe": "Chapa", "perfil": "CH 9,5", "espessura": 9.5, "quantidade": 4, "peso_total": 40.0},
        ],
        "perfis": [{"perfil": "TQ 50x50x3,0", "posicoes": ["T1"], "peso": 106.3, "kg_m": 4.25, "kg_m_catalogo": 4.25,
                    "barras": {"comprimento": 6000, "quantidade": 5}}],
    }
    R = orc.montar(lista, None)
    tubo = next(li for li in R["linhas"] if li["id"] == "tubo")
    chapa = next(li for li in R["linhas"] if li["id"].startswith("chapa:"))
    assert tubo["qtd"] == 106.3 and tubo["qtd_recorte"] == round(5 * 6.0 * 4.25, 1)   # 127,5: as 5 barras de 6 m
    assert chapa["qtd_recorte"] == round(40.0 * 1.15, 1)
    assert R["totais"]["aco_kg"] == 146.3 and R["totais"]["aco_kg_recorte"] == round(127.5 + 46.0, 1)
