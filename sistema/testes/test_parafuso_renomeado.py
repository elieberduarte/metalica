# -*- coding: utf-8 -*-
"""O parafuso renomeado continua parafuso (Hora Certa · Galpão Existente, 29/10).

O módulo do mezanino trocava o nome de cada parafuso da biblioteca de ligações para só "Parafuso"; sem o "d × L" no
nome, o detalhe o tomava por porca solta do IFC ("BOLT () 0x0") e a lista saía com 722 "Porca sextavada ¾" UNC" no
lugar dos parafusos ½". O tamanho gravado em `atributos.parafuso` (editor 3D e ligacoes3d) vale quando o nome não o tem.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest  # noqa: E402

from nucleo3d.modelo import Barra, Chapa, Documento  # noqa: E402
from nucleo3d import ligacoes3d as L3  # noqa: E402
from nucleo2d.detalhar import levantar  # noqa: E402
from nucleo2d.detalhe.base import _fixadores, nome_do_fixador  # noqa: E402
from saida import resumos  # noqa: E402


def _doc(nome_parafuso=None):
    """viga com uma chapa de 8 mm e dois parafusos ½" A325 atravessando a chapa"""
    d = Documento()
    d.add(Barra(nome="Viga", inicio=(0, 0, 0), fim=(1000, 0, 0), perfil="W 150×13,0", papel="viga", camada="Vigas",
                material="Aço", aco="ASTM A572", atributos={"tipo_ifc": "IfcBeam"}))
    d.add(Chapa(nome="Chapa", origem=(900, -60, 150), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0),
                contorno=[(0, 0), (100, 0), (100, 120), (0, 120)], espessura=8, centrada=False,
                furos=[{"x": 50, "y": 30, "diametro": 14.3}, {"x": 50, "y": 90, "diametro": 14.3}],
                camada="Chapas", material="Aço", aco="ASTM A36", atributos={"tipo_ifc": "IfcPlate"}))
    for y in (-30, 30):
        p = L3._parafuso((950, y, 150), (0, 0, 1), 12.7, 16.0, "ASTM A325")
        if nome_parafuso:
            p.nome = nome_parafuso
        d.add(p)
    return d


@pytest.mark.parametrize("nome", [None, "Parafuso", "Parafuso ½\" A325"])
def test_parafuso_renomeado_sai_como_parafuso_na_lista(nome):
    r = levantar(_doc(nome))
    assert dict(r["acessorios"]) == {"BOLT (A325) 12.7x35": 2}
    assert not any("orca" in k for k in r["acessorios"])


@pytest.mark.parametrize("nome", [None, "Parafuso"])
def test_parafuso_renomeado_sai_como_parafuso_no_resumo(nome):
    d = _doc(nome)
    r = resumos._parafusos_com_local(_fixadores(d), levantar(d)["pecas"], {}, {}, {}, {}, {})
    assert [(x["nome"], x["qtd"], bool(x.get("parafuso"))) for x in r] == [("Parafuso M12.7x35", 2, True)]


def test_furo_do_parafuso_renomeado_pelo_diametro_gravado():
    """o furo que o detalhe infere na viga vinha da tabela de porcas (8 mm → Ø9,5 em 251 furos da W410); é o ½" gravado"""
    from nucleo2d.detalhe.base import _diametro_do_fixador
    p = L3._parafuso((0, 0, 0), (0, 0, 1), 12.7, 16.0, "ASTM A325")
    p.nome = "Parafuso"
    assert _diametro_do_fixador(p, (35.0, 12.7, 11.0)) == (12.7, False)


def test_porca_solta_do_ifc_continua_porca():
    """o que não tem tamanho nem no nome nem nos atributos (a porca solta "BOLT () 0x0" do IFC) segue sem tamanho"""
    p = L3._parafuso((0, 0, 0), (0, 0, 1), 12.7, 16.0, "ASTM A325")
    p.nome = "BOLT () 0x0"
    p.atributos = {"tipo_ifc": "IfcMechanicalFastener"}
    assert nome_do_fixador(p) == "BOLT () 0x0"
