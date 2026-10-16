# -*- coding: utf-8 -*-
"""Resumo da obra e resumo de materiais: os dois documentos que a fábrica emite por obra,
saindo do mesmo levantamento da lista de materiais.

* **Resumo da obra** (uma coluna): números principais, dimensões e eixos, tesouras por
  tipo, terças e linhas, pesos por grupo, telhas por tipo e parafusos com o local de uso.
* **Resumo de materiais** (duas colunas, com o quadrinho de conferência): por família de
  produção, kg e metros por perfil (na grafia da fábrica, com a bitola), chaparia por
  espessura, parafusos, telhas por trecho e totais.

Tudo pelo peso teórico (`nucleo2d.detalhe.base.peso_teorico`) e pela nomenclatura de
produção (`PREFIXO_NOME`). O que o IFC não traz vem de `dados` (projeto.json →
`dados_resumo`): revisão, descrição do projeto, descrição comercial da telha, letras dos
eixos das tesouras e as notas das tesouras.
"""
import collections
import hashlib
import html
import math
import os
import re
from typing import Dict, List, Optional, Tuple

from nucleo3d.modelo import Documento, Solido
from nucleo2d.detalhe.base import (_marcas, marcas_de, _autovetores, _eixos_dos_fixadores, _fixadores, _parede_da_peca, _so_parafusos,
                                   _eixo_da_peca)
from saida import identidade
from saida.dobras import com_bitola_e_mm as com_bitola

#: Família de produção de cada tipo de peça/conjunto: (chave, título do resumo de materiais).
FAMILIAS = collections.OrderedDict([
    ("chumbadores", "Chumbadores"), ("pilares", "Pilares PL"), ("vigas_portico", "Vigas de pórtico VG"),
    ("tesouras", "Tesouras"),
    ("tercas_cob", "Terças cob. T.C."), ("tercas_lat", "Terças lat. T.L."), ("tercas_oit", "Terças oit. T.O."),
    ("tercas_marq", "Terças de marquise T.M."), ("vigas", "Vigas e barras B."),
    ("fix_telha", "Fixação de telha F.T."), ("acabamento", "Acabamento A.T."),
    ("agul_cob", "Agulhamentos cob. A.C."), ("agul_lat", "Agulhamentos lat. e oit. A.L."),
    ("agul_diag", "Agulhamentos diagonais A.D."), ("contrav", "Contraventos CV."),
    ("dispositivos", "Dispositivos DP."), ("chapas", "Chapas soltas CH"),
    ("funilaria", "Rufos RF e calhas CL"),
])
#: Famílias fora do peso da estrutura metálica: a funilaria de aluzinc acompanha a telha
#: (no resumo da fábrica, a cumeeira de telha entra nas telhas, não no aço).
FORA_DO_ACO = ("telhas", "funilaria")
_FAMILIA_DO_TIPO = {
    "tesoura": "tesouras", "pilar": "pilares", "viga": "vigas_portico", "terca_cobertura": "tercas_cob", "terca_lateral": "tercas_lat", "terca_oitao": "tercas_oit",
    "terca_marquise": "tercas_marq", "agulhamento": "agul_cob", "agulhamento_lateral": "agul_lat",
    "agulhamento_diagonal": "agul_diag", "gancho": "agul_diag", "contraventamento": "contrav", "barra_roscada": "contrav",
    "conjunto": "dispositivos", "perfil_fechamento": "fix_telha", "cantoneira_forro": "acabamento",
    "chumbador": "chumbadores", "barra": "vigas", "chapa": "chapas", "suporte_terca": "chapas", "castanha": "chapas",
    "suporte_agulhamento": "chapas", "suporte_contraventamento": "chapas",
    "rufo": "funilaria", "calha": "funilaria",
}
#: Grupos do quadro de pesos do resumo da obra, na ordem.
GRUPOS_PESO = [
    ("Pilares", ("pilares",)), ("Vigas de pórtico", ("vigas_portico",)), ("Tesouras", ("tesouras",)), ("Terças e longarinas", ("tercas_cob", "tercas_lat", "tercas_oit", "tercas_marq")),
    ("Vigas e barras", ("vigas",)), ("Perfis de fixação e acabamento de telhas", ("fix_telha", "acabamento")),
    ("Agulhamentos (correntes rígidas)", ("agul_cob", "agul_lat")), ("Agulhamentos diagonais", ("agul_diag",)),
    ("Contraventamentos", ("contrav",)), ("Dispositivos", ("dispositivos",)), ("Chapas soltas", ("chapas",)),
    ("Chumbadores", ("chumbadores",)),
]
_POLEGADA = {12: '1/2"', 16: '5/8"', 10: '3/8"', 20: '3/4"', 8: '5/16"', 24: '1"'}
_COMPRIMENTO_POL = {25: '1"', 30: '1.1/4"', 35: '1.1/2"', 40: '1.3/4"', 45: '1.3/4"', 50: '2"', 55: '2.1/4"', 60: '2.1/2"',
                    65: '2.1/2"', 70: '2.3/4"', 75: '3"', 80: '3"', 90: '3.1/2"', 100: '4"'}
_CHAPA_POL = [(4.75, '3/16"'), (4.8, '3/16"'), (6.3, '1/4"'), (6.35, '1/4"'), (6.4, '1/4"'), (7.94, '5/16"'), (8.0, '5/16"'),
              (9.5, '3/8"'), (9.53, '3/8"'), (12.7, '1/2"'), (13.0, '1/2"'), (15.88, '5/8"'), (16.0, '5/8"'), (19.05, '3/4"'),
              (25.4, '1"')]
LARGURA_UTIL_TELHA = 980.0
#: Chapa comercial da fábrica (05/10: "1,20 x 3,00") e a perda considerada no corte da chaparia (%), quando os dados
#: do resumo não trazem outra.
CHAPA_COMERCIAL = (1200.0, 3000.0)
PERDA_CHAPAS = 15.0
#: Arruela solta no IFC ("BOLT () 0x0" fino): diâmetro externo máximo → bitola, Ø do parafuso (mm).
_ARRUELAS = [(24.0, '3/8"', 9.5), (30.0, '1/2"', 12.7), (36.0, '5/8"', 15.9), (42.0, '3/4"', 19.1), (48.0, '7/8"', 22.2), (60.0, '1"', 25.4)]
#: Porca solta: medida entre cantos (a maior extensão) máxima → bitola, Ø (mm).
_PORCAS_POL = [(19.0, '3/8"', 9.5), (25.0, '1/2"', 12.7), (32.0, '5/8"', 15.9), (39.0, '3/4"', 19.1), (45.0, '7/8"', 22.2), (56.0, '1"', 25.4)]


def _fixador_solto(ext) -> Tuple[str, float, bool]:
    """Porca ou arruela solta do IFC ("BOLT () 0x0", sem tamanho no nome) pelas extensões
    principais: a arruela é o disco fino; a bitola pelo diâmetro externo dela ou pela medida
    entre cantos da porca. Devolve (chave "Porca 5/8\"" / "Arruela 3/8\"", Ø mm, é_arruela)."""
    achatada = min(ext) <= 5.0
    tabela = _ARRUELAS if achatada else _PORCAS_POL
    maior = max(ext)
    pol, d = tabela[-1][1:]
    for lim, rot, dd in tabela:
        if maior <= lim:
            pol, d = rot, dd
            break
    return ("Arruela %s" if achatada else "Porca %s") % pol, d, achatada


#: Tipos de peça que são chapa (a chapa de apoio da tesoura está entre elas).
_TIPOS_CHAPA = {"chapa", "suporte_terca", "castanha", "suporte_agulhamento", "suporte_contraventamento"}


# ============================================================ utilidades
def _n(x, casas=0) -> str:
    if x is None:
        return "—"
    s = ("{:,.%df}" % casas).format(float(x))
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _esc(t) -> str:
    return html.escape(str(t if t is not None else ""))


def _ordem_natural(texto: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", texto or "")]


def _centro(vs) -> Tuple[float, float, float]:
    n = float(len(vs)) or 1.0
    return (sum(v[0] for v in vs) / n, sum(v[1] for v in vs) / n, sum(v[2] for v in vs) / n)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _por_marca(d: Optional[dict]) -> dict:
    """{marca: valor} com as chaves fundidas ("M5 / M6") abertas."""
    fora = {}
    for k, v in (d or {}).items():
        for m in str(k).split(" / "):
            fora[m.strip()] = v
    return fora


#: Espessura comercial da chapa (mm) → polegada; 3,00 é a #11, vendida como 1/8".
_CHAPA_COMERCIAL = [(3.0, '1/8"'), (3.18, '1/8"'), (4.75, '3/16"'), (4.76, '3/16"'), (4.8, '3/16"'), (6.3, '1/4"'),
                    (6.35, '1/4"'), (6.4, '1/4"'), (7.94, '5/16"'), (8.0, '5/16"'), (9.5, '3/8"'), (9.53, '3/8"'),
                    (12.5, '1/2"'), (12.7, '1/2"'), (13.0, '1/2"'), (15.88, '5/8"'), (16.0, '5/8"'), (19.0, '3/4"'),
                    (19.05, '3/4"'), (19.1, '3/4"'), (22.2, '7/8"'), (22.23, '7/8"'), (25.0, '1"'), (25.4, '1"'),
                    (31.75, '1.1/4"'), (38.1, '1.1/2"'), (50.8, '2"')]
def _polegada_da_chapa(t: float) -> Optional[str]:
    return next((p for esp, p in _CHAPA_COMERCIAL if abs(t - esp) < 0.06), None)


def rotulo_chapa(t: float) -> str:
    """A chapa como a fábrica pede (06/10): bitola, mm e polegada — "#11 - 3,00mm - 1/8"", "6,30mm - 1/4"";
    espessura sem bitola nem polegada fica só em mm ("5,60mm")."""
    from saida.dobras import bitola_de
    pol = _polegada_da_chapa(t)
    b = bitola_de(t)
    partes = (["#%d" % b] if b else []) + ["%smm" % _n(t, 2)] + ([pol] if pol else [])
    return " - ".join(partes)


def _espessuras_comerciais() -> List[float]:
    """As espessuras de chapa que se compram: as chapas do catálogo e as bitolas dos fornecedores (#9 3,75, #7 4,50,
    3/16" 4,75), de 1,5 mm para cima."""
    ts = set()
    try:
        from nucleo import catalogo
        ts |= {float(i.dados.get("t") or 0.0) for i in catalogo.itens("chapa")}
        ts |= {float(b.get("t_mm") or 0.0) for b in catalogo.bitolas()}
    except Exception:                                       # noqa: BLE001 — sem catálogo, as da tabela daqui
        ts |= {esp for esp, _ in _CHAPA_COMERCIAL}
    return sorted(t for t in ts if t >= 1.5)


def fracao_polegada(t: float) -> str:
    """A polegada (em 1/32") a até 0,1 mm da espessura, ou "": 5,60 → 7/32", 11,20 → 7/16", 8,90 → "" (06/10)."""
    n = int(round(t / 25.4 * 32))
    if n <= 0 or abs(t - n * 25.4 / 32) > 0.1:
        return ""
    inteiro, resto = divmod(n, 32)
    den = 32
    while resto and resto % 2 == 0:
        resto, den = resto // 2, den // 2
    if not resto:
        return '%d"' % inteiro
    return ('%d.%d/%d"' % (inteiro, resto, den)) if inteiro else '%d/%d"' % (resto, den)


def chapa_comercial(t: float) -> float:
    """A chapa que se compra para a espessura do modelo: a mesma, ou a próxima acima (06/10: 4,30 → #7 4,50;
    10,30 → 1/2"; a peça não sai mais fina que o projeto). Acima da maior, fica a do modelo."""
    for tc in _espessuras_comerciais():
        if tc >= t - 0.06:
            return tc
    return t


def _chapas_por_rotulo(chapas) -> List[dict]:
    """As chapas da lista (uma linha por espessura medida e material) juntas pela chapa comercial e pelo material
    (06/10): 19,0 e 19,1 mm do modelo são a mesma 3/4", e a espessura fora do comercial vai para a próxima acima.
    Cada linha leva a bitola, a espessura e a polegada (o rótulo "#11 - 3,00mm - 1/8""), as espessuras do modelo
    que entraram nela, o peso do modelo (`kg`, o da lista) e o da chapa comprada (`kg_compra`)."""
    from saida.dobras import bitola_de
    juntas: Dict[tuple, dict] = collections.OrderedDict()
    for g in chapas or []:
        t = float(g.get("espessura") or 0.0)
        tc = chapa_comercial(t)
        mat = str(g.get("material") or "")
        j = juntas.setdefault((tc, mat), {"material": mat, "t": tc, "kg": 0.0, "pecas": 0, "m2": 0.0, "modelo": set()})
        j["kg"] += float(g.get("peso") or 0.0)
        j["pecas"] += int(g.get("pecas") or 0)
        j["m2"] += float(g.get("area_m2") or 0.0)
        j["modelo"].add(round(t, 2))
    for j in juntas.values():
        b = bitola_de(j["t"])
        j["bitola"] = "#%d" % b if b else ""
        j["mm"] = "%smm" % _n(j["t"], 2)
        j["polegada"] = _polegada_da_chapa(j["t"]) or ""
        j["rotulo"] = " - ".join(x for x in (j["bitola"], j["mm"], j["polegada"]) if x)
        outras = sorted(x for x in j.pop("modelo") if abs(x - j["t"]) >= 0.06)
        # a espessura do modelo com a polegada dela quando bate (5,60mm ≈ 7/32", que não está no catálogo)
        j["modelo"] = ", ".join("%smm%s" % (_n(x, 2), (" (≈%s)" % fracao_polegada(x)) if fracao_polegada(x) else "")
                                for x in outras)
        j["kg_compra"] = j["m2"] * j["t"] * 7.85
    return sorted(juntas.values(), key=lambda j: (j["t"], j["material"]))


def descricao_parafuso(nome: str, classe: Optional[str] = None) -> Tuple[str, str, Optional[float]]:
    """"M12 x 35" → ("Parafuso M12x35", 'Parafuso sextavado Ø1/2" x 1.1/2" ASTM A307 + porca e arruela', 12)."""
    m = re.match(r"M(\d+(?:[.,]\d+)?)\s*x\s*(\d+)", nome or "", re.I)
    if not m:
        return nome, nome, None
    d = float(m.group(1).replace(",", "."))
    L = int(m.group(2))
    pol = _pol_mais_perto(d) or "M%g" % d
    lpol = _COMPRIMENTO_POL.get(L) or _COMPRIMENTO_POL.get(min(_COMPRIMENTO_POL, key=lambda k: abs(k - L)))
    classe = classe or ("A325" if (d >= 16 and L >= 50) else "A307")     # a do modelo ("BOLT (A325) …") quando há
    return ("Parafuso M%gx%d" % (d, L), "Parafuso sextavado Ø%s x %s ASTM %s + porca e arruela" % (pol, lpol, classe), d)


def _pol_mais_perto(d) -> str:
    """A bitola em polegada mais perto do diâmetro (mm), a até 1,5 mm: 12,7 → 1/2", 19,05 → 3/4" (o round dava 13 e
    19, fora da tabela — o parafuso Ø1/2" saía "M12.7")."""
    d = float(d or 0)
    k = min(_POLEGADA, key=lambda x: abs(x - d))
    return _POLEGADA[k] if abs(k - d) <= 1.5 else ""


#: O químico do chumbador (09/10): o anel entre o furo no concreto e a barra, no embutimento, com a perda (o que fica no
#: misturador, o descarte do começo de cada cartucho e o excesso que transborda); furo da Hilti para a barra em polegada.
EMBUTIMENTO_QUIMICO = 150.0
FURO_CONCRETO = {12.7: 14.29, 15.875: 19.05, 19.05: 22.23, 22.225: 25.4, 25.4: 28.58}     # 1/2"→9/16", 5/8"→3/4", 3/4"→7/8"…
PERDA_QUIMICO = 0.30
CARTUCHO_ML = 500
DESCARTE_ML = 15.0


def volume_quimico_ml(d: float, embutimento: float = EMBUTIMENTO_QUIMICO) -> float:
    """ml de químico num furo: π/4 (d0² − d²) × embutimento, sem a perda."""
    d = float(d or 0)
    k = min(FURO_CONCRETO, key=lambda x: abs(x - d))
    d0 = FURO_CONCRETO[k] if abs(k - d) <= 1.0 else d + 2.0
    return math.pi / 4.0 * (d0 * d0 - d * d) * float(embutimento) / 1000.0


def cartuchos_quimico(ml: float) -> dict:
    total = ml * (1.0 + PERDA_QUIMICO)
    n = int(math.ceil(total / (CARTUCHO_ML - DESCARTE_ML) - 1e-9)) if total > 0 else 0
    return {"ml_total": round(total, 0), "cartuchos": n, "cartucho_ml": CARTUCHO_ML}


def _eh_chumbador(nome: str) -> bool:
    return bool(re.match(r"\s*(CHUMBADOR|PARABOLT|HARDBOLT)", str(nome or ""), re.I))


def descricao_chumbador(d: float, L) -> Tuple[str, str]:
    """O chumbador químico pelo diâmetro e comprimento (mm): ("Chumbador químico HIT-V Ø5/8\" x 250",
    "Barra roscada HIT-V ASTM A36 Ø5/8\" x 250 mm + porca e arruela, com químico HIT-RE 500")."""
    pol = _pol_mais_perto(d) or "Ø%g mm" % float(d)
    return ("Chumbador químico HIT-V Ø%s x %s" % (pol, L),
            "Barra roscada HIT-V ASTM A36 Ø%s x %s mm + porca e arruela, com químico de injeção HIT-RE 500" % (pol, L))


# ============================================================ levantamento
def levantar_resumos(doc: Documento, lev: dict, lista: dict, nomes: dict, dados: Optional[dict] = None) -> dict:
    """Todos os números dos dois documentos, a partir do levantamento (`lev`), da lista de
    materiais montada (`lista`) e dos nomes de produção (`nomes`)."""
    dados = dict(dados or {})
    posicoes = list(lev["posicoes"])
    pecas: List[Solido] = list(lev["pecas"])
    tipos = _por_marca(nomes.get("tipos"))
    nomes_pos = _por_marca(nomes.get("posicoes"))
    tipos_conj = _por_marca(nomes.get("tipos_conjuntos"))
    nomes_conj = _por_marca(nomes.get("conjuntos"))
    conj_info = {c["marca"]: c for c in (lista.get("conjuntos") or [])}
    por_conj_nome: Dict[str, dict] = {}
    for c in lista.get("conjuntos") or []:
        # a tesoura pelo tipo do conjunto também (no depósito, os conjuntos de tesoura vêm na categoria CONJUNTOS: o
        # resumo saía com 0 tesouras e as dimensões vazias, 05/10)
        cat = "TESOURAS" if tipos_conj.get(c["marca"]) == "tesoura" else c.get("categoria")
        if cat != c.get("categoria"):
            conj_info[c["marca"]] = dict(c, categoria=cat)
        r = por_conj_nome.setdefault(c.get("nome") or c["marca"], {"nome": c.get("nome") or c["marca"], "marcas": [], "instancias": 0,
                                                                   "peso_unitario": c.get("peso_unitario") or 0.0, "peso_total": 0.0,
                                                                   "categoria": cat, "composicao": {}})
        r["marcas"].append(c["marca"])
        r["instancias"] += int(c.get("instancias") or 0)
        r["peso_total"] += float(c.get("peso_total") or 0.0)
        for m, q in (c.get("composicao") or {}).items():
            r["composicao"][m] = max(r["composicao"].get(m, 0), q)
    marca_para_pos = {}
    for p in posicoes:
        for m in marcas_de(p):
            marca_para_pos[m] = p
    pecas_por_marca: Dict[str, List[Solido]] = collections.defaultdict(list)
    for e in pecas:
        pecas_por_marca[str(_marcas(e).get("posicao") or e.nome or e.id)].append(e)

    def familia_do_conjunto(marca_conj: str) -> Optional[str]:
        if conj_info.get(marca_conj, {}).get("categoria") == "TESOURAS":
            return "tesouras"
        return _FAMILIA_DO_TIPO.get(tipos_conj.get(marca_conj, ""))

    def familia_da_posicao(p) -> str:
        t = tipos.get(p.marca) or ""
        conjs = [c for c in p.conjuntos if c not in set(marcas_de(p))]
        fams = {familia_do_conjunto(c) for c in conjs} - {None}
        if p.classe == "telha":
            return "telhas"
        if t in ("rufo", "calha"):
            return "funilaria"
        if fams and len(fams) == 1:
            return next(iter(fams))
        if fams:
            return sorted(fams, key=lambda f: list(FAMILIAS).index(f) if f in FAMILIAS else 99)[0]
        return _FAMILIA_DO_TIPO.get(t, "vigas")

    # ---- tesouras: instâncias, eixos e geometria
    from nucleo2d.detalhe.conjuntos import _instancias_do_conjunto, _eixos_do_conjunto
    tes_inst: List[dict] = []
    for nome_t, r in por_conj_nome.items():
        if r["categoria"] != "TESOURAS":
            continue
        lista_p = [e for e in pecas if str(_marcas(e).get("conjunto") or "") in r["marcas"] and e.vertices]
        # a variante de furação ("P3 (b)") é a mesma peça no lugar: as instâncias se reconhecem pela posição de base
        unidade = collections.Counter()
        for m, q in r["composicao"].items():
            unidade[re.sub(r" \([b-z]\)$", "", m)] += q
        if not lista_p or not unidade:
            continue
        try:
            grupos = _instancias_do_conjunto(lista_p, unidade)
        except Exception:                                   # noqa: BLE001
            grupos = [lista_p]
        for g in grupos:
            if len(g) < 4:
                continue
            tes_inst.append({"tipo": nome_t, "pecas": g})
    eixo_g = None
    todos_v = [v for e in pecas if e.vertices for v in e.vertices]
    if len(tes_inst) >= 2:
        cs = [_centro([v for e in t["pecas"] for v in e.vertices]) for t in tes_inst]
        _c, pca = _autovetores(cs) if len(cs) >= 3 else (None, None)
        if pca is None:
            d = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1], 0.0)
            L = math.hypot(d[0], d[1]) or 1.0
            eixo_g = (d[0] / L, d[1] / L, 0.0)
        else:
            eixo_g = pca[0]
    elif tes_inst:
        _c, u, v, w = _eixos_do_conjunto(tes_inst[0]["pecas"])
        eixo_g = w
    if eixo_g is None:
        eixo_g = (1.0, 0.0, 0.0)
    if eixo_g[0] < 0 or (abs(eixo_g[0]) < 1e-9 and eixo_g[1] < 0):
        eixo_g = (-eixo_g[0], -eixo_g[1], -eixo_g[2])
    perp_g = (-eixo_g[1], eixo_g[0], 0.0)
    gs = [_dot(v, eixo_g) for v in todos_v]
    limites_g = (min(gs), max(gs)) if gs else None
    def _dist_h(a, b) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _tipo_da_peca(e) -> str:
        return tipos.get(str(_marcas(e).get("posicao") or e.nome or e.id), "")

    # geometria de cada instância (meia-tesoura ou tesoura inteira)
    for t in tes_inst:
        g = t["pecas"]
        vs = [v for e in g for v in e.vertices]
        c, u, v, w = _eixos_do_conjunto(g)
        us = [_dot(p, u) for p in vs]
        zs = [p[2] for p in vs]
        u0, u1, z0, z1 = min(us), max(us), min(zs), max(zs)
        L = u1 - u0
        i_topo = max(range(len(vs)), key=lambda i: zs[i])
        f = (us[i_topo] - u0) / L if L > 0 else 0.5
        # meia-tesoura: a cumeeira numa ponta (e u orientado do beiral para a cumeeira)
        meia = f < 0.2 or f > 0.8
        if meia and f < 0.5:
            u = (-u[0], -u[1], -u[2])
            us = [-x for x in us]
            u0, u1 = -u1, -u0
        # apoio: a chapa de apoio (a chapa horizontal mais baixa, no terço de baixo) de cada
        # lado; sem chapa, os pontos mais baixos daquele lado
        chapas = []
        for e in g:
            if _tipo_da_peca(e) not in _TIPOS_CHAPA:
                continue
            ez = [q[2] for q in e.vertices]
            eu = [_dot(q, u) for q in e.vertices]
            if max(ez) - min(ez) <= 25.0 and max(eu) - min(eu) >= 80.0 and max(ez) <= z0 + 0.4 * (z1 - z0):
                cc = _centro(e.vertices)
                # a chapa de apoio é chapa (não suporte de terça) e é a maior: no beiral há
                # chapinhas horizontais de suporte mais baixas do que ela
                chapas.append({"z": max(ez), "u": (min(eu) + max(eu)) / 2.0, "xyz": (cc[0], cc[1], max(ez)), "chapa": True,
                               "ordem": (_tipo_da_peca(e) in ("chapa", "castanha"), max(eu) - min(eu))})
        lados = [(u0, u1)] if meia else [(u0, u0 + L / 2.0), (u0 + L / 2.0, u1)]
        apoios = []
        for a0, a1 in lados:
            cs = [ch for ch in chapas if a0 <= ch["u"] <= a1]
            if cs:
                apoios.append(max(cs, key=lambda x: x["ordem"]))
                continue
            pts = [p for p, uu in zip(vs, us) if a0 <= uu <= a1 and p[2] <= z0 + 60.0]
            if pts:
                cc = _centro(pts)
                apoios.append({"z": z0, "u": _dot(cc, u), "xyz": (cc[0], cc[1], z0), "chapa": False})
        if not apoios:
            apoios.append({"z": z0, "u": u0, "xyz": (vs[us.index(u0)][0], vs[us.index(u0)][1], z0), "chapa": False})
        # inclinação da água: a barra inclinada mais comprida (o banzo superior)
        barras = []
        for e in g:
            if _tipo_da_peca(e) in _TIPOS_CHAPA or _tipo_da_peca(e) == "telha":
                continue
            ex = _eixo_da_peca(e)
            if not ex:
                continue
            a, b = ex
            dh = math.hypot(b[0] - a[0], b[1] - a[1])
            dz = abs(b[2] - a[2])
            if dh > 0 and 0.03 <= dz / dh <= 1.0:
                barras.append((math.hypot(dh, dz), dz / dh))
        t.update({"meia": meia, "u": u, "w": w, "L": L, "z_topo": z1, "topo": vs[i_topo], "pontas": (vs[us.index(u0)], vs[us.index(u1)]),
                  "apoios": apoios, "inclinacao": math.degrees(math.atan(max(barras)[1])) if barras else 0.0})
    # o eixo do galpão é a normal das tesouras (a PCA dos centros entorta quando a ala
    # está deslocada do corpo principal, e as linhas de terça deixam de coincidir)
    if tes_inst:
        ref = tes_inst[0]["w"]
        soma = [0.0, 0.0, 0.0]
        for t in tes_inst:
            sinal = 1.0 if _dot(t["w"], ref) >= 0 else -1.0
            soma = [soma[i] + sinal * t["w"][i] for i in range(3)]
        norma = math.hypot(soma[0], soma[1])
        if norma > 1e-6:
            eixo_g = (soma[0] / norma, soma[1] / norma, 0.0)
            if eixo_g[0] < 0 or (abs(eixo_g[0]) < 1e-9 and eixo_g[1] < 0):
                eixo_g = (-eixo_g[0], -eixo_g[1], 0.0)
            perp_g = (-eixo_g[1], eixo_g[0], 0.0)
            gs = [_dot(v, eixo_g) for v in todos_v]
            limites_g = (min(gs), max(gs)) if gs else None
    # meias-tesouras emendadas na cumeeira viram uma tesoura: as duas com a cumeeira no
    # mesmo ponto, apontando uma para a outra
    unidades: List[dict] = []
    usados = set()
    for i, a in enumerate(tes_inst):
        if i in usados:
            continue
        usados.add(i)
        par = None
        if a["meia"]:
            melhor = None
            for j, b in enumerate(tes_inst):
                if j in usados or not b["meia"]:
                    continue
                d = math.dist(a["topo"], b["topo"])
                if d <= 800.0 and _dot(a["u"], b["u"]) < -0.5 and (melhor is None or d < melhor[0]):
                    melhor = (d, j)
            if melhor:
                par = tes_inst[melhor[1]]
                usados.add(melhor[1])
        membros = [a] + ([par] if par else [])
        apoios = [ap for m in membros for ap in m["apoios"]]
        if par:
            comprimento = _dist_h(a["pontas"][0], par["pontas"][0])
            vao = _dist_h(apoios[0]["xyz"], apoios[-1]["xyz"]) if len(apoios) >= 2 else comprimento
            corrida = vao / 2.0
        elif a["meia"]:
            comprimento = a["L"]
            vao = _dist_h(apoios[0]["xyz"], a["topo"])       # meia-tesoura solta: do apoio à cumeeira
            corrida = vao
        else:
            comprimento = a["L"]
            vao = _dist_h(apoios[0]["xyz"], apoios[-1]["xyz"]) if len(apoios) >= 2 else comprimento
            corrida = vao / 2.0
        z_apoio = sum(ap["z"] for ap in apoios) / len(apoios)
        incl = sum(m["inclinacao"] for m in membros) / len(membros)
        nomes_m = [m["tipo"] for m in membros]
        centro = _centro([v for m in membros for e in m["pecas"] for v in e.vertices])
        unidades.append({"tipo": nomes_m[0] if len(set(nomes_m)) == 1 else " + ".join(sorted(nomes_m, key=_ordem_natural)),
                         "membros": collections.Counter(nomes_m), "meias": len(membros) if a["meia"] else 0,
                         "pos_g": _dot(centro, eixo_g), "comprimento": comprimento, "vao": vao,
                         "altura": max(m["z_topo"] for m in membros) - z_apoio, "flecha": corrida * math.tan(math.radians(incl)),
                         "inclinacao": incl, "z_apoio": z_apoio, "apoio_por_chapa": all(ap["chapa"] for ap in apoios),
                         "pecas": [e for m in membros for e in m["pecas"]]})
    # cada tesoura montada com o nome dela, em sequência na ordem das metades — T1, T2, T3… —, o mesmo das
    # pranchas ("T1 + T2" confundia os montadores, pedido do usuário, 28/09); as metades ficam em "metades"
    seq = {n: "T%d" % i for i, n in enumerate(sorted({t["tipo"] for t in unidades}, key=_ordem_natural), start=1)}
    for t in unidades:
        t["metades"] = t["tipo"]
        t["tipo"] = seq[t["tipo"]]
    tes_inst = unidades

    def _trechos_de(unidades_ordenadas) -> List[dict]:
        """Tesouras seguidas com o mesmo vão formam um trecho."""
        saida: List[dict] = []
        for t in unidades_ordenadas:
            if saida and abs(saida[-1]["vao"] - t["vao"]) <= 150.0:
                saida[-1]["fim"] = t
                saida[-1]["tesouras"].append(t)
            else:
                saida.append({"inicio": t, "fim": t, "vao": t["vao"], "tesouras": [t]})
        return saida

    tes_inst.sort(key=lambda t: t["pos_g"])
    trechos = _trechos_de(tes_inst)
    principal = max(range(len(trechos)), key=lambda k: (len(trechos[k]["tesouras"]), -k)) if trechos else 0
    if len(trechos) > 1 and principal > len(trechos) - 1 - principal:
        # o corpo principal (o trecho com mais tesouras) vem primeiro: eixos A, B, C… a partir dele
        eixo_g = (-eixo_g[0], -eixo_g[1], -eixo_g[2])
        perp_g = (-eixo_g[1], eixo_g[0], 0.0)
        limites_g = (-limites_g[1], -limites_g[0]) if limites_g else None
        for t in tes_inst:
            t["pos_g"] = -t["pos_g"]
        tes_inst.sort(key=lambda t: t["pos_g"])
        trechos = _trechos_de(tes_inst)
        principal = len(trechos) - 1 - principal
    letras = [x.strip() for x in str(dados.get("eixos") or "").replace(";", ",").split(",") if x.strip()]
    if len(letras) != len(tes_inst):
        letras = [chr(ord("A") + i) if i < 26 else "A%d" % (i - 25) for i in range(len(tes_inst))]
    for t, letra in zip(tes_inst, letras):
        t["eixo"] = letra
    n_ala = 0
    for k, tr in enumerate(trechos):
        if len(trechos) == 1:
            tr["nome"] = "Galpão"
        elif k == principal:
            tr["nome"] = "Corpo principal"
        else:
            n_ala += 1
            tr["nome"] = "Ala %d" % n_ala if len(trechos) > 2 else "Ala"
        tr["comprimento"] = tr["fim"]["pos_g"] - tr["inicio"]["pos_g"]
        if k > 0:
            # o degrau entre as coberturas: da última tesoura do trecho anterior à primeira deste
            tr["transicao"] = tr["inicio"]["pos_g"] - trechos[k - 1]["fim"]["pos_g"]
            tr["eixos_transicao"] = "%s a %s" % (trechos[k - 1]["fim"]["eixo"], tr["inicio"]["eixo"])
        tr["eixos"] = "%s a %s" % (tr["inicio"]["eixo"], tr["fim"]["eixo"]) if tr["inicio"] is not tr["fim"] else tr["inicio"]["eixo"]
    # projeção em planta (aço + telhas), por trecho pelas peças no intervalo de cada um
    def caixa_em_planta(vs):
        if not vs:
            return (0.0, 0.0)
        a = [_dot(p, eixo_g) for p in vs]
        b = [_dot(p, perp_g) for p in vs]
        return (max(a) - min(a), max(b) - min(b))
    lim = []
    for k, tr in enumerate(trechos):
        a0 = tr["inicio"]["pos_g"] - (tr["inicio"]["pos_g"] - trechos[k - 1]["fim"]["pos_g"]) / 2.0 if k > 0 else -1e12
        a1 = tr["fim"]["pos_g"] + (trechos[k + 1]["inicio"]["pos_g"] - tr["fim"]["pos_g"]) / 2.0 if k + 1 < len(trechos) else 1e12
        lim.append((a0, a1))
    for tr, (a0, a1) in zip(trechos, lim):
        vs = [v for e in pecas if e.vertices for v in e.vertices if a0 <= _dot(v, eixo_g) <= a1]
        tr["projecao"] = caixa_em_planta(vs)
    projecao_total = caixa_em_planta(todos_v)
    area_m2 = sum(tr["projecao"][0] * tr["projecao"][1] for tr in trechos) / 1e6 if trechos else projecao_total[0] * projecao_total[1] / 1e6
    nivel_apoio = min((t["z_apoio"] for t in tes_inst), default=None)
    apoio_por_chapa = bool(tes_inst) and all(t["apoio_por_chapa"] for t in tes_inst)

    # ---- tesouras por tipo (a tabela do resumo da obra): o tipo é a unidade montada
    # (as duas meias, quando é o caso)
    tipos_tes: List[dict] = []
    for nome_t in sorted({t["tipo"] for t in tes_inst}, key=_ordem_natural):
        inst = [t for t in tes_inst if t["tipo"] == nome_t]
        membros = inst[0]["membros"]
        comp: Dict[str, int] = collections.Counter()
        for n_m, k in membros.items():
            for m, q in por_conj_nome[n_m]["composicao"].items():
                comp[m] += q * k
        # banzo: o perfil da barra mais comprida; treliçamento: o de mais comprimento total entre os outros
        comp_perfil: Dict[str, float] = collections.Counter()
        mais_comprida = None
        for m, q in comp.items():
            p = marca_para_pos.get(m)
            if p is None or p.classe in ("chapa", "chapa_dobrada", "telha"):
                continue
            nome_p = com_bitola(p.perfil)
            comp_perfil[nome_p] += float(p.comprimento or 0.0) * q
            if mais_comprida is None or float(p.comprimento or 0.0) > mais_comprida[0]:
                mais_comprida = (float(p.comprimento or 0.0), nome_p)
        banzos = mais_comprida[1] if mais_comprida else ""
        outros = [k for k, _ in comp_perfil.most_common() if k != banzos]
        kg_un = sum(por_conj_nome[n_m]["peso_unitario"] * k for n_m, k in membros.items())
        tipos_tes.append({
            "tipo": nome_t, "qtd": len(inst), "eixos": ", ".join(t["eixo"] for t in inst), "membros": dict(membros),
            "meias": inst[0]["meias"], "composicao": dict(comp),
            "vao": max(t["vao"] for t in inst), "comprimento": max(t["comprimento"] for t in inst),
            "flecha": max(t["flecha"] for t in inst), "altura": max(t["altura"] for t in inst),
            "banzos": banzos, "trelicamento": outros[0] if outros else "",
            "kg_un": kg_un, "kg_total": kg_un * len(inst),
            "marcas": [m for n_m in membros for m in por_conj_nome[n_m]["marcas"]],
        })
    inclinacao = None
    if tes_inst:
        inclinacao = sum(t["inclinacao"] for t in tes_inst) / len(tes_inst)

    # ---- famílias: posições e perfis
    fam_pos: Dict[str, List] = collections.defaultdict(list)
    for p in posicoes:
        fam_pos[familia_da_posicao(p)].append(p)
    peso_fam = {f: sum(p.peso_total for p in ps) for f, ps in fam_pos.items()}

    def nome_da_peca(marca: str) -> str:
        return nomes_pos.get(marca) or " / ".join(dict.fromkeys(nomes_pos.get(m.strip()) or m.strip() for m in str(marca).split(" / ")))

    def perfis_de(ps, so_barras=True) -> List[dict]:
        """Os perfis do grupo com o peso e o comprimento, e embaixo de cada um as peças que somaram (06/10: "o total
        desse perfil e logo abaixo todas as peças que compuseram aquele valor, com o nome e o comprimento")."""
        g: Dict[str, dict] = collections.OrderedDict()
        for p in ps:
            if so_barras and p.classe in ("chapa", "chapa_dobrada", "telha", "indefinida"):
                continue
            nome = com_bitola(p.perfil) if p.perfil else "?"
            r = g.setdefault(nome, {"perfil": nome, "kg": 0.0, "m": 0.0, "pecas": 0, "_lista": collections.Counter()})
            r["kg"] += p.peso_total
            r["m"] += float(p.comprimento or 0.0) * p.quantidade / 1000.0
            r["pecas"] += p.quantidade
            r["_lista"][(nome_da_peca(getattr(p, "marca", "")), int(round(float(p.comprimento or 0.0))))] += p.quantidade
        for r in g.values():
            r["lista"] = [{"nome": n, "comprimento": c, "qtd": q}
                          for (n, c), q in sorted(r.pop("_lista").items(), key=lambda kv: (_ordem_natural(kv[0][0]), kv[0][1]))]
        return sorted(g.values(), key=lambda r: -r["kg"])

    def composicao_de(ps, conjuntos_da_familia) -> str:
        if conjuntos_da_familia:
            return " · ".join("%s %dx" % (c["nome"], c["instancias"]) for c in conjuntos_da_familia)
        itens = sorted(((nomes_pos.get(p.marca) or p.marca, p.quantidade) for p in ps), key=lambda kv: _ordem_natural(kv[0]))
        return " · ".join("%s %dx" % kv for kv in itens)

    # sem cobertura, a treliça é viga caixote (o detalhar diz pelos nomes; o resumo montado sem ele, pelas posições)
    from nucleo2d.detalhe.base import TITULO_SEM_COBERTURA, obra_tem_cobertura
    cobertura = nomes.get("cobertura") if nomes.get("cobertura") is not None else obra_tem_cobertura(posicoes, tipos)
    titulo_trelica = "Tesouras" if cobertura else TITULO_SEM_COBERTURA
    familias: List[dict] = []
    for chave, titulo in FAMILIAS.items():
        if chave == "tesouras":
            titulo = titulo_trelica
        ps = fam_pos.get(chave) or []
        conjs = [r for r in por_conj_nome.values() if (r["categoria"] == "TESOURAS" and chave == "tesouras")
                 or (r["categoria"] != "TESOURAS" and familia_do_conjunto(r["marcas"][0]) == chave)]
        conjs.sort(key=lambda r: _ordem_natural(r["nome"]))
        if not ps and not conjs:
            continue
        n_pecas = len(tes_inst) if chave == "tesouras" else (sum(c["instancias"] for c in conjs) if conjs else sum(p.quantidade for p in ps))
        # as tesouras pelo nome delas (T1 03x · T2 02x…), como na tabela do resumo da obra e nas pranchas — a linha das
        # meias (T1 8x · T2 2x…) usava os mesmos nomes para outra coisa (05/10)
        # sem conjuntos, as peças já saem embaixo de cada perfil (nome, quantidade e comprimento): a linha corrida
        # com os nomes repetia a mesma coisa sem o comprimento (06/10)
        comp_ = (" · ".join("%s %02dx" % (tt["tipo"], tt["qtd"]) for tt in tipos_tes) if chave == "tesouras" and tipos_tes
                 else composicao_de(ps, conjs) if conjs else "")
        bloco = {"chave": chave, "titulo": titulo, "n": n_pecas, "composicao": comp_,
                 "perfis": perfis_de(ps), "kg": peso_fam.get(chave, 0.0), "sub": []}
        if chave == "tesouras":
            for tt in tipos_tes:
                ps_t = [(marca_para_pos[m], q * tt["qtd"]) for m, q in tt["composicao"].items() if m in marca_para_pos]

                class _Q:
                    def __init__(self, p, q):
                        self.perfil, self.classe, self.comprimento, self.marca = p.perfil, p.classe, p.comprimento, p.marca
                        self.quantidade, self.peso_total = q, p.peso * q
                bloco["sub"].append({"titulo": "%s (%02dx) - eixos %s" % (tt["tipo"], tt["qtd"], tt["eixos"]),
                                     "perfis": perfis_de([_Q(p, q) for p, q in ps_t])})
            bloco["perfis"] = []
        if chave == "chapas":
            bloco["nota"] = "somente chapas - ver chaparia"
            bloco["perfis"] = []
        familias.append(bloco)

    # ---- chaparia
    chaparia = _chapas_por_rotulo(lista.get("chapas"))
    chaparia_total = {"kg": sum(c["kg"] for c in chaparia), "pecas": sum(c["pecas"] for c in chaparia)}

    # ---- parafusos e fixadores, com o local de uso
    fixadores = _so_parafusos(_fixadores(doc))
    from nucleo2d.detalhar import projeto_recebido
    parafusos = _parafusos_com_local(fixadores, pecas, tipos, nomes_pos, tipos_conj, nomes_conj, conj_info,
                                     recebido=projeto_recebido(doc))
    n_parafusos = sum(p["qtd"] for p in parafusos if p["parafuso"])

    # ---- telhas: por trecho (cobertura, fechamento, forro) e código
    telhas = _telhas(lev, lista, pecas_por_marca, nivel_apoio, dados)

    # ---- terças: linhas e famílias
    tercas = _tercas(posicoes, tipos, pecas_por_marca, trechos, lim, eixo_g, perp_g, nomes_pos, limites_g)

    # ---- pesos por grupo
    grupos_peso = []
    for titulo, chaves in GRUPOS_PESO:
        kg = sum(peso_fam.get(c, 0.0) for c in chaves)
        if kg > 0:
            grupos_peso.append({"grupo": titulo_trelica if chaves == ("tesouras",) else titulo, "kg": kg})
    peso_aco = sum(kg for f, kg in peso_fam.items() if f not in FORA_DO_ACO)
    peso_telhas = telhas["kg_total"]
    ml_telhas = telhas["ml_total"]
    peso_funilaria = peso_fam.get("funilaria", 0.0)
    for g in grupos_peso:
        g["pct"] = 100.0 * g["kg"] / peso_aco if peso_aco else 0.0
    perfis_kg = sum(f["kg"] for f in familias if f["chave"] not in FORA_DO_ACO) - peso_fam.get("chapas", 0.0)

    identificacao = dict(lista.get("projeto") or {})
    pendencias = _pendencias(lista, parafusos, lev, nomes_pos)
    pintura = _area_de_pintura(lista)
    compra = _compra(lista, parafusos, telhas, dados)
    maior, pesada = _maior_e_mais_pesada(lista, tipos_tes, "tesoura" if cobertura else "viga caixote")
    # onde fica cada tesoura, para o tipo dela na implantação do dossiê: a ponta de cima em planta (09/10)
    tesouras_lugar = []
    for t in tes_inst:
        vs = [v for e in t["pecas"] for v in (e.vertices or [])]
        if vs:
            topo = max(vs, key=lambda v: _dot(v, perp_g))
            cc = _centro(vs)
            tesouras_lugar.append({"tipo": t["tipo"], "eixo": t.get("eixo", ""), "xy": (cc[0] + (topo[0] - cc[0]) * 0.82,
                                                                                      cc[1] + (topo[1] - cc[1]) * 0.82, 0.0)})
    import time as _time
    return {
        "gerado": _time.strftime("%d/%m/%Y %H:%M"), "pendencias": pendencias, "pintura": pintura, "compra": compra,
        "maior": maior, "mais_pesada": pesada, "tesouras_lugar": tesouras_lugar,
        "projeto": identificacao, "dados": dados,
        "cobertura": cobertura,
        # sem cobertura não há tesoura (a proposta e o orçamento contavam as 129 caixas do Vicente como tesouras)
        "numeros": {"tesouras": sum(t["qtd"] for t in tipos_tes) if cobertura else 0,
                    "trelicas_sem_cobertura": 0 if cobertura else sum(t["qtd"] for t in tipos_tes),
                    "peso_aco": peso_aco, "ml_telhas": ml_telhas,
                    "peso_telhas": peso_telhas, "peso_funilaria": peso_funilaria,
                    "total": peso_aco + peso_telhas + peso_funilaria, "parafusos": n_parafusos,
                    "inclinacao": inclinacao, "kg_m2": (peso_aco / area_m2) if area_m2 else None,
                    "m2_telhas": telhas["m2_total"], "m2_pintura": pintura["total_m2"]},
        "dimensoes": {"eixos": " ".join(t["eixo"] for t in tes_inst), "comprimento_total": (tes_inst[-1]["pos_g"] - tes_inst[0]["pos_g"]) if tes_inst else 0.0,
                      "trechos": [{k: v for k, v in tr.items() if k not in ("inicio", "fim", "tesouras")} for tr in trechos],
                      "projecao": projecao_total, "area_m2": area_m2, "nivel_apoio": nivel_apoio, "apoio_por_chapa": apoio_por_chapa,
                      "n_tesouras": len(tes_inst)},
        "tesouras": tipos_tes, "tercas": tercas, "grupos_peso": grupos_peso, "telhas": telhas, "parafusos": parafusos,
        "familias": familias, "chaparia": chaparia, "chaparia_total": chaparia_total,
        "perfis_kg": peso_aco - chaparia_total["kg"] if chaparia_total["kg"] else perfis_kg,
        "avisos": list(lev.get("avisos") or []),
    }


def _parafusos_com_local(fixadores, pecas, tipos, nomes_pos, tipos_conj, nomes_conj, conj_info, recebido: bool = False) -> List[dict]:
    """Cada tamanho de parafuso (e porca/arruela) com a quantidade e os locais de uso — o
    par de famílias das peças que ele atravessa (a peça é a que tem o furo em volta do eixo
    do fixador) e as peças envolvidas."""
    if not fixadores:
        return []
    import numpy as np
    eixos = _eixos_dos_fixadores(fixadores)
    # grade das peças por caixa, para achar as candidatas de cada fixador (a telha fica de
    # fora: o parafuso dela não vem no IFC, e a malha dela é enorme)
    caixas = []
    arrays = {}
    for e in pecas:
        if not e.vertices or tipos.get(str(_marcas(e).get("posicao") or e.nome or "")) == "telha":
            continue
        xs, ys, zs = zip(*e.vertices)
        caixas.append((e, (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))))
        arrays[e.id] = np.asarray(e.vertices, dtype=float)
    cel = 500.0
    grade: Dict[tuple, list] = collections.defaultdict(list)
    for e, cx in caixas:
        for i in range(int(math.floor(cx[0] / cel)), int(math.floor(cx[3] / cel)) + 1):
            for j in range(int(math.floor(cx[1] / cel)), int(math.floor(cx[4] / cel)) + 1):
                for k in range(int(math.floor(cx[2] / cel)), int(math.floor(cx[5] / cel)) + 1):
                    grade[(i, j, k)].append((e, cx))

    def familia_peca(e) -> Tuple[str, str]:
        m = _marcas(e)
        pos = str(m.get("posicao") or e.nome or "")
        conj = str(m.get("conjunto") or "")
        t = tipos.get(pos, "")
        tc = tipos_conj.get(conj, "") if conj and conj != pos else ""
        if conj_info.get(conj, {}).get("categoria") == "TESOURAS":
            return ("tesoura", nomes_conj.get(conj) or conj)
        if tc in ("agulhamento", "agulhamento_lateral", "agulhamento_diagonal", "contraventamento", "conjunto", "chumbador"):
            return (tc, nomes_conj.get(conj) or conj)
        return (t or "peca", nomes_pos.get(pos) or pos)
    rotulos = {"tesoura": "tesoura", "conjunto": "dispositivo (DP.)", "terca_cobertura": "terça de cobertura (T.C.)",
               "terca_lateral": "terça lateral (T.L.)", "terca_oitao": "terça do oitão (T.O.)", "terca_marquise": "terça de marquise (T.M.)",
               "agulhamento": "agulhamento de cobertura (A.C.)", "agulhamento_lateral": "agulhamento lateral (A.L.)",
               "agulhamento_diagonal": "agulhamento diagonal (A.D.)", "contraventamento": "contraventamento (CV.)",
               "chumbador": "chumbador (CB)", "suporte_terca": "chapa (CH)", "chapa": "chapa solta (CH)", "castanha": "chapa (CH)",
               "suporte_agulhamento": "chapa (CH)", "suporte_contraventamento": "chapa (CH)", "perfil_fechamento": "fixação de telha (F.T.)",
               "cantoneira_forro": "acabamento (A.T.)", "barra_roscada": "barra roscada (BR)", "gancho": "gancho", "barra": "barra (B.)",
               "parte": "peça", "telha": "telha"}
    contagem: Dict[str, dict] = collections.OrderedDict()
    # as porcas e arruelas soltas de ponta roscada saem no padrão da fábrica (1 porca + 2 arruelas por
    # ponta, na bitola da barra — pedido do usuário, 28/09), no local da barra; as outras, como estão
    from nucleo2d.detalhe.base import (pontas_roscadas, PORCAS_POR_PONTA, ARRUELAS_POR_PONTA, PORCAS_POR_PERNA_CHUMBADOR,
                                       ARRUELAS_POR_PERNA_CHUMBADOR)
    pontas, usados = pontas_roscadas(pecas, fixadores)
    # o chumbador nunca na regra do parafuso (N07, decisão do usuário 16/10): no projeto recebido, as porcas e arruelas
    # que o projetista pôs (contadas como estão); no nosso, 2 porcas + 1 arruela por perna
    eh_chumbador = lambda pt: familia_peca(pt["peca"])[0] == "chumbador" or         tipos.get(str(_marcas(pt["peca"]).get("posicao") or pt["peca"].nome or "")) == "chumbador"     # noqa: E731
    if recebido:
        for pt in pontas:
            if eh_chumbador(pt):
                usados.difference_update(pt["fixadores"])
    for f in fixadores:
        if f.id in usados:
            continue
        info = eixos.get(f.id)
        if info is None:
            continue
        cc, eixo, meio, ext, porca = info
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+)", f.nome or "")
        if m and float(m.group(1).replace(",", ".")) > 0:
            d = float(m.group(1).replace(",", "."))
            # o chumbador químico (barra roscada HIT-V embutida no concreto, 09/10) sai com o nome dele, não como parafuso
            mc = re.search(r"\((A\d{3}[^)]*)\)", f.nome or "")
            chave = ("CHUMBADOR %g x %s" % (d, m.group(2))) if _eh_chumbador(f.nome) else (
                "M%g x %s" % (d, m.group(2)) + (" (%s)" % mc.group(1).strip() if mc else ""))
            eh_parafuso = True
        else:
            chave, d, _arruela = _fixador_solto(ext)
            eh_parafuso = False
        # as peças que o fixador atravessa: caixa contém o centro e há vértice a menos de
        # 1,6 raios do eixo (o furo em volta) perto do centro
        cand = grade.get((int(math.floor(cc[0] / cel)), int(math.floor(cc[1] / cel)), int(math.floor(cc[2] / cel))), [])
        atravessadas = []
        raio = max(d / 2.0, 6.0) * 1.8 + 3.0
        for e, cx in cand:
            if not (cx[0] - 25 <= cc[0] <= cx[3] + 25 and cx[1] - 25 <= cc[1] <= cx[4] + 25 and cx[2] - 25 <= cc[2] <= cx[5] + 25):
                continue
            D = arrays[e.id] - np.asarray(cc, dtype=float)
            t = D @ np.asarray(eixo, dtype=float)
            mask = np.abs(t) <= meio + 40.0
            if not mask.any():
                continue
            lat2 = (D[mask] ** 2).sum(axis=1) - t[mask] ** 2
            if (lat2 <= raio * raio).any():
                atravessadas.append(e)
        fams = sorted({familia_peca(e) for e in atravessadas}, key=lambda x: x[0])
        if not fams:
            local = ("sem peça reconhecida em volta", ())
        else:
            tipos_f = [x[0] for x in fams]
            nomes_f = sorted({x[1] for x in fams}, key=_ordem_natural)
            local = (" x ".join(dict.fromkeys(rotulos.get(t, t) for t in tipos_f)), tuple(nomes_f))
        r = contagem.setdefault(chave, {"parafuso": eh_parafuso, "qtd": 0, "locais": collections.OrderedDict(), "d": d})
        r["qtd"] += 1
        # o chumbador químico do modelo: o embutimento (para o químico) e se a arruela é uma chapa do projeto (a CH2 do
        # Vicente, 09/10: a arruela solta contava em dobro)
        cq = (f.atributos or {}).get("chumbador_quimico") or {}
        if cq:
            r["embutimento"] = float(cq.get("embutimento") or EMBUTIMENTO_QUIMICO)
            r["quimico"] = str(cq.get("quimico") or "HIT-RE 500")
            if cq.get("arruela") is False:
                r["sem_arruela"] = r.get("sem_arruela", 0) + 1
        lr = r["locais"].setdefault(local[0], {"qtd": 0, "pecas": set(), "ids": []})
        lr["qtd"] += 1
        lr["pecas"].update(local[1])
        lr["ids"].append(f.id)                              # para "ver no 3D" a pendência (06/10)
    for pt in pontas:
        fam = familia_peca(pt["peca"])
        local = rotulos.get(fam[0], fam[0])
        n_porcas, n_arruelas = PORCAS_POR_PONTA, ARRUELAS_POR_PONTA
        if eh_chumbador(pt):
            if recebido:
                continue                                        # as do modelo, contadas acima
            n_porcas, n_arruelas = PORCAS_POR_PERNA_CHUMBADOR, ARRUELAS_POR_PERNA_CHUMBADOR
        for chave, q in (("Porca %s" % (pt["bitola"] or "?"), n_porcas), ("Arruela %s" % (pt["bitola"] or "?"), n_arruelas)):
            r = contagem.setdefault(chave, {"parafuso": False, "qtd": 0, "locais": collections.OrderedDict(), "d": pt["d"]})
            r["qtd"] += q
            lr = r["locais"].setdefault(local, {"qtd": 0, "pecas": set(), "ids": []})
            lr["qtd"] += q
            lr["pecas"].add(fam[1])
    saida = []
    for chave, r in contagem.items():
        if r["parafuso"] and chave.startswith("CHUMBADOR"):
            nome, desc = descricao_chumbador(r["d"], chave.rsplit(" ", 1)[-1])
        elif r["parafuso"]:
            mc = re.search(r"\((A\d{3}[^)]*)\)", chave)
            nome, desc, _d = descricao_parafuso(chave.split(" (")[0].replace(" ", ""), mc.group(1) if mc else None)
        else:
            nome = chave
            desc = ("Arruela lisa Ø%s" if chave.startswith("Arruela") else "Porca sextavada Ø%s UNC") % chave.split(" ", 1)[1]
        locais = sorted(r["locais"].items(), key=lambda kv: -kv[1]["qtd"])
        if r.get("sem_arruela") and r["sem_arruela"] >= r["qtd"]:
            desc = desc.replace(" + porca e arruela", " + porca (a arruela é chapa do projeto)")
        saida.append({"nome": nome, "descricao": desc, "qtd": r["qtd"], "parafuso": r["parafuso"], "d": r["d"],
                      "sem_arruela": int(r.get("sem_arruela") or 0), "embutimento": r.get("embutimento"), "quimico": r.get("quimico"),
                      "locais": [{"local": k, "qtd": v["qtd"], "pecas": sorted(v["pecas"], key=_ordem_natural), "ids": v.get("ids") or []}
                                 for k, v in locais]})
    saida.sort(key=lambda x: (not x["parafuso"], x["d"] or 0, _ordem_natural(x["nome"])))
    return saida


def descricao_telha(perfil: str, dados_telha: str = "") -> str:
    """A descrição comercial de uma telha pelo perfil dela ("TELHA TP40 0.65MM" → "Telha TP40 0,65 mm"). A dos dados do
    resumo vale quando é a mesma espessura (ela é uma só para a obra: a multi-dobra de 0,65 saía como 0,50, 05/10); o
    "Telha TELHA" repetido sai. A espessura também como "ESP.0.65" sem o MM (o depósito da SOORO, 09/10: a cobertura
    de 0,65 entrava na compra como a de 0,50 dos dados)."""
    base = re.sub(r"(?i)^\s*telha\s+", "", str(perfil or "")).strip()
    m = re.search(r"(\d+[.,]\d+)\s*MM", base, re.I) or re.search(r"\bESP\.?\s*(\d+[.,]\d+)\b", base, re.I)
    esp = m.group(1).replace(".", ",") if m else ""
    d = re.sub(r"(?i)^\s*telha\s+telha\b", "Telha", str(dados_telha or "").strip())
    d = re.sub(r"(\d+)[.,](\d+)\s*MM\b", r"\1,\2 mm", d, flags=re.I)
    if d and (not esp or esp.replace(",", ".") in d.replace(",", ".")):
        return d
    nome = re.sub(r"\s*(\d+[.,]\d+\s*MM|\bESP\.?\s*\d+[.,]\d+\b)", "", base, flags=re.I).strip()
    return ("Telha %s %s mm" % (nome, esp)).replace("  ", " ") if esp else ("Telha %s" % base if base else "Telha")


def _telhas(lev: dict, lista: dict, pecas_por_marca, nivel_apoio, dados) -> dict:
    """As telhas por trecho — cobertura, fechamento (oitões e paredes) e forro do beiral —, com o nome de produção da
    lista (o mesmo das pranchas) e a descrição de cada uma pelo perfil dela."""
    descricao = re.sub(r"(?i)^\s*telha\s+telha\b", "Telha", str(dados.get("telha") or "").strip())
    linhas_lista = [li for li in (lista.get("posicoes") or []) if li.get("categoria") == "TELHAS"]
    itens = []
    for li in linhas_lista:
        classe = str(li.get("classe") or "")
        if "multi-dobra" in classe.lower() and "complemento" not in classe.lower():
            trecho, codigo = "cobertura", "MD"
        elif "cumeeira" in classe.lower():
            trecho, codigo = "cobertura", "CU"
        else:
            codigo = "TL"
            # pela geometria da peça: normal quase vertical = cobertura ou forro
            # (forro: abaixo do apoio das tesouras); normal deitada = fechamento
            trecho = "cobertura"
            ents = pecas_por_marca.get(str(li["marca"]).split(" / ")[0]) or []
            if ents:
                e = ents[0]
                _c, pca = _autovetores(e.vertices)
                nz = abs(pca[2][2])
                cz = sum(v[2] for v in e.vertices) / len(e.vertices)
                if nz < 0.5:
                    trecho = "fechamento"
                elif nivel_apoio is not None and cz < nivel_apoio - 50.0:
                    trecho = "forro"
        comp = float(li.get("comprimento") or 0.0)
        cortada = any("cortada" in str(o).lower() or "corte em obra" in str(o).lower() for o in (li.get("observacoes") or []))
        qtd = int(li.get("quantidade") or 0)
        ml = comp * qtd / 1000.0
        itens.append({"trecho": trecho, "codigo": codigo, "marca": li["marca"], "perfil": li.get("perfil", ""), "nome": li.get("nome") or "",
                      "descricao": descricao_telha(li.get("perfil", ""), descricao),
                      "qtd": qtd, "comprimento": comp, "ml": ml, "m2": float(li.get("area_m2") or ml * LARGURA_UTIL_TELHA / 1000.0),
                      "kg": float(li.get("peso_total") or 0.0), "cortada": cortada, "classe": classe})
    ordem_trecho = {"cobertura": 0, "fechamento": 1, "forro": 2}
    itens.sort(key=lambda t: (ordem_trecho[t["trecho"]], {"TL": 0, "MD": 1, "CU": 2}[t["codigo"]], -t["comprimento"]))
    n_por = collections.Counter()
    for t in itens:
        n_por[t["codigo"]] += 1
        t["codigo_n"] = t["nome"] or "%s%d" % (t["codigo"], n_por[t["codigo"]])
    trechos = collections.OrderedDict()
    for t in itens:
        trechos.setdefault(t["trecho"], []).append(t)
    return {"descricao": descricao, "itens": itens, "trechos": trechos,
            "ml_total": sum(t["ml"] for t in itens), "kg_total": sum(t["kg"] for t in itens),
            "m2_total": sum(t["m2"] for t in itens),
            "ml_por_trecho": {k: sum(t["ml"] for t in v) for k, v in trechos.items()},
            "m2_por_trecho": {k: sum(t["m2"] for t in v) for k, v in trechos.items()},
            "largura_util": LARGURA_UTIL_TELHA}


def _tercas(posicoes, tipos, pecas_por_marca, trechos, limites, eixo_g, perp_g, nomes_pos, limites_g=None) -> dict:
    """Linhas de terça por trecho (na cobertura por água, nas saias por lado) e as
    famílias: quantas terças de cobertura, laterais e de oitão, em quantos tipos, o perfil
    principal e a furação."""
    fam = {"terca_cobertura": "cob", "terca_lateral": "lat", "terca_oitao": "oit", "terca_marquise": "marq"}
    parede = {"lateral": "lat", "oitao": "oit"}
    contagem = {k: {"pecas": 0, "tipos": 0} for k in fam.values()}
    perfis = collections.Counter()
    furos = collections.Counter()
    centros = []                                     # (familia, ponto ao longo do galpão, transversal, z)
    itens: List[dict] = []                           # uma linha por tipo de terça (a tabela do resumo da obra)
    for p in posicoes:
        t = tipos.get(p.marca, "")
        if t not in fam:
            continue
        contagem[fam[t]]["tipos"] += 1
        # as peças pelo tipo (T.C., T.L., T.O.: o nome da lista e das pranchas); a orientação de cada peça só conta as
        # linhas — antes, as T.C. das saias contavam como laterais (72 T.C. e 24 T.L. contra 83 e 13 na lista, 05/10)
        contagem[fam[t]]["pecas"] += p.quantidade
        itens.append({"familia": fam[t], "nome": nomes_pos.get(p.marca) or p.marca, "perfil": com_bitola(p.perfil),
                      "comprimento": float(p.comprimento or 0.0), "qtd": p.quantidade, "kg": p.peso_total})
        perfis[com_bitola(p.perfil)] += p.quantidade
        for f in p.furos:
            furos[f.rotulo()] += 1
        for m in marcas_de(p):
            for e in pecas_por_marca.get(m) or []:
                # cada peça pela orientação dela: a mesma posição pode viajar na cobertura e na saia
                k = parede.get(_parede_da_peca(e, eixo_g, limites_g)) or ("marq" if t == "terca_marquise" else "cob")
                c = sum(v[0] for v in e.vertices) / len(e.vertices), sum(v[1] for v in e.vertices) / len(e.vertices), sum(v[2] for v in e.vertices) / len(e.vertices)
                centros.append((k, _dot(c, eixo_g), _dot(c, perp_g), c[2]))
    def _linhas_de(pontos) -> List[Tuple[float, float]]:
        """Agrupa os centros (transversal, z) em linhas: pontos a menos de 150 mm nas duas
        direções são a mesma linha (peças emendadas ou de comprimentos diferentes)."""
        linhas_: List[List[float]] = []
        for y, z in sorted(pontos):
            for li in linhas_:
                if abs(li[0] - y) <= 150.0 and abs(li[1] - z) <= 150.0:
                    break
            else:
                linhas_.append([y, z])
        return [(y, z) for y, z in linhas_]

    linhas = []
    for tr, (a0, a1) in zip(trechos, limites):
        cob = _linhas_de([(y, z) for k, a, y, z in centros if k == "cob" and a0 <= a <= a1])
        ys = [y for k, a, y, z in centros if k == "cob" and a0 <= a <= a1]
        meio = (max(ys) + min(ys)) / 2.0 if ys else 0.0
        por_agua = collections.Counter("esq" if y < meio else "dir" for y, z in cob)
        saias = _linhas_de([(y, z) for k, a, y, z in centros if k == "lat" and a0 <= a <= a1])
        por_lado = collections.Counter("esq" if y < meio else "dir" for y, z in saias)
        linhas.append({"trecho": tr["nome"], "eixos": tr["eixos"], "cobertura": len(cob), "por_agua": dict(por_agua),
                       "saias": len(saias), "por_lado": dict(por_lado), "total": len(cob) + len(saias)})
    perfil_principal = perfis.most_common(1)[0][0] if perfis else ""
    itens.sort(key=lambda i: (list(fam.values()).index(i["familia"]), _ordem_natural(i["nome"])))
    return {"contagem": contagem, "linhas": linhas, "perfil_principal": perfil_principal, "itens": itens,
            "furos": ", ".join("%s" % r for r, _ in furos.most_common(3))}


#: As observações da lista que pedem conferência (as outras — a saia da telha, o perfil original, o furo pelo
#: parafuso — são informação e ficam na lista de materiais). O comprimento da peça curva pelo volume ÷ seção é
#: informação (06/10: a fábrica não dobra, calandra ou corta em trechos retos; a conta fecha com o catálogo); fica
#: pendência quando não sai.
_PEDE_CONFERENCIA = re.compile(r"difere|conferir|não calculad|do plano da seção|sem peça", re.I)


def _pendencias(lista: dict, parafusos: List[dict], lev: dict, nomes_pos: dict) -> List[dict]:
    """O que conferir antes de fabricar: as ressalvas da lista que pedem conferência (a medida diferente do nome do
    TecnoMETAL, o comprimento de corte não calculado ou estimado pelo volume, a peça que sai do plano), os parafusos sem
    peça reconhecida em volta e os avisos do levantamento que não repetem as ressalvas. Cada uma leva os `ids` das peças
    do modelo, para a tela abrir o 3D com elas em destaque (06/10)."""
    ids_da_marca = {p.marca: list(getattr(p, "global_ids", None) or []) for p in lev.get("posicoes") or []}
    saida = []
    for r in lista.get("ressalvas") or []:
        nome = " / ".join(dict.fromkeys(nomes_pos.get(m.strip()) or m.strip() for m in str(r.get("marca") or "").split(" / ")))
        for o in r.get("observacoes") or []:
            if _PEDE_CONFERENCIA.search(str(o)):
                saida.append({"peca": nome, "perfil": r.get("perfil_nome") or r.get("perfil") or "", "o_que": str(o),
                              "ids": ids_da_marca.get(r.get("marca") or "", [])})
    ja_medidas = any("difere" in x["o_que"] for x in saida)
    for it in parafusos:
        for loc in it.get("locais") or []:
            if loc["local"].startswith("sem peça"):
                saida.append({"peca": it["nome"], "perfil": "", "o_que": "%d sem peça reconhecida em volta (parafuso solto no modelo?)" % loc["qtd"],
                              "ids": list(loc.get("ids") or [])})
    for a in _avisos_que_contam(lev.get("avisos") or []):
        if not (ja_medidas and "nome do TecnoMETAL" in str(a)):
            saida.append({"peca": "", "perfil": "", "o_que": str(a)})
    for x in saida:
        x["chave"] = chave_da_pendencia(x)
    return saida


def chave_da_pendencia(x: dict) -> str:
    """A chave que liga a pendência à resposta do usuário (13/10): peça + o que conferir, sem os números que mudam
    de uma geração para outra (quantidades, medidas em mm), para a resposta sobreviver a um resumo gerado de novo."""
    texto = "%s|%s" % (str(x.get("peca") or "").strip().lower(), re.sub(r"\d+", "#", str(x.get("o_que") or "").strip().lower()))
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:10]


def _avisos_que_contam(avisos) -> List[str]:
    """Os avisos do levantamento que mudam um número (peso) ou pedem conferência; os outros ficam no detalhamento."""
    return [str(a) for a in avisos if "peso" in str(a).lower() or "conferir" in str(a).lower()]


def _perimetro_m(perfil: str) -> Optional[float]:
    """A superfície por metro (m²/m) do perfil: o perímetro da seção do catálogo (a mesma do 3D)."""
    try:
        from nucleo3d import geometria as G
        sec = G.secao(G.resolver_perfil(perfil))
    except Exception:                                       # noqa: BLE001 — perfil fora do catálogo
        return None
    if not sec or len(sec) < 3:
        return None
    per = sum(math.hypot(sec[i][0] - sec[i - 1][0], sec[i][1] - sec[i - 1][1]) for i in range(len(sec)))
    return per / 1000.0


def _area_de_pintura(lista: dict) -> dict:
    """A área de pintura (05/10: "área de pintura — sim"): perfis e barras pelo perímetro da seção × o comprimento; as
    chapas pelas duas faces. As telhas não entram (vêm pintadas)."""
    perfis, sem = [], []
    for g in lista.get("perfis") or []:
        pm = _perimetro_m(g.get("perfil") or "")
        if pm is None:
            sem.append(g.get("perfil") or "")
            continue
        perfis.append({"perfil": com_bitola(g.get("perfil") or ""), "m2_m": pm, "m": float(g.get("comprimento_m") or 0.0),
                       "m2": pm * float(g.get("comprimento_m") or 0.0)})
    chapas_m2 = 2.0 * sum(float(c.get("area_m2") or 0.0) for c in lista.get("chapas") or [])
    total = sum(p["m2"] for p in perfis) + chapas_m2
    return {"perfis": perfis, "chapas_m2": chapas_m2, "total_m2": total, "sem_secao": sem}


def _bitola_pol(d: Optional[float]) -> str:
    return _pol_mais_perto(d) or "M%g" % float(d or 0)


def _compra(lista: dict, parafusos: List[dict], telhas: dict, dados: dict) -> dict:
    """A parte de compra do resumo de materiais: perfis em barras comerciais (o plano de corte da lista: W em 12 m, o
    resto em 6 m), chapas em chapas comerciais de 1,20 × 3,00 (pela área, com a perda), parafusos, porcas e arruelas
    separados e somados por bitola, telhas por perfil em ml e m²."""
    perfis = []
    pos_por_marca = {li.get("marca"): li for li in lista.get("posicoes") or []}
    for g in lista.get("perfis") or []:
        b = g.get("barras") or {}
        perfis.append({"perfil": com_bitola(g.get("perfil") or ""), "material": g.get("material") or "", "kg": float(g.get("peso") or 0.0),
                       "pecas": int(g.get("pecas") or 0), "kg_m": float(g.get("kg_m") or 0.0), "catalogo": g.get("catalogo") or "",
                       "fora_do_catalogo": g.get("fonte_kg_m") == "calculado", "similar": g.get("fonte_kg_m") == "similar",
                       "escolhido": g.get("fonte_kg_m") == "escolhido", "ifc": g.get("perfil") or "",
                       "m": float(g.get("comprimento_m") or 0.0), "barra_m": float(b.get("comprimento") or 0.0) / 1000.0,
                       "barras": int(b.get("quantidade") or 0), "aproveitamento": b.get("aproveitamento"), "emendas": int(b.get("emendas") or 0)})
        # o peso de compra (07/10): cada barra comercial pelo kg/m do catálogo (o do similar ou o escolhido), e as barras todas
        pf = perfis[-1]
        kg_m_compra = float(g.get("kg_m_catalogo") or 0.0) or pf["kg_m"]
        pf["kg_barra"] = kg_m_compra * pf["barra_m"]
        # as peças sob medida (13/10): a terça e o dobrado maior que a barra, no comprimento delas, sem sobra
        pf["sob_medida_pecas"] = int(b.get("sob_medida_pecas") or 0)
        pf["sob_medida_m"] = float(b.get("sob_medida_m") or 0.0)
        pf["kg_sob_medida"] = kg_m_compra * pf["sob_medida_m"]
        pf["kg_compra"] = pf["kg_barra"] * pf["barras"] + pf["kg_sob_medida"]
        # a emenda ligada no plano de corte (07/10): as peças que saem em dois pedaços, e as barras que ela poupa
        pf["emendadas"] = len(b.get("emendadas") or []) if g.get("emenda") else 0
        sem = (g.get("barras_sem_emenda") or {}).get("quantidade")
        pf["barras_sem_emenda"] = int(sem) if g.get("emenda") and sem else 0
        # sem aproveitamento (09/10, para comparar lado a lado): cada posição cortada só das barras dela — a sobra não
        # serve a outra peça — e a peça maior que a barra em barras inteiras, sem emenda
        pf["barras_sem_aproveitamento"] = _barras_sem_aproveitamento(
            [pos_por_marca[mk] for mk in g.get("posicoes") or [] if mk in pos_por_marca], float(b.get("comprimento") or 0.0),
            g.get("sob_medida") or "")
        pf["kg_sem_aproveitamento"] = pf["kg_barra"] * pf["barras_sem_aproveitamento"] + pf["kg_sob_medida"]
    try:
        perda = float(str(dados.get("perda_chapas") or "").replace(",", ".").replace("%", "")) if dados.get("perda_chapas") else PERDA_CHAPAS
    except ValueError:
        perda = PERDA_CHAPAS
    area_chapa = CHAPA_COMERCIAL[0] * CHAPA_COMERCIAL[1] / 1e6
    chapas = []
    for c in _chapas_por_rotulo(lista.get("chapas")):
        m2 = c["m2"]
        chapas.append({"rotulo": c["rotulo"], "bitola": c["bitola"], "mm": c["mm"], "polegada": c["polegada"], "modelo": c["modelo"],
                       "material": c["material"], "m2": m2, "kg": c["kg_compra"], "pecas": c["pecas"],
                       "chapas": int(math.ceil(m2 * (1.0 + perda / 100.0) / area_chapa - 1e-9)) if m2 > 0 else 0})
    # cada parafuso vem com 1 porca e 1 arruela ("+ porca e arruela"); as porcas e arruelas soltas (pontas roscadas,
    # chumbadores) somam na bitola delas
    pf, porcas, arruelas, quimico = [], collections.Counter(), collections.Counter(), collections.OrderedDict()
    for it in parafusos:
        if it["parafuso"]:
            # os ids dos parafusos do item: o "ver no 3D ↗" da linha (14/10, "onde vão esses 6 parafusos?")
            pf.append({"nome": it["nome"], "descricao": it["descricao"], "qtd": it["qtd"],
                       "ids": [i for lc in it.get("locais") or [] for i in lc.get("ids") or []]})
            porcas[_bitola_pol(it.get("d"))] += it["qtd"]
            # a arruela que já é chapa do projeto (a CH2 do chumbador da CH1) não se compra solta
            if it["qtd"] - int(it.get("sem_arruela") or 0):
                arruelas[_bitola_pol(it.get("d"))] += it["qtd"] - int(it.get("sem_arruela") or 0)
            if it.get("embutimento"):
                q_ = quimico.setdefault(it.get("quimico") or "HIT-RE 500", {"furos": 0, "ml": 0.0})
                q_["furos"] += it["qtd"]
                q_["ml"] += it["qtd"] * volume_quimico_ml(it["d"], it["embutimento"])
        else:
            alvo = arruelas if it["nome"].startswith("Arruela") else porcas
            alvo[it["nome"].split(" ", 1)[1] if " " in it["nome"] else it["nome"]] += it["qtd"]
    ordem_b = lambda b: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", b)]   # noqa: E731
    telhas_p = collections.OrderedDict()
    for it in telhas.get("itens") or []:
        r = telhas_p.setdefault(it["descricao"], {"descricao": it["descricao"], "ml": 0.0, "m2": 0.0, "kg": 0.0, "pecas": 0})
        r["ml"] += it["ml"]
        r["m2"] += it["m2"]
        r["kg"] += it["kg"]
        r["pecas"] += it["qtd"]
    return {"perfis": perfis, "chapas": chapas, "outros_aco": _outros_aco(lista), "perda_chapas": perda, "chapa_comercial": CHAPA_COMERCIAL,
            "parafusos": pf, "porcas": sorted(porcas.items(), key=lambda kv: ordem_b(kv[0])),
            "arruelas": sorted(arruelas.items(), key=lambda kv: ordem_b(kv[0])), "telhas": list(telhas_p.values()),
            "quimicos": [dict(v, nome=k, **cartuchos_quimico(v["ml"])) for k, v in quimico.items()]}


def _barras_e_sob_medida(barras: int, sob: int, nome: str = "barras") -> str:
    """"40 barras" ou "7 barras + 14 peças sob medida"."""
    t = "%d %s" % (barras, nome)
    return t + (" + %d peças sob medida" % sob if sob else "")


def _celula_barras(barras: int, p: dict) -> str:
    """A célula das barras no quadro de compra: o número, e embaixo as peças sob medida, quando há (13/10)."""
    sob = int(p.get("sob_medida_pecas") or 0)
    if not sob:
        return str(barras or "")
    return "%s<br><span class=\"cinza\">+%d sob medida</span>" % (barras or "—", sob)


def _mesmo_nome(perfil: str) -> str:
    """O nome do perfil para comparar o do catálogo com o do IFC: "TQ 50×50×3,0" e "TQ 50x50x3,0" são o mesmo."""
    return str(perfil or "").upper().replace("×", "X").replace(" ", "").replace(",", ".")


def _barras_sem_aproveitamento(posicoes: List[dict], barra: float, sob_medida: str = "") -> int:
    """Barras comerciais sem aproveitamento: cada posição só das barras dela (n peças por barra, com a perda de corte
    entre elas); a peça maior que a barra leva ceil(L / barra) barras inteiras. A peça sob medida (`sob_medida` "todas"
    ou "maiores" que a barra, 13/10) não leva barra: entra pelos metros dela."""
    from saida.lista_producao import PERDA_CORTE
    if barra <= 0:
        return 0
    n = 0
    for li in posicoes:
        L, q = float(li.get("comprimento") or 0.0), int(li.get("quantidade") or 0)
        if L <= 0 or q <= 0:
            continue
        if sob_medida == "todas" or (sob_medida and L > barra + 1e-6):
            continue
        if L > barra + 1e-6:
            n += q * int(math.ceil(L / barra - 1e-9))
        else:
            por_barra = max(1, int((barra + PERDA_CORTE) // (L + PERDA_CORTE)))
            n += int(math.ceil(q / por_barra - 1e-9))
    return n


def _outros_aco(lista: dict) -> List[dict]:
    """O aço que o IFC traz fora das peças de perfil e chapa — o guarda-corpo (gradil), o piso de chapa perfurada —, por
    tipo (o do Revit sem a família): peças, metros lineares e m². Sem o peso: a malha do gradil traz barra maciça no
    lugar de tubo e pesaria várias vezes mais (36 t na Passarela Mirante, 06/10)."""
    from nucleo.catalogo import nome_do_ifc
    g: Dict[str, dict] = collections.OrderedDict()
    for it in lista.get("pre_moldados") or []:
        if it.get("categoria") != "aço fora das peças":
            continue
        nome = str(it.get("nome") or "?")
        familia = nome.split(":", 1)[0].strip() if ":" in nome else ""
        r = g.setdefault(nome, {"item": nome_do_ifc(nome), "familia": familia, "pecas": 0, "ml": 0.0, "m2": 0.0, "abertas": 0})
        r["pecas"] += int(it.get("quantidade") or 0)
        r["ml"] += float(it.get("comprimento_m") or 0.0)
        r["m2"] += float(it.get("area_m2") or 0.0)
        r["abertas"] += int(it.get("abertas") or 0)
    return sorted(g.values(), key=lambda r: (r["familia"], r["item"]))


def _maior_e_mais_pesada(lista: dict, tipos_tes: List[dict], nome_trelica: str = "tesoura"):
    """A maior peça (comprimento, para o transporte) e a mais pesada (para o içamento): entre as peças soltas e os
    conjuntos montados (a tesoura inteira, ou as meias quando é fabricada em duas)."""
    # sem as telhas e a funilaria (rufo, calha: chapa dobrada de aluzinc, não é peça de aço a transportar montada)
    funilaria = re.compile(r"RUFO|CALHA", re.I)
    soltas = [li for li in lista.get("posicoes") or [] if li.get("categoria") != "TELHAS"
              and not re.match(r"(RF|CL)\d", str(li.get("nome") or "")) and not funilaria.search(str(li.get("perfil") or "") + str(li.get("classe") or ""))]
    maior = max(soltas, key=lambda li: float(li.get("comprimento") or 0.0), default=None)
    m = {"nome": (maior.get("nome") or maior.get("marca")) if maior else "", "comprimento": float(maior.get("comprimento") or 0.0) if maior else 0.0,
         "perfil": com_bitola(maior.get("perfil") or "") if maior else ""}
    cands = [((li.get("nome") or li.get("marca")), float(li.get("peso") or 0.0), "peça") for li in soltas]
    de_tesoura = {m for tt in tipos_tes for m in tt.get("marcas") or []}
    cands += [((c.get("nome") or c.get("marca")), float(c.get("peso_unitario") or 0.0), "conjunto") for c in lista.get("conjuntos") or []
              if c.get("categoria") != "TESOURAS" and c.get("marca") not in de_tesoura]
    # a tesoura é içada montada (as meias têm os mesmos nomes T1, T2… das tesouras: "T5 (conjunto)" confundia)
    cands += [("%s %s" % (nome_trelica, tt["tipo"]), float(tt.get("kg_un") or 0.0), "montada") for tt in tipos_tes]
    nome, kg, tipo = max(cands, key=lambda c: c[1], default=("", 0.0, ""))
    return m, {"nome": nome, "kg": kg, "tipo": tipo}


# ============================================================ HTML
# a mesma identidade da proposta comercial (08/10): grafite, verde-limão, Segoe UI, os traços inclinados,
# cartões de números e tabelas abertas; as cores da compra (âmbar, vermelho, azul) seguem as mesmas
_CSS = """
@page { size: A4; margin: 19mm 12mm 15mm 12mm;
  @top-left { content: element(cabecalho); vertical-align: bottom; padding-bottom: 3mm; }
  @top-right { content: element(cabref); vertical-align: bottom; padding-bottom: 3mm; }
  @bottom-left { content: element(rodape); vertical-align: top; padding-top: 2.5mm; }
  @bottom-right { content: counter(page) " / " counter(pages); font: 600 7.6pt 'Segoe UI', Arial, sans-serif; color: #6b7780;
                  vertical-align: top; padding-top: 2.5mm; }
}
@page :first { margin-top: 12mm; @top-left { content: none; } @top-right { content: none; } }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font: 8.6pt/1.42 'Segoe UI', 'Segoe UI Variable', Arial, Helvetica, sans-serif; color: var(--texto); }
b { font-weight: 600; }
.cabecalho { position: running(cabecalho); }
.cabecalho .logo { height: 6.5mm; display: block; }
.cabecalho .logo-texto, .rodape b { color: var(--pri); font-weight: 600; }
.cabref { position: running(cabref); font: 600 7.2pt 'Segoe UI', Arial; color: var(--mudo); letter-spacing: .06em; text-transform: uppercase; text-align: right; }
.cabref b { color: var(--pri); }
.rodape { position: running(rodape); font: 7.2pt 'Segoe UI', Arial; color: var(--mudo); }
.cinza { color: var(--mudo); font-size: 7.6pt; }
.mono { font-family: Consolas, monospace; font-size: 8pt; }
.pecas { color: var(--mudo); font-size: 7.4pt; }

/* ---------------- faixa do topo (a capa da proposta, em uma faixa) */
.faixa-topo { background: var(--pri2); color: #fff; border-radius: 3mm; padding: 6mm 8mm 5mm; position: relative; overflow: hidden; break-inside: avoid; }
.faixa-topo::after { content: ""; position: absolute; right: -10mm; top: -5mm; width: 46mm; height: 10mm; background: var(--dest); opacity: .9; transform: skewX(-38deg); }
.faixa-topo .topo { display: flex; justify-content: space-between; align-items: center; gap: 6mm; position: relative; z-index: 1; padding-right: 30mm; }
.faixa-topo .logo { height: 8mm; display: block; }
.faixa-topo .logo-texto { font: 600 11pt 'Segoe UI', Arial; color: #fff; }
.faixa-topo .rev { font: 600 7.4pt 'Segoe UI', Arial; letter-spacing: .14em; text-transform: uppercase; color: rgba(255,255,255,.85);
                   border: 1px solid rgba(255,255,255,.45); padding: 1.2mm 3mm; border-radius: 99px; white-space: nowrap; }
.marca { display: flex; gap: 2mm; margin: 6mm 0 3mm; }
.marca i { width: 8mm; height: 2.6mm; background: var(--dest); transform: skewX(-38deg); display: block; }
.marca i + i { opacity: .55; }
.faixa-topo .rotulo { font: 600 7.8pt 'Segoe UI', Arial; letter-spacing: .26em; text-transform: uppercase; color: var(--dest); }
.faixa-topo h1 { font: 300 21pt/1.1 'Segoe UI Light', 'Segoe UI', Arial; margin: 1.5mm 0 0; letter-spacing: -.01em; color: #fff; }
.faixa-topo .desc { margin-top: 1.5mm; font-size: 9pt; color: rgba(255,255,255,.8); }
.faixa-topo .pe { margin-top: 5mm; padding-top: 3mm; border-top: 1px solid rgba(255,255,255,.18); display: flex; flex-wrap: wrap; gap: 1mm 7mm;
                  font-size: 7.6pt; color: rgba(255,255,255,.66); }
.faixa-topo .pe b { color: #fff; font-weight: 600; }

/* ---------------- quadro de números (os cartões da ficha técnica) */
.ficha { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2.6mm; margin: 4.5mm 0 1mm; break-inside: avoid; }
.ficha div { background: var(--fundo); border-radius: 2.2mm; padding: 2.6mm 3.2mm 2.4mm; border-top: 2.4px solid var(--dest); }
.ficha span { display: block; font: 600 6.6pt 'Segoe UI', Arial; color: var(--mudo); letter-spacing: .13em; text-transform: uppercase; }
.ficha b { display: block; font: 300 15pt/1.15 'Segoe UI Light', 'Segoe UI', Arial; color: var(--pri); margin-top: .6mm; white-space: nowrap; }
.ficha b small { font-size: 8pt; font-weight: 600; color: var(--mudo); margin-left: .8mm; }
.ficha em { display: block; font-style: normal; font-size: 7pt; color: var(--mudo); line-height: 1.3; margin-top: .6mm; }

/* ---------------- títulos */
h2 { display: flex; align-items: flex-end; gap: 3.5mm; margin: 6.5mm 0 2.5mm; padding-bottom: 2mm; border-bottom: 1.2px solid var(--linha);
     font: 700 11.5pt/1.1 'Segoe UI', Arial; color: var(--pri); break-after: avoid; }
h2 .n { font: 300 19pt/0.85 'Segoe UI Light', 'Segoe UI', Arial; color: var(--dest); min-width: 8mm; }
h2 .tag { margin-left: auto; font: 600 7pt 'Segoe UI', Arial; letter-spacing: .14em; text-transform: uppercase; color: var(--mudo); white-space: nowrap; }
h2.parte { font-size: 14pt; border-bottom-color: var(--pri); }
h2.parte .n { font-size: 26pt; }
h2 .tag.ok { color: #4f5f12; background: #eef4d5; padding: .8mm 2.6mm; border-radius: 99px; letter-spacing: .08em; }
h2 .tag.atencao { color: #7a4f00; background: #fff4d6; padding: .8mm 2.6mm; border-radius: 99px; letter-spacing: .08em; }
h3 { display: flex; align-items: center; gap: 2.2mm; font: 700 9.4pt 'Segoe UI', Arial; color: var(--pri); margin: 4.5mm 0 1mm; break-after: avoid; }
h3::before { content: ""; width: 3.6mm; height: 1.5mm; background: var(--dest); transform: skewX(-38deg); flex: none; }
.nota { font-size: 7.6pt; color: var(--mudo); margin: .6mm 0 2mm; }
.explica { font-size: 7.6pt; color: var(--mudo); margin: 0 0 1.2mm; }
.sub { font-size: 8.6pt; margin: 0; }

/* ---------------- tabelas (as da proposta: abertas, cabeçalho em versalete) */
table { border-collapse: collapse; width: 100%; font-size: 8pt; margin: .8mm 0 1.6mm; }
tr { break-inside: avoid; }
th { text-align: left; font: 600 6.6pt 'Segoe UI', Arial; letter-spacing: .09em; text-transform: uppercase; color: var(--mudo);
     border-bottom: 1.2px solid var(--pri); padding: 1.4mm 1.5mm; vertical-align: bottom; }
td { padding: 1.05mm 1.5mm; border-bottom: 1px solid var(--linha); vertical-align: top; }
table.inteira { break-inside: avoid; }
td.r, th.r { text-align: right; }
td.r { white-space: nowrap; }
td.c, th.c { text-align: center; }
tr.total td { font-weight: 700; color: var(--pri); background: var(--fundo); border-top: 1.2px solid var(--pri); border-bottom: 0; }
tr.resolvida td { color: #6b7780; }
tr.resolvida td:nth-child(4) b { color: #2c6e37; }
table.tes { font-size: 7.5pt; }
table.tes td, table.tes th { padding: 1.1mm 1.1mm; }
/* a compra diferente do projeto, para a conferência (06/10): similar âmbar, fora do catálogo vermelho, escolhido azul */
tr.compra-similar td { background: #fff4d6; } tr.compra-similar td b, tr.compra-similar .cinza { color: #7a4f00; }
tr.compra-fora td { background: #fde4e1; } tr.compra-fora td b, tr.compra-fora .cinza { color: #9b1c1c; }
tr.compra-escolhido td { background: #e3edff; } tr.compra-escolhido td b, tr.compra-escolhido .cinza { color: #0b3d91; }
/* a compra de perfis com e sem aproveitamento, lado a lado (09/10): um bloco de cada cor */
table th.ap-com, table td.ap-com, tr td.ap-com, .legenda-compra .ap-com { background: #e6f2e1; }
table th.ap-sem, table td.ap-sem, tr td.ap-sem, .legenda-compra .ap-sem { background: #fbe9dc; }
tr.grupos th { font-size: 7.4pt; text-align: center; letter-spacing: .04em; border-bottom: none; }
tr.grupos th.ap-com { color: #2f5d1e; } tr.grupos th.ap-sem { color: #8a3d0c; }
tr.grupos th.ap-proj { color: var(--pri); border-bottom: 1.2pt solid var(--pri); }
table.compra-perfis { font-size: 7pt; table-layout: fixed; width: 100%; }
table.compra-perfis th, table.compra-perfis td { padding-left: .8mm; padding-right: .8mm; }
table.compra-perfis th { font-size: 6.2pt; letter-spacing: 0; padding-left: 1.4mm; padding-right: 1.4mm; }
table.compra-perfis td:first-child { overflow-wrap: anywhere; }
table.compra-perfis .cinza { font-size: 6.4pt; }
.legenda-compra { font-size: 7.2pt; color: var(--mudo); margin: .6mm 0 2.4mm; }
.legenda-compra span { display: inline-block; width: 3.4mm; height: 2.6mm; vertical-align: -.3mm; margin: 0 1.2mm 0 2.6mm; border-radius: .6mm; }
.legenda-compra span:first-child { margin-left: 0; }
@media screen { .trocar-perfil[data-perfil] { cursor: pointer; } }

/* ---------------- destaque de um número (área de pintura, área da obra) */
.cartao { background: var(--fundo); border-radius: 2.5mm; padding: 3mm 4mm; margin: 2.5mm 0; border-left: 3px solid var(--dest); break-inside: avoid; }
.cartao b.v { font: 300 13pt 'Segoe UI Light', 'Segoe UI', Arial; color: var(--pri); margin-right: 2mm; }
.cartao span { color: var(--mudo); font-size: 7.8pt; }
.cartao .rot { display: block; font: 600 6.6pt 'Segoe UI', Arial; letter-spacing: .13em; text-transform: uppercase; color: var(--mudo); margin-bottom: .4mm; }

/* ---------------- resumo de materiais: B. por grupo, em duas colunas com o quadrinho */
.colunas { column-count: 2; column-gap: 7mm; }
.fam { break-inside: avoid; margin: 0 0 3mm; }
.fam.longa { break-inside: auto; }                 /* a família comprida segue na outra coluna: não deixa a coluna vazia */
.fam .sub, .fam .comp { break-after: avoid; }
.fam h3 { margin: 0 0 .6mm; padding-bottom: .8mm; border-bottom: 1.2px solid var(--pri); }
.fam h3 small { margin-left: auto; font: 600 7pt 'Segoe UI', Arial; color: var(--mudo); letter-spacing: .06em; }
.fam .comp { font-size: 7.2pt; color: var(--mudo); margin: 0 0 .6mm; }
.fam .sub { font-size: 8pt; font-weight: 700; color: var(--pri); margin: 1.2mm 0 .2mm; }
.fam table { margin: 0; font-size: 8pt; }
.fam td { border: 0; border-bottom: 1px dotted #c9d1d6; padding: .5mm 1mm; }
.fam td.pecas-perfil { font-size: 6.8pt; color: var(--mudo); padding: 0 0 1.2mm 3mm; border: 0; line-height: 1.35; }
.fam td.q { width: 3.6mm; padding: 0; border: 0; }
.fam td.q::after { content: ""; display: block; width: 3.2mm; height: 3.2mm; margin: .5mm 0 0 .4mm; border: 1px solid var(--pri); border-radius: .6mm; }
.fam td.kg { text-align: right; white-space: nowrap; }
.fam td.m { text-align: right; white-space: nowrap; width: 16mm; color: var(--mudo); }
.fam .item { font-weight: 700; color: var(--pri); }
.fam .desc { font-size: 7.2pt; color: var(--mudo); font-weight: 400; }
.fam .loc { font-size: 7.2pt; color: var(--mudo); padding-left: 3mm; }
.fam .total-fam { font-weight: 700; color: var(--pri); font-size: 8pt; margin: .8mm 0 0; }

/* ---------------- o total (o bloco de investimento da proposta) */
.total-box { background: var(--pri); color: #fff; border-radius: 3mm; padding: 5mm 7mm 4.5mm; margin-top: 4mm; position: relative; overflow: hidden; break-inside: avoid; }
.total-box::before { content: ""; position: absolute; right: 7mm; top: 6mm; width: 11mm; height: 3.6mm; background: var(--dest); transform: skewX(-38deg); }
.total-box::after { content: ""; position: absolute; right: 20mm; top: 6mm; width: 11mm; height: 3.6mm; background: var(--dest); opacity: .5; transform: skewX(-38deg); }
.total-box small { font: 600 7.2pt 'Segoe UI', Arial; letter-spacing: .2em; text-transform: uppercase; color: var(--dest); }
.total-box .v { font: 300 24pt/1.1 'Segoe UI Light', 'Segoe UI', Arial; margin: 1.5mm 0 0; }
.total-box .ind { display: flex; flex-wrap: wrap; gap: 2mm 8mm; margin-top: 3.5mm; padding-top: 3mm; border-top: 1px solid rgba(255,255,255,.18);
                  font-size: 7.4pt; color: rgba(255,255,255,.7); }
.total-box .ind b { display: block; color: #fff; font-size: 10pt; font-weight: 600; }

/* ---------------- o dossiê (09/10): a foto da capa, os desenhos, a estrutura por tipo e os pavimentos */
figure { margin: 0; }
.capa { margin: 3.5mm 0 0; border-radius: 3mm; overflow: hidden; break-inside: avoid; }
.capa img { display: block; width: 100%; height: 78mm; object-fit: cover; }
figure.desenho { margin: 1mm 0 1.5mm; text-align: center; break-inside: avoid; }
figure.desenho svg { max-width: 100%; height: auto; }
figure figcaption { font-size: 7pt; color: var(--mudo); margin-top: .8mm; text-align: center; }
.legenda { display: flex; flex-wrap: wrap; gap: 1mm 4.5mm; font-size: 7.4pt; color: var(--texto); margin: 0 0 2mm; justify-content: center; }
.legenda i, h3.tipo i, .pecas-pav i { display: inline-block; width: 4mm; height: 2.2mm; border-radius: .5mm; margin-right: 1.4mm; vertical-align: -.2mm; }
.chip { display: inline-block; width: 3mm; height: 3mm; border-radius: .6mm; margin-right: 1.6mm; vertical-align: -.4mm; }
.cartoes { display: grid; grid-template-columns: repeat(auto-fit, minmax(34mm, 1fr)); gap: 2.4mm; margin: 2mm 0 2mm; break-inside: avoid; }
.cartoes div { background: var(--fundo); border-radius: 2mm; padding: 2mm 3mm; border-left: 2.4px solid var(--dest); }
.cartoes span { display: block; font: 600 6.4pt 'Segoe UI', Arial; letter-spacing: .12em; text-transform: uppercase; color: var(--mudo); }
.cartoes b { display: block; font: 300 12pt/1.2 'Segoe UI Light', 'Segoe UI', Arial; color: var(--pri); }
.cartoes em { display: block; font-style: normal; font-size: 7pt; color: var(--mudo); }
h3.tipo { margin: 5mm 0 1.6mm; padding-bottom: .9mm; border-bottom: 1.2px solid var(--pri); }
h3.tipo::before { display: none; }
h3.tipo i { width: 5mm; height: 3.2mm; }
h3.tipo small { margin-left: auto; font: 600 7.4pt 'Segoe UI', Arial; color: var(--mudo); letter-spacing: .04em; }
.bloco-tipo.lado { break-inside: avoid; }
.lado-a-lado { display: grid; grid-template-columns: 60mm 1fr; gap: 3.5mm; align-items: start; }
table.tipo { font-size: 7.4pt; }
table.tipo td.c, table.tipo td.r { white-space: nowrap; }
.foto-tipo img { display: block; width: 100%; border-radius: 2mm; border: 1px solid var(--linha); }
.bloco-tipo:not(.lado) .foto-tipo { max-width: 120mm; margin: 0 auto 2mm; }
table.tipo td { vertical-align: middle; }
.pav { break-inside: avoid; margin-bottom: 4mm; }
.pav-corpo { display: grid; grid-template-columns: 92mm 1fr; gap: 4mm; align-items: start; margin-top: 1.5mm; }
.pav figure.planta-pav svg { max-height: 70mm; width: auto; max-width: 100%; }
.foto-pav img { display: block; width: 100%; border-radius: 2mm; border: 1px solid var(--linha); }
.pecas-pav { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 1.2mm; font-size: 7.6pt; }
.pecas-pav li.t { font: 600 6.6pt 'Segoe UI', Arial; letter-spacing: .12em; text-transform: uppercase; color: var(--mudo); width: 100%; }
.pecas-pav b { color: var(--pri); margin-right: 1mm; }

/* ---------------- na tela (a prévia da página de materiais): a folha sobre o fundo */
@media screen {
  html { background: #e8ecef; }
  body { max-width: 210mm; margin: 6mm auto; background: #fff; padding: 10mm 11mm 12mm; border-radius: 2mm; box-shadow: 0 1px 4px rgba(20,28,33,.14); }
}
"""


def _doc(R: dict, titulo: str, corpo: str, paginado: bool = False) -> str:
    """O documento HTML; `paginado` traz o Paged.js, o cabeçalho e o rodapé correntes e o sinal de fim de
    paginação que a impressão em PDF (`saida.printpdf`) espera."""
    css = identidade.variaveis_css(R.get("marca")) + _CSS
    # o título da página no padrão de entrega ("OBRA - Resumo de materiais (dd.mm.aaaa)", 09/10): é o nome que o
    # navegador sugere no Imprimir › Salvar como PDF, e o título do PDF
    from saida.entrega import nome_de_entrega
    t_pag = nome_de_entrega((R.get("projeto") or {}).get("nome") or "", titulo)
    if paginado:
        from saida import printpdf
        return printpdf.envelope(_correntes(R, titulo) + corpo, css, _esc(t_pag))
    return ("<!DOCTYPE html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><title>%s</title><style>%s</style></head>"
            "<body>%s</body></html>" % (_esc(t_pag), css, corpo))


def _correntes(R: dict, titulo: str) -> str:
    """O logo no alto à esquerda, a referência à direita e o rodapé com a marca (o mesmo da proposta)."""
    marca = R.get("marca") or {}
    rev = (R.get("dados") or {}).get("revisao") or ""
    rod = " · ".join(_esc(x) for x in (marca.get("slogan") or marca.get("nome"), marca.get("site")) if x)
    return ("<div class=\"cabecalho\">%s</div><div class=\"cabref\">%s · <b>%s</b>%s</div><div class=\"rodape\">%s%s</div>"
            % (identidade.logo_ou_nome(marca), _esc(titulo), _esc(R["projeto"].get("nome") or ""), (" · " + _esc(rev)) if rev else "",
               ("<b>%s</b> · " % rod) if rod else "", "documento interno"))


def _cabecalho(R: dict, titulo: str) -> str:
    p, d = R["projeto"], R["dados"]
    marca = R.get("marca") or {}
    rev = d.get("revisao") or ""
    quando = d.get("data") or ""
    chip = " · ".join(x for x in (("Rev. %s" % rev) if rev else "", quando) if x)
    # a base é o modelo 3D do projeto (ajustado no programa depois do IFC: furação, suportes, chapas), não o IFC
    pe = ["base: <b>modelo 3D do projeto</b>" + ((" (IFC de origem %s)" % _esc(p["origem_ifc"])) if p.get("origem_ifc") else "")]
    if R.get("gerado"):
        pe.append("gerado em <b>%s</b>" % _esc(R["gerado"]))
    pe.append("documento interno")
    return ("<header class=\"faixa-topo\"><div class=\"topo\">%s%s</div><div class=\"marca\"><i></i><i></i></div>"
            "<div class=\"rotulo\">%s</div><h1>%s</h1>%s<div class=\"pe\">%s</div></header>"
            % (identidade.logo_ou_nome(marca, claro=True) or "<span></span>", ("<span class=\"rev\">%s</span>" % _esc(chip)) if chip else "",
               _esc(titulo), _esc(p.get("nome") or ""), ("<div class=\"desc\">%s</div>" % _esc(d["descricao"])) if d.get("descricao") else "",
               "".join("<span>%s</span>" % x for x in pe)))


def _h2(n, titulo: str, tag: str = "", classe_tag: str = "", parte: bool = False) -> str:
    """O título de seção da proposta: o número grande em verde-limão, o título e, à direita, a contagem."""
    return "<h2%s><span class=\"n\">%s</span>%s%s</h2>" % (
        " class=\"parte\"" if parte else "", ("%02d" % n) if isinstance(n, int) else _esc(n), _esc(titulo),
        ("<span class=\"tag%s\">%s</span>" % ((" " + classe_tag) if classe_tag else "", _esc(tag))) if tag else "")


def _ficha(itens) -> str:
    """Os cartões de números: (rótulo, valor, unidade, detalhe)."""
    cols = 3 if len(itens) in (3, 6, 9) else 4
    return "<div class=\"ficha\"%s>%s</div>" % ("" if cols == 4 else " style=\"grid-template-columns:repeat(%d,1fr)\"" % cols, "".join(
        "<div><span>%s</span><b>%s%s</b>%s</div>" % (_esc(r), _esc(v), ("<small>%s</small>" % _esc(u)) if u else "",
                                                    ("<em>%s</em>" % _esc(d)) if d else "")
        for r, v, u, d in itens))


def _foto(R: dict, nome: str) -> str:
    """A foto do dossiê como data URI (a prévia da tela é por http e não lê file:///; o PDF também a leva dentro)."""
    cam = ((R.get("dossie") or {}).get("fotos") or {}).get(nome)
    if not cam or not os.path.exists(cam):
        return ""
    import base64
    with open(cam, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")


def _m(mm: float) -> str:
    """mm → "6,85 m" (o 5 arredonda para cima: 2.195 → 2,20)."""
    return _n(math.floor(float(mm) / 10.0 + 0.5) / 100.0, 2) + " m"


def _blocos_de_estrutura(R: dict) -> List[dict]:
    """A estrutura por tipo do dossiê; sem ele (o resumo montado à mão nos testes), as tesouras do resumo."""
    X = R.get("dossie") or {}
    if X.get("estrutura"):
        return X["estrutura"]
    tes = [t for t in R.get("tesouras") or [] if t.get("qtd")]
    if not tes:
        return []
    return [{"chave": "tesouras", "titulo": "Tesouras" if R.get("cobertura", True) else "Vigas caixote", "cor": "#d9480f", "ids": [],
             "qtd": sum(t["qtd"] for t in tes),
             "m": sum(t["qtd"] * t["comprimento"] for t in tes) / 1000.0, "kg": sum(t["kg_total"] for t in tes),
             "linhas": [{"comprimento": t["comprimento"], "qtd": t["qtd"], "kg": t["kg_total"], "marcas": [t["tipo"]],
                         "perfis": [x for x in (t.get("banzos"), t.get("trelicamento")) if x], "onde": [], "ids": [],
                         "vao": t["vao"], "altura": t["altura"], "flecha": t["flecha"], "eixos": t.get("eixos", "")} for t in tes]}]


def _legenda(itens) -> str:
    return "<div class=\"legenda\">%s</div>" % "".join("<span><i style=\"background:%s\"></i>%s</span>" % (_esc(c), _esc(t)) for t, c in itens)


def _bloco_tipo(R: dict, b: dict, varios: bool) -> str:
    """Um tipo de estrutura: o título com a cor da planta, a foto do 3D com ele em destaque e a tabela por comprimento
    (cada linha abre o 3D com as peças dela, na tela)."""
    X = R.get("dossie") or {}
    tes = b["chave"] == "tesouras" and any("vao" in li for li in b["linhas"])
    if tes:
        colunas = [("Qtd", "c"), "Tipo", "Eixos", ("Vão", "r"), ("Comprimento", "r"), ("Altura*", "r"), "Banzos / treliçamento", ("kg", "r")]
        linhas = [[(li["qtd"], "c"), (", ".join(li["marcas"]), "b"), li.get("eixos") or "", ("%s m" % _n(li["vao"] / 1000.0, 2), "r"),
                   (_m(li["comprimento"]), "r"), ("%s m" % _n(li["altura"] / 1000.0, 2), "r"), " / ".join(li["perfis"]),
                   (_n(li["kg"], 1), "r")] for li in b["linhas"]]
        larg = ["7%", "8%", "15%", "10%", "12%", "9%", "28%", "11%"]
        rod = [("%d" % b["qtd"], "c"), ("TOTAL", "b"), "", "", "", "", "", (_n(b["kg"], 1), "r")]
    else:
        colunas = [("Qtd", "c"), ("Comprimento", "r"), ("Total", "r"), "Marca", "Perfil"] + (["Onde"] if varios else []) + [("kg", "r")]
        linhas = []
        for li in b["linhas"]:
            marcas = ", ".join(li["marcas"][:6]) + (" …" if len(li["marcas"]) > 6 else "")
            perfis = ", ".join(li["perfis"][:3]) + (" …" if len(li["perfis"]) > 3 else "")
            row = [("%d un" % li["qtd"], "c"), ("<b>%s</b>" % _esc(_m(li["comprimento"])), "r"),
                   ("%s m" % _n(li["qtd"] * li["comprimento"] / 1000.0, 1), "r"), _esc(marcas), "<span class=\"cinza\">%s</span>" % _esc(perfis)]
            if varios:
                row.append("<span class=\"cinza\">%s</span>" % _esc(" · ".join("%s %d" % (p, q) for p, q in li.get("onde") or [])))
            row.append((_n(li.get("kg") or 0.0, 1), "r"))
            linhas.append(row)
        larg = (["9%", "13%", "11%", "17%", "20%", "20%", "10%"] if varios else ["9%", "14%", "12%", "22%", "31%", "12%"])
        rod = [("%d un" % b["qtd"], "c"), "", ("%s m" % _n(b["m"], 1), "r"), ("TOTAL", "b"), ""] + ([""] if varios else []) + [(_n(b["kg"], 1), "r")]
    tabela = _tabela(colunas, linhas, rodape=rod, larguras=larg, bruto=True, classe="tipo",
                     ids_linhas=[",".join(li.get("ids") or []) for li in b["linhas"]])
    foto = _foto(R, "tipo-" + b["chave"])
    onde = (X.get("fotos_onde") or {}).get("tipo-" + b["chave"])
    fig = ("<figure class=\"foto-tipo\"><img src=\"%s\" alt=\"\"><figcaption>%s em destaque%s</figcaption></figure>"
           % (foto, _esc(b["titulo"]), (" · no %s (o mesmo nos outros pavimentos)" % _esc(onde)) if onde else "")) if foto else ""
    cab = ("<h3 class=\"tipo\"><i style=\"background:%s\"></i>%s<small>%d un · %s m · %s kg</small></h3>"
           % (_esc(b["cor"]), _esc(b["titulo"]), b["qtd"], _n(b["m"], 1), _n(b["kg"], 1)))
    nota = ""
    if tes:
        meias = [t for t in R.get("tesouras") or [] if t.get("meias", 0) >= 2]
        nota = "* do nível de apoio ao topo do banzo superior na cumeeira."
        if meias:
            dif = [t["tipo"] for t in meias if len(t.get("membros") or {}) > 1]
            nota = ("Fabricadas em 2 meias-tesouras emendadas na cumeeira%s. " % ((" (%s com as duas meias diferentes)" % " e ".join(dif)) if dif else "")) + nota
        if (R.get("dados") or {}).get("notas_tesouras"):
            nota += " " + R["dados"]["notas_tesouras"]
        nota = "<p class=\"nota\">%s</p>" % _esc(nota)
    if fig and len(b["linhas"]) <= 7:
        return "<section class=\"bloco-tipo lado\">%s<div class=\"lado-a-lado\">%s<div>%s%s</div></div></section>" % (cab, fig, tabela, nota)
    return "<section class=\"bloco-tipo\">%s%s%s%s</section>" % (cab, fig, tabela, nota)


def html_resumo_obra(R: dict, paginado: bool = False) -> str:
    """O resumo da obra como o dossiê dela (09/10): a foto, os números, a obra desenhada (implantação com eixos e cotas,
    ou o corte com os pavimentos), a estrutura por tipo com a foto de cada um, a ficha de cada pavimento e, no fim, os
    pesos, as telhas, os parafusos e as pendências."""
    n, dim = R["numeros"], R["dimensoes"]
    X = R.get("dossie") or {}
    varios = bool(X.get("varios"))
    blocos = _blocos_de_estrutura(R)
    tem_tesouras = any(b["chave"] == "tesouras" for b in blocos)
    partes = [_cabecalho(R, "RESUMO DA OBRA")]
    capa = _foto(R, "capa")
    if capa:
        partes.append("<figure class=\"capa\"><img src=\"%s\" alt=\"\"></figure>" % capa)
    # os números numa olhada (nos cartões da proposta)
    q = []
    if varios:
        pavs = X.get("pavimentos") or []
        andares = sum(p["repete"] for p in pavs)
        q.append(("Pavimentos", "%d" % len(pavs), "", "%d andares com aço (%s)" % (andares, ", ".join(
            "%s ×%d" % (p["nome"], p["repete"]) if p["repete"] > 1 else p["nome"] for p in pavs))))
    elif tem_tesouras and n.get("tesouras"):
        q.append(("Tesouras", "%d" % n["tesouras"], "", ("inclinação %s%% (%s°)" % (_n(100 * math.tan(math.radians(n["inclinacao"])), 0), _n(n["inclinacao"], 1)))
                  if n.get("inclinacao") else ""))
    q.append(("Estrutura metálica", _n(n["peso_aco"], 1), "kg", ("%s kg/m² de projeção" % _n(n["kg_m2"], 1)) if (n.get("kg_m2") and not varios) else ""))
    if n.get("ml_telhas"):
        q.append(("Telhas", _n(n.get("m2_telhas") or 0.0, 2), "m²", "%s ml · %s kg" % (_n(n["ml_telhas"], 2), _n(n["peso_telhas"], 1))))
        q.append(("Total geral", _n(n["total"], 1), "kg", "aço + telhas%s" % (" + rufos" if n.get("peso_funilaria") else "")))
    principais = [b for b in blocos if b["chave"] not in ("suportes", "travamentos")]
    if principais:
        q.append(("Peças principais", "%d" % sum(b["qtd"] for b in principais), "un",
                  " · ".join("%d %s" % (b["qtd"], b["titulo"].lower()) for b in principais[:3])))
    q.append(("Parafusos", "%d" % n["parafusos"], "", "e as porcas e arruelas soltas: ver Parafusos"))
    q.append(("Área de pintura", _n(n.get("m2_pintura") or 0.0, 1), "m²", "perfis pelo perímetro da seção, chapas nas duas faces"))
    if R.get("maior") and R["maior"].get("nome"):
        q.append(("Maior peça · transporte", _n(R["maior"]["comprimento"] / 1000.0, 2), "m", "%s · %s" % (R["maior"]["nome"], R["maior"]["perfil"])))
    if R.get("mais_pesada") and R["mais_pesada"].get("nome"):
        q.append(("Mais pesada · içamento", _n(R["mais_pesada"]["kg"], 1), "kg", "%s (%s)" % (R["mais_pesada"]["nome"], R["mais_pesada"]["tipo"])))
    partes.append(_ficha(q))
    sec = 0
    # ---- a obra desenhada
    svgs = X.get("svg") or {}
    if varios:
        sec += 1
        partes.append(_h2(sec, "A obra em corte", "%d pavimentos" % len(X.get("pavimentos") or [])))
        if svgs.get("corte"):
            partes.append("<figure class=\"desenho\">%s</figure>" % svgs["corte"])
            partes.append("<p class=\"nota\">Corte esquemático: o aço projetado na direção mais comprida do prédio, na cor do "
                          "pavimento; os pilares de concreto em cinza. À direita, cada pavimento com as cotas e quantas vezes se repete.</p>")
        linhas = []
        for p in X.get("pavimentos") or []:
            resumo_p = " · ".join("%d %s" % (pp["qtd"], pp["titulo"].lower()) for pp in p.get("papeis") or [] if pp["chave"] != "suportes")
            linhas.append(["<span class=\"chip\" style=\"background:%s\"></span><b>%s</b>" % (_esc(p["cor"]), _esc(p["nome"])),
                           "%s a %s" % (_nivel(p["z0"]), _nivel(p["z1"])), ("×%d" % p["repete"], "c"), _esc(resumo_p),
                           (_n(p["kg"] / max(1, p["repete"]), 1), "r"), (_n(p["kg"], 1), "r")])
        partes.append(_tabela(["Pavimento", "Cotas", ("Repete", "c"), "Peças (total)", ("kg por andar", "r"), ("kg total", "r")], linhas,
                              larguras=["16%", "17%", "8%", "37%", "11%", "11%"], bruto=True,
                              ids_linhas=[",".join(p.get("ids") or []) for p in X.get("pavimentos") or []]))
    else:
        sec += 1
        partes.append(_h2(sec, "Implantação", ("eixos %s" % _eixos_rotulo(X.get("eixos"))) if X.get("eixos") else ""))
        if svgs.get("implantacao"):
            partes.append("<figure class=\"desenho\">%s</figure>" % svgs["implantacao"])
            partes.append(_legenda(X.get("legenda") or []))
        # o que o desenho não mostra, em cartões
        c = []
        if dim.get("n_tesouras", 0) > 1 and not X.get("eixos"):
            c.append(("Comprimento entre tesouras", "%s m" % _n(dim["comprimento_total"] / 1000.0, 2), "%s a %s" % (dim["eixos"].split()[0], dim["eixos"].split()[-1])))
        vaos = sorted({round(tr["vao"]) for tr in dim.get("trechos") or [] if tr.get("vao")}, reverse=True)
        if vaos:
            c.append(("Vão entre apoios", " · ".join("%s m" % _n(v / 1000.0, 2) for v in vaos), "das tesouras"))
        if dim.get("projecao"):
            c.append(("Projeção com beirais", "%s × %s m" % (_n(dim["projecao"][0] / 1000.0, 2), _n(dim["projecao"][1] / 1000.0, 2)),
                      "área %s m²" % _n(dim.get("area_m2") or 0.0, 2)))
        if dim.get("nivel_apoio") is not None:
            c.append(("Nível de apoio", "%s%s m" % ("+" if dim["nivel_apoio"] >= 0 else "", _n(dim["nivel_apoio"] / 1000.0, 3)),
                      "face de cima da chapa de apoio" if dim.get("apoio_por_chapa") else "ponto mais baixo das tesouras"))
        if n.get("inclinacao"):
            c.append(("Inclinação", "%s%%" % _n(100 * math.tan(math.radians(n["inclinacao"])), 0), "%s°" % _n(n["inclinacao"], 1)))
        if c:
            partes.append("<div class=\"cartoes\">%s</div>" % "".join(
                "<div><span>%s</span><b>%s</b><em>%s</em></div>" % (_esc(a), _esc(b), _esc(d)) for a, b, d in c))
        trechos = [tr for tr in dim.get("trechos") or [] if tr.get("nome")]
        if len(trechos) > 1:
            linhas = []
            for tr in trechos:
                if tr.get("transicao"):
                    linhas.append(["Transição (%s)" % tr["eixos_transicao"], ("%s m" % _n(tr["transicao"] / 1000.0, 2), "r"), ""])
                linhas.append(["<b>%s</b> (%s)" % (_esc(tr["nome"]), _esc(tr["eixos"])), ("vão %s m" % _n(tr["vao"] / 1000.0, 2), "r"),
                               "projeção %s × %s m" % (_n(tr["projecao"][0] / 1000.0, 2), _n(tr["projecao"][1] / 1000.0, 2))])
            partes.append("<h3>Trechos da cobertura</h3>" + _tabela(["Trecho", ("Medida", "r"), "Observação"], linhas, bruto=True,
                                                                    larguras=["40%", "20%", "40%"]))
    # ---- a estrutura por tipo
    if blocos:
        sec += 1
        partes.append(_h2(sec, "Estrutura por tipo", "%d tipos" % len(blocos)))
        partes.append("<p class=\"explica\">Cada tipo pelo papel na obra, com as peças por comprimento (sem separar perfil nem "
                      "espessura); a marca é a das pranchas.%s</p>" % (" Na tela, clicar na linha abre o 3D com as peças dela." if not paginado else ""))
        for b in blocos:
            partes.append(_bloco_tipo(R, b, varios))
        tc = R.get("tercas") or {}
        if X.get("tem_cobertura", tem_tesouras) and tc.get("linhas"):
            partes.append("<h3>Linhas de terças por trecho</h3>" + _tabela(
                ["Trecho", ("Linhas na cobertura", "r"), ("Linhas nas saias", "r"), ("Total de linhas", "r")],
                [[l["trecho"] + " (%s)" % l["eixos"], ("%d (%s por água)" % (l["cobertura"], "/".join(str(v) for v in sorted(l["por_agua"].values(), reverse=True)) or "0"), "r"),
                  ("%d (%s por lado)" % (l["saias"], "/".join(str(v) for v in sorted(l["por_lado"].values(), reverse=True)) or "0"), "r"), (l["total"], "r")]
                 for l in tc["linhas"]]))
            if tc.get("furos"):
                partes.append("<p class=\"nota\">Furos das terças: %s.</p>" % _esc(tc["furos"]))
    # ---- a ficha de cada pavimento
    if varios:
        sec += 1
        partes.append(_h2(sec, "Pavimentos", "planta e foto de cada um", parte=False))
        for k, p in enumerate(X.get("pavimentos") or []):
            foto = _foto(R, "pav-%d" % k)
            lista_p = "".join("<li><i style=\"background:%s\"></i><b>%s</b> %s</li>" % (
                _esc(pp["cor"]), _esc(pp["titulo"]), _esc(" · ".join("%d × %s" % (li["qtd"] // max(1, p["repete"]) if p["repete"] > 1 and li["qtd"] % p["repete"] == 0 else li["qtd"], _m(li["comprimento"]))
                                                                for li in pp["linhas"][:6])))
                for pp in p.get("papeis") or [])
            por = " (por andar)" if p["repete"] > 1 else ""
            partes.append(
                "<section class=\"pav\"><h3 class=\"tipo\"><i style=\"background:%s\"></i>%s%s<small>%s a %s · %s kg%s</small></h3>"
                "<figure class=\"desenho planta-pav\">%s<figcaption>Planta%s</figcaption></figure>"
                "<div class=\"pav-corpo\">%s<ul class=\"pecas-pav\"><li class=\"t\">Peças%s</li>%s</ul></div></section>"
                % (_esc(p["cor"]), _esc(p["nome"]), (" ×%d" % p["repete"]) if p["repete"] > 1 else "", _nivel(p["z0"]), _nivel(p["z1"]),
                   _n(p["kg"], 1), (" (%s por andar)" % _n(p["kg"] / p["repete"], 1)) if p["repete"] > 1 else "",
                   p.get("svg") or "", " de um andar" if p["repete"] > 1 else "",
                   ("<figure class=\"foto-pav\"><img src=\"%s\" alt=\"\"><figcaption>O aço do pavimento na cor do tipo; o concreto em cinza</figcaption></figure>" % foto) if foto else "",
                   por, lista_p))
    # ---- pesos: pelo tipo de estrutura (o mesmo do dossiê) e o resto do aço
    sec += 1
    if blocos and X.get("estrutura"):
        linhas = [["<span class=\"chip\" style=\"background:%s\"></span>%s" % (_esc(b["cor"]), _esc(b["titulo"])), (_n(b["kg"], 1), "r"),
                   (_n(100.0 * b["kg"] / n["peso_aco"], 1) + "%" if n["peso_aco"] else "", "r")] for b in blocos]
        resto = n["peso_aco"] - sum(b["kg"] for b in blocos)
        if resto > 0.5:
            linhas.append(["Chapas soltas, chumbadores e o mais", (_n(resto, 1), "r"), (_n(100.0 * resto / n["peso_aco"], 1) + "%", "r")])
    else:
        linhas = [[_esc(g["grupo"]), (_n(g["kg"], 1), "r"), (_n(g["pct"], 1) + "%", "r")] for g in R["grupos_peso"]]
    linhas.append([("TOTAL ESTRUTURA METÁLICA", "b"), (_n(n["peso_aco"], 1), "r"), ("100%", "r")])
    if n.get("ml_telhas"):
        linhas.append(["Telhas (%s ml)" % _n(n["ml_telhas"], 2), (_n(n["peso_telhas"], 1), "r"), ""])
    if n.get("peso_funilaria"):
        linhas.append(["Rufos e calhas", (_n(n["peso_funilaria"], 1), "r"), ""])
    if n.get("ml_telhas") or n.get("peso_funilaria"):
        linhas.append([("TOTAL GERAL (AÇO + TELHAS%s)" % (" + RUFOS" if n.get("peso_funilaria") else ""), "b"), (_n(n["total"], 1), "r"), ""])
    partes.append(_h2(sec, "Pesos", "%s kg de aço" % _n(n["peso_aco"], 1)) + _tabela(["Grupo", ("Peso (kg)", "r"), ("%", "r")], linhas,
                                                                                    larguras=["70%", "18%", "12%"], bruto=True))
    partes.append("<p class=\"nota\">Pesos teóricos: perfis formados a frio pela NBR 6355 (tira desenvolvida com o desconto das dobras), "
                  "laminados, tubos e barras pelas tabelas do catálogo, chapas pelo retângulo envolvente; o conjunto com as chapas dele. "
                  "Não inclui solda, pintura, parafusos das telhas, rufos e calhas.</p>")
    # ---- telhas (só a obra com telha)
    T = R.get("telhas") or {}
    if T.get("ml_total"):
        sec += 1
        partes.append(_h2(sec, "Telhas", "%s ml" % _n(T["ml_total"], 2)))
        desc = T.get("descricao")
        rot_trecho = {"cobertura": "cobertura", "fechamento": "fechamentos (oitões e paredes)", "forro": "forro do beiral"}
        linhas = []
        for trecho, itens in T["trechos"].items():
            soltos = [it for it in itens if it["ml"] >= 20.0 or it["qtd"] >= 10] if len(itens) > 6 else list(itens)
            miudos = [it for it in itens if it not in soltos]
            for it in soltos:
                texto = "%s - %s%s" % (it.get("descricao") or desc or ("Telha %s" % it["perfil"]), rot_trecho[trecho],
                                       " - multidobra" if it["codigo"] == "MD" else (" - cumeeira" if it["codigo"] == "CU" else "")) \
                    + (" - cortada na largura" if it["cortada"] else "")
                linhas.append([it["codigo_n"], texto, (it["qtd"], "c"), (_n(it["comprimento"] / 1000.0, 2), "r"), (_n(it["ml"], 2), "r"),
                               (_n(it.get("m2") or 0.0, 2), "r"), (_n(it["kg"], 1), "r")])
            if miudos:
                codigos = [it["codigo_n"] for it in miudos]
                texto = "%s - %s (%d comprimentos: %s a %s - ver relação de telhas)" % (
                    miudos[0].get("descricao") or desc or ("Telha %s" % miudos[0]["perfil"]), rot_trecho[trecho], len(miudos), codigos[0], codigos[-1])
                linhas.append(["%d tipos" % len(miudos), texto, (sum(it["qtd"] for it in miudos), "c"), ("vários", "r"),
                               (_n(sum(it["ml"] for it in miudos), 2), "r"), (_n(sum(it.get("m2") or 0.0 for it in miudos), 2), "r"),
                               (_n(sum(it["kg"] for it in miudos), 1), "r")])
        sub = " + ".join("%s %s ml" % (rot_trecho[k], _n(v, 2)) for k, v in T["ml_por_trecho"].items())
        partes.append(_tabela(["Tipo", "Descrição", ("Qtd", "c"), ("Comp. (m)", "r"), ("Total (ml)", "r"), ("m²", "r"), ("kg", "r")], linhas,
                              rodape=[("TOTAL", "b"), sub, "", "", (_n(T["ml_total"], 2), "r"), (_n(T.get("m2_total") or 0.0, 2), "r"),
                                      (_n(T["kg_total"], 1), "r")],
                              larguras=["10%", "47%", "6%", "9%", "10%", "9%", "9%"]))
        partes.append("<p class=\"nota\">m² pela largura útil (%s m).</p>" % _n(T["largura_util"] / 1000.0, 2))
    # ---- parafusos
    P = R["parafusos"]
    sec += 1
    partes.append(_h2(sec, "Parafusos e fixadores", "%d parafusos" % n["parafusos"]))
    linhas = []
    for it in P:
        primeiro = True
        for loc in it["locais"]:
            pecas = ", ".join(loc["pecas"][:24]) + (" …" if len(loc["pecas"]) > 24 else "")
            linhas.append([(it["nome"], "b") if primeiro else "", it["descricao"] if primeiro else "", (it["qtd"], "c") if primeiro else "",
                           "%s<br><span class=\"pecas\">%s</span>" % (_esc(loc["local"]), _esc(pecas)), (loc["qtd"], "r")])
            primeiro = False
    partes.append(_tabela(["Parafuso / fixador", "Descrição comercial", ("Qtd", "c"), "Local de uso", ("Qtd no local", "r")], linhas,
                          rodape=[("TOTAL DE PARAFUSOS", "b"), "", (n["parafusos"], "c"), "", ""], larguras=["12%", "22%", "6%", "52%", "8%"], bruto=True))
    partes.append("<p class=\"nota\">Quantidades conforme o modelo 3D.</p>")
    # ---- pendências de conferência
    pend = R.get("pendencias")
    if pend is None:
        pend = [{"peca": "", "perfil": "", "o_que": a} for a in _avisos_que_contam(R.get("avisos") or [])]
    sec += 1
    # as respostas do usuário às pendências (a aba Conferência, 13/10): a resolvida sai da conta de "a conferir"
    conf = R.get("conferencias") or {}
    resp = [conf.get(x.get("chave") or "") or {} for x in pend]
    abertas = sum(1 for r in resp if r.get("situacao") != "resolvida")
    resumo_pend = ("%d a conferir" % abertas + (" · %d resolvida(s)" % (len(pend) - abertas) if len(pend) - abertas else "")) if pend else "nenhuma pendência"
    partes.append(_h2(sec, "Pendências de conferência", resumo_pend, "atencao" if abertas else "ok"))
    if pend:
        if any(r for r in resp):
            linhas = [[x["peca"], x["perfil"], x["o_que"], _resposta_texto(r)] for x, r in zip(pend, resp)]
            partes.append(_tabela(["Peça", "Perfil", "O que conferir", "Resposta"], linhas, larguras=["14%", "18%", "40%", "28%"], bruto=True,
                                  ids_linhas=[",".join(x.get("ids") or []) for x in pend],
                                  classes_linhas=[("resolvida" if r.get("situacao") == "resolvida" else "") for r in resp]))
        else:
            partes.append(_tabela(["Peça", "Perfil", "O que conferir"], [[x["peca"], x["perfil"], x["o_que"]] for x in pend],
                                  larguras=["18%", "22%", "60%"], ids_linhas=[",".join(x.get("ids") or []) for x in pend]))
    return _doc(R, "Resumo da obra", "".join(partes), paginado)


SITUACOES_CONFERENCIA = {"aberta": "em aberto", "respondida": "respondida", "resolvida": "resolvida"}


def _resposta_texto(r: dict) -> str:
    """A célula da resposta: a situação, a data e o texto do usuário."""
    if not r:
        return ""
    sit = SITUACOES_CONFERENCIA.get(r.get("situacao") or "", "")
    quando = str(r.get("quando") or "")[:16].replace("T", " ")
    cab = " · ".join(x for x in (sit, quando) if x)
    return "<b>%s</b>%s" % (_esc(cab), ("<br>" + _esc(r.get("resposta") or "")) if r.get("resposta") else "")


def _nivel(z: float) -> str:
    return ("+" if z >= 0 else "") + _n(z / 1000.0, 2)


def _eixos_rotulo(eixos: Optional[dict]) -> str:
    nums = [x["nome"] for x in (eixos or {}).get("numeros") or []]
    lets = [x["nome"] for x in (eixos or {}).get("letras") or []]
    partes = []
    if nums:
        partes.append("%s a %s" % (nums[0], nums[-1]) if len(nums) > 1 else nums[0])
    if lets:
        partes.append("%s a %s" % (lets[0], lets[-1]) if len(lets) > 1 else lets[0])
    return " × ".join(partes)


def html_resumo_materiais(R: dict, paginado: bool = False) -> str:
    n, dim = R["numeros"], R["dimensoes"]
    partes = [_cabecalho(R, "RESUMO DE MATERIAIS")]
    # os números da compra e da obra numa olhada, nos cartões da proposta (08/10)
    C = R.get("compra") or {}
    q = [("Estrutura metálica", _n(n["peso_aco"], 1), "kg", "perfis %s + chaparia %s kg" % (_n(R["perfis_kg"], 1), _n(R["chaparia_total"]["kg"], 1)))]
    if dim["trechos"]:
        # só o total (o usuário, 09/10: a conta de cada ala enchia o cartão; o detalhe fica no resumo da obra)
        q.append(("Área de projeção", _n(dim["area_m2"], 2), "m²", "com beirais"))
    if C.get("perfis"):
        q.append(("Compra de perfis", _n(sum(p.get("kg_compra") or 0.0 for p in C["perfis"]), 1), "kg",
                  _barras_e_sob_medida(sum(p["barras"] for p in C["perfis"]), sum(p.get("sob_medida_pecas") or 0 for p in C["perfis"]),
                                       "barras comerciais")))
    if C.get("chapas"):
        cl, ca = C["chapa_comercial"]
        q.append(("Chapas comerciais", "%d" % sum(c["chapas"] for c in C["chapas"]), "",
                  "%s x %s m · %s%% de perda" % (_n(cl / 1000.0, 2), _n(ca / 1000.0, 2), _n(C["perda_chapas"], 0))))
    q.append(("Telhas", _n(n["ml_telhas"], 2), "ml", "%s m² · %s kg" % (_n(n.get("m2_telhas") or 0.0, 2), _n(n["peso_telhas"], 1))))
    q.append(("Parafusos", "%d" % n["parafusos"], "", ""))
    q.append(("Área de pintura", _n(n.get("m2_pintura") or 0.0, 1), "m²", ""))
    if n.get("kg_m2"):
        q.append(("Consumo de aço", _n(n["kg_m2"], 1), "kg/m²", "de projeção"))
    partes.append(_ficha(q))
    partes.append(_html_compra(R))
    partes.append(_h2("B", "Por grupo", "conferência da fábrica", parte=True))
    partes.append("<p class=\"explica\">Pesos teóricos (kg) e comprimento total (m) por perfil - mesmos números da lista de materiais. "
                  "Chapas somadas por espessura na chaparia. Quadrinho à direita para conferência.</p>")
    blocos = []

    def linhas_perfis(perfis):
        # embaixo de cada perfil, as peças dele: nome, quantidade e comprimento (06/10)
        def pecas(pf):
            itens = " · ".join("%s %dx %s" % (x["nome"], x["qtd"], _n(x["comprimento"])) for x in pf.get("lista") or [])
            return ("<tr><td colspan=\"4\" class=\"pecas-perfil\">%s <span class=\"cinza\">(mm)</span></td></tr>" % _esc(itens)) if itens else ""
        return "".join("<tr><td>%s</td><td class=\"kg\">%s kg</td><td class=\"m\">%s m</td><td class=\"q\"></td></tr>%s"
                       % (_esc(pf["perfil"]), _n(pf["kg"], 2), _n(pf["m"], 2), pecas(pf)) for pf in perfis)
    for f in R["familias"]:
        h = "<div class=\"fam\"><h3>%s<small>%02dx</small></h3>" % (_esc(f["titulo"]), f["n"])
        if f.get("composicao"):
            h += "<p class=\"comp\">%s</p>" % _esc(f["composicao"])
        if f.get("nota"):
            h += "<p class=\"comp\">%s</p>" % _esc(f["nota"])
        for s in f["sub"]:
            h += "<p class=\"sub\">%s</p><table>%s</table>" % (_esc(s["titulo"]), linhas_perfis(s["perfis"]))
        if f["perfis"]:
            h += "<table>%s</table>" % linhas_perfis(f["perfis"])
        h += "</div>"
        if h.count("<tr>") > 14:
            h = h.replace("<div class=\"fam\">", "<div class=\"fam longa\">", 1)
        blocos.append(h)
    # chaparia
    ch = R["chaparia"]
    h = "<div class=\"fam\"><h3>Chaparia<small>todas as chapas</small></h3><table>"
    for c in ch:
        mat = (" (%s)" % c["material"]) if c.get("material") and len({x.get("material") for x in ch}) > 1 else ""
        mat += (" — modelo %s" % c["modelo"]) if c.get("modelo") else ""
        h += "<tr><td>%s</td><td class=\"kg\">%s kg</td><td class=\"m\">%d pç / %s m²</td><td class=\"q\"></td></tr>" % (_esc(c["rotulo"] + mat), _n(c["kg"], 2), c["pecas"], _n(c["m2"], 2))
    h += "<tr><td class=\"item\">Total chaparia</td><td class=\"kg item\">%s kg</td><td class=\"m item\">%d pç</td><td class=\"q\"></td></tr></table></div>" % (_n(R["chaparia_total"]["kg"], 2), R["chaparia_total"]["pecas"])
    blocos.append(h)
    # parafusos
    h = "<div class=\"fam\"><h3>Parafusos e fixadores<small>%d</small></h3><table>" % n["parafusos"]
    for it in R["parafusos"]:
        h += "<tr><td class=\"item\">%s<br><span class=\"desc\">%s</span></td><td class=\"kg\">%dx</td><td class=\"q\"></td></tr>" % (_esc(it["nome"]), _esc(it["descricao"]), it["qtd"])
        for loc in it["locais"]:
            h += "<tr><td class=\"loc\">%s</td><td class=\"kg cinza\">%dx</td><td></td></tr>" % (_esc(loc["local"]), loc["qtd"])
    h += "</table></div>"
    if h.count("<tr>") > 14:
        h = h.replace("<div class=\"fam\">", "<div class=\"fam longa\">", 1)
    blocos.append(h)
    # telhas
    T = R["telhas"]
    h = "<div class=\"fam\"><h3>Telhas<small>%s ml</small></h3>" % _n(T["ml_total"], 2)
    rot_trecho = {"cobertura": "Cobertura", "fechamento": "Fechamento dos oitões e paredes", "forro": "Forro do beiral"}
    for trecho, itens in T["trechos"].items():
        descs = " / ".join(dict.fromkeys(it.get("descricao") or "Telha" for it in itens))
        h += "<p class=\"sub\">%s</p><p class=\"comp\">%s (largura útil %s m)</p><table>" % (_esc(rot_trecho[trecho]), _esc(descs), _n(T["largura_util"] / 1000.0, 2))
        for it in itens:
            h += "<tr><td>%02d pçs c/. %s m</td><td class=\"m\">%s%s</td><td class=\"q\"></td></tr>" % (
                it["qtd"], _n(it["comprimento"] / 1000.0, 2), _esc(it["codigo_n"]), " (cortada na largura)" if it["cortada"] else "")
        h += "</table><p class=\"total-fam\">Total: %s ml</p>" % _n(T["ml_por_trecho"][trecho], 2)
    h += "<p class=\"total-fam\">Total telhas = %s ml (%s kg)</p></div>" % (_n(T["ml_total"], 2), _n(T["kg_total"], 1))
    blocos.append(h)
    partes.append("<div class=\"colunas\">%s</div>" % "".join(blocos))
    # o total, no bloco do investimento da proposta (largura toda, depois das colunas)
    ind = [("perfis e barras", "%s kg" % _n(R["perfis_kg"], 2)), ("chaparia", "%s kg" % _n(R["chaparia_total"]["kg"], 2)),
           ("telhas", "%s ml / %s m² (%s kg)" % (_n(n["ml_telhas"], 2), _n(n.get("m2_telhas") or 0.0, 2), _n(n["peso_telhas"], 1)))]
    if n.get("peso_funilaria"):
        ind.append(("rufos e calhas", "%s kg" % _n(n["peso_funilaria"], 1)))
    ind += [("total geral c/ telhas", "%s kg" % _n(n["total"], 2)), ("aço por m²", "%s kg/m²" % (_n(n["kg_m2"], 1) if n.get("kg_m2") else "—")),
            ("pintura", "%s m²" % _n(n.get("m2_pintura") or 0.0, 1))]
    partes.append("<div class=\"total-box\"><small>Total estrutura metálica</small><div class=\"v\">%s kg</div><div class=\"ind\">%s</div></div>"
                  % (_n(n["peso_aco"], 2), "".join("<span><b>%s</b>%s</span>" % (_esc(v), _esc(r)) for r, v in ind)))
    return _doc(R, "Resumo de materiais", "".join(partes), paginado)


_LEGENDA_COMPRA = ("<p class=\"legenda-compra\"><span style=\"background:#fff4d6\">&nbsp;</span>similar do catálogo no lugar do "
                   "perfil do projeto <span style=\"background:#fde4e1\">&nbsp;</span>fora do catálogo e sem similar "
                   "<span style=\"background:#e3edff\">&nbsp;</span>trocado à mão</p>")


def _classe_compra(p: dict) -> str:
    """A cor da linha do perfil na compra: o que não é o perfil do projeto direto do catálogo (06/10)."""
    if p.get("escolhido"):
        return "compra-escolhido"
    if p.get("similar"):
        return "compra-similar"
    if p.get("fora_do_catalogo"):
        return "compra-fora"
    return ""


def _html_compra(R: dict) -> str:
    """A. Compra (05/10): perfis em barras comerciais (W em 12 m, o resto em 6 m; a terça e o dobrado maior que 6 m sob
    medida, 13/10), chapas de 1,20 × 3,00 com a perda, parafusos, porcas e arruelas por bitola, telhas e a área de pintura.
    Com a coluna "pedido" em branco para o comprador."""
    C = R.get("compra") or {}
    if not C:
        return ""
    h = [_h2("A", "Compra", "coluna Pedido para o comprador", parte=True)]
    if C.get("perfis"):
        h.append("<h3>Perfis e barras</h3><p class=\"explica\">Um por tipo de perfil, cruzado com o catálogo; barras comerciais pelo plano "
                 "de corte da lista; W em 12 m; tubos, redondos e laminados em polegada em 6 m (a peça maior sai com emenda); "
                 "dobrados em 6 m; terças e dobrados maiores que 6 m sob medida (no comprimento da peça, sem sobra).</p>")

        def nome_perfil(p):
            # o nome do catálogo em cima, o do IFC embaixo (06/10); fora do catálogo, o do IFC e de onde veio o kg/m
            cat = p.get("catalogo") or ""
            if cat and p.get("escolhido"):
                cima, baixo = cat, "escolhido no lugar do IFC: %s" % p["perfil"]
            elif cat and p.get("similar"):
                cima, baixo = cat, "similar ao IFC: %s" % p["perfil"]
            elif cat:
                cima, baixo = cat, ("IFC: %s" % p["perfil"]) if _mesmo_nome(cat) != _mesmo_nome(p["perfil"]) else ""
            else:
                cima, baixo = p["perfil"], ("fora do catálogo e sem similar (kg/m pelas medidas)" if p.get("fora_do_catalogo") else "")
            # a tela da lista põe o clique no nome (trocar pelo parecido do catálogo); no PDF é só o texto
            return "<b class=\"trocar-perfil\" data-perfil=\"%s\">%s</b>%s" % (
                _esc(p.get("ifc") or p["perfil"]), _esc(cima), ("<br><span class=\"cinza\">%s</span>" % _esc(baixo)) if baixo else "")
        # o kg das peças (o que vai na obra) e o de compra em dois blocos lado a lado (o usuário, 09/10): COM
        # aproveitamento (o plano de corte: peças diferentes na mesma barra, as sobras usadas, a emenda na peça maior que
        # a barra) e SEM (cada posição só das barras dela) — barras × kg/barra = kg em cada um; quase sempre vale o menor
        # na ordem do usuário (09/10): o projeto, depois SEM aproveitamento e COM; só o total de barras (as emendas
        # ficam no plano de corte da lista); a letra menor e o nome do IFC só quando difere do catálogo — o quadro passava
        # da largura da folha no PDF
        tot_com = sum(p.get("kg_compra") or 0.0 for p in C["perfis"])
        tot_sem = sum(p.get("kg_sem_aproveitamento") or 0.0 for p in C["perfis"])
        sob_tot = {"sob_medida_pecas": sum(p.get("sob_medida_pecas") or 0 for p in C["perfis"])}
        h.append(_tabela(["Perfil", "Material", ("Peças", "r ap-proj"), ("m", "r ap-proj"), ("kg/m", "r ap-proj"), ("kg peças", "r ap-proj"),
                          ("Barra", "r"),
                          ("Barras", "r ap-sem"), ("kg/barra", "r ap-sem"), ("kg", "r ap-sem"),
                          ("Barras", "r ap-com"), ("kg/barra", "r ap-com"), ("kg", "r ap-com"), ("Aprov.", "r"), "Pedido"],
                         [[nome_perfil(p), p["material"], (p.get("pecas") or "", "r"), (_n(p["m"], 2), "r"),
                           (_n(p.get("kg_m") or 0.0, 2), "r"), (_n(p["kg"], 1), "r"), ("%s m" % _n(p["barra_m"], 0), "r"),
                           (_celula_barras(p.get("barras_sem_aproveitamento") or 0, p), "r ap-sem"), (_n(p.get("kg_barra") or 0.0, 1), "r ap-sem"),
                           ("<b>%s</b>" % _n(p.get("kg_sem_aproveitamento") or 0.0, 1), "r ap-sem"),
                           (_celula_barras(p["barras"], p), "r ap-com"), (_n(p.get("kg_barra") or 0.0, 1), "r ap-com"),
                           ("<b>%s</b>" % _n(p.get("kg_compra") or 0.0, 1), "r ap-com"),
                           ("%s%%" % _n(p["aproveitamento"], 0) if p["aproveitamento"] is not None else "", "r"), ""] for p in C["perfis"]],
                         rodape=[("TOTAL", "b"), "", (sum(p.get("pecas") or 0 for p in C["perfis"]), "r"),
                                 (_n(sum(p["m"] for p in C["perfis"]), 2), "r"), "", (_n(sum(p["kg"] for p in C["perfis"]), 1), "r"), "",
                                 (_celula_barras(sum(p.get("barras_sem_aproveitamento") or 0 for p in C["perfis"]), sob_tot), "r ap-sem"), ("", "ap-sem"),
                                 (_n(tot_sem, 1), "r ap-sem"),
                                 (_celula_barras(sum(p["barras"] for p in C["perfis"]), sob_tot), "r ap-com"), ("", "ap-com"),
                                 (_n(tot_com, 1), "r ap-com"), "", ""],
                         larguras=["16%", "6%", "5%", "7%", "5%", "7%", "5%", "5%", "6%", "7%", "5%", "6%", "7%", "6%", "7%"], bruto=True,
                         classe="compra-perfis", classes_linhas=[_classe_compra(p) for p in C["perfis"]],
                         grupos=[("", 2, ""), ("Projeto", 4, "ap-proj"), ("", 1, ""), ("Sem aproveitamento", 3, "ap-sem"),
                                 ("Com aproveitamento", 3, "ap-com"), ("", 2, "")]))
        if tot_com and tot_sem:
            h.append("<p class=\"legenda-compra\"><span class=\"ap-sem\">&nbsp;&nbsp;</span> sem aproveitamento: cada posição "
                     "só das barras dela (a sobra não serve a outra peça) &nbsp; <span class=\"ap-com\">&nbsp;&nbsp;</span> com "
                     "aproveitamento: as peças diferentes na mesma barra e as sobras usadas (emenda na peça maior que a barra). "
                     "Diferença: %s kg (%s%%) a menos com aproveitamento.</p>"
                     % (_n(tot_sem - tot_com, 1), _n(100.0 * (tot_sem - tot_com) / tot_sem, 1)))
        if any(_classe_compra(p) for p in C["perfis"]):
            h.append(_LEGENDA_COMPRA)
    if C.get("outros_aco"):
        h.append("<h3>Gradis, pisos e outras peças de aço</h3><p class=\"explica\">O que o IFC traz fora das peças de perfil e chapa; "
                 "o comprimento é a maior extensão de cada peça, somada.</p>")
        h.append(_tabela(["Item", "Família", ("Peças", "r"), ("ml", "r"), ("m²", "r"), "Pedido"],
                         [[(x["item"], "b"), x["familia"], (x["pecas"], "r"), (_n(x["ml"], 2), "r"),
                           (_n(x["m2"], 2) if x["m2"] else "", "r"), ""] for x in C["outros_aco"]],
                         larguras=["30%", "20%", "10%", "12%", "12%", "16%"]))
        h.append("<p class=\"legenda-compra\">Sem o peso: a malha do IFC não serve para pesar o gradil (barra maciça no lugar de tubo, "
                 "chapa perfurada sem os furos) — conferir as seções com o projeto ou o fornecedor.%s</p>"
                 % ("".join(" %s: %d peça(s) com a malha aberta." % (x["item"], x["abertas"]) for x in C["outros_aco"] if x["abertas"])))
    if C.get("chapas"):
        cl, ca = C["chapa_comercial"]
        h.append("<h3>Chapas</h3><p class=\"explica\">Pela espessura comercial: a do modelo ou a próxima acima, e o peso nela; chapa de %s x %s m; "
                 "a quantidade pela área com %s%% de perda no corte.</p>"
                 % (_n(cl / 1000.0, 2), _n(ca / 1000.0, 2), _n(C["perda_chapas"], 0)))
        h.append(_tabela(["Bitola", "Espessura", "Polegada", "No modelo", "Material", ("Peças", "r"), ("m²", "r"), ("kg", "r"),
                          ("Chapas", "r"), "Pedido"],
                         [[(c.get("bitola") or "—", "b"), (c.get("mm") or c["rotulo"], "b"), (c.get("polegada") or "—", "b"),
                           c.get("modelo") or "", c.get("material") or "", (c["pecas"], "r"), (_n(c["m2"], 2), "r"), (_n(c["kg"], 1), "r"),
                           (c["chapas"], "r"), ""] for c in C["chapas"]],
                         rodape=[("TOTAL", "b"), "", "", "", "", (sum(c["pecas"] for c in C["chapas"]), "r"),
                                 (_n(sum(c["m2"] for c in C["chapas"]), 2), "r"), (_n(sum(c["kg"] for c in C["chapas"]), 1), "r"),
                                 (sum(c["chapas"] for c in C["chapas"]), "r"), ""],
                         larguras=["7%", "10%", "8%", "17%", "14%", "7%", "9%", "10%", "8%", "10%"],
                         classes_linhas=["compra-similar" if c.get("modelo") else "" for c in C["chapas"]]))
        if any(c.get("modelo") for c in C["chapas"]):
            h.append("<p class=\"legenda-compra\"><span style=\"background:#fff4d6\">&nbsp;</span>a chapa do modelo não é "
                     "comercial: compra na espessura padrão acima</p>")
    if C.get("parafusos") or C.get("porcas") or C.get("arruelas"):
        h.append("<h3>Parafusos, porcas e arruelas</h3><p class=\"explica\">Cada parafuso com 1 porca e 1 arruela; as soltas — pontas roscadas, "
                 "chumbadores — somadas na bitola.</p>")
        linhas = [[pf["nome"], pf["descricao"].split(" + ")[0], (pf["qtd"], "r"), ""] for pf in C.get("parafusos") or []]
        linhas += [["Porca %s" % b, "Porca sextavada Ø%s" % b, (q, "r"), ""] for b, q in C.get("porcas") or []]
        linhas += [["Arruela %s" % b, "Arruela lisa Ø%s" % b, (q, "r"), ""] for b, q in C.get("arruelas") or []]
        linhas += [["Químico %s" % q["nome"], "Químico de injeção %s, cartucho %d ml — %s furos, ~%s ml com %d%% de perda"
                    % (q["nome"], q["cartucho_ml"], _n(q["furos"], 0), _n(q["ml_total"], 0), round(PERDA_QUIMICO * 100)), (q["cartuchos"], "r"), ""]
                   for q in C.get("quimicos") or []]
        # a linha do parafuso leva os ids dele: na tela, o clique mostra onde estão no 3D (porcas, arruelas e químico não)
        ids = [",".join(pf.get("ids") or []) for pf in C.get("parafusos") or []]
        h.append(_tabela(["Item", "Descrição", ("Qtd", "r"), "Pedido"], linhas, larguras=["20%", "52%", "12%", "16%"],
                         ids_linhas=ids + [""] * (len(linhas) - len(ids))))
    if C.get("telhas"):
        h.append("<h3>Telhas</h3><p class=\"explica\">m² pela largura útil.</p>")
        h.append(_tabela(["Telha", ("Peças", "r"), ("ml", "r"), ("m²", "r"), ("kg", "r"), "Pedido"],
                         [[x["descricao"], (x["pecas"], "r"), (_n(x["ml"], 2), "r"), (_n(x["m2"], 2), "r"), (_n(x["kg"], 1), "r"), ""] for x in C["telhas"]],
                         larguras=["36%", "10%", "13%", "13%", "13%", "15%"]))
    pt = R.get("pintura") or {}
    if pt:
        h.append("<div class=\"cartao\"><span class=\"rot\">Área de pintura</span><b class=\"v\">%s m²</b><span>perfis e barras %s m² (perímetro da seção × comprimento) + chapas %s m² "
                 "(as duas faces)%s</span></div>" % (_n(pt["total_m2"], 1), _n(pt["total_m2"] - pt["chapas_m2"], 1), _n(pt["chapas_m2"], 1),
                                             ("; sem a seção no catálogo: %s" % ", ".join(pt["sem_secao"])) if pt.get("sem_secao") else ""))
    return "".join(h)


def _tabela(colunas, linhas, rodape=None, larguras=None, bruto=False, classe=None, classes_linhas=None, ids_linhas=None,
            grupos=None) -> str:
    """`grupos`: uma linha de títulos por cima do cabeçalho, [(texto, colunas que cobre, classe)] (os dois blocos da compra
    de perfis, com e sem aproveitamento, 09/10)."""
    def cel(c, tag="td"):
        cls = ""
        if isinstance(c, tuple):
            c, cls = c
        v = c if bruto and isinstance(c, str) and "<" in c else _esc(c)
        if cls == "b":
            v, cls = "<b>%s</b>" % v, ""
        return "<%s%s>%s</%s>" % (tag, (" class=\"%s\"" % cls) if cls else "", v, tag)
    cols = ("<colgroup>%s</colgroup>" % "".join("<col style=\"width:%s\">" % w for w in larguras)) if larguras else ""
    th = "".join(cel(c, "th") for c in colunas)
    cl, il = list(classes_linhas or []), list(ids_linhas or [])
    corpo = "".join("<tr%s%s>%s</tr>" % ((" class=\"%s\"" % cl[i]) if i < len(cl) and cl[i] else "",
                                         (" data-ids=\"%s\"" % html.escape(il[i])) if i < len(il) and il[i] else "",
                                         "".join(cel(c) for c in l))
                    for i, l in enumerate(linhas))
    pe = ("<tr class=\"total\">%s</tr>" % "".join(cel(c) for c in rodape)) if rodape else ""
    # a tabela curta não se parte entre páginas (o cabeçalho ficava sozinho no pé da página, 08/10)
    classe = " ".join(x for x in (classe, "inteira" if len(linhas) <= 8 else "") if x)
    topo = ("<tr class=\"grupos\">%s</tr>" % "".join(
        "<th%s%s>%s</th>" % ((" colspan=\"%d\"" % n) if n > 1 else "", (" class=\"%s\"" % c) if c else "", _esc(t))
        for t, n, c in grupos)) if grupos else ""
    return "<table%s>%s<thead>%s<tr>%s</tr></thead><tbody>%s%s</tbody></table>" % (
        (" class=\"%s\"" % classe) if classe else "", cols, topo, th, corpo, pe)


# ============================================================ planilha (Excel)
def planilha_de_materiais(R: dict, lista: Optional[dict], caminho: str) -> str:
    """O resumo de materiais em Excel (o usuário, 09/10): os números dos cartões, a compra de perfis (projeto, sem e com
    aproveitamento), as chapas, os parafusos e chumbadores (com porcas, arruelas e o químico), a lista de materiais por
    posição e os conjuntos — os mesmos números do PDF, para filtrar, somar e mandar ao comprador."""
    from saida import xlsx_simples
    n, dim, C = R["numeros"], R["dimensoes"], R.get("compra") or {}

    def r1(x, c=1):
        return round(float(x or 0.0), c)
    perfis = C.get("perfis") or []
    kg_com = sum(p.get("kg_compra") or 0.0 for p in perfis)
    kg_sem = sum(p.get("kg_sem_aproveitamento") or 0.0 for p in perfis)
    sob = sum(p.get("sob_medida_pecas") or 0 for p in perfis)
    resumo = [["Item", "Valor", "Unidade", "Observação"],
              ["Estrutura metálica", r1(n["peso_aco"]), "kg", "perfis + chaparia"],
              ["Perfis (peso teórico)", r1(R.get("perfis_kg")), "kg", ""],
              ["Chaparia (peso teórico)", r1((R.get("chaparia_total") or {}).get("kg")), "kg", ""]]
    if dim.get("trechos"):
        resumo.append(["Área de projeção", r1(dim["area_m2"], 2), "m²", "com beirais"])
    if perfis:
        resumo += [["Compra de perfis sem aproveitamento", r1(kg_sem), "kg",
                    _barras_e_sob_medida(sum(p.get("barras_sem_aproveitamento") or 0 for p in perfis), sob)],
                   ["Compra de perfis com aproveitamento", r1(kg_com), "kg", _barras_e_sob_medida(sum(p["barras"] for p in perfis), sob)]]
    if C.get("chapas"):
        cl, ca = C["chapa_comercial"]
        resumo.append(["Chapas comerciais", sum(c["chapas"] for c in C["chapas"]), "pç",
                       "%s x %s m, %s%% de perda" % (_n(cl / 1000.0, 2), _n(ca / 1000.0, 2), _n(C["perda_chapas"], 0))])
    resumo += [["Telhas", r1(n.get("ml_telhas"), 2), "ml", "%s m²" % _n(n.get("m2_telhas") or 0.0, 2)],
               ["Parafusos e chumbadores", int(n.get("parafusos") or 0), "pç", ""],
               ["Área de pintura", r1(n.get("m2_pintura")), "m²", ""]]
    if n.get("kg_m2"):
        resumo.append(["Consumo de aço", r1(n["kg_m2"]), "kg/m²", "de projeção"])
    abas = [{"nome": "Resumo", "linhas": resumo, "larguras": [38, 14, 9, 36]}]
    if perfis:
        cab = ["Perfil", "Perfil no IFC", "Material", "Peças", "m", "kg/m", "kg peças", "Barra (m)", "Sob medida – peças", "Sob medida – m",
               "Sem aprov. – barras", "Sem aprov. – kg/barra", "Sem aprov. – kg",
               "Com aprov. – barras", "Com aprov. – kg/barra", "Com aprov. – kg", "Aproveitamento (%)", "Pedido"]
        linhas = [cab] + [[p.get("catalogo") or p["perfil"], p.get("ifc") or p["perfil"], p.get("material") or "", int(p.get("pecas") or 0),
                           r1(p["m"], 2), r1(p.get("kg_m"), 2), r1(p["kg"]), int(round(p["barra_m"])),
                           int(p.get("sob_medida_pecas") or 0), r1(p.get("sob_medida_m"), 2),
                           int(p.get("barras_sem_aproveitamento") or 0), r1(p.get("kg_barra")), r1(p.get("kg_sem_aproveitamento")),
                           int(p["barras"]), r1(p.get("kg_barra")), r1(p.get("kg_compra")),
                           int(round(p["aproveitamento"])) if p.get("aproveitamento") is not None else None, ""] for p in perfis]
        linhas.append(["TOTAL", "", "", sum(int(p.get("pecas") or 0) for p in perfis), r1(sum(p["m"] for p in perfis), 2), None,
                       r1(sum(p["kg"] for p in perfis)), None, sob, r1(sum(p.get("sob_medida_m") or 0.0 for p in perfis), 2),
                       sum(int(p.get("barras_sem_aproveitamento") or 0) for p in perfis), None,
                       r1(kg_sem), sum(int(p["barras"]) for p in perfis), None, r1(kg_com), None, ""])
        abas.append({"nome": "Perfis e barras", "linhas": linhas, "total": True,
                     "larguras": [22, 22, 8, 8, 10, 8, 11, 8, 10, 10, 10, 10, 11, 10, 10, 11, 10, 10]})
    if C.get("chapas"):
        linhas = [["Bitola", "Espessura", "Polegada", "No modelo", "Material", "Peças", "m²", "kg", "Chapas", "Pedido"]]
        linhas += [[c.get("bitola") or "", c.get("mm") or c.get("rotulo") or "", c.get("polegada") or "", c.get("modelo") or "",
                    c.get("material") or "", int(c["pecas"]), r1(c["m2"], 2), r1(c["kg"]), int(c["chapas"]), ""] for c in C["chapas"]]
        linhas.append(["TOTAL", "", "", "", "", sum(int(c["pecas"]) for c in C["chapas"]), r1(sum(c["m2"] for c in C["chapas"]), 2),
                       r1(sum(c["kg"] for c in C["chapas"])), sum(int(c["chapas"]) for c in C["chapas"]), ""])
        abas.append({"nome": "Chapas", "linhas": linhas, "total": True, "larguras": [8, 11, 9, 16, 12, 8, 9, 10, 8, 10]})
    fix = [["Item", "Descrição", "Qtd", "Pedido"]]
    fix += [[pf["nome"], pf["descricao"], int(pf["qtd"]), ""] for pf in C.get("parafusos") or []]
    fix += [["Porca %s" % b, "Porca sextavada Ø%s" % b, int(q), ""] for b, q in C.get("porcas") or []]
    fix += [["Arruela %s" % b, "Arruela lisa Ø%s" % b, int(q), ""] for b, q in C.get("arruelas") or []]
    fix += [["Químico %s" % q["nome"], "Químico de injeção %s, cartucho %d ml (%s furos, ~%s ml com %d%% de perda)"
             % (q["nome"], q["cartucho_ml"], _n(q["furos"], 0), _n(q["ml_total"], 0), round(PERDA_QUIMICO * 100)), int(q["cartuchos"]), ""]
            for q in C.get("quimicos") or []]
    if len(fix) > 1:
        abas.append({"nome": "Parafusos e chumbadores", "linhas": fix, "larguras": [34, 80, 9, 10]})
    if lista and lista.get("posicoes"):
        cab = ["Posição", "Nome", "Categoria", "Classe", "Perfil", "Material", "Qtd", "Comprimento (mm)", "Largura (mm)",
               "Espessura (mm)", "Peso unit. (kg)", "Peso total (kg)", "Furos", "Conjuntos", "Observações"]
        pos = lista["posicoes"]
        linhas = [cab] + [[li.get("marca"), li.get("nome") or "", li.get("categoria") or "", li.get("classe") or "",
                           li.get("perfil_nome") or li.get("perfil") or "", li.get("material") or "", int(li.get("quantidade") or 0),
                           li.get("comprimento") or None, li.get("largura") or None, li.get("espessura") or None,
                           r1(li.get("peso"), 2), r1(li.get("peso_total"), 2), li.get("furos") or "",
                           ", ".join(li.get("conjuntos") or []), "; ".join(li.get("observacoes") or [])] for li in pos]
        linhas.append(["TOTAL", "", "", "", "", "", sum(int(li.get("quantidade") or 0) for li in pos), None, None, None, None,
                       r1(sum(float(li.get("peso_total") or 0.0) for li in pos), 2), "", "", ""])
        abas.append({"nome": "Lista de materiais", "linhas": linhas, "total": True,
                     "larguras": [22, 10, 12, 14, 22, 9, 7, 11, 10, 10, 10, 11, 14, 30, 30]})
    if lista and lista.get("conjuntos"):
        linhas = [["Conjunto", "Nome", "Categoria", "Quantidade", "Peças por unidade", "Composição", "Peso unit. (kg)", "Peso total (kg)"]]
        linhas += [[c.get("marca"), c.get("nome") or "", c.get("titulo_categoria") or c.get("categoria") or "", int(c.get("instancias") or 0),
                    int(c.get("pecas_unidade") or 0), c.get("composicao_texto") or "", r1(c.get("peso_unitario"), 2),
                    r1(c.get("peso_total"), 2)] for c in lista["conjuntos"]]
        abas.append({"nome": "Conjuntos", "linhas": linhas, "larguras": [30, 10, 12, 10, 10, 60, 12, 12]})
    return xlsx_simples.escrever(caminho, abas)


# ============================================================ gravação
#: Os números do último resumo gerado, lidos pelo resumo de orçamento.
ARQ_NUMEROS = "resumo-numeros.json"


def gerar_resumos(pasta: str, R: dict, imprimir_pdf: bool = True) -> dict:
    """Grava resumo-da-obra.html/.pdf e resumo-de-materiais.html/.pdf em `pasta`."""
    from projetos import trocar_arquivo
    os.makedirs(pasta, exist_ok=True)
    saida = {}
    # os números principais (área, dimensões, pesos) para o resumo de orçamento (saida/orcamento.py)
    try:
        import json
        with open(os.path.join(pasta, ARQ_NUMEROS), "w", encoding="utf-8") as f:
            json.dump({"numeros": R.get("numeros"), "dimensoes": R.get("dimensoes"),
                       # as pendências de conferência, para a aba Conferência responder (13/10)
                       "pendencias": R.get("pendencias") or []}, f, ensure_ascii=False, default=str)
    except (OSError, TypeError, ValueError):
        pass
    for chave, titulo, fn in (("obra", "resumo-da-obra", html_resumo_obra), ("materiais", "resumo-de-materiais", html_resumo_materiais)):
        h = fn(R)
        caminho = os.path.join(pasta, titulo + ".html")
        with open(caminho + ".parcial", "w", encoding="utf-8") as f:
            f.write(h)
        trocar_arquivo(caminho + ".parcial", caminho)
        saida[chave] = {"html": caminho}
        if imprimir_pdf:
            from saida import printpdf
            pdf = os.path.join(pasta, titulo + ".pdf")
            paginado = os.path.join(pasta, titulo + ".paginado.html")
            try:
                with open(paginado, "w", encoding="utf-8") as f:
                    f.write(fn(R, paginado=True))
                printpdf.imprimir(paginado, pdf, verbose=False, timeout=300)
                saida[chave]["pdf"] = pdf
            except Exception as exc:                   # noqa: BLE001 — sem navegador, fica o HTML
                saida[chave]["erro_pdf"] = str(exc)
            finally:
                try:
                    os.remove(paginado)
                except OSError:
                    pass
        if chave == "materiais":
            # a planilha do resumo de materiais (09/10), com a lista de materiais da mesma pasta
            try:
                import json as _json
                cam_l = os.path.join(pasta, "lista-de-materiais.json")
                lista = _json.load(open(cam_l, encoding="utf-8")) if os.path.exists(cam_l) else None
                saida[chave]["xlsx"] = planilha_de_materiais(R, lista, os.path.join(pasta, titulo + ".xlsx"))
            except Exception as exc:                   # noqa: BLE001 — a planilha não segura os PDFs
                saida[chave]["erro_xlsx"] = str(exc)
    return saida
