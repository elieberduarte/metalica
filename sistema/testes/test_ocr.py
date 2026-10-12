# -*- coding: utf-8 -*-
"""OCR interno (nucleo/ocr.py): o formato do resultado, as páginas pedidas e, no Windows com o OCR em pt-BR, a
leitura de verdade de uma imagem com texto."""
import os

import pytest

from nucleo import ocr


def test_paginas_pedidas():
    assert ocr._paginas_pedidas(None, 3) == [1, 2, 3]
    assert ocr._paginas_pedidas("2-3,5,9", 6) == [2, 3, 5]
    assert ocr._paginas_pedidas([0, 1, 7], 6) == [1]


def test_arrumar_linhas_e_caixas():
    r = ocr._arrumar({"linhas": [{"t": "Cantoneiras simples", "p": [["Cantoneiras", 10, 20, 90, 12], ["simples", 105, 21, 50, 11]]},
                                 {"t": "6.5.2", "p": ["6.5.2", 10, 40, 30, 12]}],          # uma palavra: o JSON achata
                      "largura": 200, "altura": 100, "angulo": None})
    assert r["texto"] == "Cantoneiras simples\n6.5.2"
    assert r["linhas"][0]["caixa"] == [10.0, 20.0, 145.0, 12.0]
    assert r["linhas"][1]["palavras"][0]["texto"] == "6.5.2"


def test_sem_acento_na_busca():
    assert ocr._sem_acento("Ligações excêntricas") == "Ligacoes excentricas"


@pytest.mark.skipif(os.name != "nt" or not ocr.disponivel(), reason="só no Windows com o OCR em português")
def test_le_uma_imagem(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    pg = doc.new_page(width=420, height=120)
    pg.insert_text((20, 60), "Treliça com excentricidade", fontsize=24)
    img = tmp_path / "t.png"
    pg.get_pixmap(dpi=200).save(str(img))
    texto = ocr.ler_imagens([str(img)])[0]["texto"]
    assert "excentricidade" in texto.lower()
