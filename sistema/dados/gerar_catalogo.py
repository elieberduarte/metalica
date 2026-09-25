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
* **fornecedores** — `dados/fornecedores/*.json`, transcrições dos catálogos públicos
  (seção 3 abaixo): entram o que as séries não têm, marcado `fornecedor: True`, e quem
  fabrica cada perfil (`fabricantes`).

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


def _dim(*medidas):
    """Medidas em mm para exibir: "127×50×17×1,95"."""
    return "×".join(("%g" % m).replace(".", ",") for m in medidas)


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
        "dim": _dim(h, bf, d, t) if d else _dim(h, bf, t),
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
        "dim": _dim(b1, b2, t), "b": max(b1, b2), "b2": min(b1, b2), "t": t,
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
    ("14", 1.90, 14.9, "Ue leves (MSG; a #14 da fábrica é a CH 2,0)"),
    ("14 (fábrica)", 2.00, 15.7, "Ue leves, a #14 da chapa a quente"),
    ("13", 2.25, 17.7, "Ue de terças"),
    ("12", 2.65, 20.8, "Ue de terças e longarinas"),
    ("11", 3.00, 23.6, "Ue, chapa xadrez, perfis dobrados"),
    ("10", 3.40, 26.7, "perfis dobrados (MSG; a #10 da fábrica é a CH 3,35)"),
    ("10 (fábrica)", 3.35, 26.3, "perfis dobrados, a #10 da chapa a quente"),
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
# 3. Catálogos de fornecedores (dados/fornecedores/)
# =====================================================================================
#
# Transcrições dos catálogos públicos (Gerdau, ArcelorMittal, Vallourec, Marcegaglia,
# Perfinasa, Perfilor, Isoeste, Tetraferro, telhas de vários fabricantes). Tudo que vem
# daqui ganha `fornecedor: True` quando não faz parte das séries acima: entra na consulta,
# na busca e na troca de perfil, mas o dimensionamento automático continua escolhendo só
# nas séries padrão. Da NBR 6355 só entram as designações; as propriedades dos formados a
# frio são sempre calculadas (NBR 14762), e a tabela do fabricante, quando existe, fica
# ao lado (`tabela_fabricante`) para quem quiser conferir.

FORNECEDORES = os.path.join(BASE, "fornecedores")

USO_FRIO = {
    "Ze": "terças e longarinas contínuas (o Z encaixa no transpasse)",
    "Z45": "terças e longarinas contínuas, com transpasse",
    "Cr": "terças leves, travessas de fechamento, apoio de forro e de telha",
}


def _ler_fornecedor(nome):
    caminho = os.path.join(FORNECEDORES, nome)
    if not os.path.exists(caminho):
        return {}
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _num(x, casas_min=0):
    """Número com vírgula, sem zeros sobrando ("3,6", "4,75", "50"); `casas_min` força
    ao menos essa quantidade de casas ("3,0")."""
    s = ("%.2f" % float(x)).rstrip("0")
    if s.endswith("."):
        s = s[:-1]
    if casas_min and "." not in s:
        s += "." + "0" * casas_min
    return s.replace(".", ",")


def _marca_fornecedor(reg, fonte):
    fab = fonte.get("fabricante")
    reg["fabricantes"] = [fab] if fab else []
    if fonte.get("tabela_fabricante") and fab:
        reg["tabela_fabricante"] = {fab: fonte["tabela_fabricante"]}
    if fonte.get("fonte"):
        reg["fonte"] = fonte["fonte"]
    if fonte.get("obs"):
        reg["obs"] = fonte["obs"]
    return reg


def _do_z_cartola(fam, h, b, d, t):
    from nucleo import secoes_frio
    s = secoes_frio.propriedades(fam, h, b, d, t)
    return {
        "nome": "%s %s×%s×%s×%s" % (fam, _num(h), _num(b), _num(d), ("%.2f" % t).replace(".", ",")),
        "familia": fam, "grupo": "formado a frio", "dim": _dim(h, b, d, t),
        "d": h, "bf": b, "enrijecedor": d, "t": t,
        "massa": _fmt(s["massa"], 2), "A": _fmt(s["A"], 3),
        "Ix": _fmt(s["Ix"], 1), "Wx": _fmt(s["Wx"], 2), "rx": _fmt(s["rx"], 2),
        "Iy": _fmt(s["Iy"], 1), "Wy": _fmt(s["Wy"], 2), "ry": _fmt(s["ry"], 2),
        "Ixy": _fmt(s["Ixy"], 1), "I1": _fmt(s["I1"], 1), "I2": _fmt(s["I2"], 1),
        "alfa": _fmt(s["alfa"], 1), "rmin": _fmt(s["rmin"], 2),
        "J": _fmt(s["J"], 4), "Cw": _fmt(s["Cw"], 1), "x0": _fmt(s["x0"], 3), "r0": _fmt(s["r0"], 3),
        "norma": "NBR 6355 (dimensões) e NBR 14762 (propriedades)", "origem": "calculado",
        "uso": USO_FRIO.get(fam, ""),
    }


def frio_de_fornecedores():
    """Formados a frio dos catálogos: U, Ue, Ze, Z45, cartola e cantoneira dobrada.
    Linhas sem as medidas completas (o Z da Isoeste só dá a altura) ficam de fora."""
    from nucleo import nbr14762
    from nucleo.perfis_fabrica import perfil_cantoneira
    itens = []
    for p in _ler_fornecedor("formados_a_frio.json").get("perfis", []):
        fam, h, b, d, t = p.get("familia"), p.get("h"), p.get("b"), p.get("D"), p.get("t")
        if not (h and b and t) or (fam in ("Ue", "Ze", "Z45", "Cr") and not d):
            continue
        try:
            if fam == "U":
                reg = _do_frio(nbr14762.propriedades_u(h, b, t), "U", h, b, 0.0, t)
            elif fam == "Ue":
                reg = _do_frio(nbr14762.propriedades_ue(h, b, d, t), "Ue", h, b, d, t)
            elif fam == "L":
                b1, b2 = max(h, b), min(h, b)
                reg = _da_cantoneira(perfil_cantoneira(b1, b2, t), b1, b2, t)
            elif fam in USO_FRIO:
                reg = _do_z_cartola(fam, h, b, d, t)
            else:
                continue
        except Exception:
            continue
        itens.append(_marca_fornecedor(reg, p))
    return itens


def laminados_de_fornecedores():
    """W e HP (Gerdau), I e U americanos e cantoneiras em polegada (Gerdau, ArcelorMittal).
    Linhas que o catálogo só dá com a massa entram sem as propriedades."""
    itens = []
    for p in _ler_fornecedor("laminados_I.json").get("perfis", []):
        reg = {k: v for k, v in p.items() if v is not None and k not in ("fabricante", "rotulo_original")}
        reg.update({"nome": p["nome"], "familia": "I", "serie": p.get("familia"),
                    "grupo": "laminado", "origem": "tabela",
                    "norma": "ASTM A572 Gr. 50 / NBR 5884 (tabela do fabricante)",
                    "uso": "pilares e estacas" if p.get("familia") == "HP" else "vigas e pilares"})
        itens.append(_marca_fornecedor(reg, p))
    lam = _ler_fornecedor("laminados_U_L_barras.json")
    usos = {"U": "terças pesadas, vigas de tapamento, travessas",
            "I": "vigas leves, trilhos de talha",
            "L": "diagonais, montantes, travamentos e agulhamento"}
    for fam in ("U", "I", "L"):
        for p in lam.get(fam, []):
            reg = {k: v for k, v in p.items() if v is not None and k not in ("fabricante", "obs", "rz_min")}
            if p.get("rz_min"):
                reg["rmin"] = p["rz_min"]
            if fam == "L" and not p.get("b2"):
                reg["b2"] = p.get("b")
            reg.update({"familia": fam, "grupo": "laminado",
                        "origem": "tabela", "so_massa": None if p.get("A") else True,
                        "norma": "ASTM A36 (tabela do fabricante)", "uso": usos[fam]})
            itens.append(_marca_fornecedor(reg, p))
    return itens


#: Raios dos cantos do tubo retangular com costura (externo 2t, interno t), como nas
#: tabelas de fabricante; em canto vivo a área e a inércia saíam 3 % a 5 % acima.
RAIO_EXTERNO_TUBO = 2.0
RAIO_INTERNO_TUBO = 1.0


def _cantos(r):
    """Área que o arredondamento de raio r tira de um canto e a distância do centroide
    dela ao vértice, em cada eixo."""
    a = (1.0 - math.pi / 4.0) * r * r
    c = r * (10.0 - 3.0 * math.pi) / (12.0 - 3.0 * math.pi)
    return a, c


def _props_tubo(tipo, D, b, h, t):
    """Propriedades de tubo pela seção cheia menos o furo; o retangular desconta os quatro
    cantos arredondados (raio externo 2t, interno t). mm → cm."""
    t = t / 10.0
    if tipo == "redondo":
        De = D / 10.0
        Di = De - 2 * t
        A = math.pi * (De ** 2 - Di ** 2) / 4
        I = math.pi * (De ** 4 - Di ** 4) / 64
        W = I / (De / 2)
        r = math.sqrt(I / A)
        return {"A": _fmt(A, 3), "Ix": _fmt(I, 2), "Iy": _fmt(I, 2), "Wx": _fmt(W, 2),
                "Wy": _fmt(W, 2), "rx": _fmt(r, 2), "ry": _fmt(r, 2), "J": _fmt(2 * I, 2)}
    B, H = b / 10.0, h / 10.0
    bi, hi = B - 2 * t, H - 2 * t
    ae, ce = _cantos(RAIO_EXTERNO_TUBO * t)
    ai, ci = _cantos(RAIO_INTERNO_TUBO * t)
    A = (B * H - 4 * ae) - (bi * hi - 4 * ai)
    Ix = ((B * H ** 3 / 12 - 4 * ae * (H / 2 - ce) ** 2)
          - (bi * hi ** 3 / 12 - 4 * ai * (hi / 2 - ci) ** 2))
    Iy = ((H * B ** 3 / 12 - 4 * ae * (B / 2 - ce) ** 2)
          - (hi * bi ** 3 / 12 - 4 * ai * (bi / 2 - ci) ** 2))
    Am = (B - t) * (H - t)
    J = 4 * Am ** 2 * t / (2 * ((B - t) + (H - t)))
    return {"A": _fmt(A, 3), "Ix": _fmt(Ix, 2), "Iy": _fmt(Iy, 2),
            "Wx": _fmt(Ix / (H / 2), 2), "Wy": _fmt(Iy / (B / 2), 2),
            "rx": _fmt(math.sqrt(Ix / A), 2), "ry": _fmt(math.sqrt(Iy / A), 2), "J": _fmt(J, 2)}


def _geo_tubo(tipo, D, b, h, t):
    if tipo == "redondo":
        return ("redondo", round(float(D), 1), round(float(t), 2))
    return (tipo, round(float(max(b, h)), 1), round(float(min(b, h)), 1), round(float(t), 2))


def tubos_de_fornecedores():
    """Tubos Vallourec (sem costura, com a tabela completa) e Marcegaglia (com costura,
    o catálogo só dá a massa: as propriedades são calculadas). Nomes na grafia do
    perfis.json: TC redondo, TQ quadrado, TR retangular; os que ele já tem ficam de fora."""
    ja = set()
    try:
        with open(os.path.join(BASE, "perfis.json"), encoding="utf-8") as f:
            for p in json.load(f).get("tubo", []):
                ja.add(_geo_tubo(p.get("tipo"), p.get("D"), p.get("b"), p.get("h"), p.get("t")))
    except (OSError, ValueError, TypeError):
        pass
    itens, vistos = [], {}
    for p in _ler_fornecedor("tubos.json").get("tubos", []):
        tipo, D, b, h, t = p.get("tipo"), p.get("D"), p.get("b"), p.get("h"), p.get("t")
        if not t or (tipo == "redondo" and not D) or (tipo != "redondo" and not (b and h)):
            continue
        geo = _geo_tubo(tipo, D, b, h, t)
        if geo in ja:
            continue
        if geo in vistos:                      # mesmo tubo nos dois fabricantes
            fab = p.get("fabricante")
            if fab and fab not in vistos[geo]["fabricantes"]:
                vistos[geo]["fabricantes"].append(fab)
            continue
        if tipo == "redondo":
            nome, dim = "TC %s×%s" % (_num(D, 1), _num(t, 1)), "ø" + _dim(D, t)
        elif tipo == "quadrado":
            nome, dim = "TQ %s×%s×%s" % (_num(b), _num(b), _num(t, 1)), _dim(b, b, t)
        else:
            hh, bb = max(b, h), min(b, h)
            nome, dim = "TR %s×%s×%s" % (_num(hh), _num(bb), _num(t, 1)), _dim(hh, bb, t)
        reg = {"nome": nome, "familia": "tubo", "grupo": "tubo", "tipo": tipo, "dim": dim,
               "t": t, "massa": p.get("massa")}
        if tipo == "redondo":
            reg["D"] = D
        else:
            reg["b"], reg["h"] = min(b, h), max(b, h)
        if p.get("A"):
            for k in ("A", "Ix", "Iy", "Wx", "Wy", "rx", "ry", "J", "Zx", "Zy", "Wt"):
                if p.get(k) is not None:
                    reg[k] = p[k]
            reg["origem"] = "tabela"
        else:
            reg.update(_props_tubo(tipo, D, b, h, t))
            reg["origem"] = "calculado"
            if not reg.get("massa"):
                reg["massa"] = _fmt(reg["A"] * RHO * 1e-4, 2)
        reg["norma"] = p.get("norma") or ""
        reg["uso"] = "pilares, banzos e diagonais de treliça aparente, estruturas tubulares"
        if p.get("sob_consulta"):
            reg["sob_consulta"] = True
        _marca_fornecedor(reg, {"fabricante": p.get("fabricante"), "fonte": p.get("fonte")})
        vistos[geo] = reg
        itens.append(reg)
    return itens


def barras_de_fornecedores():
    """Barras redondas e chatas da Gerdau, nos nomes do catálogo ("Barra redonda ø 3/8\"")."""
    lam = _ler_fornecedor("laminados_U_L_barras.json")
    itens = []
    for p in lam.get("barras_redondas", []):
        d = float(p["diametro"])
        rot = p["nome"].replace("BR ", "", 1).strip()
        A = math.pi * (d / 10.0) ** 2 / 4
        itens.append(_marca_fornecedor({
            "nome": "Barra redonda ø %s" % rot, "familia": "barra_redonda", "grupo": "barra",
            "d": d, "A": _fmt(A, 3), "massa": p.get("massa") or _fmt(A * RHO * 1e-4, 3),
            "polegada": rot if '"' in rot else None, "origem": "tabela",
            "norma": "SAE 1020 / ASTM A36 (tabela do fabricante)",
            "uso": "tirantes, chumbadores, eixos"}, p))
    for p in lam.get("barras_chatas", []):
        rot = p["nome"].replace("BC ", "", 1).strip()
        b, t = float(p["largura"]), float(p["espessura"])
        itens.append(_marca_fornecedor({
            "nome": "Barra chata %s" % rot, "familia": "barra_chata", "grupo": "barra",
            "b": b, "t": t, "A": _fmt(b * t / 100.0, 3), "massa": p.get("massa"),
            "origem": "tabela", "norma": "ASTM A36 (tabela do fabricante)",
            "uso": "travessas, enrijecedores, grades, chapinhas"}, p))
    return itens


def telhas_de_fornecedores():
    """Telhas trapezoidais e onduladas: um item por modelo e espessura, com a massa por m²
    e as larguras total e útil. Modelos sem tabela publicada entram como referência."""
    itens = []
    for p in _ler_fornecedor("telhas.json").get("telhas", []):
        base = {"familia": "telha", "grupo": "telha", "modelo": p["nome"],
                "largura_total": p.get("largura_total"), "largura_util": p.get("largura_util"),
                "altura_onda": p.get("altura_onda"), "comprimento_max": p.get("comprimento_max"),
                "origem": "tabela", "norma": "tabela do fabricante",
                "uso": "cobertura e fechamento"}
        if p.get("observacao"):
            base["obs"] = p["observacao"]
        fab = p.get("fabricante") or ""
        esps = [e for e in (p.get("espessuras") or []) if e.get("t")]
        if not esps:
            reg = dict(base, nome="%s (%s)" % (p["nome"], fab))
            itens.append(_marca_fornecedor(reg, p))
            continue
        for e in esps:
            reg = dict(base, nome="%s %s mm (%s)" % (p["nome"], _num(e["t"], 2), fab),
                       t=e["t"], massa_m2=e.get("peso_m2"))
            itens.append(_marca_fornecedor(reg, p))
    return itens


def _geometria(reg):
    """Chave de geometria para achar o mesmo perfil com outro nome."""
    f = reg["familia"]
    r = lambda x: round(float(x or 0), 1)
    if f in ("U", "Ue", "Ze", "Z45", "Cr"):
        return (f, r(reg.get("d")), r(reg.get("bf")), r(reg.get("enrijecedor")), round(float(reg.get("t") or 0), 2))
    if f == "L":
        return (f, r(reg.get("b")), r(reg.get("b2") or reg.get("b")), round(float(reg.get("t") or 0), 1))
    if f == "barra_redonda":
        return (f, r(reg.get("d")))
    if f == "barra_chata":
        return (f, r(reg.get("b")), r(reg.get("t")))
    return (f, reg["nome"])


def _juntar(base, novos):
    """Acrescenta os itens dos fornecedores às séries sem repetir: se o perfil já existe
    (mesmo nome ou mesma geometria), só ganha o nome do fabricante."""
    from nucleo.catalogo import _chave
    por_nome = {_chave(i["nome"]): i for i in base}
    por_geo = {_geometria(i): i for i in base}
    for n in novos:
        velho = por_nome.get(_chave(n["nome"])) or por_geo.get(_geometria(n))
        if velho is not None:
            for fab in n.get("fabricantes", []):
                if fab and fab not in velho.setdefault("fabricantes", []):
                    velho["fabricantes"].append(fab)
            if n.get("tabela_fabricante"):
                velho.setdefault("tabela_fabricante", {}).update(n["tabela_fabricante"])
            continue
        n["fornecedor"] = True
        n = {k: v for k, v in n.items() if v is not None}
        por_nome[_chave(n["nome"])] = n
        por_geo[_geometria(n)] = n
        base.append(n)
    return base


#: Diferença entre a massa do catálogo e A·ρ acima da qual a massa é tida por errada.
TOLERANCIA_MASSA = 0.05


def conferir_massas(itens):
    """Massa por metro contra a área (A·7850): a que difere mais de 5 % é erro de
    transcrição (L 5"×7/16" com 23,52 no lugar de 21,16 kg/m, TC 42,4×1,35, TQ 30×30×1,8)
    e passa a ser a da área, com a do fornecedor guardada em `massa_fornecedor`."""
    corrigidos = []
    for it in itens:
        A, m = it.get("A"), it.get("massa")
        if not A or not m or it.get("familia") in ("chapa", "telha", "parafuso"):
            continue
        esperada = A * RHO * 1e-4
        teto = esperada
        if it.get("familia") == "tubo" and it.get("tipo") != "redondo" and it.get("b") and it.get("h"):
            # o fornecedor dá a massa com o canto vivo ou com raio menor que 2t: entre as
            # duas áreas a massa está certa
            bb, hh, tt = it["b"], it["h"], it.get("t") or 0.0
            teto = (bb * hh - (bb - 2 * tt) * (hh - 2 * tt)) / 100.0 * RHO * 1e-4
        if m < esperada * (1.0 - TOLERANCIA_MASSA) or m > teto * (1.0 + TOLERANCIA_MASSA):
            it["massa_fornecedor"] = m
            it["massa"] = _fmt(esperada, 3 if esperada < 2 else 2)
            it["obs_massa"] = ("a massa do catálogo (%s kg/m) não bate com a área (%s cm²); "
                               "adotada A·7850" % (m, A))
            corrigidos.append((it["nome"], m, it["massa"]))
    return corrigidos


def bitolas():
    """Tabela de bitolas (#14 etc.) dos fornecedores: a mesma bitola muda de espessura
    conforme a chapa é laminada a quente, a frio ou zincada."""
    return _ler_fornecedor("formados_a_frio.json").get("bitolas", [])


# =====================================================================================
# 4. Montagem
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

    # fornecedores: o que o perfis.json já tem entra só na sombra (para não repetir)
    sombra = _sombra_do_banco()
    n_sombra = len(sombra)
    base = sombra + dados["itens"]
    _juntar(base, frio_de_fornecedores() + laminados_de_fornecedores() + barras_de_fornecedores())
    base.extend(tubos_de_fornecedores())
    base.extend(telhas_de_fornecedores())
    dados["fabricantes_perfis"] = {s["nome"]: s["fabricantes"] for s in base[:n_sombra]
                                   if s.get("fabricantes")}
    dados["itens"] = base[n_sombra:]
    dados["massas_corrigidas"] = [{"nome": n, "catalogo": a, "adotada": b}
                                  for n, a, b in conferir_massas(dados["itens"])]
    dados["bitolas"] = bitolas()
    return dados


def _sombra_do_banco():
    """Os perfis do perfis.json no formato dos itens, só para achar repetidos."""
    try:
        with open(os.path.join(BASE, "perfis.json"), encoding="utf-8") as f:
            banco = json.load(f)
    except (OSError, ValueError):
        return []
    sombra = []
    for tipo, lista in banco.items():
        if not isinstance(lista, list):
            continue
        for p in lista:
            nome = p.get("nome", "")
            fam = tipo
            if tipo in ("U", "Ue"):
                fam = "Ue" if nome.upper().startswith("UE") else "U"
            reg = {"nome": nome, "familia": fam, "d": p.get("d"), "bf": p.get("bf"),
                   "enrijecedor": p.get("D") if fam == "Ue" else None, "t": p.get("t"),
                   "b": p.get("b"), "b2": p.get("b2") or p.get("b")}
            if tipo in ("U", "Ue") and "(FF)" not in nome and not nome.upper().startswith("UE"):
                reg["t"] = p.get("tw") or p.get("t")      # U laminado: a geometria não importa
                reg["d"] = -1.0
            sombra.append(reg)
    return sombra


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
        # um item por linha: o arquivo fica menor e o diff mostra o que mudou
        f.write("{\n")
        for k in [k for k in dados if k != "itens"]:
            f.write(" %s: %s,\n" % (json.dumps(k), json.dumps(dados[k], ensure_ascii=False)))
        f.write(' "itens": [\n')
        f.write(",\n".join("  " + json.dumps(i, ensure_ascii=False) for i in dados["itens"]))
        f.write("\n ]\n}\n")
    print("%s: %d itens" % (os.path.relpath(SAIDA, SISTEMA), len(dados["itens"])))
    for fam, n in sorted(por_familia.items(), key=lambda kv: -kv[1]):
        print("   %-14s %4d" % (fam, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
