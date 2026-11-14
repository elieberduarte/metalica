# -*- coding: utf-8 -*-
"""Localização e chumbação: fatias da planta, eixos, níveis, locação dos chumbadores.

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
from nucleo2d.detalhe.conjuntos_grupos import (  # noqa: E402
    _casco,
    _instancias_do_conjunto,
    _sobrepoe,
    posicao_base)


# ============================================================ localização
def _extensao_menor(e) -> float:
    """A espessura da peça: a menor extensão dos vértices na direção de menor espalhamento (a chapa
    em pé ou deitada, em qualquer orientação)."""
    from saida.detalhamento import _autovetores
    c, pca = _autovetores(e.vertices)
    n = tuple(pca[2])
    t = [sum(v[i] * n[i] for i in range(3)) for v in e.vertices]
    return max(t) - min(t)


def _itens_de_localizacao(pecas: Sequence[Solido]) -> List[Tuple[str, List[Solido]]]:
    """(rótulo, peças) por instância de conjunto; peça solta (marca = conjunto, ou sem
    conjunto) vale por si."""
    por_conj: Dict[str, List[Solido]] = collections.OrderedDict()
    soltas: List[Solido] = []
    from saida.detalhamento import _eh_telha
    for e in pecas:
        m = _marcas(e)
        if _eh_telha(str(m.get("perfil") or e.nome or "")):
            # a telha tem a paginação dela: na localização, "TL2" (telha) ao lado de "T.L.2" (terça lateral)
            # confundia (análise das pranchas, 29/09)
            continue
        conj = str(m.get("conjunto") or "")
        pos = str(m.get("posicao") or "")
        if conj and conj != pos:
            por_conj.setdefault(conj, []).append(e)
        else:
            soltas.append(e)
    itens: List[Tuple[str, List[Solido]]] = []
    for conj, lista in list(por_conj.items()):
        total = collections.Counter(posicao_base(e) for e in lista)
        n = 0
        for q in total.values():
            n = math.gcd(n, q)
        n = max(n, 1)
        unidade = collections.Counter({k: q // n for k, q in total.items()})
        if sum(unidade.values()) == 1:
            # o conjunto "solo" de uma peça (o numerar dá M#### à peça fora de conjunto) é peça solta: a marca dela, não o
            # M#### que não existe em folha nenhuma (Hora Certa · Galpão Existente, 29/10: 239 rótulos M#### na planta)
            soltas.extend(lista)
            continue
        for g in _instancias_do_conjunto(lista, unidade):
            itens.append((conj, g))
    for e in soltas:
        m = _marcas(e)
        itens.append((str(m.get("posicao") or e.nome or ""), [e]))
    return itens


#: Item menor que isto (chapinha solta, conjunto de chapas) não ganha marca na planta.
MENOR_ITEM_LOCALIZACAO = 500.0


#: Folga da fatia das elevações da localização, além da espessura das tesouras do plano do corte (os suportes
#: de terça e as chapas coladas nelas entram; a tesoura do vão seguinte não).
FOLGA_FATIA = 150.0


#: Meia espessura da fatia que passa numa linha de eixo (a ponta da tesoura, o chumbamento e a chapa de apoio).
FOLGA_FATIA_EIXO = 400.0


def _plano_da_fatia(itens, w, ex: Optional[dict] = None, largura: float = 0.0, nomes: Optional[dict] = None):
    """O corte de uma elevação da localização: (w_min, w_max, nome) da fatia em volta do plano dos conjuntos
    planos que olham para a vista (as tesouras, na transversal). Vale o plano que mais se repete com os
    mesmos conjuntos (o pórtico típico), depois o com mais conjuntos, depois o mais perto de quem olha. Sem
    conjunto plano que cubra um terço da `largura` da vista (na longitudinal só há os dispositivos da
    ponta), o corte passa na primeira linha de eixo (os apoios: a ponta de cada tesoura com o chumbamento).
    Com todas as tesouras projetadas umas sobre as outras não se lia nada (pedido do usuário, 30/09: "uma
    fatia sem ver elementos atrás dos perfis"). None: nem conjunto plano nem eixo."""
    planos = []
    for rotulo, lista in itens:
        if not rotulo or len(lista) < 2:
            continue
        if re.match(r"^(A\.[CDL]\.|C\.?V\.)\d", (nomes or {}).get(rotulo) or rotulo):
            continue                                  # agulhas e contraventos típicos: repetem em todo vão
        vv = [q for e in lista for q in e.vertices]
        ws = [_dot(q, w) for q in vv]
        ext_w = max(ws) - min(ws)
        ext3 = max(max(q[i] for q in vv) - min(q[i] for q in vv) for i in range(3))
        if ext3 >= 4 * MENOR_ITEM_LOCALIZACAO and ext_w <= 0.2 * ext3 and ext3 >= largura / 3.0:
            planos.append(((max(ws) + min(ws)) / 2.0, min(ws), max(ws), rotulo))
    if not planos:
        # a primeira linha de eixo; sem ela, o plano dos conjuntos menores; sem nenhum, a fachada da frente (a
        # parede lateral da Sala, com os contraventos em X da parede de trás por cima dela) — antes que a vista de
        # tudo sobreposto
        if ex:
            from nucleo3d.eixos import segmentos
            linhas = sorted((_dot(s_["a"], w), s_["nome"]) for s_ in segmentos(ex)
                            if abs(_dot(s_["a"], w) - _dot(s_["b"], w)) < 1.0 and not s_.get("malha"))
            if linhas:
                c, nome = linhas[0]
                return c - FOLGA_FATIA_EIXO, c + FOLGA_FATIA_EIXO, nome
        if largura <= 0:
            return None
        menor = _plano_da_fatia(itens, w, None, 0.0, nomes)
        if menor is not None:
            return menor
        ws_ = [_dot(q, w) for _r, lista in itens for e in lista for q in e.vertices]
        return (min(ws_) - 1.0, min(ws_) + 2 * FOLGA_FATIA_EIXO, "") if ws_ else None
    planos.sort()
    grupos = [[planos[0]]]
    for pl in planos[1:]:
        if pl[0] - grupos[-1][-1][0] <= 2 * FOLGA_FATIA:
            grupos[-1].append(pl)
        else:
            grupos.append([pl])
    assinatura = [tuple(sorted(pl[3] for pl in gr)) for gr in grupos]
    repete = collections.Counter(assinatura)
    i = min(range(len(grupos)), key=lambda k: (-repete[assinatura[k]], -len(grupos[k]), grupos[k][0][0]))
    gr = grupos[i]
    a, b = min(pl[1] for pl in gr) - FOLGA_FATIA, max(pl[2] for pl in gr) + FOLGA_FATIA
    c = sum(pl[0] for pl in gr) / len(gr)
    nome = ""
    if ex:
        from nucleo3d.eixos import segmentos
        perto = [(abs(_dot(s_["a"], w) - c), s_["nome"]) for s_ in segmentos(ex)
                 if abs(_dot(s_["a"], w) - _dot(s_["b"], w)) < 1.0 and not s_.get("malha")]
        perto = [t for t in perto if t[0] <= (b - a) / 2.0 + FOLGA_FATIA]
        if perto:
            nome = min(perto)[1]
    return a, b, nome


def _cortar_na_fatia(e: Solido, w, a: float, b: float) -> List[Tuple[float, float, float]]:
    """Os pontos da peça dentro da fatia a ≤ w·p ≤ b (as faces recortadas nos dois planos); [] se ela não
    chega à fatia. A peça toda dentro devolve os próprios vértices."""
    ws = [_dot(q, w) for q in e.vertices]
    if not ws or max(ws) < a or min(ws) > b:
        return []
    if min(ws) >= a and max(ws) <= b:
        return list(e.vertices)
    pts = []

    def recorta(poli, lim, sinal):
        saida = []
        n = len(poli)
        for k in range(n):
            p1, p2 = poli[k], poli[(k + 1) % n]
            d1, d2 = sinal * (_dot(p1, w) - lim), sinal * (_dot(p2, w) - lim)
            if d1 >= 0:
                saida.append(p1)
            if (d1 >= 0) != (d2 >= 0):
                t = d1 / (d1 - d2)
                saida.append(tuple(p1[j] + t * (p2[j] - p1[j]) for j in range(3)))
        return saida
    for f in e.faces:
        poli = [e.vertices[k] for k in f]
        poli = recorta(recorta(poli, a, 1.0), b, -1.0)
        pts.extend(poli)
    if not e.faces:
        pts = [q for q, x in zip(e.vertices, ws) if a <= x <= b]
    return pts


def _eixos_do_modelo(doc: Documento, eixos: Optional[dict], nomes_producao: Optional[dict]) -> Optional[dict]:
    """Os eixos gravados no projeto, ou identificados do modelo agora (None se não der)."""
    from nucleo3d import eixos as _eixos
    if _eixos.sem_eixos(eixos):                                 # o usuário apagou todos: a planta sai sem eixos
        return None
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
        # a linha passa da borda das peças: com beiral ou marquise além do último eixo a bolinha
        # caía em cima da estrutura (o depósito químico, 29/09)
        ts = [(cx - a[0]) * d[0] + (cy - a[1]) * d[1] for cx in (0.0, largura) for cy in (0.0, altura)]
        m = 2.0 * esc
        t0, t1 = min(0.0, min(ts) - m), max(L, max(ts) + m)
        a, b = (a[0] + d[0] * t0, a[1] + d[1] * t0), (a[0] + d[0] * t1, a[1] + d[1] * t1)
        # a linha vai de bolinha a bolinha; a bolinha fica encostada na ponta da linha
        p.linha(a[0], a[1], b[0], b[1], camada="EIXO")
        for ponta, sinal in ((a, -1.0), (b, 1.0)):
            cx, cy = ponta[0] + sinal * d[0] * r, ponta[1] + sinal * d[1] * r
            p.circulo(cx, cy, r, camada="EIXO")
            p.texto(cx, cy - 0.35 * h, seg["nome"], h, "EIXO", alinhamento="centro")
        if seg.get("malha"):
            continue                                  # a malha local tem a planta de chumbação dela, com as cotas
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


def _locacao_dos_chumbadores(p: "_Papel", ex: dict, chumb: Sequence[Solido], u, v, u0: float, v0: float,
                             nomes: Optional[Dict[str, str]] = None, chapas: Sequence[Solido] = (),
                             esc: float = 0.0, todas_chapas: Sequence[Solido] = ()) -> List[Tuple[str, str, str, str, str]]:
    """A locação de cada grupo de chumbadores (os de uma base: até 400 mm entre si em planta) até o eixo de letra e o de
    número mais perto — o que a obra mede para pôr o chumbador no concreto (Q09, primeiro uso 16/10: a planta de
    chumbação só tinha os eixos e a marca num pontinho; o CB2 de D1/D7 a ~260 mm do eixo sem cota).

    R11 (2ª rodada, 16/10): as cotas de 21 e 29 mm viravam um risco de 0,2 mm no papel, sem dizer se era em X ou em Y nem
    a partir de onde, e não havia o nível. A cota só sai com pelo menos 1,5 mm de papel; cada grupo ganha uma linha no
    quadro de locação (devolvida): (marca, cruzamento, até o eixo de letra, até o eixo de número, topo da chapa) — com
    "no eixo" quando está nele e o eixo vizinho para o lado em que o grupo sai."""
    from nucleo3d.eixos import segmentos
    linhas = segmentos(ex)
    centros = []
    for e in chumb:
        vs = e.vertices
        centros.append((sum(q[0] for q in vs) / len(vs), sum(q[1] for q in vs) / len(vs), e))
    grupos: List[list] = []
    marca_de = lambda e_: str(_marcas(e_).get("posicao") or e_.nome or "")      # noqa: E731

    def caixa3(e_):
        return tuple((min(q[i] for q in e_.vertices), max(q[i] for q in e_.vertices)) for i in range(3))
    caixas_ch = [(id(c_), caixa3(c_)) for c_ in (todas_chapas or chapas)]

    def chapa_de(e_):
        # a chapa de base que o chumbador atravessa (None sem nenhuma)
        b_ = caixa3(e_)
        return next((i_ for i_, k_ in caixas_ch if all(k_[i][0] - 2.0 <= b_[i][1] and b_[i][0] - 2.0 <= k_[i][1]
                                                       for i in range(3))), None)
    for c in centros:
        for g in grupos:
            # a base é a mesma marca na mesma chapa: o chumbador de outra base encostada (a da marquise na MQ1, 1,42 m
            # abaixo da do W530 na AP5; as PM-P18 e PM-P19 do mezanino, a menos de 400 mm) entrava no grupo vizinho e
            # ficava sem linha de locação (montador N01, auditor N24, 30/10)
            if marca_de(g[0][2]) == marca_de(c[2]) and chapa_de(g[0][2]) == chapa_de(c[2]) and                     any(math.hypot(c[0] - o[0], c[1] - o[1]) <= 400.0 for o in g):
                g.append(c)
                break
        else:
            grupos.append([c])

    def caixa_xy(e_):
        vs_ = e_.vertices
        return (min(q[0] for q in vs_), min(q[1] for q in vs_), max(q[0] for q in vs_), max(q[1] for q in vs_),
                max(q[2] for q in vs_))
    caixas_todas = [(id(c_), caixa_xy(c_)) for c_ in (todas_chapas or chapas)]
    quadro = []
    for g in grupos:
        cx = sum(o[0] for o in g) / len(g)
        cy = sum(o[1] for o in g) / len(g)
        marca = str(_marcas(g[0][2]).get("posicao") or g[0][2].nome or "")
        rotulo = (nomes or {}).get(marca) or marca
        textos, cruz = {}, {}
        for tipo in ("letra", "numero"):
            melhor = None
            mesmos = []
            for s_ in linhas:
                if s_["tipo"] != tipo:
                    continue
                ax, ay, bx, by = s_["a"][0], s_["a"][1], s_["b"][0], s_["b"][1]
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                if L2 < 1e-9:
                    continue
                mesmos.append(s_)
                k = ((cx - ax) * dx + (cy - ay) * dy) / L2
                fx, fy = ax + k * dx, ay + k * dy
                dist = math.hypot(cx - fx, cy - fy)
                if melhor is None or dist < melhor[0]:
                    melhor = (dist, fx, fy, s_["nome"], s_)
            if melhor is None:
                continue
            dist, fx, fy, nome_eixo, s0 = melhor
            cruz[tipo] = str(nome_eixo)
            if dist < 5.0:
                textos[tipo] = "no eixo %s" % nome_eixo
                continue
            # o eixo vizinho para o lado em que o grupo sai: diz a direção sem depender de X/Y do papel
            nx, ny = (cx - fx) / dist, (cy - fy) / dist
            viz = None
            for s_ in mesmos:
                if s_ is s0:
                    continue
                d_ = (s_["a"][0] - fx) * nx + (s_["a"][1] - fy) * ny
                if d_ > 1.0 and (viz is None or d_ < viz[0]):
                    viz = (d_, s_["nome"])
            textos[tipo] = "%d do eixo %s %s" % (round(dist), nome_eixo,
                                                ("para o %s" % viz[1]) if viz else "para fora da malha")
            if esc and dist < 1.5 * esc:
                continue                                    # menos de 1,5 mm no papel: só no quadro
            pf = (_dot((fx, fy, 0.0), u) - u0, _dot((fx, fy, 0.0), v) - v0)
            pc = (_dot((cx, cy, 0.0), u) - u0, _dot((cx, cy, 0.0), v) - v0)
            p.d.add(_Cota(modo="alinhada", p1=p._p(*pf), p2=p._p(*pc), deslocamento=4.0, texto="%d" % round(dist), altura=ALTURA_COTA,
                          atributos=dict(p.atr, locacao=rotulo, eixo=str(nome_eixo))))
        topo = None
        minhas = []
        # a chapa da base é a que os chumbadores do grupo atravessam; sem nenhuma, as que estão a até 400 mm (antes,
        # sempre essas: a base de baixo levava o topo da chapa de cima, encostada)
        cx3 = [tuple((min(q[i] for q in o[2].vertices), max(q[i] for q in o[2].vertices)) for i in range(3)) for o in g]
        atravessa = [c_ for c_ in chapas if any(all(min(q[i] for q in c_.vertices) - 2.0 <= b_[i][1]
                                                    and b_[i][0] - 2.0 <= max(q[i] for q in c_.vertices) for i in range(3))
                                                for b_ in cx3)]
        for c_ in atravessa or chapas:
            vs_ = c_.vertices
            if atravessa or any(math.hypot(q[0] - cx, q[1] - cy) <= 400.0 for q in vs_):
                z_ = max(q[2] for q in vs_)
                topo = z_ if topo is None else max(topo, z_)
                minhas.append(caixa_xy(c_))
        # a chapa de base desta que sobrepõe a de outra base em planta: duas bases no mesmo lugar (montador N01)
        meus_pts = [(o[0], o[1]) for o in g]
        conflito = None
        for i_, cx_ in caixas_todas:
            if any(i_ == id(c_) for c_ in chapas if caixa_xy(c_) in minhas):
                continue
            sobre = any(a[0] < cx_[2] and cx_[0] < a[2] and a[1] < cx_[3] and cx_[1] < a[3] for a in minhas) or any(
                cx_[0] <= x_ <= cx_[2] and cx_[1] <= y_ <= cx_[3] for x_, y_ in meus_pts)
            if sobre:
                conflito = cx_[4]
                break
        topo_txt = ("%+.3f" % (topo / 1000.0)).replace(".", ",") if topo is not None else "—"
        if conflito is not None:
            topo_txt += " — SOBREPÕE outra chapa de base (topo %s): a conferir com o projetista" % (
                "%+.3f" % (conflito / 1000.0)).replace(".", ",")
        quadro.append((rotulo, "%s-%s" % (cruz.get("letra", "?"), cruz.get("numero", "?")),
                       textos.get("letra", "—"), textos.get("numero", "—"), topo_txt))
    quadro.sort(key=lambda r: (_ordem_natural(r[0]), r[1]))
    return quadro


def _regioes_da_chumbacao(ex: Optional[dict], chumb: Sequence[Solido], chapas: Sequence[Solido]) -> list:
    """As plantas da chumbação: (eixos, chumbadores, chapas, título, referência) — uma só sem malhas locais; com elas,
    uma por malha que tem peça, cada peça na malha em que o centro dela cai (`eixos.malha_do_ponto`)."""
    if not ex or not ex.get("malhas"):
        return [(ex, list(chumb), list(chapas), "PLANTA DE CHUMBAÇÃO", "")]
    from nucleo3d import eixos as _eixos
    malhas = _eixos.malhas_de(ex)
    segs = _eixos.segmentos(ex)
    por = {m.get("nome") or "": ([], []) for m in malhas}

    def centro(e):
        vs = e.vertices
        return (sum(q[0] for q in vs) / len(vs), sum(q[1] for q in vs) / len(vs))

    def malha_de(c):
        sel = [s for s in _eixos.malha_do_ponto(c, segs) if s.get("tipo") != "extra"]
        return (sel[0].get("malha") or "") if sel else ""
    # a base inteira numa malha só, pelo centro do grupo (os chumbadores até 400 mm entre si, como a locação): no canto
    # em que a ampliação encosta na marquise, os 14 CB3 do P5 se dividiam entre as duas plantas (30/10)
    grupos: List[list] = []
    marca_de = lambda e_: str(_marcas(e_).get("posicao") or e_.nome or "")      # noqa: E731
    for e in chumb:
        c = centro(e)
        for g in grupos:
            if marca_de(g[0][1]) == marca_de(e) and any(math.hypot(c[0] - o[0], c[1] - o[1]) <= 400.0 for o, _e in g):
                g.append((c, e))
                break
        else:
            grupos.append([(c, e)])
    centros = []
    for g in grupos:
        cg = (sum(o[0] for o, _e in g) / len(g), sum(o[1] for o, _e in g) / len(g))
        m = malha_de(cg)
        centros.append((cg, m))
        por[m][0].extend(e for _o, e in g)
    for e in chapas:
        # a chapa vai com a base em que está (o grupo de chumbadores mais perto, até 400 mm)
        c = centro(e)
        perto = min(centros, key=lambda x: math.hypot(c[0] - x[0][0], c[1] - x[0][1]), default=None)
        if perto is not None and math.hypot(c[0] - perto[0][0], c[1] - perto[0][1]) <= 400.0:
            por[perto[1]][1].append(e)
        else:
            por[malha_de(c)][1].append(e)
    saida = []
    for m in malhas:
        nome = m.get("nome") or ""
        cb, ch = por[nome]
        if not cb and not ch:
            continue
        if not nome:
            saida.append((m, cb, ch, "PLANTA DE CHUMBAÇÃO", ""))
            continue
        ref = _eixos.referencia_da_malha(m, malhas[0])
        if m.get("descricao"):
            ref = (ref + " — " if ref else "") + m["descricao"]
        saida.append((m, cb, ch, "PLANTA DE CHUMBAÇÃO — %s" % nome.upper(), ref))
    return saida


def desenho_de_chumbacao(doc: Documento, pecas: Sequence[Solido], nomes_producao: Optional[dict],
                         titulo: str = "Detalhamento – chumbação", eixos: Optional[dict] = None,
                         nomes: Optional[Dict[str, str]] = None, niveis: Optional[Sequence[dict]] = None) -> Desenho:
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
    caixas_cb = [tuple((min(v[i] for v in e.vertices), max(v[i] for v in e.vertices)) for i in range(3)) for e in chumb]
    perto, atravessadas = [], []
    for e in pecas:
        # a placa soldada no pilar é "parte" do conjunto dele (o conjunto do pilar com a base, 14/10/2026): conta
        chapa_e = _tipo_ifc(e).startswith("IfcPlate") or type(getattr(e, "parametrica", None)).__name__ == "Chapa"
        tipo_e = tipos.get(str(_marcas(e).get("posicao") or ""))
        if e.id in ids_ch or (tipo_e not in ("chapa", "castanha", "suporte_terca", None) and not (tipo_e == "parte" and chapa_e)):
            continue
        zs = [v[2] for v in e.vertices]
        cx = sum(v[0] for v in e.vertices) / len(e.vertices)
        cy = sum(v[1] for v in e.vertices) / len(e.vertices)
        if not any(math.hypot(cx - c[0], cy - c[1]) <= 400.0 and abs(min(zs) - c[2]) <= 500.0 for c in centros):
            continue
        # a placa de base passa de 1" (a engastada de 31,75; a do galpão lançado, 2"): até 80 mm se for chapa, como
        # na regra de cima — com 25 mm a placa de 31,75 da base aplicada no 3D sumia da planta (14/10/2026)
        lim_e = 80.0 if chapa_e else 25.0
        if not so_chapas and _extensao_menor(e) <= lim_e:
            # a chapa que o chumbador atravessa, deitada ou em pé (a de parede)
            cx_e = [(min(v[i] for v in e.vertices), max(v[i] for v in e.vertices)) for i in range(3)]
            if any(all(cx_e[i][0] - 2.0 <= b[i][1] and b[i][0] - 2.0 <= cx_e[i][1] for i in range(3)) for b in caixas_cb):
                atravessadas.append(e)
        if max(zs) - min(zs) <= lim_e:
            perto.append(e)
    # a chapa de base é a que o chumbador atravessa; a chapa deitada logo acima (o suporte da agulha
    # no depósito químico, 29/09) não é — a regra da vizinhança fica para o modelo em que nenhuma cruza
    chapas = atravessadas or perto
    # uma planta por malha (as malhas locais, Hora Certa · Galpão Existente, 30/10): cada frente com os eixos dela e na
    # escala da maior — a obra inteira numa planta só saía a 1:500 e a base locada "73481 do eixo 1 para fora da malha"
    regioes = _regioes_da_chumbacao(ex, chumb, chapas)
    from nucleo3d.eixos import segmentos
    preparo = []
    for ex_r, chumb_r, chapas_r, titulo_r, ref_r in regioes:
        itens = chumb_r + chapas_r
        todos = [v for e in itens for v in e.vertices]
        if ex_r:
            # a planta abrange os eixos inteiros (com a folga das bolinhas)
            todos = todos + [q for s in segmentos(ex_r) for q in (s["a"], s["b"])]
        minimo = [min(v[i] for v in todos) for i in range(3)]
        maximo = [max(v[i] for v in todos) for i in range(3)]
        if ref_r:
            # a malha local na direção dela: as linhas em pé e deitadas, as cotas sem o erro do giro
            g_ = (ex_r["eixo_g"][0], ex_r["eixo_g"][1], 0.0)
            u, v = g_, (-g_[1], g_[0], 0.0)
            if max(_dot(q, v) for q in todos) - min(_dot(q, v) for q in todos) > \
                    max(_dot(q, u) for q in todos) - min(_dot(q, u) for q in todos):
                u, v = v, (-g_[0], -g_[1], 0.0)
        elif maximo[1] - minimo[1] > maximo[0] - minimo[0]:
            u, v = (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)
        else:
            u, v = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        us = [_dot(q, u) for q in todos]
        vs_ = [_dot(q, v) for q in todos]
        u0, v0 = min(us), min(vs_)
        preparo.append((ex_r, chumb_r, chapas_r, titulo_r, ref_r, itens, minimo, u, v, u0, v0,
                        max(us) - u0, max(vs_) - v0))
    w = (0.0, 0.0, -1.0)
    esc = max(escala_normalizada(max(r[11] / 700.0, r[12] / 450.0, 1.0)) for r in preparo)
    d = Desenho(nome=titulo, escala=esc)
    h_txt = 2.5 * esc
    atr_base = {"detalhe": "chumbacao"}
    _registrar_camadas_de_pecas(d)
    x0 = 0.0
    for ex_r, chumb_r, chapas_r, titulo_r, ref_r, itens, minimo, u, v, u0, v0, larg_v, alt_v in preparo:
        p = _Papel(d, dict(atr_base, vista=titulo_r), x0, 0.0)
        rotulos = []
        quadro_loc = []
        for e in itens:
            pts = [(_dot(q, u) - u0, _dot(q, v) - v0) for q in e.vertices]
            casco = _casco(pts)
            if len(casco) < 3:
                continue
            m = _marcas(e)
            atr = dict(atr_base, vista=titulo_r, origem=e.id, nome=e.nome or "")
            if m.get("posicao"):
                atr["posicao"] = str(m["posicao"])
            if m.get("conjunto"):
                atr["conjunto"] = str(m["conjunto"])
            pp = _Papel(d, atr, x0, 0.0)
            eh_chumb = e.id in ids_ch
            pp.polilinha(casco, fechada=True, camada="TIRANTES" if (eh_chumb and not so_chapas) else "CHAPAS-VISTA")
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
        if ex_r:
            _desenhar_eixos(p, ex_r, u, v, u0, v0, esc, larg_v, alt_v)
            if not so_chapas:
                quadro_loc = _locacao_dos_chumbadores(p, ex_r, chumb_r, u, v, u0, v0, nomes, chapas=chapas_r, esc=esc,
                                                      todas_chapas=chapas)
        if not ex_r:
            # sem eixos, as totais das peças; com eixos, a cadeia entre eixos já fecha com a total dela — a total das
            # peças ia até a ponta das linhas de eixo (37828 no depósito, no vazio) e, medindo as peças, ficava fora
            # da caixa na prancha reduzida (análise das pranchas, 29/09)
            p.cota_h(0, larg_v, 0, -10.0)
            p.cota_v(0, alt_v, larg_v, 10.0)
        # o título e a linha de baixo são o cabeçalho da caixa (na prancha vão para o canto de cima, fora das bolinhas
        # dos eixos, onde encostavam); a escala fica só no "ESC." da caixa — a do desenho de origem (1:75) não é a da
        # prancha reduzida (1:125)
        n_chumb, n_chapas = (0, len(chumb_r) + len(chapas_r)) if so_chapas else (len(chumb_r), len(chapas_r))
        atr_t = p.atr
        p.atr = dict(atr_t, cabecalho=0)
        p.texto(0, -(10.0 + 8.0) * esc, titulo_r, 3.5 * esc)
        p.atr = dict(atr_t, cabecalho=1)
        p.texto(0, -(10.0 + 8.0 + 4.5) * esc, "%d chumbador(es) e %d chapa(s) de base, vistos de cima, nos eixos da obra"
                % (n_chumb, n_chapas)
                + (" (sem chumbador no modelo: os furos das chapas marcam onde eles passam)" if so_chapas else ""), 2.0 * esc)
        y_q = -(10.0 + 8.0 + 4.5 + 7.0) * esc
        if ref_r:
            # onde a malha local fica na principal: o que a obra marca primeiro
            p.atr = dict(atr_t, referencia_malha=True)
            p.texto(0, y_q, "MALHA LOCAL — " + ref_r, 2.5 * esc)
            y_q -= 5.0 * esc
        if quadro_loc:
            # o quadro de locação embaixo do título (R11): uma linha por grupo, a distância a cada eixo e para que lado
            p.atr = dict(atr_t, quadro_locacao=True)
            ref_n = referencia_dos_niveis(niveis)
            p.texto(0, y_q, "LOCAÇÃO DOS CHUMBADORES — centro do grupo até os eixos (mm); topo da chapa de base (m%s)"
                    % (", " + ref_n if ref_n else ""), 2.5 * esc)
            for k, (rot_, cruz_, t_l, t_n, topo_) in enumerate(quadro_loc, 1):
                p.texto(0, y_q - 4.0 * k * esc, "%s em %s: %s; %s; topo %s" % (rot_, cruz_, t_l, t_n, topo_), 2.0 * esc)
        p.atr = atr_t
        ext_c = p.extremos
        d.metadados.setdefault("celulas", []).append([round(t, 1) for t in ext_c])
        d.vistas.append({"origem": [minimo[0], minimo[1], minimo[2]], "normal": list(w), "acima": list(v),
                         "profundidade": None, "cortar": False, "entidades": None, "rotular": True,
                         "nome": titulo_r, "tipo": "topo", "pecas_cortadas": 0, "pecas_projetadas": len(itens),
                         "largura": round(larg_v, 1), "altura": round(alt_v, 1), "canto": [x0, 0.0], "avisos": [],
                         "ref2d": [round(u0 - _dot(minimo, u), 2), round(v0 - _dot(minimo, v), 2)]})
        x0 = ext_c[2] + 30.0 * esc
    d.metadados["detalhamento"] = {"grupo": "chumbacao", "posicoes": [], "itens": {}}
    d.metadados["eixos"] = ex
    return d


def referencia_dos_niveis(niveis: Optional[Sequence[dict]]) -> str:
    """"±0,000 = Piso acabado +906,40": o nível do projeto em z = 0, a que as cotas de nível das folhas se referem (montador
    M14, Hora Certa · Galpão Existente, 29/10: "topo −1,389 de quê?"). Vazio sem os níveis do projeto."""
    zero = [n for n in niveis or () if isinstance(n, dict) and abs(float(n.get("z") or 0.0)) < 1.0 and n.get("nome")]
    return ("±0,000 = %s" % zero[0]["nome"]) if zero else ""


def _nivel_m(z: float) -> str:
    return ("±0,000" if abs(z) < 0.5 else "%+.3f" % (z / 1000.0)).replace(".", ",")


def _desenhar_niveis(p: "_Papel", niveis: Sequence[dict], v0: float, alt_v: float, esc: float) -> int:
    """As marcas de nível na elevação (v = z): à esquerda da vista, um traço com o triângulo e "nome (+3,290)", para
    cada nível do projeto na altura das peças (até 0,5 m fora). Devolve quantas."""
    n = 0
    for nv in sorted((x for x in niveis or () if isinstance(x, dict) and x.get("nome")), key=lambda x: float(x.get("z") or 0)):
        z = float(nv.get("z") or 0.0)
        y = z - v0
        if y < -500.0 or y > alt_v + 500.0:
            continue
        x1, x0 = -3.0 * esc, -40.0 * esc
        p.linha(x0, y, x1, y, camada="EIXO")
        t = 1.5 * esc
        p.polilinha([(x1 - 4.0 * esc - t, y + 2 * t), (x1 - 4.0 * esc + t, y + 2 * t), (x1 - 4.0 * esc, y)], fechada=True,
                    camada="TEXTO")
        p.texto(x1 - 7.0 * esc, y + 0.6 * esc, "%s (%s)" % (nv["nome"], _nivel_m(z)), 2.0 * esc, "TEXTO",
                alinhamento="direita", atributos={"nivel": round(z, 1)})
        n += 1
    return n


def desenho_de_localizacao(doc: Documento, pecas: Sequence[Solido], titulo: str = "Detalhamento – localização",
                           ignorar: Sequence[str] = (), nomes: Optional[Dict[str, str]] = None,
                           camadas_pecas: Optional[Dict[str, str]] = None, eixos: Optional[dict] = None,
                           nomes_producao: Optional[dict] = None,
                           vistas_pedidas: Sequence[str] = ("topo", "frente", "lateral"),
                           titulo_planta: str = "", deitar_em_y: Optional[bool] = None,
                           rotular_de_topo: bool = False, niveis: Optional[Sequence[dict]] = None) -> Desenho:
    """Planta e duas elevações esquemáticas do modelo inteiro (cada peça é o contorno
    convexo da sua projeção, em linha fina) com a marca de cada conjunto e de cada peça
    solta escrita no lugar em que está montada: é a planta de montagem que diz onde vai
    cada item detalhado. `ignorar`: marcas de posição que ficam fora (telhas).
    `vistas_pedidas` (topo, frente, lateral) e `titulo_planta`: o pré-moldado usa só a planta (a locação dos pilares,
    a fôrma de cada nível) ou só os dois cortes (16/10). `deitar_em_y`: o lado comprido (y) na horizontal, fixo — as
    plantas dos níveis giram todas iguais, pelo prédio, não pelas peças de cada uma; `rotular_de_topo`: a peça vista de
    topo também ganha a marca na planta (o pilar do pré-moldado; a terça vista de ponta da metálica não)."""
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
    comprido_em_y = ext[1] > ext[0] if deitar_em_y is None else bool(deitar_em_y)
    if comprido_em_y:
        # de cima (observador em +z, w = -z): direita = y, cima do papel = -x
        u_pl, v_pl, w_pl = (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, -1.0)
        u_lo, v_lo, w_lo = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)      # vista de +x
        u_tr, v_tr, w_tr = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)       # vista de -y
    else:
        u_pl, v_pl, w_pl = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)
        u_lo, v_lo, w_lo = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)       # vista de -y
        u_tr, v_tr, w_tr = (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)      # vista de -x
    vistas = [(titulo_planta or "PLANTA DE LOCALIZAÇÃO", "topo", u_pl, v_pl, w_pl),
              ("ELEVAÇÃO LONGITUDINAL", "frente", u_lo, v_lo, w_lo),
              ("ELEVAÇÃO TRANSVERSAL", "lateral", u_tr, v_tr, w_tr)]
    vistas = [vv for vv in vistas if vv[1] in vistas_pedidas] or vistas
    ex_modelo = _eixos_do_modelo(doc, eixos, nomes_producao)
    # as elevações são cortes: só o que está na fatia do plano do pórtico típico, cada peça recortada nela
    # (id -> pontos 3D); a planta vê tudo
    fatias = {}
    for nome, tipo, u, v, w in vistas:
        us_ = [_dot(q, u) for q in todos]
        pl = None if tipo == "topo" else _plano_da_fatia(itens, w, ex_modelo, max(us_) - min(us_), nomes)
        if pl is None:
            fatias[nome] = (None, {e.id: list(e.vertices) for e in pecas})
            continue
        cortes = {}
        for e in pecas:
            pts = _cortar_na_fatia(e, w, pl[0], pl[1])
            if len(pts) >= 3:
                cortes[e.id] = pts
        fatias[nome] = (pl, cortes) if cortes else (None, {e.id: list(e.vertices) for e in pecas})

    def extensao(u, v, nome=None):
        pts = [q for lst in fatias[nome][1].values() for q in lst] if nome else todos
        us = [_dot(p, u) for p in pts]
        vs = [_dot(p, v) for p in pts]
        return max(us) - min(us), max(vs) - min(vs)
    tem = {vv[1] for vv in vistas}
    l_pl, a_pl = extensao(u_pl, v_pl) if "topo" in tem else (0.0, 0.0)
    l_lo, a_lo = extensao(u_lo, v_lo, "ELEVAÇÃO LONGITUDINAL") if "frente" in tem else (0.0, 0.0)
    l_tr, a_tr = extensao(u_tr, v_tr, "ELEVAÇÃO TRANSVERSAL") if "lateral" in tem else (0.0, 0.0)
    folga_papel = 45.0
    # papel útil de uma A1 deitada, descontados carimbo e margens
    esc = escala_normalizada(max((l_pl + folga_papel * 0 + max(l_tr, 0.0)) / 760.0,
                                 (a_pl + a_lo + 2 * folga_papel) / 520.0, 1.0))
    d = Desenho(nome=titulo, escala=esc)
    folga = folga_papel * esc
    atr_base = {"detalhe": "localizacao"}
    h_txt = 2.5 * esc
    lugar = {"topo": (0.0, a_lo + folga if "frente" in tem else 0.0), "frente": (0.0, 0.0),
             "lateral": (l_lo + folga if "frente" in tem else 0.0, 0.0)}
    for (nome, tipo, u, v, w), (x0, y0) in zip(vistas, [lugar[vv[1]] for vv in vistas]):
        plano, cortes = fatias[nome]
        visiveis = [q for lst in cortes.values() for q in lst]
        us = [_dot(p, u) for p in visiveis]
        vs = [_dot(p, v) for p in visiveis]
        u0, v0 = min(us), min(vs)
        p = _Papel(d, dict(atr_base, vista=nome), x0, y0)
        n_pecas = 0
        # contornos
        for e in pecas:
            if e.id not in cortes:
                continue
            pts = [(_dot(q, u) - u0, _dot(q, v) - v0) for q in cortes[e.id]]
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
            if tipo != "topo" and len(lista) == 1 and str(_marcas(lista[0]).get("conjunto") or "") in (
                    "", str(_marcas(lista[0]).get("posicao") or "")):
                # nas elevações só os conjuntos: com as peças soltas (terças, contraventos, uma marca por peça)
                # as marcas se amontoavam e nada se lia (análise das pranchas, 29/09); a planta tem todas
                continue
            nome_r = (nomes or {}).get(rotulo) or rotulo
            if tipo != "topo" and re.match(r"^(A\.[CDL]\.|C\.?V\.)\d", nome_r):
                continue                              # os típicos (contraventos, agulhas) repetem em todo vão: na planta
            vv = [q for e in lista for q in e.vertices]
            no_corte = [q for e in lista for q in cortes.get(e.id, ())]
            if not no_corte:
                continue                              # atrás (ou à frente) do corte
            ext3 = max(max(q[i] for q in vv) - min(q[i] for q in vv) for i in range(3))
            if ext3 < MENOR_ITEM_LOCALIZACAO:
                continue
            # de topo ou não, pelo que aparece no corte (a ponta da tesoura cortada na linha dos apoios tem a
            # marca; a terça vista de ponta, não); a marca vai no meio do que aparece
            vc = no_corte if plano else vv
            pu = [_dot(q, u) - u0 for q in vc]
            pv = [_dot(q, v) - v0 for q in vc]
            ext3c = max(max(q[i] for q in vc) - min(q[i] for q in vc) for i in range(3))
            ext2 = max(max(pu) - min(pu), max(pv) - min(pv))
            if ext3c > 0 and ext2 < 0.3 * ext3c and not (rotular_de_topo and tipo == "topo"):
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
            ex = ex_modelo
            if ex:
                _desenhar_eixos(p, ex, u, v, u0, v0, esc, larg_v, alt_v)
                d.metadados["eixos"] = ex
        p.cota_h(0, larg_v, 0, -10.0)
        p.cota_v(0, alt_v, larg_v, 10.0)
        if tipo != "topo" and niveis:
            _desenhar_niveis(p, niveis, v0, alt_v, esc)        # os níveis do projeto nas elevações (montador M14, 29/10)
        # o título vai abaixo de tudo o que já foi desenhado: as linhas de eixo passam 1,5 m
        # além das peças, com a bolinha na ponta, e a bolinha do primeiro eixo caía no título
        y_tit = min(-(10.0 + 8.0) * esc, p.extremos[1] - p.dy - 6.0 * esc)      # extremos: absolutos; texto: da vista
        # o título e a linha de baixo são o cabeçalho da caixa, como na chumbação; a escala fica só no "ESC." da caixa —
        # a do desenho de origem não é a da prancha quando ela reduz (auditoria D13, 11/10/2026)
        atr_t = p.atr
        p.atr = dict(atr_t, cabecalho=0)
        p.texto(0, y_tit, nome + (" – CORTE NO EIXO %s" % plano[2] if plano and plano[2] else ""), 3.5 * esc)
        p.atr = dict(atr_t, cabecalho=1)
        p.texto(0, y_tit - 4.5 * esc,
                "marcas de conjunto no lugar de montagem; peça solta com a própria marca" if tipo == "topo"
                else ("só o que está no plano do corte, sem as peças de trás; " if plano else "")
                + "tesouras, dispositivos e chumbamentos no lugar de montagem (terças, contraventos e agulhas na planta)",
                2.0 * esc)
        p.atr = atr_t
        ext_c = p.extremos
        d.metadados.setdefault("celulas", []).append([round(t, 1) for t in ext_c])
        d.vistas.append({"origem": [minimo[0], minimo[1], minimo[2]], "normal": list(w), "acima": list(v),
                         "profundidade": None, "cortar": False, "entidades": None, "rotular": True,
                         "nome": nome, "tipo": tipo, "pecas_cortadas": 0, "pecas_projetadas": n_pecas,
                         "largura": round(larg_v, 1), "altura": round(alt_v, 1), "canto": [x0, y0], "avisos": [],
                         "ref2d": [round(u0 - _dot(minimo, u), 2), round(v0 - _dot(minimo, v), 2)]})
    d.metadados["detalhamento"] = {"grupo": "localizacao", "posicoes": [], "itens": {}}
    return d
