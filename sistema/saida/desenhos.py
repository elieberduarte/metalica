# -*- coding: utf-8 -*-
"""Desenhos de detalhamento do galpão, em DXF (escala 1:1, milímetros).

Cada função recebe geometria — um `ProjetoGalpao`, um `DadosGalpao` ou um dicionário
simples — e devolve um objeto `Desenho` de `saida.dxf`, pronto para gravar.

Princípios seguidos aqui (Capítulo 14 do manual, "Catálogo de detalhes construtivos",
e Capítulo 16, "Exemplo completo"):

* **Desenho autoexplicativo.** Contorno das peças, hachura no que está cortado, cotas
  de tudo que o fabricante precisa marcar, furos com diâmetro, símbolos de solda,
  identificação de perfil em cada peça e notas de fabricação.
* **Tudo em milímetro, 1:1.** A escala é uma informação do desenho (vai no rótulo e no
  retorno de `gerar_todos`), não uma transformação das coordenadas. O que muda com a
  escala é só a *altura do texto e o tamanho das setas e afastamentos de cota*, que são
  dimensionados para valer 2,5 mm (texto) e 10 mm (afastamento) **no papel**.
* **Sem número mágico escondido.** Os valores adotados por falta de dado do orquestrador
  estão em `PADRAO_*`, documentados, e são recolocados em `Desenho.padroes` para que o
  memorial possa dizer que foram adotados.

Dependência mínima: `saida.dxf` e o catálogo de perfis. Funciona com um `ProjetoGalpao`
completo e também com um dicionário de geometria mínimo (ver `PADRAO_GALPAO`), de modo a
poder ser testado antes do orquestrador existir.

O que se lê do `ProjetoGalpao`
------------------------------
================================ ==================================================
Fonte                            Uso no desenho
================================ ==================================================
`projeto.dados`                  toda a geometria do galpão (metros → mm)
`projeto.elemento("Pilar")`      nome do perfil do pilar (idem viga, terça,
                                 longarina); na falta, `PADRAO_PERFIS`
`projeto.ligacoes["viga-pilar"]` `Resultado` de `nucleo.ligacoes.chapa_de_topo`
`projeto.ligacoes["cumeeira"]`   idem, para a cumeeira
`projeto.base`                   `Resultado` de `nucleo.bases.dimensionar_base`
================================ ==================================================

O núcleo calcula em **centímetros** e o desenho é em **milímetros**: a conversão é
feita chave a chave em `_ligacao_do_resultado` e `_base_do_resultado`, nunca por cópia
cega do dicionário — uma chave homônima em outra unidade estragaria o desenho em
silêncio. O que o projeto ainda não traz sai dos padrões documentados em `PADRAO_*`.
"""
import math
import re
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple, Union

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:                     # permite rodar o módulo isoladamente
    sys.path.insert(0, _RAIZ)

from saida.dxf import Desenho                                   # noqa: E402
from nucleo.perfis import banco, Perfil                         # noqa: E402
from nucleo.modelo_galpao import DadosGalpao, ProjetoGalpao     # noqa: E402


# =====================================================================================
# Valores adotados quando o projeto ainda não traz o dado
# =====================================================================================

#: Perfis padrão por faixa de vão (m). Ordem: (vão máximo, pilar, viga).
#: A faixa de 20 m reproduz o galpão do Capítulo 16 (pilar W 360×44,6, viga W 360×32,9).
PADRAO_PERFIS = [
    (12.0, "W 310×38,7", "W 310×28,3"),
    (18.0, "W 360×44,6", "W 310×32,7"),
    (22.0, "W 360×44,6", "W 360×32,9"),
    (28.0, "W 460×60,0", "W 410×46,1"),
    (99.0, "W 530×74,0", "W 460×52,0"),
]

PADRAO_TERCA = "Ue 200×75×20×2,65"        # Cap. 16, passo 1 (vão de terça de 5 m)
PADRAO_TERCA_GRANDE = "Ue 250×85×25×3,00"  # vão de terça acima de 6 m
PADRAO_LONGARINA = "Ue 200×75×20×2,65"
PADRAO_COLUNA_OITAO = "W 250×25,3"
#: Contraventamentos quando o projeto ainda não traz o elemento calculado: tirante
#: redondo com esticador, a mesma solução de `nucleo/galpao.py` (_contraventamentos),
#: com o ø 20 mm do Cap. 16, passo 10(b). Com o projeto calculado, vale o perfil dos
#: elementos "Contraventamento de cobertura" e "Contraventamento vertical".
PADRAO_CONTRAV_COBERTURA = "Barra redonda ø 20 mm"
PADRAO_CONTRAV_VERTICAL = "Barra redonda ø 20 mm"
PADRAO_DIAGONAL_VERTICAL = PADRAO_CONTRAV_VERTICAL   # nome antigo, mantido por compatibilidade
PADRAO_ESCORA = 'TC 88,9×3,2 (3")'         # a escora não é dimensionada pelo cálculo
PADRAO_DIAM_CONTRAVENTAMENTO = 20.0
PADRAO_DIAM_CORRENTE = 16.0                # corrente de terça ø 16 mm, como na lista de material

#: Geometria mínima aceita por qualquer função que receba "dados" de galpão, em metros.
PADRAO_GALPAO = dict(
    vao=20.0, comprimento=40.0, pe_direito=6.0, espacamento_porticos=5.0,
    inclinacao=10.0, balanco_lateral=0.0, com_misula=True, comprimento_misula=1.8,
    altura_misula=0.0, base_rotulada=True, espacamento_tercas=1.6, linhas_correntes=1,
)

#: Ligação parafusada padrão (Cap. 16, passos 7 e 8; Cap. 14.3.3).
PADRAO_LIGACAO = dict(
    d_parafuso=19.05,        # ø 3/4"
    classe_parafuso="A325",
    folga_furo=2.0,          # furo ø 21 para parafuso ø 3/4"
    gabarito=100.0,          # g entre as duas colunas de parafusos da chapa de topo
    borda_mesa=40.0,         # fileira a 40 mm da face da mesa (fora e dentro)
    borda_chapa=40.0,        # sobra da chapa além da última fileira
    chapa_esp=22.4,          # 7/8" em A36
    enrijecedor_esp=10.0,
    perna_solda_alma=5.0,
    perna_solda_mesa=8.0,
    penetracao_total_mesas=True,
)

#: Base de pilar padrão (Cap. 16, passo 9; Cap. 14 e Cap. 10 do manual).
PADRAO_BASE = dict(
    placa_B=300.0,           # largura da placa (perpendicular ao plano do pórtico)
    placa_L=400.0,           # comprimento da placa (no plano do pórtico, direção d)
    placa_t=19.0,
    d_chumbador=19.05,       # ø 3/4"
    n_chumbadores=2,         # 2 = base rotulada; 4 = base engastada
    gabarito_B=130.0,        # afastamento entre chumbadores na direção B
    gabarito_L=0.0,          # 0 = chumbadores no meio da placa (rótula)
    folga_furo=8.0,          # furo ø 27 para chumbador ø 3/4" (montagem)
    arruela=60.0,            # arruela quadrada 60 × 60 × 8, soldada
    grout=30.0,
    pedestal_altura=150.0,   # trecho do pedestal acima do piso acabado
    pedestal_folga=100.0,    # sobra do pedestal além da placa, de cada lado
    ancoragem=400.0,
    gancho=100.0,
    fck_MPa=25.0,
)

#: Apoio de terça padrão (Cap. 14.1.1 e 14.1.2).
PADRAO_TERCA_DET = dict(
    tipo_chapa="dobrada",    # "dobrada" ou "cantoneira"
    chapa_esp=4.75,
    d_parafuso=12.7,         # ø 1/2"
    n_parafusos=2,
    gabarito_parafusos=100.0,
    folga_terca=15.0,        # folga entre duas terças no apoio simples
    d_corrente=PADRAO_DIAM_CORRENTE,
    perna_solda=5.0,
)

#: Nó de contraventamento padrão (Cap. 14.2.1b e 16, passo 10).
PADRAO_CONTRAVENTAMENTO = dict(
    gusset_esp=9.5,
    d_parafuso=19.05,
    n_parafusos=2,
    gabarito=70.0,           # espaçamento entre parafusos na barra
    borda=40.0,
    angulo=45.0,             # ângulo da diagonal com o banzo
    perna_solda=6.0,
    # tirante redondo (Cap. 14.2.1a): orelha de 8–9,5 mm soldada, furo ø d + 2,
    # arruela, porca e contraporca; esticador no meio da diagonal
    orelha_esp=9.5,
    folga_furo_tirante=2.0,
    esticador_comp=0.0,      # 0 = 8·d, no mínimo 150 mm: conferir no catálogo (DIN 1480)
    ajuste_rosca=40.0,       # rosca além da porca, para regular o tirante na montagem
)


# =====================================================================================
# Estilo: tudo que depende da escala de impressão
# =====================================================================================

class Estilo:
    """Converte "milímetros no papel" em milímetros no modelo.

    Um desenho 1:1 em mm impresso a 1:100 precisa de texto de 250 mm para que ele saia
    com 2,5 mm na folha. Todas as alturas de texto, setas e afastamentos de cota deste
    módulo passam por aqui.
    """

    def __init__(self, escala: float = 10.0, texto_papel: float = 2.5):
        self.escala = float(escala)
        self.texto_papel = float(texto_papel)

    # alturas de texto (mm no modelo)
    @property
    def t(self) -> float:            # texto corrente / cotas
        return self.texto_papel * self.escala

    @property
    def tp(self) -> float:           # texto pequeno (notas, marcas secundárias)
        return 2.0 * self.escala

    @property
    def tg(self) -> float:           # texto grande (nome da peça)
        return 3.2 * self.escala

    @property
    def tt(self) -> float:           # título da vista
        return 4.0 * self.escala

    # afastamentos
    @property
    def off(self) -> float:          # 1ª linha de cota, afastada da peça
        return 10.0 * self.escala

    @property
    def off2(self) -> float:         # 2ª linha de cota
        return 20.0 * self.escala

    @property
    def off3(self) -> float:
        return 30.0 * self.escala

    @property
    def seta(self) -> float:
        return 2.5 * self.escala

    @property
    def folga(self) -> float:        # folga entre a peça e o início da linha de chamada
        return 1.5 * self.escala

    @property
    def lin(self) -> float:          # entrelinha de um bloco de notas
        return 3.4 * self.escala

    def texto_escala(self) -> str:
        e = self.escala
        return f"1:{e:.0f}" if abs(e - round(e)) < 1e-6 else f"1:{e:g}"


# =====================================================================================
# Utilidades numéricas e de formatação
# =====================================================================================

def _mm(v: float, casas: int = 0) -> str:
    """Número de cota, em mm, do jeito que vai no desenho."""
    if casas == 0:
        return f"{v:.0f}"
    s = f"{v:.{casas}f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _finito(*vals) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals)


def _rot(p: Tuple[float, float], ang_rad: float) -> Tuple[float, float]:
    c, s = math.cos(ang_rad), math.sin(ang_rad)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def _mover(pts, dx, dy, ang_rad=0.0):
    if ang_rad:
        return [(_rot(p, ang_rad)[0] + dx, _rot(p, ang_rad)[1] + dy) for p in pts]
    return [(p[0] + dx, p[1] + dy) for p in pts]


# =====================================================================================
# Primitivas de desenho técnico sensíveis à escala
#
# `saida.dxf.Desenho` traz cota_linear, chamada e simbolo_solda com tamanhos fixos em
# milímetros (setas de 3,5 mm, traço de chamada de 8 mm), o que só serve a detalhes
# desenhados perto de 1:1. As funções abaixo constroem os mesmos elementos sobre as
# primitivas do módulo (linha, seta, solido, texto), agora proporcionais à escala.
# =====================================================================================

def _cota(d: Desenho, est: Estilo, x1, y1, x2, y2, desl, texto=None,
          altura=None, camada="COTA", extensao=None):
    """Cota alinhada entre dois pontos, deslocada `desl` perpendicularmente.

    `desl > 0` joga a cota para a esquerda do sentido 1→2 (para cima, numa cota
    horizontal da esquerda para a direita).
    """
    dx, dy = x2 - x1, y2 - y1
    comp = math.hypot(dx, dy)
    if comp < 1e-9 or not _finito(x1, y1, x2, y2, desl):
        return d
    h = altura if altura is not None else est.t
    ext = extensao if extensao is not None else 2.0 * est.escala
    ux, uy = dx / comp, dy / comp
    nx, ny = -uy, ux
    sg = 1.0 if desl >= 0 else -1.0
    a1 = (x1 + nx * desl, y1 + ny * desl)
    a2 = (x2 + nx * desl, y2 + ny * desl)
    fol = est.folga
    d.linha(x1 + nx * sg * fol, y1 + ny * sg * fol,
            a1[0] + nx * sg * ext, a1[1] + ny * sg * ext, camada)
    d.linha(x2 + nx * sg * fol, y2 + ny * sg * fol,
            a2[0] + nx * sg * ext, a2[1] + ny * sg * ext, camada)
    d.linha(a1[0], a1[1], a2[0], a2[1], camada)
    ang = math.degrees(math.atan2(uy, ux))
    tam = min(est.seta, max(0.4 * est.seta, comp / 4))
    fora = comp < 3.0 * tam            # cota curta: setas por fora
    if fora:
        d.seta(a1[0], a1[1], ang, tam, camada)
        d.seta(a2[0], a2[1], ang + 180, tam, camada)
        d.linha(a1[0] - ux * 2 * tam, a1[1] - uy * 2 * tam, a1[0], a1[1], camada)
        d.linha(a2[0] + ux * 2 * tam, a2[1] + uy * 2 * tam, a2[0], a2[1], camada)
    else:
        d.seta(a1[0], a1[1], ang + 180, tam, camada)
        d.seta(a2[0], a2[1], ang, tam, camada)
    txt = texto if texto is not None else _mm(comp)
    mx, my = (a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2
    ang_txt = ang if -90 < ang <= 90 else ang + 180
    lado = 1.0 if -90 < ang <= 90 else -1.0
    off = h * 0.55 * lado
    if fora:                            # texto na ponta, para não bater nas setas
        mx += ux * (2.4 * tam + 0.4 * h * len(txt))
        my += uy * (2.4 * tam + 0.4 * h * len(txt))
    d.texto(mx + nx * off, my + ny * off, txt, h, camada,
            angulo=ang_txt, alinhamento="centro")
    return d


def _cota_h(d, est, x1, x2, y, desl, texto=None, altura=None):
    return _cota(d, est, x1, y, x2, y, desl, texto, altura)


def _cota_v(d, est, y1, y2, x, desl, texto=None, altura=None):
    """`desl > 0` joga a cota para a direita da peça."""
    return _cota(d, est, x, y1, x, y2, -desl, texto, altura)


def _cadeia_h(d, est, xs: Sequence[float], y, desl, textos=None, altura=None):
    """Cota em cadeia (parcial a parcial) no eixo horizontal."""
    xs = list(xs)
    for i in range(len(xs) - 1):
        t = textos[i] if textos else None
        _cota_h(d, est, xs[i], xs[i + 1], y, desl, t, altura)
    return d


def _cadeia_v(d, est, ys: Sequence[float], x, desl, textos=None, altura=None):
    ys = list(ys)
    for i in range(len(ys) - 1):
        t = textos[i] if textos else None
        _cota_v(d, est, ys[i], ys[i + 1], x, desl, t, altura)
    return d


def _chamada(d: Desenho, est: Estilo, x_alvo, y_alvo, x_txt, y_txt, texto,
             altura=None, camada="TEXTO", linhas=None):
    """Linha de chamada com seta na peça e texto na ponta (uma ou mais linhas)."""
    if not _finito(x_alvo, y_alvo, x_txt, y_txt):
        return d
    h = altura if altura is not None else est.tp
    d.linha(x_alvo, y_alvo, x_txt, y_txt, camada)
    ang = math.degrees(math.atan2(y_alvo - y_txt, x_alvo - x_txt))
    d.seta(x_alvo, y_alvo, ang, est.seta, camada)
    direita = x_txt >= x_alvo
    traco = (4.0 * est.escala) * (1 if direita else -1)
    d.linha(x_txt, y_txt, x_txt + traco, y_txt, camada)
    alin = "esquerda" if direita else "direita"
    xt = x_txt + traco + (0.6 * est.escala if direita else -0.6 * est.escala)
    for i, ln in enumerate([texto] + list(linhas or [])):
        d.texto(xt, y_txt + 0.45 * h - i * 1.35 * h, ln, h, camada, alinhamento=alin)
    return d


def _solda(d: Desenho, est: Estilo, x_alvo, y_alvo, x_ref, y_ref, perna,
           tipo="filete", texto="", em_volta=False, campo=False, outro_lado=False):
    """Símbolo de solda AWS A2.4 proporcional à escala.

    `tipo`: "filete" (triângulo), "penetracao" (chanfro em V / penetração total) ou
    "topo". `outro_lado=True` põe o símbolo acima da linha de referência (lado oposto
    ao da seta).
    """
    cam = "SOLDA"
    e = est.escala
    d.linha(x_alvo, y_alvo, x_ref, y_ref, cam)
    ang = math.degrees(math.atan2(y_alvo - y_ref, x_alvo - x_ref))
    d.seta(x_alvo, y_alvo, ang, est.seta, cam)
    direita = x_ref >= x_alvo
    comp = 22.0 * e * (1 if direita else -1)
    d.linha(x_ref, y_ref, x_ref + comp, y_ref, cam)             # linha de referência
    lado = -1.0 if outro_lado else 1.0
    bx = x_ref + comp * 0.42
    tri = 3.2 * e
    if tipo == "filete":
        d.solido((bx, y_ref), (bx + abs(comp) * 0.22, y_ref),
                 (bx, y_ref + tri * lado), camada=cam)
        d.texto(bx - 0.8 * e, y_ref + (0.6 * e if lado > 0 else -tri - 2.2 * est.tp),
                _mm(perna), est.tp, cam, alinhamento="direita")
    else:                                                        # chanfro / penetração
        d.linha(bx, y_ref, bx + tri * 0.55, y_ref + tri * lado, cam)
        d.linha(bx + tri * 1.1, y_ref, bx + tri * 0.55, y_ref + tri * lado, cam)
        d.linha(bx, y_ref, bx + tri * 1.1, y_ref, cam)
    if texto:
        d.texto(x_ref + comp + (0.8 * e if direita else -0.8 * e), y_ref + 0.5 * e,
                texto, est.tp, cam, alinhamento="esquerda" if direita else "direita")
    if em_volta:
        d.circulo(x_ref, y_ref, 1.6 * e, cam)
    if campo:
        d.linha(x_ref, y_ref, x_ref, y_ref + 4.5 * e, cam)
        d.solido((x_ref, y_ref + 4.5 * e), (x_ref + 2.6 * e, y_ref + 4.5 * e),
                 (x_ref, y_ref + 3.2 * e), camada=cam)
    return d


def _furo(d: Desenho, est: Estilo, x, y, diametro, camada="FURO", eixos=True):
    d.circulo(x, y, diametro / 2, camada)
    if eixos:
        c = diametro / 2 + 1.6 * est.escala
        d.linha(x - c, y, x + c, y, "EIXO")
        d.linha(x, y - c, x, y + c, "EIXO")
    return d


def _oblongo(d: Desenho, x, y, larg, alt, camada="FURO"):
    """Furo oblongo de largura `larg` (eixo x) e altura `alt` (eixo y)."""
    r = min(larg, alt) / 2
    if larg >= alt:
        a = larg / 2 - r
        d.arco(x - a, y, r, 90, 270, camada)
        d.arco(x + a, y, r, 270, 90, camada)
        d.linha(x - a, y + r, x + a, y + r, camada)
        d.linha(x - a, y - r, x + a, y - r, camada)
    else:
        a = alt / 2 - r
        d.arco(x, y + a, r, 0, 180, camada)
        d.arco(x, y - a, r, 180, 360, camada)
        d.linha(x - r, y - a, x - r, y + a, camada)
        d.linha(x + r, y - a, x + r, y + a, camada)
    return d


def _eixo(d: Desenho, x1, y1, x2, y2, sobra=0.0):
    """Linha de eixo prolongada `sobra` além dos dois pontos."""
    dx, dy = x2 - x1, y2 - y1
    c = math.hypot(dx, dy)
    if c < 1e-9:
        return d
    ux, uy = dx / c, dy / c
    return d.linha(x1 - ux * sobra, y1 - uy * sobra, x2 + ux * sobra, y2 + uy * sobra,
                   "EIXO")


def _terreno(d: Desenho, est: Estilo, x1, x2, y, camada="CONCRETO"):
    """Linha de piso acabado com os traços inclinados de terreno."""
    d.linha(x1, y, x2, y, camada)
    n = max(4, int((x2 - x1) / (4.0 * est.escala)))
    passo = (x2 - x1) / n
    t = 2.6 * est.escala
    for i in range(n):
        xi = x1 + i * passo
        d.linha(xi, y, xi - t * 0.7, y - t, camada)
    return d


def _titulo_vista(d: Desenho, est: Estilo, x, y, titulo, escala_txt="", alinhamento="centro"):
    d.texto(x, y, titulo, est.tt, "TEXTO", alinhamento=alinhamento)
    larg = len(titulo) * est.tt * 0.62
    x0 = x - larg / 2 if alinhamento == "centro" else x
    d.linha(x0, y - est.tt * 0.45, x0 + larg, y - est.tt * 0.45, "TEXTO")
    if escala_txt:
        d.texto(x, y - est.tt * 1.5, f"ESCALA {escala_txt}", est.tp, "TEXTO",
                alinhamento=alinhamento)
    return d


def _notas(d: Desenho, est: Estilo, x, y, linhas: Sequence[str], titulo="NOTAS"):
    d.texto(x, y, titulo, est.t, "TEXTO")
    yy = y - est.lin
    for i, ln in enumerate(linhas):
        d.texto(x, yy - i * est.lin, f"{i + 1}. {ln}", est.tp, "TEXTO")
    return d


def _no(d: Desenho, est: Estilo, x, y, texto):
    """Marcação de nó da estrutura: círculo pequeno cheio + identificação."""
    r = 1.6 * est.escala
    d.circulo(x, y, r, "EIXO")
    d.texto(x + 2.4 * est.escala, y + 1.2 * est.escala, texto, est.tp, "TEXTO")
    return d


# =====================================================================================
# Seções transversais de perfil
# =====================================================================================

def _dims_perfil(p: Perfil) -> dict:
    """Dimensões reais da seção, em mm, já resolvendo as diferenças de catálogo.

    O catálogo guarda `d/bf/tw/tf` para perfil I, `d/bf/t` para U e Ue (a aba do
    enrijecedor de borda do Ue vem do campo `dim`), `b/t` para cantoneira e
    `D/t` ou `h/b/t` para tubo.
    """
    dd = p.dados
    tipo = p.tipo
    if tipo == "I":
        return dict(tipo="I", h=p.d, b=p.bf, tw=p.tw, tf=p.tf)
    if tipo == "U":
        return dict(tipo="U", h=p.d, b=p.bf, tw=p.tw, tf=p.tf)
    if tipo == "Ue":
        lab = 0.0
        partes = str(dd.get("dim", "")).replace(",", ".").split("×")
        if len(partes) >= 4:
            try:
                lab = float(partes[2])
            except ValueError:
                lab = 0.0
        return dict(tipo="Ue", h=p.d, b=p.bf, tw=p.tw, tf=p.tw, lab=lab)
    if tipo == "L":
        b = dd.get("b") or p.bf
        return dict(tipo="L", h=b, b=b, tw=dd.get("t", p.tw), tf=dd.get("t", p.tw))
    if tipo == "barra":
        return dict(tipo="barra", h=p.d, b=p.d, tw=p.d, tf=p.d)
    if tipo == "tubo":
        if dd.get("tipo") == "redondo":
            return dict(tipo="tubo_redondo", h=dd.get("D", p.d), b=dd.get("D", p.d),
                        tw=dd.get("t", p.tw), tf=dd.get("t", p.tw))
        return dict(tipo="tubo_retangular", h=dd.get("h", p.d), b=dd.get("b", p.bf),
                    tw=dd.get("t", p.tw), tf=dd.get("t", p.tw))
    return dict(tipo="?", h=p.d, b=p.bf, tw=p.tw, tf=p.tf)


def contorno_perfil(p: Union[Perfil, str]) -> List[List[Tuple[float, float]]]:
    """Polígonos fechados da seção transversal, em mm, centrados em (0, 0).

    Devolve uma lista: perfis abertos dão um polígono só; tubos dão o contorno externo,
    o interno e as faixas de parede (que são o que se hachura no corte).
    """
    p = _perfil(p)
    g = _dims_perfil(p)
    h, b, tw, tf = g["h"], g["b"], g["tw"], g["tf"]
    if g["tipo"] == "I":
        return [[(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + tf),
                 (tw / 2, -h / 2 + tf), (tw / 2, h / 2 - tf), (b / 2, h / 2 - tf),
                 (b / 2, h / 2), (-b / 2, h / 2), (-b / 2, h / 2 - tf),
                 (-tw / 2, h / 2 - tf), (-tw / 2, -h / 2 + tf), (-b / 2, -h / 2 + tf)]]
    if g["tipo"] == "U":
        return [[(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + tf),
                 (-b / 2 + tw, -h / 2 + tf), (-b / 2 + tw, h / 2 - tf),
                 (b / 2, h / 2 - tf), (b / 2, h / 2), (-b / 2, h / 2)]]
    if g["tipo"] == "Ue":
        t = tw
        lab = g.get("lab", 0.0) or max(15.0, 0.1 * h)
        return [[(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + lab),
                 (b / 2 - t, -h / 2 + lab), (b / 2 - t, -h / 2 + t),
                 (-b / 2 + t, -h / 2 + t), (-b / 2 + t, h / 2 - t),
                 (b / 2 - t, h / 2 - t), (b / 2 - t, h / 2 - lab),
                 (b / 2, h / 2 - lab), (b / 2, h / 2), (-b / 2, h / 2)]]
    if g["tipo"] == "L":
        t = tw
        return [[(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + t),
                 (-b / 2 + t, -h / 2 + t), (-b / 2 + t, h / 2), (-b / 2, h / 2)]]
    if g["tipo"] == "tubo_retangular":
        t = tw
        return [[(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)],
                [(-b / 2 + t, -h / 2 + t), (b / 2 - t, -h / 2 + t),
                 (b / 2 - t, h / 2 - t), (-b / 2 + t, h / 2 - t)]]
    if g["tipo"] in ("tubo_redondo", "barra"):
        return []          # tratado à parte (círculos), ver _desenhar_secao
    return [[(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]]


def _areas_hachura(p: Perfil) -> List[List[Tuple[float, float]]]:
    """Polígonos simples a hachurar no corte (para tubo, as quatro paredes)."""
    g = _dims_perfil(p)
    h, b, t = g["h"], g["b"], g["tw"]
    if g["tipo"] == "tubo_retangular":
        return [
            [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + t), (-b / 2, -h / 2 + t)],
            [(-b / 2, h / 2 - t), (b / 2, h / 2 - t), (b / 2, h / 2), (-b / 2, h / 2)],
            [(-b / 2, -h / 2 + t), (-b / 2 + t, -h / 2 + t), (-b / 2 + t, h / 2 - t),
             (-b / 2, h / 2 - t)],
            [(b / 2 - t, -h / 2 + t), (b / 2, -h / 2 + t), (b / 2, h / 2 - t),
             (b / 2 - t, h / 2 - t)],
        ]
    if g["tipo"] == "barra":                   # seção maciça: o disco inteiro
        return [[(h / 2 * math.cos(math.radians(a)), h / 2 * math.sin(math.radians(a)))
                 for a in range(0, 360, 10)]]
    if g["tipo"] == "tubo_redondo":
        R, r = h / 2, h / 2 - t
        setores = []
        for k in range(8):
            a0, a1 = math.radians(k * 45), math.radians((k + 1) * 45)
            ext = [(R * math.cos(a0 + (a1 - a0) * i / 6), R * math.sin(a0 + (a1 - a0) * i / 6))
                   for i in range(7)]
            ins = [(r * math.cos(a0 + (a1 - a0) * i / 6), r * math.sin(a0 + (a1 - a0) * i / 6))
                   for i in range(6, -1, -1)]
            setores.append(ext + ins)
        return setores
    return contorno_perfil(p)


def _desenhar_secao(d: Desenho, p: Perfil, x=0.0, y=0.0, ang_graus=0.0,
                    corte=True, camada="ACO", esp_hachura=None):
    """Insere a seção transversal de `p` em (x, y), opcionalmente hachurada."""
    g = _dims_perfil(p)
    a = math.radians(ang_graus)
    if g["tipo"] == "barra":
        d.circulo(x, y, g["h"] / 2, camada)
    elif g["tipo"] == "tubo_redondo":
        d.circulo(x, y, g["h"] / 2, camada)
        d.circulo(x, y, g["h"] / 2 - g["tw"], camada)
    else:
        for pol in contorno_perfil(p):
            d.polilinha(_mover(pol, x, y, a), fechada=True, camada=camada)
    if corte:
        # em perfil de parede fina a hachura tem que ser mais fechada que a parede,
        # senão o corte sai sem nenhuma linha dentro
        e = esp_hachura or max(1.2, min(max(g["h"], g["b"]) / 26.0, g["tw"] * 0.8))
        for pol in _areas_hachura(p):
            d.hachura(_mover(pol, x, y, a), espacamento=e, angulo=45.0)
    return d


def desenhar_perfil(perfil, x: float = 0.0, y: float = 0.0, corte: bool = True,
                    *, escala: Optional[float] = None, desenho: Optional[Desenho] = None,
                    com_cotas: bool = True, rotulo: Optional[str] = None,
                    camada: str = "ACO") -> Desenho:
    """Seção transversal de qualquer perfil do catálogo (I, U, Ue, L, tubo).

    Desenha o contorno, a hachura de corte (se `corte`), as cotas de altura, largura e
    espessuras, e o nome do perfil. É a peça reaproveitada por todos os outros desenhos
    (`_desenhar_secao` faz a parte gráfica sem as cotas).

    Parâmetros
    ----------
    perfil : `Perfil` ou nome do catálogo ("W 360×44,6", 'L 3"×1/4"'...)
    x, y   : posição do centro da seção, em mm
    corte  : hachura de corte
    escala : denominador da escala de impressão; se omitido, é escolhido para que o
             texto fique com cerca de 3 % da altura da seção.
    """
    p = _perfil(perfil)
    g = _dims_perfil(p)
    if escala is None:
        escala = max(2.0, round(max(g["h"], g["b"]) / 70.0))
    est = Estilo(escala)
    d = desenho if desenho is not None else Desenho(f"perfil {p.nome}")
    _desenhar_secao(d, p, x, y, corte=corte, camada=camada)

    h, b, tw, tf = g["h"], g["b"], g["tw"], g["tf"]
    if not com_cotas:
        return d

    if g["tipo"] == "barra":                   # barra maciça: só o diâmetro
        _eixo(d, x - h / 2, y, x + h / 2, y, sobra=0.35 * est.off)
        _eixo(d, x, y - h / 2, x, y + h / 2, sobra=0.35 * est.off)
        _cota_h(d, est, x - h / 2, x + h / 2, y + h / 2, est.off, f"%%c{_mm(h, 1)}")
        d.texto(x, y - h / 2 - est.off2 - est.tg, rotulo or p.nome, est.tg, "TEXTO",
                alinhamento="centro")
        d.texto(x, y - h / 2 - est.off2 - est.tg * 2.4,
                f"{p.massa:.2f} kg/m".replace(".", ","), est.tp, "TEXTO",
                alinhamento="centro")
        return d

    # eixos da seção
    _eixo(d, x - b / 2, y, x + b / 2, y, sobra=0.35 * est.off)
    _eixo(d, x, y - h / 2, x, y + h / 2, sobra=0.35 * est.off)

    # cotas principais
    _cota_v(d, est, y - h / 2, y + h / 2, x + b / 2, est.off, _mm(h))
    _cota_h(d, est, x - b / 2, x + b / 2, y + h / 2, est.off, _mm(b))

    # espessuras, por linha de chamada
    if g["tipo"] in ("I", "U"):
        _chamada(d, est, x, y + h * 0.18, x - b / 2 - est.off2, y + h * 0.34,
                 f"alma {_mm(tw, 1)}")
        _chamada(d, est, x + b * 0.30, y - h / 2 + tf / 2,
                 x + b / 2 + est.off2, y - h / 2 - est.off, f"mesa {_mm(tf, 1)}")
    elif g["tipo"] == "Ue":
        lab = g.get("lab", 0.0)
        _chamada(d, est, x - b / 2 + tw / 2, y, x - b / 2 - est.off2, y + h * 0.25,
                 f"t = {_mm(tw, 2)}")
        if lab:                        # enrijecedor de borda, cotado na própria aba
            _cota_v(d, est, y + h / 2 - lab, y + h / 2, x + b / 2 - tw,
                    -est.off * 0.5, _mm(lab), est.tp)
    else:
        _chamada(d, est, x + b / 2 - tw / 2, y, x + b / 2 + est.off2, y + h * 0.30,
                 f"t = {_mm(tw, 2)}")

    txt = rotulo or p.nome
    d.texto(x, y - h / 2 - est.off2 - est.tg, txt, est.tg, "TEXTO", alinhamento="centro")
    d.texto(x, y - h / 2 - est.off2 - est.tg * 2.4,
            f"{p.massa:.1f} kg/m".replace(".", ","), est.tp, "TEXTO",
            alinhamento="centro")
    return d


# =====================================================================================
# Leitura da geometria (ProjetoGalpao, DadosGalpao ou dicionário)
# =====================================================================================

#: Diâmetros de tirante do cálculo (mesma série de `nucleo/galpao.py`, TIRANTES). O nome
#: publicado arredonda o diâmetro ("ø 13 mm" para 12,7 mm); a série desfaz o arredondamento.
_TIRANTES_MM = (12.7, 16.0, 20.0, 22.2, 25.4, 31.75)

#: Rosca de cada tirante: métrica nos diâmetros métricos, UNC nos em polegada.
_ROSCAS_TIRANTE = {12.7: '1/2" UNC', 16.0: "M16", 20.0: "M20", 22.2: '7/8" UNC',
                   25.4: '1" UNC', 31.75: '1.1/4" UNC'}


def _diametro_barra(nome) -> float:
    """Diâmetro, em mm, de um nome "Barra redonda ø 20 mm" / "Barra ø 16 mm" (0 se não for)."""
    import re
    m = re.match(r"\s*barra\b.*?(\d+(?:[.,]\d+)?)\s*mm", str(nome), re.IGNORECASE)
    if not m:
        return 0.0
    d = float(m.group(1).replace(",", "."))
    for serie in _TIRANTES_MM:
        if abs(serie - d) <= 0.6:
            return serie
    return d


def _perfil_barra(d_mm: float) -> Perfil:
    """Perfil sintético de barra redonda maciça (tirante), como o do cálculo."""
    area_cm2 = math.pi * (d_mm / 10.0) ** 2 / 4.0
    nome = f"Barra redonda ø {_mm(d_mm, 1)} mm"
    return Perfil(nome=nome, tipo="barra",
                  dados={"nome": nome, "d": d_mm, "b": d_mm, "t": d_mm,
                         "A": round(area_cm2, 3), "massa": round(area_cm2 * 0.785, 2)})


def _eh_tirante(p: Perfil) -> bool:
    return p.tipo == "barra"


def _rosca(d_mm: float) -> str:
    return _ROSCAS_TIRANTE.get(d_mm, f"M{d_mm:.0f}")


def _perfil(nome_ou_perfil) -> Perfil:
    """Aceita um `Perfil` pronto, um nome do catálogo ou "Barra redonda ø N mm".

    Depois do banco de laminados vem o catálogo completo, que é quem conhece as séries
    formadas a frio (Ue, U de fábrica, cantoneira em milímetro). Sem esse passo a terça
    e o banzo da tesoura eram desenhados com a seção de um W 310, que não é a peça.
    """
    if isinstance(nome_ou_perfil, Perfil):
        return nome_ou_perfil
    d_barra = _diametro_barra(nome_ou_perfil)
    if d_barra:
        return _perfil_barra(d_barra)
    nome = str(nome_ou_perfil)
    p = banco().get(nome)
    if p is None:
        try:
            from nucleo import catalogo
            p = catalogo.perfil_de(nome)
        except Exception:
            p = None
    if p is None:                                  # nome desconhecido: não trava o desenho
        p = banco()["W 310×38,7"]
    return p


def _dados_galpao(fonte) -> DadosGalpao:
    """Normaliza a entrada num `DadosGalpao`."""
    if isinstance(fonte, ProjetoGalpao):
        return fonte.dados
    if isinstance(fonte, DadosGalpao):
        return fonte
    base = dict(PADRAO_GALPAO)
    if isinstance(fonte, dict):
        base.update({k: v for k, v in fonte.items()
                     if k in DadosGalpao.__dataclass_fields__})
    return DadosGalpao(**base)


def _perfis_galpao(fonte, dg: DadosGalpao) -> Dict[str, str]:
    """Perfis de cada peça: do projeto quando houver, senão do padrão por faixa de vão."""
    pilar = viga = terca = longarina = None
    if isinstance(fonte, ProjetoGalpao):
        for chave, alvo in (("pilar", "pilar"), ("viga", "viga"), ("terça", "terca"),
                            ("longarina", "longarina")):
            el = fonte.elemento(chave)
            if el and el.perfil:
                if alvo == "pilar":
                    pilar = el.perfil
                elif alvo == "viga":
                    viga = el.perfil
                elif alvo == "terca":
                    terca = el.perfil
                else:
                    longarina = el.perfil
    if isinstance(fonte, dict):
        pilar = fonte.get("perfil_pilar", pilar)
        viga = fonte.get("perfil_viga", viga)
        terca = fonte.get("perfil_terca", terca)
        longarina = fonte.get("perfil_longarina", longarina)
    if not (pilar and viga):
        for vmax, pp, pv in PADRAO_PERFIS:
            if dg.vao <= vmax:
                pilar = pilar or pp
                viga = viga or pv
                break
    terca = terca or (PADRAO_TERCA if dg.espacamento_porticos <= 6.0
                      else PADRAO_TERCA_GRANDE)
    longarina = longarina or PADRAO_LONGARINA
    # contraventamentos: nome exato, porque "Contraventamento" casaria os dois
    cob = vert = None
    if isinstance(fonte, ProjetoGalpao):
        el = _elemento(fonte, "Contraventamento de cobertura")
        cob = el.perfil if el is not None and el.perfil else None
        el = _elemento(fonte, "Contraventamento vertical")
        vert = el.perfil if el is not None and el.perfil else None
    if isinstance(fonte, dict):
        cob = fonte.get("perfil_contrav_cobertura", cob)
        vert = fonte.get("perfil_contrav_vertical", vert)
    cob = cob or PADRAO_CONTRAV_COBERTURA
    vert = vert or PADRAO_CONTRAV_VERTICAL
    return dict(pilar=pilar, viga=viga, terca=terca, longarina=longarina,
                coluna_oitao=PADRAO_COLUNA_OITAO,
                contrav_cobertura=cob, contrav_vertical=vert,
                diagonal=vert, escora=PADRAO_ESCORA)


def _altura_misula_calculada(fonte) -> float:
    """Altura total da seção no joelho adotada pelo cálculo da ligação, em mm (0 se não houver)."""
    ligacoes = getattr(fonte, "ligacoes", None) or {}
    r = ligacoes.get("viga-pilar") if isinstance(ligacoes, dict) else None
    try:
        return float((r.dados or {}).get("altura_misula_mm") or 0.0)
    except Exception:
        return 0.0


def _geometria_contraventamento(fonte, nome: str) -> dict:
    """Geometria publicada pelo cálculo para o contraventamento, ou vazio.

    Só vale quando traz `vaos_contraventados`, que marca o contrato em que `paineis`
    significa painéis ao longo do vão.
    """
    elementos = getattr(fonte, "elementos", None) or []
    for el in elementos:
        if getattr(el, "nome", "") == nome and isinstance(getattr(el, "geometria", None), dict):
            geo = el.geometria
            return geo if geo.get("vaos_contraventados") else {}
    return {}


def _vaos_contrav(g, nome: str, n_vaos: int) -> List[int]:
    """Vãos contraventados (índice a partir de 0): do cálculo, ou extremos e central."""
    geo = _geometria_contraventamento(g.fonte, nome)
    vaos = set()
    for v in geo.get("vaos_contraventados") or []:
        try:
            iv = int(v) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= iv < max(n_vaos, 1):
            vaos.add(iv)
    if vaos:
        return sorted(vaos)
    return sorted({0, n_vaos - 1, max(0, (n_vaos - 1) // 2)}) if n_vaos >= 2 else [0]


def _paineis_contrav(g, vao_mm: float) -> int:
    """Painéis ao longo do vão no X de cobertura: do cálculo, ou vão/espaçamento."""
    geo = _geometria_contraventamento(g.fonte, "Contraventamento de cobertura")
    try:
        n = int(geo.get("paineis") or 0)
    except (TypeError, ValueError):
        n = 0
    return n if n >= 1 else max(2, int(round(vao_mm / max(g.esp_port, 1.0))))


def _elemento(fonte, nome: str):
    """Elemento do projeto pelo nome exato (`ProjetoGalpao.elemento` casa por prefixo)."""
    for el in getattr(fonte, "elementos", None) or []:
        if getattr(el, "nome", "") == nome:
            return el
    return None


def _inteiro(x, minimo: int) -> Optional[int]:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return int(x) if x >= minimo else None


#: Recuos da primeira e da última terça, ao longo da água (Cap. 16, passo 1; é também a
#: regra de `nucleo/galpao.py`, que os publica em `recuo_beiral_m` e `recuo_cumeeira_m`).
RECUO_BEIRAL_TERCA = 200.0
RECUO_CUMEEIRA_TERCA = 250.0


def _tercas_calc(g) -> Tuple[int, float, int, float]:
    """(vãos de terça por água, espaçamento ao longo da água em mm, linhas de corrente,
    recuo da primeira terça ao beiral ao longo da água em mm).

    Do elemento "Terça" quando o cálculo o publicou (`linhas` por água,
    `espacamento_m`, `recuo_beiral_m`, `n_correntes`): o desenho posiciona exatamente o
    publicado, sem recalcular. Sem o elemento, a regra do cálculo: primeira terça a
    200 mm do beiral, última a 250 mm da cumeeira, número de vãos arredondado para cima
    para o espaçamento não passar do pedido.
    """
    agua = (g.vao / 2.0) / math.cos(g.theta)
    el = _elemento(g.fonte, "Terça")
    geo = el.geometria if el is not None and isinstance(el.geometria, dict) else {}
    rec_b = _valor(geo, "recuo_beiral_m", 1000.0)
    rec_c = _valor(geo, "recuo_cumeeira_m", 1000.0)
    linhas = _inteiro(geo.get("linhas", geo.get("por_agua")), 2)
    esp = _valor(geo, "espacamento_m", 1000.0)
    if linhas and esp:
        n_esp = linhas - 1
        if rec_b is None:
            # contrato antigo, sem recuos: o que sobra da água fica metade em cada ponta
            rec_b = max(0.0, (agua - n_esp * esp) / 2.0)
    else:
        rec_b = RECUO_BEIRAL_TERCA if rec_b is None else rec_b
        rec_c = RECUO_CUMEEIRA_TERCA if rec_c is None else rec_c
        util = max(agua - rec_b - rec_c, 1.0)
        n_esp = max(1, int(math.ceil(util / max(g.esp_terca, 1.0) - 1e-9)))
        esp = util / n_esp
    n_corr = _inteiro(geo.get("n_correntes"), 0)
    if n_corr is None:
        n_corr = max(0, int(g.dg.linhas_correntes))
    return n_esp, esp, n_corr, rec_b


def _fiadas_longarina(g) -> Tuple[List[float], float]:
    """Alturas das fiadas de longarina, em mm, e o espaçamento entre elas.

    Do elemento "Longarina de fechamento" quando ele publicar `fiadas_por_lado` (ou
    `fiadas`/`linhas`) e `espacamento_m`: as n fiadas ficam a esse espaçamento,
    centradas na altura da parede, ou nas `cotas_fiadas_m` publicadas pelo cálculo. Sem
    o elemento, fiadas a cada 1,9 m a partir do piso, parando 300 mm abaixo do beiral
    (Cap. 16, passo 1: 1,90 / 3,80 / 5,70 m para 6 m).
    """
    H = g.h_beiral
    el = _elemento(g.fonte, "Longarina de fechamento")
    geo = el.geometria if el is not None and isinstance(el.geometria, dict) else {}
    cotas = geo.get("cotas_fiadas_m")
    if cotas:
        ys = [float(c) * 1000.0 for c in cotas]
        if ys and 0.0 < ys[0] and ys[-1] < H:
            return ys, (ys[1] - ys[0]) if len(ys) > 1 else H
    n = _inteiro(geo.get("fiadas_por_lado", geo.get("fiadas", geo.get("linhas"))), 1)
    if n:
        passo = _valor(geo, "espacamento_m", 1000.0) or H / (n + 1.0)
        y0 = (H - (n - 1) * passo) / 2.0
        ys = [y0 + k * passo for k in range(n)]
        if ys[0] > 0.0 and ys[-1] < H:
            return ys, passo
    passo = 1900.0
    ys = [k * passo for k in range(1, 20) if k * passo <= H - 300.0]
    return (ys, passo) if ys else ([H / 2.0], H / 2.0)


def _lista_vaos(indices) -> str:
    """[0, 3, 7] -> "1, 4 e 8"."""
    n = [str(i + 1) for i in indices]
    return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " e " + n[-1]


class _Geo:
    """Geometria do pórtico em milímetros, derivada de `DadosGalpao`."""

    def __init__(self, fonte):
        self.fonte = fonte
        dg = _dados_galpao(fonte)
        self.dg = dg
        self.perfis = _perfis_galpao(fonte, dg)
        self.pilar = _perfil(self.perfis["pilar"])
        self.viga = _perfil(self.perfis["viga"])
        self.terca = _perfil(self.perfis["terca"])
        self.longarina = _perfil(self.perfis["longarina"])

        self.vao = dg.vao * 1000.0
        self.comprimento = dg.comprimento * 1000.0
        self.H = dg.pe_direito * 1000.0
        self.esp_port = dg.espacamento_porticos * 1000.0
        self.i = dg.inclinacao / 100.0
        self.theta = math.atan(self.i)
        self.flecha = (self.vao / 2.0) * self.i
        # na tesoura o pé-direito é o nível do banzo inferior: a parede sobe mais a
        # altura da tesoura até o beiral, e é de lá que o telhado começa a subir
        self.h_tesoura = dg.altura_tesoura_m * 1000.0
        self.h_beiral = self.H + self.h_tesoura
        self.h_cumeeira = self.h_beiral + self.flecha
        self.trelicado = bool(dg.eh_trelicado)
        self.balanco = dg.balanco_lateral * 1000.0
        self.esp_terca = dg.espacamento_tercas * 1000.0
        self.com_misula = bool(dg.com_misula)
        self.L_misula = dg.comprimento_misula * 1000.0 if self.com_misula else 0.0
        self.h_misula = (dg.altura_misula * 1000.0) or self.viga.d
        # a ligação de joelho foi dimensionada com uma altura total de seção; o
        # desenho mostra a mísula com essa altura, descontada a própria viga
        alt_calc = _altura_misula_calculada(fonte)
        if self.com_misula and alt_calc > self.viga.d:
            self.h_misula = alt_calc - self.viga.d
        self.rotulada = bool(dg.base_rotulada)
        self.n_porticos = dg.n_porticos
        self.d_pilar = self.pilar.d
        self.d_viga = self.viga.d


# =====================================================================================
# 1. Pórtico — elevação
# =====================================================================================

def _agua(g: _Geo, espelhar: bool) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Extremos da linha inferior do rafter de uma água (joelho → cumeeira)."""
    x0 = 0.0 if not espelhar else g.vao
    s = 1.0 if not espelhar else -1.0
    return (x0, g.h_beiral), (x0 + s * g.vao / 2.0, g.h_cumeeira)


def _faixa(d: Desenho, p1, p2, esp, lado=1, camada="ACO", fechar=True):
    """Barra desenhada como faixa de espessura `esp` a partir da linha p1→p2.

    `lado = +1` joga a espessura para a esquerda do sentido p1→p2. Devolve os quatro
    cantos (p1, p2, p2', p1').
    """
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    c = math.hypot(dx, dy)
    if c < 1e-9:
        return []
    nx, ny = -dy / c * lado * esp, dx / c * lado * esp
    q1 = (p1[0] + nx, p1[1] + ny)
    q2 = (p2[0] + nx, p2[1] + ny)
    pts = [p1, p2, q2, q1]
    if fechar:
        d.polilinha(pts, fechada=True, camada=camada)
    return pts


def portico(projeto) -> Desenho:
    """Elevação do pórtico transversal: de alma cheia ou treliçado.

    O pórtico treliçado é desenhado por `portico_trelicado`; daqui para baixo é o de
    alma cheia. Desenhar um pórtico de alma cheia onde a estrutura é uma tesoura seria
    uma prancha falsa, então o desvio é na entrada.
    """
    if _dados_galpao(projeto).eh_trelicado:
        return portico_trelicado(projeto)
    return _portico_alma_cheia(projeto)


def _portico_alma_cheia(projeto) -> Desenho:
    """Elevação do pórtico transversal completo (Cap. 16, Figura 16.2).

    Mostra pilares, vigas inclinadas, mísulas, as três ligações (joelho, cumeeira e
    base) com a chamada do detalhe correspondente, e as bases. Cotas: vão entre eixos,
    pé-direito, altura de cumeeira, inclinação, comprimento de mísula e meia-vão.
    """
    g = _Geo(projeto)
    est = Estilo(100.0)
    d = Desenho("portico")

    H, V, hc = g.H, g.vao, g.h_cumeeira
    dp, dv = g.d_pilar, g.d_viga

    # ---------------- pilares ----------------
    for x in (0.0, V):
        d.retangulo(x - dp / 2, 0.0, dp, H, "ACO")
        d.linha(x - dp / 2 + g.pilar.tf, 0.0, x - dp / 2 + g.pilar.tf, H, "ACO-FINO")
        d.linha(x + dp / 2 - g.pilar.tf, 0.0, x + dp / 2 - g.pilar.tf, H, "ACO-FINO")
        _eixo(d, x, -est.off, x, hc * 0.2)

    # ---------------- vigas (duas águas) ----------------
    for espelhar in (False, True):
        (xa, ya), (xb, yb) = _agua(g, espelhar)
        s = -1 if espelhar else 1
        # a faixa da viga sobe do lado de fora do joelho (banzo inferior na linha)
        _faixa(d, (xa, ya), (xb, yb), dv, lado=s)
        # mesas em vista
        for f in (g.viga.tf, dv - g.viga.tf):
            nx, ny = -math.sin(g.theta) * s, math.cos(g.theta)
            d.linha(xa + nx * f, ya + ny * f, xb + nx * f, yb + ny * f, "ACO-FINO")
        # balanço do beiral
        if g.balanco > 0:
            xc = xa - s * g.balanco
            yc = ya - g.balanco * g.i
            _faixa(d, (xc, yc), (xa, ya), dv, lado=s)

    # ---------------- mísulas ----------------
    if g.com_misula and g.L_misula > 0:
        for espelhar in (False, True):
            (xa, ya), _ = _agua(g, espelhar)
            s = -1 if espelhar else 1
            ux, uy = math.cos(g.theta) * s, math.sin(g.theta)
            nx, ny = math.sin(g.theta) * s, -math.cos(g.theta)      # para baixo
            raiz = (xa + nx * g.h_misula, ya + ny * g.h_misula)
            fim = (xa + ux * g.L_misula, ya + uy * g.L_misula)
            d.polilinha([(xa, ya), fim, raiz], fechada=True, camada="ACO")
            # mesa inferior da mísula, recuada da aresta pela espessura da mesa
            tf = g.viga.tf
            cx_, cy_ = fim[0] - raiz[0], fim[1] - raiz[1]
            c_ = math.hypot(cx_, cy_) or 1.0
            mx, my = -cy_ / c_ * tf * s, cx_ / c_ * tf * s
            d.linha(raiz[0] + mx, raiz[1] + my, fim[0] + mx, fim[1] + my, "ACO-FINO")
            # enrijecedor obrigatório no fim da mísula (Cap. 14.3.3)
            d.linha(fim[0] - nx * g.h_misula * 0.12, fim[1] - ny * g.h_misula * 0.12,
                    fim[0] + nx * g.h_misula * 0.12, fim[1] + ny * g.h_misula * 0.12,
                    "ACO")

    # ---------------- bases ----------------
    ped_b = dp + 2 * PADRAO_BASE["pedestal_folga"]
    ped_h = 600.0
    for x in (0.0, V):
        d.retangulo(x - ped_b / 2, -ped_h, ped_b, ped_h, "CONCRETO")
        d.hachura([(x - ped_b / 2, -ped_h), (x + ped_b / 2, -ped_h),
                   (x + ped_b / 2, 0.0), (x - ped_b / 2, 0.0)],
                  espacamento=90.0, angulo=45.0)
        pl = PADRAO_BASE["placa_L"]
        d.retangulo(x - pl / 2, 0.0, pl, PADRAO_BASE["placa_t"] * 3, "ACO")
    _terreno(d, est, -V * 0.08, V * 1.08, 0.0)

    # ---------------- nós ----------------
    _no(d, est, 0.0, 0.0, "N1")
    _no(d, est, 0.0, H, "N2")
    _no(d, est, V / 2.0, hc, "N3")
    _no(d, est, V, H, "N4")
    _no(d, est, V, 0.0, "N5")

    # ---------------- indicação das ligações ----------------
    r_lig = 0.055 * V
    for x, nome, det in ((0.0, "JOELHO", "DET. 04"), (V, "JOELHO", "DET. 04")):
        d.circulo(x, H, r_lig, "AUXILIAR")
    d.circulo(V / 2.0, hc, r_lig, "AUXILIAR")
    for x in (0.0, V):
        d.circulo(x, 0.0, r_lig * 0.7, "AUXILIAR")

    # chamadas: as das ligações vão para dentro do pórtico (área livre) e as dos
    # perfis para fora, de modo que nenhuma linha de chamada cruze outra
    _chamada(d, est, r_lig * 0.7, H + r_lig * 0.7, V * 0.20, H * 0.80,
             "LIGACAO DE JOELHO - CHAPA DE TOPO", est.tp,
             linhas=["VER DET. 04"])
    _chamada(d, est, V / 2.0 + r_lig * 0.7, hc + r_lig * 0.5,
             V * 0.66, hc + 0.26 * hc, "LIGACAO DE CUMEEIRA - VER DET. 05", est.tp)
    _chamada(d, est, V + r_lig * 0.5, -r_lig * 0.4, V * 0.82, -ped_h - est.off2 * 1.6,
             "BASE " + ("ROTULADA" if g.rotulada else "ENGASTADA") + " - VER DET. 06",
             est.tp)

    # ---------------- identificação dos perfis ----------------
    _chamada(d, est, -dp / 2, H * 0.42, -est.off3 - V * 0.10, H * 0.30,
             f"PILAR P1  {g.pilar.nome}", est.tp,
             linhas=[f"{g.pilar.massa:.1f} kg/m".replace(".", ","),
                     f"L = {_mm(H)} mm"])
    xm = V * 0.30
    ym = H + xm * g.i + g.d_viga
    _chamada(d, est, xm, ym, V * 0.24, hc + 0.26 * hc,
             f"VIGA V1  {g.viga.nome}  ({g.viga.massa:.1f} kg/m)".replace(".0 kg", ",0 kg"),
             est.tp)
    if g.com_misula and g.L_misula > 0:
        ux, uy = math.cos(g.theta), math.sin(g.theta)
        px = ux * g.L_misula * 0.55
        py = H + uy * g.L_misula * 0.55 - g.h_misula * 0.35
        _chamada(d, est, px, py, V * 0.20, H * 0.55,
                 f"MISULA M1  {g.viga.nome} CORTADO", est.tp,
                 linhas=[f"Lm = {_mm(g.L_misula)}   hm = {_mm(g.h_misula)}"])

    # ---------------- cotas ----------------
    y_cota = -ped_h - est.off
    _cota_h(d, est, 0.0, V / 2.0, y_cota, -est.off, _mm(V / 2.0))
    _cota_h(d, est, V / 2.0, V, y_cota, -est.off, _mm(V / 2.0))
    _cota_h(d, est, 0.0, V, y_cota, -est.off2 - est.off, _mm(V))
    d.texto(V / 2.0, y_cota - est.off3 - est.t * 1.6, "VAO ENTRE EIXOS DE PILARES",
            est.tp, "TEXTO", alinhamento="centro")

    x_cota = -dp / 2 - est.off
    _cota_v(d, est, 0.0, H, x_cota, -est.off, f"{_mm(H)}  (PE-DIREITO)")

    x_cota_d = V + dp / 2 + est.off
    _cota_v(d, est, H, hc, x_cota_d, est.off, _mm(g.flecha))
    _cota_v(d, est, 0.0, hc, x_cota_d, est.off2 + est.off,
            f"{_mm(hc)}  (CUMEEIRA)")

    # inclinação: triângulo de declividade sobre a água esquerda, longe das chamadas
    xt = V * 0.30
    yt = H + xt * g.i + dv + est.off * 1.2
    base_t = V * 0.08
    d.linha(xt, yt, xt + base_t, yt + base_t * g.i, "COTA")
    d.linha(xt, yt, xt + base_t, yt, "COTA")
    d.linha(xt + base_t, yt, xt + base_t, yt + base_t * g.i, "COTA")
    d.texto(xt + base_t * 0.5, yt - est.t * 1.1, "100", est.tp, "COTA",
            alinhamento="centro")
    d.texto(xt + base_t * 1.15, yt + base_t * g.i * 0.5,
            f"{g.dg.inclinacao:g}".replace(".", ","), est.tp, "COTA")

    # comprimento de mísula, cotado ao longo da viga (do lado de fora, abaixo)
    if g.com_misula and g.L_misula > 0:
        ux, uy = math.cos(g.theta), math.sin(g.theta)
        _cota(d, est, 0.0, H, ux * g.L_misula, H + uy * g.L_misula,
              g.d_viga + est.off * 0.6, f"MISULA {_mm(g.L_misula)}")

    # ---------------- rótulo e notas ----------------
    x_tit = V / 2.0
    y_tit = y_cota - est.off3 - est.tt * 3.2
    _titulo_vista(d, est, x_tit, y_tit, "PORTICO TIPICO - ELEVACAO", est.texto_escala())
    notas = [
        "Cotas em milimetros. Desenho em escala 1:1 no modelo.",
        f"Aco dos perfis: {g.dg.aco_perfis}; chapas: {g.dg.aco_chapas}.",
        f"Parafusos {g.dg.parafuso}; eletrodo {g.dg.eletrodo}.",
        f"Inclinacao {g.dg.inclinacao:g} %%% ({math.degrees(g.theta):.1f}%%d).".replace(".", ","),
        f"{g.n_porticos} porticos a cada {_mm(g.esp_port)} mm.",
        "Bases " + ("rotuladas" if g.rotulada else "engastadas") + " - ver DET. 06.",
    ]
    _notas(d, est, -dp / 2 - est.off, y_tit - est.tt * 2.0, notas)
    return d


# =====================================================================================
# 1b. Pórtico treliçado — elevação da tesoura
# =====================================================================================

def _tesoura_do_projeto(fonte, dg: DadosGalpao):
    """A tesoura desenhada é a mesma que o cálculo montou.

    Sem cálculo (pré-visualização do formulário) ela é remontada com os mesmos dados,
    pelo mesmo gerador — o desenho nunca inventa uma malha que o cálculo não viu.
    """
    if isinstance(fonte, ProjetoGalpao):
        t = (fonte.esforcos or {}).get("geometria_tesoura")
        if t is not None:
            return t
    from nucleo import tesouras
    return tesouras.geometria(
        vao=dg.vao * 100, inclinacao=dg.inclinacao / 100.0, formato=dg.formato_tesoura,
        diagonais=dg.diagonais_tesoura, altura_apoio=dg.altura_tesoura * 100,
        paineis=dg.paineis_tesoura, espacamento_tercas=dg.espacamento_tercas * 100)


def _perfis_tesoura(fonte) -> Dict[str, str]:
    """Perfil de cada família de barra da tesoura, pelo nome que o cálculo publicou."""
    from nucleo.galpao import NOME_DA_BARRA
    from nucleo import tesouras
    saida = {}
    for papel in tesouras.PAPEIS:
        el = _elemento(fonte, NOME_DA_BARRA[papel])
        if el is not None and el.perfil:
            saida[papel] = el.perfil
    return saida


def _barra_centrada(d: Desenho, p1, p2, esp: float, camada="ACO"):
    """Barra desenhada como faixa de espessura `esp` centrada no eixo p1→p2."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    c = math.hypot(dx, dy)
    if c < 1e-9 or esp <= 0:
        return
    nx, ny = -dy / c * esp / 2.0, dx / c * esp / 2.0
    d.polilinha([(p1[0] + nx, p1[1] + ny), (p2[0] + nx, p2[1] + ny),
                 (p2[0] - nx, p2[1] - ny), (p1[0] - nx, p1[1] - ny)],
                fechada=True, camada=camada)


def portico_trelicado(projeto) -> Desenho:
    """Elevação do pórtico transversal com tesoura treliçada.

    Mostra os dois pilares, a tesoura inteira (banzos, diagonais e montantes, cada barra
    com a altura do perfil adotado), as bases e as cotas que a fábrica usa: vão, painel,
    altura da tesoura no apoio e na cumeeira, pé-direito e beiral.
    """
    from nucleo import tesouras as _tes
    g = _Geo(projeto)
    dg = g.dg
    t = _tesoura_do_projeto(projeto, dg)
    perfis = _perfis_tesoura(projeto)
    est = Estilo(100.0)
    d = Desenho("portico-trelicado")

    H, V = g.H, g.vao
    hc = g.h_cumeeira
    dp = g.d_pilar
    esp = {}
    for papel in _tes.PAPEIS:
        nome = perfis.get(papel)
        esp[papel] = _perfil(nome).d if nome else (120.0 if papel.startswith("banzo") else 60.0)

    def ponto(nome_no):
        n = t.no(nome_no)
        return (n.x * 10.0, H + n.y * 10.0)

    # ---------------- pilares ----------------
    topo = H + (t.altura_apoio * 10.0 if dg.ligacao_tesoura == "rígida" else 0.0)
    for x in (0.0, V):
        d.retangulo(x - dp / 2, 0.0, dp, topo, "ACO")
        d.linha(x - dp / 2 + g.pilar.tf, 0.0, x - dp / 2 + g.pilar.tf, topo, "ACO-FINO")
        d.linha(x + dp / 2 - g.pilar.tf, 0.0, x + dp / 2 - g.pilar.tf, topo, "ACO-FINO")
        _eixo(d, x, -est.off, x, hc * 0.2)

    # ---------------- tesoura ----------------
    pular = {"mont_esq", "mont_dir"} if dg.ligacao_tesoura == "rígida" else set()
    for b in t.barras:
        if b.rotulo in pular:
            continue
        camada = "ACO" if b.papel.startswith("banzo") else "ACO-FINO"
        _barra_centrada(d, ponto(b.i), ponto(b.j), esp[b.papel], camada)
    for n in t.nos:                       # chapas de nó, em linha auxiliar
        x, y = ponto(n.nome)
        d.circulo(x, y, max(esp.values()) * 0.45, "AUXILIAR")

    # ---------------- bases ----------------
    ped_b = dp + 2 * PADRAO_BASE["pedestal_folga"]
    ped_h = 600.0
    for x in (0.0, V):
        d.retangulo(x - ped_b / 2, -ped_h, ped_b, ped_h, "CONCRETO")
        d.hachura([(x - ped_b / 2, -ped_h), (x + ped_b / 2, -ped_h),
                   (x + ped_b / 2, 0.0), (x - ped_b / 2, 0.0)],
                  espacamento=90.0, angulo=45.0)
        pl = PADRAO_BASE["placa_L"]
        d.retangulo(x - pl / 2, 0.0, pl, PADRAO_BASE["placa_t"] * 3, "ACO")
    _terreno(d, est, -V * 0.08, V * 1.08, 0.0)

    # ---------------- chamadas ----------------
    r_lig = 0.045 * V
    d.circulo(0.0, H, r_lig, "AUXILIAR")
    d.circulo(V, H, r_lig, "AUXILIAR")
    _chamada(d, est, r_lig * 0.7, H + r_lig * 0.7, V * 0.18, H * 0.78,
             "LIGACAO TESOURA-PILAR", est.tp, linhas=["CHAPA DE TOPO DO PILAR"])
    meio = t.no(("BI%d" % t.paineis) if t.formato != "banzos paralelos" else "TS%d" % t.paineis)
    _chamada(d, est, V * 0.5, H + meio.y * 10.0, V * 0.62, hc + 0.22 * hc,
             "CHAPA DE NO - GUSSET", est.tp)
    _chamada(d, est, V + r_lig * 0.5, -r_lig * 0.4, V * 0.82, -ped_h - est.off2 * 1.6,
             "BASE " + ("ROTULADA" if g.rotulada else "ENGASTADA") + " - VER DET. 06",
             est.tp)
    _chamada(d, est, -dp / 2, topo * 0.42, -est.off3 - V * 0.10, topo * 0.30,
             f"PILAR P1  {g.pilar.nome}", est.tp,
             linhas=[f"{g.pilar.massa:.1f} kg/m".replace(".", ","), f"L = {_mm(topo)} mm"])

    rotulo = {"banzo superior": "BS", "banzo inferior": "BI",
              "diagonal": "D", "montante": "M"}
    linhas = [f"{rotulo[p]}  {perfis[p]}" for p in _tes.PAPEIS if p in perfis]
    if linhas:
        _chamada(d, est, V * 0.5, hc, V * 0.24, hc + 0.30 * hc,
                 "PERFIS DA TESOURA", est.tp, linhas=linhas)

    # ---------------- cotas ----------------
    y_cota = -ped_h - est.off
    _cota_h(d, est, 0.0, V / 2.0, y_cota, -est.off, _mm(V / 2.0))
    _cota_h(d, est, V / 2.0, V, y_cota, -est.off, _mm(V / 2.0))
    _cota_h(d, est, 0.0, V, y_cota, -est.off2 - est.off, _mm(V))
    d.texto(V / 2.0, y_cota - est.off3 - est.t * 1.6, "VAO ENTRE EIXOS DE PILARES",
            est.tp, "TEXTO", alinhamento="centro")
    # painéis do banzo superior, na cadeia que a fábrica marca
    xs = [t.no("TS%d" % k).x * 10.0 for k in range(2 * t.paineis + 1)]
    _cadeia_h(d, est, xs, y_cota, est.off * 0.8)

    x_cota = -dp / 2 - est.off
    _cota_v(d, est, 0.0, H, x_cota, -est.off, f"{_mm(H)}  (PE-DIREITO)")
    if t.altura_apoio > 0:
        _cota_v(d, est, H, H + t.altura_apoio * 10.0, x_cota, -est.off2 - est.off,
                f"{_mm(t.altura_apoio * 10.0)}  (TESOURA NO APOIO)")
    x_cota_d = V + dp / 2 + est.off
    _cota_v(d, est, H, hc, x_cota_d, est.off, _mm(hc - H))
    _cota_v(d, est, 0.0, hc, x_cota_d, est.off2 + est.off, f"{_mm(hc)}  (CUMEEIRA)")

    # ---------------- rótulo e notas ----------------
    y_tit = y_cota - est.off3 - est.tt * 3.6
    _titulo_vista(d, est, V / 2.0, y_tit, "PORTICO TRELICADO - ELEVACAO",
                  est.texto_escala())
    notas = [
        "Cotas em milimetros. Desenho em escala 1:1 no modelo.",
        f"Tesoura {t.formato}, diagonais {t.diagonais}, "
        f"{t.paineis} paineis por agua.".upper(),
        f"Aco dos perfis: {dg.aco_perfis}; chapas: {dg.aco_chapas}.",
        f"Parafusos {dg.parafuso}; eletrodo {dg.eletrodo}.",
        f"Tesoura {dg.ligacao_tesoura} no pilar; bases "
        + ("rotuladas" if g.rotulada else "engastadas") + ".",
        f"{g.n_porticos} porticos a cada {_mm(g.esp_port)} mm.",
    ]
    _notas(d, est, -dp / 2 - est.off, y_tit - est.tt * 2.0, notas)
    return d


# =====================================================================================
# 2. Planta de cobertura
# =====================================================================================

def planta_cobertura(projeto) -> Desenho:
    """Planta de cobertura (Cap. 16, Figura 16.1).

    Eixo X = comprimento do galpão; eixo Y = vão. Mostra os pórticos (marcados P1…Pn),
    as terças com o espaçamento cotado, as linhas de correntes no meio de cada vão, o
    contraventamento em X nos vãos extremos e no central, as escoras dos nós, a linha
    de cumeeira e as linhas de beiral.
    """
    g = _Geo(projeto)
    est = Estilo(200.0)
    d = Desenho("planta-cobertura")

    C, V = g.comprimento, g.vao
    xs = [i * g.esp_port for i in range(g.n_porticos)]
    if xs and abs(xs[-1] - C) > 1.0:            # comprimento não múltiplo do espaçamento
        xs[-1] = C
    y_cum = V / 2.0

    # ---------------- pórticos ----------------
    bfv = g.viga.bf
    for i, x in enumerate(xs):
        d.retangulo(x - bfv / 2, 0.0, bfv, V, "ACO")
        _eixo(d, x, -est.off * 0.8, x, V + est.off * 0.8)
        d.texto(x, V + est.off * 1.4, f"P{i + 1}", est.t, "TEXTO", alinhamento="centro")

    # ---------------- terças ----------------
    # a distribuição publicada pelo cálculo (ver _tercas_calc): recuo e espaçamento são
    # medidos ao longo da água e aqui aparecem projetados (× cos θ). Cada terça é
    # desenhada para dentro da sua água.
    n_vao_terca, esp_incl, n_corr, rec_incl = _tercas_calc(g)
    cos_t = math.cos(g.theta)
    passo = esp_incl * cos_t
    rec_b = rec_incl * cos_t
    meia = [rec_b + k * passo for k in range(n_vao_terca + 1)]
    bft = g.terca.bf
    ys_terca = []
    for y in meia:                                   # água de baixo
        y0 = min(y, y_cum - bft)
        ys_terca.append(y0)
        d.linha(0.0, y0, C, y0, "ACO-FINO")
        d.linha(0.0, y0 + bft, C, y0 + bft, "ACO-FINO")
    for y in meia:                                   # água de cima, espelhada
        y1 = max(V - y, y_cum + bft)
        ys_terca.append(y1 - bft)
        d.linha(0.0, y1, C, y1, "ACO-FINO")
        d.linha(0.0, y1 - bft, C, y1 - bft, "ACO-FINO")
    ys_terca.sort()

    # ---------------- cumeeira e beirais ----------------
    _eixo(d, -est.off * 0.5, y_cum, C + est.off * 0.5, y_cum)
    d.texto(C + est.off * 0.35, y_cum, "CUMEEIRA", est.t, "TEXTO",
            vertical="meio")
    for yb in (0.0, V):
        d.linha(0.0, yb, C, yb, "ACO")

    # ---------------- correntes (tirantes de terça) ----------------
    # número de linhas por vão: o do cálculo da terça (pode ter subido de 1 para 2 ou 3)
    y_ini = min(meia[0] + bft, y_cum)      # face da terça de beiral
    y_ult = min(meia[-1], y_cum - bft)     # face da terça de cumeeira
    for i in range(len(xs) - 1):
        bay = xs[i + 1] - xs[i]
        for k in range(1, n_corr + 1):
            xc = xs[i] + bay * k / (n_corr + 1.0)
            d.linha(xc, y_ini, xc, y_ult, "AUXILIAR")
            d.linha(xc, V - y_ult, xc, V - y_ini, "AUXILIAR")
            # tirante de cumeeira em V, ligando as duas terças de cumeeira
            d.linha(xc, y_ult, xc + bay * 0.06, y_cum, "AUXILIAR")
            d.linha(xc, V - y_ult, xc + bay * 0.06, y_cum, "AUXILIAR")

    # ---------------- contraventamento em X ----------------
    n_vaos = len(xs) - 1
    vaos_x = _vaos_contrav(g, "Contraventamento de cobertura", n_vaos)
    n_pain = _paineis_contrav(g, V)
    ys_pain = [V * k / n_pain for k in range(n_pain + 1)]
    for iv in vaos_x:
        x1, x2 = xs[iv], xs[iv + 1]
        for k in range(n_pain):
            ya, yb = ys_pain[k], ys_pain[k + 1]
            d.linha(x1, ya, x2, yb, "ACO")
            d.linha(x1, yb, x2, ya, "ACO")
        for yp in ys_pain[1:-1]:                       # escoras nos nós
            d.linha(x1, yp, x2, yp, "ACO")
        d.texto((x1 + x2) / 2.0, V + est.off * 0.45, f"CC-{iv + 1}", est.t, "TEXTO",
                alinhamento="centro")

    # ---------------- marcas e chamadas ----------------
    ix = vaos_x[0]
    cc = _perfil(g.perfis["contrav_cobertura"])
    _chamada(d, est, (xs[ix] + xs[ix + 1]) / 2.0, ys_pain[1] * 0.5,
             -est.off2, V + est.off3 * 1.2,
             "CONTRAVENTAMENTO DE COBERTURA (CC)", est.tp,
             linhas=[(f"tirante %%c{_mm(cc.d, 1)} mm com esticador" if _eh_tirante(cc)
                      else cc.nome),
                     f"{n_pain} paineis por vao - ver DET. 08"])
    yt_ref = ys_terca[-2]
    _chamada(d, est, C * 0.55, yt_ref, C * 0.58, V + est.off3 * 1.2,
             f"TERCA T1  {g.terca.nome}", est.tp,
             linhas=[f"{len(ys_terca)} linhas a cada {_mm(esp_incl)} mm",
                     "(na inclinacao) - ver DET. 07"])
    xc_ref = xs[len(xs) // 2] + (xs[1] - xs[0]) * 0.5 if len(xs) > 2 else C / 2.0
    if n_corr:
        _chamada(d, est, xc_ref, y_cum * 0.60, C * 0.30, -est.off3 * 1.3,
                 f"CORRENTE %%c{_mm(PADRAO_DIAM_CORRENTE)} COM ESTICADOR", est.tp,
                 linhas=[f"{n_corr} linha(s) por vao, nas duas aguas",
                         "com tirante de cumeeira em V"])
    iv = vaos_x[-1]
    _chamada(d, est, (xs[iv] + xs[iv + 1]) / 2.0, ys_pain[1],
             C + est.off2, V + est.off3 * 1.2, f"ESCORA  {PADRAO_ESCORA}", est.tp,
             linhas=["nos nos do X"])
    _chamada(d, est, C * 0.80, 0.0, C * 0.74, -est.off3 * 1.3, "BEIRAL / CALHA", est.tp)

    # ---------------- cotas ----------------
    _cadeia_h(d, est, xs, 0.0, -est.off)
    _cota_h(d, est, 0.0, C, 0.0, -est.off2 - est.off, _mm(C))
    # espaçamento das terças, na lateral esquerda (meia água, projeção horizontal)
    _cota_v(d, est, 0.0, meia[0], 0.0, -est.off, _mm(meia[0]), est.tp)
    _cota_v(d, est, meia[0], meia[-1], 0.0, -est.off,
            f"{n_vao_terca} x {_mm(passo)} = {_mm(meia[-1] - meia[0])}")
    if y_cum - meia[-1] > 1.0:
        _cota_v(d, est, meia[-1], y_cum, 0.0, -est.off, _mm(y_cum - meia[-1]), est.tp)
    _cota_v(d, est, 0.0, V, 0.0, -est.off2 - est.off, f"{_mm(V)}  (VAO)")

    # ---------------- rótulo e notas ----------------
    y_tit = -est.off3 - est.off - est.tt * 2.6
    _titulo_vista(d, est, C / 2.0, y_tit, "PLANTA DE COBERTURA", est.texto_escala())
    _notas(d, est, 0.0, y_tit - est.tt * 2.2, [
        "Cotas em milimetros.",
        f"{g.n_porticos} porticos (P1 a P{g.n_porticos}) a cada {_mm(g.esp_port)} mm.",
        f"{len(ys_terca)} linhas de terca {g.terca.nome} a cada {_mm(esp_incl)} mm "
        "(na inclinacao).",
        f"Contraventamento de cobertura em X nos vaos {_lista_vaos(vaos_x)} (CC).",
        (f"{n_corr} linha(s) de corrente por vao, com tirante de cumeeira em V."
         if n_corr else "Sem correntes: dispensadas no calculo da terca."),
        f"Escoras {PADRAO_ESCORA} adotadas no detalhamento; nao constam do calculo.",
    ])
    return d


# =====================================================================================
# 3. Elevação longitudinal
# =====================================================================================

def elevacao_longitudinal(projeto) -> Desenho:
    """Elevação da parede lateral (Cap. 16, Figura 16.3).

    Pilares dos pórticos, viga de beiral, longarinas de fechamento e contraventamento
    vertical em X nos vãos extremos e no central. A linha de cumeeira aparece tracejada
    (está além do plano do desenho).
    """
    g = _Geo(projeto)
    est = Estilo(200.0)
    d = Desenho("elevacao-longitudinal")

    C, H = g.comprimento, g.H
    xs = [i * g.esp_port for i in range(g.n_porticos)]
    if xs and abs(xs[-1] - C) > 1.0:
        xs[-1] = C
    bfp = g.pilar.bf

    # ---------------- pilares (vistos pela mesa) ----------------
    for i, x in enumerate(xs):
        d.retangulo(x - bfp / 2, 0.0, bfp, H, "ACO")
        _eixo(d, x, -est.off, x, H + est.off * 1.2)
        d.texto(x, H + est.off * 1.8, f"P{i + 1}", est.t, "TEXTO", alinhamento="centro")

    # ---------------- viga de beiral e cumeeira ----------------
    # na tesoura o beiral fica acima do topo do pilar: a linha do banzo inferior é a do
    # pé-direito e a terça de beiral corre na altura do banzo superior
    if g.trelicado and g.h_beiral > H + 1.0:
        d.linha(0.0, H, C, H, "ACO-FINO")
        d.texto(C * 0.5, H - est.tp * 1.4, "BANZO INFERIOR DA TESOURA", est.tp,
                "TEXTO", alinhamento="centro")
    d.linha(0.0, g.h_beiral, C, g.h_beiral, "ACO")
    d.retangulo(0.0, g.h_beiral, C, g.terca.d, "ACO-FINO")
    d.linha(0.0, g.h_cumeeira, C, g.h_cumeeira, "OCULTA")
    d.texto(C * 0.5, g.h_cumeeira + est.tp * 0.6, "CUMEEIRA (ALEM)", est.tp, "TEXTO",
            alinhamento="centro")

    # ---------------- longarinas ----------------
    # fiadas a cada 1,9 m a partir do piso, parando a 300 mm abaixo do beiral
    # (Cap. 16, passo 1: 1,90 / 3,80 / 5,70 m para pé-direito de 6 m)
    ys_long, passo_l = _fiadas_longarina(g)
    n_long = len(ys_long)
    dl = g.longarina.d
    for yl in ys_long:
        d.linha(0.0, yl, C, yl, "ACO-FINO")
        d.linha(0.0, yl + dl, C, yl + dl, "ACO-FINO")

    # ---------------- contraventamento vertical em X ----------------
    n_vaos = len(xs) - 1
    vaos_x = _vaos_contrav(g, "Contraventamento vertical", n_vaos)
    cv = _perfil(g.perfis["contrav_vertical"])
    tir_v = _eh_tirante(cv)
    for iv in vaos_x:
        x1, x2 = xs[iv], xs[iv + 1]
        d.linha(x1 + bfp / 2, 0.0, x2 - bfp / 2, H, "ACO")
        d.linha(x1 + bfp / 2, H, x2 - bfp / 2, 0.0, "ACO")
        if not tir_v:               # só cantoneira é ligada no cruzamento
            d.circulo((x1 + x2) / 2.0, H / 2.0, 0.010 * C, "AUXILIAR")
        d.texto((x1 + x2) / 2.0, -500.0 - est.off * 0.55, f"CV-{iv + 1}", est.t,
                "TEXTO", alinhamento="centro")

    # ---------------- bases ----------------
    ped_b = bfp + 2 * PADRAO_BASE["pedestal_folga"]
    for x in xs:
        d.retangulo(x - ped_b / 2, -500.0, ped_b, 500.0, "CONCRETO")
        d.hachura([(x - ped_b / 2, -500.0), (x + ped_b / 2, -500.0),
                   (x + ped_b / 2, 0.0), (x - ped_b / 2, 0.0)],
                  espacamento=110.0, angulo=45.0)
    _terreno(d, est, -C * 0.03, C * 1.03, 0.0)

    # ---------------- chamadas ----------------
    iv = vaos_x[0]
    _chamada(d, est, (xs[iv] + xs[iv + 1]) * 0.5 - g.esp_port * 0.2, H * 0.32,
             C * 0.14, -500.0 - est.off2 - est.off,
             "CONTRAVENTAMENTO VERTICAL EM X (CV)", est.tp,
             linhas=([f"TIRANTE %%c{_mm(cv.d, 1)} mm com esticador",
                      "pontas e esticador: DET. 08"] if tir_v else
                     [cv.nome,
                      f"gussets {_mm(PADRAO_CONTRAVENTAMENTO['gusset_esp'], 1)} mm"
                      " - ver DET. 08"]))
    if ys_long:
        _chamada(d, est, C * 0.62, ys_long[len(ys_long) // 2], C * 0.66,
                 g.h_cumeeira + est.off2 * 1.3, f"LONGARINA L1  {g.longarina.nome}",
                 est.tp, linhas=[f"{len(ys_long)} fiadas a cada {_mm(passo_l)} mm"])
    _chamada(d, est, C * 0.30, H + g.terca.d * 0.5, C * 0.22,
             g.h_cumeeira + est.off2 * 1.3, "VIGA DE BEIRAL / ESCORA", est.tp)
    _chamada(d, est, xs[2] if len(xs) > 2 else 0.0, H * 0.55,
             -est.off3, -500.0 - est.off * 0.4, f"PILAR  {g.pilar.nome}", est.tp,
             linhas=[f"{g.pilar.massa:.1f} kg/m".replace(".", ",")])

    # ---------------- cotas ----------------
    _cadeia_h(d, est, xs, -500.0, -est.off)
    _cota_h(d, est, 0.0, C, -500.0, -est.off2 - est.off, _mm(C))
    _cadeia_v(d, est, [0.0] + ys_long + [H], 0.0, -est.off, altura=est.tp)
    _cota_v(d, est, 0.0, H, 0.0, -est.off2 - est.off, _mm(H))
    _cota_v(d, est, 0.0, g.h_cumeeira, C, est.off, _mm(g.h_cumeeira))

    y_tit = -500.0 - est.off3 - est.tt * 3.0
    _titulo_vista(d, est, C / 2.0, y_tit, "ELEVACAO LONGITUDINAL - PAREDE LATERAL",
                  est.texto_escala())
    _notas(d, est, 0.0, y_tit - est.tt * 2.2, [
        "Cotas em milimetros.",
        f"Longarinas {g.longarina.nome} em {len(ys_long)} fiadas.",
        f"Contraventamento vertical em X nos vaos {_lista_vaos(vaos_x)} (CV).",
    ] + ([
        "Tirantes trabalham so a tracao: em cada X atua a diagonal tracionada.",
        "Pre-tracionar pelo esticador apos o prumo; os tirantes nao se ligam no cruzamento.",
    ] if tir_v else [
        "Diagonais ligadas no cruzamento (reduz L de flambagem a metade).",
    ]))
    return d


# =====================================================================================
# 4. Ligação viga–pilar (joelho com chapa de topo)
# =====================================================================================

def _valor(dic: dict, chave: str, fator: float = 1.0) -> Optional[float]:
    """Número finito e positivo de um dicionário, já convertido por `fator`."""
    x = dic.get(chave)
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    if not math.isfinite(x) or x <= 0:
        return None
    return float(x) * fator


def _ligacao_do_resultado(r) -> dict:
    """Traduz `Resultado.dados` de `nucleo.ligacoes.chapa_de_topo` para o desenho.

    **Cuidado com as unidades**: o núcleo trabalha em centímetros e os desenhos em
    milímetros, então a conversão é feita chave a chave. Nada é copiado às cegas — uma
    chave com o mesmo nome e outra unidade estragaria o desenho em silêncio.

    Chaves lidas (todas em cm, como as devolve o núcleo): `t_chapa`, `largura_chapa`,
    `gabarito`, `d_furo`; e `diametro` (nome comercial do parafuso, ex.: `'3/4"'`).
    """
    v: Dict[str, float] = {}
    dd = getattr(r, "dados", None)
    if not isinstance(dd, dict):
        return v
    for chave_cm, alvo in (("t_chapa", "chapa_esp"), ("largura_chapa", "chapa_larg"),
                           ("gabarito", "gabarito")):
        x = _valor(dd, chave_cm, 10.0)
        if x is not None:
            v[alvo] = x
    nome_d = dd.get("diametro")
    d_mm = None
    if isinstance(nome_d, str):
        try:
            from nucleo import materiais as _mat
            d_mm = _mat.diametro(nome_d)[0] * 10.0
        except Exception:
            d_mm = None
    if d_mm is None:
        d_mm = _valor(dd, "d", 10.0)
    if d_mm:
        v["d_parafuso"] = d_mm
        d_furo = _valor(dd, "d_furo", 10.0)
        if d_furo and d_furo > d_mm:
            v["folga_furo"] = d_furo - d_mm
    if isinstance(dd.get("parafuso"), str):
        v["classe_parafuso"] = dd["parafuso"].replace("ASTM ", "")
    return v


def _dados_ligacao(fonte, chave: str, padrao: dict) -> dict:
    """Junta os padrões com o que o projeto trouxer em `ligacoes[chave].dados`."""
    v = dict(padrao)
    if isinstance(fonte, ProjetoGalpao):
        g = _Geo(fonte)
        v.update(dict(perfil_pilar=g.pilar.nome, perfil_viga=g.viga.nome,
                      inclinacao=fonte.dados.inclinacao,
                      com_misula=g.com_misula,
                      comprimento_misula=g.L_misula, altura_misula=g.h_misula))
        v.update(_ligacao_do_resultado(fonte.ligacoes.get(chave)))
    elif isinstance(fonte, dict):
        v.update(fonte)
    elif isinstance(fonte, DadosGalpao):
        g = _Geo(fonte)
        v.update(dict(perfil_pilar=g.pilar.nome, perfil_viga=g.viga.nome,
                      inclinacao=fonte.inclinacao, com_misula=g.com_misula,
                      comprimento_misula=g.L_misula, altura_misula=g.h_misula))
    return v


def _linhas_parafusos(y_topo_mesa, tf_sup, y_base_mesa, tf_inf, borda):
    """Alturas das 4 fileiras de parafusos de uma chapa de topo estendida.

    Uma fileira fora e uma dentro de cada mesa, a `borda` da face da mesa
    (Cap. 16, Figura 16.9).
    """
    return [y_topo_mesa + borda,
            y_topo_mesa - tf_sup - borda,
            y_base_mesa + tf_inf + borda,
            y_base_mesa - borda]


def ligacao_viga_pilar(dados) -> Desenho:
    """Detalhe da ligação de joelho com chapa de topo estendida (Cap. 16, passo 7).

    Vista de elevação (pilar, mísula, chapa de topo, parafusos com gabaritos cotados e
    enrijecedores do pilar) e vista da chapa com a disposição dos furos.

    Chaves aceitas em `dados` (mm, exceto onde indicado): `perfil_pilar`, `perfil_viga`,
    `com_misula`, `comprimento_misula`, `altura_misula`, `inclinacao` (%), `chapa_esp`,
    `chapa_larg`, `d_parafuso`, `gabarito`, `borda_mesa`, `borda_chapa`, `folga_furo`,
    `enrijecedor_esp`, `perna_solda_alma`, `perna_solda_mesa`.
    """
    v = _dados_ligacao(dados, "viga-pilar", PADRAO_LIGACAO)
    if "perfil_pilar" not in v or "perfil_viga" not in v:
        g = _Geo(dados if not isinstance(dados, dict) else dados)
        v.setdefault("perfil_pilar", g.pilar.nome)
        v.setdefault("perfil_viga", g.viga.nome)
        v.setdefault("com_misula", g.com_misula)
        v.setdefault("comprimento_misula", g.L_misula)
        v.setdefault("altura_misula", g.h_misula)
        v.setdefault("inclinacao", g.dg.inclinacao)

    pil = _perfil(v["perfil_pilar"])
    vig = _perfil(v["perfil_viga"])
    incl = float(v.get("inclinacao", 10.0)) / 100.0
    theta = math.atan(incl)
    com_mis = bool(v.get("com_misula", True))
    Lm = float(v.get("comprimento_misula", 1800.0)) if com_mis else 0.0
    hm = float(v.get("altura_misula", 0.0)) or (vig.d if com_mis else 0.0)
    if not com_mis:
        hm = 0.0

    tch = float(v["chapa_esp"])
    dpar = float(v["d_parafuso"])
    dfuro = dpar + float(v["folga_furo"])
    gab = float(v["gabarito"])
    bm = float(v["borda_mesa"])
    bc = float(v["borda_chapa"])
    ench = float(v["enrijecedor_esp"])
    bch = float(v.get("chapa_larg", 0.0)) or max(vig.bf + 30.0, gab + 100.0)

    est = Estilo(10.0)
    d = Desenho("ligacao-viga-pilar")

    # ---------- geometria da elevação ----------
    # origem: face interna da mesa do pilar (x = 0), topo da mesa superior da viga (y = 0)
    dpil, tfp, twp = pil.d, pil.tf, pil.tw
    x_face = 0.0                      # face da mesa interna do pilar
    x_ch = x_face + tch               # face de trás da chapa = início da viga
    D_tot = vig.d + hm                # altura total na raiz da mísula (vertical)
    y_top = 0.0
    y_bot = -D_tot

    # pilar
    y_pil_top = y_top + bc + 2.2 * est.off
    y_pil_bot = y_bot - bc - 3.2 * est.off
    d.polilinha([(x_face - dpil, y_pil_bot), (x_face, y_pil_bot),
                 (x_face, y_pil_top), (x_face - dpil, y_pil_top)],
                fechada=True, camada="ACO")
    d.linha(x_face - tfp, y_pil_bot, x_face - tfp, y_pil_top, "ACO")
    d.linha(x_face - dpil + tfp, y_pil_bot, x_face - dpil + tfp, y_pil_top, "ACO")
    _eixo(d, x_face - dpil / 2, y_pil_bot - est.off, x_face - dpil / 2, y_pil_top + est.off)

    # chapa de topo
    y_ch_top = y_top + bm + bc
    y_ch_bot = y_bot - bm - bc
    d.retangulo(x_face, y_ch_bot, tch, y_ch_top - y_ch_bot, "ACO")
    d.hachura([(x_face, y_ch_bot), (x_face + tch, y_ch_bot),
               (x_face + tch, y_ch_top), (x_face, y_ch_top)],
              espacamento=9.0, angulo=45.0)

    # viga inclinada, a partir da chapa
    Lv = max(Lm + 320.0, 950.0)
    ux, uy = math.cos(theta), math.sin(theta)
    dv_vert = vig.d                                   # corte vertical junto à chapa
    p_top = (x_ch, y_top)
    p_top2 = (x_ch + Lv, y_top + Lv * incl)
    d.linha(p_top[0], p_top[1], p_top2[0], p_top2[1], "ACO")
    d.linha(x_ch, y_top - vig.tf, x_ch + Lv, y_top - vig.tf + Lv * incl, "ACO")
    y_alma_inf = y_top - dv_vert + vig.tf
    d.linha(x_ch, y_top - dv_vert, x_ch + Lv, y_top - dv_vert + Lv * incl, "ACO")
    d.linha(x_ch, y_alma_inf, x_ch + Lv, y_alma_inf + Lv * incl, "ACO")
    # linha de ruptura no fim do trecho desenhado
    d.linha(x_ch + Lv, y_top + Lv * incl + 30.0,
            x_ch + Lv, y_top - D_tot + Lv * incl - 30.0, "ACO-FINO")

    # mísula
    if com_mis and Lm > 0:
        x_fim = x_ch + Lm * ux
        y_fim = y_top - dv_vert + Lm * incl
        d.polilinha([(x_ch, y_top - dv_vert), (x_fim, y_fim), (x_ch, y_bot)],
                    fechada=True, camada="ACO")
        # mesa inferior da mísula
        nx, ny = -math.sin(math.atan2(y_fim - y_bot, x_fim - x_ch)), \
                 math.cos(math.atan2(y_fim - y_bot, x_fim - x_ch))
        tfm = vig.tf
        d.linha(x_ch + nx * tfm, y_bot + ny * tfm, x_fim + nx * tfm, y_fim + ny * tfm,
                "ACO-FINO")
        # enrijecedor obrigatório no fim da mísula (Cap. 14.3.3)
        d.linha(x_fim, y_fim, x_fim, y_top - dv_vert + Lm * incl, "ACO")
        _chamada(d, est, x_fim, (y_fim + y_top - dv_vert + Lm * incl) / 2.0,
                 x_fim + est.off2 * 0.6, y_bot - est.off * 1.2,
                 "ENRIJECEDOR 8 mm NO FIM DA MISULA", est.tp,
                 linhas=["(forca de desvio da mesa inferior)"])

    # enrijecedores do pilar, no nível das mesas da viga e da mísula
    for yy, rot in ((y_top - vig.tf / 2, "sup"), (y_bot + vig.tf / 2, "inf")):
        d.retangulo(x_face - dpil + tfp, yy - ench / 2, dpil - 2 * tfp, ench, "ACO")
        d.hachura([(x_face - dpil + tfp, yy - ench / 2), (x_face - tfp, yy - ench / 2),
                   (x_face - tfp, yy + ench / 2), (x_face - dpil + tfp, yy + ench / 2)],
                  espacamento=7.0, angulo=45.0)

    # parafusos (4 fileiras x 2)
    ys_par = _linhas_parafusos(y_top, vig.tf, y_bot, vig.tf, bm)
    for yy in ys_par:
        d.parafuso(x_face + tch / 2, yy, dpar)
        d.linha(x_face - 2.2 * dpar, yy, x_face + tch + 2.2 * dpar, yy, "EIXO")

    # soldas
    _solda(d, est, x_ch + 12.0, y_top - vig.tf / 2, x_ch + Lv * 0.30,
           y_ch_top + est.off * 1.6, 0.0, tipo="penetracao",
           texto="PENETRACAO TOTAL (mesas)")
    _solda(d, est, x_ch + 10.0, y_top - dv_vert * 0.55,
           x_ch + Lv * 0.32, y_top - dv_vert * 1.05,
           float(v["perna_solda_alma"]), tipo="filete", texto="alma, 2 lados")
    if com_mis and Lm > 0:
        _solda(d, est, x_ch + Lm * 0.42, y_top - dv_vert + Lm * 0.42 * incl - 6.0,
               x_ch + Lm * 0.45, y_bot - est.off2 * 1.9,
               float(v["perna_solda_mesa"]) - 2.0, tipo="filete",
               texto="misula-viga, continuo")

    # ---------- cotas da elevação ----------
    # (a distribuição das fileiras de parafusos é cotada na vista da chapa)
    hb = D_tot - vig.tf
    _cota_v(d, est, y_ch_bot, y_ch_top, x_face - dpil, -est.off,
            _mm(y_ch_top - y_ch_bot))
    _cota_v(d, est, y_bot + vig.tf / 2, y_top - vig.tf / 2, x_face - dpil,
            -est.off2 - est.off, f"hb = {_mm(hb)}")
    _cota_h(d, est, x_face, x_face + tch, y_ch_top, est.off, _mm(tch, 1))
    _cota_h(d, est, x_face - dpil, x_face, y_pil_bot, -est.off, _mm(dpil))
    if com_mis and Lm > 0:
        _cota_h(d, est, x_ch, x_ch + Lm * ux, y_bot, -est.off2, f"MISULA {_mm(Lm)}")
        _cota_v(d, est, y_bot, y_top - dv_vert, x_face - dpil,
                -est.off3 - est.off, f"hm = {_mm(hm)}")

    _chamada(d, est, x_face - dpil / 2, y_pil_top - est.off, x_face - dpil - est.off2,
             y_ch_top + est.off * 1.6, f"PILAR  {pil.nome}", est.tp)
    _chamada(d, est, x_ch + Lv * 0.75, y_top - vig.tf + Lv * 0.75 * incl,
             x_ch + Lv * 0.55, y_top + est.off3, f"VIGA  {vig.nome}", est.tp)
    _chamada(d, est, x_face - dpil * 0.55, y_bot + vig.tf / 2,
             x_face - dpil - est.off3 * 1.9, y_bot * 1.15,
             f"ENRIJECEDORES {_mm(ench)} mm", est.tp,
             linhas=["nos dois niveis (o momento inverte)"])
    _titulo_vista(d, est, x_face - dpil / 2 + Lv * 0.3, y_pil_bot - est.off2,
                  "ELEVACAO", est.texto_escala())

    # ---------- vista da chapa ----------
    x0 = x_ch + Lv + est.off3 * 1.6 + bch / 2
    d.retangulo(x0 - bch / 2, y_ch_bot, bch, y_ch_top - y_ch_bot, "ACO")
    _eixo(d, x0, y_ch_bot - est.off, x0, y_ch_top + est.off)
    # contorno da viga/mísula por trás da chapa
    d.linha(x0 - vig.bf / 2, y_ch_bot, x0 - vig.bf / 2, y_ch_top, "OCULTA")
    d.linha(x0 + vig.bf / 2, y_ch_bot, x0 + vig.bf / 2, y_ch_top, "OCULTA")
    d.linha(x0 - vig.bf / 2, y_top, x0 + vig.bf / 2, y_top, "OCULTA")
    d.linha(x0 - vig.bf / 2, y_top - vig.tf, x0 + vig.bf / 2, y_top - vig.tf, "OCULTA")
    d.linha(x0 - vig.bf / 2, y_bot, x0 + vig.bf / 2, y_bot, "OCULTA")
    d.linha(x0 - vig.bf / 2, y_bot + vig.tf, x0 + vig.bf / 2, y_bot + vig.tf, "OCULTA")
    d.linha(x0 - vig.tw / 2, y_ch_bot, x0 - vig.tw / 2, y_ch_top, "OCULTA")
    d.linha(x0 + vig.tw / 2, y_ch_bot, x0 + vig.tw / 2, y_ch_top, "OCULTA")
    for yy in ys_par:
        for sx in (-1, 1):
            _furo(d, est, x0 + sx * gab / 2, yy, dfuro)

    _cota_h(d, est, x0 - gab / 2, x0 + gab / 2, y_ch_top, est.off, f"g = {_mm(gab)}")
    _cota_h(d, est, x0 - bch / 2, x0 + bch / 2, y_ch_top, est.off2 + est.off, _mm(bch))
    _cadeia_v(d, est, [y_ch_bot] + sorted(ys_par) + [y_ch_top], x0 + bch / 2,
              est.off, altura=est.tp)
    _cota_v(d, est, y_ch_bot, y_ch_top, x0 + bch / 2, est.off2 + est.off,
            _mm(y_ch_top - y_ch_bot))
    _cota_h(d, est, x0 - bch / 2, x0 - gab / 2, y_ch_bot, -est.off,
            _mm((bch - gab) / 2), est.tp)
    _chamada(d, est, x0 + gab / 2, ys_par[0], x0 + bch / 2 + est.off2,
             y_ch_top + est.off2 * 1.2,
             f"{len(ys_par) * 2} PARAFUSOS %%c{_mm(dpar, 1)} {v['classe_parafuso']}",
             est.tp, linhas=[f"furos %%c{_mm(dfuro)} na chapa e no pilar"])
    _titulo_vista(d, est, x0, y_pil_bot - est.off2,
                  "CHAPA DE TOPO - VISTA", est.texto_escala())
    d.texto(x0, y_ch_bot - est.off2 - est.t,
            f"CH {_mm(bch)} x {_mm(y_ch_top - y_ch_bot)} x {_mm(tch, 1)}",
            est.t, "TEXTO", alinhamento="centro")

    # ---------- notas ----------
    _notas(d, est, x_face - dpil, y_pil_bot - est.off3 * 1.6, [
        "Cotas em milimetros.",
        f"Chapa de topo estendida {_mm(bch)} x {_mm(y_ch_top - y_ch_bot)} x {_mm(tch, 1)} mm.",
        f"{len(ys_par) * 2} parafusos %%c{_mm(dpar, 1)} {v['classe_parafuso']}, furos %%c{_mm(dfuro)} mm.",
        "Soldas das mesas com penetracao total; alma com filete "
        f"{_mm(v['perna_solda_alma'])} mm nos dois lados.",
        "Enrijecedores do pilar no nivel das duas mesas (o momento inverte de sinal).",
        "Faces de contato sem pintura; parafusos protendidos.",
    ])
    return d


# =====================================================================================
# 5. Ligação de cumeeira
# =====================================================================================

def ligacao_cumeeira(dados) -> Desenho:
    """Chapa de topo na cumeeira, com os dois trechos de viga inclinados.

    Cap. 16, passo 8: duas chapas estendidas verticais parafusadas entre si, com as
    extremidades das vigas cortadas no ângulo do telhado.
    """
    v = _dados_ligacao(dados, "cumeeira", PADRAO_LIGACAO)
    if "perfil_viga" not in v:
        g = _Geo(dados)
        v.setdefault("perfil_viga", g.viga.nome)
        v.setdefault("inclinacao", g.dg.inclinacao)
    vig = _perfil(v["perfil_viga"])
    incl = float(v.get("inclinacao", 10.0)) / 100.0
    theta = math.atan(incl)

    tch = float(v["chapa_esp"])
    dpar = float(v["d_parafuso"])
    dfuro = dpar + float(v["folga_furo"])
    gab = float(v["gabarito"])
    bm = float(v["borda_mesa"])
    bc = float(v["borda_chapa"])
    bch = float(v.get("chapa_larg", 0.0)) or max(vig.bf + 30.0, gab + 100.0)

    est = Estilo(10.0)
    d = Desenho("ligacao-cumeeira")

    # altura da viga medida no corte vertical da cumeeira
    D_vert = vig.d / math.cos(theta)
    tf_vert = vig.tf / math.cos(theta)
    y_top = 0.0
    y_bot = -D_vert
    y_ch_top = y_top + bm + bc
    y_ch_bot = y_bot - bm - bc

    Lv = max(850.0, 2.2 * D_vert)
    # ---------- elevação ----------
    for s in (-1, 1):                       # esquerda (sobe) e direita (desce)
        x_ch = s * tch
        # linhas superiores e inferiores da viga (corte vertical na cumeeira)
        for (y0, cam) in ((y_top, "ACO"), (y_top - tf_vert, "ACO"),
                          (y_bot + tf_vert, "ACO"), (y_bot, "ACO")):
            d.linha(x_ch, y0, x_ch + s * Lv, y0 - Lv * incl, cam)
        d.linha(x_ch, y_top, x_ch, y_bot, "ACO")
        d.linha(x_ch + s * Lv, y_top - Lv * incl, x_ch + s * Lv, y_bot - Lv * incl,
                "ACO-FINO")
        # chapa
        x_pl = 0.0 if s > 0 else -tch
        d.retangulo(x_pl, y_ch_bot, tch, y_ch_top - y_ch_bot, "ACO")
        d.hachura([(x_pl, y_ch_bot), (x_pl + tch, y_ch_bot),
                   (x_pl + tch, y_ch_top), (x_pl, y_ch_top)],
                  espacamento=8.0, angulo=45.0 * s)

    _eixo(d, 0.0, y_ch_bot - est.off, 0.0, y_ch_top + est.off)

    ys_par = _linhas_parafusos(y_top, tf_vert, y_bot, tf_vert, bm)
    for yy in ys_par:
        d.parafuso(0.0, yy, dpar)
        d.linha(-2.6 * dpar - tch, yy, 2.6 * dpar + tch, yy, "EIXO")

    # soldas
    _solda(d, est, tch + 14.0, y_top - tf_vert / 2, Lv * 0.34, y_ch_top + est.off,
           0.0, tipo="penetracao", texto="PENETRACAO TOTAL (mesas)")
    _solda(d, est, -tch - 12.0, y_bot * 0.5, -Lv * 0.55, y_ch_bot - est.off * 0.8,
           float(v["perna_solda_alma"]), tipo="filete", texto="alma, 2 lados")

    # cotas
    _cota_v(d, est, y_ch_bot, y_ch_top, -tch, -est.off2, _mm(y_ch_top - y_ch_bot))
    _cota_v(d, est, y_bot + tf_vert / 2, y_top - tf_vert / 2, -tch,
            -est.off3 - est.off, f"hb = {_mm(D_vert - tf_vert)}")
    _cadeia_v(d, est, [y_ch_bot] + sorted(ys_par) + [y_ch_top], tch, est.off,
              altura=est.tp)
    _cota_h(d, est, -tch, tch, y_ch_top, est.off, f"2 x {_mm(tch, 1)}")

    # ângulo do telhado
    xa = Lv * 0.62
    d.linha(xa, y_top - xa * incl, xa + 260.0, y_top - xa * incl, "COTA")
    d.texto(xa + 40.0, y_top - xa * incl + est.tp * 0.5,
            f"{v.get('inclinacao', 10.0):g} %%% ({math.degrees(theta):.1f}%%d)".replace(".", ","),
            est.tp, "COTA")

    _chamada(d, est, -Lv * 0.55, y_top + Lv * 0.55 * incl - tf_vert,
             -Lv * 0.75, y_top + est.off3 * 1.4, f"VIGA  {vig.nome}", est.tp)
    _chamada(d, est, 0.0, ys_par[3], Lv * 0.45, y_ch_bot - est.off * 0.8,
             f"{len(ys_par) * 2} PARAFUSOS %%c{_mm(dpar, 1)} {v['classe_parafuso']}",
             est.tp, linhas=[f"furos %%c{_mm(dfuro)}"])
    _titulo_vista(d, est, 0.0, y_ch_bot - est.off3 - est.tt,
                  "CUMEEIRA - ELEVACAO", est.texto_escala())

    # ---------- vista da chapa ----------
    x0 = Lv + est.off3 * 1.6 + bch / 2
    d.retangulo(x0 - bch / 2, y_ch_bot, bch, y_ch_top - y_ch_bot, "ACO")
    _eixo(d, x0, y_ch_bot - est.off, x0, y_ch_top + est.off)
    for yy in (y_top, y_top - tf_vert, y_bot + tf_vert, y_bot):
        d.linha(x0 - vig.bf / 2, yy, x0 + vig.bf / 2, yy, "OCULTA")
    for sx in (-1, 1):
        d.linha(x0 + sx * vig.bf / 2, y_ch_bot, x0 + sx * vig.bf / 2, y_ch_top, "OCULTA")
        d.linha(x0 + sx * vig.tw / 2, y_ch_bot, x0 + sx * vig.tw / 2, y_ch_top, "OCULTA")
    for yy in ys_par:
        for sx in (-1, 1):
            _furo(d, est, x0 + sx * gab / 2, yy, dfuro)
    _cota_h(d, est, x0 - gab / 2, x0 + gab / 2, y_ch_top, est.off, f"g = {_mm(gab)}")
    _cota_h(d, est, x0 - bch / 2, x0 + bch / 2, y_ch_top, est.off2 + est.off, _mm(bch))
    _cadeia_v(d, est, [y_ch_bot] + sorted(ys_par) + [y_ch_top], x0 + bch / 2,
              est.off, altura=est.tp)
    d.texto(x0, y_ch_bot - est.off2 - est.t,
            f"2 CH {_mm(bch)} x {_mm(y_ch_top - y_ch_bot)} x {_mm(tch, 1)}",
            est.t, "TEXTO", alinhamento="centro")
    _titulo_vista(d, est, x0, y_ch_bot - est.off3 - est.tt, "CHAPA DE TOPO - VISTA",
                  est.texto_escala())

    _notas(d, est, -Lv, y_ch_bot - est.off3 * 2.4, [
        "Cotas em milimetros.",
        "Chapas cortadas no angulo do telhado; faces de contato planas.",
        f"{len(ys_par) * 2} parafusos %%c{_mm(dpar, 1)} {v['classe_parafuso']}.",
        "Mao-francesa obrigatoria na terca de cumeeira, dos dois lados (Cap. 14.1.4).",
    ])
    return d


# =====================================================================================
# 6. Base de pilar
# =====================================================================================

def _base_do_resultado(r) -> dict:
    """Traduz `Resultado.dados` de `nucleo.bases.dimensionar_base` para o desenho.

    O núcleo já publica um sub-dicionário `geometria` em **milímetros** (`B_mm`,
    `L_mm`, `t_mm`, `grout_mm`, `pedestal_mm`, `chumbador_x_mm`, `h_ef_mm`), que é o
    que se usa aqui; as demais chaves do resultado estão em centímetros e não são
    copiadas às cegas.
    """
    v: Dict[str, float] = {}
    dd = getattr(r, "dados", None)
    if not isinstance(dd, dict):
        return v
    geo = dd.get("geometria") if isinstance(dd.get("geometria"), dict) else {}
    for chave_mm, alvo in (("B_mm", "placa_B"), ("L_mm", "placa_L"),
                           ("t_mm", "placa_t"), ("grout_mm", "grout"),
                           ("h_ef_mm", "ancoragem")):
        x = _valor(geo, chave_mm)
        if x is not None:
            v[alvo] = x
    ped = geo.get("pedestal_mm")
    if isinstance(ped, (list, tuple)) and len(ped) == 2 and "placa_B" in v:
        larg = max(float(ped[0]), float(ped[1]))
        if math.isfinite(larg) and larg > v["placa_B"]:
            v["pedestal_folga"] = (larg - v["placa_B"]) / 2.0
    n = dd.get("n_chumbadores")
    if isinstance(n, int) and 1 <= n <= 12:
        v["n_chumbadores"] = n
    furo = _valor(dd, "furo_placa_mm")
    ch = dd.get("chumbadores") if isinstance(dd.get("chumbadores"), dict) else {}
    d_mm = _valor(ch, "d", 10.0)
    if d_mm:
        v["d_chumbador"] = d_mm
        if furo and furo > d_mm:
            v["folga_furo"] = furo - d_mm
    arr = _valor(ch, "arruela_chapa_mm") or _valor(dd, "arruela_chapa_mm")
    if arr:
        v["arruela"] = arr
    x_ch = _valor(geo, "chumbador_x_mm")
    if x_ch and int(v.get("n_chumbadores", 2)) >= 4:
        v["gabarito_L"] = 2.0 * x_ch
    fck = _valor(dd, "fck", 10.0)          # kN/cm² -> MPa
    if fck:
        v["fck_MPa"] = fck
    return v


def base_pilar(dados) -> Desenho:
    """Base do pilar: vista frontal e planta da placa (Cap. 16, passo 9).

    A vista frontal olha a mesa do pilar (perpendicular ao plano do pórtico), que é a
    direção em que os dois chumbadores da base rotulada aparecem separados. A planta
    mostra a placa com o contorno do perfil, os furos e o gabarito.

    Chaves aceitas em `dados` (mm): `perfil_pilar`, `placa_B`, `placa_L`, `placa_t`,
    `d_chumbador`, `n_chumbadores`, `gabarito_B`, `gabarito_L`, `folga_furo`,
    `arruela`, `grout`, `pedestal_altura`, `pedestal_folga`, `ancoragem`, `gancho`,
    `rotulada` (bool).
    """
    v = dict(PADRAO_BASE)
    rotulada = True
    if isinstance(dados, (ProjetoGalpao, DadosGalpao)):
        g = _Geo(dados)
        v["perfil_pilar"] = g.pilar.nome
        rotulada = g.rotulada
        v["fck_MPa"] = g.dg.fck_MPa
        if isinstance(dados, ProjetoGalpao):
            v.update(_base_do_resultado(dados.base))
            if "n_chumbadores" in v:
                rotulada = int(v["n_chumbadores"]) <= 2
    elif isinstance(dados, dict):
        v.update(dados)
        rotulada = bool(v.get("rotulada", v.get("base_rotulada", True)))
    v.setdefault("perfil_pilar", "W 360×44,6")
    if not rotulada and "n_chumbadores" not in (dados if isinstance(dados, dict) else {}):
        v["n_chumbadores"] = 4

    pil = _perfil(v["perfil_pilar"])
    B, L, t = float(v["placa_B"]), float(v["placa_L"]), float(v["placa_t"])
    B = max(B, pil.bf + 80.0)
    L = max(L, pil.d + 40.0)
    dch = float(v["d_chumbador"])
    dfuro = dch + float(v["folga_furo"])
    n_ch = int(v["n_chumbadores"])
    gB = float(v["gabarito_B"]) or (B - 120.0)
    gL = float(v["gabarito_L"]) or (pil.d + 90.0 if n_ch >= 4 else 0.0)
    if n_ch >= 4:                       # a placa tem que conter os chumbadores
        L = max(L, gL + 120.0)
    gB = min(gB, B - 100.0)
    grout = float(v["grout"])
    ped_h = float(v["pedestal_altura"])
    ped_f = float(v["pedestal_folga"])
    anc = float(v["ancoragem"])
    gancho = float(v["gancho"])
    arr = float(v["arruela"])

    est = Estilo(10.0)
    d = Desenho("base-pilar")

    # ================= vista frontal (olhando a mesa do pilar) =================
    # y = 0 no piso acabado; o pedestal sobe `ped_h` acima dele, o grout vem em cima
    # do pedestal e a placa em cima do grout
    y_topo_ped = ped_h
    y_placa = y_topo_ped + grout
    y_top_placa = y_placa + t
    h_pilar = 430.0
    ped_B = B + 2 * ped_f
    y_anc_fim = y_topo_ped - anc          # ponta reta do chumbador
    ped_baixo = y_anc_fim - gancho - 150.0

    # pedestal de concreto
    d.polilinha([(-ped_B / 2, ped_baixo), (ped_B / 2, ped_baixo),
                 (ped_B / 2, y_topo_ped), (-ped_B / 2, y_topo_ped)],
                fechada=True, camada="CONCRETO")
    d.hachura([(-ped_B / 2, ped_baixo), (ped_B / 2, ped_baixo),
               (ped_B / 2, y_topo_ped), (-ped_B / 2, y_topo_ped)],
              espacamento=26.0, angulo=45.0)
    d.hachura([(-ped_B / 2, ped_baixo), (ped_B / 2, ped_baixo),
               (ped_B / 2, y_topo_ped), (-ped_B / 2, y_topo_ped)],
              espacamento=52.0, angulo=135.0)
    # piso acabado, só fora do pedestal
    _terreno(d, est, -ped_B / 2 - 260.0, -ped_B / 2, 0.0)
    _terreno(d, est, ped_B / 2, ped_B / 2 + 260.0, 0.0)

    # grout
    d.retangulo(-B / 2, y_topo_ped, B, grout, "CONCRETO")
    d.hachura([(-B / 2, y_topo_ped), (B / 2, y_topo_ped), (B / 2, y_placa),
               (-B / 2, y_placa)], espacamento=6.0, angulo=135.0)

    # placa de base
    d.retangulo(-B / 2, y_placa, B, t, "ACO")
    d.hachura([(-B / 2, y_placa), (B / 2, y_placa), (B / 2, y_top_placa),
               (-B / 2, y_top_placa)], espacamento=7.0, angulo=45.0)

    # pilar visto pela mesa: largura bf, mesa em primeiro plano, alma tracejada
    d.retangulo(-pil.bf / 2, y_top_placa, pil.bf, h_pilar, "ACO")
    d.linha(-pil.tw / 2, y_top_placa, -pil.tw / 2, y_top_placa + h_pilar, "OCULTA")
    d.linha(pil.tw / 2, y_top_placa, pil.tw / 2, y_top_placa + h_pilar, "OCULTA")
    d.linha(-pil.bf / 2, y_top_placa + h_pilar, pil.bf / 2, y_top_placa + h_pilar,
            "ACO-FINO")
    _eixo(d, 0.0, ped_baixo - est.off, 0.0, y_top_placa + h_pilar + est.off)

    # soldas do pilar à placa
    d.filete_solda(-pil.bf / 2, y_top_placa, 8.0, 0.0, lado=1)
    d.filete_solda(pil.bf / 2, y_top_placa, 8.0, 180.0, lado=-1)
    _solda(d, est, pil.bf / 2 - 6.0, y_top_placa + 6.0,
           pil.bf / 2 + est.off2, y_top_placa + est.off3, 8.0, tipo="filete",
           texto="todo o perimetro", em_volta=True)

    # chumbadores
    xs_ch = [-gB / 2, gB / 2] if n_ch <= 2 else [-gB / 2, gB / 2]
    for xc in xs_ch:
        d.linha(xc - dch / 2, y_top_placa + 60.0, xc - dch / 2, y_anc_fim, "PARAFUSO")
        d.linha(xc + dch / 2, y_top_placa + 60.0, xc + dch / 2, y_anc_fim, "PARAFUSO")
        # gancho
        sg = 1 if xc > 0 else -1
        d.linha(xc - dch / 2, y_anc_fim, xc + sg * gancho, y_anc_fim, "PARAFUSO")
        d.linha(xc + dch / 2, y_anc_fim + dch, xc + sg * gancho, y_anc_fim + dch,
                "PARAFUSO")
        d.arco(xc + sg * gancho, y_anc_fim + dch / 2, dch / 2, 0, 360, "PARAFUSO")
        # arruela quadrada + porca
        d.retangulo(xc - arr / 2, y_top_placa, arr, 8.0, "ACO")
        d.retangulo(xc - dch * 0.85, y_top_placa + 8.0, dch * 1.7, dch * 0.8, "PARAFUSO")
        d.retangulo(xc - dch * 0.85, y_top_placa + 8.0 + dch * 0.8, dch * 1.7, dch * 0.8,
                    "PARAFUSO")
        _eixo(d, xc, y_top_placa + 90.0, xc, y_anc_fim - 40.0)

    # cotas da elevação
    _cota_h(d, est, -B / 2, B / 2, ped_baixo, -est.off, _mm(B))
    _cota_h(d, est, -ped_B / 2, ped_B / 2, ped_baixo, -est.off2 - est.off,
            _mm(ped_B), est.tp)
    _cota_h(d, est, -gB / 2, gB / 2, y_top_placa + h_pilar, est.off,
            f"gabarito {_mm(gB)}")
    _cadeia_v(d, est, [0.0, y_topo_ped, y_placa, y_top_placa], B / 2 + 40.0,
              est.off, textos=[_mm(ped_h), _mm(grout), _mm(t, 1)], altura=est.tp)
    _cota_v(d, est, y_anc_fim, y_topo_ped, -B / 2 - 40.0, -est.off2,
            f"Lanc >= {_mm(anc)}")

    _chamada(d, est, -B / 2 + 20.0, y_placa + t / 2, -ped_B / 2 - est.off3 * 1.1,
             y_top_placa + est.off3 * 1.4,
             f"PLACA DE BASE {_mm(B)} x {_mm(L)} x {_mm(t, 1)}", est.tp,
             linhas=["aco A36"])
    _chamada(d, est, -B / 2 + 60.0, y_topo_ped + grout / 2, -ped_B / 2 - est.off3 * 1.1,
             y_top_placa + est.off2 * 0.9, f"GROUT {_mm(grout)} mm", est.tp,
             linhas=["argamassa de alta resistencia"])
    _chamada(d, est, ped_B / 2 - 40.0, y_anc_fim * 0.85, ped_B / 2 + est.off2,
             y_anc_fim * 1.05, f"PEDESTAL C{v['fck_MPa']:.0f}", est.tp,
             linhas=[f"{_mm(ped_h)} mm acima do piso", "armar com estribos"])
    _chamada(d, est, gB / 2 + dch / 2, y_anc_fim * 0.45, ped_B / 2 + est.off2,
             y_anc_fim * 0.30, f"{n_ch} CHUMBADORES %%c{_mm(dch, 1)}", est.tp,
             linhas=[f"gancho {_mm(gancho)} mm"])
    _chamada(d, est, -gB / 2, y_top_placa + 12.0, -ped_B / 2 - est.off3 * 1.1,
             y_top_placa + est.off2 * 0.2, f"ARRUELA {_mm(arr)}x{_mm(arr)}x8 SOLDADA",
             est.tp, linhas=["porca + contraporca"])

    _titulo_vista(d, est, 0.0, ped_baixo - est.off3 * 1.3,
                  "ELEVACAO  (vista perpendicular ao portico)", est.texto_escala())

    # ================= planta da placa =================
    x0 = ped_B / 2 + est.off3 * 3.2 + B / 2
    y0 = y_top_placa + h_pilar * 0.35
    d.retangulo(x0 - B / 2, y0 - L / 2, B, L, "ACO")
    # contorno do perfil sobre a placa: bf na horizontal (direção B), d na vertical
    for pol in contorno_perfil(pil):
        d.polilinha(_mover(pol, x0, y0), fechada=True, camada="ACO-FINO")
    _eixo(d, x0 - B / 2 - est.off, y0, x0 + B / 2 + est.off, y0)
    _eixo(d, x0, y0 - L / 2 - est.off, x0, y0 + L / 2 + est.off)

    if n_ch <= 2:
        furos = [(-gB / 2, 0.0), (gB / 2, 0.0)]
    else:
        furos = [(sx * gB / 2, sy * gL / 2) for sx in (-1, 1) for sy in (-1, 1)]
    for fx, fy in furos:
        _furo(d, est, x0 + fx, y0 + fy, dfuro)
        d.retangulo(x0 + fx - arr / 2, y0 + fy - arr / 2, arr, arr, "ACO-FINO")

    _cota_h(d, est, x0 - B / 2, x0 + B / 2, y0 + L / 2, est.off2, f"B = {_mm(B)}")
    _cota_h(d, est, x0 - gB / 2, x0 + gB / 2, y0 + L / 2, est.off, _mm(gB))
    _cota_v(d, est, y0 - L / 2, y0 + L / 2, x0 + B / 2, est.off2, f"L = {_mm(L)}")
    if n_ch > 2:
        _cota_v(d, est, y0 - gL / 2, y0 + gL / 2, x0 + B / 2, est.off, _mm(gL))
    else:
        _cota_v(d, est, y0 - L / 2, y0, x0 + B / 2, est.off, _mm(L / 2), est.tp)
    _cota_h(d, est, x0 - B / 2, x0 - gB / 2, y0 - L / 2, -est.off,
            _mm((B - gB) / 2), est.tp)

    _chamada(d, est, x0 + gB / 2, y0 + dfuro / 2, x0 + B / 2 + est.off3,
             y0 + L * 0.42, f"{n_ch} FUROS %%c{_mm(dfuro)}", est.tp,
             linhas=[f"para chumbador %%c{_mm(dch, 1)}", "folga de montagem"])
    _chamada(d, est, x0 + pil.bf * 0.30, y0 + pil.d / 2 - 8.0,
             x0 - B / 2 - est.off3, y0 + L * 0.42, f"PILAR {pil.nome}", est.tp)
    _titulo_vista(d, est, x0, y0 - L / 2 - est.off3 * 1.4, "PLANTA DA PLACA",
                  est.texto_escala())

    # ================= notas =================
    _notas(d, est, -ped_B / 2, ped_baixo - est.off3 * 2.2, [
        "Cotas em milimetros.",
        ("Base rotulada: chumbadores no eixo do pilar, sem braco de alavanca."
         if n_ch <= 2 else
         "Base engastada: chumbadores fora das mesas, com braco de alavanca."),
        f"Placa {_mm(B)} x {_mm(L)} x {_mm(t, 1)} mm em A36; grout de {_mm(grout)} mm.",
        f"Chumbadores %%c{_mm(dch, 1)}, ancoragem >= {_mm(anc)} mm mais gancho de {_mm(gancho)} mm.",
        f"Furos %%c{_mm(dfuro)} mm na placa (folga de montagem) com arruela "
        f"{_mm(arr)}x{_mm(arr)}x8 soldada apos o prumo.",
        "Nivelar a placa com porcas antes do grout; conferir prumo e cota de topo.",
    ])
    return d


# =====================================================================================
# 7. Detalhe da terça
# =====================================================================================

def detalhe_terca(dados) -> Desenho:
    """Apoio da terça Ue sobre a viga do pórtico (Cap. 14, Figuras 14.1 e 14.2).

    Três vistas: corte perpendicular ao eixo da terça (chapa de terça soldada à mesa
    da viga, terça parafusada pela alma), vista lateral ao longo da terça (furos
    oblongos e folga entre terças) e o detalhe do tirante/corrente com esticador.

    Chaves aceitas em `dados` (mm): `perfil_terca`, `perfil_viga`, `tipo_chapa`,
    `chapa_esp`, `d_parafuso`, `n_parafusos`, `gabarito_parafusos`, `folga_terca`,
    `d_corrente`, `perna_solda`.
    """
    v = dict(PADRAO_TERCA_DET)
    if isinstance(dados, (ProjetoGalpao, DadosGalpao)):
        g = _Geo(dados)
        v["perfil_terca"] = g.terca.nome
        v["perfil_viga"] = g.viga.nome
    elif isinstance(dados, dict):
        v.update(dados)
    v.setdefault("perfil_terca", PADRAO_TERCA)
    v.setdefault("perfil_viga", "W 360×32,9")

    ter = _perfil(v["perfil_terca"])
    vig = _perfil(v["perfil_viga"])
    gt = _dims_perfil(ter)
    ht, bt, tt_ = gt["h"], gt["b"], gt["tw"]
    tch = float(v["chapa_esp"])
    dpar = float(v["d_parafuso"])
    npar = int(v["n_parafusos"])
    gpar = float(v["gabarito_parafusos"])
    folga = float(v["folga_terca"])
    dcor = float(v["d_corrente"])
    perna = float(v["perna_solda"])

    h_ch = 0.75 * ht                      # 0,7 a 0,8 da altura da terça (Cap. 14.1.1)
    b_ch = max(60.0, 0.75 * vig.bf)       # aba soldada na mesa: bf/2 a bf
    dfuro = dpar + 2.0                    # furo na terça: d + 2
    obl_l, obl_h = dpar + 2.0, dpar + 10.0  # oblongo na chapa (Cap. 14.1.1)

    est = Estilo(5.0)
    d = Desenho("detalhe-terca")

    # ---------------- VISTA A: corte perpendicular ao eixo da terca ----------------
    # a viga aparece em vista longitudinal: ve-se a mesa superior e um trecho da alma
    Lv = 2.4 * vig.bf
    y_mesa = 0.0
    y_quebra = y_mesa - vig.d * 0.45
    d.linha(-Lv / 2, y_mesa, Lv / 2, y_mesa, "ACO")
    d.linha(-Lv / 2, y_mesa - vig.tf, Lv / 2, y_mesa - vig.tf, "ACO")
    d.linha(-Lv / 2, y_mesa - vig.tf, -Lv / 2, y_mesa, "ACO")
    d.linha(Lv / 2, y_mesa - vig.tf, Lv / 2, y_mesa, "ACO")
    for sx in (-1, 1):
        d.linha(sx * vig.tw / 2, y_mesa - vig.tf, sx * vig.tw / 2, y_quebra, "ACO")
    d.polilinha([(-vig.tw, y_quebra + 6.0), (-vig.tw * 0.3, y_quebra - 6.0),
                 (vig.tw * 0.3, y_quebra + 6.0), (vig.tw, y_quebra - 6.0)],
                camada="ACO-FINO")

    # chapa de terca dobrada: aba horizontal soldada na mesa + aba vertical
    # a aba horizontal sai para o lado oposto ao da terça, que assenta direto na
    # mesa da viga (Cap. 14.1.1)
    x_ch = -tch / 2
    perfil_ch = [(-b_ch, y_mesa), (x_ch + tch, y_mesa), (x_ch + tch, y_mesa + h_ch),
                 (x_ch, y_mesa + h_ch), (x_ch, y_mesa + tch), (-b_ch, y_mesa + tch)]
    d.polilinha(perfil_ch, fechada=True, camada="ACO")
    d.hachura(perfil_ch, espacamento=3.0, angulo=45.0)

    # terca Ue em secao, alma encostada na aba vertical da chapa
    x_ter = x_ch + tch + bt / 2
    y_ter = y_mesa + ht / 2
    _desenhar_secao(d, ter, x_ter, y_ter, corte=True)

    # parafusos na alma da terca
    y_p0 = y_mesa + h_ch * 0.32
    y_p1 = y_mesa + h_ch * 0.76
    for yy in (y_p0, y_p1):
        d.parafuso(x_ch + tch / 2, yy, dpar)
        d.linha(x_ch - 2.6 * dpar, yy, x_ch + tch + 2.6 * dpar, yy, "EIXO")

    _solda(d, est, -b_ch * 0.55, y_mesa + tch / 2, b_ch * 0.9 + est.off2,
           y_mesa - est.off2 * 0.9, perna, tipo="filete", texto="2 lados, na mesa")

    _cota_v(d, est, y_mesa, y_mesa + h_ch, -b_ch, -est.off,
            f"hch = {_mm(h_ch)}")
    _cota_v(d, est, y_mesa, y_mesa + ht, x_ter + bt / 2, est.off, _mm(ht))
    _cota_h(d, est, -b_ch, x_ch + tch, y_mesa - vig.tf, -est.off,
            _mm(b_ch + tch / 2))
    _cadeia_v(d, est, [y_mesa, y_p0, y_p1], x_ch + tch, est.off2, altura=est.tp)
    _chamada(d, est, x_ch + tch / 2, y_p1, -b_ch - est.off2, y_mesa + ht * 1.55,
             f"{npar} PARAFUSOS %%c{_mm(dpar, 1)}", est.tp,
             linhas=["A307 ou A325"])
    _chamada(d, est, x_ch, y_mesa + h_ch * 0.52, -b_ch - est.off2,
             y_mesa + ht * 1.15, f"CHAPA DOBRADA t = {_mm(tch, 2)}", est.tp)
    _chamada(d, est, x_ter + bt * 0.35, y_ter + ht * 0.30,
             x_ter + bt / 2 + est.off, y_mesa + ht * 1.75,
             f"TERCA  {ter.nome}", est.tp)
    _chamada(d, est, -Lv * 0.40, y_mesa - vig.tf / 2, -b_ch - est.off2,
             y_mesa - est.off2 * 0.3, "VIGA DO PORTICO", est.tp, linhas=[vig.nome])
    y_tit = y_quebra - est.off3 * 1.2
    _titulo_vista(d, est, 0.0, y_tit, "VISTA A - CORTE PERPENDICULAR A TERCA",
                  est.texto_escala())

    # ---------------- VISTA B: ao longo da terca ----------------
    Lb = 2.4 * ht
    larg_ch = gpar + 80.0
    x0 = Lv / 2 + est.off3 * 1.8 + Lb / 2
    d.linha(x0 - Lb / 2 - folga, y_mesa, x0 + Lb / 2 + folga, y_mesa, "ACO")
    d.linha(x0 - Lb / 2 - folga, y_mesa - vig.tf, x0 + Lb / 2 + folga,
            y_mesa - vig.tf, "ACO")
    d.retangulo(x0 - larg_ch / 2, y_mesa, larg_ch, h_ch, "ACO")

    for s_ in (-1, 1):
        xa = x0 + s_ * folga / 2
        xb = x0 + s_ * (folga / 2 + Lb / 2)
        d.linha(xa, y_mesa, xb, y_mesa, "ACO")
        d.linha(xa, y_mesa + ht, xb, y_mesa + ht, "ACO")
        d.linha(xa, y_mesa, xa, y_mesa + ht, "ACO")
        d.linha(xa, y_mesa + tt_, xb, y_mesa + tt_, "ACO-FINO")
        d.linha(xa, y_mesa + ht - tt_, xb, y_mesa + ht - tt_, "ACO-FINO")

    for s_ in (-1, 1):
        xf = x0 + s_ * gpar / 2
        _oblongo(d, xf, y_mesa + h_ch * 0.54, obl_h, obl_l)
        d.parafuso(xf, y_mesa + h_ch * 0.54, dpar)

    _cota_h(d, est, x0 - gpar / 2, x0 + gpar / 2, y_mesa + h_ch, est.off, _mm(gpar))
    _cota_h(d, est, x0 - folga / 2, x0 + folga / 2, y_mesa + ht, est.off2,
            f"folga {_mm(folga)}")
    _cota_h(d, est, x0 - larg_ch / 2, x0 + larg_ch / 2, y_mesa - vig.tf, -est.off,
            _mm(larg_ch))
    _chamada(d, est, x0 + gpar / 2, y_mesa + h_ch * 0.54 + obl_l / 2,
             x0 + Lb * 0.50, y_mesa + ht * 1.15,
             f"FURO OBLONGO {_mm(obl_h)} x {_mm(obl_l)}", est.tp,
             linhas=["na chapa, nunca na terca"])
    _chamada(d, est, x0 - Lb * 0.35, y_mesa + ht * 0.5, x0 - Lb * 0.62,
             y_mesa - est.off2 * 0.3, "TERCAS SIMPLESMENTE APOIADAS", est.tp)
    _titulo_vista(d, est, x0, y_tit, "VISTA B - AO LONGO DA TERCA", est.texto_escala())

    # ---------------- VISTA C: corrente com esticador ----------------
    Lc = 3.2 * ht
    x1 = x0 + Lb / 2 + est.off3 * 1.8 + bt / 2
    y_cor = y_mesa + ht * (2.0 / 3.0)          # a h/3 do topo (Cap. 14.1.2)
    for xx in (x1, x1 + Lc):
        _desenhar_secao(d, ter, xx, y_mesa + ht / 2, corte=True)
        _furo(d, est, xx - bt / 2 + tt_ / 2, y_cor, dcor + 2.0, eixos=False)
    for sy in (-1, 1):
        d.linha(x1, y_cor + sy * dcor / 2, x1 + Lc, y_cor + sy * dcor / 2, "ACO")
    xm1, xm2 = x1 + Lc * 0.38, x1 + Lc * 0.62
    d.polilinha([(xm1, y_cor - dcor * 1.4), (xm1 + dcor, y_cor - dcor * 1.9),
                 (xm2 - dcor, y_cor - dcor * 1.9), (xm2, y_cor - dcor * 1.4),
                 (xm2, y_cor + dcor * 1.4), (xm2 - dcor, y_cor + dcor * 1.9),
                 (xm1 + dcor, y_cor + dcor * 1.9), (xm1, y_cor + dcor * 1.4)],
                fechada=True, camada="ACO")
    d.linha(xm1, y_cor + dcor / 2, xm2, y_cor + dcor / 2, "OCULTA")
    d.linha(xm1, y_cor - dcor / 2, xm2, y_cor - dcor / 2, "OCULTA")
    for xx, s_ in ((x1 - bt / 2 + tt_ / 2, 1), (x1 + Lc - bt / 2 + tt_ / 2, -1)):
        for k in (1, 2):
            d.retangulo(xx + s_ * k * dcor * 0.95 - dcor * 0.4, y_cor - dcor * 0.85,
                        dcor * 0.8, dcor * 1.7, "PARAFUSO")

    _cota_v(d, est, y_cor, y_mesa + ht, x1 + bt / 2, est.off,
            f"h/3 = {_mm(ht / 3.0)}", est.tp)
    _cota_h(d, est, x1, x1 + Lc, y_mesa, -est.off2, "VAO ENTRE TERCAS")
    _chamada(d, est, (xm1 + xm2) / 2.0, y_cor + dcor * 1.9, x1 + Lc * 0.40,
             y_mesa + ht * 1.15, f"ESTICADOR (TENSOR) %%c{_mm(dcor, 1)}", est.tp,
             linhas=["classe >= a da barra"])
    _chamada(d, est, x1 + dcor * 1.2, y_cor - dcor * 0.85, x1 - est.off2,
             y_mesa - est.off2 * 0.3, "PORCA + CONTRAPORCA", est.tp)
    _chamada(d, est, x1 + Lc * 0.16, y_cor + dcor / 2, x1 - est.off,
             y_mesa + ht * 1.75, f"CORRENTE %%c{_mm(dcor, 1)}", est.tp,
             linhas=[f"furo %%c{_mm(dcor + 2)} na alma"])
    _titulo_vista(d, est, x1 + Lc / 2, y_tit, "VISTA C - CORRENTE COM ESTICADOR",
                  est.texto_escala())

    _notas(d, est, -Lv / 2, y_tit - est.tt * 3.4, [
        "Cotas em milimetros.",
        f"Chapa de terca t = {_mm(tch, 2)} mm, altura {_mm(h_ch)} mm "
        "(0,7 a 0,8 da altura da terca).",
        f"Solda de filete {_mm(perna)} mm nos dois lados, na mesa da viga.",
        f"Furos oblongos apenas na chapa; na terca, furo redondo %%c{_mm(dfuro)} mm.",
        "Nunca soldar a terca na viga em campo (queima a galvanizacao).",
        f"Corrente %%c{_mm(dcor, 1)} no terco superior da alma, sempre com esticador.",
    ])
    return d


# =====================================================================================
# 8. Nó de contraventamento
# =====================================================================================

def detalhe_contraventamento(dados) -> Desenho:
    """Nó do contraventamento de cobertura (Cap. 14.2 e Cap. 16, passo 10).

    Desenha a solução que o cálculo adotou para as diagonais do X de cobertura:

    * **tirante redondo** ("Barra redonda ø N mm", a solução de `nucleo/galpao.py`):
      chapa gusset soldada à mesa, uma orelha perpendicular a cada tirante, ponta
      rosqueada com arruela, porca e contraporca, e esticador no meio da diagonal;
    * **cantoneira** (perfil L): diagonais parafusadas na chapa gusset.

    Nos dois casos os eixos concorrem no **ponto de trabalho** (PT), sobre o eixo da mesa.

    Chaves aceitas em `dados` (mm): `perfil_viga`, `perfil_diagonal`, `perfil_escora`,
    `perfil_vertical`, `gusset_esp`, `angulo` (graus), `perna_solda`; para cantoneira
    `d_parafuso`, `n_parafusos`, `gabarito`, `borda`; para tirante `orelha_esp`,
    `folga_furo_tirante`, `esticador_comp`, `ajuste_rosca`.
    """
    v = dict(PADRAO_CONTRAVENTAMENTO)
    if isinstance(dados, (ProjetoGalpao, DadosGalpao)):
        g = _Geo(dados)
        v["perfil_viga"] = g.viga.nome
        v["perfil_diagonal"] = g.perfis["contrav_cobertura"]
        v["perfil_vertical"] = g.perfis["contrav_vertical"]
        v["perfil_escora"] = g.perfis["escora"]
        # a diagonal vence o espaçamento entre pórticos e a largura do painel
        largura_painel = g.vao / _paineis_contrav(g, g.vao)
        v["angulo"] = math.degrees(math.atan2(g.esp_port, max(largura_painel, 1.0)))
    elif isinstance(dados, dict):
        v.update(dados)
    v.setdefault("perfil_viga", "W 360×32,9")
    v.setdefault("perfil_diagonal", PADRAO_CONTRAV_COBERTURA)
    v.setdefault("perfil_escora", PADRAO_ESCORA)
    dia = _perfil(v["perfil_diagonal"])
    if _eh_tirante(dia):
        return _no_tirante(v, dia)
    return _no_cantoneira(v)


def _no_tirante(v: dict, dia: Perfil) -> Desenho:
    """Nó do X de cobertura em tirante redondo (Cap. 14.2.1a).

    Planta do nó, corte ao longo de um tirante (orelha, furo, rosca, arruela, porca e
    contraporca) e o esticador no meio da diagonal. A orelha fica perpendicular ao
    tirante e do lado da diagonal, de modo que a porca trabalhe à compressão contra ela
    e as pontas dos dois tirantes não se cruzem no PT.
    """
    vig = _perfil(v["perfil_viga"])
    esc_p = _perfil(v["perfil_escora"])
    db = float(dia.d)
    rosca = _rosca(db)
    folga = float(v["folga_furo_tirante"])
    dfuro = db + folga
    tg = float(v["gusset_esp"])
    to = float(v["orelha_esp"])
    perna = float(v["perna_solda"])
    alfa = math.radians(float(v["angulo"]))
    ca, sa = math.cos(alfa), math.sin(alfa)

    # peças normalizadas em proporções usuais, só para o desenho (porca ISO 4032,
    # arruela ISO 7089); as medidas de compra vêm do fornecedor
    m_p = 0.85 * db                          # altura da porca
    s_p = 1.5 * db                           # abertura da chave
    t_ar = max(3.0, 0.15 * db)               # espessura da arruela
    d_ar = 1.85 * db                         # diâmetro da arruela
    borda = max(1.5 * dfuro, 25.0)           # borda do furo na orelha
    w_o = 2.0 * borda                        # largura da orelha
    e_f = max(borda, db / 2.0 + 15.0)        # centro do furo acima da chapa gusset
    h_o = e_f + borda                        # altura da orelha
    L_est = float(v["esticador_comp"]) or max(150.0, 8.0 * db)
    ajuste = float(v["ajuste_rosca"])
    pilha = t_ar + 2.0 * m_p + 0.3 * db      # arruela + porca + contraporca + 2 fios
    L_rosca = math.ceil((pilha + to + ajuste) / 5.0) * 5.0

    est = Estilo(5.0)
    d = Desenho("detalhe-contraventamento")
    d.escala_sugerida = est.texto_escala()

    bf = vig.bf
    # orelha longe o bastante do PT para caber inteira na chapa gusset, abaixo da
    # mesa, e para as pontas rosqueadas dos dois tirantes não se encontrarem
    a = (bf / 2 + 15.0 + (w_o / 2) * ca + (to / 2) * sa) / sa
    a = max(a, to / 2 + pilha + s_p / max(ca, 0.2))
    a = math.ceil(a / 10.0) * 10.0
    r_tip = a - to / 2 - pilha
    Ld = a + 2.2 * bf                        # trecho de tirante desenhado

    diag = [(-ca, -sa), (ca, -sa)]           # D1 à esquerda, D2 à direita

    def P(u, r, o=0.0):
        """Ponto a `r` do PT ao longo de `u`, afastado `o` para a esquerda do eixo."""
        return (u[0] * r - u[1] * o, u[1] * r + u[0] * o)

    def ret(u, r0, r1, o0, o1):
        return [P(u, r0, o0), P(u, r1, o0), P(u, r1, o1), P(u, r0, o1)]

    def quebra(p0, p1):
        """Linha de ruptura em zigue-zague entre dois pontos."""
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        dx, dy = (p1[0] - p0[0]) / 6, (p1[1] - p0[1]) / 6
        d.polilinha([p0, (mx - dx - dy, my - dy + dx), (mx + dx + dy, my + dy - dx), p1],
                    camada="ACO-FINO")

    # ================= PLANTA DO NÓ =================
    cantos = []
    for u in diag:
        cantos += ret(u, a - to / 2, a + to / 2, -w_o / 2, w_o / 2)
    X = max(abs(p[0]) for p in cantos) + 25.0
    ytop = -bf / 2
    ybot = min(p[1] for p in cantos) - 25.0
    c = 30.0
    gusset = [(-X, ytop), (X, ytop), (X, ybot + c), (X - c, ybot), (-X + c, ybot),
              (-X, ybot + c)]
    Lf2 = X + 0.9 * bf

    # mesa da viga (banzo do X) e chapa gusset soldada no bordo dela
    d.linha(-Lf2, -bf / 2, Lf2, -bf / 2, "ACO")
    d.linha(-Lf2, bf / 2, Lf2, bf / 2, "ACO")
    d.linha(-Lf2, -vig.tw / 2, Lf2, -vig.tw / 2, "OCULTA")
    d.linha(-Lf2, vig.tw / 2, Lf2, vig.tw / 2, "OCULTA")
    _eixo(d, -Lf2, 0.0, Lf2, 0.0, sobra=est.off * 0.5)
    d.polilinha(gusset, fechada=True, camada="ACO")

    for u in diag:
        _eixo(d, 0.0, 0.0, *P(u, Ld), sobra=20.0)
        # orelha em pé, vista de cima pela espessura; o furo fica oculto dentro dela
        d.polilinha(ret(u, a - to / 2, a + to / 2, -w_o / 2, w_o / 2), fechada=True,
                    camada="ACO")
        for o in (-dfuro / 2, dfuro / 2):
            d.linha(*P(u, a - to / 2, o), *P(u, a + to / 2, o), "OCULTA")
        # corpo do tirante, do lado da diagonal
        for o in (-db / 2, db / 2):
            d.linha(*P(u, a + to / 2, o), *P(u, Ld, o), "ACO")
        quebra(P(u, Ld, -db), P(u, Ld, db))
        # rosca visível entre a orelha e o fim da regulagem (linha fina no fundo do fio)
        for o in (-0.42 * db, 0.42 * db):
            d.linha(*P(u, a + to / 2, o), *P(u, r_tip + L_rosca, o), "ACO-FINO")
        # arruela, porca e contraporca do lado do PT; a ponta sai dois fios
        r = a - to / 2
        d.polilinha(ret(u, r - t_ar, r, -d_ar / 2, d_ar / 2), fechada=True,
                    camada="PARAFUSO")
        r -= t_ar
        for _ in range(2):
            d.polilinha(ret(u, r - m_p, r, -s_p / 2, s_p / 2), fechada=True,
                        camada="PARAFUSO")
            for o in (-s_p / 4, s_p / 4):
                d.linha(*P(u, r - m_p, o), *P(u, r, o), "PARAFUSO")
            r -= m_p
        d.polilinha(ret(u, r_tip, r, -db / 2, db / 2), fechada=True, camada="ACO")

    # ponto de trabalho
    d.circulo(0.0, 0.0, 0.09 * bf, "EIXO")
    d.circulo(0.0, 0.0, 0.035 * bf, "EIXO")

    # escora, para o pórtico vizinho, com o eixo no PT
    ge = _dims_perfil(esc_p)
    be = ge["b"] or ge["h"]
    y_esc = ybot - 1.6 * bf
    d.linha(-be / 2, ybot, -be / 2, y_esc, "ACO")
    d.linha(be / 2, ybot, be / 2, y_esc, "ACO")
    quebra((-be / 2, y_esc), (be / 2, y_esc))
    _eixo(d, 0.0, ybot, 0.0, y_esc, sobra=20.0)

    # indicação do corte B-B, ao longo do tirante D2
    u2 = diag[1]
    for r in (r_tip - 30.0, Ld + 30.0):
        p0, p1 = P(u2, r, -0.35 * est.off), P(u2, r, 0.35 * est.off)
        d.linha(p0[0], p0[1], p1[0], p1[1], "ACO")
        d.texto(p1[0] + 0.4 * est.t, p1[1], "B", est.t, "TEXTO", vertical="meio")

    # soldas e cotas da planta
    _solda(d, est, -X * 0.55, ytop, -X - est.off2, bf * 1.3, perna, tipo="filete",
           texto="gusset-mesa, 2 lados")
    _cota(d, est, 0.0, 0.0, *P(u2, a), -(w_o / 2 + est.off * 0.8), f"a = {_mm(a)}")
    _cota_h(d, est, -X, X, ybot, -est.off, _mm(2 * X))
    _cota_v(d, est, ybot, ytop, -X, -est.off, _mm(ytop - ybot))
    _cota_v(d, est, -bf / 2, bf / 2, Lf2, est.off, f"bf = {_mm(bf)}")
    r_ang = a + 1.3 * bf
    d.arco(0.0, 0.0, r_ang, 180.0, 180.0 + math.degrees(alfa), "COTA")
    meio = alfa / 2.0                      # rótulo no meio do arco, por fora
    d.texto(-r_ang * 1.06 * math.cos(meio), -r_ang * 1.06 * math.sin(meio),
            f"{math.degrees(alfa):.0f}%%d", est.tp, "COTA", alinhamento="direita",
            vertical="meio")

    u1 = diag[0]
    _chamada(d, est, 0.0, 0.0, -Lf2 * 0.45, bf * 2.2, "PT - PONTO DE TRABALHO",
             est.tp, linhas=["eixos dos tirantes e da escora", "concorrem no eixo da mesa"])
    _chamada(d, est, Lf2 * 0.75, bf * 0.25, Lf2 * 0.35, bf * 2.2,
             f"MESA DA VIGA  {vig.nome}", est.tp)
    _chamada(d, est, *P(u1, a, w_o / 2), -Lf2 - est.off * 0.5, ybot * 0.40,
             f"ORELHA t = {_mm(to, 1)}", est.tp, linhas=["uma por tirante"])
    _chamada(d, est, *P(u1, a - to / 2 - t_ar - m_p * 0.5, s_p / 2),
             -Lf2 - est.off * 0.5, ybot * 0.85, "ARRUELA + PORCA + CONTRAPORCA", est.tp)
    _chamada(d, est, -X * 0.6, ybot + 10.0, -Lf2 - est.off * 0.5, ybot - 0.55 * bf,
             f"CHAPA GUSSET t = {_mm(tg, 1)}", est.tp)
    _chamada(d, est, -be / 2, y_esc + 0.3 * bf, -Lf2 * 0.80, y_esc + 0.1 * bf,
             f"ESCORA  {esc_p.nome}", est.tp)
    _chamada(d, est, *P(u2, Ld - 0.4 * bf, -db / 2), Lf2 * 0.75, y_esc - 0.25 * bf,
             f"DIAGONAIS - TIRANTE %%c{_mm(db, 1)} mm", est.tp,
             linhas=[f"rosca {rosca} nas pontas", "esticador no meio (vista C)"])
    y_tit_a = y_esc - 0.25 * bf - est.off2 * 1.6
    _titulo_vista(d, est, 0.0, y_tit_a, "PLANTA DO NO - TIRANTES", est.texto_escala())

    # ================= CORTE B-B (ao longo do tirante D2) =================
    s0 = r_tip - 50.0
    s1 = a + to / 2 + 1.5 * bf
    xB0 = Lf2 + est.off3 * 2.2

    def XB(s):
        return xB0 + (s - s0)

    YB = -bf / 2 - 40.0
    ze = YB + e_f
    g0, g1 = r_tip - 40.0, a + to / 2 + 70.0
    chapa = [(XB(g0), YB - tg), (XB(g1), YB - tg), (XB(g1), YB), (XB(g0), YB)]
    d.polilinha(chapa, fechada=True, camada="ACO")
    d.hachura(chapa, espacamento=3.0, angulo=45.0)
    xl, xr = XB(a - to / 2), XB(a + to / 2)
    for z0, z1 in ((0.0, e_f - dfuro / 2), (e_f + dfuro / 2, h_o)):
        pl = [(xl, YB + z0), (xr, YB + z0), (xr, YB + z1), (xl, YB + z1)]
        d.polilinha(pl, fechada=True, camada="ACO")
        d.hachura(pl, espacamento=2.5, angulo=45.0)
    # tirante cortado no comprimento: não se hachura
    for zz in (ze - db / 2, ze + db / 2):
        d.linha(XB(r_tip), zz, XB(s1), zz, "ACO")
    d.linha(XB(r_tip), ze - db / 2, XB(r_tip), ze + db / 2, "ACO")
    quebra((XB(s1), ze - db), (XB(s1), ze + db))
    _eixo(d, XB(s0), ze, XB(s1), ze, sobra=15.0)
    for zz in (ze - 0.42 * db, ze + 0.42 * db):
        d.linha(XB(r_tip), zz, XB(r_tip + L_rosca), zz, "ACO-FINO")
    x = xl
    d.retangulo(x - t_ar, ze - d_ar / 2, t_ar, d_ar, "PARAFUSO")
    x -= t_ar
    for _ in range(2):
        d.retangulo(x - m_p, ze - 0.58 * s_p, m_p, 1.16 * s_p, "PARAFUSO")
        for zz in (ze - 0.29 * s_p, ze + 0.29 * s_p):
            d.linha(x - m_p, zz, x, zz, "PARAFUSO")
        x -= m_p
    d.filete_solda(xl, YB, perna, 180.0, lado=-1)
    d.filete_solda(xr, YB, perna, 0.0, lado=1)
    _solda(d, est, xr + perna * 0.35, YB + perna * 0.35, xr + est.off2 * 1.4,
           YB + h_o + est.off * 0.8, perna, tipo="filete", texto="orelha-gusset, 2 lados")

    x_dim = XB(g0)
    _cota_v(d, est, YB, ze, xl, -(xl - x_dim) - est.off, f"e = {_mm(e_f)}")
    _cota_v(d, est, YB, YB + h_o, xl, -(xl - x_dim) - est.off2, _mm(h_o))
    _cota_h(d, est, xl, xr, YB + h_o, est.off, _mm(to, 1))
    _cota_v(d, est, ze - db / 2, ze + db / 2, XB(s1) - 30.0, est.off * 0.8,
            f"%%c{_mm(db, 1)}", est.tp)
    _cota_h(d, est, XB(r_tip), XB(r_tip + L_rosca), YB - tg, -est.off,
            f"ROSCA {rosca} - {_mm(L_rosca)}")
    _chamada(d, est, (xl + xr) / 2, ze + dfuro / 2, xr + est.off2 * 0.6,
             YB + h_o + est.off2 * 1.3, f"FURO %%c{_mm(dfuro)} (d + {_mm(folga)})", est.tp)
    _chamada(d, est, XB(g1) - 20.0, YB - tg / 2, XB(g1) + est.off, YB - tg - est.off * 1.8,
             f"CHAPA GUSSET t = {_mm(tg, 1)}", est.tp)
    _chamada(d, est, xl - t_ar - m_p, ze + 0.58 * s_p, x_dim - est.off, YB + h_o + est.off2 * 1.3,
             "ARRUELA + PORCA + CONTRAPORCA", est.tp)
    y_tit_b = YB - tg - est.off2 * 1.9
    _titulo_vista(d, est, XB((s0 + s1) / 2), y_tit_b, "CORTE B-B - PONTA DO TIRANTE",
                  est.texto_escala())

    # ================= VISTA C: ESTICADOR =================
    yC = y_tit_b - est.tt * 1.5 - est.off2 * 2.2
    xC = XB((s0 + s1) / 2)
    Lc2 = L_est / 2
    lb = 1.2 * db                            # olhal rosqueado do esticador
    ext = Lc2 + m_p + 0.9 * bf
    x_ponta = 0.12 * L_est
    for sgn in (-1, 1):
        for zz in (yC - db / 2, yC + db / 2):
            d.linha(xC + sgn * ext, zz, xC + sgn * (Lc2 + m_p), zz, "ACO")
            d.linha(xC + sgn * (Lc2 - lb), zz, xC + sgn * x_ponta, zz, "ACO")
            d.linha(xC + sgn * Lc2, zz, xC + sgn * (Lc2 - lb), zz, "OCULTA")
        d.linha(xC + sgn * x_ponta, yC - db / 2, xC + sgn * x_ponta, yC + db / 2, "ACO")
        quebra((xC + sgn * ext, yC - db), (xC + sgn * ext, yC + db))
        for zz in (yC - 0.42 * db, yC + 0.42 * db):
            d.linha(xC + sgn * x_ponta, zz, xC + sgn * (Lc2 + m_p + ajuste), zz, "ACO-FINO")
        xb0, xb1 = sorted((xC + sgn * Lc2, xC + sgn * (Lc2 - lb)))
        d.retangulo(xb0, yC - 0.9 * db, xb1 - xb0, 1.8 * db, "ACO")
        xc0, xc1 = sorted((xC + sgn * Lc2, xC + sgn * (Lc2 + m_p)))
        d.retangulo(xc0, yC - 0.58 * s_p, xc1 - xc0, 1.16 * s_p, "PARAFUSO")
    for z0, z1 in ((0.55 * db, 0.85 * db), (-0.85 * db, -0.55 * db)):
        d.retangulo(xC - Lc2 + lb, yC + z0, L_est - 2 * lb, z1 - z0, "ACO")
    _eixo(d, xC - ext, yC, xC + ext, yC, sobra=15.0)

    L_re = (Lc2 - x_ponta) + m_p + ajuste
    _cota_h(d, est, xC - Lc2, xC + Lc2, yC + 0.9 * db, est.off, _mm(L_est))
    _cota_h(d, est, xC - Lc2 - m_p - ajuste, xC - x_ponta, yC - 0.9 * db, -est.off,
            f"ROSCA DIR. {rosca} = {_mm(L_re)}", est.tp)
    _cota_h(d, est, xC + x_ponta, xC + Lc2 + m_p + ajuste, yC - 0.9 * db, -est.off,
            f"ROSCA ESQ. {rosca} = {_mm(L_re)}", est.tp)
    _chamada(d, est, xC + Lc2 * 0.4, yC + 0.85 * db, xC + Lc2 + est.off,
             yC + 0.9 * db + est.off2 * 1.2, f"ESTICADOR FORJADO {rosca}", est.tp,
             linhas=["classe >= a da barra"])
    _chamada(d, est, xC - Lc2 - m_p * 0.5, yC + 0.58 * s_p, xC - Lc2 - est.off2,
             yC + 0.9 * db + est.off2 * 1.2, "CONTRAPORCA", est.tp)
    y_tit_c = yC - 0.9 * db - est.off2 * 1.9
    _titulo_vista(d, est, xC, y_tit_c, "VISTA C - ESTICADOR NO MEIO DA DIAGONAL",
                  est.texto_escala())

    # ================= notas =================
    notas = [
        "Cotas em milimetros.",
        f"Tirantes %%c{_mm(db, 1)} mm com rosca {rosca} nas pontas "
        "(Ae = 0,75 Ag, NBR 8800 item 5.2.8).",
        f"Orelha t = {_mm(to, 1)} mm soldada a chapa gusset t = {_mm(tg, 1)} mm; "
        f"gusset soldado a mesa, filete {_mm(perna)} mm.",
        f"Furo %%c{_mm(dfuro)} na orelha; arruela, porca e contraporca do lado do PT.",
        "Esticador no meio da diagonal; pre-tracionar apos o prumo.",
        "Tirantes so trabalham a tracao e nao se ligam no cruzamento.",
        f"Esticador de {_mm(L_est)} mm adotado para o desenho; confirmar no catalogo.",
    ]
    pv = v.get("perfil_vertical")
    if pv:
        pvert = _perfil(pv)
        notas.append(f"Contraventamento vertical: tirante %%c{_mm(pvert.d, 1)} mm, mesmas "
                     "pontas e esticador." if _eh_tirante(pvert) else
                     f"Contraventamento vertical em {pvert.nome}: ligacao parafusada em gusset.")
    notas.append(f"Escora {esc_p.nome} adotada no detalhamento; nao consta do calculo.")
    _notas(d, est, -Lf2 - est.off3, min(y_tit_a, y_tit_c) - est.off3, notas)
    return d


def _no_cantoneira(v: dict) -> Desenho:
    """Nó do X de cobertura em cantoneira: diagonais parafusadas na chapa gusset soldada
    à mesa da viga, com diagonais e escora concorrendo no PT (Cap. 14.2.1b)."""
    vig = _perfil(v["perfil_viga"])
    dia = _perfil(v["perfil_diagonal"])
    esc_p = _perfil(v["perfil_escora"])
    tg = float(v["gusset_esp"])
    dpar = float(v["d_parafuso"])
    dfuro = dpar + 2.0
    npar = int(v["n_parafusos"])
    gab = float(v["gabarito"])
    borda = float(v["borda"])
    alfa = math.radians(float(v["angulo"]))
    perna = float(v["perna_solda"])

    est = Estilo(10.0)
    d = Desenho("detalhe-contraventamento")

    # ---------------- mesa da viga em planta (banzo do X) ----------------
    bf = vig.bf
    Lf = 8.0 * bf
    d.linha(-Lf / 2, -bf / 2, Lf / 2, -bf / 2, "ACO")
    d.linha(-Lf / 2, bf / 2, Lf / 2, bf / 2, "ACO")
    d.linha(-Lf / 2, -vig.tw / 2, Lf / 2, -vig.tw / 2, "OCULTA")
    d.linha(-Lf / 2, vig.tw / 2, Lf / 2, vig.tw / 2, "OCULTA")
    _eixo(d, -Lf / 2 - est.off, 0.0, Lf / 2 + est.off, 0.0)

    # ---------------- gusset ----------------
    Lg = 3.1 * bf
    Hg = 2.4 * bf
    d.polilinha([(-Lg / 2, -bf / 2), (Lg / 2, -bf / 2), (Lg / 2, -bf / 2 - Hg * 0.42),
                 (Lg * 0.18, -bf / 2 - Hg), (-Lg * 0.18, -bf / 2 - Hg),
                 (-Lg / 2, -bf / 2 - Hg * 0.42)], fechada=True, camada="ACO")

    # ---------------- ponto de trabalho ----------------
    PT = (0.0, 0.0)
    d.circulo(PT[0], PT[1], 0.09 * bf, "EIXO")
    d.circulo(PT[0], PT[1], 0.035 * bf, "EIXO")
    _chamada(d, est, PT[0], PT[1], -Lf * 0.30, bf * 1.9,
             "PT - PONTO DE TRABALHO", est.tp,
             linhas=["eixos das barras concorrentes", "sobre o eixo da mesa"])

    # ---------------- diagonais e escora ----------------
    gd = _dims_perfil(dia)
    bd = gd["b"]
    Ld = 3.6 * bf
    eixos = [(-math.cos(alfa), -math.sin(alfa), "DIAGONAL D1"),
             (math.cos(alfa), -math.sin(alfa), "DIAGONAL D2")]
    for ux, uy, rot in eixos:
        _eixo(d, PT[0], PT[1], PT[0] + ux * Ld, PT[1] + uy * Ld)
        # cantoneira em planta: faixa de largura bd centrada no eixo de gramil
        nx, ny = -uy, ux
        p1 = (PT[0] + ux * 0.22 * Ld, PT[1] + uy * 0.22 * Ld)
        p2 = (PT[0] + ux * Ld, PT[1] + uy * Ld)
        for s in (-0.35, 0.65):
            d.linha(p1[0] + nx * bd * s, p1[1] + ny * bd * s,
                    p2[0] + nx * bd * s, p2[1] + ny * bd * s, "ACO")
        d.linha(p2[0] + nx * bd * -0.35, p2[1] + ny * bd * -0.35,
                p2[0] + nx * bd * 0.65, p2[1] + ny * bd * 0.65, "ACO-FINO")
        # parafusos ao longo do eixo
        for k in range(npar):
            dist = borda + 0.30 * Ld * 0 + k * gab + 0.36 * Ld
            px, py = PT[0] + ux * dist, PT[1] + uy * dist
            d.parafuso(px, py, dpar)
            d.circulo(px, py, dfuro / 2, "FURO")

    # escora perpendicular à mesa, para o outro pórtico
    Le = bf / 2 + Hg + 1.8 * bf
    _eixo(d, PT[0], PT[1], PT[0], PT[1] - Le)
    ge = _dims_perfil(esc_p)
    be = ge["b"] or ge["h"]
    d.linha(-be / 2, -bf / 2 - Hg * 0.55, -be / 2, -Le, "ACO")
    d.linha(be / 2, -bf / 2 - Hg * 0.55, be / 2, -Le, "ACO")
    d.linha(-be / 2, -Le, be / 2, -Le, "ACO-FINO")

    # ---------------- soldas ----------------
    _solda(d, est, -Lg * 0.30, -bf / 2, -Lg * 0.55 - est.off3, bf * 1.1, perna,
           tipo="filete", texto="gusset-mesa, 2 lados")

    # ---------------- cotas ----------------
    ux, uy = math.cos(alfa), -math.sin(alfa)
    p_a = (PT[0] + ux * (0.36 * Ld), PT[1] + uy * (0.36 * Ld))
    p_b = (PT[0] + ux * (0.36 * Ld + gab), PT[1] + uy * (0.36 * Ld + gab))
    _cota(d, est, PT[0], PT[1], p_a[0], p_a[1], -est.off * 1.4, _mm(0.36 * Ld))
    _cota(d, est, p_a[0], p_a[1], p_b[0], p_b[1], -est.off * 1.4, _mm(gab))
    _cota_h(d, est, -Lg / 2, Lg / 2, -bf / 2 - Hg, -est.off, _mm(Lg))
    _cota_v(d, est, -bf / 2 - Hg, -bf / 2, -Lg / 2, -est.off, _mm(Hg))
    _cota_v(d, est, -bf / 2, bf / 2, Lf / 2, est.off, f"bf = {_mm(bf)}")
    _chamada(d, est, -Lg * 0.34, -bf / 2 - Hg * 0.86, -Lf * 0.30,
             -bf / 2 - Hg * 1.25, f"GUSSET t = {_mm(tg, 1)}", est.tp)

    # ângulo da diagonal
    r_ang = 1.5 * bf
    d.arco(PT[0], PT[1], r_ang, 180, 180 + math.degrees(alfa), "COTA")
    d.texto(PT[0] - r_ang * 1.12, PT[1] - r_ang * 0.30,
            f"{math.degrees(alfa):.0f}%%d", est.tp, "COTA", alinhamento="direita")

    _chamada(d, est, PT[0] + math.cos(alfa) * Ld * 0.85,
             PT[1] - math.sin(alfa) * Ld * 0.85, Lf * 0.32, -Le * 0.80,
             f"DIAGONAIS  {dia.nome}", est.tp,
             linhas=[f"{npar} parafusos %%c{_mm(dpar, 1)}"])
    _chamada(d, est, be / 2, -Le * 0.88, -Lf * 0.30, -Le - est.off * 0.6,
             f"ESCORA  {esc_p.nome}", est.tp)
    _chamada(d, est, Lf * 0.36, 0.0, Lf * 0.30, bf * 1.9,
             f"MESA DA VIGA  {vig.nome}", est.tp)

    _titulo_vista(d, est, 0.0, -Le - est.off3 * 1.6,
                  "NO DE CONTRAVENTAMENTO - PLANTA", est.texto_escala())
    _notas(d, est, -Lf / 2, -Le - est.off3 * 2.4, [
        "Cotas em milimetros.",
        f"Gusset t = {_mm(tg, 1)} mm, soldado a mesa da viga com filete {_mm(perna)} mm.",
        "Os eixos das barras devem concorrer no PT; excentricidade gera M = N.e.",
        f"Parafusos %%c{_mm(dpar, 1)} A325, furos %%c{_mm(dfuro)} mm.",
        "Distancia ao bordo livre do gusset >= 2 t na barra comprimida.",
        "Angulo das diagonais entre 35%%d e 55%%d.",
    ])
    return d


# =====================================================================================
# 9. Prancha de seções
# =====================================================================================

def secoes_perfis(projeto, nomes: Optional[Sequence[str]] = None) -> Desenho:
    """Quadro com as seções transversais de todos os perfis usados no galpão."""
    g = _Geo(projeto)
    if nomes is None:
        nomes = [g.pilar.nome, g.viga.nome, g.terca.nome, g.longarina.nome,
                 g.perfis["contrav_cobertura"], g.perfis["contrav_vertical"],
                 g.perfis["escora"]]
    vistos, lista = set(), []
    for n in nomes:
        if n and n not in vistos:
            vistos.add(n)
            lista.append(n)
    d = Desenho("secoes-perfis")
    est = Estilo(5.0)
    x = 0.0
    alturas = []
    for n in lista:
        p = _perfil(n)
        gg = _dims_perfil(p)
        passo = max(gg["b"], 160.0) + 6.0 * est.off
        desenhar_perfil(p, x + passo / 2, 0.0, corte=True, escala=5.0, desenho=d)
        alturas.append(gg["h"])
        x += passo
    hmax = max(alturas) if alturas else 400.0
    _titulo_vista(d, est, x / 2.0, -hmax / 2 - 9.0 * est.off,
                  "SECOES DOS PERFIS", est.texto_escala())
    _notas(d, est, 0.0, -hmax / 2 - 11.0 * est.off, [
        "Cotas em milimetros.",
        "Hachura indica secao cortada.",
    ])
    return d


# =====================================================================================
# 10. Geração de todos os desenhos
# =====================================================================================

#: Ordem, nome de arquivo, título e escala sugerida de cada desenho.
# =====================================================================================
# Diagramas do pórtico e quadro de verificações
# =====================================================================================

#: Grandezas desenhadas, na ordem: chave no mapa, título e unidade.
GRANDEZAS_DIAGRAMA = (
    ("M", "MOMENTO FLETOR", "kN.m"),
    ("V", "ESFORCO CORTANTE", "kN"),
    ("N", "FORCA NORMAL", "kN"),
)

#: Quanto da altura do pórtico a maior ordenada do diagrama ocupa.
ALTURA_DIAGRAMA = 0.42


def _mapa_de_esforcos(projeto):
    """Mapa de esforços do projeto, ou `None` quando não há análise disponível.

    Os desenhos também são gerados a partir de um `DadosGalpao` cru, sem cálculo — daí
    a tolerância. É o mesmo mapa que o editor 3D usa, então papel e tela contam a mesma
    história. A importação é tardia porque `nucleo3d.mapa_esforcos` lê a geometria
    daqui.
    """
    if not hasattr(projeto, "esforcos"):
        return None
    try:
        from nucleo3d import mapa_esforcos
        mapa = mapa_esforcos.mapa_de_esforcos(projeto)
    except Exception:
        return None
    return mapa if mapa.get("ok") else None


def _ponto_barra(p) -> Tuple[float, float]:
    """Ponto do mapa (x, vão, altura) na elevação do pórtico (x = vão, y = altura)."""
    return (p[1], p[2])


def _serie(diagrama: dict, grandeza: str) -> Tuple[List[float], List[float]]:
    """Ordenadas máximas e mínimas da barra: na envoltória são duas, senão uma só."""
    if not diagrama:
        return [], []
    if grandeza in diagrama:
        v = diagrama[grandeza]
        return v, v
    return diagrama.get(grandeza + "_max", []), diagrama.get(grandeza + "_min", [])


def _pico_do_mapa(mapa: dict, chave: str, grandeza: str) -> float:
    pico = 0.0
    for b in mapa["portico"]["barras"]:
        alto, baixo = _serie(b["diagramas"].get(chave), grandeza)
        for serie in (alto, baixo):
            for v in serie or []:
                pico = max(pico, abs(v))
    return pico


def _fita_diagrama(d: Desenho, est: Estilo, barra: dict, chave: str, grandeza: str,
                   escala_ord: float, dx: float = 0.0,
                   dy: float = 0.0) -> List[Tuple[float, float, float]]:
    """Desenha o diagrama de uma barra e devolve os extremos (valor, x, y) do trecho.

    A ordenada é medida perpendicular à barra, na `normal` que o mapa manda — a face
    tracionada pelo momento positivo. É a convenção do desenho estrutural: o diagrama
    de momentos fica do lado que traciona.
    """
    diagrama = barra["diagramas"].get(chave)
    alto, baixo = _serie(diagrama, grandeza)
    if not alto and not baixo:
        return []
    s = (diagrama or {}).get("s") or []
    (x0, y0), (x1, y1) = _ponto_barra(barra["ini"]), _ponto_barra(barra["fim"])
    nx, ny = barra["normal"][1], barra["normal"][2]
    extremos = []

    for serie in [s for s in (alto, baixo) if s]:
        contorno = []
        for i, t in enumerate(s[:len(serie)]):
            bx = x0 + (x1 - x0) * t + dx
            by = y0 + (y1 - y0) * t + dy
            v = serie[i]
            contorno.append((bx + nx * v * escala_ord, by + ny * v * escala_ord))
        base_i = (x0 + dx, y0 + dy)
        base_f = (x0 + (x1 - x0) * s[len(serie) - 1] + dx,
                  y0 + (y1 - y0) * s[len(serie) - 1] + dy)
        d.polilinha([base_i] + contorno + [base_f], fechada=True, camada="COTA")
        k = max(range(len(serie)), key=lambda j: abs(serie[j]))
        if abs(serie[k]) > 1e-9:
            extremos.append((serie[k], contorno[k][0], contorno[k][1]))
    return extremos


def _esqueleto_portico(d: Desenho, g: _Geo, dx: float = 0.0, dy: float = 0.0,
                       camada="ACO"):
    """Eixo do pórtico: pilares e as duas águas, linha simples."""
    V, H, hc = g.vao, g.H, g.h_cumeeira
    d.polilinha([(dx, dy), (dx, dy + H), (dx + V / 2.0, dy + hc),
                 (dx + V, dy + H), (dx + V, dy)], camada=camada)
    for x in (dx, dx + V):
        d.linha(x - 0.02 * V, dy, x + 0.02 * V, dy, "EIXO")


def diagramas_portico(projeto) -> Desenho:
    """Diagramas de N, V e M do pórtico, na envoltória das combinações últimas.

    Três elevações empilhadas, uma por grandeza, com o diagrama medido perpendicular à
    barra e os valores de pico cotados. Os números vêm do mesmo mapa que o editor 3D
    desenha na tela (`nucleo3d/mapa_esforcos.py`), que por sua vez vem da análise que
    dimensionou as peças: o papel não recalcula nada por conta própria.

    Empilhadas, e não lado a lado, por dois motivos: a folha aproveita melhor a altura
    e o desenho não fica com três vãos de largura, que jogaria as coordenadas para
    longe demais da escala do próprio galpão.
    """
    g = _Geo(projeto)
    est = Estilo(100.0)
    d = Desenho("diagramas-portico")
    mapa = _mapa_de_esforcos(projeto)
    alvo = g.h_cumeeira * ALTURA_DIAGRAMA
    passo = g.h_cumeeira * 1.25 + 2.0 * alvo

    for k, (grandeza, titulo, unidade) in enumerate(GRANDEZAS_DIAGRAMA):
        dx, dy = 0.0, -k * passo
        _esqueleto_portico(d, g, dx, dy)
        escala_txt = ""
        if mapa:
            pico = _pico_do_mapa(mapa, "envoltoria", grandeza)
            escala_ord = (alvo / pico) if pico > 1e-9 else 0.0
            extremos = []
            for barra in mapa["portico"]["barras"]:
                extremos += [(v, x, y, barra["rotulo"])
                             for v, x, y in _fita_diagrama(
                                 d, est, barra, "envoltoria", grandeza, escala_ord,
                                 dx, dy)]
            # só os maiores recebem cota, e nunca dois no mesmo lugar: valores vizinhos
            # (o pico de duas barras que se encontram num nó) sairiam um por cima do
            # outro e se liam como um número só — "26,5" e "27" viram "226,5"
            extremos.sort(key=lambda e: -abs(e[0]))
            postos: List[Tuple[float, float]] = []
            for v, x, y, _rot in extremos:
                if abs(v) < 0.12 * pico or len(postos) >= 6:
                    break
                yt = y + (est.tp * 0.4 if v >= 0 else -est.tp * 1.4)
                if any(abs(x - px) < est.tp * 3.2 and abs(yt - py) < est.tp * 1.6
                       for px, py in postos):
                    continue
                d.texto(x, yt, f"{_mm(abs(v), 1)}", est.tp, "TEXTO", alinhamento="centro")
                postos.append((x, yt))
            escala_txt = (f"1 cm = {_mm(alvo / 10.0 / escala_ord, 1)} {unidade}"
                          if escala_ord else "")
        _titulo_vista(d, est, dx + g.vao / 2.0, dy - alvo - est.off,
                      f"{titulo} ({unidade})", escala_txt)

    if mapa:
        casos = [c["chave"] for c in mapa["combinacoes"] if c["tipo"] == "ultima"]
        # uma vez cada combinação: as de vento se repetem com cpi+ e cpi- (a nota numa
        # linha só ficava mais larga que os diagramas)
        bases = list(dict.fromkeys(re.sub(r"\s*\(cpi.*?\)$", "", c) for c in casos))
        cpi = " (as de vento com cpi+ e cpi-)" if len(bases) < len(casos) else ""
        desloc = mapa["servico"].get("deslocamento") or {}
        notas = [
            "Envoltoria das combinacoes ultimas: " + "; ".join(bases) + cpi + ".",
            "Ordenadas perpendiculares a barra; o momento positivo fica do lado "
            "tracionado.",
            "Valores em kN e kN.m, por portico, para o espacamento adotado.",
        ]
        if desloc:
            notas.append(
                f"Deslocamento horizontal do topo: {_mm(desloc.get('u_cm', 0), 2)} cm "
                f"<= {_mm(desloc.get('limite_cm', 0), 2)} cm ({desloc.get('criterio', '')}).")
        notas.append("Diagramas gerados pela mesma analise que dimensionou as pecas.")
        so = (getattr(projeto, "esforcos", None) or {}).get("segunda_ordem") if isinstance(
            getattr(projeto, "esforcos", None), dict) else None
        if so:
            notas.append("Valores de 1a ordem; pilar e viga verificados com os momentos x %s "
                         "(2a ordem, B1/B2 da NBR 8800, Anexo D)."
                         % _mm(max(so["fator_pilar"], so["fator_viga"]), 2))
    else:
        notas = ["Sem analise disponivel: gere os desenhos a partir de um galpao "
                 "dimensionado para ver os diagramas."]
    ultimo = -(len(GRANDEZAS_DIAGRAMA) - 1) * passo
    _notas(d, est, 0.0, ultimo - alvo - est.off3 * 1.4, notas)
    d.escala_sugerida = est.texto_escala()
    return d


#: Fator do quadro: o desenho sai em milímetros de papel (1:1), e este fator dá o
#: tamanho confortável de leitura numa prancha A1 — texto de 2,8 mm.
ESCALA_QUADRO = 1.4

#: Colunas do quadro: (título, largura em mm de papel, alinhamento).
COLUNAS_QUADRO = (
    ("MARCA", 16.0, "esquerda"),
    ("ELEMENTO", 52.0, "esquerda"),
    ("PERFIL", 40.0, "esquerda"),
    ("M (kN.m)", 20.0, "direita"),
    ("V (kN)", 16.0, "direita"),
    ("N (kN)", 16.0, "direita"),
    ("VERIFICACAO QUE GOVERNA", 74.0, "esquerda"),
    ("Sd/Rd", 16.0, "direita"),
    ("SITUACAO", 22.0, "esquerda"),
)

#: Marca de cada elemento no desenho, igual à da lista de material.
MARCAS_QUADRO = {
    "Pilar": "P1", "Viga": "V1", "Mísula": "V1", "Terça": "T1",
    "Longarina": "L1", "Contraventamento de cobertura": "CC",
    "Contraventamento vertical": "CV",
}


def _marca_do_elemento(nome: str) -> str:
    for chave, marca in MARCAS_QUADRO.items():
        if nome.lower().startswith(chave.lower()):
            return marca
    return "-"


def _razao(v) -> str:
    """Razão S/R com duas casas, arredondando meio para cima.

    Duas casas porque numa coluna de razões 0,90 lê melhor que 0,9; meio para cima
    porque o arredondamento bancário do Python transformaria 0,825 em 0,82, e quem
    confere a tabela contra o memorial espera 0,83.
    """
    from decimal import Decimal, ROUND_HALF_UP
    try:
        d = Decimal(str(float(v))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (TypeError, ValueError, ArithmeticError):
        return "-"
    return f"{d}".replace(".", ",")


def _cortar(texto, larg: float, altura: float) -> str:
    """O que cabe na coluna: no DXF cada letra ocupa cerca de 0,72 da altura do texto."""
    t = str(texto)
    cabe = max(3, int(larg / (altura * 0.72)))
    return t if len(t) <= cabe else t[:cabe - 1].rstrip(" -,") + "."


def _linha_quadro(d: Desenho, est: Estilo, x: float, y: float, valores: Sequence[str],
                  altura: float, cabecalho=False, k: float = ESCALA_QUADRO):
    """Uma linha do quadro, com as réguas verticais e o texto em cada coluna."""
    xi = x
    for (titulo, larg, alin), valor in zip(COLUNAS_QUADRO, valores):
        larg *= k
        tx = xi + (larg - 1.6 * k if alin == "direita" else 1.6 * k)
        d.texto(tx, y - altura * 0.70, _cortar(valor, larg - 3.2 * k, est.tp),
                est.tp, "TEXTO", alinhamento=alin)
        d.linha(xi, y, xi, y - altura, "ACO-FINO")
        xi += larg
    d.linha(xi, y, xi, y - altura, "ACO-FINO")
    d.linha(x, y - altura, xi, y - altura, "ACO" if cabecalho else "ACO-FINO")
    return xi


def quadro_verificacoes(projeto) -> Desenho:
    """Quadro com o aproveitamento de cada peça, ligação e base.

    É a tabela que o projetista procura primeiro: o que governa cada peça, com qual
    esforço e com que folga. Os valores são os do memorial — vêm do mesmo cálculo.
    """
    k = ESCALA_QUADRO
    est = Estilo(k)                       # tabela não tem escala: sai em mm de papel
    d = Desenho("quadro-verificacoes")
    mapa = _mapa_de_esforcos(projeto)
    largura = sum(c[1] for c in COLUNAS_QUADRO) * k
    alt_linha = 6.2 * k
    y = 0.0

    _titulo_vista(d, est, largura / 2.0, y + 9.0 * k, "QUADRO DE VERIFICACOES")
    if mapa:
        d.texto(largura / 2.0, y + 3.4 * k,
                "Esforcos da envoltoria das combinacoes ultimas", est.tp, "TEXTO",
                alinhamento="centro")
    d.linha(0.0, y, largura, y, "ACO")
    _linha_quadro(d, est, 0.0, y, [c[0] for c in COLUNAS_QUADRO], alt_linha,
                  cabecalho=True)
    y -= alt_linha

    if mapa:
        for nome, e in mapa["elementos"].items():
            dim = e["dimensionamento"]
            situacao = "ATENDE" if e["ok"] else "NAO ATENDE"
            _linha_quadro(d, est, 0.0, y, [
                _marca_do_elemento(nome), nome, e["perfil"],
                _mm(dim["M"], 1) if dim["M"] else "-",
                _mm(dim["V"], 1) if dim["V"] else "-",
                _mm(dim["N"], 1) if dim["N"] else "-",
                e["governa"] or "-",
                _razao(e["aproveitamento"]), situacao], alt_linha)
            y -= alt_linha

    for chave, r in (getattr(projeto, "ligacoes", None) or {}).items():
        _linha_quadro(d, est, 0.0, y, [
            "-", f"Ligacao {chave}", r.perfil or "-", "-", "-", "-",
            r.critica.titulo if r.critica else "-",
            _razao(r.razao), "ATENDE" if r.ok else "NAO ATENDE"], alt_linha)
        y -= alt_linha
    base = getattr(projeto, "base", None)
    if base is not None:
        _linha_quadro(d, est, 0.0, y, [
            "-", "Base do pilar", base.perfil or "-", "-", "-", "-",
            base.critica.titulo if base.critica else "-",
            _razao(base.razao), "ATENDE" if base.ok else "NAO ATENDE"], alt_linha)
        y -= alt_linha

    if not mapa and not getattr(projeto, "ligacoes", None):
        d.texto(1.6, y - alt_linha * 0.72, "Sem calculo disponivel.", est.tp, "TEXTO")
        y -= alt_linha

    notas = ["M, V e N sao os esforcos que dimensionaram a peca, no caso que governa.",
             "Sd/Rd e a razao da verificacao critica: 1,00 e o limite da norma.",
             "Conferir com o memorial de calculo antes da fabricacao."]
    if mapa:
        desloc = mapa["servico"].get("deslocamento") or {}
        if desloc:
            notas.insert(0, f"Deslocamento do topo {_mm(desloc.get('u_cm', 0), 2)} cm de "
                            f"{_mm(desloc.get('limite_cm', 0), 2)} cm "
                            f"({desloc.get('criterio', '')}).")
    _notas(d, est, 0.0, y - alt_linha, notas)
    d.escala_sugerida = "1:1"
    return d


CATALOGO = [
    ("01-PORTICO", "Portico tipico - elevacao", "1:100", portico),
    ("02-PLANTA-COBERTURA", "Planta de cobertura", "1:200", planta_cobertura),
    ("03-ELEVACAO-LONGITUDINAL", "Elevacao longitudinal", "1:200", elevacao_longitudinal),
    ("04-LIGACAO-VIGA-PILAR", "Ligacao viga-pilar (joelho)", "1:10", ligacao_viga_pilar),
    ("05-LIGACAO-CUMEEIRA", "Ligacao de cumeeira", "1:10", ligacao_cumeeira),
    ("06-BASE-PILAR", "Base do pilar", "1:10", base_pilar),
    ("07-DETALHE-TERCA", "Apoio de terca e corrente", "1:5", detalhe_terca),
    ("08-DETALHE-CONTRAVENTAMENTO", "No de contraventamento", "1:10",
     detalhe_contraventamento),
    ("09-SECOES-PERFIS", "Secoes dos perfis", "1:5", secoes_perfis),
    ("10-DIAGRAMAS-PORTICO", "Diagramas do portico - M, V e N", "1:100",
     diagramas_portico),
    ("11-QUADRO-DE-VERIFICACOES", "Quadro de verificacoes", "1:1", quadro_verificacoes),
]


def catalogo_de(projeto) -> List[tuple]:
    """Os desenhos que se aplicam a este projeto.

    A ligação de joelho e a de cumeeira por chapa de topo são do pórtico de alma cheia.
    Numa tesoura elas não existem — quem liga os banzos é a chapa de nó —, e imprimir
    essas pranchas seria detalhar uma peça que a obra não vai ter.
    """
    try:
        trelicado = _dados_galpao(projeto).eh_trelicado
    except Exception:
        trelicado = False
    if not trelicado:
        return list(CATALOGO)
    fora = {"04-LIGACAO-VIGA-PILAR", "05-LIGACAO-CUMEEIRA"}
    return [x for x in CATALOGO if x[0] not in fora]


def gerar_todos(projeto, pasta: str) -> List[dict]:
    """Grava todos os DXF em `pasta` e devolve a lista do que foi criado.

    Cada item: `{"arquivo", "nome", "titulo", "escala", "largura_mm", "altura_mm"}`.
    """
    os.makedirs(os.path.abspath(pasta), exist_ok=True)
    saida = []
    for nome, titulo, escala, fn in catalogo_de(projeto):
        d = fn(projeto)
        caminho = os.path.join(pasta, f"{nome}.dxf")
        d.gravar(caminho)
        saida.append(dict(arquivo=os.path.abspath(caminho), nome=nome, titulo=titulo,
                          escala=getattr(d, "escala_sugerida", escala),
                          largura_mm=round(d.largura, 1),
                          altura_mm=round(d.altura, 1)))
    return saida


if __name__ == "__main__":                      # python -m saida.desenhos [pasta]
    destino = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_RAIZ, "projetos", "_desenhos")
    for item in gerar_todos(DadosGalpao(), destino):
        print(f"{item['nome']:<30} {item['escala']:>7}  "
              f"{item['largura_mm']:.0f} x {item['altura_mm']:.0f} mm")
