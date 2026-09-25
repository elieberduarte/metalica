# -*- coding: utf-8 -*-
"""Eixos da obra: as linhas numeradas (as tesouras, atravessadas ao galpão) e as linhas
com letra (os apoios — chumbadores ou chapas de base — ao longo do galpão), identificadas
do próprio modelo e gravadas no projeto para o usuário renomear, mover e acrescentar.

O IFC de fábrica não traz os pilares de concreto nem a malha de eixos: o que há são as
tesouras e os chumbadores. As tesouras dão o eixo do galpão (PCA em planta dos centroides
das peças delas: com várias tesouras o maior espalhamento é o eixo; com uma só, o menor) e
cada agrupamento de peças ao longo dele é um eixo numerado (1, 2, 3…). Os chumbadores
(ou, sem eles, as chapas horizontais mais baixas) agrupados na direção atravessada são os
eixos com letra (A, B, C…). Coordenadas: `g` ao longo do galpão, `p` atravessado, no plano.

`segmentos` dá as linhas em 3D para as plantas desenharem (com as bolinhas e as cotas
entre eixos em `nucleo2d.detalhe.conjuntos._desenhar_eixos`), e `de_dict` valida o que o
usuário gravou no projeto (`projeto.json` → `eixos`).
"""
import math
import string
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo3d.modelo import Documento, Solido, Barra, Chapa

Ponto = Tuple[float, float, float]

#: Peças a menos disto (mm) na mesma linha são o mesmo eixo.
GAP_EIXO = 600.0
#: Quanto a linha do eixo passa além do último eixo atravessado (mm).
FOLGA_EIXO = 1500.0


def _centroide(vs: Sequence[Ponto]) -> Ponto:
    n = len(vs)
    return (sum(v[0] for v in vs) / n, sum(v[1] for v in vs) / n, sum(v[2] for v in vs) / n)


def _pca_2d(pts: Sequence[Tuple[float, float]]):
    """(eixo maior, eixo menor) unitários e os desvios ao longo deles, em planta."""
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts) / n
    syy = sum((p[1] - my) ** 2 for p in pts) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts) / n
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    maior = (math.cos(ang), math.sin(ang))
    menor = (-maior[1], maior[0])
    var_maior = sxx * maior[0] ** 2 + 2 * sxy * maior[0] * maior[1] + syy * maior[1] ** 2
    var_menor = sxx * menor[0] ** 2 + 2 * sxy * menor[0] * menor[1] + syy * menor[1] ** 2
    if var_menor > var_maior:
        maior, menor, var_maior, var_menor = menor, maior, var_menor, var_maior
    return maior, menor, math.sqrt(max(var_maior, 0.0)), math.sqrt(max(var_menor, 0.0))


def _agrupar(valores: Sequence[float], gap: float = GAP_EIXO) -> List[float]:
    """Valores em 1D agrupados por proximidade; a posição de cada grupo é a média."""
    vs = sorted(valores)
    grupos: List[List[float]] = []
    for v in vs:
        if grupos and v - grupos[-1][-1] <= gap:
            grupos[-1].append(v)
        else:
            grupos.append([v])
    return [sum(g) / len(g) for g in grupos]


def _letra(i: int) -> str:
    letras = string.ascii_uppercase
    return letras[i] if i < 26 else letras[i // 26 - 1] + letras[i % 26]


def _marcas(e) -> dict:
    return (getattr(e, "atributos", None) or {}).get("marcas") or {}


def _vertices(e) -> List[Ponto]:
    if isinstance(e, Solido):
        return list(e.vertices)
    if isinstance(e, Barra):
        return [tuple(e.inicio), tuple(e.fim)]
    if isinstance(e, Chapa):
        try:
            from nucleo3d import geometria as _geo
            return [tuple(v) for v in _geo.malha(e)[0]]          # chapa paramétrica
        except Exception:                                       # noqa: BLE001
            return [tuple(e.origem)]
    return []


def identificar_eixos(doc: Documento, nomes: Optional[dict] = None) -> dict:
    """Os eixos pelo modelo. `nomes`: o nomes.json do detalhamento (tipos por marca e por
    conjunto); sem ele, ou sem tesoura reconhecida, as tesouras são adivinhadas pelas
    peças mais altas e os apoios pelas chapas mais baixas."""
    nomes = nomes or {}
    tipos = nomes.get("tipos") or {}
    tipos_conj = nomes.get("tipos_conjuntos") or {}
    conj_tes = {m for m, t in tipos_conj.items() if t == "tesoura"}
    pecas = [e for e in doc.entidades.values() if isinstance(e, (Solido, Barra, Chapa)) and getattr(e, "visivel", True)]
    if not pecas:
        raise ValueError("o modelo não tem peças.")
    todos_v = [v for e in pecas for v in _vertices(e)]
    z_min, z_max = min(v[2] for v in todos_v), max(v[2] for v in todos_v)

    def marca_conj(e) -> str:
        return str(_marcas(e).get("conjunto") or "")

    tes = [e for e in pecas if marca_conj(e) in conj_tes] if conj_tes else []
    if not tes:
        # sem nomes: as peças da metade de cima do modelo desenham as tesouras
        tes = [e for e in pecas if _centroide(_vertices(e))[2] >= z_min + 0.5 * (z_max - z_min)] or pecas
    cs = [_centroide(_vertices(e)) for e in tes if _vertices(e)]
    maior, menor, d_maior, d_menor = _pca_2d([(c[0], c[1]) for c in cs])
    # várias tesouras: o maior espalhamento é o eixo do galpão; uma só: o menor
    varias = d_maior > 500.0 and d_menor > 500.0 and d_maior / max(d_menor, 1.0) < 8.0
    g = maior if (varias or d_maior > 4.0 * d_menor and len(_agrupar([c[0] * maior[0] + c[1] * maior[1] for c in cs])) >= 2) else menor
    if d_maior < 500.0:
        g = menor
    if g[0] < 0 or (abs(g[0]) < 1e-9 and g[1] < 0):
        g = (-g[0], -g[1])
    p = (-g[1], g[0])
    gs = [c[0] * g[0] + c[1] * g[1] for c in cs]
    numeros = [{"nome": str(i + 1), "pos": round(v, 1)} for i, v in enumerate(_agrupar(gs))]
    # apoios: chumbadores; senão chapas horizontais junto do nível mais baixo das tesouras
    chumb = [e for e in pecas if tipos.get(str(_marcas(e).get("posicao") or "")) == "chumbador"]
    origem_letras = "chumbadores"
    if not chumb:
        z_tes = min(v[2] for e in tes for v in _vertices(e))
        chumb = []
        for e in pecas:
            if not isinstance(e, (Solido, Chapa)):
                continue
            vs = _vertices(e)
            if len(vs) < 4:
                continue
            zs = [v[2] for v in vs]
            xs = [v[0] for v in vs]
            ys = [v[1] for v in vs]
            if max(zs) - min(zs) <= 25.0 and max(max(xs) - min(xs), max(ys) - min(ys)) >= 80.0 and max(zs) <= z_tes + 800.0:
                chumb.append(e)
        origem_letras = "chapas de base" if chumb else "extremos das tesouras"
    if chumb:
        cc = [_centroide(_vertices(e)) for e in chumb]
        ps = [c[0] * p[0] + c[1] * p[1] for c in cc]
        z_base = min(v[2] for e in chumb for v in _vertices(e))
    else:
        vs_t = [v for e in tes for v in _vertices(e)]
        ps = [min(v[0] * p[0] + v[1] * p[1] for v in vs_t), max(v[0] * p[0] + v[1] * p[1] for v in vs_t)]
        z_base = min(v[2] for v in vs_t)
    letras = [{"nome": _letra(i), "pos": round(v, 1)} for i, v in enumerate(_agrupar(ps))]
    return {"eixo_g": [round(g[0], 6), round(g[1], 6)], "perp_g": [round(p[0], 6), round(p[1], 6)],
            "numeros": numeros, "letras": letras, "z_base": round(z_base, 1),
            "origem": "auto", "fonte_letras": origem_letras}


def de_dict(d: Optional[dict]) -> Optional[dict]:
    """O que veio do projeto (ou do usuário), validado; None quando não serve."""
    if not isinstance(d, dict):
        return None
    try:
        g = [float(d["eixo_g"][0]), float(d["eixo_g"][1])]
        L = math.hypot(g[0], g[1])
        if L < 1e-9:
            return None
        g = [g[0] / L, g[1] / L]
        p = [-g[1], g[0]]
        def lista(chave):
            saida = []
            for item in d.get(chave) or []:
                nome = str(item.get("nome") or "").strip()
                if not nome:
                    continue
                saida.append({"nome": nome[:6], "pos": round(float(item.get("pos")), 1)})
            return sorted(saida, key=lambda x: x["pos"])
        numeros, letras = lista("numeros"), lista("letras")
        if not numeros and not letras:
            return None
        return {"eixo_g": g, "perp_g": p, "numeros": numeros, "letras": letras,
                "z_base": float(d.get("z_base") or 0.0), "origem": str(d.get("origem") or "usuario"),
                "fonte_letras": str(d.get("fonte_letras") or "")}
    except (KeyError, TypeError, ValueError):
        return None


def segmentos(eixos: dict, folga: float = FOLGA_EIXO) -> List[dict]:
    """As linhas dos eixos em 3D (z = z_base): {"nome", "tipo": "numero"|"letra", "a", "b"}.
    O eixo numerado corre atravessado, do primeiro ao último eixo com letra (mais a folga);
    o eixo com letra corre ao longo do galpão, do primeiro ao último numerado."""
    g, p = eixos["eixo_g"], eixos["perp_g"]
    z = float(eixos.get("z_base") or 0.0)
    gs = [e["pos"] for e in eixos["numeros"]] or [0.0]
    ps = [e["pos"] for e in eixos["letras"]] or [0.0]
    g0, g1 = min(gs) - folga, max(gs) + folga
    p0, p1 = min(ps) - folga, max(ps) + folga
    saida = []
    for e in eixos["numeros"]:
        a = (g[0] * e["pos"] + p[0] * p0, g[1] * e["pos"] + p[1] * p0, z)
        b = (g[0] * e["pos"] + p[0] * p1, g[1] * e["pos"] + p[1] * p1, z)
        saida.append({"nome": e["nome"], "tipo": "numero", "a": a, "b": b})
    for e in eixos["letras"]:
        a = (g[0] * g0 + p[0] * e["pos"], g[1] * g0 + p[1] * e["pos"], z)
        b = (g[0] * g1 + p[0] * e["pos"], g[1] * g1 + p[1] * e["pos"], z)
        saida.append({"nome": e["nome"], "tipo": "letra", "a": a, "b": b})
    return saida
