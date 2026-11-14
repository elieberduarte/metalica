# -*- coding: utf-8 -*-
"""Malhas das peças, vizinhos no plano, cortes das terças, telha assentada e polilinhas.

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
    _casco)
from nucleo2d.detalhe.conjuntos_curvas import (  # noqa: E402
    _dist_ponto_seg)


#: As malhas das peças do modelo enquanto os conjuntos são desenhados (malhas_guardadas): _vizinhos_no_plano e
#: _cortes_das_tercas olham o modelo inteiro a cada conjunto. No Edifício Administrativo (29/10, 5.562 peças) eram 12,8 s
#: de malhas por vez, duas vezes em cada um dos 82 conjuntos: 36 dos 41 min do Detalhar. Pela identidade da peça (o
#: desenho não mexe no modelo); fora do `with`, a malha é feita de novo como antes.
_MALHAS: Optional[Dict[int, tuple]] = None


class malhas_guardadas:
    """`with malhas_guardadas():` — dentro, a malha de cada peça é feita uma vez só"""

    def __enter__(self):
        global _MALHAS
        self._antes = _MALHAS
        if _MALHAS is None:
            _MALHAS = {}
        return self

    def __exit__(self, *a):
        global _MALHAS
        _MALHAS = self._antes
        return False


def _malha_guardada(ent):
    from nucleo3d.geometria import malha
    if _MALHAS is None:
        return malha(ent)
    g = _MALHAS.get(id(ent))
    if g is None or g[0] is not ent:
        try:
            g = (ent, malha(ent), None)
        except Exception as e:                                # noqa: BLE001 — a peça sem malha falha igual da próxima vez
            g = (ent, None, e)
        _MALHAS[id(ent)] = g
    if g[2] is not None:
        raise g[2]
    return g[1]


def _vizinhos_no_plano(doc: Documento, instancia: Sequence, origem, u, v, w, u0: float, v0: float,
                       dx: float, dy: float, perto: float = 400.0) -> List[tuple]:
    """As peças de fora da tesoura que ficam no plano dela (cabem em 400 mm atravessado, o meio a até
    300 mm do plano) e encostadas no contorno (até `perto` mm): o montante lateral e as chapas dele na
    ponta. Parafuso, telha, calha e barra redonda não. Devolve (id, marca, contorno projetado)."""
    ws = [_dot(_sub(q, origem), w) for e in instancia for q in e.vertices]
    if not ws:
        return []
    w0 = (min(ws) + max(ws)) / 2.0
    ids = {e.id for e in instancia}
    pts_i = [(_dot(_sub(q, origem), u) - u0 + dx, _dot(_sub(q, origem), v) - v0 + dy) for e in instancia for q in e.vertices]
    casco = _casco(pts_i)
    if len(casco) < 3:
        return []
    bx0, bx1 = min(q[0] for q in casco) - perto, max(q[0] for q in casco) + perto
    by0, by1 = min(q[1] for q in casco) - perto, max(q[1] for q in casco) + perto
    saida = []
    cand = []
    for ent in doc.entidades.values():
        if ent.id in ids or getattr(ent, "tipo", "") not in ("barra", "solido", "chapa"):
            continue
        perfil = str(_marcas(ent).get("perfil") or getattr(ent, "nome", "") or "")
        if re.search(r"BOLT|TELHA|CALHA|RUFO", perfil, re.I) or _eh_redonda_perfil(perfil) \
                or "telha" in str(getattr(ent, "camada", "") or "").lower():
            continue
        try:
            vs = _malha_guardada(ent)[0]
        except Exception:                                     # noqa: BLE001 — peça sem malha
            continue
        if not vs:
            continue
        pw = [_dot(_sub(q, origem), w) - w0 for q in vs]
        if max(pw) - min(pw) > 400.0 or abs((max(pw) + min(pw)) / 2.0) > 300.0:
            continue
        pts = [(_dot(_sub(q, origem), u) - u0 + dx, _dot(_sub(q, origem), v) - v0 + dy) for q in vs]
        if max(q[0] for q in pts) < bx0 or min(q[0] for q in pts) > bx1 or max(q[1] for q in pts) < by0 or min(q[1] for q in pts) > by1:
            continue
        if max(math.dist(q0, q1) for q0 in pts[:1] for q1 in pts) < 150.0 and not _tipo_ifc(ent).startswith("IfcPlate"):
            continue                                          # porca, arruela
        # a peça muito mais alta que o conjunto (o tirante de 3,7 m na ponta da viga-caixa de 250 mm do Vicente,
        # 08/10) não é o montante da ponta: desenhada inteira, esticava a célula e a reduzia de escala
        alt_c = (by1 - by0) - 2 * perto
        if max(q[1] for q in pts) - min(q[1] for q in pts) > max(2.0 * alt_c, alt_c + 1000.0):
            continue
        c_ = _casco(pts)
        if len(c_) < 3 or min(_dist_ponto_seg(q, casco[i], casco[(i + 1) % len(casco)])
                               for q in c_ for i in range(len(casco))) > perto:
            continue
        if all(_trecho_dentro(q, q, casco, 0.0) is not None for q in c_):
            continue                                          # dentro do contorno da tesoura: já aparece nela
        cand.append((ent, c_))
    # só a peça em pé na ponta da tesoura (o montante lateral) e as chapas do conjunto dela: as terças de
    # parede no plano da tesoura do oitão, deitadas, não entram
    u_min, u_max = min(q[0] for q in casco), max(q[0] for q in casco)
    em_pe = []
    for ent, c_ in cand:
        us_, vs_ = [q[0] for q in c_], [q[1] for q in c_]
        meio = (min(us_) + max(us_)) / 2.0
        if not _tipo_ifc(ent).startswith("IfcPlate") and max(vs_) - min(vs_) > 2.0 * (max(us_) - min(us_)) \
                and (meio < u_min + 150.0 or meio > u_max - 150.0):
            em_pe.append(ent)
    conj_ok = {str(_marcas(e).get("conjunto") or "") for e in em_pe} - {""}
    ids_ok = {e.id for e in em_pe}
    for ent, c_ in cand:
        if ent.id in ids_ok or (_tipo_ifc(ent).startswith("IfcPlate") and str(_marcas(ent).get("conjunto") or "") in conj_ok):
            saida.append((ent.id, str(_marcas(ent).get("posicao") or ""), c_))
    return saida


def _cortes_das_tercas(doc: Documento, instancia: Sequence, origem, u, v, w, u0: float, v0: float,
                       segs_bz: Sequence[tuple], dx: float, dy: float,
                       com_telha: bool = True) -> Tuple[List[tuple], List[List[tuple]], List[tuple]]:
    """O que o plano da tesoura (o do meio da instância) corta em volta dela, como no corte das
    tesouras do projetista: (segmentos das terças, polilinhas da telha), já na célula.

    Terça: a peça fora da tesoura, comprida na direção do plano (atravessa, ou termina a até 300 mm
    dele — a emendada em cima da tesoura), de frente para ele (a peça toda cabe em 600 mm no
    desenho: a mão-francesa e a corrente inclinadas não entram), seção de 25 a 400 mm, encostada por
    fora no contorno da tesoura (até 400 mm): as de cima do banzo, as da cumeeira e as de parede ao
    lado do pilar. Cada face da malha cortada dá um segmento.

    Telha (camada de telhas): só o contorno de baixo, o lado virado para a estrutura, numa polilinha
    — para ver se a telha pega na estrutura (pedido do usuário, 28/09)."""
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
        if eh_telha and not com_telha:
            continue
        if eh_telha:
            m_onda = re.search(r"TP\s*(\d+)", str(_marcas(ent).get("perfil") or getattr(ent, "nome", "") or "").upper())
            if m_onda:
                ondas.append(float(m_onda.group(1)))
        try:
            vs, fs = _malha_guardada(ent)
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
