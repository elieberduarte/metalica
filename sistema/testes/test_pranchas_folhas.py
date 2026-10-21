# -*- coding: utf-8 -*-
"""O PDF das pranchas pelas folhas que estão no desenho (nucleo2d/pranchas.py, sincronizar_folhas).

Vicente Residence, 21/10 (usuário: "está saindo várias folhas em branco"): a folha 4 foi apagada no CAD (clicando na borda)
e as seguintes encostadas à mão; o PDF recortava as páginas nos lugares que a montagem gravou — a página 4 com o fundo de
outra folha e da 5 à 10 em branco."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Linha, Polilinha, Texto, transladar   # noqa: E402
from nucleo2d import pranchas as P                                         # noqa: E402

LARG, ALT = P.FOLHAS["A1"]


def _folha(n, total):
    d = Desenho(nome="Prancha %02d" % n, escala=1.0)
    d.metadados["prancha"] = {"formato": "A1", "numero": n, "total": total, "titulo": "Folha %d" % n}
    atr = {"prancha": "moldura"}
    d.add(Polilinha(camada="PRANCHA", vertices=[(0, 0), (LARG, 0), (LARG, ALT), (0, ALT)], fechada=True, atributos=dict(atr)))
    d.add(Texto(camada="TEXTO", posicao=(800, 10), texto="PRANCHA %02d/%02d   REV. 00" % (n, total), altura=1.7,
                atributos=dict(atr, campo="prancha")))
    d.add(Linha(camada="VISTA", a=(100, 300), b=(400, 300), atributos={"conteudo": n}))
    d.add(Texto(camada="TEXTO", posicao=(100, 320), texto="T%d – 01x" % n, altura=3.5, atributos={"cabecalho": 0, "conteudo": n}))
    return d


def _pranchas_editadas():
    """Três folhas lado a lado; a 2 apagada (a moldura e o conteúdo), a 3 encostada no lugar dela, e a marca T9 deixada
    fora de toda folha."""
    junto = P.juntar_pranchas([_folha(n, 3) for n in (1, 2, 3)])
    passo = LARG + P.FOLGA_ENTRE_FOLHAS
    for k in [k for k, e in junto.entidades.items() if e.atributos.get("prancha_numero") == 2]:
        del junto.entidades[k]
    for k, e in list(junto.entidades.items()):
        if e.atributos.get("prancha_numero") == 3:
            junto.entidades[k] = transladar(e, -passo, 0.0)
            junto.entidades[k].id = k
    junto.add(Texto(camada="TEXTO", posicao=(3 * passo + 50, 300), texto="T9 – 02x", altura=3.5, atributos={"cabecalho": 0}))
    return junto


def test_folha_apagada_e_movida():
    d = _pranchas_editadas()
    r = P.sincronizar_folhas(d)
    assert r["removidas"] == ["Folha 2"]
    assert r["fora"] == ["T9 – 02x"]
    folhas = d.metadados["pranchas"]
    assert [f["numero"] for f in folhas] == [1, 2] and all(f["total"] == 2 for f in folhas)
    assert folhas[1]["origem"] == [LARG + P.FOLGA_ENTRE_FOLHAS, 0.0]        # a que era a 3, no lugar da 2
    # cada página com o que está desenhado nela: a 2 tem o conteúdo da antiga 3 e o carimbo renumerado
    partes = P._por_folha(d)
    assert len(partes) == len(P.paginas_de(d)) == 2
    conteudo = [{e.atributos.get("conteudo") for e in p.entidades.values()} - {None} for p in partes]
    assert conteudo == [{1}, {3}]
    carimbos = [e.texto for e in partes[1].entidades.values() if e.atributos.get("campo") == "prancha"]
    assert carimbos == ["PRANCHA 02/02   REV. 00"]


def test_pdf_sem_paginas_em_branco(tmp_path):
    """Só pela exportação de sempre (sem a correção: três páginas, a 2 e a 3 em branco)."""
    import pymupdf
    P.pdf_dos_desenhos([_pranchas_editadas()], str(tmp_path / "pranchas.pdf"))
    doc = pymupdf.open(str(tmp_path / "pranchas.pdf"))
    textos = [pg.get_text() for pg in doc]
    assert len(doc) == 2, [t[:40] for t in textos]
    assert "T1" in textos[0] and "T3" in textos[1] and "PRANCHA 02/02" in textos[1]


def test_pdf_avisa_a_folha_apagada_e_o_que_ficou_fora(tmp_path):
    avisos = []
    P.pdf_dos_desenhos([_pranchas_editadas()], str(tmp_path / "pranchas.pdf"), avisos=avisos)
    assert any("apagada" in a for a in avisos) and any("T9 – 02x" in a for a in avisos)


def test_pranchas_como_montadas_nao_mudam():
    junto = P.juntar_pranchas([_folha(n, 3) for n in (1, 2, 3)])
    antes = [dict(f) for f in junto.metadados["pranchas"]]
    r = P.sincronizar_folhas(junto)
    assert r == {"removidas": [], "fora": []}
    assert [(f["numero"], f["origem"]) for f in junto.metadados["pranchas"]] == [(f["numero"], f["origem"]) for f in antes]
