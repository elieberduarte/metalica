# -*- coding: utf-8 -*-
"""A gestão das impressões (usuário, 12/11, no Vicente Residence: "precisamos melhorar a ferramenta de gestão das
impressões"; a tela A aprovada, Projeto/ANALISES/Interface/Impressao-gerenciador-proposta-2026-11-12.pdf): a escala e a
revisão de cada folha, a situação (nunca impressa, impressa, mudou depois) pela assinatura do que está na moldura dela,
o histórico e os conjuntos de folhas no projeto (nucleo2d/impressoes.py), o papel escolhido por folha
(saida/impressao.py) e o título curto da folha cortado numa palavra inteira (nucleo2d/pranchas.titulo_curto — o
"Planta de locação dos chumbadores, Chumbamento –" das pranchas do Vicente). A tela está no verif_impressao_ui."""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import impressoes, pranchas                                       # noqa: E402
from nucleo2d.desenho import Desenho, Linha, Texto                              # noqa: E402
from saida import impressao                                                     # noqa: E402

MM = 72 / 25.4


# ------------------------------------------------------------------ o título curto
def test_titulo_curto_nao_corta_no_meio():
    """Vicente, folha 03: as 48 letras cortavam "…, Chumbamento – chapas e barras" no travessão"""
    t = pranchas.titulo_curto("Planta de locação dos chumbadores, Chumbamento – chapas e barras")
    assert t == "Planta de locação dos chumbadores, Chumbamento…" and len(t) <= pranchas.TITULO_MAX
    assert pranchas.titulo_curto("Conjuntos menores, Chumbamento – chapas e barras") == "Conjuntos menores, Chumbamento – chapas e barras"
    assert pranchas.titulo_curto("Localização") == "Localização"
    assert len(pranchas.titulo_curto("A" * 60)) == pranchas.TITULO_MAX
    assert not pranchas.titulo_curto("Vigas caixote, Conjuntos menores, Chumbamento – chapas, Barras").rstrip("…").endswith(("–", ","))


def test_fontes_titulo_usa_o_corte_inteiro():
    cels = [{"fonte": "Planta de locação dos chumbadores"}, {"fonte": "Chumbamento – chapas e barras"}]
    assert pranchas.fontes_titulo(cels) == "Planta de locação dos chumbadores, Chumbamento…"


# ------------------------------------------------------------------ escala, revisão, situação
def test_escala_da_folha():
    cel = lambda *ks: {"celulas": [{"escala": k} for k in ks]}
    assert impressoes.escala_da_folha(cel(25, 25, 10)) == "1:25 / 1:10"
    assert impressoes.escala_da_folha(cel(50)) == "1:50"
    assert impressoes.escala_da_folha(cel(25, 10, 100)) == "várias"
    assert impressoes.escala_da_folha({"celulas": [], "escala": 20}) == "1:20"
    assert impressoes.escala_da_folha({}) == ""


def test_revisao_da_folha():
    revs = {"3": [{"rev": "00", "descricao": "EMISSÃO INICIAL"}, {"rev": "02", "descricao": "chumbação"}]}
    assert impressoes.revisao_da_folha(revs, 3) == "02"
    assert impressoes.revisao_da_folha(revs, 4) == "" and impressoes.revisao_da_folha(revs, None) == ""


SITUACOES = [(0.0, 0.0), (1218181.0, 211836.0)]


def _duas_folhas(ox, oy):
    """Duas folhas A1 lado a lado (como o Montar pranchas deixa), com uma linha e um texto em cada."""
    ents = []
    folhas = []
    for i in range(2):
        x0 = ox + i * 900.0
        folhas.append({"numero": i + 1, "origem": [x0, oy], "tamanho": [841.0, 594.0]})
        ents += [{"id": "l%d" % i, "tipo": "linha", "camada": "VISTA", "a": [x0 + 10, oy + 10], "b": [x0 + 300, oy + 10]},
                 {"id": "t%d" % i, "tipo": "texto", "camada": "TEXTO", "posicao": [x0 + 50, oy + 50], "texto": "FOLHA %d" % (i + 1)}]
    return ents, folhas


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_assinatura_por_folha(ox, oy):
    ents, folhas = _duas_folhas(ox, oy)
    a = impressoes.assinaturas(ents, folhas)
    assert len(a) == 2 and a[0] != a[1]
    # os ids novos (montar de novo) não mudam a assinatura
    outro = [dict(e, id=e["id"] + "x") for e in ents]
    assert impressoes.assinaturas(outro, folhas) == a
    # mexer na folha 2 muda só a 2
    mudado = copy.deepcopy(ents)
    mudado[3]["texto"] = "FOLHA 2 REV"
    b = impressoes.assinaturas(mudado, folhas)
    assert b[0] == a[0] and b[1] != a[1]
    # a folha sem moldura (o desenho de uma folha só) leva tudo
    assert impressoes.assinaturas(ents, [{}])[0] == impressoes.assinaturas(list(reversed(ents))[::-1], [{}])[0]


def test_situacao_e_historico(tmp_path):
    pasta = str(tmp_path)
    ch = impressoes.chave("pranchas", 3)
    assert impressoes.situacao(impressoes.ler(pasta)["historico"], ch, "aaa") == {"estado": "nunca"}
    impressoes.registrar(pasta, r"\\192.168.0.218\HP403F7F (HP Designjet T120)",
                         [{"chave": ch, "desenho": "pranchas", "numero": 3, "titulo": "Planta", "revisao": "02", "assinatura": "aaa"}],
                         quando="2026-11-10T16:20:00")
    hist = impressoes.ler(pasta)["historico"]
    assert impressoes.situacao(hist, ch, "aaa") == {"estado": "impressa", "quando": "10/11", "onde": "plotter", "revisao": "02"}
    assert impressoes.situacao(hist, ch, "bbb")["estado"] == "mudou"
    assert impressoes.situacao(hist, impressoes.chave("pranchas", 4), "aaa")["estado"] == "nunca"
    # a última impressão vale
    impressoes.registrar(pasta, "Microsoft Print to PDF", [{"chave": ch, "assinatura": "bbb", "revisao": "03"}], quando="2026-11-12T08:00:00")
    s = impressoes.situacao(impressoes.ler(pasta)["historico"], ch, "bbb")
    assert s["estado"] == "impressa" and s["quando"] == "12/11" and s["onde"] == "Microsoft Print to PDF"


def test_conjuntos_validos():
    assert impressoes.conjuntos_validos({" Fabricação ": ["pranchas|4", "pranchas|5"], "": ["x"], "ruim": "x"}) == {"Fabricação": ["pranchas|4", "pranchas|5"]}
    assert impressoes.conjuntos_validos(None) == {}


def test_eh_plotter():
    assert impressoes.ehPlotter(r"\\192.168.0.218\HP403F7F (HP Designjet T120)")
    assert not impressoes.ehPlotter("Microsoft Print to PDF") and not impressoes.ehPlotter("OneNote (Desktop)")


# ------------------------------------------------------------------ o papel por folha
def test_ajuste_do_papel_escolhido():
    papeis = [{"id": 8, "nome": "A3", "largura": 297, "altura": 420}, {"id": 9, "nome": "A4", "largura": 210, "altura": 297}]
    assert impressao.ajuste_para(297, 210, papeis, 8) == "real"          # a A4 cabe na A3
    assert impressao.ajuste_para(841, 594, papeis, 8) == "ajustar"       # a A1 na A3: ajustada
    assert impressao.ajuste_para(841, 594, papeis, 99) == "ajustar"


def _com_pdf_do_windows():
    if sys.platform != "win32":
        return False
    try:
        return any(p["nome"] == "Microsoft Print to PDF" for p in impressao.impressoras()["impressoras"])
    except Exception:                                    # noqa: BLE001
        return False


@pytest.fixture(autouse=True)
def _sem_faulthandler():
    import faulthandler
    ligado = faulthandler.is_enabled()
    faulthandler.disable()
    yield
    if ligado:
        faulthandler.enable()


def _a4(i, n, escalas=()):
    d = Desenho(nome="Prancha %02d" % i, escala=1.0)
    d.add(Linha(a=(30, 30), b=(250, 30)))
    d.add(Texto(posicao=(40, 100), texto="FOLHA %d" % i, altura=10))
    d.metadados["prancha"] = {"formato": "A4", "numero": i, "total": n, "titulo": "FOLHA %d" % i,
                              "celulas": [{"escala": e} for e in escalas]}
    return d


@pytest.mark.skipif(not _com_pdf_do_windows(), reason="sem a Microsoft Print to PDF do Windows")
def test_rota_folhas_historico_papel_e_conjuntos(tmp_path, monkeypatch):
    """A rota do CAD: as folhas com escala, revisão e situação; imprimir as folhas 1 e 3 com a 3 no A3 (o papel dela)
    — no PDF da impressora a 1 sai A4 e a 3 A3 —, o histórico no projeto e a situação depois; a folha mudada no disco
    vira "mudou"; os conjuntos gravados e lidos."""
    import pymupdf
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    r = g.criar("Obra gestão", tipo="ifc")
    s = r.get("slug") or r.get("id") or r.get("nome")
    for i, esc in ((1, (25,)), (2, (50, 50, 10)), (3, ())):
        d = _a4(i, 3, esc)
        g.salvar_desenho(s, d.nome, d.dict())
    g._atualizar(s, carimbo_pranchas={"revisoes": {"3": [{"rev": "00", "descricao": "EMISSÃO INICIAL"}, {"rev": "01", "descricao": "x"}]}})
    nomes = sorted(d["nome"] for d in g.listar_desenhos(s))
    r = app.rota_impressao(s, "folhas", {"desenhos": nomes})
    f = r["folhas"]
    assert [x["escala"] for x in f] == ["1:25", "1:50 / 1:10", ""] and [x["revisao"] for x in f] == ["", "", "01"]
    assert all(x["situacao"] == {"estado": "nunca"} for x in f) and r["conjuntos"] == {}
    papel_a3 = next(pp["id"] for pp in impressao.papeis("Microsoft Print to PDF")["papeis"] if pp["nome"] == "A3")
    r = app.rota_impressao(s, "imprimir", {"desenhos": nomes, "impressora": "Microsoft Print to PDF", "folhas": [0, 2],
                                           "papeis": {"2": papel_a3}, "cor": "preto", "copias": 1})
    assert [x["papel"] for x in r["folhas"]] == ["A4", "A3"]
    arq = os.path.join(g._existente(s), "pranchas", r["arquivo"]["nome"])
    doc = pymupdf.open(arq)
    assert [round(pg.rect.width / MM) for pg in doc] == [297, 420]
    doc.close()
    f = app.rota_impressao(s, "folhas", {"desenhos": nomes})["folhas"]
    assert [x["situacao"]["estado"] for x in f] == ["impressa", "nunca", "impressa"] and f[2]["situacao"]["revisao"] == "01"
    # a folha 3 mudada no disco
    d3 = _a4(3, 3)
    d3.add(Texto(posicao=(60, 60), texto="NOTA NOVA", altura=5))
    g.salvar_desenho(s, d3.nome, d3.dict())
    f = app.rota_impressao(s, "folhas", {"desenhos": nomes})["folhas"]
    assert [x["situacao"]["estado"] for x in f] == ["impressa", "nunca", "mudou"]
    # os conjuntos
    c = app.rota_impressao(s, "conjuntos", {"conjuntos": {"Fabricação": [f[0]["chave"], f[2]["chave"]]}})["conjuntos"]
    assert c == {"Fabricação": ["prancha-01|1", "prancha-03|3"]}
    assert app.rota_impressao(s, "conjuntos", {})["conjuntos"] == c
    assert app.rota_impressao(s, "folhas", {"desenhos": nomes})["conjuntos"] == c


# ------------------------------------------------------------------ D05: o conjunto segue o título da folha
def _folhas(*titulos, desenho="pranchas"):
    return [{"chave": impressoes.chave(desenho, i), "desenho": desenho, "numero": i, "titulo": t} for i, t in enumerate(titulos, 1)]


def test_conjunto_segue_o_titulo_quando_as_pranchas_sao_montadas_de_novo():
    """D05 do usuario-desastrado (13/11): o "C2" com a 02 "Terças" e a 04 "Barras, Tirantes…"; montadas de novo sem a
    localização e as terças, a nova 02 é "Barras, Tirantes…" — o conjunto marcava a 02 pelo número (outra folha) e dizia
    "C2 (2)", calado; pela plotter sairia a folha errada."""
    antes = _folhas("Localização", "Terças", "Contraventamentos", "Barras, Tirantes")
    c2 = impressoes.conjuntos_validos({"C2": [{"chave": f["chave"], "titulo": f["titulo"]} for f in (antes[1], antes[3])]})["C2"]
    assert c2 == [{"chave": "pranchas|2", "titulo": "Terças"}, {"chave": "pranchas|4", "titulo": "Barras, Tirantes"}]
    depois = _folhas("Contraventamentos", "Barras, Tirantes")
    r = impressoes.resolver_conjunto(c2, depois)
    assert r["chaves"] == ["pranchas|2"]                                   # a folha "Barras, Tirantes", agora a 02
    assert r["mudaram"] == [{"titulo": "Barras, Tirantes", "de": "pranchas|4", "para": "pranchas|2"}]
    assert r["faltam"] == ["Terças"] and r["total"] == 2 and not r["antigo"]
    # as mesmas pranchas: o conjunto marca as mesmas folhas, sem aviso
    r = impressoes.resolver_conjunto(c2, antes)
    assert r["chaves"] == ["pranchas|2", "pranchas|4"] and not r["mudaram"] and not r["faltam"]


def test_conjunto_antigo_so_com_o_numero_avisa():
    # o guardado antes de 13/11 (só a chave): marca pelo número, mas não dá para conferir — a tela pede para salvar de novo
    r = impressoes.resolver_conjunto(["pranchas|2", "pranchas|9"], _folhas("A", "B"))
    assert r["chaves"] == ["pranchas|2"] and r["faltam"] == ["pranchas|9"] and r["antigo"]


def test_titulos_repetidos_nao_marcam_a_mesma_folha_duas_vezes():
    c = [{"chave": "pranchas|1", "titulo": "Detalhamento"}, {"chave": "pranchas|2", "titulo": "Detalhamento"}]
    r = impressoes.resolver_conjunto(c, _folhas("Capa", "Detalhamento", "Detalhamento"))
    assert sorted(r["chaves"]) == ["pranchas|2", "pranchas|3"] and not r["faltam"]


def test_rota_folhas_resolve_os_conjuntos(tmp_path, monkeypatch):
    """a rota das folhas devolve cada conjunto já resolvido nas folhas de hoje (a tela marca por ele e avisa)"""
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    r = g.criar("Obra conjuntos", tipo="ifc")
    s = r.get("slug") or r.get("id") or r.get("nome")
    for i in (1, 2, 3):
        d = _a4(i, 3)
        g.salvar_desenho(s, d.nome, d.dict())
    nomes = sorted(d["nome"] for d in g.listar_desenhos(s))
    f = app.rota_impressao(s, "folhas", {"desenhos": nomes})["folhas"]
    app.rota_impressao(s, "conjuntos", {"conjuntos": {"C2": [{"chave": f[2]["chave"], "titulo": f[2]["titulo"]}]}})
    # montada de novo: a folha 3 ("FOLHA 3") passa a ser a prancha 01, e a 03 vira outra
    for i, tit in ((1, "FOLHA 3"), (3, "FOLHA 9")):
        d = _a4(i, 3)
        d.metadados["prancha"]["titulo"] = tit
        g.salvar_desenho(s, d.nome, d.dict())
    r = app.rota_impressao(s, "folhas", {"desenhos": nomes})
    res = r["resolvidos"]["C2"]
    assert res["chaves"] == [r["folhas"][0]["chave"]] and res["mudaram"] and not res["faltam"]
