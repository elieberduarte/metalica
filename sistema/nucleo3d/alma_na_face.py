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
