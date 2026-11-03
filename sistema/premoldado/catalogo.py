# -*- coding: utf-8 -*-
"""O catálogo do pré-moldado: o que o programa conhece de materiais e peças, com os valores que a norma
dá (nada de tabela de fornecedor — as seções padrão da fábrica entram quando o usuário passar).

* concretos C20 a C90 (NBR 6118, 8.2) — com o agregado escolhido;
* aços CA-50 e CA-60 (8.3), com γs do pré-moldado e do pré-fabricado (NBR 9062, 8.1);
* bitolas (NBR 7480) e o comprimento de ancoragem básico por concreto (NBR 6118, 9.4.2.4);
* cobrimentos (Tabela 7.2, com o Δc = 5 mm do pré-fabricado) e a classe mínima (Tabela 7.1);
* as seções de pilar que o dimensionamento do galpão experimenta, com as propriedades e a altura máxima
  em balanço pelos limites de esbeltez (λ ≤ 90 e λ ≤ 140).
"""
from __future__ import annotations

import math
from typing import Dict, List

from .concreto import ACOS, ALFA_E, BITOLAS, CLASSE_MINIMA, COBRIMENTO, AcoArmadura, Concreto
from .galpao import DadosGalpaoPM
from .nbr9062 import ancoragem

CLASSES = [20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80, 90]
CLASSES_ANCORAGEM = [25, 30, 35, 40, 45, 50]


def concretos(agregado: str = "granito") -> List[Dict]:
    linhas = []
    for fck in CLASSES:
        c = Concreto(fck, agregado)
        c13 = Concreto(fck, agregado, gama_c=1.3)
        linhas.append({"classe": "C%d" % fck, "fck": fck, "fcd_14": c.fcd * 10, "fcd_13": c13.fcd * 10,
                       "fctm": c.fctm_MPa, "fctk_inf": c.fctk_inf * 10, "fctk_sup": c.fctk_sup * 10,
                       "Eci": c.Eci * 10, "Ecs": c.Ecs * 10, "eps_c2": c.eps_c2, "eps_cu": c.eps_cu,
                       "grupo": "I" if fck <= 50 else "II"})
    return linhas


def acos() -> List[Dict]:
    out = []
    for nome, a in ACOS.items():
        a110 = AcoArmadura(nome, a.fyk_MPa, gama_s=1.10)
        out.append({"nome": nome, "fyk": a.fyk_MPa, "fyd_115": a.fyd * 10, "fyd_110": a110.fyd * 10,
                    "Es": a.Es_MPa, "eps_yd": a.eps_yd})
    return out


def bitolas() -> List[Dict]:
    a = ACOS["CA-50"]
    out = []
    for fi, (area, massa) in BITOLAS.items():
        lb = {}
        for fck in CLASSES_ANCORAGEM:
            v, _ = ancoragem(fi, Concreto(fck), a, boa_aderencia=True)
            lb["C%d" % fck] = math.ceil(v)
        out.append({"bitola": fi, "area": area, "massa": massa, "lb": lb})
    return out


def cobrimentos() -> List[Dict]:
    return [{"caa": caa, "laje": l, "viga_pilar": v, "solo": s, "laje_pf": l - 5, "viga_pilar_pf": v - 5,
             "classe_minima": "C%d" % CLASSE_MINIMA[caa]} for caa, (l, v, s) in COBRIMENTO.items()]


def secoes_pilar() -> List[Dict]:
    out = []
    for b, h in DadosGalpaoPM().secoes_pilar:
        b, h = min(b, h), max(b, h)
        A = b * h
        Ix, Iy = b * h ** 3 / 12.0, h * b ** 3 / 12.0
        i_min = b / math.sqrt(12.0)
        out.append({"b": b, "h": h, "A": A, "peso": A / 1e4 * 25.0, "Ix": Ix, "Iy": Iy, "i_min": i_min,
                    # pilar engastado na base e livre no topo: le = 2·L
                    "L90": 90 * i_min / 2.0 / 100.0, "L140": 140 * i_min / 2.0 / 100.0,
                    "As_min": 0.004 * A, "As_max": 0.04 * A})
    return out


def catalogo(agregado: str = "granito") -> Dict:
    if agregado not in ALFA_E:
        agregado = "granito"
    return {"agregado": agregado, "agregados": list(ALFA_E), "concretos": concretos(agregado), "acos": acos(),
            "bitolas": bitolas(), "classes_ancoragem": ["C%d" % f for f in CLASSES_ANCORAGEM],
            "cobrimentos": cobrimentos(), "secoes_pilar": secoes_pilar()}
