# -*- coding: utf-8 -*-
"""Documentos do contrato: o contrato de empreitada global (Word editável e PDF), o termo de aceite da
entrega e o termo aditivo — a partir de ``saida/comercial.py`` (cláusulas e dados)."""
import html
import os
import re
from datetime import date
from typing import Dict, List

from saida import comercial as C
from saida.docx_simples import Documento


def _trechos(texto: str):
    """'**negrito** e __sublinhado__' → [(texto, estilos)] para o Word."""
    saida = []
    for parte in re.split(r"(\*\*.+?\*\*|__.+?__)", str(texto)):
        if not parte:
            continue
        if parte.startswith("**"):
            saida.append((parte[2:-2], "b"))
        elif parte.startswith("__"):
            saida.append((parte[2:-2], "u"))
        else:
            saida.append((parte, ""))
    return saida


def _html_rico(texto: str) -> str:
    s = html.escape(str(texto))
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"__(.+?)__", r"<u>\1</u>", s)


TITULO = "CONTRATO DE EMPREITADA GLOBAL PARA EXECUÇÃO DE OBRA EM ESTRUTURA METÁLICA"


def _abertura(Cn: dict, empresa: dict) -> str:
    return ("Que entre si fazem, de um lado, %s, de ora em diante denominada simplesmente **CONTRATANTE**, e, de outro lado, %s, "
            "doravante denominada **CONTRATADA**, que entre si têm justo e contratado o presente instrumento particular, cujas "
            "relações se regerão pelas cláusulas e condições seguintes:" % (C.qualificacao_contratante(Cn), C.qualificacao_contratada(empresa)))


def _assinaturas(Cn: dict, empresa: dict) -> List[tuple]:
    ct = Cn.get("contratante") or {}
    t = Cn.get("testemunhas") or [{}, {}]
    return [((empresa.get("razao_social") or "").upper(), "CONTRATADA"), ((ct.get("razao_social") or "").upper(), "CONTRATANTE"),
            ("1ª TESTEMUNHA: %s" % (t[0].get("nome") or ""), ("CPF: " + t[0]["cpf"]) if t and t[0].get("cpf") else "CPF:"),
            ("2ª TESTEMUNHA: %s" % (t[1].get("nome") if len(t) > 1 else ""), ("CPF: " + t[1]["cpf"]) if len(t) > 1 and t[1].get("cpf") else "CPF:")]


def contrato_docx(P: dict, Cn: dict, empresa: dict, caminho: str) -> str:
    d = Documento(fonte="Calibri", tamanho=12)
    if empresa.get("logo"):
        d.cabecalho_img = empresa["logo"]
    d.rodape_texto = " · ".join(x for x in (empresa.get("razao_social"), ("CNPJ " + empresa["cnpj"]) if empresa.get("cnpj") else "",
                                            empresa.get("site")) if x)
    d.titulo(TITULO, 12.5)
    d.paragrafo(_trechos(_abertura(Cn, empresa)))
    for i, cl in enumerate(C.clausulas_contrato(P, Cn, empresa), 1):
        d.paragrafo([("CLÁUSULA %s: %s" % (C._ordinal(i), cl["titulo"]), "b")], alinhar="left", antes=200, depois=100)
        for par in cl["paragrafos"]:
            if isinstance(par, dict) and "lista" in par:
                d.lista([_trechos(x) for x in par["lista"]])
            else:
                d.paragrafo(_trechos(par))
    dt = C.ler_data(Cn.get("data")) or date.today()
    d.paragrafo("%s, %s." % (Cn.get("cidade_assinatura") or empresa.get("cidade") or "", C.data_extenso(dt, maiuscula=False)), alinhar="right", antes=240)
    for nome, papel in _assinaturas(Cn, empresa):
        d.paragrafo("", depois=480)
        d.paragrafo("_______________________________________________", alinhar="left", depois=0)
        d.paragrafo([(nome, "b")], alinhar="left", depois=0)
        d.paragrafo(papel, alinhar="left")
    return d.gravar(caminho)


CSS_CONTRATO = """
@page { size: A4; margin: 25mm 28mm 22mm 28mm;
  @top-left { content: element(cab); } @bottom-center { content: element(rod); }
  @bottom-right { content: counter(page) "/" counter(pages); font: 8pt Calibri, 'Segoe UI', Arial; color: #777; } }
body { font: 11pt/1.45 Calibri, 'Segoe UI', Arial, sans-serif; color: #111; }
.cab { position: running(cab); } .cab img { height: 8mm; }
.rod { position: running(rod); font: 7.5pt Calibri, Arial; color: #777; }
h1 { font-size: 12.5pt; text-align: center; margin: 0 0 7mm; letter-spacing: .02em; }
p { text-align: justify; margin: 0 0 2.4mm; }
h2 { font-size: 11pt; margin: 6mm 0 2mm; break-after: avoid; }
ul { margin: 0 0 3mm; padding-left: 9mm; } li { text-align: justify; margin: 0 0 1.2mm; list-style: square; }
.data { text-align: right; margin-top: 8mm; }
.assin { display: grid; grid-template-columns: 1fr 1fr; gap: 16mm 14mm; margin-top: 14mm; break-inside: avoid; }
.assin div { border-top: 1px solid #111; padding-top: 1.5mm; font-size: 9.5pt; } .assin b { display: block; }
.minuta { position: fixed; top: 40%; left: 0; right: 0; text-align: center; font: 700 64pt Calibri, Arial; color: rgba(200, 40, 40, .07);
          transform: rotate(-28deg); }
"""


def contrato_html(P: dict, Cn: dict, empresa: dict) -> tuple:
    partes = []
    if empresa.get("logo"):
        partes.append('<div class="cab"><img src="file:///%s"></div>' % empresa["logo"].replace("\\", "/"))
    partes.append('<div class="rod">%s</div>' % html.escape(" · ".join(x for x in (empresa.get("razao_social"), ("CNPJ " + empresa["cnpj"]) if empresa.get("cnpj") else "") if x)))
    if Cn.get("situacao") != "assinado":
        partes.append('<div class="minuta">MINUTA %s</div>' % html.escape(Cn.get("revisao") or ""))
    partes.append("<h1>%s</h1><p>%s</p>" % (TITULO, _html_rico(_abertura(Cn, empresa))))
    for i, cl in enumerate(C.clausulas_contrato(P, Cn, empresa), 1):
        partes.append("<h2>CLÁUSULA %s: %s</h2>" % (C._ordinal(i), html.escape(cl["titulo"])))
        for par in cl["paragrafos"]:
            if isinstance(par, dict) and "lista" in par:
                partes.append("<ul>%s</ul>" % "".join("<li>%s</li>" % _html_rico(x) for x in par["lista"]))
            else:
                partes.append("<p>%s</p>" % _html_rico(par))
    dt = C.ler_data(Cn.get("data")) or date.today()
    partes.append('<p class="data">%s, %s.</p>' % (html.escape(Cn.get("cidade_assinatura") or empresa.get("cidade") or ""), C.data_extenso(dt, maiuscula=False)))
    partes.append('<div class="assin">%s</div>' % "".join("<div><b>%s</b>%s</div>" % (html.escape(a), html.escape(b)) for a, b in _assinaturas(Cn, empresa)))
    return "\n".join(partes), CSS_CONTRATO


def termo_aceite_html(P: dict, Cn: dict, empresa: dict, dados: dict) -> tuple:
    ct = Cn.get("contratante") or {}
    obra = P.get("obra") or {}
    pend = [x for x in (dados.get("pendencias") or []) if x]
    corpo = """%s<div class="rod">%s</div><h1>TERMO DE ACEITE E RECEBIMENTO DA OBRA</h1>
<p>Pelo presente termo, <b>%s</b>, inscrita no CNPJ/MF sob o nº %s, na qualidade de CONTRATANTE, declara ter recebido de
<b>%s</b>, CNPJ %s, CONTRATADA, os serviços objeto do contrato de empreitada global para execução de estrutura metálica
referente à obra <b>%s</b>, localizada em %s, conforme a proposta técnica comercial nº %s %s.</p>
<p>A entrega foi verificada em %s. %s</p>
%s
<p>A partir desta data inicia-se a contagem dos prazos de garantia previstos no contrato, e cessa a responsabilidade da
CONTRATADA pela guarda e conservação da estrutura, que passa à CONTRATANTE.</p>
<p class="data">%s, %s.</p>
<div class="assin"><div><b>%s</b>CONTRATANTE · nome, CPF e cargo</div><div><b>%s</b>CONTRATADA</div></div>""" % (
        ('<div class="cab"><img src="file:///%s"></div>' % empresa["logo"].replace("\\", "/")) if empresa.get("logo") else "",
        html.escape(empresa.get("razao_social") or ""), html.escape((ct.get("razao_social") or "").upper()), html.escape(ct.get("cnpj") or "—"),
        html.escape((empresa.get("razao_social") or "").upper()), html.escape(empresa.get("cnpj") or "—"), html.escape(obra.get("nome") or ""),
        html.escape(" - ".join(x for x in (obra.get("cidade"), obra.get("uf")) if x) or "—"), html.escape(P.get("numero") or ""),
        html.escape(P.get("revisao") or ""), html.escape(dados.get("data_vistoria") or "—"),
        "Os serviços foram executados de acordo com o contratado, sem pendências." if not pend else
        "Os serviços foram executados de acordo com o contratado, com as pendências abaixo, que a CONTRATADA se compromete a sanar no prazo indicado:",
        ("<ul>%s</ul>" % "".join("<li>%s</li>" % html.escape(x) for x in pend)) if pend else "",
        html.escape(Cn.get("cidade_assinatura") or empresa.get("cidade") or ""), C.data_extenso(C.ler_data(dados.get("data")) or date.today(), maiuscula=False),
        html.escape((ct.get("razao_social") or "").upper()), html.escape((empresa.get("razao_social") or "").upper()))
    return corpo, CSS_CONTRATO


def aditivo_html(P: dict, Cn: dict, empresa: dict, aditivo: dict, n: int) -> tuple:
    ct = Cn.get("contratante") or {}
    valor = C._f(aditivo.get("valor"))
    corpo = """%s<div class="rod">%s</div><h1>%sº TERMO ADITIVO AO CONTRATO DE EMPREITADA GLOBAL</h1>
<p>As partes, <b>%s</b> (CONTRATANTE) e <b>%s</b> (CONTRATADA), já qualificadas no contrato de empreitada global para execução
de estrutura metálica da obra <b>%s</b>, firmado em %s, resolvem aditá-lo, nos termos da cláusula de alteração de escopo, conforme segue:</p>
<h2>CLÁUSULA PRIMEIRA: DO OBJETO DO ADITIVO</h2><p>%s</p>
<h2>CLÁUSULA SEGUNDA: DO VALOR</h2><p>%s</p>
<h2>CLÁUSULA TERCEIRA: DO PRAZO</h2><p>%s</p>
<h2>CLÁUSULA QUARTA: DA RATIFICAÇÃO</h2><p>Permanecem inalteradas e em pleno vigor todas as demais cláusulas e condições do contrato
original que não conflitem com o presente termo.</p>
<p class="data">%s, %s.</p>
<div class="assin"><div><b>%s</b>CONTRATANTE</div><div><b>%s</b>CONTRATADA</div></div>""" % (
        ('<div class="cab"><img src="file:///%s"></div>' % empresa["logo"].replace("\\", "/")) if empresa.get("logo") else "",
        html.escape(empresa.get("razao_social") or ""), n, html.escape((ct.get("razao_social") or "").upper()),
        html.escape((empresa.get("razao_social") or "").upper()), html.escape((P.get("obra") or {}).get("nome") or ""),
        html.escape(Cn.get("assinado_em") or Cn.get("data") or "—"), html.escape(aditivo.get("descricao") or "—"),
        ("Pelo objeto deste aditivo, a CONTRATANTE pagará à CONTRATADA o valor de <b>%s</b> (%s)%s." % (
            C.reais(valor), C.extenso_reais(valor), (", " + html.escape(aditivo["pagamento"])) if aditivo.get("pagamento") else ""))
        if valor else "Este aditivo não altera o preço do contrato.",
        ("O prazo de execução fica acrescido de %s dias." % int(C._f(aditivo.get("prazo_dias")))) if C._f(aditivo.get("prazo_dias")) else
        "Este aditivo não altera o prazo do contrato.",
        html.escape(Cn.get("cidade_assinatura") or empresa.get("cidade") or ""), C.data_extenso(C.ler_data(aditivo.get("data")) or date.today(), maiuscula=False),
        html.escape((ct.get("razao_social") or "").upper()), html.escape((empresa.get("razao_social") or "").upper()))
    return corpo, CSS_CONTRATO


def imprimir(corpo: str, css: str, titulo: str, pasta: str, nome: str) -> Dict[str, str]:
    from saida import printpdf
    from saida.proposta_html import imprimir_curto
    os.makedirs(pasta, exist_ok=True)
    return imprimir_curto(printpdf.envelope(corpo, css, titulo), pasta, nome)
