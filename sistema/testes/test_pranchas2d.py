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
        # a cota por cima da peça (dentro da caixa): a que fica por baixo alarga a célula (teste próprio)
        d.add(Cota(modo="h", p1=(x, 0), p2=(x + larg, 0), deslocamento=10, atributos=dict(atr)))
        d.add(Texto(posicao=(x, 700), texto="P%d – 04x" % (i + 1), altura=3.5, atributos=dict(atr)))
        d.metadados.setdefault("celulas", []).append([x, -150, x + larg, 750])
        x += larg + 400
    return d


def test_caixa_da_celula_inclui_a_linha_de_cota():
    """A caixa da célula conta a linha de cota deslocada e o número dela (revisão de 28/09: a
    cadeia de cotas sob a terça invadia o título da linha de baixo da prancha)."""
    c = Cota(modo="h", p1=(0, 0), p2=(1000, 0), deslocamento=-10, altura=2.5)
    (x0, y0), (x1, y1) = pranchas._caixa_de([c], 10.0)
    assert (x0, x1, y1) == (0, 1000, 0)
    assert abs(y0 - (-(10 + 2 + 2.5 + 1) * 10)) < 1e-6
    c2 = Cota(modo="v", p1=(0, 0), p2=(0, 500), deslocamento=8, altura=2.5)
    (x0, y0), (x1, y1) = pranchas._caixa_de([c2], 10.0)
    assert x1 == 0 and abs(x0 - (-(8 + 5.5) * 10)) < 1e-6


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
    """Com índice, a relação das pranchas vai na faixa livre ao lado do carimbo da prancha 01 (pedido
    do usuário, 28/09) — sem folha de índice separada; a numeração começa no conteúdo."""
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
    pr = folhas[0].metadados["prancha"]
    assert folhas[0].nome == "Prancha 01" and not pr["relacao"] and pr["celulas"] and pr["numero"] == 1
    assert pr["total"] == len(folhas)
    # a legenda é só do que está na prancha (pedido do usuário, 28/09): sem a relação das pranchas
    leg = [e for e in folhas[0].entidades.values() if isinstance(e, Texto) and (e.atributos or {}).get("prancha") == "legenda"]
    assert not any(e.texto == "RELAÇÃO DAS PRANCHAS" for e in leg)
    assert not any(e.texto == "01/%02d" % len(folhas) for e in leg)
    # a legenda, no quadro LEGENDA, fica na faixa ao lado do carimbo
    from nucleo2d.pranchas import FOLHAS, CARIMBO, MARGENS
    larg, _alt = FOLHAS["A1"]
    lim_x, lim_y = larg - MARGENS["direita"] - CARIMBO["A1"][0], MARGENS["inferior"] + CARIMBO["A1"][1]
    assert all(t.posicao[0] < lim_x and t.posicao[1] + t.altura <= lim_y for t in leg)
    sem = montar_pranchas(fontes, formato="A1", titulo="Prancha", indice=False)
    assert len(sem) == len(folhas) and not sem[0].metadados["prancha"].get("relacao")


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


def test_carimbo_editado_na_folha_vai_para_a_prancha():
    """os textos do carimbo mudados no CAD (obra, projetista, revisão, conteúdo) são os da prancha
    (pedido do usuário, 28/09); antes a prancha reescrevia com os dados do projeto e o conteúdo "-" """
    from nucleo2d import pranchas as P
    from nucleo2d.desenho import Desenho, Texto
    d = Desenho(nome="Detalhamento – tesouras", escala=25.0)
    f = P.folha_no_desenho("A1", 25.0, (0.0, 0.0), {"obra": "X", "responsavel": "Y"}, titulo="T")
    for e in f.entidades.values():
        a = e.atributos or {}
        if isinstance(e, Texto) and a.get("campo") == "obra":
            e.texto = "OBRA EDITADA"
        if isinstance(e, Texto) and a.get("campo") == "prancha":
            e.texto = "PRANCHA 01/01   REV. 03"
        d.add(e)
    base = next(e for e in d.entidades.values() if isinstance(e, Texto) and (e.atributos or {}).get("campo") == "conteudo")
    base.texto = "TESOURAS T1 E T2"
    ps = P.pranchas_das_folhas(d, "detalhamento-tesouras", {"obra": "DO PROJETO"})
    txt = {(e.atributos or {}).get("campo"): e.texto for e in ps[0].entidades.values() if isinstance(e, Texto)}
    assert txt["obra"] == "OBRA EDITADA" and txt["conteudo"] == "TESOURAS T1 E T2"
    assert "REV. 03" in txt["prancha"]

def test_pranchas_lado_a_lado_num_desenho_so(tmp_path):
    """As pranchas juntas num desenho só, em papel 1:1 (pedido do usuário, 28/09): cada folha
    deslocada para a direita da anterior, com a moldura marcada com `folha` (o clique pega a folha
    inteira, o carimbo edita como na folha do desenho de trabalho) e `metadados.pranchas` com a
    origem de cada uma; o PDF sai uma página por folha, cada uma só com o que é dela."""
    import pymupdf
    folhas = pranchas.montar_pranchas([{"nome": "det", "desenho": _detalhe()}], formato="A3", titulo="Prancha",
                                      carimbo={"obra": "OBRA PRIMEIRA"})
    folhas += pranchas.montar_pranchas([{"nome": "det", "desenho": _detalhe()}], formato="A3", titulo="Prancha",
                                       carimbo={"obra": "OBRA SEGUNDA"})
    for i, f in enumerate(folhas, start=1):
        f.metadados["prancha"].update(numero=i, total=2)
    assert len(folhas) == 2
    junto = pranchas.juntar_pranchas(folhas, nome="Pranchas")
    larg, alt = pranchas.FOLHAS["A3"]
    meta = junto.metadados["pranchas"]
    assert [m["numero"] for m in meta] == [1, 2] and meta[0]["origem"] == [0.0, 0.0]
    assert abs(meta[1]["origem"][0] - (larg + pranchas.FOLGA_ENTRE_FOLHAS)) < 1e-6
    assert junto.tamanho == sum(f.tamanho for f in folhas)
    x0 = meta[1]["origem"][0]
    seg = [e for e in junto.entidades.values() if e.atributos.get("prancha_numero") == 2]
    assert seg and all(x0 - 0.01 <= p[0] <= x0 + larg + 0.01 for e in seg for p in e.pontos())
    molduras = {e.atributos.get("folha") for e in seg if e.atributos.get("prancha") == "moldura"}
    assert molduras == {meta[1]["folha"]}
    assert len(pranchas._folhas_do(junto)) == 2
    # a caixa da célula acompanha a folha
    cel = meta[1]["celulas"][0]["caixa"]
    assert x0 <= cel[0] <= cel[2] <= x0 + larg
    # grava e lê de volta
    d2 = Desenho.de_dict(junto.dict())
    assert d2.tamanho == junto.tamanho and len(d2.metadados["pranchas"]) == 2
    # o PDF: uma página por folha, no tamanho do papel, cada uma com o seu conteúdo
    assert len(pranchas.paginas_de(junto)) == 2
    doc = pymupdf.open(pranchas.pdf_dos_desenhos([junto], str(tmp_path / "p.pdf")))
    assert len(doc) == 2
    assert abs(doc[1].rect.width / 72 * 25.4 - larg) < 1
    assert "OBRA SEGUNDA" in doc[1].get_text() and "OBRA SEGUNDA" not in doc[0].get_text()
    assert "OBRA PRIMEIRA" in doc[0].get_text() and "OBRA PRIMEIRA" not in doc[1].get_text()

def test_gerar_pranchas_das_folhas_junta_num_desenho_so(tmp_path, monkeypatch):
    """O caminho à mão pelo app (28/09): as folhas de cada desenho de trabalho viram pranchas lado
    a lado num desenho só ("Pranchas"); as geradas antes de outro desenho ficam, na ordem, e as do
    desenho atual são refeitas, com a numeração correndo por todas. O desenho das pranchas não
    serve de fonte, e o PDF dele sai uma página por folha."""
    import pytest
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    r = g.criar("Obra teste", tipo="ifc")
    s = r.get("slug") or r.get("id") or r.get("nome")

    def com_folhas(nome, n):
        d = Desenho(nome=nome, escala=10.0)
        x = 0.0
        for i in range(n):
            f = pranchas.folha_no_desenho("A4", 10.0, (x, 0.0), {"obra": "Obra"}, titulo="%s %d" % (nome, i + 1))
            d.camadas.update(f.camadas)
            for e in f.entidades.values():
                d.add(e)
            d.add(Linha(a=(x + 500, 500), b=(x + 1500, 500)))
            x += 297 * 10 + 500
        return d
    g.salvar_desenho(s, "trabalho-a", com_folhas("A", 2).dict())
    g.salvar_desenho(s, "trabalho-b", com_folhas("B", 1).dict())
    r1 = app.pranchas_das_folhas(s, "trabalho-a", {})
    assert r1["desenho"] == "pranchas" and [p["numero"] for p in r1["pranchas"]] == [1, 2]
    r2 = app.pranchas_das_folhas(s, "trabalho-b", {})
    assert [(p["fonte"], p["numero"]) for p in r2["pranchas"]] == [("trabalho-a", 1), ("trabalho-a", 2), ("trabalho-b", 3)]
    j = g.abrir_desenho(s, "pranchas")
    assert len(j["metadados"]["pranchas"]) == 3 and j["metadados"]["gerado_por"] == "folhas"
    assert all(p["do_desenho"] == 1 for p in r2["pranchas"])
    # o A refeito com uma folha só: o B fica, e a numeração corre de novo
    g.salvar_desenho(s, "trabalho-a", com_folhas("A", 1).dict())
    r3 = app.pranchas_das_folhas(s, "trabalho-a", {})
    assert [(p["fonte"], p["numero"]) for p in r3["pranchas"]] == [("trabalho-b", 1), ("trabalho-a", 2)]
    assert [d["nome"] for d in g.listar_desenhos(s) if d.get("pranchas")] == ["pranchas"]
    with pytest.raises(ErroDeDados):
        app.pranchas_das_folhas(s, "pranchas", {})
    with pytest.raises(ErroDeDados):
        app.montar_pranchas_projeto(s, {"desenhos": ["pranchas"]})
    assert app.exportar_desenho_pdf(s, "pranchas", {})["paginas"] == 2



def test_siglas_da_relacao():
    """A relação das pranchas explica as siglas que aparecem nelas (pedido do usuário, 28/09): a mais
    longa que começa o nome e vem antes do número — T.C.1 é terça de cobertura, T1 é tesoura."""
    from nucleo2d.pranchas import siglas_usadas
    s = dict(siglas_usadas(["T1 – 03x", "A.D.1 / A.D.2", "T.C.1", "CH4 – 28x", "TMD.1", "PLANTA DE CHUMBAÇÃO"]))
    assert set(s) == {"T", "A.D.", "T.C.", "CH", "TMD"}
    assert s["T.C."] == "Terça de cobertura" and s["A.D."] == "Agulhamento diagonal" and s["TMD"] == "Telha multi-dobra"


def test_faixa_ao_lado_do_carimbo_recebe_celulas_pequenas():
    """A faixa ao lado do carimbo, embaixo, recebe as células pequenas da fila em toda prancha
    (pedido do usuário, 28/09) — sem invadir o carimbo; com o índice, a primeira fica com a relação."""
    d = _detalhe(n_celulas=120, larg=300.0, escala=50.0)
    larg, _alt = pranchas.FOLHAS["A3"]
    lc, ac = pranchas.CARIMBO["A3"]
    x_carimbo = larg - pranchas.MARGENS["direita"] - lc
    y_faixa = pranchas.MARGENS["inferior"] + ac
    for indice in (False, True):
        folhas = pranchas.montar_pranchas([{"nome": "det", "desenho": d}], formato="A3", indice=indice)
        assert sum(len(f.metadados["prancha"]["celulas"]) for f in folhas) == 120
        for i, f in enumerate(folhas):
            na_faixa = [c for c in f.metadados["prancha"]["celulas"] if c["caixa"][3] <= y_faixa + 0.01]
            assert all(c["caixa"][2] <= x_carimbo for c in na_faixa)
            if i < len(folhas) - 1:
                assert na_faixa, "os DETALHES da prancha %d ficaram vazios" % (i + 1)
            legenda = [t for t in f.entidades.values() if isinstance(t, Texto) and (t.atributos or {}).get("prancha") == "legenda"]
            assert all(t.posicao[0] < x_carimbo and t.posicao[1] < y_faixa for t in legenda)
            assert not any(t.texto == "RELAÇÃO DAS PRANCHAS" for t in legenda)   # a legenda é só da prancha


def test_legenda_nunca_passa_da_caixa():
    """A legenda cabe na largura dada: as siglas ficam inteiras e a relação das pranchas perde colunas,
    com "… +N" na última linha (a Sala com o desenho completo junto dava 29 pranchas e a legenda
    invadia o carimbo — 28/09)."""
    from nucleo2d.desenho import Desenho
    leg = {"relacao": True, "blocos": [("SIGLAS", [("T", "Tesoura"), ("CH", "Chapa")])], "n_rel": 1}
    rel = [("%02d/60" % i, "VISTAS: completo, localização, chaparias") for i in range(1, 61)]
    d = Desenho(nome="t", escala=1.0)
    w = pranchas._legenda(d, leg, 0.0, 0.0, 90.0, rel, {}, largura=150.0)
    assert w <= 150.0 + 0.01
    textos = [e.texto for e in d.entidades.values()]
    assert "SIGLAS" in textos and "Tesoura" in textos and any(t.startswith("+") for t in textos)


def test_chapas_da_tesoura_na_prancha_dela_com_a_quantidade_dela():
    """Na prancha da tesoura, as chapas dela e os chumbamentos vão para os DETALHES (ou para o canto livre
    do quadro) com quantas estão desenhadas ali; o total da obra fica na prancha das chapas (pedido do
    usuário, 28/09). Os detalhes de furos das barras vão junto da tesoura, fora da célula dela; a legenda
    é NESTA PRANCHA + SIGLAS; a chamada de uma chapa detalhada na própria prancha não leva "– PR.xx"."""
    import os
    import re
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_detalhar2d import _modelo_real
    from nucleo2d import detalhar as det
    from nucleo2d.pranchas import montar_pranchas
    from nucleo2d.desenho import Chamada, Texto
    doc = _modelo_real()
    r = det.detalhar(doc, grupos=["tesouras", "chaparias"], converter=False)
    fontes = [{"nome": "detalhamento-" + k, "desenho": d} for k, d in r["desenhos"].items()]
    folhas = montar_pranchas(fontes, formato="A1")
    tit = [[c["titulo"] for c in f.metadados["prancha"]["celulas"]] for f in folhas]
    p1 = tit[0]
    assert any(t.startswith("T1 ") for t in p1)
    # as chapas da prancha 01 com a quantidade dela (a das tesouras desenhadas ali); o total da obra, na
    # prancha das chapas — cada uma aparece de novo lá, com quantidade maior ou igual
    q1 = {t.split(" – ")[0]: int(t.split(" – ")[1].rstrip("x")) for t in p1 if re.match(r"(CH|CB)\d", t) and " – " in t}
    assert len(q1) >= 3, p1
    total = {}
    for ts in tit[1:]:
        for t in ts:
            if " – " in t and t.split(" – ")[0] in q1:
                total[t.split(" – ")[0]] = int(t.split(" – ")[1].rstrip("x"))
    assert total and all(q1[n] <= total[n] for n in total), (q1, total)
    assert any(q1[n] < total[n] for n in total), (q1, total)
    # a chamada de uma chapa detalhada na prancha 01 não aponta outra prancha
    ch = [e.texto for e in folhas[0].entidades.values() if isinstance(e, Chamada)]
    locais = [n for n in q1 if n.startswith("CH") and " + " not in n and n in ch]
    assert locais and not any(t.startswith(locais[0] + " – PR.") for t in ch), (locais, ch)
    # a legenda: nome e quantidade desta prancha e as siglas
    leg = [e.texto for e in folhas[0].entidades.values() if isinstance(e, Texto) and (e.atributos or {}).get("prancha") == "legenda"]
    assert "NESTA PRANCHA" in leg and "SIGLAS" in leg
    assert not any(t.startswith("PEÇAS DE") for t in leg)
    # os detalhes de furos das barras: na prancha da tesoura dona deles
    furos = [(i, t) for i, ts in enumerate(tit) for t in ts if re.match(r"DETALHE [A-Z] – FUROS DE", t)]
    assert furos and all(any(x.startswith(("T1 ", "T2 ", "T3 ", "T4 ")) for x in tit[i]) for i, _t in furos)
    # no quadro da tesoura (não na faixa), com a linha de chamada até a marca dos furos (28/09)
    from nucleo2d.desenho import Linha
    for i, _t in furos:
        assert any(isinstance(e, Linha) and (e.atributos or {}).get("prancha") == "chamada_furos" for e in folhas[i].entidades.values())
    # as chapas de uma montagem de chapas da prancha não saem soltas (a montagem já as cota); a do
    # chumbamento vai junto das vistas dele, logo ao lado ou embaixo (28/09)
    cels1 = folhas[0].metadados["prancha"]["celulas"]
    for t in p1:
        nome_m = t.split(" – ")[0]
        if " + " in nome_m and not nome_m.startswith("CB"):
            assert not any(x.split(" – ")[0] in nome_m.split(" + ") for x in p1), (nome_m, p1)
        if nome_m.startswith("CB") and " + " in nome_m:
            cb = next(c for c in cels1 if c["titulo"] == t)
            ch = next((c for c in cels1 if c["titulo"].split(" – ")[0] == nome_m.split(" + ")[1]), None)
            assert ch is not None, (nome_m, p1)
            perto = abs(ch["caixa"][0] - cb["caixa"][2]) < 12.0 or abs(ch["caixa"][3] - cb["caixa"][1]) < 12.0
            assert perto, (cb, ch)
    # a faixa de baixo: ACESSÓRIOS/DISPOSITIVOS
    assert any(isinstance(e, Texto) and e.texto == "ACESSÓRIOS/DISPOSITIVOS" for e in folhas[0].entidades.values())


def test_contraventos_e_conjuntos_lado_a_lado():
    """Contraventos e agulhamentos (CV., A.C., A.L., A.D.) num quadro, os conjuntos (DP.) em outro, lado a
    lado na mesma prancha quando cabem; a diagonal do DP com o perfil escrito (pedidos do usuário, 28/09)."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_detalhar2d import _modelo_real
    from nucleo2d import detalhar as det
    from nucleo2d.pranchas import montar_pranchas
    from nucleo2d.desenho import Texto
    doc = _modelo_real()
    r = det.detalhar(doc, grupos=["conjuntos", "contraventamentos", "agulhamentos"], converter=False)
    fontes = [{"nome": "detalhamento-" + k, "desenho": d} for k, d in r["desenhos"].items()]
    folhas = montar_pranchas(fontes, formato="A1")
    titulos = [{e.texto for e in f.entidades.values() if isinstance(e, Texto) and (e.atributos or {}).get("campo") == "titulo"}
               for f in folhas]
    todas = set().union(*titulos)
    if "CONTRAVENTOS E AGULHAMENTOS" in todas and any(t.startswith("CONJUNTOS MENORES") for t in todas):
        assert any("CONTRAVENTOS E AGULHAMENTOS" in t_ and any(x.startswith("CONJUNTOS MENORES") for x in t_) for t_ in titulos)
    # a diagonal do DP com o perfil cheio (as duas bordas), não só a linha de eixo
    from nucleo2d.desenho import Linha, Polilinha
    itens_dp = {m: it for d in r["desenhos"].values() for m, it in ((d.metadados.get("detalhamento") or {}).get("itens") or {}).items()
                if str(it.get("nome") or "").startswith("DP.")}
    for marca_dp in itens_dp:
        linhas_d = [e for d in r["desenhos"].values() for e in d.entidades.values()
                    if isinstance(e, (Linha, Polilinha)) and str(e.camada).startswith("DIAGONAIS")
                    and (e.atributos or {}).get("conjunto") == marca_dp]
        n_diag = sum(x["qtd"] for x in itens_dp[marca_dp].get("composicao") or [] if str(x.get("perfil") or "").upper().startswith("U92"))
        if n_diag:
            assert len(linhas_d) >= 2 * n_diag, (marca_dp, len(linhas_d), n_diag)


def test_agulhamentos_de_cantoneira_num_detalhe_tipico():
    """Os agulhamentos de cantoneira (A.L., A.C. — e o conjunto que usa a barra deles, como o DP.1 da Sala)
    num detalhe típico só, como as A.D., e as barras deles fora da prancha de barras (pedido do usuário, 28/09)."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_detalhar2d import _modelo_real
    from nucleo2d import detalhar as det
    doc = _modelo_real()
    r = det.detalhar(doc, grupos=["conjuntos", "agulhamentos", "extras"], converter=False)
    itens_c = (r["desenhos"]["conjuntos"].metadados.get("detalhamento") or {}).get("itens") or {}
    nomes_c = [str(it.get("nome") or "") for it in itens_c.values()]
    grupos = [n for n in nomes_c if " / " in n and any(p.startswith(("A.L.", "A.C.")) for p in n.split(" / "))]
    soltos = [n for n in nomes_c if " / " not in n and n.startswith(("A.L.", "A.C.")) and (itens_c and True)]
    if not grupos and not soltos:
        return                                         # o modelo de exemplo não tem agulhamento de cantoneira
    assert grupos, nomes_c
    # as barras que o detalhe típico lista ("Barra L1.1/4''X1/8'': A.C.1, A.L.3, A.L.2.1") não têm célula nas barras
    from nucleo2d.desenho import Texto
    barras_do_grupo = set()
    for e in (e_ for d_ in r["desenhos"].values() for e_ in d_.entidades.values()):
        if isinstance(e, Texto) and e.texto.startswith("Barra ") and any(n.startswith(("A.L.", "A.C.")) for n in e.texto.split(": ")[-1].split(", ")):
            barras_do_grupo |= {n.strip() for n in e.texto.split(": ")[-1].split(",")}
    assert barras_do_grupo
    # nos desenhos por família (os das pranchas), nenhuma célula dessas barras
    from nucleo2d.pranchas import celulas_de
    nomes_cel = []
    for k, d_ in r["desenhos"].items():
        if k in ("barras", "completo"):
            continue                                   # o desenho por classe, que as pranchas não usam
        its = (d_.metadados.get("detalhamento") or {}).get("itens") or {}
        nomes_cel += [str((its.get(c["chave"][1]) or {}).get("nome") or "") for c in celulas_de(d_, k) if c.get("chave")]
    assert nomes_cel and not any(n in barras_do_grupo for n in nomes_cel), nomes_cel


def test_tercas_alinhadas_e_suportes_na_faixa():
    """Terças em colunas alinhadas (o mesmo x no começo de cada coluna) e, na faixa de baixo, os suportes
    de terça — terça nenhuma (pedido do usuário, 28/09)."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_detalhar2d import _modelo_real
    from nucleo2d import detalhar as det
    from nucleo2d.pranchas import montar_pranchas, MARGENS, CARIMBO
    doc = _modelo_real()
    r = det.detalhar(doc, grupos=["tercas"], converter=False)
    fontes = [{"nome": "detalhamento-" + k, "desenho": d} for k, d in r["desenhos"].items()]
    folhas = montar_pranchas(fontes, formato="A1")
    y_faixa = MARGENS["inferior"] + CARIMBO["A1"][1]
    for f in folhas:
        cels = f.metadados["prancha"]["celulas"]
        ter = [c for c in cels if (c.get("item") or {}).get("categoria") == "TERÇAS"]
        assert not any(c["caixa"][3] <= y_faixa + 0.01 for c in ter), "terça na faixa de baixo"
        xs = sorted({round(c["caixa"][0], 1) for c in ter})
        assert len(xs) <= 2, xs                       # duas colunas, cada uma num x só


def test_prancha_dos_chumbadores():
    """A planta de locação dos chumbadores reduzida à esquerda e, à direita, as chapas e as barras de
    chumbamento — a primeira prancha da obra (pedido do usuário, 28/09)."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_detalhar2d import _modelo_real
    from nucleo2d import detalhar as det
    from nucleo2d.pranchas import montar_pranchas
    from nucleo2d.desenho import Texto
    doc = _modelo_real()
    r = det.detalhar(doc, grupos=["chumbacao", "chaparias", "extras"], converter=False)
    if "chumbacao" not in r["desenhos"]:
        return
    fontes = [{"nome": "detalhamento-" + k, "desenho": d} for k, d in r["desenhos"].items()]
    folhas = montar_pranchas(fontes, formato="A1")
    tit = {e.texto for e in folhas[0].entidades.values() if isinstance(e, Texto) and (e.atributos or {}).get("campo") == "titulo"}
    assert "PLANTA DE LOCAÇÃO DOS CHUMBADORES" in tit
    cels = [c["titulo"] for c in folhas[0].metadados["prancha"]["celulas"]]
    if any(t.startswith("CB") for f in folhas for t in (c["titulo"] for c in f.metadados["prancha"]["celulas"])):
        assert "CHUMBAMENTO – CHAPAS E BARRAS" in tit and any(t.startswith("CB") for t in cels), cels
