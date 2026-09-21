# -*- coding: utf-8 -*-
"""Leitura de IFC para o documento 3D (`nucleo3d.modelo.Documento`).

    from ifc.importar import importar, inspecionar
    info = inspecionar("recebido.ifc")     # prévia rápida, sem geometria
    doc = importar("recebido.ifc")
    doc.metadados["importacao"]            # relatório do que entrou e do que faltou

O que o importador entrega, em ordem de valor:

1. **Estrutura de verdade.** Viga, pilar e barra que no IFC são extrusão de um perfil
   paramétrico viram `Barra`, com eixo, comprimento e o perfil do catálogo mais
   próximo (tolerância de 5 % em altura, largura e espessuras). É o que permite
   reabrir, editar e redimensionar um modelo recebido de terceiros em vez de herdar
   uma malha morta. Do mesmo modo, `IfcPlate` extrudado de contorno plano volta como
   `Chapa` (plano, contorno, espessura e furos circulares), e a ida e volta pelo
   exportador preserva o tipo.
2. **Geometria fiel.** O que não é barra vira `Solido` com vértices e faces, a partir
   de extrusão, brep, malha indexada, item mapeado, recorte por meio-espaço e disco
   varrido. O que o módulo não sabe converter vira caixa envolvente **com aviso**, em
   vez de sumir do modelo.
3. **Contexto.** Camadas de apresentação (IfcPresentationLayerAssignment, com cor,
   visibilidade e bloqueio), e na falta delas `Pset_MetalicaCalculo.Camada` ou o
   nome do pavimento; unidades convertidas para milímetro; conjuntos de
   propriedades e quantidades; material de aparência (MaterialAparencia, estilo de
   superfície ou material associado) separado do aço de cálculo (`aco`).

Unidades: o documento é sempre em milímetro. O fator vem de `IfcUnitAssignment`
(arquivo em metro, o caso mais comum, entra multiplicado por 1000).

Eixos: os do arquivo, sem rotação — o IFC também usa Z para cima.

Limitações conhecidas (todas registram aviso no relatório):

* superfícies curvas exatas (`IfcAdvancedBrep`, `IfcBSplineSurface`, `IfcSurfaceOfRevolution`)
  não são tesseladas: o elemento entra como caixa envolvente;
* `IfcBooleanResult` só é resolvido quando o segundo operando é meio-espaço plano;
  subtração de sólido contra sólido usa o primeiro operando;
* raios de concordância e inclinação de mesa dos perfis paramétricos são ignorados na
  malha (a área muda menos de 2 % e o casamento com o catálogo usa as dimensões
  nominais, não a malha);
* a origem dos perfis U, L e T é tomada no centro da caixa envolvente, e não no centro
  de gravidade, o que desloca a seção alguns milímetros em relação ao eixo declarado;
* `IfcOpeningElement` (vãos de porta e janela) é lido mas não subtraído do elemento
  hospedeiro; passe `incluir_aberturas=True` para vê-los como sólidos separados.
"""
import math
import os
import re
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from ifc.step import Arquivo, Entidade, Ref, Tipado, ler                # noqa: E402
from nucleo3d.modelo import (Barra, Camada, Chapa, Documento,          # noqa: E402
                             Material, Solido)

__all__ = ["importar", "inspecionar", "Importador", "LIMITACOES", "camada_semantica",
           "marcas_de", "CAMADAS_SEMANTICAS"]

LIMITACOES = [
    "IfcAdvancedBrep, NURBS e superfícies de revolução entram como caixa envolvente",
    "IfcBooleanResult só é recortado quando o segundo operando é meio-espaço plano",
    "raios de concordância dos perfis paramétricos são ignorados na malha",
    "perfis U, L e T são posicionados pelo centro da caixa envolvente",
    "aberturas (IfcOpeningElement) não são subtraídas do elemento hospedeiro",
]

EPS = 1e-9

# ---- unidades ------------------------------------------------------------
PREFIXOS_SI = {"EXA": 1e18, "PETA": 1e15, "TERA": 1e12, "GIGA": 1e9, "MEGA": 1e6,
               "KILO": 1e3, "HECTO": 1e2, "DECA": 1e1, "DECI": 1e-1, "CENTI": 1e-2,
               "MILLI": 1e-3, "MICRO": 1e-6, "NANO": 1e-9, "PICO": 1e-12,
               "FEMTO": 1e-15, "ATTO": 1e-18}

#: Tipos IFC que não são objetos físicos e não entram no documento.
IGNORADOS = {"IFCANNOTATION", "IFCGRID", "IFCVIRTUALELEMENT", "IFCOPENINGELEMENT",
             "IFCSPACE", "IFCDISTRIBUTIONPORT", "IFCPORT"}

ESPACIAIS = ("IFCPROJECT", "IFCSITE", "IFCBUILDING", "IFCBUILDINGSTOREY",
             "IFCSPACE", "IFCSPATIALZONE", "IFCEXTERNALSPATIALELEMENT")

#: Papel de `Barra` a partir do tipo IFC e do PredefinedType.
PAPEL_POR_TIPO = {"IFCCOLUMN": "pilar", "IFCBEAM": "viga", "IFCMEMBER": "barra"}
PAPEL_POR_PREDEFINIDO = {"PURLIN": "terça", "BRACE": "contraventamento",
                         "POST": "pilar", "COLUMN": "pilar", "RAFTER": "viga",
                         "JOIST": "viga", "STRUT": "contraventamento",
                         "CHORD": "barra", "MULLION": "longarina",
                         "STRINGER": "longarina"}

#: Papéis de `Barra` aceitos como estão quando vêm no ObjectType do elemento.
PAPEIS_CONHECIDOS = {"pilar", "viga", "terça", "terca", "contraventamento", "longarina",
                     "barra", "tirante", "montante", "diagonal", "banzo", "corrente"}

#: Maior diâmetro de seção redonda cheia e maior espessura de seção retangular cheia
#: aceitos como barra de aço (tirante, corrente, barra chata). Acima disso a seção
#: cheia é pilar de concreto ou peça de madeira, e fica sólido. É critério de
#: classificação do importador, não de norma.
LIMITE_REDONDA_MM = 150.0
LIMITE_CHATA_MM = 50.0

#: Grafia bonita dos tipos IFC mais comuns (o arquivo guarda tudo em maiúsculas).
TIPOS_IFC = {}
for _t in ("IfcBeam IfcColumn IfcMember IfcPlate IfcSlab IfcWall IfcWallStandardCase "
           "IfcRoof IfcStair IfcStairFlight IfcRamp IfcRampFlight IfcRailing "
           "IfcCovering IfcCurtainWall IfcWindow IfcDoor IfcFooting IfcPile "
           "IfcBuildingElementProxy IfcFurnishingElement IfcFurniture IfcFlowSegment "
           "IfcFlowFitting IfcFlowTerminal IfcFlowController IfcDistributionElement "
           "IfcElementAssembly IfcMechanicalFastener IfcFastener IfcDiscreteAccessory "
           "IfcReinforcingBar IfcTendon IfcChimney IfcShadingDevice IfcSpace "
           "IfcSite IfcBuilding IfcBuildingStorey IfcProject IfcOpeningElement "
           "IfcTransportElement IfcSanitaryTerminal IfcSlabStandardCase "
           "IfcBeamStandardCase IfcColumnStandardCase IfcMemberStandardCase "
           "IfcPlateStandardCase IfcGeographicElement IfcCivilElement").split():
    TIPOS_IFC[_t.upper()] = _t


def nome_ifc(tipo: str) -> str:
    """'IFCBEAM' -> 'IfcBeam'. Tipo desconhecido volta como veio."""
    return TIPOS_IFC.get(tipo.upper(), tipo)


# =========================================================== álgebra 4×4

Matriz = Tuple[Tuple[float, float, float, float], ...]


def m_identidade() -> Matriz:
    return ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def m_multiplicar(a: Matriz, b: Matriz) -> Matriz:
    """a·b — aplica b primeiro e a depois, como manda a convenção de coluna."""
    return tuple(
        tuple(a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
              for j in range(4))
        for i in range(4))


def m_ponto(m: Matriz, p: Sequence[float]) -> Tuple[float, float, float]:
    x, y, z = p[0], p[1], p[2]
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def m_direcao(m: Matriz, v: Sequence[float]) -> Tuple[float, float, float]:
    """Transforma um vetor: rotação e escala, sem translação."""
    x, y, z = v[0], v[1], v[2]
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z,
            m[1][0] * x + m[1][1] * y + m[1][2] * z,
            m[2][0] * x + m[2][1] * y + m[2][2] * z)


def _norm(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / n, v[1] / n, v[2] / n) if n > EPS else (0.0, 0.0, 1.0)


def _cruz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def m_de_eixos(origem, eixo_z, eixo_x) -> Matriz:
    """Matriz de um sistema local: Z é o eixo principal, X a direção de referência.

    X é ortogonalizado contra Z (Gram-Schmidt), como o IFC manda; Y sai do produto
    vetorial, sempre destro.
    """
    z = _norm(eixo_z or (0.0, 0.0, 1.0))
    x = eixo_x or ((1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0))
    d = _dot(x, z)
    x = (x[0] - d * z[0], x[1] - d * z[1], x[2] - d * z[2])
    if math.sqrt(_dot(x, x)) < 1e-9:           # X paralelo a Z: escolhe outro
        alt = (1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0)
        d = _dot(alt, z)
        x = (alt[0] - d * z[0], alt[1] - d * z[1], alt[2] - d * z[2])
    x = _norm(x)
    y = _cruz(z, x)
    o = origem or (0.0, 0.0, 0.0)
    return ((x[0], y[0], z[0], o[0]),
            (x[1], y[1], z[1], o[1]),
            (x[2], y[2], z[2], o[2]),
            (0.0, 0.0, 0.0, 1.0))


def m_escalar(m: Matriz, sx: float, sy: float, sz: float) -> Matriz:
    """Multiplica as colunas (os eixos) por escalas — usado nos operadores de transformação."""
    return ((m[0][0] * sx, m[0][1] * sy, m[0][2] * sz, m[0][3]),
            (m[1][0] * sx, m[1][1] * sy, m[1][2] * sz, m[1][3]),
            (m[2][0] * sx, m[2][1] * sy, m[2][2] * sz, m[2][3]),
            (0.0, 0.0, 0.0, 1.0))


# =========================================================== malha

class Malha:
    """Vértices e faces em construção, antes de virar `Solido`."""
    __slots__ = ("vertices", "faces", "_indice")

    def __init__(self):
        self.vertices: List[Tuple[float, float, float]] = []
        self.faces: List[List[int]] = []
        self._indice: Dict[Tuple[int, int, int], int] = {}

    # ---- construção ----
    def ponto(self, p) -> int:
        """Índice do vértice, reaproveitando os coincidentes (tolerância de 1 µm)."""
        chave = (int(round(p[0] * 1000)), int(round(p[1] * 1000)), int(round(p[2] * 1000)))
        i = self._indice.get(chave)
        if i is None:
            i = len(self.vertices)
            self._indice[chave] = i
            self.vertices.append((float(p[0]), float(p[1]), float(p[2])))
        return i

    def face(self, pontos):
        """Acrescenta uma face a partir de pontos 3D, descartando repetidos seguidos."""
        idx = []
        for p in pontos:
            i = self.ponto(p)
            if not idx or idx[-1] != i:
                idx.append(i)
        if len(idx) > 2 and idx[0] == idx[-1]:
            idx.pop()
        if len(idx) >= 3:
            self.faces.append(idx)

    def face_indices(self, idx: List[int]):
        limpo = []
        for i in idx:
            if not limpo or limpo[-1] != i:
                limpo.append(i)
        if len(limpo) > 2 and limpo[0] == limpo[-1]:
            limpo.pop()
        if len(limpo) >= 3:
            self.faces.append(limpo)

    def somar(self, outra: "Malha"):
        if outra is None:
            return
        for f in outra.faces:
            self.face([outra.vertices[i] for i in f])

    # ---- consultas ----
    @property
    def vazia(self) -> bool:
        return not self.faces

    def transformada(self, m: Matriz) -> "Malha":
        nova = Malha()
        pts = [m_ponto(m, v) for v in self.vertices]
        for f in self.faces:
            nova.face([pts[i] for i in f])
        return nova

    def caixa(self):
        if not self.vertices:
            return None
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        zs = [v[2] for v in self.vertices]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def volume_assinado(self) -> float:
        v = 0.0
        for f in self.faces:
            a = self.vertices[f[0]]
            for i in range(1, len(f) - 1):
                b, c = self.vertices[f[i]], self.vertices[f[i + 1]]
                v += _dot(a, _cruz(b, c)) / 6.0
        return v

    def orientar(self):
        """Vira as faces para fora, se o volume tiver saído negativo."""
        if self.volume_assinado() < 0:
            self.faces = [list(reversed(f)) for f in self.faces]

    def __repr__(self):
        return "<Malha %d vértices, %d faces>" % (len(self.vertices), len(self.faces))


def caixa_malha(minimo, maximo) -> Malha:
    """Paralelepípedo a partir dos extremos — a geometria de último recurso."""
    (x0, y0, z0), (x1, y1, z1) = minimo, maximo
    for a, b in ((x0, x1), (y0, y1), (z0, z1)):
        if abs(b - a) < 1e-6:
            pass          # caixa achatada ainda é melhor que nada
    m = Malha()
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    for f in ([0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
              [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]):
        m.face([v[i] for i in f])
    return m


# =========================================================== polígonos 2D

def area_assinada(pts) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def anti_horario(pts):
    return list(pts) if area_assinada(pts) >= 0 else list(reversed(pts))


def horario(pts):
    return list(pts) if area_assinada(pts) <= 0 else list(reversed(pts))


def juntar_furos(externo, furos):
    """Costura cada furo ao contorno externo por um corte de ida e volta.

    O resultado é um polígono simples, fechado, que qualquer triangulação em leque
    resolve — e cuja área assinada continua sendo área menos furos.
    """
    laco = list(externo)
    for furo in furos:
        f = horario(furo)
        if len(f) < 3:
            continue
        melhor = None
        for i, p in enumerate(laco):
            for j, q in enumerate(f):
                d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                if melhor is None or d < melhor[0]:
                    melhor = (d, i, j)
        _, i, j = melhor
        laco = laco[:i + 1] + f[j:] + f[:j + 1] + laco[i:]
    return laco


def poligono_circulo(raio: float, n: int, cx=0.0, cy=0.0):
    return [(cx + raio * math.cos(2 * math.pi * k / n),
             cy + raio * math.sin(2 * math.pi * k / n)) for k in range(n)]


# =========================================================== importador

class Importador:
    """Converte um `Arquivo` STEP já lido em `Documento`.

    Normalmente não se instancia à mão: use `importar(caminho)`.
    """

    def __init__(self, arquivo: Arquivo, **opcoes):
        self.arq = arquivo
        self.op = {
            "estrutural": True,          # tentar reconhecer Barra
            "tolerancia_perfil": 0.05,   # 5 % em cada dimensão
            "segmentos_circulo": 24,
            "incluir_aberturas": False,
            "incluir_espacos": False,
            "camada_padrao": "Importado",
            "max_avisos": 200,
            "nome": None,
        }
        self.op.update(opcoes)

        self.escala = 1000.0             # fator do arquivo para milímetro
        self.unidade_origem = "metro"
        self.angulo = 1.0                # fator do ângulo do arquivo para radiano
        self.avisos: List[str] = []
        self.nao_suportados: Dict[str, int] = {}
        self.contagem: Dict[str, int] = {}
        self.perfis_casados: List[dict] = []
        self.sem_perfil: List[dict] = []
        self.chapas_reconhecidas: List[dict] = []
        self.barras_como_solido: List[dict] = []
        self._camada_de: Dict[int, str] = {}      # representação ou item -> camada
        self.camadas_ifc: List[dict] = []
        self.origem_camada: Dict[str, int] = {}
        self.ignorados: Dict[str, int] = {}
        self._cache_matriz: Dict[int, Matriz] = {}
        self._cache_mapa: Dict[int, Malha] = {}
        self._props: Dict[int, List[Entidade]] = {}
        self._materiais: Dict[int, Entidade] = {}
        self._agregados: Dict[int, List[int]] = {}
        self._contidos: Dict[int, List[int]] = {}
        self._cor_material: Dict[int, Tuple[str, float]] = {}
        self._vistos: set = set()
        self.doc = Documento(nome=self.op["nome"] or "Importado")
        self._banco = None

    # ------------------------------------------------------------ diagnóstico
    def avisar(self, msg: str):
        if len(self.avisos) < self.op["max_avisos"]:
            self.avisos.append(msg)
        elif len(self.avisos) == self.op["max_avisos"]:
            self.avisos.append("... mais avisos omitidos")

    def nao_suportado(self, tipo: str, detalhe: str = ""):
        self.nao_suportados[tipo] = self.nao_suportados.get(tipo, 0) + 1
        if self.nao_suportados[tipo] <= 3:
            self.avisar("geometria não suportada: %s%s — usada a caixa envolvente"
                        % (nome_ifc(tipo), (" (%s)" % detalhe) if detalhe else ""))

    # ------------------------------------------------------------ atalhos
    def res(self, ref) -> Optional[Entidade]:
        return self.arq.resolver(ref)

    def lista(self, refs) -> List[Entidade]:
        return self.arq.resolver_lista(refs)

    # ------------------------------------------------------------ unidades
    def ler_unidades(self):
        """Lê `IfcUnitAssignment` e fixa o fator de conversão para milímetro."""
        atrib = None
        projetos = self.arq.por_tipo("IFCPROJECT")
        if projetos:
            atrib = self.res(projetos[0].arg(8))
        if atrib is None:
            lista = self.arq.por_tipo("IFCUNITASSIGNMENT")
            atrib = lista[0] if lista else None
        if atrib is None:
            self.avisar("arquivo sem IfcUnitAssignment: assumido metro")
            return
        for u in self.lista(atrib.arg(0)):
            tipo_grandeza = str(u.arg(1) or "")
            fator = self._fator_unidade(u)
            if fator is None:
                continue
            if tipo_grandeza == "LENGTHUNIT":
                self.escala = fator * 1000.0      # fator vem em metros
                self.unidade_origem = self._nome_unidade(u)
            elif tipo_grandeza == "PLANEANGLEUNIT":
                self.angulo = fator               # fator vem em radianos
        if abs(self.escala) < 1e-12:
            self.avisar("unidade de comprimento inválida: assumido metro")
            self.escala = 1000.0

    def _fator_unidade(self, u: Entidade) -> Optional[float]:
        """Fator da unidade para a unidade SI base (metro ou radiano)."""
        if u.e_tipo("IFCSIUNIT"):
            prefixo = str(u.arg(2) or "")
            return PREFIXOS_SI.get(prefixo, 1.0)
        if u.e_tipo("IFCCONVERSIONBASEDUNIT", "IFCCONVERSIONBASEDUNITWITHOFFSET"):
            medida = self.res(u.arg(3))
            if medida is None:
                return None
            valor = medida.arg(0)
            if isinstance(valor, Tipado):
                valor = valor.valor
            base = self.res(medida.arg(1))
            fator_base = self._fator_unidade(base) if base is not None else 1.0
            try:
                return float(valor) * (fator_base if fator_base else 1.0)
            except (TypeError, ValueError):
                return None
        return None

    def _nome_unidade(self, u: Entidade) -> str:
        if u.e_tipo("IFCSIUNIT"):
            prefixo = str(u.arg(2) or "").lower()
            nome = str(u.arg(3) or "METRE").lower()
            traducao = {"metre": "metro"}
            pref = {"milli": "milí", "centi": "centí", "deci": "decí", "kilo": "quilô"}
            return (pref.get(prefixo, "") + traducao.get(nome, nome)) if prefixo else \
                traducao.get(nome, nome)
        return str(u.arg(2) or "unidade convertida")

    # ------------------------------------------------------------ pontos e eixos
    def ponto(self, ref) -> Tuple[float, float, float]:
        """`IfcCartesianPoint` em milímetro (completa com zero em 2D)."""
        e = self.res(ref)
        if e is None:
            return (0.0, 0.0, 0.0)
        c = e.arg(0) or []
        k = self.escala
        x = float(c[0]) * k if len(c) > 0 else 0.0
        y = float(c[1]) * k if len(c) > 1 else 0.0
        z = float(c[2]) * k if len(c) > 2 else 0.0
        return (x, y, z)

    def direcao(self, ref, padrao=None):
        """`IfcDirection` normalizado; None quando o argumento está omitido."""
        e = self.res(ref)
        if e is None:
            return padrao
        c = e.arg(0) or []
        v = (float(c[0]) if len(c) > 0 else 0.0,
             float(c[1]) if len(c) > 1 else 0.0,
             float(c[2]) if len(c) > 2 else 0.0)
        if abs(v[0]) < EPS and abs(v[1]) < EPS and abs(v[2]) < EPS:
            return padrao
        return _norm(v)

    def matriz(self, ref) -> Matriz:
        """Matriz 4×4 de qualquer colocação: placement local, eixo 3D, eixo 2D."""
        e = self.res(ref)
        if e is None:
            return m_identidade()
        guardada = self._cache_matriz.get(e.id)
        if guardada is not None:
            return guardada
        self._cache_matriz[e.id] = m_identidade()     # corta recursão cíclica
        m = self._matriz_de(e)
        self._cache_matriz[e.id] = m
        return m

    def _matriz_de(self, e: Entidade) -> Matriz:
        t = e.tipos
        if "IFCLOCALPLACEMENT" in t:
            rel = e.arg(0)
            local = self.matriz(e.arg(1))
            if rel is not None:
                pai = self.res(rel)
                if pai is None:
                    self.avisar("IfcLocalPlacement #%d é relativo a %s, que não existe "
                                "no arquivo: usada só a colocação local" % (e.id, rel))
                else:
                    return m_multiplicar(self.matriz(rel), local)
            return local
        if "IFCAXIS2PLACEMENT3D" in t:
            return m_de_eixos(self.ponto(e.arg(0)), self.direcao(e.arg(1)),
                              self.direcao(e.arg(2)))
        if "IFCAXIS2PLACEMENT2D" in t:
            d = self.direcao(e.arg(1), (1.0, 0.0, 0.0))
            o = self.ponto(e.arg(0))
            return m_de_eixos(o, (0.0, 0.0, 1.0), (d[0], d[1], 0.0))
        if "IFCAXIS1PLACEMENT" in t:
            return m_de_eixos(self.ponto(e.arg(0)), self.direcao(e.arg(1)), None)
        if "IFCGRIDPLACEMENT" in t:
            self.avisar("IfcGridPlacement não é resolvido: elemento fica na origem")
            return m_identidade()
        if "IFCCARTESIANTRANSFORMATIONOPERATOR3D" in t or \
           "IFCCARTESIANTRANSFORMATIONOPERATOR3DNONUNIFORM" in t or \
           "IFCCARTESIANTRANSFORMATIONOPERATOR2D" in t or \
           "IFCCARTESIANTRANSFORMATIONOPERATOR2DNONUNIFORM" in t:
            return self._matriz_operador(e)
        self.avisar("colocação desconhecida: %s" % nome_ifc(e.tipo))
        return m_identidade()

    def _matriz_operador(self, e: Entidade) -> Matriz:
        bidim = "2D" in e.tipo
        x = self.direcao(e.arg(0))
        if bidim:
            z = (0.0, 0.0, 1.0)
            origem = self.ponto(e.arg(2))
            escala = e.arg(3)
            escalas = (escala, e.arg(4), None) if "NONUNIFORM" in e.tipo else (escala,) * 3
        else:
            z = self.direcao(e.arg(4))
            origem = self.ponto(e.arg(2))
            escala = e.arg(3)
            escalas = ((escala, e.arg(5), e.arg(6)) if "NONUNIFORM" in e.tipo
                       else (escala,) * 3)
        m = m_de_eixos(origem, z, x)
        s = [float(v) if isinstance(v, (int, float)) else 1.0 for v in escalas]
        s = [v if abs(v) > EPS else 1.0 for v in s]
        if s != [1.0, 1.0, 1.0]:
            m = m_escalar(m, s[0], s[1], s[2])
        return m

    # ------------------------------------------------------------ curvas
    def pontos_curva_2d(self, ref) -> List[Tuple[float, float]]:
        """Aproxima qualquer curva plana fechada por uma poligonal, em milímetro."""
        e = self.res(ref)
        if e is None:
            return []
        t = e.tipos
        n = max(8, int(self.op["segmentos_circulo"]))
        if "IFCPOLYLINE" in t:
            pts = [self.ponto(p)[:2] for p in (e.arg(0) or [])]
            if len(pts) > 1 and _quase_igual2(pts[0], pts[-1]):
                pts.pop()
            return pts
        if "IFCINDEXEDPOLYCURVE" in t:
            return self._poly_indexada(e)
        if "IFCCOMPOSITECURVE" in t or "IFCCOMPOSITECURVEONSURFACE" in t:
            pts: List[Tuple[float, float]] = []
            for seg in self.lista(e.arg(0)):
                parte = self.pontos_curva_2d(seg.arg(2))
                if seg.arg(1) is False:
                    parte = list(reversed(parte))
                if pts and parte and _quase_igual2(pts[-1], parte[0]):
                    parte = parte[1:]
                pts.extend(parte)
            if len(pts) > 1 and _quase_igual2(pts[0], pts[-1]):
                pts.pop()
            return pts
        if "IFCTRIMMEDCURVE" in t:
            return self._curva_aparada(e)
        if "IFCCIRCLE" in t:
            m = self.matriz(e.arg(0))
            r = float(e.arg(1) or 0.0) * self.escala
            return [m_ponto(m, (p[0], p[1], 0.0))[:2] for p in poligono_circulo(r, n)]
        if "IFCELLIPSE" in t:
            m = self.matriz(e.arg(0))
            a = float(e.arg(1) or 0.0) * self.escala
            b = float(e.arg(2) or 0.0) * self.escala
            return [m_ponto(m, (a * math.cos(2 * math.pi * k / n),
                                b * math.sin(2 * math.pi * k / n), 0.0))[:2]
                    for k in range(n)]
        if "IFCLINE" in t:
            return []
        self.avisar("curva não suportada no perfil: %s" % nome_ifc(e.tipo))
        return []

    def _poly_indexada(self, e: Entidade) -> List[Tuple[float, float]]:
        lista_pontos = self.res(e.arg(0))
        if lista_pontos is None:
            return []
        coords = [(float(c[0]) * self.escala, float(c[1]) * self.escala)
                  for c in (lista_pontos.arg(0) or []) if len(c) >= 2]
        segmentos = e.arg(1)
        if not segmentos:
            return coords
        pts: List[Tuple[float, float]] = []
        for seg in segmentos:
            if not isinstance(seg, Tipado):
                continue
            idx = seg.args[0] if seg.args else []
            if isinstance(idx, list) and idx and isinstance(idx[0], list):
                idx = idx[0]
            try:
                p = [coords[int(i) - 1] for i in idx]
            except (IndexError, ValueError, TypeError):
                continue
            if seg.tipo == "IFCARCINDEX" and len(p) == 3:
                p = _arco_por_tres(p[0], p[1], p[2],
                                   max(4, self.op["segmentos_circulo"] // 2))
            if pts and p and _quase_igual2(pts[-1], p[0]):
                p = p[1:]
            pts.extend(p)
        if len(pts) > 1 and _quase_igual2(pts[0], pts[-1]):
            pts.pop()
        return pts

    def _curva_aparada(self, e: Entidade) -> List[Tuple[float, float]]:
        base = self.res(e.arg(0))
        if base is None:
            return []
        sentido = e.arg(3)
        sentido = True if sentido is None else bool(sentido)
        if base.e_tipo("IFCCIRCLE"):
            m = self.matriz(base.arg(0))
            r = float(base.arg(1) or 0.0) * self.escala
            a1 = self._parametro_trim(e.arg(1), m, r)
            a2 = self._parametro_trim(e.arg(2), m, r)
            if a1 is None or a2 is None:
                return [m_ponto(m, (p[0], p[1], 0.0))[:2]
                        for p in poligono_circulo(r, self.op["segmentos_circulo"])]
            if sentido:
                while a2 < a1:
                    a2 += 2 * math.pi
            else:
                while a2 > a1:
                    a2 -= 2 * math.pi
            n = max(2, int(abs(a2 - a1) / (2 * math.pi) *
                           self.op["segmentos_circulo"]) + 1)
            return [m_ponto(m, (r * math.cos(a1 + (a2 - a1) * k / n),
                                r * math.sin(a1 + (a2 - a1) * k / n), 0.0))[:2]
                    for k in range(n + 1)]
        if base.e_tipo("IFCLINE"):
            p1 = self._ponto_trim(e.arg(1))
            p2 = self._ponto_trim(e.arg(2))
            if p1 and p2:
                return [p1[:2], p2[:2]]
            return []
        if base.e_tipo("IFCPOLYLINE"):
            return self.pontos_curva_2d(base.id)
        self.avisar("curva aparada sobre %s não é suportada" % nome_ifc(base.tipo))
        return []

    def _parametro_trim(self, trim, m: Matriz, raio: float) -> Optional[float]:
        """Ângulo (rad) de um Trim, seja parâmetro ou ponto cartesiano."""
        if not trim:
            return None
        itens = trim if isinstance(trim, list) else [trim]
        for it in itens:
            if isinstance(it, Tipado) and it.tipo == "IFCPARAMETERVALUE":
                try:
                    return float(it.valor) * self.angulo
                except (TypeError, ValueError):
                    continue
        for it in itens:
            e = self.res(it)
            if e is not None and e.e_tipo("IFCCARTESIANPOINT"):
                p = self.ponto(e.id)
                inv = _inversa_rigida(m)
                lx, ly, _ = m_ponto(inv, p)
                return math.atan2(ly, lx)
        return None

    def _ponto_trim(self, trim):
        itens = trim if isinstance(trim, list) else [trim]
        for it in itens:
            e = self.res(it)
            if e is not None and e.e_tipo("IFCCARTESIANPOINT"):
                return self.ponto(e.id)
        return None

    def pontos_curva_3d(self, ref) -> List[Tuple[float, float, float]]:
        """Poligonal 3D de uma diretriz (varredura de tubo, por exemplo)."""
        e = self.res(ref)
        if e is None:
            return []
        t = e.tipos
        if "IFCPOLYLINE" in t:
            pts = [self.ponto(p) for p in (e.arg(0) or [])]
            return pts
        if "IFCCOMPOSITECURVE" in t:
            pts: List[Tuple[float, float, float]] = []
            for seg in self.lista(e.arg(0)):
                parte = self.pontos_curva_3d(seg.arg(2))
                if seg.arg(1) is False:
                    parte = list(reversed(parte))
                if pts and parte and _quase_igual3(pts[-1], parte[0]):
                    parte = parte[1:]
                pts.extend(parte)
            return pts
        if "IFCTRIMMEDCURVE" in t:
            base = self.res(e.arg(0))
            if base is not None and base.e_tipo("IFCLINE"):
                p1, p2 = self._ponto_trim(e.arg(1)), self._ponto_trim(e.arg(2))
                if p1 and p2:
                    return [p1, p2]
            plana = self.pontos_curva_2d(ref)
            return [(p[0], p[1], 0.0) for p in plana]
        if "IFCINDEXEDPOLYCURVE" in t:
            lp = self.res(e.arg(0))
            if lp is not None:
                k = self.escala
                return [(float(c[0]) * k, float(c[1]) * k,
                         float(c[2]) * k if len(c) > 2 else 0.0)
                        for c in (lp.arg(0) or [])]
        plana = self.pontos_curva_2d(ref)
        return [(p[0], p[1], 0.0) for p in plana]

    # ------------------------------------------------------------ perfis
    def perfil_2d(self, ref):
        """Contorno externo, furos e ficha do perfil, em milímetro.

        Devolve `(externo, furos, info)`. `info` traz as dimensões nominais usadas
        para casar com o catálogo: família, d, bf, tw, tf e o nome declarado.
        """
        e = self.res(ref)
        if e is None:
            return [], [], {}
        t = e.tipo
        nome = e.arg(1) or ""
        k = self.escala
        n = max(8, int(self.op["segmentos_circulo"]))
        info = {"familia": "", "nome": str(nome) if nome else "", "ifc": nome_ifc(t)}
        ext: List[Tuple[float, float]] = []
        furos: List[List[Tuple[float, float]]] = []

        def d(i, padrao=0.0):
            v = e.arg(i)
            try:
                return float(v) * k
            except (TypeError, ValueError):
                return padrao

        if t == "IFCRECTANGLEPROFILEDEF" or t == "IFCROUNDEDRECTANGLEPROFILEDEF":
            bx, by = d(3) / 2.0, d(4) / 2.0
            ext = [(-bx, -by), (bx, -by), (bx, by), (-bx, by)]
            info.update(familia="retangulo", d=2 * by, bf=2 * bx, tw=0.0, tf=0.0)
        elif t == "IFCRECTANGLEHOLLOWPROFILEDEF":
            bx, by, esp = d(3) / 2.0, d(4) / 2.0, d(5)
            ext = [(-bx, -by), (bx, -by), (bx, by), (-bx, by)]
            if esp > 0 and bx > esp and by > esp:
                ix, iy = bx - esp, by - esp
                furos = [[(-ix, -iy), (ix, -iy), (ix, iy), (-ix, iy)]]
            info.update(familia="tubo_retangular", d=2 * by, bf=2 * bx, tw=esp, tf=esp)
        elif t == "IFCCIRCLEPROFILEDEF":
            r = d(3)
            ext = poligono_circulo(r, n)
            info.update(familia="circulo", d=2 * r, bf=2 * r, tw=0.0, tf=0.0)
        elif t == "IFCCIRCLEHOLLOWPROFILEDEF":
            r, esp = d(3), d(4)
            ext = poligono_circulo(r, n)
            if 0 < esp < r:
                furos = [poligono_circulo(r - esp, n)]
            info.update(familia="tubo_circular", d=2 * r, bf=2 * r, tw=esp, tf=esp)
        elif t == "IFCISHAPEPROFILEDEF" or t == "IFCASYMMETRICISHAPEPROFILEDEF":
            bf, h, tw, tf = d(3), d(4), d(5), d(6)
            ext = _poligono_i(bf, h, tw, tf)
            info.update(familia="I", d=h, bf=bf, tw=tw, tf=tf)
        elif t == "IFCUSHAPEPROFILEDEF":
            h, bf, tw, tf = d(3), d(4), d(5), d(6)
            ext = _poligono_u(bf, h, tw, tf)
            info.update(familia="U", d=h, bf=bf, tw=tw, tf=tf)
        elif t == "IFCCSHAPEPROFILEDEF":
            h, bf, esp, lab = d(3), d(4), d(5), d(6)
            ext = _poligono_c(bf, h, esp, lab)
            info.update(familia="Ue", d=h, bf=bf, tw=esp, tf=esp)
        elif t == "IFCLSHAPEPROFILEDEF":
            h = d(3)
            b = d(4) or h
            esp = d(5)
            ext = _poligono_l(b, h, esp)
            info.update(familia="L", d=h, bf=b, tw=esp, tf=esp)
        elif t == "IFCTSHAPEPROFILEDEF":
            h, bf, tw, tf = d(3), d(4), d(5), d(6)
            ext = _poligono_t(bf, h, tw, tf)
            info.update(familia="T", d=h, bf=bf, tw=tw, tf=tf)
        elif t == "IFCZSHAPEPROFILEDEF":
            h, bf, tw, tf = d(3), d(4), d(5), d(6)
            ext = _poligono_z(bf, h, tw, tf)
            info.update(familia="Z", d=h, bf=bf, tw=tw, tf=tf)
        elif t in ("IFCARBITRARYCLOSEDPROFILEDEF", "IFCARBITRARYPROFILEDEFWITHVOIDS"):
            ext = self.pontos_curva_2d(e.arg(2))
            if t == "IFCARBITRARYPROFILEDEFWITHVOIDS":
                for c in (e.arg(3) or []):
                    f = self.pontos_curva_2d(c)
                    if len(f) >= 3:
                        furos.append(f)
            info.update(familia="livre")
            return _fechar(ext), [_fechar(f) for f in furos], info
        elif t == "IFCDERIVEDPROFILEDEF":
            pai_ext, pai_furos, pai_info = self.perfil_2d(e.arg(2))
            m = self.matriz(e.arg(3))
            trans = lambda p: m_ponto(m, (p[0], p[1], 0.0))[:2]   # noqa: E731
            info.update(pai_info)
            info["familia"] = pai_info.get("familia", "livre")
            if not info.get("nome"):
                info["nome"] = str(e.arg(4) or pai_info.get("nome", ""))
            return ([trans(p) for p in pai_ext],
                    [[trans(p) for p in f] for f in pai_furos], info)
        elif t == "IFCCENTERLINEPROFILEDEF":
            eixo = self.pontos_curva_2d(e.arg(2))
            esp = d(3)
            ext = _engrossar_linha(eixo, esp)
            info.update(familia="livre")
        elif t == "IFCCOMPOSITEPROFILEDEF":
            for sub in self.lista(e.arg(2)):
                sext, sfuros, sinfo = self.perfil_2d(sub.id)
                if sext:
                    if not ext:
                        ext, furos, info = sext, sfuros, sinfo
                    else:
                        self.avisar("perfil composto: só a primeira seção foi usada")
            return _fechar(ext), furos, info
        else:
            self.avisar("perfil não suportado: %s" % nome_ifc(t))
            return [], [], info

        # posição local do perfil paramétrico (IfcAxis2Placement2D)
        pos = e.arg(2)
        if pos is not None and t != "IFCARBITRARYCLOSEDPROFILEDEF":
            m = self.matriz(pos)
            if m != m_identidade():
                ext = [m_ponto(m, (p[0], p[1], 0.0))[:2] for p in ext]
                furos = [[m_ponto(m, (p[0], p[1], 0.0))[:2] for p in f] for f in furos]
        return _fechar(ext), [_fechar(f) for f in furos], info

    # ------------------------------------------------------------ itens de geometria
    def malha_do_item(self, ref, profundidade=0) -> Optional[Malha]:
        """Converte um item de representação em malha, no sistema da representação."""
        e = self.res(ref)
        if e is None:
            self.avisar("item de representação %s não existe no arquivo" % ref)
            return None
        if profundidade > 12:
            self.avisar("geometria aninhada demais em %s" % nome_ifc(e.tipo))
            return None
        t = e.tipo
        try:
            if t in ("IFCEXTRUDEDAREASOLID", "IFCEXTRUDEDAREASOLIDTAPERED"):
                return self._extrusao(e)
            if t == "IFCREVOLVEDAREASOLID":
                return self._revolucao(e)
            if t in ("IFCFACETEDBREP", "IFCFACETEDBREPWITHVOIDS", "IFCMANIFOLDSOLIDBREP",
                     "IFCCLOSEDSHELL", "IFCOPENSHELL", "IFCCONNECTEDFACESET"):
                return self._brep(e)
            if t in ("IFCSHELLBASEDSURFACEMODEL", "IFCFACEBASEDSURFACEMODEL"):
                m = Malha()
                for casca in self.lista(e.arg(0)):
                    parcial = self._brep(casca)
                    if parcial:
                        m.somar(parcial)
                return m if not m.vazia else None
            if t == "IFCPOLYGONALFACESET":
                return self._malha_poligonal(e)
            if t == "IFCTRIANGULATEDFACESET":
                return self._malha_triangulada(e)
            if t == "IFCMAPPEDITEM":
                return self._item_mapeado(e, profundidade)
            if t in ("IFCBOOLEANCLIPPINGRESULT", "IFCBOOLEANRESULT"):
                return self._booleano(e, profundidade)
            if t == "IFCSWEPTDISKSOLID" or t == "IFCSWEPTDISKSOLIDPOLYGONAL":
                return self._disco_varrido(e)
            if t == "IFCBOUNDINGBOX":
                canto = self.ponto(e.arg(0))
                dx = float(e.arg(1) or 0.0) * self.escala
                dy = float(e.arg(2) or 0.0) * self.escala
                dz = float(e.arg(3) or 0.0) * self.escala
                return caixa_malha(canto, (canto[0] + dx, canto[1] + dy, canto[2] + dz))
            if t == "IFCCSGSOLID":
                return self.malha_do_item(e.arg(0), profundidade + 1)
            if t in ("IFCGEOMETRICSET", "IFCGEOMETRICCURVESET", "IFCPOLYLINE",
                     "IFCTEXTLITERAL", "IFCTEXTLITERALWITHEXTENT", "IFCCARTESIANPOINT",
                     "IFCANNOTATIONFILLAREA", "IFCINDEXEDPOLYCURVE", "IFCCIRCLE",
                     "IFCTRIMMEDCURVE", "IFCCOMPOSITECURVE"):
                return None          # curva ou anotação: não é sólido, não é falha
        except (TypeError, ValueError, IndexError, AttributeError, ZeroDivisionError) as erro:
            self.avisar("falha ao converter %s #%d: %s" % (nome_ifc(t), e.id, erro))
            return self._caixa_de_recurso(e, t)
        return self._caixa_de_recurso(e, t)

    def _caixa_de_recurso(self, e: Entidade, tipo: str) -> Optional[Malha]:
        """Último recurso: a caixa envolvente dos pontos alcançáveis pelo item."""
        self.nao_suportado(tipo)
        pontos = self._pontos_alcancaveis(e)
        if len(pontos) < 2:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        zs = [p[2] for p in pontos]
        if max(xs) - min(xs) < 1e-6 and max(ys) - min(ys) < 1e-6 and \
                max(zs) - min(zs) < 1e-6:
            return None
        return caixa_malha((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))

    def _pontos_alcancaveis(self, raiz: Entidade, limite=20000):
        """Todos os IfcCartesianPoint que a entidade alcança, já em milímetro."""
        pontos = []
        vistos = set()
        pilha = [raiz.id]
        while pilha and len(pontos) < limite:
            atual = pilha.pop()
            if atual in vistos:
                continue
            vistos.add(atual)
            e = self.arq.entidades.get(atual)
            if e is None:
                continue
            if e.tipo == "IFCCARTESIANPOINT":
                pontos.append(self.ponto(e.id))
                continue
            if e.tipo in ("IFCCARTESIANPOINTLIST3D", "IFCCARTESIANPOINTLIST2D"):
                k = self.escala
                for c in (e.arg(0) or []):
                    pontos.append((float(c[0]) * k, float(c[1]) * k,
                                   float(c[2]) * k if len(c) > 2 else 0.0))
                continue
            pilha_valores = list(e.args)
            while pilha_valores:
                v = pilha_valores.pop()
                if type(v) is Ref:
                    pilha.append(int(v))
                elif isinstance(v, list):
                    pilha_valores.extend(v)
                elif isinstance(v, Tipado):
                    pilha_valores.extend(v.args)
        return pontos

    # ---- extrusão ----
    def _extrusao(self, e: Entidade) -> Optional[Malha]:
        ext, furos, _info = self.perfil_2d(e.arg(0))
        if len(ext) < 3:
            return None
        pos = self.matriz(e.arg(1))
        direcao = self.direcao(e.arg(2), (0.0, 0.0, 1.0))
        prof = float(e.arg(3) or 0.0) * self.escala
        if abs(prof) < 1e-9:
            return None
        m = _prisma(ext, furos, direcao, prof)
        return m.transformada(pos)

    def _revolucao(self, e: Entidade) -> Optional[Malha]:
        ext, furos, _ = self.perfil_2d(e.arg(0))
        if len(ext) < 3:
            return None
        pos = self.matriz(e.arg(1))
        eixo = self.res(e.arg(2))
        origem = self.ponto(eixo.arg(0)) if eixo is not None else (0.0, 0.0, 0.0)
        direcao = self.direcao(eixo.arg(1), (0.0, 0.0, 1.0)) if eixo is not None \
            else (0.0, 0.0, 1.0)
        angulo = float(e.arg(3) or 0.0) * self.angulo
        if abs(angulo) < 1e-9:
            return None
        if furos:
            self.avisar("furos do perfil ignorados em IfcRevolvedAreaSolid")
        n = max(6, int(self.op["segmentos_circulo"] * abs(angulo) / (2 * math.pi)) + 2)
        aneis = []
        for k in range(n + 1):
            a = angulo * k / n
            aneis.append([_girar((p[0], p[1], 0.0), origem, direcao, a) for p in ext])
        m = Malha()
        for k in range(n):
            a, b = aneis[k], aneis[k + 1]
            for i in range(len(ext)):
                j = (i + 1) % len(ext)
                m.face([a[i], a[j], b[j], b[i]])
        if abs(abs(angulo) - 2 * math.pi) > 1e-6:
            m.face(aneis[0])
            m.face(list(reversed(aneis[-1])))
        m.orientar()
        return m.transformada(pos)

    # ---- brep e malhas ----
    def _brep(self, e: Entidade) -> Optional[Malha]:
        t = e.tipos
        if "IFCFACETEDBREP" in t or "IFCFACETEDBREPWITHVOIDS" in t or \
                "IFCMANIFOLDSOLIDBREP" in t:
            cascas = [self.res(e.arg(0))]
            if "IFCFACETEDBREPWITHVOIDS" in t:
                cascas += self.lista(e.arg(1))
        else:
            cascas = [e]
        m = Malha()
        for casca in cascas:
            if casca is None:
                continue
            for face in self.lista(casca.arg(0)):
                self._face_brep(face, m)
        return m if not m.vazia else None

    def _face_brep(self, face: Entidade, m: Malha):
        if not face.e_tipo("IFCFACE", "IFCFACESURFACE", "IFCADVANCEDFACE"):
            return
        externo: List[Tuple[float, float, float]] = []
        internos: List[List[Tuple[float, float, float]]] = []
        for bound in self.lista(face.arg(0)):
            laco = self.res(bound.arg(0))
            if laco is None:
                continue
            if not laco.e_tipo("IFCPOLYLOOP"):
                if laco.e_tipo("IFCEDGELOOP"):
                    pts = self._laco_de_arestas(laco)
                else:
                    self.avisar("contorno de face não poligonal: %s" % nome_ifc(laco.tipo))
                    continue
            else:
                pts = [self.ponto(p) for p in (laco.arg(0) or [])]
            if len(pts) < 3:
                continue
            if bound.arg(1) is False:
                pts = list(reversed(pts))
            if bound.e_tipo("IFCFACEOUTERBOUND") or not externo:
                externo = pts
            else:
                internos.append(pts)
        if len(externo) < 3:
            return
        if internos:
            # furo na face: costura no plano dominante da face
            plano = _eixo_dominante(externo)
            achatar = lambda p: (p[(plano + 1) % 3], p[(plano + 2) % 3])  # noqa: E731
            ext2 = [achatar(p) for p in externo]
            mapa = {}
            for p2, p3 in zip(ext2, externo):
                mapa[(round(p2[0], 4), round(p2[1], 4))] = p3
            furos2 = []
            for laco in internos:
                f2 = [achatar(p) for p in laco]
                for p2, p3 in zip(f2, laco):
                    mapa[(round(p2[0], 4), round(p2[1], 4))] = p3
                furos2.append(f2)
            unido = juntar_furos(anti_horario(ext2) if area_assinada(ext2) >= 0
                                 else list(reversed(ext2)), furos2)
            pts3 = [mapa.get((round(p[0], 4), round(p[1], 4))) for p in unido]
            if all(p is not None for p in pts3):
                if area_assinada(ext2) < 0:
                    pts3 = list(reversed(pts3))
                m.face(pts3)
                return
            self.avisar("face com furo não pôde ser costurada; furo ignorado")
        m.face(externo)

    def _laco_de_arestas(self, laco: Entidade):
        pts = []
        for orientada in self.lista(laco.arg(0)):
            aresta = self.res(orientada.arg(2)) if len(orientada) > 2 else None
            if aresta is None:
                continue
            for i in (0, 1):
                v = self.res(aresta.arg(i))
                if v is not None and v.e_tipo("IFCVERTEXPOINT"):
                    p = self.res(v.arg(0))
                    if p is not None and p.e_tipo("IFCCARTESIANPOINT"):
                        q = self.ponto(p.id)
                        if not pts or not _quase_igual3(pts[-1], q):
                            pts.append(q)
        return pts

    def _malha_poligonal(self, e: Entidade) -> Optional[Malha]:
        coords = self._lista_de_pontos(e.arg(0))
        if not coords:
            return None
        pn = e.arg(3) or []
        m = Malha()
        for face in self.lista(e.arg(2)):
            idx = face.arg(0) or []
            pts = _indices_para_pontos(idx, coords, pn)
            if len(pts) < 3:
                continue
            internos = []
            if face.e_tipo("IFCINDEXEDPOLYGONALFACEWITHVOIDS"):
                for v in (face.arg(1) or []):
                    fp = _indices_para_pontos(v, coords, pn)
                    if len(fp) >= 3:
                        internos.append(fp)
            if internos:
                self.avisar("face poligonal com vazio: o vazio foi ignorado")
            m.face(pts)
        return m if not m.vazia else None

    def _malha_triangulada(self, e: Entidade) -> Optional[Malha]:
        coords = self._lista_de_pontos(e.arg(0))
        if not coords:
            return None
        pn = e.arg(4) or []
        m = Malha()
        for tri in (e.arg(3) or []):
            pts = _indices_para_pontos(tri, coords, pn)
            if len(pts) >= 3:
                m.face(pts)
        return m if not m.vazia else None

    def _lista_de_pontos(self, ref):
        lp = self.res(ref)
        if lp is None:
            return []
        k = self.escala
        return [(float(c[0]) * k, float(c[1]) * k,
                 float(c[2]) * k if len(c) > 2 else 0.0)
                for c in (lp.arg(0) or []) if len(c) >= 2]

    # ---- item mapeado ----
    def _item_mapeado(self, e: Entidade, profundidade: int) -> Optional[Malha]:
        fonte = self.res(e.arg(0))
        if fonte is None:
            self.avisar("IfcMappedItem sem fonte de mapeamento")
            return None
        base = self._cache_mapa.get(fonte.id)
        if base is None:
            base = Malha()
            rep = self.res(fonte.arg(1))
            if rep is not None:
                for item in self.lista(rep.arg(3)):
                    parcial = self.malha_do_item(item.id, profundidade + 1)
                    if parcial:
                        base.somar(parcial)
            origem = self.matriz(fonte.arg(0))
            base = base.transformada(origem) if origem != m_identidade() else base
            self._cache_mapa[fonte.id] = base
        if base.vazia:
            return None
        alvo = self.matriz(e.arg(1))
        return base.transformada(alvo) if alvo != m_identidade() else base

    # ---- booleanos ----
    def _booleano(self, e: Entidade, profundidade: int) -> Optional[Malha]:
        base = self.malha_do_item(e.arg(1), profundidade + 1)
        if base is None or base.vazia:
            return None
        operador = str(e.arg(0) or "DIFFERENCE").upper()
        segundo = self.res(e.arg(2))
        if segundo is None:
            return base
        if operador != "DIFFERENCE":
            self.avisar("operação booleana %s não é resolvida: usada a geometria base"
                        % operador)
            return base
        plano = self._plano_de_meio_espaco(segundo)
        if plano is None:
            self.avisar("recorte por %s não resolvido: usada a geometria base"
                        % nome_ifc(segundo.tipo))
            return base
        origem, normal, dentro_positivo = plano
        cortada, ok = _cortar_por_plano(base, origem, normal, not dentro_positivo)
        if not ok:
            self.avisar("recorte deixou a malha aberta em %s #%d" % (nome_ifc(e.tipo), e.id))
        if cortada is None or cortada.vazia:
            self.avisar("recorte removeria o elemento inteiro: usada a geometria base")
            return base
        return cortada

    def _plano_de_meio_espaco(self, e: Entidade):
        """(origem, normal, o meio-espaço é o lado positivo?) ou None."""
        if not e.e_tipo("IFCHALFSPACESOLID", "IFCPOLYGONALBOUNDEDHALFSPACE",
                        "IFCBOXEDHALFSPACE"):
            return None
        superficie = self.res(e.arg(0))
        if superficie is None or not superficie.e_tipo("IFCPLANE"):
            return None
        m = self.matriz(superficie.arg(0))
        origem = (m[0][3], m[1][3], m[2][3])
        normal = _norm((m[0][2], m[1][2], m[2][2]))
        acordo = e.arg(1)
        acordo = True if acordo is None else bool(acordo)
        if e.e_tipo("IFCPOLYGONALBOUNDEDHALFSPACE"):
            self.avisar("IfcPolygonalBoundedHalfSpace aproximado pelo plano infinito")
        if e.e_tipo("IFCBOXEDHALFSPACE"):
            self.avisar("IfcBoxedHalfSpace aproximado pelo plano infinito")
        # acordo True: o sólido é o lado para onde a normal NÃO aponta
        return origem, normal, not acordo

    # ---- disco varrido ----
    def _disco_varrido(self, e: Entidade) -> Optional[Malha]:
        eixo = self.pontos_curva_3d(e.arg(0))
        eixo = _sem_repetidos3(eixo)
        if len(eixo) < 2:
            return None
        raio = float(e.arg(1) or 0.0) * self.escala
        interno = e.arg(2)
        if interno:
            self.avisar("IfcSweptDiskSolid: o furo interno do tubo foi ignorado")
        if raio <= 0:
            return None
        n = max(6, int(self.op["segmentos_circulo"]) // 2)
        return _varrer_disco(eixo, raio, n)

    # ------------------------------------------------------------ representações
    def representacao_de(self, prod: Entidade):
        """Devolve (representação 'Body' escolhida, todas as representações)."""
        forma = self.res(prod.arg(6))
        if forma is None:
            return None, []
        reps = self.lista(forma.arg(2))
        if not reps:
            return None, []
        corpo = None
        for r in reps:
            ident = str(r.arg(1) or "")
            if ident.lower() == "body":
                corpo = r
                break
        if corpo is None:
            for r in reps:
                ident = str(r.arg(1) or "").lower()
                if ident not in ("axis", "box", "footprint", "annotation", "profile",
                                 "surveypoints"):
                    corpo = r
                    break
        if corpo is None:
            for r in reps:
                if str(r.arg(1) or "").lower() == "box":
                    corpo = r
                    break
        return corpo, reps

    def malha_da_representacao(self, rep: Entidade) -> Optional[Malha]:
        if rep is None:
            return None
        m = Malha()
        # referências cruas: um item que não existe precisa virar aviso com o número
        for ref in (rep.arg(3) or []):
            parcial = self.malha_do_item(ref)
            if parcial and not parcial.vazia:
                m.somar(parcial)
        return m if not m.vazia else None

    # ------------------------------------------------------------ relações
    def indexar_relacoes(self):
        for rel in self.arq.por_tipo("IFCRELAGGREGATES", "IFCRELNESTS"):
            pai = rel.arg(4)
            if pai is None:
                continue
            filhos = [int(f) for f in (rel.arg(5) or []) if isinstance(f, int)]
            self._agregados.setdefault(int(pai), []).extend(filhos)
        for rel in self.arq.por_tipo("IFCRELCONTAINEDINSPATIALSTRUCTURE"):
            estrutura = rel.arg(5)
            if estrutura is None:
                continue
            elementos = [int(f) for f in (rel.arg(4) or []) if isinstance(f, int)]
            self._contidos.setdefault(int(estrutura), []).extend(elementos)
        for rel in self.arq.por_tipo("IFCRELDEFINESBYPROPERTIES"):
            definicao = self.res(rel.arg(5))
            if definicao is None:
                continue
            for obj in (rel.arg(4) or []):
                if isinstance(obj, int):
                    self._props.setdefault(int(obj), []).append(definicao)
        for rel in self.arq.por_tipo("IFCRELASSOCIATESMATERIAL"):
            material = self.res(rel.arg(5))
            if material is None:
                continue
            for obj in (rel.arg(4) or []):
                if isinstance(obj, int):
                    self._materiais[int(obj)] = material

    # ------------------------------------------------------------ camadas
    def ler_camadas(self):
        """IfcPresentationLayerAssignment / IfcPresentationLayerWithStyle -> `Camada`.

        Name é o nome; LayerOn .F. ou LayerFrozen .T. deixam a camada oculta (camada
        congelada não aparece, como no CAD); LayerBlocked .T. — visível mas não
        editável — é o nosso `bloqueada`; a cor vem do IfcSurfaceStyle em
        LayerStyles. `.U.` e atributo omitido valem o padrão (visível, livre). O
        elemento pertence à camada que lista a sua representação, ou um item dela, em
        AssignedItems — é assim que Revit, ArchiCAD e Tekla gravam.
        """
        for camada_ifc in self.arq.por_tipo("IFCPRESENTATIONLAYERASSIGNMENT",
                                            "IFCPRESENTATIONLAYERWITHSTYLE"):
            nome = str(camada_ifc.arg(0) or "").strip()
            if not nome:
                continue
            visivel, bloqueada, cor = True, False, ""
            if camada_ifc.e_tipo("IFCPRESENTATIONLAYERWITHSTYLE"):
                visivel = camada_ifc.arg(4) is not False and camada_ifc.arg(5) is not True
                bloqueada = camada_ifc.arg(6) is True
                achado = self._cor_de_estilos(camada_ifc.arg(7))
                if achado:
                    cor = achado[0]
            itens = [int(r) for r in (camada_ifc.arg(2) or []) if isinstance(r, int)]
            for i in itens:
                self._camada_de.setdefault(i, nome)
            camada = self.doc.camadas.get(nome)
            if camada is None:
                camada = Camada(nome=nome)
                self.doc.camadas[nome] = camada
            if cor:
                camada.cor = cor
            camada.visivel = visivel
            camada.bloqueada = bloqueada
            self.camadas_ifc.append({"nome": nome, "itens": len(itens), "cor": camada.cor,
                                     "visivel": visivel, "bloqueada": bloqueada})

    def camada_apresentacao(self, reps: List[Entidade]) -> str:
        """Camada de apresentação da primeira representação (ou item) atribuída."""
        if not self._camada_de:
            return ""
        for rep in reps:
            if rep.id in self._camada_de:
                return self._camada_de[rep.id]
        for rep in reps:
            for ref in (rep.arg(3) or []):
                if not isinstance(ref, int):
                    continue
                if int(ref) in self._camada_de:
                    return self._camada_de[int(ref)]
                item = self.res(ref)
                if item is None or item.tipo != "IFCMAPPEDITEM":
                    continue
                # geometria reaproveitada: a camada pode estar na fonte do mapa
                fonte = self.res(item.arg(0))
                origem = self.res(fonte.arg(1)) if fonte is not None else None
                if origem is None:
                    continue
                if origem.id in self._camada_de:
                    return self._camada_de[origem.id]
                for sub in (origem.arg(3) or []):
                    if isinstance(sub, int) and int(sub) in self._camada_de:
                        return self._camada_de[int(sub)]
        return ""

    def _camada_do_elemento(self, corpo: Optional[Entidade], todas: List[Entidade],
                            propriedades: dict, camada_espacial: str,
                            tipo: str = "", nome_elemento: str = "") -> str:
        """Camada de apresentação > Pset_MetalicaCalculo.Camada > tipo da peça > pavimento.

        Exportadores de detalhamento (TecnoMETAL, Tekla sem configuração) não escrevem
        camada nenhuma, e um galpão inteiro cairia no nome do pavimento. Nesse caso a
        camada vem do que a peça é — telha, chapa, parafuso, tirante, pilar, viga — que
        é a divisão que o usuário precisa para ocultar as telhas e ver a estrutura."""
        reps = ([corpo] if corpo is not None else []) + [r for r in todas if r is not corpo]
        nome = self.camada_apresentacao(reps)
        origem = "apresentacao"
        if not nome:
            valor = ((propriedades or {}).get("Pset_MetalicaCalculo") or {}).get("Camada")
            nome = valor.strip() if isinstance(valor, str) else ""
            origem = "pset" if nome else ""
        if not nome:
            nome = camada_semantica(tipo, nome_elemento)
            origem = "tipo" if nome else "pavimento"
            if nome and nome not in self.doc.camadas:
                self.doc.camadas[nome] = Camada(nome=nome, cor=CAMADAS_SEMANTICAS[nome])
        self.origem_camada[origem] = self.origem_camada.get(origem, 0) + 1
        return nome or camada_espacial

    def propriedades_de(self, prod: Entidade) -> dict:
        """Conjuntos de propriedades e quantidades, prontos para o painel do editor."""
        fora: Dict[str, dict] = {}
        for definicao in self._props.get(prod.id, ()):
            if definicao.e_tipo("IFCPROPERTYSET"):
                nome = str(definicao.arg(2) or "PropertySet")
                fora.setdefault(nome, {}).update(
                    self._ler_propriedades(definicao.arg(4)))
            elif definicao.e_tipo("IFCELEMENTQUANTITY"):
                nome = str(definicao.arg(2) or "Quantidades")
                fora.setdefault(nome, {}).update(
                    self._ler_quantidades(definicao.arg(5)))
        return fora

    def _ler_propriedades(self, refs) -> dict:
        d = {}
        for p in self.lista(refs):
            nome = str(p.arg(0) or "")
            if not nome:
                continue
            if p.e_tipo("IFCPROPERTYSINGLEVALUE"):
                d[nome] = _valor_simples(p.arg(2))
            elif p.e_tipo("IFCPROPERTYENUMERATEDVALUE"):
                vals = [_valor_simples(v) for v in (p.arg(2) or [])]
                d[nome] = vals[0] if len(vals) == 1 else vals
            elif p.e_tipo("IFCPROPERTYLISTVALUE"):
                d[nome] = [_valor_simples(v) for v in (p.arg(2) or [])]
            elif p.e_tipo("IFCPROPERTYBOUNDEDVALUE"):
                d[nome] = {"min": _valor_simples(p.arg(2)),
                           "max": _valor_simples(p.arg(3))}
            elif p.e_tipo("IFCCOMPLEXPROPERTY"):
                d[nome] = self._ler_propriedades(p.arg(3))
        return d

    def _ler_quantidades(self, refs) -> dict:
        d = {}
        for q in self.lista(refs):
            nome = str(q.arg(0) or "")
            if not nome:
                continue
            valor = q.arg(3)
            if isinstance(valor, (int, float)):
                d[nome] = float(valor)
            elif q.e_tipo("IFCPHYSICALCOMPLEXQUANTITY"):
                d[nome] = self._ler_quantidades(q.arg(2))
        return d

    # ------------------------------------------------------------ materiais
    def material_de(self, prod: Entidade, corpo: Optional[Entidade],
                    propriedades: Optional[dict] = None):
        """(material de aparência, nome do IfcMaterial associado).

        O material do documento é de **aparência** (cor, opacidade); o aço de cálculo
        vai em `aco`. A ordem de decisão:

        1. `Pset_MetalicaCalculo.MaterialAparencia`, que o exportador grava;
        2. o estilo de superfície do próprio elemento (IfcStyledItem nos itens do
           corpo): o nome do IfcSurfaceStyle vira o material, com a cor dele;
        3. o IfcMaterial associado, com a cor da sua representação — mas um aço do
           catálogo sem cor própria vira o material "Aço", porque "ASTM A36" é nome
           de aço, não de aparência.
        """
        calc = (propriedades or {}).get("Pset_MetalicaCalculo") or {}
        aparencia = calc.get("MaterialAparencia")
        aparencia = aparencia.strip() if isinstance(aparencia, str) else ""
        ent = self._materiais.get(prod.id)
        nome_mat, cor_mat, opac_mat = (self._material_nome_cor(ent) if ent is not None
                                       else ("", "", 1.0))
        estilo = self._estilo_da_representacao(corpo) if corpo is not None else None
        if aparencia:
            nome = aparencia
            cor, opacidade = (estilo[1], estilo[2]) if estilo else (cor_mat, opac_mat)
        elif estilo:
            nome = estilo[0] or nome_mat or "Cor %s" % estilo[1]
            cor, opacidade = estilo[1], estilo[2]
        elif nome_mat:
            if not cor_mat and self._aco_do_catalogo(nome_mat):
                nome, cor, opacidade = "Aço", "", 1.0
            else:
                nome, cor, opacidade = nome_mat, cor_mat, opac_mat
        else:
            return "", ""
        self._garantir_material(nome, cor, opacidade, nome_mat)
        return nome, nome_mat

    def _aco_do_catalogo(self, nome: str) -> bool:
        try:
            from nucleo import materiais as mat
            return nome in mat.ACOS
        except Exception:
            return False

    def _garantir_material(self, nome: str, cor: str, opacidade: float, nome_mat: str):
        """Cria o material de aparência, ou atualiza a cor com a que veio do arquivo."""
        m = self.doc.materiais.get(nome)
        if m is None:
            m = Material(nome=nome, cor=cor or "#9aa4b2", opacidade=opacidade)
            texto = (nome + " " + nome_mat).lower()
            if self._aco_do_catalogo(nome_mat):
                m.aco = nome_mat
            elif any(p in texto for p in ("aço", "aco", "steel", "metal")):
                m.aco = "ASTM A572 Gr.50"
            elif any(p in texto for p in ("concret", "concrete")):
                m.metalico, m.rugosidade = 0.0, 0.9
            self.doc.materiais[nome] = m
        elif cor:
            # o arquivo é a verdade: a cor gravada vence a cor padrão do documento
            m.cor = cor
            m.opacidade = opacidade

    def _material_nome_cor(self, ent: Entidade):
        """Nome, cor e opacidade de qualquer forma de material do IFC."""
        t = ent.tipos
        if "IFCMATERIAL" in t:
            nome = str(ent.arg(0) or "Material")
            cor, opac = self._cor_do_material(ent)
            return nome, cor, opac
        if "IFCMATERIALLAYERSETUSAGE" in t:
            return self._material_nome_cor_ref(ent.arg(0))
        if "IFCMATERIALLAYERSET" in t:
            camadas = self.lista(ent.arg(0))
            nome = str(ent.arg(1) or "")
            if camadas:
                sub = self._material_nome_cor_ref(camadas[0].arg(0))
                return (nome or sub[0]), sub[1], sub[2]
            return nome or "Material", "", 1.0
        if "IFCMATERIALLAYER" in t:
            return self._material_nome_cor_ref(ent.arg(0))
        if "IFCMATERIALPROFILESETUSAGE" in t:
            return self._material_nome_cor_ref(ent.arg(0))
        if "IFCMATERIALPROFILESET" in t:
            perfis = self.lista(ent.arg(2))
            nome = str(ent.arg(0) or "")
            if perfis:
                sub = self._material_nome_cor_ref(perfis[0].arg(2))
                return (sub[0] or nome), sub[1], sub[2]
            return nome or "Material", "", 1.0
        if "IFCMATERIALPROFILE" in t or "IFCMATERIALCONSTITUENT" in t:
            return self._material_nome_cor_ref(ent.arg(2))
        if "IFCMATERIALCONSTITUENTSET" in t:
            itens = self.lista(ent.arg(2))
            if itens:
                return self._material_nome_cor(itens[0])
            return str(ent.arg(0) or "Material"), "", 1.0
        if "IFCMATERIALLIST" in t:
            itens = self.lista(ent.arg(0))
            if itens:
                return self._material_nome_cor(itens[0])
        return "", "", 1.0

    def _material_nome_cor_ref(self, ref):
        e = self.res(ref)
        return self._material_nome_cor(e) if e is not None else ("", "", 1.0)

    def _cor_do_material(self, material: Entidade):
        guardada = self._cor_material.get(material.id)
        if guardada is not None:
            return guardada
        resultado = ("", 1.0)
        for rep in self.arq.inversos_tipo(material.id,
                                          "IFCMATERIALDEFINITIONREPRESENTATION"):
            for r in self.lista(rep.arg(2)):
                for item in self.lista(r.arg(3)):
                    achado = self._cor_de_estilos(item.arg(1) if
                                                  item.e_tipo("IFCSTYLEDITEM") else None)
                    if achado:
                        resultado = achado
                        break
        self._cor_material[material.id] = resultado
        return resultado

    def _estilo_da_representacao(self, corpo: Entidade):
        """(nome do estilo, cor, opacidade) do IfcStyledItem nos itens do corpo.

        Segue um nível de IfcMappedItem: vários programas põem o estilo nos itens da
        representação mapeada, e não no item que a instancia.
        """
        itens = self.lista(corpo.arg(3))
        for item in list(itens):
            if item.tipo == "IFCMAPPEDITEM":
                fonte = self.res(item.arg(0))
                rep = self.res(fonte.arg(1)) if fonte is not None else None
                if rep is not None:
                    itens.extend(self.lista(rep.arg(3)))
        for item in itens:
            for estilizado in self.arq.inversos_tipo(item.id, "IFCSTYLEDITEM"):
                achado = self._estilo_superficie(estilizado.arg(1))
                if achado:
                    return achado
        return None

    def _estilo_superficie(self, refs, profundidade=0):
        """(nome, cor, opacidade) do primeiro IfcSurfaceStyle com cor na lista."""
        if refs is None or profundidade > 6:
            return None
        for e in self.lista(refs):
            if e.e_tipo("IFCSURFACESTYLE"):
                achado = self._cor_de_estilos(e.arg(2))
                if achado:
                    return (str(e.arg(0) or "").strip(), achado[0], achado[1])
            elif e.e_tipo("IFCPRESENTATIONSTYLEASSIGNMENT"):
                achado = self._estilo_superficie(e.arg(0), profundidade + 1)
                if achado:
                    return achado
            elif e.e_tipo("IFCCOLOURRGB"):
                return ("", _hex_cor(e.arg(1), e.arg(2), e.arg(3)), 1.0)
        return None

    def _cor_de_estilos(self, refs, profundidade=0):
        """Procura um IfcColourRgb descendo por atribuições e estilos de superfície."""
        if refs is None or profundidade > 6:
            return None
        for e in self.lista(refs):
            t = e.tipos
            if "IFCCOLOURRGB" in t:
                cor = _hex_cor(e.arg(1), e.arg(2), e.arg(3))
                return (cor, 1.0)
            if "IFCPRESENTATIONSTYLEASSIGNMENT" in t:
                achado = self._cor_de_estilos(e.arg(0), profundidade + 1)
                if achado:
                    return achado
            elif "IFCSURFACESTYLE" in t:
                achado = self._cor_de_estilos(e.arg(2), profundidade + 1)
                if achado:
                    return achado
            elif "IFCSURFACESTYLERENDERING" in t or "IFCSURFACESTYLESHADING" in t:
                cor_ent = self.res(e.arg(0))
                transp = e.arg(1)
                if cor_ent is not None and cor_ent.e_tipo("IFCCOLOURRGB"):
                    cor = _hex_cor(cor_ent.arg(1), cor_ent.arg(2), cor_ent.arg(3))
                    opac = 1.0 - float(transp) if isinstance(transp, (int, float)) else 1.0
                    return (cor, max(0.05, min(1.0, opac)))
        return None

    # ------------------------------------------------------------ barras
    def _catalogo(self):
        if self._banco is None:
            try:
                from nucleo.perfis import banco
                self._banco = banco()
            except Exception as erro:                      # catálogo indisponível
                self.avisar("catálogo de perfis indisponível (%s): tudo vira sólido"
                            % erro)
                self._banco = False
        return self._banco or None

    def casar_perfil(self, info: dict):
        """Perfil do catálogo mais próximo das dimensões nominais do perfil IFC.

        Compara altura, largura e espessuras com tolerância relativa (5 % por padrão)
        e devolve `(nome, erro_maximo)` — ou None quando nada casa.
        """
        banco = self._catalogo()
        if banco is None:
            return None
        familia = info.get("familia", "")
        tipos = {"I": ("I",), "U": ("U", "Ue"), "Ue": ("Ue", "U"), "L": ("L",),
                 "tubo_circular": ("tubo",), "tubo_retangular": ("tubo",)}.get(familia)
        # nome declarado no IFC, quando bate com o catálogo, vale mais que a medida
        declarado = (info.get("nome") or "").strip()
        p = banco.get(declarado) if declarado else None
        if p is not None:
            if tipos and p.tipo in tipos:
                return p.nome, 0.0
            if not tipos and info.get("caixa"):
                # contorno livre (formado a frio sai assim do exportador): o nome só
                # vale se a caixa envolvente do contorno tiver as medidas do perfil
                alvo = sorted(info["caixa"])
                nominal = sorted([p.d or p.bf, p.bf or p.d])
                erro = max(abs(a - b) / b for a, b in zip(alvo, nominal) if b) \
                    if all(nominal) else 1.0
                if erro <= float(self.op["tolerancia_perfil"]):
                    return p.nome, erro
        if not tipos:
            return None
        tol = float(self.op["tolerancia_perfil"])
        alvo_d = info.get("d", 0.0)
        alvo_b = info.get("bf", 0.0)
        alvo_tw = info.get("tw", 0.0)
        alvo_tf = info.get("tf", 0.0)
        melhor = None
        for tipo in tipos:
            for p in banco.lista(tipo):
                if familia == "tubo_circular" and p.dados.get("tipo") != "redondo":
                    continue
                if familia == "tubo_retangular" and p.dados.get("tipo") == "redondo":
                    continue
                if familia == "L":
                    pares = ((alvo_d, p.bf), (alvo_b, p.bf), (alvo_tw, p.tw))
                elif familia == "tubo_circular":
                    pares = ((alvo_d, p.d), (alvo_tw, p.tw))
                elif familia == "tubo_retangular":
                    pares = ((alvo_d, p.d), (alvo_b, p.bf), (alvo_tw, p.tw))
                else:
                    pares = ((alvo_d, p.d), (alvo_b, p.bf), (alvo_tw, p.tw),
                             (alvo_tf, p.tf))
                erro = 0.0
                bom = True
                for alvo, valor in pares:
                    if not alvo or not valor:
                        continue
                    rel = abs(valor - alvo) / alvo
                    if rel > tol:
                        bom = False
                        break
                    erro = max(erro, rel)
                if bom and (melhor is None or erro < melhor[1]):
                    melhor = (p.nome, erro)
        return melhor

    def tentar_barra(self, prod: Entidade, corpo: Entidade, mundo, material: str = ""):
        """Cria uma `Barra` quando o elemento é extrusão simples de perfil conhecido.

        Perfil conhecido é o do catálogo (pelo nome declarado ou pelas medidas) ou,
        para seção cheia, a barra redonda ou chata sintética que `geometria` aceita.
        Devolve `(barra, motivo)`: a barra, ou None e o motivo de o elemento ficar
        sólido — que vai para o relatório, para nenhuma peça estrutural sumir em
        silêncio. Motivo vazio quer dizer "não se aplica" (não é viga/pilar/membro).
        """
        if not self.op["estrutural"]:
            return None, ""
        if prod.tipo not in PAPEL_POR_TIPO and \
                prod.tipo not in ("IFCBEAMSTANDARDCASE", "IFCCOLUMNSTANDARDCASE",
                                  "IFCMEMBERSTANDARDCASE"):
            return None, ""
        achado = self._extrusao_unica(corpo, mundo)
        if achado is None:
            itens = self.lista(corpo.arg(3))
            if len(itens) != 1:
                return None, "corpo com %d itens de geometria, e não uma extrusão" % len(itens)
            return None, "geometria %s não é extrusão simples" % nome_ifc(itens[0].tipo)
        item, mundo = achado
        ext, _furos, info = self.perfil_2d(item.arg(0))
        familia = info.get("familia", "")
        if not familia:
            return None, "perfil %s não suportado" % info.get("ifc", "?")
        if len(ext) >= 3:
            xs = [p[0] for p in ext]
            ys = [p[1] for p in ext]
            info["caixa"] = (max(xs) - min(xs), max(ys) - min(ys))
        casado = self.casar_perfil(info)
        motivo = ""
        if casado is None and familia in ("circulo", "retangulo"):
            casado, motivo = self._barra_sintetica(info, material)
        if casado is None:
            medidas = "d=%.1f bf=%.1f tw=%.1f tf=%.1f mm" % (
                info.get("d", 0.0), info.get("bf", 0.0), info.get("tw", 0.0),
                info.get("tf", 0.0))
            if familia in ("I", "U", "L", "tubo_circular", "tubo_retangular"):
                self.sem_perfil.append({
                    "elemento": str(prod.arg(2) or prod.arg(0) or ""),
                    "perfil_ifc": info.get("nome", "") or info.get("ifc", ""),
                    "d": round(info.get("d", 0.0), 1), "bf": round(info.get("bf", 0.0), 1),
                    "tw": round(info.get("tw", 0.0), 1), "tf": round(info.get("tf", 0.0), 1)})
            return None, motivo or "perfil %s '%s' sem correspondente no catálogo (%s)" % (
                info.get("ifc", ""), info.get("nome", ""), medidas)
        nome_perfil, erro = casado

        pos = self.matriz(item.arg(1))
        total = m_multiplicar(mundo, pos)
        direcao = self.direcao(item.arg(2), (0.0, 0.0, 1.0))
        prof = float(item.arg(3) or 0.0) * self.escala
        if abs(prof) < 1e-6:
            return None, "extrusão de comprimento nulo"
        inicio = m_ponto(total, (0.0, 0.0, 0.0))
        fim = m_ponto(total, (direcao[0] * prof, direcao[1] * prof, direcao[2] * prof))
        if prof < 0:
            inicio, fim = fim, inicio

        eixo_x = _norm(m_direcao(total, (1.0, 0.0, 0.0)))
        eixo_y = _norm(m_direcao(total, (0.0, 1.0, 0.0)))
        d = _norm((fim[0] - inicio[0], fim[1] - inicio[1], fim[2] - inicio[2]))
        if familia == "circulo":
            rotacao = 0.0                         # seção cheia redonda: sem orientação
        elif familia == "retangulo" and info.get("d", 0.0) > info.get("bf", 0.0):
            # barra chata: `geometria` desenha a largura no x da seção, então a
            # rotação é a que leva esse x à direção em que o arquivo pôs a largura
            rotacao = round(_rotacao_secao(d, eixo_y), 3)
        else:
            rotacao = round(_rotacao_secao(d, eixo_x), 3)
        barra = Barra(
            nome=str(prod.arg(2) or "") or nome_perfil,
            inicio=inicio, fim=fim, perfil=nome_perfil, rotacao=rotacao,
            papel=self._papel(prod))
        barra.atributos["eixos_ifc"] = {"x": eixo_x, "y": eixo_y}
        barra.atributos["perfil_ifc"] = info
        self.perfis_casados.append({
            "elemento": barra.nome, "tipo_ifc": nome_ifc(prod.tipo),
            "perfil_ifc": info.get("nome", "") or info.get("ifc", ""),
            "familia": familia, "perfil": nome_perfil,
            "erro_pct": round(erro * 100, 2)})
        return barra, ""

    def _barra_sintetica(self, info: dict, material: str):
        """Barra redonda ou chata para seção cheia (IfcCircle/IfcRectangleProfileDef).

        Não estão no catálogo: são os perfis sintéticos de `geometria` (correntes,
        tirantes, barras chatas). O nome declarado no arquivo vale quando
        `geometria.resolver_perfil` o aceita e as medidas conferem — é o que mantém
        "Barra ø 16 mm" igual na ida e volta; senão, monta "Barra redonda ø D mm" ou
        "Barra chata L × e mm" e pede o nome canônico a `resolver_perfil`.

        Seção cheia grande ou de material não metálico é pilar de concreto ou peça
        de madeira, não barra de aço: fica sólido, com o motivo. Os limites
        (`LIMITE_REDONDA_MM`, `LIMITE_CHATA_MM`) são de classificação, não de norma.
        Devolve `((nome, erro), "")` ou `(None, motivo)`.
        """
        baixo = (material or "").lower()
        for palavra in ("concret", "madeira", "wood", "timber", "alvenaria", "masonry"):
            if palavra in baixo:
                return None, "seção cheia de material não metálico (%s)" % material
        try:
            from nucleo3d.geometria import resolver_perfil
        except Exception as erro:
            return None, "nucleo3d.geometria indisponível para barra sintética (%s)" % erro
        tol = float(self.op["tolerancia_perfil"])
        if info["familia"] == "circulo":
            diametro = info.get("d", 0.0)
            if diametro <= 0:
                return None, "círculo de diâmetro nulo"
            if diametro > LIMITE_REDONDA_MM:
                return None, ("círculo cheio ø %.1f mm grande demais para barra redonda "
                              "(limite %g mm)" % (diametro, LIMITE_REDONDA_MM))
            alvo = ("redonda", [diametro])
            padrao = "Barra redonda ø %g mm" % _diametro_comercial(diametro)
        else:
            largura = max(info.get("d", 0.0), info.get("bf", 0.0))
            espessura = min(info.get("d", 0.0), info.get("bf", 0.0))
            if espessura <= 0:
                return None, "retângulo de espessura nula"
            if espessura > LIMITE_CHATA_MM:
                return None, ("retângulo cheio %g × %g mm espesso demais para barra chata "
                              "(limite %g mm)" % (round(largura, 2), round(espessura, 2),
                                                  LIMITE_CHATA_MM))
            alvo = ("chata", [largura, espessura])
            padrao = "Barra chata %g × %g mm" % (round(largura, 2), round(espessura, 2))

        for nome in ((info.get("nome") or "").strip(), padrao):
            if not nome:
                continue
            try:
                p = resolver_perfil(nome)
            except Exception:
                continue
            if p.dados.get("tipo") != alvo[0]:
                continue
            if alvo[0] == "redonda":
                nominal = [float(p.dados.get("d") or 0.0)]
            else:
                nominal = sorted([float(p.dados.get("b") or p.dados.get("d") or 0.0),
                                  float(p.dados.get("t") or 0.0)], reverse=True)
            if not all(nominal):
                continue
            erro = max(abs(a - b) / b for a, b in zip(alvo[1], nominal))
            if erro <= tol:
                return (p.nome, erro), ""
        return None, "nome %r não foi aceito por geometria.resolver_perfil" % padrao

    # ------------------------------------------------------------ chapas
    def _extrusao_unica(self, corpo: Entidade, mundo):
        """(IfcExtrudedAreaSolid, matriz até ele) quando o corpo é uma extrusão só.

        Segue um nível de IfcMappedItem, que é como vários programas reaproveitam a
        mesma peça.
        """
        itens = self.lista(corpo.arg(3))
        if len(itens) != 1:
            return None
        item = itens[0]
        if item.tipo == "IFCMAPPEDITEM":
            fonte = self.res(item.arg(0))
            rep = self.res(fonte.arg(1)) if fonte is not None else None
            if rep is None:
                return None
            sub = self.lista(rep.arg(3))
            if len(sub) != 1:
                return None
            extra = m_multiplicar(self.matriz(item.arg(1)), self.matriz(fonte.arg(0)))
            item = sub[0]
            mundo = m_multiplicar(mundo, extra)
        if item.tipo != "IFCEXTRUDEDAREASOLID":
            return None
        return item, mundo

    def tentar_chapa(self, prod: Entidade, corpo: Entidade, mundo) -> Optional[Chapa]:
        """Reconstrói uma `Chapa` a partir de um IfcPlate extrudado de contorno plano.

        Aceita IfcArbitraryClosedProfileDef, IfcArbitraryProfileDefWithVoids (os
        vazios circulares viram `furos`) e IfcRectangleProfileDef. O plano da chapa
        sai dos eixos da extrusão; a espessura, da profundidade. Quando a colocação do
        elemento fica no meio da espessura, a chapa volta `centrada` — que é como o
        exportador grava — e, quando fica numa face, volta com `centrada=False`.
        Vazio que não é círculo não cabe em `Chapa.furos`: o elemento cai para
        sólido, com aviso, em vez de perder o recorte.
        """
        if not self.op["estrutural"]:
            return None
        if prod.tipo not in ("IFCPLATE", "IFCPLATESTANDARDCASE"):
            return None
        colocacao = (mundo[0][3], mundo[1][3], mundo[2][3])
        achado = self._extrusao_unica(corpo, mundo)
        if achado is None:
            return None
        item, mundo = achado
        perfil = self.res(item.arg(0))
        if perfil is None or perfil.tipo not in ("IFCARBITRARYCLOSEDPROFILEDEF",
                                                 "IFCARBITRARYPROFILEDEFWITHVOIDS",
                                                 "IFCRECTANGLEPROFILEDEF"):
            return None
        ext, vazios, _info = self.perfil_2d(perfil.id)
        if len(ext) < 3:
            return None
        nome = str(prod.arg(2) or "")
        direcao = self.direcao(item.arg(2), (0.0, 0.0, 1.0))
        if abs(direcao[2]) < 0.999:
            self.avisar("chapa %s extrudada fora da normal do contorno: fica como sólido"
                        % (nome or prod.arg(0)))
            return None
        prof = float(item.arg(3) or 0.0) * self.escala
        if abs(prof) < 1e-6:
            return None

        total = m_multiplicar(mundo, self.matriz(item.arg(1)))
        ex = _norm(m_direcao(total, (1.0, 0.0, 0.0)))
        ey = _norm(m_direcao(total, (0.0, 1.0, 0.0)))
        n = _norm(_cruz(ex, ey))
        o = m_ponto(total, (0.0, 0.0, 0.0))
        v = m_direcao(total, (direcao[0] * prof, direcao[1] * prof, direcao[2] * prof))
        avanco = _dot(v, n)
        esp = abs(avanco)
        base = o if avanco > 0 else (o[0] + v[0], o[1] + v[1], o[2] + v[2])
        meio = (base[0] + n[0] * esp / 2, base[1] + n[1] * esp / 2, base[2] + n[2] * esp / 2)
        if math.dist(colocacao, base) < 0.01:
            origem, centrada = base, False
        else:
            origem, centrada = meio, True

        def no_plano(p2):
            p = m_ponto(total, (p2[0], p2[1], 0.0))
            d = (p[0] - origem[0], p[1] - origem[1], p[2] - origem[2])
            return (round(_dot(d, ex), 6), round(_dot(d, ey), 6))

        contorno = [no_plano(p) for p in ext]
        furos = []
        for vazio in vazios:
            pts = [no_plano(p) for p in vazio]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            raios = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
            r = sum(raios) / len(raios)
            if len(pts) < 8 or r <= 0 or max(abs(x - r) for x in raios) > 0.02 * r:
                self.avisar("chapa %s tem vazio não circular: fica como sólido"
                            % (nome or prod.arg(0)))
                return None
            furos.append({"x": round(cx, 4), "y": round(cy, 4),
                          "diametro": round(2 * r, 4)})

        limpo = lambda vet: tuple(0.0 if abs(c) < 1e-12 else round(c, 12)  # noqa: E731
                                  for c in vet)
        chapa = Chapa(nome=nome, origem=tuple(round(c, 6) for c in origem),
                      eixo_x=limpo(ex), eixo_y=limpo(ey), contorno=contorno,
                      espessura=round(esp, 6), centrada=centrada, furos=furos)
        self.chapas_reconhecidas.append({
            "elemento": nome or str(prod.arg(0) or ""), "espessura": chapa.espessura,
            "vertices": len(contorno), "furos": len(furos), "centrada": centrada})
        return chapa

    def _aco_de(self, propriedades: dict, material: str) -> str:
        """Aço do catálogo citado no arquivo (Pset_MetalicaCalculo ou material)."""
        try:
            from nucleo import materiais as mat
            conhecidos = mat.ACOS
        except Exception:
            return ""
        candidatos = []
        for pset in (propriedades or {}).values():
            if isinstance(pset, dict) and isinstance(pset.get("Aco"), str):
                candidatos.append(pset["Aco"].strip())
        candidatos.append(material or "")
        for c in candidatos:
            if c in conhecidos:
                return c
        return ""

    def _papel(self, prod: Entidade) -> str:
        """Papel da barra: ObjectType quando é um papel conhecido, depois o
        PredefinedType, depois palavras-chave do ObjectType.

        O ObjectType vem primeiro porque é onde o exportador grava o papel exato;
        o PredefinedType é mais pobre (longarina e terça saem ambas .PURLIN., e a
        corrente sai .MEMBER.), então só decide quando o arquivo não disser mais.
        """
        tipo_objeto = str(prod.arg(4) or "").strip().lower()
        if tipo_objeto in PAPEIS_CONHECIDOS:
            return tipo_objeto
        predefinido = str(prod.arg(8) or "").upper()
        if predefinido in PAPEL_POR_PREDEFINIDO:
            return PAPEL_POR_PREDEFINIDO[predefinido]
        tipo_obj = str(prod.arg(4) or "").lower()
        for chave, papel in (("terça", "terça"), ("terca", "terça"),
                             ("purlin", "terça"), ("contravent", "contraventamento"),
                             ("brace", "contraventamento"), ("longarina", "longarina"),
                             ("pilar", "pilar"), ("column", "pilar"),
                             ("viga", "viga"), ("beam", "viga")):
            if chave in tipo_obj:
                return papel
        base = prod.tipo.replace("STANDARDCASE", "")
        return PAPEL_POR_TIPO.get(base, "barra")

    # ------------------------------------------------------------ percurso
    def processar(self) -> Documento:
        inicio = time.time()
        self.ler_unidades()
        self.indexar_relacoes()
        self.ler_camadas()

        projetos = self.arq.por_tipo("IFCPROJECT")
        if projetos:
            p = projetos[0]
            self.doc.nome = self.op["nome"] or str(p.arg(2) or "Importado")
            self.doc.metadados["projeto_ifc"] = {
                "nome": str(p.arg(2) or ""), "descricao": str(p.arg(3) or ""),
                "fase": str(p.arg(6) or ""), "global_id": str(p.arg(0) or "")}
            for raiz in projetos:
                self._percorrer_espacial(raiz, self.op["camada_padrao"], 0)
        else:
            self.avisar("arquivo sem IfcProject: os elementos entram sem hierarquia")

        # elementos fora de qualquer estrutura espacial não podem sumir
        orfaos = 0
        for e in self.arq.por_tipo(*sorted(_TIPOS_PRODUTO)):
            if e.id in self._vistos or e.tipo in ESPACIAIS:
                continue
            if e.arg(6) is None:
                continue
            orfaos += 1
            self._elemento(e, self.op["camada_padrao"])
        if orfaos:
            self.avisar("%d elemento(s) fora da hierarquia espacial foram para a camada '%s'"
                        % (orfaos, self.op["camada_padrao"]))

        if self.barras_como_solido:
            motivos: Dict[str, int] = {}
            for b in self.barras_como_solido:
                motivos[b["motivo"]] = motivos.get(b["motivo"], 0) + 1
            principal = max(motivos, key=motivos.get)
            self.avisar("%d viga(s)/pilar(es)/membro(s) ficaram como sólido e não como "
                        "barra editável (ver 'barras_como_solido'); motivo mais comum: %s"
                        % (len(self.barras_como_solido), principal))

        # as camadas padrão do documento (Estrutura, Terças…) só servem ao galpão
        # dimensionado; num modelo importado ficariam vazias no painel, entre as que
        # importam. Some as que não receberam peça, desde que sobre alguma
        usadas = {e.camada for e in self.doc.entidades.values()}
        if usadas:
            for nome in [n for n in self.doc.camadas if n not in usadas]:
                del self.doc.camadas[nome]

        self.doc.metadados["importacao"] = {
            "arquivo": os.path.basename(self.arq.caminho),
            "schema": self.arq.schema,
            "aplicacao": self.arq.aplicacao,
            "entidades_step": len(self.arq.entidades),
            "unidade_origem": self.unidade_origem,
            "escala_para_mm": self.escala,
            "contagem_por_tipo": dict(sorted(self.contagem.items())),
            "barras": len(self.doc.barras),
            "solidos": len(self.doc.solidos),
            "chapas": len(self.doc.chapas),
            "chapas_reconhecidas": self.chapas_reconhecidas,
            "perfis_casados": self.perfis_casados,
            "sem_perfil_no_catalogo": self.sem_perfil,
            "barras_como_solido": self.barras_como_solido,
            "camadas_ifc": self.camadas_ifc,
            "origem_camada": dict(sorted(self.origem_camada.items())),
            "nao_suportados": dict(sorted(self.nao_suportados.items())),
            "ignorados": dict(sorted(self.ignorados.items())),
            "avisos": self.avisos + list(self.arq.avisos),
            "truncado": self.arq.truncado,
            "limitacoes": LIMITACOES,
            "tempo_s": round(time.time() - inicio, 3),
        }
        return self.doc

    def _percorrer_espacial(self, no: Entidade, camada: str, nivel: int):
        if nivel > 20 or no.id in self._vistos:
            return
        self._vistos.add(no.id)
        if no.tipo == "IFCBUILDINGSTOREY":
            camada = _nome_camada(no, "Pavimento")
        elif no.tipo == "IFCSITE" and nivel > 0:
            camada = _nome_camada(no, "Terreno")
        elif no.tipo == "IFCSPACE":
            camada = _nome_camada(no, "Ambiente")
        for filho in self.lista(self._contidos.get(no.id, [])):
            self._elemento(filho, camada)
        for filho in self.lista(self._agregados.get(no.id, [])):
            if filho.tipo in ESPACIAIS:
                self._percorrer_espacial(filho, camada, nivel + 1)
            else:
                self._elemento(filho, camada)

    def _elemento(self, prod: Entidade, camada: str):
        if prod.id in self._vistos:
            return
        self._vistos.add(prod.id)
        tipo = prod.tipo
        if tipo in IGNORADOS:
            if tipo == "IFCOPENINGELEMENT" and self.op["incluir_aberturas"]:
                pass
            elif tipo == "IFCSPACE" and self.op["incluir_espacos"]:
                pass
            else:
                self.ignorados[nome_ifc(tipo)] = self.ignorados.get(nome_ifc(tipo), 0) + 1
                return
        if tipo in ESPACIAIS and tipo != "IFCSPACE":
            return

        # peças de um conjunto (IfcElementAssembly) entram como elementos próprios
        filhos = self._agregados.get(prod.id, [])
        if filhos and tipo in ("IFCELEMENTASSEMBLY", "IFCCURTAINWALL", "IFCROOF",
                               "IFCSTAIR", "IFCRAMP", "IFCBUILDINGELEMENTPART"):
            for filho in self.lista(filhos):
                self._elemento(filho, camada)
            if prod.arg(6) is None:
                return

        self.contagem[nome_ifc(tipo)] = self.contagem.get(nome_ifc(tipo), 0) + 1
        mundo = self.matriz(prod.arg(5)) if prod.arg(5) is not None else m_identidade()
        corpo, todas = self.representacao_de(prod)
        global_id = str(prod.arg(0) or "")
        nome = str(prod.arg(2) or "")
        descricao = str(prod.arg(3) or "")
        propriedades = self.propriedades_de(prod)
        material, material_ifc = self.material_de(prod, corpo, propriedades)
        marcas = marcas_de(nome, descricao, propriedades)

        if corpo is None:
            if todas:
                self.avisar("elemento %s (%s) tem representação sem corpo utilizável"
                            % (nome or global_id, nome_ifc(tipo)))
            return
        camada = self._camada_do_elemento(corpo, todas, propriedades, camada, tipo, nome)

        # objeto paramétrico primeiro: barra (viga, pilar, membro) ou chapa
        e_chapa = tipo in ("IFCPLATE", "IFCPLATESTANDARDCASE")
        parametrica, motivo = None, ""
        try:
            if e_chapa:
                parametrica = self.tentar_chapa(prod, corpo, mundo)
            else:
                parametrica, motivo = self.tentar_barra(prod, corpo, mundo,
                                                        material_ifc or material)
        except (TypeError, ValueError, IndexError, AttributeError,
                ZeroDivisionError) as erro:
            motivo = "falha ao reconhecer: %s" % erro
            self.avisar("falha ao reconhecer %s em %s: %s"
                        % ("chapa" if e_chapa else "barra", nome or global_id, erro))
        if parametrica is None and motivo:
            self.barras_como_solido.append({
                "elemento": nome or global_id, "tipo_ifc": nome_ifc(tipo),
                "origem_ifc": global_id, "motivo": motivo})
        if parametrica is not None:
            parametrica.camada = camada
            parametrica.material = material
            aco = self._aco_de(propriedades, material_ifc or material)
            if aco:
                parametrica.aco = aco
            parametrica.atributos["tipo_ifc"] = nome_ifc(tipo)
            parametrica.atributos["origem_ifc"] = global_id
            if propriedades:
                parametrica.atributos["propriedades"] = propriedades
            if marcas:
                parametrica.atributos["marcas"] = marcas
            self.doc.add(parametrica)
            return

        malha = None
        try:
            malha = self.malha_da_representacao(corpo)
        except (TypeError, ValueError, IndexError, AttributeError,
                ZeroDivisionError, RecursionError) as erro:
            self.avisar("falha na geometria de %s (%s): %s"
                        % (nome or global_id, nome_ifc(tipo), erro))
        if malha is None or malha.vazia:
            self.avisar("elemento %s (%s) ficou sem geometria"
                        % (nome or global_id, nome_ifc(tipo)))
            return
        mundial = malha.transformada(mundo) if mundo != m_identidade() else malha
        solido = Solido(nome=nome, camada=camada, material=material,
                        vertices=mundial.vertices, faces=mundial.faces,
                        origem_ifc=global_id)
        solido.atributos["tipo_ifc"] = nome_ifc(tipo)
        predefinido = prod.arg(8)
        if isinstance(predefinido, str):
            solido.atributos["predefinido_ifc"] = str(predefinido)
        if propriedades:
            solido.atributos["propriedades"] = propriedades
        if marcas:
            solido.atributos["marcas"] = marcas
        self.doc.add(solido)


#: Camadas atribuídas pelo tipo da peça quando o arquivo não traz camada nenhuma.
CAMADAS_SEMANTICAS = {
    "Telhas": "#9aa4b2", "Chapas": "#b8860b", "Parafusos": "#7a5c3a",
    "Tirantes": "#2e8b57", "Pilares": "#4b5563", "Vigas": "#0b3d91", "Barras": "#6a7f99",
}

_RE_TELHA = re.compile(r"TELHA|TP\s*\d{2}|TRAPEZ|ONDUL", re.I)
_RE_PARAFUSO = re.compile(r"\bBOLT\b|PARAF|\bNUT\b|PORCA|ARRUELA|WASHER", re.I)
_RE_TIRANTE = re.compile(r"FE\s*RED|BARRA\s*ROSC|REDOND|VERG|TIRANTE", re.I)


def camada_semantica(tipo: str, nome: str) -> str:
    """Camada pelo que a peça é, para arquivos sem camada (TecnoMETAL, Tekla).

    O nome da peça manda antes do tipo: o TecnoMETAL grava telha como IfcBeam e
    IfcColumn, e parafuso como IfcBuildingElementProxy."""
    t = (tipo or "").upper()
    n = nome or ""
    if _RE_TELHA.search(n):
        return "Telhas"
    if t in ("IFCPLATE", "IFCPLATESTANDARDCASE"):
        return "Chapas"
    if t in ("IFCMECHANICALFASTENER", "IFCFASTENER") or _RE_PARAFUSO.search(n):
        return "Parafusos"
    if _RE_TIRANTE.search(n):
        return "Tirantes"
    if t in ("IFCCOLUMN", "IFCCOLUMNSTANDARDCASE"):
        return "Pilares"
    if t in ("IFCBEAM", "IFCBEAMSTANDARDCASE"):
        return "Vigas"
    if t in ("IFCMEMBER", "IFCMEMBERSTANDARDCASE"):
        return "Barras"
    return ""


def marcas_de(nome: str, descricao: str, propriedades: dict) -> dict:
    """Marcas de conjunto, posição e perfil da peça, para agrupar no editor.

    Lê o pset do TecnoMETAL ("Steel & Graphics Common": Part Mark, Assembly Mark,
    Profile), os do Tekla (PART_POS, ASSEMBLY_POS, PROFILE) e, na falta deles, a
    descrição "Mark:M86 Pos:P93 Material:CIVIL 300" que o TecnoMETAL também grava."""
    achado = {}
    chaves = {"posicao": ("Part Mark", "PART_POS", "Part Position", "Posicao"),
              "conjunto": ("Assembly Mark", "ASSEMBLY_POS", "Assembly Position", "Conjunto"),
              "perfil": ("Profile", "PROFILE", "Perfil")}
    for pset in (propriedades or {}).values():
        if not isinstance(pset, dict):
            continue
        for campo, nomes in chaves.items():
            for k in nomes:
                v = pset.get(k)
                if isinstance(v, str) and v.strip() and campo not in achado:
                    achado[campo] = re.sub(r"\s+", " ", v).strip()
    for campo, chave in (("posicao", "Pos"), ("conjunto", "Mark")):
        if campo not in achado:
            # "Mark: Pos:" (parafuso sem marca) não pode virar conjunto "Pos:"
            m = re.search(chave + r"\s*:\s*([^\s:]+)(?=\s|$)", descricao or "")
            if m:
                achado[campo] = m.group(1)
    if "perfil" not in achado and nome and nome.strip():
        achado["perfil"] = re.sub(r"\s+", " ", nome).strip()
    return achado


#: Tipos de produto varridos na busca por elementos órfãos.
_TIPOS_PRODUTO = {
    "IFCBEAM", "IFCBEAMSTANDARDCASE", "IFCCOLUMN", "IFCCOLUMNSTANDARDCASE",
    "IFCMEMBER", "IFCMEMBERSTANDARDCASE", "IFCPLATE", "IFCPLATESTANDARDCASE",
    "IFCSLAB", "IFCSLABSTANDARDCASE", "IFCWALL", "IFCWALLSTANDARDCASE",
    "IFCROOF", "IFCSTAIR", "IFCSTAIRFLIGHT", "IFCRAMP", "IFCRAMPFLIGHT",
    "IFCRAILING", "IFCCOVERING", "IFCCURTAINWALL", "IFCWINDOW", "IFCDOOR",
    "IFCFOOTING", "IFCPILE", "IFCBUILDINGELEMENTPROXY", "IFCFURNISHINGELEMENT",
    "IFCFURNITURE", "IFCFLOWSEGMENT", "IFCFLOWFITTING", "IFCFLOWTERMINAL",
    "IFCFLOWCONTROLLER", "IFCFLOWMOVINGDEVICE", "IFCFLOWSTORAGEDEVICE",
    "IFCDISTRIBUTIONELEMENT", "IFCDISTRIBUTIONFLOWELEMENT", "IFCENERGYCONVERSIONDEVICE",
    "IFCELEMENTASSEMBLY", "IFCMECHANICALFASTENER", "IFCFASTENER",
    "IFCDISCRETEACCESSORY", "IFCREINFORCINGBAR", "IFCREINFORCINGMESH", "IFCTENDON",
    "IFCCHIMNEY", "IFCSHADINGDEVICE", "IFCTRANSPORTELEMENT", "IFCSANITARYTERMINAL",
    "IFCGEOGRAPHICELEMENT", "IFCCIVILELEMENT", "IFCBUILDINGELEMENTPART",
    "IFCELECTRICAPPLIANCE", "IFCLIGHTFIXTURE", "IFCPROXY", "IFCSPACE",
    "IFCOPENINGELEMENT",
}


# =========================================================== geometria auxiliar

def _quase_igual2(a, b, tol=1e-6):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def _quase_igual3(a, b, tol=1e-6):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol and abs(a[2] - b[2]) < tol


def _fechar(pts):
    """Remove o ponto repetido do fim e pontos coincidentes seguidos."""
    limpo = []
    for p in pts:
        if not limpo or not _quase_igual2(limpo[-1], p):
            limpo.append((float(p[0]), float(p[1])))
    if len(limpo) > 1 and _quase_igual2(limpo[0], limpo[-1]):
        limpo.pop()
    return limpo


def _sem_repetidos3(pts):
    limpo = []
    for p in pts:
        if not limpo or not _quase_igual3(limpo[-1], p, 1e-4):
            limpo.append(p)
    return limpo


def _indices_para_pontos(idx, coords, pn):
    pts = []
    for i in idx or []:
        try:
            j = int(i)
        except (TypeError, ValueError):
            continue
        if pn:
            if 1 <= j <= len(pn):
                j = int(pn[j - 1])
            else:
                continue
        if 1 <= j <= len(coords):
            pts.append(coords[j - 1])
    return pts


def _eixo_dominante(pts):
    """Índice do eixo mais alinhado com a normal do polígono (0=X, 1=Y, 2=Z)."""
    n = [0.0, 0.0, 0.0]
    m = len(pts)
    for i in range(m):
        a, b = pts[i], pts[(i + 1) % m]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return max(range(3), key=lambda i: abs(n[i]))


def _poligono_i(bf, h, tw, tf):
    x, y, w, t = bf / 2.0, h / 2.0, tw / 2.0, tf
    return [(x, -y), (x, -y + t), (w, -y + t), (w, y - t), (x, y - t), (x, y),
            (-x, y), (-x, y - t), (-w, y - t), (-w, -y + t), (-x, -y + t), (-x, -y)]


def _poligono_u(bf, h, tw, tf):
    """Perfil U com a alma à esquerda e as mesas para +X."""
    x, y = bf / 2.0, h / 2.0
    return [(-x, -y), (x, -y), (x, -y + tf), (-x + tw, -y + tf),
            (-x + tw, y - tf), (x, y - tf), (x, y), (-x, y)]


def _poligono_c(bf, h, esp, labio):
    """Perfil U enrijecido (IfcCShapeProfileDef): alma à esquerda, lábios para dentro."""
    x, y = bf / 2.0, h / 2.0
    lab = max(0.0, labio)
    return [(-x, -y), (x, -y), (x, -y + lab), (x - esp, -y + lab), (x - esp, -y + esp),
            (-x + esp, -y + esp), (-x + esp, y - esp), (x - esp, y - esp),
            (x - esp, y - lab), (x, y - lab), (x, y), (-x, y)]


def _poligono_l(b, h, t):
    x, y = b / 2.0, h / 2.0
    return [(-x, -y), (x, -y), (x, -y + t), (-x + t, -y + t), (-x + t, y), (-x, y)]


def _poligono_t(bf, h, tw, tf):
    x, y, w = bf / 2.0, h / 2.0, tw / 2.0
    return [(-w, -y), (w, -y), (w, y - tf), (x, y - tf), (x, y), (-x, y),
            (-x, y - tf), (-w, y - tf)]


def _poligono_z(bf, h, tw, tf):
    x, y, w = bf, h / 2.0, tw / 2.0
    return [(-w, -y), (x, -y), (x, -y + tf), (w, -y + tf), (w, y - tf), (-x, y - tf),
            (-x, y), (-w, y)]


def _engrossar_linha(eixo, espessura):
    """Contorno de uma linha média engrossada — aproximação de IfcCenterLineProfileDef."""
    if len(eixo) < 2:
        return []
    metade = espessura / 2.0
    esq, dir_ = [], []
    for i, p in enumerate(eixo):
        a = eixo[max(0, i - 1)]
        b = eixo[min(len(eixo) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n, dx / n
        esq.append((p[0] + nx * metade, p[1] + ny * metade))
        dir_.append((p[0] - nx * metade, p[1] - ny * metade))
    return esq + list(reversed(dir_))


def _prisma(ext, furos, direcao, profundidade) -> Malha:
    """Extrusão reta de um contorno com furos."""
    ext = anti_horario(ext)
    furos = [horario(f) for f in furos if len(f) >= 3]
    d = (direcao[0] * profundidade, direcao[1] * profundidade, direcao[2] * profundidade)
    m = Malha()
    tampa = juntar_furos(ext, furos) if furos else ext
    base3 = [(p[0], p[1], 0.0) for p in tampa]
    topo3 = [(p[0] + d[0], p[1] + d[1], p[2] + d[2]) for p in base3]
    m.face(list(reversed(base3)))
    m.face(topo3)
    for laco in [ext] + furos:
        n = len(laco)
        for i in range(n):
            a, b = laco[i], laco[(i + 1) % n]
            a3 = (a[0], a[1], 0.0)
            b3 = (b[0], b[1], 0.0)
            m.face([a3, b3, (b3[0] + d[0], b3[1] + d[1], b3[2] + d[2]),
                    (a3[0] + d[0], a3[1] + d[1], a3[2] + d[2])])
    m.orientar()
    return m


def _girar(p, origem, eixo, angulo):
    """Rodrigues: gira `p` em torno da reta (origem, eixo)."""
    k = _norm(eixo)
    v = (p[0] - origem[0], p[1] - origem[1], p[2] - origem[2])
    c, s = math.cos(angulo), math.sin(angulo)
    kv = _cruz(k, v)
    kd = _dot(k, v)
    return (origem[0] + v[0] * c + kv[0] * s + k[0] * kd * (1 - c),
            origem[1] + v[1] * c + kv[1] * s + k[1] * kd * (1 - c),
            origem[2] + v[2] * c + kv[2] * s + k[2] * kd * (1 - c))


def _varrer_disco(eixo, raio, n) -> Malha:
    """Tubo aproximado: anel de `n` lados acompanhando a poligonal."""
    m = Malha()
    aneis = []
    for i, p in enumerate(eixo):
        antes = eixo[i - 1] if i > 0 else None
        depois = eixo[i + 1] if i < len(eixo) - 1 else None
        if antes is None:
            t = _norm((depois[0] - p[0], depois[1] - p[1], depois[2] - p[2]))
        elif depois is None:
            t = _norm((p[0] - antes[0], p[1] - antes[1], p[2] - antes[2]))
        else:
            t1 = _norm((p[0] - antes[0], p[1] - antes[1], p[2] - antes[2]))
            t2 = _norm((depois[0] - p[0], depois[1] - p[1], depois[2] - p[2]))
            t = _norm((t1[0] + t2[0], t1[1] + t2[1], t1[2] + t2[2]))
        u = _norm(_cruz(t, (0.0, 0.0, 1.0) if abs(t[2]) < 0.9 else (1.0, 0.0, 0.0)))
        v = _cruz(t, u)
        aneis.append([(p[0] + raio * (math.cos(2 * math.pi * k / n) * u[0] +
                                      math.sin(2 * math.pi * k / n) * v[0]),
                       p[1] + raio * (math.cos(2 * math.pi * k / n) * u[1] +
                                      math.sin(2 * math.pi * k / n) * v[1]),
                       p[2] + raio * (math.cos(2 * math.pi * k / n) * u[2] +
                                      math.sin(2 * math.pi * k / n) * v[2]))
                      for k in range(n)])
    for i in range(len(aneis) - 1):
        a, b = aneis[i], aneis[i + 1]
        for k in range(n):
            j = (k + 1) % n
            m.face([a[k], a[j], b[j], b[k]])
    m.face(list(reversed(aneis[0])))
    m.face(aneis[-1])
    m.orientar()
    return m


def _cortar_por_plano(malha: Malha, origem, normal, manter_positivo=True):
    """Corta a malha pelo plano, fechando a boca. Devolve (malha, fechou_direito)."""
    s = 1.0 if manter_positivo else -1.0
    tol = 1e-6
    dist = [s * ((v[0] - origem[0]) * normal[0] + (v[1] - origem[1]) * normal[1] +
                 (v[2] - origem[2]) * normal[2]) for v in malha.vertices]
    if all(d >= -tol for d in dist):
        return malha, True                       # nada a cortar
    nova = Malha()
    segmentos = []
    for face in malha.faces:
        saida = []
        corte = []
        n = len(face)
        for k in range(n):
            a, b = face[k], face[(k + 1) % n]
            da, db = dist[a], dist[b]
            pa, pb = malha.vertices[a], malha.vertices[b]
            if da >= -tol:
                saida.append(pa)
            if (da > tol and db < -tol) or (da < -tol and db > tol):
                t = da / (da - db)
                p = (pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t,
                     pa[2] + (pb[2] - pa[2]) * t)
                saida.append(p)
                corte.append(p)
        if len(saida) >= 3:
            nova.face(saida)
        if len(corte) == 2 and not _quase_igual3(corte[0], corte[1], 1e-6):
            segmentos.append(tuple(corte))
    if not segmentos:
        return (nova if not nova.vazia else None), True
    tampas, completo = _encadear(segmentos)
    alvo = (-normal[0] * s, -normal[1] * s, -normal[2] * s)
    for laco in tampas:
        if len(laco) < 3:
            continue
        nrm = _normal_poligono(laco)
        nova.face(laco if _dot(nrm, alvo) >= 0 else list(reversed(laco)))
    return (nova if not nova.vazia else None), completo


def _encadear(segmentos, tol=1e-4):
    """Encadeia segmentos soltos em laços fechados."""
    def chave(p):
        return (round(p[0] / tol), round(p[1] / tol), round(p[2] / tol))

    vizinhos: Dict[tuple, List[tuple]] = {}
    for a, b in segmentos:
        vizinhos.setdefault(chave(a), []).append((a, b))
        vizinhos.setdefault(chave(b), []).append((b, a))
    usados = set()
    lacos = []
    completo = True
    for i, (a0, b0) in enumerate(segmentos):
        if i in usados:
            continue
        laco = [a0, b0]
        usados.add(i)
        atual = b0
        for _ in range(len(segmentos) + 1):
            seguinte = None
            for j, (a, b) in enumerate(segmentos):
                if j in usados:
                    continue
                if _quase_igual3(a, atual, tol):
                    seguinte, proximo = j, b
                    break
                if _quase_igual3(b, atual, tol):
                    seguinte, proximo = j, a
                    break
            if seguinte is None:
                break
            usados.add(seguinte)
            atual = proximo
            if _quase_igual3(atual, a0, tol):
                break
            laco.append(atual)
        if len(laco) >= 3:
            lacos.append(laco)
        else:
            completo = False
    return lacos, completo


def _normal_poligono(pts):
    n = [0.0, 0.0, 0.0]
    m = len(pts)
    for i in range(m):
        a, b = pts[i], pts[(i + 1) % m]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return _norm(n)


def _inversa_rigida(m: Matriz) -> Matriz:
    """Inversa de uma matriz de corpo rígido (rotação transposta + translação)."""
    r = [[m[i][j] for j in range(3)] for i in range(3)]
    t = [m[i][3] for i in range(3)]
    return ((r[0][0], r[1][0], r[2][0], -(r[0][0] * t[0] + r[1][0] * t[1] + r[2][0] * t[2])),
            (r[0][1], r[1][1], r[2][1], -(r[0][1] * t[0] + r[1][1] * t[1] + r[2][1] * t[2])),
            (r[0][2], r[1][2], r[2][2], -(r[0][2] * t[0] + r[1][2] * t[1] + r[2][2] * t[2])),
            (0.0, 0.0, 0.0, 1.0))


def _arco_por_tres(p1, p2, p3, n):
    """Arco circular passando por três pontos, aproximado por `n` cordas."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return [p1, p2, p3]
    ux = ((ax ** 2 + ay ** 2) * (by - cy) + (bx ** 2 + by ** 2) * (cy - ay) +
          (cx ** 2 + cy ** 2) * (ay - by)) / d
    uy = ((ax ** 2 + ay ** 2) * (cx - bx) + (bx ** 2 + by ** 2) * (ax - cx) +
          (cx ** 2 + cy ** 2) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    a1 = math.atan2(ay - uy, ax - ux)
    a2 = math.atan2(by - uy, bx - ux)
    a3 = math.atan2(cy - uy, cx - ux)
    # garante que o meio fica entre início e fim
    def ajustar(a, base, horario_):
        while a > base:
            a -= 2 * math.pi
        while a < base - 2 * math.pi:
            a += 2 * math.pi
        return a
    anti = ((a2 - a1) % (2 * math.pi)) < ((a3 - a1) % (2 * math.pi))
    total = ((a3 - a1) % (2 * math.pi)) if anti else -((a1 - a3) % (2 * math.pi))
    return [(ux + r * math.cos(a1 + total * k / n), uy + r * math.sin(a1 + total * k / n))
            for k in range(n + 1)]


def base_secao(direcao):
    """Triedro (u, v, w) da seção com rotação zero — o mesmo de `geometria.base_local`.

    `u` é o X da seção (largura da mesa), `v` o Y (eixo forte), `w` o eixo da barra.
    O vetor auxiliar é o Z global, trocado pelo X global quando a barra é quase
    vertical. Repetido aqui para o importador não depender do módulo de desenho; o
    teste confere que os dois concordam.
    """
    w = _norm(direcao)
    aux = (0.0, 0.0, 1.0) if abs(w[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = _norm(_cruz(aux, w))
    v = _norm(_cruz(w, u))
    return u, v, w


def _rotacao_secao(direcao, eixo_x_real) -> float:
    """`Barra.rotacao`, em graus, que leva o X padrão da seção ao X que veio do IFC.

    A rotação gira `u` na direção de `v` (u' = u·cos + v·sin), como em
    `geometria.base_local`: é o editor que desenha a barra, então é a convenção dele
    que precisa reproduzir a seção do arquivo.
    """
    u, v, _w = base_secao(direcao)
    return math.degrees(math.atan2(_dot(eixo_x_real, v), _dot(eixo_x_real, u)))


def _diametro_comercial(d: float) -> float:
    """Diâmetro nominal: múltiplo de 1/16" quando cai em cima (12,7; 31,75), senão mm inteiro."""
    passo = 25.4 / 16
    k = round(d / passo)
    if k > 0 and abs(d - k * passo) < 0.01:
        return round(k * passo, 2)
    return float(round(d))


def _valor_simples(v):
    """Desembrulha `IFCLABEL('x')` e afins para um valor Python."""
    if isinstance(v, Tipado):
        return _valor_simples(v.valor)
    if isinstance(v, list):
        return [_valor_simples(x) for x in v]
    if isinstance(v, Ref):
        return None
    return v


def _hex_cor(r, g, b) -> str:
    def c(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = 0.0
        if f > 1.0:                 # alguns arquivos gravam 0..255
            f = f / 255.0
        return max(0, min(255, int(round(f * 255))))
    return "#%02x%02x%02x" % (c(r), c(g), c(b))


def _nome_camada(no: Entidade, padrao: str) -> str:
    nome = str(no.arg(2) or "").strip() or str(no.arg(7) or "").strip()
    return nome or padrao


# =========================================================== API

def importar(caminho: str, **opcoes) -> Documento:
    """Lê um IFC e devolve o `Documento` 3D em milímetro.

    Opções: `estrutural` (reconhecer barras, padrão True), `tolerancia_perfil` (0.05),
    `segmentos_circulo` (24), `incluir_aberturas` (False), `incluir_espacos` (False),
    `camada_padrao` ("Importado"), `nome` (nome do documento).

    O relatório da importação fica em `documento.metadados["importacao"]`: contagem por
    tipo IFC, o que virou `Barra`, o que virou `Solido`, o que não foi suportado e os
    avisos — é o que a interface mostra ao usuário depois de abrir o arquivo.
    """
    arquivo = ler(caminho)
    return Importador(arquivo, **opcoes).processar()


def importar_texto(texto: str, **opcoes) -> Documento:
    """Mesma importação, a partir do conteúdo em memória (usado nos testes)."""
    from ifc.step import ler_texto
    return Importador(ler_texto(texto), **opcoes).processar()


def inspecionar(caminho: str) -> dict:
    """Prévia rápida de um IFC: esquema, unidades, contagens e hierarquia.

    Não constrói geometria nenhuma — serve para a interface mostrar o que há dentro de
    um arquivo grande antes de o usuário decidir importar.
    """
    inicio = time.time()
    arq = ler(caminho)
    imp = Importador(arq)
    imp.ler_unidades()
    imp.indexar_relacoes()
    imp.ler_camadas()

    contagem = arq.contagem_por_tipo()
    elementos = {nome_ifc(t): n for t, n in contagem.items()
                 if t in _TIPOS_PRODUTO and t not in ESPACIAIS}

    def no(e: Entidade) -> dict:
        d = {"tipo": nome_ifc(e.tipo), "nome": str(e.arg(2) or ""),
             "global_id": str(e.arg(0) or ""), "elementos": len(imp._contidos.get(e.id, [])),
             "filhos": []}
        if e.tipo == "IFCBUILDINGSTOREY":
            elev = e.arg(9)
            if isinstance(elev, (int, float)):
                d["elevacao_mm"] = float(elev) * imp.escala
        for filho in imp.lista(imp._agregados.get(e.id, [])):
            if filho.tipo in ESPACIAIS:
                d["filhos"].append(no(filho))
        return d

    hierarquia = [no(p) for p in arq.por_tipo("IFCPROJECT")]
    return {
        "arquivo": os.path.basename(caminho),
        "tamanho_bytes": os.path.getsize(caminho) if os.path.isfile(caminho) else 0,
        "schema": arq.schema,
        "descricao": arq.descricao,
        "aplicacao": arq.aplicacao,
        "nome_original": arq.nome_original,
        "entidades_step": len(arq.entidades),
        "unidade_origem": imp.unidade_origem,
        "escala_para_mm": imp.escala,
        "contagem_por_tipo": {nome_ifc(t): n for t, n in contagem.items()},
        "elementos": dict(sorted(elementos.items())),
        "total_elementos": sum(elementos.values()),
        "hierarquia": hierarquia,
        "camadas": imp.camadas_ifc,
        "truncado": arq.truncado,
        "avisos": list(arq.avisos) + imp.avisos,
        "tempo_s": round(time.time() - inicio, 3),
    }
