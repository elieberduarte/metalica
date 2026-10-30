# -*- coding: utf-8 -*-
"""O chumbador sem porca no modelo leva o padrão da fábrica na lista, com aviso (FAB-05, reincidência — Hora Certa ·
Galpão Existente, 30/10, auditor N06).

O modelo montado das folhas do projetista não traz a porca que a folha desenha; com nenhuma porca modelada, o chumbador
não tinha "ponta roscada" e a lista saía sem porca nem arruela para os 218 chumbadores (Ø12, Ø36, ⅝"), no projeto
recebido E no nosso. Agora: 2 porcas + 1 arruela por perna e o aviso para conferir com a folha. O chumbador soldado na
chapa (sem `projecao_mm`) não muda.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest  # noqa: E402

from nucleo3d import geometria as geo  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402
from nucleo2d.detalhar import levantar  # noqa: E402


def _doc(origem, projecao=140.0, perfil="FE RED 5/8''", d=15.875):
    geo.registrar_perfil(geo.barra_redonda(d, perfil))
    doc = Documento(nome="chumbadores")
    doc.metadados = dict(getattr(doc, "metadados", None) or {}, origem_projeto=origem)
    at = {"tipo_ifc": "IfcMember", "elemento": "Chumbador", "funcao": "chumbador"}
    if projecao:
        at["projecao_mm"] = projecao
    for k in range(4):
        doc.add(Barra(nome="Chumbador", inicio=(k * 200.0, 0.0, projecao or 0.0), fim=(k * 200.0, 0.0, -600.0),
                      perfil=perfil, papel="chumbador", material="Aço", aco="ASTM A36", atributos=dict(at)))
    return doc


@pytest.mark.parametrize("origem", ["recebido", "nosso"])
def test_chumbador_sem_porca_leva_o_padrao_e_avisa(origem):
    r = levantar(_doc(origem), regra_tercas=False)
    ac = r["acessorios"]
    assert ac.get('Porca sextavada Ø5/8" UNC') == 8 and ac.get('Arruela lisa Ø5/8"') == 4, ac
    assert any("sem porca no modelo" in a for a in r.get("avisos") or []), r.get("avisos")


def test_chumbador_em_milimetro():
    r = levantar(_doc("recebido", perfil="BARRA REDONDA 36", d=36.0), regra_tercas=False)
    assert r["acessorios"].get("Porca sextavada M36") == 8


def test_chumbador_soldado_sem_projecao_nao_muda():
    r = levantar(_doc("recebido", projecao=None), regra_tercas=False)
    assert not any("orca" in k for k in r["acessorios"]), r["acessorios"]
