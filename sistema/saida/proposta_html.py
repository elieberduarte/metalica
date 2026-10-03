# -*- coding: utf-8 -*-
"""A proposta técnica comercial em PDF, com cara de material comercial: capa com a imagem do modelo 3D,
ficha técnica da obra, galeria, escopo em blocos, condições lado a lado, investimento em destaque,
linha do tempo da obra e o "de acordo" do cliente. O conteúdo (textos, escopo, condições) é o das
propostas da empresa; a forma é nova. Paginação pelo Paged.js (saida/printpdf.py)."""
import html
import os
from datetime import timedelta
from typing import List, Optional
from urllib.parse import quote

from saida.comercial import _f, data_extenso, extenso_reais, ler_data, num, reais


def _e(t) -> str:
    return html.escape(str(t if t is not None else ""))


def _rico(t) -> str:
    """**negrito** e __sublinhado__ dentro do texto escapado."""
    import re
    s = _e(t)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"__(.+?)__", r"<u>\1</u>", s)
    return s


def _url(caminho: str) -> str:
    return "file:///" + quote(os.path.abspath(caminho).replace("\\", "/")) if caminho else ""


def _cor(empresa, k, padrao):
    return ((empresa.get("cores") or {}).get(k) or padrao)


CSS = """
@page { size: A4; margin: 24mm 16mm 20mm 16mm;
  @top-left { content: element(cabecalho); vertical-align: bottom; padding-bottom: 4mm; }
  @top-right { content: element(cabref); vertical-align: bottom; padding-bottom: 4mm; }
  @bottom-left { content: element(rodape); vertical-align: top; padding-top: 3mm; }
  @bottom-right { content: counter(page) " / " counter(pages); font: 600 8pt 'Segoe UI', Arial, sans-serif; color: var(--mudo);
                  vertical-align: top; padding-top: 3mm; }
}
@page capa { margin: 0; @top-left { content: none; } @top-right { content: none; } @bottom-left { content: none; } @bottom-right { content: none; } }
:root { --pri: %(pri)s; --pri2: %(pri2)s; --dest: %(dest)s; --fundo: #f3f5f6; --linha: #dde3e7; --texto: #26323a; --mudo: #6b7780; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font: 9.6pt/1.5 'Segoe UI', 'Segoe UI Variable', Arial, sans-serif; color: var(--texto); }
.cabecalho { position: running(cabecalho); }
.cabecalho img { height: 7mm; display: block; }
.cabref { position: running(cabref); font: 600 7.6pt 'Segoe UI', Arial; color: var(--mudo); letter-spacing: .06em; text-transform: uppercase; text-align: right; }
.cabref b { color: var(--pri); }
.rodape { position: running(rodape); font: 7.6pt 'Segoe UI', Arial; color: var(--mudo); }
.rodape b { color: var(--pri); font-weight: 600; letter-spacing: .02em; }

/* ---------------- capa */
.capa { page: capa; width: 210mm; height: 297mm; position: relative; overflow: hidden; background: var(--pri2); color: #fff; break-after: page; }
.capa .foto { position: absolute; inset: 0 0 34%% 0; background: #e9eef3 center / cover no-repeat; }
.capa .foto::after { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(20,28,33,.38) 0%%, rgba(20,28,33,0) 22%%, rgba(20,28,33,0) 55%%, var(--pri2) 100%%); }
.capa .topo { position: absolute; top: 14mm; left: 16mm; right: 16mm; display: flex; justify-content: space-between; align-items: center; z-index: 2; }
.capa .topo img { height: 10mm; }
.capa .topo .num { font: 600 8pt 'Segoe UI', Arial; letter-spacing: .16em; text-transform: uppercase; color: rgba(255,255,255,.85);
                   border: 1px solid rgba(255,255,255,.45); padding: 1.6mm 3.2mm; border-radius: 99px; backdrop-filter: blur(2px); }
.capa .baixo { position: absolute; left: 16mm; right: 16mm; bottom: 16mm; z-index: 2; }
.capa .marca { display: flex; gap: 2.2mm; margin-bottom: 7mm; }
.capa .marca i { width: 9mm; height: 3mm; background: var(--dest); transform: skewX(-38deg); display: block; }
.capa .marca i + i { opacity: .55; }
.capa .rotulo { font: 600 8.5pt 'Segoe UI', Arial; letter-spacing: .28em; text-transform: uppercase; color: var(--dest); }
.capa h1 { font: 300 30pt/1.08 'Segoe UI Light', 'Segoe UI', Arial; margin: 3mm 0 0; letter-spacing: -.01em; }
.capa h2 { font: 700 21pt/1.15 'Segoe UI', Arial; margin: 5mm 0 0; color: #fff; }
.capa .cli { margin-top: 4mm; font-size: 11pt; color: rgba(255,255,255,.82); }
.capa .faixa { margin-top: 12mm; padding-top: 5mm; border-top: 1px solid rgba(255,255,255,.18); display: flex; justify-content: space-between;
               font-size: 8.4pt; color: rgba(255,255,255,.72); }
.capa .faixa b { color: #fff; font-weight: 600; }
.capa .slogan { font: 300 13pt 'Segoe UI Light', 'Segoe UI', Arial; color: #fff; letter-spacing: .01em; }

/* ---------------- tipografia das páginas */
.secao { break-before: page; }
.titulo-secao { display: flex; align-items: flex-end; gap: 5mm; margin: 0 0 7mm; padding-bottom: 3.5mm; border-bottom: 1.2px solid var(--linha); }
.titulo-secao .n { font: 300 30pt/0.9 'Segoe UI Light', 'Segoe UI', Arial; color: var(--dest); }
.titulo-secao h2 { margin: 0; font: 700 16pt/1.1 'Segoe UI', Arial; color: var(--pri); letter-spacing: -.005em; }
.titulo-secao small { display: block; font: 600 7.6pt 'Segoe UI', Arial; color: var(--mudo); letter-spacing: .18em; text-transform: uppercase; margin-bottom: 1.4mm; }
h3 { font: 700 10.5pt 'Segoe UI', Arial; color: var(--pri); margin: 6mm 0 2.5mm; break-after: avoid; }
h3 .tag { font: 600 7pt 'Segoe UI', Arial; color: var(--mudo); letter-spacing: .14em; text-transform: uppercase; margin-right: 2mm; }
p { margin: 0 0 2.6mm; text-align: justify; }
.carta .data { text-align: right; color: var(--mudo); margin-bottom: 7mm; }
.carta .dest b { font-size: 10.5pt; color: var(--pri); }
.carta .ref { margin: 6mm 0 5mm; padding: 3mm 4mm; background: var(--fundo); border-left: 3px solid var(--dest); font-weight: 600; color: var(--pri); }
.quem { margin-top: 9mm; display: grid; grid-template-columns: 1fr 1.15fr; gap: 7mm; break-inside: avoid; }
.quem .bloco { background: var(--pri); color: #fff; border-radius: 3mm; padding: 7mm 7mm 6mm; position: relative; overflow: hidden; }
.quem .bloco::after { content: ""; position: absolute; right: -8mm; top: -6mm; width: 34mm; height: 9mm; background: var(--dest); transform: skewX(-38deg); opacity: .9; }
.quem .bloco h4 { margin: 0 0 3mm; font: 600 7.6pt 'Segoe UI', Arial; letter-spacing: .2em; text-transform: uppercase; color: var(--dest); }
.quem .bloco p { color: rgba(255,255,255,.9); font-size: 10.5pt; line-height: 1.55; text-align: left; }
.dif { list-style: none; padding: 0; margin: 0; }
.dif li { display: grid; grid-template-columns: 7mm 1fr; gap: 2mm; padding: 2.6mm 0; border-bottom: 1px solid var(--linha); }
.dif li:last-child { border-bottom: 0; }
.dif li::before { content: ""; width: 5mm; height: 5mm; border-radius: 50%%; margin-top: .4mm;
                  background: var(--dest) url("data:image/svg+xml,%%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'%%3E%%3Cpath d='M5 10.5l3 3 7-7' fill='none' stroke='%%2335434C' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'/%%3E%%3C/svg%%3E") center/70%% no-repeat; }

/* ---------------- projeto */
.heroi { width: 100%%; height: 80mm; border-radius: 3mm; background: #eef2f6 center / cover no-repeat; margin-bottom: 6mm; }
.ficha { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; margin-bottom: 5mm; break-inside: avoid; }
.ficha div { background: var(--fundo); border-radius: 2.5mm; padding: 3mm 4mm 2.8mm; border-top: 2.5px solid var(--dest); }
.ficha b { display: block; font: 300 17pt/1.1 'Segoe UI Light', 'Segoe UI', Arial; color: var(--pri); }
.ficha b small { font-size: 9pt; font-weight: 600; color: var(--mudo); margin-left: 1mm; }
.ficha span { font: 600 7.2pt 'Segoe UI', Arial; color: var(--mudo); letter-spacing: .14em; text-transform: uppercase; }
/* a galeria é um bloco só: o Paged.js entrava em laço ao partir a grade entre páginas (03/10) */
.galeria { display: grid; grid-template-columns: 1fr 1fr; gap: 3.5mm; break-inside: avoid; }
.galeria figure { margin: 0; }
.galeria .img { height: 46mm; border-radius: 2.5mm; background: #eef2f6 center / cover no-repeat; }
.galeria figcaption { font-size: 7.8pt; color: var(--mudo); margin-top: 1.4mm; }
.nota3d { font-size: 7.6pt; color: var(--mudo); margin-top: 3mm; }

/* ---------------- escopo */
table.t { width: 100%%; border-collapse: collapse; margin: 1mm 0 4mm; font-size: 8.8pt; }
table.t th { text-align: left; font: 600 7.4pt 'Segoe UI', Arial; letter-spacing: .1em; text-transform: uppercase; color: var(--mudo);
             border-bottom: 1.2px solid var(--pri); padding: 1.8mm 2mm; }
table.t td { padding: 2mm; border-bottom: 1px solid var(--linha); vertical-align: top; }
table.t td.r, table.t th.r { text-align: right; white-space: nowrap; }
table.t tr.total td { font-weight: 700; color: var(--pri); border-bottom: 0; }
table.t tr { break-inside: avoid; }
.blocos .bloco { border: 1px solid var(--linha); border-radius: 2.5mm; padding: 4mm 5mm 2.5mm; margin-bottom: 4mm; break-inside: avoid-page; }
.blocos .bloco h4 { margin: 0 0 2.5mm; font: 700 9.6pt 'Segoe UI', Arial; color: var(--pri); display: flex; align-items: center; gap: 2.4mm; }
.blocos .bloco h4::before { content: ""; width: 4mm; height: 1.6mm; background: var(--dest); transform: skewX(-38deg); }
ul.itens { margin: 0; padding: 0; list-style: none; }
ul.itens li { position: relative; padding: 0 0 1.6mm 5mm; }
ul.itens li::before { content: ""; position: absolute; left: .6mm; top: 2.1mm; width: 1.6mm; height: 1.6mm; background: var(--pri); border-radius: 50%%; }
ul.itens li.dest { font-weight: 600; color: var(--pri); }
ul.itens li.dest::before { background: var(--dest); }

/* ---------------- condições */
.colunas { display: grid; grid-template-columns: 1fr 1fr; gap: 6mm; margin-top: 3mm; }
.cartao { background: var(--fundo); border-radius: 3mm; padding: 5mm 5mm 3mm; break-inside: avoid; }
.cartao h4 { margin: 0 0 3mm; font: 700 9.4pt 'Segoe UI', Arial; color: var(--pri); }
ul.marcas { margin: 0; padding: 0; list-style: none; font-size: 8.6pt; }
.cartao.largo { margin-top: 5mm; break-inside: auto; }
.cartao.largo ul.marcas { columns: 2; column-gap: 7mm; }
.cartao.largo ul.marcas li { break-inside: avoid; }
ul.marcas li { display: grid; grid-template-columns: 5.5mm 1fr; gap: 1.2mm; padding: 1.2mm 0; }
ul.marcas li::before { content: "✓"; font-weight: 700; color: #7c9a1f; }
ul.marcas.nao li::before { content: "✕"; color: #b4483c; }
ul.marcas.contr li::before { content: "→"; color: var(--pri); }

/* ---------------- investimento */
.valor { background: var(--pri); color: #fff; border-radius: 3.5mm; padding: 7mm 9mm 6mm; position: relative; overflow: hidden; break-inside: avoid; }
.valor::before { content: ""; position: absolute; right: 9mm; top: 8mm; width: 14mm; height: 4.5mm; background: var(--dest); transform: skewX(-38deg); }
.valor::after { content: ""; position: absolute; right: 26mm; top: 8mm; width: 14mm; height: 4.5mm; background: var(--dest); opacity: .5; transform: skewX(-38deg); }
.valor small { font: 600 7.8pt 'Segoe UI', Arial; letter-spacing: .22em; text-transform: uppercase; color: var(--dest); }
.valor .v { font: 300 32pt/1.1 'Segoe UI Light', 'Segoe UI', Arial; margin: 3mm 0 1.5mm; letter-spacing: -.01em; }
.valor .ext { color: rgba(255,255,255,.78); font-size: 9.4pt; }
.valor .ind { display: flex; gap: 9mm; margin-top: 6mm; padding-top: 4mm; border-top: 1px solid rgba(255,255,255,.18); font-size: 8.4pt; color: rgba(255,255,255,.7); }
.valor .ind b { display: block; color: #fff; font-size: 11.5pt; font-weight: 600; }
.notas { font-size: 7.8pt; color: var(--mudo); font-style: italic; margin-top: 3mm; }
.notas p { margin: 0 0 1.2mm; }
.duas { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; margin-top: 4mm; break-inside: avoid; }
.duas .cartao p { margin: 0; text-align: left; }
.validade { display: inline-flex; gap: 2mm; align-items: center; margin-top: 5mm; padding: 2mm 4mm; border-radius: 99px; background: #eef4d5;
            color: #4f5f12; font: 600 8.4pt 'Segoe UI', Arial; }
.linha-tempo { display: grid; grid-template-columns: repeat(6, 1fr); margin: 5mm 0 0; position: relative; break-inside: avoid; }
.linha-tempo::before { content: ""; position: absolute; left: 6%%; right: 6%%; top: 4.6mm; height: 1.2px; background: var(--linha); }
.linha-tempo div { text-align: center; position: relative; padding: 0 1mm; }
.linha-tempo i { display: block; width: 9.2mm; height: 9.2mm; margin: 0 auto 2mm; border-radius: 50%%; background: #fff; border: 1.6px solid var(--pri);
                 font: 700 8.6pt/8.6mm 'Segoe UI', Arial; color: var(--pri); font-style: normal; }
.linha-tempo div:last-child i { background: var(--dest); border-color: var(--dest); }
.linha-tempo b { display: block; font-size: 8.4pt; color: var(--pri); }
.linha-tempo span { font-size: 7.4pt; color: var(--mudo); }

/* ---------------- aceite */
.fim { break-inside: avoid; }
.aceite { margin-top: 6mm; border: 1.4px solid var(--pri); border-radius: 3mm; padding: 6mm 7mm; break-inside: avoid; }
.aceite h4 { margin: 0 0 2mm; font: 700 10.5pt 'Segoe UI', Arial; color: var(--pri); }
.assin { display: grid; grid-template-columns: 1fr 1fr; gap: 12mm; margin-top: 12mm; }
.assin div { border-top: 1px solid var(--texto); padding-top: 2mm; font-size: 8.4pt; }
.assin b { display: block; color: var(--pri); }
.empresa { margin-top: 5mm; display: flex; justify-content: space-between; gap: 6mm; font-size: 7.8pt; color: var(--mudo); border-top: 1px solid var(--linha); padding-top: 4mm; }
.empresa b { color: var(--pri); }
"""


def _ficha(P: dict, numeros: Optional[dict], orc: Optional[dict]) -> List[tuple]:
    itens = []
    area = sum(_f(g.get("area")) or 0 for g in P.get("geometria") or [])
    if area:
        itens.append((num(area, 2), "m²", "Área coberta"))
    peso = _f(P.get("peso_kg"))
    if peso:
        itens.append((num(peso, 0), "kg", "Aço estrutural"))
    nr = (numeros or {}).get("numeros") or {}
    trechos = ((numeros or {}).get("dimensoes") or {}).get("trechos") or []
    vao = max((float(t.get("vao") or 0) for t in trechos), default=0.0) / 1000.0
    if vao:
        itens.append((num(vao, 2), "m", "Vão livre"))
    if nr.get("tesouras"):
        itens.append((str(int(nr["tesouras"])), "", "Tesouras"))
    tot = (orc or {}).get("totais") or {}
    if tot.get("telhas_ml"):
        itens.append((num(tot["telhas_ml"], 0), "m", "Telhas"))
    if area and peso:
        itens.append((num(peso / area, 1), "kg/m²", "Consumo de aço"))
    return itens[:6]


def html_proposta(P: dict, empresa: dict, numeros: Optional[dict] = None, orc: Optional[dict] = None) -> str:
    pri = _cor(empresa, "primaria", "#35434C")
    css = CSS % {"pri": pri, "pri2": "#1f2a31", "dest": _cor(empresa, "destaque", "#C3D773")}
    cli, obra, inv = P.get("cliente") or {}, P.get("obra") or {}, P.get("investimento") or {}
    nome_emp = empresa.get("nome_comercial") or empresa.get("razao_social") or ""
    d = ler_data(P.get("data"))
    data_txt = data_extenso(d) if d else _e(P.get("data"))
    numero = " · ".join(x for x in (("Nº " + P["numero"]) if P.get("numero") else "", P.get("revisao") or "") if x)
    imagens = [i for i in P.get("imagens") or [] if i.get("arquivo") and os.path.exists(i["arquivo"])]
    def _achar(*nomes):
        for n_ in nomes:
            for i in imagens:
                if os.path.splitext(os.path.basename(i["arquivo"]))[0] == n_:
                    return i
        return None
    capa_img = _achar("capa", "aerea_frente", "aerea_tras") or (imagens[0] if imagens else None)
    foto_da_capa = capa_img
    if capa_img and os.path.splitext(os.path.basename(capa_img["arquivo"]))[0] == "capa":
        imagens = [i for i in imagens if i is not capa_img]          # a foto da capa não se repete na galeria
        capa_img = _achar("aerea_frente")
    logo, logo_claro = empresa.get("logo") or "", empresa.get("logo_claro") or empresa.get("logo") or ""
    local_obra = " - ".join(x for x in (obra.get("cidade"), obra.get("uf")) if x)
    partes = []

    # ---- capa
    partes.append('<section class="capa"><div class="foto" style="background-image:url(\'%s\')"></div>'
                  '<div class="topo">%s<span class="num">%s</span></div>'
                  '<div class="baixo"><div class="marca"><i></i><i></i></div>'
                  '<div class="rotulo">Proposta técnica e comercial</div>'
                  '<h1>Estrutura metálica%s</h1><h2>%s</h2><div class="cli">%s</div>'
                  '<div class="faixa"><span class="slogan">%s</span><span><b>%s</b>%s</span></div></div></section>' % (
                      _url(foto_da_capa["arquivo"]) if foto_da_capa else "",
                      ('<img src="%s">' % _url(logo_claro)) if logo_claro else "<b>%s</b>" % _e(nome_emp), _e(numero),
                      (" — " + _e(P["opcao"])) if P.get("opcao") else "", _e(obra.get("nome") or ""),
                      _e(" · ".join(x for x in (cli.get("nome"), local_obra) if x)), _e(empresa.get("slogan") or ""),
                      _e(data_txt), ("  ·  " + _e(empresa.get("site"))) if empresa.get("site") else ""))

    # ---- elementos correntes (depois da capa: antes dela abriam uma página em branco)
    partes.append('<div class="cabecalho">%s</div>' % (('<img src="%s">' % _url(logo)) if logo else "<b>%s</b>" % _e(nome_emp)))
    partes.append('<div class="cabref">Proposta <b>%s</b> · %s</div>' % (_e(P.get("numero") or ""), _e(P.get("revisao") or "")))
    partes.append('<div class="rodape"><b>%s</b>%s</div>' % (_e(empresa.get("slogan") or nome_emp),
                                                          ("  ·  " + _e(empresa.get("site"))) if empresa.get("site") else ""))

    # ---- carta + quem somos
    dest = "<b>%s</b>" % _e((cli.get("nome") or "").upper())
    if cli.get("contato"):
        dest += "<br>A/C %s" % _e(cli["contato"])
    loc_cli = " - ".join(x for x in (cli.get("cidade"), cli.get("uf")) if x)
    if loc_cli:
        dest += "<br>%s" % _e(loc_cli)
    difs = "".join("<li>%s</li>" % _e(x) for x in empresa.get("diferenciais") or [])
    partes.append('<section class="carta"><div class="data">%s%s.</div><div class="dest">%s</div>'
                  '<div class="ref">Ref.: %s</div><p>Prezados Senhores,</p>'
                  '<p>Conforme vossa solicitação, apresentamos nossa proposta técnica comercial para execução de estrutura '
                  'metálica, para a obra a ser executada em <b>%s</b>%s.</p>'
                  '<p>Nas próximas páginas estão o modelo da estrutura, o escopo detalhado, as condições e o investimento. '
                  'Ficamos à disposição para apresentar a proposta e ajustar o que for preciso.</p>'
                  '<div class="quem"><div class="bloco"><h4>Quem somos</h4><p>%s</p></div><ul class="dif">%s</ul></div></section>' % (
                      _e(P.get("cidade_emissao") + ", ") if P.get("cidade_emissao") else "", _e(data_txt), dest,
                      _e(P.get("ref") or ""), _e(local_obra or "—"), (" (%s)" % _e(P["opcao"])) if P.get("opcao") else "",
                      _e(empresa.get("apresentacao") or ""), difs))

    # ---- 01 o projeto
    secao = 1
    if imagens or P.get("mostrar_ficha", True):
        ficha = _ficha(P, numeros, orc) if P.get("mostrar_ficha", True) else []
        heroi = _achar("perspectiva", "aerea_frente_telhas", "lateral") or next((i for i in imagens if i is not capa_img), capa_img)
        # uma fileira da galeria (duas imagens): com a ficha e o destaque, a página fecha sem sobrar foto para a seguinte
        outras = [i for i in imagens if i is not heroi and i is not capa_img][:2 if ficha else 4]
        h = ['<section class="secao"><div class="titulo-secao"><span class="n">%02d</span><div><small>O projeto</small><h2>%s</h2></div></div>'
             % (secao, _e(obra.get("nome") or "A estrutura"))]
        if heroi:
            h.append('<div class="heroi" style="background-image:url(\'%s\')"></div>' % _url(heroi["arquivo"]))
        if ficha:
            h.append('<div class="ficha">%s</div>' % "".join('<div><b>%s<small>%s</small></b><span>%s</span></div>' % (_e(v), _e(u), _e(r))
                                                            for v, u, r in ficha))
        if outras:
            h.append('<div class="galeria">%s</div>' % "".join('<figure><div class="img" style="background-image:url(\'%s\')"></div>'
                                                               '<figcaption>%s</figcaption></figure>' % (_url(i["arquivo"]), _e(i.get("legenda") or ""))
                                                               for i in outras))
        if imagens:
            h.append('<p class="nota3d">Imagens geradas do modelo 3D da estrutura, usado no projeto e na fabricação. Ilustrativas: '
                     'cores e acabamentos conforme especificado no escopo.</p>')
        h.append("</section>")
        partes.append("".join(h))
        secao += 1

    # ---- 02 escopo
    h = ['<section class="secao"><div class="titulo-secao"><span class="n">%02d</span><div><small>Detalhamento de escopo</small>'
         '<h2>O que vamos entregar</h2></div></div><p>%s</p>' % (secao, _e(_escopo_intro()))]
    sub = 1
    h.append('<h3><span class="tag">%d.%d</span>Projetos</h3><p>%s</p>' % (secao, sub, _e(
        "O projeto da estrutura metálica será elaborado por profissional habilitado, atendendo as normas brasileiras vigentes."
        if P.get("projeto_por") != "cliente" else
        "Esta proposta foi elaborada com base nos projetos e quantitativos enviados pelo cliente.")))
    car = [c for c in P.get("carregamentos") or [] if c.get("descricao")]
    if car:
        sub += 1
        h.append('<h3><span class="tag">%d.%d</span>Carregamentos</h3><table class="t"><tr><th>Carga</th><th>Descrição</th></tr>%s'
                 '<tr><td colspan="2"><i>Ações de vento conforme NBR 6123/2023</i></td></tr></table>'
                 % (secao, sub, "".join("<tr><td>%s</td><td>%s</td></tr>" % (_e(c.get("carga")), _e(c.get("descricao"))) for c in car)))
    geo = P.get("geometria") or []
    if geo:
        sub += 1
        tot = sum(_f(g.get("area")) or 0 for g in geo)
        h.append('<h3><span class="tag">%d.%d</span>Geometria das estruturas</h3><table class="t"><tr><th>Estrutura</th>'
                 '<th class="r">Largura</th><th class="r">Comprimento</th><th class="r">Área</th></tr>%s%s</table>' % (
                     secao, sub, "".join('<tr><td>%s</td><td class="r">%s</td><td class="r">%s</td><td class="r">%s m²</td></tr>' % (
                         _e(g.get("nome")), (num(g["largura"]) + " m") if _f(g.get("largura")) else "—",
                         (num(g["comprimento"]) + " m") if _f(g.get("comprimento")) else "—", num(g.get("area")) if _f(g.get("area")) else "—")
                         for g in geo),
                     ('<tr class="total"><td>Área total</td><td></td><td></td><td class="r">%s m²</td></tr>' % num(tot)) if len(geo) > 1 else ""))
    sub += 1
    blocos = "".join('<div class="bloco"><h4>%s</h4><ul class="itens">%s</ul></div>' % (
        _e(b.get("titulo") or "Estrutura"), "".join('<li class="%s">%s</li>' % ("dest" if i.get("destaque") else "", _rico(i.get("texto")))
                                                    for i in b.get("itens") or [] if i.get("texto")))
        for b in P.get("escopo") or [])
    h.append('<h3><span class="tag">%d.%d</span>Estrutura metálica</h3><div class="blocos">%s</div>' % (secao, sub, blocos))
    if _f(P.get("peso_kg")):
        h.append('<p class="nota3d">Peso de estrutura considerado: %s kg (peso teórico do modelo).</p>' % num(P["peso_kg"], 2))
    h.append("</section>")
    partes.append("".join(h))
    secao += 1

    # ---- 03 condições
    cond = "".join("<li>%s</li>" % _rico(x) for x in P.get("condicoes") or [])
    seg = "".join("<li>%s</li>" % _rico(x) for x in P.get("seguranca") or [])
    exc = "".join("<li>%s</li>" % _rico(x) for x in P.get("exclusoes") or [])
    resp = "".join("<li>%s</li>" % _rico(x) for x in P.get("responsabilidades") or [])
    partes.append('<section class="secao"><div class="titulo-secao"><span class="n">%02d</span><div><small>Condições</small>'
                  '<h2>Condições gerais, exclusões e responsabilidades</h2></div></div>'
                  '<div class="colunas"><div class="cartao"><h4>Condições gerais</h4><ul class="marcas">%s</ul></div>'
                  '<div class="cartao"><h4>Proteção e segurança</h4><ul class="marcas">%s</ul></div></div>'
                  '<div class="cartao largo"><h4>Não incluso nesta proposta</h4><ul class="marcas nao">%s</ul></div>'
                  '<div class="cartao largo"><h4>Por conta do contratante</h4><ul class="marcas contr">%s</ul></div></section>'
                  % (secao, cond, seg, exc, resp))
    secao += 1

    # ---- 04 investimento
    valor = _f(inv.get("valor"))
    area = sum(_f(g.get("area")) or 0 for g in geo)
    ind = []
    if valor and area:
        ind.append(("%s/m²" % reais(valor / area), "por m² de área coberta"))
    if valor and _f(P.get("peso_kg")):
        ind.append(("%s/kg" % reais(valor / _f(P["peso_kg"])), "por kg de aço"))
    h = ['<section class="secao"><div class="titulo-secao"><span class="n">%02d</span><div><small>Investimento</small>'
         '<h2>Investimento e condições comerciais</h2></div></div>' % secao]
    h.append('<div class="valor"><small>Investimento total</small><div class="v">%s</div><div class="ext">%s</div>%s</div>' % (
        reais(valor) if valor else "A definir", _e(("(" + extenso_reais(valor).capitalize() + ")") if valor else ""),
        ('<div class="ind">%s</div>' % "".join("<span><b>%s</b>%s</span>" % (_e(a), _e(b)) for a, b in ind)) if ind else ""))
    h.append('<p style="margin-top:4mm">Para execução do escopo – item %d desta proposta – o investimento total será de <b>%s</b>.</p>'
             % (2 if imagens or P.get("mostrar_ficha", True) else 1, reais(valor) if valor else "a definir"))
    if inv.get("partes"):
        h.append('<table class="t"><tr><th>Composição</th><th class="r">Valor</th></tr>%s</table>' % "".join(
            '<tr><td>%s</td><td class="r">%s</td></tr>' % (_e(p.get("descricao")), reais(p.get("valor"))) for p in inv["partes"] if p.get("descricao")))
    if inv.get("opcionais"):
        h.append('<h3>Opcionais</h3><table class="t"><tr><th>Item</th><th class="r">Investimento total com o item</th></tr>%s</table>' % "".join(
            '<tr><td>%s</td><td class="r">%s</td></tr>' % (_e(o.get("descricao")), reais(o.get("valor"))) for o in inv["opcionais"] if o.get("descricao")))
    notas = list(inv.get("notas") or [])
    from saida.comercial import NOTA_ANTIDUMPING
    if NOTA_ANTIDUMPING not in notas:
        notas.append(NOTA_ANTIDUMPING)
    h.append('<div class="notas">%s</div>' % "".join("<p>%s</p>" % _e(n_) for n_ in notas))
    parcelas = [p for p in P.get("parcelas") or [] if _f(p.get("valor"))]
    if parcelas:
        pag = '<table class="t"><tr><th>Parcela</th><th>Vencimento</th><th class="r">Valor</th></tr>%s</table>' % "".join(
            '<tr><td>%s</td><td>%s</td><td class="r">%s</td></tr>' % (_e(p.get("descricao")), _e(p.get("vencimento")), reais(p.get("valor")))
            for p in parcelas)
    else:
        pag = "<p>%s</p>" % _e(P.get("pagamento") or "A combinar.")
    h.append('<div class="duas"><div class="cartao"><h4>Condições de pagamento</h4>%s</div><div class="cartao"><h4>Prazo de execução</h4>'
             '<p>%s</p></div></div>' % (pag, _e(P.get("prazo") or "A combinar.")))
    val = int(_f(P.get("validade_dias")) or 0)
    if val and d:
        h.append('<div class="validade">Proposta válida por %d dias — até %s</div>' % (val, (d + timedelta(days=val)).strftime("%d/%m/%Y")))
    pe = P.get("prazos_etapas") or {}
    passos = [("Aprovação", "contrato e sinal"), ("Projeto", _dias(pe.get("projeto"))), ("Fabricação", _dias(pe.get("fabricacao"))),
              ("Transporte", "até a obra"), ("Montagem", _dias(pe.get("montagem"))), ("Entrega", "termo de aceite")]
    h.append('<h3>Como a sua obra acontece</h3><div class="linha-tempo">%s</div>' % "".join(
        '<div><i>%d</i><b>%s</b><span>%s</span></div>' % (k + 1, _e(a), _e(b)) for k, (a, b) in enumerate(passos)))
    h.append("</section>")
    partes.append("".join(h))

    # ---- aceite
    rep = (empresa.get("representante") or {}).get("nome") or ""
    end = ", ".join(x for x in (empresa.get("endereco"), empresa.get("bairro"), " - ".join(y for y in (empresa.get("cidade"), empresa.get("uf")) if y)) if x)
    partes.append('<div class="fim"><div class="aceite"><h4>De acordo</h4><p>Declaramos estar de acordo com o escopo, as condições e o investimento '
                  'desta proposta nº %s %s, que servirá de base para o contrato.</p><div class="assin">'
                  '<div><b>%s</b>Contratante · nome, CPF e data</div><div><b>%s</b>%s</div></div></div>'
                  '<div class="empresa"><span><b>%s</b><br>%s%s</span><span style="text-align:right">%s</span></div></div>' % (
                      _e(P.get("numero") or ""), _e(P.get("revisao") or ""), _e(cli.get("nome") or "Contratante"),
                      _e(empresa.get("razao_social") or nome_emp), _e(rep or "Contratada"),
                      _e(empresa.get("razao_social") or nome_emp), ("CNPJ " + _e(empresa["cnpj"]) + "<br>") if empresa.get("cnpj") else "",
                      _e(end), "<br>".join(_e(x) for x in (empresa.get("site"), empresa.get("email"), empresa.get("telefone")) if x)))
    return "\n".join(partes), css


def _dias(v) -> str:
    n_ = int(_f(v) or 0)
    return ("%d dias" % n_) if n_ else "conforme cronograma"


def _escopo_intro() -> str:
    from saida.comercial import ESCOPO_INTRO
    return ESCOPO_INTRO


def gerar_pdf(P: dict, empresa: dict, pasta: str, nome_base: str, numeros: Optional[dict] = None, orc: Optional[dict] = None) -> dict:
    """Grava <nome_base>.html e .pdf em `pasta`. Devolve {"html", "pdf"} (e "erro_pdf" se o Chrome falhar)."""
    from saida import printpdf
    os.makedirs(pasta, exist_ok=True)
    corpo, css = html_proposta(P, empresa, numeros, orc)
    doc = printpdf.envelope(corpo, css, "Proposta %s %s" % (P.get("numero") or "", P.get("revisao") or ""))
    return imprimir_curto(doc, pasta, nome_base)


def imprimir_curto(doc: str, pasta: str, nome_base: str) -> dict:
    """Imprime o HTML a partir de uma pasta temporária de caminho curto: com o projeto numa pasta funda e o nome do
    documento longo, o caminho passava de 260 caracteres e o Chrome não abria o arquivo (o Paged.js "não terminava")."""
    import shutil
    import tempfile
    from saida import printpdf
    tmp = tempfile.mkdtemp(prefix="mtl_")
    h = os.path.join(tmp, "doc.html")
    with open(h, "w", encoding="utf-8") as f:
        f.write(doc)
    saida = {}
    pdf_tmp = os.path.join(tmp, "doc.pdf")
    try:
        printpdf.imprimir(h, pdf_tmp, verbose=False, timeout=300)
        pdf = os.path.join(pasta, nome_base + ".pdf")
        shutil.move(pdf_tmp, pdf)
        saida["pdf"] = pdf
    except Exception as exc:                            # noqa: BLE001
        saida["erro_pdf"] = str(exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return saida
