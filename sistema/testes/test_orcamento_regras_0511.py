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
    # a exceção do usuário (05/11): a CH 28 SOBE para 1 1/4" ("para não termos problema")
    assert orc.chapa_do_orcamento(28.0) == (31.8, 'CH 31,8 - 1 1/4"')
    # a CH 27 também sobe (o usuário ampliou a exceção, 05/11, via gestor); a 26 e a 25 seguem a mais próxima
    assert orc.chapa_do_orcamento(27.0) == (31.8, 'CH 31,8 - 1 1/4"')
    assert orc.chapa_do_orcamento(26.0)[0] == 25.4 and orc.chapa_do_orcamento(25.0)[0] == 25.4
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


def test_chumbador_de_barra_redonda_uma_linha_por_diametro_em_metro():
    # a barra é comprada por metro (o usuário, 05/11 tarde): UMA linha por diâmetro, com as peças no detalhe
    lista = {"posicoes": [], "acessorios": [{"nome": "CHUMBADOR 12x230", "quantidade": 60},
                                            {"nome": "CHUMBADOR 12x400", "quantidade": 10},
                                            {"nome": "CHUMBADOR 36x1507", "quantidade": 8},
                                            {"nome": "CHUMBADOR 12.7x300", "quantidade": 4},
                                            {"nome": "CHUMBADOR QUÍMICO HIT-V 12.7x190", "quantidade": 4},
                                            {"nome": "Chumbador Hardbolt 12x150", "quantidade": 4},
                                            {"nome": "CHUMBADOR 23x24", "quantidade": 24}]}
    linhas = orc.montar(lista, None)["linhas"]
    L = {li["id"]: li for li in linhas}
    c = L['chumb:Ø12 - 1/2"']
    assert c["descricao"] == 'Chumbador Ø12 - 1/2"' and c["un"] == "m" and c["qtd"] == 17.8      # 13,8 + 4,0 m
    assert 'Ø12 - 1/2" x 230 x 60 pç = 13,8 m' in c["detalhe"] and 'Ø12 - 1/2" x 400 x 10 pç = 4 m' in c["detalhe"]
    assert "~17,7 kg" in c["detalhe"]       # 10/11: pela barra comprada, π·12,7²/4 × 7,85 × 17,8 m (era 15,8 pelo Ø12)
    c = L['chumb:Ø36 - 1 1/2"']
    assert c["descricao"] == 'Chumbador Ø36 - 1 1/2"' and c["qtd"] == 12.06
    # o 12,7 vai em mm inteiro, o maior (13), na mesma polegada mas em outra linha (outro diâmetro de barra)
    assert L['chumb:Ø13 - 1/2"']["qtd"] == 1.2
    assert sum(1 for li in linhas if li["id"].startswith("chumb:Ø")) == 3
    # o químico e o mecânico não são barra comprada: seguem por peça
    assert L["chumb:CHUMBADOR QUÍMICO HIT-V 12.7x190"]["un"] == "pç"
    assert L["chumb:Chumbador Hardbolt 12x150"]["un"] == "pç"
    # o nome estragado da importação (heliponto: 24 mm de comprimento) não vira metro de barra
    assert L["chumb:CHUMBADOR 23x24"]["un"] == "pç"


def test_dobrado_no_comprimento_real_e_w_em_barras():
    # o usuário, 04/11: o dobrado (U/Ue, L dobrada, cartola) entra na compra no comprimento real, sem sobra; o W segue
    # pelas barras de 12 m do plano de corte com emenda, e o L laminado pelas barras de 6 m
    pos = [{"marca": "U1", "classe": "Barra", "perfil": "U150X50X2.25", "quantidade": 7, "comprimento": 4300, "peso_total": 151.3},
           {"marca": "C1", "classe": "Barra", "perfil": "CARTOLA 50X25X2", "quantidade": 3, "comprimento": 2000, "peso_total": 12.0},
           {"marca": "V1", "classe": "Barra", "perfil": "W200X26.6", "quantidade": 2, "comprimento": 7000, "peso_total": 372.4},
           {"marca": "L1", "classe": "Barra", "perfil": "L 2\"×1/4\"", "quantidade": 4, "comprimento": 2500, "peso_total": 47.6}]
    barras6 = {"comprimento": 6000, "quantidade": 7}                         # o plano em barras de 6 m: 7 barras
    perfis = [{"perfil": "U150X50X2.25", "posicoes": ["U1"], "comprimento_m": 30.1, "kg_m": 5.03, "kg_m_catalogo": 5.03,
               "barras": barras6, "barras_sem_emenda": barras6},
              {"perfil": "CARTOLA 50X25X2", "posicoes": ["C1"], "comprimento_m": 6.0, "kg_m": 2.0,
               "barras_sem_emenda": {"comprimento": 6000, "quantidade": 2}},
              {"perfil": "W200X26.6", "posicoes": ["V1"], "comprimento_m": 14.0, "kg_m": 26.6,
               "barras_com_emenda": {"comprimento": 12000, "quantidade": 2, "emendadas": []}},
              {"perfil": "L 2\"×1/4\"", "posicoes": ["L1"], "comprimento_m": 10.0, "kg_m": 4.76,
               "barras_sem_emenda": {"comprimento": 6000, "quantidade": 2}}]
    L = {li["id"]: li for li in orc.montar({"posicoes": pos, "perfis": perfis}, None)["linhas"]}
    u = L["u_fino"]
    assert u["qtd_recorte"] == round(5.03 * 30.1, 1) and "comprimento real" in u["recorte_como"]   # não 7 × 6 m
    assert L["cartola"]["qtd_recorte"] == 12.0 and "comprimento real" in L["cartola"]["recorte_como"]
    assert L["w"]["qtd_recorte"] == round(26.6 * 24.0, 1) and "barras" in L["w"]["recorte_como"]  # 2 barras de 12 m
    assert L["redondo_L"]["qtd_recorte"] == round(4.76 * 12.0, 1)                                  # 2 barras de 6 m


def test_calha_e_rufo_em_chapa_de_bobina_em_kg():
    # o usuário, 05/11: a chapa do projeto, só a largura muda para a da bobina de compra (1,20 m); acima de 1.200 mm de
    # desenvolvimento, 2 larguras; sem espessura no projeto, calha 0,65 e rufo 0,50
    pos = [{"marca": "CL1", "classe": "Barra", "categoria": "RUFOS", "perfil": "CALHA 1", "material": "aluzinc", "quantidade": 2,
            "comprimento": 600, "largura": 10000, "espessura": 0.65, "peso_total": 61.2},
           {"marca": "CL2", "classe": "Barra", "categoria": "RUFOS", "perfil": "CALHA 2", "material": "aluzinc", "quantidade": 1,
            "comprimento": 1500, "largura": 5000, "espessura": 0.65, "peso_total": 38.3},
           {"marca": "RF1", "classe": "Barra", "categoria": "RUFOS", "perfil": "RUFO 1", "material": "galvalume", "quantidade": 4,
            "comprimento": 300, "largura": 6000, "espessura": 0, "peso_total": 28.3},
           {"marca": "RF2", "classe": "Barra", "categoria": "RUFOS", "perfil": "RUFO 2", "material": "galvalume", "quantidade": 1,
            "comprimento": 0, "largura": 0, "espessura": 0, "peso_total": 5.0}]
    R = orc.montar({"posicoes": pos}, None)
    L = {li["id"]: li for li in R["linhas"]}
    kg_calha = 20.0 * 1 * 1.2 * 0.65 * 7.85 + 5.0 * 2 * 1.2 * 0.65 * 7.85       # 122,5 + 61,2
    assert L["calha"]["qtd"] == round(kg_calha, 1) and L["calha"]["un"] == "kg" and L["calha"]["kg_modelo"] == 99.5
    assert "Aluzinc #0,65 – 30,00 m" in L["calha"]["detalhe"]                    # 20 m × 1 + 5 m × 2 larguras
    kg_rufo = 24.0 * 1.2 * 0.50 * 7.85 + 5.0                                    # padrão 0,50; o RF2 sem comprimento: o kg da lista
    assert L["rufo"]["qtd"] == round(kg_rufo, 1)
    assert "padrão da empresa" in L["rufo"]["detalhe"] and "sem comprimento de peça" in L["rufo"]["detalhe"]
    assert L["mo_calha"]["qtd"] == 99.5 and L["mo_calha"]["preco"] is None      # a mão de obra pelo kg da peça
    assert R["totais"]["funilaria_kg_bobina"] == round(kg_calha, 1) + round(kg_rufo, 1)
    assert orc.larguras_de_bobina(1200) == 1 and orc.larguras_de_bobina(1201) == 2 and orc.larguras_de_bobina(0) == 1


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


def test_barra_do_chumbador_na_polegada_igual_ou_maior():
    # 10/11 (usuário, Hora Certa, auditor final V04: "vamos padronizar para a maior"; no "é assim?": "maior de verdade, Ø33
    # em 1 3/8""): a mais próxima dava Ø33 → 1 1/4" (31,75 < 33, com porca 1 3/8") e Ø20 → 3/4" (19,05 < 20)
    casos = {36: '1 1/2"', 33: '1 3/8"', 27: '1 1/8"', 20: '7/8"', 16: '5/8"', 12: '1/2"', 25: '1"', 25.4: '1"'}
    for d, pol in casos.items():
        assert orc.pol_da_barra(d) == pol, (d, orc.pol_da_barra(d))
        assert orc.barra_de_compra(d)[0] >= d * 0.99
    # o kg da linha pela barra comprada: Ø33 × 10 m → 1 3/8" (34,93) = 75,2 kg (pelo Ø33 seriam 67,1)
    lista = {"posicoes": [], "acessorios": [{"nome": "CHUMBADOR 33x1000", "quantidade": 10}]}
    L = {li["id"]: li for li in orc.montar(lista, None)["linhas"]}
    c = L['chumb:Ø33 - 1 3/8"']
    assert c["descricao"] == 'Chumbador Ø33 - 1 3/8"' and c["qtd"] == 10
    assert "~75,2 kg" in c["detalhe"], c["detalhe"]
