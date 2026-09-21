# -*- coding: utf-8 -*-
"""Gera os DXF e os PNG de conferência visual em `projetos/_conferencia/`.

Uso:  PYTHONIOENCODING=utf-8 python testes/conferir.py [nome-do-desenho ...]
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from nucleo.modelo_galpao import DadosGalpao          # noqa: E402
from saida import desenhos, dxf_render                # noqa: E402

PASTA = os.path.join(RAIZ, "projetos", "_conferencia")


def main(filtros=()):
    # confere o que o sistema entrega: o projeto calculado; sem o cálculo, os padrões
    try:
        from nucleo.galpao import dimensionar
        fonte = dimensionar(DadosGalpao())
        print("fonte: projeto calculado (nucleo.galpao.dimensionar)")
    except Exception as erro:                       # cálculo ausente ou quebrado
        fonte = DadosGalpao()
        print(f"fonte: DadosGalpao padrao ({type(erro).__name__}: {erro})")
    os.makedirs(PASTA, exist_ok=True)
    for item in desenhos.gerar_todos(fonte, PASTA):
        if filtros and not any(f.upper() in item["nome"] for f in filtros):
            continue
        png = item["arquivo"].replace(".dxf", ".png")
        dxf_render.para_png(item["arquivo"], png, dpi=130, largura=13.0)
        print(f"{item['nome']:<30} {item['escala']:>7}  "
              f"{item['largura_mm']:.0f} x {item['altura_mm']:.0f} mm  -> {png}")


if __name__ == "__main__":
    main(sys.argv[1:])
