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
from typing import Dict, List, Optional, Tuple

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
    tipo_linha: str = "CONTINUOUS"     # os do acadiso.lin (nucleo2d/tipos_linha.py): CONTINUOUS, DASHED, HIDDEN, DOT…
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
    # o tipo de linha e a espessura (mm) do objeto; None = os da camada (o "ByLayer" do AutoCAD) — 23/10
    tipo_linha: Optional[str] = None
    espessura: Optional[float] = None

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
    terminador: Optional[str] = None     # traco (padrão: o traço oblíquo da produção), seta ou bola; None = o do desenho (metadados.estilo)
    casas: Optional[int] = None          # casas depois da vírgula no número (None = automático: inteiro, ou uma casa)
    # quanto vale cada mm desenhado: a cota feita na prancha, numa célula em 1:25, mostra a medida da peça (25 × o
    # desenhado) — pedido do usuário, 01/10: "criar alguma opção para escolher a escala da cota"; None = 1
    escala: Optional[float] = None
    # o fator de tamanho: texto, ponta e afastamentos juntos × fator — a cota feita sobre um desenho importado acompanha o
    # tamanho das cotas dele (07/10, web/cad/ferramentas.js Cota.fatorLocal); None = 1
    fator: Optional[float] = None
    # a folga do número à linha de cota, em mm de papel (a DIMGAP do AutoCAD); None = a do desenho (metadados.estilo
    # .folga_texto) ou FOLGA_TEXTO_COTA — 22/10, web/cad/nucleo/desenho2d.js folgaDaCota
    folga: Optional[float] = None

    def pontos(self):
        return [self.p1, self.p2]

    def medida(self) -> float:
        """o número que a cota mostra sem texto escrito: o desenhado × a escala da cota"""
        return self.valor() * float(self.escala or 1.0)

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
    # as setas a mais (26/10): [{"de": 0..1 — o ponto da linha de onde sai (0 na seta, 1 no joelho), "alvo": (x, y)}]
    ramos: List[dict] = field(default_factory=list)

    def pontos(self):
        return [self.alvo, self.posicao] + [tuple(r["alvo"]) for r in self.ramos]

    def segmentos_dos_ramos(self) -> List[Tuple[Ponto2, Ponto2]]:
        """[(origem, alvo)] de cada seta a mais (o mesmo de web/cad/nucleo/desenho2d.js ramosDaChamada)."""
        out = []
        for r in self.ramos:
            t = min(1.0, max(0.0, float(r.get("de", 1.0))))
            o = (self.alvo[0] + (self.posicao[0] - self.alvo[0]) * t, self.alvo[1] + (self.posicao[1] - self.alvo[1]) * t)
            out.append((o, tuple(r["alvo"])))
        return out


def ramos_levados(ramos, f) -> List[dict]:
    """As setas a mais da chamada com o alvo de cada uma levado por `f` (o `de` não muda: é a fração da linha)."""
    return [dict(r, alvo=f(tuple(r["alvo"]))) for r in (ramos or [])]


@dataclass
class CotaEspecial(Entidade2D):
    """As cotas angular, de raio, de diâmetro e ordenada (23/10): modo, centro (o vértice / o centro / a origem), p1, p2
    (o 2º lado do ângulo), posicao (por onde passa o arco / onde fica o número), eixo (x | y, da ordenada). O desenho
    delas é o de nucleo2d/cota_especial.py, espelho de web/cad/nucleo/cota_especial.js."""
    tipo: str = "cota_especial"
    camada: str = "COTA"
    modo: str = "angular"
    centro: Ponto2 = (0.0, 0.0)
    p1: Ponto2 = (0.0, 0.0)
    p2: Optional[Ponto2] = None
    posicao: Ponto2 = (0.0, 0.0)
    eixo: Optional[str] = None
    texto: Optional[str] = None
    altura: float = 2.5
    casas: Optional[int] = None
    escala: Optional[float] = None
    fator: Optional[float] = None
    terminador: Optional[str] = None
    folga: Optional[float] = None

    def pontos(self):
        return [self.centro, self.p1, self.posicao] + ([self.p2] if self.p2 else [])


@dataclass
class Bloco(Entidade2D):
    """A inserção de um bloco (24/10, como no AutoCAD): a definição fica em `Desenho.metadados["blocos"][nome]`
    ({"entidades": [...]}, no referencial dela, com o ponto de base na origem) e na biblioteca da empresa
    (nucleo2d/blocos.py); a inserção a põe em `posicao`, girada de `angulo` (graus), com a `escala` (sx, sy; a negativa
    espelha). O que está na camada "0" da definição vai para a camada da inserção. `filhos_do_bloco` dá as entidades."""
    tipo: str = "bloco"
    nome: str = ""
    posicao: Ponto2 = (0.0, 0.0)
    escala: Tuple[float, float] = (1.0, 1.0)
    angulo: float = 0.0

    def pontos(self):
        return [self.posicao]


TIPOS = {"linha": Linha, "polilinha": Polilinha, "circulo": Circulo, "arco": Arco,
         "texto": Texto, "cota": Cota, "hachura": Hachura, "chamada": Chamada, "cota_especial": CotaEspecial,
         "bloco": Bloco}


def entidade_de_dict(e: dict) -> Optional["Entidade2D"]:
    """A entidade do dicionário gravado (o do CAD); None para o tipo desconhecido."""
    classe = TIPOS.get((e or {}).get("tipo"))
    if classe is None:
        return None
    campos = {k: v for k, v in e.items() if k in classe.__dataclass_fields__}
    for k in ("a", "b", "centro", "posicao", "p1", "p2", "alvo", "texto_pos", "escala"):  # (a CotaEspecial usa os mesmos)
        if k in campos and isinstance(campos[k], (list, tuple)):
            campos[k] = tuple(campos[k])
    if "vertices" in campos:
        campos["vertices"] = [tuple(q) for q in campos["vertices"]]
    if "contornos" in campos:
        campos["contornos"] = [[tuple(q) for q in c] for c in campos["contornos"]]
    if "ramos" in campos:
        campos["ramos"] = [{"de": float(r.get("de", 1.0)), "alvo": tuple(r["alvo"])} for r in campos["ramos"] or []
                           if isinstance(r, dict) and r.get("alvo")]
    return classe(**campos)


def filhos_do_bloco(b: "Bloco", blocos: dict, prof: int = 0) -> List["Entidade2D"]:
    """As entidades da inserção `b`, no desenho: as da definição transformadas (a mesma conta de
    web/cad/nucleo/desenho2d.js filhosDoBloco). O bloco dentro do bloco também (até 8 níveis)."""
    d = (blocos or {}).get(b.nome)
    if not isinstance(d, dict) or prof > 8:
        return []
    sx, sy = (float(v) for v in (b.escala or (1.0, 1.0)))
    t = math.radians(float(b.angulo or 0.0))
    c, s_ = math.cos(t), math.sin(t)
    ox, oy = b.posicao

    def f(q):
        x, y = q[0] * sx, q[1] * sy
        return (ox + x * c - y * s_, oy + x * s_ + y * c)

    def fang(a):
        r = math.radians(float(a or 0.0))
        return (math.degrees(math.atan2(sy * math.sin(r), sx * math.cos(r))) + float(b.angulo or 0.0)) % 360.0
    k = math.sqrt(abs(sx * sy)) or 1.0
    espelha = sx * sy < 0
    out: List[Entidade2D] = []
    for i, reg in enumerate(d.get("entidades") or []):
        e = entidade_de_dict(reg)
        if e is None:
            continue
        e.id = "%s:%d" % (b.id, i)
        if e.camada in ("0", "", None):
            e.camada = b.camada
        if isinstance(e, Bloco):
            e.posicao = f(e.posicao)
            e.angulo = fang(e.angulo)
            e.escala = (e.escala[0] * k * (-1.0 if espelha else 1.0), e.escala[1] * k)
            out += filhos_do_bloco(e, blocos, prof + 1)
            continue
        if isinstance(e, Linha):
            e.a, e.b = f(e.a), f(e.b)
        elif isinstance(e, Polilinha):
            e.vertices = [f(q) for q in e.vertices]
        elif isinstance(e, Circulo):
            e.centro, e.raio = f(e.centro), e.raio * k
        elif isinstance(e, Arco):
            e.centro, e.raio = f(e.centro), e.raio * k
            a0, a1 = fang(e.inicio), fang(e.fim)
            e.inicio, e.fim = (a1, a0) if espelha else (a0, a1)
        elif isinstance(e, Texto):
            e.posicao = f(e.posicao)
            # espelhado, o texto continua legível (o MIRRTEXT 0 do AutoCAD): só gira com o bloco
            e.angulo = (float(e.angulo or 0.0) + float(b.angulo or 0.0)) % 360.0 if espelha else fang(e.angulo)
            e.altura = e.altura * k
        elif isinstance(e, Cota):
            p1, p2 = e.p1, e.p2
            e.p1, e.p2 = f(p1), f(p2)
            if e.modo in ("h", "v"):
                q2 = f((p2[0], p1[1]) if e.modo == "h" else (p1[0], p2[1]))
                dx, dy = q2[0] - e.p1[0], q2[1] - e.p1[1]
                tol = 1e-6 * (abs(dx) + abs(dy) + 1.0)
                if abs(dy) <= tol:
                    e.modo = "h"
                elif abs(dx) <= tol:
                    e.modo = "v"
                else:
                    e.modo, e.p2 = "alinhada", q2
            if e.texto_pos:
                e.texto_pos = f(e.texto_pos)
            if espelha:
                e.deslocamento = -e.deslocamento
            e.altura = e.altura * k
        elif isinstance(e, Hachura):
            e.contornos = [[f(q) for q in cont] for cont in e.contornos]
            e.angulo = (float(e.angulo or 0.0) + float(b.angulo or 0.0)) % 360.0
        elif isinstance(e, Chamada):
            e.alvo, e.posicao, e.altura = f(e.alvo), f(e.posicao), e.altura * k
            e.ramos = ramos_levados(e.ramos, f)
        elif isinstance(e, CotaEspecial):
            e.centro, e.p1, e.posicao = f(e.centro), f(e.p1), f(e.posicao)
            if e.p2:
                e.p2 = f(e.p2)
            if espelha and e.modo == "angular":
                e.p1, e.p2 = e.p2, e.p1
            e.altura = e.altura * k
        out.append(e)
    return out


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
        n.ramos = ramos_levados(n.ramos, mv)
    elif isinstance(n, CotaEspecial):
        n.centro, n.p1, n.posicao = mv(n.centro), mv(n.p1), mv(n.posicao)
        if n.p2:
            n.p2 = mv(n.p2)
    return n



#: O texto de várias linhas (24/10): as linhas no texto separadas por "\n", a 1,6 altura uma da outra — o mesmo da tela
#: (web/cad/nucleo/desenho2d.js ENTRELINHA). A primeira linha fica no ponto; com `vertical == "meio"` o bloco é centrado.
ENTRELINHA = 1.6


def linhas_do_texto(e: "Texto", k: float = 1.0):
    """[((x, y), linha)] do texto: uma só no texto comum; no de várias linhas, descendo no referencial do texto (girado)."""
    ls = str(e.texto if e.texto is not None else "").split("\n")
    if len(ls) == 1:
        return [((e.posicao[0], e.posicao[1]), ls[0])]
    passo = ENTRELINHA * float(e.altura) * k
    d0 = (len(ls) - 1) * passo / 2.0 if e.vertical == "meio" else 0.0
    a = math.radians(float(e.angulo or 0.0))
    return [((e.posicao[0] - math.sin(a) * (d0 - i * passo), e.posicao[1] + math.cos(a) * (d0 - i * passo)), t) for i, t in enumerate(ls)]


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
        pts = [p for e in self.blocos_explodidos().entidades.values() for p in e.pontos()]
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
            "entidades": [_sem_estilo_vazio(asdict(e)) for e in self.entidades.values()],
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
            ent = entidade_de_dict(e)
            if ent is not None:
                des.add(ent)
        return des

    def blocos_explodidos(self) -> "Desenho":
        """Uma cópia rasa do desenho com cada inserção de bloco trocada pelas entidades dela (o PDF, as folhas). Sem
        bloco, o próprio desenho."""
        if not any(isinstance(e, Bloco) for e in self.entidades.values()):
            return self
        out = Desenho(nome=self.nome, unidade=self.unidade, escala=self.escala, camadas=self.camadas, vistas=self.vistas,
                      metadados=self.metadados)
        defs = self.metadados.get("blocos") or {}
        for e in self.entidades.values():
            if isinstance(e, Bloco):
                for f_ in filhos_do_bloco(e, defs):
                    out.add(f_)
            else:
                out.entidades[e.id] = e
        return out

    # ---- saída ----
    def para_dxf(self, escala: Optional[float] = None, texto_unicode: bool = False):
        """Desenho DXF (saida/dxf.py), em milímetro 1:1, com o que é "de papel"
        multiplicado pela escala: cota de 2,5 mm no papel em 1:20 vira texto de 50 mm."""
        from saida.dxf import Desenho as DXF
        k = float(escala or self.escala or 1.0)
        d = DXF(self.nome, texto_unicode=texto_unicode)
        from nucleo2d.tipos_linha import escala_tracejado, estilo_da_linha
        d.ltscale = k * escala_tracejado(self.metadados.get("estilo"))
        from saida.dxf import aci_mais_proxima, nome_de_camada_r12
        # no DXF para o AutoCAD, o nome da camada no que o R12 aceita ("BANZOS U100X50X#9" →
        # "BANZOS_U100X50X_9"); o do PDF (texto_unicode) fica como no CAD, que é por ele que sai a cor
        nome_cam = (lambda n: _camada_dxf(n)) if texto_unicode else (lambda n: nome_de_camada_r12(_camada_dxf(n)))
        d.camadas_extras = [(nome_cam(n), aci_mais_proxima(c.cor), str(c.tipo_linha or "CONTINUOUS").upper())
                            for n, c in self.camadas.items() if _camada_dxf(n) == n and getattr(c, "cor", None)]
        for e in self.blocos_explodidos().entidades.values():
            cam = self.camadas.get(e.camada)
            if cam is not None and not cam.visivel:
                continue
            camada = nome_cam(e.camada)
            if isinstance(e, Linha):
                d.linha(*e.a, *e.b, camada)
            elif isinstance(e, Polilinha):
                d.polilinha(e.vertices, e.fechada, camada)
            elif isinstance(e, Circulo):
                d.circulo(e.centro[0], e.centro[1], e.raio, camada)
            elif isinstance(e, Arco):
                d.arco(e.centro[0], e.centro[1], e.raio, e.inicio, e.fim, camada)
            elif isinstance(e, Texto):
                for (x, y), t in linhas_do_texto(e, k):
                    d.texto(x, y, t, e.altura * k, camada, angulo=e.angulo, alinhamento=e.alinhamento, vertical=e.vertical)
            elif isinstance(e, Cota):
                # o número da cota na camada do texto (preto no papel), a linha na da cota (28/09)
                _cota_dxf(d, e, k, camada, terminador=(e.terminador or (self.metadados.get("estilo") or {}).get("terminador") or TERMINADOR_PADRAO),
                          camada_texto=nome_cam("TEXTO") if "TEXTO" in self.camadas else None,
                          estilo=self.metadados.get("estilo") or {})
            elif isinstance(e, Hachura):
                for contorno in e.contornos[:1]:      # o primeiro é o externo; os outros ficam vazios
                    if e.padrao == "solido" and len(contorno) >= 3:
                        d.hachura(contorno, espacamento=0.5 * k, angulo=e.angulo, camada=camada, furos=e.contornos[1:])
                    else:
                        # tubo e perfil caixa: o vazio de dentro não se hachura
                        d.hachura(contorno, espacamento=e.espacamento * k, angulo=e.angulo, camada=camada, furos=e.contornos[1:])
            elif isinstance(e, Chamada):
                _chamada_dxf(d, e, k, camada)
            elif isinstance(e, CotaEspecial):
                _cota_especial_dxf(d, e, k, camada, camada_texto=nome_cam("TEXTO") if "TEXTO" in self.camadas else None,
                                   estilo=self.metadados.get("estilo") or {})
            # a cor própria do objeto (o DXF importado com as cores, 08/10) volta no DXF
            cor = (e.atributos or {}).get("cor") if isinstance(e, (Linha, Polilinha, Circulo, Arco, Texto)) else None
            if cor:
                d.cor_da_ultima(aci_mais_proxima(cor))
            # o tipo de linha e a espessura do objeto (os dele ou os da camada, 23/10) e, para a pena do PDF, a cor do CAD
            if isinstance(e, (Linha, Polilinha, Circulo, Arco, Texto)):
                tl, esp = estilo_da_linha(e, cam)
                d.estilo_da_ultima(tl if isinstance(e, (Linha, Polilinha, Circulo, Arco)) else None, esp,
                                   cor or (getattr(cam, "cor", None) if cam is not None else None))
        return d


_MAPA_CAMADAS = {"CORTE": "ACO", "VISTA": "ACO", "VISTA-FINA": "ACO-FINO"}


def _sem_estilo_vazio(d: dict) -> dict:
    """o objeto "pela camada" não grava tipo_linha/espessura vazios (as pranchas têm dezenas de milhares de objetos)"""
    if d.get("tipo_linha") is None:
        d.pop("tipo_linha", None)
    if d.get("espessura") is None:
        d.pop("espessura", None)
    return d


def _camada_dxf(nome: str) -> str:
    """As camadas do DXF de detalhamento são as de saida/dxf.py; CORTE e VISTA caem em
    ACO e VISTA-FINA em ACO-FINO, para o arquivo abrir com a paleta que a produção já usa."""
    return _MAPA_CAMADAS.get(nome, nome)


def _terminador_dxf(d, x: float, y: float, ang: float, tam: float, camada: str, tipo: str):
    """A ponta da cota: seta cheia, bola (círculo) ou traço oblíquo a 45°."""
    if tipo == "bola":
        d.circulo(x, y, 0.35 * tam, camada)
    elif tipo == "traco":
        a = math.radians(ang + 45.0)
        cx, cy = 0.5 * tam * math.cos(a), 0.5 * tam * math.sin(a)
        d.linha(x - cx, y - cy, x + cx, y + cy, camada)
    else:
        d.seta(x, y, ang, tam, camada)


#: a ponta das cotas sem terminador próprio nem do desenho: o traço oblíquo, como a produção lê (pedido do
#: usuário, 28/09)
TERMINADOR_PADRAO = "traco"

#: da linha de cota à base do número, em mm de papel (× o fator da cota): a DIMGAP do AutoCAD no estilo ISO-25 (pedido
#: do usuário, 22/10, ME Sooro: "melhorar o magnetismo do número com a cota … igual ao autocad"). Antes, 0,55 × a altura
#: do texto. Espelho de web/cad/nucleo/desenho2d.js FOLGA_TEXTO_COTA.
FOLGA_TEXTO_COTA = 0.625


def folga_da_cota(c, estilo: Optional[dict] = None) -> float:
    """A folga do número (mm de papel): a da cota, a do estilo do desenho ou a padrão."""
    for v in (getattr(c, "folga", None), (estilo or {}).get("folga_texto")):
        try:
            if v is not None and v != "" and float(v) >= 0:
                return float(v)
        except (TypeError, ValueError):
            pass
    return FOLGA_TEXTO_COTA


def _cota_dxf(d, c: Cota, k: float, camada: str, terminador: str = TERMINADOR_PADRAO, camada_texto: str = None,
              estilo: Optional[dict] = None):
    """Cota com setas (ou bolas, ou traços) e texto proporcionais à escala (o que
    `saida/desenhos._cota` faz para o galpão, aqui sobre o documento 2D). O número no mesmo lugar que a tela o põe
    (web/cad/nucleo/desenho2d.js textoDaCota): a `folga` acima da linha e, quando não cabe entre as chamadas, um degrau
    para fora."""
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
    f = float(c.fator or 1.0)
    h = c.altura * k * f
    ext, fol, seta = 2.0 * k * f, 1.5 * k * f, 2.5 * k * f
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
        _terminador_dxf(d, a1[0], a1[1], ang, tam, camada, terminador)
        _terminador_dxf(d, a2[0], a2[1], ang + 180, tam, camada, terminador)
    else:
        _terminador_dxf(d, a1[0], a1[1], ang + 180, tam, camada, terminador)
        _terminador_dxf(d, a2[0], a2[1], ang, tam, camada, terminador)
    txt = c.texto if c.texto is not None else formatar_cota(c.medida(), c.casas)
    if c.texto_pos:
        d.texto(c.texto_pos[0], c.texto_pos[1], txt, h, camada_texto or camada, angulo=(ang if -90 < ang <= 90 else ang + 180), alinhamento="centro")
        return
    mx, my = (a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2
    ang_txt = ang if -90 < ang <= 90 else ang + 180
    lado = 1.0 if -90 < ang <= 90 else -1.0
    off = folga_da_cota(c, estilo) * k * f * lado
    if fora:
        mx += ux * (2.4 * tam + 0.4 * h * len(txt))
        my += uy * (2.4 * tam + 0.4 * h * len(txt))
    elif 0.62 * h * len(txt) + 2 * tam > comp:
        # não cabe entre as chamadas: um degrau para fora, como na tela (no PDF ele ficava em cima das chamadas)
        mx += nx * sg * 1.9 * h
        my += ny * sg * 1.9 * h
    d.texto(mx + nx * off, my + ny * off, txt, h, camada_texto or camada, angulo=ang_txt, alinhamento="centro")


def _cota_especial_dxf(d, c, k: float, camada: str, camada_texto: Optional[str] = None, estilo: Optional[dict] = None):
    """A cota angular, de raio, de diâmetro ou ordenada no DXF do PDF: as linhas, os arcos, as pontas e o número que
    nucleo2d/cota_especial.primitivas dá — o mesmo que a tela desenha."""
    from nucleo2d.cota_especial import primitivas
    pr = primitivas(c, k, estilo)
    for a, b in pr["linhas"]:
        d.linha(a[0], a[1], b[0], b[1], camada)
    for ar in pr["arcos"]:
        d.arco(ar["centro"][0], ar["centro"][1], ar["raio"], ar["inicio"], ar["fim"], camada)
    for p in pr["pontas"]:
        _terminador_dxf(d, p["p"][0], p["p"][1], p["ang"], p["tam"], camada, p["tipo"])
    for t in pr["textos"]:
        d.texto(t["pos"][0], t["pos"][1], t["txt"], t["h"], camada_texto or camada, angulo=t["ang"], alinhamento=t["alinhamento"])


def _chamada_dxf(d, c: Chamada, k: float, camada: str):
    h = c.altura * k
    d.linha(c.alvo[0], c.alvo[1], c.posicao[0], c.posicao[1], camada)
    ang = math.degrees(math.atan2(c.alvo[1] - c.posicao[1], c.alvo[0] - c.posicao[0]))
    d.seta(c.alvo[0], c.alvo[1], ang, 2.5 * k, camada)
    for o, a in c.segmentos_dos_ramos():          # as setas a mais (26/10)
        d.linha(o[0], o[1], a[0], a[1], camada)
        d.seta(a[0], a[1], math.degrees(math.atan2(a[1] - o[1], a[0] - o[0])), 2.5 * k, camada)
    direita = c.posicao[0] >= c.alvo[0]
    traco = 8.0 * k if direita else -8.0 * k
    d.linha(c.posicao[0], c.posicao[1], c.posicao[0] + traco, c.posicao[1], camada)
    d.texto(c.posicao[0] + traco + (1.5 * k if direita else -1.5 * k), c.posicao[1] + 0.8 * k,
            c.texto, h, camada, alinhamento="esquerda" if direita else "direita")


def formatar_mm(v: float, casas: Optional[int] = None) -> str:
    """Número de cota: inteiro quando é, senão uma casa com vírgula; com `casas`, sempre esse
    número de casas depois da vírgula (0 arredonda ao mm)."""
    if casas is not None and int(casas) >= 0:
        return ("%.*f" % (int(casas), v)).replace(".", ",")
    if abs(v - round(v)) < 0.05:
        return "%d" % round(v)
    return ("%.1f" % v).replace(".", ",")


def formatar_cota(v: float, casas=None) -> str:
    """O número da cota (REGRA do usuário, 26/10, na T1 da Sala de Compressores: "700,1" → 700): no automático,
    sempre ao mm inteiro; decimal só com as `casas` escolhidas à mão (a chapa, raro). O mesmo de web/cad/nucleo/
    desenho2d.js numeroDaCota (o meio mm sobe, como o Math.round de lá)."""
    if casas not in (None, "", "auto"):
        try:
            if int(casas) >= 0:
                return formatar_mm(v, int(casas))
        except (TypeError, ValueError):
            pass
    n = math.floor(v + 0.5)
    return "%d" % (0 if n == 0 else n)


def escala_sugerida(largura_mm: float, altura_mm: float, folha_util=(750.0, 520.0)) -> float:
    """Menor escala normalizada em que o desenho cabe na área útil de uma A1."""
    if largura_mm <= 0 and altura_mm <= 0:
        return 20.0
    necessaria = max(largura_mm / folha_util[0], altura_mm / folha_util[1], 1.0)
    for e in (1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500):
        if e >= necessaria:
            return float(e)
    return 500.0
