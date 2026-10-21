# -*- coding: utf-8 -*-
"""A estrutura lançada na planta (CAD, menu Estrutura) vira o modelo 3D.

Os elementos são entidades comuns do desenho 2D com `atributos.elemento`:

* pilar — polilinha fechada (o contorno em planta, já girado), `nivel_base` e `nivel_topo` (mm), `secao`
  ({tipo: retangular|T|I|U, b, h, … em cm} no concreto, {perfil, aco} no aço), `material`, `marca`;
* viga — linha de a a b, `nivel_topo` (a face de cima no concreto; o eixo no aço), `secao`, `material`;
* fundacao — polilinha fechada, `altura` (mm), `nivel_topo`, `tipo` (sapata|bloco);
* consolo — polilinha fechada, `altura` (mm), `nivel_topo`;
* tesoura — linha de apoio a apoio: a viga de cobertura de concreto em I (`secao` bf, hf, bw, h no apoio, h_meio),
  o apoio em `nivel_base` na ponta a e `nivel_fim` na b, `forma` "duas águas" (mais alta no meio) ou "uma água";
* chapa — polilinha fechada de aço, `espessura` (mm), `nivel_topo` (a face de cima), `aco`;
* furo — círculo (camada FURO), `diametro`: fura a chapa em que cai;
* parafuso — círculo (camada PARAFUSO), `diametro`, `comprimento`, `nivel_topo` (a cabeça);
* painel — linha (o eixo da placa de fechamento): `espessura`, `modulo` (a largura do painel), `orientacao` vertical
  (em pé, lado a lado) ou horizontal (deitados, empilhados), `nivel_base`, `nivel_topo`, `tipo` alveolar ou maciço;
* laje — polilinha fechada: `tipo` maciça, alveolar ou pré-laje (as placas de `modulo` no `sentido` x ou y, com a
  `capa` moldada por cima), `espessura` da placa, `nivel_topo` (o topo da capa);
* escada — linha do pé ao topo (o sentido de subida): `largura`, `nivel_base`, `nivel_topo`, `espelho_max`, `espessura`
  (da laje da escada); os degraus iguais pelo desnível (n = ⌈H/espelho⌉).

O nível pode ser um número (mm) ou o nome de um nível do projeto. O concreto vira sólido extrudado
(material Concreto, nas camadas do galpão pré-moldado); o aço vira Barra com o perfil. Cada peça guarda
`origem_2d` (o id no desenho) e a marca, para a ida e volta.
"""
from __future__ import annotations

import collections
import copy
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo2d.desenho import Circulo, Desenho, Linha, Polilinha
from nucleo3d.geometria import extrudar
from nucleo3d.modelo import Barra, Camada, Chapa, Documento, Solido

ELEMENTOS = ("pilar", "viga", "fundacao", "consolo", "tesoura", "chapa", "furo", "parafuso", "painel", "laje", "escada", "trelica")
CAMADAS = {"pilar": ("Pilares pré-moldados", "#9aa3ad"), "viga": ("Vigas pré-moldadas", "#b8c4d6"),
           "fundacao": ("Fundações", "#a89f91"), "consolo": ("Consolos", "#9aa3ad"),
           "tesoura": ("Vigas pré-moldadas", "#b8c4d6"), "chapa": ("Chapas", "#c9a227"),
           "furo": ("Chapas", "#c9a227"), "parafuso": ("Parafusos", "#1f5fbf"),
           "painel": ("Fechamento pré-moldado", "#b9b3a6"), "laje": ("Lajes", "#c2bcae"), "escada": ("Escadas", "#aaa39a"),
           "trelica": ("Treliças", "#4b5563")}
IFC = {"pilar": "IfcColumn", "viga": "IfcBeam", "fundacao": "IfcFooting", "consolo": "IfcMember", "tesoura": "IfcBeam",
       "chapa": "IfcPlate", "furo": "", "parafuso": "IfcMechanicalFastener", "painel": "IfcWall", "laje": "IfcSlab",
       "escada": "IfcStair", "trelica": "IfcMember"}

#: mm: a junta entre painéis e entre placas de laje (só no desenho do 3D)
JUNTA = 10.0
#: mm: a chapa de nó entre as almas do perfil "composto" (dois U de costas) — a do detalhe da emenda do CD Bom Dia
CHAPA_COMPOSTO = 6.35


def _nivel(v, niveis: Dict[str, float], padrao: float = 0.0) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        if v in niveis:
            return float(niveis[v])
        try:
            return float(v.replace(",", "."))
        except ValueError:
            pass
    return padrao


def elementos(des: Desenho) -> List[dict]:
    """os elementos lançados: [{id, elemento, atributos, entidade}]"""
    out = []
    for e in des.entidades.values():
        a = e.atributos or {}
        if a.get("elemento") in ELEMENTOS:
            out.append({"id": e.id, "elemento": a["elemento"], "atributos": a, "entidade": e})
    return out


def _contorno_z(pts: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """o contorno em planta (X, Y) no sistema da extrusão vertical de nucleo3d (o 1º eixo do contorno vai
    para o Y global e o 2º para o X): (x, y) → (−y, x), uma rotação que preserva a orientação"""
    return [(-y, x) for x, y in pts]


def _secao_concreto(s: dict) -> List[Tuple[float, float]]:
    """o contorno da seção (mm; u horizontal centrado, v da face de baixo) das seções de concreto"""
    t = s.get("tipo", "retangular")
    cm = lambda k, d=0.0: float(s.get(k, d) or d) * 10.0
    if t == "T":
        bf, hf, bw, h = cm("bf"), cm("hf"), cm("bw"), cm("h")
        return [(-bw / 2, 0), (bw / 2, 0), (bw / 2, h - hf), (bf / 2, h - hf), (bf / 2, h), (-bf / 2, h), (-bf / 2, h - hf), (-bw / 2, h - hf)]
    if t == "I":
        bf, hf, bw, h = cm("bf"), cm("hf"), cm("bw"), cm("h")
        return [(-bf / 2, 0), (bf / 2, 0), (bf / 2, hf), (bw / 2, hf), (bw / 2, h - hf), (bf / 2, h - hf), (bf / 2, h), (-bf / 2, h),
                (-bf / 2, h - hf), (-bw / 2, h - hf), (-bw / 2, hf), (-bf / 2, hf)]
    if t == "U":
        B, h, tp, tf = cm("B"), cm("h"), cm("t"), cm("tf")
        return [(-B / 2, 0), (B / 2, 0), (B / 2, h), (B / 2 - tp, h), (B / 2 - tp, tf), (-B / 2 + tp, tf), (-B / 2 + tp, h), (-B / 2, h)]
    b, h = cm("b"), cm("h")
    return [(-b / 2, 0), (b / 2, 0), (b / 2, h), (-b / 2, h)]


def _altura_secao(s: dict) -> float:
    return float(s.get("h", 0) or 0) * 10.0


def _marcar(sol, camada: str, atributos: dict, material: str = "Concreto"):
    sol.camada = camada
    sol.material = material
    sol.atributos = dict(atributos)
    return sol


def _prisma(perfil: Sequence[Tuple[float, float]], A: Tuple[float, float], d: Tuple[float, float], largura: float, nome: str) -> Solido:
    """o perfil (s ao longo da peça, z) convexo, espessado `largura` para os dois lados na horizontal perpendicular
    à direção d em planta, a partir do ponto A — a vista lateral da tesoura vira sólido"""
    n = (-d[1], d[0])
    k = len(perfil)
    vs = []
    for lado in (-0.5, 0.5):
        for s, z in perfil:
            vs.append((A[0] + d[0] * s + n[0] * lado * largura, A[1] + d[1] * s + n[1] * lado * largura, z))
    faces = [[0, i + 1, i] for i in range(1, k - 1)] + [[k, k + i, k + i + 1] for i in range(1, k - 1)]
    faces += [[i, (i + 1) % k, k + (i + 1) % k, k + i] for i in range(k)]
    sol = Solido(nome=nome, vertices=vs, faces=faces)
    if sol.volume < 0:
        sol.faces = [list(reversed(f)) for f in faces]
    return sol


def _tesoura(A, B, z_a: float, z_b: float, s: dict, forma: str, nome: str) -> List[Solido]:
    """a viga de cobertura em I: a mesa de baixo no apoio (de z_a a z_b), a alma e a mesa de cima, a altura do
    apoio (h) até o meio (h_meio) nas duas águas, constante na de uma água"""
    cm = lambda k, dflt=0.0: float(s.get(k, dflt) or dflt) * 10.0          # noqa: E731
    bf, hf, bw, h = cm("bf"), cm("hf"), cm("bw"), cm("h")
    hm = h if forma == "uma água" else cm("h_meio", s.get("h", 0))
    L = math.dist(A, B)
    d = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
    zb = lambda t: z_a + (z_b - z_a) * t / L                                # noqa: E731
    if hm > h + 1:
        topo = [(0.0, zb(0) + h), (L / 2, zb(L / 2) + hm), (L, zb(L) + h)]
    else:
        topo = [(0.0, zb(0) + h), (L, zb(L) + h)]
    baixo = [(0.0, zb(0)), (L, zb(L))]
    mesa_inf = baixo + [(L, zb(L) + hf), (0.0, zb(0) + hf)]
    alma = [(0.0, zb(0) + hf), (L, zb(L) + hf)] + [(t, z - hf) for t, z in reversed(topo)]
    out = [_prisma(mesa_inf, A, d, bf, nome + " — mesa de baixo"), _prisma(alma, A, d, bw, nome + " — alma")]
    for (t0, z0), (t1, z1) in zip(topo, topo[1:]):
        out.append(_prisma([(t0, z0 - hf), (t1, z1 - hf), (t1, z1), (t0, z0)], A, d, bf, nome + " — mesa de cima"))
    return out


def _paineis(A, B, a: dict, z0: float, z1: float, nome: str) -> List[Solido]:
    """os painéis de fechamento ao longo da linha A→B: em pé (lado a lado, na largura do módulo; o último fecha o
    comprimento) ou deitados (empilhados do nível da base ao do topo)"""
    L = math.dist(A, B)
    d = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
    esp = float(a.get("espessura") or 150.0)
    mod = max(float(a.get("modulo") or 1250.0), 100.0)
    out = []
    if str(a.get("orientacao") or "vertical") == "horizontal":
        z = z0
        k = 0
        while z < z1 - 1:
            zt = min(z + mod, z1)
            zf = zt if zt >= z1 - 1 else zt - JUNTA / 2                     # a junta só entre painéis
            out.append(_prisma([(0.0, z), (L, z), (L, zf), (0.0, zf)], A, d, esp, "%s — painel %d" % (nome, k + 1)))
            z, k = zt, k + 1
        return out
    s = 0.0
    k = 0
    while s < L - 1:
        s1 = min(s + mod, L)
        sf = s1 if s1 >= L - 1 else s1 - JUNTA / 2
        out.append(_prisma([(s, z0), (sf, z0), (sf, z1), (s, z1)], A, d, esp, "%s — painel %d" % (nome, k + 1)))
        s, k = s1 + JUNTA / 2, k + 1
    return out


def _laje(pts, a: dict, z_topo: float, nome: str) -> List[Solido]:
    """a laje: maciça (o contorno inteiro); alveolar ou pré-laje em placas de `modulo` no sentido pedido, dentro da
    caixa do contorno, e a capa por cima"""
    esp = float(a.get("espessura") or 200.0)
    tipo = str(a.get("tipo") or "maciça")
    capa = 0.0 if tipo == "maciça" else float(a.get("capa") or 0.0)
    out = []
    if tipo == "maciça":
        out.append(extrudar(_contorno_z(pts), (0.0, 0.0, 1.0), esp, origem=(0.0, 0.0, z_topo - esp), nome="%s — laje maciça" % nome))
        return out
    z_placa = z_topo - capa
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    mod = max(float(a.get("modulo") or 1250.0), 100.0)
    no_x = str(a.get("sentido") or "x") == "x"                # as placas correm em X, lado a lado em Y
    ini, fim = (y0, y1) if no_x else (x0, x1)
    t = ini
    k = 0
    while t < fim - 1:
        t1 = min(t + mod, fim)
        tf = t1 if t1 >= fim - 1 else t1 - JUNTA / 2
        if no_x:
            ret = [(x0, t), (x1, t), (x1, tf), (x0, tf)]
        else:
            ret = [(t, y0), (tf, y0), (tf, y1), (t, y1)]
        out.append(extrudar(_contorno_z(ret), (0.0, 0.0, 1.0), esp, origem=(0.0, 0.0, z_placa - esp), nome="%s — placa %d" % (nome, k + 1)))
        t, k = t1 + JUNTA / 2, k + 1
    if capa > 0:
        out.append(extrudar(_contorno_z(pts), (0.0, 0.0, 1.0), capa, origem=(0.0, 0.0, z_placa), nome="%s — capa" % nome))
    return out


def _escada(A, B, a: dict, z0: float, z1: float, nome: str) -> Tuple[List[Solido], dict]:
    """a escada de A (o pé) a B (o topo): n degraus iguais pelo desnível e pelo espelho máximo, cada um um sólido da
    laje inclinada ao piso do degrau (convexo); devolve os sólidos e {n, espelho, piso}"""
    L = math.dist(A, B)
    d = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
    H = z1 - z0
    n = max(1, math.ceil(abs(H) / max(float(a.get("espelho_max") or 180.0), 50.0) - 1e-9))
    e, p = H / n, L / n
    t = float(a.get("espessura") or 120.0) * math.sqrt(1 + (H / L) ** 2)       # a laje medida na vertical
    fundo = lambda s: z0 + H * s / L - t                                          # noqa: E731
    out = []
    for i in range(n):
        s0, s1 = i * p, (i + 1) * p
        topo = z0 + (i + 1) * e
        out.append(_prisma([(s0, fundo(s0)), (s1, fundo(s1)), (s1, topo), (s0, topo)], A, d, float(a.get("largura") or 1200.0),
                           "%s — degrau %d" % (nome, i + 1)))
    return out, {"n": n, "espelho": round(e, 1), "piso": round(p, 1), "blondel": round(2 * e + p, 1)}


def _dentro(p, poli) -> bool:
    x, y = p
    dentro = False
    for i in range(len(poli)):
        (x1, y1), (x2, y2) = poli[i], poli[(i + 1) % len(poli)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dentro = not dentro
    return dentro


def _altura_do_perfil(nome: str) -> float:
    """a altura d (mm) do perfil de aço do catálogo; 0 se não o acha"""
    try:
        from nucleo.perfis import perfil
        return float(perfil(nome).d or 0.0)
    except Exception:  # noqa: BLE001 — fora do nucleo.perfis (o W 200×41,7): o catálogo do 3D (11/10)
        pass
    try:
        from nucleo3d.geometria import resolver_perfil
        return float(getattr(resolver_perfil(nome), "d", 0.0) or 0.0)
    except (KeyError, ValueError, TypeError, AttributeError):
        return 0.0


def _centro_do_contorno(vs) -> Optional[Tuple[float, float]]:
    """o centro de gravidade do polígono (mm); None se degenerado"""
    pts = [(float(v[0]), float(v[1])) for v in vs or []]
    A = cx = cy = 0.0
    for i in range(len(pts)):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
        k = x0 * y1 - x1 * y0
        A += k
        cx += (x0 + x1) * k
        cy += (y0 + y1) * k
    if abs(A) < 1e-9:
        return None
    return cx / (3 * A), cy / (3 * A)


#: Duas linhas paralelas do desenho da tesoura a até esta distância (mm), no mesmo trecho, são as duas faces de um
#: mesmo perfil desenhado em linha dupla (o banzo em U visto de lado: 50 mm de aba no U 150×50).
LINHA_DUPLA_MAX = 120.0


def _linhas_duplas(segs: List[Tuple[float, float, float, float]]) -> Dict[int, Tuple[int, float, Tuple[float, float]]]:
    """{externa: (interna, distância, normal para dentro)}: os pares de linhas paralelas próximas que se cobrem no
    comprimento (as duas faces de um perfil em linha dupla). A externa é a mais longe do miolo da tesoura."""
    pts = [q for s in segs for q in ((s[0], s[1]), (s[2], s[3]))]
    cx, cy = sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts)
    pares: Dict[int, Tuple[int, float, Tuple[float, float]]] = {}
    usados = set()
    for i, a in enumerate(segs):
        la = math.hypot(a[2] - a[0], a[3] - a[1])
        if la < 1:
            continue
        ux, uy = (a[2] - a[0]) / la, (a[3] - a[1]) / la
        nx, ny = -uy, ux
        for j, b in enumerate(segs):
            if j <= i or i in usados or j in usados:
                continue
            lb = math.hypot(b[2] - b[0], b[3] - b[1])
            if lb < 1 or abs(((b[2] - b[0]) * ux + (b[3] - b[1]) * uy) / lb) < 0.9995:     # paralelas (< 1,8°)
                continue
            d0 = (b[0] - a[0]) * nx + (b[1] - a[1]) * ny
            d1 = (b[2] - a[0]) * nx + (b[3] - a[1]) * ny
            if abs(d0 - d1) > 5.0 or not (5.0 < abs(d0) <= LINHA_DUPLA_MAX):
                continue
            # cobrem-se no comprimento (a de dentro é mais curta nas pontas: as faces se encontram em meia-esquadria)
            ta = sorted((0.0, la))
            tb = sorted(((b[0] - a[0]) * ux + (b[1] - a[1]) * uy, (b[2] - a[0]) * ux + (b[3] - a[1]) * uy))
            cobre = min(ta[1], tb[1]) - max(ta[0], tb[0])
            if cobre < 0.5 * min(la, lb):
                continue
            # a externa é a mais longe do miolo
            da = abs((cx - a[0]) * nx + (cy - a[1]) * ny)
            mb = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            db = abs((cx - mb[0]) * nx + (cy - mb[1]) * ny)
            dist = abs(d0)
            if da >= db:
                s = 1.0 if d0 > 0 else -1.0
                pares[i] = (j, dist, (nx * s, ny * s))
            else:
                s = -1.0 if d0 > 0 else 1.0
                pares[j] = (i, dist, (nx * s, ny * s))
            usados.update((i, j))
    return pares


def _lado_das_ligadas(seg, normal, alma, tol: float) -> int:
    """+1, −1 ou 0: o lado com mais barras ligadas (ver _ligadas_dos_lados)"""
    mais, menos = _ligadas_dos_lados(seg, normal, alma, tol)
    return (mais > menos) - (mais < menos)


def _ligadas_dos_lados(seg, normal, alma, tol: float) -> Tuple[int, int]:
    """De que lado do perfil `seg` (u0, v0, u1, v1) ficam as barras da alma ligadas a ele: +1 do lado da `normal`, −1 do
    outro, 0 sem ligação. A ligada é a que tem uma ponta na linha do perfil (até `tol`, dentro do comprimento); a outra
    ponta diz o lado — é o miolo daquela tesoura, mesmo com outra tesoura encostada (o CD Bom Dia, 11/10: três tesouras
    por eixo, os montantes de ponta lado a lado a 330 mm no apoio da viga de transição). Devolve (do lado da normal,
    do outro)."""
    du, dv = seg[2] - seg[0], seg[3] - seg[1]
    L = math.hypot(du, dv)
    if L < 1:
        return 0, 0
    tu, tv = du / L, dv / L
    mais = menos = 0
    for a in alma:
        for (pu, pv), (qu, qv) in (((a[0], a[1]), (a[2], a[3])), ((a[2], a[3]), (a[0], a[1]))):
            ao_longo = (pu - seg[0]) * tu + (pv - seg[1]) * tv
            fora = abs((pu - seg[0]) * tv - (pv - seg[1]) * tu)
            if fora > tol or not (-tol <= ao_longo <= L + tol):
                continue
            lado = (qu - pu) * normal[0] + (qv - pv) * normal[1]
            if lado > 1.0:
                mais += 1
            elif lado < -1.0:
                menos += 1
            break
    return mais, menos


def _nos_no_eixo_do_banzo(segs, papeis, eixos: Dict[int, Tuple[float, float, float, float, float]], unir: float = 100.0):
    """Os nós da alma no eixo do banzo (NBR 8800:2024, 6.5.2: "os eixos que passam pelos centros geométricos das seções
    transversais de barras axialmente solicitadas que formam um nó devem, de preferência, se interceptar em um ponto
    comum"; decisão do usuário, 12/10, para os dois geradores de treliça — o do Posto é de_planta._nos_no_eixo_do_banzo).
    O desenho leva a alma até a face do banzo: no CD Bom Dia as pontas ficavam 22–25 mm fora do eixo e ~85 nós por
    tesoura com as barras chegando a pontos diferentes. Cada ponta de montante ou diagonal que chega num banzo vai, pela
    própria linha da barra, ao eixo dele; as pontas a menos de `unir` mm umas das outras no mesmo banzo viram um nó só —
    o do montante, quando há, senão o do meio. A barra quase paralela ao banzo (menos de 20°) não conta.
    `eixos`: {i: (u0, v0, u1, v1, meia)} o eixo de cada banzo e a meia largura dele no plano. Devolve (segs, pontas
    movidas, nós unidos)."""
    out = [list(x) for x in segs]
    pontas = []                                        # [j, ponta (0/1), banzo, ao longo do eixo, papel]
    for j, sg in enumerate(segs):
        if papeis[j] not in ("montante", "diagonal") or j in eixos:
            continue
        la = math.hypot(sg[2] - sg[0], sg[3] - sg[1])
        if la < 1.0:
            continue
        for k in (0, 1):
            ps, pv = (sg[0], sg[1]) if k == 0 else (sg[2], sg[3])
            ds, dv = ((sg[2] - sg[0]) / la, (sg[3] - sg[1]) / la) if k == 0 else ((sg[0] - sg[2]) / la, (sg[1] - sg[3]) / la)
            melhor = None
            for i, (b0, c0, b1, c1, meia) in eixos.items():
                lb = math.hypot(b1 - b0, c1 - c0)
                if lb < 1.0:
                    continue
                ts, tv = (b1 - b0) / lb, (c1 - c0) / lb
                tol = max(60.0, 1.5 * meia + 15.0)
                fora = abs((ps - b0) * tv - (pv - c0) * ts)
                ao = (ps - b0) * ts + (pv - c0) * tv
                if fora > tol or not (-tol <= ao <= lb + tol):
                    continue
                cruz = ds * tv - dv * ts
                if abs(cruz) < math.sin(math.radians(20.0)):
                    continue
                t = -((ps - b0) * tv - (pv - c0) * ts) / cruz
                ns, nv = ps + t * ds, pv + t * dv
                if math.hypot(ns - ps, nv - pv) > 2.0 * tol:
                    continue
                if melhor is None or fora < melhor[0]:
                    melhor = (fora, i, ns, nv, (ns - b0) * ts + (nv - c0) * tv)
            if melhor is not None:
                _f, i, ns, nv, ao = melhor
                out[j][2 * k], out[j][2 * k + 1] = ns, nv
                pontas.append([j, k, i, ao, papeis[j]])
    movidas = sum(1 for j, k, *_r in pontas if math.hypot(out[j][2 * k] - segs[j][2 * k], out[j][2 * k + 1] - segs[j][2 * k + 1]) > 0.5)
    # as pontas no mesmo banzo a menos de `unir` mm: um nó só (o grupo não passa de `unir` de ponta a ponta)
    unidos = 0
    for i, (b0, c0, b1, c1, _m) in eixos.items():
        lb = math.hypot(b1 - b0, c1 - c0) or 1.0
        ts, tv = (b1 - b0) / lb, (c1 - c0) / lb
        nesta = sorted((x for x in pontas if x[2] == i), key=lambda x: x[3])
        grupo: list = []
        for x in nesta + [None]:
            if x is not None and (not grupo or x[3] - grupo[0][3] <= unir):
                grupo.append(x)
                continue
            if len(grupo) > 1 and max(g[3] for g in grupo) - min(g[3] for g in grupo) > 0.5:
                mont = [g[3] for g in grupo if g[4] == "montante"]
                alvo = sum(mont) / len(mont) if mont else sum(g[3] for g in grupo) / len(grupo)
                for g in grupo:
                    out[g[0]][2 * g[1]], out[g[0]][2 * g[1] + 1] = b0 + alvo * ts, c0 + alvo * tv
                unidos += 1
            grupo = [x] if x is not None else []
    return [tuple(x) for x in out], movidas, unidos


def _giro_para(w: Tuple[float, float, float], alvo: Tuple[float, float, float]) -> float:
    """O giro (graus) da barra de direção `w` que leva o eixo local u da seção a `alvo` (geometria.base_local)."""
    from nucleo3d.geometria import base_local
    u0, v0, _ = base_local(w, 0.0)
    return math.degrees(math.atan2(sum(a * b for a, b in zip(alvo, v0)), sum(a * b for a, b in zip(alvo, u0)))) % 360.0


def _trelica(doc: Documento, e, a: dict, tab: Dict[str, float], camada: str, base: dict) -> int:
    """A tesoura de aço pelo desenho (web/cad/estrutura.js, tesouraPeloDesenho — pedido do usuário, 06/10): o elemento
    da planta é a linha do apoio ao apoio (de um eixo ao outro); `desenho.barras` são as barras do desenho da tesoura em
    linhas — [u0, v0, u1, v1, papel] em mm, u ao longo do vão (0 no apoio do começo) e v na altura (0 no apoio, o ponto mais baixo
    da tesoura; nas lançadas antes de 06/10 à noite, o banzo inferior).
    O vão do desenho é ajustado ao comprimento da linha da planta (o desenho e a planta diferem de um arredondamento) e o
    apoio (v = 0) fica no nível dado. Devolve quantas barras 3D.

    Regras de modelagem (usuário, 07/10, Docas):
    * o perfil desenhado em linha dupla (as duas faces) é um perfil só, no meio das duas linhas — antes a linha de dentro
      virava mais uma cantoneira; o trecho em linha dupla que continua o banzo (a ponta inclinada) é banzo, com o mesmo U;
    * o banzo em U fica sempre com a boca virada para o miolo da tesoura, qualquer que seja a posição em que foi lançado;
    * as cantoneiras (diagonais e montantes em linha simples) ficam sempre do mesmo lado do plano da tesoura — antes o lado
      dependia do sentido em que a linha foi desenhada; `cantoneira: "dupla"` põe uma em cada aba do U."""
    if not isinstance(e, Linha):
        raise ErroDeDados("a tesoura precisa da linha de um apoio ao outro")
    d = a.get("desenho") or {}
    barras = d.get("barras") or []
    vao = float(d.get("vao") or 0.0)
    L = math.dist(e.a, e.b)
    if not barras or vao <= 0 or L < 1:
        raise ErroDeDados("a tesoura não tem o desenho das barras")
    k = L / vao
    ux, uy = (e.b[0] - e.a[0]) / L, (e.b[1] - e.a[1]) / L
    fora_do_plano = (-uy, ux, 0.0)                       # a normal horizontal do plano da tesoura
    # o apoio no nível, ou acima dele (sobre a viga: o topo da viga — `acima_do_nivel` mm, 06/10)
    z0 = _nivel(a.get("nivel_base"), tab, 3000.0) + float(a.get("acima_do_nivel") or 0.0)
    perfis = a.get("perfis") or {}
    aco = str(a.get("aco") or "ASTM A572 Gr.50")
    marca = str(a.get("marca") or "")
    dupla = str(a.get("cantoneira") or "simples") == "dupla"
    nome_papel = {"banzo_sup": "banzo superior", "banzo_inf": "banzo inferior", "diagonal": "diagonal", "montante": "montante",
                  "extremidade": "montante de extremidade", "secundaria": "barra secundária"}

    def P(u, v):
        return (e.a[0] + ux * u * k, e.a[1] + uy * u * k, z0 + v)

    segs, papeis, perfis_b, secoes_b, vaos_b, virar_b, duplas_b = [], [], [], [], [], [], []
    for b in barras:
        try:
            segs.append(tuple(float(x) for x in b[:4]))
        except (TypeError, ValueError):
            continue
        # a cantoneira dupla desta barra pelo projeto (o "2L32x32" da lista de marcas, identificacao.desenho_da_tesoura)
        duplas_b.append(bool(len(b) > 9 and b[9]))
        papeis.append(str(b[4]) if len(b) > 4 else "diagonal")
        # o perfil da própria barra (a legenda de cores da folha de perfis do projeto, 11/10) e a seção dupla dela
        perfis_b.append(str(b[5]) if len(b) > 5 and b[5] else "")
        # "alma_no_plano" (a leitura do corte T1 do Hangar, 20–21/10) foi desfeita pelo usuário: o U simples segue a 2.2
        # e a 2.5 — a Montagem gravada com ela monta como banzo simples
        secoes_b.append(str(b[6]) if len(b) > 6 and b[6] and b[6] != "alma_no_plano" else "")
        # o painel "Perfis da tesoura" (11/10): o vão entre os dois perfis (mm; vazio = a altura da alma) e "virar" a boca
        try:
            vaos_b.append(float(b[7]) if len(b) > 7 and b[7] not in (None, "") else None)
        except (TypeError, ValueError):
            vaos_b.append(None)
        virar_b.append(bool(len(b) > 8 and b[8]))
    if not segs:
        raise ErroDeDados("a tesoura não tem o desenho das barras")
    pares = _linhas_duplas(segs)
    internas = {j for (j, _d, _n) in pares.values()}

    def toca(s, outro):
        return any(math.dist(p, q) < 2.0 for p in ((s[0], s[1]), (s[2], s[3])) for q in ((outro[0], outro[1]), (outro[2], outro[3])))

    # os nós da alma no eixo do banzo (NBR 8800:2024, 6.5.2 — usuário, 12/10): o eixo é a linha do banzo (no meio das
    # duas faces, no perfil em linha dupla) e a meia largura dele no plano diz até onde a ponta da alma ainda é dele
    def _meia_no_plano(i):
        if i in pares:
            return pares[i][1] / 2.0
        try:
            from nucleo3d.geometria import resolver_perfil
            pb = resolver_perfil(perfis_b[i] or perfis.get(papeis[i]) or perfis.get("banzo_sup") or perfis.get("banzo_inf"))
            if secoes_b[i] == "composto":
                return float(pb.d or 0.0) / 2.0
            if secoes_b[i] == "caixa":
                return float(pb.bf or 0.0)
            # o perfil da legenda do projeto em linha de centro: o projetista pode ter desenhado a faixa do banzo com a
            # altura toda (a T1 do Hangar: 127, a alma da alma parando a 63,5 do eixo) — a ponta a até meia altura também
            # é do banzo (3.2: < 100 mm vai ao eixo). Sem isso o par de cantoneiras a ±48 não chegava no banzo e a
            # treliça se partia em pedaços (21/10, a 2.5 sem os pares)
            if perfis_b[i]:
                return max(float(pb.d or 0.0), float(pb.bf or 0.0)) / 2.0
            return float(pb.bf or 0.0) * 0.5
        except Exception:                              # noqa: BLE001
            return 25.0
    eixos_bz = {}
    for i, sg in enumerate(segs):
        if i in internas or not (papeis[i].startswith("banzo") or papeis[i] == "extremidade" or i in pares):
            continue
        if i in pares:
            _j, dist_, (nx_, ny_) = pares[i]
            sg = (sg[0] + nx_ * dist_ / 2, sg[1] + ny_ * dist_ / 2, sg[2] + nx_ * dist_ / 2, sg[3] + ny_ * dist_ / 2)
        eixos_bz[i] = (sg[0], sg[1], sg[2], sg[3], _meia_no_plano(i))
    segs, _movidas, _unidos = _nos_no_eixo_do_banzo(segs, papeis, eixos_bz)
    # a seção e o perfil do banzo desta tesoura (2.9: o par de cantoneiras se posiciona pela alma do U)
    i_bz = [j for j in range(len(segs)) if papeis[j].startswith("banzo") and j not in internas]
    sec_banzo = next((secoes_b[j] for j in i_bz if secoes_b[j]), "")
    perfis_b_banzo = next((perfis_b[j] for j in i_bz if perfis_b[j]), "")
    vaos_b_banzo = next((vaos_b[j] for j in i_bz if vaos_b[j] is not None), None)
    perfil_banzo = perfis_b_banzo or perfis.get("banzo_sup") or perfis.get("banzo_inf")
    # 2.9, composto: o U que passa entre as almas (o montante U100 da T2 do Hangar) — o vão entre as almas é a altura dele
    # (os banzos encostados e soldados nos montantes — usuário, 21/10: "os perfis dos banzos ficaram afastados dos
    # montantes") e a ponta em U só é desse perfil (2.9a). Sem U na alma, a altura do banzo (a ponta do banzo cabe)
    perfil_ponta, vao_composto = perfil_banzo, None
    if sec_banzo == "composto":
        try:
            from nucleo3d.geometria import resolver_perfil
            from nucleo3d.regras_trelica import forma as _forma
            us_alma = [perfis_b[j] or perfis.get(papeis[j]) or perfis.get("montante") or perfis.get("diagonal") or ""
                       for j in range(len(segs)) if j not in internas
                       and not (papeis[j].startswith("banzo") or papeis[j] == "extremidade")]
            us_alma = [p_ for p_ in us_alma if _forma(p_) == "U"]
            if us_alma:
                perfil_ponta = max(us_alma, key=lambda p_: float(resolver_perfil(p_).d or 0.0))
                vao_composto = float(resolver_perfil(perfil_ponta).d or 0.0) or None
            else:
                vao_composto = float(resolver_perfil(perfil_banzo).d or 0.0) or None
        except Exception:                              # noqa: BLE001
            perfil_ponta, vao_composto = perfil_banzo, None
    # o U simples deitado (2.2) num desenho com a faixa do banzo na altura toda (a T1/T3 do Hangar, 21/10): senta na chapa
    # e o topo fica onde o projetista desenhou (as terças apoiam nele) — os banzos se afastam (d/2 − xg) cada um
    if not sec_banzo and perfis_b_banzo:
        _sentar_u_simples(segs, papeis, internas, perfil_banzo, float(a.get("acima_do_nivel") or 0.0))
    # 2.9a: o trecho a 45° do painel de ponta — o trecho de banzo curto e inclinado que nasce no topo do montante de
    # extremidade (a T2-B4 do Hangar, 283 mm a 45°); o banzo de verdade é comprido
    chanfros = set()
    if sec_banzo == "composto" or (not sec_banzo and perfis_b_banzo):
        alt_d = float(d.get("altura") or 0.0) or max((max(s[1], s[3]) for s in segs), default=0.0)
        topos = [(s[0], s[1]) if s[1] > s[3] else (s[2], s[3]) for j, s in enumerate(segs) if papeis[j] == "extremidade"]
        for j, s in enumerate(segs):
            if not papeis[j].startswith("banzo") or j in internas:
                continue
            L_s = math.hypot(s[2] - s[0], s[3] - s[1])
            if L_s < 1.0 or L_s > 1.2 * alt_d:
                continue
            ang = math.degrees(math.atan2(abs(s[3] - s[1]), abs(s[2] - s[0])))
            if 20.0 <= ang <= 70.0 and any(min(math.dist(tp, (s[0], s[1])), math.dist(tp, (s[2], s[3]))) < 2.0 for tp in topos):
                chanfros.add(j)
        _ponta_no_final(segs, papeis, chanfros, internas, perfil_banzo, composto=sec_banzo == "composto",
                        perfil_ponta=perfil_ponta)
    sup = [segs[i] for i in pares if papeis[i] == "banzo_sup"]
    # a alma em linha simples: as barras que dizem de que lado fica o miolo de cada banzo (a regra da boca do U)
    alma = [segs[i] for i in range(len(segs)) if i not in pares and i not in internas
            and not (papeis[i].startswith("banzo") or papeis[i] == "extremidade")]
    # para o montante de ponta também os banzos que saem dele: vão para a tesoura dele (no apoio de B do CD Bom Dia
    # nenhuma diagonal chega ao montante de ponta da TC1, só os banzos)
    banzos = [(i, segs[i]) for i in range(len(segs)) if i not in internas and (papeis[i].startswith("banzo") or i in pares)]
    # o vão entre os dois U do banzo composto: a altura (d) do perfil mais usado na alma desta tesoura
    try:
        from nucleo3d.geometria import resolver_perfil
        alma_p = collections.Counter(perfis_b[j] or perfis.get("diagonal") or "" for j in range(len(segs))
                                     if not (papeis[j].startswith("banzo") or papeis[j] == "extremidade")).most_common(1)
        vao_da_alma = float(resolver_perfil(alma_p[0][0]).d or CHAPA_COMPOSTO) if alma_p and alma_p[0][0] else CHAPA_COMPOSTO
    except Exception:                                  # noqa: BLE001
        vao_da_alma = CHAPA_COMPOSTO
    pontas_u: List[Tuple[int, Barra]] = []            # as peças da ponta em U só (2.9a): a meia-esquadria entre elas
    quadro_u: List[Tuple[int, Barra]] = []            # o U simples da legenda: o quadro da ponta em meia-esquadria
    n = 0
    feitas: List[Barra] = []                           # as barras desta tesoura (o encaixe é por tesoura)
    secundarias: List[Tuple[Barra, tuple]] = []        # as de um lado só, por fora do U: cortadas na face do banzo
    perfis_u: Dict[int, Barra] = {}
    for i, s in enumerate(segs):
        if i in internas:
            continue                                   # a outra face do perfil em linha dupla
        papel = papeis[i]
        perfil_u = None
        if i in pares:
            # perfil em linha dupla: o U. O que não veio marcado como banzo é a ponta da tesoura: a inclinada que continua
            # o banzo é banzo (o mesmo U); a de pé é o montante de extremidade, também em U
            if not papel.startswith("banzo"):
                de_pe = abs(s[2] - s[0]) < 0.2 * math.hypot(s[2] - s[0], s[3] - s[1])
                papel = "extremidade" if de_pe else ("banzo_sup" if any(toca(s, o) for o in sup) or not perfis.get("banzo_inf") else "banzo_inf")
            perfil_u = perfis.get(papel) or perfis.get("banzo_sup") or perfis.get("banzo_inf")
        perfil = perfil_u or perfis.get(papel) or perfis.get("diagonal" if papel in ("montante", "secundaria") else papel) or "L 50,8×4,76"
        if perfis_b[i]:
            perfil = perfis_b[i]
        u0, v0, u1, v1 = s
        if i in pares:                                 # no meio das duas faces
            _j, dist, (nx, ny) = pares[i]
            u0, v0, u1, v1 = u0 + nx * dist / 2, v0 + ny * dist / 2, u1 + nx * dist / 2, v1 + ny * dist / 2
        A, B = P(u0, v0), P(u1, v1)
        if math.dist(A, B) < 5.0:
            continue
        w = tuple((B[c] - A[c]) / math.dist(A, B) for c in range(3))
        atr = dict(base, origem={"peca": marca}, papel_trelica=papel,
                   **({"calandrar_raio": d.get("raio_banzo_sup")} if papel == "banzo_sup" and d.get("raio_banzo_sup") else {}),
                   **({"boca_virada": True} if virar_b[i] else {}),
                   **({"perfil_do_projeto": True} if perfis_b[i] else {}))   # a legenda manda (regime 0.1)
        # a ponta em U conta como banzo: as cantoneiras encaixam nela, e ela não é recortada como alma
        papel_3d = "banzo" if (papel.startswith("banzo") or papel == "extremidade") else ("diagonal" if papel == "secundaria" else papel)
        nome = "%s %s %d" % (marca, nome_papel.get(papel, papel), i + 1)
        if secoes_b[i] in ("caixa", "composto"):
            # a seção dupla da legenda do projeto (CD Bom Dia, croqui ao lado de "BANZOS", 11/10):
            # "COMPOSTO" = dois U de costas, a boca de cada um para fora do plano, afastados pela altura do perfil da alma
            # (a alma entra entre eles: Ue 100 composto com 127 entre as almas, para a alma em Ue 127);
            # "DUPLO (CAIXA)" = dois U de boca um para o outro, lado a lado no plano da tesoura (o caixão do Posto), a
            # altura atravessando o plano
            try:
                from nucleo3d.geometria import resolver_perfil, secao
                pd_ = resolver_perfil(perfil)
                xg = -min(q[0] for q in secao(pd_))            # da alma ao centroide (a boca abre para +u)
                bf = float(pd_.bf or 0.0)
                d_u = float(pd_.d or 0.0)
            except Exception:                                  # noqa: BLE001
                xg, bf, d_u = 15.0, 50.0, 0.0
            caixa = secoes_b[i] == "caixa"
            ls_ = math.hypot(u1 - u0, v1 - v0) or 1.0
            n_pl = (ux * (-(v1 - v0) / ls_) * k, uy * (-(v1 - v0) / ls_) * k, (u1 - u0) / ls_)     # a normal no plano
            dw_ = sum(a_ * b_ for a_, b_ in zip(n_pl, w))
            n_pl = tuple(a_ - dw_ * b_ for a_, b_ in zip(n_pl, w))
            nn_ = math.sqrt(sum(a_ * a_ for a_ in n_pl)) or 1.0
            n_pl = tuple(a_ / nn_ for a_ in n_pl)
            if not caixa and (papel == "extremidade" or i in chanfros):
                # 2.9a (regras_trelica; usuário, 21/10, a T2 do Hangar montada à mão): a ponta do composto é UM U só, no
                # plano, encaixado entre as almas dos dois U — do perfil que passa entre elas (o montante U100: "ponta
                # em U100 entre as almas"; sem U na alma, o do banzo) —, a altura atravessa o plano (as abas soldam nas
                # almas), a alma para fora, a boca no plano para o vão (o montante para o meio, o 45° para baixo); o
                # montante nasce no nível de apoio (sentado na chapa, como o fundo dos banzos)
                perfil = perfil_ponta or perfil
                nx2, ny2 = -(v1 - v0) / ls_, (u1 - u0) / ls_              # a perpendicular no plano, em 2D
                if papel == "extremidade":
                    if (vao / 2.0 - (u0 + u1) / 2.0) * nx2 < 0:
                        nx2, ny2 = -nx2, -ny2
                    if v0 < v1:
                        A = P(u0, v0 - d_u / 2.0)
                    else:
                        B = P(u1, v1 - d_u / 2.0)
                    w = tuple((B[c] - A[c]) / math.dist(A, B) for c in range(3))
                elif ny2 > 0:
                    nx2, ny2 = -nx2, -ny2
                boca = (ux * nx2 * k, uy * nx2 * k, ny2)
                dwb = sum(a_ * b_ for a_, b_ in zip(boca, w))
                boca = tuple(a_ - dwb * b_ for a_, b_ in zip(boca, w))
                bp = Barra(inicio=A, fim=B, perfil=perfil, papel=papel_3d, aco=aco, camada=camada, nome=nome,
                           rotacao=_giro_para(w, boca), atributos=dict(atr, secao_dupla="composto", ponta_composto=True))
                doc.add(bp)
                feitas.append(bp)
                pontas_u.append((i, bp))
                n += 1
                continue
            direcao = n_pl if caixa else fora_do_plano
            # o vão entre as almas: o dado no painel; senão a altura do U que passa entre elas (os banzos encostados no
            # montante: CD Bom Dia, alma Ue 127 em banzo Ue 100; Hangar, U100 em 2U127)
            off = (bf - xg) if caixa else (xg + (vaos_b[i] if vaos_b[i] is not None else (vao_composto or max(vao_da_alma, d_u))) / 2.0)
            for lado in (1.0, -1.0):
                dl = tuple(lado * off * c for c in direcao)
                abre = tuple((-lado if caixa else lado) * (-1.0 if virar_b[i] else 1.0) * c for c in direcao)
                bd = Barra(inicio=tuple(A[c] + dl[c] for c in range(3)), fim=tuple(B[c] + dl[c] for c in range(3)), perfil=perfil,
                           papel=papel_3d, aco=aco, camada=camada, nome=nome + (" (a)" if lado > 0 else " (b)"), rotacao=_giro_para(w, abre),
                           atributos=dict(atr, secao_dupla=secoes_b[i], a_confirmar="seção dupla: arranjo dos dois perfis"))
                doc.add(bd)
                feitas.append(bd)
                n += 1
            continue
        banzo_simples = i not in pares and (papel.startswith("banzo") or papel == "extremidade")
        if i in pares or banzo_simples:
            # a boca do U para o miolo: o eixo u da seção (para onde o U abre) na normal para dentro, no plano da tesoura.
            # O banzo em linha de centro (o esqueleto do leitor do desenho detalhado, Montagem por eixos — 11/10) também:
            # o de cima abre para baixo, o de baixo para cima e o trecho em pé para o meio do vão; antes ele ia pela regra
            # da cantoneira e ficava com a boca para fora do plano (o CD Bom Dia: 24 de 26 trechos do banzo de cima)
            # o miolo: o lado de onde chegam as barras da alma ligadas a este perfil; sem ligação, o par desenhado diz
            # (a face de fora é a mais longe do meio do desenho) e, em linha de centro, o de cima abre para baixo, o
            # de baixo para cima e o em pé para o meio do vão
            cu0, cv0, cu1, cv1 = u0, v0, u1, v1
            ls = math.hypot(cu1 - cu0, cv1 - cv0) or 1.0
            nx, ny = -(cv1 - cv0) / ls, (cu1 - cu0) / ls
            tol_lig = (pares[i][1] / 2.0 + 60.0) if i in pares else 80.0
            em_pe = papel == "extremidade" or abs(ny) < 0.3
            mais, menos = _ligadas_dos_lados((cu0, cv0, cu1, cv1), (nx, ny), alma, tol_lig)
            if em_pe and mais and menos:
                # o montante em U no meio da tesoura (alma ligada dos dois lados — a TF1 dos oitões, nos pilares): a boca
                # para o meio do vão desta tesoura (decisão do usuário, 11/10)
                lado = 1 if (vao / 2.0 - (cu0 + cu1) / 2.0) * nx > 0 else -1
            else:
                lado = (mais > menos) - (mais < menos)
            if not lado and em_pe:
                lado = _lado_das_ligadas((cu0, cv0, cu1, cv1), (nx, ny), [b for j, b in banzos if j != i], tol_lig + 80.0)
            if lado:
                nx, ny = nx * lado, ny * lado
            elif i in pares:
                nx, ny = pares[i][2]
            elif papel == "extremidade" or abs(ny) < 0.3:
                if (vao / 2.0 - (s[0] + s[2]) / 2.0) * nx < 0:
                    nx, ny = -nx, -ny
            elif (papel == "banzo_inf") != (ny > 0):
                nx, ny = -nx, -ny
            if virar_b[i]:
                nx, ny = -nx, -ny
            dentro = (ux * nx * k, uy * nx * k, ny)
            dw = sum(x * y for x, y in zip(dentro, w))
            dentro = tuple(x - dw * y for x, y in zip(dentro, w))
            bu = Barra(inicio=A, fim=B, perfil=perfil, papel=papel_3d, aco=aco, camada=camada, nome=nome,
                       rotacao=_giro_para(w, dentro), atributos=atr)
            doc.add(bu)
            feitas.append(bu)
            if i in pares:                             # o canto em meia-esquadria é o das faces desenhadas
                perfis_u[i] = bu
            elif chanfros and not sec_banzo:           # o U simples da legenda: o quadro da ponta (2.9a)
                quadro_u.append((i, bu))
            n += 1
            continue
        # cantoneira: a aba deitada sempre do mesmo lado do plano (giro pela normal do plano, não pelo sentido da linha)
        giro = _giro_para(w, fora_do_plano)
        if re.match(r"(?i)^\s*Ue?\s", perfil) and papel != "secundaria":
            # a alma em U ou Ue: a altura do perfil atravessa o plano (entra entre os dois U do banzo composto, ou na boca
            # do banzo — CD Bom Dia, 11/10); a boca no plano, para cima (a em pé, para o meio do vão: regras_trelica T3/T4)
            ls_ = math.hypot(u1 - u0, v1 - v0) or 1.0
            nx_, ny_ = -(v1 - v0) / ls_, (u1 - u0) / ls_
            if ny_ < -0.3 or (abs(ny_) <= 0.3 and nx_ < 0):
                nx_, ny_ = -nx_, -ny_
            alvo = (ux * nx_ * k, uy * nx_ * k, ny_)
            dw_ = sum(a_ * b_ for a_, b_ in zip(alvo, w))
            giro = _giro_para(w, tuple(a_ - dw_ * b_ for a_, b_ in zip(alvo, w)))
        if virar_b[i]:
            giro = (giro + 180.0) % 360.0
        if papel == "secundaria":
            # a barra secundária ("L22x22#11 - Um lado só", Docas 08/10): uma cantoneira só, numa face da tesoura, por fora
            # das abas do U — a aba deitada encostada na aba do U e a outra para fora; passa por fora das cantoneiras
            try:
                from nucleo3d.geometria import resolver_perfil
                pu = resolver_perfil(perfis.get("banzo_sup") or perfis.get("banzo_inf"))
                pl = resolver_perfil(perfil)
                fora = float(pu.d or 0.0) / 2.0 + float(pl.bf or 0.0) / 2.0
            except Exception:                          # noqa: BLE001
                fora = 0.0
            dl = tuple(fora * c for c in fora_do_plano)
            bl = Barra(inicio=tuple(A[c] + dl[c] for c in range(3)), fim=tuple(B[c] + dl[c] for c in range(3)), perfil=perfil,
                       papel=papel_3d, aco=aco, camada=camada, nome=nome, rotacao=giro, atributos=dict(atr, um_lado_so=True))
            doc.add(bl)
            secundarias.append((bl, s))
            n += 1
            continue
        if not (dupla or duplas_b[i]):
            bl = Barra(inicio=A, fim=B, perfil=perfil, papel=papel_3d, aco=aco, camada=camada, nome=nome,
                       rotacao=giro, atributos=atr)
            doc.add(bl)
            feitas.append(bl)
            n += 1
            continue
        # dupla: uma em cada aba do U, encostada na face de dentro da aba; a segunda é a primeira espelhada no plano
        # (na cantoneira de abas iguais, espelhar é girar 90°)
        abraca = sec_banzo == "composto"
        try:
            from nucleo3d.geometria import resolver_perfil, secao
            pu = resolver_perfil(perfis_b_banzo or perfis.get("banzo_sup") or perfis.get("banzo_inf"))
            pl = resolver_perfil(perfil)
            if abraca:
                # 2.9: o par por dentro dos perfis — no vão entre as almas dos dois U, as costas da aba deitada na face
                # de dentro de cada alma (cada uma a vão/2 do plano), a aba que atravessa o plano para o centro (usuário,
                # 21/10: "essas cantoneiras precisam seguir o mesmo modelo das que ajustei manualmente, por dentro dos
                # perfis" — antes ia uma dentro de cada boca)
                xl = -min(q[0] for q in secao(pl))
                vao_u = (vaos_b_banzo if vaos_b_banzo is not None else (vao_composto or max(vao_da_alma, float(pu.d or 0.0))))
                afast = vao_u / 2.0 - xl
            else:
                # 2.5: o U simples com a boca para dentro do vão — uma em cada aba do U, encostada na face de dentro da aba
                afast = max(float(pu.d or 0.0) / 2.0 - float(pu.tf or pu.tw or 0.0) - float(pl.bf or 0.0) / 2.0, 0.0)
        except Exception:                              # noqa: BLE001 — sem as medidas, encostadas no plano
            afast = 0.0
        par_ids = []
        for lado, g in ((-1.0, giro), (1.0, giro + 90.0)):
            dl = tuple(lado * afast * c for c in fora_do_plano)
            bl = Barra(inicio=tuple(A[c] + dl[c] for c in range(3)), fim=tuple(B[c] + dl[c] for c in range(3)), perfil=perfil,
                       papel=papel_3d, aco=aco, camada=camada, nome=nome + (" (a)" if lado < 0 else " (b)"), rotacao=g % 360.0,
                       atributos=dict(atr, cantoneira_dupla="a" if lado < 0 else "b"))
            doc.add(bl)
            feitas.append(bl)
            par_ids.append(bl.id)
            n += 1
        # as presilhas que ligam as duas cantoneiras (NBR 8800:2024, 5.3.6.1 — usuário, 12/10): igualmente espaçadas entre
        # os nós, atravessando o par; a quantidade da nota do projeto (`presilhas` do tipo: {qtd, perfil}), nunca abaixo
        # do mínimo da norma (de_planta._presilhas_pela_norma, a mesma conta do Posto)
        from nucleo3d.de_planta import _presilhas_pela_norma
        nota_p = a.get("presilhas") or {}
        n_p = 0 if abraca else max(int(nota_p.get("qtd") or 0), _presilhas_pela_norma(perfil))   # 2.9: a alma do U liga o par
        try:
            larg = 2.0 * afast + float(pl.bf or 0.0)
        except Exception:                              # noqa: BLE001
            larg = 2.0 * afast + 25.0
        for k_p in range(1, n_p + 1):
            f = k_p / (n_p + 1.0)
            cq = tuple(A[c] + (B[c] - A[c]) * f for c in range(3))
            # a estação é daqui; o lugar e o giro são da regra 3.3 (regras_trelica.aplicar, logo abaixo): a aba nas abas
            # de dentro do par, ao longo da barra, de uma aba deitada à outra — antes ia de fora a fora, com giro 0
            # (atravessava as cantoneiras e não seguia a inclinação da diagonal: o Hangar, 21/10)
            pres = Barra(inicio=tuple(cq[c] - fora_do_plano[c] * larg / 2.0 for c in range(3)),
                         fim=tuple(cq[c] + fora_do_plano[c] * larg / 2.0 for c in range(3)), perfil=nota_p.get("perfil") or perfil,
                         papel="presilha", aco=aco, camada=camada, nome="%s presilha %d.%d" % (marca, i + 1, k_p), rotacao=0.0,
                         atributos=dict(atr, presilha_de=perfil, papel_trelica="presilha", presilha_par=list(par_ids)))
            doc.add(pres)
            feitas.append(pres)
            n += 1
    # as regras de posição das peças da treliça (nucleo3d/regras_trelica, 16/10 — uma regra só para todo gerador): o que
    # o desenho deixou em outra posição é girado aqui, antes dos cantos e do encaixe (que dependem do giro)
    from nucleo3d import regras_trelica
    regras_trelica.aplicar(feitas, por_grupo=False)
    _cantos_em_meia_esquadria(segs, pares, perfis_u, P, fora_do_plano)
    _meia_esquadria_da_ponta(pontas_u)
    _meia_esquadria_da_ponta(quadro_u, so_com={id(b) for i_, b in quadro_u if papeis[i_] == "extremidade" or i_ in chanfros})
    # o encaixe de fábrica (nucleo3d/alma_na_face, o mesmo do 3D pelos quadros): a cantoneira entra na boca do U e para
    # na alma dele, cortada no ângulo; o bico no montante e a bissetriz entre diagonais. Antes a ponta da cantoneira
    # ficava na linha de fora do banzo e atravessava o perfil (o usuário, 08/10: "peças cortando os banzos")
    from nucleo3d import alma_na_face
    alma_na_face.encaixar(feitas)
    # a secundária fica fora da faixa do U (o encaixe não a acha): a ponta que chega num banzo é cortada rente à face de
    # fora dele (a linha de fora do desenho), no ângulo
    for bl, s in secundarias:
        for k, ponta in ((0, (s[0], s[1])), (1, (s[2], s[3]))):
            planos = []                                # no canto, as faces dos dois perfis (o bico)
            for i, (j, _dist, (nx, ny)) in pares.items():
                o = segs[i]
                lo = math.hypot(o[2] - o[0], o[3] - o[1])
                if lo < 1:
                    continue
                # a ponta na linha de fora do perfil (a até 2 mm, dentro do comprimento dele)
                fora_da_linha = abs((ponta[0] - o[0]) * (o[3] - o[1]) - (ponta[1] - o[1]) * (o[2] - o[0])) / lo
                ao_longo = ((ponta[0] - o[0]) * (o[2] - o[0]) + (ponta[1] - o[1]) * (o[3] - o[1])) / lo
                if fora_da_linha > 2.0 or not (-2.0 <= ao_longo <= lo + 2.0):
                    continue
                nrm = (ux * nx * k, uy * nx * k, ny)
                no = bl.inicio if k == 0 else bl.fim
                base3 = P(*ponta)
                # o ponto relativo ao nó da ponta: a face está na linha de fora (o plano contém a normal do plano da tesoura,
                # então a barra deslocada para fora dele é cortada no mesmo plano)
                planos.append({"normal": [round(c, 9) for c in nrm], "ponto": [round(base3[c] - no[c], 4) for c in range(3)]})
            if planos and k == 0:
                bl.cortes_inicio = planos
            elif planos:
                bl.cortes_fim = planos
    return n


def _dist_seg_2d(p, a, b) -> float:
    ab = (b[0] - a[0], b[1] - a[1])
    L2 = ab[0] * ab[0] + ab[1] * ab[1]
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / L2))
    return math.dist(p, (a[0] + ab[0] * t, a[1] + ab[1] * t))


def _sentar_u_simples(segs: list, papeis: List[str], internas: set, perfil_banzo: Optional[str], acima: float) -> float:
    """O U simples deitado (2.2, a boca para dentro do vão) num desenho em que o projetista desenhou a faixa do banzo com
    a altura toda do perfil (a T1/T3 do Hangar: 127, o fundo da faixa no apoio — `acima_do_nivel` = d/2): no 3D o U
    deitado tem só a aba no plano, e a tesoura ficava 51 mm acima do apoio e com o topo 51 mm abaixo das terças (21/10,
    o usuário: "sentar na chapa" e "aumentar a altura da tesoura"). O banzo inferior desce e o superior (com o 45°) sobe
    (d/2 − xg): o fundo do U de baixo no apoio e o topo do U de cima onde o desenho tem a face de cima. Os nós da alma
    em cada banzo andam com ele. Muda `segs` no lugar; devolve o quanto cada banzo andou (0 = desenho não é desse jeito)."""
    try:
        from nucleo3d.geometria import resolver_perfil, secao
        pb = resolver_perfil(perfil_banzo)
        xg = -min(q[0] for q in secao(pb))
        d_b = float(pb.d or 0.0)
    except Exception:                                    # noqa: BLE001
        return 0.0
    if not d_b or abs(acima - d_b / 2.0) > 2.0:
        return 0.0                                       # o fundo da faixa desenhada não está no apoio: fica como está
    delta = d_b / 2.0 - xg
    if delta < 0.5:
        return 0.0
    linhas = {"banzo_inf": [], "banzo_sup": []}
    for j, s in enumerate(segs):
        if j in internas:
            continue
        for k in linhas:
            if papeis[j].startswith(k):
                linhas[k].append(((s[0], s[1]), (s[2], s[3])))

    def novo(p):
        if any(_dist_seg_2d(p, a_, b_) < 1.0 for a_, b_ in linhas["banzo_inf"]):
            return (p[0], p[1] - delta)
        if any(_dist_seg_2d(p, a_, b_) < 1.0 for a_, b_ in linhas["banzo_sup"]):
            return (p[0], p[1] + delta)
        return p
    for j, s in enumerate(segs):
        a_, b_ = novo((s[0], s[1])), novo((s[2], s[3]))
        segs[j] = (a_[0], a_[1], b_[0], b_[1])
    return delta


def _ponta_no_final(segs: list, papeis: List[str], chanfros: set, internas: set, perfil_banzo: Optional[str],
                    composto: bool = True, perfil_ponta: Optional[str] = None) -> int:
    """2.9a: a ponta alinhada com o final da tesoura — a face de fora da alma do montante de extremidade no fim do banzo
    inferior (usuário, 21/10: "alinhar com o final da tesoura"). O desenho do projeto põe o eixo da ponta a meia altura
    do perfil da face (63,5 no U 127 do Hangar) e a ponta ficava 51 mm para dentro. O montante de extremidade, o trecho
    a 45° preso nele e o que chega nos nós deles andam juntos ao longo do vão; o banzo superior vai até o 45° pela
    própria linha. No composto o 45° (o U central, entre as almas) sobe pelo próprio eixo até a face de fora dele encostar
    na face de cima do banzo superior; no U simples (o quadro da ponta, a T1 do Hangar montada à mão em 21/10) o banzo
    inferior termina no eixo do montante — os cantos são em meia-esquadria (_meia_esquadria_da_ponta). `perfil_ponta`:
    o da ponta quando não é o do banzo (o U100 entre as almas do composto). Muda `segs` (no lugar); devolve quantas
    pontas andaram."""
    try:
        from nucleo3d.geometria import resolver_perfil, secao
        pb = resolver_perfil(perfil_banzo)
        d_b = float(pb.d or 0.0)
        xg = -min(q[0] for q in secao(resolver_perfil(perfil_ponta or perfil_banzo)))   # da face de fora ao eixo da ponta
    except Exception:                                    # noqa: BLE001 — sem o perfil, a ponta fica onde o desenho pôs
        return 0
    us_bi = [u for j, s in enumerate(segs) if papeis[j] == "banzo_inf" and j not in internas for u in (s[0], s[2])]
    if not us_bi:
        return 0
    lo, hi = min(us_bi), max(us_bi)
    andou = 0
    for j, s in enumerate(list(segs)):
        if papeis[j] != "extremidade" or j in internas or abs(s[2] - s[0]) > 1.0:
            continue
        u = s[0]
        if 0.0 < u - lo <= d_b:
            delta = (lo + xg) - u
        elif 0.0 < hi - u <= d_b:
            delta = (hi - xg) - u
        else:
            continue
        if abs(delta) < 0.5:
            continue
        nos = {(s[0], s[1]), (s[2], s[3])}             # os nós que andam: os da ponta e o de cima do 45° preso nela
        for c in chanfros:
            sc = segs[c]
            if any(math.dist(p, q) < 2.0 for p in nos for q in ((sc[0], sc[1]), (sc[2], sc[3]))):
                nos |= {(sc[0], sc[1]), (sc[2], sc[3])}
        # o nó de cima do 45° fica na linha do banzo superior: anda ao longo dela (o banzo vai até ele)
        def novo(p):
            for k, sb in enumerate(segs):
                if not papeis[k].startswith("banzo_sup") or k in chanfros or k in internas:
                    continue
                for a_, b_ in (((sb[0], sb[1]), (sb[2], sb[3])), ((sb[2], sb[3]), (sb[0], sb[1]))):
                    if math.dist(a_, p) < 2.0 and abs(b_[0] - a_[0]) > 1.0:
                        incl = (b_[1] - a_[1]) / (b_[0] - a_[0])
                        return (p[0] + delta, p[1] + delta * incl)
            return (p[0] + delta, p[1])
        mapa = {p: novo(p) for p in nos}
        if not composto:
            # o U simples: o banzo inferior termina no eixo do montante (o canto em meia-esquadria)
            u_fim = lo if u - lo <= d_b else hi
            for k, sk in enumerate(segs):
                if papeis[k] == "banzo_inf" and k not in internas:
                    for p in ((sk[0], sk[1]), (sk[2], sk[3])):
                        if abs(p[0] - u_fim) < 1.0:
                            mapa[p] = (u + delta, p[1])
        for k, sk in enumerate(segs):
            pa, pb_ = (sk[0], sk[1]), (sk[2], sk[3])
            na = next((mapa[q] for q in mapa if math.dist(q, pa) < 2.0), pa)
            nb = next((mapa[q] for q in mapa if math.dist(q, pb_) < 2.0), pb_)
            if na != pa or nb != pb_:
                segs[k] = (na[0], na[1], nb[0], nb[1])
        if composto:
            topo = (s[0] + delta, max(s[1], s[3]))
            for c in chanfros:
                _chanfro_ate_o_topo(segs, c, topo, papeis, chanfros, internas, xg, d_b)
        andou += 1
    return andou


def _chanfro_ate_o_topo(segs: list, c: int, canto: Tuple[float, float], papeis: List[str], chanfros: set, internas: set,
                        xg: float, d_b: float) -> None:
    """2.9a, composto: o 45° preso no canto `canto` sobe pelo próprio eixo até a face de fora dele (a alma, do lado de
    cima) encostar na face de cima do banzo superior — passa entre as almas dos dois U (usuário, 21/10, a T2 do Hangar)"""
    sc = segs[c]
    pa, pb_ = (sc[0], sc[1]), (sc[2], sc[3])
    if math.dist(pa, canto) < 2.0:
        p0, p1, fim_e_b = pa, pb_, True
    elif math.dist(pb_, canto) < 2.0:
        p0, p1, fim_e_b = pb_, pa, False
    else:
        return
    L = math.dist(p0, p1)
    if L < 1.0:
        return
    dr = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
    nc = (-dr[1], dr[0]) if dr[0] >= 0 else (dr[1], -dr[0])       # a perpendicular para cima (o lado da alma)
    if nc[1] < 0:
        nc = (-nc[0], -nc[1])
    # o banzo superior que nasce no topo do 45°
    for k, sb in enumerate(segs):
        if not papeis[k].startswith("banzo_sup") or k in chanfros or k in internas:
            continue
        for b0, b1 in (((sb[0], sb[1]), (sb[2], sb[3])), ((sb[2], sb[3]), (sb[0], sb[1]))):
            if math.dist(b0, p1) >= 2.0:
                continue
            Lb = math.dist(b0, b1)
            if Lb < 1.0:
                continue
            bd = ((b1[0] - b0[0]) / Lb, (b1[1] - b0[1]) / Lb)
            nb = (-bd[1], bd[0]) if bd[0] >= 0 else (bd[1], -bd[0])
            if nb[1] < 0:
                nb = (-nb[0], -nb[1])
            den = dr[0] * nb[0] + dr[1] * nb[1]
            if abs(den) < 1e-6:
                return
            q = (p1[0] + xg * nc[0] - b0[0], p1[1] + xg * nc[1] - b0[1])
            t = (d_b / 2.0 - (q[0] * nb[0] + q[1] * nb[1])) / den
            novo = (p1[0] + t * dr[0], p1[1] + t * dr[1])
            segs[c] = (p0[0], p0[1], novo[0], novo[1]) if fim_e_b else (novo[0], novo[1], p0[0], p0[1])
            return


def _meia_esquadria_da_ponta(pontas_u: List[Tuple[int, Barra]], so_com: Optional[set] = None) -> int:
    """2.9a: as peças da ponta que se encontram num nó se cortam na bissetriz — o plano do canto, como o usuário montou
    à mão no Hangar (21/10): no composto o montante de extremidade e o 45° (o U central); no U simples o quadro da ponta
    — banzo inferior × montante, montante × 45°, 45° × banzo superior. A normal de cada corte é a bissetriz das duas
    direções (saindo do nó), apontando para dentro da própria peça. `so_com`: só os encontros em que uma das peças é
    destas (ids) — o banzo com o banzo na cumeeira não. Devolve quantos cortes."""
    n = 0
    for a_, (_i, pa) in enumerate(pontas_u):
        for _j, pb in pontas_u[a_ + 1:]:
            if so_com is not None and id(pa) not in so_com and id(pb) not in so_com:
                continue
            for ka, qa in ((0, pa.inicio), (1, pa.fim)):
                for kb, qb in ((0, pb.inicio), (1, pb.fim)):
                    if math.dist(qa, qb) > 2.0:
                        continue
                    # as direções saindo do nó
                    da = tuple((pa.fim[c] - pa.inicio[c]) if ka == 0 else (pa.inicio[c] - pa.fim[c]) for c in range(3))
                    db = tuple((pb.fim[c] - pb.inicio[c]) if kb == 0 else (pb.inicio[c] - pb.fim[c]) for c in range(3))
                    la, lb = math.dist((0, 0, 0), da) or 1.0, math.dist((0, 0, 0), db) or 1.0
                    da, db = tuple(x / la for x in da), tuple(x / lb for x in db)
                    nb = tuple(db[c] - da[c] for c in range(3))
                    ln = math.dist((0, 0, 0), nb)
                    if ln < 1e-6:
                        continue
                    nb = tuple(x / ln for x in nb)
                    for peca, k, dd in ((pa, ka, da), (pb, kb, db)):
                        nrm = nb if sum(x * y for x, y in zip(nb, dd)) > 0 else tuple(-x for x in nb)
                        corte = [{"normal": [round(c, 9) for c in nrm], "ponto": [0.0, 0.0, 0.0]}]
                        if k == 0:
                            peca.cortes_inicio = corte
                        else:
                            peca.cortes_fim = corte
                        n += 1
    return n


def _cantos_em_meia_esquadria(segs, pares, perfis_u: Dict[int, Barra], P, fora_do_plano) -> int:
    """Os perfis em linha dupla que se encontram num canto (o banzo e a ponta, os dois trechos do banzo de cima) se
    cortam em meia-esquadria: o plano do canto de fora (as linhas de fora se encontram) ao de dentro (o cruzamento das
    linhas de dentro), em pé no plano da tesoura. Antes um U atravessava o outro no canto. Devolve quantos cortes."""
    def cruza(p1, p2, p3, p4):
        d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0])
        if abs(d) < 1e-9:
            return None
        t_ = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d
        return (p1[0] + t_ * (p2[0] - p1[0]), p1[1] + t_ * (p2[1] - p1[1]))
    n = 0
    ids = [i for i in pares if i in perfis_u]
    for x, i in enumerate(ids):
        for j in ids[x + 1:]:
            si, sj = segs[i], segs[j]
            pontas_i = ((si[0], si[1]), (si[2], si[3]))
            pontas_j = ((sj[0], sj[1]), (sj[2], sj[3]))
            comum = next(((ki, kj) for ki in (0, 1) for kj in (0, 1) if math.dist(pontas_i[ki], pontas_j[kj]) < 2.0), None)
            if not comum:
                continue
            C = pontas_i[comum[0]]
            ii, ij = segs[pares[i][0]], segs[pares[j][0]]
            I = cruza((ii[0], ii[1]), (ii[2], ii[3]), (ij[0], ij[1]), (ij[2], ij[3]))
            if I is None or math.dist(C, I) > 4 * LINHA_DUPLA_MAX:
                continue
            C3, I3 = P(*C), P(*I)
            ci = tuple(I3[k] - C3[k] for k in range(3))
            nrm = (ci[1] * fora_do_plano[2] - ci[2] * fora_do_plano[1], ci[2] * fora_do_plano[0] - ci[0] * fora_do_plano[2],
                   ci[0] * fora_do_plano[1] - ci[1] * fora_do_plano[0])
            if math.sqrt(sum(c * c for c in nrm)) < 1e-6:
                continue
            for k, b in ((comum[0], perfis_u[i]), (comum[1], perfis_u[j])):
                no = b.inicio if k == 0 else b.fim
                plano = {"normal": [round(c, 9) for c in nrm], "ponto": [round(C3[c] - no[c], 4) for c in range(3)]}
                if k == 0:
                    b.cortes_inicio = [plano]
                else:
                    b.cortes_fim = [plano]
                n += 1
    return n


def _giro_do_contorno(vs, rotacao) -> float:
    """O giro do pilar de aço (graus) pelo contorno desenhado: a seção posta na planta (web/cad/estrutura.js,
    secaoNaPlanta — I, tubo, U, Ue, L e o retângulo antigo) começa pela aresta da mesa, no +X do pilar com giro 0°.
    O `rotacao` gravado no lançamento não muda quando o pilar é girado no CAD, e o 3D saía virado 90° do 2D (06/10)."""
    pts = [(float(v[0]), float(v[1])) for v in vs or []]
    if len(pts) in (4, 6, 8, 12):
        dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        if math.hypot(dx, dy) > 1e-6:
            return round(math.degrees(math.atan2(dy, dx)), 6) % 360.0
    return float(rotacao or 0.0)


#: os quadros da Montagem (web/cad/montagem.js) em que o que se lança é a obra: a implantação, com os eixos (a nova
#: dinâmica de 11/10 — os outros quadros são desenho para ler ou para ver)
QUADROS_DA_OBRA = ("implantacao",)


def _mapa_do_quadro(q: dict):
    """a volta do papel do quadro ao real: (x, y) → (g, p) = (X0 + (x − q.x − ox)·s, Y0 + (y − q.y − oy)·s), no sistema
    dos eixos (g ao longo dos numerados), girado de `giro` graus para a planta; None sem o mapa"""
    mp = q.get("mapa") if isinstance(q, dict) else None
    try:
        s = float(q.get("escala") or 0.0)
        X0, Y0, ox, oy = (float(mp[k]) for k in ("X0", "Y0", "ox", "oy"))
        qx, qy = float(q.get("x") or 0.0), float(q.get("y") or 0.0)
        giro = math.radians(float(mp.get("giro") or 0.0))
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
    if s <= 0:
        return None
    co, se = math.cos(giro), math.sin(giro)

    def f(p):
        g, q_ = X0 + (float(p[0]) - qx - ox) * s, Y0 + (float(p[1]) - qy - oy) * s
        return (g * co - q_ * se, g * se + q_ * co)
    return f, s


def _mapa_inverso_do_quadro(q: dict):
    """do real (g, p) ao papel do quadro: o contrário de _mapa_do_quadro"""
    mp = q.get("mapa") if isinstance(q, dict) else None
    try:
        s = float(q.get("escala") or 0.0)
        X0, Y0, ox, oy = (float(mp[k]) for k in ("X0", "Y0", "ox", "oy"))
        qx, qy = float(q.get("x") or 0.0), float(q.get("y") or 0.0)
        giro = math.radians(float(mp.get("giro") or 0.0))
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
    if s <= 0:
        return None
    co, se = math.cos(giro), math.sin(giro)

    def f(p):
        g, q_ = float(p[0]) * co + float(p[1]) * se, -float(p[0]) * se + float(p[1]) * co
        return ((g - X0) / s + qx + ox, (q_ - Y0) / s + qy + oy)
    return f, s


def planta_real(des: Desenho) -> Desenho:
    """A Montagem é uma folha em mm de papel: cada quadro tem a sua escala. Os elementos lançados dentro do quadro da
    Implantação voltam à medida real pelo mapa dele (`metadados.montagem.quadros[].mapa`); o resto da folha (o desenho
    do cliente posto nos quadros, as elevações) não é obra e fica de fora. Fora da Montagem, o próprio desenho."""
    m = (des.metadados or {}).get("montagem") if isinstance(des.metadados, dict) else None
    if not isinstance(m, dict):
        return des
    mapas = {}
    for q in m.get("quadros") or []:
        if isinstance(q, dict) and q.get("tipo") in QUADROS_DA_OBRA:
            r = _mapa_do_quadro(q)
            if r:
                mapas[q.get("id")] = r
    out = Desenho(nome=des.nome, escala=des.escala, metadados={k: v for k, v in des.metadados.items() if k != "montagem"})
    out.camadas = des.camadas
    for e in des.entidades.values():
        a = e.atributos or {}
        if not a.get("elemento") or a.get("quadro") not in mapas:
            continue
        f, s = mapas[a["quadro"]]
        n = copy.deepcopy(e)
        if isinstance(n, Linha):
            n.a, n.b = f(n.a), f(n.b)
        elif isinstance(n, Polilinha):
            n.vertices = [f(v) for v in n.vertices]
        elif isinstance(n, Circulo):
            n.centro = f(n.centro)
            n.raio = n.raio * s
        else:
            continue
        if isinstance(a.get("centro"), (list, tuple)) and len(a["centro"]) >= 2:
            n.atributos = dict(n.atributos, centro=list(f(a["centro"])))
        out.entidades[n.id] = n
    return out


def _furo_marcador(face, eixo, d: float, prof: float, peca_id: str) -> Solido:
    """o marcador de furo (o da ferramenta Furo, que o 3D abre na barra e o detalhamento lê): um prisma de 8 lados do
    diâmetro do furo, da face `face` pelo `eixo` na profundidade dada"""
    from nucleo3d import geometria as G
    ex = _unit3(eixo)
    a = _unit3(_cruz3(ex, (0.0, 0.0, 1.0) if abs(ex[2]) < 0.9 else (1.0, 0.0, 0.0)))
    b = _cruz3(ex, a)
    lados = [tuple(face[k] + (a[k] * math.cos(t) + b[k] * math.sin(t)) * d / 2.0 for k in range(3))
             for t in (2 * math.pi * j / 8 for j in range(8))]
    f = G.prisma(lados, tuple(c * prof for c in ex), nome="Furo Ø%g" % d, camada="Furos", material="Cor #1f2430")
    f.atributos = {"tipo_ifc": "IfcOpeningElement", "exportar": False,
                   "furo": {"d": d, "ponto": [round(float(c), 2) for c in face], "eixo": [round(float(c), 6) for c in ex],
                            "profundidade": prof, "peca": peca_id}}
    return f


def _unit3(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


def _cruz3(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _suportes_das_tercas(doc: Documento, avisos: List[str]) -> int:
    """O suporte de terça pelo projeto (Hangar, folhas 4 e 33 — 21/10/2026): a cantoneira (`suporte.perfil`, o ST1
    L127×50#3,75 com 150 mm) em cada cruzamento da terça com o banzo de cima de uma tesoura (no 2U composto, no plano
    da tesoura, entre os dois U) — a perna alta em pé, encostada na costa da alma da terça; a perna baixa deitada no
    banzo, para o lado de fora da terça. Onde duas terças emendam, cada uma recua a metade da folga (`folga`, 10 mm
    entre as pontas); os furos (`furos`: {ao_longo, altura, d}, a partir do meio do suporte e do pé da terça) furam a
    perna e a alma das terças — o par a 25 mm da ponta de cada terça; a terça que passa inteira leva os quatro. Uma
    peça por cruzamento. Devolve quantas."""
    from nucleo3d.geometria import base_local, resolver_perfil, secao
    tercas = [b for b in doc.entidades.values() if isinstance(b, Barra) and b.papel in ("terça", "terca")
              and isinstance((b.atributos or {}).get("suporte"), dict)]
    if not tercas:
        return 0
    banzos = [b for b in doc.entidades.values() if isinstance(b, Barra) and b.papel == "banzo"
              and str((b.atributos or {}).get("papel_trelica") or "") == "banzo_sup"
              and not (b.atributos or {}).get("ponta_composto")]
    # os cruzamentos: {(tesoura, terça): [pontos sobre cada banzo de cima dela]} — o composto tem dois
    cruz = collections.defaultdict(list)
    for t in tercas:
        w = _unit3(tuple(t.fim[k] - t.inicio[k] for k in range(3)))
        Lt = math.dist(t.inicio, t.fim)
        for bz in banzos:
            wb = _unit3(tuple(bz.fim[k] - bz.inicio[k] for k in range(3)))
            nb = _cruz3(wb, (0.0, 0.0, 1.0))
            if math.hypot(nb[0], nb[1]) < 0.5:
                continue
            nb = _unit3(nb)
            den = sum(w[k] * nb[k] for k in range(3))
            if abs(den) < 0.5:
                continue                                 # a terça paralela ao banzo não cruza
            s = sum((bz.inicio[k] - t.inicio[k]) * nb[k] for k in range(3)) / den
            if s < -200.0 or s > Lt + 200.0:
                continue                                 # (o U de fora do composto passa da ponta da terça: o meio decide)
            P = tuple(t.inicio[k] + w[k] * s for k in range(3))
            proj = sum((P[k] - bz.inicio[k]) * wb[k] for k in range(2)) / max(1e-9, math.hypot(wb[0], wb[1]))
            Lb = math.hypot(bz.fim[0] - bz.inicio[0], bz.fim[1] - bz.inicio[1])
            if proj < -50.0 or proj > Lb + 50.0:
                continue
            chave = (str((bz.atributos or {}).get("origem_2d") or (bz.atributos or {}).get("peca") or bz.id), t.id)
            cruz[chave].append(s)
    # cada cruzamento no meio dos banzos de cima da tesoura (o plano dela) e quem termina/começa ali
    pontos = []                                          # (P, terça, s)
    for (tes, tid), ss in cruz.items():
        t = doc.entidades[tid]
        s = sum(ss) / len(ss)
        if -1.0 <= s <= math.dist(t.inicio, t.fim) + 1.0:
            pontos.append((tes, t, min(max(s, 0.0), math.dist(t.inicio, t.fim))))
    juntas = collections.defaultdict(list)               # o ponto da obra → as terças que passam, terminam ou começam
    for tes, t, s in pontos:
        w = _unit3(tuple(t.fim[k] - t.inicio[k] for k in range(3)))
        P = tuple(t.inicio[k] + w[k] * s for k in range(3))
        juntas[(tes, round(P[1] / 20.0), round(P[2] / 20.0))].append((t, s, P, w))
    n = 0
    for (_tes, _y, _z), lista in juntas.items():
        t0, s0, P0, w0 = lista[0]
        sp = t0.atributos["suporte"]
        try:
            pl = resolver_perfil(sp["perfil"])
            pts_l = secao(pl)
            pts_t = secao(resolver_perfil(t0.perfil))
        except Exception:                                # noqa: BLE001
            avisos.append("suporte de terça: perfil %s fora do catálogo" % sp.get("perfil"))
            continue
        ut, vt, _ = base_local(w0, float(t0.rotacao or 0.0))
        costa = tuple(P0[k] + ut[k] * min(q[0] for q in pts_t) for k in range(3))   # a costa da alma da terça
        pe = P0[2] + vt[2] * min(q[1] for q in pts_t) if abs(vt[2]) > 0.5 else P0[2]
        xl0, yl0 = min(q[0] for q in pts_l), min(q[1] for q in pts_l)               # a quina da cantoneira
        tl = float(pl.tw or pl.tf or 3.0)
        L = float(sp.get("comprimento") or 150.0)
        folga = float(sp.get("folga") or 0.0)
        fora = tuple(-c for c in ut)
        # a perna baixa (u da seção) para fora da terça, a alta (v) para cima: o sentido da barra escolhe a mão
        for sentido in (1.0, -1.0):
            wl = tuple(c * sentido for c in w0)
            g = _giro_para(wl, fora)
            ul, vl, _ = base_local(wl, g)
            if vl[2] > 0.5:
                break
        ax = tuple(costa[k] - ul[k] * xl0 for k in range(3))
        ax = (ax[0], ax[1], pe - yl0 * vl[2])
        sup = Barra(inicio=tuple(ax[k] - wl[k] * L / 2.0 for k in range(3)), fim=tuple(ax[k] + wl[k] * L / 2.0 for k in range(3)),
                    perfil=sp["perfil"], rotacao=round(g, 3), papel="suporte", aco=str(sp.get("aco") or "ASTM A36"),
                    camada="Suportes", nome=str(sp.get("marca") or "Suporte de terça"), material="Aço",
                    atributos={"tipo_ifc": "IfcMember", "elemento": "Suporte de terça", "marca": sp.get("marca"),
                               "sigla": sp.get("marca"), **({"a_definir": sp["a_definir"]} if sp.get("a_definir") else {})})
        if "Suportes" not in doc.camadas:
            doc.camadas["Suportes"] = Camada(nome="Suportes", cor="#a16207")
        doc.add(sup)
        n += 1
        for f in sp.get("furos") or []:                  # os furos da perna alta, atravessando a perna
            face = tuple(costa[k] + w0[k] * float(f["ao_longo"]) for k in range(3))
            doc.add(_furo_marcador((face[0], face[1], pe + float(f["altura"])), fora, float(f["d"]), tl + 1.0, sup.id))
        emenda = sum(1 for t, s, _P, _w in lista if s < 1.0 or s > math.dist(t.inicio, t.fim) - 1.0) >= 2
        for t, s, P, w in lista:
            Lt = math.dist(t.inicio, t.fim)
            if emenda and folga and s < 1.0:
                t.recorte_inicio = max(float(t.recorte_inicio or 0.0), folga / 2.0)
            elif emenda and folga and s > Lt - 1.0:
                t.recorte_fim = max(float(t.recorte_fim or 0.0), folga / 2.0)
            ta = float(resolver_perfil(t.perfil).tw or 2.0)
            utt, _v, _ = base_local(w, float(t.rotacao or 0.0))
            for f in sp.get("furos") or []:
                lado = float(f["ao_longo"]) * sum(w0[k] * w[k] for k in range(3))   # no sentido desta terça
                if (s < 1.0 and lado < 0) or (s > Lt - 1.0 and lado > 0):
                    continue                             # só os furos do lado em que esta terça está
                face = tuple(costa[k] + w[k] * lado for k in range(3))
                doc.add(_furo_marcador((face[0], face[1], pe + float(f["altura"])), utt, float(f["d"]), ta + 1.0, t.id))
    if n:
        sp0 = tercas[0].atributos["suporte"]
        if sp0.get("a_definir"):
            avisos.append("suporte de terça %s: %s — apontamento ao projetista" % (sp0.get("marca") or "", sp0["a_definir"]))
    return n


def _faixa_da_secao(b: Barra, eixo) -> Tuple[float, float]:
    """quanto a seção da barra vai, a partir do eixo dela, na direção `eixo` (min, max)"""
    from nucleo3d.geometria import base_local, resolver_perfil, secao
    u, v, _ = base_local(b.direcao, float(b.rotacao or 0.0))
    pu, pv = sum(u[k] * eixo[k] for k in range(3)), sum(v[k] * eixo[k] for k in range(3))
    vals = [q[0] * pu + q[1] * pv for q in secao(resolver_perfil(b.perfil))]
    return min(vals), max(vals)


def _chapas_das_tesouras(doc: Documento, pedidas: List[Tuple[str, dict]], avisos: List[str]) -> int:
    """As chapas da emenda e das ligações das tesouras pelo projeto (Hangar, folhas 30 e 32/33 — 21/10/2026;
    identificacao.chapas_das_emendas). `pedidas`: [(id da tesoura na planta, {emenda, ligacao, parafusos_emenda})].

    Emenda (a CE): onde o banzo de baixo se interrompe (as meias-tesouras da cumeeira), uma chapa em cada metade, as
    duas encostadas no meio da junta e os banzos morrendo nelas (o banzo de cima com o corte em pé na face da chapa);
    os parafusos da emenda nos furos das alturas da elevação (`parafusos_emenda.alturas`), atravessando as duas. Cada
    metade tem o seu montante (o M11 do Hangar): o montante único que a linha do desenho dá na junta vira dois, um
    encostado em cada chapa (o U com a costa da alma nela); a diagonal que chega na junta para na face do montante.

    Ligação (a CL): em cada montante onde chega uma viga de fora do plano (a VC ou a VT), encostada nele (o U pela
    costa da alma). Os furos da aba (os que não são da emenda) furam a viga que está na frente deles; a viga longe da
    chapa ou sem viga na frente vira aviso. A chapa com aba de um lado só (a CE2/CL2 da T1, no oitão) põe a aba para o
    lado de onde as vigas chegam, na distância do eixo que o projeto dá (`eixo_x`).

    O pé de toda chapa no pé do banzo de baixo; a altura do projeto que não fecha com o topo do banzo de cima vira aviso.
    Devolve quantas peças entraram (chapas, montantes e parafusos)."""
    from nucleo3d.geometria import base_local, resolver_perfil, secao
    from nucleo3d.ligacoes3d import _parafuso
    if not pedidas:
        return 0
    if "Chapas" not in doc.camadas:
        doc.camadas["Chapas"] = Camada(nome="Chapas", cor="#c9a227")
    barras = [b for b in doc.entidades.values() if isinstance(b, Barra)]
    Z = (0.0, 0.0, 1.0)
    n = 0
    nao_pega = collections.Counter()                     # (chapa, viga) → furos com a viga ali que não a pegam
    afastada = {}                                        # (chapa, viga) → maior folga entre a chapa e a viga
    for tid, ped in pedidas:
        proprias = [b for b in barras if (b.atributos or {}).get("origem_2d") == tid]
        pt = lambda b: str((b.atributos or {}).get("papel_trelica") or "")
        inf = [b for b in proprias if b.papel == "banzo" and pt(b) == "banzo_inf"]
        sup = [b for b in proprias if b.papel == "banzo" and pt(b) == "banzo_sup" and not (b.atributos or {}).get("ponta_composto")]
        if not inf:
            continue
        marca = str((inf[0].atributos or {}).get("marca") or "")
        d0 = inf[0].direcao
        w = _unit3((d0[0], d0[1], 0.0))
        nr = _unit3(_cruz3(w, Z))
        O = inf[0].inicio
        s_ = lambda P: sum((P[k] - O[k]) * w[k] for k in range(2))
        x_ = lambda P: sum((P[k] - O[k]) * nr[k] for k in range(2))
        x_eixo = sum(x_(b.meio) for b in inf) / len(inf)
        z0 = min(b.meio[2] + _faixa_da_secao(b, Z)[0] for b in inf)
        P_ = lambda s, x, z: (O[0] + w[0] * s + nr[0] * x, O[1] + w[1] * s + nr[1] * x, z)

        def banzo_de_cima_em(s):
            for b in sup:
                sa, sb = s_(b.inicio), s_(b.fim)
                if min(sa, sb) - 30 <= s <= max(sa, sb) + 30 and abs(sb - sa) > 1:
                    return b, b.inicio[2] + (b.fim[2] - b.inicio[2]) * (s - sa) / (sb - sa)
            return None, None

        def topo_de_cima(s):
            b, z = banzo_de_cima_em(s)
            return None if b is None else z + _faixa_da_secao(b, Z)[1]

        # a junta: onde o banzo de baixo se interrompe (as metades da cumeeira)
        ints = sorted((min(s_(b.inicio), s_(b.fim)), max(s_(b.inicio), s_(b.fim))) for b in inf)
        corr = []
        for a_, b_ in ints:
            if corr and a_ <= corr[-1][1] + 1.0:
                corr[-1][1] = max(corr[-1][1], b_)
            else:
                corr.append([a_, b_])
        juntas = [(corr[i][1] + corr[i + 1][0]) / 2.0 for i in range(len(corr) - 1) if 3.0 < corr[i + 1][0] - corr[i][1] < 80.0]
        smin, smax = corr[0][0], corr[-1][1]
        # as vigas que chegam de fora do plano (VC, VT): a ponta perto do plano da tesoura, a barra quase normal a ele
        chegam = []
        for b in barras:
            if b in proprias or b.papel in ("terça", "terca", "suporte", "chumbador", "pilar"):
                continue
            db = b.direcao
            if abs(sum(db[k] * nr[k] for k in range(3))) < 0.95:
                continue
            for P, Q in ((b.inicio, b.fim), (b.fim, b.inicio)):
                if abs(x_(P) - x_eixo) < 250.0 and smin - 50 <= s_(P) <= smax + 50:
                    chegam.append((b, s_(P), 1.0 if x_(Q) > x_eixo else -1.0))
        lados = {l for _b, _s, l in chegam}

        def por_chapa(ch, s_meio, esp, lados_aqui, nome, extra):
            """a chapa (centrada no plano s_meio), com o contorno do projeto; devolve (Chapa, [(furo, ponto)])"""
            B = float(ch["largura"])
            cont = [tuple(v) for v in ch["contorno"]]
            furos = [dict(f) for f in ch.get("furos") or []]
            aba = ch.get("aba") or "duas"
            um_lado = aba in ("esquerda", "direita")
            ex = float(ch.get("eixo_x") or B / 2.0)
            if aba == "direita":                         # a aba sempre à esquerda (X = 0)
                cont = [(B - x, y) for x, y in reversed(cont)]
                for f in furos:
                    f["x"] = B - float(f["x"])
                ex = B - ex
            lado = 1.0
            if um_lado:
                if len(lados_aqui) == 1:
                    lado = next(iter(lados_aqui))
                else:
                    avisos.append("%s da %s: a chapa tem aba de um lado só e as vigas chegam %s — a aba foi para o lado +"
                                  % (ch["marca"], marca, "dos dois lados" if lados_aqui else "de nenhum lado"))
            if um_lado:
                exd = tuple(-lado * c for c in nr)
                borda = x_eixo + lado * ex                # o X = 0 da chapa: a ponta da aba
            else:
                exd = nr
                borda = x_eixo - ex
            org = P_(s_meio, borda, z0)
            c = Chapa(origem=org, eixo_x=exd, eixo_y=Z, contorno=cont, espessura=esp, centrada=True,
                      furos=[{"x": round(float(f["x"]), 2), "y": round(float(f["y"]), 2), "diametro": float(f["d"])} for f in furos],
                      aco="ASTM A36", camada="Chapas", nome=nome, material="Aço",
                      atributos=dict({"tipo_ifc": "IfcPlate", "elemento": "chapa", "marca": ch["marca"], "sigla": ch["marca"],
                                      "espessura": esp, "tesoura": marca, "origem_2d": tid}, **extra))
            pontos = [(f, tuple(org[k] + exd[k] * float(f["x"]) + Z[k] * float(f["y"]) for k in range(3))) for f in furos]
            topo = topo_de_cima(s_meio)
            if topo is not None and abs(z0 + float(ch["altura"]) - topo) > 10.0:
                avisos.append("%s da %s: a chapa tem %g mm e a tesoura ali %g (pé do banzo de baixo ao topo do de cima)"
                              % (ch["marca"], marca, ch["altura"], round(topo - z0)))
            return c, pontos

        def furar_vigas(ch, pontos, esp, lados_aqui, bolt_y=()):
            """os furos da aba furam a viga que está na frente deles (a mais perto, até 250 mm da chapa); o furo da aba do
            lado em que não chega viga fica só na chapa. Devolve quantos acharam viga"""
            achou = 0
            for f, H in pontos:
                if any(abs(float(f["y"]) - y) < 3.0 for y in bolt_y):
                    continue
                if (1.0 if x_(H) > x_eixo else -1.0) not in lados_aqui:
                    continue
                alvo = None
                for b, _s, _l in chegam:
                    dirb = b.direcao
                    tpar = sum((H[k] - b.inicio[k]) * dirb[k] for k in range(3))
                    if tpar < -5.0 or tpar > b.comprimento + 5.0:
                        continue
                    Pb = tuple(b.inicio[k] + dirb[k] * tpar for k in range(3))
                    u, v, _ = base_local(dirb, float(b.rotacao or 0.0))
                    du, dv = sum((H[k] - Pb[k]) * u[k] for k in range(3)), sum((H[k] - Pb[k]) * v[k] for k in range(3))
                    wu, wv = sum(w[k] * u[k] for k in range(3)), sum(w[k] * v[k] for k in range(3))
                    pts = secao(resolver_perfil(b.perfil))
                    t0, t1, ok = -1e9, 1e9, True
                    for p0, dp, lo, hi in ((du, wu, min(q[0] for q in pts), max(q[0] for q in pts)),
                                           (dv, wv, min(q[1] for q in pts), max(q[1] for q in pts))):
                        if abs(dp) < 1e-9:
                            ok = ok and lo <= p0 <= hi
                        else:
                            ta, tb = (lo - p0) / dp, (hi - p0) / dp
                            t0, t1 = max(t0, min(ta, tb)), min(t1, max(ta, tb))
                    dist = 0.0 if t0 <= 0 <= t1 else min(abs(t0), abs(t1))
                    if ok and t0 <= t1 and dist < 250.0 and (alvo is None or dist < alvo[3]):
                        alvo = (b, t0, t1, dist)
                if alvo is None:
                    # o furo que sobra (a VT usa só os de baixo da aba) não é falta; a viga que está ali e não é pega é
                    perto = next((b for b, _s, l in chegam if (1.0 if x_(H) > x_eixo else -1.0) == l
                                  and -5.0 <= sum((H[k] - b.inicio[k]) * b.direcao[k] for k in range(3)) <= b.comprimento + 5.0
                                  and abs(s_(b.meio) - s_(H)) < 250.0 and abs(b.meio[2] - H[2]) < 100.0), None)
                    if perto is not None:
                        nao_pega[(ch["marca"], (perto.atributos or {}).get("marca") or perto.nome)] += 1
                    continue
                b, t0, t1, _d = alvo
                achou += 1
                if t0 >= 0:
                    folga, face, eixo = t0 - esp / 2.0, tuple(H[k] + w[k] * t0 for k in range(3)), w
                elif t1 <= 0:
                    folga, face, eixo = -t1 - esp / 2.0, tuple(H[k] + w[k] * t1 for k in range(3)), tuple(-c for c in w)
                else:
                    folga, face, eixo = -1.0, tuple(H[k] + w[k] * t0 for k in range(3)), w
                if abs(folga) > 2.0:
                    k_ = (ch["marca"], (b.atributos or {}).get("marca") or b.nome)
                    afastada[k_] = max(afastada.get(k_, 0.0), folga, key=abs)
                tw = float(resolver_perfil(b.perfil).tw or 3.0)
                doc.add(_furo_marcador(face, eixo, float(f["d"]), min(t1 - t0, tw + 1.0), b.id))
            return achou

        # ---- a emenda
        ce = ped.get("emenda")
        par = ped.get("parafusos_emenda") or {}
        if ce and not juntas:
            avisos.append("%s da %s: a tesoura não se interrompe (sem meias-tesouras) — a chapa da emenda ficou de fora" % (ce["marca"], marca))
        for sj in (juntas if ce else []):
            t = float(ce["espessura"])
            alt_par = [float(y) for y in par.get("alturas") or []]
            pontos_lado = {}
            for sg in (1.0, -1.0):
                c, pontos = por_chapa(ce, sj + sg * t / 2.0, t, lados, "%s %s" % (ce["marca"], marca), {"papel_chapa": "emenda"})
                doc.add(c)
                n += 1
                pontos_lado[sg] = pontos
                furar_vigas(ce, pontos, t, lados, alt_par)
            # os parafusos da emenda: um em cada furo das alturas da elevação, no meio da junta
            if par.get("diametro"):
                for f, H in pontos_lado[1.0]:
                    if any(abs(float(f["y"]) - y) < 3.0 for y in alt_par):
                        Hc = tuple(H[k] - w[k] * t / 2.0 for k in range(3))
                        pz = _parafuso(Hc, w, float(par["diametro"]), 2.0 * t, "ASTM A307")
                        pz.atributos.update(marca="PAR %s" % ce["marca"], tesoura=marca, origem_2d=tid)
                        doc.add(pz)
                        n += 1
            # cada metade com o seu montante, encostado na chapa; a diagonal que chega na junta para nele
            na_junta = [b for b in proprias if b.papel == "montante" and b.id in doc.entidades and abs(s_(b.meio) - sj) < 30.0]
            face_mont = {1.0: sj + t, -1.0: sj - t}
            novas_m = []
            troca = {}                                       # o id do montante de antes → {lado: o id do novo}
            for m in na_junta:
                doc.entidades.pop(m.id, None)
                for sg in (1.0, -1.0):
                    dx = sj + sg * (t + 25.0) - s_(m.meio)          # provisório: a regra vira, depois encosta
                    nova = Barra(inicio=(m.inicio[0] + w[0] * dx, m.inicio[1] + w[1] * dx, m.inicio[2]),
                                 fim=(m.fim[0] + w[0] * dx, m.fim[1] + w[1] * dx, m.fim[2]), perfil=m.perfil,
                                 rotacao=float(m.rotacao or 0.0), papel=m.papel, aco=m.aco, camada=m.camada,
                                 nome="%s (%s)" % (m.nome, "lado +" if sg > 0 else "lado −"), material=m.material,
                                 atributos=dict(m.atributos or {}, junto_da_emenda=ce["marca"]),
                                 recorte_inicio=m.recorte_inicio, recorte_fim=m.recorte_fim,
                                 cortes_inicio=[dict(c) for c in m.cortes_inicio or []], cortes_fim=[dict(c) for c in m.cortes_fim or []])
                    doc.add(nova)
                    novas_m.append((sg, nova))
                    troca.setdefault(m.id, {})[sg] = nova.id
                    n += 1
            # as presilhas do par de cantoneiras de antes (a T1 e a T3: o montante em 2L): uma para cada metade
            for pz in [b for b in proprias if b.papel == "presilha" and b.id in doc.entidades
                       and set((b.atributos or {}).get("presilha_par") or []) & set(troca)]:
                doc.entidades.pop(pz.id, None)
                for sg in (1.0, -1.0):
                    dx = sg * (t + 25.0)
                    novo_par = [troca.get(i, {}).get(sg, i) for i in (pz.atributos or {}).get("presilha_par") or []]
                    doc.add(Barra(inicio=(pz.inicio[0] + w[0] * dx, pz.inicio[1] + w[1] * dx, pz.inicio[2]),
                                  fim=(pz.fim[0] + w[0] * dx, pz.fim[1] + w[1] * dx, pz.fim[2]), perfil=pz.perfil,
                                  rotacao=float(pz.rotacao or 0.0), papel=pz.papel, aco=pz.aco, camada=pz.camada,
                                  nome="%s (%s)" % (pz.nome, "lado +" if sg > 0 else "lado −"), material=pz.material,
                                  atributos=dict(pz.atributos or {}, presilha_par=novo_par, junto_da_emenda=ce["marca"])))
                    n += 1
                n -= 1
            if novas_m:
                # a boca pela regra (2.3: as peças da alma abrem para o meio do vão — o M11 de cada metade para a junta)
                from nucleo3d import regras_trelica as _rt
                _rt.orientar([b for b in doc.entidades.values() if isinstance(b, Barra) and (b.atributos or {}).get("origem_2d") == tid])
            for sg, nova in novas_m:
                lo, hi = _faixa_da_secao(nova, w)
                sc = sj + sg * t - (lo if sg > 0 else hi)              # a face dele na face da chapa
                dx = sc - s_(nova.meio)
                ini = (nova.inicio[0] + w[0] * dx, nova.inicio[1] + w[1] * dx, nova.inicio[2])
                fim = (nova.fim[0] + w[0] * dx, nova.fim[1] + w[1] * dx, nova.fim[2])
                b_sup, zc = banzo_de_cima_em(sc)
                if b_sup is not None:                        # o topo no eixo do banzo de cima naquele ponto
                    if ini[2] > fim[2]:
                        ini = ini[:2] + (zc,)
                    else:
                        fim = fim[:2] + (zc,)
                nova.inicio, nova.fim = ini, fim
                face_mont[sg] = sc + (hi if sg > 0 else lo)
            if troca:
                from nucleo3d import regras_trelica as _rt
                _rt.presilhas_no_lugar([b for b in doc.entidades.values() if isinstance(b, Barra) and (b.atributos or {}).get("origem_2d") == tid])
            for b in proprias:
                if b.papel == "montante" or b.id not in doc.entidades:
                    continue
                for ponta in ("inicio", "fim"):
                    P = getattr(b, ponta)
                    outra = b.fim if ponta == "inicio" else b.inicio
                    if abs(s_(P) - sj) > 12.0:
                        continue
                    sg = 1.0 if s_(outra) > sj else -1.0
                    cosw = abs(sum(b.direcao[k] * w[k] for k in range(3)))
                    if b.papel == "banzo":
                        # o banzo de cima: o corte em pé na face da chapa (o de baixo já para nela pelo comprimento)
                        if pt(b) == "banzo_sup":
                            pl = P_(sj + sg * t, x_(P), P[2])
                            setattr(b, "cortes_" + ponta, [{"normal": [round(c, 9) for c in w],
                                                            "ponto": [round(pl[k] - P[k], 4) for k in range(3)]}])
                    elif cosw > 0.1 and abs(s_(P) - sj) < 2.0:
                        rec = abs(face_mont[sg] - sj) / cosw
                        setattr(b, "recorte_" + ponta, max(float(getattr(b, "recorte_" + ponta) or 0.0), round(rec, 1)))
        # ---- a ligação: nos montantes onde as vigas chegam (fora da junta)
        cl = ped.get("ligacao")
        if cl:
            pos = sorted(s for _b, s, _l in chegam if all(abs(s - sj) > 150.0 for sj in juntas))
            grupos = []
            for s in pos:
                if grupos and s - grupos[-1][-1] < 120.0:
                    grupos[-1].append(s)
                else:
                    grupos.append([s])
            monts = [b for b in proprias if b.papel == "montante" and b.id in doc.entidades]
            t = float(cl["espessura"])
            for gs in grupos:
                sc = sum(gs) / len(gs)
                perto = sorted(monts, key=lambda m: abs(s_(m.meio) - sc))
                if not perto or abs(s_(perto[0].meio) - sc) > 150.0:
                    avisos.append("%s da %s: a viga chega a %s mm do início da tesoura sem montante ali — a chapa ficou de fora"
                                  % (cl["marca"], marca, round(sc)))
                    continue
                m = perto[0]
                sm = s_(m.meio)
                gm = [mm for mm in monts if abs(s_(mm.meio) - sm) < 5.0]
                faixas = [_faixa_da_secao(mm, w) for mm in gm]
                # o lado: o U pela costa da alma; as duas cantoneiras, para o lado de fora da junta
                u, _v, _ = base_local(m.direcao, float(m.rotacao or 0.0))
                uw = sum(u[k] * w[k] for k in range(3))
                if str(m.perfil).upper().startswith("U") and abs(uw) > 0.5:
                    xmin = min(q[0] for q in secao(resolver_perfil(m.perfil)))
                    sg = 1.0 if uw * xmin > 0 else -1.0
                else:
                    sg = 1.0 if not juntas or sm >= juntas[0] else -1.0
                face = sm + (max(f[1] for f in faixas) if sg > 0 else min(f[0] for f in faixas))
                lados_aqui = {l for _b, s, l in chegam if abs(s - sc) < 150.0}
                c, pontos = por_chapa(cl, face + sg * t / 2.0, t, lados_aqui, "%s %s" % (cl["marca"], marca), {"papel_chapa": "ligacao"})
                doc.add(c)
                n += 1
                furar_vigas(cl, pontos, t, lados_aqui)
                # a chapa que cruza um banzo da tesoura (a CL2 da T1, sem recorte: o U de boca para dentro)
                xs = [x_(tuple(c.origem[k] + c.eixo_x[k] * X for k in range(3))) for X, _Y in c.contorno]
                ys = [Y for _X, Y in c.contorno]
                for b in inf + sup:
                    sa, sb = sorted((s_(b.inicio), s_(b.fim)))
                    if not sa - 1 <= face <= sb + 1:
                        continue
                    lo, hi = _faixa_da_secao(b, nr)
                    zlo, zhi = _faixa_da_secao(b, Z)
                    zb = b.inicio[2] + (b.fim[2] - b.inicio[2]) * ((face - s_(b.inicio)) / ((s_(b.fim) - s_(b.inicio)) or 1.0))
                    # o recorte do contorno (a CL1): o banzo passa se a chapa não tem material naquela altura e largura
                    xb0, xb1 = x_(b.meio) + lo, x_(b.meio) + hi
                    cruza = _contorno_cruza(c, x_, xb0, xb1, zb + zlo - z0, zb + zhi - z0)
                    if cruza:
                        msg = ("%s da %s: a chapa cruza o banzo %s (%s mm de largura) — o detalhe do projeto não tem "
                               "recorte para ele: apontamento ao projetista"
                               % (cl["marca"], marca, "de baixo" if b in inf else "de cima", round(cruza, 1)))
                        if msg not in avisos:
                            avisos.append(msg)
                        break
    for (chm, vm), q in sorted(nao_pega.items()):
        avisos.append("%s: %d furo(s) da aba caem fora da seção da %s que chega ali (a viga virada ou em outra altura que a "
                      "do detalhe dela) — os furos ficam só na chapa; confira a %s" % (chm, q, vm, vm))
    for (chm, vm), folga in sorted(afastada.items()):
        avisos.append("%s: a %s %s da chapa (%s mm) — os furos estão nela; a posição pede conferência"
                      % (chm, vm, "afastada" if folga > 0 else "entrando", round(abs(folga), 1)))
    return n


def _contorno_cruza(c: Chapa, x_, xb0: float, xb1: float, yb0: float, yb1: float) -> float:
    """quanto o contorno da chapa (em pé, eixo_x na horizontal) entra no retângulo do banzo (x da obra, y a partir do
    pé da chapa): amostra o retângulo e conta os pontos dentro do contorno; devolve a largura invadida (0: não cruza)"""
    cont = c.contorno
    ox = x_(c.origem)
    sx = x_(tuple(c.origem[k] + c.eixo_x[k] for k in range(3))) - ox      # +1 ou −1
    def dentro(X, Y):
        r = False
        j = len(cont) - 1
        for i in range(len(cont)):
            xi, yi = cont[i]
            xj, yj = cont[j]
            if (yi > Y) != (yj > Y) and X < (xj - xi) * (Y - yi) / ((yj - yi) or 1e-12) + xi:
                r = not r
            j = i
        return r
    larg = []
    for i in range(1, 20):
        xo = xb0 + (xb1 - xb0) * i / 20.0
        X = (xo - ox) / (sx or 1.0)
        if any(dentro(X, yb0 + (yb1 - yb0) * k / 6.0) for k in range(1, 6)):
            larg.append(xo)
    return (max(larg) - min(larg) + (xb1 - xb0) / 20.0) if larg else 0.0



def modelo_da_planta(des: Desenho, niveis: Optional[Sequence[dict]] = None, nome: str = "Estrutura lançada") -> Tuple[Documento, List[str]]:
    """o Documento 3D da planta; devolve (documento, avisos). A Montagem vai pela Implantação, na medida real."""
    des = planta_real(des)
    tab = {str(n.get("nome")): float(n.get("z") or 0.0) for n in (niveis or []) if isinstance(n, dict) and n.get("nome")}
    doc = Documento(nome=nome)
    avisos: List[str] = []
    n_aco = 0
    pedidas: List[Tuple[str, dict]] = []
    for it in elementos(des):
        a, e, tipo = it["atributos"], it["entidade"], it["elemento"]
        marca = str(a.get("marca") or "")
        base = {"peca": marca, "marca": marca, "elemento": tipo, "origem_2d": e.id, "tipo_ifc": IFC[tipo], "pre_moldado": a.get("material") != "aco"}
        material = a.get("material") or "concreto"
        camada, cor = CAMADAS[tipo]
        if material == "aco" and tipo in ("pilar", "viga"):
            camada, cor = "Estrutura", "#4b5563"
        if camada not in doc.camadas:
            doc.camadas[camada] = Camada(nome=camada, cor=cor)
        try:
            if tipo == "pilar":
                if not isinstance(e, Polilinha) or len(e.vertices) < 3:
                    raise ErroDeDados("o pilar precisa de um contorno fechado")
                z0, z1 = _nivel(a.get("nivel_base"), tab, 0.0), _nivel(a.get("nivel_topo"), tab, 3000.0)
                if z1 <= z0:
                    raise ErroDeDados("o topo (%s) não está acima da base (%s)" % (z1, z0))
                if material == "aco":
                    # o centro pelo contorno desenhado (centro de gravidade: é onde a seção foi posta), não o "centro"
                    # gravado no lançamento — mover, copiar ou escalar o pilar não o atualiza, e as cópias iam todas
                    # para o ponto do original (06/10)
                    c = _centro_do_contorno(e.vertices) or a.get("centro")
                    s = a.get("secao") or {}
                    bar = Barra(inicio=(c[0], c[1], z0), fim=(c[0], c[1], z1), perfil=s.get("perfil", "W 310×38,7"), rotacao=_giro_do_contorno(e.vertices, a.get("rotacao")) + 90.0,
                                papel="pilar", aco=s.get("aco", "ASTM A572 Gr.50"), camada=camada, nome="Pilar %s" % marca, atributos=base)
                    doc.add(bar)
                    n_aco += 1
                else:
                    sol = extrudar(_contorno_z(e.vertices), (0.0, 0.0, 1.0), z1 - z0, origem=(0.0, 0.0, z0), nome="Pilar %s" % marca)
                    doc.add(_marcar(sol, camada, dict(base, secao=a.get("secao"), nivel_base=z0, nivel_topo=z1)))
            elif tipo == "trelica":
                n_aco += _trelica(doc, e, a, tab, camada, base)
                # as chapas da emenda e das ligações pelo projeto (a etapa da Identificação, 21/10): no fim, com as vigas
                # que chegam já no 3D (_chapas_das_tesouras)
                if isinstance(a.get("chapas"), dict):
                    pedidas.append((e.id, a["chapas"]))
            elif tipo == "viga":
                if not isinstance(e, Linha):
                    raise ErroDeDados("a viga precisa de uma linha")
                z = _nivel(a.get("nivel_topo"), tab, 3000.0)
                s = a.get("secao") or {}
                # o nível dado é o do eixo, o da face de cima ou o da de baixo (pedido do usuário, 06/10): o eixo da barra
                # de aço é o meio do perfil; o sólido de concreto vai pela face de cima
                alin = a.get("alinhamento") or ("eixo" if material == "aco" else "topo")
                if material == "aco":
                    h = _altura_do_perfil(s.get("perfil", "W 310×38,7"))
                    z += {"topo": -h / 2.0, "base": h / 2.0}.get(alin, 0.0)
                else:
                    h = _altura_secao(s)
                    z += {"eixo": h / 2.0, "base": h}.get(alin, 0.0)
                # a ponta b numa cota própria (`nivel_fim`, a Identificação para modelagem, 20/10): o contravento no plano do
                # telhado sobe com o banzo; o alinhamento vale igual nas duas pontas
                zb = z + (_nivel(a.get("nivel_fim"), tab, 0.0) - _nivel(a.get("nivel_topo"), tab, 3000.0)) if a.get("nivel_fim") is not None else z
                A, B = (e.a[0], e.a[1], z), (e.b[0], e.b[1], zb)
                L = math.dist(A, B)
                if L < 1:
                    raise ErroDeDados("a viga tem comprimento nulo")
                if material == "aco":
                    # a terça lançada pela Identificação para modelagem (20/10): a viga de aço com papel "terça" (o
                    # detalhamento e os resumos separam pelo papel), na camada das terças
                    papel = a.get("papel") or "viga"
                    cam_b, cor_b, nome_b = {"terça": ("Terças", "#0f766e", "Terça"), "terca": ("Terças", "#0f766e", "Terça"),
                                            "contraventamento": ("Contraventamento", "#16a34a", "Contravento"),
                                            "corrente": ("Correntes", "#65a30d", "Corrente"),
                                            "travamento": ("Travamentos", "#0891b2", "Travamento")}.get(papel, (camada, None, "Viga"))
                    if cam_b not in doc.camadas:
                        doc.camadas[cam_b] = Camada(nome=cam_b, cor=cor_b or "#4b5563")
                    # o suporte da terça pelo projeto (a etapa da Identificação, 21/10): o 3D põe um em cada cruzamento
                    # com o banzo de cima (_suportes_das_tercas, no fim)
                    extra_b = {"suporte": dict(a["suporte"])} if papel in ("terça", "terca") and isinstance(a.get("suporte"), dict) else {}
                    bar = Barra(inicio=A, fim=B, perfil=s.get("perfil", "W 310×38,7"), papel=papel, aco=s.get("aco", "ASTM A572 Gr.50"),
                                rotacao=float(a.get("rotacao") or 0.0), camada=cam_b, nome="%s %s" % (nome_b, marca),
                                atributos=dict(base, **extra_b))
                    doc.add(bar)
                    n_aco += 1
                else:
                    h = _altura_secao(s)
                    cont = [(u, v - h) for u, v in _secao_concreto(s)]
                    d = ((B[0] - A[0]) / L, (B[1] - A[1]) / L, 0.0)
                    sol = extrudar(cont, d, L, origem=A, nome="Viga %s" % marca)
                    doc.add(_marcar(sol, camada, dict(base, secao=s, nivel_topo=z, comprimento_mm=round(L))))
            elif tipo in ("fundacao", "consolo"):
                if not isinstance(e, Polilinha) or len(e.vertices) < 3:
                    raise ErroDeDados("%s precisa de um contorno fechado" % tipo)
                z1 = _nivel(a.get("nivel_topo"), tab, 0.0)
                h = float(a.get("altura") or 0.0)
                if h <= 0:
                    raise ErroDeDados("%s sem altura" % tipo)
                sol = extrudar(_contorno_z(e.vertices), (0.0, 0.0, 1.0), h, origem=(0.0, 0.0, z1 - h),
                               nome="%s %s" % ("Sapata" if a.get("tipo") != "bloco" else "Bloco", marca) if tipo == "fundacao" else "Consolo %s" % marca)
                extra = {"moldado_no_local": True} if tipo == "fundacao" else {}
                doc.add(_marcar(sol, camada, dict(base, nivel_topo=z1, altura_mm=h, **extra)))
            elif tipo == "tesoura":
                if not isinstance(e, Linha):
                    raise ErroDeDados("a tesoura precisa de uma linha")
                z_a = _nivel(a.get("nivel_base"), tab, 3000.0)
                z_b = _nivel(a.get("nivel_fim"), tab, z_a)
                if math.dist(e.a, e.b) < 1:
                    raise ErroDeDados("a tesoura tem comprimento nulo")
                s = a.get("secao") or {}
                if not all(float(s.get(k) or 0) > 0 for k in ("bf", "hf", "bw", "h")):
                    raise ErroDeDados("a seção I precisa de mesa, alma e altura")
                for sol in _tesoura(tuple(e.a), tuple(e.b), z_a, z_b, s, str(a.get("forma") or "duas águas"), "Tesoura %s" % marca):
                    doc.add(_marcar(sol, camada, dict(base, secao=s, nivel_base=z_a, nivel_fim=z_b, forma=a.get("forma"),
                                                      comprimento_mm=round(math.dist(e.a, e.b)))))
            elif tipo == "chapa":
                if not isinstance(e, Polilinha) or len(e.vertices) < 3:
                    raise ErroDeDados("a chapa precisa de um contorno fechado")
                esp = float(a.get("espessura") or 0.0)
                if esp <= 0:
                    raise ErroDeDados("a chapa sem espessura")
                z1 = _nivel(a.get("nivel_topo"), tab, 0.0)
                ch = Chapa(origem=(0.0, 0.0, z1 - esp / 2), contorno=[(v[0], v[1]) for v in e.vertices], espessura=esp, centrada=True,
                           aco=str(a.get("aco") or "ASTM A36"), camada=camada, nome="Chapa %s" % marca, material="Aço",
                           atributos=dict(base, pre_moldado=False, espessura=esp, nivel_topo=z1))
                doc.add(ch)
                n_aco += 1
            elif tipo in ("painel", "escada"):
                if not isinstance(e, Linha) or math.dist(e.a, e.b) < 1:
                    raise ErroDeDados("precisa de uma linha com comprimento")
                z0 = _nivel(a.get("nivel_base"), tab, 0.0)
                z1 = _nivel(a.get("nivel_topo"), tab, 3000.0)
                if z1 <= z0:
                    raise ErroDeDados("o nível de cima (%s) não está acima do de baixo (%s)" % (z1, z0))
                if tipo == "painel":
                    for sol in _paineis(tuple(e.a), tuple(e.b), a, z0, z1, "Fechamento %s" % marca):
                        doc.add(_marcar(sol, camada, dict(base, espessura=a.get("espessura"), nivel_base=z0, nivel_topo=z1, tipo_painel=a.get("tipo"))))
                else:
                    sols, g = _escada(tuple(e.a), tuple(e.b), a, z0, z1, "Escada %s" % marca)
                    for sol in sols:
                        doc.add(_marcar(sol, camada, dict(base, nivel_base=z0, nivel_topo=z1, degraus=g)))
                    if g["blondel"] < 600 or g["blondel"] > 660:
                        avisos.append("escada %s: 2e + p = %s mm (espelho %s × piso %s), fora da faixa confortável de 600 a 660 — "
                                      "o comprimento do lance decide o piso" % (marca, g["blondel"], g["espelho"], g["piso"]))
            elif tipo == "laje":
                if not isinstance(e, Polilinha) or len(e.vertices) < 3:
                    raise ErroDeDados("a laje precisa de um contorno fechado")
                z1 = _nivel(a.get("nivel_topo"), tab, 3000.0)
                for sol in _laje([(v[0], v[1]) for v in e.vertices], a, z1, "Laje %s" % marca):
                    doc.add(_marcar(sol, camada, dict(base, nivel_topo=z1, tipo_laje=a.get("tipo"), espessura=a.get("espessura"), capa=a.get("capa"))))
            elif tipo == "parafuso":
                c = a.get("centro") or list(getattr(e, "centro", (0.0, 0.0)))
                dia, L = float(a.get("diametro") or 0.0), float(a.get("comprimento") or 0.0)
                if dia <= 0 or L <= 0:
                    raise ErroDeDados("o parafuso precisa de diâmetro e comprimento")
                z1 = _nivel(a.get("nivel_topo"), tab, 0.0)
                if a.get("papel") == "chumbador":
                    # o chumbador do apoio (identificacao.apoios_das_tesouras, 21/10): a barra redonda da produção, como a
                    # das placas de base (ligacoes3d._chumbadores) — do topo (a face de baixo da placa) para baixo
                    from nucleo3d import geometria as geo
                    bitola = str(a.get("bitola") or "")
                    perfil = "FE RED %s" % bitola.replace('"', "''") if bitola else "FE RED Ø%g" % round(dia, 1)
                    geo.registrar_perfil(geo.barra_redonda(dia, perfil))
                    doc.add(Barra(inicio=(c[0], c[1], z1), fim=(c[0], c[1], z1 - L), perfil=perfil, papel="chumbador",
                                  aco=str(a.get("aco") or "SAE 1020"), camada="Chumbadores", nome="Chumbador %s" % marca,
                                  material="Aço", atributos=dict(base, pre_moldado=False, elemento="Chumbador",
                                                                  tipo_ifc="IfcMember", comprimento_mm=round(L))))
                    n_aco += 1
                    continue
                pts = [(dia / 2 * math.cos(2 * math.pi * k / 16), dia / 2 * math.sin(2 * math.pi * k / 16)) for k in range(16)]
                sol = extrudar(pts, (0.0, 0.0, 1.0), L, origem=(c[0], c[1], z1 - L), nome="Parafuso %s ø%s" % (marca, round(dia)))
                doc.add(_marcar(sol, camada, dict(base, pre_moldado=False, diametro=dia, comprimento=L, nivel_topo=z1), material="Aço"))
                n_aco += 1
        except ErroDeDados as err:
            avisos.append("%s %s: %s" % (tipo, marca, err))
    n_aco += _suportes_das_tercas(doc, avisos)
    n_aco += _chapas_das_tesouras(doc, pedidas, avisos)
    # os furos: na chapa em que caem (as coordenadas da chapa são as da planta)
    chapas = [c for c in doc.entidades.values() if isinstance(c, Chapa) and (c.atributos or {}).get("elemento") == "chapa"]
    for it in elementos(des):
        if it["elemento"] != "furo":
            continue
        a, e = it["atributos"], it["entidade"]
        c = tuple(a.get("centro") or getattr(e, "centro", (0.0, 0.0)))[:2]
        # o furo que diz a chapa (`chapa`: a marca dela) vai nela — a CB1 por cima da PB1 cobre os furos dos chumbadores
        dentro = [ch for ch in chapas if _dentro(c, ch.contorno)]
        alvo = next((ch for ch in dentro if a.get("chapa") and (ch.atributos or {}).get("marca") == a.get("chapa")), None) \
            or (dentro[0] if dentro else None)
        if alvo is None:
            avisos.append("furo %s: fora de todas as chapas (o 3D não tem onde furar)" % (a.get("marca") or e.id))
            continue
        alvo.furos.append({"x": c[0], "y": c[1], "diametro": float(a.get("diametro") or 0.0), "origem_2d": e.id})
    doc.metadados["de_planta_estrutura"] = {"elementos": len(elementos(des)), "aco": n_aco, "avisos": list(avisos)}
    # o elemento vinculado a um nível que não existe mais (apagado ou renomeado fora do CAD): o 3D usa o padrão, e isso
    # não pode passar calado (06/10)
    perdidos = collections.defaultdict(list)
    for it in elementos(des):
        a = it["atributos"] or {}
        for k in ("nivel_base", "nivel_topo", "nivel_fim"):
            v = a.get(k)
            if isinstance(v, str) and v not in tab:
                try:
                    float(v.replace(",", "."))
                except ValueError:
                    perdidos[v].append(str(a.get("marca") or "?"))
    for v, marcas in perdidos.items():
        avisos.append("o nível \"%s\" não existe nos níveis do projeto (%s): o 3D usou a cota padrão — escolha o nível de novo "
                      "nas propriedades" % (v, ", ".join(sorted(set(marcas))[:12])))
    if not doc.entidades:
        raise ErroDeDados("nenhum elemento da planta virou peça: " + ("; ".join(avisos) if avisos else "lance pilares, vigas, fundações ou consolos"))
    # a mesma marca em vários elementos (cópias feitas antes de 06/10 levavam a marca do original): o 3D sai, mas as
    # peças ficam com o mesmo nome — avisa para renumerar
    # a tesoura de aço repete a marca do tipo de propósito (T1 em cada eixo)
    marcas = collections.Counter(str((it["atributos"] or {}).get("marca") or "") for it in elementos(des) if it["elemento"] != "trelica")
    repetidas = ["%s (%d×)" % (m, n) for m, n in marcas.items() if m and n > 1]
    if repetidas:
        avisos.append("Marcas repetidas na planta: %s. Apague as cópias e copie de novo (a cópia ganha marca nova), ou "
                      "troque a marca nas Propriedades." % ", ".join(repetidas))
    return doc, avisos


# ------------------------------------------------------------------ a planta e o 3D ligados (a sincronia)

def da_planta(e, nome: str, estrito: bool = False) -> bool:
    """A peça do 3D que veio desta planta: marcada com `planta`, ou (gerada antes da marca) com o elemento e o id do
    contorno da planta e sem o eixo das peças do galpão pré-moldado. `estrito`: só a marcada com esta planta — a
    limpeza pela planta vazia não pode levar a peça sem marca de outra planta (um desenho de detalhamento vazio)."""
    a = e.atributos or {}
    if a.get("planta"):
        return a.get("planta") == nome
    if estrito:
        return False
    return bool(a.get("origem_2d")) and a.get("elemento") in ELEMENTOS and not a.get("eixo")


def sincronizar(g, s: str, nome: str, novo: Optional[Documento], avisos: List[str], estrito: bool = False) -> dict:
    """Troca no modelo 3D do projeto `s` as peças da planta `nome` pelas de agora (`novo`; None = a planta ficou sem
    elementos); o resto do modelo fica. `g` é o gerente de projetos (app._gerente()). A cobertura retrátil da análise
    (nucleo3d/cobertura_movel, a Kaefer) refaz as n tesouras e redesenha a planta, devolvida em `desenho`."""
    m = g.abrir_modelo(s)
    doc = Documento.de_dict(m) if m else Documento(nome=(novo.nome if novo else s))
    antes = [k for k, e in doc.entidades.items() if da_planta(e, nome, estrito)]
    for k in antes:
        del doc.entidades[k]
    if novo is not None:
        for nome_c, c in novo.camadas.items():
            if nome_c not in doc.camadas:
                doc.camadas[nome_c] = c
        for e in novo.entidades.values():
            doc.add(e)
    entrou = len(novo.entidades) if novo is not None else 0
    if not antes and not entrou:
        return {"ok": True, "mudou": False, "avisos": avisos}
    pj = g.ler(s)
    par = pj.get("analise_parametros") or {}
    desenho_novo = None
    if par.get("cobertura_movel"):
        from nucleo3d import cobertura_movel as CM
        try:
            CM.aplicar(doc, par, pj.get("cobertura_movel_vista") or "aberta")
            des = Desenho.de_dict(g.abrir_desenho(s, nome))
            if CM.na_planta(des, doc):
                g.salvar_desenho(s, nome, des.dict())
                desenho_novo = des.dict()
        except ErroDeDados as e:
            avisos = list(avisos) + ["cobertura retrátil: %s" % e]
    g.salvar_modelo(s, doc.dict(), marco=False)
    return {"ok": True, "mudou": True, "saiu": len(antes), "entrou": entrou, "avisos": avisos,
            "estatisticas": doc.estatisticas(), **({"desenho": desenho_novo} if desenho_novo else {})}


def gerar_no_projeto(g, s: str, nome: str, sincronia: bool = False) -> dict:
    """A planta `nome` do projeto `s` vira o 3D: com `sincronia`, troca só as peças dela (a planta e o 3D ligados, a
    cada gravação do CAD); sem, o modelo inteiro passa a ser o da planta (Gerar 3D da planta…)."""
    pj = g.ler(s)
    des = Desenho.de_dict(g.abrir_desenho(s, nome))
    real = planta_real(des)
    if sincronia and not elementos(real):
        # a planta ficou sem elementos (o último pilar apagado): o 3D tira as peças que vieram dela
        return sincronizar(g, s, nome, None, [], estrito=True)
    doc, avisos = modelo_da_planta(des, pj.get("niveis") or [], nome=pj.get("nome") or s)
    for e in doc.entidades.values():
        e.atributos = dict(e.atributos or {}, planta=nome)          # de que planta a peça veio (a sincronia)
    if sincronia:
        return sincronizar(g, s, nome, doc, avisos)
    g.salvar_modelo(s, doc.dict(), marco=True)
    return {"ok": True, "url": "/editor3d?projeto=%s" % s, "avisos": avisos, "estatisticas": doc.estatisticas(),
            "resumo": doc.metadados.get("de_planta_estrutura")}


# ------------------------------------------------------------------ a volta: o 3D atualiza a planta

def _caixa3d(ent) -> Optional[Tuple[float, float, float, float, float, float]]:
    """(x0, x1, y0, y1, z0, z1) de um sólido ou de uma barra"""
    if isinstance(ent, Barra):
        pts = [ent.inicio, ent.fim]
    elif isinstance(ent, Chapa):
        o, ex, ey = ent.origem, ent.eixo_x, ent.eixo_y
        nz = ent.espessura / 2
        pts = [(o[0] + x * ex[0] + y * ey[0], o[1] + x * ex[1] + y * ey[1], o[2] + dz) for x, y in ent.contorno for dz in (-nz, nz)]
    else:
        pts = getattr(ent, "vertices", None) or []
    if not pts:
        return None
    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def _mover_2d(e, dx: float, dy: float) -> None:
    if isinstance(e, Polilinha):
        e.vertices = [(v[0] + dx, v[1] + dy) for v in e.vertices]
    elif isinstance(e, Linha):
        e.a = (e.a[0] + dx, e.a[1] + dy)
        e.b = (e.b[0] + dx, e.b[1] + dy)
    elif isinstance(e, Circulo):
        e.centro = (e.centro[0] + dx, e.centro[1] + dy)
    elif hasattr(e, "posicao"):
        e.posicao = (e.posicao[0] + dx, e.posicao[1] + dy)
    a = e.atributos or {}
    if a.get("centro"):
        a["centro"] = [a["centro"][0] + dx, a["centro"][1] + dy]


def _proxima_marca(des: Desenho, elemento: str) -> str:
    pref = {"pilar": "P", "viga": "V", "fundacao": "S", "consolo": "C"}[elemento]
    usadas = {str((e.atributos or {}).get("marca") or "") for e in des.entidades.values() if (e.atributos or {}).get("elemento") == elemento}
    n = 1
    while "%s%d" % (pref, n) in usadas:
        n += 1
    return "%s%d" % (pref, n)


def _cm(v: float) -> str:
    return ("%.1f" % v).rstrip("0").rstrip(".").replace(".", ",")


#: as peças que as ferramentas do 3D do pré-moldado criam (editor_pm.js): o `peca` delas, sem eixo do galpão
PECAS_DO_3D = {"P": "pilar", "V": "viga", "SP": "fundacao", "CS": "consolo"}


def planta_do_modelo(des: Desenho, doc: Documento, niveis: Optional[Sequence[dict]] = None, tol: float = 1.0) -> Dict[str, list]:
    """a volta do lançamento: o que mudou no 3D vai para a planta (mm).

    * a peça que veio da planta (`origem_2d`) e foi movida no 3D move o elemento (e o rótulo dele);
    * o pilar de concreto com outra seção em planta troca o contorno e a seção; o topo e a base dos pilares
      e o topo (e a altura) das vigas, das fundações e dos consolos seguem o 3D (o nível vira número quando muda);
    * a peça que as ferramentas do 3D criaram (pilar, viga, sapata, consolo, sem `origem_2d`) entra na planta
      como elemento novo, e a peça 3D ganha o `origem_2d` dele (o modelo precisa ser gravado de novo);
    * o elemento da planta cuja peça sumiu do 3D fica na planta e vira apontamento (apagar é do usuário).

    Devolve {"alteracoes": [...], "novos": [ids 2D], "sem_peca": [marcas], "modelo_mudou": [ids 3D]}."""
    tab = {str(n.get("nome")): float(n.get("z") or 0.0) for n in (niveis or []) if isinstance(n, dict) and n.get("nome")}
    out: Dict[str, list] = {"alteracoes": [], "novos": [], "sem_peca": [], "modelo_mudou": []}
    rotulos: Dict[str, list] = {}
    for e in des.entidades.values():
        r = (e.atributos or {}).get("rotulo_de")
        if r:
            rotulos.setdefault(r, []).append(e)
    por_origem: Dict[str, list] = {}
    for p3 in doc.entidades.values():
        o = (p3.atributos or {}).get("origem_2d")
        if o:
            por_origem.setdefault(str(o), []).append(p3)
    for it in elementos(des):
        e, a, tipo = it["entidade"], dict(it["atributos"]), it["elemento"]
        marca = str(a.get("marca") or e.id)
        if tipo in ("furo", "trelica"):
            continue                                    # o furo vai com a chapa; a tesoura é refeita pela planta
        pecas = por_origem.get(e.id)
        if not pecas:
            out["sem_peca"].append(marca)
            continue
        cx3 = [c for c in (_caixa3d(p) for p in pecas) if c]
        if not cx3:
            continue
        x0, x1 = min(c[0] for c in cx3), max(c[1] for c in cx3)
        y0, y1 = min(c[2] for c in cx3), max(c[3] for c in cx3)
        z0, z1 = min(c[4] for c in cx3), max(c[5] for c in cx3)
        mud = []
        if tipo in ("viga", "tesoura", "painel", "escada") and isinstance(e, Linha):
            p3 = pecas[0]
            if tipo in ("tesoura", "painel", "escada"):
                # a tesoura são três ou quatro sólidos: a linha de apoio pela caixa de todos, o nível só na volta do 3D gerado
                p3 = Solido(vertices=[v for q in pecas for v in (getattr(q, "vertices", None) or [])])
            if isinstance(p3, Barra):
                na, nb, zt = (p3.inicio[0], p3.inicio[1]), (p3.fim[0], p3.fim[1]), p3.inicio[2]
            else:
                L0 = math.dist(e.a, e.b) or 1.0
                d = ((e.b[0] - e.a[0]) / L0, (e.b[1] - e.a[1]) / L0)
                proj = [v[0] * d[0] + v[1] * d[1] for v in p3.vertices]
                perp = [-v[0] * d[1] + v[1] * d[0] for v in p3.vertices]
                s0, s1 = min(proj), max(proj)
                t = (min(perp) + max(perp)) / 2
                na = (d[0] * s0 - d[1] * t, d[1] * s0 + d[0] * t)
                nb = (d[0] * s1 - d[1] * t, d[1] * s1 + d[0] * t)
                zt = z1
            if math.dist(na, e.a) > tol or math.dist(nb, e.b) > tol:
                dx, dy = (na[0] + nb[0]) / 2 - (e.a[0] + e.b[0]) / 2, (na[1] + nb[1]) / 2 - (e.a[1] + e.b[1]) / 2
                if abs(math.dist(na, nb) - math.dist(e.a, e.b)) > tol:
                    mud.append("comprimento %d → %d mm" % (round(math.dist(e.a, e.b)), round(math.dist(na, nb))))
                if math.hypot(dx, dy) > tol:
                    mud.append("movida %d mm" % round(math.hypot(dx, dy)))
                for r in rotulos.get(e.id, []):
                    _mover_2d(r, dx, dy)
                e.a, e.b = na, nb
            if tipo == "viga" and isinstance(p3, Barra) and a.get("material") == "aco":
                # o nível gravado é o do eixo, o da face de cima ou o da de baixo (alinhamento): a barra está no eixo — sem
                # descontar meio perfil, a terça apoiada pela face de baixo "subia" 63,5 mm a cada volta do 3D (20/10)
                alin = a.get("alinhamento") or "eixo"
                h = _altura_do_perfil((a.get("secao") or {}).get("perfil", "W 310×38,7"))
                zt -= {"topo": -h / 2.0, "base": h / 2.0}.get(alin, 0.0)
            if tipo == "viga" and abs(_nivel(a.get("nivel_topo"), tab, zt) - zt) > tol:
                mud.append("topo %s → %s" % (a.get("nivel_topo"), round(zt)))
                a["nivel_topo"] = round(zt)
            if tipo == "tesoura" and abs(_nivel(a.get("nivel_base"), tab, z0) - min(z0, _nivel(a.get("nivel_fim"), tab, z0))) > tol:
                dz = z0 - min(_nivel(a.get("nivel_base"), tab, z0), _nivel(a.get("nivel_fim"), tab, z0))
                if abs(dz) > tol:
                    a["nivel_base"] = round(_nivel(a.get("nivel_base"), tab, z0) + dz)
                    a["nivel_fim"] = round(_nivel(a.get("nivel_fim"), tab, z0) + dz)
                    mud.append("apoio %+d mm" % round(dz))
        elif isinstance(e, Circulo) and tipo == "parafuso":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            dx, dy = cx - e.centro[0], cy - e.centro[1]
            if math.hypot(dx, dy) > tol:
                e.atributos = a
                _mover_2d(e, dx, dy)
                mud.append("movido %d mm" % round(math.hypot(dx, dy)))
            if abs(_nivel(a.get("nivel_topo"), tab, z1) - z1) > tol:
                mud.append("cabeça %s → %s" % (a.get("nivel_topo"), round(z1)))
                a["nivel_topo"] = round(z1)
        elif isinstance(e, Polilinha) and e.vertices:
            # o centro da caixa, como o do 3D: a média dos vértices de um contorno irregular (pilar com rasgo, laje com recorte) sai do centro e a volta "movia" a peça sem ninguém ter mexido (PRATI CD, 09/10: lajes até 2,4 m)
            cx2 = (min(v[0] for v in e.vertices) + max(v[0] for v in e.vertices)) / 2
            cy2 = (min(v[1] for v in e.vertices) + max(v[1] for v in e.vertices)) / 2
            if tipo == "pilar" and isinstance(pecas[0], Barra):
                cx, cy = pecas[0].inicio[0], pecas[0].inicio[1]
            else:
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            dx, dy = cx - cx2, cy - cy2
            if math.hypot(dx, dy) > tol:
                e.atributos = a
                _mover_2d(e, dx, dy)
                for r in rotulos.get(e.id, []):
                    _mover_2d(r, dx, dy)
                mud.append("movido %d mm" % round(math.hypot(dx, dy)))
            if tipo == "pilar" and not isinstance(pecas[0], Barra) and a.get("material", "concreto") == "concreto":
                vx = [v[0] for v in e.vertices]
                vy = [v[1] for v in e.vertices]
                lx, ly = x1 - x0, y1 - y0
                if abs((max(vx) - min(vx)) - lx) > tol or abs((max(vy) - min(vy)) - ly) > tol:
                    e.vertices = [(cx - lx / 2, cy - ly / 2), (cx + lx / 2, cy - ly / 2), (cx + lx / 2, cy + ly / 2), (cx - lx / 2, cy + ly / 2)]
                    s = dict(a.get("secao") or {})
                    girado = float(a.get("rotacao") or 0) % 180 >= 45
                    s["b"], s["h"] = (round(ly / 10, 1), round(lx / 10, 1)) if girado else (round(lx / 10, 1), round(ly / 10, 1))
                    s["tipo"] = "retangular"
                    mud.append("seção %s × %s cm" % (_cm(s["b"]), _cm(s["h"])))
                    a["secao"] = s
            if tipo == "pilar":
                zb, zt = (pecas[0].inicio[2], pecas[0].fim[2]) if isinstance(pecas[0], Barra) else (z0, z1)
                if abs(_nivel(a.get("nivel_topo"), tab, zt) - zt) > tol:
                    mud.append("topo %s → %s" % (a.get("nivel_topo"), round(zt)))
                    a["nivel_topo"] = round(zt)
                if abs(_nivel(a.get("nivel_base"), tab, zb) - zb) > tol:
                    mud.append("base %s → %s" % (a.get("nivel_base"), round(zb)))
                    a["nivel_base"] = round(zb)
            else:
                if abs(_nivel(a.get("nivel_topo"), tab, z1) - z1) > tol:
                    mud.append("topo %s → %s" % (a.get("nivel_topo"), round(z1)))
                    a["nivel_topo"] = round(z1)
                if tipo == "laje":
                    pass                                    # a espessura (placa + capa) fica a da planta
                elif tipo == "chapa":
                    if abs(float(a.get("espessura") or 0) - (z1 - z0)) > tol:
                        mud.append("espessura %s → %s mm" % (a.get("espessura"), _cm(z1 - z0)))
                        a["espessura"] = round(z1 - z0, 2)
                elif abs(float(a.get("altura") or 0) - (z1 - z0)) > tol:
                    mud.append("altura %s → %d mm" % (a.get("altura"), round(z1 - z0)))
                    a["altura"] = round(z1 - z0)
        if mud:
            e.atributos = a
            out["alteracoes"].append("%s %s: %s" % (tipo, marca, ", ".join(mud)))
    # as peças novas do 3D
    for p3 in list(doc.entidades.values()):
        at = p3.atributos or {}
        tipo = PECAS_DO_3D.get(str(at.get("peca") or ""))
        if not tipo or at.get("origem_2d") or at.get("eixo") or not at.get("pre_moldado"):
            continue
        c = _caixa3d(p3)
        if c is None:
            continue
        x0, x1, y0, y1, z0, z1 = c
        marca = _proxima_marca(des, tipo)
        base = {"elemento": tipo, "material": "concreto", "marca": marca, "do_3d": True}
        if tipo == "viga":
            ao_longo_x = (x1 - x0) >= (y1 - y0)
            ym, xm = (y0 + y1) / 2, (x0 + x1) / 2
            larg = (y1 - y0) if ao_longo_x else (x1 - x0)
            novo = Linha(camada="ESTRUTURA", a=(x0, ym) if ao_longo_x else (xm, y0), b=(x1, ym) if ao_longo_x else (xm, y1),
                         atributos=dict(base, secao={"tipo": "retangular", "b": round(larg / 10, 1), "h": round((z1 - z0) / 10, 1)},
                                        nivel_topo=round(z1)))
        else:
            ret = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            centro = [(x0 + x1) / 2, (y0 + y1) / 2]
            extra = {"pilar": {"secao": {"tipo": "retangular", "b": round((x1 - x0) / 10, 1), "h": round((y1 - y0) / 10, 1)},
                               "nivel_base": round(z0), "nivel_topo": round(z1), "rotacao": 0, "centro": centro},
                     "fundacao": {"tipo": "sapata", "altura": round(z1 - z0), "nivel_topo": round(z1), "centro": centro},
                     "consolo": {"altura": round(z1 - z0), "nivel_topo": round(z1)}}[tipo]
            novo = Polilinha(camada="ESTRUTURA", vertices=ret, fechada=True, atributos=dict(base, **extra))
        des.add(novo)
        p3.atributos = dict(at, origem_2d=novo.id, marca=marca, elemento=tipo)
        out["novos"].append(novo.id)
        out["modelo_mudou"].append(p3.id)
        out["alteracoes"].append("%s %s: novo, lançado no 3D" % (tipo, marca))
    return out


def montagem_do_modelo(des: Desenho, doc: Documento, niveis: Optional[Sequence[dict]] = None, tol: float = 1.0) -> Dict[str, list]:
    """A volta do 3D para a Montagem (20/10/2026, Fase 6 da Identificação para modelagem: "depois se precisar fazer algum
    ajuste o usuário pode fazer tanto pela planta 2D quanto pelo 3D, pois ambos ficarão vinculados"). Os elementos da
    Implantação vão à medida real (planta_real), a volta de sempre (planta_do_modelo) acerta o que mudou no 3D — peça
    movida, comprimento, cota — e o que mudou volta ao papel do quadro pelo mapa inverso. A tesoura segue refeita pela
    planta (a volta não a toca) e a peça nova feita no 3D não entra na Montagem (fica no 3D). Mexe em `des`."""
    m = (des.metadados or {}).get("montagem") if isinstance(des.metadados, dict) else None
    if not isinstance(m, dict):
        return planta_do_modelo(des, doc, niveis, tol)
    inversos = {}
    for q in m.get("quadros") or []:
        if isinstance(q, dict) and q.get("tipo") in QUADROS_DA_OBRA:
            r = _mapa_inverso_do_quadro(q)
            if r:
                inversos[q.get("id")] = r
    real = planta_real(des)
    r = planta_do_modelo(real, doc, niveis, tol)
    for k, e in real.entidades.items():
        orig = des.entidades.get(k)
        inv = orig is not None and inversos.get((orig.atributos or {}).get("quadro"))
        if not inv:
            continue
        f, s = inv
        if isinstance(e, Linha) and isinstance(orig, Linha):
            orig.a, orig.b = f(e.a), f(e.b)
        elif isinstance(e, Polilinha) and isinstance(orig, Polilinha):
            orig.vertices = [f(v) for v in e.vertices]
        elif isinstance(e, Circulo) and isinstance(orig, Circulo):
            orig.centro = f(e.centro)
        at = dict(e.atributos or {})
        if isinstance(at.get("centro"), (list, tuple)) and len(at["centro"]) >= 2:
            at["centro"] = list(f(at["centro"]))
        orig.atributos = at
    r["novos"], r["modelo_mudou"] = [], []
    return r
