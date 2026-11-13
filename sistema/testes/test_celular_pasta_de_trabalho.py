# -*- coding: utf-8 -*-
"""A pasta do celular (pacotes, aparelhos, nuvem.json) com os dados de verdade em METALICA_DADOS (celular/web.em_teste).

Defeito (13/11, usuário: "não temos essa opção de enviar para o celular novamente, só consigo habilitar e desabilitar"):
desde 04/11 os dados de verdade estão em C:\\Metálica\\dados pela variável METALICA_DADOS, e o celular tomava a variável
por "teste" — o dev usava C:\\Metálica\\dados\\.celular, vazia: a nuvem desligada, nenhum aparelho, e nada mais subiu para o
celular pela nuvem desde 04/11 (as pranchas originais do 7201dae não chegavam). A configuração de verdade estava em
%LOCALAPPDATA%\\Metálica\\celular. Teste é só o `--dados` (verificadores), a marca METALICA_TESTE ou METALICA_DADOS numa
pasta temporária (o conftest)."""
import os
import sys
import tempfile
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celular import web as W                      # noqa: E402


@pytest.fixture
def maquina(tmp_path, monkeypatch):
    """Uma máquina como a do usuário: METALICA_DADOS = a pasta de dados de verdade (fora da temporária), o dev sem --dados."""
    dados = tmp_path / "Metalica" / "dados"
    dados.mkdir(parents=True)
    local = tmp_path / "LocalAppData"
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "Temp"))     # a pasta de dados NÃO é temporária
    monkeypatch.setenv("METALICA_DADOS", str(dados))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("METALICA_TESTE", raising=False)
    monkeypatch.delenv("METALICA_CELULAR_DIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["app.py", "--dev", "--reaberto"])
    monkeypatch.setitem(sys.modules, "app", types.SimpleNamespace(PROJETOS=str(dados), referencia_do_lancamento=lambda s: None))
    monkeypatch.setattr(W, "_UNICO", None)
    return dados, local


def test_dados_de_verdade_usam_a_configuracao_de_verdade(maquina):
    dados, local = maquina
    c = W.celular()
    assert ".celular" not in c.trabalho, c.trabalho
    assert os.path.normcase(c.trabalho) == os.path.normcase(os.path.join(str(local), "Metálica", "celular"))
    assert not W.em_teste()


@pytest.mark.parametrize("como", ["--dados", "METALICA_TESTE", "temporaria"])
def test_os_testes_continuam_na_pasta_propria(maquina, monkeypatch, tmp_path, como):
    dados, _local = maquina
    if como == "--dados":
        monkeypatch.setattr(sys, "argv", ["app.py", "--dados", str(dados)])
    elif como == "METALICA_TESTE":
        monkeypatch.setenv("METALICA_TESTE", "1")
    else:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))         # o conftest: dados dentro da temporária
    assert W.em_teste()
    c = W.celular()
    assert os.path.normcase(c.trabalho) == os.path.normcase(os.path.join(str(dados), ".celular"))
