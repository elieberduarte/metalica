# -*- coding: utf-8 -*-
"""D03 (agente usuario-desastrado, 13/11, antes da 0.9.3): o Cancelar novo (00c4f44) não cancelava o Detalhar nunca, nem
tarefa longa com a obra aberta numa tela — o botão ficava "cancelando…" e a tarefa ia até o fim. Duas causas, as duas no
"já está gravando?" (_gravou_no_projeto), que via um arquivo do projeto mais novo que o início da tarefa:
  1. o sinal de vida de qualquer tela aberta na obra regrava o aberto.json a cada 60 s (marcar_aberto) — e ele não
     estava entre o que não é gravação da tarefa (_NAO_E_GRAVACAO);
  2. o Detalhar pedido pelo diálogo gravava as opções no projeto.json logo no começo (g.tocar), antes de qualquer conta.
Agora o aberto.json (e a pasta das cenas, gravada pela tela delas) não contam, e as opções do diálogo vão para o
projeto.json só no fim do Detalhar, junto com os desenhos: cancelado, o projeto fica como estava."""
import json
import os
import sys
import tempfile
import threading
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQUI = os.path.dirname(os.path.abspath(__file__))
for p in (RAIZ, AQUI):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest                                                    # noqa: E402
import app                                                        # noqa: E402


@pytest.fixture()
def dados(monkeypatch):
    raiz = tempfile.mkdtemp(prefix="metalica_d03_")
    monkeypatch.setattr(app, "PROJETOS", raiz)
    guardado = dict(app.PROGRESSO)
    app.PROGRESSO.clear()
    app._CANCELAR.clear()
    yield raiz
    app.PROGRESSO.clear()
    app.PROGRESSO.update(guardado)
    app._CANCELAR.clear()


def _projeto():
    from test_reanalise import _tesoura
    g = app._gerente()
    s = g.criar("Obra D03")["slug"]
    doc, _ = _tesoura(222913.0, 251770.0, 12000.0, False)
    with open(g.caminho_modelo(s), "w", encoding="utf-8") as f:
        json.dump(doc.dict(), f)
    return g, s


def test_tela_aberta_na_obra_nao_impede_o_cancelar(dados):
    """O caso do Filipin: a tarefa longa com a obra aberta numa tela (o sinal de vida regrava o aberto.json)."""
    g, s = _projeto()
    feitos = []

    def tarefa():
        try:
            app._progresso(s, "levantando as peças…")
            time.sleep(0.3)
            g.marcar_aberto(s, "OUTRA-MAQUINA", "fulano", minimo=0)    # o sinal de vida da tela, no meio da conta
            time.sleep(0.3)
            app._progresso(s, "planta de localização…")
            feitos.append("inteira")
        except app.TarefaCancelada:
            feitos.append("cancelada")
        finally:
            app._fim_progresso(s)

    t = threading.Thread(target=tarefa)
    t.start()
    time.sleep(0.45)
    assert app.cancelar_tarefa(s)["cancelando"]
    t.join(10)
    assert feitos == ["cancelada"]


def test_detalhar_pelo_dialogo_cancela_e_o_projeto_fica_como_estava(dados, monkeypatch):
    """O Detalhar com as opções do diálogo (rotular…) e o Cancelar logo no começo: sai cancelado, sem desenho novo e sem
    as opções novas no projeto.json."""
    g, s = _projeto()
    antes = json.dumps(g.ler(s).get("opcoes_detalhamento"))
    pasta2d = os.path.join(g.pasta(s), "desenhos-2d")
    desenhos_antes = sorted(os.listdir(pasta2d)) if os.path.isdir(pasta2d) else []
    chamadas = {"n": 0}
    original = app._progresso

    def progresso(s_, etapa, fracao=None):
        chamadas["n"] += 1
        if chamadas["n"] == 2:                      # o usuário clica Cancelar logo depois da 1ª etapa
            app._CANCELAR[s] = time.time()
        return original(s_, etapa, fracao)

    monkeypatch.setattr(app, "_progresso", progresso)
    with pytest.raises(app.TarefaCancelada):
        app.detalhar_projeto(s, {"rotular": True, "converter": False, "parafuso_compra": "metrico"})
    assert json.dumps(g.ler(s).get("opcoes_detalhamento")) == antes
    assert (sorted(os.listdir(pasta2d)) if os.path.isdir(pasta2d) else []) == desenhos_antes
