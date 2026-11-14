# -*- coding: utf-8 -*-
"""D11 (agente usuario-desastrado, 13/11): o Salvar do Dimensionamento gravava vão 0 e comprimento negativo.

A tela marcava "2 campos a corrigir", mas o Salvar gravava `vao: 0, comprimento: -40` no projeto.json e dizia "Projeto
salvo"; o Modelo 3D recusava depois. O formulário continua sendo rascunho de trabalho — campo em branco ou ausente é
gravado como está —, mas o número fora da faixa de entrada do cálculo não é gravado: fica o valor de antes (ou nada, no
projeto novo) e a resposta diz quais campos ficaram de fora, com o rótulo, o valor digitado e a faixa aceita.
As faixas têm uma fonte só (nucleo/modelo_galpao.FAIXAS): o cálculo (validar), o Salvar (fora_da_faixa) e a tela (o
catálogo dos campos) recusam o mesmo valor.
"""
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from nucleo.base import ErroDeDados                                                   # noqa: E402
from nucleo.modelo_galpao import (DadosGalpao, FAIXAS, FAIXAS_DOS_CRITERIOS,          # noqa: E402
                                  faixas_de_entrada, fora_da_faixa)
from projetos import Projetos                                                         # noqa: E402

BOM = {"nome": "Galpão", "vao": 20, "comprimento": 40, "pe_direito": 6}


def _g(tmp_path):
    g = Projetos(str(tmp_path))
    return g, g.criar("Galpão", tipo="galpao", dados=dict(BOM))["slug"]


# ------------------------------------------------------------------ o Salvar
def test_o_caso_do_agente_vao_0_e_comprimento_negativo_nao_sao_gravados(tmp_path):
    g, s = _g(tmp_path)
    r = g.salvar_dados(s, {"nome": "Galpão", "vao": 0, "comprimento": -40, "pe_direito": 6.5})
    gravado = g.ler(s)["dados"]
    assert gravado["vao"] == 20 and gravado["comprimento"] == 40        # ficou o de antes
    assert gravado["pe_direito"] == 6.5                                  # o válido foi gravado
    fora = {f["campo"]: f for f in r["nao_gravados"]}
    assert set(fora) == {"vao", "comprimento"}
    assert fora["vao"]["valor"] == 0 and fora["vao"]["motivo"] == "Vão: valor 0 fora da faixa aceitável (5 a 60 m)."
    assert fora["comprimento"]["motivo"] == "Comprimento: valor -40 fora da faixa aceitável (5 a 300 m)."
    assert r["vao"] == 20 and r["comprimento"] == 40                      # o cartão da lista não mostra 0 × −40


def test_tudo_valido_grava_como_sempre_e_sem_o_campo_a_mais(tmp_path):
    g, s = _g(tmp_path)
    r = g.salvar_dados(s, {"nome": "Galpão", "vao": 25, "comprimento": 60, "pe_direito": "6,5"})
    assert "nao_gravados" not in r
    assert g.ler(s)["dados"] == {"nome": "Galpão", "vao": 25, "comprimento": 60, "pe_direito": "6,5"}


def test_em_branco_ou_ausente_continua_sendo_rascunho(tmp_path):
    g, s = _g(tmp_path)
    r = g.salvar_dados(s, {"nome": "Galpão", "vao": "", "comprimento": None, "cliente": ""})
    assert "nao_gravados" not in r
    assert g.ler(s)["dados"] == {"nome": "Galpão", "vao": "", "comprimento": None, "cliente": ""}


def test_o_que_nao_e_numero_tambem_fica_de_fora(tmp_path):
    g, s = _g(tmp_path)
    r = g.salvar_dados(s, {"vao": "vinte", "comprimento": 40})
    assert [f["campo"] for f in r["nao_gravados"]] == ["vao"] and "não é um número" in r["nao_gravados"][0]["motivo"]
    assert g.ler(s)["dados"]["vao"] == 20


def test_sem_valor_anterior_o_campo_fica_em_branco_nao_o_invalido_nem_um_padrao(tmp_path):
    g = Projetos(str(tmp_path))
    r = g.criar("Novo", tipo="galpao", dados={"nome": "Novo", "vao": 0, "comprimento": -40, "pe_direito": 6})
    assert {f["campo"] for f in r["nao_gravados"]} == {"vao", "comprimento"}
    assert g.ler(r["slug"])["dados"] == {"nome": "Novo", "pe_direito": 6, "cliente": "", "local": "", "responsavel": ""}
    # e o Salvar seguinte, ainda errado: continua sem o campo
    r2 = g.salvar_dados(r["slug"], {"nome": "Novo", "vao": 3, "pe_direito": 6})
    assert [f["campo"] for f in r2["nao_gravados"]] == ["vao"] and "vao" not in g.ler(r["slug"])["dados"]


def test_o_valor_anterior_que_tambem_nao_vale_nao_volta(tmp_path):
    """Projeto gravado antes desta correção com vão 0: o Salvar com outro valor errado não devolve o 0."""
    import json
    g, s = _g(tmp_path)
    caminho = os.path.join(str(tmp_path), s, "projeto.json")
    with open(caminho, encoding="utf-8") as f:
        p = json.load(f)
    p["dados"]["vao"] = 0
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(p, f)
    g.salvar_dados(s, {"nome": "Galpão", "vao": 2, "comprimento": 40})
    assert "vao" not in g.ler(s)["dados"]


def test_a_rota_devolve_os_campos_que_ficaram_de_fora(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    s = app.criar_projeto({"nome": "Pela rota", "tipo": "galpao", "dados": dict(BOM)})["slug"]
    r = app.acao_de_projeto(s, "dados", {"dados": {"nome": "Pela rota", "vao": 0, "comprimento": 40}})
    assert [f["campo"] for f in r["nao_gravados"]] == ["vao"]
    assert app._gerente().ler(s)["dados"]["vao"] == 20


# ------------------------------------------------------------------ uma fonte só: a tela, o Salvar e o Modelo 3D
def _valido(campo):
    return getattr(DadosGalpao(), campo)


@pytest.mark.parametrize("campo, rotulo, minimo, maximo, unidade", FAIXAS + FAIXAS_DOS_CRITERIOS,
                         ids=[f[0] for f in FAIXAS + FAIXAS_DOS_CRITERIOS])
def test_a_tela_o_salvar_e_o_modelo_3d_recusam_o_mesmo_valor(campo, rotulo, minimo, maximo, unidade):
    import app
    catalogo = {i["campo"]: i for g in app._campos_formulario() for i in g["campos"]}
    assert catalogo[campo]["faixa"] == [minimo, maximo]                  # a tela marca o campo com esta faixa
    assert fora_da_faixa({campo: _valido(campo)}) == {}                   # o padrão do programa vale nos três
    DadosGalpao().validar()
    for ruim in (minimo - 1, maximo + 1):
        motivo = fora_da_faixa({campo: ruim})[campo]                      # o Salvar
        assert rotulo in motivo and "fora da faixa aceitável" in motivo
        with pytest.raises(ErroDeDados) as e:                             # o Modelo 3D (o cálculo)
            app._dados_de({campo: ruim})
        assert str(e.value) == motivo                                     # o mesmo texto, com o valor e a faixa
    for limite in (minimo, maximo):
        assert fora_da_faixa({campo: limite}) == {}                       # as pontas da faixa valem


def test_toda_faixa_do_calculo_esta_na_tabela():
    """O `validar` não tem faixa de número fora da tabela (as da tesoura, que dependem do tipo de pórtico, ficam nele)."""
    assert set(faixas_de_entrada()) == {f[0] for f in FAIXAS + FAIXAS_DOS_CRITERIOS}
    campos = {f.name for f in __import__("dataclasses").fields(DadosGalpao)}
    assert set(faixas_de_entrada()) <= campos


def test_a_tela_usa_a_faixa_que_vem_do_catalogo():
    """web/app.js tinha as faixas dele (inclinação até 100, flechas até 600): a do catálogo vale por cima."""
    with open(os.path.join(os.path.dirname(AQUI), "web", "app.js"), encoding="utf-8") as f:
        js = f.read()
    assert "CONFIG[item.campo].faixa = item.faixa" in js
    assert "nao_gravados" in js
