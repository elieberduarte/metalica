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

from nucleo2d.detalhe.base import (
    parafusos_posicionados, largura_da_chamada,  # noqa: E402
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
    # polilinha que é só o arco (a silhueta veio partida: o arco separado das retas): não
    # há segmento comprido para os do arco serem "curtos" — todos iguais, virando para o
    # mesmo lado. O trecho é a polilinha inteira; as pontas fazem o papel das retas
    # vizinhas (o chanfro pelas tangentes sai igual ao do contorno inteiro)
    if not fechada and n >= 8:
        giros = [giro(k) for k in range(ns - 1)]
        if max(comp) <= 1.6 * min(comp) and all(1.0 <= abs(g) <= 30.0 for g in giros) \
                and len({1 if g > 0 else -1 for g in giros}) == 1:
            return [(0, n - 1)]
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


def _nos_do_arco_puro(pts: Sequence[Tuple[float, float]], direcoes=None):
    """Nós do chanfro de uma polilinha que é só o arco: centro pelo círculo de três pontos
    e tangentes exatas nas pontas — o primeiro e o último segmento do arco são chordas,
    meio passo angular fora da tangente, e prolongá-los deixava o nó uns 30 mm para dentro
    e o trecho até a ponta tombado. Devolve [nó1, nó2] ou None."""
    n = len(pts)
    if n < 5:
        return None
    A, M, E = pts[0], pts[n // 2], pts[-1]
    d = 2.0 * (A[0] * (M[1] - E[1]) + M[0] * (E[1] - A[1]) + E[0] * (A[1] - M[1]))
    if abs(d) < 1e-9:
        return None
    a2, m2, e2 = A[0] ** 2 + A[1] ** 2, M[0] ** 2 + M[1] ** 2, E[0] ** 2 + E[1] ** 2
    cx = (a2 * (M[1] - E[1]) + m2 * (E[1] - A[1]) + e2 * (A[1] - M[1])) / d
    cy = (a2 * (E[0] - M[0]) + m2 * (A[0] - E[0]) + e2 * (M[0] - A[0])) / d

    def tangente(p):
        return (p[0] - (p[1] - cy), p[1] + (p[0] - cx))      # ponto sobre a tangente em p

    def direcao_na_ponta(p, viz, sentido):
        """Direção da reta que sai da ponta, orientada como o arco a percorre: a da reta
        do contorno da mesma peça (o arco puro costuma acabar um ou dois facetados antes
        da tangência, e a tangente ali ainda está inclinada). None sem contorno."""
        c = (viz[0] - p[0], viz[1] - p[1])
        Lc = math.hypot(*c)
        if not direcoes or Lc < 1e-6:
            return None
        c = (c[0] / Lc * sentido, c[1] / Lc * sentido)
        d_ = max(direcoes, key=lambda x: abs(x[0] * c[0] + x[1] * c[1]))
        if abs(d_[0] * c[0] + d_[1] * c[1]) < math.cos(math.radians(20.0)):
            return None
        return d_ if d_[0] * c[0] + d_[1] * c[1] > 0 else (-d_[0], -d_[1])
    t1 = direcao_na_ponta(A, pts[1], 1.0)          # entrando no arco
    t2 = direcao_na_ponta(E, pts[-2], -1.0)        # saindo dele
    if t1 is not None and t2 is not None:
        # a diagonal é a bissetriz das duas retas, tangente ao círculo do lado do arco
        dm = (t1[0] + t2[0], t1[1] + t2[1])
        Ld = math.hypot(*dm)
        if Ld > 1e-6:
            dm = (dm[0] / Ld, dm[1] / Ld)
            nrm = (-dm[1], dm[0])
            R = math.dist(A, (cx, cy))
            if nrm[0] * (M[0] - cx) + nrm[1] * (M[1] - cy) < 0:
                nrm = (-nrm[0], -nrm[1])
            Mt = (cx + nrm[0] * R, cy + nrm[1] * R)
            no1 = _cruzamento(A, (A[0] + t1[0], A[1] + t1[1]), Mt, (Mt[0] + dm[0], Mt[1] + dm[1]))
            no2 = _cruzamento(E, (E[0] + t2[0], E[1] + t2[1]), Mt, (Mt[0] + dm[0], Mt[1] + dm[1]))
            if no1 is not None and no2 is not None:
                return [no1, no2]
    no1 = _cruzamento(A, tangente(A), M, tangente(M))
    no2 = _cruzamento(E, tangente(E), M, tangente(M))
    if no1 is None or no2 is None:
        return None
    return [no1, no2]


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
    direcoes: Dict[str, list] = {}               # peça → direções das retas junto ao arco (do contorno fechado)

    def trechos_de(e):
        pts = [tuple(p) for p in e.vertices]
        n = len(pts)
        if n < 6:
            return pts, []
        # numa polilinha fechada, gira a lista até nenhum arco atravessar a emenda dela
        trechos = _trechos_curvos(pts, e.fechada)
        if e.fechada:
            for _ in range(n):
                if all(j < n for _, j in trechos):
                    break
                pts = pts[1:] + pts[:1]
                trechos = _trechos_curvos(pts, True)
        return pts, trechos

    def corda_do_arco(pts, i, j):
        a, b = min(i + 1, len(pts) - 1), max(min(j, len(pts)) - 1, 0)
        return math.dist(pts[a], pts[b])
    # o joelho de cada peça: o maior arco dela. Arco bem menor (a transição curta do banzo
    # para o joelho) não é canto e fica como o modelo traz
    maior: Dict[str, float] = {}
    for e in novas:
        if isinstance(e, Polilinha) and (e.atributos or {}).get("origem") in ids:
            pts, trechos = trechos_de(e)
            for i, j in trechos:
                o_ = (e.atributos or {}).get("origem")
                maior[o_] = max(maior.get(o_, 0.0), corda_do_arco(pts, i, j))
    for e in novas:
        if not isinstance(e, Polilinha) or (e.atributos or {}).get("origem") not in ids:
            continue
        pts, trechos = trechos_de(e)
        n = len(pts)
        origem = (e.atributos or {}).get("origem")
        todos = trechos
        trechos = [(i, j) for i, j in todos if corda_do_arco(pts, i, j) >= FRACAO_JOELHO * maior.get(origem, 0.0)]
        # os arcos pequenos (transição do banzo para o joelho) viram a reta entre as pontas
        pequenos = [t for t in todos if t not in trechos]
        if not trechos and not pequenos:
            continue
        preparadas.append((e, pts, trechos, origem, pequenos))
        if not (len(trechos) == 1 and trechos[0][0] == 0 and trechos[0][1] == n - 1 and not e.fechada):
            # as direções das retas junto ao arco (de qualquer polilinha que as tenha, aberta
            # ou fechada), para as arestas que vierem só como arco
            for i, j in trechos:
                if j < n and j - i >= 3:
                    for p_, q_ in ((pts[i], pts[i + 1]), (pts[j - 1], pts[j])):
                        L_ = math.dist(p_, q_)
                        if L_ > 1e-6:
                            direcoes.setdefault(origem, []).append(((q_[0] - p_[0]) / L_, (q_[1] - p_[1]) / L_))
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
    for e, pts, trechos, origem, pequenos in preparadas:
        mudou = False
        nos_e = []                                  # as pontas da diagonal: os nós do chanfro
        for i, j in sorted(trechos + pequenos, reverse=True):
            if j >= len(pts) or j - i < 3:
                continue
            if (i, j) in pequenos:
                pts = pts[:i + 2] + pts[j - 1:]          # só as pontas do arco: a reta entre elas
                mudou = True
                continue
            # o arco vai de pts[i+1] a pts[j-1] (pts[i] e pts[j] são as outras pontas dos
            # trechos retos vizinhos): os vértices do meio saem, fica a diagonal
            a, b = pts[i + 1], pts[j - 1]
            # polilinha que é só o arco (as arestas das abas vindas separadas do contorno):
            # nós pelas tangentes exatas
            novos = _nos_do_arco_puro(pts, direcoes.get(origem)) if (i == 0 and j == len(pts) - 1 and not e.fechada) else None
            if novos is None:
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
        if nos_e:
            e.atributos = dict(e.atributos or {}, chanfro="diagonal",
                               nos_chanfro=[[round(x, 2), round(y, 2)] for x, y in nos_e])
    return saida


#: Arco com corda menor que esta fração da do maior arco da mesma peça não é o joelho.
FRACAO_JOELHO = 0.5


def _nos_das_quebras(novas: List, ids: set, giro_minimo: float = 2.0) -> None:
    """Peça quebrada em retas no 3D: cada linha dela ganha `nos_chanfro` nas quinas (o
    vértice interno onde a direção muda), como `_chanfrar_cantos` faz na peça com arco."""
    for e in novas:
        if not isinstance(e, Polilinha) or (e.atributos or {}).get("origem") not in ids or (e.atributos or {}).get("nos_chanfro"):
            continue
        pts = [tuple(p) for p in e.vertices]
        n = len(pts)
        nos = []
        for k in range(n):
            if not e.fechada and (k == 0 or k == n - 1):
                continue
            a, b, c = pts[k - 1], pts[k], pts[(k + 1) % n]
            u = (b[0] - a[0], b[1] - a[1])
            v = (c[0] - b[0], c[1] - b[1])
            lu, lv = math.hypot(*u), math.hypot(*v)
            if lu < 1e-6 or lv < 1e-6:
                continue
            cosang = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (lu * lv)))
            if math.degrees(math.acos(cosang)) >= giro_minimo:
                nos.append([round(b[0], 2), round(b[1], 2)])
        if nos:
            e.atributos = dict(e.atributos or {}, chanfro="quebra", nos_chanfro=nos)

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
    # A peça quebrada em retas no 3D (Cantos redondos) já vem do modelo como a fábrica
    # monta — o joelho termina no nó em meia-esquadria e o banzo já foi esticado até ele —,
    # então só ganha a linha de emenda; mexer nas pontas do banzo aqui torcia as linhas
    # (a aba ia parar no contorno de baixo e cruzava o perfil até a cumeeira).
    moveis = [e for e in canto if (e.atributos or {}).get("chanfro") != "quebra"]
    outras = [e for e in novas if isinstance(e, (Polilinha, Linha)) and (e.atributos or {}).get("origem") not in ids]
    banzos = [e for e in outras if e.camada == "BANZOS"]

    def vertices(e):
        return list(e.vertices) if isinstance(e, Polilinha) else [e.a, e.b]
    # 1) o banzo avança até o nó: o trecho reto entre o nó e a ponta que encosta no banzo sai.
    # Primeiro decide tudo com as posições originais (a ponta do banzo é a mesma para as
    # várias linhas da peça), depois move.
    juncoes = [w for b_ in banzos for w in vertices(b_)]
    movimentos = []                                  # (ponta antiga m, nó q)
    for e in moveis:
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
    # a linha de emenda de cada nó: o par dele (o nó do outro contorno da mesma peça, a
    # menos de EMENDA_MAX). O banzo termina nela, em meia-esquadria com a peça do canto
    todos_nos = [(float(q[0]), float(q[1])) for e in moveis for q in e.atributos["nos_chanfro"]]

    def par_do_no(q):
        cand = [(math.dist(q, r), r) for r in todos_nos if 5.0 < math.dist(q, r) <= EMENDA_MAX]
        return min(cand)[1] if cand else None

    compridas: Dict[tuple, list] = collections.defaultdict(list)   # nó → [(ponta de longe, ponta nova)]

    def destino(w, longe=None):
        cand = [(math.dist(w, q), q) for m, q in movimentos if perto(w, m)]
        if not cand:
            return w
        q = min(cand)[1]
        if longe is None or math.dist(w, longe) < 1e-6:
            return q
        # linha comprida do banzo (anda na própria direção): termina onde cruza a linha de
        # emenda — o contorno de fora cai no nó de fora, o de dentro no de dentro, a aba no
        # meio; a ponta do banzo fica colada na peça do canto
        par = par_do_no(q)
        L0 = math.dist(w, longe)
        d0 = ((w[0] - longe[0]) / L0, (w[1] - longe[1]) / L0)
        mv0 = math.dist(w, q)
        if par is not None and mv0 > 1e-6 and                 abs(((q[0] - w[0]) * d0[0] + (q[1] - w[1]) * d0[1]) / mv0) >= math.cos(math.radians(15.0)):
            x = _cruzamento(longe, w, q, par)
            if x is not None and math.dist(x, q) <= EMENDA_MAX + 20.0:
                x = (round(x[0], 2), round(x[1], 2))
                compridas[q].append((longe, x))
                return x
        # a ponta desliza na direção da própria linha até a altura do nó: a linha da aba,
        # que não passa pelo nó, ia girar em volta da outra ponta (o banzo "torcia")
        L = math.dist(w, longe)
        d = ((w[0] - longe[0]) / L, (w[1] - longe[1]) / L)
        mv = math.dist(w, q)
        # só desliza quem anda na própria direção (as linhas compridas do banzo); a tampa da
        # ponta, curta e atravessada, vai inteira até o nó — deslizando ao longo dela mesma
        # ela ficava no lugar antigo e a ponta do banzo desmanchava
        if mv < 1e-6 or abs(((q[0] - w[0]) * d[0] + (q[1] - w[1]) * d[1]) / mv) < math.cos(math.radians(15.0)):
            return q
        t = (q[0] - longe[0]) * d[0] + (q[1] - longe[1]) * d[1]
        return (round(longe[0] + d[0] * t, 2), round(longe[1] + d[1] * t, 2))
    if movimentos:
        for o in outras:
            if o.camada == "CHAPAS":
                continue
            if isinstance(o, Polilinha):
                vs = list(o.vertices)
                n = len(vs)
                novos = []
                for k, w in enumerate(vs):
                    viz = [vs[j % n] for j in (k - 1, k + 1) if (0 <= j < n) or o.fechada]
                    longe = max(viz, key=lambda x: math.dist(x, w)) if viz else None
                    novos.append(destino(w, longe))
                o.vertices = novos
            else:
                o.a, o.b = destino(o.a, o.b), destino(o.b, o.a)
        _quinas_da_emenda(moveis, outras, compridas, par_do_no, perto)
    # 2) a linha de emenda em cada nó: o nó do contorno de fora com o do de dentro
    por_origem: Dict[str, list] = collections.defaultdict(list)
    candidatos: Dict[str, list] = collections.defaultdict(list)
    for e in canto:
        antigos = [(float(q[0]), float(q[1])) for q in e.atributos["nos_chanfro"]]
        for k, q in enumerate(e.atributos.get("nos_quina") or e.atributos["nos_chanfro"]):
            q = (float(q[0]), float(q[1]))
            movido = k < len(antigos) and math.dist(q, antigos[k]) > 0.05
            candidatos[e.atributos.get("origem")].append((not movido, q))
    for origem, cand in candidatos.items():
        lista = por_origem[origem]
        # o nó que foi para a quina vale mais; outro nó a menos de 12 mm dele é o mesmo
        # (a ponta da linha de aba da peça do canto)
        for _, q in sorted(cand, key=lambda t: t[0]):
            if not any(math.dist(q, w) < 12.0 for w in lista):
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
                                             emenda=True, chanfro=None, nos_chanfro=None, nos_quina=None)))


def _quinas_da_emenda(canto, outras, compridas, par_do_no, perto) -> None:
    """Fecha a meia-esquadria do banzo com a peça do canto: em cada nó, a quina é o
    cruzamento da linha de contorno do banzo (a comprida mais perto do nó) com o lado da
    peça do canto que chega nele — no modelo as faces não se encontram exatamente no nó, e
    sobrava um degrau de alguns milímetros. O nó da peça do canto, a tampa do banzo e a
    linha da aba (que termina na emenda entre as duas quinas) acompanham."""
    quina: Dict[tuple, tuple] = {}
    lado: Dict[tuple, tuple] = {}
    for e in canto:
        vs = [tuple(v) for v in e.vertices]
        n = len(vs)
        for k, v in enumerate(vs):
            q = next((q for q in compridas if perto(v, q, 0.05)), None)
            if q is None:
                continue
            viz = [vs[j % n] for j in (k - 1, k + 1) if (0 <= j < n) or e.fechada]
            if viz:
                lado[q] = max(viz, key=lambda x: math.dist(x, v))
    for q, lista in compridas.items():
        if q not in lado or not lista:
            continue
        # a linha de contorno do banzo é a que passa mais perto do nó
        def afastamento(item):
            longe, x = item
            L = math.dist(longe, x)
            return abs((q[0] - longe[0]) * (x[1] - longe[1]) - (q[1] - longe[1]) * (x[0] - longe[0])) / L if L > 1e-6 else 1e9
        longe, x = min(lista, key=afastamento)
        X = _cruzamento(longe, x, lado[q], q)
        if X is not None and math.dist(X, q) <= 40.0:
            quina[q] = (round(X[0], 2), round(X[1], 2))
    if not quina:
        return

    def nova(w):
        for q, X in quina.items():
            if perto(w, q, 0.05):
                return X
        return w
    # pontas novas das linhas compridas: o contorno vai para a quina; as outras (a aba)
    # terminam na emenda entre as duas quinas
    troca_ponta: Dict[tuple, tuple] = {}
    for q, lista in compridas.items():
        par = par_do_no(q)
        a_ = quina.get(q, q)
        b_ = quina.get(par, par) if par is not None else None
        for longe, x in lista:
            if q in quina and math.dist(x, a_) < 1e-9:
                continue
            if b_ is None:
                continue
            X = _cruzamento(longe, x, a_, b_)
            if X is not None and math.dist(X, x) <= 40.0:
                troca_ponta[x] = (round(X[0], 2), round(X[1], 2))
        # a de contorno
        if q in quina:
            longe, x = min(lista, key=lambda it: math.dist(it[1], quina[q]))
            troca_ponta[x] = quina[q]

    def ajuste(w):
        w2 = troca_ponta.get(tuple(w))
        return w2 if w2 is not None else nova(tuple(w))
    for o in outras:
        if o.camada == "CHAPAS":
            continue
        if isinstance(o, Polilinha):
            o.vertices = [ajuste(w) for w in o.vertices]
        else:
            o.a, o.b = ajuste(o.a), ajuste(o.b)
    # as emendas (quina de fora – quina de dentro): a linha de aba da peça do canto, que
    # tem o nó dela a poucos milímetros do de fora, também termina na emenda
    emendas = []
    for q, X in quina.items():
        par = par_do_no(q)
        if par is not None and par in quina:
            emendas.append((X, quina[par]))

    def na_emenda(v, viz):
        for a_, b_ in emendas:
            L = math.dist(a_, b_)
            if L < 1e-6:
                continue
            dist_ = abs((v[0] - a_[0]) * (b_[1] - a_[1]) - (v[1] - a_[1]) * (b_[0] - a_[0])) / L
            if dist_ > 15.0 or min(math.dist(v, a_), math.dist(v, b_)) > L + 15.0:
                continue
            X = _cruzamento(viz, v, a_, b_)
            if X is not None and math.dist(X, v) <= 20.0:
                return (round(X[0], 2), round(X[1], 2))
        return v
    for e in canto:
        vs = [tuple(v) for v in e.vertices]
        n = len(vs)
        nos = [(float(a), float(b)) for a, b in e.atributos["nos_chanfro"]]
        movidos = {}
        novos = []
        for k, v in enumerate(vs):
            w = nova(v)
            if w == v and any(perto(v, q, 0.05) for q in nos):
                viz = [vs[j % n] for j in (k - 1, k + 1) if (0 <= j < n) or e.fechada]
                if viz:
                    w = na_emenda(v, max(viz, key=lambda x: math.dist(x, v)))
            if w != v:
                movidos[v] = w
            novos.append(w)
        e.vertices = novos
        e.atributos = dict(e.atributos, nos_quina=[list(movidos.get(q, nova(q))) for q in nos])


def _so_bordas_externas(desenho: Desenho, entidades: Sequence, ids_barras: set, camada_de: Dict[str, str]) -> None:
    """Na elevação do conjunto, cada barra fica só com o contorno de fora do perfil: a aresta de
    dentro (a espessura do U, a outra aba da cantoneira), que saía como uma segunda linha colada na
    borda, e a cópia fina da borda saem (pedido do usuário, 28/09 — o padrão do corte das tesouras
    do projetista). Uma linha é borda quando a peça inteira fica de um lado dela, no trecho que ela
    ocupa; a de dentro tem peça dos dois lados. As linhas de emenda do canto ficam."""
    por: Dict[str, list] = collections.defaultdict(list)
    for e in entidades:
        a = e.atributos or {}
        if a.get("origem") in ids_barras and isinstance(e, (Linha, Polilinha)) and e.camada not in ("FURO", "EIXO") \
                and not a.get("emenda"):
            por[a["origem"]].append(e)
    for origem, ents in por.items():
        segs = []
        for e in ents:
            if isinstance(e, Linha):
                segs.append((tuple(e.a), tuple(e.b), e))
            else:
                v = [tuple(q) for q in e.vertices] + ([tuple(e.vertices[0])] if e.fechada and len(e.vertices) > 2 else [])
                segs += [(v[i], v[i + 1], e) for i in range(len(v) - 1)]
        segs = [s for s in segs if math.dist(s[0], s[1]) > 0.5]

        def borda(a_, b_):
            """a peça inteira de um lado da linha, no trecho dela: cada outra linha da peça é
            recortada no trecho (a face do outro lado do joelho atravessa o trecho sem ter ponta
            dentro dele) e conta o lado de cada ponta do pedaço"""
            L = math.dist(a_, b_)
            tx, ty = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
            lado = set()
            for c_, d_, _e in segs:
                sc = (c_[0] - a_[0]) * tx + (c_[1] - a_[1]) * ty
                sd = (d_[0] - a_[0]) * tx + (d_[1] - a_[1]) * ty
                hc = -(c_[0] - a_[0]) * ty + (c_[1] - a_[1]) * tx
                hd = -(d_[0] - a_[0]) * ty + (d_[1] - a_[1]) * tx
                lo, hi = 1.0, L - 1.0
                if max(sc, sd) < lo or min(sc, sd) > hi:
                    continue
                if abs(sd - sc) < 1e-9:
                    amostras = [hc, hd]
                else:
                    amostras = []
                    for s_lim in (max(min(sc, sd), lo), min(max(sc, sd), hi)):
                        f = (s_lim - sc) / (sd - sc)
                        amostras.append(hc + (hd - hc) * f)
                for h in amostras:
                    if abs(h) > 0.3:
                        lado.add(h > 0)
                        if len(lado) == 2:
                            return False
            return True

        manter: List[tuple] = []
        # as linhas grossas primeiro: a cópia fina de uma borda já mantida não entra de novo
        for a_, b_, e in sorted(segs, key=lambda s: s[2].camada == "VISTA-FINA"):
            if not borda(a_, b_):
                continue
            L = math.dist(a_, b_)
            tx, ty = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
            repetida = False
            for c_, d_, _e in manter:
                # a mesma borda (colada e paralela, cobrindo este trecho)
                if max(abs(-(q[0] - c_[0]) * ((d_[1] - c_[1]) / max(math.dist(c_, d_), 1e-9))
                           + (q[1] - c_[1]) * ((d_[0] - c_[0]) / max(math.dist(c_, d_), 1e-9))) for q in (a_, b_)) <= 0.3:
                    s0, s1 = sorted(((q[0] - c_[0]) * tx + (q[1] - c_[1]) * ty) for q in (c_, d_))
                    sa, sb = sorted(((q[0] - c_[0]) * tx + (q[1] - c_[1]) * ty) for q in (a_, b_))
                    if sa >= s0 - 0.5 and sb <= s1 + 0.5:
                        repetida = True
                        break
            if not repetida:
                manter.append((a_, b_, e))
        for e in ents:
            desenho.remover(e.id)
        for a_, b_, e in manter:
            cam = e.camada if e.camada != "VISTA-FINA" else camada_de.get(origem, "VISTA")
            atr = {k: v for k, v in (e.atributos or {}).items() if k not in ("nos_chanfro", "nos_quina", "chanfro")}
            desenho.add(Linha(camada=cam, a=(round(a_[0], 2), round(a_[1], 2)), b=(round(b_[0], 2), round(b_[1], 2)), atributos=atr))


def _cortes_das_tercas(doc: Documento, instancia: Sequence, origem, u, v, w, u0: float, v0: float,
                       segs_bz: Sequence[tuple], dx: float, dy: float) -> Tuple[List[tuple], List[List[tuple]], List[tuple]]:
    """O que o plano da tesoura (o do meio da instância) corta em volta dela, como no corte das
    tesouras do projetista: (segmentos das terças, polilinhas da telha), já na célula.

    Terça: a peça fora da tesoura, comprida na direção do plano (atravessa, ou termina a até 300 mm
    dele — a emendada em cima da tesoura), de frente para ele (a peça toda cabe em 600 mm no
    desenho: a mão-francesa e a corrente inclinadas não entram), seção de 25 a 400 mm, encostada por
    fora no contorno da tesoura (até 400 mm): as de cima do banzo, as da cumeeira e as de parede ao
    lado do pilar. Cada face da malha cortada dá um segmento.

    Telha (camada de telhas): só o contorno de baixo, o lado virado para a estrutura, numa polilinha
    — para ver se a telha pega na estrutura (pedido do usuário, 28/09)."""
    from nucleo3d.geometria import malha
    ws = [_dot(_sub(q, origem), w) for e in instancia for q in e.vertices]
    if not ws or not segs_bz:
        return [], [], []
    w0 = (min(ws) + max(ws)) / 2.0
    ids = {e.id for e in instancia}
    # o contorno das barras (sem as chapas: as cantoneiras de apoio saem da tesoura e o casco com elas
    # engolia a terça da cumeeira e a de parede entre dois apoios)
    casco = _casco([(_dot(_sub(q, origem), u) - u0 + dx, _dot(_sub(q, origem), v) - v0 + dy)
                    for e in instancia if not _tipo_ifc(e).startswith("IfcPlate") for q in e.vertices])
    if len(casco) < 3:
        return [], [], []
    cx = sum(q[0] for q in casco) / len(casco)
    cy = sum(q[1] for q in casco) / len(casco)
    bx0, bx1 = min(q[0] for q in casco) - 400.0, max(q[0] for q in casco) + 400.0
    by0, by1 = min(q[1] for q in casco) - 400.0, max(q[1] for q in casco) + 400.0
    casco_y0 = by0 + 400.0

    def dentro_do_casco(q, folga=0.0):
        return _trecho_dentro(q, q, casco, folga) is not None

    def ate_o_casco(q):
        if dentro_do_casco(q):
            return 0.0
        return min(_dist_ponto_seg(q, casco[i], casco[(i + 1) % len(casco)]) for i in range(len(casco)))

    def dentro_da_secao(q, segs):
        n = 0
        for a_, b_ in segs:
            if (a_[1] > q[1]) != (b_[1] > q[1]):
                xq = a_[0] + (q[1] - a_[1]) * (b_[0] - a_[0]) / (b_[1] - a_[1])
                if xq > q[0]:
                    n += 1
        return n % 2 == 1

    fora = []
    por_peca: List[list] = []                                 # as seções das terças, uma lista por peça
    telha: List[tuple] = []
    ondas: List[float] = []                                   # a altura da onda (TP40 → 40 mm)
    centros: List[tuple] = []
    for ent in doc.entidades.values():
        if ent.id in ids or getattr(ent, "tipo", "") not in ("barra", "solido"):
            continue
        eh_telha = "telha" in str(getattr(ent, "camada", "") or "").lower()
        if eh_telha:
            m_onda = re.search(r"TP\s*(\d+)", str(_marcas(ent).get("perfil") or getattr(ent, "nome", "") or "").upper())
            if m_onda:
                ondas.append(float(m_onda.group(1)))
        try:
            vs, fs = malha(ent)
        except Exception:                                     # peça sem malha (perfil desconhecido)
            continue
        if not vs:
            continue
        pw = [_dot(_sub(q, origem), w) - w0 for q in vs]
        if max(pw) - min(pw) < 800.0:
            continue
        # atravessa o plano, ou termina a até 300 mm dele (a terça emendada em cima da tesoura): o corte
        # é no plano ou, na que termina antes, 1 mm para dentro da ponta
        if min(pw) > -1.0:
            if min(pw) > 300.0:
                continue
            corte = min(pw) + 1.0
        elif max(pw) < 1.0:
            if max(pw) < -300.0:
                continue
            corte = max(pw) - 1.0
        else:
            corte = 0.0
        pu = [_dot(_sub(q, origem), u) - u0 + dx for q in vs]
        pv = [_dot(_sub(q, origem), v) - v0 + dy for q in vs]
        if not eh_telha and (max(pu) - min(pu) > 600.0 or max(pv) - min(pv) > 600.0):
            continue                                          # peça de través (mão-francesa, corrente)

        def fatiar(c):
            """os segmentos da malha cortada em w = c (a face com mais de dois cruzamentos — a alma com
            os furos — dá os pares em ordem ao longo dela)"""
            pw_ = [x - c for x in pw]
            fora_ = []
            for f in fs:
                pts = []
                for i in range(len(f)):
                    a_i, b_i = f[i], f[(i + 1) % len(f)]
                    da, db = pw_[a_i], pw_[b_i]
                    if (da > 0) != (db > 0):
                        t = da / (da - db)
                        pts.append((pu[a_i] + (pu[b_i] - pu[a_i]) * t, pv[a_i] + (pv[b_i] - pv[a_i]) * t))
                if len(pts) > 2:
                    ex_ = max(pts, key=lambda q: q[0])[0] - min(pts, key=lambda q: q[0])[0]
                    ey_ = max(pts, key=lambda q: q[1])[1] - min(pts, key=lambda q: q[1])[1]
                    pts.sort(key=lambda q: q[0] if ex_ >= ey_ else q[1])
                for k in range(0, len(pts) - 1, 2):
                    if math.dist(pts[k], pts[k + 1]) > 0.5:
                        fora_.append((pts[k], pts[k + 1]))
            return fora_

        def soltas(sg_):
            cont = collections.Counter((round(q[0] * 2) / 2, round(q[1] * 2) / 2) for ab in sg_ for q in ab)
            return sum(1 for n_ in cont.values() if n_ == 1)
        # a terça é reta: a seção é a mesma ao longo dela. No plano da tesoura (ou na ponta dela) o
        # corte pode cair num furo da ligação ou na ponta cortada e sair em pedaços (pedido do usuário,
        # 28/09: "corrija a representação do corte das terças") — fica o corte ali perto, dentro da
        # peça, que fecha o contorno
        candidatos = [corte] if eh_telha else [corte + o for o in (0.0, 20.0, -20.0, 45.0, -45.0, 90.0, -90.0, 150.0, -150.0)
                                              if min(pw) + 0.5 < corte + o < max(pw) - 0.5] or [corte]
        segs = min((fatiar(c) for c in candidatos), key=lambda sg_: (soltas(sg_), -sum(math.dist(*ab) for ab in sg_)))
        if not segs:
            continue
        if eh_telha:
            pts = [q for sg in segs for q in sg]
            # a telha toda abaixo das barras é o forro (TP40 0,50 da Sala, a 4,50 m): o corte dele
            # saía em riscos soltos debaixo do banzo (pedido do usuário, 28/09) — aqui fica só a cobertura
            if max(q[1] for q in pts) < casco_y0 + 1.0:
                continue
            # a direção da telha no corte (a maior extensão da seção) e, dela, só as faces compridas
            # viradas para a estrutura
            mx_ = sum(q[0] for q in pts) / len(pts)
            my_ = sum(q[1] for q in pts) / len(pts)
            sxx = sum((q[0] - mx_) ** 2 for q in pts)
            syy = sum((q[1] - my_) ** 2 for q in pts)
            sxy = sum((q[0] - mx_) * (q[1] - my_) for q in pts)
            ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
            tx, ty = math.cos(ang), math.sin(ang)
            for a_, b_ in segs:
                L = math.dist(a_, b_)
                sx, sy = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
                if abs(sx * tx + sy * ty) < 0.866:            # face de ponta (mais de 30° da telha)
                    continue
                m = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)
                nx, ny = -sy, sx
                if dentro_da_secao((m[0] + nx * 0.3, m[1] + ny * 0.3), segs):
                    nx, ny = -nx, -ny                         # normal para fora da telha
                if nx * (cx - m[0]) + ny * (cy - m[1]) <= 0:
                    continue                                  # a face de cima
                tt = _trecho_dentro(a_, b_, [(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)], 0.0)
                if tt:
                    em = lambda t: (a_[0] + (b_[0] - a_[0]) * t, a_[1] + (b_[1] - a_[1]) * t)
                    telha.append((em(tt[0]), em(tt[1]), ent.id, (nx, ny)))
            continue
        cu = [q[0] for sg in segs for q in sg]
        cv = [q[1] for sg in segs for q in sg]
        if max(max(cu) - min(cu), max(cv) - min(cv)) > 400.0:
            continue                                          # seção grande demais: não é terça
        if max(max(cu) - min(cu), max(cv) - min(cv)) < 25.0:
            continue                                          # a corrente, o tirante
        mx, my = (min(cu) + max(cu)) / 2, (min(cv) + max(cv)) / 2
        # encostada por fora no contorno da tesoura (a de dentro — o travamento — não é terça)
        if dentro_do_casco((mx, my), 20.0):
            continue
        if min(ate_o_casco(q) for sg in segs for q in sg) > 400.0:
            continue
        if any(math.dist((mx, my), c_) < 30.0 for c_ in centros):
            continue                                          # as duas terças da emenda: um corte só
        centros.append((mx, my))
        fora.append((ent.id, str(_marcas(ent).get("nome") or _marcas(ent).get("posicao") or ent.nome or ""), segs))
        por_peca.append(segs)
    # no traspasse o plano corta as duas telhas, e o chapéu da cumeeira passa por cima delas: fica só
    # o de baixo — o trecho de uma face que tem outra telha paralela logo abaixo dela (até 60 mm, entre
    # ela e a estrutura) sai; no vão entre as telhas (a cumeeira) o chapéu fica
    def de_baixo(i, sg):
        a_, b_, id_, (nx, ny) = sg
        L = math.dist(a_, b_)
        tx, ty = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
        cobertos = []
        for j, (c_, d_, id2, _n2) in enumerate(telha):
            if id2 == id_:
                continue
            L2 = math.dist(c_, d_)
            if L2 < 1e-6 or abs(tx * (d_[1] - c_[1]) / L2 - ty * (d_[0] - c_[0]) / L2) > 0.087:
                continue
            h = [((q[0] - a_[0]) * nx + (q[1] - a_[1]) * ny) for q in (c_, d_)]
            if not all(0.3 < x_ <= 60.0 for x_ in h) and not (j < i and all(abs(x_) <= 0.3 for x_ in h)):
                continue
            s0, s1 = sorted(((q[0] - a_[0]) * tx + (q[1] - a_[1]) * ty) for q in (c_, d_))
            if s1 > 0.0 and s0 < L:
                cobertos.append((max(s0, 0.0), min(s1, L)))
        livres, t = [], 0.0
        for s0, s1 in sorted(cobertos):
            if s0 > t + 5.0:
                livres.append((t, s0))
            t = max(t, s1)
        if L > t + 5.0:
            livres.append((t, L))
        return [((a_[0] + tx * s0, a_[1] + ty * s0), (a_[0] + tx * s1, a_[1] + ty * s1)) for s0, s1 in livres]
    telha = [pedaco for i, sg in enumerate(telha) for pedaco in de_baixo(i, sg)]
    onda = sorted(ondas)[len(ondas) // 2] if ondas else 40.0
    polis, extras = _telha_assentada(_encadear(telha), por_peca, (cx, cy), onda=onda)
    return fora, polis, extras


def _telha_assentada(polis: Sequence[list], tercas: Sequence[list], centro: tuple, raio: Optional[float] = None,
                     folga_max: float = 60.0, onda: float = 40.0) -> Tuple[List[list], List[tuple]]:
    """A linha da telha como ela é montada (pedidos do usuário, 28/09):

    - assentada nas terças: cada reta comprida (a água, a parede, o forro de baixo do joelho — 500 mm
      ou mais) desce até encostar na terça mais alta embaixo dela (o modelo do TecnoMETAL deixa a
      telha uns 12 mm acima);
    - o canto com o raio da multi-dobra: as facetas entre duas retas (3 ou mais) viram o arco de raio
      interno comercial (R450 na TP40, o do detalhe das telhas) tangente às duas retas, anotado;
    - os parafusos: onde a reta encosta numa terça, um parafuso no meio do encosto (a haste entrando
      na aba e a cabeça na crista), para ver que a telha está na posição certa;
    - o perfil inteiro: a linha de baixo (a onda que assenta) e a de cima (a crista, a altura da onda
      acima; no canto o raio externo, R490 na TP40).

    `tercas`: os segmentos da seção de cada terça cortada. Devolve (polilinhas, extras), com os extras
    como ("linha", a, b, papel) e ("texto", posição, texto)."""
    if raio is None:
        from nucleo2d.detalhe.telhas import RAIO_INTERNO_COMERCIAL
        raio = RAIO_INTERNO_COMERCIAL
    pts_t = [[q for sg in segs for q in sg] for segs in tercas]
    saida, extras = [], []

    def direcoes(a_, b_):
        L = math.dist(a_, b_)
        t = ((b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L)
        n = (-t[1], t[0])
        m = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)
        if n[0] * (centro[0] - m[0]) + n[1] * (centro[1] - m[1]) < 0:
            n = (-n[0], -n[1])                                 # para o lado da estrutura
        return t, n, L

    for poli in polis:
        retas: List[list] = []
        for i in range(len(poli) - 1):
            a_, b_ = tuple(poli[i]), tuple(poli[i + 1])
            if math.dist(a_, b_) < 0.5:
                continue
            if retas and math.dist(retas[-1][1], a_) < 1.0:
                ra, rb = retas[-1]
                t1, _n1, _L1 = direcoes(ra, rb)
                t2, _n2, _L2 = direcoes(a_, b_)
                if abs(t1[0] * t2[1] - t1[1] * t2[0]) < 0.0175 and t1[0] * t2[0] + t1[1] * t2[1] > 0:
                    retas[-1] = [ra, b_]                       # a mesma reta em dois pedaços
                    continue
            retas.append([a_, b_])
        longa = [math.dist(*r) >= 500.0 for r in retas]
        # assentar cada reta comprida na terça mais alta embaixo dela; os parafusos nos encostos
        for k, r in enumerate(retas):
            t, n, L = direcoes(*r)
            if L < 200.0:
                continue                                       # faceta do canto
            hs = [(q[0] - r[0][0]) * n[0] + (q[1] - r[0][1]) * n[1]
                  for pts in pts_t for q in pts
                  if -1.0 <= (q[0] - r[0][0]) * t[0] + (q[1] - r[0][1]) * t[1] <= L + 1.0]
            hs = [h for h in hs if -5.0 <= h <= folga_max]
            if not hs:
                continue
            g = min(hs)
            # só a reta comprida desce até a terça; o trecho curto (o chapéu da cumeeira) fica onde está
            # e ganha os parafusos da terça em que encosta
            if longa[k] and abs(g) > 0.3:
                r[0] = (r[0][0] + n[0] * g, r[0][1] + n[1] * g)
                r[1] = (r[1][0] + n[0] * g, r[1][1] + n[1] * g)
            for pts in pts_t:
                ss = [(q[0] - r[0][0]) * t[0] + (q[1] - r[0][1]) * t[1] for q in pts
                      if -1.0 <= (q[0] - r[0][0]) * n[0] + (q[1] - r[0][1]) * n[1] <= (5.0 if longa[k] else g + 5.0)]   # as terças da água variam uns mm
                ss = [x for x in ss if -1.0 <= x <= L + 1.0]
                if not ss:
                    continue
                sm = (min(ss) + max(ss)) / 2.0
                pq = (r[0][0] + t[0] * sm, r[0][1] + t[1] * sm)
                cab = (pq[0] - n[0] * (onda + 2.0), pq[1] - n[1] * (onda + 2.0))
                extras.append(("linha", cab, (pq[0] + n[0] * 25.0, pq[1] + n[1] * 25.0), "parafuso_telha"))
                extras.append(("linha", (cab[0] - t[0] * 6.0, cab[1] - t[1] * 6.0),
                               (cab[0] + t[0] * 6.0, cab[1] + t[1] * 6.0), "parafuso_telha"))
        # o canto: as facetas entre duas retas viram o arco do raio comercial
        idx = [k for k in range(len(retas)) if longa[k]]
        cantos = {}
        for i, j in zip(idx, idx[1:]):
            if j - i - 1 < 3:
                continue
            (a1, b1), (a2, b2) = retas[i], retas[j]
            d1, _n, L1 = direcoes(a1, b1)
            d2, _n, L2 = direcoes(a2, b2)
            den = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(den) < 0.17:                                # menos de 10°: não é canto
                continue
            tt = ((a2[0] - a1[0]) * d2[1] - (a2[1] - a1[1]) * d2[0]) / den
            I = (a1[0] + d1[0] * tt, a1[1] + d1[1] * tt)
            theta = math.atan2(den, d1[0] * d2[0] + d1[1] * d2[1])
            T = raio * math.tan(abs(theta) / 2.0)
            s1 = (I[0] - a1[0]) * d1[0] + (I[1] - a1[1]) * d1[1] - T
            s2 = (I[0] - a2[0]) * d2[0] + (I[1] - a2[1]) * d2[1] + T
            if s1 <= 0.0 or s2 >= L2:
                continue
            P1 = (a1[0] + d1[0] * s1, a1[1] + d1[1] * s1)
            P2 = (a2[0] + d2[0] * s2, a2[1] + d2[1] * s2)
            sg = 1.0 if theta > 0 else -1.0
            C = (P1[0] - d1[1] * raio * sg, P1[1] + d1[0] * raio * sg)
            ang1 = math.atan2(P1[1] - C[1], P1[0] - C[0])
            npt = max(4, int(abs(math.degrees(theta)) / 5.0))
            arco = [(C[0] + raio * math.cos(ang1 + theta * f / npt), C[1] + raio * math.sin(ang1 + theta * f / npt))
                    for f in range(npt + 1)]
            cantos[i] = (j, P1, P2, arco)
            meio = arco[len(arco) // 2]
            fora_ = (meio[0] - C[0]) / raio, (meio[1] - C[1]) / raio
            # por dentro do arco (por fora ele caía em cima das cotas do joelho)
            extras.append(("texto", (meio[0] - fora_[0] * 90.0, meio[1] - fora_[1] * 90.0),
                           "R%d int. / R%d ext." % (round(raio), round(raio + onda))))
        verts: List[tuple] = []

        def por(q):
            if not verts or math.dist(verts[-1], q) > 0.5:
                verts.append(q)
        k = 0
        while k < len(retas):
            if k in cantos:
                j, P1, P2, arco = cantos[k]
                por(retas[k][0])
                for q in arco:
                    por(q)
                retas[j][0] = P2
                k = j
                continue
            por(retas[k][0])
            por(retas[k][1])
            k += 1
        # as retas assentadas descem uns 12 mm e as pontas que ficaram (o chapéu da cumeeira) viram
        # ganchos: sai o vértice em que a linha volta para trás (mais de 150°)
        mudou = True
        while mudou and len(verts) > 2:
            mudou = False
            for i in range(1, len(verts) - 1):
                p0, p1, p2 = verts[i - 1], verts[i], verts[i + 1]
                u1 = (p1[0] - p0[0], p1[1] - p0[1])
                u2 = (p2[0] - p1[0], p2[1] - p1[1])
                l1, l2 = math.hypot(*u1), math.hypot(*u2)
                if l1 < 1.0 or l2 < 1.0 or (u1[0] * u2[0] + u1[1] * u2[1]) / (l1 * l2) < -0.866:
                    del verts[i]
                    mudou = True
                    break
        if len(verts) >= 2:
            saida.append(verts)
            if onda > 0:
                saida.append(_deslocar_polilinha(verts, onda, centro))
    return saida, extras


def _deslocar_polilinha(verts: Sequence[tuple], d: float, centro: tuple) -> List[tuple]:
    """A polilinha deslocada de `d` para o lado de fora (o contrário de `centro`, decidido pelo
    trecho mais comprido e mantido na polilinha inteira), com os cantos em meia-esquadria."""
    segs = [(verts[i], verts[i + 1]) for i in range(len(verts) - 1) if math.dist(verts[i], verts[i + 1]) > 1e-6]
    if not segs:
        return list(verts)
    a_, b_ = max(segs, key=lambda sg: math.dist(*sg))
    L = math.dist(a_, b_)
    esq = (-(b_[1] - a_[1]) / L, (b_[0] - a_[0]) / L)
    m = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)
    lado = -1.0 if esq[0] * (centro[0] - m[0]) + esq[1] * (centro[1] - m[1]) > 0 else 1.0   # para fora

    def nrm(sg):
        L_ = math.dist(*sg)
        return (-(sg[1][1] - sg[0][1]) / L_ * lado, (sg[1][0] - sg[0][0]) / L_ * lado)
    pts = []
    for i in range(len(segs) + 1):
        n1 = nrm(segs[max(i - 1, 0)])
        n2 = nrm(segs[min(i, len(segs) - 1)])
        q = segs[i][0] if i < len(segs) else segs[-1][1]
        bx, by = n1[0] + n2[0], n1[1] + n2[1]
        c = (bx * bx + by * by) ** 0.5
        if c < 1e-6:
            bx, by, f = n1[0], n1[1], d
        else:
            bx, by = bx / c, by / c
            f = d / max(bx * n1[0] + by * n1[1], 0.2)          # meia-esquadria (limitada nos cantos vivos)
        pts.append((q[0] + bx * f, q[1] + by * f))
    return pts


def _encadear(segs: Sequence[tuple], tol: float = 10.0) -> List[List[tuple]]:
    """Junta segmentos em polilinhas pelas pontas (até `tol`); o segmento repetido (a telha que
    sobrepõe a outra) entra uma vez só."""
    unicos: List[tuple] = []
    for a_, b_ in segs:
        if any((math.dist(a_, c_) < 2.0 and math.dist(b_, d_) < 2.0) or (math.dist(a_, d_) < 2.0 and math.dist(b_, c_) < 2.0)
               for c_, d_ in unicos):
            continue
        unicos.append((a_, b_))
    polis: List[List[tuple]] = []
    livres = list(unicos)
    while livres:
        a_, b_ = livres.pop(0)
        poli = [a_, b_]
        cresceu = True
        while cresceu:
            cresceu = False
            for i, (c_, d_) in enumerate(livres):
                if math.dist(poli[-1], c_) <= tol:
                    poli.append(d_)
                elif math.dist(poli[-1], d_) <= tol:
                    poli.append(c_)
                elif math.dist(poli[0], d_) <= tol:
                    poli.insert(0, c_)
                elif math.dist(poli[0], c_) <= tol:
                    poli.insert(0, d_)
                else:
                    continue
                livres.pop(i)
                cresceu = True
                break
        polis.append(poli)
    return polis


def _familia_do_perfil(e) -> str:
    """"U100X50X3.04" → "U100X50": o perfil sem a espessura (o banzo e a descida dele no joelho têm a
    mesma seção nominal, às vezes em chapas diferentes)."""
    p_ = str(_marcas(e).get("perfil") or "").upper().replace(" ", "")
    partes = p_.split("X")
    return "X".join(partes[:2]) if len(partes) >= 3 else p_


def _alma_com_contorno(instancia: Sequence, alma: Dict[str, Tuple[tuple, tuple]], banzos: Sequence[tuple],
                       camada_de: Dict[str, str]) -> set:
    """As barras fora dos banzos que ficam com o contorno (peças de banzo, não da alma).

    Quando o banzo tem um perfil que a alma não usa (a treliça em U100X50 com a alma em U92X30): as
    barras com o perfil do banzo ligadas a ele, em cadeia — a horizontal e a descida do banzo de
    baixo no joelho, o montante de fechamento e a horizontal de baixo da cumeeira (pedido do usuário,
    28/09: "faltou essa parte do banzo inferior"; o U92X30 do joelho fica em eixo).

    Quando a alma tem o mesmo perfil do banzo, pela posição: a barra na continuação de um banzo (até
    5° e no eixo dele, ou até 20° saindo da ponta dele) e o montante com as duas pontas nas pontas
    dos banzos (o fechamento da cumeeira). Só contra os banzos, não contra as barras já aceitas."""
    pecas = {e.id: e for e in instancia}
    fam_bz = {_familia_do_perfil(e) for e in instancia if camada_de.get(e.id) == "BANZOS"} - {""}
    do_banzo = {k for k in alma if k in pecas and _familia_do_perfil(pecas[k]) in fam_bz}
    contorno = set()
    if do_banzo and len(do_banzo) <= len(alma) / 2.0:
        ligadas = list(banzos)
        mudou = True
        while mudou:
            mudou = False
            for k in sorted(do_banzo - contorno):
                a_, b_ = alma[k]
                if math.dist(a_, b_) < 100.0:
                    continue
                if any(_dist_ponto_seg(q, ca, cb) <= 150.0 for q in (a_, b_) for ca, cb in ligadas):
                    contorno.add(k)
                    ligadas.append((a_, b_))
                    mudou = True
        return contorno
    pontas_bz = [q for ab in banzos for q in ab]
    for k, (a_, b_) in alma.items():
        L = math.dist(a_, b_)
        if L < 100.0:
            continue
        vx, vy = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
        na_linha = False
        for ca, cb in banzos:
            Lc = math.dist(ca, cb)
            ux, uy = (cb[0] - ca[0]) / Lc, (cb[1] - ca[1]) / Lc
            sen = abs(ux * vy - uy * vx)
            if sen <= 0.087:                                # até 5°: no eixo do banzo
                if max(abs(-(q[0] - ca[0]) * uy + (q[1] - ca[1]) * ux) for q in (a_, b_)) <= 40.0:
                    na_linha = True
                    break
            if sen <= 0.342 and min(math.dist(q, w_) for q in (a_, b_) for w_ in (ca, cb)) <= 60.0:
                na_linha = True                             # até 20°, saindo da ponta
                break
        fechamento = camada_de.get(k) == "MONTANTES" and all(
            any(math.dist(q, w_) <= 200.0 for w_ in pontas_bz) for q in (a_, b_))
        if na_linha or fechamento:
            contorno.add(k)
    return contorno


def _trecho_dentro(a_, b_, casco: Sequence[tuple], folga: float = 1.0):
    """O trecho [t0, t1] do segmento a→b dentro do polígono convexo (anti-horário), a mais de
    `folga` das bordas; None se não entra."""
    t0, t1 = 0.0, 1.0
    n = len(casco)
    for i in range(n):
        p0, p1 = casco[i], casco[(i + 1) % n]
        ex, ey = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(ex, ey)
        if L < 1e-9:
            continue
        # distância com sinal para dentro (à esquerda da aresta)
        da = (ex * (a_[1] - p0[1]) - ey * (a_[0] - p0[0])) / L - folga
        db = (ex * (b_[1] - p0[1]) - ey * (b_[0] - p0[0])) / L - folga
        if da < 0 and db < 0:
            return None
        if da < 0 or db < 0:
            t = da / (da - db)
            if da < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
        if t1 - t0 <= 1e-6:
            return None
    return t0, t1


def _esconder_atras_dos_montantes(desenho: Desenho, entidades: Sequence, montantes: set, atras: set) -> None:
    """As linhas das peças de `atras` que passam por dentro do contorno de um montante de `montantes`
    saem nesse trecho (o banzo de baixo entrava 46 mm no montante de fechamento da cumeeira)."""
    if not montantes:
        return
    cascos = {}
    for e in entidades:
        o = (e.atributos or {}).get("origem")
        if o in montantes and isinstance(e, Linha):
            cascos.setdefault(o, []).extend([tuple(e.a), tuple(e.b)])
    cascos = {o: _casco(pts) for o, pts in cascos.items() if len(pts) >= 3}
    for e in entidades:
        o = (e.atributos or {}).get("origem")
        if o not in atras or o in montantes or not isinstance(e, Linha) or e.id not in desenho.entidades:
            continue
        pedacos = [(tuple(e.a), tuple(e.b))]
        for om, casco in cascos.items():
            if len(casco) < 3:
                continue
            novos = []
            for a_, b_ in pedacos:
                tt = _trecho_dentro(a_, b_, casco)
                if not tt:
                    novos.append((a_, b_))
                    continue
                em = lambda t: (a_[0] + (b_[0] - a_[0]) * t, a_[1] + (b_[1] - a_[1]) * t)
                if tt[0] > 1e-6:
                    novos.append((a_, em(tt[0])))
                if tt[1] < 1.0 - 1e-6:
                    novos.append((em(tt[1]), b_))
            pedacos = novos
        if len(pedacos) == 1 and pedacos[0] == (tuple(e.a), tuple(e.b)):
            continue
        desenho.remover(e.id)
        for a_, b_ in pedacos:
            if math.dist(a_, b_) > 0.5:
                desenho.add(Linha(camada=e.camada, a=(round(a_[0], 2), round(a_[1], 2)), b=(round(b_[0], 2), round(b_[1], 2)),
                                  atributos=dict(e.atributos or {})))


def _sem_larguras(xs: Sequence[float], fixos: set, meio: float, minimo: float = 60.0) -> Tuple[List[float], List[float]]:
    """A cadeia sem a largura dos perfis: de dois pontos seguidos a menos de `minimo`, fica o fixo
    (a face da ponta, as faces da cumeeira) ou o mais perto do meio da treliça. Devolve (os que
    ficam, os que saíram)."""
    ficam: List[float] = []
    sairam: List[float] = []
    for x in xs:
        if ficam and x - ficam[-1] < minimo:
            ant = ficam[-1]
            if ant in fixos and x in fixos:
                ficam.append(x)                      # a folga da cumeeira fica
            elif ant in fixos:
                sairam.append(x)
            elif x in fixos or abs(x - meio) < abs(ant - meio):
                sairam.append(ant)
                ficam[-1] = x
            else:
                sairam.append(x)
        else:
            ficam.append(x)
    return ficam, sairam


def _contorno_dos_banzos(desenho: Desenho, marca: str) -> Tuple[List[tuple], List[tuple]]:
    """O contorno dos banzos do conjunto desenhado: (segmentos, quinas). Quina é o vértice em que o
    contorno dobra (mais de 10°) — o vértice no meio de uma reta (a peça partida em dois traços) não
    conta: não é nó nem ponto de marcar."""
    segs = []
    for e in desenho.entidades.values():
        a = e.atributos or {}
        if e.camada != "BANZOS" or a.get("conjunto") != marca or a.get("detalhe") != "conjunto":
            continue
        if isinstance(e, Linha):
            segs.append((tuple(e.a), tuple(e.b)))
        elif isinstance(e, Polilinha):
            v = [tuple(q) for q in e.vertices] + ([tuple(e.vertices[0])] if e.fechada else [])
            segs += [(v[i], v[i + 1]) for i in range(len(v) - 1)]
    segs = [sg for sg in segs if math.dist(sg[0], sg[1]) > 1.0]
    quinas: List[tuple] = []
    for a_, b_ in segs:
        for q, r in ((a_, b_), (b_, a_)):
            d1 = math.atan2(r[1] - q[1], r[0] - q[0])
            for c_, d_ in segs:
                for q2, r2 in ((c_, d_), (d_, c_)):
                    if math.dist(q, q2) > 1.0 or (q2, r2) == (q, r):
                        continue
                    d2 = math.atan2(r2[1] - q2[1], r2[0] - q2[0])
                    giro = abs(math.degrees(d1 - d2)) % 360.0
                    giro = min(giro, 360.0 - giro)
                    if 10.0 < giro < 170.0 and not any(math.dist(q, w) < 1.0 for w in quinas):
                        quinas.append(q)
    return segs, quinas


def _eixos_das_faces(segs: Sequence[tuple], esp_min: float = 30.0, esp_max: float = 320.0) -> List[tuple]:
    """Os eixos dos trechos retos do contorno dos banzos: o meio de duas faces paralelas, afastadas
    entre `esp_min` e `esp_max` (a altura do perfil), no trecho em que as duas se sobrepõem — o banzo
    reto e também as pernas da peça dobrada do joelho (o pilar), que não têm um eixo reto só."""
    eixos: List[tuple] = []
    longos = [sg for sg in segs if math.dist(sg[0], sg[1]) >= 150.0]
    for i, (a_, b_) in enumerate(longos):
        L = math.dist(a_, b_)
        ux, uy = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
        for c_, d_ in longos[i + 1:]:
            L2 = math.dist(c_, d_)
            if abs(ux * (d_[1] - c_[1]) / L2 - uy * (d_[0] - c_[0]) / L2) > 0.02:
                continue
            dist = -(c_[0] - a_[0]) * uy + (c_[1] - a_[1]) * ux
            if not (esp_min <= abs(dist) <= esp_max):
                continue
            s0, s1 = sorted(((q[0] - a_[0]) * ux + (q[1] - a_[1]) * uy) for q in (c_, d_))
            lo, hi = max(0.0, s0), min(L, s1)
            if hi - lo < 0.5 * min(L, L2):
                continue
            nx, ny = -uy * dist / 2, ux * dist / 2
            eixos.append(((a_[0] + ux * lo + nx, a_[1] + uy * lo + ny), (a_[0] + ux * hi + nx, a_[1] + uy * hi + ny)))
    return eixos


def _alma_em_eixo(desenho: Desenho, entidades: Sequence, alma: Dict[str, Tuple[tuple, tuple]], camada_de: Dict[str, str],
                  quinas: Sequence[tuple] = (), apoios: Sequence[tuple] = (), encaixe: float = 200.0) -> List[tuple]:
    """A alma da treliça (montantes, diagonais, as barras do joelho) desenhada pela linha de trabalho,
    como o corte do projetista (regra do usuário, 28/09): cada barra vira uma linha só, no eixo; o
    montante fica no eixo dele; a ponta da diagonal vai ao nó: (1) a ponta do montante, quando ela
    chega na ponta dele (o nó do banzo); (2) senão, o cruzamento do eixo dela com o eixo do montante ou
    do banzo em que ela chega (a barra que encosta no meio do montante do joelho continua reta — antes
    ia para a ponta dele e saía torta); (3) senão, a quina do banzo (no joelho, onde o contorno dobra);
    (4) senão, o encontro com as outras diagonais que chegam ali. `alma`: id da peça → (a, b), o eixo
    já na célula; `apoios`: os eixos dos banzos (a, b). Os furos e as emendas ficam; o contorno da peça
    sai. Devolve os nós (as pontas das linhas desenhadas)."""
    if not alma:
        return []
    for e in list(entidades):
        a = e.atributos or {}
        if a.get("origem") in alma and isinstance(e, (Linha, Polilinha)) and e.camada not in ("FURO", "EIXO") \
                and not a.get("emenda"):
            desenho.remover(e.id)
    montantes = [ab for k, ab in alma.items() if camada_de.get(k) == "MONTANTES"]
    tops = [q for ab in montantes for q in ab]
    eixos = {k: list(ab) for k, ab in alma.items()}
    soltas = []                                          # (k, i) das pontas sem montante nem quina
    linhas_apoio = [tuple(ab) for ab in montantes] + [tuple(ab) for ab in apoios]

    def no_da_ponta(q, outra, so_cruzamento=False):
        tops_m = [(tip, (ma, mb)) for ma, mb in montantes for tip in (ma, mb)]
        # o primeiro eixo (montante ou banzo) que a reta da barra cruza, logo depois da ponta
        L = math.dist(q, outra)
        cruz = None
        if L > 1.0:
            ux, uy = (q[0] - outra[0]) / L, (q[1] - outra[1]) / L
            for i_l, (la, lb) in enumerate(linhas_apoio):
                x = _cruzamento(outra, q, la, lb)
                if x is None:
                    continue
                t = (x[0] - q[0]) * ux + (x[1] - q[1]) * uy
                if not (-80.0 <= t <= encaixe):
                    continue
                Ll = math.dist(la, lb)
                if Ll < 1.0:
                    continue
                s_ = ((x[0] - la[0]) * (lb[0] - la[0]) + (x[1] - la[1]) * (lb[1] - la[1])) / Ll
                if not (-30.0 <= s_ <= Ll + 30.0):
                    continue
                if cruz is None or abs(t) < cruz[0]:
                    cruz = (abs(t), x, i_l < len(montantes))
        if cruz is not None:
            x, no_montante = cruz[1], cruz[2]
            if so_cruzamento:
                return x
            # o nó do banzo: a barra chega no banzo junto da ponta de um montante — liga na ponta dele;
            # a que chega no próprio montante fica no cruzamento (no meio dele, no joelho), a não ser que
            # caia na ponta
            tip = min(tops_m, key=lambda tm: math.dist(tm[0], x))[0] if tops_m else None
            if tip is not None and math.dist(tip, x) <= (10.0 if no_montante else 120.0):
                return tip
            return x
        # sem cruzamento: a ponta de montante perto, a quina do joelho
        tip = min((tm[0] for tm in tops_m), key=lambda n: math.dist(n, q)) if tops_m else None
        if tip is not None and math.dist(tip, q) <= encaixe:
            return tip
        perto = min(quinas, key=lambda n: math.dist(n, q)) if quinas else None
        if perto is not None and math.dist(perto, q) <= encaixe:
            return perto
        return None

    def reta_ou_prumo(ab):
        ang = abs(math.degrees(math.atan2(ab[1][1] - ab[0][1], ab[1][0] - ab[0][0]))) % 180.0
        return min(ang, 180.0 - ang) < 5.0 or abs(ang - 90.0) < 5.0

    for k, ab in eixos.items():
        if camada_de.get(k) == "MONTANTES":
            continue
        originais = list(ab)
        # a barra deitada ou em pé (a horizontal do joelho) é como o montante: fica no eixo dela e só
        # vai até o cruzamento — a ponta anda na reta dela, não sai torta para um nó ao lado (regra do
        # usuário, 28/09: "não mexer nos montantes")
        fixa = reta_ou_prumo(originais)
        for i, q in enumerate(originais):
            achou = no_da_ponta(q, originais[1 - i], so_cruzamento=fixa)
            if achou is not None and fixa:
                o_ = originais[1 - i]
                L_ = math.dist(q, o_)
                ux, uy = (q[0] - o_[0]) / L_, (q[1] - o_[1]) / L_
                t_ = (achou[0] - o_[0]) * ux + (achou[1] - o_[1]) * uy
                achou = (o_[0] + ux * t_, o_[1] + uy * t_)
            if achou is not None:
                ab[i] = achou
            elif not fixa:
                soltas.append((k, i))
    usadas = set()
    for j, (k, i) in enumerate(soltas):
        if (k, i) in usadas:
            continue
        grupo = [(k, i)] + [(k2, i2) for k2, i2 in soltas[j + 1:] if k2 != k and (k2, i2) not in usadas
                            and math.dist(eixos[k2][i2], eixos[k][i]) <= encaixe]
        if len(grupo) > 1:
            mx = sum(eixos[g][h][0] for g, h in grupo) / len(grupo)
            my = sum(eixos[g][h][1] for g, h in grupo) / len(grupo)
            for g, h in grupo:
                eixos[g][h] = (mx, my)
                usadas.add((g, h))
    # de nó a nó: a ponta da barra inclinada que fica a até 80 mm da ponta de uma barra horizontal ou em
    # pé (a barra do joelho, o montante) vai para ela — no joelho a diagonal cruzava o B.14 a uns 50 mm do
    # nó da horizontal que chega ali
    ancoras = [(k2, q2) for k2, ab2 in eixos.items() if reta_ou_prumo(ab2) for q2 in ab2]
    for k, ab in eixos.items():
        if camada_de.get(k) == "MONTANTES" or reta_ou_prumo(ab):
            continue
        for i, q in enumerate(list(ab)):
            if any(math.dist(q, q2) <= 0.5 for k2, q2 in ancoras if k2 != k):
                continue                                 # já está num nó
            perto = [(math.dist(q, q2), q2) for k2, q2 in ancoras if k2 != k and 0.5 < math.dist(q, q2) <= 80.0]
            if perto:
                ab[i] = min(perto)[1]
    feitas: List[tuple] = []
    for k, (a_, b_) in eixos.items():
        if math.dist(a_, b_) < 5.0:
            continue
        if any(max(math.dist(a_, fa), math.dist(b_, fb)) < 15.0 or max(math.dist(a_, fb), math.dist(b_, fa)) < 15.0
               for fa, fb in feitas):
            continue                     # a cantoneira dupla (2L): as duas no mesmo eixo, uma linha só
        feitas.append((a_, b_))
        base = next((x for x in entidades if (x.atributos or {}).get("origem") == k), None)
        atr = {kk: vv for kk, vv in ((base.atributos or {}) if base is not None else {}).items()
               if kk not in ("nos_chanfro", "nos_quina", "chanfro")}
        atr["origem"] = k
        atr["eixo"] = True
        desenho.add(Linha(camada=camada_de.get(k, "DIAGONAIS"), a=(round(a_[0], 2), round(a_[1], 2)),
                          b=(round(b_[0], 2), round(b_[1], 2)), atributos=atr))
    return [q for ab in feitas for q in ab]


def _pontas_da_trelica(segs: Sequence[tuple], quinas: Sequence[tuple], nos: Sequence[tuple], dx: float, dy: float,
                       larg: float, alt: float, trechos_cima: Sequence[tuple], trechos_baixo: Sequence[tuple]) -> List[dict]:
    """As duas pontas da treliça para as cotas de produção (em coordenadas da célula). A zona da ponta
    é o que fica além do fim reto dos dois banzos — o joelho do canto, ou só a face da ponta. Uma
    referência só: o contorno pela **face de fora** (das quinas coladas de fora e de dentro fica a de
    fora, nunca a média — a média dava medida que não existe na peça) e os nós das barras que chegam
    na ponta. Para cada ponta: `face` (o x da face de fora, de onde saem as chamadas), `xs` e `ys`
    (quinas e nós), e o chanfro de fora do joelho."""
    if not segs or not trechos_cima or not trechos_baixo:
        return []

    def loc(q):
        return (q[0] - dx, q[1] - dy)
    segs = [(loc(a_), loc(b_)) for a_, b_ in segs]
    quinas = [loc(q) for q in quinas]
    nos = [loc(q) for q in nos]
    cx, cy = larg / 2.0, alt / 2.0

    def juntar(vals, centro, tol=30.0):
        """valores a menos de `tol` viram um só: o mais de fora (longe do centro) — a face de fora"""
        vals = sorted(vals)
        if not vals:
            return []
        grupos = [[vals[0]]]
        for x in vals[1:]:
            if x - grupos[-1][-1] <= tol:
                grupos[-1].append(x)
            else:
                grupos.append([x])
        return [round(max(g, key=lambda v: abs(v - centro)), 1) for g in grupos]

    angs = [math.degrees(math.atan2(t[2][1][1] - t[2][0][1], t[2][1][0] - t[2][0][0])) % 180.0
            for t in list(trechos_cima) + list(trechos_baixo) if t[2] is not None] + [0.0, 90.0]
    fora = []
    for lado in (-1, 1):
        if lado > 0:
            xz = min(max(t[1] for t in trechos_cima), max(t[1] for t in trechos_baixo))

            def na_zona(x, xz=xz):
                return x >= xz - 1.0
        else:
            xz = max(min(t[0] for t in trechos_cima), min(t[0] for t in trechos_baixo))

            def na_zona(x, xz=xz):
                return x <= xz + 1.0
        zs = [sg for sg in segs if na_zona(sg[0][0]) and na_zona(sg[1][0])]
        pts = [q for sg in zs for q in sg]
        if not pts:
            continue
        face = min(q[0] for q in pts) if lado < 0 else max(q[0] for q in pts)
        # o contorno de fora: as quinas no casco da zona (a quina da face de dentro fica dentro dele)
        casco = _casco(pts)
        de_fora = [q for q in quinas if na_zona(q[0]) and any(math.dist(q, c_) < 1.0 for c_ in casco)]
        nz = [q for q in nos if na_zona(q[0])]
        # a altura da ponta: o pilar e o joelho, até 600 mm da face (a ponta do banzo de baixo, mais para
        # dentro, fica na cadeia horizontal)
        perto_face = [q for q in de_fora if abs(q[0] - face) <= 600.0]
        ys_p = [q[1] for q in perto_face] or [q[1] for q in pts]
        base, topo = min(ys_p), max(ys_p)
        ys = sorted(juntar([base, topo] + [q[1] for q in perto_face], cy))
        # degrau de espessura (menos de 60 mm, a quina de um perfil) não é medida de marcar: sai, e
        # a base e o topo ficam
        limpos = [ys[0]]
        for y in ys[1:]:
            if y - limpos[-1] >= 60.0:
                limpos.append(y)
            elif y == ys[-1]:
                limpos[-1] = y if len(limpos) > 1 else limpos[-1]
                if len(limpos) == 1:
                    limpos.append(y)
        ys = limpos
        # o começo reto dos dois banzos (xz) entra: é onde a peça do joelho encontra o banzo de baixo
        xs = juntar([face, xz] + [q[0] for q in de_fora], cx)
        for q in nz:
            if all(abs(q[0] - x) > 30.0 for x in xs):
                xs.append(round(q[0], 1))
        xs = sorted(xs)
        chanfro = None
        melhor = -1.0
        for a_, b_ in zs:
            L = math.dist(a_, b_)
            if L < 60.0:
                continue
            ang = math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0])) % 180.0
            if any(min(abs(ang - g), 180.0 - abs(ang - g)) < 8.0 for g in angs):
                continue
            a2, b2 = sorted((a_, b_))
            mx, my = (a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2
            dist_c = math.hypot(mx - cx, my - cy)
            if dist_c > melhor:
                ux, uy = (b2[0] - a2[0]) / L, (b2[1] - a2[1]) / L
                sinal = 1.0 if (-uy) * (mx - cx) + ux * (my - cy) > 0 else -1.0
                chanfro, melhor = (a2, b2, sinal), dist_c
        fora.append({"lado": lado, "face": face, "xs": xs, "ys": ys, "base": base, "topo": topo, "chanfro": chanfro})
    return fora


def _cruzamento(a0, a1, b0, b1):
    """Interseção das retas a0–a1 e b0–b1, ou None se paralelas."""
    r = (a1[0] - a0[0], a1[1] - a0[1])
    s = (b1[0] - b0[0], b1[1] - b0[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((b0[0] - a0[0]) * s[1] - (b0[1] - a0[1]) * s[0]) / den
    return (a0[0] + t * r[0], a0[1] + t * r[1])


#: Parafusos a menos disto (mm) um do outro são da mesma ligação: uma chamada só.
GRUPO_DE_PARAFUSOS = 150.0
#: Mais que isto de ligações e a elevação fica só com a lista do título (chamada demais polui).
MAX_CHAMADAS_PARAFUSOS = 10


def chamadas_de_parafusos(p, doc, instancia, origem, u, v, u0: float, v0: float, esc: float) -> int:
    """Nas elevações dos conjuntos menores (dispositivos, vigas, pilares): uma chamada por
    ligação com os parafusos dela ("4x M12 x 30"). O texto vai para fora, no lado que tiver
    lugar; a que encostaria em outra chamada não sai (a lista no título continua). A
    tesoura fica sem: os parafusos dela são os dos suportes de terça, que estão no detalhe
    das terças. Devolve quantas saíram."""
    pts = []
    for c, nome in parafusos_posicionados(doc, instancia):
        rel = _sub(c, origem)
        pts.append(((_dot(rel, u) - u0, _dot(rel, v) - v0), nome))
    if not pts:
        return 0
    grupos: List[list] = []
    for q, nome in sorted(pts, key=lambda t: (t[0][0], t[0][1])):
        for g in grupos:
            if any(math.hypot(q[0] - r[0][0], q[1] - r[0][1]) <= GRUPO_DE_PARAFUSOS for r in g):
                g.append((q, nome))
                break
        else:
            grupos.append([(q, nome)])
    if len(grupos) > MAX_CHAMADAS_PARAFUSOS:
        return 0
    xs = [x for x, _ in p.pontos] or [0.0]
    ys = [y for _, y in p.pontos] or [0.0]
    cx = (min(xs) + max(xs)) / 2 - p.dx
    cy = (min(ys) + max(ys)) / 2 - p.dy
    ocupado: List[Tuple[float, float, float, float]] = []
    feitas = 0
    alt = 2.0
    for g in grupos:
        cont = collections.Counter(n for _, n in g)
        txt = " + ".join("%dx %s" % (q, n) for n, q in sorted(cont.items(), key=lambda kv: _ordem_natural(kv[0])))
        gx = sum(q[0] for q, _ in g) / len(g)
        gy = sum(q[1] for q, _ in g) / len(g)
        larg = largura_da_chamada(txt, alt, esc)
        # para fora do conjunto: o lado do centro para o grupo
        sx = 1.0 if gx >= cx else -1.0
        sy = 1.0 if gy >= cy else -1.0
        for k in (1.0, 1.8, 2.6):
            for fx, fy in ((sx, sy), (sx, -sy), (-sx, sy)):
                xt, yt = gx + fx * 8.0 * esc * k, gy + fy * 8.0 * esc * k
                caixa = (min(xt, xt + fx * larg), yt - 1.0 * esc, max(xt, xt + fx * larg), yt + (alt + 1.0) * esc)
                if any(_sobrepoe(caixa, o, 1.0 * esc) for o in ocupado):
                    continue
                p.chamada(gx, gy, xt, yt, txt, alt)
                ocupado.append(caixa)
                feitas += 1
                break
            else:
                continue
            break
    return feitas


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
            # peça já quebrada em retas no 3D (Cantos redondos): os nós são as quinas das
            # linhas dela — a emenda entra neles como no chanfro desenhado
            ids_quebradas = {e.id for e in instancia if e.id in ids_conformadas and (e.atributos or {}).get("quebras")}
            if ids_quebradas:
                _nos_das_quebras(novas, ids_quebradas)
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
    # cada barra só com as bordas de fora do perfil (sem a linha da espessura colada na borda)
    _so_bordas_externas(desenho, [desenho.entidades[k] for k in desenho.entidades if k not in antes],
                        {e.id for e in instancia if not _tipo_ifc(e).startswith("IfcPlate")}, camada_de)
    # extremos reais em (u, v) do que foi desenhado: canto inferior esquerdo = (dx, dy)
    us = [_dot(_sub(p, origem), u) for e in instancia for p in e.vertices]
    vs = [_dot(_sub(p, origem), v) for e in instancia for p in e.vertices]
    u0, v0 = min(us), min(vs)
    # na treliça, a alma pela linha de trabalho: montante no eixo, diagonal de nó a nó
    segs_bz, quinas_bz, nos_alma = [], [], []
    contorno = set()
    if any(c_ == "BANZOS" for c_ in camada_de.values()):
        alma = {}
        for e in instancia:
            if camada_de.get(e.id) not in ("MONTANTES", "DIAGONAIS") or _tipo_ifc(e).startswith("IfcPlate"):
                continue
            eixo = _eixo_da_peca(e)
            if eixo:
                alma[e.id] = tuple((_dot(_sub(q, origem), u) - u0 + dx, _dot(_sub(q, origem), v) - v0 + dy) for q in eixo)
        segs_bz, quinas_bz = _contorno_dos_banzos(desenho, marca)
        apoios_bz = []
        for e in instancia:
            if camada_de.get(e.id) != "BANZOS":
                continue
            eixo = _eixo_da_peca(e)
            if eixo:
                ab = tuple((_dot(_sub(q, origem), u) - u0 + dx, _dot(_sub(q, origem), v) - v0 + dy) for q in eixo)
                if math.dist(*ab) > 0.25 * larg:            # o banzo reto (a peça dobrada do joelho não tem eixo reto)
                    apoios_bz.append(ab)
        # ficam com o contorno (peças de banzo, não da alma): a barra na continuação de um banzo (a
        # horizontal que leva o banzo de baixo até o pilar do joelho) e o montante que fecha a
        # meia-tesoura na cumeeira (as pontas dos dois banzos chegam nas pontas dele)
        contorno = _alma_com_contorno(instancia, alma, apoios_bz, camada_de)
        for k in contorno:
            apoios_bz.append(alma.pop(k))                  # as outras barras ainda encaixam no eixo dela
        # o montante com contorno (o de fechamento da cumeeira, a descida do banzo no joelho) fica
        # na frente: o banzo e a barra com contorno que entram nele param na face dele
        _esconder_atras_dos_montantes(desenho, [desenho.entidades[k] for k in desenho.entidades if k not in antes],
                                      {k for k in contorno if camada_de.get(k) == "MONTANTES"},
                                      {e.id for e in instancia if camada_de.get(e.id) == "BANZOS"} | set(contorno))
        apoios_bz += _eixos_das_faces(segs_bz)
        nos_alma = _alma_em_eixo(desenho, [desenho.entidades[k] for k in desenho.entidades if k not in antes], alma, camada_de,
                                 quinas=quinas_bz, apoios=apoios_bz)
    atr = {"conjunto": marca, "detalhe": "conjunto"}
    if nome:
        atr["nome"] = nome                      # o grupo do conjunto no DXF leva o nome de produção
    if segs_bz:
        # as terças em corte, onde cruzam o plano da tesoura sobre o banzo de cima (como o corte das
        # tesouras do projetista): a posição e o lado das abas se leem no próprio desenho
        tercas, telhas, extras = _cortes_das_tercas(doc, instancia, origem, u, v, w, u0, v0, segs_bz, dx, dy)
        for id_t, nome_t, segs_t in tercas:
            # cada seção é uma peça só no CAD (o clique pega ela inteira — pedido do usuário, 28/09):
            # "corte" é a terça de onde ela veio; não é "origem", que o Aplicar peças ao 3D lê
            for a_, b_ in segs_t:
                desenho.add(Linha(camada="TERCAS", a=(round(a_[0], 2), round(a_[1], 2)), b=(round(b_[0], 2), round(b_[1], 2)),
                                  atributos=dict(atr, terca_em_corte=True, corte=id_t, nome_corte=nome_t)))
        for poli in telhas:
            # só o contorno de baixo da telha, para ver se ela pega na estrutura
            desenho.add(Polilinha(camada="TELHAS", vertices=[(round(q[0], 2), round(q[1], 2)) for q in poli],
                                  atributos=dict(atr, telha_em_corte=True)))
        for x in extras:
            # o parafuso que prende a telha na terça; o texto do raio da multidobra não vai (pedido do
            # usuário, 28/09: fica só a linha da telha)
            if x[0] == "linha":
                desenho.add(Linha(camada="TELHAS", a=(round(x[1][0], 2), round(x[1][1], 2)), b=(round(x[2][0], 2), round(x[2][1], 2)),
                                  atributos=dict(atr, **{x[3]: True})))
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

    def ys_topo_ok(ts):
        return all(t[3] is not None for t in ts)

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
    # na treliça, a diagonal que chega ao banzo ao lado de um montante é desenhada no nó dele (até
    # 120 mm): a cadeia cota esse mesmo nó
    tol_nos = 120.0 if any(c_ == "BANZOS" for c_ in camada_de.values()) else 60.0
    nos_baixo = fundir(nos_baixo, tol=tol_nos, fixos=(0.0, larg))
    nos_cima = fundir(nos_cima, tol=tol_nos, fixos=(0.0, larg))
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

    # as peças em pé com contorno (a descida do banzo no joelho, o montante da cumeeira): as faces delas,
    # na célula — a cadeia do joelho mede a face da descida, e a do banzo de baixo termina na face do
    # montante da cumeeira, onde o banzo acaba (pedidos do usuário, 28/09)
    pecas_em_pe = []
    for k_ in contorno:
        if camada_de.get(k_) != "MONTANTES":
            continue
        pts_ = [q for e_ in desenho.entidades.values() if isinstance(e_, Linha) and (e_.atributos or {}).get("origem") == k_
                for q in (e_.a, e_.b)]
        if pts_:
            pecas_em_pe.append((min(q[0] for q in pts_) - dx, max(q[0] for q in pts_) - dx,
                                min(q[1] for q in pts_) - dy, max(q[1] for q in pts_) - dy))

    def cadeia_do_banzo(nos, em_cima):
        ts = trechos(em_cima)
        sinal = off if em_cima else -off
        # na treliça a cadeia dos nós sai mesmo apertada: é o que se marca no gabarito
        apertada = not (any(de_cima[id(b)] for b in banzos) and any(not de_cima[id(b)] for b in banzos))
        if len(ts) <= 1:
            reta = ts[0][2] if ts else None
            if reta is None:
                return p.cadeia_h(nos, alt if em_cima else 0.0, sinal, exigir_espaco=apertada)
            return p.cadeia_alinhada(reta, nos, sinal, exigir_espaco=apertada)
        # um trecho por água: os nós dele e as pontas dele, cada cadeia na sua reta
        feita = False
        meio_ts = (ts[0][1] + ts[-1][0]) / 2.0
        for x0, x1, reta, ytopo in ts:
            if not em_cima:
                # o banzo de baixo acaba na face do montante da cumeeira: a cadeia termina ali, não
                # no eixo (o 863 ia até o meio da cumeeira)
                for a_, b_, _y0, _y1 in pecas_em_pe:
                    if abs((a_ + b_) / 2.0 - meio_ts) > 300.0:
                        continue
                    if abs(x1 - meio_ts) < 300.0 and (a_ + b_) / 2.0 < meio_ts:
                        x1 = a_
                    elif abs(x0 - meio_ts) < 300.0 and (a_ + b_) / 2.0 > meio_ts:
                        x0 = b_
            # os nós da água (até 40 mm fora das pontas) e as pontas; nó colado na ponta (a
            # cumeeira tem dois montantes a 70 mm) funde com ela
            pontas = (round(x0, 1), round(x1, 1))
            nos_t = fundir({*pontas} | {x for x in nos if x0 - 40.0 <= x <= x1 + 40.0}, tol=60.0, fixos=pontas)
            if len(nos_t) < 2:
                continue
            feita = (p.cadeia_alinhada(reta, nos_t, sinal, exigir_espaco=apertada) if reta is not None
                     else p.cadeia_h(nos_t, ytopo if em_cima else 0.0, sinal, exigir_espaco=apertada)) or feita
        return feita
    cadeia = len(nos_baixo) > 2 and cadeia_do_banzo(nos_baixo, False)
    # a treliça (banzo em cima e embaixo): as cotas pensadas para o corte e o gabarito — a água
    # inteira ao longo de cada banzo, as pontas (joelho) medidas trecho a trecho, a cumeeira
    trelica = any(de_cima[id(b)] for b in banzos) and any(not de_cima[id(b)] for b in banzos)
    pontas = _pontas_da_trelica(segs_bz, quinas_bz, nos_alma, dx, dy, larg, alt, trechos(True), trechos(False)) if trelica else []
    nivel_baixo = 1 if cadeia else 0
    # as medidas da treliça são as da estrutura: de face a face do contorno dos banzos (a chapa de apoio
    # que passa da face não entra — pedido do usuário, 28/09)
    xs_bz = [q[0] - dx for sg_ in segs_bz for q in sg_] if trelica else []
    face_esq, face_dir = (min(xs_bz), max(xs_bz)) if xs_bz else (0.0, larg)
    if trelica:
        agua = False
        for x0, x1, reta, _yt in trechos(False):
            if reta is not None and x1 - x0 > 300.0:
                agua = p.cadeia_alinhada(reta, [x0, x1], -off * (nivel_baixo + 1), exigir_espaco=False) or agua
        nivel_baixo += 1 if agua else 0
        # as pontas (a chapa de apoio, a face, as quinas e os nós do joelho) numa cadeia só, de ponta a
        # ponta, com a cumeeira no meio: fecha com a total — nenhuma medida solta
        if any(len(pt["xs"]) > 1 for pt in pontas):
            xs_h = {round(face_esq, 1), round(face_dir, 1)} | {x for pt in pontas for x in pt["xs"]
                                                                if face_esq - 1.0 <= x <= face_dir + 1.0}
            ts_c = trechos(True)
            fixos = {round(face_esq, 1), round(face_dir, 1)}
            # a descida do banzo no joelho: as faces dela no lugar dos nós em cima dela (o eixo do B.14,
            # o nó das diagonais a 30 mm da face — que parecia a borda da cantoneira, pedido do usuário)
            for a_, b_, _y0, _y1 in pecas_em_pe:
                if min((a_ + b_) / 2.0 - face_esq, face_dir - (a_ + b_) / 2.0) > 0.25 * (face_dir - face_esq):
                    continue
                xs_h = {x for x in xs_h if not (a_ - 40.0 <= x <= b_ + 40.0)} | {round(a_, 1), round(b_, 1)}
            if len(ts_c) > 1:
                xs_h.add(round(ts_c[0][1], 1))
                xs_h.add(round(ts_c[1][0], 1))          # a folga entre as duas metades
                fixos |= {round(ts_c[0][1], 1), round(ts_c[1][0], 1)}
            # a largura do perfil não se cota na cadeia (os 50 do pilar, os 55 da descida do banzo —
            # pedido do usuário, 28/09): de dois pontos a menos de 60 mm fica a face de fora da peça
            # (a ponta da treliça) ou o que está mais para o meio; o outro vira a medida de dentro
            xs_c, tirados = _sem_larguras(sorted(xs_h), fixos, (face_esq + face_dir) / 2.0)
            if p.cadeia_h(xs_c, 0.0, -off * (nivel_baixo + 1), exigir_espaco=False):
                nivel_baixo += 1
            # o joelho: o vão livre por dentro (da face de dentro do pilar à da descida do banzo) e a
            # largura toda por fora (da face da ponta à face de dentro da descida)
            joelho = False
            for lado_, face_ in ((1, face_esq), (-1, face_dir)):
                dentro_ = sorted((x for x in tirados if abs(x - face_) < 0.25 * (face_dir - face_esq)),
                                 key=lambda x: abs(x - face_))
                if len(dentro_) < 2:
                    continue
                fora_ = [x for x in xs_c if abs(x - face_) < 0.25 * (face_dir - face_esq) and x != round(face_, 1)
                         and (x - dentro_[1]) * lado_ > 0 and abs(x - dentro_[1]) < 60.0]
                p.cota_h(min(dentro_[0], dentro_[1]), max(dentro_[0], dentro_[1]), 0, -off * (nivel_baixo + 1))
                if fora_:
                    p.cota_h(min(face_, fora_[0]), max(face_, fora_[0]), 0, -off * (nivel_baixo + 2))
                joelho = True
            if joelho:
                nivel_baixo += 2
    p.cota_h(face_esq, face_dir, 0, -off * (nivel_baixo + 1))
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
    n_topo = (1 if cadeia_cima else 0) + (1 if cadeia_suportes else 0)
    if trelica:
        # a água inteira ao longo do banzo de cima, por fora das cadeias de nós e de suportes
        agua = False
        for x0, x1, reta, ytopo in trechos(True):
            if x1 - x0 > 300.0:
                agua = (p.cadeia_alinhada(reta, [x0, x1], off * (n_topo + 1), exigir_espaco=False) if reta is not None
                        else p.cadeia_h([x0, x1], ytopo, off * (n_topo + 1), exigir_espaco=False)) or agua
        n_topo += 1 if agua else 0
        ts_meia = trechos(True)
        if len(ts_meia) > 1 and ys_topo_ok(ts_meia):
            # tesoura montada: cada metade na horizontal, da face da ponta ao meio da cumeeira (como o
            # 7200 do projeto), por cima das cotas das águas
            meio_c = (ts_meia[0][1] + ts_meia[1][0]) / 2.0
            y_ap = max(yt for _a, _b, _r, yt in ts_meia)
            p.cota_h(face_esq, meio_c, y_ap, off * (n_topo + 1.5))
            p.cota_h(meio_c, face_dir, y_ap, off * (n_topo + 1.5))
            n_topo += 2
        # cada ponta: as alturas trecho a trecho (onde o banzo dobra, a base do joelho, o topo) e a
        # altura dela por fora; o chanfro do joelho pelo comprimento, na própria inclinação
        # cada ponta: as alturas das quinas e dos nós (a face de fora como referência, as chamadas saem
        # da face da peça, não da chapa de apoio) e a altura da ponta por fora
        maior = 0.0
        ponta_dir = None                                  # (x da face, deslocamento da cota mais de fora)
        for pt in pontas:
            sg = 1.0 if pt["lado"] > 0 else -1.0
            desl0 = abs((larg if pt["lado"] > 0 else 0.0) - pt["face"]) / esc     # a chapa além da face
            nv = 1 if len(pt["ys"]) > 2 and p.cadeia_v(pt["ys"], pt["face"], sg * (off + desl0), exigir_espaco=False) else 0
            p.cota_v(pt["ys"][0], pt["ys"][-1], pt["face"], sg * (off * (nv + 1) + desl0))
            if pt["lado"] > 0:
                ponta_dir = (pt["face"], off * (nv + 1) + desl0)
            maior = max(maior, pt["ys"][-1] - pt["ys"][0])
            if pt["chanfro"]:
                a_, b_, lado_ = pt["chanfro"]
                p.cadeia_alinhada((a_, b_), [a_[0], b_[0]], lado_ * off, exigir_espaco=False)
        # a altura toda pelo contorno dos banzos (da base ao ápice) — a da caixa da célula ia da chapa de
        # apoio à ponta do suporte de terça
        ys_bz = [q[1] - dy for sg_ in segs_bz for q in sg_]
        ts_cima = trechos(True)
        if ys_bz:
            base_bz, apice = min(ys_bz), max(ys_bz)
            # a descida do banzo de baixo no joelho (a peça em pé com o contorno): a altura dela, do lado
            # de dentro (pedido do usuário, 28/09) — é a base da flecha
            topo_descida = None
            for k_ in contorno:
                if camada_de.get(k_) != "MONTANTES":
                    continue
                pts_ = [q for e_ in desenho.entidades.values() if isinstance(e_, Linha) and (e_.atributos or {}).get("origem") == k_
                        for q in (e_.a, e_.b)]
                if not pts_:
                    continue
                xs_m = [q[0] - dx for q in pts_]
                ys_m = [q[1] - dy for q in pts_]
                xm = (min(xs_m) + max(xs_m)) / 2.0
                if len(ts_cima) > 1 and ts_cima[0][1] - 300.0 <= xm <= ts_cima[1][0] + 300.0:
                    continue                                  # o montante da cumeeira tem a cota dele
                if min(xm - face_esq, face_dir - xm) > 0.25 * (face_dir - face_esq):
                    continue
                para_dentro = 1.0 if xm < (face_esq + face_dir) / 2.0 else -1.0
                x_ = max(xs_m) if para_dentro > 0 else min(xs_m)
                p.cota_v(min(ys_m), max(ys_m), x_, para_dentro * off * 0.6)
                topo_descida = max(ys_m) if topo_descida is None else min(topo_descida, max(ys_m))
            if len(ts_cima) > 1:
                # tesoura montada: a flecha (da descida do banzo ao ápice) e a altura toda escritas como no
                # projeto, na ponta da direita por fora das alturas do joelho (pedido do usuário, 28/09 —
                # na cumeeira ficavam em cima do montante); sem a ponta, junto da cumeeira
                x_t, d_t = ponta_dir if ponta_dir else (ts_cima[1][0], off * -0.4)
                if topo_descida is not None and apice - topo_descida > 100.0:
                    p.cota_v(topo_descida, apice, x_t, d_t + off, texto="FLECHA TOTAL %d" % round(apice - topo_descida))
                    d_t += off
                p.cota_v(base_bz, apice, x_t, d_t + off, texto="ALTURA TOTAL %d" % round(apice - base_bz))
            elif apice - base_bz - maior > 5.0:
                p.cota_v(base_bz, apice, larg, off * 3 + abs(larg - max(pt["face"] for pt in pontas)) / esc if pontas else off * 3)
        ts_b = trechos(False)
        if len(ts_cima) > 1 and len(ts_b) > 1:
            xa_, xb_ = ts_cima[0][1], ts_cima[1][0]
            esq_ = [x for x in nos_baixo if x < xa_ - 60.0]
            dir_ = [x for x in nos_baixo if x > xb_ + 60.0]
            if esq_ and dir_:
                # o último nó de cada lado, as faces das metades e a folga entre elas, na horizontal, logo
                # abaixo do banzo de baixo na cumeeira (pedido do usuário, 28/09)
                xs_r = [max(esq_), xa_, xb_, min(dir_)]
                y_r = min(yb for _a, _b, _r, yb in ts_b if yb is not None) if all(t[3] is not None for t in ts_b) else 0.0
                p.cadeia_h(xs_r, y_r, -off * 2.0, exigir_espaco=False)
        if len(ts_cima) > 1 and nos_alma:
            # tesoura montada: a altura do montante da cumeeira, curta e junto dele
            xr = ts_cima[0][1]
            mont = [e for e in desenho.entidades.values() if isinstance(e, Linha) and e.camada == "MONTANTES"
                    and (e.atributos or {}).get("eixo") and (e.atributos or {}).get("conjunto") == marca]
            if mont:
                m_ = min(mont, key=lambda e: abs((e.a[0] + e.b[0]) / 2 - dx - xr))
                if abs((m_.a[0] + m_.b[0]) / 2 - dx - xr) < 300.0:
                    p.cota_v(m_.a[1] - dy, m_.b[1] - dy, (m_.a[0] + m_.b[0]) / 2 - dx, -off * 0.6)
    else:
        cadeia = len(alturas) > 2 and p.cadeia_v(alturas, larg, off)
        p.cota_v(0, alt, larg, off2 if cadeia else off)
    _rotular_barras(p, rotulos, esc)
    if tipo != "tesoura":
        chamadas_de_parafusos(p, doc, instancia, origem, u, v, u0, v0, esc)
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
    y = alt + (off * n_topo + 12.0) * esc           # por cima dos níveis de cota do banzo de cima

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
        # as soltas de ponta roscada no padrão da fábrica: 1 porca + 2 arruelas por ponta (28/09)
        from nucleo2d.detalhe.base import pontas_roscadas, PORCAS_POR_PONTA, ARRUELAS_POR_PONTA, _fixadores
        pontas, usados = pontas_roscadas(instancia, _fixadores(doc))
        por_bitola = collections.Counter(pt["bitola"] or "" for pt in pontas)
        for bit, n_ in sorted(por_bitola.items()):
            b_ = " Ø%s" % bit if bit else ""
            itens_p.append("%dx porca sext.%s + %dx arruela lisa%s" % (n_ * PORCAS_POR_PONTA, b_, n_ * ARRUELAS_POR_PONTA, b_))
        porcas -= min(porcas, len(usados))
        if porcas:
            itens_p.append("%dx porca/arruela" % porcas)
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


def _bitola(perfil: str) -> str:
    """A bitola em polegadas escrita no perfil da barra redonda: "FE RED 3/8''" → '3/8"'."""
    m = re.search(r"(\d+(?:[ .\-]\d+/\d+|/\d+)?)\s*(?:''|\"|”)", perfil)
    return (m.group(1).strip() + '"') if m else ""


def _roscas(doc: Documento, inst: Sequence[Solido], origem, u, v, u0: float, v0: float, comprimento: float) -> List[tuple]:
    """As roscas do conjunto na vista (u, v): cada porca (ou arruela) solta perto da instância vai
    para a peça redonda em que ela está — o tirante, o gancho da agulha (G.1), a barra roscada do
    esticador — e a rosca é a ponta dessa peça mais perto da porca, `comprimento` mm (a barra
    roscada, inteira). Devolve [(peça, u0, u1, v do eixo, diâmetro)], uma por ponta roscada."""
    from nucleo2d.detalhe.base import _fixadores, _so_parafusos, _nome_do_parafuso, _autovetores
    from nucleo.perfis_fabrica import polegadas_mm
    redondas = []
    for e in inst:
        perfil = str(_marcas(e).get("perfil") or e.nome or "")
        if not _eh_redonda_perfil(perfil) or not getattr(e, "vertices", None):
            continue
        pu = [_dot(_sub(q, origem), u) - u0 for q in e.vertices]
        pv = [_dot(_sub(q, origem), v) - v0 for q in e.vertices]
        d = polegadas_mm(_bitola(perfil)) or 10.0
        redondas.append((e, pu, pv, d, "ROSCAD" in perfil.upper()))
    if not redondas:
        return []
    caixas = [_caixa(e) for e in inst if getattr(e, "vertices", None)]
    minimo = [min(cx[i][0] for cx in caixas) - 200.0 for i in range(3)]
    maximo = [max(cx[i][1] for cx in caixas) + 200.0 for i in range(3)]
    fora, feitas, porcas_da = [], set(), {}
    for f in _so_parafusos(_fixadores(doc)):
        cc = tuple(sum(q[i] for q in f.vertices) / len(f.vertices) for i in range(3))
        if not all(minimo[i] <= cc[i] <= maximo[i] for i in range(3)):
            continue
        # só a porca e a arruela soltas (o parafuso de verdade — o M16 da castanha — traz a dele),
        # pela forma, como a legenda do conjunto as conta
        ext = []
        _, pca = _autovetores(f.vertices)
        for ax in pca:
            ts = [_dot(_sub(q, cc), ax) for q in f.vertices]
            ext.append(max(ts) - min(ts))
        _nome, pela_porca = _nome_do_parafuso(f, ext)
        if not (pela_porca or ext[0] <= 1.5 * ext[1]):
            continue
        fu = _dot(_sub(cc, origem), u) - u0
        fv = _dot(_sub(cc, origem), v) - v0
        # a peça redonda que passa pela porca: a que a contém no comprimento (a porca da agulha fica
        # além da ponta do ferro, no gancho; a do contravento, na barra roscada do esticador, não no
        # ferro liso soldado nela) e no eixo; só sem nenhuma, a de ponta até 40 mm dela
        no_eixo = [r for r in redondas if min(r[2]) - 15.0 <= fv <= max(r[2]) + 15.0]
        cand = ([r for r in no_eixo if min(r[1]) <= fu <= max(r[1])]
                or [r for r in no_eixo if min(r[1]) - 40.0 <= fu <= max(r[1]) + 40.0])
        if not cand:
            continue
        e, pu, pv, d, roscada = min(cand, key=lambda r: min(abs(fu - min(r[1])), abs(fu - max(r[1]))))
        a_, b_ = min(pu), max(pu)
        if roscada:
            x_a, x_b = a_, b_
        elif fu - a_ <= b_ - fu:
            x_a, x_b = a_, a_ + min(comprimento, 0.9 * (b_ - a_))
        else:
            x_a, x_b = b_ - min(comprimento, 0.9 * (b_ - a_)), b_
        # a porca e a arruela da mesma ponta contam uma vez; na barra roscada, cada grupo de porcas
        # (as duas pontas do esticador) é uma ponta roscada, com a rosca desenhada uma vez só
        if roscada:
            # as porcas a até 40 mm umas das outras são da mesma ponta
            ja = porcas_da.setdefault(e.id, [])
            if any(abs(fu - x) <= 40.0 for x in ja):
                continue
            ja.append(fu)
        else:
            chave = (e.id, round(x_a))
            if chave in feitas:
                continue
            feitas.add(chave)
        if roscada and any(r[0] is e for r in fora):
            fora.append((e, None, None, None, d))     # conta a ponta, sem desenhar de novo
            continue
        # o eixo na ponta roscada: os vértices do anel da ponta (o gancho da outra ponta espalha)
        ponta = x_a if abs(fu - x_a) <= abs(fu - x_b) else x_b
        anel = [q for q_u, q in zip(pu, pv) if abs(q_u - ponta) <= 15.0]
        v_c = (min(anel) + max(anel)) / 2 if anel and max(anel) - min(anel) <= 2.5 * d else fv
        fora.append((e, x_a, x_b, v_c, d))
    return fora


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
    """Detalhe típico dos conjuntos que só diferem no comprimento da barra principal (mesmas
    peças de ponta): contraventamentos e agulhas. A elevação do mais comprido com o nome das
    peças de ponta embaixo e, no estilo do projeto do Posto (pedido do usuário, 28/09), as cotas
    empilhadas debaixo dela, todas do tamanho da barra desenhada, com o nome, o comprimento e a
    quantidade no meio — "CV.3 COMP=5150mm – 02X"; a rosca desenhada e cotada nas pontas da
    barra que têm porca. `membros` = [(rotulo do grupo, instância, nº de instâncias)]."""
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
    # a rosca nas pontas da barra que têm porca (o fixador perto da ponta, no eixo): as linhas
    # do fundo da rosca e os traços dos filetes ao longo de ROSCA_GANCHO, "ROSCA" embaixo e a
    # cota do comprimento em cima, como o Posto desenha (pedido do usuário, 28/09)
    linhas_lado = {False: 0, True: 0}
    n_roscas = 0
    for r_ in extremos_pecas:
        lado_ = (r_[0] + r_[1]) / 2 > meio
        linhas_lado[lado_] = max(linhas_lado[lado_], r_[2])
    from nucleo2d.detalhe.celulas import ROSCA_GANCHO
    bitola_rosca = ""
    for peca_r, x_a, x_b, v_c, d_b in _roscas(doc, inst, origem, u, v, u0, v0, ROSCA_GANCHO):
        if x_a is None:
            n_roscas += 1                             # outra ponta da mesma barra roscada
            continue
        for s_ in (-1.0, 1.0):
            p.linha(x_a, v_c + s_ * d_b * 0.32, x_b, v_c + s_ * d_b * 0.32, "ACO-FINO")
        passo_f = max(d_b * 0.6, 1.2 * esc)
        x_f = x_a + passo_f / 2
        while x_f < x_b:
            p.linha(x_f - d_b * 0.25, v_c - d_b / 2, x_f + d_b * 0.25, v_c + d_b / 2, "ACO-FINO")
            x_f += passo_f
        p.cota_h(x_a, x_b, v_c + d_b / 2, 4.0)
        n_roscas += 1
        lado_ = (x_a + x_b) / 2 > meio
        linhas_lado[lado_] += 1
        p.texto((x_a + x_b) / 2, -(3.0 + 3.0 * (linhas_lado[lado_] - 1)) * esc - h_nome, "ROSCA", h_nome, "TEXTO", alinhamento="centro")
        bitola_rosca = bitola_rosca or _bitola(str(_marcas(peca_r).get("perfil") or peca_r.nome or ""))
    # as cotas empilhadas debaixo da peça, uma por conjunto, todas do tamanho da barra desenhada
    # (o comprimento de cada uma vai no texto, no meio): "CV.1 COMP=4258mm – 08X", como o Posto
    y_base = -(3.0 + 3.0 * max(linhas_lado.values() or [0]) + 4.0) * esc - h_nome
    passo_c = 6.0
    for i, (rot, inst_m, n_inst) in enumerate(membros):
        tir_m = _tirante_principal(inst_m) or _barra_mais_longa(inst_m)
        marca_m = (fundidas.get(str(_marcas(tir_m).get("posicao") or tir_m.nome), str(_marcas(tir_m).get("posicao") or tir_m.nome))
                   if tir_m is not None else None)
        comp_m = (comprimentos.get(marca_m) if marca_m else None) or (
            _comprimento_na_vista(tir_m, inst_m) if tir_m is not None else _extensao_do_conjunto(inst_m)[0])
        nome_m = nomes_conj.get(rot, rot)
        y_c = y_base - passo_c * i * esc
        txt = "%s COMP=%dmm – %02dX" % (nome_m, round(comp_m), n_inst)
        p.cota_h(round(t0), round(t1), y_c, 0.0, texto=txt)
        for x_ in (round(t0), round(t1)):
            p.linha(x_, y_c - 1.5 * esc, x_, y_c + 1.5 * esc, "COTA")
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
    # a barra de cada um (nome e perfil); o comprimento de corte está na cota empilhada
    barras_ = collections.OrderedDict()
    for rot, inst_m, n_inst in membros:
        tir = _tirante_principal(inst_m)
        if tir is None:
            continue
        marca_t = fundidas.get(str(_marcas(tir).get("posicao") or tir.nome), str(_marcas(tir).get("posicao") or tir.nome))
        barras_.setdefault(str(_marcas(tir).get("perfil") or tir.nome or ""), []).append(nomes.get(marca_t) or marca_t)
    for perfil_b, nomes_b in barras_.items():
        linhas.append("Barra %s: %s" % (perfil_b, ", ".join(nomes_b)))
    # o padrão da fábrica na ponta roscada: 1 porca e 2 arruelas (pedido do usuário, 28/09) — não
    # o que o modelo tem (o projetista põe porcas e arruelas soltas, lidas pela forma)
    if n_roscas:
        bitola = (" Ø%s" % bitola_rosca) if bitola_rosca else ""
        linhas.append("Por ponta roscada: 1 porca sextavada%s + 2 arruelas lisas%s (%d ponta%s por unidade)"
                      % (bitola, bitola, n_roscas, "s" if n_roscas > 1 else ""))
    pecas_ponta = collections.Counter(nome_de(_marcas(e).get("posicao") or e.nome) for e in inst if e is not tirante)
    if pecas_ponta:
        linhas.append("Pecas de ponta (por unidade): "
                      + ", ".join("%s x%d" % (k, q) for k, q in sorted(pecas_ponta.items(), key=lambda kv: _ordem_natural(kv[0]))))
    y = alt + (off + 4.0) * esc
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


def _eixos_do_modelo(doc: Documento, eixos: Optional[dict], nomes_producao: Optional[dict]) -> Optional[dict]:
    """Os eixos gravados no projeto, ou identificados do modelo agora (None se não der)."""
    from nucleo3d import eixos as _eixos
    pronto = _eixos.de_dict(eixos)
    if pronto:
        return pronto
    try:
        return _eixos.identificar_eixos(doc, nomes_producao)
    except Exception:                                           # noqa: BLE001 — planta sai sem eixos
        return None


def _desenhar_eixos(p: "_Papel", eixos: dict, u, v, u0: float, v0: float, esc: float,
                    largura: float, altura: float) -> None:
    """Os eixos na planta: linha em EIXO com a bolinha e o nome nas duas pontas, e a cadeia
    de cotas entre eixos (com a total) fora das bolinhas. `u`, `v`: eixos 3D da vista;
    `u0`, `v0`: a origem do papel nessas direções (o mesmo que as peças usam)."""
    from nucleo3d.eixos import segmentos
    r = 4.5 * esc                                     # raio da bolinha (mm de modelo)
    h = 3.5 * esc                                     # o nome do eixo maior que o texto corrente (pedido do usuário)
    xs_letras, ys_numeros = [], []
    horizontais_sao_numeros = None
    for seg in segmentos(eixos):
        a = (_dot(seg["a"], u) - u0, _dot(seg["a"], v) - v0)
        b = (_dot(seg["b"], u) - u0, _dot(seg["b"], v) - v0)
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            continue
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        # a linha vai de bolinha a bolinha; a bolinha fica encostada na ponta da linha
        p.linha(a[0], a[1], b[0], b[1], camada="EIXO")
        for ponta, sinal in ((a, -1.0), (b, 1.0)):
            cx, cy = ponta[0] + sinal * d[0] * r, ponta[1] + sinal * d[1] * r
            p.circulo(cx, cy, r, camada="EIXO")
            p.texto(cx, cy - 0.35 * h, seg["nome"], h, "EIXO", alinhamento="centro")
        horizontal = abs(d[0]) >= abs(d[1])
        if seg["tipo"] == "numero":
            if horizontais_sao_numeros is None:
                horizontais_sao_numeros = horizontal
            ys_numeros.append(a[1] if horizontal else a[0])
        else:
            xs_letras.append(a[0] if not horizontal else a[1])
    # cadeias de cotas: as posições dos eixos de um tipo ao longo da direção do outro
    if horizontais_sao_numeros is None:
        return
    if horizontais_sao_numeros:
        # números em linhas horizontais (posições em y), letras em verticais (posições em x)
        if len(xs_letras) >= 2:
            y_topo = altura + 2.0 * r + 8.0 * esc
            p.cadeia_h(xs_letras, y_topo, 4.0, exigir_espaco=False)
            p.cota_h(min(xs_letras), max(xs_letras), y_topo, 12.0)
        if len(ys_numeros) >= 2:
            x_esq = -(2.0 * r + 8.0 * esc)
            p.cadeia_v(ys_numeros, x_esq, -4.0, exigir_espaco=False)
            p.cota_v(min(ys_numeros), max(ys_numeros), x_esq, -12.0)
    else:
        if len(ys_numeros) >= 2:
            y_topo = altura + 2.0 * r + 8.0 * esc
            p.cadeia_h(ys_numeros, y_topo, 4.0, exigir_espaco=False)
            p.cota_h(min(ys_numeros), max(ys_numeros), y_topo, 12.0)
        if len(xs_letras) >= 2:
            x_esq = -(2.0 * r + 8.0 * esc)
            p.cadeia_v(xs_letras, x_esq, -4.0, exigir_espaco=False)
            p.cota_v(min(xs_letras), max(xs_letras), x_esq, -12.0)


def desenho_de_chumbacao(doc: Documento, pecas: Sequence[Solido], nomes_producao: Optional[dict],
                         titulo: str = "Detalhamento – chumbação", eixos: Optional[dict] = None,
                         nomes: Optional[Dict[str, str]] = None) -> Desenho:
    """Planta de chumbação: os chumbadores e as chapas de base vistos de cima, no lugar em
    que ficam, com a marca de cada um, os eixos com as bolinhas e as cotas entre eixos —
    o que a obra precisa para posicionar os chumbadores no concreto."""
    from nucleo2d.pranchas import escala_normalizada
    tipos = (nomes_producao or {}).get("tipos") or {}
    chumb = [e for e in pecas if tipos.get(str(_marcas(e).get("posicao") or "")) == "chumbador"]
    ex = _eixos_do_modelo(doc, eixos, nomes_producao)
    so_chapas = not chumb            # sem chumbador no modelo: o que se desenha são as chapas de base
    if not chumb:
        # sem chumbador reconhecido: as chapas horizontais junto do nível de base
        z_base = float(ex["z_base"]) if ex else min(v[2] for e in pecas for v in e.vertices)
        chumb = []
        for e in pecas:
            zs = [v[2] for v in e.vertices]
            xs = [v[0] for v in e.vertices]
            ys = [v[1] for v in e.vertices]
            # chapa até 3" de espessura: a placa de base de pilar engastado passa de 1" (a do
            # galpão lançado sai com 2"); o resto (barra deitada perto da base) até 25 mm, como antes
            chapa = _tipo_ifc(e).startswith("IfcPlate") or type(getattr(e, "parametrica", None)).__name__ == "Chapa"
            if max(zs) - min(zs) <= (80.0 if chapa else 25.0) and max(max(xs) - min(xs), max(ys) - min(ys)) >= 80.0                     and min(zs) <= z_base + 300.0:
                chumb.append(e)
    if not chumb:
        raise ErroDeDados("sem chumbadores nem chapas de base no modelo.")
    # as chapas que estão nos chumbadores (a chapa de base): perto em planta e em altura
    centros = []
    for e in chumb:
        vs = e.vertices
        centros.append((sum(v[0] for v in vs) / len(vs), sum(v[1] for v in vs) / len(vs), sum(v[2] for v in vs) / len(vs)))
    ids_ch = {e.id for e in chumb}
    chapas = []
    for e in pecas:
        if e.id in ids_ch or tipos.get(str(_marcas(e).get("posicao") or "")) not in ("chapa", "castanha", "suporte_terca", None):
            continue
        zs = [v[2] for v in e.vertices]
        if max(zs) - min(zs) > 25.0:
            continue
        cx = sum(v[0] for v in e.vertices) / len(e.vertices)
        cy = sum(v[1] for v in e.vertices) / len(e.vertices)
        if any(math.hypot(cx - c[0], cy - c[1]) <= 400.0 and abs(min(zs) - c[2]) <= 500.0 for c in centros):
            chapas.append(e)
    itens = chumb + chapas
    todos = [v for e in itens for v in e.vertices]
    if ex:
        # a planta abrange os eixos inteiros (com a folga das bolinhas)
        from nucleo3d.eixos import segmentos
        todos = todos + [q for s in segmentos(ex) for q in (s["a"], s["b"])]
    minimo = [min(v[i] for v in todos) for i in range(3)]
    maximo = [max(v[i] for v in todos) for i in range(3)]
    ext = [maximo[i] - minimo[i] for i in range(3)]
    comprido_em_y = ext[1] > ext[0]
    if comprido_em_y:
        u, v, w = (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, -1.0)
    else:
        u, v, w = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)
    us = [_dot(q, u) for q in todos]
    vs_ = [_dot(q, v) for q in todos]
    u0, v0 = min(us), min(vs_)
    larg_v, alt_v = max(us) - u0, max(vs_) - v0
    esc = escala_normalizada(max(larg_v / 700.0, alt_v / 450.0, 1.0))
    d = Desenho(nome=titulo, escala=esc)
    h_txt = 2.5 * esc
    atr_base = {"detalhe": "chumbacao"}
    p = _Papel(d, dict(atr_base, vista="PLANTA DE CHUMBAÇÃO"), 0.0, 0.0)
    _registrar_camadas_de_pecas(d)
    rotulos = []
    for e in itens:
        pts = [(_dot(q, u) - u0, _dot(q, v) - v0) for q in e.vertices]
        casco = _casco(pts)
        if len(casco) < 3:
            continue
        m = _marcas(e)
        atr = dict(atr_base, vista="PLANTA DE CHUMBAÇÃO", origem=e.id, nome=e.nome or "")
        if m.get("posicao"):
            atr["posicao"] = str(m["posicao"])
        if m.get("conjunto"):
            atr["conjunto"] = str(m["conjunto"])
        pp = _Papel(d, atr, 0.0, 0.0)
        eh_chumb = e.id in ids_ch
        pp.polilinha(casco, fechada=True, camada="TIRANTES" if (eh_chumb and not so_chapas) else "CHAPAS")
        # os furos da chapa de base paramétrica são onde os chumbadores passam: é o que a
        # obra marca no concreto (a chapa do IFC traz o chumbador como peça própria)
        par = getattr(e, "parametrica", None)
        if par is not None and getattr(par, "furos", None) and hasattr(par, "eixo_x"):
            for f in par.furos:
                P = tuple(par.origem[i] + par.eixo_x[i] * float(f.get("x", 0.0)) + par.eixo_y[i] * float(f.get("y", 0.0))
                          for i in range(3))
                pp.circulo(_dot(P, u) - u0, _dot(P, v) - v0, float(f.get("diametro", 20.0)) / 2.0, camada="FURO")
        p.pontos.extend(pp.pontos)
        if eh_chumb:
            marca = str(m.get("posicao") or e.nome or "")
            # o nome começa na borda direita da peça (do centro, encostava na chapa estreita)
            cx = max(q[0] for q in pts)
            cy = sum(q[1] for q in pts) / len(pts)
            rotulos.append(((nomes or {}).get(marca) or marca, cx, cy))
    postos: List[Tuple[str, float, float]] = []
    for rotulo, cx, cy in sorted(rotulos, key=lambda r: (r[2], r[1])):
        if any(t == rotulo and math.hypot(cx - x_, cy - y_) < 8.0 * h_txt for t, x_, y_ in postos):
            continue
        postos.append((rotulo, cx, cy))
        p.texto(cx + 1.5 * esc, cy + 3.0 * esc, rotulo, h_txt, "TEXTO")
    if ex:
        _desenhar_eixos(p, ex, u, v, u0, v0, esc, larg_v, alt_v)
    p.cota_h(0, larg_v, 0, -10.0)
    p.cota_v(0, alt_v, larg_v, 10.0)
    p.texto(0, -(10.0 + 8.0) * esc, "PLANTA DE CHUMBAÇÃO", 3.5 * esc)
    n_chumb, n_chapas = (0, len(chumb) + len(chapas)) if so_chapas else (len(chumb), len(chapas))
    p.texto(0, -(10.0 + 8.0 + 4.5) * esc, "escala 1:%s · %d chumbador(es) e %d chapa(s) de base, vistos de cima, nos eixos da obra"
            % (int(esc) if float(esc).is_integer() else esc, n_chumb, n_chapas)
            + (" (sem chumbador no modelo: os furos das chapas marcam onde eles passam)" if so_chapas else ""), 2.0 * esc)
    ext_c = p.extremos
    d.metadados.setdefault("celulas", []).append([round(t, 1) for t in ext_c])
    d.vistas.append({"origem": [minimo[0], minimo[1], minimo[2]], "normal": list(w), "acima": list(v),
                     "profundidade": None, "cortar": False, "entidades": None, "rotular": True,
                     "nome": "PLANTA DE CHUMBAÇÃO", "tipo": "topo", "pecas_cortadas": 0, "pecas_projetadas": len(itens),
                     "largura": round(larg_v, 1), "altura": round(alt_v, 1), "canto": [0.0, 0.0], "avisos": [],
                     "ref2d": [round(u0 - _dot(minimo, u), 2), round(v0 - _dot(minimo, v), 2)]})
    d.metadados["detalhamento"] = {"grupo": "chumbacao", "posicoes": [], "itens": {}}
    d.metadados["eixos"] = ex
    return d


def desenho_de_localizacao(doc: Documento, pecas: Sequence[Solido], titulo: str = "Detalhamento – localização",
                           ignorar: Sequence[str] = (), nomes: Optional[Dict[str, str]] = None,
                           camadas_pecas: Optional[Dict[str, str]] = None, eixos: Optional[dict] = None,
                           nomes_producao: Optional[dict] = None) -> Desenho:
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
        if tipo == "topo":
            ex = _eixos_do_modelo(doc, eixos, nomes_producao)
            if ex:
                _desenhar_eixos(p, ex, u, v, u0, v0, esc, larg_v, alt_v)
                d.metadados["eixos"] = ex
        p.cota_h(0, larg_v, 0, -10.0)
        p.cota_v(0, alt_v, larg_v, 10.0)
        # o título vai abaixo de tudo o que já foi desenhado: as linhas de eixo passam 1,5 m
        # além das peças, com a bolinha na ponta, e a bolinha do primeiro eixo caía no título
        y_tit = min(-(10.0 + 8.0) * esc, p.extremos[1] - p.dy - 6.0 * esc)      # extremos: absolutos; texto: da vista
        p.texto(0, y_tit, nome, 3.5 * esc)
        p.texto(0, y_tit - 4.5 * esc, "escala 1:%s · marcas de conjunto no lugar de montagem; peça solta com a própria marca" % (int(esc) if float(esc).is_integer() else esc), 2.0 * esc)
        ext_c = p.extremos
        d.metadados.setdefault("celulas", []).append([round(t, 1) for t in ext_c])
        d.vistas.append({"origem": [minimo[0], minimo[1], minimo[2]], "normal": list(w), "acima": list(v),
                         "profundidade": None, "cortar": False, "entidades": None, "rotular": True,
                         "nome": nome, "tipo": tipo, "pecas_cortadas": 0, "pecas_projetadas": n_pecas,
                         "largura": round(larg_v, 1), "altura": round(alt_v, 1), "canto": [x0, y0], "avisos": [],
                         "ref2d": [round(u0 - _dot(minimo, u), 2), round(v0 - _dot(minimo, v), 2)]})
    d.metadados["detalhamento"] = {"grupo": "localizacao", "posicoes": [], "itens": {}}
    return d
