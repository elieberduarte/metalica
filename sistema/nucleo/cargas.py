# -*- coding: utf-8 -*-
"""Ações e combinações — NBR 6120:2019, NBR 6123 (vento) e NBR 8681 / NBR 8800.

O módulo cobre três assuntos, na ordem em que aparecem no projeto:

1. **Ações permanentes e variáveis** (NBR 6120:2019 e NBR 8800, Anexo B):
   tabelas consultáveis de pesos de elementos construtivos e de sobrecargas de uso,
   e a composição do peso próprio de uma cobertura, parcela por parcela.
2. **Vento** (NBR 6123): V₀ → S₁, S₂, S₃ → V_k → q → C_e, C_pi → pressão efetiva
   em cada superfície do galpão, para vento transversal e longitudinal.
3. **Combinações** (NBR 8681 e NBR 8800, Tabelas 1 e 2): combinações últimas
   normais (cada variável como principal, permanente favorável com γ_g = 1,0) e
   combinações de serviço (quase permanente, frequente e rara).

Unidades deste módulo
---------------------
    pressão / carga de superfície   kN/m²
    carga linear                    kN/m
    velocidade                      m/s
    comprimento (b, a, h, z)        m
    ângulo                          graus

O restante do sistema trabalha em kN, cm e kN·cm (ver ``GUIA_SISTEMA.md``). As ações
nascem em kN/m² e kN/m — as unidades das normas de carga — e são convertidas para
kN/cm pelo módulo que as aplica nas barras (``galpao.py``, ``analise.py``).

Convenção de sinais das pressões de vento: **positivo = pressão** (empurra a face,
de fora para dentro); **negativo = sucção** (puxa a face para fora).

Convenção das direções do vento
-------------------------------
Este módulo nomeia as duas direções pelo que elas fazem, e não por um ângulo:

    "transversal"   — vento perpendicular à cumeeira (entra pela parede maior);
    "longitudinal"  — vento paralelo à cumeeira (entra pelo oitão).

O ângulo 0°/90° da NBR 6123 (Tabelas 4 e 5) é medido a partir da maior dimensão
em planta: 0° = longitudinal, 90° = transversal — que é a convenção do Capítulo 16
do manual. O Capítulo 5 do manual usa a convenção inversa (chama de 0° o vento
perpendicular à cumeeira). Por isso os aliases "0°"/"90°" aceitos aqui seguem o
Capítulo 5, e a documentação de cada resultado traz o nome por extenso.
"""
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Union

from .base import ErroDeDados, Passo, fmt

# ---------------------------------------------------------------------------
# utilidades internas
# ---------------------------------------------------------------------------


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto))
                   if unicodedata.category(c) != "Mn")


def _chave(texto) -> str:
    """Normaliza um nome para consulta: sem acento, minúsculo, sem pontuação."""
    return re.sub(r"[^a-z0-9]+", " ", _sem_acento(texto).lower()).strip()


def _busca(tabela: dict, nome, rotulo: str):
    """Consulta tolerante a acento, caixa e nome parcial."""
    k = _chave(nome)
    if k in tabela:
        return tabela[k]
    parciais = [c for c in tabela if k and (k in c or c in k)]
    if len(parciais) == 1:
        return tabela[parciais[0]]
    if len(parciais) > 1:
        raise ErroDeDados(f"{rotulo} ambíguo: '{nome}' casa com {', '.join(sorted(parciais))}")
    raise ErroDeDados(f"{rotulo} desconhecido: '{nome}'. Disponíveis: "
                      + ", ".join(sorted(tabela)))


def _interp(x: float, xs: Sequence[float], ys: Sequence[float]) -> float:
    """Interpolação linear com extremos constantes."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ys[-1]


def _fc(x: float) -> str:
    """Coeficiente no padrão brasileiro para o nome da combinação: 1,25 · 1,4 · 1,0."""
    s = f"{x:.3f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s.replace(".", ",")


# ===========================================================================
# 1. AÇÕES PERMANENTES E VARIÁVEIS — NBR 6120:2019
# ===========================================================================

@dataclass(frozen=True)
class Elemento:
    """Peso de um elemento construtivo (manual, Tabela 5.1 / 17.10; NBR 6120)."""
    nome: str
    valor: float                  # valor adotado
    minimo: float = 0.0
    maximo: float = 0.0
    unidade: str = "kN/m²"
    obs: str = ""
    norma: str = "NBR 6120:2019, Tabelas 1 a 3 (manual, Tabela 5.1)"

    @property
    def faixa(self) -> Tuple[float, float]:
        return (self.minimo or self.valor, self.maximo or self.valor)

    def texto(self) -> str:
        f = ""
        if self.minimo and self.maximo and self.minimo != self.maximo:
            f = f" (faixa {fmt(self.minimo)}–{fmt(self.maximo)})"
        return f"{self.nome}: {fmt(self.valor)} {self.unidade}{f}"


def _el(nome, valor, minimo=0.0, maximo=0.0, unidade="kN/m²", obs=""):
    return Elemento(nome, valor, minimo, maximo, unidade, obs)


# Pesos próprios de elementos construtivos (kN/m² da superfície do elemento).
# O valor adotado é o usual de projeto; a faixa é a da Tabela 5.1 do manual.
PESOS: Dict[str, Elemento] = {_chave(e.nome): e for e in [
    _el("telha metálica simples", 0.05, 0.05, 0.10,
        obs="trapezoidal 0,43–0,65 mm, aço galvanizado/galvalume"),
    _el("telha metálica de alumínio", 0.04, 0.03, 0.05, obs="trapezoidal de alumínio"),
    _el("telha sanduíche", 0.15, 0.12, 0.20, obs="termoacústica, núcleo EPS ou PIR 30–50 mm"),
    _el("telha de fibrocimento 6 mm", 0.20, 0.18, 0.25, obs="ondulada, inclui sobreposições"),
    _el("telha de fibrocimento 8 mm", 0.28, 0.25, 0.30, obs="ondulada"),
    _el("telha cerâmica", 0.70, 0.60, 0.80, obs="com ripas e caibros"),
    _el("terças", 0.05, 0.05, 0.08, obs="Ue 150–250 mm, vãos 5–8 m (manual, 16.2.1)"),
    _el("contraventamentos e acessórios", 0.05, 0.03, 0.08,
        obs="correntes, contraventos, mãos-francesas e ligações (manual, 16.2.1)"),
    _el("terças e contraventamentos", 0.10, 0.05, 0.10,
        obs="linha única da Tabela 5.1 (terças + contraventos de cobertura)"),
    _el("forro", 0.20, 0.10, 0.30, obs="gesso acartonado, PVC ou lã, com a estrutura de fixação"),
    _el("forro de gesso acartonado", 0.20, 0.15, 0.20, obs="placa 12,5 mm com perfis"),
    _el("forro de PVC", 0.05, 0.05, 0.10, obs="com a estrutura de fixação"),
    _el("laje steel deck 12 cm", 2.55, 2.30, 2.80, obs="fôrma 0,80 mm + concreto"),
    _el("laje steel deck 15 cm", 3.10, 2.80, 3.40, obs="fôrma 0,80 mm + concreto"),
    _el("laje maciça de concreto", 2.50, 2.50, 2.50,
        obs="h = 10 cm; usar peso_laje_macica(h) para outras espessuras"),
    _el("laje pré-moldada 12 cm", 2.00, 1.80, 2.20, obs="vigotas + lajotas, capa 4 cm"),
    _el("painel alveolar 20 cm", 2.95, 2.70, 3.20, obs="pré-moldado protendido"),
    _el("alvenaria cerâmica 14 cm", 2.00, 1.80, 2.20,
        obs="kN/m² de parede, revestida — multiplicar pela altura para obter kN/m"),
    _el("alvenaria cerâmica 9 cm", 1.35, 1.20, 1.50, obs="kN/m² de parede, revestida"),
    _el("alvenaria de bloco de concreto 14 cm", 2.40, 2.20, 2.60, obs="kN/m² de parede, revestida"),
    _el("drywall", 0.375, 0.25, 0.50, obs="kN/m² de parede"),
    _el("revestimento de piso", 1.00, 0.80, 1.20, obs="contrapiso + cerâmica/porcelanato"),
    _el("piso elevado", 0.40, 0.30, 0.50, obs=""),
    _el("piso de grade", 0.30, 0.28, 0.33, obs="grade 25×3 a 32×3 (manual, Tabela 17.10)"),
    _el("fechamento lateral com telha metálica", 0.125, 0.10, 0.15,
        obs="kN/m² de fachada, inclui longarinas"),
    _el("fechamento lateral em painel isotérmico", 0.20, 0.15, 0.25, obs="kN/m² de fachada"),
    _el("instalações penduradas", 0.30, 0.10, 0.50,
        obs="elétrica, ar-condicionado, sprinkler; dutos grandes podem passar de 0,5"),
    _el("vidro 10 mm", 0.25, 0.25, 0.25, obs="25 kN/m³ × espessura"),
    _el("painel ACM", 0.08, 0.08, 0.08, obs=""),
    _el("painel de fachada", 0.45, 0.30, 0.60, obs=""),
    _el("placas fotovoltaicas", 0.25, 0.15, 0.25,
        obs="sobre o telhado; verificar também o vento sobre os painéis"),
]}

_ALIAS_PESO = {
    "telha metalica": "telha metalica simples",
    "metalica": "telha metalica simples",
    "metalica simples": "telha metalica simples",
    "trapezoidal": "telha metalica simples",
    "aluminio": "telha metalica de aluminio",
    "sanduiche": "telha sanduiche",
    "termoacustica": "telha sanduiche",
    "fibrocimento": "telha de fibrocimento 6 mm",
    "ceramica": "telha ceramica",
    "steel deck": "laje steel deck 12 cm",
    "alvenaria": "alvenaria ceramica 14 cm",
    "revestimento": "revestimento de piso",
    "instalacoes": "instalacoes penduradas",
}

# Pesos específicos (kN/m³) — manual, Tabela 5.1 e 17.10.
PESOS_ESPECIFICOS: Dict[str, float] = {
    "aço": 78.5, "alumínio": 27.0, "concreto armado": 25.0, "concreto simples": 24.0,
    "argamassa": 21.0, "alvenaria de tijolo furado": 13.0, "alvenaria de tijolo maciço": 18.0,
    "madeira": 8.0, "vidro": 25.0, "água": 10.0, "solo": 20.0,
}


@dataclass(frozen=True)
class Sobrecarga:
    """Sobrecarga de uso (NBR 6120:2019; cobertura pela NBR 8800, Anexo B.5.1)."""
    nome: str
    valor: float                  # kN/m²
    minimo: float = 0.0
    maximo: float = 0.0
    psi: str = "depósito"         # linha da Tabela 2 da NBR 8800 (ver PSI)
    obs: str = ""
    norma: str = "NBR 6120:2019, Tabela 10"

    @property
    def faixa(self) -> Tuple[float, float]:
        return (self.minimo or self.valor, self.maximo or self.valor)


def _sc(nome, valor, psi, minimo=0.0, maximo=0.0, obs="", norma="NBR 6120:2019, Tabela 10"):
    return Sobrecarga(nome, valor, minimo, maximo, psi, obs, norma)


SOBRECARGAS: Dict[str, Sobrecarga] = {_chave(s.nome): s for s in [
    _sc("cobertura sem acesso", 0.25, "cobertura", obs="só manutenção, em projeção horizontal",
        norma="NBR 8800:2008, item B.5.1"),
    _sc("cobertura com acesso", 1.00, "cobertura", 0.50, 1.00, obs="acesso de pessoas"),
    _sc("forro sem acesso", 0.50, "cobertura", obs=""),
    _sc("forro com acesso", 1.00, "cobertura", obs="manutenção de instalações"),
    _sc("residencial", 1.50, "residencial", obs="dormitórios, salas, cozinhas, banheiros"),
    _sc("área de serviço", 2.00, "residencial", obs="despensas e áreas de serviço"),
    _sc("sacada", 2.50, "residencial", obs=""),
    _sc("escritório", 2.50, "comercial", obs="salas de uso geral"),
    _sc("sala de reunião", 3.00, "comercial", obs=""),
    _sc("arquivo", 5.00, "depósito", obs="ou por levantamento das estantes"),
    _sc("loja", 4.00, "comercial", obs="áreas comerciais; supermercados: avaliar"),
    _sc("depósito", 7.50, "depósito", 5.00, 7.50,
        obs="calcular pela altura de empilhamento × peso específico"),
    _sc("garagem", 3.00, "depósito", obs="veículos ≤ 30 kN; caminhões 6,0 ou projeto específico"),
    _sc("escada com acesso ao público", 3.00, "comercial", obs=""),
    _sc("escada de uso restrito", 2.50, "residencial", obs="residencial"),
    _sc("sala de aula", 3.00, "comercial", obs=""),
    _sc("biblioteca leitura", 3.00, "comercial", obs=""),
    _sc("biblioteca estantes", 6.00, "depósito", obs="6,0 ou mais"),
    _sc("auditório", 4.00, "comercial", obs=""),
    _sc("academia", 5.00, "comercial", obs="verificar vibração"),
    _sc("mezanino industrial", 5.00, "depósito", 5.00, 7.50,
        obs="oficina; 7,5–10 para estoque; máquinas entram com o peso real + impacto"),
    _sc("plataforma de manutenção", 2.50, "depósito", obs="passarelas industriais"),
    _sc("plataforma de operação", 5.00, "depósito", obs="com materiais"),
]}


def peso(elemento) -> Elemento:
    """Peso próprio de um elemento construtivo (kN/m²), manual Tabela 5.1."""
    k = _chave(elemento)
    k = _ALIAS_PESO.get(k, k)
    return _busca(PESOS, k, "elemento")


def sobrecarga(local) -> Sobrecarga:
    """Sobrecarga de uso (kN/m²) por tipo de ambiente (NBR 6120:2019)."""
    if isinstance(local, (int, float)):
        return Sobrecarga("valor informado", float(local), psi="depósito",
                          obs="valor informado pelo usuário", norma="—")
    return _busca(SOBRECARGAS, local, "local de uso")


def peso_laje_macica(h_cm: float, peso_especifico: float = 25.0) -> float:
    """Peso próprio de laje maciça (kN/m²): γ_concreto · h (NBR 6120, Tabela 1)."""
    if h_cm <= 0 or h_cm > 40:
        raise ErroDeDados(f"espessura de laje maciça fora da faixa usual: {h_cm} cm "
                          "(aceitável: 0 < h ≤ 40 cm)")
    return peso_especifico * h_cm / 100.0


def peso_laje_steel_deck(h_cm: float) -> float:
    """Peso próprio de laje mista com fôrma de aço incorporada (kN/m²).

    Interpolação entre os dois pontos tabelados no manual (Tabela 5.1):
    h = 12 cm → 2,55 kN/m² e h = 15 cm → 3,10 kN/m². Estimativa preliminar:
    confirme com o catálogo da fôrma (altura da nervura e espessura da chapa).
    """
    if h_cm < 10 or h_cm > 20:
        raise ErroDeDados(f"espessura de laje steel deck fora da faixa coberta: {h_cm} cm "
                          "(aceitável: 10 cm ≤ h ≤ 20 cm)")
    return 2.55 + (3.10 - 2.55) * (h_cm - 12.0) / 3.0


def carga_de_parede(elemento, altura_m: float) -> float:
    """Carga linear (kN/m) de uma parede sobre a viga que a suporta."""
    if altura_m <= 0:
        raise ErroDeDados("a altura da parede deve ser positiva (m)")
    return peso(elemento).valor * altura_m


def por_metro(q_kN_m2: float, largura_m: float) -> float:
    """Converte carga de superfície (kN/m²) em carga linear (kN/m).

    `largura_m` é a área de influência por metro de barra: o espaçamento das
    terças, o espaçamento dos pórticos, a largura da faixa (manual, item 5.2.3).
    """
    if largura_m <= 0:
        raise ErroDeDados("a largura de influência deve ser positiva (m)")
    return q_kN_m2 * largura_m


@dataclass
class ItemCarga:
    descricao: str
    valor: float
    fonte: str = ""


@dataclass
class Composicao:
    """Uma carga somada parcela a parcela, com a origem de cada uma.

    O memorial imprime a composição inteira, e não só o total: é assim que o
    leitor confere de onde veio cada kN/m².
    """
    titulo: str
    itens: List[ItemCarga] = field(default_factory=list)
    unidade: str = "kN/m²"
    norma: str = "NBR 6120:2019"

    def add(self, descricao: str, valor: float, fonte: str = ""):
        self.itens.append(ItemCarga(descricao, valor, fonte))
        return self

    @property
    def total(self) -> float:
        return sum(i.valor for i in self.itens)

    def __float__(self) -> float:
        return self.total

    def texto(self) -> str:
        p = " + ".join(f"{i.descricao} {fmt(i.valor)}" for i in self.itens)
        return f"{self.titulo}: {p} = {fmt(self.total)} {self.unidade}"

    def passos(self) -> List[Passo]:
        ps = [Passo(i.descricao, valor=fmt(i.valor, 3, self.unidade), norma=i.fonte)
              for i in self.itens]
        ps.append(Passo(f"{self.titulo} — total",
                        formula=" + ".join(i.descricao for i in self.itens),
                        conta=" + ".join(fmt(i.valor, 3) for i in self.itens),
                        valor=fmt(self.total, 3, self.unidade), norma=self.norma))
        return ps


def peso_proprio_cobertura(telha="telha metálica simples",
                           com_forro: bool = False,
                           com_tercas: bool = True,
                           com_acessorios: bool = True,
                           instalacoes: float = 0.0,
                           valor_telha: Optional[float] = None,
                           valor_forro: Optional[float] = None,
                           extras: Sequence[Tuple[str, float]] = ()) -> Composicao:
    """Peso próprio de uma cobertura metálica, em kN/m² de projeção horizontal.

    Devolve uma `Composicao` com a parcela de cada elemento (telha, terças,
    contraventamentos e acessórios, forro, instalações), citando a origem — o
    memorial imprime a soma discriminada (manual, Tabelas 5.1 e 16.2.1).

    Parâmetros
    ----------
    telha            nome na tabela PESOS ("telha metálica simples", "sanduíche",
                     "fibrocimento", ...) ou "nenhuma".
    com_tercas       inclui 0,05 kN/m² de terças (Ue a cada 1,5–2,0 m).
    com_acessorios   inclui 0,05 kN/m² de correntes, contraventos, mãos-francesas
                     e ligações.
    instalacoes      kN/m² de instalações penduradas (0 quando não houver).
    valor_telha,
    valor_forro      sobrepõem o valor da tabela quando o fabricante é conhecido.
    extras           parcelas adicionais [(descrição, kN/m²), ...].

    Não inclui o peso próprio dos pórticos/tesouras, que entra diretamente nas
    barras da análise (manual, item 16.2.1).
    """
    c = Composicao("Peso próprio da cobertura")
    if telha is not None and _chave(telha) not in ("nenhuma", "sem telha", ""):
        el = peso(telha)
        v = float(valor_telha) if valor_telha is not None else el.valor
        c.add(el.nome, v, el.norma)
    elif valor_telha is not None:
        c.add("telha (valor informado)", float(valor_telha), "informado pelo usuário")
    if com_tercas:
        el = PESOS[_chave("terças")]
        c.add(el.nome, el.valor, el.norma)
    if com_acessorios:
        el = PESOS[_chave("contraventamentos e acessórios")]
        c.add(el.nome, el.valor, el.norma)
    if com_forro or valor_forro is not None:
        el = PESOS[_chave("forro")]
        v = float(valor_forro) if valor_forro is not None else el.valor
        c.add(el.nome, v, el.norma)
    if instalacoes:
        c.add("instalações penduradas", float(instalacoes),
              PESOS[_chave("instalações penduradas")].norma)
    for desc, val in extras:
        c.add(desc, float(val), "informado pelo usuário")
    if not c.itens:
        raise ErroDeDados("nenhuma parcela de peso próprio foi selecionada para a cobertura")
    return c


# ===========================================================================
# 2. VENTO — NBR 6123
# ===========================================================================

@dataclass(frozen=True)
class CidadeV0:
    nome: str
    V0: float                     # m/s
    minimo: float = 0.0
    maximo: float = 0.0
    fonte: str = "manual, Tabela 5.4 (leitura do mapa de isopletas da NBR 6123)"


def _cid(nome, V0, minimo=0.0, maximo=0.0, fonte=None):
    return CidadeV0(nome, V0, minimo, maximo,
                    fonte or "manual, Tabela 5.4 (leitura do mapa de isopletas da NBR 6123)")


_REGIONAL = ("valor regional da Tabela 5.4 do manual — confira o mapa de isopletas "
             "da NBR 6123 vigente para a localidade")

# Velocidade básica V0 (m/s). Quando o manual dá uma faixa, adota-se o limite
# superior (a favor da segurança) e a faixa fica registrada.
V0_CIDADES: Dict[str, CidadeV0] = {_chave(c.nome): c for c in [
    # Sul
    _cid("Porto Alegre", 46), _cid("Florianópolis", 43), _cid("Curitiba", 43),
    _cid("Londrina", 45), _cid("Chapecó", 50, 48, 50), _cid("Caxias do Sul", 46, 45, 47),
    # Sudeste
    _cid("São Paulo", 43, 40, 43), _cid("Rio de Janeiro", 35), _cid("Belo Horizonte", 32),
    _cid("Vitória", 32), _cid("Campinas", 42),
    # Centro-Oeste
    _cid("Campo Grande", 40), _cid("Cuiabá", 32), _cid("Goiânia", 33), _cid("Brasília", 35),
    # Nordeste
    _cid("Salvador", 30), _cid("Recife", 30), _cid("Fortaleza", 30), _cid("Natal", 30),
    _cid("São Luís", 30),
    _cid("Aracaju", 30, 30, 35, _REGIONAL), _cid("Maceió", 30, 30, 35, _REGIONAL),
    _cid("João Pessoa", 30, 30, 35, _REGIONAL), _cid("Teresina", 30, 30, 35, _REGIONAL),
    # Norte
    _cid("Manaus", 30), _cid("Belém", 30), _cid("Porto Velho", 30), _cid("Palmas", 32),
    _cid("Rio Branco", 30, 30, 30, _REGIONAL), _cid("Macapá", 30, 30, 30, _REGIONAL),
    _cid("Boa Vista", 30, 30, 30, _REGIONAL),
]}


def velocidade_basica(cidade) -> float:
    """Velocidade básica V₀ em m/s (NBR 6123, item 5.1 — mapa de isopletas).

    Aceita o nome da cidade (tabela V0_CIDADES) ou o próprio V₀ em m/s, lido pelo
    projetista no mapa da norma vigente — que é sempre o procedimento correto,
    pois a tabela aqui é uma leitura aproximada do mapa.
    """
    if isinstance(cidade, (int, float)):
        v = float(cidade)
        if not (25.0 <= v <= 60.0):
            raise ErroDeDados(f"V₀ = {v} m/s fora da faixa do mapa brasileiro "
                              "(aceitável: 25 a 60 m/s)")
        return v
    return _busca(V0_CIDADES, cidade, "cidade").V0


def fator_s1(tipo: str = "plano", theta_graus: float = 0.0,
             z: float = 0.0, d: float = 1.0) -> float:
    """Fator topográfico S₁ (NBR 6123, item 5.2).

    tipo = "plano"  (terreno plano ou fracamente acidentado)         → 1,0
    tipo = "vale"   (vale profundo, protegido de ventos)             → 0,9
    tipo = "talude" ou "morro" (ponto na crista ou próximo dela):
            θ ≤ 3°            → S₁ = 1,0
            6° ≤ θ ≤ 17°      → S₁ = 1,0 + (2,5 − z/d)·tg(θ − 3°) ≥ 1
            θ ≥ 45°           → S₁ = 1,0 + (2,5 − z/d)·0,31 ≥ 1
            faixas 3°–6° e 17°–45°: interpolação linear em θ.

    z = altura do ponto acima da superfície do terreno no topo do talude/morro;
    d = diferença de nível entre a base e o topo. O acréscimo se anula para
    z ≥ 2,5·d. No sotavento do morro adota-se S₁ = 1,0, a favor da segurança.
    """
    t = _chave(tipo)
    if t in ("plano", "terreno plano", "fracamente acidentado"):
        return 1.0
    if t in ("vale", "vale profundo"):
        return 0.9
    if t not in ("talude", "morro", "talude ou morro", "crista"):
        raise ErroDeDados(f"tipo de relevo desconhecido: '{tipo}'. "
                          "Use 'plano', 'vale', 'talude' ou 'morro'.")
    if d <= 0:
        raise ErroDeDados("para talude ou morro é preciso informar d > 0 "
                          "(desnível entre a base e o topo, em m)")
    if z < 0:
        raise ErroDeDados("a altura z do ponto acima do topo não pode ser negativa")
    th = float(theta_graus)
    if th < 0:
        raise ErroDeDados("a inclinação θ do talude não pode ser negativa")
    tg = _interp(th,
                 [0.0, 3.0, 6.0, 17.0, 45.0, 90.0],
                 [0.0, 0.0, math.tan(math.radians(3.0)), math.tan(math.radians(14.0)),
                  0.31, 0.31])
    return max(1.0, 1.0 + (2.5 - z / d) * tg)


# NBR 6123, Tabela 1 — parâmetros b e p de S₂ = b·F_r·(z/10)^p, por categoria e classe.
PARAMETROS_S2: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("I", "A"): (1.10, 0.06),   ("I", "B"): (1.11, 0.065),  ("I", "C"): (1.12, 0.07),
    ("II", "A"): (1.00, 0.085), ("II", "B"): (1.00, 0.09),  ("II", "C"): (1.00, 0.10),
    ("III", "A"): (0.94, 0.10), ("III", "B"): (0.94, 0.105), ("III", "C"): (0.93, 0.115),
    ("IV", "A"): (0.86, 0.12),  ("IV", "B"): (0.85, 0.125), ("IV", "C"): (0.84, 0.135),
    ("V", "A"): (0.74, 0.15),   ("V", "B"): (0.73, 0.16),   ("V", "C"): (0.71, 0.175),
}
# Fator de rajada F_r (sempre o da categoria II, por classe) — NBR 6123, Tabela 1.
FR_S2: Dict[str, float] = {"A": 1.00, "B": 0.98, "C": 0.95}
# Altura gradiente z_g (m) — limite superior de validade da expressão.
ZG_S2: Dict[str, float] = {"I": 250.0, "II": 300.0, "III": 350.0, "IV": 420.0, "V": 500.0}

CATEGORIAS_S2 = {
    "I": "superfícies lisas de grandes dimensões (mar, lagos, pântanos sem vegetação)",
    "II": "terreno aberto em nível, poucos obstáculos isolados (obstáculos < 1 m)",
    "III": "terreno plano ou ondulado com sebes, muros e edificações baixas (obstáculos ≈ 3 m)",
    "IV": "obstáculos numerosos e pouco espaçados: zona industrial ou urbanizada (≈ 10 m)",
    "V": "obstáculos numerosos, grandes e altos: centros de grandes cidades, florestas (≥ 25 m)",
}
CLASSES_S2 = {
    "A": "maior dimensão (horizontal ou vertical) ≤ 20 m — telhas, terças, elementos isolados",
    "B": "maior dimensão entre 20 m e 50 m",
    "C": "maior dimensão > 50 m",
}

_ROMANOS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}


def _categoria(categoria) -> str:
    if isinstance(categoria, int):
        if categoria not in _ROMANOS:
            raise ErroDeDados(f"categoria de rugosidade inválida: {categoria} (use I a V)")
        return _ROMANOS[categoria]
    c = _sem_acento(str(categoria)).strip().upper().replace("CATEGORIA", "").strip()
    if c not in ZG_S2:
        raise ErroDeDados(f"categoria de rugosidade desconhecida: '{categoria}'. "
                          "Use I, II, III, IV ou V.")
    return c


def _classe(classe) -> str:
    c = _sem_acento(str(classe)).strip().upper().replace("CLASSE", "").strip()
    if c not in FR_S2:
        raise ErroDeDados(f"classe de dimensão desconhecida: '{classe}'. Use A, B ou C.")
    return c


def classe_por_dimensao(maior_dimensao_m: float) -> str:
    """Classe A/B/C pela maior dimensão da edificação ou do elemento (NBR 6123, 5.3.2)."""
    if maior_dimensao_m <= 0:
        raise ErroDeDados("a maior dimensão deve ser positiva (m)")
    if maior_dimensao_m <= 20.0:
        return "A"
    return "B" if maior_dimensao_m <= 50.0 else "C"


def fator_s2(categoria="II", classe="B", z: float = 10.0) -> float:
    """Fator de rugosidade, dimensões e altura S₂ (NBR 6123, item 5.3 e Tabela 1).

        S₂ = b · F_r · (z/10)^p

    z é a altura acima do terreno, em metros. Abaixo de 5 m a norma tabela um
    valor constante: adota-se S₂(5 m), que é maior que o da expressão e portanto
    está a favor da segurança. Acima da altura gradiente z_g a expressão não vale
    e a função levanta ErroDeDados.
    """
    cat, cl = _categoria(categoria), _classe(classe)
    b, p = PARAMETROS_S2[(cat, cl)]
    fr = FR_S2[cl]
    if z <= 0:
        raise ErroDeDados("a altura z deve ser positiva (m)")
    if z > ZG_S2[cat]:
        raise ErroDeDados(f"z = {z} m acima da altura gradiente da categoria {cat} "
                          f"(z_g = {ZG_S2[cat]:.0f} m): fora do alcance da Tabela 1 da NBR 6123")
    z_calc = max(float(z), 5.0)
    return b * fr * (z_calc / 10.0) ** p


# NBR 6123, Tabela 3 — fator estatístico S₃.
GRUPOS_S3: Dict[int, Tuple[float, str]] = {
    1: (1.10, "edificações cuja ruína afeta a segurança ou o socorro após a tempestade "
              "(hospitais, quartéis, centrais de comunicação e energia)"),
    2: (1.00, "hotéis, residências, comércio e indústria com alto fator de ocupação"),
    3: (0.95, "indústrias com baixo fator de ocupação (depósitos, silos, construções rurais)"),
    4: (0.88, "vedações: telhas, vidros, painéis de vedação"),
    5: (0.83, "edificações temporárias e estruturas durante a construção"),
}


def fator_s3(grupo: Union[int, str] = 2) -> float:
    """Fator estatístico S₃ (NBR 6123, item 5.4 e Tabela 3)."""
    if isinstance(grupo, str):
        k = _chave(grupo)
        achado = [g for g, (_, d) in GRUPOS_S3.items() if k in _chave(d)]
        if len(achado) != 1:
            raise ErroDeDados(f"grupo de S₃ desconhecido: '{grupo}'. Use 1 a 5 "
                              "(2 = indústria/comércio com alto fator de ocupação).")
        grupo = achado[0]
    if grupo not in GRUPOS_S3:
        raise ErroDeDados(f"grupo de S₃ inválido: {grupo} (use 1 a 5)")
    return GRUPOS_S3[int(grupo)][0]


def velocidade_caracteristica(V0: float, S1: float = 1.0, S2: float = 1.0,
                              S3: float = 1.0) -> float:
    """V_k = V₀·S₁·S₂·S₃, em m/s (NBR 6123, item 4.2 — equação 5.2 do manual)."""
    return float(V0) * S1 * S2 * S3


def pressao_dinamica(Vk: float) -> float:
    """Pressão dinâmica q = 0,613·V_k² (N/m²), devolvida em **kN/m²**.

    NBR 6123, item 4.2, equação 2. A constante 0,613 é metade da massa específica
    do ar (1,226 kg/m³) nas condições normais.
    """
    if Vk <= 0:
        raise ErroDeDados("a velocidade característica V_k deve ser positiva (m/s)")
    return 0.613 * float(Vk) ** 2 / 1000.0


def pressao_efetiva(Ce: float, Cpi: float, q: float) -> float:
    """p = (C_e − C_pi)·q, em kN/m² (NBR 6123, item 6.1 — equação 5.4 do manual).

    Positivo = pressão sobre a face; negativo = sucção.
    """
    return (float(Ce) - float(Cpi)) * float(q)


# --- coeficientes de pressão externa (Tabelas 4 e 5 da NBR 6123) ------------

TRANSVERSAL = "transversal"
LONGITUDINAL = "longitudinal"

_ALIAS_DIRECAO = {
    "transversal": TRANSVERSAL, "0": TRANSVERSAL, "0 graus": TRANSVERSAL,
    "perpendicular a cumeeira": TRANSVERSAL, "perpendicular": TRANSVERSAL,
    "90 nbr": TRANSVERSAL,
    "longitudinal": LONGITUDINAL, "90": LONGITUDINAL, "90 graus": LONGITUDINAL,
    "paralelo a cumeeira": LONGITUDINAL, "paralelo": LONGITUDINAL, "oitao": LONGITUDINAL,
    "0 nbr": LONGITUDINAL,
}


def _direcao(nome) -> str:
    k = _chave(str(nome).replace("°", " graus"))
    if k in _ALIAS_DIRECAO:
        return _ALIAS_DIRECAO[k]
    raise ErroDeDados(f"direção de vento desconhecida: '{nome}'. "
                      "Use 'transversal' (⊥ à cumeeira) ou 'longitudinal' (∥ à cumeeira).")


# NBR 6123, Tabela 4 — paredes de edificação de planta retangular.
# Chave: (faixa de h/b, faixa de a/b) → por direção do vento:
#   barlavento  parede que recebe o vento de frente
#   sotavento   parede oposta
#   lateral_1   paredes paralelas ao vento, trecho inicial (b/2 a partir da aresta de barlavento)
#   lateral_2   paredes paralelas ao vento, trecho restante
_TABELA_4 = {
    ("<=1/2", "1..3/2"): {
        TRANSVERSAL:  {"barlavento": 0.7, "sotavento": -0.4, "lateral_1": -0.8, "lateral_2": -0.5},
        LONGITUDINAL: {"barlavento": 0.7, "sotavento": -0.4, "lateral_1": -0.8, "lateral_2": -0.5},
    },
    ("<=1/2", "2..4"): {
        TRANSVERSAL:  {"barlavento": 0.7, "sotavento": -0.5, "lateral_1": -0.9, "lateral_2": -0.5},
        LONGITUDINAL: {"barlavento": 0.7, "sotavento": -0.3, "lateral_1": -0.8, "lateral_2": -0.4},
    },
    ("1/2..3/2", "1..3/2"): {
        TRANSVERSAL:  {"barlavento": 0.7, "sotavento": -0.5, "lateral_1": -0.9, "lateral_2": -0.5},
        LONGITUDINAL: {"barlavento": 0.7, "sotavento": -0.5, "lateral_1": -0.9, "lateral_2": -0.5},
    },
    ("1/2..3/2", "2..4"): {
        TRANSVERSAL:  {"barlavento": 0.7, "sotavento": -0.6, "lateral_1": -0.9, "lateral_2": -0.5},
        LONGITUDINAL: {"barlavento": 0.7, "sotavento": -0.5, "lateral_1": -0.9, "lateral_2": -0.5},
    },
}

# NBR 6123, Tabela 5 — telhados de duas águas, planta retangular.
# Para cada faixa de h/b: θ (graus) e os coeficientes das quatro zonas.
#   EF = água de barlavento e GH = água de sotavento (vento transversal)
#   EG = trecho inicial (b/2) e FH = restante                (vento longitudinal)
_TETA_TABELA_5 = [0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0]
_TABELA_5 = {
    "<=1/2": {
        "EF": [-0.8, -0.9, -1.2, -1.0, -0.4, 0.0, 0.3, 0.7],
        "GH": [-0.4, -0.4, -0.4, -0.4, -0.4, -0.4, -0.5, -0.6],
        "EG": [-0.8, -0.8, -0.8, -0.8, -0.7, -0.7, -0.7, -0.7],
        "FH": [-0.4, -0.4, -0.6, -0.6, -0.6, -0.6, -0.6, -0.6],
    },
    "1/2..3/2": {
        "EF": [-0.9, -1.2, -1.1, -1.0, -0.7, -0.2, 0.2, 0.6],
        "GH": [-0.4, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4],
        "EG": [-0.8, -0.9, -0.8, -0.8, -0.8, -0.8, -0.8, -0.8],
        "FH": [-0.5, -0.5, -0.5, -0.5, -0.5, -0.5, -0.5, -0.5],
    },
}

# Coeficientes locais de alta sucção, só para telhas, fixações e elementos de vedação.
CE_LOCAL_CANTO_PAREDE = -1.0      # faixa ≈ 0,2·b junto aos cantos (manual, Tabela 16.2)
CE_LOCAL_BORDA_TELHADO = -1.4     # faixa ≈ 0,15·b nas bordas    (manual, Tabela 5.7)
CE_LOCAL_CUMEEIRA = -2.0          # cantos e cumeeira            (manual, Tabela 5.7)


@dataclass(frozen=True)
class Coeficiente:
    """Coeficiente de pressão externa C_e de uma superfície do galpão."""
    direcao: str
    superficie: str               # nome legível ("telhado barlavento")
    letra: str                    # notação da NBR 6123 ("EF", "A1", "C")
    Ce: float
    zona: str = ""                # extensão da zona, quando subdividida
    local: bool = False           # True = coeficiente local (só telhas e fixações)
    norma: str = ""

    @property
    def rotulo(self) -> str:
        return f"{self.superficie} ({self.letra})" if self.letra else self.superficie


@dataclass
class CoeficientesGalpao:
    """Coeficientes de pressão externa de um galpão de duas águas."""
    b: float
    a: float
    h: float
    theta: float
    h_b: float
    a_b: float
    faixa_h_b: str
    faixa_a_b: str
    coeficientes: List[Coeficiente] = field(default_factory=list)
    observacoes: List[str] = field(default_factory=list)

    def por_direcao(self, direcao) -> List[Coeficiente]:
        d = _direcao(direcao)
        return [c for c in self.coeficientes if c.direcao == d]

    def estruturais(self) -> List[Coeficiente]:
        """Sem os coeficientes locais de borda (que só valem para telhas e fixações)."""
        return [c for c in self.coeficientes if not c.local]

    def busca(self, superficie, direcao=None) -> Coeficiente:
        k = _chave(superficie)
        cs = [c for c in self.coeficientes
              if (direcao is None or c.direcao == _direcao(direcao))
              and (k in _chave(c.superficie) or k == _chave(c.letra))]
        if not cs:
            raise ErroDeDados(f"superfície desconhecida: '{superficie}'. Disponíveis: "
                              + ", ".join(sorted({c.superficie for c in self.coeficientes})))
        if len(cs) > 1:
            raise ErroDeDados(f"superfície ambígua: '{superficie}' casa com "
                              + ", ".join(f"{c.superficie} [{c.direcao}]" for c in cs))
        return cs[0]

    def tabela(self) -> List[dict]:
        return [{"direção": c.direcao, "superfície": c.rotulo, "zona": c.zona,
                 "Ce": c.Ce, "local": c.local} for c in self.coeficientes]


def coeficientes_pressao_galpao(b: float, a: float, h: float,
                                theta_graus: float) -> CoeficientesGalpao:
    """Coeficientes de pressão externa C_e de um galpão de duas águas.

    NBR 6123, Tabela 4 (paredes) e Tabela 5 (telhados de duas águas), em função
    de h/b, a/b e da inclinação θ do telhado, para as duas direções de vento.

    Parâmetros (em metros)
    ----------------------
    b  largura (menor dimensão em planta, vão do pórtico);
    a  comprimento (maior dimensão em planta);
    h  altura do beiral (pé-direito);
    theta_graus  inclinação do telhado.

    Interpolação: linear em θ entre os valores tabelados da Tabela 5 (0°, 5°, 10°,
    15°, 20°, 30°, 45° e 60°) e linear em a/b na lacuna entre as colunas
    1 ≤ a/b ≤ 3/2 e 2 ≤ a/b ≤ 4 da Tabela 4. As faixas de h/b **não** são
    interpoladas: a norma as trata como degraus.

    Cobertura e limites (ver observações do resultado):
      * h/b ≤ 3/2 — acima disso levanta ErroDeDados (não implementado);
      * 0° ≤ θ ≤ 60°;
      * a/b > 4 usa a coluna 2 ≤ a/b ≤ 4, com observação de extrapolação;
      * a faixa 1/2 < h/b ≤ 3/2 não é validada por exemplo do manual.
    """
    for nome, v in (("b", b), ("a", a), ("h", h)):
        if v <= 0:
            raise ErroDeDados(f"a dimensão {nome} do galpão deve ser positiva (m)")
    if a < b:
        raise ErroDeDados(f"a = {fmt(a)} m deve ser a maior dimensão em planta e "
                          f"b = {fmt(b)} m a menor (vão). Inverta os dois.")
    th = float(theta_graus)
    if th < 0 or th > 60:
        raise ErroDeDados(f"inclinação do telhado θ = {fmt(th)}° fora da Tabela 5 da "
                          "NBR 6123 (0° ≤ θ ≤ 60°)")
    h_b, a_b = h / b, a / b
    obs: List[str] = []
    if h_b <= 0.5:
        faixa_h = "<=1/2"
    elif h_b <= 1.5:
        faixa_h = "1/2..3/2"
        obs.append("h/b entre 1/2 e 3/2: valores das Tabelas 4 e 5 adotados a favor da "
                   "segurança; os exemplos do manual só validam h/b ≤ 1/2 — confira na "
                   "norma antes de usar em obra.")
    else:
        raise ErroDeDados(f"h/b = {fmt(h_b)} > 3/2: fora da faixa implementada das Tabelas 4 "
                          "e 5 da NBR 6123 (galpões usuais têm h/b ≤ 1/2). Consulte a norma.")
    if a_b > 4.0:
        obs.append(f"a/b = {fmt(a_b)} > 4: adotada a coluna 2 ≤ a/b ≤ 4 da Tabela 4 "
                   "(extrapolação; a norma não tabela a/b > 4).")

    def parede(papel: str) -> Dict[str, float]:
        c1 = _TABELA_4[(faixa_h, "1..3/2")]
        c2 = _TABELA_4[(faixa_h, "2..4")]
        return {d: _interp(a_b, [1.5, 2.0], [c1[d][papel], c2[d][papel]])
                for d in (TRANSVERSAL, LONGITUDINAL)}

    if 1.5 < a_b < 2.0:
        obs.append(f"a/b = {fmt(a_b)} cai na lacuna entre as colunas 1 ≤ a/b ≤ 3/2 e "
                   "2 ≤ a/b ≤ 4 da Tabela 4: coeficientes de parede interpolados linearmente.")

    barl, sota = parede("barlavento"), parede("sotavento")
    lat1, lat2 = parede("lateral_1"), parede("lateral_2")

    tel = _TABELA_5[faixa_h]
    ce = {z: _interp(th, _TETA_TABELA_5, tel[z]) for z in ("EF", "GH", "EG", "FH")}
    if th not in _TETA_TABELA_5:
        obs.append(f"θ = {fmt(th)}° interpolado linearmente entre os ângulos tabelados da "
                   "Tabela 5 da NBR 6123.")

    n4 = "NBR 6123, Tabela 4"
    n5 = "NBR 6123, Tabela 5"
    z1p = f"trecho inicial de {fmt(b / 2)} m (b/2) a partir da aresta de barlavento"
    z1t = f"trecho inicial de {fmt(b / 2)} m (b/2) a partir do oitão de barlavento"
    cs = [
        # vento transversal (perpendicular à cumeeira) — entra pela parede maior
        Coeficiente(TRANSVERSAL, "parede lateral barlavento", "A", barl[TRANSVERSAL], "", False, n4),
        Coeficiente(TRANSVERSAL, "parede lateral sotavento", "B", sota[TRANSVERSAL], "", False, n4),
        Coeficiente(TRANSVERSAL, "oitão zona 1", "C1/D1", lat1[TRANSVERSAL], z1p, False, n4),
        Coeficiente(TRANSVERSAL, "oitão zona 2", "C2/D2", lat2[TRANSVERSAL], "restante", False, n4),
        Coeficiente(TRANSVERSAL, "telhado barlavento", "EF", ce["EF"], "água de barlavento",
                    False, n5),
        Coeficiente(TRANSVERSAL, "telhado sotavento", "GH", ce["GH"], "água de sotavento",
                    False, n5),
        # vento longitudinal (paralelo à cumeeira) — entra pelo oitão
        Coeficiente(LONGITUDINAL, "oitão barlavento", "C", barl[LONGITUDINAL], "", False, n4),
        Coeficiente(LONGITUDINAL, "oitão sotavento", "D", sota[LONGITUDINAL], "", False, n4),
        Coeficiente(LONGITUDINAL, "parede lateral zona 1", "A1/B1", lat1[LONGITUDINAL],
                    z1p, False, n4),
        Coeficiente(LONGITUDINAL, "parede lateral zona 2", "A2/B2", lat2[LONGITUDINAL],
                    "restante", False, n4),
        Coeficiente(LONGITUDINAL, "telhado zona 1", "EG", ce["EG"], z1t, False, n5),
        Coeficiente(LONGITUDINAL, "telhado zona 2", "FH", ce["FH"], "restante", False, n5),
    ]
    # zonas locais de alta sucção — apenas telhas, fixações e elementos de vedação
    for d in (TRANSVERSAL, LONGITUDINAL):
        cs += [
            Coeficiente(d, "canto de parede (local)", "", CE_LOCAL_CANTO_PAREDE,
                        f"faixa ≈ 0,2·b = {fmt(0.2 * b)} m junto aos cantos", True,
                        "NBR 6123, Tabela 4 (manual, Tabela 16.2)"),
            Coeficiente(d, "borda de telhado (local)", "", CE_LOCAL_BORDA_TELHADO,
                        f"faixa ≈ 0,15·b = {fmt(0.15 * b)} m nas bordas", True,
                        "NBR 6123, Tabela 5 (manual, Tabela 5.7)"),
            Coeficiente(d, "cumeeira e cantos de telhado (local)", "", CE_LOCAL_CUMEEIRA,
                        f"faixa ≈ 0,15·b = {fmt(0.15 * b)} m", True,
                        "NBR 6123, Tabela 5 (manual, Tabela 5.7)"),
        ]
    obs.append("Os coeficientes marcados como locais valem só para telhas, fixações e "
               "elementos de vedação; não devem ser usados no dimensionamento da "
               "estrutura principal (manual, item 5.4.6).")
    return CoeficientesGalpao(b, a, h, th, h_b, a_b,
                              faixa_h, "1..3/2" if a_b < 2 else "2..4", cs, obs)


# --- coeficiente de pressão interna (NBR 6123, item 6.2) -------------------

@dataclass(frozen=True)
class CasoCpi:
    valor: float
    nome: str
    descricao: str
    norma: str = "NBR 6123, item 6.2"


_RAZOES_ABERTURA = [1.0, 1.5, 2.0, 3.0, 6.0]
_CPI_ABERTURA = [0.1, 0.3, 0.5, 0.6, 0.8]

ABERTURAS = {
    "duas faces opostas": "duas faces opostas igualmente permeáveis, as outras impermeáveis",
    "quatro faces permeáveis": "quatro faces igualmente permeáveis",
    "estanque": "edificação efetivamente estanque, com janelas fixas",
    "abertura dominante a barlavento": "abertura dominante na face de barlavento (portão aberto)",
    "abertura dominante a sotavento": "abertura dominante na face de sotavento",
    "abertura dominante em face paralela": "abertura dominante em face paralela ao vento",
}


def coeficiente_pressao_interna(aberturas="duas faces opostas",
                                razao_areas: Optional[float] = None,
                                ce_face: Optional[float] = None) -> List[CasoCpi]:
    """Coeficiente de pressão interna C_pi (NBR 6123, item 6.2 — Tabela 5.8 do manual).

    Devolve **a lista de casos a verificar**, porque a norma manda testar todos os
    valores possíveis e usar o mais desfavorável para cada elemento.

        "duas faces opostas"               → +0,2 (vento ⊥ à face permeável) e
                                             −0,3 (vento ⊥ à face impermeável)
        "quatro faces permeáveis"          → −0,3 e 0 (o mais nocivo)
        "estanque"                         → −0,2 e 0 (o mais nocivo)
        "abertura dominante a barlavento"  → +0,1 a +0,8 conforme `razao_areas`
                                             (área da abertura / soma das demais),
                                             interpolado entre 1; 1,5; 2; 3 e ≥ 6
        "abertura dominante a sotavento"
        "abertura dominante em face paralela" → C_pi = C_e da face onde está a
                                             abertura, informado em `ce_face`
    """
    k = _chave(aberturas)
    if k in ("duas faces opostas", "duas faces opostas permeaveis", "fechado",
             "portoes nos dois oitoes", "frestas"):
        return [CasoCpi(+0.2, "C_pi = +0,2",
                        "duas faces opostas igualmente permeáveis, vento perpendicular "
                        "a uma face permeável"),
                CasoCpi(-0.3, "C_pi = −0,3",
                        "duas faces opostas igualmente permeáveis, vento perpendicular "
                        "a uma face impermeável")]
    if k in ("quatro faces permeaveis", "quatro faces", "permeavel"):
        return [CasoCpi(-0.3, "C_pi = −0,3", "quatro faces igualmente permeáveis (o mais nocivo)"),
                CasoCpi(0.0, "C_pi = 0", "quatro faces igualmente permeáveis (o mais nocivo)")]
    if k in ("estanque", "edificacao estanque", "janelas fixas"):
        return [CasoCpi(-0.2, "C_pi = −0,2", "edificação efetivamente estanque, janelas fixas"),
                CasoCpi(0.0, "C_pi = 0", "edificação efetivamente estanque, janelas fixas")]
    if k in ("abertura dominante a barlavento", "abertura dominante barlavento",
             "portao aberto a barlavento", "portao a barlavento"):
        if razao_areas is None:
            raise ErroDeDados("para abertura dominante a barlavento informe `razao_areas` = "
                              "área da abertura dominante ÷ soma das áreas das demais "
                              "aberturas (1; 1,5; 2; 3; ≥ 6 na Tabela do item 6.2.5)")
        r = float(razao_areas)
        if r <= 0:
            raise ErroDeDados("`razao_areas` deve ser positiva")
        v = _interp(r, _RAZOES_ABERTURA, _CPI_ABERTURA)
        extra = ""
        if r < 1.0:
            extra = (" (razão < 1: a abertura não é dominante — adotado o menor valor "
                     "tabelado; verifique também o caso de permeabilidade uniforme)")
        return [CasoCpi(v, f"C_pi = {fmt(v, 2)}",
                        f"abertura dominante a barlavento, razão de áreas {fmt(r, 2)}{extra}",
                        "NBR 6123, item 6.2.5")]
    if k in ("abertura dominante a sotavento", "abertura dominante sotavento",
             "portao aberto a sotavento", "abertura dominante em face paralela",
             "abertura dominante face paralela", "abertura em face paralela"):
        if ce_face is None:
            raise ErroDeDados("para abertura dominante a sotavento ou em face paralela ao "
                              "vento, C_pi é igual ao C_e externo da face onde está a "
                              "abertura: informe `ce_face`")
        v = float(ce_face)
        return [CasoCpi(v, f"C_pi = {fmt(v, 2)}",
                        "abertura dominante a sotavento ou em face paralela: C_pi = C_e da "
                        "face onde está a abertura", "NBR 6123, item 6.2.5")]
    raise ErroDeDados(f"situação de permeabilidade desconhecida: '{aberturas}'. Disponíveis: "
                      + ", ".join(sorted(ABERTURAS)))


# --- pressões efetivas no galpão -------------------------------------------

@dataclass(frozen=True)
class Pressao:
    """Pressão efetiva em uma superfície, para uma direção de vento e um C_pi."""
    direcao: str
    superficie: str
    letra: str
    zona: str
    Ce: float
    Cpi: float
    caso_cpi: str
    p: float                      # kN/m²  (+ pressão, − sucção)
    local: bool = False

    @property
    def rotulo(self) -> str:
        return f"{self.superficie} ({self.letra})" if self.letra else self.superficie

    @property
    def succao(self) -> bool:
        return self.p < 0

    def texto(self) -> str:
        return (f"vento {self.direcao} · {self.rotulo} · C_e = {fmt(self.Ce, 2)} · "
                f"{self.caso_cpi} → p = {fmt(self.p, 2)} kN/m²")


@dataclass
class VentoGalpao:
    """Resultado completo do vento sobre um galpão: fatores, q, C_e, C_pi e pressões."""
    V0: float
    S1: float
    S2: float
    S3: float
    Vk: float
    q: float                                     # kN/m²
    categoria: str
    classe: str
    z: float
    grupo: int
    coeficientes: CoeficientesGalpao
    casos_cpi: List[CasoCpi] = field(default_factory=list)
    pressoes: List[Pressao] = field(default_factory=list)
    passos: List[Passo] = field(default_factory=list)
    observacoes: List[str] = field(default_factory=list)
    dados: dict = field(default_factory=dict)

    # -- consultas ---------------------------------------------------------
    def filtrar(self, superficie=None, direcao=None, cpi=None,
                local: Optional[bool] = None) -> List[Pressao]:
        r = self.pressoes
        if direcao is not None:
            d = _direcao(direcao)
            r = [p for p in r if p.direcao == d]
        if superficie is not None:
            k = _chave(superficie)
            r = [p for p in r if k in _chave(p.superficie) or k == _chave(p.letra)]
        if cpi is not None:
            r = [p for p in r if abs(p.Cpi - float(cpi)) < 1e-9]
        if local is not None:
            r = [p for p in r if p.local == local]
        return r

    def pressao(self, superficie, direcao, cpi) -> float:
        """Pressão efetiva (kN/m²) de uma superfície, direção e C_pi."""
        r = self.filtrar(superficie, direcao, cpi)
        if not r:
            raise ErroDeDados(f"não há pressão calculada para '{superficie}' com vento "
                              f"{direcao} e C_pi = {fmt(float(cpi), 2)}")
        if len(r) > 1:
            raise ErroDeDados(f"'{superficie}' casa com mais de uma superfície: "
                              + ", ".join(p.rotulo for p in r))
        return r[0].p

    def envoltoria(self, superficie, direcao=None, incluir_local: bool = False) -> Tuple[float, float]:
        """(pressão máxima, sucção máxima) de uma superfície entre todos os casos."""
        r = self.filtrar(superficie, direcao, local=None if incluir_local else False)
        if not r:
            raise ErroDeDados(f"superfície desconhecida: '{superficie}'")
        return (max(p.p for p in r), min(p.p for p in r))

    def critica(self, incluir_local: bool = False) -> Pressao:
        """A maior sucção de todo o galpão — a que dimensiona terças e fixações."""
        r = [p for p in self.pressoes if incluir_local or not p.local]
        return min(r, key=lambda p: p.p)

    def tabela(self, incluir_local: bool = False) -> List[dict]:
        return [{"direção": p.direcao, "superfície": p.rotulo, "zona": p.zona,
                 "Ce": p.Ce, "Cpi": p.Cpi, "p (kN/m²)": p.p}
                for p in self.pressoes if incluir_local or not p.local]


def pressoes_galpao(b: float, a: float, h: float, theta_graus: float,
                    V0=None, cidade=None, categoria="II", classe="B",
                    z: Optional[float] = None, S1: float = 1.0, grupo: int = 2,
                    aberturas="duas faces opostas",
                    razao_areas: Optional[float] = None,
                    ce_face_abertura: Optional[float] = None,
                    S2: Optional[float] = None,
                    casos_cpi: Optional[Sequence[CasoCpi]] = None) -> VentoGalpao:
    """Vento sobre um galpão de duas águas, do V₀ às pressões por superfície.

    Junta as etapas da NBR 6123: V₀ → S₁·S₂·S₃ → V_k → q = 0,613·V_k² →
    C_e (Tabelas 4 e 5) e C_pi (item 6.2) → p = (C_e − C_pi)·q, em kN/m², para
    as duas direções de vento e para cada caso de C_pi.

    Parâmetros principais (m, graus, m/s)
    -------------------------------------
    b, a, h, theta_graus  geometria (b = vão, a = comprimento, h = beiral);
    V0 ou cidade          velocidade básica, direta ou pela tabela de cidades;
    categoria, classe     rugosidade do terreno e dimensão da edificação (S₂);
    z                     altura de referência de S₂; por omissão a altura da
                          cumeeira, h + (b/2)·tg θ, a favor da segurança;
    S1, grupo             fator topográfico e grupo do fator estatístico S₃;
    aberturas             situação de permeabilidade (ver `coeficiente_pressao_interna`);
    S2                    sobrepõe o S₂ calculado (o Capítulo 16 do manual, por
                          exemplo, adota o valor a 10 m para toda a estrutura);
    casos_cpi             lista de CasoCpi para sobrepor os casos padrão.

    Devolve um `VentoGalpao`, com os fatores, a memória de cálculo (`passos`),
    os coeficientes e a lista de pressões — é o que o orquestrador do galpão e o
    memorial consomem.
    """
    if V0 is None and cidade is None:
        raise ErroDeDados("informe V₀ (m/s) ou a cidade para obter a velocidade básica")
    v0 = velocidade_basica(V0 if V0 is not None else cidade)
    cat, cl = _categoria(categoria), _classe(classe)
    coef = coeficientes_pressao_galpao(b, a, h, theta_graus)
    if z is None:
        z = h + (b / 2.0) * math.tan(math.radians(float(theta_graus)))
    s2 = fator_s2(cat, cl, z) if S2 is None else float(S2)
    s3 = fator_s3(grupo)
    if isinstance(grupo, str):                      # o rótulo do grupo vira o número
        grupo = next(g for g, (v, _) in GRUPOS_S3.items() if abs(v - s3) < 1e-9)
    vk = velocidade_caracteristica(v0, S1, s2, s3)
    q = pressao_dinamica(vk)

    casos = list(casos_cpi) if casos_cpi else coeficiente_pressao_interna(
        aberturas, razao_areas=razao_areas, ce_face=ce_face_abertura)

    pressoes = [Pressao(c.direcao, c.superficie, c.letra, c.zona, c.Ce, caso.valor,
                        caso.nome, pressao_efetiva(c.Ce, caso.valor, q), c.local)
                for c in coef.coeficientes for caso in casos]

    b_s2, p_s2 = PARAMETROS_S2[(cat, cl)]
    passos = [
        Passo("Velocidade básica do vento", formula="V<sub>0</sub>",
              conta=str(cidade) if cidade else "informada",
              valor=fmt(v0, 1, "m/s"), norma="NBR 6123, item 5.1 (mapa de isopletas)"),
        Passo("Fator topográfico", formula="S<sub>1</sub>", conta="",
              valor=fmt(S1, 2), norma="NBR 6123, item 5.2"),
        Passo(f"Fator de rugosidade (categoria {cat}, classe {cl}, z = {fmt(z, 1)} m)",
              formula="S<sub>2</sub> = b·F<sub>r</sub>·(z/10)<sup>p</sup>",
              conta=(f"{fmt(b_s2, 2)} · {fmt(FR_S2[cl], 2)} · ({fmt(z, 1)}/10)"
                     f"<sup>{fmt(p_s2, 3)}</sup>" if S2 is None else "valor adotado"),
              valor=fmt(s2, 3), norma="NBR 6123, item 5.3 e Tabela 1"),
        Passo(f"Fator estatístico (grupo {grupo})", formula="S<sub>3</sub>",
              conta=GRUPOS_S3[int(grupo)][1], valor=fmt(s3, 2),
              norma="NBR 6123, item 5.4 e Tabela 3"),
        Passo("Velocidade característica",
              formula="V<sub>k</sub> = V<sub>0</sub>·S<sub>1</sub>·S<sub>2</sub>·S<sub>3</sub>",
              conta=f"{fmt(v0, 1)} × {fmt(S1, 2)} × {fmt(s2, 3)} × {fmt(s3, 2)}",
              valor=fmt(vk, 2, "m/s"), norma="NBR 6123, item 4.2"),
        Passo("Pressão dinâmica", formula="q = 0,613·V<sub>k</sub>²",
              conta=f"0,613 × {fmt(vk, 2)}²",
              valor=f"{fmt(q * 1000, 0, 'N/m²')} = {fmt(q, 3, 'kN/m²')}",
              norma="NBR 6123, item 4.2"),
        Passo("Proporções da edificação",
              formula="h/b · a/b · θ",
              conta=f"{fmt(h, 1)}/{fmt(b, 1)} · {fmt(a, 1)}/{fmt(b, 1)} · {fmt(theta_graus, 1)}°",
              valor=f"h/b = {fmt(coef.h_b, 2)}; a/b = {fmt(coef.a_b, 2)}",
              norma="NBR 6123, Tabelas 4 e 5"),
        Passo("Coeficientes de pressão interna considerados", formula="C<sub>pi</sub>",
              conta=" e ".join(c.descricao for c in casos),
              valor=" / ".join(fmt(c.valor, 2) for c in casos),
              norma="NBR 6123, item 6.2"),
        Passo("Pressão efetiva em cada superfície",
              formula="p = (C<sub>e</sub> − C<sub>pi</sub>)·q",
              conta=f"q = {fmt(q, 3)} kN/m²",
              valor=f"maior sucção: {fmt(min(p.p for p in pressoes if not p.local), 2, 'kN/m²')}",
              norma="NBR 6123, item 6.1"),
    ]
    obs = list(coef.observacoes)
    if S2 is not None:
        obs.append(f"S₂ = {fmt(s2, 3)} adotado diretamente (não calculado pela Tabela 1).")
    obs.append(f"S₂ calculado na altura z = {fmt(z, 2)} m; o mesmo valor foi usado em todas "
               "as superfícies (prática usual em galpões — manual, Tabela 5.5).")
    return VentoGalpao(v0, S1, s2, s3, vk, q, cat, cl, float(z), int(grupo),
                       coef, casos, pressoes, passos, obs,
                       {"b": b, "a": a, "h": h, "theta": float(theta_graus),
                        "h_cumeeira": h + (b / 2.0) * math.tan(math.radians(float(theta_graus)))})


# ===========================================================================
# 3. COMBINAÇÕES — NBR 8681:2003 e NBR 8800:2008 (Tabelas 1 e 2)
# ===========================================================================

# NBR 8800:2008, Tabela 1 — coeficientes γ_f = γ_f1·γ_f3 das ações permanentes
# diretas, valor desfavorável por tipo de combinação última.
# (normais, especiais ou de construção, excepcionais)
GAMA_G: Dict[str, Tuple[float, float, float]] = {
    "metálica": (1.25, 1.15, 1.10),
    "pré-moldada": (1.30, 1.20, 1.15),
    "moldada no local": (1.35, 1.25, 1.15),
    "industrializado com adições": (1.40, 1.30, 1.20),
    "geral": (1.50, 1.40, 1.30),
    "indireta": (1.20, 1.20, 0.00),
}
GAMA_G_DESCRICAO = {
    "metálica": "peso próprio de estruturas metálicas (pequena variabilidade)",
    "pré-moldada": "peso próprio de estruturas pré-moldadas",
    "moldada no local": "peso próprio moldado no local, elementos construtivos "
                        "industrializados e empuxos permanentes",
    "industrializado com adições": "elementos construtivos industrializados com adições in loco",
    "geral": "elementos construtivos em geral e equipamentos (grande variabilidade)",
    "indireta": "ações permanentes indiretas (recalques, retração)",
}
# Valor favorável (a ação alivia o efeito verificado).
GAMA_G_FAVORAVEL: Dict[str, float] = {k: (0.0 if k == "indireta" else 1.0) for k in GAMA_G}

# NBR 8800:2008, Tabela 1 — ações variáveis.
GAMA_Q: Dict[str, Tuple[float, float, float]] = {
    "temperatura": (1.20, 1.00, 1.00),
    "vento": (1.40, 1.20, 1.00),
    "truncada": (1.20, 1.10, 1.00),
    "sobrecarga": (1.50, 1.30, 1.00),
    "ponte rolante": (1.50, 1.30, 1.00),
}

# NBR 8800:2008, Tabela 2 — fatores de combinação ψ₀ e de redução ψ₁ e ψ₂.
PSI: Dict[str, Tuple[float, float, float]] = {
    "residencial": (0.5, 0.4, 0.3),
    "comercial": (0.7, 0.6, 0.4),
    "depósito": (0.8, 0.7, 0.6),
    "cobertura": (0.8, 0.7, 0.6),
    "vento": (0.6, 0.3, 0.0),
    "temperatura": (0.6, 0.5, 0.3),
    "passarela": (0.6, 0.4, 0.3),
    "ponte rolante": (1.0, 0.8, 0.5),
}
PSI_DESCRICAO = {
    "residencial": "locais sem predominância de equipamentos fixos nem de concentração "
                   "de pessoas (residências)",
    "comercial": "locais com predominância de equipamentos fixos ou de concentração de "
                 "pessoas (escritórios, comércio, escolas, edifícios públicos)",
    "depósito": "bibliotecas, arquivos, depósitos, oficinas e garagens",
    "cobertura": "sobrecargas em coberturas",
    "vento": "vento (pressão dinâmica)",
    "temperatura": "variações uniformes de temperatura",
    "passarela": "cargas móveis e efeitos dinâmicos em passarelas de pedestres",
    "ponte rolante": "cargas móveis e efeitos dinâmicos de pontes rolantes",
}

TIPOS_COMBINACAO = {"normais": 0, "especiais": 1, "construção": 1, "excepcionais": 2}


def _indice_combinacao(tipo: str) -> int:
    k = _chave(tipo)
    for nome, i in TIPOS_COMBINACAO.items():
        if k == _chave(nome):
            return i
    raise ErroDeDados(f"tipo de combinação última desconhecido: '{tipo}'. Use "
                      "'normais', 'especiais', 'construção' ou 'excepcionais'.")


def gama_f(tipo: str, subtipo: str = "", combinacao: str = "normais",
           favoravel: bool = False) -> float:
    """Coeficiente de ponderação γ_f de uma ação (NBR 8800:2008, Tabela 1)."""
    i = _indice_combinacao(combinacao)
    t = _chave(tipo)
    if t in ("permanente", "permanentes", "g"):
        chave = _busca_chave(GAMA_G, subtipo or "geral", "tipo de ação permanente")
        return GAMA_G_FAVORAVEL[chave] if favoravel else GAMA_G[chave][i]
    if t in ("vento", "variavel", "variaveis", "q"):
        padrao = "vento" if t == "vento" else "sobrecarga"
        chave = _busca_chave(GAMA_Q, subtipo or padrao, "tipo de ação variável")
        return 0.0 if favoravel else GAMA_Q[chave][i]
    raise ErroDeDados(f"tipo de ação desconhecido: '{tipo}'. "
                      "Use 'permanente', 'variavel' ou 'vento'.")


def _busca_chave(tabela: dict, nome, rotulo: str) -> str:
    k = _chave(nome)
    for c in tabela:
        if _chave(c) == k:
            return c
    parciais = [c for c in tabela if k and (k in _chave(c) or _chave(c) in k)]
    if len(parciais) == 1:
        return parciais[0]
    raise ErroDeDados(f"{rotulo} desconhecido: '{nome}'. Disponíveis: "
                      + ", ".join(sorted(tabela)))


def psi(uso: str) -> Tuple[float, float, float]:
    """(ψ₀, ψ₁, ψ₂) de uma ação variável (NBR 8800:2008, Tabela 2)."""
    return PSI[_busca_chave(PSI, uso, "ação variável (ψ)")]


@dataclass
class Acao:
    """Uma ação característica, com seus coeficientes de ponderação.

    nome     rótulo que aparece no memorial ("PP", "Sobrecarga", "Vento").
    tipo     "permanente", "variavel" ou "vento".
    valor    valor característico, com **sinal** (o sinal define o sentido do
             efeito: positivo e negativo são sentidos opostos da mesma grandeza,
             por exemplo carga para baixo e sucção para cima).
    subtipo  linha da Tabela 1 da NBR 8800 ("metálica", "geral", "sobrecarga",
             "ponte rolante", "temperatura"...). Por omissão, o valor mais
             conservador do grupo.
    psi      linha da Tabela 2 da NBR 8800 ("cobertura", "comercial", "vento"...).
    favoravel  força a classificação favorável/desfavorável da ação permanente;
             `None` (padrão) deixa que o sentido verificado decida.
    """
    nome: str
    tipo: str = "permanente"
    valor: float = 0.0
    subtipo: str = ""
    psi: str = ""
    favoravel: Optional[bool] = None

    def __post_init__(self):
        t = _chave(self.tipo)
        if t in ("permanente", "permanentes", "g"):
            self.tipo = "permanente"
            self.subtipo = _busca_chave(GAMA_G, self.subtipo or "geral",
                                        "tipo de ação permanente")
        elif t in ("vento", "v"):
            self.tipo = "vento"
            self.subtipo = "vento"
            self.psi = self.psi or "vento"
        elif t in ("variavel", "variaveis", "q"):
            self.tipo = "variavel"
            self.subtipo = _busca_chave(GAMA_Q, self.subtipo or "sobrecarga",
                                        "tipo de ação variável")
            self.psi = self.psi or ("ponte rolante" if self.subtipo == "ponte rolante"
                                    else "depósito")
        else:
            raise ErroDeDados(f"tipo de ação desconhecido: '{self.tipo}'. "
                              "Use 'permanente', 'variavel' ou 'vento'.")
        if self.tipo != "permanente":
            self.psi = _busca_chave(PSI, self.psi, "ação variável (ψ)")
        self.valor = float(self.valor)

    @property
    def permanente(self) -> bool:
        return self.tipo == "permanente"

    @property
    def rotulo(self) -> str:
        if self.tipo == "vento" and self.valor < 0 and "sucção" not in self.nome.lower():
            return f"{self.nome} (sucção)"
        return self.nome

    def gama(self, combinacao: str = "normais", favoravel: bool = False) -> float:
        return gama_f(self.tipo, self.subtipo, combinacao, favoravel)

    @property
    def psi0(self) -> float:
        return 0.0 if self.permanente else psi(self.psi)[0]

    @property
    def psi1(self) -> float:
        return 0.0 if self.permanente else psi(self.psi)[1]

    @property
    def psi2(self) -> float:
        return 0.0 if self.permanente else psi(self.psi)[2]


@dataclass
class Parcela:
    """Uma ação dentro de uma combinação, com o coeficiente que a multiplica."""
    acao: str
    gama: float
    psi: float
    valor: float
    papel: str                    # "permanente desfavorável", "principal", "secundária"...
    norma: str = ""

    @property
    def coef(self) -> float:
        return self.gama * self.psi

    @property
    def contribuicao(self) -> float:
        return self.coef * self.valor

    def texto(self) -> str:
        if abs(self.psi - 1.0) > 1e-9:
            if abs(self.gama - 1.0) < 1e-9:            # ELS: γ_f = 1,0, só o ψ aparece
                return f"{_fc(self.psi)}·{self.acao}"
            return f"{_fc(self.gama)}·{_fc(self.psi)}·{self.acao}"
        return f"{_fc(self.gama)}·{self.acao}"

    def passo(self) -> Passo:
        return Passo(f"{self.acao} — {self.papel}",
                     formula=self.texto(),
                     conta=(f"{_fc(self.gama)} × {_fc(self.psi)} × {fmt(self.valor, 3)}"
                            if abs(self.psi - 1.0) > 1e-9
                            else f"{_fc(self.gama)} × {fmt(self.valor, 3)}"),
                     valor=fmt(self.contribuicao, 3), norma=self.norma)


@dataclass
class Combinacao:
    """Uma combinação de ações, capaz de se explicar no memorial."""
    nome: str
    tipo: str                     # "última normal", "serviço rara", ...
    sentido: str                  # "+" ou "−"
    principal: str
    parcelas: List[Parcela] = field(default_factory=list)
    norma: str = "NBR 8681:2003 / NBR 8800:2008, item 4.7"

    @property
    def total(self) -> float:
        return sum(p.contribuicao for p in self.parcelas)

    def __float__(self) -> float:
        return self.total

    @property
    def expressao(self) -> str:
        return " + ".join(p.texto() for p in self.parcelas)

    @property
    def titulo(self) -> str:
        return f"{self.nome}: {self.expressao}"

    def texto(self, unidade: str = "") -> str:
        return f"{self.titulo} = {fmt(self.total, 2, unidade)}"

    def passos(self, unidade: str = "") -> List[Passo]:
        ps = [p.passo() for p in self.parcelas]
        ps.append(Passo(f"{self.nome} — total ({self.tipo})",
                        formula=self.expressao,
                        conta=" + ".join(fmt(p.contribuicao, 3) for p in self.parcelas),
                        valor=fmt(self.total, 3, unidade), norma=self.norma))
        return ps


def _sinal(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _prepara(acoes: Sequence[Acao]) -> List[Acao]:
    if not acoes:
        raise ErroDeDados("nenhuma ação informada para combinar")
    for a in acoes:
        if not isinstance(a, Acao):
            raise ErroDeDados(f"esperava uma Acao e recebi {type(a).__name__}: {a!r}")
    return list(acoes)


def combinacoes_ultimas(acoes: Sequence[Acao], tipo: str = "normais",
                        sentidos: Sequence[str] = ("+", "-"),
                        prefixo: str = "C") -> List[Combinacao]:
    """Combinações últimas (ELU) — NBR 8681, item 5.1.3; NBR 8800, item 4.7.7.2.

        F_d = Σ γ_gi·F_Gi,k + γ_q1·F_Q1,k + Σ γ_qj·ψ_0j·F_Qj,k

    Para cada **sentido** verificado (o sinal do efeito que se quer maximizar):

    * cada ação variável que atua naquele sentido entra uma vez como principal
      (com γ_q integral) enquanto as demais entram reduzidas por ψ₀;
    * as ações variáveis que aliviam o efeito **não entram** (NBR 8681: a ação
      variável só é considerada quando desfavorável);
    * cada ação permanente entra com γ_g desfavorável quando age no sentido
      verificado e com **γ_g = 1,0 (favorável) quando alivia** — é esse o caso da
      combinação de levantamento 1,0·PP + 1,4·V_sucção, que governa terças,
      tesouras e chumbadores de galpões leves (manual, item 5.7.1).

    `sentidos` aceita "+" (maximiza o efeito positivo, tipicamente a gravidade)
    e "-" (maximiza o efeito negativo, tipicamente a sucção).
    """
    acoes = _prepara(acoes)
    _indice_combinacao(tipo)
    rotulo = {"normais": "última normal", "especiais": "última especial",
              "construção": "última de construção",
              "excepcionais": "última excepcional"}[_busca_chave(TIPOS_COMBINACAO, tipo, "tipo")]
    combs: List[Combinacao] = []
    for s in sentidos:
        sn = 1 if str(s).strip() in ("+", "1", "positivo") else -1
        rot_sentido = "+" if sn > 0 else "−"
        permanentes = []
        for a in (x for x in acoes if x.permanente):
            fav = a.favoravel if a.favoravel is not None else (_sinal(a.valor) * sn < 0)
            permanentes.append(Parcela(a.rotulo, a.gama(tipo, fav), 1.0, a.valor,
                                       "permanente favorável" if fav else "permanente desfavorável",
                                       "NBR 8800, Tabela 1"))
        variaveis = [a for a in acoes if not a.permanente and _sinal(a.valor) * sn > 0]
        if not variaveis:
            combs.append(Combinacao(f"{prefixo}{len(combs) + 1}", rotulo, rot_sentido,
                                    "—", list(permanentes)))
            continue
        for principal in variaveis:
            ps = list(permanentes)
            ps.append(Parcela(principal.rotulo, principal.gama(tipo), 1.0, principal.valor,
                              "variável principal", "NBR 8800, Tabela 1"))
            for outra in variaveis:
                if outra is principal:
                    continue
                ps.append(Parcela(outra.rotulo, outra.gama(tipo), outra.psi0, outra.valor,
                                  "variável secundária (ψ₀)", "NBR 8800, Tabelas 1 e 2"))
            combs.append(Combinacao(f"{prefixo}{len(combs) + 1}", rotulo, rot_sentido,
                                    principal.rotulo, ps))
    return combs


def combinacoes_servico(acoes: Sequence[Acao],
                        sentidos: Sequence[str] = ("+", "-"),
                        tipos: Sequence[str] = ("quase permanente", "frequente", "rara"),
                        prefixo: str = "S") -> List[Combinacao]:
    """Combinações de serviço (ELS) — NBR 8681, item 5.1.4; NBR 8800, item 4.7.7.3.

        quase permanente:  F_ser = Σ F_Gi,k + Σ ψ_2j·F_Qj,k
        frequente:         F_ser = Σ F_Gi,k + ψ_11·F_Q1,k + Σ ψ_2j·F_Qj,k
        rara:              F_ser = Σ F_Gi,k + F_Q1,k + Σ ψ_1j·F_Qj,k

    Todos os γ_f valem 1,0. Como no ELU, para cada sentido verificado entram
    apenas as ações variáveis desfavoráveis àquele sentido, e as frequentes e
    raras geram uma combinação por ação variável principal.
    """
    acoes = _prepara(acoes)
    validos = ("quase permanente", "frequente", "rara")
    combs: List[Combinacao] = []
    for s in sentidos:
        sn = 1 if str(s).strip() in ("+", "1", "positivo") else -1
        rot_sentido = "+" if sn > 0 else "−"
        permanentes = [Parcela(a.rotulo, 1.0, 1.0, a.valor, "permanente (γ_f = 1,0)",
                               "NBR 8800, Tabela 1 (ELS)")
                       for a in acoes if a.permanente]
        variaveis = [a for a in acoes if not a.permanente and _sinal(a.valor) * sn > 0]
        for t in tipos:
            k = _chave(t)
            if k not in [_chave(v) for v in validos]:
                raise ErroDeDados(f"combinação de serviço desconhecida: '{t}'. "
                                  "Use 'quase permanente', 'frequente' ou 'rara'.")
            if k == _chave("quase permanente"):
                ps = list(permanentes) + [
                    Parcela(a.rotulo, 1.0, a.psi2, a.valor, "variável (ψ₂)",
                            "NBR 8800, Tabela 2") for a in variaveis]
                combs.append(Combinacao(f"{prefixo}{len(combs) + 1}", "serviço quase permanente",
                                        rot_sentido, "—", ps))
                continue
            if not variaveis:
                continue
            for principal in variaveis:
                ps = list(permanentes)
                if k == _chave("frequente"):
                    ps.append(Parcela(principal.rotulo, 1.0, principal.psi1, principal.valor,
                                      "variável principal (ψ₁)", "NBR 8800, Tabela 2"))
                    ps += [Parcela(o.rotulo, 1.0, o.psi2, o.valor, "variável (ψ₂)",
                                   "NBR 8800, Tabela 2") for o in variaveis if o is not principal]
                    nome_tipo = "serviço frequente"
                else:
                    ps.append(Parcela(principal.rotulo, 1.0, 1.0, principal.valor,
                                      "variável principal (valor característico)",
                                      "NBR 8681, item 5.1.4"))
                    ps += [Parcela(o.rotulo, 1.0, o.psi1, o.valor, "variável (ψ₁)",
                                   "NBR 8800, Tabela 2") for o in variaveis if o is not principal]
                    nome_tipo = "serviço rara"
                combs.append(Combinacao(f"{prefixo}{len(combs) + 1}", nome_tipo, rot_sentido,
                                        principal.rotulo, ps))
    return combs


def envoltoria(combinacoes: Sequence[Combinacao]) -> Tuple[Combinacao, Combinacao]:
    """(combinação de maior efeito positivo, combinação de maior efeito negativo)."""
    if not combinacoes:
        raise ErroDeDados("nenhuma combinação para envoltória")
    return (max(combinacoes, key=lambda c: c.total),
            min(combinacoes, key=lambda c: c.total))


def critica(combinacoes: Sequence[Combinacao]) -> Combinacao:
    """A combinação de maior efeito em módulo."""
    if not combinacoes:
        raise ErroDeDados("nenhuma combinação para avaliar")
    return max(combinacoes, key=lambda c: abs(c.total))


# ===========================================================================
# catálogo para a interface web
# ===========================================================================

def listar() -> dict:
    """Tabelas consultáveis, no formato que a interface web consome."""
    return {
        "pesos": [{"nome": e.nome, "valor": e.valor, "min": e.minimo, "max": e.maximo,
                   "unidade": e.unidade, "obs": e.obs} for e in PESOS.values()],
        "pesos_especificos": PESOS_ESPECIFICOS,
        "sobrecargas": [{"nome": s.nome, "valor": s.valor, "min": s.minimo, "max": s.maximo,
                         "psi": s.psi, "obs": s.obs} for s in SOBRECARGAS.values()],
        "cidades": [{"nome": c.nome, "V0": c.V0} for c in V0_CIDADES.values()],
        "categorias_s2": CATEGORIAS_S2,
        "classes_s2": CLASSES_S2,
        "grupos_s3": {g: {"S3": v, "descricao": d} for g, (v, d) in GRUPOS_S3.items()},
        "aberturas": ABERTURAS,
        "gama_g": {k: {"normais": v[0], "especiais": v[1], "excepcionais": v[2],
                       "favoravel": GAMA_G_FAVORAVEL[k], "descricao": GAMA_G_DESCRICAO[k]}
                   for k, v in GAMA_G.items()},
        "gama_q": {k: {"normais": v[0], "especiais": v[1], "excepcionais": v[2]}
                   for k, v in GAMA_Q.items()},
        "psi": {k: {"psi0": v[0], "psi1": v[1], "psi2": v[2],
                    "descricao": PSI_DESCRICAO[k]} for k, v in PSI.items()},
    }
