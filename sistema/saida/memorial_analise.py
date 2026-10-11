# -*- coding: utf-8 -*-
"""Memorial da análise estrutural e o quadro de comparação com o engenheiro (etapa 6, 11/10/2026).

O memorial é o resultado gravado da análise (`analise_estrutural.json`, nucleo3d/analise_estrutural.py) escrito para quem
confere: premissas, cargas e vento, combinações, 2ª ordem, deslocamentos de serviço, a verificação das peças (o ranking e
a conta da peça que governa cada grupo, a mesma da tela), reações, bases pela NBR 8800:2024 6.7, apoio das tesouras,
ligações e os apontamentos. Nada é recalculado aqui: o que sai é o que a tela mostra.

O quadro de comparação (pedido de 06/10: o mesmo projeto calculado por um engenheiro estrutural — a Cobertura Quadra
Kaefer) põe os números dele ao lado dos nossos, na ordem em que se confere um cálculo: cargas totais por caso, reações,
esforços em pilares e vigas, peças, bases e deslocamentos. Os números dele ficam em `<projeto>/analise/comparacao.json`
(digitados na tela da análise); a diferença é (nosso − dele) / dele.
"""
import html
import json
import math
import os
import time
from typing import Dict, List, Optional

TF = 9.80665                       # kN por tf
ARQ_COMPARACAO = os.path.join("analise", "comparacao.json")

PAPEL = {"pilar": "pilar", "viga": "viga", "banzo_sup": "banzo superior", "banzo_inf": "banzo inferior",
         "montante": "montante", "diagonal": "diagonal", "terça": "terça", "terca": "terça",
         "contraventamento": "contraventamento", "banzo": "banzo"}


def _esc(t) -> str:
    return html.escape(str(t if t is not None else ""))


def _n(x, c=1) -> str:
    """número no formato brasileiro (milhar com ponto, decimal com vírgula); "—" sem valor"""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    s = ("%." + str(c) + "f") % float(x)
    i, _, d = s.partition(".")
    neg = i.startswith("-")
    i = i.lstrip("-")
    g = []
    while len(i) > 3:
        g.insert(0, i[-3:])
        i = i[:-3]
    g.insert(0, i)
    r = ".".join(g) + ("," + d if d else "")
    return ("−" if neg and float(s) != 0 else "") + r


def _pct(u, c=0) -> str:
    return "—" if u is None else ("≥ 999%" if u >= 9.99 else _n(u * 100, c) + "%")


def _papel(p) -> str:
    return PAPEL.get(p, p or "—")


def _grupo_legivel(chave: str) -> str:
    f, _, perfil = str(chave).partition("|")
    return "%s · %s" % (_papel(f), perfil)


def _ok(v) -> str:
    return "<span class=ok>ok</span>" if v else "<span class=ruim>não passa</span>"


def _tab(cab: List[str], linhas: List[List[str]], cls: str = "", esquerda: int = 1) -> str:
    """tabela simples: as `esquerda` primeiras colunas alinhadas à esquerda"""
    th = "".join("<th%s>%s</th>" % (" class=l" if k < esquerda else "", h) for k, h in enumerate(cab))
    tr = "".join("<tr>%s</tr>" % "".join("<td%s>%s</td>" % (" class=l" if k < esquerda else "", c)
                                         for k, c in enumerate(ln)) for ln in linhas)
    return "<table%s><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
        " class=%s" % cls if cls else "", th, tr)


def _kv(pares) -> str:
    """tabela de duas colunas (rótulo, valor)"""
    rot = lambda a: ("<span class=rec>%s</span>" % a[2:]) if a.startswith("  ") else a      # "  " = subitem do de cima
    return "<table class=kv>%s</table>" % "".join("<tr><td class=l>%s</td><td class=l>%s</td></tr>" % (rot(a), b)
                                                  for a, b in pares if b not in (None, ""))


# ------------------------------------------------------------------ onde fica cada base
def nome_da_base(chave: str, eixos: Optional[List[dict]] = None) -> str:
    """'B/7' pelos eixos do projeto; sem eixos, 'x 18,60; y −5,74 m' (a chave é 'x,y' em mm)"""
    try:
        x, y = (float(v) for v in str(chave).split(","))
    except ValueError:
        return str(chave)
    if eixos:
        from saida.planta_cargas import eixos_do_ponto
        return "eixo " + eixos_do_ponto(eixos, x, y)
    return "x %s; y %s m" % (_n(x / 1000, 2), _n(y / 1000, 2))


# ------------------------------------------------------------------ premissas
def _premissas(an: dict) -> str:
    p = an.get("parametros") or {}
    pm = an.get("modelo_analise") == "premoldado"
    sim = lambda v: "sim" if v in (True, "true", "sim") else "não"
    kpa = lambda v: "%s kN/m²" % _n(v, 2)
    linhas = []

    def add(rot, chave, fmt=lambda v: _esc(v)):
        if chave in p and p[chave] not in (None, ""):
            linhas.append((rot, fmt(p[chave])))

    if pm:
        linhas.append(("Modelo", "pórtico espacial do pré-moldado (pilares engastados, vigas rotuladas nos consolos; "
                                 "concreto pela NBR 6118, 15.7.3)"))
        add("Piso: revestimento", "piso_revestimento", kpa)
        add("Piso: sobrecarga", "piso_sobrecarga", kpa)
        add("Base das colunas de aço", "base_coluna_aco")
        add("Permeabilidade (C<sub>pi</sub>)", "aberturas")
    else:
        add("Bases dos pilares", "base", lambda v: {"engastada": "engastadas", "articulada": "articuladas"}.get(v, v))
        if p.get("bases"):
            linhas.append(("  exceções", ", ".join("%s: %s" % (nome_da_base(k), v) for k, v in p["bases"].items())))
        add("Ligação viga–pilar", "viga_pilar", lambda v: {"rigida": "rígida", "rotulada": "rotulada"}.get(v, v))
        add("Tesoura no apoio", "tesoura_rotulada_no_apoio", lambda v: "rotulada" if v in (True, "true") else "contínua")
        add("Almas das treliças", "rotula_alma",
            lambda v: {"no_plano": "rotuladas no plano da treliça", "total": "rotuladas nas duas direções"}.get(v, v))
        add("Terças", "terca_rotulada", lambda v: "rotuladas onde terminam sobre a tesoura" if v in (True, "true") else "contínuas")
        add("Cargas do telhado", "cargas_pelas_tercas",
            lambda v: "chegam às tesouras pelas terças" if v in (True, "true") else "direto nos nós do banzo superior")
        add("Tesoura chumbada no pilar de concreto", "chumbada_no_pilar")
        add("Telha + terças", "telha", kpa)
        add("Permanente extra", "carga_extra", kpa)
        add("Sobrecarga", "sobrecarga", lambda v: "%s (projeção horizontal, NBR 8800 B.5.1)" % kpa(v))
        add("Travamento de hipótese", "travamento_hipotese",
            lambda v: {"auto": "só quando o modelo não tem terças", "sim": "sempre", "nao": "não"}.get(v, v))
        add("  terça / escora de hipótese", "perfil_terca_hipotese")
        add("  contravento de hipótese", "perfil_contravento_hipotese")
    add("Vento", "vento", sim)
    if p.get("vento") not in (False, "false"):
        add("  V<sub>0</sub>", "v0", lambda v: "%s m/s" % _n(v, 1))
        add("  S<sub>1</sub>", "s1", lambda v: _n(v, 2))
        add("  categoria do terreno", "categoria")
        add("  classe", "classe")
        add("  S<sub>3</sub>", "s3", lambda v: _n(v, 2))
        add("  arrasto nas barras (8.1)", "vento_nas_barras", sim)
    if p.get("cobertura_movel") in (True, "true"):
        linhas.append(("Cobertura retrátil", "%s tesouras; aberta %s m, retraída %s m (pilha na ponta %s); peso total do "
                       "fabricante %s kg; braço da sanfona %s" % (
                           p.get("movel_n"), _n(p.get("movel_comprimento_aberta"), 1),
                           _n(p.get("movel_comprimento_retraida"), 1),
                           "de Y menor" if p.get("movel_lado_retraida") == "y_menor" else "de Y maior",
                           _n(p.get("movel_peso_total_kg"), 0), _esc(p.get("perfil_sanfona")))))
    add("2ª ordem nas ELU", "segunda_ordem", lambda v: "sim (P-Δ, NBR 8800:2024, 4.10.7)" if v not in (False, "false")
        else "não (só 1ª ordem)")
    add("Aço dos tubos (verificação)", "aco_tubos", lambda v: _esc(v) or "o de cada peça no modelo")
    add("Bloco das bases: f<sub>ck</sub>", "base_fck_mpa", lambda v: "%s MPa" % _n(v, 0))
    add("Placa das bases", "base_aco_placa")
    trocas = p.get("trocas_perfil") or {}
    if trocas:
        linhas.append(("Trocas de perfil (só na análise)", "<br>".join(
            "%s → <b>%s</b>" % (_esc(_grupo_legivel(k)), _esc(v)) for k, v in trocas.items())))
    if p.get("giro_pilares"):
        linhas.append(("Pilares girados (só na análise)", "%d" % len(p["giro_pilares"])))
    r = an.get("resumo_esqueleto") or {}
    if r:
        linhas.append(("Modelo de cálculo", "%s nós e %s barras no esqueleto (as peças levadas às linhas de eixo); "
                       "%s nós e %s barras no pórtico resolvido" % (r.get("nos", "—"), r.get("barras", "—"),
                                                                     len(an.get("nos") or []), len(an.get("barras") or []))))
    return _kv(linhas)


# ------------------------------------------------------------------ cargas e vento
def _vento(an: dict) -> str:
    i = an.get("info") or {}
    v, c, mv = i.get("vento"), i.get("cobertura"), an.get("movel")
    L = []
    if mv:
        L.append("<b>Cobertura retrátil — %s</b>: %s tesouras a cada %s m em %s m; %s kg cada (peso do fabricante ÷ %s); "
                 "sanfona com %s braços; abas laterais de %s m (NBR 6123, 7.2.5.1: 1,3·q·A a barlavento, 0,8·q·A a sotavento)."
                 % ("aberta" if mv.get("configuracao") == "aberta" else "retraída", mv.get("n"), _n(mv.get("passo_m"), 3),
                    _n(mv.get("comprimento_m"), 2), _n(mv.get("peso_tesoura_kg"), 1), mv.get("n"),
                    mv.get("sanfona_barras", "—"), _n(mv.get("altura_aba_m"), 2)))
    if an.get("modelo_analise") == "premoldado":
        if c:
            L.append("Cobertura: %s m² em %s vigas pórtico." % (_n(c.get("area_m2"), 1), c.get("vigas_portico", "—")))
        if i.get("lajes"):
            L.append("Lajes: %s peças (%s kN de peso próprio) nas vigas que as apoiam, com o revestimento e a sobrecarga de piso."
                     % (i["lajes"].get("n"), _n(i["lajes"].get("peso_kN"), 0)))
        if v:
            L.append("V<sub>k</sub> = %s m/s (S<sub>2</sub> = %s, categoria %s, classe %s) · q = <b>%s kN/m²</b>"
                     % (_n(v.get("Vk"), 1), _n(v.get("S2"), 3), v.get("categoria", "—"), v.get("classe", "—"),
                        _n(v.get("q_kN_m2"), 3)))
            L.append("Prédio fechado (NBR 6123:2023, Tabelas 6 e 7): b = %s m, a = %s m, h = %s m, θ = %s°; C<sub>pi</sub> %s."
                     % (_n(v.get("b"), 1), _n(v.get("a"), 1), _n(v.get("h"), 2), _n(v.get("teta"), 1),
                        " e ".join(_n(x, 1) for x in v.get("cpi") or [])))
        return "".join("<p>%s</p>" % x for x in L)
    if c:
        L.append("Cobertura: %s m² em %s tesouras; larguras de influência %s m."
                 % (_n(c.get("area_m2"), 1), c.get("trelicas", "—"), " · ".join(_n(x, 2) for x in c.get("larguras_m") or [])))
    if v:
        L.append("V<sub>k</sub> = %s m/s (S<sub>2</sub> = %s, classe %s, z = %s m) · q = <b>%s kN/m²</b>"
                 % (_n(v.get("Vk"), 1), _n(v.get("S2"), 3), v.get("classe", "—"), _n(v.get("z"), 1), _n(v.get("q_kN_m2"), 3)))
        for k, vc in enumerate(v.get("coberturas") or [v]):
            qual = ("Cobertura %d (z = %s m, q = %s kN/m²) — " % (k + 1, _n(vc.get("z"), 2), _n(vc.get("q_kN_m2"), 3))
                    if v.get("coberturas") else "")
            if vc.get("aguas") == 1:
                L.append("%sCobertura isolada a uma água (NBR 6123:2023, 7.2, Tabela 24): vão %s m, tg θ = %s; altura livre %s m."
                         % (qual, _n(vc.get("vao"), 1), _n(vc.get("tg"), 3), _n(vc.get("h_livre"), 2)))
                L.append("Carregamento 1: %s · Carregamento 2: %s (positivo empurra para baixo; linear entre as bordas)."
                         % (_esc((vc.get("carregamento_1") or {}).get("tabela_24")),
                            _esc((vc.get("carregamento_2") or {}).get("tabela_24"))))
            else:
                c1, c2 = vc.get("carregamento_1") or {}, vc.get("carregamento_2") or {}
                L.append("%sCobertura isolada a duas águas (NBR 6123:2023, 7.2, Tabela 25): vão %s m, flecha %s m → tg θ = %s; "
                         "altura livre %s m." % (qual, _n(vc.get("vao"), 1), _n(vc.get("flecha"), 2), _n(vc.get("tg"), 3),
                                                  _n(vc.get("h_livre"), 2)))
                L.append("Carregamento 1: c<sub>pb</sub> = %s, c<sub>ps</sub> = %s · Carregamento 2: c<sub>pb</sub> = %s, "
                         "c<sub>ps</sub> = %s (positivo empurra para baixo)." % (
                             _n(c1.get("cpb"), 3), _n(c1.get("cps"), 3), _n(c2.get("cpb"), 3), _n(c2.get("cps"), 3)))
        if v.get("atrito_kN") is not None:
            L.append("Atrito ao longo da geratriz (7.2.2): %s kN." % _n(v.get("atrito_kN"), 1))
        for lista, rot in ((v.get("barras_transversal"), "com o vento perpendicular à geratriz"),
                           (v.get("barras_longitudinal"), "com o vento ao longo da geratriz")):
            if lista:
                L.append("Arrasto nas barras %s (8.1): %s." % (rot, "; ".join(
                    "%s %s: %s kN/m (C %s · K %s · c %s mm, %s)" % (
                        _esc(r.get("papel")), _esc(r.get("perfil")), _n(r.get("w_kN_m"), 3), _n(r.get("C"), 2),
                        _n(r.get("K"), 2), r.get("c_mm"), _esc(r.get("regime"))) for r in lista)))
    return "".join("<p>%s</p>" % x for x in L)


def _casos(an: dict) -> str:
    eq = an.get("equilibrio") or {}
    linhas = []
    for k, c in (an.get("casos") or {}).items():
        e = eq.get(k) or {}
        car, rea = e.get("cargas_kN") or [None] * 3, e.get("reacoes_kN") or [None] * 3
        H = math.hypot(car[0], car[1]) if car[0] is not None else None
        fecha = (abs(sum(car) + sum(rea)) < 0.05 * max(1.0, abs(car[2] or 0) + (H or 0))) if car[0] is not None else None
        linhas.append(["<b>%s</b>" % _esc(k), _esc(c.get("descricao")), _n(car[2], 2), _n(H, 2),
                       _n(rea[2], 2), "" if fecha is None else ("ok" if fecha else "<span class=ruim>não fecha</span>")])
    return _tab(["caso", "descrição", "ΣF<sub>z</sub> cargas (kN)", "ΣH cargas (kN)", "ΣF<sub>z</sub> reações (kN)",
                 "equilíbrio"], linhas, esquerda=2)


def _combinacoes(an: dict) -> str:
    linhas = []
    for k, c in (an.get("combinacoes") or {}).items():
        fat = " + ".join("%s·%s" % (_n(f, 2), _esc(n)) for n, f in (c.get("fatores") or {}).items() if f)
        linhas.append(["<b>%s</b>" % _esc(k), _esc(c.get("tipo")), fat, _esc(c.get("descricao"))])
    return _tab(["combinação", "tipo", "fatores", "descrição"], linhas, esquerda=4)


# ------------------------------------------------------------------ 2ª ordem e serviço
def _segunda_ordem(an: dict) -> str:
    so = an.get("segunda_ordem")
    if not so:
        p = an.get("parametros") or {}
        return "<p>%s</p>" % ("Desligada nas premissas: os esforços são de 1ª ordem." if p.get("segunda_ordem") is False
                              else "Sem 2ª ordem neste resultado.")
    r = so.get("resumo") or {}
    cls = {"pequena": "pequena (≤ 1,1)", "média": "média (1,1 a 1,4)", "grande": "GRANDE (> 1,4)"}
    txt = ("<p>Deslocabilidade <b>%s</b> — Δ<sub>2</sub>/Δ<sub>1</sub> até <b>%s</b>%s.%s</p>"
           "<p class=nota>Cada combinação última com P-Δ (rigidez geométrica, iterando a normal), EA e EI × %s e forças "
           "nocionais de %s%% da carga gravitacional de cálculo de cada nó nas combinações só gravitacionais, nas duas "
           "direções em planta (·X e ·Y; NBR 8800:2024, 4.10.7.1.1) — nas de vento a norma as dispensa, salvo na grande "
           "deslocabilidade (4.10.7.2). Δ = o maior deslocamento horizontal no topo dos pilares; Δ<sub>1</sub> = 1ª ordem com "
           "as mesmas cargas e rigidez. Os esforços, as reações e a verificação das ELU são os de 2ª ordem.</p>") % (
        cls.get(r.get("classe"), "—"), _n(r.get("razao_max"), 3),
        " (%s)" % _esc(r["comb_razao_max"]) if r.get("comb_razao_max") else "",
        " <b class=ruim>Instável em %d combinação(ões).</b>" % len(r["instaveis"]) if r.get("instaveis") else "",
        _n(r.get("fator_rigidez", 0.8), 1), _n((r.get("nocional") or 0.003) * 100, 1))
    linhas = [[_esc(c), _n(x.get("delta1_mm"), 1), _n(x.get("delta2_mm"), 1),
               "<b class=ruim>instável</b>" if x.get("instavel") else _n(x.get("razao"), 3), _esc(x.get("classe") or ""),
               str(x.get("iteracoes", ""))] for c, x in (so.get("combinacoes") or {}).items()]
    return txt + _tab(["combinação", "Δ<sub>1</sub> (mm)", "Δ<sub>2</sub> (mm)", "Δ<sub>2</sub>/Δ<sub>1</sub>", "classe",
                       "iterações"], linhas)


def deslocamentos(an: dict) -> Optional[dict]:
    """o topo dos pilares contra H/300 e a flecha das tesouras contra L/250 nas combinações ELS (NBR 8800, Tabela C.1) —
    a mesma conta do quadro "Como ler" da tela (web/analise_guia.js)"""
    combs, por = an.get("combinacoes") or {}, an.get("por_comb") or {}
    els = [c for c, v in combs.items() if v.get("tipo") == "ELS" and c in por]
    nos, barras, apoios = an.get("nos") or [], an.get("barras") or [], an.get("apoios") or []
    if not els or not nos or not apoios:
        return None
    tops = {}
    for b in barras:
        if b.get("papel") != "pilar":
            continue
        za, zb = nos[b["a"]][2], nos[b["b"]][2]
        topo = b["a"] if za >= zb else b["b"]
        tops[topo] = 0.0
    if not tops:
        return None
    zmin = min(nos[a["no"]][2] for a in apoios)
    for n in tops:
        tops[n] = nos[n][2] - zmin
    h = {"max": 0.0, "comb": "", "lim": 0.0}
    for c in els:
        U = por[c].get("desl_mm") or []
        for n, H in tops.items():
            if n < len(U):
                d = math.hypot(U[n][0], U[n][1])
                if d > h["max"]:
                    h.update(max=d, comb=c, lim=H / 300.0, H=H)
    trel = {x for b in barras if b.get("elemento") == "trelica" for x in (b["a"], b["b"])}
    v = {"max": 0.0, "comb": ""}
    for c in els:
        U = por[c].get("desl_mm") or []
        if not U:
            continue
        z0 = sum(U[n][2] for n in tops if n < len(U)) / max(1, len(tops))
        for n in trel:
            if n < len(U) and abs(U[n][2] - z0) > v["max"]:
                v.update(max=abs(U[n][2] - z0), comb=c)
    vao = ((an.get("info") or {}).get("vento") or {}).get("vao")
    if vao and trel:
        v["lim"] = vao * 1000 / 250.0
        v["vao"] = vao
    return {"topo": h, "flecha": v if trel else None}


def _servico(an: dict) -> str:
    d = deslocamentos(an)
    if not d:
        return "<p>Sem combinações de serviço neste resultado.</p>"
    h, v = d["topo"], d["flecha"]
    L = ["<p>Topo dos pilares: <b>%s mm</b> em %s; limite H/300 = %s mm (H = %s m) — %s.</p>" % (
        _n(h["max"], 0), _esc(h["comb"]), _n(h["lim"], 0), _n(h.get("H", 0) / 1000, 2), _ok(h["max"] <= h["lim"]))]
    if v and v.get("lim"):
        L.append("<p>Flecha das tesouras: <b>%s mm</b> em %s; limite L/250 = %s mm (vão %s m) — %s.</p>" % (
            _n(v["max"], 0), _esc(v["comb"]), _n(v["lim"], 0), _n(v["vao"], 2), _ok(v["max"] <= v["lim"])))
    L.append("<p class=nota>Combinações raras de serviço, sem coeficientes (NBR 8800, Anexo C, Tabela C.1). Os limites são os "
             "de galpão: o projeto pode adotar outros.</p>")
    return "".join(L)


# ------------------------------------------------------------------ verificação das peças
def conta_da_peca(pc: dict, V: dict, nomes: Optional[Dict[str, str]] = None) -> str:
    """a conta de uma peça como no bloco "Verificação da peça" da tela (web/analise_estrutural.js, blocoDaVerificacao)"""
    R = (V.get("resistencias") or [{}])[pc.get("res", 0)] if V.get("resistencias") else {}
    nome = (nomes or {}).get(pc.get("chave")) or pc.get("marca") or ""
    titulo = "%s%s · %s · %s%s" % (_papel(pc.get("papel")), " · " + _esc(nome) if nome else "", _esc(pc.get("perfil")),
                                   _esc(pc.get("aco")), " (f<sub>y</sub> %s MPa)" % _n(R.get("fy"), 0) if R.get("fy") else "")
    if pc.get("uso") is None:
        return "<div class=conta><b>%s</b><p class=ruim>%s</p></div>" % (titulo, _esc(" · ".join(pc.get("obs") or []) or "não verificada"))
    u = pc["uso"]
    linhas = [("Governa", "<b>%s</b>%s%s · %s" % (
        _esc(pc.get("verif")), " em %s" % _esc(pc["comb"]) if pc.get("comb") else "",
        ", a %s%% da barra" % _n((pc.get("x") or 0) * 100, 0) if pc.get("x") is not None else "",
        "esforços de 1ª ordem" if V.get("primeira_ordem") else "esforços de 2ª ordem"))]
    linhas.append(("Peça", "L = %s m (%s trecho%s)" % (_n(pc.get("L"), 2), pc.get("nb", 1), "s" if pc.get("nb", 1) > 1 else "")))
    k = "K·" if pc.get("K") else ""
    linhas.append(("Flambagem", "%sL<sub>x</sub> = <b>%s m</b> (eixo forte) · %sL<sub>y</sub> = <b>%s m</b> (eixo fraco; L<sub>b</sub> "
                   "da FLT) · K = %s" % (k, _n(pc.get("Lx"), 2), k, _n(pc.get("Ly"), 2),
                                         _n(pc["K"], 2) + " (NBR 16239, 4.8)" if pc.get("K") else "1")))
    tv = pc.get("travamentos") or [0, 0]
    linhas.append(("Travamentos", "%s na altura · %s na largura, ao longo da peça" % (tv[0], tv[1])))
    if pc.get("lam_lim"):
        linhas.append(("Esbeltez", "λ = %s (limite %s%s) — %s" % (
            _n(pc.get("lam"), 0), _n(pc["lam_lim"], 0), ", comprimida" if pc["lam_lim"] == 200 else ", só tracionada",
            "<span class=ruim>acima do limite</span>" if (pc.get("lam") or 0) > pc["lam_lim"] else "ok")))
    rd = []
    if R.get("Nc"):
        rd.append("N<sub>c,Rd</sub> = <b>%s kN</b>%s" % (_n(R["Nc"], 1), " (χ %s, Q %s, λ<sub>0</sub> %s)" % (
            _n(R.get("chi"), 3), _n(R.get("Q"), 3), _n(R.get("lambda0"), 2)) if R.get("chi") is not None else ""))
    if R.get("Nt"):
        rd.append("N<sub>t,Rd</sub> = <b>%s kN</b>" % _n(R["Nt"], 1))
    if R.get("Mz"):
        rd.append("M<sub>z,Rd</sub> = <b>%s kN·m</b>%s" % (_n(R["Mz"], 2), " (%s)" % _esc(str(R["gov_Mz"]).replace("Flexão — ", ""))
                                                            if R.get("gov_Mz") else ""))
    if R.get("My"):
        rd.append("M<sub>y,Rd</sub> = <b>%s kN·m</b>%s" % (_n(R["My"], 2), " (%s)" % _esc(str(R["gov_My"]).replace("Flexão — ", ""))
                                                            if R.get("gov_My") else ""))
    if R.get("Vy"):
        rd.append("V<sub>y,Rd</sub> = %s · V<sub>z,Rd</sub> = %s kN" % (_n(R["Vy"], 1), _n(R.get("Vz"), 1)))
    linhas.append(("Resistências (%s)" % _esc(R.get("norma") or "NBR 8800"), "<br>".join(rd)))
    s = pc.get("esf")
    if s:
        V_ = math.hypot(s.get("Vy", 0), s.get("Vz", 0))
        linhas.append(("Solicitantes", "N = %s kN · M<sub>z</sub> = %s · M<sub>y</sub> = %s kN·m · V = %s kN<br>"
                       "N = %s tf · M<sub>z</sub> = %s · M<sub>y</sub> = %s tf·m · V = %s tf" % (
                           _n(s.get("N"), 1), _n(s.get("Mz"), 2), _n(s.get("My"), 2), _n(V_, 1),
                           _n(s.get("N", 0) / TF, 2), _n(s.get("Mz", 0) / TF, 2), _n(s.get("My", 0) / TF, 2), _n(V_ / TF, 2))))
        if pc.get("B1"):
            b1 = lambda x: "∞ (N ≥ N<sub>e</sub>)" if x >= 99 else _n(x, 3)
            linhas.append(("P-δ (B<sub>1</sub>)", "B<sub>1</sub> = %s (z) · %s (y); C<sub>m</sub> %s · %s; N<sub>e</sub> %s · %s kN" % (
                b1(pc["B1"][0]), b1(pc["B1"][1]), _n(pc["Cm"][0], 2), _n(pc["Cm"][1], 2), _n(pc["Ne"][0], 0), _n(pc["Ne"][1], 0))))
        p = pc.get("partes") or {}
        if R.get("redonda"):
            conta = "N/N<sub>t,Rd</sub> = %s" % _n(p.get("N"), 3)
        elif R.get("linear"):
            conta = ("N/N<sub>Rd</sub> + B<sub>1</sub>·M<sub>z</sub>/M<sub>z,Rd</sub> + B<sub>1</sub>·M<sub>y</sub>/M<sub>y,Rd</sub> = "
                     "%s + %s + %s (NBR 14762, 9.8.2.4)" % (_n(p.get("N"), 3), _n(p.get("Mz"), 3), _n(p.get("My"), 3)))
        elif (p.get("N") or 0) >= 0.2:
            conta = ("N/N<sub>Rd</sub> + 8/9·(B<sub>1</sub>·M<sub>z</sub>/M<sub>z,Rd</sub> + B<sub>1</sub>·M<sub>y</sub>/M<sub>y,Rd</sub>) = "
                     "%s + 8/9·(%s + %s) (5.5.1.2, eq. a)" % (_n(p.get("N"), 3), _n(p.get("Mz"), 3), _n(p.get("My"), 3)))
        else:
            conta = ("N/(2·N<sub>Rd</sub>) + B<sub>1</sub>·M<sub>z</sub>/M<sub>z,Rd</sub> + B<sub>1</sub>·M<sub>y</sub>/M<sub>y,Rd</sub> = "
                     "%s/2 + %s + %s (5.5.1.2, eq. b)" % (_n(p.get("N"), 3), _n(p.get("Mz"), 3), _n(p.get("My"), 3)))
        if p.get("V"):
            conta += "<br>cortante: %s" % _n(p["V"], 3)
        linhas.append(("Interação", conta))
    obs = list(pc.get("obs") or []) + list(R.get("obs") or [])
    return ("<div class=conta><div class=cab><span class='uso %s'>%s</span><b>%s</b></div>%s%s</div>" % (
        "ruim" if u > 1 else "ok", _pct(u), titulo, _kv(linhas),
        "<p class=nota>%s</p>" % "<br>".join(_esc(o) for o in obs) if obs else ""))


def _verificacao(an: dict, nomes: Optional[Dict[str, str]] = None, titulo_situacao: str = "") -> str:
    V = an.get("verificacao")
    if not V:
        return "<p>Sem verificação das peças neste resultado (calcule de novo).</p>"
    gs = V.get("grupos") or []
    pecas = V.get("pecas") or []
    sug = {g["chave"]: g for g in an.get("grupos_perfis") or []}
    linhas = []
    for g in gs:
        s = sug.get(g["chave"]) or {}
        leve = s.get("mais_leve_que_passa")
        linhas.append([_esc(_grupo_legivel(g["chave"])), str(g.get("pecas", "")), str(g.get("nao_passam", "")),
                       "<b class=%s>%s</b>" % ("ruim" if (g.get("uso") or 0) > 1 else "ok", _pct(g.get("uso"))),
                       _esc(g.get("verif")), _esc(g.get("comb")),
                       _esc(leve) if leve and leve != s.get("atual") else ("—" if not leve else "o atual")])
    H = ["<p>%sCada grupo é uma função com um perfil (o perfil original do modelo, antes das trocas de teste); o uso é o "
         "da peça mais solicitada do grupo. \"Mais leve que passa\" é a estimativa da tela de troca de perfil (mesmas "
         "resistências, esforços da combinação que governa cada barra) — confirmar recalculando com a troca.</p>" % (
             "<b>%s.</b> " % titulo_situacao if titulo_situacao else ""),
         _tab(["grupo", "peças", "não passam", "uso máx.", "governa", "combinação", "mais leve que passa"], linhas)]
    for g in gs:
        k = g.get("peca")
        if isinstance(k, int) and 0 <= k < len(pecas):
            H.append(conta_da_peca(pecas[k], V, nomes))
    if V.get("avisos"):
        H.append("".join("<p class=aviso>%s</p>" % _esc(a) for a in V["avisos"]))
    return "".join(H)


# ------------------------------------------------------------------ reações, bases, apoio, ligações
def _reacoes(an: dict, eixos=None) -> str:
    env = an.get("reacoes_envoltoria")
    linhas = []
    if env:
        for e in env:
            linhas.append([_esc(nome_da_base(e["chave"], eixos)), "▪" if e.get("tipo") == "engastada" else "▲",
                           "%s <span class=c>%s</span>" % (_n(e["Fz_max"][0], 1), _esc(e["Fz_max"][1])),
                           "%s <span class=c>%s</span>" % ("<b class=ruim>%s</b>" % _n(e["Fz_min"][0], 1) if e["Fz_min"][0] < 0
                                                           else _n(e["Fz_min"][0], 1), _esc(e["Fz_min"][1])),
                           "%s <span class=c>%s</span>" % (_n(e["H_max"][0], 1), _esc(e["H_max"][1])),
                           "%s <span class=c>%s</span>" % (_n(e["M_max"][0], 1), _esc(e["M_max"][1]))])
    else:
        for e in _reacoes_por_apoio(an):
            linhas.append([_esc(nome_da_base(e["chave"], eixos)), "▪" if e.get("tipo") == "engastada" else "▲",
                           "%s <span class=c>%s</span>" % (_n(e["Fz_max"][0], 1), _esc(e["Fz_max"][1])),
                           "%s <span class=c>%s</span>" % (_n(e["Fz_min"][0], 1), _esc(e["Fz_min"][1])),
                           "%s <span class=c>%s</span>" % (_n(e["H_max"][0], 1), _esc(e["H_max"][1])),
                           "%s <span class=c>%s</span>" % (_n(e["M_max"][0], 1), _esc(e["M_max"][1]))])
    if not linhas:
        return "<p>Sem reações neste resultado.</p>"
    return ("<p>Envoltória das combinações últimas%s (kN e kN·m). F<sub>z</sub> positivo comprime a base; negativo arranca "
            "(é o que o chumbador recebe). ▪ engastada · ▲ articulada.</p>" % (
                " nas duas situações (aberta e retraída)" if an.get("outras_situacoes") else "")
            + _tab(["base", "", "F<sub>z</sub> máx", "F<sub>z</sub> mín", "H máx", "M máx"], linhas, esquerda=2))


def _reacoes_por_apoio(an: dict) -> List[dict]:
    """a envoltória ELU das reações apoio por apoio, quando o resultado não traz `reacoes_envoltoria` (uma situação só)"""
    combs, por = an.get("combinacoes") or {}, an.get("por_comb") or {}
    elus = [c for c, v in combs.items() if v.get("tipo") == "ELU" and c in por]
    out = []
    for ap in an.get("apoios") or []:
        n = str(ap["no"])
        rs = [(c, por[c]["reacoes"][n]) for c in elus if n in (por[c].get("reacoes") or {})]
        if not rs:
            continue
        fmax = max(rs, key=lambda r: r[1][2])
        fmin = min(rs, key=lambda r: r[1][2])
        hmax = max(rs, key=lambda r: math.hypot(r[1][0], r[1][1]))
        mmax = max(rs, key=lambda r: math.hypot(r[1][3], r[1][4]))
        out.append({"chave": ap.get("chave", n), "tipo": ap.get("tipo"),
                    "Fz_max": [fmax[1][2], fmax[0]], "Fz_min": [fmin[1][2], fmin[0]],
                    "H_max": [math.hypot(hmax[1][0], hmax[1][1]), hmax[0]],
                    "M_max": [math.hypot(mmax[1][3], mmax[1][4]), mmax[0]]})
    return out


def grupos_de_bases(an: dict) -> List[dict]:
    """as bases iguais (mesmo pilar e mesma solução) juntas, como na tela"""
    g = {}
    for b in an.get("bases") or []:
        bb = b.get("base") or {}
        k = ("%s|%s|%s|%s|%s|%s|%s|%s" % (b.get("perfil"), bb.get("tipo"), bb.get("nb"), bb.get("diametro"), bb.get("tp"),
                                          bb.get("lx"), bb.get("ly"), b.get("ok")) if bb else "%s|%s" % (b.get("perfil"), b["chave"]))
        g.setdefault(k, {"b": b, "chaves": []})["chaves"].append(b["chave"])
    return list(g.values())


def _bases(an: dict, eixos=None) -> str:
    L = an.get("bases")
    if not L:
        return "<p>Sem bases dimensionadas neste resultado.</p>"
    grupos = grupos_de_bases(an)
    linhas = []
    for gr in grupos:
        b, bb = gr["b"], gr["b"].get("base") or {}
        linhas.append([("%d bases" % len(gr["chaves"])) if len(gr["chaves"]) > 1 else _esc(nome_da_base(gr["chaves"][0], eixos)),
                       _esc(b.get("perfil")),
                       "%s×ø%s · %s×%s×%s" % (bb.get("nb"), _esc(bb.get("diametro")), _n(bb.get("lx"), 0), _n(bb.get("ly"), 0),
                                             _n(bb.get("tp"), 1)) if bb.get("tp") else "—",
                       "—" if b.get("ok") is None else _ok(b.get("ok")) + (" ⚠" if b.get("avisos") else "")])
    H = ["<p>Cada base verificada em todas as combinações últimas%s, com o N, o M e o V concomitantes (2ª ordem). Método da "
         "NBR 8800:2024, 6.7 (com a Errata 1:2025): placa e chumbadores pela Tabela 18, chumbadores ASTM A36, bloco f<sub>ck</sub> "
         "%s MPa, placa %s.</p>" % (" das duas situações" if an.get("outras_situacoes") else "", _n(L[0].get("fck", 25), 0),
                                     _esc(L[0].get("aco_placa", ""))),
         _tab(["base", "pilar", "chumbadores · placa (mm)", ""], linhas, esquerda=2)]
    for gr in grupos:
        H.append(_detalhe_da_base(gr["b"], [nome_da_base(c, eixos) for c in gr["chaves"]]))
    return "".join(H)


def _detalhe_da_base(b: dict, onde: List[str]) -> str:
    bb, env = b.get("base") or {}, b.get("envoltoria") or {}
    cr = lambda c: ("%s kN · M %s · V %s (%s%s)" % (_n(c.get("N"), 1), _n(c.get("M"), 1), _n(c.get("V"), 1),
                                                   c["sit"] + " · " if c.get("sit") else "", _esc(c.get("comb")))) if c else "—"
    pares = [("N máx", cr(env.get("N_max"))), ("N mín", cr(env.get("N_min"))), ("M máx", cr(env.get("M_max"))),
             ("V máx", cr(env.get("V_max")))]
    if bb:
        T, K = bb.get("tabela") or {}, bb.get("bloco") or {}
        pares += [
            ("Solução", "base tipo %s · <b>%s chumbadores ø %s</b> ASTM A36 · placa <b>%s × %s × %s mm</b> (t<sub>p,mín</sub> %s mm)%s" % (
                bb.get("tipo"), bb.get("nb"), _esc(bb.get("diametro")), _n(bb.get("lx"), 0), _n(bb.get("ly"), 0),
                _n(bb.get("tp"), 1), _n(bb.get("tp_min"), 1), " · ~%s kg" % _n(bb["peso_kg"], 0) if bb.get("peso_kg") else "")),
            ("Espessura governa em", "%s%s (%s)" % ((bb.get("governa_tp") or {}).get("sit", "") + " · " if (bb.get("governa_tp") or {}).get("sit") else "",
                                                   _esc((bb.get("governa_tp") or {}).get("comb", "—")), _esc((bb.get("governa_tp") or {}).get("caso", "")))),
        ]
        if bb.get("governa_ft"):
            gf = bb["governa_ft"]
            pares.append(("Chumbador", "F<sub>t,Sd</sub> = %s kN por chumbador → d<sub>b,mín</sub> %s mm (ø %s mm) em %s (%s)" % (
                _n(gf.get("Ft"), 1), _n(gf.get("db_min"), 1), _n(bb.get("db"), 0), _esc(gf.get("comb")), _esc(gf.get("caso")))))
        disp = bb.get("dispositivo")
        pc = bb.get("placa_cisalhamento") or {}
        pares.append(("Cortante", "atrito placa–argamassa (μ = 0,45)" if disp == "atrito" else
                      "arruelas especiais soldadas à placa (6.7.2.5)" if disp == "arruelas soldadas" else
                      "placa de cisalhamento %s × %s × %s mm (6.7.2.4)" % (_n(pc.get("bh"), 0), _n(pc.get("bv"), 0), _n(pc.get("tpv"), 1))))
        if T:
            pares.append(("Tabela 18", "a<sub>1</sub> %s · a<sub>2</sub> %s · embutimento h<sub>1</sub> %s · h<sub>2</sub> %s · furo %s · "
                          "arruela %s×%s×%s · argamassa e<sub>n</sub> %s mm" % (T.get("a1"), T.get("a2"), T.get("h1"), T.get("h2"),
                                                                               T.get("df"), T.get("arruela"), T.get("arruela"),
                                                                               _n(T.get("ta"), 1), T.get("en"))))
        if K:
            pares.append(("Bloco", "mínimo %s × %s mm, altura %s mm; f<sub>ck</sub> ≥ %s MPa; armadura mínima ø%s c/ %s mm (NBR 6118)" % (
                _n(K.get("Nb"), 0), _n(K.get("Bb"), 0), _n(K.get("Ab"), 0), T.get("fck_min", "—"), _n(K.get("phi"), 1), K.get("S"))))
    J = b.get("chumbador_j")
    if J:
        pares.append(("Chumbador em J", "F<sub>t</sub> %s kN · f<sub>bd</sub> %s MPa · ℓ<sub>b,nec</sub> %s mm contra o embutimento da "
                      "Tabela (%s mm) — %s (NBR 6118:2023, 9.4.2)" % (_n(J.get("Ft_kN"), 1), _n(J.get("fbd"), 2), _n(J.get("lb_nec"), 0),
                                                                    _n(J.get("h_disponivel"), 0),
                                                                    "ok" if J.get("ok") else "<span class=ruim>precisa de embutimento maior</span>")))
    JO = (b.get("chumbador_j_opcoes") or {}).get("recomendada")
    if JO:
        pares.append(("J que fecha", "%s × ø %s · barra %s mm · f<sub>ck</sub> %s MPa · bloco ≥ %s mm · placa %s mm" % (
            JO.get("nb"), _esc(JO.get("diametro")), _n(JO.get("comprimento"), 0), _n(JO.get("fck"), 0),
            _n(JO.get("bloco_altura_min"), 0), _n(JO.get("tp"), 1))))
    for chave, rot in (("com_abas", "Com abas"), ("com_abas_pontas", "Duas abas por lado")):
        A = b.get(chave)
        if A and A.get("tp"):
            pares.append((rot, "placa %s mm · abas %s × %s × %s mm · ~%s kg%s" % (
                _n(A.get("tp"), 1), _n(A.get("hg"), 0), _n(A.get("Lg"), 0), _n(A.get("tg"), 1), _n(A.get("peso_kg"), 0),
                "" if A.get("ok") else " · <span class=ruim>não fecha</span>")))
    falhas = list(bb.get("falhas") or []) + list(b.get("avisos") or [])
    return "<div class=conta><div class=cab><b>Base %s</b> — pilar %s, apoio %s %s</div>%s%s</div>" % (
        _esc(" · ".join(onde[:6]) + (" …" if len(onde) > 6 else "")), _esc(b.get("perfil")), _esc(b.get("apoio")),
        "" if b.get("ok") is None else _ok(b.get("ok")), _kv(pares),
        "".join("<p class=aviso>%s</p>" % _esc(f) for f in falhas))


def _carrinho(an: dict) -> str:
    A = an.get("apoios_tesouras")
    if not A or not A.get("pior"):
        return ""
    p = A["pior"]
    xy = lambda v: "; ".join(_n(x, 2) for x in v.get("xy") or [])
    lin = lambda rot, v: [rot, "<b>%s</b>" % _n(v.get("valor"), 1), "%s (%s) · %s" % (_esc(v.get("grupo")), xy(v), _esc(v.get("comb")))]
    media = sum(max(0.0, a["Fv_max"][0]) for a in A.get("apoios") or []) / max(1, len(A.get("apoios") or []))
    return ("<p>%s apoios — a soma das forças que a tesoura e o que vai com ela entregam no apoio, nas combinações últimas "
            "(2ª ordem). Compressão positiva; negativa = arrancamento. Média da compressão por apoio: %s kN.</p>" % (
                A.get("n", len(A.get("apoios") or [])), _n(media, 1))
            + _tab(["o pior", "kN", "onde"], [lin("compressão no apoio", p["Fv_max"]), lin("arrancamento", p["Fv_min"]),
                                              lin("horizontal no vão", p["Ht_max"]), lin("ao longo do trilho", p["Hl_max"])]))


def _ligacoes(an: dict) -> str:
    H = []
    L = an.get("ligacoes") or []
    if L:
        g = {}
        for l in L:
            m = l["max"]
            k = "%s|%s|%d|%d" % (l.get("perfil_viga"), l.get("perfil_pilar"), round(m["Mz"][0]), round(m["V"][0]))
            g.setdefault(k, {"l": l, "n": 0})["n"] += 1
        linhas = []
        for it in g.values():
            l, m = it["l"], it["l"]["max"]
            c = m["Mz"][1]
            linhas.append(["%s → %s%s" % (_esc(l.get("perfil_viga")), _esc(l.get("perfil_pilar")), " (%d)" % it["n"] if it["n"] > 1 else ""),
                           "<b>%s</b> <span class=c>%s</span>" % (_n(m["Mz"][0], 1), _esc(c.get("comb"))),
                           "N %s · V %s · M<sub>fraco</sub> %s" % (_n(c.get("N"), 1), _n(c.get("V"), 1), _n(c.get("My"), 2)),
                           _n(m["V"][0], 1), "+%s / −%s" % (_n(m["Nt"][0], 1), _n(m["Nc"][0], 1))])
        H.append("<p>Esforços nas pontas das vigas que chegam em pilares (2ª ordem): o maior momento no eixo forte com a normal, "
                 "o cortante e o momento fraco da mesma combinação; o maior cortante e as normais extremas.</p>")
        H.append(_tab(["viga → pilar", "M máx (kN·m)", "concomitantes", "V máx (kN)", "N± (kN)"], linhas))
    T = an.get("ligacoes_topo") or []
    if T:
        g = {}
        for l in T:
            x = l.get("ligacao") or {}
            k = "%s|%s|%s|%s|%s|%s|%s" % (l.get("pilar"), l.get("viga"), x.get("n"), x.get("diametro"), x.get("t_pilar"),
                                          x.get("t_viga"), l.get("ok"))
            g.setdefault(k, {"l": l, "n": 0})["n"] += 1
        H.append("<p>Viga apoiada no topo do pilar: chapa soldada no topo do pilar + chapa soldada sob a mesa da viga, parafusos "
                 "verticais (a solução de partida, a avaliar) — NBR 8800:2024: parafusos 6.3.3, alavanca 6.3.5, solda 6.2.5, "
                 "alma da viga 5.7.3/5.7.4. A análise considera a ligação rígida; chapas parafusadas no topo são semirrígidas.</p>")
        linhas = []
        for it in g.values():
            l = it["l"]
            x, pr = l.get("ligacao") or {}, (l.get("ligacao") or {}).get("pior") or {}
            linhas.append(["%s · %s%s" % (_esc(l.get("pilar")), _esc(l.get("viga")), " (%d)" % it["n"] if it["n"] > 1 else ""),
                           "%s×ø%s A325 · %s×%s · %s/%s mm" % (x.get("n"), _esc(x.get("diametro")), _n(x.get("Bx"), 0), _n(x.get("By"), 0),
                                                             _n(x.get("t_pilar"), 1), _n(x.get("t_viga"), 1)) if x.get("n") else "—",
                           "tração %s · interação %s · alma %s" % (_pct(pr.get("ft")), _pct(pr.get("int")), _pct(pr.get("alma"))),
                           _ok(l.get("ok"))])
        H.append(_tab(["pilar · viga", "parafusos · chapas", "usos", ""], linhas, esquerda=2))
        for it in g.values():
            for f in ((it["l"].get("ligacao") or {}).get("falhas") or []):
                H.append("<p class=aviso>%s · %s: %s</p>" % (_esc(it["l"].get("pilar")), _esc(it["l"].get("viga")), _esc(f)))
    return "".join(H) or "<p>Nenhuma viga chegando em pilar neste modelo.</p>"


def apontamentos(an: dict) -> List[str]:
    """tudo o que o resultado aponta, sem repetir: instabilidade, avisos do cálculo, da verificação, das bases e ligações"""
    out = []
    if an.get("instavel"):
        out.append("Estrutura instável: %s." % an["instavel"])
    out += list(an.get("avisos") or [])
    out += list((an.get("verificacao") or {}).get("avisos") or [])
    for b in an.get("bases") or []:
        out += list(b.get("avisos") or [])
        out += list((b.get("base") or {}).get("falhas") or [])
    for l in an.get("ligacoes_topo") or []:
        out += ["ligação %s · %s: %s" % (l.get("pilar"), l.get("viga"), f) for f in ((l.get("ligacao") or {}).get("falhas") or [])]
        if l.get("aviso"):
            out.append(l["aviso"])
    vistos, unicos = set(), []
    for a in out:
        if a and a not in vistos:
            vistos.add(a)
            unicos.append(a)
    return unicos


# ------------------------------------------------------------------ o quadro de comparação
def _env_de_grupos(an: dict) -> List[dict]:
    """pilares e vigas por grupo (função + perfil original): a envoltória ELU de 2ª ordem de todas as barras do grupo"""
    env = an.get("envoltoria") or []
    g = {}
    for i, b in enumerate(an.get("barras") or []):
        if b.get("papel") not in ("pilar", "viga") or b.get("hipotese") or i >= len(env):
            continue
        e = env[i] or {}
        k = "%s|%s" % (b["papel"], b.get("perfil_original") or b.get("perfil"))
        x = g.setdefault(k, {"chave": k, "perfil": b.get("perfil"), "Nc": 0.0, "Nt": 0.0, "M": 0.0, "V": 0.0})
        N = e.get("N") or [0, 0]
        x["Nc"] = max(x["Nc"], -min(N[0], 0))
        x["Nt"] = max(x["Nt"], max(N[1], 0))
        x["M"] = max(x["M"], e.get("M") or 0)
        x["V"] = max(x["V"], e.get("V") or 0)
    return sorted(g.values(), key=lambda x: (not x["chave"].startswith("pilar"), x["chave"]))


def linhas_comparacao(an: dict, eixos=None) -> List[dict]:
    """as seções do quadro, na ordem de conferência: [{titulo, nota, linhas: [{chave, rotulo, nosso, un, tipo}]}].
    `un` é a grandeza ('F' força em kN, 'M' momento em kN·m, '%', 'mm', 'txt'): a tela e o PDF convertem F e M para tf
    quando o engenheiro trabalha em tf"""
    S = []
    eq = an.get("equilibrio") or {}
    L = []
    for k, c in (an.get("casos") or {}).items():
        car = (eq.get(k) or {}).get("cargas_kN")
        if not car:
            continue
        if abs(car[2]) >= 0.005:
            L.append({"chave": "carga|%s|Fz" % k, "rotulo": "%s — vertical (ΣF<sub>z</sub>)" % _esc(k),
                      "nosso": -car[2], "un": "F"})
        H = math.hypot(car[0], car[1])
        if H > 0.5:
            L.append({"chave": "carga|%s|H" % k, "rotulo": "%s — horizontal (ΣH)" % _esc(k), "nosso": H, "un": "F"})
    if L:
        S.append({"titulo": "Cargas totais por caso", "nota": "a soma das cargas aplicadas em cada caso, sem coeficientes; a vertical positiva para "
                  "baixo (o primeiro número a bater: se a carga total difere, o resto também difere)", "linhas": L})
    L = []
    reac = an.get("reacoes_envoltoria") or _reacoes_por_apoio(an)
    for e in reac:
        nome = _esc(nome_da_base(e["chave"], eixos))
        for k, rot, un in (("Fz_max", "F<sub>z</sub> máx", "F"), ("Fz_min", "F<sub>z</sub> mín (− arranca)", "F"),
                           ("H_max", "H máx", "F"), ("M_max", "M máx", "M")):
            L.append({"chave": "reacao|%s|%s" % (e["chave"], k), "rotulo": "%s — %s" % (nome, rot), "nosso": e[k][0], "un": un,
                      "comb": e[k][1]})
    if L:
        S.append({"titulo": "Reações nas bases (envoltória ELU)", "nota": "kN e kN·m; com a combinação de cada máximo", "linhas": L})
    L = []
    for g in _env_de_grupos(an):
        nome = _esc(_grupo_legivel(g["chave"]))
        for k, rot, un in (("Nc", "compressão máx", "F"), ("Nt", "tração máx", "F"), ("M", "M máx", "M"), ("V", "V máx", "F")):
            if g[k] > 0.005:
                L.append({"chave": "esforco|%s|%s" % (g["chave"], k), "rotulo": "%s — %s" % (nome, rot), "nosso": g[k], "un": un})
    if L:
        S.append({"titulo": "Esforços nos pilares e vigas (envoltória ELU, 2ª ordem)",
                  "nota": "o maior de todas as barras do grupo; M soma os dois planos", "linhas": L})
    L = []
    V = an.get("verificacao") or {}
    for g in V.get("grupos") or []:
        nome = _esc(_grupo_legivel(g["chave"]))
        L.append({"chave": "peca|%s|uso" % g["chave"], "rotulo": "%s — uso máx." % nome, "nosso": (g.get("uso") or 0) * 100, "un": "%"})
        L.append({"chave": "peca|%s|perfil" % g["chave"], "rotulo": "%s — perfil adotado" % nome,
                  "nosso": g["chave"].partition("|")[2], "un": "txt"})
    if L:
        S.append({"titulo": "Peças (verificação pela norma)", "nota": "uso = solicitação ÷ resistência de cálculo da peça "
                  "mais solicitada; o perfil adotado pelo engenheiro ao lado do nosso", "linhas": L})
    L = []
    for gr in grupos_de_bases(an):
        b, bb = gr["b"], gr["b"].get("base") or {}
        if not bb:
            continue
        onde = "%d bases %s" % (len(gr["chaves"]), _esc(b.get("perfil"))) if len(gr["chaves"]) > 1 else \
            "%s (%s)" % (_esc(nome_da_base(gr["chaves"][0], eixos)), _esc(b.get("perfil")))
        L.append({"chave": "base|%s|tp" % gr["chaves"][0], "rotulo": "%s — espessura da placa" % onde, "nosso": bb.get("tp"), "un": "mm"})
        L.append({"chave": "base|%s|chumb" % gr["chaves"][0], "rotulo": "%s — chumbadores" % onde,
                  "nosso": "%s × ø %s" % (bb.get("nb"), bb.get("diametro")), "un": "txt"})
    if L:
        S.append({"titulo": "Bases", "nota": "NBR 8800:2024, 6.7", "linhas": L})
    d = deslocamentos(an)
    if d:
        L = [{"chave": "desl|topo", "rotulo": "topo dos pilares (ELS, horizontal)", "nosso": d["topo"]["max"], "un": "mm",
              "comb": d["topo"]["comb"]}]
        if d.get("flecha") and d["flecha"].get("max"):
            L.append({"chave": "desl|flecha", "rotulo": "flecha das tesouras (ELS)", "nosso": d["flecha"]["max"], "un": "mm",
                      "comb": d["flecha"]["comb"]})
        S.append({"titulo": "Deslocamentos (serviço)", "nota": "combinações raras, sem coeficientes", "linhas": L})
    return S


def ler_comparacao(pasta_projeto: str) -> dict:
    try:
        with open(os.path.join(pasta_projeto, ARQ_COMPARACAO), encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    c.setdefault("unidade", "kN")
    c.setdefault("engenheiro", "")
    c.setdefault("valores", {})
    c.setdefault("notas", "")
    return c


def gravar_comparacao(pasta_projeto: str, novo: dict) -> dict:
    c = ler_comparacao(pasta_projeto)
    if novo.get("unidade") in ("kN", "tf"):
        c["unidade"] = novo["unidade"]
    for k in ("engenheiro", "notas"):
        if k in novo:
            c[k] = str(novo[k] or "")[:2000]
    for k, v in (novo.get("valores") or {}).items():
        v = str(v if v is not None else "").strip()[:80]
        if v:
            c["valores"][str(k)[:300]] = v
        else:
            c["valores"].pop(str(k), None)
    c["alterado"] = time.strftime("%d/%m/%Y %H:%M")
    os.makedirs(os.path.join(pasta_projeto, "analise"), exist_ok=True)
    caminho = os.path.join(pasta_projeto, ARQ_COMPARACAO)
    with open(caminho + ".tmp", "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    os.replace(caminho + ".tmp", caminho)
    return c


def numero(texto) -> Optional[float]:
    """o número digitado ('1.234,5', '-12,3', '12.5'); None se não for número"""
    if texto is None:
        return None
    t = str(texto).strip().replace(" ", "").replace("−", "-")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def na_unidade(valor, un: str, unidade: str):
    """o nosso valor (kN / kN·m) na unidade escolhida para o quadro"""
    if isinstance(valor, (int, float)) and un in ("F", "M") and unidade == "tf":
        return valor / TF
    return valor


def rotulo_unidade(un: str, unidade: str) -> str:
    return {"F": unidade, "M": unidade + "·m", "%": "%", "mm": "mm"}.get(un, "")


def diferenca(nosso, dele) -> Optional[float]:
    """(nosso − dele) / dele; os dois com o sinal de quem digitou — a reação de arrancamento compara com sinal"""
    if not isinstance(nosso, (int, float)) or dele is None or abs(dele) < 1e-9:
        return None
    return (nosso - dele) / abs(dele)


def html_comparacao(secoes: List[dict], comp: dict, so_preenchidas: bool = False) -> str:
    un_q = comp.get("unidade", "kN")
    vals = comp.get("valores") or {}
    H = []
    n_total = n_preenchidas = 0
    for s in secoes:
        linhas = []
        for ln in s["linhas"]:
            n_total += 1
            dele_txt = vals.get(ln["chave"], "")
            if dele_txt:
                n_preenchidas += 1
            elif so_preenchidas:
                continue
            nosso = na_unidade(ln["nosso"], ln["un"], un_q)
            if ln["un"] == "txt":
                igual = dele_txt and str(dele_txt).replace(" ", "").lower() == str(nosso).replace(" ", "").lower()
                dif = "" if not dele_txt else ("igual" if igual else "<span class=ruim>diferente</span>")
                nosso_t = _esc(nosso)
            else:
                d = diferenca(nosso, numero(dele_txt))
                cls = "" if d is None else ("ok" if abs(d) <= 0.05 else "medio" if abs(d) <= 0.15 else "ruim")
                dif = "" if d is None else "<b class=%s>%s%s%%</b>" % (cls, "+" if d > 0 else "", _n(d * 100, 1))
                nosso_t = _n(nosso, 0 if ln["un"] == "mm" else 1 if ln["un"] == "%" else 2)
            linhas.append([ln["rotulo"] + (" <span class=c>%s</span>" % _esc(ln["comb"]) if ln.get("comb") else ""),
                           rotulo_unidade(ln["un"], un_q), nosso_t, _esc(dele_txt) or "<span class=vazio>&nbsp;</span>", dif])
        if linhas:
            H.append("<h3>%s</h3><p class=nota>%s</p>" % (_esc(s["titulo"]), _esc(s.get("nota", ""))))
            H.append(_tab(["", "unid.", "nosso", "engenheiro", "diferença"], linhas, cls="comp"))
    cab = ("<p>Os números do engenheiro%s ao lado dos nossos, na unidade <b>%s</b>. Diferença = (nosso − dele) ÷ dele: "
           "<b class=ok>até 5%%</b>, <b class=medio>5 a 15%%</b>, <b class=ruim>acima de 15%%</b>. %d de %d valores preenchidos%s.</p>" % (
               " (%s)" % _esc(comp["engenheiro"]) if comp.get("engenheiro") else "", un_q, n_preenchidas, n_total,
               " em %s" % comp["alterado"] if comp.get("alterado") else ""))
    if comp.get("notas"):
        cab += "<p class=nota>%s</p>" % _esc(comp["notas"]).replace("\n", "<br>")
    return cab + "".join(H)


# ------------------------------------------------------------------ o documento
CSS = """
@page { size: A4; margin: 14mm 13mm 14mm 13mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1d232b; font-size: 8.6pt; margin: 0; line-height: 1.35; }
h1 { font-size: 17pt; margin: 0 0 1mm; color: #14233a; }
h2 { font-size: 11.5pt; margin: 7mm 0 2mm; padding-bottom: 1mm; border-bottom: 1.4px solid #2a3a52; color: #14233a; break-after: avoid; }
h3 { font-size: 9.6pt; margin: 4mm 0 1mm; color: #2a3a52; break-after: avoid; }
p { margin: 1mm 0 1.6mm; }
.sub { color: #5b6573; } .rec { padding-left: 4mm; } .nota { color: #5b6573; font-size: 7.6pt; } .c { color: #7b8593; font-size: 6.8pt; }
.capa { border-left: 4px solid #1f4e9c; padding: 2mm 0 2mm 4mm; margin-bottom: 4mm; }
.indice { columns: 2; font-size: 8pt; color: #2a3a52; margin: 2mm 0 4mm; padding-left: 5mm; }
table { border-collapse: collapse; width: 100%; font-size: 7.6pt; margin: 1mm 0 2.5mm; }
thead { display: table-header-group; } tr { break-inside: avoid; }
th { font-size: 6.9pt; color: #5b6573; text-align: right; border-bottom: 1.2px solid #2a3a52; padding: 1mm 1.4mm; vertical-align: bottom; }
th.l, td.l { text-align: left; } td { text-align: right; padding: 0.8mm 1.4mm; border-bottom: 1px solid #e3e7ec; vertical-align: top; }
table.kv td:first-child { color: #5b6573; width: 30%; white-space: nowrap; }
.conta { break-inside: avoid; border: 1px solid #d5dbe3; border-radius: 2mm; padding: 2mm 3mm; margin: 2.5mm 0; }
.conta .cab { margin-bottom: 1mm; } .uso { font-size: 12pt; font-weight: 700; margin-right: 3mm; }
.ok { color: #1e7b45; } .medio { color: #b26a00; } .ruim { color: #c0392b; }
.aviso { border-left: 3px solid #d68910; background: #fdf5e6; padding: 1mm 2mm; margin: 1mm 0; }
table.comp td:nth-child(4) { background: #f4f7fb; min-width: 20mm; font-weight: 600; } .vazio { display: inline-block; min-width: 18mm; }
"""


def html_memorial(an: dict, projeto: dict, nomes: Optional[Dict[str, str]] = None, eixos=None,
                  comparacao: Optional[dict] = None) -> str:
    nome = projeto.get("nome") or an.get("projeto") or ""
    p = an.get("parametros") or {}
    secoes = []

    def sec(titulo, corpo):
        if corpo:
            secoes.append((titulo, corpo))

    sec("Premissas", _premissas(an))
    sec("Cargas e vento", _vento(an) + "<h3>Casos de carga</h3>" + _casos(an))
    sec("Combinações", "<p>NBR 8800:2024 (ELU e ELS)%s.</p>" % (
        "; pré-moldado pela NBR 8681 (γ 1,3 no peso próprio pré-moldado)" if an.get("modelo_analise") == "premoldado" else "")
        + _combinacoes(an))
    sec("2ª ordem (NBR 8800:2024, 4.10.7)", _segunda_ordem(an))
    sec("Deslocamentos de serviço", _servico(an))
    situ = ""
    if an.get("outras_situacoes"):
        situ = "Situação %s" % ("aberta" if an.get("situacao") == "aberta" else an.get("situacao") or "principal")
    sec("Verificação das peças", _verificacao(an, nomes, situ))
    for k, outra in (an.get("outras_situacoes") or {}).items():
        sec("Situação %s: 2ª ordem e peças" % ("retraída" if k == "retraida" else k),
            _segunda_ordem(outra) + _verificacao(outra, nomes, "Situação %s" % ("retraída" if k == "retraida" else k)))
    sec("Reações nas bases", _reacoes(an, eixos))
    sec("Bases dos pilares (NBR 8800:2024, 6.7)", _bases(an, eixos) if an.get("bases") else "")
    sec("Apoio das tesouras", _carrinho(an))
    sec("Ligações viga–pilar", _ligacoes(an) if (an.get("ligacoes") or an.get("ligacoes_topo")) else "")
    ap = apontamentos(an)
    sec("Apontamentos", "".join("<p class=aviso>%s</p>" % _esc(a) for a in ap) if ap else "<p>Nenhum.</p>")
    if comparacao is not None:
        sec("Comparação com o engenheiro", html_comparacao(linhas_comparacao(an, eixos), comparacao))
    corpo = "".join("<h2>%d. %s</h2>%s" % (i + 1, t, c) for i, (t, c) in enumerate(secoes))
    indice = "<ol class=indice>%s</ol>" % "".join("<li>%s</li>" % t for t, _ in secoes)
    capa = ("<div class=capa><h1>Memorial da análise estrutural</h1><p><b>%s</b>%s</p>"
            "<p class=sub>Calculado em %s pelo Metálica %s · norma de referência ABNT NBR 8800:2024 com a Errata 1:2025, "
            "NBR 6123:2023 (vento), NBR 14762 (perfis formados a frio), NBR 16239:2013 (tubos), NBR 6118:2023 (ancoragem)</p>"
            "<p class=sub>Unidades: kN, kN·m, m e mm (as solicitantes das peças também em tf). N &gt; 0 tração. Os esforços das "
            "combinações últimas são de 2ª ordem quando a premissa está ligada.</p></div>") % (
        _esc(nome), " — %s" % _esc(projeto.get("local") or an.get("local")) if (projeto.get("local") or an.get("local")) else "",
        _esc(an.get("calculado_em") or "—"), _esc(an.get("programa") or ""))
    return ("<!doctype html><html lang=pt-BR><meta charset=utf-8><title>Memorial da análise - %s</title><style>%s</style>"
            "<body>%s%s%s</body></html>" % (_esc(nome), CSS, capa, indice, corpo))


def html_quadro(an: dict, projeto: dict, comparacao: dict, eixos=None) -> str:
    """só o quadro de comparação, para levar ao engenheiro (em branco ou preenchido)"""
    nome = projeto.get("nome") or an.get("projeto") or ""
    return ("<!doctype html><html lang=pt-BR><meta charset=utf-8><title>Comparação - %s</title><style>%s</style><body>"
            "<div class=capa><h1>Comparação com o engenheiro</h1><p><b>%s</b></p><p class=sub>Análise de %s (Metálica %s)</p></div>"
            "%s</body></html>" % (_esc(nome), CSS, _esc(nome), _esc(an.get("calculado_em") or "—"), _esc(an.get("programa") or ""),
                                  html_comparacao(linhas_comparacao(an, eixos), comparacao)))


def _imprimir(h: str, pdf: str):
    from saida.printpdf import navegador
    import subprocess
    subprocess.run([navegador(), "--headless=new", "--no-pdf-header-footer", "--print-to-pdf=" + pdf,
                    "file:///" + h.replace("\\", "/")], capture_output=True, timeout=300)


def gerar(pasta_projeto: str, an: dict, doc, projeto: dict, qual: str = "memorial") -> Dict[str, str]:
    """grava o HTML e o PDF em <projeto>/analise/: o memorial inteiro (com o quadro) ou só o quadro de comparação"""
    from saida.planta_cargas import eixos_do_projeto
    from saida.pecas_analise import nomes_dos_pilares
    pasta = os.path.join(pasta_projeto, "analise")
    os.makedirs(pasta, exist_ok=True)
    eixos = eixos_do_projeto(pasta_projeto)
    comp = ler_comparacao(pasta_projeto)
    if qual == "comparacao":
        texto, base = html_quadro(an, projeto, comp, eixos), "comparacao-com-o-engenheiro"
    else:
        try:
            nomes = nomes_dos_pilares(an, doc) if doc is not None else {}
        except Exception:                   # noqa: BLE001 — sem os nomes da planta de cargas, as marcas do modelo
            nomes = {}
        texto, base = html_memorial(an, projeto, nomes, eixos, comp), "memorial-da-analise"
    h = os.path.join(pasta, base + ".html")
    with open(h, "w", encoding="utf-8") as f:
        f.write(texto)
    pdf = os.path.join(pasta, base + ".pdf")
    _imprimir(h, pdf)
    return {"html": h, "pdf": pdf}
