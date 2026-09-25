# -*- coding: utf-8 -*-
"""Documento 3D: o modelo que o editor manipula e que vira IFC.

Um documento é uma lista de entidades organizadas em camadas. Há dois tipos de
entidade, e a diferença entre elas é o que o sistema sabe sobre o objeto:

    paramétrica   Barra e Chapa sabem o que são. A barra guarda o perfil do catálogo
                  e o eixo; a geometria é gerada a partir disso. Trocar o perfil
                  atualiza o desenho, o peso e o tipo IFC exportado.
    livre         Solido guarda vértices e faces, como no SketchUp. Serve para o que
                  não é estrutura: terreno, equipamento, geometria vinda de IFC de
                  terceiros.

Unidades do documento: **milímetro** e grau. É a unidade dos desenhos e do IFC, e
evita conversões no editor. O dimensionamento continua em kN e cm; a conversão
acontece na fronteira, em `de_projeto.py`.

Eixos: Z para cima, X ao longo do comprimento do galpão, Y no sentido do vão. É a
convenção usada nos desenhos e a que o IFC recebe sem rotação adicional.
"""
from dataclasses import dataclass, field, asdict, fields, is_dataclass
from typing import Dict, List, Optional, Tuple
import math
import uuid

Ponto = Tuple[float, float, float]


# --------------------------------------------------------------- utilidades

def novo_id(prefixo="e") -> str:
    return f"{prefixo}{uuid.uuid4().hex[:12]}"


def distancia(a: Ponto, b: Ponto) -> float:
    return math.dist(a, b)


def somar(a: Ponto, b: Ponto) -> Ponto:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def subtrair(a: Ponto, b: Ponto) -> Ponto:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def escalar(a: Ponto, k: float) -> Ponto:
    return (a[0] * k, a[1] * k, a[2] * k)


def norma(a: Ponto) -> float:
    return math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)


def normalizar(a: Ponto) -> Ponto:
    n = norma(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 1.0)


def produto_vetorial(a: Ponto, b: Ponto) -> Ponto:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def produto_escalar(a: Ponto, b: Ponto) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


# --------------------------------------------------------------- organização


_ATOMOS = (int, float, str, bool, type(None))
_NUMEROS = {int, float}


def _copia_para_dict(v):
    """O mesmo que `asdict` faz com o valor, sem copiar número por número: tupla só de
    números é imutável e vai inteira (o modelo tem milhões de coordenadas; o `asdict`
    levava ~8 s por gravação no projeto dos compressores)."""
    if isinstance(v, _ATOMOS):
        return v
    if isinstance(v, list):
        if not v:
            return []
        tipos = {type(x) for x in v}
        if tipos <= _NUMEROS:
            return list(v)                                  # índices de uma face
        if tipos == {tuple} and {type(k) for x in v for k in x} <= _NUMEROS:
            return list(v)                                  # vértices: as tuplas vão inteiras
        return [_copia_para_dict(x) for x in v]
    if isinstance(v, tuple):
        return v if all(isinstance(k, _ATOMOS) for k in v) else tuple(_copia_para_dict(x) for x in v)
    if isinstance(v, dict):
        return {k: _copia_para_dict(x) for k, x in v.items()}
    if is_dataclass(v) and not isinstance(v, type):
        return asdict(v)
    return v

@dataclass
class Camada:
    """Tag no sentido do SketchUp: controla visibilidade e cor padrão."""
    nome: str
    cor: str = "#8a94a6"
    visivel: bool = True
    bloqueada: bool = False


@dataclass
class Material:
    """Material de aparência e, quando estrutural, de cálculo."""
    nome: str
    cor: str = "#9aa4b2"
    opacidade: float = 1.0
    metalico: float = 0.85
    rugosidade: float = 0.45
    aco: str = ""            # nome no catálogo de materiais, quando estrutural


# --------------------------------------------------------------- entidades

@dataclass
class Entidade:
    """Base de tudo que aparece no modelo."""
    id: str = field(default_factory=lambda: novo_id())
    tipo: str = "entidade"
    nome: str = ""
    camada: str = "Estrutura"
    material: str = ""
    visivel: bool = True
    bloqueada: bool = False
    grupo: str = ""                       # id do grupo pai, quando houver
    atributos: Dict[str, object] = field(default_factory=dict)

    def dict(self) -> dict:
        d = {f.name: _copia_para_dict(getattr(self, f.name)) for f in fields(self)}
        d["tipo"] = self.tipo
        return d


@dataclass
class Barra(Entidade):
    """Elemento linear com perfil de catálogo: pilar, viga, terça, contraventamento.

    O eixo vai de `inicio` a `fim`, em milímetros. `perfil` é o nome no catálogo
    (por exemplo "W 310×38,7"). `rotacao` gira a seção em torno do próprio eixo, em
    graus. `papel` define o tipo IFC exportado.
    """
    tipo: str = "barra"
    inicio: Ponto = (0.0, 0.0, 0.0)
    fim: Ponto = (0.0, 0.0, 1000.0)
    perfil: str = "W 310×38,7"
    rotacao: float = 0.0
    papel: str = "viga"                   # pilar, viga, terça, contraventamento, barra
    aco: str = "ASTM A572 Gr.50"
    recorte_inicio: float = 0.0           # encurtamento na ponta, mm
    recorte_fim: float = 0.0

    @property
    def comprimento(self) -> float:
        return distancia(self.inicio, self.fim)

    @property
    def direcao(self) -> Ponto:
        return normalizar(subtrair(self.fim, self.inicio))

    @property
    def meio(self) -> Ponto:
        return escalar(somar(self.inicio, self.fim), 0.5)

    @property
    def vertical(self) -> bool:
        return abs(self.direcao[2]) > 0.95

    def tipo_ifc(self) -> str:
        return {"pilar": "IfcColumn", "viga": "IfcBeam", "terça": "IfcMember",
                "terca": "IfcMember", "contraventamento": "IfcMember",
                "longarina": "IfcMember", "barra": "IfcMember"}.get(
                    self.papel.lower(), "IfcMember")


@dataclass
class Chapa(Entidade):
    """Chapa plana de espessura constante: chapa de topo, base, gusset, enrijecedor.

    O contorno é uma lista de pontos no plano local, e o plano é definido pela
    origem e pelos vetores `eixo_x` e `eixo_y`. A espessura cresce para o lado da
    normal, ou simetricamente quando `centrada`.
    """
    tipo: str = "chapa"
    origem: Ponto = (0.0, 0.0, 0.0)
    eixo_x: Ponto = (1.0, 0.0, 0.0)
    eixo_y: Ponto = (0.0, 1.0, 0.0)
    contorno: List[Tuple[float, float]] = field(default_factory=list)
    espessura: float = 12.7
    centrada: bool = True
    furos: List[dict] = field(default_factory=list)     # {x, y, diametro}
    aco: str = "ASTM A36"

    @property
    def normal(self) -> Ponto:
        return normalizar(produto_vetorial(self.eixo_x, self.eixo_y))

    @property
    def area(self) -> float:
        """Área do contorno, em mm²."""
        p = self.contorno
        if len(p) < 3:
            return 0.0
        s = sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
                for i in range(len(p)))
        bruta = abs(s) / 2
        furos = 0.0
        for f in self.furos:
            d = float(f.get("diametro", 0) or 0)
            if d > 0:
                furos += math.pi * (d / 2) ** 2
            else:
                larg, alt = float(f.get("largura", 0) or 0), float(f.get("altura", 0) or 0)
                if larg > 0 and alt > 0:
                    a, b = max(larg, alt), min(larg, alt)
                    furos += (a - b) * b + math.pi * (b / 2) ** 2
        return bruta - furos

    def tipo_ifc(self) -> str:
        return "IfcPlate"


@dataclass
class Solido(Entidade):
    """Geometria livre: vértices e faces, como no SketchUp.

    As faces são listas de índices de vértices, em ordem anti-horária vista de fora.
    É o que recebe a geometria importada de IFC de terceiros e o que as ferramentas
    de desenho e push/pull produzem.
    """
    tipo: str = "solido"
    vertices: List[Ponto] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)
    arestas_vivas: List[Tuple[int, int]] = field(default_factory=list)
    origem_ifc: str = ""                  # GlobalId de onde veio, quando importado

    @property
    def volume(self) -> float:
        """Volume por soma de tetraedros, em mm³ (positivo para sólido fechado)."""
        v = 0.0
        for f in self.faces:
            for i in range(1, len(f) - 1):
                a, b, c = self.vertices[f[0]], self.vertices[f[i]], self.vertices[f[i + 1]]
                v += produto_escalar(a, produto_vetorial(b, c)) / 6
        return abs(v)

    def tipo_ifc(self) -> str:
        return self.atributos.get("tipo_ifc", "IfcBuildingElementProxy")


@dataclass
class Grupo(Entidade):
    """Conjunto de entidades tratado como um objeto. Pode ser instanciado."""
    tipo: str = "grupo"
    filhos: List[str] = field(default_factory=list)
    origem: Ponto = (0.0, 0.0, 0.0)
    definicao: str = ""                   # id da definição, quando é uma instância


# --------------------------------------------------------------- documento

@dataclass
class Documento:
    """O modelo inteiro: entidades, camadas, materiais e metadados."""
    nome: str = "Modelo"
    unidade: str = "mm"
    entidades: Dict[str, Entidade] = field(default_factory=dict)
    camadas: Dict[str, Camada] = field(default_factory=dict)
    materiais: Dict[str, Material] = field(default_factory=dict)
    projeto: dict = field(default_factory=dict)      # dados do galpão, quando veio dele
    metadados: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.camadas:
            for nome, cor in (("Estrutura", "#4b5563"), ("Terças", "#0b3d91"),
                              ("Contraventamento", "#2e8b57"), ("Chapas", "#b8860b"),
                              ("Fechamento", "#9aa4b2"), ("Referência", "#c0392b"),
                              ("Importado", "#6a3fb5")):
                self.camadas[nome] = Camada(nome=nome, cor=cor)
        if not self.materiais:
            self.materiais["Aço"] = Material("Aço", "#8a94a6", aco="ASTM A572 Gr.50")
            self.materiais["Aço galvanizado"] = Material("Aço galvanizado", "#b6bec9",
                                                         aco="ZAR-345")
            self.materiais["Concreto"] = Material("Concreto", "#b9b2a6", metalico=0.0,
                                                  rugosidade=0.9)
            self.materiais["Telha"] = Material("Telha", "#cfd6e0", metalico=0.6)
            self.materiais["Vidro"] = Material("Vidro", "#9fc6e8", opacidade=0.35,
                                               metalico=0.1, rugosidade=0.05)

    # ---- manipulação ----
    def add(self, ent: Entidade) -> Entidade:
        if ent.camada and ent.camada not in self.camadas:
            self.camadas[ent.camada] = Camada(nome=ent.camada)
        self.entidades[ent.id] = ent
        return ent

    def remover(self, id_: str):
        ent = self.entidades.pop(id_, None)
        if isinstance(ent, Grupo):
            for f in ent.filhos:
                self.remover(f)
        return ent

    def get(self, id_: str) -> Optional[Entidade]:
        return self.entidades.get(id_)

    def por_tipo(self, tipo: str) -> List[Entidade]:
        return [e for e in self.entidades.values() if e.tipo == tipo]

    def por_camada(self, camada: str) -> List[Entidade]:
        return [e for e in self.entidades.values() if e.camada == camada]

    @property
    def barras(self) -> List[Barra]:
        return [e for e in self.entidades.values() if isinstance(e, Barra)]

    @property
    def chapas(self) -> List[Chapa]:
        return [e for e in self.entidades.values() if isinstance(e, Chapa)]

    @property
    def solidos(self) -> List[Solido]:
        return [e for e in self.entidades.values() if isinstance(e, Solido)]

    def caixa(self) -> Tuple[Ponto, Ponto]:
        """Caixa envolvente do modelo, em mm."""
        pts: List[Ponto] = []
        for e in self.entidades.values():
            if isinstance(e, Barra):
                pts += [e.inicio, e.fim]
            elif isinstance(e, Chapa):
                for (x, y) in e.contorno or [(0.0, 0.0)]:
                    pts.append(somar(e.origem, somar(escalar(e.eixo_x, x),
                                                     escalar(e.eixo_y, y))))
            elif isinstance(e, Solido):
                pts += e.vertices
        if not pts:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        return (tuple(min(p[i] for p in pts) for i in range(3)),
                tuple(max(p[i] for p in pts) for i in range(3)))

    def estatisticas(self) -> dict:
        return {"entidades": len(self.entidades), "barras": len(self.barras),
                "chapas": len(self.chapas), "solidos": len(self.solidos),
                "camadas": len(self.camadas)}

    # ---- serialização ----
    def dict(self) -> dict:
        return {
            "nome": self.nome, "unidade": self.unidade,
            "entidades": [e.dict() for e in self.entidades.values()],
            "camadas": {k: asdict(v) for k, v in self.camadas.items()},
            "materiais": {k: asdict(v) for k, v in self.materiais.items()},
            "projeto": self.projeto, "metadados": self.metadados,
        }

    @staticmethod
    def de_dict(d: dict) -> "Documento":
        doc = Documento(nome=d.get("nome", "Modelo"), unidade=d.get("unidade", "mm"),
                        projeto=d.get("projeto", {}), metadados=d.get("metadados", {}))
        doc.camadas = {k: Camada(**v) for k, v in (d.get("camadas") or {}).items()}
        doc.materiais = {k: Material(**v) for k, v in (d.get("materiais") or {}).items()}
        if not doc.camadas or not doc.materiais:
            doc.__post_init__()
        classes = {"barra": Barra, "chapa": Chapa, "solido": Solido, "grupo": Grupo}
        for reg in d.get("entidades", []):
            cls = classes.get(reg.get("tipo"), Entidade)
            campos = {f for f in cls.__dataclass_fields__}
            limpo = {k: v for k, v in reg.items() if k in campos}
            for chave in ("inicio", "fim", "origem", "eixo_x", "eixo_y"):
                if chave in limpo and isinstance(limpo[chave], list):
                    limpo[chave] = tuple(limpo[chave])
            if cls is Solido and "vertices" in limpo:
                limpo["vertices"] = [tuple(v) for v in limpo["vertices"]]
            doc.entidades[limpo.get("id", novo_id())] = cls(**limpo)
        return doc
