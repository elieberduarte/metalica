"""Análise global da estrutura pré-moldada (09/10/2026, o BRAMAIS: "simule as cargas na estrutura inteira... quero ver
como elas se comportam junto com o restante da estrutura").

O IFC do pré-moldado (Tekla) chega como sólidos: pilares, vigas, lajes alveolares, painéis, consolos, neoprenes. O motor
da análise (nucleo3d/analise_estrutural.py) é o mesmo — o resolvedor, a 2ª ordem, os resultados e a tela —; aqui se monta
o pórtico de concreto e as cargas do prédio:

* **Barras** — os pilares e as vigas de concreto, com a seção tirada da face de topo do sólido (a área e as inércias da
  forma real: retângulo, I, T, com aba) e o módulo do concreto pelo fck do material (NBR 6118, 8.2.8), com a rigidez
  reduzida da não linearidade física aproximada (15.7.3: 0,8 nos pilares, 0,4 nas vigas). As colunas de aço com o perfil
  do catálogo.
* **Ligações** — a viga apoiada no consolo (neoprene) rotulada nas duas pontas; o pilar engastado no bloco (cálice); a
  coluna de aço apoiando a viga por baixo, rotulada no topo, com a base pelo parâmetro.
* **Cargas** — peso próprio pelo volume de cada peça (25 kN/m³); as lajes alveolares (peso, revestimento e sobrecarga de
  piso) nas vigas que as apoiam; a cobertura (permanentes e sobrecarga) nas vigas pórtico pela faixa de influência de
  cada uma; o vento do prédio fechado (NBR 6123:2023, Tabelas 6 e 7) nas quatro direções e nos dois C_pi — as fachadas
  pelos pilares e colunas da borda (largura de influência) e o telhado pelas vigas pórtico.
* **Combinações** — NBR 8681: γ = 1,3 no peso próprio do pré-moldado, 1,4 nas outras permanentes e nas variáveis.

Unidades: m, kN, kN·m (como o motor).
"""
from __future__ import annotations

import collections
import math
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

from nucleo3d import analise_estrutural as AE

GAMA_CONCRETO = 25.0                       # kN/m³
#: a rigidez de cálculo da análise global (NBR 6118, 15.7.3 — não linearidade física aproximada): (EI)sec = fator·Eci·Ic
FATOR_PILAR = 0.8
FATOR_VIGA = 0.4
#: um apoio de viga (consolo) acha o pilar até esta distância em planta da face dele (m)
FOLGA_APOIO = 0.80

PARAMETROS = {
    # escolha do motor: auto (pelo modelo) | aco | premoldado
    "modelo_analise": "auto",
    # piso (lajes alveolares)
    "piso_revestimento": 1.0,              # kN/m² — contrapiso e revestimento
    "piso_sobrecarga": 3.0,                # kN/m² — NBR 6120, a confirmar com o uso
    # a base das colunas de aço no pré-moldado (chumbadas no bloco)
    "base_coluna_aco": "rotulada",         # rotulada | engastada
    # vento: a permeabilidade (C_pi, NBR 6123 6.2)
    "aberturas": "duas faces opostas",
}


def e_premoldado(doc) -> bool:
    """o modelo é a estrutura de concreto: mais pilares e vigas de concreto do que barras de aço estruturais"""
    conc = aco = 0
    for e in doc.entidades.values():
        at = getattr(e, "atributos", None) or {}
        t = str(at.get("tipo_ifc") or "")
        if getattr(e, "tipo", "") == "solido" and _concreto(e) and t in ("IfcColumn", "IfcBeam"):
            if str(getattr(e, "nome", "")).upper().startswith(("PILAR", "VIGA")):
                conc += 1
        elif getattr(e, "tipo", "") == "barra" and getattr(e, "papel", "") in ("pilar", "viga", "terça"):
            aco += 1
    return conc >= 10 and conc > aco


def _concreto(e) -> bool:
    m = str(getattr(e, "material", "") or "").upper()
    return "CONCRET" in m or "FCK" in m


def _fck(e) -> float:
    m = re.search(r"FCK\s*(\d+)", str(getattr(e, "material", "") or "").upper())
    return float(m.group(1)) if m else 40.0


def modulo_concreto(fck: float) -> Tuple[float, float]:
    """(Eci, Ecs) em kN/m² — NBR 6118:2023, 8.2.8 (αE = 1, granito/gnaisse), fck ≤ 50 MPa"""
    eci = 5600.0 * math.sqrt(fck) * 1000.0
    ai = min(1.0, 0.8 + 0.2 * fck / 80.0)
    return eci, ai * eci


# ------------------------------------------------------------------ a seção pela face do sólido

def _poligono_props(pts: np.ndarray) -> Optional[dict]:
    """área, centroide e o tensor de inércia (2×2) do polígono (n, 2) — Green / shoelace"""
    x, y = pts[:, 0], pts[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    c = x * y1 - x1 * y
    A = c.sum() / 2.0
    if abs(A) < 1e-8:
        return None
    cx = ((x + x1) * c).sum() / (6 * A)
    cy = ((y + y1) * c).sum() / (6 * A)
    Ixx = ((y * y + y * y1 + y1 * y1) * c).sum() / 12.0        # ∫y² dA (na origem)
    Iyy = ((x * x + x * x1 + x1 * x1) * c).sum() / 12.0
    Ixy = ((x * y1 + 2 * x * y + 2 * x1 * y1 + x1 * y) * c).sum() / 24.0
    s = 1.0 if A > 0 else -1.0
    A, Ixx, Iyy, Ixy = A * s, Ixx * s, Iyy * s, Ixy * s
    Ixx -= A * cy * cy
    Iyy -= A * cx * cx
    Ixy -= A * cx * cy
    return {"A": A, "c": np.array([cx, cy]), "T": np.array([[Iyy, -Ixy], [-Ixy, Ixx]])}     # T: tensor (∫x², ∫xy; ∫y²)


def _secao_do_solido(e, eixo: np.ndarray) -> Optional[dict]:
    """a seção da peça prismática: a face (de topo) perpendicular ao eixo, em m. Devolve A, Iz (forte), Iy (fraca), J, Wz,
    Wy, o centroide (3D, num ponto do eixo) e a direção da altura da seção (ey)"""
    vs = np.array(e.vertices, float) / 1000.0
    melhor = None
    for f in e.faces or []:
        if len(f) < 3:
            continue
        p = vs[f]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        # a normal pela soma dos produtos (robusta em polígono côncavo)
        n = np.zeros(3)
        for i in range(len(p)):
            n += np.cross(p[i], p[(i + 1) % len(p)])
        nn = np.linalg.norm(n)
        if nn < 1e-9:
            continue
        n /= nn
        if abs(n @ eixo) < 0.98:
            continue
        area = nn / 2.0
        if melhor is None or area > melhor[0] + 1e-9:
            melhor = (area, p)
    if melhor is None:
        return None
    p = melhor[1]
    # base no plano da face: u, v perpendiculares ao eixo
    ref = np.array([0.0, 0.0, 1.0]) if abs(eixo[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(eixo, ref); u /= np.linalg.norm(u)
    v = np.cross(eixo, u)
    o = p.mean(axis=0)
    q = np.column_stack([(p - o) @ u, (p - o) @ v])
    pr = _poligono_props(q)
    if pr is None or pr["A"] < 1e-5:
        return None
    lam, vec = np.linalg.eigh(pr["T"])                      # λ crescentes
    # a altura da seção (ey) é a direção de maior ∫(r·e)² dA: o momento em torno de z (perpendicular) é o forte
    e_alto = vec[:, 1]
    ey = e_alto[0] * u + e_alto[1] * v
    Iz, Iy = float(lam[1]), float(lam[0])
    # as distâncias extremas da fibra
    qc = q - pr["c"]
    dy = np.abs(qc @ vec[:, 1]).max()
    dz = np.abs(qc @ vec[:, 0]).max()
    A = float(pr["A"])
    Ip = Iz + Iy
    J = A ** 4 / (4 * math.pi ** 2 * Ip) if Ip > 0 else 0.0     # Saint-Venant, seção maciça compacta
    centro = o + pr["c"][0] * u + pr["c"][1] * v
    return {"A": A, "Iz": Iz, "Iy": Iy, "J": J, "Wz": Iz / max(dy, 1e-6), "Wy": Iy / max(dz, 1e-6), "ey": ey,
            "centro_face": centro, "h": 2 * dy, "b": 2 * dz}


def _volume(e) -> float:
    """m³: o VOLUME do Tekla nas propriedades; sem ele, pela malha (divergência)"""
    pr = ((getattr(e, "atributos", None) or {}).get("propriedades") or {})
    for g in pr.values():
        if isinstance(g, dict) and g.get("VOLUME"):
            try:
                return float(g["VOLUME"])
            except (TypeError, ValueError):
                pass
    vs = np.array(e.vertices, float) / 1000.0
    vol = 0.0
    for f in e.faces or []:
        for i in range(1, len(f) - 1):
            vol += np.dot(vs[f[0]], np.cross(vs[f[i]], vs[f[i + 1]])) / 6.0
    return abs(vol)


# ------------------------------------------------------------------ as peças

def _pecas(doc) -> Tuple[List[dict], List[dict], List[dict], List[str]]:
    """(membros, lajes, paredes, avisos): os membros do pórtico (pilar, viga, coluna de aço) com eixo e seção; as lajes e
    as paredes (painéis) como carga"""
    membros, lajes, paredes, avisos = [], [], [], []
    ignoradas = collections.Counter()
    cache_aco: dict = {}
    for e in doc.entidades.values():
        at = getattr(e, "atributos", None) or {}
        t = str(at.get("tipo_ifc") or "")
        nome = str(getattr(e, "nome", "") or "")
        NOME = nome.upper()
        if getattr(e, "tipo", "") == "barra":
            if getattr(e, "papel", "") not in ("pilar", "viga", "terça", "contraventamento"):
                ignoradas[nome or "barra"] += 1
                continue
            sec = AE._secao(getattr(e, "perfil", "") or "", False, cache_aco)
            if sec is None:
                ignoradas[(getattr(e, "perfil", "") or nome) + " (perfil fora do catálogo)"] += 1
                continue
            a = np.array(e.inicio, float) / 1000.0
            b = np.array(e.fim, float) / 1000.0
            if a[2] > b[2]:
                a, b = b, a
            membros.append({"id": e.id, "tipo": "coluna_aco" if getattr(e, "papel", "") == "pilar" else "viga_aco",
                            "nome": nome, "perfil": getattr(e, "perfil", ""), "a": a, "b": b, "sec": dict(sec),
                            "R": AE._eixos(a, b, float(getattr(e, "rotacao", 0.0) or 0.0)),
                            "aco": getattr(e, "aco", "") or "", "peso_kN_m": sec["kg_m"] * AE.G_GRAV})
            continue
        if getattr(e, "tipo", "") != "solido" or not getattr(e, "vertices", None):
            continue
        if t == "IfcWallStandardCase" or NOME.startswith("PAINEL"):
            vs = np.array(e.vertices, float) / 1000.0
            paredes.append({"id": e.id, "min": vs.min(0), "max": vs.max(0), "kN": _volume(e) * GAMA_CONCRETO})
            continue
        if "LAJE" in NOME or NOME.startswith(("ENCHIMENTO", "ESCADA")):
            vs = np.array(e.vertices, float) / 1000.0
            lajes.append({"id": e.id, "nome": nome, "min": vs.min(0), "max": vs.max(0), "kN": _volume(e) * GAMA_CONCRETO,
                          "alveolar": "ALVEOLAR" in NOME})
            continue
        if not _concreto(e) or t not in ("IfcColumn", "IfcBeam") or not NOME.startswith(("PILAR", "VIGA", "COLUNA")):
            ignoradas[nome or t] += 1
            continue
        vs = np.array(e.vertices, float) / 1000.0
        if t == "IfcColumn":
            eixo = np.array([0.0, 0.0, 1.0])
            # o eixo pela face de baixo (o pilar tem consolos: a caixa toda tira o centro do lugar)
            sec = _secao_do_solido(e, eixo)
            if sec is None:
                ignoradas[nome + " (sem a face da seção)"] += 1
                continue
            cx, cy = sec["centro_face"][0], sec["centro_face"][1]
            a = np.array([cx, cy, vs[:, 2].min()])
            b = np.array([cx, cy, vs[:, 2].max()])
            tipo = "pilar"
        else:
            c = vs.mean(0)
            _w, vec = np.linalg.eigh(np.cov((vs - c).T))
            eixo = vec[:, -1] / np.linalg.norm(vec[:, -1])
            if eixo[0] + 1e-6 * eixo[1] < 0:
                eixo = -eixo
            sec = _secao_do_solido(e, eixo)
            if sec is None:
                ignoradas[nome + " (sem a face da seção)"] += 1
                continue
            ts = (vs - sec["centro_face"]) @ eixo
            a = sec["centro_face"] + eixo * ts.min()
            b = sec["centro_face"] + eixo * ts.max()
            tipo = "viga"
        fck = _fck(e)
        eci, ecs = modulo_concreto(fck)
        fator = FATOR_PILAR if tipo == "pilar" else FATOR_VIGA
        L = float(np.linalg.norm(b - a))
        vol = _volume(e)
        ex = (b - a) / max(L, 1e-9)
        ey = sec["ey"] - (sec["ey"] @ ex) * ex
        ey /= np.linalg.norm(ey)
        R = np.stack([ex, ey, np.cross(ex, ey)])
        s = {k: sec[k] for k in ("A", "Iz", "Iy", "J", "Wz", "Wy")}
        s.update({"E": fator * eci, "G": fator * eci / 2.4, "kg_m": vol * GAMA_CONCRETO / max(L, 1e-9) / AE.G_GRAV,
                  "concreto": True, "tipo": "concreto", "fck": fck})
        membros.append({"id": e.id, "tipo": tipo, "nome": nome, "perfil": "%s %.0f×%.0f (fck %g)" % (nome.title(), sec["b"] * 100, sec["h"] * 100, fck),
                        "a": a, "b": b, "sec": s, "R": R, "aco": "", "peso_kN_m": vol * GAMA_CONCRETO / max(L, 1e-9),
                        "caixa": (vs.min(0), vs.max(0))})
    for nome, n in ignoradas.most_common(12):
        avisos.append("%d peça(s) \"%s\" fora do pórtico (consolos, neoprenes, insertos)" % (n, nome))
    return membros, lajes, paredes, avisos


# ------------------------------------------------------------------ nós e ligações

class _Nos:
    def __init__(self, tol=0.02):
        self.p: List[np.ndarray] = []
        self.tol = tol

    def no(self, x) -> int:
        x = np.asarray(x, float)
        for i, q in enumerate(self.p):
            if np.linalg.norm(q - x) <= self.tol:
                return i
        self.p.append(x.copy())
        return len(self.p) - 1


def _dist_ponto_segmento_planta(p, a, b) -> Tuple[float, float]:
    """(distância em planta, t ∈ [0, 1]) do ponto ao segmento a–b"""
    ab = (b - a)[:2]
    L2 = float(ab @ ab)
    t = 0.0 if L2 < 1e-12 else float(np.clip(((p - a)[:2] @ ab) / L2, 0.0, 1.0))
    q = a[:2] + t * ab
    return float(np.linalg.norm(p[:2] - q)), t


def _no_do_ponto(pt, no_de, membros, NS):
    """o nó de (membro, t); com membro None, t é o nó do pilar (o índice do membro pilar e o t dele vêm em pt[2])"""
    im, t = pt
    k = (im, round(t, 4))
    if k in no_de:
        return no_de[k]
    m = membros[im]
    return NS.no(m["a"] + t * (m["b"] - m["a"]))


def _travamento_do_oitao(membros, topo_coluna, P) -> List[dict]:
    """O contraventamento da cobertura no vão da ponta, onde há colunas de oitão apoiando as vigas pórtico da fachada: em
    cada posição de coluna e nas pontas das vigas, um ponto na viga do oitão e outro na viga pórtico paralela mais perto
    (a do pórtico vizinho); escora entre os pares e X em cada painel. Devolve [{tipo, p: (membro, t), q: (membro, t)}]."""
    if not topo_coluna:
        return []
    vp = [i for i, m in enumerate(membros) if m["tipo"] == "viga" and "PORTICO" in m["nome"].upper()]
    oitao = sorted({iw for iw, _t in topo_coluna.values()})
    out = []
    for iw in oitao:
        w = membros[iw]
        d = (w["b"] - w["a"])[:2]
        Lw = float(np.linalg.norm(d))
        d = d / Lw
        n = np.array([-d[1], d[0]])
        # a viga vizinha: paralela, sobreposta, a mais perto
        viz = None
        for j in vp:
            if j == iw:
                continue
            v = membros[j]
            d2 = (v["b"] - v["a"])[:2]
            d2 = d2 / np.linalg.norm(d2)
            if abs(d2 @ d) < 0.95:
                continue
            s0, s1 = sorted((w["a"][:2] @ d, w["b"][:2] @ d))
            t0, t1 = sorted((v["a"][:2] @ d, v["b"][:2] @ d))
            if min(s1, t1) - max(s0, t0) < 0.5 * (s1 - s0):
                continue
            dist = abs(float((v["a"][:2] - w["a"][:2]) @ n))
            if dist < 0.3:
                continue
            if viz is None or dist < viz[0]:
                viz = (dist, j)
        if viz is None:
            continue
        v = membros[viz[1]]
        # os pontos na viga do oitão: as pontas (perto) e as colunas
        ts = sorted({0.02, 0.98} | {t for (iw2, t) in topo_coluna.values() if iw2 == iw})
        pares = []
        for t in ts:
            pw = w["a"] + t * (w["b"] - w["a"])
            # o mesmo ponto na vizinha (a projeção em planta)
            dv = v["b"] - v["a"]
            tv = float(np.clip(((pw - v["a"])[:2] @ dv[:2]) / float(dv[:2] @ dv[:2]), 0.02, 0.98))
            pares.append(((iw, round(t, 4)), (viz[1], round(tv, 4))))
        for k, (p, q) in enumerate(pares):
            if 0 < k < len(pares) - 1:
                out.append({"tipo": "escora", "p": p, "q": q})
            if k + 1 < len(pares):
                p2, q2 = pares[k + 1]
                out.append({"tipo": "diagonal", "p": p, "q": q2})
                out.append({"tipo": "diagonal", "p": p2, "q": q})
    return out


def montar(doc, par: Optional[dict] = None) -> dict:
    P = dict(AE.PARAMETROS_PADRAO, **(par or {}))
    membros, lajes, paredes, avisos = _pecas(doc)
    pilares = [m for m in membros if m["tipo"] in ("pilar", "coluna_aco")]
    vigas = [m for m in membros if m["tipo"] in ("viga", "viga_aco")]
    # os pontos de cada membro (parâmetro t ao longo dele) e o nó de cada um
    pontos: Dict[int, Dict[float, np.ndarray]] = {i: {} for i in range(len(membros))}
    idx = {id(m): i for i, m in enumerate(membros)}
    sem_apoio = []
    apoio_de_viga: Dict[Tuple[int, str], Tuple[int, float]] = {}       # (viga, ponta) → (membro que apoia, t nele)
    for v in vigas:
        iv = idx[id(v)]
        for ponta, pt in (("a", v["a"]), ("b", v["b"])):
            achado = None
            # 1) o pilar: a ponta em cima do consolo (a caixa do pilar com folga, na altura dele)
            melhor = None
            for pl in pilares:
                if pl["tipo"] != "pilar":
                    continue
                cmin, cmax = pl["caixa"]
                dx = max(cmin[0] - pt[0], 0.0, pt[0] - cmax[0])
                dy = max(cmin[1] - pt[1], 0.0, pt[1] - cmax[1])
                d = math.hypot(dx, dy)
                if d <= FOLGA_APOIO and cmin[2] - 0.3 <= pt[2] <= cmax[2] + 1.2:
                    dc = math.hypot(pt[0] - pl["a"][0], pt[1] - pl["a"][1])
                    if melhor is None or dc < melhor[0]:
                        melhor = (dc, pl)
            if melhor:
                pl = melhor[1]
                z = min(max(pt[2], pl["a"][2]), pl["b"][2])
                t = (z - pl["a"][2]) / max(pl["b"][2] - pl["a"][2], 1e-9)
                achado = (idx[id(pl)], t)
            if achado is None:
                # 2) outra viga por baixo (a ponta apoiada no meio de outra)
                for w in vigas:
                    if w is v:
                        continue
                    d, t = _dist_ponto_segmento_planta(pt, w["a"], w["b"])
                    zw = w["a"][2] + t * (w["b"][2] - w["a"][2])
                    if d <= 0.6 and -0.2 <= pt[2] - zw <= 1.2 and 0.02 < t < 0.98:
                        achado = (idx[id(w)], t)
                        break
            if achado is None:
                sem_apoio.append(v["nome"])
                continue
            apoio_de_viga[(iv, ponta)] = achado
    # as colunas de aço sob as vigas (o topo encostado no fundo da viga): o ponto na viga
    topo_coluna: Dict[int, Tuple[int, float]] = {}
    for pl in pilares:
        if pl["tipo"] != "coluna_aco":
            continue
        top = pl["b"]
        for w in vigas:
            d, t = _dist_ponto_segmento_planta(top, w["a"], w["b"])
            zw = w["a"][2] + t * (w["b"][2] - w["a"][2])
            if d <= 0.5 and -0.2 <= zw - top[2] <= 1.5:
                topo_coluna[idx[id(pl)]] = (idx[id(w)], t)
                break
    # o travamento da cobertura no vão da ponta (hipótese): o topo das colunas do oitão escorado na viga pórtico vizinha
    trav = _travamento_do_oitao(membros, topo_coluna, P) if P.get("travamento_hipotese", "auto") != "nao" else []
    # os pontos de cada membro: as pontas e onde algo se apoia nele
    for i, m in enumerate(membros):
        pontos[i][0.0] = m["a"]
        pontos[i][1.0] = m["b"]
    for (iv, ponta), (im, t) in apoio_de_viga.items():
        m = membros[im]
        pontos[im][round(t, 4)] = m["a"] + t * (m["b"] - m["a"])
    for ic, (iw, t) in topo_coluna.items():
        w = membros[iw]
        pontos[iw][round(t, 4)] = w["a"] + t * (w["b"] - w["a"])
    for tr in trav:
        for (iw, t) in (tr["p"], tr["q"]):
            if iw is not None:
                w = membros[iw]
                pontos[iw][round(t, 4)] = w["a"] + t * (w["b"] - w["a"])
    # os nós
    NS = _Nos()
    no_de: Dict[Tuple[int, float], int] = {}
    for i, ps in pontos.items():
        if membros[i]["tipo"] in ("pilar", "coluna_aco"):
            for t, x in ps.items():
                no_de[(i, t)] = NS.no(x)
    # a ponta da viga vai ao nó do apoio; o resto dos pontos dela ganha nó próprio
    for (iv, ponta), (im, t) in apoio_de_viga.items():
        alvo = (im, round(t, 4))
        if alvo not in no_de:
            m = membros[im]
            no_de[alvo] = NS.no(m["a"] + t * (m["b"] - m["a"]))
        no_de[(iv, 0.0 if ponta == "a" else 1.0)] = no_de[alvo]
    for i, ps in pontos.items():
        if membros[i]["tipo"] in ("viga", "viga_aco"):
            for t, x in ps.items():
                if (i, t) not in no_de:
                    no_de[(i, t)] = NS.no(x)
    # o topo da coluna de aço vai ao nó da viga
    for ic, (iw, t) in topo_coluna.items():
        no_de[(ic, 1.0)] = no_de[(iw, round(t, 4))]
    # as barras
    barras: List[dict] = []
    for i, m in enumerate(membros):
        ts = sorted(pontos[i])
        if m["tipo"] in ("viga", "viga_aco") and not ((i, "a") in apoio_de_viga or (i, "b") in apoio_de_viga):
            pass
        for k in range(len(ts) - 1):
            na, nb = no_de[(i, ts[k])], no_de[(i, ts[k + 1])]
            if na == nb:
                continue
            pa, pb = NS.p[na], NS.p[nb]
            L = float(np.linalg.norm(pb - pa))
            if L < 1e-3:
                continue
            ex = (pb - pa) / L
            ey = m["R"][1] - (m["R"][1] @ ex) * ex
            if np.linalg.norm(ey) < 1e-6:
                ey = np.cross(ex, [0.0, 0.0, 1.0]) if abs(ex[2]) < 0.9 else np.cross(ex, [1.0, 0.0, 0.0])
            ey /= np.linalg.norm(ey)
            papel = "pilar" if m["tipo"] in ("pilar", "coluna_aco") else "viga"
            soltos = []
            if papel == "viga" and m["tipo"] == "viga":
                if k == 0 and (i, "a") in apoio_de_viga:
                    soltos += [4, 5]                     # a viga no consolo (neoprene): rotulada
                if k == len(ts) - 2 and (i, "b") in apoio_de_viga:
                    soltos += [10, 11]
            if m["tipo"] == "coluna_aco" and k == len(ts) - 2 and i in topo_coluna:
                soltos += [10, 11]                       # o topo da coluna encostado na viga
            barras.append({"a": na, "b": nb, "L": L, "papel": papel, "papel_trelica": None, "elemento": m["tipo"],
                           "grupo": m["tipo"], "marca": m["nome"], "perfil": m["perfil"], "ids": [m["id"]], "aco": m["aco"],
                           "sec": m["sec"], "duplo": False, "rot": 0.0, "R": np.stack([ex, ey, np.cross(ex, ey)]),
                           "soltos": soltos, "membro": i, "t0": ts[k], "t1": ts[k + 1]})
    # as barras do travamento (hipótese): escoras e o X de cada painel do vão da ponta
    cache_h: dict = {}
    n_trav = 0
    for tr in trav:
        na = _no_do_ponto(tr["p"], no_de, membros, NS)
        nb = _no_do_ponto(tr["q"], no_de, membros, NS)
        if na is None or nb is None or na == nb:
            continue
        pa, pb = NS.p[na], NS.p[nb]
        L = float(np.linalg.norm(pb - pa))
        perfil = P.get("perfil_terca_hipotese") if tr["tipo"] == "escora" else P.get("perfil_contravento_hipotese")
        sec = AE._secao(perfil or "", False, cache_h)
        if sec is None or L < 1e-3:
            continue
        R = AE._eixos(pa, pb, 0.0)
        barras.append({"a": na, "b": nb, "L": L, "papel": "terça" if tr["tipo"] == "escora" else "contraventamento",
                       "papel_trelica": None, "elemento": "travamento", "grupo": "travamento", "marca": "hipótese",
                       "perfil": perfil, "ids": [], "aco": "", "sec": dict(sec), "duplo": False, "rot": 0.0, "R": R,
                       "soltos": [4, 5, 10, 11], "membro": -1, "t0": 0.0, "t1": 1.0, "hipotese": True})
        n_trav += 1
    nos = np.array(NS.p, float)
    if n_trav:
        avisos.append(("travamento da cobertura no vão da ponta (HIPÓTESE, o modelo não tem): %d barras — escoras %s do topo das "
                       "colunas do oitão até a viga pórtico vizinha e X de %s em cada painel; sem ele, o topo das colunas só "
                       "fica preso pela viga pórtico de lado e anda mais de 1 m com o vento") % (
                       n_trav, P.get("perfil_terca_hipotese"), P.get("perfil_contravento_hipotese")))
    # apoios: o pé dos pilares e das colunas
    apoios = []
    for i, m in enumerate(membros):
        if m["tipo"] not in ("pilar", "coluna_aco"):
            continue
        n = no_de[(i, 0.0)]
        tipo = "engastada" if m["tipo"] == "pilar" else (P.get("base_coluna_aco") or "rotulada")
        chave = "%d,%d" % (round(nos[n][0] * 1000), round(nos[n][1] * 1000))
        tipo = (P.get("bases") or {}).get(chave) or tipo
        apoios.append({"no": int(n), "tipo": tipo, "chave": chave})
    if sem_apoio:
        c = collections.Counter(sem_apoio)
        avisos.append("%d viga(s) sem apoio achado (ficaram soltas na ponta): %s" % (
            len(sem_apoio), ", ".join("%s ×%d" % kv for kv in c.most_common(6))))
    n_conc = sum(1 for m in membros if m["sec"].get("concreto"))
    resumo = {"pilares": sum(1 for m in membros if m["tipo"] == "pilar"), "vigas": sum(1 for m in membros if m["tipo"] == "viga"),
              "colunas_aco": sum(1 for m in membros if m["tipo"] == "coluna_aco"), "lajes": len(lajes), "paredes": len(paredes),
              "barras": len(barras), "nos": len(nos), "membros_concreto": n_conc}
    avisos.insert(0, ("Análise global do pré-moldado: %(pilares)d pilares e %(vigas)d vigas de concreto, %(colunas_aco)d colunas de "
                      "aço; %(lajes)d lajes e %(paredes)d painéis como carga. Vigas rotuladas nos consolos, pilares engastados "
                      "no bloco; rigidez de cálculo 0,8·Eci·Ic nos pilares e 0,4·Eci·Ic nas vigas (NBR 6118, 15.7.3).") % resumo)
    return {"nos": nos, "barras": barras, "apoios": apoios, "avisos": avisos, "par": P, "resumo_esqueleto": resumo,
            "movel": None, "membros": membros, "lajes": lajes, "paredes": paredes}


# ------------------------------------------------------------------ cargas

def _barras_do_membro(M: dict) -> Dict[int, List[int]]:
    out: Dict[int, List[int]] = collections.defaultdict(list)
    for j, br in enumerate(M["barras"]):
        out[br["membro"]].append(j)
    return out


def _vigas_portico(M: dict) -> List[int]:
    return [i for i, m in enumerate(M["membros"]) if m["tipo"] == "viga" and "PORTICO" in m["nome"].upper()]


def _larguras_cobertura(M: dict, vp: List[int]) -> Dict[int, float]:
    """a faixa de influência de cada viga pórtico: metade da distância às vizinhas paralelas que se sobrepõem a ela, de
    cada lado; na borda, só o lado de dentro"""
    mem = M["membros"]
    out = {}
    for i in vp:
        a, b = mem[i]["a"], mem[i]["b"]
        d = (b - a)[:2]
        d = d / np.linalg.norm(d)
        n = np.array([-d[1], d[0]])
        s0, s1 = sorted((a[:2] @ d, b[:2] @ d))
        lados = {1: None, -1: None}
        for j in vp:
            if j == i:
                continue
            a2, b2 = mem[j]["a"], mem[j]["b"]
            d2 = (b2 - a2)[:2]
            d2 = d2 / np.linalg.norm(d2)
            if abs(d2 @ d) < 0.95:
                continue
            t0, t1 = sorted((a2[:2] @ d, b2[:2] @ d))
            if min(s1, t1) - max(s0, t0) < 0.5:
                continue
            dist = float((a2[:2] - a[:2]) @ n)
            if abs(dist) < 0.3:
                continue
            lado = 1 if dist > 0 else -1
            if lados[lado] is None or abs(dist) < abs(lados[lado]):
                lados[lado] = dist
        w = sum(abs(v) / 2.0 for v in lados.values() if v is not None)
        out[i] = w
    return out


def cargas(M: dict):
    from nucleo import cargas as C
    P, nos, barras, mem = M["par"], M["nos"], M["barras"], M["membros"]
    avisos: List[str] = []
    info: dict = {}
    porm = _barras_do_membro(M)
    casos: Dict[str, dict] = {}
    # ---- peso próprio das peças do pórtico + as lajes (peso) nas vigas que as apoiam
    # a barra de hipótese (o travamento da cobertura, sem peça no modelo) pelo perfil dela
    pp = {j: np.array([0.0, 0.0, -(mem[br["membro"]]["peso_kN_m"] if br["membro"] >= 0 else br["sec"]["kg_m"] * AE.G_GRAV)])
          for j, br in enumerate(barras)}
    cp: Dict[int, np.ndarray] = {}
    scp: Dict[int, np.ndarray] = {}

    def somar(d, j, v):
        d[j] = d.get(j, np.zeros(3)) + v

    # lajes: o vão na maior dimensão em planta; cada ponta na viga que está embaixo dela
    vigas_i = [i for i, m in enumerate(mem) if m["tipo"] == "viga"]
    sem_apoio_laje = 0
    peso_lajes = 0.0
    for lj in M["lajes"]:
        lo, hi = lj["min"], lj["max"]
        dx, dy = hi[0] - lo[0], hi[1] - lo[1]
        area = dx * dy
        pontas = ([np.array([lo[0] + 0.15, (lo[1] + hi[1]) / 2, lo[2]]), np.array([hi[0] - 0.15, (lo[1] + hi[1]) / 2, lo[2]])]
                  if dx >= dy else
                  [np.array([(lo[0] + hi[0]) / 2, lo[1] + 0.15, lo[2]]), np.array([(lo[0] + hi[0]) / 2, hi[1] - 0.15, lo[2]])])
        g_laje = lj["kN"] + (float(P.get("piso_revestimento") or 0.0) * area if lj["alveolar"] else 0.0)
        q_laje = float(P.get("piso_sobrecarga") or 0.0) * area if lj["alveolar"] else 0.0
        peso_lajes += lj["kN"]
        achou = []
        for pt in pontas:
            best = None
            for i in vigas_i:
                d, t = _dist_ponto_segmento_planta(pt, mem[i]["a"], mem[i]["b"])
                cmin, cmax = mem[i]["caixa"]
                ztop = cmax[2]
                if d <= 0.9 and -0.5 <= pt[2] - ztop <= 0.6:
                    if best is None or d < best[0]:
                        best = (d, i, t)
            achou.append(best)
        ok = [x for x in achou if x is not None]
        if not ok:
            sem_apoio_laje += 1
            continue
        for d, i, t in ok:
            # a parcela da laje vai à barra (trecho) da viga onde a ponta dela cai, distribuída no trecho
            js = porm[i]
            j = next((j for j in js if barras[j]["t0"] - 1e-6 <= t <= barras[j]["t1"] + 1e-6), js[0])
            L = barras[j]["L"]
            somar(cp, j, np.array([0.0, 0.0, -g_laje / len(ok) / L]))
            if q_laje:
                somar(scp, j, np.array([0.0, 0.0, -q_laje / len(ok) / L]))
    if sem_apoio_laje:
        avisos.append("%d laje(s) sem viga achada embaixo: o peso delas ficou fora" % sem_apoio_laje)
    # ---- cobertura nas vigas pórtico (permanentes e sobrecarga), pela faixa de influência
    vp = _vigas_portico(M)
    larg = _larguras_cobertura(M, vp)
    g_cob = float(P.get("telha") or 0.0) + float(P.get("carga_extra") or 0.0)
    q_cob = float(P.get("sobrecarga") or 0.0)
    scc: Dict[int, np.ndarray] = {}
    area_cob = 0.0
    for i in vp:
        w = larg.get(i, 0.0)
        for j in porm[i]:
            ex = barras[j]["R"][0]
            Lh = math.hypot(ex[0], ex[1])                    # a projeção horizontal por m de barra
            somar(cp, j, np.array([0.0, 0.0, -g_cob * w]))
            scc[j] = np.array([0.0, 0.0, -q_cob * w * Lh])
            area_cob += w * barras[j]["L"] * Lh
    casos["PP"] = {"dist": pp, "nodal": {}, "descricao": "peso próprio das peças de concreto e de aço (25 kN/m³; pelo perfil)"}
    casos["CP"] = {"dist": cp, "nodal": {}, "descricao": ("lajes (peso + revestimento %.2f kN/m²) nas vigas e cobertura "
                                                         "(%.2f kN/m²) nas vigas pórtico") % (float(P.get("piso_revestimento") or 0), g_cob)}
    if scp:
        casos["SCP"] = {"dist": scp, "nodal": {}, "descricao": "sobrecarga de piso (%.2f kN/m²)" % float(P.get("piso_sobrecarga") or 0)}
    if scc:
        casos["SC"] = {"dist": scc, "nodal": {}, "descricao": "sobrecarga de cobertura (%.2f kN/m², projeção horizontal)" % q_cob}
    info["cobertura"] = {"area_m2": round(area_cob, 1), "vigas_portico": len(vp),
                         "larguras_m": sorted({round(v, 3) for v in larg.values()})}
    info["lajes"] = {"n": len(M["lajes"]), "peso_kN": round(peso_lajes, 1)}
    # ---- vento
    if P.get("vento", True):
        vc, vi = _vento(M, porm, vp, larg, avisos)
        casos.update(vc)
        info["vento"] = vi
    return casos, info, avisos


def _vento(M, porm, vp, larg, avisos):
    """o prédio fechado: as quatro direções (±x, ±y) e os dois C_pi. Fachada: os pilares e colunas da borda de cada
    fila, com a largura de influência ao longo da fachada, na altura toda; telhado: as vigas pórtico pela zona."""
    from nucleo import cargas as C
    P, nos, barras, mem = M["par"], M["nos"], M["barras"], M["membros"]
    verticais = [i for i, m in enumerate(mem) if m["tipo"] in ("pilar", "coluna_aco")]
    if not verticais:
        return {}, {}
    xy = np.array([[mem[i]["a"][0], mem[i]["a"][1]] for i in verticais])
    x0, x1 = xy[:, 0].min(), xy[:, 0].max()
    y0, y1 = xy[:, 1].min(), xy[:, 1].max()
    zt = max(float(mem[i]["b"][2]) for i in verticais)
    a_dim, b_dim = max(x1 - x0, y1 - y0), min(x1 - x0, y1 - y0)
    longo_em_x = (x1 - x0) >= (y1 - y0)
    # a altura do beiral: a mediana do topo dos pilares de concreto da fachada longa
    h = float(np.median([mem[i]["b"][2] for i in verticais]))
    vg = [mem[i] for i in vp]
    if vg:
        dz = [abs(m["b"][2] - m["a"][2]) / max(math.hypot(*(m["b"] - m["a"])[:2]), 1e-6) for m in vg]
        teta = math.degrees(math.atan(float(np.median(dz))))
    else:
        teta = 0.0
    V0, S1, S3 = float(P.get("v0") or 42.0), float(P.get("s1") or 1.0), float(P.get("s3") or 1.0)
    cat = P.get("categoria") or "II"
    classe = P.get("classe") or C.classe_por_dimensao(a_dim)
    S2 = C.fator_s2(cat, classe, zt)
    Vk = C.velocidade_caracteristica(V0, S1, S2, S3)
    q = C.pressao_dinamica(Vk)
    coefs = {(c.direcao, c.letra): c.Ce for c in C.coeficientes_pressao_galpao(b_dim, a_dim, h, teta).coeficientes if not c.local}
    cpis = [c.valor for c in C.coeficiente_pressao_interna(P.get("aberturas") or "duas faces opostas")]
    # a cumeeira: a coordenada no meio da largura (o galpão de duas águas)
    if longo_em_x:
        cume = (y0 + y1) / 2.0
    else:
        cume = (x0 + x1) / 2.0
    casos = {}
    # filas: as verticais agrupadas pela coordenada transversal ao vento
    def filas(eixo):
        """{coord: [verticais]}, a coordenada eixo (0 = x, 1 = y) arredondada"""
        f = collections.defaultdict(list)
        for k, i in enumerate(verticais):
            f[round(float(xy[k, eixo]) / 0.5) * 0.5].append(i)
        return f

    def larguras(coords):
        cs = sorted(coords)
        out = {}
        for k, c in enumerate(cs):
            esq = (c - cs[k - 1]) / 2.0 if k > 0 else 0.0
            dir_ = (cs[k + 1] - c) / 2.0 if k + 1 < len(cs) else 0.0
            out[c] = esq + dir_
        return out

    dirs = [("+X", np.array([1.0, 0.0])), ("-X", np.array([-1.0, 0.0])), ("+Y", np.array([0.0, 1.0])), ("-Y", np.array([0.0, -1.0]))]
    for nome_d, dv in dirs:
        ao_longo = 0 if abs(dv[0]) > 0 else 1                   # o eixo do vento
        transv = 1 - ao_longo
        longitudinal = (ao_longo == 0) == longo_em_x            # vento paralelo à cumeeira: entra pelo oitão
        dirn = "longitudinal" if longitudinal else "transversal"
        barl = coefs[(dirn, "C" if longitudinal else "A")]
        sota = coefs[(dirn, "D" if longitudinal else "B")]
        lat1 = coefs[(dirn, "A1/B1" if longitudinal else "C1/D1")]
        lat2 = coefs[(dirn, "A2/B2" if longitudinal else "C2/D2")]
        z1 = min(max(b_dim / 3.0, a_dim / 4.0), 2.0 * h) if longitudinal else min(2.0 * h, b_dim / 2.0)
        sinal = float(dv[ao_longo])
        # a coordenada de barlavento (a borda de onde vem o vento)
        lim = (x0, x1) if ao_longo == 0 else (y0, y1)
        borda_barl = lim[0] if sinal > 0 else lim[1]
        for cpi in cpis:
            nome = "V%s %s" % (nome_d, ("Cpi+%.1f" % cpi) if cpi >= 0 else ("Cpi%.1f" % cpi))
            dist: Dict[int, np.ndarray] = {}
            # fachadas a barlavento e sotavento: por fila (a coordenada transversal), a primeira e a última vertical
            fl = filas(transv)
            lw = larguras(fl.keys())
            for c, vs_ in fl.items():
                ordem = sorted(vs_, key=lambda i: mem[i]["a"][ao_longo] * sinal)
                for i, ce in ((ordem[0], barl), (ordem[-1], sota)) if len(ordem) > 1 else ((ordem[0], barl),):
                    pnet = (ce - cpi) * q                          # + empurra para dentro
                    # a força: barlavento empurra no sentido do vento; sotavento, com sucção, também
                    sentido = 1.0 if i == ordem[0] else -1.0
                    wv = np.zeros(3)
                    wv[ao_longo] = sinal * sentido * pnet * lw[c]
                    for j in porm[i]:
                        dist[j] = dist.get(j, np.zeros(3)) + wv
            # fachadas laterais (paralelas ao vento): por fila ao longo do vento, a primeira e a última na transversal
            fl2 = filas(ao_longo)
            lw2 = larguras(fl2.keys())
            for c, vs_ in fl2.items():
                ordem = sorted(vs_, key=lambda i: mem[i]["a"][transv])
                d_barl = abs(c - borda_barl)
                ce = lat1 if d_barl <= z1 else lat2
                pnet = (ce - cpi) * q
                for i, normal_in in ((ordem[0], 1.0), (ordem[-1], -1.0)) if len(ordem) > 1 else ():
                    wv = np.zeros(3)
                    wv[transv] = normal_in * pnet * lw2[c]          # + para dentro
                    for j in porm[i]:
                        dist[j] = dist.get(j, np.zeros(3)) + wv
            # telhado: as vigas pórtico, pela zona do meio de cada trecho
            for i in vp:
                w = larg.get(i, 0.0)
                for j in porm[i]:
                    br = barras[j]
                    pm = (nos[br["a"]] + nos[br["b"]]) / 2.0
                    if longitudinal:
                        d = abs(pm[ao_longo] - borda_barl)
                        zona = "EG" if d <= b_dim / 2.0 else ("FH" if d <= b_dim else "IJ")
                    else:
                        lado_barl = (pm[transv] - cume) * (-sinal) > 0     # a água voltada para o vento
                        zona = "EF" if lado_barl else "GH"
                    ce = coefs[(dirn, zona)]
                    pnet = (ce - cpi) * q                          # + pressão (para baixo)
                    Lh = math.hypot(br["R"][0][0], br["R"][0][1])
                    dist[j] = dist.get(j, np.zeros(3)) + np.array([0.0, 0.0, -pnet * w * Lh])
            casos[nome] = {"dist": dist, "nodal": {}, "descricao": "vento %s (%s), C_pi = %+.1f" % (nome_d, dirn, cpi)}
    vi = {"q_kN_m2": round(q, 3), "Vk": round(Vk, 1), "S2": round(S2, 3), "classe": classe, "categoria": cat,
          "teta": round(teta, 2), "h": round(h, 2), "b": round(b_dim, 2), "a": round(a_dim, 2), "cpi": cpis,
          "coeficientes": {"%s %s" % k: v for k, v in coefs.items()}}
    return casos, vi


# ------------------------------------------------------------------ combinações (NBR 8681)

def combinacoes(casos) -> Dict[str, dict]:
    tem = set(casos)
    ventos = [c for c in casos if c.startswith("V")]
    G = {"PP": 1.3, "CP": 1.4}
    Gf = {"PP": 1.0, "CP": 1.0}
    Q = {k: 1.4 for k in ("SCP", "SC") if k in tem}
    Q05 = {k: 1.4 * 0.5 for k in Q}
    out: Dict[str, dict] = {}
    if Q:
        out["ELU Q"] = {"tipo": "ELU", "fatores": {**G, **Q}, "descricao": "permanentes + sobrecargas (piso e cobertura) principais"}
    for v in ventos:
        out["ELU %s" % v] = {"tipo": "ELU", "fatores": {**G, v: 1.4, **Q05}, "descricao": "permanentes + vento %s principal + sobrecargas" % v}
        out["ELU %s fav" % v] = {"tipo": "ELU", "fatores": {**Gf, v: 1.4}, "descricao": "permanentes favoráveis + vento %s" % v}
    if not out:
        out["ELU G"] = {"tipo": "ELU", "fatores": dict(G), "descricao": "permanentes"}
    out["ELS Q"] = {"tipo": "ELS", "fatores": {"PP": 1.0, "CP": 1.0, **{k: 1.0 for k in Q}}, "descricao": "rara: permanentes + sobrecargas"}
    for v in ventos:
        out["ELS %s" % v] = {"tipo": "ELS", "fatores": {"PP": 1.0, "CP": 1.0, v: 1.0}, "descricao": "rara: permanentes + vento %s" % v}
    return out


def calcular(doc, par: Optional[dict] = None) -> dict:
    P = dict(AE.PARAMETROS_PADRAO, **(par or {}))
    r = AE._calcular_situacao(doc, P, montador=montar, carregador=cargas, combinador=combinacoes)
    r["modelo_analise"] = "premoldado"
    r["reacoes_envoltoria"] = AE.envoltoria_das_reacoes({"": r})
    r["grupos_perfis"] = AE.grupos_de_perfis(r)
    return r
