# -*- coding: utf-8 -*-
"""Lê o sumário impresso no PDF e grava os marcadores (outline) de navegação."""
import re, sys, pymupdf


def aplicar(PDF="build/Manual_Estruturas_Metalicas.pdf"):
    d = pymupdf.open(PDF)

    # 1) descobre as páginas do sumário
    paginas_sumario = [i for i in range(min(12, len(d)))
                       if d[i].get_text().lstrip().startswith("Manual Prático de Estruturas Metálicas\nSumário")
                       or "\nSumário\n" in d[i].get_text()[:120]]
    if not paginas_sumario:
        paginas_sumario = [i for i in range(2, 9)]

    # 2) descobre o deslocamento entre o número impresso e o índice físico
    #    (a numeração impressa começa na capa? conferimos com uma entrada conhecida)
    desloc = None
    toc = []
    for i in paginas_sumario:
        pg = d[i]
        linhas = {}
        for x0, y0, x1, y1, txt, *_ in pg.get_text("words"):
            linhas.setdefault(round(y0), []).append((x0, txt))
        for y in sorted(linhas):
            itens = sorted(linhas[y])
            textos = [t for _, t in itens]
            if len(textos) < 2:
                continue
            if not re.fullmatch(r"\d+", textos[-1]):
                continue
            num = int(textos[-1])
            titulo = " ".join(textos[:-1]).strip()
            if not re.match(r"^\d+\.", titulo):
                continue
            if titulo.startswith("Manual Prático"):
                continue
            x_ini = itens[0][0]
            nivel = 1 if x_ini < 58 else 2
            toc.append([nivel, titulo, num])

    # 3) o deslocamento vem dos links internos já existentes (nameddest cap1)
    for i in paginas_sumario:
        for lk in d[i].get_links():
            if lk.get("nameddest") == "cap1":
                impresso = next((t[2] for t in toc if t[0] == 1), None)
                if impresso:
                    desloc = (lk["page"] + 1) - impresso
                break
        if desloc is not None:
            break
    if desloc is None:
        desloc = 0

    for t in toc:
        t[2] = max(1, min(len(d), t[2] + desloc))

    d.set_toc(toc)
    d.saveIncr()
    print(f"   {len(toc)} marcadores de navegação gravados.")
    return len(toc)


if __name__ == "__main__":
    aplicar(sys.argv[1] if len(sys.argv) > 1 else "build/Manual_Estruturas_Metalicas.pdf")
