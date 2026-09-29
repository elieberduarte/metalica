# -*- coding: utf-8 -*-
"""A barrinha da conferência no modo desenvolvimento: o que testes/progresso.py grava enquanto a
conferência roda e o que o servidor calcula disso (app.estado_da_conferencia)."""
import importlib
import os

import pytest

import app


def _arquivo(agora):
    return {"inicio": agora - 400, "atualizado": agora - 5, "fim": None, "ok": None, "texto": "verif_cad",
            "etapas": [{"nome": "testes automáticos", "est": 100.0, "ini": agora - 400, "fim": agora - 300, "ok": True},
                       {"nome": "verificadores das telas", "est": 1000.0, "ini": agora - 300, "fim": None, "ok": None,
                        "feito": 20, "total": 40},
                       {"nome": "bateria das obras", "est": 200.0, "ini": None, "fim": None, "ok": None}]}


def test_meio_da_conferencia():
    agora = 10000.0
    c = app.estado_da_conferencia(_arquivo(agora), agora)
    # testes inteiros (100) + metade dos verificadores (500) de 1300
    assert c["pct"] == pytest.approx(100 * 600 / 1300, abs=0.1)
    assert (c["etapa"], c["n_etapa"], c["etapas"], c["feito"], c["total"]) == ("verificadores das telas", 2, 3, 20, 40)
    assert c["resta_s"] == 500 + 200 and c["texto"] == "verif_cad" and not c["fim"] and not c["parada"]


def test_fim_mostra_o_resultado_e_depois_some():
    agora = 10000.0
    d = _arquivo(agora)
    d["etapas"][1].update(fim=agora - 60, ok=False)
    d["etapas"][2].update(ini=agora - 60, fim=agora - 10, ok=True)
    d.update(fim=agora - 10, ok=False)
    c = app.estado_da_conferencia(d, agora)
    assert c["fim"] and c["pct"] == 100.0 and c["ok"] is False and c["falhas"] == ["verificadores das telas"]
    assert app.estado_da_conferencia(d, agora + app.CONFERENCIA_MOSTRA + 1) is None
    assert app.estado_da_conferencia(None, agora) is None


def test_sem_noticia_ha_muito_tempo_e_parada():
    agora = 10000.0
    d = _arquivo(agora)
    d["atualizado"] = agora - app.CONFERENCIA_PARADA - 1
    assert app.estado_da_conferencia(d, agora)["parada"]


def test_cancelar_derruba_o_processo_e_marca_o_arquivo(tmp_path):
    """O botão Cancelar: a árvore do pid gravado pela conferência é derrubada, o arquivo fica com fim,
    ok=False e cancelada, a etapa aberta fechada; sem conferência rodando, nada é feito."""
    import json
    arq = tmp_path / "_conferencia.json"
    agora = 10000.0
    d = dict(_arquivo(agora), pid=4321)
    arq.write_text(json.dumps(d), encoding="utf-8")
    mortos = []
    r = app.cancelar_conferencia(matar=lambda pid: mortos.append(pid) or "ok", arquivo=str(arq))
    assert r["cancelada"] and mortos == [4321]
    d2 = json.loads(arq.read_text(encoding="utf-8"))
    assert d2["cancelada"] and d2["fim"] and d2["ok"] is False and d2["etapas"][1]["fim"] and d2["etapas"][1]["ok"] is False
    c = app.estado_da_conferencia(d2, d2["fim"] + 1)
    assert c["fim"] and c["cancelada"] and c["ok"] is False
    # de novo: já terminou, não derruba nada
    assert not app.cancelar_conferencia(matar=lambda pid: mortos.append(pid), arquivo=str(arq))["cancelada"] and mortos == [4321]
    assert not app.cancelar_conferencia(matar=lambda pid: None, arquivo=str(tmp_path / "nao-existe.json"))["cancelada"]


def test_progresso_grava_as_etapas(tmp_path, monkeypatch):
    import progresso
    importlib.reload(progresso)
    monkeypatch.setattr(progresso, "ARQ", str(tmp_path / "_conferencia.json"))
    monkeypatch.setattr(progresso, "DURACOES", str(tmp_path / "_duracoes.json"))
    monkeypatch.delenv("METALICA_CONFERENCIA", raising=False)
    progresso.passo("testes automáticos", 1, 2)             # sem conferência: não cria nada
    assert progresso._ler() is None
    progresso.iniciar(["testes automáticos", "bateria das obras"])
    progresso.comecar("testes automáticos")
    progresso.terminar("testes automáticos", True)
    progresso.passo("bateria das obras", 2, 5, "posto-cb")
    d = progresso._ler()
    assert d["etapas"][0]["ok"] is True and d["etapas"][1]["feito"] == 2 and d["texto"] == "posto-cb"
    assert d["pid"] == os.getpid() and d["cancelada"] is False
    assert "testes automáticos" in progresso._ler(progresso.DURACOES)
    progresso.fim(True)
    assert progresso._ler()["ok"] is True
    os.environ.pop("METALICA_CONFERENCIA", None)            # iniciar() liga para os processos filhos
