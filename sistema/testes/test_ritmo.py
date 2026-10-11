# -*- coding: utf-8 -*-
"""O ritmo da conferência (calmo/cheio — pedido do usuário, 11/10/2026): o arquivo do modo, o que cada modo
libera e a árvore de processos que o vigia acompanha."""
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ritmo  # noqa: E402


def test_modo_padrao_e_troca(tmp_path):
    arq = str(tmp_path / "_conferencia_ritmo.json")
    assert ritmo.modo(arq) == "calmo"                     # sem arquivo: o computador pode estar em uso
    ritmo.gravar("cheio", arq)
    assert ritmo.modo(arq) == "cheio"
    with pytest.raises(ValueError):
        ritmo.gravar("turbo", arq)
    (tmp_path / "_conferencia_ritmo.json").write_text("{quebrado", encoding="utf-8")
    assert ritmo.modo(arq) == "calmo"


def test_calmo_pesa_menos_que_cheio():
    assert ritmo.verificadores_n("calmo") == 1
    assert ritmo.verificadores_n("cheio") >= 1
    assert ritmo.pytest_n("calmo") <= ritmo.pytest_n("cheio")
    assert ritmo.prioridade("calmo") == 0x40 and ritmo.prioridade("cheio") == 0x4000


def test_mascara_metade_de_cima():
    assert ritmo.mascara("cheio", 0xFFF) == 0xFFF
    assert ritmo.mascara("calmo", 0xFFF) == 0xFC0          # 12 lógicos: os 6 de cima, os de baixo ficam livres
    assert ritmo.mascara("calmo", 0b1) == 0b1              # um só: fica com ele
    assert ritmo.mascara("calmo", 0b111) == 0b100


def test_app_le_e_grava_o_mesmo_arquivo(tmp_path):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import app
    arq = str(tmp_path / "_conferencia_ritmo.json")
    assert app.ritmo_da_conferencia(arquivo=arq) == {"modo": "calmo"}
    assert app.ritmo_da_conferencia("cheio", arquivo=arq) == {"modo": "cheio"}
    assert ritmo.modo(arq) == "cheio"
    with pytest.raises(ValueError):
        app.ritmo_da_conferencia("", arquivo=arq)


@pytest.mark.skipif(os.name != "nt", reason="prioridade e processadores pelo Windows")
def test_arvore_segue_o_modo():
    filho = subprocess.Popen([sys.executable, "-c",
                              "import subprocess,sys,time;"
                              "q=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);time.sleep(30)"])
    try:
        neto = None
        for _ in range(40):
            d = ritmo.descendentes(filho.pid)
            if d:
                neto = d[0]
                break
            time.sleep(0.25)
        assert neto, "o neto não apareceu na árvore"
        assert filho.pid in ritmo.descendentes(os.getpid())
        assert ritmo.aplicar("calmo", [filho.pid, neto]) == 2
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-Process -Id %d).PriorityClass; (Get-Process -Id %d).ProcessorAffinity" % (neto, neto)],
                             capture_output=True, text=True).stdout.split()
        assert out[0] == "Idle"
        assert ritmo.aplicar("cheio", [filho.pid, neto]) == 2
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Process -Id %d).PriorityClass" % neto],
                             capture_output=True, text=True).stdout.split()
        assert out[0] == "BelowNormal"
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(filho.pid)], capture_output=True)


def test_verificadores_respeitam_o_ritmo_no_meio(monkeypatch):
    """no calmo, um de cada vez; trocar para o cheio no meio libera os outros trabalhadores"""
    import threading
    import rodar_verificadores as rv
    modo = {"m": "calmo"}
    monkeypatch.setattr(ritmo, "modo", lambda arquivo=None: modo["m"])
    monkeypatch.setattr(rv, "descobrir", lambda filtros=(): (["v%d" % i for i in range(8)], []))
    monkeypatch.setattr(rv, "_porta_fixa", lambda c: None)
    monkeypatch.setattr(rv, "_ler_duracoes", lambda: {})
    monkeypatch.setattr(rv, "_gravar_duracoes", lambda d: None)
    agora, maximo, feitos, trava = [0], {"calmo": 0, "cheio": 0}, [0], threading.Lock()

    def rodar(c):
        with trava:
            agora[0] += 1
            m = modo["m"]
            maximo[m] = max(maximo[m], agora[0])
        time.sleep(0.3)
        with trava:
            agora[0] -= 1
            feitos[0] += 1
            if feitos[0] == 3:
                modo["m"] = "cheio"
        return True, 0.3, [], 1
    monkeypatch.setattr(rv, "rodar", rodar)
    assert rv.main([]) == 0
    assert feitos[0] == 8
    assert maximo["calmo"] == 1
    assert maximo["cheio"] > 1
