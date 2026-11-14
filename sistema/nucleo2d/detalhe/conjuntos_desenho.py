# -*- coding: utf-8 -*-
"""O desenho de cada conjunto: vistas, cotas, chamadas de parafusos e de chapas, cores por perfil.

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
from nucleo2d.detalhe.conjuntos_grupos import (  # noqa: E402
    _casco,
    _classificar_pecas_do_conjunto,
    _detalhes_de_furos,
    _eixos_do_conjunto,
    _furos_dos_parafusos_da_caixa,
    _marcar_furos_das_barras,
    _sobrepoe)
from nucleo2d.detalhe.conjuntos_curvas import (  # noqa: E402
    _chanfrar_cantos,
    _cruzamento,
    _emendas_do_chanfro,
    _nos_das_quebras,
    _so_bordas_externas)
from nucleo2d.detalhe.conjuntos_tercas import (  # noqa: E402
    _alma_com_contorno,
    _cortes_das_tercas,
    _trecho_dentro,
    _vizinhos_no_plano)
from nucleo2d.detalhe.tesouras_montadas import (  # noqa: E402
    metades_espelhadas_iguais,
    sem_metades_iguais,
    uniao_das_chapas)


def _esconder_atras_dos_montantes(desenho: Desenho, entidades: Sequence, montantes: set, atras: set) -> None:
    """As linhas das peças de `atras` que passam por dentro do contorno de um montante de `montantes`
    saem nesse trecho (o banzo de baixo entrava 46 mm no montante de fechamento da cumeeira)."""
    if not montantes:
        return
    cascos = {}
    for e in entidades:
        o = (e.atributos or {}).get("origem")
        if o in montantes and isinstance(e, Linha):
            cascos.setdefault(o, []).extend([tuple(e.a), tuple(e.b)])
    cascos = {o: _casco(pts) for o, pts in cascos.items() if len(pts) >= 3}
    for e in entidades:
        o = (e.atributos or {}).get("origem")
        if o not in atras or o in montantes or not isinstance(e, Linha) or e.id not in desenho.entidades:
            continue
        pedacos = [(tuple(e.a), tuple(e.b))]
        for om, casco in cascos.items():
            if len(casco) < 3:
                continue
            novos = []
            for a_, b_ in pedacos:
                tt = _trecho_dentro(a_, b_, casco)
                if not tt:
                    novos.append((a_, b_))
                    continue
                em = lambda t: (a_[0] + (b_[0] - a_[0]) * t, a_[1] + (b_[1] - a_[1]) * t)
                if tt[0] > 1e-6:
                    novos.append((a_, em(tt[0])))
                if tt[1] < 1.0 - 1e-6:
                    novos.append((em(tt[1]), b_))
            pedacos = novos
        if len(pedacos) == 1 and pedacos[0] == (tuple(e.a), tuple(e.b)):
            continue
        desenho.remover(e.id)
        for a_, b_ in pedacos:
            if math.dist(a_, b_) > 0.5:
                desenho.add(Linha(camada=e.camada, a=(round(a_[0], 2), round(a_[1], 2)), b=(round(b_[0], 2), round(b_[1], 2)),
                                  atributos=dict(e.atributos or {})))


def _sem_larguras(xs: Sequence[float], fixos: set, meio: float, minimo: float = 60.0) -> Tuple[List[float], List[float]]:
    """A cadeia sem a largura dos perfis: de dois pontos seguidos a menos de `minimo`, fica o fixo
    (a face da ponta, as faces da cumeeira) ou o mais perto do meio da treliça. Devolve (os que
    ficam, os que saíram)."""
    ficam: List[float] = []
    sairam: List[float] = []
    for x in xs:
        if ficam and x - ficam[-1] < minimo:
            ant = ficam[-1]
            if ant in fixos and x in fixos:
                ficam.append(x)                      # a folga da cumeeira fica
            elif ant in fixos:
                sairam.append(x)
            elif x in fixos or abs(x - meio) < abs(ant - meio):
                sairam.append(ant)
                ficam[-1] = x
            else:
                sairam.append(x)
        else:
            ficam.append(x)
    return ficam, sairam


def _contorno_dos_banzos(desenho: Desenho, marca: str) -> Tuple[List[tuple], List[tuple]]:
    """O contorno dos banzos do conjunto desenhado: (segmentos, quinas). Quina é o vértice em que o
    contorno dobra (mais de 10°) — o vértice no meio de uma reta (a peça partida em dois traços) não
    conta: não é nó nem ponto de marcar."""
    segs = []
    for e in desenho.entidades.values():
        a = e.atributos or {}
        if e.camada != "BANZOS" or a.get("conjunto") != marca or a.get("detalhe") != "conjunto":
            continue
        if isinstance(e, Linha):
            segs.append((tuple(e.a), tuple(e.b)))
        elif isinstance(e, Polilinha):
            v = [tuple(q) for q in e.vertices] + ([tuple(e.vertices[0])] if e.fechada else [])
            segs += [(v[i], v[i + 1]) for i in range(len(v) - 1)]
    segs = [sg for sg in segs if math.dist(sg[0], sg[1]) > 1.0]
    quinas: List[tuple] = []
    for a_, b_ in segs:
        for q, r in ((a_, b_), (b_, a_)):
            d1 = math.atan2(r[1] - q[1], r[0] - q[0])
            for c_, d_ in segs:
                for q2, r2 in ((c_, d_), (d_, c_)):
                    if math.dist(q, q2) > 1.0 or (q2, r2) == (q, r):
                        continue
                    d2 = math.atan2(r2[1] - q2[1], r2[0] - q2[0])
                    giro = abs(math.degrees(d1 - d2)) % 360.0
                    giro = min(giro, 360.0 - giro)
                    if 10.0 < giro < 170.0 and not any(math.dist(q, w) < 1.0 for w in quinas):
                        quinas.append(q)
    return segs, quinas


def _eixos_das_faces(segs: Sequence[tuple], esp_min: float = 30.0, esp_max: float = 320.0) -> List[tuple]:
    """Os eixos dos trechos retos do contorno dos banzos: o meio de duas faces paralelas, afastadas
    entre `esp_min` e `esp_max` (a altura do perfil), no trecho em que as duas se sobrepõem — o banzo
    reto e também as pernas da peça dobrada do joelho (o pilar), que não têm um eixo reto só."""
    eixos: List[tuple] = []
    longos = [sg for sg in segs if math.dist(sg[0], sg[1]) >= 150.0]
    for i, (a_, b_) in enumerate(longos):
        L = math.dist(a_, b_)
        ux, uy = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
        for c_, d_ in longos[i + 1:]:
            L2 = math.dist(c_, d_)
            if abs(ux * (d_[1] - c_[1]) / L2 - uy * (d_[0] - c_[0]) / L2) > 0.02:
                continue
            dist = -(c_[0] - a_[0]) * uy + (c_[1] - a_[1]) * ux
            if not (esp_min <= abs(dist) <= esp_max):
                continue
            s0, s1 = sorted(((q[0] - a_[0]) * ux + (q[1] - a_[1]) * uy) for q in (c_, d_))
            lo, hi = max(0.0, s0), min(L, s1)
            if hi - lo < 0.5 * min(L, L2):
                continue
            nx, ny = -uy * dist / 2, ux * dist / 2
            eixos.append(((a_[0] + ux * lo + nx, a_[1] + uy * lo + ny), (a_[0] + ux * hi + nx, a_[1] + uy * hi + ny)))
    return eixos


def _alma_em_eixo(desenho: Desenho, entidades: Sequence, alma: Dict[str, Tuple[tuple, tuple]], camada_de: Dict[str, str],
                  quinas: Sequence[tuple] = (), apoios: Sequence[tuple] = (), encaixe: float = 200.0) -> List[tuple]:
    """A alma da treliça (montantes, diagonais, as barras do joelho) desenhada pela linha de trabalho,
    como o corte do projetista (regra do usuário, 28/09): cada barra vira uma linha só, no eixo; o
    montante fica no eixo dele; a ponta da diagonal vai ao nó: (1) a ponta do montante, quando ela
    chega na ponta dele (o nó do banzo); (2) senão, o cruzamento do eixo dela com o eixo do montante ou
    do banzo em que ela chega (a barra que encosta no meio do montante do joelho continua reta — antes
    ia para a ponta dele e saía torta); (3) senão, a quina do banzo (no joelho, onde o contorno dobra);
    (4) senão, o encontro com as outras diagonais que chegam ali. `alma`: id da peça → (a, b), o eixo
    já na célula; `apoios`: os eixos dos banzos (a, b). Os furos e as emendas ficam; o contorno da peça
    sai. Devolve os nós (as pontas das linhas desenhadas)."""
    if not alma:
        return []
    for e in list(entidades):
        a = e.atributos or {}
        if a.get("origem") in alma and isinstance(e, (Linha, Polilinha)) and e.camada not in ("FURO", "EIXO") \
                and not a.get("emenda"):
            desenho.remover(e.id)
    montantes = [ab for k, ab in alma.items() if camada_de.get(k) == "MONTANTES"]
    tops = [q for ab in montantes for q in ab]
    eixos = {k: list(ab) for k, ab in alma.items()}
    soltas = []                                          # (k, i) das pontas sem montante nem quina
    linhas_apoio = [tuple(ab) for ab in montantes] + [tuple(ab) for ab in apoios]

    def no_da_ponta(q, outra, so_cruzamento=False):
        tops_m = [(tip, (ma, mb)) for ma, mb in montantes for tip in (ma, mb)]
        # o primeiro eixo (montante ou banzo) que a reta da barra cruza, logo depois da ponta
        L = math.dist(q, outra)
        cruz = None
        if L > 1.0:
            ux, uy = (q[0] - outra[0]) / L, (q[1] - outra[1]) / L
            for i_l, (la, lb) in enumerate(linhas_apoio):
                x = _cruzamento(outra, q, la, lb)
                if x is None:
                    continue
                t = (x[0] - q[0]) * ux + (x[1] - q[1]) * uy
                if not (-80.0 <= t <= encaixe):
                    continue
                Ll = math.dist(la, lb)
                if Ll < 1.0:
                    continue
                s_ = ((x[0] - la[0]) * (lb[0] - la[0]) + (x[1] - la[1]) * (lb[1] - la[1])) / Ll
                if not (-30.0 <= s_ <= Ll + 30.0):
                    continue
                if cruz is None or abs(t) < cruz[0]:
                    cruz = (abs(t), x, i_l < len(montantes))
        if cruz is not None:
            x, no_montante = cruz[1], cruz[2]
            if so_cruzamento:
                return x
            # o nó do banzo: a barra chega no banzo junto da ponta de um montante — liga na ponta dele;
            # a que chega no próprio montante fica no cruzamento (no meio dele, no joelho), a não ser que
            # caia na ponta
            tip = min(tops_m, key=lambda tm: math.dist(tm[0], x))[0] if tops_m else None
            if tip is not None and math.dist(tip, x) <= (10.0 if no_montante else 120.0):
                return tip
            return x
        # sem cruzamento: a ponta de montante perto, a quina do joelho
        tip = min((tm[0] for tm in tops_m), key=lambda n: math.dist(n, q)) if tops_m else None
        if tip is not None and math.dist(tip, q) <= encaixe:
            return tip
        perto = min(quinas, key=lambda n: math.dist(n, q)) if quinas else None
        if perto is not None and math.dist(perto, q) <= encaixe:
            return perto
        return None

    def reta_ou_prumo(ab):
        ang = abs(math.degrees(math.atan2(ab[1][1] - ab[0][1], ab[1][0] - ab[0][0]))) % 180.0
        return min(ang, 180.0 - ang) < 5.0 or abs(ang - 90.0) < 5.0

    for k, ab in eixos.items():
        if camada_de.get(k) == "MONTANTES":
            continue
        originais = list(ab)
        if math.dist(originais[0], originais[1]) < 1e-6:
            # a peça perpendicular ao plano da vista (a travessa de uma viga-caixa, vista de topo: Vicente, 08/10) é um
            # ponto no desenho — não tem direção para andar no eixo; fica onde está (dava divisão por zero)
            continue
        # a barra deitada ou em pé (a horizontal do joelho) é como o montante: fica no eixo dela e só
        # vai até o cruzamento — a ponta anda na reta dela, não sai torta para um nó ao lado (regra do
        # usuário, 28/09: "não mexer nos montantes")
        fixa = reta_ou_prumo(originais)
        for i, q in enumerate(originais):
            achou = no_da_ponta(q, originais[1 - i], so_cruzamento=fixa)
            if achou is not None and fixa:
                o_ = originais[1 - i]
                L_ = math.dist(q, o_)
                ux, uy = (q[0] - o_[0]) / L_, (q[1] - o_[1]) / L_
                t_ = (achou[0] - o_[0]) * ux + (achou[1] - o_[1]) * uy
                achou = (o_[0] + ux * t_, o_[1] + uy * t_)
            if achou is not None:
                ab[i] = achou
            elif not fixa:
                soltas.append((k, i))
    usadas = set()
    for j, (k, i) in enumerate(soltas):
        if (k, i) in usadas:
            continue
        grupo = [(k, i)] + [(k2, i2) for k2, i2 in soltas[j + 1:] if k2 != k and (k2, i2) not in usadas
                            and math.dist(eixos[k2][i2], eixos[k][i]) <= encaixe]
        if len(grupo) > 1:
            mx = sum(eixos[g][h][0] for g, h in grupo) / len(grupo)
            my = sum(eixos[g][h][1] for g, h in grupo) / len(grupo)
            for g, h in grupo:
                eixos[g][h] = (mx, my)
                usadas.add((g, h))
    # de nó a nó: a ponta da barra inclinada que fica a até 80 mm da ponta de uma barra horizontal ou em
    # pé (a barra do joelho, o montante) vai para ela — no joelho a diagonal cruzava o B.14 a uns 50 mm do
    # nó da horizontal que chega ali
    ancoras = [(k2, q2) for k2, ab2 in eixos.items() if reta_ou_prumo(ab2) for q2 in ab2]
    for k, ab in eixos.items():
        if camada_de.get(k) == "MONTANTES" or reta_ou_prumo(ab):
            continue
        for i, q in enumerate(list(ab)):
            if any(math.dist(q, q2) <= 0.5 for k2, q2 in ancoras if k2 != k):
                continue                                 # já está num nó
            perto = [(math.dist(q, q2), q2) for k2, q2 in ancoras if k2 != k and 0.5 < math.dist(q, q2) <= 80.0]
            if perto:
                ab[i] = min(perto)[1]
    feitas: List[tuple] = []
    for k, (a_, b_) in eixos.items():
        if math.dist(a_, b_) < 5.0:
            continue
        if any(max(math.dist(a_, fa), math.dist(b_, fb)) < 15.0 or max(math.dist(a_, fb), math.dist(b_, fa)) < 15.0
               for fa, fb in feitas):
            continue                     # a cantoneira dupla (2L): as duas no mesmo eixo, uma linha só
        feitas.append((a_, b_))
        base = next((x for x in entidades if (x.atributos or {}).get("origem") == k), None)
        atr = {kk: vv for kk, vv in ((base.atributos or {}) if base is not None else {}).items()
               if kk not in ("nos_chanfro", "nos_quina", "chanfro")}
        atr["origem"] = k
        atr["eixo"] = True
        desenho.add(Linha(camada=camada_de.get(k, "DIAGONAIS"), a=(round(a_[0], 2), round(a_[1], 2)),
                          b=(round(b_[0], 2), round(b_[1], 2)), atributos=atr))
    return [q for ab in feitas for q in ab]


def _alturas_da_cadeia(ys: Sequence[float], extra: Sequence[float], minimo: float = 60.0) -> List[float]:
    """As alturas da cadeia de uma ponta com as dos nós (`extra`): a base e o topo ficam; as do meio a mais de
    `minimo` de cada vizinha (degrau menor não é medida de marcar)."""
    if len(ys) < 2:
        return list(ys)
    base, topo = ys[0], ys[-1]
    meio = sorted(set(round(y, 1) for y in list(ys[1:-1]) + list(extra) if base < y < topo))
    saida = [base]
    for y in meio:
        if y - saida[-1] >= minimo and topo - y >= minimo:
            saida.append(y)
    saida.append(topo)
    return saida


def _pontas_da_trelica(segs: Sequence[tuple], quinas: Sequence[tuple], nos: Sequence[tuple], dx: float, dy: float,
                       larg: float, alt: float, trechos_cima: Sequence[tuple], trechos_baixo: Sequence[tuple]) -> List[dict]:
    """As duas pontas da treliça para as cotas de produção (em coordenadas da célula). A zona da ponta
    é o que fica além do fim reto dos dois banzos — o joelho do canto, ou só a face da ponta. Uma
    referência só: o contorno pela **face de fora** (das quinas coladas de fora e de dentro fica a de
    fora, nunca a média — a média dava medida que não existe na peça) e os nós das barras que chegam
    na ponta. Para cada ponta: `face` (o x da face de fora, de onde saem as chamadas), `xs` e `ys`
    (quinas e nós), e o chanfro de fora do joelho."""
    if not segs or not trechos_cima or not trechos_baixo:
        return []

    def loc(q):
        return (q[0] - dx, q[1] - dy)
    segs = [(loc(a_), loc(b_)) for a_, b_ in segs]
    quinas = [loc(q) for q in quinas]
    nos = [loc(q) for q in nos]
    cx, cy = larg / 2.0, alt / 2.0

    def juntar(vals, centro, tol=30.0):
        """valores a menos de `tol` viram um só: o mais de fora (longe do centro) — a face de fora"""
        vals = sorted(vals)
        if not vals:
            return []
        grupos = [[vals[0]]]
        for x in vals[1:]:
            if x - grupos[-1][-1] <= tol:
                grupos[-1].append(x)
            else:
                grupos.append([x])
        return [round(max(g, key=lambda v: abs(v - centro)), 1) for g in grupos]

    angs = [math.degrees(math.atan2(t[2][1][1] - t[2][0][1], t[2][1][0] - t[2][0][0])) % 180.0
            for t in list(trechos_cima) + list(trechos_baixo) if t[2] is not None] + [0.0, 90.0]
    fora = []
    for lado in (-1, 1):
        if lado > 0:
            xz = min(max(t[1] for t in trechos_cima), max(t[1] for t in trechos_baixo))

            def na_zona(x, xz=xz):
                return x >= xz - 1.0
        else:
            xz = max(min(t[0] for t in trechos_cima), min(t[0] for t in trechos_baixo))

            def na_zona(x, xz=xz):
                return x <= xz + 1.0
        zs = [sg for sg in segs if na_zona(sg[0][0]) and na_zona(sg[1][0])]
        pts = [q for sg in zs for q in sg]
        if not pts:
            continue
        face = min(q[0] for q in pts) if lado < 0 else max(q[0] for q in pts)
        # o contorno de fora: as quinas no casco da zona (a quina da face de dentro fica dentro dele)
        casco = _casco(pts)
        de_fora = [q for q in quinas if na_zona(q[0]) and any(math.dist(q, c_) < 1.0 for c_ in casco)]
        nz = [q for q in nos if na_zona(q[0])]
        # a altura da ponta: o pilar e o joelho, até 600 mm da face (a ponta do banzo de baixo, mais para
        # dentro, fica na cadeia horizontal)
        perto_face = [q for q in de_fora if abs(q[0] - face) <= 600.0]
        ys_p = [q[1] for q in perto_face] or [q[1] for q in pts]
        base, topo = min(ys_p), max(ys_p)
        ys = sorted(juntar([base, topo] + [q[1] for q in perto_face], cy))
        # degrau de espessura (menos de 60 mm, a quina de um perfil) não é medida de marcar: sai, e
        # a base e o topo ficam
        limpos = [ys[0]]
        for y in ys[1:]:
            if y - limpos[-1] >= 60.0:
                limpos.append(y)
            elif y == ys[-1]:
                limpos[-1] = y if len(limpos) > 1 else limpos[-1]
                if len(limpos) == 1:
                    limpos.append(y)
        ys = limpos
        # o começo reto dos dois banzos (xz) entra: é onde a peça do joelho encontra o banzo de baixo
        xs = juntar([face, xz] + [q[0] for q in de_fora], cx)
        for q in nz:
            if all(abs(q[0] - x) > 30.0 for x in xs):
                xs.append(round(q[0], 1))
        xs = sorted(xs)
        chanfro = None
        melhor = -1.0
        for a_, b_ in zs:
            L = math.dist(a_, b_)
            if L < 60.0:
                continue
            ang = math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0])) % 180.0
            if any(min(abs(ang - g), 180.0 - abs(ang - g)) < 8.0 for g in angs):
                continue
            a2, b2 = sorted((a_, b_))
            mx, my = (a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2
            dist_c = math.hypot(mx - cx, my - cy)
            if dist_c > melhor:
                ux, uy = (b2[0] - a2[0]) / L, (b2[1] - a2[1]) / L
                sinal = 1.0 if (-uy) * (mx - cx) + ux * (my - cy) > 0 else -1.0
                chanfro, melhor = (a2, b2, sinal), dist_c
        # as alturas dos nós junto da face (onde as travessas chegam na coluna da ponta): o DP as cota em cadeia
        ys_nos = sorted({round(q[1], 1) for q in nz if abs(q[0] - face) <= 600.0 and base + 1.0 < q[1] < topo - 1.0})
        fora.append({"lado": lado, "face": face, "xs": xs, "ys": ys, "base": base, "topo": topo, "chanfro": chanfro,
                     "ys_nos": ys_nos})
    return fora


#: Parafusos a menos disto (mm) um do outro são da mesma ligação: uma chamada só.
GRUPO_DE_PARAFUSOS = 150.0


#: Mais que isto de ligações e a elevação fica só com a lista do título (chamada demais polui).
MAX_CHAMADAS_PARAFUSOS = 10


def chamadas_de_parafusos(p, doc, instancia, origem, u, v, u0: float, v0: float, esc: float, fora=()) -> int:
    """Nas elevações dos conjuntos menores (dispositivos, vigas, pilares): uma chamada por
    ligação com os parafusos dela ("4x M12 x 30"). O texto vai para fora, no lado que tiver
    lugar; a que encostaria em outra chamada não sai (a lista no título continua). A
    tesoura fica sem: os parafusos dela são os dos suportes de terça, que estão no detalhe
    das terças. `fora`: caixas [(x0, x1), (y0, y1), (z0, z1)] das peças cujos parafusos não levam chamada
    (as terças presas no DP). Devolve quantas saíram."""
    pts = []
    for c, nome in parafusos_posicionados(doc, instancia):
        if any(all(cx_[k][0] - 15.0 <= c[k] <= cx_[k][1] + 15.0 for k in range(3)) for cx_ in fora):
            continue
        rel = _sub(c, origem)
        pts.append(((_dot(rel, u) - u0, _dot(rel, v) - v0), nome))
    if not pts:
        return 0
    grupos: List[list] = []
    for q, nome in sorted(pts, key=lambda t: (t[0][0], t[0][1])):
        for g in grupos:
            if any(math.hypot(q[0] - r[0][0], q[1] - r[0][1]) <= GRUPO_DE_PARAFUSOS for r in g):
                g.append((q, nome))
                break
        else:
            grupos.append([(q, nome)])
    if len(grupos) > MAX_CHAMADAS_PARAFUSOS:
        return 0
    xs = [x for x, _ in p.pontos] or [0.0]
    ys = [y for _, y in p.pontos] or [0.0]
    cx = (min(xs) + max(xs)) / 2 - p.dx
    cy = (min(ys) + max(ys)) / 2 - p.dy
    ocupado: List[Tuple[float, float, float, float]] = []
    feitas = 0
    alt = ALTURA_CHAMADA
    for g in grupos:
        cont = collections.Counter(n for _, n in g)
        txt = " + ".join("%dx %s" % (q, n) for n, q in sorted(cont.items(), key=lambda kv: _ordem_natural(kv[0])))
        gx = sum(q[0] for q, _ in g) / len(g)
        gy = sum(q[1] for q, _ in g) / len(g)
        larg = largura_da_chamada(txt, alt, esc)
        # para fora do conjunto: o lado do centro para o grupo
        sx = 1.0 if gx >= cx else -1.0
        sy = 1.0 if gy >= cy else -1.0
        for k in (1.0, 1.8, 2.6):
            for fx, fy in ((sx, sy), (sx, -sy), (-sx, sy)):
                xt, yt = gx + fx * 8.0 * esc * k, gy + fy * 8.0 * esc * k
                caixa = (min(xt, xt + fx * larg), yt - 1.0 * esc, max(xt, xt + fx * larg), yt + (alt + 1.0) * esc)
                if any(_sobrepoe(caixa, o, 1.0 * esc) for o in ocupado):
                    continue
                p.chamada(gx, gy, xt, yt, txt, alt)
                ocupado.append(caixa)
                feitas += 1
                break
            else:
                continue
            break
    return feitas


#: A mesma chapa repetida até este tanto de vezes no desenho leva chamada em todas (usuário, 26/10, na T1 da Sala de
#: Compressores: "faltou uma linha de chamada para essa chapa", a CH9 da outra ponta; "faltou uma divisão na linha de
#: chamada para indicar o outro suporte"). Mais que isso (a chapinha de cada terça) fica numa chamada só, como antes.
MAX_RAMOS_CHAPA = 4


#: As ocorrências a até isto (mm) uma da outra dividem a chamada (uma seta para cada, saindo do joelho); mais longe, cada
#: uma tem a sua — uma seta de ponta a ponta da tesoura atravessaria o desenho.
RAMO_ATE = 1500.0


#: Chapas a menos disto (mm, na elevação) são o mesmo lugar: uma chamada só ("CH15 + CH17") — com 60 as da cumeeira
#: da T2 do depósito (CH17, CH20, CH21) saíam em três chamadas encavaladas; o mesmo raio do grupo de parafusos
MESMO_LUGAR_CHAPAS = 150.0


def _suportes_nas_chamadas(pts: list, suportes: Dict[str, str]) -> list:
    """As chapas de um suporte de terça viram uma ocorrência só, com o nome dele (usuário, 30/10, na T1 da Sala de
    Compressores: "Essas devem ser marcado o nome do suporte de terça e não as chapas se é o S.T.1, ou S.T.2").
    `pts`: [(ponto, nome, posição fundida)]; `suportes`: "P11 + P12" (as posições soldadas) ou "P14" (a chapa sozinha)
    → "S.T.1". As chapas do suporte soldado se juntam pela mais perto, a até MESMO_LUGAR_CHAPAS uma da outra; a chapa
    que fica ao lado e não é dele (a CH3 da Sala) segue com o nome dela."""
    restam = list(pts)
    for chave, nome_st in sorted(suportes.items(), key=lambda kv: -len(kv[0].split(" + "))):
        comp = chave.split(" + ")
        if len(comp) == 1:
            restam = [(q, nome_st, None) if m == comp[0] else (q, n, m) for q, n, m in restam]
            continue
        achou = True
        while achou:
            achou = False
            for i, (q0, _n, m0) in enumerate(restam):
                if m0 != comp[0]:
                    continue
                usados = [i]
                for outra in comp[1:]:
                    cand = [j for j, (q, _n2, m) in enumerate(restam) if m == outra and j not in usados
                            and math.hypot(q[0] - q0[0], q[1] - q0[1]) <= MESMO_LUGAR_CHAPAS]
                    if not cand:
                        break
                    usados.append(min(cand, key=lambda j: math.hypot(restam[j][0][0] - q0[0], restam[j][0][1] - q0[1])))
                else:
                    qs = [restam[j][0] for j in usados]
                    q_st = (sum(q[0] for q in qs) / len(qs), sum(q[1] for q in qs) / len(qs))
                    restam = [r for j, r in enumerate(restam) if j not in usados] + [(q_st, nome_st, None)]
                    achou = True
                    break
    return restam


def chamadas_das_chapas(p, instancia, origem, u, v, u0: float, v0: float, esc: float, nome_de,
                        suportes: Optional[Dict[str, str]] = None, fundida_de=None) -> int:
    """Na elevação da tesoura: uma chamada com o nome de produção de cada chapa (a da cumeeira, a do apoio, a
    chapinha do suporte), para a fábrica achar o detalhe dela (pedido do usuário, 02/10: "nos detalhes das tesouras
    não tem nenhuma chamada indicando o nome das chapas"). Cada chapa uma vez — na ocorrência mais perto do meio da
    tesoura; as do mesmo lugar numa chamada só. O texto vai para fora, no lado com lugar; devolve quantas saíram.
    `suportes` (posições → S.T.n, a nomeação do Detalhar): as chapas do suporte de terça saem com o nome dele;
    `fundida_de`: a marca do IFC → a posição fundida, a das chaves de `suportes`."""
    fundida_de = fundida_de or (lambda m: m)
    pts = []
    for e in instancia:
        if not (_tipo_ifc(e).startswith("IfcPlate") or isinstance(e, Chapa)) or not getattr(e, "vertices", None):
            continue
        m = _marcas(e)
        if not m.get("posicao"):
            continue
        n_ = len(e.vertices)
        c = tuple(sum(q[k] for q in e.vertices) / n_ for k in range(3))
        rel = _sub(c, origem)
        pts.append(((_dot(rel, u) - u0, _dot(rel, v) - v0), str(nome_de(m["posicao"]) or m["posicao"]),
                    fundida_de(str(m["posicao"]))))
    if not pts:
        return 0
    pts = [(q, n) for q, n, _m in (_suportes_nas_chamadas(pts, suportes) if suportes else pts)]
    # o S.T.n não divide a chamada com a chapa do lado (usuário, 30/10: "Separados para não confundir" — o "CH3 + S.T.1"
    # parecia a CH3 ser do suporte)
    eh_st = set((suportes or {}).values())
    lugares: List[list] = []
    for q, nome in pts:
        for g in lugares:
            if (nome in eh_st) != bool(g[1] & eh_st):
                continue
            if math.hypot(q[0] - g[0][0], q[1] - g[0][1]) <= MESMO_LUGAR_CHAPAS:
                g[1].add(nome)
                break
        else:
            lugares.append([q, {nome}])
    xs = [x for x, _ in p.pontos] or [0.0]
    ys = [y for _, y in p.pontos] or [0.0]
    cx = (min(xs) + max(xs)) / 2 - p.dx
    cy = (min(ys) + max(ys)) / 2 - p.dy
    # cada combinação de chapas uma vez, no lugar mais perto do meio; os outros lugares dela, setas a mais
    escolhidos: Dict[tuple, tuple] = {}
    todos_k: Dict[tuple, list] = collections.defaultdict(list)
    for q, nomes in lugares:
        k = tuple(sorted(nomes, key=_ordem_natural))
        todos_k[k].append(q)
        if k not in escolhidos or abs(q[0] - cx) < abs(escolhidos[k][0] - cx):
            escolhidos[k] = q
    # as chamadas: [(chapas, alvo, outros alvos)] — a chapa repetida poucas vezes, uma por grupo de ocorrências perto umas
    # das outras (a principal a mais perto do meio, as outras como setas a mais); a muito repetida, uma só
    chamadas_k = []
    for k, q0 in escolhidos.items():
        ocorr = todos_k[k]
        if len(ocorr) > MAX_RAMOS_CHAPA:
            chamadas_k.append((k, q0, []))
            continue
        grupos_q: List[list] = []
        for q in sorted(ocorr, key=lambda q: abs(q[0] - cx)):
            for g in grupos_q:
                if any(math.hypot(q[0] - r[0], q[1] - r[1]) <= RAMO_ATE for r in g):
                    g.append(q)
                    break
            else:
                grupos_q.append([q])
        chamadas_k += [(k, g[0], g[1:]) for g in grupos_q]
    ja = set()
    ocupado: List[Tuple[float, float, float, float]] = []
    feitas = 0
    alt = ALTURA_CHAMADA
    for k, (gx, gy), outros in sorted(chamadas_k, key=lambda t: abs(t[1][0] - cx)):
        nomes = [n for n in k if n not in ja] or list(k)
        txt = " + ".join(nomes)
        larg = largura_da_chamada(txt, alt, esc)
        sx = 1.0 if gx >= cx else -1.0
        sy = -1.0 if gy <= cy else 1.0
        for passo in (1.0, 1.8, 2.6, 3.4):
            for fx, fy in ((sx, sy), (-sx, sy), (sx, -sy)):
                xt, yt = gx + fx * 8.0 * esc * passo, gy + fy * 8.0 * esc * passo
                caixa = (min(xt, xt + fx * larg), yt - 1.0 * esc, max(xt, xt + fx * larg), yt + (alt + 1.0) * esc)
                if any(_sobrepoe(caixa, o, 1.0 * esc) for o in ocupado):
                    continue
                p.chamada(gx, gy, xt, yt, txt, alt, outros=outros)
                ocupado.append(caixa)
                ja.update(k)
                feitas += 1
                break
            else:
                continue
            break
    return feitas


def _rotular_barras(p: "_Papel", rotulos, esc: float, altura_papel: float = 1.8):
    """Rótulo de posição ao lado do meio de cada barra, deslocado na perpendicular da
    barra; quando cai em cima de outro rótulo, afasta-se mais um passo (até quatro)."""
    h = altura_papel * esc
    caixas = []
    for txt, (x, y), ang in rotulos:
        a = ang if ang <= 90 else ang - 180
        ra = math.radians(a)
        nx, ny = -math.sin(ra), math.cos(ra)
        larg = 0.75 * h * len(txt)
        meia = max(larg, h) / 2
        caixa = None
        for passo in range(4):
            d = (1.6 + 2.4 * passo) * esc
            cx, cy = x + nx * d, y + ny * d
            caixa = (cx - meia, cy - h / 2, cx + meia, cy + h / 2)
            if not any(_sobrepoe(caixa, cb, 0.3 * h) for cb in caixas):
                break
        caixas.append(caixa)
        p.texto(cx, cy - h / 2, txt, h, "TEXTO", angulo=a, alinhamento="centro")


def desenho_do_conjunto(doc: Documento, marca: str, instancia: Sequence[Solido], n_instancias: int,
                        desenho: Desenho, dx: float, dy: float, rotular: bool = True,
                        fundidas: Optional[Dict[str, str]] = None, nota=None,
                        nomes: Optional[Dict[str, str]] = None, nome: str = "", tipo: str = "",
                        conformadas: Optional[set] = None,
                        pesos: Optional[Dict[str, float]] = None, caixa: bool = False,
                        nomes_st: Optional[Dict[str, str]] = None) -> Tuple[float, float, float, float]:
    """Elevação do conjunto com cotas de nós, título e lista de perfis, em (dx, dy).
    `fundidas`: marca do IFC → posição fundida; `nomes`: posição fundida → nome de
    produção (rótulos e composição com o mesmo nome que as células de posição);
    `nome`: o do conjunto (T1, S.T.2…); `pesos`: posição fundida → kg por peça.
    `caixa`: a viga caixote (a treliça da obra sem cobertura: os tubos do Vicente, 13/10) é uma prancha de
    produção — as travessas com o perfil cheio (não a linha de eixo), nada de fora do conjunto em volta
    (os suportes e chumbadores da laje são do gabarito, não do soldador) e a altura cotada entre as faces
    dos banzos (o vão de 150 que fecha os 250), não o comprimento da travessa (146).
    `nomes_st`: posições → S.T.n (nomeação do Detalhar), para a chamada do suporte de terça na tesoura."""
    fundidas = fundidas or {}
    nomes = nomes or {}
    pesos = pesos or {}

    def nome_de(marca_ifc):
        f = fundidas.get(str(marca_ifc), str(marca_ifc))
        return nomes.get(f) or f
    c, u, v, w = _eixos_do_conjunto(instancia)
    if tipo == "chumbador":
        # o chumbador de parede (a chapa em pé com as barras deitadas entrando no concreto): a elevação olha ao
        # longo da chapa, com o alto da obra para cima — a chapa em pé, as barras deitadas para a esquerda, as
        # nervuras para a direita; pelos eixos principais o desenho saía enviesado ("o corte dessa chapa está
        # bem estranho", 29/09). O chumbador de pilar (barras em pé) fica como está.
        from saida.detalhamento import _autovetores
        chapas_pe = []
        for e_ in instancia:
            if not (_tipo_ifc(e_).startswith("IfcPlate") or isinstance(getattr(e_, "parametrica", None), Chapa)):
                continue
            c_e, pca_e = _autovetores(e_.vertices)
            n_e = _norm(tuple(pca_e[2]))
            if abs(n_e[2]) < 0.3:
                ext_e = [max(_dot(_sub(q, c_e), pca_e[k]) for q in e_.vertices) - min(_dot(_sub(q, c_e), pca_e[k]) for q in e_.vertices)
                         for k in range(2)]
                chapas_pe.append((ext_e[0] * ext_e[1], c_e, n_e))
        redondas = [e_ for e_ in instancia if _eh_redonda_perfil(str(_marcas(e_).get("perfil") or e_.nome or ""))]
        if chapas_pe and redondas:
            _a, c_ch, n_ch = max(chapas_pe, key=lambda t: t[0])
            z_ = (0.0, 0.0, 1.0)
            h_ = _norm(_cruz(z_, n_ch))
            u_ = _norm(_cruz(h_, z_))                          # a convenção da vista: direita = w × v
            c_r = [sum(q[k] for e_ in redondas for q in e_.vertices) / sum(len(e_.vertices) for e_ in redondas) for k in range(3)]
            if _dot(_sub(tuple(c_r), c_ch), u_) > 0:           # as barras para a esquerda
                h_ = tuple(-k for k in h_)
                u_ = tuple(-k for k in u_)
            u, v, w = u_, z_, h_
    # observador em -w (convenção do motor de vistas): origem atrás de tudo
    ws = [_dot(_sub(p, c), w) for e in instancia for p in e.vertices]
    origem = tuple(c[i] + w[i] * (min(ws) - 10.0) for i in range(3))
    vista = _vistas.Vista(origem=origem, normal=w, acima=v, profundidade=None, cortar=False,
                          entidades=[e.id for e in instancia], rotular=False,
                          nome="Conjunto %s" % marca, tipo="conjunto")
    u, v, w = vista.eixos()          # exatamente os eixos com que a vista é desenhada
    antes = set(desenho.entidades)
    _vistas.gerar(doc, vista, desenho, (dx, dy))
    info = desenho.vistas[-1]
    larg, alt = info["largura"], info["altura"]
    novas = [desenho.entidades[k] for k in desenho.entidades if k not in antes]
    camada_de = _classificar_pecas_do_conjunto(instancia, (u, v, origem))
    _registrar_camadas_de_pecas(desenho)
    # A barra calandrada do canto (banzo que dobra no joelho) sai da fábrica como duas
    # peças retas cortadas em meia-esquadria: o desenho mostra o canto vivo com a
    # emenda diagonal, não o arco que o modelo 3D traz.
    if conformadas:
        ids_conformadas = {e.id for e in instancia
                           if fundidas.get(str(_marcas(e).get("posicao") or e.nome), str(_marcas(e).get("posicao") or e.nome)) in conformadas}
        if ids_conformadas:
            # as chapas desenhadas (suportes de terça): o trecho reto que segura uma delas
            # avança sobre o arco
            ids_chapas = {e.id for e in instancia if camada_de.get(e.id) == "CHAPAS"}
            apoios = []
            for e in novas:
                if (e.atributos or {}).get("origem") in ids_chapas and hasattr(e, "pontos"):
                    pp = e.pontos()
                    if pp:
                        apoios.append((min(q[0] for q in pp), min(q[1] for q in pp), max(q[0] for q in pp), max(q[1] for q in pp)))
            novas = _chanfrar_cantos(desenho, novas, ids_conformadas, apoios)
            # peça já quebrada em retas no 3D (Cantos redondos): os nós são as quinas das
            # linhas dela — a emenda entra neles como no chanfro desenhado
            ids_quebradas = {e.id for e in instancia if e.id in ids_conformadas and (e.atributos or {}).get("quebras")}
            if ids_quebradas:
                _nos_das_quebras(novas, ids_quebradas)
    for e in novas:
        e.atributos["conjunto"] = marca
        e.atributos["detalhe"] = "conjunto"
        # silhueta (VISTA/CORTE) na camada da peça: terças, banzos, diagonais…; as
        # arestas finas ficam finas
        if e.camada in ("VISTA", "CORTE") and e.atributos.get("origem") in camada_de:
            e.camada = camada_de[e.atributos["origem"]]
    if conformadas and any((e.atributos or {}).get("nos_chanfro") for e in novas):
        # canto em peças retas: banzo até o nó e a linha de emenda em cada nó
        _emendas_do_chanfro(desenho, novas, ids_conformadas, camada_de)
    # cada barra só com as bordas de fora do perfil (sem a linha da espessura colada na borda)
    _so_bordas_externas(desenho, [desenho.entidades[k] for k in desenho.entidades if k not in antes],
                        {e.id for e in instancia if not _tipo_ifc(e).startswith("IfcPlate")}, camada_de)
    # extremos reais em (u, v) do que foi desenhado: canto inferior esquerdo = (dx, dy)
    us = [_dot(_sub(p, origem), u) for e in instancia for p in e.vertices]
    vs = [_dot(_sub(p, origem), v) for e in instancia for p in e.vertices]
    u0, v0 = min(us), min(vs)
    # na treliça, a alma pela linha de trabalho: montante no eixo, diagonal de nó a nó
    segs_bz, quinas_bz, nos_alma = [], [], []
    contorno = set()
    if any(c_ == "BANZOS" for c_ in camada_de.values()):
        alma = {}
        for e in instancia:
            if camada_de.get(e.id) not in ("MONTANTES", "DIAGONAIS") or _tipo_ifc(e).startswith("IfcPlate"):
                continue
            eixo = _eixo_da_peca(e)
            if eixo:
                alma[e.id] = tuple((_dot(_sub(q, origem), u) - u0 + dx, _dot(_sub(q, origem), v) - v0 + dy) for q in eixo)
        segs_bz, quinas_bz = _contorno_dos_banzos(desenho, marca)
        apoios_bz = []
        for e in instancia:
            if camada_de.get(e.id) != "BANZOS":
                continue
            eixo = _eixo_da_peca(e)
            if eixo:
                ab = tuple((_dot(_sub(q, origem), u) - u0 + dx, _dot(_sub(q, origem), v) - v0 + dy) for q in eixo)
                if math.dist(*ab) > 0.25 * larg:            # o banzo reto (a peça dobrada do joelho não tem eixo reto)
                    apoios_bz.append(ab)
        # ficam com o contorno (peças de banzo, não da alma): a barra na continuação de um banzo (a
        # horizontal que leva o banzo de baixo até o pilar do joelho) e o montante que fecha a
        # meia-tesoura na cumeeira (as pontas dos dois banzos chegam nas pontas dele)
        contorno = set(_alma_com_contorno(instancia, alma, apoios_bz, camada_de))
        contorno_caixa: set = set()
        if tipo == "conjunto" or caixa:
            # no conjunto (o DP), a diagonal e o montante com o perfil cheio — as duas bordas, como os outros perfis —, não
            # só a linha de eixo (pedido do usuário, 28/09); na viga caixote também ("representar os tubos", 13/10)
            novos = {k for k in alma if camada_de.get(k) in ("DIAGONAIS", "MONTANTES")} - contorno
            if caixa:
                # as travessas no plano da vista; a de topo, vista de ponta (eixo = um ponto), fica escondida no banzo
                novos = {k for k in novos if math.dist(*alma[k]) > 40.0}
                contorno_caixa = novos                # as travessas: só o contorno, sem virar "descida do banzo" nas cotas
            contorno |= novos
        # o perfil laminado (W, I, H) da alma — o montante W200 da tesoura de alma cheia do depósito
        # químico, 29/09: "esse perfil está sendo representado só por uma linha" — com o perfil cheio
        por_id = {e.id: e for e in instancia}
        contorno |= {k for k in alma if k in por_id and re.match(r"^\s*(W|HP|I|H)\s*\d", str(_marcas(por_id[k]).get("perfil") or ""), re.I)}
        for k in contorno:
            apoios_bz.append(alma.pop(k))                  # as outras barras ainda encaixam no eixo dela
        # o montante com contorno (o de fechamento da cumeeira, a descida do banzo no joelho) fica
        # na frente: o banzo e a barra com contorno que entram nele param na face dele
        _esconder_atras_dos_montantes(desenho, [desenho.entidades[k] for k in desenho.entidades if k not in antes],
                                      {k for k in contorno if camada_de.get(k) == "MONTANTES"},
                                      {e.id for e in instancia if camada_de.get(e.id) == "BANZOS"} | set(contorno))
        apoios_bz += _eixos_das_faces(segs_bz)
        nos_alma = _alma_em_eixo(desenho, [desenho.entidades[k] for k in desenho.entidades if k not in antes], alma, camada_de,
                                 quinas=quinas_bz, apoios=apoios_bz)
    atr = {"conjunto": marca, "detalhe": "conjunto"}
    if nome:
        atr["nome"] = nome                      # o grupo do conjunto no DXF leva o nome de produção
    # o DP sem as terças em corte (pedido do usuário, 28/09); o chumbador também: a cantoneira dele
    # passa por banzo, e o poste em pé sobre ele saía como vizinho, alto e sem cota (o CB1 do
    # depósito, análise das pranchas de 29/09)
    if segs_bz and tipo not in ("conjunto", "chumbador") and not caixa:
        # as terças em corte, onde cruzam o plano da tesoura sobre o banzo de cima (como o corte das
        # tesouras do projetista): a posição e o lado das abas se leem no próprio desenho
        tercas, telhas, extras = _cortes_das_tercas(doc, instancia, origem, u, v, w, u0, v0, segs_bz, dx, dy, com_telha=False)
        for id_t, nome_t, segs_t in tercas:
            # cada seção é uma peça só no CAD (o clique pega ela inteira — pedido do usuário, 28/09):
            # "corte" é a terça de onde ela veio; não é "origem", que o Aplicar peças ao 3D lê
            for a_, b_ in segs_t:
                desenho.add(Linha(camada="TERCAS", a=(round(a_[0], 2), round(a_[1], 2)), b=(round(b_[0], 2), round(b_[1], 2)),
                                  atributos=dict(atr, terca_em_corte=True, corte=id_t, nome_corte=nome_t)))
        # a telha (a linha dela e o parafuso na terça) não entra na tesoura: fica só na prancha das
        # telhas (pedido do usuário, 28/09)
        del telhas, extras
        # as peças de fora no plano da tesoura, encostadas nela — o montante lateral na ponta (A.L.2.1 do
        # depósito químico, 29/09: "pode trazer esse elemento para o corte das tesouras") —, vistas de lado
        for id_v, marca_v, pts_v in _vizinhos_no_plano(doc, instancia, origem, u, v, w, u0, v0, dx, dy):
            desenho.add(Polilinha(camada="VISTA-FINA", vertices=[(round(x_, 2), round(y_, 2)) for x_, y_ in pts_v], fechada=True,
                                  atributos=dict(atr, vizinho=True, corte=id_v, nome_corte=nome_de(marca_v) if marca_v else "")))
    p = _Papel(desenho, atr, dx, dy)
    esc = desenho.escala
    off, off2, off3 = 10.0, 20.0, 30.0
    # eixos das barras em (u, v); banzos são as barras quase horizontais e compridas
    barras = []
    rotulos = []
    for e in instancia:
        if _tipo_ifc(e).startswith("IfcPlate"):
            continue
        eixo = _eixo_da_peca(e)
        if not eixo:
            continue
        a, b = eixo
        pa = (_dot(_sub(a, origem), u) - u0, _dot(_sub(a, origem), v) - v0)
        pb = (_dot(_sub(b, origem), u) - u0, _dot(_sub(b, origem), v) - v0)
        comp = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        if comp < 40.0:
            continue
        ang = abs(math.degrees(math.atan2(pb[1] - pa[1], pb[0] - pa[0]))) % 180
        # a cantoneira do suporte de terça (L 63,5 atravessando a treliça, papel "suporte") não é barra da alma: entrava
        # como montante e deslocava o nó em 46–70 mm (cadeia 573 · 695 no lugar de 644 · 625 — PRATI, 13/10)
        papel_e = str(getattr(getattr(e, "parametrica", None), "papel", "") or "")
        if papel_e != "suporte":
            barras.append((pa, pb, comp, ang))
        m = _marcas(e)
        if rotular and m.get("posicao"):
            rotulos.append((nome_de(m["posicao"]), ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), ang))
    barras_furadas = _marcar_furos_das_barras(p, instancia, origem, u, v, u0, v0, esc)
    if caixa:
        _furos_dos_parafusos_da_caixa(p, doc, instancia, origem, u, v, w, u0, v0, esc, barras_furadas)
    banzos = [b for b in barras if (b[3] < 25.0 or b[3] > 155.0) and b[2] > 0.25 * larg]
    diagonais = [b for b in barras if b not in banzos]
    # nós: interseção do eixo de cada diagonal/montante com o eixo de cada banzo, perto da
    # ponta da diagonal (a ponta em si é cortada em ângulo e cai fora do nó)
    nos_baixo, nos_cima = {0.0, larg}, {0.0, larg}
    alturas = {0.0, alt}
    # onde chega um montante (barra em pé), o nó é o eixo dele: é o que a fábrica marca no
    # banzo; a diagonal que chega ao mesmo nó cruza o eixo do banzo com excentricidade
    de_montante = set()

    def intersecao(p1, p2, q1, q2):
        d1 = (p2[0] - p1[0], p2[1] - p1[1])
        d2 = (q2[0] - q1[0], q2[1] - q1[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            return None
        t = ((q1[0] - p1[0]) * d2[1] - (q1[1] - p1[1]) * d2[0]) / den
        return (p1[0] + d1[0] * t, p1[1] + d1[1] * t), t
    v_medio = sum((b[0][1] + b[1][1]) / 2 for b in banzos) / len(banzos) if banzos else alt / 2

    def y_em(b, x):
        (xa, ya), (xb, yb) = b[0], b[1]
        return ya if abs(xb - xa) < 1e-9 else ya + (yb - ya) * (x - xa) / (xb - xa)

    def _de_cima(b):
        """Banzo de cima: o mais alto entre os banzos que passam na mesma abscissa (a
        altura média não serve na tesoura montada de duas águas, em que o banzo de baixo
        perto da cumeeira fica acima do banzo de cima perto do beiral)."""
        xm = (b[0][0] + b[1][0]) / 2
        outros = [o for o in banzos if o is not b and min(o[0][0], o[1][0]) - 1.0 <= xm <= max(o[0][0], o[1][0]) + 1.0
                  and abs(y_em(o, xm) - y_em(b, xm)) > 20.0]
        if not outros:
            return (b[0][1] + b[1][1]) / 2 > v_medio
        return y_em(b, xm) > max(y_em(o, xm) for o in outros) or y_em(b, xm) > min(y_em(o, xm) for o in outros) and \
            y_em(b, xm) >= sum(y_em(o, xm) for o in outros) / len(outros)
    def _sozinho(b):
        xm = (b[0][0] + b[1][0]) / 2
        return not any(o is not b and min(o[0][0], o[1][0]) - 1.0 <= xm <= max(o[0][0], o[1][0]) + 1.0
                       and abs(y_em(o, xm) - y_em(b, xm)) > 20.0 for o in banzos)
    # a tesoura de alma cheia (uma barra W por água — o depósito químico, 29/09): nenhum banzo tem outro
    # por cima ou por baixo; as duas águas são o banzo de cima (pela altura média, a água mais baixa
    # virava o de baixo e a cadeia da outra atravessava a tesoura inteira)
    alma_cheia = bool(banzos) and all(_sozinho(b) for b in banzos)
    de_cima = {id(b): True if alma_cheia else _de_cima(b) for b in banzos}
    for pa, pb, comp, ang in diagonais:
        for bz in banzos:
            qa, qb = bz[0], bz[1]
            r = intersecao(pa, pb, qa, qb)
            if r is None:
                continue
            (x, y), t = r
            # até 15% além da ponta, e nunca menos de 60 mm: o montante curto (146 mm entre os tubos da viga-caixa
            # do Vicente, 08/10) para na face do banzo, 27 mm antes do eixo dele — 18%, e nenhum nó saía
            margem = max(0.15, 60.0 / max(comp, 1.0))
            if -margem <= t <= 1.0 + margem and min(qa[0], qb[0]) - 50 <= x <= max(qa[0], qb[0]) + 50:
                em_cima = de_cima[id(bz)]
                (nos_cima if em_cima else nos_baixo).add(round(x, 1))
                if abs(ang - 90.0) < 10.0:
                    de_montante.add(round(x, 1))
    for qa, qb, _, _ in banzos:
        for q in (qa, qb):
            alturas.add(round(q[1], 1))

    def ys_topo_ok(ts):
        return all(t[3] is not None for t in ts)

    def fundir(vals, tol=60.0, fixos=()):
        """Nós a menos de `tol` viram um só, na média: as duas diagonais que chegam ao mesmo
        nó cruzam o eixo do banzo com alguns centímetros de excentricidade. Os extremos
        (0 e o comprimento) não se movem."""
        vals = sorted(vals)
        grupos = [[vals[0]]]
        for x in vals[1:]:
            # o montante a mais de 60 mm da ponta é um nó dele, não a ponta (a última travessa da viga-caixa, a 100 mm
            # da emenda — Vicente, 08/10: a cadeia fechava com "500" no lugar de "400 · 100")
            ponta_e_montante = x - grupos[-1][-1] > 60.0 and (
                (x in fixos and grupos[-1][-1] in de_montante) or (x in de_montante and any(g in fixos for g in grupos[-1])))
            if x - grupos[-1][-1] > tol or ponta_e_montante:
                grupos.append([x])
            else:
                grupos[-1].append(x)
        fora = []
        for g in grupos:
            fixo = [x for x in g if x in fixos]
            mont = [x for x in g if x in de_montante]
            fora.append(fixo[0] if fixo else round(sum(mont) / len(mont), 1) if mont else round(sum(g) / len(g), 1))
        return fora
    # na treliça, a diagonal que chega ao banzo ao lado de um montante é desenhada no nó dele (até
    # 120 mm): a cadeia cota esse mesmo nó
    tol_nos = 120.0 if any(c_ == "BANZOS" for c_ in camada_de.values()) else 60.0
    nos_baixo = fundir(nos_baixo, tol=tol_nos, fixos=(0.0, larg))
    nos_cima = fundir(nos_cima, tol=tol_nos, fixos=(0.0, larg))
    alturas = fundir(alturas, tol=30.0, fixos=(0.0, alt))
    # a cadeia de cada banzo acompanha a caída da cobertura: banzo inclinado (mais de 2°)
    # ganha cotas alinhadas à própria reta, com as distâncias medidas nela — é o que se
    # marca na barra; banzo horizontal fica com a cadeia horizontal
    def _reta(pts):
        a_, b_ = min(pts, key=lambda q: q[0]), max(pts, key=lambda q: q[0])
        if b_[0] - a_[0] < 1e-6 or abs(math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0]))) < 2.0:
            return None
        return a_, b_

    def trechos(em_cima):
        """Trechos do banzo de um lado, por caída: [(x0, x1, reta ou None, y do topo)]. A
        meia-tesoura tem um só; a tesoura montada de duas águas, um por água."""
        lados = [b for b in banzos if de_cima[id(b)] == em_cima]
        grupos: Dict[int, list] = collections.OrderedDict()
        for b in sorted(lados, key=lambda b: min(b[0][0], b[1][0])):
            (xa, ya), (xb, yb) = sorted((b[0], b[1]))
            inc = math.degrees(math.atan2(yb - ya, xb - xa)) if xb - xa > 1e-6 else 0.0
            grupos.setdefault(0 if abs(inc) < 2.0 else (1 if inc > 0 else -1), []).append(b)
        fora = []
        for bs in grupos.values():
            pts = [q for b in bs for q in (b[0], b[1])]
            fora.append((min(q[0] for q in pts), max(q[0] for q in pts), _reta(pts), max(q[1] for q in pts)))
        return sorted(fora, key=lambda t: t[0])

    def reta_do_banzo(em_cima):
        ts = trechos(em_cima)
        return ts[0][2] if len(ts) == 1 else None

    # a borda de cima do que foi desenhado deste conjunto em cada abscissa: a cadeia de cima do DP (banzo
    # reto) nasce na peça em cada ponto — o suporte mais baixo que a chapa da ponta tinha a linha de
    # chamada começando no ar (M73 da Sala, "cotas pegando no vazio", 29/09)
    segs_topo: list = []

    def topo_em(x):
        if not segs_topo:
            for k_ in desenho.entidades:
                if k_ in antes:
                    continue
                e_ = desenho.entidades[k_]
                if e_.camada in ("COTA", "TEXTO", "EIXO") or not isinstance(e_, (Linha, Polilinha)):
                    continue
                pts_ = [e_.a, e_.b] if isinstance(e_, Linha) else list(e_.vertices) + ([e_.vertices[0]] if e_.fechada else [])
                segs_topo.extend(zip(pts_, pts_[1:]))
            segs_topo.append(((0.0, -1e9), (0.0, -1e9)))      # a lista não fica vazia (nada desenhado)
        X = x + dx
        melhor = None
        for (ax_, ay_), (bx_, by_) in segs_topo:
            if min(ax_, bx_) - 1.0 <= X <= max(ax_, bx_) + 1.0:
                if abs(bx_ - ax_) < 1e-6:
                    yy = max(ay_, by_)
                else:
                    t_ = min(1.0, max(0.0, (X - ax_) / (bx_ - ax_)))
                    yy = ay_ + t_ * (by_ - ay_)
                melhor = yy if melhor is None else max(melhor, yy)
        return alt if melhor is None or melhor < -1e8 else min(alt, melhor - dy)

    # as peças em pé com contorno (a descida do banzo no joelho, o montante da cumeeira): as faces delas,
    # na célula — a cadeia do joelho mede a face da descida, e a do banzo de baixo termina na face do
    # montante da cumeeira, onde o banzo acaba (pedidos do usuário, 28/09)
    pecas_em_pe = []
    for k_ in contorno:
        if camada_de.get(k_) != "MONTANTES" or k_ in contorno_caixa:
            continue
        pts_ = [q for e_ in desenho.entidades.values() if isinstance(e_, Linha) and (e_.atributos or {}).get("origem") == k_
                for q in (e_.a, e_.b)]
        if pts_:
            pecas_em_pe.append((min(q[0] for q in pts_) - dx, max(q[0] for q in pts_) - dx,
                                min(q[1] for q in pts_) - dy, max(q[1] for q in pts_) - dy))

    def cadeia_do_banzo(nos, em_cima):
        ts = trechos(em_cima)
        sinal = off if em_cima else -off
        # na treliça a cadeia dos nós sai mesmo apertada: é o que se marca no gabarito
        apertada = not (any(de_cima[id(b)] for b in banzos) and any(not de_cima[id(b)] for b in banzos))
        if len(ts) <= 1:
            reta = ts[0][2] if ts else None
            if reta is None:
                return p.cadeia_h(nos, alt if em_cima else 0.0, sinal, exigir_espaco=apertada,
                                  alturas=topo_em if em_cima else None)
            return p.cadeia_alinhada(reta, nos, sinal, exigir_espaco=apertada)
        # um trecho por água: os nós dele e as pontas dele, cada cadeia na sua reta
        feita = False
        meio_ts = (ts[0][1] + ts[-1][0]) / 2.0
        for x0, x1, reta, ytopo in ts:
            if not em_cima:
                # o banzo de baixo acaba na face do montante da cumeeira: a cadeia termina ali, não
                # no eixo (o 863 ia até o meio da cumeeira)
                for a_, b_, _y0, _y1 in pecas_em_pe:
                    if abs((a_ + b_) / 2.0 - meio_ts) > 300.0:
                        continue
                    if abs(x1 - meio_ts) < 300.0 and (a_ + b_) / 2.0 < meio_ts:
                        x1 = a_
                    elif abs(x0 - meio_ts) < 300.0 and (a_ + b_) / 2.0 > meio_ts:
                        x0 = b_
            # os nós da água (até 40 mm fora das pontas) e as pontas; nó colado na ponta (a
            # cumeeira tem dois montantes a 70 mm) funde com ela
            pontas = (round(x0, 1), round(x1, 1))
            nos_t = fundir({*pontas} | {x for x in nos if x0 - 40.0 <= x <= x1 + 40.0}, tol=60.0, fixos=pontas)
            if len(nos_t) < 2:
                continue
            feita = (p.cadeia_alinhada(reta, nos_t, sinal, exigir_espaco=apertada) if reta is not None
                     else p.cadeia_h(nos_t, ytopo if em_cima else 0.0, sinal, exigir_espaco=apertada)) or feita
        return feita
    cadeia = len(nos_baixo) > 2 and cadeia_do_banzo(nos_baixo, False)
    # a treliça (banzo em cima e embaixo): as cotas pensadas para o corte e o gabarito — a água
    # inteira ao longo de cada banzo, as pontas (joelho) medidas trecho a trecho, a cumeeira
    trelica = any(de_cima[id(b)] for b in banzos) and any(not de_cima[id(b)] for b in banzos)
    pontas = _pontas_da_trelica(segs_bz, quinas_bz, nos_alma, dx, dy, larg, alt, trechos(True), trechos(False)) if trelica else []
    nivel_baixo = 1 if cadeia else 0
    montada = trelica and len(trechos(True)) > 1
    # as medidas da treliça são as da estrutura: de face a face do contorno dos banzos (a chapa de apoio
    # que passa da face não entra — pedido do usuário, 28/09)
    xs_bz = [q[0] - dx for sg_ in segs_bz for q in sg_] if trelica else []
    face_esq, face_dir = (min(xs_bz), max(xs_bz)) if xs_bz else (0.0, larg)
    if trelica:
        agua = False
        for x0, x1, reta, _yt in trechos(False):
            if reta is not None and x1 - x0 > 300.0:
                agua = p.cadeia_alinhada(reta, [x0, x1], -off * (nivel_baixo + 1), exigir_espaco=False) or agua
        nivel_baixo += 1 if agua else 0
        # as pontas (a chapa de apoio, a face, as quinas e os nós do joelho) numa cadeia só, de ponta a
        # ponta, com a cumeeira no meio: fecha com a total — nenhuma medida solta
        if any(len(pt["xs"]) > 1 for pt in pontas):
            xs_h = {round(face_esq, 1), round(face_dir, 1)} | {x for pt in pontas for x in pt["xs"]
                                                                if face_esq - 1.0 <= x <= face_dir + 1.0}
            ts_c = trechos(True)
            fixos = {round(face_esq, 1), round(face_dir, 1)}
            # a descida do banzo no joelho: as faces dela no lugar dos nós em cima dela (o eixo do B.14,
            # o nó das diagonais a 30 mm da face — que parecia a borda da cantoneira, pedido do usuário)
            for a_, b_, _y0, _y1 in pecas_em_pe:
                if min((a_ + b_) / 2.0 - face_esq, face_dir - (a_ + b_) / 2.0) > 0.25 * (face_dir - face_esq):
                    continue
                xs_h = {x for x in xs_h if not (a_ - 40.0 <= x <= b_ + 40.0)} | {round(a_, 1), round(b_, 1)}
            if len(ts_c) > 1:
                # a tesoura é montada com as chapas de união no lugar: a cadeia vai até o centro geométrico (usuário,
                # 26/10, na T1 da Sala: "até o centro geométrico" — 780 | 420 | 7130, não 7126 até a metade e a folga
                # de 8, que não existe: as duas chapas de topo se encostam no meio)
                meio_c = round((ts_c[0][1] + ts_c[1][0]) / 2.0, 1)
                xs_h.add(meio_c)
                fixos.add(meio_c)
            # a largura do perfil não se cota na cadeia (os 50 do pilar, os 55 da descida do banzo —
            # pedido do usuário, 28/09): de dois pontos a menos de 60 mm fica a face de fora da peça
            # (a ponta da treliça) ou o que está mais para o meio; o outro vira a medida de dentro
            xs_c, tirados = _sem_larguras(sorted(xs_h), fixos, (face_esq + face_dir) / 2.0)
            if montada:
                # tesoura montada, como o usuário ajustou a prancha (28/09): a cadeia de baixo numa linha só,
                # colada na base — a ponta, a face de dentro da descida do banzo (a largura do joelho), o
                # primeiro nó, a cumeeira —, sem os pontos de dentro do joelho; as metades e a total logo
                # abaixo, 7 mm uma da outra. Fica mais baixa (cabem duas tesouras numa prancha).
                for a_, b_, _y0, _y1 in pecas_em_pe:
                    meio_p = (a_ + b_) / 2.0
                    if meio_p - face_esq < 0.25 * (face_dir - face_esq):
                        xs_c = [x for x in xs_c if not (face_esq + 1.0 < x < b_ - 1.0)]
                    elif face_dir - meio_p < 0.25 * (face_dir - face_esq):
                        xs_c = [x for x in xs_c if not (a_ + 1.0 < x < face_dir - 1.0)]
                p.cadeia_h(xs_c, 0.0, -off, exigir_espaco=False)
            elif p.cadeia_h(xs_c, 0.0, -off * (nivel_baixo + 1), exigir_espaco=False):
                nivel_baixo += 1
            # o joelho: o vão livre por dentro (da face de dentro do pilar à da descida do banzo) e a
            # largura toda por fora (da face da ponta à face de dentro da descida)
            joelho = False
            for lado_, face_ in (() if montada else ((1, face_esq), (-1, face_dir))):
                dentro_ = sorted((x for x in tirados if abs(x - face_) < 0.25 * (face_dir - face_esq)),
                                 key=lambda x: abs(x - face_))
                if len(dentro_) < 2:
                    continue
                fora_ = [x for x in xs_c if abs(x - face_) < 0.25 * (face_dir - face_esq) and x != round(face_, 1)
                         and (x - dentro_[1]) * lado_ > 0 and abs(x - dentro_[1]) < 60.0]
                p.cota_h(min(dentro_[0], dentro_[1]), max(dentro_[0], dentro_[1]), 0, -off * (nivel_baixo + 1))
                if fora_:
                    p.cota_h(min(face_, fora_[0]), max(face_, fora_[0]), 0, -off * (nivel_baixo + 2))
                joelho = True
            if joelho:
                nivel_baixo += 2
    if montada and trelica:
        ts_m = trechos(True)
        meio_m = (ts_m[0][1] + ts_m[1][0]) / 2.0
        p.cota_h(face_esq, meio_m, 0, -(off + PASSO_COTA_TESOURA))
        p.cota_h(meio_m, face_dir, 0, -(off + PASSO_COTA_TESOURA))
        p.cota_h(face_esq, face_dir, 0, -(off + 2 * PASSO_COTA_TESOURA))
    elif alma_cheia and len(trechos(True)) > 1:
        # alma cheia montada: na base, de ponta a ponta, os montantes (onde ela apoia) e a cumeeira numa
        # cadeia só, e a total logo abaixo
        ts_a = trechos(True)
        meio_a = (ts_a[0][1] + ts_a[1][0]) / 2.0
        xs_a = sorted({0.0, round(larg, 1), round(meio_a, 1)} | {x for x in de_montante if 1.0 < x < larg - 1.0})
        p.cadeia_h(fundir(set(xs_a), tol=60.0, fixos=(0.0, round(larg, 1), round(meio_a, 1))), 0.0, -off, exigir_espaco=False)
        p.cota_h(0.0, larg, 0, -(off + PASSO_COTA_TESOURA))
    else:
        p.cota_h(face_esq, face_dir, 0, -off * (nivel_baixo + 1))
    antes_cima = set(desenho.entidades)
    cadeia_cima = len(nos_cima) > 2 and nos_cima != nos_baixo and cadeia_do_banzo(nos_cima, True)
    cotas_cima = [k_ for k_ in desenho.entidades if k_ not in antes_cima and isinstance(desenho.entidades[k_], _Cota)]
    sups_cotados: List[list] = []                # as cadeias de suportes desenhadas (abscissas), para a regra das metades iguais
    # suportes de terça (chapinhas/cantoneiras curtas encostadas no banzo de cima): a
    # cadeia do espaçamento deles, alinhada ao banzo, acima da cadeia dos nós
    suportes = []
    trechos_cima = trechos(True)
    reta_cima = reta_do_banzo(True)
    sup_por_trecho: Dict[int, list] = collections.defaultdict(list)
    faces_cima: Dict[int, Optional[float]] = {}

    def face_de_cima(i_t, reta):
        """a distância da face de cima do banzo à reta dele (acima, positiva), pelos banzos da água"""
        if i_t not in faces_cima:
            (ax2, ay2), (bx2, by2) = reta
            cl2 = math.hypot(bx2 - ax2, by2 - ay2) or 1.0
            ux2, uy2 = (bx2 - ax2) / cl2, (by2 - ay2) / cl2
            x_lo, x_hi = min(ax2, bx2), max(ax2, bx2)
            ds = []
            for b_ in instancia:
                if camada_de.get(b_.id) != "BANZOS":
                    continue
                for q in b_.vertices:
                    qx = _dot(_sub(q, origem), u) - u0
                    qy = _dot(_sub(q, origem), v) - v0
                    if x_lo - 1.0 <= qx <= x_hi + 1.0:
                        ds.append(-(qx - ax2) * uy2 + (qy - ay2) * ux2)
            faces_cima[i_t] = max(ds) if ds else None
        return faces_cima[i_t]
    for e in instancia:
        if camada_de.get(e.id) != "CHAPAS":
            continue
        pu = [_dot(_sub(q, origem), u) - u0 for q in e.vertices]
        pv = [_dot(_sub(q, origem), v) - v0 for q in e.vertices]
        cx, cy = sum(pu) / len(pu), sum(pv) / len(pv)
        i_t = 0
        if len(trechos_cima) > 1:
            # tesoura montada: a reta da água em que o suporte está
            i_t = min(range(len(trechos_cima)), key=lambda i: 0.0 if trechos_cima[i][0] <= cx <= trechos_cima[i][1]
                      else min(abs(cx - trechos_cima[i][0]), abs(cx - trechos_cima[i][1])))
            reta_cima = trechos_cima[i_t][2]
        # o suporte é a chapa em pé, perpendicular ao banzo (estreita ao longo dele e alta); o gusset deitado
        # e o enrijecedor ao lado dele não contam. Medido na direção do banzo: pela horizontal, o suporte
        # de 200 mm num banzo de 11° já passava dos 40 mm e nenhum era cotado (a água direita da T1 do
        # depósito só com o 10612, pedido do usuário, 30/09)
        if reta_cima is not None:
            (ax_, ay_), (bx_, by_) = reta_cima
            cl = math.hypot(bx_ - ax_, by_ - ay_) or 1.0
            ux_, uy_ = (bx_ - ax_) / cl, (by_ - ay_) / cl
            ao_longo = [a_ * ux_ + b_ * uy_ for a_, b_ in zip(pu, pv)]
            de_pe = [-a_ * uy_ + b_ * ux_ for a_, b_ in zip(pu, pv)]
        else:
            ao_longo, de_pe = pu, pv
        if max(ao_longo) - min(ao_longo) > 40.0 or max(de_pe) - min(de_pe) < 100.0:
            continue
        if reta_cima is not None:
            (ax_, ay_), (bx_, by_) = reta_cima
            dist = abs((bx_ - ax_) * (ay_ - cy) - (ax_ - cx) * (by_ - ay_)) / max(math.hypot(bx_ - ax_, by_ - ay_), 1e-9)
        else:
            dist = abs(cy - alt)
        sobre_a_mesa = False
        if dist > 150.0 and reta_cima is not None:
            # o suporte em pé sobre a mesa de cima do banzo alto (o W250 da tesoura de alma cheia do depósito,
            # 30/09): o centro dele fica a meia altura dele acima da face de cima, a 230–270 mm da reta do
            # banzo — pela reta só, nenhum era cotado
            topo_b = face_de_cima(i_t, reta_cima)
            d_s = -(cx - ax_) * uy_ + (cy - ay_) * ux_
            sobre_a_mesa = topo_b is not None and abs(d_s - topo_b - (max(de_pe) - min(de_pe)) / 2.0) <= 60.0
        if dist <= 150.0 or sobre_a_mesa:
            if reta_cima is not None:
                # o suporte fica em pé, perpendicular ao banzo: a referência dele é o pé da
                # perpendicular no banzo (a projeção vertical erra em banzo inclinado), e a
                # abscissa que a cadeia alinhada leva de volta a esse mesmo ponto
                cl = math.hypot(bx_ - ax_, by_ - ay_) or 1.0
                ux_, uy_ = (bx_ - ax_) / cl, (by_ - ay_) / cl
                t_ = (cx - ax_) * ux_ + (cy - ay_) * uy_
                suportes.append(ax_ + ux_ * t_)
            else:
                suportes.append(cx)
            sup_por_trecho[i_t].append(suportes[-1])
    cadeia_suportes = False
    if len(trechos_cima) > 1:
        # uma cadeia de suportes por água, das pontas do trecho
        desl = off2 if cadeia_cima else off
        for i_t, lista_s in sup_por_trecho.items():
            x0, x1, reta_t, ytopo = trechos_cima[i_t]
            sup = fundir(set(round(s, 1) for s in lista_s) | {round(x0, 1), round(x1, 1)}, tol=60.0,
                         fixos=(round(x0, 1), round(x1, 1)))
            if len(sup) > 2:
                # o trecho reto na horizontal: a linha pelo topo do desenho, como a cadeia de cima (pelo topo do
                # trecho, mais baixo, o degrau a mais caía na linha dela — o 906 sobre o 839 do DP.3 da Sala, 29/09)
                feita_s = (p.cadeia_alinhada(reta_t, sup, desl, exigir_espaco=False) if reta_t is not None
                           else p.cadeia_h(sup, alt, desl, exigir_espaco=False, alturas=topo_em))
                if feita_s:
                    sups_cotados.append(sup)
                cadeia_suportes = feita_s or cadeia_suportes
        suportes = []
    if len(suportes) >= 2:
        sup = fundir(set(round(s, 1) for s in suportes) | {0.0, larg}, tol=60.0, fixos=(0.0, larg))
        # a cadeia dos suportes só se repete quando é exatamente a dos nós (terça em todo
        # nó); terça de dois em dois nós tem espaçamento próprio, e é ele que se cota
        iguais = len(sup) == len(nos_cima) and all(abs(s - n_) <= 20.0 for s, n_ in zip(sorted(sup), sorted(nos_cima)))
        if not iguais and len(sup) > 2:
            # a folga da ponta ao primeiro suporte é curta (uns 120 mm): a cadeia sai mesmo
            # assim — é a medida que a fábrica marca no banzo
            desl = off2 if cadeia_cima else off
            # a referência é o suporte da terça (regra da fábrica): a linha de chamada nasce
            # no pé do suporte, no banzo, e sobe por ele até a cadeia
            cadeia_suportes = (p.cadeia_alinhada(reta_cima, sup, desl, exigir_espaco=False) if reta_cima is not None
                               else p.cadeia_h(sup, alt, desl, exigir_espaco=False, alturas=topo_em))
            if cadeia_suportes:
                sups_cotados.append(sup)
    if cadeia_cima and sups_cotados:
        sem_metades_iguais(desenho, cotas_cima, sups_cotados, p.dx)
    n_topo = (1 if cadeia_cima else 0) + (1 if cadeia_suportes else 0)
    if alma_cheia and len(trechos_cima) > 1:
        # o comprimento de cada água, na inclinação dela, por fora das cadeias
        for x0, x1, reta, ytopo in trechos_cima:
            if x1 - x0 > 300.0:
                # na horizontal, pelo topo do desenho como as cadeias de baixo dela (pelo topo do trecho, mais
                # baixo, caía na linha delas — o 906 sobre o 839 do DP.3 da Sala, 29/09)
                (p.cadeia_alinhada(reta, [x0, x1], off * (n_topo + 1), exigir_espaco=False) if reta is not None
                 else p.cadeia_h([x0, x1], alt, off * (n_topo + 1), exigir_espaco=False, alturas=topo_em))
        n_topo += 1
    if trelica:
        # a água inteira ao longo do banzo de cima, por fora das cadeias de nós e de suportes
        agua = False
        for x0, x1, reta, ytopo in trechos(True):
            if x1 - x0 > 300.0:
                agua = (p.cadeia_alinhada(reta, [x0, x1], off * (n_topo + 1), exigir_espaco=False) if reta is not None
                        else p.cadeia_h([x0, x1], alt, off * (n_topo + 1), exigir_espaco=False, alturas=topo_em)) or agua
        n_topo += 1 if agua else 0
        ts_meia = trechos(True)
        if len(ts_meia) > 1 and ys_topo_ok(ts_meia) and not montada:
            # tesoura montada: cada metade na horizontal, da face da ponta ao meio da cumeeira (como o
            # 7200 do projeto), por cima das cotas das águas
            meio_c = (ts_meia[0][1] + ts_meia[1][0]) / 2.0
            y_ap = max(yt for _a, _b, _r, yt in ts_meia)
            p.cota_h(face_esq, meio_c, y_ap, off * (n_topo + 1.5))
            p.cota_h(meio_c, face_dir, y_ap, off * (n_topo + 1.5))
            n_topo += 2
        elif len(ts_meia) > 1 and ys_topo_ok(ts_meia):
            # a montada (as duas metades juntas): por cima de tudo, cada lado na horizontal da face da ponta ao nó onde
            # o banzo de cima começa e dele ao meio da cumeeira — 280 | 8050 na T1 da Sala (usuário, 30/10: cotou à mão
            # 275 | 8055, "Essa cota parece estar pegando no ponto errado. Precisa ser bem no nó", "Faltou essa cota",
            # "Precisa repetir para o outro lado")
            meio_c = (ts_meia[0][1] + ts_meia[1][0]) / 2.0
            y_ap = max(yt for _a, _b, _r, yt in ts_meia)
            no_esq, no_dir = ts_meia[0][0], ts_meia[-1][1]
            p.cadeia_h([face_esq] + ([no_esq] if no_esq - face_esq > 30.0 else []) + [meio_c], y_ap, off * (n_topo + 1.5),
                       exigir_espaco=False)
            p.cadeia_h([meio_c] + ([no_dir] if face_dir - no_dir > 30.0 else []) + [face_dir], y_ap, off * (n_topo + 1.5),
                       exigir_espaco=False)
            n_topo += 1
        # cada ponta: as alturas trecho a trecho (onde o banzo dobra, a base do joelho, o topo) e a
        # altura dela por fora; o chanfro do joelho pelo comprimento, na própria inclinação
        # cada ponta: as alturas das quinas e dos nós (a face de fora como referência, as chamadas saem
        # da face da peça, não da chapa de apoio) e a altura da ponta por fora
        maior = 0.0
        ponta_dir = None                                  # (x da face, deslocamento da cota mais de fora)
        cotadas_ys = []
        if tipo == "conjunto":
            # no DP, a cadeia de cada ponta passa também pelas travessas que chegam na coluna dela (base → travessa →
            # topo): na face da coluna principal do DP.3 da Sala só saía a total 1361, e o usuário cotou à mão 498 +
            # 800 (01/10); a mais de 60 mm uma da outra, como as quinas
            # a coluna (montante) da ponta que desce abaixo da treliça entra na cadeia: do pé dela à base da
            # treliça e daí ao topo (no DP.3 da Sala, o W150 a 500 mm abaixo do banzo de baixo — 498 à mão)
            monts = [e for e in desenho.entidades.values() if isinstance(e, Linha)
                     and str(e.camada or "").startswith("MONTANTES") and (e.atributos or {}).get("conjunto") == marca]
            for pt in pontas:
                ys_m = [q[1] - dy for e in monts for q in (e.a, e.b)
                        if abs((e.a[0] + e.b[0]) / 2.0 - dx - pt["face"]) <= 300.0]
                extra = list(pt.get("ys_nos") or [])
                ys_pt = list(pt["ys"])
                pt["ys_trelica"] = _alturas_da_cadeia(list(ys_pt), extra)       # o trecho da treliça, para comparar
                if ys_m and ys_pt and min(ys_m) < ys_pt[0] - 60.0:
                    ys_pt = [round(min(ys_m), 1)] + ys_pt
                    # a total dessa ponta é a altura da coluna, que já sai cotada com ela (o montante, mais abaixo)
                    pt["com_coluna"] = True
                pt["ys"] = _alturas_da_cadeia(ys_pt, extra)
        for pt in pontas:
            ys_cmp = pt.get("ys_trelica") or pt["ys"]
            if tipo == "conjunto" and not pt.get("com_coluna") and any(
                    len(ys_) == len(ys_cmp) and all(abs(a_ - b_) <= 2.0 for a_, b_ in zip(ys_, ys_cmp)) for ys_ in cotadas_ys):
                # o DP estreito: as duas pontas são o mesmo trecho, e a mesma altura saía dos dois lados (423 |
                # 423 nos DP.37 a DP.41 do depósito, análise das pranchas de 29/09); a ponta com a coluna sai sempre
                # (a cadeia dela começa no pé da coluna)
                continue
            cotadas_ys.append(list(ys_cmp))
            sg = 1.0 if pt["lado"] > 0 else -1.0
            desl0 = abs((larg if pt["lado"] > 0 else 0.0) - pt["face"]) / esc     # a chapa além da face
            nv = 1 if len(pt["ys"]) > 2 and p.cadeia_v(pt["ys"], pt["face"], sg * (off + desl0), exigir_espaco=False) else 0
            if not pt.get("com_coluna"):
                p.cota_v(pt["ys"][0], pt["ys"][-1], pt["face"], sg * (off * (nv + 1) + desl0))
            if pt["lado"] > 0:
                ponta_dir = (pt["face"], off * (nv + 1) + desl0)
            maior = max(maior, pt["ys"][-1] - pt["ys"][0])
            if pt["chanfro"]:
                a_, b_, lado_ = pt["chanfro"]
                p.cadeia_alinhada((a_, b_), [a_[0], b_[0]], lado_ * off * 2.0, exigir_espaco=False)   # por fora (28/09)
        # a altura toda pelo contorno dos banzos (da base ao ápice) — a da caixa da célula ia da chapa de
        # apoio à ponta do suporte de terça
        ys_bz = [q[1] - dy for sg_ in segs_bz for q in sg_]
        ts_cima = trechos(True)
        if ys_bz:
            base_bz, apice = min(ys_bz), max(ys_bz)
            # a descida do banzo de baixo no joelho (a peça em pé com o contorno): a altura dela, do lado
            # de dentro (pedido do usuário, 28/09) — é a base da flecha
            topo_descida = None
            if caixa:
                # a viga caixote: o vão entre as faces dos banzos, uma vez, na primeira travessa — não a altura de cada
                # travessa (a de 146 mm não "fecha" os 250 da caixa: 50 + 150 + 50; pedido do usuário, 13/10)
                ys_bz = [q[1] - dy for e_ in desenho.entidades.values() if isinstance(e_, Linha) and e_.camada == "BANZOS"
                         and (e_.atributos or {}).get("conjunto") == marca for q in (e_.a, e_.b)]
                baixo = [y_ for y_ in ys_bz if y_ < alt / 2.0]
                cima = [y_ for y_ in ys_bz if y_ >= alt / 2.0]
                xs_t = sorted(((e_.a[0] + e_.b[0]) / 2.0 - dx for e_ in desenho.entidades.values() if isinstance(e_, Linha)
                               and e_.camada == "MONTANTES" and (e_.atributos or {}).get("conjunto") == marca))
                if baixo and cima and xs_t and min(cima) - max(baixo) > 20.0:
                    p.cota_v(max(baixo), min(cima), xs_t[0] + 25.0, off * 0.6)
            for k_ in ([] if caixa else contorno):
                if camada_de.get(k_) != "MONTANTES":
                    continue
                pts_ = [q for e_ in desenho.entidades.values() if isinstance(e_, Linha) and (e_.atributos or {}).get("origem") == k_
                        for q in (e_.a, e_.b)]
                if not pts_:
                    continue
                xs_m = [q[0] - dx for q in pts_]
                ys_m = [q[1] - dy for q in pts_]
                xm = (min(xs_m) + max(xs_m)) / 2.0
                if len(ts_cima) > 1 and ts_cima[0][1] - 300.0 <= xm <= ts_cima[1][0] + 300.0:
                    continue                                  # o montante da cumeeira tem a cota dele
                if min(xm - face_esq, face_dir - xm) > 0.25 * (face_dir - face_esq):
                    continue
                para_dentro = 1.0 if xm < (face_esq + face_dir) / 2.0 else -1.0
                x_ = max(xs_m) if para_dentro > 0 else min(xs_m)
                p.cota_v(min(ys_m), max(ys_m), x_, para_dentro * off * 0.6)
                topo_descida = max(ys_m) if topo_descida is None else min(topo_descida, max(ys_m))
            if len(ts_cima) > 1:
                # tesoura montada: a flecha (da descida do banzo ao ápice) e a altura toda escritas como no
                # projeto, na ponta da direita por fora das alturas do joelho (pedido do usuário, 28/09 —
                # na cumeeira ficavam em cima do montante); sem a ponta, junto da cumeeira
                x_t, d_t = ponta_dir if ponta_dir else (ts_cima[1][0], off * -0.4)
                if topo_descida is not None and apice - topo_descida > 100.0:
                    p.cota_v(topo_descida, apice, x_t, d_t + off, texto="FLECHA TOTAL %d" % round(apice - topo_descida))
                    d_t += off
                p.cota_v(base_bz, apice, x_t, d_t + off, texto="ALTURA TOTAL %d" % round(apice - base_bz))
            elif apice - base_bz - maior > 5.0:
                p.cota_v(base_bz, apice, larg, off * 3 + abs(larg - max(pt["face"] for pt in pontas)) / esc if pontas else off * 3)
        ts_b = trechos(False)
        if len(ts_cima) > 1 and len(ts_b) > 1:
            xa_, xb_ = ts_cima[0][1], ts_cima[1][0]
            esq_ = [x for x in nos_baixo if x < xa_ - 60.0]
            dir_ = [x for x in nos_baixo if x > xb_ + 60.0]
            if esq_ and dir_:
                # o último nó de cada lado até a face das chapas de união e a largura delas, na horizontal, logo
                # abaixo do banzo de baixo na cumeeira (pedido do usuário, 28/09; 26/10, na T1 da Sala: 853 | 19 | 852
                # até a "união das chapas" — antes ia às faces das metades com uma folga de 8 que não existe)
                uniao = uniao_das_chapas(desenho, marca, (xa_ + xb_) / 2.0, dx)
                xs_r = ([max(esq_), uniao[0], uniao[1], min(dir_)] if uniao
                        else [max(esq_), (xa_ + xb_) / 2.0, min(dir_)])
                y_r = min(yb for _a, _b, _r, yb in ts_b if yb is not None) if all(t[3] is not None for t in ts_b) else 0.0
                p.cadeia_h(xs_r, y_r, -off * 2.0, exigir_espaco=False)
        if len(ts_cima) > 1 and nos_alma:
            # tesoura montada: a altura do montante da cumeeira, curta e junto dele
            xr = ts_cima[0][1]
            mont = [e for e in desenho.entidades.values() if isinstance(e, Linha) and e.camada == "MONTANTES"
                    and (e.atributos or {}).get("eixo") and (e.atributos or {}).get("conjunto") == marca]
            if mont:
                m_ = min(mont, key=lambda e: abs((e.a[0] + e.b[0]) / 2 - dx - xr))
                if abs((m_.a[0] + m_.b[0]) / 2 - dx - xr) < 300.0:
                    p.cota_v(m_.a[1] - dy, m_.b[1] - dy, (m_.a[0] + m_.b[0]) / 2 - dx, -off * 0.6)
        if len(ts_cima) > 1:
            # as duas metades com o mesmo número onde a estrutura é espelhada, o maior (853 | 19 | 853 — usuário, 30/10)
            metades_espelhadas_iguais(desenho, marca, (ts_cima[0][1] + ts_cima[1][0]) / 2.0 + dx)
    else:
        cadeia = len(alturas) > 2 and p.cadeia_v(alturas, larg, off)
        p.cota_v(0, alt, larg, off2 if cadeia else off)
    _rotular_barras(p, rotulos, esc)
    if tipo == "tesoura":
        chamadas_das_chapas(p, instancia, origem, u, v, u0, v0, esc, nome_de, suportes=nomes_st,
                            fundida_de=lambda m: fundidas.get(m, m))
    fora_t = []
    if tipo != "tesoura":
        # no DP, os parafusos que prendem as terças nele não têm chamada (são da terça, na obra — pedido
        # do usuário, 28/09); a ligação com a tesoura fica
        if tipo == "conjunto":
            ids_i = {e.id for e in instancia}
            cx_i = [_caixa(e) for e in instancia]
            lim = [(min(c_[k][0] for c_ in cx_i) - 200.0, max(c_[k][1] for c_ in cx_i) + 200.0) for k in range(3)]
            for e in doc.entidades.values():
                if e.id in ids_i or not getattr(e, "vertices", None):
                    continue
                if not re.match(r"T\.[CLOM]\.\d", nome_de(_marcas(e).get("posicao") or "")):
                    continue
                cx_e = _caixa(e)
                if all(cx_e[k][0] <= lim[k][1] and cx_e[k][1] >= lim[k][0] for k in range(3)):
                    fora_t.append(cx_e)
        chamadas_de_parafusos(p, doc, instancia, origem, u, v, u0, v0, esc, fora=fora_t)
    if barras_furadas:
        # os detalhes de furação abaixo de tudo o que a elevação já desenhou
        fundo = min([0.0] + [q[1] - dy for q in p.pontos])
        _detalhes_de_furos(p, barras_furadas, nome_de, esc, fundo - 20.0 * esc)
    # as soldas de fábrica chapa × perfil (auditoria D3, 11/10/2026 — decisão do usuário): a nota geral na legenda e um
    # símbolo "TÍP." por tipo de encontro (T e sobreposição), não um em cada ligação
    cordoes_solda = []
    try:
        from nucleo2d.detalhe.soldas import soldas_do_conjunto
        from nucleo2d.detalhe.base import _fixadores as _fix_doc, simbolo_solda
        cx_s = [_caixa(e) for e in instancia if getattr(e, "vertices", None)]
        lim_s = [(min(c_[k][0] for c_ in cx_s) - 20.0, max(c_[k][1] for c_ in cx_s) + 20.0) for k in range(3)]
        fix_s = [f for f in _fix_doc(doc)
                 if all(_caixa(f)[k][0] <= lim_s[k][1] and _caixa(f)[k][1] >= lim_s[k][0] for k in range(3))]
        cordoes_solda = soldas_do_conjunto(instancia, fix_s)
    except Exception:                                    # noqa: BLE001 — sem o levantamento, o conjunto sai sem a solda
        cordoes_solda = []
    # título e lista de perfis: um perfil por linha, escrito na camada (cor) das peças
    # que o usam — banzo, diagonal, montante, chapa —, como a fábrica lê a elevação
    perfis_cam: Dict[tuple, int] = collections.Counter()
    peso_un = 0.0
    for e in instancia:
        m = _marcas(e)
        marca_e = str(m.get("posicao") or e.nome)
        perfis_cam[(camada_de.get(e.id, "TEXTO"), str(m.get("perfil") or e.nome))] += 1
        peso_un += float(pesos.get(fundidas.get(marca_e, marca_e), 0.0) or 0.0)
    ordem_cam = {k: i for i, k in enumerate(CAMADAS_PECAS)}
    # a função com mais de um perfil (os banzos U100X50 #11, #9 e #8 da tesoura): cada chapa (perfil) na
    # cor dela, a mesma em banzo, diagonal ou montante (pedido do usuário, 28/09)
    sub_camada = _camadas_por_perfil(desenho, marca, instancia, camada_de)
    if sub_camada:
        perfis_cam = collections.Counter()
        for e in instancia:
            m = _marcas(e)
            cam_ = camada_de.get(e.id, "TEXTO")
            perfil_e = str(m.get("perfil") or e.nome)
            perfis_cam[(sub_camada.get((cam_, com_bitola(perfil_e)), cam_), perfil_e)] += 1
        ordem_cam = {k: i for i, k in enumerate(CAMADAS_PECAS)}
        for k_ in desenho.camadas:
            base_ = k_.split(" ")[0]
            if base_ in CAMADAS_PECAS and k_ != base_:
                ordem_cam[k_] = ordem_cam[base_] + 0.1
    y = alt + (off * n_topo + 12.0) * esc           # por cima dos níveis de cota do banzo de cima

    def quebrar(prefixo, itens, largura=64):
        fora, atual = [], prefixo
        for it in itens:
            if len(atual) + len(it) + 2 > largura and atual != prefixo:
                fora.append(atual.rstrip(", "))
                atual = ""                           # continuação alinhada à margem (espaços não alinham em fonte proporcional)
            atual += it + ", "
        fora.append(atual.rstrip(", "))
        return fora
    # legenda enxuta: nome e quantidade, os perfis (um por linha, na cor da peça), os
    # parafusos e o peso; sem a lista de nomes das peças — cada uma tem o seu detalhe e o
    # tipo está no título do quadro. Cada linha é (texto, camada).
    titulo = "%s – %02dx" % (nome or marca, n_instancias)
    linhas = [(titulo, "TEXTO")]
    # uma linha por tipo de peça, na cor dela: "U100X50X4.18" (banzos, azul), "U88X40X2.25 /
    # U100X50X3.04" (diagonais, laranja)…; as chapas pela espessura ("PLATE 400x120x13" → #13)
    por_cam: Dict[str, List[str]] = collections.OrderedDict()
    # cada perfil uma linha só, na cor da primeira função que o usa: a tesoura de alma cheia toda em
    # W200X22.50 (banzos, montantes e diagonais) escrevia o mesmo perfil três vezes (29/09)
    ja_listados = set()
    for (cam_, perfil_), _q in sorted(perfis_cam.items(), key=lambda kv: (ordem_cam.get(kv[0][0], 99), _ordem_natural(kv[0][1]))):
        if not perfil_:
            continue
        if cam_ == "CHAPAS":
            m_esp = re.search(r"x\s*([\d.,]+)\s*$", perfil_)
            perfil_ = "#" + m_esp.group(1).replace(".", ",") if m_esp else perfil_
        perfil_ = com_bitola_e_mm(perfil_)          # U100X50X4.18 → U100X50X#8/4.18mm: bitola e mm (05/10)
        if cam_ != "CHAPAS":
            if perfil_ in ja_listados:
                continue
            ja_listados.add(perfil_)
        lista_ = por_cam.setdefault(cam_ if (cam_ in CAMADAS_PECAS or cam_ in desenho.camadas) else "TEXTO", [])
        if perfil_ not in lista_:
            lista_.append(perfil_)
    for cam_, lista_ in por_cam.items():
        if cam_ == "CHAPAS":
            lista_ = sorted(lista_, key=_ordem_natural, reverse=True)
        linhas.append(("%s%s" % ("Chapas " if cam_ == "CHAPAS" else "", " / ".join(lista_)), cam_))
    # os da terça presa no DP também fora da lista: o desenho não mostra a terça nem a chamada deles (os M12 x 35
    # dos DP.37 a DP.41 do depósito, análise das pranchas de 29/09)
    paraf, porcas = parafusos_no_conjunto(doc, instancia, fora=fora_t)
    if paraf or porcas:
        itens_p = ["%dx %s" % (q, k) for k, q in sorted(paraf.items(), key=lambda kv: _ordem_natural(kv[0]))]
        # as soltas de ponta roscada no padrão da fábrica: 1 porca + 2 arruelas por ponta (28/09) — a ponta
        # procurada em todas as barras do modelo (a do chumbador não está na tesoura)
        # (o chumbador pela regra da lista — o do projetista no projeto recebido, 2 porcas + 1 arruela no nosso: R05)
        from nucleo2d.detalhe.base import pontas_do_modelo, soltas_no_conjunto, ferragens_das_pontas
        from nucleo2d.detalhar import projeto_recebido
        mapa = pontas_do_modelo(doc)
        soltas = soltas_no_conjunto(doc, instancia)
        pontas = {id(mapa[f]): mapa[f] for f in soltas if f in mapa}
        ferr = ferragens_das_pontas(doc, list(pontas.values()), projeto_recebido(doc))
        for bit in sorted({b for _t, b in ferr}):
            b_ = " Ø%s" % bit if bit else ""
            np_, na_ = ferr.get(("porca", bit), 0), ferr.get(("arruela", bit), 0)
            itens_p.append(" + ".join(x for x in ("%dx porca sext.%s" % (np_, b_) if np_ else "",
                                                  "%dx arruela lisa%s" % (na_, b_) if na_ else "") if x))
        resto = sum(1 for f in soltas if f not in mapa)
        if resto:
            itens_p.append("%dx porca/arruela" % resto)
        linhas += [(t, "TEXTO") for t in quebrar("Parafusos: ", itens_p)]
    if cordoes_solda:
        m_s = sum(c_["comprimento"] * c_["lados"] for c_ in cordoes_solda) / 1000.0
        deduzidas_s = [c_ for c_ in cordoes_solda if not c_.get("definida")]
        if deduzidas_s:
            pernas_s = sorted({c_["perna"] for c_ in deduzidas_s})
            # em duas linhas curtas: numa só ela passava da largura da célula e tirava as cotas do vizinho (M89, 11/10)
            linhas.append(("Solda de fábrica: filete %s mm, exceto indicado" % " / ".join(_mm(x_, 0) for x_ in pernas_s), "SOLDA"))
            linhas.append(("  todo o contato chapa × perfil (%s m/un.)" % _mm(m_s, 1), "SOLDA"))
        else:
            # só as soldas definidas no 3D: cada uma tem o símbolo dela
            linhas.append(("Solda de fábrica: conforme os símbolos (%s m/un.)" % _mm(m_s, 1), "SOLDA"))
    if peso_un > 0:
        # o conjunto leve com duas casas: 2,9 × 25 não dava os 73,3 do CB1 (análise das pranchas, 29/09)
        linhas.append(("%s kg/un  total %s kg" % (_mm(peso_un, 2 if peso_un < 10.0 else 1), _mm(peso_un * n_instancias, 1)),
                       "TEXTO"))
    for txt in ([nota] if isinstance(nota, str) else list(nota or [])):
        if not txt:
            continue
        # nota quebrada por palavras, com recuo
        atual = "* "
        for palavra in txt.split(" "):
            if len(atual) + len(palavra) + 1 > 72 and atual.strip() != "*":
                linhas.append((atual.rstrip(), "TEXTO"))
                atual = "  "
            atual += palavra + " "
        linhas.append((atual.rstrip(), "TEXTO"))
    for i, (txt, cam_) in enumerate(reversed(linhas)):
        alt_t = 3.5 if i == len(linhas) - 1 else 2.5
        # a ordem da linha no bloco (0 = o título): a prancha leva o bloco para baixo do conjunto
        p.texto(0, y, txt, alt_t * esc, cam_, atributos={"legenda_conjunto": len(linhas) - 1 - i})
        y += (alt_t + 1.2) * esc
    # o símbolo "TÍP." de cada tipo de solda, desenhado por último, com a linha de referência acima de tudo (cotas e
    # legenda): no meio das cotas do alto da elevação ele tirava cotas do conjunto (M89 da Água Gelada, 11/10)
    if cordoes_solda:
        topo_s = max([q[1] - p.dy for q in p.pontos] + [alt])
        for j_s, tipo_s in enumerate(("T", "sobreposição")):
            c_s = next((c_ for c_ in cordoes_solda if c_["tipo"] == tipo_s and not c_.get("definida")), None)
            if c_s is None:
                continue
            mx_s = sum(_dot(_sub(c_s[q], origem), u) for q in ("p0", "p1")) / 2.0 - u0
            my_s = sum(_dot(_sub(c_s[q], origem), v) for q in ("p0", "p1")) / 2.0 - v0
            lado_s = 1.0 if j_s == 0 else -1.0             # o segundo tipo para o outro lado: os dois costumam estar no mesmo nó
            simbolo_solda(p, esc, mx_s, my_s, mx_s + lado_s * 12.0 * esc, topo_s + (8.0 + 8.0 * j_s) * esc, c_s["perna"],
                          ambos_lados=c_s["lados"] == 2, cauda="TÍP.")
        # as soldas definidas à mão no 3D (14/10/2026): um símbolo por par de peças, sem o "TÍP.", com o tipo
        # (filete ou penetração), a perna e o trecho-passo do intermitente
        pos_de = {e.id: str(_marcas(e).get("posicao") or "") for e in instancia}
        vistas_s = set()
        k_s = 0
        for c_s in cordoes_solda:
            if not c_s.get("definida"):
                continue
            chave_s = (frozenset((pos_de.get(c_s.get("chapa"), ""), pos_de.get(c_s.get("perfil"), ""))),
                       c_s["perna"], c_s.get("solda"), c_s["lados"], c_s.get("intermitente"))
            if chave_s in vistas_s:
                continue
            vistas_s.add(chave_s)
            mx_s = sum(_dot(_sub(c_s[q], origem), u) for q in ("p0", "p1")) / 2.0 - u0
            my_s = sum(_dot(_sub(c_s[q], origem), v) for q in ("p0", "p1")) / 2.0 - v0
            lado_s = 1.0 if k_s % 2 == 0 else -1.0
            simbolo_solda(p, esc, mx_s, my_s, mx_s + lado_s * 12.0 * esc, topo_s + (24.0 + 8.0 * k_s) * esc, c_s["perna"],
                          ambos_lados=c_s["lados"] == 2, forma=str(c_s.get("solda") or "filete"),
                          intermitente=c_s.get("intermitente"))
            k_s += 1
    ext = p.extremos
    # a chapa na elevação do conjunto é só mostrada (a de corte está na prancha das chapas): o contorno dela na camada
    # cinza CHAPAS-VISTA — o texto da lista de perfis ("Chapas #9,5") continua na cor das chapas (13/10)
    _chapas_so_vistas(desenho, antes)
    return (min(ext[0], dx), min(ext[1], dy), max(ext[2], dx + larg), max(ext[3], dy + alt))


def _chapas_so_vistas(desenho: Desenho, antes: set, entidades=None) -> int:
    """O traço das chapas desenhadas (linhas, polilinhas, arcos) desde `antes` — ou de `entidades` — passa da camada
    CHAPAS (a do corte) para CHAPAS-VISTA (cinza): é chapa mostrada no conjunto, não a chapa para cortar. Devolve
    quantas entidades mudou."""
    _registrar_camadas_de_pecas(desenho)
    n = 0
    ents = entidades if entidades is not None else [desenho.entidades[k] for k in desenho.entidades if k not in antes]
    for e in ents:
        if getattr(e, "camada", "") == "CHAPAS" and not isinstance(e, Texto) and not (e.atributos or {}).get("chapa_de_corte"):
            e.camada = "CHAPAS-VISTA"
            n += 1
    return n


#: Entre as linhas de cota de baixo da tesoura montada (a cadeia, as metades, a total), mm de papel.
PASSO_COTA_TESOURA = 7.0


#: As cores dos perfis quando um conjunto tem mais de um na mesma função: cada perfil a sua, a mesma em
#: todas as funções e em todo o desenho; a primeira livre da função (banzo azul-claro, diagonal laranja,
#: montante roxo), depois as de reserva — nenhuma verde (é a cor das cotas) nem ouro (as chapas).
#: O 2º perfil do banzo em vermelho, bem longe do ciano do 1º (usuário, 30/10, na T1 da Sala: "Colocar em cores bem
#: diferentes para não confundir onde vai cada um dos perfis" — o U100X50X#11 e o #9 saíam ciano e azul, ou o mesmo ciano)
CORES_POR_PERFIL = {
    "BANZOS": ["#22a7c2", "#dc2626", "#2563eb", "#0e7490"],
    "DIAGONAIS": ["#e67e22", "#9a3412", "#be185d"],
    "MONTANTES": ["#a855f7", "#ec4899", "#6366f1", "#7e22ce"],
}


CORES_DE_RESERVA = ["#0891b2", "#be185d", "#4f46e5", "#b45309", "#7c3aed", "#475569"]


#: perfil → cor, uma só no Detalhar inteiro: cada célula escolhia as cores no desenho em que era desenhada pela 1ª vez e
#: era copiada para os outros (o desenho por família, o completo, as pranchas) sem as camadas — na prancha, a camada
#: "BANZOS U100X50X#9" ficava com o ciano do #11 (Sala de Compressores, 30/10). O Detalhar zera (zerar_cores_por_perfil).
_CORES_DO_DETALHAR = threading.local()


def _cores_do_detalhar() -> Dict[str, str]:
    if not hasattr(_CORES_DO_DETALHAR, "cores"):
        _CORES_DO_DETALHAR.cores = {}
    return _CORES_DO_DETALHAR.cores


def zerar_cores_por_perfil():
    _cores_do_detalhar().clear()


def _camadas_por_perfil(desenho: Desenho, marca: str, instancia: Sequence[Solido], camada_de: Dict[str, str]) -> Dict[tuple, str]:
    """Banzos, diagonais e montantes com mais de um perfil numa função: cada perfil numa camada
    ("BANZOS U100X50X#9") com a cor dele — o mesmo perfil, a mesma cor, em qualquer função e em todos os
    conjuntos do desenho —, e as linhas do conjunto passam para ela. Devolve {(função, perfil): camada};
    vazio se toda função tem um perfil só (fica a cor da função)."""
    from nucleo2d.desenho import Camada2D
    por_funcao: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    perfil_de: Dict[str, str] = {}
    for e in instancia:
        cam_ = camada_de.get(e.id)
        if cam_ not in CORES_POR_PERFIL:
            continue
        perfil_e = com_bitola(str(_marcas(e).get("perfil") or e.nome))
        perfil_de[e.id] = perfil_e
        por_funcao[cam_][perfil_e] += 1
    if not any(len(perfis) > 1 for perfis in por_funcao.values()):
        return {}
    # as cores já dadas neste Detalhar (outras tesouras, em qualquer desenho) e no desenho: perfil → cor
    cor_de: Dict[str, str] = _cores_do_detalhar()
    for nome_c, cam in desenho.camadas.items():
        base_, _sp, perfil_c = nome_c.partition(" ")
        if base_ in CORES_POR_PERFIL and perfil_c:
            cor_de.setdefault(perfil_c, cam.cor)
    mapa: Dict[tuple, str] = {}
    for cam_ in CORES_POR_PERFIL:
        perfis = por_funcao.get(cam_)
        for perfil_e, _n in sorted((perfis or {}).items(), key=lambda kv: (-kv[1], _ordem_natural(kv[0]))):
            if perfil_e not in cor_de:
                usadas = set(cor_de.values())
                livres = [c for c in CORES_POR_PERFIL[cam_] + CORES_DE_RESERVA if c not in usadas]
                cor_de[perfil_e] = livres[0] if livres else CORES_DE_RESERVA[len(cor_de) % len(CORES_DE_RESERVA)]
            nome_c = "%s %s" % (cam_, perfil_e)
            if nome_c not in desenho.camadas or desenho.camadas[nome_c].cor != cor_de[perfil_e]:
                base = desenho.camadas.get(cam_)
                desenho.camadas[nome_c] = Camada2D(nome_c, cor_de[perfil_e], espessura=base.espessura if base else 0.35)
            mapa[(cam_, perfil_e)] = nome_c
    for e in desenho.entidades.values():
        a = e.atributos or {}
        if a.get("conjunto") != marca or e.camada not in CORES_POR_PERFIL:
            continue
        perfil_e = perfil_de.get(a.get("origem"))
        if perfil_e and (e.camada, perfil_e) in mapa:
            e.camada = mapa[(e.camada, perfil_e)]
    return mapa
