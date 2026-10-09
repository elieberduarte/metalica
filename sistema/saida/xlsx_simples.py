# -*- coding: utf-8 -*-
"""Planilha do Excel (.xlsx) sem biblioteca de fora, como o docx_simples (09/10/2026): abas com linhas de texto e
números, o cabeçalho em negrito com fundo, congelado e com filtro, a largura das colunas e os números com casas.

    escrever(caminho, [{"nome": "Perfis", "linhas": [["Perfil", "kg"], ["TQ 50x50x3,0", 10972.6]],
                        "cabecalho": 1, "larguras": [28, 10], "total": True}])

`cabecalho`: quantas linhas de cima são título (negrito, fundo); `total`: a última linha em negrito."""
import os
import zipfile
from typing import List, Optional
from xml.sax.saxutils import escape

_TIPOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
%s
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

#: 0 texto; 1 título (negrito, fundo); 2 número com 1–2 casas; 3 inteiro; 4 total texto; 5 total número; 6 total inteiro
_ESTILOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.0#"/></numFmts>
<fonts count="2"><font><sz val="10"/><name val="Calibri"/></font><font><b/><sz val="10"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDCE6EF"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top style="thin"><color rgb="FF8A94A6"/></top><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="7">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment wrapText="1" vertical="center"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"/>
<xf numFmtId="164" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyNumberFormat="1"/>
<xf numFmtId="3" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyNumberFormat="1"/>
</cellXfs>
</styleSheet>"""


def _coluna(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _nome_aba(nome: str, usados: set) -> str:
    n = "".join(c for c in str(nome or "Aba") if c not in '[]:*?/\\')[:31] or "Aba"
    base, k = n, 2
    while n.lower() in usados:
        sufixo = " (%d)" % k
        n, k = base[:31 - len(sufixo)] + sufixo, k + 1
    usados.add(n.lower())
    return n


def _celula(ref: str, v, titulo: bool, total: bool) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        v = "sim" if v else "não"
    if isinstance(v, (int, float)) and not titulo:
        s = (6 if total else 3) if isinstance(v, int) else (5 if total else 2)
        return '<c r="%s" s="%d"><v>%r</v></c>' % (ref, s, v if isinstance(v, int) else float(v))
    s = 1 if titulo else (4 if total else 0)
    return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, s, escape(str(v)))


def _aba(a: dict) -> str:
    linhas: List[list] = a.get("linhas") or []
    cab = int(a.get("cabecalho", 1) or 0)
    total = bool(a.get("total"))
    n_col = max((len(l) for l in linhas), default=1)
    cols = ""
    if a.get("larguras"):
        cols = "<cols>%s</cols>" % "".join('<col min="%d" max="%d" width="%g" customWidth="1"/>' % (i + 1, i + 1, w)
                                            for i, w in enumerate(a["larguras"]) if w)
    corpo = []
    for r, linha in enumerate(linhas):
        tit = r < cab
        tot = total and r == len(linhas) - 1 and r >= cab
        cels = "".join(_celula("%s%d" % (_coluna(c), r + 1), v, tit, tot) for c, v in enumerate(linha))
        corpo.append('<row r="%d">%s</row>' % (r + 1, cels))
    vista = ""
    if cab:
        vista = ('<sheetViews><sheetView workbookViewId="0"><pane ySplit="%d" topLeftCell="A%d" activePane="bottomLeft" '
                 'state="frozen"/></sheetView></sheetViews>' % (cab, cab + 1))
    filtro = ""
    if cab and len(linhas) > cab:
        filtro = '<autoFilter ref="A%d:%s%d"/>' % (cab, _coluna(n_col - 1), len(linhas) - (1 if total else 0))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '%s<sheetFormatPr defaultRowHeight="14"/>%s<sheetData>%s</sheetData>%s</worksheet>' % (vista, cols, "".join(corpo), filtro))


def escrever(caminho: str, abas: List[dict], titulo: Optional[str] = None) -> str:
    """Grava a planilha (arquivo .parcial e troca, como os outros documentos) e devolve o caminho."""
    usados: set = set()
    nomes = [_nome_aba(a.get("nome"), usados) for a in abas]
    tipos = "\n".join('<Override PartName="/xl/worksheets/sheet%d.xml" '
                      'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1)
                      for i in range(len(abas)))
    livro = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
             'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>%s</sheets>%s</workbook>'
             % ("".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(n, {'"': "&quot;"}), i + 1, i + 1)
                        for i, n in enumerate(nomes)),
                "<definedNames>%s</definedNames>" % "".join(
                    '<definedName name="_xlnm._FilterDatabase" localSheetId="%d" hidden="1">\'%s\'!$A$%d:$%s$%d</definedName>'
                    % (i, escape(n).replace("'", "''"), int(a.get("cabecalho", 1) or 1),
                       _coluna(max((len(l) for l in a.get("linhas") or [[]]), default=1) - 1),
                       max(len(a.get("linhas") or []) - (1 if a.get("total") else 0), 1))
                    for i, (n, a) in enumerate(zip(nomes, abas)) if a.get("cabecalho", 1) and len(a.get("linhas") or []) > 1)))
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s'
            '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/></Relationships>'
            % ("".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                       'worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(len(abas))), len(abas) + 1))
    parcial = caminho + ".parcial"
    with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TIPOS % tipos)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("xl/workbook.xml", livro)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/styles.xml", _ESTILOS)
        for i, a in enumerate(abas):
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), _aba(a))
    os.replace(parcial, caminho)
    return caminho
