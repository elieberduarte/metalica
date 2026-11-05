# -*- coding: utf-8 -*-
"""As 4 regras do usuário para todo orçamento (05/11, pelo gestor): a chapa pela comercial MAIS PRÓXIMA em mm e polegada,
mesmo menor, com o kg pela comercial; o chumbador de barra redonda com o comprimento total da barra na linha; o disco em
branco (o gestor preenche); a tinta só pela área de pintura (m²)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import orcamento as orc                             # noqa: E402


def test_chapa_pela_comercial_mais_proxima_em_mm_e_polegada():
    # os exemplos do usuário: CH 15 → CH 15,88 - 5/8"; CH 20 → CH 19,1 - 3/4" (a mais próxima, mesmo menor)
    assert orc.chapa_do_orcamento(15.0) == (15.88, 'CH 15,88 - 5/8"')     # 5/8" = 15,88 no rótulo e no kg (05/11)
    assert orc.chapa_do_orcamento(16.0) == (15.88, 'CH 15,88 - 5/8"')
    # a exceção do usuário (05/11): a CH 28 SOBE para 1 1/4" ("para não termos problema"); só ela
    assert orc.chapa_do_orcamento(28.0) == (31.8, 'CH 31,8 - 1 1/4"')
    assert orc.chapa_do_orcamento(27.0)[0] == 25.4 and orc.chapa_do_orcamento(25.0)[0] == 25.4
    assert orc.chapa_do_orcamento(20.0) == (19.1, 'CH 19,1 - 3/4"')
    assert orc.chapa_do_orcamento(31.5) == (31.8, 'CH 31,8 - 1 1/4"')
    assert orc.chapa_do_orcamento(17.55)[0] == 19.1                    # empate: a maior ("na dúvida a MAIOR")
    assert orc.chapa_do_orcamento(6.3) == (6.35, 'CH 6,35 - 1/4"')     # 1/4" com o rótulo 6,35 (gestor, 05/11)
    assert orc.chapa_do_orcamento(3.0)[1].startswith("CH #11 - 3,00mm")  # a fina segue a bitola do resumo de compra
    lista = {"posicoes": [
        {"marca": "C1", "classe": "Chapa", "perfil": "CH 15", "espessura": 15.0, "quantidade": 2, "peso_total": 150.0},
        {"marca": "C2", "classe": "Chapa", "perfil": "CH 20", "espessura": 20.0, "quantidade": 1, "peso_total": 200.0},
        {"marca": "C3", "classe": "Chapa", "perfil": "CH 16", "espessura": 16.0, "quantidade": 1, "peso_total": 32.0}]}
    R = orc.montar(lista, None)
    ch = {li["descricao"]: li for li in R["linhas"] if li["id"].startswith("chapa:")}
    assert set(ch) == {'Estrutura # CH 15,88 - 5/8"', 'Estrutura # CH 19,1 - 3/4"'}
    c16, c19 = ch['Estrutura # CH 15,88 - 5/8"'], ch['Estrutura # CH 19,1 - 3/4"']
    assert c16["qtd"] == 190.6 and c16["kg_modelo"] == 182.0          # 150 × 15,88/15 + 32 × 15,88/16: o kg pela comercial
    assert "projeto 15,00 / 16,00 mm → comercial 15,88 mm" in c16["detalhe"]
    assert c19["qtd"] == 191.0                                                # 200 × 19,1/20: menor que o projeto
    assert R["totais"]["aco_kg"] == 381.6
    assert c19["qtd_recorte"] == round(191.0 * 1.15, 1)                        # a compra com a perda de recorte


def test_chumbador_de_barra_redonda_com_o_comprimento_total():
    lista = {"posicoes": [], "acessorios": [{"nome": "CHUMBADOR 12x230", "quantidade": 60},
                                            {"nome": "CHUMBADOR 36x1507", "quantidade": 8},
                                            {"nome": "CHUMBADOR QUÍMICO HIT-V 12.7x190", "quantidade": 4},
                                            {"nome": "Chumbador Hardbolt 12x150", "quantidade": 4},
                                            {"nome": "CHUMBADOR 23x24", "quantidade": 24}]}
    L = {li["id"]: li for li in orc.montar(lista, None)["linhas"]}
    c = L["chumb:CHUMBADOR 12x230"]
    assert c["descricao"] == 'Chumbador Ø12 - 1/2" x 230 x 60 pç' and c["qtd"] == 13.8 and c["un"] == "m"   # = 13,8 m
    c = L["chumb:CHUMBADOR 36x1507"]
    assert c["descricao"] == 'Chumbador Ø36 - 1 1/2" x 1507 x 8 pç' and c["qtd"] == 12.06
    # o químico e o mecânico não são barra comprada: seguem por peça
    assert L["chumb:CHUMBADOR QUÍMICO HIT-V 12.7x190"]["un"] == "pç"
    assert L["chumb:Chumbador Hardbolt 12x150"]["un"] == "pç"
    # o nome estragado da importação (heliponto: 24 mm de comprimento) não vira metro de barra
    assert L["chumb:CHUMBADOR 23x24"]["un"] == "pç"


def test_disco_em_branco_e_tinta_pela_area_de_pintura():
    lista = {"posicoes": [{"marca": "V1", "classe": "Barra", "perfil": "W200X26.6", "quantidade": 2, "comprimento": 6000,
                           "peso_total": 319.2}],
             "perfis": [{"perfil": "W200X26.6", "posicoes": ["V1"], "comprimento_m": 12.0, "peso": 319.2}],
             "chapas": [{"espessura": 9.5, "area_m2": 0.5, "peso": 37.3}]}
    L = {li["id"]: li for li in orc.montar(lista, None)["linhas"]}
    assert L["disco"]["qtd"] is None and L["disco"]["preco"] is None and "gestor" in L["disco"]["detalhe"]
    t = L["tinta"]
    assert t["un"] == "m²" and t["preco"] is None and "intumescente" in t["detalhe"]
    assert t["qtd"] > 1.0                                    # perfis (perímetro × comprimento) + 2 × 0,5 m² das chapas
    assert "chapas 1,0 m²" in t["detalhe"]
