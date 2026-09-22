# -*- coding: utf-8 -*-
"""Pranchas a partir dos desenhos de detalhamento do modelo do cliente; PNG da primeira."""
import json, os, sys, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE)
SCR = os.path.dirname(os.path.abspath(__file__))
from nucleo3d.modelo import Documento
from nucleo2d import detalhar, pranchas
from saida import dxf_render
doc = Documento.de_dict(json.load(open(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), encoding="utf-8")))
r = detalhar.detalhar(doc)
fontes = [{"nome": k, "desenho": d} for k, d in r["desenhos"].items()]
t = time.time()
folhas = pranchas.montar_pranchas(fontes, formato="A1", carimbo={"obra": "COMPRESSORES AR COMPRIMIDO", "cliente": "ME SOORO", "responsavel": "Elieber"}, titulo="Prancha")
print("%d pranchas em %.1f s" % (len(folhas), time.time() - t))
out = os.path.join(SCR, "det2d"); os.makedirs(out, exist_ok=True)
for f in folhas:
    m = f.metadados["prancha"]
    print("  %-12s %5d entidades  %2d células  fontes=%s" % (f.nome, f.tamanho, len(m["celulas"]), m["fontes"]))
for i in (0, 1, 2, len(folhas) - 1):
    f = folhas[i]
    dxf = f.para_dxf(1.0).gravar(os.path.join(out, "prancha_%02d.dxf" % (i + 1)))
    dxf_render.para_png(dxf, os.path.join(out, "prancha_%02d.png" % (i + 1)), dpi=100, largura=24)
    print("png", i + 1)
