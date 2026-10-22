# -*- coding: utf-8 -*-
"""A peça lida do desenho, posta pela seção real (usuário, SESI Chapecó, 22/10/2026: "pode aplicar" — o MET-1 da
verificação da metálica).

A leitura de prancha dá o eixo da barra no MEIO do contorno desenhado do perfil; o 3D põe o CENTROIDE da seção no eixo.
Em U, Ue e cantoneira o centroide fica perto da alma (Ue 200×75: 23 mm da alma, não 37,5), e a peça saía 11–15 mm para o
lado da boca: a VM caixa de dois Ue boca a boca com os dois entrando 22–30 mm um no outro (121 mm em vez de 150), as
terças 1–3 cm no ar sobre o banzo, as correntes 4–12 cm antes da terça.

* `eixo_pelo_contorno(barras)` — leva cada barra do meio do contorno ao centroide, pela seção do catálogo e pelo giro
  (o deslocamento é o meio da caixa da seção nos eixos locais u e v; nas seções simétricas — W, tubo, barra — é zero).
* as terças assentam no topo real dos banzos com `de_planta._assentar_tercas` (já existente).
* `correntes_ate_a_alma(correntes, tercas)` — cada ponta de corrente vai até a alma da terça que ela encontra: do lado da
  boca, a face de dentro da alma; do lado das costas, a face de fora."""
import math
from typing import Dict, Iterable, List, Optional, Tuple

from nucleo3d.geometria import base_local, secao


def _perfil(nome):
    try:
        from nucleo3d.geometria import resolver_perfil
        return resolver_perfil(nome)
    except Exception:                       # noqa: BLE001
        return None


def meio_do_contorno(perfil: str) -> Tuple[float, float]:
    """(x, y) do meio da caixa da seção, nos eixos locais (u, v), a partir do centroide (0, 0)"""
    p = _perfil(perfil)
    if p is None:
        return 0.0, 0.0
    pts = secao(p)
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


def eixo_pelo_contorno(barras: Iterable, tol: float = 0.5) -> Dict[str, int]:
    """Desloca cada barra do meio do contorno para o centroide (muda inicio/fim). Devolve as contagens."""
    cache: Dict[str, Tuple[float, float]] = {}
    out = {"deslocadas": 0, "simetricas": 0}
    for b in barras:
        perfil = getattr(b, "perfil", None)
        if not perfil:
            continue
        if perfil not in cache:
            cache[perfil] = meio_do_contorno(perfil)
        mx, my = cache[perfil]
        if abs(mx) < tol and abs(my) < tol:
            out["simetricas"] += 1
            continue
        d = tuple(b.fim[i] - b.inicio[i] for i in range(3))
        if math.sqrt(sum(c * c for c in d)) < 1.0:
            continue
        u, v, _w = base_local(d, getattr(b, "rotacao", 0.0) or 0.0)
        s = tuple(-(mx * u[i] + my * v[i]) for i in range(3))
        b.inicio = tuple(b.inicio[i] + s[i] for i in range(3))
        b.fim = tuple(b.fim[i] + s[i] for i in range(3))
        out["deslocadas"] += 1
    return out


def _alma(perfil: str) -> Optional[Tuple[float, float]]:
    """(face de fora, face de dentro) da alma do U/Ue no eixo local u (a boca para +u)"""
    p = _perfil(perfil)
    if p is None:
        return None
    try:
        from nucleo3d.geometria import _dims
        g = _dims(p)
    except Exception:                       # noqa: BLE001
        return None
    if g.get("forma") not in ("U", "Ue"):
        return None
    xmin = min(q[0] for q in secao(p))
    return xmin, xmin + float(g.get("tw") or 2.0)


def correntes_ate_a_alma(correntes: Iterable, tercas: Iterable, alcance: float = 250.0, folga_z: float = 200.0) -> Dict[str, int]:
    """Cada ponta de corrente (barra quase horizontal) até a alma da terça U/Ue mais próxima dela (a até `alcance` mm do eixo
    da terça, em planta, e a até `folga_z` em altura): do lado da boca (+u) a face de dentro, do lado das costas a de fora.
    A ponta anda sobre a reta da corrente. Devolve as contagens."""
    tercas = list(tercas)
    info = []
    for t in tercas:
        al = _alma(t.perfil)
        if al is None:
            continue
        d = tuple(t.fim[i] - t.inicio[i] for i in range(3))
        L = math.hypot(d[0], d[1])
        if L < 1.0:
            continue
        u, _v, _w = base_local(d, getattr(t, "rotacao", 0.0) or 0.0)
        info.append((t, al, u, (d[0] / L, d[1] / L), L))
    out = {"pontas": 0, "sem_terca": 0}
    for c in correntes:
        for ponta in (0, 1):
            e = c.inicio if ponta == 0 else c.fim
            o = c.fim if ponta == 0 else c.inicio
            dc = tuple(o[i] - e[i] for i in range(3))
            Lc = math.hypot(dc[0], dc[1])
            if Lc < 1.0:
                continue
            melhor = None
            for t, al, u, dt, L in info:
                a = t.inicio
                # o eixo da terça em planta: a distância da ponta a ele
                s = (e[0] - a[0]) * dt[0] + (e[1] - a[1]) * dt[1]
                if s < -alcance or s > L + alcance:
                    continue
                px, py = a[0] + dt[0] * s, a[1] + dt[1] * s
                dist = math.hypot(e[0] - px, e[1] - py)
                zt = a[2] + (t.fim[2] - a[2]) * max(0.0, min(1.0, s / L))
                if dist > alcance or abs(e[2] - zt) > folga_z:
                    continue
                # na emenda de duas terças, a que passa sob a ponta vence a que só chega pelo alcance (SESI, CF34)
                chave = (0 if 0.0 <= s <= L else 1, dist)
                if melhor is None or chave < melhor[0]:
                    melhor = (chave, t, al, u, (px, py))
            if melhor is None:
                out["sem_terca"] += 1
                continue
            _dist, t, (fora, dentro), u, (px, py) = melhor
            uh = math.hypot(u[0], u[1])
            if uh < 0.5:
                continue
            ux, uy = u[0] / uh, u[1] / uh
            # de que lado da terça vem a corrente (o lado da outra ponta): +u é o da boca
            lado = (o[0] - px) * ux + (o[1] - py) * uy
            alvo_u = dentro if lado > 0 else fora
            # a ponta na reta da corrente onde a coordenada u (a partir do eixo da terça) vale alvo_u
            ku = (dc[0] * ux + dc[1] * uy) / Lc               # quanto a corrente anda em u por mm em planta
            if abs(ku) < 0.3:
                continue
            ue = (e[0] - px) * ux + (e[1] - py) * uy
            k = (alvo_u - ue) / ku / Lc                         # fração de dc a andar
            nova = tuple(e[i] + dc[i] * k for i in range(3))
            if ponta == 0:
                c.inicio = nova
            else:
                c.fim = nova
            out["pontas"] += 1
    return out
