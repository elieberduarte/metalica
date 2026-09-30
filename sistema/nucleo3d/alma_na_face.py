# -*- coding: utf-8 -*-
"""A alma da treliça (montantes e diagonais) para na face interna do banzo.

O nó de cálculo fica no eixo do banzo (é por ele que o esqueleto e as regras de apoio ligam as
barras), mas a peça de verdade termina antes: a ponta reta com a quina livre da face do banzo e
uma folga. É o `recorte_inicio`/`recorte_fim` da barra — o 3D, o IFC, o peso e a lista de corte já
contam com ele; `inicio`/`fim` continuam no nó.

Para cada ponta de alma que chega num banzo do mesmo bloco (a treliça; `origem.peca`): na direção
do plano da treliça perpendicular ao banzo, apontando para a alma, a face do banzo está a
`a_max` do nó (a seção girada do banzo, e o caixão com os dois U); a quina da ponta da alma mais
perto do banzo está a `t·(d·p) + min(seção·p)` — a ponta anda até essa quina passar a face mais a
folga."""
import math
import re
from collections import defaultdict
from types import SimpleNamespace
from typing import Dict, Iterable, List, Optional, Tuple

from nucleo3d.geometria import base_local, secao
from nucleo3d.modelo import Barra

FOLGA = 10.0            # mm entre a ponta da alma e a face do banzo
PERTO = 450.0           # mm: o banzo "do nó" passa a até isso da ponta da alma (o caixão tem o eixo fora do nó)
ATRAS = 100.0           # mm: o eixo do banzo do nó fica atrás da ponta (o U de dentro do caixão, a ~50 mm à frente)
MAX_FRACAO = 0.35       # não recorta mais que isso do comprimento em cada ponta (a leitura estranha fica como está)

ALMA = ("montante", "diagonal")


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _unit(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


_SEC: Dict[str, List[Tuple[float, float]]] = {}


def _pontos_da_secao(perfil) -> Optional[List[Tuple[float, float]]]:
    if perfil not in _SEC:
        _SEC[perfil] = None
        for como in (lambda n: n, _do_catalogo):        # o banco básico e o catálogo (os de chapa dobrada)
            try:
                _SEC[perfil] = [(float(q[0]), float(q[1])) for q in secao(como(perfil))]
                break
            except Exception:                           # noqa: BLE001 — perfil fora do banco: sem recorte
                continue
    return _SEC[perfil]


def _do_catalogo(nome):
    from nucleo import catalogo
    pa = catalogo.perfil_de(nome)
    if pa is None:
        raise KeyError(nome)
    return pa


def _extremo(barra, direcao, menor=False) -> Optional[float]:
    """o maior (ou menor) avanço da seção da barra na direção dada (perpendicular ao eixo dela)"""
    pts = _pontos_da_secao(barra.perfil)
    if not pts:
        return None
    u, v, _w = base_local(_sub(barra.fim, barra.inicio), float(barra.rotacao or 0.0))
    pu, pv = _dot(u, direcao), _dot(v, direcao)
    vals = [x * pu + y * pv for x, y in pts]
    return min(vals) if menor else max(vals)


def recorte_da_ponta(alma, ponta: int, banzos: Iterable, folga: float = FOLGA) -> float:
    """quanto a ponta (0 = inicio, 1 = fim) da barra de alma recua para ficar fora dos banzos"""
    E = tuple(alma.inicio if ponta == 0 else alma.fim)
    O = tuple(alma.fim if ponta == 0 else alma.inicio)
    L = math.dist(E, O)
    if L < 1.0:
        return 0.0
    d = _unit(_sub(O, E))                               # da ponta para dentro da alma
    melhor = 0.0
    for b in banzos:
        a0, a1 = tuple(b.inicio), tuple(b.fim)
        Lb = math.dist(a0, a1)
        if Lb < 1.0:
            continue
        c = _unit(_sub(a1, a0))
        s = _dot(_sub(E, a0), c)
        if s < -PERTO or s > Lb + PERTO:
            continue
        pe = _sub(E, _sub(a0, _mul(c, -s)))              # da linha do banzo até a ponta
        dist = math.sqrt(_dot(pe, pe))
        if dist > PERTO:
            continue
        # p: no plano (banzo, alma), perpendicular ao banzo, para o lado da alma
        p = _sub(d, _mul(c, _dot(d, c)))
        np_ = math.sqrt(_dot(p, p))
        if np_ < 0.17:                                  # alma quase paralela ao banzo (< 10°): não é ponta nele
            continue
        p = _mul(p, 1.0 / np_)
        dp = _dot(d, p)
        if _dot(_mul(pe, -1.0), p) > ATRAS:
            continue                                    # o banzo está do lado da alma (o outro banzo da treliça)
        ext_b = _extremo(b, p)
        ext_a = _extremo(alma, p, menor=True)
        if ext_b is None or ext_a is None:
            continue
        # a face do banzo, medida a partir da ponta da alma, na direção p
        face = _dot(_sub(a0, E), p) + ext_b
        if face + folga <= ext_a:
            continue                                    # a alma já termina fora deste banzo
        t = (face + folga - ext_a) / dp
        s_t = s + t * _dot(d, c)
        if s_t < -30.0 or s_t > Lb + 30.0:
            continue                                    # a alma sai pela ponta deste banzo (o toco do apoio)
        if t > melhor:
            melhor = t
    if melhor > MAX_FRACAO * L:
        return 0.0
    return round(melhor, 1)


def aparar(entidades: Iterable, folga: float = FOLGA) -> Dict[str, int]:
    """recorta as pontas das almas nos banzos do mesmo bloco (`atributos.origem.peca`); devolve
    as contagens (pontas recortadas, barras)"""
    # a treliça montada em duas peças (a viga de transição e a tesoura em cima: "NOME (tesoura de
    # cima)#k" e "NOME#k") é um nó só para os banzos: a alma de uma apoia no banzo da outra
    blocos: Dict[str, Dict[str, list]] = defaultdict(lambda: {"banzo": [], "alma": []})
    for b in entidades:
        atr = getattr(b, "atributos", None) or {}
        peca = (atr.get("origem") or {}).get("peca")
        if not peca:
            continue
        chave = re.sub(r" \([^()]*\)(#\d+)$", r"\1", peca)
        if not isinstance(b, Barra):
            # o banzo calandrado (sólido varrido): cada trecho do eixo vale como um banzo reto
            bz = atr.get("banzo") or {}
            eixo = bz.get("eixo") or []
            for q0, q1 in zip(eixo, eixo[1:]):
                blocos[chave]["banzo"].append(SimpleNamespace(inicio=tuple(q0), fim=tuple(q1), perfil=bz.get("perfil"),
                                                              rotacao=bz.get("rotacao") or 0.0, papel="banzo"))
            continue
        if b.papel == "banzo":
            blocos[chave]["banzo"].append(b)
        elif b.papel in ALMA:
            blocos[chave]["alma"].append(b)
    res = {"pontas": 0, "barras": 0}
    for g in blocos.values():
        if not g["banzo"]:
            continue
        for a in g["alma"]:
            r0 = recorte_da_ponta(a, 0, g["banzo"], folga)
            r1 = recorte_da_ponta(a, 1, g["banzo"], folga)
            if r0 + r1 >= math.dist(tuple(a.inicio), tuple(a.fim)) - 20.0:
                continue
            if r0 or r1:
                a.recorte_inicio, a.recorte_fim = r0, r1
                res["pontas"] += (1 if r0 else 0) + (1 if r1 else 0)
                res["barras"] += 1
    return res


# ------------------------------------------------------------------ o encaixe de fábrica
# O corte reto acima deixa a quina livre da face: a ponta fica no ar de um lado. Na fábrica a
# alma é cortada no ângulo: deita na face do banzo (meia-esquadria) e, no nó com montante, a
# diagonal ganha um segundo corte encostado nele (o bico); duas diagonais no mesmo nó sem
# montante se cortam na bissetriz. A face é a do banzo NA FAIXA da alma (a largura dela fora
# do plano da treliça): a alma estreita entra na boca do U e para na alma dele (a L dupla
# soldada nas paredes); a larga para na ponta das abas. Tudo vai em `cortes_inicio`/`cortes_fim`
# da barra (planos; o 3D, o IFC, o peso e a lista de corte já contam com eles).

FOLGA_ENCAIXE = 0.0     # mm: a solda é encostada
NO = 200.0              # mm: pontas de alma a menos disso, no mesmo banzo, são do mesmo nó
BORDA = 0.5             # mm: a faixa da alma encolhida, para a parede encostada não contar


def _faixa_e_maximo(barra, origem, eixo_e, lo, hi, direcao) -> Optional[float]:
    """o maior avanço (na `direcao`, a partir de `origem`) da seção da barra dentro da faixa
    lo ≤ e ≤ hi (medida em `eixo_e` a partir de `origem`); None se a seção não passa na faixa"""
    from nucleo3d.geometria import _recortar_convexo      # Sutherland–Hodgman serve ao côncavo
    pts = _pontos_da_secao(barra.perfil)
    if not pts:
        return None
    u, v, _w = base_local(_sub(barra.fim, barra.inicio), float(barra.rotacao or 0.0))
    b0 = _dot(_sub(tuple(barra.inicio), origem), eixo_e)
    eu, ev = _dot(u, eixo_e), _dot(v, eixo_e)
    poli = _recortar_convexo(list(pts), eu, ev, b0 - lo)
    if len(poli) >= 3:
        poli = _recortar_convexo(poli, -eu, -ev, hi - b0)
    if len(poli) < 3:
        return None
    d0 = _dot(_sub(tuple(barra.inicio), origem), direcao)
    du, dv = _dot(u, direcao), _dot(v, direcao)
    return d0 + max(x * du + y * dv for x, y in poli)


def _faixa_da_alma(alma, e) -> Optional[Tuple[float, float]]:
    pts = _pontos_da_secao(alma.perfil)
    if not pts:
        return None
    u, v, _w = base_local(_sub(alma.fim, alma.inicio), float(alma.rotacao or 0.0))
    vals = [x * _dot(u, e) + y * _dot(v, e) for x, y in pts]
    return min(vals), max(vals)


def _face_no_banzo(alma, ponta: int, banzos, folga: float):
    """a ponta da alma no banzo em que ela deita (o de corte mais fundo): {E, d, p, e, face,
    banzo, faixa, t, barra, ponta} ou None"""
    E = tuple(alma.inicio if ponta == 0 else alma.fim)
    O = tuple(alma.fim if ponta == 0 else alma.inicio)
    L = math.dist(E, O)
    if L < 1.0:
        return None
    d = _unit(_sub(O, E))
    melhor = None
    for b in banzos:
        a0, a1 = tuple(b.inicio), tuple(b.fim)
        Lb = math.dist(a0, a1)
        if Lb < 1.0:
            continue
        c = _unit(_sub(a1, a0))
        s = _dot(_sub(E, a0), c)
        if s < -PERTO or s > Lb + PERTO:
            continue
        pe = _sub(E, _sub(a0, _mul(c, -s)))
        if math.sqrt(_dot(pe, pe)) > PERTO:
            continue
        p = _sub(d, _mul(c, _dot(d, c)))
        np_ = math.sqrt(_dot(p, p))
        if np_ < 0.17:
            continue
        p = _mul(p, 1.0 / np_)
        dp = _dot(d, p)
        if _dot(_mul(pe, -1.0), p) > ATRAS:
            continue
        e = _unit((c[1] * p[2] - c[2] * p[1], c[2] * p[0] - c[0] * p[2], c[0] * p[1] - c[1] * p[0]))
        faixa = _faixa_da_alma(alma, e)
        if faixa is None:
            continue
        face = _faixa_e_maximo(b, E, e, faixa[0] + BORDA, faixa[1] - BORDA, p)
        if face is None:
            continue                                    # o banzo não passa na faixa da alma
        fundo = _faixa_e_maximo(b, E, e, -1e9, 1e9, _mul(p, -1.0))
        if face + folga <= 0.0 and (fundo is None or -fundo > 0.0):
            continue                                    # o nó está fora do banzo: a alma não chega nele
        # (a face abaixo do nó é a alma do U por dentro: a alma estreita desce na boca até ela)
        t = (face + folga) / dp
        s_t = s + t * _dot(d, c)
        if s_t < -30.0 or s_t > Lb + 30.0 or t > MAX_FRACAO * L:
            continue
        if melhor is None or t > melhor["t"]:
            melhor = dict(E=E, d=d, p=p, e=e, face=face + folga, banzo=id(b), faixa=faixa, t=t,
                          barra=alma, ponta=ponta)
    return melhor


def _cantos_na_face(r) -> List[Tuple[float, float, float]]:
    """os cantos da seção da alma na face do banzo (a ponta em meia-esquadria)"""
    alma, E, d, p = r["barra"], r["E"], r["d"], r["p"]
    u, v, _w = base_local(_sub(alma.fim, alma.inicio), float(alma.rotacao or 0.0))
    dp = _dot(d, p)
    res = []
    for x, y in _pontos_da_secao(alma.perfil) or ():
        P0 = (E[0] + u[0] * x + v[0] * y, E[1] + u[1] * x + v[1] * y, E[2] + u[2] * x + v[2] * y)
        t = (r["face"] - _dot(_sub(P0, E), p)) / dp
        res.append((P0[0] + d[0] * t, P0[1] + d[1] * t, P0[2] + d[2] * t))
    return res


def _plano(normal, ponto_rel) -> dict:
    return {"normal": [round(c, 9) for c in normal], "ponto": [round(c, 4) for c in ponto_rel]}


def _blocos(entidades):
    blocos: Dict[str, Dict[str, list]] = defaultdict(lambda: {"banzo": [], "alma": []})
    for b in entidades:
        atr = getattr(b, "atributos", None) or {}
        peca = (atr.get("origem") or {}).get("peca")
        if not peca:
            continue
        chave = re.sub(r" \([^()]*\)(#\d+)$", r"\1", peca)
        if not isinstance(b, Barra):
            bz = atr.get("banzo") or {}
            eixo = bz.get("eixo") or []
            for q0, q1 in zip(eixo, eixo[1:]):
                blocos[chave]["banzo"].append(SimpleNamespace(inicio=tuple(q0), fim=tuple(q1), perfil=bz.get("perfil"),
                                                              rotacao=bz.get("rotacao") or 0.0, papel="banzo"))
            continue
        if b.papel == "banzo":
            blocos[chave]["banzo"].append(b)
        elif b.papel in ALMA:
            blocos[chave]["alma"].append(b)
    return blocos


def encaixar(entidades: Iterable, folga: float = FOLGA_ENCAIXE) -> Dict[str, int]:
    """o encaixe de fábrica das almas nos banzos do mesmo bloco (`atributos.origem.peca`): a
    meia-esquadria na face do banzo, o bico no montante vizinho e a bissetriz entre diagonais.
    Troca o recorte reto dessas pontas pelos planos; devolve as contagens."""
    from nucleo3d.geometria import (_normalizar_contorno, _prisma_cortado, alturas_de_corte,
                                    secao_com_furos)
    res = {"pontas": 0, "barras": 0, "bicos": 0, "bissetrizes": 0}
    cos_paralelo = math.cos(math.radians(5.0))
    for g in _blocos(entidades).values():
        if not g["banzo"]:
            continue
        pontas = []
        for a in g["alma"]:
            for k in (0, 1):
                r = _face_no_banzo(a, k, g["banzo"], folga)
                if r:
                    r["planos"] = [_plano(r["p"], _mul(r["p"], r["face"]))]
                    r["com_montante"] = False
                    pontas.append(r)
        # os nós: pontas no mesmo banzo, perto uma da outra, que se cruzam na faixa
        for i, X in enumerate(pontas):
            for Y in pontas[i + 1:]:
                if X["banzo"] != Y["banzo"] or X["barra"] is Y["barra"] or math.dist(X["E"], Y["E"]) > NO:
                    continue
                if abs(_dot(X["d"], Y["d"])) > cos_paralelo:
                    continue                            # paralelas: as duas L da alma dupla, os dois U do tubo
                e = X["e"]
                ex = (_dot(X["E"], e) + X["faixa"][0], _dot(X["E"], e) + X["faixa"][1])
                fy = _faixa_da_alma(Y["barra"], e) or (0.0, 0.0)
                ey = (_dot(Y["E"], e) + fy[0], _dot(Y["E"], e) + fy[1])
                if min(ex[1], ey[1]) - max(ex[0], ey[0]) < 1.0:
                    continue                            # lado a lado fora do plano: não se tocam
                pX, pY = X["barra"].papel, Y["barra"].papel
                if pX != pY:
                    Z, M = (X, Y) if pX == "diagonal" else (Y, X)   # a diagonal encosta no montante
                    m = _unit(_sub(tuple(M["barra"].fim), tuple(M["barra"].inicio)))
                    q = _sub(Z["d"], _mul(m, _dot(Z["d"], m)))
                    if math.sqrt(_dot(q, q)) < 0.17:
                        continue
                    q = _unit(q)
                    faixa = Z["faixa"]
                    face = _faixa_e_maximo(M["barra"], Z["E"], Z["e"], faixa[0] + BORDA, faixa[1] - BORDA, q)
                    if face is None:
                        continue
                    if min(_dot(_sub(P, Z["E"]), q) for P in _cantos_na_face(Z)) >= face + folga - 0.5:
                        continue                        # a diagonal já passa longe do montante
                    Z["planos"].append(_plano(q, _mul(q, face + folga)))
                    Z["com_montante"] = True
                    res["bicos"] += 1
                elif pX == pY == "diagonal":
                    n = _unit(_sub(X["d"], Y["d"]))
                    N = _mul((X["E"][0] + Y["E"][0], X["E"][1] + Y["E"][1], X["E"][2] + Y["E"][2]), 0.5)
                    fura = any(_dot(_sub(P, N), n) < -0.5 for P in _cantos_na_face(X)) or \
                        any(_dot(_sub(P, N), n) > 0.5 for P in _cantos_na_face(Y))
                    if fura:
                        X.setdefault("bissetriz", []).append(_plano(n, _sub(N, X["E"])))
                        Y.setdefault("bissetriz", []).append(_plano(_mul(n, -1.0), _sub(N, Y["E"])))
        # grava: a bissetriz só onde não há montante no nó; a peça que o bico comeria fica só
        # com a meia-esquadria
        mexidas = {}
        for r in pontas:
            extra = [] if r["com_montante"] else r.get("bissetriz", [])
            res["bissetrizes"] += len(extra)
            a = r["barra"]
            if r["ponta"] == 0:
                a.cortes_inicio, a.recorte_inicio = r["planos"] + extra, 0.0
            else:
                a.cortes_fim, a.recorte_fim = r["planos"] + extra, 0.0
            mexidas[id(a)] = a
            res["pontas"] += 1
        for a in mexidas.values():
            try:
                ext, internos = _normalizar_contorno(secao_com_furos(a.perfil))
                if _prisma_cortado(ext, internos, *alturas_de_corte(a)) is None:
                    a.cortes_inicio, a.cortes_fim = a.cortes_inicio[:1], a.cortes_fim[:1]
            except Exception:                           # noqa: BLE001 — perfil fora do banco: fica como está
                pass
            res["barras"] += 1
    return res
