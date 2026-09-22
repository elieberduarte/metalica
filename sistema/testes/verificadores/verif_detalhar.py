# -*- coding: utf-8 -*-
"""Detalhamento do modelo do cliente: roda nucleo2d.detalhar, grava DXF e PNG de cada desenho."""
import json, os, sys, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE)
SCR = os.path.dirname(os.path.abspath(__file__))
from nucleo3d.modelo import Documento
from nucleo2d import detalhar
from saida import dxf_render

t = time.time()
doc = Documento.de_dict(json.load(open(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), encoding="utf-8")))
print("modelo: %d entidades em %.1f s" % (len(doc.entidades), time.time() - t))
t = time.time()
r = detalhar.detalhar(doc, avisar=print)
print("detalhado em %.1f s" % (time.time() - t))
print("posições:", len(r["posicoes"]), " conjuntos:", len(r["conjuntos"]), " peso:", r["peso_total"], "kg")
print("regra das terças aplicada em %d posições:" % len(r["regra_tercas"]))
for k, v in list(r["regra_tercas"].items())[:12]:
    print("   ", k, "->", v)
print("avisos:", r["avisos"][:10])
for c in r["conjuntos"][:12]:
    print("   conj %-5s %3d peças %2d inst iguais=%s %s" % (c["marca"], c["pecas"], c["instancias"], c["iguais"], c["composicao"]))
out = os.path.join(SCR, "det2d"); os.makedirs(out, exist_ok=True)
for chave, d in r["desenhos"].items():
    dxf = d.para_dxf().gravar(os.path.join(out, chave + ".dxf"))
    print("  %-10s %6d entidades  escala 1:%g  -> %s" % (chave, d.tamanho, d.escala, os.path.basename(dxf)))
    json.dump(d.dict(), open(os.path.join(out, chave + ".desenho.json"), "w", encoding="utf-8"))
    try:
        dxf_render.para_png(dxf, os.path.join(out, chave + ".png"), dpi=70, largura=30)
    except Exception as e:
        print("     png falhou:", e)
