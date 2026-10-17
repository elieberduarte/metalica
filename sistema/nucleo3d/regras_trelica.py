# -*- coding: utf-8 -*-
"""Regras de montagem da treliça de aço — o que cada peça é e como fica (uma regra só para todo gerador).

O usuário (16/10): "o sistema continua gerando peças com perfil errado, aleatório… toda vez que gera uma tesoura nova volta
com a configuração antiga… tornar regras do sistema". As regras foram recriadas e aprovadas por ele em 16/10 à noite
(Projeto/ANALISES/Montagem/Regras-de-montagem-das-tesouras-revisao-geral-2026-10-16.docx, com as respostas). Todo gerador
chama `aplicar` (classificar + orientar) antes do encaixe de fábrica; `conferir` acusa, na conferência do 3D e no Verificar
apoios; testes/test_regras_trelica.py gera por todos os caminhos e cai se alguma peça sair da regra.

Eixos da seção como em geometria.base_local: w ao longo da barra, u = para onde o U abre (a 1ª aba da cantoneira),
v = a altura do perfil (a 2ª aba).

1. O QUE É CADA PEÇA (pelo contorno, não pelo nome que veio do desenho)
  1.2  Banzo superior = toda peça deitada/inclinada no contorno de cima da treliça (nada da treliça acima dela) — também o
       topo do painel de ponta que o desenho chamou de "diagonal". Vira papel "banzo" e recebe o perfil do banzo.
  1.4  Ponta = a peça em pé que fecha a treliça em cada apoio: recebe o perfil do banzo ("as pontas sempre devem seguir o
       perfil do banzo"). A peça cujo perfil veio da legenda do projeto (`perfil_do_projeto`) não muda: o projeto manda.

2. COMO CADA PEÇA FICA — princípio único: a treliça se fecha para dentro
  2.0  Um plano por treliça; n é a normal dele com o sinal fixo (+x, senão +y, senão +z). Nada depende do sentido da linha.
  2.1  Todo U/Ue com a alma atravessando o plano (as abas no plano): v ∥ n.
  2.2  Banzos abrem para dentro: o de cima para baixo, o de baixo para cima (o lado das peças da alma ligadas). O banzo
       intermediário (alma dos dois lados) abre para cima. Consequência: nenhum banzo de cima abre para cima.
  2.3  Peças da alma (ponta, montante, diagonal) abrem para o meio do vão; a diagonal NUNCA para cima (a perpendicular que
       desce); o montante no meio exato do vão abre para a ponta alta. A ponta e o canto abrem para dentro.
  2.4  Cantoneira simples = um U cortado ao meio: a aba que atravessa o plano sempre do mesmo lado (+n, o mesmo em toda a
       obra); a aba deitada no plano aponta para onde a boca do U apontaria (2.2/2.3).
  2.5  Cantoneira em par = um U partido: uma em cada aba do banzo, a aba que atravessa o plano apontando para o centro
       (uma de cada lado), as abas deitadas as duas na direção da boca (2.3); presilhas entre elas (norma 5.3.6.1).
  2.6  U deitado fora da treliça (escora, viga lateral) nunca abre para cima — fica com o gerador.
  2.7  A peça virada de propósito (`atributos.boca_virada`, o "virar" do painel) fica com a boca ao contrário da regra.
  2.8  Fora destas regras: tubos, barras redondas, I/W, a barra secundária "um lado só", a presilha, o banzo composto/caixa
       (`secao_dupla`, pelo croqui da legenda).

3. FÁBRICA
  3.1  Nada atravessa o banzo: a ponta da alma (montante, diagonal) para na face do banzo, cortada no plano dela
       (meia-esquadria), com bico no montante e bissetriz entre diagonais (nucleo3d/alma_na_face.encaixar). O nó de
       cálculo continua no eixo do banzo; o corte é da peça. Adendos de 16/10 (usuário: "algumas diagonais não passaram
       a regra dos recortes, ainda estão com a ponta furando o banzo"):
  3.1a O encaixe faz parte da regra: `aplicar` encaixa depois de classificar, orientar e recuar — vale para todo gerador
       e todo script de obra, sem depender de cada um lembrar de chamar. A conferência acusa a ponta de alma que chega
       num banzo com material além da face dele e sem o corte ("3.1", com os mm que furam).
  3.1b O trecho de alma que cabe inteiro dentro do material do(s) banzo(s) (o corte das duas pontas soma mais que o
       comprimento dele) não é peça. Se é um montante partido e nenhuma outra peça chega na emenda, o trecho vizinho
       alinhado vai até o nó (UMA peça de banzo a banzo); se a emenda é um nó (o degrau de 50 mm entre o topo do painel
       de ponta e o banzo inclinado, no corte CC do Mercado), o trecho só sai — os banzos já se tocam. `juntar_trechos`
       devolve os trechos; quem tira a peça do modelo é quem monta. A conferência acusa ("3.1", peça dentro do banzo).

4. O ENTORNO DA TESOURA
  4.8  Encontro da tesoura com platibanda ou fechamento (a peça que chega × a peça que passa) — usuário, 16/10: "o final da
       tesoura nunca pode invadir a platibanda, deve sempre parar na face interna". A platibanda é a peça contínua; a
       tesoura é a interrompida. O limite da tesoura é o plano da face interna da platibanda (a face do perfil dela voltada
       para a tesoura) deslocado da folga de montagem FOLGA_FACE: nenhuma peça da tesoura (banzos, montante de ponta,
       diagonal de ponta) tem material além desse plano — o montante de ponta fica paralelo à face, com a sua face externa
       na folga; os banzos e a diagonal param no eixo do montante de ponta, cortados no ângulo quando chegam inclinados.
       A platibanda não muda. Vale para qualquer treliça que passa (treliça de cumeeira, viga de transição): a que chega para
       na face da que passa. Só recua, nunca prolonga (a tesoura que termina antes da platibanda fica como está).
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
    if pt in _FORA or a.get("um_lado_so") or a.get("secao_dupla"):
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


def _pares(barras: List, n: Ponto, centro: Ponto) -> Dict[int, int]:
    """2.5: os pares de cantoneiras (mesmo perfil, paralelas, lado a lado a até 250 mm, a mesma faixa ao longo):
    {id(barra): lado} com lado = +1/−1, de que lado do plano a cantoneira está (pelo afastamento; se encostadas no plano,
    pelo atributo cantoneira_dupla a/b do gerador)"""
    out = {}
    por_perfil = collections.defaultdict(list)
    for b in barras:
        if forma(b.perfil) == "L":
            por_perfil[str(b.perfil)].append(b)
    for lista in por_perfil.values():
        for i, a in enumerate(lista):
            wa = _unit(_sub(a.fim, a.inicio))
            ma = tuple((a.inicio[k] + a.fim[k]) / 2.0 for k in range(3))
            La = math.dist(a.inicio, a.fim)
            for b in lista[i + 1:]:
                if id(a) in out and id(b) in out:
                    continue
                wb = _unit(_sub(b.fim, b.inicio))
                if abs(_dot(wa, wb)) < 0.995:
                    continue
                mb = tuple((b.inicio[k] + b.fim[k]) / 2.0 for k in range(3))
                d = _sub(mb, ma)
                if abs(_dot(d, wa)) > 0.25 * La or math.sqrt(max(_dot(d, d) - _dot(d, wa) ** 2, 0.0)) > 250.0:
                    continue
                if abs(math.dist(b.inicio, b.fim) - La) > 0.25 * La:
                    continue
                da, db = _dot(_sub(ma, centro), n), _dot(_sub(mb, centro), n)
                if abs(da - db) > 1.0:
                    out[id(a)], out[id(b)] = (1 if da > db else -1), (1 if db > da else -1)
                else:
                    la = str((getattr(a, "atributos", None) or {}).get("cantoneira_dupla") or "a")
                    out[id(a)] = -1 if la == "a" else 1
                    out[id(b)] = -out[id(a)]
    return out


def trelicas(entidades: Iterable, por_grupo: bool = True) -> List[dict]:
    """[{n, centro, eixo, meio, vao, alta, barras: [(barra, papel)], par: {id: lado}, vultos}] — cada treliça plana do modelo.
    `por_grupo=False`: as barras dadas são de uma treliça só (o gerador passa as que acabou de fazer) — não separa pelo
    bloco/conjunto, só pelas ligações"""
    from nucleo3d.modelo import Barra
    por_chave = collections.defaultdict(list)
    vultos = collections.defaultdict(list)             # todas as barras da treliça, também as de regra própria (o
    for e in entidades:                                # banzo composto): o que está acima de uma peça (1.2)
        if not isinstance(e, Barra):
            continue
        a_ = getattr(e, "atributos", None) or {}
        if (str(a_.get("papel_trelica") or "") or str(getattr(e, "papel", "") or "")).startswith(
                ("banzo", "montante", "diagonal", "extremidade")):
            vultos[_chave_grupo(e) if por_grupo else ("todas",)].append(e)
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
            banzos = [b for b in comp if _papel(b) == "banzo"]
            ref = banzos or comp
            # o eixo da treliça: a direção (no plano) do banzo mais comprido, com o sinal fixo
            maior = max(ref, key=lambda b: math.dist(b.inicio, b.fim))
            eixo = _sinal_fixo(_unit(_no_plano(_unit(_sub(maior.fim, maior.inicio)), n)))
            # o meio do vão: o meio da extensão das barras ao longo do eixo (não o centroide, que anda com a alma)
            pts = [p for b in comp for p in (b.inicio, b.fim)]
            proj = [_dot(p, eixo) for p in pts]
            lo_p, hi_p = min(proj), max(proj)
            meio = _add(_no_plano(c, eixo), _mul(eixo, (lo_p + hi_p) / 2.0))
            # a ponta alta: a ponta em que o contorno de cima está mais alto (empate: +eixo)
            up = _no_plano((0.0, 0.0, 1.0), n)
            z0 = max((_dot(p, up) for p, q in zip(pts, proj) if q < lo_p + 300.0), default=0.0)
            z1 = max((_dot(p, up) for p, q in zip(pts, proj) if q > hi_p - 300.0), default=0.0)
            alta = _mul(eixo, -1.0) if z0 > z1 + 20.0 else eixo
            lo = [min(min(b.inicio[k], b.fim[k]) for b in comp) - 300.0 for k in range(3)]
            hi = [max(max(b.inicio[k], b.fim[k]) for b in comp) + 300.0 for k in range(3)]
            dentro = [o for o in vultos[_k] if all(min(o.inicio[k], o.fim[k]) <= hi[k] and max(o.inicio[k], o.fim[k]) >= lo[k]
                                                   for k in range(3))
                      and abs(_dot(_sub(o.inicio, c), n)) < 300.0 and abs(_dot(_sub(o.fim, c), n)) < 300.0]
            out.append({"n": n, "centro": c, "eixo": eixo, "meio": meio, "vao": hi_p - lo_p, "alta": alta,
                        "barras": [(b, _papel(b)) for b in comp], "par": _pares(comp, n, c), "vultos": dentro})
    return out


def lado_da_aba(b, n) -> int:
    """2.4/2.5: para que lado do plano sai a aba da cantoneira que atravessa o plano (+1, −1; 0 = nenhuma: torta)"""
    u, v, _w = _eixos(b)
    for e in (u, v):
        c = _dot(e, n)
        if abs(c) > 0.9:
            return 1 if c > 0 else -1
    return 0


def _aba_deitada(b, n) -> Ponto:
    """a aba da cantoneira que fica no plano"""
    u, v, _w = _eixos(b)
    return v if abs(_dot(u, n)) > abs(_dot(v, n)) else u


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


def _mid(b) -> Ponto:
    return tuple((b.inicio[k] + b.fim[k]) / 2.0 for k in range(3))


def _cima(t) -> Optional[Ponto]:
    """o "para cima" no plano da treliça (None quando o plano é deitado: não há cima)"""
    up = _no_plano((0.0, 0.0, 1.0), t["n"])
    return _unit(up) if math.sqrt(_dot(up, up)) > 0.5 else None


def _miolo_do_banzo(b, t) -> Ponto:
    """2.2: o lado (no plano) de onde chegam as peças da alma ligadas ao banzo; ligadas dos dois lados (o banzo
    intermediário) → para cima; sem ligação → o centro da treliça"""
    w = _unit(_sub(b.fim, b.inicio))
    lado = _unit(_cross(t["n"], w))                       # perpendicular ao banzo, no plano
    mais, menos = 0, 0                                    # peças da alma ligadas, de cada lado do banzo
    for o, pap in t["barras"]:
        if o is b or pap == "banzo":
            continue
        for p, q in ((o.inicio, o.fim), (o.fim, o.inicio)):
            if _dist_pt_seg(p, b.inicio, b.fim) <= TOL_LIGA:
                s = _dot(_sub(q, p), lado)
                if s > 1.0:
                    mais += 1
                elif s < -1.0:
                    menos += 1
                break
        else:
            # o montante que passa pela ponta do banzo (o banzo morre no meio dele): sai para os dois lados
            if any(_dist_pt_seg(p, o.inicio, o.fim) <= TOL_LIGA for p in (b.inicio, b.fim)):
                mais += 1
                menos += 1
    if mais and menos:                                    # o banzo intermediário (decisão 3): para cima
        up = _cima(t)
        if up is not None:
            return lado if _dot(lado, up) > 0 else _mul(lado, -1.0)
    soma = float(mais - menos) if (mais or menos) else _dot(_sub(t["centro"], _mid(b)), lado)
    return lado if soma >= 0 else _mul(lado, -1.0)


def no_topo(b, t) -> bool:
    """1.2: a peça deitada sem nada da treliça acima do meio dela — o contorno de cima (o banzo superior)"""
    up = _cima(t)
    if up is None or _em_pe(b, t):
        return False
    h_ax = _unit(_cross(t["n"], up))                      # a horizontal no plano
    mid = _mid(b)
    hm, ym = _dot(mid, h_ax), _dot(mid, up)
    for o in t.get("vultos") or [o for o, _p in t["barras"]]:
        if o is b:
            continue
        h0, h1 = _dot(o.inicio, h_ax), _dot(o.fim, h_ax)
        y0, y1 = _dot(o.inicio, up), _dot(o.fim, up)
        if abs(h1 - h0) < 1.0:                            # em pé exatamente no meio dela
            if abs(h0 - hm) < 1.0 and max(y0, y1) > ym + 30.0:
                return False
            continue
        if min(h0, h1) - 1.0 <= hm <= max(h0, h1) + 1.0:
            y = y0 + (y1 - y0) * (hm - h0) / (h1 - h0)
            if y > ym + 30.0:
                return False
    return True


def na_ponta(b, t) -> bool:
    """1.4: a peça em pé numa das duas pontas da treliça"""
    if not _em_pe(b, t):
        return False
    d = abs(_dot(_sub(_mid(b), t["meio"]), t["eixo"]))
    return d > t["vao"] / 2.0 - 80.0


def perfil_do_banzo(t) -> Optional[str]:
    """o perfil do banzo superior da treliça (o mais usado; sem banzo de cima marcado, o de qualquer banzo)"""
    cont, cont2 = collections.Counter(), collections.Counter()
    for o in t.get("vultos") or [o for o, _p in t["barras"]]:
        a = getattr(o, "atributos", None) or {}
        pt = str(a.get("papel_trelica") or "")
        if pt == "banzo_sup" or (not pt and str(getattr(o, "papel", "")) == "banzo" and no_topo(o, t)):
            cont[str(o.perfil)] += 1
        elif pt.startswith("banzo") or str(getattr(o, "papel", "")) == "banzo":
            cont2[str(o.perfil)] += 1
    for c in (cont, cont2):
        if c:
            return c.most_common(1)[0][0]
    return None


def _alvo_no_plano(b, papel: str, t: dict) -> Ponto:
    """2.2/2.3: para onde a boca do U aponta (no plano); na cantoneira, para onde aponta a aba deitada"""
    w = _unit(_sub(b.fim, b.inicio))
    n = t["n"]
    lado = _unit(_cross(n, w))                            # perpendicular à peça, no plano
    up = _cima(t)
    if no_topo(b, t):                                     # 2.2: o banzo de cima (também o que veio como "diagonal") abre para baixo
        if up is not None:
            return lado if _dot(lado, up) < 0 else _mul(lado, -1.0)
        return lado if _dot(_sub(t["centro"], _mid(b)), lado) >= 0 else _mul(lado, -1.0)
    if papel == "banzo":
        return _miolo_do_banzo(b, t)                      # 2.2
    if _em_pe(b, t) or papel in ("montante", "extremidade"):
        d = _dot(_sub(t["meio"], _mid(b)), t["eixo"])    # 2.3: a peça em pé abre para o meio do vão
        if abs(d) < 25.0:
            d = _dot(t["alta"], t["eixo"])                # no meio exato: para a ponta alta
        return lado if d * _dot(lado, t["eixo"]) >= 0 else _mul(lado, -1.0)
    if up is not None and abs(_dot(lado, up)) > 0.3:     # 2.3: a diagonal nunca para cima
        return lado if _dot(lado, up) < 0 else _mul(lado, -1.0)
    d = _dot(_sub(t["meio"], _mid(b)), t["eixo"])         # a diagonal quase em pé (sem "cima" na perpendicular): o meio
    return lado if d * _dot(lado, t["eixo"]) >= 0 else _mul(lado, -1.0)


def _alvo_fora_do_plano(b, t: dict) -> Ponto:
    """2.4/2.5: para que lado sai a aba da cantoneira que atravessa o plano: +n (o lado fixo da obra); no par, para o
    centro (a cantoneira de cada aba do banzo aponta para a outra)"""
    lado = t["par"].get(id(b))
    return _mul(t["n"], -float(lado)) if lado else t["n"]


def alvo_u(b, papel: str, t: dict) -> Optional[Ponto]:
    """a direção em que o eixo u da seção deve ficar (U: a boca; L: a aba que atravessa o plano); None = fora da regra"""
    f = forma(getattr(b, "perfil", ""))
    if f is None or (f == "L" and papel == "banzo"):
        return None                                       # banzo em cantoneira: fora destas regras
    return _alvo_fora_do_plano(b, t) if f == "L" else _alvo_no_plano(b, papel, t)


def _regra(b, papel, t) -> str:
    if forma(b.perfil) == "L":
        return "2.5" if id(b) in t["par"] else "2.4"
    if papel == "banzo" or no_topo(b, t):
        return "2.2"
    return "2.3"


# ------------------------------------------------------------------ classificar, orientar, conferir
def _giro_da_cantoneira(w, fora, plano) -> float:
    """dos quatro giros da cantoneira, o que põe uma aba atravessando o plano para `fora` e a outra deitada para `plano`"""
    from nucleo3d.geometria import base_local
    base = _giro_para(w, fora)
    melhor, nota = round(base, 3), -9.0
    for d in (0.0, 90.0, -90.0, 180.0):
        g = (base + d) % 360.0
        u, v, _w = base_local(w, g)
        cruza, outra = (u, v) if abs(_dot(u, fora)) > abs(_dot(v, fora)) else (v, u)
        if _dot(cruza, fora) < 0.9:
            continue
        if _dot(outra, plano) > nota:
            melhor, nota = round(g, 3), _dot(outra, plano)
    return melhor


def _virada(b) -> bool:
    return bool((getattr(b, "atributos", None) or {}).get("boca_virada"))


def _trocar_perfil(b, perfil: str):
    b.perfil = perfil
    a = getattr(b, "atributos", None)
    if isinstance(a, dict):
        if isinstance(a.get("marcas"), dict):
            a["marcas"]["perfil"] = perfil
        if "peso_kg" in a:
            try:
                from nucleo3d.geometria import peso_barra
                a["peso_kg"] = round(peso_barra(b), 2)
            except Exception:                             # noqa: BLE001
                pass


def classificar(entidades: Iterable, por_grupo: bool = True) -> int:
    """1.2 e 1.4: a peça no contorno de cima vira banzo superior (papel e perfil do banzo); a ponta recebe o perfil do
    banzo. A peça com o perfil da legenda do projeto (`perfil_do_projeto`) não muda. Devolve quantas mudaram"""
    lista = list(entidades)
    mudou = 0
    for t in trelicas(lista, por_grupo):
        pb = perfil_do_banzo(t)
        for b, papel in t["barras"]:
            a = getattr(b, "atributos", None)
            if not isinstance(a, dict):
                a = b.atributos = {}
            if a.get("perfil_do_projeto"):
                continue
            if papel != "banzo" and no_topo(b, t):        # 1.2
                b.papel = "banzo"
                a["papel_trelica"] = "banzo_sup"
                if "funcao" in a:
                    a["funcao"] = "banzo superior"
                if pb and forma(pb) == "U" and str(b.perfil) != pb:
                    _trocar_perfil(b, pb)
                mudou += 1
            elif papel != "banzo" and na_ponta(b, t) and pb and forma(pb) == "U" and str(b.perfil) != pb:   # 1.4
                _trocar_perfil(b, pb)
                mudou += 1
    return mudou


def orientar(entidades: Iterable, por_grupo: bool = True) -> int:
    """gira cada peça das treliças pela regra (seção 2); devolve quantas mudaram"""
    lista = list(entidades)
    mudou = 0
    for t in trelicas(lista, por_grupo):
        for b, papel in t["barras"]:
            alvo = alvo_u(b, papel, t)
            if alvo is None:
                continue
            w = _unit(_sub(b.fim, b.inicio))
            vira = -1.0 if _virada(b) else 1.0            # 2.7: virada de propósito = a boca ao contrário da regra
            if forma(b.perfil) == "L":
                g = _giro_da_cantoneira(w, alvo, _mul(_alvo_no_plano(b, papel, t), vira))
            else:
                g = round(_giro_para(w, _mul(alvo, vira)), 3)
            atual = float(getattr(b, "rotacao", 0.0) or 0.0) % 360.0
            if abs(((g - atual) + 180.0) % 360.0 - 180.0) > 0.5:
                b.rotacao = g
                mudou += 1
    return mudou


FOLGA_FACE = 0.0         # mm: a folga entre a tesoura que chega e a face interna da platibanda (4.8: "parar na face")


def _extensao(b, direcao: Ponto) -> float:
    """quanto o material da barra se estende do eixo dela na direção dada (pela seção girada), em mm"""
    try:
        from nucleo3d.geometria import resolver_perfil, secao
        pts = secao(resolver_perfil(b.perfil))
    except Exception:                                     # noqa: BLE001 — sem a seção: meia largura de 50
        return 50.0
    u, v, _w = _eixos(b)
    return max(_dot(_add(_mul(u, x), _mul(v, y)), direcao) for x, y in pts)


def _vertical(t) -> bool:
    return abs(t["n"][2]) < 0.3


def _encontros(ts: List[dict]) -> List[tuple]:
    """(A, B, sA, limite, dentro): a treliça A chega na treliça B (planos perpendiculares, as duas em pé); sA é o lado de
    B em que A está; `limite` é a distância do plano de B até onde A pode ir (meia largura de B + a folga); `dentro(p)`
    diz se o ponto p está na frente de B (no retângulo dela)"""
    out = []
    for A in ts:
        if not _vertical(A):
            continue
        for B in ts:
            if B is A or not _vertical(B) or abs(_dot(A["n"], B["n"])) > 0.3:
                continue
            nB, cB = B["n"], B["centro"]
            sA = 1.0 if _dot(_sub(A["centro"], cB), nB) >= 0 else -1.0
            ptsB = [p for b, _p in B["barras"] for p in (b.inicio, b.fim)]
            eB = B["eixo"]
            lo, hi = min(_dot(p, eB) for p in ptsB) - 50.0, max(_dot(p, eB) for p in ptsB) + 50.0
            zlo, zhi = min(p[2] for p in ptsB) - 50.0, max(p[2] for p in ptsB) + 50.0

            def dentro(p, eB=eB, lo=lo, hi=hi, zlo=zlo, zhi=zhi):
                return lo <= _dot(p, eB) <= hi and zlo <= p[2] <= zhi
            hB = max(_extensao(b, _mul(nB, sA)) for b, _p in B["barras"])
            limite = hB + FOLGA_FACE
            ptsA = [p for b, _p in A["barras"] for p in (b.inicio, b.fim)]
            # A CHEGA em B: fica inteira de um lado do plano de B (não o atravessa: a parede que cruza várias tesouras
            # não é a peça que chega) e tem ponto na frente de B, perto da face ou já dentro
            if min(sA * _dot(_sub(p, cB), nB) for p in ptsA) < -(hB + 5.0):
                continue
            if not any(dentro(p) and sA * _dot(_sub(p, cB), nB) < limite + 100.0 for p in ptsA):
                continue
            # B PASSA por A: estende-se para os dois lados do plano de A (no canto entre dois painéis ninguém passa:
            # é meia-esquadria, regra 3.1)
            gB = [_dot(_sub(p, A["centro"]), A["n"]) for p in ptsB]
            if min(gB) > -20.0 or max(gB) < 20.0:
                continue
            out.append((A, B, sA, limite, dentro))
    return out


def invasoes(entidades: Iterable, por_grupo: bool = True) -> List[tuple]:
    """4.8: (barra de A, B, mm além do limite) para cada peça da tesoura que chega com material além da face interna da
    treliça que passa"""
    ts = trelicas(list(entidades), por_grupo)
    out = []
    for A, B, sA, limite, dentro in _encontros(ts):
        nB, cB = B["n"], B["centro"]
        for b, _p in A["barras"]:
            w = _unit(_sub(b.fim, b.inicio))
            paralela = abs(_dot(w, nB)) < 0.3                    # o montante de ponta: corre ao longo da face
            ext = _extensao(b, _mul(nB, -sA)) if paralela else 0.0
            pior = 0.0
            for p in (b.inicio, b.fim):
                if not dentro(p):
                    continue
                f = sA * _dot(_sub(p, cB), nB) - ext           # a face do material mais perto de B
                if f < limite - 0.5:
                    pior = max(pior, limite - f)
            if pior > 0:
                out.append((b, B, round(pior, 1)))
    return out


def recuar(entidades: Iterable, por_grupo: bool = True) -> int:
    """4.8: leva a ponta da tesoura que chega até a face interna da treliça que passa. O montante de ponta diz até onde
    vai o eixo dele (a face externa do material na folga); cada ponto de barra além desse plano é transladado até ele
    ao longo da normal da platibanda (o recuo puro: a ponta continua em pé, o banzo e a diagonal só encurtam) — as
    barras que chegavam no mesmo nó continuam chegando. Só recua, nunca prolonga. Devolve quantas barras mudaram"""
    lista = list(entidades)
    ts = trelicas(lista, por_grupo)
    mudou = set()
    for A, B, sA, limite, dentro in _encontros(ts):
        nB, cB = B["n"], B["centro"]
        f = lambda p: sA * _dot(_sub(p, cB), nB)                  # noqa: E731 — a distância do plano de B, para A
        # 1. o montante de ponta (corre ao longo da face): o eixo dele fica em limite + a extensão do material
        alvo = limite
        for b, _p in A["barras"]:
            w = _unit(_sub(b.fim, b.inicio))
            if abs(_dot(w, nB)) < 0.3 and any(dentro(p) for p in (b.inicio, b.fim)):   # a ponta, mesmo mais alta que B
                ext = _extensao(b, _mul(nB, -sA))
                if min(f(b.inicio), f(b.fim)) - ext < limite - 0.5:
                    alvo = max(alvo, limite + ext)
        # 2. cada ponto de barra além do alvo vai ao plano do alvo, pela normal da platibanda
        for b, _p in A["barras"]:
            for k in ("inicio", "fim"):
                p = getattr(b, k)
                if dentro(p) and f(p) < alvo - 0.5:
                    setattr(b, k, tuple(round(c, 3) for c in _add(p, _mul(nB, sA * (alvo - f(p))))))
                    mudou.add(id(b))
    return len(mudou)


def _alma_e_banzos(entidades):
    """[(alma, [banzos do bloco dela])] — o mesmo agrupamento do encaixe (atributos.origem.peca)"""
    from nucleo3d import alma_na_face
    out = []
    for g in alma_na_face._blocos(entidades).values():
        if g["banzo"]:
            out.extend((a, g["banzo"]) for a in g["alma"])
    return out


def _face_da_ponta(alma, k, banzos, sem_limite=False):
    """a face do banzo em que a ponta k da alma chega (o dicionário do encaixe: E, d, p, face, t…), ou None.
    `sem_limite`: também quando o corte passa do limite do encaixe (MAX_FRACAO) — o trecho todo dentro do banzo"""
    from nucleo3d import alma_na_face as AF
    antigo = AF.MAX_FRACAO
    if sem_limite:
        AF.MAX_FRACAO = 10.0
    try:
        return AF._face_no_banzo(alma, k, banzos, AF.FOLGA_ENCAIXE)
    finally:
        AF.MAX_FRACAO = antigo


def _corte_da_ponta(alma, k, banzos, sem_limite=False):
    """o que a ponta k da alma recua ao longo dela até a face do banzo (negativo: a face está além do nó — a alma em U
    entra na boca do banzo e para na alma dele), ou None se a ponta não chega em banzo"""
    r = _face_da_ponta(alma, k, banzos, sem_limite)
    return None if r is None else r["t"]


def _quanto_fura(alma, r) -> float:
    """quanto (mm, na direção da face) o material da ponta reta da alma passa da face do banzo: as quinas da seção no
    plano da ponta comparadas com a face (a quina da diagonal inclinada desce além do nó)"""
    from nucleo3d import alma_na_face as AF
    pts = AF._pontos_da_secao(alma.perfil)
    if not pts:
        return 0.0
    u, v, _w = base_local_barra(alma)
    p = r["p"]
    menor = min(x * _dot(u, p) + y * _dot(v, p) for x, y in pts)
    return max(0.0, r["face"] - menor)


def base_local_barra(b):
    return _eixos(b)


def _todo_dentro(a, banzos) -> bool:
    """3.1b: o trecho de alma cujo material está inteiro dentro do(s) banzo(s) — o corte das duas pontas soma mais que
    o comprimento (ou o de uma ponta só já passa dele)"""
    L = math.dist(a.inicio, a.fim)
    ts = [_corte_da_ponta(a, k, banzos, sem_limite=True) for k in (0, 1)]
    if any(t is not None and t >= 0.95 * L for t in ts):
        return True
    return all(t is not None for t in ts) and ts[0] + ts[1] >= 0.95 * L


def furos_no_banzo(entidades: Iterable) -> List[tuple]:
    """3.1a/3.1b: (alma, ponta, mm) — a ponta que chega no banzo com material além da face e sem corte; mm = -1 para o
    trecho todo dentro do banzo"""
    out = []
    for a, banzos in _alma_e_banzos(list(entidades)):
        if _todo_dentro(a, banzos):
            out.append((a, 0, -1.0))                      # 3.1b: o trecho todo dentro do banzo
            continue
        for k in (0, 1):
            r = _face_da_ponta(a, k, banzos, sem_limite=True)
            if r is None:
                continue
            cortes = a.cortes_inicio if k == 0 else a.cortes_fim
            if cortes:
                continue                                  # encaixada (o plano da face ou o recorte do usuário)
            recorte = float((a.recorte_inicio if k == 0 else a.recorte_fim) or 0.0)
            fura = _quanto_fura(a, r) - recorte * abs(_dot(r["d"], r["p"]))
            if fura > 1.0:
                out.append((a, k, round(fura, 1)))
    return out


def juntar_trechos(entidades: Iterable) -> List:
    """3.1b: o trecho de montante todo dentro do banzo é absorvido pelo trecho alinhado vizinho (que passa a ir até o
    nó), quando nenhuma outra peça chega na emenda. Devolve os trechos absorvidos — quem monta tira do modelo"""
    lista = [e for e in entidades if hasattr(e, "inicio") and hasattr(e, "fim")]
    absorvidos = []
    for a, banzos in _alma_e_banzos(lista):
        if any(a is x for x in absorvidos) or not _todo_dentro(a, banzos):
            continue
        if a.papel != "montante":
            absorvidos.append(a)                          # a diagonal toda dentro do banzo: só sai
            continue
        w = _unit(_sub(a.fim, a.inicio))
        for k_emenda in (0, 1):                           # a ponta da emenda: a que não está no nó do banzo
            J = a.inicio if k_emenda == 0 else a.fim
            no = a.fim if k_emenda == 0 else a.inicio
            vizinhos = [o for o in lista if o is not a and o not in absorvidos
                        and any(math.dist(J, q) < 1.0 for q in (o.inicio, o.fim))]
            alinhados = [o for o in vizinhos if getattr(o, "papel", "") == "montante"
                         and abs(_dot(_unit(_sub(o.fim, o.inicio)), w)) > 0.999]
            if len(vizinhos) != 1 or len(alinhados) != 1:
                continue                                  # chega outra peça na emenda: é um nó, não emenda
            o = alinhados[0]
            if math.dist(o.inicio, J) < 1.0:
                o.inicio = tuple(no)
            else:
                o.fim = tuple(no)
            absorvidos.append(a)
            break
        else:
            absorvidos.append(a)                          # a emenda é um nó (o degrau entre dois banzos): só sai
    return absorvidos


def aplicar(entidades: Iterable, por_grupo: bool = True) -> Tuple[int, int, int, int]:
    """o que todo gerador e todo script de obra chamam: (peças reclassificadas, peças giradas, peças recuadas da
    platibanda, pontas encaixadas no banzo). Depois do recuo as peças são orientadas de novo (a direção mudou um pouco e
    o triedro pode ter trocado o vetor auxiliar); o encaixe (3.1a) vem por último, porque depende do giro e da posição"""
    from nucleo3d import alma_na_face
    lista = list(entidades)
    n_class = classificar(lista, por_grupo)
    n_giro = orientar(lista, por_grupo)
    n_rec = recuar(lista, por_grupo)
    if n_rec:
        n_giro += orientar(lista, por_grupo)
    antes = {id(b): (repr(getattr(b, "cortes_inicio", None)), repr(getattr(b, "cortes_fim", None)))
             for b in lista if hasattr(b, "cortes_inicio")}
    alma_na_face.encaixar(lista)
    n_enc = sum(1 for b in lista if hasattr(b, "cortes_inicio")
                and antes.get(id(b)) != (repr(b.cortes_inicio), repr(b.cortes_fim)))
    return n_class, n_giro, n_rec, n_enc


def conferir(entidades: Iterable, tol_graus: float = 5.0, por_grupo: bool = True) -> List[dict]:
    """as peças fora da regra: [{id, nome, perfil, papel, regra, erro_graus, ponto}] — regra 1.2 (devia ser banzo),
    1.4 (ponta sem o perfil do banzo), 2.2–2.5 (posição)"""
    out = []
    cos_tol = math.cos(math.radians(tol_graus))

    def acusa(b, papel, regra, erro):
        out.append({"id": b.id, "nome": b.nome, "perfil": b.perfil, "papel": papel, "regra": regra,
                    "erro_graus": erro, "ponto": [round(x) for x in b.inicio]})

    for t in trelicas(list(entidades), por_grupo):
        pb = perfil_do_banzo(t)
        for b, papel in t["barras"]:
            a = getattr(b, "atributos", None) or {}
            if not a.get("perfil_do_projeto"):
                if papel != "banzo" and no_topo(b, t):
                    acusa(b, papel, "1.2", 0.0)
                elif papel != "banzo" and na_ponta(b, t) and pb and forma(pb) == "U" and str(b.perfil) != pb:
                    acusa(b, papel, "1.4", 0.0)
            alvo = alvo_u(b, papel, t)
            if alvo is None:
                continue
            vira = -1.0 if _virada(b) else 1.0
            if forma(b.perfil) == "L":
                lado = lado_da_aba(b, t["n"])
                if lado != (1 if _dot(alvo, t["n"]) > 0 else -1):
                    acusa(b, papel, _regra(b, papel, t), 180.0 if lado else 90.0)
                    continue
                c = _dot(_aba_deitada(b, t["n"]), _mul(_alvo_no_plano(b, papel, t), vira))
            else:
                c = _dot(_eixos(b)[0], _mul(alvo, vira))
            if c < cos_tol:
                acusa(b, papel, "2.3" if forma(b.perfil) == "L" else _regra(b, papel, t),
                      round(math.degrees(math.acos(max(-1.0, min(1.0, c)))), 1))
    for a, k, mm in furos_no_banzo(list(entidades)):
        out.append({"id": a.id, "nome": a.nome, "perfil": a.perfil, "papel": _papel(a) or a.papel, "regra": "3.1",
                    "erro_graus": 0.0, "mm": mm, "ponto": [round(x) for x in (a.inicio if k == 0 else a.fim)]})
    for b, _B, mm in invasoes(list(entidades), por_grupo):
        out.append({"id": b.id, "nome": b.nome, "perfil": b.perfil, "papel": _papel(b), "regra": "4.8",
                    "erro_graus": 0.0, "mm": mm, "ponto": [round(x) for x in b.inicio]})
    return out


TEXTO_REGRAS = __doc__
