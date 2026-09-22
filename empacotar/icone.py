# -*- coding: utf-8 -*-
"""Gera `metalica.ico` a partir do ícone do editor 3D (o cubo azul da aba do navegador).

    python empacotar/icone.py

O ICO leva PNGs de 16 a 256 px (formato aceito desde o Vista), rasterizados do SVG pelo
PyMuPDF, que o sistema já usa para o memorial; sem PIL. `construir.py` passa o arquivo ao
PyInstaller (`--icon`), e o Inno Setup usa o ícone do executável nos atalhos."""
import os
import struct
import sys

try:
    import pymupdf as fitz
except ImportError:                                   # versões antigas
    import fitz

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "metalica.ico")
SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>
<rect width='32' height='32' rx='5' fill='#0b3d91'/>
<path d='M6 21V11l10-5 10 5v10l-10 5z' fill='none' stroke='#fff' stroke-width='2.2' stroke-linejoin='round'/>
<path d='M6 11l10 5 10-5M16 16v10' fill='none' stroke='#fff' stroke-width='1.2' opacity='.65'/>
</svg>"""
TAMANHOS = (16, 24, 32, 48, 64, 128, 256)


def png_do_svg(tamanho: int) -> bytes:
    doc = fitz.open(stream=SVG.encode("utf-8"), filetype="svg")
    pagina = doc[0]
    escala = tamanho / pagina.rect.width
    pix = pagina.get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=True)
    return pix.tobytes("png")


def gerar(saida: str = SAIDA) -> str:
    imagens = [(t, png_do_svg(t)) for t in TAMANHOS]
    cabecalho = struct.pack("<HHH", 0, 1, len(imagens))
    entradas, dados = b"", b""
    deslocamento = 6 + 16 * len(imagens)
    for t, png in imagens:
        entradas += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(png), deslocamento + len(dados))
        dados += png
    with open(saida, "wb") as f:
        f.write(cabecalho + entradas + dados)
    return saida


if __name__ == "__main__":
    print(gerar(sys.argv[1] if len(sys.argv) > 1 else SAIDA))
