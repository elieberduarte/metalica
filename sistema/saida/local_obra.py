"""A obra no terreno do cliente (20/10/2026, o usuário: "vincular a obra a um mapa para ter o modelo apresentado dentro
do terreno do cliente").

A amarração da obra ao mundo fica no `projeto.json`, em `terreno`:

    {"lat": -24.95, "lon": -53.45,      o ponto de amarração no mundo (graus, WGS 84)
     "ponto": [x, y],                   o mesmo ponto no modelo (mm do projeto)
     "norte": 12.5,                     o azimute do eixo +Y do modelo (graus, horário a partir do norte verdadeiro)
     "endereco": "...", "fonte": "esri" | {"tipo": "wms", "url": ..., "camada": ...}}

e a imagem baixada fica na pasta do projeto, em `terreno/imagem.jpg` com `terreno/imagem.json` (os limites dela em
Web Mercator, EPSG:3857), para o 3D abrir sem internet. A imagem é sempre um quadrado com o norte para cima; o visor
(web/visor3d/terreno.js) a põe no chão girada pelo `norte`, com as mesmas contas daqui.

As fontes do teste são as gratuitas: a busca de endereço pelo OpenStreetMap (Nominatim) e a imagem da Esri World
Imagery, com a atribuição na tela. O Google só pela Map Tiles API (chave e faturamento; não deixa guardar a imagem), e
o geoportal da prefeitura (Cascavel…) por WMS, quando ele publica a ortofoto.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from nucleo.base import ErroDeDados

R_TERRA = 6378137.0                       # o raio do Web Mercator (m)
PIXELS_MAX = 4096                         # o lado da imagem baixada: cabe em toda placa de vídeo
ZOOM_MAX = 19
# a volta do terreno em torno da obra: a vizinhança aparece (a nitidez é a da fonte — a Esri dá ~0,5 m por pixel em
# Cascavel —, e o lado maior não a piora enquanto cabe em PIXELS_MAX)
MARGEM_MIN_M = 150.0
PASTA = "terreno"

FONTES = {
    "esri": {"nome": "Esri World Imagery (gratuita)", "tipo": "xyz", "zoom_max": 19,
             "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
             "atribuicao": "Imagem: Esri, Maxar, Earthstar Geographics e comunidade GIS"},
}
# a fonte falsa dos testes (sem internet): quadriculado com o número de cada bloco
if os.environ.get("METALICA_TERRENO_FALSO") == "1":
    FONTES["teste"] = {"nome": "Teste (sem internet)", "tipo": "teste", "zoom_max": 19, "atribuicao": "Imagem de teste"}

AGENTE = "Metalica/1.0 (estruturas metalicas; suporte.vizin@gmail.com)"   # o Nominatim pede identificação


class ErroTerreno(ErroDeDados):
    pass


# ------------------------------------------------------------------ as contas (as mesmas do terreno.js)

def modelo_para_geo(t: dict, x: float, y: float) -> tuple:
    """O ponto do modelo (mm) em (lat, lon) pela amarração `t`. A obra é pequena perto da Terra: o plano tangente no
    ponto de amarração basta (menos de 1 mm de erro em 1 km)."""
    a = math.radians(float(t.get("norte") or 0.0))
    dx, dy = (x - t["ponto"][0]) / 1000.0, (y - t["ponto"][1]) / 1000.0
    leste = dx * math.cos(a) + dy * math.sin(a)
    norte = -dx * math.sin(a) + dy * math.cos(a)
    lat0 = math.radians(t["lat"])
    return (t["lat"] + math.degrees(norte / R_TERRA), t["lon"] + math.degrees(leste / (R_TERRA * math.cos(lat0))))


def geo_para_modelo(t: dict, lat: float, lon: float) -> tuple:
    a = math.radians(float(t.get("norte") or 0.0))
    lat0 = math.radians(t["lat"])
    norte = math.radians(lat - t["lat"]) * R_TERRA
    leste = math.radians(lon - t["lon"]) * R_TERRA * math.cos(lat0)
    dx = leste * math.cos(a) - norte * math.sin(a)
    dy = leste * math.sin(a) + norte * math.cos(a)
    return (t["ponto"][0] + dx * 1000.0, t["ponto"][1] + dy * 1000.0)


def mercator(lat: float, lon: float) -> tuple:
    return (R_TERRA * math.radians(lon), R_TERRA * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def de_mercator(mx: float, my: float) -> tuple:
    return (math.degrees(2 * math.atan(math.exp(my / R_TERRA)) - math.pi / 2), math.degrees(mx / R_TERRA))


def metros_por_pixel(lat: float, zoom: int) -> float:
    """O tamanho do pixel no chão, no nível `zoom` dos blocos de 256 px."""
    return 2 * math.pi * R_TERRA * math.cos(math.radians(lat)) / (256 * 2 ** zoom)


def regiao(t: dict, caixa: list) -> dict:
    """O quadrado (Web Mercator) da imagem: em volta da obra inteira em qualquer giro (o círculo da caixa em planta) com
    a margem — o Ajustar arrasta e gira sem a obra sair da imagem. `caixa` = [x0, y0, x1, y1] em mm do projeto."""
    x0, y0, x1, y1 = (float(v) for v in caixa)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    raio = math.hypot(x1 - x0, y1 - y0) / 2 / 1000.0
    lado = 2 * (raio + max(MARGEM_MIN_M, raio))            # m no chão
    lat, lon = modelo_para_geo(t, cx, cy)
    k = 1 / math.cos(math.radians(lat))                     # o Mercator estica o chão por 1/cos(lat)
    mx, my = mercator(lat, lon)
    meio = lado * k / 2
    return {"x0": mx - meio, "y0": my - meio, "x1": mx + meio, "y1": my + meio, "lado_m": lado, "lat": lat, "lon": lon}


def zoom_para(lado_m: float, lat: float, zoom_max: int = ZOOM_MAX) -> int:
    """O nível mais fino em que o quadrado cabe em PIXELS_MAX."""
    z = int(math.floor(math.log2(2 * math.pi * R_TERRA * math.cos(math.radians(lat)) * PIXELS_MAX / (256 * lado_m))))
    return max(1, min(z, zoom_max))


# ------------------------------------------------------------------ a amarração no projeto

def validar(t: dict) -> dict:
    if not isinstance(t, dict):
        raise ErroTerreno("dados do terreno inválidos.")
    try:
        lat, lon = float(t["lat"]), float(t["lon"])
        ponto = [float(t["ponto"][0]), float(t["ponto"][1])]
        norte = float(t.get("norte") or 0.0)
    except (KeyError, TypeError, ValueError, IndexError):
        raise ErroTerreno("faltam a latitude, a longitude ou o ponto de amarração.")
    if not (-85 < lat < 85 and -180 <= lon <= 180) or not all(math.isfinite(v) for v in (lat, lon, norte, *ponto)):
        raise ErroTerreno("coordenada fora do mundo: lat %s, lon %s." % (lat, lon))
    norte = (norte + 180.0) % 360.0 - 180.0
    saida = {"lat": round(lat, 8), "lon": round(lon, 8), "ponto": [round(v, 1) for v in ponto], "norte": round(norte, 3)}
    for k in ("endereco",):
        if t.get(k):
            saida[k] = str(t[k])[:300]
    fonte = t.get("fonte") or "esri"
    if isinstance(fonte, dict):
        url, camada = str(fonte.get("url") or "").strip(), str(fonte.get("camada") or "").strip()
        if not re.match(r"^https?://", url) or not camada:
            raise ErroTerreno("a fonte WMS precisa do endereço (http…) e do nome da camada.")
        saida["fonte"] = {"tipo": "wms", "url": url.split("?")[0], "camada": camada,
                          "nome": str(fonte.get("nome") or "WMS")[:80]}
    elif fonte in FONTES:
        saida["fonte"] = fonte
    else:
        raise ErroTerreno("fonte de imagem desconhecida: %s" % fonte)
    if isinstance(t.get("caixa"), list) and len(t["caixa"]) == 4:
        saida["caixa"] = [round(float(v), 1) for v in t["caixa"]]
    return saida


def _meta_imagem(pasta: str) -> Optional[dict]:
    try:
        with open(os.path.join(pasta, PASTA, "imagem.json"), encoding="utf-8") as f:
            m = json.load(f)
        return m if os.path.isfile(os.path.join(pasta, PASTA, "imagem.jpg")) else None
    except (OSError, ValueError):
        return None


def estado(g, s: str) -> dict:
    p = g.ler(s)
    fontes = [{"chave": k, "nome": v["nome"]} for k, v in FONTES.items()]
    return {"terreno": p.get("terreno"), "imagem": _meta_imagem(g.pasta(s)), "fontes": fontes}


def gravar(g, s: str, corpo: dict) -> dict:
    t = validar(corpo or {})
    g.tocar(s, terreno=t)
    return estado(g, s)


# ------------------------------------------------------------------ a busca do endereço

_PONTO = r"[-+]?\d{1,3}(?:\.\d+)?"
_VIRGULA = r"[-+]?\d{1,3},\d+"


def coordenada_do_texto(texto: str) -> Optional[tuple]:
    """A coordenada colada: "-24.95, -53.45" (o botão direito do Google Maps), "-24,95 -53,45" (vírgula decimal) ou o
    link do Google Maps (…/@-24.95,-53.45,17z ou !3d-24.95!4d-53.45). None se o texto não é coordenada."""
    t = str(texto or "").strip()
    m = (re.search(r"!3d(%s)!4d(%s)" % (_PONTO, _PONTO), t) or re.search(r"@(%s),(%s)" % (_PONTO, _PONTO), t)
         or re.fullmatch(r"(%s)\s*[,;\s]\s*(%s)" % (_PONTO, _PONTO), t)
         or re.fullmatch(r"(%s)\s*[;\s]\s*(%s)" % (_VIRGULA, _VIRGULA), t))
    if not m:
        return None
    lat, lon = (float(v.replace(",", ".")) for v in (m.group(1), m.group(2)))
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def _baixar(url: str, tempo: float = 20.0) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept-Language": "pt-BR"})
    with urllib.request.urlopen(pedido, timeout=tempo) as r:
        return r.read()


def buscar_endereco(q: str, baixar: Callable[[str], bytes] = _baixar) -> dict:
    texto = str(q or "").strip()
    if not texto:
        raise ErroTerreno("escreva o endereço ou cole a coordenada.")
    c = coordenada_do_texto(texto)
    if c:
        return {"resultados": [{"nome": "Coordenada %.6f, %.6f" % c, "lat": c[0], "lon": c[1]}]}
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": texto, "format": "jsonv2", "limit": 6, "countrycodes": "br", "accept-language": "pt-BR"})
    try:
        lista = json.loads(baixar(url).decode("utf-8"))
    except (OSError, ValueError) as e:
        raise ErroTerreno("a busca de endereço não respondeu (%s). Confira a internet ou cole a coordenada do Google "
                          "Maps (botão direito no mapa → a primeira linha)." % (getattr(e, "reason", None) or e))
    return {"resultados": [{"nome": r.get("display_name", ""), "lat": float(r["lat"]), "lon": float(r["lon"])}
                           for r in lista if r.get("lat") and r.get("lon")]}


# ------------------------------------------------------------------ a imagem

def _bloco_teste(z: int, x: int, y: int):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (256, 256), (90, 130, 80) if (x + y) % 2 else (150, 160, 110))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 255, 255], outline=(240, 240, 240))
    d.text((10, 10), "%d/%d/%d" % (z, x, y), fill=(255, 255, 255))
    return im


def _vazio(im) -> bool:
    """O bloco "Map data not yet available" da Esri: cinza claro liso (o desvio de cada canal pequeno, os três iguais)."""
    from PIL import ImageStat
    st = ImageStat.Stat(im.convert("RGB"))
    return (max(st.stddev) < 12 and all(185 < m < 225 for m in st.mean) and max(st.mean) - min(st.mean) < 4)


def _bloco(fonte: dict, z: int, x: int, y: int, baixar):
    from PIL import Image
    if fonte["tipo"] == "teste":
        return None if z > fonte.get("zoom_real", 99) else _bloco_teste(z, x, y)
    im = Image.open(io.BytesIO(baixar(fonte["url"].format(z=z, x=x, y=y)))).convert("RGB")
    return None if _vazio(im) else im


def _nivel_com_imagem(fonte: dict, reg: dict, z: int, baixar, minimo: int = 12) -> int:
    """O nível `z` ou o primeiro abaixo em que o bloco do meio da região tem imagem (a Esri não tem o 19 em todo lugar:
    no centro de Cascavel, 20/10, os blocos do 19 vinham "Map data not yet available")."""
    mundo = 2 * math.pi * R_TERRA
    while z > minimo:
        por_px = mundo / (256 * 2 ** z)
        x = int(((reg["x0"] + reg["x1"]) / 2 + mundo / 2) / por_px // 256)
        y = int((mundo / 2 - (reg["y0"] + reg["y1"]) / 2) / por_px // 256)
        try:
            if _bloco(fonte, z, x, y, baixar) is not None:
                return z
        except Exception:
            return z                                          # sem resposta: o download conta a falha
        z -= 1
    return z


def _imagem_xyz(fonte: dict, reg: dict, z: int, baixar, progresso) -> "Image.Image":
    """Os blocos 256 px do nível `z` que cobrem a região, costurados e recortados num quadrado de pixels inteiros; a
    região passa a ser a do recorte (os limites da imagem são os dos pixels, sem o meio pixel do arredondamento)."""
    from PIL import Image
    mundo = 2 * math.pi * R_TERRA
    por_px = mundo / (256 * 2 ** z)
    # pixel global (origem no canto noroeste do mundo)
    lado = max(1, int(round((reg["x1"] - reg["x0"]) / por_px)))
    px0 = int(round((reg["x0"] + mundo / 2) / por_px))
    py0 = int(round((mundo / 2 - reg["y1"]) / por_px))
    px1, py1 = px0 + lado, py0 + lado
    reg.update(x0=px0 * por_px - mundo / 2, x1=px1 * por_px - mundo / 2, y1=mundo / 2 - py0 * por_px, y0=mundo / 2 - py1 * por_px)
    bx0, bx1, by0, by1 = px0 // 256, (px1 - 1) // 256, py0 // 256, (py1 - 1) // 256
    blocos = [(bx, by) for by in range(by0, by1 + 1) for bx in range(bx0, bx1 + 1)]
    tela = Image.new("RGB", ((bx1 - bx0 + 1) * 256, (by1 - by0 + 1) * 256), (128, 128, 128))
    feitos = [0]
    falhas = []

    def um(b):
        bx, by = b
        try:
            im = _bloco(fonte, z, bx, by, baixar)            # o vazio da fonte fica cinza, como o que falha
        except Exception as e:                               # um bloco que falha fica cinza; a imagem sai
            falhas.append(str(e))
            im = None
        feitos[0] += 1
        progresso("baixando a imagem do terreno (%d de %d blocos)" % (feitos[0], len(blocos)), 0.05 + 0.85 * feitos[0] / len(blocos))
        return b, im

    with ThreadPoolExecutor(max_workers=6) as ex:
        for (bx, by), im in ex.map(um, blocos):
            if im is not None:
                tela.paste(im, ((bx - bx0) * 256, (by - by0) * 256))
    if falhas and len(falhas) == len(blocos):
        raise ErroTerreno("a fonte de imagem não respondeu (%s). Confira a internet." % falhas[0])
    return tela.crop((px0 - bx0 * 256, py0 - by0 * 256, px1 - bx0 * 256, py1 - by0 * 256))


def _imagem_wms(fonte: dict, reg: dict, lado_px: int, baixar, progresso) -> "Image.Image":
    """O GetMap em EPSG:3857 (o GeoServer reprojeta), em pedaços de até 1024 px — muito servidor limita o tamanho."""
    from PIL import Image
    n = max(1, math.ceil(lado_px / 1024))
    passo_px = math.ceil(lado_px / n)
    tela = Image.new("RGB", (passo_px * n, passo_px * n), (128, 128, 128))
    passo_m = (reg["x1"] - reg["x0"]) / n
    k = 0
    for j in range(n):
        for i in range(n):
            x0, y1 = reg["x0"] + i * passo_m, reg["y1"] - j * passo_m
            q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": fonte["camada"], "STYLES": "",
                 "CRS": "EPSG:3857", "BBOX": "%.3f,%.3f,%.3f,%.3f" % (x0, y1 - passo_m, x0 + passo_m, y1),
                 "WIDTH": passo_px, "HEIGHT": passo_px, "FORMAT": "image/jpeg"}
            dados = baixar(fonte["url"] + "?" + urllib.parse.urlencode(q))
            try:
                im = Image.open(io.BytesIO(dados)).convert("RGB")
            except Exception:
                raise ErroTerreno("o WMS não devolveu imagem: %s" % dados[:300].decode("utf-8", "replace"))
            tela.paste(im, (i * passo_px, j * passo_px))
            k += 1
            progresso("baixando a imagem do terreno (%d de %d partes)" % (k, n * n), 0.05 + 0.85 * k / (n * n))
    return tela


def baixar_imagem(g, s: str, corpo: Optional[dict] = None, progresso: Callable = lambda *a: None,
                  baixar: Callable[[str], bytes] = _baixar) -> dict:
    """Baixa a imagem em volta da obra pela amarração gravada (com a `caixa` do modelo do corpo, em mm do projeto) e a
    guarda na pasta do projeto. A anterior só sai depois de a nova estar pronta."""
    p = g.ler(s)
    t = dict(p.get("terreno") or {})
    if not t:
        raise ErroTerreno("defina o local da obra antes de baixar a imagem.")
    corpo = corpo or {}
    if isinstance(corpo.get("caixa"), list) and len(corpo["caixa"]) == 4:
        t["caixa"] = [round(float(v), 1) for v in corpo["caixa"]]
        g.tocar(s, terreno=t)
    caixa = t.get("caixa") or [t["ponto"][0] - 20000, t["ponto"][1] - 20000, t["ponto"][0] + 20000, t["ponto"][1] + 20000]
    fonte = t.get("fonte") or "esri"
    cfg = fonte if isinstance(fonte, dict) else FONTES.get(fonte)
    if not cfg:
        raise ErroTerreno("fonte de imagem desconhecida: %s" % fonte)
    reg = regiao(t, caixa)
    progresso("preparando a imagem do terreno…", 0.02)
    if cfg["tipo"] == "wms":
        z = None
        lado_px = min(PIXELS_MAX, int(reg["lado_m"] / 0.1))   # ortofoto de prefeitura: até 10 cm por pixel
        lado_px = max(lado_px, 512)
        im = _imagem_wms(cfg, reg, lado_px, baixar, progresso)
    else:
        z = zoom_para(reg["lado_m"], reg["lat"], cfg.get("zoom_max", ZOOM_MAX))
        progresso("procurando o nível da imagem…", 0.04)
        z = _nivel_com_imagem(cfg, reg, z, baixar)
        im = _imagem_xyz(cfg, reg, z, baixar, progresso)
    progresso("gravando a imagem…", 0.95)
    pasta = os.path.join(g.pasta(s), PASTA)
    os.makedirs(pasta, exist_ok=True)
    tmp = os.path.join(pasta, "imagem.jpg.tmp")
    im.save(tmp, "JPEG", quality=86)
    os.replace(tmp, os.path.join(pasta, "imagem.jpg"))
    meta = {"x0": reg["x0"], "y0": reg["y0"], "x1": reg["x1"], "y1": reg["y1"], "largura": im.size[0],
            "altura": im.size[1], "zoom": z, "lado_m": round(reg["lado_m"], 1),
            "fonte": cfg.get("nome") or fonte, "atribuicao": cfg.get("atribuicao") or cfg.get("nome") or "",
            "baixada_em": time.strftime("%Y-%m-%d %H:%M"), "versao": int(time.time())}
    with open(os.path.join(pasta, "imagem.json"), "w", encoding="utf-8", newline="") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return estado(g, s)


# ------------------------------------------------------------------ as rotas (app.py)

def rota_get(g, s: str, resto: list, q: dict) -> dict:
    """GET /api/projetos/<s>/terreno[/imagem.jpg|/buscar-endereco?q=]. {"arquivo": caminho} = servir o arquivo."""
    if not resto:
        return estado(g, s)
    if resto == ["imagem.jpg"]:
        return {"arquivo": os.path.join(g.pasta(s), PASTA, "imagem.jpg")}
    if resto == ["buscar-endereco"]:
        return buscar_endereco((q.get("q") or [""])[0])
    raise ErroTerreno("rota do terreno desconhecida: %s" % "/".join(resto))


def rota_post(g, s: str, resto: list, corpo: dict, progresso: Callable) -> dict:
    """POST /api/projetos/<s>/terreno (grava a amarração) e …/terreno/baixar-imagem."""
    if not resto:
        return gravar(g, s, corpo)
    if resto == ["baixar-imagem"]:
        return baixar_imagem(g, s, corpo, progresso)
    if resto == ["esquecer"]:
        g.tocar(s, terreno=None)
        return estado(g, s)
    raise ErroTerreno("rota do terreno desconhecida: %s" % "/".join(resto))
