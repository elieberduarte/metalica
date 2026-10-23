"""Imprimir o desenho que não é das pranchas (usuário, 23/10: "se dou um ctrl + p nessa tela original ele não deixa
imprimir aparece essa mensagem que o projeto não tem prancha"): uma folha com o trecho do desenho (a vista da tela ou o
desenho inteiro) na escala escolhida — pranchas.pdf_da_area —, no papel da série A em que ela cabe (impressao
.papel_da_folha com serie_a). A tela é conferida em verificadores/verif_cad_selecao_setas_impressao.py."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo.base import ErroDeDados  # noqa: E402
from nucleo2d import pranchas  # noqa: E402
from nucleo2d.desenho import Desenho, Linha, Texto  # noqa: E402
from saida import impressao  # noqa: E402

MM = 72 / 25.4


def _original():
    d = Desenho(nome="Original", escala=10.0)
    d.add(Linha(a=(0, 0), b=(2000, 0)))
    d.add(Linha(a=(2000, 0), b=(2000, 1200)))
    d.add(Linha(id="longe", a=(50000, 50000), b=(51000, 50000)))
    d.add(Texto(posicao=(100, 1300), texto="ORIGINAL", altura=5))
    return d


def test_folha_do_trecho_na_escala(tmp_path):
    import pymupdf
    pdf = pranchas.pdf_da_area(_original(), str(tmp_path / "a.pdf"), ((0, 0), (2000, 1400)), escala=10)
    pg = pymupdf.open(pdf)[0]
    assert (round(pg.rect.width / MM), round(pg.rect.height / MM)) == (200, 140)     # 2000 × 1400 ÷ 10
    escuros = sum(1 for b in pg.get_pixmap(dpi=30, colorspace=pymupdf.csGRAY).samples if b < 128)
    assert escuros > 50                                                                # as linhas e o texto
    # sem escala: a do desenho
    pg = pymupdf.open(pranchas.pdf_da_area(_original(), str(tmp_path / "b.pdf"), ((0, 0), (2000, 1400))))[0]
    assert round(pg.rect.width / MM) == 200


def test_trecho_vazio_ou_grande_demais():
    with pytest.raises(ErroDeDados):
        pranchas.pdf_da_area(_original(), "x.pdf", ((0, 0), (0, 100)), escala=10)
    with pytest.raises(ErroDeDados) as e:
        pranchas.pdf_da_area(_original(), "x.pdf", ((0, 0), (60000, 60000)), escala=1)
    assert "escala maior" in str(e.value)


PAPEIS = [{"id": 1, "nome": "Envelope C5", "largura": 162.0, "altura": 229.0},
          {"id": 2, "nome": "B5 (JIS)", "largura": 182.0, "altura": 257.0},
          {"id": 9, "nome": "A4", "largura": 210.0, "altura": 297.0},
          {"id": 8, "nome": "A3", "largura": 297.0, "altura": 420.0}]


def test_folha_de_desenho_no_menor_da_serie_a():
    p, ajuste, _ = impressao.papel_da_folha((200.0, 160.0), PAPEIS, serie_a=True)
    assert p["nome"] == "A4" and ajuste == "real"
    # a das pranchas continua no menor que cabe (o A1 sem o ISOA1 vai no DSheet, test_impressao)
    p, _a, _ = impressao.papel_da_folha((200.0, 160.0), PAPEIS)
    assert p["nome"] == "Envelope C5"
    # sem nenhum da série A em que caiba, o menor dos outros
    p, _a, _ = impressao.papel_da_folha((200.0, 160.0), PAPEIS[:2], serie_a=True)
    assert p["nome"] == "Envelope C5"
