# -*- coding: utf-8 -*-
"""Análise estrutural de pórticos planos e treliças pelo método da rigidez direta.

Módulo de análise linear elástica de primeira ordem, com amplificação dos esforços
para os efeitos de segunda ordem pelo método B1/B2 do Anexo D da NBR 8800:2008.

Escopo e limitações (declarados explicitamente, conforme o princípio 1 do guia):
    * análise **plana** (pórtico plano, 3 graus de liberdade por nó: ux, uy, rz);
    * material **elástico linear**, seções prismáticas em cada barra;
    * pequenos deslocamentos (a 2ª ordem entra por amplificação, não por geometria
      atualizada); não há análise P-Δ rigorosa nem plastificação;
    * sem efeito de cisalhamento na deformação (viga de Euler-Bernoulli) e sem
      variação de temperatura ou recalque de apoio.

Unidades (obrigatórias em todo o sistema — ver GUIA_SISTEMA.md):
    comprimento  cm
    força        kN
    momento      kN·cm
    carga distribuída  kN/cm
    tensão / módulo    kN/cm²

Convenções de sinal
-------------------
Eixos globais: x para a direita, y para cima, rotação anti-horária positiva.

Esforços internos da barra, medidos ao longo do eixo local (do nó inicial para o
nó final), com o eixo local y obtido girando o eixo local x de +90°:

    N  tração positiva;
    V  positivo quando gira o trecho à esquerda do corte no sentido horário
       (é o V que satisfaz V = dM/dx);
    M  positivo quando traciona a face do lado **local −y** da barra.

Para uma barra definida da esquerda para a direita, a face local −y é a face
inferior: M positivo traciona a face inferior (convenção usual de viga). Os
geradores de modelo deste módulo (`portico_galpao`) orientam as barras de modo que
M positivo tracione a face inferior da viga e a face **interna** do pilar, que é a
convenção adotada no Capítulo 16 do manual.

Sem dependências externas: a álgebra linear é eliminação de Gauss com pivotamento
parcial escrita à mão sobre listas (GUIA_SISTEMA.md, "Estilo do código").
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .base import E as E_ACO
from .base import ErroDeDados, Passo, fmt

__all__ = [
    "No", "Barra", "Carga", "Modelo",
    "Diagrama", "Extremo", "ResultadoBarra", "ResultadoAnalise",
    "ExtremoEnvoltoria", "EnvoltoriaBarra", "Envoltoria",
    "resolver", "envoltoria",
    "Andar", "DadosSegundaOrdem", "ResultadoSegundaOrdem",
    "coeficiente_Cm", "amplificar",
    "portico_galpao", "viga_continua", "trelica", "Misula",
    "Conferencia", "conferir_por_formula", "FORMULAS",
    "resolver_sistema",
]

Ref = Union[int, str]

# Tolerâncias numéricas (relativas — nunca absolutas, para não depender da escala)
TOL_PIVO = 1e-12        # fração do maior coeficiente da coluna: abaixo disso, pivô nulo
TOL_RIGIDEZ = 1e-12     # fração da maior rigidez: abaixo disso, grau de liberdade solto
TOL_COMPRIMENTO = 1e-6  # cm — comprimento mínimo de barra


# =====================================================================================
# 1. Álgebra linear — Gauss com pivotamento parcial, escrito à mão sobre listas
# =====================================================================================

def resolver_sistema(A: List[List[float]], b: List[float],
                     rotulos: Optional[Sequence[str]] = None) -> List[float]:
    """Resolve A·x = b por eliminação de Gauss com pivotamento parcial.

    `A` é modificada apenas em cópia. `rotulos` dá nome às incógnitas para que a
    mensagem de erro de matriz singular aponte o grau de liberdade culpado.
    Levanta `ErroDeDados` se a matriz for singular (estrutura hipostática).
    """
    n = len(A)
    if n == 0:
        return []
    if len(b) != n:
        raise ErroDeDados(f"Sistema inconsistente: matriz {n}×{n} e vetor de {len(b)} termos.")

    # maior valor de cada coluna, para um critério de pivô nulo independente da escala
    escala = [max((abs(A[i][j]) for i in range(n)), default=0.0) or 1.0 for j in range(n)]
    M = [list(A[i]) + [b[i]] for i in range(n)]

    for k in range(n):
        p = k
        maior = abs(M[k][k])
        for i in range(k + 1, n):
            if abs(M[i][k]) > maior:
                maior, p = abs(M[i][k]), i
        if maior <= TOL_PIVO * escala[k]:
            nome = rotulos[k] if rotulos and k < len(rotulos) else f"incógnita {k}"
            raise ErroDeDados(
                "Matriz de rigidez singular: a estrutura é hipostática (um mecanismo) "
                f"no grau de liberdade {nome}. Acrescente apoio, barra ou remova a rótula "
                "que deixou o nó livre para girar/transladar.")
        if p != k:
            M[k], M[p] = M[p], M[k]
        pivo = M[k][k]
        linha_k = M[k]
        for i in range(k + 1, n):
            linha_i = M[i]
            if linha_i[k] == 0.0:
                continue
            f = linha_i[k] / pivo
            linha_i[k] = 0.0
            for j in range(k + 1, n + 1):
                if linha_k[j] != 0.0:
                    linha_i[j] -= f * linha_k[j]

    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = M[i][n]
        linha = M[i]
        for j in range(i + 1, n):
            if linha[j] != 0.0:
                s -= linha[j] * x[j]
        x[i] = s / linha[i]
    return x


def _inverter(M: List[List[float]]) -> List[List[float]]:
    """Inversa de uma matriz pequena (1×1 ou 2×2) por Gauss-Jordan."""
    n = len(M)
    A = [list(M[i]) + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(A[i][k]))
        if abs(A[p][k]) == 0.0:
            raise ErroDeDados("Rótula mal posta: a condensação estática da barra é impossível "
                              "(rigidez de rotação nula na extremidade liberada).")
        A[k], A[p] = A[p], A[k]
        pivo = A[k][k]
        for j in range(2 * n):
            A[k][j] /= pivo
        for i in range(n):
            if i == k or A[i][k] == 0.0:
                continue
            f = A[i][k]
            for j in range(2 * n):
                A[i][j] -= f * A[k][j]
    return [linha[n:] for linha in A]


# =====================================================================================
# 2. Modelo — nós, barras, cargas e casos de carga
# =====================================================================================

_APOIOS = {
    "livre":      (False, False, False),
    "movel":      (False, True, False),    # rolete: impede só o deslocamento vertical
    "movel_x":    (False, True, False),
    "movel_y":    (True, False, False),
    "rotulado":   (True, True, False),     # 2º gênero
    "fixo":       (True, True, False),
    "engastado":  (True, True, True),      # 3º gênero
    "engaste":    (True, True, True),
}


def _normaliza_apoio(apoio) -> Tuple[bool, bool, bool]:
    if apoio is None:
        return (False, False, False)
    if isinstance(apoio, str):
        chave = apoio.strip().lower().replace("ó", "o").replace("á", "a").replace("é", "e")
        if chave not in _APOIOS:
            raise ErroDeDados(
                f"Apoio '{apoio}' desconhecido. Use um de {sorted(set(_APOIOS))} "
                "ou a tripla (ux, uy, rz) de restrições.")
        return _APOIOS[chave]
    try:
        ux, uy, rz = apoio
    except (TypeError, ValueError):
        raise ErroDeDados("Apoio deve ser um nome ('rotulado', 'engastado', 'movel', 'livre') "
                          "ou a tripla (ux, uy, rz) de restrições booleanas.")
    return (bool(ux), bool(uy), bool(rz))


@dataclass
class No:
    """Nó do modelo. Coordenadas em cm; `apoio` são as restrições (ux, uy, rz)."""
    x: float
    y: float
    apoio: Any = (False, False, False)
    nome: str = ""

    def __post_init__(self):
        self.x = float(self.x)
        self.y = float(self.y)
        self.apoio = _normaliza_apoio(self.apoio)

    @property
    def restrito_ux(self) -> bool:
        return self.apoio[0]

    @property
    def restrito_uy(self) -> bool:
        return self.apoio[1]

    @property
    def restrito_rz(self) -> bool:
        return self.apoio[2]

    @property
    def apoiado(self) -> bool:
        return any(self.apoio)


@dataclass
class Barra:
    """Barra prismática de pórtico plano entre dois nós.

    A  área da seção (cm²);  I  inércia à flexão no plano (cm⁴);  E  módulo (kN/cm²).
    `rotula_i` / `rotula_f` liberam a rotação na extremidade inicial / final
    (condensação estática — base rotulada, ligação flexível, barra de treliça).
    """
    ni: int
    nf: int
    A: float
    I: float
    E: float = E_ACO
    rotulo: str = ""
    rotula_i: bool = False
    rotula_f: bool = False

    def __post_init__(self):
        self.ni = int(self.ni)
        self.nf = int(self.nf)
        self.A = float(self.A)
        self.I = float(self.I)
        self.E = float(self.E)


DIRECOES = ("perpendicular", "axial", "global_x", "global_y", "projetada_x", "projetada_y")


@dataclass
class Carga:
    """Carga de um caso de carregamento.

    tipo = "nodal"        — Fx, Fy (kN) e Mz (kN·cm) aplicados no nó `alvo`;
    tipo = "distribuida"  — q (kN/cm) uniforme na barra `alvo`, na direção `direcao`;
    tipo = "concentrada"  — P (kN) na barra `alvo`, a `a` cm do nó inicial.

    Direções da carga distribuída (q positivo no sentido do eixo indicado):
        "perpendicular"  eixo local y da barra, por metro de barra (vento em telhado);
        "axial"          eixo local x da barra, por metro de barra;
        "global_x"       eixo global x, por unidade de comprimento da barra;
        "global_y"       eixo global y, por unidade de comprimento da barra;
        "projetada_x"    eixo global x, por unidade de **projeção vertical**;
        "projetada_y"    eixo global y, por unidade de **projeção horizontal**
                         (peso próprio e sobrecarga em viga inclinada: q negativo
                         para carga de cima para baixo).
    A carga concentrada aceita as quatro primeiras direções.
    """
    tipo: str
    alvo: Ref
    Fx: float = 0.0
    Fy: float = 0.0
    Mz: float = 0.0
    q: float = 0.0
    P: float = 0.0
    a: float = 0.0
    direcao: str = "perpendicular"

    @classmethod
    def nodal(cls, no: Ref, Fx: float = 0.0, Fy: float = 0.0, Mz: float = 0.0) -> "Carga":
        return cls("nodal", no, Fx=Fx, Fy=Fy, Mz=Mz)

    @classmethod
    def distribuida(cls, barra: Ref, q: float, direcao: str = "perpendicular") -> "Carga":
        return cls("distribuida", barra, q=q, direcao=direcao)

    @classmethod
    def concentrada(cls, barra: Ref, P: float, a: float,
                    direcao: str = "perpendicular") -> "Carga":
        return cls("concentrada", barra, P=P, a=a, direcao=direcao)


class Modelo:
    """Nós, barras e casos de carga nomeados de uma estrutura plana."""

    def __init__(self, nome: str = ""):
        self.nome = nome
        self.nos: List[No] = []
        self.barras: List[Barra] = []
        self.casos: Dict[str, List[Carga]] = {}
        self.dados: dict = {}        # espaço livre (geometria adotada, rótulos, etc.)

    # ---------------- construção ----------------

    def add_no(self, x: float, y: float, apoio=None, nome: str = "") -> int:
        self.nos.append(No(x, y, apoio, nome))
        return len(self.nos) - 1

    def add_barra(self, ni: Ref, nf: Ref, A: float, I: float, E: float = E_ACO,
                  rotulo: str = "", rotula_i: bool = False, rotula_f: bool = False) -> int:
        self.barras.append(Barra(self.indice_no(ni), self.indice_no(nf), A, I, E,
                                 rotulo, rotula_i, rotula_f))
        return len(self.barras) - 1

    def caso(self, nome: str) -> str:
        """Cria (ou apenas devolve) um caso de carga vazio."""
        self.casos.setdefault(nome, [])
        return nome

    def add_carga(self, caso: str, carga: Carga) -> Carga:
        self.casos.setdefault(caso, []).append(carga)
        return carga

    def nodal(self, caso: str, no: Ref, Fx: float = 0.0, Fy: float = 0.0,
              Mz: float = 0.0) -> Carga:
        return self.add_carga(caso, Carga.nodal(self.indice_no(no), Fx, Fy, Mz))

    def distribuida(self, caso: str, barra: Ref, q: float,
                    direcao: str = "perpendicular") -> Carga:
        if direcao not in DIRECOES:
            raise ErroDeDados(f"Direção de carga '{direcao}' desconhecida. Use uma de {DIRECOES}.")
        return self.add_carga(caso, Carga.distribuida(self.indice_barra(barra), q, direcao))

    def concentrada(self, caso: str, barra: Ref, P: float, a: float,
                    direcao: str = "perpendicular") -> Carga:
        if direcao not in DIRECOES[:4]:
            raise ErroDeDados(
                f"Direção '{direcao}' não vale para carga concentrada. Use uma de {DIRECOES[:4]}.")
        k = self.indice_barra(barra)
        L = self.comprimento(k)
        if not 0.0 <= a <= L:
            raise ErroDeDados(
                f"Carga concentrada fora da barra {barra}: a = {fmt(a, 1, 'cm')} não está "
                f"entre 0 e L = {fmt(L, 1, 'cm')}.")
        return self.add_carga(caso, Carga.concentrada(k, P, a, direcao))

    # ---------------- consultas ----------------

    def indice_no(self, ref: Ref) -> int:
        if isinstance(ref, No):
            return self.nos.index(ref)
        if isinstance(ref, str):
            for i, n in enumerate(self.nos):
                if n.nome == ref:
                    return i
            raise ErroDeDados(f"Nó '{ref}' não existe no modelo. "
                              f"Nós nomeados: {[n.nome for n in self.nos if n.nome]}.")
        i = int(ref)
        if not -len(self.nos) <= i < len(self.nos):
            raise ErroDeDados(f"Nó {i} fora da faixa (o modelo tem {len(self.nos)} nós).")
        return i % len(self.nos) if self.nos else i

    def indice_barra(self, ref: Ref) -> int:
        if isinstance(ref, Barra):
            return self.barras.index(ref)
        if isinstance(ref, str):
            for i, b in enumerate(self.barras):
                if b.rotulo == ref:
                    return i
            raise ErroDeDados(f"Barra '{ref}' não existe no modelo. "
                              f"Barras rotuladas: {[b.rotulo for b in self.barras if b.rotulo]}.")
        i = int(ref)
        if not -len(self.barras) <= i < len(self.barras):
            raise ErroDeDados(f"Barra {i} fora da faixa (o modelo tem {len(self.barras)} barras).")
        return i % len(self.barras) if self.barras else i

    def comprimento(self, barra: Ref) -> float:
        b = self.barras[self.indice_barra(barra)]
        ni, nf = self.nos[b.ni], self.nos[b.nf]
        return math.hypot(nf.x - ni.x, nf.y - ni.y)

    @property
    def ngl(self) -> int:
        return 3 * len(self.nos)

    # ---------------- validação ----------------

    def validar(self, caso: Optional[str] = None) -> None:
        """Confere a consistência dos dados. Levanta `ErroDeDados` com a causa."""
        if len(self.nos) < 2:
            raise ErroDeDados("O modelo precisa de pelo menos 2 nós.")
        if not self.barras:
            raise ErroDeDados("O modelo não tem nenhuma barra.")

        vizinhos: Dict[int, List[int]] = {i: [] for i in range(len(self.nos))}
        for k, b in enumerate(self.barras):
            id_b = b.rotulo or f"barra {k}"
            for idx in (b.ni, b.nf):
                if not 0 <= idx < len(self.nos):
                    raise ErroDeDados(f"{id_b}: nó {idx} inexistente "
                                      f"(o modelo tem {len(self.nos)} nós).")
            if b.ni == b.nf:
                raise ErroDeDados(f"{id_b}: nó inicial e final são o mesmo (nó {b.ni}).")
            L = self.comprimento(k)
            if L < TOL_COMPRIMENTO:
                raise ErroDeDados(
                    f"{id_b}: comprimento nulo ({fmt(L, 6, 'cm')}) — os nós {b.ni} e {b.nf} "
                    "estão na mesma posição. Elimine a barra ou separe os nós.")
            if b.A <= 0:
                raise ErroDeDados(f"{id_b}: área A = {fmt(b.A, 3, 'cm²')} deve ser positiva.")
            if b.I <= 0:
                raise ErroDeDados(f"{id_b}: inércia I = {fmt(b.I, 3, 'cm⁴')} deve ser positiva.")
            if b.E <= 0:
                raise ErroDeDados(f"{id_b}: módulo E = {fmt(b.E, 1, 'kN/cm²')} deve ser positivo.")
            vizinhos[b.ni].append(b.nf)
            vizinhos[b.nf].append(b.ni)

        soltos = [i for i, v in enumerate(vizinhos) if not vizinhos[i]]
        if soltos:
            nomes = ", ".join(self.nos[i].nome or str(i) for i in soltos)
            raise ErroDeDados(f"Nó solto: o(s) nó(s) {nomes} não pertence(m) a nenhuma barra. "
                              "Ligue-o a uma barra ou remova-o do modelo.")

        # conectividade: a estrutura tem de ser uma peça só
        visto = {0}
        fila = [0]
        while fila:
            i = fila.pop()
            for j in vizinhos[i]:
                if j not in visto:
                    visto.add(j)
                    fila.append(j)
        if len(visto) != len(self.nos):
            fora = sorted(set(range(len(self.nos))) - visto)
            nomes = ", ".join(self.nos[i].nome or str(i) for i in fora[:6])
            raise ErroDeDados("Estrutura hipostática: o modelo está partido em trechos "
                              f"desconexos (o(s) nó(s) {nomes} não se liga(m) ao resto). ")

        n_restr = sum(sum(1 for r in n.apoio if r) for n in self.nos)
        if n_restr < 3:
            raise ErroDeDados(
                f"Estrutura hipostática: há apenas {n_restr} restrição(ões) de apoio. "
                "Um corpo plano precisa de no mínimo 3 (duas translações e uma rotação, "
                "ou três restrições não concorrentes e não paralelas).")

        if caso is not None:
            self._validar_caso(caso)

    def _validar_caso(self, caso: str) -> List[Carga]:
        if caso not in self.casos:
            raise ErroDeDados(f"Caso de carga '{caso}' não existe. "
                              f"Casos do modelo: {list(self.casos)}.")
        for c in self.casos[caso]:
            if c.tipo == "nodal":
                self.indice_no(c.alvo)
            elif c.tipo in ("distribuida", "concentrada"):
                k = self.indice_barra(c.alvo)
                if c.tipo == "concentrada":
                    L = self.comprimento(k)
                    if not 0.0 <= c.a <= L:
                        raise ErroDeDados(
                            f"Carga concentrada fora da barra {c.alvo}: a = {fmt(c.a, 1, 'cm')} "
                            f"não está entre 0 e L = {fmt(L, 1, 'cm')}.")
            else:
                raise ErroDeDados(f"Tipo de carga '{c.tipo}' desconhecido.")
        return self.casos[caso]

    def resumo(self) -> str:
        return (f"{self.nome or 'modelo'}: {len(self.nos)} nós, {len(self.barras)} barras, "
                f"casos {list(self.casos)}")


# =====================================================================================
# 3. Elemento de pórtico plano — rigidez, rotação, cargas equivalentes e condensação
# =====================================================================================

def _rigidez_local(Emod: float, A: float, I: float, L: float) -> List[List[float]]:
    """Matriz de rigidez 6×6 do elemento de pórtico plano em eixos locais."""
    ea = Emod * A / L
    a = Emod * I / L
    b = Emod * I / (L * L)
    c = Emod * I / (L ** 3)
    k = [[0.0] * 6 for _ in range(6)]
    k[0][0] = k[3][3] = ea
    k[0][3] = k[3][0] = -ea
    k[1][1] = k[4][4] = 12.0 * c
    k[1][4] = k[4][1] = -12.0 * c
    k[1][2] = k[2][1] = 6.0 * b
    k[1][5] = k[5][1] = 6.0 * b
    k[2][4] = k[4][2] = -6.0 * b
    k[4][5] = k[5][4] = -6.0 * b
    k[2][2] = k[5][5] = 4.0 * a
    k[2][5] = k[5][2] = 2.0 * a
    return k


class _Elemento:
    """Dados geométricos e de rigidez de uma barra, prontos para a montagem."""

    def __init__(self, modelo: Modelo, indice: int):
        b = modelo.barras[indice]
        ni, nf = modelo.nos[b.ni], modelo.nos[b.nf]
        self.indice = indice
        self.barra = b
        self.rotulo = b.rotulo or f"barra {indice}"
        self.xi, self.yi = ni.x, ni.y
        self.xf, self.yf = nf.x, nf.y
        dx, dy = nf.x - ni.x, nf.y - ni.y
        self.L = math.hypot(dx, dy)
        self.c = dx / self.L
        self.s = dy / self.L
        self.k_local = _rigidez_local(b.E, b.A, b.I, self.L)
        self.liberados = [i for i, lib in ((2, b.rotula_i), (5, b.rotula_f)) if lib]
        self.mantidos = [i for i in range(6) if i not in self.liberados]
        if self.liberados:
            krr = [[self.k_local[r][s_] for s_ in self.liberados] for r in self.liberados]
            self.krr_inv = _inverter(krr)
        else:
            self.krr_inv = None
        self.gl = [3 * b.ni, 3 * b.ni + 1, 3 * b.ni + 2,
                   3 * b.nf, 3 * b.nf + 1, 3 * b.nf + 2]

    # -- transformação local <-> global -------------------------------------------

    def para_local(self, ug: Sequence[float]) -> List[float]:
        c, s = self.c, self.s
        return [c * ug[0] + s * ug[1], -s * ug[0] + c * ug[1], ug[2],
                c * ug[3] + s * ug[4], -s * ug[3] + c * ug[4], ug[5]]

    def para_global(self, vl: Sequence[float]) -> List[float]:
        c, s = self.c, self.s
        return [c * vl[0] - s * vl[1], s * vl[0] + c * vl[1], vl[2],
                c * vl[3] - s * vl[4], s * vl[3] + c * vl[4], vl[5]]

    def rigidez_global(self, k_local: List[List[float]]) -> List[List[float]]:
        """T^T · k · T, com T a matriz de rotação do elemento."""
        c, s = self.c, self.s
        # k·T  (colunas rodadas)
        kt = [[0.0] * 6 for _ in range(6)]
        for i in range(6):
            li = k_local[i]
            kt[i][0] = li[0] * c - li[1] * s
            kt[i][1] = li[0] * s + li[1] * c
            kt[i][2] = li[2]
            kt[i][3] = li[3] * c - li[4] * s
            kt[i][4] = li[3] * s + li[4] * c
            kt[i][5] = li[5]
        # T^T·(k·T)  (linhas rodadas)
        kg = [[0.0] * 6 for _ in range(6)]
        for j in range(6):
            kg[0][j] = kt[0][j] * c - kt[1][j] * s
            kg[1][j] = kt[0][j] * s + kt[1][j] * c
            kg[2][j] = kt[2][j]
            kg[3][j] = kt[3][j] * c - kt[4][j] * s
            kg[4][j] = kt[3][j] * s + kt[4][j] * c
            kg[5][j] = kt[5][j]
        return kg

    # -- condensação estática da(s) rótula(s) --------------------------------------

    def condensar(self, Q: List[float]) -> Tuple[List[List[float]], List[float]]:
        """Devolve (k_condensada, Q_condensado) em eixos locais.

        A rotação liberada é eliminada impondo momento nulo na extremidade:
            k* = k_kk − k_kr·k_rr⁻¹·k_rk        Q* = Q_k − k_kr·k_rr⁻¹·Q_r
        """
        if not self.liberados:
            return self.k_local, list(Q)
        k = self.k_local
        r = self.liberados
        inv = self.krr_inv
        # w[i][a] = Σ_b k[i][r_b]·inv[b][a]
        w = [[sum(k[i][r[b]] * inv[b][a] for b in range(len(r))) for a in range(len(r))]
             for i in range(6)]
        kc = [[0.0] * 6 for _ in range(6)]
        for i in self.mantidos:
            for j in self.mantidos:
                kc[i][j] = k[i][j] - sum(w[i][a] * k[r[a]][j] for a in range(len(r)))
        Qc = [0.0] * 6
        for i in self.mantidos:
            Qc[i] = Q[i] - sum(w[i][a] * Q[r[a]] for a in range(len(r)))
        return kc, Qc

    def recuperar_liberados(self, u_local: List[float], Q: List[float]) -> List[float]:
        """Completa o vetor de deslocamentos locais com as rotações liberadas reais."""
        if not self.liberados:
            return u_local
        k = self.k_local
        r = self.liberados
        inv = self.krr_inv
        u = list(u_local)
        for a in range(len(r)):
            u[r[a]] = 0.0
        resto = [Q[r[b]] - sum(k[r[b]][j] * u[j] for j in self.mantidos) for b in range(len(r))]
        for a in range(len(r)):
            u[r[a]] = sum(inv[a][b] * resto[b] for b in range(len(r)))
        return u


def _cargas_do_elemento(el: _Elemento, cargas: Sequence[Carga]
                        ) -> Tuple[float, float, List[Tuple[float, float, float]]]:
    """Converte as cargas de barra para (qx, qy) locais uniformes e pontuais locais."""
    qx = qy = 0.0
    pontos: List[Tuple[float, float, float]] = []
    c, s = el.c, el.s
    for carga in cargas:
        if carga.tipo == "distribuida":
            q, d = carga.q, carga.direcao
            if d == "perpendicular":
                qy += q
            elif d == "axial":
                qx += q
            elif d == "global_x":
                qx += q * c
                qy += -q * s
            elif d == "global_y":
                qx += q * s
                qy += q * c
            elif d == "projetada_x":
                qe = q * abs(s)          # por unidade de projeção vertical
                qx += qe * c
                qy += -qe * s
            elif d == "projetada_y":
                qe = q * abs(c)          # por unidade de projeção horizontal
                qx += qe * s
                qy += qe * c
            else:
                raise ErroDeDados(f"Direção de carga '{d}' desconhecida.")
        elif carga.tipo == "concentrada":
            P, d = carga.P, carga.direcao
            if d == "perpendicular":
                px, py = 0.0, P
            elif d == "axial":
                px, py = P, 0.0
            elif d == "global_x":
                px, py = P * c, -P * s
            elif d == "global_y":
                px, py = P * s, P * c
            else:
                raise ErroDeDados(f"Direção '{d}' não vale para carga concentrada.")
            pontos.append((float(carga.a), px, py))
    pontos.sort(key=lambda p: p[0])
    return qx, qy, pontos


def _cargas_equivalentes(L: float, qx: float, qy: float,
                         pontos: Sequence[Tuple[float, float, float]]) -> List[float]:
    """Vetor de cargas nodais equivalentes (consistentes) em eixos locais."""
    Q = [0.0] * 6
    if qx:
        Q[0] += qx * L / 2.0
        Q[3] += qx * L / 2.0
    if qy:
        Q[1] += qy * L / 2.0
        Q[2] += qy * L * L / 12.0
        Q[4] += qy * L / 2.0
        Q[5] -= qy * L * L / 12.0
    for a, px, py in pontos:
        b = L - a
        if px:
            Q[0] += px * b / L
            Q[3] += px * a / L
        if py:
            Q[1] += py * b * b * (3.0 * a + b) / L ** 3
            Q[2] += py * a * b * b / L ** 2
            Q[4] += py * a * a * (a + 3.0 * b) / L ** 3
            Q[5] -= py * a * a * b / L ** 2
    return Q


# =====================================================================================
# 4. Solver — montagem, condições de contorno, solução e esforços internos
# =====================================================================================

@dataclass
class Extremo:
    """Um valor extremo de diagrama e a posição onde ocorre (cm a partir do nó inicial)."""
    valor: float
    x: float

    def __iter__(self):
        return iter((self.valor, self.x))


@dataclass
class Diagrama:
    """Diagramas N, V, M amostrados ao longo da barra."""
    x: List[float]
    N: List[float]
    V: List[float]
    M: List[float]

    def _extremo(self, grandeza: str, maior: bool) -> Extremo:
        v = getattr(self, grandeza)
        if not v:
            return Extremo(0.0, 0.0)
        if maior:
            i = max(range(len(v)), key=lambda k: v[k])
        else:
            i = min(range(len(v)), key=lambda k: v[k])
        return Extremo(v[i], self.x[i])

    def maximo(self, grandeza: str = "M") -> Extremo:
        return self._extremo(grandeza, True)

    def minimo(self, grandeza: str = "M") -> Extremo:
        return self._extremo(grandeza, False)

    def absoluto(self, grandeza: str = "M") -> Extremo:
        """Maior valor em módulo, com o sinal preservado."""
        v = getattr(self, grandeza)
        if not v:
            return Extremo(0.0, 0.0)
        i = max(range(len(v)), key=lambda k: abs(v[k]))
        return Extremo(v[i], self.x[i])

    @property
    def N_max(self) -> Extremo:
        return self.maximo("N")

    @property
    def N_min(self) -> Extremo:
        return self.minimo("N")

    @property
    def V_max(self) -> Extremo:
        return self.maximo("V")

    @property
    def V_min(self) -> Extremo:
        return self.minimo("V")

    @property
    def M_max(self) -> Extremo:
        return self.maximo("M")

    @property
    def M_min(self) -> Extremo:
        return self.minimo("M")


@dataclass
class ResultadoBarra:
    """Esforços de extremidade e diagramas de uma barra em um caso de carga."""
    indice: int
    rotulo: str
    L: float
    f_local: List[float]                         # ações de extremidade, eixos locais
    diagrama: "Diagrama"
    qx: float = 0.0
    qy: float = 0.0
    pontos: List[Tuple[float, float, float]] = field(default_factory=list)

    def esforcos(self, x: float, lado: int = 1) -> Tuple[float, float, float]:
        """(N, V, M) na seção a `x` cm do nó inicial.

        `lado` = +1 lê imediatamente à direita de uma carga concentrada, −1 à esquerda.
        """
        f = self.f_local
        N = -(f[0] + self.qx * x)
        V = f[1] + self.qy * x
        M = -f[2] + f[1] * x + self.qy * x * x / 2.0
        for a, px, py in self.pontos:
            if a < x or (a == x and lado > 0):
                N -= px
                V += py
            if a < x:
                M += py * (x - a)
        return N, V, M

    @property
    def N_i(self) -> float:
        return self.esforcos(0.0)[0]

    @property
    def N_f(self) -> float:
        return self.esforcos(self.L, lado=-1)[0]

    @property
    def V_i(self) -> float:
        return self.esforcos(0.0)[1]

    @property
    def V_f(self) -> float:
        return self.esforcos(self.L, lado=-1)[1]

    @property
    def M_i(self) -> float:
        """Momento no nó inicial (kN·cm)."""
        return -self.f_local[2]

    @property
    def M_f(self) -> float:
        """Momento no nó final (kN·cm)."""
        return self.f_local[5]

    def resumo(self) -> str:
        return (f"{self.rotulo}: N {fmt(self.diagrama.absoluto('N').valor, 1, 'kN')}, "
                f"V {fmt(self.diagrama.absoluto('V').valor, 1, 'kN')}, "
                f"M {fmt(self.diagrama.absoluto('M').valor / 100.0, 1, 'kN·m')}")


class ResultadoAnalise:
    """Resultado consultável de um caso de carga."""

    def __init__(self, modelo: Modelo, caso: str, u: List[float],
                 reacoes: Dict[int, Tuple[float, float, float]],
                 barras: List[ResultadoBarra], gl_soltos: List[int]):
        self.modelo = modelo
        self.caso = caso
        self.u = u
        self.reacoes = reacoes
        self.barras = barras
        self.gl_soltos = gl_soltos     # gl sem rigidez, travados automaticamente

    # ---- consultas ----

    def deslocamento(self, no: Ref) -> Tuple[float, float, float]:
        """(ux, uy, rz) do nó, em cm e rad."""
        i = self.modelo.indice_no(no)
        return (self.u[3 * i], self.u[3 * i + 1], self.u[3 * i + 2])

    def reacao(self, no: Ref) -> Tuple[float, float, float]:
        """(Rx, Ry, Mz) do apoio, em kN e kN·cm. Zero nos nós sem apoio."""
        i = self.modelo.indice_no(no)
        return self.reacoes.get(i, (0.0, 0.0, 0.0))

    def barra(self, ref: Ref) -> ResultadoBarra:
        return self.barras[self.modelo.indice_barra(ref)]

    def momento(self, barra: Ref, x: Optional[float] = None) -> float:
        """Momento fletor (kN·cm) na seção x; sem x, o maior em módulo."""
        rb = self.barra(barra)
        if x is None:
            return rb.diagrama.absoluto("M").valor
        return rb.esforcos(x)[2]

    def normal(self, barra: Ref, x: float = 0.0) -> float:
        return self.barra(barra).esforcos(x)[0]

    def cortante(self, barra: Ref, x: float = 0.0) -> float:
        return self.barra(barra).esforcos(x)[1]

    # ---- equilíbrio global ----

    def cargas_aplicadas(self) -> Tuple[float, float, float]:
        """Resultante (ΣFx, ΣFy, ΣMz na origem) das cargas efetivamente aplicadas."""
        m = self.modelo
        Fx = Fy = Mz = 0.0
        for c in m.casos.get(self.caso, []):
            if c.tipo == "nodal":
                n = m.nos[m.indice_no(c.alvo)]
                Fx += c.Fx
                Fy += c.Fy
                Mz += c.Mz + n.x * c.Fy - n.y * c.Fx
            else:
                k = m.indice_barra(c.alvo)
                el = _Elemento(m, k)
                qx, qy, pontos = _cargas_do_elemento(el, [c])
                if qx or qy:
                    fx = el.c * qx * el.L - el.s * qy * el.L
                    fy = el.s * qx * el.L + el.c * qy * el.L
                    xm = el.xi + el.c * el.L / 2.0
                    ym = el.yi + el.s * el.L / 2.0
                    Fx += fx
                    Fy += fy
                    Mz += xm * fy - ym * fx
                for a, px, py in pontos:
                    fx = el.c * px - el.s * py
                    fy = el.s * px + el.c * py
                    xp = el.xi + el.c * a
                    yp = el.yi + el.s * a
                    Fx += fx
                    Fy += fy
                    Mz += xp * fy - yp * fx
        return Fx, Fy, Mz

    def soma_reacoes(self) -> Tuple[float, float, float]:
        """Resultante das reações de apoio (ΣRx, ΣRy, ΣMz na origem)."""
        Fx = Fy = Mz = 0.0
        for i, (rx, ry, mz) in self.reacoes.items():
            n = self.modelo.nos[i]
            Fx += rx
            Fy += ry
            Mz += mz + n.x * ry - n.y * rx
        return Fx, Fy, Mz

    def equilibrio(self) -> Tuple[float, float, float]:
        """Resíduo (ΣFx, ΣFy, ΣMz) de cargas aplicadas + reações. Deve ser ~0."""
        ca = self.cargas_aplicadas()
        rr = self.soma_reacoes()
        return (ca[0] + rr[0], ca[1] + rr[1], ca[2] + rr[2])

    def resumo(self) -> str:
        linhas = [f"Caso {self.caso}"]
        for i in sorted(self.reacoes):
            rx, ry, mz = self.reacoes[i]
            nome = self.modelo.nos[i].nome or f"nó {i}"
            linhas.append(f"  reação {nome}: H {fmt(rx, 1, 'kN')}, V {fmt(ry, 1, 'kN')}, "
                          f"M {fmt(mz / 100.0, 1, 'kN·m')}")
        for rb in self.barras:
            linhas.append("  " + rb.resumo())
        return "\n".join(linhas)


def _pontos_amostragem(L: float, qy: float, f1: float,
                       pontos: Sequence[Tuple[float, float, float]],
                       n: int) -> List[float]:
    """Malha de amostragem: n pontos uniformes + descontinuidades + seções de V = 0."""
    eps = max(L * 1e-9, 1e-12)
    xs = [L * k / (n - 1) for k in range(n)]
    for a, px, py in pontos:
        xs.append(max(0.0, a - eps))
        xs.append(min(L, a + eps))
    if qy:
        limites = [0.0] + [a for a, _, _ in pontos] + [L]
        for t in range(len(limites) - 1):
            xa, xb = limites[t], limites[t + 1]
            V = f1 + qy * xa + sum(py for a, _, py in pontos if a <= xa)
            x0 = xa - V / qy
            if xa < x0 < xb:
                xs.append(x0)
    xs = sorted(min(max(v, 0.0), L) for v in xs)
    saida: List[float] = []
    for v in xs:
        if not saida or v - saida[-1] > eps / 2.0:
            saida.append(v)
    return saida


def resolver(modelo: Modelo, caso: str, n_pontos: int = 21) -> ResultadoAnalise:
    """Resolve um caso de carga pelo método da rigidez direta (pórtico plano).

    Monta K global, aplica as condições de contorno, resolve K·u = F por eliminação
    de Gauss com pivotamento parcial e recupera os esforços internos de cada barra
    por superposição da solução engastada (cargas de engastamento perfeito).
    """
    modelo.validar(caso)
    cargas = modelo.casos[caso]
    ngl = modelo.ngl
    K = [[0.0] * ngl for _ in range(ngl)]
    F = [0.0] * ngl

    for c in cargas:
        if c.tipo == "nodal":
            i = modelo.indice_no(c.alvo)
            F[3 * i] += c.Fx
            F[3 * i + 1] += c.Fy
            F[3 * i + 2] += c.Mz

    elementos: List[_Elemento] = []
    dados_barra: List[Tuple[float, float, list, List[float]]] = []
    for k in range(len(modelo.barras)):
        el = _Elemento(modelo, k)
        elementos.append(el)
        cargas_k = [c for c in cargas
                    if c.tipo in ("distribuida", "concentrada")
                    and modelo.indice_barra(c.alvo) == k]
        qx, qy, pontos = _cargas_do_elemento(el, cargas_k)
        Q = _cargas_equivalentes(el.L, qx, qy, pontos)
        kc, Qc = el.condensar(Q)
        kg = el.rigidez_global(kc)
        Qg = el.para_global(Qc)
        gl = el.gl
        for i in range(6):
            F[gl[i]] += Qg[i]
            linha = K[gl[i]]
            for j in range(6):
                linha[gl[j]] += kg[i][j]
        dados_barra.append((qx, qy, pontos, Q))

    restritos = set()
    for i, n in enumerate(modelo.nos):
        for d, r in enumerate(n.apoio):
            if r:
                restritos.add(3 * i + d)

    # graus de liberdade sem rigidez nenhuma (rotação de nó de treliça, por exemplo):
    # travam-se automaticamente, mas só se não houver carga aplicada neles
    maior_k = max((abs(K[i][i]) for i in range(ngl)), default=1.0) or 1.0
    maior_f = max((abs(v) for v in F), default=1.0) or 1.0
    soltos: List[int] = []
    for i in range(ngl):
        if i in restritos:
            continue
        if max(abs(v) for v in K[i]) <= TOL_RIGIDEZ * maior_k:
            if abs(F[i]) > 1e-9 * maior_f:
                no = i // 3
                gdl = ("ux", "uy", "rz")[i % 3]
                nome = modelo.nos[no].nome or f"nó {no}"
                raise ErroDeDados(
                    f"Estrutura hipostática: o grau de liberdade {gdl} do {nome} não tem "
                    "rigidez alguma e recebe carga. Provável causa: todas as barras que "
                    "chegam ao nó estão rotuladas (nó de treliça) e foi aplicado momento.")
            soltos.append(i)
            restritos.add(i)

    livres = [i for i in range(ngl) if i not in restritos]
    u = [0.0] * ngl
    if livres:
        A = [[K[i][j] for j in livres] for i in livres]
        b = [F[i] for i in livres]
        rotulos = []
        for g in livres:
            no = g // 3
            nome = modelo.nos[no].nome or f"nó {no}"
            rotulos.append(f"{('ux', 'uy', 'rz')[g % 3]} do {nome}")
        x = resolver_sistema(A, b, rotulos)
        for j, g in enumerate(livres):
            u[g] = x[j]

    # reações: R = K·u − F, apenas nos graus restringidos por apoio do usuário
    reacoes: Dict[int, Tuple[float, float, float]] = {}
    for i, n in enumerate(modelo.nos):
        if not n.apoiado:
            continue
        r = [0.0, 0.0, 0.0]
        for d in range(3):
            if n.apoio[d]:
                g = 3 * i + d
                linha = K[g]
                r[d] = sum(linha[j] * u[j] for j in range(ngl) if linha[j] != 0.0) - F[g]
        reacoes[i] = (r[0], r[1], r[2])

    resultados: List[ResultadoBarra] = []
    for k, el in enumerate(elementos):
        qx, qy, pontos, Q = dados_barra[k]
        ug = [u[g] for g in el.gl]
        ul = el.recuperar_liberados(el.para_local(ug), Q)
        f_local = [sum(el.k_local[i][j] * ul[j] for j in range(6)) - Q[i] for i in range(6)]
        for r in el.liberados:               # zera o resíduo numérico na rótula
            f_local[r] = 0.0
        rb = ResultadoBarra(k, el.rotulo, el.L, f_local,
                            Diagrama([], [], [], []), qx, qy, list(pontos))
        xs = _pontos_amostragem(el.L, qy, f_local[1], pontos, max(3, n_pontos))
        Ns, Vs, Ms = [], [], []
        for x in xs:
            N, V, M = rb.esforcos(x, lado=1)
            Ns.append(N)
            Vs.append(V)
            Ms.append(M)
        if xs:                                # a última seção lê à esquerda do nó final
            Ns[-1], Vs[-1], Ms[-1] = rb.esforcos(xs[-1], lado=-1)
        rb.diagrama = Diagrama(xs, Ns, Vs, Ms)
        resultados.append(rb)

    return ResultadoAnalise(modelo, caso, u, reacoes, resultados, soltos)


# =====================================================================================
# 5. Envoltória — máximos e mínimos entre casos, com o caso governante
# =====================================================================================

@dataclass
class ExtremoEnvoltoria:
    """Valor extremo, posição na barra e caso de carga que o governa."""
    valor: float
    x: float
    caso: str


@dataclass
class EnvoltoriaBarra:
    """Máximos e mínimos de N, V e M de uma barra entre todos os casos."""
    indice: int
    rotulo: str
    L: float
    N_max: ExtremoEnvoltoria
    N_min: ExtremoEnvoltoria
    V_max: ExtremoEnvoltoria
    V_min: ExtremoEnvoltoria
    M_max: ExtremoEnvoltoria
    M_min: ExtremoEnvoltoria

    def absoluto(self, grandeza: str = "M") -> ExtremoEnvoltoria:
        """O extremo de maior módulo — o que dimensiona."""
        a = getattr(self, grandeza + "_max")
        b = getattr(self, grandeza + "_min")
        return a if abs(a.valor) >= abs(b.valor) else b

    def resumo(self) -> str:
        return (f"{self.rotulo}: N {fmt(self.N_min.valor, 1)}/{fmt(self.N_max.valor, 1, 'kN')}, "
                f"V {fmt(self.V_min.valor, 1)}/{fmt(self.V_max.valor, 1, 'kN')}, "
                f"M {fmt(self.M_min.valor / 100, 1)}/{fmt(self.M_max.valor / 100, 1, 'kN·m')} "
                f"(governa M: {self.absoluto('M').caso})")


class Envoltoria:
    """Envoltória de esforços — é ela que alimenta o dimensionamento."""

    def __init__(self, modelo: Modelo, barras: List[EnvoltoriaBarra],
                 resultados: Dict[str, ResultadoAnalise],
                 reacoes: Dict[int, Dict[str, ExtremoEnvoltoria]]):
        self.modelo = modelo
        self.barras = barras
        self.resultados = resultados
        self.reacoes = reacoes

    @property
    def casos(self) -> List[str]:
        return list(self.resultados)

    def barra(self, ref: Ref) -> EnvoltoriaBarra:
        return self.barras[self.modelo.indice_barra(ref)]

    def reacao(self, no: Ref) -> Dict[str, ExtremoEnvoltoria]:
        """Extremos de Rx, Ry e Mz do apoio — inclusive o arrancamento (Ry mínimo)."""
        return self.reacoes[self.modelo.indice_no(no)]

    def resumo(self) -> str:
        return "\n".join(["Envoltória (" + ", ".join(self.casos) + ")"]
                         + ["  " + b.resumo() for b in self.barras])


def envoltoria(modelo: Modelo, casos: Optional[Sequence[str]] = None,
               n_pontos: int = 21) -> Envoltoria:
    """Resolve todos os casos e devolve, por barra, os extremos de N, V e M.

    Guarda o caso que governa cada extremo e também os extremos das reações de
    apoio (o projetista de fundações precisa do arrancamento, não só da compressão).
    """
    nomes = list(casos) if casos is not None else list(modelo.casos)
    if not nomes:
        raise ErroDeDados("Não há casos de carga para a envoltória.")
    resultados: Dict[str, ResultadoAnalise] = {}
    for nome in nomes:
        resultados[nome] = resolver(modelo, nome, n_pontos)

    barras: List[EnvoltoriaBarra] = []
    for k in range(len(modelo.barras)):
        ext: Dict[str, ExtremoEnvoltoria] = {}
        for g in ("N", "V", "M"):
            ext[g + "_max"] = ExtremoEnvoltoria(-math.inf, 0.0, "")
            ext[g + "_min"] = ExtremoEnvoltoria(math.inf, 0.0, "")
        L = 0.0
        rotulo = ""
        for nome in nomes:
            rb = resultados[nome].barras[k]
            L, rotulo = rb.L, rb.rotulo
            for g in ("N", "V", "M"):
                mx = rb.diagrama.maximo(g)
                mn = rb.diagrama.minimo(g)
                if mx.valor > ext[g + "_max"].valor:
                    ext[g + "_max"] = ExtremoEnvoltoria(mx.valor, mx.x, nome)
                if mn.valor < ext[g + "_min"].valor:
                    ext[g + "_min"] = ExtremoEnvoltoria(mn.valor, mn.x, nome)
        barras.append(EnvoltoriaBarra(k, rotulo, L, ext["N_max"], ext["N_min"],
                                      ext["V_max"], ext["V_min"],
                                      ext["M_max"], ext["M_min"]))

    reacoes: Dict[int, Dict[str, ExtremoEnvoltoria]] = {}
    for i, n in enumerate(modelo.nos):
        if not n.apoiado:
            continue
        d: Dict[str, ExtremoEnvoltoria] = {}
        for j, g in enumerate(("Rx", "Ry", "Mz")):
            d[g + "_max"] = ExtremoEnvoltoria(-math.inf, 0.0, "")
            d[g + "_min"] = ExtremoEnvoltoria(math.inf, 0.0, "")
            for nome in nomes:
                v = resultados[nome].reacao(i)[j]
                if v > d[g + "_max"].valor:
                    d[g + "_max"] = ExtremoEnvoltoria(v, 0.0, nome)
                if v < d[g + "_min"].valor:
                    d[g + "_min"] = ExtremoEnvoltoria(v, 0.0, nome)
        reacoes[i] = d

    return Envoltoria(modelo, barras, resultados, reacoes)


# =====================================================================================
# 6. Efeitos de segunda ordem — método B1/B2 (NBR 8800:2008, Anexo D)
# =====================================================================================

# Classificação quanto à deslocabilidade (NBR 8800:2008, item 4.9.4.2), pela razão
# entre o deslocamento horizontal de 2ª ordem e o de 1ª ordem do andar:
LIMITE_PEQUENA = 1.1
LIMITE_MEDIA = 1.4


@dataclass
class Andar:
    """Dados de um andar (ou do pórtico inteiro, no galpão de um pavimento).

    h        altura do andar, cm
    delta_h  deslocamento horizontal relativo de 1ª ordem do andar, cm
    soma_N   ΣN_Sd — soma das forças axiais de compressão nos pilares do andar, kN
    soma_H   ΣH_Sd — soma das forças horizontais do andar que produzem delta_h, kN
    barras   barras do andar (índices ou rótulos); vazio = todas
    """
    h: float
    delta_h: float
    soma_N: float
    soma_H: float
    nome: str = "pórtico"
    barras: Sequence[Ref] = field(default_factory=tuple)


@dataclass
class DadosSegundaOrdem:
    """Dados para a amplificação B1/B2 (NBR 8800:2008, Anexo D).

    andares       um `Andar` por pavimento (um só, no galpão de pórticos).
    Rs            NBR 8800, D.2.2: 0,85 para estruturas cuja estabilidade lateral
                  depende exclusivamente da rigidez das ligações viga-pilar
                  (pórticos rígidos); 1,00 para as demais (com sistema de
                  contraventamento). Informe explicitamente o caso da estrutura.
    resultado_nt  resultado da análise "nt" (nós indeslocáveis, com contenção lateral
                  fictícia). Se não for informado, todo o esforço é tratado como "lt"
                  e amplificado por B2 ou B1 — o que for maior —, simplificação a
                  favor da segurança (princípio 3 do guia).
    K1            coeficiente de flambagem no plano para N_e1 (≤ 1,0, estrutura
                  contida lateralmente — NBR 8800, D.2.1).
    Cm            valor imposto de C_m por barra; sem ele, calcula-se do diagrama.
    barras_com_carga_transversal  barras com carga entre as extremidades.
    extremos_restritos            rotação impedida nas extremidades dessas barras.
    """
    andares: Sequence[Andar]
    Rs: float = 0.85
    resultado_nt: Optional["ResultadoAnalise"] = None
    K1: float = 1.0
    Cm: Dict[Ref, float] = field(default_factory=dict)
    barras_com_carga_transversal: Sequence[Ref] = field(default_factory=tuple)
    extremos_restritos: bool = True


@dataclass
class BarraAmplificada:
    """Esforços de uma barra já amplificados para a 2ª ordem."""
    indice: int
    rotulo: str
    L: float
    B1: float
    B2: float
    Cm: float
    Ne1: float
    N_sd1: float
    diagrama: "Diagrama"

    def resumo(self) -> str:
        return (f"{self.rotulo}: B1 = {fmt(self.B1, 3)}, B2 = {fmt(self.B2, 3)} → "
                f"M = {fmt(self.diagrama.absoluto('M').valor / 100.0, 1, 'kN·m')}")


class ResultadoSegundaOrdem:
    """Esforços amplificados, classificação da estrutura e memória de cálculo."""

    def __init__(self, resultado: "ResultadoAnalise", classificacao: str,
                 B2: Dict[str, float], barras: List[BarraAmplificada],
                 passos: List[Passo], observacao: str, aplicavel: bool):
        self.resultado = resultado
        self.modelo = resultado.modelo
        self.caso = resultado.caso
        self.classificacao = classificacao
        self.B2 = B2
        self.barras = barras
        self.passos = passos
        self.observacao = observacao
        self.aplicavel = aplicavel

    def barra(self, ref: Ref) -> BarraAmplificada:
        return self.barras[self.modelo.indice_barra(ref)]

    def momento(self, barra: Ref, x: Optional[float] = None) -> float:
        b = self.barra(barra)
        if x is None:
            return b.diagrama.absoluto("M").valor
        i = min(range(len(b.diagrama.x)), key=lambda k: abs(b.diagrama.x[k] - x))
        return b.diagrama.M[i]

    def resumo(self) -> str:
        linhas = [f"Caso {self.caso} — {self.classificacao} "
                  f"(B2 máx = {fmt(max(self.B2.values()) if self.B2 else 1.0, 3)})"]
        if self.observacao:
            linhas.append("  " + self.observacao)
        for b in self.barras:
            linhas.append("  " + b.resumo())
        return "\n".join(linhas)


def coeficiente_Cm(M1: float = 0.0, M2: float = 0.0, carga_transversal: bool = False,
                   extremos_restritos: bool = True) -> Tuple[float, str]:
    """C_m da NBR 8800:2008, item D.2.1. Devolve (valor, justificativa).

    a) sem forças transversais entre as extremidades:
           C_m = 0,60 − 0,40·(M1/M2)
       com M1/M2 positivo quando os momentos provocam curvatura reversa e negativo
       quando provocam curvatura simples;
    b) com forças transversais entre as extremidades: C_m = 0,85 se houver restrição
       à rotação nas extremidades e C_m = 1,00 se não houver.
    """
    if carga_transversal:
        if extremos_restritos:
            return 0.85, ("barra com força transversal entre as extremidades e rotação "
                          "impedida nos apoios (NBR 8800, D.2.1-b)")
        return 1.00, ("barra com força transversal entre as extremidades e extremidades "
                      "livres à rotação (NBR 8800, D.2.1-b)")
    a, b = abs(M1), abs(M2)
    if max(a, b) == 0.0:
        return 1.00, "momentos de extremidade nulos: adotado C_m = 1,00 (conservador)"
    razao = min(a, b) / max(a, b)
    if M1 * M2 < 0.0:
        razao = +razao       # curvatura reversa
        curva = "curvatura reversa"
    else:
        razao = -razao       # curvatura simples
        curva = "curvatura simples"
    return 0.60 - 0.40 * razao, (f"momentos de extremidade em {curva}, "
                                 f"M1/M2 = {fmt(razao, 3)} (NBR 8800, D.2.1-a)")


def _B2_do_andar(andar: Andar, Rs: float, passos: List[Passo]) -> float:
    """B2 de um andar (NBR 8800:2008, item D.2.2)."""
    if andar.h <= 0:
        raise ErroDeDados(f"Andar '{andar.nome}': altura h = {fmt(andar.h, 1, 'cm')} "
                          "deve ser positiva.")
    if andar.soma_H == 0.0:
        raise ErroDeDados(
            f"Andar '{andar.nome}': ΣH_Sd = 0. O B2 do Anexo D exige uma análise com "
            "força horizontal (a combinação de vento, ou as forças nocionais de 0,3 % "
            "das cargas gravitacionais do item 4.9.7 da NBR 8800).")
    razao = (1.0 / Rs) * (andar.delta_h / andar.h) * (andar.soma_N / andar.soma_H)
    if razao >= 1.0:
        raise ErroDeDados(
            f"Andar '{andar.nome}': (1/R_s)·(Δh/h)·(ΣN_Sd/ΣH_Sd) = {fmt(razao, 3)} ≥ 1. "
            "A estrutura é instável sob essa combinação — aumente a rigidez lateral.")
    B2 = 1.0 / (1.0 - razao)
    passos.append(Passo(
        f"B₂ do andar '{andar.nome}'",
        formula="B<sub>2</sub> = 1 / [1 − (1/R<sub>s</sub>)·(Δ<sub>h</sub>/h)·"
                "(ΣN<sub>Sd</sub>/ΣH<sub>Sd</sub>)]",
        conta=f"1 / [1 − (1/{fmt(Rs, 2)})·({fmt(andar.delta_h, 2)}/{fmt(andar.h, 0)})·"
              f"({fmt(andar.soma_N, 1)}/{fmt(andar.soma_H, 1)})]",
        valor=fmt(B2, 3),
        norma="NBR 8800:2008, item D.2.2"))
    return B2


def _classificar(B2_max: float) -> str:
    """Deslocabilidade da estrutura (NBR 8800:2008, item 4.9.4.2)."""
    if B2_max <= LIMITE_PEQUENA:
        return "pequena deslocabilidade"
    if B2_max <= LIMITE_MEDIA:
        return "média deslocabilidade"
    return "grande deslocabilidade"


def amplificar(resultado: "ResultadoAnalise",
               dados: DadosSegundaOrdem) -> ResultadoSegundaOrdem:
    """Amplifica os esforços de 1ª ordem pelo método B1/B2 (NBR 8800:2008, Anexo D).

        N_Sd = N_nt + B2·N_lt          M_Sd = B1·M_nt + B2·M_lt
        B1 = C_m / (1 − N_Sd1/N_e1) ≥ 1,0      N_e1 = π²·E·I/(K1·L)²

    Devolve os esforços amplificados, a classificação da estrutura quanto à
    deslocabilidade e a memória de cálculo em passos.
    """
    modelo = resultado.modelo
    if not dados.andares:
        raise ErroDeDados("Informe pelo menos um `Andar` para calcular B2 "
                          "(altura, Δh de 1ª ordem, ΣN_Sd e ΣH_Sd).")
    if not 0.0 < dados.Rs <= 1.0:
        raise ErroDeDados(f"R_s = {fmt(dados.Rs, 2)} fora da faixa: use 0,85 (pórtico "
                          "rígido) ou 1,00 (estrutura contraventada), NBR 8800, D.2.2.")

    passos: List[Passo] = []
    B2_andar: Dict[str, float] = {}
    for andar in dados.andares:
        B2_andar[andar.nome] = _B2_do_andar(andar, dados.Rs, passos)
    B2_max = max(B2_andar.values())

    classificacao = _classificar(B2_max)
    passos.append(Passo(
        "Classificação quanto à deslocabilidade",
        formula="Δ<sub>2ª ordem</sub> / Δ<sub>1ª ordem</sub> ≈ B<sub>2</sub>",
        conta=f"B₂ máx = {fmt(B2_max, 3)} "
              f"(≤ {fmt(LIMITE_PEQUENA, 1)} pequena; ≤ {fmt(LIMITE_MEDIA, 1)} média)",
        valor=classificacao,
        norma="NBR 8800:2008, item 4.9.4.2"))

    aplicavel = classificacao != "grande deslocabilidade"
    observacoes: List[str] = []
    if not aplicavel:
        observacoes.append(
            "Estrutura de grande deslocabilidade: a NBR 8800 (item 4.9.4.2) NÃO admite o "
            "método da amplificação dos esforços do Anexo D — é obrigatória uma análise "
            "rigorosa de 2ª ordem. Os valores abaixo são apenas indicativos.")
    elif classificacao == "média deslocabilidade":
        observacoes.append(
            "Média deslocabilidade: a NBR 8800 (item 4.9.4.3) exige que a análise de 1ª "
            "ordem que alimenta a amplificação use rigidezes reduzidas (0,8·EI e 0,8·EA) "
            "e inclua as forças nocionais de 0,3 % das cargas gravitacionais (item 4.9.7).")
    else:
        observacoes.append(
            "Pequena deslocabilidade: a NBR 8800 (item 4.9.7) exige, ainda assim, as forças "
            "nocionais de 0,3 % das cargas gravitacionais aplicadas em cada andar.")
    if dados.resultado_nt is None:
        observacoes.append(
            "Sem a análise nt (nós indeslocáveis): adotou-se M_Sd = máx(B1, B2)·M de 1ª "
            "ordem em todas as barras — simplificação a favor da segurança.")

    # B2 por barra
    def B2_da_barra(k: int) -> float:
        for andar in dados.andares:
            if andar.barras and k in [modelo.indice_barra(b) for b in andar.barras]:
                return B2_andar[andar.nome]
        sem_mapa = [a for a in dados.andares if not a.barras]
        if sem_mapa:
            return max(B2_andar[a.nome] for a in sem_mapa)
        return B2_max

    transversais = {modelo.indice_barra(b) for b in dados.barras_com_carga_transversal}
    Cm_imposto = {modelo.indice_barra(k): v for k, v in dados.Cm.items()}

    barras: List[BarraAmplificada] = []
    for k, barra in enumerate(modelo.barras):
        rb = resultado.barras[k]
        rnt = dados.resultado_nt.barras[k] if dados.resultado_nt is not None else None
        B2 = B2_da_barra(k)

        # N_Sd1: compressão máxima da análise nt (ou da total, se não houver nt)
        base = rnt if rnt is not None else rb
        N_comp = -min(base.diagrama.N) if base.diagrama.N else 0.0
        N_sd1 = max(0.0, N_comp)
        Ne1 = math.pi ** 2 * barra.E * barra.I / (dados.K1 * rb.L) ** 2

        tem_carga = k in transversais or rb.qy != 0.0 or bool(rb.pontos)
        if k in Cm_imposto:
            Cm, just = Cm_imposto[k], "C_m imposto pelo usuário"
        else:
            Cm, just = coeficiente_Cm(base.M_i, base.M_f, tem_carga, dados.extremos_restritos)

        if N_sd1 >= Ne1:
            raise ErroDeDados(
                f"{rb.rotulo}: N_Sd1 = {fmt(N_sd1, 1, 'kN')} ≥ N_e1 = {fmt(Ne1, 1, 'kN')}. "
                "A barra flamba no plano antes de qualquer amplificação — aumente a seção "
                "ou reduza o comprimento de flambagem.")
        B1 = max(1.0, Cm / (1.0 - N_sd1 / Ne1))

        if rb.diagrama.x:
            xs = list(rb.diagrama.x)
            if rnt is not None:
                Nnt, Vnt, Mnt = [], [], []
                for x in xs:
                    n_, v_, m_ = rnt.esforcos(x)
                    Nnt.append(n_)
                    Vnt.append(v_)
                    Mnt.append(m_)
                N = [Nnt[i] + B2 * (rb.diagrama.N[i] - Nnt[i]) for i in range(len(xs))]
                V = [Vnt[i] + B2 * (rb.diagrama.V[i] - Vnt[i]) for i in range(len(xs))]
                M = [B1 * Mnt[i] + B2 * (rb.diagrama.M[i] - Mnt[i]) for i in range(len(xs))]
            else:
                f = max(B1, B2)
                N = [B2 * v for v in rb.diagrama.N]
                V = [B2 * v for v in rb.diagrama.V]
                M = [f * v for v in rb.diagrama.M]
            diag = Diagrama(xs, N, V, M)
        else:
            diag = Diagrama([], [], [], [])

        passos.append(Passo(
            f"B₁ da {rb.rotulo}",
            formula="B<sub>1</sub> = C<sub>m</sub>/(1 − N<sub>Sd1</sub>/N<sub>e1</sub>) ≥ 1,0"
                    " ; N<sub>e1</sub> = π²·E·I/(K₁·L)²",
            conta=f"{fmt(Cm, 3)}/(1 − {fmt(N_sd1, 1)}/{fmt(Ne1, 1)})  [{just}]",
            valor=fmt(B1, 3),
            norma="NBR 8800:2008, item D.2.1"))

        barras.append(BarraAmplificada(k, rb.rotulo, rb.L, B1, B2, Cm, Ne1, N_sd1, diag))

    return ResultadoSegundaOrdem(resultado, classificacao, B2_andar, barras, passos,
                                 " ".join(observacoes), aplicavel)


# =====================================================================================
# 7. Geradores de modelo prontos
# =====================================================================================

@dataclass
class Misula:
    """Trecho de maior inércia junto ao joelho do pórtico.

    comprimento  projeção do trecho enrijecido medida sobre a viga, cm
    I            inércia do trecho, cm⁴ (ou use `fator`, que multiplica a I da viga)
    A            área do trecho, cm² (padrão: a da viga — a favor da segurança,
                 porque subestima a rigidez axial, de efeito desprezível)
    fator        multiplicador da inércia da viga, quando I não é informado

    A mísula real é de altura variável (máxima na raiz, nula no fim) e aqui é
    substituída por um trecho prismático. Usar a inércia da **raiz** superestima
    muito o enrijecimento (contra a segurança nos deslocamentos); o manual, no
    Passo 6-a do Capítulo 16, adota uma inércia efetiva de cerca de 1,5·I_viga para
    a mísula de 1,8 m, valor que reproduz a redução de ≈ 10 % dos deslocamentos.
    """
    comprimento: float
    I: Optional[float] = None
    A: Optional[float] = None
    fator: Optional[float] = None


def _secao(perfil_ou_nome, A: Optional[float], I: Optional[float],
           quem: str) -> Tuple[float, float]:
    """Resolve A e I a partir de um `Perfil`, do nome de um perfil ou dos valores."""
    if A is not None and I is not None:
        return float(A), float(I)
    if perfil_ou_nome is not None:
        p = perfil_ou_nome
        if isinstance(p, str):
            from .perfis import perfil as _perfil
            p = _perfil(p)
        try:
            return float(p.A), float(p.Ix)
        except AttributeError:
            raise ErroDeDados(f"{quem}: objeto de perfil sem as propriedades A e Ix.")
    raise ErroDeDados(f"{quem}: informe o perfil (objeto ou nome do catálogo) ou "
                      "diretamente a área A (cm²) e a inércia I (cm⁴).")


def _misula(m, I_viga: float, A_viga: float) -> Optional[Misula]:
    if m is None:
        return None
    if isinstance(m, Misula):
        mis = m
    elif isinstance(m, dict):
        mis = Misula(**m)
    else:
        try:
            comprimento, fator = m
        except (TypeError, ValueError):
            raise ErroDeDados(
                "Mísula: use Misula(comprimento, I=...) , um dicionário ou a dupla "
                "(comprimento_cm, fator_de_inércia).")
        mis = Misula(float(comprimento), fator=float(fator))
    if mis.comprimento <= 0:
        raise ErroDeDados(f"Mísula: comprimento {fmt(mis.comprimento, 1, 'cm')} "
                          "deve ser positivo.")
    if mis.I is None:
        if mis.fator is None:
            raise ErroDeDados("Mísula: informe a inércia I (cm⁴) ou o fator que multiplica "
                              "a inércia da viga.")
        if mis.fator < 1.0:
            raise ErroDeDados(f"Mísula: fator de inércia {fmt(mis.fator, 2)} < 1 — a mísula "
                              "aumenta a inércia, nunca a reduz.")
        mis = Misula(mis.comprimento, I=mis.fator * I_viga, A=mis.A, fator=mis.fator)
    if mis.A is None:
        mis = Misula(mis.comprimento, I=mis.I, A=A_viga, fator=mis.fator)
    return mis


def portico_galpao(vao: float, pe_direito: float, inclinacao: float,
                   base_rotulada: bool = True, misula=None,
                   pilar=None, viga=None,
                   A_pilar: Optional[float] = None, I_pilar: Optional[float] = None,
                   A_viga: Optional[float] = None, I_viga: Optional[float] = None,
                   E: float = E_ACO, rotula_cumeeira: bool = False,
                   nome: str = "pórtico de galpão") -> Modelo:
    """Pórtico transversal de duas águas, de alma cheia, pronto para receber cargas.

    vao         vão entre eixos dos pilares, cm
    pe_direito  altura do joelho (topo do pilar) acima da base, cm
    inclinacao  tangente da inclinação do telhado (0,10 = 10 %; θ = 5,71°)
    base_rotulada  True → apoio de 2º gênero; False → engaste
    misula      `Misula`, dicionário ou dupla (comprimento_cm, fator_de_inércia);
                representada por um trecho de maior inércia junto a cada joelho
    pilar/viga  `Perfil` do catálogo ou o nome dele; como alternativa, informe
                A_pilar/I_pilar e A_viga/I_viga
    rotula_cumeeira  libera a rotação na cumeeira (pórtico de três rótulas)

    Nós nomeados: A e E (bases), B e D (joelhos), C (cumeeira) e F1/F2 (fim das
    mísulas). Barras rotuladas: "pilar_esq", "misula_esq", "viga_esq", "viga_dir",
    "misula_dir", "pilar_dir". As barras são orientadas de modo que o momento
    positivo tracione a face inferior da viga e a face interna do pilar, como na
    Tabela 16.4 do manual.
    """
    if vao <= 0 or pe_direito <= 0:
        raise ErroDeDados(f"Pórtico: vão ({fmt(vao, 1, 'cm')}) e pé-direito "
                          f"({fmt(pe_direito, 1, 'cm')}) têm de ser positivos.")
    if not 0.0 <= inclinacao < 1.0:
        raise ErroDeDados(f"Inclinação {fmt(inclinacao, 3)} fora da faixa: informe a "
                          "tangente (0,10 = 10 %), entre 0 e 1.")
    Ap, Ip = _secao(pilar, A_pilar, I_pilar, "Pilar do pórtico")
    Av, Iv = _secao(viga, A_viga, I_viga, "Viga do pórtico")
    mis = _misula(misula, Iv, Av)

    apoio = "rotulado" if base_rotulada else "engastado"
    h_cumeeira = pe_direito + vao / 2.0 * inclinacao
    cos_t = 1.0 / math.sqrt(1.0 + inclinacao ** 2)
    meia_viga = (vao / 2.0) / cos_t

    if mis is not None and mis.comprimento >= meia_viga:
        raise ErroDeDados(
            f"Mísula de {fmt(mis.comprimento, 1, 'cm')} não cabe na meia-viga de "
            f"{fmt(meia_viga, 1, 'cm')}. Reduza o comprimento da mísula.")

    m = Modelo(nome)
    m.add_no(0.0, 0.0, apoio, "A")
    m.add_no(0.0, pe_direito, None, "B")
    m.add_no(vao / 2.0, h_cumeeira, None, "C")
    m.add_no(vao, pe_direito, None, "D")
    m.add_no(vao, 0.0, apoio, "E")

    m.add_barra("A", "B", Ap, Ip, E, "pilar_esq")
    if mis is not None:
        dx = mis.comprimento * cos_t
        m.add_no(dx, pe_direito + dx * inclinacao, None, "F1")
        m.add_no(vao - dx, pe_direito + dx * inclinacao, None, "F2")
        m.add_barra("B", "F1", mis.A, mis.I, E, "misula_esq")
        m.add_barra("F1", "C", Av, Iv, E, "viga_esq", rotula_f=rotula_cumeeira)
        m.add_barra("C", "F2", Av, Iv, E, "viga_dir", rotula_i=rotula_cumeeira)
        m.add_barra("F2", "D", mis.A, mis.I, E, "misula_dir")
    else:
        m.add_barra("B", "C", Av, Iv, E, "viga_esq", rotula_f=rotula_cumeeira)
        m.add_barra("C", "D", Av, Iv, E, "viga_dir", rotula_i=rotula_cumeeira)
    m.add_barra("D", "E", Ap, Ip, E, "pilar_dir")

    m.dados.update(vao=vao, pe_direito=pe_direito, inclinacao=inclinacao,
                   angulo_graus=math.degrees(math.atan(inclinacao)),
                   altura_cumeeira=h_cumeeira, comprimento_viga=meia_viga,
                   base_rotulada=base_rotulada,
                   misula=mis, A_pilar=Ap, I_pilar=Ip, A_viga=Av, I_viga=Iv,
                   barras_viga=(["misula_esq", "viga_esq", "viga_dir", "misula_dir"]
                                if mis is not None else ["viga_esq", "viga_dir"]),
                   barras_pilar=["pilar_esq", "pilar_dir"])
    return m


def viga_continua(vaos: Sequence[float], A: Optional[float] = None,
                  I: Optional[float] = None, perfil=None, E: float = E_ACO,
                  engaste_esq: bool = False, engaste_dir: bool = False,
                  balanco_esq: float = 0.0, balanco_dir: float = 0.0,
                  nome: str = "viga contínua") -> Modelo:
    """Viga contínua de n vãos sobre apoios simples — terças e longarinas contínuas.

    vaos         lista dos vãos, cm (pelo menos um)
    balanco_esq / balanco_dir  comprimento dos balanços de extremidade, cm
    engaste_esq / engaste_dir  engasta a extremidade em vez de apoiá-la

    Nós nomeados "apoio1", "apoio2", ... e, havendo balanço, "ponta_esq"/"ponta_dir".
    Barras rotuladas "balanco_esq", "vao1", "vao2", ..., "balanco_dir".
    """
    vaos = [float(v) for v in vaos]
    if not vaos:
        raise ErroDeDados("Viga contínua: informe pelo menos um vão.")
    for i, L in enumerate(vaos, 1):
        if L <= 0:
            raise ErroDeDados(f"Viga contínua: o vão {i} vale {fmt(L, 1, 'cm')}; "
                              "todos os vãos devem ser positivos.")
    if balanco_esq < 0 or balanco_dir < 0:
        raise ErroDeDados("Viga contínua: balanço não pode ser negativo.")
    Ax, Ix = _secao(perfil, A, I, "Viga contínua")

    m = Modelo(nome)
    x = 0.0
    if balanco_esq > 0:
        m.add_no(0.0, 0.0, None, "ponta_esq")
        x = balanco_esq
    # primeiro apoio: de 2º gênero (impede também a translação horizontal da viga)
    m.add_no(x, 0.0, "engastado" if engaste_esq else "rotulado", "apoio1")
    if balanco_esq > 0:
        m.add_barra("ponta_esq", "apoio1", Ax, Ix, E, "balanco_esq")
    for i, L in enumerate(vaos, 1):
        x += L
        ultimo = (i == len(vaos))
        if ultimo and engaste_dir:
            ap = "engastado"
        else:
            ap = "movel"
        m.add_no(x, 0.0, ap, f"apoio{i + 1}")
        m.add_barra(f"apoio{i}", f"apoio{i + 1}", Ax, Ix, E, f"vao{i}")
    if balanco_dir > 0:
        m.add_no(x + balanco_dir, 0.0, None, "ponta_dir")
        m.add_barra(f"apoio{len(vaos) + 1}", "ponta_dir", Ax, Ix, E, "balanco_dir")

    m.dados.update(vaos=vaos, balanco_esq=balanco_esq, balanco_dir=balanco_dir,
                   A=Ax, I=Ix, n_apoios=len(vaos) + 1)
    return m


def trelica(coordenadas: Sequence[Sequence[float]],
            barras: Sequence[Sequence],
            apoios: Union[Dict[int, Any], Sequence[Tuple[int, Any]]],
            A: Optional[float] = None, E: float = E_ACO,
            nomes: Optional[Sequence[str]] = None,
            nome: str = "treliça") -> Modelo:
    """Treliça plana: todas as barras rotuladas nas duas extremidades.

    coordenadas  [(x, y), ...] em cm
    barras       [(i, j), (i, j, A), (i, j, A, rótulo), ...]
    apoios       {índice ou nome do nó: apoio}, com apoio = "rotulado", "movel",
                 "engastado" ou a tripla (ux, uy, rz)
    A            área comum das barras, cm² (pode ser dada barra a barra)
    nomes        nome de cada nó, na ordem das coordenadas

    Como as duas extremidades são liberadas à rotação, a inércia I não influi no
    resultado (a parcela de flexão do elemento se anula na condensação estática):
    adota-se I = 1 cm⁴ apenas para satisfazer a validação do modelo. As rotações
    dos nós ficam sem rigidez e são travadas automaticamente pelo solver.
    """
    m = Modelo(nome)
    for k, (x, y) in enumerate(coordenadas):
        m.add_no(float(x), float(y), None, nomes[k] if nomes else "")
    itens = apoios.items() if isinstance(apoios, dict) else apoios
    for ref, ap in itens:
        m.nos[m.indice_no(ref)].apoio = _normaliza_apoio(ap)
    for k, b in enumerate(barras):
        i, j = b[0], b[1]
        Ab = float(b[2]) if len(b) > 2 and b[2] is not None else (
            float(A) if A is not None else None)
        if Ab is None or Ab <= 0:
            raise ErroDeDados(
                f"Treliça, barra {k}: informe a área A (cm²) da barra ou o parâmetro "
                "`A` comum a todas — em treliça hiperestática a área muda os esforços.")
        rot = b[3] if len(b) > 3 else f"b{k + 1}"
        m.add_barra(i, j, Ab, 1.0, E, rot, rotula_i=True, rotula_f=True)
    m.dados.update(tipo="treliça", n_barras=len(m.barras), n_nos=len(m.nos))
    return m


# =====================================================================================
# 8. Fórmulas fechadas de conferência — o "cheque à mão" do engenheiro
# =====================================================================================
#
# Soluções clássicas da Resistência dos Materiais (manual, Capítulo 4). Servem para
# mostrar no memorial, ao lado do resultado numérico, a ordem de grandeza esperada.
# Unidades: q em kN/cm, P em kN, L em cm, E em kN/cm², I em cm⁴;
#           M sai em kN·cm, V e R em kN, flecha em cm.

@dataclass
class Conferencia:
    """Resultado de uma fórmula fechada, com a memória de cálculo pronta."""
    caso: str
    titulo: str
    valores: Dict[str, float]
    unidades: Dict[str, str]
    passos: List[Passo]
    fonte: str = "Manual, Capítulo 4 (fundamentos de estática e resistência)"
    faixa: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def __getitem__(self, chave: str) -> float:
        if chave not in self.valores:
            raise ErroDeDados(f"'{chave}' não é um resultado de '{self.caso}'. "
                              f"Disponíveis: {sorted(self.valores)}.")
        return self.valores[chave]

    def comparar(self, chave: str, valor_numerico: float) -> float:
        """Diferença percentual do valor numérico em relação à fórmula fechada."""
        ref = self[chave]
        if ref == 0.0:
            return 0.0 if abs(valor_numerico) < 1e-9 else float("inf")
        return (abs(valor_numerico) - abs(ref)) / abs(ref) * 100.0

    def resumo(self) -> str:
        itens = ", ".join(f"{k} = {fmt(v, 2, self.unidades.get(k, ''))}"
                          for k, v in self.valores.items())
        return f"{self.titulo}: {itens}"


def _c(caso, titulo, valores, unidades, passos, faixa=None, fonte=None) -> Conferencia:
    c = Conferencia(caso, titulo, valores, unidades, passos, faixa=faixa or {})
    if fonte:
        c.fonte = fonte
    return c


def _exige(caso: str, dados: dict, *nomes: str) -> List[float]:
    faltando = [n for n in nomes if dados.get(n) is None]
    if faltando:
        raise ErroDeDados(f"Conferência '{caso}': faltam os dados {faltando}. "
                          f"Necessários: {list(nomes)} (q em kN/cm, P em kN, L em cm, "
                          "E em kN/cm², I em cm⁴).")
    vals = []
    for n in nomes:
        v = float(dados[n])
        if n in ("L", "E", "I") and v <= 0:
            raise ErroDeDados(f"Conferência '{caso}': {n} = {fmt(v, 3)} deve ser positivo.")
        vals.append(v)
    return vals


UNID_PADRAO = {"M": "kN·cm", "M_apoio": "kN·cm", "M_vao": "kN·cm", "M_max": "kN·cm",
               "M_joelho": "kN·cm", "M_cumeeira": "kN·cm", "M0": "kN·cm",
               "V": "kN", "V_max": "kN", "R": "kN", "R_esq": "kN", "R_dir": "kN",
               "R_central": "kN", "H": "kN", "flecha": "cm", "x_M_max": "cm"}


def _f_biapoiada_uniforme(d) -> Conferencia:
    q, L, Emod, I = _exige("biapoiada_uniforme", d, "q", "L", "E", "I")
    q = abs(q)
    M = q * L ** 2 / 8.0
    V = q * L / 2.0
    fl = 5.0 * q * L ** 4 / (384.0 * Emod * I)
    passos = [
        Passo("Momento máximo no meio do vão", "M = q·L²/8",
              f"{fmt(q, 4)} × {fmt(L, 1)}²/8", fmt(M, 1, "kN·cm")),
        Passo("Cortante máximo no apoio", "V = q·L/2",
              f"{fmt(q, 4)} × {fmt(L, 1)}/2", fmt(V, 1, "kN")),
        Passo("Flecha no meio do vão", "δ = 5·q·L⁴/(384·E·I)",
              f"5 × {fmt(q, 4)} × {fmt(L, 1)}⁴/(384 × {fmt(Emod, 0)} × {fmt(I, 0)})",
              fmt(fl, 3, "cm")),
    ]
    return _c("biapoiada_uniforme", "Viga biapoiada com carga uniforme",
              {"M": M, "M_max": M, "V": V, "V_max": V, "R": V, "flecha": fl,
               "x_M_max": L / 2.0}, UNID_PADRAO, passos)


def _f_biapoiada_concentrada(d) -> Conferencia:
    P, L, Emod, I = _exige("biapoiada_concentrada", d, "P", "L", "E", "I")
    P = abs(P)
    a = float(d.get("a", L / 2.0))
    if not 0.0 < a < L:
        raise ErroDeDados(f"Conferência: a = {fmt(a, 1, 'cm')} tem de ficar entre 0 e L.")
    b = L - a
    M = P * a * b / L
    R1, R2 = P * b / L, P * a / L
    if abs(a - L / 2.0) < 1e-9:
        fl = P * L ** 3 / (48.0 * Emod * I)
        fórmula_fl = "δ = P·L³/(48·E·I)"
    else:                      # flecha máxima da carga fora do meio (Timoshenko)
        c_ = max(a, b)
        d_ = L - c_
        fl = P * d_ * (L ** 2 - d_ ** 2) ** 1.5 / (9.0 * math.sqrt(3.0) * Emod * I * L)
        fórmula_fl = "δ = P·b·(L² − b²)^{3/2}/(9√3·E·I·L)"
    passos = [
        Passo("Reações de apoio", "R₁ = P·b/L ; R₂ = P·a/L",
              f"{fmt(P, 1)} × {fmt(b, 1)}/{fmt(L, 1)}", fmt(R1, 1, "kN")),
        Passo("Momento sob a carga", "M = P·a·b/L",
              f"{fmt(P, 1)} × {fmt(a, 1)} × {fmt(b, 1)}/{fmt(L, 1)}", fmt(M, 1, "kN·cm")),
        Passo("Flecha máxima", fórmula_fl, "", fmt(fl, 3, "cm")),
    ]
    return _c("biapoiada_concentrada", "Viga biapoiada com carga concentrada",
              {"M": M, "M_max": M, "V": max(R1, R2), "V_max": max(R1, R2),
               "R_esq": R1, "R_dir": R2, "flecha": fl, "x_M_max": a},
              UNID_PADRAO, passos)


def _f_balanco_uniforme(d) -> Conferencia:
    q, L, Emod, I = _exige("balanco_uniforme", d, "q", "L", "E", "I")
    q = abs(q)
    M = q * L ** 2 / 2.0
    V = q * L
    fl = q * L ** 4 / (8.0 * Emod * I)
    passos = [
        Passo("Momento no engaste", "M = q·L²/2",
              f"{fmt(q, 4)} × {fmt(L, 1)}²/2", fmt(M, 1, "kN·cm")),
        Passo("Cortante no engaste", "V = q·L", f"{fmt(q, 4)} × {fmt(L, 1)}", fmt(V, 1, "kN")),
        Passo("Flecha na ponta", "δ = q·L⁴/(8·E·I)",
              f"{fmt(q, 4)} × {fmt(L, 1)}⁴/(8 × {fmt(Emod, 0)} × {fmt(I, 0)})",
              fmt(fl, 3, "cm")),
    ]
    return _c("balanco_uniforme", "Balanço com carga uniforme",
              {"M": M, "M_max": M, "M_apoio": M, "V": V, "V_max": V, "R": V,
               "flecha": fl, "x_M_max": 0.0}, UNID_PADRAO, passos)


def _f_balanco_concentrada(d) -> Conferencia:
    P, L, Emod, I = _exige("balanco_concentrada", d, "P", "L", "E", "I")
    P = abs(P)
    M = P * L
    fl = P * L ** 3 / (3.0 * Emod * I)
    passos = [
        Passo("Momento no engaste", "M = P·L", f"{fmt(P, 1)} × {fmt(L, 1)}", fmt(M, 1, "kN·cm")),
        Passo("Flecha na ponta", "δ = P·L³/(3·E·I)", "", fmt(fl, 3, "cm")),
    ]
    return _c("balanco_concentrada", "Balanço com carga na ponta",
              {"M": M, "M_max": M, "M_apoio": M, "V": P, "V_max": P, "R": P,
               "flecha": fl, "x_M_max": 0.0}, UNID_PADRAO, passos)


def _f_biengastada_uniforme(d) -> Conferencia:
    q, L, Emod, I = _exige("biengastada_uniforme", d, "q", "L", "E", "I")
    q = abs(q)
    Ma = q * L ** 2 / 12.0
    Mv = q * L ** 2 / 24.0
    V = q * L / 2.0
    fl = q * L ** 4 / (384.0 * Emod * I)
    passos = [
        Passo("Momento nos engastes", "M = q·L²/12",
              f"{fmt(q, 4)} × {fmt(L, 1)}²/12", fmt(Ma, 1, "kN·cm")),
        Passo("Momento no meio do vão", "M = q·L²/24",
              f"{fmt(q, 4)} × {fmt(L, 1)}²/24", fmt(Mv, 1, "kN·cm")),
        Passo("Flecha no meio do vão", "δ = q·L⁴/(384·E·I)", "", fmt(fl, 3, "cm")),
    ]
    return _c("biengastada_uniforme", "Viga biengastada com carga uniforme",
              {"M_apoio": Ma, "M_vao": Mv, "M_max": Ma, "V": V, "V_max": V, "R": V,
               "flecha": fl, "x_M_max": 0.0}, UNID_PADRAO, passos)


def _f_biengastada_concentrada(d) -> Conferencia:
    P, L, Emod, I = _exige("biengastada_concentrada", d, "P", "L", "E", "I")
    P = abs(P)
    M = P * L / 8.0
    fl = P * L ** 3 / (192.0 * Emod * I)
    passos = [
        Passo("Momento nos engastes e no meio", "M = P·L/8",
              f"{fmt(P, 1)} × {fmt(L, 1)}/8", fmt(M, 1, "kN·cm")),
        Passo("Flecha no meio do vão", "δ = P·L³/(192·E·I)", "", fmt(fl, 3, "cm")),
    ]
    return _c("biengastada_concentrada", "Viga biengastada com carga no meio do vão",
              {"M_apoio": M, "M_vao": M, "M_max": M, "V": P / 2.0, "V_max": P / 2.0,
               "R": P / 2.0, "flecha": fl, "x_M_max": 0.0}, UNID_PADRAO, passos)


def _f_engastada_apoiada_uniforme(d) -> Conferencia:
    q, L, Emod, I = _exige("engastada_apoiada_uniforme", d, "q", "L", "E", "I")
    q = abs(q)
    Ma = q * L ** 2 / 8.0
    Mv = 9.0 * q * L ** 2 / 128.0
    R1, R2 = 5.0 * q * L / 8.0, 3.0 * q * L / 8.0
    fl = q * L ** 4 / (185.0 * Emod * I)
    passos = [
        Passo("Momento no engaste", "M = q·L²/8", "", fmt(Ma, 1, "kN·cm")),
        Passo("Momento máximo no vão (x = 5L/8)", "M = 9·q·L²/128", "", fmt(Mv, 1, "kN·cm")),
        Passo("Reações", "R_engaste = 5·q·L/8 ; R_apoio = 3·q·L/8", "", fmt(R1, 1, "kN")),
        Passo("Flecha máxima", "δ ≈ q·L⁴/(185·E·I)", "", fmt(fl, 3, "cm")),
    ]
    return _c("engastada_apoiada_uniforme", "Viga engastada-apoiada com carga uniforme",
              {"M_apoio": Ma, "M_vao": Mv, "M_max": Ma, "V": R1, "V_max": R1,
               "R_esq": R1, "R_dir": R2, "flecha": fl, "x_M_max": 5.0 * L / 8.0},
              UNID_PADRAO, passos)


def _f_continua_dois_vaos(d) -> Conferencia:
    q, L, Emod, I = _exige("continua_dois_vaos_uniforme", d, "q", "L", "E", "I")
    q = abs(q)
    Ma = q * L ** 2 / 8.0
    Mv = 9.0 * q * L ** 2 / 128.0
    Rc = 1.25 * q * L
    Re = 0.375 * q * L
    fl = q * L ** 4 / (185.0 * Emod * I)
    passos = [
        Passo("Momento negativo sobre o apoio central", "M = q·L²/8",
              f"{fmt(q, 4)} × {fmt(L, 1)}²/8", fmt(Ma, 1, "kN·cm")),
        Passo("Momento positivo no vão (x = 0,375 L)", "M = 9·q·L²/128", "",
              fmt(Mv, 1, "kN·cm")),
        Passo("Reação do apoio central", "R = 1,25·q·L",
              f"1,25 × {fmt(q, 4)} × {fmt(L, 1)}", fmt(Rc, 1, "kN")),
        Passo("Reações das extremidades", "R = 0,375·q·L", "", fmt(Re, 1, "kN")),
        Passo("Flecha máxima do vão", "δ ≈ q·L⁴/(185·E·I)", "", fmt(fl, 3, "cm")),
    ]
    return _c("continua_dois_vaos_uniforme", "Viga contínua de dois vãos iguais",
              {"M_apoio": Ma, "M_vao": Mv, "M_max": Ma, "R_central": Rc, "R_esq": Re,
               "R_dir": Re, "V": 0.625 * q * L, "V_max": 0.625 * q * L, "flecha": fl,
               "x_M_max": L}, UNID_PADRAO, passos)


def _f_portico_biarticulado(d) -> Conferencia:
    q, L, h = _exige("portico_biarticulado", d, "q", "L", "h")
    Iv, Ip = _exige("portico_biarticulado", d, "I_viga", "I_pilar")
    q = abs(q)
    k = (Iv / L) / (Ip / h)
    H = q * L ** 2 / (4.0 * h * (2.0 * k + 3.0))
    M_no = H * h
    M0 = q * L ** 2 / 8.0
    M_vao = M0 - M_no
    passos = [
        Passo("Rigidez relativa viga/pilar", "k = (I_viga/L)/(I_pilar/h)",
              f"({fmt(Iv, 0)}/{fmt(L, 1)})/({fmt(Ip, 0)}/{fmt(h, 1)})", fmt(k, 3)),
        Passo("Empuxo horizontal nas bases", "H = q·L²/[4·h·(2k + 3)]",
              f"{fmt(q, 4)} × {fmt(L, 1)}²/[4 × {fmt(h, 1)} × (2 × {fmt(k, 3)} + 3)]",
              fmt(H, 1, "kN")),
        Passo("Momento no nó (canto)", "M = H·h", f"{fmt(H, 1)} × {fmt(h, 1)}",
              fmt(M_no, 1, "kN·cm")),
        Passo("Momento no meio do vão", "M = q·L²/8 − H·h",
              f"{fmt(M0, 1)} − {fmt(M_no, 1)}", fmt(M_vao, 1, "kN·cm")),
    ]
    return _c("portico_biarticulado", "Pórtico retangular biarticulado, carga uniforme na viga",
              {"H": H, "M_joelho": M_no, "M_no": M_no, "M_vao": M_vao, "M0": M0,
               "R": q * L / 2.0, "V": q * L / 2.0},
              dict(UNID_PADRAO, M_no="kN·cm"), passos)


def _f_portico_duas_aguas(d) -> Conferencia:
    q, L = _exige("portico_duas_aguas_biarticulado", d, "q", "L")
    q = abs(q)
    M0 = q * L ** 2 / 8.0
    faixa_joelho = (0.50 * M0, 0.60 * M0)
    faixa_cumeeira = (0.30 * M0, 0.40 * M0)
    passos = [
        Passo("Viga biapoiada equivalente", "M₀ = q·L²/8",
              f"{fmt(q, 4)} × {fmt(L, 1)}²/8", fmt(M0, 1, "kN·cm")),
        Passo("Faixa esperada do momento de joelho", "M_joelho = (0,50 a 0,60)·M₀",
              f"({fmt(faixa_joelho[0], 1)} a {fmt(faixa_joelho[1], 1)})",
              fmt(0.55 * M0, 1, "kN·cm"), "Manual, Capítulo 16, Passo 4"),
        Passo("Faixa esperada do momento de cumeeira", "M_cumeeira = (0,30 a 0,40)·M₀",
              f"({fmt(faixa_cumeeira[0], 1)} a {fmt(faixa_cumeeira[1], 1)})",
              fmt(0.35 * M0, 1, "kN·cm"), "Manual, Capítulo 16, Passo 4"),
    ]
    c = _c("portico_duas_aguas_biarticulado",
           "Pórtico biarticulado de duas águas (ordem de grandeza)",
           {"M0": M0, "M_joelho": 0.55 * M0, "M_cumeeira": 0.35 * M0, "R": q * L / 2.0},
           UNID_PADRAO, passos,
           faixa={"M_joelho": faixa_joelho, "M_cumeeira": faixa_cumeeira},
           fonte="Manual, Capítulo 16, Passo 4 — válido para I_pilar ≈ 1,5·I_viga "
                 "e h/L ≈ 0,3, com base rotulada")
    return c


FORMULAS = {
    "biapoiada_uniforme": _f_biapoiada_uniforme,
    "biapoiada_concentrada": _f_biapoiada_concentrada,
    "balanco_uniforme": _f_balanco_uniforme,
    "balanco_concentrada": _f_balanco_concentrada,
    "biengastada_uniforme": _f_biengastada_uniforme,
    "biengastada_concentrada": _f_biengastada_concentrada,
    "engastada_apoiada_uniforme": _f_engastada_apoiada_uniforme,
    "continua_dois_vaos_uniforme": _f_continua_dois_vaos,
    "portico_biarticulado": _f_portico_biarticulado,
    "portico_duas_aguas_biarticulado": _f_portico_duas_aguas,
}


def conferir_por_formula(caso: str, **dados) -> Conferencia:
    """Solução clássica de conferência — o "cheque à mão" ao lado do resultado numérico.

    Casos disponíveis em `FORMULAS`. Dados esperados (unidades internas do sistema):
        q (kN/cm), P (kN), a (cm), L (cm), h (cm), E (kN/cm²), I, I_viga, I_pilar (cm⁴).

    >>> c = conferir_por_formula("biapoiada_uniforme", q=0.10, L=600, E=20000, I=7407.6)
    >>> round(c["M"], 1), round(c["flecha"], 2)
    (4500.0, 1.14)
    """
    if caso not in FORMULAS:
        raise ErroDeDados(f"Caso de conferência '{caso}' desconhecido. "
                          f"Disponíveis: {sorted(FORMULAS)}.")
    dados.setdefault("E", E_ACO)
    return FORMULAS[caso](dados)
