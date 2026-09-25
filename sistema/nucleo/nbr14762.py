# -*- coding: utf-8 -*-
"""Perfis formados a frio — NBR 14762:2010 (terças, longarinas e barras Ue).

Este módulo cobre o perfil **U enrijecido (Ue)**, que é o perfil de terça e de
longarina de galpão. A NBR 8800 não se aplica a perfis formados a frio: além da
flambagem global (flexão, torção e flexo-torção), a chapa fina flamba **localmente**
antes de escoar e o conjunto mesa+enrijecedor gira em torno da dobra com a alma —
a flambagem **distorcional**, que não existe no perfil laminado.

Estão implementados os dois caminhos da norma:

* **MRD — Método da Resistência Direta** (item 9.8): usa a seção bruta e as cargas
  críticas elásticas dos três modos, aplicando uma curva de resistência a cada um.
  É o caminho principal deste módulo (`compressao_mrd`, `flexao_mrd`).
* **MSE/MLE — Método da Seção Efetiva** (item 9.7): reduz cada chapa esbelta à sua
  largura efetiva (Winter) e devolve A_ef e W_ef (`secao_efetiva`).

Unidades (conforme GUIA_SISTEMA.md)
-----------------------------------
Entram em **mm** apenas as dimensões nominais do perfil (como no catálogo e na
designação "Ue 200×75×20×2,65"); em `terca()` e `dimensionar_terca()` entram vão em
**m** e cargas em **kN/m**, que é a linguagem da interface. Tudo o mais é interno:

    força kN · momento kN·cm · tensão kN/cm² · comprimento cm

LIMITES DE APLICABILIDADE (leia antes de usar)
----------------------------------------------
1. Só seção **Ue** (U enrijecido) de espessura constante, com enrijecedor de borda
   simples a 90°. Z, Ze, cartola, perfis compostos e enrijecedores intermediários
   **não** estão implementados.
2. As propriedades de seção saem do **método linear** (linha média), com os cantos
   modelados como arcos de raio interno `r` (padrão 1,0·t, conforme NBR 6355 e
   item 3.5.2 do manual). Divergem 1 % a 8 % das tabelas de catálogo, que arredondam
   e às vezes divergem entre si — veja `testes/test_nbr14762.py`.
3. As **cargas críticas local e distorcional** vêm de expressões analíticas
   aproximadas (detalhadas nas docstrings de `forca_critica_local` e
   `forca_critica_distorcional`), **não** de análise de faixas finitas (CUFSM/GBT),
   que é o que a NBR 14762 admite no item 9.8.1 como forma "exata". Onde houver
   tabela do fabricante para a configuração exata (número de correntes, fixação da
   telha, continuidade), **o valor do fabricante prevalece sobre o deste módulo**.
4. O efeito estabilizante da telha (restrição à rotação da mesa, continuidade,
   terças em luva) é **ignorado** por padrão — o resultado fica a favor da segurança.
   Quem quiser considerá-lo passa `k_mola` em `flexao_mrd` (kN·cm/cm por cm de barra).
5. Não são verificados: furos na alma, cargas concentradas fora dos apoios,
   fadiga, torção de empenamento por carga excêntrica (a carga é suposta aplicada
   no plano da alma ou com a telha impedindo o giro).
"""
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .base import (E, G, NU, RHO, GAMA_A1, GAMA_A2, ErroDeDados,
                   Resultado, Verificacao, fmt)
from . import materiais as mat
from .perfis import Perfil, banco, perfil

# --- coeficientes de flambagem de chapa (NBR 14762:2010, Tabelas 6 e 7) ---
K_AA = 4.0            # elemento AA (dois bordos apoiados), compressão uniforme
K_AL = 0.43           # elemento AL (um bordo livre), compressão uniforme
K_AA_FLEXAO = 23.9    # elemento AA sob flexão pura (ψ = −1)

# --- coeficientes de ponderação (NBR 14762:2010, Tabela 4) ---
GAMA = GAMA_A1        # 1,10 — tração (escoamento), flexão e cortante
GAMA_COMPRESSAO = 1.20  # 1,20 — compressão centrada (a 0.8.13 e anteriores usavam 1,10)
GAMA_RUPTURA = GAMA_A2  # 1,35 — ruptura (esmagamento em furos)
#: Índice de esbeltez máximo da barra comprimida (NBR 14762:2010, item 9.7.4).
ESBELTEZ_MAX_COMPRESSAO = 200.0

_D_PLACA = E / (12.0 * (1.0 - NU ** 2))   # rigidez de placa por unidade de t³

# Coeficientes de esmagamento da alma — NBR 14762:2010, item 9.9, Tabela 22
# (seções U e Ue, mesas enrijecidas, carga numa única mesa).
# chave: (mesa_fixada, posicao) -> (C, CR, CN, Ch)
_ESMAGAMENTO = {
    (True,  "extremidade"): (4.0,  0.14, 0.35, 0.02),
    (True,  "interior"):    (13.0, 0.23, 0.14, 0.01),
    (False, "extremidade"): (4.0,  0.14, 0.35, 0.02),
    (False, "interior"):    (13.0, 0.23, 0.14, 0.01),
}


# =============================================================================
# 1. GEOMETRIA E PROPRIEDADES DA SEÇÃO Ue (método linear)
# =============================================================================

def _arco(cx, cy, raio, a0, a1, n=24) -> List[Tuple[float, float]]:
    """Discretiza um arco da linha média em n segmentos."""
    return [(cx + raio * math.cos(a0 + (a1 - a0) * i / n),
             cy + raio * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def _limpa(pontos) -> List[Tuple[float, float]]:
    q = [pontos[0]]
    for p in pontos[1:]:
        if abs(p[0] - q[-1][0]) > 1e-12 or abs(p[1] - q[-1][1]) > 1e-12:
            q.append(p)
    return q


def _trechos_ue(h, bf, d, t, r) -> List[dict]:
    """Linha média do Ue, em trechos identificados. Tudo em cm.

    Origem: face externa da alma em x = 0, meia altura em y = 0. A seção é
    simétrica em relação ao eixo x (eixo de maior inércia). Os trechos são
    percorridos da ponta do enrijecedor inferior à ponta do superior.
    """
    rm = r + t / 2.0               # raio da linha média nos cantos
    ym = (h - t) / 2.0             # meia altura da linha média da alma
    xw = t / 2.0                   # linha média da alma
    xl = bf - t / 2.0              # linha média do enrijecedor
    yl = ym - (d - t / 2.0)        # ponta do enrijecedor superior
    T = []
    T.append({"elem": "enr_inf", "reta": ((xl, -yl), (xl, -(ym - rm)))})
    T.append({"elem": "canto", "pts": _arco(xl - rm, -(ym - rm), rm, 0.0, -math.pi / 2)})
    T.append({"elem": "mesa_inf", "reta": ((xl - rm, -ym), (xw + rm, -ym))})
    T.append({"elem": "canto", "pts": _arco(xw + rm, -(ym - rm), rm, -math.pi / 2, -math.pi)})
    T.append({"elem": "alma", "reta": ((xw, -(ym - rm)), (xw, ym - rm))})
    T.append({"elem": "canto", "pts": _arco(xw + rm, ym - rm, rm, math.pi, math.pi / 2)})
    T.append({"elem": "mesa_sup", "reta": ((xw + rm, ym), (xl - rm, ym))})
    T.append({"elem": "canto", "pts": _arco(xl - rm, ym - rm, rm, math.pi / 2, 0.0)})
    T.append({"elem": "enr_sup", "reta": ((xl, ym - rm), (xl, yl))})
    for tr in T:
        if "reta" in tr:
            tr["pts"] = [tr["reta"][0], tr["reta"][1]]
    return T


def _trechos_u(h, bf, t, r) -> List[dict]:
    """Linha média do U simples (sem enrijecedor), na mesma convenção de `_trechos_ue`.
    Percorrida da ponta da mesa inferior à ponta da mesa superior; a mesa é elemento
    AL (um bordo livre)."""
    rm = r + t / 2.0
    ym = (h - t) / 2.0
    xw = t / 2.0
    xl = bf              # a borda livre da mesa: a linha média vai até a face da ponta
    T = []
    T.append({"elem": "mesa_inf", "reta": ((xl, -ym), (xw + rm, -ym))})
    T.append({"elem": "canto", "pts": _arco(xw + rm, -(ym - rm), rm, -math.pi / 2, -math.pi)})
    T.append({"elem": "alma", "reta": ((xw, -(ym - rm)), (xw, ym - rm))})
    T.append({"elem": "canto", "pts": _arco(xw + rm, ym - rm, rm, math.pi, math.pi / 2)})
    T.append({"elem": "mesa_sup", "reta": ((xw + rm, ym), (xl, ym))})
    for tr in T:
        if "reta" in tr:
            tr["pts"] = [tr["reta"][0], tr["reta"][1]]
    return T


def _trechos(sec: "SecaoUe") -> List[dict]:
    """Trechos da linha média da seção (Ue, ou U simples quando `sec.d == 0`)."""
    if sec.d <= 0:
        return _trechos_u(sec.h, sec.bf, sec.t, sec.r)
    return _trechos_ue(sec.h, sec.bf, sec.d, sec.t, sec.r)


def _polilinha(trechos) -> List[Tuple[float, float]]:
    pts = []
    for tr in trechos:
        pts.extend(tr["pts"])
    return _limpa(pts)


def _props_pecas(pecas: Sequence[Sequence[Tuple[float, float]]], t: float) -> dict:
    """Área, centroide e inércias de um conjunto de polilinhas de linha média.

    Método linear da NBR 14762 (item 9.2 e Anexo A): a parede é substituída pela
    sua linha média de espessura t, o que despreza termos de ordem t²/b² — erro
    inferior a 0,1 % nas espessuras usuais.
    """
    L = Sy = Sx = 0.0
    for P in pecas:
        for i in range(len(P) - 1):
            (x1, y1), (x2, y2) = P[i], P[i + 1]
            li = math.hypot(x2 - x1, y2 - y1)
            L += li
            Sy += li * (x1 + x2) / 2.0
            Sx += li * (y1 + y2) / 2.0
    if L <= 0:
        raise ErroDeDados("seção efetiva nula: revise as dimensões do perfil")
    A = L * t
    xc, yc = Sy / L, Sx / L
    Ix = Iy = Ixy = 0.0
    for P in pecas:
        for i in range(len(P) - 1):
            (x1, y1), (x2, y2) = P[i], P[i + 1]
            li = math.hypot(x2 - x1, y2 - y1)
            a1, b1 = x1 - xc, y1 - yc
            a2, b2 = x2 - xc, y2 - yc
            Ix += li * (b1 * b1 + b1 * b2 + b2 * b2) / 3.0
            Iy += li * (a1 * a1 + a1 * a2 + a2 * a2) / 3.0
            Ixy += li * (2 * a1 * b1 + a1 * b2 + a2 * b1 + 2 * a2 * b2) / 6.0
    return {"A": A, "L": L, "xc": xc, "yc": yc,
            "Ix": Ix * t, "Iy": Iy * t, "Ixy": Ixy * t}


def _props_linha(P: Sequence[Tuple[float, float]], t: float) -> dict:
    """Propriedades completas de uma linha média **conexa**, inclusive centro de
    torção e constante de empenamento (teoria de Vlasov para seção aberta de
    parede fina — NBR 14762, Anexo A)."""
    p = _props_pecas([P], t)
    xc, yc, Ix, Iy = p["xc"], p["yc"], p["Ix"], p["Iy"]
    # coordenada setorial com polo no centroide: dω = (x−xc)dy − (y−yc)dx
    om = [0.0]
    for i in range(len(P) - 1):
        (x1, y1), (x2, y2) = P[i], P[i + 1]
        om.append(om[-1] + (x1 - xc) * (y2 - y1) - (y1 - yc) * (x2 - x1))
    Iwx = Iwy = 0.0
    for i in range(len(P) - 1):
        (x1, y1), (x2, y2) = P[i], P[i + 1]
        li = math.hypot(x2 - x1, y2 - y1)
        a1, b1 = x1 - xc, y1 - yc
        a2, b2 = x2 - xc, y2 - yc
        w1, w2 = om[i], om[i + 1]
        Iwy += li * (2 * a1 * w1 + a1 * w2 + a2 * w1 + 2 * a2 * w2) / 6.0
        Iwx += li * (2 * b1 * w1 + b1 * w2 + b2 * w1 + 2 * b2 * w2) / 6.0
    Iwx *= t
    Iwy *= t
    xs = xc + Iwx / Ix                      # centro de torção
    ys = yc - Iwy / Iy
    oms = [0.0]
    for i in range(len(P) - 1):
        (x1, y1), (x2, y2) = P[i], P[i + 1]
        oms.append(oms[-1] + (x1 - xs) * (y2 - y1) - (y1 - ys) * (x2 - x1))
    S = S2 = 0.0
    for i in range(len(P) - 1):
        (x1, y1), (x2, y2) = P[i], P[i + 1]
        li = math.hypot(x2 - x1, y2 - y1)
        w1, w2 = oms[i], oms[i + 1]
        S += li * (w1 + w2) / 2.0
        S2 += li * (w1 * w1 + w1 * w2 + w2 * w2) / 3.0
    p.update({"xs": xs, "ys": ys,
              "Cw": S2 * t - (S * t) ** 2 / p["A"],
              "J": p["L"] * t ** 3 / 3.0,
              "x0": xc - xs, "y0": yc - ys})
    return p


@dataclass(frozen=True)
class SecaoUe:
    """Seção Ue e suas propriedades. Dimensões nominais em mm; propriedades em cm."""
    nome: str
    # dimensões nominais externas, mm
    h_mm: float
    bf_mm: float
    d_mm: float
    t_mm: float
    r_mm: float
    # dimensões em cm (externas)
    h: float
    bf: float
    d: float
    t: float
    r: float
    # larguras planas (trecho reto entre cantos), cm
    bw_plano: float
    bf_plano: float
    d_plano: float
    # propriedades de seção, cm
    A: float
    Ix: float
    Iy: float
    Wx: float
    Wy: float
    xc: float          # centroide, medido da face externa da alma
    xs: float          # centro de torção, mesma origem
    x0: float          # xc − xs (excentricidade do centro de torção)
    r0: float          # raio de giração polar em relação ao centro de torção
    J: float
    Cw: float
    massa: float       # kg/m

    # ---- derivadas ----
    @property
    def rx(self) -> float:
        return math.sqrt(self.Ix / self.A)

    @property
    def ry(self) -> float:
        return math.sqrt(self.Iy / self.A)

    @property
    def esbeltez_alma(self) -> float:
        return self.bw_plano / self.t

    @property
    def esbeltez_mesa(self) -> float:
        return self.bf_plano / self.t

    @property
    def esbeltez_enrijecedor(self) -> float:
        return self.d_plano / self.t

    def resumo(self) -> dict:
        return {"nome": self.nome, "h": self.h_mm, "bf": self.bf_mm, "d": self.d_mm,
                "t": self.t_mm, "r": self.r_mm, "massa": round(self.massa, 2),
                "A": round(self.A, 2), "Ix": round(self.Ix, 1), "Wx": round(self.Wx, 2),
                "Iy": round(self.Iy, 1), "Wy": round(self.Wy, 2),
                "rx": round(self.rx, 2), "ry": round(self.ry, 2),
                "J": round(self.J, 4), "Cw": round(self.Cw), "x0": round(self.x0, 3),
                "r0": round(self.r0, 3),
                "bw/t": round(self.esbeltez_alma, 1),
                "bf/t": round(self.esbeltez_mesa, 1),
                "D/t": round(self.esbeltez_enrijecedor, 1)}


def propriedades_ue(h: float, bf: float, d_enr: float, t: float,
                    r: Optional[float] = None, nome: str = "") -> SecaoUe:
    """Propriedades geométricas de um Ue pelo método linear (NBR 14762, Anexo A).

    Parâmetros em **mm** (dimensões externas, como na designação NBR 6355):
        h      altura total da alma
        bf     largura da mesa
        d_enr  comprimento do enrijecedor de borda
        t      espessura da chapa
        r      raio interno de dobra; padrão 1,0·t (NBR 6355 e item 3.5.2 do manual
               exigem r ≥ 1,0·t a 1,5·t para não trincar a chapa)

    Devolve `SecaoUe` com as propriedades em cm. A linha média é integrada
    numericamente, inclusive nos arcos dos cantos; o centro de torção e C_w saem
    da coordenada setorial (Vlasov), e J = Σ(L·t³)/3.
    """
    for rot, val in (("h", h), ("bf", bf), ("d_enr", d_enr), ("t", t)):
        if val is None or val <= 0:
            raise ErroDeDados(f"dimensão {rot} deve ser positiva (recebido: {val})")
    if not (0.4 <= t <= 8.0):
        raise ErroDeDados(f"espessura t = {t} mm fora da faixa da NBR 6355 "
                          "para perfis formados a frio (0,4 mm a 8,0 mm)")
    if r is None:
        r = 1.0 * t
    if r < 0:
        raise ErroDeDados("raio de dobra não pode ser negativo")
    rm = r + t / 2.0
    if bf <= t + 2 * rm:
        raise ErroDeDados(f"mesa bf = {bf} mm curta demais para o raio de dobra "
                          f"(precisa de bf > {t + 2 * rm:.1f} mm)")
    if h <= t + 2 * rm:
        raise ErroDeDados(f"alma h = {h} mm curta demais para o raio de dobra "
                          f"(precisa de h > {t + 2 * rm:.1f} mm)")
    if d_enr <= t / 2.0 + rm:
        raise ErroDeDados(f"enrijecedor D = {d_enr} mm curto demais para o raio de "
                          f"dobra (precisa de D > {t / 2.0 + rm:.1f} mm)")

    hc, bfc, dc, tc, rc = h / 10.0, bf / 10.0, d_enr / 10.0, t / 10.0, r / 10.0
    trechos = _trechos_ue(hc, bfc, dc, tc, rc)
    p = _props_linha(_polilinha(trechos), tc)
    planos = {}
    for tr in trechos:
        if "reta" in tr:
            (x1, y1), (x2, y2) = tr["reta"]
            planos[tr["elem"]] = math.hypot(x2 - x1, y2 - y1)
    Wx = p["Ix"] / (hc / 2.0)
    # fibra extrema em y: a ponta da mesa (mais afastada do centroide)
    Wy = p["Iy"] / max(bfc - p["xc"], p["xc"])
    r0 = math.sqrt((p["Ix"] + p["Iy"]) / p["A"] + p["x0"] ** 2)
    if not nome:
        nome = (f"Ue {h:g}×{bf:g}×{d_enr:g}×{t:.2f}".replace(".", ","))
    return SecaoUe(nome=nome, h_mm=h, bf_mm=bf, d_mm=d_enr, t_mm=t, r_mm=r,
                   h=hc, bf=bfc, d=dc, t=tc, r=rc,
                   bw_plano=planos["alma"], bf_plano=planos["mesa_sup"],
                   d_plano=planos["enr_sup"],
                   A=p["A"], Ix=p["Ix"], Iy=p["Iy"], Wx=Wx, Wy=Wy,
                   xc=p["xc"], xs=p["xs"], x0=p["x0"], r0=r0,
                   J=p["J"], Cw=p["Cw"], massa=p["A"] * RHO * 1e-4)


def propriedades_u(h: float, bf: float, t: float, r: Optional[float] = None,
                   nome: str = "") -> SecaoUe:
    """Propriedades de um **U simples** formado a frio (sem enrijecedor), pelo mesmo
    método linear de `propriedades_ue`. Devolve `SecaoUe` com `d = 0`: as rotinas do
    MRD tratam a mesa como elemento AL (k = 0,43) e não têm modo distorcional (não há
    enrijecedor para girar). Dimensões em mm."""
    for rot, val in (("h", h), ("bf", bf), ("t", t)):
        if val is None or val <= 0:
            raise ErroDeDados(f"dimensão {rot} deve ser positiva (recebido: {val})")
    if not (0.4 <= t <= 8.0):
        raise ErroDeDados(f"espessura t = {t} mm fora da faixa da NBR 6355 "
                          "para perfis formados a frio (0,4 mm a 8,0 mm)")
    if r is None:
        r = 1.0 * t
    rm = r + t / 2.0
    if bf <= t + rm:
        raise ErroDeDados(f"mesa bf = {bf} mm curta demais para o raio de dobra")
    if h <= t + 2 * rm:
        raise ErroDeDados(f"alma h = {h} mm curta demais para o raio de dobra")
    hc, bfc, tc, rc = h / 10.0, bf / 10.0, t / 10.0, r / 10.0
    trechos = _trechos_u(hc, bfc, tc, rc)
    p = _props_linha(_polilinha(trechos), tc)
    planos = {}
    for tr in trechos:
        if "reta" in tr:
            (x1, y1), (x2, y2) = tr["reta"]
            planos[tr["elem"]] = math.hypot(x2 - x1, y2 - y1)
    Wx = p["Ix"] / (hc / 2.0)
    Wy = p["Iy"] / max(bfc - p["xc"], p["xc"])
    r0 = math.sqrt((p["Ix"] + p["Iy"]) / p["A"] + p["x0"] ** 2)
    if not nome:
        nome = (f"U {h:g}×{bf:g}×{t:.2f} (FF)".replace(".", ","))
    return SecaoUe(nome=nome, h_mm=h, bf_mm=bf, d_mm=0.0, t_mm=t, r_mm=r,
                   h=hc, bf=bfc, d=0.0, t=tc, r=rc,
                   bw_plano=planos["alma"], bf_plano=planos["mesa_sup"], d_plano=0.0,
                   A=p["A"], Ix=p["Ix"], Iy=p["Iy"], Wx=Wx, Wy=Wy,
                   xc=p["xc"], xs=p["xs"], x0=p["x0"], r0=r0,
                   J=p["J"], Cw=p["Cw"], massa=p["A"] * RHO * 1e-4)


def _dims_do_nome(texto: str) -> Optional[Tuple[float, float, float, float]]:
    """Extrai h × bf × D × t (mm) de 'Ue 200×75×20×2,65'."""
    limpo = (texto.replace("×", "x").replace("X", "x").replace(",", ".")
             .replace("Ue", " ").replace("UE", " "))
    nums = []
    for pedaco in limpo.replace("x", " ").split():
        try:
            nums.append(float(pedaco))
        except ValueError:
            pass
    if len(nums) >= 4:
        return nums[0], nums[1], nums[2], nums[3]
    return None


def secao_do_perfil(p, r: Optional[float] = None) -> SecaoUe:
    """Monta a `SecaoUe` de um perfil do catálogo (`dados/perfis.json`).

    Aceita o objeto `Perfil`, ou o nome ("Ue 200×75×20×2,65"). As dimensões do
    enrijecedor não estão nos campos do `Perfil`, então saem do campo `dim` ou
    do próprio nome.
    """
    if not isinstance(p, Perfil):
        p = perfil(str(p))
    nome_up = p.nome.strip().upper()
    if p.tipo == "Ue" and not nome_up.startswith("UE"):
        # U simples formado a frio ("U 100×50×2,00 (FF)"): três dimensões
        dims3 = _dims_u_do_nome(p.dados.get("dim", "")) or _dims_u_do_nome(p.nome)
        if dims3 is None:
            raise ErroDeDados(f"não consegui ler as dimensões h×bf×t de {p.nome}")
        h, bf, t = dims3
        return propriedades_u(h, bf, t, r=r, nome=p.nome)
    if p.tipo != "Ue":
        raise ErroDeDados(f"{p.nome} não é um perfil formado a frio U ou Ue; "
                          "este módulo só dimensiona U e Ue. Z, Ze e "
                          "cartola não estão implementados")
    dims = _dims_do_nome(p.dados.get("dim", "")) or _dims_do_nome(p.nome)
    if dims is None:
        raise ErroDeDados(f"não consegui ler as dimensões h×bf×D×t de {p.nome}")
    h, bf, d_enr, t = dims
    return propriedades_ue(h, bf, d_enr, t, r=r, nome=p.nome)


def _dims_u_do_nome(texto: str) -> Optional[Tuple[float, float, float]]:
    """Extrai h × bf × t (mm) de 'U 100×50×2,00 (FF)' ou '92×40×2,25'."""
    limpo = (texto.replace("×", "x").replace("X", "x").replace(",", ".")
             .replace("(FF)", " ").replace("(ff)", " "))
    nums = []
    for pedaco in limpo.replace("x", " ").replace("U", " ").replace("u", " ").split():
        try:
            nums.append(float(pedaco))
        except ValueError:
            pass
    if len(nums) == 3:
        return nums[0], nums[1], nums[2]
    return None


def perfis_ue(massa_max: Optional[float] = None,
              altura_max: Optional[float] = None) -> List[Perfil]:
    """Ue do catálogo, do mais leve ao mais pesado (para as buscas)."""
    ps = [p for p in banco().lista("Ue") if p.nome.strip().upper().startswith("UE")]
    if massa_max:
        ps = [p for p in ps if p.massa <= massa_max]
    if altura_max:
        ps = [p for p in ps if p.d <= altura_max]
    return sorted(ps, key=lambda p: (p.massa or 0, p.d))


# =============================================================================
# 2. CARGAS CRÍTICAS ELÁSTICAS
# =============================================================================

def _tensao_placa(k: float, b: float, t: float) -> float:
    """Tensão crítica de flambagem de chapa (NBR 14762, item 9.2, eq. 12):

        σ_cr = k·π²·E / [12·(1 − ν²)·(b/t)²]
    """
    return k * math.pi ** 2 * _D_PLACA / (b / t) ** 2


def tensoes_criticas_locais(sec: SecaoUe, esforco: str = "compressao") -> dict:
    """σ_ℓ de cada elemento da seção, em kN/cm² (NBR 14762, item 9.2/Anexo D).

    **Aproximação adotada** — cada chapa é tratada isoladamente, simplesmente
    apoiada nos bordos ligados às chapas vizinhas (coeficientes k das Tabelas 6 e 7
    da norma), e σ_ℓ da seção é o **menor** entre os elementos. É a hipótese
    clássica do Método da Largura Efetiva. A análise de faixas finitas (CUFSM),
    que a norma admite no item 9.8.1, capta a restrição mútua entre as chapas e
    costuma dar σ_ℓ **maior**; portanto esta estimativa é conservadora quando um
    elemento é bem mais esbelto que os vizinhos, e pode ser ligeiramente contra a
    segurança quando alma e mesa têm esbeltez parecida (nesse caso a interação
    reduz o k da chapa mais robusta). Use valores do fabricante ou do CUFSM quando
    o perfil estiver próximo do limite.

    Para `esforco="flexao"` a tensão devolvida é referida à **fibra extrema
    comprimida** (é a convenção do MRD): o k = 23,9 da alma já é definido assim, e
    para mesa e enrijecedor adota-se, a favor da segurança, a tensão da fibra
    extrema em vez da tensão média do elemento.
    """
    if esforco not in ("compressao", "flexao"):
        raise ErroDeDados("esforco deve ser 'compressao' ou 'flexao'")
    k_alma = K_AA_FLEXAO if esforco == "flexao" else K_AA
    if sec.d <= 0:
        # U simples: a mesa tem um bordo livre (AL) e não há enrijecedor
        return {
            "alma": _tensao_placa(k_alma, sec.bw_plano, sec.t),
            "mesa": _tensao_placa(K_AL, sec.bf_plano, sec.t),
            "enrijecedor": float("inf"),
            "k_alma": k_alma, "k_mesa": K_AL, "k_enrijecedor": None,
        }
    return {
        "alma": _tensao_placa(k_alma, sec.bw_plano, sec.t),
        "mesa": _tensao_placa(K_AA, sec.bf_plano, sec.t),
        "enrijecedor": _tensao_placa(K_AL, sec.d_plano, sec.t),
        "k_alma": k_alma, "k_mesa": K_AA, "k_enrijecedor": K_AL,
    }


def forca_critica_local(sec: SecaoUe, esforco: str = "compressao") -> float:
    """Força (kN) ou momento (kN·cm) crítico de flambagem **local** — item 9.8.

        N_ℓ = σ_ℓ · A            (compressão centrada)
        M_ℓ = σ_ℓ · W_x          (flexão em torno de x)

    σ_ℓ é o menor entre os elementos, calculado por `tensoes_criticas_locais` —
    leia lá a discussão da aproximação (chapas isoladas, e não faixas finitas).
    """
    s = tensoes_criticas_locais(sec, esforco)
    sigma = min(s["alma"], s["mesa"], s["enrijecedor"])
    return sigma * (sec.A if esforco == "compressao" else sec.Wx)


def _mesa_enrijecedor(sec: SecaoUe) -> dict:
    """Propriedades do conjunto mesa+enrijecedor e a posição da dobra com a alma.

    Sistema local paralelo ao global; a "junção" é o encontro das linhas médias
    da alma e da mesa, que é o eixo em torno do qual o conjunto gira no modo
    distorcional.
    """
    rm = sec.r + sec.t / 2.0
    ym = (sec.h - sec.t) / 2.0
    xw, xl = sec.t / 2.0, sec.bf - sec.t / 2.0
    yl = ym - (sec.d - sec.t / 2.0)
    P = [(xw, ym), (xl - rm, ym)]
    P += _arco(xl - rm, ym - rm, rm, math.pi / 2, 0.0)
    P.append((xl, yl))
    P = _limpa(P)
    f = _props_linha(P, sec.t)
    f["xJ"] = xw - f["xc"]        # junção relativa ao centroide da mesa
    f["yJ"] = ym - f["yc"]
    return f


def forca_critica_distorcional(sec: SecaoUe, esforco: str = "compressao",
                               k_mola: float = 0.0) -> float:
    """Força (kN) ou momento (kN·cm) crítico **distorcional** — item 9.8 / Anexo D.

    **Modelo adotado (aproximado, documente no memorial).** O conjunto
    mesa+enrijecedor é tratado como corpo rígido que gira de φ(z) = φ₀·sen(πz/L)
    em torno da dobra mesa–alma, restringido elasticamente pela rigidez à rotação
    da alma. É o mesmo modelo mecânico de Lau & Hancock (1987) e de Schafer, que
    está por trás do Anexo D da NBR 14762 e do Apêndice 2 da AISI S100, aqui na
    versão de **um grau de liberdade** (só a rotação; a translação da junção é
    impedida). Igualando energia de deformação e trabalho das tensões (Rayleigh):

        σ_dist(L) = [ (π/L)⁴·E·(I_yf·y_J² + I_xf·x_J² − 2·I_xyf·x_J·y_J + C_wf)
                      + (π/L)²·G·J_f + k_φ ]
                  / [ (π/L)²·(A_f·(x_J² + y_J²) + I_xf + I_yf + t·b_w³/c_w) ]

    com k_φ = 3·D/b_w (rigidez de rotação da alma com o bordo oposto rotulado,
    D = E·t³/[12(1−ν²)]) e c_w = 52,5 na compressão e 560 na flexão (integral da
    forma cúbica da alma ponderada pela tensão; na flexão só a metade comprimida
    desestabiliza). σ_dist é o mínimo em L, procurado numericamente — o L crítico
    resultante fica em 1,5 a 3 vezes a altura da alma, como se espera do modo
    distorcional.

    O que é **conservador** aqui: k_φ usa só o termo 3D/b_w, desprezando a parcela
    que a alma ganha por ser comprimida em meia-onda longa; e a alma tracionada da
    mesa oposta não é contada como restrição adicional. O que é **contra a
    segurança**: impedir a translação da junção eleva σ_dist frente ao modelo de
    dois graus de liberdade da AISI. Os dois efeitos se compensam em boa parte,
    mas **o resultado não substitui uma análise de faixas finitas nem a tabela do
    fabricante**, que prevalecem.

    `k_mola` (kN·cm/cm por cm de barra) soma a k_φ a restrição à rotação dada pela
    telha ou por um travamento; o padrão 0,0 ignora esse ganho.
    """
    if esforco not in ("compressao", "flexao"):
        raise ErroDeDados("esforco deve ser 'compressao' ou 'flexao'")
    if sec.d <= 0:
        return float("inf")          # U simples: sem enrijecedor não há modo distorcional
    f = _mesa_enrijecedor(sec)
    bw = sec.h - sec.t                      # altura da linha média da alma
    k_phi = 3.0 * _D_PLACA * sec.t ** 3 / bw + max(k_mola, 0.0)
    c_w = 560.0 if esforco == "flexao" else 52.5
    rig_f = (E * (f["Iy"] * f["yJ"] ** 2 + f["Ix"] * f["xJ"] ** 2
                  - 2 * f["Ixy"] * f["xJ"] * f["yJ"] + f["Cw"]))
    geo = (f["A"] * (f["xJ"] ** 2 + f["yJ"] ** 2) + f["Ix"] + f["Iy"]
           + sec.t * bw ** 3 / c_w)
    melhor = float("inf")
    L = 2.0
    while L < 500.0:
        n = math.pi / L
        sigma = (n ** 4 * rig_f + n ** 2 * G * f["J"] + k_phi) / (n ** 2 * geo)
        melhor = min(melhor, sigma)
        L *= 1.01
    return melhor * (sec.A if esforco == "compressao" else sec.Wx)


def forca_critica_global(sec: SecaoUe, KxLx: float = 0.0, KyLy: float = 0.0,
                         KtLt: Optional[float] = None, esforco: str = "compressao",
                         Cb: float = 1.0) -> float:
    """Força (kN) ou momento (kN·cm) crítico de flambagem **global** — item 9.7.2.

    O Ue é **monossimétrico** em relação ao eixo x (o de maior inércia), com o
    centro de torção fora da seção (x₀ ≠ 0). Por isso:

    *Compressão* (item 9.7.2.2) — o menor entre a flambagem por flexão em torno
    de y e a **flexo-torção**, que acopla a flexão em torno do eixo de simetria x
    com a torção:

        N_ey = π²·E·I_y/(K_yL_y)²
        N_ex = π²·E·I_x/(K_xL_x)²
        N_et = [π²·E·C_w/(K_tL_t)² + G·J] / r₀²
        N_exz = (1/2β)·[(N_ex + N_et) − √((N_ex + N_et)² − 4·β·N_ex·N_et)],
                β = 1 − (x₀/r₀)²
        N_e = min(N_ey, N_exz)

    *Flexão em torno de x* (item 9.8.2.2), que é flexão em torno do **eixo de
    simetria** — momento crítico de flambagem lateral com torção:

        M_e = C_b·r₀·A·√(σ_ey·σ_t)

    com σ_ey = π²E/(K_yL_y/r_y)² e σ_t = (1/(A·r₀²))·[G·J + π²·E·C_w/(K_tL_t)²].
    Essa expressão é equivalente à forma (π/L)·√[E·I_y·G·J·(1 + π²·E·C_w/(G·J·L²))]
    quando K_yL_y = K_tL_t.

    `KtLt` é o comprimento **destravado à torção**; em terça com correntes ele
    costuma ser maior que K_yL_y, porque a corrente impede o deslocamento lateral
    mas não o giro da seção. Se omitido, adota-se KtLt = KyLy.
    Comprimento nulo (mesa comprimida contida continuamente) devolve infinito.
    """
    if esforco not in ("compressao", "flexao"):
        raise ErroDeDados("esforco deve ser 'compressao' ou 'flexao'")
    if KtLt is None:
        KtLt = KyLy
    if esforco == "flexao":
        if KyLy <= 0:
            return float("inf")      # mesa comprimida contida continuamente
        sigma_ey = math.pi ** 2 * E / (KyLy / sec.ry) ** 2
        Ct = G * sec.J + (math.pi ** 2 * E * sec.Cw / KtLt ** 2 if KtLt > 0 else 0.0)
        sigma_t = Ct / (sec.A * sec.r0 ** 2)
        return Cb * sec.r0 * sec.A * math.sqrt(sigma_ey * sigma_t)
    Ney = math.pi ** 2 * E * sec.Iy / KyLy ** 2 if KyLy > 0 else float("inf")
    Nex = math.pi ** 2 * E * sec.Ix / KxLx ** 2 if KxLx > 0 else float("inf")
    Net = ((math.pi ** 2 * E * sec.Cw / KtLt ** 2 if KtLt > 0 else 0.0)
           + G * sec.J) / sec.r0 ** 2
    if math.isinf(Nex):
        Nexz = float("inf")
    else:
        beta = 1.0 - (sec.x0 / sec.r0) ** 2
        disc = max((Nex + Net) ** 2 - 4 * beta * Nex * Net, 0.0)
        Nexz = (Nex + Net - math.sqrt(disc)) / (2 * beta)
    return min(Ney, Nexz)


def cb_trecho(Mmax: float, MA: float, MB: float, MC: float) -> float:
    """C_b do trecho destravado (NBR 14762, item 9.8.2.2 — igual à NBR 8800):

        C_b = 12,5·M_max / (2,5·M_max + 3·M_A + 4·M_B + 3·M_C) ≤ 3,0
    """
    Mmax, MA, MB, MC = abs(Mmax), abs(MA), abs(MB), abs(MC)
    den = 2.5 * Mmax + 3 * MA + 4 * MB + 3 * MC
    return min(12.5 * Mmax / den, 3.0) if den > 0 else 1.0


def segmentos_viga_uniforme(n_travamentos: int) -> List[Tuple[float, float]]:
    """Trechos destravados de uma viga biapoiada sob carga uniforme.

    Devolve [(M_max do trecho / (qL²/8), C_b do trecho), ...] para `n_travamentos`
    travamentos laterais igualmente espaçados (as correntes da terça). O trecho
    que governa é escolhido depois, comparando M_Sd/M_Rd de cada um.
    """
    n = max(int(n_travamentos), 0) + 1        # número de trechos
    def m(xi):                                 # momento normalizado por qL²/8
        return 4.0 * xi * (1.0 - xi)
    saida = []
    for i in range(n):
        a, b = i / n, (i + 1) / n
        pontos = [a + (b - a) * f for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
        vals = [m(x) for x in pontos]
        Mmax = max(vals)
        saida.append((Mmax, cb_trecho(Mmax, vals[1], vals[2], vals[3])))
    return saida


# =============================================================================
# 3. MÉTODO DA RESISTÊNCIA DIRETA (MRD) — item 9.8
# =============================================================================

def _chi_global(lambda_0: float) -> float:
    """Fator de redução da flambagem global à compressão (item 9.7.2, eq. 51)."""
    if lambda_0 <= 1.5:
        return 0.658 ** (lambda_0 ** 2)
    return 0.877 / lambda_0 ** 2


def compressao_mrd(sec: SecaoUe, aco, N_Sd: float = 0.0, KxLx: float = 0.0,
                   KyLy: float = 0.0, KtLt: Optional[float] = None,
                   k_mola: float = 0.0, gama: float = GAMA_COMPRESSAO) -> Verificacao:
    """Compressão centrada pelo MRD (NBR 14762:2010, item 9.8.2).

    Devolve o **menor** entre os três modos:

        global        N_c,Re = χ·A·f_y,  λ₀ = √(A·f_y/N_e)
        local         λ_ℓ = √(N_c,Re/N_ℓ);  λ_ℓ ≤ 0,776 → N_c,Rℓ = N_c,Re
                      senão N_c,Rℓ = (1 − 0,15·(N_ℓ/N_c,Re)^0,4)·(N_ℓ/N_c,Re)^0,4·N_c,Re
        distorcional  λ_dist = √(A·f_y/N_dist);  λ_dist ≤ 0,561 → N_c,Rdist = A·f_y
                      senão N_c,Rdist = (1 − 0,25·(N_dist/A f_y)^0,6)·(N_dist/A f_y)^0,6·A·f_y

    N_c,Rd = min(...)/γ, com γ = 1,20 (Tabela 4, compressão centrada).
    """
    if isinstance(aco, str):
        aco = mat.aco(aco)
    fy = aco.fy
    v = Verificacao("Compressão centrada (MRD)", norma="NBR 14762:2010, item 9.8.2",
                    Sd=abs(N_Sd), unidade="kN")
    Afy = sec.A * fy
    Ne = forca_critica_global(sec, KxLx, KyLy, KtLt, "compressao")
    lambda_0 = math.sqrt(Afy / Ne) if Ne != float("inf") else 0.0
    chi = _chi_global(lambda_0)
    NRe = chi * Afy
    v.passo("Escoamento da seção bruta", "N<sub>y</sub> = A·f<sub>y</sub>",
            f"{fmt(sec.A)} × {fmt(fy)}", fmt(Afy, 1, "kN"), "item 9.7.1")
    v.passo("Flambagem global (flexão ou flexo-torção)",
            "N<sub>e</sub>, λ<sub>0</sub> = √(A·f<sub>y</sub>/N<sub>e</sub>), χ",
            f"N<sub>e</sub> = {fmt(Ne, 0)} kN; λ<sub>0</sub> = {fmt(lambda_0, 3)}",
            f"χ = {fmt(chi, 3)} → N<sub>c,Re</sub> = {fmt(NRe, 1, 'kN')}", "item 9.7.2")

    Nl = forca_critica_local(sec, "compressao")
    lam_l = math.sqrt(NRe / Nl)
    if lam_l <= 0.776:
        NRl = NRe
    else:
        rr = Nl / NRe
        NRl = (1 - 0.15 * rr ** 0.4) * rr ** 0.4 * NRe
    v.passo("Flambagem local",
            "λ<sub>ℓ</sub> = √(N<sub>c,Re</sub>/N<sub>ℓ</sub>)",
            f"N<sub>ℓ</sub> = {fmt(Nl, 0)} kN; λ<sub>ℓ</sub> = {fmt(lam_l, 3)}",
            f"N<sub>c,Rℓ</sub> = {fmt(NRl, 1, 'kN')}", "item 9.8.2.2")

    Nd = forca_critica_distorcional(sec, "compressao", k_mola)
    lam_d = math.sqrt(Afy / Nd)
    if lam_d <= 0.561:
        NRd_dist = Afy
    else:
        rr = Nd / Afy
        NRd_dist = (1 - 0.25 * rr ** 0.6) * rr ** 0.6 * Afy
    v.passo("Flambagem distorcional",
            "λ<sub>dist</sub> = √(A·f<sub>y</sub>/N<sub>dist</sub>)",
            f"N<sub>dist</sub> = {fmt(Nd, 0)} kN; λ<sub>dist</sub> = {fmt(lam_d, 3)}",
            f"N<sub>c,Rdist</sub> = {fmt(NRd_dist, 1, 'kN')}", "item 9.8.2.3")

    modos = {"global": NRe, "local": NRl, "distorcional": NRd_dist}
    modo = min(modos, key=modos.get)
    v.Rd = modos[modo] / gama
    v.passo("Resistência de cálculo", "N<sub>c,Rd</sub> = min(...)/γ",
            f"{fmt(modos[modo], 1)}/{gama:.2f} (governa: {modo})",
            fmt(v.Rd, 1, "kN"), "Tabela 4")
    v.observacao = (f"Modo governante: {modo}. Cargas críticas local e distorcional "
                    "por expressões analíticas aproximadas — ver docstring.")
    return v


def flexao_mrd(sec: SecaoUe, aco, M_Sd: float = 0.0, Lb: float = 0.0,
               Lt: Optional[float] = None, Cb: float = 1.0, k_mola: float = 0.0,
               gama: float = GAMA, titulo: str = "Flexão em torno de x (MRD)"
               ) -> Verificacao:
    """Flexão em torno do eixo x pelo MRD (NBR 14762:2010, item 9.8.2).

        global (FLT)  λ₀ = √(W_x·f_y/M_e)
                      λ₀ ≤ 0,6      → M_Re = W_x·f_y
                      0,6 < λ₀ < 1,336 → M_Re = 1,11·W_x·f_y·(1 − 0,278·λ₀²)
                      λ₀ ≥ 1,336    → M_Re = W_x·f_y/λ₀²  (= M_e)
        local         λ_ℓ = √(M_Re/M_ℓ); ≤ 0,776 → M_Rℓ = M_Re, senão
                      M_Rℓ = (1 − 0,15·(M_ℓ/M_Re)^0,4)·(M_ℓ/M_Re)^0,4·M_Re
        distorcional  λ_dist = √(W_x·f_y/M_dist); ≤ 0,673 → M_Rdist = W_x·f_y,
                      senão M_Rdist = (1 − 0,22·(M_dist/W_x f_y)^0,5)·(M_dist/W_x f_y)^0,5·W_x·f_y

    `Lb` é o comprimento destravado lateralmente (0 = mesa comprimida contida
    continuamente, caso da terça sob carga gravitacional com a telha fixada);
    `Lt` é o comprimento destravado **à torção** (padrão: igual a Lb). Momentos
    em kN·cm.
    """
    if isinstance(aco, str):
        aco = mat.aco(aco)
    fy = aco.fy
    v = Verificacao(titulo, norma="NBR 14762:2010, item 9.8.2",
                    Sd=abs(M_Sd), unidade="kN·cm")
    My = sec.Wx * fy
    Me = forca_critica_global(sec, 0.0, Lb, Lt, "flexao", Cb)
    if math.isinf(Me):
        lambda_0, MRe = 0.0, My
    else:
        lambda_0 = math.sqrt(My / Me)
        if lambda_0 <= 0.6:
            MRe = My
        elif lambda_0 < 1.336:
            MRe = 1.11 * My * (1 - 0.278 * lambda_0 ** 2)
        else:
            MRe = My / lambda_0 ** 2
    v.passo("Início de escoamento da seção bruta",
            "M<sub>y</sub> = W<sub>x</sub>·f<sub>y</sub>",
            f"{fmt(sec.Wx)} × {fmt(fy)}", fmt(My, 0, "kN·cm"), "item 9.8.2.1")
    v.passo("Flambagem lateral com torção (global)",
            "M<sub>e</sub> = C<sub>b</sub>·r<sub>0</sub>·A·√(σ<sub>ey</sub>·σ<sub>t</sub>)",
            (f"L<sub>b</sub> = {fmt(Lb, 0)} cm; L<sub>t</sub> = "
             f"{fmt(Lb if Lt is None else Lt, 0)} cm; C<sub>b</sub> = {fmt(Cb, 2)}; "
             f"M<sub>e</sub> = {'∞' if math.isinf(Me) else fmt(Me, 0)} kN·cm; "
             f"λ<sub>0</sub> = {fmt(lambda_0, 3)}"),
            f"M<sub>Re</sub> = {fmt(MRe, 0, 'kN·cm')} (χ<sub>FLT</sub> = "
            f"{fmt(MRe / My, 3)})", "item 9.8.2.2")

    Ml = forca_critica_local(sec, "flexao")
    lam_l = math.sqrt(MRe / Ml)
    if lam_l <= 0.776:
        MRl = MRe
    else:
        rr = Ml / MRe
        MRl = (1 - 0.15 * rr ** 0.4) * rr ** 0.4 * MRe
    v.passo("Flambagem local", "λ<sub>ℓ</sub> = √(M<sub>Re</sub>/M<sub>ℓ</sub>)",
            f"M<sub>ℓ</sub> = {fmt(Ml, 0)} kN·cm; λ<sub>ℓ</sub> = {fmt(lam_l, 3)}",
            f"M<sub>Rℓ</sub> = {fmt(MRl, 0, 'kN·cm')}", "item 9.8.2.2")

    Md = forca_critica_distorcional(sec, "flexao", k_mola)
    lam_d = math.sqrt(My / Md)
    if lam_d <= 0.673:
        MRdist = My
    else:
        rr = Md / My
        MRdist = (1 - 0.22 * rr ** 0.5) * rr ** 0.5 * My
    v.passo("Flambagem distorcional",
            "λ<sub>dist</sub> = √(W<sub>x</sub>·f<sub>y</sub>/M<sub>dist</sub>)",
            f"M<sub>dist</sub> = {fmt(Md, 0)} kN·cm; λ<sub>dist</sub> = {fmt(lam_d, 3)}",
            f"M<sub>Rdist</sub> = {fmt(MRdist, 0, 'kN·cm')}", "item 9.8.2.3")

    modos = {"global (FLT)": MRe, "local": MRl, "distorcional": MRdist}
    modo = min(modos, key=modos.get)
    v.Rd = modos[modo] / gama
    v.passo("Momento resistente de cálculo", "M<sub>Rd</sub> = min(...)/γ",
            f"{fmt(modos[modo], 0)}/{gama:.2f} (governa: {modo})",
            fmt(v.Rd, 0, "kN·cm"), "Tabela 4")
    v.observacao = f"Modo governante: {modo}."
    return v


def flexao_em_y_mrd(sec: SecaoUe, aco, M_Sd: float = 0.0,
                    gama: float = GAMA) -> Verificacao:
    """Flexão em torno de y (componente paralela ao plano do telhado).

    Em torno do eixo de menor inércia não há flambagem lateral com torção
    (item 9.8.2.2 dispensa a verificação quando a flexão se dá em torno do eixo
    perpendicular ao de simetria, com a seção livre para deslocar no plano de
    maior rigidez). Restam o escoamento da fibra extrema e a flambagem local e
    distorcional, tratadas aqui com o mesmo W_y a favor da segurança.
    """
    if isinstance(aco, str):
        aco = mat.aco(aco)
    v = Verificacao("Flexão em torno de y", norma="NBR 14762:2010, item 9.8.2",
                    Sd=abs(M_Sd), unidade="kN·cm")
    My = sec.Wy * aco.fy
    # a flambagem local da mesa sob gradiente é menos severa; usa-se σ_ℓ da mesa
    s = tensoes_criticas_locais(sec, "compressao")
    sigma_l = min(s["mesa"], s["enrijecedor"])
    Ml = sigma_l * sec.Wy
    lam_l = math.sqrt(My / Ml)
    MR = My if lam_l <= 0.776 else (
        (1 - 0.15 * (Ml / My) ** 0.4) * (Ml / My) ** 0.4 * My)
    v.Rd = MR / gama
    v.passo("Escoamento da fibra extrema (ponta da mesa)",
            "M<sub>y,Rd</sub> = W<sub>y</sub>·f<sub>y</sub>/γ",
            f"{fmt(sec.Wy)} × {fmt(aco.fy)} / {gama:.2f}",
            fmt(v.Rd, 0, "kN·cm"), "item 9.8.2.1")
    return v


# =============================================================================
# 4. MÉTODO DA SEÇÃO EFETIVA (MSE) — item 9.7 / larguras efetivas item 9.2
# =============================================================================

def largura_efetiva(b: float, t: float, sigma: float, k: float = K_AA) -> float:
    """Largura efetiva de uma chapa comprimida — método de Winter (item 9.2.1).

        λ_p = √(σ/σ_cr),  σ_cr = k·π²E/[12(1−ν²)(b/t)²]
        λ_p ≤ 0,673 → b_ef = b
        λ_p > 0,673 → b_ef = b·(1 − 0,22/λ_p)/λ_p

    `b` largura plana do elemento (cm), `sigma` tensão de compressão atuante no
    elemento (kN/cm²).
    """
    if b <= 0 or t <= 0:
        raise ErroDeDados("largura e espessura devem ser positivas")
    if sigma <= 0:
        return b
    sigma_cr = _tensao_placa(k, b, t)
    lam_p = math.sqrt(sigma / sigma_cr)
    if lam_p <= 0.673:
        return b
    return b * (1 - 0.22 / lam_p) / lam_p


def coeficiente_mesa_enrijecida(sec: SecaoUe, sigma: float) -> dict:
    """k da mesa com enrijecedor de borda e eficiência do enrijecedor (item 9.2.2).

        S  = 1,28·√(E/σ)
        I_a = 399·t⁴·[(b/t)/S − 0,328]³ ≤ t⁴·[115·(b/t)/S + 5]
        I_s = D³·t/12  (enrijecedor a 90°)
        R_I = min(I_s/I_a ; 1)
        n  = max(0,582 − (b/t)/(4S) ; 1/3)
        k  = min(R_I^n·(k_a − k_u) + k_u ; k_a),  k_a = 4,0, k_u = 0,43
    """
    b_t = sec.bf_plano / sec.t
    S = 1.28 * math.sqrt(E / sigma)
    Ia = 399 * sec.t ** 4 * max((b_t / S - 0.328), 0.0) ** 3
    Ia = min(Ia, sec.t ** 4 * (115 * b_t / S + 5))
    Is = sec.d_plano ** 3 * sec.t / 12.0
    RI = min(Is / Ia, 1.0) if Ia > 0 else 1.0
    n = max(0.582 - b_t / (4 * S), 1.0 / 3.0)
    k = min(RI ** n * (K_AA - K_AL) + K_AL, K_AA)
    return {"S": S, "Ia": Ia, "Is": Is, "RI": RI, "n": n, "k": k}


def _pecas_efetivas(sec: SecaoUe, fy: float, esforco: str, y_na: float) -> List[list]:
    """Constrói as polilinhas da seção efetiva (partes não efetivas removidas).

    y_na: ordenada da linha neutra (cm), na convenção do `_trechos_ue`
    (y = 0 na meia altura). Para compressão centrada use y_na = None.
    """
    trechos = _trechos(sec)
    y_top = sec.h / 2.0
    cm = coeficiente_mesa_enrijecida(sec, fy)      # U simples: D = 0 → R_I = 0 → k = 0,43
    pecas = []
    for tr in trechos:
        if tr["elem"] == "canto":
            pecas.append(tr["pts"])            # cantos sempre efetivos
            continue
        (x1, y1), (x2, y2) = tr["reta"]
        b = math.hypot(x2 - x1, y2 - y1)

        def corta(inicio, fim):
            """Sub-segmento entre as abscissas curvilíneas inicio e fim."""
            f0, f1 = max(inicio / b, 0.0), min(fim / b, 1.0)
            if f1 - f0 <= 1e-9:
                return None
            return [(x1 + (x2 - x1) * f0, y1 + (y2 - y1) * f0),
                    (x1 + (x2 - x1) * f1, y1 + (y2 - y1) * f1)]

        if tr["elem"] == "alma":
            if esforco == "compressao":
                bef = largura_efetiva(b, sec.t, fy, K_AA)
                for pc in (corta(0, bef / 2), corta(b - bef / 2, b)):
                    if pc:
                        pecas.append(pc)
                continue
            # flexão: gradiente de tensões; o trecho vai de y1 (tração) a y2 (compressão)
            sig = lambda y: fy * (y - y_na) / (y_top - y_na)
            f1_, f2_ = sig(y2), sig(y1)        # f1 = bordo mais comprimido
            if f1_ <= 0:                        # alma toda tracionada
                pecas.append(tr["pts"])
                continue
            psi = f2_ / f1_
            kw = 4 + 2 * (1 - psi) ** 3 + 2 * (1 - psi)
            bef = largura_efetiva(b, sec.t, f1_, kw)
            b1 = bef / (3 - psi)
            b2 = bef / 2.0 if psi < -0.236 else bef - b1
            # parte comprimida da alma, medida a partir do bordo comprimido (y2)
            bc = b if psi >= 0 else b * f1_ / (f1_ - f2_)
            if b1 + b2 >= bc:                   # alma totalmente efetiva
                pecas.append(tr["pts"])
                continue
            # y2 é o topo; s medido de y1 (base). Bordo comprimido em s = b.
            for pc in (corta(b - b1, b), corta(b - bc, b - bc + b2),
                       corta(0, b - bc)):
                if pc:
                    pecas.append(pc)
            continue

        if tr["elem"] in ("mesa_sup", "mesa_inf"):
            y_mesa = y1
            sigma = fy if esforco == "compressao" else fy * (y_mesa - y_na) / (y_top - y_na)
            if sigma <= 0:
                pecas.append(tr["pts"])         # mesa tracionada: toda efetiva
                continue
            bef = largura_efetiva(b, sec.t, sigma, cm["k"])
            if sec.d <= 0:
                # U simples: mesa AL, a parte efetiva encosta na dobra com a alma
                # (mesa_inf vai da ponta livre à dobra; mesa_sup, da dobra à ponta)
                pc = corta(b - bef, b) if tr["elem"] == "mesa_inf" else corta(0, bef)
                if pc:
                    pecas.append(pc)
                continue
            for pc in (corta(0, bef / 2), corta(b - bef / 2, b)):
                if pc:
                    pecas.append(pc)
            continue

        # enrijecedor: elemento AL, apoiado na dobra com a mesa e livre na ponta
        y_mesa = y2 if tr["elem"] == "enr_sup" else y1     # extremo junto à mesa
        sigma = fy if esforco == "compressao" else fy * (y_mesa - y_na) / (y_top - y_na)
        if sigma <= 0:
            pecas.append(tr["pts"])
            continue
        ds = largura_efetiva(b, sec.t, sigma, K_AL) * cm["RI"]
        # o trecho 'enr_sup' vai da dobra (s=0) à ponta; 'enr_inf' vai da ponta à dobra
        pc = corta(0, ds) if tr["elem"] == "enr_sup" else corta(b - ds, b)
        if pc:
            pecas.append(pc)
    return pecas


def secao_efetiva(sec: SecaoUe, aco, esforco: str = "compressao",
                  iteracoes: int = 20) -> dict:
    """Seção efetiva pelo MSE/MLE (NBR 14762:2010, itens 9.2 e 9.7).

    Devolve `{"Aef", "Wef", "y_na", "k_mesa", "RI", "passos"}` com as propriedades
    da seção reduzida (cm² e cm³). Para `esforco="flexao"` a posição da linha
    neutra é iterada, porque ao remover a parte não efetiva da alma comprimida a
    linha neutra desce — o processo converge em poucas iterações.

    Os cantos arredondados são mantidos integralmente efetivos, como permite o
    método linear. Este caminho é **alternativo** ao MRD; para terças o módulo usa
    o MRD, e o MSE serve de conferência e para os casos em que o projetista
    prefira o item 9.7.
    """
    if isinstance(aco, str):
        aco = mat.aco(aco)
    if esforco not in ("compressao", "flexao"):
        raise ErroDeDados("esforco deve ser 'compressao' ou 'flexao'")
    fy = aco.fy
    cm = coeficiente_mesa_enrijecida(sec, fy)
    if esforco == "compressao":
        p = _props_pecas(_pecas_efetivas(sec, fy, "compressao", 0.0), sec.t)
        return {"Aef": p["A"], "Wef": None, "y_na": None,
                "k_mesa": cm["k"], "RI": cm["RI"],
                "obs": "A_ef na tensão f_y (item 9.7.1)"}
    y_na = 0.0
    p = None
    for _ in range(iteracoes):
        pecas = _pecas_efetivas(sec, fy, "flexao", y_na)
        p = _props_pecas(pecas, sec.t)
        novo = p["yc"]
        if abs(novo - y_na) < 1e-6:
            y_na = novo
            break
        y_na = 0.5 * (y_na + novo)        # relaxação, para convergir sempre
    y_top = sec.h / 2.0
    Wef = p["Ix"] / max(y_top - y_na, 1e-9)
    return {"Aef": p["A"], "Wef": Wef, "Ief": p["Ix"], "y_na": y_na,
            "k_mesa": cm["k"], "RI": cm["RI"],
            "obs": "W_ef referido à fibra extrema comprimida (item 9.7.3)"}


def flexao_mse(sec: SecaoUe, aco, M_Sd: float = 0.0, Lb: float = 0.0,
               Lt: Optional[float] = None, Cb: float = 1.0,
               gama: float = GAMA) -> Verificacao:
    """Flexão pelo MSE (item 9.7.3): M_Rd = χ_FLT·W_ef·f_y/γ.

    A flambagem distorcional **não** está incluída aqui — pelo item 9.7.3 ela é
    verificada à parte. Use `flexao_mrd` para o dimensionamento; esta função é
    conferência do caminho alternativo.
    """
    if isinstance(aco, str):
        aco = mat.aco(aco)
    ef = secao_efetiva(sec, aco, "flexao")
    Me = forca_critica_global(sec, 0.0, Lb, Lt, "flexao", Cb)
    My = sec.Wx * aco.fy
    if math.isinf(Me):
        chi = 1.0
    else:
        lam = math.sqrt(My / Me)
        if lam <= 0.6:
            chi = 1.0
        elif lam < 1.336:
            chi = 1.11 * (1 - 0.278 * lam ** 2)
        else:
            chi = 1.0 / lam ** 2
    v = Verificacao("Flexão em torno de x (MSE)",
                    norma="NBR 14762:2010, item 9.7.3", Sd=abs(M_Sd), unidade="kN·cm")
    v.Rd = chi * ef["Wef"] * aco.fy / gama
    v.passo("Seção efetiva", "W<sub>ef</sub> (larguras efetivas de Winter)",
            f"A<sub>ef</sub> = {fmt(ef['Aef'])} cm²; k<sub>mesa</sub> = "
            f"{fmt(ef['k_mesa'], 2)}; R<sub>I</sub> = {fmt(ef['RI'], 2)}",
            fmt(ef["Wef"], 2, "cm³"), "itens 9.2.1 e 9.2.2")
    v.passo("Momento resistente",
            "M<sub>Rd</sub> = χ<sub>FLT</sub>·W<sub>ef</sub>·f<sub>y</sub>/γ",
            f"{fmt(chi, 3)} × {fmt(ef['Wef'], 2)} × {fmt(aco.fy)} / {gama:.2f}",
            fmt(v.Rd, 0, "kN·cm"), "item 9.7.3")
    v.observacao = "Flambagem distorcional verificada à parte (item 9.7.3)."
    return v


# =============================================================================
# 5. CISALHAMENTO, ESMAGAMENTO DA ALMA E INTERAÇÕES
# =============================================================================

def cisalhamento(sec: SecaoUe, aco, V_Sd: float = 0.0, kv: float = 5.0,
                 gama: float = GAMA) -> Verificacao:
    """Força cortante na alma (NBR 14762:2010, item 9.7.4).

        V_Rd = (1/γ)·min[ 0,60·f_y·h·t ;
                          0,64·t²·√(k_v·f_y·E) ;
                          0,905·E·k_v·t³/h ]

    As três parcelas são, na ordem, o escoamento por cisalhamento, a flambagem
    inelástica e a flambagem elástica da alma; o mínimo reproduz exatamente os
    três ramos da norma e é contínuo nas transições. k_v = 5,0 para alma sem
    enrijecedores transversais.
    """
    if isinstance(aco, str):
        aco = mat.aco(aco)
    h, t, fy = sec.bw_plano, sec.t, aco.fy
    esc = 0.60 * fy * h * t
    inel = 0.64 * t ** 2 * math.sqrt(kv * fy * E)
    elas = 0.905 * E * kv * t ** 3 / h
    Vn = min(esc, inel, elas)
    v = Verificacao("Força cortante na alma", norma="NBR 14762:2010, item 9.7.4",
                    Sd=abs(V_Sd), Rd=Vn / gama, unidade="kN")
    v.passo("Esbeltez da alma", "h/t", f"{fmt(h)}/{fmt(t)}",
            fmt(h / t, 1), "item 9.7.4")
    v.passo("Parcelas de resistência",
            "0,60·f<sub>y</sub>·h·t | 0,64·t²·√(k<sub>v</sub>f<sub>y</sub>E) | "
            "0,905·E·k<sub>v</sub>·t³/h",
            f"{fmt(esc, 1)} | {fmt(inel, 1)} | {fmt(elas, 1)} kN",
            fmt(Vn, 1, "kN"), "item 9.7.4")
    v.passo("Resistência de cálculo", "V<sub>Rd</sub> = V<sub>n</sub>/γ",
            f"{fmt(Vn, 1)}/{gama:.2f}", fmt(v.Rd, 1, "kN"), "Tabela 4")
    return v


def esmagamento_alma(sec: SecaoUe, aco, R_Sd: float = 0.0, N_apoio: float = 10.0,
                     posicao: str = "extremidade", mesa_fixada: bool = True,
                     theta: float = 90.0, gama: float = GAMA) -> Verificacao:
    """Esmagamento (enrugamento) da alma sob reação de apoio — item 9.9.

        R_n = C·t²·f_y·senθ·(1 − C_R·√(r/t))·(1 + C_N·√(N/t))·(1 − C_h·√(h/t))

    Coeficientes da Tabela 22 para seções U e Ue com mesas enrijecidas e carga
    aplicada numa única mesa (Tabela `_ESMAGAMENTO`). `N_apoio` é o comprimento de
    apoio em cm (comprimento da chapa de terça, por exemplo); `posicao` é
    "extremidade" (terça biapoiada) ou "interior" (terça contínua sobre o pórtico).

    Em terça apoiada sobre chapa curta este estado-limite costuma ser decisivo:
    é a alma fina amassando sobre o apoio, e nenhuma verificação de flexão avisa.
    """
    if isinstance(aco, str):
        aco = mat.aco(aco)
    if posicao not in ("extremidade", "interior"):
        raise ErroDeDados("posicao deve ser 'extremidade' ou 'interior'")
    if N_apoio <= 0:
        raise ErroDeDados("comprimento de apoio N deve ser positivo (cm)")
    C, CR, CN, Ch = _ESMAGAMENTO[(bool(mesa_fixada), posicao)]
    t, h, r, fy = sec.t, sec.bw_plano, sec.r, aco.fy
    Rn = (C * t ** 2 * fy * math.sin(math.radians(theta))
          * (1 - CR * math.sqrt(r / t))
          * (1 + CN * math.sqrt(N_apoio / t))
          * (1 - Ch * math.sqrt(h / t)))
    v = Verificacao(f"Esmagamento da alma no apoio ({posicao})",
                    norma="NBR 14762:2010, item 9.9", Sd=abs(R_Sd),
                    Rd=max(Rn, 0.0) / gama, unidade="kN")
    v.passo("Coeficientes da Tabela 22",
            "C | C<sub>R</sub> | C<sub>N</sub> | C<sub>h</sub>",
            f"{C:g} | {CR:g} | {CN:g} | {Ch:g} "
            f"({'mesa fixada ao apoio' if mesa_fixada else 'mesa não fixada'})",
            "", "Tabela 22")
    v.passo("Resistência nominal",
            "R<sub>n</sub> = C·t²·f<sub>y</sub>·senθ·(1−C<sub>R</sub>√(r/t))·"
            "(1+C<sub>N</sub>√(N/t))·(1−C<sub>h</sub>√(h/t))",
            f"C={C:g}; t={fmt(t)} cm; N={fmt(N_apoio)} cm; r/t={fmt(r / t, 2)}; "
            f"h/t={fmt(h / t, 1)}", fmt(Rn, 1, "kN"), "item 9.9")
    v.passo("Resistência de cálculo", "R<sub>Rd</sub> = R<sub>n</sub>/γ",
            f"{fmt(Rn, 1)}/{gama:.2f}", fmt(v.Rd, 1, "kN"), "Tabela 4")
    if N_apoio / t > 210 or sec.bw_plano / sec.t > 200:
        v.observacao = ("Fora dos limites de validade da Tabela 22 (N/t ≤ 210, "
                        "h/t ≤ 200): resultado apenas indicativo.")
    return v


def interacao_momento_cortante(M_Sd: float, M_Rd: float, V_Sd: float,
                               V_Rd: float) -> Verificacao:
    """Interação momento–força cortante (item 9.8.4), alma sem enrijecedores:

        (M_Sd/M_Rd)² + (V_Sd/V_Rd)² ≤ 1,0
    """
    rm = abs(M_Sd) / M_Rd if M_Rd else float("inf")
    rv = abs(V_Sd) / V_Rd if V_Rd else float("inf")
    val = math.sqrt(rm ** 2 + rv ** 2)
    v = Verificacao("Interação momento–cortante",
                    norma="NBR 14762:2010, item 9.8.4", Sd=val, Rd=1.0, unidade="—")
    v.passo("Equação de interação",
            "√[(M<sub>Sd</sub>/M<sub>Rd</sub>)² + (V<sub>Sd</sub>/V<sub>Rd</sub>)²] ≤ 1",
            f"√[{fmt(rm, 3)}² + {fmt(rv, 3)}²]", fmt(val, 3), "item 9.8.4")
    return v


def interacao_flexao_obliqua(Mx_Sd: float, Mx_Rd: float, My_Sd: float,
                             My_Rd: float) -> Verificacao:
    """Flexão oblíqua (item 9.8.2.5): M_x,Sd/M_x,Rd + M_y,Sd/M_y,Rd ≤ 1,0."""
    rx = abs(Mx_Sd) / Mx_Rd if Mx_Rd else float("inf")
    ry = abs(My_Sd) / My_Rd if My_Rd else float("inf")
    v = Verificacao("Flexão oblíqua (Mx + My)",
                    norma="NBR 14762:2010, item 9.8.2.5", Sd=rx + ry, Rd=1.0,
                    unidade="—")
    v.passo("Equação de interação",
            "M<sub>x,Sd</sub>/M<sub>x,Rd</sub> + M<sub>y,Sd</sub>/M<sub>y,Rd</sub> ≤ 1",
            f"{fmt(rx, 3)} + {fmt(ry, 3)}", fmt(rx + ry, 3), "item 9.8.2.5")
    return v


def flecha(w_servico_kN_cm: float, vao_cm: float, I: float,
           limite: float = 180.0, titulo: str = "Flecha") -> Verificacao:
    """Flecha de viga biapoiada sob carga uniforme: δ = 5wL⁴/(384·E·I).

    `limite` é o denominador de L/limite (NBR 14762, Anexo C / NBR 8800, Anexo C:
    L/180 para terças sob carga gravitacional e L/120 sob vento de sucção, salvo
    exigência do fabricante da telha).
    """
    d = 5 * abs(w_servico_kN_cm) * vao_cm ** 4 / (384.0 * E * I)
    v = Verificacao(titulo, norma="NBR 14762:2010, Anexo C", Sd=d,
                    Rd=vao_cm / limite, unidade="cm")
    v.passo("Flecha no meio do vão", "δ = 5·w·L⁴/(384·E·I)",
            f"5 × {fmt(abs(w_servico_kN_cm), 5)} × {fmt(vao_cm, 0)}⁴ / "
            f"(384 × {fmt(E, 0)} × {fmt(I, 0)})", fmt(d, 2, "cm"), "Anexo C")
    v.passo("Limite", f"L/{limite:g}", f"{fmt(vao_cm, 0)}/{limite:g}",
            fmt(vao_cm / limite, 2, "cm"), "Anexo C")
    return v


# =============================================================================
# 6. TERÇA / LONGARINA
# =============================================================================

def terca(perfil_ue, aco="CF-26 (NBR 6650)", vao: float = 5.0,
          carga_gravidade: float = 0.0, carga_succao: float = 0.0,
          n_correntes: int = 1, *,
          inclinacao: float = 0.0,
          carga_servico_gravidade: Optional[float] = None,
          carga_servico_succao: Optional[float] = None,
          comprimento_apoio: float = 10.0,
          apoio: str = "extremidade",
          telha_trava_mesa: bool = True,
          correntes_travam_torcao: bool = False,
          k_mola: float = 0.0,
          limite_flecha_gravidade: float = 180.0,
          limite_flecha_succao: float = 120.0,
          raio_dobra: Optional[float] = None,
          elemento: str = "Terça") -> Resultado:
    """Verificação completa de uma terça (ou longarina) Ue — NBR 14762:2010.

    Unidades de entrada (linguagem da interface):
        vao                  m
        carga_gravidade      kN/m **de cálculo**, positiva para baixo (ELU)
        carga_succao         kN/m **de cálculo**, positiva = sucção (para cima)
        carga_servico_*      kN/m de serviço para a flecha; se omitido, adota-se
                             a carga de cálculo dividida por 1,4
        inclinacao           graus (inclinação do telhado)
        comprimento_apoio    cm (comprimento de apoio sobre a chapa de terça)

    O que é verificado
    ------------------
    * **Gravidade** — a telha fixada trava continuamente a mesa superior
      (comprimida), então L_b = 0 e não há FLT (`telha_trava_mesa=True`). A
      componente da carga paralela ao plano do telhado dá flexão em torno de y,
      com vão igual ao espaçamento das correntes; entra na interação de flexão
      oblíqua do item 9.8.2.5.
    * **Sucção** — a mesa **inferior** fica comprimida e não é travada pela telha.
      L_b = vão/(n_correntes + 1). As correntes impedem o deslocamento lateral,
      mas **não** o giro da seção: por isso o comprimento destravado à torção é
      adotado igual ao vão inteiro (`correntes_travam_torcao=False`, padrão).
      Passe `True` só se houver travamento efetivo à torção (mão-francesa,
      travamento de mesa a mesa) nos pontos de corrente. C_b é calculado trecho a
      trecho e o trecho governante é o que tem a maior razão M_Sd/M_Rd.
    * **Cortante**, **esmagamento da alma no apoio**, **interação M–V** e
      **flechas** (L/180 na gravidade e L/120 na sucção, ajustáveis).

    Devolve um `Resultado` com todas as verificações e, em `.dados`, a geometria
    adotada, L_b, C_b, os momentos e as razões — é de lá que o memorial e os
    desenhos leem.
    """
    if isinstance(aco, str):
        aco = mat.aco(aco)
    sec = (perfil_ue if isinstance(perfil_ue, SecaoUe)
           else secao_do_perfil(perfil_ue, r=raio_dobra))
    if vao <= 0:
        raise ErroDeDados(f"vão deve ser positivo (recebido: {vao} m)")
    if n_correntes < 0:
        raise ErroDeDados("número de linhas de correntes não pode ser negativo")
    if carga_gravidade < 0:
        raise ErroDeDados("carga_gravidade é positiva para baixo (kN/m)")
    if carga_succao < 0:
        raise ErroDeDados("carga_succao é positiva no sentido da sucção (kN/m)")

    L = vao * 100.0                       # cm
    Lb = L / (n_correntes + 1)
    Lt = Lb if correntes_travam_torcao else L
    theta = math.radians(inclinacao)
    wg = carga_gravidade / 100.0          # kN/cm
    ws = carga_succao / 100.0
    wg_s = (carga_servico_gravidade if carga_servico_gravidade is not None
            else carga_gravidade / 1.4) / 100.0
    ws_s = (carga_servico_succao if carga_servico_succao is not None
            else carga_succao / 1.4) / 100.0

    r = Resultado(f"{elemento} L = {vao:g} m", perfil=sec.nome, material=aco.nome)
    segs = segmentos_viga_uniforme(n_correntes)

    # ---------- gravidade ----------
    Mx_g = wg * math.cos(theta) * L ** 2 / 8.0
    My_g = wg * math.sin(theta) * Lb ** 2 / 8.0
    Lb_g = 0.0 if telha_trava_mesa else Lb
    Lt_g = 0.0 if telha_trava_mesa else Lt
    vg = flexao_mrd(sec, aco, Mx_g, Lb_g, Lt_g, Cb=1.0, k_mola=k_mola,
                    titulo="Flexão Mx — combinação gravitacional")
    if telha_trava_mesa:
        vg.observacao += (" Mesa comprimida (superior) contida continuamente pela "
                          "telha: L_b = 0, sem FLT.")
    r.add(vg)
    if inclinacao > 0:
        vy = flexao_em_y_mrd(sec, aco, My_g)
        vy.titulo = "Flexão My — componente no plano do telhado"
        vy.observacao = (f"Vão de flexão em y = espaçamento das correntes "
                         f"({fmt(Lb, 0)} cm), tratado como biapoiado — conservador.")
        r.add(vy)
        r.add(interacao_flexao_obliqua(Mx_g, vg.Rd, My_g, vy.Rd))

    # ---------- sucção ----------
    Mx_s_total = ws * L ** 2 / 8.0
    v_suc = None
    if carga_succao > 0:
        pior = None
        for (m_rel, Cb) in segs:
            vv = flexao_mrd(sec, aco, Mx_s_total * m_rel, Lb, Lt, Cb=Cb,
                            k_mola=k_mola,
                            titulo="Flexão Mx — combinação de sucção "
                                   "(mesa inferior comprimida)")
            if pior is None or vv.razao > pior.razao:
                pior = vv
                pior_cb = Cb
        v_suc = pior
        v_suc.observacao += (
            f" Mesa comprimida é a inferior, livre: L_b = {fmt(Lb, 0)} cm "
            f"({n_correntes} linha(s) de corrente); L_t = {fmt(Lt, 0)} cm "
            f"({'correntes travam a torção' if correntes_travam_torcao else 'as correntes travam o deslocamento lateral, não o giro'}); "
            f"C_b = {fmt(pior_cb, 2)}.")
        r.add(v_suc)

    # ---------- cortante e apoio ----------
    w_max = max(wg, ws)
    V_Sd = w_max * L / 2.0
    vc = cisalhamento(sec, aco, V_Sd)
    r.add(vc)
    ve = esmagamento_alma(sec, aco, V_Sd, comprimento_apoio, apoio,
                          mesa_fixada=True)
    r.add(ve)

    # interação M-V no apoio é nula (M = 0 ali); a norma exige a verificação onde
    # M e V coexistem — em viga biapoiada sob carga uniforme o ponto crítico é o
    # trecho a 1/4 do vão, onde M = 0,75·M_max e V = 0,5·V_max
    M_ref = max(Mx_g, Mx_s_total)
    M_Rd_ref = min([v.Rd for v in (vg, v_suc) if v is not None])
    r.add(interacao_momento_cortante(0.75 * M_ref, M_Rd_ref, 0.5 * V_Sd, vc.Rd))

    # ---------- flechas ----------
    if wg_s > 0:
        r.add(flecha(wg_s, L, sec.Ix, limite_flecha_gravidade,
                     f"Flecha — gravidade (L/{limite_flecha_gravidade:g})"))
    if ws_s > 0:
        r.add(flecha(ws_s, L, sec.Ix, limite_flecha_succao,
                     f"Flecha — sucção (L/{limite_flecha_succao:g})"))

    r.dados.update({
        "secao": sec.resumo(), "vao_m": vao, "n_correntes": n_correntes,
        "Lb_cm": Lb, "Lt_cm": Lt, "inclinacao_graus": inclinacao,
        "massa_kg_m": sec.massa, "aco": aco.nome, "fy": aco.fy,
        "Mx_gravidade_kNcm": Mx_g, "My_gravidade_kNcm": My_g,
        "Mx_succao_kNcm": Mx_s_total, "V_Sd_kN": V_Sd,
        "Mx_Rd_gravidade_kNcm": vg.Rd,
        "Mx_Rd_succao_kNcm": v_suc.Rd if v_suc else None,
        "razoes": {v.titulo: round(v.razao, 3) for v in r.verificacoes},
    })
    return r


def dimensionar_terca(aco="CF-26 (NBR 6650)", vao: float = 5.0,
                      carga_gravidade: float = 0.0, carga_succao: float = 0.0,
                      *, correntes: Sequence[int] = (0, 1, 2, 3),
                      massa_max: Optional[float] = None,
                      altura_max: Optional[float] = None,
                      apenas_aprovados: bool = True,
                      perfis: Optional[Sequence] = None,
                      **kwargs) -> List[Resultado]:
    """Busca no catálogo o Ue mais leve que atende, variando as linhas de corrente.

    Devolve a lista de `Resultado` **ordenada por peso** (e, com o mesmo perfil,
    pelo menor número de correntes), cada um com as razões de todas as
    verificações em `.dados["razoes"]`. O primeiro elemento é a solução mais
    econômica. `apenas_aprovados=False` devolve também as reprovadas, para a
    interface mostrar o quanto faltou.

    Os `kwargs` são repassados a `terca()` (inclinacao, comprimento_apoio,
    limites de flecha, cargas de serviço, etc.).
    """
    saida: List[Resultado] = []
    # `perfis` restringe a busca (o perfil forçado pelo usuário, por exemplo)
    for p in (list(perfis) if perfis is not None else perfis_ue(massa_max=massa_max, altura_max=altura_max)):
        try:
            sec = secao_do_perfil(p, r=kwargs.get("raio_dobra"))
        except ErroDeDados:
            continue
        for n in sorted(set(int(c) for c in correntes)):
            try:
                res = terca(sec, aco, vao, carga_gravidade, carga_succao, n, **kwargs)
            except ErroDeDados:
                continue
            res.dados["massa_kg_m"] = sec.massa
            if res.ok or not apenas_aprovados:
                saida.append(res)
            if res.ok:
                break          # menos correntes já resolve: não testa mais linhas
    saida.sort(key=lambda r: (round(r.dados["massa_kg_m"], 3),
                              r.dados["n_correntes"], r.razao))
    return saida


def tabela_capacidade(aco="CF-26 (NBR 6650)", vaos: Sequence[float] = (5, 6, 7, 8),
                      n_correntes: int = 2, limite_flecha: float = 180.0,
                      gama_carga: float = 1.4) -> List[dict]:
    """Capacidade q_d (kN/m) de terças Ue por vão, carga gravitacional.

    Reproduz o formato da Tabela 7.9 do manual: viga biapoiada, mesa comprimida
    contida pela telha e q_serviço = q_d/`gama_carga` para a flecha
    L/`limite_flecha`. Serve para pré-dimensionamento e para comparar com a
    tabela do manual — os valores deste módulo são **menores** nas células
    governadas pelo momento, porque incluem a flambagem distorcional, que a
    tabela orientativa ignora.

    `n_correntes` está na assinatura só para registrar a hipótese da tabela (o
    manual supõe correntes a cada 1/3 do vão): com a mesa comprimida contida
    continuamente pela telha, as correntes **não** alteram M_x,Rd — elas contam
    na flexão oblíqua e, principalmente, na sucção, que esta tabela não cobre.
    Para o caso de sucção use `terca()` ou `dimensionar_terca()`.
    """
    linhas = []
    for p in perfis_ue():
        sec = secao_do_perfil(p)
        linha = {"perfil": p.nome, "massa": p.massa, "q": {}}
        for vao in vaos:
            L = vao * 100.0
            v = flexao_mrd(sec, aco, 0.0, 0.0, 0.0, Cb=1.0)
            q_mom = 8 * v.Rd / L ** 2 * 100.0                  # kN/m
            q_fle = (384 * E * sec.Ix / (5 * limite_flecha * L ** 3)
                     * gama_carga * 100.0)                     # kN/m
            linha["q"][vao] = {"qd": min(q_mom, q_fle),
                               "governa": "flecha" if q_fle < q_mom else "momento",
                               "q_momento": q_mom, "q_flecha": q_fle}
        linhas.append(linha)
    return linhas
