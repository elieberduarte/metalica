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
    assert C.gravar(g, s, i, {"proporcao": "21:9"})["proporcao"] == "21:9"     # 13/11: o quadro largo das fachadas geradas
    with pytest.raises(C.ErroCena, match="proporção"):
        C.gravar(g, s, i, {"proporcao": "2:1"})
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


def test_pdf_do_exportar_vai_para_a_pasta_cenas(tmp_path):
    """11/11 (amostra-5, o Exportar da tela das Cenas): o PDF com uma página por cena, montado na tela, vai para cenas/ com o
    nome dado pela tela — só o nome (nada de pasta), sempre .pdf, e só PDF de verdade; "pdf" não vira id de cena."""
    g, s = _gerente(tmp_path)

    def enviar(nome, conteudo=b"%PDF-1.4\n%%EOF\n"):
        caminho = os.path.join(str(tmp_path), "envio.pdf")
        with open(caminho, "wb") as f:
            f.write(conteudo)
        return C.rota_post(g, s, ["pdf"], {"arquivo_local": caminho, "nome": nome})
    assert enviar("Cenas - Obra (render).pdf")["nome"] == "Cenas - Obra (render).pdf"
    assert enviar(r"..\..\fora.pdf")["nome"] == "fora.pdf"           # sem sair da pasta
    assert enviar("../x/Cena: a?b")["nome"] == "Cena- a-b.pdf"
    assert sorted(os.listdir(os.path.join(g.pasta(s), "cenas"))) == ["Cena- a-b.pdf", "Cenas - Obra (render).pdf", "fora.pdf"]
    with pytest.raises(C.ErroCena):
        enviar("x.pdf", b"\x89PNG\r\n\x1a\n")                          # não é PDF
    assert C.nova_3d(g, s, {"nome": "PDF", "camera": _CAM})["id"] == "pdf-cena"


def test_video_do_exportar_vai_para_a_pasta_cenas(tmp_path):
    """12/11 (o vídeo passeando pelas cenas, montado na tela): o MP4 vai para cenas/ com o nome dado pela tela — só o nome,
    sempre .mp4, só MP4 de verdade (a caixa ftyp); o de mesmo nome é trocado; "video" não vira id de cena."""
    g, s = _gerente(tmp_path)
    mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomavc1" + b"\x00" * 64

    def enviar(nome, conteudo=mp4):
        caminho = os.path.join(str(tmp_path), "envio.mp4")
        with open(caminho, "wb") as f:
            f.write(conteudo)
        return C.rota_post(g, s, ["video"], {"arquivo_local": caminho, "nome": nome})
    assert enviar("Vídeo - Obra (cenas).mp4")["nome"] == "Vídeo - Obra (cenas).mp4"
    assert enviar("Vídeo - Obra (cenas).mp4", mp4 + b"mais")["nome"] == "Vídeo - Obra (cenas).mp4"   # o de antes trocado
    assert os.path.getsize(os.path.join(g.pasta(s), "cenas", "Vídeo - Obra (cenas).mp4")) == len(mp4) + 4
    assert enviar(r"..\..\fora")["nome"] == "fora.mp4"
    with pytest.raises(C.ErroCena):
        enviar("x.mp4", b"%PDF-1.4\n%%EOF\n")                         # não é MP4
    assert not os.path.exists(os.path.join(str(tmp_path), "envio.mp4"))  # o recusado não fica no disco
    with pytest.raises(C.ErroCena):
        C.rota_post(g, "nao-existe", ["video"], {"arquivo_local": "x", "nome": "a.mp4"})
    assert C.nova_3d(g, s, {"nome": "Video", "camera": _CAM})["id"] == "video-cena"


def test_sombra_nos_cantos_da_cena(tmp_path):
    """12/11 (amostra-15 aprovada: "médio" como padrão, um seletor no Estilo): o nível da sombra suave nos cantos gravado na
    cena do 3D (sem o campo = médio, decidido na tela); só os 4 níveis; vai na cena nova e no Copiar ajustes › Estilo."""
    g, s = _gerente(tmp_path)
    a = C.nova_3d(g, s, {"nome": "A", "camera": _CAM})
    assert "cantos" not in a                                            # o padrão (médio) é da tela
    b = C.nova_3d(g, s, {"nome": "B", "camera": _CAM, "cantos": "forte"})
    assert b["cantos"] == "forte"
    for nivel in ("sem", "suave", "medio", "forte"):
        assert C.rota_post(g, s, [a["id"]], {"cantos": nivel})["cantos"] == nivel
    with pytest.raises(C.ErroCena):
        C.rota_post(g, s, [a["id"]], {"cantos": "muito"})
    with pytest.raises(C.ErroCena):
        C.nova_3d(g, s, {"nome": "C", "camera": _CAM, "cantos": 3})
    assert C.ler(g, s, a["id"])["cantos"] == "forte"                    # o recusado não mudou nada
    C.rota_post(g, s, [b["id"]], {"cantos": "suave"})
    C.rota_post(g, s, ["copiar"], {"de": b["id"], "para": [a["id"]], "grupos": ["estilo"]})
    assert C.ler(g, s, a["id"])["cantos"] == "suave"


def _mp4(segundos, escala=1000, versao=0):
    """Um MP4 mínimo como o do vídeo das cenas: ftyp, mdat e a moov no fim, com a mvhd (a duração)."""
    import struct

    def caixa(tipo, corpo):
        return struct.pack(">I", 8 + len(corpo)) + tipo + corpo
    if versao == 1:
        mvhd = bytes([1, 0, 0, 0]) + struct.pack(">QQIQ", 0, 0, escala, int(segundos * escala))
    else:
        mvhd = bytes(4) + struct.pack(">IIII", 0, 0, escala, int(segundos * escala))
    return (caixa(b"ftyp", b"isom\x00\x00\x02\x00isomavc1") + caixa(b"mdat", b"\x00" * 5000)
            + caixa(b"moov", caixa(b"mvhd", mvhd + bytes(80))))


def test_videos_gravados_para_assistir_na_tela(tmp_path):
    """12/11 (usuário: "quero assistir dentro do sistema" — antes só tocava o recém-gravado, na janela do Exportar): a lista
    dos MP4 da pasta cenas/ (o mais novo primeiro, com a duração lida da mvhd) e a rota que entrega um deles para o player —
    só um nome .mp4 de dentro da pasta; "videos" não vira id de cena."""
    g, s = _gerente(tmp_path)
    assert L.rota_get(g, s, ["cenas", "videos"], {}) == {"videos": []}          # sem a pasta cenas/ ainda
    pasta = os.path.join(g.pasta(s), "cenas")
    os.makedirs(pasta)
    for nome, seg, versao, hora in (("Vídeo - Obra (cenas).mp4", 36.033, 0, 1000), ("Antigo.MP4", 75, 1, 500)):
        p = os.path.join(pasta, nome)
        with open(p, "wb") as f:
            f.write(_mp4(seg, versao=versao))
        os.utime(p, (1_700_000_000 + hora, 1_700_000_000 + hora))
    with open(os.path.join(pasta, "Cena - Fachada (render).jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff")
    with open(os.path.join(pasta, "estragado.mp4"), "wb") as f:          # não é MP4: entra sem a duração
        f.write(b"nada")
    os.utime(os.path.join(pasta, "estragado.mp4"), (1_600_000_000, 1_600_000_000))
    v = L.rota_get(g, s, ["cenas", "videos"], {})["videos"]
    assert [x["nome"] for x in v] == ["Vídeo - Obra (cenas).mp4", "Antigo.MP4", "estragado.mp4"]
    assert abs(v[0]["segundos"] - 36.033) < 1e-6 and v[1]["segundos"] == 75 and v[2]["segundos"] is None
    assert v[0]["bytes"] == len(_mp4(36.033)) and v[0]["em"].startswith("2023-11-")
    arq = L.rota_get(g, s, ["cenas", "videos", "Vídeo - Obra (cenas).mp4"], {})["arquivo"]
    assert os.path.samefile(arq, os.path.join(pasta, "Vídeo - Obra (cenas).mp4"))
    for ruim in ("..\\..\\projeto.json", "../projeto.json", "Cena - Fachada (render).jpg", ".escondido.mp4", "sumiu.mp4", ""):
        with pytest.raises(C.ErroCena):
            L.rota_get(g, s, ["cenas", "videos", ruim], {})
    with pytest.raises(C.ErroCena):
        C.listar_videos(g, "nao-existe")
    assert C.nova_3d(g, s, {"nome": "Videos", "camera": _CAM})["id"] == "videos-cena"


def test_mostrar_o_render_na_pasta(tmp_path, monkeypatch):
    """11/11 ("preciso que os render feito tenha um acesso rápido a pasta para encontrar o arquivo"): …/cenas/mostrar abre a
    pasta cenas/ com o arquivo selecionado — só de dentro dela; a lista diz qual é o render da cena (o do cartão)."""
    from PIL import Image
    g, s = _gerente(tmp_path)
    abertos = []
    monkeypatch.setattr(C, "_abrir_no_explorador", lambda pasta, arquivo=None: abertos.append((pasta, arquivo)))
    i = C.nova(g, s, _foto(tmp_path))["id"]
    caminho = os.path.join(str(tmp_path), "envio-render.jpg")
    Image.new("RGB", (20, 10)).save(caminho, "JPEG")
    nome = C.rota_post(g, s, [i, "imagem"], {"arquivo_local": caminho, "nome": "render.jpg"})["nome"]
    pasta = os.path.join(g.pasta(s), "cenas")
    assert C.listar(g, s)["cenas"][0]["render_arquivo"] == nome
    C.rota_post(g, s, ["mostrar"], {"nome": nome})
    C.rota_post(g, s, ["mostrar"], {})
    C.rota_post(g, s, ["mostrar"], {"nome": "../../projeto.json"})       # fora da pasta: só a pasta
    C.rota_post(g, s, ["mostrar"], {"nome": "nao-existe.jpg"})
    assert abertos == [(pasta, os.path.join(pasta, nome)), (pasta, None), (pasta, None), (pasta, None)]
    assert C.nova_3d(g, s, {"nome": "Mostrar", "camera": _CAM})["id"] == "mostrar-cena"
    # o projeto que não existe: recusa, sem criar a pasta dele nem abrir o Explorador (11/11, achado na sondagem do dev)
    with pytest.raises(C.ErroCena):
        C.rota_post(g, s.replace(s, "nao-existe"), ["mostrar"], {})
    assert not os.path.exists(os.path.join(str(tmp_path), "nao-existe")) and len(abertos) == 4


def test_ambientes_e_luzes_da_noite(tmp_path):
    """11/11 (amostra-6 aprovada: os 6 ambientes; as luzes de noite automáticas + ajuste): o fundo da cena do 3D pode ser um
    ambiente, e as luzes (refletores, interna, a força 0–3 e a cor) ficam na cena; null tira."""
    g, s = _gerente(tmp_path)
    i = C.nova_3d(g, s, {"nome": "Noite", "camera": _CAM, "fundo": "noite",
                         "luzes": {"refletores": True, "interna": False, "forca_ref": 9, "forca_int": -1, "cor": "branca"}})["id"]
    c = C.ler(g, s, i)
    assert c["fundo"] == "noite"
    assert c["luzes"] == {"refletores": True, "interna": False, "forca_ref": 3.0, "forca_int": 0.0, "cor": "branca"}
    for f in ("ceu", "entardecer", "nublado", "estudio", "noite-azul", "noite"):
        assert C.gravar(g, s, i, {"fundo": f})["fundo"] == f
    with pytest.raises(C.ErroCena, match="luzes"):
        C.gravar(g, s, i, {"luzes": {"cor": "verde"}})
    assert "luzes" not in C.gravar(g, s, i, {"luzes": None})


def test_copiar_ajustes_para_outras_cenas(tmp_path):
    """11/11 ("quando ajusto as configurações em uma cena poderia… ter a opção de copiar de uma cena para (sol, terreno...)"):
    os grupos marcados vão da cena de origem para as escolhidas; o que a origem não tem sai do destino; na cena da foto só o
    que ela tem (sol, camadas, marca); a vista (posição) de cada uma fica."""
    g, s = _gerente(tmp_path)
    a = C.nova_3d(g, s, {"nome": "A", "camera": {**_CAM, "fov": 30}, "fundo": "noite", "proporcao": "4:3", "pintar": "sistema",
                         "luzes": {"cor": "branca"}, "sol": {"direcao": 120, "altura": 40}, "desligadas": ["camada:Fechamento"]})["id"]
    b = C.nova_3d(g, s, {"nome": "B", "camera": _CAM, "fundo": "ceu", "marca": {"empresa": "sem"}})["id"]
    f = C.nova(g, s, _foto(tmp_path))["id"]
    r = C.rota_post(g, s, ["copiar"], {"de": a, "para": [b, f, a], "grupos": ["sol", "ambiente", "marca", "enquadramento"]})
    assert r["copiadas"] == [b, f]
    cb, cf = C.ler(g, s, b), C.ler(g, s, f)
    assert cb["sol"]["direcao"] == 120 and cb["fundo"] == "noite" and cb["luzes"]["cor"] == "branca"
    assert "marca" not in cb                                   # A não tem marca (o padrão): B volta ao padrão
    assert cb["proporcao"] == "4:3" and cb["camera"]["fov"] == 30 and cb["camera"]["posicao"] == C.ler(g, s, b)["camera"]["posicao"]
    assert cb.get("pintar") is None and cb.get("desligadas") in (None, [])   # estilo e camadas não foram marcados
    assert cf["sol"]["direcao"] == 120 and "fundo" not in cf and "luzes" not in cf   # a foto: só o que ela tem
    C.rota_post(g, s, ["copiar"], {"de": a, "para": [f], "grupos": ["camadas"]})
    assert C.ler(g, s, f)["desligadas"] == ["camada:Fechamento"]
    with pytest.raises(C.ErroCena):
        C.rota_post(g, s, ["copiar"], {"de": a, "para": [], "grupos": ["sol"]})
    with pytest.raises(C.ErroCena):
        C.rota_post(g, s, ["copiar"], {"de": a, "para": ["../x"], "grupos": ["sol"]})


def test_marca_dagua_usa_o_logo_deitado_do_carimbo(tmp_path):
    """12/11 ("gostaria que o logo da DEZN ficasse na mesma configuração da Hermes, com o nome dezn antes e o logo depois"):
    a empresa com o logo do carimbo (o DEZN_logo_metalica_carimbo do manual: o nome e o símbolo à direita) usa ele na marca
    d'água; no fundo escuro, o claro dele; sem o do carimbo, o logo de sempre."""
    import json as _json
    g, s = _gerente(tmp_path)
    marca = os.path.join(str(tmp_path), "fabrica", "empresas", "dezn", "marca")
    os.makedirs(marca)
    for n in ("logo_metalica.svg", "logo_claro_metalica.svg", "logo_carimbo_metalica.svg", "logo_carimbo_claro_metalica.svg"):
        with open(os.path.join(marca, n), "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 30"><rect width="100" height="30"/></svg>')
    linha = {"nome_comercial": "DEZN", "logo": "logo_metalica.svg", "logo_claro": "logo_claro_metalica.svg",
             "logo_carimbo": "logo_carimbo_metalica.svg", "logo_carimbo_claro": "logo_carimbo_claro_metalica.svg"}
    caminho = os.path.join(str(tmp_path), "fabrica", "empresas", "dezn", "empresa.json")
    with open(caminho, "w", encoding="utf-8") as f:
        _json.dump({"nome_comercial": "DEZN Construtora", "linhas": {"metalica": linha}}, f)
    assert C.arquivo_da_marca(g, s, "dezn", "cor").endswith("logo_carimbo_metalica.svg")
    assert C.arquivo_da_marca(g, s, "dezn", "claro").endswith("logo_carimbo_claro_metalica.svg")
    linha = {k: v for k, v in linha.items() if not k.startswith("logo_carimbo")}
    with open(caminho, "w", encoding="utf-8") as f:
        _json.dump({"nome_comercial": "DEZN Construtora", "linhas": {"metalica": linha}}, f)
    assert C.arquivo_da_marca(g, s, "dezn", "cor").endswith("logo_metalica.svg")
    assert C.arquivo_da_marca(g, s, "dezn", "claro").endswith("logo_claro_metalica.svg")


def test_entorno_e_luzes_postas_a_mao(tmp_path):
    """12/11 (amostra-8 aprovada: o entorno — grama, pátio, concreto, terra —, a calçada ajustável, o pátio desenhado, e as
    luzes postas à mão): os campos da cena, os limites, e o Copiar ajustes leva o entorno com o ambiente."""
    g, s = _gerente(tmp_path)
    i = C.nova_3d(g, s, {"nome": "A", "camera": _CAM, "entorno": {"tipo": "patio", "calcada": 40, "patio": [[0, 0], [30000, -20000]]},
                         "luzes": {"mao": [{"tipo": "poste", "p": [1000, -12000, 0], "forca": 9}, {"tipo": "refletor", "p": [0, 0, 5000]}]}})["id"]
    c = C.ler(g, s, i)
    assert c["entorno"] == {"tipo": "patio", "calcada": 15.0, "patio": [[0, 0], [30000, -20000]]}
    assert c["luzes"]["mao"] == [{"tipo": "poste", "p": [1000, -12000, 0], "forca": 3.0}, {"tipo": "refletor", "p": [0, 0, 5000], "forca": 1.0}]
    for ruim in ({"entorno": {"tipo": "neve"}}, {"entorno": {"patio": [[1, 2]]}},
                 {"luzes": {"mao": [{"tipo": "vela", "p": [0, 0, 0]}]}}, {"luzes": {"mao": [{"tipo": "poste", "p": [0, 0, 0]}] * 21}}):
        with pytest.raises(C.ErroCena):
            C.gravar(g, s, i, ruim)
    assert "entorno" not in C.gravar(g, s, i, {"entorno": None})
    C.gravar(g, s, i, {"entorno": {"tipo": "grama"}})
    b = C.nova_3d(g, s, {"nome": "B", "camera": _CAM})["id"]
    C.rota_post(g, s, ["copiar"], {"de": i, "para": [b], "grupos": ["ambiente"]})
    assert C.ler(g, s, b)["entorno"]["tipo"] == "grama" and len(C.ler(g, s, b)["luzes"]["mao"]) == 2


def test_figuras_e_arvores_do_fundo(tmp_path):
    """12/11 (amostra-9 aprovada: pessoas, veículos e árvores postas como as luzes, o estilo por cena, as árvores do fundo em 3
    densidades): os campos da cena, os limites, e o Copiar ajustes › Pessoas, veículos e árvores."""
    g, s = _gerente(tmp_path)
    i = C.nova_3d(g, s, {"nome": "A", "camera": _CAM, "entorno": {"tipo": "grama", "arvores": 2},
                         "figuras": {"estilo": "neutro", "itens": [{"tipo": "pessoa", "p": [1000, -5000, 0], "giro": 400, "semente": 3},
                                                                    {"tipo": "caminhao", "p": [0, -20000.04, 0]}]}})["id"]
    c = C.ler(g, s, i)
    assert c["entorno"]["arvores"] == 2
    assert c["figuras"] == {"estilo": "neutro", "itens": [{"tipo": "pessoa", "p": [1000, -5000, 0], "giro": 40.0, "semente": 3},
                                                          {"tipo": "caminhao", "p": [0, -20000.0, 0], "giro": 0.0, "semente": 1}]}
    for ruim in ({"figuras": {"itens": [{"tipo": "dinossauro", "p": [0, 0, 0]}]}}, {"figuras": {"estilo": "neon"}},
                 {"figuras": {"itens": [{"tipo": "carro", "p": [0, 0, 0]}] * 61}}, {"figuras": {"itens": "pessoa"}},
                 {"figuras": {"itens": [{"tipo": "carro", "p": [0, 0, 0], "semente": True}]}},
                 {"figuras": [1]}, {"entorno": {"tipo": "grama", "arvores": 5}}):
        with pytest.raises(C.ErroCena):
            C.gravar(g, s, i, ruim)
    assert "arvores" not in C.gravar(g, s, i, {"entorno": {"tipo": "grama", "arvores": 0}})["entorno"]
    assert "figuras" not in C.gravar(g, s, i, {"figuras": {"estilo": "auto", "itens": []}})   # nada posto, o padrão: sai
    C.gravar(g, s, i, {"figuras": {"itens": [{"tipo": "araucaria", "p": [0, 30000, 0], "semente": 7}]}})
    b = C.nova_3d(g, s, {"nome": "B", "camera": _CAM})["id"]
    C.rota_post(g, s, ["copiar"], {"de": i, "para": [b], "grupos": ["figuras"]})
    assert [f["tipo"] for f in C.ler(g, s, b)["figuras"]["itens"]] == ["araucaria"]
    C.gravar(g, s, i, {"figuras": None})
    C.rota_post(g, s, ["copiar"], {"de": i, "para": [b], "grupos": ["figuras"]})   # a origem sem figuras: o destino fica igual
    assert "figuras" not in C.ler(g, s, b)


def test_a_lista_nao_perde_a_cena_que_esta_sendo_gravada(tmp_path):
    """12/11 (verif_ambientes_cenas: a lista veio sem a cena "fachada" no meio das gravações): ler a lista enquanto a cena é
    gravada (o arquivo trocado no Windows) não pode deixar a cena de fora."""
    import threading
    g, s = _gerente(tmp_path)
    i = C.nova_3d(g, s, {"nome": "Fachada", "camera": _CAM})["id"]
    parar = threading.Event()

    erros = []

    def gravar_sem_parar():
        k = 0
        while not parar.is_set():
            try:
                C.gravar(g, s, i, {"luzes": {"forca_ref": (k % 30) / 10}}); k += 1
            except Exception as e:                       # noqa: BLE001 — a gravação negada ("Acesso negado") é o defeito
                erros.append(repr(e)); return
    t = threading.Thread(target=gravar_sem_parar)
    t.start()
    try:
        faltou = sum(1 for _ in range(400) if [c["id"] for c in C.listar(g, s)["cenas"]] != [i])
    finally:
        parar.set(); t.join()
    assert faltou == 0 and not erros, (faltou, erros[:1])
