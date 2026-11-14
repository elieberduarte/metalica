# -*- coding: utf-8 -*-
"""D06 (agente usuario-desastrado, 13/11): o IFC truncado ou que não é IFC entrava calado.

- Os primeiros 100 kB de um IFC (sem END-ISO-10303-21) viravam um projeto com 176 das 434 peças, sem aviso nenhum: o
  importador sabia (`truncado` no relatório) e nenhuma tela usava. Agora o recado vai na resposta da rota (`avisos`) e
  fica no projeto.json (`importacao_resumo.truncado` + `aviso`), de onde a lista, o editor e o modo ver o mostram.
- O arquivo cortado bem no fim de uma linha não era visto como truncado (nenhuma instrução pela metade): agora quem
  começou com ISO-10303-21 e não chegou ao END-ISO-10303-21 é truncado.
- Um PNG renomeado para .ifc virava um projeto com 0 peças. Agora é recusado com "não é um IFC", antes de entrar na pasta
  da obra e de tomar o lugar do IFC de antes com o mesmo nome.
"""
import base64
import json
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from ifc.importar import importar, inspecionar                # noqa: E402
from ifc.step import eh_step, ler                             # noqa: E402
from nucleo.base import ErroDeDados                           # noqa: E402

INTEIRO = os.path.join(AQUI, "dados_ifc", "estrutura_mm.ifc")
PNG = b"\x89PNG\r\n\x1a\n" + bytes(600)


def _bruto():
    with open(INTEIRO, "rb") as f:
        return f.read()


def _cortado_no_meio_da_linha():
    b = _bruto()
    return b[:len(b) * 2 // 3].rsplit(b"\n", 1)[0] + b"\n#9001=IFCCARTESIANPOINT((0.,0."


def _cortado_no_fim_da_linha():
    b = _bruto()
    corte = b[:len(b) * 2 // 3].rsplit(b"\n", 1)[0] + b"\n"
    assert corte.rstrip().endswith(b";") and b"END-ISO-10303-21" not in corte
    return corte


def _obra(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    return app, g, g.criar("Obra IFC", tipo="ifc")["slug"]


def _b64(bruto):
    return base64.b64encode(bruto).decode("ascii")


# ------------------------------------------------------------------ o leitor
def test_o_arquivo_inteiro_nao_e_truncado():
    arq = ler(INTEIRO)
    assert arq.inicio and arq.fim and not arq.truncado
    assert not ler(INTEIRO, so_cabecalho=True).truncado       # só o cabeçalho: para antes do fim, e não é corte


@pytest.mark.parametrize("corte", [_cortado_no_meio_da_linha, _cortado_no_fim_da_linha])
def test_o_cortado_e_truncado_no_meio_ou_no_fim_da_linha(tmp_path, corte):
    caminho = str(tmp_path / "cortado.ifc")
    with open(caminho, "wb") as f:
        f.write(corte())
    arq = ler(caminho)
    assert arq.truncado and any("truncado" in a for a in arq.avisos)
    assert importar(caminho).metadados["importacao"]["truncado"] is True
    assert inspecionar(caminho)["truncado"] is True


@pytest.mark.parametrize("nome, bruto, diz", [
    ("foto.ifc", PNG, "não é um IFC"),
    ("vazio.ifc", b"", "vazio"),
    ("compactado.ifc", b"PK\x03\x04" + bytes(100), "compactado"),
    ("em-xml.ifc", b'<?xml version="1.0"?><ifcXML/>', "XML"),
], ids=["imagem", "vazio", "zip", "xml"])
def test_o_que_nao_e_ifc_e_recusado_pelo_importador(tmp_path, nome, bruto, diz):
    caminho = str(tmp_path / nome)
    with open(caminho, "wb") as f:
        f.write(bruto)
    assert not eh_step(caminho)
    for leitura in (importar, inspecionar):
        with pytest.raises(ErroDeDados) as e:
            leitura(caminho)
        assert diz in str(e.value) and nome in str(e.value)


# ------------------------------------------------------------------ a rota do projeto
@pytest.mark.parametrize("corte", [_cortado_no_meio_da_linha, _cortado_no_fim_da_linha])
def test_a_rota_avisa_o_ifc_truncado_e_o_aviso_fica_no_projeto(tmp_path, monkeypatch, corte):
    app, g, s = _obra(tmp_path, monkeypatch)
    r = app.importar_ifc_no_projeto(s, {"nome": "cortado.ifc", "conteudo_b64": _b64(corte())})
    assert r["relatorio"]["truncado"] is True
    assert r["avisos"] and "INCOMPLETO" in r["avisos"][0] and "END-ISO-10303-21" in r["avisos"][0]
    assert r["resumo"]["truncado"] is True and r["resumo"]["aviso"] == r["avisos"][0]
    guardado = g.ler(s)["importacao_resumo"]                  # a lista, o editor e o modo ver leem daqui
    assert guardado["truncado"] is True and "%d peça" % guardado["pecas"] in guardado["aviso"]
    assert [p["ifc_incompleto"] for p in g.listar() if p["slug"] == s] == [True]      # o cartão da lista


def test_a_rota_nao_avisa_o_ifc_inteiro(tmp_path, monkeypatch):
    app, g, s = _obra(tmp_path, monkeypatch)
    r = app.importar_ifc_no_projeto(s, {"nome": "inteiro.ifc", "conteudo_b64": _b64(_bruto())})
    assert r["avisos"] == [] and "truncado" not in r["resumo"] and "aviso" not in r["resumo"]
    assert "truncado" not in g.ler(s)["importacao_resumo"]
    assert [p["ifc_incompleto"] for p in g.listar() if p["slug"] == s] == [False]


def test_a_rota_recusa_o_que_nao_e_ifc_e_o_ifc_de_antes_fica(tmp_path, monkeypatch):
    app, g, s = _obra(tmp_path, monkeypatch)
    app.importar_ifc_no_projeto(s, {"nome": "modelo.ifc", "conteudo_b64": _b64(_bruto())})
    origem = os.path.join(g._existente(s), "origem")
    with open(g.caminho_modelo(s), "rb") as f:
        modelo_antes = f.read()
    with pytest.raises(ErroDeDados) as e:
        app.importar_ifc_no_projeto(s, {"nome": "modelo.ifc", "conteudo_b64": _b64(PNG)})
    assert "não é um IFC" in str(e.value)
    assert os.listdir(origem) == ["modelo.ifc"]               # nada a mais na pasta, nem o ".recebendo"
    with open(os.path.join(origem, "modelo.ifc"), "rb") as f:
        assert f.read() == _bruto()                           # o PNG não tomou o lugar do IFC de antes
    with open(g.caminho_modelo(s), "rb") as f:
        assert f.read() == modelo_antes
    assert "truncado" not in json.dumps(g.ler(s).get("importacao_resumo"))


def test_a_rota_recusa_o_envio_binario_que_nao_e_ifc(tmp_path, monkeypatch):
    """O arquivo grande chega pelo envio binário, já no disco (.envios): recusado, não fica nem lá nem na obra."""
    from nucleo import envios
    app, g, s = _obra(tmp_path, monkeypatch)
    pasta = os.path.join(str(tmp_path), envios.PASTA)
    os.makedirs(pasta, exist_ok=True)
    enviado = os.path.join(pasta, "envio-1.bin")
    with open(enviado, "wb") as f:
        f.write(PNG)
    with pytest.raises(ErroDeDados) as e:
        app.importar_ifc_no_projeto(s, {"nome": "foto.ifc", envios.CAMPO: enviado})
    assert "foto.ifc não é um IFC" in str(e.value)
    assert not os.path.exists(enviado)
    assert os.listdir(os.path.join(g._existente(s), "origem")) == []


def test_a_rota_avulsa_avisa_e_recusa(tmp_path, monkeypatch):
    """O IFC aberto sem projeto (/api/modelo/ifc/importar e a prévia): o mesmo aviso e a mesma recusa."""
    import app
    monkeypatch.setattr(app, "MODELOS", str(tmp_path / "modelos"))
    r = app.importar_ifc({"nome": "cortado.ifc", "conteudo_b64": _b64(_cortado_no_fim_da_linha())})
    assert r["avisos"] and "INCOMPLETO" in r["avisos"][0]
    assert app.importar_ifc({"nome": "inteiro.ifc", "conteudo_b64": _b64(_bruto())})["avisos"] == []
    for rota in (app.importar_ifc, app.inspecionar_ifc):
        with pytest.raises(ErroDeDados) as e:
            rota({"nome": "foto.ifc", "conteudo_b64": _b64(PNG)})
        assert "não é um IFC" in str(e.value)
