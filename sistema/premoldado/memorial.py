# -*- coding: utf-8 -*-
"""Memorial de cálculo do galpão pré-moldado (PDF), no mesmo formato do memorial da parte metálica
(`saida/memorial.py`: capítulos numerados, sumário, a memória de cada verificação em passos)."""
from __future__ import annotations

import datetime
import os
from typing import List

from nucleo.base import fmt
from saida import memorial as M

from .concreto import BITOLAS
from .galpao import ProjetoGalpaoPM


def _svg_secao(b: float, h: float, arm, estribos, cobrimento: float) -> str:
    """a seção do pilar com as barras (h na horizontal, b na vertical), escala para ~60 mm"""
    esc = 5.0
    W, H = h * esc, b * esc
    pad = 30
    fi = arm.bitola / 10.0
    c = cobrimento + estribos[0] / 10.0 + fi / 2
    pts = []
    # faces "de cima e de baixo" da flexão em h (paralelas a b): n_h barras em cada — aqui ficam à esquerda e à direita
    for x in (c, h - c):
        for i in range(arm.n_h):
            y = c + i * (b - 2 * c) / max(arm.n_h - 1, 1)
            pts.append((x, y))
    for y in (c, b - c):
        for i in range(1, arm.n_b + 1):
            x = c + i * (h - 2 * c) / (arm.n_b + 1)
            pts.append((x, y))
    circ = "".join('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#1b2433"/>' % (pad + x * esc, pad + y * esc, max(fi * esc / 2, 2.5)) for x, y in pts)
    ce = cobrimento * esc
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" style="max-width:62mm">'
            '<rect x="%d" y="%d" width="%.1f" height="%.1f" fill="#eef2f8" stroke="#1b2433" stroke-width="1.5"/>'
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" stroke="#0b3d91" stroke-width="1" rx="4"/>%s'
            '<text x="%.1f" y="%d" font-size="12" text-anchor="middle">h = %s cm</text>'
            '<text x="%d" y="%.1f" font-size="12" text-anchor="middle" transform="rotate(-90 %d %.1f)">b = %s cm</text></svg>') % (
        W + 2 * pad, H + 2 * pad, W + 2 * pad, H + 2 * pad, pad, pad, W, H, pad + ce, pad + ce, W - 2 * ce, H - 2 * ce, circ,
        pad + W / 2, pad - 10, fmt(h, 0), pad - 12, pad + H / 2, pad - 12, pad + H / 2, fmt(b, 0))


def _svg_viga(v) -> str:
    """a seção da viga (a do meio do vão) com as barras de baixo e de cima"""
    pts = v.secao.contorno()
    xs = [x for x, _ in pts]
    W, H = max(xs) - min(xs), v.secao.h
    esc = min(5.0, 220.0 / max(W, H))
    pad = 30
    X = lambda x: pad + (x - min(xs)) * esc
    Y = lambda y: pad + (H - y) * esc
    a = v.armadura or {}
    circ = []
    c = 4.0
    base = [x for x, y in pts if y < 1e-6]
    larg = max(base) - min(base)

    def linha(n, fi, y, largura):
        for i in range(n):
            x = -largura / 2 + c + (i * (largura - 2 * c) / (n - 1) if n > 1 else (largura - 2 * c) / 2)
            circ.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#1b2433"/>' % (X(x), Y(y), max(fi / 10 * esc / 2, 2.5)))
    if a.get("n_inf"):
        cam = a.get("camadas", 1)
        por = -(-a["n_inf"] // cam)
        resto = a["n_inf"]
        for k in range(cam):
            linha(min(por, resto), a["fi_inf"], c + k * (a["fi_inf"] / 10 + 2), larg)
            resto -= por
    if a.get("n_sup"):
        if v.secao.tipo == "U":
            t = v.secao.parametros["t"]
            for x in (-W / 2 + t / 2, W / 2 - t / 2):
                circ.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#1b2433"/>' % (X(x), Y(H - c), max(a["fi_sup"] / 10 * esc / 2, 2.5)))
        else:
            topo = [x for x, y in pts if y >= H - 1e-6]
            linha(a["n_sup"], a["fi_sup"], H - c, max(topo) - min(topo))
    poli = " ".join("%.1f,%.1f" % (X(x), Y(y)) for x, y in pts)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" style="max-width:70mm">'
            '<polygon points="%s" fill="#eef2f8" stroke="#1b2433" stroke-width="1.5"/>%s'
            '<text x="%.1f" y="%d" font-size="12" text-anchor="middle">%s cm</text>'
            '<text x="%d" y="%.1f" font-size="12" text-anchor="middle" transform="rotate(-90 %d %.1f)">h = %s cm</text></svg>') % (
        W * esc + 2 * pad, H * esc + 2 * pad, W * esc + 2 * pad, H * esc + 2 * pad, poli, "".join(circ),
        pad + W * esc / 2, pad - 10, fmt(W, 0), pad - 12, pad + H * esc / 2, pad - 12, pad + H * esc / 2, fmt(H, 0))


def montar_html(p: ProjetoGalpaoPM) -> str:
    d = p.dados
    doc = M._Doc()
    # 1. dados
    doc.cap("Dados da obra e do sistema estrutural")
    doc.add(M._chave_valor([
        ("Obra", d.nome), ("Cliente", d.cliente or "—"), ("Local", d.local or "—"), ("Responsável técnico", d.responsavel or "—"),
        ("Vão transversal", "%s m" % fmt(d.vao, 2)), ("Vãos entre pórticos", " + ".join(fmt(v, 2) for v in d.vaos_longitudinais) + " m"),
        ("Comprimento", "%s m" % fmt(d.comprimento, 2)), ("Pórticos", str(d.n_porticos)),
        ("Altura dos pilares (acima da fundação)", "%s m" % fmt(d.altura_pilar, 2) if not d.filas_diferentes
         else "fila A %s m, fila B %s m" % (fmt(d.altura_pilar, 2), fmt(d.altura_b, 2))),
        ("Cobertura", "%s, apoiada no topo dos pilares (articulada), %s, inclinação %s°%s" % (
            "viga de cobertura em concreto em cada pórtico" if d.viga_cobertura else "estrutura metálica", d.cobertura,
            fmt(d.inclinacao_efetiva, 2), " (pelas alturas das filas)" if d.uma_agua else "")),
        ("Vigas longitudinais", {"nenhuma": "não há", "calha": "viga-calha em U nos consolos dos pilares",
                                 "travamento": "viga de travamento nos consolos dos pilares"}[d.vigas_longitudinais]
         + ("" if d.vigas_longitudinais == "nenhuma" else " (%s)" % d.extremidade_vigas)),
        ("Concreto", "C%s, agregado %s" % (fmt(d.fck, 0), d.agregado)), ("Aço", d.aco),
        ("Classe de agressividade", d.caa), ("Produção", "pré-fabricado (γc = 1,3; γs = 1,10)" if d.pre_fabricado else "pré-moldado (γc = 1,4; γs = 1,15)"),
    ], "Dados de entrada"))
    doc.fim_cap()
    # 2. normas e hipóteses
    doc.cap("Normas e hipóteses")
    doc.add("<ul>%s</ul>" % "".join("<li>%s</li>" % M._esc(n) for n in (
        "ABNT NBR 9062:2017 — Projeto e execução de estruturas de concreto pré-moldado",
        "ABNT NBR 6118:2023 (emenda 1:2026) — Projeto de estruturas de concreto",
        "ABNT NBR 6123 — Forças devidas ao vento em edificações",
        "ABNT NBR 8681 — Ações e segurança nas estruturas; ABNT NBR 6120 — Ações para o cálculo de estruturas")))
    doc.sec("Hipóteses")
    doc.add("<ul>%s</ul>" % "".join("<li>%s</li>" % M._esc(h) for h in p.hipoteses))
    doc.fim_cap()
    # 3. ações
    doc.cap("Ações")
    doc.add(M._chave_valor([("Cobertura (telha e estrutura)", "%s kN/m²" % fmt(d.cobertura_permanente, 2)),
                            ("Sobrecarga de cobertura", "%s kN/m²" % fmt(d.sobrecarga, 2)),
                            ("Fechamento lateral preso aos pilares", "%s kN/m²" % fmt(d.fechamento_lateral, 2)),
                            ("Peso específico do concreto armado", "25 kN/m³ (NBR 6118, 8.2.2)")], "Ações permanentes e variáveis"))
    v = p.vento
    if v:
        doc.sec("Vento")
        doc.add(M._chave_valor([("V0", "%s m/s" % fmt(v["V0"], 0)), ("S1", fmt(v["S1"], 2)), ("S2", fmt(v["S2"], 3)), ("S3", fmt(v["S3"], 2)),
                                ("Vk", "%s m/s" % fmt(v["Vk"], 1)), ("q", "%s kN/m²" % fmt(v["q"], 3))], "Velocidade e pressão dinâmica"))
        linhas = [[l["direção"], l["superfície"], fmt(l["Ce"], 2), fmt(l["Cpi"], 1), fmt(l["p (kN/m²)"], 3)] for l in v["tabela"] if not l.get("zona") or "restante" in l.get("zona", "")
                  or "água" in l.get("zona", "")]
        doc.tabela(["Direção", "Superfície", "Ce", "Cpi", "p (kN/m²)"], linhas, "Pressões de vento por superfície")
    doc.fim_cap()
    # 4. combinações
    from .galpao import combinacoes
    doc.cap("Combinações últimas")
    ventos = sorted({c for s in (p.pilares[0].esforcos.get("situacoes") or []) for c in [s["comb"]]}) if p.pilares else []
    doc.p("Combinações normais (NBR 8681): peso do pré-moldado γ = 1,3; cobertura e fechamento 1,4; sobrecarga 1,5 (ψ0 = 0,8); "
          "vento 1,4 (ψ0 = 0,6); com o vento de sucção, as permanentes favoráveis (γ = 1,0). Cada caso de vento nos dois sentidos, "
          "nas direções transversal e longitudinal, com Cpi = +0,2 e −0,3.")
    doc.fim_cap()
    # 5. pilares
    doc.cap("Pilares")
    for pil in p.pilares:
        doc.sec("Pilar %s — %s × %s cm, %s" % (pil.tipo, fmt(pil.b, 0), fmt(pil.h, 0), pil.armadura.texto()))
        sits = pil.esforcos.get("situacoes") or []
        doc.tabela(["Combinação", "Pórtico", "N<sub>d</sub> (kN)", "M<sub>x</sub> (kN·m)", "M<sub>y</sub> (kN·m)", "V<sub>x</sub> (kN)", "V<sub>y</sub> (kN)"],
                   [[M._esc(s["comb"]), str(s["portico"]), fmt(s["Nd"], 1), fmt(s["Mx"] / 100, 1), fmt(s["My"] / 100, 1),
                     fmt(s.get("Vx", 0), 1), fmt(s.get("Vy", 0), 1)] for s in sits],
                   "Situações que governam (momentos na base, 1ª ordem)")
        from .concreto import cobrimento
        doc.figura(_svg_secao(pil.b, pil.h, pil.armadura, pil.estribos, cobrimento(d.caa, "pilar", True)),
                   "Seção do pilar %s: %s, estribos ø%s c/ %s cm" % (pil.tipo, pil.armadura.texto(), fmt(pil.estribos[0], 1), fmt(pil.estribos[1], 1)))
        doc.add(M._resultado_html(pil.resultado, doc))
    doc.fim_cap()
    # vigas e consolos
    if p.vigas:
        doc.cap("Vigas")
        doc.p("Vigas biapoiadas de concreto armado (NBR 6118 e NBR 9062): flexão em todas as seções do vão, cisalhamento no apoio, "
              "abertura de fissuras (combinação frequente), flecha com a fluência (combinação quase permanente, limites das Tabelas 8 e 9 "
              "da NBR 9062), estabilidade lateral (6.1.6), içamento (5.3.2), o apoio (7.4 ou 7.5) e o aparelho de elastômero (7.2.1.6).")
        for v in p.vigas:
            doc.sec("%s %s — %s (%d un.)" % (v.funcao.capitalize(), v.marca, v.secao.texto(), v.quantidade))
            doc.figura(_svg_viga(v), "Seção %s: %s" % (v.secao.texto(), v.texto_armadura()))
            if v.alternativas and len(v.alternativas) > 1:
                doc.tabela(["Seção tentada", "Situação", "Razão"], [[M._esc(a["secao"]), "passa" if a["ok"] else "não passa",
                                                                      fmt(a["razao"], 2) if a["razao"] is not None else "—"] for a in v.alternativas],
                           "A mais leve que passa")
            for r in (v.resultado, v.apoio, v.elastomero):
                if r is not None:
                    doc.add(M._resultado_html(r, doc))
        doc.fim_cap()
    if p.ligacoes:
        doc.cap("Consolos dos pilares")
        if d.ponte_rolante:
            doc.p("Os consolos da ponte rolante têm a análise de fadiga obrigatória (NBR 9062, 7.3.1.3): a variação de tensão no tirante "
                  "(barra com solda, NBR 6118 Tabela 23.2) e a compressão na biela (23.5.4.1), na combinação frequente com ψ1 = 1,0.")
        for r in p.ligacoes:
            doc.sec(r.elemento)
            doc.add(M._resultado_html(r, doc))
        doc.fim_cap()
    if p.fundacoes:
        doc.cap("Fundações")
        doc.p("Sob o cálice, %s (NBR 6118, %s). O solo e as estacas com as combinações características (γ = 1); a estrutura com as "
              "situações últimas do pilar, com a 2ª ordem (NBR 9062, 7.7.1.1). Os dados geotécnicos são da obra (NBR 6122)."
              % ("sapata rígida" if d.fundacao == "sapata" else "bloco rígido sobre estacas", "22.6" if d.fundacao == "sapata" else "22.7"))
        for r in p.fundacoes:
            doc.sec(r.elemento)
            if r.dados.get("armadura"):
                doc.p("Armadura: %s." % M._esc(r.dados["armadura"]))
            doc.add(M._resultado_html(r, doc))
        doc.fim_cap()
    # 6. cálices
    doc.cap("Ligação com a fundação — cálices")
    for r in p.calices:
        doc.sec(r.elemento)
        doc.add(M._resultado_html(r, doc))
    doc.fim_cap()
    # 7. transitórias e serviço
    doc.cap("Situações transitórias e estado-limite de serviço")
    for r in p.icamento:
        doc.sec(r.elemento)
        doc.add(M._resultado_html(r, doc))
    doc.fim_cap()
    # 8. lista
    doc.cap("Lista de peças")
    doc.tabela(["Marca", "Peça", "Qtd.", "Comprimento (m)", "Concreto (m³/un.)", "Peso (kN/un.)", "Aço (kg/un.)", "Armadura"],
               [[l["marca"], M._esc(l["descricao"]), str(l["quantidade"]), fmt(l["comprimento_m"], 2), fmt(l["volume_m3"], 3),
                 "—" if l["peso_kN"] is None else fmt(l["peso_kN"], 1), "—" if l["aco_kg"] is None else fmt(l["aco_kg"], 1), M._esc(l["armadura"])]
                for l in p.lista], "Peças pré-moldadas")
    tot_v = sum(l["volume_m3"] * l["quantidade"] for l in p.lista)
    tot_a = sum((l["aco_kg"] or 0) * l["quantidade"] for l in p.lista)
    doc.p("Total: <b>%s m³</b> de concreto e <b>%s kg</b> de aço nas peças (os cálices com a armadura da memória)." % (fmt(tot_v, 2), fmt(tot_a, 0)))
    doc.fim_cap()
    # 9. conclusão
    doc.cap("Conclusão e pendências")
    ok = p.ok
    doc.add(M._box("Todas as verificações atendem." if ok else "Há verificações que não atendem — ver os capítulos anteriores.",
                   "Situação", "ok" if ok else "erro"))
    doc.add("<ul>%s</ul>" % "".join("<li>%s</li>" % M._esc(t) for t in (
        "A cobertura metálica e a ligação dela no topo do pilar (chumbadores, cintamento do topo — NBR 9062, 6.2.3) são verificadas no módulo metálico."
        if not d.viga_cobertura else "As terças e a telha sobre a viga de cobertura são verificadas à parte (módulo metálico ou terças pré-moldadas).",
        "O chumbador (pino) dos apoios das vigas é verificado ao corte só no aço — a NBR 9062 não traz essa conta; conferir o efeito pino no concreto."
        if p.vigas else "",
        "O bloco ou a sapata sob o cálice ainda não entram neste cálculo (escolha a fundação na tela)." if not p.fundacoes else
        "Fundação: a tensão admissível do solo, a carga das estacas e o comprimento delas vêm da sondagem (NBR 6122) — confira.",
        "As armaduras do colarinho seguem o modelo da Figura 27 da NBR 9062 com braços adotados pelo programa — conferir.",
        "Os dispositivos de içamento dos pilares (alças) com βa = 3 (NBR 9062, 5.3.2/5.3.3) devem ser especificados no detalhamento.") if t))
    doc.fim_cap()
    css = open(os.path.join(os.path.dirname(M.__file__), "memorial.css"), encoding="utf-8").read()
    capa = ('<section class="capa"><h1>Memorial de cálculo</h1><h2>%s</h2><p>Estrutura de concreto pré-moldado — pilares engastados em cálice</p>'
            '<p>%s</p><p class="pequeno">%s · módulo pré-moldado (em desenvolvimento)</p></section>') % (
        M._esc(d.nome), M._esc(d.local or ""), datetime.date.today().strftime("%d/%m/%Y"))
    from saida import printpdf
    return printpdf.envelope(capa + doc.sumario() + doc.corpo(), css, "Memorial de cálculo — %s" % d.nome)


def gerar(p: ProjetoGalpaoPM, pasta: str, nome: str = "Memorial_pre-moldado.pdf") -> str:
    from saida import printpdf
    os.makedirs(pasta, exist_ok=True)
    html_path = os.path.join(pasta, "memorial_pre-moldado.html")
    open(html_path, "w", encoding="utf-8").write(montar_html(p))
    pdf = os.path.join(pasta, nome)
    printpdf.imprimir(html_path, pdf)
    return os.path.abspath(pdf)
