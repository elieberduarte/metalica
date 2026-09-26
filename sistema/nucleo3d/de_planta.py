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

__all__ = ["montar", "PADRAO", "ler_elevacoes", "pecas_da_planta"]

Ponto2 = Tuple[float, float]

PADRAO = {
    "planta": "PLANTA NO NÍVEL 6,00",          # título (começo) da planta estrutural
    "nivel": 6000.0,                            # nível do banzo inferior, mm
    "locacao": "LOCAÇÃO",                       # título da locação dos pilares
    "base": 0.0,                                # nível da base dos pilares, mm
    "tercas": "PLANTA NO NÍVEL DAS TERÇAS",     # título da planta das terças
    "familias": ["TESOURA", "PAINEL", "TRANSIÇÃO", "TRELIÇA", "COMP"],
    "aco": "ASTM A36",
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
    if t in ("arco", "circulo"):
        return (e["centro"][0], e["centro"][1])
    return (e["posicao"][0], e["posicao"][1])


def _dentro(p, caixa) -> bool:
    return caixa[0] <= p[0] <= caixa[2] and caixa[1] <= p[1] <= caixa[3]


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
                out.append((a, b, cam))
        elif e["tipo"] == "polilinha":
            v = [(p[0], p[1]) for p in e["vertices"]]
            if e.get("fechada") and len(v) > 2:
                v.append(v[0])
            for a, b in zip(v, v[1:]):
                if math.dist(a, b) > 1.0:
                    out.append((a, b, cam))
    return out


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
            return Caminho("composto", partes=novas, largura=self.largura, camada=self.camada)
        if self.tipo == "reta":
            return Caminho("reta", a=self.ponto(s0), b=self.ponto(s1), largura=self.largura, camada=self.camada)
        return Caminho("arco", centro=self.centro, raio=self.raio, ini=(self.ini + math.degrees(s0 / self.raio)) % 360,
                       fim=(self.ini + math.degrees(s1 / self.raio)) % 360, largura=self.largura, camada=self.camada)

    def invertido(self) -> "Caminho":
        if self.tipo == "reta":
            return Caminho("reta", a=self.b, b=self.a, largura=self.largura, camada=self.camada)
        # o arco não inverte o sentido dos ângulos: quem inverte é o mapeamento (s → L − s)
        return self


def centros_retos(segs, lmin: float = 250.0, larg=(15.0, 260.0)) -> List[Caminho]:
    """Pares de segmentos paralelos, a uma distância de largura de perfil, que correm
    juntos → linha de centro. Um segmento entra em um par só."""
    info = []
    for a, b, cam in segs:
        (ux, uy), L = _unit(a, b)
        if L < lmin:
            continue
        if ux < -1e-9 or (abs(ux) < 1e-9 and uy < 0):
            a, b, ux, uy = b, a, -ux, -uy
        info.append((a, b, ux, uy, L, cam))
    por_ang: Dict[int, List[int]] = collections.defaultdict(list)
    for i, s in enumerate(info):
        por_ang[int(round(math.degrees(math.atan2(s[3], s[2])))) % 180].append(i)
    usados = set()
    out: List[Caminho] = []
    ordem = sorted(range(len(info)), key=lambda i: -info[i][4])
    for i in ordem:
        if i in usados:
            continue
        a, b, ux, uy, L, cam = info[i]
        ang = int(round(math.degrees(math.atan2(uy, ux)))) % 180
        cands = set()
        for d in (-1, 0, 1):
            cands |= set(por_ang[(ang + d) % 180])
        melhor = None
        for j in cands:
            if j == i or j in usados:
                continue
            c, d_, vx, vy, M, _ = info[j]
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
                               largura=abs(dist), camada=cam))
    return out, [info[i] for i in range(len(info)) if i not in usados]


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
            if math.dist(p, a) < tol and t[0] * ta[0] + t[1] * ta[1] > cosmax:
                d = math.dist(p, a)
                if melhor is None or d < melhor[0]:
                    melhor = (d, j, False)
            if math.dist(p, b) < tol and -(t[0] * tb[0] + t[1] * tb[1]) > cosmax:
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
                               camada=c.camada))
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
                               ini=ini, fim=fim, largura=d, camada=p.get("camada", "")))
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
    melhor = None
    for c in comps:
        x0, y0, x1, y1 = c["caixa"]
        if not (x0 - 3000 <= tx <= x1 + 3000) or not (-2000 <= y0 - ty <= 8000):
            continue
        area = (x1 - x0) * (y1 - y0)
        if melhor is None or area > melhor[0]:
            melhor = (area, c["caixa"])
    if melhor is None:
        raise ErroDeDados("não achei o desenho acima do título \"%s\"." % titulo["texto"])
    # a planta é feita de grupos que nem sempre se tocam (uma treliça solta, a borda): junta
    # os grupos vizinhos, a menos de 8 m, até a moldura parar de crescer (as plantas de
    # um mesmo arquivo ficam dezenas de metros uma da outra)
    x0, y0, x1, y1 = melhor[1]
    folga = 8000.0
    mudou = True
    while mudou:
        mudou = False
        for c in comps:
            a0, b0, a1, b1 = c["caixa"]
            if a0 >= x0 and b0 >= y0 and a1 <= x1 and b1 <= y1:
                continue
            if a0 <= x1 + folga and a1 >= x0 - folga and b0 <= y1 + folga and b1 >= y0 - folga:
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
    out: Dict[str, List[Ponto2]] = collections.defaultdict(list)
    for c in circ:
        r = c["raio"]
        gx, gy = int(c["centro"][0] // 1000), int(c["centro"][1] // 1000)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for t in grade.get((gx + dx, gy + dy), []):
                    # o texto do balão começa um pouco à esquerda e abaixo do centro
                    if abs(t["posicao"][0] - c["centro"][0]) < 1.3 * r and abs(t["posicao"][1] - c["centro"][1]) < 1.3 * r:
                        out[t["texto"].strip().upper()].append((c["centro"][0], c["centro"][1]))
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
    caixa: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    marcas_terca: List[float] = field(default_factory=list)     # s das marcas "ST" (suporte de terça)

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
    for nome, qtd, t in titulos:
        if nome in out:
            continue
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
        if melhor is None:
            continue
        c = melhor[1]
        x0, y0, x1, y1 = c["caixa"]
        # a nota dos perfis fica entre o desenho e o título
        banzo = alma = None
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
            elif re.search(r"DIAG|MONT", s) and alma is None:
                alma = r
        el = _elevacao_do_grupo(nome, qtd, c["segs"])
        el.banzo, el.alma = banzo, alma
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
        el.marcas_terca = sorted(marcas)
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
    el = Elevacao(nome=nome, familia=nome.split()[0], qtd=qtd, comprimento=x_dir - x_esq, x_esq=x_esq)

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
    for a, b, _ux, _uy, L, _cam in simples:
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
    return el


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


_RX_ROTULO = re.compile(r"(?i)^\s*(TESOURA|PAINEL|TRANSI[ÇC][ÃA]O|TRELI[ÇC]A|COMP|TES|VM)[\s.\-]*([\w]*)")


def pecas_da_planta(ents, caixa, elevacoes: Dict[str, Elevacao], avisar=None) -> Tuple[List[Trecho], dict]:
    """as peças nomeadas da planta estrutural, cortadas no comprimento de cada elevação"""
    from nucleo2d.reconhecer import perfil_do_texto
    regiao = [e for e in ents if _dentro(_pt(e), caixa)]
    segs = _segmentos(regiao)
    retas, _soltas = centros_retos(segs, lmin=300.0, larg=(40.0, 260.0))
    caminhos: List[Caminho] = encadear(retas + centros_arcos(regiao))
    # o nome da peça da borda fica do lado de fora do desenho
    folga = (caixa[0] - 2500, caixa[1] - 2500, caixa[2] + 2500, caixa[3] + 2500)
    textos = [e for e in ents if e["tipo"] == "texto" and _dentro(e["posicao"], folga) and _RX_ROTULO.match(e["texto"])]
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
        # o texto é escrito a partir do começo: o meio do rótulo é o que marca a peça
        comp_txt = len(t["texto"].strip()) * (t.get("altura") or 2.5) * 50.0 * 0.8
        tan = caminhos[melhor[1]].tangente(melhor[2])
        rad = math.radians(t.get("angulo") or 0.0)
        meio = (p[0] + math.cos(rad) * comp_txt / 2, p[1] + math.sin(rad) * comp_txt / 2)
        s_meio, _d = caminhos[melhor[1]].projetar(meio)
        por_caminho[melhor[1]].append((s_meio, t["texto"].strip(), t))
    # nós: cruzamentos das linhas de centro (onde uma treliça apoia na outra)
    nos: Dict[int, List[float]] = collections.defaultdict(list)
    amostras = {i: [c.ponto(c.comprimento * k / 40.0) for k in range(41)] for i, c in enumerate(caminhos)}
    for i, c in enumerate(caminhos):
        nos[i] += [0.0, c.comprimento]
        for j, d in enumerate(caminhos):
            if i == j:
                continue
            for q in amostras[j][::2] + [d.ponto(0.0), d.ponto(d.comprimento)]:
                s, dist = c.projetar(q)
                if dist < 200.0:
                    nos[i].append(s)
    trechos: List[Trecho] = []
    stats = {"caminhos": len(caminhos), "rotulos": len(textos), "sem_peca": sem_peca, "sem_rotulo": 0,
             "sem_elevacao": collections.Counter(), "vigas": 0}

    def nome_do(texto):
        m = _RX_ROTULO.match(texto)
        return (_sem_acento(m.group(1)) + " " + m.group(2).upper()).replace("TES ", "TESOURA ")
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
        ns = sorted(set(round(s, 0) for s in nos[i]))
        for s_meio, texto, _t in rot:
            m = _RX_ROTULO.match(texto)
            fam = _sem_acento(m.group(1))
            if fam in ("VM",):
                perf = perfil_do_texto(texto)
                trechos.append(Trecho(caminho=c, nome=texto, familia="VIGA", perfil=perf))
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
            Le = el.comprimento
            if len(rot) == 1 and abs(L - Le) <= max(0.08 * Le, 300.0):
                s0, s1 = 0.0, L
            else:
                s0, s1 = s_meio - Le / 2, s_meio + Le / 2
                # encosta as pontas no nó mais perto (a treliça termina onde apoia)
                s0 = min(ns, key=lambda n: abs(n - s0)) if min(abs(n - s0) for n in ns) < max(600.0, 0.12 * Le) else s0
                s1 = min(ns, key=lambda n: abs(n - s1)) if min(abs(n - s1) for n in ns) < max(600.0, 0.12 * Le) else s1
                s0, s1 = max(0.0, s0), min(L, s1)
            if s1 - s0 < 0.5 * Le:
                s0, s1 = max(0.0, s_meio - Le / 2), min(L, s_meio + Le / 2)
            trechos.append(Trecho(caminho=c.trecho(s0, s1), nome=nome, familia=fam, elevacao=el))
    return trechos, stats


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
    L = t.caminho.comprimento or 1.0
    k = el.comprimento / L
    se = (L - s if t.invertida else s) * k
    se = min(max(se, 60.0), el.comprimento - 60.0)
    return el.topo(se)


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
    k = el.comprimento / L if L else 1.0
    out = []
    for inv in (False, True):
        ss = [((L - s) if inv else s) * k for s in cruz]
        votos = collections.Counter(int(round((m - s) / 50.0)) for s in ss for m in el.marcas_terca if abs(m - s) < 700)
        if not votos:
            out.append((0, None))
            continue
        b0 = max(votos, key=lambda v: votos[v] + votos.get(v - 1, 0) + votos.get(v + 1, 0)) * 50.0
        out.append((sum(1 for s in ss if any(abs(m - s - b0) < 90 for m in el.marcas_terca)), b0))
    return out[0], out[1]


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
    resto = [custo(t) / max(1, len(vizinhos[id(t)])) for t in ts_alt if vizinhos[id(t)]]
    return {"trelicas": len(ts), "pelas_marcas": pelas_marcas, "pelas_alturas": trocas,
            "desencontro_medio_mm": round(sum(resto) / len(resto), 1) if resto else 0.0}


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
    textos = [e for e in ents if e["tipo"] == "texto"]
    avisos: List[str] = []

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
    avisar("lendo as peças da planta…")
    trechos, st = pecas_da_planta(ents, caixa_p, elevacoes)
    # a planta das terças, trazida para cima da planta estrutural: as linhas das terças
    # decidem o sentido das treliças (marcas "ST") e depois viram as terças
    caixa_t, desl_t = outra_planta(par.get("tercas"))
    reg_t: List[dict] = []
    eixos_t: List[Tuple[Ponto2, Ponto2]] = []
    if caixa_t:
        folga_t = (caixa_t[0] - 2500, caixa_t[1] - 2500, caixa_t[2] + 2500, caixa_t[3] + 2500)
        reg_t = [e for e in ents if _dentro(_pt(e), folga_t)]

        def _mv(p):
            return (p[0] + desl_t[0], p[1] + desl_t[1])
        eixos_t = [(_mv(a), _mv(b)) for a, b, _c in _segmentos(reg_t, re.compile(r"(?i)ter[çc]a\s*eixo"))]
        if not eixos_t:
            ret_t, _s = centros_retos(_segmentos(reg_t, re.compile(r"(?i)ter[çc]a")), lmin=500.0, larg=(20.0, 160.0))
            eixos_t = [(_mv(c.a), _mv(c.b)) for c in ret_t]
    ori = orientar(trechos, eixos_t)

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

    # ---------------------------------------------------------------- treliças
    avisar("montando as treliças…")
    contagem = collections.Counter()
    for k_t, t in enumerate(trechos):
        if t.familia == "VIGA":
            continue
        el = t.elevacao
        c = t.caminho
        Lc = c.comprimento
        esc = Lc / el.comprimento if el.comprimento and 0.9 < Lc / el.comprimento < 1.1 else 1.0
        contagem[t.nome] += 1
        conj = "%s#%d" % (t.nome, k_t)
        p_banzo = (el.banzo or {}).get("perfil")
        p_alma = (el.alma or {}).get("perfil")
        mult_alma = int((el.alma or {}).get("mult") or 1)
        if not p_banzo:
            avisos.append("%s: sem a nota do banzo; ficou sem perfil." % t.nome)
            continue

        def P(s, h):
            sp = (Lc - s * esc) if t.invertida else s * esc
            sp = min(max(sp, 0.0), Lc)
            x, y = c.ponto(sp)
            return (x, y, nivel + h), sp
        for m in el.membros:
            dupla = m.altura_linha > 0.0
            perfil = p_banzo if (m.papel == "banzo" or dupla) else (p_alma or p_banzo)
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
                sol = varrer(perfil, pts, deitado=True, abas_para_baixo=(m.h0 + m.h1) / 2 > 100.0)
                sol.nome = perfil
                sol.camada = "Treliças"
                comp = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
                raios = [c.raio] if c.tipo == "arco" else [q.raio for q, _r in c.partes if q.tipo == "arco"]
                sol.atributos = {"tipo_ifc": "IfcMember", "calandrada": {"raio": round(min(raios), 1),
                                                                          "raios": [round(r_, 1) for r_ in raios]},
                                 "origem": {"planta": _bonito(t.nome), "sentido": t.sentido_por}}
                doc.add(sol)
                pecas.append({"ent": sol, "perfil": perfil, "papel": "banzo", "L": comp, "conjunto": conj})
                continue
            if perfil == p_alma and mult_alma > 1 and not dupla:
                # cantoneira dupla: costas com costas, uma de cada lado do plano da treliça
                pa = _perfil(perfil)
                af = (float(pa.bf or 25.0) if pa else 25.0) / 2 + 3.0
                smid = (s0p + s1p) / 2
                tx, ty = c.tangente(smid)
                nx, ny = -ty, tx
                for sinal, rot in ((1, 0.0), (-1, 180.0)):
                    d = (nx * af * sinal, ny * af * sinal, 0.0)
                    barra(tuple(q0[i] + d[i] for i in range(3)), tuple(q1[i] + d[i] for i in range(3)), perfil,
                          papel, "Treliças", conj, rot, {"planta": _bonito(t.nome), "sentido": t.sentido_por})
            else:
                rot = 90.0 if (m.papel == "banzo") else 0.0
                barra(q0, q1, perfil, papel, "Treliças", conj, rot, {"planta": _bonito(t.nome), "sentido": t.sentido_por})

    # ---------------------------------------------------------------- vigas
    for t in trechos:
        if t.familia != "VIGA" or not t.perfil:
            continue
        c = t.caminho
        pf = t.perfil["perfil"]
        pa = _perfil(pf)
        d = float(pa.d or 150.0) if pa else 150.0
        z = nivel - d / 2.0
        pts = [c.ponto(0.0), c.ponto(c.comprimento)]
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

    # ---------------------------------------------------------------- pilares
    avisar("pilares da locação…")
    pilares = 0
    caixa_l, desl_l = outra_planta(par.get("locacao"))
    if caixa_l:
        from nucleo2d.reconhecer import perfil_do_texto
        folga = (caixa_l[0] - 2500, caixa_l[1] - 2500, caixa_l[2] + 2500, caixa_l[3] + 2500)
        placas = []
        for e in ents:
            if e["tipo"] == "polilinha" and e.get("fechada") and re.search(r"(?i)chapa", e.get("camada", "")) \
                    and _dentro(e["vertices"][0], folga):
                xs = [v[0] for v in e["vertices"]]
                ys = [v[1] for v in e["vertices"]]
                w, h = max(xs) - min(xs), max(ys) - min(ys)
                if 120 <= w <= 900 and 120 <= h <= 900:
                    placas.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
        secoes = []
        for e in ents:
            if e["tipo"] == "polilinha" and not _ANOT.search(e.get("camada", "")) and _dentro(e["vertices"][0], folga):
                vs = [(v[0], v[1]) for v in e["vertices"]]
                xs, ys = [v[0] for v in vs], [v[1] for v in vs]
                if max(xs) - min(xs) < 520 and max(ys) - min(ys) < 520 and len(vs) >= 4:
                    lados = [(math.dist(vs[i], vs[(i + 1) % len(vs)]), vs[i], vs[(i + 1) % len(vs)]) for i in range(len(vs))]
                    L, a, b = max(lados)
                    secoes.append((((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2),
                                   math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180))
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
            longe = min((u.caminho.projetar((x, y))[1] for u in trechos), default=0.0)
            orig = {"locacao": t["texto"].strip()}
            if longe > 600.0:
                # não há treliça nem viga da planta estrutural em cima dele: é de outra
                # estrutura (mezanino, torre); a altura fica a conferir
                orig["a_conferir"] = "altura: nenhuma peça da planta estrutural em cima (%.1f m)" % (longe / 1000.0)
                avisos.append("pilar %s em (%.0f; %.0f) sem peça da cobertura em cima (a %.1f m): foi até o nível "
                              "do banzo; confira a altura dele." % (t["texto"].strip(), x, y, longe / 1000.0))
            barra((x, y, base), (x, y, nivel), r["perfil"], "pilar", "Pilares", None, rot, orig)
            pilares += 1

    # ---------------------------------------------------------------- terças e acessórios
    avisar("terças e acessórios…")
    # a terça apoia nas treliças da cobertura; o painel da borda (a testeira) sobe acima do
    # telhado e não é apoio dela
    trelicas_3d = [t for t in trechos if t.elevacao is not None and t.familia != "PAINEL"]

    def topo_em(p: Ponto2) -> Optional[float]:
        hs = [h for t in trelicas_3d for h in [_altura_no_ponto(t, p, 250.0)] if h is not None]
        return max(hs) if hs else None
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
        rot_tc = [(mover(t["posicao"]), t["texto"].strip().upper().replace(" ", "")) for t in reg
                  if t["tipo"] == "texto" and re.match(r"^TC\s?\d+[A-Z]?$", t["texto"].strip().upper())]
        pa_bz = 40.0
        # cada nome TC vale para a linha de terça mais perto dele (e só para ela)
        nomes_da_linha: Dict[int, List[float]] = collections.defaultdict(list)
        for pr, sg in rot_tc:
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
                nomes_da_linha[melhor[1]].append(melhor[2])
        for i_l, (a, b) in enumerate(eixos_t):
            L = math.dist(a, b)
            if L < 500.0:
                continue
            (ux, uy), _L = _unit(a, b)
            # apoios: onde a linha da terça passa por cima de uma treliça (o meio de cada
            # travessia, com a altura do banzo ali)
            apoios = []
            npas = max(2, int(L / 50.0))
            corrida: List[Tuple[float, float]] = []
            for k in range(npas + 2):
                s = L * k / npas
                h = topo_em((a[0] + ux * s, a[1] + uy * s)) if k <= npas else None
                if h is not None:
                    corrida.append((s, h))
                elif corrida:
                    apoios.append((sum(c_[0] for c_ in corrida) / len(corrida), sum(c_[1] for c_ in corrida) / len(corrida)))
                    corrida = []
            if not apoios:
                continue
            # a treliça alta que a terça cruza (a transição que carrega as tesouras) passa
            # acima do telhado: a terça encosta nela, não senta em cima. O apoio que foge da
            # reta dos vizinhos mais de 400 mm sai (a cumeeira desvia uns 200 mm e fica)
            while len(apoios) >= 3:
                desvios = []
                for k in range(len(apoios)):
                    if 0 < k < len(apoios) - 1:
                        (sa, ha), (sb, hb) = apoios[k - 1], apoios[k + 1]
                    elif k == 0:
                        (sa, ha), (sb, hb) = apoios[1], apoios[2]
                    else:
                        (sa, ha), (sb, hb) = apoios[-3], apoios[-2]
                    sk, hk = apoios[k]
                    prev = ha + (hb - ha) * (sk - sa) / (sb - sa) if abs(sb - sa) > 1.0 else ha
                    desvios.append((abs(hk - prev), k))
                pior, k = max(desvios)
                if pior <= 400.0:
                    break
                apoios.pop(k)
            # uma terça por nome TC escrito junto da linha: o corte entre duas terças é o
            # apoio mais perto do meio entre os dois nomes
            nomes_l = sorted(nomes_da_linha.get(i_l, []))
            cortes = []
            for s_a, s_b in zip(nomes_l, nomes_l[1:]):
                meio = (s_a + s_b) / 2
                ap = min(apoios, key=lambda ap: abs(ap[0] - meio))
                # sem apoio achado entre os dois nomes, o meio entre eles (o nome fica no
                # meio da terça)
                s_c = ap[0] if s_a < ap[0] < s_b else meio
                if not cortes or s_c - cortes[-1] > 300.0:
                    cortes.append(s_c)
            pontos = [0.0] + cortes + [L]
            for s0, s1 in zip(pontos, pontos[1:]):
                if s1 - s0 < 300.0:
                    continue
                mid = ((a[0] + ux * (s0 + s1) / 2), (a[1] + uy * (s0 + s1) / 2))
                sig = min(rot_tc, key=lambda r: math.dist(r[0], mid)) if rot_tc else None
                perf = None
                if sig and math.dist(sig[0], mid) < 3000 and sig[1] in tab_tc:
                    perf = tab_tc[sig[1]].get("perfil")
                perf = perf or "U 100×40×2,65 (FF)"
                pt_ = _perfil(perf)
                dz = pa_bz / 2 + (float(pt_.d or 100) / 2 if pt_ else 50.0)

                def zem(s):
                    if len(apoios) == 1:
                        return nivel + apoios[0][1] + dz
                    # reta pelos apoios do trecho (a terça é reta)
                    (sa, ha), (sb, hb) = apoios[0], apoios[-1]
                    dentro = [ap for ap in apoios if s0 - 1 <= ap[0] <= s1 + 1]
                    if len(dentro) >= 2:
                        (sa, ha), (sb, hb) = dentro[0], dentro[-1]
                    if abs(sb - sa) < 1.0:
                        return nivel + ha + dz
                    return nivel + ha + (hb - ha) * (s - sa) / (sb - sa) + dz
                p0 = (a[0] + ux * s0, a[1] + uy * s0, zem(s0))
                p1 = (a[0] + ux * s1, a[1] + uy * s1, zem(s1))
                if barra(p0, p1, perf, "terça", "Terças", None, 0.0, {"sigla": sig[1] if sig else ""}):
                    tercas += 1

        def acessorio(camada_rx, perfil, papel, camada, acima):
            n = 0
            for a, b, _c in _segmentos(reg, re.compile(camada_rx)):
                a, b = mover(a), mover(b)
                if math.dist(a, b) < 300.0:
                    continue
                za, zb = superficie(a), superficie(b)
                if za is None or zb is None:
                    continue
                if barra((a[0], a[1], nivel + za + acima), (b[0], b[1], nivel + zb + acima), perfil, papel, camada):
                    n += 1
            return n
        contravs = acessorio(r"(?i)contravent", "Barra redonda 12,5", "contraventamento", "Contraventamento", 0.0)
        correntes = acessorio(r"(?i)corrente", 'L 1"×1/8"', "corrente", "Correntes", pa_bz / 2 + 50.0)
        esticadores = acessorio(r"(?i)esticador", "Barra redonda 10", "corrente", "Correntes", pa_bz / 2 + 50.0)

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
        "vigas": st.get("vigas", 0), "pilares": pilares, "tercas": tercas, "correntes": correntes,
        "esticadores": esticadores, "contraventamentos": contravs,
        "barras": len(doc.barras), "calandradas": sum(1 for p in pecas if p["ent"].tipo == "solido"),
        "posicoes": len(posicao_de and set(posicao_de.values())), "conjuntos": n_conj, "peso_kg": round(peso, 1),
        "orientacao": ori, "planta_sem_nome": st.get("sem_rotulo", 0),
        "nomes_sem_elevacao": {_bonito(k): v for k, v in (st.get("sem_elevacao") or {}).items()},
        "projeto": {"tercas": tc_total, "correntes": sum(v["qtd"] for v in tab_cr.values()),
                    "contraventos": sum(v["qtd"] for v in tab_cv.values()),
                    "esticadores": sum(v["qtd"] for v in tab_est.values()), "pilares": pm_total},
    }
    doc.metadados["de_planta"] = {"parametros": {k: v for k, v in par.items()}, "resumo": resumo}
    return {"doc": doc, "resumo": resumo, "conferencia": conf, "avisos": avisos}
