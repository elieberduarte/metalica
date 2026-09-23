# -*- coding: utf-8 -*-
"""Modelo 3D do galpão dimensionado: `ProjetoGalpao` → `Documento`.

É a fronteira entre o núcleo de cálculo (kN, cm, metros na entrada do usuário) e o
módulo 3D (milímetro, grau, Z para cima). Toda conversão de unidade acontece aqui.

Eixos: **X** ao longo do comprimento do galpão, **Y** no sentido do vão, **Z** para
cima. O pórtico 1 fica em x = 0 e o pilar da esquerda em y = 0.

Mesmas convenções dos desenhos 2D
---------------------------------
A geometria sai de `saida.desenhos._Geo` e dos `PADRAO_*` daquele módulo, de modo
que o modelo 3D e as pranchas DXF mostram as mesmas posições:

* pórticos a cada `espacamento_porticos`, o último ajustado ao comprimento;
* terças a 200 mm do beiral e 250 mm da cumeeira, com o número de vãos que mantém o
  espaçamento abaixo do alvo (planta de cobertura);
* longarinas nas alturas publicadas pelo cálculo, as mesmas da elevação;
* contraventamento em X: vãos contraventados, painéis ao longo do vão e quantidade
  **lidos do cálculo** (`elemento(...).geometria`: `vaos_contraventados`, `paineis`,
  `quantidade`), porque o dimensionamento pode aumentar os painéis para o tirante
  caber. Sem projeto dimensionado (`exemplo()`), vale a regra dos desenhos: vãos
  extremos e central, `max(2, round(vão/espaçamento))` painéis, um X por parede;
* correntes no meio de cada vão, ligando as terças, com tirante em V na cumeeira;
* chapa de topo com as quatro fileiras de parafusos de `_linhas_parafusos` e placa
  de base com os chumbadores no gabarito da prancha de base.

Diferenças deliberadas em relação ao 2D (o 3D não tem a liberdade do desenho):

* **Eixo da viga.** No 2D a faixa da viga é desenhada para cima da linha
  joelho–cumeeira; no 3D a linha é o **eixo** (centroide) da viga, que é como o
  pórtico foi analisado (nós N2 e N3 da elevação). A caixa do pórtico fica então
  exatamente vão × comprimento × altura de cumeeira.
* **Mísula.** Representada por duas `Chapa`: a alma triangular (espessura da alma
  da viga) e a mesa inferior inclinada (largura e espessura da mesa da viga). É o
  que se fabrica ao cortar o perfil na diagonal, e dá o peso certo — uma barra
  prismática com a seção da raiz dobraria o peso da alma.
  A altura segue a convenção dos desenhos (`_Geo.h_misula`: a altura informada ou a
  da viga, medida abaixo da mesa inferior); quando a ligação foi dimensionada com
  outra altura total, ela vai em `atributos["altura_ligacao_mm"]`.
* **Cumeeira.** As duas chapas de topo (uma por água) são modeladas encostadas uma
  na outra no plano y = vão/2.
* **Longarinas.** Usam o perfil verificado pelo cálculo (elemento "Longarina de
  fechamento"); sem ele, o da terça, e sem projeto o `PADRAO_LONGARINA` dos
  desenhos. Ficam na face externa do pilar.
* **Escoras dos nós do X de cobertura** não entram: não estão na lista de material
  e o dimensionamento não as verifica.

* **Correntes** em ø 16 mm, como na lista de material e na planta de cobertura.

Cada entidade leva em `atributos`: `marca`, `elemento` (nome do elemento
dimensionado de origem) e a posição (pórtico, água, linha, vão). As peças de aço
levam `peso_kg`; o pedestal de concreto e o fechamento levam `volume_m3` (o pedestal
também `peso_concreto_kg`) e **nunca** `peso_kg`, que é o que a lista de material e o
IFC somam como aço.
"""
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from nucleo.base import RHO                                     # noqa: E402
from nucleo.modelo_galpao import DadosGalpao, ProjetoGalpao     # noqa: E402
from nucleo.perfis import Perfil                                # noqa: E402
from nucleo3d import geometria as geo                           # noqa: E402
from nucleo3d.modelo import (Barra, Chapa, Documento, Ponto, Solido,   # noqa: E402
                             normalizar, somar, escalar as _mult)
from saida import desenhos as dsn                               # noqa: E402

#: Massa específica do concreto armado, kg/m³ (NBR 6120, Tabela 1).
RHO_CONCRETO = 2500.0

#: Espessura dos sólidos de telha e fechamento, mm (só visual; peso não entra).
ESPESSURA_TELHA = 30.0

#: Altura do pedestal abaixo da placa de base, mm (a mesma da elevação do pórtico).
ALTURA_PEDESTAL = 600.0

#: Diâmetro da corrente de terça, mm. É o da lista de material do dimensionamento
#: (marca TC, "Barra ø 16 mm"), igual ao `PADRAO_DIAM_CORRENTE` da planta de cobertura,
#: de modo que planta, lista de material e 3D mostram a mesma barra.
DIAM_CORRENTE = 16.0

def _vaos_padrao(n_vaos: int) -> List[int]:
    """Vãos contraventados (índice a partir de 0): os dois extremos e o central.

    Usa a regra do próprio cálculo (`nucleo.galpao._vaos_contraventados`) quando ela
    existe, e a mesma regra das pranchas como reserva.
    """
    try:
        from nucleo.galpao import _vaos_contraventados
        vaos = sorted({int(v) for v in _vaos_contraventados(n_vaos)})
        if vaos and all(0 <= v < max(n_vaos, 1) for v in vaos):
            return vaos
    except Exception:
        pass
    return sorted({0, n_vaos - 1, max(0, (n_vaos - 1) // 2)}) if n_vaos >= 2 else [0]


#: Marcas de fabricação, as mesmas da lista de material.
MARCAS = {"pilar": "P1", "viga": "V1", "misula_alma": "M1", "misula_mesa": "M2",
          "banzo superior": "BS", "banzo inferior": "BI",
          "diagonal": "D", "montante": "M", "travamento": "TV",
          "terca": "T1", "corrente": "TC", "longarina": "L1",
          "contrav_cobertura": "CC", "contrav_vertical": "CV",
          "chapa_joelho": "CH1", "chapa_cumeeira": "CH2", "placa_base": "CH3",
          "pedestal": "PD", "telha": "TL", "fechamento": "FC"}


# =====================================================================================
# Pontos de entrada
# =====================================================================================

def modelo_vazio(nome: str = "Modelo") -> Documento:
    """Documento sem entidades, com as camadas e materiais padrão."""
    return Documento(nome=nome)


def exemplo(com_fechamento: bool = True) -> Documento:
    """Galpão simples (vão de 15 m, 30 m de comprimento) sem rodar o dimensionamento.

    Usa os perfis padrão por faixa de vão dos desenhos (`PADRAO_PERFIS`) e as
    ligações e bases padrão. Serve para testes e para a demonstração do editor.
    """
    dados = DadosGalpao(nome="Galpão de exemplo", vao=15.0, comprimento=30.0,
                        pe_direito=6.0, espacamento_porticos=6.0, inclinacao=10.0,
                        espacamento_tercas=1.5, linhas_correntes=1)
    return modelo_do_galpao(dados, com_fechamento=com_fechamento)


def modelo_do_galpao(projeto, com_fechamento: bool = True,
                     com_pedestais: bool = True) -> Documento:
    """Constrói o modelo 3D completo do galpão, em milímetros, com Z para cima.

    Aceita um `ProjetoGalpao` dimensionado (caso normal: perfis, ligações e base do
    cálculo), um `DadosGalpao` ou um dicionário de geometria (perfis e detalhes
    padrão dos desenhos).
    """
    return _Construtor(projeto, com_fechamento, com_pedestais).montar()


def pesos(doc: Documento) -> Dict[str, float]:
    """Peso de aço do modelo por marca e total, em kg, somando `atributos["peso_kg"]`.

    `peso_kg` só existe em peça de aço — é o que a lista de material e o IFC somam.
    Pedestal de concreto e fechamento guardam `volume_m3` (e o pedestal também
    `peso_concreto_kg`), que ficam fora desta soma.
    """
    saida: Dict[str, float] = {}
    total = 0.0
    for e in doc.entidades.values():
        p = e.atributos.get("peso_kg")
        if not isinstance(p, (int, float)):
            continue
        marca = e.atributos.get("marca", e.nome or e.tipo)
        saida[marca] = saida.get(marca, 0.0) + p
        total += p
    saida = {k: round(v, 1) for k, v in saida.items()}
    saida["total_aco_kg"] = round(total, 1)
    return saida


def caixa_do_portico(doc: Documento) -> Tuple[Ponto, Ponto]:
    """Caixa envolvente dos eixos de pilares e vigas, em mm.

    É a caixa que tem de dar vão × comprimento × altura de cumeeira. A caixa do
    documento inteiro é maior, e deve ser: terças e telhas ficam acima do eixo da
    viga, longarinas fora do pilar e o pedestal abaixo do piso.
    """
    pts = [pt for b in doc.barras if b.papel in ("pilar", "viga")
           for pt in (b.inicio, b.fim)]
    if not pts:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return geo.caixa_envolvente(pts)


# =====================================================================================
# Construtor
# =====================================================================================

class _Construtor:
    """Monta o documento peça por peça. Um método por família de peças."""

    def __init__(self, fonte, com_fechamento: bool, com_pedestais: bool):
        self.fonte = fonte
        self.projeto = fonte if isinstance(fonte, ProjetoGalpao) else None
        self.g = dsn._Geo(fonte)
        self.dg: DadosGalpao = self.g.dg
        self.com_fechamento = com_fechamento
        self.com_pedestais = com_pedestais
        self.doc = Documento(nome=self.dg.nome or "Galpão")

        g = self.g
        self.V, self.C, self.H = g.vao, g.comprimento, g.H
        # na tesoura o topo do pilar (H) é o banzo inferior e o telhado começa no
        # beiral, uma altura de tesoura acima; no pórtico de alma cheia os dois coincidem
        self.hb = g.h_beiral
        self.topo_pilar = g.h_beiral if (self.dg.eh_trelicado
                                         and self.dg.ligacao_tesoura == "rígida") else g.H
        self.hc, self.i, self.theta = g.h_cumeeira, g.i, g.theta
        self.c, self.s = math.cos(g.theta), math.sin(g.theta)
        self.xs = [k * g.esp_port for k in range(g.n_porticos)]
        if self.xs and abs(self.xs[-1] - self.C) > 1.0:
            self.xs[-1] = self.C
        self.vaos_x = _vaos_padrao(len(self.xs) - 1)
        self.vaos_cobertura = self.vaos_vertical = self.vaos_x
        self.paineis_cobertura = 0
        self.pilar, self.viga = g.pilar, g.viga
        self.terca = g.terca
        # longarina verificada pelo cálculo; sem ela, o perfil da terça, como a lista
        # de material fazia antes de a longarina ser dimensionada
        if self.projeto and self.projeto.elemento("Longarina"):
            self.longarina = g.longarina
        elif self.projeto and self.projeto.elemento("Terça"):
            self.longarina = g.terca
        else:
            self.longarina = g.longarina

    # ------------------------------------------------------------------ utilidades
    def _elemento(self, nome: str):
        return self.projeto.elemento(nome) if self.projeto else None

    def _nome_elemento(self, nome: str, padrao: str) -> str:
        el = self._elemento(nome)
        return el.nome if el else padrao

    def _barra(self, chave: str, ini: Ponto, fim: Ponto, perfil: Perfil, papel: str,
               camada: str, material: str, aco: str, elemento: str,
               rotacao: float = 0.0, marca: Optional[str] = None, **pos) -> Barra:
        marca = marca or MARCAS[chave]
        b = Barra(nome=marca, inicio=tuple(ini), fim=tuple(fim),
                  perfil=perfil.nome, rotacao=rotacao, papel=papel, camada=camada,
                  material=material, aco=aco)
        b.atributos = {"marca": marca, "elemento": elemento,
                       "peso_kg": round(geo.peso_barra(b), 2), **pos}
        self.doc.add(b)
        return b

    def _chapa(self, chave: str, origem: Ponto, ex: Ponto, ey: Ponto,
               contorno: List[Tuple[float, float]], espessura: float, elemento: str,
               furos: Optional[List[dict]] = None, camada: str = "Chapas",
               centrada: bool = True, **pos) -> Chapa:
        ch = Chapa(nome=MARCAS[chave], origem=tuple(origem), eixo_x=normalizar(ex),
                   eixo_y=normalizar(ey), contorno=[tuple(p) for p in contorno],
                   espessura=float(espessura), centrada=centrada,
                   furos=list(furos or []), camada=camada, material="Aço",
                   aco=self.dg.aco_chapas)
        ch.atributos = {"marca": MARCAS[chave], "elemento": elemento,
                        "peso_kg": round(geo.peso_chapa(ch), 2), **pos}
        self.doc.add(ch)
        return ch

    def _z_agua(self, y: float) -> float:
        """Cota do eixo da água na posição y do vão (viga ou banzo superior)."""
        return self.hb + self.i * min(y, self.V - y)

    def _normal_agua(self, y: float) -> Ponto:
        """Normal da água (para cima, perpendicular à viga) na posição y."""
        return (0.0, -self.s, self.c) if y <= self.V / 2 else (0.0, self.s, self.c)

    # ------------------------------------------------------------------ montagem
    def montar(self) -> Documento:
        self._pilares()
        if self.dg.eh_trelicado:
            self._tesoura()
        else:
            self._vigas()
            self._misulas()
        self._tercas_e_correntes()
        self._longarinas()
        self._contraventamento_cobertura()
        self._contraventamento_vertical()
        self._travamento_banzo_inferior()
        if not self.dg.eh_trelicado:
            # as chapas de topo do joelho e da cumeeira são do pórtico de alma cheia;
            # na tesoura quem faz esse papel é a chapa de nó, ainda não modelada em 3D
            self._chapas_de_topo()
        self._bases()
        if self.com_fechamento:
            self._fechamento()
        self._metadados()
        return self.doc

    # ------------------------------------------------------------------ pórtico
    def _pilares(self):
        el = self._nome_elemento("Pilar", "Pilar")
        for k, x in enumerate(self.xs):
            for lado, y in (("esquerdo", 0.0), ("direito", self.V)):
                # rotação 90°: alma no plano do pórtico (eixo forte no Y global)
                self._barra("pilar", (x, y, 0.0), (x, y, self.topo_pilar), self.pilar, "pilar",
                            "Estrutura", "Aço", self.dg.aco_perfis, el, rotacao=90.0,
                            portico=k + 1, lado=lado)

    def _vigas(self):
        el = self._nome_elemento("Viga", "Viga do pórtico")
        for k, x in enumerate(self.xs):
            for agua, y0 in ((1, 0.0), (2, self.V)):
                self._barra("viga", (x, y0, self.H), (x, self.V / 2, self.hc),
                            self.viga, "viga", "Estrutura", "Aço", self.dg.aco_perfis,
                            el, portico=k + 1, agua=agua)

    def _tesoura(self):
        """A tesoura de cada pórtico, barra por barra, com o perfil de cada família.

        A malha é a mesma que o cálculo usou (`esforcos["geometria_tesoura"]`), e as
        marcas são as da lista de material: BS e BI nos banzos, D1…Dn e M1…Mn nas
        barras internas, agrupadas por comprimento.
        """
        from nucleo import tesouras as _tes
        from nucleo.galpao import NOME_DA_BARRA
        t = dsn._tesoura_do_projeto(self.fonte, self.dg)
        perfis, nomes = {}, {}
        for papel in _tes.PAPEIS:
            el = self._elemento(NOME_DA_BARRA[papel])
            perfis[papel] = dsn._perfil(el.perfil) if el and el.perfil else self.viga
            nomes[papel] = el.nome if el else NOME_DA_BARRA[papel]
        pular = {"mont_esq", "mont_dir"} if self.dg.ligacao_tesoura == "rígida" else set()

        # marca por comprimento, na mesma ordem da lista de material
        marca_de = {}
        for papel in ("diagonal", "montante"):
            comps = sorted({round(t.comprimento(b) / 100.0, 2)
                            for b in t.do_papel(papel) if b.rotulo not in pular},
                           reverse=True)
            for i, c in enumerate(comps, start=1):
                marca_de[(papel, c)] = "%s%d" % (MARCAS[papel], i)

        for k, x in enumerate(self.xs):
            for b in t.barras:
                if b.rotulo in pular:
                    continue
                ni, nj = t.no(b.i), t.no(b.j)
                ini = (x, ni.x * 10.0, self.H + ni.y * 10.0)
                fim = (x, nj.x * 10.0, self.H + nj.y * 10.0)
                comp = round(t.comprimento(b) / 100.0, 2)
                marca = marca_de.get((b.papel, comp), MARCAS[b.papel])
                papel3d = "banzo" if b.papel.startswith("banzo") else b.papel
                self._barra(b.papel, ini, fim, perfis[b.papel], papel3d, "Estrutura",
                            "Aço", self.dg.aco_perfis, nomes[b.papel], marca=marca,
                            portico=k + 1, barra=b.rotulo, familia=b.papel)

    def _travamento_banzo_inferior(self):
        """Tirantes que travam o banzo inferior de uma tesoura à vizinha."""
        el = self._elemento("Travamento do banzo inferior")
        if el is None or not self.dg.eh_trelicado:
            return
        t = dsn._tesoura_do_projeto(self.fonte, self.dg)
        linhas = int(el.geometria.get("linhas_por_tesoura") or 0)
        if linhas <= 0:
            return
        perfil = self._perfil_contraventamento("Travamento do banzo inferior")
        nos = [n for n in t.nos if n.banzo == "inferior"]
        nos.sort(key=lambda n: n.x)
        if len(nos) < linhas + 2:
            return
        passo = (len(nos) - 1) / float(linhas + 1)
        alvos = [nos[int(round(passo * (j + 1)))] for j in range(linhas)]
        for j, n in enumerate(alvos):
            y, z = n.x * 10.0, self.H + n.y * 10.0
            for iv in range(len(self.xs) - 1):
                self._barra("travamento", (self.xs[iv], y, z), (self.xs[iv + 1], y, z),
                            perfil, "contraventamento", "Contraventamento", "Aço",
                            self.dg.aco_chapas, el.nome, linha=j + 1, vao=iv + 1)

    def _misulas(self):
        g = self.g
        if not (g.com_misula and g.L_misula > 0):
            return
        el = self._nome_elemento("Viga", "Viga do pórtico")
        Lm, hm = g.L_misula, g.h_misula
        dv, tw, tf, bf = self.viga.d, self.viga.tw, self.viga.tf, self.viga.bf
        lig = self.projeto.ligacoes.get("viga-pilar") if self.projeto else None
        h_lig = (lig.dados.get("altura_misula_mm") if lig is not None
                 and isinstance(getattr(lig, "dados", None), dict) else None)
        extra = {"altura_ligacao_mm": h_lig} if h_lig else {}
        for k, x in enumerate(self.xs):
            for agua, y0 in ((1, 0.0), (2, self.V)):
                sy = 1.0 if agua == 1 else -1.0
                u = (0.0, sy * self.c, self.s)             # ao longo da viga
                baixo = (0.0, sy * self.s, -self.c)        # perpendicular, para baixo
                A = (x, y0, self.H)
                B0 = somar(A, _mult(baixo, dv / 2))        # face inferior da viga
                cima = _mult(baixo, -1.0)
                # alma: triângulo com catetos Lm (ao longo da viga) e hm (na raiz)
                self._chapa("misula_alma", B0, u, cima,
                            [(0.0, 0.0), (Lm, 0.0), (0.0, -hm)], tw, el,
                            camada="Estrutura", portico=k + 1, agua=agua, **extra)
                # mesa inferior inclinada, na hipotenusa do triângulo
                raiz = somar(B0, _mult(baixo, hm))
                ponta = somar(B0, _mult(u, Lm))
                eixo = (ponta[0] - raiz[0], ponta[1] - raiz[1], ponta[2] - raiz[2])
                Lh = math.sqrt(sum(c * c for c in eixo))
                meio = _mult(somar(raiz, ponta), 0.5)
                self._chapa("misula_mesa", meio, eixo, (1.0, 0.0, 0.0),
                            [(-Lh / 2, -bf / 2), (Lh / 2, -bf / 2), (Lh / 2, bf / 2),
                             (-Lh / 2, bf / 2)], tf, el, camada="Estrutura",
                            portico=k + 1, agua=agua)

    # ------------------------------------------------------------------ cobertura
    def _ys_tercas(self) -> Tuple[List[float], float]:
        """Posições (em planta) das terças de uma água, as mesmas da planta de cobertura.

        O alvo é o espaçamento real calculado pelo dimensionamento quando existe
        (`cargas["espacamento_tercas_real"]`); senão, o pedido pelo usuário.
        """
        rec_beiral, rec_cumeeira = 200.0, 250.0
        alvo = self.g.esp_terca
        if self.projeto and self.projeto.cargas.get("espacamento_tercas_real"):
            alvo = float(self.projeto.cargas["espacamento_tercas_real"]) * 1000.0
        util = self.V / 2 - rec_beiral - rec_cumeeira
        n = max(1, int(math.ceil(util / alvo - 1e-6)))
        passo = util / n
        return [rec_beiral + k * passo for k in range(n + 1)], passo

    def _centro_terca(self, x: float, y: float) -> Ponto:
        """Centroide da terça apoiada na mesa superior da viga, na posição y."""
        off = self.viga.d / 2 + self.terca.d / 2
        n = self._normal_agua(y)
        return (x, y + n[1] * off, self._z_agua(y) + n[2] * off)

    def _tercas_e_correntes(self):
        meia, passo = self._ys_tercas()
        el = self._nome_elemento("Terça", "Terça")
        ang = math.degrees(self.theta)
        linhas = []
        for agua in (1, 2):
            ys = meia if agua == 1 else [self.V - y for y in meia]
            for j, y in enumerate(ys):
                linhas.append((agua, j + 1, y))
                for iv in range(len(self.xs) - 1):
                    a = self._centro_terca(self.xs[iv], y)
                    b = self._centro_terca(self.xs[iv + 1], y)
                    # eixo forte perpendicular ao plano da água
                    self._barra("terca", a, b, self.terca, "terça", "Terças",
                                "Aço galvanizado", self.dg.aco_tercas, el,
                                rotacao=ang if agua == 1 else -ang,
                                agua=agua, linha=j + 1, vao=iv + 1)
        self.linhas_tercas = linhas
        self.passo_tercas = passo

        # correntes: no meio de cada vão (ou nos terços, com 2 linhas), ligando as
        # terças de uma água e fechando em V na cumeeira
        terca = self._elemento("Terça")
        n_corr = int(terca.geometria.get("n_correntes", 0)) if terca else \
            max(0, int(self.dg.linhas_correntes))
        if n_corr <= 0:
            return
        barra = geo.registrar_perfil(geo.barra_redonda(DIAM_CORRENTE, "Barra ø 16 mm"))
        for iv in range(len(self.xs) - 1):
            x1, x2 = self.xs[iv], self.xs[iv + 1]
            for k in range(1, n_corr + 1):
                xc = x1 + (x2 - x1) * k / (n_corr + 1.0)
                for agua in (1, 2):
                    ys = meia if agua == 1 else [self.V - y for y in meia]
                    pts = [self._centro_terca(xc, y) for y in ys]
                    for j in range(len(pts) - 1):
                        self._barra("corrente", pts[j], pts[j + 1], barra, "barra",
                                    "Terças", "Aço", self.dg.aco_chapas,
                                    "Corrente de terça", agua=agua, vao=iv + 1,
                                    linha_corrente=k)
                    cume = self._centro_terca(xc + (x2 - x1) * 0.06, self.V / 2)
                    self._barra("corrente", pts[-1], cume, barra, "barra", "Terças",
                                "Aço", self.dg.aco_chapas, "Tirante de cumeeira",
                                agua=agua, vao=iv + 1, linha_corrente=k)

    def _longarinas(self):
        """Fiadas nas mesmas alturas da elevação longitudinal.

        As cotas vêm do cálculo (`cotas_fiadas_m`) por meio da mesma função que
        desenha a elevação; sem cálculo, fiadas a cada 1 900 mm a partir do piso.
        """
        zs = list(dsn._fiadas_longarina(self.g)[0])
        el = self._nome_elemento("Longarina", "Longarina de fechamento")
        off = self.pilar.d / 2 + self.longarina.d / 2      # face externa do pilar
        for lado, yw, ang in (("esquerdo", -off, 90.0), ("direito", self.V + off, -90.0)):
            for j, z in enumerate(zs):
                for iv in range(len(self.xs) - 1):
                    self._barra("longarina", (self.xs[iv], yw, z),
                                (self.xs[iv + 1], yw, z), self.longarina, "longarina",
                                "Terças", "Aço galvanizado", self.dg.aco_tercas, el,
                                rotacao=ang, lado=lado, fiada=j + 1, vao=iv + 1)

    # ------------------------------------------------------------------ contraventamento
    def _perfil_contraventamento(self, nome: str) -> Perfil:
        el = self._elemento(nome)
        if el and el.perfil:
            try:
                return geo.registrar_perfil(geo.resolver_perfil(el.perfil))
            except Exception:
                pass
        return geo.registrar_perfil(geo.barra_redonda(dsn.PADRAO_DIAM_CONTRAVENTAMENTO))

    def _geometria_contrav(self, nome: str) -> dict:
        """Geometria publicada pelo cálculo do contraventamento, se houver.

        Só vale quando traz `vaos_contraventados`: é a marca do contrato em que
        `paineis` quer dizer painéis **ao longo do vão**. Uma versão anterior do
        cálculo usava `paineis` com outro sentido, e ler aquele número mudaria o
        desenho sem aviso.
        """
        el = self._elemento(nome)
        g_ = el.geometria if el is not None and isinstance(el.geometria, dict) else {}
        return g_ if g_.get("vaos_contraventados") else {}

    def _vaos_de(self, g_: dict) -> List[int]:
        """Vãos do cálculo (numerados a partir de 1) em índice a partir de 0."""
        n_vaos = len(self.xs) - 1
        vaos = set()
        for v in g_.get("vaos_contraventados") or []:
            try:
                iv = int(v) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= iv < n_vaos:
                vaos.add(iv)
        return sorted(vaos) or self.vaos_x

    def _contraventamento_cobertura(self):
        perf = self._perfil_contraventamento("Contraventamento de cobertura")
        el = self._nome_elemento("Contraventamento de cobertura",
                                 "Contraventamento de cobertura")
        geo_c = self._geometria_contrav("Contraventamento de cobertura")
        try:
            n_pain = int(geo_c.get("paineis") or 0)
        except (TypeError, ValueError):
            n_pain = 0
        if n_pain < 1:
            n_pain = max(2, int(round(self.V / max(self.g.esp_port, 1.0))))
        self.paineis_cobertura = n_pain
        self.vaos_cobertura = self._vaos_de(geo_c)
        ys = [self.V * k / n_pain for k in range(n_pain + 1)]
        for iv in self.vaos_cobertura:
            x1, x2 = self.xs[iv], self.xs[iv + 1]
            for k in range(n_pain):
                ya, yb = ys[k], ys[k + 1]
                pa1, pb2 = (x1, ya, self._z_agua(ya)), (x2, yb, self._z_agua(yb))
                pb1, pa2 = (x1, yb, self._z_agua(yb)), (x2, ya, self._z_agua(ya))
                for diag, (p, q) in enumerate(((pa1, pb2), (pb1, pa2)), start=1):
                    self._barra("contrav_cobertura", p, q, perf, "contraventamento",
                                "Contraventamento", "Aço", self.dg.aco_chapas, el,
                                vao=iv + 1, painel=k + 1, diagonal=diag)

    def _contraventamento_vertical(self):
        perf = self._perfil_contraventamento("Contraventamento vertical")
        el = self._nome_elemento("Contraventamento vertical", "Contraventamento vertical")
        bfp = self.pilar.bf
        self.vaos_vertical = self._vaos_de(self._geometria_contrav("Contraventamento vertical"))
        for iv in self.vaos_vertical:
            x1, x2 = self.xs[iv] + bfp / 2, self.xs[iv + 1] - bfp / 2
            for lado, y in (("esquerdo", 0.0), ("direito", self.V)):
                for diag, (za, zb) in enumerate(((0.0, self.H), (self.H, 0.0)), start=1):
                    self._barra("contrav_vertical", (x1, y, za), (x2, y, zb), perf,
                                "contraventamento", "Contraventamento", "Aço",
                                self.dg.aco_chapas, el, vao=iv + 1, lado=lado,
                                diagonal=diag)

    # ------------------------------------------------------------------ ligações
    def _chapas_de_topo(self):
        """Chapas de topo do joelho e da cumeeira, com os furos das 4 fileiras."""
        viga = self.viga
        c = self.c
        # --- joelho (DET. 04): mesma receita de `desenhos.ligacao_viga_pilar`
        v = dsn._dados_ligacao(self.fonte, "viga-pilar", dsn.PADRAO_LIGACAO)
        tch = float(v["chapa_esp"])
        dfuro = float(v["d_parafuso"]) + float(v["folga_furo"])
        gab, bm, bc = float(v["gabarito"]), float(v["borda_mesa"]), float(v["borda_chapa"])
        bch = float(v.get("chapa_larg", 0.0)) or max(viga.bf + 30.0, gab + 100.0)
        hm = self.g.h_misula if self.g.com_misula else 0.0
        D_tot = viga.d + hm
        y_top, y_bot = 0.0, -D_tot
        ys = dsn._linhas_parafusos(y_top, viga.tf, y_bot, viga.tf, bm)
        cont = [(-bch / 2, y_bot - bm - bc), (bch / 2, y_bot - bm - bc),
                (bch / 2, y_top + bm + bc), (-bch / 2, y_top + bm + bc)]
        furos = [{"x": sx * gab / 2, "y": yy, "diametro": dfuro}
                 for yy in ys for sx in (-1, 1)]
        z_top = self.H + (viga.d / 2) / c           # topo da viga no plano da chapa
        el = "Ligação viga-pilar"
        for k, x in enumerate(self.xs):
            for lado, y in (("esquerdo", self.pilar.d / 2 + tch / 2),
                            ("direito", self.V - self.pilar.d / 2 - tch / 2)):
                self._chapa("chapa_joelho", (x, y, z_top), (1.0, 0.0, 0.0),
                            (0.0, 0.0, 1.0), cont, tch, el, furos=furos,
                            portico=k + 1, lado=lado)

        # --- cumeeira (DET. 05): seção da viga, cortada na vertical
        vc = dsn._dados_ligacao(self.fonte, "cumeeira", dsn.PADRAO_LIGACAO)
        tcc = float(vc["chapa_esp"])
        dfc = float(vc["d_parafuso"]) + float(vc["folga_furo"])
        gabc = float(vc["gabarito"])
        bcc = float(vc.get("chapa_larg", 0.0)) or max(viga.bf + 30.0, gabc + 100.0)
        dvv = viga.d / c
        ysc = dsn._linhas_parafusos(dvv / 2, viga.tf, -dvv / 2, viga.tf, bm)
        contc = [(-bcc / 2, -dvv / 2 - bm - bc), (bcc / 2, -dvv / 2 - bm - bc),
                 (bcc / 2, dvv / 2 + bm + bc), (-bcc / 2, dvv / 2 + bm + bc)]
        furosc = [{"x": sx * gabc / 2, "y": yy, "diametro": dfc}
                  for yy in ysc for sx in (-1, 1)]
        for k, x in enumerate(self.xs):
            for agua, dy in ((1, -tcc / 2), (2, tcc / 2)):
                self._chapa("chapa_cumeeira", (x, self.V / 2 + dy, self.hc),
                            (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), contc, tcc,
                            "Ligação de cumeeira", furos=furosc, portico=k + 1,
                            agua=agua)

    def _bases(self):
        """Placa de base com os furos dos chumbadores e o pedestal de concreto.

        Mesma leitura de `desenhos.base_pilar`: B é a dimensão perpendicular ao plano
        do pórtico (X global) e L a do plano do pórtico (Y global); os chumbadores
        ficam a ±gB/2 em X e, com 4 ou mais, também a ±gL/2 em Y.
        """
        v = dict(dsn.PADRAO_BASE)
        rotulada = bool(self.dg.base_rotulada)
        if self.projeto is not None:
            v.update(dsn._base_do_resultado(self.projeto.base))
            if "n_chumbadores" in v and self.projeto.base is not None:
                rotulada = int(v["n_chumbadores"]) <= 2
        if not rotulada and int(v.get("n_chumbadores", 2)) < 4:
            v["n_chumbadores"] = 4
        pil = self.pilar
        B = max(float(v["placa_B"]), pil.bf + 80.0)
        L = max(float(v["placa_L"]), pil.d + 40.0)
        t = float(v["placa_t"])
        dfuro = float(v["d_chumbador"]) + float(v["folga_furo"])
        n_ch = int(v["n_chumbadores"])
        gB = float(v["gabarito_B"]) or (B - 120.0)
        gL = float(v["gabarito_L"]) or (pil.d + 90.0 if n_ch >= 4 else 0.0)
        if n_ch >= 4:
            L = max(L, gL + 120.0)
        gB = min(gB, B - 100.0)
        if n_ch >= 4:
            furos = [{"x": sx * gB / 2, "y": sy * gL / 2, "diametro": dfuro}
                     for sx in (-1, 1) for sy in (-1, 1)]
        else:
            furos = [{"x": sx * gB / 2, "y": 0.0, "diametro": dfuro} for sx in (-1, 1)]
        cont = [(-B / 2, -L / 2), (B / 2, -L / 2), (B / 2, L / 2), (-B / 2, L / 2)]
        folga = float(v["pedestal_folga"])
        for k, x in enumerate(self.xs):
            for lado, y in (("esquerdo", 0.0), ("direito", self.V)):
                # placa com a face inferior no nível 0, crescendo para cima
                self._chapa("placa_base", (x, y, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                            cont, t, "Base do pilar", furos=furos, centrada=False,
                            portico=k + 1, lado=lado, n_chumbadores=n_ch)
                if self.com_pedestais:
                    bx, by = B / 2 + folga, L / 2 + folga
                    s = geo.prisma([(x - bx, y - by, -ALTURA_PEDESTAL),
                                    (x + bx, y - by, -ALTURA_PEDESTAL),
                                    (x + bx, y + by, -ALTURA_PEDESTAL),
                                    (x - bx, y + by, -ALTURA_PEDESTAL)],
                                   (0.0, 0.0, ALTURA_PEDESTAL),
                                   nome=MARCAS["pedestal"], camada="Referência",
                                   material="Concreto")
                    s.atributos = {"marca": MARCAS["pedestal"],
                                   "elemento": "Pedestal de concreto",
                                   "volume_m3": round(s.volume / 1e9, 4),
                                   "peso_concreto_kg": round(
                                       geo.peso_solido(s, RHO_CONCRETO), 1),
                                   "tipo_ifc": "IfcFooting", "portico": k + 1,
                                   "lado": lado}
                    self.doc.add(s)

    # ------------------------------------------------------------------ fechamento
    def _fechamento(self):
        """Telhas das duas águas e fechamento das paredes, como sólidos finos."""
        e = ESPESSURA_TELHA
        C, V, H, hc = self.C, self.V, self.H, self.hc
        off = self.viga.d / 2 + self.terca.d                # topo da terça
        for agua, (y0, y1) in ((1, (0.0, V / 2)), (2, (V, V / 2))):
            n = self._normal_agua(y0 if agua == 1 else y0 - 1.0)
            p0 = (0.0, y0 + n[1] * off, self._z_agua(y0) + n[2] * off)
            p1 = (0.0, y1 + n[1] * off, self._z_agua(y1) + n[2] * off)
            cantos = [p0, (C, p0[1], p0[2]), (C, p1[1], p1[2]), p1]
            s = geo.prisma(cantos, _mult(n, e), nome=MARCAS["telha"],
                           camada="Fechamento", material="Telha")
            s.atributos = {"marca": MARCAS["telha"], "elemento": "Telha de cobertura",
                           "volume_m3": round(s.volume / 1e9, 4),
                           "descricao": self.dg.telha, "agua": agua,
                           "tipo_ifc": "IfcRoof"}
            self.doc.add(s)
        # paredes laterais, na face externa das longarinas
        yf = self.pilar.d / 2 + self.longarina.d
        h_fech = (self.dg.altura_fechamento * 1000.0) or self.hb
        for lado, y, sy in (("esquerdo", -yf, -1.0), ("direito", V + yf, 1.0)):
            cantos = [(0.0, y, 0.0), (C, y, 0.0), (C, y, h_fech), (0.0, y, h_fech)]
            s = geo.prisma(cantos, (0.0, sy * e, 0.0), nome=MARCAS["fechamento"],
                           camada="Fechamento", material="Telha")
            s.atributos = {"marca": MARCAS["fechamento"], "elemento": "Fechamento lateral",
                           "volume_m3": round(s.volume / 1e9, 4),
                           "descricao": self.dg.fechamento_lateral, "lado": lado,
                           "tipo_ifc": "IfcWall"}
            self.doc.add(s)
        # oitões (frontões), por fora do primeiro e do último pórtico
        bf = self.pilar.bf / 2
        for lado, x, sx in (("frente", -bf, -1.0), ("fundo", C + bf, 1.0)):
            hb = self.hb
            cantos = [(x, 0.0, 0.0), (x, V, 0.0), (x, V, hb), (x, V / 2, hc), (x, 0.0, hb)]
            s = geo.prisma(cantos, (sx * e, 0.0, 0.0), nome=MARCAS["fechamento"],
                           camada="Fechamento", material="Telha")
            s.atributos = {"marca": MARCAS["fechamento"], "elemento": "Fechamento de oitão",
                           "volume_m3": round(s.volume / 1e9, 4),
                           "lado": lado, "tipo_ifc": "IfcWall"}
            self.doc.add(s)

    # ------------------------------------------------------------------ metadados
    def _metadados(self):
        dg = self.dg
        self.doc.projeto = {k: v for k, v in dg.dict().items()
                            if isinstance(v, (int, float, str, bool))}
        p = pesos(self.doc)
        self.doc.metadados = {
            "origem": "nucleo3d.de_projeto",
            "unidade": "mm",
            "eixos": "X comprimento, Y vão, Z para cima",
            "porticos_x_mm": [round(x, 1) for x in self.xs],
            "vaos_contraventados": [iv + 1 for iv in self.vaos_cobertura],
            "vaos_contraventados_vertical": [iv + 1 for iv in self.vaos_vertical],
            "paineis_cobertura": self.paineis_cobertura,
            "linhas_tercas_por_agua": len(self.linhas_tercas) // 2,
            "passo_tercas_mm": round(self.passo_tercas, 1),
            "perfis": {"pilar": self.pilar.nome, "viga": self.viga.nome,
                       "terca": self.terca.nome, "longarina": self.longarina.nome},
            "pesos_kg": p,
            "dimensionado": self.projeto is not None,
        }
        if self.projeto is not None and self.projeto.resumo_pesos:
            self.doc.metadados["resumo_pesos_projeto"] = dict(self.projeto.resumo_pesos)
