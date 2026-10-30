# -*- coding: utf-8 -*-
"""O contravento em barra redonda maior que 6 m vem sob medida (decisão do usuário, 30/10 — Hora Certa · Galpão
Existente, auditor N08: 24 contraventos de 7,2 a 10 m saíam "(emenda) 6.000 + (resto da emenda)" no plano de corte e
inteiros na prancha, sem emenda detalhada). O redondo até 6 m continua cortado da barra de 6 m."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from nucleo3d import geometria as geo  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402
from nucleo2d.detalhar import levantar  # noqa: E402
from saida import lista_producao as lp  # noqa: E402


def _lista(comprimentos):
    perfil = "BARRA REDONDA 16"
    geo.registrar_perfil(geo.barra_redonda(16.0, perfil))
    doc = Documento(nome="cv")
    for k, L in enumerate(comprimentos):
        doc.add(Barra(nome="CV", inicio=(0.0, k * 500.0, 3000.0), fim=(L, k * 500.0, 3000.0), perfil=perfil,
                      papel="contravento", material="Aço", aco="ASTM A36",
                      atributos={"tipo_ifc": "IfcMember", "funcao": "contravento"}))
    lev = levantar(doc, regra_tercas=False)
    lista = lp.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"], projeto={"nome": "t"})
    return next(g for g in lista["perfis"] if "16" in g["perfil"])


def test_contravento_de_10m_vem_sob_medida_sem_emenda():
    g = _lista([10000.0, 10000.0, 7200.0])
    assert g["sob_medida"] == "maiores"
    assert g["barras"]["emendas"] == 0, g["barras"]
    assert g["barras"]["sob_medida_pecas"] == 3


def test_contravento_curto_sai_da_barra_de_6m():
    g = _lista([2500.0, 2500.0])
    assert g["barras"]["quantidade"] == 1 and g["barras"].get("sob_medida_pecas", 0) == 0
