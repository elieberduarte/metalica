# -*- coding: utf-8 -*-
"""As cenas: a estrutura encaixada numa foto do local, para apresentação (usuário, 26/10: "quando tenho uma foto precisava
criar uma opção de conseguir colocar a estrutura na foto… uma ferramenta nova 'criar cena', para poder encaixar certinho
o 3D na imagem; isso seria só para apresentação, não precisa ser gerado automaticamente com o projeto").

A imagem pronta (a foto com o 3D) vai para <projeto>/cenas/ (usuário, 26/10: "essas cenas devem ir para uma pasta… uma
nova chamada cenas, dentro da pasta da obra… isso vai valer para as próximas também"); a aba Arquivos a mostra. Os dados de
cada cena ficam em <projeto>/cenas/dados/<id>/: a foto (foto.jpg, até FOTO_LADO_MAX) e cena.json — o nome, os pares de
pontos (o ponto da foto, de 0 a 1, e o mesmo ponto no modelo, em mm do projeto), a câmera encaixada (posição e giro em mm do
projeto, o ângulo vertical), a opacidade do 3D, as camadas desligadas, a situação da cobertura retrátil, o sol (direção e
altura) e se a cena está pronta (concluida: os pontos escondidos até "Editar cena"). A conta do
encaixe é da tela (web/visor3d/cena.js); aqui só se guarda.

Rotas, penduradas nas do terreno (saida/local_obra.py, /api/projetos/<s>/terreno/cenas…).
"""
import json
import os
import re
import threading
import time
import unicodedata
from typing import Optional

from nucleo.base import ErroDeDados

PASTA = "cenas"
FOTO_LADO_MAX = 6000                       # px: a foto do celular (4000 × 3000, 12 Mpx) passa inteira
FOTO_EXT = (".jpg", ".jpeg", ".png")


class ErroCena(ErroDeDados):
    pass


def _pasta(g, s: str) -> str:
    """A pasta dos dados das cenas (<projeto>/cenas/dados); o arranjo de antes (26/10, a 1ª versão: os dados em cenas/<id>
    e a imagem em documentos/) muda para o de agora na primeira vez."""
    raiz = os.path.join(g.pasta(s), PASTA)
    dados = os.path.join(raiz, "dados")
    if os.path.isdir(raiz):
        for i in os.listdir(raiz):
            velho = os.path.join(raiz, i)
            if i != "dados" and os.path.isfile(os.path.join(velho, "cena.json")):
                os.makedirs(dados, exist_ok=True)
                os.replace(velho, os.path.join(dados, i))
            elif i != "dados" and os.path.isdir(velho) and set(os.listdir(velho)) <= {"foto.jpg"}:
                import shutil                                 # a cena apagada pela metade (a 1ª versão do apagar)
                shutil.rmtree(velho, ignore_errors=True)
        docs = os.path.join(g.pasta(s), "documentos")
        if os.path.isdir(docs):
            for nome in os.listdir(docs):
                if nome.startswith("Cena - ") and nome.lower().endswith(".png"):
                    os.replace(os.path.join(docs, nome), os.path.join(raiz, nome))
    return dados


def _id_valido(i: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]{1,40}", i or ""):
        raise ErroCena("cena desconhecida: %s" % i)
    return i


# as rotas rodam cada uma num fio: a tela grava o sol, as camadas, a lente… cada um no seu tempo, e duas gravações da
# mesma cena juntas usavam o mesmo .tmp (uma caía com erro 500), liam o cena.json no meio da troca ("cena desconhecida")
# ou gravavam uma por cima do campo da outra (27/10). Ler, mudar e gravar uma cena é uma coisa só.
_TRAVA = threading.RLock()


def _ler(caminho: str) -> Optional[dict]:
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _gravar(caminho: str, dados: dict) -> None:
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def listar(g, s: str) -> dict:
    pasta, cenas = _pasta(g, s), []
    if os.path.isdir(pasta):
        for i in sorted(os.listdir(pasta)):
            if i.startswith("."):
                continue
            c = _ler(os.path.join(pasta, i, "cena.json"))
            if c:
                cenas.append(c)
    cenas.sort(key=lambda c: c.get("criada") or "")
    return {"cenas": cenas}


def ler(g, s: str, i: str) -> dict:
    with _TRAVA:
        c = _ler(os.path.join(_pasta(g, s), _id_valido(i), "cena.json"))
    if not c:
        raise ErroCena("cena desconhecida: %s" % i)
    return c


def _novo_id(pasta: str, nome: str) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:30] or "cena"
    i, k = base, 2
    while os.path.exists(os.path.join(pasta, i)):
        i, k = "%s-%d" % (base, k), k + 1
    return i


def nova(g, s: str, corpo: dict) -> dict:
    """A foto chega pelo envio binário ({"arquivo_local", "nome"}); o nome da cena é o da foto sem a extensão."""
    origem, nome_arq = corpo.get("arquivo_local"), os.path.basename(str(corpo.get("nome") or "foto.jpg"))
    if not origem or not os.path.isfile(origem):
        raise ErroCena("nenhuma foto recebida.")
    ext = os.path.splitext(nome_arq)[1].lower()
    if ext not in FOTO_EXT:
        os.remove(origem)
        raise ErroCena("a foto precisa ser JPG ou PNG (veio %s)." % (ext or nome_arq))
    from PIL import Image, ImageOps
    try:
        with Image.open(origem) as im:
            im = ImageOps.exif_transpose(im)               # a foto do celular deitado vem com o giro no EXIF
            im = im.convert("RGB")
            if max(im.size) > FOTO_LADO_MAX:
                im.thumbnail((FOTO_LADO_MAX, FOTO_LADO_MAX))
            pasta = _pasta(g, s)
            os.makedirs(pasta, exist_ok=True)
            nome = os.path.splitext(nome_arq)[0][:60] or "Cena"
            i = _novo_id(pasta, nome)
            os.makedirs(os.path.join(pasta, i))
            im.save(os.path.join(pasta, i, "foto.jpg"), "JPEG", quality=92)
            px = list(im.size)
    except OSError as e:
        raise ErroCena("a foto não abriu (%s)." % e)
    finally:
        try:
            os.remove(origem)
        except OSError:
            pass
    agora = time.strftime("%Y-%m-%dT%H:%M:%S")
    c = {"id": i, "nome": nome, "foto": "foto.jpg", "px": px, "pares": [], "camera": None, "opacidade": 1.0,
         "criada": agora, "alterada": agora}
    _gravar(os.path.join(pasta, i, "cena.json"), c)
    return c


def _numeros(v, n: int) -> list:
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise ErroCena("dados da cena inválidos.")
    try:
        out = [float(x) for x in v]
    except (TypeError, ValueError):
        raise ErroCena("dados da cena inválidos.")
    if not all(x == x and abs(x) < 1e12 for x in out):
        raise ErroCena("dados da cena inválidos.")
    return out


def gravar(g, s: str, i: str, corpo: dict) -> dict:
    """Os pares, a câmera, a opacidade e o nome (o que vier)."""
    with _TRAVA:
        return _gravar_campos(g, s, i, corpo)


def _gravar_campos(g, s: str, i: str, corpo: dict) -> dict:
    c = ler(g, s, i)
    if "nome" in corpo:
        c["nome"] = str(corpo["nome"] or c["nome"]).strip()[:80] or c["nome"]
    if "pares" in corpo:
        pares = []
        for p in corpo["pares"] or []:
            if not isinstance(p, dict):
                raise ErroCena("dados da cena inválidos.")
            par = {"foto": _numeros(p.get("foto"), 2)}
            if p.get("modelo") is not None:
                par["modelo"] = _numeros(p.get("modelo"), 3)
            pares.append(par)
        c["pares"] = pares
    if "camera" in corpo:
        cam = corpo["camera"]
        if cam is None:
            c["camera"] = None
        else:
            if not isinstance(cam, dict):
                raise ErroCena("dados da cena inválidos.")
            c["camera"] = {"posicao": _numeros(cam.get("posicao"), 3), "giro": _numeros(cam.get("giro"), 4),
                           "fov": min(170.0, max(1.0, _numeros([cam.get("fov")], 1)[0]))}
            if cam.get("erro_px") is not None:
                c["camera"]["erro_px"] = round(_numeros([cam.get("erro_px")], 1)[0], 2)
    if "opacidade" in corpo:
        c["opacidade"] = min(1.0, max(0.05, _numeros([corpo["opacidade"]], 1)[0]))
    # o que aparece na cena (usuário, 26/10: "essa imagem interagir com as camadas, poder abrir a quadra, colocar e tirar a
    # lona"): as camadas e os sistemas desligados ("camada:<nome>", "sistema:<chave>") e a situação da cobertura retrátil
    if "desligadas" in corpo:
        d = corpo["desligadas"] or []
        if not isinstance(d, list) or len(d) > 500 or not all(isinstance(x, str) and len(x) <= 200 for x in d):
            raise ErroCena("dados da cena inválidos.")
        c["desligadas"] = sorted(set(d))
    if "situacao" in corpo:
        if corpo["situacao"] not in (None, "aberta", "retraida"):
            raise ErroCena("situação da cobertura desconhecida: %s" % corpo["situacao"])
        c["situacao"] = corpo["situacao"]
    # o sol da cena (usuário, 27/10: "ter as opções de mudar a posição das sombras aqui na composição da cena"): ligado ou
    # não, a direção em volta da obra (0–360°, nos eixos do modelo) e a altura acima do horizonte (web/visor3d/sol.js)
    if "sol" in corpo:
        sol = corpo["sol"]
        if not isinstance(sol, dict) or not isinstance(sol.get("ligado", True), bool):
            raise ErroCena("dados da cena inválidos.")
        direcao, altura = _numeros([sol.get("direcao"), sol.get("altura")], 2)
        c["sol"] = {"ligado": sol.get("ligado", True), "direcao": round(direcao % 360.0, 1), "altura": round(min(85.0, max(5.0, altura)), 1)}
        if sol.get("chao") is not None:                     # a força da sombra no chão da foto (0 a 1)
            c["sol"]["chao"] = round(min(1.0, max(0.0, _numeros([sol.get("chao")], 1)[0])), 2)
    # a cena pronta (usuário, 27/10: "salvar cena após a conclusão, para não ficar aparecendo essas bolinhas… caso seja
    # necessário editar ter um para editar cena, daí elas reaparecem"): a tela esconde os pontos e o encaixe
    if "concluida" in corpo:
        if not isinstance(corpo["concluida"], bool):
            raise ErroCena("dados da cena inválidos.")
        if corpo["concluida"] and not c.get("camera"):
            raise ErroCena("encaixe a cena antes de salvar.")
        c["concluida"] = corpo["concluida"]
    c["alterada"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _gravar(os.path.join(_pasta(g, s), i, "cena.json"), c)
    return c


def gravar_imagem(g, s: str, i: str, corpo: dict) -> dict:
    """A imagem pronta (a foto com o 3D, feita na tela) vai para <projeto>/cenas/: "Cena - <nome>.png" pelo Salvar imagem;
    "Cena - <nome> (render).jpg" pelo Renderizar (27/10: "a resolução ainda é meio baixa… uma opção para 'renderizar' a
    imagem") — o envio chamado render.jpg; um não apaga o outro."""
    c = ler(g, s, i)
    origem = corpo.get("arquivo_local")
    if not origem or not os.path.isfile(origem):
        raise ErroCena("nenhuma imagem recebida.")
    pasta = os.path.join(g.pasta(s), PASTA)
    os.makedirs(pasta, exist_ok=True)
    nome = re.sub(r'[\\/:*?"<>|]+', "-", c.get("nome") or i).strip() or i
    enviado = str(corpo.get("nome") or "").lower()
    ext = ".jpg" if enviado.endswith((".jpg", ".jpeg")) else ".png"
    destino = os.path.join(pasta, "Cena - %s%s%s" % (nome, " (render)" if enviado.startswith("render") else "", ext))
    os.replace(origem, destino)
    return {"arquivo": destino, "nome": os.path.basename(destino)}


def apagar(g, s: str, i: str) -> dict:
    """A pasta da cena sai da lista na hora (renomeada para .lixo-…) e é removida; o que o Windows ainda prende (a foto aberta
    pelo OneDrive ou pelo navegador — 26/10, a Kaefer: o apagar parava no meio e a cena ficava pela metade) sai na próxima."""
    with _TRAVA:
        return _apagar(g, s, i)


def _apagar(g, s: str, i: str) -> dict:
    import shutil
    dados = _pasta(g, s)
    pasta = os.path.join(dados, _id_valido(i))
    if os.path.isdir(pasta):
        lixo = os.path.join(dados, ".lixo-%s-%d" % (i, int(time.time() * 1000)))
        try:
            os.replace(pasta, lixo)
        except OSError:
            lixo = pasta
            try:
                os.remove(os.path.join(pasta, "cena.json"))      # sem o cena.json a cena já não aparece
            except OSError as e:
                raise ErroCena("a cena está aberta noutro programa (%s). Feche e tente de novo." % e)
        shutil.rmtree(lixo, ignore_errors=True)
    for velho in os.listdir(dados) if os.path.isdir(dados) else []:
        if velho.startswith(".lixo-"):
            shutil.rmtree(os.path.join(dados, velho), ignore_errors=True)
    return listar(g, s)


def rota_get(g, s: str, resto: list) -> dict:
    """…/terreno/cenas[/<id>[/foto.jpg]]. {"arquivo": caminho} = servir o arquivo."""
    if not resto:
        return listar(g, s)
    i = _id_valido(resto[0])
    if resto[1:] == ["foto.jpg"]:
        return {"arquivo": os.path.join(_pasta(g, s), i, "foto.jpg")}
    if len(resto) == 1:
        return ler(g, s, i)
    raise ErroCena("rota da cena desconhecida: %s" % "/".join(resto))


def rota_post(g, s: str, resto: list, corpo: dict) -> dict:
    """…/terreno/cenas/nova (a foto), …/<id> (grava), …/<id>/imagem (a imagem pronta), …/<id>/apagar."""
    if resto == ["nova"]:
        return nova(g, s, corpo)
    if len(resto) == 1:
        return gravar(g, s, _id_valido(resto[0]), corpo)
    if len(resto) == 2 and resto[1] == "imagem":
        return gravar_imagem(g, s, _id_valido(resto[0]), corpo)
    if len(resto) == 2 and resto[1] == "apagar":
        return apagar(g, s, _id_valido(resto[0]))
    raise ErroCena("rota da cena desconhecida: %s" % "/".join(resto))
