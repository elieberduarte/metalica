# -*- coding: utf-8 -*-
"""As cenas (saida/cenas.py, 26/10): a estrutura numa foto do local, guardada no projeto — a foto, os pares de pontos, a
câmera encaixada e a imagem pronta em documentos/. A conta do encaixe é da tela (verif_cena)."""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import cenas as C                            # noqa: E402
from saida import local_obra as L                       # noqa: E402
from projetos import Projetos                           # noqa: E402


def _gerente(tmp_path):
    g = Projetos(str(tmp_path))
    r = g.criar("Quadra")
    return g, (r.get("slug") or r.get("id") or "quadra")


def _foto(tmp_path, nome="IMG_2026.jpg", tam=(4000, 3000), girada=False):
    from PIL import Image
    im = Image.new("RGB", tam, (90, 120, 80))
    caminho = os.path.join(str(tmp_path), "envio-" + nome)
    if girada:                                            # o celular deitado: os pixels em pé e o EXIF dizendo "gire 90°"
        exif = Image.Exif()
        exif[0x0112] = 6
        im.save(caminho, "JPEG", exif=exif)
    else:
        im.save(caminho, "JPEG")
    return {"arquivo_local": caminho, "nome": nome}


def test_nova_cena_pela_rota_do_terreno(tmp_path):
    g, s = _gerente(tmp_path)
    c = L.rota_post(g, s, ["cenas", "nova"], _foto(tmp_path), lambda *a: None)
    assert c["id"] == "img-2026" and c["nome"] == "IMG_2026" and c["px"] == [4000, 3000] and c["pares"] == []
    assert os.path.isfile(os.path.join(g.pasta(s), "cenas", "img-2026", "foto.jpg"))
    assert L.rota_get(g, s, ["cenas"], {})["cenas"][0]["id"] == "img-2026"
    assert L.rota_get(g, s, ["cenas", "img-2026", "foto.jpg"], {})["arquivo"].endswith(os.path.join("img-2026", "foto.jpg"))
    c2 = L.rota_post(g, s, ["cenas", "nova"], _foto(tmp_path), lambda *a: None)
    assert c2["id"] == "img-2026-2"                          # a mesma foto de novo: outra cena


def test_foto_deitada_entra_de_pe_pelo_exif(tmp_path):
    g, s = _gerente(tmp_path)
    c = C.nova(g, s, _foto(tmp_path, tam=(400, 300), girada=True))
    assert c["px"] == [300, 400]


def test_gravar_pares_camera_e_opacidade(tmp_path):
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    c = C.rota_post(g, s, [i], {"pares": [{"foto": [0.1, 0.2], "modelo": [1000, 2000, 0]}, {"foto": [0.5, 0.5]}],
                                "camera": {"posicao": [-5000, -20000, 1700], "giro": [0.5, 0, 0, 0.866], "fov": 74.6, "erro_px": 1.234},
                                "opacidade": 0.8, "nome": "Vista da entrada"})
    assert c["pares"] == [{"foto": [0.1, 0.2], "modelo": [1000.0, 2000.0, 0.0]}, {"foto": [0.5, 0.5]}]
    assert c["camera"]["fov"] == 74.6 and c["camera"]["erro_px"] == 1.23 and c["opacidade"] == 0.8 and c["nome"] == "Vista da entrada"
    assert C.ler(g, s, i)["camera"]["posicao"] == [-5000.0, -20000.0, 1700.0]
    for ruim in ({"pares": [{"foto": [0.1]}]}, {"camera": {"posicao": [0, 0], "giro": [0, 0, 0, 1], "fov": 60}},
                 {"pares": [{"foto": ["x", 1]}]}, {"camera": {"posicao": [0, 0, float("nan")], "giro": [0, 0, 0, 1], "fov": 60}}):
        with pytest.raises(C.ErroCena):
            C.gravar(g, s, i, ruim)


def test_imagem_pronta_vai_para_documentos(tmp_path):
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    C.gravar(g, s, i, {"nome": "Vista: da entrada"})
    png = os.path.join(str(tmp_path), "envio.png")
    with open(png, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    r = C.rota_post(g, s, [i, "imagem"], {"arquivo_local": png})
    assert r["nome"] == "Cena - Vista- da entrada.png"
    assert os.path.isfile(os.path.join(g.pasta(s), "documentos", r["nome"]))


def test_nome_da_cena_nao_sai_da_pasta(tmp_path):
    g, s = _gerente(tmp_path)
    for ruim in ("..", "../outro", "a/b", "A", ""):
        with pytest.raises(C.ErroCena):
            C.rota_get(g, s, [ruim, "foto.jpg"])
    with pytest.raises(C.ErroCena):
        C.rota_post(g, s, ["..", "apagar"], {})


def test_apagar(tmp_path):
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    assert C.apagar(g, s, i)["cenas"] == []
    assert not os.path.exists(os.path.join(g.pasta(s), "cenas", i))


def test_so_jpg_e_png(tmp_path):
    g, s = _gerente(tmp_path)
    caminho = os.path.join(str(tmp_path), "doc.pdf")
    with open(caminho, "wb") as f:
        f.write(b"%PDF")
    with pytest.raises(C.ErroCena, match="JPG ou PNG"):
        C.nova(g, s, {"arquivo_local": caminho, "nome": "doc.pdf"})
    assert not os.path.exists(caminho)
