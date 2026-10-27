# -*- coding: utf-8 -*-
"""A lista de materiais refeita pelo modelo 3D (SESI, 27/10: "cliquei para atualizar a lista de materiais pelo 3D, porém
se saio dessa tela ele interrompe a atualização"). O levantamento roda no pedido e segue até o fim mesmo quando a tela
sai; quem voltava via a lista antiga sem saber que ela estava sendo refeita, e o novo clique começava outra conta junto.
Agora o GET diz que ela está sendo refeita (desde quando), e o segundo pedido espera a mesma conta."""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app                                                        # noqa: E402
from saida import lista_producao                                  # noqa: E402


def test_lista_em_curso_aparece_no_get_e_o_segundo_pedido_espera_a_mesma(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    s = g.criar("Obra")["slug"]
    pasta = os.path.join(g._existente(s), "detalhamento")
    os.makedirs(pasta)
    arq = os.path.join(pasta, lista_producao.ARQUIVO_JSON)
    with open(arq, "w", encoding="utf-8") as f:
        json.dump({"gerado": "2026-10-27 15:13"}, f)                # a lista de antes
    chamadas, pode = [], threading.Event()

    def levantar(s_, corpo, pasta_):
        chamadas.append(s_)
        pode.wait(10)
        lista = {"gerado": "2026-10-27 17:00"}
        with open(arq, "w", encoding="utf-8") as f:
            json.dump(lista, f)
        return lista
    monkeypatch.setattr(app, "_levantar_lista_de_materiais", levantar)
    r = {}
    t1 = threading.Thread(target=lambda: r.setdefault("clique", app.lista_de_materiais(s, recalcular=True)))
    t1.start()
    time.sleep(0.3)
    # a tela que saiu e voltou: a lista de antes, dizendo que está sendo refeita e desde quando
    volta = app.lista_de_materiais(s)
    assert volta["gerado"] == "2026-10-27 15:13" and volta["atualizando"] and volta["atualizando"]["desde"]
    # o segundo clique (outra aba, ou o mesmo de novo) não começa outra conta: espera a que está rodando
    t2 = threading.Thread(target=lambda: r.setdefault("de_novo", app.lista_de_materiais(s, recalcular=True)))
    t2.start()
    time.sleep(0.3)
    pode.set()
    t1.join(10)
    t2.join(10)
    assert chamadas == [s]
    assert r["clique"]["gerado"] == "2026-10-27 17:00" and r["clique"]["atualizando"] is None
    assert r["de_novo"]["gerado"] == "2026-10-27 17:00"
    assert app.materiais_em_curso(s) is None and app.lista_de_materiais(s)["atualizando"] is None


def test_conta_que_falha_nao_deixa_a_lista_presa_em_atualizando(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    s = g.criar("Obra")["slug"]

    def quebra(*a):
        raise RuntimeError("modelo ilegível")
    monkeypatch.setattr(app, "_levantar_lista_de_materiais", quebra)
    try:
        app.lista_de_materiais(s, recalcular=True)
    except RuntimeError:
        pass
    assert app.materiais_em_curso(s) is None
