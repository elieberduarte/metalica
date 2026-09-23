# -*- coding: utf-8 -*-
"""Gera `dados/catalogo.json`: o que o catálogo de peças tem além de `perfis.json`.

    python dados/gerar_catalogo.py            # regrava o catálogo
    python dados/gerar_catalogo.py --conferir # só compara com o arquivo atual

Três origens, e cada item diz de qual veio (campo `origem`), porque isso muda a confiança:

* **tabela** — lido das tabelas do Anexo do manual (`manual/capitulos/cap17_anexos.html`),
  que são as tabelas de fabricante já conferidas: chapas finas e grossas (17.5), barras
  redondas e chatas (17.6) e parafusos (17.8). Quando o manual não está ao lado do
  sistema (instalação do usuário), valem as cópias gravadas aqui embaixo, que saíram
  dessas mesmas tabelas.
* **calculado** — séries comerciais de perfis formados a frio (NBR 6355) e de cantoneiras
  cujas propriedades são calculadas pelo método linear da NBR 14762 (linha média, cantos
  arredondados), o mesmo de `nucleo/perfis_fabrica.py`. Divergem 1 % a 8 % das tabelas de
  fabricante, que arredondam e às vezes divergem entre si — por isso ficam marcadas.
* **perfis.json** — os laminados W/HP, U, cantoneiras em polegada e tubos já extraídos
  pelo `extrai_perfis.py`; o catálogo os lê de lá, não os repete aqui.

O catálogo serve a três coisas: consultar peças na interface, oferecer alternativas na
troca de perfil da análise (mais leve/mais pesado, com o impacto no peso) e, adiante,
desenhar em 2D escolhendo a peça pelo catálogo.
"""
import json
import math
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SISTEMA = os.path.dirname(BASE)
if SISTEMA not in sys.path:
    sys.path.insert(0, SISTEMA)

MANUAL = os.path.join(SISTEMA, "..", "manual", "capitulos", "cap17_anexos.html")
SAIDA = os.path.join(BASE, "catalogo.json")

RHO = 7850.0        # kg/m³


# =====================================================================================
# 1. Séries comerciais dos formados a frio (NBR 6355) e das cantoneiras
# =====================================================================================

#: U simples formado a frio: (altura, mesa) × espessuras usuais, em mm (NBR 6355, série U).
SERIE_U = [
    (50, 25), (75, 40), (100, 40), (100, 50), (125, 50), (150, 50), (150, 60),
    (200, 75), (250, 85), (300, 85),
]
#: Ue (U enrijecido): (altura, mesa, enrijecedor).
SERIE_UE = [
    (50, 25, 10), (75, 40, 15), (100, 40, 17), (100, 50, 17), (125, 50, 17),
    (127, 50, 17), (150, 60, 20), (150, 75, 20), (200, 75, 20), (200, 75, 25),
    (250, 85, 25), (300, 85, 25), (300, 100, 25),
]
#: Espessuras comerciais de chapa para dobrar (mm) — as mesmas da tabela de chapas finas.
ESPESSURAS_FF = [1.20, 1.50, 1.95, 2.25, 2.65, 3.00, 3.75, 4.25, 4.75]

#: Cantoneiras de abas iguais em milímetro: (aba, espessura). As de espessura fina são as
#: formadas a frio que a fábrica dobra; as grossas equivalem às laminadas métricas.
SERIE_L_MM = [
    (20, 2.25), (25, 2.25), (30, 2.25), (30, 3.00), (40, 2.25), (40, 3.00),
    (50, 2.25), (50, 3.00), (50, 4.00), (50, 5.00), (60, 3.00), (60, 5.00),
    (60, 6.00), (65, 6.00), (75, 6.00), (75, 8.00), (100, 8.00), (100, 10.00),
]
#: Cantoneiras de abas desiguais (aba maior, aba menor, espessura).
SERIE_L_DESIGUAL = [
    (50, 30, 2.25), (60, 40, 3.00), (75, 50, 3.00), (75, 50, 6.00), (100, 75, 8.00),
]


def _fmt(x, casas=2):
    return round(float(x), casas)


def perfis_frio():
    """Séries U e Ue pelo método linear da NBR 14762 (nucleo/nbr14762.py)."""
    from nucleo import nbr14762
    itens = []
    for h, bf in SERIE_U:
        for t in ESPESSURAS_FF:
            if bf < 8 * t or h < 10 * t:            # relação largura/espessura sem sentido
                continue
            try:
                sec = nbr14762.propriedades_u(h, bf, t)
            except Exception:
                continue
            itens.append(_do_frio(sec, "U", h, bf, 0.0, t))
    for h, bf, d in SERIE_UE:
        for t in ESPESSURAS_FF:
            if bf < 8 * t or d < 4 * t:
                continue
            try:
                sec = nbr14762.propriedades_ue(h, bf, d, t)
            except Exception:
                continue
            itens.append(_do_frio(sec, "Ue", h, bf, d, t))
    return itens


def _do_frio(sec, familia, h, bf, d, t):
    return {
        "nome": sec.nome, "familia": familia, "grupo": "formado a frio",
        "dim": ("%g×%g×%g" % (h, bf, t)) if not d else ("%g×%g×%g×%g" % (h, bf, d, t)),
        "d": h, "bf": bf, "enrijecedor": d or None, "t": t,
        "massa": _fmt(sec.massa, 2), "A": _fmt(sec.A, 3),
        "Ix": _fmt(sec.Ix, 1), "Wx": _fmt(sec.Wx, 2), "rx": _fmt(sec.rx, 2),
        "Iy": _fmt(sec.Iy, 1), "Wy": _fmt(sec.Wy, 2), "ry": _fmt(sec.ry, 2),
        "J": _fmt(sec.J, 4), "Cw": _fmt(sec.Cw, 1), "x0": _fmt(sec.x0, 3), "r0": _fmt(sec.r0, 3),
        "norma": "NBR 6355 (dimensões) e NBR 14762 (propriedades)",
        "origem": "calculado",
        "uso": "terças, longarinas, banzos e diagonais de treliça" if familia == "Ue"
               else "travessas, montantes, diagonais e banzos leves",
    }


def cantoneiras():
    """Cantoneiras em milímetro, iguais e desiguais, pelo método linear."""
    from nucleo.perfis_fabrica import perfil_cantoneira
    itens = []
    for b, t in SERIE_L_MM:
        p = perfil_cantoneira(b, b, t)
        if not p.dados.get("sintetico"):
            continue                                  # já está no perfis.json (polegada)
        itens.append(_da_cantoneira(p, b, b, t))
    for b1, b2, t in SERIE_L_DESIGUAL:
        p = perfil_cantoneira(b1, b2, t)
        itens.append(_da_cantoneira(p, b1, b2, t))
    return itens


def _da_cantoneira(p, b1, b2, t):
    d = p.dados
    frio = bool(d.get("formado_a_frio"))
    return {
        "nome": p.nome, "familia": "L", "grupo": "formado a frio" if frio else "laminado",
        "dim": "%g×%g×%g" % (b1, b2, t), "b": max(b1, b2), "b2": min(b1, b2), "t": t,
        "massa": d["massa"], "A": d["A"], "Ix": d["Ix"], "Iy": d["Iy"],
        "Wx": d["Wx"], "Wy": d["Wy"], "rx": d["rx"], "ry": d["ry"], "rmin": d["rmin"],
        "J": d["J"],
        "norma": "NBR 6355" if frio else "NBR 6109 (dimensões); propriedades calculadas",
        "origem": "calculado",
        "uso": "diagonais e montantes de treliça, travamentos, agulhamento",
    }


# =====================================================================================
# 2. Chapas, barras e parafusos (tabelas do Anexo)
# =====================================================================================

#: Chapas finas (bitola MSG) — espessura em mm e massa em kg/m². Tabela 17.5 do manual.
CHAPAS_FINAS = [
    ("26", 0.45, 3.5, "telhas leves"),
    ("24", 0.60, 4.7, "telhas, calhas leves"),
    ("22", 0.75, 5.9, "calhas, rufos"),
    ("20", 0.90, 7.1, "steel deck leve, dutos"),
    ("18", 1.20, 9.4, "steel deck, perfis leves"),
    ("16", 1.50, 11.8, "Ue leves, forros"),
    ("14", 1.90, 14.9, "Ue leves"),
    ("13", 2.25, 17.7, "Ue de terças"),
    ("12", 2.65, 20.8, "Ue de terças e longarinas"),
    ("11", 3.00, 23.6, "Ue, chapa xadrez, perfis dobrados"),
    ("10", 3.40, 26.7, "perfis dobrados"),
    ("8", 4.25, 33.4, "perfis dobrados pesados, chapa xadrez"),
]
#: Chapas grossas (polegada) — espessura em mm e massa em kg/m². Tabela 17.5.
CHAPAS_GROSSAS = [
    ('1/4"', 6.35, 49.8, "chapas de terça, gussets leves, enrijecedores"),
    ('5/16"', 7.94, 62.3, "gussets, chapas de ligação"),
    ('3/8"', 9.53, 74.8, "gussets, chapas de alma, cantoneiras de apoio"),
    ('1/2"', 12.70, 99.7, "chapas de topo leves, placas de base pequenas"),
    ('5/8"', 15.90, 124.7, "chapas de topo, placas de base"),
    ('3/4"', 19.05, 149.5, "placas de base, chapas de topo de pórticos"),
    ('7/8"', 22.20, 174.5, "chapas de topo"),
    ('1"', 25.40, 199.4, "placas de base engastadas, emendas"),
    ('1.1/4"', 31.75, 249.2, "placas de base pesadas"),
    ('1.1/2"', 38.10, 299.1, "placas de base de pilares pesados"),
    ('2"', 50.80, 398.8, "bases especiais, chapas de apoio"),
]
#: Barras redondas — diâmetro (mm), área (cm²), massa (kg/m) e uso. Tabela 17.6.
BARRAS_REDONDAS = [
    (6.3, 0.31, 0.25, "ligações de grade"),
    (8.0, 0.50, 0.40, "pendurais leves"),
    (10.0, 0.79, 0.62, "correntes leves"),
    (12.5, 1.23, 0.96, "correntes, pendurais"),
    (16.0, 2.01, 1.58, "correntes, contraventamento leve"),
    (20.0, 3.14, 2.47, "contraventamento de cobertura"),
    (22.0, 3.80, 2.99, "contraventamento, chumbadores"),
    (25.0, 4.91, 3.86, "contraventamento pesado, chumbadores"),
    (32.0, 8.04, 6.32, "chumbadores de bases engastadas"),
]
#: Barras redondas em polegada, as que a fábrica usa nos tirantes ("FE RED 3/8\"").
BARRAS_POLEGADA = ['1/4"', '5/16"', '3/8"', '1/2"', '5/8"', '3/4"', '7/8"', '1"']
#: Barras chatas — (largura mm, espessura mm, massa kg/m, rótulo em polegada). Tabela 17.6.
BARRAS_CHATAS = [
    (25.4, 3.18, 0.63, '1"×1/8"'), (25.4, 4.76, 0.95, '1"×3/16"'), (25.4, 6.35, 1.27, '1"×1/4"'),
    (38.1, 4.76, 1.42, '1½"×3/16"'), (38.1, 6.35, 1.90, '1½"×1/4"'),
    (50.8, 4.76, 1.90, '2"×3/16"'), (50.8, 6.35, 2.53, '2"×1/4"'), (50.8, 9.53, 3.80, '2"×3/8"'),
    (50.8, 12.70, 5.06, '2"×1/2"'), (63.5, 6.35, 3.17, '2½"×1/4"'), (63.5, 9.53, 4.75, '2½"×3/8"'),
    (76.2, 6.35, 3.80, '3"×1/4"'), (76.2, 9.53, 5.70, '3"×3/8"'), (76.2, 12.70, 7.60, '3"×1/2"'),
    (101.6, 9.53, 7.60, '4"×3/8"'), (101.6, 12.70, 10.1, '4"×1/2"'),
    (200.0, 4.75, 7.46, "200×4,75 (rodapé)"),
]


def chapas():
    itens = []
    for bitola, esp, kgm2, uso in CHAPAS_FINAS:
        itens.append({"nome": "CH %s mm" % ("%g" % esp).replace(".", ","), "familia": "chapa",
                      "grupo": "chapa fina", "t": esp, "bitola_msg": bitola,
                      "massa_m2": kgm2, "uso": uso, "origem": "tabela",
                      "norma": "bitola MSG; massa = 7,85 kg/m² por mm"})
    for pol, esp, kgm2, uso in CHAPAS_GROSSAS:
        itens.append({"nome": "CH %s mm (%s)" % (("%g" % esp).replace(".", ","), pol),
                      "familia": "chapa", "grupo": "chapa grossa", "t": esp, "polegada": pol,
                      "massa_m2": kgm2, "uso": uso, "origem": "tabela",
                      "norma": "espessura em polegada; massa = 7,85 kg/m² por mm"})
    return itens


def barras():
    from nucleo.perfis_fabrica import polegadas_mm
    itens = []
    for d, A, massa, uso in BARRAS_REDONDAS:
        itens.append({"nome": "Barra redonda ø %s mm" % ("%g" % d).replace(".", ","),
                      "familia": "barra_redonda", "grupo": "barra", "d": d,
                      "A": A, "massa": massa, "uso": uso, "origem": "tabela",
                      "norma": "kg/m = 0,00617·ø²"})
    for pol in BARRAS_POLEGADA:
        d = polegadas_mm(pol)
        A = math.pi * (d / 10.0) ** 2 / 4
        itens.append({"nome": 'Barra redonda ø %s' % pol, "familia": "barra_redonda",
                      "grupo": "barra", "d": _fmt(d, 2), "A": _fmt(A, 3),
                      "massa": _fmt(A * RHO * 1e-4, 3), "polegada": pol,
                      "uso": "tirantes e contraventamentos (bitola de fábrica)",
                      "origem": "calculado", "norma": "seção cheia redonda"})
    for b, t, massa, rotulo in BARRAS_CHATAS:
        itens.append({"nome": "Barra chata %s" % rotulo, "familia": "barra_chata",
                      "grupo": "barra", "b": b, "t": t, "A": _fmt(b * t / 100.0, 3),
                      "massa": massa, "uso": "travessas, enrijecedores, grades",
                      "origem": "tabela", "norma": "kg/m = 0,00785·b·t (mm)"})
    return itens


def parafusos():
    """Parafusos e barras roscadas do catálogo de materiais, com as medidas usuais."""
    from nucleo import materiais as mat
    itens = []
    for nome, p in mat.PARAFUSOS.items():
        # DIAMETROS: bitola -> (diâmetro cm, área bruta cm², área efetiva à tração cm²)
        for d_nome, medidas in mat.DIAMETROS.items():
            d_cm, Ab, Ae = medidas[0], medidas[1], medidas[2]
            d_mm = d_cm * 10.0
            itens.append({"nome": "%s %s" % (nome, d_nome), "familia": "parafuso",
                          "grupo": "conector", "material": nome, "bitola": d_nome,
                          "d": _fmt(d_mm, 2), "Ab": Ab, "Ae": Ae,
                          "fub_kN_cm2": p.fub, "grupo_norma": p.grupo,
                          "furo_padrao": _fmt(d_mm + (1.5 if d_mm <= 22 else 2.0), 1),
                          "origem": "tabela", "norma": "NBR 8800, Tabelas 11 e 12",
                          "uso": "ligações parafusadas"})
    return itens


# =====================================================================================
# 3. Montagem
# =====================================================================================

def montar():
    dados = {
        "leia_me": ("Catálogo de peças do Metálica. `origem` diz de onde veio cada item: "
                    "tabela (anexo do manual, valores de fabricante), calculado (método "
                    "linear da NBR 14762, para as séries formadas a frio e cantoneiras "
                    "métricas). Os laminados W/HP, U, cantoneiras em polegada e tubos "
                    "estão em perfis.json e entram no catálogo por lá."),
        "gerado_por": "dados/gerar_catalogo.py",
        "itens": [],
    }
    dados["itens"].extend(perfis_frio())
    dados["itens"].extend(cantoneiras())
    dados["itens"].extend(chapas())
    dados["itens"].extend(barras())
    dados["itens"].extend(parafusos())
    return dados


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    dados = montar()
    por_familia = {}
    for it in dados["itens"]:
        por_familia[it["familia"]] = por_familia.get(it["familia"], 0) + 1
    if "--conferir" in argv:
        antigo = json.load(open(SAIDA, encoding="utf-8")) if os.path.exists(SAIDA) else {}
        iguais = json.dumps(antigo.get("itens"), sort_keys=True) == json.dumps(dados["itens"], sort_keys=True)
        print("catálogo %s (%d itens)" % ("igual" if iguais else "DIFERENTE", len(dados["itens"])))
        return 0 if iguais else 1
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    print("%s: %d itens" % (os.path.relpath(SAIDA, SISTEMA), len(dados["itens"])))
    for fam, n in sorted(por_familia.items(), key=lambda kv: -kv[1]):
        print("   %-14s %4d" % (fam, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
