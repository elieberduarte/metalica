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
import html
import math
import os
import re
from typing import Dict, List, Optional, Tuple

from nucleo3d.modelo import Documento, Solido
from nucleo2d.detalhe.base import (_marcas, marcas_de, _autovetores, _eixos_dos_fixadores, _fixadores, _parede_da_peca, _so_parafusos,
                                   _eixo_da_peca)
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


def descricao_parafuso(nome: str) -> Tuple[str, str, Optional[float]]:
    """"M12 x 35" → ("Parafuso M12x35", 'Parafuso sextavado Ø1/2" x 1.1/2" ASTM A307 + porca e arruela', 12)."""
    m = re.match(r"M(\d+(?:[.,]\d+)?)\s*x\s*(\d+)", nome or "", re.I)
    if not m:
        return nome, nome, None
    d = float(m.group(1).replace(",", "."))
    L = int(m.group(2))
    pol = _POLEGADA.get(int(round(d)), "M%g" % d)
    lpol = _COMPRIMENTO_POL.get(L) or _COMPRIMENTO_POL.get(min(_COMPRIMENTO_POL, key=lambda k: abs(k - L)))
    classe = "A325" if (d >= 16 and L >= 50) else "A307"
    return ("Parafuso M%gx%d" % (d, L), "Parafuso sextavado Ø%s x %s ASTM %s + porca e arruela" % (pol, lpol, classe), d)


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

    familias: List[dict] = []
    for chave, titulo in FAMILIAS.items():
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
    parafusos = _parafusos_com_local(fixadores, pecas, tipos, nomes_pos, tipos_conj, nomes_conj, conj_info)
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
            grupos_peso.append({"grupo": titulo, "kg": kg})
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
    maior, pesada = _maior_e_mais_pesada(lista, tipos_tes)
    import time as _time
    return {
        "gerado": _time.strftime("%d/%m/%Y %H:%M"), "pendencias": pendencias, "pintura": pintura, "compra": compra,
        "maior": maior, "mais_pesada": pesada,
        "projeto": identificacao, "dados": dados,
        "numeros": {"tesouras": sum(t["qtd"] for t in tipos_tes), "peso_aco": peso_aco, "ml_telhas": ml_telhas,
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


def _parafusos_com_local(fixadores, pecas, tipos, nomes_pos, tipos_conj, nomes_conj, conj_info) -> List[dict]:
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
    from nucleo2d.detalhe.base import pontas_roscadas, PORCAS_POR_PONTA, ARRUELAS_POR_PONTA
    pontas, usados = pontas_roscadas(pecas, fixadores)
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
            chave = "M%g x %s" % (d, m.group(2))
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
        lr = r["locais"].setdefault(local[0], {"qtd": 0, "pecas": set(), "ids": []})
        lr["qtd"] += 1
        lr["pecas"].update(local[1])
        lr["ids"].append(f.id)                              # para "ver no 3D" a pendência (06/10)
    for pt in pontas:
        fam = familia_peca(pt["peca"])
        local = rotulos.get(fam[0], fam[0])
        for chave, q in (("Porca %s" % (pt["bitola"] or "?"), PORCAS_POR_PONTA), ("Arruela %s" % (pt["bitola"] or "?"), ARRUELAS_POR_PONTA)):
            r = contagem.setdefault(chave, {"parafuso": False, "qtd": 0, "locais": collections.OrderedDict(), "d": pt["d"]})
            r["qtd"] += q
            lr = r["locais"].setdefault(local, {"qtd": 0, "pecas": set(), "ids": []})
            lr["qtd"] += q
            lr["pecas"].add(fam[1])
    saida = []
    for chave, r in contagem.items():
        if r["parafuso"]:
            nome, desc, _d = descricao_parafuso(chave.replace(" ", ""))
        else:
            nome = chave
            desc = ("Arruela lisa Ø%s" if chave.startswith("Arruela") else "Porca sextavada Ø%s UNC") % chave.split(" ", 1)[1]
        locais = sorted(r["locais"].items(), key=lambda kv: -kv[1]["qtd"])
        saida.append({"nome": nome, "descricao": desc, "qtd": r["qtd"], "parafuso": r["parafuso"], "d": r["d"],
                      "locais": [{"local": k, "qtd": v["qtd"], "pecas": sorted(v["pecas"], key=_ordem_natural), "ids": v.get("ids") or []}
                                 for k, v in locais]})
    saida.sort(key=lambda x: (not x["parafuso"], x["d"] or 0, _ordem_natural(x["nome"])))
    return saida


def descricao_telha(perfil: str, dados_telha: str = "") -> str:
    """A descrição comercial de uma telha pelo perfil dela ("TELHA TP40 0.65MM" → "Telha TP40 0,65 mm"). A dos dados do
    resumo vale quando é a mesma espessura (ela é uma só para a obra: a multi-dobra de 0,65 saía como 0,50, 05/10); o
    "Telha TELHA" repetido sai."""
    base = re.sub(r"(?i)^\s*telha\s+", "", str(perfil or "")).strip()
    m = re.search(r"(\d+[.,]\d+)\s*MM", base, re.I)
    esp = m.group(1).replace(".", ",") if m else ""
    d = re.sub(r"(?i)^\s*telha\s+telha\b", "Telha", str(dados_telha or "").strip())
    d = re.sub(r"(\d+)[.,](\d+)\s*MM\b", r"\1,\2 mm", d, flags=re.I)
    if d and (not esp or esp.replace(",", ".") in d.replace(",", ".")):
        return d
    nome = re.sub(r"\s*\d+[.,]\d+\s*MM", "", base, flags=re.I).strip()
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
    return saida


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
    return _POLEGADA.get(int(round(float(d or 0))), "M%g" % float(d or 0))


def _compra(lista: dict, parafusos: List[dict], telhas: dict, dados: dict) -> dict:
    """A parte de compra do resumo de materiais: perfis em barras comerciais (o plano de corte da lista: W em 12 m, o
    resto em 6 m), chapas em chapas comerciais de 1,20 × 3,00 (pela área, com a perda), parafusos, porcas e arruelas
    separados e somados por bitola, telhas por perfil em ml e m²."""
    perfis = []
    for g in lista.get("perfis") or []:
        b = g.get("barras") or {}
        perfis.append({"perfil": com_bitola(g.get("perfil") or ""), "material": g.get("material") or "", "kg": float(g.get("peso") or 0.0),
                       "pecas": int(g.get("pecas") or 0), "kg_m": float(g.get("kg_m") or 0.0), "catalogo": g.get("catalogo") or "",
                       "fora_do_catalogo": g.get("fonte_kg_m") == "calculado", "similar": g.get("fonte_kg_m") == "similar",
                       "escolhido": g.get("fonte_kg_m") == "escolhido", "ifc": g.get("perfil") or "",
                       "m": float(g.get("comprimento_m") or 0.0), "barra_m": float(b.get("comprimento") or 0.0) / 1000.0,
                       "barras": int(b.get("quantidade") or 0), "aproveitamento": b.get("aproveitamento"), "emendas": int(b.get("emendas") or 0)})
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
    pf, porcas, arruelas = [], collections.Counter(), collections.Counter()
    for it in parafusos:
        if it["parafuso"]:
            pf.append({"nome": it["nome"], "descricao": it["descricao"], "qtd": it["qtd"]})
            porcas[_bitola_pol(it.get("d"))] += it["qtd"]
            arruelas[_bitola_pol(it.get("d"))] += it["qtd"]
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
    return {"perfis": perfis, "chapas": chapas, "perda_chapas": perda, "chapa_comercial": CHAPA_COMERCIAL,
            "parafusos": pf, "porcas": sorted(porcas.items(), key=lambda kv: ordem_b(kv[0])),
            "arruelas": sorted(arruelas.items(), key=lambda kv: ordem_b(kv[0])), "telhas": list(telhas_p.values())}


def _maior_e_mais_pesada(lista: dict, tipos_tes: List[dict]):
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
    cands += [("tesoura %s" % tt["tipo"], float(tt.get("kg_un") or 0.0), "montada") for tt in tipos_tes]
    nome, kg, tipo = max(cands, key=lambda c: c[1], default=("", 0.0, ""))
    return m, {"nome": nome, "kg": kg, "tipo": tipo}


# ============================================================ HTML
_CSS = """
@page { size: A4; margin: 14mm 12mm 14mm 12mm; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 9pt; color: #1b1b1b; line-height: 1.32; margin: 0; }
h1 { font-size: 15pt; color: #0b3d91; margin: 0 0 1mm; }
.sub { font-size: 9pt; margin: 0; }
.sub b { font-size: 9.5pt; }
.cinza { color: #555; font-size: 8pt; }
.numeros { border: 1.5px solid #0b3d91; padding: 2mm 3mm; margin: 3mm 0; background: #f4f7fc; font-size: 9.5pt; }
h2 { font-size: 11pt; color: #0b3d91; margin: 4.5mm 0 1.5mm; border-bottom: 1px solid #9fb3d6; padding-bottom: 0.6mm; break-after: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 8.4pt; margin: 1mm 0 1.5mm; }
tr { break-inside: avoid; }
th, td { border: 1px solid #b9c2d0; padding: 1mm 1.6mm; vertical-align: top; text-align: left; }
th { background: #e8eef8; font-weight: bold; }
td.r, th.r { text-align: right; }
td.r { white-space: nowrap; }
table.tes { font-size: 7.8pt; }
table.tes td, table.tes th { padding: 0.8mm 1.2mm; }
td.c, th.c { text-align: center; }
tr.total td { font-weight: bold; background: #f0f3f8; }
.nota { font-size: 8pt; color: #333; margin: 0.5mm 0 1.5mm; }
.mono { font-family: Consolas, monospace; font-size: 8pt; }
.pecas { color: #555; font-size: 7.8pt; }
/* resumo de materiais: duas colunas */
.colunas { column-count: 2; column-gap: 7mm; }
.fam { break-inside: avoid; margin: 0 0 2.4mm; }
.fam h3 { font-size: 9.6pt; margin: 0 0 0.4mm; border-bottom: 1px solid #333; padding-bottom: 0.2mm; }
.fam .comp { font-size: 7.6pt; color: #555; font-style: italic; margin: 0 0 0.6mm; }
.fam td.pecas-perfil { font-size: 7pt; color: #555; padding: 0 0 1.2mm 3mm; border: 0; line-height: 1.35; }
@media screen { .trocar-perfil[data-perfil] { cursor: pointer; } }
/* a compra diferente do projeto, para a conferência (06/10): similar âmbar, fora do catálogo vermelho, escolhido azul */
tr.compra-similar td { background: #fff4d6; } tr.compra-similar td b, tr.compra-similar .cinza { color: #7a4f00; }
tr.compra-fora td { background: #fde4e1; } tr.compra-fora td b, tr.compra-fora .cinza { color: #9b1c1c; }
tr.compra-escolhido td { background: #e3edff; } tr.compra-escolhido td b, tr.compra-escolhido .cinza { color: #0b3d91; }
.legenda-compra { font-size: 7.6pt; color: #555; margin: 0.8mm 0 2.5mm; }
.legenda-compra span { display: inline-block; padding: 0 1.6mm; margin-right: 2.5mm; border-radius: 0.6mm; }
* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.fam .sub { font-size: 8.8pt; font-weight: bold; margin: 0.8mm 0 0.2mm; }
.fam table { margin: 0; font-size: 8.4pt; }
.fam td { border: 0; border-bottom: 1px dotted #ccc; padding: 0.4mm 1mm; }
.fam td.q { width: 4mm; border: 1px solid #333; padding: 0; }
.fam td.kg { text-align: right; white-space: nowrap; }
.fam td.m { text-align: right; white-space: nowrap; width: 16mm; }
.fam .item { font-weight: bold; }
.fam .desc { font-size: 7.6pt; color: #444; font-style: italic; }
.fam .loc { font-size: 7.6pt; color: #333; padding-left: 3mm; }
.total-box { border: 1.5px solid #333; padding: 2mm; margin-top: 3mm; break-inside: avoid; }
table.quadro { border: 1.5px solid #0b3d91; background: #f4f7fc; margin: 3mm 0; }
table.quadro td { border: 0; border-bottom: 1px solid #d5deec; padding: 1mm 2mm; }
table.quadro td.v { font-weight: bold; text-align: right; white-space: nowrap; }
table.quadro td.d { color: #555; font-size: 7.8pt; }
h2.parte { font-size: 12pt; border-bottom: 2px solid #0b3d91; }
"""


def _doc(titulo: str, corpo: str, paginado: bool = False) -> str:
    """O documento HTML; `paginado` traz o Paged.js e o sinal de fim de paginação que a
    impressão em PDF (`saida.printpdf`) espera."""
    if paginado:
        from saida import printpdf
        return printpdf.envelope(corpo, _CSS, titulo)
    return ("<!DOCTYPE html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><title>%s</title><style>%s</style></head>"
            "<body>%s</body></html>" % (_esc(titulo), _CSS, corpo))


def _cabecalho(R: dict, titulo: str) -> str:
    p, d = R["projeto"], R["dados"]
    rev = d.get("revisao") or ""
    quando = d.get("data") or ""
    # a base é o modelo 3D do projeto (ajustado no programa depois do IFC: furação, suportes, chapas), não o IFC
    base = "base: modelo 3D do projeto" + ((" (IFC de origem %s)" % p.get("origem_ifc")) if p.get("origem_ifc") else "")
    linha2 = " - ".join(x for x in (d.get("descricao") or "", ("revisão %s" % rev) if rev else "", quando, base,
                                   ("gerado em %s" % R["gerado"]) if R.get("gerado") else "") if x)
    return ("<h1>%s</h1><p class=\"sub\"><b>%s</b></p><p class=\"cinza\">%s</p>"
            % (_esc(titulo), _esc(p.get("nome") or ""), _esc(linha2)))


def html_resumo_obra(R: dict, paginado: bool = False) -> str:
    n, dim = R["numeros"], R["dimensoes"]
    partes = [_cabecalho(R, "RESUMO DA OBRA")]
    # o quadro de números (05/10): o que a gerência pergunta primeiro, numa olhada
    q = [("Tesouras", "%d" % n["tesouras"], ("inclinação %s%% (%s°)" % (_n(100 * math.tan(math.radians(n["inclinacao"])), 0), _n(n["inclinacao"], 1)))
          if n.get("inclinacao") else ""),
         ("Estrutura metálica", "%s kg" % _n(n["peso_aco"], 1), ("%s kg/m² de projeção" % _n(n["kg_m2"], 1)) if n.get("kg_m2") else ""),
         ("Telhas", "%s m²" % _n(n.get("m2_telhas") or 0.0, 2), "%s ml · %s kg" % (_n(n["ml_telhas"], 2), _n(n["peso_telhas"], 1))),
         ("Total geral (aço + telhas%s)" % (" + rufos" if n.get("peso_funilaria") else ""), "%s kg" % _n(n["total"], 1), ""),
         ("Parafusos", "%d" % n["parafusos"], "e as porcas e arruelas soltas: ver a seção 6"),
         ("Área de pintura", "%s m²" % _n(n.get("m2_pintura") or 0.0, 1), "perfis pelo perímetro da seção, chapas nas duas faces")]
    if R.get("maior") and R["maior"].get("nome"):
        q.append(("Maior peça (transporte)", "%s m" % _n(R["maior"]["comprimento"] / 1000.0, 2), "%s · %s" % (R["maior"]["nome"], R["maior"]["perfil"])))
    if R.get("mais_pesada") and R["mais_pesada"].get("nome"):
        q.append(("Mais pesada (içamento)", "%s kg" % _n(R["mais_pesada"]["kg"], 1), "%s (%s)" % (R["mais_pesada"]["nome"], R["mais_pesada"]["tipo"])))
    partes.append("<table class=\"quadro\"><colgroup><col style=\"width:34%%\"><col style=\"width:20%%\"><col style=\"width:46%%\"></colgroup>%s</table>"
                  % "".join("<tr><td>%s</td><td class=\"v\">%s</td><td class=\"d\">%s</td></tr>" % (_esc(a), _esc(b), _esc(c)) for a, b, c in q))
    # 1. dimensões
    linhas = []
    if dim["n_tesouras"] > 1:
        linhas.append(["Comprimento total entre eixos (%s a %s)" % (dim["eixos"].split()[0], dim["eixos"].split()[-1]), "%s m" % _n(dim["comprimento_total"] / 1000.0, 2),
                       "%d eixos de tesoura: %s" % (dim["n_tesouras"], ", ".join(dim["eixos"].split()))])
    for tr in dim["trechos"]:
        if tr.get("transicao"):
            linhas.append(["Transição entre coberturas (eixos %s)" % tr["eixos_transicao"], "%s m" % _n(tr["transicao"] / 1000.0, 2),
                           "da última tesoura do trecho anterior à primeira deste"])
        um = len(dim["trechos"]) == 1                     # um trecho só: a projeção está na linha de baixo
        # o trecho de uma tesoura só não tem comprimento entre eixos ("0,00 m x 21,21 m"): só o vão
        dim_tr = ("%s m x %s m" % (_n(tr["comprimento"] / 1000.0, 2), _n(tr["vao"] / 1000.0, 2)) if tr["comprimento"] >= 1.0
                  else "vão %s m" % _n(tr["vao"] / 1000.0, 2))
        linhas.append(["%s (eixos %s)" % (tr["nome"], tr["eixos"]), dim_tr,
                       "vão entre apoios %s m" % _n(tr["vao"] / 1000.0, 2)
                       + ("" if um else "; projeção %s x %s m" % (_n(tr["projecao"][0] / 1000.0, 2), _n(tr["projecao"][1] / 1000.0, 2)))])
    linhas.append(["Projeção total com beirais e saias", "%s m x %s m" % (_n(dim["projecao"][0] / 1000.0, 2), _n(dim["projecao"][1] / 1000.0, 2)),
                   "contorno externo em planta; área %s m² (%s kg/m² de aço)" % (_n(dim["area_m2"], 2), _n(n["kg_m2"], 1) if n.get("kg_m2") else "—")])
    if dim.get("nivel_apoio") is not None:
        linhas.append(["Nível de apoio das tesouras", "%s%s m" % ("+" if dim["nivel_apoio"] >= 0 else "", _n(dim["nivel_apoio"] / 1000.0, 3)),
                       "cota do modelo" + (" (face de cima da chapa de apoio)" if dim.get("apoio_por_chapa") else " (ponto mais baixo das tesouras)")])
    partes.append("<h2>1. Dimensões da obra</h2>" + _tabela(["Trecho", ("Dimensão", "r"), "Observação"], [[a, (b, "r"), c] for a, b, c in linhas], larguras=["34%", "20%", "46%"]))
    # 2. tesouras
    tes = R["tesouras"]
    partes.append("<h2>2. Tesouras - %d unidades</h2>" % n["tesouras"])
    partes.append(_tabela(["Tipo", ("Qtd", "c"), "Eixos", ("Vão entre apoios", "r"), ("Comprimento", "r"), ("Flecha (subida do banzo)", "r"),
                           ("Altura na cumeeira*", "r"), "Banzos / treliçamento", ("kg/un", "r"), ("kg total", "r")],
                          [[t["tipo"], (t["qtd"], "c"), t["eixos"], ("%s m" % _n(t["vao"] / 1000.0, 2), "r"), ("%s m" % _n(t["comprimento"] / 1000.0, 2), "r"),
                            ("%s m" % _n(t["flecha"] / 1000.0, 2), "r"), ("%s m" % _n(t["altura"] / 1000.0, 2), "r"),
                            "%s / %s" % (t["banzos"], t["trelicamento"]) if t["trelicamento"] else t["banzos"],
                            (_n(t["kg_un"], 1), "r"), (_n(t["kg_total"], 1), "r")] for t in tes],
                          rodape=[("TOTAL", ""), (n["tesouras"], "c"), "", "", "", "", "", "", "", (_n(sum(t["kg_total"] for t in tes), 1), "r")],
                          larguras=["9%", "5%", "9%", "10%", "10%", "11%", "11%", "19%", "8%", "8%"], classe="tes"))
    notas = R["dados"].get("notas_tesouras") or ""
    meias = [t for t in tes if t.get("meias", 0) >= 2]
    if meias:
        diferentes = [t["tipo"] for t in meias if len(t["membros"]) > 1]
        notas = ("Fabricadas em 2 meias-tesouras emendadas na cumeeira%s. "
                 % ((" (%s com as duas meias diferentes)" % " e ".join(diferentes)) if diferentes else "")) + notas
    partes.append("<p class=\"nota\">* do nível de apoio ao topo do banzo superior na cumeeira.%s</p>" % ((" " + _esc(notas)) if notas else ""))
    # 3. terças
    tc = R["tercas"]
    partes.append("<h2>3. Terças e longarinas</h2>")
    if tc["linhas"]:
        partes.append(_tabela(["Trecho", ("Linhas na cobertura", "r"), ("Linhas nas saias", "r"), ("Total de linhas", "r")],
                              [[l["trecho"] + " (%s)" % l["eixos"], ("%d (%s por água)" % (l["cobertura"], "/".join(str(v) for v in sorted(l["por_agua"].values(), reverse=True)) or "0"), "r"),
                                ("%d (%s por lado)" % (l["saias"], "/".join(str(v) for v in sorted(l["por_lado"].values(), reverse=True)) or "0"), "r"), (l["total"], "r")] for l in tc["linhas"]]))
    c = tc["contagem"]
    # as terças por tipo, em tabela (no lugar do parágrafo, 05/10); a contagem é a da lista e das pranchas
    rot_f = {"cob": "cobertura", "lat": "lateral", "oit": "oitão", "marq": "marquise"}
    if tc.get("itens"):
        partes.append(_tabela(["Tipo", "Família", "Perfil", ("Comprimento", "r"), ("Qtd", "c"), ("kg", "r")],
                              [[i["nome"], rot_f.get(i["familia"], i["familia"]), i["perfil"], ("%s m" % _n(i["comprimento"] / 1000.0, 2), "r"),
                                (i["qtd"], "c"), (_n(i["kg"], 1), "r")] for i in tc["itens"]],
                              rodape=[("TOTAL", "b"), "%d T.C. · %d T.L. · %d T.O.%s" % (c["cob"]["pecas"], c["lat"]["pecas"], c["oit"]["pecas"],
                                                                                    (" · %d T.M." % c["marq"]["pecas"]) if c["marq"]["pecas"] else ""),
                                      "", "", (sum(i["qtd"] for i in tc["itens"]), "c"), (_n(sum(i["kg"] for i in tc["itens"]), 1), "r")],
                              larguras=["16%", "14%", "26%", "16%", "10%", "18%"]))
    if tc["furos"]:
        partes.append("<p class=\"nota\">Furos das terças: %s.</p>" % _esc(tc["furos"]))
    fam = {f["chave"]: f for f in R["familias"]}
    trav = []
    for chave, rot in (("agul_cob", "agulhamentos de cobertura"), ("agul_lat", "agulhamentos laterais/oitão"), ("agul_diag", "agulhamentos diagonais"),
                       ("contrav", "contraventamentos"), ("dispositivos", "dispositivos"), ("chumbadores", "chumbadores")):
        if chave in fam:
            trav.append("%d %s" % (fam[chave]["n"], rot))
    if trav:
        partes.append("<p class=\"nota\">Travamentos: %s.</p>" % _esc(", ".join(trav)))
    # 4. pesos
    gp = R["grupos_peso"]
    linhas = [[g["grupo"], (_n(g["kg"], 1), "r"), (_n(g["pct"], 1) + "%", "r")] for g in gp]
    linhas.append([("TOTAL ESTRUTURA METÁLICA", "b"), (_n(n["peso_aco"], 1), "r"), ("100%", "r")])
    linhas.append(["Telhas (%s ml)" % _n(n["ml_telhas"], 2), (_n(n["peso_telhas"], 1), "r"), ""])
    if n.get("peso_funilaria"):
        linhas.append(["Rufos e calhas", (_n(n["peso_funilaria"], 1), "r"), ""])
    linhas.append([("TOTAL GERAL (AÇO + TELHAS%s)" % (" + RUFOS" if n.get("peso_funilaria") else ""), "b"), (_n(n["total"], 1), "r"), ""])
    partes.append("<h2>4. Pesos</h2>" + _tabela(["Grupo", ("Peso (kg)", "r"), ("%", "r")], linhas, larguras=["70%", "18%", "12%"]))
    partes.append("<p class=\"nota\">Pesos teóricos: perfis formados a frio pela NBR 6355 (tira desenvolvida com o desconto das dobras), "
                  "laminados, tubos e barras pelas tabelas do catálogo, chapas pelo retângulo envolvente. Não inclui solda, pintura, "
                  "parafusos das telhas, rufos e calhas.</p>")
    # 5. telhas
    T = R["telhas"]
    partes.append("<h2>5. Telhas - %s ml</h2>" % _n(T["ml_total"], 2))
    desc = T["descricao"]
    rot_trecho = {"cobertura": "cobertura", "fechamento": "fechamentos (oitões e paredes)", "forro": "forro do beiral"}
    linhas = []
    for trecho, itens in T["trechos"].items():
        # num trecho com muitos comprimentos (oitões, forro), só os tipos grandes saem
        # um a um; os miúdos vão numa linha só, como na relação da fábrica
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
    # 6. parafusos
    P = R["parafusos"]
    partes.append("<h2>6. Parafusos e fixadores - %d parafusos</h2>" % n["parafusos"])
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
    # 7. pendências de conferência (05/10): as ressalvas da lista e o que o levantamento não reconheceu
    pend = R.get("pendencias")
    if pend is None:                                       # resumo sem as pendências montadas: os avisos que contam
        pend = [{"peca": "", "perfil": "", "o_que": a} for a in _avisos_que_contam(R.get("avisos") or [])]
    partes.append("<h2>7. Pendências de conferência - %s</h2>" % ("%d" % len(pend) if pend else "nenhuma"))
    if pend:
        # a tela da lista liga o clique na linha: abre o 3D com as peças em destaque (os ids na linha, 06/10)
        partes.append(_tabela(["Peça", "Perfil", "O que conferir"], [[x["peca"], x["perfil"], x["o_que"]] for x in pend],
                              larguras=["18%", "22%", "60%"], ids_linhas=[",".join(x.get("ids") or []) for x in pend]))
    return _doc("Resumo da obra", "".join(partes), paginado)


def html_resumo_materiais(R: dict, paginado: bool = False) -> str:
    n, dim = R["numeros"], R["dimensoes"]
    partes = [_cabecalho(R, "RESUMO DE MATERIAIS")]
    if len(dim["trechos"]) > 1:
        area = " + ".join("%s %s x %s = %s" % (tr["nome"].lower(), _n(tr["projecao"][0] / 1000.0, 2), _n(tr["projecao"][1] / 1000.0, 2),
                                              _n(tr["projecao"][0] * tr["projecao"][1] / 1e6, 2)) for tr in dim["trechos"])
        partes.append("<p class=\"sub\"><b>*Área (projeção c/ beirais):</b> %s → <b>%s m²</b></p>" % (_esc(area), _n(dim["area_m2"], 2)))
    elif dim["trechos"]:
        tr = dim["trechos"][0]
        partes.append("<p class=\"sub\"><b>*Área (projeção c/ beirais):</b> %s x %s = <b>%s m²</b></p>"
                      % (_n(tr["projecao"][0] / 1000.0, 2), _n(tr["projecao"][1] / 1000.0, 2), _n(dim["area_m2"], 2)))
    partes.append(_html_compra(R))
    partes.append("<h2 class=\"parte\">B. Por grupo (conferência da fábrica)</h2>")
    partes.append("<p class=\"cinza\">Pesos teóricos (kg) e comprimento total (m) por perfil - mesmos números da lista de materiais. "
                  "Chapas somadas por espessura na chaparia. Quadrinho à direita para conferência.</p>")
    blocos = []

    def linhas_perfis(perfis):
        # embaixo de cada perfil, as peças dele: nome, quantidade e comprimento (06/10)
        def pecas(pf):
            itens = " · ".join("%s %dx %s" % (x["nome"], x["qtd"], _n(x["comprimento"])) for x in pf.get("lista") or [])
            return ("<tr><td colspan=\"4\" class=\"pecas-perfil\">%s <span class=\"cinza\">(mm)</span></td></tr>" % _esc(itens)) if itens else ""
        return "".join("<tr><td>%s</td><td class=\"kg\">= %s kg</td><td class=\"m\">%s m</td><td class=\"q\"></td></tr>%s"
                       % (_esc(pf["perfil"]), _n(pf["kg"], 2), _n(pf["m"], 2), pecas(pf)) for pf in perfis)
    for f in R["familias"]:
        h = "<div class=\"fam\"><h3>*%s (%02dx):</h3>" % (_esc(f["titulo"]), f["n"])
        if f.get("composicao"):
            h += "<p class=\"comp\">%s</p>" % _esc(f["composicao"])
        if f.get("nota"):
            h += "<p class=\"comp\">%s</p>" % _esc(f["nota"])
        for s in f["sub"]:
            h += "<p class=\"sub\">%s</p><table>%s</table>" % (_esc(s["titulo"]), linhas_perfis(s["perfis"]))
        if f["perfis"]:
            h += "<table>%s</table>" % linhas_perfis(f["perfis"])
        h += "</div>"
        blocos.append(h)
    # chaparia
    ch = R["chaparia"]
    h = "<div class=\"fam\"><h3>*Chaparia (todas as chapas):</h3><table>"
    for c in ch:
        mat = (" (%s)" % c["material"]) if c.get("material") and len({x.get("material") for x in ch}) > 1 else ""
        mat += (" — modelo %s" % c["modelo"]) if c.get("modelo") else ""
        h += "<tr><td>%s</td><td class=\"kg\">= %s kg</td><td class=\"m\">%d pç / %s m²</td><td class=\"q\"></td></tr>" % (_esc(c["rotulo"] + mat), _n(c["kg"], 2), c["pecas"], _n(c["m2"], 2))
    h += "<tr><td class=\"item\">Total chaparia</td><td class=\"kg item\">= %s kg</td><td class=\"m item\">%d pç</td><td class=\"q\"></td></tr></table></div>" % (_n(R["chaparia_total"]["kg"], 2), R["chaparia_total"]["pecas"])
    blocos.append(h)
    # parafusos
    h = "<div class=\"fam\"><h3>*Parafusos e fixadores:</h3><table>"
    for it in R["parafusos"]:
        h += "<tr><td class=\"item\">%s<br><span class=\"desc\">%s</span></td><td class=\"kg\">= %dx</td><td class=\"q\"></td></tr>" % (_esc(it["nome"]), _esc(it["descricao"]), it["qtd"])
        for loc in it["locais"]:
            h += "<tr><td class=\"loc\">%s</td><td class=\"kg\">%dx</td><td></td></tr>" % (_esc(loc["local"]), loc["qtd"])
    h += "</table></div>"
    blocos.append(h)
    # telhas
    T = R["telhas"]
    h = "<div class=\"fam\"><h3>*Telhas:</h3>"
    rot_trecho = {"cobertura": "Cobertura", "fechamento": "Fechamento dos oitões e paredes", "forro": "Forro do beiral"}
    for trecho, itens in T["trechos"].items():
        descs = " / ".join(dict.fromkeys(it.get("descricao") or "Telha" for it in itens))
        h += "<p class=\"sub\">%s:</p><p class=\"comp\">%s (largura útil %s m)</p><table>" % (_esc(rot_trecho[trecho]), _esc(descs), _n(T["largura_util"] / 1000.0, 2))
        for it in itens:
            h += "<tr><td>%02d pçs c/. %s m</td><td class=\"m\">%s%s</td><td class=\"q\"></td></tr>" % (
                it["qtd"], _n(it["comprimento"] / 1000.0, 2), _esc(it["codigo_n"]), " (cortada na largura)" if it["cortada"] else "")
        h += "</table><p class=\"sub\">Total: %s ml</p>" % _n(T["ml_por_trecho"][trecho], 2)
    h += "<p class=\"sub\"><u>Total telhas = %s ml (%s kg)</u></p></div>" % (_n(T["ml_total"], 2), _n(T["kg_total"], 1))
    blocos.append(h)
    # total
    blocos.append("<div class=\"total-box\"><b>*Total estrutura metálica: %s kg</b><br><span class=\"cinza\">perfis e barras %s kg + chaparia %s kg · "
                  "telhas %s ml / %s m² (%s kg)%s · total geral c/ telhas %s kg · %s kg/m² de aço · pintura %s m²</span></div>"
                  % (_n(n["peso_aco"], 2), _n(R["perfis_kg"], 2), _n(R["chaparia_total"]["kg"], 2), _n(n["ml_telhas"], 2),
                     _n(n.get("m2_telhas") or 0.0, 2), _n(n["peso_telhas"], 1),
                     (" · rufos e calhas %s kg" % _n(n["peso_funilaria"], 1)) if n.get("peso_funilaria") else "",
                     _n(n["total"], 2), _n(n["kg_m2"], 1) if n.get("kg_m2") else "—", _n(n.get("m2_pintura") or 0.0, 1)))
    partes.append("<div class=\"colunas\">%s</div>" % "".join(blocos))
    return _doc("Resumo de materiais", "".join(partes), paginado)


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
    """A. Compra (05/10): perfis em barras comerciais (W em 12 m, o resto em 6 m — a peça maior que 6 m leva o perfil
    para 12 m), chapas de 1,20 × 3,00 com a perda, parafusos, porcas e arruelas por bitola, telhas e a área de pintura.
    Com a coluna "pedido" em branco para o comprador."""
    C = R.get("compra") or {}
    if not C:
        return ""
    h = ["<h2 class=\"parte\">A. Compra</h2>"]
    if C.get("perfis"):
        h.append("<p class=\"sub\"><b>Perfis e barras</b> (um por tipo de perfil, cruzado com o catálogo; barras comerciais pelo plano "
                 "de corte da lista; W em 12 m, os outros em 6 m, ou 12 m quando a peça passa de 6 m)</p>")

        def nome_perfil(p):
            # o nome do catálogo em cima, o do IFC embaixo (06/10); fora do catálogo, o do IFC e de onde veio o kg/m
            cat = p.get("catalogo") or ""
            if cat and p.get("escolhido"):
                cima, baixo = cat, "escolhido no lugar do IFC: %s" % p["perfil"]
            elif cat and p.get("similar"):
                cima, baixo = cat, "similar ao IFC: %s" % p["perfil"]
            elif cat:
                cima, baixo = cat, ("IFC: %s" % p["perfil"]) if cat.replace(" ", "") != p["perfil"].replace(" ", "") else ""
            else:
                cima, baixo = p["perfil"], ("fora do catálogo e sem similar (kg/m pelas medidas)" if p.get("fora_do_catalogo") else "")
            # a tela da lista põe o clique no nome (trocar pelo parecido do catálogo); no PDF é só o texto
            return "<b class=\"trocar-perfil\" data-perfil=\"%s\">%s</b>%s" % (
                _esc(p.get("ifc") or p["perfil"]), _esc(cima), ("<br><span class=\"cinza\">%s</span>" % _esc(baixo)) if baixo else "")
        h.append(_tabela(["Perfil", "Material", ("Peças", "r"), ("m", "r"), ("kg/m", "r"), ("kg", "r"), ("Barra", "r"), ("Barras", "r"),
                          ("Aprov.", "r"), "Pedido"],
                         [[nome_perfil(p), p["material"], (p.get("pecas") or "", "r"), (_n(p["m"], 2), "r"),
                           (_n(p.get("kg_m") or 0.0, 2), "r"), (_n(p["kg"], 1), "r"), ("%s m" % _n(p["barra_m"], 0), "r"),
                           ("%d%s" % (p["barras"], (" (%d emenda%s)" % (p["emendas"], "s" if p["emendas"] > 1 else "")) if p["emendas"] else ""), "r"),
                           ("%s%%" % _n(p["aproveitamento"], 0) if p["aproveitamento"] is not None else "", "r"), ""] for p in C["perfis"]],
                         rodape=[("TOTAL", "b"), "", (sum(p.get("pecas") or 0 for p in C["perfis"]), "r"),
                                 (_n(sum(p["m"] for p in C["perfis"]), 2), "r"), "", (_n(sum(p["kg"] for p in C["perfis"]), 1), "r"),
                                 "", (sum(p["barras"] for p in C["perfis"]), "r"), "", ""],
                         larguras=["24%", "11%", "7%", "10%", "7%", "10%", "7%", "10%", "6%", "8%"], bruto=True,
                         classes_linhas=[_classe_compra(p) for p in C["perfis"]]))
        if any(_classe_compra(p) for p in C["perfis"]):
            h.append(_LEGENDA_COMPRA)
    if C.get("chapas"):
        cl, ca = C["chapa_comercial"]
        h.append("<p class=\"sub\"><b>Chapas</b> (pela espessura comercial: a do modelo ou a próxima acima, e o peso nela; chapa de %s x %s m; "
                 "a quantidade pela área com %s%% de perda no corte)</p>"
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
        h.append("<p class=\"sub\"><b>Parafusos, porcas e arruelas</b> (cada parafuso com 1 porca e 1 arruela; as soltas — pontas roscadas, "
                 "chumbadores — somadas na bitola)</p>")
        linhas = [[pf["nome"], pf["descricao"].split(" + ")[0], (pf["qtd"], "r"), ""] for pf in C.get("parafusos") or []]
        linhas += [["Porca %s" % b, "Porca sextavada Ø%s" % b, (q, "r"), ""] for b, q in C.get("porcas") or []]
        linhas += [["Arruela %s" % b, "Arruela lisa Ø%s" % b, (q, "r"), ""] for b, q in C.get("arruelas") or []]
        h.append(_tabela(["Item", "Descrição", ("Qtd", "r"), "Pedido"], linhas, larguras=["20%", "52%", "12%", "16%"]))
    if C.get("telhas"):
        h.append("<p class=\"sub\"><b>Telhas</b> (m² pela largura útil)</p>")
        h.append(_tabela(["Telha", ("Peças", "r"), ("ml", "r"), ("m²", "r"), ("kg", "r"), "Pedido"],
                         [[x["descricao"], (x["pecas"], "r"), (_n(x["ml"], 2), "r"), (_n(x["m2"], 2), "r"), (_n(x["kg"], 1), "r"), ""] for x in C["telhas"]],
                         larguras=["36%", "10%", "13%", "13%", "13%", "15%"]))
    pt = R.get("pintura") or {}
    if pt:
        h.append("<p class=\"sub\"><b>Área de pintura: %s m²</b> — perfis e barras %s m² (perímetro da seção × comprimento) + chapas %s m² "
                 "(as duas faces)%s</p>" % (_n(pt["total_m2"], 1), _n(pt["total_m2"] - pt["chapas_m2"], 1), _n(pt["chapas_m2"], 1),
                                             ("; sem a seção no catálogo: %s" % ", ".join(pt["sem_secao"])) if pt.get("sem_secao") else ""))
    return "".join(h)


def _tabela(colunas, linhas, rodape=None, larguras=None, bruto=False, classe=None, classes_linhas=None, ids_linhas=None) -> str:
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
    return "<table%s>%s<thead><tr>%s</tr></thead><tbody>%s%s</tbody></table>" % (
        (" class=\"%s\"" % classe) if classe else "", cols, th, corpo, pe)


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
            json.dump({"numeros": R.get("numeros"), "dimensoes": R.get("dimensoes")}, f, ensure_ascii=False, default=str)
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
    return saida
