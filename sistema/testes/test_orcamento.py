# -*- coding: utf-8 -*-
"""Resumo de orçamento (saida/orcamento.py): leitura da planilha de preços, classificação das peças,
linhas e totais, edições do dono e os arquivos. A planilha é montada aqui (a tabela de preços da
empresa não vai para o repositório)."""
import os
import sys
import tempfile
import zipfile
from datetime import date
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import orcamento as O       # noqa: E402

LINHAS_TABELA = [
    ["TABELA DE PREÇOS"],
    ["EMPRESA  TESTE      VERSÃO  V1"],
    ["CHAVE\n(gerador)", "CATEGORIA", "ITEM / ESPECIFICAÇÃO", "FORNECEDOR", "UN", "PREÇO (R$)", "DATA DA\nCOTAÇÃO", "VALIDADE", "SITUAÇÃO", "FONTE"],
    ["PERFIS"],
    ["l_dobrado", "PERFIS", "CANTONEIRA L DOBRADA", "PERFYAÇO", "kg", 6.6, "08/09/2026", "", "ok", "x"],
    ["u_225", "PERFIS", "PERFIL MVAL - 2,00mm e 2,25mm - 4,80m à 6,40m", "MVAL", "kg", 5.75, "08/09/2026", "", "ok", "x"],
    ["u_terca", "PERFIS", "PERFIL MVAL - 2,25mm - menor 4,80m / maior 6,40m (terças)", "MVAL", "kg", 6, "08/09/2026", "", "ok", "x"],
    ["u_esp", "PERFIS", "PERFIL MVAL - 2,65/3,00 e 4,75mm - 4,80m à 6,40m", "MVAL", "kg", 5.6, "08/09/2026", "", "ok", "x"],
    ["", "PERFIS", "PERFIL MVAL - 2,65/3,00 e 4,75mm - Menor 4,80m/Maior 6,40m", "MVAL", "kg", 5.85, "24/07/2026", "", "ok", "x"],
    ["u_fora", "PERFIS", "PERFIL PERFYAÇO - FORA PADRÃO ATÉ 6,00m", "PERFYAÇO", "kg", 6.6, "08/09/2026", "", "ok", "x"],
    ["w", "PERFIS", "PERFIL W (laminado)", "ARCELOR", "kg", 7.45, "08/09/2026", "", "ok", "x"],
    ["CHAPAS"],
    ["chapa", "CHAPAS", "CHAPA MVAL - 3,75 à 12,50mm", "MVAL", "kg", 5.35, "08/09/2026", "", "ok", "x"],
    ["", "CHAPAS", "CHAPA MVAL - 3,00 à 3,35mm", "MVAL", "kg", 5.5, "24/07/2026", "", "ok", "x"],
    ["redondo_L", "BARRAS E CANTONEIRAS", "CANT. L22x22 à L63x63 / BAR. RED. 3/4\" à 1\"", "ARCELOR", "kg", 6.4, "08/09/2026", "", "ok", "x"],
    ["telha", "TELHAS E ACABAMENTOS", "TELHA TP40 #0,50mm PRÉ-PINTADA", "ARCELOR", "ml", 66.15, "08/09/2026", "", "ok", "x"],
    ["cumeeira", "TELHAS E ACABAMENTOS", "CUMEEIRA TP40 #0,50mm", "ARCELOR", "pç", 60, "08/09/2026", "", "ok", "x"],
    ["oa", "FIXAÇÕES DE TELHA", "FIXAÇÃO 2.3/8\" - HARD - TP40 - BRANCO", "HARD", "pç", 1.4, "24/07/2026", "", "VER ?", "x"],
    ["PARAFUSOS"],
    ["", "PARAFUSOS", "PARAFUSO 1/2\"x1.1/4\" - COMPLETO ZB - A307", "", "pç", 1.54, "08/09/2026", "", "ok", "x"],
    ["", "PARAFUSOS", "PARAFUSO 1/2\"x1.1/2\" - COMPLETO ZB - A307", "", "pç", 1.63, "08/09/2026", "", "ok", "x"],
    ["", "PARAFUSOS", "PARAFUSO 1/2\"x1.1/2\" - COMPLETO-A307 G.FOGO", "", "pç", 1.9, "08/09/2026", "", "ok", "x"],
    ["", "PARAFUSOS", "PARAFUSO 3/4\"x2\" - COMPLETO A325 ZB", "", "pç", 5.45, "08/09/2026", "", "ok", "x"],
    ["", "PARAFUSOS", "PORCA 3/8 - A307 - ZB", "", "pç", 0.15, "08/09/2026", "", "ok", "x"],
    ["", "PARAFUSOS", "ARRUELA 3/8 - A307 - ZB", "", "pç", 0.15, "08/09/2026", "", "ok", "x"],
]


def _xlsx(caminho, linhas):
    """Planilha mínima com células de texto embutido (o leitor também aceita sharedStrings)."""
    def cel(ref, v):
        if isinstance(v, (int, float)):
            return '<c r="%s"><v>%s</v></c>' % (ref, v)
        return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, escape(str(v)))
    rows = []
    for i, li in enumerate(linhas, 1):
        rows.append('<row r="%d">%s</row>' % (i, "".join(cel("%s%d" % ("ABCDEFGHIJ"[j], i), v) for j, v in enumerate(li) if v != "")))
    folha = ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData>%s</sheetData></worksheet>' % "".join(rows))
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   '<sheet name="Tabela de preços" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", folha)


def _tabela(tmp):
    cam = os.path.join(tmp, "Tabela de precos TESTE V1.xlsx")
    _xlsx(cam, LINHAS_TABELA)
    return O.ler_tabela(cam)


def _pos(marca, classe, perfil, qtd, comp, kg_total, categoria="BARRAS", esp=0, material="ASTM A36"):
    return {"marca": marca, "classe": classe, "perfil": perfil, "quantidade": qtd, "comprimento": comp, "peso_total": kg_total,
            "categoria": categoria, "espessura": esp, "material": material}


LISTA = {"posicoes": [
    _pos("CH1", "Chapa", "PLATE 6.3", 10, 200, 20.0, "CHAPAS", esp=6.3),
    _pos("CH2", "Chapa", "PLATE 3", 10, 100, 5.0, "CHAPAS", esp=3.0),
    _pos("CH3", "Chapa", "PLATE 12.7", 2, 300, 18.0, "CHAPAS", esp=12.7),     # 1/2": a faixa "até 12,50"
    _pos("P1", "Barra", "U92X30X#13", 20, 3000, 100.0),                       # bitola #13 = 2,25: U padrão
    _pos("T1", "Barra", "U150X50X2.25", 8, 7350, 300.0, "TERÇAS"),            # terça de 7,35 m: preço "maior 6,40"
    _pos("T2", "Barra", "U150X50X2.25", 4, 6000, 120.0, "TERÇAS"),            # terça de 6 m: preço normal
    _pos("P2", "Barra", "U100X50X3.04", 6, 2000, 60.0),
    _pos("P3", "Barra", "U200X50X3.75", 4, 5000, 80.0),                       # 3,75: fora padrão
    _pos("V1", "Barra", "W150X13.00", 2, 6000, 156.0),
    _pos("A1", "Barra", "L50X50X2.25", 1, 13000, 22.0),                       # dobrada acima de 12 m
    _pos("R1", "Barra redonda", "FE RED 3/8''", 10, 1500, 8.0, "TIRANTES"),
    _pos("L1", "Barra", "L 1\"×1/8\"", 4, 800, 4.0),
    _pos("X1", "Barra", "PERFIL ESTRANHO", 1, 1000, 3.0),
    _pos("TL1", "Telha", "TELHA TP40 0.50MM", 10, 5000, 200.0, "TELHAS"),
    _pos("TL2", "Telha (complemento da multi-dobra)", "TELHA TP40 0.50MM", 2, 1000, 8.0, "TELHAS"),
    _pos("CU1", "Cumeeira", "CUMEEIRA", 6, 980, 12.0, "TELHAS"),
], "acessorios": [{"nome": "BOLT (A) 12x35", "quantidade": 10}, {"nome": "BOLT (A) 12x30", "quantidade": 10},
                  {"nome": "Porca sextavada Ø3/8\" UNC", "quantidade": 4}, {"nome": "Arruela lisa Ø3/8\"", "quantidade": 8},
                  {"nome": "BOLT (A325) 20x50", "quantidade": 3}, {"nome": "CHUMBADOR 25x600", "quantidade": 4}]}


def test_le_a_planilha_e_acha_os_precos():
    with tempfile.TemporaryDirectory() as tmp:
        T = _tabela(tmp)
    assert len(T["itens"]) == 19                                   # os títulos de grupo ficam de fora
    p = O.Precos(T)
    assert p.chave("u_225")["preco"] == 5.75 and p.chave("w")["fornecedor"] == "ARCELOR"
    assert p.chapa(6.3)["preco"] == 5.35 and p.chapa(3.0)["preco"] == 5.5 and p.chapa(12.7)["preco"] == 5.35
    assert p.chapa(25.0) is None
    # o menor comprimento que não fica curto, zincado (o galvanizado a fogo só quando pedido)
    assert p.parafuso(0.5, 30, "A307")["preco"] == 1.54            # 1.1/4" = 31,75 mm
    assert p.parafuso(0.5, 35, "A307")["preco"] == 1.63            # 1.1/2" = 38,1 mm
    assert p.parafuso(0.5, 35, "A307", galv_fogo=True)["preco"] == 1.9
    assert p.parafuso(0.75, 50, "A307") is None and p.parafuso(0.75, 50, "A325")["preco"] == 5.45
    assert p.porca(3 / 8)["preco"] == 0.15 and p.arruela(3 / 8)["preco"] == 0.15
    assert O._pol('1.1/2') == 1.5 and O.mm_para_pol(12) == 0.5 and O.mm_para_pol(20) == 0.75


def test_classifica_as_pecas_pela_regra_da_fabrica():
    c = {li["marca"]: O.classificar(li) for li in LISTA["posicoes"]}
    assert c["P1"] == "u_fino" and c["T1"] == "u_fino_fora" and c["T2"] == "u_fino"
    assert c["P2"] == "u_grosso" and c["P3"] == "u_fora" and c["V1"] == "w" and c["A1"] == "l_dobrado"
    assert c["R1"] == "redondo_L" and c["L1"] == "redondo_L" and c["X1"] == "outro"
    assert c["TL1"] == "telha" and c["TL2"] == "telha" and c["CU1"] == "cumeeira" and c["CH1"] == "chapa"
    # peça qualquer acima de 6,40 m também não sai da barra padrão
    assert O.classificar(_pos("B", "Barra", "U100X50X3.00", 1, 7000, 1)) == "u_grosso_fora"


def test_monta_o_resumo_com_totais_edicoes_e_avisos():
    with tempfile.TemporaryDirectory() as tmp:
        T = _tabela(tmp)
    R = O.montar(LISTA, T, projeto={"nome": "Obra teste"}, hoje=date(2026, 10, 3))
    L = {li["id"]: li for li in R["linhas"]}
    assert R["totais"]["aco_kg"] == 896.0                          # sem telhas e cumeeira
    assert L["u_fino"]["qtd"] == 220.0 and L["u_fino"]["preco"] == 5.75 and L["u_fino"]["total"] == 1265.0
    assert L["u_fino_fora"]["qtd"] == 300.0 and L["u_fino_fora"]["preco"] == 6
    assert L["u_fora"]["preco"] == 6.6 and L["outro"]["preco"] is None
    assert L["corte_chaparia"]["qtd"] == 43.0 and L["corte_chaparia"]["origem"] == "dono"
    assert L["telha:TELHA TP40 0.50MM"]["qtd"] == 52.0 and L["telha:TELHA TP40 0.50MM"]["descricao"] == "Telha TP40 0.50MM"
    assert L["cumeeira"]["qtd"] == 6 and L["cumeeira"]["preco"] == 60
    par = L['paraf:A307:1/2"']
    assert par["qtd"] == 20 and abs(par["preco"] - (1.54 + 1.63) / 2) < 1e-6
    assert L['paraf:A325:3/4"']["preco"] == 5.45
    assert L['porca:3/8"']["total"] == 0.6 and L['arruela:3/8"']["qtd"] == 8
    assert L["fabricacao"]["qtd"] == 896.0 and L["fabricacao"]["preco"] is None
    soma = round(sum(li["total"] or 0 for li in R["linhas"]), 2)
    assert R["totais"]["tabela"] == soma
    textos = " | ".join(a["texto"] for a in R["avisos"])
    assert "Sem preço na tabela: Estrutura — outros perfis" in textos and "acima de 12 m" in textos
    assert "Chumbador 25x600" in textos and "Cotação de 24/07/2026" in textos
    assert "VER ?" not in textos                                   # a fixação "VER ?" ainda não tem quantidade
    assert "Sem preço na tabela: Corte chaparia" not in textos

    # as edições do dono: quantidade e preço trocados, fechamento, linha acrescentada, linha tirada
    ed = {"cabecalho": {"local": "Cascavel – PR", "area_m2": "100"},
          "linhas": {"w": {"preco": 7.9}, "fabricacao": {"preco_fech": 3.5}, "frete": {"qtd": 2, "total_fech": 6400},
                     "u_fora": {"oculta": True}},
          "extras": [{"descricao": "Guindaste", "un": "dia", "qtd": 2, "preco": 1800, "preco_fech": 1700}], "notas": "100% parafusada"}
    R2 = O.montar(LISTA, T, ed, projeto={"nome": "Obra teste"}, hoje=date(2026, 10, 3))
    L2 = {li["id"]: li for li in R2["linhas"]}
    assert L2["w"]["preco"] == 7.9 and L2["w"]["preco_auto"] == 7.45 and L2["w"]["total"] == round(156 * 7.9, 2)
    assert L2["fabricacao"]["total_fech"] == 896 * 3.5 and L2["frete"]["total_fech"] == 6400
    assert L2["extra:0"]["total"] == 3600 and L2["extra:0"]["total_fech"] == 3400
    assert R2["totais"]["fechamento"] == round(896 * 3.5 + 6400 + 3400, 2)
    assert R2["totais"]["tabela"] == round(R["totais"]["tabela"] - L["u_fora"]["total"] - L["w"]["total"] + L2["w"]["total"] + 3600, 2)
    # com quantidade, a fixação "VER ?" passa a ser avisada
    R3 = O.montar(LISTA, T, {"linhas": {"fix_oa": {"qtd": 100}}}, hoje=date(2026, 10, 3))
    assert any("VER ?" in a["texto"] for a in R3["avisos"])
    assert R2["cabecalho"]["local"] == "Cascavel – PR" and R2["cabecalho"]["area_m2"] == 100.0
    assert R2["totais"]["rs_m2_fechamento"] == round(R2["totais"]["fechamento"] / 100, 2)


def test_avisa_obra_sem_parafusos_e_chapa_absurda():
    lista = {"posicoes": [_pos("P1", "Barra", "U150X50X2.25", 100, 6000, 2000.0),
                          _pos("CH9", "Chapa", "PLATE 650x200x146", 5, 650, 750.0, "CHAPAS", esp=146.5, material="")], "acessorios": []}
    R = O.montar(lista, None, hoje=date(2026, 10, 3))
    textos = [a["texto"] for a in R["avisos"]]
    assert any("Nenhuma tabela de preços" in t for t in textos)
    assert any("nenhum parafuso" in t for t in textos)
    assert any("146,5 mm" in t for t in textos) and any("sem material" in t for t in textos)
    assert R["avisos"][0]["nivel"] == "alto"


def test_grava_edicoes_documentos_e_troca_a_tabela():
    with tempfile.TemporaryDirectory() as tmp:
        T = _tabela(tmp)
        proj = os.path.join(tmp, "projeto")
        os.makedirs(proj)
        O.gravar_edicoes(proj, {"linhas": {"w": {"preco": 8, "lixo": 1}, "x": {}}, "extras": [{"descricao": ""}, {"descricao": "Andaime", "qtd": 1}],
                                "notas": "a"})
        ed = O.ler_edicoes(proj)
        assert ed["linhas"] == {"w": {"preco": 8}} and [x["descricao"] for x in ed["extras"]] == ["Andaime"]
        R = O.montar(LISTA, T, ed, projeto={"nome": "Obra <teste>"})
        arq = O.gravar_documentos(proj, R, imprimir_pdf=False)
        h = open(arq["html"], encoding="utf-8").read()
        assert "Obra &lt;teste&gt;" in h and "VALOR TOTAL" in h and "Andaime" in h and 'data-paged' in h
        csv_ = open(arq["csv"], encoding="utf-8-sig").read()
        assert "Estrutura W (laminado);156;kg;8;" in csv_
        # tabela nova: grava em <dados>/fabrica/precos e passa a ser a vigente; .xlsx que não se lê é recusado
        dados = os.path.join(tmp, "dados")
        assert O.tabela_vigente(dados) is None
        destino = O.guardar_tabela(dados, "Tabela V2.xlsx", open(os.path.join(tmp, "Tabela de precos TESTE V1.xlsx"), "rb").read())
        assert O.tabela_vigente(dados) == destino
        for nome, conteudo in (("lixo.xlsx", b"nada"), ("tabela.csv", b"a;b")):
            try:
                O.guardar_tabela(dados, nome, conteudo)
                assert False, "devia recusar"
            except Exception:
                pass
        assert sorted(os.listdir(os.path.join(dados, "fabrica", "precos"))) == ["Tabela V2.xlsx"]
