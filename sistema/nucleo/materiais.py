# -*- coding: utf-8 -*-
"""Aços estruturais, parafusos, eletrodos e concreto.

Tensões em kN/cm² (1 kN/cm² = 10 MPa).
"""
from dataclasses import dataclass
from typing import Dict, List

from .base import ErroDeDados


@dataclass(frozen=True)
class Aco:
    nome: str
    fy: float          # resistência ao escoamento, kN/cm²
    fu: float          # resistência à ruptura, kN/cm²
    norma: str = ""
    uso: str = ""

    @property
    def fy_MPa(self) -> float:
        return self.fy * 10

    @property
    def fu_MPa(self) -> float:
        return self.fu * 10


ACOS: Dict[str, Aco] = {a.nome: a for a in [
    # laminados e chapas grossas
    Aco("ASTM A36", 25.0, 40.0, "ASTM A36/A36M", "perfis, chapas e barras de uso geral"),
    Aco("ASTM A572 Gr.50", 34.5, 45.0, "ASTM A572", "perfis estruturais de alta resistência"),
    Aco("ASTM A572 Gr.42", 29.0, 41.5, "ASTM A572", "perfis e chapas"),
    Aco("ASTM A588", 34.5, 48.5, "ASTM A588", "aço patinável (aparente)"),
    Aco("ASTM A992", 34.5, 45.0, "ASTM A992", "perfis W de edifícios"),
    Aco("NBR 7007 MR250", 25.0, 40.0, "NBR 7007", "perfis laminados"),
    Aco("NBR 7007 AR350", 35.0, 45.0, "NBR 7007", "perfis laminados de alta resistência"),
    Aco("NBR 7007 AR350 COR", 35.0, 48.5, "NBR 7007", "perfil laminado patinável"),
    Aco("NBR 7007 AR415", 41.5, 52.0, "NBR 7007", "perfis de alta resistência"),
    Aco("CSN COR 420", 30.0, 42.0, "NBR 5920/5921", "chapa patinável"),
    Aco("USI-SAC 350", 34.5, 49.0, "NBR 5920/5921", "chapa patinável"),
    # formados a frio
    Aco("CF-26 (NBR 6650)", 26.0, 41.0, "NBR 6650", "perfis formados a frio (terças, longarinas)"),
    Aco("CIVIL 300", 30.0, 40.0, "NBR 6650 / CSN", "chapa laminada a quente para perfis formados a frio"),
    Aco("CIVIL 350", 35.0, 45.0, "NBR 6650 / CSN", "chapa laminada a quente de alta resistência"),
    Aco("ZAR-230", 23.0, 31.0, "NBR 7008", "chapa galvanizada para perfis formados a frio"),
    Aco("ZAR-280", 28.0, 38.0, "NBR 7008", "chapa galvanizada de maior resistência"),
    Aco("ZAR-345", 34.5, 43.0, "NBR 7008", "chapa galvanizada estrutural"),
    # tubos
    Aco("ASTM A500 Gr.B", 31.5, 40.0, "ASTM A500", "tubos estruturais"),
    Aco("ASTM A500 Gr.C", 34.5, 42.7, "ASTM A500", "tubos estruturais"),
    Aco("VMB 250", 25.0, 40.0, "NBR 8261", "tubos estruturais"),
    Aco("VMB 300", 30.0, 41.5, "NBR 8261", "tubos estruturais"),
    Aco("VMB 350", 35.0, 46.0, "NBR 8261", "tubos estruturais"),
]}

ACO_PADRAO = "ASTM A572 Gr.50"


@dataclass(frozen=True)
class Parafuso:
    nome: str
    fub: float         # resistência à ruptura do parafuso, kN/cm²
    grupo: str         # "comum" ou "alta resistência"
    norma: str = ""

    @property
    def alta_resistencia(self) -> bool:
        return self.grupo == "alta resistência"


PARAFUSOS: Dict[str, Parafuso] = {p.nome: p for p in [
    Parafuso("ASTM A307", 41.5, "comum", "ASTM A307"),
    Parafuso("ASTM A325", 82.5, "alta resistência", "ASTM A325 / NBR 8855"),
    Parafuso("ASTM A490", 103.5, "alta resistência", "ASTM A490"),
    Parafuso("ISO 4.6", 40.0, "comum", "ISO 898-1"),
    Parafuso("ISO 8.8", 80.0, "alta resistência", "ISO 898-1"),
    Parafuso("ISO 10.9", 100.0, "alta resistência", "ISO 898-1"),
    Parafuso("ASTM F1554 Gr.36", 40.0, "comum", "ASTM F1554 (chumbador)"),
    Parafuso("ASTM F1554 Gr.55", 51.7, "comum", "ASTM F1554 (chumbador)"),
]}

# diâmetros comerciais: nome -> (diâmetro nominal cm, área bruta cm², área efetiva na rosca cm²)
DIAMETROS: Dict[str, tuple] = {
    '1/2"':   (1.270, 1.267, 0.9142),
    '5/8"':   (1.588, 1.979, 1.4581),
    '3/4"':   (1.905, 2.850, 2.1587),
    '7/8"':   (2.223, 3.879, 2.9806),
    '1"':     (2.540, 5.067, 3.9026),
    '1.1/8"': (2.858, 6.413, 4.9032),
    '1.1/4"': (3.175, 7.917, 6.2258),
    "M12":    (1.200, 1.131, 0.8430),
    "M16":    (1.600, 2.011, 1.5700),
    "M20":    (2.000, 3.142, 2.4500),
    "M22":    (2.200, 3.801, 3.0300),
    "M24":    (2.400, 4.524, 3.5300),
    "M27":    (2.700, 5.726, 4.5900),
    "M30":    (3.000, 7.069, 5.6100),
}

# protensão mínima de parafusos de alta resistência (NBR 8800, Tabela 15), em kN
PROTENSAO: Dict[str, Dict[str, float]] = {
    "ASTM A325": {'1/2"': 53, '5/8"': 85, '3/4"': 125, '7/8"': 173, '1"': 227,
                  '1.1/8"': 249, '1.1/4"': 316, "M16": 91, "M20": 142, "M22": 176,
                  "M24": 205, "M27": 267, "M30": 326},
    "ASTM A490": {'1/2"': 66, '5/8"': 106, '3/4"': 156, '7/8"': 218, '1"': 285,
                  '1.1/8"': 356, '1.1/4"': 454, "M16": 114, "M20": 179, "M22": 221,
                  "M24": 257, "M27": 334, "M30": 408},
}

# coeficiente de atrito das superfícies (NBR 8800, item 6.3.4)
ATRITO = {"A (jateada, sem pintura)": 0.35,
          "B (jateada e pintada, classe B)": 0.50,
          "C (galvanizada e escovada)": 0.35,
          "pintada (não classificada)": 0.20}


@dataclass(frozen=True)
class Eletrodo:
    nome: str
    fw: float          # resistência à ruptura do metal da solda, kN/cm²
    processo: str = ""


ELETRODOS: Dict[str, Eletrodo] = {e.nome: e for e in [
    Eletrodo("E60XX", 41.5, "eletrodo revestido (SMAW)"),
    Eletrodo("E70XX", 48.5, "eletrodo revestido (SMAW)"),
    Eletrodo("ER70S-6", 48.5, "MIG/MAG (GMAW)"),
    Eletrodo("E71T-1", 48.5, "arame tubular (FCAW)"),
    Eletrodo("F7A2-EM12K", 48.5, "arco submerso (SAW)"),
]}

# perna mínima de filete por espessura da parte mais grossa (NBR 8800, Tabela 10), em cm
PERNA_MINIMA = [(0.635, 0.30), (1.27, 0.50), (1.905, 0.60), (float("inf"), 0.80)]


def perna_minima(t_maior_cm: float) -> float:
    for lim, perna in PERNA_MINIMA:
        if t_maior_cm <= lim:
            return perna
    return 0.80


def perna_maxima(t_menor_cm: float) -> float:
    """Perna máxima ao longo de borda (NBR 8800, item 6.2.6.2.2)."""
    return t_menor_cm if t_menor_cm < 0.635 else t_menor_cm - 0.2


@dataclass(frozen=True)
class Concreto:
    nome: str
    fck: float         # kN/cm²

    @property
    def fck_MPa(self) -> float:
        return self.fck * 10

    @property
    def fcd(self) -> float:
        from .base import GAMA_C
        return self.fck / GAMA_C


# fck em kN/cm²: C25 = 25 MPa = 2,5 kN/cm²
CONCRETOS: Dict[str, Concreto] = {f"C{int(f*10)}": Concreto(f"C{int(f*10)}", f)
                                  for f in (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)}


def aco(nome: str) -> Aco:
    if nome not in ACOS:
        raise ErroDeDados(f"aço desconhecido: {nome}. Disponíveis: {', '.join(ACOS)}")
    return ACOS[nome]


def parafuso(nome: str) -> Parafuso:
    if nome not in PARAFUSOS:
        raise ErroDeDados(f"parafuso desconhecido: {nome}")
    return PARAFUSOS[nome]


def diametro(nome: str) -> tuple:
    if nome not in DIAMETROS:
        raise ErroDeDados(f"diâmetro desconhecido: {nome}")
    return DIAMETROS[nome]


def eletrodo(nome: str) -> Eletrodo:
    if nome not in ELETRODOS:
        raise ErroDeDados(f"eletrodo desconhecido: {nome}")
    return ELETRODOS[nome]


def concreto(nome_ou_fck) -> Concreto:
    """Aceita "C25", 25 (MPa) ou 2,5 (kN/cm²). Valores de 15 a 50 são lidos como MPa."""
    if isinstance(nome_ou_fck, (int, float)):
        f = float(nome_ou_fck)
        if f > 10:                      # veio em MPa
            f = f / 10
        if not (1.5 <= f <= 5.0):
            raise ErroDeDados(
                f"fck fora da faixa usual: {nome_ou_fck}. Informe 15 a 50 MPa "
                f"(ou 1,5 a 5,0 kN/cm²).")
        return Concreto(f"C{int(round(f*10))}", f)
    if nome_ou_fck not in CONCRETOS:
        raise ErroDeDados(f"concreto desconhecido: {nome_ou_fck}")
    return CONCRETOS[nome_ou_fck]


def listar() -> dict:
    """Catálogo para a interface web."""
    return {
        "acos": [{"nome": a.nome, "fy": a.fy, "fu": a.fu, "uso": a.uso} for a in ACOS.values()],
        "parafusos": [{"nome": p.nome, "fub": p.fub, "grupo": p.grupo} for p in PARAFUSOS.values()],
        "diametros": list(DIAMETROS),
        "eletrodos": [{"nome": e.nome, "fw": e.fw} for e in ELETRODOS.values()],
        "concretos": [{"nome": c.nome, "fck_MPa": c.fck_MPa} for c in CONCRETOS.values()],
    }
