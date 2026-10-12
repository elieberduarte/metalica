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

    segs, papeis, perfis_b, secoes_b, vaos_b, virar_b = [], [], [], [], [], []
    for b in barras:
        try:
            segs.append(tuple(float(x) for x in b[:4]))
        except (TypeError, ValueError):
            continue
        papeis.append(str(b[4]) if len(b) > 4 else "diagonal")
        # o perfil da própria barra (a legenda de cores da folha de perfis do projeto, 11/10) e a seção dupla dela
        perfis_b.append(str(b[5]) if len(b) > 5 and b[5] else "")
        secoes_b.append(str(b[6]) if len(b) > 6 and b[6] else "")
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
                   **({"calandrar_raio": d.get("raio_banzo_sup")} if papel == "banzo_sup" and d.get("raio_banzo_sup") else {}))
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
            except Exception:                                  # noqa: BLE001
                xg, bf = 15.0, 50.0
            caixa = secoes_b[i] == "caixa"
            ls_ = math.hypot(u1 - u0, v1 - v0) or 1.0
            n_pl = (ux * (-(v1 - v0) / ls_) * k, uy * (-(v1 - v0) / ls_) * k, (u1 - u0) / ls_)     # a normal no plano
            dw_ = sum(a_ * b_ for a_, b_ in zip(n_pl, w))
            n_pl = tuple(a_ - dw_ * b_ for a_, b_ in zip(n_pl, w))
            nn_ = math.sqrt(sum(a_ * a_ for a_ in n_pl)) or 1.0
            n_pl = tuple(a_ / nn_ for a_ in n_pl)
            direcao = n_pl if caixa else fora_do_plano
            off = (bf - xg) if caixa else (xg + (vaos_b[i] if vaos_b[i] is not None else vao_da_alma) / 2.0)
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
            n += 1
            continue
        # cantoneira: a aba deitada sempre do mesmo lado do plano (giro pela normal do plano, não pelo sentido da linha)
        giro = _giro_para(w, fora_do_plano)
        if re.match(r"(?i)^\s*Ue?\s", perfil) and papel != "secundaria":
            # a alma em U ou Ue: a altura do perfil atravessa o plano (entra entre os dois U do banzo composto, ou na boca
            # do banzo — CD Bom Dia, 11/10); a boca no plano, sempre para o mesmo lado (para cima; a em pé, para o fim)
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
        if not dupla:
            bl = Barra(inicio=A, fim=B, perfil=perfil, papel=papel_3d, aco=aco, camada=camada, nome=nome,
                       rotacao=giro, atributos=atr)
            doc.add(bl)
            feitas.append(bl)
            n += 1
            continue
        # dupla: uma em cada aba do U, encostada na face de dentro da aba; a segunda é a primeira espelhada no plano
        # (na cantoneira de abas iguais, espelhar é girar 90°)
        try:
            from nucleo3d.geometria import resolver_perfil
            pu = resolver_perfil(perfis.get("banzo_sup") or perfis.get("banzo_inf"))
            pl = resolver_perfil(perfil)
            afast = max(float(pu.d or 0.0) / 2.0 - float(pu.tf or pu.tw or 0.0) - float(pl.bf or 0.0) / 2.0, 0.0)
        except Exception:                              # noqa: BLE001 — sem as medidas, encostadas no plano
            afast = 0.0
        for lado, g in ((-1.0, giro), (1.0, giro + 90.0)):
            dl = tuple(lado * afast * c for c in fora_do_plano)
            bl = Barra(inicio=tuple(A[c] + dl[c] for c in range(3)), fim=tuple(B[c] + dl[c] for c in range(3)), perfil=perfil,
                       papel=papel_3d, aco=aco, camada=camada, nome=nome + (" (a)" if lado < 0 else " (b)"), rotacao=g % 360.0,
                       atributos=dict(atr, cantoneira_dupla="a" if lado < 0 else "b"))
            doc.add(bl)
            feitas.append(bl)
            n += 1
    _cantos_em_meia_esquadria(segs, pares, perfis_u, P, fora_do_plano)
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


def modelo_da_planta(des: Desenho, niveis: Optional[Sequence[dict]] = None, nome: str = "Estrutura lançada") -> Tuple[Documento, List[str]]:
    """o Documento 3D da planta; devolve (documento, avisos). A Montagem vai pela Implantação, na medida real."""
    des = planta_real(des)
    tab = {str(n.get("nome")): float(n.get("z") or 0.0) for n in (niveis or []) if isinstance(n, dict) and n.get("nome")}
    doc = Documento(nome=nome)
    avisos: List[str] = []
    n_aco = 0
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
                A, B = (e.a[0], e.a[1], z), (e.b[0], e.b[1], z)
                L = math.dist(A, B)
                if L < 1:
                    raise ErroDeDados("a viga tem comprimento nulo")
                if material == "aco":
                    bar = Barra(inicio=A, fim=B, perfil=s.get("perfil", "W 310×38,7"), papel="viga", aco=s.get("aco", "ASTM A572 Gr.50"),
                                camada=camada, nome="Viga %s" % marca, atributos=base)
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
                pts = [(dia / 2 * math.cos(2 * math.pi * k / 16), dia / 2 * math.sin(2 * math.pi * k / 16)) for k in range(16)]
                sol = extrudar(pts, (0.0, 0.0, 1.0), L, origem=(c[0], c[1], z1 - L), nome="Parafuso %s ø%s" % (marca, round(dia)))
                doc.add(_marcar(sol, camada, dict(base, pre_moldado=False, diametro=dia, comprimento=L, nivel_topo=z1), material="Aço"))
                n_aco += 1
        except ErroDeDados as err:
            avisos.append("%s %s: %s" % (tipo, marca, err))
    # os furos: na chapa em que caem (as coordenadas da chapa são as da planta)
    chapas = [c for c in doc.entidades.values() if isinstance(c, Chapa) and (c.atributos or {}).get("elemento") == "chapa"]
    for it in elementos(des):
        if it["elemento"] != "furo":
            continue
        a, e = it["atributos"], it["entidade"]
        c = tuple(a.get("centro") or getattr(e, "centro", (0.0, 0.0)))[:2]
        alvo = next((ch for ch in chapas if _dentro(c, ch.contorno)), None)
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
