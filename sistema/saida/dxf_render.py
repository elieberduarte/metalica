# -*- coding: utf-8 -*-
"""Lê um DXF R12 e o desenha em PNG ou PDF.

Serve a dois propósitos: conferir visualmente o que foi gravado (o DXF é a fonte única
dos desenhos) e montar as pranchas de impressão, que assim mostram exatamente o mesmo
conteúdo que o arquivo de CAD entregue.
"""
import math
import os
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

# cores ACI usadas nas camadas padrão
CORES_ACI = {1: "#d62728", 2: "#b8860b", 3: "#2e8b57", 4: "#17becf", 5: "#0b3d91",
             6: "#a12a1f", 7: "#111111", 8: "#7a7a7a", 9: "#9aa4b2"}

TRACOS = {"CONTINUOUS": (0, ()), "CENTER": (0, (12, 3, 2, 3)),
          "HIDDEN": (0, (5, 3)), "DASHED": (0, (8, 4))}


def ler_dxf(caminho: str) -> dict:
    """Extrai camadas e entidades de um DXF R12."""
    with open(caminho, encoding="cp1252", errors="replace") as f:
        bruto = f.read().split("\n")
    pares = []
    i = 0
    while i < len(bruto) - 1:
        cod = bruto[i].strip()
        if cod.isdigit() or (cod.startswith("-") and cod[1:].isdigit()):
            pares.append((int(cod), bruto[i + 1].rstrip("\r")))
            i += 2
        else:
            i += 1

    camadas: Dict[str, dict] = {}
    entidades: List[dict] = []
    secao = None
    tabela = None
    atual = None
    tipo_atual = None

    def fechar():
        nonlocal atual, tipo_atual
        if atual is not None and tipo_atual:
            atual["tipo"] = tipo_atual
            entidades.append(atual)
        atual, tipo_atual = None, None

    for cod, val in pares:
        if cod == 0:
            if val == "SECTION":
                secao = "?"
                continue
            if val == "ENDSEC":
                fechar()
                secao = tabela = None
                continue
            if secao == "TABLES":
                # fecha a camada anterior antes de abrir qualquer coisa nova
                if tipo_atual == "LAYER" and atual:
                    camadas[atual.get("nome", "0")] = atual
                    atual, tipo_atual = None, None
                if val == "LAYER":
                    tabela = "LAYER"
                    atual = {}
                    tipo_atual = "LAYER"
                    continue
                if val in ("LTYPE", "STYLE", "TABLE", "ENDTAB"):
                    atual, tipo_atual = None, None
                    tabela = None
                    continue
            if secao == "ENTITIES":
                fechar()
                if val in ("LINE", "CIRCLE", "ARC", "TEXT", "SOLID", "POLYLINE", "VERTEX", "SEQEND"):
                    tipo_atual = val
                    atual = {"pontos": []}
                continue
        if cod == 2 and secao == "?":
            secao = val
            continue
        if tipo_atual == "LAYER":
            if cod == 2:
                atual["nome"] = val
            elif cod == 62:
                atual["cor"] = abs(int(val))
            elif cod == 6:
                atual["tipo_linha"] = val
            continue
        if atual is None:
            continue
        if cod == 8:
            atual["camada"] = val
        elif cod == 1:
            atual["texto"] = val
        elif cod in (10, 11, 12, 13, 20, 21, 22, 23, 40, 41, 50, 51, 72, 73, 70):
            try:
                atual[cod] = float(val)
            except ValueError:
                atual[cod] = 0.0

    fechar()
    if tipo_atual == "LAYER" and atual:
        camadas[atual.get("nome", "0")] = atual

    # agrupa POLYLINE + VERTEX
    saida = []
    poli = None
    for e in entidades:
        if e["tipo"] == "POLYLINE":
            poli = {"tipo": "POLYLINE", "camada": e.get("camada", "0"),
                    "fechada": bool(int(e.get(70, 0))) and int(e.get(70, 0)) & 1,
                    "pontos": []}
        elif e["tipo"] == "VERTEX" and poli is not None:
            poli["pontos"].append((e.get(10, 0.0), e.get(20, 0.0)))
        elif e["tipo"] == "SEQEND":
            if poli:
                saida.append(poli)
            poli = None
        else:
            saida.append(e)
    return {"camadas": camadas, "entidades": saida}


def _cor(camada: str, camadas: dict) -> str:
    c = camadas.get(camada, {})
    return CORES_ACI.get(int(c.get("cor", 7)), "#111111")


def _traco(camada: str, camadas: dict):
    return TRACOS.get(camadas.get(camada, {}).get("tipo_linha", "CONTINUOUS"), (0, ()))


#: códigos de controle do DXF para caracteres especiais (AutoCAD)
SIMBOLOS = {"%%c": "ø", "%%C": "ø", "%%d": "°", "%%D": "°",
            "%%p": "±", "%%P": "±", "%%%": "%"}


def _simbolos(texto: str) -> str:
    for k, v in SIMBOLOS.items():
        texto = texto.replace(k, v)
    return texto


def _caixa_texto(x, y, texto, altura, ha, va, rot):
    """Caixa aproximada de um texto, em unidades do desenho (para o autoscale)."""
    larg = len(texto) * altura * 0.62
    dx = {"left": (0.0, larg), "center": (-larg / 2, larg / 2),
          "right": (-larg, 0.0)}[ha]
    dy = {"baseline": (-0.25 * altura, altura), "center": (-0.6 * altura, 0.6 * altura),
          "top": (-altura, 0.25 * altura)}[va]
    cantos = [(dx[0], dy[0]), (dx[1], dy[0]), (dx[1], dy[1]), (dx[0], dy[1])]
    a = math.radians(rot or 0.0)
    ca, sa = math.cos(a), math.sin(a)
    return [(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in cantos]


def _escala_texto_automatica(ents, ax) -> float:
    """Fator que faz o texto sair no PNG com o mesmo tamanho relativo do DXF.

    A altura do texto no DXF está em milímetros do modelo, enquanto `ax.text` recebe
    pontos de tela. Sem correção, um desenho de 20 m e um detalhe de 200 mm sairiam com
    a mesma letra. Aqui a altura em mm é convertida pela razão entre o tamanho da figura
    e a extensão do desenho, de modo que o PNG mostre o que sairia no plot.
    """
    xs, ys = [], []
    for e in ents:
        if e["tipo"] == "POLYLINE":
            xs += [p[0] for p in e["pontos"]]
            ys += [p[1] for p in e["pontos"]]
        elif e["tipo"] == "TEXT":
            hj, vj = int(e.get(72, 0)), int(e.get(73, 0))
            x = e.get(11, e.get(10, 0)) if (hj or vj) else e.get(10, 0)
            y = e.get(21, e.get(20, 0)) if (hj or vj) else e.get(20, 0)
            ha = {0: "left", 1: "center", 2: "right"}.get(hj, "left")
            va = {0: "baseline", 2: "center", 3: "top"}.get(vj, "baseline")
            for px, py in _caixa_texto(x, y, _simbolos(e.get("texto", "")),
                                       e.get(40, 2.5), ha, va, e.get(50, 0)):
                xs.append(px)
                ys.append(py)
        else:
            for c in (10, 11, 12, 13):
                if c in e:
                    xs.append(e[c])
            for c in (20, 21, 22, 23):
                if c in e:
                    ys.append(e[c])
    if not xs or not ys:
        return 1.0
    larg = max(1e-6, max(xs) - min(xs))
    alt = max(1e-6, max(ys) - min(ys))
    fw, fh = ax.figure.get_size_inches()
    pt_por_mm = min(fw * 72.0 / larg, fh * 72.0 / alt)
    # fontsize usado abaixo é h*2.4*escala_texto; queremos h*pt_por_mm
    return max(1e-5, min(50.0, pt_por_mm / 2.4))


def desenhar(caminho_dxf: str, ax=None, escala_texto=1.0, camadas_ocultas=()):
    """`escala_texto=None` calcula o fator automaticamente (texto em escala real)."""
    doc = ler_dxf(caminho_dxf)
    cams, ents = doc["camadas"], doc["entidades"]
    if ax is None:
        fig, ax = plt.subplots(figsize=(11, 8))
    if escala_texto is None:
        escala_texto = _escala_texto_automatica(ents, ax)
    for e in ents:
        cam = e.get("camada", "0")
        if cam in camadas_ocultas:
            continue
        cor = _cor(cam, cams)
        lw = 1.4 if cam in ("ACO", "CONCRETO") else (0.5 if cam in ("HACHURA", "COTA", "EIXO") else 0.9)
        t = e["tipo"]
        if t == "LINE":
            ax.plot([e.get(10, 0), e.get(11, 0)], [e.get(20, 0), e.get(21, 0)],
                    color=cor, lw=lw, ls=_traco(cam, cams), solid_capstyle="round")
        elif t == "CIRCLE":
            ax.add_patch(plt.Circle((e.get(10, 0), e.get(20, 0)), e.get(40, 1),
                                    fill=False, color=cor, lw=lw))
        elif t == "ARC":
            a0, a1 = e.get(50, 0), e.get(51, 360)
            if a1 < a0:
                a1 += 360
            ang = [math.radians(a) for a in _linspace(a0, a1, 60)]
            xc, yc, r = e.get(10, 0), e.get(20, 0), e.get(40, 1)
            ax.plot([xc + r * math.cos(a) for a in ang], [yc + r * math.sin(a) for a in ang],
                    color=cor, lw=lw)
        elif t == "POLYLINE":
            pts = e["pontos"]
            if len(pts) >= 2:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                if e.get("fechada"):
                    xs.append(pts[0][0])
                    ys.append(pts[0][1])
                ax.plot(xs, ys, color=cor, lw=lw, ls=_traco(cam, cams))
        elif t == "SOLID":
            pts = [(e.get(10, 0), e.get(20, 0)), (e.get(11, 0), e.get(21, 0)),
                   (e.get(12, 0), e.get(22, 0)), (e.get(13, 0), e.get(23, 0))]
            ax.add_patch(MplPolygon(pts, closed=True, facecolor=cor, edgecolor=cor, lw=0.3))
        elif t == "TEXT":
            h = e.get(40, 2.5) * escala_texto
            hj = int(e.get(72, 0))
            vj = int(e.get(73, 0))
            x = e.get(11, e.get(10, 0)) if (hj or vj) else e.get(10, 0)
            y = e.get(21, e.get(20, 0)) if (hj or vj) else e.get(20, 0)
            ha = {0: "left", 1: "center", 2: "right"}.get(hj, "left")
            va = {0: "baseline", 2: "center", 3: "top"}.get(vj, "baseline")
            txt = _simbolos(e.get("texto", ""))
            ax.text(x, y, txt, fontsize=h * 2.4, color=cor,
                    rotation=e.get(50, 0), ha=ha, va=va, rotation_mode="anchor",
                    family="DejaVu Sans")
            # o texto não entra no autoscale do matplotlib; sem isto o tight_layout
            # espreme os eixos para caber uma legenda que ficou fora do desenho
            ax.update_datalim(_caixa_texto(x, y, txt, e.get(40, 2.5), ha, va,
                                           e.get(50, 0)))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.autoscale_view()
    return ax


def _linspace(a, b, n):
    if n < 2:
        return [a]
    passo = (b - a) / (n - 1)
    return [a + i * passo for i in range(n)]


def para_png(caminho_dxf: str, caminho_png: str, dpi=120, largura=12.0,
             escala_texto=None):
    """`escala_texto=None` (padrão) desenha o texto na escala real do desenho."""
    fig, ax = plt.subplots(figsize=(largura, largura * 0.72))
    desenhar(caminho_dxf, ax, escala_texto=escala_texto)
    fig.tight_layout(pad=0.4)
    os.makedirs(os.path.dirname(os.path.abspath(caminho_png)), exist_ok=True)
    fig.savefig(caminho_png, dpi=dpi, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return caminho_png


if __name__ == "__main__":
    import sys
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".dxf", ".png")
    print(para_png(src, dst))
