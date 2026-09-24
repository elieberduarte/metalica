# -*- coding: utf-8 -*-
"""Páginas do programa: toda tela carrega o sinal de vida (web/vivo.js).

Sem ele o programa instalado conclui que nenhuma janela está aberta e se encerra seis
segundos depois de a tela abrir — a página continua à vista, mas qualquer botão dá
"Failed to fetch" (foi o que aconteceu com o PDF da lista de materiais na 0.7.22).
"""
import glob
import os

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def test_toda_pagina_da_sinal_de_vida():
    paginas = glob.glob(os.path.join(WEB, "**", "*.html"), recursive=True)
    assert paginas
    sem = [os.path.relpath(p, WEB) for p in paginas
           if "vivo.js" not in open(p, encoding="utf-8").read()]
    assert not sem, "páginas sem web/vivo.js (o programa fecha sozinho): %s" % ", ".join(sem)
