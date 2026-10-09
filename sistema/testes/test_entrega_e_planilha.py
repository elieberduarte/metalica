# -*- coding: utf-8 -*-
"""O nome de entrega dos arquivos ("OBRA - Arquivo (dd.mm.aaaa).ext", 09/10) e a planilha do resumo de materiais
(xlsx sem biblioteca de fora): abas, títulos, números e o total."""
import json
import os
import sys
import time
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import entrega, xlsx_simples                       # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def test_nome_de_entrega():
    t = time.mktime((2026, 10, 9, 12, 0, 0, 0, 0, -1))
    assert entrega.nome_de_entrega("VICENTE RESIDENCE", "resumo-de-materiais", ".pdf", t) == \
        "VICENTE RESIDENCE - Resumo de materiais (09.10.2026).pdf"
    # o arquivo que já traz a obra não a repete; o nome sem obra fica só com o arquivo
    assert entrega.nome_de_entrega("ME SOORO - DEPÓSITO QUÍMICO", "Proposta_2026-001_R00_ME_SOORO_-_DEPÓSITO_QUÍM", ".pdf", t) == \
        "ME SOORO - DEPÓSITO QUÍMICO - Proposta 2026-001 R00 (09.10.2026).pdf"
    assert entrega.nome_de_entrega("", "romaneio", ".csv", t) == "Romaneio (09.10.2026).csv"
    assert "/" not in entrega.nome_de_entrega("OBRA A/B", "plano-de-corte", ".csv", t)


def test_arquivo_servido_pela_pasta_do_projeto(tmp_path):
    p = tmp_path / "obra-x"
    (p / "detalhamento").mkdir(parents=True)
    (p / "projeto.json").write_text(json.dumps({"nome": "OBRA X"}), encoding="utf-8")
    f = p / "detalhamento" / "romaneio.csv"
    f.write_text("a;b", encoding="utf-8")
    nome = entrega.nome_do_arquivo_servido(str(f), str(tmp_path))
    assert nome.startswith("OBRA X - Romaneio (") and nome.endswith(").csv")
    assert entrega.nome_do_arquivo_servido(str(p / "projeto.json"), str(tmp_path)) is None     # o .json não é entrega


def test_planilha_abre_com_abas_numeros_e_total(tmp_path):
    cam = str(tmp_path / "p.xlsx")
    xlsx_simples.escrever(cam, [{"nome": "Perfis e barras", "linhas": [["Perfil", "kg", "barras"], ["TQ 50x50x3,0", 10972.6, 437],
                                                                     ["TOTAL", 10972.6, 437]], "total": True, "larguras": [20, 10, 8]},
                                {"nome": "Resumo", "linhas": [["Item", "Valor"], ["Aço", 39667.0]]}])
    z = zipfile.ZipFile(cam)
    livro = ET.fromstring(z.read("xl/workbook.xml"))
    assert [s.get("name") for s in livro.find("m:sheets", NS)] == ["Perfis e barras", "Resumo"]
    aba = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    linhas = aba.find("m:sheetData", NS).findall("m:row", NS)
    assert len(linhas) == 3
    c = linhas[1].findall("m:c", NS)
    assert c[0].find("m:is/m:t", NS).text == "TQ 50x50x3,0" and c[1].find("m:v", NS).text == "10972.6" and c[2].find("m:v", NS).text == "437"
    assert aba.find("m:autoFilter", NS) is not None and aba.find("m:sheetViews/m:sheetView/m:pane", NS).get("state") == "frozen"
    for nome in z.namelist():                                   # todo XML bem formado
        if nome.endswith(".xml") or nome.endswith(".rels"):
            ET.fromstring(z.read(nome))
