# -*- coding: utf-8 -*-
"""Importa um modelo do SketchUp (.skp) direto, pela biblioteca do próprio SketchUp instalado (SketchUpAPI.dll, a API
em C que vem com o programa) — pedido do usuário, 02/10: "tem como importar o SKP direto?".

O IFC que o SketchUp exporta de um modelo vindo de DWG chega como UM objeto só (o heliponto: um proxy com 96 malhas,
camada "Layer0") e perde as etiquetas. O .skp guarda em cada face a etiqueta (tag) de origem — no modelo do CYPE,
"CPLAN_MATERIAL_PIEZA_METALICA_VIGA", "…_TORNILLO", "…_LAMINA_EF_HORMIGON"… —, e é ela que diz o que a peça é. Aqui:
cada grupo/instância e, dentro, cada conjunto de faces da mesma etiqueta que se tocam vira uma peça (Solido), na
camada da etiqueta, com o tipo IFC, o perfil (o W pelo catálogo, PLATE com a espessura) e a marca (peças iguais, a
mesma marca). As unidades internas do SketchUp são polegadas: tudo vai a mm.

Sem o SketchUp instalado nesta máquina, `disponivel()` é falso e a importação diz o motivo.
"""
import collections
import ctypes
import glob
import json
import math
import os
from ctypes import POINTER, Structure, byref, c_double, c_int, c_size_t, c_void_p
from typing import Dict, List, Optional, Tuple

from nucleo.base import ErroDeDados
from nucleo3d.modelo import Camada, Documento, Solido

POLEGADA = 25.4

#: etiqueta (o miolo do nome do CYPE, ou o nome da tag) → (camada, tipo IFC, o que é)
ETIQUETAS = {
    "PIEZA_METALICA_VIGA": ("Vigas", "IfcBeam", "viga"),
    "PIEZA_METALICA_PILAR": ("Pilares", "IfcColumn", "pilar"),
    "CHAPA": ("Chapas", "IfcPlate", "chapa"),
    "RIGIDIZADOR_BARRA": ("Chapas", "IfcPlate", "enrijecedor"),
    "PLACA_BASE_PLACA_ANCLAJE": ("Chapas", "IfcPlate", "placa de base"),
    "RIGIDIZADOR_PLACA_ANCLAJE": ("Chapas", "IfcPlate", "enrijecedor da base"),
    "PERNOS_PLACA_ANCLAJE": ("Chumbadores", "IfcMechanicalFastener", "chumbador"),
    "TORNILLO": ("Parafusos", "IfcMechanicalFastener", "parafuso"),
    "TUERCA": ("Parafusos", "IfcMechanicalFastener", "porca"),
    "ARANDELA": ("Parafusos", "IfcMechanicalFastener", "arruela"),
    "SOLDADURA_EN_TALLER": ("Soldas de fábrica", "IfcBuildingElementProxy", "solda de fábrica"),
    "SOLDADURA_EN_LUGAR_MONTAJE": ("Soldas de montagem", "IfcBuildingElementProxy", "solda de montagem"),
    "LAMINA_EF_HORMIGON": ("Laje de concreto", "IfcSlab", "laje de concreto"),
}
CORES = {"Vigas": "#0b3d91", "Pilares": "#4b5563", "Chapas": "#b8860b", "Chumbadores": "#5b6b2f", "Parafusos": "#7a5c3a",
         "Soldas de fábrica": "#c0392b", "Soldas de montagem": "#e67e22", "Laje de concreto": "#9aa4b2",
         "Sem etiqueta": "#8a94a6"}
PREFIXOS = {"Vigas": "V", "Pilares": "PL", "Chapas": "CH", "Chumbadores": "CB", "Parafusos": "PF"}
#: o que não é peça de aço a detalhar (fica no 3D, sem marca)
SEM_MARCA = {"Soldas de fábrica", "Soldas de montagem", "Laje de concreto", "Sem etiqueta"}


def _dll() -> Optional[str]:
    """A SketchUpAPI.dll do SketchUp mais novo instalado (Program Files\\SketchUp\\SketchUp 20xx\\SketchUp)."""
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", r"C:\Program Files")):
        achados = sorted(glob.glob(os.path.join(base, "SketchUp", "SketchUp 20*", "SketchUp", "SketchUpAPI.dll")), reverse=True)
        if achados:
            return achados[0]
    return None


def disponivel() -> bool:
    return _dll() is not None


class _Ref(Structure):
    _fields_ = [("ptr", c_void_p)]


class _Ponto(Structure):
    _fields_ = [("x", c_double), ("y", c_double), ("z", c_double)]


class _Transf(Structure):
    _fields_ = [("v", c_double * 16)]


class _Api:
    def __init__(self):
        caminho = _dll()
        if not caminho:
            raise ErroDeDados("para importar .skp é preciso o SketchUp instalado nesta máquina (a leitura usa a "
                              "biblioteca dele, SketchUpAPI.dll); sem ele, exporte do SketchUp em IFC.")
        os.add_dll_directory(os.path.dirname(caminho))
        self.c = ctypes.CDLL(caminho)
        for nome in ("SUFaceToDrawingElement", "SUGroupToDrawingElement", "SUComponentInstanceToDrawingElement"):
            getattr(self.c, nome).restype = _Ref

    def ok(self, res, nome):
        if res != 0:
            raise ErroDeDados("o SketchUp não leu o arquivo (%s: erro %d)" % (nome, res))

    def lista(self, num_fn, get_fn, pai) -> List[_Ref]:
        n = c_size_t()
        self.ok(getattr(self.c, num_fn)(pai, byref(n)), num_fn)
        if not n.value:
            return []
        arr = (_Ref * n.value)()
        m = c_size_t()
        self.ok(getattr(self.c, get_fn)(pai, n.value, arr, byref(m)), get_fn)
        return [arr[i] for i in range(m.value)]

    def texto(self, fn, ref) -> str:
        s = _Ref()
        self.c.SUStringCreate(byref(s))
        getattr(self.c, fn)(ref, byref(s))
        n = c_size_t()
        self.c.SUStringGetUTF8Length(s, byref(n))
        buf = ctypes.create_string_buffer(n.value + 1)
        c = c_size_t()
        self.c.SUStringGetUTF8(s, n.value + 1, buf, byref(c))
        self.c.SUStringRelease(byref(s))
        return buf.value.decode("utf-8", "replace")

    def etiqueta(self, elem) -> str:
        L = _Ref()
        if self.c.SUDrawingElementGetLayer(elem, byref(L)) != 0 or not L.ptr:
            return ""
        t = self.texto("SULayerGetName", L)
        if t.startswith("CPLAN_MATERIAL_"):
            t = t[len("CPLAN_MATERIAL_"):].split("0_2550")[0]
        return "" if t in ("Layer0", "Untagged", "Sem etiqueta") else t

    def transf(self, fn, ref) -> List[float]:
        t = _Transf()
        self.ok(getattr(self.c, fn)(ref, byref(t)), fn)
        return list(t.v)

    def triangulos(self, face) -> Tuple[List[Tuple[float, float, float]], List[Tuple[int, int, int]]]:
        """A face triangulada (com os furos) pelo SUMeshHelper."""
        m = _Ref()
        self.ok(self.c.SUMeshHelperCreate(byref(m), face), "SUMeshHelperCreate")
        try:
            n = c_size_t()
            self.c.SUMeshHelperGetNumVertices(m, byref(n))
            pts = (_Ponto * max(n.value, 1))()
            k = c_size_t()
            self.c.SUMeshHelperGetVertices(m, n.value, pts, byref(k))
            nt = c_size_t()
            self.c.SUMeshHelperGetNumTriangles(m, byref(nt))
            idx = (c_size_t * max(nt.value * 3, 1))()
            k2 = c_size_t()
            self.c.SUMeshHelperGetVertexIndices(m, nt.value * 3, idx, byref(k2))
            P = [(pts[i].x, pts[i].y, pts[i].z) for i in range(k.value)]
            T = [(idx[3 * i], idx[3 * i + 1], idx[3 * i + 2]) for i in range(k2.value // 3)]
            return P, T
        finally:
            self.c.SUMeshHelperRelease(byref(m))


def _compor(a: List[float], b: List[float]) -> List[float]:
    """a · b (matrizes 4×4 do SketchUp, por coluna)."""
    r = [0.0] * 16
    for col in range(4):
        for lin in range(4):
            r[col * 4 + lin] = sum(a[k * 4 + lin] * b[col * 4 + k] for k in range(4))
    return r


def _aplicar(t: List[float], p) -> Tuple[float, float, float]:
    x, y, z = p
    w = t[3] * x + t[7] * y + t[11] * z + t[15] or 1.0
    return ((t[0] * x + t[4] * y + t[8] * z + t[12]) / w, (t[1] * x + t[5] * y + t[9] * z + t[13]) / w,
            (t[2] * x + t[6] * y + t[10] * z + t[14]) / w)


IDENT = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def _ler_faces(caminho: str, avisar=None):
    """[(etiqueta, objeto, [triângulos em mm])] de todas as faces do modelo, com a transformação acumulada."""
    api = _Api()
    api.c.SUInitialize()
    modelo = _Ref()
    try:
        api.ok(api.c.SUModelCreateFromFile(byref(modelo), os.path.abspath(caminho).encode("utf-8")), "abrir o .skp")
        faces = []
        objeto = [0]

        def percorrer(ents, t, etq_pai, obj):
            for f in api.lista("SUEntitiesGetNumFaces", "SUEntitiesGetFaces", ents):
                etq = api.etiqueta(api.c.SUFaceToDrawingElement(f)) or etq_pai
                P, T = api.triangulos(f)
                Pm = [tuple(c * POLEGADA for c in _aplicar(t, p)) for p in P]
                faces.append((etq, obj, Pm, T))
            for g in api.lista("SUEntitiesGetNumGroups", "SUEntitiesGetGroups", ents):
                etq = api.etiqueta(api.c.SUGroupToDrawingElement(g)) or etq_pai
                sub = _Ref()
                api.ok(api.c.SUGroupGetEntities(g, byref(sub)), "grupo")
                objeto[0] += 1
                percorrer(sub, _compor(t, api.transf("SUGroupGetTransform", g)), etq, objeto[0])
            for inst in api.lista("SUEntitiesGetNumInstances", "SUEntitiesGetInstances", ents):
                etq = api.etiqueta(api.c.SUComponentInstanceToDrawingElement(inst)) or etq_pai
                d = _Ref()
                api.ok(api.c.SUComponentInstanceGetDefinition(inst, byref(d)), "definição")
                if api.texto("SUComponentDefinitionGetName", d) in ("Stacy", "Steve", "Susan", "Chris", "Lisanne"):
                    continue                           # a figura humana de escala que o SketchUp põe no modelo novo
                sub = _Ref()
                api.ok(api.c.SUComponentDefinitionGetEntities(d, byref(sub)), "componente")
                objeto[0] += 1
                percorrer(sub, _compor(t, api.transf("SUComponentInstanceGetTransform", inst)), etq, objeto[0])
        raiz = _Ref()
        api.ok(api.c.SUModelGetEntities(modelo, byref(raiz)), "entidades")
        percorrer(raiz, IDENT, "", 0)
        return faces
    finally:
        if modelo.ptr:
            api.c.SUModelRelease(byref(modelo))
        api.c.SUTerminate()


def _pecas(faces) -> List[dict]:
    """As peças: por objeto e etiqueta, as faces que se tocam (vértice em comum, 0,01 mm)."""
    por = collections.defaultdict(list)
    for etq, obj, P, T in faces:
        por[(obj, etq)].append((P, T))
    pecas = []
    for (obj, etq), lst in por.items():
        idx: Dict[tuple, int] = {}
        verts: List[tuple] = []
        tris: List[tuple] = []
        for P, T in lst:
            loc = []
            for p in P:
                k = (round(p[0], 2), round(p[1], 2), round(p[2], 2))
                if k not in idx:
                    idx[k] = len(verts)
                    verts.append(p)
                loc.append(idx[k])
            tris += [(loc[a], loc[b], loc[c]) for a, b, c in T]
        pai = list(range(len(verts)))

        def raiz(i):
            while pai[i] != i:
                pai[i] = pai[pai[i]]
                i = pai[i]
            return i
        for a, b, c in tris:
            ra, rb, rc = raiz(a), raiz(b), raiz(c)
            pai[rb] = ra
            pai[raiz(rc)] = ra
        grupos = collections.defaultdict(list)
        for t in tris:
            grupos[raiz(t[0])].append(t)
        for ts in grupos.values():
            usados = sorted({i for t in ts for i in t})
            novo = {i: k for k, i in enumerate(usados)}
            vs = [verts[i] for i in usados]
            pecas.append({"etiqueta": etq, "vertices": vs, "faces": [[novo[a], novo[b], novo[c]] for a, b, c in ts]})
    return pecas


def _catalogo_I():
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados", "fornecedores", "laminados_I.json")
    try:
        return json.load(open(caminho, encoding="utf-8"))["perfis"]
    except (OSError, ValueError, KeyError):
        return []


def _perfil_I(cat, d, bf) -> Optional[str]:
    melhor = None
    for it in cat:
        try:
            h, b = float(it["d"]), float(it["bf"])
        except (KeyError, TypeError, ValueError):
            continue
        e = abs(h - d) + abs(b - bf)
        if abs(h - d) <= 3 and abs(b - bf) <= 3 and (melhor is None or e < melhor[0]):
            melhor = (e, str(it["nome"]).replace("\u00d7", "X").replace(" ", "").replace(",0", ""))
    return melhor[1] if melhor else None


def _secao_da_barra(vs):
    """(comprimento, altura, largura, direção da altura, direção da largura) da barra: o comprimento na direção mais
    comprida (a diagonal da planta também)."""
    xs, ys, zs = zip(*vs)
    d = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    if d[0] > 1000 and d[1] > 1000 and d[2] < min(d[0], d[1]):
        melhor = None
        for sy in (1.0, -1.0):
            n_ = math.hypot(d[0], d[1])
            u = (d[0] / n_, sy * d[1] / n_)
            n = (-u[1], u[0])
            pr = [v[0] * n[0] + v[1] * n[1] for v in vs]
            larg = max(pr) - min(pr)
            pu = [v[0] * u[0] + v[1] * u[1] for v in vs]
            if melhor is None or larg < melhor[2]:
                melhor = (max(pu) - min(pu), d[2], larg, (0.0, 0.0, 1.0), (n[0], n[1], 0.0))
        return melhor
    ordem = sorted(range(3), key=lambda i: d[i])
    eixo = lambda i: tuple(1.0 if k == i else 0.0 for k in range(3))    # noqa: E731
    return d[ordem[2]], d[ordem[1]], d[ordem[0]], eixo(ordem[1]), eixo(ordem[0])


def _dividir_ao_meio(vs, faces, direcao):
    """A malha cortada no meio da medida em `direcao` (as duas vigas iguais lado a lado que o modelo trouxe num
    sólido só): cada face vai para o lado do centro dela; devolve [(vértices, faces), (vértices, faces)]."""
    pr = [sum(v[k] * direcao[k] for k in range(3)) for v in vs]
    meio = (max(pr) + min(pr)) / 2.0
    lados = ([], [])
    for f in faces:
        c = sum(pr[i] for i in f) / len(f)
        lados[0 if c < meio else 1].append(f)
    out = []
    for fs in lados:
        usados = sorted({i for f in fs for i in f})
        novo = {i: k for k, i in enumerate(usados)}
        out.append(([vs[i] for i in usados], [[novo[i] for i in f] for f in fs]))
    return out


def _eixo_e_faixa(vs) -> Tuple[int, float, float, Tuple[float, ...], Tuple[float, ...]]:
    """(eixo comprido 0/1/2, começo, fim ao longo dele, caixa mín, caixa máx)."""
    lo = tuple(min(v[i] for v in vs) for i in range(3))
    hi = tuple(max(v[i] for v in vs) for i in range(3))
    d = [hi[i] - lo[i] for i in range(3)]
    ax = d.index(max(d))
    return ax, lo[ax], hi[ax], lo, hi


#: Fração do comprimento da parte mais curta em comum com a outra para serem a mesma barra.
SOBREPOSICAO = 0.8


def _juntar_barras(pecas: List[dict], tol: float = 1.5) -> List[dict]:
    """As partes de uma mesma barra (o CYPE exporta o perfil em pedaços: as mesas, a alma, os raios de concordância),
    da mesma etiqueta, no mesmo eixo, com o mesmo começo e fim e encostadas, viram uma peça só. A viga que encosta
    na outra numa ligação não entra: é de outro eixo ou de outra faixa."""
    barras = [p for p in pecas if ETIQUETAS.get(p["etiqueta"], ("",))[0] in ("Vigas", "Pilares")]
    resto = [p for p in pecas if ETIQUETAS.get(p["etiqueta"], ("",))[0] not in ("Vigas", "Pilares")]
    info = [_eixo_e_faixa(p["vertices"]) for p in barras]
    pai = list(range(len(barras)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    # candidatos pela posição no plano da seção (células de 1 m em volta do centro), no mesmo eixo e etiqueta
    celulas = collections.defaultdict(list)
    for i, (ax, a, b, lo, hi) in enumerate(info):
        o = [k for k in range(3) if k != ax]
        c = tuple(int(math.floor((lo[k] + hi[k]) / 2.0 / 1000.0)) for k in o)
        celulas[(barras[i]["etiqueta"], ax) + c].append(i)
    for i, (ax, a, b, lo, hi) in enumerate(info):
        o = [k for k in range(3) if k != ax]
        c = tuple(int(math.floor((lo[k] + hi[k]) / 2.0 / 1000.0)) for k in o)
        for d0 in (-1, 0, 1):
            for d1 in (-1, 0, 1):
                for j in celulas.get((barras[i]["etiqueta"], ax, c[0] + d0, c[1] + d1), ()):
                    if j <= i:
                        continue
                    _, a2, b2, lo2, hi2 = info[j]
                    curta = min(b - a, b2 - a2)
                    sobre = min(b, b2) - max(a, a2)
                    # a mesma barra: quase todo o comprimento em comum (a mesa recortada na ponta chega a ser 166 mm
                    # mais curta que a alma, no heliponto) e encostadas na seção
                    if curta <= 0 or sobre < SOBREPOSICAO * curta:
                        continue
                    if all(lo[k] <= hi2[k] + tol and lo2[k] <= hi[k] + tol for k in o):
                        pai[raiz(j)] = raiz(i)
    grupos = collections.defaultdict(list)
    for i in range(len(barras)):
        grupos[raiz(i)].append(barras[i])
    juntas = []
    for g in grupos.values():
        if len(g) == 1:
            juntas.append(g[0])
            continue
        vs, fs = [], []
        for p in g:
            off = len(vs)
            vs += p["vertices"]
            fs += [[i + off for i in f] for f in p["faces"]]
        juntas.append({"etiqueta": g[0]["etiqueta"], "vertices": vs, "faces": fs, "partes": len(g)})
    return juntas + resto


def importar(caminho: str, avisar=None) -> Documento:
    """O Documento do .skp: peças separadas, camada pela etiqueta, tipo IFC, perfil e marca."""
    avisar = avisar or (lambda *a: None)
    avisar("lendo o .skp pela biblioteca do SketchUp…")
    faces = _ler_faces(caminho, avisar)
    avisar("separando as peças (%d faces)…" % len(faces))
    pecas = _juntar_barras(_pecas(faces))
    cat = _catalogo_I()
    doc = Documento(nome=os.path.splitext(os.path.basename(caminho))[0])
    doc.camadas.clear()
    assin: Dict[tuple, str] = {}
    cont = collections.Counter()
    resumo = collections.Counter()
    sem_etiqueta = collections.Counter()
    k_peca = 0
    while k_peca < len(pecas):
        p = pecas[k_peca]
        k_peca += 1
        camada, tipo, oque = ETIQUETAS.get(p["etiqueta"], ("Sem etiqueta", "IfcBuildingElementProxy", p["etiqueta"] or "sem etiqueta"))
        if camada == "Sem etiqueta":
            sem_etiqueta[p["etiqueta"] or "(nenhuma)"] += 1
        vs = p["vertices"]
        xs, ys, zs = zip(*vs)
        dims = sorted((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
        if camada in ("Vigas", "Pilares"):
            comp, alt, larg, dir_alt, dir_larg = _secao_da_barra(vs)
            perfil = _perfil_I(cat, alt, larg) or _perfil_I(cat, larg, alt)
            if not perfil:
                # duas vigas iguais lado a lado num sólido só (a diagonal dupla W610X217 do heliponto): a peça vira duas
                for d_, b_, dir_ in ((alt, larg / 2.0, dir_larg), (larg, alt / 2.0, dir_alt)):
                    duplo = _perfil_I(cat, d_, b_)
                    if duplo:
                        metades = _dividir_ao_meio(vs, p["faces"], dir_)
                        if all(len(m[0]) >= 8 for m in metades):
                            for vs_m, fs_m in metades[1:]:
                                pecas.append({"etiqueta": p["etiqueta"], "vertices": vs_m, "faces": fs_m, "partes": p.get("partes", 1),
                                              "dividida": True})
                            vs, p = metades[0][0], dict(p, vertices=metades[0][0], faces=metades[0][1], dividida=True)
                            xs, ys, zs = zip(*vs)
                            dims = sorted((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
                            perfil = duplo
                            break
            perfil = perfil or "I %dx%d (a confirmar)" % (round(alt), round(larg))
        elif camada == "Chapas":
            perfil = "PLATE %dx%dx%d" % (round(dims[2]), round(dims[1]), round(dims[0]))
        elif camada in ("Parafusos", "Chumbadores"):
            perfil = "%s %dx%d" % (oque.upper(), round(dims[1]), round(dims[2]))
        else:
            perfil = oque.upper()
        s = Solido(nome=perfil, camada=camada, vertices=[tuple(round(c, 3) for c in v) for v in vs], faces=p["faces"])
        s.atributos["tipo_ifc"] = tipo
        s.atributos["origem_skp"] = {"etiqueta": p["etiqueta"], "peca": oque, "partes": p.get("partes", 1)}
        if camada not in SEM_MARCA:
            k = (camada, perfil, tuple(round(x) for x in dims), len(vs))
            if k not in assin:
                cont[camada] += 1
                assin[k] = "%s%d" % (PREFIXOS.get(camada, "P"), cont[camada])
            s.atributos["marcas"] = {"posicao": assin[k], "conjunto": assin[k], "perfil": perfil}
        if camada not in doc.camadas:
            doc.camadas[camada] = Camada(nome=camada, cor=CORES.get(camada, "#8a94a6"))
        doc.add(s)
        resumo[camada] += 1
    doc.metadados["importacao"] = {"origem": "skp", "faces": len(faces), "pecas": len(pecas), "por_camada": dict(resumo),
                                   "marcas": dict(cont), "sem_etiqueta": dict(sem_etiqueta)}
    return doc
