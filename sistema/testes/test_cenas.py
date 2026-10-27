# -*- coding: utf-8 -*-
"""As cenas (saida/cenas.py, 26/10): a estrutura numa foto do local, guardada no projeto — a foto, os pares de pontos, a
câmera encaixada e a imagem pronta em cenas/ (26/10: "uma pasta… chamada cenas, dentro da pasta da obra"). A conta do encaixe é da tela (verif_cena)."""
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
    assert os.path.isfile(os.path.join(g.pasta(s), "cenas", "dados", "img-2026", "foto.jpg"))
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


def test_camadas_e_cobertura_retratil_da_cena(tmp_path):
    """26/10 ("essa imagem interagir com as camadas, poder abrir a quadra, colocar e tirar a lona"): o que fica desligado e a
    situação da cobertura retrátil gravados na cena."""
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    c = C.gravar(g, s, i, {"desligadas": ["camada:Lona", "sistema:cobertura", "camada:Lona"], "situacao": "aberta"})
    assert c["desligadas"] == ["camada:Lona", "sistema:cobertura"] and c["situacao"] == "aberta"
    assert C.gravar(g, s, i, {"situacao": None})["situacao"] is None
    for ruim in ({"situacao": "meia"}, {"desligadas": "camada:Lona"}, {"desligadas": [1]}):
        with pytest.raises(C.ErroCena):
            C.gravar(g, s, i, ruim)


def test_cena_salva_esconde_os_pontos_ate_editar(tmp_path):
    """27/10 ("salvar cena após a conclusão, para não ficar aparecendo essas bolinhas… ter um para editar cena"): a cena
    pronta fica gravada; só com o encaixe feito; Editar cena volta."""
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    assert not C.ler(g, s, i).get("concluida")
    with pytest.raises(C.ErroCena):                       # sem o encaixe não há o que salvar
        C.gravar(g, s, i, {"concluida": True})
    cam = {"posicao": [-5000, -20000, 1700], "giro": [0, 0, 0, 1], "fov": 60}
    assert C.gravar(g, s, i, {"camera": cam, "concluida": True})["concluida"] is True
    assert C.ler(g, s, i)["concluida"] is True and C.ler(g, s, i)["camera"]["fov"] == 60
    assert C.gravar(g, s, i, {"opacidade": 0.5})["concluida"] is True    # mexer na opacidade não reabre
    assert C.gravar(g, s, i, {"concluida": False})["concluida"] is False
    with pytest.raises(C.ErroCena):
        C.gravar(g, s, i, {"concluida": "sim"})


def test_sol_da_cena(tmp_path):
    """27/10 ("ter as opções de mudar a posição das sombras aqui na composição da cena"): o sol gravado na cena."""
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    assert "sol" not in C.ler(g, s, i)                      # a tela usa o sol padrão
    c = C.gravar(g, s, i, {"sol": {"ligado": True, "direcao": 400, "altura": 99}})
    assert c["sol"] == {"ligado": True, "direcao": 40.0, "altura": 85.0}
    assert C.gravar(g, s, i, {"sol": {"ligado": False, "direcao": 120, "altura": 20}})["sol"]["ligado"] is False
    # 27/10 ("fazer as sombras 'interagir' com o chão da quadra"): a força da sombra no chão
    assert C.gravar(g, s, i, {"sol": {"direcao": 120, "altura": 20, "chao": 1.7}})["sol"]["chao"] == 1.0
    assert C.gravar(g, s, i, {"sol": {"direcao": 120, "altura": 20, "chao": 0.35}})["sol"]["chao"] == 0.35
    with pytest.raises(C.ErroCena):
        C.gravar(g, s, i, {"sol": {"direcao": 120, "altura": 20, "chao": "forte"}})
    for ruim in ({"sol": "alto"}, {"sol": {"direcao": 10}}, {"sol": {"ligado": "sim", "direcao": 1, "altura": 30}}):
        with pytest.raises(C.ErroCena):
            C.gravar(g, s, i, ruim)


def test_gravacoes_ao_mesmo_tempo_nao_se_perdem(tmp_path):
    """27/10 (verif_cena, a sombra no chão): a tela grava o sol, as camadas, a lente… cada um no seu tempo, e duas gravações
    da mesma cena ao mesmo tempo usavam o mesmo .tmp — uma caía com erro 500, a outra lia o cena.json no meio da troca
    ("cena desconhecida") ou gravava por cima do campo da outra."""
    import threading
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    erros = []

    campos = [lambda n: {"opacidade": 0.1 + 0.01 * n}, lambda n: {"nome": "Vista %d" % n},
              lambda n: {"desligadas": ["camada:T%d" % n]}, lambda n: {"sol": {"direcao": n, "altura": 30}}]

    def mexer(k):
        for n in range(20):
            try:
                C.gravar(g, s, i, campos[k % 4](n))
            except Exception as e:                       # noqa: BLE001 — qualquer erro conta
                erros.append(repr(e))
    fios = [threading.Thread(target=mexer, args=(k,)) for k in range(4)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    assert not erros, erros[:3]
    c = C.ler(g, s, i)                                   # cada campo com o último valor dele: nenhum gravado por cima
    assert (round(c["opacidade"], 3), c["nome"], c["desligadas"], c["sol"]["direcao"]) == (0.29, "Vista 19", ["camada:T19"], 19.0)


def test_imagem_pronta_vai_para_a_pasta_cenas(tmp_path):
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    C.gravar(g, s, i, {"nome": "Vista: da entrada"})
    png = os.path.join(str(tmp_path), "envio.png")
    with open(png, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    r = C.rota_post(g, s, [i, "imagem"], {"arquivo_local": png})
    assert r["nome"] == "Cena - Vista- da entrada.png"
    assert os.path.isfile(os.path.join(g.pasta(s), "cenas", r["nome"]))
    # e a aba Arquivos a mostra (só a imagem: a foto e os dados da cena, em cenas/dados, não)
    from saida import arquivos_projeto as A
    lista = A.listar(g.pasta(s), lambda c: c)
    assert [(a["nome"], a["pasta"]) for a in lista] == [(r["nome"], "cenas")] and lista[0]["descricao"].startswith("Cena")


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
    assert not os.path.exists(os.path.join(g.pasta(s), "cenas", "dados", i))


def test_arranjo_de_antes_muda_sozinho(tmp_path):
    """A 1ª versão (26/10) gravava os dados em cenas/<id> e a imagem em documentos/ (a Kaefer): mudam na 1ª abertura."""
    import json
    g, s = _gerente(tmp_path)
    velho = os.path.join(g.pasta(s), "cenas", "whatsapp")
    os.makedirs(velho)
    json.dump({"id": "whatsapp", "nome": "WhatsApp", "criada": "2026-10-26T20:00:00"}, open(os.path.join(velho, "cena.json"), "w"))
    os.makedirs(os.path.join(g.pasta(s), "documentos"))
    open(os.path.join(g.pasta(s), "documentos", "Cena - WhatsApp.png"), "wb").write(b"png")
    open(os.path.join(g.pasta(s), "documentos", "Proposta.pdf"), "wb").write(b"pdf")
    assert [c["id"] for c in C.listar(g, s)["cenas"]] == ["whatsapp"]
    assert os.path.isfile(os.path.join(g.pasta(s), "cenas", "dados", "whatsapp", "cena.json"))
    assert os.path.isfile(os.path.join(g.pasta(s), "cenas", "Cena - WhatsApp.png"))
    assert sorted(os.listdir(os.path.join(g.pasta(s), "documentos"))) == ["Proposta.pdf"]
    # e a cena apagada pela metade (só a foto ficou, a 1ª versão do apagar) sai
    meia = os.path.join(g.pasta(s), "cenas", "meia")
    os.makedirs(meia)
    open(os.path.join(meia, "foto.jpg"), "wb").write(b"jpg")
    C.listar(g, s)
    assert sorted(os.listdir(os.path.join(g.pasta(s), "cenas"))) == ["Cena - WhatsApp.png", "dados"]


def test_apagar_com_a_foto_presa(tmp_path, monkeypatch):
    """26/10 (Kaefer): "não consigo apagar uma cena" — no Windows a foto pode estar presa (o OneDrive, o navegador) e o apagar
    parava no meio, a cena pela metade. Agora a pasta sai da lista na hora e o resto é removido quando der."""
    import shutil
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    monkeypatch.setattr(shutil, "rmtree", lambda *a, **k: None)              # nada sai do disco (tudo preso)
    assert C.apagar(g, s, i)["cenas"] == []
    assert C.listar(g, s)["cenas"] == []
    assert not os.path.exists(os.path.join(g.pasta(s), "cenas", "dados", i))


def test_so_jpg_e_png(tmp_path):
    g, s = _gerente(tmp_path)
    caminho = os.path.join(str(tmp_path), "doc.pdf")
    with open(caminho, "wb") as f:
        f.write(b"%PDF")
    with pytest.raises(C.ErroCena, match="JPG ou PNG"):
        C.nova(g, s, {"arquivo_local": caminho, "nome": "doc.pdf"})
    assert not os.path.exists(caminho)
