# -*- coding: utf-8 -*-
"""O 3D pelos quadros da Montagem (plano de 01/10, etapa 6).

Depois da leitura (`leitura_quadros.ler`) e da pré-análise, cada quadro de tesoura é um elemento
único — o bloco: todas as tesouras do mesmo tipo são cópias dele, colocadas pela planta da posição
das tesouras (cada marca T01… em cima da linha dela). Corrigir o quadro corrige todas.

Na montagem entram as regras acertadas na portaria do Projeto Hermes (30/09):

* o banzo em U deitado com as abas para dentro da treliça; o montante de linha dupla no perfil do
  banzo; a cantoneira da alma DUPLA, soldada nas paredes do U, quando o banzo é U;
* o encaixe de fábrica da alma (corte no ângulo, bico no montante: `alma_na_face.encaixar`);
* as terças pela planta das terças (sigla → perfil da lista), apoiadas no banzo de cima;
* os suportes e os contraventos pelas variantes escolhidas no banco de detalhes (ST1, SC1…);
* os pilares pela locação (trazida para a planta pelos nomes em comum): de concreto só apoio
  (fora do cálculo), metálicos como barra, da base ao topo do corte (ou dos parâmetros).

O modelo fica perto da origem: `deslocamento` diz quanto foi somado às coordenadas da Original.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional, Tuple

from nucleo3d import leitura_quadros as lq

__all__ = ["gerar"]

ACO = "ASTM A36"


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _unit2(a, b):
    L = math.dist(a, b) or 1.0
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L), L


class _Montador:
    def __init__(self, doc, desl):
        from nucleo3d import geometria as G
        self.G = G
        self.doc = doc
        self.desl = desl
        self.pecas: List[dict] = []
        self._cache: Dict[tuple, Tuple[float, float]] = {}

    def P(self, x, y, z):
        return (round(x + self.desl[0], 1), round(y + self.desl[1], 1), round(z, 1))

    def barra(self, p0, p1, perfil, papel, camada, conj, rot=0.0, origem=None, **attrs):
        from nucleo3d.modelo import Barra
        if math.dist(p0, p1) < 5.0:
            return None
        b = Barra(nome=perfil, inicio=tuple(round(c, 1) for c in p0), fim=tuple(round(c, 1) for c in p1),
                  perfil=perfil, rotacao=rot, papel=papel, aco=ACO, camada=camada)
        b.atributos = {"tipo_ifc": b.tipo_ifc(), "origem": dict(origem or {}, peca=conj)}
        b.atributos.update(attrs)
        self.doc.add(b)
        self.pecas.append({"perfil": perfil, "L": math.dist(p0, p1), "conj": conj, "papel": papel})
        return b

    def projecoes(self, perf, rot, q0, q1, n):
        """(mín, máx) da seção ao longo de n, com a barra de q0 a q1 passando pela origem"""
        from nucleo3d.modelo import Barra
        d = [q1[i] - q0[i] for i in range(3)]
        chave = (perf, rot, tuple(round(c, 3) for c in d), tuple(round(c, 4) for c in n))
        if chave not in self._cache:
            v, _f = self.G.malha_barra(Barra(inicio=(0.0, 0.0, 0.0), fim=tuple(d), perfil=perf, rotacao=rot))
            pr = [sum(p_[i] * n[i] for i in range(3)) for p_ in v]
            self._cache[chave] = (min(pr), max(pr))
        return self._cache[chave]

    def colocar(self, el, conj, P, origem=None):
        """o bloco da tesoura: P(s, h) → ponto 3D (a regra da portaria, 30/09)"""
        G = self.G
        p_b = (el.banzo or {}).get("perfil")
        p_a = (el.alma or {}).get("perfil") or p_b
        hs = [h for m in el.membros if m.papel == "banzo" for h in (m.h0, m.h1)]
        meio = (min(hs) + max(hs)) / 2 if hs else 0.0
        a0, a1 = P(0.0, 0.0), P(1000.0, 0.0)
        ex = [(a1[i] - a0[i]) / 1000.0 for i in range(3)]
        ez = [0.0, 0.0, 1.0]
        try:
            pb = G.resolver_perfil(p_b)
            u_banzo = pb.tipo in ("U", "Ue")
        except Exception:
            pb, u_banzo = None, False
        try:
            l_alma = G.resolver_perfil(p_a).tipo == "L" if p_a != p_b else False
        except Exception:
            l_alma = False

        def normal_no_plano(q0, q1):
            d = [q1[i] - q0[i] for i in range(3)]
            L = math.sqrt(sum(c * c for c in d)) or 1.0
            d = [c / L for c in d]
            base = ez if abs(d[2]) < 0.95 else ex
            k = sum(base[i] * d[i] for i in range(3))
            n = [base[i] - k * d[i] for i in range(3)]
            Ln = math.sqrt(sum(c * c for c in n)) or 1.0
            return [c / Ln for c in n]

        def mover(q, n, dist):
            return tuple(q[i] + n[i] * dist for i in range(3))

        def centro(perf, rot, q0, q1, n):
            lo, hi = self.projecoes(perf, rot, q0, q1, n)
            return (lo + hi) / 2.0

        for m in el.membros:
            q0, q1 = P(m.s0, m.h0), P(m.s1, m.h1)
            n = normal_no_plano(q0, q1)
            if m.papel == "banzo":
                rot = 270.0 if (m.h0 + m.h1) / 2 > meio else 90.0
                c = centro(p_b, rot, q0, q1, n)
                self.barra(mover(q0, n, -c), mover(q1, n, -c), p_b, "banzo", "Treliças", conj, rot, origem)
            elif getattr(m, "moldura", False) or (m.altura_linha > 0 and m.papel == "montante"):
                c = centro(p_b, 0.0, q0, q1, n)
                self.barra(mover(q0, n, -c), mover(q1, n, -c), p_b, "montante", "Treliças", conj, 0.0, origem)
            elif u_banzo and l_alma:
                # a cantoneira dupla, soldada nas paredes do U: uma de cada lado, dentro da boca do banzo
                dentro = pb.d / 2.0 - pb.tw
                e = [ex[1] * ez[2] - ex[2] * ez[1], ex[2] * ez[0] - ex[0] * ez[2], ex[0] * ez[1] - ex[1] * ez[0]]
                for lado in (1.0, -1.0):
                    melhor = None
                    for rot in (0.0, 90.0, 180.0, 270.0):
                        lo_e, hi_e = self.projecoes(p_a, rot, q0, q1, e)
                        lo_n, hi_n = self.projecoes(p_a, rot, q0, q1, n)
                        nota = (hi_e if lado > 0 else -lo_e) + hi_n
                        if melhor is None or nota < melhor[0] - 1e-6:
                            melhor = (nota, rot, lo_e, hi_e, lo_n, hi_n)
                    _s, rot, lo_e, hi_e, lo_n, hi_n = melhor
                    off_e = lado * dentro - (hi_e if lado > 0 else lo_e)
                    off_n = -(lo_n + hi_n) / 2.0
                    self.barra(mover(mover(q0, e, off_e), n, off_n), mover(mover(q1, e, off_e), n, off_n), p_a, m.papel,
                               "Treliças", conj, rot, dict(origem or {}, nota="L dupla soldada nas paredes do U"))
            else:
                self.barra(q0, q1, p_a, m.papel, "Treliças", conj, 0.0, origem)


def _altura_topo(el, s: float) -> Optional[float]:
    """o eixo do banzo de cima em s (o mais alto que passa ali)"""
    hs = []
    for m in el.membros:
        if m.papel != "banzo":
            continue
        lo, hi = min(m.s0, m.s1), max(m.s0, m.s1)
        if lo - 1.0 <= s <= hi + 1.0 and hi - lo > 1.0:
            t = (s - m.s0) / (m.s1 - m.s0)
            hs.append(m.h0 + (m.h1 - m.h0) * t)
    return max(hs) if hs else None


def _profundidade(el, s: float) -> float:
    """a altura da peça em s: do banzo mais baixo ao mais alto que passam ali"""
    hs = []
    for m in el.membros:
        if m.papel != "banzo":
            continue
        lo, hi = min(m.s0, m.s1), max(m.s0, m.s1)
        if lo - 1.0 <= s <= hi + 1.0 and hi - lo > 1.0:
            t = (s - m.s0) / (m.s1 - m.s0)
            hs.append(m.h0 + (m.h1 - m.h0) * t)
    return (max(hs) - min(hs)) if len(hs) >= 2 else 0.0


def _meia_linha(el, de_cima: bool) -> float:
    """a metade da altura desenhada do banzo (a linha dupla do U deitado)"""
    bz = [m for m in el.membros if m.papel == "banzo" and m.altura_linha > 0]
    if not bz:
        return 20.0
    hs = [(m.h0 + m.h1) / 2 for m in bz]
    meio = (min(hs) + max(hs)) / 2
    esc = [m for m in bz if ((m.h0 + m.h1) / 2 > meio) == de_cima] or bz
    return sum(m.altura_linha for m in esc) / len(esc) / 2.0


def gerar(desenho: dict, parametros: Optional[dict] = None, pasta_dados: Optional[str] = None,
          leitura: Optional[dict] = None) -> dict:
    """{doc, resumo, avisos, leitura, deslocamento, niveis}"""
    from nucleo import banco_detalhes
    from nucleo3d import alma_na_face
    from nucleo3d.geometria import prisma
    from nucleo3d.modelo import Camada, Documento
    L = leitura or lq.ler(desenho, parametros)
    ref = L["referencia"]
    m_meta = ((desenho.get("metadados") or {}).get("montagem")) or {}
    escolhas = dict(m_meta.get("ligacoes") or {})
    avisos: List[str] = []
    par = dict(L.get("parametros") or {})
    base = float(ref.get("base") or 0.0)
    topo = ref.get("topo")
    if topo is None:
        topo = base + 4000.0
        avisos.append("sem o topo dos pilares: usei +%.2f m (base + 4,00) — gerado assim mesmo" % ((base + 4000.0) / 1000.0))
    topo = float(topo)
    por = {q["tipo"]: q for q in L["quadros"]}
    pos = (por.get("tesouras_pos") or {}).get("leitura") or {"marcas": [], "linhas": []}
    ter = (por.get("tercas") or {}).get("leitura") or {"marcas": [], "linhas": [], "tabela": {}, "contraventos": []}
    loc = (por.get("locacao") or {}).get("leitura") or {"pilares": [], "eixos": []}
    els = L["elevacoes"]
    # o modelo perto da origem: o canto de baixo à esquerda da planta das tesouras
    xs = [p for l in pos["linhas"] for p in (l["a"][0], l["b"][0])] or [p for l in ter["linhas"] for p in (l["a"][0], l["b"][0])] or [0.0]
    ys = [p for l in pos["linhas"] for p in (l["a"][1], l["b"][1])] or [p for l in ter["linhas"] for p in (l["a"][1], l["b"][1])] or [0.0]
    desl = (-round(min(xs)), -round(min(ys)))
    doc = Documento(nome="Montagem pelos quadros")
    for nome_c, cor in (("Treliças", "#4b5563"), ("Terças", "#0b3d91"), ("Suportes", "#c9a227"),
                        ("Contraventamento", "#2e8b57"), ("Pilares", "#6b7280"), ("Concreto (apoio)", "#b9b2a6")):
        doc.camadas[nome_c] = Camada(nome=nome_c, cor=cor)
    M = _Montador(doc, desl)
    contagem = collections.Counter()
    # ------------------------------------------------------------ as tesouras
    marcas = pos["marcas"]
    if marcas:
        cx = sum(mk["posicao"][0] for mk in marcas) / len(marcas)
        cy = sum(mk["posicao"][1] for mk in marcas) / len(marcas)
    else:
        cx = cy = 0.0
    colocadas = []          # (a, b no plano, el, z0, s0 do bloco na linha, sentido)
    usadas = set()
    # as peças de cada linha, em ordem: as que somam o comprimento da linha vão encostadas uma na outra
    # (T04 + T03 + T04 na linha da ponta); senão a primeira e a última encostam nas pontas da linha quando a
    # marca está perto delas e as do meio ficam no meio do vão que sobra
    pos_na_linha: Dict[int, Dict[int, float]] = {}
    por_linha: Dict[int, List[int]] = collections.defaultdict(list)
    for k, mk in enumerate(marcas):
        if "linha" in mk and mk["nome"] in els:
            por_linha[mk["linha"]].append(k)
    for li_k, ks in por_linha.items():
        li = pos["linhas"][li_k]
        Ll = math.dist(li["a"], li["b"])
        ks.sort(key=lambda k: marcas[k]["t"])
        Ls = [els[marcas[k]["nome"]].comprimento for k in ks]
        tot = sum(Ls)
        t0s: Dict[int, float] = {}
        if len(ks) > 1 and abs(tot - Ll) <= 0.05 * Ll:
            folga = (Ll - tot) / len(ks)
            acc = folga / 2.0
            for k, Le in zip(ks, Ls):
                t0s[k] = acc
                acc += Le + folga
        else:
            ini, fim = 0.0, Ll
            if len(ks) > 1 and marcas[ks[0]]["t"] < Ls[0]:
                t0s[ks[0]] = 0.0
                ini = Ls[0]
            if len(ks) > 1 and Ll - marcas[ks[-1]]["t"] < Ls[-1]:
                t0s[ks[-1]] = Ll - Ls[-1]
                fim = Ll - Ls[-1]
            meio = [(k, Le) for k, Le in zip(ks, Ls) if k not in t0s]
            if len(meio) == 1 and len(ks) > 1:
                k, Le = meio[0]
                t0s[k] = ini + (fim - ini - Le) / 2.0
        pos_na_linha[li_k] = t0s
    for k_m, mk in enumerate(marcas):
        nome = mk["nome"]
        el = els.get(nome)
        if el is None:
            avisos.append("%s: sem quadro de tesoura — não colocada" % nome)
            continue
        if "linha" not in mk:
            avisos.append("%s em (%.0f, %.0f): sem linha de tesoura na planta — não colocada" % (nome, mk["posicao"][0], mk["posicao"][1]))
            continue
        li = pos["linhas"][mk["linha"]]
        a, b = tuple(li["a"]), tuple(li["b"])
        (ux, uy), Ll = _unit2(a, b)
        Le = el.comprimento
        # a peça na linha: a linha inteira quando tem o tamanho dela; senão centrada na marca, dentro da linha
        if k_m in pos_na_linha.get(mk["linha"], {}):
            t0 = pos_na_linha[mk["linha"]][k_m]
        elif abs(Ll - Le) <= 0.1 * Le:
            t0 = (Ll - Le) / 2.0
        else:
            t0 = min(max(mk["t"] - Le / 2.0, 0.0), max(Ll - Le, 0.0)) if Ll >= Le else (Ll - Le) / 2.0
            avisos.append("%s: linha da planta com %.0f mm e elevação com %.0f mm — %s" % (
                nome, Ll, Le, "centrada na marca" if Ll >= Le else "centrada na linha (passa das pontas)"))
        chave = (mk["linha"], round(t0))
        if chave in usadas:
            continue                                  # duas marcas na mesma peça
        usadas.add(chave)
        # o sentido: a ponta mais funda (a raiz da asa, onde a peça apoia) para o lado de dentro da planta
        # (o meio das marcas); a peça simétrica fica como a linha vai
        h_ini = _profundidade(el, min(150.0, Le / 4))
        h_fim = _profundidade(el, max(Le - 150.0, Le * 3 / 4))
        p_ini = (a[0] + ux * t0, a[1] + uy * t0)
        p_fim = (a[0] + ux * (t0 + Le), a[1] + uy * (t0 + Le))
        sentido = 1.0
        if abs(h_ini - h_fim) > 100.0:
            alta_fim = h_fim > h_ini
            fim_dentro = math.dist(p_fim, (cx, cy)) < math.dist(p_ini, (cx, cy))
            if alta_fim != fim_dentro:
                sentido = -1.0
        z0 = topo + _meia_linha(el, False)
        contagem[nome] += 1
        conj = "%s#%d" % (nome, contagem[nome])
        if sentido > 0:
            def P(s, h, a=a, ux=ux, uy=uy, t0=t0, z0=z0):
                return M.P(a[0] + ux * (t0 + s), a[1] + uy * (t0 + s), z0 + h)
        else:
            def P(s, h, a=a, ux=ux, uy=uy, t0=t0, z0=z0, Le=Le):
                return M.P(a[0] + ux * (t0 + Le - s), a[1] + uy * (t0 + Le - s), z0 + h)
        M.colocar(el, conj, P, {"planta": nome, "quadro": "tesoura " + nome})
        colocadas.append({"a": a, "u": (ux, uy), "t0": t0, "Le": Le, "sentido": sentido, "el": el, "z0": z0, "nome": nome})
    for nome, el in els.items():
        if contagem.get(nome, 0) == 0:
            avisos.append("tesoura %s lida e sem marca na planta: não entrou no modelo" % nome)
    # ------------------------------------------------------------ terças
    def topo_no_ponto(p) -> Optional[Tuple[float, dict]]:
        """(z do eixo do banzo de cima, a tesoura) onde o ponto da planta cai sobre uma tesoura colocada"""
        melhor = None
        for c in colocadas:
            a, (ux, uy) = c["a"], c["u"]
            t = (p[0] - a[0]) * ux + (p[1] - a[1]) * uy
            d = abs(-(p[0] - a[0]) * uy + (p[1] - a[1]) * ux)
            s = t - c["t0"]
            if c["sentido"] < 0:
                s = c["Le"] - s
            if -150.0 <= s <= c["Le"] + 150.0 and d < 400.0:
                h = _altura_topo(c["el"], min(max(s, 0.0), c["Le"]))
                if h is not None and (melhor is None or d < melhor[0]):
                    melhor = (d, c["z0"] + h + _meia_linha(c["el"], True), c)
        return (melhor[1], melhor[2]) if melhor else None

    sigla_da_linha: Dict[int, str] = {}
    for mk in ter.get("marcas") or []:
        if "linha" in mk:
            sigla_da_linha.setdefault(mk["linha"], mk["sigla"])
    padrao_terca = next((it.get("perfil") for it in (ter.get("tabela") or {}).values() if it.get("perfil")), None)
    var_st = banco_detalhes.variante(escolhas.get("suporte_terca"), pasta_dados) if escolhas.get("suporte_terca") else None
    n_terca = n_st = 0
    sem_apoio = 0
    feitos_st = set()
    for i, li in enumerate(ter.get("linhas") or []):
        a, b = tuple(li["a"]), tuple(li["b"])
        sig = sigla_da_linha.get(i)
        perfil = ((ter.get("tabela") or {}).get(sig) or {}).get("perfil") or padrao_terca
        if not perfil:
            avisos.append("terça %s sem perfil (nem na lista): não entrou" % (sig or "sem sigla"))
            continue
        apoios = []
        (ux, uy), Lt = _unit2(a, b)
        for c in colocadas:
            # o cruzamento da linha da terça com a peça colocada (as duas um pouco esticadas: a terça de vão
            # em vão para na face da tesoura): a + u·tt = c.a + v·sl
            (vx, vy) = c["u"]
            D = -ux * vy + vx * uy
            if abs(D) < 1e-6:
                continue
            wx, wy = c["a"][0] - a[0], c["a"][1] - a[1]
            tt = (-wx * vy + wy * vx) / D
            sl = (ux * wy - uy * wx) / D
            if not (-150.0 <= tt <= Lt + 150.0 and c["t0"] - 150.0 <= sl <= c["t0"] + c["Le"] + 150.0):
                continue
            s = sl - c["t0"] if c["sentido"] > 0 else c["Le"] - (sl - c["t0"])
            h = _altura_topo(c["el"], min(max(s, 0.0), c["Le"]))
            if h is not None:
                z_ap = c["z0"] + h + _meia_linha(c["el"], True)
                # a terça desenhada na elevação (o corte dela em cima do banzo): o pé dela manda
                td = [hh for ss, hh in getattr(c["el"], "tercas_des", None) or [] if abs(ss - s) < 150.0]
                apoios.append((min(max(tt, 0.0), Lt), z_ap, c, (c["z0"] + min(td)) if td else None))
        if not apoios:
            sem_apoio += 1
            continue
        pes_des = [zd for _t, _z, _c, zd in apoios if zd is not None]
        z_pe = (sum(pes_des) / len(pes_des)) if pes_des else max(z for _t, z, _c, _zd in apoios)
        try:
            from nucleo3d.geometria import resolver_perfil
            d_t = float(resolver_perfil(perfil).d or 100.0)
        except Exception:
            d_t = 100.0
        z = z_pe + d_t / 2.0
        # as peças: cada marca TC é uma peça; a linha com várias marcas se corta na tesoura mais perto do meio
        # entre duas marcas vizinhas (a planta desenha a linha inteira, a lista conta as peças)
        ms = sorted((mk for mk in ter.get("marcas") or [] if mk.get("linha") == i), key=lambda mk: mk["t"])
        cruz = sorted({round(tt, 1) for tt, _z, _c, _zd in apoios})
        cortes = []
        for m1, m2 in zip(ms, ms[1:]):
            meio_t = (m1["t"] + m2["t"]) / 2.0
            dentro = [c_ for c_ in cruz if m1["t"] < c_ < m2["t"]]
            cortes.append(min(dentro, key=lambda c_: abs(c_ - meio_t)) if dentro else meio_t)
        pontas = [0.0] + cortes + [Lt]
        siglas = [mk["sigla"] for mk in ms] or [sig]
        for k, (t_a, t_b) in enumerate(zip(pontas, pontas[1:])):
            sg = siglas[k] if k < len(siglas) else sig
            pf = ((ter.get("tabela") or {}).get(sg) or {}).get("perfil") or perfil
            q0 = M.P(a[0] + ux * t_a, a[1] + uy * t_a, z)
            q1 = M.P(a[0] + ux * t_b, a[1] + uy * t_b, z)
            # o lado do suporte pela elevação (de que lado da terça desenhada ela desenha o suporte): a alma da
            # terça virada para ele — a terça vai no sentido que põe a alma desse lado (portaria, 30/09)
            voto = 0.0
            for tt, _z, c, _zd in apoios:
                if t_a - 150.0 <= tt <= t_b + 150.0:
                    voto += _lado_desenhado(c, (a[0] + ux * tt, a[1] + uy * tt), (-uy, ux))
            if voto and _lado_da_alma(M, pf, 0.0, (ux, uy)) * voto < 0:
                q0, q1 = q1, q0
            # a seção centrada nas duas linhas desenhadas da terça (o eixo do perfil não fica no meio da Ue)
            nn = [-(q1[1] - q0[1]), q1[0] - q0[0], 0.0]
            Ln = math.hypot(nn[0], nn[1]) or 1.0
            nn = [nn[0] / Ln, nn[1] / Ln, 0.0]
            lo_n, hi_n = M.projecoes(pf, 0.0, q0, q1, nn)
            off = -(lo_n + hi_n) / 2.0
            q0 = (q0[0] + nn[0] * off, q0[1] + nn[1] * off, q0[2])
            q1 = (q1[0] + nn[0] * off, q1[1] + nn[1] * off, q1[2])
            tb = M.barra(q0, q1, pf, "terça", "Terças", sg or "TERÇA", 0.0, {"sigla": sg})
            if tb is None:
                continue
            n_terca += 1
            contagem["TERÇA " + (sg or "?")] += 1
            comp_lista = ((ter.get("tabela") or {}).get(sg) or {}).get("comp")
            if comp_lista and abs(comp_lista - (t_b - t_a)) > 30.0:
                avisos.append("%s: na lista %.0f mm, na planta %.0f mm" % (sg, comp_lista, t_b - t_a))
            # os suportes da variante escolhida, em cada tesoura que a peça cruza ou onde ela para
            if var_st:
                vistos = set()
                for tt, z_ap, c, _zd in apoios:
                    if not (t_a - 150.0 <= tt <= t_b + 150.0):
                        continue
                    # na emenda sobre a tesoura o suporte é um só (as duas peças apoiam nele)
                    # um suporte por ponto da tesoura (as terças dos dois vãos chegam no mesmo)
                    (vx, vy) = c["u"]
                    kk = (id(c), round(((a[0] + ux * tt - c["a"][0]) * vx + (a[1] + uy * tt - c["a"][1]) * vy) / 100.0))
                    sd = getattr(c["el"], "suportes_des", None) or []
                    na_ponta = min(abs(tt - t_a), abs(tt - t_b)) < 200.0
                    if sd and not na_ponta:
                        # o projeto desenha os suportes na elevação: só onde ele desenha (na ponta da peça —
                        # a emenda e o fim da terça — o suporte vai sempre)
                        (vx, vy) = c["u"]
                        sl = (a[0] + ux * tt - c["a"][0]) * vx + (a[1] + uy * tt - c["a"][1]) * vy
                        s_ = sl - c["t0"] if c["sentido"] > 0 else c["Le"] - (sl - c["t0"])
                        if min(abs(s_ - x) for x in sd) > 150.0:
                            continue
                    if kk in vistos or kk in feitos_st:
                        continue
                    vistos.add(kk)
                    feitos_st.add(kk)
                    n_st += _suporte_de_terca(M, var_st, tb, c, (a[0] + ux * tt, a[1] + uy * tt), z - d_t / 2.0)
    if sem_apoio:
        avisos.append("%d terça(s) sem tesoura embaixo (nem nas pontas): não entraram" % sem_apoio)
    # ------------------------------------------------------------ contraventos
    var_cv = banco_detalhes.variante(escolhas.get("suporte_contravento"), pasta_dados) if escolhas.get("suporte_contravento") else None
    n_cv = n_sc = 0
    p_barra_cv = None
    from nucleo2d.reconhecer import perfil_do_texto
    r_cv = perfil_do_texto(((var_cv or {}).get("colocacao") or {}).get("barra") or 'Ø1/2"')
    p_barra_cv = (r_cv or {}).get("perfil") or 'Barra redonda ø 1/2"'
    col_cv = (var_cv or {}).get("colocacao") or {}
    usa_sc = bool(var_cv) and str(col_cv.get("peca") or "").startswith("L")
    for li in ter.get("contraventos") or []:
        a, b = tuple(li["a"]), tuple(li["b"])
        ra, rb = topo_no_ponto(a), topo_no_ponto(b)
        if not ra or not rb:
            avisos.append("contravento em (%.0f, %.0f)–(%.0f, %.0f) com ponta fora das tesouras: não entrou" % (a[0], a[1], b[0], b[1]))
            continue
        if usa_sc:
            r_sc = _contravento_com_sc(M, var_cv, (a, ra), (b, rb), p_barra_cv)
            n_cv += 1
            n_sc += r_sc
            continue
        q0, q1 = M.P(a[0], a[1], ra[0]), M.P(b[0], b[1], rb[0])
        M.barra(q0, q1, p_barra_cv, "contraventamento", "Contraventamento", "CV", 0.0, {"planta": "CV"},
                variante=(var_cv or {}).get("id"))
        n_cv += 1
    # ------------------------------------------------------------ pilares
    al = ref.get("locacao") or {"dx": 0.0, "dy": 0.0}
    n_p = 0
    var_base = banco_detalhes.variante(escolhas.get("base_pilar"), pasta_dados) if escolhas.get("base_pilar") else None
    for p in loc.get("pilares") or []:
        x, y = p["posicao"][0] + al["dx"], p["posicao"][1] + al["dy"]
        if p.get("perfil"):
            M.barra(M.P(x, y, base), M.P(x, y, topo), p["perfil"], "pilar", "Pilares", p["nome"], 0.0, {"planta": p["nome"]},
                    marca=p["nome"], variante_base=(var_base or {}).get("id"))
            n_p += 1
            continue
        contorno = p.get("contorno")
        if isinstance(contorno, dict) and contorno.get("raio"):
            r = contorno["raio"]
            cantos = [M.P(x + r * math.cos(2 * math.pi * i / 24), y + r * math.sin(2 * math.pi * i / 24), base) for i in range(24)]
            sec = "Ø%.0f cm" % (2 * r / 10.0)
        elif isinstance(contorno, list) and len(contorno) >= 4:
            vs = contorno[:-1] if contorno[0] == contorno[-1] else contorno
            ox, oy = x - p["posicao"][0], y - p["posicao"][1]
            cantos = [M.P(v[0] + ox, v[1] + oy, base) for v in vs]
            sec = p.get("secao") or "contorno da locação"
        elif p.get("concreto") and len(p["concreto"]) == 1:
            r = p["concreto"][0] / 2.0
            cantos = [M.P(x + r * math.cos(2 * math.pi * i / 24), y + r * math.sin(2 * math.pi * i / 24), base) for i in range(24)]
            sec = "Ø%.0f cm" % (2 * r / 10.0)
        elif p.get("concreto"):
            w, h = p["concreto"]
            cantos = [M.P(x - w / 2, y - h / 2, base), M.P(x + w / 2, y - h / 2, base), M.P(x + w / 2, y + h / 2, base), M.P(x - w / 2, y + h / 2, base)]
            sec = "%s cm" % p.get("secao")
        else:
            avisos.append("%s sem seção nem contorno: não entrou" % p["nome"])
            continue
        sol = prisma(cantos, (0.0, 0.0, topo - base))
        sol.nome = "%s — concreto %s (apoio)" % (p["nome"], sec)
        sol.camada = "Concreto (apoio)"
        sol.material = "Concreto"
        sol.atributos = {"tipo_ifc": "IfcColumn", "marca": p["nome"], "concreto": True, "calcular": False, "secao": sec,
                         "nota": "pilar de concreto de outros: só apoio da estrutura metálica, fora do cálculo e da lista de aço"}
        doc.add(sol)
        n_p += 1
    # ------------------------------------------------------------ o encaixe de fábrica da alma
    try:
        enc = alma_na_face.encaixar([b for b in doc.barras])
    except Exception as ex:                          # a leitura estranha fica como está, avisada
        enc = {}
        avisos.append("encaixe de fábrica da alma não aplicado: %s" % ex)
    resumo = {
        "tesouras": dict((k, v) for k, v in contagem.items() if not k.startswith("TERÇA ")),
        "tercas": n_terca, "suportes_terca": n_st, "contraventos": n_cv, "suportes_contravento": n_sc, "pilares": n_p,
        "barras": len(doc.barras), "entidades": len(doc.entidades), "encaixe": enc,
        "variantes": {k: v for k, v in escolhas.items() if v}, "base": base, "topo": topo,
        "deslocamento_mm": list(desl),
    }
    # a conferência projeto × modelo (como na portaria): o título e a lista do projeto, as marcas da planta e o modelo
    conf = []
    for q_ in L["quadros"]:
        lt_ = q_.get("leitura") or {}
        if q_["tipo"] in lq.COM_NOME and lt_.get("nome"):
            nome = lt_["nome"]
            conf.append({"peca": nome, "projeto": lt_.get("qtd"), "planta": (pos.get("contagem") or {}).get(nome, 0),
                         "modelo": contagem.get(nome, 0)})
    for sig, it in sorted((ter.get("tabela") or {}).items()):
        conf.append({"peca": sig, "projeto": it.get("qtd"), "planta": (ter.get("contagem") or {}).get(sig, 0),
                     "modelo": contagem.get("TERÇA " + sig, 0)})
    for c_ in conf:
        c_["confere"] = c_["modelo"] == (c_["projeto"] if c_["projeto"] is not None else c_["planta"])
    resumo["conferencia"] = conf
    niveis = [{"nome": "BASE DOS PILARES", "z": base}, {"nome": "TOPO DOS PILARES", "z": topo}]
    return {"doc": doc, "resumo": resumo, "avisos": avisos, "leitura": L, "deslocamento": desl, "niveis": niveis}


def _lado_da_alma(M, perfil, rot, d2) -> float:
    """de que lado (+1: o de n = (−dy, dx)) fica a alma da terça que vai na direção d2: a face mais alta"""
    from nucleo3d.modelo import Barra
    nx, ny = -d2[1], d2[0]
    try:
        v, _f = M.G.malha_barra(Barra(inicio=(0.0, 0.0, 0.0), fim=(d2[0] * 1000.0, d2[1] * 1000.0, 0.0), perfil=perfil, rotacao=rot))
    except Exception:
        return -1.0
    pr = [(p_[0] * nx + p_[1] * ny, p_[2]) for p_ in v]
    lo, hi = min(x for x, _z in pr), max(x for x, _z in pr)
    a_lo = max(z for x, z in pr if x < lo + 3.0) - min(z for x, z in pr if x < lo + 3.0)
    a_hi = max(z for x, z in pr if x > hi - 3.0) - min(z for x, z in pr if x > hi - 3.0)
    return 1.0 if a_hi > a_lo else -1.0


def _lado_desenhado(c: dict, p_planta, n2) -> float:
    """de que lado da terça a elevação da tesoura `c` desenha o suporte, em n2 (±1, 0 se não desenha)"""
    el = c["el"]
    td = getattr(el, "tercas_des", None) or []
    sd = getattr(el, "suportes_des", None) or []
    if not td or not sd:
        return 0.0
    (vx, vy) = c["u"]
    sl = (p_planta[0] - c["a"][0]) * vx + (p_planta[1] - c["a"][1]) * vy
    s = sl - c["t0"] if c["sentido"] > 0 else c["Le"] - (sl - c["t0"])
    s_t = min((x for x, _h in td), key=lambda x: abs(x - s))
    if abs(s_t - s) > 200.0:
        return 0.0
    s_s = min(sd, key=lambda x: abs(x - s_t))
    if abs(s_s - s_t) > 150.0 or abs(s_s - s_t) < 1.0:
        return 0.0
    # o sentido de s no plano: o da linha da tesoura (ou o contrário, se a peça foi virada)
    ds = (s_s - s_t) * c["sentido"]
    return 1.0 if (ds * (vx * n2[0] + vy * n2[1])) > 0 else -1.0


def _suporte_de_terca(M, var: dict, terca, c: dict, p_planta, z_banzo: float) -> int:
    """a cantoneira da variante (ST1) ao lado da terça, em cima do banzo da tesoura `c`: o pé no topo do
    banzo, a aba em pé encostada na alma da terça e a deitada para fora; centrada no eixo da tesoura"""
    col = var.get("colocacao") or {}
    from nucleo2d.reconhecer import perfil_do_texto
    r = lq.perfil_escrito(col.get("peca") or "") or perfil_do_texto(col.get("peca") or "")
    if not r:
        return 0
    perfil = r["perfil"]
    comp = float(col.get("comprimento") or 120.0)
    a3, b3 = terca.inicio, terca.fim
    (dx, dy), _L = _unit2(a3, b3)
    nx, ny = -dy, dx                                            # o lado da terça (normal no plano)
    # a face da terça de cada lado e o lado da alma (a seção fica mais "cheia" do lado da alma)
    lo_t, hi_t = M.projecoes(terca.perfil, terca.rotacao, a3, b3, [nx, ny, 0.0])
    try:
        from nucleo3d.modelo import Barra
        v, _f = M.G.malha_barra(Barra(inicio=(0.0, 0.0, 0.0), fim=tuple(_sub(b3, a3)), perfil=terca.perfil, rotacao=terca.rotacao))
        pr = [(p_[0] * nx + p_[1] * ny, p_[2]) for p_ in v]
        alto_lo = max(z for n_, z in pr if n_ < lo_t + 3.0) - min(z for n_, z in pr if n_ < lo_t + 3.0)
        alto_hi = max(z for n_, z in pr if n_ > hi_t - 3.0) - min(z for n_, z in pr if n_ > hi_t - 3.0)
        lado = -1.0 if alto_lo >= alto_hi else 1.0              # a alma: o lado com a face mais alta
    except Exception:
        lado = -1.0
    face = hi_t if lado > 0 else lo_t
    # a cantoneira atravessada no banzo, paralela à terça (os 120 mm ao longo dela), centrada no eixo da tesoura:
    # a aba em pé encostada na alma da terça, a deitada para fora, o pé no topo do banzo (portaria, 30/09)
    px, py = p_planta[0] + M.desl[0], p_planta[1] + M.desl[1]
    ex_t = (px - a3[0]) * nx + (py - a3[1]) * ny
    px, py = px + nx * (face - ex_t), py + ny * (face - ex_t)
    q0 = (px - dx * comp / 2, py - dy * comp / 2, 0.0)
    q1 = (px + dx * comp / 2, py + dy * comp / 2, 0.0)
    w = [nx * lado, ny * lado, 0.0]                             # da terça para fora
    from nucleo3d.modelo import Barra
    melhor = None
    for rot in (0.0, 90.0, 180.0, 270.0):
        v, _f = M.G.malha_barra(Barra(inicio=(0.0, 0.0, 0.0), fim=tuple(_sub(q1, q0)), perfil=perfil, rotacao=rot))
        pw = [(p_[0] * w[0] + p_[1] * w[1], p_[2]) for p_ in v]
        lo_w, lo_z = min(x for x, _z in pw), min(z for _x, z in pw)
        alt_junto = max(z for x, z in pw if x < lo_w + 3.0) - lo_z           # a aba em pé junto da terça
        larg_pe = max(x for x, z in pw if z < lo_z + 3.0) - lo_w             # a aba deitada embaixo
        nota = 2.0 * alt_junto + larg_pe            # a aba maior em pé (os furos da alma da terça), a menor deitada
        if melhor is None or nota > melhor[0] + 1e-6:
            melhor = (nota, rot, lo_w, lo_z)
    _s, rot, lo_w, lo_z = melhor
    mv = [w[0] * (-lo_w), w[1] * (-lo_w), z_banzo - lo_z]
    q0 = tuple(q0[k] + mv[k] for k in range(3))
    q1 = tuple(q1[k] + mv[k] for k in range(3))
    b = M.barra(q0, q1, perfil, "suporte", "Suportes", var["id"], rot, {"sigla": var["id"], "variante": var["id"]},
                variante=var["id"], furos=col.get("furos"), parafuso=col.get("parafuso"))
    return 1 if b is not None else 0


def _contravento_com_sc(M, var: dict, ponta_a, ponta_b, p_barra) -> int:
    """o tirante entre dois suportes SC1 da variante (o detalhe da portaria, 30/09): em cada ponta a L em pé no
    topo do banzo de cima, centrada no banzo e girada no ângulo do tirante (a aba do furo em esquadro com a
    barra, o canto para fora), o furo a `furo_z` do pé; a barra reta entre os furos, passando `passa` de cada
    um (porca e rosca). Devolve quantos SC1 entraram."""
    import numpy as np
    from nucleo2d.reconhecer import perfil_do_texto
    from nucleo3d.modelo import Barra
    col = var.get("colocacao") or {}
    r = perfil_do_texto(col.get("peca") or "") or lq.perfil_escrito(col.get("peca") or "")
    if not r:
        return 0
    perfil = r["perfil"]
    alt = float(col.get("altura") or 90.0)
    fz = float(col.get("furo_z") or 45.0)
    passa = float(col.get("passa") or 40.0)
    try:
        pf = M.G.resolver_perfil(perfil)
        t_ = float(pf.tw or pf.tf or 4.76)
        aba = float(pf.bf or pf.d or 50.8)
    except Exception:
        t_, aba = 4.76, 50.8
    borda = aba / 2.0                                           # o furo no meio da aba
    cache = {}

    def secao(rot):
        rk = round(rot % 360.0, 2)
        if rk not in cache:
            cache[rk] = np.array(M.G.malha_barra(Barra(inicio=(0, 0, 0), fim=(0, 0, 100), perfil=perfil, rotacao=rk))[0])
        return rk, cache[rk]

    def pose(H, u_out):
        uh = np.array((u_out[0], u_out[1], 0.0))
        uh /= np.linalg.norm(uh)
        nh = np.array((-uh[1], uh[0], 0.0))

        def nota(rot):
            rk, v = secao(rot)
            pu, pn = v @ uh, v @ nh
            return (np.ptp(pu) + np.ptp(pn)) + 0.01 * (pu.max() - pn.min()), rk, pu.max(), pn.min()
        melhor = min((nota(x) for x in np.arange(0.0, 360.0, 0.5)), key=lambda x: x[0])
        melhor = min((nota(melhor[1] + dd) for dd in np.arange(-0.5, 0.51, 0.05)), key=lambda x: x[0])
        _s, rot, hi_u, lo_n = melhor
        eixo = H + uh * (-(hi_u - t_ / 2.0)) + nh * (-(lo_n + borda))
        v = secao(rot)[1] + eixo
        return rot, eixo, v

    # os furos: na ponta desenhada, no eixo da tesoura, a `fz` acima do topo do banzo de cima
    Hs, ns, axs = [], [], []
    for (p, (z_top, c)) in (ponta_a, ponta_b):
        (vx, vy) = c["u"]
        sl = (p[0] - c["a"][0]) * vx + (p[1] - c["a"][1]) * vy
        x_ax, y_ax = c["a"][0] + vx * sl + M.desl[0], c["a"][1] + vy * sl + M.desl[1]
        Hs.append(np.array((x_ax, y_ax, z_top + fz)))
        ns.append(np.array((-vy, vx, 0.0)))
        axs.append(np.array((x_ax, y_ax, 0.0)))
    # o conjunto (a L, o furo, a ponta do tirante) anda na normal da tesoura até o meio da L cair no eixo do banzo
    for _it in range(4):
        u = (Hs[1] - Hs[0]) / np.linalg.norm(Hs[1] - Hs[0])
        for k, u_out in ((0, -u), (1, u)):
            _rot, _eixo, v = pose(Hs[k], u_out)
            meio = (v.min(axis=0) + v.max(axis=0)) / 2.0
            desvio = float((axs[k] - meio) @ ns[k])
            Hs[k] = Hs[k] + ns[k] * desvio
    u = (Hs[1] - Hs[0]) / np.linalg.norm(Hs[1] - Hs[0])
    q0 = tuple(float(x) for x in Hs[0] - u * passa)
    q1 = tuple(float(x) for x in Hs[1] + u * passa)
    M.barra(q0, q1, p_barra, "contraventamento", "Contraventamento", "CV", 0.0, {"planta": "CV"},
            variante=var["id"], suporte="%s (furo Ø%.0f a %.0f mm do pé)" % (var["id"], float(col.get("furo_d") or 16.0), fz))
    n = 0
    for H, u_out in ((Hs[0], -u), (Hs[1], u)):
        rot, eixo, _v = pose(H, u_out)
        z0 = float(H[2]) - fz
        b = M.barra((float(eixo[0]), float(eixo[1]), z0), (float(eixo[0]), float(eixo[1]), z0 + alt), perfil, "suporte",
                    "Suportes", var["id"], round(float(rot), 2), {"sigla": var["id"], "variante": var["id"]},
                    variante=var["id"], marca=var["id"],
                    furo={"z": fz, "d": float(col.get("furo_d") or 16.0), "ponto": [round(float(x), 1) for x in H],
                          "eixo": [round(float(x), 5) for x in u_out]})
        n += 1 if b is not None else 0
    return n
