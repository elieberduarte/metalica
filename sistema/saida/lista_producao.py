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

from saida.detalhamento import Posicao, CLASSES, _ordenar, gravar_romaneio

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


def _linha_posicao(p: Posicao, categoria: str) -> dict:
    chapa = _e_chapa(p)
    return {"marca": p.marca, "nome": getattr(p, "nome", ""), "categoria": categoria, "classe": CLASSES.get(p.classe, p.classe),
            "perfil": p.perfil, "material": p.material, "quantidade": p.quantidade,
            "comprimento": round(p.comprimento) if p.classe != "indefinida" else 0,
            "largura": round(p.desenvolvimento[0] if p.desenvolvimento else p.H) if chapa or p.classe == "telha" else 0,
            "espessura": round(p.espessura or p.T, 1) if chapa else 0,
            "area_m2": round(_area_m2(p) * p.quantidade, 3) if chapa or p.classe == "telha" else 0,
            "furos": p.rotulo_furos(), "peso": round(p.peso, 3), "peso_total": round(p.peso_total, 2),
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
    saida = []
    for conj, total in por_conj.items():
        n = 0
        for q in total.values():
            n = math.gcd(n, q)
        n = max(n, 1)
        unidade = {k: q // n for k, q in total.items()}
        if sum(unidade.values()) < 2:
            continue
        if all(por_marca.get(k) is not None and por_marca[k].classe == "telha" for k in unidade):
            continue
        peso = sum(q * (por_marca[k].peso if k in por_marca else 0.0) for k, q in unidade.items())
        barras = sum(q for k, q in unidade.items() if k in por_marca and por_marca[k].classe.startswith("barra"))
        comp = sorted(unidade.items(), key=lambda kv: _ordem_natural(kv[0]))
        saida.append({"marca": conj, "nome": (nomes or {}).get(conj, ""), "instancias": n, "pecas_unidade": sum(unidade.values()),
                      "composicao": dict(comp),
                      "composicao_texto": ", ".join("%d× %s" % (q, k) for k, q in comp),
                      "peso_unitario": round(peso, 2), "peso_total": round(peso * n, 2),
                      "categoria": "TESOURAS" if barras >= 8 else "CONJUNTOS"})
    saida.sort(key=lambda c: (-c["peso_total"], _ordem_natural(c["marca"])))
    return saida


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
    linhas = [_linha_posicao(p, categorias.get(p.marca, "OUTROS")) for p in lista]

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
                                         "comprimento_m": 0.0, "area_m2": 0.0, "peso": 0.0})
        g["posicoes"].append(p.marca)
        g["pecas"] += p.quantidade
        g["comprimento_m"] += p.comprimento * p.quantidade / 1000.0
        g["area_m2"] += _area_m2(p) * p.quantidade
        g["peso"] += p.peso_total
    lista_telhas = []
    for g in telhas.values():
        for k in ("comprimento_m", "area_m2"):
            g[k] = round(g[k], 2)
        g["peso"] = round(g["peso"], 1)
        lista_telhas.append(g)

    # totais por categoria
    por_cat: Dict[str, dict] = collections.OrderedDict((k, {"categoria": k, "titulo": v, "posicoes": 0, "pecas": 0, "peso": 0.0})
                                                       for k, v in CATEGORIAS.items())
    for p in lista:
        c = por_cat.setdefault(categorias.get(p.marca, "OUTROS"), {"categoria": "OUTROS", "titulo": "Outros", "posicoes": 0, "pecas": 0, "peso": 0.0})
        c["posicoes"] += 1
        c["pecas"] += p.quantidade
        c["peso"] += p.peso_total
    peso_total = sum(p.peso_total for p in lista)
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
        "totais": {"posicoes": len(lista), "pecas": sum(p.quantidade for p in lista),
                   "peso": round(peso_total, 1), "conjuntos": len(conjuntos),
                   "acessorios": sum(acessorios.values()) if acessorios else 0,
                   "categorias": categorias_lista},
        "posicoes": linhas, "perfis": lista_perfis, "chapas": lista_chapas, "telhas": lista_telhas,
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


def gravar(pasta: str, lista: dict, posicoes: Sequence[Posicao], acessorios: Dict[str, int]) -> dict:
    """JSON, CSVs e HTML em `pasta`. Devolve {nome: caminho}."""
    import json
    os.makedirs(pasta, exist_ok=True)
    arquivos = {}
    caminho = os.path.join(pasta, ARQUIVO_JSON)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    arquivos["json"] = caminho
    arquivos["romaneio"] = gravar_romaneio(os.path.join(pasta, "romaneio.csv"), posicoes, acessorios)
    arquivos["perfis"] = _csv(os.path.join(pasta, "resumo-perfis.csv"),
                              ["Perfil", "Material", "Categoria", "Posicoes", "Pecas", "Comprimento total (m)", "kg/m",
                               "Peso (kg)", "Barra comercial (m)", "Barras", "Aproveitamento (%)", "Sobra (m)", "Pecas com emenda"],
                              [[g["perfil"], g["material"], g["categoria"], " ".join(g["posicoes"]), g["pecas"],
                                _num_csv(g["comprimento_m"]), _num_csv(g["kg_m"], 3), _num_csv(g["peso"], 1),
                                _num_csv(g["barras"]["comprimento"] / 1000.0, 0), g["barras"]["quantidade"],
                                _num_csv(g["barras"]["aproveitamento"], 1), _num_csv(g["barras"]["sobra_m"]), g["barras"]["emendas"]]
                               for g in lista["perfis"]])
    arquivos["chapas"] = _csv(os.path.join(pasta, "resumo-chapas.csv"),
                              ["Espessura (mm)", "Material", "Posicoes", "Pecas", "Area (m2)", "Peso (kg)"],
                              [[_num_csv(g["espessura"], 1), g["material"], " ".join(g["posicoes"]), g["pecas"],
                                _num_csv(g["area_m2"]), _num_csv(g["peso"], 1)] for g in lista["chapas"]])
    arquivos["conjuntos"] = _csv(os.path.join(pasta, "conjuntos.csv"),
                                 ["Nome", "Conjunto", "Categoria", "Instancias", "Pecas por unidade", "Composicao",
                                  "Peso unitario (kg)", "Peso total (kg)"],
                                 [[c.get("nome", ""), c["marca"], c["categoria"], c["instancias"], c["pecas_unidade"], c["composicao_texto"],
                                   _num_csv(c["peso_unitario"]), _num_csv(c["peso_total"])] for c in lista["conjuntos"]])
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
    if lista["chapas"]:
        partes.append(_tabela("Quadro 3 — Chapas por espessura e material",
                              [("Espessura (mm)", "c"), ("Material", "l"), ("Posições", "l"), ("Peças", "c"), ("Área (m²)", "r"), ("Peso (kg)", "r")],
                              [[(_n(g["espessura"], 1), "c b"), (g["material"], "l"), (" ".join(g["posicoes"]), "l"), (g["pecas"], "c"),
                                (_n(g["area_m2"], 2), "r"), (_n(g["peso"], 1), "r b")] for g in lista["chapas"]],
                              rodape=[("TOTAL", "c b"), ("", "l"), ("", "l"), (_n(sum(g["pecas"] for g in lista["chapas"])), "c b"),
                                      (_n(sum(g["area_m2"] for g in lista["chapas"]), 2), "r b"), (_n(sum(g["peso"] for g in lista["chapas"]), 1), "r b")],
                              larguras=["12%", "14%", "44%", "10%", "10%", "10%"]))
    if lista.get("telhas"):
        partes.append(_tabela("Quadro 4 — Telhas",
                              [("Perfil", "l"), ("Posições", "l"), ("Peças", "c"), ("Compr. (m)", "r"), ("Área (m²)", "r"), ("Peso (kg)", "r")],
                              [[(g["perfil"], "l b"), (" ".join(g["posicoes"]), "l"), (g["pecas"], "c"), (_n(g["comprimento_m"], 2), "r"),
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
                           ("Larg. (mm)", "r"), ("Esp. (mm)", "r"), ("Furos", "l"), ("Peso un. (kg)", "r"), ("Peso tot. (kg)", "r"), ("Conjuntos", "l")],
                          [[(p.get("nome") or "—", "l b"), (p["marca"], "l"), (p["classe"], "l"), (p["perfil"], "l"), (p["material"], "l"), (p["quantidade"], "c"),
                            (_n(p["comprimento"]) if p["comprimento"] else "—", "r"), (_n(p["largura"]) if p["largura"] else "—", "r"),
                            (_n(p["espessura"], 1) if p["espessura"] else "—", "r"), (p["furos"] or "—", "l"),
                            (_n(p["peso"], 2), "r"), (_n(p["peso_total"], 1), "r b"), (" ".join(p["conjuntos"][:12]) + (" …" if len(p["conjuntos"]) > 12 else ""), "l")]
                           for p in lista["posicoes"]],
                          rodape=[("TOTAL", "l b"), ("", "l"), ("", "l"), ("", "l"), ("", "l"), (_n(t["pecas"]), "c b"), ("", "r"), ("", "r"), ("", "r"), ("", "l"),
                                  ("", "r"), (_n(t["peso"], 1), "r b"), ("", "l")],
                          larguras=["6%", "5%", "6%", "13%", "8%", "4%", "7%", "6%", "5%", "11%", "6%", "6%", "17%"]))
    if lista["acessorios"]:
        partes.append(_tabela("Quadro 7 — Acessórios (só na lista: parafusos, porcas, arruelas)",
                              [("Item", "l"), ("Quantidade", "c")],
                              [[(a["nome"], "l"), (a["quantidade"], "c")] for a in lista["acessorios"]],
                              larguras=["70%", "30%"]))
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
