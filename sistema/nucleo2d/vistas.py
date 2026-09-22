# -*- coding: utf-8 -*-
"""Vistas 2D do modelo 3D: corte por um plano qualquer e projeção do que está além.

    from nucleo2d.vistas import Vista, gerar
    v = Vista(origem=(0, 12000, 0), normal=(0, 1, 0), profundidade=3000)
    desenho = gerar(documento3d, v)          # um `nucleo2d.desenho.Desenho`

Convenção do plano, a mesma da ferramenta de seção do editor 3D: a **normal aponta para
o lado que fica**. O observador está do lado removido, olhando na direção da normal.
O que o plano atravessa vira a **seção** da peça (polígono fechado, hachurado, na camada
CORTE). O que está além do plano, até `profundidade`, aparece **projetado** (silhueta na
camada VISTA e arestas vivas na VISTA-FINA). Sem corte (`cortar=False`), tudo dentro da
profundidade é projetado: é a vista de frente, topo ou lateral de uma seleção.

Sistema do desenho: `u` para a direita, `v` para cima, ambos no plano; `acima` diz o que
é "cima" (Z do modelo por padrão; num corte horizontal, Y). Coordenadas em milímetro,
com a origem no canto inferior esquerdo do que foi desenhado.

Linhas ocultas: não são removidas. Numa vista de estrutura metálica o que está atrás
costuma ser exatamente o que se quer ver (a tesoura atrás da tesoura cortada), e a
profundidade de vista é o controle: peça além dela não entra. Remoção de ocultas de
verdade fica para quando um desenho pedir.

Cada entidade 2D gerada guarda em `atributos` de que peça 3D veio (`origem`, `nome`,
`marca`, `perfil`), para o CAD rotular, selecionar por peça e cotar sabendo o que é.
"""
import collections
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo3d import geometria
from nucleo3d.modelo import Barra, Chapa, Documento, Solido
from nucleo2d.desenho import (Desenho, Hachura, Linha, Polilinha, Texto, escala_sugerida)

Ponto = Tuple[float, float, float]
Ponto2 = Tuple[float, float]

EPS = 1e-6
#: Ângulo entre faces vizinhas acima do qual a aresta comum é "viva" e se desenha.
ANGULO_ARESTA_VIVA = 30.0


# --------------------------------------------------------------- vetores

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cruz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a))
    if n < 1e-12:
        raise ErroDeDados("vetor nulo onde se esperava uma direção.")
    return (a[0] / n, a[1] / n, a[2] / n)


def _normal_face(pts: Sequence[Ponto]) -> Ponto:
    nx = ny = nz = 0.0
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / m, ny / m, nz / m) if m > 1e-12 else (0.0, 0.0, 0.0)


def _area2(pts: Sequence[Ponto2]) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        s += a[0] * b[1] - b[0] * a[1]
    return s / 2.0


# ------------------------------------------------------------ definição

@dataclass
class Vista:
    """Como olhar para o modelo."""
    origem: Ponto = (0.0, 0.0, 0.0)          # um ponto do plano
    normal: Ponto = (0.0, 1.0, 0.0)          # aponta para o lado que fica
    acima: Optional[Ponto] = None            # "para cima" no desenho; padrão Z (ou Y)
    profundidade: Optional[float] = None     # mm além do plano; None = tudo
    cortar: bool = True                      # False = só projeção
    entidades: Optional[List[str]] = None    # ids a incluir; None = todas as visíveis
    rotular: bool = True                     # marca da peça junto de cada seção
    nome: str = ""
    tipo: str = "corte"                      # corte, frente, topo, lateral… só rótulo

    def eixos(self) -> Tuple[Ponto, Ponto, Ponto]:
        """(u, v, w): u à direita, v para cima, w = normal (profundidade)."""
        w = _norm(self.normal)
        acima = self.acima
        if acima is None:
            acima = (0.0, 0.0, 1.0) if abs(w[2]) < 0.9 else (0.0, 1.0, 0.0)
        acima = _norm(acima)
        u = _cruz(w, acima)
        if math.sqrt(_dot(u, u)) < 1e-9:
            raise ErroDeDados("a direção 'acima' não pode ser paralela à normal do plano.")
        u = _norm(u)
        v = _norm(_cruz(u, w))
        return u, v, w

    def dict(self) -> dict:
        return {"origem": list(self.origem), "normal": list(self.normal),
                "acima": list(self.acima) if self.acima else None,
                "profundidade": self.profundidade, "cortar": self.cortar,
                "entidades": self.entidades, "rotular": self.rotular,
                "nome": self.nome, "tipo": self.tipo}

    @classmethod
    def de_dict(cls, d: dict) -> "Vista":
        if not isinstance(d, dict):
            raise ErroDeDados("definição de vista ausente.")
        def p(k, padrao):
            v = d.get(k)
            if v is None:
                return padrao
            if not (isinstance(v, (list, tuple)) and len(v) == 3):
                raise ErroDeDados("%s: esperado [x, y, z]" % k)
            return tuple(float(x) for x in v)
        prof = d.get("profundidade")
        return cls(origem=p("origem", (0.0, 0.0, 0.0)), normal=p("normal", (0.0, 1.0, 0.0)),
                   acima=p("acima", None), profundidade=float(prof) if prof not in (None, "") else None,
                   cortar=bool(d.get("cortar", True)), entidades=d.get("entidades"),
                   rotular=bool(d.get("rotular", True)), nome=str(d.get("nome") or ""),
                   tipo=str(d.get("tipo") or "corte"))


def vista_padrao(tipo: str, caixa: Tuple[Ponto, Ponto], folga: float = 10.0) -> Vista:
    """Vistas ortográficas prontas de uma caixa envolvente: frente, tras, esquerda,
    direita, topo, inferior. O plano encosta na caixa pelo lado do observador."""
    (x0, y0, z0), (x1, y1, z1) = caixa
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    tabela = {
        "frente":   ((cx, y0 - folga, cz), (0, 1, 0), (0, 0, 1)),
        "tras":     ((cx, y1 + folga, cz), (0, -1, 0), (0, 0, 1)),
        "esquerda": ((x0 - folga, cy, cz), (1, 0, 0), (0, 0, 1)),
        "direita":  ((x1 + folga, cy, cz), (-1, 0, 0), (0, 0, 1)),
        "topo":     ((cx, cy, z1 + folga), (0, 0, -1), (0, 1, 0)),
        "inferior": ((cx, cy, z0 - folga), (0, 0, 1), (0, 1, 0)),
    }
    if tipo not in tabela:
        raise ErroDeDados("vista desconhecida: %r (use frente, tras, esquerda, direita, topo, inferior)" % tipo)
    o, n, a = tabela[tipo]
    return Vista(origem=tuple(float(x) for x in o), normal=tuple(float(x) for x in n),
                 acima=tuple(float(x) for x in a), cortar=False, tipo=tipo, nome=tipo.capitalize())


# --------------------------------------------------------------- núcleo

def _malha_local(ent, u, v, w, origem) -> Tuple[List[Ponto], List[List[int]]]:
    """Malha da entidade no sistema (u, v, w) do plano."""
    verts, faces = geometria.malha(ent)
    local = []
    for p in verts:
        d = _sub(p, origem)
        local.append((_dot(d, u), _dot(d, v), _dot(d, w)))
    return local, faces


def _secao(P: Sequence[Ponto], faces, normais) -> List[List[Ponto2]]:
    """Laços fechados da interseção da malha com w = 0, em (u, v)."""
    segs = []
    for f, nf in zip(faces, normais):
        pts = []
        n = len(f)
        for i in range(n):
            a, b = P[f[i]], P[f[(i + 1) % n]]
            da, db = a[2], b[2]
            if (da < 0) != (db < 0):
                t = da / (da - db)
                pts.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        if len(pts) == 2:
            segs.append((pts[0], pts[1]))
        elif len(pts) > 2:
            # face côncava ou com furos ligados por fendas: pontos emparelhados ao
            # longo da reta de interseção (direção n_face × w, no plano)
            du, dv = nf[1], -nf[0]
            pts.sort(key=lambda p: p[0] * du + p[1] * dv)
            for i in range(0, len(pts) - 1, 2):
                if math.hypot(pts[i][0] - pts[i + 1][0], pts[i][1] - pts[i + 1][1]) > EPS:
                    segs.append((pts[i], pts[i + 1]))
    return _encadear(segs)


def _encadear(segs) -> List[List[Ponto2]]:
    """Segmentos soltos → laços fechados (os abertos são descartados: malha aberta)."""
    chave = lambda p: (round(p[0], 2), round(p[1], 2))    # noqa: E731
    adj = collections.defaultdict(list)
    for k, (a, b) in enumerate(segs):
        adj[chave(a)].append((k, b))
        adj[chave(b)].append((k, a))
    usados, lacos = set(), []
    for k, (a, b) in enumerate(segs):
        if k in usados:
            continue
        usados.add(k)
        laco, atual, fechado = [a, b], b, False
        while True:
            prox = [(kk, o) for kk, o in adj[chave(atual)] if kk not in usados]
            if not prox:
                break
            kk, o = prox[0]
            usados.add(kk)
            if chave(o) == chave(a):
                fechado = True
                break
            laco.append(o)
            atual = o
        if fechado and len(laco) >= 3 and abs(_area2(laco)) > 1.0:
            lacos.append(laco)
    return lacos


def _arestas_visiveis(P, faces, normais, w_min: float, w_max: Optional[float]):
    """Silhueta e arestas vivas da malha vista ao longo de +w, restritas à faixa de
    profundidade. Aresta atravessando w_min é aparada no plano.

    Face virada para o observador tem normal com componente w negativa (o observador
    está em -w olhando para +w)."""
    por_aresta = collections.defaultdict(list)
    for idx, f in enumerate(faces):
        n = len(f)
        for i in range(n):
            a, b = f[i], f[(i + 1) % n]
            por_aresta[(min(a, b), max(a, b))].append(idx)
    cos_viva = math.cos(math.radians(ANGULO_ARESTA_VIVA))
    fortes, finas = [], []
    for (a, b), fs in por_aresta.items():
        frente = [normais[i][2] < -EPS for i in fs]
        if len(fs) == 1 or (any(frente) and not all(frente)):
            destino = fortes
        elif all(frente) and _dot(normais[fs[0]], normais[fs[1]]) < cos_viva:
            destino = finas
        else:
            continue
        pa, pb = P[a], P[b]
        # faixa de profundidade: [w_min, w_max]
        if pa[2] < w_min and pb[2] < w_min:
            continue
        if w_max is not None and pa[2] > w_max and pb[2] > w_max:
            continue
        if (pa[2] < w_min) != (pb[2] < w_min):
            t = (w_min - pa[2]) / (pb[2] - pa[2])
            corte = (pa[0] + t * (pb[0] - pa[0]), pa[1] + t * (pb[1] - pa[1]), w_min)
            pa, pb = (corte, pb) if pa[2] < w_min else (pa, corte)
        if w_max is not None and (pa[2] > w_max) != (pb[2] > w_max):
            t = (w_max - pa[2]) / (pb[2] - pa[2])
            corte = (pa[0] + t * (pb[0] - pa[0]), pa[1] + t * (pb[1] - pa[1]), w_max)
            pa, pb = (corte, pb) if pa[2] > w_max else (pa, corte)
        if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) > 0.05:
            destino.append(((pa[0], pa[1]), (pb[0], pb[1]), (pa[2] + pb[2]) / 2))
    return fortes, finas


def _atributos(ent) -> dict:
    marcas = (ent.atributos or {}).get("marcas") or {}
    a = {"origem": ent.id, "nome": ent.nome or "", "tipo3d": ent.tipo}
    if isinstance(ent, Barra):
        a["perfil"] = ent.perfil
        a["papel"] = ent.papel
    elif isinstance(ent, Chapa):
        a["espessura"] = ent.espessura
    if marcas:
        a.update({k: marcas[k] for k in ("posicao", "conjunto", "perfil") if k in marcas})
    if ent.atributos and ent.atributos.get("origem_ifc"):
        a["origem_ifc"] = ent.atributos["origem_ifc"]
    return a


def gerar(doc: Documento, vista: Vista, desenho: Optional[Desenho] = None,
          deslocamento: Ponto2 = (0.0, 0.0)) -> Desenho:
    """Gera (ou acrescenta a `desenho`) a vista 2D de `doc`.

    Devolve o desenho com origem no canto inferior esquerdo do que foi desenhado, mais
    `deslocamento`. `desenho.vistas` recebe a definição e a caixa da vista, para o CAD
    saber de onde veio cada trecho e para a prancha poder montar mais de uma."""
    u, v, w = vista.eixos()
    origem = tuple(float(x) for x in vista.origem)
    prof = vista.profundidade
    # com corte, o que está antes do plano (w < 0) some; sem corte, o plano é só a
    # referência de onde a profundidade começa a contar, e nada é removido
    w_min = 0.0 if vista.cortar else float("-inf")
    w_max = None if prof is None else float(prof)

    ids = vista.entidades
    escolhidas = []
    for ent in doc.entidades.values():
        if ids is not None and ent.id not in ids:
            continue
        if ids is None:
            if not ent.visivel:
                continue
            cam = doc.camadas.get(ent.camada)
            if cam is not None and not cam.visivel:
                continue
        if isinstance(ent, (Barra, Chapa, Solido)):
            escolhidas.append(ent)

    secoes: List[Tuple[object, List[List[Ponto2]]]] = []
    fortes: List[Tuple[object, Ponto2, Ponto2, float]] = []
    finas: List[Tuple[object, Ponto2, Ponto2, float]] = []
    avisos: List[str] = []
    for ent in escolhidas:
        try:
            P, faces = _malha_local(ent, u, v, w, origem)
        except Exception as e:                      # peça sem geometria não derruba a vista
            avisos.append("%s: %s" % (ent.nome or ent.id, e))
            continue
        if not P or not faces:
            continue
        ws = [p[2] for p in P]
        w_lo, w_hi = min(ws), max(ws)
        if vista.cortar and w_hi <= EPS:
            continue                                # inteira do lado removido
        if w_max is not None and w_lo >= w_max:
            continue                                # além da profundidade
        normais = [_normal_face([P[i] for i in f]) for f in faces]
        if vista.cortar and w_lo < -EPS < EPS < w_hi:
            lacos = _secao(P, faces, normais)
            if lacos:
                secoes.append((ent, lacos))
        f1, f2 = _arestas_visiveis(P, faces, normais, w_min, w_max)
        fortes.extend((ent, a, b, z) for a, b, z in f1)
        finas.extend((ent, a, b, z) for a, b, z in f2)

    # origem do desenho no canto inferior esquerdo
    xs, ys = [], []
    for _, lacos in secoes:
        for l in lacos:
            xs += [p[0] for p in l]
            ys += [p[1] for p in l]
    for _, a, b, _ in fortes + finas:
        xs += [a[0], b[0]]
        ys += [a[1], b[1]]
    if not xs:
        raise ErroDeDados("a vista não alcança nenhuma peça: mude o plano ou a profundidade.")
    x0, y0 = min(xs), min(ys)
    larg, alt = max(xs) - x0, max(ys) - y0
    dx, dy = deslocamento[0] - x0, deslocamento[1] - y0
    mv = lambda p: (p[0] + dx, p[1] + dy)             # noqa: E731

    des = desenho if desenho is not None else Desenho(nome=vista.nome or "Vista")
    if desenho is None:
        des.escala = escala_sugerida(larg, alt)
    # o que está mais longe primeiro, para a ordem de desenho ajudar a leitura
    for ent, a, b, z in sorted(finas, key=lambda t: -t[3]):
        des.add(Linha(camada="VISTA-FINA", a=mv(a), b=mv(b), atributos=_atributos(ent)))
    for ent, a, b, z in sorted(fortes, key=lambda t: -t[3]):
        des.add(Linha(camada="VISTA", a=mv(a), b=mv(b), atributos=_atributos(ent)))
    for ent, lacos in secoes:
        atr = _atributos(ent)
        lacos = sorted(lacos, key=lambda l: -abs(_area2(l)))
        contornos = [[mv(p) for p in l] for l in lacos]
        des.add(Hachura(contornos=contornos, padrao="aco", atributos=dict(atr)))
        for c in contornos:
            des.add(Polilinha(camada="CORTE", vertices=c, fechada=True, atributos=dict(atr)))
        if vista.rotular:
            rotulo = atr.get("posicao") or atr.get("perfil") or atr.get("nome")
            if rotulo:
                ext = contornos[0]
                cx = sum(p[0] for p in ext) / len(ext)
                cy = max(p[1] for p in ext)
                des.add(Texto(posicao=(cx, cy + 1.5 * des.escala), texto=str(rotulo),
                              altura=2.0, alinhamento="centro", atributos=dict(atr, rotulo=True)))

    des.vistas.append({**vista.dict(), "pecas_cortadas": len(secoes),
                       "pecas_projetadas": len({id(e) for e, *_ in fortes}),
                       "largura": round(larg, 1), "altura": round(alt, 1),
                       "canto": [deslocamento[0], deslocamento[1]], "avisos": avisos[:20]})
    return des
