# -*- coding: utf-8 -*-
"""Pranchas de desenho em PDF, prontas para impressão.

    from saida import pranchas
    arquivos = pranchas.gerar(projeto, "projetos/meu-galpao/pranchas")

Cada prancha é uma folha ISO (A1 ou A3, em paisagem) com margem, quadro, **carimbo no
canto inferior direito** e um ou mais desenhos posicionados e escalados para caber.

A escala é de verdade: uma cota de 1 000 mm desenhada em 1:100 mede 10 mm na folha
impressa em tamanho real. Isso é garantido fixando a figura do matplotlib no tamanho
exato da folha (em polegadas) e dando a cada eixo um intervalo de dados igual à largura
do quadro em milímetros **multiplicada pela escala**. O PDF do matplotlib é vetorial,
então a folha sai com as linhas em escala e o texto selecionável.

O módulo é desacoplado de `saida/desenhos.py`: aceita objetos `Desenho` de `saida.dxf`,
caminhos de arquivos DXF, ou nada — caso em que ele mesmo pede os desenhos ao
`saida.desenhos`, se estiver disponível.
"""
import math
import os
import sys
import tempfile
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple, Union

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

import matplotlib                                            # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages         # noqa: E402

from nucleo.base import fmt                                  # noqa: E402
from nucleo.modelo_galpao import DadosGalpao, ProjetoGalpao  # noqa: E402
from saida import dxf_render                                 # noqa: E402
from saida.dxf import Desenho                                # noqa: E402

# =====================================================================================
# Folhas, margens e escalas
# =====================================================================================

#: Formatos ISO 216 em paisagem: (largura, altura) em mm.
FOLHAS: Dict[str, Tuple[float, float]] = {
    "A0": (1189.0, 841.0),
    "A1": (841.0, 594.0),
    "A2": (594.0, 420.0),
    "A3": (420.0, 297.0),
    "A4": (297.0, 210.0),
}

#: Margens do quadro (mm): a esquerda é maior por causa da dobra/encadernação.
MARGENS = {"esquerda": 20.0, "direita": 10.0, "superior": 10.0, "inferior": 10.0}
MARGENS_A3 = {"esquerda": 15.0, "direita": 7.0, "superior": 7.0, "inferior": 7.0}

#: Carimbo (largura × altura, mm). A largura de 180 mm é a da ISO 7200.
CARIMBO = {"A0": (180.0, 70.0), "A1": (180.0, 65.0), "A2": (180.0, 60.0),
           "A3": (180.0, 55.0), "A4": (170.0, 50.0)}

#: Escalas normalizadas admitidas (denominador de 1:n).
ESCALAS = (1, 2, 2.5, 5, 10, 15, 20, 25, 33.333, 50, 75, 100, 125, 150, 200, 250,
           500, 750, 1000, 1250, 1500, 2000, 2500, 5000)

#: Relação entre a altura de texto do DXF (mm no modelo) e o corpo da fonte em pontos.
#: 1 mm = 2,835 pt e a altura da maiúscula da DejaVu Sans vale ≈ 0,73 do corpo;
#: `dxf_render` monta o corpo como `altura · escala_texto · 2,4`.
_FATOR_TEXTO = (2.835 / 0.73) / 2.4

#: Observação obrigatória do carimbo.
OBS_CARIMBO = ("Desenho gerado automaticamente. Deve ser conferido e assinado por "
               "engenheiro habilitado, com ART no CREA, antes da fabricação.")


def escala_normalizada(escala_minima: float) -> float:
    """A menor escala da série que ainda faz o desenho caber."""
    for e in ESCALAS:
        if e >= escala_minima - 1e-9:
            return float(e)
    return float(ESCALAS[-1])


def texto_escala(escala: float) -> str:
    if escala < 1.0:
        return f"{fmt(1.0 / escala, 0)}:1"
    return "1:" + (f"{escala:.0f}" if abs(escala - round(escala)) < 1e-6
                   else fmt(escala, 1))


# =====================================================================================
# Itens de desenho
# =====================================================================================

class Vista:
    """Um desenho a colocar na prancha, com seu título e escala preferida."""

    def __init__(self, desenho: Union[Desenho, str], titulo: str = "",
                 escala: Optional[float] = None, nome: str = ""):
        self.desenho = desenho
        self.titulo = titulo or nome or "Vista"
        self.nome = nome or titulo
        self.escala_preferida = escala
        self._arquivo: Optional[str] = None
        self._extremos: Optional[Tuple[float, float, float, float]] = None

    # -- geometria --------------------------------------------------------
    def arquivo(self, pasta_tmp: str) -> str:
        """Caminho de um DXF com este desenho (grava um temporário se preciso)."""
        if self._arquivo:
            return self._arquivo
        if isinstance(self.desenho, str):
            self._arquivo = os.path.abspath(self.desenho)
        else:
            destino = os.path.join(pasta_tmp,
                                   (self.nome or "vista").replace(" ", "_") + ".dxf")
            self.desenho.gravar(destino)
            self._arquivo = destino
        return self._arquivo

    def extremos(self, pasta_tmp: str) -> Tuple[float, float, float, float]:
        if self._extremos is not None:
            return self._extremos
        if isinstance(self.desenho, Desenho):
            e = tuple(self.desenho.extremos)
            if e[0] < 1e19:
                self._extremos = e
                return e
        doc = dxf_render.ler_dxf(self.arquivo(pasta_tmp))
        xs, ys = [], []
        for ent in doc["entidades"]:
            if ent["tipo"] == "POLYLINE":
                for x, y in ent["pontos"]:
                    xs.append(x)
                    ys.append(y)
                continue
            for cx, cy in ((10, 20), (11, 21), (12, 22), (13, 23)):
                if cx in ent:
                    xs.append(ent[cx])
                    ys.append(ent.get(cy, 0.0))
            if ent["tipo"] in ("CIRCLE", "ARC"):
                r = ent.get(40, 0.0)
                xs += [ent.get(10, 0.0) - r, ent.get(10, 0.0) + r]
                ys += [ent.get(20, 0.0) - r, ent.get(20, 0.0) + r]
        if not xs:
            self._extremos = (0.0, 0.0, 100.0, 100.0)
        else:
            self._extremos = (min(xs), min(ys), max(xs), max(ys))
        return self._extremos

    def tamanho(self, pasta_tmp: str) -> Tuple[float, float]:
        x0, y0, x1, y1 = self.extremos(pasta_tmp)
        return max(x1 - x0, 1.0), max(y1 - y0, 1.0)


def _vista(item, pasta_tmp: str) -> Vista:
    """Normaliza o que veio do orquestrador (dict, Desenho, caminho) em uma `Vista`."""
    if isinstance(item, Vista):
        return item
    if isinstance(item, dict):
        alvo = item.get("desenho") or item.get("arquivo") or item.get("caminho")
        esc = item.get("escala")
        if isinstance(esc, str) and ":" in esc:
            try:
                esc = float(esc.split(":")[1].replace(",", "."))
            except ValueError:
                esc = None
        return Vista(alvo, item.get("titulo", ""), esc, item.get("nome", ""))
    if isinstance(item, (Desenho, str)):
        return Vista(item)
    raise TypeError(f"não sei desenhar um item do tipo {type(item).__name__}")


# =====================================================================================
# Composição das pranchas do galpão
# =====================================================================================

#: Prancha: (número, formato, título, [nomes dos desenhos de `saida.desenhos`]).
COMPOSICAO = [
    (1, "A1", "Pórtico típico e seções dos perfis",
     ["01-PORTICO", "09-SECOES-PERFIS"]),
    (2, "A1", "Planta de cobertura e elevação longitudinal",
     ["02-PLANTA-COBERTURA", "03-ELEVACAO-LONGITUDINAL"]),
    (3, "A1", "Ligações do pórtico — joelho e cumeeira",
     ["04-LIGACAO-VIGA-PILAR", "05-LIGACAO-CUMEEIRA"]),
    (4, "A1", "Base do pilar e apoio de terça",
     ["06-BASE-PILAR", "07-DETALHE-TERCA"]),
    (5, "A3", "Nó de contraventamento",
     ["08-DETALHE-CONTRAVENTAMENTO"]),
    (6, "A1", "Diagramas do pórtico e quadro de verificações",
     ["10-DIAGRAMAS-PORTICO", "11-QUADRO-DE-VERIFICACOES"]),
]


def _desenhos_do_projeto(projeto, pasta_tmp: str) -> Dict[str, Vista]:
    """Pede os desenhos ao `saida.desenhos`; devolve {} se o módulo não estiver pronto."""
    try:
        from saida import desenhos
    except Exception:
        return {}
    saida: Dict[str, Vista] = {}
    for nome, titulo, escala, fn in getattr(desenhos, "CATALOGO", []):
        try:
            d = fn(projeto)
        except Exception:
            continue
        # a escala em que o desenho foi cotado vence a do catálogo: o nó de
        # contraventamento em tirante sai em 1:5, a versão em cantoneira em 1:10
        escala = getattr(d, "escala_sugerida", None) or escala
        try:
            esc = float(str(escala).split(":")[1].replace(",", "."))
        except Exception:
            esc = None
        saida[nome] = Vista(d, titulo, esc, nome)
    return saida


def _desenhos_de_teste(projeto) -> Dict[str, Vista]:
    """Desenho mínimo, usado quando `saida/desenhos.py` não está disponível.

    Não é um substituto do detalhamento: é só um contorno do pórtico com as cotas
    principais, para que a prancha (e o teste de layout) possam existir antes do
    módulo de desenhos.
    """
    d = projeto.dados if isinstance(projeto, ProjetoGalpao) else DadosGalpao()
    vao = d.vao * 1000.0
    H = d.pe_direito * 1000.0
    fl = vao / 2.0 * d.inclinacao / 100.0
    des = Desenho("portico-esquema")
    des.polilinha([(0, 0), (0, H), (vao / 2, H + fl), (vao, H), (vao, 0)],
                  camada="ACO")
    des.linha(-500, 0, vao + 500, 0, "CONCRETO")
    des.cota_h(0, vao, -1500, texto=f"{vao:.0f}")
    des.cota_v(0, H, vao + 1500, texto=f"{H:.0f}")
    des.texto(vao / 2, H + fl + 900, "PORTICO TIPICO", 250, "TEXTO",
              alinhamento="centro")
    return {"01-PORTICO": Vista(des, "Pórtico típico — esquema", 100.0, "01-PORTICO")}


# =====================================================================================
# Desenho da folha
# =====================================================================================

def _eixo_folha(fig, largura: float, altura: float):
    """Eixo que cobre a folha inteira e trabalha em milímetros de papel."""
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(0.0, largura)
    ax.set_ylim(0.0, altura)
    ax.set_aspect("equal")
    ax.axis("off")
    return ax


def _quadro(ax, largura, altura, margens):
    x0, y0 = margens["esquerda"], margens["inferior"]
    x1, y1 = largura - margens["direita"], altura - margens["superior"]
    ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color="#111", lw=1.2,
            solid_joinstyle="miter")
    return x0, y0, x1, y1


def _texto(ax, x, y, texto, tamanho_mm=2.5, negrito=False, ha="left", va="baseline",
           cor="#111", zorder=8):
    ax.text(x, y, texto, fontsize=tamanho_mm * 2.835 / 0.73, ha=ha, va=va, color=cor,
            fontweight="bold" if negrito else "normal", family="DejaVu Sans",
            zorder=zorder)


def _quebrar(texto: str, n: int, linhas: int = 2) -> List[str]:
    """Quebra o texto em até `linhas` linhas de no máximo `n` caracteres."""
    palavras = texto.split()
    saida, atual = [], ""
    for p in palavras:
        se = (atual + " " + p).strip()
        if len(se) <= n or not atual:
            atual = se
        else:
            saida.append(atual)
            atual = p
            if len(saida) == linhas - 1:
                break
    resto = " ".join(palavras[sum(len(l.split()) for l in saida):]) if saida else atual
    saida.append(resto.strip())
    return (saida + [""] * linhas)[:linhas]


def _carimbo(ax, x1, y0, largura_c, altura_c, info: dict):
    """Carimbo ISO 7200 simplificado, ancorado no canto inferior direito do quadro.

    Quatro faixas, de cima para baixo: obra e cliente, título do desenho,
    responsável / escala e data / prancha e revisão, e a observação obrigatória.
    """
    x0 = x1 - largura_c
    y1 = y0 + altura_c
    ax.add_patch(plt.Rectangle((x0, y0), largura_c, altura_c, fill=True,
                               facecolor="#ffffff", edgecolor="#111", lw=1.2,
                               zorder=5))
    h_obs = altura_c * 0.13
    h_rod = altura_c * 0.29
    h_tit = altura_c * 0.25
    y_obs = y0 + h_obs                    # topo da faixa da observação
    y_rod = y_obs + h_rod                 # topo da faixa do rodapé
    y_tit = y_rod + h_tit                 # topo da faixa do título
    for y in (y_obs, y_rod, y_tit):
        ax.plot([x0, x1], [y, y], color="#111", lw=0.7, zorder=6)
    xc1 = x0 + largura_c * 0.46
    xc2 = x0 + largura_c * 0.72
    for x in (xc1, xc2):
        ax.plot([x, x], [y_obs, y_rod], color="#111", lw=0.7, zorder=6)

    m = 3.0
    h_top = y1 - y_tit
    k = altura_c / 65.0                 # todas as alturas de texto acompanham a folha
    # faixa superior: obra e cliente
    _texto(ax, x0 + m, y1 - 0.19 * h_top, "OBRA", 1.9 * k, cor="#555")
    obra = info["obra"]
    # o nome da obra encolhe para caber inteiro, em vez de ser cortado
    tam_obra = 3.4 if len(obra) <= 40 else (2.8 if len(obra) <= 52 else 2.3)
    _texto(ax, x0 + m, y1 - 0.45 * h_top, obra[:74], tam_obra * k, negrito=True)
    _texto(ax, x0 + m, y1 - 0.68 * h_top, "CLIENTE", 1.9 * k, cor="#555")
    _texto(ax, x0 + m, y1 - 0.91 * h_top, info["cliente"][:58], 2.5 * k)
    # faixa do título do desenho
    _texto(ax, x0 + m, y_tit - 0.23 * h_tit, "TÍTULO DO DESENHO", 1.9 * k, cor="#555")
    _texto(ax, x0 + m, y_tit - 0.56 * h_tit, info["titulo"][:48], 3.1 * k,
           negrito=True)
    if info.get("subtitulo"):
        _texto(ax, x0 + m, y_tit - 0.86 * h_tit, info["subtitulo"][:66], 2.1 * k,
               cor="#333")
    # rodapé: responsável | escala e data | prancha e revisão
    for x, rotulo, valor, extra, grande in (
            (x0, "RESPONSÁVEL TÉCNICO", info["responsavel"][:38], info["crea"][:44],
             False),
            (xc1, "ESCALA", info["escala"][:20], "DATA  " + info["data"], False),
            (xc2, "PRANCHA", info["prancha"], "REV. " + info["revisao"], True)):
        _texto(ax, x + m, y_rod - 0.19 * h_rod, rotulo, 1.8 * k, cor="#555")
        _texto(ax, x + m, y_rod - 0.46 * h_rod, valor, (3.4 if grande else 2.5) * k,
               negrito=True)
        _texto(ax, x + m, y_rod - 0.74 * h_rod, extra, 1.9 * k, cor="#333")

    # observação obrigatória
    l1, l2 = _quebrar(OBS_CARIMBO, int(largura_c / 1.05 / max(k, 0.6)), 2)
    if l2:
        _texto(ax, x0 + m, y_obs - 0.38 * h_obs, l1, 1.7 * k, cor="#a5231a")
        _texto(ax, x0 + m, y_obs - 0.80 * h_obs, l2, 1.7 * k, cor="#a5231a")
    else:
        _texto(ax, x0 + m, y_obs - 0.62 * h_obs, l1, 1.7 * k, cor="#a5231a")


#: Espaço reservado sob cada vista para o rótulo e a escala (mm de papel).
FAIXA_TITULO = 11.0
#: Folga entre a vista e as bordas da sua célula (mm de papel).
FOLGA_CELULA = 5.0


def _escala_na_celula(vista: Vista, pasta_tmp: str, cl: float, ca: float
                      ) -> Tuple[float, float, float]:
    """Escala adotada e tamanho ocupado no papel (mm) de uma vista numa célula."""
    util_l = max(cl - 2 * FOLGA_CELULA, 10.0)
    util_a = max(ca - 2 * FOLGA_CELULA - FAIXA_TITULO, 10.0)
    larg_d, alt_d = vista.tamanho(pasta_tmp)
    esc_min = max(larg_d / util_l, alt_d / util_a)
    escala = escala_normalizada(esc_min)
    if vista.escala_preferida and vista.escala_preferida >= esc_min - 1e-9:
        escala = escala_normalizada(vista.escala_preferida)
    return escala, larg_d / escala, alt_d / escala


def _grade(vistas: Sequence[Vista], pasta_tmp: str, larg: float, alt: float
           ) -> Tuple[int, int]:
    """Grade (colunas, linhas) que faz os desenhos saírem maiores na folha.

    Testa todas as grades possíveis e escolhe a que maximiza a área de papel
    efetivamente ocupada pelos desenhos — é o critério que o projetista usa no
    olho: aproveitar a folha sem deixar vazio.
    """
    n = len(vistas)
    if n <= 1:
        return 1, 1
    melhor = None
    # varre do maior número de colunas para o menor: empatada a área ocupada,
    # fica a grade mais "deitada", que é a que aproveita melhor a folha paisagem
    for colunas in range(n, 0, -1):
        linhas = int(math.ceil(n / colunas))
        cl, ca = larg / colunas, alt / linhas
        area = 0.0
        for v in vistas:
            _, bw, bh = _escala_na_celula(v, pasta_tmp, cl, ca)
            area += bw * bh
        if melhor is None or area > melhor[0] + 1e-9:
            melhor = (area, colunas, linhas)
    return melhor[1], melhor[2]


#: Formatos que o sistema emite, do menor para o maior. O A2 existe para o detalhe
#: cotado em 1:5 (nó de contraventamento em tirante), que não cabe legível no A3 e
#: ficaria perdido no A1.
FORMATOS_EMITIDOS = ("A3", "A2", "A1")

#: Quanto a escala impressa pode piorar em relação à sugerida no desenho antes de
#: trocar de folha. Acima disso o texto do desenho (dimensionado para 2,5 mm no papel
#: na escala sugerida) fica pequeno demais para leitura em obra.
TOLERANCIA_ESCALA = 1.6


def _area_util(formato: str) -> Tuple[float, float]:
    W, H = FOLHAS[formato]
    m = MARGENS_A3 if formato in ("A3", "A4") else MARGENS
    alt_c = CARIMBO[formato][1]
    return ((W - m["esquerda"] - m["direita"] - 4.0),
            (H - m["superior"] - m["inferior"] - 4.0) - (alt_c + 3.0))


def formato_suficiente(vistas: Sequence[Vista], pasta_tmp: str,
                       formato: str = "A3",
                       formatos: Sequence[str] = FORMATOS_EMITIDOS) -> str:
    """Menor folha em que nenhuma vista precisa encolher demais.

    O desenho traz a escala para a qual foi cotado (texto de 2,5 mm no papel). Se a
    folha obriga a reduzir mais de `TOLERANCIA_ESCALA` vezes, o texto fica ilegível
    e a prancha sobe de formato.
    """
    candidatos = [f for f in formatos
                  if FOLHAS[f][0] * FOLHAS[f][1] >= FOLHAS[formato][0]
                  * FOLHAS[formato][1] - 1e-6]
    candidatos = candidatos or [formato]
    for f in candidatos:
        larg, alt = _area_util(f)
        colunas, linhas = _grade(vistas, pasta_tmp, larg, alt)
        cl, ca = larg / colunas, alt / linhas
        pior = 0.0
        for v in vistas:
            escala, _, _ = _escala_na_celula(v, pasta_tmp, cl, ca)
            if v.escala_preferida:
                pior = max(pior, escala / v.escala_preferida)
        if pior <= TOLERANCIA_ESCALA:
            return f
    return candidatos[-1]


def _desenhar_vista(fig, folha: Tuple[float, float],
                    celula: Tuple[float, float, float, float],
                    vista: Vista, pasta_tmp: str, ax_folha) -> float:
    """Coloca uma vista na célula (x0, y0, larg, alt) em mm; devolve a escala usada.

    O quadro do eixo é ajustado **ao tamanho real do desenho na escala adotada**,
    e não à célula inteira: é assim que a vista fica centrada e o rótulo cai logo
    abaixo dela, como em prancha desenhada à mão.
    """
    W, H = folha
    cx0, cy0, clarg, calt = celula
    escala, bw, bh = _escala_na_celula(vista, pasta_tmp, clarg, calt)

    # quadro do desenho, centrado na célula acima da faixa do rótulo
    ax_x0 = cx0 + (clarg - bw) / 2.0
    centro_y = cy0 + FAIXA_TITULO + (calt - FAIXA_TITULO) / 2.0
    ax_y0 = centro_y - bh / 2.0
    ax = fig.add_axes((ax_x0 / W, ax_y0 / H, bw / W, bh / H))
    ax.set_aspect("equal")
    ax.axis("off")

    # intervalo de dados = medida do quadro no papel × escala:
    # é isso que garante 1 mm do desenho = 1/escala mm na folha impressa
    x0, y0, x1, y1 = vista.extremos(pasta_tmp)
    cxd, cyd = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    meia_l = bw * escala / 2.0
    meia_a = bh * escala / 2.0
    limites = (cxd - meia_l, cxd + meia_l, cyd - meia_a, cyd + meia_a)

    dxf_render.desenhar(vista.arquivo(pasta_tmp), ax,
                        escala_texto=_FATOR_TEXTO / escala)
    ax.set_xlim(limites[0], limites[1])
    ax.set_ylim(limites[2], limites[3])
    ax.set_aspect("equal")

    # rótulo da vista, centrado logo abaixo do desenho
    xm = cx0 + clarg / 2.0
    y_reg = max(ax_y0 - 2.0, cy0 + FAIXA_TITULO - 2.0)
    _texto(ax_folha, xm, y_reg - 1.2, vista.titulo.upper(), 2.9, negrito=True,
           ha="center", va="top")
    meia_linha = max(min(clarg * 0.24, bw * 0.6), 14.0)
    ax_folha.plot([xm - meia_linha, xm + meia_linha], [y_reg - 5.6] * 2,
                  color="#111", lw=0.9, zorder=8)
    _texto(ax_folha, xm, y_reg - 6.8, "ESCALA " + texto_escala(escala), 2.2,
           ha="center", va="top", cor="#333")
    return escala


def prancha(vistas: Sequence[Vista], caminho_pdf: str, formato: str = "A1",
            info: Optional[dict] = None, pasta_tmp: Optional[str] = None) -> dict:
    """Monta e grava uma prancha. Devolve {arquivo, titulo, escala, formato, ...}."""
    formato = formato.upper()
    if formato not in FOLHAS:
        raise ValueError(f"formato de folha desconhecido: {formato}. "
                         f"Use um de {sorted(FOLHAS)}.")
    W, H = FOLHAS[formato]
    margens = dict(MARGENS_A3 if formato in ("A3", "A4") else MARGENS)
    larg_c, alt_c = CARIMBO[formato]
    info = dict(info or {})

    tmp_criado = None
    if pasta_tmp is None:
        tmp_criado = tempfile.TemporaryDirectory()
        pasta_tmp = tmp_criado.name
    try:
        fig = plt.figure(figsize=(W / 25.4, H / 25.4))
        fig.patch.set_facecolor("white")
        ax_folha = _eixo_folha(fig, W, H)
        qx0, qy0, qx1, qy1 = _quadro(ax_folha, W, H, margens)

        # área útil de desenho: acima da faixa do carimbo
        faixa = alt_c + 3.0
        util_x0, util_y0 = qx0 + 2.0, qy0 + faixa
        util_l = (qx1 - 2.0) - util_x0
        util_a = (qy1 - 2.0) - util_y0

        colunas, linhas = _grade(vistas, pasta_tmp, util_l, util_a)
        cl = util_l / colunas
        ca = util_a / linhas
        escalas = []
        for i, v in enumerate(vistas):
            col = i % colunas
            lin = i // colunas
            cx0 = util_x0 + col * cl
            cy0 = util_y0 + (linhas - 1 - lin) * ca
            escalas.append(_desenhar_vista(fig, (W, H), (cx0, cy0, cl, ca), v,
                                           pasta_tmp, ax_folha))

        texto_esc = (texto_escala(escalas[0]) if len(set(escalas)) == 1
                     else "indicadas")
        info.setdefault("escala", texto_esc)
        _carimbo(ax_folha, qx1, qy0, larg_c, alt_c, info)

        # legenda do canto superior esquerdo do quadro
        _texto(ax_folha, qx0 + 3.0, qy1 - 6.0, info.get("obra", ""), 3.0, negrito=True)
        _texto(ax_folha, qx0 + 3.0, qy1 - 10.0, info.get("titulo", ""), 2.4,
               cor="#333")
        _texto(ax_folha, qx1 - 3.0, qy1 - 6.0,
               f"{formato} · {W:.0f} × {H:.0f} mm", 2.2, ha="right", cor="#555")

        os.makedirs(os.path.dirname(os.path.abspath(caminho_pdf)), exist_ok=True)
        with PdfPages(caminho_pdf) as pdf:
            pdf.savefig(fig, facecolor="white")
        plt.close(fig)
    finally:
        if tmp_criado is not None:
            tmp_criado.cleanup()

    return {"arquivo": os.path.abspath(caminho_pdf), "titulo": info.get("titulo", ""),
            "escala": info.get("escala", ""), "formato": formato,
            "prancha": info.get("prancha", ""), "revisao": info.get("revisao", "")}


# =====================================================================================
# Entrada do orquestrador
# =====================================================================================

def _info_base(projeto, titulo: str, numero: str, subtitulo: str = "") -> dict:
    d = projeto.dados if isinstance(projeto, ProjetoGalpao) else DadosGalpao()
    return {
        "obra": d.nome or "Galpão",
        "cliente": d.cliente or "—",
        "titulo": titulo,
        "subtitulo": subtitulo,
        "responsavel": d.responsavel or "—",
        "crea": "CREA nº ____________ — ART nº ____________",
        "data": date.today().strftime("%d/%m/%Y"),
        "prancha": numero,
        "revisao": "00",
    }


def gerar(projeto, pasta: str, desenhos: Optional[Sequence] = None) -> List[dict]:
    """Gera as pranchas em PDF e devolve a lista do que foi criado.

    `desenhos` aceita objetos `Desenho`, caminhos de DXF, `Vista` ou dicionários no
    formato devolvido por `saida.desenhos.gerar_todos`. Sem esse argumento, os
    desenhos são pedidos a `saida.desenhos`; se nem ele estiver disponível, uma
    prancha de esquema é montada a partir da geometria, com aviso.
    """
    pasta = os.path.abspath(pasta)
    os.makedirs(pasta, exist_ok=True)
    avisos = getattr(projeto, "avisos", [])
    saida: List[dict] = []

    with tempfile.TemporaryDirectory() as tmp:
        if desenhos:
            vistas = [_vista(x, tmp) for x in desenhos]
            catalogo = {v.nome: v for v in vistas}
            composicao = [(i + 1, "A3", v.titulo, [v.nome])
                          for i, v in enumerate(vistas)]
        else:
            catalogo = _desenhos_do_projeto(projeto, tmp)
            if catalogo:
                composicao = COMPOSICAO
            else:
                catalogo = _desenhos_de_teste(projeto)
                composicao = [(1, "A1", "Pórtico típico — esquema", ["01-PORTICO"])]
                if isinstance(avisos, list):
                    avisos.append(
                        "Pranchas montadas com o desenho de esquema do próprio módulo: "
                        "o módulo saida/desenhos.py não pôde fornecer os detalhes.")

        total = len(composicao)
        for numero, formato, titulo, nomes in composicao:
            vistas = [catalogo[n] for n in nomes if n in catalogo]
            if not vistas:
                continue
            formato = formato_suficiente(vistas, tmp, formato)
            sub = " · ".join(v.titulo for v in vistas)
            info = _info_base(projeto, titulo, f"{numero:02d}/{total:02d}", sub)
            arquivo = os.path.join(pasta, f"PR{numero:02d}-"
                                   + _slug(titulo) + f"-{formato}.pdf")
            saida.append(prancha(vistas, arquivo, formato, info, tmp))
    return saida


def _slug(texto: str) -> str:
    tab = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
                        "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC")
    t = texto.translate(tab).lower()
    t = "".join(c if c.isalnum() else "-" for c in t)
    while "--" in t:
        t = t.replace("--", "-")
    return t.strip("-")[:48] or "prancha"


if __name__ == "__main__":                     # python -m saida.pranchas [pasta]
    destino = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_RAIZ, "projetos",
                                                                 "_pranchas")
    p = ProjetoGalpao(dados=DadosGalpao())
    for item in gerar(p, destino):
        print(f"{item['prancha']:>6}  {item['formato']:<3} {item['escala']:>10}  "
              f"{item['arquivo']}")
