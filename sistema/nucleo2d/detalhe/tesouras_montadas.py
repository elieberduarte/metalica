# -*- coding: utf-8 -*-
"""Tesouras montadas: as duas meias no mesmo plano, metades espelhadas, união das chapas.

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
    _eixos_do_conjunto,
    _instancias_do_conjunto)


# ============================================================ tesouras montadas
#: Duas meias-tesouras são da mesma tesoura quando estão no mesmo plano (a esta distância, mm).
TOLERANCIA_PLANO_TESOURA = 150.0


#: Folga (mm) entre as caixas de duas meias para serem a mesma tesoura montada: no mesmo plano e encostadas (com
#: folga para a emenda e a chapa da cumeeira). Só o plano juntava as vigas-caixa dos 12 andares do Vicente — mesmo
#: plano vertical, alturas diferentes — numa "tesoura" só (08/10).
FOLGA_MEIAS_MONTADAS = 300.0


def _faixa_reta(pecas: Sequence[Solido], normal, tol: float = 30.0, faixas: int = 24) -> bool:
    """As peças, vistas no plano de normal `normal`, formam uma faixa reta — o contorno de cima e o de baixo
    constantes ao longo do comprimento (até `tol` mm) —, como uma linha de vigas emendadas; a tesoura tem caída. Só as
    barras: a chapa de apoio de cada ponta, mais alta que a treliça, quebrava a faixa (Hora Certa · Galpão Existente,
    29/10: as 12 treliças planas TS01 em linha, entre as faces dos pilares, viravam uma "tesoura" de 46 m)."""
    barras = [e for e in pecas if not _tipo_ifc(e).startswith("IfcPlate")] or list(pecas)
    # com o papel na treliça gravado, só ela: as mãos-francesas do conjunto da meia descem abaixo do banzo nas pontas
    # (Sala de Tintas, 30/10: duas treliças planas de 10 m em linha, com o pilar entre elas, viravam a "T1" de 20 m)
    da_trelica = [e for e in barras if str((e.atributos or {}).get("papel_trelica") or "") in ("banzo", "montante", "diagonal")]
    barras = da_trelica or barras
    # os vértices e pontos ao longo das arestas: o prisma da barra só tem vértice nas pontas, e no meio do vão a faixa via
    # só a ponta do montante (abaixo da face do banzo) — a treliça plana não dava faixa reta. O passo é meia faixa: a
    # 1/8 da aresta, o banzo de 11,9 m da TS02 deixava faixas sem o contorno de cima (a "T3" de 14,7 m, 30/10)
    todos = [v for e in barras for v in (e.vertices or [])]
    if not todos:
        return False
    passo = max(1.0, max(max(v[k] for v in todos) - min(v[k] for v in todos) for k in range(3)) / (2.0 * faixas))
    verts = []
    for e in barras:
        vs = e.vertices or []
        verts.extend(vs)
        for f in (getattr(e, "faces", None) or []):
            for i in range(len(f)):
                a, b = vs[f[i]], vs[f[(i + 1) % len(f)]]
                n_ = max(2, int(math.ceil(math.dist(a, b) / passo)))
                verts.extend(tuple(a[k] + (b[k] - a[k]) * t / n_ for k in range(3)) for t in range(1, n_))
    if len(verts) < 4:
        return False
    n = _norm(normal)
    c = tuple(sum(v[i] for v in verts) / len(verts) for i in range(3))
    planos = [_sub(v, c) for v in verts]
    planos = [_sub(q, tuple(n[i] * _dot(q, n) for i in range(3))) for q in planos]
    # o eixo maior no plano
    _c, pca = _autovetores(planos)
    a1 = pca[0]
    a2 = _norm(_cruz(n, a1))
    us = [_dot(q, a1) for q in planos]
    vs = [_dot(q, a2) for q in planos]
    u0, u1 = min(us), max(us)
    if u1 - u0 < 1e-6:
        return False
    cima: Dict[int, float] = {}
    baixo: Dict[int, float] = {}
    for u_, v_ in zip(us, vs):
        k = min(faixas - 1, int((u_ - u0) / (u1 - u0) * faixas))
        cima[k] = max(cima.get(k, -1e18), v_)
        baixo[k] = min(baixo.get(k, 1e18), v_)
    if len(cima) < faixas // 2:
        return False
    return (max(cima.values()) - min(cima.values()) <= tol) and (max(baixo.values()) - min(baixo.values()) <= tol)


def _caixa_de_pecas(pecas: Sequence[Solido]):
    cs = [_caixa(e) for e in pecas]
    return [(min(c[k][0] for c in cs), max(c[k][1] for c in cs)) for k in range(3)]


#: Duas cotas espelhadas pelo meio da tesoura montada são a mesma medida se diferem até isto (mm).
ESPELHADAS_ATE = 1.0


def metades_espelhadas_iguais(desenho, marca: str, meio: float, tol_pos: float = 3.0) -> int:
    """Na tesoura montada, a cota de uma metade e a espelhada dela na outra (pelo x `meio`, no desenho) escritas com o
    mesmo número quando diferem até ESPELHADAS_ATE: o MAIOR dos dois. Saía 853 | 19 | 852 na cumeeira da T1 da Sala
    (1724 entre os nós − 19 do pacote = 852,5 de cada lado) e 492 | 7838 | 7839 | 491 na T4 (usuário, 30/10: "Esses
    valores não deveriam ser igual pela estrutura ser espelhada?" → "853" — "É mais fácil ele cortar um pedacinho do
    que faltar"). Só escreve o número quando o arredondamento separava os dois; devolve quantas cotas mudaram."""
    def medida(c):
        if c.modo == "h":
            return abs(c.p2[0] - c.p1[0])
        if c.modo == "v":
            return abs(c.p2[1] - c.p1[1])
        return math.dist(c.p1, c.p2)
    cotas = [e for e in desenho.entidades.values() if isinstance(e, _Cota) and not e.texto
             and (e.atributos or {}).get("conjunto") == marca and (e.atributos or {}).get("detalhe") == "conjunto"]
    usadas = set()
    feitas = 0
    for i, a in enumerate(cotas):
        if i in usadas:
            continue
        ea = [(2.0 * meio - q[0], q[1]) for q in (a.p1, a.p2)]
        for j in range(i + 1, len(cotas)):
            b = cotas[j]
            if j in usadas or b.modo != a.modo:
                continue
            pb = [tuple(b.p1), tuple(b.p2)]
            if not any(all(math.dist(x, y) <= tol_pos for x, y in zip(ea, par)) for par in (pb, pb[::-1])):
                continue
            ma, mb = medida(a), medida(b)
            ra, rb = math.floor(ma + 0.5), math.floor(mb + 0.5)
            if abs(ma - mb) <= ESPELHADAS_ATE and ra != rb:
                a.texto = b.texto = "%d" % max(ra, rb)
                feitas += 2
            usadas.update((i, j))
            break
    return feitas


def uniao_das_chapas(desenho, marca: str, meio: float, dx: float = 0.0) -> Optional[Tuple[float, float]]:
    """As faces de fora das chapas de topo que unem as duas metades da tesoura montada, na abscissa da célula: as
    chapas do conjunto (camada CHAPAS…) inteiras a menos de 40 mm do meio. Na Sala, duas de 9,5 mm encostadas no
    meio: (−9,5, +9,5). None quando não há chapa de união no desenho."""
    xs = []
    for e in desenho.entidades.values():
        if not str(e.camada or "").startswith("CHAPAS") or (e.atributos or {}).get("conjunto") != marca:
            continue
        pts = [e.a, e.b] if isinstance(e, Linha) else list(getattr(e, "vertices", None) or [])
        if pts and all(abs(q[0] - dx - meio) <= 40.0 for q in pts):
            xs += [q[0] - dx for q in pts]
    if not xs or max(xs) - min(xs) < 1.0:
        return None
    # ao mm: a espessura do pacote inteira (19 = duas chapas de 9,5) em volta do centro dele, com o meio milímetro para
    # cima — 853 | 19 | 852, a cadeia fecha (cada face arredondada sozinha dava 18 ou 20 no meio)
    w = float(round(max(xs) - min(xs)))
    lo = float(math.floor((max(xs) + min(xs)) / 2.0 - w / 2.0 + 0.5))
    return (lo, lo + w)


#: Duas metades de um vão entre terças que diferem até isto (mm) são o montante no meio: não se cotam (regra de 26/10).
METADES_IGUAIS = 1.0


#: O nó da cadeia e o suporte da terça são o mesmo ponto até esta distância (mm, na abscissa do desenho).
NO_NO_SUPORTE = 30.0


def sem_metades_iguais(desenho, cotas_nos: Sequence[str], sups_cotados: Sequence[Sequence[float]], dx: float = 0.0) -> int:
    """Regra das metades iguais (usuário, 26/10, na T1 da Sala de Compressores): na cadeia dos nós do banzo de cima, o vão entre duas
    terças com um nó só no meio, dividido em duas metades iguais (773 + 773 num vão de 1.546), não leva as duas cotas — "o
    pessoal da fábrica divide manualmente na hora da montagem"; a cadeia das terças, por fora, já mede o vão. Metade
    desigual (754 + 792, a do lado da cumeeira 773 + 875) fica: "a produção precisa da medida para saber onde a peça
    precisa ser posicionada". `cotas_nos`: as chaves das cotas da cadeia dos nós; `sups_cotados`: as abscissas de cada
    cadeia de suportes desenhada. Apaga as cotas das metades iguais e devolve quantas."""
    segs = []
    for k in cotas_nos:
        c = desenho.entidades.get(k)
        if c is None:
            continue
        xa, xb = sorted((c.p1[0] - dx, c.p2[0] - dx))
        segs.append((xa, xb, math.dist(c.p1, c.p2), k))
    tirar = set()
    for sup in sups_cotados:
        s_ = sorted(sup)
        for s0, s1 in zip(s_, s_[1:]):
            dentro = sorted((sg for sg in segs if sg[0] >= s0 - NO_NO_SUPORTE and sg[1] <= s1 + NO_NO_SUPORTE),
                            key=lambda sg: sg[0])
            if len(dentro) != 2:
                continue
            (a0, a1, la, ka), (b0, b1, lb, kb) = dentro
            encadeadas = (abs(a0 - s0) <= NO_NO_SUPORTE and abs(a1 - b0) <= 1.0 and abs(b1 - s1) <= NO_NO_SUPORTE)
            if encadeadas and abs(la - lb) <= METADES_IGUAIS + 0.01:
                tirar.update((ka, kb))
    for k in tirar:
        desenho.entidades.pop(k, None)
    return len(tirar)


def tesouras_montadas(meias: Sequence[tuple]) -> Tuple[List[dict], set]:
    """Tesouras inteiras a partir das meias. `meias` = [(rótulo da célula, peças do
    conjunto, composição unitária)]; cada instância de meia é posta no plano dela (a
    distância do centro ao longo da normal), e as que caem no mesmo plano formam uma
    tesoura montada — é assim que a fábrica gabarita: as duas águas juntas. Tesouras
    montadas com as mesmas meias (os mesmos rótulos) viram uma só, com a quantidade.

    Devolve ([{"rotulos": (…), "pecas": [peças da primeira], "n": quantas}], rótulos que
    ficaram inteiramente dentro de tesouras montadas)."""
    insts = []                                       # (rótulo, peças, normal, d, centro)
    for rotulo, lista, unidade in meias:
        for g in _instancias_do_conjunto(lista, unidade):
            c, _u, _v, w = _eixos_do_conjunto(g)
            k = max(range(3), key=lambda i: abs(w[i]))
            if w[k] < 0:
                w = (-w[0], -w[1], -w[2])
            insts.append((rotulo, g, w, _dot(c, w), c))
    insts.sort(key=lambda t: t[3])
    planos: List[list] = []
    for t in insts:
        alvo = next((pl for pl in planos if abs(t[3] - pl[0][3]) <= TOLERANCIA_PLANO_TESOURA
                     and abs(_dot(t[2], pl[0][2])) > 0.99), None)
        if alvo is None:
            planos.append([t])
        else:
            alvo.append(t)
    # no mesmo plano e encostadas: o plano dividido nos grupos de meias que se tocam
    juntos: List[list] = []
    for pl in planos:
        caixas = [_caixa_de_pecas(t[1]) for t in pl]
        pai = list(range(len(pl)))

        def raiz(i):
            while pai[i] != i:
                pai[i] = pai[pai[i]]
                i = pai[i]
            return i
        for i in range(len(pl)):
            for j in range(i + 1, len(pl)):
                if all(caixas[i][k][0] - FOLGA_MEIAS_MONTADAS <= caixas[j][k][1] and
                       caixas[j][k][0] - FOLGA_MEIAS_MONTADAS <= caixas[i][k][1] for k in range(3)):
                    pai[raiz(i)] = raiz(j)
        por_raiz: Dict[int, list] = collections.OrderedDict()
        for i, t in enumerate(pl):
            por_raiz.setdefault(raiz(i), []).append(t)
        juntos.extend(por_raiz.values())
    montadas: Dict[tuple, dict] = collections.OrderedDict()
    fora = collections.Counter()                     # instâncias que não formaram par
    total = collections.Counter(t[0] for t in insts)
    for pl in juntos:
        if len(pl) < 2 or _faixa_reta([e for t in pl for e in t[1]], pl[0][2]):
            # sem par, ou as "meias" são trechos de uma faixa reta (as vigas-caixa emendadas em linha do Vicente,
            # 08/10): cada uma é a peça de fábrica e sai na célula dela; a montada só junta as águas de uma tesoura
            for t in pl:
                fora[t[0]] += 1
            continue
        # da esquerda para a direita no desenho (ao longo do vão)
        pl.sort(key=lambda t: t[4][0] + t[4][1])
        chave = tuple(sorted(t[0] for t in pl))
        m = montadas.setdefault(chave, {"rotulos": chave, "pecas": [e for t in pl for e in t[1]], "n": 0, "instancias": []})
        m["n"] += 1
        # cada montada no lugar: as meias dela (a marca e as peças) e o meio — o Controle de produção aponta a montada
        # inteira e acende as peças dela no 3D (usuário 13/11: "as partes só serão apontadas juntas com o conjunto inteiro")
        pts = [t[4] for t in pl]
        m["instancias"].append({
            "meias": [{"marca": collections.Counter(str(_marcas(e).get("conjunto") or "") for e in t[1]).most_common(1)[0][0],
                       "ids": [str(e.id) for e in t[1]]} for t in pl],
            "meio": [round(sum(c[k] for c in pts) / len(pts), 1) for k in range(3)]})
    cobertos = {r for r in total if not fora.get(r)} if montadas else set()
    return list(montadas.values()), cobertos
