# -*- coding: utf-8 -*-
"""O vigia de janelas do programa instalado: um pedido HTTP atendido há pouco conta como
sinal de vida (a página que entra pelo "voltar" pede arquivos antes de mandar o sinal),
e a troca de página tem 30 s, não 6 — o servidor se encerrava com a janela na tela."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app                                   # noqa: E402


def test_pedido_recente_conta_como_sinal_de_vida():
    antes = app._ULTIMO_PEDIDO[0]
    try:
        app._ULTIMO_PEDIDO[0] = time.time()
        assert app._pedido_recente()
        app._ULTIMO_PEDIDO[0] = time.time() - app.SILENCIO_TROCA_DE_PAGINA - 1.0
        assert not app._pedido_recente()
        app._ULTIMO_PEDIDO[0] = time.time() - 10.0
        assert app._pedido_recente() and not app._pedido_recente(5.0)
    finally:
        app._ULTIMO_PEDIDO[0] = antes


def test_troca_de_pagina_tem_folga_de_meio_minuto():
    assert app.SILENCIO_TROCA_DE_PAGINA >= 30.0
    # o sinal de vida das páginas continua a cada 5 s (web/vivo.js), bem dentro da folga
    with open(os.path.join(os.path.dirname(app.__file__), "web", "vivo.js"), encoding="utf-8") as f:
        assert "setInterval(sinal, 5000)" in f.read()
