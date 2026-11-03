# -*- coding: utf-8 -*-
"""Galpão pré-moldado — pilares de concreto engastados em cálice, cobertura apoiada no topo.

O sistema é o mais comum do pré-moldado: pilares em balanço (engastados na fundação por cálice)
e a cobertura (metálica, sobre os pilares) articulada no topo. Na direção transversal, os dois
pilares de cada pórtico trabalham juntos, ligados no topo pela cobertura (escora rotulada); na
longitudinal, a força do vento no oitão se divide entre todos os pilares pelo contraventamento da
cobertura, e os pilares de canto levam também a parede do oitão.

Mesmo caminho do galpão metálico (`nucleo/galpao.py`): `DadosGalpaoPM` → `dimensionar` →
`ProjetoGalpaoPM` (esforços, pilares dimensionados com a memória, cálices, lista de peças).
O vento é o da parte metálica (`nucleo.cargas.pressoes_galpao`); o pórtico, o solver de
`nucleo.analise`; o concreto, `premoldado.nbr6118`.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo import analise, cargas
from nucleo.base import ErroDeDados, Resultado, Verificacao, fmt

from . import nbr6118 as N6118
from . import nbr9062 as N9062
from . import vigas as VG
from . import fundacao as F
from . import protensao as PR
from .concreto import BITOLAS, Concreto, aco as aco_armadura, cobrimento

PESO_CONCRETO = 25.0          # kN/m³ (NBR 6118, 8.2.2)


@dataclass
class DadosGalpaoPM:
    # identificação
    nome: str = "Galpão pré-moldado"
    cliente: str = ""
    local: str = ""
    responsavel: str = ""
    # geometria (m, graus)
    vao: float = 8.28
    vaos_longitudinais: List[float] = field(default_factory=lambda: [4.0, 6.3, 4.0, 4.935, 4.935, 4.932])
    altura_pilar: float = 9.0                 # do topo da fundação (boca do cálice) ao topo do pilar (fila A)
    altura_pilar_b: float = 0.0               # a fila B, quando diferente (0 = igual à A)
    inclinacao_graus: float = 11.31
    cobertura: str = "duas águas"             # ou "uma água" (o caimento de A para B pelas alturas)
    # cargas (kN/m²)
    cobertura_permanente: float = 0.20        # telha + estrutura metálica da cobertura
    sobrecarga: float = 0.25
    fechamento_lateral: float = 0.10          # peso do fechamento preso nos pilares (por m² de parede)
    # vento (NBR 6123)
    v0: float = 48.0
    s1: float = 1.0
    categoria: str = "IV"
    classe: str = "B"
    grupo: int = 3                            # S3 (NBR 6123:2023, Tabela 4): 3 = indústria, comércio, residência — 1,00
    aberturas: str = "duas faces opostas"
    # concreto e armadura
    fck: float = 35.0
    agregado: str = "basalto"
    aco: str = "CA-50"
    caa: str = "II"
    phi_fluencia: float = 2.0
    # pilares: seções candidatas b × h (cm; h na direção do vão)
    secoes_pilar: List[Tuple[float, float]] = field(default_factory=lambda: [
        (30, 40), (35, 40), (40, 40), (40, 45), (40, 50), (45, 50), (50, 50), (40, 60), (50, 60), (60, 60)])
    # cálice
    interface_calice: str = "rugosa"
    parede_calice: float = 20.0               # cm
    # produção: pré-fabricado (usina com o controle de 12.1.2 da NBR 9062: γc = 1,3, γs = 1,10) ou
    # pré-moldado (γc = 1,4, γs = 1,15) — 8.1
    pre_fabricado: bool = False
    # vigas longitudinais no topo dos pilares, apoiadas em consolos: "nenhuma", "calha" (seção U) ou
    # "travamento" (retangular)
    vigas_longitudinais: str = "nenhuma"
    secoes_calha: List[Tuple[float, float, float, float]] = field(default_factory=lambda: [   # B, h, parede, fundo (cm)
        (50, 40, 8, 8), (60, 45, 8, 10), (70, 50, 10, 10), (80, 60, 10, 12), (90, 70, 12, 12)])
    secoes_travamento: List[Tuple[float, float]] = field(default_factory=lambda: [              # b, h (cm)
        (15, 30), (15, 40), (20, 40), (20, 50), (25, 50), (25, 60), (30, 60), (30, 70)])
    extremidade_vigas: str = "sem recorte"    # ou "dente Gerber"
    consolo_altura: float = 40.0              # cm, no engastamento
    consolo_a: float = 15.0                   # cm, da face do pilar ao centro do apoio da viga
    # viga de cobertura em concreto (transversal, no topo dos pilares; seção I com o banzo de cima na
    # inclinação da cobertura) — a telha e as terças ficam em cobertura_permanente
    viga_cobertura: bool = False
    secoes_viga_cobertura: List[Tuple[float, float, float, float]] = field(default_factory=lambda: [  # mesa b, mesa h, alma, h no apoio
        (25, 10, 10, 40), (30, 10, 12, 40), (30, 12, 12, 50), (35, 12, 12, 60), (40, 15, 15, 60), (40, 15, 15, 80), (50, 15, 15, 100)])
    umidade: float = 75.0                     # % (retração, NBR 6118, Tabela 8.1)
    # a cobertura de outra obra do programa (o slug), trazida para o 3D para conferir o encaixe
    cobertura_projeto: str = ""
    # pilares de oitão (entre as filas A e B, nos pórticos das pontas): (número do eixo, distância à fila A em m)
    pilares_oitao: List[Tuple[int, float]] = field(default_factory=list)
    # o elemento da planta de lançamento de cada pilar ("1/A" → {"id", "marca"}), quando os dados vieram dela
    # (premoldado.da_planta): o 3D e as plantas de saída levam o id, para a ida e volta (R5)
    origem_planta: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # protensão por pré-tração (cordoalhas retas na pista): a viga de cobertura e as terças em concreto
    viga_cobertura_protendida: bool = False
    tercas_protendidas: bool = False          # terças T protendidas sobre as vigas de cobertura (pede a viga de cobertura)
    tercas_espacamento: float = 2.0           # m entre terças, na água
    secoes_terca: List[Tuple[float, float, float, float]] = field(default_factory=lambda: [   # mesa b, mesa h, alma, h (cm)
        (20, 6, 8, 25), (25, 6, 10, 30), (30, 7, 10, 35), (30, 8, 12, 40), (35, 8, 12, 50)])
    cordoalha: str = "CP190 RB 12,7"
    sigma_pi: float = 0.74                    # σpi/fptk (≤ 0,74 na pré-tração)
    fcj_liberacao: float = 25.0               # MPa na liberação (≥ 21)
    acomodacao_pista: float = 0.0             # mm (fabricante das ancoragens)
    pista: float = 100.0                      # m
    # fundação sob o cálice: "nenhuma" (só o cálice), "sapata" ou "estacas" — os dados do solo e da estaca
    # são da obra (NBR 6122, fora da pasta Normas)
    fundacao: str = "nenhuma"
    sigma_adm: float = 200.0                  # kPa
    fracao_comprimida: float = 0.667          # mínimo da base comprimida (a conferir)
    peso_solo: float = 18.0                   # kN/m³
    estaca_diametro: float = 30.0             # cm
    estaca_carga: float = 300.0               # kN, admissível à compressão
    estaca_tracao: float = 0.0                # kN, admissível à tração
    estaca_espacamento: float = 3.0           # × diâmetro
    # ponte rolante (os valores das rodas, o impacto e as forças horizontais são do fabricante da ponte: a
    # NBR 8800:2024 traz só os γ e os ψ)
    ponte_rolante: bool = False
    pr_altura: float = 6.0                    # m, topo do consolo (apoio da viga de rolamento) acima da boca do cálice
    pr_excentricidade: float = 60.0           # cm, do eixo do pilar ao eixo do trilho, para dentro do galpão
    pr_roda_max: float = 0.0                  # kN por roda, do lado do carro (sem impacto)
    pr_roda_min: float = 0.0                  # kN por roda, do outro lado
    pr_rodas: int = 2                         # rodas por cabeceira (por lado)
    pr_entre_eixos: float = 3.0               # m entre rodas vizinhas da cabeceira
    pr_impacto: float = 0.0                   # fração das cargas verticais das rodas
    pr_transversal: float = 0.0               # kN por lado (soma das rodas), perpendicular ao trilho
    pr_longitudinal: float = 0.0              # kN por lado, frenagem
    pr_viga_peso: float = 3.0                 # kN/m: viga de rolamento e trilho
    pr_altura_trilho: float = 0.8             # m, do topo do consolo ao topo do trilho
    consolo_pr_altura: float = 60.0           # cm, altura do consolo da ponte no engastamento

    def validar(self):
        if not (4.0 <= self.vao <= 40.0):
            raise ErroDeDados("vão fora da faixa (4 a 40 m): %s" % fmt(self.vao, 2))
        if not self.vaos_longitudinais or any(v <= 0 for v in self.vaos_longitudinais):
            raise ErroDeDados("informe os vãos entre pórticos (m)")
        if not (3.0 <= self.altura_pilar <= 18.0):
            raise ErroDeDados("altura do pilar fora da faixa (3 a 18 m): %s" % fmt(self.altura_pilar, 2))
        if not (0.0 <= self.inclinacao_graus <= 30.0):
            raise ErroDeDados("inclinação da cobertura fora da faixa (0 a 30°)")
        if self.vigas_longitudinais not in ("nenhuma", "calha", "travamento"):
            raise ErroDeDados("vigas longitudinais: use nenhuma, calha ou travamento")
        if self.ponte_rolante:
            if self.pr_roda_max <= 0:
                raise ErroDeDados("ponte rolante: informe a carga máxima por roda (dado do fabricante da ponte)")
            if not (1.0 <= self.pr_altura < self.altura_pilar):
                raise ErroDeDados("ponte rolante: o consolo (%s m) tem de ficar abaixo do topo do pilar (%s m)"
                                  % (fmt(self.pr_altura, 2), fmt(self.altura_pilar, 2)))
            if int(self.pr_rodas) not in (1, 2, 3, 4):
                raise ErroDeDados("ponte rolante: de 1 a 4 rodas por cabeceira")
        if self.tercas_protendidas and not self.viga_cobertura:
            raise ErroDeDados("terças protendidas: ligue a viga de cobertura em concreto (as terças se apoiam nela)")
        if self.fundacao not in ("nenhuma", "sapata", "estacas"):
            raise ErroDeDados("fundação: use nenhuma, sapata ou estacas")
        if self.cobertura not in ("duas águas", "uma água"):
            raise ErroDeDados("cobertura: use duas águas ou uma água")
        if self.altura_pilar_b and not (3.0 <= self.altura_pilar_b <= 18.0):
            raise ErroDeDados("altura dos pilares da fila B fora da faixa (3 a 18 m)")
        if self.extremidade_vigas not in ("sem recorte", "dente Gerber"):
            raise ErroDeDados("extremidade das vigas: use sem recorte ou dente Gerber")

    @property
    def comprimento(self) -> float:
        return sum(self.vaos_longitudinais)

    @property
    def n_porticos(self) -> int:
        return len(self.vaos_longitudinais) + 1

    def largura_de_influencia(self, i: int) -> float:
        v = self.vaos_longitudinais
        esq = v[i - 1] / 2 if i > 0 else 0.0
        dir_ = v[i] / 2 if i < len(v) else 0.0
        return esq + dir_

    @property
    def altura_b(self) -> float:
        return self.altura_pilar_b if self.altura_pilar_b > 0 else self.altura_pilar

    @property
    def filas_diferentes(self) -> bool:
        return abs(self.altura_b - self.altura_pilar) > 0.005

    @property
    def uma_agua(self) -> bool:
        return self.cobertura == "uma água"

    @property
    def inclinacao_efetiva(self) -> float:
        """graus: a informada nas duas águas; na de uma água, a que as alturas das filas dão"""
        if self.uma_agua:
            return math.degrees(math.atan2(abs(self.altura_b - self.altura_pilar), self.vao))
        return self.inclinacao_graus

    def altura_tipo(self, tipo: str) -> float:
        """a altura (m) dos pilares de um tipo: os "… B" na fila B; o oitão, o mais alto da linha"""
        if tipo.endswith(" B"):
            return self.altura_b
        if tipo == "oitão":
            return max(self.altura_oitao(y) for _e, y in (self.pilares_oitao or [(1, self.vao / 2)]))
        return self.altura_pilar

    def altura_oitao(self, y: float) -> float:
        """a altura (m) do topo de um pilar de oitão a y da fila A. Com a cobertura metálica o pilar para no
        nível do apoio das filas (a coluna de oitão da estrutura metálica sobe até a água): na de uma água,
        na linha que vai do topo de A ao topo de B; nas duas águas, no topo das filas. Com a viga de
        cobertura em concreto, o pilar sobe até a água."""
        if self.uma_agua:
            return self.altura_pilar + (self.altura_b - self.altura_pilar) * y / self.vao
        if self.viga_cobertura:
            return self.altura_pilar + math.tan(math.radians(self.inclinacao_graus)) * min(y, self.vao - y)
        return self.altura_pilar

    @property
    def altura_cumeeira(self) -> float:
        if self.uma_agua:
            return max(self.altura_pilar, self.altura_b)
        return self.altura_pilar + self.vao / 2 * math.tan(math.radians(self.inclinacao_graus))


@dataclass
class PilarDimensionado:
    tipo: str                                  # "canto" | "intermediário"
    b: float
    h: float
    armadura: Optional[N6118.ArmaduraPilar]
    resultado: Optional[Resultado]
    estribos: Tuple[float, float] = (5.0, 20.0)
    esforcos: dict = field(default_factory=dict)
    quantidade: int = 0
    comprimento_total: float = 0.0             # m (com o embutimento)
    alternativas: List[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.resultado and self.resultado.ok)


@dataclass
class ProjetoGalpaoPM:
    dados: DadosGalpaoPM
    vento: dict = field(default_factory=dict)
    combinacoes: List[dict] = field(default_factory=list)
    esforcos: Dict[str, dict] = field(default_factory=dict)
    pilares: List[PilarDimensionado] = field(default_factory=list)
    calices: List[Resultado] = field(default_factory=list)
    icamento: List[Resultado] = field(default_factory=list)
    vigas: List[VG.VigaDimensionada] = field(default_factory=list)
    ligacoes: List[Resultado] = field(default_factory=list)      # consolos dos pilares
    fundacoes: List[Resultado] = field(default_factory=list)     # sapata ou bloco sob o cálice, por tipo de pilar
    cargas_vigas: dict = field(default_factory=dict)
    lista: List[dict] = field(default_factory=list)
    hipoteses: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (not self.erros and all(p.ok for p in self.pilares) and all(v.ok for v in self.vigas)
                and all(r.ok for r in self.calices + self.icamento + self.ligacoes + self.fundacoes))


# ------------------------------------------------------------------ ações e combinações

def _vento(d: DadosGalpaoPM) -> dict:
    vg = cargas.pressoes_galpao(b=d.vao, a=d.comprimento, h=max(d.altura_pilar, d.altura_b), theta_graus=d.inclinacao_efetiva, V0=d.v0,
                                categoria=d.categoria, classe=d.classe, S1=d.s1, grupo=d.grupo, aberturas=d.aberturas)
    tab = vg.tabela()

    def p(direcao, chave, cpi, escolher=min):
        c = [l["p (kN/m²)"] for l in tab if l["direção"] == direcao and abs(l["Cpi"] - cpi) < 1e-6 and chave in l["superfície"].lower()]
        return escolher(c) if c else 0.0
    casos = {}
    for cpi in (0.2, -0.3):
        casos["transversal cpi %+.1f" % cpi] = {
            "direcao": "transversal", "cpi": cpi,
            "parede_barlavento": p("transversal", "parede lateral barlavento", cpi, max),
            "parede_sotavento": p("transversal", "parede lateral sotavento", cpi),
            "telhado_barlavento": p("transversal", "telhado barlavento", cpi),
            "telhado_sotavento": p("transversal", "telhado sotavento", cpi)}
        casos["longitudinal cpi %+.1f" % cpi] = {
            "direcao": "longitudinal", "cpi": cpi,
            "oitao_barlavento": p("longitudinal", "oitão barlavento", cpi, max),
            "oitao_sotavento": p("longitudinal", "oitão sotavento", cpi),
            "parede_lateral": p("longitudinal", "parede lateral zona 2", cpi),
            "telhado": p("longitudinal", "telhado zona 2", cpi)}
    return {"objeto": vg, "V0": d.v0, "S1": vg.S1, "S2": vg.S2, "S3": vg.S3, "Vk": vg.Vk, "q": vg.q, "tabela": tab, "casos": casos,
            "passos": getattr(vg, "passos", [])}


#: NBR 8800:2024, Tabela 2 — pilares e outros elementos que suportam vigas de rolamento de pontes rolantes
PSI_PONTE_PILAR = (0.7, 0.6, 0.4)
#: os casos da ponte: o carro junto de cada lado, com a força transversal nos dois sentidos
PONTE_CASOS = ["PR esq →", "PR esq ←", "PR dir →", "PR dir ←"]


def combinacoes(ventos: List[str], ponte: Sequence[str] = ()) -> List[dict]:
    """ELU normais (NBR 8681): o peso do pré-moldado com γ = 1,3 (pré-moldada), a cobertura e o
    fechamento com 1,4; sobrecarga 1,5 (ψ0 = 0,8); vento 1,4 (ψ0 = 0,6); o levantamento com as
    permanentes favoráveis (γ = 1,0)"""
    g_pm = cargas.GAMA_G["pré-moldada"][0]
    psi_sc = cargas.PSI["cobertura"][0]
    psi_v = cargas.PSI["vento"][0]
    out = [{"nome": "ELU sobrecarga", "fatores": {"PP": g_pm, "CP": 1.4, "SC": 1.5}}]
    for w in ventos:
        out.append({"nome": "ELU sobrecarga + %s" % w, "fatores": {"PP": g_pm, "CP": 1.4, "SC": 1.5, w: 1.4 * psi_v}})
        out.append({"nome": "ELU %s + sobrecarga" % w, "fatores": {"PP": g_pm, "CP": 1.4, "SC": 1.5 * psi_sc, w: 1.4}})
        out.append({"nome": "ELU %s (permanentes favoráveis)" % w, "fatores": {"PP": 1.0, "CP": 1.0, w: 1.4}})
    g_pr = cargas.GAMA_Q["ponte rolante"][0]
    psi_pr = PSI_PONTE_PILAR[0]
    for c in ponte:
        out.append({"nome": "ELU %s + sobrecarga" % c, "fatores": {"PP": g_pm, "CP": 1.4, "SC": 1.5 * psi_sc, c: g_pr}})
        for w in ventos:
            out.append({"nome": "ELU %s + %s" % (c, w), "fatores": {"PP": g_pm, "CP": 1.4, c: g_pr, w: 1.4 * psi_v}})
            out.append({"nome": "ELU %s + %s" % (w, c), "fatores": {"PP": g_pm, "CP": 1.4, w: 1.4, c: g_pr * psi_pr}})
    return out


def combinacoes_caracteristicas(ventos: List[str], ponte: Sequence[str] = ()) -> List[dict]:
    """as combinações com γ = 1 para o solo e as estacas: G + Q, com o vento como principal ou
    secundário (ψ0) e o vento com só as permanentes (a menor normal)"""
    psi_sc = cargas.PSI["cobertura"][0]
    psi_v = cargas.PSI["vento"][0]
    out = [{"nome": "G + Q", "fatores": {"PP": 1.0, "CP": 1.0, "SC": 1.0}}]
    for w in ventos:
        out.append({"nome": "G + Q + ψ0·%s" % w, "fatores": {"PP": 1.0, "CP": 1.0, "SC": 1.0, w: psi_v}})
        out.append({"nome": "G + %s + ψ0·Q" % w, "fatores": {"PP": 1.0, "CP": 1.0, "SC": psi_sc, w: 1.0}})
        out.append({"nome": "G + %s" % w, "fatores": {"PP": 1.0, "CP": 1.0, w: 1.0}})
    for c in ponte:
        out.append({"nome": "G + %s" % c, "fatores": {"PP": 1.0, "CP": 1.0, "SC": psi_sc, c: 1.0}})
        for w in ventos:
            out.append({"nome": "G + %s + ψ0·%s" % (c, w), "fatores": {"PP": 1.0, "CP": 1.0, c: 1.0, w: psi_v}})
            out.append({"nome": "G + %s + ψ0·%s" % (w, c), "fatores": {"PP": 1.0, "CP": 1.0, w: 1.0, c: PSI_PONTE_PILAR[0]}})
    return out


def _ventos(vento: dict) -> List[str]:
    return ["%s %s" % (k, s_) for k in vento["casos"] for s_ in ("→", "←")]


def _ponte(d: "DadosGalpaoPM") -> List[str]:
    return list(PONTE_CASOS) if d.ponte_rolante else []


def fator_rodas(d: "DadosGalpaoPM", i: int) -> float:
    """a soma das ordenadas da linha de influência da reação no pórtico i (vigas de rolamento biapoiadas
    entre pórticos) com as rodas de uma cabeceira na posição mais desfavorável"""
    xs = [0.0]
    for v in d.vaos_longitudinais:
        xs.append(xs[-1] + v)
    X = xs[i]
    esq = xs[i - 1] if i > 0 else None
    dir_ = xs[i + 1] if i < len(xs) - 1 else None

    def eta(x):
        if esq is not None and esq <= x <= X:
            return (x - esq) / (X - esq)
        if dir_ is not None and X <= x <= dir_:
            return (dir_ - x) / (dir_ - X)
        return 0.0
    offs = [k * d.pr_entre_eixos for k in range(int(d.pr_rodas))]
    melhor = 0.0
    for x0 in np.linspace(X - offs[-1], X, 201):
        melhor = max(melhor, sum(eta(x0 + o) for o in offs))
    return melhor


# ------------------------------------------------------------------ o pórtico transversal

def _barras_pilar(d: DadosGalpaoPM) -> Dict[str, Tuple[str, ...]]:
    """as barras de cada pilar no modelo: uma só, ou duas (abaixo e acima do consolo da ponte rolante)"""
    if d.ponte_rolante:
        return {"esq": ("pilar_esq", "pilar_esq_sup"), "dir": ("pilar_dir", "pilar_dir_sup")}
    return {"esq": ("pilar_esq",), "dir": ("pilar_dir",)}


def _modelo_portico(d: DadosGalpaoPM, esp: float, b: float, h: float, conc: Concreto, vento: dict, cv: Optional[dict] = None,
                    kpr: float = 0.0):
    """o modelo do pórtico (dois pilares engastados, a cobertura como escora rotulada) com os casos
    de carga; devolve (modelo, nomes dos casos de vento). `cv`: as cargas das vigas no topo (o peso
    das longitudinais por metro, a água da calha por metro, o peso da viga de cobertura por pilar)"""
    cv = cv or {}
    HA, HB = d.altura_pilar * 100.0, d.altura_b * 100.0
    L = d.vao * 100.0
    m = analise.Modelo("pórtico pré-moldado")
    m.add_no(0.0, 0.0, "engastado", "Aesq")
    m.add_no(0.0, HA, None, "Tesq")
    m.add_no(L, HB, None, "Tdir")
    m.add_no(L, 0.0, "engastado", "Adir")
    A, I = b * h, b * h ** 3 / 12.0
    E = conc.Ecs
    PIL = _barras_pilar(d)
    if d.ponte_rolante:
        Hr = d.pr_altura * 100.0
        m.add_no(0.0, Hr, None, "Cesq")
        m.add_no(L, Hr, None, "Cdir")
        for lado, x0 in (("esq", 0.0), ("dir", L)):
            m.add_barra("A" + lado, "C" + lado, A, I, E=E, rotulo=PIL[lado][0])
            m.add_barra("C" + lado, "T" + lado, A, I, E=E, rotulo=PIL[lado][1])
    else:
        m.add_barra("Aesq", "Tesq", A, I, E=E, rotulo="pilar_esq")
        m.add_barra("Adir", "Tdir", A, I, E=E, rotulo="pilar_dir")
    m.add_barra("Tesq", "Tdir", 1000.0, 1.0, E=E, rotulo="cobertura", rotula_i=True, rotula_f=True)
    todas = PIL["esq"] + PIL["dir"]
    th = math.radians(d.inclinacao_efetiva)
    area_agua = esp * d.vao / 2 / math.cos(th)            # m² por água (ou por metade da água única), no pórtico
    # o sinal x da normal do telhado em cada nó: nas duas águas cada água pende para o seu lado; na de uma
    # água o plano inteiro pende para a fila mais baixa
    s_agua = 1.0 if d.altura_b >= d.altura_pilar else -1.0
    pp = PESO_CONCRETO * (b * h / 1e4)                     # kN/m do pilar
    # PP: o peso do pilar
    m.caso("PP")
    for bar in todas:
        m.distribuida("PP", bar, -pp / 100.0, "global_y")
    # as vigas pré-moldadas que chegam no topo (centradas no eixo do pilar na direção do vão)
    P_vigas = cv.get("pp_long", 0.0) * esp + cv.get("pp_cob", 0.0)
    if P_vigas:
        for no in ("Tesq", "Tdir"):
            m.nodal("PP", no, 0.0, -P_vigas)
    # CP: a cobertura e o fechamento
    m.caso("CP")
    for no in ("Tesq", "Tdir"):
        m.nodal("CP", no, 0.0, -(d.cobertura_permanente + cv.get("cp_tercas", 0.0)) * esp * d.vao / 2)
    for bar in todas:
        m.distribuida("CP", bar, -d.fechamento_lateral * esp / 100.0, "global_y")
    if d.ponte_rolante:
        # a viga de rolamento e o trilho, no consolo (excentricidade e para dentro do galpão)
        e = d.pr_excentricidade
        Fv = d.pr_viga_peso * esp
        m.nodal("CP", "Cesq", 0.0, -Fv, -Fv * e)
        m.nodal("CP", "Cdir", 0.0, -Fv, Fv * e)
        imp = 1.0 + d.pr_impacto
        Vmax, Vmin = d.pr_roda_max * imp * kpr, d.pr_roda_min * imp * kpr
        Ht = d.pr_transversal / int(d.pr_rodas) * kpr
        ht = d.pr_altura_trilho * 100.0
        for caso in PONTE_CASOS:
            m.caso(caso)
            Vl, Vr = (Vmax, Vmin) if " esq " in caso else (Vmin, Vmax)
            sentido = 1.0 if caso.endswith("→") else -1.0
            m.nodal(caso, "Cesq", sentido * Ht, -Vl, -Vl * e - sentido * Ht * ht)
            m.nodal(caso, "Cdir", sentido * Ht, -Vr, Vr * e - sentido * Ht * ht)
    m.caso("SC")
    for no in ("Tesq", "Tdir"):
        m.nodal("SC", no, 0.0, -d.sobrecarga * esp * d.vao / 2 - cv.get("q_long", 0.0) * esp)
    for nome, c in vento["casos"].items():
        for sentido in (1, -1):                           # da esquerda para a direita e o contrário
            caso = "%s %s" % (nome, "→" if sentido > 0 else "←")
            m.caso(caso)
            barl, sot = (PIL["esq"], PIL["dir"]) if sentido > 0 else (PIL["dir"], PIL["esq"])
            tb, ts = ("Tesq", "Tdir") if sentido > 0 else ("Tdir", "Tesq")
            if c["direcao"] == "transversal":
                # paredes: a pressão de barlavento empurra para dentro, a sucção de sotavento puxa para
                # fora — as duas no sentido do vento
                for bar in barl:
                    m.distribuida(caso, bar, sentido * c["parede_barlavento"] * esp / 100.0, "global_x")
                for bar in sot:
                    m.distribuida(caso, bar, -sentido * c["parede_sotavento"] * esp / 100.0, "global_x")
                # telhado: a força normal a cada água (sucção p < 0 puxa para fora)
                for p_, no, lado in ((c["telhado_barlavento"], tb, -1), (c["telhado_sotavento"], ts, 1)):
                    F = p_ * area_agua                         # kN (negativo: sucção)
                    Fv = -F * math.cos(th)                     # para cima quando sucção
                    nx = -s_agua if d.uma_agua else lado * sentido
                    Fh = -F * math.sin(th) * nx                # a água de barlavento puxa contra o vento
                    m.nodal(caso, no, Fh, Fv)
            else:
                # longitudinal: as paredes laterais em sucção puxam cada pilar para fora; o telhado levanta
                p_ = c["parede_lateral"]
                for bar in PIL["esq"]:
                    m.distribuida(caso, bar, p_ * esp / 100.0, "global_x")      # sucção (p<0): para −x
                for bar in PIL["dir"]:
                    m.distribuida(caso, bar, -p_ * esp / 100.0, "global_x")
                for no in ("Tesq", "Tdir"):
                    m.nodal(caso, no, 0.0, -c["telhado"] * area_agua * math.cos(th))
    return m, ["%s %s" % (n, s_) for n in vento["casos"] for s_ in ("→", "←")]


def _ler_pilar(d: DadosGalpaoPM, r, barras: Tuple[str, ...]) -> dict:
    """N (compressão), M na base e no meio, V na base e no topo de um pilar (uma ou duas barras)"""
    H = (d.altura_b if barras[0] == "pilar_dir" else d.altura_pilar) * 100.0
    inf = r.barra(barras[0])
    Nb, Vb, Mb = inf.esforcos(0.0)
    if len(barras) == 1:
        Mm = inf.esforcos(H / 2)[2]
        Vt = inf.esforcos(H, -1)[1]
    else:
        Hr = d.pr_altura * 100.0
        sup = r.barra(barras[1])
        Mm = inf.esforcos(H / 2)[2] if H / 2 <= Hr else sup.esforcos(H / 2 - Hr)[2]
        Vt = sup.esforcos(H - Hr, -1)[1]
    return {"N": -Nb, "M_base": Mb, "M_meio": Mm, "V_base": Vb, "V_topo": Vt}


def _portico(d: DadosGalpaoPM, esp: float, b: float, h: float, conc: Concreto, vento: dict, cv: Optional[dict] = None,
             kpr: float = 0.0) -> Dict[str, dict]:
    """os esforços nos dois pilares de um pórtico (largura de influência `esp`, m) para cada caso
    de carga: base e meia altura (M em kN·cm, N em kN de compressão, V em kN)"""
    m, _casos_v = _modelo_portico(d, esp, b, h, conc, vento, cv, kpr)
    PIL = _barras_pilar(d)
    out = {}
    nomes = ["PP", "CP", "SC"] + _ventos(vento) + _ponte(d)
    for caso in nomes:
        r = analise.resolver(m, caso, 21)
        out[caso] = {"pilar_esq": _ler_pilar(d, r, PIL["esq"]), "pilar_dir": _ler_pilar(d, r, PIL["dir"])}
    return out


# ------------------------------------------------------------------ a direção longitudinal

def _longitudinal(d: DadosGalpaoPM, vento: dict) -> Dict[str, dict]:
    """a força do vento no oitão dividida igualmente pelos pilares, no topo (a cobertura
    contraventada distribui); os pilares de canto levam também a parede do oitão (apoiada na
    base e no topo travado: M = q·H²/8). Momentos na base (kN·cm) por caso, para o pilar
    intermediário e para o de canto"""
    H = max(d.altura_pilar, d.altura_b)
    th = math.radians(d.inclinacao_graus)
    A_oitao = d.vao * (d.altura_pilar + d.altura_b) / 2 + (0.0 if d.uma_agua else d.vao / 2 * (d.vao / 2 * math.tan(th)))
    n_pil = 2 * d.n_porticos
    out = {}
    for nome, c in vento["casos"].items():
        if c["direcao"] != "longitudinal":
            continue
        F = (c["oitao_barlavento"] - c["oitao_sotavento"]) * A_oitao      # kN
        F_pil = F / n_pil
        q_canto = max(abs(c["oitao_barlavento"]), abs(c["oitao_sotavento"])) * d.vao / 2   # kN/m
        for s_ in ("→", "←"):
            esf = {}
            for tipo in tipos_de_pilar(d):
                Ht = d.altura_tipo(tipo)                    # cada fila com a sua altura
                if tipo.startswith("canto"):
                    esf[tipo] = {"M_base": (F_pil * Ht + q_canto * Ht * Ht / 8.0) * 100.0,
                                 "M_meio": (F_pil * Ht / 2 + q_canto * Ht * Ht / 16.0) * 100.0, "F_topo": F_pil,
                                 "V_base": F_pil + 5.0 / 8.0 * q_canto * Ht}
                else:
                    esf[tipo] = {"M_base": F_pil * Ht * 100.0, "M_meio": F_pil * Ht / 2 * 100.0, "F_topo": F_pil, "V_base": F_pil}
            out["%s %s" % (nome, s_)] = esf
    if d.ponte_rolante:
        # a frenagem de um lado repartida pelos pilares daquele lado (a viga de rolamento ligada a todos),
        # no topo do trilho
        F = d.pr_longitudinal / d.n_porticos
        z = d.pr_altura + d.pr_altura_trilho
        for c in PONTE_CASOS:
            out[c] = {tipo: {"M_base": F * z * 100.0, "M_meio": F * max(z - d.altura_tipo(tipo) / 2, 0.0) * 100.0, "F_topo": 0.0, "V_base": F}
                      for tipo in tipos_de_pilar(d)}
    return out


def _alfa_b(M_base: float, M_meio: float) -> float:
    """15.8.2 b): pilar em balanço — αb = 0,80 + 0,20·MC/MA ≥ 0,85 (MC no meio, MA no engaste)"""
    if abs(M_base) < 1e-9:
        return 1.0
    return min(max(0.80 + 0.20 * M_meio / M_base, 0.85), 1.0)


# ------------------------------------------------------------------ o dimensionamento

def _excentricidade_consolos(d: DadosGalpaoPM, i: int, b: float, cv: dict) -> Dict[str, float]:
    """o momento (kN·cm, direção longitudinal, constante ao longo do pilar) das vigas longitudinais
    apoiadas nos consolos do pórtico i: a diferença das reações dos dois lados × (b/2 + a)"""
    if not cv.get("pp_long"):
        return {}
    v = d.vaos_longitudinais
    vl = v[i - 1] if i > 0 else 0.0
    vr = v[i] if i < len(v) else 0.0
    e = b / 2.0 + d.consolo_a
    return {"PP": cv["pp_long"] * abs(vr - vl) / 2.0 * e, "SC": cv.get("q_long", 0.0) * abs(vr - vl) / 2.0 * e}


def _situacoes(d: DadosGalpaoPM, conc: Concreto, vento: dict, b: float, h: float, cv: Optional[dict] = None,
               comb: Optional[List[dict]] = None) -> Dict[str, List[dict]]:
    """as situações de projeto (Nd, Mx, αbx, My, αby, Nsg, combinação) de cada tipo de pilar, na
    envoltória de todos os pórticos; ficam as que governam. `comb`: outras combinações (as
    características da fundação); sem ele, as últimas"""
    cv = cv or {}
    comb = comb or combinacoes(_ventos(vento), _ponte(d))
    lon = _longitudinal(d, vento)
    psi2 = cargas.PSI["cobertura"][2]
    sit: Dict[str, List[dict]] = {t: [] for t in tipos_de_pilar(d)}
    for i in range(d.n_porticos):
        esp = d.largura_de_influencia(i)
        tipo0 = "canto" if i in (0, d.n_porticos - 1) else "intermediário"
        por = _portico(d, esp, b, h, conc, vento, cv, fator_rodas(d, i) if d.ponte_rolante else 0.0)
        exc = _excentricidade_consolos(d, i, b, cv)
        for bar in ("pilar_esq", "pilar_dir"):
            tipo = tipo0 + (" B" if bar == "pilar_dir" and d.filas_diferentes else "")
            Nsg = sum(por[c][bar]["N"] for c in ("PP", "CP")) + psi2 * por["SC"][bar]["N"]
            for cb in comb:
                f = cb["fatores"]
                Nd = sum(fa * por[c][bar]["N"] for c, fa in f.items())
                Mb = sum(fa * por[c][bar]["M_base"] for c, fa in f.items())
                Mm = sum(fa * por[c][bar]["M_meio"] for c, fa in f.items())
                Me = sum(fa * exc[c] for c, fa in f.items() if c in exc)
                My = sum(fa * lon[c][tipo]["M_base"] for c, fa in f.items() if c in lon) + Me
                Mym = sum(fa * lon[c][tipo]["M_meio"] for c, fa in f.items() if c in lon) + Me
                Vx = sum(fa * por[c][bar]["V_base"] for c, fa in f.items())
                Vtx = sum(fa * por[c][bar]["V_topo"] for c, fa in f.items())
                Vty = sum(fa * lon[c][tipo]["F_topo"] for c, fa in f.items() if c in lon)
                Vy = sum(fa * lon[c][tipo]["V_base"] for c, fa in f.items() if c in lon)
                sit[tipo].append({"Nd": Nd, "Mx": abs(Mb), "abx": _alfa_b(Mb, Mm), "My": abs(My), "aby": _alfa_b(My, Mym),
                                  "Vx": abs(Vx), "Vy": abs(Vy), "Htopo": math.hypot(Vtx, Vty),
                                  "Nsg": Nsg, "comb": cb["nome"], "portico": i + 1, "pilar": bar})
    for tipo, lst in sit.items():
        if not lst:
            continue
        chaves = {id(max(lst, key=lambda s: s["Mx"])), id(max(lst, key=lambda s: s["My"])), id(max(lst, key=lambda s: s["Htopo"])),
                  id(max(lst, key=lambda s: s["Nd"])), id(min(lst, key=lambda s: s["Nd"])),
                  id(max(lst, key=lambda s: s["Mx"] / max(s["Nd"], 1.0)))}
        sit[tipo] = [s for s in lst if id(s) in chaves]
    return sit


def tipos_de_pilar(d: DadosGalpaoPM) -> List[str]:
    """os tipos das filas: canto e intermediário; com alturas diferentes, os da fila B à parte"""
    base = ["canto", "intermediário"]
    return base + [t + " B" for t in base] if d.filas_diferentes else base


def _verificar_pilar(d: DadosGalpaoPM, conc, aco, b, h, d_linha, arm, sits, altura: Optional[float] = None) -> Resultado:
    pior = None
    H = (altura if altura is not None else d.altura_pilar) * 100.0
    le = 2.0 * H
    for s in sits:
        r = N6118.pilar(b, h, arm, d_linha, H, le, le, max(s["Nd"], 1.0), s["Mx"], s["My"], s["abx"], s["aby"],
                        conc, aco, Nsg=max(s["Nsg"], 1.0), phi=d.phi_fluencia, elemento="Pilar")
        r.dados["situacao"] = s
        if pior is None or (pior.ok and not r.ok) or (pior.ok == r.ok and r.razao > pior.razao):
            pior = r
    return pior


def dimensionar(d: DadosGalpaoPM) -> ProjetoGalpaoPM:
    p = ProjetoGalpaoPM(dados=d)
    try:
        d.validar()
        gc, gs = N9062.coeficientes(d.pre_fabricado)
        conc = Concreto(d.fck, d.agregado, gama_c=gc)
        aco = dataclasses.replace(aco_armadura(d.aco), gama_s=gs)
        p.vento = _vento(d)
        _vigas(d, p, conc, aco)
        cv = p.cargas_vigas
        c_nom = cobrimento(d.caa, "pilar", pre_fabricado=True)
        for tipo in tipos_de_pilar(d):
            escolhido = None
            H_t = d.altura_tipo(tipo)
            for (b, h) in sorted(d.secoes_pilar, key=lambda s_: (s_[0] * s_[1], s_[1])):
                lam = 2.0 * H_t * 100.0 * math.sqrt(12.0) / min(b, h)
                if lam > 140.0:
                    continue
                sits = _situacoes(d, conc, p.vento, b, h, cv)[tipo]
                if not sits:
                    continue
                d_linha = c_nom + 0.63 + 1.0                       # cobrimento + estribo + meia barra (ø20)
                arm, r = N6118.armar_pilar(b, h, d_linha, lambda a: _verificar_pilar(d, conc, aco, b, h, d_linha, a, sits, H_t))
                if arm is not None and r is not None and r.ok:
                    escolhido = PilarDimensionado(tipo, b, h, arm, r, N6118.estribos_pilar(arm), {"situacoes": sits})
                    break
            if escolhido is None:
                if tipo.startswith("canto") or d.n_porticos > 2:
                    p.erros.append("pilar %s: nenhuma seção candidata passa — aumente as seções" % tipo)
                continue
            filas = 1 if d.filas_diferentes else 2
            escolhido.quantidade = (2 if tipo.startswith("canto") else d.n_porticos - 2) * filas
            p.pilares.append(escolhido)
        _pilares_oitao(d, p, conc, aco, c_nom)
        for pil in p.pilares:
            _calice_e_icamento(d, p, pil, conc, aco)
        _consolos(d, p, conc, aco)
        _consolo_ponte(d, p, conc, aco)
        _fundacoes(d, p, conc, aco)
        _deslocamento_topo(d, p, conc)
        _deslocamento_ponte(d, p, conc)
        _lista(d, p)
        p.hipoteses.append("Coeficientes das resistências: γc = %s e γs = %s (%s, NBR 9062, 8.1)."
                           % (fmt(gc, 2), fmt(gs, 2), "pré-fabricado" if d.pre_fabricado else "pré-moldado"))
        p.hipoteses += [
            "Pilares engastados na fundação por cálice e cobertura articulada no topo (escora entre os dois pilares do pórtico).",
            "Comprimento de flambagem ℓe = 2ℓ nas duas direções (pilar em balanço, NBR 6118, 15.8.2).",
        ] + ([
            "Filas com alturas diferentes: A com %s m e B com %s m (%s); os pilares da fila B são um tipo à parte."
            % (fmt(d.altura_pilar, 2), fmt(d.altura_b, 2), "cobertura de uma água, inclinação %s° pelas alturas" % fmt(d.inclinacao_efetiva, 2)
               if d.uma_agua else "duas águas")] if d.filas_diferentes or d.uma_agua else []) + [
            "Vento: V0 = %s m/s; coeficientes de forma da parte metálica (Tabelas 4 e 5)." % fmt(d.v0, 0),
            "Direção longitudinal: a força no oitão dividida igualmente entre os pilares pelo topo (cobertura contraventada); "
            "o pilar de canto leva também a parede do oitão (q·H²/8).",
            "Fluência (λ > 90) pela excentricidade adicional de 15.8.4 com φ = %s." % fmt(d.phi_fluencia, 1),
        ]
        if d.vigas_longitudinais != "nenhuma":
            p.hipoteses.append("Vigas longitudinais (%s) biapoiadas nos consolos dos pilares, com o vão de cálculo igual ao maior vão "
                               "entre eixos (a favor da segurança); o peso e %s chegam ao pilar com a excentricidade do consolo "
                               "(b/2 + a: momento constante na direção longitudinal)."
                               % (d.vigas_longitudinais, "a água da calha cheia (variável, com os ψ da cobertura)"
                                  if d.vigas_longitudinais == "calha" else "o que a viga leva"))
        if d.ponte_rolante:
            p.hipoteses.append("Ponte rolante: rodas de %s kN (máx.) e %s kN (mín.), impacto %s %%, transversal %s kN e frenagem %s kN por lado, "
                               "dados do fabricante (a NBR 8800:2024 traz só γ = 1,5 e os ψ — Tabela 2: pilares que suportam vigas de "
                               "rolamento 0,7/0,6/0,4). Vigas de rolamento biapoiadas entre pórticos; a reação no consolo pela linha de "
                               "influência com as %d rodas da cabeceira a %s m; a frenagem repartida pelos pilares do lado. O pilar tem um nó "
                               "no consolo (%s m), com a excentricidade de %s cm do trilho."
                               % (fmt(d.pr_roda_max, 1), fmt(d.pr_roda_min, 1), fmt(d.pr_impacto * 100, 0), fmt(d.pr_transversal, 1),
                                  fmt(d.pr_longitudinal, 1), int(d.pr_rodas), fmt(d.pr_entre_eixos, 2), fmt(d.pr_altura, 2), fmt(d.pr_excentricidade, 0)))
        if d.viga_cobertura:
            p.hipoteses.append("Viga de cobertura em concreto armado em cada pórtico, biapoiada no topo dos pilares, com a carga da "
                               "cobertura (cobertura permanente e sobrecarga pela largura de influência) distribuída uniforme; "
                               "a cobertura permanente informada deve ser só a telha e as terças.")
    except ErroDeDados as e:
        p.erros.append(str(e))
    return p


# ------------------------------------------------------------------ as vigas

def _meio_viga(d: DadosGalpaoPM, conc: Concreto, aco) -> VG.MeioViga:
    return VG.MeioViga(conc, aco, cobrimento(d.caa, "viga", pre_fabricado=True), d.caa, d.pre_fabricado, d.umidade)


def _escolher(casos: List[Tuple[VG.CasoViga, callable]], meio: VG.MeioViga) -> VG.VigaDimensionada:
    """a mais leve que passa (cada candidata com o seu caso — a água da calha depende da seção)"""
    ordem = sorted(casos, key=lambda c: c[1](c[0].vao * 50.0).A)
    alternativas, ultima = [], None
    for caso, secao_em in ordem:
        v = VG.verificar_viga(caso, secao_em, meio)
        alternativas.append({"secao": v.secao.texto(), "ok": v.ok, "razao": round(v.resultado.razao, 3) if v.resultado else None})
        ultima = v
        if v.ok:
            break
    ultima.alternativas = alternativas
    return ultima


def _vigas(d: DadosGalpaoPM, p: ProjetoGalpaoPM, conc: Concreto, aco) -> None:
    """as vigas longitudinais (calha ou travamento) e a viga de cobertura; as cargas que elas levam ao
    topo dos pilares ficam em p.cargas_vigas"""
    meio = _meio_viga(d, conc, aco)
    psi = cargas.PSI["cobertura"]
    cv = {}
    n_vaos = len(d.vaos_longitudinais)
    if d.vigas_longitudinais != "nenhuma":
        vmax = max(d.vaos_longitudinais)
        casos = []
        if d.vigas_longitudinais == "calha":
            for (B, h, t, tf) in d.secoes_calha:
                agua = VG.PESO_AGUA * (B - 2 * t) * (h - tf) / 1e4          # kN/m, calha cheia
                caso = VG.CasoViga("VC", "viga-calha", vmax, vmax, 0.0, agua, psi, 0.0, 400.0,
                                   "NBR 9062, Tabela 8 (empoçamento)", d.extremidade_vigas, quantidade=2 * n_vaos)
                casos.append((caso, (lambda B, h, t, tf: lambda x: VG.secao_U(B, h, t, tf))(B, h, t, tf)))
        else:
            for (b, h) in d.secoes_travamento:
                caso = VG.CasoViga("VT", "viga de travamento", vmax, vmax, 0.0, 0.0, psi, 0.0, 250.0, "NBR 9062, Tabela 9",
                                   d.extremidade_vigas, quantidade=2 * n_vaos)
                casos.append((caso, (lambda b, h: lambda x: VG.secao_retangular(b, h))(b, h)))
        v = _escolher(casos, meio)
        v.quantidade = 2 * n_vaos
        p.vigas.append(v)
        caso_v = next(c for c, f in casos if f(0.0).texto() == v.secao.texto())
        cv["pp_long"] = v.secao.peso
        cv["q_long"] = caso_v.q
        if not v.ok:
            p.avisos.append("%s: nenhuma das seções candidatas passa — aumente as seções" % v.funcao)
    pres = [c[k] for c in p.vento["casos"].values() for k in ("telhado_barlavento", "telhado_sotavento", "telhado") if k in c]
    succao_m2 = max(0.0, -min(pres)) if pres else 0.0
    base_pr = PR.Protensao(cordoalha=d.cordoalha, sigma_pi=d.sigma_pi, fcj=d.fcj_liberacao, acomodacao=d.acomodacao_pista, pista=d.pista)
    th = math.radians(d.inclinacao_graus)
    if d.tercas_protendidas and d.viga_cobertura:
        et = d.tercas_espacamento
        vmax = max(d.vaos_longitudinais)
        linhas = 2 * math.ceil(d.vao / 2 / math.cos(th) / et) + 1
        casos = []
        for (bf, hf, bw, h) in d.secoes_terca:
            caso = VG.CasoViga("TR", "terça", vmax, vmax, d.cobertura_permanente * et, d.sobrecarga * et, psi, succao_m2 * et, 250.0,
                               "NBR 9062, Tabela 8", "sem recorte", quantidade=linhas * n_vaos)
            casos.append((caso, (lambda bf, hf, bw, h: lambda x: VG.secao_T(bf, hf, bw, h))(bf, hf, bw, h)))
        v = PR.dimensionar(casos[0][0], casos, meio, base_pr)
        v.quantidade = linhas * n_vaos
        p.vigas.append(v)
        cv["cp_tercas"] = v.secao.peso / et                  # kN/m² de cobertura
        cv["tercas_linhas"] = linhas
        if not v.ok:
            p.avisos.append("terças: nenhuma das seções candidatas passa — aumente as seções")
        p.hipoteses.append("Terças protendidas T a cada %s m na água (%d linhas), biapoiadas nas vigas de cobertura, vão de %s m; a carga normal "
                           "à cobertura em projeção horizontal — a componente na água (sen θ) fica para a fixação das telhas e o "
                           "travamento das terças; a cobertura permanente informada é só a telha." % (fmt(et, 2), linhas, fmt(vmax, 2)))
    if d.viga_cobertura:
        esp = max(d.largura_de_influencia(i) for i in range(d.n_porticos))
        succao = succao_m2 * esp
        L = d.vao * 100.0
        g_cob = (d.cobertura_permanente + cv.get("cp_tercas", 0.0)) * esp
        casos = []
        for (bf, hf, bw, h0) in d.secoes_viga_cobertura:
            caso = VG.CasoViga("VCO", "viga de cobertura", d.vao, d.vao, g_cob, d.sobrecarga * esp, psi,
                               succao, 250.0, "NBR 9062, Tabela 8", "sem recorte", quantidade=d.n_porticos)
            if d.uma_agua:
                casos.append((caso, (lambda bf, hf, bw, h0: lambda x: VG.secao_I(bf, hf, bw, h0))(bf, hf, bw, h0)))
            else:
                casos.append((caso, (lambda bf, hf, bw, h0: lambda x: VG.secao_I(bf, hf, bw, h0 + min(x, L - x) * math.tan(th)))(bf, hf, bw, h0)))
        v = PR.dimensionar(casos[0][0], casos, meio, base_pr) if d.viga_cobertura_protendida else _escolher(casos, meio)
        v.quantidade = d.n_porticos
        p.vigas.append(v)
        cv["pp_cob"] = v.peso_kN / 2.0
        if not v.ok:
            p.avisos.append("viga de cobertura: nenhuma das seções candidatas passa — aumente as seções")
    p.cargas_vigas = cv


def _momentos_totais(d: DadosGalpaoPM, conc: Concreto, aco, pil: PilarDimensionado, s: dict) -> Tuple[float, float]:
    """(Mx, My) na base com a 2ª ordem do pilar (o que o cálice e a fundação recebem — NBR 9062, 7.7.1.1)"""
    H = d.altura_tipo(pil.tipo) * 100.0
    le = 2.0 * H
    d_linha = cobrimento(d.caa, "pilar", pre_fabricado=True) + 0.63 + 1.0
    r = N6118.pilar(pil.b, pil.h, pil.armadura, d_linha, H, le, le, max(s["Nd"], 1.0), s["Mx"], s["My"],
                    s["abx"], s["aby"], conc, aco, Nsg=max(s["Nsg"], 1.0), phi=d.phi_fluencia, elemento="Pilar")
    out = []
    for eixo, M1 in (("x", s["Mx"]), ("y", s["My"])):
        dd = r.dados.get(eixo) or {}
        out.append(max(M1, dd.get("Mtot") or dd.get("M1") or 0.0))
    return out[0], out[1]


def _fundacoes(d: DadosGalpaoPM, p: ProjetoGalpaoPM, conc: Concreto, aco) -> None:
    """a sapata ou o bloco sob o cálice de cada tipo de pilar: o solo e as estacas com as combinações
    características; a estrutura com as situações últimas do pilar e a 2ª ordem"""
    if d.fundacao == "nenhuma":
        return
    par = F.ParametrosFundacao(tipo=d.fundacao, sigma_adm=d.sigma_adm, fracao_comprimida=d.fracao_comprimida, peso_solo=d.peso_solo,
                               cobrimento=cobrimento(d.caa, "fundacao"), estaca_diametro=d.estaca_diametro, estaca_carga=d.estaca_carga,
                               estaca_tracao=d.estaca_tracao, estaca_espacamento=d.estaca_espacamento)
    comb_k = combinacoes_caracteristicas(_ventos(p.vento), _ponte(d))
    for pil in p.pilares:
        cal = next((r for r in p.calices if r.dados.get("direcao") == "x" and r.dados.get("tipo_pilar") == pil.tipo), None)
        if cal is None:
            continue
        ext_b, ext_h = cal.dados["externo"]
        int_b, int_h = cal.dados["interno"]
        Lemb = cal.dados["Lemb_adotado"]
        peso_col = PESO_CONCRETO * (ext_b * ext_h - int_b * int_h) * Lemb / 1e6
        sits_d, amp = [], [1.0, 1.0]
        for s in pil.esforcos.get("situacoes") or []:
            Mh, Mb = _momentos_totais(d, conc, aco, pil, s)
            if s["Mx"] > 1.0:
                amp[0] = max(amp[0], Mh / s["Mx"])
            if s["My"] > 1.0:
                amp[1] = max(amp[1], Mb / s["My"])
            sits_d.append(F.Situacao("%s (pórtico %d)" % (s["comb"], s["portico"]), s["Nd"], Mh, Mb, s["Vx"], s["Vy"]))
        sk = (pil.esforcos.get("caracteristicas") or []) if pil.tipo == "oitão" else             _situacoes(d, conc, p.vento, pil.b, pil.h, p.cargas_vigas, comb=comb_k)[pil.tipo]
        sits_k = [F.Situacao("%s (pórtico %d)" % (s["comb"], s["portico"]), s["Nd"], s["Mx"] * amp[0], s["My"] * amp[1], s["Vx"], s["Vy"])
                  for s in sk]
        nome = "%s do pilar %s" % ("Sapata" if d.fundacao == "sapata" else "Bloco sobre estacas", pil.tipo)
        fun = F.sapata if d.fundacao == "sapata" else F.bloco
        r = fun(ext_b, ext_h, Lemb, pil.b, pil.h, sits_k, sits_d, conc, aco, par, elemento=nome, peso_colarinho=peso_col)
        r.dados["tipo_pilar"] = pil.tipo
        r.dados["quantidade"] = pil.quantidade
        r.dados["Lemb"] = Lemb
        r.hipotese("segunda_ordem", "Momentos na base com a 2ª ordem do pilar (NBR 9062, 7.7.1.1); nas combinações características, "
                   "o acréscimo de 2ª ordem da ELU (× %s no vão, × %s no comprimento)." % (fmt(amp[0], 2), fmt(amp[1], 2)), "rotina")
        p.fundacoes.append(r)


#: NBR 6118, Tabela 23.2 — Δfsd,fad (MPa) para 2·10⁶ ciclos: barras retas e o tirante com barra transversal soldada
DELTA_F_FADIGA = {"reta": {10.0: 190, 12.5: 190, 16.0: 190, 20.0: 185, 25.0: 175, 32.0: 165}, "soldada": 85}


def _consolo_ponte(d: DadosGalpaoPM, p: ProjetoGalpaoPM, conc: Concreto, aco) -> None:
    """o consolo que recebe a viga de rolamento (NBR 9062, 7.3): o maior fator de rodas do tipo de pilar,
    a força transversal da ponte somada ao atrito do apoio (7.3.1.5 e 7.3.9) e a fadiga obrigatória
    (7.3.1.3): a variação de tensão no tirante (NBR 6118, 23.5.5, barra soldada) e a compressão na biela
    (23.5.4.1) na combinação frequente com ψ1 = 1,0 (23.5.2)"""
    if not d.ponte_rolante:
        return
    fyd = min(aco.fyd, 43.5)
    g_pr = cargas.GAMA_Q["ponte rolante"][0]
    imp = 1.0 + d.pr_impacto
    for pil in p.pilares:
        if pil.tipo == "oitão":
            continue
        idx = [i for i in range(d.n_porticos) if (i in (0, d.n_porticos - 1)) == pil.tipo.startswith("canto")]
        if not idx:
            continue
        k = max(fator_rodas(d, i) for i in idx)
        esp = max(d.largura_de_influencia(i) for i in idx)
        a = d.pr_excentricidade - pil.h / 2.0
        if a <= 0:
            p.erros.append("ponte rolante: o trilho (%s cm do eixo) fica sobre o pilar %s (h = %s cm) — aumente a excentricidade"
                           % (fmt(d.pr_excentricidade, 0), pil.tipo, fmt(pil.h, 0)))
            continue
        Q = d.pr_roda_max * imp * k                          # kN, a roda com o impacto e a linha de influência
        G_ = d.pr_viga_peso * esp
        Fd = 1.4 * G_ + g_pr * Q
        Ht = d.pr_transversal / int(d.pr_rodas) * k
        Hd = g_pr * Ht + N9062.HD_FD["chapas não soldadas"] * Fd
        r = N9062.consolo(pil.b, d.consolo_pr_altura, a, Fd, conc, aco, Hd=Hd, apoio="ponte rolante", pre_fabricado=d.pre_fabricado,
                          elemento="Consolo da ponte rolante — pilar %s" % pil.tipo)
        r.carga("Reação da viga de rolamento", "F<sub>d</sub> = 1,4·g·ℓ + %s·(1 + φ)·P<sub>máx</sub>·Ση" % fmt(g_pr, 1),
                "g = %s kN/m, ℓ = %s m, φ = %s, P = %s kN, Ση = %s" % (fmt(d.pr_viga_peso, 1), fmt(esp, 2), fmt(d.pr_impacto, 2),
                                                                      fmt(d.pr_roda_max, 1), fmt(k, 3)), fmt(Fd, 1, "kN"), "NBR 8681 e NBR 8800, Tabela 1")
        r.carga("Força horizontal", "H<sub>d</sub> = %s·H<sub>t</sub>·Ση + 0,25·F<sub>d</sub>" % fmt(g_pr, 1),
                "H<sub>t</sub> = %s kN por roda" % fmt(d.pr_transversal / int(d.pr_rodas), 1), fmt(Hd, 1, "kN"), "NBR 9062, 7.3.1.5 e 7.3.9 e)")
        # fadiga (7.3.1.3 → NBR 6118, 23.5): a variação é a própria ponte (entra e sai), com γf = 1,0 e ψ1 = 1,0
        dd = r.dados
        n_t, fi_t = dd["barras"]
        As_ef = n_t * BITOLAS[fi_t][0]
        ad = dd["a_d"]
        if ad <= 1.0:
            dT = (0.1 + ad) * Q + Ht if ad > 0.5 else 0.8 * Q / 1.4 + Ht
        else:
            dT = Q * a / (0.9 * dd["d"]) + Ht
        dfad = DELTA_F_FADIGA["soldada"] / 10.0                # kN/cm²
        As_fad = dT / dfad
        vf = Verificacao("Consolo da ponte — fadiga do tirante", norma="NBR 9062, 7.3.1.3 e NBR 6118, 23.5.5", Sd=dT / As_ef * 10,
                         Rd=DELTA_F_FADIGA["soldada"], unidade="MPa")
        vf.passo("Variação da força no tirante (combinação frequente, ψ<sub>1</sub> = 1,0, γ<sub>f</sub> = 1,0)",
                 "ΔT = (0,1 + a/d)·ΔF + ΔH", "ΔF = %s kN, ΔH = %s kN" % (fmt(Q, 1), fmt(Ht, 1)), fmt(dT, 1, "kN"), "NBR 6118, 23.5.2 e 23.5.3")
        vf.passo("Variação de tensão", "Δσ<sub>s</sub> = ΔT/A<sub>s,tir</sub>", "%s / %s" % (fmt(dT, 1), fmt(As_ef, 2)),
                 fmt(dT / As_ef * 10, 0, "MPa"), "")
        vf.passo("Limite (barra com solda — o tirante ancorado por barra transversal soldada, 7.3.3)", "Δf<sub>sd,fad</sub>", "",
                 "%d MPa" % DELTA_F_FADIGA["soldada"], "NBR 6118, Tabela 23.2")
        if As_ef < As_fad:
            n2, fi2 = N9062._barras(As_fad, (12.5, 16.0, 20.0, 25.0), n_min=2)
            As2 = n2 * BITOLAS[fi2][0]
            vf.Sd = dT / As2 * 10
            vf.passo("Tirante aumentado para a fadiga", "A<sub>s</sub> ≥ ΔT/Δf<sub>sd,fad</sub>", "%s / %s" % (fmt(dT, 1), fmt(dfad, 2)),
                     "%d ø%s (%s cm²)" % (n2, fmt(fi2, 1), fmt(As2, 2)), "")
            dd["barras"] = (n2, fi2)
            dd["As_tir"] = As2
        r.add(vf)
        # a biela na fadiga: a tensão máxima da combinação frequente (a ponte com ψ1 = 1,0) ≤ 0,45·fcd
        if 0.5 < ad <= 1.0:
            th = math.atan(0.9 * dd["d"] / a)
            F_freq = G_ + Q
            sig = F_freq / math.sin(th) / (pil.b * 0.2 * dd["d"] * math.cos(th))
            vb = Verificacao("Consolo da ponte — fadiga do concreto na biela", norma="NBR 6118, 23.5.4.1", Sd=sig * 10, Rd=0.45 * conc.fcd * 10,
                             unidade="MPa")
            vb.passo("Compressão na biela (combinação frequente, η<sub>c</sub> = 1 a favor da segurança)",
                     "σ<sub>c,máx</sub> ≤ f<sub>cd,fad</sub> = 0,45·f<sub>cd</sub>", "F = %s kN" % fmt(F_freq, 1), fmt(sig * 10, 2, "MPa"), "NBR 6118, 23.5.4.1")
            r.add(vb)
        r.hipotese("torcao", "A frenagem da ponte (%s kN por lado) no topo do trilho torce o consolo fora do seu plano (NBR 9062, 7.3.1.8 b): "
                   "conferir no detalhamento." % fmt(d.pr_longitudinal, 1), "rotina")
        r.dados["tipo_pilar"] = pil.tipo
        r.dados["ponte"] = True
        p.ligacoes.append(r)


def _deslocamento_ponte(d: DadosGalpaoPM, p: ProjetoGalpaoPM, conc: Concreto) -> None:
    """ELS com ponte rolante: o deslocamento horizontal na altura da viga de rolamento ≤ H/400, H = a altura
    da viga de rolamento (NBR 9062, Tabela 7, nota a), nas combinações frequentes (ψ1 do vento 0,3 com a ponte
    em ψ2; a ponte em ψ1 = 0,6 com o vento em ψ2 = 0)"""
    if not d.ponte_rolante or not p.pilares:
        return
    psi1_v = cargas.PSI["vento"][1]
    psi1_pr, psi2_pr = PSI_PONTE_PILAR[1], PSI_PONTE_PILAR[2]
    pil = min(p.pilares, key=lambda q: q.b * q.h)
    Hr = d.pr_altura * 100.0
    pior = None
    for i in range(d.n_porticos):
        m, casos_v = _modelo_portico(d, d.largura_de_influencia(i), pil.b, pil.h, conc, p.vento, p.cargas_vigas, fator_rodas(d, i))
        uv = {c: analise.resolver(m, c, 5) for c in casos_v + PONTE_CASOS}
        u = {c: max(abs(r.deslocamento("Cesq")[0]), abs(r.deslocamento("Cdir")[0])) for c, r in uv.items()}
        for cv in casos_v:
            for cp in PONTE_CASOS:
                ux = max(abs(psi1_v * uv[cv].deslocamento(n)[0] + psi2_pr * uv[cp].deslocamento(n)[0]) for n in ("Cesq", "Cdir"))
                if pior is None or ux > pior[0]:
                    pior = (ux, "%s (ψ1) + %s (ψ2)" % (cv, cp), i + 1)
        for cp in PONTE_CASOS:
            if pior is None or psi1_pr * u[cp] > pior[0]:
                pior = (psi1_pr * u[cp], "%s (ψ1)" % cp, i + 1)
    ux, nome, porti = pior
    lim = Hr / 400.0
    v = Verificacao("Deslocamento horizontal na viga de rolamento (ELS, combinação frequente)", norma="NBR 9062, 5.4.3 (Tabela 7, nota a)",
                    Sd=ux, Rd=lim, unidade="cm")
    v.passo("Combinação que governa — pórtico %d" % porti, nome, "ψ<sub>1</sub> vento %s; ponte ψ<sub>1</sub> %s, ψ<sub>2</sub> %s" % (
        fmt(psi1_v, 1), fmt(psi1_pr, 1), fmt(psi2_pr, 1)), fmt(ux, 2, "cm"), "NBR 8800, Tabela 2")
    v.passo("Limite", "H/400, H = altura da viga de rolamento", "%s / 400" % fmt(Hr, 0), fmt(lim, 2, "cm"), "NBR 9062, Tabela 7")
    v.observacao = "rigidez bruta E<sub>cs</sub>·I<sub>c</sub> (estádio I) — com o pilar fissurado o deslocamento cresce: conferir"
    r = Resultado("Estrutura — deslocamento na viga de rolamento", perfil="pilar %s × %s" % (fmt(pil.b, 0), fmt(pil.h, 0)), material=conc.nome)
    r.add(v)
    p.icamento.append(r)


#: a marca de cada tipo de pilar
SUFIXO = {"canto": "C", "intermediário": "I", "oitão": "O", "canto B": "CB", "intermediário B": "IB"}


def _pilares_oitao(d: DadosGalpaoPM, p: ProjetoGalpaoPM, conc: Concreto, aco, c_nom: float) -> None:
    """os pilares de oitão: em balanço, engastados no cálice e com o topo livre (a favor da segurança); o vento
    do oitão na faixa de parede de cada um (metade da distância aos vizinhos da mesma linha, as filas incluídas)
    e a cobertura na faixa até o meio do primeiro vão; um tipo só, pela faixa maior"""
    if not d.pilares_oitao:
        return
    n_ult = d.n_porticos
    por_eixo: Dict[int, List[float]] = {}
    for eixo, y in d.pilares_oitao:
        eixo = int(eixo)
        if eixo not in (1, n_ult) or not (0.0 < float(y) < d.vao):
            p.avisos.append("pilar de oitão (%s; %s m) fora de um oitão ou fora do vão: ficou de fora" % (eixo, fmt(float(y), 2)))
            continue
        por_eixo.setdefault(eixo, []).append(float(y))
    if not por_eixo:
        return
    w = 0.0
    for eixo, ys in por_eixo.items():
        linha = sorted([0.0, d.vao] + ys)
        for y in ys:
            i = linha.index(y)
            w = max(w, (linha[i + 1] - linha[i - 1]) / 2.0)
    L1 = max(d.vaos_longitudinais[0], d.vaos_longitudinais[-1])
    lon = [c for c in p.vento["casos"].values() if c["direcao"] == "longitudinal"]
    p_oit = max((max(abs(c["oitao_barlavento"]), abs(c["oitao_sotavento"])) for c in lon), default=0.0)
    H = max(d.altura_oitao(y) for ys in por_eixo.values() for y in ys)
    q = p_oit * w                                          # kN/m
    Mw = q * H * H / 2.0 * 100.0                           # kN·cm na base
    Vw = q * H
    area = w * L1 / 2.0
    Ng, Nq = (d.cobertura_permanente + p.cargas_vigas.get("cp_tercas", 0.0)) * area, d.sobrecarga * area
    gpp = cargas.GAMA_G["pré-moldada"][0]
    psi_sc, psi_v = cargas.PSI["cobertura"][0], cargas.PSI["vento"][0]
    psi2 = cargas.PSI["cobertura"][2]
    escolhido = None
    for (b, h) in sorted(d.secoes_pilar, key=lambda s_: (s_[0] * s_[1], s_[1])):
        if 2.0 * H * 100.0 * math.sqrt(12.0) / min(b, h) > 140.0:
            continue
        Npp = PESO_CONCRETO * b * h / 1e4 * H
        base = {"Mx": 0.0, "abx": 1.0, "aby": 0.85, "Vx": 0.0, "Vy": 0.0, "Htopo": 0.0, "portico": min(por_eixo), "pilar": "oitão",
                "Nsg": Npp + Ng + psi2 * Nq}
        sits = [dict(base, Nd=gpp * Npp + 1.4 * Ng + 1.5 * psi_sc * Nq, My=1.4 * Mw, Vy=1.4 * Vw, comb="ELU vento no oitão + sobrecarga"),
                dict(base, Nd=gpp * Npp + 1.4 * Ng + 1.5 * Nq, My=1.4 * psi_v * Mw, Vy=1.4 * psi_v * Vw, comb="ELU sobrecarga + vento no oitão"),
                dict(base, Nd=Npp + Ng, My=1.4 * Mw, Vy=1.4 * Vw, comb="ELU vento no oitão (permanentes favoráveis)")]
        d_linha = c_nom + 0.63 + 1.0
        arm, r = N6118.armar_pilar(b, h, d_linha, lambda a: _verificar_pilar(d, conc, aco, b, h, d_linha, a, sits))
        if arm is not None and r is not None and r.ok:
            carac = [dict(base, Nd=Npp + Ng + psi_sc * Nq, My=Mw, Vy=Vw, comb="G + vento no oitão + ψ0·Q"),
                     dict(base, Nd=Npp + Ng + Nq, My=psi_v * Mw, Vy=psi_v * Vw, comb="G + Q + ψ0·vento no oitão"),
                     dict(base, Nd=Npp + Ng, My=Mw, Vy=Vw, comb="G + vento no oitão")]
            escolhido = PilarDimensionado("oitão", b, h, arm, r, N6118.estribos_pilar(arm), {"situacoes": sits, "caracteristicas": carac})
            break
    if escolhido is None:
        p.erros.append("pilar de oitão: nenhuma seção candidata passa — aumente as seções")
        return
    escolhido.quantidade = sum(len(v) for v in por_eixo.values())
    p.pilares.append(escolhido)
    p.hipoteses.append("Pilares de oitão (%d) em balanço, engastados no cálice e com o topo livre: o vento do oitão (%s kN/m²) na faixa "
                       "de %s m de parede e a cobertura na faixa até o meio do primeiro vão; um tipo só, pela faixa maior."
                       % (escolhido.quantidade, fmt(p_oit, 3), fmt(w, 2)))


def _consolos(d: DadosGalpaoPM, p: ProjetoGalpaoPM, conc: Concreto, aco) -> None:
    """o consolo de cada tipo de pilar que recebe a viga longitudinal (largura = h do pilar)"""
    vl = next((v for v in p.vigas if v.funcao != "viga de cobertura"), None)
    if vl is None:
        return
    Fd = vl.reacoes["Fd"]
    for pil in p.pilares:
        if pil.tipo == "oitão":
            continue
        r = N9062.consolo(pil.h, d.consolo_altura, d.consolo_a, Fd, conc, aco, apoio="elastômero", pre_fabricado=d.pre_fabricado,
                          elemento="Consolo do pilar %s (apoio da %s)" % (pil.tipo, vl.funcao))
        r.dados["por_pilar"] = 1 if pil.tipo.startswith("canto") else 2
        r.dados["tipo_pilar"] = pil.tipo
        r.hipotese("reacao", "Reação de cálculo da %s %s: F<sub>d</sub> = %s kN (a maior, no maior vão)." % (vl.funcao, vl.marca, fmt(Fd, 1)), "rotina")
        p.ligacoes.append(r)


def _calice_e_icamento(d: DadosGalpaoPM, p: ProjetoGalpaoPM, pil: PilarDimensionado, conc: Concreto, aco) -> None:
    """o cálice do pilar (as duas direções; fica o maior embutimento) e o içamento do pilar inteiro"""
    sits = pil.esforcos.get("situacoes") or []
    if not sits:
        return
    res = []
    for direcao, M_, V_, h_, b_ in (("x", "Mx", "Vx", pil.h, pil.b), ("y", "My", "Vy", pil.b, pil.h)):
        s = max(sits, key=lambda s_: s_[M_])
        r = N9062.calice(b_, h_, s["Nd"], s[M_], s.get(V_, 0.0), conc, aco, pil.armadura.bitola, d.interface_calice,
                         d.parede_calice, direcao=direcao, elemento="Cálice do pilar %s — direção %s" % (pil.tipo, direcao))
        r.dados["situacao"] = s
        r.dados["tipo_pilar"] = pil.tipo
        res.append(r)
    Lemb = max(r.dados["Lemb"] for r in res)
    for r in res:
        r.dados["Lemb_adotado"] = Lemb
        p.calices.append(r)
    pil.comprimento_total = d.altura_tipo(pil.tipo) + Lemb / 100.0
    # o cintamento do topo (6.2.3): a força horizontal que a cobertura aplica no topo do pilar
    s_h = max(sits, key=lambda s_: s_.get("Htopo", 0.0))
    Hd = s_h.get("Htopo", 0.0)
    gn = N9062.gama_n(d.pre_fabricado, False)
    As_c = gn * Hd / min(aco.fyd, 43.5)
    h1 = min(pil.b, pil.h)
    n_c, fi_c = N9062._barras(max(As_c, 0.01), (6.3, 8.0, 10.0), n_min=2)
    rc = Resultado("Cintamento do topo do pilar %s" % pil.tipo, perfil="%s × %s cm" % (fmt(pil.b, 0), fmt(pil.h, 0)), material=aco.nome)
    vc = Verificacao("Cintamento do topo — armadura horizontal", norma="NBR 9062, 6.2.3", Sd=As_c, Rd=n_c * BITOLAS[fi_c][0], unidade="cm²")
    vc.passo("Força horizontal no topo (%s, pórtico %d)" % (s_h["comb"], s_h["portico"]), "H<sub>d</sub>", "", fmt(Hd, 1, "kN"), "")
    vc.passo("Armadura de cintamento", "A<sub>s,cint</sub> = γ<sub>n</sub>·H<sub>d</sub>/f<sub>yd</sub>", "%s × %s / %s" % (fmt(gn, 1), fmt(Hd, 1), fmt(min(aco.fyd, 43.5), 2)),
             fmt(As_c, 2, "cm²"), "NBR 9062, 6.2.3 e 7.3.1.1")
    vc.passo("Distribuição", "em h<sub>1</sub> ≤ b, 2/3 no terço superior", "h<sub>1</sub> = %s cm" % fmt(h1, 0),
             "%d estribos ø%s (ramos horizontais)" % (max(n_c // 2, 2), fmt(fi_c, 1)), "NBR 9062, 6.2.3")
    rc.add(vc)
    rc.dados.update({"tipo_pilar": pil.tipo, "estribos": max(n_c // 2, 2), "bitola": fi_c, "h1": h1})
    p.icamento.append(rc)
    # içamento: deitado na face mais larga — a flexão na menor dimensão
    menor, maior = min(pil.b, pil.h), max(pil.b, pil.h)
    arm = pil.armadura if pil.b <= pil.h else pil.armadura.girada()
    As_face = (arm.n_b + 2) * BITOLAS[arm.bitola][0]
    d_linha = cobrimento(d.caa, "pilar", True) + 0.63 + arm.bitola / 20.0
    p.icamento.append(N9062.icamento_pilar(maior, menor, pil.comprimento_total * 100.0, As_face, menor - d_linha, conc, aco,
                                           elemento="Içamento do pilar %s" % pil.tipo))


def _deslocamento_topo(d: DadosGalpaoPM, p: ProjetoGalpaoPM, conc: Concreto) -> None:
    """ELS: o deslocamento horizontal do topo na combinação frequente (ψ1 do vento) ≤ H/400
    (NBR 9062, Tabela 7, galpão). Estádio I (Ecs·Ic) se o momento frequente não passa do de
    fissuração (NBR 6118, 17.3.1); senão 0,5·Ecs·Ic, a favor da segurança"""
    if not p.pilares:
        return
    psi1 = cargas.PSI["vento"][1]
    H = max(d.altura_pilar, d.altura_b) * 100.0
    pior = None
    pil = max(p.pilares, key=lambda q: q.b * q.h)
    for pil_ in p.pilares:
        if pil_.b * pil_.h < pil.b * pil.h:
            pil = pil_
    for i in range(d.n_porticos):
        esp = d.largura_de_influencia(i)
        m, casos_v = _modelo_portico(d, esp, pil.b, pil.h, conc, p.vento, p.cargas_vigas)
        for caso in casos_v:
            r = analise.resolver(m, caso, 11)
            # cada fila contra a sua altura: o deslocamento é comparado a H/400 pela fila mais crítica
            uA, uB = abs(r.deslocamento("Tesq")[0]), abs(r.deslocamento("Tdir")[0])
            u = max(uA, uB * d.altura_pilar / d.altura_b) if d.filas_diferentes else max(uA, uB)
            Mb = max(abs(r.barra("pilar_esq").esforcos(0.0)[2]), abs(r.barra("pilar_dir").esforcos(0.0)[2]))
            if pior is None or u > pior[0]:
                pior = (u, caso, i + 1, Mb)
    if pior is None:
        return
    u, caso, porti, Mb = pior
    Ic = pil.b * pil.h ** 3 / 12.0
    Mr = 1.5 * conc.fctm * Ic / (pil.h / 2)
    fator = 1.0 if psi1 * Mb <= Mr else 0.5
    u_f = psi1 * u / fator
    H = d.altura_pilar * 100.0                              # a fila A (a B já entrou proporcional)
    lim = H / 400.0
    v = Verificacao("Deslocamento horizontal do topo (ELS, combinação frequente)", norma="NBR 9062, 5.4.3 (Tabela 7)", Sd=u_f, Rd=lim, unidade="cm")
    v.passo("Rigidez do pilar", "E<sub>cs</sub>·I<sub>c</sub>" if fator == 1.0 else "0,5·E<sub>cs</sub>·I<sub>c</sub> (fissurado)",
            "M<sub>freq</sub> = %s kN·m; M<sub>r</sub> = %s kN·m" % (fmt(psi1 * Mb / 100, 1), fmt(Mr / 100, 1)), "", "NBR 6118, 17.3.1")
    v.passo("Deslocamento no topo — %s (pórtico %d)" % (caso, porti), "u = ψ<sub>1</sub>·u<sub>vento</sub>", "%s × %s" % (fmt(psi1, 1), fmt(u / fator, 2)),
            fmt(u_f, 2, "cm"), "NBR 8681")
    v.passo("Limite do galpão", "H/400", "%s / 400" % fmt(H, 0), fmt(lim, 2, "cm"), "NBR 9062, Tabela 7")
    r = Resultado("Estrutura — deslocamento horizontal", perfil="pilar %s × %s" % (fmt(pil.b, 0), fmt(pil.h, 0)), material=conc.nome)
    r.add(v)
    p.icamento.append(r)


def _lista(d: DadosGalpaoPM, p: ProjetoGalpaoPM) -> None:
    """a lista de peças: pilares (com o embutimento) e cálices — concreto, aço e peso de içamento"""
    n_cons = {r.dados.get("tipo_pilar"): r.dados.get("por_pilar", 0) for r in p.ligacoes if r.elemento.startswith("Consolo do pilar")}
    ponte = {r.dados.get("tipo_pilar") for r in p.ligacoes if r.dados.get("ponte")}
    for pil in p.pilares:
        arm = pil.armadura
        L = pil.comprimento_total
        vol = pil.b * pil.h / 1e4 * L
        kg_long = arm.n_total * BITOLAS[arm.bitola][1] * (L + 0.3)
        fi_t, s_t = pil.estribos
        perim = 2 * (pil.b + pil.h - 8 * cobrimento(d.caa, "pilar", True)) / 100.0 + 0.2
        kg_est = math.ceil(L * 100.0 / s_t) * perim * BITOLAS[fi_t][1]
        p.lista.append({"marca": "P-%s" % SUFIXO[pil.tipo],
                        "descricao": "Pilar %s %s × %s cm%s" % (pil.tipo, fmt(pil.b, 0), fmt(pil.h, 0),
                                                                 (" com %d consolo%s" % (n_cons[pil.tipo], "s" if n_cons[pil.tipo] > 1 else "")
                                                                  if n_cons.get(pil.tipo) else "")
                                                                 + (" e consolo da ponte rolante" if pil.tipo in ponte else "")),
                        "quantidade": pil.quantidade, "comprimento_m": round(L, 2), "volume_m3": round(vol, 3),
                        "peso_kN": round(vol * PESO_CONCRETO, 1), "aco_kg": round(kg_long + kg_est, 1),
                        "armadura": "%s + estribos ø%s c/ %s" % (arm.texto(), fmt(fi_t, 1), fmt(s_t, 1)),
                        "taxa_kg_m3": round((kg_long + kg_est) / vol, 0)})
    for r in p.calices:
        if r.dados.get("direcao") != "x":
            continue
        e = r.dados["externo"]
        H_c = r.dados["Lemb_adotado"] + (0.0 if p.fundacoes else r.dados["fundo"])
        vol = e[0] * e[1] / 1e4 * H_c / 100.0 - r.dados["interno"][0] * r.dados["interno"][1] / 1e4 * r.dados["Lemb_adotado"] / 100.0
        tipo = r.dados.get("tipo_pilar") or next(t for t in ("canto", "oitão", "intermediário") if t in r.elemento)
        qtd = next((q.quantidade for q in p.pilares if q.tipo == tipo), 0)
        p.lista.append({"marca": "CL-%s" % SUFIXO[tipo],
                        "descricao": "Cálice (colarinho) %s × %s cm, altura %s cm" % (fmt(e[0], 0), fmt(e[1], 0), fmt(H_c, 0)),
                        "quantidade": qtd, "comprimento_m": round(H_c / 100.0, 2), "volume_m3": round(vol, 3),
                        "peso_kN": None, "aco_kg": None, "armadura": "ver memória do cálice", "taxa_kg_m3": None})
    _lista_vigas(d, p)
    _lista_fundacoes(d, p)


def _lista_fundacoes(d: DadosGalpaoPM, p: ProjetoGalpaoPM) -> None:
    for r in p.fundacoes:
        dd = r.dados
        if "ah" not in dd:
            continue
        tipo = dd["tipo_pilar"]
        suf = SUFIXO[tipo]
        if dd["tipo"] == "sapata":
            p.lista.append({"marca": "SP-%s" % suf, "descricao": "Sapata %s × %s × %s cm (moldada no local)" % (
                fmt(dd["ah"], 0), fmt(dd["ab"], 0), fmt(dd["hf"], 0)), "quantidade": dd["quantidade"], "comprimento_m": round(dd["ah"] / 100.0, 2),
                "volume_m3": round(dd["volume"], 3), "peso_kN": None, "aco_kg": round(dd["aco_kg"], 1), "armadura": dd["armadura"],
                "taxa_kg_m3": round(dd["aco_kg"] / dd["volume"], 0)})
        else:
            p.lista.append({"marca": "BL-%s" % suf, "descricao": "Bloco %s × %s × %s cm sobre %d estacas (moldado no local)" % (
                fmt(dd["ah"], 0), fmt(dd["ab"], 0), fmt(dd["hf"], 0), dd["n_estacas"]), "quantidade": dd["quantidade"],
                "comprimento_m": round(dd["ah"] / 100.0, 2), "volume_m3": round(dd["volume"], 3), "peso_kN": None, "aco_kg": None,
                "armadura": dd["armadura"], "taxa_kg_m3": None})
            p.lista.append({"marca": "EST-%s" % suf, "descricao": "Estaca ø%s cm (comprimento pela sondagem)" % fmt(dd["estaca_diametro"], 0),
                            "quantidade": dd["n_estacas"] * dd["quantidade"], "comprimento_m": 0.0, "volume_m3": 0.0, "peso_kN": None,
                            "aco_kg": None, "armadura": "—", "taxa_kg_m3": None})


def _lista_vigas(d: DadosGalpaoPM, p: ProjetoGalpaoPM) -> None:
    """as vigas por comprimento de peça (as longitudinais entre as faces dos pilares, com 1 cm de folga
    em cada ponta; a de cobertura até as faces externas dos pilares), os aparelhos de apoio e os chumbadores"""
    b_pil = max((q.b for q in p.pilares), default=0.0) / 100.0
    h_pil = max((q.h for q in p.pilares), default=0.0) / 100.0
    for v in p.vigas:
        if v.funcao == "viga de cobertura":
            pecas = [(d.vao + h_pil, d.n_porticos)]
        else:
            por_vao: Dict[float, int] = {}
            por_linha = p.cargas_vigas.get("tercas_linhas", 0) if v.funcao == "terça" else 2
            for vao in d.vaos_longitudinais:
                # as terças de ponta a ponta entre os eixos das vigas de cobertura (1 cm de folga); as longitudinais entre faces
                comp = (math.floor((vao - 0.02) * 100.0 + 1e-6) if v.funcao == "terça" else
                        math.floor((vao - b_pil - 0.02) * 100.0 + 1e-6)) / 100.0
                por_vao[comp] = por_vao.get(comp, 0) + por_linha
            pecas = sorted(por_vao.items(), reverse=True)
        vol_m = v.volume / max(v.comprimento, 1e-9)
        aco_m = v.aco_kg / max(v.comprimento, 1e-9)
        for k, (comp, qtd) in enumerate(pecas):
            vol = vol_m * comp
            p.lista.append({"marca": "%s-%d" % (v.marca, k + 1) if len(pecas) > 1 else v.marca,
                            "descricao": "%s %s%s" % (v.funcao.capitalize(), v.secao.texto(), "" if v.secao is v.secao_apoio or
                                                         abs(v.secao.h - v.secao_apoio.h) < 0.5 else ", altura %s no apoio" % fmt(v.secao_apoio.h, 0)),
                            "quantidade": qtd, "comprimento_m": round(comp, 2), "volume_m3": round(vol, 3),
                            "peso_kN": round(vol * PESO_CONCRETO, 1), "aco_kg": round(aco_m * comp, 1),
                            "armadura": v.texto_armadura(), "taxa_kg_m3": round(aco_m / max(vol_m, 1e-9), 0)})
        el = v.elastomero
        if el is not None:
            n_ap = 2 * sum(q for _c, q in pecas)
            pino = el.dados.get("chumbador")
            p.lista.append({"marca": "EL-%s" % v.marca, "descricao": "Aparelho de apoio de elastômero %s%s" % (
                el.perfil, " + chumbador ø%s" % fmt(pino, 1) if pino else ""), "quantidade": n_ap, "comprimento_m": 0.0,
                "volume_m3": 0.0, "peso_kN": None, "aco_kg": None, "armadura": "—", "taxa_kg_m3": None})
