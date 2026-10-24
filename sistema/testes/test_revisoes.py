# -*- coding: utf-8 -*-
"""As revisões das pranchas (nucleo2d/revisoes.py; usuário, 24/10: a opção A — a tabela inteira em cima do carimbo, a
mais nova em cima, REV. | DATA | DESCRIÇÃO DA REVISÃO | POR; o diálogo marca as pranchas que mudaram)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nucleo2d.desenho import Desenho, Linha, Texto
from nucleo2d import modelo_hermes as M, revisoes
from nucleo2d.pranchas import FOLHAS, juntar_pranchas


def _prancha(numero, formato="A1"):
    d = Desenho(nome="Prancha %02d" % numero, escala=1.0)
    larg, alt = FOLHAS[formato]
    quadro, carimbo = M.desenhar_folha(d, formato, larg, alt, {"obra": "OBRA", "revisao": "00"}, numero, 4, "1:25", ["- TESOURAS"])
    d.metadados["prancha"] = {"formato": formato, "numero": numero, "total": 4, "titulo": "P%d" % numero,
                              "quadro": list(quadro), "carimbo": list(carimbo), "celulas": []}
    return d


def _da_tabela(d, n=None):
    return [e for e in d.entidades.values() if (e.atributos or {}).get("campo") == "revisoes"
            and (n is None or (e.atributos or {}).get("prancha_numero") == n)]


def _texto_prancha(d, n=None):
    return [e.texto for e in d.entidades.values() if isinstance(e, Texto) and (e.atributos or {}).get("campo") == "prancha"
            and (n is None or (e.atributos or {}).get("prancha_numero") == n)]


def test_nova_revisao_numera_cada_prancha():
    r = revisoes.nova_revisao({}, [3, 5], "telhas do beiral", "E.D.", "17/10/2026", "10/10/2026")
    assert [ln["rev"] for ln in r["3"]] == ["00", "01"] and r["3"][0]["descricao"] == "EMISSÃO INICIAL"
    assert r["3"][0]["data"] == "10/10/2026" and r["3"][1] == {"rev": "01", "data": "17/10/2026", "descricao": "TELHAS DO BEIRAL", "por": "E.D."}
    r2 = revisoes.nova_revisao(r, [3], "detalhe 4", "E.D.", "24/10/2026")
    assert [ln["rev"] for ln in r2["3"]] == ["00", "01", "02"] and [ln["rev"] for ln in r2["5"]] == ["00", "01"]
    assert [ln["rev"] for ln in r["3"]] == ["00", "01"]                 # a entrada não muda


def test_nova_revisao_sem_descricao_recusa():
    try:
        revisoes.nova_revisao({}, [1], "  ")
    except ValueError:
        return
    raise AssertionError("aceitou a revisão sem descrição")


def test_tabela_em_cima_do_carimbo_a_mais_nova_em_cima():
    linhas = revisoes.nova_revisao(revisoes.nova_revisao({}, [3], "terças", "E.D.", "17/10/2026", "10/10/2026"), [3], "telhas", "E.D.", "24/10/2026")
    d = Desenho(nome="p", escala=1.0)
    larg, alt = FOLHAS["A1"]
    M.desenhar_folha(d, "A1", larg, alt, {"obra": "OBRA", "revisao": "00", "revisoes": linhas}, 3, 12, "1:50", [])
    tab = _da_tabela(d)
    topo_carimbo = M.MARGENS["inferior"] + M.CARIMBO[1]
    assert tab and all(min(p[1] for p in e.pontos()) >= topo_carimbo + 1.9 for e in tab), "a tabela fica em cima do carimbo"
    revs = sorted((e.posicao[1], e.texto) for e in tab if isinstance(e, Texto) and e.texto in ("REV.", "00", "01", "02"))
    assert [t for _y, t in revs] == ["REV.", "00", "01", "02"], "o cabeçalho embaixo e a mais nova em cima"
    assert abs(revs[1][0] - revs[0][0] - M.REV_ALTURA) < 1e-6
    x1 = larg - M.MARGENS["direita"]
    xs = [p[0] for e in tab for p in e.pontos()]
    assert min(xs) >= x1 - M.CARIMBO[0] and max(xs) <= x1, "na largura do carimbo"
    assert _texto_prancha(d) == ["PRANCHA 03/12   REV. 02"], "o REV. do carimbo é o da última linha"


def test_sem_revisao_o_carimbo_fica_como_era():
    d = Desenho(nome="p", escala=1.0)
    M.desenhar_folha(d, "A1", 841, 594, {"obra": "OBRA", "revisao": "00", "revisoes": {"5": []}}, 3, 12, "1:50", [])
    assert not _da_tabela(d) and _texto_prancha(d) == ["PRANCHA 03/12   REV. 00"]


def test_a3_reduz_como_o_carimbo():
    d = Desenho(nome="p", escala=1.0)
    larg, alt = FOLHAS["A3"]
    caixa = M.desenhar_revisoes(d, "A3", larg, alt, [{"rev": "00", "data": "", "descricao": "EMISSÃO INICIAL", "por": ""}], {})
    f = M.FATOR_CARIMBO["A3"]
    assert abs((caixa[3] - caixa[1]) - 2 * M.REV_ALTURA * f) < 1e-6
    assert abs(caixa[1] - (M.MARGENS["inferior"] + (M.CARIMBO[1] + 2.0) * f)) < 1e-6


def test_aplicar_no_desenho_das_pranchas_troca_a_tabela_da_folha_certa():
    junto = juntar_pranchas([_prancha(1), _prancha(2)])
    origem2 = junto.metadados["pranchas"][1]["origem"]
    r = revisoes.nova_revisao({}, [2], "terças trocadas", "E.D.", "17/10/2026", "10/10/2026")
    res = revisoes.aplicar_no_desenho(junto, r)
    assert res["folhas"] == 1 and not _da_tabela(junto, 1) and _da_tabela(junto, 2)
    assert min(p[0] for e in _da_tabela(junto, 2) for p in e.pontos()) > origem2[0], "na folha 2, não na 1"
    assert _texto_prancha(junto, 2) == ["PRANCHA 02/04   REV. 01"] and _texto_prancha(junto, 1) == ["PRANCHA 01/04   REV. 00"]
    n_antes = len(_da_tabela(junto, 2))
    r2 = revisoes.nova_revisao(r, [2], "detalhe 4", "E.D.", "24/10/2026")
    revisoes.aplicar_no_desenho(junto, r2)
    assert len(_da_tabela(junto, 2)) > n_antes and _texto_prancha(junto, 2) == ["PRANCHA 02/04   REV. 02"]
    textos = [e.texto for e in _da_tabela(junto, 2) if isinstance(e, Texto)]
    assert textos.count("REV.") == 1 and textos.count("01") == 1, "a tabela de antes sai (não fica uma em cima da outra)"
    folha = next(e for e in _da_tabela(junto, 2))
    assert folha.atributos.get("folha") == junto.metadados["pranchas"][1]["folha"], "o clique na tabela pega a folha"


def test_tabela_que_cai_num_detalhe_e_avisada():
    junto = juntar_pranchas([_prancha(1)])
    # um detalhe logo acima do carimbo, no lugar da tabela
    junto.add(Linha(camada="VISTA", a=(700.0, 120.0), b=(760.0, 125.0), atributos={"prancha_numero": 1, "cel": "x"}))
    r = revisoes.aplicar_no_desenho(junto, revisoes.nova_revisao({}, [1], "x", "", "24/10/2026"))
    assert r["encostam"] == [1]
    longe = juntar_pranchas([_prancha(1)])
    longe.add(Linha(camada="VISTA", a=(100.0, 400.0), b=(200.0, 400.0), atributos={"prancha_numero": 1, "cel": "x"}))
    assert revisoes.aplicar_no_desenho(longe, revisoes.nova_revisao({}, [1], "x", "", "24/10/2026"))["encostam"] == []


def test_prancha_solta_tambem():
    d = _prancha(4)
    revisoes.aplicar_no_desenho(d, revisoes.nova_revisao({}, [4], "x", "", "24/10/2026"))
    assert _da_tabela(d) and _texto_prancha(d) == ["PRANCHA 04/04   REV. 01"]
