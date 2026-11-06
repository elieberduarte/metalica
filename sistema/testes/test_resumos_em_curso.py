# -*- coding: utf-8 -*-
"""Os resumos da obra gerados no "Gerar de novo" (usuário, 06/11: "Se clico para gerar um novo resumo e saio da tela ele
interrompe o processo, preciso que corrija isso para ele continuar gerando em segundo plano"). A geração roda no pedido e
segue até o fim mesmo quando a tela sai (provado: pedido abandonado em 2 s, PDFs gravados 352 s depois); quem voltava via
o resumo antigo com o botão livre, e o novo clique começava outra geração junto. Agora o GET diz que estão sendo gerados
(desde quando), e o segundo pedido espera a mesma geração e devolve o mesmo resultado."""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                                    # noqa: E402
import app                                                        # noqa: E402


def test_resumos_em_curso_aparecem_no_get_e_o_segundo_pedido_espera_o_mesmo(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    s = app._gerente().criar("Obra")["slug"]
    chamadas, pode = [], threading.Event()

    def gerar(s_, corpo, porta=None):
        chamadas.append(s_)
        pode.wait(10)
        return {"numeros": {"peso": 1}, "avisos": [], "dados": {}}
    monkeypatch.setattr(app, "_gerar_resumos_projeto", gerar)
    r = {}
    t1 = threading.Thread(target=lambda: r.setdefault("clique", app.gerar_resumos_projeto(s, {"dados": {}})))
    t1.start()
    time.sleep(0.3)
    volta = app.dados_dos_resumos(s)                               # a tela que saiu e voltou
    assert volta["atualizando"] and volta["atualizando"]["desde"]
    t2 = threading.Thread(target=lambda: r.setdefault("de_novo", app.gerar_resumos_projeto(s, {"dados": {}})))
    t2.start()
    time.sleep(0.3)
    pode.set()
    t1.join(10)
    t2.join(10)
    assert chamadas == [s]                                         # uma geração só
    assert r["clique"] is r["de_novo"] and r["clique"]["numeros"] == {"peso": 1}
    assert app.resumos_em_curso(s) is None and app.dados_dos_resumos(s)["atualizando"] is None


def test_geracao_que_falha_nao_prende_e_o_segundo_recebe_o_erro(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    s = app._gerente().criar("Obra")["slug"]
    pode = threading.Event()

    def quebra(*a, **k):
        pode.wait(10)
        raise RuntimeError("modelo ilegível")
    monkeypatch.setattr(app, "_gerar_resumos_projeto", quebra)
    erros = []

    def chamar():
        try:
            app.gerar_resumos_projeto(s, {})
        except RuntimeError as e:
            erros.append(str(e))
    t1 = threading.Thread(target=chamar); t1.start(); time.sleep(0.3)
    t2 = threading.Thread(target=chamar); t2.start(); time.sleep(0.3)
    pode.set(); t1.join(10); t2.join(10)
    assert erros == ["modelo ilegível", "modelo ilegível"]
    assert app.resumos_em_curso(s) is None
