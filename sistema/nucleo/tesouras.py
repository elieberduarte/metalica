# -*- coding: utf-8 -*-
"""Tesouras e pórticos treliçados: a geometria, o modelo de análise e os perfis.

O pórtico de alma cheia resolve o galpão com duas peças (pilar e viga). A tesoura
resolve com quatro famílias — banzo superior, banzo inferior, diagonais e montantes —
e é o que a fábrica mais produz, porque troca chapa grossa por perfil leve dobrado.

Este módulo sabe três coisas, e só elas:

1. **desenhar a malha** (`geometria`): onde ficam os nós e quais barras os ligam, para
   cada formato de tesoura e cada arranjo de diagonais;
2. **montar o modelo de análise** (`montar`): banzos contínuos (elementos de pórtico,
   porque a terça carrega o banzo superior entre os nós e ali há flexão local),
   diagonais e montantes rotulados nas duas pontas, pilares de alma cheia;
3. **escolher o perfil** (`menor_perfil`): o mais leve do catálogo que passa na
   verificação do membro, família por família.

Quem carrega, combina e imprime é o `nucleo/galpao.py`. Aqui não há carga nem norma
além da verificação do membro, que vem de `nucleo/verificar.py`.

Unidades: cm e kN, como no resto da análise. Na interface o usuário fala em metros.

    Eixo do modelo, com o banzo inferior no topo do pilar (y = pé-direito):

        formato "trapezoidal"          formato "banzos paralelos"    "triangular"
        ____/\\____                     ____/\\____                    ____/\\____
       |__________|  h no apoio        \\__________/  h constante      (h = 0 no apoio)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import catalogo, verificar
from .analise import E_ACO, Modelo
from .base import ErroDeDados, Resultado, fmt
from .perfis import Perfil

__all__ = ["FORMATOS", "DIAGONAIS", "PAPEIS", "Tesoura", "geometria", "montar",
           "altura_padrao", "paineis_padrao", "menor_perfil", "candidatos",
           "perfil_proximo", "FAMILIAS_POR_PAPEL", "candidatos_verificados"]

#: Formato da tesoura: o que cada um faz com os dois banzos.
FORMATOS: Dict[str, str] = {
    "trapezoidal": "banzo inferior horizontal e banzo superior em duas águas; a altura "
                   "cresce do apoio para a cumeeira — o formato mais usado em galpão",
    "banzos paralelos": "os dois banzos acompanham a inclinação, com altura constante; "
                        "todas as diagonais saem iguais e a fabricação é a mais simples",
    "triangular": "banzo inferior horizontal e altura nula no apoio (tesoura clássica); "
                  "só fecha bem com telhado inclinado, porque a altura vem da inclinação",
}

#: Arranjo das barras internas.
DIAGONAIS: Dict[str, str] = {
    "Howe": "montantes verticais e diagonais caindo para o apoio; sob gravidade as "
            "diagonais comprimem e os montantes tracionam",
    "Pratt": "montantes verticais e diagonais caindo para a cumeeira; sob gravidade as "
             "diagonais tracionam, o que permite peça mais leve",
    "Warren": "sem montantes: só diagonais em zigue-zague, com os nós do banzo inferior "
              "no meio do painel — menos peças e menos chapas de nó",
}

#: Famílias de barra da tesoura, na ordem em que o memorial mostra.
PAPEIS: Tuple[str, ...] = ("banzo superior", "banzo inferior", "diagonal", "montante")

#: Prefixo do rótulo de cada papel, usado nas barras do modelo e no mapa de esforços.
_PREFIXO = {"banzo superior": "bs", "banzo inferior": "bi",
            "diagonal": "diag", "montante": "mont"}

#: Famílias do catálogo oferecidas a cada papel, em ordem de preferência.
FAMILIAS_POR_PAPEL: Dict[str, Tuple[str, ...]] = {
    "banzo superior": ("Ue", "U"),
    "banzo inferior": ("Ue", "U"),
    "diagonal": ("L", "U", "Ue"),
    "montante": ("L", "U", "Ue"),
}

MIN_ALTURA_APOIO = 15.0          # cm — abaixo disso não cabe ligação no apoio

#: Espessura mínima de parede aceita numa barra de tesoura, mm. Não é limite de norma:
#: é o que a fábrica dobra e o que chega à obra sem amassar. Chapa mais fina do que isso
#: passa na conta e não passa no transporte.
MIN_ESPESSURA = 2.0
TOL = 1e-6


# =====================================================================================
# 1. Geometria
# =====================================================================================

@dataclass
class No:
    """Um nó da tesoura, em cm, no sistema local (y = 0 no banzo inferior do apoio)."""
    nome: str
    x: float
    y: float
    banzo: str                   # "superior" ou "inferior"


@dataclass
class Barra:
    """Uma barra da tesoura, pelos nomes dos nós."""
    rotulo: str
    i: str
    j: str
    papel: str


@dataclass
class Tesoura:
    """A malha pronta: nós, barras e as medidas que o desenho e o memorial usam."""
    vao: float                   # cm, entre eixos de pilares
    inclinacao: float            # tangente
    formato: str
    diagonais: str
    altura_apoio: float          # cm, entre banzos no apoio (0 na triangular)
    paineis: int                 # painéis do banzo superior por água
    nos: List[No] = field(default_factory=list)
    barras: List[Barra] = field(default_factory=list)

    # --- consultas ---
    def no(self, nome: str) -> No:
        for n in self.nos:
            if n.nome == nome:
                return n
        raise ErroDeDados("nó %s não existe na tesoura." % nome)

    def comprimento(self, b: Barra) -> float:
        a, c = self.no(b.i), self.no(b.j)
        return math.hypot(c.x - a.x, c.y - a.y)

    def do_papel(self, papel: str) -> List[Barra]:
        return [b for b in self.barras if b.papel == papel]

    def rotulos(self, papel: str) -> List[str]:
        return [b.rotulo for b in self.do_papel(papel)]

    @property
    def altura_cumeeira(self) -> float:
        """Altura da tesoura na cumeeira, entre banzos, cm."""
        if self.formato == "banzos paralelos":
            return self.altura_apoio
        return self.altura_apoio + self.vao / 2.0 * self.inclinacao

    @property
    def flecha(self) -> float:
        """Altura total da tesoura, do banzo inferior no apoio à cumeeira, cm."""
        return self.altura_apoio + self.vao / 2.0 * self.inclinacao

    @property
    def painel(self) -> float:
        """Comprimento de um painel do banzo superior, medido na inclinação, cm."""
        cos_t = 1.0 / math.sqrt(1.0 + self.inclinacao ** 2)
        return (self.vao / 2.0) / cos_t / self.paineis

    def comprimento_total(self, papel: str) -> float:
        return sum(self.comprimento(b) for b in self.do_papel(papel))

    def resumo(self) -> dict:
        return {
            "formato": self.formato, "diagonais": self.diagonais,
            "vao_m": round(self.vao / 100.0, 2),
            "altura_apoio_m": round(self.altura_apoio / 100.0, 3),
            "altura_cumeeira_m": round(self.altura_cumeeira / 100.0, 3),
            "flecha_m": round(self.flecha / 100.0, 3),
            "paineis_por_agua": self.paineis,
            "painel_m": round(self.painel / 100.0, 3),
            "nos": len(self.nos),
            "barras": len(self.barras),
            "pecas": {p: len(self.do_papel(p)) for p in PAPEIS if self.do_papel(p)},
            "comprimentos_m": {p: round(self.comprimento_total(p) / 100.0, 2)
                               for p in PAPEIS if self.do_papel(p)},
        }


def altura_padrao(vao: float, formato: str, inclinacao: float) -> float:
    """Altura da tesoura no apoio (cm) quando o usuário não escolhe.

    Trapezoidal: vão/25 no apoio, o que dá perto de vão/12 na cumeeira com 10 % de
    inclinação. Banzos paralelos: vão/12, porque aí a altura é a mesma do apoio à
    cumeeira e é ela sozinha que vence o vão. Triangular: zero — a altura vem toda da
    inclinação do telhado.
    """
    if formato == "triangular":
        return 0.0
    if formato == "banzos paralelos":
        return max(40.0, vao / 12.0)
    return max(MIN_ALTURA_APOIO * 2, vao / 25.0)


def paineis_padrao(vao: float, inclinacao: float, espacamento_tercas: float) -> int:
    """Painéis por água, escolhidos para o nó do banzo superior cair perto da terça.

    Terça fora do nó não é erro — o banzo superior é contínuo e o cálculo pega a flexão
    local —, mas nó e terça juntos tiram a flexão e é assim que se detalha.
    """
    cos_t = 1.0 / math.sqrt(1.0 + inclinacao ** 2)
    agua = (vao / 2.0) / cos_t
    alvo = max(espacamento_tercas, 60.0)
    return max(2, min(14, int(round(agua / alvo))))


def _malha(formato: str, diagonais: str, paineis: int) -> Tuple[List[float], List[Tuple]]:
    """Posições relativas dos nós inferiores e a lista de barras internas.

    Devolve (`t_inferiores`, `web`), com `t` medido em painéis (0 no apoio esquerdo,
    2·paineis no direito) e cada item de `web` na forma (papel, ponta_i, ponta_j), em
    que cada ponta é ("sup", k) ou ("inf", t).
    """
    m = 2 * paineis
    web: List[Tuple] = []
    if diagonais == "Warren":
        # nós inferiores no meio do painel, mais os dois do apoio
        t_inf = [0.0] + [k + 0.5 for k in range(m)] + [float(m)]
        for k in range(m):
            web.append(("diagonal", ("sup", k), ("inf", k + 0.5)))
            web.append(("diagonal", ("inf", k + 0.5), ("sup", k + 1)))
        return t_inf, web

    t_inf = [float(k) for k in range(m + 1)]
    for k in range(1, m):
        web.append(("montante", ("sup", k), ("inf", float(k))))
    for k in range(m):
        primeira_agua = k < paineis
        if (diagonais == "Howe") == primeira_agua:
            # Howe à esquerda e Pratt à direita: a diagonal desce indo para a cumeeira
            web.append(("diagonal", ("sup", k + 1), ("inf", float(k))))
        else:
            web.append(("diagonal", ("sup", k), ("inf", float(k + 1))))
    return t_inf, web


def geometria(vao: float, inclinacao: float, formato: str = "trapezoidal",
              diagonais: str = "Howe", altura_apoio: float = 0.0,
              paineis: int = 0, espacamento_tercas: float = 160.0) -> Tesoura:
    """Monta a malha da tesoura. Medidas em cm, `inclinacao` é a tangente (0,10 = 10 %)."""
    if formato not in FORMATOS:
        raise ErroDeDados("Formato de tesoura \"%s\" desconhecido. Use um de: %s."
                          % (formato, ", ".join(FORMATOS)))
    if diagonais not in DIAGONAIS:
        raise ErroDeDados("Arranjo de diagonais \"%s\" desconhecido. Use um de: %s."
                          % (diagonais, ", ".join(DIAGONAIS)))
    if vao <= 0:
        raise ErroDeDados("Tesoura: o vão tem de ser positivo.")
    if not 0.0 <= inclinacao < 1.0:
        raise ErroDeDados("Tesoura: informe a inclinação como tangente, entre 0 e 1.")

    h0 = float(altura_apoio) if altura_apoio and altura_apoio > 0 else altura_padrao(vao, formato, inclinacao)
    if formato == "triangular":
        h0 = 0.0
    elif h0 < MIN_ALTURA_APOIO:
        raise ErroDeDados("Altura da tesoura no apoio de %s é pequena demais para caber a "
                          "ligação; use pelo menos %s ou escolha a tesoura triangular."
                          % (fmt(h0 / 100, 2, "m"), fmt(MIN_ALTURA_APOIO / 100, 2, "m")))
    n = int(paineis) if paineis and paineis > 0 else paineis_padrao(vao, inclinacao, espacamento_tercas)
    if n < 2:
        raise ErroDeDados("Tesoura: são necessários pelo menos 2 painéis por água.")
    if formato == "triangular" and vao / 2.0 * inclinacao < vao / 25.0:
        raise ErroDeDados(
            "Tesoura triangular com %s de vão e %s%% de inclinação fica com só %s de altura "
            "na cumeeira (menos de vão/25): não vence o vão. Suba a inclinação do telhado ou "
            "escolha a tesoura trapezoidal." % (fmt(vao / 100, 1, "m"), fmt(inclinacao * 100, 1),
                                                fmt(vao / 2.0 * inclinacao / 100, 2, "m")))

    t = Tesoura(vao=vao, inclinacao=inclinacao, formato=formato, diagonais=diagonais,
                altura_apoio=h0, paineis=n)
    m = 2 * n
    dx = vao / m                       # projeção horizontal de um painel

    def y_sup(x: float) -> float:
        return h0 + inclinacao * min(x, vao - x)

    def y_inf(x: float) -> float:
        return 0.0 if formato != "banzos paralelos" else y_sup(x) - h0

    for k in range(m + 1):
        x = k * dx
        t.nos.append(No("TS%d" % k, x, y_sup(x), "superior"))
    t_inf, web = _malha(formato, diagonais, n)
    for tt in t_inf:
        x = tt * dx
        t.nos.append(No(_nome_inf(tt), x, y_inf(x), "inferior"))

    # banzos: uma barra por painel, na ordem, porque a continuidade importa
    for k in range(m):
        t.barras.append(Barra("bs%d" % (k + 1), "TS%d" % k, "TS%d" % (k + 1), "banzo superior"))
    for a, b in zip(t_inf, t_inf[1:]):
        t.barras.append(Barra("bi%d" % (len(t.do_papel("banzo inferior")) + 1),
                              _nome_inf(a), _nome_inf(b), "banzo inferior"))
    # montantes de extremidade: fecham a tesoura no apoio (só existem se houver altura)
    if h0 > TOL:
        t.barras.append(Barra("mont_esq", "TS0", _nome_inf(0.0), "montante"))
        t.barras.append(Barra("mont_dir", "TS%d" % m, _nome_inf(float(m)), "montante"))
    contas = {"diagonal": 0, "montante": 0}
    for papel, pi, pj in web:
        contas[papel] += 1
        t.barras.append(Barra("%s%d" % (_PREFIXO[papel], contas[papel]),
                              _ponta(pi), _ponta(pj), papel))
    # nó solto (altura zero no apoio) some: a ponta do banzo superior é a do inferior
    if h0 <= TOL:
        _fundir(t, "TS0", _nome_inf(0.0))
        _fundir(t, "TS%d" % m, _nome_inf(float(m)))
    return t


def _nome_inf(t: float) -> str:
    return "BI%s" % (("%g" % t).replace(".", "_"))


def _ponta(p: Tuple) -> str:
    return ("TS%d" % p[1]) if p[0] == "sup" else _nome_inf(p[1])


def _fundir(t: Tesoura, mantido: str, removido: str):
    """Funde dois nós coincidentes (apoio da tesoura triangular).

    Na tesoura triangular o banzo superior encontra o inferior no apoio, e a primeira
    diagonal passa a ligar os mesmos nós de um dos banzos. Essa barra repetida sai: o
    painel do apoio fica fechado pelo montante seguinte, como se detalha na prática.
    """
    t.nos = [n for n in t.nos if n.nome != removido]
    for b in t.barras:
        if b.i == removido:
            b.i = mantido
        if b.j == removido:
            b.j = mantido
    vistos, limpas = set(), []
    for b in t.barras:
        chave = frozenset((b.i, b.j))
        if b.i == b.j or chave in vistos:
            continue
        vistos.add(chave)
        limpas.append(b)
    t.barras = limpas


# =====================================================================================
# 2. Modelo de análise
# =====================================================================================

def montar(t: Tesoura, pe_direito: float, secoes: Dict[str, Tuple[float, float]],
           base_rotulada: bool = False, ligacao: str = "apoiada",
           E: float = E_ACO, nome: str = "pórtico treliçado") -> Modelo:
    """Tesoura sobre dois pilares, pronta para receber carga.

    `secoes` traz (A, I) de cada papel e do "pilar", em cm² e cm⁴.

    Os banzos entram como elementos de pórtico (contínuos): é o banzo superior que
    recebe a terça entre os nós, e ignorar essa flexão local subestima justamente a
    barra mais solicitada. Diagonais e montantes entram rotulados nas duas pontas.

    `ligacao` diz como a tesoura chega ao pilar:

    * ``"apoiada"`` — a tesoura se apoia no topo do pilar, sem transmitir momento. É o
      caso usual, e então o pilar precisa de base engastada, senão o pórtico é um
      mecanismo no plano transversal;
    * ``"rígida"`` — o pilar sobe até o banzo superior e recebe os dois banzos, formando
      o joelho do pórtico treliçado. Aí a base pode ser rotulada.
    """
    if ligacao not in ("apoiada", "rígida"):
        raise ErroDeDados("Ligação da tesoura \"%s\" desconhecida: use \"apoiada\" ou \"rígida\"." % ligacao)
    if ligacao == "apoiada" and base_rotulada:
        raise ErroDeDados(
            "Tesoura apoiada sobre pilar de base rotulada é um mecanismo no plano do "
            "pórtico: não há o que segure o galpão contra o vento transversal. Engaste a "
            "base do pilar ou ligue a tesoura rigidamente ao pilar.")
    if ligacao == "rígida" and t.altura_apoio <= TOL:
        raise ErroDeDados(
            "A tesoura triangular chega ao pilar num ponto só e não forma joelho rígido. "
            "Escolha a ligação apoiada (com base engastada) ou a tesoura trapezoidal.")
    faltando = [p for p in list(PAPEIS) + ["pilar"]
                if (t.do_papel(p) or p == "pilar") and p not in secoes]
    if faltando:
        raise ErroDeDados("Faltam as seções de: %s." % ", ".join(faltando))

    m = Modelo(nome)
    apoio = "rotulado" if base_rotulada else "engastado"
    m.add_no(0.0, 0.0, apoio, "A")
    m.add_no(t.vao, 0.0, apoio, "E")
    for n in t.nos:
        m.add_no(n.x, pe_direito + n.y, None, n.nome)

    Ap, Ip = secoes["pilar"]
    no_esq_inf, no_dir_inf = _nome_inf(0.0), _nome_inf(float(2 * t.paineis))
    if t.altura_apoio <= TOL:                      # tesoura triangular: os nós fundiram
        no_esq_inf, no_dir_inf = "TS0", "TS%d" % (2 * t.paineis)

    if ligacao == "rígida":
        # o pilar sobe até o banzo superior e vira o montante de extremidade
        m.add_barra("A", no_esq_inf, Ap, Ip, E, "pilar_esq")
        m.add_barra(no_esq_inf, "TS0", Ap, Ip, E, "joelho_esq")
        m.add_barra("E", no_dir_inf, Ap, Ip, E, "pilar_dir")
        m.add_barra(no_dir_inf, "TS%d" % (2 * t.paineis), Ap, Ip, E, "joelho_dir")
        barras_pular = {"mont_esq", "mont_dir"}
        # O joelho rígido é o binário entre os dois banzos, que chegam ao pilar em
        # alturas diferentes. Cada banzo chega rotulado: fosse engastado, o momento do
        # joelho viraria flexão no banzo — o que não é o caminho de força da treliça, e
        # pedia um banzo desproporcional.
        nos_do_pilar = {"TS0", "TS%d" % (2 * t.paineis), no_esq_inf, no_dir_inf}
    else:
        m.add_barra("A", no_esq_inf, Ap, Ip, E, "pilar_esq", rotula_f=True)
        m.add_barra("E", no_dir_inf, Ap, Ip, E, "pilar_dir", rotula_f=True)
        barras_pular = set()
        nos_do_pilar = set()

    for b in t.barras:
        if b.rotulo in barras_pular:
            continue
        A, I = secoes[b.papel]
        rotulada = b.papel in ("diagonal", "montante")
        m.add_barra(b.i, b.j, A, I, E, b.rotulo,
                    rotula_i=rotulada or b.i in nos_do_pilar,
                    rotula_f=rotulada or b.j in nos_do_pilar)

    meio = t.paineis
    pil_esq = ["pilar_esq"] + (["joelho_esq"] if ligacao == "rígida" else [])
    pil_dir = ["pilar_dir"] + (["joelho_dir"] if ligacao == "rígida" else [])
    m.dados.update(
        tipo="tesoura", formato=t.formato, diagonais=t.diagonais, vao=t.vao,
        pe_direito=pe_direito, inclinacao=t.inclinacao, ligacao=ligacao,
        base_rotulada=base_rotulada, altura_apoio=t.altura_apoio,
        altura_cumeeira=pe_direito + t.altura_apoio + t.vao / 2.0 * t.inclinacao,
        paineis=t.paineis, painel=t.painel,
        barras_agua_esq=["bs%d" % k for k in range(1, meio + 1)],
        barras_agua_dir=["bs%d" % k for k in range(meio + 1, 2 * meio + 1)],
        barras_pilar=pil_esq + pil_dir,
        barras_pilar_esq=pil_esq, barras_pilar_dir=pil_dir,
        no_joelho=no_esq_inf, no_apoio_esq=no_esq_inf, no_apoio_dir=no_dir_inf,
        no_cumeeira="TS%d" % meio,
        barras_por_papel={p: [b.rotulo for b in t.do_papel(p) if b.rotulo not in barras_pular]
                          for p in PAPEIS if t.do_papel(p)},
        barras_viga=["bs%d" % k for k in range(1, 2 * meio + 1)],
    )
    return m


def perfil_proximo(familias: Sequence[str], altura_mm: float) -> Perfil:
    """Perfil do catálogo com a altura de seção mais próxima — semente do laço."""
    lista = candidatos(familias)
    if not lista:
        raise ErroDeDados("catálogo sem perfis das famílias %s." % ", ".join(familias))
    return min(lista, key=lambda p: (abs(getattr(p, "d", 0.0) - altura_mm), p.massa or 1e9))


# =====================================================================================
# 3. Escolha do perfil
# =====================================================================================

_CACHE: Dict[Tuple[str, ...], List[Perfil]] = {}


def candidatos(familias: Sequence[str], altura_min: float = 0.0,
               altura_max: float = 0.0) -> List[Perfil]:
    """Perfis do catálogo das famílias pedidas, do mais leve ao mais pesado."""
    chave = tuple(familias)
    lista = _CACHE.get(chave)
    if lista is None:
        vistos, lista = set(), []
        for f in familias:
            for it in catalogo.itens(f):
                if not it.eh_barra or it.nome in vistos:
                    continue
                p = catalogo.perfil_de(it)
                if p is None or not getattr(p, "A", 0):
                    continue
                vistos.add(it.nome)
                lista.append(p)
        lista.sort(key=lambda p: (p.massa or 1e9, getattr(p, "d", 0.0)))
        _CACHE[chave] = lista
    if altura_min or altura_max:
        return [p for p in lista
                if (not altura_min or getattr(p, "d", 0.0) >= altura_min)
                and (not altura_max or getattr(p, "d", 0.0) <= altura_max)]
    return list(lista)


def _espessura(p: Perfil) -> float:
    """Espessura de parede do perfil, em mm (0 quando não se aplica, como na barra redonda)."""
    for chave in ("t", "tw", "tf", "e"):
        v = p.dados.get(chave)
        if v:
            return float(v)
    return 0.0


def menor_perfil(familias: Sequence[str], aco: str, Nc: float, Nt: float, M: float,
                 Lx: float, Ly: float, elemento: str,
                 altura_min: float = 0.0, altura_max: float = 0.0,
                 esbeltez_max: float = 250.0,
                 espessura_min: float = MIN_ESPESSURA, n: int = 1,
                 forcado: Optional[Perfil] = None) -> Tuple[Optional[Perfil], Optional[Resultado]]:
    """O perfil mais leve que passa. Devolve (perfil, resultado) ou o menos ruim achado.

    `esbeltez_max` recusa antes da norma a barra esbelta demais (NBR 8800 limita
    λ = KL/r a 200 na compressão e 300 na tração): não adianta passar por pouco numa
    peça que chega torta à obra. `n` é o número de peças da barra (2 no perfil duplo);
    `forcado` pula a busca e verifica só aquele perfil — é o que o usuário escolheu.
    """
    if forcado is not None:
        return forcado, verificar.verificar_membro(forcado, aco, Nc, Nt, M, Lx, Ly, n, elemento, [])
    melhor = (None, None)
    comprimido = abs(Nc) > 1e-6
    limite = min(esbeltez_max, 200.0 if comprimido else 300.0)
    for p in candidatos(familias, altura_min, altura_max):
        if espessura_min and 0 < _espessura(p) < espessura_min:
            continue
        r_min = min(getattr(p, "rx", 0.0) or 1e9, getattr(p, "ry", 0.0) or 1e9)
        if r_min and max(Lx, Ly) / r_min > limite:
            continue
        r = verificar.verificar_membro(p, aco, Nc, Nt, M, Lx, Ly, n, elemento, [])
        if r.ok:
            return p, r
        if melhor[1] is None or r.razao < melhor[1].razao:
            melhor = (p, r)
    return melhor


def candidatos_verificados(familias: Sequence[str], aco: str, Nc: float, Nt: float, M: float,
                           Lx: float, Ly: float, elemento: str, altura_ref: float = 0.0,
                           altura_max: float = 0.0, n: int = 1, limite: int = 12,
                           espessura_min: float = MIN_ESPESSURA) -> List[dict]:
    """Os perfis do catálogo em volta do adotado, cada um verificado nos mesmos esforços:
    o que passa primeiro (do mais leve ao mais pesado), depois o que não passa (do que
    chegou mais perto). É a lista que o projetista usa para trocar o perfil sem sair do
    que a norma aceita — e para ver quanto cada escolha custa em kg/m."""
    a_min = 0.5 * altura_ref if altura_ref else 0.0
    a_max = min(2.0 * altura_ref, altura_max) if (altura_ref and altura_max) else (2.0 * altura_ref if altura_ref else altura_max)
    saida = []
    for p in candidatos(familias, a_min, a_max):
        if espessura_min and 0 < _espessura(p) < espessura_min:
            continue
        r = verificar.verificar_membro(p, aco, Nc, Nt, M, Lx, Ly, n, elemento, [])
        saida.append({"perfil": p.nome, "razao": round(r.razao, 3), "ok": bool(r.ok),
                      "massa": round((p.massa or 0.0) * n, 2)})
    saida.sort(key=lambda x: (not x["ok"], x["massa"] if x["ok"] else x["razao"]))
    return saida[:limite]
