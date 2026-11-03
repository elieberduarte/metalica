# -*- coding: utf-8 -*-
"""O carimbo das pranchas com o logo da empresa do projeto, e as hachuras cheias do PDF na cor delas.

OBRA · CASA ALTO PADRÃO, 02/11 (usuário: "ter as plantas, cortes, implantação, tudo organizadinho e padronizado, e aproveitando
para montar as pranchas"; o carimbo escolhido foi o da DEZN):
- o carimbo só desenhava o logo da Hermes, em qualquer projeto. Agora o projeto marca a empresa
  (projeto.json "carimbo_pranchas": {"empresa": "dezn"}) e o logo vem do cadastro dela (marca/logo.svg);
- o PDF pintava toda hachura cheia na cor da CAMADA e por cima de linhas e textos (e ainda com as riscas da hachura do DXF
  embaixo): a planta humanizada, colorida pelo material de cada peça, saía cinza e cobria os nomes dos cômodos.
O SVG do teste é o da DEZN como está no cadastro (4 caminhos de retas e 2 textos)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Hachura, Texto, Linha   # noqa: E402
from nucleo2d import modelo_hermes as MH                       # noqa: E402
from nucleo2d import pranchas as P                             # noqa: E402

SVG_DEZN = ('<?xml version="1.0" encoding="UTF-8"?>\n<svg viewBox="3800 10 1540 1420" xmlns="http://www.w3.org/2000/svg">'
            '<path fill="#7F9FFF" d="M4308.9 177.7 L4308.9 408.4 L4386.6 360.8 L4386.6 228.5 L4449.1 190.1 L4449.1 322.4 '
            'L4523.8 276.7 L4523.8 144.4 L4570.6 115.7 L4617.4 144.4 L4617.4 276.7 L4692.0 322.4 L4692.0 190.1 L4754.6 228.5 '
            'L4754.6 360.8 L4832.3 408.4 L4832.3 177.7 L4570.6 22.7 Z"/>'
            '<path fill="#800080" d="M4570.6 408.4 L4891.4 604.9 L4891.4 505.9 L4570.6 309.4 L4249.8 505.9 L4249.8 604.9 Z"/>'
            '<path fill="#800080" d="M4523.8 482.5 L4449.1 528.2 L4449.1 651.6 L4523.8 651.6 Z"/>'
            '<path fill="#800080" d="M4692.0 528.2 L4617.4 482.5 L4617.4 651.6 L4692.0 651.6 Z"/>'
            '<text x="3818" y="1188.3" textLength="1505" lengthAdjust="spacingAndGlyphs" style="font:700 586px Arial;'
            'fill:#22346E">DEZN</text><text x="3822" y="1411.0" textLength="1495" lengthAdjust="spacingAndGlyphs" '
            'style="font:400 208px \'Microsoft JhengHei\';fill:#800080">CONSTRUTORA</text></svg>')


def _svg(pasta):
    caminho = os.path.join(pasta, "logo.svg")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(SVG_DEZN)
    return caminho


def _folha(info):
    d = Desenho(nome="folha", escala=1.0)
    MH.desenhar_folha(d, "A1", 841.0, 594.0, info, 1, 1, "1:50", ["PLANTA BAIXA"])
    return d


def test_logo_do_svg_le_os_caminhos_e_os_textos():
    with tempfile.TemporaryDirectory() as tmp:
        logo = MH.logo_do_svg(_svg(tmp))
    assert len(logo["hachuras"]) == 4
    assert [h["cor"] for h in logo["hachuras"]] == ["#7F9FFF", "#800080", "#800080", "#800080"]
    assert [t["texto"] for t in logo["textos"]] == ["DEZN", "CONSTRUTORA"]
    assert len(logo["hachuras"][0]["contornos"][0]) == 18
    x0, y0, x1, y1 = logo["caixa"]
    assert x0 < 3820 and x1 > 5300 and y1 > -30 and y0 < -1400       # y para cima: o telhado em cima, o texto embaixo


def test_carimbo_com_o_logo_da_empresa_no_lugar_do_da_hermes():
    with tempfile.TemporaryDirectory() as tmp:
        logo = MH.logo_do_svg(_svg(tmp))
    com = _folha({"obra": "CASA", "logo": logo})
    sem = _folha({"obra": "CASA"})
    do_logo = lambda d: [e for e in d.entidades.values() if (e.atributos or {}).get("campo") == "logo"]   # noqa: E731
    h_com = [e for e in do_logo(com) if isinstance(e, Hachura)]
    t_com = [e for e in do_logo(com) if isinstance(e, Texto)]
    assert len(h_com) == 4 and {e.atributos["cor"] for e in h_com} == {"#7F9FFF", "#800080"}
    assert [t.texto for t in t_com] == ["DEZN", "CONSTRUTORA"]
    assert len(do_logo(sem)) == len(MH.LOGO_HACHURAS)                   # sem empresa: o da Hermes, como antes
    # dentro da caixa do logo do carimbo (A1: o carimbo encosta no quadro, embaixo à direita)
    cx0 = 841.0 - MH.MARGENS["direita"] - MH.CARIMBO[0]
    bx0, by0, bx1, by1 = MH.CAIXAS["logo"]
    pts = [p for e in h_com for c in e.contornos for p in c] + [t.posicao for t in t_com]
    assert all(cx0 + bx0 <= x <= cx0 + bx1 and 7.0 + by0 <= y <= 7.0 + by1 for x, y in pts)


class _Eixo:
    def __init__(self):
        self.patches = []

    def add_patch(self, p):
        self.patches.append(p)


def test_pdf_pinta_a_hachura_cheia_na_cor_dela_e_por_baixo():
    d = Desenho(nome="humanizada", escala=100.0)
    d.add(Hachura(camada="HUM", contornos=[[(0, 0), (1000, 0), (1000, 1000), (0, 1000)]], padrao="solido",
                  atributos={"cor": "#d8c3a5"}))
    d.add(Hachura(camada="HUM", contornos=[[(0, 0), (500, 0), (500, 500)]], padrao="solido"))
    ax = _Eixo()
    P._preencher_solidas(d, ax)
    import matplotlib.colors as mc
    assert mc.to_hex(ax.patches[0].get_facecolor()) == "#d8c3a5"      # a do objeto, como no CAD
    assert mc.to_hex(ax.patches[1].get_facecolor()) == mc.to_hex(d.camadas["HUM"].cor if "HUM" in d.camadas else "#111827")
    assert all(p.get_zorder() < 2 for p in ax.patches)                # embaixo das linhas (2) e dos textos (3)


def test_pdf_sem_as_riscas_da_hachura_cheia():
    d = Desenho(nome="humanizada", escala=1.0)
    d.add(Hachura(camada="HUM", contornos=[[(10, 10), (200, 10), (200, 150), (10, 150)]], padrao="solido",
                  atributos={"cor": "#d8c3a5"}))
    d.add(Linha(camada="VISTA", a=(0, 0), b=(50, 0)))
    d.add(Texto(camada="TEXTO", posicao=(50, 50), texto="SALA", altura=2.5))

    class _Pdf:
        def savefig(self, fig):
            pass
    with tempfile.TemporaryDirectory() as tmp:
        arq = os.path.join(tmp, "p.dxf")
        P._pagina_do_pdf(_Pdf(), d, arq, 297.0, 210.0, 1.0, 1.0, 0.0, 0.0, {})
        with open(arq, encoding="utf-8", errors="replace") as f:
            linhas = [ln.strip() for ln in f]
    assert linhas.count("LINE") == 1                                    # só a linha do desenho; a hachura não vira riscas
    assert len(d.entidades) == 3                                        # e o desenho volta inteiro


def test_logo_da_empresa_marcada_no_projeto():
    import app
    with tempfile.TemporaryDirectory() as raiz:
        marca = os.path.join(raiz, "fabrica", "empresas", "dezn", "marca")
        os.makedirs(marca)
        _svg(marca)
        with open(os.path.join(raiz, "fabrica", "empresas", "dezn", "empresa.json"), "w", encoding="utf-8") as f:
            json.dump({"nome_comercial": "DEZN Construtora"}, f)
        antes = app.PROJETOS
        app.PROJETOS = raiz
        try:
            logo = app._logo_do_carimbo({"carimbo_pranchas": {"empresa": "dezn"}})
            assert logo and [t["texto"] for t in logo["textos"]] == ["DEZN", "CONSTRUTORA"]
            assert app._logo_do_carimbo({}) is None                     # sem empresa: o carimbo da Hermes
            assert app._logo_do_carimbo({"carimbo_pranchas": {"empresa": "nao-existe"}}) is None
        finally:
            app.PROJETOS = antes


def test_logo_da_linha_metalica_sem_o_construtora():
    """OBRA · WE COQUEIRAL · ESCADAS, 02/11 (usuário: "o projeto executivo detalhado nas pranchas com o logo da DEZN"): na
    metálica a DEZN assina só "DEZN" (memória dezn-proposta-metalica, empresa.json "linhas.metalica"); o carimbo saía com o
    logo principal, com o "CONSTRUTORA". O projeto marca a linha: "carimbo_pranchas": {"empresa": "dezn", "linha": "metalica"}."""
    import app
    with tempfile.TemporaryDirectory() as raiz:
        marca = os.path.join(raiz, "fabrica", "empresas", "dezn", "marca")
        os.makedirs(marca)
        _svg(marca)
        so_dezn = SVG_DEZN[:SVG_DEZN.index("<text x=\"3822\"")] + "</svg>"
        with open(os.path.join(marca, "logo_metalica.svg"), "w", encoding="utf-8") as f:
            f.write(so_dezn)
        with open(os.path.join(raiz, "fabrica", "empresas", "dezn", "empresa.json"), "w", encoding="utf-8") as f:
            json.dump({"nome_comercial": "DEZN Construtora",
                       "linhas": {"metalica": {"nome_comercial": "DEZN", "logo": "logo_metalica.svg"}}}, f)
        antes = app.PROJETOS
        app.PROJETOS = raiz
        try:
            logo = app._logo_do_carimbo({"carimbo_pranchas": {"empresa": "dezn", "linha": "metalica"}})
            assert logo and [t["texto"] for t in logo["textos"]] == ["DEZN"]
            # sem a linha (a arquitetura da Casa Alto Padrão): o logo principal, com o CONSTRUTORA
            logo = app._logo_do_carimbo({"carimbo_pranchas": {"empresa": "dezn"}})
            assert [t["texto"] for t in logo["textos"]] == ["DEZN", "CONSTRUTORA"]
        finally:
            app.PROJETOS = antes
