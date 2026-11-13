# -*- coding: utf-8 -*-
"""Telhas para o fornecedor: o DXF em tamanho real e a relação em Word, no padrão do Fábio (usuário, 13/11; briefing
Projeto/BRIEFINGS/Briefing-padrao-telhas-fabio-2026-11-13.md).

- O desenho vem pronto do Detalhar (nucleo2d/detalhe/telhas_fornecedor.py → desenhos-2d/telhas-fornecedor.desenho.json),
  com a relação nos metadados — os mesmos números do detalhamento das telhas.
- O DXF: R2018, tudo no Model, 1 unidade = 1 mm, e COTAS DE VERDADE (DIMENSION linear, alinhada, de raio e angular),
  que medem a geometria — "que ele consiga tirar uma cota e conferir". O estilo de cota é o do usuário ("1-125", o do
  Projeto/OBRAS/ME-Sooro/Comum/dxf_padrao_usuario.py: traço oblíquo, linha de cota na cor 1, chamada na cor 2), em
  tamanho real (fator 1) e no tamanho de texto do desenho.
- O Word: o formato do .doc do Fábio (Times New Roman 12, A4; título, lugar e tipo em negrito sublinhado; "Total" em
  negrito), com a imagem dos quadros de cada multidobra.
"""
import math
import os
import re
from typing import Dict, List, Optional

#: O estilo de cota do usuário ("1-125", lido do DXF editado por ele, 13/11) — aqui em tamanho real: DIMLFAC 1 e o
#: DIMSCALE que dá à cota o tamanho dos textos do desenho (o texto de 1,0 × DIMSCALE)
ESTILO_COTA_USUARIO = {"dimasz": 1.0, "dimexo": 1.0, "dimdli": 0.1, "dimexe": 1.0, "dimdle": 1.0, "dimfxl": 5.0,
                       "dimtih": 0, "dimtad": 1, "dimtxt": 1.0, "dimclrd": 1, "dimclre": 2, "dimclrt": 256, "dimdec": 0,
                       "dimtdec": 0, "dimtxsty": "STANDARD", "dimlfac": 1.0,
                       # o número com o fundo do desenho: a estrutura de referência não passa por cima dele
                       "dimtfill": 1}
NOME_ESTILO = "TAMANHO-REAL"


def _texto_shx(t: str) -> str:
    """o txt.shx não tem o travessão, o ponto do meio nem o "≈" (saíam como "?")"""
    return str(t).replace("≈", "~").replace("–", "-").replace("—", "-").replace("·", ".").replace("\n", " ")


def gravar_dxf(desenho, caminho: str) -> str:
    """O desenho em tamanho real num DXF R2018 com cotas de verdade. Linha, polilinha, texto, arco e círculo como estão;
    Cota → DIMENSION linear/alinhada; CotaEspecial raio → DIMENSION de raio, angular → DIMENSION angular."""
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    from nucleo2d.desenho import Linha, Polilinha, Texto, Arco, Circulo, Cota, CotaEspecial
    from saida.dxf import aci_mais_proxima
    k = float(desenho.escala or 1.0)                       # mm de papel → mm do Model (o tamanho dos textos)
    doc = ezdxf.new("R2018", setup=["linetypes", "styles"])
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = k
    msp = doc.modelspace()
    ds = doc.dimstyles.new(NOME_ESTILO, dxfattribs=dict(ESTILO_COTA_USUARIO, dimscale=2.5 * k))
    ds.set_arrows(blk=ezdxf.ARROWS.oblique)
    for nome, cam in desenho.camadas.items():
        if nome not in doc.layers:
            tl = str(cam.tipo_linha or "CONTINUOUS").upper()
            doc.layers.add(nome, color=aci_mais_proxima(cam.cor), linetype=tl if tl in doc.linetypes else "CONTINUOUS")
    alinh = {"esquerda": "LEFT", "centro": "CENTER", "direita": "RIGHT"}
    for e in desenho.entidades.values():
        a = {"layer": e.camada or "0"}
        if e.camada and e.camada not in doc.layers:
            doc.layers.add(e.camada)
        if isinstance(e, Linha):
            msp.add_line(e.a, e.b, dxfattribs=a)
        elif isinstance(e, Polilinha):
            msp.add_lwpolyline([tuple(q) for q in e.vertices], close=bool(e.fechada), dxfattribs=a)
        elif isinstance(e, Circulo):
            msp.add_circle(e.centro, e.raio, dxfattribs=a)
        elif isinstance(e, Arco):
            msp.add_arc(e.centro, e.raio, e.inicio, e.fim, dxfattribs=a)
        elif isinstance(e, Texto):
            t = _texto_shx(e.texto)
            if t.strip():
                x = msp.add_text(t, height=float(e.altura) * k, rotation=float(e.angulo or 0.0), dxfattribs=a)
                x.set_placement(tuple(e.posicao), align=TextEntityAlignment[alinh.get(e.alinhamento, "LEFT")])
        elif isinstance(e, Cota):
            _cota_linear(msp, e)
        elif isinstance(e, CotaEspecial):
            _cota_especial(msp, e)
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    doc.saveas(caminho)
    return caminho


def _cota_linear(msp, c):
    """a Cota do sistema → DIMENSION que mede a geometria (sem texto por cima)"""
    (x1, y1), (x2, y2) = c.p1, c.p2
    if c.modo == "h":
        u, medida = (1.0 if x2 >= x1 else -1.0, 0.0), abs(x2 - x1)
    elif c.modo == "v":
        u, medida = (0.0, 1.0 if y2 >= y1 else -1.0), abs(y2 - y1)
    else:
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-9:
            return
        u, medida = ((x2 - x1) / L, (y2 - y1) / L), L
    if medida < 1e-6:
        return
    a = {"layer": c.camada or "COTA"}
    k = float(getattr(msp.doc.dimstyles.get(NOME_ESTILO).dxf, "dimscale", 1.0)) / 2.5
    desl = float(c.deslocamento or 0.0) * k
    if c.modo in ("h", "v"):
        n = (-u[1], u[0])
        base = (x1 + n[0] * desl, y1 + n[1] * desl)
        dim = msp.add_linear_dim(base=base, p1=(x1, y1), p2=(x2, y2), angle=(0.0 if c.modo == "h" else 90.0),
                                 dimstyle=NOME_ESTILO, dxfattribs=a)
    else:
        dim = msp.add_aligned_dim(p1=(x1, y1), p2=(x2, y2), distance=desl if abs(desl) > 1e-6 else 1.0,
                                  dimstyle=NOME_ESTILO, dxfattribs=a)
    dim.render()


def _cota_especial(msp, c):
    a = {"layer": c.camada or "COTA"}
    if c.modo == "raio":
        dim = msp.add_radius_dim(center=tuple(c.centro), mpoint=tuple(c.p1), dimstyle=NOME_ESTILO, dxfattribs=a)
        dim.render()
    elif c.modo == "angular" and c.p2:
        from nucleo2d.cota_especial import setor_angular
        ini, varre = setor_angular(c)
        # os dois lados no sentido anti-horário do setor que a posição escolheu
        p1, p2 = (c.p1, c.p2) if abs(((math.degrees(math.atan2(c.p1[1] - c.centro[1], c.p1[0] - c.centro[0])) - ini) + 360.0)
                                     % 360.0) < 1e-3 else (c.p2, c.p1)
        dim = msp.add_angular_dim_3p(base=tuple(c.posicao), center=tuple(c.centro), p1=tuple(p1), p2=tuple(p2),
                                     dimstyle=NOME_ESTILO, override={"dimdec": 0, "dimadec": 0}, dxfattribs=a)
        dim.render()


# ============================================================ a relação em Word
def gravar_docx(linhas: List[tuple], caminho: str, imagens: Optional[Dict[str, str]] = None, largura_imagem_cm: float = 15.0) -> str:
    """As linhas de telhas_fornecedor.texto_da_relacao num .docx no formato do Fábio. `imagens`: o texto de uma linha →
    a imagem que vai logo depois dela (os quadros da multidobra)."""
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Mm, Pt, Cm
    d = docx.Document()
    s = d.sections[0]
    s.page_width, s.page_height = Mm(210), Mm(297)
    s.left_margin, s.right_margin = Mm(30), Mm(20)
    s.top_margin, s.bottom_margin = Mm(12.5), Mm(12.5)
    st = d.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(12)
    st.element.rPr.rFonts.set(docx.oxml.ns.qn("w:eastAsia"), "Times New Roman")
    pf = st.paragraph_format
    pf.space_before = pf.space_after = Pt(0)
    for texto, estilo in linhas:
        p = d.add_paragraph()
        if estilo in ("titulo", "data"):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if texto:
            r = p.add_run(texto)
            r.bold = estilo in ("titulo", "data", "lugar", "tipo", "total")
            r.underline = estilo in ("titulo", "data", "lugar", "tipo")
        img = (imagens or {}).get(texto) if estilo == "linha" else None
        if img and os.path.exists(img):
            q = d.add_paragraph()
            q.alignment = WD_ALIGN_PARAGRAPH.CENTER
            q.add_run().add_picture(img, width=Cm(largura_imagem_cm))
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    d.save(caminho)
    return caminho


def imagens_das_multidobras(desenho, pasta: str) -> Dict[str, str]:
    """a imagem (PNG) dos quadros de cada multidobra do desenho do fornecedor, para o Word: {conjunto: caminho}"""
    import pymupdf
    from nucleo2d.desenho import Desenho
    from nucleo2d.pranchas import pdf_da_area
    grupos: Dict[str, list] = {}
    for e in desenho.entidades.values():
        at = e.atributos or {}
        if at.get("detalhe") == "multidobra_fornecedor":
            grupos.setdefault(str(at.get("conjunto") or ""), []).append(e)
    out = {}
    os.makedirs(pasta, exist_ok=True)
    for conj, ents in grupos.items():
        d = Desenho(nome="md", escala=desenho.escala)
        for e in ents:
            d.add(e)
        pts = [q for e in ents for q in e.pontos()]
        x0, y0 = min(q[0] for q in pts) - 300.0, min(q[1] for q in pts) - 300.0
        x1, y1 = max(q[0] for q in pts) + 300.0, max(q[1] for q in pts) + 300.0
        nome = re.sub(r"[^\w-]+", "_", conj) or "md"
        pdf = pdf_da_area(d, os.path.join(pasta, "multidobra_%s.pdf" % nome), ((x0, y0), (x1, y1)), escala=desenho.escala)
        png = os.path.join(pasta, "multidobra_%s.png" % nome)
        pymupdf.open(pdf)[0].get_pixmap(dpi=150).save(png)
        out[conj] = png
    return out


def gerar(desenho, pasta_saida: str, base: str, obra: str = "", local: str = "", data: str = "") -> dict:
    """O DXF e o Word do fornecedor de um desenho telhas-fornecedor: <base>.dxf e <base>.docx em `pasta_saida`."""
    from nucleo2d.detalhe.telhas_fornecedor import texto_da_relacao, linha_da_relacao
    blocos = (desenho.metadados or {}).get("relacao") or []
    dxf = gravar_dxf(desenho, os.path.join(pasta_saida, base + ".dxf"))
    imgs = imagens_das_multidobras(desenho, os.path.join(pasta_saida, "_imagens"))
    por_linha = {}
    for b in blocos:
        for t in b["tipos"]:
            for l_ in t["linhas"]:
                if l_.get("multidobra") and str(l_["multidobra"]) in imgs:
                    por_linha[linha_da_relacao(l_)] = imgs[str(l_["multidobra"])]
    docx_ = gravar_docx(texto_da_relacao(blocos, obra, local, data), os.path.join(pasta_saida, base + ".docx"), por_linha)
    return {"dxf": dxf, "docx": docx_, "imagens": imgs}
