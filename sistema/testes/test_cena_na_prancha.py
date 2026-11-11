# -*- coding: utf-8 -*-
"""A cena na prancha (usuário, 11/11: "pode fazer" — a etapa 4 da tela das Cenas; amostra-2 aprovada): o objeto imagem do
CAD 2D (nucleo2d.desenho.Imagem) — viva (o render atual da cena) ou fixa (a cópia congelada) —, as rotas que entregam a
imagem, a moldura no DXF e a imagem no PDF da prancha."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nucleo2d.desenho import Desenho, Imagem, Linha, entidade_de_dict, transladar  # noqa: E402
from saida import cenas as C                                                      # noqa: E402
from projetos import Projetos                                                     # noqa: E402

_CAM = {"posicao": [10000, -20000, 8000], "alvo": [0, 0, 0], "fov": 45}


def _obra(tmp_path, render=True, cor=(30, 90, 200)):
    from PIL import Image
    g = Projetos(str(tmp_path))
    r = g.criar("Obra")
    s = r.get("slug") or r.get("id") or "obra"
    i = C.nova_3d(g, s, {"nome": "Fachada", "camera": _CAM})["id"]
    if render:
        caminho = os.path.join(str(tmp_path), "envio.jpg")
        Image.new("RGB", (320, 180), cor).save(caminho, "JPEG")
        C.rota_post(g, s, [i, "imagem"], {"arquivo_local": caminho, "nome": "render.jpg"})
    return g, s, i


def test_a_entidade_imagem_vai_e_volta_e_anda():
    e = entidade_de_dict({"tipo": "imagem", "id": "x", "camada": "VISTA", "posicao": [10, 20], "largura": 160, "altura": 90,
                          "cena": "fachada", "nome": "Fachada", "viva": False, "arquivo": "fachada-1.jpg"})
    assert isinstance(e, Imagem) and e.posicao == (10, 20) and not e.viva
    assert e.pontos() == [(10, 20), (170, 20), (170, 110), (10, 110)]
    assert transladar(e, 5, -5).posicao == (15, 15)


def test_a_moldura_no_dxf():
    d = Desenho(nome="t", escala=1.0)
    d.add(Imagem(camada="VISTA", posicao=(0, 0), largura=160, altura=90, cena="fachada"))
    texto = open(d.para_dxf().gravar(os.path.join(os.environ.get("TEMP", "/tmp"), "moldura_cena.dxf")), encoding="latin-1").read()
    assert "POLYLINE" in texto or "LWPOLYLINE" in texto


def test_viva_e_fixa_pelas_rotas(tmp_path):
    g, s, i = _obra(tmp_path)
    pasta = g.pasta(s)
    viva = C.rota_get(g, s, [i, "render.jpg"])["arquivo"]
    assert viva.endswith("Cena - Fachada (render).jpg") and C.arquivo_da_imagem(pasta, i, True) == viva
    f = C.rota_post(g, s, [i, "fixar"], {})
    fixa = C.rota_get(g, s, ["prancha", f["arquivo"]])["arquivo"]
    assert os.path.isfile(fixa) and f["arquivo"].startswith(i + "-") and C.arquivo_da_imagem(pasta, i, False, f["arquivo"]) == fixa
    # a fixa fica mesmo que a cena seja renderizada de novo ou apagada; fora da pasta, nada
    C.apagar(g, s, i)
    assert C.arquivo_da_imagem(pasta, i, True) is None and os.path.isfile(fixa)
    assert C.arquivo_da_imagem(pasta, "", False, "../../projeto.json") is None
    with pytest.raises(C.ErroCena):
        C.rota_get(g, s, [i, "render.jpg"])


def test_fixar_sem_render_avisa(tmp_path):
    g, s, i = _obra(tmp_path, render=False)
    with pytest.raises(C.ErroCena, match="ainda não tem render"):
        C.rota_post(g, s, [i, "fixar"], {})


def test_a_imagem_no_pdf_da_prancha(tmp_path):
    from nucleo2d.pranchas import pdf_dos_desenhos
    g, s, i = _obra(tmp_path)
    d = Desenho(nome="prancha", escala=1.0)
    d.add(Linha(camada="VISTA", a=(0, 0), b=(200, 0)))
    d.add(Imagem(camada="VISTA", posicao=(10, 10), largura=160, altura=90, cena=i, nome="Fachada"))
    com = pdf_dos_desenhos([d], os.path.join(str(tmp_path), "com.pdf"), pasta_projeto=g.pasta(s))
    assert b"/Subtype /Image" in open(com, "rb").read()
    # sem a pasta do projeto (ou sem render): só a moldura, e o aviso
    avisos = []
    C.apagar(g, s, i)
    sem = pdf_dos_desenhos([d], os.path.join(str(tmp_path), "sem.pdf"), pasta_projeto=g.pasta(s), avisos=avisos)
    assert b"/Subtype /Image" not in open(sem, "rb").read()
    assert any("Fachada" in a and "não foi achada" in a for a in avisos)
