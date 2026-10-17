# -*- coding: utf-8 -*-
"""Peso dos perfis dobrados: teórico × com o desconto das dobras.

REGRA DE PESO (usuário, 14/10): kg/m = (soma das medidas externas − 2·t por dobra) × t × 8 kg/m² por mm — o Ue
200×75×25×2,25 dá (200 + 150 + 50 − 18) × 2,25 × 0,008 = 6,876 kg/m. É ela que pesa as peças e dá o kg/m da compra e do
catálogo (`kg_m_regra`, `kg_m_do_formado`). O texto abaixo (o arco da dobra na linha média) segue valendo só para o
corte da tira na fábrica.

O modelo 3D (e o peso que sai da malha) tem as dobras em canto vivo. Na fábrica o perfil
sai de uma tira da bobina, e a largura dessa tira — o **desenvolvido** — é menor que a
soma das medidas externas: em cada dobra o material faz um arco em vez de dois lados de
um canto. É o "desconto das dobras".

Para uma dobra de 90° com raio interno `ri` e linha neutra a `k·t` da face interna:

    desconto = 2·(ri + t) − (π/2)·(ri + k·t)

Com ri = t e k = 0,5 (linha média, a convenção da NBR 6355 para as tabelas de massa):
desconto = (4 − 0,75·π)·t ≈ 1,64·t por dobra. Assim o U 150×50×2,25 dá 242,6 mm de tira e
4,28 kg/m — o valor da tabela da norma.

    peso teórico       = soma das medidas externas × t × comprimento × 7850 kg/m³
    peso com desconto  = desenvolvido × t × comprimento × 7850 kg/m³

Os furos não entram em nenhum dos dois (o peso do modelo já os desconta).
"""
import math
import re
from typing import Optional

RHO = 7.85e-3          # kg por (mm² · m)
#: Raio interno da dobra em espessuras e posição da linha neutra (fração de t).
RAIO_INTERNO = 1.0
FATOR_K = 0.5

#: A REGRA DE PESO da fábrica (usuário, 14/10, a planilha dele: Ue 200×75×25×2,25 = (0,2 + 2·0,075 + 2·0,025 − 8·0,00225)
#: × 18 = 6,876 kg/m): o desenvolvido para o peso desconta 2·t por dobra e a chapa pesa 8 kg/m² por mm de espessura. Vale
#: para o peso e o kg/m de todo perfil dobrado (posições, compra, catálogo). O desconto geométrico da dobra
#: (`desconto_por_dobra`, o arco na linha média) continua só para o corte da tira na fábrica (fabrica.py).
DESCONTO_PESO_T = 2.0              # espessuras descontadas por dobra
KG_M2_POR_MM = 8.0                 # kg/m² de chapa por mm de espessura
RHO_PESO = KG_M2_POR_MM * 1e-3     # kg por (mm de tira × mm de espessura × m de perfil)

#: nº de dobras e medidas externas somadas por família (h = alma, b = aba, d = enrijecedor)
_FAMILIAS = {
    "U": (2, lambda h, b, d: h + 2 * b),
    "UE": (4, lambda h, b, d: h + 2 * b + 2 * d),
    "Z": (2, lambda h, b, d: h + 2 * b),
    "ZE": (4, lambda h, b, d: h + 2 * b + 2 * d),
    "L": (1, lambda h, b, d: h + b),
    "CR": (4, lambda h, b, d: h + 2 * b + 2 * d),     # cartola: alma, abas e as duas mesas
}


def desconto_por_dobra(t: float, ri: Optional[float] = None, k: float = FATOR_K) -> float:
    """Quanto a tira perde, em mm, a cada dobra de 90°."""
    ri = RAIO_INTERNO * t if ri is None else ri
    return 2.0 * (ri + t) - math.pi / 2.0 * (ri + k * t)


def _num(txt: str) -> float:
    return float(txt.replace(",", "."))


def geometria(perfil: str) -> Optional[dict]:
    """Família, medidas e espessura de um perfil dobrado pelo nome ("U150X50X2.28",
    "C127X50X17X#14", "UE 100x40x17x2,00", "L50X50X2.25"). None para o que não é dobrado
    da chapa (laminado em polegada, W, barra redonda, tubo)."""
    if not perfil or "'" in perfil or '"' in perfil:
        return None
    s = perfil.upper().replace(" ", "").replace("×", "X")
    s = re.sub(r"\(FF\)$", "", s)
    m = re.match(r"^(UE|ZE|CR|U|C|Z|L)(\d+(?:[.,]\d+)?)X(\d+(?:[.,]\d+)?)(?:X(\d+(?:[.,]\d+)?))?X(#\d+|\d+(?:[.,]\d+)?)$", s)
    if not m:
        return None
    fam, h, b, d, esp = m.groups()
    if esp.startswith("#"):
        from nucleo.perfis_fabrica import BITOLAS
        t = BITOLAS.get(int(esp[1:]))
        if not t:
            return None
    else:
        t = _num(esp)
    h, b = _num(h), _num(b)
    d = _num(d) if d else 0.0
    if fam == "C":
        fam = "UE" if d else "U"
    elif fam in ("U", "Z") and d:
        fam += "E"
    elif fam == "L" and d:
        return None
    if fam not in _FAMILIAS or t <= 0 or t > 0.25 * min(h, b):
        return None
    dobras, soma = _FAMILIAS[fam]
    return {"familia": fam, "h": h, "b": b, "d": d, "t": t, "dobras": dobras, "soma_externa": soma(h, b, d)}


def kg_m_regra(soma_externa: float, n_dobras: int, t: float) -> float:
    """kg/m do perfil dobrado pela regra da fábrica: (soma das medidas externas − 2·t por dobra) × t × 8 kg/m² por mm."""
    return (soma_externa - n_dobras * DESCONTO_PESO_T * t) * t * RHO_PESO


#: nº de dobras e soma das medidas externas das famílias do catálogo (h = alma, b = aba, d = enrijecedor; na cantoneira
#: dobrada b e b2 são as duas abas)
_FAMILIAS_CATALOGO = {"U": "U", "Ue": "UE", "Ze": "ZE", "Z45": "ZE", "Cr": "CR"}


def kg_m_do_formado(familia: str, h: float, b: float, d: float, t: float, b2: float = 0.0) -> Optional[float]:
    """O kg/m pela regra da fábrica para um item do catálogo ("formado a frio"): U, Ue, Ze, Z45 (as quatro dobras),
    cartola e cantoneira dobrada. None quando a família não é dobrada."""
    if not t or t <= 0:
        return None
    if familia == "L":
        return kg_m_regra(float(b) + float(b2 or b), 1, float(t)) if b else None
    if familia == "Cr":
        # cartola no catálogo: altura × topo × abas ("Cr 20×30×12" = laterais de 20, topo de 30, abas de 12)
        return kg_m_regra(float(b) + 2.0 * float(h) + 2.0 * float(d or 0.0), 4, float(t)) if h and b else None
    fam = _FAMILIAS_CATALOGO.get(familia)
    if fam is None or not h or not b:
        return None
    n, soma = _FAMILIAS[fam]
    return kg_m_regra(soma(float(h), float(b), float(d or 0.0)), n, float(t))


def pesos(perfil: str, comprimento_m: float = 1.0) -> Optional[dict]:
    """{soma_externa, dobras, desconto_dobra, desenvolvido, kg_m_teorico, kg_m_desconto,
    peso_teorico, peso_desconto} para `comprimento_m` metros do perfil, pela regra de peso da fábrica (2·t por dobra,
    8 kg/m² por mm): o teórico sem o desconto das dobras, o "com desconto" com ele."""
    g = geometria(perfil)
    if g is None:
        return None
    desc = DESCONTO_PESO_T * g["t"]
    desenv = g["soma_externa"] - g["dobras"] * desc
    kt = g["soma_externa"] * g["t"] * RHO_PESO
    kd = kg_m_regra(g["soma_externa"], g["dobras"], g["t"])
    return {"familia": g["familia"], "t": g["t"], "soma_externa": round(g["soma_externa"], 2), "dobras": g["dobras"],
            "desconto_dobra": round(desc, 2), "desenvolvido": round(desenv, 1),
            "kg_m_teorico": round(kt, 3), "kg_m_desconto": round(kd, 3),
            "peso_teorico": kt * comprimento_m, "peso_desconto": kd * comprimento_m}


def massa_da_norma(perfil: str) -> Optional[float]:
    """kg/m da tabela do catálogo (NBR 6355) para o mesmo perfil, quando existir."""
    g = geometria(perfil)
    if g is None:
        return None
    try:
        from nucleo import catalogo
    except Exception:                                  # noqa: BLE001
        return None
    fam = {"U": "U", "UE": "Ue", "ZE": "Ze", "L": "L", "CR": "Cr"}.get(g["familia"])
    if not fam:
        return None
    for it in catalogo.itens(fam):
        if it.grupo != "formado a frio":
            continue
        # as medidas pelo campo "dim" ("150×50×17×2,25"; cantoneira de abas iguais "50×50×2,25")
        try:
            dims = [_num(x) for x in str(it.dados.get("dim") or "").split("×")]
        except ValueError:
            continue
        if len(dims) < 3:
            continue
        h, b, t = dims[0], dims[1], dims[-1]
        d = dims[2] if len(dims) == 4 else 0.0
        if (abs(h - g["h"]) < 0.6 and abs(b - g["b"]) < 0.6 and abs(t - g["t"]) < 0.011
                and abs(d - g["d"]) < 0.6):
            return float(it.massa) if it.massa else None
    return None


#: Espessuras (mm) de cada bitola de chapa: a MSG (é a que o TecnoMETAL escreve no nome do
#: perfil — #8 = 4,176 → "4.18") e a ABNT/fornecedores (nucleo/perfis_fabrica.BITOLAS e o
#: catálogo). A fábrica chama o perfil pelo número da bitola: U100X50X#8.
ESPESSURAS_BITOLA = {
    7: (4.554, 4.5), 8: (4.176, 4.25), 9: (3.797, 3.75), 10: (3.416, 3.35), 11: (3.038, 3.0),
    12: (2.657, 2.65, 2.7), 13: (2.278, 2.25, 2.3), 14: (1.897, 1.9, 1.95, 2.0), 15: (1.709, 1.7, 1.8),
    16: (1.519, 1.5, 1.55), 18: (1.214, 1.2), 20: (0.912, 0.9),
}
TOLERANCIA_BITOLA = 0.035


def bitola_de(t: float) -> Optional[int]:
    """Número da bitola cuja espessura (MSG ou ABNT) está a até 0,035 mm de `t`."""
    melhor = None
    for num, ts in ESPESSURAS_BITOLA.items():
        for x in ts:
            d = abs(t - x)
            if d <= TOLERANCIA_BITOLA and (melhor is None or d < melhor[0]):
                melhor = (d, num)
    return melhor[1] if melhor else None


def com_bitola(perfil: str) -> str:
    """O nome do perfil dobrado como a fábrica escreve: a espessura pelo número da bitola
    ("U100X50X4.18" → "U100X50X#8", "C150X50X17X2.25" → "C150X50X17X#13"). Perfil que não é
    dobrado da chapa, ou espessura fora das bitolas, fica como está. A polegada que o arquivo traz com as
    duas aspas separadas ("1/4' '") sai junta ("1/4''"). O nome do Revit ("Família:Tipo:ID") sai só o tipo."""
    if perfil and ":" in perfil:
        from nucleo.catalogo import nome_do_ifc
        perfil = nome_do_ifc(perfil)
    if perfil:
        perfil = re.sub(r"'\s+'", "''", perfil)
    if not perfil or geometria(perfil) is None:
        return perfil
    m = re.search(r"(?i)x\s*(\d+(?:[.,]\d+)?)\s*(\(FF\))?\s*$", perfil)
    if not m:
        return perfil
    b = bitola_de(_num(m.group(1)))
    if b is None:
        return perfil
    return perfil[:m.start(1)] + "#%d" % b + (perfil[m.end(1):] if m.group(2) else "")


def com_bitola_e_mm(perfil: str) -> str:
    """O nome do perfil dobrado para quem lê, com a bitola e a espessura em mm juntas (pedido do usuário, 05/10:
    "sempre coloque #chapa/mm — C127X50X17X#13/2.25mm"): "U150X50X2.28" → "U150X50X#13/2.28mm", "C127X50X17X#14" →
    "C127X50X17X#14/1.90mm" (a espessura da bitola na tabela da fábrica). O que não é dobrado da chapa (W, L em
    polegada, barra redonda) e a espessura fora das bitolas ficam como em `com_bitola`. Só para mostrar: o nome
    gravado (o que o catálogo e o orçamento leem) não muda; nome de camada não leva "/" (AutoCAD)."""
    p = com_bitola(perfil)
    if not p or re.search(r"#\d+/", p):
        return p
    if perfil and ":" in perfil:
        from nucleo.catalogo import nome_do_ifc
        perfil = nome_do_ifc(perfil)
    g = geometria(perfil)
    m = re.search(r"#(\d+)", p)
    if g is None or not m:
        return p
    return p[:m.end()] + "/%.2fmm" % g["t"] + p[m.end():]
