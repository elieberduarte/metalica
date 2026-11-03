# -*- coding: utf-8 -*-
"""A fundação sob o cálice: sapata rígida ou bloco sobre estacas (NBR 6118, 22.6 e 22.7; NBR 9062, 7.7).

O colarinho do cálice fica sobre a fundação e a base do pilar se apoia no topo dela (a espessura abaixo
da base do pilar ≥ 20 cm, NBR 9062, 7.7.5.1). A boca do cálice fica no nível do terreno.

* `distribuicao` — as tensões no contato com o solo (plano, sem tração) pelo método das áreas ativas:
  com a resultante no núcleo central é a fórmula da flexão composta; fora dele, só a parte comprimida;
* `sapata` — a menor sapata rígida (h ≥ (a − ap)/3, 22.6.1) em que a tensão máxima não passa da admissível
  e a área comprimida não fica abaixo da fração mínima, nas combinações características; a flexão na face
  do colarinho com a tração uniforme na largura (22.6.2.2 a), a compressão diagonal no contorno do
  colarinho (22.6.2.2 b e 19.5.3.1, com o momento de 19.5.2.2) e a pressão de contato da base do pilar
  (21.2.1);
* `bloco` — o bloco rígido sobre 2, 4 ou 6 estacas: as reações (característica ≤ carga admissível da
  estaca), as bielas do pilar a cada estaca com a inclinação de 22.3.1 (tg θ de 1 a 2), os tirantes sobre as
  estacas (22.7.2.1 a) e as tensões nos nós com os limites de 22.3.2 (fcd1 no nó do pilar, CCC; fcd3 no nó
  da estaca, CCT); armaduras de distribuição (22.7.4.1.2) e lateral/superior (22.7.4.1.5).

O que é da NBR 6122 (a tensão admissível do solo, a carga admissível da estaca, a fração mínima comprimida
da base, o espaçamento das estacas e a distância à borda) entra como dado da obra: a norma não está na
pasta Normas e os valores padrão ficam marcados como a conferir.

Unidades: cm, kN, kN·cm; tensões no solo em kPa na entrada e na saída.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from nucleo.base import ErroDeDados, Resultado, Verificacao, fmt

from . import nbr6118 as N6118
from .concreto import BITOLAS, AcoArmadura, Concreto, escolher_barras

PESO_CONCRETO = 25.0          # kN/m³
N_MALHA = 40                  # divisões da base em cada direção
FUNDO_MINIMO = 20.0           # cm abaixo da base do pilar (NBR 9062, 7.7.5.1)


@dataclass
class ParametrosFundacao:
    tipo: str = "sapata"                       # "sapata" | "estacas"
    sigma_adm: float = 200.0                   # kPa (sondagem — NBR 6122)
    fracao_comprimida: float = 2.0 / 3.0       # da área da base (a conferir — NBR 6122)
    peso_solo: float = 18.0                    # kN/m³
    cobrimento: float = 3.0                    # cm (em contato com o solo, NBR 6118 Tabela 7.2)
    estaca_diametro: float = 30.0              # cm
    estaca_carga: float = 300.0                # kN, compressão admissível (característica)
    estaca_tracao: float = 0.0                 # kN, tração admissível (característica)
    estaca_espacamento: float = 3.0            # × diâmetro, entre eixos (a conferir — NBR 6122)
    estaca_borda: float = 15.0                 # cm, da face da estaca à face do bloco (a conferir)


@dataclass
class Situacao:
    """uma combinação no topo da fundação (boca do cálice): N para baixo, os momentos e as cortantes
    em módulo, nas direções h (plano do pórtico) e b (longitudinal)"""
    nome: str
    N: float
    Mh: float
    Mb: float
    Vh: float = 0.0
    Vb: float = 0.0


# ------------------------------------------------------------------ as tensões na base

def distribuicao(ah: float, ab: float, N: float, Mh: float, Mb: float, n: int = N_MALHA):
    """as tensões (kN/cm²) na base ah × ab (cm) com a força N (kN, para baixo) e os momentos Mh (excentricidade
    na direção de ah) e Mb (kN·cm), o solo sem tração: devolve (fração comprimida, σmáx, σ na malha, X, Y)
    ou None se a resultante sai da base (tomba) ou N ≤ 0"""
    if N <= 0 or abs(Mh) / N >= ah / 2 or abs(Mb) / N >= ab / 2:
        return None
    xs = -ah / 2 + (np.arange(n) + 0.5) * ah / n
    ys = -ab / 2 + (np.arange(n) + 0.5) * ab / n
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    dA = ah * ab / n / n
    ativo = np.ones_like(X, dtype=bool)
    sig = None
    for _ in range(60):
        x, y = X[ativo], Y[ativo]
        A = np.array([[x.size, x.sum(), y.sum()], [x.sum(), (x * x).sum(), (x * y).sum()], [y.sum(), (x * y).sum(), (y * y).sum()]]) * dA
        try:
            p = np.linalg.solve(A, np.array([N, Mh, Mb]))
        except np.linalg.LinAlgError:
            return None
        sig = p[0] + p[1] * X + p[2] * Y
        novo = sig > 0
        if (novo == ativo).all():
            break
        ativo = novo
        if not ativo.any():
            return None
    sig = np.where(ativo, sig, 0.0)
    # o máximo do plano nos cantos da base (a malha lê no centro das células)
    cantos = max(p[0] + p[1] * sx * ah / 2 + p[2] * sy * ab / 2 for sx in (-1, 1) for sy in (-1, 1))
    return float(ativo.mean()), float(max(cantos, sig.max())), sig, X, Y


def _malha(As: float, largura: float, bitolas=(8.0, 10.0, 12.5, 16.0, 20.0)) -> Tuple[float, float, int]:
    """(ø, espaçamento cm, nº de barras) da armadura As (cm²) distribuída em `largura` (cm): o menor ø com
    espaçamento de 10 a 20 cm"""
    for fi in bitolas:
        a = BITOLAS[fi][0]
        n = max(math.ceil(As / a - 1e-9), 2)
        s = largura / n
        s = math.floor(s / 2.5) * 2.5
        if s >= 10.0:
            s = min(s, 20.0)
            return fi, s, max(math.ceil(largura / s), 2)
    fi = bitolas[-1]
    n = max(math.ceil(As / BITOLAS[fi][0] - 1e-9), 2)
    return fi, max(math.floor(largura / n / 2.5) * 2.5, 7.5), n


def _pressao_contato(Nd: float, b: float, h: float, ab: float, ah: float, conc: Concreto) -> Verificacao:
    """21.2.1: a base do pilar (b × h) no topo da fundação; Ac1 = a maior área semelhante inscrita"""
    Ac0 = b * h
    k = min(ab / b, ah / h, 3.3)
    FRd = Ac0 * conc.fcd * k
    v = Verificacao("Pressão de contato da base do pilar", norma="NBR 6118, 21.2.1", Sd=Nd, Rd=FRd)
    v.passo("Área carregada e a maior semelhante inscrita", "√(A<sub>c1</sub>/A<sub>c0</sub>) ≤ 3,3",
            "A<sub>c0</sub> = %s × %s cm" % (fmt(b, 0), fmt(h, 0)), fmt(k, 2), "NBR 6118, 21.2.1")
    v.passo("Resistente", "F<sub>Rd</sub> = A<sub>c0</sub>·f<sub>cd</sub>·√(A<sub>c1</sub>/A<sub>c0</sub>)", "%s × %s × %s" % (fmt(Ac0, 0), fmt(conc.fcd, 3), fmt(k, 2)),
            fmt(FRd, 0, "kN"), "")
    v.observacao = "a favor da segurança: toda a normal do pilar na base (sem o atrito nas paredes do cálice)"
    return v


# ------------------------------------------------------------------ sapata

def sapata(ext_b: float, ext_h: float, Lemb: float, pil_b: float, pil_h: float, sits_k: Sequence[Situacao],
           sits_d: Sequence[Situacao], conc: Concreto, aco: AcoArmadura, par: ParametrosFundacao,
           elemento: str = "Sapata", peso_colarinho: float = 0.0) -> Resultado:
    """a menor sapata rígida sob o colarinho ext_b × ext_h (cm) que passa no solo; depois a estrutura"""
    if not sits_k:
        raise ErroDeDados("fundação: sem combinações características")
    sa = par.sigma_adm / 1e4                                   # kN/cm²
    melhor = None
    passo = 10.0
    lados = [ext_h + 2 * passo * i for i in range(1, 41)]
    candidatos = sorted(((ah, ext_b + (ah - ext_h) * k) for ah in lados for k in (1.0, 0.75, 0.5, 0.25)),
                        key=lambda c: (c[0] * c[1], c[0]))
    for ah, ab in candidatos:
        ab = math.ceil(ab / 5.0) * 5.0
        hf = max(FUNDO_MINIMO, (ah - ext_h) / 3.0, (ab - ext_b) / 3.0)
        hf = math.ceil(hf / 5.0) * 5.0
        W = PESO_CONCRETO * ah * ab * hf / 1e6 + peso_colarinho + par.peso_solo * (ah * ab - ext_b * ext_h) * Lemb / 1e6
        ok, linhas = True, []
        for s in sits_k:
            N = s.N + W
            Mh = s.Mh + s.Vh * (Lemb + hf)
            Mb = s.Mb + s.Vb * (Lemb + hf)
            dist = distribuicao(ah, ab, N, Mh, Mb)
            if dist is None:
                ok = False
                break
            frac, smax = dist[0], dist[1]
            linhas.append((s, N, Mh, Mb, frac, smax))
            if frac < par.fracao_comprimida - 1e-9 or smax > sa * 1.0001:
                ok = False
                break
        if ok:
            melhor = (ah, ab, hf, W, linhas)
            break
    r = Resultado(elemento, material=conc.nome)
    if melhor is None:
        v = Verificacao("Sapata — tensão no solo", norma="NBR 6118, 22.6 (solo: NBR 6122)", Sd=1.0, Rd=0.0, unidade="")
        v.indeterminada = True
        v.observacao = "nenhuma sapata até %s cm de lado atende à tensão admissível e à área comprimida" % fmt(lados[-1], 0)
        r.add(v)
        return r
    ah, ab, hf, W, linhas = melhor
    r.perfil = "%s × %s × %s cm (h no vão × b no comprimento × altura)" % (fmt(ah, 0), fmt(ab, 0), fmt(hf, 0))
    # ---- solo (características)
    s_gov = max(linhas, key=lambda l: l[5])
    s_frac = min(linhas, key=lambda l: l[4])
    vs = Verificacao("Sapata — tensão máxima no solo (combinação característica)", norma="solo: NBR 6122 (σadm da sondagem)",
                     Sd=s_gov[5] * 1e4, Rd=par.sigma_adm, unidade="kPa")
    vs.passo("Peso da sapata, do colarinho e do solo sobre a sapata", "W", "γ<sub>solo</sub> = %s kN/m³" % fmt(par.peso_solo, 0), fmt(W, 1, "kN"), "")
    vs.passo("Combinação que governa: %s" % s_gov[0].nome, "N = N<sub>k</sub> + W; M = M<sub>k</sub> + V<sub>k</sub>·(L<sub>emb</sub> + h)",
             "N = %s kN; M<sub>h</sub> = %s; M<sub>b</sub> = %s kN·m" % (fmt(s_gov[1], 1), fmt(s_gov[2] / 100, 1), fmt(s_gov[3] / 100, 1)),
             "σ<sub>máx</sub> = %s kPa" % fmt(s_gov[5] * 1e4, 0), "")
    vs.passo("Distribuição plana, solo sem tração", "σ = σ<sub>0</sub> + k<sub>h</sub>·x + k<sub>b</sub>·y na parte comprimida", "", "", "NBR 6118, 22.6.1")
    r.add(vs)
    vf = Verificacao("Sapata — área comprimida da base", norma="solo: NBR 6122 (fração mínima a conferir)", Sd=par.fracao_comprimida,
                     Rd=s_frac[4], unidade="")
    vf.passo("Combinação: %s" % s_frac[0].nome, "A<sub>comprimida</sub>/A ≥ %s" % fmt(par.fracao_comprimida, 2), "",
             fmt(s_frac[4] * 100, 0, "%"), "")
    r.add(vf)
    # ---- estrutura (ELU): as tensões só das cargas do pilar
    rig = Verificacao("Sapata rígida", norma="NBR 6118, 22.6.1", Sd=max((ah - ext_h) / 3, (ab - ext_b) / 3), Rd=hf, unidade="cm")
    rig.passo("h ≥ (a − a<sub>p</sub>)/3 nas duas direções", "a<sub>p</sub> = o colarinho (%s × %s cm)" % (fmt(ext_h, 0), fmt(ext_b, 0)), "", fmt(hf, 0, "cm"), "")
    rig.passo("Espessura abaixo da base do pilar", "≥ 20 cm", "", fmt(hf, 0, "cm"), "NBR 9062, 7.7.5.1")
    r.add(rig)
    d = hf - par.cobrimento - 1.0
    piores = {"h": (0.0, None), "b": (0.0, None)}
    for s in sits_d:
        dist = distribuicao(ah, ab, s.N, s.Mh + s.Vh * (Lemb + hf), s.Mb + s.Vb * (Lemb + hf))
        if dist is None:
            continue
        _f, _m, sig, X, Y = dist
        dA = ah * ab / N_MALHA / N_MALHA
        for eixo, C, meia in (("h", X, ext_h / 2), ("b", Y, ext_b / 2)):
            for lado in (1, -1):
                sel = lado * C > meia
                M = float((sig[sel] * (lado * C[sel] - meia)).sum() * dA)
                if M > piores[eixo][0]:
                    piores[eixo] = (M, s)
    arm = {}
    for eixo, largura, vao_lado in (("h", ab, ah), ("b", ah, ab)):
        M, s = piores[eixo]
        v, dd = N6118.flexao_simples(largura, hf, d, M, conc, aco)
        fi, esp, n = _malha(dd["As"], largura)
        from .vigas import momento_resistente, secao_retangular
        v.Sd, v.Rd = M, momento_resistente(secao_retangular(largura, hf), n * BITOLAS[fi][0], d, conc, aco)[0]
        v.titulo = "Sapata — flexão na face do colarinho (barras na direção %s)" % ("do vão" if eixo == "h" else "do comprimento")
        v.passo("Momento das tensões do solo além da face do colarinho%s" % (" — %s" % s.nome if s else ""), "M<sub>d</sub> = ∫σ·(x − a<sub>p</sub>/2)dA",
                "", fmt(M / 100, 1, "kN·m"), "NBR 6118, 22.6.3")
        v.passo("Tração uniforme na largura", "", "b = %s cm, d = %s cm" % (fmt(largura, 0), fmt(d, 1)),
                "ø%s c/ %s cm (%d barras, com gancho nas pontas)" % (fmt(fi, 1), fmt(esp, 1), n), "NBR 6118, 22.6.2.2 a e 22.6.4.1.1")
        r.add(v)
        arm[eixo] = (fi, esp, n, dd["As"])
    # compressão diagonal no contorno do colarinho (19.5.3.1) com o momento (19.5.2.2)
    Kt = [(0.5, 0.45), (1.0, 0.60), (2.0, 0.70), (3.0, 0.80)]
    K = lambda c1, c2: float(np.interp(c1 / c2, [k[0] for k in Kt], [k[1] for k in Kt]))
    u0 = 2 * (ext_b + ext_h)
    tau_max, s_t = 0.0, None
    for s in sits_d:
        Wh = ext_h ** 2 / 2 + ext_h * ext_b
        Wb = ext_b ** 2 / 2 + ext_b * ext_h
        t = s.N / (u0 * d) + K(ext_h, ext_b) * s.Mh / (Wh * d) + K(ext_b, ext_h) * s.Mb / (Wb * d)
        if t > tau_max:
            tau_max, s_t = t, s
    av = 1.0 - conc.fck_MPa / 250.0
    tRd2 = 0.27 * av * conc.fcd
    vc = Verificacao("Sapata — compressão diagonal no contorno do colarinho", norma="NBR 6118, 22.6.2.2 b e 19.5.3.1", Sd=tau_max * 10,
                     Rd=tRd2 * 10, unidade="MPa")
    vc.passo("Tensão no contorno C (u<sub>0</sub> = %s cm) — %s" % (fmt(u0, 0), s_t.nome if s_t else ""),
             "τ<sub>Sd</sub> = F<sub>Sd</sub>/(u<sub>0</sub>d) + K·M<sub>Sd</sub>/(W<sub>p</sub>d)", "", fmt(tau_max * 10, 2, "MPa"), "NBR 6118, 19.5.2.2")
    vc.passo("Resistente", "τ<sub>Rd2</sub> = 0,27·α<sub>v</sub>·f<sub>cd</sub>", "α<sub>v</sub> = %s" % fmt(av, 2), fmt(tRd2 * 10, 2, "MPa"), "NBR 6118, 19.5.3.1")
    r.add(vc)
    r.add(_pressao_contato(max(s.N for s in sits_d), pil_b, pil_h, ab, ah, conc))
    vol = ah * ab * hf / 1e6
    kg = sum(n * (L + 2 * 10 * fi / 10.0) / 100.0 * BITOLAS[fi][1] for (fi, _e, n, _A), L in
             ((arm["h"], ah - 2 * par.cobrimento), (arm["b"], ab - 2 * par.cobrimento)))
    r.dados.update({"barras": {k: (arm[k][0], arm[k][1], arm[k][2]) for k in ("h", "b")}, "cobrimento": par.cobrimento})
    r.dados.update({"tipo": "sapata", "ah": ah, "ab": ab, "hf": hf, "volume": vol, "aco_kg": kg, "W": W,
                    "armadura": "ø%s c/ %s (vão) + ø%s c/ %s (comprimento), com gancho" % (fmt(arm["h"][0], 1), fmt(arm["h"][1], 1),
                                                                                          fmt(arm["b"][0], 1), fmt(arm["b"][1], 1))})
    r.hipotese("solo", "Tensão admissível do solo %s kPa e área comprimida mínima de %s da base: dados da obra pela NBR 6122 "
               "(fora da pasta Normas) — confira com a sondagem." % (fmt(par.sigma_adm, 0), fmt(par.fracao_comprimida * 100, 0) + " %"), "usuario")
    return r


# ------------------------------------------------------------------ bloco sobre estacas

def _estacas(n: int, e: float) -> List[Tuple[float, float]]:
    if n == 2:
        return [(-e / 2, 0.0), (e / 2, 0.0)]
    if n == 4:
        return [(sx * e / 2, sy * e / 2) for sx in (-1, 1) for sy in (-1, 1)]
    if n == 6:
        return [(x, sy * e / 2) for x in (-e, 0.0, e) for sy in (-1, 1)]
    raise ErroDeDados("bloco: 2, 4 ou 6 estacas")


def bloco(ext_b: float, ext_h: float, Lemb: float, pil_b: float, pil_h: float, sits_k: Sequence[Situacao],
          sits_d: Sequence[Situacao], conc: Concreto, aco: AcoArmadura, par: ParametrosFundacao,
          elemento: str = "Bloco sobre estacas", peso_colarinho: float = 0.0) -> Resultado:
    """o bloco rígido com o menor número de estacas (2, 4 ou 6) que atende às cargas admissíveis"""
    fi = par.estaca_diametro
    e = par.estaca_espacamento * fi
    borda = fi / 2 + par.estaca_borda
    fyd = min(aco.fyd, 43.5)
    avaliados = []
    for n, fator in [(n, f) for n in (2, 4, 6) for f in (1.0, 1.25, 1.5, 1.75, 2.0)]:
        e = par.estaca_espacamento * fi * fator
        pos = _estacas(n, e)
        xs = [p[0] for p in pos]
        ys = [p[1] for p in pos]
        ah = max(max(xs) - min(xs) + 2 * borda, ext_h + 20.0)
        ab = max(max(ys) - min(ys) + 2 * borda, ext_b + 20.0)
        ah, ab = math.ceil(ah / 5) * 5, math.ceil(ab / 5) * 5
        # bielas a 45° até a estaca mais distante do nó do pilar (a um quarto da base do pilar do centro)
        rs = [math.hypot(max(abs(x) - pil_h / 4, 0.0), max(abs(y) - pil_b / 4, 0.0)) for x, y in pos]
        d = max(max(rs), FUNDO_MINIMO)
        hb = math.ceil((d + 10.0) / 5) * 5
        d = hb - 10.0
        W = PESO_CONCRETO * ah * ab * hb / 1e6 + peso_colarinho + par.peso_solo * (ah * ab - ext_b * ext_h) * Lemb / 1e6
        Sx2 = sum(x * x for x in xs) or 1e-9
        Sy2 = sum(y * y for y in ys) or 1e-9
        reac = []
        for s in sits_k:
            N = s.N + W
            Mh = s.Mh + s.Vh * (Lemb + hb)
            Mb = s.Mb + s.Vb * (Lemb + hb)
            Rs = [N / n + Mh * x / Sx2 + (Mb * y / Sy2 if any(ys) else 0.0) for x, y in pos]
            Rs += [N / n - Mh * x / Sx2 - (Mb * y / Sy2 if any(ys) else 0.0) for x, y in pos]    # o momento nos dois sentidos
            reac.append((s, max(Rs), min(Rs), Mb))
        Rmax = max(r_[1] for r_ in reac)
        Rmin = min(r_[2] for r_ in reac)
        sem_mb = n == 2 and any(r_[3] > 1.0 for r_ in reac)
        ok = Rmax <= par.estaca_carga * 1.0001 and Rmin >= -par.estaca_tracao - 1e-9 and not sem_mb
        avaliados.append((ok, (n, pos, ah, ab, hb, d, W, reac, Rmax, Rmin, rs, sem_mb, e)))
    bons = [a[1] for a in avaliados if a[0]]
    if bons:
        escolhido = min(bons, key=lambda c: (c[0], c[2] * c[3] * c[4]))
    else:
        # nenhum passa: o que chega mais perto (a menor falta relativa)
        def falta(c):
            return max(c[8] / par.estaca_carga, (-c[9]) / max(par.estaca_tracao, 1.0) if c[9] < 0 else 0.0, 99.0 if c[11] else 0.0)
        escolhido = min((a[1] for a in avaliados), key=lambda c: (falta(c), c[0]))
    n, pos, ah, ab, hb, d, W, reac, Rmax, Rmin, rs, sem_mb, e = escolhido
    r = Resultado(elemento, perfil="%d estacas ø%s, bloco %s × %s × %s cm" % (n, fmt(fi, 0), fmt(ah, 0), fmt(ab, 0), fmt(hb, 0)), material=conc.nome)
    sg = max(reac, key=lambda r_: r_[1])
    vr = Verificacao("Estacas — reação máxima (combinação característica)", norma="estaca: NBR 6122 (carga admissível da obra)",
                     Sd=Rmax, Rd=par.estaca_carga)
    vr.passo("Peso do bloco, do colarinho e do solo sobre o bloco", "W", "", fmt(W, 1, "kN"), "")
    vr.passo("Reação — %s" % sg[0].nome, "R<sub>i</sub> = N/n ± M<sub>h</sub>·x<sub>i</sub>/Σx² ± M<sub>b</sub>·y<sub>i</sub>/Σy²",
             "n = %d, espaçamento %s cm (%s·ø)" % (n, fmt(e, 0), fmt(e / fi, 2)), fmt(Rmax, 1, "kN"), "")
    r.add(vr)
    vt = Verificacao("Estacas — reação mínima (tração)", norma="estaca: NBR 6122", Sd=max(-Rmin, 0.0), Rd=par.estaca_tracao)
    vt.passo("Menor reação", "", "", fmt(Rmin, 1, "kN"), "")
    if Rmin >= 0:
        vt.dispensada = True
    else:
        vt.observacao = ("estaca tracionada: informe a tração admissível da estaca (projeto geotécnico) e ancore a armadura dela no "
                         "topo do bloco (NBR 6118, Figura 22.7)" if par.estaca_tracao <= 0 else
                         "estaca tracionada: ancorar a armadura da estaca no topo do bloco (NBR 6118, Figura 22.7)")
    r.add(vt)
    if sem_mb:
        vm = Verificacao("Bloco de 2 estacas — momento na direção do comprimento", norma="NBR 6118, 22.7.2.2", Sd=1.0, Rd=0.0, unidade="")
        vm.indeterminada = True
        vm.observacao = "as duas estacas em linha não resistem ao momento longitudinal: prever vigas baldrame ou usar 4 estacas"
        r.add(vm)
    # ---- bielas e tirantes (ELU)
    av2 = 1.0 - conc.fck_MPa / 250.0
    fcd1, fcd3 = 0.85 * av2 * conc.fcd, 0.72 * av2 * conc.fcd
    Sx2 = sum(x * x for x, _ in pos) or 1e-9
    Sy2 = sum(y * y for _, y in pos) or 1e-9
    Rd_max, Nd_max, Th, Tb, s_T = 0.0, 0.0, 0.0, 0.0, None
    for s in sits_d:
        Mh = s.Mh + s.Vh * (Lemb + hb)
        Mb = s.Mb + s.Vb * (Lemb + hb)
        Nd_max = max(Nd_max, s.N)
        for sinal in (1, -1):
            for (x, y), rr in zip(pos, rs):
                R = s.N / n + sinal * (Mh * x / Sx2 + (Mb * y / Sy2 if any(p[1] for p in pos) else 0.0))
                if R > Rd_max:
                    Rd_max = R
                th = R * max(abs(x) - pil_h / 4, 0.0) / d
                tb = R * max(abs(y) - pil_b / 4, 0.0) / d
                if th > Th:
                    Th, s_T = th, s
                Tb = max(Tb, tb)
    tg_min = d / max(rs)
    tg_max = d / max(min(rs), 1e-9)
    vi = Verificacao("Bloco — inclinação das bielas (tg θ ≥ 0,57)", norma="NBR 6118, 22.3.1", Sd=0.57, Rd=tg_min, unidade="")
    vi.passo("tg θ entre 0,57 e 2", "tg θ = d/r (r: da estaca ao nó do pilar, a um quarto da base do pilar)",
             "d = %s cm" % fmt(d, 0), "%s a %s" % (fmt(tg_min, 2), fmt(min(tg_max, 99), 2)), "NBR 6118, 22.3.1")
    if tg_max > 2.0 + 1e-9:
        vi.observacao = "estaca muito perto do pilar (tg θ = %s > 2): a carga dela vai por compressão direta" % fmt(tg_max, 2)
    r.add(vi)
    sin2 = tg_min ** 2 / (1 + tg_min ** 2)
    Ap = pil_b * pil_h
    Aest = math.pi * fi ** 2 / 4
    vbp = Verificacao("Bloco — nó sob o pilar (CCC)", norma="NBR 6118, 22.3.2", Sd=Nd_max / (Ap * sin2) * 10, Rd=fcd1 * 10, unidade="MPa")
    vbp.passo("Tensão na biela junto ao pilar", "σ = N<sub>d</sub>/(A<sub>p</sub>·sen²θ) ≤ f<sub>cd1</sub> = 0,85·α<sub>v2</sub>·f<sub>cd</sub>",
              "N<sub>d</sub> = %s kN, A<sub>p</sub> = %s cm²" % (fmt(Nd_max, 1), fmt(Ap, 0)), fmt(vbp.Sd, 2, "MPa"), "NBR 6118, 22.3.2")
    r.add(vbp)
    vbe = Verificacao("Bloco — nó sobre a estaca (CCT)", norma="NBR 6118, 22.3.2", Sd=Rd_max / (Aest * sin2) * 10, Rd=fcd3 * 10, unidade="MPa")
    vbe.passo("Tensão na biela junto à estaca", "σ = R<sub>d</sub>/(A<sub>est</sub>·sen²θ) ≤ f<sub>cd3</sub> = 0,72·α<sub>v2</sub>·f<sub>cd</sub>",
              "R<sub>d</sub> = %s kN" % fmt(Rd_max, 1), fmt(vbe.Sd, 2, "MPa"), "NBR 6118, 22.3.2")
    r.add(vbe)
    arm = []
    barras = {}
    for nome, T in (("do vão", Th), ("do comprimento", Tb)):
        if T <= 0:
            continue
        As = T / fyd
        nb, fb = escolher_barras(As, (10.0, 12.5, 16.0, 20.0, 25.0), n_min=2, n_max=16) or (0, 0.0)
        v = Verificacao("Bloco — tirante sobre as estacas (direção %s)" % nome, norma="NBR 6118, 22.3.3 e 22.7.4.1.1", Sd=As,
                        Rd=nb * BITOLAS[fb][0] if nb else 0.0, unidade="cm²")
        v.passo("Força no tirante (a estaca mais carregada)%s" % (" — %s" % s_T.nome if s_T and nome == "do vão" else ""),
                "T = R<sub>d</sub>·(x − a<sub>p</sub>/4)/d", "", fmt(T, 1, "kN"), "Blévot / NBR 6118, 22.3")
        v.passo("Armadura por faixa de estacas (largura 1,2·ø)", "A<sub>s</sub> = T/f<sub>yd</sub>", "%s / %s" % (fmt(T, 1), fmt(fyd, 2)),
                "%d ø%s por faixa" % (nb, fmt(fb, 1)) if nb else "—", "NBR 6118, 22.7.2.1 a")
        if not nb:
            v.indeterminada = True
        r.add(v)
        arm.append("%d ø%s (faixas %s)" % (nb, fmt(fb, 1), nome))
        if nb:
            barras["h" if nome == "do vão" else "b"] = (nb, fb)
    vd = Verificacao("Bloco — armadura de distribuição", norma="NBR 6118, 22.7.4.1.2", Sd=0.2 * max(Th, Tb) / fyd, Rd=0.2 * max(Th, Tb) / fyd, unidade="cm²")
    vd.passo("Malha nas duas direções", "20 % das forças de tração", "", fmt(0.2 * max(Th, Tb) / fyd, 2, "cm²"), "NBR 6118, 22.7.4.1.2")
    if n == 2:
        vd.observacao = "estacas em linha: armaduras laterais e superior obrigatórias (22.7.4.1.5)"
    r.add(vd)
    r.add(_pressao_contato(Nd_max, pil_b, pil_h, ab, ah, conc))
    vol = ah * ab * hb / 1e6
    r.dados.update({"barras": barras, "cobrimento": par.cobrimento})
    r.dados.update({"tipo": "estacas", "ah": ah, "ab": ab, "hf": hb, "n_estacas": n, "estacas": pos, "estaca_diametro": fi,
                    "volume": vol, "aco_kg": None, "W": W, "armadura": " + ".join(arm) + " + distribuição"})
    r.hipotese("estacas", "Carga admissível da estaca %s kN (tração %s kN), espaçamento mínimo %s·ø e %s cm da face da estaca à borda do bloco: "
               "dados da obra pela NBR 6122 (fora da pasta Normas) — confira." % (fmt(par.estaca_carga, 0), fmt(par.estaca_tracao, 0),
                                                                               fmt(par.estaca_espacamento, 1), fmt(par.estaca_borda, 0)), "usuario")
    r.hipotese("bielas", "Bloco rígido: bielas do nó do pilar (a um quarto da base do pilar do centro) a cada estaca, tg θ ≥ 1 na mais "
               "distante; tirantes sobre as estacas; os limites dos nós de 22.3.2.", "rotina")
    return r
