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


def test_o_que_fica_na_frente(tmp_path):
    """27/10 ("a estrutura está atrás desse alambrado, como fazer para o sistema entender isso"): os contornos na foto e
    quanto cada um cobre; a parede é da tela (verif_cena)."""
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]
    assert "frente" not in C.ler(g, s, i)
    c = C.gravar(g, s, i, {"frente": [{"pontos": [[0, 0.34], [0.71, 0.445], [0.71, 0.632], [-0.2, 0.7]], "cobre": 0.7},
                                      {"pontos": [[0.7, 0.44], [1, 0.42], [1.4, 0.63]]}]})
    assert c["frente"] == [{"pontos": [[0.0, 0.34], [0.71, 0.445], [0.71, 0.632], [0.0, 0.7]], "cobre": 0.7},
                           {"pontos": [[0.7, 0.44], [1.0, 0.42], [1.0, 0.63]], "cobre": 1.0}]
    assert C.ler(g, s, i)["frente"][0]["cobre"] == 0.7
    assert C.gravar(g, s, i, {"frente": [{"pontos": [[0, 0], [1, 0], [1, 1]], "cobre": 0}]})["frente"][0]["cobre"] == 0.05
    assert C.gravar(g, s, i, {"frente": []})["frente"] == []
    for ruim in ({"frente": "alambrado"}, {"frente": [{"pontos": [[0, 0], [1, 1]]}]}, {"frente": [{"pontos": [[0, 0], [1], [1, 1]]}]},
                 {"frente": [{"pontos": [[0, 0], [1, 0], [1, 1]], "cobre": "muito"}]},
                 {"frente": [{"pontos": [[0, 0], [1, 0], [1, 1]]}] * (C.FRENTE_MAX + 1)}):
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


def test_render_vai_ao_lado_da_imagem(tmp_path):
    """27/10 ("uma opção para 'renderizar' a imagem"): o render (enviado como render.jpg) vira "Cena - <nome> (render).jpg"
    e não apaga a do Salvar imagem."""
    from PIL import Image
    g, s = _gerente(tmp_path)
    i = C.nova(g, s, _foto(tmp_path))["id"]

    def enviar(nome, fmt):
        caminho = os.path.join(str(tmp_path), "envio-" + nome)
        Image.new("RGB", (20, 10)).save(caminho, fmt)
        return C.rota_post(g, s, [i, "imagem"], {"arquivo_local": caminho, "nome": nome})
    assert enviar("cena.png", "PNG")["nome"] == "Cena - IMG_2026.png"
    assert enviar("render.jpg", "JPEG")["nome"] == "Cena - IMG_2026 (render).jpg"
    assert sorted(os.listdir(os.path.join(g.pasta(s), "cenas"))) == ["Cena - IMG_2026 (render).jpg", "Cena - IMG_2026.png", "dados"]


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


# ---------------------------------------------------------------- as cenas do 3D (11/11: "criar cena… salvar cena")

_CAM = {"posicao": [-20000, -30000, 15000], "alvo": [10000, 20000, 0], "fov": 45, "projecao": "perspectiva"}


def test_cena_do_3d_guarda_a_vista_com_nome(tmp_path):
    g, s = _gerente(tmp_path)
    c = L.rota_post(g, s, ["cenas", "nova-3d"], {"nome": "Fachada frontal", "camera": _CAM, "desligadas": ["camada:Telhas"],
                                                  "pintar": "camada", "arestas": False, "planta": True,
                                                  "piso_oculto": ["eixos"], "sol": {"ligado": True, "direcao": 400, "altura": 30}},
                    lambda *a: None)
    assert c["id"] == "fachada-frontal" and c["tipo"] == "3d" and c["nome"] == "Fachada frontal"
    assert c["camera"] == {"posicao": [-20000, -30000, 15000], "alvo": [10000, 20000, 0], "fov": 45, "projecao": "perspectiva"}
    assert c["desligadas"] == ["camada:Telhas"] and c["pintar"] == "camada" and c["arestas"] is False and c["planta"] is True
    assert c["piso_oculto"] == ["eixos"] and c["sol"] == {"ligado": True, "direcao": 40.0, "altura": 30.0}
    assert c["guarda"] == {"camera": True, "camadas": True, "estilo": True} and "foto" not in c
    assert not os.path.exists(os.path.join(g.pasta(s), "cenas", "dados", "fachada-frontal", "foto.jpg"))
    assert [x["id"] for x in L.rota_get(g, s, ["cenas"], {})["cenas"]] == ["fachada-frontal"]


def test_atualizar_a_cena_do_3d_com_a_vista_atual(tmp_path):
    g, s = _gerente(tmp_path)
    i = C.nova_3d(g, s, {"nome": "Interna", "camera": _CAM})["id"]
    cam2 = {"posicao": [0, 0, 5000], "alvo": [0, 1, 0], "fov": 60, "projecao": "ortografica", "zoom": 2.5}
    c = C.rota_post(g, s, [i], {"camera": cam2, "desligadas": [], "guarda": {"estilo": False}, "nome": "Interna — ponte"})
    assert c["camera"]["projecao"] == "ortografica" and c["camera"]["zoom"] == 2.5 and c["camera"]["fov"] == 60
    assert c["guarda"] == {"camera": True, "camadas": True, "estilo": False} and c["nome"] == "Interna — ponte"
    assert C.ler(g, s, i)["camera"]["posicao"] == [0, 0, 5000]


def test_cena_do_3d_sem_camera_ou_com_dado_ruim_nao_fica(tmp_path):
    g, s = _gerente(tmp_path)
    with pytest.raises(C.ErroCena, match="câmera"):
        C.nova_3d(g, s, {"nome": "X"})
    with pytest.raises(C.ErroCena):
        C.nova_3d(g, s, {"nome": "X", "camera": {**_CAM, "alvo": _CAM["posicao"]}})      # olha para o próprio lugar
    with pytest.raises(C.ErroCena):
        C.nova_3d(g, s, {"nome": "X", "camera": _CAM, "pintar": "<script>"})
    with pytest.raises(C.ErroCena):
        C.nova_3d(g, s, {"nome": "X", "camera": {**_CAM, "projecao": "olho-de-peixe"}})
    assert C.listar(g, s)["cenas"] == []
    assert not [d for d in os.listdir(os.path.join(g.pasta(s), "cenas", "dados")) if not d.startswith(".")]


def test_nome_padrao_e_nomes_repetidos(tmp_path):
    g, s = _gerente(tmp_path)
    a = C.nova_3d(g, s, {"camera": _CAM})
    b = C.nova_3d(g, s, {"nome": "Cena 1", "camera": _CAM})
    assert a["nome"] == "Cena 1" and a["id"] == "cena-1" and b["id"] == "cena-1-2"


def test_abas_na_ordem_de_criacao_e_reordenadas(tmp_path):
    g, s = _gerente(tmp_path)
    foto = C.nova(g, s, _foto(tmp_path, tam=(40, 30)))["id"]            # a cena por foto de antes (sem "ordem")
    a = C.nova_3d(g, s, {"nome": "A", "camera": _CAM})["id"]
    b = C.nova_3d(g, s, {"nome": "B", "camera": _CAM})["id"]
    assert [c["id"] for c in C.listar(g, s)["cenas"]] == [foto, a, b]     # a nova vai para o fim
    r = L.rota_post(g, s, ["cenas", "ordem"], {"ids": [b, foto, a]}, lambda *x: None)
    assert [c["id"] for c in r["cenas"]] == [b, foto, a]
    c = C.nova_3d(g, s, {"nome": "C", "camera": _CAM})["id"]
    assert [x["id"] for x in C.listar(g, s)["cenas"]] == [b, foto, a, c]
    assert [x["id"] for x in C.ordenar(g, s, {"ids": [c]})["cenas"]] == [c, b, foto, a]   # as que faltam vão depois
    with pytest.raises(C.ErroCena):
        C.ordenar(g, s, {"ids": "a,b"})


def test_apagar_a_cena_do_3d(tmp_path):
    g, s = _gerente(tmp_path)
    i = C.nova_3d(g, s, {"nome": "Some", "camera": _CAM})["id"]
    assert L.rota_post(g, s, ["cenas", i, "apagar"], {}, lambda *a: None)["cenas"] == []


# ---------------------------------------------------------------- a tela das Cenas (11/11, amostra-4 aprovada)

def test_quadro_e_fundo_da_cena_do_3d(tmp_path):
    g, s = _gerente(tmp_path)
    i = C.nova_3d(g, s, {"nome": "Fachada", "camera": _CAM, "proporcao": "4:3", "fundo": "transparente"})["id"]
    c = C.ler(g, s, i)
    assert c["proporcao"] == "4:3" and c["fundo"] == "transparente"
    assert C.gravar(g, s, i, {"proporcao": "A3", "fundo": "ceu"})["proporcao"] == "A3"
    with pytest.raises(C.ErroCena, match="proporção"):
        C.gravar(g, s, i, {"proporcao": "21:9"})
    with pytest.raises(C.ErroCena, match="fundo"):
        C.gravar(g, s, i, {"fundo": "nuvens"})


def test_miniatura_da_cena(tmp_path):
    g, s = _gerente(tmp_path)
    i = C.nova_3d(g, s, {"nome": "Mini", "camera": _CAM})["id"]
    envio = _foto(tmp_path, "mini.jpg", tam=(1600, 900))
    r = L.rota_post(g, s, ["cenas", i, "miniatura"], envio, lambda *a: None)
    caminho = L.rota_get(g, s, ["cenas", i, "miniatura.jpg"], {})["arquivo"]
    from PIL import Image
    with Image.open(caminho) as im:
        assert max(im.size) == C.MINIATURA_LADO                  # reduzida para a lista
    assert C.ler(g, s, i)["miniatura"] == r["miniatura"] and not os.path.exists(envio["arquivo_local"])


def test_lista_diz_se_a_cena_tem_render_e_a_ordem_nao_grava_isso(tmp_path):
    g, s = _gerente(tmp_path)
    a = C.nova_3d(g, s, {"nome": "Com render", "camera": _CAM})["id"]
    b = C.nova_3d(g, s, {"nome": "Sem render", "camera": _CAM})["id"]
    pasta = os.path.join(g.pasta(s), "cenas")
    with open(os.path.join(pasta, "Cena - Com render (render).jpg"), "wb") as f:
        f.write(b"jpg")
    cenas = {c["id"]: c for c in C.listar(g, s)["cenas"]}
    assert cenas[a].get("render_em") and not cenas[b].get("render_em")
    C.ordenar(g, s, {"ids": [b, a]})
    assert "render_em" not in C._ler(os.path.join(pasta, "dados", a, "cena.json"))    # a situação é da lista, não do arquivo


# ---------------------------------------------------------------- a marca d'água (11/11: B — o logo em cor numa placa)

def _logo_em_faixa(caminho, largura=1772, altura=229):
    """Como o logo.png da Hermes: o nome numa ponta, o símbolo na outra, com transparência em volta."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((82, 68, 564, 145), fill=(53, 67, 76, 255))          # o "HERMES"
    d.rectangle((1621, 68, 1690, 145), fill=(195, 215, 115, 255))    # o símbolo
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    im.save(caminho)


def test_marca_dagua_empresa_do_projeto_e_o_logo_compacto(tmp_path):
    g, s = _gerente(tmp_path)
    _logo_em_faixa(os.path.join(str(tmp_path), "fabrica", "marca", "logo.png"))
    marca_dezn = os.path.join(str(tmp_path), "fabrica", "empresas", "dezn", "marca")
    os.makedirs(marca_dezn)
    with open(os.path.join(marca_dezn, "logo_metalica.svg"), "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 80"><rect width="100" height="80"/></svg>')
    import json as _json
    with open(os.path.join(str(tmp_path), "fabrica", "empresas", "dezn", "empresa.json"), "w", encoding="utf-8") as f:
        _json.dump({"nome_comercial": "DEZN Construtora", "linhas": {"metalica": {"nome_comercial": "DEZN", "logo": "logo_metalica.svg"}}}, f)
    r = L.rota_get(g, s, ["cenas", "marca"], {})
    assert r["padrao"] == "principal" and {e["id"] for e in r["empresas"]} >= {"principal", "dezn"}
    assert next(e for e in r["empresas"] if e["id"] == "dezn")["nome"] == "DEZN"
    # o projeto com a DEZN no carimbo: a marca padrão é a dela
    p = g.ler(s); p["carimbo_pranchas"] = {"empresa": "dezn"}
    with open(os.path.join(g.pasta(s), "projeto.json"), "w", encoding="utf-8") as f:
        _json.dump(p, f)
    assert C.empresa_padrao(g, s) == "dezn"
    # o PNG em faixa sai compacto: o nome e o símbolo juntos (a faixa tinha 1.608 px de largura útil)
    arq = L.rota_get(g, s, ["cenas", "marca", "principal", "cor"], {})["arquivo"]
    from PIL import Image
    with Image.open(arq) as im:
        assert im.size[1] == 78 and im.size[0] < 600                 # 483 + 42 + 70
    assert os.path.dirname(arq) == os.path.join(g.pasta(s), "cenas", "dados") and os.path.basename(arq).startswith(".marca-")
    assert C.listar(g, s)["cenas"] == []                             # o arquivo da marca não vira cena
    assert L.rota_get(g, s, ["cenas", "marca", "dezn", "cor"], {})["arquivo"].endswith("logo_metalica.svg")
    with pytest.raises(C.ErroCena, match="tom"):
        C.arquivo_da_marca(g, s, "principal", "xadrez")
    os.makedirs(os.path.join(str(tmp_path), "fabrica", "empresas", "outra"))       # cadastrada, sem logo
    with pytest.raises(C.ErroCena, match="logo"):
        C.arquivo_da_marca(g, s, "outra", "cor")


def test_marca_da_cena(tmp_path):
    g, s = _gerente(tmp_path)
    i = C.nova_3d(g, s, {"nome": "Marca", "camera": _CAM})["id"]
    assert i == "marca-cena"                                         # "marca" é a rota da marca d'água
    c = C.gravar(g, s, i, {"marca": {"empresa": "dezn", "jeito": "C", "canto": "esq"}})
    assert c["marca"] == {"empresa": "dezn", "jeito": "C", "canto": "esq"}
    assert C.gravar(g, s, i, {"marca": {"empresa": "sem"}})["marca"] == {"empresa": "sem", "jeito": "B", "canto": "dir"}
    with pytest.raises(C.ErroCena):
        C.gravar(g, s, i, {"marca": {"empresa": "../x"}})
    with pytest.raises(C.ErroCena):
        C.gravar(g, s, i, {"marca": {"empresa": "dezn", "jeito": "D"}})
    f = C.nova(g, s, _foto(tmp_path, tam=(40, 30)))["id"]            # a cena da foto também
    assert C.gravar(g, s, f, {"marca": {"empresa": "principal", "jeito": "A"}})["marca"]["jeito"] == "A"


def test_lista_da_marca_diz_quem_tem_logo(tmp_path):
    """verif_cena, 11/11: numa obra sem logo cadastrado a tela pedia o logo a cada prévia (erro 400 no console)."""
    g, s = _gerente(tmp_path)
    assert C.empresas_da_marca(g, s)["empresas"] == [{"id": "principal", "nome": "Empresa principal", "logo": False}]
    _logo_em_faixa(os.path.join(str(tmp_path), "fabrica", "marca", "logo.png"))
    assert C.empresas_da_marca(g, s)["empresas"][0]["logo"] is True
