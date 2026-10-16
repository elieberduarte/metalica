# -*- coding: utf-8 -*-
"""Fôrma das peças pré-moldadas do IFC (pedido do usuário, 16/10/2026: "todo o sistema foi montado para detalhar a
metálica; preciso detalhar o pré-moldado apenas, para revisar a parte estrutural").

O IFC de obra (o Mercado Conceito, do Tekla) traz o pré-moldado como sólidos: pilares, vigas L/R/T, consoles, lajes
alveolares, blocos, colarinhos, estacas, contenções. Aqui cada peça de concreto vira uma célula de fôrma:

* **Família** pelo nome da peça (`FAMILIAS`): pilares e vigas, lajes e capa, fundações, contenções e muros; o que é de
  concreto e não casa com nenhuma vai para "outras". Terreno, rua, calçada, piso e vaga não são estrutura e ficam fora;
  o neoprene, as chapas, as porcas e arruelas também (não são concreto).
* **Console** é parte do pilar (a peça que a fábrica concreta junto): o console que encosta num pilar entra na fôrma
  dele; o que não encosta em pilar entra na peça de concreto em que encosta, ou fica sozinho.
* **Peças iguais** são contadas, não repetidas: a mesma marca do Tekla (o `Reference` do IFC: VL18, NP1, Pc_PP-118) e
  a mesma geometria (medidas no sistema da peça e volume). A mesma marca com geometrias diferentes vira marca/A, /B…;
  sem marca, a sigla do nome e um número.
* **Vistas**: elevação (comprimento × altura), lateral (largura × altura) e planta (comprimento × largura), no sistema
  da peça — o eixo comprido em planta é o comprimento. As arestas vivas da malha e o contorno aparente; a escondida sai
  tracejada (camada OCULTA). Cotas: a cadeia dos pontos da forma (o console, o dente, o chanfro) e a total.

A conta é toda pela malha do IFC; nada aqui muda o 3D.
"""
import collections
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from nucleo2d.desenho import Desenho
from nucleo2d.detalhe.base import _Papel, _empilhar
from nucleo2d.detalhe.fora_do_aco import material_nao_aco, volume_da_malha, _sem_acento
from nucleo3d.modelo import Documento, Solido

#: (chave, título do desenho, padrão do nome sem acento). A ordem conta: "contenção alveolar" é contenção, não laje.
FAMILIAS: Sequence[Tuple[str, str, str]] = (
    ("contencoes", "Contenções, muros e painéis", r"conten|muro|cortina|arrimo|parede|painel|placa"),
    ("fundacoes", "Fundações", r"estaca|bloco|colarinho|enchimento|sapata|calice|baldrame|tubula"),
    ("lajes", "Lajes alveolares, capa e escadas", r"laje|capa|escada|degrau|patamar|alveolar"),
    ("pilares_vigas", "Pilares e vigas", r"pilar|viga|console|consolo|aba|dente|tirante|terca"),
)
#: A outra família: concreto que não casou com nenhum nome.
OUTRAS = ("outras", "Outras peças de concreto")
#: O que é do terreno e da urbanização, não da estrutura.
FORA = r"terreno|solo\b|rua\b|calcada|piso\b|vaga|pavimento|asfalto|grama|meio.?fio|sarjeta"
#: Camada que é de pré-moldado pelo nome (quando o material não diz).
CAMADA_PM = r"pre.?fabric|pre.?moldad|concreto|precast"
CONSOLE = r"console|consolo"
RHO_CONCRETO = 2500.0          # kg/m³
ESCALA = 25.0                   # 1:25
#: Arestas: a dobra entre duas faces a mais disto (graus) é aresta viva; a faceta do cilindro (estaca redonda) não é.
ANGULO_ARESTA = 20.0
#: Mais escondidas compridas ao longo da peça que isto numa vista (os alvéolos vistos de lado e de cima): elas saem.
MAX_OCULTAS_AO_LONGO = 6
#: A cadeia de cotas sai mesmo apertada (o número vai para fora) até este número de pontos: a altura dos consoles é a
#: informação da fôrma do pilar; com mais pontos, só a total.
MAX_PONTOS_CADEIA = 24
#: Soldagem dos vértices da malha (mm): o IFC repete o vértice em cada face.
SOLDA = 0.5


def _nome(e) -> str:
    return str(((e.atributos or {}).get("marcas") or {}).get("perfil") or e.nome or "").strip()


def referencia(e) -> str:
    """A marca da peça no IFC: o `Reference` dos Pset_*Common (o Tekla grava a posição da peça ali)."""
    for k, ps in ((e.atributos or {}).get("propriedades") or {}).items():
        if isinstance(ps, dict) and str(k).endswith("Common") and str(ps.get("Reference") or "").strip():
            return str(ps["Reference"]).strip()
    m = (e.atributos or {}).get("marcas") or {}
    return str(m.get("posicao") or "").strip()


def eh_concreto(e) -> bool:
    """Concreto pelo material; sem material que diga, pela camada do pré-moldado. O material de aço vence a camada: a
    chapa, a porca e a arruela do inserto e o neoprene ("STEEL/SHORE A-60") vêm na camada do pré-fabricado."""
    mat = material_nao_aco(e)
    if mat:
        return mat[0] == "concreto"
    m = _sem_acento(str(getattr(e, "material", "") or ""))
    if re.search(r"steel|aco\b|a36|a325|a572|astm|shore|neoprene|elastomer", m):
        return False
    return bool(re.search(CAMADA_PM, _sem_acento(str(getattr(e, "camada", "") or ""))))


def concreto_da_peca(e) -> str:
    """A classe do concreto pelo material do IFC ("CONCRETE/Fck-40" → "fck 40 MPa"), ou ""."""
    m = re.search(r"(?:fck|c)\s*[-=:]?\s*(\d{2,3})", _sem_acento(str(getattr(e, "material", "") or "")))
    return "fck %s MPa" % m.group(1) if m else ""


def familia_de(e) -> Optional[str]:
    """A família da peça de concreto pelo nome; None para o que não é estrutura (terreno, rua…) ou não é concreto."""
    if not isinstance(e, Solido) or not eh_concreto(e):
        return None
    n = _sem_acento(_nome(e))
    if re.search(FORA, n):
        return None
    for chave, _t, padrao in FAMILIAS:
        if re.search(padrao, n):
            return chave
    return OUTRAS[0]


# ------------------------------------------------------------------ malha

class _Malha:
    """A malha soldada de uma peça (ou da peça com os consoles): vértices únicos, faces, triângulos."""

    def __init__(self, ents: Sequence[Solido]):
        pts, faces = [], []
        for e in ents:
            base = len(pts)
            pts.extend(e.vertices)
            faces.extend([[base + i for i in f] for f in e.faces if len(f) >= 3])
        P = np.asarray(pts, float)
        chave = np.round(P / SOLDA).astype(np.int64)
        _u, inv = np.unique(chave, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        V = np.zeros((int(inv.max()) + 1 if len(inv) else 0, 3))
        V[inv] = P
        self.V = V
        fs = []
        for f in faces:
            g = []
            for i in f:
                j = int(inv[i])
                if not g or g[-1] != j:
                    g.append(j)
            if len(g) > 1 and g[0] == g[-1]:
                g.pop()
            if len(g) >= 3:
                fs.append(g)
        self.F = fs
        tri = [(f[0], f[k], f[k + 1]) for f in fs for k in range(1, len(f) - 1)]
        self.T = np.asarray(tri, int) if tri else np.zeros((0, 3), int)

    def normais(self) -> np.ndarray:
        out = []
        for f in self.F:
            Q = self.V[f]
            n = np.zeros(3)
            for k in range(len(f)):
                a, b = Q[k], Q[(k + 1) % len(f)]
                n += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
            L = np.linalg.norm(n)
            out.append(n / L if L > 1e-12 else n)
        return np.asarray(out)

    def arestas(self):
        """{(i, j): [faces]} de cada aresta."""
        m: Dict[Tuple[int, int], List[int]] = collections.defaultdict(list)
        for k, f in enumerate(self.F):
            for a in range(len(f)):
                i, j = f[a], f[(a + 1) % len(f)]
                m[(min(i, j), max(i, j))].append(k)
        return m


def _direcao_em_planta(V: np.ndarray, F) -> Tuple[float, float]:
    """O comprimento da peça em planta: a direção das arestas horizontais que mais se repete (módulo 90°, pesada pelo
    comprimento ao quadrado), e das duas ortogonais a de maior extensão."""
    peso: Dict[int, float] = collections.defaultdict(float)
    for f in F:
        for a in range(len(f)):
            p, q = V[f[a]], V[f[(a + 1) % len(f)]]
            dx, dy = q[0] - p[0], q[1] - p[1]
            L2 = dx * dx + dy * dy
            if L2 < 1.0:
                continue
            ang = math.degrees(math.atan2(dy, dx)) % 90.0
            peso[int(round(ang * 2)) % 180] += L2
    ang = (max(peso, key=peso.get) / 2.0) if peso else 0.0
    u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
    v = (-u[1], u[0])
    eu = V[:, 0] * u[0] + V[:, 1] * u[1]
    ev = V[:, 0] * v[0] + V[:, 1] * v[1]
    if np.ptp(ev) > np.ptp(eu) + 1.0:
        u, v = v, (-v[1], v[0])
    if u[0] < -1e-9 or (abs(u[0]) <= 1e-9 and u[1] < 0):
        u = (-u[0], -u[1])
    return u


def no_sistema_da_peca(V: np.ndarray, F) -> np.ndarray:
    """Os vértices em (comprimento, largura, altura), com o canto mínimo na origem."""
    u = _direcao_em_planta(V, F)
    v = (-u[1], u[0])
    L = np.stack([V[:, 0] * u[0] + V[:, 1] * u[1], V[:, 0] * v[0] + V[:, 1] * v[1], V[:, 2]], axis=1)
    return L - L.min(axis=0)


# ------------------------------------------------------------------ peças

class PecaPM:
    """Uma peça de fôrma: as entidades (a peça e os consoles), a geometria no sistema dela, e as instâncias."""

    def __init__(self, ents: Sequence[Solido], familia: str):
        self.ents = list(ents)
        self.familia = familia
        self.nome = _nome(ents[0])
        self.ref = referencia(ents[0])
        self.consoles = len(ents) - 1
        self.concreto = concreto_da_peca(ents[0])
        m = _Malha(ents)
        self.malha = m
        self.L = no_sistema_da_peca(m.V, m.F) if len(m.V) else np.zeros((0, 3))
        self.dims = tuple(float(x) for x in (np.ptp(self.L, axis=0) if len(self.L) else (0.0, 0.0, 0.0)))
        self.volume = sum(volume_da_malha(e.vertices, e.faces) for e in ents) / 1e9      # m³
        self.instancias: List["PecaPM"] = [self]
        self.marca = ""

    def assinatura(self) -> tuple:
        return (self.familia, self.ref or _sem_acento(self.nome), self.consoles,
                tuple(int(round(d / 5.0)) for d in self.dims), int(round(self.volume * 1000)))


def _caixa(e: Solido):
    P = np.asarray(e.vertices, float)
    return P.min(axis=0), P.max(axis=0)


def _encostam(a, b, folga: float = 10.0) -> bool:
    return bool(np.all(a[0] - folga <= b[1]) and np.all(b[0] - folga <= a[1]))


def pecas_do_modelo(doc: Documento, familias: Optional[Sequence[str]] = None, avisar=None) -> List[PecaPM]:
    """As peças de fôrma do modelo (os consoles já dentro do pilar), das famílias pedidas."""
    avisar = avisar or (lambda *a: None)
    por_fam: Dict[str, List[Solido]] = collections.defaultdict(list)
    for e in doc.entidades.values():
        if not getattr(e, "visivel", True):
            continue
        f = familia_de(e)
        if f:
            por_fam[f].append(e)
    todas = [e for es in por_fam.values() for e in es]
    consoles = [e for e in todas if re.search(CONSOLE, _sem_acento(_nome(e)))]
    ids_console = {e.id for e in consoles}
    hospedes = [e for e in todas if e.id not in ids_console]
    caixas = {e.id: _caixa(e) for e in todas}
    # o console vai para o pilar em que encosta; sem pilar, para a peça de concreto em que encosta
    dono: Dict[str, List[Solido]] = collections.defaultdict(list)
    soltos = []
    pilares = [e for e in hospedes if re.search(r"pilar", _sem_acento(_nome(e)))]
    for c in consoles:
        cx = caixas[c.id]
        alvo = next((p for p in pilares if _encostam(cx, caixas[p.id])), None)
        if alvo is None:
            alvo = next((p for p in hospedes if _encostam(cx, caixas[p.id])), None)
        if alvo is None:
            soltos.append(c)
        else:
            dono[alvo.id].append(c)
    avisar("%d peças de concreto, %d consoles (%d soltos)" % (len(hospedes), len(consoles), len(soltos)))
    fam_de = {e.id: f for f, es in por_fam.items() for e in es}
    pedidas = set(familias) if familias else None
    pecas = []
    for i, e in enumerate(hospedes + soltos):
        f = fam_de[e.id]
        if pedidas is not None and f not in pedidas:
            continue
        if i % 200 == 0:
            avisar("geometria das peças (%d de %d)" % (i, len(hospedes) + len(soltos)))
        try:
            pecas.append(PecaPM([e] + dono.get(e.id, []), f))
        except Exception:                                   # noqa: BLE001 — a peça sem malha boa fica de fora
            continue
    return pecas


def _sigla(nome: str) -> str:
    palavras = [w for w in re.split(r"[^A-Za-z]+", _sem_acento(nome).upper()) if w and w not in ("P", "DE", "DA", "DO")]
    return "".join(w[0] for w in palavras[:3]) or "PC"


def agrupar(pecas: Sequence[PecaPM]) -> List[PecaPM]:
    """As peças iguais juntas (a primeira de cada grupo representa, com as instâncias) e as marcas dadas."""
    grupos: Dict[tuple, PecaPM] = {}
    for p in pecas:
        a = p.assinatura()
        if a in grupos:
            grupos[a].instancias.append(p)
        else:
            grupos[a] = p
    reps = list(grupos.values())
    # a mesma marca do Tekla com geometrias diferentes: /A, /B… (da mais usada para a menos)
    por_ref: Dict[str, List[PecaPM]] = collections.defaultdict(list)
    sem_ref: Dict[str, List[PecaPM]] = collections.defaultdict(list)
    for r in reps:
        (por_ref[r.ref] if r.ref else sem_ref[_sigla(r.nome)]).append(r)
    for ref, lst in por_ref.items():
        lst.sort(key=lambda r: (-len(r.instancias), r.dims))
        for k, r in enumerate(lst):
            r.marca = ref if len(lst) == 1 else "%s/%s" % (ref, chr(65 + k) if k < 26 else str(k + 1))
    usadas = {r.marca for r in reps if r.marca}
    for sig, lst in sem_ref.items():
        lst.sort(key=lambda r: (-len(r.instancias), r.dims))
        n = 0
        for r in lst:
            n += 1
            while "%s%d" % (sig, n) in usadas:
                n += 1
            r.marca = "%s%d" % (sig, n)
            usadas.add(r.marca)
    ordem_nome = lambda r: (_sem_acento(r.nome), [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", r.marca)])
    return sorted(reps, key=ordem_nome)


# ------------------------------------------------------------------ vistas

#: (título, eixo horizontal, eixo vertical, eixo de profundidade, sinal: +1 = o observador do lado do maior valor)
VISTAS = (("ELEVAÇÃO", 0, 2, 1, -1), ("VISTA LATERAL", 1, 2, 0, 1), ("PLANTA", 0, 1, 2, 1))


def _segmentos_da_vista(p: PecaPM, iu: int, iv: int, iw: int, sinal: int):
    """[(u1, v1, u2, v2, visível)] das arestas vivas e do contorno aparente, vistos de `iw` (o observador do lado
    `sinal`), sem repetir o que cai no mesmo traço (o visível vence)."""
    m, L = p.malha, p.L
    if not len(L) or not m.F:
        return []
    N = m.normais()
    # a normal no sistema da peça: a mesma rotação dos vértices (só no plano), refeita pela diferença das posições
    u = _direcao_em_planta(m.V, m.F)
    R = np.array([[u[0], u[1], 0.0], [-u[1], u[0], 0.0], [0.0, 0.0, 1.0]])
    NL = N @ R.T
    vista = NL[:, iw] * sinal                              # > 0: a face olha para o observador
    cos_lim = math.cos(math.radians(ANGULO_ARESTA))
    cand = []
    for (i, j), fs in m.arestas().items():
        if len(fs) == 1:
            cand.append((i, j, True))
        else:
            a, b = NL[fs[0]], NL[fs[1]]
            dobra = float(np.dot(a, b)) < cos_lim
            if dobra or (vista[fs[0]] > 1e-6) != (vista[fs[1]] > 1e-6):
                cand.append((i, j, dobra))
    if not cand:
        return []
    # visibilidade: o ponto da aresta está escondido se um triângulo cobre ele e fica mais perto do observador
    T = m.T
    A, B, C = L[T[:, 0]], L[T[:, 1]], L[T[:, 2]]
    au, av, bu, bv, cu, cv = A[:, iu], A[:, iv], B[:, iu], B[:, iv], C[:, iu], C[:, iv]
    den = (bv - cv) * (au - cu) + (cu - bu) * (av - cv)
    ok = np.abs(den) > 1e-9
    den = np.where(ok, den, 1.0)

    def escondido(q) -> bool:
        x, y, w = q[iu], q[iv], q[iw]
        l1 = ((bv - cv) * (x - cu) + (cu - bu) * (y - cv)) / den
        l2 = ((cv - av) * (x - cu) + (au - cu) * (y - cv)) / den
        l3 = 1.0 - l1 - l2
        dentro = ok & (l1 > 0.02) & (l2 > 0.02) & (l3 > 0.02)
        if not dentro.any():
            return False
        wt = l1 * A[:, iw] + l2 * B[:, iw] + l3 * C[:, iw]
        return bool(np.any(dentro & ((wt - w) * sinal > 1.0)))

    saida: Dict[tuple, list] = {}
    for i, j, dobra in cand:
        a, b = L[i], L[j]
        ua, va, ub, vb = round(a[iu], 1), round(a[iv], 1), round(b[iu], 1), round(b[iv], 1)
        if abs(ua - ub) < 0.5 and abs(va - vb) < 0.5:
            continue                                        # a aresta de ponta (vista de frente) vira um ponto
        vis = any(not escondido(a + (b - a) * t) for t in (0.2, 0.5, 0.8))
        if not vis and not dobra:
            continue                                        # o contorno aparente escondido (o alvéolo) não é aresta
        k = (ua, va, ub, vb) if (ua, va) <= (ub, vb) else (ub, vb, ua, va)
        k = tuple(round(x) for x in k)
        if k not in saida or (vis and not saida[k][4]):
            saida[k] = [k[0], k[1], k[2], k[3], vis]
    out = list(saida.values())
    # os alvéolos da laje vistos de lado e de cima: muitas escondidas compridas ao longo da peça só borram a vista —
    # saem essas; o furo da estaca no bloco (o círculo facetado) fica
    larg = float(np.ptp(L[:, iu])) if len(L) else 0.0
    compridas = [s for s in out if not s[4] and abs(s[1] - s[3]) < 1.0 and abs(s[2] - s[0]) >= 0.6 * larg]
    if len(compridas) > MAX_OCULTAS_AO_LONGO:
        tirar = {id(s) for s in compridas}
        out = [s for s in out if id(s) not in tirar]
    return out


#: Pontos da cadeia mais perto que isto (mm) são um só: o chanfro e a pingadeira de 10–15 mm viravam cotas miúdas.
JUNTAR_CADEIA = 15.0


def _juntar_perto(vals, total: float) -> List[float]:
    """Os pontos da cadeia de 0 a `total`, sem os que ficam a menos de `JUNTAR_CADEIA` do anterior (as pontas ficam)."""
    out = [0.0]
    for v in sorted(float(x) for x in vals if 0.0 < x < total):
        if v - out[-1] >= JUNTAR_CADEIA and total - v >= JUNTAR_CADEIA:
            out.append(v)
    out.append(float(round(total)))
    return out


def _num(x: float) -> str:
    return ("%.0f" % x) if abs(x - round(x)) < 0.05 else ("%.1f" % x).replace(".", ",")


def desenhar_celula(desenho: Desenho, p: PecaPM, dx: float, dy: float):
    """A célula da peça em (dx, dy): título, as três vistas com as cotas. Devolve os extremos."""
    esc = desenho.escala
    # detalhe + posicao: a célula que as pranchas reconhecem (manter_montagem) e que o CAD trava como uma peça só; o
    # "premoldado" não liga nenhuma ferramenta do aço (elas olham detalhe == "posicao")
    pap = _Papel(desenho, {"detalhe": "premoldado", "posicao": p.marca, "familia": p.familia}, dx, dy)
    Lx, Ly, Lz = p.dims
    gap = 22.0 * esc
    # posições das vistas na célula (origem = canto de baixo à esquerda da elevação)
    origem = {"ELEVAÇÃO": (0.0, 0.0), "VISTA LATERAL": (Lx + gap, 0.0), "PLANTA": (0.0, -(Ly + gap))}
    for titulo, iu, iv, iw, sinal in VISTAS:
        ox, oy = origem[titulo]
        segs = _segmentos_da_vista(p, iu, iv, iw, sinal)
        for u1, v1, u2, v2, vis in segs:
            pap.linha(ox + u1, oy + v1, ox + u2, oy + v2, "VISTA" if vis else "OCULTA")
        larg, alt = (p.dims[iu], p.dims[iv])
        # cotas: a cadeia dos pontos da forma (só o que aparece) e a total por fora
        us = _juntar_perto({round(s[0]) for s in segs if s[4]} | {round(s[2]) for s in segs if s[4]}, larg)
        vs = _juntar_perto({round(s[1]) for s in segs if s[4]} | {round(s[3]) for s in segs if s[4]}, alt)
        fez_u = 2 < len(us) <= MAX_PONTOS_CADEIA and pap.cadeia_h([ox + x for x in us], oy, -8.0, exigir_espaco=False)
        pap.cota_h(ox, ox + larg, oy, -15.0 if fez_u else -8.0)
        fez_v = 2 < len(vs) <= MAX_PONTOS_CADEIA and pap.cadeia_v([oy + y for y in vs], ox, -8.0, exigir_espaco=False)
        pap.cota_v(oy, oy + alt, ox, -15.0 if fez_v else -8.0)
        pap.texto(ox + larg / 2, oy + alt + 4.0 * esc, titulo, 2.5 * esc, alinhamento="centro")
    # o título da célula
    n = len(p.instancias)
    topo = Lz + 12.0 * esc
    pap.texto(0.0, topo + 7.0 * esc, "%s – %dx" % (p.marca, n), 5.0 * esc)
    linha2 = "%s · %s × %s × %s mm" % (p.nome or "peça", _num(Lx), _num(Ly), _num(Lz))
    if p.consoles:
        linha2 += " · com %d console%s" % (p.consoles, "" if p.consoles == 1 else "s")
    pap.texto(0.0, topo + 1.5 * esc, linha2, 2.8 * esc)
    peso = p.volume * RHO_CONCRETO
    pap.texto(0.0, topo - 3.5 * esc, "%sVolume %s m³ · peso %s kg (2,5 t/m³) · total %s m³" % (
        "Concreto %s · " % p.concreto if p.concreto else "",
        ("%.3f" % p.volume).replace(".", ","), _num(peso), ("%.2f" % (p.volume * n)).replace(".", ",")), 2.5 * esc)
    return pap.extremos


def desenhos(doc: Documento, familias: Optional[Sequence[str]] = None, prefixo: str = "pré-moldado",
             avisar=None, reps: Optional[Sequence[PecaPM]] = None) -> Dict[str, Desenho]:
    """{família: Desenho} com as fôrmas das peças das famílias pedidas (todas, sem `familias`). `reps`: as peças já
    agrupadas (as do modelo inteiro, as mesmas marcas dos desenhos de conjunto)."""
    avisar = avisar or (lambda *a: None)
    if reps is None:
        reps = agrupar(pecas_do_modelo(doc, familias, avisar))
    if familias:
        reps = [r for r in reps if r.familia in set(familias)]
    titulos = dict([(k, t) for k, t, _p in FAMILIAS] + [OUTRAS])
    saida: Dict[str, Desenho] = {}
    ordem = [k for k, _t, _p in FAMILIAS[::-1]] + [OUTRAS[0]]       # pilares e vigas primeiro
    for fam in ordem:
        lst = [r for r in reps if r.familia == fam]
        if not lst:
            continue
        d = Desenho(nome="%s – %s" % (prefixo, titulos[fam]), escala=ESCALA)
        d.metadados["premoldado"] = {"familia": fam, "pecas": sum(len(r.instancias) for r in lst), "marcas": len(lst)}
        celulas = []
        for k, r in enumerate(lst):
            celulas.append(lambda x, y, r=r: desenhar_celula(d, r, x, y))
        avisar("desenhando %s: %d marcas" % (titulos[fam].lower(), len(lst)))
        _empilhar(d, celulas, largura_max_papel=1100.0)
        saida[fam] = d
    return saida


def resumo(doc: Documento) -> List[dict]:
    """Quantas peças e marcas cada família tem (o diálogo mostra antes de detalhar)."""
    cont: Dict[str, int] = collections.Counter()
    for e in doc.entidades.values():
        f = familia_de(e)
        if f and not re.search(CONSOLE, _sem_acento(_nome(e))):
            cont[f] += 1
    titulos = [(k, t) for k, t, _p in FAMILIAS[::-1]] + [OUTRAS]
    return [{"familia": k, "titulo": t, "pecas": cont.get(k, 0)} for k, t in titulos]


# ------------------------------------------------------------------ desenhos de conjunto (16/10)
# As plantas, os cortes e as elevações são os da metálica (nucleo2d/detalhe/conjuntos.py: desenho_de_localizacao e
# desenho_de_elevacoes), com as peças de concreto marcadas pela marca da fôrma — o rótulo na planta é o mesmo da célula.

#: (chave, título do desenho)
GERAIS: Sequence[Tuple[str, str]] = (
    ("locacao", "Planta de locação dos pilares"),
    ("formas_niveis", "Plantas de fôrma por nível"),
    ("cortes", "Cortes"),
    ("elevacoes", "Elevações"),
)
#: Topos de vigas e lajes a menos disto (mm) são o mesmo nível; nível com menos peças que NIVEL_MINIMO não sai.
TOL_NIVEL = 100.0
NIVEL_MINIMO = 3


def _marcadas(reps: Sequence[PecaPM]) -> Tuple[List[Solido], Dict[str, str]]:
    """Cópias das peças de concreto com a marca da fôrma como conjunto (a localização da metálica rotula os conjuntos,
    também nos cortes): a peça principal com a posição «marca'», o console com «marca'c» — a instância do pilar fica
    com os consoles dele. Devolve as cópias e {id: família}."""
    import copy as _copy
    out, fam = [], {}
    for r in reps:
        for inst in r.instancias:
            for k, e in enumerate(inst.ents):
                c = _copy.copy(e)
                a = dict(e.atributos or {})
                a["marcas"] = {"conjunto": r.marca, "posicao": r.marca + ("'c" if k else "'"), "perfil": inst.nome}
                c.atributos = a
                out.append(c)
                fam[c.id] = r.familia
    return out, fam


def _z(e) -> Tuple[float, float]:
    zs = [v[2] for v in e.vertices]
    return min(zs), max(zs)


def niveis(reps: Sequence[PecaPM]) -> List[float]:
    """Os níveis da estrutura: o topo das vigas e lajes agrupado (o console e o pilar não contam)."""
    tops = []
    for r in reps:
        if r.familia not in ("pilares_vigas", "lajes") or re.search(r"pilar", _sem_acento(r.nome)):
            continue
        for inst in r.instancias:
            tops.append(_z(inst.ents[0])[1])
    grupos: List[List[float]] = []
    for z in sorted(tops):
        if grupos and z - grupos[-1][-1] <= TOL_NIVEL:
            grupos[-1].append(z)
        else:
            grupos.append([z])
    return [max(g) for g in grupos if len(g) >= NIVEL_MINIMO]


def _nivel_txt(z: float) -> str:
    return ("%+.2f" % (z / 1000.0)).replace(".", ",")


def desenhos_gerais(doc: Documento, reps: Sequence[PecaPM], pedidos: Sequence[str], eixos: Optional[dict] = None,
                    prefixo: str = "pré-moldado", avisar=None) -> Dict[str, Desenho]:
    """{chave: Desenho} dos desenhos de conjunto pedidos (GERAIS), pelos geradores da metálica."""
    from nucleo.base import ErroDeDados
    from nucleo2d.detalhe.conjuntos import desenho_de_localizacao, desenho_de_elevacoes
    from nucleo2d.detalhar import _anexar_quadro
    avisar = avisar or (lambda *a: None)
    pecas, fam = _marcadas(reps)
    titulos = dict(GERAIS)
    # o lado comprido do prédio inteiro: todas as plantas giram iguais
    todos = [v for e in pecas for v in e.vertices]
    deitar = (max(v[1] for v in todos) - min(v[1] for v in todos)) > (max(v[0] for v in todos) - min(v[0] for v in todos)) if todos else None
    saida: Dict[str, Desenho] = {}

    def nome(k):
        return "%s – %s" % (prefixo, titulos[k])

    def eh(e, padrao):
        return bool(re.search(padrao, _sem_acento(str((e.atributos.get("marcas") or {}).get("perfil") or e.nome or ""))))

    try:
        if "locacao" in pedidos:
            avisar("planta de locação dos pilares…")
            # o pilar e o bloco (ou a sapata) — a estaca, o colarinho e o enchimento empilhavam marcas no mesmo ponto
            sel = [e for e in pecas if (eh(e, r"pilar|bloco|sapata|calice") and not eh(e, r"enchimento")) and not eh(e, CONSOLE)]
            if sel:
                saida["locacao"] = desenho_de_localizacao(doc, sel, nome("locacao"), eixos=eixos, vistas_pedidas=("topo",),
                                                          titulo_planta="PLANTA DE LOCAÇÃO DOS PILARES E FUNDAÇÕES",
                                                          deitar_em_y=deitar, rotular_de_topo=True)
        if "formas_niveis" in pedidos:
            zs = niveis(reps)
            plantas = []
            for z in zs:
                avisar("planta de fôrma do nível %s…" % _nivel_txt(z))
                sel = []
                for e in pecas:
                    z0, z1 = _z(e)
                    if fam[e.id] == "fundacoes":
                        continue
                    if abs(z1 - z) <= TOL_NIVEL and not eh(e, CONSOLE):
                        sel.append(e)                       # as vigas e lajes do nível
                    elif eh(e, r"pilar") and z0 < z - TOL_NIVEL < z1:
                        sel.append(e)                       # o pilar que passa por ele
                if len(sel) >= NIVEL_MINIMO:
                    try:
                        plantas.append((z, desenho_de_localizacao(doc, sel, "nível", eixos=eixos, vistas_pedidas=("topo",),
                                                                  titulo_planta="PLANTA DE FÔRMA – NÍVEL %s" % _nivel_txt(z),
                                                                  deitar_em_y=deitar, rotular_de_topo=True)))
                    except ErroDeDados:
                        continue
            if plantas:
                dc = Desenho(nome=nome("formas_niveis"), escala=max(d.escala for _z_, d in plantas))
                y = 0.0
                for z, d in sorted(plantas, key=lambda t: -t[0]):         # de cima para baixo
                    y = _anexar_quadro(dc, d, "NÍVEL %s" % _nivel_txt(z), y)
                dc.metadados["premoldado"] = {"niveis": [round(z, 1) for z, _d in plantas]}
                saida["formas_niveis"] = dc
        if "cortes" in pedidos:
            avisar("cortes…")
            sel = [e for e in pecas]
            saida["cortes"] = desenho_de_localizacao(doc, sel, nome("cortes"), eixos=eixos,
                                                     vistas_pedidas=("frente", "lateral"), deitar_em_y=deitar)
        if "elevacoes" in pedidos:
            avisar("elevações das fachadas…")
            sel = [e for e in pecas if fam[e.id] != "fundacoes"]
            saida["elevacoes"] = desenho_de_elevacoes(doc, sel, nome("elevacoes"), eixos=eixos)
    except ErroDeDados as e:
        avisar("desenho de conjunto não gerado: %s" % e)
    for k, d in saida.items():
        d.metadados.setdefault("premoldado", {})["geral"] = k
    return saida
