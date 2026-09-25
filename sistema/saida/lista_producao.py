# -*- coding: utf-8 -*-
"""Lista de materiais de produção, feita do mesmo levantamento que o detalhamento desenha.

A partir das posições do modelo (``nucleo2d.detalhar.levantar``) saem, num só lugar:

* **romaneio por posição** — marca, conjuntos, tipo, perfil ou chapa, material, quantidade,
  dimensões, furos, peso unitário e total, observações;
* **resumo por perfil** — quantas peças, comprimento total, kg/m, peso e a estimativa de
  barras comerciais (6 ou 12 m) por encaixe "primeiro que cabe, do maior para o menor";
* **chapas por espessura e material** — peças, área e peso;
* **conjuntos** — instâncias, composição e peso de cada montagem (o que sobe no caminhão);
* **acessórios** contados (parafusos, porcas, arruelas) e **totais por categoria**.

Grava em ``<projeto>/detalhamento/``: ``lista-de-materiais.json`` (a tela lê), ``romaneio.csv``,
``resumo-perfis.csv``, ``resumo-chapas.csv``, ``conjuntos.csv`` (abrem no Excel) e
``lista-de-materiais.html`` (imprimível); ``gerar_pdf`` faz o PDF com o Chrome, como o memorial.
"""
import collections
import csv
import math
import os
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from saida.detalhamento import Posicao, CLASSES, _ordenar

#: Comprimento das barras comerciais (mm) e perda por corte considerada no encaixe.
BARRAS_COMERCIAIS = (6000.0, 12000.0)
PERDA_CORTE = 3.0

ARQUIVO_JSON = "lista-de-materiais.json"
ARQUIVO_HTML = "lista-de-materiais.html"
ARQUIVO_PDF = "Lista-de-materiais.pdf"


# ============================================================ números e texto

def _n(x, casas=0) -> str:
    """Número no padrão brasileiro: 12.345,6."""
    if x is None or x == "":
        return ""
    s = "{:,.{c}f}".format(float(x), c=casas)
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _esc(t) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ordem_natural(texto):
    from nucleo2d.detalhar import _ordem_natural as f
    return f(texto)


# ============================================================ encaixe em barras

def encaixar(comprimentos: Sequence[float], barra: float, perda: float = PERDA_CORTE) -> dict:
    """Quantas barras de `barra` mm saem as peças, por "primeiro que cabe" do maior para o
    menor. Peça maior que a barra conta como emenda (uma barra inteira por trecho, o resto
    volta para o encaixe)."""
    sobras: List[float] = []
    colocado = 0.0
    emendas = 0
    fila = []
    for L in sorted(comprimentos, reverse=True):
        if L > barra + 1e-6:
            emendas += 1
            inteiras = int(L // barra)
            sobras.extend([0.0] * inteiras)
            colocado += inteiras * barra
            resto = L - inteiras * barra
            if resto > 1e-6:
                fila.append(resto)
        else:
            fila.append(L)
    for L in sorted(fila, reverse=True):
        for i, s in enumerate(sobras):
            if s >= L + perda or abs(s - L) < 1e-6:
                sobras[i] = max(0.0, s - L - perda)
                break
        else:
            sobras.append(max(0.0, barra - L - perda))
        colocado += L
    n = len(sobras)
    total = n * barra
    return {"comprimento": barra, "quantidade": n, "emendas": emendas,
            "aproveitamento": round(100.0 * colocado / total, 1) if total else 0.0,
            "sobra_m": round(sum(sobras) / 1000.0, 2)}


def _barra_para(comprimentos: Sequence[float], barra: float) -> float:
    """0 = automático: 6 m quando tudo cabe, senão 12 m."""
    if barra and barra > 0:
        return float(barra)
    maior = max(comprimentos) if comprimentos else 0.0
    return BARRAS_COMERCIAIS[0] if maior <= BARRAS_COMERCIAIS[0] + 1e-6 else BARRAS_COMERCIAIS[1]


# ============================================================ montagem

def _e_chapa(p: Posicao) -> bool:
    return p.classe in ("chapa", "chapa_dobrada")


def _area_m2(p: Posicao) -> float:
    if p.desenvolvimento:
        return p.desenvolvimento[0] * p.desenvolvimento[1] / 1e6
    return p.L * p.H / 1e6


def _compra_telha(p: Posicao) -> dict:
    from nucleo2d.detalhe.base import compra_da_telha
    return compra_da_telha(p)


def _linha_posicao(p: Posicao, categoria: str) -> dict:
    chapa = _e_chapa(p)
    if p.classe == "telha":
        # a telha é comprada inteira, na largura comercial; o corte é na obra
        c = _compra_telha(p)
        return {"marca": p.marca, "nome": getattr(p, "nome", ""), "categoria": categoria, "classe": CLASSES.get(p.classe, p.classe),
                "perfil": p.perfil, "material": p.material, "quantidade": p.quantidade,
                "comprimento": round(c["comprimento"]), "largura": round(c["largura"]), "espessura": 0,
                "area_m2": round(c["comprimento"] * c["largura"] / 1e6 * p.quantidade, 3),
                "furos": p.rotulo_furos(), "parafusos": p.rotulo_parafusos(), "peso": round(c["peso"], 3),
                "peso_total": round(c["peso"] * p.quantidade, 2), "conjuntos": list(p.conjuntos),
                "observacoes": list(p.observacoes) + (["corte em obra"] if c["cortada"] else [])}
    return {"marca": p.marca, "nome": getattr(p, "nome", ""), "categoria": categoria, "classe": CLASSES.get(p.classe, p.classe),
            "perfil": p.perfil, "material": p.material, "quantidade": p.quantidade,
            "comprimento": round(p.comprimento) if p.classe != "indefinida" else 0,
            "largura": round(p.desenvolvimento[0] if p.desenvolvimento else p.H) if chapa or p.classe == "telha" else 0,
            "espessura": round(p.espessura or p.T, 1) if chapa else 0,
            "area_m2": round(_area_m2(p) * p.quantidade, 3) if chapa or p.classe == "telha" else 0,
            "furos": p.rotulo_furos(), "parafusos": p.rotulo_parafusos(), "peso": round(p.peso, 3), "peso_total": round(p.peso_total, 2),
            "conjuntos": list(p.conjuntos), "observacoes": list(p.observacoes)}


def _conjuntos(pecas, por_marca: Dict[str, Posicao], nomes: Optional[Dict[str, str]] = None) -> List[dict]:
    """Montagens do modelo: instâncias pelo mdc das quantidades por posição (como o
    detalhamento), composição unitária e peso de uma montagem."""
    from nucleo2d.detalhar import _marcas
    por_conj: Dict[str, collections.Counter] = collections.OrderedDict()
    for e in pecas:
        m = _marcas(e)
        conj = str(m.get("conjunto") or "")
        if not conj:
            continue
        por_conj.setdefault(conj, collections.Counter())[str(m.get("posicao") or e.nome)] += 1
    from nucleo2d.detalhar import _unidade_pela_maioria
    saida = []
    for conj, total in por_conj.items():
        n = 0
        for q in total.values():
            n = math.gcd(n, q)
        n = max(n, 1)
        unidade = {k: q // n for k, q in total.items()}
        difere = []
        if n == 1:
            # uma peça a mais ou a menos numa das instâncias derruba o mdc para 1 e o
            # conjunto inteiro saía como uma unidade só; a maioria das posições dá a unidade
            # (a mesma regra do detalhamento)
            robusta = _unidade_pela_maioria(collections.Counter(total))
            if robusta:
                n, unidade = robusta[0], dict(robusta[1])
                difere = ["%s (%d em vez de %d)" % (k, total.get(k, 0), n * unidade.get(k, 0))
                          for k in sorted(set(total) | set(unidade), key=_ordem_natural)
                          if total.get(k, 0) != n * unidade.get(k, 0)]
        if sum(unidade.values()) < 2:
            continue
        if all(por_marca.get(k) is not None and por_marca[k].classe == "telha" for k in unidade):
            continue
        # o peso total é o das peças que existem (29 P13, não 8 × 4); o unitário, a média
        peso_tot = sum(q * (por_marca[k].peso if k in por_marca else 0.0) for k, q in total.items())
        barras = sum(q for k, q in unidade.items() if k in por_marca and por_marca[k].classe.startswith("barra"))
        comp = sorted(unidade.items(), key=lambda kv: _ordem_natural(kv[0]))
        saida.append({"marca": conj, "nome": (nomes or {}).get(conj, ""), "instancias": n, "pecas_unidade": sum(unidade.values()),
                      "composicao": dict(comp),
                      "composicao_texto": ", ".join("%d× %s" % (q, k) for k, q in comp)
                      + ("  (no total diferem: %s)" % ", ".join(difere) if difere else ""),
                      "peso_unitario": round(peso_tot / n, 2), "peso_total": round(peso_tot, 2),
                      "difere": difere,
                      "categoria": "TESOURAS" if barras >= 8 else "CONJUNTOS"})
    saida.sort(key=lambda c: (-c["peso_total"], _ordem_natural(c["marca"])))
    return saida


def comparar_dobras(perfis: Sequence[dict]) -> dict:
    """Perfis dobrados da chapa: peso teórico (soma das medidas externas) × com o desconto
    das dobras (a tira desenvolvida), lado a lado com o peso do modelo e o kg/m da NBR 6355.
    Ver `saida/dobras.py`."""
    from saida import dobras
    linhas = []
    for g in perfis:
        r = dobras.pesos(g["perfil"], g["comprimento_m"])
        if r is None:
            continue
        norma = dobras.massa_da_norma(g["perfil"])
        linhas.append({"perfil": g["perfil"], "material": g["material"], "pecas": g["pecas"], "comprimento_m": g["comprimento_m"],
                       "t": r["t"], "dobras": r["dobras"], "soma_externa": r["soma_externa"], "desenvolvido": r["desenvolvido"],
                       "kg_m_teorico": r["kg_m_teorico"], "kg_m_desconto": r["kg_m_desconto"], "kg_m_norma": norma,
                       "kg_m_modelo": g["kg_m"], "peso_modelo": g["peso"],
                       "peso_teorico": round(r["peso_teorico"], 1), "peso_desconto": round(r["peso_desconto"], 1),
                       "diferenca": round(r["peso_teorico"] - r["peso_desconto"], 1),
                       "diferenca_pct": round(100.0 * (1.0 - r["kg_m_desconto"] / r["kg_m_teorico"]), 2) if r["kg_m_teorico"] else 0.0})
    tot = {k: round(sum(li[k] for li in linhas), 1) for k in ("peso_modelo", "peso_teorico", "peso_desconto", "diferenca")}
    tot["diferenca_pct"] = round(100.0 * tot["diferenca"] / tot["peso_teorico"], 2) if tot["peso_teorico"] else 0.0
    return {"linhas": linhas, "totais": tot,
            "regra": "desconto por dobra de 90° = 2(ri + t) − π/2 (ri + k·t), com ri = %g·t e k = %g "
                     "(linha média, como a NBR 6355): ≈ %.2f·t" % (dobras.RAIO_INTERNO, dobras.FATOR_K, dobras.desconto_por_dobra(1.0))}


def montar(posicoes: Sequence[Posicao], categorias: Dict[str, str], acessorios: Dict[str, int],
           pecas=None, barra: float = 0.0, projeto: Optional[dict] = None,
           nomes_conjuntos: Optional[Dict[str, str]] = None) -> dict:
    """A lista inteira, pronta para gravar em JSON. `barra` em mm (0 = automático);
    `nomes_conjuntos`: marca do conjunto → nome de produção."""
    from nucleo2d.detalhar import CATEGORIAS
    lista = _ordenar(posicoes)
    por_marca = {}
    for p in lista:
        por_marca[p.marca] = p
        for m in (getattr(p, "marcas", None) or []):
            por_marca[m] = p
    # telhas multi-dobra: as facetas e retas de cada uma viram uma linha só, pelo desenvolvido
    md = {"telhas": [], "posicoes": set()}
    if pecas:
        try:
            from nucleo2d.detalhe.telhas import multidobras
            md = multidobras(pecas)
        except Exception:                                   # noqa: BLE001
            md = {"telhas": [], "posicoes": set()}
    md.setdefault("cumeeiras", [])
    consumida = lambda p: p.classe == "telha" and all(m in md["posicoes"] for m in (getattr(p, "marcas", None) or [p.marca]))   # noqa: E731
    lista = [p for p in lista if not consumida(p)]
    linhas = [_linha_posicao(p, categorias.get(p.marca, "OUTROS")) for p in lista]
    for i, t in enumerate(md["telhas"], 1):
        linhas.append({"marca": t["conjunto"], "nome": "TMD.%d" % i, "categoria": "TELHAS", "classe": "Telha multi-dobra",
                       "perfil": t["perfil"], "material": t["material"], "quantidade": t["instancias"],
                       "comprimento": round(t["desenv_ext"]), "largura": 980, "espessura": 0,
                       "area_m2": round(t["desenv_ext"] * 980 / 1e6 * t["instancias"], 3), "furos": "", "parafusos": "",
                       "peso": round(t["peso"], 3), "peso_total": round(t["peso"] * t["instancias"], 2), "conjuntos": [t["conjunto"]],
                       "observacoes": ["multi-dobra: retas %.0f + %.0f, raio int. %.0f, %.1f°, desenv. int. %.0f" % (
                           t["reta1"], t["reta2"], t["raio_int"], t["angulo"], t["desenv_int"])]})
        cb = t.get("cobrimento")
        if cb:
            linhas.append({"marca": t["conjunto"] + "-C", "nome": "TMD.%d-C" % i, "categoria": "TELHAS",
                           "classe": "Telha (complemento da multi-dobra)", "perfil": t["perfil"], "material": t["material"],
                           "quantidade": t["instancias"], "comprimento": round(cb["resto"]), "largura": 980, "espessura": 0,
                           "area_m2": round(cb["resto"] * 980 / 1e6 * t["instancias"], 3), "furos": "", "parafusos": "",
                           "peso": cb.get("peso", 0.0), "peso_total": round(cb.get("peso", 0.0) * t["instancias"], 2),
                           "conjuntos": [t["conjunto"]],
                           "observacoes": ["começa %d mm antes da terça %s (transpasse %.0f mm)" % (150, cb["terca"], cb["transpasse"])]})

    for i, t in enumerate(md["cumeeiras"], 1):
        linhas.append({"marca": t["conjunto"], "nome": "CM.%d" % i, "categoria": "TELHAS", "classe": "Cumeeira",
                       "perfil": t["perfil"], "material": t["material"], "quantidade": t["instancias"],
                       "comprimento": round(t["desenv"]), "largura": 980, "espessura": 0,
                       "area_m2": round(t["desenv"] * 980 / 1e6 * t["instancias"], 3), "furos": "", "parafusos": "",
                       "peso": round(t["peso"], 3), "peso_total": round(t["peso"] * t["instancias"], 2), "conjuntos": [t["conjunto"]],
                       "observacoes": ["cumeeira: pernas %d + %d, dobra %.1f°, uma peça só" % (t["perna1"], t["perna2"], t["angulo"])]})

    # perfis (tudo o que é barra, tirante incluído): peças, comprimento total, kg/m, barras
    perfis: Dict[tuple, dict] = collections.OrderedDict()
    for p in lista:
        if _e_chapa(p) or p.classe in ("telha", "indefinida"):
            continue
        g = perfis.setdefault((p.perfil, p.material), {
            "perfil": p.perfil, "material": p.material, "categoria": categorias.get(p.marca, "BARRAS"),
            "posicoes": [], "pecas": 0, "comprimento_m": 0.0, "peso": 0.0, "_comps": []})
        g["posicoes"].append(p.marca)
        g["pecas"] += p.quantidade
        g["comprimento_m"] += p.comprimento * p.quantidade / 1000.0
        g["peso"] += p.peso_total
        g["_comps"].extend([p.comprimento] * p.quantidade)
        if categorias.get(p.marca) == "TERÇAS":
            g["categoria"] = "TERÇAS"
    lista_perfis = []
    for g in perfis.values():
        comps = g.pop("_comps")
        b = _barra_para(comps, barra)
        g["barras"] = encaixar(comps, b)
        g["kg_m"] = round(g["peso"] / g["comprimento_m"], 3) if g["comprimento_m"] else 0.0
        g["comprimento_m"] = round(g["comprimento_m"], 2)
        g["peso"] = round(g["peso"], 1)
        g["posicoes"] = sorted(g["posicoes"], key=_ordem_natural)
        lista_perfis.append(g)
    lista_perfis.sort(key=lambda g: (-g["peso"], g["perfil"]))
    dobrados = comparar_dobras(lista_perfis)

    # chapas por espessura e material
    chapas: Dict[tuple, dict] = collections.OrderedDict()
    for p in lista:
        if not _e_chapa(p):
            continue
        t = round(p.espessura or p.T, 1)
        g = chapas.setdefault((t, p.material), {"espessura": t, "material": p.material, "posicoes": [],
                                                "pecas": 0, "area_m2": 0.0, "peso": 0.0})
        g["posicoes"].append(p.marca)
        g["pecas"] += p.quantidade
        g["area_m2"] += _area_m2(p) * p.quantidade
        g["peso"] += p.peso_total
    lista_chapas = []
    for g in chapas.values():
        g["area_m2"] = round(g["area_m2"], 2)
        g["peso"] = round(g["peso"], 1)
        g["posicoes"] = sorted(g["posicoes"], key=_ordem_natural)
        lista_chapas.append(g)
    lista_chapas.sort(key=lambda g: (g["espessura"], g["material"]))

    # telhas por perfil
    telhas: Dict[str, dict] = collections.OrderedDict()
    for p in lista:
        if p.classe != "telha":
            continue
        g = telhas.setdefault(p.perfil, {"perfil": p.perfil, "posicoes": [], "pecas": 0,
                                         "comprimento_m": 0.0, "area_m2": 0.0, "peso": 0.0, "_chapas": collections.Counter()})
        c = _compra_telha(p)
        g["posicoes"].append(p.marca)
        g["pecas"] += p.quantidade
        g["comprimento_m"] += c["comprimento"] * p.quantidade / 1000.0
        g["area_m2"] += c["comprimento"] * c["largura"] / 1e6 * p.quantidade
        g["peso"] += c["peso"] * p.quantidade
        g["_chapas"][int(round(c["comprimento"]))] += p.quantidade
        g["largura"] = int(round(c["largura"]))
        g["largura_total"] = int(round(c.get("largura_total", c["largura"])))
    for t in md["telhas"]:
        g = telhas.setdefault(t["perfil"], {"perfil": t["perfil"], "posicoes": [], "pecas": 0,
                                             "comprimento_m": 0.0, "area_m2": 0.0, "peso": 0.0, "_chapas": collections.Counter()})
        g["posicoes"].append(t["conjunto"])
        g["pecas"] += t["instancias"]
        g["comprimento_m"] += t["desenv_ext"] * t["instancias"] / 1000.0
        g["area_m2"] += t["desenv_ext"] * 980 / 1e6 * t["instancias"]
        g["peso"] += t["peso"] * t["instancias"]
        g["_chapas"][int(round(t["desenv_ext"]))] += t["instancias"]
        g.setdefault("multidobra", []).append(int(round(t["desenv_ext"])))
        cb = t.get("cobrimento")
        if cb:
            g["pecas"] += t["instancias"]
            g["comprimento_m"] += cb["resto"] * t["instancias"] / 1000.0
            g["area_m2"] += cb["resto"] * 980 / 1e6 * t["instancias"]
            g["peso"] += cb.get("peso", 0.0) * t["instancias"]
            g["_chapas"][int(round(cb["resto"]))] += t["instancias"]
        g["largura"] = 980
        g["largura_total"] = 1050
    for t in md["cumeeiras"]:
        g = telhas.setdefault(t["perfil"], {"perfil": t["perfil"], "posicoes": [], "pecas": 0,
                                             "comprimento_m": 0.0, "area_m2": 0.0, "peso": 0.0, "_chapas": collections.Counter()})
        g["posicoes"].append(t["conjunto"])
        g["pecas"] += t["instancias"]
        g["comprimento_m"] += t["desenv"] * t["instancias"] / 1000.0
        g["area_m2"] += t["desenv"] * 980 / 1e6 * t["instancias"]
        g["peso"] += t["peso"] * t["instancias"]
        g["_chapas"][int(round(t["desenv"]))] += t["instancias"]
        g.setdefault("cumeeira", []).append(int(round(t["desenv"])))
        g["largura"] = 980
        g["largura_total"] = 1050
    lista_telhas = []
    for g in telhas.values():
        chapas_t = g.pop("_chapas")
        # o pedido de compra: quantas chapas inteiras de cada comprimento
        g["chapas"] = [{"comprimento": L, "quantidade": q} for L, q in sorted(chapas_t.items(), reverse=True)]
        md_L = set(g.pop("multidobra", []))
        cm_L = set(g.pop("cumeeira", []))
        g["chapas_texto"] = " · ".join("%d× %d%s" % (q, L, " multi-dobra" if L in md_L else " cumeeira" if L in cm_L else "")
                                       for L, q in sorted(chapas_t.items(), reverse=True))
        for k in ("comprimento_m", "area_m2"):
            g[k] = round(g[k], 2)
        g["peso"] = round(g["peso"], 1)
        lista_telhas.append(g)

    # totais por categoria
    por_cat: Dict[str, dict] = collections.OrderedDict((k, {"categoria": k, "titulo": v, "posicoes": 0, "pecas": 0, "peso": 0.0})
                                                       for k, v in CATEGORIAS.items())
    # pelas linhas da lista, que é o que se compra e se fabrica: as telhas multi-dobra, o
    # complemento e a cumeeira entram (as facetas que elas consomem, não), com o peso de
    # compra das telhas — o total bate com a soma da coluna do quadro de posições
    for li in linhas:
        c = por_cat.setdefault(li.get("categoria") or "OUTROS", {"categoria": "OUTROS", "titulo": "Outros", "posicoes": 0, "pecas": 0, "peso": 0.0})
        c["posicoes"] += 1
        c["pecas"] += li["quantidade"]
        c["peso"] += li["peso_total"]
    peso_total = sum(li["peso_total"] for li in linhas)
    categorias_lista = []
    for c in por_cat.values():
        if not c["pecas"]:
            continue
        c["peso"] = round(c["peso"], 1)
        c["pct"] = round(100.0 * c["peso"] / peso_total, 1) if peso_total else 0.0
        categorias_lista.append(c)

    conjuntos = _conjuntos(pecas or [], por_marca, nomes_conjuntos)
    ressalvas = [{"marca": p.marca, "perfil": p.perfil, "observacoes": list(p.observacoes)} for p in lista if p.observacoes]
    return {
        "gerado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "projeto": dict(projeto or {}),
        "barra": barra or 0,
        "totais": {"posicoes": len(linhas), "pecas": sum(li["quantidade"] for li in linhas),
                   "peso": round(peso_total, 1), "conjuntos": len(conjuntos),
                   "acessorios": sum(acessorios.values()) if acessorios else 0,
                   "categorias": categorias_lista},
        "posicoes": linhas, "perfis": lista_perfis, "chapas": lista_chapas, "telhas": lista_telhas,
        "dobrados": dobrados,
        "conjuntos": conjuntos,
        "acessorios": [{"nome": k, "quantidade": v} for k, v in sorted((acessorios or {}).items())],
        "ressalvas": ressalvas,
    }


# ============================================================ arquivos

def _csv(caminho: str, colunas: Sequence[str], linhas: Sequence[Sequence]) -> str:
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\r\n")
        w.writerow(colunas)
        for linha in linhas:
            w.writerow(linha)
    return caminho


def _num_csv(x, casas=2) -> str:
    return ("%.*f" % (casas, x)).replace(".", ",")


def gravar_romaneio_da_lista(caminho: str, lista: dict) -> str:
    """O romaneio em CSV com as MESMAS linhas da lista impressa: a telha multi-dobra (TMD),
    o complemento e a cumeeira entram como na lista, as telhas no comprimento de compra, e
    as facetas das multi-dobras não aparecem soltas (antes o CSV saía das posições cruas:
    832 telhas soltas, sem TMD/CM, com o peso do modelo)."""
    linhas = []
    for li in lista.get("posicoes") or []:
        linhas.append([li.get("nome", ""), li.get("marca", ""), " ".join(li.get("conjuntos") or []),
                       li.get("classe", ""), li.get("perfil", ""), li.get("material", ""), li.get("quantidade", 0),
                       li.get("comprimento") or "", li.get("largura") or "", _num_csv(li["espessura"], 1) if li.get("espessura") else "",
                       li.get("furos", ""), li.get("parafusos", ""), _num_csv(li.get("peso") or 0.0, 3),
                       _num_csv(li.get("peso_total") or 0.0, 2), "; ".join(li.get("observacoes") or [])])
    for a in lista.get("acessorios") or []:
        linhas.append(["", "", "", "Acessório", a["nome"], "", a["quantidade"], "", "", "", "", "", "", "", "só na lista"])
    return _csv(caminho, ["Nome", "Posicao", "Conjuntos", "Tipo", "Perfil / chapa", "Material", "Qtd",
                          "Comprimento (mm)", "Largura (mm)", "Espessura (mm)", "Furos", "Parafusos",
                          "Peso unit (kg)", "Peso total (kg)", "Observacoes"], linhas)


def gravar(pasta: str, lista: dict, posicoes: Sequence[Posicao], acessorios: Dict[str, int]) -> dict:
    """JSON, CSVs e HTML em `pasta`. Devolve {nome: caminho}."""
    from projetos import _gravar_json
    os.makedirs(pasta, exist_ok=True)
    arquivos = {}
    caminho = os.path.join(pasta, ARQUIVO_JSON)
    _gravar_json(caminho, lista, indent=1)             # temporário + troca: a tela nunca lê meio arquivo
    arquivos["json"] = caminho
    arquivos["romaneio"] = gravar_romaneio_da_lista(os.path.join(pasta, "romaneio.csv"), lista)
    arquivos["perfis"] = _csv(os.path.join(pasta, "resumo-perfis.csv"),
                              ["Perfil", "Material", "Categoria", "Posicoes", "Pecas", "Comprimento total (m)", "kg/m",
                               "Peso (kg)", "Barra comercial (m)", "Barras", "Aproveitamento (%)", "Sobra (m)", "Pecas com emenda"],
                              [[g["perfil"], g["material"], g["categoria"], " ".join(g["posicoes"]), g["pecas"],
                                _num_csv(g["comprimento_m"]), _num_csv(g["kg_m"], 3), _num_csv(g["peso"], 1),
                                _num_csv(g["barras"]["comprimento"] / 1000.0, 0), g["barras"]["quantidade"],
                                _num_csv(g["barras"]["aproveitamento"], 1), _num_csv(g["barras"]["sobra_m"]), g["barras"]["emendas"]]
                               for g in lista["perfis"]])
    dob = (lista.get("dobrados") or {}).get("linhas") or []
    if dob:
        arquivos["dobras"] = _csv(os.path.join(pasta, "peso-dobras.csv"),
                                  ["Perfil", "Material", "Pecas", "Comprimento total (m)", "Espessura (mm)", "Dobras",
                                   "Soma externa (mm)", "Desenvolvido (mm)", "kg/m teorico", "kg/m com desconto", "kg/m NBR 6355",
                                   "Peso do modelo (kg)", "Peso teorico (kg)", "Peso com desconto (kg)", "Diferenca (kg)", "Diferenca (%)"],
                                  [[d["perfil"], d["material"], d["pecas"], _num_csv(d["comprimento_m"]), _num_csv(d["t"]), d["dobras"],
                                    _num_csv(d["soma_externa"], 1), _num_csv(d["desenvolvido"], 1), _num_csv(d["kg_m_teorico"], 3),
                                    _num_csv(d["kg_m_desconto"], 3), _num_csv(d["kg_m_norma"], 3) if d["kg_m_norma"] else "",
                                    _num_csv(d["peso_modelo"], 1), _num_csv(d["peso_teorico"], 1), _num_csv(d["peso_desconto"], 1),
                                    _num_csv(d["diferenca"], 1), _num_csv(d["diferenca_pct"], 2)] for d in dob])
    arquivos["chapas"] = _csv(os.path.join(pasta, "resumo-chapas.csv"),
                              ["Espessura (mm)", "Material", "Posicoes", "Pecas", "Area (m2)", "Peso (kg)"],
                              [[_num_csv(g["espessura"], 1), g["material"], " ".join(g["posicoes"]), g["pecas"],
                                _num_csv(g["area_m2"]), _num_csv(g["peso"], 1)] for g in lista["chapas"]])
    arquivos["conjuntos"] = _csv(os.path.join(pasta, "conjuntos.csv"),
                                 ["Nome", "Conjunto", "Categoria", "Instancias", "Pecas por unidade", "Composicao",
                                  "Peso unitario (kg)", "Peso total (kg)"],
                                 [[c.get("nome", ""), c["marca"], c["categoria"], c["instancias"], c["pecas_unidade"], c["composicao_texto"],
                                   _num_csv(c["peso_unitario"]), _num_csv(c["peso_total"])] for c in lista["conjuntos"]])
    if lista.get("pre_moldados"):
        arquivos["pre_moldados"] = _csv(os.path.join(pasta, "pre-moldados.csv"),
                                        ["Nome", "Material", "Categoria", "Tipo IFC", "Pecas", "Volume (m3)",
                                         "Massa especifica (kg/m3)", "Peso (kg)"],
                                        [[g["nome"], g["material"], g["categoria"], g.get("tipo_ifc", ""), g["quantidade"],
                                          _num_csv(g["volume_m3"], 3), _num_csv(g["massa_especifica"], 0),
                                          _num_csv(g["peso_kg"], 1)] for g in lista["pre_moldados"]])
    if lista.get("estrutura_a_conferir"):
        arquivos["estrutura_a_conferir"] = _csv(os.path.join(pasta, "estrutura-a-conferir.csv"),
                                                ["Tipo", "Secao medida (mm)", "kg/m medido", "Comprimento (mm)", "Pecas",
                                                 "Peso (kg)", "Origem (malha do IFC)"],
                                                [[g["tipo"], g["secao"], _num_csv(g["kg_m"], 1) if g["kg_m"] is not None else "malha aberta",
                                                  g["comprimento"], g["quantidade"],
                                                  _num_csv(g["peso_kg"], 1) if g["peso_kg"] is not None else "", g["origem"]]
                                                 for g in lista["estrutura_a_conferir"]])
    caminho = os.path.join(pasta, ARQUIVO_HTML)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(documento_html(lista))
    arquivos["html"] = caminho
    return arquivos


# ============================================================ HTML e PDF

def _tabela(titulo: str, colunas: Sequence, linhas: Sequence[Sequence], rodape: Optional[Sequence] = None,
            larguras: Optional[Sequence[str]] = None, classes: str = "tab small") -> str:
    """Tabela no padrão do memorial: célula = (valor, classes css) ou valor simples."""
    def celula(c, tag="td"):
        if isinstance(c, tuple):
            v, cls = c
        else:
            v, cls = c, ("r" if isinstance(c, (int, float)) else "l")
        return "<%s class=\"%s\">%s</%s>" % (tag, cls, _esc(v), tag)
    cols = "".join("<col style=\"width:%s\">" % w for w in larguras) if larguras else ""
    th = "".join(celula(c, "th") for c in colunas)
    corpo = "".join("<tr>" + "".join(celula(c) for c in linha) + "</tr>" for linha in linhas)
    pe = ("<tfoot><tr>" + "".join(celula(c) for c in rodape) + "</tr></tfoot>") if rodape else ""
    return ("<table class=\"%s\">" % classes + ("<caption>%s</caption>" % _esc(titulo) if titulo else "")
            + ("<colgroup>%s</colgroup>" % cols if cols else "") + "<thead><tr>%s</tr></thead><tbody>%s</tbody>%s</table>" % (th, corpo, pe))


def _cabecalho_html(lista: dict) -> str:
    p = lista.get("projeto") or {}
    t = lista.get("totais") or {}
    from versao import identificacao
    quando = lista.get("gerado", "")
    try:
        quando = datetime.strptime(quando, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        pass
    linhas = [("Obra", p.get("nome") or "—", "Cliente", p.get("cliente") or "—"),
              ("Local", p.get("local") or "—", "Responsável", p.get("responsavel") or "—"),
              ("Origem", p.get("origem_ifc") or "modelo do projeto", "Gerado em", quando),
              ("Peças", "%s peças em %s posições, %s conjuntos" % (_n(t.get("pecas", 0)), _n(t.get("posicoes", 0)), _n(t.get("conjuntos", 0))),
               "Peso total", "%s kg" % _n(t.get("peso", 0), 1))]
    trs = "".join("<tr><td class=\"l b\" style=\"width:14%%\">%s</td><td class=\"l\">%s</td>"
                  "<td class=\"l b\" style=\"width:14%%\">%s</td><td class=\"l\">%s</td></tr>" % tuple(_esc(x) for x in li)
                  for li in linhas)
    return ("<div class=\"cabdoc\"><h1 class=\"cap\"><span class=\"tit\">Lista de materiais</span></h1>"
            "<table class=\"tab auto\" style=\"font-size:9pt\"><tbody>%s</tbody></table>"
            "<p class=\"pequeno\">%s · quantidades do modelo IFC importado; pesos pelo volume das peças (7.850 kg/m³).</p></div>"
            % (trs, _esc(identificacao())))


def corpo_html(lista: dict) -> str:
    """Os quadros da lista (sem <html>): o mesmo HTML vai para a impressão e para o PDF."""
    partes = [_cabecalho_html(lista)]
    t = lista["totais"]
    partes.append(_tabela("Quadro 1 — Totais por categoria",
                          [("Categoria", "l"), ("Posições", "c"), ("Peças", "c"), ("Peso (kg)", "r"), ("% do peso", "c")],
                          [[(c["titulo"], "l"), (c["posicoes"], "c"), (c["pecas"], "c"), (_n(c["peso"], 1), "r"), (_n(c["pct"], 1), "c")]
                           for c in t["categorias"]],
                          rodape=[("TOTAL", "l b"), (_n(t["posicoes"]), "c b"), (_n(t["pecas"]), "c b"), (_n(t["peso"], 1), "r b"), ("100,0", "c b")],
                          larguras=["44%", "14%", "14%", "14%", "14%"]))
    if lista["perfis"]:
        partes.append(_tabela("Quadro 2 — Perfis: comprimento, peso e barras comerciais (encaixe estimado, perda de corte %s mm)" % _n(PERDA_CORTE),
                              [("Perfil", "l"), ("Material", "l"), ("Posições", "l"), ("Peças", "c"), ("Compr. (m)", "r"), ("kg/m", "r"),
                               ("Peso (kg)", "r"), ("Barra", "c"), ("Barras", "c"), ("Aprov. (%)", "c"), ("Emendas", "c")],
                              [[(g["perfil"], "l b"), (g["material"], "l"), (" ".join(g["posicoes"]), "l"), (g["pecas"], "c"),
                                (_n(g["comprimento_m"], 2), "r"), (_n(g["kg_m"], 2), "r"), (_n(g["peso"], 1), "r b"),
                                ("%s m" % _n(g["barras"]["comprimento"] / 1000.0), "c"), (g["barras"]["quantidade"], "c b"),
                                (_n(g["barras"]["aproveitamento"], 1), "c"), (g["barras"]["emendas"] or "—", "c")] for g in lista["perfis"]],
                              rodape=[("TOTAL", "l b"), ("", "l"), ("", "l"), (_n(sum(g["pecas"] for g in lista["perfis"])), "c b"),
                                      (_n(sum(g["comprimento_m"] for g in lista["perfis"]), 2), "r b"), ("", "r"),
                                      (_n(sum(g["peso"] for g in lista["perfis"]), 1), "r b"), ("", "c"),
                                      (_n(sum(g["barras"]["quantidade"] for g in lista["perfis"])), "c b"), ("", "c"), ("", "c")],
                              larguras=["15%", "10%", "23%", "6%", "8%", "6%", "8%", "6%", "6%", "6%", "6%"]))
    dob = lista.get("dobrados") or {}
    if dob.get("linhas"):
        td = dob["totais"]
        partes.append(_tabela("Perfis dobrados — peso teórico × com desconto das dobras (%s)" % dob.get("regra", ""),
                              [("Perfil", "l"), ("Peças", "c"), ("Compr. (m)", "r"), ("Dobras", "c"), ("Soma ext. (mm)", "r"),
                               ("Desenv. (mm)", "r"), ("kg/m teórico", "r"), ("kg/m c/ desc.", "r"), ("kg/m NBR", "r"),
                               ("Peso modelo (kg)", "r"), ("Peso teórico (kg)", "r"), ("Peso c/ desc. (kg)", "r"), ("Dif. (kg)", "r"), ("Dif. (%)", "c")],
                              [[(d["perfil"], "l b"), (d["pecas"], "c"), (_n(d["comprimento_m"], 2), "r"), (d["dobras"], "c"),
                                (_n(d["soma_externa"], 1), "r"), (_n(d["desenvolvido"], 1), "r b"), (_n(d["kg_m_teorico"], 3), "r"),
                                (_n(d["kg_m_desconto"], 3), "r"), (_n(d["kg_m_norma"], 2) if d["kg_m_norma"] else "—", "r"),
                                (_n(d["peso_modelo"], 1), "r"), (_n(d["peso_teorico"], 1), "r"), (_n(d["peso_desconto"], 1), "r b"),
                                (_n(d["diferenca"], 1), "r"), (_n(d["diferenca_pct"], 1), "c")] for d in dob["linhas"]],
                              rodape=[("TOTAL", "l b"), ("", "c"), ("", "r"), ("", "c"), ("", "r"), ("", "r"), ("", "r"), ("", "r"), ("", "r"),
                                      (_n(td["peso_modelo"], 1), "r b"), (_n(td["peso_teorico"], 1), "r b"), (_n(td["peso_desconto"], 1), "r b"),
                                      (_n(td["diferenca"], 1), "r b"), (_n(td["diferenca_pct"], 1), "c b")]))
    if lista["chapas"]:
        partes.append(_tabela("Quadro 3 — Chapas por espessura e material",
                              [("Espessura (mm)", "c"), ("Material", "l"), ("Posições", "l"), ("Peças", "c"), ("Área (m²)", "r"), ("Peso (kg)", "r")],
                              [[(_n(g["espessura"], 1), "c b"), (g["material"], "l"), (" ".join(g["posicoes"]), "l"), (g["pecas"], "c"),
                                (_n(g["area_m2"], 2), "r"), (_n(g["peso"], 1), "r b")] for g in lista["chapas"]],
                              rodape=[("TOTAL", "c b"), ("", "l"), ("", "l"), (_n(sum(g["pecas"] for g in lista["chapas"])), "c b"),
                                      (_n(sum(g["area_m2"] for g in lista["chapas"]), 2), "r b"), (_n(sum(g["peso"] for g in lista["chapas"]), 1), "r b")],
                              larguras=["12%", "14%", "44%", "10%", "10%", "10%"]))
    if lista.get("telhas"):
        partes.append(_tabela("Quadro 4 — Telhas (chapas inteiras de compra; cortes em obra)",
                              [("Perfil", "l"), ("Chapas (qtd × compr. mm)", "l"), ("Peças", "c"), ("Compr. (m)", "r"), ("Área (m²)", "r"), ("Peso (kg)", "r")],
                              [[(g["perfil"] + (" · larg. %d (útil %d)" % (g.get("largura_total", g["largura"]), g["largura"]) if g.get("largura") else ""), "l b"), (g.get("chapas_texto", ""), "l"),
                                (g["pecas"], "c"), (_n(g["comprimento_m"], 2), "r"),
                                (_n(g["area_m2"], 2), "r"), (_n(g["peso"], 1), "r")] for g in lista["telhas"]]))
    if lista["conjuntos"]:
        partes.append(_tabela("Quadro 5 — Conjuntos (montagens): instâncias, composição e peso",
                              [("Nome", "l"), ("Conjunto", "l"), ("Tipo", "l"), ("Instâncias", "c"), ("Peças/un.", "c"), ("Composição", "l"),
                               ("Peso un. (kg)", "r"), ("Peso total (kg)", "r")],
                              [[(c.get("nome") or "—", "l b"), (c["marca"], "l"), ("Tesoura/pórtico" if c["categoria"] == "TESOURAS" else "Conjunto", "l"),
                                (c["instancias"], "c"), (c["pecas_unidade"], "c"), (c["composicao_texto"], "l"),
                                (_n(c["peso_unitario"], 1), "r"), (_n(c["peso_total"], 1), "r b")] for c in lista["conjuntos"]],
                              larguras=["8%", "8%", "11%", "8%", "8%", "37%", "10%", "10%"]))
    partes.append(_tabela("Quadro 6 — Romaneio por posição",
                          [("Nome", "l"), ("Posição", "l"), ("Tipo", "l"), ("Perfil / chapa", "l"), ("Material", "l"), ("Qtd", "c"), ("Compr. (mm)", "r"),
                           ("Larg. (mm)", "r"), ("Esp. (mm)", "r"), ("Furos", "l"), ("Parafusos", "l"), ("Peso un. (kg)", "r"), ("Peso tot. (kg)", "r"), ("Conjuntos", "l")],
                          [[(p.get("nome") or "—", "l b"), (p["marca"], "l"), (p["classe"], "l"), (p["perfil"], "l"), (p["material"], "l"), (p["quantidade"], "c"),
                            (_n(p["comprimento"]) if p["comprimento"] else "—", "r"), (_n(p["largura"]) if p["largura"] else "—", "r"),
                            (_n(p["espessura"], 1) if p["espessura"] else "—", "r"), (p["furos"] or "—", "l"), (p.get("parafusos") or "—", "l"),
                            (_n(p["peso"], 2), "r"), (_n(p["peso_total"], 1), "r b"), (" ".join(p["conjuntos"][:12]) + (" …" if len(p["conjuntos"]) > 12 else ""), "l")]
                           for p in lista["posicoes"]],
                          rodape=[("TOTAL", "l b"), ("", "l"), ("", "l"), ("", "l"), ("", "l"), (_n(t["pecas"]), "c b"), ("", "r"), ("", "r"), ("", "r"), ("", "l"), ("", "l"),
                                  ("", "r"), (_n(t["peso"], 1), "r b"), ("", "l")],
                          larguras=["6%", "5%", "6%", "12%", "7%", "4%", "6%", "5%", "5%", "10%", "9%", "6%", "6%", "13%"]))
    if lista["acessorios"]:
        partes.append(_tabela("Quadro 7 — Acessórios (só na lista: parafusos, porcas, arruelas)",
                              [("Item", "l"), ("Quantidade", "c")],
                              [[(a["nome"], "l"), (a["quantidade"], "c")] for a in lista["acessorios"]],
                              larguras=["70%", "30%"]))
    pm = lista.get("pre_moldados") or []
    if pm:
        partes.append(_tabela("Quadro 8 — Fora do aço: pré-moldado e outros materiais (volume da malha do IFC)",
                              [("Nome", "l"), ("Material", "l"), ("Peças", "c"), ("Volume (m³)", "r"), ("kg/m³", "r"), ("Peso (kg)", "r")],
                              [[(g["nome"], "l b"), (g["material"], "l"), (g["quantidade"], "c"), (_n(g["volume_m3"], 3), "r"),
                                (_n(g["massa_especifica"]), "r"), (_n(g["peso_kg"], 1), "r b")] for g in pm],
                              rodape=[("TOTAL", "l b"), ("", "l"), (_n(sum(g["quantidade"] for g in pm)), "c b"),
                                      (_n(sum(g["volume_m3"] for g in pm), 3), "r b"), ("", "r"),
                                      (_n(sum(g["peso_kg"] for g in pm), 1), "r b")],
                              larguras=["26%", "26%", "10%", "13%", "10%", "15%"]))
    ec = lista.get("estrutura_a_conferir") or []
    if ec:
        partes.append(_tabela("Quadro 9 — Estrutura de aço a conferir (malhas sem peças separadas: seção e comprimento medidos, "
                              "sem o perfil; fora dos totais acima)",
                              [("Tipo", "l"), ("Seção (mm)", "c"), ("kg/m", "r"), ("Compr. (mm)", "r"), ("Peças", "c"), ("Peso (kg)", "r")],
                              [[(g["tipo"], "l"), (g["secao"], "c b"),
                                (_n(g["kg_m"], 1) if g["kg_m"] is not None else "malha aberta", "r"), (_n(g["comprimento"]), "r"),
                                (g["quantidade"], "c"), (_n(g["peso_kg"], 1) if g["peso_kg"] is not None else "—", "r b")] for g in ec],
                              rodape=[("TOTAL medido", "l b"), ("", "c"), ("", "r"), ("", "r"), (_n(sum(g["quantidade"] for g in ec)), "c b"),
                                      (_n(sum(g["peso_kg"] or 0.0 for g in ec), 1), "r b")],
                              larguras=["30%", "16%", "12%", "14%", "12%", "16%"]))
    if lista["ressalvas"]:
        itens = "".join("<li><b>%s</b> %s — %s</li>" % (_esc(r["marca"]), _esc(r["perfil"]), _esc("; ".join(r["observacoes"]))) for r in lista["ressalvas"])
        partes.append("<p class=\"pequeno\"><b>Observações do detalhamento</b> (conferir antes de mandar cortar)</p><ul class=\"pequeno\">%s</ul>" % itens)
    return "\n".join(partes)


def _css() -> str:
    return open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "memorial.css"), encoding="utf-8").read()


def _css_extra(lista: dict) -> str:
    obra = _esc((lista.get("projeto") or {}).get("nome") or "")
    return """
.cabdoc .tit { string-set: capitulo content() }
@page {
  size: A4 landscape;
  @top-left { content: "%s" }
  @bottom-left { content: "Lista de materiais — quantidades do modelo IFC; pesos pelo volume das peças." }
  @bottom-right { content: counter(page) }
}
""" % obra


def documento_html(lista: dict) -> str:
    """HTML completo, sem paginador: abre no navegador e imprime pelo próprio Chrome."""
    titulo = "Lista de materiais — %s" % ((lista.get("projeto") or {}).get("nome") or "")
    return ("<!DOCTYPE html>\n<html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><title>%s</title>"
            "<style>%s%s\nbody.lista { margin: 12mm auto; max-width: 270mm; padding: 0 8mm; }</style></head>"
            "<body class=\"lista\"><div class=\"lista-doc\">%s</div></body></html>"
            % (_esc(titulo), _css(), _css_extra(lista), corpo_html(lista)))


def gerar_pdf(pasta: str, lista: dict) -> str:
    """PDF em `pasta`, paginado pelo Chrome (como o memorial)."""
    from saida import printpdf
    doc = printpdf.envelope("<div class=\"lista-doc\">%s</div>" % corpo_html(lista), _css(),
                            "Lista de materiais — %s" % ((lista.get("projeto") or {}).get("nome") or ""))
    doc = doc.replace("<body>", "<body class=\"lista\">").replace("</style>", _css_extra(lista) + "</style>")
    html_path = os.path.join(pasta, "lista-de-materiais.paginado.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(doc)
    pdf_path = os.path.join(pasta, ARQUIVO_PDF)
    printpdf.imprimir(html_path, pdf_path, verbose=False)
    try:
        os.remove(html_path)
    except OSError:
        pass
    return os.path.abspath(pdf_path)
