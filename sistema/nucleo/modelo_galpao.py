# -*- coding: utf-8 -*-
"""Contrato de dados do galpão: o que entra e o que sai do dimensionamento.

`DadosGalpao` é o que o usuário preenche na interface.
`ProjetoGalpao` é o resultado completo, consumido pelo memorial, pelos desenhos e pela
lista de material. Nenhum módulo de saída calcula nada: tudo que eles imprimem ou
desenham já está aqui.

Unidades deste contrato: metros e kN na entrada do usuário; os módulos de cálculo
convertem para cm e kN internamente. Os campos que fogem disso trazem a unidade no nome.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .base import Resultado, ErroDeDados


# ---------------------------------------------------------------- entrada

@dataclass
class DadosGalpao:
    """Tudo que o usuário informa para dimensionar um galpão de duas águas."""
    # identificação
    nome: str = "Galpão"
    cliente: str = ""
    local: str = ""
    responsavel: str = ""

    # geometria (m)
    vao: float = 20.0                    # vão livre entre eixos de pilares
    comprimento: float = 40.0            # comprimento total
    pe_direito: float = 6.0              # do piso ao nível do joelho
    espacamento_porticos: float = 5.0    # distância entre pórticos
    inclinacao: float = 10.0             # inclinação do telhado, em %
    balanco_lateral: float = 0.0         # beiral além do pilar, cada lado

    # sistema
    tipo_portico: str = "alma cheia"     # "alma cheia" ou "treliçado"
    base_rotulada: bool = True
    com_misula: bool = True
    comprimento_misula: float = 1.8      # m, medido ao longo da viga
    altura_misula: float = 0.0           # 0 = automática (altura da viga)

    # materiais
    aco_perfis: str = "ASTM A572 Gr.50"
    aco_tercas: str = "CF-26 (NBR 6650)"
    aco_chapas: str = "ASTM A36"
    parafuso: str = "ASTM A325"
    eletrodo: str = "E70XX"
    fck_MPa: float = 25.0

    # cobertura e fechamento
    telha: str = "trapezoidal 0,50 mm"
    espacamento_tercas: float = 1.6      # m (alvo; o sistema ajusta para caber no vão)
    linhas_correntes: int = 1            # linhas de tirantes por água
    fechamento_lateral: str = "telha metálica"
    altura_fechamento: float = 0.0       # 0 = até o pé-direito

    # cargas
    sobrecarga_cobertura: float = 0.25   # kN/m²
    carga_forro: float = 0.0             # kN/m²
    carga_extra: float = 0.0             # kN/m² (equipamentos, iluminação)
    ponte_rolante: bool = False
    capacidade_ponte_t: float = 0.0

    # vento (NBR 6123)
    cidade: str = ""
    v0: float = 40.0                     # m/s
    categoria_rugosidade: str = "II"
    classe: str = "B"
    fator_topografico: float = 1.0       # S1
    fator_estatistico: float = 1.0       # S3
    aberturas: str = "duas faces opostas"

    # critérios de projeto
    flecha_terca: int = 180              # L/180
    flecha_viga: int = 250               # L/250
    desloc_horizontal: int = 300         # H/300
    custo_kg: float = 17.0               # R$/kg instalado, para a estimativa

    def validar(self):
        """Erros de entrada com mensagem em português e faixa aceitável."""
        def faixa(campo, valor, minimo, maximo, unidade=""):
            if valor is None or not (minimo <= valor <= maximo):
                raise ErroDeDados(
                    f"{campo}: valor {valor} fora da faixa aceitável "
                    f"({minimo} a {maximo} {unidade}).".replace("  ", " "))
        faixa("Vão", self.vao, 5, 60, "m")
        faixa("Comprimento", self.comprimento, 5, 300, "m")
        faixa("Pé-direito", self.pe_direito, 2.5, 20, "m")
        faixa("Espaçamento entre pórticos", self.espacamento_porticos, 3, 12, "m")
        faixa("Inclinação do telhado", self.inclinacao, 2, 100, "%")
        faixa("Espaçamento de terças", self.espacamento_tercas, 0.8, 3.0, "m")
        faixa("Velocidade básica do vento", self.v0, 25, 55, "m/s")
        faixa("Sobrecarga de cobertura", self.sobrecarga_cobertura, 0, 5, "kN/m²")
        faixa("fck do concreto", self.fck_MPa, 15, 50, "MPa")
        faixa("Linhas de correntes", self.linhas_correntes, 0, 4, "")
        if self.categoria_rugosidade not in ("I", "II", "III", "IV", "V"):
            raise ErroDeDados("Categoria de rugosidade deve ser I, II, III, IV ou V.")
        if self.classe not in ("A", "B", "C"):
            raise ErroDeDados("Classe da edificação deve ser A, B ou C.")
        if self.comprimento < self.espacamento_porticos:
            raise ErroDeDados("O comprimento do galpão é menor que o espaçamento entre pórticos.")
        # O que o programa ainda não calcula é recusado, não ignorado: um memorial que
        # imprime "pórtico treliçado" com o cálculo de alma cheia seria um documento falso.
        if "alma" not in str(self.tipo_portico or "").lower():
            raise ErroDeDados("Pórtico \"%s\" ainda não é calculado por este programa: só o pórtico de "
                              "alma cheia de duas águas. Escolha \"alma cheia\"." % self.tipo_portico)
        if self.ponte_rolante or (self.capacidade_ponte_t or 0) > 0:
            raise ErroDeDados("Ponte rolante ainda não entra no cálculo (cargas móveis, vigas de rolamento "
                              "e efeitos dinâmicos). Desmarque a ponte rolante ou dimensione o galpão "
                              "com ponte em outro programa.")
        return self

    # --- grandezas derivadas ---
    @property
    def angulo_telhado(self) -> float:
        """Ângulo do telhado em graus."""
        import math
        return math.degrees(math.atan(self.inclinacao / 100))

    @property
    def altura_cumeeira(self) -> float:
        """Altura total até a cumeeira, em m."""
        return self.pe_direito + (self.vao / 2) * (self.inclinacao / 100)

    @property
    def n_porticos(self) -> int:
        return int(round(self.comprimento / self.espacamento_porticos)) + 1

    @property
    def comprimento_agua(self) -> float:
        """Comprimento inclinado de uma água, em m."""
        import math
        return (self.vao / 2) / math.cos(math.radians(self.angulo_telhado))

    @property
    def area_coberta(self) -> float:
        return self.vao * self.comprimento

    def dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- saída

@dataclass
class Peca:
    """Uma peça da lista de material."""
    marca: str
    descricao: str
    perfil: str
    material: str
    quantidade: int
    comprimento_m: float
    peso_unit_kg: float = 0.0
    peso_total_kg: float = 0.0
    area_pintura_m2: float = 0.0
    observacao: str = ""


@dataclass
class ElementoDimensionado:
    """Um elemento estrutural já verificado."""
    nome: str                      # "Pilar", "Viga do pórtico", "Terça"...
    perfil: str
    material: str
    resultado: Optional[Resultado] = None
    esforcos: Dict[str, float] = field(default_factory=dict)
    geometria: Dict[str, float] = field(default_factory=dict)
    alternativas: List[dict] = field(default_factory=list)   # outros perfis testados

    @property
    def razao(self) -> float:
        return self.resultado.razao if self.resultado else 0.0

    @property
    def ok(self) -> bool:
        return self.resultado.ok if self.resultado else False


@dataclass
class ProjetoGalpao:
    """Resultado completo do dimensionamento. É o que memorial, desenhos e lista leem."""
    dados: DadosGalpao = field(default_factory=DadosGalpao)

    # etapas de cálculo, cada uma com sua memória
    cargas: Dict[str, object] = field(default_factory=dict)      # composição de cargas
    vento: Dict[str, object] = field(default_factory=dict)       # V0, S1, S2, S3, q, Ce, Cpi, pressões
    combinacoes: List[object] = field(default_factory=list)      # combinações montadas
    esforcos: Dict[str, object] = field(default_factory=dict)    # envoltória do pórtico

    # elementos dimensionados
    elementos: List[ElementoDimensionado] = field(default_factory=list)

    # ligações e base
    ligacoes: Dict[str, Resultado] = field(default_factory=dict)
    base: Optional[Resultado] = None

    # produtos
    lista_material: List[Peca] = field(default_factory=list)
    resumo_pesos: Dict[str, float] = field(default_factory=dict)
    custo: Dict[str, float] = field(default_factory=dict)

    # diagnóstico
    avisos: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)

    # ---- consultas usadas pelas saídas ----
    def elemento(self, nome: str) -> Optional[ElementoDimensionado]:
        for e in self.elementos:
            if e.nome.lower().startswith(nome.lower()):
                return e
        return None

    @property
    def peso_total_kg(self) -> float:
        return sum(p.peso_total_kg for p in self.lista_material)

    @property
    def consumo_kg_m2(self) -> float:
        a = self.dados.area_coberta
        return self.peso_total_kg / a if a else 0.0

    @property
    def area_pintura_m2(self) -> float:
        return sum(p.area_pintura_m2 for p in self.lista_material)

    @property
    def ok(self) -> bool:
        return (not self.erros
                and all(e.ok for e in self.elementos)
                and all(r.ok for r in self.ligacoes.values())
                and (self.base.ok if self.base else True))

    def resumo(self) -> List[str]:
        linhas = [e.resultado.resumo() if e.resultado else f"{e.nome}: —"
                  for e in self.elementos]
        linhas += [r.resumo() for r in self.ligacoes.values()]
        if self.base:
            linhas.append(self.base.resumo())
        return linhas

    def para_json(self) -> dict:
        """Versão serializável, para a interface web."""
        def verif(v):
            return {"titulo": v.titulo, "norma": v.norma, "Sd": v.Sd, "Rd": v.Rd,
                    "unidade": v.unidade, "razao": round(v.razao, 3), "ok": v.ok,
                    "dispensada": v.dispensada, "observacao": v.observacao,
                    "passos": [{"texto": p.texto, "formula": p.formula, "conta": p.conta,
                                "valor": p.valor, "norma": p.norma} for p in v.passos]}

        def res(r):
            if r is None:
                return None
            return {"elemento": r.elemento, "perfil": r.perfil, "material": r.material,
                    "razao": round(r.razao, 3), "ok": r.ok,
                    "critica": r.critica.titulo if r.critica else "",
                    "verificacoes": [verif(v) for v in r.verificacoes],
                    "dados": {k: v for k, v in r.dados.items() if _simples(v)}}

        return {
            "dados": self.dados.dict(),
            "ok": self.ok,
            "elementos": [{"nome": e.nome, "perfil": e.perfil, "material": e.material,
                           "razao": round(e.razao, 3), "ok": e.ok,
                           "esforcos": e.esforcos, "geometria": e.geometria,
                           "alternativas": e.alternativas,
                           "resultado": res(e.resultado)} for e in self.elementos],
            "ligacoes": {k: res(v) for k, v in self.ligacoes.items()},
            "base": res(self.base),
            "vento": {k: v for k, v in self.vento.items() if _simples(v)},
            "cargas": {k: v for k, v in self.cargas.items() if _simples(v)},
            "lista_material": [asdict(p) for p in self.lista_material],
            "resumo_pesos": self.resumo_pesos,
            "custo": self.custo,
            "peso_total_kg": round(self.peso_total_kg, 1),
            "consumo_kg_m2": round(self.consumo_kg_m2, 2),
            "area_pintura_m2": round(self.area_pintura_m2, 1),
            "avisos": self.avisos,
            "erros": self.erros,
        }


def _simples(v) -> bool:
    return isinstance(v, (int, float, str, bool, type(None))) or (
        isinstance(v, (list, tuple, dict)) and len(str(v)) < 20000)
