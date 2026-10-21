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


# ------------------------------------------------------------------ a remontagem aprende pela folha
def _folha_com_celulas(n, total, ids):
    d = _folha(n, total)
    d.metadados["prancha"]["celulas"] = []
    for j, cel in enumerate(ids):
        y = 300 - 120 * j
        d.add(Polilinha(camada="VISTA", vertices=[(100, y), (400, y), (400, y + 80), (100, y + 80)], fechada=True,
                        atributos={"cel": cel, "fonte": "detalhamento-x"}))
        d.add(Texto(camada="TEXTO", posicao=(110, y + 60), texto=cel, altura=3.5, atributos={"cel": cel, "fonte": "detalhamento-x"}))
        d.metadados["prancha"]["celulas"].append({"id": cel, "caixa": [100, y, 400, y + 80]})
    return d


def _montagem():
    return P.juntar_pranchas([_folha_com_celulas(1, 3, ["c1"]), _folha_com_celulas(2, 3, ["c2"]),
                              _folha_com_celulas(3, 3, ["c3"])])


def _onde(d, cel):
    """(número da folha em que a célula está, x dentro da folha)"""
    q = [p for e in d.entidades.values() if (e.atributos or {}).get("cel") == cel for p in e.pontos()]
    cx = min(p[0] for p in q)
    for f in d.metadados["pranchas"]:
        if f["origem"][0] <= cx <= f["origem"][0] + LARG:
            return f["numero"], round(cx - f["origem"][0])
    return None, None


def test_remontar_depois_de_apagar_e_encostar_folhas():
    """O usuário leva a célula da folha 2 para a 3, apaga a moldura da 2 e encosta a 3 no lugar dela (Vicente, 21/10). A
    montagem seguinte (as molduras de volta nos lugares de sempre) sai como ele deixou: duas folhas, o c3 na moldura
    dele e o c2 dentro dela onde ele pôs — antes o c3 caía na moldura da folha 2 (cada célula "andava" uma folha)."""
    from nucleo2d import ajustes_pranchas as AJ
    passo = LARG + P.FOLGA_ENTRE_FOLHAS
    antigo = _montagem()
    antigo.metadados["geracao"] = "g1"
    ajustes = {"impressoes": {"g1": AJ.marcar(antigo)}}
    # a edição no CAD: o c2 para baixo, à direita na folha 3; a moldura da 2 apagada; a 3 (com o c2) encostada
    for k, e in list(antigo.entidades.items()):
        a = e.atributos or {}
        if a.get("cel") == "c2":
            antigo.entidades[k] = transladar(e, passo + 300, -200); antigo.entidades[k].id = k
        elif a.get("prancha_numero") == 2:
            del antigo.entidades[k]
    for k, e in list(antigo.entidades.items()):
        a = e.atributos or {}
        if a.get("prancha_numero") == 3 or a.get("cel") == "c2":
            antigo.entidades[k] = transladar(antigo.entidades[k], -passo, 0); antigo.entidades[k].id = k
    ajustes = AJ.aprender(antigo, ajustes)
    novo = _montagem()
    AJ.marcar(novo)
    r = AJ.aplicar(novo, ajustes)
    assert r.get("folhas_tiradas") == ["Folha 2"]
    assert [f["numero"] for f in novo.metadados["pranchas"]] == [1, 2]
    assert _onde(novo, "c1") == (1, 100)
    assert _onde(novo, "c3") == (2, 100)                     # na moldura da folha dele, no lugar gerado
    assert _onde(novo, "c2") == (2, 400)                     # na folha para onde o usuário a levou
    carimbos = [e.texto for e in novo.entidades.values() if (e.atributos or {}).get("campo") == "prancha"]
    assert sorted(carimbos) == ["PRANCHA 01/02   REV. 00", "PRANCHA 02/02   REV. 00"]


def test_remontar_sem_mexer_nas_folhas_continua_igual():
    from nucleo2d import ajustes_pranchas as AJ
    antigo = _montagem()
    antigo.metadados["geracao"] = "g1"
    ajustes = AJ.aprender(antigo, {"impressoes": {"g1": AJ.marcar(antigo)}})
    assert not ajustes.get("celulas") and not ajustes.get("folhas_apagadas")
    novo = _montagem()
    AJ.marcar(novo)
    AJ.aplicar(novo, ajustes)
    assert [_onde(novo, c) for c in ("c1", "c2", "c3")] == [(1, 100), (2, 100), (3, 100)]
