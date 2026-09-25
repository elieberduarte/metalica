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
from saida.dobras import com_bitola

#: Família de produção de cada tipo de peça/conjunto: (chave, título do resumo de materiais).
FAMILIAS = collections.OrderedDict([
    ("chumbadores", "Chumbadores"), ("tesouras", "Tesouras"),
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
    "tesoura": "tesouras", "terca_cobertura": "tercas_cob", "terca_lateral": "tercas_lat", "terca_oitao": "tercas_oit",
    "terca_marquise": "tercas_marq", "agulhamento": "agul_cob", "agulhamento_lateral": "agul_lat",
    "agulhamento_diagonal": "agul_diag", "gancho": "agul_diag", "contraventamento": "contrav", "barra_roscada": "contrav",
    "conjunto": "dispositivos", "perfil_fechamento": "fix_telha", "cantoneira_forro": "acabamento",
    "chumbador": "chumbadores", "barra": "vigas", "chapa": "chapas", "suporte_terca": "chapas", "castanha": "chapas",
    "suporte_agulhamento": "chapas", "suporte_contraventamento": "chapas",
    "rufo": "funilaria", "calha": "funilaria",
}
#: Grupos do quadro de pesos do resumo da obra, na ordem.
GRUPOS_PESO = [
    ("Tesouras", ("tesouras",)), ("Terças e longarinas", ("tercas_cob", "tercas_lat", "tercas_oit", "tercas_marq")),
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


def rotulo_chapa(t: float) -> str:
    for esp, pol in _CHAPA_POL:
        if abs(t - esp) < 0.06:
            return "#%s (%s mm)" % (pol, _n(esp, 2))
    return "#%s mm" % _n(t, 2)


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
        r = por_conj_nome.setdefault(c.get("nome") or c["marca"], {"nome": c.get("nome") or c["marca"], "marcas": [], "instancias": 0,
                                                                   "peso_unitario": c.get("peso_unitario") or 0.0, "peso_total": 0.0,
                                                                   "categoria": c.get("categoria"), "composicao": {}})
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
        unidade = collections.Counter({m: q for m, q in r["composicao"].items()})
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

    def perfis_de(ps, so_barras=True) -> List[dict]:
        g: Dict[str, dict] = collections.OrderedDict()
        for p in ps:
            if so_barras and p.classe in ("chapa", "chapa_dobrada", "telha", "indefinida"):
                continue
            nome = com_bitola(p.perfil) if p.perfil else "?"
            r = g.setdefault(nome, {"perfil": nome, "kg": 0.0, "m": 0.0, "pecas": 0})
            r["kg"] += p.peso_total
            r["m"] += float(p.comprimento or 0.0) * p.quantidade / 1000.0
            r["pecas"] += p.quantidade
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
        bloco = {"chave": chave, "titulo": titulo, "n": n_pecas, "composicao": composicao_de(ps, conjs),
                 "perfis": perfis_de(ps), "kg": peso_fam.get(chave, 0.0), "sub": []}
        if chave == "tesouras":
            for tt in tipos_tes:
                ps_t = [(marca_para_pos[m], q * tt["qtd"]) for m, q in tt["composicao"].items() if m in marca_para_pos]

                class _Q:
                    def __init__(self, p, q):
                        self.perfil, self.classe, self.comprimento = p.perfil, p.classe, p.comprimento
                        self.quantidade, self.peso_total = q, p.peso * q
                bloco["sub"].append({"titulo": "%s (%02dx) - eixos %s" % (tt["tipo"], tt["qtd"], tt["eixos"]),
                                     "perfis": perfis_de([_Q(p, q) for p, q in ps_t])})
            bloco["perfis"] = []
        if chave == "chapas":
            bloco["nota"] = "somente chapas - ver chaparia"
            bloco["perfis"] = []
        familias.append(bloco)

    # ---- chaparia
    chaparia = []
    for g in lista.get("chapas") or []:
        chaparia.append({"rotulo": rotulo_chapa(float(g["espessura"])), "kg": g["peso"], "pecas": g["pecas"], "m2": g["area_m2"]})
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
    return {
        "projeto": identificacao, "dados": dados,
        "numeros": {"tesouras": sum(t["qtd"] for t in tipos_tes), "peso_aco": peso_aco, "ml_telhas": ml_telhas,
                    "peso_telhas": peso_telhas, "peso_funilaria": peso_funilaria,
                    "total": peso_aco + peso_telhas + peso_funilaria, "parafusos": n_parafusos,
                    "inclinacao": inclinacao, "kg_m2": (peso_aco / area_m2) if area_m2 else None},
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
    for f in fixadores:
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
        lr = r["locais"].setdefault(local[0], {"qtd": 0, "pecas": set()})
        lr["qtd"] += 1
        lr["pecas"].update(local[1])
    saida = []
    for chave, r in contagem.items():
        if r["parafuso"]:
            nome, desc, _d = descricao_parafuso(chave.replace(" ", ""))
        else:
            nome = chave
            desc = ("Arruela lisa Ø%s" if chave.startswith("Arruela") else "Porca sextavada Ø%s UNC") % chave.split(" ", 1)[1]
        locais = sorted(r["locais"].items(), key=lambda kv: -kv[1]["qtd"])
        saida.append({"nome": nome, "descricao": desc, "qtd": r["qtd"], "parafuso": r["parafuso"], "d": r["d"],
                      "locais": [{"local": k, "qtd": v["qtd"], "pecas": sorted(v["pecas"], key=_ordem_natural)} for k, v in locais]})
    saida.sort(key=lambda x: (not x["parafuso"], x["d"] or 0, _ordem_natural(x["nome"])))
    return saida


def _telhas(lev: dict, lista: dict, pecas_por_marca, nivel_apoio, dados) -> dict:
    """As telhas por trecho — cobertura, fechamento (oitões e paredes) e forro do beiral —
    com o código TL/MD/CU, como a lista de compra da fábrica."""
    descricao = str(dados.get("telha") or "").strip()
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
        itens.append({"trecho": trecho, "codigo": codigo, "marca": li["marca"], "perfil": li.get("perfil", ""),
                      "qtd": int(li.get("quantidade") or 0), "comprimento": comp, "ml": comp * int(li.get("quantidade") or 0) / 1000.0,
                      "kg": float(li.get("peso_total") or 0.0), "cortada": cortada, "classe": classe})
    ordem_trecho = {"cobertura": 0, "fechamento": 1, "forro": 2}
    itens.sort(key=lambda t: (ordem_trecho[t["trecho"]], {"TL": 0, "MD": 1, "CU": 2}[t["codigo"]], -t["comprimento"]))
    n_por = collections.Counter()
    for t in itens:
        n_por[t["codigo"]] += 1
        t["codigo_n"] = "%s%d" % (t["codigo"], n_por[t["codigo"]])
    trechos = collections.OrderedDict()
    for t in itens:
        trechos.setdefault(t["trecho"], []).append(t)
    return {"descricao": descricao, "itens": itens, "trechos": trechos,
            "ml_total": sum(t["ml"] for t in itens), "kg_total": sum(t["kg"] for t in itens),
            "ml_por_trecho": {k: sum(t["ml"] for t in v) for k, v in trechos.items()},
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
    for p in posicoes:
        t = tipos.get(p.marca, "")
        if t not in fam:
            continue
        contagem[fam[t]]["tipos"] += 1
        perfis[com_bitola(p.perfil)] += p.quantidade
        for f in p.furos:
            furos[f.rotulo()] += 1
        for m in marcas_de(p):
            for e in pecas_por_marca.get(m) or []:
                # cada peça pela orientação dela: a mesma posição pode viajar na cobertura e na saia
                k = parede.get(_parede_da_peca(e, eixo_g, limites_g)) or ("marq" if t == "terca_marquise" else "cob")
                contagem[k]["pecas"] += 1
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
    return {"contagem": contagem, "linhas": linhas, "perfil_principal": perfil_principal,
            "furos": ", ".join("%s" % r for r, _ in furos.most_common(3))}


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
    linha2 = " - ".join(x for x in (d.get("descricao") or "", ("revisão %s" % rev) if rev else "", quando,
                                   ("base: modelo IFC %s" % p.get("origem_ifc")) if p.get("origem_ifc") else "") if x)
    return ("<h1>%s</h1><p class=\"sub\"><b>%s</b></p><p class=\"cinza\">%s</p>"
            % (_esc(titulo), _esc(p.get("nome") or ""), _esc(linha2)))


def html_resumo_obra(R: dict, paginado: bool = False) -> str:
    n, dim = R["numeros"], R["dimensoes"]
    partes = [_cabecalho(R, "RESUMO DA OBRA")]
    partes.append("<div class=\"numeros\"><b>Números principais:</b> %d tesouras - estrutura metálica <b>%s kg</b> - telhas <b>%s ml</b> (%s kg) - "
                  "total geral <b>%s kg</b> - <b>%d parafusos</b>%s</div>"
                  % (n["tesouras"], _n(n["peso_aco"], 1), _n(n["ml_telhas"], 2), _n(n["peso_telhas"], 1), _n(n["total"], 1), n["parafusos"],
                     (" - inclinação %s%% (%s°)" % (_n(100 * math.tan(math.radians(n["inclinacao"])), 0), _n(n["inclinacao"], 1))) if n.get("inclinacao") else ""))
    # 1. dimensões
    linhas = []
    if dim["n_tesouras"] > 1:
        linhas.append(["Comprimento total entre eixos (%s a %s)" % (dim["eixos"].split()[0], dim["eixos"].split()[-1]), "%s m" % _n(dim["comprimento_total"] / 1000.0, 2),
                       "%d eixos de tesoura: %s" % (dim["n_tesouras"], ", ".join(dim["eixos"].split()))])
    for tr in dim["trechos"]:
        if tr.get("transicao"):
            linhas.append(["Transição entre coberturas (eixos %s)" % tr["eixos_transicao"], "%s m" % _n(tr["transicao"] / 1000.0, 2),
                           "da última tesoura do trecho anterior à primeira deste"])
        linhas.append(["%s (eixos %s)" % (tr["nome"], tr["eixos"]), "%s m x %s m" % (_n(tr["comprimento"] / 1000.0, 2), _n(tr["vao"] / 1000.0, 2)),
                       "vão entre apoios %s m; projeção %s x %s m" % (_n(tr["vao"] / 1000.0, 2), _n(tr["projecao"][0] / 1000.0, 2), _n(tr["projecao"][1] / 1000.0, 2))])
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
    partes.append("<p class=\"nota\">Peças: %d terças de cobertura (T.C.) em %d tipos, %d terças laterais (T.L.), %d terças de oitão (T.O.)%s. "
                  "Perfil principal %s%s.</p>"
                  % (c["cob"]["pecas"], c["cob"]["tipos"], c["lat"]["pecas"], c["oit"]["pecas"],
                     (", %d de marquise (T.M.)" % c["marq"]["pecas"]) if c["marq"]["pecas"] else "",
                     _esc(tc["perfil_principal"]), ("; furos das terças: %s" % _esc(tc["furos"])) if tc["furos"] else ""))
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
            texto = "%s - %s%s" % (desc or ("Telha %s" % it["perfil"]), rot_trecho[trecho],
                                   " - multidobra" if it["codigo"] == "MD" else (" - cumeeira" if it["codigo"] == "CU" else "")) \
                + (" - cortada na largura" if it["cortada"] else "")
            linhas.append([it["codigo_n"], texto, (it["qtd"], "c"), (_n(it["comprimento"] / 1000.0, 2), "r"), (_n(it["ml"], 2), "r"), (_n(it["kg"], 1), "r")])
        if miudos:
            codigos = [it["codigo_n"] for it in miudos]
            texto = "%s - %s (%d comprimentos: %s a %s - ver relação de telhas)" % (
                desc or ("Telha %s" % miudos[0]["perfil"]), rot_trecho[trecho], len(miudos), codigos[0], codigos[-1])
            linhas.append(["%d tipos" % len(miudos), texto, (sum(it["qtd"] for it in miudos), "c"), ("vários", "r"),
                           (_n(sum(it["ml"] for it in miudos), 2), "r"), (_n(sum(it["kg"] for it in miudos), 1), "r")])
    sub = " + ".join("%s %s ml" % (rot_trecho[k], _n(v, 2)) for k, v in T["ml_por_trecho"].items())
    partes.append(_tabela(["Tipo", "Descrição", ("Qtd", "c"), ("Comp. (m)", "r"), ("Total (ml)", "r"), ("kg", "r")], linhas,
                          rodape=[("TOTAL", "b"), sub, "", "", (_n(T["ml_total"], 2), "r"), (_n(T["kg_total"], 1), "r")],
                          larguras=["9%", "55%", "7%", "9%", "10%", "10%"]))
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
    partes.append("<p class=\"nota\">Quantidades conforme o modelo IFC.</p>")
    avisos = [a for a in R.get("avisos") or [] if "peso" in a.lower() or "conferir" in a.lower()]
    if avisos:
        partes.append("<p class=\"cinza\">Avisos do levantamento: %s</p>" % _esc(" · ".join(avisos[:6])))
    return _doc("Resumo da obra", "".join(partes), paginado)


def html_resumo_materiais(R: dict, paginado: bool = False) -> str:
    n, dim = R["numeros"], R["dimensoes"]
    partes = [_cabecalho(R, "RESUMO DE MATERIAIS")]
    area = " + ".join("%s %s x %s = %s" % (tr["nome"].lower(), _n(tr["projecao"][0] / 1000.0, 2), _n(tr["projecao"][1] / 1000.0, 2),
                                          _n(tr["projecao"][0] * tr["projecao"][1] / 1e6, 2)) for tr in dim["trechos"])
    partes.append("<p class=\"sub\"><b>*Área (projeção c/ beirais):</b> %s → <b>%s m²</b></p>" % (_esc(area), _n(dim["area_m2"], 2)))
    partes.append("<p class=\"cinza\">Pesos teóricos (kg) e comprimento total (m) por perfil - mesmos números da lista de materiais. "
                  "Chapas somadas por espessura na chaparia. Quadrinho à direita para conferência.</p>")
    blocos = []

    def linhas_perfis(perfis):
        return "".join("<tr><td>%s</td><td class=\"kg\">= %s kg</td><td class=\"m\">%s m</td><td class=\"q\"></td></tr>"
                       % (_esc(pf["perfil"]), _n(pf["kg"], 2), _n(pf["m"], 2)) for pf in perfis)
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
        h += "<tr><td>%s</td><td class=\"kg\">= %s kg</td><td class=\"m\">%d pç / %s m²</td><td class=\"q\"></td></tr>" % (_esc(c["rotulo"]), _n(c["kg"], 2), c["pecas"], _n(c["m2"], 2))
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
    desc = T["descricao"] or "Telha"
    h = "<div class=\"fam\"><h3>*Telhas - %s:</h3>" % _esc(desc)
    rot_trecho = {"cobertura": "Cobertura", "fechamento": "Fechamento dos oitões e paredes", "forro": "Forro do beiral"}
    for trecho, itens in T["trechos"].items():
        h += "<p class=\"sub\">%s:</p><p class=\"comp\">%s (largura útil %s m)</p><table>" % (_esc(rot_trecho[trecho]), _esc(desc), _n(T["largura_util"] / 1000.0, 2))
        for it in itens:
            h += "<tr><td>%02d pçs c/. %s m</td><td class=\"m\">%s%s</td><td class=\"q\"></td></tr>" % (
                it["qtd"], _n(it["comprimento"] / 1000.0, 2), _esc(it["codigo_n"]), " (cortada na largura)" if it["cortada"] else "")
        h += "</table><p class=\"sub\">Total: %s ml</p>" % _n(T["ml_por_trecho"][trecho], 2)
    h += "<p class=\"sub\"><u>Total telhas = %s ml (%s kg)</u></p></div>" % (_n(T["ml_total"], 2), _n(T["kg_total"], 1))
    blocos.append(h)
    # total
    blocos.append("<div class=\"total-box\"><b>*Total estrutura metálica: %s kg</b><br><span class=\"cinza\">perfis e barras %s kg + chaparia %s kg · "
                  "telhas %s ml (%s kg)%s · total geral c/ telhas %s kg · %s kg/m² de aço</span></div>"
                  % (_n(n["peso_aco"], 2), _n(R["perfis_kg"], 2), _n(R["chaparia_total"]["kg"], 2), _n(n["ml_telhas"], 2),
                     _n(n["peso_telhas"], 1), (" · rufos e calhas %s kg" % _n(n["peso_funilaria"], 1)) if n.get("peso_funilaria") else "",
                     _n(n["total"], 2), _n(n["kg_m2"], 1) if n.get("kg_m2") else "—"))
    partes.append("<div class=\"colunas\">%s</div>" % "".join(blocos))
    return _doc("Resumo de materiais", "".join(partes), paginado)


def _tabela(colunas, linhas, rodape=None, larguras=None, bruto=False, classe=None) -> str:
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
    corpo = "".join("<tr>%s</tr>" % "".join(cel(c) for c in l) for l in linhas)
    pe = ("<tr class=\"total\">%s</tr>" % "".join(cel(c) for c in rodape)) if rodape else ""
    return "<table%s>%s<thead><tr>%s</tr></thead><tbody>%s%s</tbody></table>" % (
        (" class=\"%s\"" % classe) if classe else "", cols, th, corpo, pe)


# ============================================================ gravação
def gerar_resumos(pasta: str, R: dict, imprimir_pdf: bool = True) -> dict:
    """Grava resumo-da-obra.html/.pdf e resumo-de-materiais.html/.pdf em `pasta`."""
    from projetos import trocar_arquivo
    os.makedirs(pasta, exist_ok=True)
    saida = {}
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
