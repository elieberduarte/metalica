# -*- coding: utf-8 -*-
"""D12 (agente usuario-desastrado, 13/11, antes da 0.9.3): POST /api/projetos/<s>/terreno/cenas/video com o JSON
{"arquivo_local": "<um arquivo qualquer>", "nome": "x.mp4"} respondia 400 "não é um vídeo MP4" e APAGAVA o arquivo. O campo
devia nascer só no envio binário do servidor (_corpo_binario grava em <dados>/.envios), mas vinha aceito do JSON, e as
outras rotas de envio (foto e imagem das cenas, PDF, miniatura, imagem do terreno, IFC) moviam o arquivo para a obra.

Agora o JSON do cliente perde o campo (app._corpo) e todo uso confere que o caminho está na pasta de envios
(nucleo/envios.py). Os arquivos "de fora" aqui ficam numa pasta temporária, nunca em arquivo de verdade."""
import io
import json
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from nucleo import envios                       # noqa: E402
from nucleo.base import ErroDeDados             # noqa: E402
from projetos import Projetos                   # noqa: E402
from saida import cenas as C                    # noqa: E402
from saida import local_obra as L               # noqa: E402

CONTEUDO = b"%PDF-1.4 arquivo de fora que ninguem pode apagar\n"


def _fora(tmp_path, nome="importante.txt"):
    pasta = tmp_path / "fora-dos-dados"
    pasta.mkdir(exist_ok=True)
    caminho = pasta / nome
    caminho.write_bytes(CONTEUDO)
    return str(caminho)


def _intacto(caminho):
    return os.path.isfile(caminho) and open(caminho, "rb").read() == CONTEUDO


def _obra(tmp_path):
    g = Projetos(str(tmp_path / "dados"))
    r = g.criar("Obra D12")
    return g, r.get("slug") or r.get("id")


def test_so_vale_o_arquivo_da_pasta_de_envios(tmp_path):
    raiz = str(tmp_path / "dados")
    os.makedirs(envios.pasta(raiz))
    dentro = os.path.join(envios.pasta(raiz), "123-foto.jpg")
    open(dentro, "wb").close()
    assert envios.arquivo(raiz, {"arquivo_local": dentro}) == dentro
    assert envios.arquivo(raiz, {}) is None
    for caminho in (_fora(tmp_path), os.path.join(envios.pasta(raiz), "..", "projeto.json"), envios.pasta(raiz),
                    raiz, "importante.txt"):
        with pytest.raises(ErroDeDados):
            envios.arquivo(raiz, {"arquivo_local": caminho})


@pytest.mark.parametrize("rota, nome", [
    (["video"], "x.mp4"),                 # o caso do agente: não é MP4 → os.remove
    (["pdf"], "x.pdf"),                   # é "PDF" → os.replace para a obra
    (["nova"], "x.txt"),                  # não é foto → os.remove
])
def test_rotas_das_cenas_nao_tocam_no_arquivo_de_fora(tmp_path, rota, nome):
    g, s = _obra(tmp_path)
    caminho = _fora(tmp_path)
    with pytest.raises(ErroDeDados):
        C.rota_post(g, s, rota, {"arquivo_local": caminho, "nome": nome})
    assert _intacto(caminho)


def test_imagem_e_miniatura_da_cena_nao_tocam_no_arquivo_de_fora(tmp_path):
    g, s = _obra(tmp_path)
    i = C.nova_3d(g, s, {"nome": "Fachada", "camera": {"posicao": [10, 10, 10], "alvo": [0, 0, 0]}})["id"]
    caminho = _fora(tmp_path)
    for resto in ([i, "imagem"], [i, "miniatura"]):
        with pytest.raises(ErroDeDados):
            C.rota_post(g, s, resto, {"arquivo_local": caminho, "nome": "render.jpg"})
        assert _intacto(caminho)


def test_imagem_do_terreno_nao_toca_no_arquivo_de_fora(tmp_path):
    g, s = _obra(tmp_path)
    caminho = _fora(tmp_path, "planta.dxf")
    with pytest.raises(ErroDeDados):
        L.importar_imagem(g, s, {"arquivo_local": caminho, "nome": "planta.dxf"})
    assert _intacto(caminho)


def test_ifc_nao_move_o_arquivo_de_fora(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path / "dados"))
    monkeypatch.setattr(app, "MODELOS", str(tmp_path / "dados" / "modelos"))
    caminho = _fora(tmp_path, "modelo.ifc")
    with pytest.raises(ErroDeDados):
        app.importar_ifc({"arquivo_local": caminho, "nome": "modelo.ifc"})
    assert _intacto(caminho)
    s = app._gerente().criar("Obra IFC")["slug"]
    with pytest.raises(ErroDeDados):
        app.importar_ifc_no_projeto(s, {"arquivo_local": caminho, "nome": "modelo.ifc"})
    assert _intacto(caminho)


def test_json_do_cliente_perde_o_arquivo_local(tmp_path):
    # o pedido HTTP comum (JSON): o campo some antes de chegar a qualquer rota
    import app
    corpo = json.dumps({"arquivo_local": _fora(tmp_path), "nome": "x.mp4"}).encode("utf-8")
    h = object.__new__(app.Handler)
    h.headers = {"Content-Length": str(len(corpo))}
    h.rfile = io.BytesIO(corpo)
    assert h._corpo() == {"nome": "x.mp4"}
