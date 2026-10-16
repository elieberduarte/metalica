# -*- coding: utf-8 -*-
"""Uma prancha (ou um trecho dela) do PDF em imagem legível, para um agente conferir cota por cota (16/10/2026).

    python testes/recortar_prancha.py <arquivo.pdf> info                      páginas, tamanho e o texto de cada uma
    python testes/recortar_prancha.py <arquivo.pdf> <pág> [x0 y0 x1 y1] [--zoom=3] [--saida=arq.png]

A página é numerada a partir de 1; o trecho em fração da folha (0 a 1, origem no canto de cima à esquerda): 0 0 .5 .5
é o quarto de cima à esquerda. Sem trecho, a folha inteira (zoom 1). Imprime o caminho da imagem — abra com o Read.
"""
import os
import sys
import tempfile

import pymupdf as fitz

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    pdf = fitz.open(sys.argv[1])
    opc = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[3:] if a.startswith("--")}
    pos = [a for a in sys.argv[3:] if not a.startswith("--")]
    if sys.argv[2] == "info":
        for i, pg in enumerate(pdf, 1):
            r = pg.rect
            print(f"--- página {i}: {r.width / 72 * 25.4:.0f} × {r.height / 72 * 25.4:.0f} mm")
            print(" ".join(pg.get_text().split())[:1500])
        return
    pg = pdf[int(sys.argv[2]) - 1]
    r = pg.rect
    if len(pos) >= 4:
        x0, y0, x1, y1 = map(float, pos[:4])
        clip = fitz.Rect(r.x0 + x0 * r.width, r.y0 + y0 * r.height, r.x0 + x1 * r.width, r.y0 + y1 * r.height)
        zoom = float(opc.get("--zoom", 3))
    else:
        clip, zoom = r, float(opc.get("--zoom", 1))
    # imagem até ~2400 px no lado maior: legível e leve para o Read
    lado = max(clip.width, clip.height) * zoom
    if lado > 2400:
        zoom *= 2400 / lado
    pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
    saida = opc.get("--saida") or os.path.join(tempfile.gettempdir(), "metalica_recortes",
                                                f"{os.path.splitext(os.path.basename(sys.argv[1]))[0]}_p{sys.argv[2]}_{'_'.join(pos[:4]) or 'inteira'}.png")
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    pix.save(saida)
    print(saida)


if __name__ == "__main__":
    main()
