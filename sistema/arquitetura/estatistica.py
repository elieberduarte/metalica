# -*- coding: utf-8 -*-
"""A estatística da prancha da prefeitura (02/11/2026): o quadro do Aprova Fácil de Cascavel
(`Normas/ARQUITETURA/Cascavel/LEIA-ME.md`), contado pelo modelo.

- **Área do terreno:** o contorno do lote (elemento `"lote"`).
- **Área a construir:** a soma dos andares. Cada andar é a área **fechada** (os ambientes e as paredes que nascem nele,
  pela face de fora, com o miolo preenchido) mais a área **coberta aberta**: o chão debaixo de uma laje ou de um telhado
  daquele andar (alpendre, varanda coberta, marquise, o chão sob a sacada do andar de cima).
  - Pisos a até `MESMO_ANDAR` um do outro são o mesmo andar (a garagem a −0,35 e o térreo).
  - Uma laje cobre o andar quando deixa pelo menos `PE_DIREITO_MIN` livre e não passa do piso do andar seguinte
    (nem de `ANDAR_MAX` acima do piso, no último).
  - Nível sem ambiente não é andar (a casinha das caixas d'água, a platibanda). A sacada e o terraço descobertos não contam.
- **Taxa de ocupação:** a projeção da edificação (a união dos andares) sobre a área do terreno.
- **Taxa de permeabilidade:** as áreas permeáveis do lote (grama, jardim), fora da projeção da edificação, sobre a área
  do terreno.
- **Taxa de impermeabilização:** todo o resto (calçadas, deck, piscina e a edificação) sobre a área do terreno.
- **Coeficiente de aproveitamento:** a área a construir sobre a área do terreno.

PROPOSTA (ARQ-09, a combinar com o usuário pela prova `Projeto/ANALISES/Arquitetura/`): a área coberta aberta conta
inteira, sem desconto de beiral ou de balanço, e na área a construir não há área não computável.
"""
from typing import Dict, List, Optional

from nucleo3d.modelo import Documento

from . import modelo as M
from .paredes import TIPOS

MESMO_ANDAR = 1500
PE_DIREITO_MIN = 2000
ANDAR_MAX = 4500


def _geo():
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import unary_union
    return LineString, Polygon, box, unary_union


def _preencher(g):
    """a área pela face de fora: os buracos (o miolo entre as paredes) entram"""
    _, Polygon, _, unary_union = _geo()
    partes = getattr(g, "geoms", [g])
    return unary_union([Polygon(p.exterior) for p in partes if not p.is_empty and p.geom_type == "Polygon"])


def _elementos(doc: Documento, tipo: str) -> List[dict]:
    return [a for a in (M._arq(e) for e in doc.entidades.values()) if a and a.get("elemento") == tipo]


def lote(doc: Documento) -> Optional[dict]:
    lotes = _elementos(doc, "lote")
    return lotes[0] if lotes else None


def calcular(doc: Documento, com_geometria: bool = False) -> Dict:
    """o quadro da estatística, com as áreas em m² (2 casas) e as taxas em % (1 casa); `com_geometria` junta os
    polígonos (shapely) do terreno, da projeção, do permeável e de cada andar, para o desenho"""
    LineString, Polygon, box, unary_union = _geo()
    lt = lote(doc)
    if not lt:
        raise ValueError("o projeto não tem o lote: a estatística precisa do contorno do terreno")
    terreno = Polygon(lt["contorno"]).buffer(0)
    nv = M.niveis(doc)

    pisos = sorted({float(nv[a["nivel"]]["cota"]) for a in _elementos(doc, "ambiente") if a.get("nivel") in nv})
    andares: List[List[float]] = []
    for c in pisos:
        if andares and c - andares[-1][0] <= MESMO_ANDAR:
            andares[-1].append(c)
        else:
            andares.append([c])
    nomes = {}
    for n in nv.values():
        nomes.setdefault(float(n["cota"]), n["nome"])

    def cota(a, chave="nivel"):
        n = nv.get(a.get(chave))
        return float(n["cota"]) if n else None

    lajes = [(cota(a), float(nv[a["nivel"]].get("laje", 100)), a) for a in _elementos(doc, "laje") if cota(a) is not None]
    telhados = _elementos(doc, "telhado")
    lista = []
    for i, cotas in enumerate(andares):
        base, topo_piso = cotas[0], cotas[-1]
        limite = andares[i + 1][0] if i + 1 < len(andares) else topo_piso + ANDAR_MAX
        limite = min(limite, topo_piso + ANDAR_MAX)
        fech = []
        for a in _elementos(doc, "ambiente"):
            if cota(a) in cotas:
                x0, x1, y0, y1 = map(float, a["ret"])
                fech.append(box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        for a in _elementos(doc, "parede"):
            if cota(a, "base") in cotas:
                fech.append(LineString([a["p0"], a["p1"]]).buffer(TIPOS[a["tipo"]].espessura / 2, cap_style="square",
                                                                   join_style="mitre"))
        fechada = _preencher(unary_union(fech)).intersection(terreno)
        teto = []
        for c, esp, a in lajes:
            if c - esp - base >= PE_DIREITO_MIN and c <= limite:
                teto.append(Polygon(a["contorno"], [f for f in a.get("furos") or []]))
        for a in telhados:
            for ag in a["aguas"]:
                if base + PE_DIREITO_MIN <= float(ag["z_beiral"]) <= limite:
                    x0, x1, y0, y1 = map(float, ag["ret"])
                    teto.append(box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        area = unary_union([fechada] + teto).intersection(terreno)
        lista.append({"andar": " + ".join(nomes.get(c, f"{c:+.0f}") for c in cotas), "geo": area,
                      "fechada": round(fechada.area / 1e6, 2), "coberta_aberta": round((area.area - fechada.area) / 1e6, 2),
                      "area": round(area.area / 1e6, 2)})

    projecao = unary_union([a["geo"] for a in lista]) if lista else Polygon()
    permeavel = unary_union([Polygon(p).buffer(0) for p in lt.get("permeaveis") or []] or [Polygon()])
    permeavel = permeavel.intersection(terreno).difference(projecao)
    t = terreno.area
    construir = sum(a["area"] for a in lista)
    perm = permeavel.area / 1e6
    r = {
        "terreno": round(t / 1e6, 2),
        "construir": round(construir, 2),
        "andares": [{k: v for k, v in a.items() if k != "geo"} for a in lista],
        "projecao": round(projecao.area / 1e6, 2),
        "permeavel": round(perm, 2),
        "impermeavel": round(t / 1e6 - perm, 2),
        "taxa_ocupacao": round(100 * projecao.area / t, 1),
        "taxa_permeabilidade": round(100 * permeavel.area / t, 1),
        "taxa_impermeabilizacao": round(100 * (t - permeavel.area) / t, 1),
        "coeficiente": round(construir * 1e6 / t, 2),
    }
    if com_geometria:
        r["geometria"] = {"terreno": terreno, "projecao": projecao, "permeavel": permeavel,
                          "andares": [a["geo"] for a in lista]}
    return r


def _m2(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " m²"


def _pc(v: float) -> str:
    return f"{v:.1f}".replace(".", ",") + " %"


def quadro(r: Dict) -> List[tuple]:
    """as linhas do quadro de estatística da prancha (a ordem do modelo do Aprova Fácil)"""
    return [("Área do terreno", _m2(r["terreno"])),
            ("Área total a construir", _m2(r["construir"])),
            ("Taxa de impermeabilização", _pc(r["taxa_impermeabilizacao"])),
            ("Taxa de permeabilidade", _pc(r["taxa_permeabilidade"])),
            ("Taxa de ocupação", _pc(r["taxa_ocupacao"])),
            ("Coeficiente de aproveitamento", f"{r['coeficiente']:.2f}".replace(".", ","))]
