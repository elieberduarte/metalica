# -*- coding: utf-8 -*-
"""Materiais do concreto armado — ABNT NBR 6118:2023, seção 8, e os coeficientes da 12.4.

Unidades: fck e as tensões em kN/cm² (1 kN/cm² = 10 MPa), deformações em ‰ onde indicado.
As expressões da norma são em MPa: a conversão é feita aqui e registrada nos passos.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from nucleo.base import ErroDeDados, Passo, fmt

# --- coeficientes de ponderação das resistências no ELU (NBR 6118, 12.4.1, Tabela 12.1)
GAMA_C = 1.40
GAMA_S = 1.15

#: agregado graúdo → αE (NBR 6118, 8.2.8)
ALFA_E = {"basalto": 1.2, "diabásio": 1.2, "granito": 1.0, "gnaisse": 1.0, "calcário": 0.9, "arenito": 0.7}


@dataclass
class Concreto:
    """Concreto de classe C20 a C90 (NBR 6118, 8.2). `fck_MPa` é o valor da classe."""
    fck_MPa: float
    agregado: str = "granito"
    gama_c: float = GAMA_C

    def __post_init__(self):
        if not (20.0 <= self.fck_MPa <= 90.0):
            raise ErroDeDados("fck fora das classes da NBR 6118 (C20 a C90): %s MPa" % fmt(self.fck_MPa, 0))
        if self.agregado not in ALFA_E:
            raise ErroDeDados("agregado desconhecido: %s (use %s)" % (self.agregado, ", ".join(ALFA_E)))

    @property
    def nome(self) -> str:
        return "C%d" % round(self.fck_MPa)

    # --- resistências (kN/cm²)
    @property
    def fck(self) -> float:
        return self.fck_MPa / 10.0

    @property
    def fcd(self) -> float:
        return self.fck / self.gama_c

    @property
    def fctm_MPa(self) -> float:
        """8.2.5: 0,3·fck^(2/3) até C50; 2,12·ln[1 + 0,1(fck + 8)] acima"""
        f = self.fck_MPa
        return 0.3 * f ** (2.0 / 3.0) if f <= 50 else 2.12 * math.log(1 + 0.1 * (f + 8))

    @property
    def fctm(self) -> float:
        return self.fctm_MPa / 10.0

    @property
    def fctk_inf(self) -> float:
        return 0.7 * self.fctm

    @property
    def fctk_sup(self) -> float:
        return 1.3 * self.fctm

    @property
    def fctd(self) -> float:
        return self.fctk_inf / self.gama_c

    # --- módulos (kN/cm²)
    @property
    def Eci(self) -> float:
        """8.2.8: αE·5600·√fck até C50; 21,5·10³·αE·(fck/10 + 1,25)^(1/3) acima (MPa)"""
        f, a = self.fck_MPa, ALFA_E[self.agregado]
        E = a * 5600.0 * math.sqrt(f) if f <= 50 else 21.5e3 * a * (f / 10.0 + 1.25) ** (1.0 / 3.0)
        return E / 10.0

    @property
    def alfa_i(self) -> float:
        return min(0.8 + 0.2 * self.fck_MPa / 80.0, 1.0)

    @property
    def Ecs(self) -> float:
        return self.alfa_i * self.Eci

    # --- diagrama tensão-deformação e retângulo (8.2.10.1, 17.2.2)
    @property
    def eta_c(self) -> float:
        """8.2.10.1: 1,0 até C40; (40/fck)^(1/3) acima"""
        return 1.0 if self.fck_MPa <= 40 else (40.0 / self.fck_MPa) ** (1.0 / 3.0)

    @property
    def lam(self) -> float:
        return 0.8 if self.fck_MPa <= 50 else 0.8 - (self.fck_MPa - 50) / 400.0

    @property
    def alfa_c(self) -> float:
        return 0.85 if self.fck_MPa <= 50 else 0.85 * (1.0 - (self.fck_MPa - 50) / 200.0)

    @property
    def eps_c2(self) -> float:
        """‰"""
        f = self.fck_MPa
        return 2.0 if f <= 50 else 2.0 + 0.085 * (f - 50) ** 0.53

    @property
    def eps_cu(self) -> float:
        """‰"""
        f = self.fck_MPa
        return 3.5 if f <= 50 else 2.6 + 35.0 * ((90 - f) / 100.0) ** 4

    @property
    def n_parabola(self) -> float:
        f = self.fck_MPa
        return 2.0 if f <= 50 else 1.4 + 23.4 * ((90 - f) / 100.0) ** 4

    @property
    def sigma_cd(self) -> float:
        """a tensão do retângulo, largura que não diminui para a borda comprimida (17.2.2 e)"""
        return self.alfa_c * self.eta_c * self.fcd

    @property
    def xi_lim(self) -> float:
        """14.6.4.3: x/d ≤ 0,45 até C50, 0,35 acima (ductilidade nas vigas)"""
        return 0.45 if self.fck_MPa <= 50 else 0.35

    @property
    def peso_especifico(self) -> float:
        """kN/m³ do concreto armado (8.2.2): 25"""
        return 25.0

    def passos(self) -> List[Passo]:
        return [
            Passo("Resistência de cálculo à compressão", "f<sub>cd</sub> = f<sub>ck</sub>/γ<sub>c</sub>",
                  "%s / %s" % (fmt(self.fck_MPa, 0), fmt(self.gama_c)), fmt(self.fcd * 10, 2, "MPa"), "NBR 6118, 12.3.3"),
            Passo("Resistência média à tração", "f<sub>ct,m</sub> = 0,3·f<sub>ck</sub><sup>2/3</sup>" if self.fck_MPa <= 50
                  else "f<sub>ct,m</sub> = 2,12·ln[1 + 0,1(f<sub>ck</sub> + 8)]", "", fmt(self.fctm_MPa, 2, "MPa"), "NBR 6118, 8.2.5"),
            Passo("Módulo de elasticidade inicial", "E<sub>ci</sub> = α<sub>E</sub>·5600·√f<sub>ck</sub>" if self.fck_MPa <= 50
                  else "E<sub>ci</sub> = 21,5·10³·α<sub>E</sub>·(f<sub>ck</sub>/10 + 1,25)<sup>1/3</sup>",
                  "α<sub>E</sub> = %s (%s)" % (fmt(ALFA_E[self.agregado], 1), self.agregado), fmt(self.Eci * 10, 0, "MPa"), "NBR 6118, 8.2.8"),
            Passo("Módulo secante", "E<sub>cs</sub> = α<sub>i</sub>·E<sub>ci</sub>, α<sub>i</sub> = 0,8 + 0,2·f<sub>ck</sub>/80 ≤ 1",
                  "%s × %s" % (fmt(self.alfa_i, 3), fmt(self.Eci * 10, 0)), fmt(self.Ecs * 10, 0, "MPa"), "NBR 6118, 8.2.8"),
        ]


@dataclass
class AcoArmadura:
    """Aço para armadura passiva (NBR 6118, 8.3; NBR 7480)."""
    nome: str
    fyk_MPa: float
    Es_MPa: float = 210000.0
    gama_s: float = GAMA_S

    @property
    def fyk(self) -> float:
        return self.fyk_MPa / 10.0

    @property
    def fyd(self) -> float:
        return self.fyk / self.gama_s

    @property
    def Es(self) -> float:
        return self.Es_MPa / 10.0

    @property
    def eps_yd(self) -> float:
        """‰"""
        return self.fyd / self.Es * 1000.0


ACOS = {"CA-50": AcoArmadura("CA-50", 500.0), "CA-60": AcoArmadura("CA-60", 600.0)}

#: bitolas comerciais (mm) → área (cm²) e massa (kg/m) (NBR 7480)
BITOLAS: Dict[float, Tuple[float, float]] = {
    5.0: (0.196, 0.154), 6.3: (0.312, 0.245), 8.0: (0.503, 0.395), 10.0: (0.785, 0.617), 12.5: (1.227, 0.963),
    16.0: (2.011, 1.578), 20.0: (3.142, 2.466), 25.0: (4.909, 3.853), 32.0: (8.042, 6.313),
}

#: cobrimento nominal (mm) por classe de agressividade (NBR 6118, Tabela 7.2) para concreto armado:
#: laje / viga-pilar / elemento em contato com o solo
COBRIMENTO = {"I": (20, 25, 30), "II": (25, 30, 30), "III": (35, 40, 40), "IV": (45, 50, 50)}

#: classe mínima de concreto por classe de agressividade (NBR 6118, Tabela 7.1, concreto armado)
CLASSE_MINIMA = {"I": 20, "II": 25, "III": 30, "IV": 40}


def aco(nome: str) -> AcoArmadura:
    if nome not in ACOS:
        raise ErroDeDados("aço de armadura desconhecido: %s (use %s)" % (nome, ", ".join(ACOS)))
    return ACOS[nome]


def cobrimento(caa: str, elemento: str = "viga", pre_fabricado: bool = True) -> float:
    """cobrimento nominal (cm). Para elemento pré-fabricado com controle rigoroso de qualidade
    a NBR 6118 (7.4.7.4) permite Δc = 5 mm — reduz 5 mm do nominal da Tabela 7.2."""
    if caa not in COBRIMENTO:
        raise ErroDeDados("classe de agressividade desconhecida: %s (use I, II, III ou IV)" % caa)
    laje, viga, solo = COBRIMENTO[caa]
    c = {"laje": laje, "viga": viga, "pilar": viga, "solo": solo, "fundacao": solo}.get(elemento, viga)
    if pre_fabricado and elemento not in ("solo", "fundacao"):
        c -= 5
    return c / 10.0


def area_barras(n: int, bitola: float) -> float:
    return n * BITOLAS[bitola][0]


def escolher_barras(As: float, bitolas=(10.0, 12.5, 16.0, 20.0, 25.0), n_min: int = 2, n_max: int = 12) -> Optional[Tuple[int, float]]:
    """o arranjo de barras com a menor área que cobre As (cm²): (n, bitola)"""
    melhor = None
    for fi in bitolas:
        a = BITOLAS[fi][0]
        n = max(n_min, math.ceil(As / a - 1e-9))
        if n > n_max:
            continue
        cand = (n * a, n, fi)
        if melhor is None or cand < melhor:
            melhor = cand
    return (melhor[1], melhor[2]) if melhor else None
