# -*- coding: utf-8 -*-
"""Lista de materiais de produção (saida/lista_producao.py): encaixe em barras, resumos por
perfil, chapa e conjunto, totais e arquivos gravados."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import detalhar as det              # noqa: E402
from saida import lista_producao as lp            # noqa: E402
from test_detalhar2d import _modelo               # noqa: E402


def test_encaixar_em_barras():
    r = lp.encaixar([5000, 5000, 1200, 1200, 1200, 1200, 1200, 1200], 6000)
    assert r["quantidade"] == 4 and r["emendas"] == 0            # 2 de 5000 + 6 × 1200 em 2 barras (4 + 2)
    assert 0 < r["aproveitamento"] <= 100 and r["sobra_m"] > 0
    # peça de 7 m numa barra de 6: uma barra inteira e o resto (1 m) encaixa na sobra da de 4 m
    r = lp.encaixar([7000, 4000], 6000)
    assert r["quantidade"] == 2 and r["emendas"] == 1
    # com 5 m no lugar de 4 a sobra (997 mm, já descontado o corte) não recebe o resto de 1 m
    assert lp.encaixar([7000, 5000], 6000)["quantidade"] == 3
    assert lp.encaixar([], 6000)["quantidade"] == 0
    # barra automática: 6 m quando tudo cabe, 12 m se alguma peça passa
    assert lp._barra_para([5999], 0) == 6000 and lp._barra_para([6001], 0) == 12000
    assert lp._barra_para([6001], 6000) == 6000


def test_montar_resumos_e_totais():
    lev = det.levantar(_modelo())
    lista = lp.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"],
                      projeto={"nome": "Teste", "cliente": "Cliente"})
    t = lista["totais"]
    assert t["posicoes"] == 5 and t["pecas"] == 17 and t["peso"] > 0
    cats = {c["categoria"]: c for c in t["categorias"]}
    assert cats["TERÇAS"]["pecas"] == 2 and cats["CHAPAS"]["pecas"] == 3 and cats["BARRAS"]["pecas"] == 12
    assert abs(sum(c["pct"] for c in t["categorias"]) - 100) < 0.5
    # perfis: o U150 são 2 terças de 5 m → 10 m, 2 barras de 6 m; o U88 são 12 de 1,2 m → 3 barras
    perfis = {g["perfil"]: g for g in lista["perfis"]}
    u150, u88 = perfis["U150X50X2.25"], perfis["U88X40X2.25"]
    assert u150["pecas"] == 2 and abs(u150["comprimento_m"] - 10.0) < 0.01 and u150["barras"]["quantidade"] == 2
    assert u150["categoria"] == "TERÇAS" and u150["kg_m"] > 0
    assert u88["pecas"] == 12 and u88["barras"]["quantidade"] == 3 and u88["posicoes"] == ["P2", "P3", "P4"]
    # chapas: P1 130×50×3 ×3
    assert len(lista["chapas"]) == 1
    ch = lista["chapas"][0]
    assert ch["espessura"] == 3.0 and ch["pecas"] == 3 and abs(ch["area_m2"] - 3 * 0.13 * 0.05) < 0.005
    # conjuntos: M9 tem 2 instâncias de 2 P3 + 1 P4; M1..M3 uma cada (1 P1 + 2 P2); o M5 (terça solta) não entra
    conj = {c["marca"]: c for c in lista["conjuntos"]}
    assert set(conj) == {"M1", "M2", "M3", "M9"}
    assert conj["M9"]["instancias"] == 2 and conj["M9"]["composicao"] == {"P3": 2, "P4": 1}
    assert conj["M9"]["composicao_texto"] == "2× P3, 1× P4"
    assert abs(conj["M9"]["peso_total"] - 2 * conj["M9"]["peso_unitario"]) < 0.03   # arredondados em separado
    assert conj["M1"]["pecas_unidade"] == 3 and conj["M1"]["categoria"] == "CONJUNTOS"
    # romaneio por posição com categoria e conjuntos
    pos = {p["marca"]: p for p in lista["posicoes"]}
    assert pos["P1"]["categoria"] == "CHAPAS" and pos["P1"]["espessura"] == 3.0 and pos["P1"]["quantidade"] == 3
    assert pos["M5"]["categoria"] == "TERÇAS" and pos["M5"]["conjuntos"] == ["M5"]
    assert lista["projeto"]["nome"] == "Teste"
    # barra fixa de 12 m: as terças cabem numa só
    lista12 = lp.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"], barra=12000)
    assert {g["perfil"]: g for g in lista12["perfis"]}["U150X50X2.25"]["barras"] == dict(comprimento=12000.0, quantidade=1, emendas=0,
                                                                                         aproveitamento=83.3, sobra_m=1.99) or \
        {g["perfil"]: g for g in lista12["perfis"]}["U150X50X2.25"]["barras"]["quantidade"] == 1


def test_gravar_arquivos_e_html():
    lev = det.levantar(_modelo())
    lista = lp.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"], projeto={"nome": "Obra <X>"})
    with tempfile.TemporaryDirectory() as pasta:
        arq = lp.gravar(pasta, lista, lev["posicoes"], lev["acessorios"])
        for k in ("json", "romaneio", "perfis", "chapas", "conjuntos", "html"):
            assert os.path.exists(arq[k]) and os.path.getsize(arq[k]) > 0, k
        lido = json.load(open(arq["json"], encoding="utf-8"))
        assert lido["totais"]["pecas"] == 17
        linhas = open(arq["perfis"], encoding="utf-8-sig").read().splitlines()
        assert linhas[0].startswith("Perfil;Material;Categoria") and len(linhas) == 3
        assert "U150X50X2.25;CIVIL 300;TERÇAS;M5;2;10,00" in linhas[1] + linhas[2]
        html = open(arq["html"], encoding="utf-8").read()
        assert "Obra &lt;X&gt;" in html and "Romaneio por posição" in html and "2× P3, 1× P4" in html
        assert html.count("<table") >= 5
        corpo = lp.corpo_html(lista)
        assert "Quadro 1" in corpo and "Quadro 6" in corpo


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
