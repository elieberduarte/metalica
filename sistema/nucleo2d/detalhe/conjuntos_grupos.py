# -*- coding: utf-8 -*-
"""Conjuntos iguais, instâncias, eixos e os furos das caixas.

Parte do detalhamento dos conjuntos (nucleo2d/detalhe/conjuntos.py é a fachada; dividido do conjuntos.py em
13/11/2026, sem mudar a lógica)."""
import collections
import heapq
import math
import re
import threading
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from nucleo.base import ErroDeDados
from nucleo3d.modelo import Documento, Solido, Chapa
from nucleo2d.desenho import Desenho, Linha, Polilinha, Texto
from nucleo2d.desenho import Cota as _Cota
from nucleo2d import vistas as _vistas
from saida.detalhamento import (Posicao, Furo, analisar, CLASSES, _vista, _desenhar_furos, RHO_ACO, _area_2d,
                                _arestas_dos_furos, _ordem_natural, _autovetores, _lacos_2d)
from saida.desenhos import _mm
from saida.dobras import com_bitola, com_bitola_e_mm

from nucleo2d.detalhe.base import (
    parafusos_posicionados, largura_da_chamada,  # noqa: E402
    ALTURA_CHAMADA,
    ALTURA_COTA,
    CAMADAS_PECAS,
    TIPOS_NOME,
    _Papel,
    _caixa,
    _cruz,
    _dot,
    _eh_redonda_perfil,
    _eixo_da_peca,
    _marcas,
    _norm,
    _registrar_camadas_de_pecas,
    _sub,
    _tipo_ifc,
    parafusos_no_conjunto)


def _classificar_pecas_do_conjunto(instancia: Sequence[Solido], eixos=None) -> Dict[str, str]:
    """{id da peça: camada} numa instância de conjunto: chapas, pilares e redondos pelo
    tipo; barras pela posição na elevação — banzo (quase horizontal e comprida),
    montante (quase vertical) ou diagonal. `eixos` = (u, v, origem) da vista; sem eles,
    os eixos do conjunto."""
    if eixos is None:
        c, u, v, w = _eixos_do_conjunto(instancia)
        u, v, w = _vistas.Vista(origem=c, normal=w, acima=v).eixos()
        origem = c
    else:
        u, v, origem = eixos
    fora: Dict[str, str] = {}
    barras = []
    us = [_dot(_sub(p, origem), u) for e in instancia for p in e.vertices]
    larg = (max(us) - min(us)) if us else 0.0
    for e in instancia:
        t = _tipo_ifc(e)
        perfil = str(_marcas(e).get("perfil") or e.nome or "")
        if t.startswith("IfcPlate") or isinstance(getattr(e, "parametrica", None), Chapa):
            fora[e.id] = "CHAPAS"
        elif _eh_redonda_perfil(perfil):
            fora[e.id] = "TIRANTES"
        else:
            # IfcColumn não quer dizer pilar: o TecnoMETAL exporta montantes e diagonais
            # assim; o que decide é a posição da barra na elevação
            if (e.atributos or {}).get("quebras"):
                fora[e.id] = "BANZOS"                # o joelho quebrado em retas é banzo
                continue
            eixo = _eixo_da_peca(e)
            if not eixo:
                fora[e.id] = "VIGAS"
                continue
            a, b = eixo
            pa = (_dot(_sub(a, origem), u), _dot(_sub(a, origem), v))
            pb = (_dot(_sub(b, origem), u), _dot(_sub(b, origem), v))
            comp = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
            ang = abs(math.degrees(math.atan2(pb[1] - pa[1], pb[0] - pa[0]))) % 180
            barras.append((e.id, comp, ang))
    for eid, comp, ang in barras:
        if (ang < 25.0 or ang > 155.0) and comp > 0.25 * larg:
            fora[eid] = "BANZOS"
        elif 75.0 <= ang <= 105.0:
            fora[eid] = "MONTANTES"
        else:
            fora[eid] = "DIAGONAIS"
    return fora


def _instancias(pecas: Sequence[Solido], folga: float = 8.0) -> List[List[Solido]]:
    """Separa as peças de um conjunto em instâncias por conectividade das caixas."""
    caixas = [_caixa(e) for e in pecas]
    n = len(pecas)
    pai = list(range(n))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    ordem = sorted(range(n), key=lambda i: caixas[i][0][0])
    for a in range(n):
        i = ordem[a]
        for b in range(a + 1, n):
            j = ordem[b]
            if caixas[j][0][0] - folga > caixas[i][0][1]:
                break
            ci, cj = caixas[i], caixas[j]
            if all(ci[k][0] - folga <= cj[k][1] and cj[k][0] - folga <= ci[k][1] for k in range(3)):
                pai[raiz(i)] = raiz(j)
    grupos = collections.defaultdict(list)
    for i in range(n):
        grupos[raiz(i)].append(pecas[i])
    return sorted(grupos.values(), key=lambda g: (min(_caixa(e)[0][0] for e in g), min(_caixa(e)[0][1] for e in g)))


def posicao_base(e) -> str:
    """A posição da peça para reconhecer as instâncias de um conjunto: a variante de furação de uma chapa ("P48 (b)",
    _separar_variantes, 01/10) é a mesma peça no lugar — senão o conjunto com uma chapa de furo redondo onde não há
    terça deixava de ser instância dele (o M19 do ÁGUA GELADA, as meias-tesouras que não se juntavam no resumo)."""
    return re.sub(r" \([b-z]\)$", "", str(_marcas(e).get("posicao") or e.nome))


def _multiplo(grupo: Sequence[Solido], unidade: collections.Counter) -> int:
    """k quando a composição do grupo é exatamente k × unidade; senão 0."""
    cont = collections.Counter(posicao_base(e) for e in grupo)
    if set(cont) != set(unidade) or not unidade:
        return 0
    ks = {cont[m] / unidade[m] for m in unidade}
    if len(ks) != 1:
        return 0
    k = next(iter(ks))
    return int(k) if k == int(k) and k >= 1 else 0


def _dividir(grupo: Sequence[Solido], k: int, unidade: collections.Counter) -> List[List[Solido]]:
    """Separa um grupo com k unidades encostadas (águas de um pórtico na cumeeira) em k
    partes de mesmo tamanho ao longo do eixo mais comprido do grupo; devolve as partes só
    quando cada uma tem a composição unitária, senão lista vazia."""
    if k <= 1 or len(grupo) % k:
        return []
    verts = [v for e in grupo for v in e.vertices]
    c, pca = _autovetores(verts)
    e1 = pca[0]

    def t_de(e):
        ce = [sum(v[i] for v in e.vertices) / len(e.vertices) for i in range(3)]
        return _dot(_sub(ce, c), e1)
    ordenado = sorted(grupo, key=t_de)
    tam = len(grupo) // k
    partes = [ordenado[i * tam:(i + 1) * tam] for i in range(k)]
    if all(collections.Counter(posicao_base(e) for e in p) == unidade for p in partes):
        return partes
    return []


def _centro(grupo: Sequence[Solido]):
    vs = [v for e in grupo for v in e.vertices]
    return tuple(sum(v[i] for v in vs) / len(vs) for i in range(3))


def _instancias_do_conjunto(lista: Sequence[Solido], unidade: collections.Counter, folga: float = 60.0) -> List[List[Solido]]:
    """Instâncias de um conjunto: grupos por conectividade das caixas; grupo com k unidades
    encostadas é dividido; fragmentos (composição contida na unitária, mas incompleta —
    a chapinha que não encosta em nada) juntam-se ao fragmento mais próximo enquanto a
    soma couber na composição unitária."""
    def comp(g):
        return collections.Counter(posicao_base(e) for e in g)

    def cabe(c):
        return all(unidade.get(k, 0) >= q for k, q in c.items())
    grupos: List[List[Solido]] = []
    for g in _instancias(lista, folga=folga):
        k = _multiplo(g, unidade)
        partes = _dividir(g, k, unidade) if k > 1 else []
        grupos.extend(partes or [g])
    completos = [g for g in grupos if comp(g) == unidade or not cabe(comp(g))]
    frag = [g for g in grupos if comp(g) != unidade and cabe(comp(g))]
    centros = [_centro(g) for g in frag]
    comps = [comp(g) for g in frag]
    # a cada passo junta o par mais próximo que ainda cabe na composição unitária (empate: o primeiro na ordem da lista). 27/10
    # (SESI, brises com as chapas da rodada 1): varrer todos os pares a cada junção era O(n³) e o resumo da obra não terminava
    # em 1 h — cada fragmento guarda o seu par mais próximo que cabe (com os de depois dele na lista) e a fila leva só esses; a
    # cada junção são refeitos os que apontavam para os dois juntados, e os outros só comparam com o fragmento novo (o par que
    # não cabia não passa a caber: a soma só cresce)
    n = len(frag)
    vivo = [True] * n
    viz: list = [None] * n          # (d, j): o par (i, j), j > i, mais próximo que cabe
    versao = [0] * n
    fila: list = []

    def cabe_par(a, b):
        ca, cb = comps[a], comps[b]
        return (all(unidade.get(k, 0) >= q + cb.get(k, 0) for k, q in ca.items())
                and all(unidade.get(k, 0) >= q for k, q in cb.items() if k not in ca))

    def marcar(i, m):
        viz[i] = m
        versao[i] += 1
        if m is not None:
            heapq.heappush(fila, (m[0], i, m[1], versao[i]))

    def refazer(i):
        # as distâncias de uma vez (numpy) e o primeiro que cabe na ordem (distância, posição) — o mesmo da varredura
        js = np.nonzero(vivos[i + 1:])[0] + (i + 1)
        m = None
        if len(js):
            ds = ((pts[js] - pts[i]) ** 2).sum(axis=1)
            for t in np.lexsort((js, ds)):
                if cabe_par(i, int(js[t])):
                    m = (float(ds[t]), int(js[t]))
                    break
        marcar(i, m)
    pts = np.array(centros, dtype=float).reshape(-1, 3)
    vivos = np.ones(n, dtype=bool)
    for i in range(n):
        refazer(i)
    while fila:
        _, i, j, v = heapq.heappop(fila)
        if not vivo[i] or v != versao[i]:
            continue
        frag[i] = frag[i] + frag[j]
        comps[i] = comps[i] + comps[j]
        centros[i] = _centro(frag[i])
        pts[i] = centros[i]
        vivo[j] = False
        vivos[j] = False
        refazer(i)
        ate_i = ((pts[:i] - pts[i]) ** 2).sum(axis=1)
        for x in range(n):
            if not vivo[x] or x == i:
                continue
            if viz[x] is not None and viz[x][1] in (i, j):
                refazer(x)
            elif x < i:
                d = float(ate_i[x])
                if (viz[x] is None or (d, i) < viz[x]) and cabe_par(x, i):
                    marcar(x, (d, i))
    return completos + [g for g, v in zip(frag, vivo) if v]


def _eixos_do_conjunto(pecas: Sequence[Solido]):
    """(centro, u, v, w): w é a direção de menor espalhamento (normal da elevação), v o
    mais vertical dos outros dois eixos, u = v × w."""
    verts = [v for e in pecas for v in e.vertices]
    c, pca = _autovetores(verts)
    # o eixo principal pelo banzo mais comprido, quando há banzo (barra paramétrica com papel "banzo") a menos de 5° da PCA:
    # a PCA de todos os vértices inclina com as chapas da ligação de um lado só, e a treliça saía torta na elevação, com a
    # cadeia de cotas irregular (PRATI, 13/10)
    banzo = None
    for e in pecas:
        b_ = getattr(e, "parametrica", None)
        if b_ is None or str(getattr(b_, "papel", "") or "") != "banzo" or not hasattr(b_, "inicio"):
            continue
        d_ = _sub(tuple(b_.fim), tuple(b_.inicio))
        L_ = math.sqrt(_dot(d_, d_))
        if L_ > 1.0 and (banzo is None or L_ > banzo[0]):
            banzo = (L_, tuple(k / L_ for k in d_))
    if banzo is not None:
        d_ = banzo[1]
        if _dot(d_, pca[0]) < 0:
            d_ = (-d_[0], -d_[1], -d_[2])
        if _dot(d_, pca[0]) > 0.9962:                      # até 5°
            p1 = _norm(tuple(pca[1][i] - _dot(pca[1], d_) * d_[i] for i in range(3)))
            p2 = _norm(_cruz(d_, p1))
            if _dot(p2, pca[2]) < 0:
                p2 = (-p2[0], -p2[1], -p2[2])
            pca = [d_, p1, p2]
    # a peça principal escolhida no 3D (Editar → Criar conjunto, 14/10/2026) manda no eixo da elevação, até 30° da PCA:
    # a viga com as chapas de topo, o pilar com a base
    principal = next((getattr(e, "parametrica", None) for e in pecas if _marcas(e).get("principal")
                      and hasattr(getattr(e, "parametrica", None), "inicio")), None)
    if principal is not None:
        d_ = _sub(tuple(principal.fim), tuple(principal.inicio))
        L_ = math.sqrt(_dot(d_, d_))
        if L_ > 1.0:
            d_ = tuple(k / L_ for k in d_)
            if _dot(d_, pca[0]) < 0:
                d_ = (-d_[0], -d_[1], -d_[2])
            if _dot(d_, pca[0]) > 0.866:
                p1 = _norm(tuple(pca[1][i] - _dot(pca[1], d_) * d_[i] for i in range(3)))
                p2 = _norm(_cruz(d_, p1))
                if _dot(p2, pca[2]) < 0:
                    p2 = (-p2[0], -p2[1], -p2[2])
                pca = [d_, p1, p2]
    # Convenção do gerador de vistas (Vista.eixos): observador em -w, direita = w × v.
    # Aqui u é escolhido primeiro e w = v × u fecha o triedro nessa convenção.
    ext = []
    for e_ in pca:
        ts = [_dot(_sub(p, c), e_) for p in verts]
        ext.append(max(ts) - min(ts))

    def para_direita(u):
        return (-u[0], -u[1], -u[2]) if (u[0] < -1e-9 or (abs(u[0]) <= 1e-9 and u[1] < 0)) else u
    z = (0.0, 0.0, 1.0)
    # conjunto linear (tirante com as chapinhas, viga de uma barra): sai deitado na
    # horizontal, para o comprimento total ser lido direto
    if ext[0] > 0 and ext[1] < 0.12 * ext[0]:
        u = para_direita(pca[0])
        if abs(pca[2][2]) > 0.8 and abs(u[2]) < 0.3:
            # deitado no plano horizontal (tirante de cobertura com as chapinhas): visto de cima
            w = (0.0, 0.0, -1.0)
            v = _norm(_cruz(u, w))
            return c, u, v, w
        if abs(_dot(u, z)) < 0.95:
            v = _norm(tuple(z[i] - _dot(z, u) * u[i] for i in range(3)))
        else:
            v = _norm(tuple(pca[1][i] - _dot(pca[1], u) * u[i] for i in range(3)))
        w = _norm(_cruz(v, u))
        return c, u, v, w
    # a normal da vista é o eixo mais fino do conjunto; a vertical do desenho é a
    # vertical da obra projetada nesse plano — a tesoura sai inclinada como está
    # montada, o pilar em pé. Conjunto deitado no plano horizontal (contraventamento
    # de cobertura) não tem vertical: o eixo mais comprido vai para a horizontal.
    w = pca[2]
    if abs(w[2]) > 0.8:
        u = para_direita(pca[0])
        v = _norm(_cruz(w, u))
        if v[1] < 0 and abs(v[1]) > abs(v[0]):
            v = (-v[0], -v[1], -v[2])
        w = _norm(_cruz(v, u))
        return c, u, v, w
    v = _norm(tuple(z[i] - _dot(z, w) * w[i] for i in range(3)))
    u = para_direita(_norm(_cruz(v, w)))
    w = _norm(_cruz(v, u))
    return c, u, v, w


def _assinatura_conjunto(instancia: Sequence[Solido], fundidas: Optional[Dict[str, str]] = None) -> dict:
    """O que identifica o detalhe de um conjunto: composição (por posição fundida),
    extensões principais, posição relativa de cada peça e o lado para que a tesoura
    sobe no desenho. Comparar com _conjuntos_iguais, que usa tolerâncias — décimos de
    milímetro não separam duas tesouras iguais."""
    fundidas = fundidas or {}
    verts = [v for e in instancia for v in e.vertices]
    c, pca = _autovetores(verts)
    ext = []
    for e_ in pca:
        ts = [_dot(_sub(v, c), e_) for v in verts]
        ext.append(max(ts) - min(ts))
    pecas: Dict[str, List[Tuple[float, float]]] = collections.defaultdict(list)
    for e in instancia:
        m = _marcas(e)
        marca = str(m.get("posicao") or e.nome)
        ce = [sum(v[i] for v in e.vertices) / len(e.vertices) for i in range(3)]
        d = _sub(ce, c)
        pecas[fundidas.get(marca, marca)].append((abs(_dot(d, pca[0])), abs(_dot(d, pca[1]))))
    return {"ext": tuple(ext), "pecas": {k: sorted(v) for k, v in pecas.items()}, "lado": _lado_do_conjunto(instancia)}


def _lado_do_conjunto(instancia: Sequence[Solido]) -> int:
    """+1 quando o conjunto sobe para a direita no desenho, −1 para a esquerda, 0 quando
    é simétrico ou reto: a água esquerda e a direita de um pórtico são espelhadas, e o
    usuário quer um detalhe de cada lado."""
    try:
        c, u, v, w = _eixos_do_conjunto(instancia)
        u, v, w = _vistas.Vista(origem=c, normal=w, acima=v).eixos()
    except Exception:                                 # noqa: BLE001
        return 0
    # pelos vértices (não pelos centros das peças): um conjunto de poucas peças, com a
    # barra atravessando tudo, ainda tem o que comparar em cada quarto
    pontos = [(_dot(_sub(p, c), u), _dot(_sub(p, c), v)) for e in instancia for p in e.vertices]
    if not pontos:
        return 0
    us = [q[0] for q in pontos]
    vs = [q[1] for q in pontos]
    L, H = max(us) - min(us), max(vs) - min(vs)
    if L <= 0 or H <= 0:
        return 0
    # o conjunto linear — uma barra comprida com as peças pequenas nas pontas (o tirante, a agulha) — não tem
    # lado: a versão espelhada (o par de diagonais do X) é a mesma peça para a fábrica; saía com dois nomes,
    # CV.1 e CV.2, com o mesmo comprimento (pedido do usuário, 29/09). A meia-tesoura espelhada continua
    # um detalhe de cada lado
    ext_pecas = sorted((max(_dot(_sub(p, c), u) for p in e.vertices) - min(_dot(_sub(p, c), u) for p in e.vertices)
                        for e in instancia if e.vertices), reverse=True)
    if ext_pecas and ext_pecas[0] >= 0.9 * L and (len(ext_pecas) == 1 or ext_pecas[1] <= 0.3 * L):
        return 0
    esq = [cv for cu, cv in pontos if cu < -0.25 * L]
    dir_ = [cv for cu, cv in pontos if cu > 0.25 * L]
    if not esq or not dir_:
        return 0
    dif = sum(dir_) / len(dir_) - sum(esq) / len(esq)
    if abs(dif) < 0.15 * H:
        return 0
    return 1 if dif > 0 else -1


#: Tolerâncias (mm) para dois conjuntos serem o mesmo detalhe.
TOLERANCIA_CONJUNTO_EXT = 3.0


TOLERANCIA_CONJUNTO_PECA = 8.0


def _conjuntos_iguais(a: dict, b: dict) -> bool:
    if a["lado"] != b["lado"] or set(a["pecas"]) != set(b["pecas"]):
        return False
    if any(abs(x - y) > TOLERANCIA_CONJUNTO_EXT for x, y in zip(a["ext"], b["ext"])):
        return False
    for marca, lista in a["pecas"].items():
        outra = list(b["pecas"][marca])
        if len(outra) != len(lista):
            return False
        for du, dv in lista:
            k = min(range(len(outra)), key=lambda i: abs(outra[i][0] - du) + abs(outra[i][1] - dv))
            if abs(outra[k][0] - du) > TOLERANCIA_CONJUNTO_PECA or abs(outra[k][1] - dv) > TOLERANCIA_CONJUNTO_PECA:
                return False
            outra.pop(k)
    return True


#: Conjuntos com as mesmas dimensões (a esta tolerância, mm) e pelo menos esta fração
#: de peças em comum são o mesmo detalhe, com a diferença de composição anotada.
TOLERANCIA_CONJUNTO_SEMELHANTE = 20.0


FRACAO_COMUM_CONJUNTO = 0.75


def _furos_dos_parafusos_da_caixa(p, doc, instancia, origem, u, v, w, u0, v0, esc, barras_furadas=()) -> int:
    """Na viga caixote, o tubo não traz o furo modelado: o que diz qual travessa é furada é o parafuso que a
    atravessa (os 6 M12.7 da T1 do Vicente passam pelas 3 travessas TQ1 de 150, para o suporte da laje). Marca o
    furo (d + 1,5 mm, como nas chapas) no ponto em que o eixo do parafuso cruza a travessa, com a chamada do
    diâmetro no primeiro — "diferenciando os que vão furo" (pedido do usuário, 13/10). Devolve quantos marcou."""
    from nucleo2d.detalhe.base import _fixadores, _so_parafusos, _nome_do_parafuso
    from saida.detalhamento import _autovetores
    caixas = [(e, _caixa(e)) for e in instancia if getattr(e, "vertices", None) and not _tipo_ifc(e).startswith("IfcPlate")]
    if not caixas:
        return 0
    minimo = [min(cx[i][0] for _e, cx in caixas) - 20.0 for i in range(3)]
    maximo = [max(cx[i][1] for _e, cx in caixas) + 20.0 for i in range(3)]
    marcados = 0
    # o furo que a malha da barra já trouxe (o furo de verdade no tubo, 13/10) já está marcado: não repete
    vistos: set = {(round(f_["p2"][0]), round(f_["p2"][1])) for b_ in (barras_furadas or []) for f_ in (b_.get("furos") or [])
                   if f_.get("p2")}
    larg_u = max(_dot(_sub(q, origem), u) for _e, _cx in caixas for q in _e.vertices) - u0
    for f in _so_parafusos(_fixadores(doc)):
        cc = tuple(sum(q[i] for q in f.vertices) / len(f.vertices) for i in range(3))
        if not all(minimo[i] <= cc[i] <= maximo[i] for i in range(3)):
            continue
        _, pca = _autovetores(f.vertices)
        ext = []
        for ax in pca:
            ts = [_dot(_sub(q, cc), ax) for q in f.vertices]
            ext.append(max(ts) - min(ts))
        eixo_f = pca[ext.index(max(ext))]
        if abs(_dot(tuple(eixo_f), w)) < 0.7:              # só o parafuso que atravessa o plano da vista (fura a face)
            continue
        nome, pela_porca = _nome_do_parafuso(f, ext)
        if pela_porca or ext[0] <= 1.5 * ext[1]:
            continue
        # a travessa que o parafuso atravessa: a peça da caixa em cujo volume está o centro dele
        if not any(all(cx[k][0] - 2.0 <= cc[k] <= cx[k][1] + 2.0 for k in range(3)) for _e, cx in caixas):
            continue
        m_d = re.search(r"M\s*([\d.,]+)", nome)
        d_f = float(m_d.group(1).replace(",", ".")) if m_d else 12.7
        d_furo = round(d_f + 1.5, 1)
        x = _dot(_sub(cc, origem), u) - u0
        y = _dot(_sub(cc, origem), v) - v0
        if (round(x), round(y)) in vistos:                   # o parafuso da outra face, no mesmo ponto da vista
            continue
        vistos.add((round(x), round(y)))
        r = d_furo / 2.0
        p.circulo(x, y, r, "FURO")
        p.linha(x - 1.6 * r, y, x + 1.6 * r, y, "FURO")
        p.linha(x, y - 1.6 * r, x, y + 1.6 * r, "FURO")
        if marcados == 0:
            lado = -1.0 if x > larg_u / 2.0 else 1.0        # a chamada para dentro da caixa, não para fora da célula
            p.chamada(x + lado * r, y, x + lado * 10.0 * esc, y + 7.0 * esc, "FURO Ø%s" % ("%g" % d_furo).replace(".", ","), 2.0)
        marcados += 1
    return marcados


def _marcar_furos_das_barras(p, instancia, origem, u, v, u0, v0, esc) -> List[dict]:
    """Os furos das barras do conjunto na elevação: uma cruz no centro de cada furo — os da
    alma virada para baixo (fundo do banzo) não apareciam na vista. Devolve, por barra
    furada, o que o detalhe da furação precisa (`_detalhes_de_furos`)."""
    from nucleo2d.detalhe.celulas import _posicao_bruta, _furos_da_malha, _indices_do_furo
    from saida.detalhamento import analisar
    r = 1.2 * esc
    w = _cruz(u, v)
    barras = []
    for e in instancia:
        if _tipo_ifc(e).startswith("IfcPlate") or len(e.vertices or []) < 8:
            continue
        pos = _posicao_bruta(e, str(_marcas(e).get("posicao") or e.nome or e.id))
        pos.tipo_ifc = _tipo_ifc(e)
        try:
            analisar(pos)
        except Exception:                             # noqa: BLE001
            continue
        if pos.classe != "barra" or not pos.eixos:
            continue
        e1, e2, e3 = pos.eixos
        furos = []
        for f, laco, vista in _furos_da_malha(pos):
            nrm = e3 if vista == "frente" else e2
            c, _ = _indices_do_furo(e, laco, nrm, f.d / 2 + 1.0)
            x = _dot(_sub(c, origem), u) - u0
            y = _dot(_sub(c, origem), v) - v0
            p.linha(x - r, y, x + r, y, "FURO")
            p.linha(x, y - r, x, y + r, "FURO")
            furos.append({"x": f.x, "y": f.y, "d": f.d, "vista": vista, "p2": (x, y),
                          "escondido": abs(_dot(nrm, w)) < 0.5})
        if furos and pos.local:
            # as pontas da barra no desenho: de onde as cotas do detalhe partem
            i0 = min(range(len(pos.local)), key=lambda i: pos.local[i][0])
            i1 = max(range(len(pos.local)), key=lambda i: pos.local[i][0])
            pontas = [(_dot(_sub(e.vertices[i], origem), u) - u0, _dot(_sub(e.vertices[i], origem), v) - v0) for i in (i0, i1)]
            larg_face = {"frente": pos.H, "topo": max(q[2] for q in pos.local) - min(q[2] for q in pos.local)}
            larg_face["baixo"] = larg_face["topo"]                       # a outra mesa, mesma largura (D1, 11/10)
            # a altura do furo no detalhe é medida da borda da face: na alma o zero já é a
            # borda, na aba (vista de topo) o zero é o meio da peça
            base_face = {"frente": min(0.0, min(q[1] for q in pos.local)), "topo": min(q[2] for q in pos.local)}
            base_face["baixo"] = base_face["topo"]
            for f in furos:
                f["y"] = f["y"] - base_face[f["vista"]]
            barras.append({"marca": str(_marcas(e).get("posicao") or e.nome or e.id), "L": pos.L, "furos": furos,
                           "pontas": pontas, "larg_face": larg_face, "pos": pos})
    return barras


#: Escala dos detalhes de furação das barras da tesoura (1:ESCALA_DETALHE_FUROS).
ESCALA_DETALHE_FUROS = 5.0


#: Folga (mm reais) mostrada antes e depois dos furos no detalhe; trecho sem furo maior
#: que o dobro disso é interrompido (linha de quebra).
FOLGA_DETALHE_FUROS = 80.0


def _quebra(p, x, y0, y1, camada="VISTA-FINA"):
    """Linha de quebra (zigue-zague) vertical em x, de y0 a y1."""
    h = y1 - y0
    a = 0.12 * h
    p.polilinha([(x, y0 - 0.1 * h), (x, y0 + 0.4 * h), (x + a, y0 + 0.45 * h), (x - a, y0 + 0.55 * h),
                 (x, y0 + 0.6 * h), (x, y1 + 0.1 * h)], False, camada)


def _perfil_laminado(pos) -> bool:
    """W, I, H, HP: o perfil de alma cheia, que na tesoura se detalha inteiro (como a terça)."""
    return pos is not None and bool(re.match(r"^\s*(W|HP|I|H)\s*\d", str(pos.perfil or ""), re.I))


def _detalhes_de_furos(p, barras: Sequence[dict], nome_de, esc: float, y_topo: float) -> None:
    """Um detalhe ampliado por barra furada da tesoura, lado a lado abaixo da elevação: a
    face furada vista de frente, da ponta da barra até depois do último furo (trechos
    longos sem furo interrompidos), com a cadeia dos furos a partir da ponta e as linhas de
    furação. Na elevação, uma chamada com a letra do detalhe. Os furos da alma virada para
    baixo (escondidos na elevação) aparecem aqui.

    O perfil laminado (W, I, H — a tesoura de alma cheia do depósito químico, 29/09) não ganha
    detalhe ampliado nem chamada: a peça inteira, com a furação original e as cotas dos furos de
    ponta a ponta, é a célula da posição dela na prancha das barras (como a terça na dela). Desenhada
    também aqui, embaixo da tesoura em 1:50, ela saía ilegível e repetida (pedido do usuário, 29/09)."""
    k = max(1.0, esc / ESCALA_DETALHE_FUROS)
    x_cel = 0.0
    letras = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    vistos = set()
    n = 0
    ordem = sorted(barras, key=lambda b_: _ordem_natural(nome_de(b_["marca"])))
    for b in [b for b in ordem if not _perfil_laminado(b.get("pos"))]:
        nome = nome_de(b["marca"])
        for vista in ("frente", "topo", "baixo"):
            fs = [f for f in b["furos"] if f["vista"] == vista]
            if not fs or (nome, vista) in vistos:
                continue
            vistos.add((nome, vista))
            letra = letras[n % len(letras)]
            n += 1
            # o detalhe é uma célula própria na prancha (vai para os DETALHES, embaixo — pedido do usuário,
            # 28/09); a chamada com a letra, na elevação, fica com a tesoura
            atr_conj = p.atr
            # desenhado k vezes maior que a tesoura: a prancha escreve a escala real dele pelo "ampliacao" (D13, 11/10)
            p.atr = dict(atr_conj, detalhe_furos=letra, ampliacao=k)
            L = b["L"]
            # a ponta de referência: a mais perto dos furos
            do_fim = sum(f["x"] for f in fs) / len(fs) > L / 2
            dist = sorted(((L - f["x"]) if do_fim else f["x"], f["y"], f["d"]) for f in fs)
            ponta2d = b["pontas"][1 if do_fim else 0]
            outra2d = b["pontas"][0 if do_fim else 1]
            lado = "direita" if ponta2d[0] > outra2d[0] else "esquerda"
            H = float(b["larg_face"].get(vista) or 100.0)
            # colunas de furos (mesma distância da ponta) e os trechos mostrados
            cols: List[float] = []
            for d_, _, _ in dist:
                if not cols or d_ - cols[-1] > 2.0:
                    cols.append(d_)
            trechos = [[0.0, min(FOLGA_DETALHE_FUROS, cols[0])]]
            for c in cols:
                a_, b_ = max(0.0, c - FOLGA_DETALHE_FUROS), min(L, c + FOLGA_DETALHE_FUROS)
                if a_ - trechos[-1][1] <= 2 * FOLGA_DETALHE_FUROS:
                    trechos[-1][1] = max(trechos[-1][1], b_)
                else:
                    trechos.append([a_, b_])
            gap = 30.0

            def X(r):
                acum = 0.0
                for t0, t1 in trechos:
                    if r <= t1 + 1e-6:
                        return x_cel + (acum + max(0.0, r - t0)) * k
                    acum += (t1 - t0) + gap
                return x_cel + (acum - gap) * k
            y0 = y_topo - H * k
            # contorno da face: linhas de cima e de baixo por trecho, ponta à esquerda
            for t0, t1 in trechos:
                p.linha(X(t0), y0, X(t1), y0, "ACO")
                p.linha(X(t0), y_topo, X(t1), y_topo, "ACO")
            p.linha(X(0.0), y0, X(0.0), y_topo, "ACO")
            for i_, (t0, t1) in enumerate(trechos):
                if i_ > 0:
                    _quebra(p, X(t0), y0, y_topo)
                if i_ < len(trechos) - 1 or t1 < L - 1.0:
                    _quebra(p, X(t1), y0, y_topo)
            for d_, fy, diam in dist:
                p.circulo(X(d_), y0 + fy * k, diam / 2 * k, "FURO")
            # cadeia da ponta aos furos (medidas reais) e as linhas de furação
            nos = [0.0] + cols
            for i_ in range(len(nos) - 1):
                p.cota_h(X(nos[i_]), X(nos[i_ + 1]), y0, -8.0, texto="%d" % round(nos[i_ + 1] - nos[i_]))
            # e do último furo até a outra ponta (pedido do usuário, 28/09: "para não gerar dúvida"): até a
            # quebra do desenho, com a medida real
            if L - cols[-1] > 1.0:
                p.cota_h(X(cols[-1]), X(min(L, trechos[-1][1])), y0, -8.0, texto="%d" % round(L - cols[-1]))
            # as linhas de furação: furos a até 3 mm um do outro são a mesma linha (24 e 26 mm davam duas
            # cotas encavaladas — "2" e "246", 28/09)
            linhas_y = []
            for v_ in sorted(fy for _, fy, _ in dist):
                if linhas_y and v_ - linhas_y[-1][-1] <= 3.0:
                    linhas_y[-1].append(v_)
                else:
                    linhas_y.append([v_])
            linhas_y = [round(sum(g_) / len(g_)) for g_ in linhas_y]
            ys = [0.0] + [float(v_) for v_ in linhas_y] + [H]
            x_fim = X(trechos[-1][1])
            for i_ in range(len(ys) - 1):
                if ys[i_ + 1] - ys[i_] > 0.5:
                    p.cota_v(y0 + ys[i_] * k, y0 + ys[i_ + 1] * k, x_fim, 8.0, texto="%d" % round(ys[i_ + 1] - ys[i_]))
            escondido = any(f["escondido"] for f in fs)
            h = 2.2 * esc
            p.texto(x_cel, y_topo + 3.0 * esc + 1.2 * h, "DETALHE %s – FUROS DE %s" % (letra, nome), h)
            p.texto(x_cel, y_topo + 3.0 * esc, "da ponta %s%s" % (lado, " · face escondida na elevação" if escondido else ""), 1.8 * esc)
            p.atr = atr_conj
            # chamada na elevação: círculo em volta dos furos e a letra
            xs_e = [f["p2"][0] for f in fs]
            ys_e = [f["p2"][1] for f in fs]
            cx, cy = (min(xs_e) + max(xs_e)) / 2, (min(ys_e) + max(ys_e)) / 2
            raio = max(6.0 * esc, 0.6 * max(max(xs_e) - min(xs_e), max(ys_e) - min(ys_e)))
            # a marca na elevação leva a letra: na prancha, a linha de chamada do detalhe vem até ela
            p.atr = dict(atr_conj, marca_furos=letra)
            p.circulo(cx, cy, raio, "COTA")
            p.texto(cx + raio * 0.75, cy - raio * 0.75 - 2.5 * esc, letra, 2.5 * esc, "COTA")
            p.atr = atr_conj
            x_cel = x_fim + 30.0 * esc


def _conjuntos_semelhantes(a: dict, b: dict) -> bool:
    """Mesmo lado, mesmas dimensões principais e composição quase igual: a tesoura de
    ponta com outra chapa de base ou uma diagonal a menos vai para a célula da tesoura
    corrente (pedido do usuário: um detalhe por lado), com a diferença escrita."""
    if a["lado"] != b["lado"]:
        return False
    # 20 mm ou 3 % da dimensão: a chapa de base maior deixa a tesoura de ponta 28 mm
    # mais alta e ela continua sendo a mesma tesoura
    if any(abs(x - y) > max(TOLERANCIA_CONJUNTO_SEMELHANTE, 0.03 * max(x, y)) for x, y in zip(a["ext"][:2], b["ext"][:2])):
        return False
    ca = collections.Counter({k: len(v) for k, v in a["pecas"].items()})
    cb = collections.Counter({k: len(v) for k, v in b["pecas"].items()})
    comum = sum(min(ca[k], cb.get(k, 0)) for k in ca)
    return comum >= FRACAO_COMUM_CONJUNTO * max(sum(ca.values()), sum(cb.values()), 1)


def _diferenca_de_composicao(lider: dict, outra: dict) -> str:
    """"+P26 x1; -P1 x1": o que `outra` tem a mais e a menos que o conjunto líder."""
    a = collections.Counter({k: len(v) for k, v in outra["pecas"].items()})
    b = collections.Counter({k: len(v) for k, v in lider["pecas"].items()})
    mais = sorted((k for k in a if a[k] > b.get(k, 0)), key=_ordem_natural)
    menos = sorted((k for k in b if b[k] > a.get(k, 0)), key=_ordem_natural)
    partes = []
    if mais:
        partes.append("+" + ", ".join("%s x%d" % (k, a[k] - b.get(k, 0)) for k in mais))
    if menos:
        partes.append("-" + ", ".join("%s x%d" % (k, b[k] - a.get(k, 0)) for k in menos))
    return "; ".join(partes)


def _agrupar_conjuntos_iguais(candidatos, fundidas: Optional[Dict[str, str]] = None) -> List[Tuple[dict, list]]:
    """Candidatos (conj, lista, inst, n, unidade, aviso) iguais (a menos das tolerâncias)
    ou semelhantes (mesmas dimensões, composição quase igual) na mesma célula; a ordem
    dos candidatos manda (o primeiro lidera). Devolve [(assinatura do líder, grupo)];
    cada candidato do grupo ganha um 7º campo: a diferença de composição para o líder."""
    grupos: List[Tuple[dict, list]] = []
    for cand in candidatos:
        ass = _assinatura_conjunto(cand[2], fundidas)
        for ass_g, grupo in grupos:
            # só os iguais dividem a célula: tesoura com outra furação (suporte a mais,
            # furo na alma do banzo) ou outra chapa é detalhe próprio (pedido do usuário em
            # 23/09 — antes as semelhantes iam juntas com a diferença anotada)
            if _conjuntos_iguais(ass_g, ass):
                grupo.append(tuple(cand) + (_diferenca_de_composicao(ass_g, ass),))
                break
        else:
            grupos.append((ass, [tuple(cand) + ("",)]))
    return grupos


def _sobrepoe(a, b, folga=0.0) -> bool:
    return a[0] < b[2] + folga and b[0] < a[2] + folga and a[1] < b[3] + folga and b[1] < a[3] + folga


def _casco(pts: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Casco convexo 2D (cadeia monótona de Andrew)."""
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in pts))
    if len(pts) <= 2:
        return pts

    def cruz2(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    baixo: List[Tuple[float, float]] = []
    for p in pts:
        while len(baixo) >= 2 and cruz2(baixo[-2], baixo[-1], p) <= 0:
            baixo.pop()
        baixo.append(p)
    cima: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(cima) >= 2 and cruz2(cima[-2], cima[-1], p) <= 0:
            cima.pop()
        cima.append(p)
    return baixo[:-1] + cima[:-1]
