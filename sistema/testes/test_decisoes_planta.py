# -*- coding: utf-8 -*-
"""As decisões da montagem pela planta gravadas no projeto (app._com_decisoes_planta / _decisoes_planta_novas): as listas
e as chaves das chapas do projeto (Posto CB, 23/10/2026: remontar pela tela perdia as placas de base, os suportes ST e
o SC1, que só os scripts de remontagem pediam)."""
import app


def test_as_chaves_das_chapas_ficam_gravadas_e_voltam():
    # a montagem do script pede as chapas: elas ficam gravadas junto das listas
    par = {"duas_pecas": ["TRANSICAO 2"], "bases_da_locacao": True, "suportes_do_projeto": True}
    novas = app._decisoes_planta_novas(par)
    assert novas == {"duas_pecas": ["TRANSICAO 2"], "bases_da_locacao": True, "suportes_do_projeto": True}
    # a tela manda só a planta e os níveis: as decisões gravadas voltam
    pela_tela = app._com_decisoes_planta({"planta": "PLANTA NO NÍVEL 6,00m"}, novas)
    assert pela_tela["bases_da_locacao"] is True and pela_tela["suportes_do_projeto"] is True
    assert pela_tela["duas_pecas"] == ["TRANSICAO 2"]
    # o pedido que diz outra coisa vence a gravada
    assert app._com_decisoes_planta({"suportes_do_projeto": False}, novas)["suportes_do_projeto"] is False
    # projeto sem a decisão: nada muda (o L 3" padrão, sem placas)
    assert "bases_da_locacao" not in app._com_decisoes_planta({}, {"deitadas": ["TRELICA 1"]})


def test_a_passarela_fica_gravada():
    """a passarela de manutenção (o quadro {planta, nivel}) também volta na montagem pela tela"""
    novas = app._decisoes_planta_novas({"passarela": {"planta": "PLANTA DA PASSARELA", "nivel": 7600}})
    assert novas == {"passarela": {"planta": "PLANTA DA PASSARELA", "nivel": 7600}}
    assert app._com_decisoes_planta({}, novas)["passarela"]["nivel"] == 7600
