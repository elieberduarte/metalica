# -*- coding: utf-8 -*-
"""Word (.docx) sem dependências: parágrafos com trechos em negrito/sublinhado/itálico, títulos,
listas com marcador, tabelas simples, quebra de página e imagem no cabeçalho. O suficiente para o
contrato e o termo de aceite saírem editáveis (o cliente devolve o contrato reescrito no Word).

Uso::

    d = Documento(fonte="Calibri", tamanho=12)
    d.paragrafo([("CLÁUSULA PRIMEIRA: ", "b"), ("OBJETO DO CONTRATO", "b")], alinhar="both")
    d.lista(["item 1", "item 2"])
    d.gravar("contrato.docx")

Um trecho é ``texto`` ou ``(texto, estilos)`` com estilos em "b" (negrito), "i" (itálico), "u"
(sublinhado), "c" (caixa alta não muda o texto; só para clareza de quem chama).
"""
import os
import zipfile
from typing import List, Optional, Sequence, Tuple, Union
from xml.sax.saxutils import escape

Trecho = Union[str, Tuple[str, str]]

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
     'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ' \
     'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" ' \
     'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ' \
     'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'


def _run(t: Trecho, tamanho: Optional[float] = None) -> str:
    texto, estilos = (t, "") if isinstance(t, str) else (t[0], t[1] or "")
    props = ""
    if "b" in estilos:
        props += "<w:b/>"
    if "i" in estilos:
        props += "<w:i/>"
    if "u" in estilos:
        props += '<w:u w:val="single"/>'
    if tamanho:
        props += '<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (round(tamanho * 2), round(tamanho * 2))
    partes = str(texto).split("\n")
    corpo = '<w:br/>'.join('<w:t xml:space="preserve">%s</w:t>' % escape(p) for p in partes)
    return "<w:r>%s%s</w:r>" % (("<w:rPr>%s</w:rPr>" % props) if props else "", corpo)


def tamanho_imagem(caminho: str) -> Tuple[int, int]:
    """(largura, altura) de um PNG ou JPEG lendo o cabeçalho (o programa instalado não leva o Pillow)."""
    import struct
    with open(caminho, "rb") as f:
        dados = f.read(64 * 1024)
    if dados[1:4] == b"PNG":
        return struct.unpack(">II", dados[16:24])
    i = 2
    while i + 9 < len(dados):
        if dados[i] != 0xFF:
            i += 1
            continue
        marca = dados[i + 1]
        tam = struct.unpack(">H", dados[i + 2:i + 4])[0]
        if marca in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", dados[i + 5:i + 9])
            return w, h
        i += 2 + tam
    return 4, 1


class Documento:
    def __init__(self, fonte: str = "Calibri", tamanho: float = 12, margens_cm=(2.5, 3.0, 2.5, 3.0)):
        self.fonte, self.tamanho = fonte, tamanho
        self.margens = margens_cm                    # cima, direita, baixo, esquerda
        self.corpo: List[str] = []
        self.cabecalho_img: Optional[str] = None
        self.rodape_texto: str = ""

    # ------------------------------------------------------------------ blocos
    def paragrafo(self, trechos: Union[Trecho, Sequence[Trecho]], alinhar: str = "both", recuo_cm: float = 0.0,
                  primeira_cm: float = 0.0, antes: int = 0, depois: int = 120, tamanho: Optional[float] = None) -> None:
        if isinstance(trechos, (str, tuple)):
            trechos = [trechos]
        ppr = '<w:jc w:val="%s"/><w:spacing w:before="%d" w:after="%d"/>' % (alinhar, antes, depois)
        if recuo_cm or primeira_cm:
            ppr += '<w:ind w:left="%d" w:firstLine="%d"/>' % (round(recuo_cm * 567), round(primeira_cm * 567))
        self.corpo.append("<w:p><w:pPr>%s</w:pPr>%s</w:p>" % (ppr, "".join(_run(t, tamanho) for t in trechos)))

    def titulo(self, texto: str, tamanho: float = 13, alinhar: str = "center") -> None:
        self.paragrafo([(texto, "b")], alinhar=alinhar, antes=120, depois=240, tamanho=tamanho)

    def vazio(self) -> None:
        self.corpo.append("<w:p/>")

    def lista(self, itens: Sequence[Union[Trecho, Sequence[Trecho]]], marcador: str = "▪", recuo_cm: float = 1.0) -> None:
        for it in itens:
            trechos = [it] if isinstance(it, (str, tuple)) else list(it)
            ppr = ('<w:jc w:val="both"/><w:spacing w:before="0" w:after="60"/>'
                   '<w:ind w:left="%d" w:hanging="%d"/>' % (round(recuo_cm * 567), round(0.5 * 567)))
            self.corpo.append("<w:p><w:pPr>%s</w:pPr>%s%s</w:p>" % (ppr, _run(marcador + "\t"), "".join(_run(t) for t in trechos)))

    def tabela(self, linhas: Sequence[Sequence[Trecho]], larguras_cm: Sequence[float], cabecalho: bool = True,
               tamanho: Optional[float] = 10) -> None:
        grade = "".join('<w:gridCol w:w="%d"/>' % round(l * 567) for l in larguras_cm)
        borda = '<w:tblBorders>' + "".join('<w:%s w:val="single" w:sz="4" w:space="0" w:color="808080"/>' % b
                                           for b in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>'
        trs = []
        for i, lin in enumerate(linhas):
            tcs = []
            for j, cel in enumerate(lin):
                t = cel if not (cabecalho and i == 0) else ((cel, "b") if isinstance(cel, str) else (cel[0], (cel[1] or "") + "b"))
                tcs.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s</w:tcPr><w:p><w:pPr><w:spacing w:before="40" w:after="40"/></w:pPr>%s</w:p></w:tc>'
                           % (round(larguras_cm[j] * 567), '<w:shd w:val="clear" w:color="auto" w:fill="E7EBEE"/>' if cabecalho and i == 0 else "",
                              _run(t, tamanho)))
            trs.append("<w:tr>%s</w:tr>" % "".join(tcs))
        self.corpo.append('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>%s</w:tblPr><w:tblGrid>%s</w:tblGrid>%s</w:tbl>'
                          % (borda, grade, "".join(trs)))
        self.corpo.append("<w:p/>")

    def quebra_pagina(self) -> None:
        self.corpo.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    # ------------------------------------------------------------------ gravação
    def _cabecalho_xml(self, rid: str) -> str:
        w, h = tamanho_imagem(self.cabecalho_img)
        cx = int(6.0 * 360000)
        cy = int(cx * h / max(1, w))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr %s><w:p><w:pPr><w:jc w:val="left"/></w:pPr><w:r><w:drawing>'
                '<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="%d" cy="%d"/><wp:docPr id="1" name="logo"/>'
                '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
                '<pic:nvPicPr><pic:cNvPr id="0" name="logo"/><pic:cNvPicPr/></pic:nvPicPr>'
                '<pic:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
                '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p></w:hdr>' % (_W, cx, cy, rid, cx, cy))

    def gravar(self, caminho: str) -> str:
        m = self.margens
        tem_cab = bool(self.cabecalho_img and os.path.exists(self.cabecalho_img))
        sect = ('<w:sectPr>%s%s<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="%d" w:right="%d" w:bottom="%d" w:left="%d" '
                'w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>' % (
                    '<w:headerReference w:type="default" r:id="rIdCab"/>' if tem_cab else "",
                    '<w:footerReference w:type="default" r:id="rIdRod"/>' if self.rodape_texto else "",
                    round(m[0] * 567), round(m[1] * 567), round(m[2] * 567), round(m[3] * 567)))
        doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s><w:body>%s%s</w:body></w:document>'
               % (_W, "".join(self.corpo), sect))
        estilos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:cs="{f}" w:eastAsia="{f}"/>'
                   '<w:sz w:val="{s}"/><w:szCs w:val="{s}"/><w:lang w:val="pt-BR"/></w:rPr></w:rPrDefault>'
                   '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
                   '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>'
                   ).format(f=self.fonte, s=round(self.tamanho * 2))
        rels_doc = ['<Relationship Id="rIdEst" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>']
        tipos = ['<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>']
        os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
        tmp = caminho + ".parcial"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            if tem_cab:
                rels_doc.append('<Relationship Id="rIdCab" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>')
                tipos.append('<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>')
                ext = os.path.splitext(self.cabecalho_img)[1].lower().lstrip(".") or "png"
                z.write(self.cabecalho_img, "word/media/logo.%s" % ext)
                z.writestr("word/header1.xml", self._cabecalho_xml("rIdLogo"))
                z.writestr("word/_rels/header1.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                           '<Relationship Id="rIdLogo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/logo.%s"/></Relationships>' % ext)
            if self.rodape_texto:
                rels_doc.append('<Relationship Id="rIdRod" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>')
                tipos.append('<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>')
                z.writestr("word/footer1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr %s><w:p><w:pPr><w:jc w:val="center"/></w:pPr>%s</w:p></w:ftr>'
                           % (_W, _run((self.rodape_texto, ""), 8)))
            z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                       '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
                       '<Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="jpeg" ContentType="image/jpeg"/>' + "".join(tipos) + '</Types>')
            z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
            z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       + "".join(rels_doc) + '</Relationships>')
            z.writestr("word/document.xml", doc)
            z.writestr("word/styles.xml", estilos)
        os.replace(tmp, caminho)
        return caminho
