# -*- coding: utf-8 -*-
"""Um conjunto por vez, ampliado."""
import collections, json, math, os, sys
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE)
SCR = os.path.dirname(os.path.abspath(__file__))
from nucleo3d.modelo import Documento
from nucleo2d import detalhar
from nucleo2d.desenho import Desenho
from saida import dxf_render
doc = Documento.de_dict(json.load(open(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), encoding="utf-8")))
pecas, _ = detalhar._pecas(doc)
for marca in sys.argv[1].split(","):
    lista = [e for e in pecas if detalhar._marcas(e).get("conjunto") == marca]
    total = collections.Counter(str(detalhar._marcas(e).get("posicao")) for e in lista)
    n = 0
    for q in total.values(): n = math.gcd(n, q)
    unidade = collections.Counter({k: q // n for k, q in total.items()})
    insts = detalhar._instancias(lista, folga=60.0)
    inst = next((i for i in insts if collections.Counter(str(detalhar._marcas(e).get("posicao")) for e in i) == unidade), None) or max(insts, key=len)
    d = Desenho(nome=marca, escala=float(sys.argv[2]) if len(sys.argv) > 2 else 25.0)
    ext = detalhar.desenho_do_conjunto(doc, marca, inst, n, d, 0, 0, True)
    print(marca, "instâncias", n, "peças na instância", len(inst), "entidades", d.tamanho, "ext", [round(v) for v in ext])
    dxf = d.para_dxf().gravar(os.path.join(SCR, "det2d", "conj_%s.dxf" % marca))
    dxf_render.para_png(dxf, os.path.join(SCR, "det2d", "conj_%s.png" % marca), dpi=110, largura=18)
