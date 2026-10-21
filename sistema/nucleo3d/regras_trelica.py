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
  2.8  Fora destas regras: tubos, barras redondas, I/W, a barra secundária "um lado só", a presilha, o banzo em caixa
       (`secao_dupla: "caixa"`, pelo croqui da legenda).
  2.9  Banzo em U com a alma em cantoneira dupla (2L) — usuário, 21/10 (Hangar Almayer, croqui): a alma do U fica NO
       PLANO da tesoura (a altura em pé, a boca perpendicular ao plano), e as duas cantoneiras abraçam a alma do U, uma
       em cada face, a aba em pé soldada na alma — a maior superfície de contato de solda (127 mm, não a aba de 50) — e
       a outra aba para fora do plano, afastando-se da alma. No U simples (`secao_dupla: "alma_no_plano"`, T1/T3 do
       Hangar) a boca abre para fora do prédio (o corte T1: o U centrado no eixo, encostado na face externa do pilar;
       as duas tesouras de oitão espelhadas); sem prédio de um lado só (tesoura do meio), qualquer lado fora do plano
       (o gerador, que vê a planta inteira, decide: para +n). Cada cantoneira do par fica com a aba que sai do plano
       apontando para longe da alma do U mais perto. No 2U composto
       (`"composto"`, T2) os dois U de costas, afastados pela peça da alma que passa entre as almas, a boca de cada um
       para o seu lado, e uma cantoneira do par dentro de cada boca. A 2.1/2.2 continua valendo para o U com alma em U
       ou em L simples. A conferência acusa "2.9": o U com a boca no plano ou para o lado errado; a reanálise gira (e
       espelha o U simples para o outro lado do eixo). Antes a peça com `secao_dupla` era pulada e a reanálise do Hangar
       passava "nada a corrigir" com o banzo virado.
  2.9a A PONTA do banzo composto (usuário, 21/10, montada à mão na T2 do Hangar): o vão entre as almas dos dois U é a
       altura do U do banzo (127 no Hangar; nunca menor que a altura da alma — CD Bom Dia: alma Ue 127 em banzo Ue 100),
       e a ponta — o montante de extremidade e o trecho a 45° do painel de ponta — é UM U SÓ do perfil do banzo, no
       plano, encaixado entre as almas: a altura atravessa o plano (as abas encostam e soldam nas almas dos banzos), a
       alma para fora fechando a ponta, a boca para o vão (o montante para o meio; o 45° para baixo). O montante nasce
       no nível de apoio (sentado na chapa, como o fundo dos banzos) e encontra o 45° em meia-esquadria (a bissetriz);
       o banzo inferior vai até a face da ponta, o superior até o encontro com o 45°. A conferência acusa "2.9a" a ponta
       em par (um U de cada lado, como o gerador fazia) e "2.9" a ponta no plano com a boca fora do plano.

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
  3.1c O degrau no banzo de cima (usuário, 19/10, faixa norte do Mercado: "esse ponto não passou na regra do recorte"):
       dois trechos do banzo superior que se encontram na mesma estação com um desnível menor que as seções (o material
       de um dentro do outro) — o montante do degrau sobe até o nó de cima (o encaixe o corta na face do banzo de cima) e
       o banzo de baixo nasce na face do montante (recortado). Sem montante no degrau, a conferência acusa.
  3.2  Nós no eixo do banzo (NBR 8800:2024, 6.5.2): a ponta de montante/diagonal a menos de 100 mm do eixo de um banzo,
       na mesma estação e sem banzo no ponto dela, vai para o eixo (a emenda de montante partido é da 3.1b). No Mercado a
       alma do painel da ponta da meia-tesoura parava 50 mm abaixo do banzo plano.

4. O ENTORNO DA TESOURA
  4.8  Encontro da tesoura com platibanda ou fechamento (a peça que chega × a peça que passa) — usuário, 16/10: "o final da
       tesoura nunca pode invadir a platibanda, deve sempre parar na face interna". A platibanda é a peça contínua; a
       tesoura é a interrompida. O limite da tesoura é o plano da face interna da platibanda (a face do perfil dela voltada
       para a tesoura) deslocado da folga de montagem FOLGA_FACE: nenhuma peça da tesoura (banzos, montante de ponta,
       diagonal de ponta) tem material além desse plano — o montante de ponta fica paralelo à face, com a sua face externa
       na folga; os banzos e a diagonal param no eixo do montante de ponta, cortados no ângulo quando chegam inclinados.
       A platibanda não muda. Vale para qualquer treliça que passa (treliça de cumeeira, viga de transição): a que chega para
       na face da que passa. Só recua, nunca prolonga (a tesoura que termina antes da platibanda fica como está).
       Na altura vale só a folga do desenho (5 mm): a treliça que só encosta por cima ou por baixo da outra (a fachada sobre
       a faixa norte do Mercado) não é "a que chega".
  4.9  A terça com o eixo forte perpendicular à água (a alma do Ue, o chapéu da cartola), sentada no apoio: entre 10° e
       70° fora é acusada e girada de volta (perto de 90° é a terça deitada de propósito, o beiral do Docas). Usuário,
       19/10: "essa terça ficou torcida demais" (a NC-3 da faixa norte, 30,6°).
"""
from __future__ import annotations

import collections
import math
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Ponto = Tuple[float, float, float]

PAPEIS_TRELICA = {"banzo", "montante", "diagonal", "extremidade"}
_FORA = {"presilha", "secundaria"}
SECOES_2_9 = ("alma_no_plano", "composto")   # o banzo em U de alma no plano (2.9): o U simples e os dois U de costas
PREDIO_MIN = 500.0       # mm: o resto da obra a menos que isso do plano não diz de que lado é o prédio (2.9)
PONTA_NO_PLANO = 25.0    # mm: na treliça de 2U, a peça em U a menos que isso do plano é a ponta em U só (2.9a)
PONTA_CURTA = 1000.0     # mm: a peça da ponta (montante de extremidade, trecho a 45°) é curta; o banzo não
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
    liga = collections.defaultdict(list)               # os U de alma no plano (2.9): ligam as peças, não são giradas aqui
    vultos = collections.defaultdict(list)             # todas as barras da treliça, também as de regra própria (o
    for e in entidades:                                # banzo composto): o que está acima de uma peça (1.2)
        if not isinstance(e, Barra):
            continue
        a_ = getattr(e, "atributos", None) or {}
        if (str(a_.get("papel_trelica") or "") or str(getattr(e, "papel", "") or "")).startswith(
                ("banzo", "montante", "diagonal", "extremidade")):
            vultos[_chave_grupo(e) if por_grupo else ("todas",)].append(e)
        pap = _papel(e)
        if math.dist(e.inicio, e.fim) < 1.0:
            continue
        if pap is None:
            # o U de alma no plano (2.9) não entra nas peças que a regra gira como alma, mas liga a treliça: a diagonal
            # que só encosta nele (a da ponta, ou o par dentro da boca do composto) ficava num grupo de 1–2 peças, fora
            # de toda treliça, sem regra (Hangar, 21/10: 24 cantoneiras da T2-A com a aba para o lado da alma)
            if forma(getattr(e, "perfil", "")) == "U" and str(a_.get("secao_dupla") or "") in SECOES_2_9:
                liga[_chave_grupo(e) if por_grupo else ("todas",)].append(e)
            continue
        por_chave[_chave_grupo(e) if por_grupo else ("todas",)].append(e)
    # o prédio (2.9): o centro de todas as treliças do modelo — a tesoura de oitão tem o resto da obra de um lado só
    todos = [p for lista in vultos.values() for o in lista for p in (o.inicio, o.fim)]
    predio = tuple(sum(p[k] for p in todos) / len(todos) for k in range(3)) if todos else None
    out = []
    for _k, lista in por_chave.items():
        for comp_todo in _componentes(lista + liga.get(_k, [])):
            ids_liga = {id(o) for o in liga.get(_k, [])}
            comp = [b for b in comp_todo if id(b) not in ids_liga]
            if len(comp) < 3:
                continue
            pl = _normal(comp_todo)
            if pl is None:
                continue
            n, c = pl
            fora = None                                   # 2.9: para fora do prédio (None: prédio dos dois lados)
            if predio is not None:
                dp = _dot(_sub(predio, c), n)
                if abs(dp) > PREDIO_MIN:
                    fora = _mul(n, -1.0) if dp > 0 else n
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
            # 2.9: os banzos em U de alma no plano desta treliça (ficam fora de `barras`: a regra deles é só o giro)
            abraca = [o for o in dentro if forma(getattr(o, "perfil", "")) == "U"
                      and str((getattr(o, "atributos", None) or {}).get("secao_dupla") or "") in SECOES_2_9]
            # o plano do composto: o meio entre os dois U (não o centro das peças da alma — na T2 do Hangar os pares de
            # cantoneira a ±75 não se ligam e cada lado era uma "treliça" com o centro deslocado: o U do outro lado, a
            # 1,6 mm desse centro, virava "ponta" e era girado para o plano)
            ks = [_dot(_mid(o), n) for o in abraca
                  if str((getattr(o, "atributos", None) or {}).get("secao_dupla")) == "composto"]
            plano_2_9 = (min(ks) + max(ks)) / 2.0 if ks else _dot(c, n)
            out.append({"n": n, "centro": c, "eixo": eixo, "meio": meio, "vao": hi_p - lo_p, "alta": alta,
                        "barras": [(b, _papel(b)) for b in comp], "par": _pares(comp, n, c), "vultos": dentro,
                        "fora": fora, "abraca": abraca, "plano_2_9": plano_2_9})
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
    centro (a cantoneira de cada aba do banzo aponta para a outra). Na treliça da 2.9 o par abraça a alma do U: cada
    cantoneira com a aba para fora, afastando-se da alma (o contrário do par dentro da boca)"""
    if t.get("abraca"):
        k = _alma_do_u(b, t)
        if k is not None:                                 # a aba para fora, afastando-se da alma do U mais perto
            return t["n"] if _dot(_mid(b), t["n"]) >= k else _mul(t["n"], -1.0)
    lado = t["par"].get(id(b))
    if lado and t.get("abraca"):
        return _mul(t["n"], float(lado))
    return _mul(t["n"], -float(lado)) if lado else t["n"]


def _alma_do_u(b, t: dict) -> Optional[float]:
    """2.9: onde fica (na normal do plano) a alma do U de alma no plano mais perto da peça b — o meio da espessura da
    alma: o eixo da barra − (da alma ao centroide − t/2) no sentido da boca"""
    m = _mid(b)
    w = _unit(_sub(b.fim, b.inicio))
    melhor, dist = None, 1e18
    for o in t["abraca"]:
        if (getattr(o, "atributos", None) or {}).get("ponta_composto"):
            continue
        ow = _unit(_sub(o.fim, o.inicio))
        # a distância no plano (sem a normal): da ponta de b à linha do U
        p = _sub(m, _mul(t["n"], _dot(_sub(m, o.inicio), t["n"])))
        dd = _dist_pt_seg(p, o.inicio, o.fim)
        if dd < dist:
            dist, melhor = dd, o
    if melhor is None:
        return None
    pts = _pontos_da_secao(melhor.perfil)
    if not pts:
        return None
    xg = -min(q[0] for q in pts)
    try:
        from nucleo3d.geometria import resolver_perfil
        tw = float(resolver_perfil(melhor.perfil).tw or 0.0)
    except Exception:                                    # noqa: BLE001
        tw = 0.0
    u = _eixos(melhor)[0]
    return _dot(_mid(melhor), t["n"]) - _dot(u, t["n"]) * (xg - tw / 2.0)


def _ponta_do_composto(b, t: dict) -> bool:
    """2.9a: na treliça de 2U de costas, a peça em U do banzo que fica no plano (entre as almas) é a ponta em U só"""
    return abs(_dot(_mid(b), t["n"]) - t["plano_2_9"]) < PONTA_NO_PLANO


def _na_ponta_do_vao(b, t: dict) -> bool:
    """a peça curta no fim do vão (o montante de extremidade, o trecho a 45° do painel de ponta)"""
    if math.dist(b.inicio, b.fim) > PONTA_CURTA:
        return False
    return abs(_dot(_sub(_mid(b), t["meio"]), t["eixo"])) > t["vao"] / 2.0 - PONTA_CURTA / 2.0


def alvo_2_9(b, t: dict) -> Ponto:
    """2.9: para onde a boca do U de alma no plano aponta — fora do plano; o U simples para fora do prédio (+n sem
    prédio de um lado só), cada U do composto para o seu lado do plano. 2.9a: a ponta do composto (o U só no plano)
    abre no plano — o montante para o meio do vão, o trecho a 45° para baixo"""
    sec = str((getattr(b, "atributos", None) or {}).get("secao_dupla") or "")
    if sec == "composto":
        if _ponta_do_composto(b, t):
            w = _unit(_sub(b.fim, b.inicio))
            lado = _unit(_cross(t["n"], w))               # perpendicular à peça, no plano
            if _em_pe(b, t):
                d = _dot(_sub(t["meio"], _mid(b)), t["eixo"])
                return lado if d * _dot(lado, t["eixo"]) >= 0 else _mul(lado, -1.0)
            up = _cima(t)
            if up is not None and abs(_dot(lado, up)) > 0.3:
                return lado if _dot(lado, up) < 0 else _mul(lado, -1.0)
            d = _dot(_sub(t["meio"], _mid(b)), t["eixo"])
            return lado if d * _dot(lado, t["eixo"]) >= 0 else _mul(lado, -1.0)
        d = _dot(_mid(b), t["n"]) - t["plano_2_9"]
        return t["n"] if d >= 0 else _mul(t["n"], -1.0)
    if t["fora"] is not None:
        return t["fora"]
    # sem prédio de um lado só (a tesoura do meio, ou montada sozinha pelo gerador, que já pôs o lado): a boca só
    # precisa estar fora do plano — o lado que ela já tem
    return t["n"] if _dot(_eixos(b)[0], t["n"]) >= 0 else _mul(t["n"], -1.0)


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
    vistas_2_9 = set()
    ts = trelicas(lista, por_grupo)
    # 2.9 primeiro: o U de alma no plano pode virar (e andar), e o lado das cantoneiras do par se mede pela alma dele
    for t in ts:
        for b in t["abraca"]:                             # 2.9: a boca para fora do plano
            if getattr(b, "bloqueada", False) or id(b) in vistas_2_9:
                continue                                  # a treliça em dois componentes vê o mesmo banzo duas vezes
            vistas_2_9.add(id(b))
            alvo = _mul(alvo_2_9(b, t), -1.0 if _virada(b) else 1.0)
            w = _unit(_sub(b.fim, b.inicio))
            g = round(_giro_para(w, alvo), 3)
            atual = float(getattr(b, "rotacao", 0.0) or 0.0) % 360.0
            if abs(((g - atual) + 180.0) % 360.0 - 180.0) <= 0.5:
                continue
            u_antes = _eixos(b)[0]
            pts = _pontos_da_secao(b.perfil)
            if _dot(u_antes, alvo) < -0.9 and str((b.atributos or {}).get("secao_dupla")) == "alma_no_plano" and pts:
                # o U simples virado para o lado errado: vira no lugar, dentro da própria faixa de bf — a alma vai para
                # onde estavam as pontas das abas (o U centrado no eixo continua centrado); o eixo da barra anda
                # bf − 2·xg no sentido da boca antiga
                xs = [q[0] for q in pts]
                bf, xg = max(xs) - min(xs), -min(xs)
                desl = _mul(u_antes, bf - 2.0 * xg)
                b.inicio, b.fim = _add(b.inicio, desl), _add(b.fim, desl)
            b.rotacao = g
            mudou += 1
    for t in ts:
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


_SECOES: Dict[str, Optional[list]] = {}


def _pontos_da_secao(perfil: str) -> Optional[list]:
    """o contorno da seção, guardado por perfil (a 4.8 pede a seção de cada peça de cada encontro: no Mercado eram 40 mil
    contas da mesma meia dúzia de perfis, 15 s da troca por grupo)"""
    k = str(perfil or "")
    if k not in _SECOES:
        try:
            from nucleo3d.geometria import resolver_perfil, secao
            _SECOES[k] = list(secao(resolver_perfil(k)))
        except Exception:                                 # noqa: BLE001
            _SECOES[k] = None
    return _SECOES[k]


def _extensao(b, direcao: Ponto) -> float:
    """quanto o material da barra se estende do eixo dela na direção dada (pela seção girada), em mm"""
    pts = _pontos_da_secao(b.perfil)
    if not pts:                                           # sem a seção: meia largura de 50
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
            # na altura, só a folga do desenho: com 50 mm a treliça que só encosta por cima ou por baixo (a fachada do
            # Mercado sobre a faixa norte, banzos a 28 mm) virava "a que chega" e era recuada 100 mm (19/10)
            zlo, zhi = min(p[2] for p in ptsB) - 5.0, max(p[2] for p in ptsB) + 5.0

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


# ------------------------------------------------------------------ 3.2 os nós no eixo do banzo
NO_UNICO = 100.0         # mm: a ponta de alma a menos disso do eixo do banzo é o nó dele (NBR 8800:2024, 6.5.2)


def nos_fora_do_eixo(entidades: Iterable, por_grupo: bool = True) -> List[tuple]:
    """3.2: (peça da alma, ponta 0|1, o ponto no eixo do banzo, mm) — a ponta de montante/diagonal que para entre 3 e
    NO_UNICO mm do eixo de um banzo da mesma treliça, na mesma estação, sem banzo nenhum no ponto dela. No Mercado (19/10)
    o painel da ponta da meia-tesoura tinha a alma 50 mm abaixo do banzo plano: as peças não se tocavam"""
    out = []
    for t in trelicas(list(entidades), por_grupo):
        up = _cima(t)
        if up is None:
            continue
        h = _horizontal(t)
        bz = [b for b, p in t["barras"] if p == "banzo"]
        for a, p in t["barras"]:
            if p not in ("montante", "diagonal", "extremidade"):
                continue
            wa = _unit(_sub(a.fim, a.inicio))
            for k, q in ((0, tuple(a.inicio)), (1, tuple(a.fim))):
                if any(_proj_no_segmento(q, b.inicio, b.fim) < 3.0 for b in bz):
                    continue                              # já está num banzo
                if any(o is not a and min(math.dist(q, o.inicio), math.dist(q, o.fim)) < 3.0
                       and abs(_dot(wa, _unit(_sub(o.fim, o.inicio)))) > 0.999 for o, _p in t["barras"]):
                    continue                              # a emenda de um montante partido: é da 3.1b, não um nó
                melhor = None
                for b in bz:
                    e0, e1 = _dot(b.inicio, h), _dot(b.fim, h)
                    eq = _dot(q, h)
                    if not (min(e0, e1) - 1.0 <= eq <= max(e0, e1) + 1.0) or abs(e1 - e0) < 1.0:
                        continue
                    s = (eq - e0) / (e1 - e0)
                    no = _add(b.inicio, _mul(_sub(b.fim, b.inicio), s))
                    d = abs(_dot(_sub(no, q), up))
                    if 3.0 <= d <= NO_UNICO and abs(_dot(_sub(no, q), t["n"])) < 5.0 and (melhor is None or d < melhor[1]):
                        melhor = (no, d)
                if melhor:
                    out.append((a, k, melhor[0], round(melhor[1], 1)))
    return out


def nos_no_eixo(entidades: Iterable, por_grupo: bool = True) -> int:
    """3.2: leva cada ponta de alma fora do eixo (nos_fora_do_eixo) para o eixo do banzo; devolve quantas"""
    n = 0
    for a, k, no, _mm in nos_fora_do_eixo(entidades, por_grupo):
        setattr(a, "inicio" if k == 0 else "fim", tuple(round(c, 3) for c in no))
        n += 1
    return n


# ------------------------------------------------------------------ 3.1c o degrau no banzo de cima
def _proj_no_segmento(p, a, b) -> float:
    ab = _sub(b, a)
    L2 = _dot(ab, ab)
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, _dot(_sub(p, a), ab) / L2))
    return math.dist(p, _add(a, _mul(ab, t)))


def _horizontal(t) -> Optional[Ponto]:
    """a horizontal no plano da treliça (a estação de um nó é a posição nela; o eixo da treliça é o do banzo mais
    comprido, que pode ser inclinado)"""
    up = _cima(t)
    return None if up is None else _unit(_cross(t["n"], up))


def _em_pe_na_estacao(a, t) -> bool:
    w = _unit(_sub(a.fim, a.inicio))
    h = _horizontal(t) or t["eixo"]
    return abs(_dot(w, h)) < 0.2


def degraus(entidades: Iterable, por_grupo: bool = True) -> List[dict]:
    """3.1c: os degraus do banzo de cima — dois trechos do banzo superior da mesma treliça que se encontram na mesma
    estação com um desnível menor que a soma das seções (o material de um entra no do outro). [{t, alto, baixo, de_cima,
    de_baixo, k_baixo, desnivel, coberto (uma peça em pé vai do nó de baixo ao de cima), montante (a peça em pé que chega
    no nó de baixo, ou None)}]. Usuário, 19/10 (faixa norte do Mercado): "esse ponto não passou na regra do recorte" —
    o banzo de cima e o de baixo se encontravam no degrau sem corte, um sobre o outro"""
    out = []
    for t in trelicas(list(entidades), por_grupo):
        up = _cima(t)
        if up is None:
            continue
        h = _horizontal(t)
        sup = [b for b, p in t["barras"] if p == "banzo" and (str((getattr(b, "atributos", None) or {}).get(
            "papel_trelica") or "") == "banzo_sup" or no_topo(b, t))]
        em_pe = [b for b, p in t["barras"] if p in ("montante", "extremidade") and _em_pe_na_estacao(b, t)]
        pts = [(b, k, tuple(b.inicio if k == 0 else b.fim)) for b in sup for k in (0, 1)]
        for i, (b1, k1, p1) in enumerate(pts):
            for b2, k2, p2 in pts[i + 1:]:
                if b1 is b2:
                    continue
                d = _sub(p1, p2)
                dz = _dot(d, up)
                if abs(_dot(d, h)) > 5.0 or abs(_dot(d, t["n"])) > 5.0 or abs(dz) < 5.0:
                    continue
                o1 = b1.fim if k1 == 0 else b1.inicio
                o2 = b2.fim if k2 == 0 else b2.inicio
                if _dot(_sub(o1, p1), h) * _dot(_sub(o2, p2), h) >= 0:
                    continue                              # os dois do mesmo lado: não é um degrau no caminho do banzo
                (bc, pc), (bb, kb, pb) = ((b1, p1), (b2, k2, p2)) if dz > 0 else ((b2, p2), (b1, k1, p1))
                if _extensao(bc, _mul(up, -1.0)) + _extensao(bb, up) <= abs(dz) + 0.5:
                    continue                              # o desnível já separa as seções: nada se sobrepõe
                coberto = any(_proj_no_segmento(pc, a.inicio, a.fim) < 3.0 and _proj_no_segmento(pb, a.inicio, a.fim) < 3.0
                              for a in em_pe)
                mont = next((a for a in em_pe if min(math.dist(pb, a.inicio), math.dist(pb, a.fim)) < 3.0), None)
                out.append({"t": t, "alto": pc, "baixo": pb, "de_cima": bc, "de_baixo": bb, "k_baixo": kb,
                            "desnivel": round(abs(dz), 1), "coberto": coberto, "montante": mont})
    return out


def subir_montantes(entidades: Iterable, por_grupo: bool = True) -> int:
    """3.1c: no degrau do banzo de cima, o montante que chega no nó de baixo sobe até o nó de cima (o encaixe o corta
    na face do banzo de cima) e o banzo de baixo nasce na face do montante (recortado). Sem montante no degrau, a
    conferência acusa — não se inventa peça. Devolve quantos degraus foram resolvidos"""
    n = 0
    for g in degraus(entidades, por_grupo):
        m = g["montante"]
        if g["coberto"] or m is None:
            continue
        if math.dist(m.inicio, g["baixo"]) < 3.0:
            m.inicio = tuple(round(c, 3) for c in g["alto"])
        else:
            m.fim = tuple(round(c, 3) for c in g["alto"])
        bb, kb = g["de_baixo"], g["k_baixo"]
        outra = bb.fim if kb == 0 else bb.inicio
        rec = _extensao(m, _unit(_sub(outra, g["baixo"])))
        if kb == 0:
            bb.recorte_inicio = max(float(getattr(bb, "recorte_inicio", 0.0) or 0.0), round(rec, 1))
        else:
            bb.recorte_fim = max(float(getattr(bb, "recorte_fim", 0.0) or 0.0), round(rec, 1))
        n += 1
    return n


# ------------------------------------------------------------------ 4.9 a terça com a alma perpendicular à água
TERCA_TORCIDA = (10.0, 70.0)   # graus: entre esses, é a terça girada por engano (perto de 90° é a deitada de propósito)


def _agua_da_terca(tc, barras) -> Optional[Ponto]:
    """a normal da água sob a terça (para cima): a do banzo de cima mais perto que ela cruza"""
    w = _unit(_sub(tc.fim, tc.inicio))
    melhor, dmin = None, 400.0
    for b in barras:
        if b is tc or getattr(b, "papel", "") != "banzo":
            continue
        wb = _unit(_sub(b.fim, b.inicio))
        if abs(_dot(w, wb)) > 0.7:
            continue
        n = _unit(_cross(w, wb))
        if abs(n[2]) < 0.3:
            continue
        # a distância entre as duas retas, medida nos trechos (a terça passa por cima do banzo)
        d = min(_proj_no_segmento(p, b.inicio, b.fim) for p in
                [_add(tc.inicio, _mul(_sub(tc.fim, tc.inicio), s / 20.0)) for s in range(21)])
        if d < dmin:
            melhor, dmin = (n if n[2] > 0 else _mul(n, -1.0)), d
    return melhor


def tercas_torcidas(entidades: Iterable) -> List[tuple]:
    """4.9: (terça, normal da água, desvio em graus) — a terça cujo eixo forte (a alma do Ue, o chapéu da cartola) sai
    da perpendicular à água entre TERCA_TORCIDA. Usuário, 19/10: "essa terça ficou torcida demais" (a NC-3 da faixa norte
    do Mercado, 30,6°: o gerador mediu a inclinação do topo da tesourinha bem em cima do degrau de 50 mm)"""
    lista = [e for e in entidades if hasattr(e, "inicio") and hasattr(e, "perfil")]
    banzos = [b for b in lista if getattr(b, "papel", "") == "banzo"]
    out = []
    for tc in lista:
        if str(getattr(tc, "papel", "")).lower() not in ("terça", "terca"):
            continue
        n = _agua_da_terca(tc, banzos)
        if n is None:
            continue
        v = _eixos(tc)[1]
        desvio = math.degrees(math.acos(min(1.0, abs(_dot(v, n)))))
        if TERCA_TORCIDA[0] < desvio < TERCA_TORCIDA[1]:
            out.append((tc, n, round(desvio, 1)))
    return out


def _extensao_secao(perfil, rotacao, w, direcao) -> float:
    pts = _pontos_da_secao(perfil)
    if not pts:
        return 0.0
    from nucleo3d.geometria import base_local
    u, v, _ = base_local(w, rotacao)
    return max(_dot(_add(_mul(u, x), _mul(v, y)), direcao) for x, y in pts)


def girar_tercas(entidades: Iterable) -> int:
    """4.9: a terça torcida volta à perpendicular da água, sentada no mesmo apoio (a face de baixo não sai do lugar)"""
    n_ok = 0
    for tc, n, _d in tercas_torcidas(entidades):
        w = _unit(_sub(tc.fim, tc.inicio))
        v0 = _eixos(tc)[1]
        alvo = n if _dot(v0, n) >= 0 else _mul(n, -1.0)
        from nucleo3d.geometria import base_local
        u0, vv0, _ = base_local(w, 0.0)
        rot1 = math.degrees(math.atan2(-_dot(alvo, u0), _dot(alvo, vv0))) % 360.0
        baixo = _mul(n, -1.0)
        e0 = _extensao_secao(tc.perfil, float(tc.rotacao or 0.0), w, baixo)
        e1 = _extensao_secao(tc.perfil, rot1, w, baixo)
        d = e1 - e0
        tc.inicio = tuple(round(c, 3) for c in _add(tc.inicio, _mul(n, d)))
        tc.fim = tuple(round(c, 3) for c in _add(tc.fim, _mul(n, d)))
        tc.rotacao = round(rot1, 3)
        n_ok += 1
    return n_ok


ULTIMO_APLICAR: Dict[str, int] = {}


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
    n_nos = nos_no_eixo(lista, por_grupo)                  # 3.2, antes do degrau (o montante passa a chegar no nó)
    n_deg = subir_montantes(lista, por_grupo)              # 3.1c, antes do encaixe (o montante novo é cortado nele)
    n_ter = girar_tercas(lista)                            # 4.9 (só quando as terças vieram junto: o modelo inteiro)
    antes = {id(b): (repr(getattr(b, "cortes_inicio", None)), repr(getattr(b, "cortes_fim", None)))
             for b in lista if hasattr(b, "cortes_inicio")}
    alma_na_face.encaixar(lista)
    n_enc = sum(1 for b in lista if hasattr(b, "cortes_inicio")
                and antes.get(id(b)) != (repr(b.cortes_inicio), repr(b.cortes_fim)))
    ULTIMO_APLICAR.clear()
    ULTIMO_APLICAR.update(nos=n_nos, degraus=n_deg, tercas=n_ter)
    return n_class, n_giro, n_rec, n_enc


def conferir(entidades: Iterable, tol_graus: float = 5.0, por_grupo: bool = True) -> List[dict]:
    """as peças fora da regra: [{id, nome, perfil, papel, regra, erro_graus, ponto}] — regra 1.2 (devia ser banzo),
    1.4 (ponta sem o perfil do banzo), 2.2–2.5 (posição)"""
    out = []
    cos_tol = math.cos(math.radians(tol_graus))
    vistas_2_9 = set()

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
        for b in t["abraca"]:                             # 2.9: a boca do U de alma no plano, para fora do plano
            if id(b) in vistas_2_9:
                continue
            vistas_2_9.add(id(b))
            a_ = getattr(b, "atributos", None) or {}
            if str(a_.get("secao_dupla")) == "composto" and _na_ponta_do_vao(b, t) and not _ponta_do_composto(b, t):
                acusa(b, "banzo", "2.9a", 0.0)            # a ponta em par: devia ser um U só entre as almas
                continue
            c = _dot(_eixos(b)[0], _mul(alvo_2_9(b, t), -1.0 if _virada(b) else 1.0))
            if c < cos_tol:
                acusa(b, "banzo", "2.9", round(math.degrees(math.acos(max(-1.0, min(1.0, c)))), 1))
    for a, k, mm in furos_no_banzo(list(entidades)):
        out.append({"id": a.id, "nome": a.nome, "perfil": a.perfil, "papel": _papel(a) or a.papel, "regra": "3.1",
                    "erro_graus": 0.0, "mm": mm, "ponto": [round(x) for x in (a.inicio if k == 0 else a.fim)]})
    for b, _B, mm in invasoes(list(entidades), por_grupo):
        out.append({"id": b.id, "nome": b.nome, "perfil": b.perfil, "papel": _papel(b), "regra": "4.8",
                    "erro_graus": 0.0, "mm": mm, "ponto": [round(x) for x in b.inicio]})
    for a_, k, _no, mm in nos_fora_do_eixo(list(entidades), por_grupo):
        out.append({"id": a_.id, "nome": a_.nome, "perfil": a_.perfil, "papel": a_.papel, "regra": "3.2",
                    "erro_graus": 0.0, "mm": mm, "ponto": [round(x) for x in (a_.inicio if k == 0 else a_.fim)]})
    for g in degraus(list(entidades), por_grupo):
        if not g["coberto"]:
            b = g["de_cima"]
            out.append({"id": b.id, "nome": b.nome, "perfil": b.perfil, "papel": "banzo", "regra": "3.1c",
                        "erro_graus": 0.0, "mm": g["desnivel"], "ponto": [round(x) for x in g["alto"]]})
    for tc, _n, desvio in tercas_torcidas(list(entidades)):
        out.append({"id": tc.id, "nome": tc.nome, "perfil": tc.perfil, "papel": "terça", "regra": "4.9",
                    "erro_graus": desvio, "ponto": [round(x) for x in tc.inicio]})
    return out


def corrigir_modelo(doc) -> dict:
    """o modelo inteiro pelas regras, sem remontar (17/10: os modelos antigos — CD Bom Dia, Posto, PRATI, Docas — acusavam
    no Verificar apoios até serem remontados, e remontar perde as edições feitas no 3D): aplicar, o trecho de alma dentro
    do banzo sai (3.1b) e aplicar de novo. O documento recebido muda (é a cópia do editor); devolve {"novas": [],
    "alterar": {id: campos}, "remover": [ids], "resumo", "avisos"} para o editor aplicar com desfazer. A peça que mudou de
    perfil (1.2/1.4) fica com o peso novo e a marca a conferir (o Numerar decide)"""
    from nucleo3d.modelo import Barra
    barras = [e for e in doc.entidades.values() if isinstance(e, Barra)]
    antes = {e.id: e.dict() for e in barras}
    n1 = aplicar(list(doc.entidades.values()))
    tirados = juntar_trechos(list(doc.entidades.values()))
    for a in tirados:
        doc.entidades.pop(a.id, None)
    n2 = aplicar(list(doc.entidades.values())) if tirados else (0, 0, 0, 0)
    alterar = {}
    for e in barras:
        if e.id not in doc.entidades:
            continue
        d0, d1 = antes[e.id], e.dict()
        if d1.get("perfil") != d0.get("perfil"):
            a = d1.get("atributos") or {}
            if isinstance(a.get("marcas"), dict):
                a["marcas"]["perfil"] = d1["perfil"]
                if a["marcas"].get("posicao"):
                    a["marca_a_conferir"] = True
            if "peso_kg" in a:
                try:
                    from nucleo3d.geometria import peso_barra
                    a["peso_kg"] = round(peso_barra(e), 2)
                except Exception:                         # noqa: BLE001
                    pass
            a["trocas_de_perfil"] = list(a.get("trocas_de_perfil") or []) + [
                {"de": d0.get("perfil"), "para": d1.get("perfil"), "como": "regras das tesouras"}]
            d1["atributos"] = a
        mud = {k: v for k, v in d1.items() if k != "id" and d0.get(k) != v}
        if mud:
            alterar[e.id] = mud
    fora = conferir(list(doc.entidades.values()))
    soma = [x + y for x, y in zip(n1, n2)]
    return {"novas": [], "alterar": alterar, "remover": [a.id for a in tirados],
            "resumo": {"reclassificadas": soma[0], "giradas": soma[1], "recuadas": soma[2], "encaixadas": soma[3],
                       "trechos_tirados": len(tirados), "pecas": len(alterar), "fora_depois": len(fora)},
            "avisos": ["%d peça(s) continuam fora da regra (veja o Verificar apoios)" % len(fora)] if fora else []}


TEXTO_REGRAS = __doc__
