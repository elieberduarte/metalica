# -*- coding: utf-8 -*-
"""As pranchas do projetista como ele emitiu: o espaço do papel do DXF desenhado no CAD.

Regra do usuário (27/10, GER-04): o desenho Original de uma obra recebida em DWG/DXF traz TODAS as folhas inteiras —
moldura, carimbo, tabelas, notas, títulos — para conferir o 3D contra o projeto ("não sei se esses desenhos que aparecem
ali no 2D são uma interpretação do nosso sistema do projeto dele ou são o projeto original mesmo"). A importação lia só
o espaço do modelo; o papel (os layouts) e as janelas que mostram o modelo ficavam de fora.

Aqui cada layout vira uma folha no desenho, como sai na impressão:

* o que está desenhado no papel (moldura, carimbo, notas) entra como está;
* cada janela (VIEWPORT) mostra o pedaço do modelo que ela enquadra, na escala e no giro dela, cortado na borda da
  janela (`dxf_ler.recortar`);
* camadas desligadas, congeladas, que não plotam ou congeladas só naquela janela não entram — a folha impressa;
* objeto colado de outro programa (OLE: a planilha do Excel) só tem o lugar no DXF: entra o contorno com o aviso.

O papel é desenhado no tamanho de impressão vezes a escala do desenho de destino: a letra do carimbo sai com a altura
de papel dela e uma janela 1:50 num desenho 1:50 mostra o modelo no tamanho real. Os layouts ficam lado a lado, na
ordem do arquivo, a partir de `deslocamento` (o canto de baixo à esquerda).
"""
import math
from typing import Dict, List, Optional, Tuple

from nucleo2d import dxf_ler as L
from nucleo2d.desenho import Desenho, Polilinha, Texto

Ponto2 = Tuple[float, float]

#: o texto do contorno do objeto OLE
AVISO_OLE = "objeto colado de outro programa (OLE, ex.: planilha do Excel) — o DXF não traz o conteúdo"


def _caixa(e: dict, T) -> Optional[Tuple[float, float, float, float]]:
    """a caixa do objeto no sistema de quem o desenha (None: sem como saber — entra sempre)"""
    t = e["tipo"]
    if t == "LINE":
        pts = [e["a"], e["b"]]
    elif t in ("CIRCLE", "ARC"):
        (cx, cy), r = e["c"], e["r"]
        pts = [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
    elif t in ("LWPOLYLINE", "POLYLINE", "SPLINE", "LEADER", "SOLID", "TRACE", "3DFACE", "OLE2FRAME"):
        pts = list(e.get("pts") or [])
    elif t in ("TEXT", "ATTRIB"):
        h = e.get("h") or 0.0
        w = h * max(len(e.get("texto") or ""), 1)
        pts = [e["p"], e.get("p2") or e["p"]]
        pts += [(x + dx, y + dy) for x, y in list(pts) for dx, dy in ((-w, -h), (w, h))]
    elif t == "MTEXT":
        h = e.get("h") or 0.0
        w = e.get("largura") or h * max(len(e.get("texto") or ""), 1)
        n = (e.get("texto") or "").count("\\P") + 1
        x, y = e["p"]
        pts = [(x - w, y - h * 2 * n), (x + w, y + h * 2 * n)]
    elif t == "HATCH":
        pts = [p for ct in e.get("contornos") or [] for p in ct]
    elif t == "ELLIPSE":
        (cx, cy), (mx, my) = e["c"], e["maj"]
        a = math.hypot(mx, my)
        pts = [(cx - a, cy - a), (cx + a, cy + a)]
    elif t == "MULTILEADER":
        pts = [p for ln in e.get("linhas") or [] for p in ln] + [e.get("p") or (0.0, 0.0)]
    else:
        return None
    if not pts:
        return None
    q = [T.ap(p) for p in pts]
    xs, ys = [p[0] for p in q], [p[1] for p in q]
    return (min(xs), min(ys), max(xs), max(ys))


def _cruza(a, b) -> bool:
    return a is None or not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def camadas_ocultas(dxf: dict) -> set:
    """as camadas que não saem na folha impressa: desligadas, congeladas ou que não plotam"""
    return {n for n, c in dxf["camadas"].items() if c.get("desligada") or c.get("congelada") or c.get("plota") is False}


def layouts(dxf: dict) -> List[dict]:
    """[{nome, ents}] — o layout ativo (as entidades do arquivo marcadas como papel) e os outros (os blocos
    *Paper_Space<n>), na ordem do arquivo; só os que têm algo além da janela da própria folha"""
    ativo = next((b for n, b in dxf["blocos"].items() if n.upper() == "*PAPER_SPACE"), {})
    out = [{"nome": "papel", "ents": [e for e in dxf["entidades"] if e.get("papel")], "registro": ativo.get("registro")}]
    for nome, b in dxf["blocos"].items():
        if nome.upper().startswith("*PAPER_SPACE") and nome.upper() != "*PAPER_SPACE":
            out.append({"nome": nome, "ents": b["ents"], "registro": b.get("registro")})
    return [l for l in out if any(e["tipo"] != "VIEWPORT" or janela_valida(e) for e in l["ents"])]


def janela_de_plotagem(dxf: dict, lay: dict) -> Optional[Tuple[float, float, float, float]]:
    """o retângulo do papel que sai na impressão, quando o layout plota por "Janela" (tipo 4); None: a folha inteira"""
    L_ = (dxf.get("layouts") or {}).get(lay.get("registro") or "")
    if not L_ or L_.get("tipo_plot") != 4 or not L_.get("janela_plot"):
        return None
    x0, y0, x1, y1 = L_["janela_plot"]
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return None
    return (x0, y0, x1, y1)


def janela_valida(v: dict) -> bool:
    """janela que mostra o modelo: não é a da própria folha (id 1), está ligada e tem tamanho"""
    return v["tipo"] == "VIEWPORT" and v.get("id") != 1 and v.get("status") != 0 and bool(v.get("h"))         and bool(v.get("w")) and bool(v.get("altura_vista"))


def _janela_para_papel(v: dict) -> "L._T":
    """modelo → papel da janela: o ponto relativo ao alvo, girado pelo giro da vista (a vista d = R(giro)·(p − alvo),
    a conta da ezdxf), menos o centro da vista, na escala da janela, a partir do centro dela no papel"""
    k = (v["h"] / v["altura_vista"]) if v.get("altura_vista") else 1.0
    th = math.radians(v.get("giro") or 0.0)
    cs, sn = math.cos(th), math.sin(th)
    ax, ay = v.get("alvo") or (0.0, 0.0)
    vx, vy = v.get("centro_vista") or (0.0, 0.0)
    cx, cy = v["c"]
    a, b, c, d = k * cs, -k * sn, k * sn, k * cs
    return L._T(a, b, c, d, cx - k * vx - (a * ax + b * ay), cy - k * vy - (c * ax + d * ay))


def janela_no_modelo(v: dict) -> Tuple[float, float, float, float]:
    """a caixa do modelo que a janela enquadra"""
    k = (v["altura_vista"] / v["h"]) if v.get("h") else 1.0
    th = math.radians(-(v.get("giro") or 0.0))
    cs, sn = math.cos(th), math.sin(th)
    ax, ay = v.get("alvo") or (0.0, 0.0)
    vx, vy = v.get("centro_vista") or (0.0, 0.0)
    pts = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dy = vx + sx * v["w"] / 2 * k, vy + sy * v["h"] / 2 * k
        pts.append((ax + cs * dx - sn * dy, ay + sn * dx + cs * dy))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _caixa_do_layout(dxf: dict, ents: list) -> Optional[Tuple[float, float, float, float]]:
    # o texto fica fora: a caixa dele é só uma estimativa folgada (para escolher o que a janela pega); a folha é a
    # moldura, os traços e as janelas
    cx = [c for e, T in L._achatar(dxf, so_modelo=False, ents=ents) if e["tipo"] not in ("TEXT", "MTEXT", "ATTRIB")
          for c in [_caixa(e, T)] if c]
    for e in ents:
        if janela_valida(e):
            x, y = e["c"]
            cx.append((x - e["w"] / 2, y - e["h"] / 2, x + e["w"] / 2, y + e["h"] / 2))
    if not cx:
        return None
    return (min(c[0] for c in cx), min(c[1] for c in cx), max(c[2] for c in cx), max(c[3] for c in cx))


def para_desenho(texto: str = None, destino: Optional[Desenho] = None, deslocamento: Ponto2 = (0.0, 0.0),
                 escala: Optional[float] = None, prefixo_camada: str = "", dxf: Optional[dict] = None,
                 mm_por_unidade_papel: float = 1.0) -> Tuple[Desenho, dict]:
    """Acrescenta as folhas do espaço do papel ao desenho (ou a um novo). `escala`: a do desenho de destino (None: a
    dele). Devolve (desenho, resumo {folhas: [{nome, caixa, janelas, entidades}], entidades})."""
    if dxf is None:
        dxf = L.ler_dxf(texto)
    des = destino if destino is not None else Desenho(nome="Folhas do projetista", escala=escala or 1.0)
    k = float(escala or des.escala or 1.0)
    F = k * mm_por_unidade_papel                     # papel → desenho
    ocultas = camadas_ocultas(dxf)
    por_handle = {c.get("handle"): n for n, c in dxf["camadas"].items() if c.get("handle")}
    modelo = [(e, T, _caixa(e, T)) for e, T in L._achatar(dxf) if e.get("camada", "0") not in ocultas]
    resumo = {"folhas": [], "entidades": 0}
    x_cursor = float(deslocamento[0])
    for lay in layouts(dxf):
        caixa = _caixa_do_layout(dxf, lay["ents"])
        if not caixa:
            continue
        # plotada por "Janela": a folha é o retângulo impresso; o que está no papel fora dele não foi emitido (ADM, 27/10:
        # 340 mm de papel à esquerda da A0 da 900 entravam na folha)
        plot = janela_de_plotagem(dxf, lay)
        if plot:
            caixa = plot
        ox, oy = x_cursor - F * caixa[0], float(deslocamento[1]) - F * caixa[1]
        Tp = L._T(F, 0.0, 0.0, F, ox, oy)
        corte = (Tp.ap(plot[:2]) + Tp.ap(plot[2:])) if plot else None
        atr = {"origem": "dxf-papel", "folha_papel": lay["nome"]}
        desenhados = [e for e in lay["ents"] if e["tipo"] not in ("VIEWPORT", "OLE2FRAME")]
        pares = [(e, T) for e, T in L._achatar(dxf, so_modelo=False, ents=desenhados, T0=Tp)
                 if e.get("camada", "0") not in ocultas]
        _, r = L.para_desenho(None, escala=k, fator=1.0, destino=des, prefixo_camada=prefixo_camada, dxf=dxf,
                              pares=pares, recorte=corte, atributos=atr)
        n = r["entidades"]
        for e in lay["ents"]:
            if e["tipo"] != "OLE2FRAME" or e.get("camada", "0") in ocultas:
                continue
            (x0, y0), (x1, y1) = [Tp.ap(p) for p in e["pts"]]
            cam = (prefixo_camada + (e.get("camada") or "0")).strip()
            des.add(Polilinha(camada=cam, vertices=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fechada=True,
                              atributos=dict(atr, ole=True)))
            des.add(Texto(camada=cam, posicao=((x0 + x1) / 2, (y0 + y1) / 2), texto=AVISO_OLE, altura=3.5,
                          alinhamento="centro", vertical="meio", atributos=dict(atr, ole=True)))
            n += 2
        janelas, mapas = 0, []
        for v in lay["ents"]:
            if not janela_valida(v):
                continue
            (px, py), w, h = v["c"], v["w"], v["h"]
            a, b = Tp.ap((px - w / 2, py - h / 2)), Tp.ap((px + w / 2, py + h / 2))
            r_ = (a[0], a[1], b[0], b[1])
            if corte:
                r_ = (max(r_[0], corte[0]), max(r_[1], corte[1]), min(r_[2], corte[2]), min(r_[3], corte[3]))
                if r_[0] >= r_[2] or r_[1] >= r_[3]:
                    continue                                   # a janela está fora do que foi impresso
            janela = janela_no_modelo(v)
            congeladas = {por_handle.get(h) for h in v.get("congeladas") or []}
            Tv = Tp.depois(_janela_para_papel(v))
            # a conta modelo → desenho de cada janela: o vínculo 2D ↔ 3D vai às vistas da folha impressa (ADM, 27/10)
            mapas.append({"janela": v.get("id"), "modelo": tuple(round(c, 6) for c in janela),
                          "transformacao": (Tv.a, Tv.b, Tv.c, Tv.d, Tv.tx, Tv.ty)})
            pares = [(e, Tv.depois(T)) for e, T, c in modelo if _cruza(c, janela) and e.get("camada", "0") not in congeladas]
            _, r = L.para_desenho(None, escala=k, fator=1.0, destino=des, prefixo_camada=prefixo_camada, dxf=dxf,
                                  pares=pares, recorte=r_, atributos=dict(atr, janela=v.get("id")))
            n += r["entidades"]
            janelas += 1
        x1 = x_cursor + F * (caixa[2] - caixa[0])
        resumo["folhas"].append({"nome": lay["nome"], "caixa": (round(x_cursor, 1), round(float(deslocamento[1]), 1),
                                                                round(x1, 1), round(float(deslocamento[1]) + F * (caixa[3] - caixa[1]), 1)),
                                 "janelas": janelas, "mapas": mapas, "entidades": n})
        resumo["entidades"] += n
        x_cursor = x1 + 0.05 * (x1 - x_cursor)
    return des, resumo
