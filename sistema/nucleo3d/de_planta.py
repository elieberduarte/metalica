# -*- coding: utf-8 -*-
"""Montagem pela planta: o projeto recebido em DXF, sem 3D, vira modelo 3D.

Um projeto de cobertura bem desenhado traz, no mesmo arquivo:

* a **planta estrutural** num nível (ex.: "PLANTA NO NÍVEL 6,00m"), com cada treliça
  desenhada pela largura da mesa (duas linhas paralelas, ou dois arcos na peça
  calandrada) e o nome escrito junto: "TESOURA 1", "PAINEL 8", "TRANSIÇÃO 4"…;
* a **elevação** de cada treliça, com o título "TESOURA 1 - 7X" embaixo, o banzo em linha
  dupla, montantes e diagonais em linha simples, e a nota dos perfis ("BANZO U100X40X2,25",
  "DIAGONAIS E MONTANTES 2L 1"X1/8"");
* a **locação** dos pilares ("PM3(200X70X20X2,65)" sobre a placa de base);
* a **planta das terças**, com as terças ("TC13"), correntes e contraventos, e a lista das
  terças ("TC13-U100X40X2,65 - 56X").

Este módulo junta as quatro coisas como um detalhista faria: cada linha nomeada da planta
recebe a treliça da elevação de mesmo nome, em pé, com o banzo inferior no nível da
planta; os pilares vão da base até esse nível; as terças sentam no banzo superior das
treliças que passam embaixo. As plantas ficam em lugares diferentes do arquivo: elas
são alinhadas pelos balões dos eixos, que têm o mesmo nome em todas.

A peça que na planta é um arco sai calandrada: um sólido varrido ao longo do arco, com
um anel a cada 3° (como o IFC do TecnoMETAL), que o detalhamento já sabe ler.

O resultado é conferido pelo próprio projeto: quantas treliças de cada nome o título
pede ("- 7X") contra quantas a planta tem, e o mesmo para pilares e terças.
"""
from __future__ import annotations

import collections
import math
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados

__all__ = ["montar", "PADRAO", "ler_elevacoes", "pecas_da_planta", "quadro_do_usado"]

Ponto2 = Tuple[float, float]

PADRAO = {
    "planta": "PLANTA NO NÍVEL 6,00",          # título (começo) da planta estrutural
    "nivel": 6000.0,                            # nível do banzo inferior, mm
    "locacao": "LOCAÇÃO",                       # título da locação dos pilares
    "base": 0.0,                                # nível da base dos pilares, mm
    "tercas": "PLANTA NO NÍVEL DAS TERÇAS",     # título da planta das terças
    "familias": ["TESOURA", "PAINEL", "TRANSIÇÃO", "TRELIÇA", "COMP"],
    "aco": "ASTM A36",
    "outras": [],                               # [{planta, nivel}]: mezanino, caixa d'água…
    "deitadas": False,                          # faixa de treliça vista de cima vira treliça deitada (senão, a conferir)
    "duas_pecas": [],                           # elevações que são duas peças: a viga de transição e a tesoura em cima
}

#: camadas de anotação: não têm peça
_ANOT = re.compile(r"(?i)(cota|dim|eixo|texto|reg\d|anno|linha fina|projeç|alvenaria|concreto|caixa|chapas|veícul|"
                   r"area|área|esquadria|vista|folha|defpoints|telha|hach)")


_COM_ACENTO = {"TRANSICAO": "TRANSIÇÃO", "TRELICA": "TRELIÇA"}


def _bonito(nome: str) -> str:
    """o nome como o projetista escreve ("TRANSIÇÃO 4"), para mostrar"""
    fam, _, resto = str(nome).partition(" ")
    return (_COM_ACENTO.get(fam, fam) + (" " + resto if resto else "")).strip()


def _sem_acento(s: str) -> str:
    return (s.upper().replace("Ç", "C").replace("Ã", "A").replace("Á", "A").replace("É", "E").replace("Ê", "E")
            .replace("Í", "I").replace("Ó", "O").replace("Õ", "O").replace("Ú", "U"))


# =====================================================================================
# Geometria 2D
# =====================================================================================

def _pt(e) -> Ponto2:
    t = e["tipo"]
    if t == "linha":
        return (e["a"][0], e["a"][1])
    if t == "polilinha":
        return (e["vertices"][0][0], e["vertices"][0][1])
    if t == "arco":
        # o meio do arco (o centro de um arco grande fica longe do desenho, fora da planta)
        a0, a1 = e["inicio"] % 360.0, e["fim"] % 360.0
        meio = math.radians(a0 + ((a1 - a0) % 360.0) / 2.0)
        return (e["centro"][0] + e["raio"] * math.cos(meio), e["centro"][1] + e["raio"] * math.sin(meio))
    if t == "circulo":
        return (e["centro"][0], e["centro"][1])
    return (e["posicao"][0], e["posicao"][1])


def _dentro(p, caixa) -> bool:
    return caixa[0] <= p[0] <= caixa[2] and caixa[1] <= p[1] <= caixa[3]


class _Seg(tuple):
    """segmento (a, b, camada) que lembra de qual entidade do desenho saiu (`id`)"""

    def __new__(cls, a, b, cam, eid=None):
        s_ = tuple.__new__(cls, (a, b, cam))
        s_.id = eid
        return s_


def _segmentos(ents: Iterable[dict], so_camadas=None) -> List[Tuple[Ponto2, Ponto2, str]]:
    out = []
    for e in ents:
        cam = e.get("camada", "")
        # pedida a camada, vale ela (a "1-Terça Eixo" tem "eixo" no nome e é peça)
        if (so_camadas and not so_camadas.search(cam)) or (not so_camadas and _ANOT.search(cam)):
            continue
        if e["tipo"] == "linha":
            a, b = (e["a"][0], e["a"][1]), (e["b"][0], e["b"][1])
            if math.dist(a, b) > 1.0:
                out.append(_Seg(a, b, cam, e.get("id")))
        elif e["tipo"] == "polilinha":
            v = [(p[0], p[1]) for p in e["vertices"]]
            if e.get("fechada") and len(v) > 2:
                v.append(v[0])
            for a, b in zip(v, v[1:]):
                if math.dist(a, b) > 1.0:
                    out.append(_Seg(a, b, cam, e.get("id")))
    return out


def _copiar_mov(e: dict, dx: float, dy: float) -> dict:
    """a entidade deslocada (mesma id: é a mesma peça do desenho, vista no lugar da obra)"""
    n = dict(e)
    for k in ("a", "b", "centro", "posicao"):
        if k in n and n[k] is not None:
            n[k] = [n[k][0] + dx, n[k][1] + dy] + list(n[k][2:])
    if "vertices" in n:
        n["vertices"] = [[v[0] + dx, v[1] + dy] + list(v[2:]) for v in n["vertices"]]
    return n


def _unit(a, b):
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L), L


@dataclass
class Caminho:
    """Linha de centro de uma peça na planta: reta (a → b), arco (centro, raio, ângulos
    em graus no sentido anti-horário, de `ini` a `fim`) ou composto — a borda curva feita
    de arcos e retas emendados na mesma tangente (`partes`: [(caminho, ao_contrário)])."""
    tipo: str
    a: Ponto2 = (0.0, 0.0)
    b: Ponto2 = (0.0, 0.0)
    centro: Ponto2 = (0.0, 0.0)
    raio: float = 0.0
    ini: float = 0.0
    fim: float = 0.0
    largura: float = 0.0
    camada: str = ""
    partes: Optional[list] = None
    fontes: Optional[frozenset] = None      # ids das entidades do desenho que formam a peça

    @property
    def varredura(self) -> float:
        return (self.fim - self.ini) % 360.0 or 360.0

    @property
    def comprimento(self) -> float:
        if self.tipo == "reta":
            return math.dist(self.a, self.b)
        if self.tipo == "composto":
            return sum(p.comprimento for p, _r in self.partes)
        return math.radians(self.varredura) * self.raio

    @property
    def curvo(self) -> bool:
        return self.tipo == "arco" or (self.tipo == "composto" and any(p.tipo == "arco" for p, _r in self.partes))

    def _parte(self, s: float):
        """(parte, s local na parte, ao_contrário) do composto"""
        acum = 0.0
        for i, (p, rev) in enumerate(self.partes):
            L = p.comprimento
            if s <= acum + L or i == len(self.partes) - 1:
                sl = min(max(s - acum, 0.0), L)
                return p, (L - sl if rev else sl), rev
            acum += L

    def ponto(self, s: float) -> Ponto2:
        """ponto à distância `s` do começo, medida ao longo da peça"""
        if self.tipo == "reta":
            (ux, uy), _L = _unit(self.a, self.b)
            return (self.a[0] + ux * s, self.a[1] + uy * s)
        if self.tipo == "composto":
            p, sl, _rev = self._parte(s)
            return p.ponto(sl)
        ang = math.radians(self.ini) + s / self.raio
        return (self.centro[0] + self.raio * math.cos(ang), self.centro[1] + self.raio * math.sin(ang))

    def tangente(self, s: float) -> Tuple[float, float]:
        if self.tipo == "reta":
            return _unit(self.a, self.b)[0]
        if self.tipo == "composto":
            p, sl, rev = self._parte(s)
            tx, ty = p.tangente(sl)
            return (-tx, -ty) if rev else (tx, ty)
        ang = math.radians(self.ini) + s / self.raio
        return (-math.sin(ang), math.cos(ang))

    def projetar(self, p: Ponto2) -> Tuple[float, float]:
        """(s, distância) do ponto à linha de centro; s fica entre 0 e o comprimento"""
        if self.tipo == "composto":
            melhor, acum = None, 0.0
            for q, rev in self.partes:
                L = q.comprimento
                sl, d = q.projetar(p)
                s = acum + (L - sl if rev else sl)
                if melhor is None or d < melhor[1]:
                    melhor = (s, d)
                acum += L
            return melhor
        if self.tipo == "reta":
            (ux, uy), L = _unit(self.a, self.b)
            s = max(0.0, min(L, (p[0] - self.a[0]) * ux + (p[1] - self.a[1]) * uy))
            q = self.ponto(s)
            return s, math.dist(p, q)
        ang = math.degrees(math.atan2(p[1] - self.centro[1], p[0] - self.centro[0])) % 360
        rel = (ang - self.ini) % 360
        if rel <= self.varredura:
            return math.radians(rel) * self.raio, abs(math.dist(p, self.centro) - self.raio)
        s0, s1 = 0.0, self.comprimento
        d0, d1 = math.dist(p, self.ponto(s0)), math.dist(p, self.ponto(s1))
        return (s0, d0) if d0 <= d1 else (s1, d1)

    def trecho(self, s0: float, s1: float) -> "Caminho":
        if self.tipo == "composto":
            novas, acum = [], 0.0
            for q, rev in self.partes:
                L = q.comprimento
                a, b = max(s0, acum), min(s1, acum + L)
                if b - a > 1.0:
                    la, lb = a - acum, b - acum
                    if rev:
                        la, lb = L - lb, L - la
                    novas.append((q.trecho(la, lb), rev))
                acum += L
            if len(novas) == 1 and not novas[0][1]:
                return novas[0][0]
            return Caminho("composto", partes=novas, largura=self.largura, camada=self.camada, fontes=self.fontes)
        if self.tipo == "reta":
            return Caminho("reta", a=self.ponto(s0), b=self.ponto(s1), largura=self.largura, camada=self.camada, fontes=self.fontes)
        return Caminho("arco", centro=self.centro, raio=self.raio, ini=(self.ini + math.degrees(s0 / self.raio)) % 360,
                       fim=(self.ini + math.degrees(s1 / self.raio)) % 360, largura=self.largura, camada=self.camada, fontes=self.fontes)

    def invertido(self) -> "Caminho":
        if self.tipo == "reta":
            return Caminho("reta", a=self.b, b=self.a, largura=self.largura, camada=self.camada, fontes=self.fontes)
        # o arco não inverte o sentido dos ângulos: quem inverte é o mapeamento (s → L − s)
        return self


def centros_retos(segs, lmin: float = 250.0, larg=(15.0, 260.0)) -> List[Caminho]:
    """Pares de segmentos paralelos, a uma distância de largura de perfil, que correm
    juntos → linha de centro. Um segmento entra em um par só."""
    info = []
    for sg in segs:
        a, b, cam = sg
        (ux, uy), L = _unit(a, b)
        if L < lmin:
            continue
        if ux < -1e-9 or (abs(ux) < 1e-9 and uy < 0):
            a, b, ux, uy = b, a, -ux, -uy
        info.append((a, b, ux, uy, L, cam, getattr(sg, "id", None)))
    por_ang: Dict[int, List[int]] = collections.defaultdict(list)
    for i, s in enumerate(info):
        por_ang[int(round(math.degrees(math.atan2(s[3], s[2])))) % 180].append(i)
    usados = set()
    out: List[Caminho] = []
    ordem = sorted(range(len(info)), key=lambda i: -info[i][4])
    for i in ordem:
        if i in usados:
            continue
        a, b, ux, uy, L, cam, _id = info[i]
        ang = int(round(math.degrees(math.atan2(uy, ux)))) % 180
        cands = set()
        for d in (-1, 0, 1):
            cands |= set(por_ang[(ang + d) % 180])
        melhor = None
        for j in cands:
            if j == i or j in usados:
                continue
            c, d_, vx, vy, M, _, _id2 = info[j]
            if abs(ux * vy - uy * vx) > 0.01:
                continue
            n = (-uy, ux)
            dist = (c[0] - a[0]) * n[0] + (c[1] - a[1]) * n[1]
            if not (larg[0] <= abs(dist) <= larg[1]):
                continue
            s0 = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
            s1 = (d_[0] - a[0]) * ux + (d_[1] - a[1]) * uy
            lo, hi = max(0.0, min(s0, s1)), min(L, max(s0, s1))
            if hi - lo < 0.6 * min(L, M):
                continue
            nota = (hi - lo) / max(L, M) - abs(dist) / 1000.0
            if melhor is None or nota > melhor[0]:
                melhor = (nota, j, dist, s0, s1)
        if melhor:
            _, j, dist, s0, s1 = melhor
            usados.add(i)
            usados.add(j)
            lo2, hi2 = min(0.0, s0, s1), max(L, s0, s1)
            n = (-uy, ux)
            m = (a[0] + n[0] * dist / 2, a[1] + n[1] * dist / 2)
            out.append(Caminho("reta", a=(m[0] + ux * lo2, m[1] + uy * lo2), b=(m[0] + ux * hi2, m[1] + uy * hi2),
                               largura=abs(dist), camada=cam,
                               fontes=frozenset(x for x in (info[i][6], info[j][6]) if x)))
    return out, [info[i] for i in range(len(info)) if i not in usados]


def _estender_na_linha(c: Caminho, caminhos: List[Caminho], alvo: float, vao: float = 400.0) -> Caminho:
    """o trecho reto `c` crescido pelos trechos retos na mesma linha (mesma largura, a menos
    de `vao` da ponta), até ter o comprimento `alvo`"""
    (ux, uy), L = _unit(c.a, c.b)
    a0, a1 = 0.0, L
    fontes = set(c.fontes or ())
    usados = set()
    mudou = True
    while mudou and a1 - a0 < 0.97 * alvo:
        mudou = False
        for k, d in enumerate(caminhos):
            if k in usados or d is c or d.tipo != "reta" or abs(d.largura - c.largura) > 30.0:
                continue
            (vx, vy), M = _unit(d.a, d.b)
            if abs(ux * vy - uy * vx) > 0.01 or abs((d.a[0] - c.a[0]) * -uy + (d.a[1] - c.a[1]) * ux) > 30.0:
                continue
            s0 = (d.a[0] - c.a[0]) * ux + (d.a[1] - c.a[1]) * uy
            s1 = (d.b[0] - c.a[0]) * ux + (d.b[1] - c.a[1]) * uy
            lo, hi = min(s0, s1), max(s0, s1)
            if a0 - vao <= hi <= a0 + 1.0 and lo < a0:
                a0 = lo
            elif a1 - 1.0 <= lo <= a1 + vao and hi > a1:
                a1 = hi
            else:
                continue
            usados.add(k)
            fontes |= set(d.fontes or ())
            mudou = True
    if a0 == 0.0 and a1 == L:
        return c
    return Caminho("reta", a=(c.a[0] + ux * a0, c.a[1] + uy * a0), b=(c.a[0] + ux * a1, c.a[1] + uy * a1),
                   largura=c.largura, camada=c.camada, fontes=frozenset(fontes))


def juntar_colineares(retas: List[Caminho], vao: float = 400.0) -> List[Caminho]:
    """a linha dupla da treliça é interrompida onde outra peça cruza por cima: os trechos
    retos na mesma linha, com a mesma largura e separados por menos de `vao`, voltam a ser
    uma linha só (o nome e o comprimento da elevação cortam de novo onde for preciso)"""
    restantes = list(retas)
    out: List[Caminho] = []
    while restantes:
        c = restantes.pop()
        mudou = True
        while mudou:
            mudou = False
            (ux, uy), L = _unit(c.a, c.b)
            for k, d in enumerate(restantes):
                if abs(d.largura - c.largura) > 30.0:
                    continue
                (vx, vy), M = _unit(d.a, d.b)
                if abs(ux * vy - uy * vx) > 0.01:
                    continue
                # mesma linha: o outro trecho a menos de 30 mm da reta deste
                off = abs((d.a[0] - c.a[0]) * -uy + (d.a[1] - c.a[1]) * ux)
                if off > 30.0:
                    continue
                s0 = (d.a[0] - c.a[0]) * ux + (d.a[1] - c.a[1]) * uy
                s1 = (d.b[0] - c.a[0]) * ux + (d.b[1] - c.a[1]) * uy
                lo, hi = min(s0, s1), max(s0, s1)
                if lo > L + vao or hi < -vao:
                    continue
                n0, n1 = min(0.0, lo), max(L, hi)
                a = (c.a[0] + ux * n0, c.a[1] + uy * n0)
                b = (c.a[0] + ux * n1, c.a[1] + uy * n1)
                c = Caminho("reta", a=a, b=b, largura=(c.largura + d.largura) / 2, camada=c.camada,
                            fontes=frozenset(c.fontes or ()) | frozenset(d.fontes or ()))
                restantes.pop(k)
                mudou = True
                break
        out.append(c)
    return out


def encadear(caminhos: List[Caminho], tol: float = 40.0, ang_max: float = 12.0) -> List[Caminho]:
    """junta, num caminho composto, os trechos que se emendam na mesma tangente quando a
    emenda envolve um arco: é a borda curva da cobertura, que o projetista desenha em arcos
    e retas mas que é uma peça (um painel) só"""
    cosmax = math.cos(math.radians(ang_max))
    usados = set()
    out: List[Caminho] = []

    def pontas(c):
        L = c.comprimento
        return (c.ponto(0.0), c.tangente(0.0)), (c.ponto(L), c.tangente(L))

    info = [pontas(c) for c in caminhos]

    def seguinte(p, t, excluir):
        """o trecho que continua do ponto p na direção t: (índice, ao_contrário)"""
        melhor = None
        for j, c in enumerate(caminhos):
            if j in excluir or j in usados:
                continue
            (a, ta), (b, tb) = info[j]
            if abs(c.largura - caminhos[excluir_ref[0]].largura) > 60.0:
                continue

            def encosta(q):
                # a ponta encostada, ou passando um pouco por cima da outra linha (o arco que
                # o projetista esticou além da tangência)
                d = math.dist(p, q)
                return d < tol or (d < 300.0 and c.projetar(p)[1] < tol)
            if encosta(a) and t[0] * ta[0] + t[1] * ta[1] > cosmax:
                d = math.dist(p, a)
                if melhor is None or d < melhor[0]:
                    melhor = (d, j, False)
            if encosta(b) and -(t[0] * tb[0] + t[1] * tb[1]) > cosmax:
                d = math.dist(p, b)
                if melhor is None or d < melhor[0]:
                    melhor = (d, j, True)
        return melhor
    excluir_ref = [0]
    for i, c in enumerate(caminhos):
        if i in usados or c.tipo != "arco":
            continue
        excluir_ref[0] = i
        cadeia = [(i, False)]
        usados.add(i)
        # para frente
        while True:
            j, rev = cadeia[-1]
            (a, ta), (b, tb) = info[j]
            p, t = (a, (-ta[0], -ta[1])) if rev else (b, tb)
            m = seguinte(p, t, {k for k, _r in cadeia})
            if not m:
                break
            cadeia.append((m[1], m[2]))
            usados.add(m[1])
        # para trás
        while True:
            j, rev = cadeia[0]
            (a, ta), (b, tb) = info[j]
            p, t = (b, tb) if rev else (a, (-ta[0], -ta[1]))
            m = seguinte(p, t, {k for k, _r in cadeia})
            if not m:
                break
            cadeia.insert(0, (m[1], not m[2]))
            usados.add(m[1])
        if len(cadeia) == 1:
            out.append(c)
        else:
            out.append(Caminho("composto", partes=[(caminhos[k], r) for k, r in cadeia], largura=c.largura,
                               camada=c.camada,
                               fontes=frozenset().union(*[caminhos[k].fontes or frozenset() for k, _r in cadeia])))
    out += [c for k, c in enumerate(caminhos) if k not in usados]
    return out


def centros_arcos(ents, dr=(15.0, 260.0), raio_min: float = 400.0) -> List[Caminho]:
    arcos = [e for e in ents if e["tipo"] == "arco" and not _ANOT.search(e.get("camada", "")) and e["raio"] > raio_min]
    usados = set()
    out = []
    for i, p in enumerate(arcos):
        if i in usados:
            continue
        for j in range(i + 1, len(arcos)):
            q = arcos[j]
            if j in usados or math.dist(p["centro"][:2], q["centro"][:2]) > 5.0:
                continue
            d = abs(p["raio"] - q["raio"])
            if not (dr[0] <= d <= dr[1]):
                continue
            a0, a1 = p["inicio"] % 360, p["fim"] % 360
            b0, b1 = q["inicio"] % 360, q["fim"] % 360
            if min(abs(a0 - b0), 360 - abs(a0 - b0)) > 25 and min(abs(a1 - b1), 360 - abs(a1 - b1)) > 25:
                continue
            usados.add(i)
            usados.add(j)
            ini, fim = (a0, a1) if (a1 - a0) % 360 >= (b1 - b0) % 360 else (b0, b1)
            out.append(Caminho("arco", centro=(p["centro"][0], p["centro"][1]), raio=(p["raio"] + q["raio"]) / 2,
                               ini=ini, fim=fim, largura=d, camada=p.get("camada", ""),
                               fontes=frozenset(x for x in (p.get("id"), q.get("id")) if x)))
            break
    return out


# =====================================================================================
# Blocos do desenho (plantas, elevações) e balões de eixo
# =====================================================================================

def _componentes(segs, celula: float) -> List[dict]:
    """grupos de segmentos que se tocam (na grade de `celula` mm) com a caixa de cada um"""
    pai = list(range(len(segs)))

    def acha(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    grade: Dict[tuple, int] = {}
    for i, (a, b, _c) in enumerate(segs):
        L = math.dist(a, b)
        n = max(1, int(L / celula))
        for k in range(n + 1):
            x = a[0] + (b[0] - a[0]) * k / n
            y = a[1] + (b[1] - a[1]) * k / n
            ch = (int(x // celula), int(y // celula))
            if ch in grade:
                ra, rb = acha(grade[ch]), acha(i)
                if ra != rb:
                    pai[rb] = ra
            else:
                grade[ch] = i
    grupos: Dict[int, List[int]] = collections.defaultdict(list)
    for i in range(len(segs)):
        grupos[acha(i)].append(i)
    out = []
    for lst in grupos.values():
        pts = [p for i in lst for p in segs[i][:2]]
        out.append({"segs": [segs[i] for i in lst],
                    "caixa": (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))})
    return out


def _achar_titulo(textos, comeco: str) -> Optional[dict]:
    alvo = _sem_acento(comeco).replace(" ", "")
    cands = [t for t in textos if _sem_acento(t["texto"]).replace(" ", "").startswith(alvo)]
    if not cands:
        return None
    return max(cands, key=lambda t: t.get("altura") or 0)


def bloco_do_titulo(ents, titulo: dict, celula: float = 1500.0) -> Tuple[float, float, float, float]:
    """a caixa do desenho logo acima do título (planta, locação): o maior grupo de linhas
    de peça cuja base está até 8 m acima do título e que cobre o x dele"""
    tx, ty = titulo["posicao"][0], titulo["posicao"][1]
    perto = [e for e in ents if e["tipo"] in ("linha", "polilinha", "arco") and abs(_pt(e)[0] - tx) < 150000
             and -3000 < _pt(e)[1] - ty < 150000]
    segs = _segmentos(perto)
    # o arco (a borda curva) também faz parte da moldura: entra em cordas
    for e in perto:
        if e["tipo"] == "arco" and not _ANOT.search(e.get("camada", "")):
            c = Caminho("arco", centro=(e["centro"][0], e["centro"][1]), raio=e["raio"], ini=e["inicio"] % 360,
                        fim=e["fim"] % 360)
            n = max(2, int(c.varredura / 10.0))
            pts = [c.ponto(c.comprimento * k / n) for k in range(n + 1)]
            segs += [(a, b, e.get("camada", "")) for a, b in zip(pts, pts[1:])]
    comps = _componentes(segs, celula)
    # a moldura da folha (um retângulo de poucas linhas em volta de várias vistas) não é
    # desenho: fora dela, a busca não pula de uma vista para a outra
    comps = [c for c in comps if not (len(c["segs"]) <= 8 and max(c["caixa"][2] - c["caixa"][0],
                                                                  c["caixa"][3] - c["caixa"][1]) > 20000.0)]
    melhor = None
    for c in comps:
        x0, y0, x1, y1 = c["caixa"]
        if not (x0 - 5000 <= tx <= x1 + 5000) or not (-2000 <= y0 - ty <= 8000):
            continue
        area = (x1 - x0) * (y1 - y0)
        if melhor is None or area > melhor[0]:
            melhor = (area, c["caixa"])
    if melhor is None:
        raise ErroDeDados("não achei o desenho acima do título \"%s\"." % titulo["texto"])
    # a planta é feita de grupos que nem sempre se tocam (uma treliça solta, a borda): junta
    # os grupos vizinhos, a menos de 12 m, até a moldura parar de crescer (as plantas de
    # um mesmo arquivo ficam dezenas de metros uma da outra)
    x0, y0, x1, y1 = melhor[1]
    folga = 12000.0
    # cada grupo é do título grande mais perto logo abaixo dele: o grupo de outra vista (o
    # corte ao lado, a vista empilhada em cima) não entra na moldura desta
    grandes = [t for t in ents if t["tipo"] == "texto" and (t.get("altura") or 0) >= 20
               and abs(t["posicao"][0] - tx) < 160000 and -20000 < t["posicao"][1] - ty < 160000]

    def dono(caixa_c):
        a0, b0, a1, b1 = caixa_c
        cands = [(b0 - t["posicao"][1], t) for t in grandes
                 if -500 <= b0 - t["posicao"][1] <= 15000 and a0 - 5000 <= t["posicao"][0] <= a1 + 5000]
        return min(cands, key=lambda c_: c_[0])[1] if cands else None
    mudou = True
    while mudou:
        mudou = False
        for c in comps:
            a0, b0, a1, b1 = c["caixa"]
            if a0 >= x0 and b0 >= y0 and a1 <= x1 and b1 <= y1:
                continue
            if a0 <= x1 + folga and a1 >= x0 - folga and b0 <= y1 + folga and b1 >= y0 - folga:
                d_ = dono(c["caixa"])
                if d_ is not None and d_ is not titulo:
                    continue
                x0, y0, x1, y1 = min(x0, a0), min(y0, b0), max(x1, a1), max(y1, b1)
                mudou = True
    return (x0, y0, x1, y1)


def baloes(ents, caixa, folga: float = 4000.0) -> Dict[str, Ponto2]:
    """{nome do eixo: centro do balão} dos balões em volta da planta"""
    x0, y0, x1, y1 = caixa
    cx = (x0 - folga, y0 - folga, x1 + folga, y1 + folga)
    circ = [e for e in ents if e["tipo"] == "circulo" and 120 < e["raio"] < 800 and _dentro(e["centro"], cx)]
    txt = [e for e in ents if e["tipo"] == "texto" and _dentro(e["posicao"], cx)
           and re.fullmatch(r"[A-Za-z]{0,2}\d{0,2}[A-Za-z]?", e["texto"].strip() or "-")]
    grade: Dict[tuple, List[dict]] = collections.defaultdict(list)
    for t in txt:
        grade[(int(t["posicao"][0] // 1000), int(t["posicao"][1] // 1000))].append(t)
    pares = []
    for ic, c in enumerate(circ):
        r = c["raio"]
        gx, gy = int(c["centro"][0] // 1000), int(c["centro"][1] // 1000)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for t in grade.get((gx + dx, gy + dy), []):
                    # o texto do balão começa um pouco à esquerda e abaixo do centro
                    if abs(t["posicao"][0] - c["centro"][0]) < 1.3 * r and abs(t["posicao"][1] - c["centro"][1]) < 1.3 * r:
                        pares.append((math.dist(t["posicao"][:2], c["centro"][:2]), ic, id(t), t))
    # um texto por balão e um balão por texto, do par mais perto para o mais longe: nos balões
    # encostados (eixos 9 e 10 do Posto CB, a 50 cm) o "10" também cabe no balão do 9
    out: Dict[str, List[Ponto2]] = collections.defaultdict(list)
    c_usados, t_usados = set(), set()
    for _d, ic, it, t in sorted(pares, key=lambda x: x[0]):
        if ic in c_usados or it in t_usados:
            continue
        c_usados.add(ic)
        t_usados.add(it)
        c = circ[ic]["centro"]
        out[t["texto"].strip().upper()].append((c[0], c[1]))
    return {k: v[0] for k, v in out.items() if len(v) >= 1}


def deslocamento_entre(ref: Dict[str, Ponto2], outra: Dict[str, Ponto2]) -> Optional[Tuple[float, float, int]]:
    """o quanto somar às coordenadas de `outra` para cair sobre `ref` (mediana dos balões
    de mesmo nome), e quantos balões concordaram"""
    ds = [(ref[k][0] - outra[k][0], ref[k][1] - outra[k][1]) for k in ref if k in outra]
    if not ds:
        return None
    mx = sorted(d[0] for d in ds)[len(ds) // 2]
    my = sorted(d[1] for d in ds)[len(ds) // 2]
    ok = [d for d in ds if abs(d[0] - mx) < 50 and abs(d[1] - my) < 50]
    if not ok:
        return None
    return (sum(d[0] for d in ok) / len(ok), sum(d[1] for d in ok) / len(ok), len(ok))


# =====================================================================================
# Elevações
# =====================================================================================

@dataclass
class Membro:
    s0: float
    h0: float
    s1: float
    h1: float
    papel: str                  # banzo, montante, diagonal
    altura_linha: float = 0.0   # distância entre as duas linhas (perfil deitado no banzo)
    caixa: float = 0.0          # banzo em caixão (2U boca com boca): a altura dele (2 × aba)


@dataclass
class Elevacao:
    nome: str                   # "TESOURA 1"
    familia: str
    qtd: int
    comprimento: float
    membros: List[Membro] = field(default_factory=list)
    banzo: Optional[dict] = None
    alma: Optional[dict] = None
    titulo_em: Ponto2 = (0.0, 0.0)
    avisos: List[str] = field(default_factory=list)
    x_esq: float = 0.0                                          # onde começa, no desenho
    y_base: float = 0.0                                         # eixo do banzo inferior, no desenho
    caixa: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    marcas_terca: List[float] = field(default_factory=list)     # s das marcas "ST" (suporte de terça)
    fontes: set = field(default_factory=set)                    # ids das entidades do desenho dela
    emenda: Optional[str] = None                                # "inicio" | "fim": a ponta que é a emenda (peça separada)
    fundo: list = field(default_factory=list)                   # as linhas que a leitura tirou (a vista de fundo)
    apoio_terca: Optional[dict] = None                          # o perfil de apoio das terças, dos dois lados
    parte_de: Optional[str] = None                              # a elevação desenhada junto (a TRANSIÇÃO 3 na da 2)
    topo_telhado: Optional[float] = None                        # em duas peças: o topo da viga (o telhado passa ali)

    def topo(self, s: float) -> Optional[float]:
        """altura do eixo do banzo superior em `s` (o mais alto que passa por ali)"""
        hs = []
        for m in self.membros:
            if m.papel != "banzo" or max(m.h0, m.h1) < 1.0:
                continue
            lo, hi = min(m.s0, m.s1), max(m.s0, m.s1)
            if lo - 1.0 <= s <= hi + 1.0 and hi - lo > 1.0:
                t = (s - m.s0) / (m.s1 - m.s0)
                hs.append(m.h0 + (m.h1 - m.h0) * t)
        return max(hs) if hs else None


def _titulo_regex(familias: Sequence[str]):
    fam = "|".join(re.escape(_sem_acento(f)).replace("A", "[AÃÁ]").replace("C", "[CÇ]") for f in familias)
    # "TESOURA 1 - 7X", "COMP.10 2X"
    return re.compile(r"(?i)^\s*(" + fam + r")\.?\s*([\w]+)\s*-?\s*(\d+)\s*X\s*$")


def ler_elevacoes(ents, familias: Sequence[str]) -> Dict[str, Elevacao]:
    """as elevações "FAMÍLIA n - kX" do desenho: membros no referencial da treliça
    (s ao longo do banzo inferior, da ponta esquerda; h para cima do eixo dele)"""
    from nucleo2d.reconhecer import perfil_do_texto
    rx = _titulo_regex(familias)
    titulos = []
    for e in ents:
        if e["tipo"] == "texto":
            m = rx.match(e["texto"])
            if m:
                titulos.append((_sem_acento(m.group(1)) + " " + m.group(2).upper(), int(m.group(3)), e))
    if not titulos:
        return {}
    xs = [t[2]["posicao"][0] for t in titulos]
    ys = [t[2]["posicao"][1] for t in titulos]
    caixa = (min(xs) - 25000, min(ys) - 2000, max(xs) + 45000, max(ys) + 12000)
    regiao = [e for e in ents if _dentro(_pt(e), caixa)]
    comps = [c for c in _componentes(_segmentos(regiao), 150.0) if c["caixa"][2] - c["caixa"][0] > 800]
    textos = [e for e in regiao if e["tipo"] == "texto"]
    # linhas de chamada curtas e inclinadas (do texto "ST2" até o apoio da terça)
    chamadas: Dict[tuple, list] = collections.defaultdict(list)
    for e in regiao:
        if e["tipo"] != "linha":
            continue
        a, b = (e["a"][0], e["a"][1]), (e["b"][0], e["b"][1])
        L = math.dist(a, b)
        if 60.0 <= L <= 900.0 and abs(a[1] - b[1]) > 40.0:
            alto, baixo = (a, b) if a[1] > b[1] else (b, a)
            chamadas[(int(alto[0] // 1000), int(alto[1] // 1000))].append((alto, baixo))
    out: Dict[str, Elevacao] = {}

    def do_titulo(t):
        """o desenho de um título: o componente logo acima dele, começando perto do texto"""
        tx, ty = t["posicao"][0], t["posicao"][1]
        melhor = None
        for c in comps:
            x0, y0, x1, y1 = c["caixa"]
            dy = y0 - ty
            if not (-300 < dy < 4000):
                continue
            dx = x0 - tx
            if not (-4000 < dx < 4000):
                continue
            nota = abs(dx) * 1.5 + abs(dy)
            if melhor is None or nota < melhor[0]:
                melhor = (nota, c)
        return melhor[1] if melhor else None
    # os desenhos que têm título; o que sobra ao lado de um deles pode ser a continuação dele
    com_titulo = {id(c) for c in (do_titulo(t) for _n, _q, t in titulos) if c is not None}
    for nome, qtd, t in titulos:
        if nome in out:
            continue
        tx, ty = t["posicao"][0], t["posicao"][1]
        c = do_titulo(t)
        if c is None:
            continue
        cont = _continuacao(c, comps, com_titulo)
        if cont is not None:
            com_titulo.add(id(cont))
            c = {"segs": c["segs"] + cont["segs"],
                 "caixa": (c["caixa"][0], min(c["caixa"][1], cont["caixa"][1]), cont["caixa"][2], max(c["caixa"][3], cont["caixa"][3])),
                 "emenda": (c["caixa"][2], cont["caixa"][0])}
        x0, y0, x1, y1 = c["caixa"]
        # a nota dos perfis fica entre o desenho e o título
        banzo = alma = None
        notas_ids = set()
        for n in textos:
            px, py = n["posicao"][0], n["posicao"][1]
            if not (x0 - 1500 <= px <= x1 and ty - 50 <= py <= y0 + 50):
                continue
            s = _sem_acento(n["texto"])
            r = perfil_do_texto(n["texto"])
            if not r:
                continue
            if "BANZO" in s and banzo is None:
                banzo = r
                notas_ids.add(n.get("id"))
            elif re.search(r"DIAG|MONT", s) and alma is None:
                alma = r
                notas_ids.add(n.get("id"))
        el = _elevacao_do_grupo(nome, qtd, c["segs"])
        el.banzo, el.alma = banzo, alma
        if c.get("emenda"):
            _ligar_emenda(el, c["emenda"][0] - el.x_esq, c["emenda"][1] - el.x_esq)
        _alma_lida_duas_vezes(el)
        if banzo and int(banzo.get("mult") or 1) >= 2 and re.match(r"(?i)^U", str(banzo.get("perfil") or "")):
            _banzo_em_caixao(el, c["segs"])
        el.titulo_em = (tx, ty)
        el.caixa = (x0, y0, x1, y1)
        # as marcas "ST2" em cima do banzo: onde cada terça apoia (o texto fica sempre do
        # mesmo lado do apoio; a orientação desconta essa distância)
        marcas = []
        for n in textos:
            if not (re.match(r"^\s*ST\s*\d", n["texto"]) and x0 - 800 <= n["posicao"][0] <= x1 + 800
                    and y0 - 100 <= n["posicao"][1] <= y1 + 1200):
                continue
            x_apoio = _ponta_da_chamada(n, chamadas)
            marcas.append((x_apoio if x_apoio is not None else n["posicao"][0]) - el.x_esq)
            notas_ids.add(n.get("id"))
        el.marcas_terca = sorted(marcas)
        _apoio_das_tercas(el, [n for n in textos if x0 - 500 <= n["posicao"][0] <= x1 + 500 and y0 - 200 <= n["posicao"][1] <= y1 + 200])
        el.fontes = ({getattr(sg, "id", None) for sg in c["segs"]} | notas_ids | {t.get("id")}) - {None}
        if el.membros:
            out[nome] = el
    return out


def _ponta_da_chamada(texto: dict, chamadas) -> Optional[float]:
    """x do apoio apontado pela chamada do texto: a linha inclinada que começa no
    sublinhado do texto (à altura dele, logo à direita ou à esquerda) e desce até o banzo"""
    tx, ty = texto["posicao"][0], texto["posicao"][1]
    larg = len(texto["texto"].strip()) * (texto.get("altura") or 2.5) * 50.0 * 0.8
    melhor = None
    gx, gy = int(tx // 1000), int(ty // 1000)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for alto, baixo in chamadas.get((gx + dx, gy + dy), []):
                if not (-250.0 <= alto[1] - ty <= 120.0):
                    continue
                # a chamada sai de uma das pontas do texto
                d = min(abs(alto[0] - tx), abs(alto[0] - (tx + larg)))
                if d > 350.0:
                    continue
                if melhor is None or d < melhor[0]:
                    melhor = (d, baixo[0])
    return melhor[1] if melhor else None


def _elevacao_do_grupo(nome: str, qtd: int, segs) -> Elevacao:
    duplas, simples = centros_retos(segs, lmin=120.0, larg=(12.0, 140.0))
    # linha de baixo: a dupla mais baixa quase horizontal e comprida
    horiz = [c for c in duplas if abs(c.b[1] - c.a[1]) < 0.03 * max(1.0, abs(c.b[0] - c.a[0]))]
    if not horiz:
        return Elevacao(nome=nome, familia=nome.split()[0], qtd=qtd, comprimento=0.0,
                        avisos=["%s: não achei o banzo inferior na elevação." % nome])
    largura_total = max(max(c.a[0], c.b[0]) for c in duplas) - min(min(c.a[0], c.b[0]) for c in duplas)
    compridas = [c for c in horiz if abs(c.b[0] - c.a[0]) > 0.3 * largura_total] or horiz
    inf = min(compridas, key=lambda c: (c.a[1] + c.b[1]) / 2)
    y_base = (inf.a[1] + inf.b[1]) / 2
    xs = [p[0] for c in duplas for p in (c.a, c.b)]
    x_esq, x_dir = min(xs), max(xs)
    el = Elevacao(nome=nome, familia=nome.split()[0], qtd=qtd, comprimento=x_dir - x_esq, x_esq=x_esq, y_base=y_base)

    def S(p):
        return (p[0] - x_esq, p[1] - y_base)
    for c in duplas:
        a, b = S(c.a), S(c.b)
        dx, dy = b[0] - a[0], b[1] - a[1]
        if abs(dx) >= abs(dy) * 1.5:
            papel = "banzo"
        elif abs(dx) < 0.1 * abs(dy):
            papel = "montante"
        else:
            papel = "diagonal"
        el.membros.append(Membro(a[0], a[1], b[0], b[1], papel, c.largura))
    # as linhas simples: montantes e diagonais (as curtas são marcas, tampas, detalhes)
    for a, b, _ux, _uy, L, _cam, _id in simples:
        if L < 250.0:
            continue
        pa, pb = S(a), S(b)
        if min(pa[1], pb[1]) < -200 or max(pa[1], pb[1]) > 4000 or min(pa[0], pb[0]) < -200 \
                or max(pa[0], pb[0]) > el.comprimento + 200:
            continue
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        if abs(dy) < 30.0:          # linha horizontal solta: borda de chapa, tampa
            continue
        papel = "montante" if abs(dx) < 0.1 * abs(dy) else "diagonal"
        el.membros.append(Membro(pa[0], pa[1], pb[0], pb[1], papel))
    # a mesma linha vista duas vezes (o contorno do montante de ponta) entra uma vez
    vistos = set()
    unicos = []
    for m in el.membros:
        k = (round(min(m.s0, m.s1) / 20), round(max(m.s0, m.s1) / 20), round(min(m.h0, m.h1) / 20),
             round(max(m.h0, m.h1) / 20))
        if k in vistos:
            continue
        vistos.add(k)
        unicos.append(m)
    el.membros = unicos
    _tirar_vista_de_fundo(el)
    return el



def _alma_lida_duas_vezes(el: Elevacao) -> int:
    """A mesma barra da alma lida duas vezes: a 2L desenhada com linha dupla de nó a nó e mais uma
    linha de face a face (TRANSIÇÃO 1 do Posto CB), ou a mesma dupla com quatro linhas. Fica uma:
    a menos de 30 mm, a mais larga; a linha simples a menos de 70 mm da dupla, a dupla. Os pares de
    verdade (os dois montantes da cumeeira, a 150 mm) ficam."""
    alma = [m for m in el.membros if m.papel in ("montante", "diagonal")]
    fora = set()

    def paralela(m, n):
        ax, ay = m.s1 - m.s0, m.h1 - m.h0
        bx, by = n.s1 - n.s0, n.h1 - n.h0
        La, Lb = math.hypot(ax, ay), math.hypot(bx, by)
        if La < 1.0 or Lb < 1.0 or abs(ax * by - ay * bx) / (La * Lb) > 0.05:
            return None
        mx, my = (n.s0 + n.s1) / 2.0, (n.h0 + n.h1) / 2.0
        t = ((mx - m.s0) * ax + (my - m.h0) * ay) / (La * La)
        if not 0.0 < t < 1.0:
            return None
        return abs((mx - m.s0) * ay - (my - m.h0) * ax) / La
    for i, m in enumerate(alma):
        if id(m) in fora:
            continue
        for n in alma[i + 1:]:
            if id(n) in fora:
                continue
            d = paralela(m, n)
            if d is None:
                d = paralela(n, m)
            if d is None:
                continue
            if d <= 30.0:
                fica, sai = (m, n) if (m.altura_linha, _comp_m(m)) >= (n.altura_linha, _comp_m(n)) else (n, m)
            elif d <= 70.0 and (m.altura_linha > 0.0) != (n.altura_linha > 0.0):
                fica, sai = (m, n) if m.altura_linha > 0.0 else (n, m)
                if _comp_m(sai) > _comp_m(fica) + 50.0:
                    continue                    # a linha simples maior que a dupla é outra barra
            else:
                continue
            fora.add(id(sai))
            if sai is m:
                break
    if fora:
        el.membros = [m for m in el.membros if id(m) not in fora]
        el.avisos.append("%s: %d barra(s) da alma desenhadas duas vezes (a linha dupla da cantoneira e mais uma linha "
                         "ao lado) entraram uma vez só." % (_bonito(el.nome), len(fora)))
    return len(fora)


def _apoio_das_tercas(el: Elevacao, notas: list) -> int:
    """O perfil que corre ao lado da treliça, no caimento do telhado, para receber as terças (a
    TRANSIÇÃO 1 do Posto CB: "U100X40X2,25 NO EIXO DA TRELIÇA" em cada trecho, um U de cada lado):
    a leitura o tomava pela tesoura vista ao fundo. As linhas duplas inclinadas que ela tirou e que
    têm essa nota ao lado voltam, como "apoio_terca", com o perfil da nota."""
    from nucleo2d.reconhecer import perfil_do_texto
    if not el.fundo:
        return 0
    marcadas = []
    for n in notas:
        txt = _sem_acento(n["texto"]).upper()
        if "BANZO" in txt or "DIAG" in txt or "MONT" in txt:
            continue
        r = perfil_do_texto(n["texto"])
        if not r or not re.match(r"(?i)^U", str(r.get("perfil") or "")):
            continue
        marcadas.append(((n["posicao"][0] - el.x_esq, n["posicao"][1] - el.y_base), r))
    if not marcadas:
        return 0
    volta = []
    perfil = None
    for m in el.fundo:
        if m.papel != "banzo" or m.altura_linha <= 0.0 or abs(m.s1 - m.s0) < 1500.0 or abs(m.h1 - m.h0) < 30.0:
            continue
        lo, hi = min(m.s0, m.s1), max(m.s0, m.s1)
        for (sx, hy), r in marcadas:
            if lo - 300.0 <= sx <= hi + 300.0:
                t = min(max((sx - m.s0) / ((m.s1 - m.s0) or 1.0), 0.0), 1.0)
                if abs(hy - (m.h0 + (m.h1 - m.h0) * t)) <= 700.0:
                    volta.append(m)
                    perfil = r
                    break
    if not volta:
        return 0
    for m in volta:
        m.papel = "apoio_terca"
    ids = {id(m) for m in volta}
    el.fundo = [m for m in el.fundo if id(m) not in ids]
    el.membros += volta
    el.apoio_terca = {"perfil": perfil["perfil"], "trecho": perfil.get("trecho")}
    el.avisos.append("%s: o perfil %s ao lado da treliça, no caimento do telhado (%d trechos), recebe as terças — "
                     "um de cada lado." % (_bonito(el.nome), perfil["perfil"], len(volta)))
    return len(volta)


def _comp_m(m: Membro) -> float:
    return math.hypot(m.s1 - m.s0, m.h1 - m.h0)


def _banzo_em_caixao(el: Elevacao, segs) -> int:
    """BANZO 2Ue/2U: os dois perfis de boca um para o outro formam um caixão (a TRANSIÇÃO 1 do Posto
    CB: 2Ue 250×70 → 250 × 140). A elevação desenha cada caixão com três linhas compridas — as duas
    faces e a junta das bocas no meio. Cada caixão vira um banzo só, no eixo da junta; e a base da
    elevação (h = 0) passa a ser o eixo do caixão de baixo."""
    pa = _perfil((el.banzo or {}).get("perfil"))
    bf = float(pa.bf) if pa is not None and pa.bf else 0.0
    if bf <= 0.0:
        return 0
    L = el.comprimento
    alturas = []
    for a, b, _cam in segs:
        dx, dy = b[0] - a[0], b[1] - a[1]
        if abs(dx) > 0.3 * L and abs(dy) < 0.02 * abs(dx):
            alturas.append(((a[1] + b[1]) / 2.0 - el.y_base, min(a[0], b[0]) - el.x_esq, max(a[0], b[0]) - el.x_esq))
    alturas.sort()
    grupos: List[list] = []
    for h in alturas:
        if grupos and h[0] - grupos[-1][-1][0] <= 1.3 * bf:
            grupos[-1].append(h)
        else:
            grupos.append([h])
    caixas = []
    for g in grupos:
        lo, hi = g[0][0], g[-1][0]
        if abs((hi - lo) - 2.0 * bf) <= 0.25 * bf:
            caixas.append(((lo + hi) / 2.0, hi - lo, min(x[1] for x in g), max(x[2] for x in g), lo, hi))
    if len(caixas) < 2:
        return 0
    base = caixas[0][0]
    novos = []
    for m in el.membros:
        if m.papel == "banzo" and any(lo - 60.0 <= (m.h0 + m.h1) / 2.0 <= hi + 60.0 and abs(m.h1 - m.h0) < 30.0
                                      for _hc, _alt, _s0, _s1, lo, hi in caixas):
            continue                        # as linhas do caixão lidas como banzos soltos
        novos.append(m)
    for hc, alt, s0, s1, _lo, _hi in caixas:
        novos.append(Membro(s0, hc, s1, hc, "banzo", alt, caixa=alt))
    for m in novos:
        m.h0 -= base
        m.h1 -= base
    el.membros = novos
    el.y_base += base
    el.avisos.append("%s: banzo em caixão (%s, os dois perfis boca com boca, %d mm de altura): um banzo só em cada "
                     "caixão, no eixo da junta." % (_bonito(el.nome), (el.banzo or {}).get("trecho") or "2U", round(caixas[0][1])))
    return len(caixas)


def _continuacao(c: dict, comps: list, com_titulo: set) -> Optional[dict]:
    """A elevação desenhada em duas partes, com um espaço pequeno entre elas (a TRANSIÇÃO 16 do
    Posto CB: 12,12 m + emenda de 270 mm + 19,73 m = 32,12 m, a cota total e o comprimento da linha
    na planta): o desenho sem título logo à direita, com a mesma altura, é a mesma peça."""
    x0, y0, x1, y1 = c["caixa"]
    h = y1 - y0
    melhor = None
    for o in comps:
        if o is c or id(o) in com_titulo:
            continue
        a0, b0, a1, b1 = o["caixa"]
        if not (0.0 <= a0 - x1 <= 600.0):
            continue
        if abs((b1 - b0) - h) > 0.15 * h or min(b1, y1) - max(b0, y0) < 0.8 * h:
            continue
        if melhor is None or a0 < melhor["caixa"][0]:
            melhor = o
    return melhor


def _ligar_emenda(el: Elevacao, s_a: float, s_b: float) -> int:
    """Os banzos das duas partes, interrompidos no espaço da emenda, se encontram no meio dele
    (a peça é uma só: o título pede 1X e a cota total passa por cima); a emenda fica anotada."""
    meio = (s_a + s_b) / 2.0
    ligados = 0
    for m in el.membros:
        if m.papel != "banzo" or abs(m.h1 - m.h0) >= 30.0:
            continue
        for k in ("s0", "s1"):
            v = getattr(m, k)
            if s_a - 80.0 <= v <= s_b + 80.0:
                setattr(m, k, meio)
                ligados += 1
    el.avisos.append("%s: desenhada em duas partes (%.2f m + %.2f m) com %d mm entre elas — a mesma peça, com emenda "
                     "dos banzos aos %.2f m; o detalhe da emenda é a conferir." % (
                         _bonito(el.nome), s_a / 1000.0, (el.comprimento - s_b) / 1000.0, round(s_b - s_a), meio / 1000.0))
    return ligados


def _partes_da_elevacao(el: "Elevacao", dividir: bool) -> List[Tuple[str, List["Membro"]]]:
    """A elevação que o projeto confirma como duas peças — a viga de transição embaixo e a tesoura
    em cima dela (TRANSIÇÕES 2 e 5 do Posto CB): o que fica abaixo do banzo reto do meio é a viga,
    o que fica acima é a tesoura; a barra que atravessa é cortada nele (onde a tesoura apoia).
    Sem a confirmação, ou sem esse desenho (banzos retos embaixo e no meio, inclinados acima),
    uma peça só."""
    if not dividir:
        return [("", el.membros)]
    L = el.comprimento
    ban = [m for m in el.membros if m.papel == "banzo"]
    retos = sorted({round((m.h0 + m.h1) / 2) for m in ban if abs(m.s1 - m.s0) >= 0.3 * L and abs(m.h1 - m.h0) <= 30.0})
    incl = [m for m in ban if abs(m.h1 - m.h0) > 30.0 and abs(m.s1 - m.s0) >= 500.0]
    if len(retos) < 2 or not incl:
        return [("", el.membros)]
    base_incl = min(min(m.h0, m.h1) for m in incl)
    meio = [h for h in retos if retos[0] + 250.0 < h < base_incl + 100.0]
    if not meio:
        return [("", el.membros)]
    hm = max(meio)
    baixo: List[Membro] = []
    cima: List[Membro] = []
    for m in el.membros:
        lo, hi = min(m.h0, m.h1), max(m.h0, m.h1)
        if hi <= hm + 150.0:
            baixo.append(m)
        elif lo >= hm - 150.0:
            cima.append(m)
        else:
            t = (hm - m.h0) / (m.h1 - m.h0)
            sm = m.s0 + (m.s1 - m.s0) * t
            a_, b_ = Membro(m.s0, m.h0, sm, hm, m.papel), Membro(sm, hm, m.s1, m.h1, m.papel)
            (baixo if m.h0 < hm else cima).append(a_)
            (cima if m.h0 < hm else baixo).append(b_)
    el.avisos.append("%s: montada em duas peças — a viga de transição (até %.2f m) e a tesoura em cima dela."
                     % (_bonito(el.nome), hm / 1000.0))
    # a tesoura de cima é o frontão acima do telhado ("REVESTIR TRANSIÇÃO 2/3 COM TELHA OU RUFO" no
    # corte BB do Posto CB): a telha passa reta embaixo dele, e a terça senta na viga de transição
    el.topo_telhado = hm
    return [("", baixo), (" (tesoura de cima)", cima)]


def _tirar_vista_de_fundo(el: "Elevacao") -> int:
    """A elevação que desenha junto o que fica atrás da treliça (as tesouras paralelas vistas ao
    fundo, com o caimento do telhado) e as chapinhas dos nós: fica só a treliça — os banzos de
    baixo e de cima e a alma que liga um ao outro. Só age quando o desenho mostra isso (várias
    linhas inclinadas entre os banzos e muitas chapinhas): a treliça de altura variável ou com
    travessa no meio fica como está. Devolve quantas linhas saíram (e avisa)."""
    L = el.comprimento
    ban = [m for m in el.membros if m.papel == "banzo"]
    retos = [m for m in ban if abs(m.s1 - m.s0) >= 0.3 * L and abs(m.h1 - m.h0) <= 30.0]
    if len(retos) < 2:
        return 0
    hs = [(m.h0 + m.h1) / 2 for m in retos]
    baixo, cima = min(hs), max(hs)

    def entre(h):
        return baixo + 250.0 < h < cima - 250.0
    inclinados = [m for m in ban if abs(m.h1 - m.h0) > 30.0 and abs(m.s1 - m.s0) >= 500.0 and entre(m.h0) and entre(m.h1)]
    curtos = [m for m in ban if abs(m.s1 - m.s0) < 500.0]
    if len(inclinados) < 3 or len(curtos) < 10:
        return 0
    lin_b = max(h for h in hs if h <= baixo + 250.0)
    lin_c = min(h for h in hs if h >= cima - 250.0)

    def no_banzo(h):
        return baixo - 150.0 <= h <= lin_b + 150.0 or lin_c - 150.0 <= h <= cima + 150.0
    fora = set()
    for m in el.membros:
        if m.papel == "banzo":
            if abs(m.s1 - m.s0) < 500.0 or (entre(m.h0) and entre(m.h1)):
                fora.add(id(m))
        elif not (no_banzo(m.h0) and no_banzo(m.h1)):
            fora.add(id(m))
    if not fora:
        return 0
    el.fundo = [m for m in el.membros if id(m) in fora]
    el.membros = [m for m in el.membros if id(m) not in fora]
    el.avisos.append("%s: tiradas %d linhas que não são desta treliça (as tesouras desenhadas ao fundo e as "
                     "chapinhas dos nós); ficaram os dois banzos e a alma entre eles." % (_bonito(el.nome), len(fora)))
    return len(fora)


# =====================================================================================
# Planta: peças nomeadas
# =====================================================================================

@dataclass
class Trecho:
    """uma peça da planta: o caminho (já cortado no comprimento dela) e o nome"""
    caminho: Caminho
    nome: str
    familia: str
    elevacao: Optional[Elevacao] = None
    invertida: bool = False
    perfil: Optional[dict] = None
    sentido_por: str = "costume do desenho"
    rotulo_id: Optional[str] = None
    ajuste: float = 0.0             # mm que a elevação anda na peça para os nós caírem nas terças
    # a treliça deitada (a planta a desenha vista de cima): {"n": normal para o outro banzo,
    # "largura": mm entre os banzos, "almas": [(a, b)] como a planta desenha}; o caminho é o
    # primeiro banzo
    deitada: Optional[dict] = None


_RX_ROTULO = re.compile(r"(?i)^\s*(TESOURA|PAINEL|TRANSI[ÇC][ÃA]O|TRELI[ÇC]A|COMP|TES|VM)[\s.\-]*([\w]*)")


def _altura_da_elevacao(el: Elevacao) -> float:
    hs = [h for m in el.membros for h in (m.h0, m.h1)]
    return (max(hs) - min(hs)) if hs else 0.0


def _trelicas_deitadas(segs, textos, elevacoes: Dict[str, "Elevacao"], nome_do, tol: float = 40.0,
                       banzo_min: float = 2500.0):
    """A treliça deitada (passarela, viga de vento): a planta a desenha vista de cima — os dois
    banzos paralelos e, entre eles, os montantes e as diagonais, cada barra encostando nos dois.
    A treliça em pé aparece na planta só como a linha do banzo; com a alma desenhada entre duas
    linhas, ela está deitada. Cada faixa contínua de alma vira uma treliça; o nome é o da
    elevação próxima com a altura igual à largura da faixa e o comprimento dela (±8 %).
    Devolve (trechos, ids dos rótulos usados, faixas (u, n, origem, f1, f2, s0, s1))."""
    def unit(a, b):
        L = math.dist(a, b)
        return ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > 0 else (1.0, 0.0)
    longos = [s for s in segs if math.dist(s[0], s[1]) >= banzo_min]
    if not longos:
        return [], set(), []
    CEL = 2000.0
    grade = collections.defaultdict(set)
    for k, s in enumerate(longos):
        (x0, y0), (x1, y1) = s[0], s[1]
        n = int(math.dist(s[0], s[1]) // (CEL / 2)) + 1
        for j in range(n + 1):
            grade[(int((x0 + (x1 - x0) * j / n) // CEL), int((y0 + (y1 - y0) * j / n) // CEL))].add(k)

    def encosta(p, dr):
        """os banzos (linhas compridas, não paralelas à barra) em que o ponto encosta"""
        cx, cy = int(p[0] // CEL), int(p[1] // CEL)
        cands = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cands |= grade.get((cx + dx, cy + dy), set())
        out = []
        for k in cands:
            a, b = longos[k][0], longos[k][1]
            u = unit(a, b)
            if abs(u[0] * dr[0] + u[1] * dr[1]) > 0.9:
                continue
            L = math.dist(a, b)
            t = ((p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1])
            if -tol <= t <= L + tol and abs(-(p[0] - a[0]) * u[1] + (p[1] - a[1]) * u[0]) < tol:
                out.append(k)
        return out

    degraus = []
    for s in segs:
        L = math.dist(s[0], s[1])
        if not 600.0 <= L <= 3000.0:
            continue
        dr = unit(s[0], s[1])
        par = None
        for i in encosta(s[0], dr):
            for j in encosta(s[1], dr):
                u1, u2 = unit(*longos[i][:2]), unit(*longos[j][:2])
                if i != j and abs(u1[0] * u2[1] - u1[1] * u2[0]) < 0.035:
                    par = u1
                    break
            if par:
                break
        if not par:
            continue
        u = par if (par[0] > 1e-9 or (abs(par[0]) <= 1e-9 and par[1] > 0)) else (-par[0], -par[1])
        degraus.append({"u": u, "ang": math.degrees(math.atan2(u[1], u[0])) % 180.0, "seg": s})
    # as faixas: a mesma direção e as mesmas duas linhas de banzo. A posição de cada barra é
    # medida no mesmo referencial (a direção média do grupo) e a partir de um ponto do grupo:
    # o desenho fica a centenas de metros do zero, e 0,1° de diferença ali vira 70 cm
    grupos: List[List[dict]] = []
    por_ang: List[List[dict]] = []
    for d in sorted(degraus, key=lambda d: d["ang"]):
        if por_ang and d["ang"] - por_ang[-1][-1]["ang"] < 1.0:
            por_ang[-1].append(d)
        else:
            por_ang.append([d])
    for cl in por_ang:
        ux = sum(d["u"][0] for d in cl)
        uy = sum(d["u"][1] for d in cl)
        Lu = math.hypot(ux, uy) or 1.0
        u = (ux / Lu, uy / Lu)
        n = (-u[1], u[0])
        o = cl[0]["seg"][0]
        for d in cl:
            s = d["seg"]
            fa, fb = [(p[0] - o[0]) * n[0] + (p[1] - o[1]) * n[1] for p in s[:2]]
            sa, sb = [(p[0] - o[0]) * u[0] + (p[1] - o[1]) * u[1] for p in s[:2]]
            d.update(u=u, n=n, o=o, f1=min(fa, fb), f2=max(fa, fb), s0=min(sa, sb), s1=max(sa, sb))
        sub: List[List[dict]] = []
        for d in sorted((d for d in cl if d["f2"] - d["f1"] >= 600.0), key=lambda d: d["f1"]):
            for g in sub:
                m1 = sum(x["f1"] for x in g) / len(g)
                m2 = sum(x["f2"] for x in g) / len(g)
                if abs(m1 - d["f1"]) < 150.0 and abs(m2 - d["f2"]) < 150.0:
                    g.append(d)
                    break
            else:
                sub.append([d])
        grupos += sub
    trechos, usados, faixas = [], set(), []
    for g in grupos:
        g.sort(key=lambda d: d["s0"])
        partes = [[g[0]]]
        for d in g[1:]:
            if d["s0"] <= max(x["s1"] for x in partes[-1]) + 150.0:
                partes[-1].append(d)
            else:
                partes.append([d])
        partes = [p for p in partes if len(p) >= 3 and max(x["s1"] for x in p) - p[0]["s0"] >= 1000.0]
        if not partes:
            continue
        u, n, o = g[0]["u"], g[0]["n"], g[0]["o"]
        f1 = sum(d["f1"] for d in g) / len(g)
        f2 = sum(d["f2"] for d in g) / len(g)
        W = f2 - f1
        smin = min(p[0]["s0"] for p in partes)
        smax = max(max(x["s1"] for x in p) for p in partes)
        faixas.append((u, n, o, f1, f2, smin, smax))
        # os nomes perto da faixa, paralelos a ela, cuja elevação tem a altura da largura
        cands = []
        for t in textos:
            if id(t) in usados:
                continue
            nome = nome_do(t["texto"])
            el = elevacoes.get(nome)
            if el is None or nome.startswith("VM"):
                continue
            H = _altura_da_elevacao(el)
            if abs(H - W) > max(0.15 * H, 200.0):
                continue
            p = t["posicao"]
            f = (p[0] - o[0]) * n[0] + (p[1] - o[1]) * n[1]
            s = (p[0] - o[0]) * u[0] + (p[1] - o[1]) * u[1]
            ang_t = (t.get("angulo") or 0.0) % 180.0
            da = min(abs(ang_t - g[0]["ang"]), 180.0 - abs(ang_t - g[0]["ang"]))
            if max(0.0, f1 - f, f - f2) <= 3000.0 and smin - 3000.0 <= s <= smax + 3000.0 and da <= 15.0:
                cands.append((t, nome, el))
        # cada faixa de alma, e as faixas seguidas com um espaço pequeno entre elas (a mesma
        # treliça em duas partes com emenda: a TRELIÇA 1 do Posto CB, 3,12 + 0,25 + 20,80 m)
        combos = []
        for k in range(len(partes)):
            fim = max(x["s1"] for x in partes[k])
            combos.append((k, k))
            for k2 in range(k + 1, len(partes)):
                if partes[k2][0]["s0"] - fim > 600.0:
                    break
                fim = max(fim, max(x["s1"] for x in partes[k2]))
                combos.append((k, k2))
        pares = []
        for ka, kb in combos:
            Lp = max(x["s1"] for q in partes[ka:kb + 1] for x in q) - partes[ka][0]["s0"]
            for t, nome, el in cands:
                err = abs(Lp - el.comprimento) / el.comprimento
                if err <= 0.08:
                    pares.append((err, (ka, kb), id(t), t, nome, el))
        feitas = set()
        for err, (ka, kb), it, t, nome, el in sorted(pares, key=lambda x: x[0]):
            if any(k in feitas for k in range(ka, kb + 1)) or it in usados:
                continue
            feitas.update(range(ka, kb + 1))
            usados.add(it)
            p = [x for q in partes[ka:kb + 1] for x in q]
            s0, s1 = p[0]["s0"], max(x["s1"] for x in p)

            def pt(s, f):
                return (o[0] + u[0] * s + n[0] * f, o[1] + u[1] * s + n[1] * f)
            fontes = frozenset(x["seg"].id for x in p if getattr(x["seg"], "id", None))
            cam = Caminho("reta", a=pt(s0, f1), b=pt(s1, f1), largura=0.0, fontes=fontes)
            trechos.append(Trecho(caminho=cam, nome=nome, familia=_sem_acento(nome.split()[0]), elevacao=el,
                                  sentido_por="deitada: a planta desenha a treliça vista de cima", rotulo_id=t.get("id"),
                                  deitada={"n": n, "largura": W, "almas": [(x["seg"][0], x["seg"][1]) for x in p],
                                           "faixa": (u, n, o, f1, f2, s0, s1), "texto": id(t)}))
    return trechos, usados, faixas


def pecas_da_planta(ents, caixa, elevacoes: Dict[str, Elevacao], avisar=None,
                    apoios: Sequence[Ponto2] = (), deitadas=False) -> Tuple[List[Trecho], dict]:
    """as peças nomeadas da planta estrutural, cortadas no comprimento de cada elevação.
    `apoios`: os pilares (x, y) — a treliça que passa por cima de um pode terminar ali.
    `deitadas`: a faixa em que a planta desenha a treliça vista de cima vira treliça deitada —
    True para todas, ou a lista dos nomes confirmados ("TRELICA 1"); as outras (e todas, sem o
    parâmetro) só são apontadas para conferir (stats["deitadas_a_conferir"])"""
    from nucleo2d.reconhecer import perfil_do_texto
    regiao = [e for e in ents if _dentro(_pt(e), caixa)]
    segs = _segmentos(regiao)
    retas, _soltas = centros_retos(segs, lmin=300.0, larg=(40.0, 260.0))
    arcos = centros_arcos(regiao)
    # a linha dupla interrompida onde outra peça cruza volta a ser uma linha só antes de
    # emendar os arcos: senão o arco da borda leva junto o pedaço reto de outra peça (a
    # treliça que continua na mesma tangente). As pontas dos pedaços viram nós
    caminhos: List[Caminho] = encadear(juntar_colineares(retas) + arcos)
    pedacos = retas + arcos
    # o nome da peça da borda fica do lado de fora do desenho
    folga = (caixa[0] - 2500, caixa[1] - 2500, caixa[2] + 2500, caixa[3] + 2500)
    textos = [e for e in ents if e["tipo"] == "texto" and _dentro(e["posicao"], folga) and _RX_ROTULO.match(e["texto"])]

    def nome_do(texto):
        m = _RX_ROTULO.match(texto)
        return (_sem_acento(m.group(1)) + " " + m.group(2).upper()).replace("TES ", "TESOURA ")
    # a treliça deitada (a planta desenha a alma entre os dois banzos) fica com o nome dela;
    # as linhas dos banzos não disputam os outros nomes. Pedida só quando o projeto confirma:
    # no Posto CB a faixa ficou a conferir (a mesma TRANSIÇÃO 14 cabe em pé na linha curva
    # ao lado, onde as terças terminam)
    achadas, rot_deitadas, faixas_d = _trelicas_deitadas(segs, textos, elevacoes, nome_do)
    a_conferir = [{"nome": _bonito(t.nome), "comprimento": round(t.caminho.comprimento),
                   "ponto": [round((t.caminho.a[0] + t.caminho.b[0]) / 2), round((t.caminho.a[1] + t.caminho.b[1]) / 2)]}
                  for t in achadas]
    if deitadas is True:
        escolhidas = achadas
    elif deitadas:
        confirmadas = {_sem_acento(str(n)).upper().strip() for n in deitadas}
        escolhidas = [t for t in achadas if _sem_acento(t.nome).upper() in confirmadas]
    else:
        escolhidas = []
    def na_faixa_escolhida(t):
        """a faixa já é de uma treliça deitada confirmada (a TRELIÇA 1 do Posto CB, 24,17 m, é a
        passarela inteira): a outra elevação que também caberia nela não fica a conferir"""
        m_ = ((t.caminho.a[0] + t.caminho.b[0]) / 2, (t.caminho.a[1] + t.caminho.b[1]) / 2)
        for e_ in escolhidas:
            s_, d_ = e_.caminho.projetar(m_)
            if d_ <= float((e_.deitada or {}).get("largura") or 0.0) + 300.0 and -300.0 <= s_ <= e_.caminho.comprimento + 300.0:
                return True
        return False
    a_conferir = [fx for fx, t in zip(a_conferir, achadas) if t not in escolhidas and not na_faixa_escolhida(t)]
    deitadas = escolhidas
    if deitadas:
        rot_deitadas = {d.deitada["texto"] for d in deitadas}
        faixas_d = [d.deitada["faixa"] for d in deitadas]
        textos = [t for t in textos if id(t) not in rot_deitadas]

        def na_faixa(c):
            if c.tipo != "reta":
                return False
            for u, n, o, f1, f2, s0, s1 in faixas_d:
                du = ((c.b[0] - c.a[0]) * u[0] + (c.b[1] - c.a[1]) * u[1]) / (c.comprimento or 1.0)
                if abs(du) < 0.995:
                    continue
                m_ = ((c.a[0] + c.b[0]) / 2, (c.a[1] + c.b[1]) / 2)
                f = (m_[0] - o[0]) * n[0] + (m_[1] - o[1]) * n[1]
                s = (m_[0] - o[0]) * u[0] + (m_[1] - o[1]) * u[1]
                if f1 - 60.0 <= f <= f2 + 60.0 and s0 - 500.0 <= s <= s1 + 500.0:
                    return True
            return False
        caminhos = [c for c in caminhos if not na_faixa(c)]
    # cada rótulo vai para a peça paralela mais perto
    por_caminho: Dict[int, List[Tuple[float, str, dict]]] = collections.defaultdict(list)
    sem_peca = []
    for t in textos:
        p = (t["posicao"][0], t["posicao"][1])
        ang_t = (t.get("angulo") or 0.0) % 180.0
        melhor = None
        for i, c in enumerate(caminhos):
            s, d = c.projetar(p)
            if d > 800:
                continue
            tx, ty = c.tangente(s)
            ang = math.degrees(math.atan2(ty, tx)) % 180.0
            da = min(abs(ang - ang_t), 180.0 - abs(ang - ang_t))
            if da > 15.0 and c.tipo == "reta":
                continue
            nota = d + da * 20.0
            if melhor is None or nota < melhor[0]:
                melhor = (nota, i, s)
        if melhor is None:
            sem_peca.append(t["texto"].strip())
            continue
        # o texto é escrito a partir do começo: o meio do rótulo é o que marca a peça. A
        # altura do texto no arquivo depende da escala de impressão (que o arquivo não diz):
        # o nome fica dentro da peça, então o meio não passa de 35 % do comprimento dela
        comp_txt = len(t["texto"].strip()) * (t.get("altura") or 2.5) * 50.0 * 0.8
        el_t = elevacoes.get(nome_do(t["texto"]))
        meia = min(comp_txt / 2, 0.35 * el_t.comprimento) if el_t is not None else comp_txt / 2
        rad = math.radians(t.get("angulo") or 0.0)
        meio = (p[0] + math.cos(rad) * meia, p[1] + math.sin(rad) * meia)
        s_meio, _d = caminhos[melhor[1]].projetar(meio)
        por_caminho[melhor[1]].append((s_meio, t["texto"].strip(), t))
    # nós: onde uma treliça pode terminar (cruzamentos, pontas encostadas, emendas)
    polis = [_polilinha(c) for c in caminhos]
    nos: Dict[int, List[float]] = {i: _nos_de(c, i, caminhos, polis, pedacos, apoios) for i, c in enumerate(caminhos)}
    trechos: List[Trecho] = []
    stats = {"caminhos": len(caminhos), "rotulos": len(textos), "sem_peca": sem_peca, "sem_rotulo": 0,
             "sem_elevacao": collections.Counter(), "vigas": 0, "deitadas": deitadas,
             "deitadas_a_conferir": a_conferir}

    # a peça comprida tem o nome escrito mais de uma vez. Quando a planta tem mais nomes
    # de uma peça do que o título dela pede ("- 1X"), os nomes repetidos na mesma linha, a
    # menos de um comprimento um do outro, são a mesma peça: viram um só, no meio deles
    sobra = collections.Counter()
    for lst in por_caminho.values():
        for _s, texto, _t in lst:
            sobra[nome_do(texto)] += 1
    for nome_r, n in list(sobra.items()):
        el_r = elevacoes.get(nome_r)
        sobra[nome_r] = n - el_r.qtd if el_r is not None else 0
    for i in list(por_caminho):
        lst = sorted(por_caminho[i], key=lambda r: r[0])
        while True:
            pares = [(lst[k + 1][0] - lst[k][0], k) for k in range(len(lst) - 1)
                     if nome_do(lst[k][1]) == nome_do(lst[k + 1][1]) and sobra[nome_do(lst[k][1])] > 0
                     and elevacoes.get(nome_do(lst[k][1])) is not None
                     and lst[k + 1][0] - lst[k][0] < elevacoes[nome_do(lst[k][1])].comprimento]
            if not pares:
                break
            _d, k = min(pares)
            sobra[nome_do(lst[k][1])] -= 1
            lst[k:k + 2] = [((lst[k][0] + lst[k + 1][0]) / 2, lst[k][1], lst[k][2])]
        por_caminho[i] = lst
    for i, c in enumerate(caminhos):
        rot = sorted(por_caminho.get(i, []), key=lambda r: r[0])
        if not rot:
            stats["sem_rotulo"] += 1
            continue
        L = c.comprimento
        ns = nos[i]
        pedidos = []                # (s do nome, nome, família, elevação, texto)
        faixas_vm = None
        for s_meio, texto, _t in rot:
            m = _RX_ROTULO.match(texto)
            fam = _sem_acento(m.group(1))
            if fam in ("VM",):
                perf = perfil_do_texto(texto)
                if faixas_vm is None:
                    faixas_vm = _faixas_das_vigas(c, rot, pedacos)
                faixa = faixas_vm.get(id(_t))
                if faixa is None:
                    continue            # o mesmo nome escrito de novo na mesma viga
                cv = c.trecho(*faixa) if c.tipo == "reta" else c
                trechos.append(Trecho(caminho=cv, nome=texto, familia="VIGA", perfil=perf, rotulo_id=_t.get("id")))
                stats["vigas"] += 1
                continue
            num = m.group(2).upper()
            if fam == "TES":
                fam = "TESOURA"
            nome = "%s %s" % (fam, num)
            el = elevacoes.get(nome)
            if el is None:
                stats["sem_elevacao"][nome] += 1
                continue
            pedidos.append((s_meio, nome, fam, el, _t))
        if len(pedidos) == 1:
            s_meio, nome, fam, el, _t = pedidos[0]
            Le = el.comprimento
            if c.tipo == "reta" and L < 0.92 * Le:
                # a linha da treliça foi interrompida onde outra peça cruza: segue pelos
                # trechos na mesma linha até ter o comprimento da elevação
                c2 = _estender_na_linha(c, caminhos, Le)
                if c2 is not c:
                    s_meio = c2.projetar(c.ponto(s_meio))[0]
                    c, L = c2, c2.comprimento
                    ns = _nos_de(c, i, caminhos, polis, pedacos, apoios)
            if abs(L - Le) <= max(0.08 * Le, 300.0):
                # a linha toda é a peça
                trechos.append(Trecho(caminho=c, nome=nome, familia=fam, elevacao=el, rotulo_id=_t.get("id")))
                continue
            pedidos = [(s_meio, nome, fam, el, _t)]
        faixas = _escolher_trechos(L, ns, [(p[0], p[3].comprimento) for p in pedidos]) if pedidos else []
        for (s_meio, nome, fam, el, _t), (s0, s1) in zip(pedidos, faixas):
            trechos.append(Trecho(caminho=c.trecho(s0, s1), nome=nome, familia=fam, elevacao=el, rotulo_id=_t.get("id")))
    return trechos, stats


def _viga_ate_o_pilar(pts: Sequence[Ponto2], pilares: Sequence[Tuple[float, float, float]], frente: float = 500.0,
                      lado: float = 250.0, folga: float = 30.0) -> List[Ponto2]:
    """A ponta da viga que para antes de um pilar na linha dela vai até a face do pilar.
    `pilares`: (x, y, meia) — `meia` é a metade da seção do pilar. Vale para o pilar até `frente`
    mm além da ponta e a no máximo `lado` mm da linha da viga; a viga que já chega na face (ou
    passa dela) fica como está, e o pilar mais de lado que isso é do desenho, para conferir."""
    a, b = pts
    L = math.dist(a, b)
    if L < 1.0:
        return [a, b]
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    novos = [a, b]
    for k, (p, sinal) in enumerate(((a, -1.0), (b, 1.0))):
        falta = None
        encosta = False
        for qx, qy, meia in pilares:
            dx, dy = qx - p[0], qy - p[1]
            adiante = (dx * ux + dy * uy) * sinal          # positivo: o pilar está além da ponta
            if abs(-dx * uy + dy * ux) > lado:
                continue
            if -meia - folga <= adiante <= meia + folga:
                encosta = True                             # a ponta já está no pilar
            elif meia + folga < adiante <= frente and (falta is None or adiante - meia < falta):
                falta = adiante - meia
        if falta is not None and not encosta:
            novos[k] = (p[0] + ux * sinal * falta, p[1] + uy * sinal * falta)
    return novos


def _viga_repetida(pts: Sequence[Ponto2], z: float, perfil: str, feitas: Sequence[tuple], tol: float = 150.0) -> bool:
    """a viga já montada: mesmo perfil, mesmo nível, na mesma linha e cobrindo 90 % dela"""
    a, b = pts
    L = math.dist(a, b)
    if L < 1.0:
        return False
    for (p, q), z2, pf2 in feitas:
        if pf2 != perfil or abs(z2 - z) > 50.0:
            continue
        Lq = math.dist(p, q)
        if Lq < 1.0:
            continue
        ux, uy = (q[0] - p[0]) / Lq, (q[1] - p[1]) / Lq
        lado = [abs(-(r[0] - p[0]) * uy + (r[1] - p[1]) * ux) for r in (a, b)]
        if max(lado) > tol:
            continue
        sa, sb = sorted(((r[0] - p[0]) * ux + (r[1] - p[1]) * uy) for r in (a, b))
        if min(sb, Lq) - max(sa, 0.0) >= 0.9 * L:
            return True
    return False


def _faixas_das_vigas(c: Caminho, rot, pedacos) -> Dict[int, Tuple[float, float]]:
    """o trecho de cada viga VM na linha `c`: o pedaço onde está o nome mais os pedaços da
    mesma linha sem nome nenhum (a linha dupla da viga é interrompida no pilar e o nome vem
    escrito uma vez só), cada um para o nome mais perto. O mesmo nome escrito duas vezes
    na mesma viga dá uma viga só. {id do texto: (s0, s1)}"""
    if c.tipo != "reta":
        return {id(t): (0.0, c.comprimento) for _s, _x, t in rot}
    faixas = []
    for d in pedacos:
        if d.tipo != "reta" or c.projetar(d.ponto(d.comprimento / 2))[1] >= 60.0:
            continue
        (ux, uy), _L = _unit(c.a, c.b)
        (vx, vy), _M = _unit(d.a, d.b)
        if abs(ux * vy - uy * vx) > 0.02:
            continue
        s0, s1 = sorted((c.projetar(d.a)[0], c.projetar(d.b)[0]))
        faixas.append([s0, s1, None])
    if not faixas:
        return {id(t): (0.0, c.comprimento) for _s, _x, t in rot}
    faixas.sort()
    for k, (s_m, _x, t) in enumerate(rot):
        f = min(faixas, key=lambda f: 0.0 if f[0] - 50 <= s_m <= f[1] + 50 else min(abs(s_m - f[0]), abs(s_m - f[1])))
        if f[2] is None:
            f[2] = k
    for f in faixas:
        if f[2] is None:
            meio = (f[0] + f[1]) / 2
            f[2] = min(range(len(rot)), key=lambda k: abs(rot[k][0] - meio))
    out: Dict[int, Tuple[float, float]] = {}
    vistos = set()
    for k, (s_m, texto, t) in enumerate(rot):
        minhas = [f for f in faixas if f[2] == k]
        if not minhas:
            # o nome caiu num pedaço de outro nome igual: a mesma viga
            dono = min(faixas, key=lambda f: 0.0 if f[0] - 50 <= s_m <= f[1] + 50 else min(abs(s_m - f[0]), abs(s_m - f[1])))
            if rot[dono[2]][1] == texto:
                continue
            minhas = [dono]
        faixa = (min(f[0] for f in minhas), max(f[1] for f in minhas))
        chave = (texto, round(faixa[0] / 50), round(faixa[1] / 50))
        if chave in vistos:
            continue
        vistos.add(chave)
        out[id(t)] = faixa
    return out


def _polilinha(c: Caminho, passo: float = 150.0) -> List[Ponto2]:
    if c.tipo == "reta":
        return [c.a, c.b]
    L = c.comprimento
    n = max(2, int(L / passo) + 1)
    return [c.ponto(L * k / n) for k in range(n + 1)]


def _caixa_pts(pts, folga: float = 0.0):
    return (min(p[0] for p in pts) - folga, min(p[1] for p in pts) - folga,
            max(p[0] for p in pts) + folga, max(p[1] for p in pts) + folga)


def _cruzam(c1, c2) -> bool:
    return not (c1[2] < c2[0] or c2[2] < c1[0] or c1[3] < c2[1] or c2[3] < c1[1])


def _cruzamento(a, b, p, q) -> Optional[Ponto2]:
    """ponto onde os segmentos a–b e p–q se cruzam (None se não se cruzam)"""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = q[0] - p[0], q[1] - p[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-9:
        return None
    wx, wy = p[0] - a[0], p[1] - a[1]
    t = (wx * sy - wy * sx) / den
    u = (wx * ry - wy * rx) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (a[0] + rx * t, a[1] + ry * t)
    return None


def _nos_de(c: Caminho, i: int, caminhos: List[Caminho], polis, pedacos, apoios: Sequence[Ponto2] = (),
            tol: float = 200.0) -> List[float]:
    """onde a peça `c` pode terminar, medido ao longo dela: as pontas dela, os cruzamentos
    com as outras linhas, as pontas das outras encostadas nela (a treliça que apoia do
    lado) e as pontas dos pedaços que a formam (a emenda do arco com a reta, a
    interrupção da linha dupla) e os pilares embaixo dela"""
    L = c.comprimento
    pc = _polilinha(c)
    cx = _caixa_pts(pc, tol)
    ns = [0.0, L]
    for j, d in enumerate(caminhos):
        if j == i or d is c:
            continue
        pd = polis[j]
        if not _cruzam(cx, _caixa_pts(pd)):
            continue
        for q in (pd[0], pd[-1]):
            if _dentro(q, cx):
                s, dist = c.projetar(q)
                if dist < tol:
                    ns.append(s)
        for a, b in zip(pc, pc[1:]):
            ca = _caixa_pts((a, b))
            for p, q in zip(pd, pd[1:]):
                if not _cruzam(ca, _caixa_pts((p, q))):
                    continue
                x = _cruzamento(a, b, p, q)
                if x is not None:
                    ns.append(c.projetar(x)[0])
    for d in pedacos:
        for q in (d.ponto(0.0), d.ponto(d.comprimento)):
            if _dentro(q, cx):
                s, dist = c.projetar(q)
                if dist < 60.0:
                    ns.append(s)
    for q in apoios:
        if _dentro(q, cx):
            s, dist = c.projetar(q)
            if dist < 400.0:
                ns.append(s)
    return sorted(set(round(min(max(s, 0.0), L), 0) for s in ns))


def _centrado(s_meio: float, Le: float, ns: List[float], L: float) -> Tuple[float, float]:
    """o trecho do comprimento da elevação centrado no nome, com as pontas encostadas no
    nó mais perto quando há um perto"""
    s0, s1 = s_meio - Le / 2, s_meio + Le / 2
    lim = max(600.0, 0.12 * Le)
    n0 = min(ns, key=lambda n: abs(n - s0))
    n1 = min(ns, key=lambda n: abs(n - s1))
    s0 = n0 if abs(n0 - s0) < lim else s0
    s1 = n1 if abs(n1 - s1) < lim else s1
    s0, s1 = max(0.0, s0), min(L, s1)
    if s1 - s0 < 0.5 * Le:
        s0, s1 = max(0.0, s_meio - Le / 2), min(L, s_meio + Le / 2)
    return s0, s1


def _escolher_trechos(L: float, ns: List[float], pedidos: List[Tuple[float, float]],
                      folga: float = 300.0) -> List[Tuple[float, float]]:
    """o trecho de cada nome na linha: entre dois nós, com o nome dentro e o comprimento da
    elevação (o projetista escreve o nome em qualquer ponto da peça, muitas vezes perto de
    uma ponta). Os nomes vizinhos não disputam o mesmo trecho. Sem par de nós que sirva,
    o trecho centrado no nome (`_centrado`), com custo alto.
    `pedidos`: [(s do nome, comprimento da elevação)] em ordem de s."""
    cands = []
    for s_meio, Le in pedidos:
        tol = max(0.08 * Le, 300.0)
        lst = []
        for ia, a in enumerate(ns):
            if a > s_meio + folga:
                break
            for b in ns[ia + 1:]:
                if b - a > Le + tol:
                    break
                if b < s_meio - folga:
                    continue
                d = abs(b - a - Le)
                if d <= tol:
                    lst.append((d / Le + 0.05 * abs((a + b) / 2 - s_meio) / Le, a, b))
        # uma ponta num nó e a outra onde o comprimento da elevação acabar: as duas peças
        # que dividem um vão sem nó entre elas (painel 4 e painel 5 da mesma borda)
        for n in ns:
            for a, b in ((n, n + Le), (n - Le, n)):
                if 0.0 <= a and b <= L and a - folga <= s_meio <= b + folga:
                    lst.append((0.15 + 0.05 * abs((a + b) / 2 - s_meio) / Le, a, b))
        lst.sort()
        lst = lst[:12]
        a, b = _centrado(s_meio, Le, ns, L)
        lst.append((0.5 + abs(b - a - Le) / Le, a, b))
        cands.append(lst)
    # o menor custo somado sem que dois trechos vizinhos se sobreponham
    melhor = [(c_, None) for c_, _a, _b in cands[0]]
    passos = [melhor]
    for k in range(1, len(cands)):
        atual = []
        for c_, a, _b in cands[k]:
            opcoes = []
            for j, (custo_j, _v) in enumerate(passos[-1]):
                fim_j = cands[k - 1][j][2]
                multa = 0.0 if fim_j <= a + folga else 1.0
                opcoes.append((custo_j + c_ + multa, j))
            atual.append(min(opcoes))
        passos.append(atual)
    j = min(range(len(passos[-1])), key=lambda j: passos[-1][j][0])
    escolha = []
    for k in range(len(cands) - 1, -1, -1):
        escolha.append(j)
        j = passos[k][j][1]
    escolha.reverse()
    return [(cands[k][j][1], cands[k][j][2]) for k, j in enumerate(escolha)]


# =====================================================================================
# Orientação: qual ponta da elevação vai em qual ponta da planta
# =====================================================================================

def _altura_no_ponto(t: Trecho, p: Ponto2, tol: float = 350.0) -> Optional[float]:
    """altura do banzo superior da treliça `t` no ponto da planta, ou None se ela não
    passa ali"""
    el = t.elevacao
    if el is None:
        return None
    s, d = t.caminho.projetar(p)
    if d > tol:
        return None
    se = _s_na_elevacao(t, s)
    se = min(max(se, 60.0), el.comprimento - 60.0)
    h = el.topo(se)
    # na elevação em duas peças, o telhado é o topo da viga de transição, não o do frontão em cima
    corte = getattr(el, "topo_telhado", None)
    return h if corte is None or h is None else min(h, corte)


def _folga_da_elevacao(t: Trecho) -> float:
    """a elevação entra na planta sem esticar (os nós ficam no passo dela, onde a terça
    apoia), centrada no vão: a diferença de comprimento fica meio a meio nas pontas"""
    L, Le = t.caminho.comprimento, t.elevacao.comprimento
    return ((L - Le) / 2.0 if Le and 0.9 < L / Le < 1.1 else 0.0) + t.ajuste


def _s_na_planta(t: Trecho, s_el: float) -> float:
    """ponto da elevação (s a partir da ponta esquerda dela) → s ao longo da peça na
    planta. As pontas da elevação vão às pontas da peça (a barra da ponta absorve a folga)"""
    L, Le = t.caminho.comprimento, t.elevacao.comprimento
    if s_el <= 1.0:
        sp = 0.0
    elif s_el >= Le - 1.0:
        sp = L
    else:
        sp = s_el + _folga_da_elevacao(t)
    sp = min(max(sp, 0.0), L)
    return L - sp if t.invertida else sp


def _s_na_elevacao(t: Trecho, s: float) -> float:
    L = t.caminho.comprimento
    sp = L - s if t.invertida else s
    return sp - _folga_da_elevacao(t)


def _votos_das_marcas(t: Trecho, linhas_terca) -> Optional[Tuple[int, int]]:
    """quantas linhas de terça caem sobre as marcas "ST" da elevação, no sentido direto e
    no invertido (o texto da marca fica sempre à mesma distância do apoio: essa distância
    é achada por votação)"""
    el = t.elevacao
    if el is None or len(el.marcas_terca) < 2 or t.caminho.tipo != "reta":
        return None
    a, b = t.caminho.a, t.caminho.b
    (ux, uy), L = _unit(a, b)
    cruz = []
    for p, q in linhas_terca:
        (vx, vy), M = _unit(p, q)
        den = ux * vy - uy * vx
        if abs(den) < 0.2:
            continue
        wx, wy = p[0] - a[0], p[1] - a[1]
        s = (wx * vy - wy * vx) / den
        r = (wx * uy - wy * ux) / den
        if -50 <= s <= L + 50 and -50 <= r <= M + 50:
            cruz.append(s)
    if len(cruz) < 2:
        return None
    folga = (L - el.comprimento) / 2.0 if el.comprimento and 0.9 < L / el.comprimento < 1.1 else 0.0
    out = []
    for inv in (False, True):
        ss = [((L - s) if inv else s) - folga for s in cruz]
        votos = collections.Counter(int(round((m - s) / 50.0)) for s in ss for m in el.marcas_terca if abs(m - s) < 700)
        if not votos:
            out.append((0, None))
            continue
        b0 = max(votos, key=lambda v: votos[v] + votos.get(v - 1, 0) + votos.get(v + 1, 0)) * 50.0
        out.append((sum(1 for s in ss if any(abs(m - s - b0) < 90 for m in el.marcas_terca)), b0))
    return out[0], out[1]


def _nos_do_banzo(el: Elevacao) -> List[float]:
    """s dos nós do banzo de cima da elevação: onde chega um montante ou uma diagonal"""
    ns = set()
    for m in el.membros:
        if m.papel not in ("montante", "diagonal"):
            continue
        for s_, h_ in ((m.s0, m.h0), (m.s1, m.h1)):
            topo = el.topo(s_)
            if topo is not None and abs(h_ - topo) < 150.0:
                ns.add(round(s_))
    return sorted(ns)


def ajustar_aos_nos(trechos: List[Trecho], linhas_terca, familias=("TESOURA", "COMP", "TRELICA")) -> int:
    """a terça apoia no nó da treliça (as marcas "ST" da elevação caem nos nós). A peça na
    planta costuma ter um pouco mais ou menos que a elevação (a treliça termina na face do
    apoio): em vez de centrar, a elevação anda até os nós caírem nas linhas das terças — a
    mediana dos desencontros, quando eles concordam entre si e não passam de 300 mm.
    Devolve quantas treliças andaram."""
    n = 0
    for t in trechos:
        if t.elevacao is None or t.familia not in familias or t.caminho.tipo != "reta":
            continue
        nos = _nos_do_banzo(t.elevacao)
        if len(nos) < 2:
            continue
        a, b = t.caminho.a, t.caminho.b
        (ux, uy), L = _unit(a, b)
        deltas = []
        for p, q in linhas_terca:
            (vx, vy), M = _unit(p, q)
            den = ux * vy - uy * vx
            if abs(den) < 0.2:
                continue
            wx, wy = p[0] - a[0], p[1] - a[1]
            s = (wx * vy - wy * vx) / den
            r = (wx * uy - wy * ux) / den
            if not (0.0 <= s <= L and -50 <= r <= M + 50):
                continue
            se = _s_na_elevacao(t, s)
            nx = min(nos, key=lambda x: abs(x - se))
            if abs(se - nx) < 400.0:
                deltas.append(se - nx)
        if len(deltas) < 2:
            continue
        deltas.sort()
        med = deltas[len(deltas) // 2]
        concordam = sum(1 for d in deltas if abs(d - med) <= 60.0)
        if 30.0 < abs(med) <= 300.0 and concordam >= 0.6 * len(deltas):
            # andar a elevação no sentido da planta: invertida, o s da elevação cresce ao contrário
            t.ajuste += med
            n += 1
    return n


def orientar(trechos: List[Trecho], linhas_terca=None,
             familias_de_apoio=("TESOURA", "TRANSICAO", "COMP", "TRELICA", "PAINEL")) -> dict:
    """escolhe o sentido de cada treliça. Primeiro pelas marcas "ST" da elevação: no
    sentido certo elas caem onde as linhas de terça da planta cruzam a treliça. Sem
    marcas, pelo encontro dos banzos superiores: onde duas treliças se tocam, os dois
    ficam na mesma altura. Sem nada que decida, a ponta esquerda da elevação vai para o
    lado de menor x (ou de menor y) — o costume do desenho."""
    ts = [t for t in trechos if t.elevacao is not None and t.familia in familias_de_apoio]
    decididas = set()
    pelas_marcas = 0
    votos = {}
    for t in ts:
        a, b = t.caminho.ponto(0.0), t.caminho.ponto(t.caminho.comprimento)
        t.invertida = (b[0] < a[0] - 1.0) or (abs(b[0] - a[0]) <= 1.0 and b[1] < a[1])
        v = _votos_das_marcas(t, linhas_terca or [])
        if v:
            votos[id(t)] = v
    # a distância do texto "ST" ao apoio é a mesma no desenho todo: é a que mais se repete
    # entre as treliças (no sentido errado ela muda de uma treliça para outra)
    hist = collections.Counter()
    for (n0, b0), (n1, b1) in votos.values():
        for n, b_ in ((n0, b0), (n1, b1)):
            if b_ is not None and n >= 2:
                hist[int(round(b_ / 50.0))] += n
    if hist:
        moda = max(hist, key=lambda v: hist[v] + hist.get(v - 1, 0) + hist.get(v + 1, 0)) * 50.0
        for t in ts:
            v = votos.get(id(t))
            if not v:
                continue
            bons = [(abs(b_ - moda), n, inv) for inv, (n, b_) in enumerate(v)
                    if b_ is not None and n >= 2 and abs(b_ - moda) <= 150.0]
            escolha = None
            if len(bons) == 1:
                escolha = bons[0][2]
            elif len(bons) == 2:
                (d0, n0, i0), (d1, n1, i1) = bons
                if abs(d0 - d1) >= 60.0:
                    escolha = i0 if d0 < d1 else i1
                elif n0 != n1:
                    escolha = i0 if n0 > n1 else i1
            if escolha is not None:
                t.invertida = bool(escolha)
                t.sentido_por = "marcas ST"
                decididas.add(id(t))
                pelas_marcas += 1
    # a peça separada na emenda (TRANSIÇÃO 2 | TRANSIÇÃO 3): a ponta da emenda fica onde a outra
    # treliça passa (a TRANSIÇÃO 1, contínua na planta)
    for t in ts:
        el = t.elevacao
        if id(t) in decididas or not el.emenda or t.caminho.tipo != "reta":
            continue
        pontas = [t.caminho.ponto(0.0), t.caminho.ponto(t.caminho.comprimento)]
        passa = [any(u is not t and u.caminho.tipo == "reta" and _passa_por(u, q) for u in ts) for q in pontas]
        if passa[0] != passa[1]:
            ponta_emenda = 0 if passa[0] else 1             # 0: começo do caminho; 1: fim
            # sem inverter, s = 0 da elevação vai para o começo do caminho
            t.invertida = (ponta_emenda == 1) if el.emenda == "inicio" else (ponta_emenda == 0)
            t.sentido_por = "emenda na treliça que passa"
            decididas.add(id(t))
    # o cruzamento na emenda: onde outra treliça atravessa a linha desta na planta (a planta a
    # interrompe ali), a elevação tem a junta dos banzos (a emenda de 250 mm na cumeeira das
    # TRANSIÇÕES 2 e 5 do Posto CB, onde passa a TRANSIÇÃO 1). Só um sentido põe a junta no
    # cruzamento: esse vale antes do encontro dos banzos (que as inverteu)
    pelo_cruzamento = 0
    for t in ts:
        if id(t) in decididas or t.caminho.tipo != "reta":
            continue
        juntas = _juntas_dos_banzos(t.elevacao)
        cruz = _cruzamentos(t, ts)
        if not juntas or not cruz:
            continue
        L, Le = t.caminho.comprimento, t.elevacao.comprimento
        folga = (L - Le) / 2.0 if Le and 0.9 < L / Le < 1.1 else 0.0
        acertos = []
        for inv in (False, True):
            n = 0
            for s_c in cruz:
                s_e = (L - s_c if inv else s_c) - folga
                if any(abs(s_e - j) <= 300.0 for j in juntas):
                    n += 1
            acertos.append(n)
        if acertos[0] != acertos[1] and max(acertos) > 0 and min(acertos) == 0:
            t.invertida = acertos[1] > acertos[0]
            t.sentido_por = "cruzamento na emenda"
            decididas.add(id(t))
            pelo_cruzamento += 1
    # os painéis da borda são mais altos que a cobertura: não entram na regra das alturas
    ts_alt = [t for t in ts if t.familia != "PAINEL"]
    pontas = {id(t): (t.caminho.ponto(0.0), t.caminho.ponto(t.caminho.comprimento)) for t in ts_alt}
    vizinhos: Dict[int, List[Tuple[Ponto2, Trecho]]] = collections.defaultdict(list)
    for t in ts_alt:
        for p in pontas[id(t)]:
            for u in ts_alt:
                if u is t:
                    continue
                _s, d = u.caminho.projetar(p)
                if d < 350.0:
                    vizinhos[id(t)].append((p, u))
        for u in ts_alt:
            if u is t:
                continue
            for q in pontas[id(u)]:
                _s, d = t.caminho.projetar(q)
                if d < 350.0:
                    vizinhos[id(t)].append((q, u))

    def custo(t: Trecho) -> float:
        c = 0.0
        for p, u in vizinhos[id(t)]:
            ht, hu = _altura_no_ponto(t, p), _altura_no_ponto(u, p)
            if ht is not None and hu is not None:
                c += min(abs(ht - hu), 600.0)
        return c
    trocas = 0
    for _volta in range(8):
        mudou = False
        for t in ts_alt:
            if not vizinhos[id(t)] or id(t) in decididas:
                continue
            c0 = custo(t)
            t.invertida = not t.invertida
            c1 = custo(t)
            if c1 + 5.0 < c0:
                mudou = True
                trocas += 1
                t.sentido_por = "encontro dos banzos"
            else:
                t.invertida = not t.invertida
        if not mudou:
            break
    # as marcas ST erram na treliça curta (poucas marcas, quase simétricas): a decidida por elas
    # que fica com o banzo de cima desencontrado das vizinhas (> 150 mm em cada encontro) e,
    # invertida, se encontra com elas (< 50 mm), vira — a TESOURA 20 do Posto CB começava baixa
    # na cumeeira, colada na TESOURA 18 que chega alta ali
    # só as vizinhas na mesma linha (a continuação do banzo); a que cruza na ponta (a transição
    # que passa na cumeeira) é outra estrutura, de outra altura
    def na_linha(t, u):
        if t.caminho.tipo != "reta" or u.caminho.tipo != "reta":
            return False
        (tx, ty), _ = _unit(t.caminho.a, t.caminho.b)
        (ux_, uy_), _ = _unit(u.caminho.a, u.caminho.b)
        return abs(tx * uy_ - ty * ux_) < 0.1

    def custo_linha(t, viz) -> float:
        return sum(min(abs(ht - hu), 600.0) for p, u in viz
                   for ht, hu in [(_altura_no_ponto(t, p), _altura_no_ponto(u, p))] if ht is not None and hu is not None)
    contra_marcas = []
    for t in ts_alt:
        viz = [(p, u) for p, u in vizinhos[id(t)] if na_linha(t, u)]
        n_v = len(viz)
        if not n_v or t.sentido_por != "marcas ST":
            continue
        c0 = custo_linha(t, viz)
        t.invertida = not t.invertida
        c1 = custo_linha(t, viz)
        if c0 / n_v > 150.0 and c1 / n_v < 50.0:
            t.sentido_por = "encontro dos banzos (contra as marcas ST)"
            contra_marcas.append((_bonito(t.nome), round(c0 / n_v), t.caminho.ponto(t.caminho.comprimento / 2.0)))
        else:
            t.invertida = not t.invertida
    resto = [custo(t) / max(1, len(vizinhos[id(t)])) for t in ts_alt if vizinhos[id(t)]]
    return {"trelicas": len(ts), "pelas_marcas": pelas_marcas, "pelo_cruzamento": pelo_cruzamento, "pelas_alturas": trocas,
            "contra_as_marcas": contra_marcas,
            "desencontro_medio_mm": round(sum(resto) / len(resto), 1) if resto else 0.0}


def camada_da_outra(titulo: str, nivel_o: float, nivel: float, pedida: Optional[str] = None) -> str:
    """a camada das peças de uma outra planta: a pedida; a da caixa d'água com o nível (base e
    cobertura separadas); abaixo do nível da planta estrutural, o mezanino; senão, o nível"""
    if pedida and str(pedida).strip():
        return str(pedida).strip()
    t = _sem_acento(str(titulo or "")).upper()
    nv = ("%.2f" % (nivel_o / 1000.0)).replace(".", ",")
    if re.search(r"\bCX\b|CAIXA", t):
        return "Caixa d'água %s" % nv
    if "MEZANINO" in t or nivel_o < nivel:
        return "Mezanino"
    return "Nível %s" % nv


def _passa_por(u: "Trecho", q) -> bool:
    """a treliça u passa pelo ponto q (a menos de 400 mm da linha dela, longe das pontas dela)"""
    s_, d_ = u.caminho.projetar(q)
    return d_ < 400.0 and 500.0 < s_ < u.caminho.comprimento - 500.0


def _separar_nas_emendas(ents, caixa_p, elevacoes: Dict[str, "Elevacao"], avisos: List[str]) -> Dict[str, str]:
    """A elevação que desenha duas peças juntas, separadas pela emenda: a planta dá um nome a cada
    parte (no Posto CB, a linha em x = 21,37 é a TRANSIÇÃO 2 ao sul da TRANSIÇÃO 1 e a TRANSIÇÃO 3 ao
    norte; a elevação "TRANSIÇÃO 2" tem 16,63 m = 9,61 + 0,25 + 6,76). O nome da planta sem
    elevação, na mesma linha de uma elevação com emenda, cujo pedaço na planta tem o comprimento de
    uma das partes, fica com essa parte; a elevação fica com a outra. A quantidade da nova é o
    número de vezes que o nome aparece na planta. Devolve {nome novo: nome da elevação}."""
    regiao = [e for e in ents if _dentro(_pt(e), caixa_p)]
    textos = [e for e in regiao if e["tipo"] == "texto" and _RX_ROTULO.match(e["texto"])]

    def nome_do(texto):
        m = _RX_ROTULO.match(texto)
        return (_sem_acento(m.group(1)) + " " + m.group(2).upper()).replace("TES ", "TESOURA ")
    faltam = collections.defaultdict(list)
    for t in textos:
        n = nome_do(t["texto"])
        if n not in elevacoes and not n.startswith("VM"):
            faltam[n].append(t)
    if not faltam:
        return {}
    retas, _s = centros_retos(_segmentos(regiao), lmin=1000.0, larg=(40.0, 300.0))

    def peca_do_rotulo(t):
        """a linha dupla da planta ao lado do rótulo, paralela a ele"""
        p = (t["posicao"][0], t["posicao"][1])
        ang = math.radians(t.get("angulo") or 0.0)
        melhor = None
        for c in retas:
            s_, d_ = c.projetar(p)
            if d_ > 900.0 or not (-200.0 <= s_ <= c.comprimento + 200.0):
                continue
            tx, ty = c.tangente(s_)
            if abs(tx * math.cos(ang) + ty * math.sin(ang)) < 0.95:
                continue
            if melhor is None or d_ < melhor[0]:
                melhor = (d_, c)
        return melhor[1] if melhor else None
    novos: Dict[str, str] = {}
    for n, rots in faltam.items():
        for t in rots:
            c = peca_do_rotulo(t)
            if c is None:
                continue
            Lm = c.comprimento
            # as elevações com rótulo na mesma linha (colinear) e com emenda
            for t2 in textos:
                pai = nome_do(t2["texto"])
                el = elevacoes.get(pai)
                if el is None or el.emenda:
                    continue                                   # já separada
                c2 = peca_do_rotulo(t2)
                if c2 is None or c2 is c:
                    continue
                (ux, uy), _L = _unit(c.a, c.b)
                (vx, vy), _L2 = _unit(c2.a, c2.b)
                if abs(ux * vy - uy * vx) > 0.02 or abs(-(c2.a[0] - c.a[0]) * uy + (c2.a[1] - c.a[1]) * ux) > 300.0:
                    continue                                   # não é a mesma linha
                for j in _juntas_dos_banzos(el):
                    # a emenda: o espaço entre as pontas dos banzos em volta da junta
                    esq = max((max(m.s0, m.s1) for m in el.membros if m.papel == "banzo" and max(m.s0, m.s1) <= j + 5.0), default=j)
                    dir_ = min((min(m.s0, m.s1) for m in el.membros if m.papel == "banzo" and min(m.s0, m.s1) >= j - 5.0
                                and abs(m.s1 - m.s0) > 400.0), default=j)
                    partes = [(0.0, esq), (dir_, el.comprimento)]
                    for k, (a_, b_) in enumerate(partes):
                        if abs((b_ - a_) - Lm) <= 80.0 and abs((partes[1 - k][1] - partes[1 - k][0]) - Lm) > 80.0:
                            _dividir(el, partes, k, n, len(rots), elevacoes, avisos)
                            novos[n] = pai
                            break
                    if n in novos:
                        break
                if n in novos:
                    break
            if n in novos:
                break
    return novos


def _dividir(el: "Elevacao", partes, k: int, nome_novo: str, qtd: int, elevacoes, avisos) -> None:
    """a parte k da elevação vira a peça `nome_novo`; a elevação fica com a outra"""
    _limpar_emenda(el, partes[0][1], partes[1][0])

    def pedaco(a_, b_):
        out = []
        for m in el.membros:
            lo, hi = min(m.s0, m.s1), max(m.s0, m.s1)
            if lo >= a_ - 60.0 and hi <= b_ + 60.0:
                out.append(Membro(m.s0 - a_, m.h0, m.s1 - a_, m.h1, m.papel, m.altura_linha, m.caixa))
        return out
    (a_n, b_n), (a_v, b_v) = partes[k], partes[1 - k]
    nova = Elevacao(nome=nome_novo, familia=el.familia, qtd=qtd, comprimento=b_n - a_n, membros=pedaco(a_n, b_n),
                    banzo=el.banzo, alma=el.alma, titulo_em=el.titulo_em, x_esq=el.x_esq + a_n, y_base=el.y_base,
                    caixa=el.caixa, marcas_terca=[m_ - a_n for m_ in el.marcas_terca if a_n - 60.0 <= m_ <= b_n + 60.0],
                    fontes=set(el.fontes))
    nova.emenda = "inicio" if k == 1 else "fim"
    nova.parte_de = el.nome
    fica = pedaco(a_v, b_v)
    el.membros = fica
    el.marcas_terca = [m_ - a_v for m_ in el.marcas_terca if a_v - 60.0 <= m_ <= b_v + 60.0]
    el.x_esq += a_v
    el.comprimento = b_v - a_v
    el.emenda = "fim" if k == 1 else "inicio"
    elevacoes[nome_novo] = nova
    msg = ("%s: a elevação desenha junto a %s (%.2f m, depois da emenda de %d mm); a planta dá esse nome à parte "
           "%s — separadas: %s com %.2f m e %s com %.2f m (%d×, os rótulos da planta)." % (
               _bonito(el.nome), _bonito(nome_novo), (b_n - a_n) / 1000.0, round(abs(partes[1][0] - partes[0][1])),
               "de depois da emenda" if k == 1 else "de antes da emenda", _bonito(el.nome), (b_v - a_v) / 1000.0,
               _bonito(nome_novo), (b_n - a_n) / 1000.0, qtd))
    el.avisos.append(msg)
    nova.avisos.append(msg)


def _limpar_emenda(el: "Elevacao", esq: float, dir_: float) -> int:
    """O vão da emenda entre as duas peças desenhadas juntas (TRANSIÇÃO 2 | 3 do Posto CB): ali a
    elevação desenha a treliça que passa (a TRANSIÇÃO 1) em corte — os lados dela, em pé, que começam
    embaixo e passam da viga, não são alma de nenhuma das duas partes e saem; em cima dela, os U de
    ponta das tesouras (costas com costas), que a leitura tomava por cantoneira, ficam como U; e a
    ponta da viga de cada parte fica com o seu montante em U (a linha dupla da largura da aba), quando
    uma das linhas dele se juntou ao lado da treliça em corte. Devolve quantas linhas saíram."""
    pb = _perfil((el.banzo or {}).get("perfil"))
    bf = float(pb.bf) if pb is not None and pb.bf else 100.0
    banzos = [m for m in el.membros if m.papel == "banzo"]
    retos = [m for m in banzos if abs(m.h1 - m.h0) < 30.0 and abs(m.s1 - m.s0) > 400.0]
    base = min((min(m.h0, m.h1) for m in retos), default=0.0)
    meio = sorted({round((m.h0 + m.h1) / 2.0) for m in retos if (m.h0 + m.h1) / 2.0 > base + 100.0})
    if not meio:
        return 0
    h_viga = float(meio[0])                                   # o banzo de cima da viga de transição

    def em_pe(m):
        return m.papel != "banzo" and abs(m.s1 - m.s0) < 30.0

    def s_de(m):
        return (m.s0 + m.s1) / 2.0
    no_vao = [m for m in el.membros if em_pe(m) and esq - 60.0 <= s_de(m) <= dir_ + 60.0]
    corte = [m for m in no_vao if min(m.h0, m.h1) < h_viga + 100.0 and max(m.h0, m.h1) > h_viga + 300.0]
    if not corte:
        return 0
    h_sec = max(max(m.h0, m.h1) for m in corte)
    for m in no_vao:
        if min(m.h0, m.h1) >= h_sec - 60.0:
            m.altura_linha = bf                               # o U de ponta da tesoura, em cima da que passa
    fora = {id(m) for m in corte}
    # a ponta da viga de cada parte: o U de ponta (a linha dupla da largura da aba)
    novos = []
    fim_esq = max((max(m.s0, m.s1) for m in retos if max(m.s0, m.s1) <= esq + 60.0), default=None)
    ini_dir = min((min(m.s0, m.s1) for m in retos if min(m.s0, m.s1) >= dir_ - 60.0), default=None)
    for ponta, lado in ((fim_esq, -1.0), (ini_dir, 1.0)):
        if ponta is None:
            continue
        s_u = ponta + lado * bf / 2.0
        perto = [m for m in el.membros if em_pe(m) and id(m) not in fora and abs(s_de(m) - s_u) <= 150.0
                 and max(m.h0, m.h1) <= h_viga + 150.0]
        if any(m.altura_linha > 0.0 and _largura_do_perfil(m.altura_linha, (el.banzo or {}).get("perfil")) for m in perto):
            continue
        fora |= {id(m) for m in perto}
        novos.append(Membro(s_u, base, s_u, h_viga, "montante", bf))
    el.membros = [m for m in el.membros if id(m) not in fora] + novos
    el.avisos.append("%s: na emenda, a treliça que passa desenhada em corte (%d linhas) não é alma das peças; os U de "
                     "ponta ficaram como U (%d refeitos na viga)." % (_bonito(el.nome), len(corte), len(novos)))
    return len(corte)


def _juntas_dos_banzos(el: "Elevacao") -> List[float]:
    """s (na elevação) das juntas dos banzos longe das pontas: onde um pedaço de banzo termina e
    outro começa (a emenda) — o meio de cada grupo de pontas a menos de 400 mm uma da outra"""
    L = el.comprimento
    pts = sorted(s for m in el.membros if m.papel == "banzo" and abs(m.s1 - m.s0) > 100.0
                 for s in (m.s0, m.s1) if 400.0 < s < L - 400.0)
    grupos: List[List[float]] = []
    for s in pts:
        if grupos and s - grupos[-1][-1] <= 400.0:
            grupos[-1].append(s)
        else:
            grupos.append([s])
    return [sum(g) / len(g) for g in grupos if len(g) >= 2]


def _cruzamentos(t: "Trecho", outros: List["Trecho"]) -> List[float]:
    """s ao longo de t onde outra treliça reta atravessa t (as duas seguem além do cruzamento)"""
    a, b = t.caminho.a, t.caminho.b
    out = []
    for u in outros:
        if u is t or u.caminho.tipo != "reta":
            continue
        c, d = u.caminho.a, u.caminho.b
        r = (b[0] - a[0], b[1] - a[1])
        q = (d[0] - c[0], d[1] - c[1])
        den = r[0] * q[1] - r[1] * q[0]
        if abs(den) < 1e-9 * max(1.0, math.hypot(*r) * math.hypot(*q)):
            continue
        w = (c[0] - a[0], c[1] - a[1])
        tt = (w[0] * q[1] - w[1] * q[0]) / den
        uu = (w[0] * r[1] - w[1] * r[0]) / den
        Lt, Lu = math.hypot(*r), math.hypot(*q)
        if 500.0 < tt * Lt < Lt - 500.0 and 500.0 < uu * Lu < Lu - 500.0:
            out.append(tt * Lt)
    return out


# =====================================================================================
# Peça calandrada: sólido varrido pelo caminho
# =====================================================================================

def varrer(perfil_nome: str, pontos: Sequence[Tuple[float, float, float]], deitado: bool = True,
           abas_para_baixo: bool = False):
    """sólido do perfil varrido pelos pontos (um anel por ponto, tampas nas pontas): a
    peça calandrada como o TecnoMETAL a exporta. `deitado`: a alma fica horizontal (banzo
    de treliça plana em U); senão, em pé."""
    from nucleo3d.geometria import secao
    from nucleo3d.modelo import Solido
    sec = secao(perfil_nome)
    n = len(pontos)
    if n < 2:
        raise ErroDeDados("varredura com menos de dois pontos.")
    anel_pts = []
    for i, p in enumerate(pontos):
        a = pontos[max(0, i - 1)]
        b = pontos[min(n - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        tx, ty = tx / L, ty / L
        nx, ny = -ty, tx                        # horizontal, perpendicular ao caminho
        anel = []
        for (x, y) in sec:
            if deitado:
                # y da seção (altura do perfil) na horizontal; x (lado das abas) na vertical
                hz = -x if abas_para_baixo else x
                anel.append((p[0] + nx * y, p[1] + ny * y, p[2] + hz))
            else:
                anel.append((p[0] + nx * x, p[1] + ny * x, p[2] + y))
        anel_pts.append(anel)
    k = len(sec)
    vertices = [q for anel in anel_pts for q in anel]
    faces = [list(range(k - 1, -1, -1)), [(n - 1) * k + j for j in range(k)]]
    for i in range(n - 1):
        for j in range(k):
            a0, a1 = i * k + j, i * k + (j + 1) % k
            faces.append([a0, a1, a1 + k, a0 + k])
    return Solido(vertices=vertices, faces=faces)


# =====================================================================================
# Montagem
# =====================================================================================

def _perfil(nome: Optional[str]):
    from nucleo import catalogo
    return catalogo.perfil_de(nome) if nome else None


def _largura_do_perfil(w: float, nome: Optional[str]) -> bool:
    """a largura `w` da linha dupla é a do perfil (a aba ou a altura, 30 % para mais ou menos)?"""
    pa = _perfil(nome)
    if pa is None:
        return True                          # sem o catálogo, fica como sempre foi
    for dim in (pa.bf, pa.d):
        if dim and abs(w - float(dim)) <= 0.3 * float(dim):
            return True
    return False


def _giro_da_alma_em_u(q0, q1, q_meio, tangente, largura: float, nome: Optional[str]) -> float:
    """O giro (graus, o de `geometria.base_local`) da barra de alma em U vista com a `largura` na
    elevação: com a largura da aba, as abas apontam ao longo da treliça, para o meio dela (a alma
    atravessada, fechando a ponta — o montante de ponta da TRANSIÇÃO 1 do Posto CB); com a da
    alma, as abas apontam para fora do plano (a alma no plano da treliça)."""
    from nucleo3d.geometria import base_local
    pa = _perfil(nome)
    tx, ty = tangente
    d = (q1[0] - q0[0], q1[1] - q0[1], q1[2] - q0[2])
    if pa is not None and pa.bf and pa.d and abs(largura - float(pa.bf)) <= abs(largura - float(pa.d)):
        meio = ((q0[0] + q1[0]) / 2.0, (q0[1] + q1[1]) / 2.0)
        sinal = 1.0 if (q_meio[0] - meio[0]) * tx + (q_meio[1] - meio[1]) * ty >= 0.0 else -1.0
        f = (tx * sinal, ty * sinal, 0.0)                 # as abas: para o meio da treliça
    else:
        f = (-ty, tx, 0.0)                                # as abas: para fora do plano
    u, v, w = base_local(d, 0.0)
    fw = f[0] * w[0] + f[1] * w[1] + f[2] * w[2]          # só a parte de f perpendicular ao eixo
    f = (f[0] - fw * w[0], f[1] - fw * w[1], f[2] - fw * w[2])
    return round(math.degrees(math.atan2(f[0] * v[0] + f[1] * v[1] + f[2] * v[2],
                                         f[0] * u[0] + f[1] * u[1] + f[2] * u[2])) % 360.0, 1)


def _lado_do_apoio(banzo: Optional[str], perfil: Optional[str]) -> float:
    """do plano da treliça ao eixo do U de apoio das terças: a meia largura do banzo (a alma do U
    encosta na face dele) mais a distância da alma do U ao centroide"""
    pb, pu = _perfil(banzo), _perfil(perfil)
    meia = float(pb.d) / 2.0 if pb is not None and pb.d else 100.0
    try:
        from nucleo3d.geometria import secao
        xg = -min(q[0] for q in secao(pu)) if pu is not None else 12.0
    except Exception:                        # noqa: BLE001
        xg = 12.0
    return meia + xg


def _giro_abas_para(q0, q1, f) -> float:
    """o giro da barra (o de `geometria.base_local`) que põe as abas do U na direção f"""
    from nucleo3d.geometria import base_local
    d = (q1[0] - q0[0], q1[1] - q0[1], q1[2] - q0[2])
    u, v, w = base_local(d, 0.0)
    fw = f[0] * w[0] + f[1] * w[1] + f[2] * w[2]
    f = (f[0] - fw * w[0], f[1] - fw * w[1], f[2] - fw * w[2])
    return round(math.degrees(math.atan2(f[0] * v[0] + f[1] * v[1] + f[2] * v[2],
                                         f[0] * u[0] + f[1] * u[1] + f[2] * u[2])) % 360.0, 1)


def _meio_caixao(nome: Optional[str]) -> float:
    """do eixo do caixão (a junta das bocas) ao eixo de cada U: a aba menos a distância da alma ao
    centroide (Ue 250×70: 70 − 19 = 51 mm)"""
    pa = _perfil(nome)
    if pa is None or not pa.bf:
        return 35.0
    try:
        from nucleo3d.geometria import secao
        xg = -min(q[0] for q in secao(pa))
    except Exception:                        # noqa: BLE001
        xg = float(pa.bf) / 3.0
    return float(pa.bf) - xg


def _massa(nome: Optional[str]) -> float:
    p = _perfil(nome)
    return float(p.massa) if p is not None and p.massa else 0.0


def _tabela_de_siglas(textos, rx: str) -> Dict[str, dict]:
    """listas do projeto: "TC13-U100X40X2,65 - 56X" → {TC13: {perfil, qtd}},
    "CR1 COMP. 1418 18X" / "CV1 COMP=7150mm - 8X" → {CR1: {comp, qtd}}"""
    from nucleo2d.reconhecer import perfil_do_texto
    out: Dict[str, dict] = {}
    for t in textos:
        s = t["texto"].strip().upper()
        m = re.match(r"^(" + rx + r")\s*[-.]?\s*(.*?)\s*-?\s*(\d+)\s*X\s*$", s)
        if not m:
            continue
        sig = m.group(1).replace(" ", "")
        corpo = m.group(2)
        item = {"qtd": int(m.group(3))}
        c = re.search(r"COMP\.?\s*=?\s*(\d+)", corpo)
        if c:
            item["comp"] = float(c.group(1))
        else:
            r = perfil_do_texto(corpo)
            if r:
                item["perfil"] = r["perfil"]
        out.setdefault(sig, item)
    return out


def _pontas_da_terca(a: Ponto2, b: Ponto2, polis_tr, caixas_tr, tol: float = 300.0, aparar: float = 1500.0,
                     esticar: float = 1000.0) -> Tuple[float, float]:
    """(s do começo, s do fim, cruzamentos) da terça a–b apoiada: onde a linha dela cruza as
    treliças (qualquer uma, também o painel da borda e a transição em que ela encosta).
    Cada cruzamento: (s, meia largura da face em que a terça encosta, família)"""
    (ux, uy), L = _unit(a, b)
    a2 = (a[0] - ux * esticar, a[1] - uy * esticar)
    b2 = (b[0] + ux * esticar, b[1] + uy * esticar)
    cx = _caixa_pts((a2, b2))
    cruz = []                       # (s do cruzamento, meia largura em que a terça encosta)
    for (t, pl), ct in zip(polis_tr, caixas_tr):
        if not _cruzam(cx, ct):
            continue
        # o painel da borda e a transição sobem acima do telhado: a terça encosta na face
        # deles; nas outras treliças ela senta em cima, no eixo
        meia = t.caminho.largura / 2.0 if t.familia in ("PAINEL", "TRANSICAO") else 0.0
        for p, q in zip(pl, pl[1:]):
            x = _cruzamento(a2, b2, p, q)
            if x is not None:
                cruz.append(((x[0] - a[0]) * ux + (x[1] - a[1]) * uy, meia, t.familia))
    if not cruz:
        return 0.0, L, cruz

    def ponta(s_p, sinal):
        # sinal +1: a ponta do começo (o lado de dentro é s crescente); a ponta vai para a
        # face (ou o eixo) do apoio mais perto
        perto = [c for c in cruz if abs(c[0] - s_p) <= tol]
        dentro = [c for c in cruz if 0.0 <= (c[0] - s_p) * sinal <= aparar]
        fora = [c for c in cruz if 0.0 < (s_p - c[0]) * sinal <= esticar]
        esc = (min(perto, key=lambda c: abs(c[0] - s_p)) if perto else
               min(fora, key=lambda c: abs(c[0] - s_p)) if fora else
               min(dentro, key=lambda c: abs(c[0] - s_p)) if dentro else None)
        if esc is None:
            return s_p
        return esc[0] + sinal * esc[1]
    s0, s1 = ponta(0.0, 1), ponta(L, -1)
    if s1 - s0 < 300.0:
        return 0.0, L, cruz
    return s0, s1, cruz


def _pilares_pela_planta(ents, caixa_p, locados: List[dict], avisos: List[str], raio: float = 1200.0) -> int:
    """O pilar que a planta estrutural desenha (a seção dele — o retângulo com as medidas do perfil,
    onde as treliças se cruzam) perto do lugar da locação, mas fora dele: vale o da planta, que é
    onde a estrutura apoia. A diferença entre os dois desenhos vira aviso para o projetista (os três
    PM6 do Posto CB: a locação os põe a 0,72 m da seção 400 × 200 da planta de 6,00 m). Devolve
    quantos mudaram."""
    if not locados:
        return 0
    CEL = 2000.0
    grade: Dict[tuple, list] = collections.defaultdict(list)
    for e in ents:
        if e["tipo"] != "polilinha" or not (4 <= len(e["vertices"]) <= 8):
            continue                     # a seção: o retângulo, ou o U (aberto) de cada perfil
        if _ANOT.search(str(e.get("camada", ""))) or not _dentro(_pt(e), caixa_p):
            continue
        xs = [v[0] for v in e["vertices"]]
        ys = [v[1] for v in e["vertices"]]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if 100.0 <= min(w, h) and max(w, h) <= 900.0:
            c = ((max(xs) + min(xs)) / 2.0, (max(ys) + min(ys)) / 2.0)
            grade[(int(c[0] // CEL), int(c[1] // CEL))].append((c, w, h, (min(xs), min(ys), max(xs), max(ys))))
    mudou = 0
    for pl in locados:
        pa = _perfil(pl.get("perfil"))
        if pa is None or not pa.d or not pa.bf:
            continue
        d_, bf = float(pa.d), float(pa.bf)
        x, y = pl["x"], pl["y"]
        achados = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for c, w, h, cx in grade.get((int(x // CEL) + dx, int(y // CEL) + dy), []):
                    if not ((abs(w - d_) <= 40.0 and abs(h - bf) <= 40.0) or (abs(w - bf) <= 40.0 and abs(h - d_) <= 40.0)):
                        continue
                    if math.dist(c, (x, y)) < raio:
                        achados.append((math.dist(c, (x, y)), cx))
        if not achados:
            continue
        # o mais perto e os que ficam junto dele (os dois U do perfil desenhados costas com costas)
        achados.sort()
        base = achados[0][1]
        grupo = [cx for _d, cx in achados if cx[0] <= base[2] + 30.0 and cx[2] >= base[0] - 30.0
                 and cx[1] <= base[3] + 30.0 and cx[3] >= base[1] - 30.0]
        c = ((min(g[0] for g in grupo) + max(g[2] for g in grupo)) / 2.0, (min(g[1] for g in grupo) + max(g[3] for g in grupo)) / 2.0)
        dd = math.dist(c, (x, y))
        if dd < 40.0:
            continue
        pl["x"], pl["y"] = c
        pl["pela_planta"] = "posição: a locação e a planta estrutural diferem em %.2f m; ficou a da planta" % (dd / 1000.0)
        avisos.append("pilar %s em (%.0f; %.0f): a locação o põe a %.2f m da seção que a planta estrutural desenha; "
                      "ficou no lugar da planta, onde as treliças apoiam — confira com o projetista." % (
                          pl["nome"], c[0], c[1], dd / 1000.0))
        mudou += 1
    return mudou


def _pilares_da_locacao(ents, textos, caixa_l, desl_l, usados_loc: set, avisos: List[str],
                        cargas: Optional[list] = None) -> List[dict]:
    """os pilares da locação: cada nome "PM3(200X70X20X2,65)" casado com a placa de base (ou,
    sem placa, com a seção do perfil) — posição já trazida para a planta estrutural. Em `cargas`,
    as cargas que a locação escreve por pilar (`_cargas_da_locacao`)"""
    from nucleo2d.reconhecer import perfil_do_texto
    folga = (caixa_l[0] - 2500, caixa_l[1] - 2500, caixa_l[2] + 2500, caixa_l[3] + 2500)
    placas = []
    placas_ids = []
    for e in ents:
        if e["tipo"] == "polilinha" and e.get("fechada") and re.search(r"(?i)chapa", e.get("camada", "")) \
                and _dentro(e["vertices"][0], folga):
            xs = [v[0] for v in e["vertices"]]
            ys = [v[1] for v in e["vertices"]]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if 120 <= w <= 900 and 120 <= h <= 900:
                placas.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
                placas_ids.append(e.get("id"))
    secoes = []
    secoes_ids = []
    for e in ents:
        if e["tipo"] == "polilinha" and not _ANOT.search(e.get("camada", "")) and _dentro(e["vertices"][0], folga):
            vs = [(v[0], v[1]) for v in e["vertices"]]
            xs, ys = [v[0] for v in vs], [v[1] for v in vs]
            if max(xs) - min(xs) < 520 and max(ys) - min(ys) < 520 and len(vs) >= 4:
                lados = [(math.dist(vs[i], vs[(i + 1) % len(vs)]), vs[i], vs[(i + 1) % len(vs)]) for i in range(len(vs))]
                L, a, b = max(lados)
                secoes_ids.append(e.get("id"))
                secoes.append((((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2),
                               math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180))
    out: List[dict] = []
    nomes_p = []
    for t in textos:
        if not _dentro(t["posicao"], folga):
            continue
        r = perfil_do_texto(t["texto"])
        if r and r.get("papel") == "pilar":
            nomes_p.append((t, r))
    # o nome fica sempre no mesmo lugar em relação à placa: esse deslocamento típico
    # (a mediana dos pares mais próximos) casa cada nome com a sua placa, sem que o
    # vizinho a tome
    prox = []
    for t, _r in nomes_p:
        p = (t["posicao"][0], t["posicao"][1])
        if placas:
            q = min(placas, key=lambda q: math.dist(p, q))
            if math.dist(p, q) < 1500:
                prox.append((p[0] - q[0], p[1] - q[1]))
    off = (sorted(d[0] for d in prox)[len(prox) // 2], sorted(d[1] for d in prox)[len(prox) // 2]) if prox else (0.0, 0.0)
    pares = []
    for k, (t, _r) in enumerate(nomes_p):
        alvo = (t["posicao"][0] - off[0], t["posicao"][1] - off[1])
        for i, q in enumerate(placas):
            d = math.dist(alvo, q)
            if d < 2500:
                pares.append((d, k, i))
    pares.sort()
    casado: Dict[int, Ponto2] = {}
    usadas = set()
    for d, k, i in pares:
        if k in casado or i in usadas:
            continue
        casado[k] = placas[i]
        usados_loc.add(placas_ids[i])
        usadas.add(i)
    for k, (t, r) in enumerate(nomes_p):
        q = casado.get(k)
        if q is None:
            # sem placa desenhada (pilar da torre): a seção do perfil mais perto
            alvo = (t["posicao"][0] - off[0], t["posicao"][1] - off[1])
            sc = [s for s in secoes if math.dist(s[0], alvo) < 2500]
            if sc:
                q = min(sc, key=lambda s: math.dist(s[0], alvo))[0]
        if q is None:
            avisos.append("pilar \"%s\" sem placa de base nem seção perto do nome." % t["texto"].strip())
            continue
        rot = 0.0
        sc = [s for s in secoes if math.dist(s[0], q) < 300]
        if sc:
            rot = min(sc, key=lambda s: math.dist(s[0], q))[1]
        x, y = q[0] + desl_l[0], q[1] + desl_l[1]
        usados_loc.add(t.get("id"))
        usados_loc.update(secoes_ids[i_s] for i_s, s_ in enumerate(secoes) if math.dist(s_[0], q) < 300)
        out.append({"x": x, "y": y, "rot": rot, "nome": t["texto"].strip(), "perfil": r["perfil"], "_texto": t.get("id")})
    if cargas is not None:
        # onde pode estar o pilar do bloco sem nome: a placa que nenhum nome tomou, ou a seção de
        # perfil desenhada longe dos pilares achados (a placa girada passa do tamanho das placas)
        ocupados = [(pl["x"] - desl_l[0], pl["y"] - desl_l[1]) for pl in out]
        livres = [q for i, q in enumerate(placas) if i not in usadas]
        livres += [s_[0] for s_ in secoes if min((math.dist(s_[0], o) for o in ocupados + livres), default=1e9) > 300]
        cargas.extend(_cargas_da_locacao(textos, folga, livres, off, desl_l, out))
    for pl in out:
        pl.pop("_texto", None)
    return out


# a caixa d'água desenhada na planta dela, com o volume: "CX.5.000 l", "CX 10000 L"
_CAIXA_DAGUA = re.compile(r"(?i)^\s*CX\.?\s*(\d{1,3}(?:[.,]?\d{3})*)\s*l(?:itros)?\s*$")


# a carga que a locação escreve embaixo do nome do pilar: "7,0tf" (só a vertical) ou o bloco
# "Fz: 9,00 tf / Fx: 4,00 tf / Fy: 5,00 tf / MX: 2,00 tf.m / My:-1,00 tf.m"
_CARGA_LOC = re.compile(r"^\s*(?:(F[xyz]|M[xy])\s*:\s*)?(-?\d+(?:[.,]\d+)?)\s*tf(\.m)?\s*$", re.I)


def _cargas_da_locacao(textos, folga, livres, off, desl_l, locados: List[dict]) -> List[dict]:
    """as cargas por pilar da locação, em tf e tf·m como o projeto escreve. Cada bloco começa na
    vertical (Fz) e segue para baixo, na mesma coluna. O bloco embaixo de um nome é daquele pilar;
    o bloco sem nome em cima (a outra placa do pilar em quadro, PM8) é da placa livre — a que
    nenhum nome tomou — mais perto dele."""
    cand = []
    for t in textos:
        if not _dentro(t["posicao"], folga):
            continue
        m = _CARGA_LOC.match(str(t.get("texto") or ""))
        if m and bool(m.group(1) and m.group(1)[0].upper() == "M") == bool(m.group(3)):
            cand.append((t, (m.group(1) or "Fz").capitalize(), float(m.group(2).replace(",", "."))))
    por_texto = {pl["_texto"]: pl for pl in locados if pl.get("_texto")}
    nomes = [t for t in textos if t.get("id") in por_texto]
    blocos = []
    dy_nome = []
    for t, chave, v in cand:
        if chave != "Fz":
            continue
        x, y = t["posicao"][0], t["posicao"][1]
        alt = float(t.get("altura") or 10.0)
        bloco = {"Fz": v}
        # o resto do bloco: na mesma coluna, logo abaixo, cada uma a menos de ~4 alturas da anterior
        abaixo = sorted((c for c in cand if c[1] != "Fz" and abs(c[0]["posicao"][0] - x) < 3 * alt
                         and 0 < y - c[0]["posicao"][1] < 200 * alt), key=lambda c: -c[0]["posicao"][1])
        ult = y
        for c, ch, vv in abaixo:
            if ult - c["posicao"][1] > 50 * alt or ch in bloco:
                break
            bloco[ch] = vv
            ult = c["posicao"][1]
        nome = min((n for n in nomes if abs(n["posicao"][0] - x) < 6 * alt and 0 < n["posicao"][1] - y < 60 * alt),
                   key=lambda n: n["posicao"][1] - y, default=None)
        if nome is not None:
            dy_nome.append(nome["posicao"][1] - y)
        blocos.append((x, y, nome, bloco))
    dy = sorted(dy_nome)[len(dy_nome) // 2] if dy_nome else 0.0
    out = []
    for x, y, nome, bloco in blocos:
        item = {k: bloco[k] for k in ("Fz", "Fx", "Fy", "Mx", "My") if k in bloco}
        if nome is not None:
            pl = por_texto[nome["id"]]
            pl["cargas"] = dict(item)
            item.update({"pilar": pl["nome"], "_pl": pl})
        else:
            alvo = (x - off[0], y + dy - off[1])
            q = min(livres, key=lambda q: math.dist(q, (x, y)), default=None)
            if q is None or math.dist(q, (x, y)) > 3000:
                q = alvo
            item.update({"pilar": None, "x": q[0] + desl_l[0], "y": q[1] + desl_l[1]})
        out.append(item)
    return out


def montar(desenho, parametros: Optional[dict] = None, avisar=None, doc=None) -> dict:
    """o modelo 3D do projeto recebido, montado pela planta. Devolve
    {doc, resumo, conferencia, avisos}."""
    from nucleo3d.modelo import Barra, Camada, Documento
    par = dict(PADRAO)
    par.update({k: v for k, v in (parametros or {}).items() if v not in (None, "")})
    nivel = float(par["nivel"])
    base = float(par["base"])
    aco = str(par["aco"])
    avisar = avisar or (lambda *a: None)
    ents = desenho.dict()["entidades"] if hasattr(desenho, "dict") else list(desenho)
    # o quadro do que foi usado (gerado numa montagem anterior) não é projeto: fica de fora
    ents = [e for e in ents if not str(e.get("camada", "")).upper().startswith(PREFIXO_QUADRO)]
    usados: Dict[str, set] = {"planta": set(), "tercas": set(), "locacao": set()}
    outras_feitas: List[dict] = []
    caixas_dagua: List[dict] = []
    textos = [e for e in ents if e["tipo"] == "texto"]
    avisos: List[str] = []
    encaixe: List[dict] = []

    avisar("procurando as plantas…")
    t_planta = _achar_titulo(textos, par["planta"])
    if t_planta is None:
        raise ErroDeDados("não achei a planta \"%s\" no desenho." % par["planta"])
    caixa_p = bloco_do_titulo(ents, t_planta)
    b_planta = baloes(ents, caixa_p)

    def outra_planta(titulo_txt):
        t = _achar_titulo(textos, titulo_txt) if titulo_txt else None
        if t is None:
            return None, None
        # a mesma moldura da planta estrutural, levada pelo quanto o título andou; os
        # balões de mesmo nome acertam o deslocamento
        dx = t["posicao"][0] - t_planta["posicao"][0]
        dy = t["posicao"][1] - t_planta["posicao"][1]
        caixa = (caixa_p[0] + dx, caixa_p[1] + dy, caixa_p[2] + dx, caixa_p[3] + dy)
        d = deslocamento_entre(b_planta, baloes(ents, caixa))
        if d is None or d[2] < 2:
            avisos.append("\"%s\": poucos balões de eixo em comum com a planta; alinhei pelo título." % t["texto"])
            return caixa, (-dx, -dy)
        return caixa, (d[0], d[1])

    avisar("lendo as elevações…")
    elevacoes = ler_elevacoes(ents, par["familias"])
    for novo, pai in _separar_nas_emendas(ents, caixa_p, elevacoes, avisos).items():
        # a parte separada herda a decisão "duas peças" da elevação em que estava desenhada
        dp_ = [_sem_acento(str(n)).upper().strip() for n in (par.get("duas_pecas") or [])]
        if pai in dp_ and novo not in dp_:
            par["duas_pecas"] = list(par.get("duas_pecas") or []) + [novo]
    # os pilares da locação vêm antes das treliças: a treliça termina em cima deles
    avisar("pilares da locação…")
    caixa_l, desl_l = outra_planta(par.get("locacao"))
    cargas_loc: List[dict] = []
    locados = _pilares_da_locacao(ents, textos, caixa_l, desl_l, usados["locacao"], avisos, cargas_loc) if caixa_l else []
    _pilares_pela_planta(ents, caixa_p, locados, avisos)
    # os pilares com corte próprio ("PM6 - 3X", "PM8 - 1X"): a forma deles vem do corte
    from nucleo3d import pilares_corte
    cortes_pm = pilares_corte.ler_cortes_de_pilar(ents, textos)
    avisar("lendo as peças da planta…")
    trechos, st = pecas_da_planta(ents, caixa_p, elevacoes, apoios=[(p["x"], p["y"]) for p in locados],
                                  deitadas=par.get("deitadas") or False)
    for fx in st.get("deitadas_a_conferir") or []:
        avisos.append("%s (%.1f m): a planta desenha uma faixa de treliça vista de cima (os dois banzos e a alma entre "
                      "eles) com a altura e o comprimento dessa elevação — pode ser treliça deitada. Ficou como está; "
                      "confira no projeto." % (fx["nome"], fx["comprimento"] / 1000.0))
    # a planta das terças, trazida para cima da planta estrutural: as linhas das terças
    # decidem o sentido das treliças (marcas "ST") e depois viram as terças
    caixa_t, desl_t = outra_planta(par.get("tercas"))
    reg_t: List[dict] = []
    eixos_t: List[Tuple[Ponto2, Ponto2]] = []
    eixos_t_ids: List[Optional[str]] = []
    if caixa_t:
        folga_t = (caixa_t[0] - 2500, caixa_t[1] - 2500, caixa_t[2] + 2500, caixa_t[3] + 2500)
        reg_t = [e for e in ents if _dentro(_pt(e), folga_t)]

        def _mv(p):
            return (p[0] + desl_t[0], p[1] + desl_t[1])
        segs_t = _segmentos(reg_t, re.compile(r"(?i)ter[çc]a\s*eixo"))
        eixos_t = [(_mv(a), _mv(b)) for a, b, _c in segs_t]
        eixos_t_ids = [getattr(sg, "id", None) for sg in segs_t]
        if not eixos_t:
            ret_t, _s = centros_retos(_segmentos(reg_t, re.compile(r"(?i)ter[çc]a")), lmin=500.0, larg=(20.0, 160.0))
            eixos_t = [(_mv(c.a), _mv(c.b)) for c in ret_t]
            eixos_t_ids = [next(iter(c.fontes), None) if c.fontes else None for c in ret_t]
    ori = orientar(trechos, eixos_t)
    for nome_t, dif, meio_t in ori.pop("contra_as_marcas", []):
        avisos.append("%s em (%.0f; %.0f): as marcas ST da elevação davam o sentido com o banzo de cima %d mm "
                      "desencontrado das treliças vizinhas; ficou virada, encontrando com elas — confira."
                      % (nome_t, meio_t[0], meio_t[1], dif))
    ori["ajustadas_aos_nos"] = ajustar_aos_nos(trechos, eixos_t)

    doc = doc or Documento(nome=str(par.get("nome") or "Modelo pela planta"))
    for nome_c in ("Treliças", "Vigas", "Pilares", "Terças", "Contraventamento", "Correntes"):
        doc.camadas.setdefault(nome_c, Camada(nome=nome_c))
    pecas: List[dict] = []          # {ent, perfil, papel, L, conjunto}

    def barra(p0, p1, perfil, papel, camada, conjunto=None, rot=0.0, origem=None):
        if math.dist(p0, p1) < 5.0:
            return None
        b = Barra(nome=perfil, inicio=tuple(round(c, 1) for c in p0), fim=tuple(round(c, 1) for c in p1),
                  perfil=perfil, rotacao=rot, papel=papel, aco=aco, camada=camada)
        b.atributos = {"tipo_ifc": b.tipo_ifc(), "origem": origem or {}}
        doc.add(b)
        pecas.append({"ent": b, "perfil": perfil, "papel": papel, "L": math.dist(p0, p1), "conjunto": conjunto})
        return b

    # ---------------------------------------------------------------- treliças e vigas
    contagem = collections.Counter()
    # os pilares com a metade da seção: a viga que para antes deles vai até a face
    pilares_meia = []
    for pl in locados:
        pa_pl = _perfil(pl["perfil"])
        pilares_meia.append((pl["x"], pl["y"], float(pa_pl.d or 200.0) / 2.0 if pa_pl else 100.0))
    serie = iter(range(10 ** 7))

    vigas_feitas: List[tuple] = []
    duas_pecas = {_sem_acento(str(n)).upper().strip() for n in (par.get("duas_pecas") or [])}

    def montar_trechos(trechos_lista, nivel_z):
        """as treliças (cada uma em pé na sua linha, banzo inferior em `nivel_z`) e as vigas VM
        (com o topo em `nivel_z`) de uma planta"""
        for t in trechos_lista:
            k_t = next(serie)
            if t.familia == "VIGA":
                continue
            el = t.elevacao
            c = t.caminho
            contagem[t.nome] += 1
            conj = "%s#%d" % (t.nome, k_t)
            p_banzo = (el.banzo or {}).get("perfil")
            p_alma = (el.alma or {}).get("perfil")
            mult_alma = int((el.alma or {}).get("mult") or 1)
            if not p_banzo:
                avisos.append("%s: sem a nota do banzo; ficou sem perfil." % t.nome)
                continue
            # o encaixe do bloco (a elevação como desenhada) no vão da planta: o que sobra
            # ou falta fica nas barras das pontas — anotado, para conferir com o projeto
            L_v, L_e = c.comprimento, el.comprimento
            meio = c.ponto(L_v / 2.0)
            encaixe.append({"peca": _bonito(t.nome), "conjunto": conj, "vao": round(L_v), "elevacao": round(L_e),
                            "dif": round(L_v - L_e), "ajuste": round(t.ajuste),
                            "centrada": bool(L_e and 0.9 < L_v / L_e < 1.1), "ponto": [round(meio[0]), round(meio[1])]})
            enc_o = {"vao": round(L_v), "elevacao": round(L_e)}          # vai em cada barra: o painel do bloco mostra

            def P(s, h):
                sp = _s_na_planta(t, s)
                x, y = c.ponto(sp)
                return (x, y, nivel_z + h), sp
            # banzo de cima ou de baixo: acima ou abaixo do meio da altura da treliça. O U do
            # banzo fica deitado com as abas para dentro da treliça — o de cima com a alma em
            # cima (onde a terça apoia) e as abas para baixo, o de baixo com as abas para cima
            # a elevação confirmada como duas peças (a viga de transição embaixo e a tesoura em
            # cima) vira dois blocos na mesma linha; as outras, um só
            conj_base = conj
            for sufixo, membros in _partes_da_elevacao(el, _sem_acento(t.nome).upper() in duas_pecas):
                conj = conj_base if not sufixo else "%s%s#%d" % (t.nome, sufixo, k_t)
                alturas = [h for m in membros for h in (m.h0, m.h1)]
                meio_h = (min(alturas) + max(alturas)) / 2.0 if alturas else 0.0
                for m in membros:
                    dupla = m.altura_linha > 0.0
                    # a alma desenhada com linha dupla é do perfil do banzo só quando a largura da
                    # linha é a do banzo (o montante de ponta em U); a 2L também se desenha dupla
                    perfil = p_banzo if (m.papel == "banzo" or (dupla and _largura_do_perfil(m.altura_linha, p_banzo))) \
                        else (p_alma or p_banzo)
                    papel = m.papel
                    (q0, s0p), (q1, s1p) = P(m.s0, m.h0), P(m.s1, m.h1)
                    if m.papel == "banzo" and c.curvo and abs(s1p - s0p) > 300.0:
                        # banzo calandrado: varre o perfil pelo arco, com a altura variando junto
                        # um anel a cada ~3° no arco (ou 120 mm, no caminho composto)
                        passo = c.raio * math.radians(3.0) if c.tipo == "arco" else 120.0
                        n = max(2, int(abs(s1p - s0p) / passo) + 1)
                        pts = []
                        for i in range(n + 1):
                            f = i / n
                            sp = s0p + (s1p - s0p) * f
                            x, y = c.ponto(sp)
                            pts.append((x, y, q0[2] + (q1[2] - q0[2]) * f))
                        de_cima = (m.h0 + m.h1) / 2 > meio_h
                        sol = varrer(perfil, pts, deitado=True, abas_para_baixo=de_cima)
                        sol.nome = perfil
                        sol.camada = "Treliças"
                        comp = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
                        raios = [c.raio] if c.tipo == "arco" else [q.raio for q, _r in c.partes if q.tipo == "arco"]
                        # o eixo do banzo (e o giro do U, como o do banzo reto) para a alma parar na face dele
                        sol.atributos = {"tipo_ifc": "IfcMember", "calandrada": {"raio": round(min(raios), 1),
                                                                                  "raios": [round(r_, 1) for r_ in raios]},
                                         "banzo": {"perfil": perfil, "rotacao": 270.0 if de_cima else 90.0,
                                                   "eixo": [[round(v, 1) for v in q] for q in pts]},
                                         "origem": {"planta": _bonito(t.nome) + sufixo, "sentido": t.sentido_por, "peca": conj, "encaixe": enc_o}}
                        doc.add(sol)
                        pecas.append({"ent": sol, "perfil": perfil, "papel": "banzo", "L": comp, "conjunto": conj})
                        continue
                    if m.papel in ("montante", "diagonal") and perfil == p_alma and mult_alma > 1:
                        # cantoneira dupla: costas com costas, uma de cada lado do plano da treliça
                        pa = _perfil(perfil)
                        af = (float(pa.bf or 25.0) if pa else 25.0) / 2 + 3.0
                        smid = (s0p + s1p) / 2
                        tx, ty = c.tangente(smid)
                        nx, ny = -ty, tx
                        for sinal, rot in ((1, 0.0), (-1, 180.0)):
                            d = (nx * af * sinal, ny * af * sinal, 0.0)
                            barra(tuple(q0[i] + d[i] for i in range(3)), tuple(q1[i] + d[i] for i in range(3)), perfil,
                                  papel, "Treliças", conj, rot, {"planta": _bonito(t.nome) + sufixo, "sentido": t.sentido_por, "peca": conj, "encaixe": enc_o})
                    elif m.papel == "apoio_terca" and el.apoio_terca:
                        pu = el.apoio_terca["perfil"]
                        off = _lado_do_apoio(p_banzo, pu)
                        tx, ty = c.tangente((s0p + s1p) / 2.0)
                        nx, ny = -ty, tx
                        for sinal in (1.0, -1.0):
                            d_ = (nx * off * sinal, ny * off * sinal)
                            qa = (q0[0] + d_[0], q0[1] + d_[1], q0[2])
                            qb = (q1[0] + d_[0], q1[1] + d_[1], q1[2])
                            rot = _giro_abas_para(qa, qb, (nx * sinal, ny * sinal, 0.0))
                            barra(qa, qb, pu, "apoio_terca", "Treliças", conj, rot,
                                  {"planta": _bonito(t.nome) + sufixo, "sentido": t.sentido_por, "peca": conj, "encaixe": enc_o})
                    elif m.papel == "banzo" and m.caixa > 0.0:
                        # banzo em caixão: os dois U de boca um para o outro, a junta no eixo — o de
                        # cima com as abas para baixo (270), o de baixo com as abas para cima (90)
                        off = _meio_caixao(perfil)
                        dsx, dhx = m.s1 - m.s0, m.h1 - m.h0
                        Lm = math.hypot(dsx, dhx) or 1.0
                        ns, nh = -dhx / Lm, dsx / Lm
                        if nh < 0.0:
                            ns, nh = -ns, -nh
                        for sinal, rot in ((1.0, 270.0), (-1.0, 90.0)):
                            (qa, _), (qb, _) = P(m.s0 + ns * off * sinal, m.h0 + nh * off * sinal), \
                                P(m.s1 + ns * off * sinal, m.h1 + nh * off * sinal)
                            barra(qa, qb, perfil, papel, "Treliças", conj, rot,
                                  {"planta": _bonito(t.nome) + sufixo, "sentido": t.sentido_por, "peca": conj, "encaixe": enc_o, "caixao": True})
                    else:
                        # rotação 90 leva as abas do U para cima (banzo de baixo); 270, para baixo
                        rot = (270.0 if (m.h0 + m.h1) / 2 > meio_h else 90.0) if m.papel == "banzo" else 0.0
                        if m.papel != "banzo" and dupla and perfil == p_banzo:
                            # a barra da alma no perfil do banzo (o montante de ponta em U): a largura
                            # desenhada diz a face que se vê — a aba (alma atravessada ao plano, abas para
                            # dentro da treliça, fechando a ponta) ou a alma (no plano da treliça)
                            (qm, _) = P(el.comprimento / 2.0, (m.h0 + m.h1) / 2.0)
                            rot = _giro_da_alma_em_u(q0, q1, qm, c.tangente((s0p + s1p) / 2.0), m.altura_linha, perfil)
                        barra(q0, q1, perfil, papel, "Treliças", conj, rot, {"planta": _bonito(t.nome) + sufixo, "sentido": t.sentido_por, "peca": conj, "encaixe": enc_o})

        # vigas
        for t in trechos_lista:
            if t.familia != "VIGA" or not t.perfil:
                continue
            c = t.caminho
            pf = t.perfil["perfil"]
            pa = _perfil(pf)
            d = float(pa.d or 150.0) if pa else 150.0
            z = nivel_z - d / 2.0
            pts = _viga_ate_o_pilar([c.ponto(0.0), c.ponto(c.comprimento)], pilares_meia)
            if _viga_repetida(pts, z, pf, vigas_feitas):
                continue                # a mesma viga, lida de novo (o nome em duas linhas da mesma peça)
            vigas_feitas.append((pts, z, pf))
            if int(t.perfil.get("mult") or 1) > 1:
                af = (float(pa.bf or 50.0) if pa else 50.0) / 2 + 1.0
                tx, ty = c.tangente(0.0)
                nx, ny = -ty, tx
                for sinal, rot in ((1, 180.0), (-1, 0.0)):
                    barra((pts[0][0] + nx * af * sinal, pts[0][1] + ny * af * sinal, z),
                          (pts[1][0] + nx * af * sinal, pts[1][1] + ny * af * sinal, z), pf, "viga", "Vigas", None, rot,
                          {"planta": t.nome})
            else:
                barra((pts[0][0], pts[0][1], z), (pts[1][0], pts[1][1], z), pf, "viga", "Vigas", None, 0.0, {"planta": t.nome})

    def montar_deitadas(lista, nivel_z):
        """a treliça deitada: os banzos nas duas linhas da planta, no nível, e a alma como a
        planta desenha. O U do banzo fica com as abas para dentro (para o outro banzo)"""
        for t in lista:
            k_t = next(serie)
            contagem[t.nome] += 1
            conj = "%s#%d" % (t.nome, k_t)
            el = t.elevacao
            p_banzo = (el.banzo or {}).get("perfil")
            p_alma = (el.alma or {}).get("perfil") or p_banzo
            if not p_banzo:
                avisos.append("%s: sem a nota do banzo; ficou sem perfil." % t.nome)
                continue
            meio_d = t.caminho.ponto(t.caminho.comprimento / 2.0)
            encaixe.append({"peca": _bonito(t.nome), "conjunto": conj, "vao": round(t.caminho.comprimento),
                            "elevacao": round(el.comprimento), "dif": round(t.caminho.comprimento - el.comprimento),
                            "ajuste": 0, "centrada": True, "deitada": True, "ponto": [round(meio_d[0]), round(meio_d[1])]})
            nx, ny = t.deitada["n"]
            W = t.deitada["largura"]
            a, b = t.caminho.a, t.caminho.b
            L = math.dist(a, b) or 1.0
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            orig = {"planta": _bonito(t.nome), "sentido": t.sentido_por, "peca": conj}
            # rotação 0: as abas para +n (o banzo de cá olha para o de lá); 180 no outro
            for f, rot in ((0.0, 0.0), (W, 180.0)):
                barra((a[0] + nx * f, a[1] + ny * f, nivel_z), (b[0] + nx * f, b[1] + ny * f, nivel_z), p_banzo,
                      "banzo", "Treliças", conj, rot, orig)
            for p, q in t.deitada["almas"]:
                ao_longo = abs((q[0] - p[0]) * ux + (q[1] - p[1]) * uy)
                barra((p[0], p[1], nivel_z), (q[0], q[1], nivel_z), p_alma, "montante" if ao_longo < 150.0 else "diagonal",
                      "Treliças", conj, 0.0, orig)
            avisos.append("%s: montada deitada, no nível %.2f m — a planta desenha a treliça vista de cima "
                          "(os dois banzos e a alma); confira no projeto." % (_bonito(t.nome), nivel_z / 1000.0))

    avisar("montando as treliças…")
    montar_trechos(trechos, nivel)
    montar_deitadas(st.get("deitadas") or [], nivel)
    todos_trechos = [(t, nivel) for t in trechos] + [(t, nivel) for t in st.get("deitadas") or []]

    # ---------------------------------------------------------------- outras plantas
    # mezanino, base e cobertura da caixa d'água…: cada uma no seu nível, alinhada à planta
    # estrutural pelos balões dos eixos
    for k_o, outra in enumerate(par.get("outras") or []):
        titulo_o = str((outra or {}).get("planta") or "").strip()
        t_o = _achar_titulo(textos, titulo_o) if titulo_o else None
        if t_o is None:
            avisos.append("planta \"%s\" não achada no desenho." % titulo_o)
            continue
        nivel_o = float(outra.get("nivel") or 0.0)
        avisar("planta %s…" % t_o["texto"].strip())
        try:
            caixa_o = bloco_do_titulo(ents, t_o)
        except ErroDeDados as e_:
            avisos.append(str(e_))
            continue
        d_o = deslocamento_entre(b_planta, baloes(ents, caixa_o))
        if d_o is None or d_o[2] < 2:
            avisos.append("planta \"%s\": menos de dois balões de eixo em comum com a planta estrutural; ficou de "
                          "fora (não dá para saber onde ela fica)." % t_o["texto"].strip())
            continue
        f_o = (caixa_o[0] - 2500, caixa_o[1] - 2500, caixa_o[2] + 2500, caixa_o[3] + 2500)
        movidas = [_copiar_mov(e, d_o[0], d_o[1]) for e in ents if _dentro(_pt(e), f_o)]
        cx_m = (caixa_o[0] + d_o[0], caixa_o[1] + d_o[1], caixa_o[2] + d_o[0], caixa_o[3] + d_o[1])
        tr_o, _st_o = pecas_da_planta(movidas, cx_m, elevacoes, deitadas=par.get("deitadas") or False)
        orientar(tr_o, [])
        n_antes = len(pecas)
        montar_trechos(tr_o, nivel_o)
        montar_deitadas(_st_o.get("deitadas") or [], nivel_o)
        # as vigas e treliças desta planta na camada dela (o mezanino separado das vigas do nível da cobertura)
        nome_c = camada_da_outra(t_o["texto"], nivel_o, nivel, outra.get("camada"))
        doc.camadas.setdefault(nome_c, Camada(nome=nome_c))
        for pc in pecas[n_antes:]:
            pc["ent"].camada = nome_c
        tr_o = tr_o + list(_st_o.get("deitadas") or [])
        todos_trechos += [(t, nivel_o) for t in tr_o]
        ids_o = set()
        for t in tr_o:
            if t.familia == "VIGA" and not t.perfil:
                continue
            ids_o |= set(t.caminho.fontes or ()) | {t.rotulo_id}
        ids_o |= _ids_dos_eixos(ents, caixa_o) | {t_o.get("id")}
        usados["outra:" + t_o["texto"].strip()] = ids_o
        outras_feitas.append({"planta": t_o["texto"].strip(), "nivel": nivel_o, "pecas": len(tr_o), "camada": nome_c,
                              "baloes": d_o[2]})
        # as caixas d'água desenhadas nesta planta ("CX.5.000 l"): o volume e o lugar, para a carga
        # da água no cálculo de esforços
        # o lugar é o centro do círculo da caixa mais perto do texto (o texto fica ao lado dela)
        circ_o = [e for e in ents if e["tipo"] == "circulo" and 400.0 <= float(e.get("raio") or 0) <= 2500.0
                  and _dentro(e["centro"], f_o)]
        tomados_c = set()
        for t_c in textos:
            m_c = _CAIXA_DAGUA.match(str(t_c.get("texto") or ""))
            if not (m_c and _dentro(t_c["posicao"], f_o)):
                continue
            pc = t_c["posicao"]
            livres_c = [e for e in circ_o if id(e) not in tomados_c and math.dist(e["centro"], pc) < 2500.0 + e["raio"]]
            circ = min(livres_c, key=lambda e: math.dist(e["centro"], pc), default=None)
            if circ is not None:
                tomados_c.add(id(circ))
                pc = circ["centro"]
            caixas_dagua.append({"litros": int(m_c.group(1).replace(".", "").replace(",", "")),
                                 "x": pc[0] + d_o[0], "y": pc[1] + d_o[1], "nivel": nivel_o,
                                 "diametro": round(2 * circ["raio"]) if circ is not None else None,
                                 "planta": t_o["texto"].strip()})

    # ---------------------------------------------------------------- pilares
    # primeiro os que têm corte: a copa e as mãos-francesas por cima do pilar reto, e o
    # inclinado inteiro (esse não vira pilar reto abaixo)
    res_pm = {"inclinados": set(), "n": 0, "lidos": {}}
    if cortes_pm and locados and caixa_l:
        folga_l = (caixa_l[0] - 2500, caixa_l[1] - 2500, caixa_l[2] + 2500, caixa_l[3] + 2500)
        ents_loc = [e for e in ents if _dentro(_pt(e), folga_l)]

        def mover_loc(p):
            return (p[0] + desl_l[0], p[1] + desl_l[1])

        def perto_da_estrutura(p):
            return min((u.caminho.projetar(p)[1] for u, _nv in todos_trechos), default=1e9)
        res_pm = pilares_corte.montar(cortes_pm, locados, barra, nivel, base, perto_da_estrutura, ents_loc, mover_loc, avisos)
    pilares = 0
    for pl in locados:
        x, y = pl["x"], pl["y"]
        if pl["nome"] in res_pm["inclinados"]:
            continue                                   # montado inclinado pelo corte
        em_cima = [nv for u, nv in todos_trechos if u.caminho.projetar((x, y))[1] < 600.0]
        longe = 0.0 if em_cima else min((u.caminho.projetar((x, y))[1] for u, _nv in todos_trechos), default=0.0)
        orig = {"locacao": pl["nome"]}
        if pl.get("cargas"):
            orig["cargas_locacao"] = pl["cargas"]
        if pl.get("pela_planta"):
            orig["a_conferir"] = pl["pela_planta"]
        topo_p = max(em_cima) if em_cima else nivel
        if longe > 600.0:
            # não há treliça nem viga da planta estrutural em cima dele: é de outra
            # estrutura (mezanino, torre); a altura fica a conferir
            orig["a_conferir"] = "altura: nenhuma peça da planta estrutural em cima (%.1f m)" % (longe / 1000.0)
            avisos.append("pilar %s em (%.0f; %.0f) sem peça da cobertura em cima (a %.1f m): foi até o nível "
                          "do banzo; confira a altura dele." % (pl["nome"], x, y, longe / 1000.0))
        barra((x, y, base), (x, y, topo_p), pl["perfil"], "pilar", "Pilares", None, pl["rot"], orig)
        pilares += 1

    # ---------------------------------------------------------------- a alma na face do banzo
    # montantes e diagonais param na face interna do banzo, com folga (o nó continua no eixo)
    from nucleo3d import alma_na_face
    na_face = alma_na_face.aparar([p["ent"] for p in pecas])
    for p in pecas:
        e = p["ent"]
        if e.tipo == "barra" and (e.recorte_inicio or e.recorte_fim):
            p["L"] = math.dist(e.inicio, e.fim) - e.recorte_inicio - e.recorte_fim

    # ---------------------------------------------------------------- terças e acessórios
    avisar("terças e acessórios…")
    # a terça apoia nas treliças da cobertura; o painel da borda (a testeira) sobe acima do
    # telhado e não é apoio dela
    trelicas_3d = [t for t in trechos if t.elevacao is not None and t.familia != "PAINEL"]

    def topo_em(p: Ponto2) -> Optional[float]:
        # a transição sobe acima do telhado: onde uma tesoura comum também passa, a altura é a dela
        hs = [(h, t.familia == "TRANSICAO") for t in trelicas_3d for h in [_altura_no_ponto(t, p, 250.0)] if h is not None]
        comuns = [h for h, tr in hs if not tr]
        return max(comuns) if comuns else (max(h for h, _ in hs) if hs else None)
    amostras: List[Tuple[float, float, float]] = []
    for t in trelicas_3d:
        L = t.caminho.comprimento
        for k in range(0, 21):
            p = t.caminho.ponto(L * k / 20.0)
            h = _altura_no_ponto(t, p, 50.0)
            if h is not None:
                amostras.append((p[0], p[1], h))
    grade_am: Dict[tuple, list] = collections.defaultdict(list)
    for a in amostras:
        grade_am[(int(a[0] // 5000), int(a[1] // 5000))].append(a)

    def superficie(p: Ponto2) -> Optional[float]:
        """altura do banzo superior por baixo de um ponto qualquer (os quatro pontos de
        banzo mais perto, ponderados pela distância)"""
        gx, gy = int(p[0] // 5000), int(p[1] // 5000)
        viz = [a for dx in (-1, 0, 1) for dy in (-1, 0, 1) for a in grade_am.get((gx + dx, gy + dy), [])]
        if not viz:
            return None
        viz.sort(key=lambda a: math.dist(p, a[:2]))
        w = [(1.0 / max(1.0, math.dist(p, a[:2])) ** 2, a[2]) for a in viz[:4]]
        return sum(a * b for a, b in w) / sum(a for a, _ in w)

    tercas = correntes = contravs = esticadores = 0
    tab_tc: Dict[str, dict] = _tabela_de_siglas(textos, r"TC\s?\d+[A-Z]?")
    if caixa_t:
        reg = reg_t

        def mover(p):
            return (p[0] + desl_t[0], p[1] + desl_t[1])
        rot_tc = [(mover(t["posicao"]), t["texto"].strip().upper().replace(" ", ""), t.get("id")) for t in reg
                  if t["tipo"] == "texto" and re.match(r"^TC\s?\d+[A-Z]?$", t["texto"].strip().upper())]
        pa_bz = 40.0
        # cada nome TC vale para a linha de terça mais perto dele (e só para ela)
        nomes_da_linha: Dict[int, List[Tuple[float, tuple]]] = collections.defaultdict(list)
        for pr, sg, id_tc in rot_tc:
            melhor = None
            for i_l, (a, b) in enumerate(eixos_t):
                if math.dist(a, b) < 500.0:
                    continue
                (ux, uy), L = _unit(a, b)
                s = (pr[0] - a[0]) * ux + (pr[1] - a[1]) * uy
                d = abs((pr[0] - a[0]) * -uy + (pr[1] - a[1]) * ux)
                if -300 <= s <= L + 300 and d < 700 and (melhor is None or d < melhor[0]):
                    melhor = (d, i_l, s)
            if melhor:
                nomes_da_linha[melhor[1]].append((melhor[2], (pr, sg, id_tc)))
                usados["tercas"].add(id_tc)
        polis_tr = [(t, _polilinha(t.caminho)) for t in trechos if t.elevacao is not None]
        caixas_tr = [_caixa_pts(pl, 300.0) for _t, pl in polis_tr]
        for i_l, (a, b) in enumerate(eixos_t):
            L = math.dist(a, b)
            if L < 500.0:
                continue
            (ux, uy), _L = _unit(a, b)
            # a terça começa e termina num apoio: a ponta que passa do último apoio até 1,5 m
            # é aparada nele; a que para a menos de 1 m de uma treliça segue até ela. Mais
            # que isso não se corrige às cegas (falta estrutura): fica para a verificação
            s_ini, s_fim, cruz_t = _pontas_da_terca(a, b, polis_tr, caixas_tr)
            # apoios: onde a linha da terça passa por cima de uma treliça (o meio de cada
            # travessia, com a altura do banzo ali)
            apoios = []
            tirados: List[Tuple[float, float]] = []
            npas = max(2, int((s_fim - s_ini) / 50.0))
            corrida: List[Tuple[float, float]] = []
            for k in range(npas + 2):
                s = s_ini + (s_fim - s_ini) * k / npas
                h = topo_em((a[0] + ux * s, a[1] + uy * s)) if k <= npas else None
                if h is not None:
                    corrida.append((s, h))
                elif corrida:
                    if corrida[-1][0] - corrida[0][0] <= 1000.0:
                        apoios.append((sum(c_[0] for c_ in corrida) / len(corrida), sum(c_[1] for c_ in corrida) / len(corrida)))
                    else:
                        # a terça corre em cima da treliça (ao longo da transição): apoio
                        # contínuo, um a cada ~1 m com a altura de cada ponto
                        passo_c = max(1, int(round(1000.0 / max(1.0, corrida[1][0] - corrida[0][0]))))
                        apoios += corrida[::passo_c] + ([corrida[-1]] if (len(corrida) - 1) % passo_c else [])
                    corrida = []
            if not apoios:
                continue
            # a treliça alta que a terça cruza (a transição que carrega as tesouras) passa
            # acima do telhado: a terça encosta nela, não senta em cima. O apoio que foge da
            # reta dos vizinhos mais de 400 mm sai (a cumeeira desvia uns 200 mm e fica)
            # Primeiro os do meio (com vizinho dos dois lados); as pontas só depois, senão
            # a transição alta perto da ponta faz a extrapolação tirar a treliça certa
            while len(apoios) >= 3:
                def desvio(k, sa_ha, sb_hb):
                    (sa, ha), (sb, hb) = sa_ha, sb_hb
                    sk, hk = apoios[k]
                    prev = ha + (hb - ha) * (sk - sa) / (sb - sa) if abs(sb - sa) > 1.0 else ha
                    return abs(hk - prev)
                meio_d = [(desvio(k, apoios[k - 1], apoios[k + 1]), k) for k in range(1, len(apoios) - 1)]
                pior, k = max(meio_d)
                if pior <= 400.0:
                    pontas_d = [(desvio(0, apoios[1], apoios[2]), 0),
                                (desvio(len(apoios) - 1, apoios[-3], apoios[-2]), len(apoios) - 1)]
                    pior, k = max(pontas_d)
                    if pior <= 400.0:
                        break
                tirados.append(apoios.pop(k))
            # uma terça por nome TC escrito junto da linha: o corte entre duas terças é o
            # apoio mais perto do meio entre os dois nomes (a emenda é sempre em cima de um
            # apoio; só sem apoio nenhum entre as pontas fica o meio entre os nomes)
            # a treliça alta (tirada acima), o painel e a transição no meio da linha são
            # barreira: a terça não passa por dentro deles — termina na face de um lado e
            # recomeça do outro (a transição carrega as tesouras e sobe acima do telhado)
            barreiras = []
            for s_b in sorted([ap[0] for ap in tirados] + [c[0] for c in cruz_t if c[2] in ("PAINEL", "TRANSICAO")]):
                if s_ini + 300.0 < s_b < s_fim - 300.0:
                    viz_c = [c for c in cruz_t if abs(c[0] - s_b) < 300.0]
                    meia_b = 0.0
                    if viz_c:
                        # a posição do cruzamento de verdade (o meio da travessia desvia)
                        s_b, meia_b = min(viz_c, key=lambda c: abs(c[0] - s_b))[:2]
                    if barreiras and s_b - barreiras[-1][0] < 300.0:
                        barreiras[-1] = (barreiras[-1][0], max(barreiras[-1][1], meia_b))
                        continue
                    barreiras.append((s_b, meia_b))
            # a barreira (transição, painel) não é apoio de altura: a terça termina na face dela,
            # na altura do telhado que as tesouras vizinhas dão (na TRANSIÇÃO 1 o telhado passa
            # abaixo do banzo de cima dela — a elevação desenha a tesoura de trás com os suportes)
            # a transição na PONTA da terça também não dá altura: a terça termina na face dela, na
            # altura do telhado (TRANSIÇÕES 1, 15 e 16 do Posto CB, 0,3–0,6 m acima dele — a terça
            # subia no banzo de cima dela; o corte BB desenha a telha reta até a face)
            de_altura = barreiras + [c[:2] for c in cruz_t if c[2] == "TRANSICAO"
                                     and (abs(c[0] - s_ini) <= 300.0 + c[1] or abs(c[0] - s_fim) <= 300.0 + c[1])]
            sem_barreira = [ap for ap in apoios if all(abs(ap[0] - s_b) > max(300.0, m_b + 150.0) for s_b, m_b in de_altura)]
            if len(sem_barreira) >= 1:
                apoios = sem_barreira
            vaos = []
            lo = s_ini
            for s_b, meia in barreiras:
                if s_b - meia - lo > 300.0:
                    vaos.append((lo, s_b - meia))
                lo = max(lo, s_b + meia)
            if s_fim - lo > 300.0:
                vaos.append((lo, s_fim))
            nomes_rot = sorted(nomes_da_linha.get(i_l, []), key=lambda r: r[0])
            nomes_l = [r[0] for r in nomes_rot]
            pecas_t = []
            for lo, hi in vaos:
                nomes_v = [x for x in nomes_l if lo <= x <= hi]
                cortes = []
                for s_a, s_b in zip(nomes_v, nomes_v[1:]):
                    meio = (s_a + s_b) / 2
                    antes = cortes[-1] if cortes else lo
                    # a emenda entre as duas terças fica num apoio ENTRE os dois nomes; sem
                    # apoio ali, fica onde o projetista separou as terças (o meio) e vira
                    # apontamento — não se leva a emenda para além do nome da outra terça
                    bons = [ap[0] for ap in apoios if max(antes, s_a) + 300.0 < ap[0] < min(hi, s_b) - 300.0]
                    s_c = min(bons, key=lambda x: abs(x - meio)) if bons else meio
                    if s_c - antes > 300.0 and hi - s_c > 300.0:
                        cortes.append(s_c)
                        if not bons:
                            pm = (a[0] + ux * s_c, a[1] + uy * s_c)
                            avisos.append("terça: o projeto separa duas terças (%s) sem apoio entre elas — emenda fora de "
                                          "apoio em (%.0f; %.0f); confira no projeto." % (
                                              " / ".join(r[1][1] for r in nomes_rot if r[0] in (s_a, s_b)), pm[0], pm[1]))
                pts_v = [lo] + cortes + [hi]
                pecas_t += list(zip(pts_v, pts_v[1:]))
            for s0, s1 in pecas_t:
                if s1 - s0 < 300.0:
                    continue
                mid = ((a[0] + ux * (s0 + s1) / 2), (a[1] + uy * (s0 + s1) / 2))
                # o nome da terça é o da própria linha: o que está dentro do pedaço, ou o mais
                # perto ao longo dela (o nome da linha vizinha não vale)
                dentro_p = [r for r in nomes_rot if s0 - 1.0 <= r[0] <= s1 + 1.0]
                da_linha = bool(nomes_rot)
                if dentro_p:
                    sig = dentro_p[0][1]
                elif nomes_rot:
                    sig = min(nomes_rot, key=lambda r: abs(r[0] - (s0 + s1) / 2))[1]
                else:
                    sig = min(rot_tc, key=lambda r: math.dist(r[0], mid)) if rot_tc else None
                perf = None
                if sig and (da_linha or math.dist(sig[0], mid) < 3000) and sig[1] in tab_tc:
                    perf = tab_tc[sig[1]].get("perfil")
                perf = perf or "U 100×40×2,65 (FF)"
                pt_ = _perfil(perf)
                dz = pa_bz / 2 + (float(pt_.d or 100) / 2 if pt_ else 50.0)

                def zem(s):
                    # a altura dos apoios vizinhos (de apoio em apoio; fora deles, seguindo
                    # os dois mais perto): cada ponta da terça senta na treliça dela
                    aps = sorted(apoios)
                    if len(aps) == 1:
                        return nivel + aps[0][1] + dz
                    k = 1
                    while k < len(aps) - 1 and aps[k][0] < s:
                        k += 1
                    (sa, ha), (sb, hb) = aps[k - 1], aps[k]
                    if abs(sb - sa) < 1.0:
                        return nivel + ha + dz
                    return nivel + ha + (hb - ha) * (s - sa) / (sb - sa) + dz
                p0 = (a[0] + ux * s0, a[1] + uy * s0, zem(s0))
                p1 = (a[0] + ux * s1, a[1] + uy * s1, zem(s1))
                if barra(p0, p1, perf, "terça", "Terças", None, 0.0, {"sigla": sig[1] if sig else ""}):
                    if i_l < len(eixos_t_ids):
                        usados["tercas"].add(eixos_t_ids[i_l])
                    tercas += 1

        # as terças já montadas: a corrente (o agulhamento) liga uma terça à outra, na altura
        # delas — não na da treliça mais alta ali (a transição alta levava a corrente a 1 m
        # acima da terça)
        tercas_3d = [(p_["ent"].inicio, p_["ent"].fim) for p_ in pecas if p_["papel"] == "terça"]

        def z_na_terca(p, tol=400.0):
            melhor = None
            for ta, tb in tercas_3d:
                dx, dy = tb[0] - ta[0], tb[1] - ta[1]
                L2 = dx * dx + dy * dy
                if L2 < 1.0:
                    continue
                t = max(0.0, min(1.0, ((p[0] - ta[0]) * dx + (p[1] - ta[1]) * dy) / L2))
                d = math.dist(p, (ta[0] + dx * t, ta[1] + dy * t))
                if d <= tol and (melhor is None or d < melhor[0]):
                    melhor = (d, ta[2] + (tb[2] - ta[2]) * t)
            return melhor[1] if melhor else None

        def acessorio(camada_rx, perfil, papel, camada, acima, na_terca=False):
            n = 0
            for sg in _segmentos(reg, re.compile(camada_rx)):
                a, b, _c = sg
                a, b = mover(a), mover(b)
                if math.dist(a, b) < 300.0:
                    continue
                za, zb = superficie(a), superficie(b)
                if za is None or zb is None:
                    continue
                z0, z1 = nivel + za + acima, nivel + zb + acima
                if na_terca:
                    z0 = z_na_terca(a) or z0
                    z1 = z_na_terca(b) or z1
                if barra((a[0], a[1], z0), (b[0], b[1], z1), perfil, papel, camada):
                    usados["tercas"].add(getattr(sg, "id", None))
                    n += 1
            return n
        contravs = acessorio(r"(?i)contravent", "Barra redonda 12,5", "contraventamento", "Contraventamento", 0.0)
        correntes = acessorio(r"(?i)corrente", 'L 1"×1/8"', "corrente", "Correntes", pa_bz / 2 + 50.0, na_terca=True)
        esticadores = acessorio(r"(?i)esticador", "Barra redonda 10", "corrente", "Correntes", pa_bz / 2 + 50.0,
                                na_terca=True)

    # ---------------------------------------------------------------- perto da origem
    # a planta do projetista fica onde ele desenhou (no posto, a 400 m do zero do DXF): o
    # modelo vem para perto da origem, com o canto da planta no zero (em metros redondos),
    # e o deslocamento fica guardado para voltar às coordenadas do desenho
    xs = [c for p in pecas for c in ((p["ent"].inicio[0], p["ent"].fim[0]) if p["ent"].tipo == "barra"
                                     else [v[0] for v in p["ent"].vertices])]
    ys = [c for p in pecas for c in ((p["ent"].inicio[1], p["ent"].fim[1]) if p["ent"].tipo == "barra"
                                     else [v[1] for v in p["ent"].vertices])]
    desl = (0.0, 0.0)
    if xs and par.get("origem", True):
        desl = (-math.floor(min(xs) / 1000.0) * 1000.0, -math.floor(min(ys) / 1000.0) * 1000.0)
        for p in pecas:
            e = p["ent"]
            if e.tipo == "barra":
                e.inicio = (e.inicio[0] + desl[0], e.inicio[1] + desl[1], e.inicio[2])
                e.fim = (e.fim[0] + desl[0], e.fim[1] + desl[1], e.fim[2])
            else:
                e.vertices = [(v[0] + desl[0], v[1] + desl[1], v[2]) for v in e.vertices]

    # ---------------------------------------------------------------- marcas
    grupos: Dict[tuple, List[dict]] = collections.defaultdict(list)
    for p in pecas:
        grupos[(p["perfil"], p["papel"], round(p["L"]), bool(p["ent"].tipo == "solido"))].append(p)
    ordem = sorted(grupos.items(), key=lambda kv: (-len(kv[1]), -kv[0][2], str(kv[0][0])))
    posicao_de = {}
    for i, (_k, lista) in enumerate(ordem, start=1):
        for p in lista:
            posicao_de[id(p["ent"])] = "P%d" % i
    conj_por_assin: Dict[tuple, str] = {}
    por_conj: Dict[str, list] = collections.defaultdict(list)
    for p in pecas:
        if p["conjunto"]:
            por_conj[p["conjunto"]].append(p)
    marca_do_conj: Dict[str, str] = {}
    for conj, lista in por_conj.items():
        assin = (conj.split("#")[0],) + tuple(sorted(collections.Counter(posicao_de[id(p["ent"])] for p in lista).items()))
        if assin not in conj_por_assin:
            conj_por_assin[assin] = "M%d" % (len(conj_por_assin) + 1)
        marca_do_conj[conj] = conj_por_assin[assin]
    n_conj = len(conj_por_assin)
    soltas: Dict[str, str] = {}
    peso = 0.0
    for p in pecas:
        pos = posicao_de[id(p["ent"])]
        if p["conjunto"]:
            m = marca_do_conj[p["conjunto"]]
        else:
            if pos not in soltas:
                n_conj += 1
                soltas[pos] = "M%d" % n_conj
            m = soltas[pos]
        kg = round(_massa(p["perfil"]) * p["L"] / 1000.0, 3)
        peso += kg
        a = dict(p["ent"].atributos or {})
        a["marcas"] = {"posicao": pos, "conjunto": m, "perfil": p["perfil"]}
        if p["conjunto"]:
            a["marcas"]["nome_conjunto"] = _bonito(p["conjunto"].split("#")[0])
        a["peso_kg"] = kg
        p["ent"].atributos = a

    # ---------------------------------------------------------------- conferência
    conf = []
    for nome, el in sorted(elevacoes.items()):
        tem = contagem.get(nome, 0)
        if tem or el.familia in ("TESOURA",):
            conf.append({"peca": _bonito(nome), "projeto": el.qtd, "modelo": tem, "ok": tem == el.qtd})
    tc_total = sum(v["qtd"] for v in tab_tc.values())
    tab_cr = _tabela_de_siglas(textos, r"CR\s?\d+[A-Z]?")
    tab_cv = _tabela_de_siglas(textos, r"CV\s?\d+[A-Z]?")
    tab_est = _tabela_de_siglas(textos, r"EST\s?\d+[A-Z]?")
    pm_total = sum(1 for t in textos if caixa_l and _dentro(t["posicao"], caixa_l) and re.match(r"^PM\d", t["texto"].strip()))
    resumo = {
        "trelicas": sum(contagem.values()), "tipos_de_trelica": len(contagem), "elevacoes": len(elevacoes),
        "vigas": st.get("vigas", 0), "pilares": pilares, "pilares_com_corte": res_pm["n"], "tercas": tercas, "correntes": correntes,
        "esticadores": esticadores, "contraventamentos": contravs,
        "barras": len(doc.barras), "calandradas": sum(1 for p in pecas if p["ent"].tipo == "solido"),
        "alma_na_face": na_face,
        "posicoes": len(posicao_de and set(posicao_de.values())), "conjuntos": n_conj, "peso_kg": round(peso, 1),
        "orientacao": ori, "planta_sem_nome": st.get("sem_rotulo", 0), "outras_plantas": outras_feitas,
        "nomes_sem_elevacao": {_bonito(k): v for k, v in (st.get("sem_elevacao") or {}).items()},
        "projeto": {"tercas": tc_total, "correntes": sum(v["qtd"] for v in tab_cr.values()),
                    "contraventos": sum(v["qtd"] for v in tab_cv.values()),
                    "esticadores": sum(v["qtd"] for v in tab_est.values()), "pilares": pm_total},
    }
    resumo["deslocamento_mm"] = [desl[0], desl[1]]
    doc.metadados["de_planta"] = {"parametros": {k: v for k, v in par.items()}, "resumo": resumo,
                                  "deslocamento": {"x": desl[0], "y": desl[1],
                                                   "nota": "somado às coordenadas do desenho; subtraia para voltar a ele"}}
    # as cargas da locação (tf, tf·m, como o projeto escreve), no lugar do pilar no modelo: a
    # prova real das reações do cálculo
    if cargas_loc:
        itens = []
        for c in cargas_loc:
            pl = c.pop("_pl", None)
            x, y = (pl["x"], pl["y"]) if pl else (c.pop("x"), c.pop("y"))
            itens.append(dict(c, x=round(x + desl[0], 1), y=round(y + desl[1], 1)))
        doc.metadados["de_planta"]["cargas_locacao"] = {"unidade": "tf e tf·m", "pilares": itens}
    if caixas_dagua:
        doc.metadados["de_planta"]["caixas_dagua"] = [dict(c, x=round(c["x"] + desl[0], 1), y=round(c["y"] + desl[1], 1))
                                                     for c in caixas_dagua]
    for t in trechos + list(st.get("deitadas") or []):
        if t.familia == "VIGA" and not t.perfil:
            continue
        usados["planta"] |= set(t.caminho.fontes or ()) | {t.rotulo_id}
    elevacoes_usadas = {_bonito(n): sorted(elevacoes[n].fontes) for n in contagem if n in elevacoes}
    # os cortes de pilar usados vão para o quadro como as elevações
    for nome_c, corte_c in cortes_pm.items():
        if nome_c in res_pm.get("lidos", {}) and any(str(pl.get("nome") or "").upper().replace(" ", "").startswith(nome_c + "(") or
                                                    str(pl.get("nome") or "").upper().replace(" ", "") == nome_c for pl in locados):
            elevacoes_usadas["%s - %dX" % (nome_c, corte_c["qtd"])] = sorted(corte_c["ids"])
    # o que a leitura de cada elevação usada tirou ou dividiu vai para os avisos
    for n in contagem:
        for a_el in (elevacoes[n].avisos if n in elevacoes else []):
            if a_el not in avisos:
                avisos.append(a_el)
    blocos = {"planta": (caixa_p, t_planta), "tercas": (caixa_t, _achar_titulo(textos, par.get("tercas")) if par.get("tercas") else None),
              "locacao": (caixa_l, _achar_titulo(textos, par.get("locacao")) if par.get("locacao") else None)}
    for chave, (cx, tit) in blocos.items():
        if cx:
            usados[chave] |= _ids_dos_eixos(ents, cx)
            if tit is not None:
                usados[chave].add(tit.get("id"))
    usados = {k: sorted(v - {None}) for k, v in usados.items()}
    # o bloco que não cabe no vão (a elevação desenhada maior ou menor que a peça na planta)
    # é apontamento: as barras das pontas absorvem a diferença, e isso tem de ser visto
    for e_ in encaixe:
        if abs(e_["dif"]) > ENCAIXE_MAX or not e_["centrada"]:
            e_["a_conferir"] = True
            avisos.append("%s em (%d; %d): a elevação mede %s e o vão na planta %s — %s %s; as barras das pontas "
                          "absorvem a diferença. Confira no projeto." % (
                              e_["peca"], e_["ponto"][0], e_["ponto"][1], _m_txt(e_["elevacao"]), _m_txt(e_["vao"]),
                              _m_txt(abs(e_["dif"])), "a mais no vão" if e_["dif"] > 0 else "a menos no vão"))
    for e_ in encaixe:
        e_["ponto"] = [e_["ponto"][0] + round(desl[0]), e_["ponto"][1] + round(desl[1])]      # no modelo
    resumo["encaixe"] = {"blocos": len(encaixe), "justos": sum(1 for e_ in encaixe if abs(e_["dif"]) <= 50),
                         "a_conferir": sum(1 for e_ in encaixe if e_.get("a_conferir"))}
    eixos_p = eixos_da_planta(ents, caixa_p, desl)
    from nucleo3d.trelicas_lidas import montar_lista
    # os nomes da planta sem elevação no desenho: onde estão escritos (no modelo), para a tela
    sem_el: Dict[str, List[list]] = collections.defaultdict(list)
    faltam = {_sem_acento(str(k)).upper() for k in (st.get("sem_elevacao") or {})}
    for t_ in textos:
        m_ = _RX_ROTULO.match(t_["texto"])
        if not m_ or not _dentro((t_["posicao"][0], t_["posicao"][1]), caixa_p):
            continue
        nm = (_sem_acento(m_.group(1)) + " " + m_.group(2).upper()).replace("TES ", "TESOURA ")
        if nm in faltam:
            sem_el[_bonito(nm)].append([round(t_["posicao"][0] + desl[0]), round(t_["posicao"][1] + desl[1])])
    trelicas = montar_lista(ents, elevacoes, contagem, encaixe, eixos_p, float(par.get("escala") or 20.0), _bonito,
                            sem_elevacao=dict(sem_el))
    return {"doc": doc, "resumo": resumo, "conferencia": conf, "avisos": avisos_pelos_eixos(avisos, eixos_p, desl),
            "usados": usados, "elevacoes_usadas": elevacoes_usadas,
            "eixos": eixos_p, "niveis": niveis_do_desenho(textos, par), "encaixe": encaixe,
            "trelicas": trelicas}


ENCAIXE_MAX = 200.0     # mm: diferença entre a elevação e o vão na planta que vira apontamento
_RX_M = re.compile(r"(\d)\.(\d+(?: m\b|°))")


def _m_txt(mm: float) -> str:
    return ("%.2f m" % (mm / 1000.0)).replace(".", ",")


_RX_XY = re.compile(r"\((-?\d+(?:\.\d+)?); (-?\d+(?:\.\d+)?)\)")


def avisos_pelos_eixos(avisos: List[str], eixos_p: Optional[dict], desl=(0.0, 0.0)) -> List[str]:
    """o ponto dos avisos, "(400820; 65950)" em mm do desenho, dito como no projeto: pelos
    eixos, com a coordenada do modelo (o desenho + `desl`) em metros ao lado —
    "(eixo 4 / B — 21,72; 50,76 m)" """
    from nucleo3d import eixos as _eixos
    ex = _eixos.de_dict(eixos_p)
    segs = _eixos.segmentos(ex) if ex else []
    for e in (eixos_p or {}).get("extras") or []:
        segs.append({"nome": e["nome"], "tipo": "extra", "a": list(e["a"]) + [0.0], "b": list(e["b"]) + [0.0]})

    def troca(m):
        x, y = float(m.group(1)) + desl[0], float(m.group(2)) + desl[1]
        xy = ("%.2f; %.2f m" % (x / 1000.0, y / 1000.0)).replace(".", ",")
        o = _eixos.onde((x, y), segs) if segs else ""
        return "(%s — %s)" % (o, xy) if o else "(%s)" % xy
    # e os metros com vírgula, como no projeto ("6.00 m" → "6,00 m")
    return [_RX_M.sub(r"\1,\2", _RX_XY.sub(troca, a)) for a in avisos]


# =====================================================================================
# Quadro do que foi usado: o projeto limpo, só com o que virou modelo
# =====================================================================================

PREFIXO_QUADRO = "QUADRO "
CAMADAS_QUADRO = {
    "QUADRO PEÇAS": {"cor": "#1f6feb", "espessura": 0.35},
    "QUADRO NOMES": {"cor": "#16202e", "espessura": 0.25},
    "QUADRO EIXOS": {"cor": "#c0392b", "espessura": 0.18},
    "QUADRO MOLDURA": {"cor": "#16202e", "espessura": 0.5},
}


def _ids_dos_eixos(ents, caixa, folga: float = 4000.0) -> set:
    """as linhas de eixo da planta e os balões (círculo e nome) em volta dela"""
    x0, y0, x1, y1 = caixa
    cx = (x0 - folga, y0 - folga, x1 + folga, y1 + folga)
    ids = set()
    circ = []
    for e in ents:
        if not _dentro(_pt(e), cx):
            continue
        cam = str(e.get("camada", ""))
        if e["tipo"] == "linha" and re.search(r"(?i)\beixo\b", cam) and not re.search(r"(?i)ter", cam):
            ids.add(e.get("id"))
        elif e["tipo"] == "circulo" and 120 < e["raio"] < 800:
            circ.append(e)
    grade: Dict[tuple, list] = collections.defaultdict(list)
    for c in circ:
        grade[(int(c["centro"][0] // 1000), int(c["centro"][1] // 1000))].append(c)
    for t in ents:
        if t["tipo"] != "texto" or not _dentro(t["posicao"], cx):
            continue
        if not re.fullmatch(r"[A-Za-z]{0,2}\d{0,2}[A-Za-z]?", t["texto"].strip() or "-"):
            continue
        gx, gy = int(t["posicao"][0] // 1000), int(t["posicao"][1] // 1000)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for c in grade.get((gx + dx, gy + dy), []):
                    r = c["raio"]
                    if abs(t["posicao"][0] - c["centro"][0]) < 1.3 * r and abs(t["posicao"][1] - c["centro"][1]) < 1.3 * r:
                        ids.add(t.get("id"))
                        ids.add(c.get("id"))
    return ids - {None}


def _caixa_das(ents: List[dict]) -> Optional[Tuple[float, float, float, float]]:
    xs, ys = [], []
    for e in ents:
        t = e["tipo"]
        if t == "linha":
            xs += [e["a"][0], e["b"][0]]
            ys += [e["a"][1], e["b"][1]]
        elif t == "polilinha":
            xs += [v[0] for v in e["vertices"]]
            ys += [v[1] for v in e["vertices"]]
        elif t in ("arco", "circulo"):
            xs += [e["centro"][0] - e["raio"], e["centro"][0] + e["raio"]]
            ys += [e["centro"][1] - e["raio"], e["centro"][1] + e["raio"]]
        elif t == "texto":
            xs.append(e["posicao"][0])
            ys.append(e["posicao"][1])
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _copiar(e: dict, dx: float, dy: float, camada: str) -> dict:
    import uuid
    n = dict(e)
    n["id"] = "q" + uuid.uuid4().hex[:12]
    n["camada"] = camada
    n["atributos"] = {"quadro": True, "de": e.get("id")}
    for k in ("a", "b", "centro", "posicao"):
        if k in n and n[k] is not None:
            n[k] = [n[k][0] + dx, n[k][1] + dy] + list(n[k][2:])
    if "vertices" in n:
        n["vertices"] = [[v[0] + dx, v[1] + dy] + list(v[2:]) for v in n["vertices"]]
    return n


def quadro_do_usado(ents: List[dict], montagem: dict, escala: float = 20.0, data: str = "") -> dict:
    """o quadro, no próprio desenho, com o projeto limpo: só as entidades que viraram peça do
    modelo (plantas com os eixos, locação, elevações usadas), cada grupo na sua moldura,
    abaixo de tudo o que o desenho já tem. Devolve {entidades, camadas, caixa}."""
    import uuid
    ents = [e for e in ents if not str(e.get("camada", "")).upper().startswith(PREFIXO_QUADRO)]
    por_id = {e.get("id"): e for e in ents if e.get("id")}
    usados = montagem.get("usados") or {}
    eixos = set()
    for chave in [k for k in usados if k in ("planta", "tercas", "locacao") or k.startswith("outra:")]:
        # os eixos entram no grupo de cada planta; a camada deles é a dos eixos
        for i in usados.get(chave, []):
            e = por_id.get(i)
            if e is not None and (e["tipo"] == "circulo" or re.search(r"(?i)\beixo\b", str(e.get("camada", "")))):
                eixos.add(i)
    grupos = []
    chaves = [("planta", "PLANTA ESTRUTURAL"), ("tercas", "PLANTA DAS TERÇAS"), ("locacao", "LOCAÇÃO DOS PILARES")]
    chaves += [(k, k.split(":", 1)[1]) for k in usados if k.startswith("outra:")]
    for chave, titulo in chaves:
        lst = [por_id[i] for i in usados.get(chave, []) if i in por_id]
        if lst:
            grupos.append((titulo, lst, "planta"))
    for nome, ids in sorted((montagem.get("elevacoes_usadas") or {}).items()):
        lst = [por_id[i] for i in ids if i in por_id]
        if lst:
            grupos.append((nome, lst, "elevacao"))
    if not grupos:
        return {"entidades": [], "camadas": {}, "caixa": None}
    geral = _caixa_das(ents) or (0.0, 0.0, 0.0, 0.0)
    h_txt = 25.0 * escala                       # altura real do título do grupo
    margem = 3000.0
    novas: List[dict] = []

    def texto_q(x, y, t, alt):
        return {"id": "q" + uuid.uuid4().hex[:12], "tipo": "texto", "camada": "QUADRO MOLDURA", "posicao": [x, y],
                "texto": t, "altura": alt, "angulo": 0.0, "alinhamento": "esquerda", "vertical": "base",
                "atributos": {"quadro": True}}

    def moldura(x0, y0, x1, y1):
        return {"id": "q" + uuid.uuid4().hex[:12], "tipo": "polilinha", "camada": "QUADRO MOLDURA",
                "vertices": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "fechada": True, "atributos": {"quadro": True}}
    # as plantas lado a lado; as elevações em fileiras embaixo delas
    topo = geral[1] - 40000.0
    x_ini = geral[0]
    x = x_ini
    y_linha = topo
    altura_linha = 0.0
    largura_max = 0.0
    plantas = [g for g in grupos if g[2] == "planta"]
    elevs = [g for g in grupos if g[2] == "elevacao"]

    def pousar(titulo, lst, x_esq, y_topo, grande):
        c = _caixa_das(lst)
        dx = x_esq + margem - c[0]
        dy = y_topo - margem - c[3]
        for e in lst:
            cam = "QUADRO EIXOS" if e.get("id") in eixos else ("QUADRO NOMES" if e["tipo"] == "texto" else "QUADRO PEÇAS")
            novas.append(_copiar(e, dx, dy, cam))
        w = (c[2] - c[0]) + 2 * margem
        h = (c[3] - c[1]) + 2 * margem
        novas.append(moldura(x_esq, y_topo - h, x_esq + w, y_topo))
        alt = 25.0 if grande else 15.0
        novas.append(texto_q(x_esq, y_topo - h - 1.6 * alt * escala, titulo, alt))
        return w, h + 2.2 * alt * escala
    for titulo, lst, _k in plantas:
        w, h = pousar(titulo, lst, x, y_linha, True)
        x += w + 12000.0
        altura_linha = max(altura_linha, h)
    largura_max = max(x - x_ini, 120000.0)
    y_linha -= altura_linha + 12000.0
    x = x_ini
    altura_linha = 0.0
    for titulo, lst, _k in elevs:
        c = _caixa_das(lst)
        w_prev = (c[2] - c[0]) + 2 * margem
        if x > x_ini and x - x_ini + w_prev > largura_max:
            x = x_ini
            y_linha -= altura_linha + 4000.0
            altura_linha = 0.0
        w, h = pousar(titulo, lst, x, y_linha, False)
        x += w + 4000.0
        altura_linha = max(altura_linha, h)
    y_fim = y_linha - altura_linha
    # a moldura geral e o título
    X0, Y0, X1, Y1 = x_ini - 6000.0, y_fim - 6000.0, x_ini + largura_max + 6000.0, topo + 6000.0
    novas.append(moldura(X0, Y0, X1, Y1))
    novas.append(texto_q(X0, Y1 + 1.2 * 50.0 * escala, "PROJETO CONSIDERADO NO MODELO 3D", 50.0))
    sub = ("só o que virou peça do modelo: %d plantas e %d elevações%s — gerado pela montagem pela planta; "
           "a montagem seguinte refaz este quadro" % (len(plantas), len(elevs), (" · " + data) if data else ""))
    novas.append(texto_q(X0, Y1 + 0.3 * 50.0 * escala, sub, 18.0))
    camadas = {nome: {"nome": nome, "cor": v["cor"], "visivel": True, "bloqueada": False, "tipo_linha": "CONTINUOUS",
                      "espessura": v["espessura"]} for nome, v in CAMADAS_QUADRO.items()}
    return {"entidades": novas, "camadas": camadas, "caixa": [[X0, Y0], [X1, Y1 + 2.0 * 50.0 * escala]],
            "grupos": [g[0] for g in grupos]}


# =====================================================================================
# Eixos e níveis do projeto (para o 3D mostrar como o Revit)
# =====================================================================================

_RX_NIVEL = re.compile(r"(?i)N[ÍI]VEL\s*(?:DE\s*)?\+?\s*(\d{1,3}[.,]\d{1,3})")


def eixos_da_planta(ents, caixa, desl=(0.0, 0.0)) -> Optional[dict]:
    """os eixos da planta estrutural no formato do projeto (`projeto.json` → `eixos`):
    os ortogonais pela posição (numerados atravessados, com letra ao longo) e os
    inclinados em `extras`, com a linha inteira — já no lugar do modelo (`desl`)"""
    bs = baloes(ents, caixa)
    if not bs:
        return None
    x0, y0, x1, y1 = caixa
    folga = 6000.0
    linhas = []
    for e in ents:
        if e["tipo"] != "linha":
            continue
        cam = str(e.get("camada", ""))
        if not re.search(r"(?i)\beixo\b", cam) or re.search(r"(?i)ter", cam):
            continue
        a, b = (e["a"][0], e["a"][1]), (e["b"][0], e["b"][1])
        if not (_dentro(a, (x0 - folga, y0 - folga, x1 + folga, y1 + folga))
                or _dentro(b, (x0 - folga, y0 - folga, x1 + folga, y1 + folga))):
            continue
        if math.dist(a, b) > 1000.0:
            linhas.append((a, b))
    achados = []
    for nome, c in bs.items():
        melhor = None
        for a, b in linhas:
            d = min(math.dist(c, a), math.dist(c, b))
            if d < 900.0 and (melhor is None or d < melhor[0]):
                melhor = (d, a, b)
        if melhor is None:
            continue
        _d, a, b = melhor
        (ux, uy), L = _unit(a, b)
        achados.append((nome, a, b, ux, uy))
    if not achados:
        return None
    # a direção dos eixos numerados decide o eixo do galpão (g): eles correm atravessados
    num = [x for x in achados if re.match(r"^\d", x[0])]
    vert = sum(1 for x in num if abs(x[3]) < 0.02)
    horiz = sum(1 for x in num if abs(x[4]) < 0.02)
    g = (1.0, 0.0) if vert >= horiz else (0.0, 1.0)
    p = (-g[1], g[0])
    numeros, letras, extras = [], [], []
    for nome, a, b, ux, uy in achados:
        a = (a[0] + desl[0], a[1] + desl[1])
        b = (b[0] + desl[0], b[1] + desl[1])
        ao_longo_de_p = abs(ux * g[0] + uy * g[1]) < 0.02        # linha perpendicular a g
        ao_longo_de_g = abs(ux * p[0] + uy * p[1]) < 0.02
        if ao_longo_de_p:
            numeros.append({"nome": nome, "pos": round(a[0] * g[0] + a[1] * g[1], 1)})
        elif ao_longo_de_g:
            letras.append({"nome": nome, "pos": round(a[0] * p[0] + a[1] * p[1], 1)})
        else:
            extras.append({"nome": nome, "a": [round(a[0], 1), round(a[1], 1)], "b": [round(b[0], 1), round(b[1], 1)]})
    if not numeros and not letras and not extras:
        return None
    return {"eixo_g": list(g), "numeros": sorted(numeros, key=lambda e: e["pos"]),
            "letras": sorted(letras, key=lambda e: e["pos"]), "extras": extras, "z_base": 0.0,
            "origem": "planta", "fonte_letras": "balões da planta estrutural"}


def niveis_do_desenho(textos, par) -> List[dict]:
    """os níveis do projeto: a base dos pilares, o banzo inferior e os escritos nos títulos
    das plantas ("PLANTA NO NÍVEL 3,17m", "COBERTURA DA CX DÁGUA NIVEL 11,00")"""
    out = [{"nome": "BASE DOS PILARES", "z": float(par.get("base") or 0.0)},
           {"nome": "BANZO INFERIOR", "z": float(par.get("nivel") or 0.0)}]
    for t in sorted(textos, key=lambda t: -(t.get("altura") or 0)):
        if (t.get("altura") or 0) < 15:
            continue
        m = _RX_NIVEL.search(t["texto"])
        if not m:
            continue
        z = round(float(m.group(1).replace(",", ".")) * 1000.0, 1)
        if any(abs(z - n["z"]) < 20.0 for n in out):
            continue
        out.append({"nome": "NÍVEL %s" % m.group(1).replace(".", ","), "z": z, "de": t["texto"].strip()[:60]})
    return sorted(out, key=lambda n: n["z"])
