# -*- coding: utf-8 -*-
"""Documento 2D: o desenho que o CAD edita e o DXF grava.

É o contrato entre o motor de vistas (`nucleo2d/vistas.py`), a tela do CAD
(`web/cad/`) e a saída (`saida/dxf.py`, pranchas). Mesmos nomes de campo em Python e em
JavaScript, mesma serialização JSON, e nada de estado que não esteja aqui.

Unidades: **milímetro no modelo**, sempre. A escala do desenho (`escala`, por exemplo
20 para 1:20) só entra na hora de dimensionar o que é "de papel" — altura de texto,
setas de cota, espaçamento de hachura — e é o CAD e o exportador que a aplicam. Assim
um desenho cotado em 1:20 pode ir para a prancha em 1:25 e as cotas continuam certas.

Entidades: linha, polilinha, círculo, arco, texto, cota, hachura, chamada. Cada uma
tem `camada` e `atributos` (dicionário livre: de qual peça 3D veio, marca, vista).
Ângulos em graus, anti-horários, como no DXF.
"""
import math
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados

Ponto2 = Tuple[float, float]


def novo_id() -> str:
    return uuid.uuid4().hex[:10]


# ----------------------------------------------------------------- camadas

@dataclass
class Camada2D:
    nome: str
    cor: str = "#4b5563"
    visivel: bool = True
    bloqueada: bool = False
    tipo_linha: str = "CONTINUOUS"     # CONTINUOUS, HIDDEN, CENTER, DASHED
    espessura: float = 0.25            # mm no papel


#: Camadas de um desenho de detalhamento, no espírito de saida/dxf.py.
CAMADAS_PADRAO = [
    Camada2D("CORTE", "#16202e", espessura=0.5),         # contorno do que o plano corta
    Camada2D("VISTA", "#2b3646", espessura=0.35),        # silhueta do que está além
    Camada2D("VISTA-FINA", "#6b7280", espessura=0.18),   # arestas vivas
    Camada2D("OCULTA", "#8a94a6", tipo_linha="HIDDEN", espessura=0.18),
    Camada2D("HACHURA", "#8a94a6", espessura=0.13),
    Camada2D("EIXO", "#c0392b", tipo_linha="CENTER", espessura=0.18),
    Camada2D("COTA", "#1c7a43", espessura=0.18),
    Camada2D("TEXTO", "#16202e", espessura=0.25),
    Camada2D("FURO", "#1f5fbf", espessura=0.25),
    Camada2D("SOLDA", "#9a6b06", espessura=0.35),
    Camada2D("PARAFUSO", "#1f5fbf", espessura=0.25),
    Camada2D("AUXILIAR", "#7d8a9e", tipo_linha="DASHED", espessura=0.13),
]


# --------------------------------------------------------------- entidades

@dataclass
class Entidade2D:
    id: str = field(default_factory=novo_id)
    tipo: str = "entidade"
    camada: str = "VISTA"
    atributos: Dict[str, object] = field(default_factory=dict)

    def pontos(self) -> List[Ponto2]:
        """Pontos que definem a caixa envolvente."""
        return []


@dataclass
class Linha(Entidade2D):
    tipo: str = "linha"
    a: Ponto2 = (0.0, 0.0)
    b: Ponto2 = (0.0, 0.0)

    def pontos(self):
        return [self.a, self.b]


@dataclass
class Polilinha(Entidade2D):
    tipo: str = "polilinha"
    vertices: List[Ponto2] = field(default_factory=list)
    fechada: bool = False

    def pontos(self):
        return list(self.vertices)


@dataclass
class Circulo(Entidade2D):
    tipo: str = "circulo"
    centro: Ponto2 = (0.0, 0.0)
    raio: float = 1.0

    def pontos(self):
        x, y = self.centro
        return [(x - self.raio, y - self.raio), (x + self.raio, y + self.raio)]


@dataclass
class Arco(Entidade2D):
    tipo: str = "arco"
    centro: Ponto2 = (0.0, 0.0)
    raio: float = 1.0
    inicio: float = 0.0       # graus
    fim: float = 90.0

    def pontos(self):
        pts = []
        a0, a1 = self.inicio, self.fim
        if a1 < a0:
            a1 += 360.0
        n = max(2, int((a1 - a0) / 15) + 1)
        for i in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * i / n)
            pts.append((self.centro[0] + self.raio * math.cos(a), self.centro[1] + self.raio * math.sin(a)))
        return pts


@dataclass
class Texto(Entidade2D):
    tipo: str = "texto"
    camada: str = "TEXTO"
    posicao: Ponto2 = (0.0, 0.0)
    texto: str = ""
    altura: float = 2.5       # mm no papel
    angulo: float = 0.0
    alinhamento: str = "esquerda"     # esquerda, centro, direita
    vertical: str = "base"            # base, meio, topo

    def pontos(self):
        return [self.posicao]


@dataclass
class Cota(Entidade2D):
    """Cota linear entre dois pontos. `modo`: alinhada (na direção p1→p2), h ou v
    (projetada). `deslocamento` é a distância da linha de cota aos pontos, em mm de
    papel, com sinal para o lado (positivo = à esquerda do sentido p1→p2)."""
    tipo: str = "cota"
    camada: str = "COTA"
    modo: str = "alinhada"
    p1: Ponto2 = (0.0, 0.0)
    p2: Ponto2 = (0.0, 0.0)
    deslocamento: float = 10.0
    texto: Optional[str] = None
    altura: float = 2.5
    texto_pos: Optional[Ponto2] = None   # onde o número foi posto à mão (None = no meio da linha)

    def pontos(self):
        return [self.p1, self.p2]

    def valor(self) -> float:
        if self.modo == "h":
            return abs(self.p2[0] - self.p1[0])
        if self.modo == "v":
            return abs(self.p2[1] - self.p1[1])
        return math.hypot(self.p2[0] - self.p1[0], self.p2[1] - self.p1[1])


@dataclass
class Hachura(Entidade2D):
    tipo: str = "hachura"
    camada: str = "HACHURA"
    contornos: List[List[Ponto2]] = field(default_factory=list)   # primeiro é o externo
    padrao: str = "aco"           # aco (45°), concreto, solido
    angulo: float = 45.0
    espacamento: float = 2.5      # mm no papel

    def pontos(self):
        return [p for c in self.contornos for p in c]


@dataclass
class Chamada(Entidade2D):
    tipo: str = "chamada"
    camada: str = "TEXTO"
    alvo: Ponto2 = (0.0, 0.0)
    posicao: Ponto2 = (0.0, 0.0)
    texto: str = ""
    altura: float = 2.5

    def pontos(self):
        return [self.alvo, self.posicao]


TIPOS = {"linha": Linha, "polilinha": Polilinha, "circulo": Circulo, "arco": Arco,
         "texto": Texto, "cota": Cota, "hachura": Hachura, "chamada": Chamada}


# ---------------------------------------------------------------- desenho

def transladar(e: "Entidade2D", dx: float, dy: float) -> "Entidade2D":
    """Cópia da entidade deslocada de (dx, dy) — mesma identidade (id), o resto igual."""
    import copy as _copy
    n = _copy.deepcopy(e)
    mv = lambda q: (round(q[0] + dx, 3), round(q[1] + dy, 3))    # noqa: E731
    if isinstance(n, Linha):
        n.a, n.b = mv(n.a), mv(n.b)
    elif isinstance(n, Polilinha):
        n.vertices = [mv(q) for q in n.vertices]
    elif isinstance(n, (Circulo, Arco)):
        n.centro = mv(n.centro)
    elif isinstance(n, Texto):
        n.posicao = mv(n.posicao)
    elif isinstance(n, Cota):
        n.p1, n.p2 = mv(n.p1), mv(n.p2)
        if n.texto_pos:
            n.texto_pos = mv(n.texto_pos)
    elif isinstance(n, Hachura):
        n.contornos = [[mv(q) for q in c] for c in n.contornos]
    elif isinstance(n, Chamada):
        n.alvo, n.posicao = mv(n.alvo), mv(n.posicao)
    return n


@dataclass
class Desenho:
    nome: str = "Desenho"
    unidade: str = "mm"
    escala: float = 20.0                                  # 1:20
    camadas: Dict[str, Camada2D] = field(default_factory=dict)
    entidades: Dict[str, Entidade2D] = field(default_factory=dict)
    vistas: List[dict] = field(default_factory=list)     # como cada vista foi gerada
    metadados: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.camadas:
            for c in CAMADAS_PADRAO:
                self.camadas[c.nome] = Camada2D(**asdict(c))

    # ---- manipulação ----
    def add(self, ent: Entidade2D) -> Entidade2D:
        if ent.camada and ent.camada not in self.camadas:
            self.camadas[ent.camada] = Camada2D(nome=ent.camada)
        self.entidades[ent.id] = ent
        return ent

    def remover(self, id_: str):
        self.entidades.pop(id_, None)

    def por_tipo(self, tipo: str) -> List[Entidade2D]:
        return [e for e in self.entidades.values() if e.tipo == tipo]

    @property
    def tamanho(self) -> int:
        return len(self.entidades)

    def caixa(self) -> Optional[Tuple[Ponto2, Ponto2]]:
        pts = [p for e in self.entidades.values() for p in e.pontos()]
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys)), (max(xs), max(ys))

    # ---- serialização ----
    def dict(self) -> dict:
        return {
            "nome": self.nome, "unidade": self.unidade, "escala": self.escala,
            "camadas": {k: asdict(v) for k, v in self.camadas.items()},
            "entidades": [asdict(e) for e in self.entidades.values()],
            "vistas": self.vistas, "metadados": self.metadados,
        }

    @classmethod
    def de_dict(cls, d: dict) -> "Desenho":
        if not isinstance(d, dict):
            raise ErroDeDados("desenho 2D ausente ou inválido.")
        des = cls(nome=d.get("nome") or "Desenho", unidade=d.get("unidade") or "mm",
                  escala=float(d.get("escala") or 20.0),
                  camadas={k: Camada2D(**{**{"nome": k}, **v}) for k, v in (d.get("camadas") or {}).items()},
                  vistas=list(d.get("vistas") or []), metadados=dict(d.get("metadados") or {}))
        for e in d.get("entidades") or []:
            classe = TIPOS.get(e.get("tipo"))
            if classe is None:
                continue
            campos = {k: v for k, v in e.items() if k in classe.__dataclass_fields__}
            for k in ("a", "b", "centro", "posicao", "p1", "p2", "alvo", "texto_pos"):
                if k in campos and campos[k] is not None:
                    campos[k] = tuple(campos[k])
            if "vertices" in campos:
                campos["vertices"] = [tuple(p) for p in campos["vertices"]]
            if "contornos" in campos:
                campos["contornos"] = [[tuple(p) for p in c] for c in campos["contornos"]]
            des.add(classe(**campos))
        return des

    # ---- saída ----
    def para_dxf(self, escala: Optional[float] = None, texto_unicode: bool = False):
        """Desenho DXF (saida/dxf.py), em milímetro 1:1, com o que é "de papel"
        multiplicado pela escala: cota de 2,5 mm no papel em 1:20 vira texto de 50 mm."""
        from saida.dxf import Desenho as DXF
        k = float(escala or self.escala or 1.0)
        d = DXF(self.nome, texto_unicode=texto_unicode)
        for e in self.entidades.values():
            cam = self.camadas.get(e.camada)
            if cam is not None and not cam.visivel:
                continue
            camada = _camada_dxf(e.camada)
            if isinstance(e, Linha):
                d.linha(*e.a, *e.b, camada)
            elif isinstance(e, Polilinha):
                d.polilinha(e.vertices, e.fechada, camada)
            elif isinstance(e, Circulo):
                d.circulo(e.centro[0], e.centro[1], e.raio, camada)
            elif isinstance(e, Arco):
                d.arco(e.centro[0], e.centro[1], e.raio, e.inicio, e.fim, camada)
            elif isinstance(e, Texto):
                d.texto(e.posicao[0], e.posicao[1], e.texto, e.altura * k, camada,
                        angulo=e.angulo, alinhamento=e.alinhamento, vertical=e.vertical)
            elif isinstance(e, Cota):
                _cota_dxf(d, e, k, camada)
            elif isinstance(e, Hachura):
                for contorno in e.contornos[:1]:      # o primeiro é o externo; os outros ficam vazios
                    if e.padrao == "solido" and len(contorno) >= 3:
                        d.hachura(contorno, espacamento=0.5 * k, angulo=e.angulo, camada=camada, furos=e.contornos[1:])
                    else:
                        # tubo e perfil caixa: o vazio de dentro não se hachura
                        d.hachura(contorno, espacamento=e.espacamento * k, angulo=e.angulo, camada=camada, furos=e.contornos[1:])
            elif isinstance(e, Chamada):
                _chamada_dxf(d, e, k, camada)
        return d


_MAPA_CAMADAS = {"CORTE": "ACO", "VISTA": "ACO", "VISTA-FINA": "ACO-FINO"}


def _camada_dxf(nome: str) -> str:
    """As camadas do DXF de detalhamento são as de saida/dxf.py; CORTE e VISTA caem em
    ACO e VISTA-FINA em ACO-FINO, para o arquivo abrir com a paleta que a produção já usa."""
    return _MAPA_CAMADAS.get(nome, nome)


def _cota_dxf(d, c: Cota, k: float, camada: str):
    """Cota com setas e texto proporcionais à escala (o que `saida/desenhos._cota` faz
    para o galpão, aqui sobre o documento 2D)."""
    x1, y1 = c.p1
    x2, y2 = c.p2
    if c.modo == "h":
        y2 = y1
    elif c.modo == "v":
        x2 = x1
    dx, dy = x2 - x1, y2 - y1
    comp = math.hypot(dx, dy)
    if comp < 1e-9:
        return
    ux, uy = dx / comp, dy / comp
    nx, ny = -uy, ux
    desl = c.deslocamento * k
    sg = 1.0 if desl >= 0 else -1.0
    h = c.altura * k
    ext, fol, seta = 2.0 * k, 1.5 * k, 2.5 * k
    a1 = (x1 + nx * desl, y1 + ny * desl)
    a2 = (x2 + nx * desl, y2 + ny * desl)
    # linhas de chamada saem dos pontos originais (em cota h/v, dos pontos projetados)
    for (px, py), (ax, ay) in (((c.p1[0], c.p1[1]), a1), ((c.p2[0], c.p2[1]), a2)):
        d.linha(px + nx * sg * fol, py + ny * sg * fol, ax + nx * sg * ext, ay + ny * sg * ext, camada)
    d.linha(a1[0], a1[1], a2[0], a2[1], camada)
    ang = math.degrees(math.atan2(uy, ux))
    tam = min(seta, max(0.4 * seta, comp / 4))
    fora = comp < 3.0 * tam
    if fora:
        d.seta(a1[0], a1[1], ang, tam, camada)
        d.seta(a2[0], a2[1], ang + 180, tam, camada)
    else:
        d.seta(a1[0], a1[1], ang + 180, tam, camada)
        d.seta(a2[0], a2[1], ang, tam, camada)
    txt = c.texto if c.texto is not None else formatar_mm(c.valor())
    if c.texto_pos:
        d.texto(c.texto_pos[0], c.texto_pos[1], txt, h, camada, angulo=(ang if -90 < ang <= 90 else ang + 180), alinhamento="centro")
        return
    mx, my = (a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2
    ang_txt = ang if -90 < ang <= 90 else ang + 180
    lado = 1.0 if -90 < ang <= 90 else -1.0
    off = h * 0.55 * lado
    if fora:
        mx += ux * (2.4 * tam + 0.4 * h * len(txt))
        my += uy * (2.4 * tam + 0.4 * h * len(txt))
    d.texto(mx + nx * off, my + ny * off, txt, h, camada, angulo=ang_txt, alinhamento="centro")


def _chamada_dxf(d, c: Chamada, k: float, camada: str):
    h = c.altura * k
    d.linha(c.alvo[0], c.alvo[1], c.posicao[0], c.posicao[1], camada)
    ang = math.degrees(math.atan2(c.alvo[1] - c.posicao[1], c.alvo[0] - c.posicao[0]))
    d.seta(c.alvo[0], c.alvo[1], ang, 2.5 * k, camada)
    direita = c.posicao[0] >= c.alvo[0]
    traco = 8.0 * k if direita else -8.0 * k
    d.linha(c.posicao[0], c.posicao[1], c.posicao[0] + traco, c.posicao[1], camada)
    d.texto(c.posicao[0] + traco + (1.5 * k if direita else -1.5 * k), c.posicao[1] + 0.8 * k,
            c.texto, h, camada, alinhamento="esquerda" if direita else "direita")


def formatar_mm(v: float) -> str:
    """Número de cota: inteiro quando é, senão uma casa com vírgula."""
    if abs(v - round(v)) < 0.05:
        return "%d" % round(v)
    return ("%.1f" % v).replace(".", ",")


def escala_sugerida(largura_mm: float, altura_mm: float, folha_util=(750.0, 520.0)) -> float:
    """Menor escala normalizada em que o desenho cabe na área útil de uma A1."""
    if largura_mm <= 0 and altura_mm <= 0:
        return 20.0
    necessaria = max(largura_mm / folha_util[0], altura_mm / folha_util[1], 1.0)
    for e in (1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500):
        if e >= necessaria:
            return float(e)
    return 500.0
