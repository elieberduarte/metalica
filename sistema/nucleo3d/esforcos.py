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
PESO_AGUA = 10.0             # kN/m³ — NBR 6120:2019, Tabela A.1 (água doce)
RAIO_CAIXA = 1.5             # m: a caixa d'água descarrega nos nós das vigas até esta distância do centro


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

# ------------------------------------------------------------------ vento (NBR 6123:2023)
#: Tabela 3 — fator S2 pela altura z (m), categoria de rugosidade e classe (A, B, C)
S2_2023 = {
    5: {"I": (1.06, 1.04, 1.01), "II": (0.94, 0.92, 0.89), "III": (0.88, 0.86, 0.82), "IV": (0.79, 0.76, 0.73), "V": (0.74, 0.72, 0.67)},
    10: {"I": (1.10, 1.09, 1.06), "II": (1.00, 0.98, 0.95), "III": (0.94, 0.92, 0.88), "IV": (0.86, 0.83, 0.80), "V": (0.74, 0.72, 0.67)},
    15: {"I": (1.13, 1.12, 1.09), "II": (1.04, 1.02, 0.99), "III": (0.98, 0.96, 0.93), "IV": (0.90, 0.88, 0.84), "V": (0.79, 0.76, 0.72)},
    20: {"I": (1.15, 1.14, 1.12), "II": (1.06, 1.04, 1.02), "III": (1.01, 0.99, 0.96), "IV": (0.93, 0.91, 0.88), "V": (0.82, 0.80, 0.76)},
    30: {"I": (1.17, 1.17, 1.15), "II": (1.10, 1.08, 1.06), "III": (1.05, 1.03, 1.00), "IV": (0.98, 0.96, 0.93), "V": (0.87, 0.85, 0.82)},
    40: {"I": (1.20, 1.19, 1.17), "II": (1.13, 1.11, 1.09), "III": (1.08, 1.07, 1.04), "IV": (1.02, 0.99, 0.96), "V": (0.91, 0.89, 0.86)},
    50: {"I": (1.21, 1.21, 1.19), "II": (1.15, 1.13, 1.12), "III": (1.10, 1.09, 1.06), "IV": (1.04, 1.02, 0.99), "V": (0.94, 0.93, 0.89)},
}
#: Tabela 4 — fator estatístico S3 por grupo (1: abriga substâncias inflamáveis; 3: comércio)
S3_2023 = {1: 1.11, 2: 1.06, 3: 1.00, 4: 0.95, 5: 0.83}
#: Tabela 10 — telhados múltiplos simétricos de tramos iguais (h ≤ a'), θ = 5°: vento
#: perpendicular às cumeeiras (α = 0°), água a barlavento e a sotavento de cada tramo
TAB10_ALFA0 = {"a": -0.9, "b": -0.6, "c": -0.4, "d": -0.3, "m": -0.3, "n": -0.3, "x": -0.3, "z": -0.3}
#: e vento paralelo às cumeeiras (α = 90°): faixas b1 = h, b2 = h a partir da borda, b3 o resto
TAB10_ALFA90 = (-0.8, -0.6, -0.2)
VENTO_PADRAO = {"v0": None, "s1": 1.0, "categoria": "II", "classe": None, "grupo": 1, "cpi": (0.8, -0.3)}


def s2_2023(z: float, categoria: str = "II", classe: str = "C") -> float:
    """fator S2 da Tabela 3 da NBR 6123:2023, interpolado na altura (até 5 m, a linha de 5 m)"""
    col = "ABC".index(str(classe).upper())
    cat = str(categoria).upper()
    zs = sorted(S2_2023)
    z = max(zs[0], min(float(z), zs[-1]))
    for z0, z1 in zip(zs, zs[1:]):
        if z0 <= z <= z1:
            a, b = S2_2023[z0][cat][col], S2_2023[z1][cat][col]
            return a + (b - a) * (z - z0) / (z1 - z0)
    return S2_2023[zs[-1]][cat][col]


def classe_por_dimensao(maior_m: float) -> str:
    """NBR 6123:2023, 5.3.2: A até 20 m, B até 50 m, C acima"""
    return "A" if maior_m <= 20.0 else ("B" if maior_m <= 50.0 else "C")


def _tramos(u: np.ndarray, z: np.ndarray, passo: float = 0.5):
    """as calhas (vales) e as cumeeiras do telhado múltiplo ao longo de u (m), pela altura das
    terças: (calhas, cumeeiras de cada tramo, u mín., u máx.)"""
    u0, u1 = float(u.min()), float(u.max())
    n = int((u1 - u0) / passo) + 1
    soma, cont = np.zeros(n), np.zeros(n)
    k = ((u - u0) / passo).astype(int)
    np.add.at(soma, k, z)
    np.add.at(cont, k, 1)
    ok = cont > 0
    xs = np.arange(n)
    perfil = np.interp(xs, xs[ok], soma[ok] / cont[ok])
    perfil = np.convolve(perfil, np.ones(5) / 5.0, mode="same")
    calhas = []
    viz = int(3.0 / passo)
    longe = int(12.0 / passo)
    for i in range(viz, n - viz):
        janela = perfil[i - viz:i + viz + 1]
        if perfil[i] <= janela.min() + 1e-9:
            alto = min(perfil[max(0, i - longe):i].max(initial=perfil[i]), perfil[i:i + longe].max(initial=perfil[i]))
            if alto - perfil[i] > 0.08 and (not calhas or u0 + i * passo - calhas[-1] > 3.0):
                calhas.append(u0 + i * passo)
    bordas = [u0] + calhas + [u1]
    cumeeiras = []
    for a, b in zip(bordas, bordas[1:]):
        ia, ib = int((a - u0) / passo), max(int((b - u0) / passo), int((a - u0) / passo) + 1)
        cumeeiras.append(u0 + (ia + int(np.argmax(perfil[ia:ib]))) * passo)
    return calhas, cumeeiras, u0, u1


def _cpe_alfa0(u: float, calhas, cumeeiras) -> float:
    """Tabela 10, α = 0°: o coeficiente da água em que u está (u cresce no sentido do vento)"""
    k = sum(1 for c in calhas if c < u)
    n = len(calhas) + 1
    barlavento = u < cumeeiras[k]
    if k == 0:
        par = ("a", "b")
    elif k == 1:
        par = ("c", "d")
    elif k == n - 1:
        par = ("x", "z")
    else:
        par = ("m", "n")
    return TAB10_ALFA0[par[0] if barlavento else par[1]]
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

def _casos_de_vento(casos: dict, faixas, nos, ia, ib, d, base: float, car: dict, vento: Optional[dict],
                    avisos: List[str]) -> Optional[dict]:
    """os casos de vento na cobertura (NBR 6123:2023), acrescentados a `casos`: quatro sentidos
    (perpendicular e paralelo às cumeeiras, de um lado e do outro) × cada cpi. A cobertura cuja
    altura livre não chega à metade da profundidade (7.2.1) vai como edificação fechada de mesma
    cobertura — telhado múltiplo, Tabela 10 — com cpi = +0,8 e −0,3. A força sai pela diferença
    entre a pressão de dentro e a de fora, na faixa de cada terça. Devolve a memória do vento."""
    v = dict(VENTO_PADRAO)
    v.update({k: val for k, val in (vento or {}).items() if val not in (None, "")})
    if v.get("v0") is None:
        v["v0"] = car.get("v0")
    if not v.get("v0") or not faixas:
        return None
    idx = np.array([f[0] for f in faixas])
    w = np.array([f[1] for f in faixas])
    Lh = np.array([f[2] for f in faixas])
    meio = (nos[ia[idx]] + nos[ib[idx]]) / 2.0
    # as cumeeiras correm ao longo das terças: a direção dominante delas (ângulo dobrado, sem sinal)
    ang2 = np.arctan2(d[idx, 1], d[idx, 0]) * 2.0
    a_t = 0.5 * math.atan2(float((np.sin(ang2) * Lh).sum()), float((np.cos(ang2) * Lh).sum()))
    ev = np.array([math.cos(a_t), math.sin(a_t)])        # ao longo das cumeeiras
    eu = np.array([-ev[1], ev[0]])                         # perpendicular a elas
    u = meio[:, :2] @ eu
    vv = meio[:, :2] @ ev
    z = meio[:, 2]
    h = float(z.max() - base)
    maior = float(max(u.max() - u.min(), vv.max() - vv.min()))
    classe = v.get("classe") or classe_por_dimensao(maior)
    s2 = s2_2023(h, v["categoria"], classe)
    s3 = S3_2023[int(v["grupo"])]
    vk = float(v["v0"]) * float(v["s1"]) * s2 * s3
    q = 0.613 * vk ** 2 / 1000.0                           # kN/m²
    calhas, _cum, u0, u1 = _tramos(u, z)
    bordas = [u0] + calhas + [u1]
    tramo = float(np.median(np.diff(bordas))) if len(bordas) > 1 else u1 - u0
    if h > tramo:
        avisos.append("vento: altura %.1f m maior que o tramo %.1f m do telhado múltiplo — a Tabela 10 pede h ≤ a'"
                      % (h, tramo))

    def nome_eixo(vetor, sinal):
        x, y = vetor * sinal
        return ("+x" if x > 0 else "−x") if abs(x) >= abs(y) else ("+y" if y > 0 else "−y")
    cpes = {}
    for sinal in (1.0, -1.0):                              # α = 0°: vento perpendicular às cumeeiras
        cal_s, cum_s, _a, _b = _tramos(u * sinal, z)
        cpes["vento %s (perpendicular às cumeeiras)" % nome_eixo(eu, sinal)] = np.array(
            [_cpe_alfa0(ui, cal_s, cum_s) for ui in u * sinal])
    for sinal in (1.0, -1.0):                              # α = 90°: faixas a partir da borda
        vs = vv * sinal
        tira = np.floor(u / 2.0).astype(int)
        vmin = {t: vs[tira == t].min() for t in set(tira.tolist())}
        dist = vs - np.array([vmin[t] for t in tira])
        cpes["vento %s (paralelo às cumeeiras)" % nome_eixo(ev, sinal)] = np.where(
            dist < h, TAB10_ALFA90[0], np.where(dist < 2 * h, TAB10_ALFA90[1], TAB10_ALFA90[2]))
    nomes = []
    for rot, cpe in cpes.items():
        for cpi in v["cpi"]:
            nome = "V%d" % (len(nomes) + 1)
            f = np.zeros_like(casos["PP"])
            para_cima = (float(cpi) - cpe) * q * w * Lh / 2.0   # kN em cada ponta (+ para cima)
            np.add.at(f, ia[idx] * 6 + 2, para_cima)
            np.add.at(f, ib[idx] * 6 + 2, para_cima)
            casos[nome] = f
            nomes.append({"caso": nome, "descricao": "%s, cpi %+.1f" % (rot, float(cpi)),
                          "para_cima_kN": round(float(para_cima.sum() * 2), 1)})
    return {"v0": float(v["v0"]), "s1": float(v["s1"]), "categoria": v["categoria"], "classe": classe,
            "grupo": int(v["grupo"]), "s2": round(s2, 3), "s3": s3, "vk": round(vk, 2), "q": round(q, 3),
            "h": round(h, 2), "tramo": round(tramo, 2), "calhas_m": [round(c, 2) for c in calhas],
            "cpi": list(v["cpi"]), "casos": nomes,
            "norma": "NBR 6123:2023 — 7.2.1 (cobertura isolada com h < 0,5·ℓ2 → edificação fechada, cpi +0,8/−0,3), "
                     "Tabela 3 (S2), Tabela 4 (S3), Tabela 10 (telhados múltiplos, linha de 5°)"}


def hipoteses(r: dict) -> List[str]:
    """as hipóteses do cálculo, em texto, para quem confere (a tela de esforços as mostra)"""
    car = r.get("cargas") or {}
    h = ["Estrutura inteira como pórtico espacial no esqueleto (eixo a eixo), nós rígidos; o contravento redondo "
         "trabalha também à compressão.",
         "Perfil duplo (2L, 2Ue) como duas vezes o simples (área e inércias), sem o afastamento entre eles.",
         "Pé do pilar rotulado; engastado onde a locação do projeto dá momento na base.",
         "Cargas de cobertura pelas terças, cada uma com a faixa até a meia distância das vizinhas: telha %.3f, forro "
         "%.3f, painéis %.3f (permanentes) e sobrecarga %.3f kN/m² — %s." % (
             car.get("telha", 0), car.get("forro", 0), car.get("paineis", 0), car.get("sobrecarga", 0),
             car.get("fonte", "padrão do programa")),
         "Peso próprio pelo kg/m do perfil no comprimento de eixo a eixo (sem chapas e ligações)."]
    v = r.get("vento")
    if v:
        h.append("Vento NBR 6123:2023: V0 %.0f m/s, S1 %.2f, S2 %.3f (categoria %s, classe %s, h %.1f m), S3 %.2f (grupo %d) → "
                 "Vk %.1f m/s, q %.3f kN/m². Cobertura com altura livre menor que metade da profundidade: edificação "
                 "fechada (7.2.1), telhado múltiplo pela Tabela 10 (linha de 5°), cpi %s. Tramo médio %.1f m. Só a "
                 "pressão na cobertura (sem as forças horizontais nos painéis e no frontão, nem o atrito)." % (
                     v["v0"], v["s1"], v["s2"], v["categoria"], v["classe"], v["h"], v["s3"], v["grupo"], v["vk"], v["q"],
                     " e ".join("%+.1f" % c for c in v["cpi"]), v["tramo"]))
    if r.get("caixas_dagua"):
        h.append("Caixas d'água: volume × 10 kN/m³ (NBR 6120:2019, Tabela A.1) nos nós das vigas embaixo de cada uma, "
                 "como ação variável (γ 1,5; ψ0 0,8).")
    h.append("Combinações últimas normais: γ 1,25 (peso próprio), 1,40 (telha, forro, painéis), 1,50 (sobrecarga), "
             "1,40 (vento); ψ0 0,8 (cobertura) e 0,6 (vento); no levantamento, permanentes com γ 1,0.")
    return h


def combinacoes_ultimas(casos: List[str]) -> List[dict]:
    """as combinações últimas normais (NBR 8800, Tabelas 1 e 2; γ e ψ de nucleo/cargas.py): com
    as permanentes desfavoráveis, cada ação variável (sobrecarga, água das caixas, cada vento)
    uma vez como principal e as outras reduzidas por ψ0 — um vento de cada vez; e o
    levantamento, com as permanentes favoráveis (γ = 1,0) e o vento de sucção sozinho."""
    from nucleo import cargas as C
    gpp = C.GAMA_G[next(k for k in C.GAMA_G if k.startswith("met"))][0]            # 1,25
    gcp = C.GAMA_G[next(k for k in C.GAMA_G if k.startswith("industrializado"))][0]  # 1,40
    gsc, gv = C.GAMA_Q["sobrecarga"][0], C.GAMA_Q["vento"][0]                      # 1,50 e 1,40
    psc, pv = C.PSI["cobertura"][0], C.PSI["vento"][0]                             # 0,8 e 0,6
    pag = C.PSI[next(k for k in C.PSI if k.startswith("dep"))][0]                  # 0,8 (água: como depósito)
    perm = {"PP": gpp, "CP": gcp}
    grav = [(c, g, p) for c, g, p in (("SC", gsc, psc), ("AG", gsc, pag)) if c in casos]
    vs = [c for c in casos if c.startswith("V")]
    out = []
    for vento in [None] + vs:
        var = grav + ([(vento, gv, pv)] if vento else [])
        for principal, g1, _p1 in var:
            f = dict(perm)
            f[principal] = g1
            for c, g, p in var:
                if c != principal:
                    f[c] = g * p
            out.append({"nome": "ELU[%s]%s" % (principal, "+" + vento if vento and vento != principal else ""), "fatores": f})
    for c in vs:
        out.append({"nome": "ELU[%s]-levantamento" % c, "fatores": {"PP": 1.0, "CP": 1.0, c: gv}})
    for cb in out:
        cb["expressao"] = " + ".join("%s·%s" % (("%.2f" % f).replace(".", ","), k) for k, f in cb["fatores"].items())
    return out


def calcular(doc, cargas: Optional[dict] = None, esq: Optional[dict] = None, vento: Optional[dict] = None) -> dict:
    """reações e esforços da estrutura inteira para os casos PP (peso próprio), CP (telha, forro
    e painéis), SC (sobrecarga) e os de vento (NBR 6123:2023, quando há V0: nas cargas do
    projetista ou em `vento`), e as combinações últimas com a envoltória por pilar. Devolve
    {casos, pilares, combinacoes, vento, esforcos, resumo, cargas, avisos}"""
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
    faixas = []                                            # (barra, largura, comprimento na horizontal)
    for e, w in larg.items():
        i = pos[e]
        if w <= 0:
            sem_vizinha += 1
            continue
        Lh = float(np.hypot(d[i][0], d[i][1]))
        area += w * Lh
        faixas.append((i, w, Lh))
        for caso, q, comp in (("CP", sum(car[k] for k in PERMANENTES), L[i]), ("SC", car["sobrecarga"], Lh)):
            f = q * w * comp / 2
            casos[caso][ia[i] * 6 + 2] -= f
            casos[caso][ib[i] * 6 + 2] -= f
    if sem_vizinha:
        avisos.append("%d trechos de terça sem outra terça paralela a até %.1f m: sem carga de cobertura" % (sem_vizinha, LARG_MAX))
    # --- a água das caixas desenhadas nas outras plantas (a base da caixa d'água), nos nós das
    # vigas e banzos daquele nível embaixo de cada caixa
    caixas = ((doc.metadados or {}).get("de_planta") or {}).get("caixas_dagua") or []
    memoria_caixas = []
    if caixas:
        casos["AG"] = np.zeros(ndof)
        horiz = [i for i, e in enumerate(usadas) if barras[e]["papel"] in ("viga", "banzo")]
        cand = np.array(sorted({int(ia[i]) for i in horiz} | {int(ib[i]) for i in horiz}))
        for c in caixas:
            P = float(c["litros"]) / 1000.0 * PESO_AGUA
            xy = np.array([c["x"], c["y"]]) / 1000.0
            dz = np.abs(nos[cand, 2] - float(c["nivel"]) / 1000.0)
            dxy = np.linalg.norm(nos[cand, :2] - xy, axis=1)
            sel = cand[(dz < 0.6) & (dxy < RAIO_CAIXA)]
            if not len(sel):
                perto = np.nonzero((dz < 0.6) & (dxy < 3.0))[0]
                sel = cand[perto[np.argsort(dxy[perto])[:4]]] if len(perto) else sel
            if not len(sel):
                avisos.append("caixa d'água de %d l em (%.1f; %.1f) sem viga no nível %.2f m embaixo: fora do cálculo"
                              % (c["litros"], xy[0], xy[1], c["nivel"] / 1000.0))
                continue
            casos["AG"][sel * 6 + 2] -= P / len(sel)
            memoria_caixas.append({"litros": c["litros"], "kN": round(P, 1), "nos": len(sel),
                                   "x": round(xy[0], 2), "y": round(xy[1], 2), "nivel": c["nivel"]})
    memoria_vento = _casos_de_vento(casos, faixas, nos, ia, ib, d, base, car, vento, avisos)

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
    ids_do_no = collections.defaultdict(set)
    for e in usadas:
        br = barras[e]
        if br["papel"] == "pilar":
            for k in ("a", "b"):
                ids_do_no[br[k]].update(br["ids"])
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
                        "ids": sorted(set().union(*(ids_do_no[n] for n in g_))),
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

    # --- as combinações últimas e a envoltória da vertical em cada pilar (+ compressão)
    combs = combinacoes_ultimas(list(casos))
    for p in pilares:
        rz = {c: v[2] for c, v in p["reacoes_kN"].items()}
        vals = [(sum(f * rz.get(c, 0.0) for c, f in cb["fatores"].items()), cb["nome"]) for cb in combs]
        mx, mn = max(vals), min(vals)
        p["envoltoria_kN"] = {"max": round(mx[0], 2), "max_comb": mx[1], "min": round(mn[0], 2), "min_comb": mn[1]}
        p["caracteristico_kN"] = round(rz["PP"] + rz["CP"] + rz["SC"] + rz.get("AG", 0.0), 2)

    # --- esforços nas barras (N, Vy, Vz, T, My, Mz nas duas pontas, eixos locais), por caso
    Ue = U[gl]                                             # (n, 12, casos)
    fl = np.einsum("nij,njk,nkc->nic", kl, T, Ue)
    esforcos = {}
    for i, e in enumerate(usadas):
        esforcos[e] = {c: [round(float(v), 3) for v in fl[i, :, j]] for j, c in enumerate(casos)}

    # a planta (banzos e vigas vistos de cima), para a tela desenhar os pilares no lugar
    planta = []
    for i, e in enumerate(usadas):
        if barras[e]["papel"] in ("banzo", "viga") and abs(d[i][2]) < 0.5 * L[i]:
            a_, b_ = nos[ia[i]], nos[ib[i]]
            planta.append([round(a_[0], 2), round(a_[1], 2), round(b_[0], 2), round(b_[1], 2)])
    return {
        "planta": planta,
        "casos": resumo_casos,
        "pilares": pilares,
        "cargas_sem_pilar": sem_pilar,
        "esforcos": esforcos,
        "esqueleto": esq,
        "resumo": {"nos": int(usados_nos.sum()), "barras": len(usadas), "apoios": len(pes),
                   "engastados": len(engaste), "pilares": len(pilares), "area_cobertura_m2": round(area, 1),
                   "peso_aco_kg": round(float(peso.sum() / G), 0), "graus_de_liberdade": int(len(livre))},
        "cargas": car,
        "vento": memoria_vento,
        "caixas_dagua": memoria_caixas,
        "combinacoes": combs,
        "avisos": avisos,
        "_U": U, "_casos": list(casos),
    }
