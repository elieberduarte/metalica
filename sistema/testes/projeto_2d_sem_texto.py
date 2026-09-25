# -*- coding: utf-8 -*-
"""Projeto recebido sem nenhum perfil escrito, como o DXF exportado de um modelo 3D:
só linhas, em centímetros e sem unidade declarada, sem título de vista nem eixos.

Galpão de 35 m × 25 m (5 tesouras a 6,25 m): planta de cobertura com terças, marcas de
seção dos pilares, contraventamento em X e correntes de meio de vão; pórtico interno
(3 pilares treliçados desenhados como retângulo fino com hachura, tesoura em treliça);
oitão (o mesmo, com montantes de fechamento, longarinas e X); o pórtico interno
repetido; fachada lateral; um pilar sozinho (detalhe); uma linha de cota em pé
desenhada como linha comum. Serve aos testes do reconhecimento pela geometria.
"""
VAO = 3500.0          # cm
MODULO = 625.0
N_EIXOS = 5
H_PILAR = 700.0
H_BANZO_INF = 700.0
H_APOIO = 800.0       # banzo superior no beiral
H_CUMEEIRA = 950.0
PAINEL = 250.0
TERCA = 350.0
COMPRIMENTO = MODULO * (N_EIXOS - 1)
Y_PORTICO = -3000.0
Y_OITAO = -6000.0
X_LATERAL = 6000.0
X_REPETIDO = 6000.0
POSTES = (583.0, 1166.0, 2334.0, 2917.0)
GIRTS = (200.0, 400.0, 600.0)


def _y_sup(x):
    meio = VAO / 2
    return H_APOIO + (H_CUMEEIRA - H_APOIO) * (1 - abs(x - meio) / meio)


def _pilar(msp, x, y0, h):
    """Retângulo fino fechado (a alma do pilar treliçado) com a hachura dentro."""
    msp.add_lwpolyline([(x - 10, y0), (x + 10, y0), (x + 10, y0 + h), (x - 10, y0 + h)], close=True)
    y = y0
    while y + 40 <= y0 + h:
        msp.add_line((x - 10, y), (x + 10, y + 40))
        y += 40


def _trelica(msp, ox, oy):
    n = int(VAO / PAINEL)
    yi = oy + H_BANZO_INF
    msp.add_line((ox, yi), (ox + VAO, yi))                                       # banzo inferior
    msp.add_line((ox, oy + H_APOIO), (ox + VAO / 2, oy + H_CUMEEIRA))             # banzo superior
    msp.add_line((ox + VAO / 2, oy + H_CUMEEIRA), (ox + VAO, oy + H_APOIO))
    for i in range(n + 1):
        x = i * PAINEL
        msp.add_line((ox + x, yi), (ox + x, oy + _y_sup(x)))                     # montantes
    for i in range(n):
        xa, xb = i * PAINEL, (i + 1) * PAINEL
        if xb <= VAO / 2:
            a, b = (ox + xa, oy + _y_sup(xa)), (ox + xb, yi)
        else:
            a, b = (ox + xa, yi), (ox + xb, oy + _y_sup(xb))
        msp.add_line(a, b)                                                       # diagonais


def _portico(msp, ox, oy, oitao=False):
    for x in (0.0, VAO):
        _pilar(msp, ox + x, oy, H_PILAR)
    _pilar(msp, ox + VAO / 2, oy, H_BANZO_INF)          # pilar do meio até o banzo inferior
    _trelica(msp, ox, oy)
    msp.add_line((ox, oy), (ox + VAO, oy))              # linha do chão
    if oitao:
        for x in POSTES:
            msp.add_line((ox + x, oy), (ox + x, oy + _y_sup(x)))                 # montantes de fechamento
        for h in GIRTS:
            msp.add_line((ox, oy + h), (ox + VAO, oy + h))                        # longarinas
        for xa, xb in ((0.0, POSTES[0]), (POSTES[-1], VAO)):
            msp.add_line((ox + xa, oy), (ox + xb, oy + GIRTS[-1]))
            msp.add_line((ox + xa, oy + GIRTS[-1]), (ox + xb, oy))
    else:
        # a cota da cumeeira desenhada como linha comum, em pé, fora de qualquer fila de pilar
        msp.add_line((ox + VAO / 2 + 200, oy), (ox + VAO / 2 + 200, oy + H_CUMEEIRA))


def _planta(msp, ox, oy):
    for x in (0.0, VAO):
        msp.add_line((ox + x, oy), (ox + x, oy + COMPRIMENTO))                  # beirais (terças)
    x = TERCA
    while x < VAO - 1:
        msp.add_line((ox + x, oy), (ox + x, oy + COMPRIMENTO))                  # terças
        x += TERCA
    for i in range(N_EIXOS):
        y = i * MODULO
        msp.add_line((ox, oy + y), (ox + VAO, oy + y))                          # tesouras
        for xm in (0.0, VAO / 2, VAO):
            msp.add_lwpolyline([(ox + xm - 30, oy + y - 10), (ox + xm + 30, oy + y - 10),
                                (ox + xm + 30, oy + y + 10), (ox + xm - 30, oy + y + 10)], close=True)
        if i < N_EIXOS - 1:
            msp.add_line((ox, oy + y + MODULO / 2), (ox + VAO, oy + y + MODULO / 2))   # correntes
    for y in (0.0, COMPRIMENTO):
        for x in POSTES:
            msp.add_lwpolyline([(ox + x - 30, oy + y - 10), (ox + x + 30, oy + y - 10),
                                (ox + x + 30, oy + y + 10), (ox + x - 30, oy + y + 10)], close=True)
    for y0 in (0.0, COMPRIMENTO - MODULO):
        y1 = y0 + MODULO
        for a, b in (((0, y0), (VAO / 2, y1)), ((0, y1), (VAO / 2, y0)),
                     ((VAO / 2, y0), (VAO, y1)), ((VAO / 2, y1), (VAO, y0))):
            msp.add_line((ox + a[0], oy + a[1]), (ox + b[0], oy + b[1]))         # contraventamento


def _lateral(msp, ox, oy):
    for i in range(N_EIXOS):
        _pilar(msp, ox + i * MODULO, oy, H_PILAR)
    for h in (200.0, 400.0):
        msp.add_line((ox, oy + h), (ox + COMPRIMENTO, oy + h))                   # longarinas
    msp.add_line((ox, oy), (ox + COMPRIMENTO, oy))                               # chão
    msp.add_line((ox, oy + H_PILAR), (ox + COMPRIMENTO, oy + H_PILAR))           # beiral
    msp.add_line((ox, oy), (ox + MODULO, oy + H_PILAR))
    msp.add_line((ox, oy + H_PILAR), (ox + MODULO, oy))


def dxf(caminho: str) -> str:
    import ezdxf
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    msp = doc.modelspace()
    _planta(msp, 0.0, 0.0)
    _portico(msp, 0.0, Y_PORTICO)
    _portico(msp, 0.0, Y_OITAO, oitao=True)
    _portico(msp, X_REPETIDO, Y_OITAO)                   # o pórtico interno de novo
    _lateral(msp, X_LATERAL, 0.0)
    _pilar(msp, -1000.0, Y_PORTICO, H_PILAR)             # um pilar sozinho
    doc.saveas(caminho)
    return caminho
