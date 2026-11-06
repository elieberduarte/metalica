# -*- coding: utf-8 -*-
"""O memorial do quantitativo no desenho do Resumo da obra (saida/memorial_quantitativo.py, 05/11/2026): o texto guarda as
âncoras que a conferência do auditor lê de volta no PDF (conferir_resumo_hermes.py da Hora Certa), o preço liga e desliga, a
origem repetida vira nota e as travas de soma continuam. O piloto com o ADM inteiro (153 OK nos dois memoriais) é o
Projeto/ESTUDOS/Resumo-unificado/piloto_adm.py."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import memorial_quantitativo as MQ  # noqa: E402


def _D():
    W = [{"perfil": "W 530×66,0", "n": 222, "m": 1043.2, "kgm": 66.0, "kg": 68848.0,
          "origem": "3D: o rótulo de cada vão nas plantas 900/901 (DWG); pilares pela tabela de variação; tabela resumo 900/901: 1.152,0 m"},
         {"perfil": "W 610×174,0", "n": 14, "m": 71.2, "kgm": 174.0, "kg": 12391.6,
          "origem": "3D: o rótulo de cada vão nas plantas 900/901 (DWG); pilares pela tabela de variação; tabela resumo 900/901: 100,6 m"}]
    CH = [{"perfil": "CH 12,5 (1/2\")", "n": 319, "m": 157.6, "kgm": None, "kg": 2023.9, "origem": "3D: 294× Enrijecedor do pilar"}]
    total = 68848.0 + 12391.6 + 2023.9
    linhas = [
        {"nome": "Perfil W laminado A572", "unidade": "kg", "qtd": 81239.6, "texto": "81.240,00kg", "peso": True, "itens": W, "nota": "",
         "tabela": None, "preco_texto": "R$7,79/kg (ARCELOR)", "preco_item": "cotação ArcelorMittal 05/11", "preco_estimativa": False},
        {"nome": "Chaparia #", "unidade": "kg", "qtd": 2023.9, "texto": "2.025,00kg", "peso": True, "itens": CH, "nota": "a chapa comercial",
         "tabela": None, "preco_texto": "R$5,31/kg (ARCELOR)", "preco_item": "", "preco_estimativa": False},
        {"nome": "Chumbadores", "unidade": None, "qtd": None, "texto": "Ø27 - 1 1/8\": 258,25 m (1.160,72 kg)\nØ12 - 1/2\": 5,76 m (5,11 kg)",
         "peso": False, "itens": [], "nota": "FAB-05", "tabela": (["Barra", "m"], [["Ø27", "258,25"]], None), "preco_texto": "", "preco_item": ""},
        {"nome": "Montagem", "unidade": "m2", "qtd": 611.1, "texto": "611,10m2", "peso": False, "itens": [], "nota": "", "tabela": None},
        {"nome": "Intumescente TRRF", "unidade": "m2", "qtd": 3492.0, "texto": "3.492m2 (TRRF 120, perfis W)", "peso": False, "itens": [],
         "nota": "", "tabela": None, "preco_texto": "R$933/m2 (estimativa)", "preco_item": "mercado", "preco_estimativa": True},
        {"nome": "Telha", "unidade": None, "qtd": None, "texto": "—", "peso": False, "itens": [], "nota": "", "tabela": None},
        {"nome": "Impostos", "unidade": None, "qtd": None, "texto": "", "peso": False, "itens": [], "nota": "", "tabela": None},
    ]
    return {"titulo": "Edifício Administrativo", "cabecalho": "HORA CERTA – EDIFÍCIO ADMINISTRATIVO", "projeto": "ESTM-PE-900",
            "data": "05/11/2026", "rev": "rev14", "sigla": "ADM", "peso": 83265.0, "total_kg": total, "area_total": 611.1, "dif_setor": 0.0,
            "setores": [{"nome": "1º PAV.", "L": 43.41, "C": 19.38, "H": 5.22, "area": 611.1, "kg": total, "r5": 83265.0, "n": 555,
                         "tipos": {"vigas": total}, "de_projecao": "o retângulo", "de_H": "laje", "de_area": "steel deck"}],
            "linhas": linhas, "ponte": [("Projeto", 80000.0), ("+ ligações", total - 80000.0)], "faixa": [],
            "compra": {"r5": 86000.0, "sobra_kg": 2431.0, "perda_chapa_kg": 303.6, "chapa_kg": 2023.9, "nota": "W em 12 m",
                       "nota_emenda": "compra com emenda de perfil (padrão da fábrica)",
                       "tabela": [{"perfil": "W 530×66,0", "pecas": 222, "m": 1043.2, "kgm": 66.0, "kg": 68848.0, "compra": "90 barras de 12 m",
                                   "emendas": 3, "m_compra": 1080.0, "kg_compra": 71280.0, "sobra_kg": 2431.0}]},
            "ligacoes": {"texto": "todas soldadas", "contadas": [("viga soldada", 785)], "pecas": [("cantoneiras", 533, 982.4)]},
            "fora": ["sem telhas"], "contradicoes": [("tabela resumo 100,6 m", "a tabela de variação", "1")],
            "historico": [("rev13", "05/11/2026", "a chapa comercial"), ("rev14", "05/11/2026", "TRRF 120")], "preco_fonte": "tabela Hermes"}


def _texto(h):
    """o texto como o PDF o dá à conferência (sem as marcas e com os espaços juntos)"""
    t = re.sub(r"<style.*?</style>", " ", h, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", t).replace("&quot;", "\"").replace("&amp;", "&").split())


def test_as_ancoras_da_conferencia_do_auditor():
    t = _texto(MQ.html_memorial(_D(), "ADM-RESUMO-2026-11-05-rev14.docx"))
    # C04: "<linha do Word> — <primeiro trecho do texto do Word>"
    for nome, txt in (("Perfil W laminado A572", "81.240,00kg"), ("Chaparia #", "2.025,00kg"), ("Chumbadores", "Ø27 - 1 1/8\": 258,25 m"),
                      ("Montagem", "611,10m2"), ("Intumescente TRRF", "3.492m2")):
        assert re.search(re.escape(nome) + r"\s*—\s*" + re.escape(txt), t), nome
    # C07: a seção 3 entre "3. Quadro DESCRIÇÃO" e "Compra = líquido", perfil · peças · m · kg/m · kg em cada linha de peso
    i3, i4 = t.find("3. Quadro DESCRIÇÃO"), t.find("Compra = líquido")
    assert 0 <= i3 < i4
    sec3 = t[i3:i4]
    for perfil, kg in (("W 530×66,0", "68.848,0"), ("W 610×174,0", "12.391,6")):
        achado = re.findall(re.escape(perfil).replace(r"\ ", r"\s*") + r"\s+[\d\.]+\s+[\d\.,]+\s+[\d,]+\s+([\d\.]+,\d)\b", sec3)
        assert achado == [kg], perfil
    # a lista por perfil da compra fica fora da seção 3 (senão a C07 somava o W duas vezes)
    assert "90 barras de 12 m" not in sec3 and "90 barras de 12 m" in t
    # C23: a nota da compra com emenda e a coluna "emendas"
    assert "compra com emenda de perfil (padrão da fábrica)" in t.lower() and "Emendas" in t


def test_preco_ligado_e_desligado():
    D = _D()
    com = MQ.html_memorial(D, "x.docx")
    sem = MQ.html_memorial(D, "x.docx", preco=False)
    assert "R$7,79/kg (ARCELOR)" in com and "Preço unitário → Word" in com and "preço: <b class=\"chave\">ligado" in com
    assert "R$7,79" not in sem and "Preço unitário" not in sem and "a Hermes preenche" not in sem and "desligado" in sem
    assert 'class="preco estimativa"' in com                     # a estimativa (intumescente) em outra cor
    # os números são os mesmos com e sem preço
    for n in ("81.240,00kg", "83.265,00", "86.000,00", "611,10"):
        assert n in com and n in sem


def test_capa_quadro_obra_e_linhas_sem_numero():
    h = MQ.html_memorial(_D(), "ADM-RESUMO-2026-11-05-rev14.docx")
    t = _texto(h)
    assert "HORA CERTA – EDIFÍCIO ADMINISTRATIVO" in t and "embasa cada número do ADM-RESUMO-2026-11-05-rev14.docx" in t
    assert "Peso líquido 83.265 kg" in t and "Compra 86.000 kg" in t and "Intumescente 3.492 m²" in t
    assert "Telha" in t.split("Linhas com \"—\"")[1]                 # a linha "—" vai para a lista das que não há
    assert "Impostos" not in t                                      # a linha em branco é da Hermes: sem seção
    assert t.index("rev14 05/11/2026 TRRF 120") < t.index("rev13 05/11/2026")   # a revisão mais nova em cima


def test_origem_repetida_vira_nota():
    t = _texto(MQ.html_memorial(_D(), "x.docx"))
    assert "Origem de todas as linhas: 3D: o rótulo de cada vão nas plantas 900/901 (DWG); pilares pela tabela de variação." in t
    assert t.count("o rótulo de cada vão") == 1
    assert MQ._prefixo_comum(["a; b; um", "a; b; outro"]) == ""                  # curto demais: fica na coluna
    assert MQ._prefixo_comum(["só uma origem bem comprida aqui; x"]) == ""


def test_foto_ao_lado_so_da_tabela_curta(tmp_path):
    cam = tmp_path / "f.jpg"
    cam.write_bytes(b"\xff\xd8\xff")
    D = _D()
    fotos = {MQ.chave_da_foto(x): str(cam) for x in D["linhas"] if x["peso"]}
    h = MQ.corpo_memorial(D, "x.docx", fotos)
    sec_w = h[h.index("Perfil W laminado A572 — "):h.index("Chaparia # — ")]
    assert 'class="lado-a-lado"' in sec_w                           # 2 linhas: a foto ao lado
    D["linhas"][0]["itens"] = D["linhas"][0]["itens"] * 4             # 8 linhas: a foto em cima, a tabela na largura da folha
    h = MQ.corpo_memorial(D, "x.docx", fotos)
    sec_w = h[h.index("Perfil W laminado A572 — "):h.index("Chaparia # — ")]
    assert 'class="foto-em-cima"' in sec_w and 'class="lado-a-lado"' not in sec_w


def test_pedidos_de_fotos_pelas_pecas_de_cada_linha():
    ent = [{"id": "a", "tipo": "barra", "perfil": "W 530×66,0"}, {"id": "b", "tipo": "barra", "perfil": "W 610×174,0"},
           {"id": "c", "tipo": "chapa"}, {"id": "d", "tipo": "barra", "perfil": "U 200×75×3,0"}]
    P = {p["nome"]: p for p in MQ.pedidos_de_fotos(_D(), ent)}
    assert set(P) == {"capa", "linha-perfil-w-laminado-a572", "linha-chaparia"}
    assert P["linha-perfil-w-laminado-a572"]["cores"] == {MQ.CORES[0]: ["a"], MQ.CORES[1]: ["b"]}
    assert P["linha-chaparia"]["destaque"] == ["c"]
    assert MQ._perfil_canonico("U 200×75×3,00 (FF)") == MQ._perfil_canonico("U 200×75×3,0")


def test_a_ponte_que_nao_fecha_trava():
    D = _D()
    D["ponte"][0] = ("Projeto", 70000.0)
    with pytest.raises(AssertionError, match="ponte"):
        MQ.corpo_memorial(D, "x.docx")
