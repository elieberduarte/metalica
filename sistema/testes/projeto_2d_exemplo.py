# -*- coding: utf-8 -*-
"""Projeto estrutural de exemplo, como o de um escritório de cálculo, em DXF e em PDF.

Galpão de 15 m × 24 m: planta de cobertura com eixos 1–5 (6 m) e A–B (15 m), terças,
contraventamento em X nos vãos das pontas, cotas; pórtico com pilares W e a tesoura
(banzos por sigla e legenda, diagonais e montantes com o perfil escrito em algumas
barras só). Serve aos testes do caminho DXF/PDF → modelo 3D → IFC.
"""
import math

VAO = 15000.0
MODULO = 6000.0
N_EIXOS = 5
PAINEL = 1500.0
H_PILAR = 6000.0
H_APOIO = 1000.0
H_CUMEEIRA = 2500.0
Y_PORTICO = -25000.0          # onde o pórtico é desenhado no DXF


def _y_banzo_sup(x: float) -> float:
    meio = VAO / 2
    return H_APOIO + (H_CUMEEIRA - H_APOIO) * (1 - abs(x - meio) / meio)


def desenhar(em, fachada=False):
    """Desenha o projeto num "pincel" com linha(a, b, camada), texto(p, s, h, ang, camada,
    centro), circulo(c, r, camada) e cota(a, b, deslocamento, valor). Coordenadas em mm do
    modelo (1:1)."""
    L = MODULO * (N_EIXOS - 1)
    # ---------------- planta de cobertura
    for i in range(N_EIXOS):
        x = i * MODULO
        em.linha((x, -1500), (x, VAO + 1500), "EIXOS")
        em.circulo((x, VAO + 2000), 500, "EIXOS")
        em.texto((x, VAO + 2000), str(i + 1), 350, 0, "EIXOS", centro=True)
        em.linha((x, 0), (x, VAO), "TESOURAS")
        em.texto((x + 150, VAO / 2 + 400), "T1", 250, 90, "TEXTOS")
    for j, rot in enumerate("AB"):
        y = j * VAO
        em.linha((-1500, y), (L + 1500, y), "EIXOS")
        em.circulo((-2000, y), 500, "EIXOS")
        em.texto((-2000, y), rot, 350, 0, "EIXOS", centro=True)
    n_tercas = int(VAO / PAINEL) + 1
    for k in range(n_tercas):
        y = k * PAINEL
        em.linha((0, y), (L, y), "TERCAS")
        if k in (2, 5, 8):
            em.texto((MODULO * 1.5, y + 120), "TERÇA Ue 150x60x20x2,00", 200, 0, "TEXTOS", centro=True)
    for x0 in (0.0, L - MODULO):
        x1 = x0 + MODULO
        for (a, b) in (((x0, 0), (x1, VAO / 2)), ((x0, VAO / 2), (x1, 0)),
                       ((x0, VAO / 2), (x1, VAO)), ((x0, VAO), (x1, VAO / 2))):
            em.linha(a, b, "CONTRAVENTAMENTO")
        ang = math.degrees(math.atan2(VAO / 2, MODULO))
        em.texto((x0 + MODULO * 0.3, VAO * 0.15 + 380), "CONTRAV. Ø12,5", 200, ang, "TEXTOS", centro=True)
        em.texto((x0 + MODULO * 0.3, VAO * 0.65 + 380), "Ø12,5", 200, ang, "TEXTOS", centro=True)
        em.texto((x0 + MODULO * 0.7, VAO * 0.85 + 380), "Ø12,5", 200, -ang, "TEXTOS", centro=True)
    for i in range(N_EIXOS - 1):
        em.cota((i * MODULO, VAO + 800), ((i + 1) * MODULO, VAO + 800), 300, "%d" % MODULO)
    em.cota((-900, 0), (-900, VAO), 0, "%d" % VAO, vertical=True)
    em.texto((L / 2, -3200), "PLANTA DE COBERTURA", 500, 0, "TEXTOS", centro=True)
    em.texto((L / 2, -3900), "ESC. 1:100", 300, 0, "TEXTOS", centro=True)

    # ---------------- pórtico com a tesoura
    y0 = Y_PORTICO
    yt = y0 + H_PILAR
    for x in (0.0, VAO):
        em.linha((x, y0), (x, yt), "PILARES")
        em.texto((x + 250 if x == 0 else x - 2900, y0 + H_PILAR / 2), "PILAR W 250x25,3", 200, 0, "TEXTOS")
    n = int(VAO / PAINEL)
    em.linha((0, yt), (VAO, yt), "BANZOS")                                  # banzo inferior
    em.linha((0, yt + H_APOIO), (VAO / 2, yt + H_CUMEEIRA), "BANZOS")        # banzo superior
    em.linha((VAO / 2, yt + H_CUMEEIRA), (VAO, yt + H_APOIO), "BANZOS")
    em.linha((0, yt), (0, yt + H_APOIO), "MONTANTES")
    em.linha((VAO, yt), (VAO, yt + H_APOIO), "MONTANTES")
    for i in range(1, n):
        x = i * PAINEL
        em.linha((x, yt), (x, yt + _y_banzo_sup(x)), "MONTANTES")
        if i in (2, 4, 7):
            em.texto((x - 80, yt + 250), "U 75x40#13", 150, 90, "TEXTOS")
    for i in range(n):
        xa, xb = i * PAINEL, (i + 1) * PAINEL
        if xb <= VAO / 2:
            a, b = (xa, yt + _y_banzo_sup(xa)), (xb, yt)
        else:
            a, b = (xa, yt), (xb, yt + _y_banzo_sup(xb))
        em.linha(a, b, "DIAGONAIS")
        if i in (1, 3, 8):
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            nx, ny = -math.sin(math.radians(ang)), math.cos(math.radians(ang))
            em.texto((mx + nx * 120, my + ny * 120), "L 50x50x3,00", 150, ang, "TEXTOS", centro=True)
    ang_bs = math.degrees(math.atan2(H_CUMEEIRA - H_APOIO, VAO / 2))
    em.texto((VAO * 0.25, yt + _y_banzo_sup(VAO * 0.25) + 200), "BS", 200, ang_bs, "TEXTOS", centro=True)
    em.texto((VAO * 0.75, yt + _y_banzo_sup(VAO * 0.75) + 200), "BS", 200, -ang_bs, "TEXTOS", centro=True)
    em.texto((VAO * 0.35, yt - 300), "BI", 200, 0, "TEXTOS", centro=True)
    # legenda
    em.texto((VAO + 2500, yt + 2200), "BS - BANZO SUPERIOR - Ue 150x60x20#13", 200, 0, "TEXTOS")
    em.texto((VAO + 2500, yt + 1800), "BI - BANZO INFERIOR - U 150x50#13", 200, 0, "TEXTOS")
    for i in range(n):
        em.cota((i * PAINEL, y0 - 600), ((i + 1) * PAINEL, y0 - 600), 0, "%d" % PAINEL)
    em.cota((-900, y0), (-900, yt), 0, "%d" % H_PILAR, vertical=True)
    em.texto((VAO / 2, y0 - 2200), "PÓRTICO - TESOURA T1", 500, 0, "TEXTOS", centro=True)
    em.texto((VAO / 2, y0 - 2900), "ESC. 1:50", 300, 0, "TEXTOS", centro=True)
    if fachada:
        _fachada(em, y0)


X_FACHADA = 32000.0
ALTURAS_LONGARINA = (2000.0, 4000.0)


def _fachada(em, y0):
    """Fachada lateral: pilares nos eixos 1–5, duas longarinas e um X de contraventamento."""
    fx = X_FACHADA
    L = MODULO * (N_EIXOS - 1)
    for i in range(N_EIXOS):
        x = fx + i * MODULO
        em.linha((x, y0 - 1500), (x, y0 + H_PILAR + 500), "EIXOS")
        em.circulo((x, y0 - 2000), 500, "EIXOS")
        em.texto((x, y0 - 2000), str(i + 1), 350, 0, "EIXOS", centro=True)
        em.linha((x, y0), (x, y0 + H_PILAR), "PILARES")
    em.texto((fx + 250, y0 + H_PILAR / 2 + 600), "PILAR W 250x25,3", 200, 0, "TEXTOS")
    for h in ALTURAS_LONGARINA:
        em.linha((fx, y0 + h), (fx + L, y0 + h), "LONGARINAS")
        em.texto((fx + MODULO * 1.5, y0 + h + 120), "LONGARINA U 100x50#12", 200, 0, "TEXTOS", centro=True)
    for a, b in (((fx, y0), (fx + MODULO, y0 + H_PILAR)), ((fx, y0 + H_PILAR), (fx + MODULO, y0))):
        em.linha(a, b, "CONTRAVENTAMENTO")
    ang = math.degrees(math.atan2(H_PILAR, MODULO))
    em.texto((fx + MODULO * 0.3, y0 + H_PILAR * 0.3 + 330), "Ø12,5", 200, ang, "TEXTOS", centro=True)
    em.texto((fx + MODULO * 0.7, y0 + H_PILAR * 0.3 + 330), "Ø12,5", 200, -ang, "TEXTOS", centro=True)
    for i in range(N_EIXOS - 1):
        em.cota((fx + i * MODULO, y0 - 800), (fx + (i + 1) * MODULO, y0 - 800), 0, "%d" % MODULO)
    em.texto((fx + L / 2, y0 - 3200), "FACHADA LATERAL", 500, 0, "TEXTOS", centro=True)


class _EmDXF:
    def __init__(self, msp, fator=1.0):
        self.msp = msp
        self.f = fator

    def _p(self, p):
        return (p[0] / self.f, p[1] / self.f)

    def linha(self, a, b, camada):
        self.msp.add_line(self._p(a), self._p(b), dxfattribs={"layer": camada})

    def circulo(self, c, r, camada):
        self.msp.add_circle(self._p(c), r / self.f, dxfattribs={"layer": camada})

    def texto(self, p, s, h, ang, camada, centro=False):
        from ezdxf.enums import TextEntityAlignment
        t = self.msp.add_text(s, dxfattribs={"layer": camada, "height": h / self.f, "rotation": ang})
        t.set_placement(self._p(p), align=TextEntityAlignment.MIDDLE_CENTER if centro else TextEntityAlignment.LEFT)

    def cota(self, a, b, desloc, valor, vertical=False):
        a2, b2 = self._p(a), self._p(b)
        if vertical:
            base = (a2[0] - desloc / self.f, a2[1])
            d = self.msp.add_linear_dim(base=base, p1=a2, p2=b2, angle=90, dxfattribs={"layer": "COTAS"},
                                        override={"dimtxt": 200 / self.f, "dimasz": 100 / self.f})
        else:
            base = (a2[0], a2[1] + desloc / self.f)
            d = self.msp.add_linear_dim(base=base, p1=a2, p2=b2, dxfattribs={"layer": "COTAS"},
                                        override={"dimtxt": 200 / self.f, "dimasz": 100 / self.f})
        if self.f != 1.0:
            d.set_text(valor)
        d.render()


def dxf(caminho: str, unidade_m: bool = False, insunits: bool = True, fachada: bool = False) -> str:
    """Grava o projeto em DXF (R2010). `unidade_m`: desenhado em metro, cotas em mm."""
    import ezdxf
    doc = ezdxf.new("R2010")
    if insunits:
        doc.header["$INSUNITS"] = 6 if unidade_m else 4
    else:
        doc.header["$INSUNITS"] = 0
    for nome in ("EIXOS", "TESOURAS", "TERCAS", "CONTRAVENTAMENTO", "PILARES", "BANZOS", "MONTANTES",
                 "DIAGONAIS", "TEXTOS", "COTAS", "LONGARINAS"):
        doc.layers.add(nome)
    desenhar(_EmDXF(doc.modelspace(), 1000.0 if unidade_m else 1.0), fachada=fachada)
    doc.saveas(caminho)
    return caminho


class _EmPDF:
    """Folha A1 (841 × 594 mm): planta em 1:100 e pórtico em 1:50, textos de verdade."""

    CORES = {"EIXOS": (0.6, 0.1, 0.1), "COTAS": (0.1, 0.5, 0.1), "TESOURAS": (0.5, 0.5, 0.5),
             "TERCAS": (0, 0, 0.6), "CONTRAVENTAMENTO": (0.8, 0.4, 0), "PILARES": (0, 0, 0),
             "BANZOS": (0, 0.4, 0.8), "MONTANTES": (0.5, 0, 0.5), "DIAGONAIS": (0, 0.6, 0.6)}

    def __init__(self, pagina):
        self.pg = pagina
        self.k = 72.0 / 25.4

    def _esc(self, p):
        # planta (y >= -5000) em 1:100 no canto de cima; pórtico em 1:50 embaixo
        if p[1] > -10000:
            x, y = 60 + p[0] / 100.0, 330 + p[1] / 100.0
        else:
            x, y = 60 + p[0] / 50.0, 70 + (p[1] - Y_PORTICO) / 50.0
        return x * self.k, (594 - y) * self.k

    def _h(self, p):
        return 100.0 if p[1] > -10000 else 50.0

    def linha(self, a, b, camada):
        import pymupdf
        # a cor da pena é a da camada, como o CAD plota
        cor = self.CORES.get(camada, (0, 0, 0.6))
        self.pg.draw_line(pymupdf.Point(*self._esc(a)), pymupdf.Point(*self._esc(b)), color=cor, width=0.5)

    def circulo(self, c, r, camada):
        import pymupdf
        self.pg.draw_circle(pymupdf.Point(*self._esc(c)), r / self._h(c) * self.k, color=(0.6, 0.1, 0.1), width=0.4)

    def texto(self, p, s, h, ang, camada, centro=False):
        import pymupdf
        esc = self._h(p)
        fs = h / esc / 0.72 * self.k / 1.0
        x, y = self._esc(p)
        comp = 0.55 * fs * len(s)
        a = math.radians(ang)
        if centro:
            x -= math.cos(a) * comp / 2 - math.sin(a) * fs * 0.35
            y += math.sin(a) * comp / 2 + math.cos(a) * fs * 0.35
        self.pg.insert_text(pymupdf.Point(x, y), s, fontsize=fs, fontname="helv",
                            morph=(pymupdf.Point(x, y), pymupdf.Matrix(ang)) if ang else None, color=(0, 0, 0))

    def cota(self, a, b, desloc, valor, vertical=False):
        import pymupdf
        if vertical:
            a2, b2 = (a[0] - desloc, a[1]), (b[0] - desloc, b[1])
        else:
            a2, b2 = (a[0], a[1] + desloc), (b[0], b[1] + desloc)
        self.pg.draw_line(pymupdf.Point(*self._esc(a2)), pymupdf.Point(*self._esc(b2)), color=(0.1, 0.5, 0.1), width=0.25)
        for p in (a2, b2):
            x, y = self._esc(p)
            self.pg.draw_line(pymupdf.Point(x - 3, y + 3), pymupdf.Point(x + 3, y - 3), color=(0.1, 0.5, 0.1), width=0.25)
        m = ((a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2)
        esc = self._h(m)
        off = 1.2 * esc
        self.texto((m[0] - (off if vertical else 0), m[1] + (0 if vertical else off)), valor, 180, 90 if vertical else 0,
                   "COTAS", centro=True)


def pdf(caminho: str) -> str:
    import pymupdf
    doc = pymupdf.open()
    pg = doc.new_page(width=841 * 72 / 25.4, height=594 * 72 / 25.4)
    desenhar(_EmPDF(pg))
    doc.save(caminho)
    return caminho
