# -*- coding: utf-8 -*-
"""Uma célula por vez, ampliada: posições e conjuntos escolhidos."""
import json, os, sys
if len(sys.argv) < 2:
    print("ferramenta de diagnóstico, não verificador: python verif_celula.py P12,P77 [escala]")
    sys.exit(0)
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE)
SCR = os.path.dirname(os.path.abspath(__file__))
from nucleo3d.modelo import Documento
from nucleo2d import detalhar
from nucleo2d.desenho import Desenho
from saida import dxf_render
doc = Documento.de_dict(json.load(open(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), encoding="utf-8")))
pecas, _ = detalhar._pecas(doc)
posicoes, camadas = detalhar._posicoes_de(pecas)
mud = detalhar.regra_furacao_terca(posicoes, camadas)
for k, v in mud.items():
    print(k, "->", v)
quais = sys.argv[1].split(",")
for marca in quais:
    pos = next(p for p in posicoes if p.marca == marca)
    print(marca, pos.classe, pos.perfil, "L=%.0f H=%.0f T=%.1f" % (pos.L, pos.H, pos.T), "furos:", [(f.vista, round(f.x), round(f.y), f.rotulo()) for f in pos.furos][:12], pos.observacoes)
    d = Desenho(nome=marca, escala=float(sys.argv[2]) if len(sys.argv) > 2 else 10.0)
    detalhar.desenho_da_posicao(pos, d, 0, 0)
    dxf = d.para_dxf().gravar(os.path.join(SCR, "det2d", "cel_%s.dxf" % marca))
    dxf_render.para_png(dxf, os.path.join(SCR, "det2d", "cel_%s.png" % marca), dpi=110, largura=16)
