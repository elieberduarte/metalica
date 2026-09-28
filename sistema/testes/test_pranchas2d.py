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
    # (modelo da fábrica: valores em maiúsculas, "PRANCHA 01/01" na caixa do conteúdo)
    assert "OBRA X" in textos and "PRANCHA 01/01" in textos and any("1:10" in t for t in textos)
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


def test_filtro_de_chaves_e_conteudo():
    d = _detalhe(n_celulas=3)
    d.metadados["detalhamento"] = {"itens": {"P%d" % i: {"quantidade": 4, "perfil": "PLATE 100x50x3", "comprimento": 1200,
                                                          "espessura": 3.0, "peso": 1.5, "classe": "Chapa"} for i in (1, 2, 3)}}
    folhas = pranchas.montar_pranchas([{"nome": "det", "desenho": d, "chaves": ["P2"]}], formato="A3")
    cels = folhas[0].metadados["prancha"]["celulas"]
    assert [c["titulo"] for c in cels] == ["P2 – 04x"]
    # a caixa CONTEÚDO do carimbo lista o que está na folha, com a quantidade
    conteudo = " ".join(e.texto for e in folhas[0].entidades.values() if isinstance(e, Texto) and e.atributos.get("campo") == "conteudo")
    assert "P2 (04X)" in conteudo and "P1" not in conteudo


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



def test_prancha_de_indice():
    """Com índice, a prancha 01 relaciona as pranchas e lista todas as posições com o
    número da prancha em que estão; sem índice, a numeração começa no conteúdo."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_detalhar2d import _modelo
    from nucleo2d import detalhar as det
    from nucleo2d.pranchas import montar_pranchas
    from nucleo2d.desenho import Texto
    doc = _modelo()
    r = det.detalhar(doc, grupos=["chapas", "barras"], regra_tercas=False, converter=False)
    fontes = [{"nome": k, "desenho": d} for k, d in r["desenhos"].items()]
    folhas = montar_pranchas(fontes, formato="A1", titulo="Prancha", indice=True)
    assert folhas[0].nome == "Prancha 01" and folhas[0].metadados["prancha"]["indice"] is True
    assert folhas[0].metadados["prancha"]["total"] == len(folhas) and folhas[1].metadados["prancha"]["numero"] == 2
    textos = [e.texto for e in folhas[0].entidades.values() if isinstance(e, Texto)]
    assert any(t.startswith("Prancha 02/") for t in textos)
    assert any(t == "P1" for t in textos) and any(t == "M5" for t in textos)   # marcas na tabela
    assert any(t == "02" for t in textos)                                       # coluna da prancha
    sem = montar_pranchas(fontes, formato="A1", titulo="Prancha", indice=False)
    assert sem[0].metadados["prancha"]["numero"] == 1 and len(sem) == len(folhas) - 1


def test_folha_posta_no_desenho_vira_prancha_com_o_que_esta_dentro():
    """o caminho manual: a folha entra no desenho de trabalho na escala dele; o que está inteiro
    dentro da borda vai para a prancha, reduzido; o que está fora, não; a folha copiada é outra"""
    import copy
    from nucleo2d import pranchas as P
    from nucleo2d.desenho import Desenho, Linha, Texto
    d = Desenho(nome="Detalhamento – tesouras", escala=25.0)
    f = P.folha_no_desenho("A1", 25.0, (10000.0, 0.0), {"obra": "X"}, titulo="TESOURAS")
    assert f.metadados["folha"]["tamanho"] == [841.0 * 25, 594.0 * 25]
    for e in f.entidades.values():
        d.add(e)
    dentro = d.add(Linha(camada="0", a=(12000.0, 5000.0), b=(15000.0, 5000.0)))
    d.add(Texto(camada="0", posicao=(12000.0, 6000.0), texto="P1", altura=2.5))
    d.add(Linha(camada="0", a=(0.0, 0.0), b=(100.0, 100.0)))                  # fora da folha
    ps = P.pranchas_das_folhas(d, "detalhamento-tesouras", {"obra": "X"}, primeira=3)
    assert [p.nome for p in ps] == ["Prancha 03"]
    pr = ps[0]
    assert pr.metadados["prancha"]["entidades_do_desenho"] == 2
    linha = next(e for e in pr.entidades.values() if (e.atributos or {}).get("fonte") == "detalhamento-tesouras" and e.tipo == "linha")
    assert linha.a == ((12000.0 - 10000.0) / 25.0, 5000.0 / 25.0) and dentro.a == (12000.0, 5000.0)
    # a folha copiada (mesmo id, outro grupo de cópia) é outra folha
    for e in list(f.entidades.values()):
        c = copy.deepcopy(e)
        c.id = type(e)().id
        c.atributos = dict(c.atributos, grupo_copia="c1")
        d.add(c)
    assert len(P.pranchas_das_folhas(d, "x", {})) == 2


def test_gerar_de_novo_mantem_a_montagem_das_folhas():
    """gerar o detalhamento de novo não apaga as pranchas montadas (pergunta do usuário, 28/09): a
    folha fica; a célula movida para dentro dela volta atualizada no mesmo lugar (e sai do lugar
    padrão); a copiada fica nos dois; a peça que saiu do modelo fica como antes; o desenhado à mão fica"""
    from nucleo2d import pranchas as P
    from nucleo2d.desenho import Desenho, Linha, Texto

    def celula(d, marca, x, y, larg, grupo=""):
        atr = {"detalhe": "conjunto", "conjunto": marca, "faixa": "tesouras"}
        if grupo:
            atr["grupo_copia"] = grupo
        d.add(Linha(camada="BANZOS", a=(x, y), b=(x + larg, y), atributos=dict(atr)))
        d.add(Linha(camada="BANZOS", a=(x, y), b=(x + larg / 2, y + 1000.0), atributos=dict(atr)))
        d.add(Linha(camada="MONTANTES", a=(x + 1000.0, y), b=(x + 1000.0, y + 800.0), atributos=dict(atr)))   # não muda
        d.add(Texto(camada="TEXTO", posicao=(x, y + 1500.0), texto=marca, altura=2.5, atributos=dict(atr)))

    antigo = Desenho(nome="Detalhamento – tesouras", escala=25.0)
    folha = P.folha_no_desenho("A1", 25.0, (30000.0, 0.0), {"obra": "X"}, titulo="TESOURAS")
    for e in folha.entidades.values():
        antigo.add(e)
    celula(antigo, "T1", 32000.0, 5000.0, 8000.0)                  # movida para a folha
    celula(antigo, "T2", 0.0, 10000.0, 8000.0)                     # no lugar padrão
    celula(antigo, "T2", 32000.0, 9000.0, 8000.0, grupo="c1")      # e uma cópia na folha
    celula(antigo, "T9", 42000.0, 5000.0, 3000.0)                  # saiu do modelo
    antigo.add(Texto(camada="TEXTO", posicao=(33000.0, 1000.0), texto="NOTA À MÃO", altura=2.5))
    novo = Desenho(nome="Detalhamento – tesouras", escala=25.0)
    celula(novo, "T1", 0.0, 0.0, 9000.0)                           # a T1 mudou: 9 m
    celula(novo, "T2", 0.0, 10000.0, 8000.0)

    rel = P.manter_montagem(antigo, novo)
    assert rel["folhas"] == 1 and rel["atualizadas"] == 2 and rel["sem_modelo"] == ["T9"] and rel["a_mao"] == 1
    t1 = [e for e in novo.entidades.values() if (e.atributos or {}).get("conjunto") == "T1" and e.tipo == "linha"]
    assert len(t1) == 3                                             # só a da folha (a padrão saiu)
    base = next(e for e in t1 if e.a[1] == e.b[1])
    assert base.a == (32000.0, 5000.0) and base.b == (41000.0, 5000.0)   # a nova (9 m), no canto da antiga
    t2 = [e for e in novo.entidades.values() if (e.atributos or {}).get("conjunto") == "T2" and e.tipo == "linha"]
    assert len(t2) == 6                                             # a padrão e a cópia na folha
    assert any((e.atributos or {}).get("grupo_copia") == "c1" and e.a == (32000.0, 9000.0) for e in t2)
    assert any((e.atributos or {}).get("conjunto") == "T9" for e in novo.entidades.values())
    assert sum(1 for e in novo.entidades.values() if (e.atributos or {}).get("folha")) == len(folha.entidades)
    assert any(getattr(e, "texto", "") == "NOTA À MÃO" for e in novo.entidades.values())
    # e a prancha sai da folha com as células novas
    ps = P.pranchas_das_folhas(novo, "detalhamento-tesouras", {"obra": "X"})
    assert ps[0].metadados["prancha"]["entidades_do_desenho"] == 4 + 4 + 4 + 1


def test_gerar_de_novo_sem_montagem_nao_mexe():
    from nucleo2d import pranchas as P
    from nucleo2d.desenho import Desenho, Linha
    antigo = Desenho(nome="d", escala=25.0)
    antigo.add(Linha(camada="0", a=(0, 0), b=(1, 0), atributos={"detalhe": "conjunto", "conjunto": "T1", "faixa": "x"}))
    novo = Desenho(nome="d", escala=25.0)
    novo.add(Linha(camada="0", a=(0, 0), b=(2, 0), atributos={"detalhe": "conjunto", "conjunto": "T1", "faixa": "x"}))
    assert P.manter_montagem(antigo, novo) == {"folhas": 0, "atualizadas": 0, "sem_modelo": [], "a_mao": 0}
    assert len(novo.entidades) == 1

