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
    assert lp._barra_para([6300.0], 0, "U150X60X20X2.25") == 6000.0       # a peça maior vem sob medida (13/10)
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


def test_compra_com_e_sem_aproveitamento_lado_a_lado():
    """A compra de perfis em dois blocos (o usuário, 09/10): com aproveitamento (o plano de corte) e sem (cada posição só
    das barras dela; a peça maior que a barra em barras inteiras), barras × kg/barra = kg nos dois."""
    from saida import resumos as rz
    pos = [{"marca": "A", "comprimento": 2500, "quantidade": 3},      # 2 por barra de 6 m → 2 barras
           {"marca": "B", "comprimento": 1000, "quantidade": 2},      # 5 por barra → 1 barra
           {"marca": "C", "comprimento": 6848, "quantidade": 2}]      # maior que a barra: 2 barras cada → 4
    assert rz._barras_sem_aproveitamento(pos, 6000.0) == 7
    lista = {"posicoes": pos, "perfis": [{"perfil": "TQ 250x250x6,3", "posicoes": ["A", "B", "C"], "peso": 1000.0, "kg_m": 47.41,
                                          "kg_m_catalogo": 47.41, "comprimento_m": 23.2, "pecas": 7,
                                          "barras": {"comprimento": 6000, "quantidade": 5, "aproveitamento": 77.3, "emendas": 2}}]}
    C = rz._compra(lista, [], {}, {})
    p = C["perfis"][0]
    assert p["barras_sem_aproveitamento"] == 7 and abs(p["kg_sem_aproveitamento"] - 7 * 6 * 47.41) < 0.01
    html = rz._html_compra({"compra": C})
    assert "Com aproveitamento" in html and "Sem aproveitamento" in html and 'class="r ap-sem"' in html
    assert "emenda" not in html.split("<tbody>")[1].split("</tbody>")[0]   # só o total de barras (09/10)
    assert html.index("Sem aproveitamento") < html.index("Com aproveitamento") and "Projeto" in html


def test_chumbador_quimico_e_parafuso_na_bitola_e_classe_do_modelo():
    """O chumbador químico (barra roscada HIT-V no concreto, 09/10) sai com o nome dele, e o parafuso Ø1/2" (12,7) e o
    Ø3/4" (19,05) na polegada certa — o round dava 13 e 19, fora da tabela ("M12.7"); a classe do modelo vale."""
    from saida import resumos as rz
    nome, desc = rz.descricao_chumbador(15.875, "250")
    assert nome == 'Chumbador químico HIT-V Ø5/8" x 250' and "HIT-RE 500" in desc
    assert rz._eh_chumbador("CHUMBADOR QUÍMICO HIT-V 12.7x190") and not rz._eh_chumbador("BOLT (A325) 12.7x80")
    assert rz._bitola_pol(12.7) == '1/2"' and rz._bitola_pol(19.05) == '3/4"' and rz._bitola_pol(16) == '5/8"'
    assert "ASTM A325" in rz.descricao_parafuso("M12.7x80", "A325")[1] and 'Ø1/2"' in rz.descricao_parafuso("M12.7x80")[1]


def test_quimico_em_cartuchos_e_a_arruela_que_e_chapa():
    """O químico dos chumbadores (09/10): o anel furo × barra no embutimento, +30%, em cartuchos de 500 ml; a arruela que
    já é chapa do projeto (a CH2 do chumbador da CH1) não se compra solta; o orçamento ganha a linha dos cartuchos."""
    from saida import resumos as rz
    assert abs(rz.volume_quimico_ml(12.7, 150) - 5.05) < 0.05 and abs(rz.volume_quimico_ml(15.875, 150) - 13.07) < 0.05
    assert rz.cartuchos_quimico(1000.0) == {"ml_total": 1300.0, "cartuchos": 3, "cartucho_ml": 500}
    parafusos = [{"nome": "Chumbador", "descricao": "x", "qtd": 10, "parafuso": True, "d": 12.7, "sem_arruela": 10,
                  "embutimento": 150.0, "quimico": "HIT-RE 500"},
                 {"nome": "Parafuso", "descricao": "y", "qtd": 4, "parafuso": True, "d": 12.7}]
    C = rz._compra({"perfis": [], "posicoes": []}, parafusos, {}, {})
    assert dict(C["porcas"])['1/2"'] == 14 and dict(C["arruelas"])['1/2"'] == 4
    (q,) = C["quimicos"]
    assert q["furos"] == 10 and q["cartuchos"] == 1
    R = orc.montar({"posicoes": [], "acessorios": [{"nome": "CHUMBADOR QUÍMICO HIT-V 15.875x250", "quantidade": 100}]}, None)
    li = next(x for x in R["linhas"] if x["id"] == "quimico")
    assert li["qtd"] == rz.cartuchos_quimico(100 * rz.volume_quimico_ml(15.875))["cartuchos"] == 4


def test_dobrado_em_6m_terca_e_peca_longa_sob_medida():
    """O relatório de compras da SOORO (13/10): a terça vem da dobradeira no comprimento de cada peça; o outro dobrado em
    barra de 6 m, e a peça dele maior que 6 m sob medida. Em 12 m, o U100x50#11 dos banzos de 7,25 m dava 761 kg (14
    barras) para 670 kg pedidos."""
    from saida import resumos as rz
    assert lp._regra_sob_medida("U150X50X2.28", 0, terca=True) == "todas"
    assert lp._regra_sob_medida("U100X50X3.04", 0) == "maiores"
    assert lp._regra_sob_medida("W250X32.70", 0) == "" and lp._regra_sob_medida("TQ 50x50x3,0", 0) == ""
    assert lp._regra_sob_medida("L3''X3/16''", 0) == "" and lp._regra_sob_medida("U100X50X3.04", 12000.0) == ""
    # banzo: 14 × 7.253 sob medida, o resto em barras de 6 m
    g = {"perfil": "U100X50X3.04", "sob_medida": "maiores"}
    comps = [7253.0] * 14 + [2000.0] * 6
    lp._os_dois_encaixes(g, comps, 6000.0, ["B.21"] * 14 + ["B.6"] * 6, set())
    b = g["barras"]
    assert b["comprimento"] == 6000.0 and b["quantidade"] == 3
    assert b["sob_medida_pecas"] == 14 and abs(b["sob_medida_m"] - 14 * 7.253) < 0.01
    assert [pl for pl in b["plano"] if pl.get("sob_medida")] == [
        {"barras": 14, "sobra": 0, "sob_medida": True, "comprimento": 7253.0, "cortes": [{"nome": "B.21", "comprimento": 7253.0, "qtd": 1}]}]
    # terça: tudo sob medida, nenhuma barra
    t = {"perfil": "U150X50X2.28", "sob_medida": "todas"}
    lp._os_dois_encaixes(t, [6290.0, 5105.0, 3990.0], 6000.0, ["T.C.2", "T.C.4", "T.C.3"], set())
    assert t["barras"]["quantidade"] == 0 and t["barras"]["sob_medida_pecas"] == 3 and t["barras"]["aproveitamento"] == 100.0
    # a compra: barras × kg/barra + metros sob medida × kg/m, com e sem aproveitamento
    pos = [{"marca": "B21", "comprimento": 7253, "quantidade": 14}, {"marca": "B6", "comprimento": 2000, "quantidade": 6}]
    lista = {"posicoes": pos, "perfis": [dict(g, posicoes=["B21", "B6"], peso=600.0, kg_m=4.53, kg_m_catalogo=4.53,
                                              comprimento_m=113.54, pecas=20)]}
    p = rz._compra(lista, [], {}, {})["perfis"][0]
    assert p["barras"] == 3 and p["barras_sem_aproveitamento"] == 3     # 2 por barra (3 mm de corte)
    assert abs(p["kg_compra"] - 4.53 * (3 * 6 + 14 * 7.253)) < 0.01
    assert abs(p["kg_sem_aproveitamento"] - 4.53 * (3 * 6 + 14 * 7.253)) < 0.01
    assert "+14 sob medida" in rz._html_compra({"compra": {"perfis": [p]}})
