# -*- coding: utf-8 -*-
"""O que o IFC traz além das peças de aço detalháveis.

Um modelo de obra inteira (a Obra Capitão, exportada do SketchUp) mistura o pré-moldado
com o aço: laje alveolar, vigas e pilares de concreto e aparelhos de neoprene vinham como
IfcBeam/IfcColumn e o detalhamento os tratava como barras de aço — 20 mil toneladas.
E a estrutura metálica da cobertura chegava em 15 malhas soltas (IfcBuildingElementProxy),
que o detalhamento contava como parafusos.

Aqui ficam as duas separações:

* `material_nao_aco` — concreto, neoprene, madeira, vidro… pelo material da peça: saem do
  aço e vão para a lista de pré-moldados (`resumo_fora_do_aco`: peças por nome, volume em
  m³ e peso pela massa específica do material);
* `proxy_estrutural` e `estrutura_a_conferir` — a malha grande de aço sem peças separa-se
  pelas partes conectadas, e cada parte é medida (comprimento, caixa da seção, kg/m): sai
  uma lista para orçar e conferir, não desenhos de produção — o IFC não diz o perfil, as
  terças vêm contínuas de ponta a ponta e barras encostadas saem grudadas.
"""
import collections
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

#: Material (texto do IFC, sem acento e em minúsculas) → (categoria, massa específica kg/m³).
MATERIAIS_NAO_ACO: Sequence[Tuple[str, str, float]] = (
    (r"concret|concreto|fck|pre.?moldad|premoldad", "concreto", 2500.0),
    (r"neoprene|elastomer", "neoprene", 1250.0),
    (r"madeira|wood|timber", "madeira", 600.0),
    (r"vidro|glass", "vidro", 2500.0),
    (r"alvenaria|masonry|tijolo|bloco ceram", "alvenaria", 1800.0),
)

#: Malha solta de aço maior que isto (diagonal da caixa, mm) é estrutura, não parafuso.
DIAGONAL_MIN_PROXY = 1500.0
#: Parte da malha mais comprida que isto (mm) é barra contínua ou aglomerado.
COMPRIMENTO_CONTINUO = 24000.0


def _sem_acento(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


#: Nome de peça que é o terreno (o "SOLO" da Obra Capitão, 31 mil m³ com material de
#: concreto): não é pré-moldado nem aço, fica fora de tudo.
NOME_TERRENO = r"^(solo|terreno|terrain|ground|topografia)\b"


def material_nao_aco(ent) -> Optional[Tuple[str, float]]:
    """(categoria, massa específica) do material que não é aço; None para aço ou sem
    material (na dúvida, fica no aço, como antes). O terreno sai como ("terreno", 0)."""
    if re.search(NOME_TERRENO, _sem_acento(str(getattr(ent, "nome", "") or "")).strip()):
        return "terreno", 0.0
    m = _sem_acento(str(getattr(ent, "material", "") or ""))
    if not m or re.search(r"steel|aco\b|a36|a572|a500|astm|civil|usi|zar", m):
        return None
    for padrao, categoria, rho in MATERIAIS_NAO_ACO:
        if re.search(padrao, m):
            return categoria, rho
    return None


def volume_da_malha(vertices, faces) -> float:
    """Volume (mm³) da malha fechada, pela soma dos tetraedros com o centroide dos
    vértices (com a origem do arquivo, longe da peça, o arredondamento pesava)."""
    import numpy as np
    P = vertices if isinstance(vertices, np.ndarray) else np.asarray(vertices, dtype=float)
    if len(P):
        P = P - P.mean(axis=0)
    ia, ib, ic = [], [], []
    for f in faces:
        for i in range(1, len(f) - 1):
            ia.append(f[0])
            ib.append(f[i])
            ic.append(f[i + 1])
    if not ia:
        return 0.0
    A, B, C = P[ia], P[ib], P[ic]
    return float(abs(np.einsum("ij,ij->i", A, np.cross(B, C)).sum()) / 6.0)


def resumo_fora_do_aco(itens: Sequence[tuple]) -> List[dict]:
    """[(entidade, categoria, rho)] → linhas por nome e material: quantidade, volume (m³)
    e peso (kg)."""
    grupos: Dict[tuple, dict] = collections.OrderedDict()
    for ent, categoria, rho in itens:
        if categoria == "terreno":
            continue
        nome = str(getattr(ent, "nome", "") or "?")
        mat = str(getattr(ent, "material", "") or "")
        g = grupos.setdefault((nome, mat), {"nome": nome, "material": mat, "categoria": categoria,
                                            "massa_especifica": rho, "quantidade": 0, "volume_m3": 0.0,
                                            "peso_kg": 0.0, "tipo_ifc": str((ent.atributos or {}).get("tipo_ifc") or "")})
        v = volume_da_malha(getattr(ent, "vertices", None) or [], getattr(ent, "faces", None) or []) * 1e-9
        g["quantidade"] += 1
        g["volume_m3"] += v
        g["peso_kg"] += v * rho
    linhas = sorted(grupos.values(), key=lambda g: (g["categoria"], -g["volume_m3"]))
    for g in linhas:
        g["volume_m3"] = round(g["volume_m3"], 3)
        g["peso_kg"] = round(g["peso_kg"], 1)
    return linhas


def _pca(X):
    """(centro, eixos em colunas do maior espalhamento ao menor, extensões nesses eixos)."""
    import numpy as np
    c = X.mean(axis=0)
    w, U = np.linalg.eigh(np.cov((X - c).T) if len(X) > 3 else np.eye(3))
    U = U[:, ::-1]
    Y = (X - c) @ U
    return c, U, Y.max(axis=0) - Y.min(axis=0), Y[:, 0].min()


def _eixos(X):
    return _pca(X)[2]


def _triangulos(P, fs, c, U):
    """Os triângulos (leque) da parte no sistema dos eixos: (abscissa no eixo 1 de cada
    vértice, coordenadas nos eixos 2 e 3), arrays (n, 3) e (n, 3, 2)."""
    import numpy as np
    ia, ib, ic = [], [], []
    for f in fs:
        for i in range(1, len(f) - 1):
            ia.append(f[0])
            ib.append(f[i])
            ic.append(f[i + 1])
    T = np.stack([P[ia], P[ib], P[ic]], axis=1) - c          # (n, 3, 3)
    Y = T @ U                                                 # no sistema dos eixos
    return Y[:, :, 0], Y[:, :, 1:]


def _lacos_do_corte(P, fs, c, U, s0, tri=None):
    """Os laços (polígonos 2D no plano dos eixos 2 e 3) do corte da malha pelo plano
    perpendicular ao eixo 1 na abscissa s0, e se o corte ramifica (um ponto com mais de
    dois segmentos: perfis encostados, que o laço não separa). Laço que não fecha não entra."""
    import numpy as np
    S, W = tri if tri is not None else _triangulos(P, fs, c, U)
    sv = S - s0
    neg = sv < 0
    cruza = neg.any(axis=1) & ~neg.all(axis=1)                # o plano passa pelo triângulo
    sv, W, neg = sv[cruza], W[cruza], neg[cruza]
    pontos = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        corta = neg[:, a] != neg[:, b]
        den = np.where(corta, sv[:, a] - sv[:, b], 1.0)
        t = np.where(corta, sv[:, a] / den, 0.0)[:, None]
        pontos.append((corta, W[:, a] + t * (W[:, b] - W[:, a])))
    segs = []
    for k in range(len(sv)):
        pts = [tuple(round(float(x), 2) for x in q[k]) for corta, q in pontos if corta[k]]
        if len(pts) == 2 and pts[0] != pts[1]:
            segs.append((pts[0], pts[1]))
    vizinhos = collections.defaultdict(list)
    for k, (a, b) in enumerate(segs):
        vizinhos[a].append(k)
        vizinhos[b].append(k)
    ramificado = any(len(ks) > 2 for ks in vizinhos.values())
    usados, lacos = set(), []
    for k0 in range(len(segs)):
        if k0 in usados:
            continue
        usados.add(k0)
        inicio, atual = segs[k0]
        laco = [inicio, atual]
        fechou = False
        for _ in range(len(segs)):
            prox = [k for k in vizinhos[atual] if k not in usados]
            if not prox:
                break
            k = prox[0]
            usados.add(k)
            a, b = segs[k]
            atual = b if a == atual else a
            if atual == inicio:
                fechou = True
                break
            laco.append(atual)
        if fechou and len(laco) >= 3:
            lacos.append(laco)
    return lacos, ramificado


def _area_laco(laco):
    return 0.5 * sum(laco[i][0] * laco[(i + 1) % len(laco)][1] - laco[(i + 1) % len(laco)][0] * laco[i][1]
                     for i in range(len(laco)))


def _dentro(pt, laco):
    x, y = pt
    dentro = False
    for i in range(len(laco)):
        (x1, y1), (x2, y2) = laco[i], laco[(i + 1) % len(laco)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dentro = not dentro
    return dentro


def area_pelo_corte(P, fs, estacoes=(0.3, 0.5, 0.7)):
    """(área da seção em mm², perfis separados no corte) pela mediana dos cortes que
    fecham. Laço dentro de laço é furo (tubo). None quando nenhum corte fecha."""
    c, U, ext, s_min = _pca(P[sorted({v for f in fs for v in f})])
    tri = _triangulos(P, fs, c, U)
    resultados = []
    for e in estacoes:
        s0 = s_min + e * ext[0] + 0.37                     # fora dos vértices da malha
        lacos, ramificado = _lacos_do_corte(P, fs, c, U, s0, tri)
        if not lacos:
            continue
        area, externos = 0.0, 0
        for i, l in enumerate(lacos):
            prof = sum(1 for j, o in enumerate(lacos) if j != i and _dentro(l[0], o))
            area += abs(_area_laco(l)) * (1 if prof % 2 == 0 else -1)
            externos += prof % 2 == 0
        if ramificado:
            externos = max(externos, 2)                   # perfis encostados: não é um só
        # área menor que 2 % da caixa: laços que se anulam, não uma seção
        if area > 0.02 * ext[1] * ext[2]:
            resultados.append((area, externos))
    if not resultados:
        return None, 0
    resultados.sort()
    return resultados[len(resultados) // 2]


def proxy_estrutural(ent) -> bool:
    """Malha solta (IfcBuildingElementProxy) de aço e grande: estrutura, não parafuso."""
    if material_nao_aco(ent) is not None:
        return False
    nome = _sem_acento(str(getattr(ent, "nome", "") or ""))
    if re.search(r"bolt|parafus|porca|nut\b|washer|arruela|chumbador|anchor", nome):
        return False
    V = getattr(ent, "vertices", None) or []
    if len(V) < 8:
        return False
    xs, ys, zs = zip(*V)
    diag = math.sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2 + (max(zs) - min(zs)) ** 2)
    return diag >= DIAGONAL_MIN_PROXY


def _fechada(fs, idx) -> bool:
    """Toda aresta (pelos vértices soldados) em exatamente duas faces: malha fechada, e
    só então o volume — e o kg/m — valem alguma coisa."""
    arestas = collections.Counter()
    for f in fs:
        n = len(f)
        for i in range(n):
            a, b = idx[f[i]], idx[f[(i + 1) % n]]
            if a != b:
                arestas[(a, b) if a < b else (b, a)] += 1
    return bool(arestas) and all(c == 2 for c in arestas.values())


def _partes(V, F):
    """Faces agrupadas pelas partes conectadas (vértices iguais a 0,1 mm) e o índice de
    cada vértice já soldado."""
    import numpy as np
    X = np.round(np.asarray(V, dtype=float), 1)
    _, idx = np.unique(X, axis=0, return_inverse=True)
    idx = [int(k) for k in np.asarray(idx).ravel()]
    pai = list(range(max(idx) + 1 if idx else 0))

    def ache(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a
    for f in F:
        if not f:
            continue
        r0 = ache(idx[f[0]])
        for v in f[1:]:
            r = ache(idx[v])
            if r != r0:
                pai[r] = r0
    grupos: Dict[int, List[int]] = collections.defaultdict(list)
    for k, f in enumerate(F):
        if f:
            grupos[ache(idx[f[0]])].append(k)
    return list(grupos.values()), idx


def estrutura_a_conferir(proxies: Sequence, avisar=None) -> List[dict]:
    """As malhas soltas de aço separadas em partes e medidas: por tipo (barra, barra
    redonda, chapa/ligação, contínua/aglomerado), seção (caixa) e kg/m, com quantidade,
    comprimento e peso. Tudo "a conferir": o perfil não vem no IFC."""
    import numpy as np
    grupos: Dict[tuple, dict] = {}
    for ent in proxies:
        if avisar:
            avisar("medindo a estrutura sem peças (%s)…" % (getattr(ent, "nome", "") or "")[:40])
        V, F = ent.vertices, ent.faces
        P = np.asarray(V, dtype=float)
        partes, idx = _partes(V, F)
        for faces in partes:
            fs = [F[k] for k in faces]
            vs = sorted({v for f in fs for v in f})
            if len(vs) < 4:
                continue
            L, H, T = (float(x) for x in _eixos(P[vs]))
            if L <= 0:
                continue
            perfis = 1
            if _fechada(fs, idx) and L <= COMPRIMENTO_CONTINUO:
                mapa = {v: i for i, v in enumerate(vs)}
                area = volume_da_malha(P[vs], [[mapa[v] for v in f] for f in fs]) / L      # mm²
            else:
                # malha aberta (sem as tampas) ou comprida demais para o volume dizer a
                # seção: corta a peça atravessada ao eixo
                area, perfis = area_pelo_corte(P, fs)
                area = area or 0.0
            kg_m = area * 7.85e-3 if area > 0 else None
            # mais pesado que a seção cheia da caixa: a medida não fecha
            if kg_m is not None and area > 1.02 * H * T:
                kg_m = None
            if L > COMPRIMENTO_CONTINUO and perfis <= 1 and kg_m is not None:
                tipo = "barra contínua (dividir em barras comerciais)"
            elif L > COMPRIMENTO_CONTINUO:
                tipo = "aglomerado de barras (separar)"
            elif L < 3.0 * H:
                tipo = "chapa ou ligação"
            elif H > 0 and abs(H - T) <= 0.15 * H and kg_m is not None and area >= 0.6 * math.pi * (H / 2) ** 2:
                tipo = "barra redonda"
            else:
                tipo = "barra"
            chave = (tipo, int(round(H)), int(round(T)), round(kg_m, 1) if kg_m is not None else None,
                     int(round(L / 10.0)) * 10 if L <= COMPRIMENTO_CONTINUO else int(round(L / 1000.0)) * 1000)
            g = grupos.setdefault(chave, {"tipo": tipo, "secao": "%d × %d" % (chave[1], chave[2]), "kg_m": chave[3],
                                          "comprimento": chave[4], "quantidade": 0, "peso_kg": 0.0,
                                          "origem": set()})
            g["quantidade"] += 1
            if kg_m is None:
                g["peso_kg"] = None                             # malha aberta: sem peso medido
            elif g["peso_kg"] is not None:
                g["peso_kg"] += kg_m * L / 1000.0
            g["origem"].add(re.sub(r"_spec_.*$", "", str(getattr(ent, "nome", "") or "")))
    linhas = sorted(grupos.values(), key=lambda g: (g["tipo"], g["secao"], -g["comprimento"]))
    for g in linhas:
        if g["peso_kg"] is not None:
            g["peso_kg"] = round(g["peso_kg"], 1)
        g["origem"] = ", ".join(sorted(g["origem"]))
    return linhas
