# -*- coding: utf-8 -*-
"""Monta o manual (HTML único) e gera o PDF via Chrome headless + Paged.js."""
import re, os, sys, glob, subprocess, shutil, time, html

BASE = os.path.dirname(os.path.abspath(__file__))
CAPS = sorted(glob.glob(os.path.join(BASE, "capitulos", "cap*.html")))
# --only cap07  -> monta só os capítulos cujo nome de arquivo contém o texto (pode repetir)
only = [sys.argv[i+1] for i,a in enumerate(sys.argv) if a=="--only" and i+1 < len(sys.argv)]
if only:
    CAPS = [c for c in CAPS if any(o in os.path.basename(c) for o in only)]
OUTDIR = os.path.join(BASE, "build")
if "--out" in sys.argv:
    OUTDIR = os.path.join(BASE, sys.argv[sys.argv.index("--out")+1])
OUT_HTML = os.path.join(OUTDIR, "manual.html")
OUT_PDF  = os.path.join(OUTDIR, "Manual_Estruturas_Metalicas.pdf")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def read(p):
    with open(p, encoding="utf-8") as f: return f.read()

def strip_tags(s):
    s = re.sub(r"<small>.*?</small>", "", s, flags=re.S)
    s = re.sub(r'<span class="nivel[^"]*">.*?</span>', "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def slug(s):
    s = strip_tags(s).lower()
    s = re.sub(r"[^a-z0-9áéíóúâêôãõçü ]", "", s)
    return re.sub(r"\s+", "-", s)[:60]

toc = []
body_parts = []
for cap in CAPS:
    mnum = re.search(r"cap(\d+)", os.path.basename(cap)); i = int(mnum.group(1)) if mnum else 0
    txt = read(cap)
    # garante id em h1.cap e h2 para o sumário
    def h1rep(m):
        attrs, inner = m.group(1), m.group(2)
        cid = f"cap{i}"
        toc.append((1, cid, f"{i}. " + strip_tags(inner)))
        # separa <small>Capítulo N</small> do título, para o cabeçalho corrido
        sm = re.search(r"<small>.*?</small>", inner, flags=re.S)
        small = sm.group(0) if sm else ""
        tit = inner.replace(small, "").strip()
        idattr = "" if 'id=' in attrs else f' id="{cid}"'
        return f'<h1 class="cap"{attrs}{idattr}>{small}<span class="tit">{tit}</span></h1>'
    txt = re.sub(r'<h1 class="cap"([^>]*)>(.*?)</h1>', h1rep, txt, count=1, flags=re.S)
    n2 = [0]
    def h2rep(m):
        attrs, inner = m.group(1), m.group(2)
        n2[0] += 1
        cid = f"cap{i}-{n2[0]}"
        toc.append((2, cid, strip_tags(inner)))
        if 'id=' in attrs: return m.group(0)
        return f'<h2{attrs} id="{cid}">{inner}</h2>'
    txt = re.sub(r'<h2([^>]*)>(.*?)</h2>', h2rep, txt, flags=re.S)
    body_parts.append(f'<section class="capitulo" data-cap="{i}">\n{txt}\n</section>')

capa = read(os.path.join(BASE, "capa.html")) if os.path.exists(os.path.join(BASE, "capa.html")) else ""
apres = read(os.path.join(BASE, "apresentacao.html")) if os.path.exists(os.path.join(BASE, "apresentacao.html")) else ""

toc_html = ['<div class="sumario"><h1>Sumário</h1><ol>']
for lvl, cid, title in toc:
    toc_html.append(f'<li class="n{lvl}"><a href="#{cid}">{html.escape(title)}</a><span class="pt"></span><a class="pg" href="#{cid}"></a></li>')
toc_html.append('</ol></div>')

css = read(os.path.join(BASE, "estilo.css"))
pagedjs = "file:///" + os.path.join(BASE, "lib", "paged.polyfill.js").replace("\\", "/")
doc = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Manual Prático de Estruturas Metálicas</title>
<style>{css}</style>
<script>window.PagedConfig={{auto:true, after:function(){{document.documentElement.setAttribute("data-paged","done");}}}};</script>
<script src="{pagedjs}"></script>
</head><body>
{capa}
{apres}
{''.join(toc_html)}
{''.join(body_parts)}
</body></html>"""
os.makedirs(OUTDIR, exist_ok=True)
# copia figuras para <out>/fig
figsrc = os.path.join(BASE, "fig")
if os.path.isdir(figsrc):
    shutil.copytree(figsrc, os.path.join(OUTDIR, "fig"), dirs_exist_ok=True)
with open(OUT_HTML, "w", encoding="utf-8") as f: f.write(doc)
print(f"HTML: {OUT_HTML}  ({len(CAPS)} capítulos, {len(toc)} entradas de sumário)")

if "--pdf" in sys.argv:
    import printpdf
    t = time.time()
    npag = printpdf.imprimir(OUT_HTML, OUT_PDF)
    print(f"PDF: {OUT_PDF}  ({npag} páginas, {os.path.getsize(OUT_PDF)/1024:.0f} kB, {time.time()-t:.0f}s)")
    # metadados e marcadores de navegação
    try:
        import pymupdf, marcadores
        doc = pymupdf.open(OUT_PDF)
        doc.set_metadata({"title": "Manual Prático de Estruturas Metálicas",
                          "subject": "Guia prático de estruturas metálicas, do básico ao avançado",
                          "keywords": "estruturas metálicas, aço, NBR 8800, ligações, soldas, galpão"})
        doc.saveIncr(); doc.close()
        marcadores.aplicar(OUT_PDF)
    except Exception as e:
        print(f"   (aviso: marcadores/metadados não aplicados: {e})")
    if "--png" in sys.argv:
        import pymupdf
        d = pymupdf.open(OUT_PDF); pdir = os.path.join(OUTDIR, "png"); os.makedirs(pdir, exist_ok=True)
        for f in glob.glob(os.path.join(pdir, "*.png")): os.remove(f)
        for k, pg in enumerate(d, 1): pg.get_pixmap(dpi=80).save(os.path.join(pdir, f"p{k:03d}.png"))
        print(f"PNG: {len(d)} páginas em {pdir}")
