# -*- coding: utf-8 -*-
"""Memorial de cálculo do galpão, em PDF.

    from saida import memorial
    caminho = memorial.gerar(projeto, "projetos/meu-galpao/memorial")

O documento é montado em HTML e impresso pelo Chrome com o Paged.js (mesmo mecanismo
já validado no manual — ver `saida/printpdf.py`), com a folha de estilo `memorial.css`.

O memorial tem de ser **auditável**: qualquer engenheiro deve conseguir refazer as contas
lendo o documento. Por isso nada é resumido — todos os `Passo` de todas as `Verificacao`
são impressos com texto, fórmula simbólica, a mesma fórmula com os números substituídos,
o resultado e o item da norma. Este módulo **não calcula nada**: tudo que ele imprime já
está em `ProjetoGalpao` (princípio 2 do guia do sistema).

Ordem do documento:

    capa · sumário
    1. Dados de entrada            6. Dimensionamento elemento por elemento
    2. Normas e critérios          7. Ligações e base
    3. Ações e cargas              8. Lista de material e resumo
    4. Combinações                 9. Conclusão e responsabilidade técnica
    5. Esforços solicitantes
"""
import html as _html_mod
import math
import os
import re
import sys
import tempfile
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from nucleo.base import (E, G, GAMA_A1, GAMA_A2, GAMA_C, GAMA_W2, Passo,  # noqa: E402
                         Resultado, Verificacao, fmt)
from nucleo.modelo_galpao import (DadosGalpao, ElementoDimensionado,       # noqa: E402
                                  ProjetoGalpao)

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _identificacao_do_programa() -> str:
    """'Metálica 0.1.0 · núcleo 3f9a1c0b7e2d', impresso na capa: de qual versão o
    memorial saiu e com qual núcleo de cálculo (ver `versao.py`)."""
    try:
        raiz = os.path.dirname(_AQUI)
        if raiz not in sys.path:
            sys.path.insert(0, raiz)
        import versao
        return versao.identificacao()
    except Exception:                                  # a capa não pode cair por isso
        return ""

#: Largura útil da página A4 com as margens da folha de estilo (176 mm), em pontos.
#: É a largura natural das figuras desenhadas aqui; o CSS só as reduz, nunca amplia.
LARGURA_FIGURA_PT = 172.0 / 25.4 * 72.0

# =====================================================================================
# Normas citadas e agrupamento dos dados de entrada
# =====================================================================================

NORMAS = [
    ("ABNT NBR 8800:2008",
     "Projeto de estruturas de aço e de estruturas mistas de aço e concreto de edifícios",
     "Dimensionamento de barras laminadas e soldadas, ligações, combinações de ações e "
     "estados-limites de serviço."),
    ("ABNT NBR 14762:2010",
     "Dimensionamento de estruturas de aço constituídas por perfis formados a frio",
     "Terças, longarinas e demais perfis Ue/U formados a frio."),
    ("ABNT NBR 6120:2019", "Ações para o cálculo de estruturas de edificações",
     "Pesos próprios dos materiais e sobrecargas de utilização."),
    ("ABNT NBR 6123:1988", "Forças devidas ao vento em edificações",
     "Velocidade básica, fatores S₁, S₂ e S₃, coeficientes de pressão externa e interna."),
    ("ABNT NBR 8681:2003", "Ações e segurança nas estruturas — Procedimento",
     "Critério de combinação das ações e coeficientes de ponderação."),
    ("ABNT NBR 6355:2012", "Perfis estruturais de aço formados a frio — Padronização",
     "Dimensões e propriedades dos perfis Ue e U enrijecidos."),
    ("ABNT NBR 8681 / NBR 16239", "Perfis tubulares",
     "Quando houver barras tubulares (escoras e contraventamentos)."),
    ("ABNT NBR 6118:2023", "Projeto de estruturas de concreto — Procedimento",
     "Verificação do concreto sob a placa de base e da ancoragem dos chumbadores."),
    ("AWS D1.1 / ABNT NBR 8800, Anexo A", "Soldagem estrutural",
     "Qualificação dos procedimentos e resistência do metal de solda."),
]

#: Grupos dos campos de `DadosGalpao`, na ordem em que aparecem no memorial.
GRUPOS_ENTRADA = [
    ("Identificação da obra", ["nome", "cliente", "local", "responsavel"]),
    ("Geometria", ["vao", "comprimento", "pe_direito", "espacamento_porticos",
                   "inclinacao", "balanco_lateral"]),
    ("Sistema estrutural", ["tipo_portico", "base_rotulada", "com_misula",
                            "comprimento_misula", "altura_misula"]),
    ("Materiais", ["aco_perfis", "aco_tercas", "aco_chapas", "parafuso", "eletrodo",
                   "fck_MPa"]),
    ("Cobertura e fechamento", ["telha", "espacamento_tercas", "linhas_correntes",
                                "fechamento_lateral", "altura_fechamento"]),
    ("Cargas", ["sobrecarga_cobertura", "carga_forro", "carga_extra", "ponte_rolante",
                "capacidade_ponte_t"]),
    ("Vento (NBR 6123)", ["cidade", "v0", "categoria_rugosidade", "classe",
                          "fator_topografico", "fator_estatistico", "aberturas"]),
    ("Critérios de projeto", ["flecha_terca", "flecha_viga", "desloc_horizontal",
                              "custo_kg"]),
]


def _rotulos() -> Dict[str, str]:
    """Rótulos dos campos — os mesmos da interface, para o documento não divergir."""
    try:
        from app import ROTULOS            # o módulo do servidor não sobe nada ao importar
        return dict(ROTULOS)
    except Exception:
        return {}


ROTULOS = _rotulos()


def _rotulo(campo: str) -> str:
    return ROTULOS.get(campo, campo.replace("_", " ").capitalize())


# =====================================================================================
# Utilidades de HTML
# =====================================================================================

def _esc(t) -> str:
    return _html_mod.escape("" if t is None else str(t), quote=False)


def _valor(v) -> str:
    """Valor de campo de entrada, formatado para leitura."""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, float):
        return fmt(v, 3 if abs(v) < 1 and v else 2)
    if isinstance(v, int):
        return str(v)
    return _esc(v) if v not in (None, "") else "—"


def _tabela(colunas, linhas, caption="", classes="tab small", larguras=None,
            rodape=None) -> str:
    """Tabela HTML. Cada célula é um texto ou `(texto, classe)`; o texto vai cru."""
    cols = ""
    if larguras:
        cols = "<colgroup>" + "".join(f'<col style="width:{w}">' for w in larguras) \
               + "</colgroup>"
    th = "".join(f"<th>{c}</th>" for c in colunas)

    def linha_html(linha, tag="td"):
        tds = []
        for cel in linha:
            texto, cls = cel if isinstance(cel, tuple) else (cel, "l")
            tds.append(f'<{tag} class="{cls}">{texto}</{tag}>')
        return "<tr>" + "".join(tds) + "</tr>"

    corpo = "".join(linha_html(l) for l in linhas)
    pe = f"<tfoot>{''.join(linha_html(l) for l in rodape)}</tfoot>" if rodape else ""
    return (f'<table class="{classes}">'
            + (f"<caption>{caption}</caption>" if caption else "")
            + cols + f"<thead><tr>{th}</tr></thead><tbody>{corpo}</tbody>{pe}</table>")


def _chave_valor(pares, caption="", larguras=("46%", "54%"), classes="tab small") -> str:
    linhas = [[(_esc(k), "l"), (v if isinstance(v, str) else _valor(v), "r")]
              for k, v in pares]
    return _tabela(["Grandeza", "Valor"], linhas, caption, classes, list(larguras))


def _box(texto, titulo="", tipo="") -> str:
    t = f'<div class="t">{_esc(titulo)}</div>' if titulo else ""
    return f'<div class="box {tipo}">{t}{texto}</div>'


# =====================================================================================
# Desenhos: Desenho (DXF) → SVG, pelo mesmo renderizador das pranchas
# =====================================================================================

_CONTA_SVG = [0]


def _unico(svg: str) -> str:
    """Prefixa os ids internos do SVG para que várias figuras convivam na página."""
    _CONTA_SVG[0] += 1
    p = f"g{_CONTA_SVG[0]}-"
    return re.sub(r'(id="|href="#)([A-Za-z][\w.:-]*)"',
                  lambda m: f'{m.group(1)}{p}{m.group(2)}"', svg)


def desenho_para_svg(desenho, largura_mm: float = 172.0,
                     altura_max_mm: float = 118.0) -> str:
    """Renderiza um `saida.dxf.Desenho` em SVG, via `saida.dxf_render`.

    A figura sai em escala: `largura_mm` é a largura ocupada no papel, e a altura
    acompanha, limitada por `altura_max_mm`. A altura do texto do desenho (que está em
    milímetros do modelo) é convertida para a altura correspondente no papel.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from . import dxf_render

    larg = max(desenho.largura, 1e-6)
    alt = max(desenho.altura, 1e-6)
    # papel-mm por desenho-mm (é o inverso da escala do desenho)
    razao = min(largura_mm / larg, altura_max_mm / alt)
    fig_l = larg * razao / 25.4
    fig_a = alt * razao / 25.4

    with tempfile.TemporaryDirectory() as tmp:
        caminho = os.path.join(tmp, "figura.dxf")
        desenho.gravar(caminho)
        fig = plt.figure(figsize=(max(fig_l, 0.5), max(fig_a, 0.35)))
        ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
        # a altura do texto DXF vale `h` mm no modelo → h·razao mm no papel;
        # dxf_render usa fontsize = h · escala_texto · 2,4 (pt), e 1 mm = 2,835 pt,
        # com altura de letra maiúscula ≈ 0,73 do corpo da fonte
        escala_texto = razao * (2.835 / 0.73) / 2.4
        dxf_render.desenhar(caminho, ax, escala_texto=escala_texto)
        x0, y0, x1, y1 = desenho.extremos
        folga = 0.01 * max(larg, alt)
        ax.set_xlim(x0 - folga, x1 + folga)
        ax.set_ylim(y0 - folga, y1 + folga)
        ax.set_aspect("equal")
        ax.axis("off")
        import io
        buf = io.StringIO()
        fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.01,
                    transparent=True)
        plt.close(fig)

    # o SVG sai do matplotlib com largura e altura naturais em pontos, iguais ao
    # tamanho pedido no papel: é isso que faz a figura entrar na página em escala,
    # bastando `max-width: 100%` no CSS para nunca estourar a coluna de texto
    svg = buf.getvalue()
    svg = svg[svg.index("<svg"):]
    return _unico(svg)


# =====================================================================================
# Diagramas de esforços em SVG
# =====================================================================================

def _svg_esforcos(modelo, series: Dict[int, dict], grandeza: str, unidade: str,
                  cor: str, divisor: float = 1.0, largura_px: float = 900.0) -> str:
    """Diagrama de `grandeza` ("N", "V" ou "M") desenhado sobre o pórtico.

    `series[k]` = {"x": [cm], "max": [...], "min": [...]} da barra k, em kN ou kN·cm.
    O diagrama é traçado perpendicularmente a cada barra, com a mesma escala em todas.
    """
    nos = modelo.nos
    xs = [n.x for n in nos]
    ys = [n.y for n in nos]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    larg = max(x1 - x0, 1.0)
    alt = max(y1 - y0, 1.0)

    pico = 0.0
    for s in series.values():
        for v in list(s["max"]) + list(s["min"]):
            pico = max(pico, abs(v))
    if pico <= 0:
        pico = 1.0
    ordenada = 0.22 * max(larg, alt)                   # ordenada do valor de pico
    esc = ordenada / pico                              # cm de desenho por unidade

    # --- contorno do diagrama, em coordenadas do modelo ----------------------
    curvas: Dict[int, Dict[str, List[Tuple[float, float]]]] = {}
    for idx, b in enumerate(modelo.barras):
        s = series.get(idx)
        if not s or not s["x"]:
            continue
        ni, nf = nos[b.ni], nos[b.nf]
        L = math.hypot(nf.x - ni.x, nf.y - ni.y) or 1.0
        ux, uy = (nf.x - ni.x) / L, (nf.y - ni.y) / L
        nx, ny = -uy, ux                                # normal à esquerda
        curvas[idx] = {"eixo": (ni, nf, ux, uy, nx, ny)}
        for chave in ("max", "min"):
            pts = []
            for xi, v in zip(s["x"], s[chave]):
                bx, by = ni.x + ux * xi, ni.y + uy * xi
                pts.append((bx + nx * v * esc, by + ny * v * esc))
            curvas[idx][chave] = pts
            for p_ in pts:
                x0, x1 = min(x0, p_[0]), max(x1, p_[0])
                y0, y1 = min(y0, p_[1]), max(y1, p_[1])

    # --- geometria do quadro, já contendo os diagramas e os rótulos ----------
    margem = 0.07 * max(x1 - x0, y1 - y0)
    vx0, vy0 = x0 - margem, y0 - margem
    vlarg = (x1 - x0) + 2 * margem
    valt = (y1 - y0) + 2 * margem
    k = largura_px / vlarg
    fonte = max(9.0, largura_px / 75.0)
    faixa = 2.6 * fonte                                 # faixa da legenda, embaixo
    altura_px = valt * k + faixa
    px = lambda x: (x - vx0) * k                        # noqa: E731
    py = lambda y: (vy0 + valt - y) * k                 # noqa: E731

    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '
              f'{largura_px:.1f} {altura_px:.1f}" '
              f'width="{LARGURA_FIGURA_PT:.1f}pt" '
              f'height="{LARGURA_FIGURA_PT * altura_px / largura_px:.1f}pt" '
              f'font-family="Arial, Helvetica, sans-serif" '
              f'font-size="{fonte:.1f}">']

    # eixo das barras
    for b in modelo.barras:
        ni, nf = nos[b.ni], nos[b.nf]
        partes.append(f'<line x1="{px(ni.x):.1f}" y1="{py(ni.y):.1f}" '
                      f'x2="{px(nf.x):.1f}" y2="{py(nf.y):.1f}" '
                      f'stroke="#4b5563" stroke-width="2.2"/>')
    # apoios
    for n in nos:
        if n.apoiado:
            X, Y = px(n.x), py(n.y)
            t = 9.0
            partes.append(f'<polygon points="{X:.1f},{Y:.1f} {X - t:.1f},{Y + t * 1.5:.1f} '
                          f'{X + t:.1f},{Y + t * 1.5:.1f}" fill="none" stroke="#111" '
                          f'stroke-width="1.6"/>')
            partes.append(f'<line x1="{X - t * 1.5:.1f}" y1="{Y + t * 1.5:.1f}" '
                          f'x2="{X + t * 1.5:.1f}" y2="{Y + t * 1.5:.1f}" '
                          f'stroke="#111" stroke-width="2"/>')

    rotulos = []
    for idx in curvas:
        s = series[idx]
        ni, nf, ux, uy, nx, ny = curvas[idx]["eixo"]
        for chave in ("max", "min"):
            pts = curvas[idx][chave]
            if not pts:
                continue
            pontos = [f"{px(a):.1f},{py(b):.1f}" for a, b in pts]
            base = [f"{px(ni.x + ux * s['x'][-1]):.1f},{py(ni.y + uy * s['x'][-1]):.1f}",
                    f"{px(ni.x):.1f},{py(ni.y):.1f}"]
            partes.append(f'<polygon points="{" ".join(pontos + base)}" fill="{cor}" '
                          f'fill-opacity="0.16" stroke="{cor}" stroke-width="1.3" '
                          f'stroke-linejoin="round"/>')
            vals = s[chave]
            i_ext = max(range(len(vals)), key=lambda j: abs(vals[j]))
            v = vals[i_ext]
            if abs(v) > 0.08 * pico:
                bx, by = pts[i_ext]
                rotulos.append((px(bx), py(by), v / divisor,
                                1.0 if (nx * v) >= 0 else -1.0))

    vistos = []
    for X, Y, v, lado in rotulos:
        Y = Y + (-fonte * 0.45 if Y < altura_px / 2 else fonte * 1.0)
        if any(abs(X - a) < fonte * 4.6 and abs(Y - b) < fonte * 1.4
               for a, b in vistos):
            continue
        X = min(max(X, fonte * 2.0), largura_px - fonte * 2.0)
        vistos.append((X, Y))
        partes.append(f'<text x="{X:.1f}" y="{Y:.1f}" text-anchor="middle" '
                      f'fill="{cor}" font-weight="bold" '
                      f'font-size="{fonte * 0.95:.1f}">{fmt(v, 1)}</text>')

    partes.append(f'<text x="0" y="{altura_px - fonte * 0.8:.1f}" '
                  f'fill="#4b5563" font-size="{fonte * 0.95:.1f}">'
                  f'Valores em {unidade}; envelope superior e inferior das '
                  f'combinações. Escala do diagrama: {fmt(pico / divisor, 1)} '
                  f'{unidade} = {fmt(ordenada / 100, 2)} m no desenho.</text>')
    partes.append("</svg>")
    return "".join(partes)


def _svg_modelo(modelo, largura_px: float = 900.0) -> str:
    """Esquema do modelo de barras, com nós, apoios e rótulos."""
    nos = modelo.nos
    xs = [n.x for n in nos]
    ys = [n.y for n in nos]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    larg, alt = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    margem = 0.14 * max(larg, alt)
    vx0, vy0 = x0 - margem, y0 - margem
    vlarg, valt = larg + 2 * margem, alt + 2 * margem
    k = largura_px / vlarg
    px = lambda x: (x - vx0) * k                        # noqa: E731
    py = lambda y: (vy0 + valt - y) * k                 # noqa: E731
    f = max(9.0, largura_px / 70.0)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura_px:.1f} '
         f'{valt * k:.1f}" width="{LARGURA_FIGURA_PT:.1f}pt" '
         f'height="{LARGURA_FIGURA_PT * valt * k / largura_px:.1f}pt" '
         f'font-family="Arial, Helvetica, sans-serif" font-size="{f:.1f}">']
    for b in modelo.barras:
        ni, nf = nos[b.ni], nos[b.nf]
        p.append(f'<line x1="{px(ni.x):.1f}" y1="{py(ni.y):.1f}" x2="{px(nf.x):.1f}" '
                 f'y2="{py(nf.y):.1f}" stroke="#0b3d91" stroke-width="3.2"/>')
        mx, my = (ni.x + nf.x) / 2, (ni.y + nf.y) / 2
        if b.rotulo:
            comp = math.hypot(nf.x - ni.x, nf.y - ni.y) or 1.0
            nx, ny = -(nf.y - ni.y) / comp, (nf.x - ni.x) / comp
            desloc = 1.6 * f
            p.append(f'<text x="{px(mx) + nx * desloc:.1f}" '
                     f'y="{py(my) - ny * desloc:.1f}" '
                     f'text-anchor="middle" fill="#1f5fbf" '
                     f'font-size="{f * 0.85:.1f}">{_esc(b.rotulo)}</text>')
    for n in nos:
        X, Y = px(n.x), py(n.y)
        p.append(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="{f * 0.32:.1f}" fill="#fff" '
                 f'stroke="#0b3d91" stroke-width="1.6"/>')
        if n.nome:
            p.append(f'<text x="{X + f * 0.6:.1f}" y="{Y - f * 0.5:.1f}" fill="#111" '
                     f'font-weight="bold" font-size="{f * 0.9:.1f}">{_esc(n.nome)}</text>')
        if n.apoiado:
            t = f * 0.8
            if n.restrito_rz:
                p.append(f'<rect x="{X - t:.1f}" y="{Y:.1f}" width="{2 * t:.1f}" '
                         f'height="{t * 0.8:.1f}" fill="#111"/>')
            else:
                p.append(f'<polygon points="{X:.1f},{Y:.1f} {X - t:.1f},{Y + t * 1.6:.1f} '
                         f'{X + t:.1f},{Y + t * 1.6:.1f}" fill="none" stroke="#111" '
                         f'stroke-width="1.6"/>')
            p.append(f'<line x1="{X - t * 1.7:.1f}" y1="{Y + t * 1.7:.1f}" '
                     f'x2="{X + t * 1.7:.1f}" y2="{Y + t * 1.7:.1f}" stroke="#111" '
                     f'stroke-width="2"/>')
    p.append("</svg>")
    return "".join(p)


# =====================================================================================
# Construtor do documento
# =====================================================================================

class _Doc:
    """Acumula capítulos e seções e monta o sumário com os mesmos títulos."""

    def __init__(self):
        self.partes: List[str] = []
        self.toc: List[Tuple[int, str, str]] = []
        self.n1 = 0
        self.n2 = 0
        self.n_fig = 0
        self.n_tab = 0

    def cap(self, titulo: str):
        self.n1 += 1
        self.n2 = 0
        cid = f"c{self.n1}"
        self.toc.append((1, cid, f"{self.n1}. {titulo}"))
        self.partes.append(
            f'<section class="capitulo" id="{cid}">'
            f'<h1 class="cap"><span class="num">{self.n1}.</span>'
            f'<span class="tit">{_esc(titulo)}</span></h1>')
        return self

    def fim_cap(self):
        self.partes.append("</section>")
        return self

    def sec(self, titulo: str):
        self.n2 += 1
        cid = f"c{self.n1}-{self.n2}"
        self.toc.append((2, cid, f"{self.n1}.{self.n2} {titulo}"))
        self.partes.append(
            f'<h2 id="{cid}">{self.n1}.{self.n2} {_esc(titulo)}</h2>')
        return self

    def add(self, html: str):
        self.partes.append(html)
        return self

    def p(self, texto: str):
        return self.add(f"<p>{texto}</p>")

    def tabela(self, colunas, linhas, legenda="", **kw):
        self.n_tab += 1
        cap = f"Tabela {self.n_tab} — {_esc(legenda)}" if legenda else ""
        return self.add(_tabela(colunas, linhas, cap, **kw))

    def figura(self, svg: str, legenda: str, classe: str = ""):
        self.n_fig += 1
        self.partes.append(
            f'<figure class="fig {classe}">{svg}'
            f'<figcaption><b>Figura {self.n_fig}</b> — {_esc(legenda)}</figcaption>'
            f"</figure>")
        return self

    def sumario(self) -> str:
        itens = "".join(
            f'<li class="n{n}"><a href="#{cid}">{_esc(t)}</a>'
            f'<span class="pt"></span><a class="pg" href="#{cid}"></a></li>'
            for n, cid, t in self.toc)
        return f'<div class="sumario"><h1>Sumário</h1><ol>{itens}</ol></div>'

    def corpo(self) -> str:
        return "".join(self.partes)


# =====================================================================================
# Leitura defensiva do ProjetoGalpao
# =====================================================================================

def _itens(fonte) -> List[Tuple[str, Any]]:
    if isinstance(fonte, dict):
        return list(fonte.items())
    return []


def _e_composicao(v) -> bool:
    return hasattr(v, "itens") and hasattr(v, "total")


def _passos_de(v) -> List[Passo]:
    ps = getattr(v, "passos", None)
    if callable(ps):
        try:
            ps = ps()
        except Exception:
            ps = None
    return list(ps) if isinstance(ps, (list, tuple)) else []


def _vento(projeto: ProjetoGalpao):
    """O objeto de vento, venha ele direto ou dentro do dicionário `projeto.vento`."""
    v = projeto.vento
    if hasattr(v, "Vk"):
        return v
    for _, x in _itens(v):
        if hasattr(x, "Vk") and hasattr(x, "pressoes"):
            return x
    return None


def _envoltoria(projeto: ProjetoGalpao):
    """A envoltória da análise, se houver."""
    e = projeto.esforcos
    if hasattr(e, "barras") and hasattr(e, "modelo"):
        return e
    for _, x in _itens(e):
        if hasattr(x, "barras") and hasattr(x, "modelo"):
            return x
    return None


def _modelo(projeto: ProjetoGalpao, env=None):
    if env is not None and getattr(env, "modelo", None) is not None:
        return env.modelo
    for _, x in _itens(projeto.esforcos):
        if hasattr(x, "nos") and hasattr(x, "barras"):
            return x
    return None


def _series_envoltoria(env) -> Dict[int, dict]:
    """Por barra, o x amostrado e os envelopes de N, V e M entre todos os casos."""
    saida: Dict[int, dict] = {}
    resultados = getattr(env, "resultados", {}) or {}
    if not resultados:
        return saida
    for k in range(len(env.barras)):
        base = None
        env_max = {"N": None, "V": None, "M": None}
        env_min = {"N": None, "V": None, "M": None}
        for r in resultados.values():
            try:
                d = r.barras[k].diagrama
            except Exception:
                continue
            if base is None:
                base = list(d.x)
            for g in ("N", "V", "M"):
                vals = list(getattr(d, g))
                if len(vals) != len(base):
                    continue
                if env_max[g] is None:
                    env_max[g] = list(vals)
                    env_min[g] = list(vals)
                else:
                    env_max[g] = [max(a, b) for a, b in zip(env_max[g], vals)]
                    env_min[g] = [min(a, b) for a, b in zip(env_min[g], vals)]
        if base is None or env_max["M"] is None:
            continue
        saida[k] = {"x": base,
                    "N": {"x": base, "max": env_max["N"], "min": env_min["N"]},
                    "V": {"x": base, "max": env_max["V"], "min": env_min["V"]},
                    "M": {"x": base, "max": env_max["M"], "min": env_min["M"]}}
    return saida


# =====================================================================================
# Blocos: verificações, resultados, elementos
# =====================================================================================

def _passos_html(passos: Sequence[Passo]) -> str:
    if not passos:
        return ('<p class="pequeno">Sem memória de cálculo registrada para esta '
                "verificação.</p>")
    linhas = []
    for p in passos:
        linhas.append([(_esc(p.texto), "txt"), (p.formula or "", "frm"),
                       (p.conta or "", "cta"), (p.valor or "", "val"),
                       (_esc(p.norma), "nrm")])
    return _tabela(["Passo", "Fórmula", "Com os números", "Resultado", "Norma"],
                   linhas, "", "passos")


def _barra_aproveitamento(razao: float, ok: bool) -> str:
    largura = min(razao, 1.35) / 1.35 * 100.0
    lim = 1.0 / 1.35 * 100.0
    cls = "barra" if ok else "barra reprova"
    return (f'<div class="{cls}"><i style="width:{largura:.1f}%"></i>'
            f'<span class="lim" style="left:{lim:.1f}%"></span></div>'
            f'<div class="pequeno">Aproveitamento {fmt(razao * 100, 1)} % '
            f'(a marca é o limite de 100 %).</div>')


def _verificacao_html(v: Verificacao) -> str:
    if v.dispensada:
        cls, selo = "verif dispensada", '<span class="selo na">não se aplica</span>'
    elif v.ok:
        cls, selo = "verif", '<span class="selo ok">atende</span>'
    else:
        cls, selo = "verif reprova", '<span class="selo nao">NÃO ATENDE</span>'
    cabecalho = (f'<div class="cab"><span class="t">{_esc(v.titulo)}</span>'
                 f'<span class="n">{_esc(v.norma)}</span>{selo}</div>')
    cartoes = ""
    if not v.dispensada:
        cartoes = (
            '<div class="resultado">'
            f'<div class="c"><div class="k">Solicitante S<sub>d</sub></div>'
            f'<div class="v">{fmt(v.Sd, 2)}</div>'
            f'<div class="u">{_esc(v.unidade)}</div></div>'
            f'<div class="c"><div class="k">Resistente R<sub>d</sub></div>'
            f'<div class="v">{fmt(v.Rd, 2)}</div>'
            f'<div class="u">{_esc(v.unidade)}</div></div>'
            f'<div class="c"><div class="k">S<sub>d</sub>/R<sub>d</sub></div>'
            f'<div class="v">{fmt(v.razao, 3)}</div><div class="u">—</div></div>'
            f'<div class="c"><div class="k">Folga</div>'
            f'<div class="v">{fmt(v.folga, 1)}</div><div class="u">%</div></div>'
            "</div>" + _barra_aproveitamento(v.razao, v.ok))
    obs = f'<p class="obs">{_esc(v.observacao)}</p>' if v.observacao else ""
    return (f'<div class="{cls}">{cabecalho}<div class="corpo">'
            f"{_passos_html(v.passos)}{cartoes}{obs}</div></div>")


def _resumo_verificacoes(r: Resultado) -> str:
    linhas = []
    for v in r.verificacoes:
        if v.dispensada:
            estado, cls = "não se aplica", "c"
        else:
            estado, cls = ("atende", "c ok") if v.ok else ("NÃO ATENDE", "c nao")
        linhas.append([(_esc(v.titulo), "l"), (_esc(v.norma), "l"),
                       (fmt(v.Sd, 2) if not v.dispensada else "—", "r"),
                       (fmt(v.Rd, 2) if not v.dispensada else "—", "r"),
                       (_esc(v.unidade), "c"),
                       (fmt(v.razao, 3) if not v.dispensada else "—", "r b"),
                       (estado, cls)])
    return _tabela(["Estado-limite verificado", "Item da norma", "S<sub>d</sub>",
                    "R<sub>d</sub>", "Unidade", "S<sub>d</sub>/R<sub>d</sub>",
                    "Situação"], linhas, "",
                   "tab small", ["31%", "19%", "10%", "10%", "12%", "9%", "9%"])


#: Rótulos das grandezas que o cálculo publica em `esforcos` e `geometria`.
ROTULOS_GRANDEZA = {
    # esforços
    "N_kN": "Força normal N<sub>Sd</sub> (kN)",
    "V_kN": "Esforço cortante V<sub>Sd</sub> (kN)",
    "M_kNm": "Momento fletor M<sub>Sd</sub> (kN·m)",
    "M_kNcm": "Momento fletor M<sub>Sd</sub> (kN·cm)",
    "caso": "Combinação que governa",
    "q_gravidade_kN_m": "Carga de cálculo, gravidade (kN/m)",
    "q_succao_kN_m": "Carga de cálculo, sucção (kN/m)",
    "q_pressao_kN_m": "Carga de cálculo, pressão do vento (kN/m)",
    "succao_kN_m2": "Sucção do vento (kN/m²)",
    "pressao_kN_m2": "Pressão do vento (kN/m²)",
    "F_oitao_kN": "Força do vento no oitão levada à cobertura (kN)",
    "cortante_kN": "Cortante no painel de apoio (kN)",
    # geometria e travamentos
    "vao_m": "Vão (m)",
    "comprimento_m": "Comprimento (m)",
    "altura_m": "Altura (m)",
    "espacamento_m": "Espaçamento (m)",
    "linhas": "Linhas por água",
    "por_agua": "Linhas por água",
    "n_correntes": "Linhas de correntes",
    "recuo_beiral_m": "Primeira terça a partir do beiral (m)",
    "recuo_cumeeira_m": "Última terça até a cumeeira (m)",
    "fiadas_por_lado": "Fiadas por lado",
    "cotas_fiadas_m": "Alturas das fiadas a partir do piso (m)",
    "Lb_cm": "Comprimento destravado L<sub>b</sub> (cm)",
    "Ly_cm": "Comprimento destravado fora do plano L<sub>y</sub> (cm)",
    "Kx": "Coeficiente de flambagem no plano K<sub>x</sub>",
    "misula_m": "Comprimento da mísula (m)",
    "paineis": "Painéis ao longo do vão",
    "diagonais_por_painel": "Diagonais por painel",
    "vaos_contraventados": "Vãos contraventados",
    "quantidade": "Quantidade de diagonais",
    # dados adotados nas verificações: as chaves que são palavras; os símbolos da
    # norma (Ag, Cb, M_Rd_FLT, lambda_0...) saem pela regra de `_rotulo_grandeza`
    "Lt_cm": "Comprimento da peça L<sub>t</sub> (cm)",
    "inclinacao_graus": "Inclinação da peça (°)",
    "massa_kg_m": "Massa linear (kg/m)",
    "aco": "Aço",
    "aco_placa": "Aço da placa",
    "fy": "Resistência ao escoamento f<sub>y</sub>",
    "dimensionamento_automatico": "Dimensionamento automático",
    "espacamento_tercas_real": "Espaçamento real entre terças",
    "linhas_tercas_por_agua": "Linhas de terças por água",
    "pre_pilar": "Pré-dimensionamento do pilar",
    "pre_viga": "Pré-dimensionamento da viga",
    "g_cobertura": "Carga permanente da cobertura g",
    "succao_telhado": "Sucção no telhado",
    "joelho_kNm": "Momento no joelho (kN·m)",
    "cumeeira_kNm": "Momento na cumeeira (kN·m)",
    "razao_N": "Parcela de N na interação",
    "razao_Mx": "Parcela de M<sub>x</sub> na interação",
    "razao_My": "Parcela de M<sub>y</sub> na interação",
    "N_Rd_escoamento": "N<sub>Rd</sub> por escoamento da seção bruta",
    "N_Rd_ruptura": "N<sub>Rd</sub> por ruptura da seção líquida",
    "governa": "Verificação que governa",
    "modo_critico": "Modo crítico",
    # ligações (chapa de topo, modelo T-stub; dimensões em cm)
    "braco": "Braço do binário d − t<sub>f</sub> (cm)",
    "T_por_parafuso": "Tração por parafuso",
    "n_tracionados": "Parafusos tracionados",
    "n_total_parafusos": "Número total de parafusos",
    "t_chapa": "Espessura da chapa t (cm)",
    "largura_chapa": "Largura da chapa (cm)",
    "gabarito": "Gabarito g (cm)",
    "passo_linhas": "Passo entre linhas de parafusos (cm)",
    "p_tributario": "Largura tributária p (cm)",
    "a_alavanca": "Distância a do efeito alavanca (cm)",
    "b_alavanca": "Distância b do efeito alavanca (cm)",
    "diametro": "Diâmetro do parafuso",
    "d_furo": "Diâmetro do furo d<sub>h</sub>",
    # bases (modelo AISC da placa)
    "n_linha": "n′",
    "l_balanco": "λ·n′",
    "A1_necessaria": "Área de apoio necessária A<sub>1</sub>",
    "n_chumbadores": "Número de chumbadores",
    "diametro_chumbador": "Diâmetro do chumbador",
    "f_chumbador": "Força no chumbador",
    "x_chumbador": "Posição x do chumbador",
    "borda_chumbador": "Distância do chumbador à borda",
    "t_grout": "Espessura do graute",
    "t_necessaria_mm": "Espessura necessária da placa (mm)",
    "furo_placa_mm": "Furo na placa de base (mm)",
    "altura_misula_mm": "Altura da mísula (mm)",
}

#: Letras gregas escritas por extenso nas chaves do cálculo.
GREGAS = {"lambda": "λ", "chi": "χ", "sigma": "σ", "ell": "ℓ", "phi": "φ",
          "gamma": "γ", "alfa": "α", "beta": "β", "delta": "δ", "tau": "τ", "rho": "ρ"}
#: Sufixos de unidade das chaves, do mais longo para o mais curto.
UNIDADES_CHAVE = (("_kN_m2", "kN/m²"), ("_kN_cm2", "kN/cm²"), ("_kN_m", "kN/m"),
                  ("_kg_m", "kg/m"), ("_kNcm", "kN·cm"), ("_kNm", "kN·m"),
                  ("_MPa", "MPa"), ("_kN", "kN"), ("_mm", "mm"), ("_cm", "cm"),
                  ("_m2", "m²"), ("_kg", "kg"), ("_graus", "°"), ("_m", "m"))
#: Índices que vão para o subscrito do símbolo: N_Rd, M_Rd_FLT, lambda_0, h_ef.
INDICES = {"Rd", "Sd", "Rk", "Sk", "FLT", "FLM", "FLA", "pl", "ef", "x", "y", "z",
           "c", "t", "b", "p", "r", "e", "g", "n", "0", "1", "2"}
#: Palavras das chaves que perderam o acento.
ACENTOS = {"inclinacao": "inclinação", "succao": "sucção", "pressao": "pressão",
           "aco": "aço", "espacamento": "espaçamento", "tributario": "tributário",
           "necessaria": "necessária", "diametro": "diâmetro", "balanco": "balanço",
           "interacao": "interação", "critico": "crítico", "misula": "mísula",
           "automatico": "automático", "razao": "razão", "tercas": "terças",
           "terca": "terça", "agua": "água", "vao": "vão", "numero": "número"}
#: Palavras de até três letras, que não podem ser lidas como símbolo.
PALAVRAS_CURTAS = {"aco", "pre", "por", "de", "da", "do", "vao", "cor"}


def _simbolo(base: str, indices: Sequence[str]) -> str:
    """"Mx" + ["Rd"] -> M<sub>x,Rd</sub>; "lambda" + ["0"] -> λ<sub>0</sub>."""
    if base in GREGAS:
        letra, resto = GREGAS[base], ""
    elif 1 < len(base) <= 3 and base[0].isalpha() and (base[1:].islower() or base[1:].isdigit()):
        letra, resto = base[0], base[1:]
    else:
        letra, resto = base, ""
    sub = ",".join(([resto] if resto else []) + list(indices))
    return _esc(letra) + (f"<sub>{_esc(sub)}</sub>" if sub else "")


def _rotulo_grandeza(chave: str) -> str:
    """Rótulo legível de uma chave do cálculo.

    Chave conhecida usa o rótulo da tabela. As outras seguem a grafia da norma: o
    símbolo sai com índice (M_Rd_FLT -> M<sub>Rd,FLT</sub>), sem mexer na caixa, porque
    t (espessura) e T (força de tração) são grandezas diferentes; chave que é palavra
    ganha acento e inicial maiúscula; o sufixo de unidade vai para o parêntese.
    """
    if chave in ROTULOS_GRANDEZA:
        return ROTULOS_GRANDEZA[chave]
    k, unidade = str(chave), ""
    for sufixo, u in UNIDADES_CHAVE:
        if k.endswith(sufixo) and len(k) > len(sufixo):
            k, unidade = k[:-len(sufixo)], u
            break
    partes = [p for p in k.split("_") if p]
    if not partes:
        return _esc(chave)
    base, resto = partes[0], partes[1:]
    if base in GREGAS or (len(base) <= 3 and base.lower() not in PALAVRAS_CURTAS):
        indices = []
        while resto and resto[0] in INDICES:
            indices.append(resto.pop(0))
        texto = _simbolo(base, indices)
        if resto:
            texto += " " + _esc(" ".join(ACENTOS.get(p, p) for p in resto))
    else:
        palavras = " ".join(ACENTOS.get(p, p) for p in partes)
        texto = _esc(palavras[:1].upper() + palavras[1:])
    return texto + (f" ({unidade})" if unidade else "")


def _valor_grandeza(v) -> str:
    """Como `_valor`, mas listas saem como números separados por ponto e vírgula."""
    if isinstance(v, (list, tuple)):
        return "; ".join(_valor(x) for x in v) if v else "—"
    return _valor(v)


def _repetida(k, d: dict) -> bool:
    """Chave que só repete outra da mesma tabela."""
    k = str(k)
    # o momento em kN·cm é o mesmo valor do kN·m
    if k.endswith("_kNcm") and k[:-5] + "_kNm" in d:
        return True
    # "por_agua" é o mesmo número de "linhas"
    return k == "por_agua" and d.get("linhas") == d.get("por_agua")


def _dic_tabela(d: dict, titulo_chave="Grandeza", titulo_valor="Valor") -> str:
    linhas = [[(_rotulo_grandeza(k), "l"), (_valor_grandeza(v), "r")]
              for k, v in d.items() if not _repetida(k, d)]
    return _tabela([titulo_chave, titulo_valor], linhas, "", "tab small",
                   ["62%", "38%"])


def _alternativas_html(alternativas: Sequence[dict]) -> str:
    if not alternativas:
        return ""
    chaves: List[str] = []
    for a in alternativas:
        for k in a:
            if k not in chaves:
                chaves.append(k)
    linhas = []
    for a in alternativas:
        linhas.append([(_valor(a.get(k, "")), "c" if k != chaves[0] else "l")
                       for k in chaves])
    def cabecalho(k: str) -> str:
        # só a primeira letra vira maiúscula: "S_d/R_d" não pode virar "S d/r d"
        t = k.replace("_", " ").strip()
        return _esc(t[:1].upper() + t[1:])

    return ("<h4>Alternativas testadas</h4>"
            + _tabela([cabecalho(k) for k in chaves], linhas, "", "tab small"))


def _resultado_html(r: Optional[Resultado], doc: _Doc, contexto: str = "") -> str:
    if r is None:
        return _box("<p>Este elemento não traz resultado de verificação: o módulo de "
                    "cálculo correspondente não foi executado.</p>",
                    "Sem verificação", "atencao")
    partes = []
    critica = r.critica
    cab = [("Elemento", _esc(r.elemento))]
    if r.perfil:
        cab.append(("Perfil adotado", f"<b>{_esc(r.perfil)}</b>"))
    if r.material:
        cab.append(("Material", _esc(r.material)))
    cab.append(("Aproveitamento máximo", f"<b>{fmt(r.razao * 100, 1)} %</b>"))
    cab.append(("Verificação que governa",
                _esc(critica.titulo) if critica else "—"))
    cab.append(("Situação", '<b style="color:#1f7a41">atende a todos os '
                            "estados-limites verificados</b>" if r.ok else
                '<b style="color:#a5231a">NÃO ATENDE</b>'))
    partes.append(_chave_valor(cab, "", ("38%", "62%")))
    if r.dados:
        simples = {k: v for k, v in r.dados.items()
                   if isinstance(v, (int, float, str, bool)) or v is None}
        if simples:
            partes.append("<h4>Dados adotados no dimensionamento</h4>")
            partes.append(_dic_tabela(simples))
    partes.append("<h4>Quadro das verificações</h4>")
    partes.append(_resumo_verificacoes(r))
    partes.append("<h4>Memória de cálculo, verificação por verificação</h4>")
    for v in r.verificacoes:
        partes.append(_verificacao_html(v))
    if critica:
        estado = ("atende" if r.ok else "NÃO ATENDE")
        partes.append(_box(
            f"<p>Governa <b>{_esc(critica.titulo)}</b> "
            f"({_esc(critica.norma)}), com S<sub>d</sub>/R<sub>d</sub> = "
            f"<b>{fmt(critica.razao, 3)}</b> — ou seja, {fmt(critica.razao * 100, 1)} % "
            f"da capacidade. O elemento {estado} a todos os estados-limites "
            f"verificados neste memorial.{_esc(contexto)}</p>",
            "Verificação que governa", "ok" if r.ok else "atencao"))
    return "".join(partes)


# =====================================================================================
# Capítulos
# =====================================================================================

def _cap_dados(doc: _Doc, projeto: ProjetoGalpao):
    d = projeto.dados
    doc.cap("Dados de entrada")
    doc.p("Todos os dados informados para o dimensionamento, como foram usados pelo "
          "cálculo. Qualquer divergência entre esta tabela e o que se pretendia "
          "projetar invalida o restante do documento.")
    for titulo, campos in GRUPOS_ENTRADA:
        doc.sec(titulo)
        linhas = [[(_esc(_rotulo(c)), "l"), (_valor(getattr(d, c, None)), "r")]
                  for c in campos if hasattr(d, c)]
        doc.tabela(["Campo", "Valor"], linhas, titulo, larguras=["62%", "38%"])

    doc.sec("Grandezas derivadas da geometria")
    doc.tabela(
        ["Grandeza", "Fórmula", "Valor"],
        [[("Ângulo do telhado", "l"), ("θ = arctg(i)", "c"),
          (fmt(d.angulo_telhado, 2, "°"), "r")],
         [("Altura da cumeeira", "l"), ("H + (L/2)·i", "c"),
          (fmt(d.altura_cumeeira, 2, "m"), "r")],
         [("Comprimento inclinado de uma água", "l"), ("(L/2)/cos θ", "c"),
          (fmt(d.comprimento_agua, 2, "m"), "r")],
         [("Número de pórticos", "l"), ("C/e + 1", "c"), (str(d.n_porticos), "r")],
         [("Área coberta", "l"), ("L × C", "c"), (fmt(d.area_coberta, 1, "m²"), "r")],
         [("Área de fechamento lateral e de oitão", "l"),
          ("2·C·H + 2·L·(H + h<sub>cum</sub>)/2", "c"),
          (fmt(2 * d.comprimento * d.pe_direito
               + 2 * d.vao * (d.pe_direito + d.altura_cumeeira) / 2, 1, "m²"), "r")]],
        "Grandezas geométricas derivadas", larguras=["44%", "31%", "25%"])

    doc.sec("Esquema do pórtico")
    svg = _desenho_opcional(projeto, "portico", 172.0, 105.0)
    if svg:
        doc.figura(svg, "Pórtico transversal típico, com a geometria adotada "
                        "(cotas em milímetros).")
    else:
        doc.add(_box("<p>O desenho esquemático do pórtico não pôde ser gerado.</p>",
                     "Desenho indisponível", "atencao"))
    doc.fim_cap()


def _cap_normas(doc: _Doc, projeto: ProjetoGalpao):
    d = projeto.dados
    doc.cap("Normas adotadas e critérios de projeto")
    doc.sec("Normas")
    doc.tabela(["Norma", "Título", "Onde é usada"],
               [[(_esc(n), "l b"), (_esc(t), "l"), (_esc(u), "l")]
                for n, t, u in NORMAS],
               "Normas brasileiras adotadas no dimensionamento",
               larguras=["20%", "38%", "42%"])

    doc.sec("Coeficientes de ponderação das resistências")
    doc.tabela(["Símbolo", "Valor", "Aplicação"],
               [[("γ<sub>a1</sub>", "c"), (fmt(GAMA_A1, 2), "c"),
                 ("Escoamento, flambagem e instabilidade", "l")],
                [("γ<sub>a2</sub>", "c"), (fmt(GAMA_A2, 2), "c"),
                 ("Ruptura (seção líquida, esmagamento, rasgamento)", "l")],
                [("γ<sub>w2</sub>", "c"), (fmt(GAMA_W2, 2), "c"),
                 ("Metal da solda", "l")],
                [("γ<sub>c</sub>", "c"), (fmt(GAMA_C, 2), "c"),
                 ("Concreto sob a placa de base", "l")]],
               "Coeficientes γ das resistências (NBR 8800:2008, Tabela 3)",
               larguras=["16%", "14%", "70%"])

    doc.sec("Coeficientes de ponderação e fatores de combinação das ações")
    doc.add(_coeficientes_acoes_html(projeto))

    doc.sec("Limites de deslocamento adotados")
    H = d.pe_direito
    doc.tabela(["Elemento", "Critério", "Limite adotado", "Origem"],
               [[("Terça de cobertura", "l"), (f"L/{d.flecha_terca}", "c"),
                 (fmt(d.espacamento_porticos * 100 / d.flecha_terca, 2, "cm"), "r"),
                 ("NBR 8800:2008, Anexo C (vão de %s m)"
                  % fmt(d.espacamento_porticos, 2), "l")],
                [("Viga do pórtico", "l"), (f"L/{d.flecha_viga}", "c"),
                 (fmt(d.vao * 100 / d.flecha_viga, 2, "cm"), "r"),
                 ("NBR 8800:2008, Anexo C (vão de %s m)" % fmt(d.vao, 2), "l")],
                [("Deslocamento horizontal do topo do pilar", "l"),
                 (f"H/{d.desloc_horizontal}", "c"),
                 (fmt(H * 100 / d.desloc_horizontal, 2, "cm"), "r"),
                 ("NBR 8800:2008, Anexo C (altura de %s m)" % fmt(H, 2), "l")]],
               "Estados-limites de serviço", larguras=["34%", "14%", "18%", "34%"])
    doc.add(_box(
        "<p>Os deslocamentos são verificados em combinações de <b>serviço</b>, com "
        "γ<sub>f</sub> = 1,0 e o fator ψ correspondente, conforme a NBR 8800:2008, "
        "item 4.7.7.3 e Anexo C. Os limites do Anexo C são recomendações; adotá-los é "
        "decisão de projeto registrada aqui.</p>", "Como os limites são aplicados",
        "norma"))

    doc.sec("Propriedades do aço adotadas")
    doc.tabela(["Propriedade", "Símbolo", "Valor"],
               [[("Módulo de elasticidade", "l"), ("E", "c"),
                 (fmt(E, 0, "kN/cm²"), "r")],
                [("Módulo de elasticidade transversal", "l"), ("G", "c"),
                 (fmt(G, 0, "kN/cm²"), "r")],
                [("Coeficiente de Poisson", "l"), ("ν", "c"), ("0,30", "r")],
                [("Massa específica", "l"), ("ρ", "c"), ("7 850 kg/m³", "r")],
                [("Coeficiente de dilatação térmica", "l"), ("α", "c"),
                 ("1,2 × 10⁻⁵ °C⁻¹", "r")]],
               "Constantes do aço (NBR 8800:2008, item 4.5)",
               larguras=["52%", "16%", "32%"])
    doc.fim_cap()


def _coeficientes_acoes_html(projeto: ProjetoGalpao) -> str:
    """Tabela de γ_f e ψ efetivamente usados nas combinações deste projeto."""
    usados: Dict[Tuple[str, float, float], str] = {}
    for c in projeto.combinacoes or []:
        for p in getattr(c, "parcelas", []) or []:
            chave = (getattr(p, "acao", ""), round(getattr(p, "gama", 0.0), 3),
                     round(getattr(p, "psi", 1.0), 3))
            usados.setdefault(chave, getattr(p, "papel", ""))
    if usados:
        linhas = [[(_esc(acao), "l"), (fmt(g, 2), "c"), (fmt(psi, 2), "c"),
                   (fmt(g * psi, 3), "c"), (_esc(papel), "l")]
                  for (acao, g, psi), papel in usados.items()]
        return _tabela(["Ação", "γ<sub>f</sub>", "ψ", "γ<sub>f</sub>·ψ",
                        "Papel na combinação"], linhas,
                       "Coeficientes efetivamente aplicados nas combinações deste "
                       "projeto (NBR 8800:2008, Tabelas 1 e 2)",
                       "tab small", ["32%", "12%", "12%", "14%", "30%"])
    try:
        from nucleo import cargas as C
        linhas = []
        for nome, v in list(getattr(C, "GAMA_G", {}).items()):
            linhas.append([(f"Permanente — {_esc(nome)}", "l"),
                           (_valor(v), "c"), ("—", "c"), ("—", "c"),
                           ("NBR 8800, Tabela 1", "l")])
        for nome, v in list(getattr(C, "GAMA_Q", {}).items()):
            linhas.append([(f"Variável — {_esc(nome)}", "l"), (_valor(v), "c"),
                           ("—", "c"), ("—", "c"), ("NBR 8800, Tabela 1", "l")])
        for nome, v in list(getattr(C, "PSI", {}).items()):
            linhas.append([(f"ψ — {_esc(nome)}", "l"), ("—", "c"), (_valor(v), "c"),
                           ("—", "c"), ("NBR 8800, Tabela 2", "l")])
        if linhas:
            return _tabela(["Ação", "γ<sub>f</sub>", "ψ", "γ<sub>f</sub>·ψ", "Norma"],
                           linhas, "Coeficientes de ponderação e fatores de combinação "
                                   "disponíveis", "tab small")
    except Exception:
        pass
    return _box("<p>Não há combinações montadas neste projeto; os coeficientes γ e ψ "
                "não puderam ser listados.</p>", "Sem combinações", "atencao")


def _cap_cargas(doc: _Doc, projeto: ProjetoGalpao):
    doc.cap("Ações e cargas")
    doc.sec("Composição das cargas permanentes e variáveis")
    encontrou = False
    for chave, valor in _itens(projeto.cargas):
        rotulo = _esc(str(chave).replace("_", " ").capitalize())
        if _e_composicao(valor):
            encontrou = True
            doc.add(f"<h3>{rotulo}: {_esc(getattr(valor, 'titulo', ''))}</h3>")
            unidade = getattr(valor, "unidade", "")
            linhas = [[(_esc(i.descricao), "l"), (fmt(i.valor, 3), "r"),
                       (_esc(unidade), "c"), (_esc(i.fonte), "l")]
                      for i in valor.itens]
            rodape = [[("Total", "l b"), (fmt(valor.total, 3), "r b"),
                       (_esc(unidade), "c b"),
                       (_esc(getattr(valor, "norma", "")), "l b")]]
            doc.tabela(["Parcela", "Valor", "Unidade", "Origem"], linhas,
                       f"{getattr(valor, 'titulo', rotulo)} — composição parcela a "
                       "parcela", larguras=["44%", "14%", "12%", "30%"],
                       rodape=rodape)
        elif _passos_de(valor):
            encontrou = True
            doc.add(f"<h3>{rotulo}</h3>")
            doc.add(_passos_html(_passos_de(valor)))
    escalares = {k: v for k, v in _itens(projeto.cargas)
                 if isinstance(v, (int, float, str, bool))}
    if escalares:
        encontrou = True
        doc.add("<h3>Demais valores de carga informados</h3>")
        doc.add(_dic_tabela(escalares))
    if not encontrou:
        doc.add(_box("<p>O projeto não trouxe a composição de cargas (o orquestrador "
                     "ainda não preencheu <code>projeto.cargas</code>). Os valores de "
                     "entrada estão no capítulo 1.</p>",
                     "Composição de cargas indisponível", "atencao"))

    _sec_vento(doc, projeto)
    doc.fim_cap()


def _sec_vento(doc: _Doc, projeto: ProjetoGalpao):
    v = _vento(projeto)
    doc.sec("Vento (NBR 6123:1988)")
    if v is None:
        escalares = {k: x for k, x in _itens(projeto.vento)
                     if isinstance(x, (int, float, str, bool))}
        if escalares:
            doc.p("Valores de vento informados pelo cálculo:")
            doc.add(_dic_tabela(escalares))
        else:
            doc.add(_box("<p>O projeto não trouxe o cálculo do vento.</p>",
                         "Vento indisponível", "atencao"))
        return

    d = projeto.dados
    doc.p("A pressão dinâmica do vento sai da velocidade característica "
          "V<sub>k</sub> = V<sub>0</sub>·S<sub>1</sub>·S<sub>2</sub>·S<sub>3</sub>, e a "
          "pressão efetiva em cada superfície, da diferença entre o coeficiente de "
          "pressão externa e o interno: Δp = (C<sub>e</sub> − C<sub>pi</sub>)·q.")
    doc.tabela(
        ["Grandeza", "Símbolo", "Valor", "Origem"],
        [[("Velocidade básica", "l"), ("V<sub>0</sub>", "c"),
          (fmt(v.V0, 1, "m/s"), "r"),
          (_esc(d.cidade or "informada no projeto") + " — NBR 6123, Figura 1", "l")],
         [("Fator topográfico", "l"), ("S<sub>1</sub>", "c"), (fmt(v.S1, 2), "r"),
          ("NBR 6123, item 5.2", "l")],
         [("Fator de rugosidade e dimensões", "l"), ("S<sub>2</sub>", "c"),
          (fmt(v.S2, 3), "r"),
          (f"categoria {_esc(v.categoria)}, classe {_esc(v.classe)}, "
           f"z = {fmt(v.z, 1, 'm')} — NBR 6123, item 5.3", "l")],
         [("Fator estatístico", "l"), ("S<sub>3</sub>", "c"), (fmt(v.S3, 2), "r"),
          (f"grupo {v.grupo} — NBR 6123, Tabela 3", "l")],
         [("Velocidade característica", "l"), ("V<sub>k</sub>", "c"),
          (fmt(v.Vk, 2, "m/s"), "r"),
          ("V<sub>0</sub>·S<sub>1</sub>·S<sub>2</sub>·S<sub>3</sub>", "l")],
         [("Pressão dinâmica", "l"), ("q", "c"), (fmt(v.q, 3, "kN/m²"), "r"),
          ("q = 0,613·V<sub>k</sub>² (N/m²) — NBR 6123, item 4.2", "l")]],
        "Velocidade e pressão dinâmica do vento",
        larguras=["30%", "10%", "16%", "44%"])

    passos = _passos_de(v)
    if passos:
        doc.add("<h3>Memória de cálculo dos fatores do vento</h3>")
        doc.add(_passos_html(passos))

    coef = getattr(v, "coeficientes", None)
    if coef is not None and getattr(coef, "coeficientes", None):
        doc.add("<h3>Coeficientes de pressão externa C<sub>e</sub></h3>")
        doc.p(f"Relações geométricas: h/b = {fmt(getattr(coef, 'h_b', 0), 3)} "
              f"({_esc(getattr(coef, 'faixa_h_b', ''))}) e "
              f"a/b = {fmt(getattr(coef, 'a_b', 0), 3)} "
              f"({_esc(getattr(coef, 'faixa_a_b', ''))}); "
              f"θ = {fmt(getattr(coef, 'theta', 0), 1)}°.")
        linhas = [[(_esc(c.direcao), "c"), (_esc(c.superficie), "l"),
                   (_esc(c.letra), "c"), (_esc(c.zona), "l"), (fmt(c.Ce, 2), "r"),
                   ("local" if c.local else "estrutural", "c")]
                  for c in coef.coeficientes]
        doc.tabela(["Direção", "Superfície", "Notação", "Zona", "C<sub>e</sub>",
                    "Tipo"], linhas,
                   "Coeficientes de pressão externa por face (NBR 6123, Tabelas 4 e 5)",
                   larguras=["16%", "27%", "11%", "24%", "11%", "11%"])
        obs = getattr(coef, "observacoes", None)
        if obs:
            doc.add("<ul class='pequeno'>"
                    + "".join(f"<li>{_esc(o)}</li>" for o in obs) + "</ul>")

    casos = getattr(v, "casos_cpi", None)
    if casos:
        doc.add("<h3>Coeficiente de pressão interna C<sub>pi</sub></h3>")
        linhas = []
        for c in casos:
            linhas.append([(_esc(getattr(c, "nome", getattr(c, "caso", ""))), "l"),
                           (fmt(getattr(c, "Cpi", 0.0), 2), "c"),
                           (_esc(getattr(c, "descricao", getattr(c, "obs", ""))), "l"),
                           (_esc(getattr(c, "norma", "")), "l")])
        doc.tabela(["Caso", "C<sub>pi</sub>", "Situação", "Norma"], linhas,
                   "Casos de pressão interna considerados (NBR 6123, item 6.2)",
                   larguras=["24%", "10%", "42%", "24%"])

    pressoes = getattr(v, "pressoes", None)
    if pressoes:
        doc.add("<h3>Pressões efetivas</h3>")
        linhas = [[(_esc(p.direcao), "c"), (_esc(p.superficie), "l"),
                   (_esc(p.letra), "c"), (_esc(p.zona), "l"), (fmt(p.Ce, 2), "r"),
                   (fmt(p.Cpi, 2), "r"), (_esc(p.caso_cpi), "l"),
                   (fmt(p.p, 3), "r b")]
                  for p in pressoes if not p.local]
        doc.tabela(["Direção", "Superfície", "Not.", "Zona", "C<sub>e</sub>",
                    "C<sub>pi</sub>", "Caso", "Δp (kN/m²)"], linhas,
                   "Pressões efetivas por superfície — positivo é sobrepressão, "
                   "negativo é sucção",
                   larguras=["12%", "21%", "7%", "16%", "8%", "8%", "16%", "12%"])
        try:
            crit = v.critica()
            doc.add(_box(
                f"<p>A maior sucção do galpão é "
                f"<b>{fmt(crit.p, 3, 'kN/m²')}</b> em "
                f"{_esc(crit.rotulo)}, com vento {_esc(crit.direcao)} e "
                f"{_esc(crit.caso_cpi)}. É ela que dimensiona terças, fixações de "
                "telha e as ligações que podem inverter de sinal.</p>",
                "Sucção que governa", "norma"))
        except Exception:
            pass
    obs = getattr(v, "observacoes", None)
    if obs:
        doc.add("<ul class='pequeno'>" + "".join(f"<li>{_esc(o)}</li>" for o in obs)
                + "</ul>")


def _cap_combinacoes(doc: _Doc, projeto: ProjetoGalpao):
    doc.cap("Combinações de ações")
    combs = list(projeto.combinacoes or [])
    if not combs:
        doc.add(_box("<p>O projeto não trouxe combinações montadas.</p>",
                     "Combinações indisponíveis", "atencao"))
        doc.fim_cap()
        return
    doc.sec("Quadro das combinações")
    doc.p("Cada combinação é a soma das ações características multiplicadas pelo seu "
          "coeficiente de ponderação γ<sub>f</sub> e, quando a ação é variável "
          "secundária, pelo fator de combinação ψ<sub>0</sub> "
          "(NBR 8681:2003 e NBR 8800:2008, item 4.7).")
    linhas = []
    for c in combs:
        linhas.append([(_esc(getattr(c, "nome", "")), "l b"),
                       (_esc(getattr(c, "tipo", "")), "l"),
                       (_esc(getattr(c, "principal", "")), "l"),
                       (_esc(getattr(c, "expressao", "")), "l"),
                       (fmt(float(getattr(c, "total", 0.0)), 3), "r b")])
    doc.tabela(["Combinação", "Tipo", "Ação principal", "Expressão", "Resultado"],
               linhas, "Combinações consideradas",
               larguras=["16%", "16%", "16%", "37%", "15%"])

    doc.sec("Parcelas de cada combinação")
    for c in combs:
        doc.add(f"<h3>{_esc(getattr(c, 'nome', ''))} "
                f"<span class='pequeno'>({_esc(getattr(c, 'tipo', ''))})</span></h3>")
        parcelas = getattr(c, "parcelas", []) or []
        linhas = [[(_esc(getattr(p, "acao", "")), "l"),
                   (_esc(getattr(p, "papel", "")), "l"),
                   (fmt(getattr(p, "gama", 0.0), 2), "c"),
                   (fmt(getattr(p, "psi", 1.0), 2), "c"),
                   (fmt(getattr(p, "valor", 0.0), 3), "r"),
                   (fmt(getattr(p, "contribuicao", 0.0), 3), "r b"),
                   (_esc(getattr(p, "norma", "")), "l")] for p in parcelas]
        rodape = [[("Total", "l b"), ("", "l"), ("", "c"), ("", "c"), ("", "r"),
                   (fmt(float(getattr(c, "total", 0.0)), 3), "r b"),
                   (_esc(getattr(c, "norma", "")), "l")]]
        doc.tabela(["Ação", "Papel", "γ<sub>f</sub>", "ψ", "Valor característico",
                    "Contribuição", "Norma"], linhas, "", larguras=[
                        "18%", "20%", "8%", "7%", "15%", "13%", "19%"], rodape=rodape)
    doc.fim_cap()


def _cap_esforcos(doc: _Doc, projeto: ProjetoGalpao):
    doc.cap("Esforços solicitantes")
    env = _envoltoria(projeto)
    modelo = _modelo(projeto, env)

    if modelo is not None:
        doc.sec("Modelo de análise")
        doc.p("O pórtico é analisado como pórtico plano pelo método da rigidez, com "
              "barras prismáticas e as mísulas representadas por trechos de maior "
              "inércia junto aos joelhos.")
        doc.figura(_svg_modelo(modelo), "Modelo de barras do pórtico, com os nós "
                                        "nomeados e as condições de apoio.")
        linhas = []
        for i, b in enumerate(modelo.barras):
            ni, nf = modelo.nos[b.ni], modelo.nos[b.nf]
            L = math.hypot(nf.x - ni.x, nf.y - ni.y)
            linhas.append([(_esc(b.rotulo or f"barra {i}"), "l"),
                           (_esc(ni.nome or str(b.ni)), "c"),
                           (_esc(nf.nome or str(b.nf)), "c"),
                           (fmt(L / 100, 3, "m"), "r"), (fmt(b.A, 2, "cm²"), "r"),
                           (fmt(b.I, 0, "cm⁴"), "r"),
                           ("rótula" if (b.rotula_i or b.rotula_f) else "rígida", "c")])
        doc.tabela(["Barra", "Nó inicial", "Nó final", "Comprimento", "A", "I",
                    "Extremidades"], linhas, "Barras do modelo",
                   larguras=["22%", "12%", "12%", "16%", "13%", "13%", "12%"])

    if env is None:
        doc.add(_box("<p>O projeto não trouxe a envoltória de esforços. Os esforços "
                     "usados em cada elemento estão no capítulo 6.</p>",
                     "Envoltória indisponível", "atencao"))
        escalares = {k: x for k, x in _itens(projeto.esforcos)
                     if isinstance(x, (int, float, str, bool))}
        if escalares:
            doc.add(_dic_tabela(escalares))
        doc.fim_cap()
        return

    doc.sec("Envoltória de esforços por barra")
    casos = ", ".join(env.casos)
    doc.p(f"Envoltória dos casos de carga: {_esc(casos)}. Momentos em kN·m, forças em "
          "kN, posições medidas a partir do nó inicial da barra.")
    linhas = []
    for b in env.barras:
        linhas.append([
            (_esc(b.rotulo), "l b"),
            (fmt(b.N_min.valor, 1), "r"), (fmt(b.N_max.valor, 1), "r"),
            (fmt(b.V_min.valor, 1), "r"), (fmt(b.V_max.valor, 1), "r"),
            (fmt(b.M_min.valor / 100.0, 1), "r"), (fmt(b.M_max.valor / 100.0, 1), "r"),
            (_esc(b.absoluto("M").caso), "l"),
            (fmt(b.absoluto("M").x / 100.0, 2), "r")])
    doc.tabela(["Barra", "N<sub>mín</sub>", "N<sub>máx</sub>", "V<sub>mín</sub>",
                "V<sub>máx</sub>", "M<sub>mín</sub>", "M<sub>máx</sub>",
                "Caso que governa M", "x de M (m)"], linhas,
               "Envoltória de esforços (kN e kN·m)",
               larguras=["17%", "9%", "9%", "9%", "9%", "9%", "9%", "19%", "10%"])

    series = _series_envoltoria(env)
    if series and modelo is not None:
        doc.sec("Diagramas da envoltória")
        doc.p("Cada diagrama traz o envelope superior e o inferior de todos os casos, "
              "traçado perpendicularmente ao eixo de cada barra.")
        doc.figura(_svg_esforcos(modelo, {k: s["M"] for k, s in series.items()},
                                 "M", "kN·m", "#0b3d91", divisor=100.0),
                   "Envoltória do momento fletor (kN·m).")
        doc.figura(_svg_esforcos(modelo, {k: s["V"] for k, s in series.items()},
                                 "V", "kN", "#2e8b57"),
                   "Envoltória do esforço cortante (kN).")
        doc.figura(_svg_esforcos(modelo, {k: s["N"] for k, s in series.items()},
                                 "N", "kN", "#a12a1f"),
                   "Envoltória do esforço normal (kN) — negativo é compressão.")

    reacoes = getattr(env, "reacoes", None)
    if reacoes:
        doc.sec("Reações de apoio")
        doc.p("O projetista de fundações precisa dos dois sinais: a compressão máxima "
              "e o arrancamento (reação vertical mínima), além da força horizontal.")
        linhas = []
        for i, d_ in sorted(reacoes.items()):
            nome = modelo.nos[i].nome or f"nó {i}" if modelo else f"nó {i}"
            linhas.append([
                (_esc(nome), "c b"),
                (fmt(d_["Rx_min"].valor, 1), "r"), (fmt(d_["Rx_max"].valor, 1), "r"),
                (fmt(d_["Ry_min"].valor, 1), "r"), (fmt(d_["Ry_max"].valor, 1), "r"),
                (fmt(d_["Mz_min"].valor / 100.0, 1), "r"),
                (fmt(d_["Mz_max"].valor / 100.0, 1), "r"),
                (_esc(d_["Ry_min"].caso), "l")])
        doc.tabela(["Apoio", "H<sub>mín</sub>", "H<sub>máx</sub>", "V<sub>mín</sub>",
                    "V<sub>máx</sub>", "M<sub>mín</sub>", "M<sub>máx</sub>",
                    "Caso de V<sub>mín</sub>"], linhas,
                   "Reações de apoio (kN e kN·m) — V negativo é arrancamento",
                   larguras=["11%", "11%", "11%", "11%", "11%", "11%", "11%", "23%"])

    extras = {k: x for k, x in _itens(projeto.esforcos)
              if isinstance(x, (int, float, str, bool))}
    if extras:
        doc.sec("Deslocamentos e demais resultados da análise")
        doc.add(_dic_tabela(extras))
    doc.fim_cap()


def _cap_elementos(doc: _Doc, projeto: ProjetoGalpao):
    doc.cap("Dimensionamento dos elementos")
    if not projeto.elementos:
        doc.add(_box("<p>Nenhum elemento dimensionado foi entregue ao memorial.</p>",
                     "Sem elementos", "atencao"))
        doc.fim_cap()
        return
    doc.sec("Quadro geral")
    linhas = []
    for e in projeto.elementos:
        crit = e.resultado.critica if e.resultado else None
        linhas.append([(_esc(e.nome), "l b"), (_esc(e.perfil), "l"),
                       (_esc(e.material), "l"), (fmt(e.razao, 3), "r b"),
                       (_esc(crit.titulo) if crit else "—", "l"),
                       ("atende", "c ok") if e.ok else ("NÃO ATENDE", "c nao")])
    doc.tabela(["Elemento", "Perfil adotado", "Aço", "S<sub>d</sub>/R<sub>d</sub>",
                "Verificação que governa", "Situação"], linhas,
               "Resumo do dimensionamento dos elementos",
               larguras=["18%", "18%", "15%", "10%", "27%", "12%"])

    for e in projeto.elementos:
        doc.sec(e.nome)
        if e.esforcos:
            doc.add("<h4>Esforços solicitantes de cálculo</h4>")
            doc.add(_dic_tabela(e.esforcos, "Esforço"))
        if e.geometria:
            doc.add("<h4>Geometria e travamentos adotados</h4>")
            doc.add(_dic_tabela(e.geometria, "Grandeza"))
        doc.add(_resultado_html(e.resultado, doc))
        doc.add(_alternativas_html(e.alternativas))
    doc.fim_cap()


def _desenho_opcional(projeto, funcao: str, largura_mm=172.0, altura_mm=118.0):
    """Desenho de `saida.desenhos` convertido em SVG; `None` se não der para gerar."""
    try:
        from saida import desenhos
        fn = getattr(desenhos, funcao, None)
        if fn is None:
            return None
        return desenho_para_svg(fn(projeto), largura_mm, altura_mm)
    except Exception:
        return None


#: Qual desenho ilustra cada ligação (chave da ligação → função de `saida.desenhos`).
DESENHO_DA_LIGACAO = [
    (("viga-pilar", "viga_pilar", "joelho", "chapa de topo"), "ligacao_viga_pilar"),
    (("cumeeira",), "ligacao_cumeeira"),
    (("base",), "base_pilar"),
    (("terça", "terca"), "detalhe_terca"),
    (("contravent", "gusset", "diagonal"), "detalhe_contraventamento"),
]


def _funcao_desenho(chave: str) -> Optional[str]:
    k = str(chave).lower()
    for palavras, fn in DESENHO_DA_LIGACAO:
        if any(p in k for p in palavras):
            return fn
    return None


def _cap_ligacoes(doc: _Doc, projeto: ProjetoGalpao):
    doc.cap("Ligações e base")
    if not projeto.ligacoes and projeto.base is None:
        doc.add(_box("<p>Nenhuma ligação ou base foi entregue ao memorial.</p>",
                     "Sem ligações", "atencao"))
        doc.fim_cap()
        return

    doc.sec("Quadro geral")
    linhas = []
    for nome, r in projeto.ligacoes.items():
        crit = r.critica if r else None
        linhas.append([(_esc(nome), "l b"), (_esc(r.elemento if r else ""), "l"),
                       (fmt(r.razao if r else 0, 3), "r b"),
                       (_esc(crit.titulo) if crit else "—", "l"),
                       ("atende", "c ok") if (r and r.ok) else ("NÃO ATENDE", "c nao")])
    if projeto.base is not None:
        b = projeto.base
        crit = b.critica
        linhas.append([("base", "l b"), (_esc(b.elemento), "l"),
                       (fmt(b.razao, 3), "r b"),
                       (_esc(crit.titulo) if crit else "—", "l"),
                       ("atende", "c ok") if b.ok else ("NÃO ATENDE", "c nao")])
    doc.tabela(["Chave", "Ligação", "S<sub>d</sub>/R<sub>d</sub>",
                "Verificação que governa", "Situação"], linhas,
               "Resumo das ligações e da base",
               larguras=["18%", "28%", "11%", "31%", "12%"])

    itens = list(projeto.ligacoes.items())
    if projeto.base is not None:
        itens.append(("base do pilar", projeto.base))
    for nome, r in itens:
        doc.sec(str(nome).capitalize())
        fn = _funcao_desenho(nome)
        if fn:
            svg = _desenho_opcional(projeto, fn, 168.0, 112.0)
            if svg:
                doc.figura(svg, f"Detalhe adotado: {nome} (cotas em milímetros).")
        doc.add(_resultado_html(r, doc))
    doc.fim_cap()


def _cap_lista(doc: _Doc, projeto: ProjetoGalpao):
    from . import lista_material as LM
    m = LM.montar(projeto)
    pecas, cons, orc = m["pecas"], m["consumo"], m["orcamento"]
    doc.cap("Lista de material e resumo de consumo")

    doc.sec("Romaneio por marca")
    linhas = [[(_esc(p.marca), "c b"), (_esc(p.descricao), "l"), (_esc(p.perfil), "l"),
               (_esc(p.material), "l"), (str(p.quantidade), "c"),
               (fmt(p.comprimento_m, 2) if p.comprimento_m else "—", "r"),
               (fmt(p.peso_unit_kg, 1), "r"), (fmt(p.peso_total_kg, 0), "r b"),
               (fmt(p.area_pintura_m2, 1) if p.area_pintura_m2 else "—", "r")]
              for p in pecas]
    rodape = [[("", "c"), ("TOTAL", "l b"), ("", "l"), ("", "l"), ("", "c"), ("", "r"),
               ("", "r"), (LM.br(cons["peso_total_kg"], 0), "r b"),
               (LM.br(cons["area_pintura_m2"], 0), "r b")]]
    doc.tabela(["Marca", "Descrição", "Perfil", "Material", "Qtd.", "Comp. (m)",
                "Peso un. (kg)", "Peso tot. (kg)", "Pintura (m²)"], linhas,
               "Romaneio por marca",
               larguras=["6%", "25%", "17%", "12%", "6%", "9%", "9%", "9%", "7%"],
               rodape=rodape)

    doc.sec("Resumo por tipo de peça")
    linhas = [[(_esc(r["tipo"]), "l"), (fmt(r["peso_kg"], 0), "r"),
               (fmt(r["perc"], 1), "c"), (fmt(r["kg_m2"], 2), "r")]
              for r in m["resumo_tipo"]]
    doc.tabela(["Tipo de peça", "Peso (kg)", "% do total", "kg/m²"], linhas,
               "Peso por família de peça", larguras=["52%", "16%", "16%", "16%"],
               rodape=[[("TOTAL", "l b"), (LM.br(cons["peso_total_kg"], 0), "r b"),
                        ("100,0", "c b"), (fmt(cons["kg_m2"], 2), "r b")]])

    doc.sec("Compra por perfil")
    linhas = [[(_esc(r["perfil"]), "l"), (_esc(r["material"]), "l"),
               (fmt(r["kg_m"], 2), "r"), (fmt(r["comprimento_m"], 1), "r"),
               (str(r["barras_6m"]), "c"), (str(r["barras_12m"]), "c"),
               (fmt(r["comprado_m"], 1), "r"), (fmt(r["perda_perc"], 1) + " %", "c")]
              for r in m["resumo_perfil"]]
    doc.tabela(["Perfil", "Material", "kg/m", "Necessário (m)", "Barras 6 m",
                "Barras 12 m", "Comprado (m)", "Perda de corte"], linhas,
               "Quantidade a comprar, em barras comerciais de 6 e 12 m",
               larguras=["21%", "15%", "8%", "13%", "10%", "10%", "12%", "11%"])

    doc.sec("Consumo e orçamento")
    doc.tabela(["Grandeza", "Valor"],
               [[("Peso total da estrutura", "l"),
                 (LM.br(cons["peso_total_kg"], 0) + " kg", "r")],
                [("Área coberta", "l"), (fmt(cons["area_coberta_m2"], 0, "m²"), "r")],
                [("Consumo de aço", "l"), (fmt(cons["kg_m2"], 1, "kg/m²"), "r")],
                [("Área a pintar", "l"), (fmt(cons["area_pintura_m2"], 0, "m²"), "r")],
                [("Área galvanizada", "l"),
                 (fmt(cons["area_galvanizada_m2"], 0, "m²"), "r")],
                [("Volume total de tinta", "l"),
                 (fmt(cons["tinta_total_l"], 0, "L"), "r")]],
               "Resumo de consumo", larguras=["66%", "34%"])
    linhas = [[(_esc(p["parcela"]), "l"), (LM.br(p["rs_kg"], 2), "r"),
               (LM.br(p["valor"], 2), "r"), (fmt(p["perc"], 0) + " %", "c")]
              for p in orc["parcelas"]]
    doc.tabela(["Parcela", "R$/kg", "Valor (R$)", "% do total"], linhas,
               "Estimativa de custo da estrutura",
               larguras=["46%", "16%", "22%", "16%"],
               rodape=[[("TOTAL", "l b"), (LM.br(orc["custo_kg"], 2), "r b"),
                        (LM.br(orc["total"], 2), "r b"), ("100 %", "c b")]])
    doc.add(_box(f"<p>{_esc(orc['nota'])} Equivalem a aproximadamente "
                 f"R$ {LM.br(orc['rs_m2'], 0)} por m² de área coberta, só de "
                 "estrutura metálica.</p>", "Natureza dos valores de custo", "norma"))
    doc.fim_cap()


def _cap_conclusao(doc: _Doc, projeto: ProjetoGalpao):
    d = projeto.dados
    doc.cap("Conclusão e responsabilidade técnica")
    doc.sec("Declaração")
    reprovados = [e.nome for e in projeto.elementos if not e.ok]
    reprovados += [k for k, r in projeto.ligacoes.items() if r and not r.ok]
    if projeto.base is not None and not projeto.base.ok:
        reprovados.append("base do pilar")

    if projeto.ok and not reprovados:
        doc.add(_box(
            f"<p>Os elementos estruturais do galpão <b>{_esc(d.nome)}</b> "
            f"({fmt(d.vao, 1)} × {fmt(d.comprimento, 1)} m, pé-direito "
            f"{fmt(d.pe_direito, 1)} m) <b>atendem a todos os estados-limites "
            "últimos e de serviço verificados neste memorial</b>, com os perfis, "
            "aços, ligações e bases aqui indicados, para as ações e combinações "
            "do capítulo 4.</p>"
            "<p>A verificação se restringe aos estados-limites efetivamente "
            "calculados e listados nos capítulos 6 e 7. Não estão cobertos, salvo "
            "menção expressa: fadiga, incêndio, vibração, ações excepcionais, "
            "fundações, elementos de fechamento e de cobertura, e as fases "
            "provisórias de transporte e montagem.</p>",
            "Conclusão", "ok"))
    else:
        doc.add(_box(
            "<p><b>Há elementos que não atendem aos estados-limites verificados:</b> "
            + _esc(", ".join(reprovados) or "ver capítulos 6 e 7")
            + ". O projeto <b>não pode ser emitido para fabricação</b> neste estado; "
              "reveja os perfis, a geometria ou as ações antes de prosseguir.</p>",
            "Conclusão", "atencao"))

    doc.sec("Avisos e limitações")
    avisos = [a for a in projeto.avisos if a]
    erros = [e for e in projeto.erros if e]
    if erros:
        doc.add(_box("<ul>" + "".join(f"<li>{_esc(e)}</li>" for e in erros) + "</ul>",
                     "Erros registrados no cálculo", "atencao"))
    if avisos:
        doc.add("<ul>" + "".join(f"<li>{_esc(a)}</li>" for a in avisos) + "</ul>")
    else:
        doc.p("Nenhum aviso foi registrado durante o cálculo.")
    doc.add(_box(
        "<p>Este memorial foi <b>gerado automaticamente</b> a partir dos dados de "
        "entrada do capítulo 1. Ele só tem validade depois de conferido, aceito e "
        "assinado por engenheiro civil habilitado, com ART registrada no CREA. A "
        "conferência inclui, no mínimo: a coerência dos dados de entrada, a "
        "adequação do modelo estrutural, a compatibilidade com o projeto "
        "arquitetônico e com o de fundações, e a exequibilidade do detalhamento.</p>",
        "Condição de validade", "atencao"))

    doc.sec("Responsável técnico")
    doc.tabela(["Campo", "Preenchimento"],
               [[("Responsável técnico", "l"), (_esc(d.responsavel or ""), "l")],
                [("CREA nº", "l"), ("", "l")],
                [("ART nº", "l"), ("", "l")],
                [("Empresa", "l"), ("", "l")],
                [("Data de emissão", "l"),
                 (date.today().strftime("%d/%m/%Y"), "l")],
                [("Revisão", "l"), ("R00 — emissão inicial", "l")]],
               "Identificação do responsável técnico",
               larguras=["36%", "64%"])
    doc.add(
        '<div class="assinatura">'
        '<div class="linha"><div class="nome">'
        + _esc(d.responsavel or "________________________________________") +
        '</div><div class="crea">Engenheiro civil — CREA nº ____________ — '
        'ART nº ____________</div></div>'
        f'<div class="data">{_esc(d.local or "____________________")}, '
        f'{_data_extenso(date.today())}</div></div>')
    doc.fim_cap()


# =====================================================================================
# Capa
# =====================================================================================

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def _data_extenso(dt: date) -> str:
    return f"{dt.day} de {MESES[dt.month - 1]} de {dt.year}"


def _capa(projeto: ProjetoGalpao) -> str:
    d = projeto.dados
    hoje = date.today()
    sistema = ("Pórtico de alma cheia de duas águas"
               if "alma" in str(d.tipo_portico).lower()
               else f"Pórtico {d.tipo_portico}")
    sistema += (", bases rotuladas" if d.base_rotulada else ", bases engastadas")
    sistema += (f", mísula de {fmt(d.comprimento_misula, 2)} m" if d.com_misula
                else ", sem mísula")
    resumo = [
        ("Vão × comprimento × pé-direito",
         f"{fmt(d.vao, 1)} × {fmt(d.comprimento, 1)} × {fmt(d.pe_direito, 1)} m"),
        ("Área coberta", fmt(d.area_coberta, 0, "m²")),
        ("Inclinação do telhado",
         f"{fmt(d.inclinacao, 1)} % ({fmt(d.angulo_telhado, 1)}°)"),
        ("Altura da cumeeira", fmt(d.altura_cumeeira, 2, "m")),
        ("Pórticos", f"{d.n_porticos} a cada {fmt(d.espacamento_porticos, 2)} m"),
        ("Sistema estrutural", sistema),
        ("Aço dos perfis", d.aco_perfis),
        ("Vento de projeto",
         f"V₀ = {fmt(d.v0, 1)} m/s, categoria {d.categoria_rugosidade}, "
         f"classe {d.classe}"),
    ]
    linhas = "".join(f'<tr><td class="k">{_esc(k)}</td>'
                     f'<td class="v">{_esc(v)}</td></tr>' for k, v in resumo)
    esquema = _desenho_opcional(projeto, "portico", 172.0, 62.0) or ""
    return f"""
<div class="capa">
  <div class="faixa">
    <div class="sup">Projeto estrutural · estrutura metálica</div>
    <h1>Memorial de cálculo</h1>
    <div class="sub">Galpão industrial em aço — dimensionamento conforme
      ABNT NBR 8800, NBR 14762, NBR 6120, NBR 6123 e NBR 8681</div>
  </div>
  <div class="obra">
    <div class="nome">{_esc(d.nome)}</div>
    <div class="linha"><b>Cliente</b> {_esc(d.cliente or '—')}</div>
    <div class="linha"><b>Local</b> {_esc(d.local or '—')}</div>
    <div class="linha"><b>Responsável técnico</b> {_esc(d.responsavel or '—')}</div>
    <div class="linha"><b>Data</b> {_data_extenso(hoje)}</div>
    <div class="linha"><b>Revisão</b> R00 — emissão inicial</div>
  </div>
  <div class="resumo-obra">
    <div class="t">Resumo do galpão</div>
    <table><tbody>{linhas}</tbody></table>
  </div>
  <div class="esquema">{esquema}</div>
  <div class="rodape">
    <div class="aviso">Documento gerado automaticamente pelo sistema de
      dimensionamento. Só tem validade depois de conferido e assinado por engenheiro
      habilitado, com ART registrada no CREA.</div>
    <div>Emitido em {hoje.strftime('%d/%m/%Y')} · {len(projeto.elementos)} elementos
      dimensionados · {len(projeto.ligacoes) + (1 if projeto.base else 0)} ligações
      verificadas</div>
    <div class="versao">{_identificacao_do_programa()}</div>
  </div>
</div>"""


# =====================================================================================
# Entrada do orquestrador
# =====================================================================================

def montar_html(projeto: ProjetoGalpao) -> str:
    """Documento HTML completo do memorial (útil para conferir sem gerar o PDF)."""
    doc = _Doc()
    _cap_dados(doc, projeto)
    _cap_normas(doc, projeto)
    _cap_cargas(doc, projeto)
    _cap_combinacoes(doc, projeto)
    _cap_esforcos(doc, projeto)
    _cap_elementos(doc, projeto)
    _cap_ligacoes(doc, projeto)
    _cap_lista(doc, projeto)
    _cap_conclusao(doc, projeto)

    from . import printpdf
    css = open(os.path.join(_AQUI, "memorial.css"), encoding="utf-8").read()
    corpo = _capa(projeto) + doc.sumario() + doc.corpo()
    return printpdf.envelope(corpo, css,
                             f"Memorial de cálculo — {projeto.dados.nome}")


def gerar(projeto: ProjetoGalpao, pasta: str) -> str:
    """Gera o memorial de cálculo em PDF e devolve o caminho do arquivo."""
    from . import printpdf
    os.makedirs(os.path.abspath(pasta), exist_ok=True)
    html_path = os.path.join(pasta, "memorial.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(montar_html(projeto))
    pdf_path = os.path.join(pasta, "Memorial_de_calculo.pdf")
    printpdf.imprimir(html_path, pdf_path)
    return os.path.abspath(pdf_path)


if __name__ == "__main__":                     # python -m saida.memorial [pasta]
    destino = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_RAIZ, "projetos",
                                                                 "_memorial")
    p = ProjetoGalpao(dados=DadosGalpao())
    print(gerar(p, destino))
