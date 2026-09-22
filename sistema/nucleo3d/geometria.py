# -*- coding: utf-8 -*-
"""Geometria do módulo 3D: seções de perfil, extrusão, malhas e edição.

Tudo aqui está em **milímetro** e **grau**, como manda o `GUIA_3D.md`, e só usa a
biblioteca padrão — nada de numpy. O núcleo de cálculo continua em kN e cm; a
conversão acontece em `de_projeto.py`.

Divisão do módulo
-----------------
1. utilidades de vetor e de polígono (`triangular`, `normal_face`, `area_face`,
   `centroide`, `caixa_envolvente`, `interseccao_reta_plano`,
   `ponto_mais_proximo_reta`, `distancia_ponto_segmento`);
2. seções transversais do catálogo (`secao`, `secao_com_furos`);
3. extrusão e malhas (`extrudar`, `malha_barra`, `malha_chapa`);
4. operações de edição do editor (`extrudar_face`, `offset_contorno`, `mover`,
   `girar`, `espelhar`, `escalar`, `dividir_aresta`, `unir_solidos`, `secao_plano`).

Convenção da seção
------------------
O contorno da seção vive no plano local **(x = largura, y = altura)**, fechado, em
sentido anti-horário, e **centrado no centroide** da área (não no retângulo
envolvente — a diferença importa em U e em cantoneira). O eixo forte do perfil é o
eixo local *y*.

Aproximações geométricas adotadas (todas documentadas em `secao`)
-----------------------------------------------------------------
* **Raios de concordância do perfil I**: substituídos por um chanfro a 45° cuja
  perna é calculada para que a área do contorno reproduza a área tabelada do
  catálogo. O raio equivalente que sai daí fica entre 9 e 16 mm nos perfis W e HP
  do catálogo, que é a faixa real das séries laminadas.
* **Mesa do U laminado**: o catálogo traz uma espessura só (`t`, a da alma) e a
  mesa real é mais grossa e inclinada. A mesa é modelada com espessura constante
  calculada a partir da área tabelada. Dá uma relação tf/tw entre 1,1 e 1,9,
  compatível com os perfis americanos.
* **Dobras do perfil formado a frio**: cantos arredondados com raio interno igual à
  espessura (`ri = t`, NBR 6355), aproximados por 4 segmentos por dobra.
* **Cantos do tubo retangular**: raio externo 2·t e interno t, também por segmentos.
* **Tubo redondo e barra redonda**: polígono de 32 lados, que subestima a área do
  círculo em 0,64 %.
* **Cantoneira**: cantos vivos; o raio de concordância interno e o arredondamento das
  pontas se compensam e o erro de área fica abaixo de 2,5 %.

Todas essas aproximações são conferidas pelo teste `test_3d_geometria.py`, que exige
que a área do contorno bata com a área de catálogo de **todos** os perfis dentro de 3 %.
"""
import functools
import copy
import math
import os
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:                      # permite rodar o módulo isoladamente
    sys.path.insert(0, _RAIZ)

from nucleo.base import ErroDeDados, RHO                      # noqa: E402
from nucleo.perfis import Perfil, banco                       # noqa: E402
from nucleo3d.modelo import (Barra, Chapa, Entidade, Grupo, Ponto,  # noqa: E402
                             Solido, escalar as _mult, normalizar,
                             produto_escalar, produto_vetorial, somar, subtrair)

Ponto2 = Tuple[float, float]

#: Tolerância geométrica do módulo, em milímetros. Abaixo disso dois pontos são o
#: mesmo ponto (é a precisão de fabricação: décimo de milímetro é o limite útil).
TOL = 1e-7

#: Massa específica do aço, em kg/mm³ (7850 kg/m³ do `nucleo.base`).
RHO_MM3 = RHO / 1e9

#: Lados do polígono que aproxima um círculo cheio (tubo redondo, barra redonda).
LADOS_CIRCULO = 32

#: Lados do polígono que aproxima um furo de parafuso.
LADOS_FURO = 16


# =====================================================================================
# 1. Utilidades de vetor
# =====================================================================================

def _v(p) -> Ponto:
    return (float(p[0]), float(p[1]), float(p[2]))


def _finito(*vals) -> bool:
    """Verdadeiro se todos os números forem finitos (nem NaN nem infinito)."""
    for v in vals:
        if isinstance(v, (list, tuple)):
            if not _finito(*v):
                return False
        elif not math.isfinite(float(v)):
            return False
    return True


def normal_face(vertices: Sequence[Ponto]) -> Ponto:
    """Normal unitária de uma face plana, pelo método de Newell.

    Newell é estável mesmo com a face ligeiramente fora do plano ou com vértices
    quase colineares, ao contrário do produto vetorial de dois lados quaisquer.
    """
    n = [0.0, 0.0, 0.0]
    m = len(vertices)
    if m < 3:
        return (0.0, 0.0, 1.0)
    for i in range(m):
        a, b = vertices[i], vertices[(i + 1) % m]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return normalizar((n[0], n[1], n[2]))


def area_face(vertices: Sequence[Ponto]) -> float:
    """Área de um polígono plano no espaço, em mm² (metade do vetor de Newell)."""
    n = [0.0, 0.0, 0.0]
    m = len(vertices)
    if m < 3:
        return 0.0
    for i in range(m):
        a, b = vertices[i], vertices[(i + 1) % m]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) / 2.0


def centroide(pontos: Sequence[Sequence[float]]) -> Tuple[float, ...]:
    """Média dos pontos (2D ou 3D). É o que o snap do editor usa como centro."""
    if not pontos:
        raise ErroDeDados("centroide: lista de pontos vazia.")
    dim = len(pontos[0])
    return tuple(sum(p[i] for p in pontos) / len(pontos) for i in range(dim))


def caixa_envolvente(pontos: Sequence[Sequence[float]]):
    """Caixa envolvente alinhada aos eixos: ((min...), (max...))."""
    if not pontos:
        raise ErroDeDados("caixa envolvente: lista de pontos vazia.")
    dim = len(pontos[0])
    return (tuple(min(p[i] for p in pontos) for i in range(dim)),
            tuple(max(p[i] for p in pontos) for i in range(dim)))


def interseccao_reta_plano(origem: Ponto, direcao: Ponto, plano) -> Optional[Ponto]:
    """Ponto em que a reta encontra o plano, ou None se for paralela.

    `plano` é `(ponto, normal)`. Serve para o snap em face e para a ferramenta de
    corte.
    """
    p0, n = _v(plano[0]), normalizar(plano[1])
    d = normalizar(direcao)
    den = produto_escalar(d, n)
    if abs(den) < 1e-12:
        return None
    t = produto_escalar(subtrair(p0, _v(origem)), n) / den
    return somar(_v(origem), _mult(d, t))


def ponto_mais_proximo_reta(ponto: Ponto, a: Ponto, b: Ponto) -> Ponto:
    """Projeção ortogonal do ponto sobre a reta que passa por a e b (infinita)."""
    ab = subtrair(_v(b), _v(a))
    n2 = produto_escalar(ab, ab)
    if n2 < 1e-18:
        return _v(a)
    t = produto_escalar(subtrair(_v(ponto), _v(a)), ab) / n2
    return somar(_v(a), _mult(ab, t))


def distancia_ponto_segmento(ponto: Ponto, a: Ponto, b: Ponto) -> float:
    """Distância do ponto ao segmento a–b, em mm (limitada às extremidades)."""
    ab = subtrair(_v(b), _v(a))
    n2 = produto_escalar(ab, ab)
    if n2 < 1e-18:
        return math.dist(_v(ponto), _v(a))
    t = produto_escalar(subtrair(_v(ponto), _v(a)), ab) / n2
    t = max(0.0, min(1.0, t))
    return math.dist(_v(ponto), somar(_v(a), _mult(ab, t)))


def base_local(direcao: Ponto, rotacao: float = 0.0) -> Tuple[Ponto, Ponto, Ponto]:
    """Triedro local de uma barra: (u, v, w) com w na direção do eixo.

    `u` é o eixo local *x* da seção (largura da mesa) e `v` o eixo local *y* (eixo
    forte). O vetor auxiliar é o Z global, trocado pelo X global quando a direção é
    quase vertical — sem essa troca o produto vetorial degenera justamente no caso
    mais comum, que é o pilar.

    Com `rotacao = 0`:
      * barra horizontal → eixo forte **vertical** (é o que se espera de uma viga);
      * barra vertical   → eixo forte no **X global**; o pilar do galpão, cuja alma
        fica no plano do pórtico, pede `rotacao = 90`.
    """
    w = normalizar(direcao)
    aux = (0.0, 0.0, 1.0) if abs(w[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = normalizar(produto_vetorial(aux, w))
    v = normalizar(produto_vetorial(w, u))
    if rotacao:
        c, s = math.cos(math.radians(rotacao)), math.sin(math.radians(rotacao))
        u, v = (somar(_mult(u, c), _mult(v, s)),
                somar(_mult(u, -s), _mult(v, c)))
    return u, v, w


# =====================================================================================
# 2. Utilidades de polígono 2D
# =====================================================================================

def area_assinada(contorno: Sequence[Ponto2]) -> float:
    """Área com sinal (positiva no sentido anti-horário), em mm²."""
    s = 0.0
    n = len(contorno)
    for i in range(n):
        x1, y1 = contorno[i][0], contorno[i][1]
        x2, y2 = contorno[(i + 1) % n][0], contorno[(i + 1) % n][1]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def area_contorno(contorno: Sequence[Ponto2]) -> float:
    """Área absoluta do polígono, em mm²."""
    return abs(area_assinada(contorno))


def centroide_contorno(contorno: Sequence[Ponto2]) -> Ponto2:
    """Centroide da **área** do polígono (não a média dos vértices)."""
    a = area_assinada(contorno)
    if abs(a) < 1e-12:
        return centroide(contorno)[:2]
    cx = cy = 0.0
    n = len(contorno)
    for i in range(n):
        x1, y1 = contorno[i][0], contorno[i][1]
        x2, y2 = contorno[(i + 1) % n][0], contorno[(i + 1) % n][1]
        f = x1 * y2 - x2 * y1
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    return (cx / (6 * a), cy / (6 * a))


def orientar(contorno: Sequence[Ponto2], anti_horario: bool = True) -> List[Ponto2]:
    """Devolve o contorno no sentido pedido."""
    pts = [(float(p[0]), float(p[1])) for p in contorno]
    if (area_assinada(pts) < 0) == bool(anti_horario):
        pts.reverse()
    return pts


def _sem_repetidos(contorno: Sequence[Ponto2], tol: float = 1e-9) -> List[Ponto2]:
    """Remove pontos consecutivos coincidentes, inclusive o fechamento repetido."""
    pts: List[Ponto2] = []
    for p in contorno:
        q = (float(p[0]), float(p[1]))
        if not pts or math.dist(pts[-1], q) > tol:
            pts.append(q)
    while len(pts) > 1 and math.dist(pts[0], pts[-1]) <= tol:
        pts.pop()
    return pts


def _cruz(o: Ponto2, a: Ponto2, b: Ponto2) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _dentro_do_triangulo(p: Ponto2, a: Ponto2, b: Ponto2, c: Ponto2) -> bool:
    d1, d2, d3 = _cruz(a, b, p), _cruz(b, c, p), _cruz(c, a, p)
    neg = (d1 < -TOL) or (d2 < -TOL) or (d3 < -TOL)
    pos = (d1 > TOL) or (d2 > TOL) or (d3 > TOL)
    return not (neg and pos)


def _triangular_sem_cache(contorno: Sequence[Sequence[float]]) -> List[Tuple[int, int, int]]:
    """Triangula um polígono simples por *ear clipping*.

    Aceita contorno 2D `(x, y)` ou 3D (que é projetado no plano da própria face).
    Devolve triplas de índices **do contorno recebido**, sempre no sentido
    anti-horário do plano de trabalho, independentemente da orientação da entrada.

    Ear clipping é O(n²) e não trata polígono auto-interceptante; quando não acha
    mais orelha (polígono degenerado), fecha o que sobrou em leque em vez de
    levantar erro, porque uma face mal formada não pode derrubar o editor.
    """
    if contorno and len(contorno[0]) >= 3:
        pts2, _ = _projetar_no_plano(list(contorno))
    else:
        pts2 = [(float(p[0]), float(p[1])) for p in contorno]
    n = len(pts2)
    if n < 3:
        raise ErroDeDados("triangulação: o contorno precisa de pelo menos 3 pontos.")
    indices = list(range(n))
    if area_assinada(pts2) < 0:
        indices.reverse()
    tris: List[Tuple[int, int, int]] = []
    guarda = 0
    while len(indices) > 3 and guarda <= n * n + 16:
        guarda += 1
        m = len(indices)
        achou = False
        for k in range(m):
            i0, i1, i2 = indices[(k - 1) % m], indices[k], indices[(k + 1) % m]
            a, b, c = pts2[i0], pts2[i1], pts2[i2]
            if _cruz(a, b, c) <= TOL:                 # côncavo ou colinear
                continue
            livre = True
            for j in indices:
                if j in (i0, i1, i2):
                    continue
                q = pts2[j]
                # um polígono com furos costurados repete o vértice da ponte; um
                # ponto coincidente com o vértice da orelha não a invalida
                if (math.dist(q, a) < 1e-9 or math.dist(q, b) < 1e-9
                        or math.dist(q, c) < 1e-9):
                    continue
                if _dentro_do_triangulo(q, a, b, c):
                    livre = False
                    break
            if livre:
                tris.append((i0, i1, i2))
                indices.pop(k)
                achou = True
                break
        if not achou:                                  # degenerado: fecha em leque
            break
    for k in range(1, len(indices) - 1):
        tris.append((indices[0], indices[k], indices[k + 1]))
    return tris


def _projetar_no_plano(vertices: Sequence[Ponto]) -> Tuple[List[Ponto2], Tuple[Ponto, Ponto, Ponto]]:
    """Projeta uma face 3D no seu próprio plano, devolvendo os pontos 2D e o triedro."""
    n = normal_face(vertices)
    aux = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = normalizar(produto_vetorial(aux, n))
    v = normalizar(produto_vetorial(n, u))
    o = _v(vertices[0])
    pts = [(produto_escalar(subtrair(_v(p), o), u),
            produto_escalar(subtrair(_v(p), o), v)) for p in vertices]
    return pts, (u, v, n)


# ------------------------------------------------------------------ furos costurados

def _entre(a: Ponto2, b: Ponto2, p: Ponto2) -> bool:
    """Verdadeiro se `p`, já sabidamente colinear com a–b, cai dentro do segmento."""
    return (min(a[0], b[0]) - TOL <= p[0] <= max(a[0], b[0]) + TOL
            and min(a[1], b[1]) - TOL <= p[1] <= max(a[1], b[1]) + TOL)


def _cruzam(a: Ponto2, b: Ponto2, c: Ponto2, d: Ponto2, eps: float = 1e-7) -> bool:
    """Interseção de dois segmentos, contando o toque colinear."""
    d1, d2 = _cruz(c, d, a), _cruz(c, d, b)
    d3, d4 = _cruz(a, b, c), _cruz(a, b, d)
    if (((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps))
            and ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps))):
        return True
    for (p, q, r) in ((c, d, a), (c, d, b), (a, b, c), (a, b, d)):
        if abs(_cruz(p, q, r)) <= eps and _entre(p, q, r):
            return True
    return False


def _dentro_do_poligono(p: Ponto2, poligono: Sequence[Ponto2]) -> bool:
    """Ponto dentro do polígono, pela regra da paridade do raio horizontal."""
    dentro = False
    n = len(poligono)
    for i in range(n):
        a, b = poligono[i], poligono[(i + 1) % n]
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x > p[0]:
                dentro = not dentro
    return dentro


def _ponte(cadeia: Sequence[Ponto2], furo: Sequence[Ponto2],
           pendentes: Sequence[Sequence[Ponto2]]) -> Tuple[int, int]:
    """Par (vértice do furo, vértice da cadeia) que pode virar ponte, o mais curto.

    A ponte precisa ficar inteira dentro do material: não pode cruzar nenhuma aresta
    do contorno já costurado, do próprio furo ou de um furo que ainda falta costurar,
    e o seu meio tem que cair dentro do polígono e fora dos furos. Testar isso
    explicitamente custa O(n·m) por furo, mas é robusto — a busca por ângulo do
    algoritmo de Eberly erra quando duas pontes dividem o mesmo vértice, que é
    exatamente o caso de uma chapa de topo com oito furos alinhados.
    """
    n, m = len(cadeia), len(furo)
    pares = sorted(((k, j) for k in range(m) for j in range(n)),
                   key=lambda kj: math.dist(furo[kj[0]], cadeia[kj[1]]))
    for k, j in pares:
        M, P = furo[k], cadeia[j]
        if math.dist(M, P) < TOL:
            continue
        meio = ((P[0] + M[0]) / 2.0, (P[1] + M[1]) / 2.0)
        if not _dentro_do_poligono(meio, cadeia):
            continue
        if _dentro_do_poligono(meio, furo):
            continue
        if any(_dentro_do_poligono(meio, f) for f in pendentes):
            continue
        livre = True
        for i in range(n):
            k2 = (i + 1) % n
            if i == j or k2 == j:
                continue
            if _cruzam(M, P, cadeia[i], cadeia[k2]):
                livre = False
                break
        if livre:
            for i in range(m):
                k2 = (i + 1) % m
                if i == k or k2 == k:
                    continue
                if _cruzam(M, P, furo[i], furo[k2]):
                    livre = False
                    break
        if livre:
            for f in pendentes:
                mf = len(f)
                if any(_cruzam(M, P, f[i], f[(i + 1) % mf]) for i in range(mf)):
                    livre = False
                    break
        if livre:
            return k, j
    return pares[0] if pares else (0, 0)


def costurar_furos(externo: Sequence[Ponto2],
                   furos: Sequence[Sequence[Ponto2]]):
    """Junta contornos internos ao externo por pontes, virando um polígono simples.

    Devolve `(poligono, mapa)`, em que `mapa[i]` é o índice do ponto `poligono[i]`
    na lista global `externo + furo0 + furo1 + ...`. É assim que o furo de parafuso
    fica **aberto de verdade** na triangulação, e não só desenhado por cima.
    """
    ext = orientar(_sem_repetidos(externo), True)
    cadeia: List[Tuple[int, Ponto2]] = list(enumerate(ext))
    base = len(ext)
    lista = []
    for f in furos:
        fo = orientar(_sem_repetidos(f), False)         # furo no sentido horário
        if len(fo) >= 3:
            lista.append((base, fo))
        base += len(fo)
    lista.sort(key=lambda b: -max(p[0] for p in b[1]))
    for pos, (ini, fo) in enumerate(lista):
        pontos = [p for _, p in cadeia]
        pendentes = [f for _, f in lista[pos + 1:]]
        k, j = _ponte(pontos, fo, pendentes)
        anel = [(ini + (k + t) % len(fo), fo[(k + t) % len(fo)])
                for t in range(len(fo) + 1)]
        cadeia = cadeia[:j + 1] + anel + [cadeia[j]] + cadeia[j + 1:]
    return [p for _, p in cadeia], [i for i, _ in cadeia]


def _chave_contorno(pontos: Sequence[Sequence[float]]) -> tuple:
    """Contorno como tupla imutável, arredondada a 1e-6 mm, para servir de chave."""
    return tuple(tuple(round(float(c), 6) for c in p) for p in pontos)


@functools.lru_cache(maxsize=4096)
def _triangular_guardado(chave: tuple) -> Tuple[Tuple[int, int, int], ...]:
    return tuple(_triangular_sem_cache(list(chave)))


def triangular(contorno: Sequence[Sequence[float]]) -> List[Tuple[int, int, int]]:
    """Triangula um polígono simples por *ear clipping* (ver `_triangular_sem_cache`).

    O resultado fica guardado por contorno: peças com a mesma seção, como as terças de
    um galpão, reaproveitam a triangulação em vez de refazê-la uma a uma.
    """
    return list(_triangular_guardado(_chave_contorno(contorno)))


@functools.lru_cache(maxsize=2048)
def _triangular_com_furos_guardado(externo: tuple,
                                   furos: tuple) -> Tuple[Tuple[int, int, int], ...]:
    poligono, mapa = costurar_furos(list(externo), [list(f) for f in furos])
    return tuple((mapa[a], mapa[b], mapa[c]) for a, b, c in triangular(poligono))


def triangular_com_furos(externo: Sequence[Ponto2],
                         furos: Sequence[Sequence[Ponto2]]) -> List[Tuple[int, int, int]]:
    """Triangula um contorno com furos; índices na lista `externo + furos...`.

    Guardado por contorno e furos, como `triangular`: chapas iguais reaproveitam.
    """
    if not furos:
        return triangular(externo)
    return list(_triangular_com_furos_guardado(
        _chave_contorno(externo), tuple(_chave_contorno(f) for f in furos)))


# =====================================================================================
# 3. Seções transversais do catálogo
# =====================================================================================

_REGISTRO: Dict[str, Perfil] = {}


def registrar_perfil(p: Perfil) -> Perfil:
    """Guarda um perfil sintético (mísula, barra redonda) para o 3D achar pelo nome."""
    _REGISTRO[p.nome] = p
    return p


def _parse_num(txt: str) -> Optional[float]:
    try:
        return float(str(txt).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def barra_redonda(diametro_mm: float, nome: str = "") -> Perfil:
    """Perfil sintético de barra redonda maciça (tirantes e correntes)."""
    d_cm = diametro_mm / 10.0
    A = math.pi * d_cm ** 2 / 4
    nome = nome or "Barra redonda ø %g mm" % round(diametro_mm, 2)
    return Perfil(nome=nome, tipo="barra",
                  dados={"nome": nome, "tipo": "redonda", "d": diametro_mm,
                         "b": diametro_mm, "t": diametro_mm,
                         "massa": round(A * 0.785, 3), "A": round(A, 4)})


def barra_chata(largura_mm: float, espessura_mm: float, nome: str = "") -> Perfil:
    """Perfil sintético de barra chata (chapas cortadas em tira, gussets, tirantes)."""
    A = largura_mm * espessura_mm / 100.0
    nome = nome or "Barra chata %g × %g mm" % (largura_mm, espessura_mm)
    return Perfil(nome=nome, tipo="barra",
                  dados={"nome": nome, "tipo": "chata", "d": largura_mm,
                         "b": largura_mm, "t": espessura_mm,
                         "massa": round(A * 0.785, 3), "A": round(A, 4)})


def resolver_perfil(nome_ou_perfil) -> Perfil:
    """Aceita um `Perfil`, um nome do catálogo, um perfil registrado ou um nome de barra.

    Os perfis sintéticos do orquestrador ("Barra redonda ø 25 mm", "Mísula W …") não
    estão no catálogo; por isso há o registro e o reconhecimento do nome.
    """
    if isinstance(nome_ou_perfil, Perfil):
        return nome_ou_perfil
    nome = str(nome_ou_perfil or "").strip()
    if not nome:
        raise ErroDeDados("perfil não informado.")
    if nome in _REGISTRO:
        return _REGISTRO[nome]
    p = banco().get(nome)
    if p is not None:
        return p
    baixo = nome.lower().replace("ø", " ").replace("ø", " ")
    if "barra" in baixo or "chapa" in baixo or "redond" in baixo:
        nums = []
        for pedaco in (baixo.replace("×", " ").replace("x", " ")
                       .replace("mm", " ").split()):
            valor = _parse_num(pedaco)
            if valor is not None and valor > 0:
                nums.append(valor)
        if "chata" in baixo and len(nums) >= 2:
            return registrar_perfil(barra_chata(nums[0], nums[1], nome))
        if len(nums) >= 1:
            return registrar_perfil(barra_redonda(nums[0], nome))
    raise ErroDeDados(f"perfil fora do catálogo, sem geometria conhecida: {nome}")


def _dims(p: Perfil) -> dict:
    """Dimensões da seção em mm, resolvendo as diferenças de campo do catálogo.

    Segue a mesma leitura de `saida.desenhos._dims_perfil`, para que o 3D e o DXF
    mostrem exatamente a mesma peça.
    """
    dd = p.dados
    if p.tipo == "I":
        return dict(forma="I", h=p.d, b=p.bf, tw=p.tw, tf=p.tf)
    if p.tipo == "U":
        return dict(forma="U", h=p.d, b=p.bf, tw=p.tw, tf=p.tf)
    if p.tipo == "Ue":
        partes = [x for x in str(dd.get("dim", "")).replace(",", ".").split("×")]
        lab = 0.0
        if len(partes) >= 4:
            lab = _parse_num(partes[2]) or 0.0
        if not str(p.nome).strip().lower().startswith("ue"):
            lab = 0.0                       # "U 100×50×2,00 (FF)": sem enrijecedor
        return dict(forma="Ue", h=p.d, b=p.bf, tw=p.tw, tf=p.tw, lab=lab)
    if p.tipo == "L":
        b = dd.get("b") or p.bf
        return dict(forma="L", h=b, b=b, tw=dd.get("t", p.tw), tf=dd.get("t", p.tw))
    if p.tipo == "tubo":
        if dd.get("tipo") == "redondo":
            D = dd.get("D", p.d)
            return dict(forma="tubo_redondo", h=D, b=D, tw=dd.get("t", p.tw),
                        tf=dd.get("t", p.tw))
        return dict(forma="tubo_retangular", h=dd.get("h", p.d), b=dd.get("b", p.bf),
                    tw=dd.get("t", p.tw), tf=dd.get("t", p.tw))
    if p.tipo == "barra":
        if dd.get("tipo") == "chata":
            return dict(forma="barra_chata", h=dd.get("t", p.tw), b=dd.get("b", p.bf),
                        tw=dd.get("t", p.tw), tf=dd.get("t", p.tw))
        D = dd.get("d") or p.d
        return dict(forma="barra_redonda", h=D, b=D, tw=D, tf=D)
    return dict(forma="retangulo", h=p.d, b=p.bf or p.d, tw=p.tw, tf=p.tf)


def _arco(centro: Ponto2, raio: float, a0: float, a1: float, n: int) -> List[Ponto2]:
    """Pontos de um arco (ângulos em radianos), incluindo as duas pontas."""
    return [(centro[0] + raio * math.cos(a0 + (a1 - a0) * i / n),
             centro[1] + raio * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def _retangulo_arredondado(b: float, h: float, r: float, seg: int = 4) -> List[Ponto2]:
    """Retângulo b × h centrado na origem, com os quatro cantos arredondados."""
    r = max(0.0, min(r, b / 2 - TOL, h / 2 - TOL))
    x, y = b / 2 - r, h / 2 - r
    if r <= TOL:
        return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]
    pts: List[Ponto2] = []
    for cx, cy, a0 in ((x, -y, -math.pi / 2), (x, y, 0.0),
                       (-x, y, math.pi / 2), (-x, -y, math.pi)):
        pts += _arco((cx, cy), r, a0, a0 + math.pi / 2, seg)
    return _sem_repetidos(pts)


def _arredondar_polilinha(pts: Sequence[Ponto2], raio: float, seg: int = 4) -> List[Ponto2]:
    """Substitui cada vértice interno da polilinha aberta por um arco de raio `raio`."""
    if raio <= TOL or len(pts) < 3:
        return [tuple(p) for p in pts]
    saida: List[Ponto2] = [tuple(pts[0])]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        ua = (a[0] - b[0], a[1] - b[1])
        uc = (c[0] - b[0], c[1] - b[1])
        na, nc = math.hypot(*ua), math.hypot(*uc)
        if na < TOL or nc < TOL:
            continue
        ua, uc = (ua[0] / na, ua[1] / na), (uc[0] / nc, uc[1] / nc)
        cos = max(-1.0, min(1.0, ua[0] * uc[0] + ua[1] * uc[1]))
        ang = math.acos(cos)
        if ang < 1e-6 or abs(ang - math.pi) < 1e-6:
            saida.append(tuple(b))
            continue
        dist = min(raio / math.tan(ang / 2), na / 2, nc / 2)
        r = dist * math.tan(ang / 2)
        t1 = (b[0] + ua[0] * dist, b[1] + ua[1] * dist)
        t2 = (b[0] + uc[0] * dist, b[1] + uc[1] * dist)
        bis = (ua[0] + uc[0], ua[1] + uc[1])
        nb = math.hypot(*bis)
        if nb < TOL:
            saida.append(tuple(b))
            continue
        centro = (b[0] + bis[0] / nb * (r / math.sin(ang / 2)),
                  b[1] + bis[1] / nb * (r / math.sin(ang / 2)))
        a0 = math.atan2(t1[1] - centro[1], t1[0] - centro[0])
        a1 = math.atan2(t2[1] - centro[1], t2[0] - centro[0])
        while a1 - a0 > math.pi:
            a1 -= 2 * math.pi
        while a1 - a0 < -math.pi:
            a1 += 2 * math.pi
        saida += _arco(centro, r, a0, a1, seg)
    saida.append(tuple(pts[-1]))
    return _sem_repetidos_abertos(saida)


def _sem_repetidos_abertos(pts: Sequence[Ponto2], tol: float = 1e-9) -> List[Ponto2]:
    saida: List[Ponto2] = []
    for p in pts:
        q = (float(p[0]), float(p[1]))
        if not saida or math.dist(saida[-1], q) > tol:
            saida.append(q)
    return saida


def _contorno_de_espessura(linha_media: Sequence[Ponto2], t: float,
                           raio_interno: Optional[float] = None,
                           seg: int = 4) -> List[Ponto2]:
    """Contorno fechado de um perfil de espessura constante, dado o eixo da chapa.

    É como se fabrica um perfil formado a frio: uma tira de largura `t` dobrada ao
    longo da linha média. As dobras entram com raio interno `ri` (padrão `t`, da
    NBR 6355), o que reduz um pouco a área em relação ao canto vivo — a mesma
    redução que a tabela do catálogo já traz.
    """
    rm = (t if raio_interno is None else raio_interno) + t / 2.0
    pts = _arredondar_polilinha(linha_media, rm, seg)
    n = len(pts)
    esq: List[Ponto2] = []
    dir_: List[Ponto2] = []
    for i in range(n):
        if i == 0:
            tx, ty = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == n - 1:
            tx, ty = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        else:
            tx, ty = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        c = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / c, tx / c
        esq.append((pts[i][0] + nx * t / 2, pts[i][1] + ny * t / 2))
        dir_.append((pts[i][0] - nx * t / 2, pts[i][1] - ny * t / 2))
    return orientar(_sem_repetidos(esq + dir_[::-1]), True)


def _chanfro_I(g: dict, area_cm2: float) -> float:
    """Perna do chanfro que representa o raio de concordância do perfil I.

    O catálogo não traz o raio, mas traz a área. A diferença entre a área tabelada e
    a soma dos três retângulos (duas mesas e a alma) é exatamente a área dos quatro
    adoçamentos; distribuída em quatro triângulos de 45°, dá a perna `c`. Quando o
    catálogo não traz área (perfil sintético de mísula, por exemplo), o chanfro é
    nulo — e aí o contorno é o do perfil soldado, que é o certo para aquele caso.
    """
    h, b, tw, tf = g["h"], g["b"], g["tw"], g["tf"]
    retangulos = 2 * b * tf + (h - 2 * tf) * tw
    dA = area_cm2 * 100.0 - retangulos
    if dA <= 0 or not math.isfinite(dA):
        return 0.0
    c = math.sqrt(dA / 2.0)
    return min(c, (b - tw) / 2 * 0.95, (h - 2 * tf) / 2 * 0.95)


def _mesa_U(g: dict, area_cm2: float) -> float:
    """Espessura equivalente da mesa do U laminado, calibrada pela área de catálogo."""
    h, b, tw = g["h"], g["b"], g["tw"]
    den = 2.0 * (b - tw)
    if den <= 0 or area_cm2 <= 0:
        return tw
    tf = (area_cm2 * 100.0 - h * tw) / den
    return max(tw, min(tf, (h - tw) / 2.0))


def secao_com_furos(perfil) -> Tuple[List[Ponto2], List[List[Ponto2]]]:
    """Seção transversal: `(contorno externo, [contornos internos])`, em mm.

    O externo vem no sentido anti-horário e os internos no horário (é a convenção
    que a extrusão espera para gerar as normais apontando para fora do material).
    Tudo centrado no centroide da área.

    Formas cobertas: I/W/HP, U laminado, U e Ue formados a frio, cantoneira de abas
    iguais, tubo retangular e quadrado, tubo circular, barra redonda e barra chata.
    """
    p = resolver_perfil(perfil)
    g = _dims(p)
    forma = g["forma"]
    h, b, tw, tf = g["h"], g["b"], g["tw"], g["tf"]
    if not _finito(h, b, tw, tf) or h <= 0 or b <= 0:
        raise ErroDeDados(f"perfil {p.nome}: dimensões inválidas para a seção 3D.")
    externo: List[Ponto2] = []
    internos: List[List[Ponto2]] = []

    if forma == "I":
        c = _chanfro_I(g, p.A)
        y0, y1 = -h / 2, h / 2
        externo = [
            (-b / 2, y0), (b / 2, y0), (b / 2, y0 + tf), (tw / 2 + c, y0 + tf),
            (tw / 2, y0 + tf + c), (tw / 2, y1 - tf - c), (tw / 2 + c, y1 - tf),
            (b / 2, y1 - tf), (b / 2, y1), (-b / 2, y1), (-b / 2, y1 - tf),
            (-tw / 2 - c, y1 - tf), (-tw / 2, y1 - tf - c), (-tw / 2, y0 + tf + c),
            (-tw / 2 - c, y0 + tf), (-b / 2, y0 + tf)]
    elif forma == "U":
        tfu = _mesa_U(g, p.A)
        y0, y1 = -h / 2, h / 2
        externo = [
            (-b / 2, y0), (b / 2, y0), (b / 2, y0 + tfu), (-b / 2 + tw, y0 + tfu),
            (-b / 2 + tw, y1 - tfu), (b / 2, y1 - tfu), (b / 2, y1), (-b / 2, y1)]
    elif forma == "Ue":
        t = tw
        lab = g.get("lab", 0.0)
        xw = -b / 2 + t / 2                       # linha média da alma
        yf = h / 2 - t / 2                        # linha média das mesas
        xl = b / 2 - t / 2                        # linha média do enrijecedor
        if lab > t:
            media = [(xl, h / 2 - lab), (xl, yf), (xw, yf), (xw, -yf), (xl, -yf),
                     (xl, -(h / 2 - lab))]
        else:
            media = [(b / 2, yf), (xw, yf), (xw, -yf), (b / 2, -yf)]
        externo = _contorno_de_espessura(media, t)
    elif forma == "L":
        t = tw
        externo = [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + t),
                   (-b / 2 + t, -h / 2 + t), (-b / 2 + t, h / 2), (-b / 2, h / 2)]
    elif forma == "tubo_retangular":
        t = tw
        externo = _retangulo_arredondado(b, h, 2 * t, 6)
        internos = [orientar(_retangulo_arredondado(b - 2 * t, h - 2 * t, t, 6), False)]
    elif forma == "tubo_redondo":
        t = tw
        externo = _arco((0.0, 0.0), h / 2, 0.0, 2 * math.pi, LADOS_CIRCULO)[:-1]
        internos = [orientar(_arco((0.0, 0.0), max(h / 2 - t, TOL), 0.0, 2 * math.pi,
                                   LADOS_CIRCULO)[:-1], False)]
    elif forma == "barra_redonda":
        externo = _arco((0.0, 0.0), h / 2, 0.0, 2 * math.pi, LADOS_CIRCULO)[:-1]
    elif forma == "barra_chata":
        externo = [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]
    else:
        externo = [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]

    externo = orientar(_sem_repetidos(externo), True)
    internos = [orientar(_sem_repetidos(f), False) for f in internos if len(f) >= 3]

    # centraliza no centroide da área (o do retângulo envolvente erraria em U e L)
    a_ext = area_assinada(externo)
    cx, cy = centroide_contorno(externo)
    sx = a_ext * cx
    sy = a_ext * cy
    at = a_ext
    for f in internos:
        af = -abs(area_assinada(f))                # furo: área negativa
        cf = centroide_contorno(f)
        sx += af * cf[0]
        sy += af * cf[1]
        at += af
    if abs(at) > TOL:
        cx, cy = sx / at, sy / at
    externo = [(x - cx, y - cy) for x, y in externo]
    internos = [[(x - cx, y - cy) for x, y in f] for f in internos]
    if not _finito(externo) or any(not _finito(f) for f in internos):
        raise ErroDeDados(f"perfil {p.nome}: seção 3D com coordenada inválida.")
    return externo, internos


def secao(perfil) -> List[Ponto2]:
    """Contorno externo fechado da seção transversal, em mm, centrado no centroide."""
    return secao_com_furos(perfil)[0]


def area_secao(perfil) -> float:
    """Área da seção calculada pelo contorno (externo menos furos), em mm²."""
    ext, furos = secao_com_furos(perfil)
    return area_contorno(ext) - sum(area_contorno(f) for f in furos)


# =====================================================================================
# 4. Extrusão e malhas
# =====================================================================================

def _normalizar_contorno(contorno) -> Tuple[List[Ponto2], List[List[Ponto2]]]:
    """Aceita `[pontos]` ou `(externo, [internos])` e devolve na orientação correta."""
    externo, internos = contorno, []
    if isinstance(contorno, tuple) and len(contorno) == 2:
        primeiro, segundo = contorno
        # `(externo, [internos])` se o segundo item for uma lista de contornos
        # (ou uma lista vazia) — e não o segundo ponto de um contorno de dois pontos
        if isinstance(segundo, list) and (
                not segundo or (isinstance(segundo[0], (list, tuple))
                                and segundo[0]
                                and isinstance(segundo[0][0], (list, tuple)))):
            externo, internos = primeiro, list(segundo)
    externo = orientar(_sem_repetidos(externo), True)
    internos = [orientar(_sem_repetidos(f), False) for f in internos if len(f) >= 3]
    if len(externo) < 3:
        raise ErroDeDados("extrusão: contorno com menos de 3 pontos distintos.")
    return externo, internos


def extrudar(contorno, direcao: Ponto, comprimento: float, rotacao: float = 0.0,
             origem: Ponto = (0.0, 0.0, 0.0), centrado: bool = False,
             **kwargs) -> Solido:
    """Extruda um contorno 2D ao longo de `direcao` e devolve um `Solido` fechado.

    * `contorno` — lista de pontos `(x, y)` ou o par `(externo, [internos])`;
    * `direcao`  — vetor 3D (não precisa ser unitário);
    * `comprimento` — em mm, medido na direção;
    * `rotacao` — giro da seção em torno do próprio eixo, em graus;
    * `origem` — posição do centro da seção inicial;
    * `centrado` — quando verdadeiro, a origem fica no meio do comprimento.

    As tampas são trianguladas por *ear clipping* (com os furos costurados ao
    contorno externo, de modo que ficam realmente abertos) e as laterais saem em
    quadriláteros. As faces vêm com as normais apontando para fora.
    """
    if not _finito(comprimento) or abs(comprimento) < TOL:
        raise ErroDeDados("extrusão: comprimento nulo ou inválido.")
    externo, internos = _normalizar_contorno(contorno)
    u, v, w = base_local(direcao, rotacao)
    o = _v(origem)
    if centrado:
        o = somar(o, _mult(w, -comprimento / 2.0))
    if comprimento < 0:
        o = somar(o, _mult(w, comprimento))
        comprimento = -comprimento

    aneis = [externo] + internos
    plano: List[Ponto2] = []
    for anel in aneis:
        plano += anel
    tris = triangular_com_furos(externo, internos)

    n = len(plano)
    vertices: List[Ponto] = []
    for (x, y) in plano:                                   # base
        vertices.append(somar(o, somar(_mult(u, x), _mult(v, y))))
    topo = somar(o, _mult(w, comprimento))
    for (x, y) in plano:                                   # topo
        vertices.append(somar(topo, somar(_mult(u, x), _mult(v, y))))

    faces: List[List[int]] = []
    for (a, b, c) in tris:
        faces.append([a + n, b + n, c + n])                # tampa de cima: +w
        faces.append([c, b, a])                            # tampa de baixo: −w
    inicio = 0
    for anel in aneis:
        m = len(anel)
        for i in range(m):
            a, b = inicio + i, inicio + (i + 1) % m
            faces.append([a, b, b + n, a + n])
        inicio += m
    s = Solido(vertices=vertices, faces=faces, **kwargs)
    return s


def prisma(cantos: Sequence[Ponto], deslocamento: Ponto, **kwargs) -> Solido:
    """Prisma reto a partir de um polígono plano no espaço e um vetor de deslocamento.

    É o que gera telha, fechamento e pedestal: um polígono desenhado no plano da
    peça, puxado pela espessura. O polígono é reorientado para que as normais
    fiquem para fora.
    """
    pts = [_v(p) for p in cantos]
    if len(pts) < 3:
        raise ErroDeDados("prisma: o polígono precisa de pelo menos 3 pontos.")
    d = _v(deslocamento)
    if math.sqrt(produto_escalar(d, d)) < TOL:
        raise ErroDeDados("prisma: deslocamento nulo.")
    if produto_escalar(normal_face(pts), d) < 0:
        pts.reverse()
    m = len(pts)
    vertices = pts + [somar(p, d) for p in pts]
    faces: List[List[int]] = []
    for (a, b, c) in triangular(pts):
        faces.append([a + m, b + m, c + m])
        faces.append([c, b, a])
    for i in range(m):
        j = (i + 1) % m
        faces.append([i, j, j + m, i + m])
    return Solido(vertices=vertices, faces=faces, **kwargs)


def malha_barra(barra: Barra) -> Tuple[List[Ponto], List[List[int]]]:
    """Malha da barra: a seção do perfil posicionada no eixo, de `inicio` a `fim`.

    O eixo local segue `base_local`: o eixo forte da seção fica no plano definido
    por `barra.rotacao`, e o vetor auxiliar troca de Z para X quando a barra é
    vertical, para não degenerar justamente no pilar.

    `recorte_inicio` e `recorte_fim` encurtam a barra nas pontas (é o que representa
    o rebaixo para a chapa de topo).
    """
    if not isinstance(barra, Barra):
        raise ErroDeDados("malha_barra: a entidade não é uma Barra.")
    ini, fim = _v(barra.inicio), _v(barra.fim)
    if not _finito(ini, fim):
        raise ErroDeDados(f"barra {barra.nome or barra.id}: coordenada inválida.")
    L = math.dist(ini, fim)
    if L < TOL:
        raise ErroDeDados(f"barra {barra.nome or barra.id}: comprimento nulo.")
    d = normalizar(subtrair(fim, ini))
    r0 = max(0.0, float(barra.recorte_inicio or 0.0))
    r1 = max(0.0, float(barra.recorte_fim or 0.0))
    util = L - r0 - r1
    if util <= TOL:
        raise ErroDeDados(f"barra {barra.nome or barra.id}: os recortes consomem "
                          f"todo o comprimento ({L:.0f} mm).")
    s = extrudar(secao_com_furos(barra.perfil), d, util, barra.rotacao,
                 origem=somar(ini, _mult(d, r0)))
    return s.vertices, s.faces


def contorno_furo(x: float, y: float, diametro: float,
                  lados: int = LADOS_FURO) -> List[Ponto2]:
    """Polígono de um furo redondo, no sentido horário (é um contorno interno)."""
    r = max(float(diametro), 0.1) / 2.0
    return [(x + r * math.cos(-2 * math.pi * i / lados),
             y + r * math.sin(-2 * math.pi * i / lados)) for i in range(lados)]


def contorno_oblongo(x: float, y: float, largura: float, altura: float,
                     angulo: float = 0.0, lados: int = LADOS_FURO) -> List[Ponto2]:
    """Polígono de um furo oblongo (estádio), no sentido horário: `largura` é o
    comprimento total, `altura` a largura do rasgo; `angulo` em graus gira o rasgo."""
    larg, alt = max(float(largura), 0.1), max(float(altura), 0.1)
    if alt > larg:
        larg, alt = alt, larg
        angulo += 90.0
    r = alt / 2.0
    meio = (larg - alt) / 2.0
    n = max(4, lados // 2)
    pts: List[Ponto2] = []
    # semicírculo da direita (de +90° a -90°) e da esquerda (de -90° a -270°), horário
    for i in range(n + 1):
        a = math.pi / 2 - math.pi * i / n
        pts.append((meio + r * math.cos(a), r * math.sin(a)))
    for i in range(n + 1):
        a = -math.pi / 2 - math.pi * i / n
        pts.append((-meio + r * math.cos(a), r * math.sin(a)))
    ca, sa = math.cos(math.radians(angulo)), math.sin(math.radians(angulo))
    return [(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in pts]


def contorno_do_furo(f: dict) -> Optional[List[Ponto2]]:
    """Contorno de um furo da Chapa: {x, y, diametro} ou {x, y, largura, altura[, angulo]}."""
    if float(f.get("diametro", 0.0) or 0.0) > 0:
        return contorno_furo(f.get("x", 0.0), f.get("y", 0.0), f.get("diametro", 0.0))
    if float(f.get("largura", 0.0) or 0.0) > 0 and float(f.get("altura", 0.0) or 0.0) > 0:
        return contorno_oblongo(f.get("x", 0.0), f.get("y", 0.0), f["largura"], f["altura"], float(f.get("angulo", 0.0) or 0.0))
    return None


def malha_chapa(chapa: Chapa) -> Tuple[List[Ponto], List[List[int]]]:
    """Malha da chapa, com os furos **abertos** na triangulação (não só desenhados)."""
    if not isinstance(chapa, Chapa):
        raise ErroDeDados("malha_chapa: a entidade não é uma Chapa.")
    contorno = _sem_repetidos(chapa.contorno or [])
    if len(contorno) < 3:
        raise ErroDeDados(f"chapa {chapa.nome or chapa.id}: contorno com menos de "
                          f"3 pontos.")
    if not _finito(contorno) or not _finito(chapa.espessura):
        raise ErroDeDados(f"chapa {chapa.nome or chapa.id}: coordenada inválida.")
    if float(chapa.espessura) <= 0:
        raise ErroDeDados(f"chapa {chapa.nome or chapa.id}: espessura nula.")
    furos = [c for c in (contorno_do_furo(f) for f in (chapa.furos or [])) if c]
    ex = normalizar(chapa.eixo_x)
    ey = normalizar(chapa.eixo_y)
    nz = normalizar(produto_vetorial(ex, ey))
    if abs(produto_escalar(nz, nz)) < 0.5:
        raise ErroDeDados(f"chapa {chapa.nome or chapa.id}: eixos locais paralelos.")
    o = _v(chapa.origem)
    if chapa.centrada:
        o = somar(o, _mult(nz, -float(chapa.espessura) / 2.0))
    # a extrusão trabalha no seu próprio triedro; aqui a chapa já tem o dela, então
    # os pontos são levados para o espaço e o sólido é montado com a mesma receita
    externo, internos = _normalizar_contorno((contorno, furos))
    aneis = [externo] + internos
    plano: List[Ponto2] = []
    for anel in aneis:
        plano += anel
    tris = triangular_com_furos(externo, internos)
    n = len(plano)
    vertices: List[Ponto] = []
    for (x, y) in plano:
        vertices.append(somar(o, somar(_mult(ex, x), _mult(ey, y))))
    topo = somar(o, _mult(nz, float(chapa.espessura)))
    for (x, y) in plano:
        vertices.append(somar(topo, somar(_mult(ex, x), _mult(ey, y))))
    faces: List[List[int]] = []
    for (a, b, c) in tris:
        faces.append([a + n, b + n, c + n])
        faces.append([c, b, a])
    inicio = 0
    for anel in aneis:
        m = len(anel)
        for i in range(m):
            a, b = inicio + i, inicio + (i + 1) % m
            faces.append([a, b, b + n, a + n])
        inicio += m
    return vertices, faces


def malha(entidade) -> Tuple[List[Ponto], List[List[int]]]:
    """Malha de qualquer entidade com geometria (barra, chapa ou sólido)."""
    if isinstance(entidade, Barra):
        return malha_barra(entidade)
    if isinstance(entidade, Chapa):
        return malha_chapa(entidade)
    if isinstance(entidade, Solido):
        return list(entidade.vertices), [list(f) for f in entidade.faces]
    raise ErroDeDados("entidade sem geometria para malhar.")


def volume_malha(vertices: Sequence[Ponto], faces: Sequence[Sequence[int]]) -> float:
    """Volume de uma malha fechada, em mm³ (soma de tetraedros com sinal)."""
    v = 0.0
    for f in faces:
        for i in range(1, len(f) - 1):
            a, b, c = vertices[f[0]], vertices[f[i]], vertices[f[i + 1]]
            v += produto_escalar(a, produto_vetorial(b, c)) / 6.0
    return v


def peso_barra(barra: Barra) -> float:
    """Peso da barra pelo perfil do catálogo, em kg (massa linear × comprimento)."""
    p = resolver_perfil(barra.perfil)
    L = (barra.comprimento - max(0.0, barra.recorte_inicio)
         - max(0.0, barra.recorte_fim)) / 1000.0
    massa = p.massa or (p.A * 0.785 if p.A else 0.0)
    return massa * L


def peso_chapa(chapa: Chapa) -> float:
    """Peso da chapa, em kg (área líquida × espessura × massa específica)."""
    return chapa.area * float(chapa.espessura) * RHO_MM3


def peso_solido(solido: Solido, densidade: float = RHO) -> float:
    """Peso de um sólido fechado, em kg, para a densidade dada em kg/m³."""
    return solido.volume * densidade / 1e9


# =====================================================================================
# 5. Operações de edição
# =====================================================================================

def extrudar_face(solido: Solido, indice_face: int, distancia: float) -> Solido:
    """Push/pull do SketchUp: empurra uma face na direção da normal.

    Há dois casos, como no SketchUp:

    * **face de topo** — quando todas as outras faces que usam os vértices da face
      são vizinhas dela (compartilham uma aresta), os vértices são simplesmente
      transladados e as faces laterais acompanham, esticando ou encurtando. O
      volume varia de `área × distância` nos dois sentidos, e a malha continua
      fechada;
    * **face no meio de uma superfície** — os vértices são duplicados e a lateral
      nova é fechada com quadriláteros, que é o que faz nascer o ressalto.

    Distância positiva empurra no sentido da normal (para fora, aumentando o
    volume) e negativa puxa para dentro. Não há detecção de auto-interseção: puxar
    mais do que a espessura da peça produz um sólido inválido.

    Não altera o sólido recebido — devolve um sólido novo, para que o comando do
    editor desfaça trocando o objeto de volta.
    """
    if not isinstance(solido, Solido):
        raise ErroDeDados("extrudar_face: a entidade não é um Solido.")
    if not (0 <= indice_face < len(solido.faces)):
        raise ErroDeDados(f"extrudar_face: face {indice_face} não existe.")
    if not _finito(distancia) or abs(distancia) < TOL:
        raise ErroDeDados("extrudar_face: distância nula ou inválida.")
    novo = copy.deepcopy(solido)
    face = list(novo.faces[indice_face])
    n = normal_face([novo.vertices[i] for i in face])
    desl = _mult(n, float(distancia))
    m = len(face)
    arestas = {(min(face[k], face[(k + 1) % m]), max(face[k], face[(k + 1) % m]))
               for k in range(m)}
    conjunto = set(face)
    de_topo = True
    for k, outra in enumerate(novo.faces):
        if k == indice_face or not conjunto & set(outra):
            continue
        mo = len(outra)
        vizinha = any((min(outra[i], outra[(i + 1) % mo]),
                       max(outra[i], outra[(i + 1) % mo])) in arestas
                      for i in range(mo))
        if not vizinha:
            de_topo = False
            break
    if de_topo:
        for i in face:
            novo.vertices[i] = somar(novo.vertices[i], desl)
        return novo
    mapa = {}
    for i in face:
        mapa[i] = len(novo.vertices)
        novo.vertices.append(somar(novo.vertices[i], desl))
    laterais = []
    for k in range(m):
        a, b = face[k], face[(k + 1) % m]
        quad = [a, b, mapa[b], mapa[a]]
        if distancia < 0:
            quad.reverse()
        laterais.append(quad)
    novo.faces[indice_face] = [mapa[i] for i in face]
    novo.faces += laterais
    return novo


def offset_contorno(contorno: Sequence[Ponto2], distancia: float) -> List[Ponto2]:
    """Offset 2D de um polígono fechado, em mm (positivo = para fora).

    Cada aresta é deslocada pela sua normal e as arestas vizinhas são
    reinterceptadas. Cantos muito agudos e offsets maiores que o raio interno do
    polígono geram laços — o algoritmo **não** faz a limpeza topológica desses
    laços (isso exigiria um offset de Voronoi); a ferramenta do editor limita a
    distância a uma fração do menor lado.
    """
    pts = _sem_repetidos(contorno)
    if len(pts) < 3:
        raise ErroDeDados("offset: contorno com menos de 3 pontos.")
    if not _finito(distancia):
        raise ErroDeDados("offset: distância inválida.")
    horario = area_assinada(pts) < 0
    if horario:
        pts.reverse()
    n = len(pts)
    linhas = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        c = math.hypot(dx, dy)
        nx, ny = dy / c, -dx / c                  # normal externa do polígono CCW
        linhas.append(((a[0] + nx * distancia, a[1] + ny * distancia),
                       (b[0] + nx * distancia, b[1] + ny * distancia)))
    saida: List[Ponto2] = []
    for i in range(n):
        (p1, p2) = linhas[i - 1]
        (q1, q2) = linhas[i]
        d1 = (p2[0] - p1[0], p2[1] - p1[1])
        d2 = (q2[0] - q1[0], q2[1] - q1[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:                       # arestas paralelas: usa a ponta
            saida.append(q1)
            continue
        t = ((q1[0] - p1[0]) * d2[1] - (q1[1] - p1[1]) * d2[0]) / den
        saida.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    saida = _sem_repetidos(saida)
    if horario:
        saida.reverse()
    return saida


# ------------------------------------------------------------- transformações rígidas

def _matriz_rotacao(eixo: Ponto, angulo_graus: float):
    """Rotação de Rodrigues em torno de um eixo unitário, ângulo em graus."""
    x, y, z = normalizar(eixo)
    a = math.radians(angulo_graus)
    c, s, k = math.cos(a), math.sin(a), 1 - math.cos(a)
    return ((c + x * x * k, x * y * k - z * s, x * z * k + y * s),
            (y * x * k + z * s, c + y * y * k, y * z * k - x * s),
            (z * x * k - y * s, z * y * k + x * s, c + z * z * k))


def _aplicar(m, p: Ponto) -> Ponto:
    return (m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2],
            m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2],
            m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2])


def _transformar(entidade, f_ponto, f_vetor=None):
    """Aplica a transformação nos pontos que definem a entidade.

    Devolve **uma cópia**: nenhuma ferramenta altera o documento diretamente, como
    manda o princípio 2 do `GUIA_3D.md` (undo/redo por comando).
    """
    f_vetor = f_vetor or (lambda v: v)
    if isinstance(entidade, (list, tuple)) and entidade and isinstance(
            entidade[0], (list, tuple)):
        return [f_ponto(_v(p)) for p in entidade]
    if isinstance(entidade, (list, tuple)) and len(entidade) == 3 and isinstance(
            entidade[0], (int, float)):
        return f_ponto(_v(entidade))
    novo = copy.deepcopy(entidade)
    if isinstance(novo, Barra):
        novo.inicio = f_ponto(_v(novo.inicio))
        novo.fim = f_ponto(_v(novo.fim))
    elif isinstance(novo, Chapa):
        novo.origem = f_ponto(_v(novo.origem))
        novo.eixo_x = normalizar(f_vetor(_v(novo.eixo_x)))
        novo.eixo_y = normalizar(f_vetor(_v(novo.eixo_y)))
    elif isinstance(novo, Solido):
        novo.vertices = [f_ponto(_v(p)) for p in novo.vertices]
    elif isinstance(novo, Grupo):
        novo.origem = f_ponto(_v(novo.origem))
    else:
        raise ErroDeDados("entidade sem geometria para transformar.")
    return novo


def mover(entidade, delta: Ponto):
    """Translada a entidade (ou uma lista de pontos) por `delta`, em mm."""
    d = _v(delta)
    return _transformar(entidade, lambda p: somar(p, d))


def girar(entidade, eixo: Ponto, ponto: Ponto, angulo: float):
    """Gira `angulo` graus em torno da reta (`ponto`, `eixo`), regra da mão direita.

    Para uma `Barra`, gira o eixo; a orientação da seção continua sendo dada por
    `rotacao` sobre o triedro local, de modo que girar uma barra para fora do seu
    plano pode exigir acertar `rotacao` depois.
    """
    m = _matriz_rotacao(eixo, angulo)
    o = _v(ponto)
    return _transformar(entidade,
                        lambda p: somar(o, _aplicar(m, subtrair(p, o))),
                        lambda v: _aplicar(m, v))


def espelhar(entidade, ponto: Ponto, normal: Ponto):
    """Espelha no plano (`ponto`, `normal`).

    O espelhamento inverte a mão do triedro: num `Solido` as faces passariam a
    apontar para dentro, então a ordem dos vértices de cada face é invertida junto.
    """
    o, nrm = _v(ponto), normalizar(normal)

    def refletir(p):
        d = produto_escalar(subtrair(p, o), nrm)
        return subtrair(p, _mult(nrm, 2 * d))

    def refletir_vetor(v):
        return subtrair(v, _mult(nrm, 2 * produto_escalar(v, nrm)))

    novo = _transformar(entidade, refletir, refletir_vetor)
    if isinstance(novo, Solido):
        novo.faces = [list(reversed(f)) for f in novo.faces]
    return novo


def escalar(entidade, fator, ponto: Ponto = (0.0, 0.0, 0.0)):
    """Escala em torno de `ponto`. `fator` pode ser um número ou `(fx, fy, fz)`.

    Numa `Barra` só o eixo escala: a seção continua sendo a do perfil de catálogo,
    que não se deforma. Para mudar a seção, troque o perfil.
    """
    f = (fator, fator, fator) if isinstance(fator, (int, float)) else tuple(fator)
    o = _v(ponto)
    return _transformar(
        entidade,
        lambda p: (o[0] + (p[0] - o[0]) * f[0], o[1] + (p[1] - o[1]) * f[1],
                   o[2] + (p[2] - o[2]) * f[2]),
        lambda v: (v[0] * f[0], v[1] * f[1], v[2] * f[2]))


# ------------------------------------------------------------------ topologia simples

def dividir_aresta(solido: Solido, aresta: Tuple[int, int], ponto: Ponto) -> Solido:
    """Insere um vértice no meio de uma aresta e reparte as faces que a contêm.

    `aresta` é o par de índices de vértices. Todas as faces que tiverem os dois
    índices consecutivos (em qualquer ordem) ganham o vértice novo, o que mantém a
    malha fechada e sem vértice T.
    """
    if not isinstance(solido, Solido):
        raise ErroDeDados("dividir_aresta: a entidade não é um Solido.")
    a, b = int(aresta[0]), int(aresta[1])
    n = len(solido.vertices)
    if not (0 <= a < n and 0 <= b < n):
        raise ErroDeDados("dividir_aresta: índices de vértice fora da malha.")
    novo = copy.deepcopy(solido)
    idx = len(novo.vertices)
    novo.vertices.append(_v(ponto))
    achou = False
    for k, face in enumerate(novo.faces):
        m = len(face)
        nova: List[int] = []
        for i in range(m):
            nova.append(face[i])
            j = face[(i + 1) % m]
            if (face[i] == a and j == b) or (face[i] == b and j == a):
                nova.append(idx)
                achou = True
        novo.faces[k] = nova
    if not achou:
        raise ErroDeDados(f"dividir_aresta: a aresta ({a}, {b}) não existe na malha.")
    novo.arestas_vivas = [tuple(e) for e in novo.arestas_vivas
                          if set(e) != {a, b}] + [(a, idx), (idx, b)]
    return novo


def unir_solidos(a: Solido, b: Solido, tolerancia: float = 0.01, **kwargs) -> Solido:
    """União simples de dois sólidos: concatena e remove faces coincidentes.

    **Limitação documentada**: não é união booleana. Os vértices que coincidem
    dentro da tolerância são soldados e os pares de faces idênticas com orientação
    oposta (as faces de contato) são descartados. Serve para colar peças que se
    encostam face a face — que é o caso do editor ao juntar dois blocos. Sólidos
    que se **interpenetram** continuam com a geometria interna, e o volume
    resultante fica errado. Para isso seria preciso um BSP ou um kernel booleano,
    que está fora do escopo deste módulo.
    """
    if not isinstance(a, Solido) or not isinstance(b, Solido):
        raise ErroDeDados("unir_solidos: as duas entidades precisam ser sólidos.")
    vertices: List[Ponto] = []
    indice: Dict[Tuple[int, int, int], int] = {}
    esc = 1.0 / max(tolerancia, 1e-9)

    def por(p: Ponto) -> int:
        chave = (int(round(p[0] * esc)), int(round(p[1] * esc)), int(round(p[2] * esc)))
        if chave not in indice:
            indice[chave] = len(vertices)
            vertices.append(_v(p))
        return indice[chave]

    faces: List[List[int]] = []
    for s in (a, b):
        for f in s.faces:
            faces.append([por(s.vertices[i]) for i in f])
    # descarta faces degeneradas e pares coincidentes de orientação oposta
    limpas: List[List[int]] = []
    usados = set()
    chaves = []
    for f in faces:
        if len(set(f)) < 3:
            chaves.append(None)
            continue
        chaves.append(frozenset(f))
    for i, f in enumerate(faces):
        if i in usados or chaves[i] is None:
            continue
        par = None
        for j in range(i + 1, len(faces)):
            if j in usados or chaves[j] != chaves[i]:
                continue
            n1 = normal_face([vertices[k] for k in faces[i]])
            n2 = normal_face([vertices[k] for k in faces[j]])
            if produto_escalar(n1, n2) < -0.99:
                par = j
                break
        if par is None:
            limpas.append(f)
        else:
            usados.add(par)
            usados.add(i)
    return Solido(vertices=vertices, faces=limpas, **kwargs)


def secao_plano(solido: Solido, plano) -> List[Tuple[Ponto, Ponto]]:
    """Interseção do sólido com um plano: lista de segmentos, para a ferramenta de corte.

    `plano` é `(ponto, normal)`. Cada face devolve no máximo um segmento (o que vale
    para faces convexas, que é o que a triangulação produz). Os segmentos vêm soltos,
    sem encadear em polilinha — quem precisa de contorno fechado encadeia pelas
    pontas coincidentes.
    """
    if not isinstance(solido, Solido):
        raise ErroDeDados("secao_plano: a entidade não é um Solido.")
    p0, nrm = _v(plano[0]), normalizar(plano[1])
    segmentos: List[Tuple[Ponto, Ponto]] = []
    for face in solido.faces:
        pontos: List[Ponto] = []
        m = len(face)
        for i in range(m):
            a = _v(solido.vertices[face[i]])
            b = _v(solido.vertices[face[(i + 1) % m]])
            da = produto_escalar(subtrair(a, p0), nrm)
            db = produto_escalar(subtrair(b, p0), nrm)
            if abs(da) <= TOL:
                pontos.append(a)
                continue
            if da * db < 0:
                t = da / (da - db)
                pontos.append(somar(a, _mult(subtrair(b, a), t)))
        unicos: List[Ponto] = []
        for p in pontos:
            if all(math.dist(p, q) > 1e-6 for q in unicos):
                unicos.append(p)
        if len(unicos) >= 2:
            segmentos.append((unicos[0], unicos[-1]))
    return segmentos


# =====================================================================================
# 6. Conferência de malha (usada pelos testes e pela importação de IFC)
# =====================================================================================

def conferir_malha(vertices: Sequence[Ponto], faces: Sequence[Sequence[int]]) -> dict:
    """Diagnóstico de uma malha: fechada, faces planas, normais para fora.

    Devolve um dicionário com `fechada`, `volume`, `arestas_soltas`,
    `faces_degeneradas` e `planicidade` (o maior afastamento de um vértice ao plano
    médio da sua face, em mm).
    """
    arestas: Dict[Tuple[int, int], int] = {}
    degeneradas = 0
    planicidade = 0.0
    for f in faces:
        vs = [_v(vertices[i]) for i in f]
        if len(f) < 3 or area_face(vs) <= TOL:
            degeneradas += 1
            continue
        n = normal_face(vs)
        c = centroide(vs)
        for p in vs:
            planicidade = max(planicidade, abs(produto_escalar(subtrair(p, c), n)))
        m = len(f)
        for i in range(m):
            a, b = f[i], f[(i + 1) % m]
            chave = (min(a, b), max(a, b))
            arestas[chave] = arestas.get(chave, 0) + 1
    soltas = [e for e, k in arestas.items() if k != 2]
    return {"fechada": not soltas and not degeneradas,
            "volume": volume_malha(vertices, faces),
            "arestas_soltas": soltas,
            "faces_degeneradas": degeneradas,
            "planicidade": planicidade}
