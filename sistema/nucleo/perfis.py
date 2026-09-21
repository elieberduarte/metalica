# -*- coding: utf-8 -*-
"""Banco de perfis estruturais e suas propriedades geométricas.

Os dados vêm de `dados/perfis.json`, extraído das tabelas do manual (catálogos
Gerdau, Vallourec e NBR 6355). As dimensões são gravadas em mm, como nos catálogos,
e o objeto `Perfil` as expõe também em cm, que é a unidade de cálculo do sistema.

Propriedades calculadas quando o catálogo não traz:
    J   constante de torção, pela soma de retângulos (paredes finas). Fica cerca de
        10 % abaixo do catálogo em perfis laminados, porque despreza os raios de
        concordância; como J reduz o momento crítico de flambagem lateral, o
        resultado fica a favor da segurança.
    Cw  constante de empenamento, Iy·(d − tf)²/4, exata para perfil I bissimétrico.
"""
import json
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .base import ErroDeDados

CAMINHO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dados", "perfis.json")


@dataclass
class Perfil:
    """Um perfil do catálogo. Dimensões em mm; propriedades de seção em cm."""
    nome: str
    tipo: str                      # I, U, Ue, L, tubo
    dados: dict = field(default_factory=dict)

    # ---------- dimensões (mm) ----------
    @property
    def d(self) -> float:
        """Altura total."""
        return self.dados.get("d") or self.dados.get("h") or self.dados.get("D") or 0.0

    @property
    def bf(self) -> float:
        """Largura da mesa (ou do lado, em tubos)."""
        return self.dados.get("bf") or self.dados.get("b") or 0.0

    @property
    def tw(self) -> float:
        """Espessura da alma (ou da parede)."""
        return self.dados.get("tw") or self.dados.get("t") or 0.0

    @property
    def tf(self) -> float:
        """Espessura da mesa."""
        return self.dados.get("tf") or self.dados.get("t") or 0.0

    @property
    def h_alma(self) -> float:
        """Altura livre da alma, em mm (entre as faces internas das mesas)."""
        if self.tipo == "I":
            return self.d - 2 * self.tf
        if self.tipo == "tubo" and self.dados.get("tipo") != "redondo":
            return self.d - 2 * self.tw
        return self.d

    # ---------- massa e área ----------
    @property
    def massa(self) -> float:
        """kg/m."""
        return self.dados.get("massa", 0.0)

    @property
    def A(self) -> float:
        """Área bruta, cm²."""
        return self.dados.get("A", 0.0)

    # ---------- propriedades de seção (cm) ----------
    @property
    def Ix(self) -> float: return self.dados.get("Ix", 0.0)

    @property
    def Iy(self) -> float: return self.dados.get("Iy", 0.0)

    @property
    def Wx(self) -> float: return self.dados.get("Wx", 0.0)

    @property
    def Wy(self) -> float: return self.dados.get("Wy", 0.0)

    @property
    def Zx(self) -> float:
        z = self.dados.get("Zx")
        return z if z else 1.12 * self.Wx      # estimativa quando o catálogo não traz

    @property
    def Zy(self) -> float:
        z = self.dados.get("Zy")
        return z if z else 1.5 * self.Wy

    @property
    def rx(self) -> float:
        r = self.dados.get("rx")
        return r if r else (math.sqrt(self.Ix / self.A) if self.A else 0.0)

    @property
    def ry(self) -> float:
        r = self.dados.get("ry")
        return r if r else (math.sqrt(self.Iy / self.A) if self.A else 0.0)

    @property
    def rmin(self) -> float:
        return self.dados.get("rmin") or min(self.rx, self.ry)

    @property
    def J(self) -> float:
        """Constante de torção, cm⁴."""
        j = self.dados.get("J")
        if j:
            return j
        # soma de retângulos
        if self.tipo in ("I", "U"):
            bf, tf, h, tw = self.bf / 10, self.tf / 10, self.h_alma / 10, self.tw / 10
            n = 2 if self.tipo == "I" else 2
            return (n * bf * tf ** 3 + h * tw ** 3) / 3
        return 0.0

    @property
    def Cw(self) -> float:
        """Constante de empenamento, cm⁶."""
        cw = self.dados.get("Cw")
        if cw:
            return cw
        if self.tipo == "I":
            return self.Iy * ((self.d - self.tf) / 10) ** 2 / 4
        return 0.0

    @property
    def fechado(self) -> bool:
        """Seção fechada (tubo) — não sofre flambagem lateral com torção."""
        return self.tipo == "tubo"

    @property
    def bissimetrico(self) -> bool:
        return self.tipo in ("I", "tubo")

    # ---------- esbeltez dos elementos ----------
    @property
    def esbeltez_mesa(self) -> float:
        """b/t do elemento comprimido da mesa (AL para perfil I, AA para tubo)."""
        if self.tipo == "I":
            return (self.bf / 2) / self.tf
        if self.tipo == "tubo":
            if self.dados.get("tipo") == "redondo":
                return self.d / self.tw
            return (self.bf - 2 * self.tw) / self.tw
        if self.tipo in ("U", "Ue"):
            return self.bf / self.tf if self.tf else 0.0
        if self.tipo == "L":
            return self.bf / self.tw if self.tw else 0.0
        return 0.0

    @property
    def esbeltez_alma(self) -> float:
        """h/tw da alma."""
        if self.tipo == "tubo" and self.dados.get("tipo") == "redondo":
            return self.d / self.tw
        return self.h_alma / self.tw if self.tw else 0.0

    @property
    def Aw(self) -> float:
        """Área efetiva de cisalhamento, cm² (NBR 8800: d·tw para perfil I)."""
        if self.tipo == "I":
            return (self.d / 10) * (self.tw / 10)
        if self.tipo == "tubo" and self.dados.get("tipo") != "redondo":
            return 2 * (self.d / 10) * (self.tw / 10)
        if self.tipo == "tubo":
            return 0.5 * self.A
        return (self.d / 10) * (self.tw / 10)

    def __str__(self):
        return self.nome

    def resumo(self) -> dict:
        return {"nome": self.nome, "tipo": self.tipo, "massa": self.massa, "A": self.A,
                "d": self.d, "bf": self.bf, "tw": self.tw, "tf": self.tf,
                "Ix": self.Ix, "Wx": self.Wx, "Zx": self.Zx, "rx": self.rx,
                "Iy": self.Iy, "Wy": self.Wy, "ry": self.ry, "J": round(self.J, 2),
                "Cw": round(self.Cw)}


class Banco:
    def __init__(self, caminho=CAMINHO):
        with open(caminho, encoding="utf-8") as f:
            bruto = json.load(f)
        self.perfis: Dict[str, Perfil] = {}
        self.por_tipo: Dict[str, List[Perfil]] = {}
        for tipo, lista in bruto.items():
            self.por_tipo[tipo] = []
            for reg in lista:
                p = Perfil(nome=reg["nome"], tipo=tipo, dados=reg)
                self.perfis[p.nome] = p
                self.por_tipo[tipo].append(p)
        # ordena por massa, para as buscas de dimensionamento
        for tipo in self.por_tipo:
            self.por_tipo[tipo].sort(key=lambda p: p.massa or 0)

    def __getitem__(self, nome: str) -> Perfil:
        if nome in self.perfis:
            return self.perfis[nome]
        # tolera variação de grafia: "W 360x51" -> "W 360×51,0"
        alvo = _chave(nome)
        for k, p in self.perfis.items():
            if _chave(k) == alvo:
                return p
        raise ErroDeDados(f"perfil não encontrado no catálogo: {nome}")

    def get(self, nome: str) -> Optional[Perfil]:
        try:
            return self[nome]
        except ErroDeDados:
            return None

    def lista(self, tipo: str = None, familia: str = None) -> List[Perfil]:
        ps = self.por_tipo.get(tipo, []) if tipo else list(self.perfis.values())
        if familia:
            ps = [p for p in ps if p.dados.get("familia") == familia or p.nome.startswith(familia)]
        return ps

    def candidatos(self, tipo="I", familia=None, massa_max=None, altura_max=None,
                   altura_min=None) -> List[Perfil]:
        """Perfis para uma busca de dimensionamento, do mais leve ao mais pesado."""
        ps = self.lista(tipo, familia)
        if massa_max:
            ps = [p for p in ps if p.massa <= massa_max]
        if altura_max:
            ps = [p for p in ps if p.d <= altura_max]
        if altura_min:
            ps = [p for p in ps if p.d >= altura_min]
        return ps

    def nomes(self, tipo: str = None) -> List[str]:
        return [p.nome for p in self.lista(tipo)]


def _chave(nome: str) -> str:
    return (nome.upper().replace("×", "X").replace(" ", "").replace(",", ".")
            .replace('"', "").rstrip("0").rstrip("."))


_banco: Optional[Banco] = None


def banco() -> Banco:
    """Instância única do catálogo."""
    global _banco
    if _banco is None:
        _banco = Banco()
    return _banco


def perfil(nome: str) -> Perfil:
    return banco()[nome]
