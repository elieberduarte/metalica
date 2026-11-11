# -*- coding: utf-8 -*-
"""As cenas: a estrutura encaixada numa foto do local, para apresentação (usuário, 26/10: "quando tenho uma foto precisava
criar uma opção de conseguir colocar a estrutura na foto… uma ferramenta nova 'criar cena', para poder encaixar certinho
o 3D na imagem; isso seria só para apresentação, não precisa ser gerado automaticamente com o projeto").

A imagem pronta (a foto com o 3D) vai para <projeto>/cenas/ (usuário, 26/10: "essas cenas devem ir para uma pasta… uma
nova chamada cenas, dentro da pasta da obra… isso vai valer para as próximas também"); a aba Arquivos a mostra. Os dados de
cada cena ficam em <projeto>/cenas/dados/<id>/: a foto (foto.jpg, até FOTO_LADO_MAX) e cena.json — o nome, os pares de
pontos (o ponto da foto, de 0 a 1, e o mesmo ponto no modelo, em mm do projeto), a câmera encaixada (posição e giro em mm do
projeto, o ângulo vertical), a opacidade do 3D, as camadas desligadas, a situação da cobertura retrátil, o sol (direção e
altura), o que fica na frente da estrutura (frente: os contornos na foto) e se a cena está pronta (concluida: os pontos
escondidos até "Editar cena"). A conta do
encaixe é da tela (web/visor3d/cena.js); aqui só se guarda.

As cenas do 3D (usuário, 11/11: "não tem a opção de criar cena, não tem uma opção para salvar cena, renderizar, colocar isso
em uma prancha"; aprovado nas amostras de Projeto/BRIEFINGS/imagens/cenas-3d/ — abas no rodapé, como as cenas do
SketchUp): a vista do modo ver guardada com nome, sem foto — `tipo: "3d"`, a câmera {posicao, alvo, fov, projecao}
em mm do projeto, as camadas/sistemas desligados, as partes do piso ocultas, a planta, o Pintar, as arestas e o sol, e
`guarda` (o que a cena aplica ao voltar a ela: camera, camadas, estilo). Ficam na mesma lista das cenas por foto, na
ordem das abas (`ordem`). A tela é web/visor3d/cenas3d.js.

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
FRENTE_MAX = 30                            # contornos do que fica na frente da estrutura, por cena
#: o quadro da imagem da cena do 3D (largura ÷ altura; "livre" = o palco inteiro) e o fundo (11/11, a tela das Cenas)
PROPORCOES = {"16:9": 16 / 9, "4:3": 4 / 3, "3:4": 3 / 4, "A3": 420 / 297, "livre": None}
FUNDOS = ("ceu", "branco", "transparente", "terreno",
          # os ambientes (11/11, amostra-6 aprovada): o céu, o chão e a luz juntos; "ceu" é o Dia
          "entardecer", "nublado", "estudio", "noite-azul", "noite")
#: as luzes de noite da cena (amostra-6: automáticas + ajuste): refletores em volta e a luz interna, a força e a cor
CORES_LUZ = ("quente", "branca")
MINIATURA_LADO = 480                       # px: a miniatura da lista das cenas


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
                c.update(_imagens_prontas(g, s, c))
                cenas.append(c)
    cenas.sort(key=lambda c: (_ordem(c), c.get("criada") or ""))
    return {"cenas": cenas}


def _nome_arquivo(c: dict) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", c.get("nome") or c.get("id") or "").strip() or c.get("id") or "cena"


def _imagens_prontas(g, s: str, c: dict) -> dict:
    """A situação das imagens da cena na lista da tela das Cenas: a hora do render (render_em) e da imagem salva
    (imagem_em), se existem na pasta cenas/ — o render mais velho que a cena é um "render velho" na tela."""
    out = {}
    raiz = os.path.join(g.pasta(s), PASTA)
    base = "Cena - " + _nome_arquivo(c)
    for chave, nomes in (("render_em", [base + " (render).jpg", base + " (render).png"]), ("imagem_em", [base + ".png", base + ".jpg"])):
        tempos = [(os.path.getmtime(os.path.join(raiz, n)), n) for n in nomes if os.path.isfile(os.path.join(raiz, n))]
        if tempos:
            t, n = max(tempos)
            out[chave] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t))
            out[chave.replace("_em", "_arquivo")] = n            # o "Mostrar na pasta" do cartão seleciona este
    return out


def _abrir_no_explorador(pasta: str, arquivo: Optional[str] = None) -> None:
    """Abre a pasta no Explorador (o servidor é local) com o arquivo já selecionado, quando há um."""
    import subprocess
    import sys
    if os.name == "nt":
        if arquivo:
            subprocess.Popen('explorer /select,"%s"' % os.path.normpath(arquivo))
        else:
            os.startfile(pasta)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", arquivo] if arquivo else ["open", pasta])
    else:
        subprocess.Popen(["xdg-open", pasta])


def mostrar_na_pasta(g, s: str, corpo: dict) -> dict:
    """O acesso rápido ao render (usuário, 11/11: "preciso que os render feito tenha um acesso rápido a pasta para encontrar o
    arquivo"): abre a pasta cenas/ da obra no Explorador com o arquivo pedido selecionado — só um nome de arquivo de dentro
    dela; sem nome (ou o arquivo já não está lá), a pasta."""
    if not os.path.isdir(g.pasta(s)):                       # projeto que não existe: nada de criar a pasta dele
        raise ErroCena("projeto não encontrado: %s" % s)
    pasta = os.path.join(g.pasta(s), PASTA)
    os.makedirs(pasta, exist_ok=True)
    nome = os.path.basename(str(corpo.get("nome") or "").replace("\\", "/"))
    arquivo = os.path.join(pasta, nome) if nome and not nome.startswith(".") else None
    if arquivo and not os.path.isfile(arquivo):
        arquivo = None
    _abrir_no_explorador(pasta, arquivo)
    return {"pasta": pasta, "arquivo": arquivo}


# ------------------------------------------------------------------ a marca d'água (11/11, aprovada: B — o logo em cor numa
# placa branca translúcida no canto de baixo; a empresa do projeto, a mesma do carimbo das pranchas, sem = Hermes; trocável
# por cena — Hermes/DEZN/sem, A logo claro solto / B placa / C faixa com o nome da obra; sai em toda imagem exportada)

JEITOS_MARCA = ("A", "B", "C")
CANTOS_MARCA = ("dir", "esq")


def empresa_padrao(g, s: str) -> str:
    try:
        return str(((g.ler(s) or {}).get("carimbo_pranchas") or {}).get("empresa") or "principal")
    except (OSError, ValueError, KeyError):
        return "principal"


def empresas_da_marca(g, s: str) -> dict:
    from saida import comercial
    try:
        lista = comercial.listar_empresas(g.raiz)
    except OSError:
        lista = []
    out = []
    for e in lista:
        nome, logo = e.get("nome") or e["id"], False
        try:                                                # a DEZN assina "DEZN" na metálica (a linha de serviço)
            el = comercial.empresa_da_linha(comercial.ler_empresa(g.raiz, e["id"]), "metalica")
            nome = el.get("nome_comercial") or nome
            logo = any(el.get(k) and os.path.isfile(el[k]) for k in ("logo", "logo_claro"))
        except (OSError, ValueError):
            pass
        # sem logo, a tela nem pede (cada pedido sem logo era um erro 400 no console — verif_cena, 11/11)
        out.append({"id": e["id"], "nome": re.sub(r"\s+(Ltda\.?|S/?A|Construtora)$", "", nome, flags=re.I), "logo": logo})
    return {"padrao": empresa_padrao(g, s), "empresas": out}


def _compactar_faixa(origem: str, destino: str) -> None:
    """O logo em faixa de papel timbrado (o da Hermes: o nome numa ponta, o símbolo na outra) com os dois juntos, como no
    carimbo: os vãos sem tinta maiores que a altura do logo viram meio logo de altura."""
    from PIL import Image
    with Image.open(origem) as im:
        im = im.convert("RGBA")
        caixa = im.getchannel("A").getbbox()
        if not caixa:
            im.save(destino); return
        im = im.crop(caixa)
        alfa, (w, h) = im.getchannel("A"), im.size
        tinta = [alfa.crop((x, 0, x + 1, h)).getbbox() is not None for x in range(w)]
        blocos, ini = [], None
        for x, t in enumerate(tinta + [False]):
            if t and ini is None: ini = x
            if not t and ini is not None: blocos.append([ini, x]); ini = None
        juntos = [blocos[0]]
        for b in blocos[1:]:
            if b[0] - juntos[-1][1] <= h: juntos[-1][1] = b[1]
            else: juntos.append(b)
        vao = int(h * 0.55)
        larg = sum(b - a for a, b in juntos) + vao * (len(juntos) - 1)
        out, x = Image.new("RGBA", (larg, h), (0, 0, 0, 0)), 0
        for a, b in juntos:
            out.paste(im.crop((a, 0, b, h)), (x, 0)); x += b - a + vao
        out.save(destino)


def arquivo_da_marca(g, s: str, empresa: str, tom: str) -> str:
    """O logo da empresa para a marca d'água: "cor" (o logo) ou "claro" (o logo claro), da linha metálica quando ela tem.
    PNG em faixa → compacto (guardado em cenas/dados/.marca-… da obra, pela data do arquivo: o servidor só entrega o que
    está na pasta de dados)."""
    from saida import comercial
    if tom not in ("cor", "claro"):
        raise ErroCena("tom da marca desconhecido: %s" % tom)
    try:
        e = comercial.empresa_da_linha(comercial.ler_empresa(g.raiz, empresa), "metalica")
    except ValueError as err:
        raise ErroCena(str(err))
    arq = (e.get("logo_claro") if tom == "claro" else None) or e.get("logo") or ""
    if not arq or not os.path.isfile(arq):
        raise ErroCena("a empresa não tem logo cadastrado (Comercial › Empresa).")
    if not arq.lower().endswith(".png"):
        return arq
    pasta = _pasta(g, s)
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, ".marca-%s-%s-%d.png" % (re.sub(r"[^a-z0-9_-]", "", empresa), tom, int(os.path.getmtime(arq))))
    if not os.path.isfile(destino):
        _compactar_faixa(arq, destino)
    return destino


def gravar_miniatura(g, s: str, i: str, corpo: dict) -> dict:
    """A miniatura da cena para a lista da tela (a imagem pequena feita na tela), em cenas/dados/<id>/miniatura.jpg."""
    origem = corpo.get("arquivo_local")
    if not origem or not os.path.isfile(origem):
        raise ErroCena("nenhuma imagem recebida.")
    from PIL import Image
    try:
        with _TRAVA:
            c = ler(g, s, i)
            with Image.open(origem) as im:
                im = im.convert("RGB")
                im.thumbnail((MINIATURA_LADO, MINIATURA_LADO))
                im.save(os.path.join(_pasta(g, s), i, "miniatura.jpg"), "JPEG", quality=85)
            c["miniatura"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _gravar(os.path.join(_pasta(g, s), i, "cena.json"), c)
    except OSError as e:
        raise ErroCena("a miniatura não abriu (%s)." % e)
    finally:
        try:
            os.remove(origem)
        except OSError:
            pass
    return {"miniatura": c["miniatura"]}


def _ordem(c: dict) -> float:
    """A ordem das abas: a gravada (`ordem`) ou, na cena de antes dela, a hora de criação — a cena nova vai para o fim."""
    o = c.get("ordem")
    if isinstance(o, (int, float)) and o == o:
        return float(o)
    try:
        return time.mktime(time.strptime(c.get("criada") or "", "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return 0.0


def _proxima_ordem(g, s: str) -> float:
    return max([_ordem(c) for c in listar(g, s)["cenas"]] or [-1.0]) + 1


def ordenar(g, s: str, corpo: dict) -> dict:
    """A ordem das abas (arrastar ou "mover para a esquerda/direita"): `ids` na ordem nova; as que faltarem vão depois."""
    ids = corpo.get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ErroCena("dados da cena inválidos.")
    with _TRAVA:
        todas = listar(g, s)["cenas"]
        pos = {i: k for k, i in enumerate(ids)}
        todas.sort(key=lambda c: (pos.get(c["id"], len(ids)), _ordem(c)))
        pasta = _pasta(g, s)
        for k, c in enumerate(todas):
            if c.get("ordem") != k:
                c = _ler(os.path.join(pasta, c["id"], "cena.json")) or c     # a do disco (a lista traz render_em…)
                c["ordem"] = k
                _gravar(os.path.join(pasta, c["id"], "cena.json"), c)
    return listar(g, s)


def ler(g, s: str, i: str) -> dict:
    with _TRAVA:
        c = _ler(os.path.join(_pasta(g, s), _id_valido(i), "cena.json"))
    if not c:
        raise ErroCena("cena desconhecida: %s" % i)
    return c


def _novo_id(pasta: str, nome: str) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:30] or "cena"
    if base in ("marca", "nova", "nova-3d", "ordem", "pdf", "mostrar", "copiar"):   # os nomes das rotas (…/cenas/marca etc.)
        base += "-cena"
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


def nova_3d(g, s: str, corpo: dict) -> dict:
    """A cena do 3D: a vista atual do modo ver com nome (sem foto). A câmera é obrigatória; o resto, o que vier."""
    if not isinstance(corpo.get("camera"), dict):
        raise ErroCena("a cena do 3D precisa da câmera.")
    with _TRAVA:
        pasta = _pasta(g, s)
        os.makedirs(pasta, exist_ok=True)
        n = len(listar(g, s)["cenas"]) + 1
        nome = str(corpo.get("nome") or "").strip()[:80] or "Cena %d" % n
        i = _novo_id(pasta, nome)
        agora = time.strftime("%Y-%m-%dT%H:%M:%S")
        c = {"id": i, "tipo": "3d", "nome": nome, "ordem": _proxima_ordem(g, s), "criada": agora, "alterada": agora,
             "guarda": {"camera": True, "camadas": True, "estilo": True}}
        os.makedirs(os.path.join(pasta, i))
        try:
            _gravar(os.path.join(pasta, i, "cena.json"), c)
            return _gravar_campos(g, s, i, {k: v for k, v in corpo.items() if k != "nome"})
        except ErroCena:
            import shutil                                      # dado inválido: a cena não fica pela metade
            shutil.rmtree(os.path.join(pasta, i), ignore_errors=True)
            raise


def _camera_3d(cam) -> dict:
    """A câmera da cena do 3D em mm do projeto: posição, alvo, ângulo vertical, perspectiva ou ortogonal (e o zoom dela)."""
    if not isinstance(cam, dict):
        raise ErroCena("dados da cena inválidos.")
    pos, alvo = _numeros(cam.get("posicao"), 3), _numeros(cam.get("alvo"), 3)
    if sum((a - b) ** 2 for a, b in zip(pos, alvo)) < 1.0:
        raise ErroCena("a câmera da cena olha para o próprio lugar.")
    projecao = cam.get("projecao") or "perspectiva"
    if projecao not in ("perspectiva", "ortografica"):
        raise ErroCena("projeção desconhecida: %s" % projecao)
    out = {"posicao": [round(x, 1) for x in pos], "alvo": [round(x, 1) for x in alvo], "projecao": projecao,
           "fov": round(min(170.0, max(1.0, _numeros([cam.get("fov", 45.0)], 1)[0])), 2)}
    if cam.get("zoom") is not None:
        out["zoom"] = max(1e-6, _numeros([cam.get("zoom")], 1)[0])
    return out


def _lista_de_textos(v, n_max=500) -> list:
    if not isinstance(v, list) or len(v) > n_max or not all(isinstance(x, str) and len(x) <= 200 for x in v):
        raise ErroCena("dados da cena inválidos.")
    return sorted(set(v))


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
    tres_d = c.get("tipo") == "3d"
    if "camera" in corpo and tres_d:
        c["camera"] = _camera_3d(corpo["camera"])
    elif "camera" in corpo:
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
        c["desligadas"] = _lista_de_textos(corpo["desligadas"] or [])
    # o estilo da cena do 3D (11/11): o Pintar do modo ver, as arestas, a planta no chão e as partes dela ocultas, e o que
    # a cena aplica ao voltar a ela
    if tres_d:
        if "pintar" in corpo:
            p = corpo["pintar"]
            if p is not None and not (isinstance(p, str) and re.fullmatch(r"[a-z_]{1,30}", p)):
                raise ErroCena("dados da cena inválidos.")
            c["pintar"] = p
        for chave in ("arestas", "planta"):
            if chave in corpo:
                if not isinstance(corpo[chave], bool):
                    raise ErroCena("dados da cena inválidos.")
                c[chave] = corpo[chave]
        if "piso_oculto" in corpo:
            c["piso_oculto"] = _lista_de_textos(corpo["piso_oculto"] or [], 50)
        # a tela das Cenas (11/11, amostra-4 aprovada): o quadro da imagem e o fundo
        if "proporcao" in corpo:
            if corpo["proporcao"] not in PROPORCOES:
                raise ErroCena("proporção desconhecida: %s" % corpo["proporcao"])
            c["proporcao"] = corpo["proporcao"]
        if "fundo" in corpo:
            if corpo["fundo"] not in FUNDOS:
                raise ErroCena("fundo desconhecido: %s" % corpo["fundo"])
            c["fundo"] = corpo["fundo"]
        if "luzes" in corpo:
            lz = corpo["luzes"]
            if lz is None:
                c.pop("luzes", None)
            else:
                if not isinstance(lz, dict) or lz.get("cor", "quente") not in CORES_LUZ:
                    raise ErroCena("dados das luzes inválidos.")
                c["luzes"] = {"refletores": lz.get("refletores", True) is not False, "interna": lz.get("interna", True) is not False,
                              "forca_ref": min(3.0, max(0.0, _numeros([lz.get("forca_ref", 1)], 1)[0])),
                              "forca_int": min(3.0, max(0.0, _numeros([lz.get("forca_int", 1)], 1)[0])),
                              "cor": lz.get("cor", "quente")}
        if "guarda" in corpo:
            gd = corpo["guarda"]
            if not isinstance(gd, dict) or not all(k in ("camera", "camadas", "estilo") and isinstance(v, bool) for k, v in gd.items()):
                raise ErroCena("dados da cena inválidos.")
            c["guarda"] = {**c.get("guarda", {}), **gd}
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
    # o que fica na frente da estrutura (usuário, 27/10: "nessa foto por exemplo a estrutura está atrás desse alambrado, como
    # fazer para o sistema entender isso… apenas no renderizar"): os contornos clicados na foto (pontos de 0 a 1, a borda de
    # baixo no chão) e quanto cada um cobre do que está atrás dele (1 = tela fechada; 0,3 = malha). A parede é da tela.
    if "frente" in corpo:
        frente = corpo["frente"] or []
        if not isinstance(frente, list) or len(frente) > FRENTE_MAX:
            raise ErroCena("dados da cena inválidos.")
        contornos = []
        for f in frente:
            pts = f.get("pontos") if isinstance(f, dict) else None
            if not isinstance(pts, list) or not 3 <= len(pts) <= 400:
                raise ErroCena("um contorno precisa de 3 pontos ou mais.")
            pontos = [[round(min(1.0, max(0.0, u)), 5), round(min(1.0, max(0.0, v)), 5)] for u, v in (_numeros(p, 2) for p in pts)]
            cobre = f.get("cobre", 1.0)
            contornos.append({"pontos": pontos, "cobre": round(min(1.0, max(0.05, _numeros([cobre], 1)[0])), 2)})
        c["frente"] = contornos
    # a cena pronta (usuário, 27/10: "salvar cena após a conclusão, para não ficar aparecendo essas bolinhas… caso seja
    # necessário editar ter um para editar cena, daí elas reaparecem"): a tela esconde os pontos e o encaixe
    if "marca" in corpo:                                    # a marca d'água da cena (as duas: 3D e foto)
        m = corpo["marca"]
        if m is None:
            c.pop("marca", None)
        else:
            if not isinstance(m, dict):
                raise ErroCena("dados da cena inválidos.")
            emp = str(m.get("empresa") or "")
            if emp != "sem" and not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", emp):
                raise ErroCena("empresa da marca inválida: %s" % emp)
            if m.get("jeito", "B") not in JEITOS_MARCA or m.get("canto", "dir") not in CANTOS_MARCA:
                raise ErroCena("dados da marca inválidos.")
            c["marca"] = {"empresa": emp, "jeito": m.get("jeito", "B"), "canto": m.get("canto", "dir")}
    if "concluida" in corpo and not tres_d:
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
    nome = _nome_arquivo(c)
    enviado = str(corpo.get("nome") or "").lower()
    ext = ".jpg" if enviado.endswith((".jpg", ".jpeg")) else ".png"
    destino = os.path.join(pasta, "Cena - %s%s%s" % (nome, " (render)" if enviado.startswith("render") else "", ext))
    os.replace(origem, destino)
    return {"arquivo": destino, "nome": os.path.basename(destino)}


#: Copiar ajustes (usuário, 11/11: "quando ajusto as configurações em uma cena poderia… ter a opção de copiar de uma cena para
#: (sol, terreno...)"): os grupos e os campos de cada um; os marcados com * só existem na cena do 3D
GRUPOS_COPIA = {"sol": ("sol",), "ambiente": ("*fundo", "*luzes"), "camadas": ("desligadas",), "estilo": ("*pintar", "*arestas"),
                "enquadramento": ("*proporcao", "*lente"), "marca": ("marca",)}


def copiar_ajustes(g, s: str, corpo: dict) -> dict:
    """Copia os grupos de ajustes de uma cena (`de`) para outras (`para`). O que a cena de origem não tem (o sol padrão, as
    luzes padrão, a marca padrão) sai da cena de destino também — ela fica igual. Na cena da foto só vale o que ela tem
    (o sol, as camadas, a marca); o resto do 3D fica de fora."""
    de = _id_valido(str(corpo.get("de") or ""))
    para = [_id_valido(str(i)) for i in (corpo.get("para") or []) if str(i) != de]
    grupos = [x for x in (corpo.get("grupos") or []) if x in GRUPOS_COPIA]
    if not para or not grupos:
        raise ErroCena("escolha o que copiar e para quais cenas.")
    copiadas = []
    with _TRAVA:
        src = ler(g, s, de)
        for i in para:
            alvo = ler(g, s, i)
            dele_3d = alvo.get("tipo") == "3d"
            novo, tirar = {}, []
            for grupo in grupos:
                for campo in GRUPOS_COPIA[grupo]:
                    so_3d = campo.startswith("*")
                    campo = campo.lstrip("*")
                    if so_3d and not (dele_3d and src.get("tipo") == "3d"):
                        continue
                    if campo == "lente":
                        fov = (src.get("camera") or {}).get("fov")
                        if fov and alvo.get("camera"):
                            novo["camera"] = {**alvo["camera"], "fov": fov}
                    elif campo in src and src[campo] is not None:
                        novo[campo] = src[campo]
                    else:
                        tirar.append(campo)
            if novo:
                _gravar_campos(g, s, i, novo)
            if tirar:
                arq = os.path.join(_pasta(g, s), i, "cena.json")
                c = _ler(arq) or {}
                for campo in tirar:
                    c.pop(campo, None)
                _gravar(arq, c)
            copiadas.append(i)
    return {"copiadas": copiadas, **listar(g, s)}


def gravar_pdf(g, s: str, corpo: dict) -> dict:
    """O PDF do Exportar da tela das Cenas (11/11, amostra-5: uma página por cena, montado na tela) na pasta cenas/: o nome
    vem da tela ("Cena - <nome> (render).pdf" ou "Cenas - <obra> (render).pdf"), só o nome do arquivo e sempre .pdf."""
    if not os.path.isdir(g.pasta(s)):
        raise ErroCena("projeto não encontrado: %s" % s)
    origem = corpo.get("arquivo_local")
    if not origem or not os.path.isfile(origem):
        raise ErroCena("nenhum PDF recebido.")
    with open(origem, "rb") as f:
        if f.read(5) != b"%PDF-":
            raise ErroCena("o arquivo recebido não é um PDF.")
    nome = os.path.basename(str(corpo.get("nome") or "").replace("\\", "/"))
    nome = re.sub(r'[<>:"|?*\x00-\x1f]+', "-", nome).strip(" .")
    if not nome.lower().endswith(".pdf"):
        nome = (nome or "Cenas (render)") + ".pdf"
    if nome.startswith("."):
        nome = "Cenas" + nome
    pasta = os.path.join(g.pasta(s), PASTA)
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, nome)
    os.replace(origem, destino)
    return {"arquivo": destino, "nome": nome}


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
    if resto == ["marca"]:
        return empresas_da_marca(g, s)
    if len(resto) == 3 and resto[0] == "marca":
        return {"arquivo": arquivo_da_marca(g, s, resto[1], resto[2])}
    i = _id_valido(resto[0])
    if resto[1:] in (["foto.jpg"], ["miniatura.jpg"]):
        return {"arquivo": os.path.join(_pasta(g, s), i, resto[1])}
    if len(resto) == 1:
        return ler(g, s, i)
    raise ErroCena("rota da cena desconhecida: %s" % "/".join(resto))


def rota_post(g, s: str, resto: list, corpo: dict) -> dict:
    """…/terreno/cenas/nova (a foto), …/<id> (grava), …/<id>/imagem (a imagem pronta), …/<id>/apagar."""
    if resto == ["nova"]:
        return nova(g, s, corpo)
    if resto == ["nova-3d"]:
        return nova_3d(g, s, corpo)
    if resto == ["ordem"]:
        return ordenar(g, s, corpo)
    if resto == ["pdf"]:
        return gravar_pdf(g, s, corpo)
    if resto == ["mostrar"]:
        return mostrar_na_pasta(g, s, corpo)
    if resto == ["copiar"]:
        return copiar_ajustes(g, s, corpo)
    if len(resto) == 1:
        return gravar(g, s, _id_valido(resto[0]), corpo)
    if len(resto) == 2 and resto[1] == "imagem":
        return gravar_imagem(g, s, _id_valido(resto[0]), corpo)
    if len(resto) == 2 and resto[1] == "miniatura":
        return gravar_miniatura(g, s, _id_valido(resto[0]), corpo)
    if len(resto) == 2 and resto[1] == "apagar":
        return apagar(g, s, _id_valido(resto[0]))
    raise ErroCena("rota da cena desconhecida: %s" % "/".join(resto))
