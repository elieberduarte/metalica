"""Esforços na estrutura inteira, calculados no esqueleto (`analitico.py`).

Cada barra do esqueleto é uma barra de pórtico espacial (12 graus de liberdade, nós rígidos): a
treliça, a terça, a viga e o pilar juntos, as transições apoiando umas nas outras — o caminho
que a carga faz de verdade até a base. É a primeira prova do modelo: as reações nos pilares
têm de bater com as cargas que a locação do projeto escreve por pilar.

Hipóteses desta primeira versão (aparecem no resultado, em `hipoteses`):
- nós rígidos em tudo (a treliça de nós rígidos dá os mesmos esforços normais da rotulada, com
  pequenos momentos secundários); o contravento redondo trabalha também à compressão;
- o perfil duplo do esqueleto (2L, 2Ue em caixão) conta como duas vezes o perfil simples
  (área e inércias), sem o afastamento entre eles — conservador na rigidez, não nas reações;
- a inércia maior no plano vertical que contém a barra (treliças, terças, vigas); no pilar,
  a maior em torno de X;
- o pé do pilar é rotulado; é engastado quando a locação dá momento naquela base;
- as cargas de cobertura chegam pelas terças, cada uma com a faixa até a meia distância das
  vizinhas (a largura de influência), nos nós das pontas dela;
- o peso próprio é o do perfil (kg/m do catálogo) no comprimento de eixo a eixo, nos dois nós.

Unidades: kN e m no cálculo; o resultado traz as reações também em tf, a unidade da locação.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional

import numpy as np

from nucleo3d.analitico import analitico

E_ACO = 200e6          # kN/m²
G_ACO = 77e6           # kN/m²
G = 9.80665e-3         # kN por kg
TF = 9.80665           # kN por tf

#: cargas de cobertura padrão (kN/m²) — cada uma é uma hipótese, a conferir com o projeto
CARGAS_PADRAO = {
    "telha": 0.055,          # telha de aço 0,50 mm (TR40 0,50 mm no desenho do Posto CB)
    "forro": 0.0,            # forro e instalações pendurados na cobertura
    "paineis": 0.0,          # painéis solares espalhados na cobertura (kN/m² de cobertura)
    "sobrecarga": 0.25,      # NBR 8800, B.5.1: cobertura comum, projeção horizontal
}
PERMANENTES = ("telha", "forro", "paineis")


def cargas_do_projeto(projeto: dict) -> dict:
    """as cargas que o projetista escreveu nas folhas (considerações de cálculo), em kN/m², com
    a fonte; sem elas, as padrão"""
    from nucleo2d.folhas_recebidas import cargas_kN
    rec = (projeto or {}).get("projeto_recebido") or {}
    c = cargas_kN(rec)
    if not c:
        return dict(CARGAS_PADRAO, fonte="padrão do programa")
    out = dict(CARGAS_PADRAO, forro=0.0, paineis=0.0)
    out.update(c)
    out["fonte"] = "considerações de cálculo do projetista (%s)" % (rec.get("arquivo") or "folhas do DXF")
    return out
LARG_MAX = 3.5               # m: vizinha mais longe que isso não é a terça do lado
BASE_TOL = 50.0              # mm: o pé do pilar


# ------------------------------------------------------------------ seções

def _secao(nome: str, duplo: bool, cache: dict) -> Optional[tuple]:
    """(A, I_forte, I_fraca, J, kg/m) em m e kg, pelo nome do perfil no catálogo"""
    if nome in cache:
        s = cache[nome]
    else:
        from nucleo3d.calculo_ifc import _perfil_de
        p = _perfil_de(nome or "", "", {}, {})
        s = None
        if p is not None and p.A > 0:
            A = p.A * 1e-4
            Ix, Iy = p.Ix * 1e-8, p.Iy * 1e-8
            J = (p.dados.get("J") or 0.0) * 1e-8
            if Ix <= 0:                      # barra redonda: o catálogo só dá a área
                Ix = Iy = A * A / (4 * math.pi)
                J = 2 * Ix
            s = (A, max(Ix, Iy), min(Ix, Iy) or max(Ix, Iy), J or min(Ix, Iy) * 0.01, p.massa or A * 7850.0)
        cache[nome] = s
    if s is None:
        return None
    k = 2.0 if duplo else 1.0
    return tuple(v * k for v in s)


# ------------------------------------------------------------------ largura de influência das terças

def _larguras(nos: np.ndarray, tercas: List[int], barras: List[dict]) -> Dict[int, float]:
    """a faixa de cobertura que cada trecho de terça recebe: meia distância até a terça vizinha
    de cada lado (na horizontal, na perpendicular a ela); na borda, só a meia do lado que tem"""
    info = []
    for k in tercas:
        a, b = nos[barras[k]["a"]], nos[barras[k]["b"]]
        d = b[:2] - a[:2]
        L = float(np.hypot(*d))
        if L < 1e-6:
            continue
        info.append((k, (a[:2] + b[:2]) / 2, d / L, a[:2], b[:2]))
    grade = collections.defaultdict(list)
    for i, (_k, m, _u, _a, _b) in enumerate(info):
        grade[(int(m[0] // LARG_MAX), int(m[1] // LARG_MAX))].append(i)
    out = {}
    for k, m, u, _a, _b in info:
        n = np.array([-u[1], u[0]])
        lados = {1: None, -1: None}
        cx, cy = int(m[0] // LARG_MAX), int(m[1] // LARG_MAX)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grade.get((cx + dx, cy + dy), ()):
                    k2, _m2, u2, a2, b2 = info[j]
                    if k2 == k or abs(u[0] * u2[1] - u[1] * u2[0]) > 0.25:
                        continue                      # a mesma, ou não é paralela
                    # onde a perpendicular pelo meio desta cruza a outra
                    d2 = b2 - a2
                    den = n[0] * d2[1] - n[1] * d2[0]
                    if abs(den) < 1e-9:
                        continue
                    w = a2 - m
                    s = (w[0] * d2[1] - w[1] * d2[0]) / den      # distância ao longo de n
                    t = (w[0] * n[1] - w[1] * n[0]) / den        # posição na outra (0..1)
                    if not (-0.05 <= t <= 1.05) or abs(s) < 0.05 or abs(s) > LARG_MAX:
                        continue
                    lado = 1 if s > 0 else -1
                    if lados[lado] is None or abs(s) < lados[lado]:
                        lados[lado] = abs(s)
        tem = [v for v in lados.values() if v]
        out[k] = sum(tem) / 2.0 if tem else 0.0
    return out


# ------------------------------------------------------------------ pórtico espacial

def _eixos_locais(d: np.ndarray) -> np.ndarray:
    """(n, 3, 3): as linhas são x (ao longo da barra), y e z locais. z fica no plano vertical da
    barra (a inércia forte trabalha nele); na barra vertical, z = X global"""
    L = np.linalg.norm(d, axis=1)
    ex = d / L[:, None]
    ref = np.tile(np.array([0.0, 0.0, 1.0]), (len(d), 1))
    vert = np.abs(ex[:, 2]) > 0.995
    ref[vert] = (1.0, 0.0, 0.0)
    ez = ref - (ref * ex).sum(1)[:, None] * ex
    ez /= np.linalg.norm(ez, axis=1)[:, None]
    ey = np.cross(ez, ex)
    return np.stack([ex, ey, ez], axis=1)


def _rigidez_local(L, A, Iy, Iz, J) -> np.ndarray:
    """(n, 12, 12) da barra de pórtico espacial (Iy: flexão em torno de y local, no plano x-z)"""
    n = len(L)
    k = np.zeros((n, 12, 12))

    def por(i, j, v):                                      # o termo e o simétrico dele
        k[:, i, j] = v
        k[:, j, i] = v
    EA, GJ = E_ACO * A / L, G_ACO * J / L
    for i, j, v in ((0, 0, EA), (6, 6, EA), (0, 6, -EA), (3, 3, GJ), (9, 9, GJ), (3, 9, -GJ)):
        por(i, j, v)
    # flexão no plano x-y (em torno de z): graus 1, 5, 7, 11; no plano x-z (em torno de y): 2, 4, 8, 10
    for (v1, r1, v2, r2), I, s in (((1, 5, 7, 11), Iz, 1.0), ((2, 4, 8, 10), Iy, -1.0)):
        EI = E_ACO * I
        a, b, c, d = 12 * EI / L ** 3, 6 * EI / L ** 2, 4 * EI / L, 2 * EI / L
        por(v1, v1, a); por(v2, v2, a); por(v1, v2, -a)
        por(v1, r1, s * b); por(v1, r2, s * b); por(v2, r1, -s * b); por(v2, r2, -s * b)
        por(r1, r1, c); por(r2, r2, c); por(r1, r2, d)
    return k


def _transformacao(R: np.ndarray) -> np.ndarray:
    T = np.zeros((len(R), 12, 12))
    for i in range(4):
        T[:, 3 * i:3 * i + 3, 3 * i:3 * i + 3] = R
    return T


# ------------------------------------------------------------------ o cálculo

def calcular(doc, cargas: Optional[dict] = None, esq: Optional[dict] = None) -> dict:
    """reações e esforços da estrutura inteira para os casos PP (peso próprio), CP (telha, forro
    e painéis) e SC (sobrecarga). Devolve {casos, reacoes, pilares, barras, soltas, resumo,
    hipoteses, avisos}"""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    from scipy.sparse.csgraph import connected_components

    car = dict(CARGAS_PADRAO)
    car.update({k: (v if k == "fonte" else float(v)) for k, v in (cargas or {}).items() if v not in (None, "")})
    esq = esq or analitico(doc)
    nos = np.array(esq["nos"], float) / 1000.0
    barras = esq["barras"]
    avisos: List[str] = []

    # --- seções
    cache: dict = {}
    props, usadas, sem_perfil = [], [], collections.Counter()
    for i, br in enumerate(barras):
        s = _secao(br["perfil"], br["duplo"], cache)
        if s is None or br["a"] == br["b"]:
            sem_perfil[br["perfil"] or "(sem perfil)"] += 1
            continue
        props.append(s)
        usadas.append(i)
    if sem_perfil:
        avisos.append("barras sem perfil no catálogo, fora do cálculo: %s" % dict(sem_perfil))
    P = np.array(props)
    ia = np.array([barras[i]["a"] for i in usadas])
    ib = np.array([barras[i]["b"] for i in usadas])
    d = nos[ib] - nos[ia]
    L = np.linalg.norm(d, axis=1)

    # --- apoios: o pé dos pilares
    base = min((nos[barras[i][k]][2] for i in usadas if barras[i]["papel"] == "pilar" for k in ("a", "b")), default=0.0)
    pes = sorted({barras[i][k] for i in usadas if barras[i]["papel"] == "pilar" for k in ("a", "b")
                  if nos[barras[i][k]][2] <= base + BASE_TOL / 1000.0})
    loc = ((doc.metadados or {}).get("de_planta") or {}).get("cargas_locacao") or {}
    loc_itens = list(loc.get("pilares") or [])
    engaste = set()
    for n in pes:
        c = min(loc_itens, key=lambda c: math.dist((c["x"] / 1000.0, c["y"] / 1000.0), nos[n][:2]), default=None)
        if c and math.dist((c["x"] / 1000.0, c["y"] / 1000.0), nos[n][:2]) < 1.5 and ("Mx" in c or "My" in c):
            engaste.add(n)

    # --- só a parte ligada a algum apoio entra; o resto é peça solta (aviso)
    nn = len(nos)
    adj = sp.coo_matrix((np.ones(len(ia)), (ia, ib)), shape=(nn, nn))
    ncomp, rot = connected_components(adj, directed=False)
    comp_apoiada = {rot[n] for n in pes}
    usados_nos = np.zeros(nn, bool)
    usados_nos[ia] = True
    usados_nos[ib] = True
    fora = [i for i, e in enumerate(usadas) if rot[ia[i]] not in comp_apoiada]
    if fora:
        pecas = collections.Counter(barras[usadas[i]]["peca"] or barras[usadas[i]]["papel"] for i in fora)
        avisos.append("%d barras sem caminho até um pilar, fora do cálculo: %s" % (len(fora), dict(pecas.most_common(8))))
    manter = np.array([rot[ia[i]] in comp_apoiada for i in range(len(usadas))])
    usadas = [e for e, m in zip(usadas, manter) if m]
    P, ia, ib, d, L = P[manter], ia[manter], ib[manter], d[manter], L[manter]

    # --- rigidez
    R = _eixos_locais(d)
    T = _transformacao(R)
    kl = _rigidez_local(L, P[:, 0], P[:, 1], P[:, 2], P[:, 3])
    kg = np.einsum("nji,njk,nkl->nil", T, kl, T)
    gl = np.concatenate([ia[:, None] * 6 + np.arange(6), ib[:, None] * 6 + np.arange(6)], axis=1)
    lin = np.repeat(gl, 12, axis=1).ravel()
    col = np.tile(gl, (1, 12)).ravel()
    ndof = nn * 6
    K = sp.csr_matrix((kg.ravel(), (lin, col)), shape=(ndof, ndof))

    # --- casos de carga (forças nodais, kN)
    casos = {"PP": np.zeros(ndof), "CP": np.zeros(ndof), "SC": np.zeros(ndof)}
    peso = P[:, 4] * L * G
    np.add.at(casos["PP"], ia * 6 + 2, -peso / 2)
    np.add.at(casos["PP"], ib * 6 + 2, -peso / 2)
    pos = {e: i for i, e in enumerate(usadas)}
    tercas = [e for e in usadas if barras[e]["papel"] == "terça"]
    larg = _larguras(nos, tercas, barras)
    area = 0.0
    sem_vizinha = 0
    for e, w in larg.items():
        i = pos[e]
        if w <= 0:
            sem_vizinha += 1
            continue
        Lh = float(np.hypot(d[i][0], d[i][1]))
        area += w * Lh
        for caso, q, comp in (("CP", sum(car[k] for k in PERMANENTES), L[i]), ("SC", car["sobrecarga"], Lh)):
            f = q * w * comp / 2
            casos[caso][ia[i] * 6 + 2] -= f
            casos[caso][ib[i] * 6 + 2] -= f
    if sem_vizinha:
        avisos.append("%d trechos de terça sem outra terça paralela a até %.1f m: sem carga de cobertura" % (sem_vizinha, LARG_MAX))

    # --- restrições
    presos = np.zeros(ndof, bool)
    for n in pes:
        presos[n * 6:n * 6 + (6 if n in engaste else 3)] = True
    livres_nos = ~usados_nos
    for n in np.nonzero(livres_nos)[0]:
        presos[n * 6:n * 6 + 6] = True                      # nó de barra que ficou de fora
    livre = np.nonzero(~presos)[0]
    Kff = K[livre][:, livre].tocsc()
    # um grau sem rigidez nenhuma (a rotação em torno do eixo de uma barra só com J ≈ 0) trava
    diag = Kff.diagonal()
    zero = diag <= 1e-9 * (diag.max() or 1.0)
    if zero.any():
        Kff = Kff + sp.diags(np.where(zero, diag.max() * 1e-9, 0.0)).tocsc()
    F = np.stack([casos[c] for c in casos], axis=1)
    lu = spl.splu(Kff)
    U = np.zeros((ndof, F.shape[1]))
    U[livre] = lu.solve(F[livre])
    Rtot = K @ U - F                                       # nos graus presos: as reações

    # --- conferência do equilíbrio
    resumo_casos = {}
    for j, c in enumerate(casos):
        aplicado = float(F[:, j][2::6].sum())
        reagido = float(Rtot[:, j][[n * 6 + 2 for n in pes]].sum())
        resumo_casos[c] = {"carga_kN": round(-aplicado, 1), "reacoes_kN": round(reagido, 1),
                           "erro": round(abs(aplicado + reagido) / max(abs(aplicado), 1e-9), 6),
                           "flecha_max_mm": round(float(np.abs(U[:, j][2::6]).max()) * 1000, 1)}

    # --- as reações por pilar (os pés a menos de 60 cm são o mesmo pilar: as duas Ue da perna)
    grupos: List[List[int]] = []
    for n in pes:
        for g_ in grupos:
            if any(math.dist(nos[n][:2], nos[m][:2]) < 0.6 for m in g_):
                g_.append(n)
                break
        else:
            grupos.append([n])
    nome_do_no = {}
    for e in usadas:
        br = barras[e]
        if br["papel"] == "pilar":
            ent = doc.entidades.get(br["ids"][0]) if hasattr(doc.entidades, "get") else None
            nome = (((getattr(ent, "atributos", None) or {}).get("origem") or {}).get("locacao")) if ent else None
            for k in ("a", "b"):
                nome_do_no.setdefault(br[k], nome)
    pilares = []
    for g_ in grupos:
        xy = np.mean([nos[n][:2] for n in g_], axis=0)
        r = {c: [float(sum(Rtot[n * 6 + m, j] for n in g_)) for m in range(6)] for j, c in enumerate(casos)}
        pilares.append({"x": round(float(xy[0]) * 1000), "y": round(float(xy[1]) * 1000), "nos": g_,
                        "nome": next((nome_do_no.get(n) for n in g_ if nome_do_no.get(n)), None),
                        "engastado": any(n in engaste for n in g_),
                        "reacoes_kN": {c: [round(v, 2) for v in r[c]] for c in r}})
    # a carga da locação de cada pilar: a mais perto, uma para cada
    pares = sorted((math.dist((c["x"] / 1000.0, c["y"] / 1000.0), (p["x"] / 1000.0, p["y"] / 1000.0)), i, k)
                   for i, c in enumerate(loc_itens) for k, p in enumerate(pilares))
    tomado_c, tomado_p = set(), set()
    for dist, i, k in pares:
        if dist > 1.5 or i in tomado_c or k in tomado_p:
            continue
        tomado_c.add(i)
        tomado_p.add(k)
        pilares[k]["locacao"] = dict(loc_itens[i], distancia_m=round(dist, 2))
    sem_pilar = [c for i, c in enumerate(loc_itens) if i not in tomado_c]

    # --- esforços nas barras (N, Vy, Vz, T, My, Mz nas duas pontas, eixos locais), por caso
    Ue = U[gl]                                             # (n, 12, casos)
    fl = np.einsum("nij,njk,nkc->nic", kl, T, Ue)
    esforcos = {}
    for i, e in enumerate(usadas):
        esforcos[e] = {c: [round(float(v), 3) for v in fl[i, :, j]] for j, c in enumerate(casos)}

    return {
        "casos": resumo_casos,
        "pilares": pilares,
        "cargas_sem_pilar": sem_pilar,
        "esforcos": esforcos,
        "esqueleto": esq,
        "resumo": {"nos": int(usados_nos.sum()), "barras": len(usadas), "apoios": len(pes),
                   "engastados": len(engaste), "pilares": len(pilares), "area_cobertura_m2": round(area, 1),
                   "peso_aco_kg": round(float(peso.sum() / G), 0), "graus_de_liberdade": int(len(livre))},
        "cargas": car,
        "avisos": avisos,
        "_U": U, "_casos": list(casos),
    }
