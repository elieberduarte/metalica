# -*- coding: utf-8 -*-
"""Saídas de produção iguais entre si (0.8.13): o romaneio CSV com as linhas da lista, o PDF
com o texto original, peças que não entram avisadas, posições de corte diferente separadas,
a seção vazada sem hachura por dentro e células que não se encostam."""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import detalhar as det                      # noqa: E402
from nucleo2d.desenho import Desenho, Hachura, Texto, Cota  # noqa: E402
from nucleo2d.detalhe import base as B                    # noqa: E402
from saida import lista_producao as lp                    # noqa: E402
from saida.detalhamento import Posicao                    # noqa: E402
from saida.dxf_render import ler_dxf                      # noqa: E402
from test_detalhar2d import _modelo                       # noqa: E402


def _num(t):
    return float(t.replace(",", ".")) if t else 0.0


def test_romaneio_csv_tem_as_linhas_e_os_totais_da_lista():
    lev = det.levantar(_modelo())
    lista = lp.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"],
                      projeto={"nome": "Teste"})
    with tempfile.TemporaryDirectory() as tmp:
        caminho = lp.gravar_romaneio_da_lista(os.path.join(tmp, "romaneio.csv"), lista)
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
    cab, corpo = linhas[0], linhas[1:]
    assert len(corpo) == len(lista["posicoes"]) + len(lista.get("acessorios") or [])
    pos = corpo[:len(lista["posicoes"])]
    assert [r[cab.index("Posicao")] for r in pos] == [li["marca"] for li in lista["posicoes"]]
    assert sum(int(r[cab.index("Qtd")]) for r in pos) == lista["totais"]["pecas"]
    assert abs(sum(_num(r[cab.index("Peso total (kg)")]) for r in pos) - lista["totais"]["peso"]) < 0.1


def test_pdf_leva_o_texto_original_e_o_dxf_continua_ascii():
    d = Desenho(nome="t", escala=10.0)
    d.add(Texto(posicao=(0, 0), texto="TERÇAS dobra 12,5° Ø17 …"))
    assert "TERÇAS dobra 12,5° Ø17 …" in d.para_dxf(10.0, texto_unicode=True).dxf()
    ascii_ = d.para_dxf(10.0).dxf()
    assert "TERÇAS" not in ascii_ and "°" not in ascii_ and "TERCAS" in ascii_
    with tempfile.TemporaryDirectory() as tmp:
        arq = d.para_dxf(10.0, texto_unicode=True).gravar(os.path.join(tmp, "u.dxf"))
        assert "TERÇAS dobra 12,5°" in repr(ler_dxf(arq))
        arq = d.para_dxf(10.0).gravar(os.path.join(tmp, "a.dxf"))      # R12 de fora: ANSI
        assert "TERCAS" in repr(ler_dxf(arq))


def test_peca_que_nao_se_monta_vira_aviso(monkeypatch):
    doc = _modelo()
    from nucleo3d.modelo import Barra
    doc.add(Barra(perfil="U88X40X2.25", inicio=(0, 0, 0), fim=(0, 0, 1000), rotacao=0))

    def falha(ent):
        raise ValueError("comprimento zero")
    monkeypatch.setattr(B, "_proxy_da_barra", falha)
    puladas = []
    B._pecas(doc, puladas)
    assert len(puladas) == 1 and puladas[0][1] == "comprimento zero"
    lev = det.levantar(doc)
    assert any("não entraram no detalhamento" in a and "comprimento zero" in a for a in lev["avisos"])


def _pos(marca, volume, classe="barra", perfil="U100X60X3.04"):
    return Posicao(marca=marca, tipo_ifc="IfcBeam", perfil=perfil, material="ASTM A36", quantidade=2,
                   classe=classe, L=894.0, H=100.0, T=60.0, comprimento=894.0, volume=volume)


def test_corte_diferente_nao_funde():
    # P112/P113 de corte reto e P104 com a ponta a 45° (o caso do ÁGUA GELADA): mesmo perfil,
    # furos e comprimento, volume 2 % menor
    fundidas = B.fundir_posicoes_iguais([_pos("P104", 570e3), _pos("P112", 581e3), _pos("P113", 581.1e3)], {})
    assert sorted(p.marca for p in fundidas) == ["P104", "P112 / P113"]
    # telha se compra inteira: o recorte na obra não separa a posição
    telhas = B.fundir_posicoes_iguais([_pos("M117", 594e3, "telha", "TELHA TP40"), _pos("M120", 558e3, "telha", "TELHA TP40")], {})
    assert [p.marca for p in telhas] == ["M117 / M120"]


def test_secao_vazada_sem_hachura_por_dentro():
    d = Desenho(nome="t", escala=1.0)
    externo = [(0, 0), (100, 0), (100, 100), (0, 100)]
    interno = [(10, 10), (90, 10), (90, 90), (10, 90)]
    d.add(Hachura(contornos=[externo, interno], espacamento=5.0))
    dxf = d.para_dxf(1.0)
    import re
    pares = [re.search(r"\n10\n([-\d.]+)\n20\n([-\d.]+)\n.*?\n11\n([-\d.]+)\n21\n([-\d.]+)\n", e, re.S).groups()
             for e in dxf.entidades if e.startswith("0\nLINE\n")]
    assert pares
    for x1, y1, x2, y2 in pares:
        xm, ym = (float(x1) + float(x2)) / 2, (float(y1) + float(y2)) / 2
        assert not (12 < xm < 88 and 12 < ym < 88), "linha de hachura no vazio do tubo"


def test_celulas_nao_se_encostam():
    d = Desenho(nome="t", escala=10.0)

    def celula(largura, texto):
        def desenhar(x, y):
            # a cota e o título saem para a esquerda da origem: a caixa devolvida não os vê
            d.add(Cota(p1=(x, y), p2=(x, y + 500), modo="v", deslocamento=-12.0))
            d.add(Texto(posicao=(x + largura, y + 520), texto=texto, alinhamento="direita"))
            return (x, y, x + largura, y + 500)
        return desenhar
    B._empilhar(d, [celula(300, "P1 – título comprido da peça"), celula(300, "P2 – outro título comprido")])
    a, b = d.metadados["celulas"]
    assert b[0] >= a[2] + 1.0 * d.escala, (a, b)
