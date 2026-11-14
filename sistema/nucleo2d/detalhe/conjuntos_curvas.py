# -*- coding: utf-8 -*-
"""Trechos curvos, chanfros e emendas do contorno.

Parte do detalhamento dos conjuntos (nucleo2d/detalhe/conjuntos.py é a fachada; dividido do conjuntos.py em
13/11/2026, sem mudar a lógica)."""
import collections
import heapq
import math
import re
import threading
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from nucleo.base import ErroDeDados
from nucleo3d.modelo import Documento, Solido, Chapa
from nucleo2d.desenho import Desenho, Linha, Polilinha, Texto
from nucleo2d.desenho import Cota as _Cota
from nucleo2d import vistas as _vistas
from saida.detalhamento import (Posicao, Furo, analisar, CLASSES, _vista, _desenhar_furos, RHO_ACO, _area_2d,
                                _arestas_dos_furos, _ordem_natural, _autovetores, _lacos_2d)
from saida.desenhos import _mm
from saida.dobras import com_bitola, com_bitola_e_mm

from nucleo2d.detalhe.base import (
    parafusos_posicionados, largura_da_chamada,  # noqa: E402
    ALTURA_CHAMADA,
    ALTURA_COTA,
    CAMADAS_PECAS,
    TIPOS_NOME,
    _Papel,
    _caixa,
    _cruz,
    _dot,
    _eh_redonda_perfil,
    _eixo_da_peca,
    _marcas,
    _norm,
    _registrar_camadas_de_pecas,
    _sub,
    _tipo_ifc,
    parafusos_no_conjunto)


def _trechos_curvos(pts: Sequence[Tuple[float, float]], fechada: bool) -> List[Tuple[int, int]]:
    """Índices (i, j) dos trechos em arco da polilinha: quatro ou mais segmentos curtos
    seguidos virando para o mesmo lado. Os índices são os vértices reto-antes e
    reto-depois do arco."""
    n = len(pts)
    if n < 6:
        return []
    segs = [(pts[(k + 1) % n][0] - pts[k][0], pts[(k + 1) % n][1] - pts[k][1]) for k in range(n if fechada else n - 1)]
    comp = [math.hypot(*s) for s in segs]
    if not comp:
        return []
    curto = 0.4 * max(comp)

    def giro(k):                       # ângulo entre o segmento k e o k+1, em graus com sinal
        a, b = segs[k % len(segs)], segs[(k + 1) % len(segs)]
        la, lb = comp[k % len(segs)], comp[(k + 1) % len(segs)]
        if la < 1e-6 or lb < 1e-6:
            return 0.0
        return math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))

    ns = len(segs)
    limite = ns if fechada else ns - 1
    # polilinha que é só o arco (a silhueta veio partida: o arco separado das retas): não
    # há segmento comprido para os do arco serem "curtos" — todos iguais, virando para o
    # mesmo lado. O trecho é a polilinha inteira; as pontas fazem o papel das retas
    # vizinhas (o chanfro pelas tangentes sai igual ao do contorno inteiro)
    if not fechada and n >= 8:
        giros = [giro(k) for k in range(ns - 1)]
        if max(comp) <= 1.6 * min(comp) and all(1.0 <= abs(g) <= 30.0 for g in giros) \
                and len({1 if g > 0 else -1 for g in giros}) == 1:
            return [(0, n - 1)]
    trechos = []
    k = 0
    while k < limite:
        g = giro(k)
        if abs(g) < 1.0 or abs(g) > 30.0 or comp[(k + 1) % ns] > curto:
            k += 1
            continue
        sinal = 1 if g > 0 else -1
        j = k
        while j + 1 < limite and comp[(j + 1) % ns] <= curto:
            g2 = giro(j + 1)
            if abs(g2) < 1.0 or abs(g2) > 30.0 or (1 if g2 > 0 else -1) != sinal:
                break
            j += 1
        # vértices curvos: k+1 … j+1; retos de cada lado: k e j+2
        if j - k >= 3:
            trechos.append((k, j + 2))
        k = j + 2
    return trechos


#: Folga (mm) do trecho reto além do suporte de terça que ele segura, no chanfro do canto.
FOLGA_CHANFRO_SUPORTE = 100.0


def _dist_ponto_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _avanco_tangente(pts, i, j) -> Tuple[float, float]:
    """Quanto cada trecho reto vizinho do arco pts[i+1..j-1] avança (prolongado) até a
    tangente ao arco no meio dele: (do lado de i, do lado de j). A diagonal entre esses dois
    pontos envolve o arco por fora — a corda cortava por dentro, e a diagonal da treliça que
    chega na face de dentro do arco atravessava o banzo no desenho."""
    a, b = pts[i + 1], pts[j - 1]
    cx, cy = b[0] - a[0], b[1] - a[1]
    cl = math.hypot(cx, cy)
    if cl < 1e-6:
        return 0.0, 0.0
    nx, ny = -cy / cl, cx / cl
    meio = pts[i + 1:j]
    # o vértice do arco mais longe da corda é o meio dele; a tangente ali é paralela à corda
    m = max(meio, key=lambda q: abs((q[0] - a[0]) * nx + (q[1] - a[1]) * ny))
    t2 = (m[0] + cx, m[1] + cy)
    saida = []
    for ponta, longe in ((a, pts[i]), (b, pts[j])):
        x = _cruzamento(longe, ponta, m, t2)
        L = math.dist(ponta, longe)
        if x is None or L < 1e-6:
            saida.append(0.0)
            continue
        volta = ((ponta[0] - longe[0]) / L, (ponta[1] - longe[1]) / L)
        s = (x[0] - ponta[0]) * volta[0] + (x[1] - ponta[1]) * volta[1]
        saida.append(max(0.0, min(s, cl)))
    return saida[0], saida[1]


def _nos_do_arco_puro(pts: Sequence[Tuple[float, float]], direcoes=None):
    """Nós do chanfro de uma polilinha que é só o arco: centro pelo círculo de três pontos
    e tangentes exatas nas pontas — o primeiro e o último segmento do arco são chordas,
    meio passo angular fora da tangente, e prolongá-los deixava o nó uns 30 mm para dentro
    e o trecho até a ponta tombado. Devolve [nó1, nó2] ou None."""
    n = len(pts)
    if n < 5:
        return None
    A, M, E = pts[0], pts[n // 2], pts[-1]
    d = 2.0 * (A[0] * (M[1] - E[1]) + M[0] * (E[1] - A[1]) + E[0] * (A[1] - M[1]))
    if abs(d) < 1e-9:
        return None
    a2, m2, e2 = A[0] ** 2 + A[1] ** 2, M[0] ** 2 + M[1] ** 2, E[0] ** 2 + E[1] ** 2
    cx = (a2 * (M[1] - E[1]) + m2 * (E[1] - A[1]) + e2 * (A[1] - M[1])) / d
    cy = (a2 * (E[0] - M[0]) + m2 * (A[0] - E[0]) + e2 * (M[0] - A[0])) / d

    def tangente(p):
        return (p[0] - (p[1] - cy), p[1] + (p[0] - cx))      # ponto sobre a tangente em p

    def direcao_na_ponta(p, viz, sentido):
        """Direção da reta que sai da ponta, orientada como o arco a percorre: a da reta
        do contorno da mesma peça (o arco puro costuma acabar um ou dois facetados antes
        da tangência, e a tangente ali ainda está inclinada). None sem contorno."""
        c = (viz[0] - p[0], viz[1] - p[1])
        Lc = math.hypot(*c)
        if not direcoes or Lc < 1e-6:
            return None
        c = (c[0] / Lc * sentido, c[1] / Lc * sentido)
        d_ = max(direcoes, key=lambda x: abs(x[0] * c[0] + x[1] * c[1]))
        if abs(d_[0] * c[0] + d_[1] * c[1]) < math.cos(math.radians(20.0)):
            return None
        return d_ if d_[0] * c[0] + d_[1] * c[1] > 0 else (-d_[0], -d_[1])
    t1 = direcao_na_ponta(A, pts[1], 1.0)          # entrando no arco
    t2 = direcao_na_ponta(E, pts[-2], -1.0)        # saindo dele
    if t1 is not None and t2 is not None:
        # a diagonal é a bissetriz das duas retas, tangente ao círculo do lado do arco
        dm = (t1[0] + t2[0], t1[1] + t2[1])
        Ld = math.hypot(*dm)
        if Ld > 1e-6:
            dm = (dm[0] / Ld, dm[1] / Ld)
            nrm = (-dm[1], dm[0])
            R = math.dist(A, (cx, cy))
            if nrm[0] * (M[0] - cx) + nrm[1] * (M[1] - cy) < 0:
                nrm = (-nrm[0], -nrm[1])
            Mt = (cx + nrm[0] * R, cy + nrm[1] * R)
            no1 = _cruzamento(A, (A[0] + t1[0], A[1] + t1[1]), Mt, (Mt[0] + dm[0], Mt[1] + dm[1]))
            no2 = _cruzamento(E, (E[0] + t2[0], E[1] + t2[1]), Mt, (Mt[0] + dm[0], Mt[1] + dm[1]))
            if no1 is not None and no2 is not None:
                return [no1, no2]
    no1 = _cruzamento(A, tangente(A), M, tangente(M))
    no2 = _cruzamento(E, tangente(E), M, tangente(M))
    if no1 is None or no2 is None:
        return None
    return [no1, no2]


def _chanfrar_cantos(desenho: Desenho, novas: List, ids: set, apoios: Sequence = ()) -> List:
    """Troca cada arco das silhuetas das peças `ids` por uma **barra diagonal reta** — o
    chanfro que a fábrica faz, em vez de calandrar. Sem nada apoiado no canto, a diagonal é
    a tangente ao arco no meio dele (`_avanco_tangente`): os trechos retos se prolongam até
    ela e o banzo envolve o arco por fora, sem que a diagonal da treliça que chega no canto
    o atravesse. Quando um suporte de terça (`apoios`: caixas 2D das chapas) encosta no
    trecho reto logo depois do arco, esse trecho avança sobre o arco até passar do suporte
    com folga (FOLGA_CHANFRO_SUPORTE), e a diagonal vai do começo do arco até ali: o
    suporte não fica "voando" sobre a diagonal. Vale para a peça que é só o arco e para o
    arco no meio de uma silhueta fechada. O 3D fica com o arco do modelo.
    """
    saida = list(novas)
    preparadas = []
    recuos: Dict[tuple, float] = {}              # (peça, direção do trecho reto) → avanço
    direcoes: Dict[str, list] = {}               # peça → direções das retas junto ao arco (do contorno fechado)

    def trechos_de(e):
        pts = [tuple(p) for p in e.vertices]
        n = len(pts)
        if n < 6:
            return pts, []
        # numa polilinha fechada, gira a lista até nenhum arco atravessar a emenda dela
        trechos = _trechos_curvos(pts, e.fechada)
        if e.fechada:
            for _ in range(n):
                if all(j < n for _, j in trechos):
                    break
                pts = pts[1:] + pts[:1]
                trechos = _trechos_curvos(pts, True)
        return pts, trechos

    def corda_do_arco(pts, i, j):
        a, b = min(i + 1, len(pts) - 1), max(min(j, len(pts)) - 1, 0)
        return math.dist(pts[a], pts[b])
    # o joelho de cada peça: o maior arco dela. Arco bem menor (a transição curta do banzo
    # para o joelho) não é canto e fica como o modelo traz
    maior: Dict[str, float] = {}
    for e in novas:
        if isinstance(e, Polilinha) and (e.atributos or {}).get("origem") in ids:
            pts, trechos = trechos_de(e)
            for i, j in trechos:
                o_ = (e.atributos or {}).get("origem")
                maior[o_] = max(maior.get(o_, 0.0), corda_do_arco(pts, i, j))
    for e in novas:
        if not isinstance(e, Polilinha) or (e.atributos or {}).get("origem") not in ids:
            continue
        pts, trechos = trechos_de(e)
        n = len(pts)
        origem = (e.atributos or {}).get("origem")
        todos = trechos
        trechos = [(i, j) for i, j in todos if corda_do_arco(pts, i, j) >= FRACAO_JOELHO * maior.get(origem, 0.0)]
        # os arcos pequenos (transição do banzo para o joelho) viram a reta entre as pontas
        pequenos = [t for t in todos if t not in trechos]
        if not trechos and not pequenos:
            continue
        preparadas.append((e, pts, trechos, origem, pequenos))
        if not (len(trechos) == 1 and trechos[0][0] == 0 and trechos[0][1] == n - 1 and not e.fechada):
            # as direções das retas junto ao arco (de qualquer polilinha que as tenha, aberta
            # ou fechada), para as arestas que vierem só como arco
            for i, j in trechos:
                if j < n and j - i >= 3:
                    for p_, q_ in ((pts[i], pts[i + 1]), (pts[j - 1], pts[j])):
                        L_ = math.dist(p_, q_)
                        if L_ > 1e-6:
                            direcoes.setdefault(origem, []).append(((q_[0] - p_[0]) / L_, (q_[1] - p_[1]) / L_))
        # quanto cada trecho reto vizinho do arco precisa avançar para segurar um suporte
        for i, j in trechos:
            if j >= len(pts) or j - i < 3:
                continue
            corda = math.dist(pts[i + 1], pts[j - 1])
            for ponta, longe in ((pts[j - 1], pts[j]), (pts[i + 1], pts[i])):
                L = math.dist(ponta, longe)
                if L < 1e-6:
                    continue
                volta = ((ponta[0] - longe[0]) / L, (ponta[1] - longe[1]) / L)   # do reto para dentro do arco
                s = 0.0
                for (x0, y0, x1, y1) in apoios:
                    cantos = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                    if min(_dist_ponto_seg(q, ponta, longe) for q in cantos) > 60.0:
                        continue
                    alem = max((q[0] - ponta[0]) * volta[0] + (q[1] - ponta[1]) * volta[1] for q in cantos)
                    if alem > -FOLGA_CHANFRO_SUPORTE:
                        s = max(s, alem + FOLGA_CHANFRO_SUPORTE)
                if s > 0:
                    chave = (origem, round(math.degrees(math.atan2(volta[1], volta[0])) / 5.0))
                    recuos[chave] = min(max(recuos.get(chave, 0.0), s), 0.8 * corda)
    for e, pts, trechos, origem, pequenos in preparadas:
        mudou = False
        nos_e = []                                  # as pontas da diagonal: os nós do chanfro
        for i, j in sorted(trechos + pequenos, reverse=True):
            if j >= len(pts) or j - i < 3:
                continue
            if (i, j) in pequenos:
                pts = pts[:i + 2] + pts[j - 1:]          # só as pontas do arco: a reta entre elas
                mudou = True
                continue
            # o arco vai de pts[i+1] a pts[j-1] (pts[i] e pts[j] são as outras pontas dos
            # trechos retos vizinhos): os vértices do meio saem, fica a diagonal
            a, b = pts[i + 1], pts[j - 1]
            # polilinha que é só o arco (as arestas das abas vindas separadas do contorno):
            # nós pelas tangentes exatas
            novos = _nos_do_arco_puro(pts, direcoes.get(origem)) if (i == 0 and j == len(pts) - 1 and not e.fechada) else None
            if novos is None:
                tangente = _avanco_tangente(pts, i, j)
                novos = []
                for k_, (ponta, longe) in enumerate(((a, pts[i]), (b, pts[j]))):
                    L = math.dist(ponta, longe)
                    volta = ((ponta[0] - longe[0]) / L, (ponta[1] - longe[1]) / L) if L > 1e-6 else (0.0, 0.0)
                    s = recuos.get((origem, round(math.degrees(math.atan2(volta[1], volta[0])) / 5.0)), 0.0)
                    s = max(s, tangente[k_])
                    novos.append((ponta[0] + volta[0] * s, ponta[1] + volta[1] * s))
            pts = pts[:i + 1] + novos + pts[j:]
            nos_e += novos
            mudou = True
        if not mudou:
            continue
        e.vertices = [(round(x, 2), round(y, 2)) for x, y in pts]
        if nos_e:
            e.atributos = dict(e.atributos or {}, chanfro="diagonal",
                               nos_chanfro=[[round(x, 2), round(y, 2)] for x, y in nos_e])
    return saida


#: Arco com corda menor que esta fração da do maior arco da mesma peça não é o joelho.
FRACAO_JOELHO = 0.5


def _nos_das_quebras(novas: List, ids: set, giro_minimo: float = 2.0) -> None:
    """Peça quebrada em retas no 3D: cada linha dela ganha `nos_chanfro` nas quinas (o
    vértice interno onde a direção muda), como `_chanfrar_cantos` faz na peça com arco."""
    for e in novas:
        if not isinstance(e, Polilinha) or (e.atributos or {}).get("origem") not in ids or (e.atributos or {}).get("nos_chanfro"):
            continue
        pts = [tuple(p) for p in e.vertices]
        n = len(pts)
        nos = []
        for k in range(n):
            if not e.fechada and (k == 0 or k == n - 1):
                continue
            a, b, c = pts[k - 1], pts[k], pts[(k + 1) % n]
            u = (b[0] - a[0], b[1] - a[1])
            v = (c[0] - b[0], c[1] - b[1])
            lu, lv = math.hypot(*u), math.hypot(*v)
            if lu < 1e-6 or lv < 1e-6:
                continue
            cosang = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (lu * lv)))
            if math.degrees(math.acos(cosang)) >= giro_minimo:
                nos.append([round(b[0], 2), round(b[1], 2)])
        if nos:
            e.atributos = dict(e.atributos or {}, chanfro="quebra", nos_chanfro=nos)


#: Distância (mm) entre o nó do contorno de fora e o de dentro do mesmo perfil, para a
#: linha de emenda que atravessa o perfil; e o maior trecho reto que o banzo absorve.
EMENDA_MAX = 160.0


TRECHO_RETO_MAX = 1000.0


def _emendas_do_chanfro(desenho: Desenho, novas: List, ids: set, camada_de: Dict[str, str]) -> None:
    """Depois do chanfro, o canto da tesoura é feito de peças retas, como a fábrica monta:
    o banzo vai reto **até o nó** onde começa a diagonal do canto (o trecho reto curto da
    barra calandrada passa a ser do banzo), e cada nó ganha a **linha de emenda**
    atravessando o perfil (do contorno de fora ao de dentro)."""
    def perto(a, b, tol=3.0):
        return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol
    canto = [e for e in novas if isinstance(e, Polilinha) and (e.atributos or {}).get("nos_chanfro")]
    if not canto:
        return
    # A peça quebrada em retas no 3D (Cantos redondos) já vem do modelo como a fábrica
    # monta — o joelho termina no nó em meia-esquadria e o banzo já foi esticado até ele —,
    # então só ganha a linha de emenda; mexer nas pontas do banzo aqui torcia as linhas
    # (a aba ia parar no contorno de baixo e cruzava o perfil até a cumeeira).
    moveis = [e for e in canto if (e.atributos or {}).get("chanfro") != "quebra"]
    outras = [e for e in novas if isinstance(e, (Polilinha, Linha)) and (e.atributos or {}).get("origem") not in ids]
    banzos = [e for e in outras if e.camada == "BANZOS"]

    def vertices(e):
        return list(e.vertices) if isinstance(e, Polilinha) else [e.a, e.b]
    # 1) o banzo avança até o nó: o trecho reto entre o nó e a ponta que encosta no banzo sai.
    # Primeiro decide tudo com as posições originais (a ponta do banzo é a mesma para as
    # várias linhas da peça), depois move.
    juncoes = [w for b_ in banzos for w in vertices(b_)]
    movimentos = []                                  # (ponta antiga m, nó q)
    for e in moveis:
        nos = [tuple(q) for q in e.atributos["nos_chanfro"]]
        vs = [tuple(q) for q in e.vertices]
        n = len(vs)
        eh_no = [any(perto(q, no_, 0.05) for no_ in nos) for q in vs]
        junta = [not eh_no[k] and any(perto(q, w) for w in juncoes) for k, q in enumerate(vs)]
        # sequências de vértices da emenda antiga com o banzo (o trecho reto curto) que
        # encostam num nó: saem, e a linha passa a ligar o nó ao próximo nó (a emenda) ou
        # termina no nó
        tirar = set()
        k = 0
        while k < n:
            if not junta[k]:
                k += 1
                continue
            ini = k
            while k < n and junta[k]:
                k += 1
            fim = k - 1                               # a sequência é ini..fim
            antes = ini - 1 if ini > 0 else (n - 1 if e.fechada else None)
            depois = fim + 1 if fim + 1 < n else (0 if e.fechada else None)
            bordas = [b for b in (antes, depois) if b is not None and eh_no[b]]
            if not bordas:
                continue
            if any(min(math.dist(vs[r], vs[b]) for b in bordas) > TRECHO_RETO_MAX for r in range(ini, fim + 1)):
                continue
            for r in range(ini, fim + 1):
                tirar.add(r)
                movimentos.append((vs[r], min((vs[b] for b in bordas), key=lambda q: math.dist(q, vs[r]))))
        if tirar:
            e.vertices = [v for r, v in enumerate(vs) if r not in tirar]
    # a ponta antiga m (emenda com o banzo) vai para o nó nas linhas do banzo: para o nó
    # mais perto dela entre os que a apontaram (contorno de fora ou de dentro)
    # a linha de emenda de cada nó: o par dele (o nó do outro contorno da mesma peça, a
    # menos de EMENDA_MAX). O banzo termina nela, em meia-esquadria com a peça do canto
    todos_nos = [(float(q[0]), float(q[1])) for e in moveis for q in e.atributos["nos_chanfro"]]

    def par_do_no(q):
        cand = [(math.dist(q, r), r) for r in todos_nos if 5.0 < math.dist(q, r) <= EMENDA_MAX]
        return min(cand)[1] if cand else None

    compridas: Dict[tuple, list] = collections.defaultdict(list)   # nó → [(ponta de longe, ponta nova)]

    def destino(w, longe=None):
        cand = [(math.dist(w, q), q) for m, q in movimentos if perto(w, m)]
        if not cand:
            return w
        q = min(cand)[1]
        if longe is None or math.dist(w, longe) < 1e-6:
            return q
        # linha comprida do banzo (anda na própria direção): termina onde cruza a linha de
        # emenda — o contorno de fora cai no nó de fora, o de dentro no de dentro, a aba no
        # meio; a ponta do banzo fica colada na peça do canto
        par = par_do_no(q)
        L0 = math.dist(w, longe)
        d0 = ((w[0] - longe[0]) / L0, (w[1] - longe[1]) / L0)
        mv0 = math.dist(w, q)
        if par is not None and mv0 > 1e-6 and                 abs(((q[0] - w[0]) * d0[0] + (q[1] - w[1]) * d0[1]) / mv0) >= math.cos(math.radians(15.0)):
            x = _cruzamento(longe, w, q, par)
            if x is not None and math.dist(x, q) <= EMENDA_MAX + 20.0:
                x = (round(x[0], 2), round(x[1], 2))
                compridas[q].append((longe, x))
                return x
        # a ponta desliza na direção da própria linha até a altura do nó: a linha da aba,
        # que não passa pelo nó, ia girar em volta da outra ponta (o banzo "torcia")
        L = math.dist(w, longe)
        d = ((w[0] - longe[0]) / L, (w[1] - longe[1]) / L)
        mv = math.dist(w, q)
        # só desliza quem anda na própria direção (as linhas compridas do banzo); a tampa da
        # ponta, curta e atravessada, vai inteira até o nó — deslizando ao longo dela mesma
        # ela ficava no lugar antigo e a ponta do banzo desmanchava
        if mv < 1e-6 or abs(((q[0] - w[0]) * d[0] + (q[1] - w[1]) * d[1]) / mv) < math.cos(math.radians(15.0)):
            return q
        t = (q[0] - longe[0]) * d[0] + (q[1] - longe[1]) * d[1]
        return (round(longe[0] + d[0] * t, 2), round(longe[1] + d[1] * t, 2))
    if movimentos:
        for o in outras:
            if o.camada == "CHAPAS":
                continue
            if isinstance(o, Polilinha):
                vs = list(o.vertices)
                n = len(vs)
                novos = []
                for k, w in enumerate(vs):
                    viz = [vs[j % n] for j in (k - 1, k + 1) if (0 <= j < n) or o.fechada]
                    longe = max(viz, key=lambda x: math.dist(x, w)) if viz else None
                    novos.append(destino(w, longe))
                o.vertices = novos
            else:
                o.a, o.b = destino(o.a, o.b), destino(o.b, o.a)
        _quinas_da_emenda(moveis, outras, compridas, par_do_no, perto)
    # 2) a linha de emenda em cada nó: o nó do contorno de fora com o do de dentro
    por_origem: Dict[str, list] = collections.defaultdict(list)
    candidatos: Dict[str, list] = collections.defaultdict(list)
    for e in canto:
        antigos = [(float(q[0]), float(q[1])) for q in e.atributos["nos_chanfro"]]
        for k, q in enumerate(e.atributos.get("nos_quina") or e.atributos["nos_chanfro"]):
            q = (float(q[0]), float(q[1]))
            movido = k < len(antigos) and math.dist(q, antigos[k]) > 0.05
            candidatos[e.atributos.get("origem")].append((not movido, q))
    for origem, cand in candidatos.items():
        lista = por_origem[origem]
        # o nó que foi para a quina vale mais; outro nó a menos de 12 mm dele é o mesmo
        # (a ponta da linha de aba da peça do canto)
        for _, q in sorted(cand, key=lambda t: t[0]):
            if not any(math.dist(q, w) < 12.0 for w in lista):
                lista.append(q)
    for origem, nos in por_origem.items():
        usados = set()
        pares = sorted(((math.dist(nos[i], nos[j]), i, j) for i in range(len(nos)) for j in range(i + 1, len(nos))))
        for dd, i, j in pares:
            if i in usados or j in usados or not (5.0 < dd <= EMENDA_MAX):
                continue
            usados |= {i, j}
            desenho.add(Linha(camada=camada_de.get(origem, "VISTA"), a=nos[i], b=nos[j],
                              atributos=dict(next(e for e in canto if e.atributos.get("origem") == origem).atributos,
                                             emenda=True, chanfro=None, nos_chanfro=None, nos_quina=None)))


def _quinas_da_emenda(canto, outras, compridas, par_do_no, perto) -> None:
    """Fecha a meia-esquadria do banzo com a peça do canto: em cada nó, a quina é o
    cruzamento da linha de contorno do banzo (a comprida mais perto do nó) com o lado da
    peça do canto que chega nele — no modelo as faces não se encontram exatamente no nó, e
    sobrava um degrau de alguns milímetros. O nó da peça do canto, a tampa do banzo e a
    linha da aba (que termina na emenda entre as duas quinas) acompanham."""
    quina: Dict[tuple, tuple] = {}
    lado: Dict[tuple, tuple] = {}
    for e in canto:
        vs = [tuple(v) for v in e.vertices]
        n = len(vs)
        for k, v in enumerate(vs):
            q = next((q for q in compridas if perto(v, q, 0.05)), None)
            if q is None:
                continue
            viz = [vs[j % n] for j in (k - 1, k + 1) if (0 <= j < n) or e.fechada]
            if viz:
                lado[q] = max(viz, key=lambda x: math.dist(x, v))
    for q, lista in compridas.items():
        if q not in lado or not lista:
            continue
        # a linha de contorno do banzo é a que passa mais perto do nó
        def afastamento(item):
            longe, x = item
            L = math.dist(longe, x)
            return abs((q[0] - longe[0]) * (x[1] - longe[1]) - (q[1] - longe[1]) * (x[0] - longe[0])) / L if L > 1e-6 else 1e9
        longe, x = min(lista, key=afastamento)
        X = _cruzamento(longe, x, lado[q], q)
        if X is not None and math.dist(X, q) <= 40.0:
            quina[q] = (round(X[0], 2), round(X[1], 2))
    if not quina:
        return

    def nova(w):
        for q, X in quina.items():
            if perto(w, q, 0.05):
                return X
        return w
    # pontas novas das linhas compridas: o contorno vai para a quina; as outras (a aba)
    # terminam na emenda entre as duas quinas
    troca_ponta: Dict[tuple, tuple] = {}
    for q, lista in compridas.items():
        par = par_do_no(q)
        a_ = quina.get(q, q)
        b_ = quina.get(par, par) if par is not None else None
        for longe, x in lista:
            if q in quina and math.dist(x, a_) < 1e-9:
                continue
            if b_ is None:
                continue
            X = _cruzamento(longe, x, a_, b_)
            if X is not None and math.dist(X, x) <= 40.0:
                troca_ponta[x] = (round(X[0], 2), round(X[1], 2))
        # a de contorno
        if q in quina:
            longe, x = min(lista, key=lambda it: math.dist(it[1], quina[q]))
            troca_ponta[x] = quina[q]

    def ajuste(w):
        w2 = troca_ponta.get(tuple(w))
        return w2 if w2 is not None else nova(tuple(w))
    for o in outras:
        if o.camada == "CHAPAS":
            continue
        if isinstance(o, Polilinha):
            o.vertices = [ajuste(w) for w in o.vertices]
        else:
            o.a, o.b = ajuste(o.a), ajuste(o.b)
    # as emendas (quina de fora – quina de dentro): a linha de aba da peça do canto, que
    # tem o nó dela a poucos milímetros do de fora, também termina na emenda
    emendas = []
    for q, X in quina.items():
        par = par_do_no(q)
        if par is not None and par in quina:
            emendas.append((X, quina[par]))

    def na_emenda(v, viz):
        for a_, b_ in emendas:
            L = math.dist(a_, b_)
            if L < 1e-6:
                continue
            dist_ = abs((v[0] - a_[0]) * (b_[1] - a_[1]) - (v[1] - a_[1]) * (b_[0] - a_[0])) / L
            if dist_ > 15.0 or min(math.dist(v, a_), math.dist(v, b_)) > L + 15.0:
                continue
            X = _cruzamento(viz, v, a_, b_)
            if X is not None and math.dist(X, v) <= 20.0:
                return (round(X[0], 2), round(X[1], 2))
        return v
    for e in canto:
        vs = [tuple(v) for v in e.vertices]
        n = len(vs)
        nos = [(float(a), float(b)) for a, b in e.atributos["nos_chanfro"]]
        movidos = {}
        novos = []
        for k, v in enumerate(vs):
            w = nova(v)
            if w == v and any(perto(v, q, 0.05) for q in nos):
                viz = [vs[j % n] for j in (k - 1, k + 1) if (0 <= j < n) or e.fechada]
                if viz:
                    w = na_emenda(v, max(viz, key=lambda x: math.dist(x, v)))
            if w != v:
                movidos[v] = w
            novos.append(w)
        e.vertices = novos
        e.atributos = dict(e.atributos, nos_quina=[list(movidos.get(q, nova(q))) for q in nos])


def _so_bordas_externas(desenho: Desenho, entidades: Sequence, ids_barras: set, camada_de: Dict[str, str]) -> None:
    """Na elevação do conjunto, cada barra fica só com o contorno de fora do perfil: a aresta de
    dentro (a espessura do U, a outra aba da cantoneira), que saía como uma segunda linha colada na
    borda, e a cópia fina da borda saem (pedido do usuário, 28/09 — o padrão do corte das tesouras
    do projetista). Uma linha é borda quando a peça inteira fica de um lado dela, no trecho que ela
    ocupa; a de dentro tem peça dos dois lados. As linhas de emenda do canto ficam."""
    por: Dict[str, list] = collections.defaultdict(list)
    for e in entidades:
        a = e.atributos or {}
        if a.get("origem") in ids_barras and isinstance(e, (Linha, Polilinha)) and e.camada not in ("FURO", "EIXO") \
                and not a.get("emenda"):
            por[a["origem"]].append(e)
    for origem, ents in por.items():
        segs = []
        for e in ents:
            if isinstance(e, Linha):
                segs.append((tuple(e.a), tuple(e.b), e))
            else:
                v = [tuple(q) for q in e.vertices] + ([tuple(e.vertices[0])] if e.fechada and len(e.vertices) > 2 else [])
                segs += [(v[i], v[i + 1], e) for i in range(len(v) - 1)]
        segs = [s for s in segs if math.dist(s[0], s[1]) > 0.5]

        def borda(a_, b_):
            """a peça inteira de um lado da linha, no trecho dela: cada outra linha da peça é
            recortada no trecho (a face do outro lado do joelho atravessa o trecho sem ter ponta
            dentro dele) e conta o lado de cada ponta do pedaço"""
            L = math.dist(a_, b_)
            tx, ty = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
            lado = set()
            for c_, d_, _e in segs:
                sc = (c_[0] - a_[0]) * tx + (c_[1] - a_[1]) * ty
                sd = (d_[0] - a_[0]) * tx + (d_[1] - a_[1]) * ty
                hc = -(c_[0] - a_[0]) * ty + (c_[1] - a_[1]) * tx
                hd = -(d_[0] - a_[0]) * ty + (d_[1] - a_[1]) * tx
                lo, hi = 1.0, L - 1.0
                if max(sc, sd) < lo or min(sc, sd) > hi:
                    continue
                if abs(sd - sc) < 1e-9:
                    amostras = [hc, hd]
                else:
                    amostras = []
                    for s_lim in (max(min(sc, sd), lo), min(max(sc, sd), hi)):
                        f = (s_lim - sc) / (sd - sc)
                        amostras.append(hc + (hd - hc) * f)
                for h in amostras:
                    if abs(h) > 0.3:
                        lado.add(h > 0)
                        if len(lado) == 2:
                            return False
            return True

        manter: List[tuple] = []
        # as linhas grossas primeiro: a cópia fina de uma borda já mantida não entra de novo
        for a_, b_, e in sorted(segs, key=lambda s: s[2].camada == "VISTA-FINA"):
            if not borda(a_, b_):
                continue
            L = math.dist(a_, b_)
            tx, ty = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
            repetida = False
            for c_, d_, _e in manter:
                # a mesma borda (colada e paralela, cobrindo este trecho)
                if max(abs(-(q[0] - c_[0]) * ((d_[1] - c_[1]) / max(math.dist(c_, d_), 1e-9))
                           + (q[1] - c_[1]) * ((d_[0] - c_[0]) / max(math.dist(c_, d_), 1e-9))) for q in (a_, b_)) <= 0.3:
                    s0, s1 = sorted(((q[0] - c_[0]) * tx + (q[1] - c_[1]) * ty) for q in (c_, d_))
                    sa, sb = sorted(((q[0] - c_[0]) * tx + (q[1] - c_[1]) * ty) for q in (a_, b_))
                    if sa >= s0 - 0.5 and sb <= s1 + 0.5:
                        repetida = True
                        break
            if not repetida:
                manter.append((a_, b_, e))
        for e in ents:
            desenho.remover(e.id)
        for a_, b_, e in manter:
            cam = e.camada if e.camada != "VISTA-FINA" else camada_de.get(origem, "VISTA")
            atr = {k: v for k, v in (e.atributos or {}).items() if k not in ("nos_chanfro", "nos_quina", "chanfro")}
            desenho.add(Linha(camada=cam, a=(round(a_[0], 2), round(a_[1], 2)), b=(round(b_[0], 2), round(b_[1], 2)), atributos=atr))


def _cruzamento(a0, a1, b0, b1):
    """Interseção das retas a0–a1 e b0–b1, ou None se paralelas."""
    r = (a1[0] - a0[0], a1[1] - a0[1])
    s = (b1[0] - b0[0], b1[1] - b0[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((b0[0] - a0[0]) * s[1] - (b0[1] - a0[1]) * s[0]) / den
    return (a0[0] + t * r[0], a0[1] + t * r[1])
