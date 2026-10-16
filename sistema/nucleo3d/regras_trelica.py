# -*- coding: utf-8 -*-
"""Regras de posição das peças da treliça de aço — uma regra só para todo gerador (16/10/2026).

O usuário (16/10): "o sistema continua gerando peças com perfil errado, aleatório… toda vez que gera uma tesoura nova volta
com a configuração antiga, perfis de canto com a boca virada para o lado errado; tornar regras do sistema". Até aqui cada
gerador girava as peças do seu jeito (de_planta_estrutura seguia as regras de 07–12/10; a treliça entre banzos do editor, o
galpão e os scripts deixavam o giro 0 — a cantoneira com a aba para um lado ou para o outro conforme o sentido da barra, o U
de canto com a boca para fora). Este módulo diz, peça a peça, como a seção fica; `orientar` aplica e `conferir` acusa —
todo gerador chama `orientar` no fim e o teste (testes/test_regras_trelica.py) gera tesouras por todos os caminhos e falha
se alguma peça sair da regra.

As regras (eixos da seção como em geometria.base_local: w ao longo da barra, u = para onde o U abre / a 1ª aba da
cantoneira, v = a altura do perfil / a 2ª aba):

  T1  Cada treliça tem um plano; n é a normal dele, com o sinal fixo (+x, senão +y, senão +z): todas as peças da mesma
      treliça usam o mesmo n.
  T2  Banzo em U/Ue: a altura do perfil atravessa o plano (v ∥ n) e a boca (u) fica no plano, virada para o miolo — o lado
      de onde chegam as barras da alma ligadas a ele (regra do usuário 07/10 e 11/10); sem alma ligada, para o centro da
      treliça.
  T3  Peça em pé em U/Ue (montante, extremidade, o canto da platibanda): v ∥ n e a boca para o meio do vão da treliça —
      o montante de canto abre para dentro, nunca para fora (usuário 11/10 e 16/10).
  T4  Diagonal em U/Ue: v ∥ n e a boca no plano, para cima (a deitada, para o meio do vão) — usuário 11/10.
  T5  Cantoneira simples da alma: uma aba atravessando o plano, sempre para o mesmo lado (u = +n), a outra no plano
      (usuário 07/10: "ficam sempre do mesmo lado do plano"); nunca pelo sentido em que a barra foi desenhada.

Ficam de fora (não são peças da treliça plana ou têm regra própria): cantoneira dupla (o par espelhado do gerador),
presilha, barra secundária "um lado só", tubos, barras redondas e perfis I/W. A peça que o usuário virou de propósito
(`atributos.boca_virada`, o "virar" do painel Perfis da tesoura) entra na treliça mas não é girada nem acusada.
"""
from __future__ import annotations

import collections
import math
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Ponto = Tuple[float, float, float]

PAPEIS_TRELICA = {"banzo", "montante", "diagonal", "extremidade"}
_FORA = {"presilha", "secundaria"}
TOL_LIGA = 60.0          # mm: a ponta de uma barra a até isso de outra barra está ligada nela (nó da treliça)
TOL_PLANO = 0.02         # a 3ª dimensão do grupo (desvio padrão / tamanho) acima disso: não é uma treliça plana
EM_PE = 60.0             # graus: barra a mais que isso do banzo é peça em pé (montante)


# ------------------------------------------------------------------ vetores
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sinal_fixo(v):
    """o sinal de um eixo independente do sentido em que a barra foi desenhada (+x, senão +y, senão +z)"""
    for k in (0, 1, 2):
        if abs(v[k]) > 0.3:
            return _mul(v, -1.0) if v[k] < 0 else v
    return v


def _no_plano(v, w):
    """a parte de v perpendicular a w"""
    return _sub(v, _mul(w, _dot(v, w)))


# ------------------------------------------------------------------ o tipo da seção
def forma(perfil: str) -> Optional[str]:
    """'U' (U e Ue: a seção tem boca), 'L' (cantoneira simples) ou None (fora da regra)"""
    p = str(perfil or "").strip()
    if re.match(r"(?i)^ue?\s", p):
        return "U"
    if re.match(r"(?i)^l\s", p):
        return "L"
    return None


def _papel(b) -> Optional[str]:
    a = getattr(b, "atributos", None) or {}
    pt = str(a.get("papel_trelica") or "")
    if pt in _FORA or a.get("um_lado_so") or a.get("cantoneira_dupla") or a.get("secao_dupla"):
        return None
    pp = str(getattr(b, "papel", "") or "")
    if pp in _FORA:
        return None
    if pt.startswith("banzo"):
        return "banzo"
    if pt in ("montante", "diagonal", "extremidade"):
        return pt
    if pp in PAPEIS_TRELICA:
        return pp
    return None


# ------------------------------------------------------------------ as treliças do modelo
def _chave_grupo(b) -> Optional[tuple]:
    a = getattr(b, "atributos", None) or {}
    o = a.get("origem") if isinstance(a.get("origem"), dict) else {}
    for k in ("origem_2d", "conjunto"):
        if a.get(k):
            return (k, str(a[k]))
    if a.get("portico") is not None:
        return ("portico", str(a.get("portico")), str(a.get("agua") or ""))
    if o.get("peca"):
        return ("peca", str(o.get("peca")))
    return ("solta",)


def _dist_pt_seg(p, a, b) -> float:
    ab = _sub(b, a)
    L2 = _dot(ab, ab)
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, _dot(_sub(p, a), ab) / L2))
    q = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
    return math.dist(p, q)


def _componentes(barras: List) -> List[List]:
    """as barras ligadas (ponta com ponta, ou ponta no meio de outra) — cada treliça física"""
    n = len(barras)
    pai = list(range(n))

    def acha(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    # só compara barras cujas caixas (com a folga) se tocam: grade de 2 m
    CEL = 2000.0
    grade = collections.defaultdict(list)
    caixas = []
    for i, b in enumerate(barras):
        lo = [min(b.inicio[k], b.fim[k]) - TOL_LIGA for k in range(3)]
        hi = [max(b.inicio[k], b.fim[k]) + TOL_LIGA for k in range(3)]
        caixas.append((lo, hi))
        for gx in range(int(math.floor(lo[0] / CEL)), int(math.floor(hi[0] / CEL)) + 1):
            for gy in range(int(math.floor(lo[1] / CEL)), int(math.floor(hi[1] / CEL)) + 1):
                for gz in range(int(math.floor(lo[2] / CEL)), int(math.floor(hi[2] / CEL)) + 1):
                    grade[(gx, gy, gz)].append(i)
    vizinhos = collections.defaultdict(set)
    for ids in grade.values():
        for x in ids:
            vizinhos[x].update(ids)
    for i in range(n):
        bi = barras[i]
        for j in vizinhos[i]:
            if j <= i:
                continue
            bj = barras[j]
            if acha(i) == acha(j):
                continue
            (la, ha), (lb, hb) = caixas[i], caixas[j]
            if any(ha[k] < lb[k] or hb[k] < la[k] for k in range(3)):
                continue
            if (min(_dist_pt_seg(bi.inicio, bj.inicio, bj.fim), _dist_pt_seg(bi.fim, bj.inicio, bj.fim),
                    _dist_pt_seg(bj.inicio, bi.inicio, bi.fim), _dist_pt_seg(bj.fim, bi.inicio, bi.fim)) <= TOL_LIGA):
                pai[acha(i)] = acha(j)
    grupos = collections.defaultdict(list)
    for i in range(n):
        grupos[acha(i)].append(barras[i])
    return list(grupos.values())


def _normal(barras: List) -> Optional[Tuple[Ponto, Ponto]]:
    """(n, centro) do plano das barras pelo menor eixo de inércia dos pontos; None se não for plano"""
    pts = [p for b in barras for p in (tuple(b.inicio), tuple(b.fim))]
    if len(pts) < 3:
        return None
    c = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
    M = [[0.0] * 3 for _ in range(3)]
    for p in pts:
        d = _sub(p, c)
        for i in range(3):
            for j in range(3):
                M[i][j] += d[i] * d[j]
    try:
        import numpy as np
        val, vec = np.linalg.eigh(np.array(M))
    except Exception:                                    # noqa: BLE001
        return None
    if val[2] <= 0:
        return None
    if math.sqrt(max(val[0], 0.0)) > TOL_PLANO * math.sqrt(val[2]) + 1.0:
        return None                                       # não é plano: peças de mais de uma treliça, ou torta
    n = _sinal_fixo(tuple(float(x) for x in vec[:, 0]))          # T1: o sinal fixo da normal
    return _unit(n), c


def _sem_pares(barras: List) -> List:
    """tira os perfis duplos (2L, 2U): duas barras do mesmo perfil, paralelas, lado a lado (a até 250 mm, a mesma faixa
    ao longo) — o par espelhado tem regra própria no gerador, não é a cantoneira simples da T5"""
    fora = set()
    por_perfil = collections.defaultdict(list)
    for b in barras:
        por_perfil[str(b.perfil)].append(b)
    for lista in por_perfil.values():
        if len(lista) < 2:
            continue
        for i, a in enumerate(lista):
            wa = _unit(_sub(a.fim, a.inicio))
            ma = tuple((a.inicio[k] + a.fim[k]) / 2.0 for k in range(3))
            La = math.dist(a.inicio, a.fim)
            for b in lista[i + 1:]:
                wb = _unit(_sub(b.fim, b.inicio))
                if abs(_dot(wa, wb)) < 0.995:
                    continue
                mb = tuple((b.inicio[k] + b.fim[k]) / 2.0 for k in range(3))
                d = _sub(mb, ma)
                if abs(_dot(d, wa)) > 0.25 * La or math.sqrt(max(_dot(d, d) - _dot(d, wa) ** 2, 0.0)) > 250.0:
                    continue
                if abs(math.dist(b.inicio, b.fim) - La) > 0.25 * La:
                    continue
                fora.update((id(a), id(b)))
    return [b for b in barras if id(b) not in fora]


def trelicas(entidades: Iterable, por_grupo: bool = True) -> List[dict]:
    """[{n, centro, eixo (a direção dos banzos), barras: [(barra, papel)]}] — cada treliça plana do modelo.
    `por_grupo=False`: as barras dadas são de uma treliça só (o gerador passa as que acabou de fazer) — não separa pelo
    bloco/conjunto, só pelas ligações"""
    from nucleo3d.modelo import Barra
    por_chave = collections.defaultdict(list)
    for e in entidades:
        if not isinstance(e, Barra):
            continue
        pap = _papel(e)
        if pap is None or math.dist(e.inicio, e.fim) < 1.0:
            continue
        por_chave[_chave_grupo(e) if por_grupo else ("todas",)].append(e)
    out = []
    for _k, lista in por_chave.items():
        for comp in _componentes(lista):
            if len(comp) < 3:
                continue
            pl = _normal(comp)
            if pl is None:
                continue
            n, c = pl
            # o eixo e o vão pelos banzos de todas as barras (o banzo em caixão — dois U lado a lado — é par e sai da
            # lista, mas é ele que diz a direção da treliça: a viga de transição do Posto)
            banzos = [b for b in comp if _papel(b) == "banzo"]
            ref = banzos or comp
            comp = _sem_pares(comp)
            # o eixo da treliça: a direção (no plano) do banzo mais comprido
            maior = max(ref, key=lambda b: math.dist(b.inicio, b.fim))
            eixo = _sinal_fixo(_unit(_no_plano(_unit(_sub(maior.fim, maior.inicio)), n)))
            # o meio do vão: o meio da extensão das barras ao longo do eixo (não o centroide, que anda com a alma)
            proj = [_dot(p, eixo) for b in ref + comp for p in (b.inicio, b.fim)]
            meio = _add(_no_plano(c, eixo), _mul(eixo, (min(proj) + max(proj)) / 2.0))
            t = {"n": n, "centro": c, "eixo": eixo, "meio": meio, "vao": max(proj) - min(proj),
                 "barras": [(b, _papel(b)) for b in comp]}
            t["lado_L"] = _lado_da_maioria(t)
            out.append(t)
    return out


def lado_da_aba(b, n) -> int:
    """T5: para que lado do plano sai a aba da cantoneira que atravessa o plano (+1, −1; 0 = nenhuma atravessa: torta)"""
    u, v, _w = _eixos(b)
    for e in (u, v):
        c = _dot(e, n)
        if abs(c) > 0.9:
            return 1 if c > 0 else -1
    return 0


def _lado_da_maioria(t) -> float:
    """o lado em que fica a aba das cantoneiras simples desta treliça: o da maioria (empate: +n)"""
    soma = 0
    for b, p in t["barras"]:
        if p != "banzo" and forma(b.perfil) == "L":
            soma += lado_da_aba(b, t["n"])
    return -1.0 if soma < 0 else 1.0


# ------------------------------------------------------------------ o giro de cada peça
def _giro_para(w, alvo) -> float:
    """o giro (graus) da barra de direção w que leva o eixo u da seção a `alvo` (geometria.base_local)"""
    from nucleo3d.geometria import base_local
    u0, v0, _ = base_local(w, 0.0)
    return math.degrees(math.atan2(_dot(alvo, v0), _dot(alvo, u0))) % 360.0


def _eixos(b) -> Tuple[Ponto, Ponto, Ponto]:
    from nucleo3d.geometria import base_local
    return base_local(_unit(_sub(b.fim, b.inicio)), float(getattr(b, "rotacao", 0.0) or 0.0))


def _em_pe(b, t) -> bool:
    w = _unit(_sub(b.fim, b.inicio))
    return abs(_dot(w, t["eixo"])) < math.cos(math.radians(EM_PE))


def _miolo_do_banzo(b, t) -> Optional[Ponto]:
    """T2: o lado (no plano) de onde chegam as barras da alma ligadas ao banzo; sem ligação, o centro da treliça; None
    quando chegam tantas de um lado quanto do outro (o banzo do meio, entre dois painéis: fica como o gerador fez)"""
    w = _unit(_sub(b.fim, b.inicio))
    lado = _unit(_cross(t["n"], w))                       # perpendicular ao banzo, no plano
    soma = 0.0
    ligadas = 0
    for o, pap in t["barras"]:
        if o is b or pap == "banzo":
            continue
        for p, q in ((o.inicio, o.fim), (o.fim, o.inicio)):
            if _dist_pt_seg(p, b.inicio, b.fim) <= TOL_LIGA:
                s = _dot(_sub(q, p), lado)
                if abs(s) > 1.0:
                    soma += 1.0 if s > 0 else -1.0
                    ligadas += 1
                break
        else:
            # o montante que passa pela ponta do banzo (o banzo morre no meio dele): sai para os dois lados
            if any(_dist_pt_seg(p, o.inicio, o.fim) <= TOL_LIGA for p in (b.inicio, b.fim)):
                ligadas += 2
    if ligadas and abs(soma) < 0.5:
        return None
    if abs(soma) < 0.5:
        mid = tuple((b.inicio[k] + b.fim[k]) / 2.0 for k in range(3))
        soma = _dot(_sub(t["centro"], mid), lado)
    return lado if soma >= 0 else _mul(lado, -1.0)


def alvo_u(b, papel: str, t: dict) -> Optional[Ponto]:
    """a direção em que o eixo u da seção deve ficar, pela regra; None se a peça está fora da regra"""
    f = forma(getattr(b, "perfil", ""))
    if f is None:
        return None
    w = _unit(_sub(b.fim, b.inicio))
    n = t["n"]
    if f == "L":
        if papel == "banzo":
            return None                                   # banzo em cantoneira: fora destas regras
        return _mul(n, t.get("lado_L", 1.0))              # T5: a aba que sai do plano, do lado da treliça
    # U / Ue
    if papel == "banzo":
        return _miolo_do_banzo(b, t)                      # T2
    lado = _unit(_cross(n, w))                            # perpendicular à peça, no plano
    if _em_pe(b, t) or papel in ("montante", "extremidade"):
        mid = tuple((b.inicio[k] + b.fim[k]) / 2.0 for k in range(3))
        d = _dot(_sub(t.get("meio", t["centro"]), mid), t["eixo"])
        if abs(d) < 25.0:
            d = 1.0                                       # o montante no meio do vão: para +eixo (o sinal fixo)
        para_o_meio = d * _dot(lado, t["eixo"])
        return lado if para_o_meio >= 0 else _mul(lado, -1.0)          # T3
    if abs(lado[2]) > 0.3:                                # T4: para cima
        return lado if lado[2] > 0 else _mul(lado, -1.0)
    mid = tuple((b.inicio[k] + b.fim[k]) / 2.0 for k in range(3))
    return lado if _dot(_sub(t["centro"], mid), lado) >= 0 else _mul(lado, -1.0)


REGRA = {"banzo": "T2", "montante": "T3", "extremidade": "T3", "diagonal": "T4"}


def _regra(b, papel, t) -> str:
    if forma(b.perfil) == "L":
        return "T5"
    if papel == "diagonal" and _em_pe(b, t):
        return "T3"
    return REGRA.get(papel, "T2")


# ------------------------------------------------------------------ aplicar e conferir
def _giro_da_cantoneira(b, w, alvo, n) -> float:
    """T5: dos giros que põem uma aba atravessando o plano para o lado `alvo`, o que deixa a outra aba (a deitada no
    plano) para onde ela já estava — a ponta em cantoneira continua com a aba deitada para dentro da tesoura"""
    from nucleo3d.geometria import base_local
    u0, v0, _ = _eixos(b)
    deitada = u0 if abs(_dot(u0, n)) < abs(_dot(v0, n)) else v0
    base = _giro_para(w, alvo)
    melhor, nota = round(base, 3), -9.0
    for d in (0.0, 90.0, -90.0, 180.0):
        g = (base + d) % 360.0
        u, v, _w = base_local(w, g)
        cruza, outra = (u, v) if abs(_dot(u, n)) > abs(_dot(v, n)) else (v, u)
        if _dot(cruza, alvo) < 0.9:
            continue
        if _dot(outra, deitada) > nota:
            melhor, nota = round(g, 3), _dot(outra, deitada)
    return melhor


def _virada(b) -> bool:
    return bool((getattr(b, "atributos", None) or {}).get("boca_virada"))


def orientar(entidades: Iterable, por_grupo: bool = True) -> int:
    """gira cada peça das treliças pela regra; devolve quantas mudaram"""
    lista = list(entidades)
    mudou = 0
    for t in trelicas(lista, por_grupo):
        for b, papel in t["barras"]:
            if _virada(b):
                continue
            alvo = alvo_u(b, papel, t)
            if alvo is None:
                continue
            w = _unit(_sub(b.fim, b.inicio))
            if forma(b.perfil) == "L":
                if lado_da_aba(b, t["n"]) == int(t["lado_L"]):
                    continue                              # T5 já cumprida (a aba certa do lado certo)
                g = _giro_da_cantoneira(b, w, alvo, t["n"])
            else:
                g = round(_giro_para(w, alvo), 3)
            atual = float(getattr(b, "rotacao", 0.0) or 0.0) % 360.0
            if abs(((g - atual) + 180.0) % 360.0 - 180.0) > 0.5:
                b.rotacao = g
                mudou += 1
    return mudou


def conferir(entidades: Iterable, tol_graus: float = 5.0, por_grupo: bool = True) -> List[dict]:
    """as peças fora da regra: [{id, nome, perfil, papel, regra, erro_graus, ponto}]"""
    out = []
    cos_tol = math.cos(math.radians(tol_graus))
    for t in trelicas(list(entidades), por_grupo):
        for b, papel in t["barras"]:
            if _virada(b):
                continue
            alvo = alvo_u(b, papel, t)
            if alvo is None:
                continue
            u, v, w = _eixos(b)
            if forma(b.perfil) == "L":
                # T5: tanto faz qual das abas (abas iguais: girar 90° só espelha), vale o lado da que sai do plano
                if lado_da_aba(b, t["n"]) == int(t["lado_L"]):
                    continue
                out.append({"id": b.id, "nome": b.nome, "perfil": b.perfil, "papel": papel, "regra": "T5",
                            "erro_graus": 180.0 if lado_da_aba(b, t["n"]) else 90.0, "ponto": [round(x) for x in b.inicio]})
                continue
            c = _dot(u, alvo)
            if c < cos_tol:
                out.append({"id": b.id, "nome": b.nome, "perfil": b.perfil, "papel": papel, "regra": _regra(b, papel, t),
                            "erro_graus": round(math.degrees(math.acos(max(-1.0, min(1.0, c)))), 1),
                            "ponto": [round(x) for x in b.inicio]})
    return out


TEXTO_REGRAS = __doc__
