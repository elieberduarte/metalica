# -*- coding: utf-8 -*-
"""Parte "conjuntos" do detalhamento (nucleo2d/detalhar.py é a fachada)."""
import collections
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo3d.modelo import Documento, Solido, Chapa
from nucleo3d import geometria as _geo
from nucleo2d.desenho import Desenho, Linha, Polilinha, Circulo, Arco, Texto, Cota
from nucleo2d import vistas as _vistas
from saida.detalhamento import (Posicao, Furo, analisar, CLASSES, _vista, _desenhar_furos, RHO_ACO, _area_2d,
                                _arestas_dos_furos, _ordem_natural, _autovetores, _lacos_2d)
from saida.desenhos import Estilo, _mm
from saida.dobras import com_bitola

from nucleo2d.detalhe.base import (  # noqa: E402
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


def _multiplo(grupo: Sequence[Solido], unidade: collections.Counter) -> int:
    """k quando a composição do grupo é exatamente k × unidade; senão 0."""
    cont = collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in grupo)
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
    if all(collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in p) == unidade for p in partes):
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
        return collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in g)

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
    for _ in range(len(frag)):
        melhor = None
        for i in range(len(frag)):
            for j in range(i + 1, len(frag)):
                if not cabe(comps[i] + comps[j]):
                    continue
                d = sum((centros[i][k] - centros[j][k]) ** 2 for k in range(3))
                if melhor is None or d < melhor[0]:
                    melhor = (d, i, j)
        if melhor is None:
            break
        _, i, j = melhor
        frag[i] = frag[i] + frag[j]
        comps[i] = comps[i] + comps[j]
        centros[i] = _centro(frag[i])
        del frag[j], comps[j], centros[j]
    return completos + frag


def _eixos_do_conjunto(pecas: Sequence[Solido]):
    """(centro, u, v, w): w é a direção de menor espalhamento (normal da elevação), v o
    mais vertical dos outros dois eixos, u = v × w."""
    verts = [v for e in pecas for v in e.vertices]
    c, pca = _autovetores(verts)
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
            # a altura do furo no detalhe é medida da borda da face: na alma o zero já é a
            # borda, na aba (vista de topo) o zero é o meio da peça
            base_face = {"frente": min(0.0, min(q[1] for q in pos.local)), "topo": min(q[2] for q in pos.local)}
            for f in furos:
                f["y"] = f["y"] - base_face[f["vista"]]
            barras.append({"marca": str(_marcas(e).get("posicao") or e.nome or e.id), "L": pos.L, "furos": furos,
                           "pontas": pontas, "larg_face": larg_face})
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


def _detalhes_de_furos(p, barras: Sequence[dict], nome_de, esc: float, y_topo: float) -> None:
    """Um detalhe ampliado por barra furada da tesoura, lado a lado abaixo da elevação: a
    face furada vista de frente, da ponta da barra até depois do último furo (trechos
    longos sem furo interrompidos), com a cadeia dos furos a partir da ponta e as linhas de
    furação. Na elevação, uma chamada com a letra do detalhe. Os furos da alma virada para
    baixo (escondidos na elevação) aparecem aqui."""
    k = max(1.0, esc / ESCALA_DETALHE_FUROS)
    x_cel = 0.0
    letras = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    vistos = set()
    n = 0
    for b in sorted(barras, key=lambda b_: _ordem_natural(nome_de(b_["marca"]))):
        nome = nome_de(b["marca"])
        for vista in ("frente", "topo"):
            fs = [f for f in b["furos"] if f["vista"] == vista]
            if not fs or (nome, vista) in vistos:
                continue
            vistos.add((nome, vista))
            letra = letras[n % len(letras)]
            n += 1
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
            linhas_y = sorted({round(fy) for _, fy, _ in dist})
            ys = [0.0] + [float(v_) for v_ in linhas_y] + [H]
            x_fim = X(trechos[-1][1])
            for i_ in range(len(ys) - 1):
                if ys[i_ + 1] - ys[i_] > 0.5:
                    p.cota_v(y0 + ys[i_] * k, y0 + ys[i_ + 1] * k, x_fim, 8.0, texto="%d" % round(ys[i_ + 1] - ys[i_]))
            escondido = any(f["escondido"] for f in fs)
            h = 2.2 * esc
            p.texto(x_cel, y_topo + 5.0 * esc + 1.2 * h, "DETALHE %s – FUROS DE %s  (1:%d)" % (letra, nome, round(esc / k)), h)
            p.texto(x_cel, y_topo + 5.0 * esc, "da ponta %s%s" % (lado, " · face escondida na elevação" if escondido else ""), 1.8 * esc)
            # chamada na elevação: círculo em volta dos furos e a letra
            xs_e = [f["p2"][0] for f in fs]
            ys_e = [f["p2"][1] for f in fs]
            cx, cy = (min(xs_e) + max(xs_e)) / 2, (min(ys_e) + max(ys_e)) / 2
            raio = max(6.0 * esc, 0.6 * max(max(xs_e) - min(xs_e), max(ys_e) - min(ys_e)))
            p.circulo(cx, cy, raio, "COTA")
            p.texto(cx + raio * 0.75, cy - raio * 0.75 - 2.5 * esc, letra, 2.5 * esc, "COTA")
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


def _trechos_curvos(pts: Sequence[Tuple[float, float]], fechada: bool) -> List[Tuple[int, int]]:
    """Índices (i, j) dos trechos em arco da polilinha: quatro ou mais segmentos curtos
    seguidos virando para o mesmo lado. Os índices são os vértices reto-antes e
    reto-depois do arco."""
    n = len(pts)
    if n < 6:
        return []
    segs = [(pts[(k + 1) % n][0] - pts[k][0], pts[(k + 1) % n][1] - pts[k][1]) for k in range(n if fechada else n - 1)]
    comp = [math.hypot(*s) for s in segs]
    if not comp:
        return []
    curto = 0.4 * max(comp)

    def giro(k):                       # ângulo entre o segmento k e o k+1, em graus com sinal
        a, b = segs[k % len(segs)], segs[(k + 1) % len(segs)]
        la, lb = comp[k % len(segs)], comp[(k + 1) % len(segs)]
        if la < 1e-6 or lb < 1e-6:
            return 0.0
        return math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))

    ns = len(segs)
    limite = ns if fechada else ns - 1
    trechos = []
    k = 0
    while k < limite:
        g = giro(k)
        if abs(g) < 1.0 or abs(g) > 30.0 or comp[(k + 1) % ns] > curto:
            k += 1
            continue
        sinal = 1 if g > 0 else -1
        j = k
        while j + 1 < limite and comp[(j + 1) % ns] <= curto:
            g2 = giro(j + 1)
            if abs(g2) < 1.0 or abs(g2) > 30.0 or (1 if g2 > 0 else -1) != sinal:
                break
            j += 1
        # vértices curvos: k+1 … j+1; retos de cada lado: k e j+2
        if j - k >= 3:
            trechos.append((k, j + 2))
        k = j + 2
    return trechos


#: Folga (mm) do trecho reto além do suporte de terça que ele segura, no chanfro do canto.
FOLGA_CHANFRO_SUPORTE = 100.0


def _dist_ponto_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _avanco_tangente(pts, i, j) -> Tuple[float, float]:
    """Quanto cada trecho reto vizinho do arco pts[i+1..j-1] avança (prolongado) até a
    tangente ao arco no meio dele: (do lado de i, do lado de j). A diagonal entre esses dois
    pontos envolve o arco por fora — a corda cortava por dentro, e a diagonal da treliça que
    chega na face de dentro do arco atravessava o banzo no desenho."""
    a, b = pts[i + 1], pts[j - 1]
    cx, cy = b[0] - a[0], b[1] - a[1]
    cl = math.hypot(cx, cy)
    if cl < 1e-6:
        return 0.0, 0.0
    nx, ny = -cy / cl, cx / cl
    meio = pts[i + 1:j]
    # o vértice do arco mais longe da corda é o meio dele; a tangente ali é paralela à corda
    m = max(meio, key=lambda q: abs((q[0] - a[0]) * nx + (q[1] - a[1]) * ny))
    t2 = (m[0] + cx, m[1] + cy)
    saida = []
    for ponta, longe in ((a, pts[i]), (b, pts[j])):
        x = _cruzamento(longe, ponta, m, t2)
        L = math.dist(ponta, longe)
        if x is None or L < 1e-6:
            saida.append(0.0)
            continue
        volta = ((ponta[0] - longe[0]) / L, (ponta[1] - longe[1]) / L)
        s = (x[0] - ponta[0]) * volta[0] + (x[1] - ponta[1]) * volta[1]
        saida.append(max(0.0, min(s, cl)))
    return saida[0], saida[1]


def _chanfrar_cantos(desenho: Desenho, novas: List, ids: set, apoios: Sequence = ()) -> List:
    """Troca cada arco das silhuetas das peças `ids` por uma **barra diagonal reta** — o
    chanfro que a fábrica faz, em vez de calandrar. Sem nada apoiado no canto, a diagonal é
    a tangente ao arco no meio dele (`_avanco_tangente`): os trechos retos se prolongam até
    ela e o banzo envolve o arco por fora, sem que a diagonal da treliça que chega no canto
    o atravesse. Quando um suporte de terça (`apoios`: caixas 2D das chapas) encosta no
    trecho reto logo depois do arco, esse trecho avança sobre o arco até passar do suporte
    com folga (FOLGA_CHANFRO_SUPORTE), e a diagonal vai do começo do arco até ali: o
    suporte não fica "voando" sobre a diagonal. Vale para a peça que é só o arco e para o
    arco no meio de uma silhueta fechada. O 3D fica com o arco do modelo.
    """
    saida = list(novas)
    preparadas = []
    recuos: Dict[tuple, float] = {}              # (peça, direção do trecho reto) → avanço
    for e in novas:
        if not isinstance(e, Polilinha) or (e.atributos or {}).get("origem") not in ids:
            continue
        pts = [tuple(p) for p in e.vertices]
        n = len(pts)
        if n < 6:
            continue
        # numa polilinha fechada, gira a lista até nenhum arco atravessar a emenda dela
        trechos = _trechos_curvos(pts, e.fechada)
        if e.fechada:
            for _ in range(n):
                if all(j < n for _, j in trechos):
                    break
                pts = pts[1:] + pts[:1]
                trechos = _trechos_curvos(pts, True)
        if not trechos:
            continue
        origem = (e.atributos or {}).get("origem")
        preparadas.append((e, pts, trechos, origem))
        # quanto cada trecho reto vizinho do arco precisa avançar para segurar um suporte
        for i, j in trechos:
            if j >= len(pts) or j - i < 3:
                continue
            corda = math.dist(pts[i + 1], pts[j - 1])
            for ponta, longe in ((pts[j - 1], pts[j]), (pts[i + 1], pts[i])):
                L = math.dist(ponta, longe)
                if L < 1e-6:
                    continue
                volta = ((ponta[0] - longe[0]) / L, (ponta[1] - longe[1]) / L)   # do reto para dentro do arco
                s = 0.0
                for (x0, y0, x1, y1) in apoios:
                    cantos = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                    if min(_dist_ponto_seg(q, ponta, longe) for q in cantos) > 60.0:
                        continue
                    alem = max((q[0] - ponta[0]) * volta[0] + (q[1] - ponta[1]) * volta[1] for q in cantos)
                    if alem > -FOLGA_CHANFRO_SUPORTE:
                        s = max(s, alem + FOLGA_CHANFRO_SUPORTE)
                if s > 0:
                    chave = (origem, round(math.degrees(math.atan2(volta[1], volta[0])) / 5.0))
                    recuos[chave] = min(max(recuos.get(chave, 0.0), s), 0.8 * corda)
    for e, pts, trechos, origem in preparadas:
        mudou = False
        nos_e = []                                  # as pontas da diagonal: os nós do chanfro
        for i, j in sorted(trechos, reverse=True):
            if j >= len(pts) or j - i < 3:
                continue
            # o arco vai de pts[i+1] a pts[j-1] (pts[i] e pts[j] são as outras pontas dos
            # trechos retos vizinhos): os vértices do meio saem, fica a diagonal
            a, b = pts[i + 1], pts[j - 1]
            tangente = _avanco_tangente(pts, i, j)
            novos = []
            for k_, (ponta, longe) in enumerate(((a, pts[i]), (b, pts[j]))):
                L = math.dist(ponta, longe)
                volta = ((ponta[0] - longe[0]) / L, (ponta[1] - longe[1]) / L) if L > 1e-6 else (0.0, 0.0)
                s = recuos.get((origem, round(math.degrees(math.atan2(volta[1], volta[0])) / 5.0)), 0.0)
                s = max(s, tangente[k_])
                novos.append((ponta[0] + volta[0] * s, ponta[1] + volta[1] * s))
            pts = pts[:i + 1] + novos + pts[j:]
            nos_e += novos
            mudou = True
        if not mudou:
            continue
        e.vertices = [(round(x, 2), round(y, 2)) for x, y in pts]
        e.atributos = dict(e.atributos or {}, chanfro="diagonal",
                           nos_chanfro=[[round(x, 2), round(y, 2)] for x, y in nos_e])
    return saida


#: Distância (mm) entre o nó do contorno de fora e o de dentro do mesmo perfil, para a
#: linha de emenda que atravessa o perfil; e o maior trecho reto que o banzo absorve.
EMENDA_MAX = 160.0
TRECHO_RETO_MAX = 1000.0


def _emendas_do_chanfro(desenho: Desenho, novas: List, ids: set, camada_de: Dict[str, str]) -> None:
    """Depois do chanfro, o canto da tesoura é feito de peças retas, como a fábrica monta:
    o banzo vai reto **até o nó** onde começa a diagonal do canto (o trecho reto curto da
    barra calandrada passa a ser do banzo), e cada nó ganha a **linha de emenda**
    atravessando o perfil (do contorno de fora ao de dentro)."""
    def perto(a, b, tol=3.0):
        return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol
    canto = [e for e in novas if isinstance(e, Polilinha) and (e.atributos or {}).get("nos_chanfro")]
    if not canto:
        return
    outras = [e for e in novas if isinstance(e, (Polilinha, Linha)) and (e.atributos or {}).get("origem") not in ids]
    banzos = [e for e in outras if e.camada == "BANZOS"]

    def vertices(e):
        return list(e.vertices) if isinstance(e, Polilinha) else [e.a, e.b]
    # 1) o banzo avança até o nó: o trecho reto entre o nó e a ponta que encosta no banzo sai.
    # Primeiro decide tudo com as posições originais (a ponta do banzo é a mesma para as
    # várias linhas da peça), depois move.
    juncoes = [w for b_ in banzos for w in vertices(b_)]
    movimentos = []                                  # (ponta antiga m, nó q)
    for e in canto:
        nos = [tuple(q) for q in e.atributos["nos_chanfro"]]
        vs = [tuple(q) for q in e.vertices]
        n = len(vs)
        eh_no = [any(perto(q, no_, 0.05) for no_ in nos) for q in vs]
        junta = [not eh_no[k] and any(perto(q, w) for w in juncoes) for k, q in enumerate(vs)]
        # sequências de vértices da emenda antiga com o banzo (o trecho reto curto) que
        # encostam num nó: saem, e a linha passa a ligar o nó ao próximo nó (a emenda) ou
        # termina no nó
        tirar = set()
        k = 0
        while k < n:
            if not junta[k]:
                k += 1
                continue
            ini = k
            while k < n and junta[k]:
                k += 1
            fim = k - 1                               # a sequência é ini..fim
            antes = ini - 1 if ini > 0 else (n - 1 if e.fechada else None)
            depois = fim + 1 if fim + 1 < n else (0 if e.fechada else None)
            bordas = [b for b in (antes, depois) if b is not None and eh_no[b]]
            if not bordas:
                continue
            if any(min(math.dist(vs[r], vs[b]) for b in bordas) > TRECHO_RETO_MAX for r in range(ini, fim + 1)):
                continue
            for r in range(ini, fim + 1):
                tirar.add(r)
                movimentos.append((vs[r], min((vs[b] for b in bordas), key=lambda q: math.dist(q, vs[r]))))
        if tirar:
            e.vertices = [v for r, v in enumerate(vs) if r not in tirar]
    # a ponta antiga m (emenda com o banzo) vai para o nó nas linhas do banzo: para o nó
    # mais perto dela entre os que a apontaram (contorno de fora ou de dentro)
    def destino(w):
        cand = [(math.dist(w, q), q) for m, q in movimentos if perto(w, m)]
        return min(cand)[1] if cand else w
    if movimentos:
        for o in outras:
            if o.camada == "CHAPAS":
                continue
            if isinstance(o, Polilinha):
                o.vertices = [destino(w) for w in o.vertices]
            else:
                o.a, o.b = destino(o.a), destino(o.b)
    # 2) a linha de emenda em cada nó: o nó do contorno de fora com o do de dentro
    por_origem: Dict[str, list] = collections.defaultdict(list)
    for e in canto:
        for q in e.atributos["nos_chanfro"]:
            q = (float(q[0]), float(q[1]))
            lista = por_origem[e.atributos.get("origem")]
            if not any(perto(q, w, 1.0) for w in lista):
                lista.append(q)
    for origem, nos in por_origem.items():
        usados = set()
        pares = sorted(((math.dist(nos[i], nos[j]), i, j) for i in range(len(nos)) for j in range(i + 1, len(nos))))
        for dd, i, j in pares:
            if i in usados or j in usados or not (5.0 < dd <= EMENDA_MAX):
                continue
            usados |= {i, j}
            desenho.add(Linha(camada=camada_de.get(origem, "VISTA"), a=nos[i], b=nos[j],
                              atributos=dict(next(e for e in canto if e.atributos.get("origem") == origem).atributos,
                                             emenda=True, chanfro=None, nos_chanfro=None)))


def _cruzamento(a0, a1, b0, b1):
    """Interseção das retas a0–a1 e b0–b1, ou None se paralelas."""
    r = (a1[0] - a0[0], a1[1] - a0[1])
    s = (b1[0] - b0[0], b1[1] - b0[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((b0[0] - a0[0]) * s[1] - (b0[1] - a0[1]) * s[0]) / den
    return (a0[0] + t * r[0], a0[1] + t * r[1])


def _rotular_barras(p: "_Papel", rotulos, esc: float, altura_papel: float = 1.8):
    """Rótulo de posição ao lado do meio de cada barra, deslocado na perpendicular da
    barra; quando cai em cima de outro rótulo, afasta-se mais um passo (até quatro)."""
    h = altura_papel * esc
    caixas = []
    for txt, (x, y), ang in rotulos:
        a = ang if ang <= 90 else ang - 180
        ra = math.radians(a)
        nx, ny = -math.sin(ra), math.cos(ra)
        larg = 0.75 * h * len(txt)
        meia = max(larg, h) / 2
        caixa = None
        for passo in range(4):
            d = (1.6 + 2.4 * passo) * esc
            cx, cy = x + nx * d, y + ny * d
            caixa = (cx - meia, cy - h / 2, cx + meia, cy + h / 2)
            if not any(_sobrepoe(caixa, cb, 0.3 * h) for cb in caixas):
                break
        caixas.append(caixa)
        p.texto(cx, cy - h / 2, txt, h, "TEXTO", angulo=a, alinhamento="centro")


def desenho_do_conjunto(doc: Documento, marca: str, instancia: Sequence[Solido], n_instancias: int,
                        desenho: Desenho, dx: float, dy: float, rotular: bool = True,
                        fundidas: Optional[Dict[str, str]] = None, nota=None,
                        nomes: Optional[Dict[str, str]] = None, nome: str = "", tipo: str = "",
                        conformadas: Optional[set] = None,
                        pesos: Optional[Dict[str, float]] = None) -> Tuple[float, float, float, float]:
    """Elevação do conjunto com cotas de nós, título e lista de perfis, em (dx, dy).
    `fundidas`: marca do IFC → posição fundida; `nomes`: posição fundida → nome de
    produção (rótulos e composição com o mesmo nome que as células de posição);
    `nome`: o do conjunto (T1, S.T.2…); `pesos`: posição fundida → kg por peça."""
    fundidas = fundidas or {}
    nomes = nomes or {}
    pesos = pesos or {}

    def nome_de(marca_ifc):
        f = fundidas.get(str(marca_ifc), str(marca_ifc))
        return nomes.get(f) or f
    c, u, v, w = _eixos_do_conjunto(instancia)
    # observador em -w (convenção do motor de vistas): origem atrás de tudo
    ws = [_dot(_sub(p, c), w) for e in instancia for p in e.vertices]
    origem = tuple(c[i] + w[i] * (min(ws) - 10.0) for i in range(3))
    vista = _vistas.Vista(origem=origem, normal=w, acima=v, profundidade=None, cortar=False,
                          entidades=[e.id for e in instancia], rotular=False,
                          nome="Conjunto %s" % marca, tipo="conjunto")
    u, v, w = vista.eixos()          # exatamente os eixos com que a vista é desenhada
    antes = set(desenho.entidades)
    _vistas.gerar(doc, vista, desenho, (dx, dy))
    info = desenho.vistas[-1]
    larg, alt = info["largura"], info["altura"]
    novas = [desenho.entidades[k] for k in desenho.entidades if k not in antes]
    camada_de = _classificar_pecas_do_conjunto(instancia, (u, v, origem))
    _registrar_camadas_de_pecas(desenho)
    # A barra calandrada do canto (banzo que dobra no joelho) sai da fábrica como duas
    # peças retas cortadas em meia-esquadria: o desenho mostra o canto vivo com a
    # emenda diagonal, não o arco que o modelo 3D traz.
    if conformadas:
        ids_conformadas = {e.id for e in instancia
                           if fundidas.get(str(_marcas(e).get("posicao") or e.nome), str(_marcas(e).get("posicao") or e.nome)) in conformadas}
        if ids_conformadas:
            # as chapas desenhadas (suportes de terça): o trecho reto que segura uma delas
            # avança sobre o arco
            ids_chapas = {e.id for e in instancia if camada_de.get(e.id) == "CHAPAS"}
            apoios = []
            for e in novas:
                if (e.atributos or {}).get("origem") in ids_chapas and hasattr(e, "pontos"):
                    pp = e.pontos()
                    if pp:
                        apoios.append((min(q[0] for q in pp), min(q[1] for q in pp), max(q[0] for q in pp), max(q[1] for q in pp)))
            novas = _chanfrar_cantos(desenho, novas, ids_conformadas, apoios)
    for e in novas:
        e.atributos["conjunto"] = marca
        e.atributos["detalhe"] = "conjunto"
        # silhueta (VISTA/CORTE) na camada da peça: terças, banzos, diagonais…; as
        # arestas finas ficam finas
        if e.camada in ("VISTA", "CORTE") and e.atributos.get("origem") in camada_de:
            e.camada = camada_de[e.atributos["origem"]]
    if conformadas and any((e.atributos or {}).get("nos_chanfro") for e in novas):
        # canto em peças retas: banzo até o nó e a linha de emenda em cada nó
        _emendas_do_chanfro(desenho, novas, ids_conformadas, camada_de)
    # extremos reais em (u, v) do que foi desenhado: canto inferior esquerdo = (dx, dy)
    us = [_dot(_sub(p, origem), u) for e in instancia for p in e.vertices]
    vs = [_dot(_sub(p, origem), v) for e in instancia for p in e.vertices]
    u0, v0 = min(us), min(vs)
    atr = {"conjunto": marca, "detalhe": "conjunto"}
    if nome:
        atr["nome"] = nome                      # o grupo do conjunto no DXF leva o nome de produção
    p = _Papel(desenho, atr, dx, dy)
    esc = desenho.escala
    off, off2, off3 = 10.0, 20.0, 30.0
    # eixos das barras em (u, v); banzos são as barras quase horizontais e compridas
    barras = []
    rotulos = []
    for e in instancia:
        if _tipo_ifc(e).startswith("IfcPlate"):
            continue
        eixo = _eixo_da_peca(e)
        if not eixo:
            continue
        a, b = eixo
        pa = (_dot(_sub(a, origem), u) - u0, _dot(_sub(a, origem), v) - v0)
        pb = (_dot(_sub(b, origem), u) - u0, _dot(_sub(b, origem), v) - v0)
        comp = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        if comp < 40.0:
            continue
        ang = abs(math.degrees(math.atan2(pb[1] - pa[1], pb[0] - pa[0]))) % 180
        barras.append((pa, pb, comp, ang))
        m = _marcas(e)
        if rotular and m.get("posicao"):
            rotulos.append((nome_de(m["posicao"]), ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), ang))
    barras_furadas = _marcar_furos_das_barras(p, instancia, origem, u, v, u0, v0, esc)
    banzos = [b for b in barras if (b[3] < 25.0 or b[3] > 155.0) and b[2] > 0.25 * larg]
    diagonais = [b for b in barras if b not in banzos]
    # nós: interseção do eixo de cada diagonal/montante com o eixo de cada banzo, perto da
    # ponta da diagonal (a ponta em si é cortada em ângulo e cai fora do nó)
    nos_baixo, nos_cima = {0.0, larg}, {0.0, larg}
    alturas = {0.0, alt}
    # onde chega um montante (barra em pé), o nó é o eixo dele: é o que a fábrica marca no
    # banzo; a diagonal que chega ao mesmo nó cruza o eixo do banzo com excentricidade
    de_montante = set()

    def intersecao(p1, p2, q1, q2):
        d1 = (p2[0] - p1[0], p2[1] - p1[1])
        d2 = (q2[0] - q1[0], q2[1] - q1[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            return None
        t = ((q1[0] - p1[0]) * d2[1] - (q1[1] - p1[1]) * d2[0]) / den
        return (p1[0] + d1[0] * t, p1[1] + d1[1] * t), t
    v_medio = sum((b[0][1] + b[1][1]) / 2 for b in banzos) / len(banzos) if banzos else alt / 2

    def y_em(b, x):
        (xa, ya), (xb, yb) = b[0], b[1]
        return ya if abs(xb - xa) < 1e-9 else ya + (yb - ya) * (x - xa) / (xb - xa)

    def _de_cima(b):
        """Banzo de cima: o mais alto entre os banzos que passam na mesma abscissa (a
        altura média não serve na tesoura montada de duas águas, em que o banzo de baixo
        perto da cumeeira fica acima do banzo de cima perto do beiral)."""
        xm = (b[0][0] + b[1][0]) / 2
        outros = [o for o in banzos if o is not b and min(o[0][0], o[1][0]) - 1.0 <= xm <= max(o[0][0], o[1][0]) + 1.0
                  and abs(y_em(o, xm) - y_em(b, xm)) > 20.0]
        if not outros:
            return (b[0][1] + b[1][1]) / 2 > v_medio
        return y_em(b, xm) > max(y_em(o, xm) for o in outros) or y_em(b, xm) > min(y_em(o, xm) for o in outros) and \
            y_em(b, xm) >= sum(y_em(o, xm) for o in outros) / len(outros)
    de_cima = {id(b): _de_cima(b) for b in banzos}
    for pa, pb, comp, ang in diagonais:
        for bz in banzos:
            qa, qb = bz[0], bz[1]
            r = intersecao(pa, pb, qa, qb)
            if r is None:
                continue
            (x, y), t = r
            if -0.15 <= t <= 1.15 and min(qa[0], qb[0]) - 50 <= x <= max(qa[0], qb[0]) + 50:
                em_cima = de_cima[id(bz)]
                (nos_cima if em_cima else nos_baixo).add(round(x, 1))
                if abs(ang - 90.0) < 10.0:
                    de_montante.add(round(x, 1))
    for qa, qb, _, _ in banzos:
        for q in (qa, qb):
            alturas.add(round(q[1], 1))

    def fundir(vals, tol=60.0, fixos=()):
        """Nós a menos de `tol` viram um só, na média: as duas diagonais que chegam ao mesmo
        nó cruzam o eixo do banzo com alguns centímetros de excentricidade. Os extremos
        (0 e o comprimento) não se movem."""
        vals = sorted(vals)
        grupos = [[vals[0]]]
        for x in vals[1:]:
            if x - grupos[-1][-1] > tol:
                grupos.append([x])
            else:
                grupos[-1].append(x)
        fora = []
        for g in grupos:
            fixo = [x for x in g if x in fixos]
            mont = [x for x in g if x in de_montante]
            fora.append(fixo[0] if fixo else round(sum(mont) / len(mont), 1) if mont else round(sum(g) / len(g), 1))
        return fora
    nos_baixo = fundir(nos_baixo, fixos=(0.0, larg))
    nos_cima = fundir(nos_cima, fixos=(0.0, larg))
    alturas = fundir(alturas, tol=30.0, fixos=(0.0, alt))
    # a cadeia de cada banzo acompanha a caída da cobertura: banzo inclinado (mais de 2°)
    # ganha cotas alinhadas à própria reta, com as distâncias medidas nela — é o que se
    # marca na barra; banzo horizontal fica com a cadeia horizontal
    def _reta(pts):
        a_, b_ = min(pts, key=lambda q: q[0]), max(pts, key=lambda q: q[0])
        if b_[0] - a_[0] < 1e-6 or abs(math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0]))) < 2.0:
            return None
        return a_, b_

    def trechos(em_cima):
        """Trechos do banzo de um lado, por caída: [(x0, x1, reta ou None, y do topo)]. A
        meia-tesoura tem um só; a tesoura montada de duas águas, um por água."""
        lados = [b for b in banzos if de_cima[id(b)] == em_cima]
        grupos: Dict[int, list] = collections.OrderedDict()
        for b in sorted(lados, key=lambda b: min(b[0][0], b[1][0])):
            (xa, ya), (xb, yb) = sorted((b[0], b[1]))
            inc = math.degrees(math.atan2(yb - ya, xb - xa)) if xb - xa > 1e-6 else 0.0
            grupos.setdefault(0 if abs(inc) < 2.0 else (1 if inc > 0 else -1), []).append(b)
        fora = []
        for bs in grupos.values():
            pts = [q for b in bs for q in (b[0], b[1])]
            fora.append((min(q[0] for q in pts), max(q[0] for q in pts), _reta(pts), max(q[1] for q in pts)))
        return sorted(fora, key=lambda t: t[0])

    def reta_do_banzo(em_cima):
        ts = trechos(em_cima)
        return ts[0][2] if len(ts) == 1 else None

    def cadeia_do_banzo(nos, em_cima):
        ts = trechos(em_cima)
        sinal = off if em_cima else -off
        if len(ts) <= 1:
            reta = ts[0][2] if ts else None
            if reta is None:
                return p.cadeia_h(nos, alt if em_cima else 0.0, sinal)
            return p.cadeia_alinhada(reta, nos, sinal)
        # um trecho por água: os nós dele e as pontas dele, cada cadeia na sua reta
        feita = False
        for x0, x1, reta, ytopo in ts:
            # os nós da água (até 40 mm fora das pontas) e as pontas; nó colado na ponta (a
            # cumeeira tem dois montantes a 70 mm) funde com ela
            pontas = (round(x0, 1), round(x1, 1))
            nos_t = fundir({*pontas} | {x for x in nos if x0 - 40.0 <= x <= x1 + 40.0}, tol=60.0, fixos=pontas)
            if len(nos_t) < 2:
                continue
            feita = (p.cadeia_alinhada(reta, nos_t, sinal) if reta is not None
                     else p.cadeia_h(nos_t, ytopo if em_cima else 0.0, sinal)) or feita
        return feita
    cadeia = len(nos_baixo) > 2 and cadeia_do_banzo(nos_baixo, False)
    p.cota_h(0, larg, 0, -(off2 if cadeia else off))
    cadeia_cima = len(nos_cima) > 2 and nos_cima != nos_baixo and cadeia_do_banzo(nos_cima, True)
    # suportes de terça (chapinhas/cantoneiras curtas encostadas no banzo de cima): a
    # cadeia do espaçamento deles, alinhada ao banzo, acima da cadeia dos nós
    suportes = []
    trechos_cima = trechos(True)
    reta_cima = reta_do_banzo(True)
    sup_por_trecho: Dict[int, list] = collections.defaultdict(list)
    for e in instancia:
        if camada_de.get(e.id) != "CHAPAS":
            continue
        pu = [_dot(_sub(q, origem), u) - u0 for q in e.vertices]
        pv = [_dot(_sub(q, origem), v) - v0 for q in e.vertices]
        # o suporte é a chapa em pé (alta e estreita na elevação); o gusset deitado
        # e o enrijecedor ao lado dele não contam
        if max(pu) - min(pu) > 40.0 or max(pv) - min(pv) < 100.0:
            continue
        cx, cy = sum(pu) / len(pu), sum(pv) / len(pv)
        i_t = 0
        if len(trechos_cima) > 1:
            # tesoura montada: a reta da água em que o suporte está
            i_t = min(range(len(trechos_cima)), key=lambda i: 0.0 if trechos_cima[i][0] <= cx <= trechos_cima[i][1]
                      else min(abs(cx - trechos_cima[i][0]), abs(cx - trechos_cima[i][1])))
            reta_cima = trechos_cima[i_t][2]
        if reta_cima is not None:
            (ax_, ay_), (bx_, by_) = reta_cima
            dist = abs((bx_ - ax_) * (ay_ - cy) - (ax_ - cx) * (by_ - ay_)) / max(math.hypot(bx_ - ax_, by_ - ay_), 1e-9)
        else:
            dist = abs(cy - alt)
        if dist <= 150.0:
            if reta_cima is not None:
                # o suporte fica em pé, perpendicular ao banzo: a referência dele é o pé da
                # perpendicular no banzo (a projeção vertical erra em banzo inclinado), e a
                # abscissa que a cadeia alinhada leva de volta a esse mesmo ponto
                cl = math.hypot(bx_ - ax_, by_ - ay_) or 1.0
                ux_, uy_ = (bx_ - ax_) / cl, (by_ - ay_) / cl
                t_ = (cx - ax_) * ux_ + (cy - ay_) * uy_
                suportes.append(ax_ + ux_ * t_)
            else:
                suportes.append(cx)
            sup_por_trecho[i_t].append(suportes[-1])
    cadeia_suportes = False
    if len(trechos_cima) > 1:
        # uma cadeia de suportes por água, das pontas do trecho
        desl = off2 if cadeia_cima else off
        for i_t, lista_s in sup_por_trecho.items():
            x0, x1, reta_t, ytopo = trechos_cima[i_t]
            sup = fundir(set(round(s, 1) for s in lista_s) | {round(x0, 1), round(x1, 1)}, tol=60.0,
                         fixos=(round(x0, 1), round(x1, 1)))
            if len(sup) > 2:
                cadeia_suportes = (p.cadeia_alinhada(reta_t, sup, desl, exigir_espaco=False) if reta_t is not None
                                   else p.cadeia_h(sup, ytopo, desl, exigir_espaco=False)) or cadeia_suportes
        suportes = []
    if len(suportes) >= 2:
        sup = fundir(set(round(s, 1) for s in suportes) | {0.0, larg}, tol=60.0, fixos=(0.0, larg))
        # a cadeia dos suportes só se repete quando é exatamente a dos nós (terça em todo
        # nó); terça de dois em dois nós tem espaçamento próprio, e é ele que se cota
        iguais = len(sup) == len(nos_cima) and all(abs(s - n_) <= 20.0 for s, n_ in zip(sorted(sup), sorted(nos_cima)))
        if not iguais and len(sup) > 2:
            # a folga da ponta ao primeiro suporte é curta (uns 120 mm): a cadeia sai mesmo
            # assim — é a medida que a fábrica marca no banzo
            desl = off2 if cadeia_cima else off
            # a referência é o suporte da terça (regra da fábrica): a linha de chamada nasce
            # no pé do suporte, no banzo, e sobe por ele até a cadeia
            cadeia_suportes = (p.cadeia_alinhada(reta_cima, sup, desl, exigir_espaco=False) if reta_cima is not None
                               else p.cadeia_h(sup, alt, desl, exigir_espaco=False))
    cadeia = len(alturas) > 2 and p.cadeia_v(alturas, larg, off)
    p.cota_v(0, alt, larg, off2 if cadeia else off)
    _rotular_barras(p, rotulos, esc)
    if barras_furadas:
        # os detalhes de furação abaixo de tudo o que a elevação já desenhou
        fundo = min([0.0] + [q[1] - dy for q in p.pontos])
        _detalhes_de_furos(p, barras_furadas, nome_de, esc, fundo - 20.0 * esc)
    # título e lista de perfis: um perfil por linha, escrito na camada (cor) das peças
    # que o usam — banzo, diagonal, montante, chapa —, como a fábrica lê a elevação
    perfis_cam: Dict[tuple, int] = collections.Counter()
    peso_un = 0.0
    for e in instancia:
        m = _marcas(e)
        marca_e = str(m.get("posicao") or e.nome)
        perfis_cam[(camada_de.get(e.id, "TEXTO"), str(m.get("perfil") or e.nome))] += 1
        peso_un += float(pesos.get(fundidas.get(marca_e, marca_e), 0.0) or 0.0)
    ordem_cam = {k: i for i, k in enumerate(CAMADAS_PECAS)}
    y = alt + (((off3 if cadeia_cima else off2) if cadeia_suportes else (off2 if cadeia_cima else off)) + 2.0) * esc

    def quebrar(prefixo, itens, largura=64):
        fora, atual = [], prefixo
        for it in itens:
            if len(atual) + len(it) + 2 > largura and atual != prefixo:
                fora.append(atual.rstrip(", "))
                atual = ""                           # continuação alinhada à margem (espaços não alinham em fonte proporcional)
            atual += it + ", "
        fora.append(atual.rstrip(", "))
        return fora
    # legenda enxuta: nome e quantidade, os perfis (um por linha, na cor da peça), os
    # parafusos e o peso; sem a lista de nomes das peças — cada uma tem o seu detalhe e o
    # tipo está no título do quadro. Cada linha é (texto, camada).
    titulo = "%s – %02dx" % (nome or marca, n_instancias)
    linhas = [(titulo, "TEXTO")]
    # uma linha por tipo de peça, na cor dela: "U100X50X4.18" (banzos, azul), "U88X40X2.25 /
    # U100X50X3.04" (diagonais, laranja)…; as chapas pela espessura ("PLATE 400x120x13" → #13)
    por_cam: Dict[str, List[str]] = collections.OrderedDict()
    for (cam_, perfil_), _q in sorted(perfis_cam.items(), key=lambda kv: (ordem_cam.get(kv[0][0], 99), _ordem_natural(kv[0][1]))):
        if not perfil_:
            continue
        if cam_ == "CHAPAS":
            m_esp = re.search(r"x\s*([\d.,]+)\s*$", perfil_)
            perfil_ = "#" + m_esp.group(1).replace(".", ",") if m_esp else perfil_
        perfil_ = com_bitola(perfil_)               # U100X50X4.18 → U100X50X#8, como a fábrica escreve
        lista_ = por_cam.setdefault(cam_ if cam_ in CAMADAS_PECAS else "TEXTO", [])
        if perfil_ not in lista_:
            lista_.append(perfil_)
    for cam_, lista_ in por_cam.items():
        if cam_ == "CHAPAS":
            lista_ = sorted(lista_, key=_ordem_natural, reverse=True)
        linhas.append(("%s%s" % ("Chapas " if cam_ == "CHAPAS" else "", " / ".join(lista_)), cam_))
    paraf, porcas = parafusos_no_conjunto(doc, instancia)
    if paraf or porcas:
        itens_p = ["%dx %s" % (q, k) for k, q in sorted(paraf.items(), key=lambda kv: _ordem_natural(kv[0]))]
        if porcas:
            itens_p.append("%dx porca/chumbador" % porcas)
        linhas += [(t, "TEXTO") for t in quebrar("Parafusos: ", itens_p)]
    if peso_un > 0:
        linhas.append(("%s kg/un  total %s kg" % (_mm(peso_un, 1), _mm(peso_un * n_instancias, 1)), "TEXTO"))
    for txt in ([nota] if isinstance(nota, str) else list(nota or [])):
        if not txt:
            continue
        # nota quebrada por palavras, com recuo
        atual = "* "
        for palavra in txt.split(" "):
            if len(atual) + len(palavra) + 1 > 72 and atual.strip() != "*":
                linhas.append((atual.rstrip(), "TEXTO"))
                atual = "  "
            atual += palavra + " "
        linhas.append((atual.rstrip(), "TEXTO"))
    for i, (txt, cam_) in enumerate(reversed(linhas)):
        alt_t = 3.5 if i == len(linhas) - 1 else 2.5
        p.texto(0, y, txt, alt_t * esc, cam_)
        y += (alt_t + 1.2) * esc
    ext = p.extremos
    return (min(ext[0], dx), min(ext[1], dy), max(ext[2], dx + larg), max(ext[3], dy + alt))


# ============================================================ tesouras montadas
#: Duas meias-tesouras são da mesma tesoura quando estão no mesmo plano (a esta distância, mm).
TOLERANCIA_PLANO_TESOURA = 150.0


def tesouras_montadas(meias: Sequence[tuple]) -> Tuple[List[dict], set]:
    """Tesouras inteiras a partir das meias. `meias` = [(rótulo da célula, peças do
    conjunto, composição unitária)]; cada instância de meia é posta no plano dela (a
    distância do centro ao longo da normal), e as que caem no mesmo plano formam uma
    tesoura montada — é assim que a fábrica gabarita: as duas águas juntas. Tesouras
    montadas com as mesmas meias (os mesmos rótulos) viram uma só, com a quantidade.

    Devolve ([{"rotulos": (…), "pecas": [peças da primeira], "n": quantas}], rótulos que
    ficaram inteiramente dentro de tesouras montadas)."""
    insts = []                                       # (rótulo, peças, normal, d, centro)
    for rotulo, lista, unidade in meias:
        for g in _instancias_do_conjunto(lista, unidade):
            c, _u, _v, w = _eixos_do_conjunto(g)
            k = max(range(3), key=lambda i: abs(w[i]))
            if w[k] < 0:
                w = (-w[0], -w[1], -w[2])
            insts.append((rotulo, g, w, _dot(c, w), c))
    insts.sort(key=lambda t: t[3])
    planos: List[list] = []
    for t in insts:
        alvo = next((pl for pl in planos if abs(t[3] - pl[0][3]) <= TOLERANCIA_PLANO_TESOURA
                     and abs(_dot(t[2], pl[0][2])) > 0.99), None)
        if alvo is None:
            planos.append([t])
        else:
            alvo.append(t)
    montadas: Dict[tuple, dict] = collections.OrderedDict()
    fora = collections.Counter()                     # instâncias que não formaram par
    total = collections.Counter(t[0] for t in insts)
    for pl in planos:
        if len(pl) < 2:
            fora[pl[0][0]] += 1
            continue
        # da esquerda para a direita no desenho (ao longo do vão)
        pl.sort(key=lambda t: t[4][0] + t[4][1])
        chave = tuple(sorted(t[0] for t in pl))
        m = montadas.setdefault(chave, {"rotulos": chave, "pecas": [e for t in pl for e in t[1]], "n": 0})
        m["n"] += 1
    cobertos = {r for r in total if not fora.get(r)} if montadas else set()
    return list(montadas.values()), cobertos


# ============================================================ contraventamentos
#: Redondo mais curto que isto (mm) não é o tirante do contraventamento (gancho, esticador).
MENOR_TIRANTE = 600.0


def _tirante_principal(instancia: Sequence[Solido]):
    """A barra redonda mais comprida do conjunto (o tirante), ou None."""
    melhor, comp = None, 0.0
    for e in instancia:
        if not _eh_redonda_perfil(str(_marcas(e).get("perfil") or e.nome or "")):
            continue
        cx = _caixa(e)
        ext = max(cx[i][1] - cx[i][0] for i in range(3))
        if ext > comp:
            melhor, comp = e, ext
    return melhor if comp >= MENOR_TIRANTE else None


def _barra_mais_longa(instancia: Sequence[Solido]):
    """A peça mais comprida do conjunto (a barra do contraventamento que não é redonda)."""
    melhor, comp = None, 0.0
    for e in instancia:
        cx = _caixa(e)
        ext = max(cx[i][1] - cx[i][0] for i in range(3))
        if ext > comp:
            melhor, comp = e, ext
    return melhor


def _comprimento_na_vista(peca: Solido, instancia: Sequence[Solido]) -> float:
    """Extensão da peça ao longo do comprimento da vista do conjunto dela."""
    c, u, v, w = _eixos_do_conjunto(instancia)
    u, v, w = _vistas.Vista(origem=c, normal=w, acima=v).eixos()
    us = [_dot(_sub(p, c), u) for p in peca.vertices]
    return max(us) - min(us)


def _extensao_do_conjunto(instancia: Sequence[Solido]) -> Tuple[float, float]:
    """(comprimento, altura) da instância na vista em que é desenhada."""
    c, u, v, w = _eixos_do_conjunto(instancia)
    u, v, w = _vistas.Vista(origem=c, normal=w, acima=v).eixos()
    us = [_dot(_sub(p, c), u) for e in instancia for p in e.vertices]
    vs = [_dot(_sub(p, c), v) for e in instancia for p in e.vertices]
    return max(us) - min(us), max(vs) - min(vs)


def desenho_de_contraventamentos(doc: Documento, membros: Sequence[tuple], desenho: Desenho, dx: float, dy: float,
                                 nomes: Dict[str, str], nomes_conj: Dict[str, str], fundidas: Dict[str, str],
                                 comprimentos: Dict[str, float], rotular: bool = True) -> Tuple[float, float, float, float]:
    """Detalhe limpo dos contraventamentos que só diferem no comprimento do tirante
    (mesmas peças de ponta): a elevação do mais comprido, as cotas empilhadas — uma por
    contraventamento, "C.V.3 (02x) – 5150" — e, embaixo, as cotas das peças de ponta
    (barra roscada do esticador, cantoneiras, chapa). `membros` = [(rotulo do grupo,
    instância, nº de instâncias)]."""
    membros = sorted(membros, key=lambda m: _ordem_natural(nomes_conj.get(m[0], m[0])))
    maior = max(membros, key=lambda m: _extensao_do_conjunto(m[1])[0])
    rotulo, inst, _ = maior
    rotulo_celula = " / ".join(m[0] for m in membros)
    c, u, v, w = _eixos_do_conjunto(inst)
    ws = [_dot(_sub(p, c), w) for e in inst for p in e.vertices]
    origem = tuple(c[i] + w[i] * (min(ws) - 10.0) for i in range(3))
    vista = _vistas.Vista(origem=origem, normal=w, acima=v, profundidade=None, cortar=False,
                          entidades=[e.id for e in inst], rotular=False, nome="Contraventamento %s" % rotulo_celula, tipo="conjunto")
    u, v, w = vista.eixos()
    antes = set(desenho.entidades)
    _vistas.gerar(doc, vista, desenho, (dx, dy))
    info = desenho.vistas[-1]
    larg, alt = info["largura"], info["altura"]
    camada_de = _classificar_pecas_do_conjunto(inst, (u, v, origem))
    _registrar_camadas_de_pecas(desenho)
    for e in (desenho.entidades[k] for k in desenho.entidades if k not in antes):
        e.atributos["conjunto"] = rotulo_celula
        e.atributos["detalhe"] = "conjunto"
        if e.camada in ("VISTA", "CORTE") and e.atributos.get("origem") in camada_de:
            e.camada = camada_de[e.atributos["origem"]]
    us = [_dot(_sub(p, origem), u) for e in inst for p in e.vertices]
    vs = [_dot(_sub(p, origem), v) for e in inst for p in e.vertices]
    u0, v0 = min(us), min(vs)
    atr = {"conjunto": rotulo_celula, "detalhe": "conjunto"}
    p = _Papel(desenho, atr, dx, dy)
    esc = desenho.escala
    off, passo = 10.0, 8.0
    tirante = _tirante_principal(inst) or _barra_mais_longa(inst)

    def nome_de(marca_ifc):
        f = fundidas.get(str(marca_ifc), str(marca_ifc))
        return nomes.get(f) or f
    # peças de ponta cotadas embaixo: barra roscada e chapa na 1ª linha, cantoneiras na 2ª
    extremos_pecas = []
    for e in inst:
        if e is tirante:
            continue
        pu = [_dot(_sub(q, origem), u) - u0 for q in e.vertices]
        ext = max(pu) - min(pu)
        if ext < 20.0:
            continue
        perfil = str(_marcas(e).get("perfil") or e.nome or "")
        extremos_pecas.append([min(pu), max(pu), 0, nome_de(_marcas(e).get("posicao") or e.nome), perfil])
    # uma linha de cota por peça de cada ponta (as cantoneiras vizinhas não se atropelam),
    # com o nome da peça no texto: "150  B.7"
    extremos_pecas.sort(key=lambda r_: r_[0])
    meio = larg / 2.0
    for lado_ in (False, True):
        k = 0
        for r_ in extremos_pecas:
            if ((r_[0] + r_[1]) / 2 > meio) != lado_:
                continue
            k += 1
            r_[2] = k
    # as peças de ponta (gancho, chapas, barra roscada do esticador) são detalhe padrão,
    # iguais em todos: aqui só o nome embaixo de cada uma — as medidas estão no detalhe dela
    h_nome = 1.8 * esc
    for a_, b_, linha, nome_p, perfil in extremos_pecas:
        p.texto((a_ + b_) / 2, -(3.0 + 3.0 * (linha - 1)) * esc - h_nome, nome_p, h_nome, "TEXTO", alinhamento="centro")
    # cotas empilhadas por contraventamento: o tamanho da BARRA (sem as peças de ponta),
    # a partir da ponta dela no desenho
    if tirante is not None:
        pu_t = [_dot(_sub(q, origem), u) - u0 for q in tirante.vertices]
        pv_t = [_dot(_sub(q, origem), v) - v0 for q in tirante.vertices]
        t0, t1 = min(pu_t), max(pu_t)
    else:
        t0, t1 = 0.0, larg
    for i, (rot, inst_m, n_inst) in enumerate(membros):
        tir_m = _tirante_principal(inst_m) or _barra_mais_longa(inst_m)
        comp_m = _comprimento_na_vista(tir_m, inst_m) if tir_m is not None else _extensao_do_conjunto(inst_m)[0]
        nome_m = nomes_conj.get(rot, rot)
        # a cota na própria linha (deslocamento zero): só a linha com as setas e o texto —
        # as linhas de chamada de cada cota até a barra enchiam a célula de traços
        p.cota_h(round(t0), round(t0 + comp_m), alt + (off + passo * i) * esc, 0.0,
                 texto="%s (%02dx) – %d" % (nome_m, n_inst, round(comp_m)))
    # a dobra da barra (gancho na ponta): a altura da perna, cotada na própria ponta
    if tirante is not None:
        corpo = [pv for pu_, pv in zip(pu_t, pv_t) if t0 + 0.3 * (t1 - t0) < pu_ < t1 - 0.3 * (t1 - t0)]
        diam = (max(corpo) - min(corpo)) if corpo else 0.0
        for lado_esq in (True, False):
            ponta = [(pu_, pv) for pu_, pv in zip(pu_t, pv_t) if (pu_ < t0 + 250.0 if lado_esq else pu_ > t1 - 250.0)]
            if not ponta:
                continue
            vmin, vmax = min(q[1] for q in ponta), max(q[1] for q in ponta)
            if vmax - vmin - diam < 15.0:
                continue                              # ponta reta
            x_ = t0 if lado_esq else t1
            p.cota_v(vmin, vmax, x_, -off if lado_esq else off)
            # o trecho da dobra ao longo da barra (onde a perna começa)
            perna = [q[0] for q in ponta if (q[1] > max(corpo) + 2.0 or q[1] < min(corpo) - 2.0)] if corpo else []
            if perna:
                if lado_esq:
                    p.cota_h(t0, max(perna), vmax, 4.0)
                else:
                    p.cota_h(min(perna), t1, vmax, 4.0)
    # rótulos: tirante pelo perfil no meio; peças de ponta pelo nome
    if rotular:
        h = 1.8 * esc
        if tirante is not None:
            pu = [_dot(_sub(q, origem), u) - u0 for q in tirante.vertices]
            p.texto((min(pu) + max(pu)) / 2, alt + 2.0 * esc, str(_marcas(tirante).get("perfil") or tirante.nome or ""), h, "TEXTO", alinhamento="centro")
        pass
    # título: tipo, nomes e, por contraventamento, o tirante com o comprimento de corte
    total = sum(m[2] for m in membros)
    linhas = ["%s – %02dx" % (" / ".join(nomes_conj.get(m[0], m[0]) for m in membros), total)]
    for rot, inst_m, n_inst in membros:
        tir = _tirante_principal(inst_m)
        if tir is None:
            continue
        marca_t = fundidas.get(str(_marcas(tir).get("posicao") or tir.nome), str(_marcas(tir).get("posicao") or tir.nome))
        comp_t = comprimentos.get(marca_t)
        nome_t = nomes.get(marca_t) or marca_t
        linhas.append("%s – %02dx: tirante %s%s%s" % (nomes_conj.get(rot, rot), n_inst,
                                                    "" if nome_t == nomes_conj.get(rot, rot) else nome_t + " ",
                                                    str(_marcas(tir).get("perfil") or tir.nome or ""),
                                                    "  L = %d mm" % round(comp_t) if comp_t else ""))
    pecas_ponta = collections.Counter(nome_de(_marcas(e).get("posicao") or e.nome) for e in inst if e is not tirante)
    if pecas_ponta:
        linhas.append("Pecas de ponta (por unidade): "
                      + ", ".join("%s x%d" % (k, q) for k, q in sorted(pecas_ponta.items(), key=lambda kv: _ordem_natural(kv[0]))))
    y = alt + (off + passo * len(membros) + 4.0) * esc
    for i, txt in enumerate(reversed(linhas)):
        alt_t = 3.5 if i == len(linhas) - 1 else 2.5
        p.texto(0, y, txt, alt_t * esc)
        y += (alt_t + 1.2) * esc
    ext = p.extremos
    return (min(ext[0], dx), min(ext[1], dy), max(ext[2], dx + larg), max(ext[3], dy + alt))


# ============================================================ localização
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


def _itens_de_localizacao(pecas: Sequence[Solido]) -> List[Tuple[str, List[Solido]]]:
    """(rótulo, peças) por instância de conjunto; peça solta (marca = conjunto, ou sem
    conjunto) vale por si."""
    por_conj: Dict[str, List[Solido]] = collections.OrderedDict()
    soltas: List[Solido] = []
    for e in pecas:
        m = _marcas(e)
        conj = str(m.get("conjunto") or "")
        pos = str(m.get("posicao") or "")
        if conj and conj != pos:
            por_conj.setdefault(conj, []).append(e)
        else:
            soltas.append(e)
    itens: List[Tuple[str, List[Solido]]] = []
    for conj, lista in por_conj.items():
        total = collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in lista)
        n = 0
        for q in total.values():
            n = math.gcd(n, q)
        n = max(n, 1)
        unidade = collections.Counter({k: q // n for k, q in total.items()})
        for g in _instancias_do_conjunto(lista, unidade):
            itens.append((conj, g))
    for e in soltas:
        m = _marcas(e)
        itens.append((str(m.get("posicao") or e.nome or ""), [e]))
    return itens


#: Item menor que isto (chapinha solta, conjunto de chapas) não ganha marca na planta.
MENOR_ITEM_LOCALIZACAO = 500.0


def desenho_de_localizacao(doc: Documento, pecas: Sequence[Solido], titulo: str = "Detalhamento – localização",
                           ignorar: Sequence[str] = (), nomes: Optional[Dict[str, str]] = None,
                           camadas_pecas: Optional[Dict[str, str]] = None) -> Desenho:
    """Planta e duas elevações esquemáticas do modelo inteiro (cada peça é o contorno
    convexo da sua projeção, em linha fina) com a marca de cada conjunto e de cada peça
    solta escrita no lugar em que está montada: é a planta de montagem que diz onde vai
    cada item detalhado. `ignorar`: marcas de posição que ficam fora (telhas)."""
    from nucleo2d.pranchas import escala_normalizada
    fora = set(ignorar or ())
    pecas = [e for e in pecas if str(_marcas(e).get("posicao") or e.nome) not in fora]
    if not pecas:
        raise ErroDeDados("sem peças para localizar.")
    itens = _itens_de_localizacao(pecas)
    todos = [v for e in pecas for v in e.vertices]
    minimo = [min(v[i] for v in todos) for i in range(3)]
    maximo = [max(v[i] for v in todos) for i in range(3)]
    ext = [maximo[i] - minimo[i] for i in range(3)]
    # a planta fica com o lado comprido na horizontal; a elevação longitudinal embaixo
    # dela partilha o eixo horizontal; a transversal vai à direita
    comprido_em_y = ext[1] > ext[0]
    if comprido_em_y:
        # de cima (observador em +z, w = -z): direita = y, cima do papel = -x
        u_pl, v_pl, w_pl = (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, -1.0)
        u_lo, v_lo, w_lo = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)      # vista de +x
        u_tr, v_tr, w_tr = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)       # vista de -y
    else:
        u_pl, v_pl, w_pl = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)
        u_lo, v_lo, w_lo = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)       # vista de -y
        u_tr, v_tr, w_tr = (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)      # vista de -x
    vistas = [("PLANTA DE LOCALIZAÇÃO", "topo", u_pl, v_pl, w_pl),
              ("ELEVAÇÃO LONGITUDINAL", "frente", u_lo, v_lo, w_lo),
              ("ELEVAÇÃO TRANSVERSAL", "lateral", u_tr, v_tr, w_tr)]

    def extensao(u, v):
        us = [_dot(p, u) for p in todos]
        vs = [_dot(p, v) for p in todos]
        return max(us) - min(us), max(vs) - min(vs)
    l_pl, a_pl = extensao(u_pl, v_pl)
    l_lo, a_lo = extensao(u_lo, v_lo)
    l_tr, a_tr = extensao(u_tr, v_tr)
    folga_papel = 45.0
    # papel útil de uma A1 deitada, descontados carimbo e margens
    esc = escala_normalizada(max((l_pl + folga_papel * 0 + max(l_tr, 0.0)) / 760.0,
                                 (a_pl + a_lo + 2 * folga_papel) / 520.0, 1.0))
    d = Desenho(nome=titulo, escala=esc)
    folga = folga_papel * esc
    atr_base = {"detalhe": "localizacao"}
    h_txt = 2.5 * esc
    posicoes_vistas = [(0.0, a_lo + folga), (0.0, 0.0), (l_lo + folga, 0.0)]
    for (nome, tipo, u, v, w), (x0, y0) in zip(vistas, posicoes_vistas):
        us = [_dot(p, u) for p in todos]
        vs = [_dot(p, v) for p in todos]
        u0, v0 = min(us), min(vs)
        p = _Papel(d, dict(atr_base, vista=nome), x0, y0)
        n_pecas = 0
        # contornos
        for e in pecas:
            pts = [(_dot(q, u) - u0, _dot(q, v) - v0) for q in e.vertices]
            casco = _casco(pts)
            if len(casco) >= 3:
                m = _marcas(e)
                atr = dict(atr_base, vista=nome, origem=e.id, nome=e.nome or "")
                if m.get("posicao"):
                    atr["posicao"] = str(m["posicao"])
                if m.get("conjunto"):
                    atr["conjunto"] = str(m["conjunto"])
                pp = _Papel(d, atr, x0, y0)
                cam = (camadas_pecas or {}).get(str(m.get("posicao") or ""), "")
                if cam:
                    _registrar_camadas_de_pecas(d)
                pp.polilinha(casco, fechada=True, camada=cam or "ACO-FINO")
                p.pontos.extend(pp.pontos)
                n_pecas += 1
        # rótulos no centro de cada item; quem está de topo (extensão projetada pequena
        # perante a extensão 3D) não é rotulado nesta vista
        caixas = []
        rotulos = []
        for rotulo, lista in itens:
            if not rotulo:
                continue
            vv = [q for e in lista for q in e.vertices]
            pu = [_dot(q, u) - u0 for q in vv]
            pv = [_dot(q, v) - v0 for q in vv]
            ext3 = max(max(q[i] for q in vv) - min(q[i] for q in vv) for i in range(3))
            ext2 = max(max(pu) - min(pu), max(pv) - min(pv))
            if ext3 < MENOR_ITEM_LOCALIZACAO or (ext3 > 0 and ext2 < 0.3 * ext3):
                continue
            rotulos.append(((nomes or {}).get(rotulo) or rotulo, (sum(pu) / len(pu), sum(pv) / len(pv))))
        rotulos.sort(key=lambda r: (r[1][1], r[1][0]))
        postos: List[Tuple[str, float, float]] = []
        for rotulo, (cx, cy) in rotulos:
            # a mesma marca já escrita ali perto (terças vistas de ponta, uma sobre a
            # outra) não se repete
            if any(t == rotulo and math.hypot(cx - x_, cy - y_) < 6.0 * h_txt for t, x_, y_ in postos):
                continue
            larg = 0.75 * h_txt * len(rotulo)
            caixa = None
            livre = False
            for passo in range(4):
                dy = passo * 1.3 * h_txt
                caixa = (cx - larg / 2, cy + dy - h_txt / 2, cx + larg / 2, cy + dy + h_txt / 2)
                if not any(_sobrepoe(caixa, cb, 0.2 * h_txt) for cb in caixas):
                    livre = True
                    break
            if not livre:
                continue
            caixas.append(caixa)
            postos.append((rotulo, cx, cy))
            p.texto(cx, caixa[1], rotulo, h_txt, "TEXTO", alinhamento="centro")
        larg_v, alt_v = max(us) - u0, max(vs) - v0
        p.cota_h(0, larg_v, 0, -10.0)
        p.cota_v(0, alt_v, larg_v, 10.0)
        p.texto(0, -(10.0 + 8.0) * esc, nome, 3.5 * esc)
        p.texto(0, -(10.0 + 8.0 + 4.5) * esc, "escala 1:%s · marcas de conjunto no lugar de montagem; peça solta com a própria marca" % (int(esc) if float(esc).is_integer() else esc), 2.0 * esc)
        ext_c = p.extremos
        d.metadados.setdefault("celulas", []).append([round(t, 1) for t in ext_c])
        d.vistas.append({"origem": [minimo[0], minimo[1], minimo[2]], "normal": list(w), "acima": list(v),
                         "profundidade": None, "cortar": False, "entidades": None, "rotular": True,
                         "nome": nome, "tipo": tipo, "pecas_cortadas": 0, "pecas_projetadas": n_pecas,
                         "largura": round(larg_v, 1), "altura": round(alt_v, 1), "canto": [x0, y0], "avisos": []})
    d.metadados["detalhamento"] = {"grupo": "localizacao", "posicoes": [], "itens": {}}
    return d
