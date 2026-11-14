# -*- coding: utf-8 -*-
"""Parte "conjuntos" do detalhamento (nucleo2d/detalhar.py é a fachada).

Desde 13/11/2026 o conteúdo está dividido por assunto (pedido do usuário: dois chats deixarem de editar o mesmo
arquivo de 5.400 linhas); este arquivo só junta e reexporta todos os nomes, para o `from nucleo2d.detalhe.conjuntos
import X` de sempre continuar valendo. Código novo: importar do arquivo do assunto.

    conjuntos_grupos     conjuntos iguais, instâncias, eixos, furos das caixas
    conjuntos_curvas     trechos curvos, chanfros, emendas
    conjuntos_tercas     malhas, vizinhos no plano, cortes das terças, telha assentada, polilinhas
    conjuntos_desenho    o desenho de cada conjunto (vistas, cotas, chamadas, cores)
    tesouras_montadas    as tesouras montadas
    contraventamentos    os contraventamentos
    localizacao          localização e chumbação
    elevacoes            as elevações das fachadas
"""
from nucleo2d.detalhe import (conjuntos_grupos as _p1, conjuntos_curvas as _p2, conjuntos_tercas as _p3,
                              conjuntos_desenho as _p4, tesouras_montadas as _p5, contraventamentos as _p6,
                              localizacao as _p7, elevacoes as _p8)

for _p in (_p1, _p2, _p3, _p4, _p5, _p6, _p7, _p8):
    globals().update({_k: _v for _k, _v in vars(_p).items() if not (_k.startswith("__") and _k.endswith("__"))})
del _p
