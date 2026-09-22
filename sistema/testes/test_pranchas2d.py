# -*- coding: utf-8 -*-
"""Testes das pranchas montadas a partir de desenhos 2D (nucleo2d/pranchas.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import ErroDeDados                                   # noqa: E402
from nucleo2d.desenho import Desenho, Linha, Cota, Texto, Circulo     # noqa: E402
from nucleo2d import pranchas                                         # noqa: E402


def _detalhe(n_celulas=3, larg=1200.0, escala=10.0):
    """Desenho com células como as do detalhamento: caixa em metadados e atributos."""
    d = Desenho(nome="Detalhamento – teste", escala=escala)
    x = 0.0
    for i in range(n_celulas):
        atr = {"detalhe": "posicao", "posicao": "P%d" % (i + 1)}
        d.add(Linha(a=(x, 0), b=(x + larg, 0), atributos=dict(atr)))
        d.add(Linha(a=(x + larg, 0), b=(x + larg, 500), atributos=dict(atr)))
        d.add(Circulo(camada="FURO", centro=(x + 300, 250), raio=6.5, atributos=dict(atr)))
        d.add(Cota(modo="h", p1=(x, 0), p2=(x + larg, 0), deslocamento=-10, atributos=dict(atr)))
        d.add(Texto(posicao=(x, 700), texto="P%d – 04x" % (i + 1), altura=3.5, atributos=dict(atr)))
        d.metadados.setdefault("celulas", []).append([x, -150, x + larg, 750])
        x += larg + 400
    return d


def test_celulas_e_transformacao():
    d = _detalhe()
    cels = pranchas.celulas_de(d, "det")
    assert [c["titulo"] for c in cels] == ["P1 – 04x", "P2 – 04x", "P3 – 04x"]
    assert all(len(c["entidades"]) == 5 for c in cels)
    folhas = pranchas.montar_pranchas([{"nome": "det", "desenho": d}], formato="A3", carimbo={"obra": "Obra X"})
    assert len(folhas) == 1
    f = folhas[0]
    assert f.escala == 1.0 and f.metadados["prancha"]["formato"] == "A3"
    larg, alt = pranchas.FOLHAS["A3"]
    # tudo dentro da folha
    for e in f.entidades.values():
        for p in e.pontos():
            assert -0.01 <= p[0] <= larg + 0.01 and -0.01 <= p[1] <= alt + 0.01, (e.tipo, p)
    # a cota de 1200 mm em 1:10 mede 120 mm no papel e mostra "1200"
    cotas = [e for e in f.entidades.values() if isinstance(e, Cota) and e.atributos.get("fonte") == "det"]
    assert cotas and all(abs(c.valor() - 120.0) < 0.01 and c.texto == "1200" for c in cotas)
    # furo de raio 6,5 vira 0,65
    furos = [e for e in f.entidades.values() if isinstance(e, Circulo)]
    assert furos and abs(furos[0].raio - 0.65) < 1e-6
    # carimbo com obra, prancha 01/01 e escala
    textos = [e.texto for e in f.entidades.values() if isinstance(e, Texto)]
    assert "Obra X" in textos and "01/01" in textos and any("1:10" in t for t in textos)
    assert sum(1 for t in textos if t.startswith("ESC. 1:10")) == 3


def test_reduz_escala_e_quebra_em_pranchas():
    # célula de 30 m em 1:10 não cabe num A4: desce de escala com nota
    d = _detalhe(n_celulas=1, larg=30000.0, escala=10.0)
    folhas = pranchas.montar_pranchas([{"nome": "det", "desenho": d}], formato="A4")
    cel = folhas[0].metadados["prancha"]["celulas"][0]
    assert cel["escala"] > 10.0
    assert any("reduzida" in e.texto for e in folhas[0].entidades.values() if isinstance(e, Texto))
    # muitas células: várias pranchas numeradas
    d = _detalhe(n_celulas=40, larg=2000.0, escala=10.0)
    folhas = pranchas.montar_pranchas([{"nome": "det", "desenho": d}], formato="A4", titulo="Prancha")
    assert len(folhas) > 1
    assert [f.nome for f in folhas][:2] == ["Prancha 01", "Prancha 02"]
    total = sum(len(f.metadados["prancha"]["celulas"]) for f in folhas)
    assert total == 40
    # desenho sem células (um corte) é uma célula só
    corte = Desenho(nome="Corte A", escala=20.0)
    corte.add(Linha(a=(0, 0), b=(5000, 0)))
    folhas = pranchas.montar_pranchas([{"nome": "corte-a", "desenho": corte}], formato="A3")
    assert len(folhas[0].metadados["prancha"]["celulas"]) == 1
    try:
        pranchas.montar_pranchas([{"nome": "x", "desenho": Desenho(nome="vazio")}], formato="A3")
        assert False
    except ErroDeDados:
        pass


def test_filtro_de_chaves_e_tabela():
    d = _detalhe(n_celulas=3)
    d.metadados["detalhamento"] = {"itens": {"P%d" % i: {"quantidade": 4, "perfil": "PLATE 100x50x3", "comprimento": 1200,
                                                          "espessura": 3.0, "peso": 1.5, "classe": "Chapa"} for i in (1, 2, 3)}}
    folhas = pranchas.montar_pranchas([{"nome": "det", "desenho": d, "chaves": ["P2"]}], formato="A3")
    cels = folhas[0].metadados["prancha"]["celulas"]
    assert [c["titulo"] for c in cels] == ["P2 – 04x"]
    textos = [e for e in folhas[0].entidades.values() if isinstance(e, Texto) and e.atributos.get("prancha") == "tabela"]
    assert any(t.texto == "P2" for t in textos) and not any(t.texto == "P1" for t in textos)
    assert any(t.texto == "6.0" for t in textos)        # peso total 4 × 1,5


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except Exception as e:                    # noqa: BLE001
                falhas += 1
                print(f"  FALHA {nome}: {e}")
    print(f"\n{falhas} falha(s).")
    sys.exit(1 if falhas else 0)


def test_pdf_das_pranchas(tmp_path):
    """PDF no tamanho real: prancha A3 sai em 420 × 297 mm; desenho comum, no tamanho
    dele na escala mais a margem."""
    import pymupdf
    d = _detalhe()
    folhas = pranchas.montar_pranchas([{"nome": "det", "desenho": d}], formato="A3")
    caminho = pranchas.pdf_dos_desenhos(folhas + [d], str(tmp_path / "p.pdf"))
    doc = pymupdf.open(caminho)
    assert len(doc) == 2
    w, h = doc[0].rect.width / 72 * 25.4, doc[0].rect.height / 72 * 25.4
    assert abs(w - 420) < 1 and abs(h - 297) < 1
    (x0, y0), (x1, y1) = d.caixa()
    w2 = doc[1].rect.width / 72 * 25.4
    assert abs(w2 - ((x1 - x0) / d.escala + 20)) < 1
    assert "P1" in doc[0].get_text()
