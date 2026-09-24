# -*- coding: utf-8 -*-
"""Detalhamento de peças para produção a partir de um arquivo IFC.

    python -m saida.detalhamento ../Projeto/modelo.ifc [pasta_de_saida] [--png]

Lê o IFC, agrupa as peças por **posição** (Part Mark do TecnoMETAL, Tekla e afins; na
falta dela, o nome) e entrega:

* ``detalhamento.dxf`` — um arquivo único, em milímetro e 1:1, com o desenho de cada
  posição numa célula: contorno e furos em camadas próprias (``ACO``, ``FURO``), que
  é o que uma máquina de corte lê, e cotas, marca, material e quantidade em camadas
  separadas (``COTA``, ``TEXTO``), que o operador pode desligar;
* ``romaneio.csv`` — posição, conjunto, perfil, material, quantidade, dimensões,
  furos e peso, mais os parafusos, que só entram na lista;
* ``relatorio.json`` — o que foi reconhecido, o que ficou com ressalva e os avisos.

Por que partir da malha, e não do perfil declarado: exportadores de detalhamento como o
TecnoMETAL escrevem toda a geometria como ``IfcFacetedBrep``, sem perfil paramétrico e
sem laços internos nas faces. O contorno, os furos, a seção, o comprimento e as dobras
só existem na malha, então é dela que este módulo lê tudo. O nome do perfil serve de
rótulo e de conferência, nunca de fonte da geometria.

Como cada posição é lida (tudo em milímetro, no sistema local da peça):

1. **Eixos da peça.** ``e3`` é a normal do grupo de faces de maior área somada (a face
   da chapa, a alma do perfil, a onda da telha); ``e1`` é a aresta mais longa contida
   nesse plano, para chapas e telhas, ou o eixo principal por covariância, para barras.
   Barras redondas usam só a covariância, porque não têm face dominante. O desenho
   sempre sai deitado: se a peça for mais alta que larga, os eixos giram 90°.
2. **Chapa** (``IfcPlate``): contorno externo e furos são os laços de borda das faces
   de topo; laço redondo vira círculo, laço em estádio vira oblongo, o resto fica como
   polilinha. Espessura acima da nominal do nome marca a chapa como dobrada.
3. **Barra**: a seção é o corte da malha por um plano ao longo do eixo, em cinco
   estações; se a área e o centro batem em pelo menos três, a barra é reta e o
   comprimento é a extensão no eixo. Se não batem, é dobrada ou curva, e o desenho sai
   em duas vistas. Barra redonda dobrada (gancho, chumbador) recebe o comprimento
   desenvolvido pelo volume dividido pela área nominal.
4. **Telha**: retângulo de corte (comprimento na direção da onda × largura) e a
   seção da onda.

Chapa dobrada recebe o **desenvolvimento** pela linha média: a fatia perpendicular ao
eixo da dobra é uma faixa fechada de espessura t, e o comprimento planificado é
(perímetro − 2t)/2; a largura é a extensão no eixo da dobra; o eixo escolhido é o
que faz largura × desenvolvimento × t bater com o volume. Barra curva ou dobrada
recebe o **comprimento de corte** pelo volume dividido pela área da seção (a menor
fatia, que é a menos oblíqua). Furo inclinado ou rasgo aberto sai como polilinha; a
seção de barra com furo bem no meio pode falhar numa estação, por isso são nove.
"""
import collections
import csv
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from ifc.importar import Importador, nome_ifc                       # noqa: E402
from ifc.step import ler                                             # noqa: E402
from saida.desenhos import (Estilo, _cadeia_h, _cadeia_v, _cota_h,   # noqa: E402
                            _cota_v, _furo, _mm, _oblongo)
from saida.dxf import Desenho                                        # noqa: E402

__all__ = ["gerar", "ler_posicoes", "analisar", "desenhar_posicao", "Posicao"]

RHO_ACO = 7.85e-6          # kg/mm³
TIPOS_PECA = ("IFCBEAM", "IFCCOLUMN", "IFCMEMBER", "IFCPLATE", "IFCPLATESTANDARDCASE",
              "IFCMEMBERSTANDARDCASE", "IFCBEAMSTANDARDCASE", "IFCCOLUMNSTANDARDCASE")
TIPOS_ACESSORIO = ("IFCBUILDINGELEMENTPROXY", "IFCMECHANICALFASTENER",
                   "IFCDISCRETEACCESSORY", "IFCFASTENER")
PSET_MARCAS = "Steel & Graphics Common"        # TecnoMETAL; outros exportadores caem no nome

# ordem dos grupos na folha e nome que vai no romaneio
CLASSES = collections.OrderedDict([
    ("chapa", "Chapa"), ("chapa_dobrada", "Chapa dobrada"),
    ("barra", "Barra"), ("barra_redonda", "Barra redonda"),
    ("barra_conformada", "Barra dobrada/curva"), ("telha", "Telha"),
    ("indefinida", "Não reconhecida"),
])

Ponto = Tuple[float, float, float]


# ======================================================================== vetores

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cruz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def _normal_area(pontos: Sequence[Ponto]):
    """Normal unitária e área de um polígono plano (Newell)."""
    nx = ny = nz = 0.0
    n = len(pontos)
    for i in range(n):
        a, b = pontos[i], pontos[(i + 1) % n]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    area = 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)
    return (_norm((nx, ny, nz)) if area > 1e-12 else (0.0, 0.0, 0.0)), area


def _autovetores(verts: Sequence[Ponto]):
    """Eixos principais por covariância (Jacobi 3×3), do maior ao menor espalhamento."""
    n = len(verts)
    c = [sum(v[k] for v in verts) / n for k in range(3)]
    A = [[sum((v[i] - c[i]) * (v[j] - c[j]) for v in verts) for j in range(3)] for i in range(3)]
    V = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(60):
        p, q = max(((i, j) for i in range(3) for j in range(i + 1, 3)),
                   key=lambda ij: abs(A[ij[0]][ij[1]]))
        if abs(A[p][q]) < 1e-9:
            break
        th = 0.5 * math.atan2(2 * A[p][q], A[q][q] - A[p][p])
        co, si = math.cos(th), math.sin(th)
        for k in range(3):                      # A ← Rᵀ A R e V ← V R, só nas linhas p, q
            akp, akq = A[k][p], A[k][q]
            A[k][p], A[k][q] = co * akp - si * akq, si * akp + co * akq
        for k in range(3):
            apk, aqk = A[p][k], A[q][k]
            A[p][k], A[q][k] = co * apk - si * aqk, si * apk + co * aqk
        for k in range(3):
            vkp, vkq = V[k][p], V[k][q]
            V[k][p], V[k][q] = co * vkp - si * vkq, si * vkp + co * vkq
    ordem = sorted(range(3), key=lambda i: -A[i][i])
    return tuple(c), [_norm((V[0][i], V[1][i], V[2][i])) for i in ordem]


def _area_2d(pts) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        s += a[0] * b[1] - b[0] * a[1]
    return s / 2.0


def _ordem_natural(texto: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", texto or "")]


# ======================================================================== nomes

def _polegadas_mm(texto: str) -> Optional[float]:
    """Primeira medida em polegadas do texto ("3/8''", "1 1/2\"", "Ø 5/8") em mm."""
    t = re.sub(r"\s+", " ", texto or "")
    m = re.search(r"(\d+)\s+(\d+)/(\d+)", t)
    if m:
        return (int(m.group(1)) + int(m.group(2)) / int(m.group(3))) * 25.4
    m = re.search(r"(\d+)/(\d+)", t)
    if m:
        return int(m.group(1)) / int(m.group(2)) * 25.4
    return None


def _eh_redonda(perfil: str) -> bool:
    return bool(re.search(r"FE\s*RED|BARRA\s*ROSC|REDOND|\bFR\b|Ø\s*\d|VERG", perfil or "", re.I))


def _eh_telha(perfil: str) -> bool:
    return bool(re.search(r"TELHA|TP\s*\d{2}|TRAPEZ|ONDUL", perfil or "", re.I))


def _chapa_nominal(perfil: str) -> Optional[Tuple[float, float, float]]:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)",
                  perfil or "")
    if not m:
        return None
    return tuple(float(g.replace(",", ".")) for g in m.groups())


def _diametro_redonda(perfil: str, medido: float) -> float:
    d = _polegadas_mm(perfil)
    if d is None:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*mm", perfil or "", re.I)
        d = float(m.group(1).replace(",", ".")) if m else None
    if d is None or abs(d - medido) > 0.35 * medido:
        return medido
    return d


def _marcas_da_descricao(descricao: str) -> dict:
    """'Mark:M86 Pos:P93 Material:CIVIL 300' → dicionário."""
    d = {}
    for chave, campo in (("Pos", "Part Mark"), ("Mark", "Assembly Mark"),
                         ("Material", "Grade")):
        m = re.search(chave + r"\s*:\s*([^\s]+(?:\s+[^\s:]+)*?)(?=\s+\w+\s*:|$)", descricao or "")
        if m and m.group(1).strip():
            d[campo] = m.group(1).strip()
    return d


# ======================================================================== dados

@dataclass
class Furo:
    tipo: str                 # "redondo", "oblongo", "recorte"
    x: float
    y: float
    d: float = 0.0            # diâmetro
    larg: float = 0.0         # oblongo: comprimento total
    alt: float = 0.0          # oblongo: largura
    pontos: List[Tuple[float, float]] = field(default_factory=list)   # recorte
    vista: str = "frente"     # frente (e3), topo (e2)

    def rotulo(self) -> str:
        if self.tipo == "redondo":
            return "Ø%s" % _mm(self.d, 1)
        if self.tipo == "oblongo":
            return "OBL %sx%s" % (_mm(self.larg, 1), _mm(self.alt, 1))
        return "recorte"


@dataclass
class Posicao:
    marca: str
    tipo_ifc: str
    perfil: str = ""
    material: str = ""
    conjuntos: List[str] = field(default_factory=list)
    quantidade: int = 0
    global_ids: List[str] = field(default_factory=list)
    vertices: List[Ponto] = field(default_factory=list)      # coordenadas do arquivo
    faces: List[List[int]] = field(default_factory=list)
    # preenchido por analisar()
    classe: str = "indefinida"
    L: float = 0.0            # extensão no eixo e1 (comprimento)
    H: float = 0.0            # extensão em e2 (altura da vista de frente)
    T: float = 0.0            # extensão em e3 (espessura / profundidade)
    comprimento: float = 0.0  # comprimento de corte ou desenvolvido
    volume: float = 0.0       # mm³
    peso: float = 0.0         # kg, unitário
    furos: List[Furo] = field(default_factory=list)
    contorno: List[Tuple[float, float]] = field(default_factory=list)
    secao: List[List[Tuple[float, float]]] = field(default_factory=list)   # laços (v, w)
    observacoes: List[str] = field(default_factory=list)
    local: List[Ponto] = field(default_factory=list)          # vértices no sistema da peça
    normais: List[Ponto] = field(default_factory=list)        # por face, no sistema local
    eixos: Optional[Tuple[Ponto, Ponto, Ponto]] = None        # (e1, e2, e3) no arquivo
    vista_topo: bool = False                                  # o desenho precisa da vista de cima
    desenvolvimento: Optional[Tuple[float, float]] = None     # chapa dobrada: (largura, comprimento planificado)
    espessura: float = 0.0    # chapa: espessura real (T de uma chapa dobrada é a altura da dobra)
    nome: str = ""            # nome de produção (S.T.1, T.C.2-A…): nucleo2d.detalhar.nomear
    camada_2d: str = ""       # camada do desenho pelo tipo da peça (TERCAS, DIAGONAIS…)
    tipo_nome: str = ""       # tipo de produção (tesoura, terca_cobertura, contraventamento…)
    parafusos: Dict[str, int] = field(default_factory=dict)   # {"M12x35": 4}: os que atravessam a peça
    porcas: int = 0           # porcas/arruelas junto dos furos (fixadores sem tamanho no nome)

    @property
    def peso_total(self) -> float:
        return self.peso * self.quantidade

    def rotulo_parafusos(self) -> str:
        """"4x M12x35, 2x M16x40" (mais "+ n porcas" quando há fixador sem tamanho)."""
        partes = ["%dx %s" % (n, r) for r, n in sorted(self.parafusos.items(), key=lambda kv: _ordem_natural(kv[0]))]
        if self.porcas:
            partes.append("%d fixador(es) sem tamanho no IFC (porca ou chumbador)" % self.porcas)
        return ", ".join(partes)

    def rotulo_furos(self) -> str:
        cont = collections.Counter(f.rotulo() for f in self.furos)
        return ", ".join("%dx %s" % (n, r) for r, n in sorted(cont.items(),
                                                             key=lambda kv: kv[0]))


# ======================================================================== leitura

def ler_posicoes(caminho: str, avisar=None) -> Tuple[List[Posicao], Dict[str, int], dict]:
    """Agrupa as peças do IFC por posição; a malha é montada para uma peça de cada.

    Devolve (posições, acessórios por nome com a quantidade, informações do arquivo).
    """
    avisar = avisar or (lambda *a: None)
    t0 = time.time()
    arq = ler(caminho)
    imp = Importador(arq)
    imp.ler_unidades()
    imp.indexar_relacoes()
    avisar("arquivo lido: %d entidades em %.0f s" % (len(arq.entidades), time.time() - t0))

    posicoes: Dict[str, Posicao] = collections.OrderedDict()
    for tipo in TIPOS_PECA:
        for prod in arq.por_tipo(tipo):
            nome = re.sub(r"\s+", " ", str(prod.arg(2) or "")).strip()
            descricao = str(prod.arg(3) or "")
            props = imp.propriedades_de(prod).get(PSET_MARCAS) or {}
            marcas = dict(_marcas_da_descricao(descricao))
            marcas.update({k: v for k, v in props.items() if v not in (None, "")})
            marca = str(marcas.get("Part Mark") or nome or prod.arg(0))
            pos = posicoes.get(marca)
            if pos is None:
                pos = Posicao(marca=marca, tipo_ifc=nome_ifc(tipo),
                              perfil=re.sub(r"\s+", " ", str(marcas.get("Profile") or nome)),
                              material=str(marcas.get("Grade") or ""))
                posicoes[marca] = pos
                corpo, _ = imp.representacao_de(prod)
                malha = imp.malha_da_representacao(corpo)
                if malha is not None:
                    malha = malha.transformada(imp.matriz(prod.arg(5)))
                    pos.vertices, pos.faces = malha.vertices, malha.faces
                else:
                    pos.observacoes.append("sem geometria no arquivo")
            pos.quantidade += 1
            pos.global_ids.append(str(prod.arg(0) or ""))
            conj = str(marcas.get("Assembly Mark") or "")
            if conj and conj not in pos.conjuntos:
                pos.conjuntos.append(conj)

    acessorios: Dict[str, int] = collections.Counter()
    for tipo in TIPOS_ACESSORIO:
        for prod in arq.por_tipo(tipo):
            nome = re.sub(r"\s+", " ", str(prod.arg(2) or nome_ifc(tipo))).strip()
            acessorios[nome] += 1

    info = {"arquivo": os.path.basename(caminho), "schema": arq.schema,
            "aplicacao": arq.aplicacao, "nome_original": arq.nome_original,
            "unidade_origem": imp.unidade_origem, "entidades_step": len(arq.entidades),
            "avisos_leitura": list(arq.avisos) + imp.avisos,
            "tempo_leitura_s": round(time.time() - t0, 1)}
    return list(posicoes.values()), dict(acessorios), info


# ======================================================================== geometria

def _eixos_da_peca(pos: Posicao):
    """(centro, e1, e2, e3) no sistema do arquivo — ver a docstring do módulo."""
    verts = pos.vertices
    c, pca = _autovetores(verts)
    redonda = _eh_redonda(pos.perfil) and pos.tipo_ifc != "IfcPlate"
    if redonda:
        # o eixo da barra pelas normais da superfície (cilindro: todas perpendiculares ao
        # eixo), pesadas pela área — o trecho reto domina e o gancho não entorta a peça,
        # como acontecia com o eixo principal dos vértices
        e1 = _eixo_pelas_arestas_longas(pos) or _eixo_pelas_normais(pos)
        pos.eixo_exato = e1 is not None
        e1 = e1 or pca[0]
        if _dot(e1, pca[0]) < 0:
            e1 = tuple(-k for k in e1)
        p = pca[1] if abs(_dot(pca[1], e1)) < 0.9 else pca[2]
        e2 = _norm(_sub(p, tuple(_dot(p, e1) * k for k in e1)))
        e3 = _norm(_cruz(e1, e2))
        return c, e1, e2, e3

    normais = []
    for f in pos.faces:
        n, a = _normal_area([verts[i] for i in f])
        if a > 1e-9:
            normais.append((a, n))
    normais.sort(key=lambda t: -t[0])
    chapa = pos.tipo_ifc == "IfcPlate" or _eh_telha(pos.perfil)
    if chapa:
        # e3: direção de normal com maior área somada (os dois lados contam juntos):
        # a chapa e a onda da telha são muitas faces paralelas. Agrupa todas as
        # normais, e não só as maiores faces: na telha trapezoidal cada onda inclinada
        # é maior que cada mesa plana, mas as mesas somadas ganham
        grupos: Dict[tuple, list] = {}
        for a, n in normais:
            dobrada = n if (n[0] > 1e-6 or (abs(n[0]) <= 1e-6 and (n[1] > 1e-6 or
                            (abs(n[1]) <= 1e-6 and n[2] > 0)))) else tuple(-k for k in n)
            chave = tuple(round(k, 2) for k in dobrada)
            g = grupos.setdefault(chave, [0.0, [0.0, 0.0, 0.0]])
            g[0] += a
            for k in range(3):
                g[1][k] += a * dobrada[k]
        if grupos:
            _, (area_g, soma) = max(grupos.items(), key=lambda kv: kv[1][0])
            e3 = _norm(tuple(soma))
        else:
            e3 = pca[2]
    else:
        # barra: a maior face isolada é a alma, e é ela que a vista de frente mostra
        # (a soma das mesas de um W passaria a alma, e o desenho sairia de lado)
        e3 = normais[0][1] if normais else pca[2]

    # e1: aresta mais longa do contorno da face (chapa, telha) ou eixo principal
    # projetado (barra). Só arestas de borda: quando a face de topo vem dividida em
    # quadriláteros em volta do furo, a diagonal interna seria a maior aresta
    e1 = None
    if not chapa:
        # barra: o comprimento pela aresta reta mais longa da face principal (a alma, a
        # aba da cantoneira) — o eixo principal dos vértices inclina com furos, ponta
        # cortada em ângulo ou peça curta, e a peça saía desenhada enviesada
        e1 = _aresta_mais_longa(pos, e3, minimo=0.6 * _extensao_ao_longo(verts, pca[0]))
        if e1 is not None and _dot(e1, pca[0]) < 0:
            e1 = tuple(-k for k in e1)            # o mesmo sentido de antes: furos gravados não invertem
        pos.eixo_exato = e1 is not None
    if chapa:
        normais_faces = [_normal_area([verts[i] for i in f])[0] for f in pos.faces]
        lacos = _lacos_de_borda(pos, lambda n: abs(_dot(n, e3)) > 0.985, normais_faces)
        candidatas = lacos or pos.faces
        maior = 0.0
        for laco in candidatas:
            for i in range(len(laco)):
                a, b = verts[laco[i]], verts[laco[(i + 1) % len(laco)]]
                d = _sub(b, a)
                comp = math.sqrt(_dot(d, d))
                if comp > maior and comp > 1e-6 and abs(_dot(d, e3)) / comp < 0.05:
                    maior, e1 = comp, _norm(d)
    if e1 is None:
        p = pca[0]
        proj = _sub(p, tuple(_dot(p, e3) * k for k in e3))
        if math.sqrt(_dot(proj, proj)) < 0.2:        # eixo principal quase paralelo a e3
            p = pca[1]
            proj = _sub(p, tuple(_dot(p, e3) * k for k in e3))
        e1 = _norm(proj)
    e2 = _norm(_cruz(e3, e1))
    e1 = _norm(_cruz(e2, e3))
    return c, e1, e2, e3


def _extensao_ao_longo(verts, ax) -> float:
    ts = [_dot(v, ax) for v in verts]
    return max(ts) - min(ts) if ts else 0.0


def _aresta_mais_longa(pos: Posicao, e3, minimo: float = 0.0):
    """Direção da aresta de borda mais longa das faces paralelas a `e3` (ou None se a
    maior não passa de `minimo`)."""
    verts = pos.vertices
    normais_faces = [_normal_area([verts[i] for i in f])[0] for f in pos.faces]
    lacos = _lacos_de_borda(pos, lambda n: abs(_dot(n, e3)) > 0.985, normais_faces)
    maior, e1 = 0.0, None
    for laco in lacos or []:
        for i in range(len(laco)):
            a, b = verts[laco[i]], verts[laco[(i + 1) % len(laco)]]
            d = _sub(b, a)
            comp = math.sqrt(_dot(d, d))
            if comp > maior and comp > 1e-6 and abs(_dot(d, e3)) / comp < 0.05:
                maior, e1 = comp, _norm(d)
    if e1 is None or maior < minimo:
        return None
    return e1


def _eixo_pelas_arestas_longas(pos: Posicao):
    """Barra redonda: as arestas longas do cilindro (as geratrizes) correm no eixo do
    trecho reto — a média das que têm pelo menos 80 % da maior e são paralelas a ela.
    None quando a maior aresta é curta (barra facetada em pedaços)."""
    V = pos.vertices
    vistos, arestas = set(), []
    for f in pos.faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            k = (min(a, b), max(a, b))
            if k in vistos:
                continue
            vistos.add(k)
            d = _sub(V[b], V[a])
            L = math.sqrt(_dot(d, d))
            if L > 1e-6:
                arestas.append((L, d))
    if not arestas:
        return None
    Lmax, dmax = max(arestas, key=lambda t: t[0])
    ext = _extensao_ao_longo(V, _norm(dmax))
    if Lmax < 0.4 * ext:
        return None
    u = _norm(dmax)
    soma = [0.0, 0.0, 0.0]
    for L, d in arestas:
        if L >= 0.8 * Lmax and abs(_dot(_norm(d), u)) > 0.999:
            s = 1.0 if _dot(d, u) > 0 else -1.0
            soma = [soma[k] + s * d[k] for k in range(3)]
    return _norm(tuple(soma))


def _eixo_pelas_normais(pos: Posicao):
    """Direção a que as normais das faces menos apontam (menor autovetor de Σ área·n·nᵀ):
    o eixo de uma barra redonda. None se a malha não deixa decidir."""
    import numpy as np
    M = np.zeros((3, 3))
    verts = pos.vertices
    for f in pos.faces:
        n, a = _normal_area([verts[i] for i in f])
        if a > 1e-9:
            M += a * np.outer(n, n)
    w, V = np.linalg.eigh(M)
    if w[1] <= 1e-9 or w[0] > 0.3 * w[1]:
        return None
    v = V[:, 0]
    return (float(v[0]), float(v[1]), float(v[2]))


def _projetar(pos: Posicao, eixos=None):
    """Vértices no sistema local (u ao longo de e1, v de e2, w de e3), com u e v a
    partir de zero e w centrado; a peça sai deitada. `eixos` força (e1, e2, e3)."""
    c, e1, e2, e3 = _eixos_da_peca(pos) if eixos is None else (_autovetores(pos.vertices)[0],) + tuple(eixos)
    pos.eixos = (e1, e2, e3)
    def loc(e1, e2, e3):
        return [(_dot(_sub(v, c), e1), _dot(_sub(v, c), e2), _dot(_sub(v, c), e3))
                for v in pos.vertices]
    P = loc(e1, e2, e3)
    du = max(p[0] for p in P) - min(p[0] for p in P)
    dv = max(p[1] for p in P) - min(p[1] for p in P)
    # só a chapa gira para ficar deitada: na telha o comprimento é o da onda, e na
    # barra o eixo principal já é o comprimento
    if eixos is None and pos.tipo_ifc == "IfcPlate" and dv > du * 1.02:
        e1, e2 = e2, tuple(-k for k in e1)
        pos.eixos = (e1, e2, e3)
        P = loc(e1, e2, e3)
    u0 = min(p[0] for p in P)
    v0 = min(p[1] for p in P)
    w0 = (min(p[2] for p in P) + max(p[2] for p in P)) / 2
    pos.local = [(p[0] - u0, p[1] - v0, p[2] - w0) for p in P]
    pos.normais = [_normal_area([pos.local[i] for i in f])[0] for f in pos.faces]
    pos.L = max(p[0] for p in pos.local)
    pos.H = max(p[1] for p in pos.local)
    pos.T = max(p[2] for p in pos.local) - min(p[2] for p in pos.local)


def _volume(pos: Posicao) -> float:
    v = 0.0
    P = pos.local
    for f in pos.faces:
        a = P[f[0]]
        for i in range(1, len(f) - 1):
            v += _dot(a, _cruz(P[f[i]], P[f[i + 1]])) / 6.0
    return abs(v)


def _lacos_de_borda(pos: Posicao, selecionar, normais=None) -> List[List[int]]:
    """Arestas usadas por uma só face entre as faces selecionadas, encadeadas em laços
    de índices de vértice. É o que devolve contorno e furos de uma face plana recortada.
    `normais` (uma por face) substitui as locais quando a peça ainda não foi projetada."""
    cont = collections.Counter()
    for f, n in zip(pos.faces, normais if normais is not None else pos.normais):
        if not selecionar(n):
            continue
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            cont[(min(a, b), max(a, b))] += 1
    adj = collections.defaultdict(list)
    for (a, b), n in cont.items():
        if n == 1:
            adj[a].append(b)
            adj[b].append(a)
    visto, lacos = set(), []
    for ini in adj:
        if ini in visto:
            continue
        laco, atual, anterior = [ini], ini, None
        visto.add(ini)
        while True:
            prox = [v for v in adj[atual] if v != anterior and v not in visto]
            if not prox:
                break
            anterior, atual = atual, prox[0]
            visto.add(atual)
            laco.append(atual)
        if len(laco) >= 3:
            lacos.append(laco)
    return lacos


def _classificar_laco(pts2: List[Tuple[float, float]]) -> Furo:
    """Laço interno → furo redondo, oblongo ou recorte genérico."""
    xs = [p[0] for p in pts2]
    ys = [p[1] for p in pts2]
    larg, alt = max(xs) - min(xs), max(ys) - min(ys)
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    raios = [math.hypot(p[0] - cx, p[1] - cy) for p in pts2]
    rm = sum(raios) / len(raios)
    if len(pts2) >= 6 and rm > 0 and (max(raios) - min(raios)) < 0.04 * rm + 0.15 \
            and abs(larg - alt) < 0.05 * max(larg, alt) + 0.2:
        return Furo("redondo", cx, cy, d=2 * rm)
    # estádio: todos os pontos à distância r do segmento central
    r = min(larg, alt) / 2
    a = max(larg, alt) / 2 - r
    if len(pts2) >= 8 and a > 0.2:
        if larg >= alt:
            s1, s2 = (cx - a, cy), (cx + a, cy)
        else:
            s1, s2 = (cx, cy - a), (cx, cy + a)
        ok = True
        for p in pts2:
            dx, dy = s2[0] - s1[0], s2[1] - s1[1]
            t = max(0.0, min(1.0, ((p[0] - s1[0]) * dx + (p[1] - s1[1]) * dy) / (dx * dx + dy * dy)))
            dist = math.hypot(p[0] - s1[0] - t * dx, p[1] - s1[1] - t * dy)
            if abs(dist - r) > 0.05 * r + 0.2:
                ok = False
                break
        if ok:
            return Furo("oblongo", cx, cy, larg=larg, alt=alt)
    return Furo("recorte", cx, cy, pontos=list(pts2))


def _lacos_2d(pos: Posicao, eixo: int, sinal: float, ij: Tuple[int, int]):
    """Laços de borda das faces cuja normal aponta para `sinal·e[eixo]`, no plano do
    maior deles: (índices, pontos 2D pelos eixos `ij`), do maior para o menor.

    Só entram os laços coplanares com o maior: num U, as pontas das mesas têm a
    mesma normal que a alma, mas estão do outro lado da peça e não são furos."""
    lacos = _lacos_de_borda(pos, lambda n: n[eixo] * sinal > 0.985)
    if not lacos:
        return []
    itens = []
    for laco in lacos:
        pts = [(pos.local[i][ij[0]], pos.local[i][ij[1]]) for i in laco]
        nivel = sum(pos.local[i][eixo] for i in laco) / len(laco)
        itens.append((abs(_area_2d(pts)), nivel, laco, pts))
    itens.sort(key=lambda t: -t[0])
    # o plano do maior laço (a alma), ajustado pelos pontos dele: os eixos da peça vêm da
    # nuvem de vértices e, numa barra comprida com os furos concentrados, saem inclinados
    # uma fração de grau — a alma "sobe" alguns milímetros de uma ponta à outra, e o nível
    # médio de um furo perto da ponta não bate com o nível médio da alma inteira
    plano = _plano_do_laco(pos, itens[0][2], eixo, ij)

    def fora_do_plano(laco, nivel):
        cu = sum(pos.local[i][ij[0]] for i in laco) / len(laco)
        cv = sum(pos.local[i][ij[1]] for i in laco) / len(laco)
        return abs(nivel - (plano[0] + plano[1] * cu + plano[2] * cv))
    return [(laco, pts) for area, nivel, laco, pts in itens
            if fora_do_plano(laco, nivel) < 0.6 and area >= 1.0]


def _plano_do_laco(pos: Posicao, laco, eixo: int, ij: Tuple[int, int]):
    """nível = a + b·u + c·v pelos mínimos quadrados sobre os pontos do laço (u, v pelos
    eixos `ij`). Sem pontos bastantes para o ajuste, o nível médio (a, 0, 0)."""
    pts = [(pos.local[i][ij[0]], pos.local[i][ij[1]], pos.local[i][eixo]) for i in laco]
    n = len(pts)
    media = sum(p[2] for p in pts) / n
    if n < 3:
        return (media, 0.0, 0.0)
    su = sum(p[0] for p in pts) / n
    sv = sum(p[1] for p in pts) / n
    uu = sum((p[0] - su) ** 2 for p in pts)
    vv = sum((p[1] - sv) ** 2 for p in pts)
    uv = sum((p[0] - su) * (p[1] - sv) for p in pts)
    uz = sum((p[0] - su) * (p[2] - media) for p in pts)
    vz = sum((p[1] - sv) * (p[2] - media) for p in pts)
    det = uu * vv - uv * uv
    if abs(det) < 1e-9:
        return (media, 0.0, 0.0)
    b = (uz * vv - vz * uv) / det
    c = (vz * uu - uz * uv) / det
    # inclinação grande não é "eixo torto", é outra face: fica o nível médio
    if abs(b) > 0.02 or abs(c) > 0.02:
        return (media, 0.0, 0.0)
    return (media - b * su - c * sv, b, c)


def _contorno_e_furos(pos: Posicao, eixo: int, sinal: float, ij: Tuple[int, int],
                      vista: str) -> Tuple[List[Tuple[float, float]], List[Furo]]:
    """O maior laço é o contorno; os demais, furos."""
    lacos = _lacos_2d(pos, eixo, sinal, ij)
    if not lacos:
        return [], []
    furos = []
    for _, pts in lacos[1:]:
        f = _classificar_laco(pts)
        f.vista = vista
        furos.append(f)
    return lacos[0][1], furos


def _fatiar(pos: Posicao, u0: float) -> List[Tuple[List[Tuple[float, float]], bool]]:
    """Corte da malha pelo plano u = u0: laços (v, w) e se fecharam."""
    segs = []
    for f, nf in zip(pos.faces, pos.normais):
        pts = []
        n = len(f)
        for i in range(n):
            a, b = pos.local[f[i]], pos.local[f[(i + 1) % n]]
            da, db = a[0] - u0, b[0] - u0
            if (da < 0) != (db < 0):
                t = da / (da - db)
                pts.append((a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2])))
        if len(pts) == 2:
            segs.append((pts[0], pts[1]))
        elif len(pts) > 2:
            # face com furos ligados ao contorno por fendas (TecnoMETAL) ou côncava:
            # o plano cruza a borda um número par de vezes; ordenados ao longo da reta
            # de interseção, os pontos se emparelham dentro/fora
            dv, dw = nf[2], -nf[1]                    # direção (e1 × n) no plano (v, w)
            pts.sort(key=lambda p: p[0] * dv + p[1] * dw)
            for i in range(0, len(pts) - 1, 2):
                if math.hypot(pts[i][0] - pts[i + 1][0], pts[i][1] - pts[i + 1][1]) > 1e-6:
                    segs.append((pts[i], pts[i + 1]))
    chave = lambda p: (round(p[0], 2), round(p[1], 2))
    adj = collections.defaultdict(list)
    for k, (a, b) in enumerate(segs):
        adj[chave(a)].append((k, b))
        adj[chave(b)].append((k, a))
    usados, lacos = set(), []
    for k, (a, b) in enumerate(segs):
        if k in usados:
            continue
        usados.add(k)
        laco, atual = [a, b], b
        fechado = False
        while True:
            prox = [(kk, outro) for kk, outro in adj[chave(atual)] if kk not in usados]
            if not prox:
                break
            kk, outro = prox[0]
            usados.add(kk)
            if chave(outro) == chave(a):
                fechado = True
                break
            laco.append(outro)
            atual = outro
        if len(laco) >= 3:
            lacos.append((laco, fechado))
    return lacos


def _secao_ao_longo(pos: Posicao):
    """Seções em nove estações: (seção escolhida, é reta?, área total, área de um laço).

    Nove estações porque numa peça curta o furo ocupa boa parte do comprimento e as
    fatias que o atravessam saem diferentes; bastam três iguais para a barra ser reta.
    A área de um laço é a da seção de uma perna só: num chumbador em U a fatia corta
    as duas pernas, e o comprimento desenvolvido pelo volume precisa da área de uma."""
    L = pos.L
    estacoes = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    amostras = []
    for s in estacoes:
        lacos = _fatiar(pos, s * L)
        fechados = [l for l, ok in lacos if ok]
        if not fechados:
            amostras.append(None)
            continue
        area = sum(abs(_area_2d(l)) for l in fechados)
        pts = [p for l in fechados for p in l]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        amostras.append((fechados, area, cx, cy, len(fechados)))
    validas = [a for a in amostras if a]
    if not validas:
        return [], False, 0.0, 0.0
    # referência: a estação de maior área, que é a seção cheia; as que atravessam um
    # furo têm menos área e ficam de fora da contagem de iguais
    ref = max(validas, key=lambda a: a[1])
    tol_c = max(1.5, 0.002 * L)
    iguais = [s for s, a in zip(estacoes, amostras)
              if a and abs(a[1] - ref[1]) <= 0.05 * ref[1] and a[4] == ref[4]
              and math.hypot(a[2] - ref[2], a[3] - ref[3]) <= tol_c]
    # as estações iguais têm de cobrir a peça: num arco facetado as três do meio
    # coincidem dentro da tolerância, mas as pontas não
    reta = len(iguais) >= 3 and (max(iguais) - min(iguais)) >= 0.4
    # a área de uma perna vem da menor fatia de todas as estações: a fatia que pega a
    # dobra de uma barra redonda sai oblíqua, maior que a seção
    unitaria = min(abs(_area_2d(l)) for a in validas for l in a[0])
    return ref[0], reta, ref[1], unitaria


def _alinhar_eixo(pos: Posicao, medida):
    """Refina e1 pela reta que une os centros das seções nas pontas.

    A covariância dos vértices pende para onde há mais vértices (os furos numa ponta),
    e numa barra de 8 m um desvio de 0,25° já engorda a altura em 35 mm."""
    L = pos.L
    centros = []
    for s in (0.15, 0.85):
        fechados = [l for l, ok in _fatiar(pos, s * L) if ok]
        if not fechados:
            return medida
        pts = [p for l in fechados for p in l]
        centros.append((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
    dv, dw = centros[1][0] - centros[0][0], centros[1][1] - centros[0][1]
    if math.hypot(dv, dw) < 0.3:
        return medida
    e1, e2, e3 = pos.eixos
    du = 0.7 * L
    novo_e1 = _norm(tuple(e1[k] * du + e2[k] * dv + e3[k] * dw for k in range(3)))
    novo_e2 = _norm(_cruz(e3, novo_e1))
    novo_e3 = _norm(_cruz(novo_e1, novo_e2))
    _projetar(pos, (novo_e1, novo_e2, novo_e3))
    pos.volume = _volume(pos)
    return _secao_ao_longo(pos)


def _cortes_de_ponta(pos: Posicao, area_secao: float):
    """Ângulo do corte em cada ponta, pelas faces grandes quase perpendiculares ao eixo.

    Terça de telhado inclinado sai do TecnoMETAL com as pontas cortadas no ângulo da
    água; a produção precisa do ângulo e de vê-lo na vista certa: um corte girado em
    torno de e3 aparece de frente, um girado em torno de e2 só aparece de cima."""
    if not area_secao:
        return
    for f, n in zip(pos.faces, pos.normais):
        if abs(n[0]) < 0.7:
            continue
        a = _normal_area([pos.local[i] for i in f])[1]
        if a < 0.5 * area_secao:
            continue
        ang = math.degrees(math.acos(min(1.0, abs(n[0]))))
        if ang < 0.5:
            continue
        lado = "esquerda" if n[0] < 0 else "direita"
        onde = "vista de topo" if abs(n[2]) > abs(n[1]) else "vista de frente"
        pos.observacoes.append("ponta %s cortada a %s graus (%s)" % (lado, _mm(ang, 1), onde))
        if abs(n[2]) > abs(n[1]):
            pos.vista_topo = True


def analisar(pos: Posicao, eixos=None) -> Posicao:
    """Classifica a posição e mede o que a produção precisa; medidas ao milímetro inteiro.
    `eixos` força (e1, e2, e3): é como as instâncias de uma mesma chapa saem no mesmo
    sistema (ver nucleo2d.detalhar.converter_chapas)."""
    _analisar(pos, eixos)
    _arredondar(pos)
    return pos


def _arredondar(pos: Posicao):
    """A produção não corta em décimos: comprimento de corte, altura da chapa e posição
    dos furos vão para o milímetro inteiro (2529,5 → 2530). A espessura fica como está
    (4,8 mm é 3/16"). Diâmetros e rasgos também ficam (13, 17,5)."""
    if pos.classe == "indefinida":
        return
    if pos.classe == "chapa":
        L, H = float(round(pos.L)), float(round(pos.H))
        if pos.L > 0 and pos.H > 0 and L > 0 and H > 0:
            if abs(L - pos.L) > 1e-6 or abs(H - pos.H) > 1e-6:
                kx, ky = L / pos.L, H / pos.H
                pos.contorno = [(x * kx, y * ky) for x, y in pos.contorno]
            pos.L, pos.H = L, H
        pos.comprimento = pos.L
    elif pos.classe in ("barra", "barra_redonda", "barra_conformada", "telha"):
        pos.comprimento = float(round(pos.comprimento))
        pos.L = float(round(pos.L))
    elif pos.classe == "chapa_dobrada":
        pos.comprimento = float(round(pos.comprimento))
    if pos.desenvolvimento:
        pos.desenvolvimento = (float(round(pos.desenvolvimento[0])), float(round(pos.desenvolvimento[1])))
    for f in pos.furos:
        f.x, f.y = float(round(f.x)), float(round(f.y))


def _analisar(pos: Posicao, eixos=None) -> Posicao:
    if not pos.faces or len(pos.vertices) < 4:
        pos.classe = "indefinida"
        if not pos.observacoes:
            pos.observacoes.append("sem geometria")
        return pos
    _projetar(pos, eixos)
    pos.volume = _volume(pos)
    pos.peso = pos.volume * RHO_ACO
    perfil = pos.perfil or ""

    if pos.tipo_ifc == "IfcPlate":
        pos.contorno, pos.furos = _contorno_e_furos(pos, 2, +1.0, (0, 1), "frente")
        nominal = _chapa_nominal(perfil)
        t_nom = nominal[2] if nominal else pos.T
        pos.espessura = pos.T
        pos.comprimento = pos.L
        if pos.T > 1.25 * t_nom + 0.5 or not pos.contorno:
            pos.classe = "chapa_dobrada"
            _desenvolver_chapa(pos, nominal[2] if nominal else None)
        else:
            pos.classe = "chapa"
            if nominal and (abs(nominal[0] - pos.L) > 3 and abs(nominal[0] - pos.H) > 3):
                pos.observacoes.append("dimensões medidas diferem do nome do TecnoMETAL")
            elif nominal:
                _ajustar_ao_nominal(pos, nominal)
        return pos

    if _eh_telha(perfil):
        pos.classe = "telha"
        pos.comprimento = pos.L
        pos.secao = [l for l, ok in _fatiar(pos, 0.5 * pos.L)]
        return pos

    medida = _secao_ao_longo(pos)
    # o eixo pela aresta reta (ou pelas normais, na redonda) já é o da barra; refinar pelos
    # centros das seções entortava a peça com aba cortada ou gancho numa ponta
    if medida[1] and not getattr(pos, "eixo_exato", False):
        medida = _alinhar_eixo(pos, medida)
    secao, reta, area, area_unitaria = medida
    pos.secao = secao
    if _eh_redonda(perfil):
        d_med = 0.0
        if secao:
            xs = [p[0] for l in secao for p in l]
            ys = [p[1] for l in secao for p in l]
            d_med = min(max(xs) - min(xs), max(ys) - min(ys))
        d = _diametro_redonda(perfil, d_med or min(pos.H, pos.T))
        # área medida de uma perna (o polígono do arquivo), não a do círculo nominal:
        # um octógono tem 90 % da área do círculo e o comprimento sairia 10 % maior
        area_ref = area_unitaria or math.pi * d * d / 4
        # reta de verdade só quando o volume fecha: um gancho na ponta, fora das
        # estações de medida, aparece aqui
        reta_por_volume = abs(pos.volume / area_ref - pos.L) < 0.03 * pos.L + 2
        if reta and reta_por_volume:
            pos.classe = "barra_redonda"
            pos.comprimento = pos.L
        else:
            pos.classe = "barra_conformada"
            pos.comprimento = pos.volume / area_ref
            pos.observacoes.append("comprimento desenvolvido pelo volume (Ø %s)" % _mm(d, 1))
        pos.furos = []
        return pos

    if reta and secao:
        # a peça inteira tem de caber na seção: um U calandrado só na ponta passa no
        # teste das estações (o trecho reto é longo), mas sai 500 mm do plano da seção
        vs = [p[0] for l in secao for p in l]
        ws = [p[1] for l in secao for p in l]
        alt_secao, prof_secao = max(vs) - min(vs), max(ws) - min(ws)
        excesso = max(pos.H - alt_secao, pos.T - prof_secao)
        if excesso > 0.5 * max(alt_secao, prof_secao) + 3:
            reta = False
            pos.observacoes.append("a peça sai %s mm do plano da seção: dobra, curva ou "
                                   "apêndice soldado" % _mm(excesso))
    if reta and area and pos.volume > 1.03 * area * pos.L:
        reta = False
        pos.observacoes.append("volume maior que seção × comprimento: dobra fora das "
                               "estações de medida")
    if reta:
        pos.classe = "barra"
        pos.comprimento = pos.L
        # furos na alma (vista de frente) e nas mesas (vista de topo)
        _, furos_alma = _contorno_e_furos(pos, 2, +1.0, (0, 1), "frente")
        _, furos_mesa = _contorno_e_furos(pos, 1, -1.0, (0, 2), "topo")
        pos.furos = furos_alma + furos_mesa
        _cortes_de_ponta(pos, area)
        if area:
            falta = 1.0 - pos.volume / (area * pos.L)
            if falta > 0.03:
                pos.observacoes.append("recortes: volume %s %% abaixo de seção × comprimento"
                                       % _mm(100 * falta, 1))
    else:
        pos.classe = "barra_conformada"
        pos.comprimento = pos.L
        # comprimento de corte pelo volume ÷ área da seção: a menor fatia de todas as
        # estações é a menos oblíqua (a que atravessa a dobra sai maior que a seção)
        area_secao = area_unitaria * max(1, len(secao)) if area_unitaria else 0.0
        if area_secao > 0 and 0.9 * pos.L <= pos.volume / area_secao <= 3.0 * pos.L:
            pos.comprimento = pos.volume / area_secao
            pos.observacoes.append("barra dobrada ou curva: comprimento de corte %s mm pelo volume "
                                   "÷ seção (%s mm²)" % (_mm(pos.comprimento), _mm(area_secao)))
        else:
            pos.observacoes.append("barra dobrada ou curva: comprimento de corte não calculado")
    return pos


def _fatiar_eixo(pos: Posicao, eixo: int, valor: float):
    """`_fatiar` num eixo qualquer do sistema local: permuta as coordenadas para que o
    eixo pedido faça o papel de u, corta e devolve os laços no plano dos outros dois."""
    if eixo == 0:
        return _fatiar(pos, valor)
    ordem = (1, 0, 2) if eixo == 1 else (2, 0, 1)
    copia = Posicao(marca=pos.marca, tipo_ifc=pos.tipo_ifc, faces=pos.faces)
    copia.local = [tuple(p[i] for i in ordem) for p in pos.local]
    copia.normais = [tuple(n[i] for i in ordem) for n in pos.normais]
    return _fatiar(copia, valor)


#: Diferença até a qual a chapa medida na malha é tratada como a nominal do nome.
TOLERANCIA_NOMINAL = 1.0


def _ajustar_ao_nominal(pos: Posicao, nominal) -> bool:
    """A malha do IFC traz a chapa com décimos a menos do que o nome diz (150x123 vem
    com 122,5): a produção corta pelo nominal, e a cota tem de dizer 123. Quando a
    diferença é de até 1 mm em cada lado, o contorno e os furos são escalados para
    as dimensões nominais; diferença maior fica como medida."""
    a, b = float(nominal[0]), float(nominal[1])
    if abs(a - pos.L) <= TOLERANCIA_NOMINAL and abs(b - pos.H) <= TOLERANCIA_NOMINAL:
        alvo = (a, b)
    elif abs(b - pos.L) <= TOLERANCIA_NOMINAL and abs(a - pos.H) <= TOLERANCIA_NOMINAL:
        alvo = (b, a)
    else:
        return False
    if pos.L <= 0 or pos.H <= 0 or (abs(alvo[0] - pos.L) < 1e-6 and abs(alvo[1] - pos.H) < 1e-6):
        return False
    kx, ky = alvo[0] / pos.L, alvo[1] / pos.H
    # só o contorno estica; os furos ficam onde a malha os pôs, medidos do canto
    # inferior esquerdo (a referência da furadeira), sem ganhar décimos
    pos.contorno = [(x * kx, y * ky) for x, y in pos.contorno]
    pos.L, pos.H = alvo
    pos.comprimento = pos.L
    return True


def _desenvolver_chapa(pos: Posicao, t_nominal: Optional[float]):
    """Largura e comprimento planificado de uma chapa dobrada, pela linha média.

    Espessura: a nominal do nome; sem nome, 2·volume/área da malha (a chapa fina tem
    duas faces grandes). Para cada eixo candidato à dobra (u ou v), a fatia no meio é
    uma faixa fechada; o desenvolvimento é (perímetro − 2t)/2 e a largura é a extensão
    no eixo. Fica o eixo cujo largura × desenvolvimento × t mais se aproxima do volume,
    e só se a diferença for menor que 15 %."""
    S = sum(_normal_area([pos.local[i] for i in f])[1] for f in pos.faces)
    t = t_nominal or (2.0 * pos.volume / S if S > 0 else 0.0)
    if not t or t <= 0 or pos.volume <= 0:
        pos.observacoes.append("chapa dobrada: desenvolvimento não calculado (sem espessura)")
        return
    melhor = None
    for eixo, largura in ((0, pos.L), (1, pos.H)):
        lacos = [l for l, ok in _fatiar_eixo(pos, eixo, 0.5 * largura) if ok]
        if not lacos:
            continue
        laco = max(lacos, key=lambda l: abs(_area_2d(l)))
        perimetro = sum(math.hypot(laco[(i + 1) % len(laco)][0] - laco[i][0],
                                   laco[(i + 1) % len(laco)][1] - laco[i][1]) for i in range(len(laco)))
        desenv = (perimetro - 2.0 * t) / 2.0
        if desenv <= 0 or largura <= 0:
            continue
        erro = abs(largura * desenv * t - pos.volume) / pos.volume
        if melhor is None or erro < melhor[0]:
            melhor = (erro, largura, desenv)
    if melhor is None or melhor[0] > 0.15:
        pos.observacoes.append("chapa dobrada: desenvolvimento não calculado (a malha não fecha "
                               "como chapa de espessura constante)")
        return
    _, largura, desenv = melhor
    pos.espessura = t
    pos.desenvolvimento = (largura, desenv)
    pos.comprimento = desenv
    pos.observacoes.append("chapa dobrada: desenvolvimento %s x %s mm pela linha média, esp. %s mm"
                           % (_mm(largura), _mm(desenv), _mm(t, 1)))


# ======================================================================== desenho

def _estilo(pos: Posicao) -> Estilo:
    maior = max(pos.L, pos.H, 1.0)
    return Estilo(escala=min(12.0, max(1.0, maior / 250.0)))


def _vista(d: Desenho, pos: Posicao, ij: Tuple[int, int], k: int, sinal: float,
           dx: float, dy: float, ignorar: set = frozenset()):
    """Silhueta e arestas vivas da malha vista de `sinal·e[k]`, projetada nos eixos ij.

    Aresta entre face virada para o observador e face de costas é silhueta; entre duas
    faces viradas com ângulo acima de 30° é aresta viva; o resto não se vê. Arestas
    que pertencem a um furo já desenhado como círculo ficam de fora."""
    P = pos.local
    # vértice repetido (mesma posição, outro número) vira um só: a "ponte" que o IFC usa
    # para recortar os furos numa face só vai e volta pelo mesmo caminho com números
    # diferentes, e contada como duas arestas soltas aparecia como uma linha no meio da peça
    canon, primeiro = [], {}
    for i, p in enumerate(P):
        chave = (round(p[0], 2), round(p[1], 2), round(p[2], 2))
        canon.append(primeiro.setdefault(chave, i))
    por_aresta = collections.defaultdict(list)
    for idx, f in enumerate(pos.faces):
        for i in range(len(f)):
            a, b = canon[f[i]], canon[f[(i + 1) % len(f)]]
            if a == b:
                continue
            por_aresta[(min(a, b), max(a, b))].append(idx)
    ignorar = {(min(canon[a], canon[b]), max(canon[a], canon[b])) for a, b in ignorar} if ignorar else ignorar
    cos30 = math.cos(math.radians(30))
    for (a, b), fs in por_aresta.items():
        if (a, b) in ignorar:
            continue
        if len(fs) == 2 and fs[0] == fs[1]:
            continue                                  # ponte: ida e volta dentro da mesma face
        frente = [pos.normais[i][k] * sinal > 1e-6 for i in fs]
        if len(fs) == 1:
            camada = "ACO"
        elif any(frente) and not all(frente):
            camada = "ACO"
        elif all(frente) and _dot(pos.normais[fs[0]], pos.normais[fs[1]]) < cos30:
            camada = "ACO-FINO"
        else:
            continue
        d.linha(P[a][ij[0]] + dx, P[a][ij[1]] + dy, P[b][ij[0]] + dx, P[b][ij[1]] + dy, camada)


def _arestas_dos_furos(pos: Posicao, eixo: int, sinal: float, ij: Tuple[int, int]) -> set:
    """Arestas dos furos já desenhados como símbolo (círculo ou oblongo), para a silhueta
    não repeti-las: o laço da face da frente, o da face de trás e a parede do furo — tudo
    o que cai dentro do cilindro de cada furo. Sem isso, o furo redondo da malha
    aparecia dentro do oblongo do padrão de fábrica."""
    lacos = _lacos_2d(pos, eixo, sinal, ij)
    chaves = set()
    cilindros = []
    for laco, pts in lacos[1:]:
        for i in range(len(laco)):
            a, b = laco[i], laco[(i + 1) % len(laco)]
            chaves.add((min(a, b), max(a, b)))
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        cilindros.append((cx, cy, max(math.hypot(p[0] - cx, p[1] - cy) for p in pts) + 0.5))
    if cilindros and pos.local:
        P = [(q[ij[0]], q[ij[1]]) for q in pos.local]
        dentro = [any(math.hypot(x - cx, y - cy) <= r for cx, cy, r in cilindros) for x, y in P]
        for f in pos.faces:
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                if dentro[a] and dentro[b]:
                    chaves.add((min(a, b), max(a, b)))
    return chaves


def _desenhar_furos(d: Desenho, est: Estilo, furos: Sequence[Furo], dx: float, dy: float):
    for f in furos:
        if f.tipo == "redondo":
            _furo(d, est, f.x + dx, f.y + dy, f.d)
        elif f.tipo == "oblongo":
            _oblongo(d, f.x + dx, f.y + dy, f.larg, f.alt)
        else:
            d.polilinha([(x + dx, y + dy) for x, y in f.pontos], fechada=True, camada="FURO")


def _cotas_de_furos(d: Desenho, est: Estilo, furos: Sequence[Furo], L: float, H: float,
                    dx: float, dy: float):
    xs = sorted({round(f.x, 1) for f in furos} | {0.0, round(L, 1)})
    ys = sorted({round(f.y, 1) for f in furos} | {0.0, round(H, 1)})
    if len(xs) > 2:
        _cadeia_h(d, est, [x + dx for x in xs], dy, -est.off)
    if len(ys) > 2:
        _cadeia_v(d, est, [y + dy for y in ys], dx + L, est.off)


def _titulo(d: Desenho, est: Estilo, pos: Posicao, x: float, y: float):
    """Duas linhas acima da vista de frente: identificação e dados de produção."""
    conj = ", ".join(pos.conjuntos[:4]) + (" ..." if len(pos.conjuntos) > 4 else "")
    d.texto(x, y + est.lin, "%s   %s   %s   %d pc" % (pos.marca, pos.perfil, pos.material,
                                                     pos.quantidade), est.tg, "TEXTO")
    partes = [CLASSES.get(pos.classe, pos.classe)]
    if pos.classe in ("chapa", "chapa_dobrada"):
        partes.append("e = %s mm" % _mm(pos.T, 1))
    elif pos.classe == "barra_conformada":
        partes.append("L desenv. = %s mm" % _mm(pos.comprimento))
    else:
        partes.append("L = %s mm" % _mm(pos.comprimento))
    if pos.furos:
        partes.append(pos.rotulo_furos())
    partes.append("%s kg" % _mm(pos.peso, 2))
    if conj:
        partes.append("conj. " + conj)
    d.texto(x, y, "   ".join(partes), est.tp, "TEXTO")
    for i, obs in enumerate(pos.observacoes[:3]):
        d.texto(x, y + 2 * est.lin + (i + 1) * est.lin * 0.8, "* " + obs, est.tp, "TEXTO")


def desenhar_posicao(pos: Posicao) -> Desenho:
    """Célula de uma posição, com a vista de frente na origem."""
    d = Desenho(pos.marca)
    est = _estilo(pos)
    if pos.classe == "indefinida":
        d.texto(0, 0, "%s  %s  %d pc  (sem geometria)" % (pos.marca, pos.perfil,
                                                         pos.quantidade), 5.0, "TEXTO")
        return d
    L, H = pos.L, pos.H
    y_titulo = H + est.off + 2 * est.lin
    furos_frente = [f for f in pos.furos if f.vista == "frente"]
    furos_topo = [f for f in pos.furos if f.vista == "topo"]

    if pos.classe == "chapa":
        d.polilinha(pos.contorno, fechada=True, camada="ACO")
        _desenhar_furos(d, est, furos_frente, 0, 0)
        _cotas_de_furos(d, est, furos_frente, L, H, 0, 0)
        _cota_h(d, est, 0, L, 0, -(est.off2 if len({round(f.x, 1) for f in furos_frente}) else est.off))
        _cota_v(d, est, 0, H, L, est.off2 if len({round(f.y, 1) for f in furos_frente}) else est.off)
        _titulo(d, est, pos, 0, y_titulo)
        return d

    # vista de frente pela silhueta (barras, telhas, chapas dobradas)
    ignorar = _arestas_dos_furos(pos, 2, +1.0, (0, 1)) if furos_frente else set()
    _vista(d, pos, (0, 1), 2, +1.0, 0, 0, ignorar)
    _desenhar_furos(d, est, furos_frente, 0, 0)
    if furos_frente:
        _cotas_de_furos(d, est, furos_frente, L, H, 0, 0)
        _cota_h(d, est, 0, L, 0, -est.off2)
    else:
        _cota_h(d, est, 0, L, 0, -est.off)
    _cota_v(d, est, 0, H, L, est.off)

    x_dir = L + est.off3 + est.off          # coluna à direita da frente
    if pos.classe in ("barra", "barra_redonda", "telha") and pos.secao:
        # seção transversal (v vertical, w horizontal), alinhada com a frente
        w_min = min(p[1] for l in pos.secao for p in l)
        w_max = max(p[1] for l in pos.secao for p in l)
        largura = w_max - w_min
        for laco in pos.secao:
            d.polilinha([(x_dir + (w - w_min), v) for v, w in laco], fechada=True, camada="ACO")
        _cota_h(d, est, x_dir, x_dir + largura, 0, -est.off)
        _cota_v(d, est, 0, H, x_dir + largura, est.off)
        d.texto(x_dir, H + est.off * 0.6, "SECAO", est.tp, "TEXTO")
    if pos.classe == "chapa_dobrada":
        # vista lateral (v vertical, w horizontal) mostra a dobra
        w_min = min(p[2] for p in pos.local)
        _vista(d, pos, (2, 1), 0, +1.0, x_dir - w_min, 0)
        _cota_h(d, est, x_dir, x_dir + pos.T, 0, -est.off)
    if furos_topo or pos.vista_topo or pos.classe == "barra_conformada":
        # vista de topo (u horizontal, w vertical) abaixo da frente, sob as cotas
        y_topo = -(est.off3 + est.off + (pos.T / 2 - min(p[2] for p in pos.local)))
        ignorar_t = _arestas_dos_furos(pos, 1, -1.0, (0, 2)) if furos_topo else set()
        _vista(d, pos, (0, 2), 1, -1.0, 0, y_topo, ignorar_t)
        _desenhar_furos(d, est, furos_topo, 0, y_topo)
        w_min = min(p[2] for p in pos.local)
        w_max = max(p[2] for p in pos.local)
        if furos_topo:
            xs = sorted({round(f.x, 1) for f in furos_topo} | {0.0, round(L, 1)})
            _cadeia_h(d, est, xs, y_topo + w_min, -est.off)
        _cota_v(d, est, y_topo + w_min, y_topo + w_max, L, est.off)
    _titulo(d, est, pos, 0, y_titulo)
    return d


# ======================================================================== folha

def _ordenar(posicoes: Sequence[Posicao]) -> List[Posicao]:
    ordem = {c: i for i, c in enumerate(CLASSES)}
    return sorted(posicoes, key=lambda p: (ordem.get(p.classe, 99), _ordem_natural(p.perfil),
                                           _ordem_natural(p.marca)))


def montar_folha(posicoes: Sequence[Posicao], titulo: str, largura_max: float = 9000.0) -> Desenho:
    """Um DXF com todas as células em prateleiras, agrupadas por classe."""
    folha = Desenho("detalhamento")
    celulas = []
    for pos in _ordenar(posicoes):
        d = desenhar_posicao(pos)
        celulas.append((pos, d))
    # uma célula mais larga que a folha (barra de 29 m) fica sozinha na sua linha,
    # sem alargar as demais
    x = y = 0.0
    altura_linha = 0.0
    classe_atual = None
    cabecalho = 160.0
    y -= cabecalho
    for pos, d in celulas:
        folga = max(40.0, 0.06 * max(d.largura, d.altura))
        w, h = d.largura + 2 * folga, d.altura + 2 * folga
        nova_classe = pos.classe != classe_atual
        if x > 0 and (x + w > largura_max or nova_classe):
            y -= altura_linha
            x, altura_linha = 0.0, 0.0
        if nova_classe:
            y -= 60.0
            folha.texto(0, y - 30, CLASSES.get(pos.classe, pos.classe).upper(), 30.0, "TEXTO")
            y -= 60.0
            classe_atual = pos.classe
        dx = x + folga - d.extremos[0]
        dy = y - folga - d.extremos[3]
        folha.inserir(d, dx, dy)
        folha.retangulo(x, y - h, w, h, "AUXILIAR")
        x += w
        altura_linha = max(altura_linha, h)
    folha.texto(0, -cabecalho + 60, titulo, 50.0, "TEXTO")
    folha.texto(0, -cabecalho + 15, "Milimetro, 1:1. Camadas ACO e FURO: geometria de corte. "
                "COTA e TEXTO: anotacao. AUXILIAR: moldura das celulas.", 20.0, "TEXTO")
    return folha


# ======================================================================== saídas

def _num(x, casas=2) -> str:
    return ("%.*f" % (casas, x)).replace(".", ",")


def gravar_romaneio(caminho: str, posicoes: Sequence[Posicao], acessorios: Dict[str, int]) -> str:
    colunas = ["Nome", "Posicao", "Conjuntos", "Tipo", "Perfil / chapa", "Material", "Qtd",
               "Comprimento (mm)", "Largura (mm)", "Espessura (mm)", "Furos", "Parafusos",
               "Peso unit (kg)", "Peso total (kg)", "Observacoes"]
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(colunas)
        for p in _ordenar(posicoes):
            chapa = p.classe.startswith("chapa")
            w.writerow([getattr(p, "nome", ""), p.marca, " ".join(p.conjuntos), CLASSES.get(p.classe, p.classe),
                        p.perfil, p.material, p.quantidade,
                        _num(p.comprimento, 0) if p.classe != "indefinida" else "",
                        _num(p.desenvolvimento[0] if p.desenvolvimento else p.H, 0) if chapa or p.classe == "telha" else "",
                        _num(p.espessura or p.T, 1) if chapa else "",
                        p.rotulo_furos(), p.rotulo_parafusos(), _num(p.peso, 3), _num(p.peso_total, 2),
                        "; ".join(p.observacoes)])
        for nome, n in sorted(acessorios.items()):
            w.writerow(["", "", "", "Acessório", nome, "", n, "", "", "", "", "", "", "", "só na lista"])
    return caminho


def gerar(caminho_ifc: str, pasta: str, avisar=None, png: bool = False) -> dict:
    """Roda tudo e grava o DXF, o romaneio e o relatório em `pasta`."""
    avisar = avisar or (lambda *a: None)
    posicoes, acessorios, info = ler_posicoes(caminho_ifc, avisar)
    t0 = time.time()
    for pos in posicoes:
        try:
            analisar(pos)
        except Exception as e:                      # uma peça estranha não derruba o lote
            pos.classe = "indefinida"
            pos.observacoes.append("falha na análise: %s" % e)
    avisar("%d posições analisadas em %.1f s" % (len(posicoes), time.time() - t0))

    os.makedirs(pasta, exist_ok=True)
    titulo = "DETALHAMENTO DE PECAS - %s - %s - %d posicoes, %d pecas" % (
        info["nome_original"] or info["arquivo"], time.strftime("%d/%m/%Y"),
        len(posicoes), sum(p.quantidade for p in posicoes))
    folha = montar_folha(posicoes, titulo)
    dxf = folha.gravar(os.path.join(pasta, "detalhamento.dxf"))
    csv_path = gravar_romaneio(os.path.join(pasta, "romaneio.csv"), posicoes, acessorios)

    por_classe = collections.Counter(p.classe for p in posicoes)
    relatorio = {
        "arquivo": info, "posicoes": len(posicoes),
        "pecas": sum(p.quantidade for p in posicoes),
        "peso_total_kg": round(sum(p.peso_total for p in posicoes), 1),
        "por_classe": {CLASSES.get(c, c): n for c, n in por_classe.items()},
        "acessorios": acessorios,
        "com_ressalva": [{"marca": p.marca, "perfil": p.perfil, "observacoes": p.observacoes}
                         for p in posicoes if p.observacoes],
        "detalhe": [{"marca": p.marca, "classe": p.classe, "perfil": p.perfil,
                     "material": p.material, "qtd": p.quantidade, "conjuntos": p.conjuntos,
                     "L": round(p.L, 1), "H": round(p.H, 1), "T": round(p.T, 1),
                     "comprimento": round(p.comprimento, 1), "furos": p.rotulo_furos(),
                     "peso_kg": round(p.peso, 3)} for p in _ordenar(posicoes)],
        "arquivos": {"dxf": dxf, "romaneio": csv_path},
    }
    with open(os.path.join(pasta, "relatorio.json"), "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=1)
    if png:
        from saida import dxf_render
        relatorio["arquivos"]["png"] = dxf_render.para_png(
            dxf, os.path.join(pasta, "detalhamento.png"), dpi=90, largura=30.0)
    return relatorio


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    png = "--png" in argv
    argv = [a for a in argv if a != "--png"]
    if not argv:
        print(__doc__.split("\n\n")[0])
        return 2
    ifc = argv[0]
    nome = re.sub(r"[^\w-]+", "-", os.path.splitext(os.path.basename(ifc))[0]).strip("-").lower()
    pasta = argv[1] if len(argv) > 1 else os.path.join(_RAIZ, "projetos", nome, "detalhamento")
    rel = gerar(ifc, pasta, avisar=lambda m: print("  " + m), png=png)
    print("\n%(posicoes)d posições, %(pecas)d peças, %(peso_total_kg).1f kg" % rel)
    for classe, n in rel["por_classe"].items():
        print("  %-22s %4d" % (classe, n))
    if rel["acessorios"]:
        print("  acessórios: " + ", ".join("%s ×%d" % kv for kv in sorted(rel["acessorios"].items())))
    print("  com ressalva: %d" % len(rel["com_ressalva"]))
    for k, v in rel["arquivos"].items():
        print("  %-9s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
