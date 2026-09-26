# -*- coding: utf-8 -*-
"""Estruturas comuns a todos os módulos de cálculo.

Toda verificação normativa devolve um objeto `Verificacao`, que carrega o valor
solicitante, o resistente e a memória de cálculo passo a passo. O memorial em PDF
é gerado a partir dessas memórias, de modo que o documento nunca diverge do que
foi efetivamente calculado.

Unidades adotadas em todo o sistema:
    força      kN
    momento    kN·cm  (kN·m apenas na interface com o usuário)
    tensão     kN/cm²  (1 kN/cm² = 10 MPa)
    dimensão   cm      (mm apenas na interface e nos desenhos)
"""
from dataclasses import dataclass, field
from typing import List, Optional

# --- constantes do aço (NBR 8800:2008, item 4.5) ---
E = 20000.0        # módulo de elasticidade, kN/cm²
G = 7700.0         # módulo de elasticidade transversal, kN/cm²
NU = 0.3           # coeficiente de Poisson
RHO = 7850.0       # massa específica, kg/m³
ALFA = 1.2e-5      # coeficiente de dilatação térmica, 1/°C

# --- coeficientes de ponderação das resistências (NBR 8800, Tabela 3) ---
GAMA_A1 = 1.10     # escoamento, flambagem e instabilidade
GAMA_A2 = 1.35     # ruptura
GAMA_W2 = 1.35     # metal da solda
GAMA_C = 1.40      # concreto


@dataclass
class Passo:
    """Uma linha da memória de cálculo."""
    texto: str                 # o que está sendo feito
    formula: str = ""          # expressão simbólica, em HTML
    conta: str = ""            # a mesma expressão com os números substituídos
    valor: str = ""            # resultado formatado com unidade
    norma: str = ""            # item da norma que justifica o passo


#: De onde veio uma hipótese: o profissional confere primeiro o que foi medido e o que foi
#: adotado; o que veio da norma ou do catálogo ele só confirma.
FONTES_DE_HIPOTESE = {
    "modelo": "medido no modelo 3D",
    "parametro": "informado no diálogo do cálculo",
    "rotina": "adotado pela rotina de cálculo",
    "norma": "exigido pela norma",
    "catalogo": "do catálogo de perfis e aços",
}


@dataclass
class Hipotese:
    """Uma decisão tomada antes da conta — o que o memorial escreve por extenso.

    `chave` identifica o assunto (vao, largura, correntes, succao_travamento…) e é por ela
    que a explicação didática é encontrada; `texto` é a hipótese em linguagem comum, com
    os números; `fonte` é uma das `FONTES_DE_HIPOTESE`."""
    chave: str
    texto: str
    fonte: str = "rotina"


@dataclass
class Verificacao:
    """Resultado de uma verificação de estado-limite."""
    titulo: str
    norma: str = ""
    Sd: float = 0.0            # solicitante de cálculo
    Rd: float = 0.0            # resistente de cálculo
    unidade: str = "kN"
    passos: List[Passo] = field(default_factory=list)
    observacao: str = ""
    dispensada: bool = False   # verificação que não se aplica ao caso
    #: faltou dado para verificar (perfil sem propriedade, geometria que não fecha): não é
    #: aprovada — antes saía Sd = 0 / Rd = 1, verde no mapa e "o mais leve que passa"
    indeterminada: bool = False

    def passo(self, texto, formula="", conta="", valor="", norma=""):
        self.passos.append(Passo(texto, formula, conta, valor, norma))
        return self

    @property
    def razao(self) -> float:
        """Sd/Rd — o quanto da capacidade foi usado."""
        if self.dispensada:
            return 0.0
        if self.Rd == 0:
            return float("inf") if self.Sd > 0 else 0.0
        return abs(self.Sd) / abs(self.Rd)

    @property
    def ok(self) -> bool:
        if self.indeterminada:
            return False
        return self.dispensada or self.razao <= 1.0001

    @property
    def folga(self) -> float:
        """Margem percentual sobrando (negativa quando reprova)."""
        return (1.0 - self.razao) * 100.0

    def resumo(self) -> str:
        if self.dispensada:
            return f"{self.titulo}: não se aplica"
        if self.indeterminada:
            return f"{self.titulo}: indeterminada ({self.observacao})"
        s = "OK" if self.ok else "NÃO PASSA"
        return (f"{self.titulo}: {self.Sd:,.1f} / {self.Rd:,.1f} {self.unidade} "
                f"= {self.razao:.2f} {s}").replace(",", " ")


def nao_verificada(motivo) -> Verificacao:
    """A verificação que não se fez por falta de dado: conta como não aprovada."""
    v = Verificacao("Não verificada", Sd=0.0, Rd=1.0, unidade="—", indeterminada=True)
    v.observacao = str(motivo)
    return v


@dataclass
class Resultado:
    """Conjunto de verificações de um elemento (pilar, viga, terça, ligação...)."""
    elemento: str
    perfil: str = ""
    material: str = ""
    verificacoes: List[Verificacao] = field(default_factory=list)
    dados: dict = field(default_factory=dict)
    #: as decisões anteriores à conta (vão, travamentos, cargas e de onde vieram), na
    #: ordem em que o profissional confere: primeiro o modelo, depois a rotina
    hipoteses: List[Hipotese] = field(default_factory=list)
    #: como a carga chegou à peça e virou esforço: passos como os das verificações
    cargas: List[Passo] = field(default_factory=list)

    def add(self, v: Optional[Verificacao]):
        if v is not None:
            self.verificacoes.append(v)
        return v

    def hipotese(self, chave: str, texto: str, fonte: str = "rotina"):
        self.hipoteses.append(Hipotese(chave, texto, fonte))
        return self

    def carga(self, texto, formula="", conta="", valor="", norma=""):
        self.cargas.append(Passo(texto, formula, conta, valor, norma))
        return self

    @property
    def razao(self) -> float:
        vs = [v.razao for v in self.verificacoes if not v.dispensada]
        return max(vs) if vs else 0.0

    @property
    def ok(self) -> bool:
        return all(v.ok for v in self.verificacoes)

    @property
    def indeterminada(self) -> bool:
        return any(v.indeterminada for v in self.verificacoes)

    @property
    def critica(self) -> Optional[Verificacao]:
        """A verificação que governa o dimensionamento."""
        vs = [v for v in self.verificacoes if not v.dispensada]
        return max(vs, key=lambda v: v.razao) if vs else None

    def resumo(self) -> str:
        c = self.critica
        s = "OK" if self.ok else "NÃO PASSA"
        gov = f" (governa: {c.titulo})" if c else ""
        return f"{self.elemento} {self.perfil}: {self.razao:.2f} {s}{gov}"


class ErroDeDados(ValueError):
    """Entrada inconsistente informada pelo usuário."""


def fmt(x, casas=2, unidade=""):
    """Número no padrão brasileiro, para a memória de cálculo."""
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    if abs(x) >= 1e5 or (x != 0 and abs(x) < 1e-3):
        s = f"{x:.{casas}e}"
    else:
        s = f"{x:,.{casas}f}".replace(",", " ").replace(".", ",")
    return f"{s} {unidade}".strip()
