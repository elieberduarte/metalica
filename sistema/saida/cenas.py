# -*- coding: utf-8 -*-
"""As cenas: a estrutura encaixada numa foto do local, para apresentação (usuário, 26/10: "quando tenho uma foto precisava
criar uma opção de conseguir colocar a estrutura na foto… uma ferramenta nova 'criar cena', para poder encaixar certinho
o 3D na imagem; isso seria só para apresentação, não precisa ser gerado automaticamente com o projeto").

Cada cena fica em <projeto>/cenas/<id>/: a foto (foto.jpg, como veio, até FOTO_LADO_MAX) e cena.json — o nome, os pares
de pontos (o ponto da foto, de 0 a 1, e o mesmo ponto no modelo, em mm do projeto), a câmera encaixada (posição e giro em
mm do projeto, o ângulo vertical) e a opacidade do 3D. A conta do encaixe é da tela (web/visor3d/cena.js); aqui só se
guarda. A imagem pronta (a foto com o 3D) vai para <projeto>/documentos/ (a regra da aba Arquivos, 15/10).

Rotas, penduradas nas do terreno (saida/local_obra.py, /api/projetos/<s>/terreno/cenas…).
"""
import json
import os
import re
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
    return os.path.join(g.pasta(s), PASTA)


def _id_valido(i: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]{1,40}", i or ""):
        raise ErroCena("cena desconhecida: %s" % i)
    return i


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
            c = _ler(os.path.join(pasta, i, "cena.json"))
            if c:
                cenas.append(c)
    cenas.sort(key=lambda c: c.get("criada") or "")
    return {"cenas": cenas}


def ler(g, s: str, i: str) -> dict:
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
    c["alterada"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _gravar(os.path.join(_pasta(g, s), i, "cena.json"), c)
    return c


def gravar_imagem(g, s: str, i: str, corpo: dict) -> dict:
    """A imagem pronta (PNG, a foto com o 3D, feita na tela) vai para <projeto>/documentos/."""
    c = ler(g, s, i)
    origem = corpo.get("arquivo_local")
    if not origem or not os.path.isfile(origem):
        raise ErroCena("nenhuma imagem recebida.")
    pasta = os.path.join(g.pasta(s), "documentos")
    os.makedirs(pasta, exist_ok=True)
    nome = re.sub(r'[\\/:*?"<>|]+', "-", c.get("nome") or i).strip() or i
    destino = os.path.join(pasta, "Cena - %s.png" % nome)
    os.replace(origem, destino)
    return {"arquivo": destino, "nome": os.path.basename(destino)}


def apagar(g, s: str, i: str) -> dict:
    import shutil
    pasta = os.path.join(_pasta(g, s), _id_valido(i))
    if os.path.isdir(pasta):
        shutil.rmtree(pasta)
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
