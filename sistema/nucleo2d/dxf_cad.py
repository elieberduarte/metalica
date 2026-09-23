# -*- coding: utf-8 -*-
"""DXF do CAD 2D para abrir e continuar editando no AutoCAD (DXF R2010, pela ezdxf).

O que o `Desenho.para_dxf` antigo (R12, saida/dxf.py) não fazia e a fábrica pediu:

* **Cotas funcionais**: cada `Cota` vira uma entidade DIMENSION (linear, alinhada ou
  rotacionada) com o estilo de cota METALICA — no AutoCAD ela estica, muda de texto e
  responde ao DIMSTYLE, em vez de chegar "explodida" em linhas, setas e texto soltos.
  O estilo tem a escala do desenho (DIMSCALE), texto de 2,5 mm de papel acima da
  linha, setas cheias, decimal com vírgula e zeros à direita suprimidos (125, 40,5).
* **Cores**: cada camada sai com a cor dela (cor verdadeira RGB e a ACI mais próxima);
  as quase pretas vão para a ACI 7, que o AutoCAD mostra preta no fundo branco e branca
  no fundo preto. Tipo de linha e espessura também.
* **Texto**: estilo METALICA com a fonte da tela do CAD (Segoe UI), altura = altura de
  papel × escala, alinhamento e rotação iguais.
* **Grupos**: tudo o que é de uma peça ou de um conjunto (contorno, furos, cotas, título)
  vira um GROUP com o nome de produção (S_T_2, T1…): um clique no AutoCAD pega a peça
  inteira. Os quadros (TESOURAS, TERÇAS DE COBERTURA…) já agrupam as peças do mesmo tipo.

Unidades: milímetro 1:1 (o "de papel" multiplicado pela escala), como o DXF antigo.
"""
import collections
import math
import re
from typing import Optional

from nucleo2d.desenho import (Desenho, Linha, Polilinha, Circulo, Arco, Texto, Cota, Hachura, Chamada)

FONTE = "segoeui.ttf"
ESTILO = "METALICA"
PESOS = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211]


def _rgb(hexa: str):
    h = str(hexa or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 0, 0, 0


def _aci_proxima(rgb) -> int:
    from ezdxf.colors import DXF_DEFAULT_COLORS, int2rgb
    melhor, dm = 7, float("inf")
    for i in range(1, 256):
        r, g, b = int2rgb(DXF_DEFAULT_COLORS[i])
        d = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if d < dm:
            melhor, dm = i, d
    return melhor


def _nome_grupo(texto: str, usados: set) -> str:
    base = re.sub(r"[^A-Za-z0-9_\-$]", "_", str(texto or "PECA")).strip("_")[:28] or "PECA"
    nome, n = base, 1
    while nome.upper() in usados:
        n += 1
        nome = "%s_%d" % (base[:25], n)
    usados.add(nome.upper())
    return nome


def exportar(desenho: Desenho, caminho: str, escala: Optional[float] = None) -> str:
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    k = float(escala or desenho.escala or 1.0)
    doc = ezdxf.new("R2010", setup=["linetypes"])
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = k               # tracejados com o tamanho do papel
    doc.header["$DIMSCALE"] = k
    doc.styles.add(ESTILO, font=FONTE)

    ds = doc.dimstyles.new(ESTILO)
    for chave, valor in {"dimscale": k, "dimtxt": 2.5, "dimasz": 2.5, "dimexe": 2.0, "dimexo": 1.5,
                         "dimgap": 1.0, "dimtad": 1, "dimtih": 0, "dimtoh": 0, "dimdec": 1, "dimzin": 8,
                         "dimdsep": ord(","), "dimlunit": 2, "dimclrd": 0, "dimclre": 0, "dimclrt": 0,
                         "dimtix": 0, "dimsah": 0, "dimtmove": 0}.items():
        ds.dxf.set(chave, valor)
    ds.dxf.dimtxsty = ESTILO

    # camadas com a cor, o tipo de linha e a espessura do CAD
    tipos = {lt.dxf.name.upper(): lt.dxf.name for lt in doc.linetypes}
    for nome, cam in desenho.camadas.items():
        if nome in doc.layers:
            lay = doc.layers.get(nome)
        else:
            lay = doc.layers.add(nome)
        rgb = _rgb(cam.cor)
        lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255.0
        if lum < 0.25:
            lay.color = 7                   # preto no fundo branco, branco no fundo preto
        else:
            lay.color = _aci_proxima(rgb)
            lay.rgb = rgb
        lt = tipos.get(str(cam.tipo_linha or "CONTINUOUS").upper())
        lay.dxf.linetype = lt or "Continuous"
        lay.dxf.lineweight = min(PESOS, key=lambda p: abs(p - float(cam.espessura or 0.25) * 100))
        if not cam.visivel:
            lay.off()

    msp = doc.modelspace()
    alinhar = {("esquerda", "base"): TextEntityAlignment.LEFT, ("centro", "base"): TextEntityAlignment.CENTER,
               ("direita", "base"): TextEntityAlignment.RIGHT, ("esquerda", "meio"): TextEntityAlignment.MIDDLE_LEFT,
               ("centro", "meio"): TextEntityAlignment.MIDDLE_CENTER, ("direita", "meio"): TextEntityAlignment.MIDDLE_RIGHT,
               ("esquerda", "topo"): TextEntityAlignment.TOP_LEFT, ("centro", "topo"): TextEntityAlignment.TOP_CENTER,
               ("direita", "topo"): TextEntityAlignment.TOP_RIGHT}
    grupos = collections.OrderedDict()          # chave → [entidades DXF]
    nomes = {}

    def camada_de(e):
        nome = e.camada or "0"
        if nome not in doc.layers:
            doc.layers.add(nome)
        return nome

    for e in desenho.entidades.values():
        cam = desenho.camadas.get(e.camada)
        if cam is not None and not cam.visivel:
            continue
        at = {"layer": camada_de(e)}
        feitas = []
        if isinstance(e, Linha):
            feitas.append(msp.add_line(e.a, e.b, dxfattribs=at))
        elif isinstance(e, Polilinha):
            if len(e.vertices) >= 2:
                feitas.append(msp.add_lwpolyline(e.vertices, close=bool(e.fechada), dxfattribs=at))
        elif isinstance(e, Circulo):
            feitas.append(msp.add_circle(e.centro, e.raio, dxfattribs=at))
        elif isinstance(e, Arco):
            feitas.append(msp.add_arc(e.centro, e.raio, e.inicio, e.fim, dxfattribs=at))
        elif isinstance(e, Texto):
            if str(e.texto or "").strip():
                t = msp.add_text(str(e.texto), height=float(e.altura) * k, rotation=float(e.angulo or 0.0),
                                 dxfattribs=dict(at, style=ESTILO))
                t.set_placement(e.posicao, align=alinhar.get((e.alinhamento, e.vertical), TextEntityAlignment.LEFT))
                feitas.append(t)
        elif isinstance(e, Cota):
            d = _dimensao(msp, e, k, at)
            if d is not None:
                feitas.append(d)
        elif isinstance(e, Hachura):
            if e.contornos and len(e.contornos[0]) >= 3:
                h = msp.add_hatch(dxfattribs=at)
                if e.padrao == "solido":
                    h.set_solid_fill()
                else:
                    h.set_pattern_fill("ANSI31", scale=max(float(e.espacamento) * k / 3.175, 1e-3),
                                       angle=float(e.angulo or 45.0) - 45.0)
                for contorno in e.contornos:
                    if len(contorno) >= 3:
                        h.paths.add_polyline_path(contorno, is_closed=True)
                feitas.append(h)
        elif isinstance(e, Chamada):
            ld = msp.add_leader([e.posicao, e.alvo][::-1], dimstyle=ESTILO, dxfattribs=at)
            t = msp.add_text(str(e.texto or ""), height=float(e.altura) * k, dxfattribs=dict(at, style=ESTILO))
            t.set_placement((e.posicao[0], e.posicao[1] + 0.8 * k), align=TextEntityAlignment.LEFT)
            feitas += [ld, t]
        a = e.atributos or {}
        chave = (("posicao", a["posicao"]) if a.get("posicao") and a.get("detalhe") == "posicao"
                 else ("conjunto", a["conjunto"]) if a.get("conjunto") else None)
        if chave and feitas:
            grupos.setdefault(chave, []).extend(feitas)
            if a.get("nome"):
                nomes.setdefault(chave, a["nome"])
    usados = set()
    for chave, ents in grupos.items():
        if len(ents) < 2:
            continue
        g = doc.groups.new(_nome_grupo(nomes.get(chave) or chave[1], usados),
                           description="%s %s" % (chave[0], chave[1]))
        g.extend(ents)
    import os
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    doc.saveas(caminho)
    return caminho


def _dimensao(msp, c: Cota, k: float, at: dict):
    """DIMENSION linear (h, v) ou rotacionada na direção p1→p2 (alinhada), com a linha de
    cota onde o CAD a desenha: deslocamento de papel × escala, à esquerda de p1→p2."""
    x1, y1 = c.p1
    x2, y2 = c.p2
    if c.modo == "h":
        y2p, x2p = y1, x2
    elif c.modo == "v":
        y2p, x2p = y2, x1
    else:
        x2p, y2p = x2, y2
    dx, dy = x2p - x1, y2p - y1
    comp = math.hypot(dx, dy)
    if comp < 1e-6:
        return None
    ux, uy = dx / comp, dy / comp
    nx, ny = -uy, ux
    desl = float(c.deslocamento or 0.0) * k
    base = (x1 + nx * desl, y1 + ny * desl)
    ang = 0.0 if c.modo == "h" else 90.0 if c.modo == "v" else math.degrees(math.atan2(dy, dx))
    override = {}
    if c.altura and abs(float(c.altura) - 2.5) > 1e-6:
        override["dimtxt"] = float(c.altura)
    dim = msp.add_linear_dim(base=base, p1=c.p1, p2=c.p2, angle=ang, dimstyle=ESTILO,
                             text=str(c.texto) if c.texto not in (None, "") else "<>",
                             override=override or None, dxfattribs=at)
    dim.render()
    return dim.dimension
