# -*- coding: utf-8 -*-
"""A proposta em PDF no desenho compacto (27/10/2026 — o piloto C aprovado para a DEZN Construtora): sem capa,
cabeçalho na cor da marca com o logo claro, faixa de destaques terminando no valor, escopo incluso × não incluso
lado a lado, dados técnicos, responsabilidades em duas colunas, condições e o investimento com a assinatura.
Duas páginas num serviço simples.

O conteúdo é o mesmo da proposta clássica (``comercial.json``): muda só a forma. A proposta não entrega o estudo
(usuário, 27/10): o que sai aqui são os campos que o usuário revisou na tela — os avisos da proposta pegam a medida
de perfil. Impressão direta pelo Chrome (as margens de página do próprio Chrome, sem o Paged.js)."""
import html
import os
from datetime import timedelta
from typing import List, Optional
from urllib.parse import quote

from saida.comercial import _f, data_extenso, extenso_reais, ler_data, num, reais


def _e(t) -> str:
    return html.escape(str(t if t is not None else ""))


def _rico(t) -> str:
    from saida.proposta_html import _rico as r
    return r(t)


def _url(caminho: str) -> str:
    return "file:///" + quote(os.path.abspath(caminho).replace("\\", "/")) if caminho else ""


def _cores(empresa: dict) -> dict:
    c = empresa.get("cores") or {}
    return {"pri": c.get("primaria") or "#22346E", "dest": c.get("destaque") or "#800080", "apoio": c.get("apoio") or "#7F9FFF"}


CSS = """
@page { size: A4; margin: 16mm 0 18mm;
  @bottom-left { content: "%(rodape)s"; font: 600 7pt Bahnschrift, 'Segoe UI', sans-serif; letter-spacing: .2em; color: %(pri)s; padding-left: 16mm; }
  @bottom-center { content: %(logo_rodape)s; }
  @bottom-right { content: counter(page) " / " counter(pages); font: 7pt 'Segoe UI', sans-serif; color: #5A6182; padding-right: 16mm; } }
@page :first { margin-top: 0; }
:root { --pri: %(pri)s; --dest: %(dest)s; --apoio: %(apoio)s; --ink: #1A2040; --mut: #5A6182; --linha: #DCE1F2;
        --fpri: color-mix(in srgb, var(--apoio) 14%%, white); --fdest: color-mix(in srgb, var(--dest) 7%%, white); }
* { box-sizing: border-box; margin: 0; padding: 0; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font: 9.5pt/1.42 'Segoe UI', Arial, sans-serif; color: var(--ink); padding: 0 16mm; }
h1, h2, h3, .num, .eyebrow, .valor { font-family: Bahnschrift, 'Segoe UI', sans-serif; }
.eyebrow { font-size: 8pt; letter-spacing: .22em; text-transform: uppercase; color: var(--dest); font-weight: 600; }
h1 { font-size: 21pt; color: var(--pri); font-weight: 700; line-height: 1.1; margin-bottom: 1mm; }
h2 { font-size: 13pt; color: var(--pri); font-weight: 600; margin: 0 0 3mm; break-after: avoid; }
h2 .n { display: inline-block; background: var(--pri); color: #fff; font-size: 9pt; border-radius: 1mm; padding: .4mm 1.6mm;
        margin-right: 2.5mm; vertical-align: middle; }
h3 { font-size: 10.5pt; color: var(--pri); font-weight: 600; margin: 0 0 2mm; break-after: avoid; }
p { margin: 0 0 2.5mm; }
ul { list-style: none; }
ul li { position: relative; padding-left: 5mm; margin-bottom: 1.1mm; break-inside: avoid; }
ul li:before { content: ""; position: absolute; left: 0; top: .55em; width: 2.2mm; height: 2.2mm; border-radius: 50%%; background: var(--apoio); }
ul.sim li:before { background: var(--pri); }
ul.nao li:before { background: none; border: .35mm solid var(--dest); width: 1.6mm; height: 1.6mm; }
ul li.dest { font-weight: 600; color: var(--pri); }
.tab { width: 100%%; border-collapse: collapse; font-size: 9pt; }
.tab th { text-align: left; font-weight: 600; color: var(--mut); font-size: 7.5pt; letter-spacing: .08em; text-transform: uppercase;
          border-bottom: .4mm solid var(--pri); padding: 1.5mm 2mm; }
.tab td { padding: 1.8mm 2mm; border-bottom: .2mm solid var(--linha); vertical-align: top; }
.tab td.r, .tab th.r { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.tab tr { break-inside: avoid; }
section.sec { margin-bottom: 5mm; }
.duas { display: grid; grid-template-columns: 1fr 1fr; gap: 7mm; break-inside: avoid; }
.col { padding: 3.5mm 4mm; border-radius: 2.5mm; }
.col.sim { background: var(--fpri); }
.col.nao { background: var(--fdest); }
.col.nao h3 { color: var(--dest); }
.col h4 { font: 600 8pt 'Segoe UI', sans-serif; color: var(--mut); letter-spacing: .08em; text-transform: uppercase; margin: 2mm 0 1mm; }
.quadro { columns: 2; column-gap: 8mm; font-size: 9pt; border-left: 1mm solid var(--apoio); padding-left: 5mm; }
.cab { margin: 0 -16mm 5mm; height: 44mm; background: var(--pri); position: relative; overflow: hidden; color: #fff;
       clip-path: polygon(0 0, 100%% 0, 100%% 78%%, 50%% 100%%, 0 78%%); }
.cab .lg { position: absolute; left: 16mm; top: 7mm; width: 29mm; }
.cab .lg img { width: 100%%; display: block; }
.cab .lg b { font: 700 16pt Bahnschrift, 'Segoe UI', sans-serif; }
.cab .dir { position: absolute; right: 16mm; top: 12mm; text-align: right; font-size: 9.5pt; color: rgba(255,255,255,.88); }
.cab .ch { position: absolute; left: 30%%; right: -10%%; top: -6mm; height: 60mm; }
.ficha { display: grid; grid-template-columns: 1fr 1fr; margin: 3mm 0 4mm; border-top: .4mm solid var(--pri);
         border-bottom: .2mm solid var(--linha); break-inside: avoid; }
.ficha > div { padding: 2.5mm 0 2.5mm 4mm; }
.ficha > div:first-child { padding-left: 0; }
.ficha > div + div { border-left: .2mm solid var(--linha); }
.ficha .eyebrow { display: block; margin-bottom: .8mm; }
.ficha b { display: block; color: var(--pri); font-size: 10pt; }
.ficha small { color: var(--mut); font-size: 8.5pt; }
.faixa { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; margin: 3mm 0 5mm; background: var(--fpri);
         border-radius: 2.5mm; break-inside: avoid; text-align: center; }
.faixa div { padding: 3.5mm 3mm; }
.faixa div + div { border-left: .3mm solid color-mix(in srgb, var(--apoio) 35%%, white); }
.faixa .num { font-size: 15pt; font-weight: 600; color: var(--dest); display: block; line-height: 1.1; margin-bottom: .6mm; }
.faixa small { color: var(--mut); font-size: 8pt; }
.foto { width: 100%%; height: 62mm; border-radius: 2.5mm; background: #eef2f6 center / cover no-repeat; margin: 0 0 5mm; }
.caixa { display: flex; justify-content: space-between; align-items: center; gap: 8mm; background: var(--pri); color: #fff;
         border-radius: 3mm; padding: 5mm 6mm; break-inside: avoid; }
.caixa .eyebrow { color: var(--apoio); }
.caixa .valor { font-size: 26pt; font-weight: 600; line-height: 1.1; margin-top: 1mm; }
.caixa .ext { font-size: 8.5pt; opacity: .8; }
.caixa dl { display: grid; grid-template-columns: auto auto; gap: 1.5mm 5mm; font-size: 9pt; max-width: 80mm; }
.caixa dt { color: var(--apoio); }
.caixa dd { font-weight: 600; }
.notas { font-size: 7.8pt; color: var(--mut); font-style: italic; margin-top: 2.5mm; }
.notas p { margin: 0 0 1mm; }
.fim { break-inside: avoid; }
.assin { margin-top: 8mm; text-align: center; break-inside: avoid; }
.assin .linha { width: 75mm; border-top: .3mm solid var(--ink); margin: 14mm auto 0; padding-top: 1.5mm; font-size: 8.5pt; color: var(--mut); }
.assin .linha b { color: var(--ink); display: block; font-size: 9.5pt; }
.contato { margin-top: 5mm; border-top: .2mm solid var(--linha); padding-top: 3mm; font-size: 7.8pt; color: var(--mut); text-align: center; }
"""


def _chevron(cor: str, opac: float = .3, largura: int = 5) -> str:
    """o motivo da marca: um telhado em traço"""
    return ('<svg viewBox="0 0 642 200" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" style="width:100%%;height:100%%">'
            '<path d="M0 197 L321 2 L642 197" fill="none" stroke="%s" stroke-width="%d" opacity="%s"/></svg>' % (_e(cor), largura, opac))


def _logo_rodape(logo: str, altura_mm: float = 9) -> str:
    """o logo no rodapé de cada página (usuário, 30/10): só SVG, com o tamanho gravado no próprio SVG — a caixa de
    margem da página não aceita largura. Sem SVG: "none" (o rodapé fica com o nome)."""
    import base64
    import re
    if not logo.lower().endswith(".svg") or not os.path.exists(logo):
        return "none"
    with open(logo, encoding="utf-8") as f:
        svg = f.read()
    vb = re.search(r'viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', svg)
    if not vb:
        return "none"
    largura = altura_mm * float(vb.group(1)) / float(vb.group(2))
    svg = re.sub(r"<svg\b", '<svg width="%.1fmm" height="%.1fmm"' % (largura, altura_mm), svg, count=1)
    return 'url("data:image/svg+xml;base64,%s")' % base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _objeto(P: dict) -> str:
    """o que a proposta oferece, em minúscula para a frase da carta ("para a fabricação e instalação de…")"""
    t = str(P.get("ref") or "").strip().rstrip(".")
    for prefixo in ("Proposta para ", "Proposta de ", "Ref.: ", "Ref: "):
        if t.lower().startswith(prefixo.lower()):
            t = t[len(prefixo):]
    return (t[:1].lower() + t[1:]) if t else ""


def destaques(P: dict) -> List[tuple]:
    """os números da faixa: os digitados (proposta.destaques: [{valor, texto}]) ou, sem eles, área, peso e prazo."""
    d = [(str(x.get("valor") or ""), str(x.get("texto") or "")) for x in P.get("destaques") or [] if x.get("valor")]
    if d:
        return d[:4]
    area = sum(_f(g.get("area")) or 0 for g in P.get("geometria") or [])
    if area:
        d.append(("%s m²" % num(area, 0 if area >= 100 else 2), "de área"))
    if _f(P.get("peso_kg")):
        d.append(("%s kg" % num(P["peso_kg"], 0), "de estrutura (estimado)"))
    pe = P.get("prazos_etapas") or {}
    dias = sum(int(_f(v) or 0) for v in pe.values())
    if dias:
        d.append(("%d dias" % dias, "de prazo estimado"))
    return d[:4]


def _escopo(P: dict) -> str:
    blocos = [b for b in P.get("escopo") or [] if any(i.get("texto") for i in b.get("itens") or [])]
    h = []
    for b in blocos:
        if len(blocos) > 1:
            h.append("<h4>%s</h4>" % _e(b.get("titulo") or ""))
        h.append('<ul class="sim">%s</ul>' % "".join('<li class="%s">%s</li>' % ("dest" if i.get("destaque") else "", _rico(i["texto"]))
                                                  for i in b.get("itens") or [] if i.get("texto")))
    return "".join(h)


def _lista(itens, cls="") -> str:
    return '<ul class="%s">%s</ul>' % (cls, "".join("<li>%s</li>" % _rico(x) for x in itens or [] if str(x).strip()))


def _tecnicos(P: dict) -> str:
    car = [c for c in P.get("carregamentos") or [] if c.get("descricao") and str(c.get("carga") or "").strip() not in ("", "-")]
    geo = [g for g in P.get("geometria") or [] if g.get("nome")]
    peso = _f(P.get("peso_kg"))
    if not (car or geo or peso):
        return ""
    lados = []
    if car:
        lados.append('<div><h3>Carregamentos</h3><table class="tab"><tr><th>Carga</th><th>Descrição</th></tr>%s</table></div>'
                     % "".join("<tr><td>%s</td><td>%s</td></tr>" % (_e(c.get("carga")), _e(c.get("descricao"))) for c in car))
    linhas = []
    for g in geo:
        med = " × ".join("%s m" % num(g[k]) for k in ("largura", "comprimento") if _f(g.get(k)))
        linhas.append('<tr><td>%s</td><td class="r">%s</td><td class="r">%s</td></tr>'
                      % (_e(g.get("nome")), med or "—", ("%s m²" % num(g["area"])) if _f(g.get("area")) else "—"))
    if peso:
        linhas.append('<tr><td>Peso estimado da estrutura</td><td></td><td class="r">%s kg</td></tr>' % num(peso, 0))
    if linhas:
        lados.append('<div><h3>Geometria</h3><table class="tab"><tr><th>Item</th><th class="r">Medidas</th><th class="r">Total</th></tr>%s'
                     '</table></div>' % "".join(linhas))
    return '<div class="duas">%s</div>' % "".join(lados) if len(lados) > 1 else lados[0]


def html_proposta(P: dict, empresa: dict, numeros: Optional[dict] = None, orc: Optional[dict] = None):
    from saida.comercial import empresa_da_linha
    empresa = empresa_da_linha(empresa, P.get("linha"))
    cor = _cores(empresa)
    cli, obra, inv = P.get("cliente") or {}, P.get("obra") or {}, P.get("investimento") or {}
    nome_emp = empresa.get("nome_comercial") or empresa.get("razao_social") or ""
    d = ler_data(P.get("data"))
    data_txt = data_extenso(d, maiuscula=False) if d else str(P.get("data") or "")
    local_obra = " – ".join(x for x in (obra.get("cidade"), obra.get("uf")) if x)
    logo = empresa.get("logo") or ""
    logo_rodape = _logo_rodape(logo)
    # número e revisão não aparecem no papel (usuário, 30/10): ficam no nome do arquivo e no comercial.json
    css = CSS % dict(cor, rodape="" if logo_rodape != "none" else _e(nome_emp.upper()).replace('"', ""), logo_rodape=logo_rodape)
    valor = _f(inv.get("valor"))
    titulo = str(P.get("titulo") or "").strip() or _objeto(P).capitalize() or obra.get("nome") or "Proposta comercial"
    objeto = _objeto(P)
    h = []

    logo_claro = empresa.get("logo_claro") or ""
    h.append('<div class="cab"><div class="ch">%s</div><div class="lg">%s</div><div class="dir">%s%s</div></div>' % (
        _chevron(cor["apoio"]), ('<img src="%s" alt="">' % _url(logo_claro)) if logo_claro else "<b>%s</b>" % _e(nome_emp),
        _e(data_txt), (" · " + _e(P["cidade_emissao"])) if P.get("cidade_emissao") else ""))
    h.append("<h1>%s</h1>" % _e(titulo))
    ficha = []
    if cli.get("nome"):
        ficha.append('<div><span class="eyebrow">Cliente</span><b>%s</b>%s</div>' % (
            _e(cli["nome"]), ("<small>A/C %s</small>" % _e(cli["contato"])) if cli.get("contato") else ""))
    if obra.get("nome") or local_obra:
        ficha.append('<div><span class="eyebrow">Obra</span><b>%s</b>%s</div>' % (
            _e(obra.get("nome") or local_obra), ("<small>%s</small>" % _e(local_obra)) if obra.get("nome") and local_obra else ""))
    if ficha:
        h.append('<div class="ficha">%s</div>' % "".join(ficha))
    h.append("<p>Conforme a vossa solicitação, apresentamos a nossa proposta comercial%s%s%s. Abaixo estão o escopo, o que fica "
             "por conta de cada parte e o investimento.</p>" % (
                 (" para a " + _e(objeto)) if objeto else "", (", na obra " + _e(obra["nome"])) if obra.get("nome") else "",
                 (", em " + _e(local_obra)) if local_obra else ""))
    # o valor aparece uma vez só, no Investimento, junto do pagamento e do prazo (usuário, 30/10: "se repetem?")
    ds = destaques(P)
    if ds:
        h.append('<div class="faixa">%s</div>' % "".join('<div><span class="num">%s</span><small>%s</small></div>' % (_e(v), _e(t))
                                                        for v, t in ds))
    fotos = [i for i in P.get("imagens") or [] if i.get("arquivo") and os.path.exists(i["arquivo"])]
    if fotos:
        h.append('<div class="foto" style="background-image:url(\'%s\')"></div>' % _url(fotos[0]["arquivo"]))

    n = [0]

    def secao(titulo_, corpo_):
        n[0] += 1
        return '<section class="sec"><h2><span class="n">%02d</span>%s</h2>%s</section>' % (n[0], _e(titulo_), corpo_)

    intro = ("Conforme o projeto do cliente." if P.get("projeto_por") == "cliente" else "")
    h.append(secao("Escopo", ('<p>%s</p>' % _e(intro) if intro else "") +
                   '<div class="duas"><div class="col sim"><h3>Está incluso</h3>%s</div><div class="col nao"><h3>Não está incluso</h3>%s</div></div>'
                   % (_escopo(P), _lista(P.get("exclusoes"), "nao"))))
    if P.get("responsabilidades"):
        h.append(secao("Responsabilidades do contratante", '<div class="quadro">%s</div>' % _lista(P["responsabilidades"])))
    if P.get("condicoes") or P.get("seguranca"):
        h.append(secao("Condições gerais", _lista(P.get("condicoes")) +
                       (('<h3 style="margin-top:3mm">Segurança do trabalho</h3>' + _lista(P["seguranca"])) if P.get("seguranca") else "")))
    tec = _tecnicos(P) if P.get("mostrar_ficha", True) else ""
    if tec:
        h.append(secao("Dados técnicos", tec))

    # ---- investimento + assinatura (um bloco só: a assinatura não fica sozinha numa página)
    parcelas = [p for p in P.get("parcelas") or [] if _f(p.get("valor"))]
    pag = "; ".join("%s %s%s" % (p.get("descricao") or "", reais(p.get("valor")), (" em " + str(p["vencimento"])) if p.get("vencimento") else "")
                    for p in parcelas) if parcelas else str(P.get("pagamento") or "A combinar").rstrip(".")
    dl = [("Pagamento", pag), ("Prazo de execução", str(P.get("prazo") or "A combinar").rstrip("."))]
    val = int(_f(P.get("validade_dias")) or 0)
    if val and d:
        dl.append(("Validade", "%d dias — até %s" % (val, (d + timedelta(days=val)).strftime("%d/%m/%Y"))))
    corpo = ['<div class="caixa"><div><div class="eyebrow">Valor global</div><div class="valor">%s</div><div class="ext">%s</div></div>'
             '<dl>%s</dl></div>' % (reais(valor) if valor else "A definir",
                                    _e("(" + extenso_reais(valor) + ")") if valor else "",
                                    "".join("<dt>%s</dt><dd>%s</dd>" % (_e(a), _e(b)) for a, b in dl))]
    if inv.get("partes"):
        corpo.append('<table class="tab" style="margin-top:3mm"><tr><th>Composição</th><th class="r">Valor</th></tr>%s</table>' % "".join(
            '<tr><td>%s</td><td class="r">%s</td></tr>' % (_e(p.get("descricao")), reais(p.get("valor"))) for p in inv["partes"] if p.get("descricao")))
    if inv.get("opcionais"):
        corpo.append('<table class="tab" style="margin-top:3mm"><tr><th>Opcional</th><th class="r">Investimento total com o item</th></tr>%s</table>'
                     % "".join('<tr><td>%s</td><td class="r">%s</td></tr>' % (_e(o.get("descricao")), reais(o.get("valor")))
                               for o in inv["opcionais"] if o.get("descricao")))
    if inv.get("notas"):
        corpo.append('<div class="notas">%s</div>' % "".join("<p>%s</p>" % _e(x) for x in inv["notas"]))
    rt = empresa.get("responsavel_tecnico") or {}
    quem = "<b>%s</b>" % _e(empresa.get("razao_social") or nome_emp)
    if rt.get("nome"):
        quem += "%s%s" % (_e(rt["nome"]), (" · " + _e(rt["registro"])) if rt.get("registro") else "")
    corpo.append('<div class="assin"><p>Atenciosamente,</p><div class="linha">%s</div></div>' % quem)
    contato = " · ".join(_e(x) for x in (empresa.get("cnpj") and "CNPJ " + empresa["cnpj"], empresa.get("endereco"),
                                          " – ".join(y for y in (empresa.get("cidade"), empresa.get("uf")) if y),
                                          empresa.get("telefone"), empresa.get("email"), empresa.get("site")) if x)
    if contato:
        corpo.append('<div class="contato">%s</div>' % contato)
    n[0] += 1
    h.append('<section class="sec fim"><h2><span class="n">%02d</span>Investimento</h2>%s</section>' % (n[0], "".join(corpo)))
    return "\n".join(h), css


def gerar_pdf(P: dict, empresa: dict, pasta: str, nome_base: str, numeros: Optional[dict] = None, orc: Optional[dict] = None) -> dict:
    """Grava <nome_base>.pdf em `pasta`. Devolve {"pdf"} (ou {"erro_pdf"}). Imprime de uma pasta de caminho curto
    (o Chrome não abre caminho com mais de 260 caracteres — proposta_html.imprimir_curto)."""
    import shutil
    import subprocess
    import tempfile
    from saida.printpdf import navegador
    os.makedirs(pasta, exist_ok=True)
    corpo, css = html_proposta(P, empresa, numeros, orc)
    doc = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>%s</title><style>%s</style></head><body>%s</body></html>'
           % (_e("Proposta %s %s" % (P.get("numero") or "", P.get("revisao") or "")), css, corpo))
    tmp = tempfile.mkdtemp(prefix="mtl_")
    saida = {}
    try:
        h = os.path.join(tmp, "doc.html")
        with open(h, "w", encoding="utf-8") as f:
            f.write(doc)
        pdf_tmp = os.path.join(tmp, "doc.pdf")
        subprocess.run([navegador(), "--headless=new", "--no-pdf-header-footer", "--print-to-pdf=" + pdf_tmp,
                        "file:///" + h.replace("\\", "/")], capture_output=True, timeout=180)
        if not os.path.exists(pdf_tmp):
            raise RuntimeError("o Chrome não gerou o PDF")
        pdf = os.path.join(pasta, nome_base + ".pdf")
        shutil.move(pdf_tmp, pdf)
        saida["pdf"] = pdf
    except Exception as exc:                            # noqa: BLE001
        saida["erro_pdf"] = str(exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return saida
