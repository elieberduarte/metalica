# -*- coding: utf-8 -*-
"""Imprimir pranchas (saida/impressao.py, rota_impressao do app.py; pedido do usuário, 21/10): o papel de cada folha,
onde ela cai no papel, a cor, as folhas marcadas — e a impressão de verdade pela "Microsoft Print to PDF" do Windows,
que grava num arquivo o que a impressora receberia."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Linha, Texto   # noqa: E402
from nucleo2d import pranchas                         # noqa: E402
from saida import impressao                           # noqa: E402

#: os papéis como a plotter da fábrica (HP Designjet T120, driver IPP do Windows) os informa: o A1 é o "ISOA1"
PLOTTER = [{"id": 8, "nome": "A3", "largura": 297.0, "altura": 420.0},
           {"id": 9, "nome": "A4", "largura": 210.0, "altura": 297.0},
           {"id": 66, "nome": "A2", "largura": 420.0, "altura": 594.0},
           {"id": 123, "nome": "Architecture DSheet", "largura": 609.6, "altura": 914.4},
           {"id": 169, "nome": "ISOA0", "largura": 841.0, "altura": 1189.0},
           {"id": 170, "nome": "ISOA1", "largura": 594.0, "altura": 841.0}]
MM = 72 / 25.4


def test_papel_do_tamanho_da_folha():
    """Automático: a A1 deitada vai no ISOA1 (em pé no driver), em tamanho real."""
    p, ajuste, aviso = impressao.papel_da_folha((841.0, 594.0), PLOTTER)
    assert p["id"] == 170 and ajuste == "real" and not aviso
    p, ajuste, _ = impressao.papel_da_folha((420.0, 297.0), PLOTTER)
    assert p["id"] == 8


def test_papel_sem_o_tamanho_vai_no_menor_que_cabe_ou_reduzido():
    sem_a1 = [p for p in PLOTTER if p["id"] != 170]
    p, ajuste, aviso = impressao.papel_da_folha((841.0, 594.0), sem_a1)
    assert p["id"] == 123 and ajuste == "real" and "Architecture DSheet" in aviso
    so_pequenos = [p for p in PLOTTER if p["id"] in (8, 9)]
    p, ajuste, aviso = impressao.papel_da_folha((841.0, 594.0), so_pequenos)
    assert p["id"] == 8 and ajuste == "ajustar" and "reduzida" in aviso


def test_papel_escolhido_vale_com_o_ajuste_pedido():
    p, ajuste, _ = impressao.papel_da_folha((841.0, 594.0), PLOTTER, papel=8, ajuste="ajustar")
    assert p["id"] == 8 and ajuste == "ajustar"
    with pytest.raises(impressao.ErroDeImpressao):
        impressao.papel_da_folha((841.0, 594.0), PLOTTER, papel=999)


def _area(papel_mm, dpi=300, margem_mm=5.0):
    k = dpi / 25.4
    w, h = papel_mm
    return {"dpi_x": dpi, "dpi_y": dpi, "papel": (round(w * k), round(h * k)),
            "margem": (round(margem_mm * k), round(margem_mm * k)),
            "util": (round((w - 2 * margem_mm) * k), round((h - 2 * margem_mm) * k))}


def test_colocar_em_tamanho_real_no_meio_do_papel():
    """A A1 no A1 deitado: 1:1, nada girado, no meio do papel inteiro; a margem de 7 mm da folha passa da de 5 mm
    da impressora, então nada fica de fora."""
    a = _area((841.0, 594.0))
    c = impressao.colocar((841.0, 594.0), a, "real")
    assert not c["girar"] and c["escala"] == 1.0
    assert abs(c["largura"] - a["papel"][0]) <= 1 and c["fora_mm"] <= 5.01
    assert abs(c["x"] + a["margem"][0]) <= 1


def test_colocar_ajustado_gira_e_reduz():
    """A A1 deitada numa A3 em pé (a impressora não girou o papel): gira e reduz para caber na área que imprime."""
    a = _area((297.0, 420.0))
    c = impressao.colocar((841.0, 594.0), a, "ajustar")
    assert c["girar"]
    assert abs(c["escala"] - min(287.0 / 594.0, 410.0 / 841.0)) < 1e-3
    assert c["x"] >= 0 and c["y"] >= 0 and c["x"] + c["largura"] <= a["util"][0] + 1 and c["y"] + c["altura"] <= a["util"][1] + 1
    assert c["fora_mm"] == 0


def test_preto_escurece_as_cores_e_mantem_o_cinza():
    import numpy as np
    rgb = np.array([[[255, 0, 0], [0, 0, 255], [255, 255, 0], [200, 200, 200], [255, 255, 255], [255, 128, 128]]],
                   dtype=np.uint8)
    g = impressao.tons(rgb, "preto")[0, :, 0]
    assert list(g) == [0, 0, 0, 200, 255, 128]
    c = impressao.tons(rgb, "cinza")[0, :, 0]
    assert c[2] > 200 and c[0] < 100                     # o amarelo some na luminância; no preto, não
    assert impressao.tons(rgb, "cor") is rgb


def test_fator_de_ampliacao_inteiro():
    assert [impressao.fator_de_ampliacao(d) for d in (300, 360, 600, 1200, 150)] == [1, 2, 2, 4, 1]


def _pranchas_a4(n=3):
    folhas = []
    for i in range(n):
        d = Desenho(nome="Prancha %02d" % (i + 1), escala=1.0)
        d.add(Linha(a=(30, 30), b=(250, 30)))
        d.add(Texto(posicao=(40, 100), texto="FOLHA %d" % (i + 1), altura=10))
        d.metadados["prancha"] = {"formato": "A4", "numero": i + 1, "total": n, "titulo": "FOLHA %d" % (i + 1)}
        folhas.append(d)
    return folhas


def test_pdf_so_das_folhas_marcadas(tmp_path):
    import pymupdf
    doc = pymupdf.open(pranchas.pdf_dos_desenhos(_pranchas_a4(3), str(tmp_path / "p.pdf"), so=[1]))
    assert doc.page_count == 1 and "FOLHA 2" in doc[0].get_text()
    doc = pymupdf.open(pranchas.pdf_dos_desenhos(_pranchas_a4(3), str(tmp_path / "q.pdf"), so=[0, 2]))
    assert [("FOLHA 1" in p.get_text(), "FOLHA 3" in p.get_text()) for p in doc] == [(True, False), (False, True)]
    # no desenho das pranchas lado a lado, a página conta por folha
    junto = pranchas.juntar_pranchas(_pranchas_a4(2), nome="Pranchas")
    doc = pymupdf.open(pranchas.pdf_dos_desenhos(_pranchas_a4(1) + [junto], str(tmp_path / "j.pdf"), so=[2]))
    assert doc.page_count == 1 and "FOLHA 2" in doc[0].get_text()
    assert pymupdf.open(pranchas.pdf_dos_desenhos(_pranchas_a4(3), str(tmp_path / "r.pdf"))).page_count == 3


# ------------------------------------------------------------ a impressora de verdade

def _com_pdf_do_windows():
    if sys.platform != "win32":
        return False
    try:
        return any(p["nome"] == "Microsoft Print to PDF" for p in impressao.impressoras()["impressoras"])
    except Exception:                                    # noqa: BLE001
        return False


windows = pytest.mark.skipif(not _com_pdf_do_windows(), reason="sem a Microsoft Print to PDF do Windows")


@pytest.fixture(autouse=True)
def _sem_faulthandler():
    """O driver da impressora levanta e trata exceções COM internas (0x80040155); o faulthandler do pytest as
    imprime como "Windows fatal exception" mesmo tratadas. O servidor não liga o faulthandler."""
    import faulthandler
    ligado = faulthandler.is_enabled()
    faulthandler.disable()
    yield
    if ligado:
        faulthandler.enable()


def _a3_colorida(caminho):
    import pymupdf
    doc = pymupdf.open()
    pg = doc.new_page(width=420 * MM, height=297 * MM)
    pg.draw_rect(pymupdf.Rect(25 * MM, 7 * MM, 413 * MM, 290 * MM), color=(1, 0, 0), width=2)
    pg.draw_rect(pymupdf.Rect(60 * MM, 60 * MM, 200 * MM, 200 * MM), color=(0, 0, 1), fill=(0, 0, 1))
    doc.save(caminho)
    return caminho


def _pixels(caminho, pagina=0):
    import numpy as np
    import pymupdf
    pix = pymupdf.open(caminho)[pagina].get_pixmap(dpi=30, colorspace=pymupdf.csRGB)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).astype(int)


@windows
def test_imprime_a3_no_papel_a3_e_reduzida_na_a4(tmp_path):
    import pymupdf
    pdf = _a3_colorida(str(tmp_path / "a3.pdf"))
    saida = str(tmp_path / "auto.pdf")
    r = impressao.imprimir_pdf(pdf, "Microsoft Print to PDF", cor="cor", arquivo=saida)
    assert r["folhas"][0]["papel"] == "A3" and r["folhas"][0]["escala"] == 1.0
    pg = pymupdf.open(saida)[0]
    assert abs(pg.rect.width / MM - 420) < 2 and abs(pg.rect.height / MM - 297) < 2     # deitada, como a folha
    px = _pixels(saida)
    assert ((px[..., 2] > 150) & (px[..., 0] < 80)).any()                              # o azul chegou azul
    saida = str(tmp_path / "a4.pdf")
    r = impressao.imprimir_pdf(pdf, "Microsoft Print to PDF", papel=9, ajuste="ajustar", cor="preto", copias=2, arquivo=saida)
    assert r["folhas"][0]["papel"] == "A4" and abs(r["folhas"][0]["escala"] - 0.68) < 0.05
    doc = pymupdf.open(saida)
    assert doc.page_count == 2                                                          # as 2 cópias
    assert abs(doc[0].rect.width / MM - 297) < 2 and abs(doc[0].rect.height / MM - 210) < 2
    px = _pixels(saida)
    assert (px.max(axis=2) < 60).any()                                                  # o azul cheio saiu preto
    assert not ((px.max(axis=2) - px.min(axis=2)) > 40).any()                           # e nada colorido


@windows
def test_rota_imprime_as_folhas_marcadas(tmp_path, monkeypatch):
    """A rota do CAD: as folhas das pranchas na ordem do PDF; só a marcada vai para a impressora, no papel dela. A
    "Microsoft Print to PDF" (porta que pergunta onde gravar) grava em pranchas/ do projeto, sem a janela do Windows."""
    import pymupdf
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    r = g.criar("Obra impressão", tipo="ifc")
    s = r.get("slug") or r.get("id") or r.get("nome")
    for d in _pranchas_a4(3):
        g.salvar_desenho(s, d.nome, d.dict())
    nomes = sorted(d["nome"] for d in g.listar_desenhos(s))
    folhas = app.rota_impressao(s, "folhas", {"desenhos": nomes})["folhas"]
    assert [(f["indice"], f["numero"], f["formato"]) for f in folhas] == [(0, 1, "A4"), (1, 2, "A4"), (2, 3, "A4")]
    r = app.rota_impressao(s, "imprimir", {"desenhos": nomes, "impressora": "Microsoft Print to PDF", "folhas": [1],
                                           "papel": "auto", "ajuste": "real", "cor": "preto", "copias": 1})
    assert r["paginas"] == 1 and r["folhas"][0]["papel"] == "A4"
    caminho = os.path.join(str(tmp_path), r["arquivo"]["caminho"]) if r["arquivo"].get("caminho") else None
    arq = caminho if caminho and os.path.exists(caminho) else os.path.join(g._existente(s), "pranchas", r["arquivo"]["nome"])
    pg = pymupdf.open(arq)[0]
    assert abs(pg.rect.width / MM - 297) < 2 and abs(pg.rect.height / MM - 210) < 2
    with pytest.raises(app.ErroDeDados):
        app.rota_impressao(s, "imprimir", {"desenhos": nomes, "impressora": "Impressora que não existe"})
    with pytest.raises(app.ErroDeDados):
        app.rota_impressao(s, "imprimir", {"desenhos": nomes, "impressora": "Microsoft Print to PDF", "folhas": []})
