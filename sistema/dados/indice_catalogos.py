# -*- coding: utf-8 -*-
"""O índice da pasta de catálogos dos fabricantes (Normas/CATÁLOGOS, fora do git, 08/10/2026).

    python dados/indice_catalogos.py          # grava Normas/CATÁLOGOS/00-INDICE-DOS-CATALOGOS.pdf

Junta duas coisas: as fontes que os dados do sistema citam (`dados/fornecedores/*.json`, campo
`fontes`, com o `arquivo` apontando o PDF na pasta) e os PDFs que estão de fato na pasta. Sai:

* os fabricantes que o catálogo do sistema já tem, com quantos itens de cada um;
* cada PDF da pasta, por assunto: de quem é, o que traz e como o sistema usa (transcrito ou só
  consultado, e em qual arquivo de dados);
* os PDFs NOVOS — os que alguém pôs na pasta e nenhum dado do sistema cita ainda: é a fila do
  que falta ler e transcrever;
* as fontes que só existem na internet (páginas de loja, fichas atrás de cadastro);
* o que vale buscar para completar a pasta.

As pastas por assunto têm número na frente (01-PERFIS-LAMINADOS…); um PDF solto na raiz entra em
"Sem assunto" até ser movido para a pasta certa.
"""
import collections
import datetime
import glob
import html
import json
import os
import re
import sys
from typing import List

BASE = os.path.dirname(os.path.abspath(__file__))
SISTEMA = os.path.dirname(BASE)
RAIZ = os.path.dirname(SISTEMA)
PASTA = os.path.join(RAIZ, "Normas", "CATÁLOGOS")
SAIDA = "00-INDICE-DOS-CATALOGOS"
if SISTEMA not in sys.path:
    sys.path.insert(0, SISTEMA)

#: O que o sistema usa de cada arquivo de dados dos fornecedores.
USO_DO_ARQUIVO = {
    "laminados_I.json": "perfis W e HP (catálogo, troca de perfil, cálculo)",
    "laminados_U_L_barras.json": "U, I, cantoneiras em polegada e barras redondas e chatas",
    "formados_a_frio.json": "U, Ue, Z, cartola e cantoneira dobrada; tabela de bitolas (#14 = 2,00 mm…)",
    "tubos.json": "tubos redondos, quadrados e retangulares (com e sem costura)",
    "telhas.json": "telhas: largura útil, peso por m² e espessuras (resumos e orçamento)",
    "chumbadores.json": "chumbador Hardbolt: dimensões, torque, cargas permissíveis e fatores de borda e espaçamento",
}

#: O que vale buscar (curadoria de 08/10/2026): o que o sistema usa e ainda não tem fabricante por trás.
A_BUSCAR = [
    ("Parafusos estruturais", "ASTM A307 e A325 (ou ISO 8.8/10.9): dimensões, comprimento de rosca, peso por peça e porcas/arruelas — "
     "Ciser, Belenus, Metalac. Hoje os parafusos do catálogo vêm das tabelas do Anexo do manual (17.8), sem fabricante."),
    ("Chumbadores", "mecânicos de expansão (parabolt) e químicos, com as resistências de cálculo — Hilti (HST3, HIT-RE 500), Fischer, "
     "Walsywa, Âncora. A análise estrutural pede a tração e o cisalhamento por parabolt; hoje são digitados à mão."),
    ("Chumbadores de base", "barras roscadas e chumbadores em J/L para bases de pilar (aço SAE 1020/1045, ASTM F1554)."),
    ("Telhas ArcelorMittal Perfilor", "a ficha técnica da LR 17/25/33/40/100 (o site só dá as faixas de espessura; a ficha exige cadastro)."),
    ("Tubos com propriedades", "Tuper, Ipiranga e Apolo dão só faixas ou peso por barra; um catálogo com A, I e W dos tubos com costura "
     "fecharia o cálculo dos tubos que não são Vallourec."),
    ("Perfis laminados que faltam", "U 15\" e I 8\", 10\" e 12\" (não constam da tabela de bolso da Gerdau)."),
    ("Chapas grossas e piso", "Usiminas, Gerdau ou ArcelorMittal: espessuras comerciais e formatos (hoje a compra usa 1,20 x 3,00 m); "
     "chapa xadrez e chapa expandida."),
    ("Gradil e piso de grade", "grades de piso eletrofundidas (Metalgrade, Gratingbr): malha, barra portante e peso por m² — "
     "o resumo de materiais traz gradis sem o peso porque a malha do IFC não serve."),
    ("Steel deck e fechamentos", "steel deck (Metform, Perfilor Polydeck), telhas sanduíche, rufos e calhas (peso por metro)."),
    ("Tintas e galvanização", "consumo por m² e espessura de película (a área de pintura já sai no resumo)."),
]

_SO_CONSULTA = re.compile(r"(?i)não transcrit|consultad|não usad|só como referência")
_USADO_EM_PARTE = re.compile(r"(?i)usado só")           # "Usado só para a tabela de bitolas" (Sigma): entrou nos dados


def _so_consulta(x: dict) -> bool:
    o = x.get("observacao") or ""
    return bool(_SO_CONSULTA.search(o)) and not _USADO_EM_PARTE.search(o)


def _e(t) -> str:
    return html.escape(str(t if t is not None else ""))


#: Pasta do assunto → o arquivo de dados dele: telhas.json e tubos.json repetem a mesma lista de fontes.
DADOS_DO_ASSUNTO = {"01-PERFIS-LAMINADOS": ("laminados_I.json", "laminados_U_L_barras.json"), "02-PERFIS-FORMADOS-A-FRIO": ("formados_a_frio.json",),
                    "03-CHAPAS-E-BITOLAS": ("formados_a_frio.json",), "04-TUBOS": ("tubos.json",), "05-TELHAS": ("telhas.json",),
                    "06-PARAFUSOS-E-CHUMBADORES": ("chumbadores.json",)}


def ler_fontes() -> List:
    """[(arquivo de dados, fonte)] de todos os fornecedores, sem repetir a mesma fonte."""
    vistos, saida = set(), []
    for caminho in sorted(glob.glob(os.path.join(BASE, "fornecedores", "*.json"))):
        try:
            with open(caminho, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        for x in d.get("fontes") or []:
            chave = (x.get("serie"), x.get("url"), x.get("arquivo"))
            if chave in vistos:
                for i, (arqs, y) in enumerate(saida):          # a mesma fonte em outro arquivo de dados: junta os nomes
                    if (y.get("serie"), y.get("url"), y.get("arquivo")) == chave:
                        saida[i] = (arqs + (os.path.basename(caminho),), y)
                continue
            vistos.add(chave)
            saida.append(((os.path.basename(caminho),), x))
    return saida


def pdfs_da_pasta(pasta: str = PASTA) -> List[str]:
    """Os PDFs da pasta, relativos à raiz do aplicativo (como no campo `arquivo` das fontes)."""
    out = []
    for raiz, _, nomes in os.walk(pasta):
        for n in nomes:
            if n.lower().endswith(".pdf") and not n.startswith(SAIDA):
                out.append(os.path.relpath(os.path.join(raiz, n), RAIZ).replace("\\", "/"))
    return sorted(out)


def fabricantes_no_catalogo() -> List:
    """[(fabricante, itens)] do catálogo do sistema, mais os chumbadores (que não entram no catálogo de peças)."""
    try:
        with open(os.path.join(BASE, "catalogo.json"), encoding="utf-8") as f:
            itens = json.load(f).get("itens") or []
    except (OSError, ValueError):
        itens = []
    c = collections.Counter(fab for x in itens for fab in (x.get("fabricantes") or []))
    try:
        with open(os.path.join(BASE, "fornecedores", "chumbadores.json"), encoding="utf-8") as f:
            hb = json.load(f).get("hardbolt") or {}
        if hb.get("itens"):
            c["Hard (chumbador Hardbolt)"] += len(hb["itens"])
    except (OSError, ValueError):
        pass
    return c.most_common()


def montar(pasta: str = PASTA) -> dict:
    fontes = ler_fontes()
    pdfs = pdfs_da_pasta(pasta)
    por_pdf = collections.defaultdict(list)
    so_web = []
    for arq, x in fontes:
        if x.get("arquivo"):
            por_pdf[x["arquivo"]].append((arq, x))
        else:
            so_web.append((arq, x))
    grupos = collections.OrderedDict()
    for p in pdfs:
        partes = os.path.relpath(os.path.join(RAIZ, p), pasta).replace("\\", "/").split("/")
        assunto = partes[0] if len(partes) > 1 else "Sem assunto (mover para uma das pastas)"
        grupos.setdefault(assunto, []).append(p)
    faltando = sorted(a for a in por_pdf if a not in pdfs)          # citado pelos dados, mas o PDF sumiu da pasta
    novos = [p for p in pdfs if p not in por_pdf]
    return {"pdfs": pdfs, "grupos": grupos, "por_pdf": por_pdf, "so_web": so_web, "novos": novos, "faltando": faltando,
            "fabricantes": fabricantes_no_catalogo()}


def _assunto(nome: str) -> str:
    return re.sub(r"^\d+-", "", nome).replace("-", " ").capitalize()


def html_indice(I: dict) -> str:
    from saida import identidade
    css = identidade.variaveis_css({}) + """
@page { size: A4; margin: 16mm 14mm 16mm 14mm; @bottom-right { content: counter(page) " / " counter(pages); font: 600 7.5pt 'Segoe UI', Arial; color: #6b7780; } }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font: 8.8pt/1.45 'Segoe UI', Arial, sans-serif; color: var(--texto); }
.topo { background: var(--pri2); color: #fff; border-radius: 3mm; padding: 6mm 8mm 5mm; position: relative; overflow: hidden; }
.topo::after { content: ""; position: absolute; right: -10mm; top: -5mm; width: 46mm; height: 10mm; background: var(--dest); transform: skewX(-38deg); }
.topo small { font: 600 7.6pt 'Segoe UI', Arial; letter-spacing: .24em; text-transform: uppercase; color: var(--dest); }
.topo h1 { font: 300 20pt 'Segoe UI Light', 'Segoe UI', Arial; margin: 1.5mm 0 1mm; }
.topo p { margin: 0; color: rgba(255,255,255,.78); font-size: 8.6pt; }
h2 { display: flex; align-items: flex-end; gap: 3mm; font: 700 11.5pt 'Segoe UI', Arial; color: var(--pri); margin: 7mm 0 2.5mm;
     padding-bottom: 2mm; border-bottom: 1.2px solid var(--linha); break-after: avoid; }
h2 .n { font: 300 19pt/.85 'Segoe UI Light', 'Segoe UI', Arial; color: var(--dest); }
h3 { display: flex; align-items: center; gap: 2mm; font: 700 9.4pt 'Segoe UI', Arial; color: var(--pri); margin: 4.5mm 0 1mm; break-after: avoid; }
h3::before { content: ""; width: 3.6mm; height: 1.5mm; background: var(--dest); transform: skewX(-38deg); }
table { border-collapse: collapse; width: 100%; font-size: 8pt; margin: 1mm 0 2mm; }
th { text-align: left; font: 600 6.6pt 'Segoe UI', Arial; letter-spacing: .09em; text-transform: uppercase; color: var(--mudo);
     border-bottom: 1.2px solid var(--pri); padding: 1.3mm 1.5mm; }
td { padding: 1.3mm 1.5mm; border-bottom: 1px solid var(--linha); vertical-align: top; }
tr { break-inside: avoid; }
td.r { text-align: right; white-space: nowrap; }
.mudo { color: var(--mudo); font-size: 7.4pt; }
.grupo { break-inside: avoid; }
.chip { display: inline-block; padding: .3mm 2mm; border-radius: 99px; font: 600 6.8pt 'Segoe UI', Arial; white-space: nowrap; }
.chip.usado { background: #eef4d5; color: #4f5f12; } .chip.consulta { background: var(--fundo); color: var(--mudo); }
.chip.novo { background: #fff4d6; color: #7a4f00; }
.aviso { background: #fff4d6; border-left: 3px solid #d9a300; padding: 2.5mm 4mm; border-radius: 2mm; margin: 2mm 0; }
.cartoes { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2.5mm; margin-top: 4mm; }
.cartoes div { background: var(--fundo); border-radius: 2.2mm; padding: 2.6mm 3.2mm; border-top: 2.4px solid var(--dest); }
.cartoes b { display: block; font: 300 15pt 'Segoe UI Light', 'Segoe UI', Arial; color: var(--pri); }
.cartoes span { font: 600 6.6pt 'Segoe UI', Arial; letter-spacing: .12em; text-transform: uppercase; color: var(--mudo); }
"""
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    n_usados = sum(1 for p in I["pdfs"] if any(not _so_consulta(x) for _, x in I["por_pdf"].get(p, [])))
    h = ['<div class="topo"><small>Catálogos dos fabricantes</small><h1>Índice da pasta Normas/CATÁLOGOS</h1>'
         '<p>O que está na pasta, de quem é e como o sistema usa cada catálogo. Gerado em %s por sistema/dados/indice_catalogos.py.</p></div>' % hoje]
    h.append('<div class="cartoes"><div><b>%d</b><span>PDFs na pasta</span></div><div><b>%d</b><span>usados nos dados</span></div>'
             '<div><b>%d</b><span>novos a ler</span></div><div><b>%s</b><span>itens no catálogo</span></div></div>'
             % (len(I["pdfs"]), n_usados, len(I["novos"]), "{:,}".format(sum(n for _, n in I["fabricantes"])).replace(",", ".")))
    sec = 1
    if I["novos"]:
        h.append('<h2><span class="n">%02d</span>Novos na pasta — o sistema ainda não leu</h2>' % sec)
        h.append('<p>Estes PDFs estão na pasta mas nenhum dado do sistema os cita: é a fila do que falta ler e transcrever para '
                 '<span class="mudo">sistema/dados/fornecedores/</span>.</p><table><tr><th>Arquivo</th><th>Pasta</th></tr>%s</table>' % "".join(
                     '<tr><td><b>%s</b></td><td class="mudo">%s</td></tr>' % (_e(os.path.basename(p)), _e(os.path.dirname(p).split("/")[-1])) for p in I["novos"]))
        sec += 1
    if I["faltando"]:
        h.append('<div class="aviso"><b>Citados pelos dados, mas fora da pasta:</b> %s</div>' % _e("; ".join(I["faltando"])))
    h.append('<h2><span class="n">%02d</span>Fabricantes no catálogo do sistema</h2>' % sec)
    sec += 1
    h.append('<table><tr><th>Fabricante (como aparece nas peças)</th><th style="text-align:right">Itens</th></tr>%s</table>' % "".join(
        '<tr><td>%s</td><td class="r">%d</td></tr>' % (_e(f), n) for f, n in I["fabricantes"]))
    h.append('<p class="mudo">Os tubos Marcegaglia dominam a contagem porque o catálogo traz cada espessura de cada bitola. '
             '"Série NBR 6355" são os formados a frio calculados pela norma (sem fabricante).</p>')
    h.append('<h2><span class="n">%02d</span>Os catálogos da pasta, por assunto</h2>' % sec)
    sec += 1
    for assunto, pdfs in I["grupos"].items():
        h.append('<div class="grupo"><h3>%s</h3><table><colgroup><col style="width:34%%"><col style="width:12%%"><col style="width:54%%"></colgroup>'
                 '<tr><th>Arquivo</th><th>No sistema</th><th>O que traz e como é usado</th></tr>' % _e(_assunto(assunto)))
        for p in pdfs:
            refs = I["por_pdf"].get(p, [])
            if not refs:
                chip, txt = '<span class="chip novo">novo</span>', "ainda não lido"
            else:
                usado = any(not _so_consulta(x) for _, x in refs)
                chip = '<span class="chip %s">%s</span>' % (("usado", "transcrito") if usado else ("consulta", "só consulta"))
                arqs = sorted({a for ar, _ in refs for a in ar})
                proprios = [a for a in arqs if a in DADOS_DO_ASSUNTO.get(assunto, ())]
                arqs = proprios or arqs
                x = refs[0][1]
                txt = "<b>%s</b><br>%s<br><span class=\"mudo\">dados: %s%s</span>" % (
                    _e(x.get("serie")), _e(x.get("observacao") or ""), _e(", ".join(arqs)),
                    (" — " + _e("; ".join(USO_DO_ARQUIVO[a] for a in arqs if a in USO_DO_ARQUIVO))) if any(a in USO_DO_ARQUIVO for a in arqs) else "")
            h.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (_e(os.path.basename(p)), chip, txt))
        h.append("</table></div>")
    if I["so_web"]:
        h.append('<h2><span class="n">%02d</span>Fontes só na internet</h2>' % sec)
        sec += 1
        h.append('<p class="mudo">Citadas nos dados, mas sem PDF para baixar (página de loja, norma, ficha atrás de cadastro).</p>'
                 '<table><colgroup><col style="width:40%%"><col style="width:60%%"></colgroup><tr><th>Fonte</th><th>Observação</th></tr>%s</table>' % "".join(
                     '<tr><td><b>%s</b><br><span class="mudo">%s</span></td><td>%s</td></tr>' % (_e(x.get("serie")), _e(x.get("url") or "—"), _e(x.get("observacao") or ""))
                     for _, x in I["so_web"]))
    h.append('<h2><span class="n">%02d</span>O que vale buscar</h2>' % sec)
    h.append('<table><colgroup><col style="width:26%%"><col style="width:74%%"></colgroup><tr><th>Assunto</th><th>O quê, e por quê</th></tr>%s</table>' % "".join(
        '<tr><td><b>%s</b></td><td>%s</td></tr>' % (_e(a), _e(b)) for a, b in A_BUSCAR))
    h.append('<p class="mudo">Ao pôr um catálogo novo: salvar o PDF na pasta do assunto com o nome "Fabricante - assunto (ano).pdf" e pedir a '
             'transcrição; ele aparece como "novo" neste índice até os dados do sistema o citarem.</p>')
    return css, "".join(h)


def main() -> int:
    from saida import printpdf
    import shutil
    import tempfile
    I = montar()
    css, corpo = html_indice(I)
    doc = printpdf.envelope(corpo, css, "Índice dos catálogos")
    tmp = tempfile.mkdtemp(prefix="mtl_cat_")                  # caminho curto: o Chrome não abre caminho com mais de 260 caracteres
    try:
        h = os.path.join(tmp, "doc.html")
        with open(h, "w", encoding="utf-8") as f:
            f.write(doc)
        printpdf.imprimir(h, os.path.join(tmp, "doc.pdf"), verbose=False, timeout=300)
        destino = os.path.join(PASTA, SAIDA + ".pdf")
        shutil.move(os.path.join(tmp, "doc.pdf"), destino)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("%d PDFs na pasta, %d novos, %d citados fora da pasta -> %s" % (len(I["pdfs"]), len(I["novos"]), len(I["faltando"]), destino))
    return 0


if __name__ == "__main__":
    sys.exit(main())
