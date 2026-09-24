# -*- coding: utf-8 -*-
"""Modelo de prancha da Hermes (`Projeto/Modelos de Pranchas - Hermes.dwg`).

Medidas tiradas do DWG, em mm de papel, para as folhas A0 a A3 do modelo (A4 segue a
A3): quadro com 25 mm à esquerda (furação para arquivo) e 7 mm nos outros lados, marcas
de dobra entre a borda e o quadro, o aviso de direito de propriedade em pé na margem
esquerda e o carimbo no canto inferior direito — 178 × 99,8 mm (0,6 disso na A3/A4) —
com caixas de canto arredondado (R2): logo, CONTEÚDO, ESCALA, DATA, OBRA e PROJETISTA.
"""
from datetime import date
from typing import List, Sequence, Tuple

from nucleo2d.desenho import Desenho, Linha, Polilinha, Arco, Texto, Hachura, Camada2D

__all__ = ["MARGENS", "carimbo_tamanho", "desenhar_folha", "mes_ano"]

#: Margens do quadro (mm): as mesmas em todos os formatos do modelo.
MARGENS = {"esquerda": 25.0, "direita": 7.0, "superior": 7.0, "inferior": 7.0}
#: Carimbo na escala 1 (A0, A1, A2); a A3 do modelo usa o mesmo desenho reduzido a 0,6.
CARIMBO = (178.0, 99.8)
FATOR_CARIMBO = {"A0": 1.0, "A1": 1.0, "A2": 1.0, "A3": 0.6, "A4": 0.6}
RAIO = 2.0
#: Caixas do carimbo (x0, y0, x1, y1) a partir do canto inferior esquerdo dele.
CAIXAS = {
    "obra": (5.36, 5.01, 125.08, 19.97),
    "projetista": (130.07, 5.01, 172.97, 19.97),
    "data": (130.07, 24.96, 172.97, 39.93),
    "escala": (130.07, 44.91, 172.97, 59.88),
    "conteudo": (5.36, 24.96, 125.08, 59.88),
    "logo": (5.36, 64.87, 172.97, 94.8),
}
#: Rótulo de cada caixa (itálico no modelo), onde ele vai e onde vai o valor (à
#: esquerda, meio da altura).
ROTULOS = {"obra": ("OBRA:", (7.78, 16.52), (12.7, 12.5)),
           "projetista": ("PROJETISTA:", (131.97, 16.52), (138.2, 12.5)),
           "data": ("DATA:", (131.97, 36.48), (138.2, 32.2)),
           "escala": ("ESCALA:", (131.97, 56.43), (138.2, 52.1)),
           "conteudo": ("CONTEÚDO:", (7.78, 56.43), (12.8, 47.7))}
H_ROTULO = 1.9
H_VALOR = 1.9
H_CONTEUDO = 3.0
#: Marcas de dobra (mm a partir do canto inferior esquerdo da folha): "x" nas bordas de
#: cima e de baixo, "y" nas laterais, "so_cima" só na borda de cima.
DOBRAS = {
    "A0": {"x": (210.0, 329.5, 449.0, 634.0, 819.0, 1004.0), "y": (297.0, 594.0)},
    "A1": {"x": (211.0, 341.0, 471.0, 656.0), "y": (297.0,)},
    "A2": {"x": (121.0, 217.0, 313.0, 409.0), "so_cima": (105.0,), "y": (297.0,)},
    "A3": {"x": (235.0,), "y": ()},
    "A4": {"x": (), "y": ()},
}
AVISO = ("RESERVAMO-NOS O DIREITO DE PROPRIEDADE DESTE  DESENHO QUE NÃO PODERÁ SER",
         "COPIADO, CEDIDO OU REPRODUZIDO NO TODO  OU EM  PARTES,  SOB PENA  INCIDIREM OS",
         "VIOLADORES NAS SANCÕES DO TITULO IV  CAPITULO I  DO DECRETO LEI N- 7908 DE 27 DE",
         "AGOSTO DE 1946,  COM  AS EMENDAS  DO  DECRETO  LEI N- 8481  DE  27  DE  FEVEREIRO",
         "DE 1948.")
H_AVISO = 1.44
MESES = ("JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO",
         "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO")

# Logo HERMES (hachuras sólidas; a do "R" leva o furo como segundo contorno), nas
# coordenadas do carimbo em escala 1 — extraído do bloco "logo" do DWG.
from nucleo2d._logo_hermes import LOGO_HACHURAS  # noqa: E402


def mes_ano(d: date = None) -> str:
    d = d or date.today()
    return "%s / %d" % (MESES[d.month - 1], d.year)


def carimbo_tamanho(formato: str) -> Tuple[float, float]:
    f = FATOR_CARIMBO.get(formato, 1.0)
    return CARIMBO[0] * f, CARIMBO[1] * f


def _largura_texto(texto: str, altura: float) -> float:
    """Largura aproximada de uma linha em Arial (maiúsculas): 0,68 × altura por caractere."""
    return 0.68 * altura * len(texto)


def _quebrar(texto: str, largura: float, altura: float) -> List[str]:
    """Quebra por palavras para caber em `largura`; recuo de 2 espaços nas continuações."""
    linhas, atual = [], ""
    for p in texto.split(" "):
        cand = (atual + " " + p) if atual else p
        if atual and _largura_texto(cand, altura) > largura:
            linhas.append(atual)
            atual = "  " + p
        else:
            atual = cand
    if atual:
        linhas.append(atual)
    return linhas


def _caixa_arredondada(d: Desenho, x0, y0, x1, y1, r, camada, atr):
    def L(a, b):
        d.add(Linha(camada=camada, a=(round(a[0], 3), round(a[1], 3)), b=(round(b[0], 3), round(b[1], 3)), atributos=dict(atr)))
    L((x0 + r, y0), (x1 - r, y0))
    L((x1, y0 + r), (x1, y1 - r))
    L((x1 - r, y1), (x0 + r, y1))
    L((x0, y1 - r), (x0, y0 + r))
    for cx, cy, a0 in ((x1 - r, y0 + r, 270.0), (x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, 90.0), (x0 + r, y0 + r, 180.0)):
        d.add(Arco(camada=camada, centro=(round(cx, 3), round(cy, 3)), raio=r, inicio=a0, fim=a0 + 90.0, atributos=dict(atr)))


def desenhar_folha(d: Desenho, formato: str, larg: float, alt: float, info: dict,
                   numero: int, total: int, escala_txt: str, conteudo: Sequence[str]):
    """Borda, quadro, marcas de dobra, aviso na margem e carimbo. Devolve (quadro, carimbo)
    como caixas (x0, y0, x1, y1)."""
    cam = "PRANCHA"
    d.camadas[cam] = Camada2D(cam, "#111827", espessura=0.5)
    d.camadas["CARIMBO"] = Camada2D("CARIMBO", "#111827", espessura=0.25)
    atr = {"prancha": "moldura"}
    m = MARGENS
    d.add(Polilinha(camada="CARIMBO", vertices=[(0, 0), (larg, 0), (larg, alt), (0, alt)], fechada=True, atributos=dict(atr)))
    x0, y0 = m["esquerda"], m["inferior"]
    x1, y1 = larg - m["direita"], alt - m["superior"]
    d.add(Polilinha(camada=cam, vertices=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fechada=True, atributos=dict(atr)))

    def L(a, b):
        d.add(Linha(camada="CARIMBO", a=(round(a[0], 3), round(a[1], 3)), b=(round(b[0], 3), round(b[1], 3)), atributos=dict(atr)))
    dob = DOBRAS.get(formato, {})
    for x in dob.get("x", ()):
        L((x, 0), (x, y0))
        L((x, y1), (x, alt))
    for x in dob.get("so_cima", ()):
        L((x, y1), (x, alt))
    for y in dob.get("y", ()):
        L((0, y), (x0, y))
        L((x1, y), (larg, y))
    # aviso de propriedade, em pé na margem esquerda (a primeira linha mais à esquerda),
    # centrado em x = 11,9 mm como no modelo
    passo = H_AVISO * 1.667
    xb = 11.93 - (len(AVISO) - 1) * passo / 2.0 + H_AVISO / 2.0
    for i, linha in enumerate(AVISO):
        d.add(Texto(camada="CARIMBO", posicao=(round(xb + i * passo, 3), 10.58), texto=linha, altura=H_AVISO, angulo=90.0,
                    atributos=dict(atr, campo="aviso")))

    # carimbo
    f = FATOR_CARIMBO.get(formato, 1.0)
    lc, ac = CARIMBO[0] * f, CARIMBO[1] * f
    cx0, cy0 = x1 - lc, y0

    def P(x, y):
        return (round(cx0 + x * f, 3), round(cy0 + y * f, 3))
    d.add(Polilinha(camada=cam, vertices=[(cx0, cy0), (x1, cy0), (x1, cy0 + ac), (cx0, cy0 + ac)], fechada=True, atributos=dict(atr)))
    for (bx0, by0, bx1, by1) in CAIXAS.values():
        (ax, ay), (bx, by) = P(bx0, by0), P(bx1, by1)
        _caixa_arredondada(d, ax, ay, bx, by, RAIO * f, "CARIMBO", atr)
    for contornos in LOGO_HACHURAS:
        d.add(Hachura(camada="CARIMBO", contornos=[[P(x, y) for x, y in c] for c in contornos], padrao="solido",
                      angulo=0.0, espacamento=0.3, atributos=dict(atr, campo="logo")))

    def T(pos, texto, h, campo, vertical="base", al="esquerda"):
        d.add(Texto(camada="CARIMBO", posicao=P(*pos), texto=str(texto), altura=round(h * f, 3), alinhamento=al,
                    vertical=vertical, atributos=dict(atr, campo=campo)))
    for rot, p_rot, _ in ROTULOS.values():
        T(p_rot, rot, H_ROTULO, "rotulo")

    def valor(campo, texto):
        """Valor na caixa: a letra diminui até 1,3 mm para caber; se nem assim, corta."""
        vx, vy = ROTULOS[campo][2]
        larg_util = CAIXAS[campo][2] - vx - 2.0
        h = H_VALOR
        while h > 1.3 and _largura_texto(texto, h) > larg_util:
            h -= 0.1
        n_max = int(larg_util / (0.68 * h))
        if len(texto) > n_max:
            texto = texto[:max(n_max - 1, 1)] + "…"
        T((vx, vy), texto, h, campo, vertical="meio")
    obra = str(info.get("obra") or "").strip()
    cliente = str(info.get("cliente") or "").strip()
    if cliente and cliente.upper() not in obra.upper():
        obra = "%s - %s" % (obra, cliente) if obra else cliente
    valor("obra", obra.upper())
    valor("projetista", str(info.get("projetista") or info.get("responsavel") or "").upper())
    valor("data", str(info.get("data") or mes_ano()).upper())
    valor("escala", escala_txt.upper())

    # conteúdo: uma linha por grupo ("- TESOURAS: T1 (05x), T2 (02x)"), quebrando por
    # palavras; a letra diminui até caber na caixa
    vx, vy = ROTULOS["conteudo"][2]
    larg_util = CAIXAS["conteudo"][2] - vx - 3.0
    y_fundo = CAIXAS["conteudo"][1] + 5.5            # acima do número da prancha
    itens = [str(t).upper() for t in conteudo if str(t).strip()] or ["-"]
    for h in (H_CONTEUDO, 2.6, 2.2, 1.9, 1.6):
        linhas = [ln for t in itens for ln in _quebrar(t, larg_util, h)]
        passo = 1.55 * h
        cabem = int((vy - y_fundo) / passo) + 1
        if len(linhas) <= cabem:
            break
    if len(linhas) > cabem:
        linhas = linhas[:cabem - 1] + ["  … E MAIS %d LINHA(S): VER O ÍNDICE" % (len(linhas) - cabem + 1)]
    for i, ln in enumerate(linhas):
        T((vx, vy - i * passo), ln, h, "conteudo", vertical="meio")
    rev = str(info.get("revisao") or "").strip()
    T((CAIXAS["conteudo"][2] - 2.0, CAIXAS["conteudo"][1] + 2.0),
      "PRANCHA %02d/%02d%s" % (numero, total, ("   REV. %s" % rev) if rev else ""), 1.7, "prancha", al="direita")
    return (x0, y0, x1, y1), (cx0, cy0, x1, cy0 + ac)
