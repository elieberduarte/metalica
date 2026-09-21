# -*- coding: utf-8 -*-
"""Verificações de consistência dos capítulos: ids duplicados, numeração de figuras/tabelas, SVG válido."""
import re, os, glob, sys
from xml.etree import ElementTree as ET

BASE = os.path.dirname(os.path.abspath(__file__))
CAPS = sorted(glob.glob(os.path.join(BASE, "capitulos", "cap*.html")))
ids = {}
problemas = 0
for cap in CAPS:
    nome = os.path.basename(cap)
    txt = open(cap, encoding="utf-8").read()
    m = re.search(r"cap(\d+)", nome); n = int(m.group(1))
    # ids
    for i in re.findall(r'\bid="([^"]+)"', txt):
        ids.setdefault(i, []).append(nome)
    # figuras
    figs = [int(x) for x in re.findall(r"<b>Figura\s+%d\.(\d+)</b>" % n, txt)]
    tabs = [int(x) for x in re.findall(r"<caption>Tabela\s+%d\.(\d+)" % n, txt)]
    def seq_ok(lst):
        return lst == list(range(1, len(lst)+1))
    nsvg = txt.count("<svg"); nimg = txt.count("<img ")
    nex = txt.count('class="box exemplo"')
    palavras = len(re.sub(r"<[^>]+>", " ", txt).split())
    print(f"{nome}: {palavras} palavras, {nsvg} svg + {nimg} img, {len(figs)} figuras, {len(tabs)} tabelas, {nex} exemplos")
    if not seq_ok(figs):
        print(f"   !! numeração de figuras fora de ordem: {figs}"); problemas += 1
    if not seq_ok(tabs):
        print(f"   !! numeração de tabelas fora de ordem: {tabs}"); problemas += 1
    # SVG válido
    for k, svg in enumerate(re.findall(r"<svg.*?</svg>", txt, flags=re.S), 1):
        try:
            ET.fromstring(svg.replace("&nbsp;", " "))
        except ET.ParseError as e:
            print(f"   !! SVG #{k} inválido: {e}"); problemas += 1
    # imagens existem
    for src in re.findall(r'<img[^>]+src="([^"]+)"', txt):
        if not os.path.exists(os.path.join(BASE, src)):
            print(f"   !! imagem não encontrada: {src}"); problemas += 1
    # tags proibidas
    for tag in ("<html", "<body", "<style", "<script", "<head"):
        if tag in txt:
            print(f"   !! contém {tag}"); problemas += 1
    # h1
    if '<h1 class="cap">' not in txt:
        print("   !! sem <h1 class=\"cap\">"); problemas += 1
    if 'class="resumo"' not in txt:
        print("   !! sem resumo"); problemas += 1
dups = {k: v for k, v in ids.items() if len(v) > 1}
if dups:
    problemas += len(dups)
    print("!! IDs duplicados:")
    for k, v in dups.items(): print(f"   {k}: {v}")
print(f"\n{len(CAPS)} capítulos; {problemas} problema(s).")
sys.exit(1 if problemas else 0)
