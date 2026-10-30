# -*- coding: utf-8 -*-
"""Paredes com camadas, as uniões entre elas e o vão das esquadrias (regras ARQ-01 a ARQ-04, aprovadas em 30/10/2026).

    from arquitetura.paredes import Parede, Esquadria, montar
    pecas = montar([Parede("p1", (0, 0), (5000, 0), "EXT20", 0, 3000), ...], [Esquadria(...)])

Tudo em milímetro, com Z para cima, como o resto do modelo.

- **ARQ-01:** a parede é desenhada pelo eixo (o meio da espessura) e tem um tipo, que diz as camadas de um lado ao outro.
  São "núcleo" (o bloco) ou "acabamento" (o reboco). Padrão da DEZN: externa 20 = 3 + 14 + 3; interna 15 = 3 + 9 + 3.
- **ARQ-02:** onde duas paredes se encontram, o núcleo se amarra (fica contínuo) e o reboco contorna:
  - **L** (duas pontas no mesmo ponto): cada divisa de camada encontra a divisa de mesma ordem da outra parede, contada do
    lado de fora do canto. É a meia-esquadria camada por camada.
  - **T** (a ponta encosta no meio de outra): a parede que chega tem o núcleo até a face do núcleo da que passa e o
    reboco até a face dela. O reboco da que passa se interrompe onde o núcleo entra.
  - **X** (cruzam no meio): a mais grossa passa e a outra vira duas T (empate: passa a que veio primeiro na lista).
  - Três ou mais pontas no mesmo ponto: as duas mais opostas seguem como uma parede só e as outras chegam em T.
- **ARQ-03:** a base fica no nível e o topo no fundo da laje de cima. Aqui chegam `z0` e `z1` já resolvidos; quem liga a
  parede ao nível é quem a cria.
- **ARQ-04:** a esquadria abre o vão sozinha.
  - **Janela:** o código é o vão acabado. O osso (o vão no bloco) é maior de cada lado e em cima pela espessura do reboco,
    que volta no requadro; embaixo, o peitoril no osso fica um reboco abaixo.
  - **Porta:** o código é a folha. O osso é a folha + 100 mm na largura e + 50 mm na altura (batente + folga).

`montar` devolve, por parede, as **peças**: o polígono em planta (convexo) + z0/z1 + a camada. A planta cortada sai dessas
peças (hachura exata por camada) e o 3D é a extrusão delas (`solido_da_parede`).
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

P2 = Tuple[float, float]
TOL = 1.0          # mm: duas pontas a menos que isto são o mesmo ponto
PORTA_FOLGA_LARGURA = 100.0
PORTA_FOLGA_ALTURA = 50.0


# ------------------------------------------------------------------ tipos (ARQ-01)

@dataclass(frozen=True)
class Camada:
    nome: str
    espessura: float
    funcao: str            # "nucleo" | "acabamento"
    material: str


@dataclass(frozen=True)
class TipoParede:
    codigo: str
    nome: str
    camadas: Tuple[Camada, ...]       # do lado esquerdo do eixo (olhando de p0 para p1) para o direito

    @property
    def espessura(self) -> float:
        return sum(c.espessura for c in self.camadas)

    def divisas(self) -> List[float]:
        """afastamentos das divisas das camadas a partir do eixo, da esquerda (+) para a direita (−)"""
        s = self.espessura / 2
        out = [s]
        for c in self.camadas:
            s -= c.espessura
            out.append(s)
        return out

    def nucleo(self) -> Tuple[float, float]:
        """(afastamento da face esquerda do núcleo, da face direita)"""
        d = self.divisas()
        idx = [i for i, c in enumerate(self.camadas) if c.funcao == "nucleo"]
        if not idx:
            return d[0], d[-1]
        return d[idx[0]], d[idx[-1] + 1]

    def acabamento(self, lado: int) -> float:
        """espessura do acabamento do lado esquerdo (+1) ou direito (−1)"""
        cs = self.camadas if lado > 0 else tuple(reversed(self.camadas))
        e = 0.0
        for c in cs:
            if c.funcao == "nucleo":
                break
            e += c.espessura
        return e


REBOCO = "Argamassa"
TIPOS: Dict[str, TipoParede] = {
    "EXT20": TipoParede("EXT20", "Parede externa 20 cm", (
        Camada("reboco", 30, "acabamento", REBOCO),
        Camada("bloco cerâmico 14", 140, "nucleo", "Bloco cerâmico"),
        Camada("reboco", 30, "acabamento", REBOCO))),
    "INT15": TipoParede("INT15", "Parede interna 15 cm", (
        Camada("reboco", 30, "acabamento", REBOCO),
        Camada("bloco cerâmico 9", 90, "nucleo", "Bloco cerâmico"),
        Camada("reboco", 30, "acabamento", REBOCO))),
}


# ------------------------------------------------------------------ entrada

@dataclass
class Parede:
    id: str
    p0: P2
    p1: P2
    tipo: str = "EXT20"
    z0: float = 0.0
    z1: float = 3000.0
    origem: str = ""            # a parede de onde veio, quando a X a partiu em duas

    @property
    def tp(self) -> TipoParede:
        return TIPOS[self.tipo]


@dataclass
class Esquadria:
    id: str
    parede: str
    tipo: str                   # "janela" | "portajanela" (vidro do piso, pelo vão acabado) | "porta" (pela folha)
    u: float                    # distância de p0 da parede até o começo do vão acabado (janela) ou da folha (porta)
    largura: float              # janela: vão acabado; porta: folha
    altura: float
    peitoril: float = 0.0       # do piso (z0 da parede) ao vão acabado; porta: 0
    codigo: str = ""


@dataclass
class Peca:
    parede: str
    camada: str
    funcao: str                 # "nucleo" | "acabamento" | "requadro" | "peitoril"
    material: str
    poligono: List[P2]          # em planta, convexo, anti-horário
    z0: float
    z1: float

    @property
    def area(self) -> float:
        return abs(_area(self.poligono))

    @property
    def volume(self) -> float:
        return self.area * (self.z1 - self.z0)


@dataclass
class Montagem:
    pecas: List[Peca] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)

    def da_parede(self, pid: str) -> List[Peca]:
        return [p for p in self.pecas if p.parede == pid]


# ------------------------------------------------------------------ geometria plana

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, k):
    return (a[0] * k, a[1] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _unit(a):
    n = math.hypot(*a)
    return (a[0] / n, a[1] / n) if n > 1e-12 else (1.0, 0.0)


def _area(pts: Sequence[P2]) -> float:
    return sum(_cross(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))) / 2


def _intersecao(p, d, q, e) -> Optional[P2]:
    """reta p + t·d com a reta q + s·e"""
    den = _cross(d, e)
    if abs(den) < 1e-12:
        return None
    t = _cross(_sub(q, p), e) / den
    return _add(p, _mul(d, t))


def _cortar(poly: List[P2], ponto: P2, normal: P2) -> List[P2]:
    """parte do polígono convexo onde (x − ponto)·normal ≥ 0 (Sutherland–Hodgman)"""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        da, db = _dot(_sub(a, ponto), normal), _dot(_sub(b, ponto), normal)
        if da >= -1e-9:
            out.append(a)
        if (da >= -1e-9) != (db >= -1e-9) and abs(da - db) > 1e-12:
            out.append(_add(a, _mul(_sub(b, a), da / (da - db))))
    return out if len(out) >= 3 and abs(_area(out)) > 1e-6 else []


def _anti_horario(poly: List[P2]) -> List[P2]:
    return poly if _area(poly) >= 0 else list(reversed(poly))


# ------------------------------------------------------------------ uniões (ARQ-02)

class _Eixo:
    def __init__(self, w: Parede):
        self.w = w
        self.a, self.b = tuple(map(float, w.p0)), tuple(map(float, w.p1))
        self.d = _unit(_sub(self.b, self.a))
        self.n = (-self.d[1], self.d[0])               # esquerda
        self.L = math.dist(self.a, self.b)

    def u_de(self, p):
        return _dot(_sub(p, self.a), self.d)

    def v_de(self, p):
        return _dot(_sub(p, self.a), self.n)

    def ponto(self, u, v=0.0):
        return _add(_add(self.a, _mul(self.d, u)), _mul(self.n, v))


def _partir_cruzamentos(paredes: List[Parede]) -> List[Parede]:
    """X: a mais grossa passa e a outra é partida no cruzamento (vira duas T)"""
    ws = list(paredes)
    mudou = True
    while mudou:
        mudou = False
        for i in range(len(ws)):
            for j in range(i + 1, len(ws)):
                A, B = _Eixo(ws[i]), _Eixo(ws[j])
                x = _intersecao(A.a, A.d, B.a, B.d)
                if x is None:
                    continue
                ua, ub = A.u_de(x), B.u_de(x)
                if TOL < ua < A.L - TOL and TOL < ub < B.L - TOL:
                    passa, parte = (i, j) if ws[i].tp.espessura >= ws[j].tp.espessura else (j, i)
                    w = ws[parte]
                    org = w.origem or w.id
                    w1 = Parede(w.id + "#a", w.p0, x, w.tipo, w.z0, w.z1, org)
                    w2 = Parede(w.id + "#b", x, w.p1, w.tipo, w.z0, w.z1, org)
                    ws[parte:parte + 1] = [w1, w2]
                    mudou = True
                    break
            if mudou:
                break
    return ws


def _uma_parede(ws: List[Parede], pid: str) -> Optional[Parede]:
    for w in ws:
        if w.id == pid:
            return w
    return None


def montar(paredes: Sequence[Parede], esquadrias: Sequence[Esquadria] = ()) -> Montagem:
    m = Montagem()
    for w in paredes:
        if w.tipo not in TIPOS:
            raise ValueError(f"tipo de parede desconhecido: {w.tipo}")
        if math.dist(w.p0, w.p1) < TOL:
            raise ValueError(f"parede {w.id} sem comprimento")
    ws = _partir_cruzamentos(list(paredes))
    eixos = {w.id: _Eixo(w) for w in ws}

    # pontas: (parede, 0 = p0 | 1 = p1)
    pontas = [(w.id, k) for w in ws for k in (0, 1)]

    def pt(pid, k):
        e = eixos[pid]
        return e.a if k == 0 else e.b

    def para_dentro(pid, k):
        e = eixos[pid]
        return e.d if k == 0 else _mul(e.d, -1)

    # cortes nas pontas: para cada (parede, ponta, divisa i) a reta onde a divisa termina: (ponto, direção)
    corte: Dict[Tuple[str, int], list] = {}
    # interrupções do reboco da parede que passa: (parede hospedeira, índice da camada, ponto, direção da faixa, largura)
    faixas: List[Tuple[str, int, P2, P2, P2]] = []

    def por_camada(linhas):
        """das retas por divisa para os pares (divisa esquerda, divisa direita) de cada camada"""
        return [(linhas[i], linhas[i + 1]) for i in range(len(linhas) - 1)]

    def corte_reto(pid, k):
        e = eixos[pid]
        p = pt(pid, k)
        return por_camada([(_add(p, _mul(e.n, s)), e.n) for s in e.w.tp.divisas()])

    def corte_em_t(pid, k, hid):
        """a ponta (pid, k) chega no meio da parede hid"""
        e, h = eixos[pid], eixos[hid]
        p = pt(pid, k)
        dentro = para_dentro(pid, k)
        lado = 1 if _dot(dentro, h.n) > 0 else -1          # de que lado da hospedeira a parede chega
        dv = h.w.tp.divisas()
        nuc = h.w.tp.nucleo()
        face_nucleo = nuc[0] if lado > 0 else nuc[1]
        face = dv[0] if lado > 0 else dv[-1]
        # o núcleo vai até a face do núcleo da hospedeira; o acabamento para na face dela
        linha_nucleo = (h.ponto(0, face_nucleo), h.d)
        linha_face = (h.ponto(0, face), h.d)
        corte[(pid, k)] = [(linha_nucleo, linha_nucleo) if c.funcao == "nucleo" else (linha_face, linha_face)
                           for c in e.w.tp.camadas]
        interromper(pid, k, hid)

    def interromper(pid, k, hid):
        """a faixa do núcleo que chega interrompe o acabamento da hospedeira do lado de onde ela vem"""
        e, h = eixos[pid], eixos[hid]
        p = pt(pid, k)
        dentro = para_dentro(pid, k)
        lado = 1 if _dot(dentro, h.n) > 0 else -1
        dv = h.w.tp.divisas()
        nuc = h.w.tp.nucleo()
        face_nucleo = nuc[0] if lado > 0 else nuc[1]
        n0, n1 = e.w.tp.nucleo()
        c0 = _add(p, _mul(e.n, n0))
        c1 = _add(p, _mul(e.n, n1))
        for ci, cam in enumerate(h.w.tp.camadas):
            if cam.funcao != "acabamento":
                continue
            meio = (dv[ci] + dv[ci + 1]) / 2
            if (meio > 0) == (lado > 0) and abs(meio) > abs(face_nucleo) - 1e-6:
                faixas.append((hid, ci, c0, c1, dentro))

    def corte_em_l(pid, k, qid, kq):
        """duas pontas no mesmo ponto: cada divisa encontra a de mesma ordem da outra, contadas do lado de fora"""
        e, f = eixos[pid], eixos[qid]
        p = pt(pid, k)
        de, df = para_dentro(pid, k), para_dentro(qid, kq)
        if abs(_cross(de, df)) < 1e-6:                    # em linha: as duas seguem, corte reto
            return corte_reto(pid, k)
        fora_e = 1 if _dot(e.n, df) < 0 else -1           # o lado da parede e que fica para fora do canto
        fora_f = 1 if _dot(f.n, de) < 0 else -1
        se = sorted(e.w.tp.divisas(), key=lambda s: -s * fora_e)
        sf = sorted(f.w.tp.divisas(), key=lambda s: -s * fora_f)
        if len(se) != len(sf):                            # camadas diferentes: bissetriz para todas
            bis = _unit(_add(de, df))
            return por_camada([(_add(p, _mul(e.n, s)), bis) for s in e.w.tp.divisas()])
        mapa = {}
        for s1, s2 in zip(se, sf):
            q = _intersecao(_add(p, _mul(e.n, s1)), de, _add(p, _mul(f.n, s2)), df)
            mapa[s1] = q
        out = []
        for s in e.w.tp.divisas():
            q = mapa[s]
            # a reta do corte passa pelo ponto da divisa no canto; a direção é a da bissetriz das duas faces
            out.append((q, _unit(_add(de, df))))
        return por_camada(out)

    for pid, k in pontas:
        p = pt(pid, k)
        juntas = [(q, kq) for q, kq in pontas if (q, kq) != (pid, k) and math.dist(pt(q, kq), p) <= TOL]
        hosp = []
        for h in ws:
            if h.id == pid or any(h.id == q for q, _ in juntas):
                continue
            eh = eixos[h.id]
            u, v = eh.u_de(p), eh.v_de(p)
            if TOL < u < eh.L - TOL and abs(v) <= TOL:
                hosp.append(h.id)
        if hosp:
            corte_em_t(pid, k, hosp[0])
        elif len(juntas) == 1:
            corte[(pid, k)] = corte_em_l(pid, k, *juntas[0])
        elif len(juntas) >= 2:
            # as duas mais opostas seguem (corte reto entre elas); as outras chegam em T numa delas
            todas = [(pid, k)] + juntas
            par, melhor = None, 2.0
            for i in range(len(todas)):
                for j in range(i + 1, len(todas)):
                    c = _dot(para_dentro(*todas[i]), para_dentro(*todas[j]))
                    if c < melhor:
                        melhor, par = c, (todas[i], todas[j])
            if (pid, k) in par:
                corte[(pid, k)] = corte_reto(pid, k)
            else:
                corte_em_t(pid, k, par[0][0])
                interromper(pid, k, par[1][0])      # o núcleo que chega cobre o fim das duas que seguem
        else:
            corte[(pid, k)] = corte_reto(pid, k)

    # camadas como polígonos convexos, depois as interrupções em T
    pecas_planta: Dict[Tuple[str, int], List[List[P2]]] = {}
    for w in ws:
        e = eixos[w.id]
        divs = w.tp.divisas()
        c0, c1 = corte[(w.id, 0)], corte[(w.id, 1)]
        for ci in range(len(w.tp.camadas)):
            pts = []
            for j, i in enumerate((ci, ci + 1)):
                linha = (e.ponto(0, divs[i]), e.d)
                pts.append((_intersecao(*linha, *c0[ci][j]) or linha[0],
                            _intersecao(*linha, *c1[ci][j]) or e.ponto(e.L, divs[i])))
            poly = [pts[0][0], pts[0][1], pts[1][1], pts[1][0]]
            pecas_planta[(w.id, ci)] = [_anti_horario(poly)]

    for hid, ci, c0, c1, dentro in faixas:
        h = eixos[hid]
        novos = []
        for poly in pecas_planta[(hid, ci)]:
            # fora da faixa entre as faces do núcleo que chega (retas c0 e c1, na direção `dentro`)
            nrm = _unit((-dentro[1], dentro[0]))
            lado0 = 1 if _dot(_sub(c1, c0), nrm) > 0 else -1
            a = _cortar(poly, c0, _mul(nrm, -lado0))
            b = _cortar(poly, c1, _mul(nrm, lado0))
            novos += [x for x in (a, b) if x]
        pecas_planta[(hid, ci)] = novos

    # vãos das esquadrias (ARQ-04)
    por_parede: Dict[str, List[Esquadria]] = {}
    for q in esquadrias:
        por_parede.setdefault(q.parede, []).append(q)

    for w in ws:
        e = eixos[w.id]
        org = w.origem or w.id
        vaos = []
        for q in por_parede.get(org, []):
            u0 = q.u
            if w.origem:                     # parede partida: a esquadria mora no pedaço que a contém
                base = _uma_parede(list(paredes), org)
                u_abs0 = _Eixo(base).ponto(q.u)
                u0 = e.u_de(u_abs0)
                if not (0 <= u0 <= e.L):
                    continue
            vaos.append((q, u0))
        for ci, cam in enumerate(w.tp.camadas):
            for poly in pecas_planta[(w.id, ci)]:
                _pecas_com_vaos(m, w, e, ci, cam, poly, vaos)
        for q, u0 in vaos:
            _requadro(m, w, e, q, u0)

    return m


def _osso(w: Parede, q: Esquadria, u0: float):
    """(u0, u1, z0, z1) do vão no bloco e do vão acabado"""
    if q.tipo == "passagem":                    # vão livre, sem esquadria: o osso é o próprio vão
        a = (u0, u0 + q.largura, w.z0, w.z0 + q.altura)
        return a, a
    if q.tipo == "porta":
        a = (u0, u0 + q.largura, w.z0, w.z0 + q.altura)
        f = PORTA_FOLGA_LARGURA / 2
        o = (u0 - f, u0 + q.largura + f, w.z0, w.z0 + q.altura + PORTA_FOLGA_ALTURA)
        return o, a
    r = max(w.tp.acabamento(1), w.tp.acabamento(-1))
    a = (u0, u0 + q.largura, w.z0 + q.peitoril, w.z0 + q.peitoril + q.altura)
    if q.tipo == "portajanela":                 # vidro de correr do piso: o requadro dos lados e em cima, sem peitoril
        a = (u0, u0 + q.largura, w.z0, w.z0 + q.altura)
        return (a[0] - r, a[1] + r, a[2], a[3] + r), a
    o = (a[0] - r, a[1] + r, a[2] - r, a[3] + r)
    return o, a


def _pecas_com_vaos(m: Montagem, w: Parede, e: _Eixo, ci: int, cam: Camada, poly, vaos):
    """a camada inteira na altura, menos os vãos: o núcleo pelo osso, o acabamento pelo vão acabado (o requadro fecha a
    diferença dentro do núcleo); na porta todas as camadas pelo osso"""
    cortes = []
    for q, u0 in vaos:
        o, a = _osso(w, q, u0)
        r = o if (cam.funcao == "nucleo" or q.tipo == "porta") else a
        cortes.append(r)
    cortes.sort()
    restos = [poly]
    faixas_baixo_cima = []
    for (cu0, cu1, cz0, cz1) in cortes:
        novos = []
        for pl in restos:
            antes = _cortar(pl, e.ponto(cu0), _mul(e.d, -1))
            depois = _cortar(pl, e.ponto(cu1), e.d)
            meio = _cortar(_cortar(pl, e.ponto(cu0), e.d), e.ponto(cu1), _mul(e.d, -1))
            novos += [x for x in (antes, depois) if x]
            if meio:
                faixas_baixo_cima.append((meio, cz0, cz1))
        restos = novos
    for pl in restos:
        m.pecas.append(Peca(w.origem or w.id, cam.nome, cam.funcao, cam.material, _anti_horario(pl), w.z0, w.z1))
    for pl, cz0, cz1 in faixas_baixo_cima:
        if cz0 > w.z0 + 1e-6:
            m.pecas.append(Peca(w.origem or w.id, cam.nome, cam.funcao, cam.material, _anti_horario(pl), w.z0, cz0))
        if cz1 < w.z1 - 1e-6:
            m.pecas.append(Peca(w.origem or w.id, cam.nome, cam.funcao, cam.material, _anti_horario(pl), cz1, w.z1))


def _requadro(m: Montagem, w: Parede, e: _Eixo, q: Esquadria, u0: float):
    """janela: o reboco que volta no vão (laterais e em cima, na espessura do núcleo) e o peitoril embaixo"""
    if q.tipo == "porta":
        return
    o, a = _osso(w, q, u0)
    n0, n1 = w.tp.nucleo()

    def ret(ua, ub):
        return _anti_horario([e.ponto(ua, n0), e.ponto(ub, n0), e.ponto(ub, n1), e.ponto(ua, n1)])
    pid = w.origem or w.id
    if a[0] > o[0]:
        m.pecas.append(Peca(pid, "requadro", "requadro", REBOCO, ret(o[0], a[0]), a[2], a[3]))
    if o[1] > a[1]:
        m.pecas.append(Peca(pid, "requadro", "requadro", REBOCO, ret(a[1], o[1]), a[2], a[3]))
    if o[3] > a[3]:
        m.pecas.append(Peca(pid, "requadro", "requadro", REBOCO, ret(o[0], o[1]), a[3], o[3]))
    if a[2] > o[2]:
        m.pecas.append(Peca(pid, "peitoril", "peitoril", "Granito", ret(o[0], o[1]), o[2], a[2]))


# ------------------------------------------------------------------ 3D

def prisma(poligono: Sequence[P2], z0: float, z1: float):
    """vértices e faces de um prisma reto de base convexa (anti-horário)"""
    n = len(poligono)
    v = [(x, y, z0) for x, y in poligono] + [(x, y, z1) for x, y in poligono]
    faces = [list(reversed(range(n))), [n + i for i in range(n)]]
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    return v, faces


def solido_da_parede(pecas: Sequence[Peca], nome: str = "", material: str = "Alvenaria"):
    """um `Solido` com todas as peças da parede (uma casca por peça); a definição vai em `atributos.arq` por quem chama"""
    from nucleo3d.modelo import Solido
    vs, fs = [], []
    for p in pecas:
        v, f = prisma(p.poligono, p.z0, p.z1)
        base = len(vs)
        vs += v
        fs += [[base + i for i in face] for face in f]
    return Solido(nome=nome, camada="ARQ — Paredes", material=material, vertices=vs, faces=fs)
