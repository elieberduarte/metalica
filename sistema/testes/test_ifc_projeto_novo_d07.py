# -*- coding: utf-8 -*-
"""D07 (agente usuario-desastrado, 13/11): o IFC que falha deixava um projeto vazio na lista, e o nome repetido passava
sem aviso.

- "Novo a partir de IFC…" cria o projeto e depois importa. Com um arquivo ruim a importação falhava e o projeto ficava
  na lista, sem modelo — um a cada tentativa. Agora o projeto criado só para receber o IFC (`aguardando_ifc`) sai junto
  com a importação que falha: apagado quando só tem o projeto.json; para a lixeira quando o IFC chegou a entrar.
- O segundo projeto com o mesmo nome virava `<nome>-2`, e a lista ficava com dois cartões iguais. Agora a tela de
  Projetos pede `conferir_nome`: o servidor recusa dizendo qual projeto já tem o nome, a tela pergunta e, confirmado,
  cria. Quem cria sem o campo (os scripts, os outros módulos) segue como antes.
"""
import base64
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from nucleo.base import ErroDeDados                           # noqa: E402
from projetos import LIXEIRA                                  # noqa: E402

INTEIRO = os.path.join(AQUI, "dados_ifc", "estrutura_mm.ifc")
PNG = b"\x89PNG\r\n\x1a\n" + bytes(600)


def _b64(bruto):
    return base64.b64encode(bruto).decode("ascii")


def _ifc():
    with open(INTEIRO, "rb") as f:
        return f.read()


@pytest.fixture
def app_g(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    return app, app._gerente()


def _na_lista(g):
    return sorted(p["slug"] for p in g.listar())


def _na_lixeira(g):
    lixo = os.path.join(g.raiz, LIXEIRA)
    return sorted(os.listdir(lixo)) if os.path.isdir(lixo) else []


# ------------------------------------------------------------------ o projeto que nasce para o IFC
def test_o_ifc_que_falha_nao_deixa_o_projeto_novo_na_lista(app_g):
    app, g = app_g
    s = app.criar_projeto({"nome": "Vazio", "tipo": "ifc", "aguardando_ifc": True})["slug"]
    assert _na_lista(g) == [s]
    with pytest.raises(ErroDeDados) as e:
        app.acao_de_projeto(s, "importar-ifc", {"nome": "foto.ifc", "conteudo_b64": _b64(PNG)})
    assert "não é um IFC" in str(e.value) and str(e.value).endswith("O projeto não foi criado.")
    assert _na_lista(g) == [] and not os.path.exists(os.path.join(g.raiz, s))
    assert _na_lixeira(g) == []                               # só tinha o projeto.json: apagado, sem encher a lixeira
    # e a segunda tentativa com o mesmo nome não vira "vazio-2"
    assert app.criar_projeto({"nome": "Vazio", "tipo": "ifc", "aguardando_ifc": True, "conferir_nome": True})["slug"] == s


def test_sem_arquivo_nenhum_tambem_nao_fica(app_g):
    app, g = app_g
    s = app.criar_projeto({"nome": "Sem arquivo", "tipo": "ifc", "aguardando_ifc": True})["slug"]
    with pytest.raises(ErroDeDados) as e:
        app.importar_ifc_no_projeto(s, {"nome": "vazio.ifc"})
    assert "nenhum arquivo" in str(e.value) and "O projeto não foi criado." in str(e.value)
    assert _na_lista(g) == []


def test_a_importacao_que_quebra_com_o_ifc_ja_na_pasta_manda_o_projeto_para_a_lixeira(app_g, monkeypatch):
    """O IFC de verdade que o importador não aguenta: o projeto não fica na lista, mas o arquivo não é apagado."""
    app, g = app_g
    from ifc import importar as imp
    s = app.criar_projeto({"nome": "Quebra", "tipo": "ifc", "aguardando_ifc": True})["slug"]

    def quebra(caminho, **k):
        raise RuntimeError("geometria que o importador não conhece")

    monkeypatch.setattr(imp, "importar", quebra)
    with pytest.raises(RuntimeError):
        app.importar_ifc_no_projeto(s, {"nome": "modelo.ifc", "conteudo_b64": _b64(_ifc())})
    assert _na_lista(g) == []
    lixo = _na_lixeira(g)
    assert len(lixo) == 1 and lixo[0].startswith(s + "-")
    assert os.path.isfile(os.path.join(g.raiz, LIXEIRA, lixo[0], "origem", "modelo.ifc"))


def test_o_ifc_bom_fica_e_a_marca_sai(app_g):
    app, g = app_g
    s = app.criar_projeto({"nome": "Bom", "tipo": "ifc", "aguardando_ifc": True})["slug"]
    assert g.ler(s)["aguardando_ifc"] is True
    app.importar_ifc_no_projeto(s, {"nome": "modelo.ifc", "conteudo_b64": _b64(_ifc())})
    assert _na_lista(g) == [s] and not g.ler(s).get("aguardando_ifc")
    assert app.descartar_projeto_novo(s) == {"descartado": False, "existe": True}
    # daí em diante é um projeto como os outros: o IFC ruim importado por cima é recusado e o projeto fica
    with pytest.raises(ErroDeDados) as e:
        app.importar_ifc_no_projeto(s, {"nome": "foto.ifc", "conteudo_b64": _b64(PNG)})
    assert "O projeto não foi criado" not in str(e.value)
    assert _na_lista(g) == [s] and os.path.exists(g.caminho_modelo(s))


def test_o_projeto_que_nao_nasceu_para_o_ifc_nunca_e_descartado(app_g):
    app, g = app_g
    s = app.criar_projeto({"nome": "De antes", "tipo": "ifc"})["slug"]       # sem a marca: criado por outro caminho
    with pytest.raises(ErroDeDados) as e:
        app.importar_ifc_no_projeto(s, {"nome": "foto.ifc", "conteudo_b64": _b64(PNG)})
    assert "O projeto não foi criado" not in str(e.value)
    assert _na_lista(g) == [s]
    assert app.acao_de_projeto(s, "descartar-novo", {}) == {"descartado": False, "existe": True}
    assert _na_lista(g) == [s]


def test_descartar_o_que_falhou_antes_de_chegar_a_importacao(app_g):
    """O envio cortado no meio (ou de 0 bytes) falha antes da rota da importação: a tela pede o descarte."""
    app, g = app_g
    s = app.criar_projeto({"nome": "Envio cortado", "tipo": "ifc", "aguardando_ifc": True})["slug"]
    from projetos import ABERTO
    with open(os.path.join(g.raiz, s, ABERTO), "w", encoding="utf-8") as f:
        f.write("{}")                                         # o sinal de vida da tela não segura o descarte
    r = app.acao_de_projeto(s, "descartar-novo", {})
    assert r["descartado"] is True and r["existe"] is False
    assert _na_lista(g) == [] and _na_lixeira(g) == []
    assert app.descartar_projeto_novo(s) == {"descartado": False, "existe": False}      # de novo: nada a fazer


# ------------------------------------------------------------------ o nome repetido
def test_nome_repetido_e_recusado_quando_a_tela_pede_para_conferir(app_g):
    app, g = app_g
    s = app.criar_projeto({"nome": "PORTARIA HERMES", "tipo": "ifc"})["slug"]
    for nome in ("PORTARIA HERMES", "Portaria  Hermes", " portaria hermes "):
        with pytest.raises(ErroDeDados) as e:
            app.criar_projeto({"nome": nome, "tipo": "ifc", "conferir_nome": True})
        assert 'Já existe um projeto chamado "PORTARIA HERMES"' in str(e.value)
        assert e.value.nome_repetido == {"nome": "PORTARIA HERMES", "slug": s, "arquivado": False}
    assert _na_lista(g) == [s]                                # nenhum "portaria-hermes-2"
    # confirmado na tela, o pedido vem sem o campo e cria (como sempre foi para os scripts)
    assert app.criar_projeto({"nome": "PORTARIA HERMES", "tipo": "ifc"})["slug"] == s + "-2"
    # nome diferente passa direto
    assert app.criar_projeto({"nome": "Portaria Hermes 2", "tipo": "ifc", "conferir_nome": True})["slug"]


def test_o_arquivado_tambem_conta_e_o_recado_diz(app_g):
    app, g = app_g
    s = app.criar_projeto({"nome": "Galpão antigo", "tipo": "galpao"})["slug"]
    g.arquivar(s)
    with pytest.raises(ErroDeDados) as e:
        app.criar_projeto({"nome": "galpão antigo", "tipo": "galpao", "conferir_nome": True})
    assert "(arquivado)" in str(e.value) and e.value.nome_repetido["arquivado"] is True


def test_a_resposta_do_erro_leva_o_nome_repetido(app_g):
    """A tela só consegue perguntar "criar mesmo assim?" se a resposta disser que o erro é de nome repetido."""
    app, g = app_g
    app.criar_projeto({"nome": "Obra", "tipo": "galpao"})
    with pytest.raises(ErroDeDados) as e:
        app.criar_projeto({"nome": "Obra", "tipo": "galpao", "conferir_nome": True})

    class Falso:
        def _json(self, corpo, status=200):
            self.corpo, self.status = corpo, status

    falso = Falso()
    app.Handler._erro(falso, e.value, 400)
    assert falso.status == 400 and falso.corpo["nome_repetido"]["slug"] == "obra" and "Já existe" in falso.corpo["erro"]
