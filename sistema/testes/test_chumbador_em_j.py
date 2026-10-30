# -*- coding: utf-8 -*-
"""O chumbador em J é cortado com o gancho (Hora Certa · Galpão Existente, 29/10, auditor N05).

O 3D tem a perna reta e o gancho desenvolvido em `atributos.gancho_mm` (ligacoes3d "chumbador_gancho", scripts de obra);
o levantamento media só o eixo: o CB3 Ø36 saía com 1.100 (é 1.100 + 180), o CB2 Ø12 com 347 (é 347 + 137, a tabela da
980 dá 0,426 kg por peça = 480 mm) — 174 chumbadores curtos, −113 kg, 5 CB3 por barra de 6 m em vez de 4.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest  # noqa: E402

from nucleo3d import geometria as geo  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402
from nucleo2d.detalhar import levantar  # noqa: E402


def _doc(d, reto, gancho):
    geo.registrar_perfil(geo.barra_redonda(d, "BARRA REDONDA %g" % d))
    doc = Documento(nome="chumbador")
    at = {"tipo_ifc": "IfcMember", "elemento": "Chumbador", "funcao": "chumbador", "projecao_mm": 140.0}
    if gancho:
        at["gancho_mm"] = gancho
    for k in range(2):
        doc.add(Barra(nome="Chumbador", inicio=(k * 300.0, 0.0, 140.0), fim=(k * 300.0, 0.0, 140.0 - reto),
                      perfil="BARRA REDONDA %g" % d, papel="chumbador", material="Aço", aco="ISO 898 C4.6",
                      atributos=dict(at)))
    return doc


def _posicao(doc):
    pos = [p for p in levantar(doc, regra_tercas=False)["posicoes"]]
    assert len(pos) == 1
    return pos[0]


@pytest.mark.parametrize("d, reto, gancho", [(36.0, 1100.0, 180.0), (12.0, 347.0, 137.0)])
def test_comprimento_de_corte_e_o_reto_mais_o_gancho(d, reto, gancho):
    p = _posicao(_doc(d, reto, gancho))
    assert p.comprimento == pytest.approx(reto + gancho, abs=1.0)
    assert any("gancho" in o for o in p.observacoes)


def test_cb2_pesa_como_a_tabela_do_projetista():
    """28 Ø12 = 11,93 kg na tabela da 980: 0,426 kg por peça"""
    from nucleo2d.detalhe.base import peso_teorico
    p = _posicao(_doc(12.0, 347.0, 137.0))
    assert peso_teorico(p) == pytest.approx(0.426, abs=0.01)


def test_chumbador_reto_sem_gancho_nao_muda():
    p = _posicao(_doc(36.0, 1100.0, None))
    assert p.comprimento == pytest.approx(1100.0, abs=1.0)
