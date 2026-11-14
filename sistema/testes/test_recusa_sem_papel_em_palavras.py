# -*- coding: utf-8 -*-
"""No programa instalado, a recusa do Apontar quando o papel nunca veio da nuvem diz o motivo em palavras (14/11/2026,
GESTÃO · CHATS N.10; achado do CONTROLE N.2 ao corrigir o selo sem internet, 9e29f5a).

Antes (producao/web.py): "não deu para saber o seu papel nesta obra compartilhada (sem conexão com a nuvem do Metálica
([WinError 10061] Nenhuma conexão pôde ser feita porque a máquina de destino as recusou)) — conecte à internet…" — o
erro do urllib ia cru para a janela do Fernando. Agora: "(sem internet) — conecte à internet e abra o Controle de novo";
a nuvem que não responde ou responde 5xx: "(a nuvem do Metálica não respondeu)"; o recado da própria nuvem (sem acesso a
esta obra) segue como ela diz. O texto técnico vai para o log (stderr do servidor)."""
import pytest

import obra_compartilhada as OC
from nucleo.base import ErroDeDados
from test_obra_compartilhada import _post, controle_web, nuvem    # noqa: F401 — as fixtures da obra compartilhada

WIN = "sem conexão com a nuvem do Metálica ([WinError 10061] Nenhuma conexão pôde ser feita porque a máquina de destino as r)"


@pytest.fixture
def instalado(controle_web, nuvem, monkeypatch):                 # noqa: F811
    web, pastas = controle_web
    app_dev = web._app()

    class _Instalado(app_dev):
        DEV = False

        @staticmethod
        def etapas_do_projeto(s):
            return {"etapas": [{"chave": "producao", "itens": []}]}
    monkeypatch.setattr(web, "_app", lambda: _Instalado)
    nuvem.eu = "fer"
    return web


def _recusa(web, monkeypatch, erro, status=None):
    def pedir(*a, **k):
        raise OC.ErroObra(erro, status) if status else OC.ErroObra(erro)
    monkeypatch.setattr(OC, "_pedir", pedir)
    with pytest.raises(ErroDeDados) as e:
        _post(web, "/api/producao/apontar", {"projeto": "fer", "item": "T38-1", "etapa": "producao", "quantidade": 1})
    return str(e.value)


def test_sem_internet_sem_o_texto_do_windows(instalado, monkeypatch, capsys):
    m = _recusa(instalado, monkeypatch, WIN)
    assert "WinError" not in m and "máquina de destino" not in m, m
    assert m == "não deu para saber o seu papel nesta obra compartilhada (sem internet) — conecte à internet e abra o Controle de novo"
    assert "WinError 10061" in capsys.readouterr().err          # o detalhe técnico fica no log do servidor


def test_a_nuvem_que_nao_responde(instalado, monkeypatch):
    assert "(a nuvem do Metálica não respondeu a tempo)" in _recusa(instalado, monkeypatch,
                                                                    "sem conexão com a nuvem do Metálica (timed out)")
    m = _recusa(instalado, monkeypatch, "a nuvem recusou o pedido (502)", 502)
    assert "(a nuvem do Metálica não respondeu)" in m and "502" not in m


def test_o_recado_da_nuvem_segue_em_palavras(instalado, monkeypatch):
    m = _recusa(instalado, monkeypatch, "esta licença não tem acesso a esta obra compartilhada — peça ao responsável", 403)
    assert m == ("não deu para saber o seu papel nesta obra compartilhada: esta licença não tem acesso a esta obra "
                 "compartilhada — peça ao responsável")
