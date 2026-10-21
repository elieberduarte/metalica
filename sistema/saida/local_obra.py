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
from typing import Callable, Dict, Optional

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
    # a ortofoto 2021 da sede de Cascavel (IPC), a do geoportal da prefeitura (geocascavel.cascavel.pr.gov.br/geo-view,
    # "ORTOFOTO 2021 - SEDE"): pública, ~20 cm por pixel; em blocos de 256 px no EPSG:900913, como o geoportal pede
    # (os blocos vêm prontos do cache dele, ~0,3 s cada; um GetMap de 1024 px levava 40 s)
    "cascavel": {"nome": "Ortofoto 2021 — Prefeitura de Cascavel (sede)", "tipo": "wms", "zoom_max": 20,
                 "url": "https://geoserver.cascavel.pr.gov.br:8181/geoserver/wms", "camada": "ctmgeo_22s:CASCAVEL",
                 "srs": "EPSG:900913", "formato": "image/png", "tiled": True,
                 "atribuicao": "Ortofoto 2021: Prefeitura de Cascavel — IPC"},
    # a ortofoto recente de Toledo (21/10, o usuário: "encontrei um geoportal da cidade de Toledo" — o da plataforma
    # nacidade, CTM, plataforma.nacidade.com.br/ctm-3/sig-web): pública, até ~7 cm por pixel (nível 21), 0,4 s o bloco
    "toledo": {"nome": "Ortofoto recente — Prefeitura de Toledo", "tipo": "wms", "zoom_max": 21,
               "url": "https://plataforma.nacidade.com.br/geoserver/wms", "camada": "toledo-ctm-3:imagem_recente",
               "srs": "EPSG:3857", "formato": "image/png",
               "atribuicao": "Ortofoto: Prefeitura de Toledo — Maptriz Smart City / DRZ"},
}
# a fonte falsa dos testes (sem internet): quadriculado com o número de cada bloco
if os.environ.get("METALICA_TERRENO_FALSO") == "1":
    FONTES["teste"] = {"nome": "Teste (sem internet)", "tipo": "teste", "zoom_max": 19, "atribuicao": "Imagem de teste"}

AGENTE = "Metalica/1.0 (estruturas metalicas; suporte.vizin@gmail.com)"   # o Nominatim pede identificação


class ErroTerreno(ErroDeDados):
    pass


# ------------------------------------------------------------------ as contas (as mesmas do terreno.js)

def _raios(lat: float) -> tuple:
    """Os raios de curvatura do elipsoide (GRS80 = WGS 84 aqui) na latitude: o do meridiano (norte–sul) e o da primeira
    vertical (leste–oeste). Com a Terra esfera de 6.378 km a distância norte–sul errava 0,5 % no Paraná — meio metro a cada
    100 m (21/10, o IFC georreferenciado da PRATI CD)."""
    e2 = (1 / 298.257222101) * (2 - 1 / 298.257222101)
    s2 = math.sin(math.radians(lat)) ** 2
    return (R_TERRA * (1 - e2) / (1 - e2 * s2) ** 1.5, R_TERRA / math.sqrt(1 - e2 * s2))


def modelo_para_geo(t: dict, x: float, y: float) -> tuple:
    """O ponto do modelo (mm) em (lat, lon) pela amarração `t`. A obra é pequena perto da Terra: o plano tangente no
    ponto de amarração, com os raios do elipsoide, basta (milímetros em centenas de metros)."""
    a = math.radians(float(t.get("norte") or 0.0))
    dx, dy = (x - t["ponto"][0]) / 1000.0, (y - t["ponto"][1]) / 1000.0
    leste = dx * math.cos(a) + dy * math.sin(a)
    norte = -dx * math.sin(a) + dy * math.cos(a)
    m, n = _raios(t["lat"])
    return (t["lat"] + math.degrees(norte / m), t["lon"] + math.degrees(leste / (n * math.cos(math.radians(t["lat"])))))


def geo_para_modelo(t: dict, lat: float, lon: float) -> tuple:
    a = math.radians(float(t.get("norte") or 0.0))
    m, n = _raios(t["lat"])
    norte = math.radians(lat - t["lat"]) * m
    leste = math.radians(lon - t["lon"]) * n * math.cos(math.radians(t["lat"]))
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
    # a altura da imagem (mm do projeto); sem ela, no pé da obra. O usuário, 20/10, no Mercado (subsolo): "preciso deixar a
    # imagem no nível 0 para a fundação não ficar voando"
    if t.get("cota") is not None and str(t.get("cota")).strip() != "":
        try:
            cota = float(t["cota"])
        except (TypeError, ValueError):
            raise ErroTerreno("a altura da imagem precisa ser um número (mm).")
        if not math.isfinite(cota):
            raise ErroTerreno("a altura da imagem precisa ser um número (mm).")
        saida["cota"] = round(cota, 1)
    # a transparência da imagem, 0 a 0,9 (usuário, 20/10: "colocar a imagem com uma certa transparência para ver o subsolo")
    try:
        transp = float(t.get("transparencia") or 0.0)
    except (TypeError, ValueError):
        transp = 0.0
    if math.isfinite(transp) and transp > 0:
        saida["transparencia"] = round(min(transp, 0.9), 2)
    fonte = t.get("fonte") or "esri"
    if isinstance(fonte, dict):
        saida["fonte"] = fonte_do_endereco(str(fonte.get("url") or ""), str(fonte.get("camada") or ""),
                                           str(fonte.get("nome") or ""))
    elif fonte in FONTES:
        saida["fonte"] = fonte
    else:
        raise ErroTerreno("fonte de imagem desconhecida: %s" % fonte)
    if isinstance(t.get("caixa"), list) and len(t["caixa"]) == 4:
        saida["caixa"] = [round(float(v), 1) for v in t["caixa"]]
    return saida


COMO_COPIAR = ("No geoportal, aperte F12 → aba Rede (Network), escreva GetMap no filtro, mexa no mapa e copie o endereço de "
               "uma das linhas (botão direito → Copiar → Copiar URL); cole aqui — a camada vem junto.")


def fonte_do_endereco(url: str, camada: str = "", nome: str = "") -> dict:
    """A fonte de outro servidor pelo que se consegue copiar do navegador (20/10, o geoportal de Cascavel: o usuário colou o
    endereço da página e a camada ficou em branco): o pedido GetMap inteiro (a camada sai do LAYERS=), só o endereço do
    WMS (a camada se acha no GetCapabilities ao baixar) ou o modelo de blocos com {z}/{x}/{y}."""
    url = url.strip()
    if not re.match(r"^https?://", url):
        raise ErroTerreno("cole o endereço do serviço de imagem (começa com http…). " + COMO_COPIAR)
    host = urllib.parse.urlsplit(url).netloc
    if host.split(":")[0].endswith("cascavel.pr.gov.br") and not camada.strip():
        return "cascavel"                                     # qualquer link do geoportal (a página, o lote, o GetMap)
    if host.split(":")[0] == "plataforma.nacidade.com.br" and "geoserver" not in url:
        # o geoportal "nacidade" (CTM) de várias cidades (Toledo, Palotina, Guaíra, Cianorte…): o link da página vira o
        # GeoServer dele; a camada (a ortofoto da cidade da obra) se acha pelo lugar ao baixar
        return {"tipo": "wms", "url": "https://plataforma.nacidade.com.br/geoserver/wms", "camada": camada.strip(),
                "srs": "EPSG:3857", "formato": "image/png", "nome": (nome or "Geoportal nacidade")[:80],
                "atribuicao": "Ortofoto: prefeitura — plataforma nacidade (Maptriz / DRZ)"}
    if all(k in url for k in ("{z}", "{x}", "{y}")):
        return {"tipo": "xyz", "url": url, "zoom_max": 21, "nome": (nome or host)[:80], "atribuicao": "Imagem: " + host}
    q = {k.lower(): v for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
    camada = camada.strip() or (q.get("layers") or [""])[0].strip()
    return {"tipo": "wms", "url": url.split("?")[0], "camada": camada, "nome": (nome or "WMS " + host)[:80],
            "atribuicao": "Imagem: " + host}


def camadas_do_wms(url: str, baixar: Callable[[str], bytes]) -> list:
    """[(nome, título, caixa)] das camadas do GetCapabilities; caixa = (oeste, leste, sul, norte) em graus, ou None."""
    import xml.etree.ElementTree as ET
    dados = baixar(url + "?" + urllib.parse.urlencode({"SERVICE": "WMS", "REQUEST": "GetCapabilities", "VERSION": "1.3.0"}))
    try:
        raiz = ET.fromstring(dados)
    except ET.ParseError:
        raise ErroTerreno("o endereço não é de um serviço WMS (a resposta não é a lista de camadas). " + COMO_COPIAR)
    tira = lambda tag: tag.rsplit("}", 1)[-1]
    saida = []
    for el in raiz.iter():
        if tira(el.tag) != "Layer":
            continue
        filhos = {tira(c.tag): (c.text or "").strip() for c in el}
        if filhos.get("Name"):
            caixa = None
            for c in el:
                if tira(c.tag) == "EX_GeographicBoundingBox":
                    v = {tira(k.tag): k.text for k in c}
                    try:
                        caixa = tuple(float(v[k]) for k in ("westBoundLongitude", "eastBoundLongitude",
                                                            "southBoundLatitude", "northBoundLatitude"))
                    except (KeyError, TypeError, ValueError):
                        caixa = None
            saida.append((filhos["Name"], filhos.get("Title", ""), caixa))
    return saida


def ortofotos_candidatas(camadas: list, lugar: Optional[tuple] = None) -> list:
    """As ortofotos entre as camadas (orto/imagem/mosaico no nome ou no título), da mais provável à menos: as que cobrem o
    `lugar` (lat, lon) pela caixa declarada (quando ela diz algo), a "recente" antes da "anterior", o ano mais novo e a
    menor caixa; com uma camada só, ela."""
    camadas = [c if len(c) > 2 else (c[0], c[1], None) for c in camadas]
    if lugar:
        lat, lon = lugar
        cobre = [c for c in camadas if c[2] and c[2][0] <= lon <= c[2][1] and c[2][2] <= lat <= c[2][3]]
        if cobre:
            camadas = cobre
    ortos = [c for c in camadas if re.search(r"orto|ortho|imagem|aerofoto|mosaic", c[0] + " " + c[1], re.I)]
    if not ortos:
        return [camadas[0][0]] if len(camadas) == 1 else []
    area = lambda c: (c[2][1] - c[2][0]) * (c[2][3] - c[2][2]) if c[2] else float("inf")

    def nota(c):
        texto = c[0] + " " + c[1]
        ano = max([int(a) for a in re.findall(r"(?:19|20)\d\d", texto)] or [0])
        # as de demonstração do servidor (apresentação, treinamento, prova de conceito) por último: em Toledo a camada
        # "publicatreinamentos" também cobre a cidade
        demo = -1 if re.search(r"apresenta|treinamento|teste|demo|(^|[^a-z])poc[^a-z]", c[0], re.I) else 0
        return (demo, 1 if re.search(r"recente", texto, re.I) else 0, -1 if re.search(r"anterior", texto, re.I) else 0, ano, -area(c))
    return [c[0] for c in sorted(ortos, key=nota, reverse=True)]


def camada_da_ortofoto(camadas: list, lugar: Optional[tuple] = None) -> Optional[str]:
    """A ortofoto mais provável (ortofotos_candidatas), ou None."""
    lista = ortofotos_candidatas(camadas, lugar)
    return lista[0] if lista else None


def _a_que_tem_imagem(cfg: dict, candidatas: list, reg: dict, baixar, limite: int = 120) -> Optional[str]:
    """A primeira candidata (na ordem) que devolve imagem no meio da região: o servidor "nacidade" serve dezenas de cidades
    com a mesma caixa declarada (o Brasil inteiro) — só o pedido mostra qual ortofoto cobre a obra (21/10, Toledo)."""
    mundo = 2 * math.pi * R_TERRA
    z = 17
    por_px = mundo / (256 * 2 ** z)
    x = int(((reg["x0"] + reg["x1"]) / 2 + mundo / 2) / por_px // 256)
    y = int((mundo / 2 - (reg["y0"] + reg["y1"]) / 2) / por_px // 256)

    def tem(nome):
        try:
            return _bloco(dict(cfg, camada=nome), z, x, y, baixar) is not None
        except Exception:
            return False
    lista = candidatas[:limite]
    with ThreadPoolExecutor(max_workers=8) as ex:
        resultado = list(ex.map(tem, lista))
    return next((n for n, ok in zip(lista, resultado) if ok), None)


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
    link do Google Maps (…/@-24.95,-53.45,17z ou !3d-24.95!4d-53.45), e as do geoportal da prefeitura: graus/minutos/
    segundos (24° 57' 29.66" S, 53° 29' 5.18" O) ou UTM SIRGAS 2000 (X 249306, Y 7237399). None se não é coordenada."""
    t = str(texto or "").strip()
    c = _gms_do_texto(t) or _utm_do_texto(t)
    if c:
        return c
    m = (re.search(r"!3d(%s)!4d(%s)" % (_PONTO, _PONTO), t) or re.search(r"@(%s),(%s)" % (_PONTO, _PONTO), t)
         or re.fullmatch(r"(%s)\s*[,;\s]\s*(%s)" % (_PONTO, _PONTO), t)
         or re.fullmatch(r"(%s)\s*[;\s]\s*(%s)" % (_VIRGULA, _VIRGULA), t))
    if not m:
        return None
    lat, lon = (float(v.replace(",", ".")) for v in (m.group(1), m.group(2)))
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


# graus, minutos e segundos com o hemisfério: 24° 57' 29.66" S (o "Lote selecionado" do geoportal de Cascavel, 20/10)
_GMS = r"(\d{1,3})\s*[°º]\s*(\d{1,2})\s*['′’]\s*(\d{1,2}(?:[.,]\d+)?)\s*(?:\"|″|''|”)?\s*([NSLOWE])(?![A-Za-z])"


def _gms_do_texto(t: str) -> Optional[tuple]:
    """Latitude e longitude em graus/minutos/segundos ("24° 57' 29.66" S … 53° 29' 5.18" O"; O/W = oeste, L/E = leste)."""
    achados = re.findall(_GMS, t, flags=re.I)
    if len(achados) != 2:
        return None
    lat = lon = None
    for g, mi, se, h in achados:
        v = int(g) + int(mi) / 60 + float(se.replace(",", ".")) / 3600
        h = h.upper()
        if h in "NS":
            lat = -v if h == "S" else v
        else:
            lon = -v if h in "OW" else v
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return (lat, lon)


def _utm_do_texto(t: str) -> Optional[tuple]:
    """UTM SIRGAS 2000 ("X: 249306.0253, Y: 7237399.2034"): o leste (6 dígitos) e o norte (7 dígitos), com o fuso se vier
    escrito ("22S", "fuso 22", "zona 22J"); sem ele, o 22 sul (o oeste e o centro do Paraná, SC e o oeste do RS)."""
    nums = re.findall(r"(?<![\d.,])(\d{6,7}(?:[.,]\d+)?)(?![\d])", t)
    if len(nums) != 2:
        return None
    a, b = (float(v.replace(",", ".")) for v in nums)
    leste, norte = (a, b) if a < b else (b, a)
    if not (100_000 <= leste <= 900_000 and 1_000_000 <= norte <= 10_000_000):
        return None
    m = re.search(r"(?:fuso|zona|zone)\s*(\d{1,2})|(?<![\d.,])(\d{2})\s*([C-X])(?![A-Za-z])", t, flags=re.I)
    fuso = int(m.group(1) or m.group(2)) if m else 22
    letra = (m.group(3) or "").upper() if m else ""
    # no Brasil "22S" é o fuso 22 sul (não a faixa S do MGRS); as outras letras são as faixas (C–M sul, N–X norte)
    norte_hem = letra == "N" or (letra not in ("", "S") and letra > "N")
    return utm_para_geo(leste, norte, fuso, sul=not norte_hem)


def utm_para_geo(leste: float, norte: float, fuso: int, sul: bool = True) -> tuple:
    """UTM → (lat, lon) no elipsoide GRS80 (SIRGAS 2000; o WGS 84 difere em décimos de milímetro)."""
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x = leste - 500_000.0
    y = norte - (10_000_000.0 if sul else 0.0)
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    f1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    c1 = ep2 * math.cos(f1) ** 2
    t1 = math.tan(f1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(f1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(f1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = f1 - (n1 * math.tan(f1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                          + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(f1)
    return (math.degrees(lat), (fuso - 1) * 6 - 180 + 3 + math.degrees(lon))


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
    if im.mode in ("RGBA", "LA", "P"):
        a = im.convert("RGBA").getchannel("A")
        if a.getextrema()[1] == 0:
            return True                                       # o WMS fora da ortofoto: transparente
    st = ImageStat.Stat(im.convert("RGB"))
    if max(st.stddev) < 1.5:
        return True                                           # de uma cor só (o fundo branco ou preto do WMS)
    return (max(st.stddev) < 12 and all(185 < m < 225 for m in st.mean) and max(st.mean) - min(st.mean) < 4)


def _bloco(fonte: dict, z: int, x: int, y: int, baixar):
    from PIL import Image
    if fonte["tipo"] == "teste":
        return None if z > fonte.get("zoom_real", 99) else _bloco_teste(z, x, y)
    url = _url_bloco_wms(fonte, z, x, y) if fonte["tipo"] == "wms" else fonte["url"].format(z=z, x=x, y=y)
    dados = baixar(url)
    try:
        im = Image.open(io.BytesIO(dados))
        im.load()
    except Exception:
        raise ErroTerreno("o servidor não devolveu imagem: %s" % dados[:300].decode("utf-8", "replace"))
    return None if _vazio(im) else im.convert("RGB")


def _url_bloco_wms(fonte: dict, z: int, x: int, y: int) -> str:
    """O GetMap do bloco (x, y) do nível z, no quadriculado do Web Mercator — o mesmo dos blocos XYZ."""
    lado = 2 * math.pi * R_TERRA / 2 ** z
    x0, y1 = -math.pi * R_TERRA + x * lado, math.pi * R_TERRA - y * lado
    q = {"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "LAYERS": fonte["camada"], "STYLES": "",
         "SRS": fonte.get("srs") or "EPSG:3857", "BBOX": "%.6f,%.6f,%.6f,%.6f" % (x0, y1 - lado, x0 + lado, y1),
         "WIDTH": 256, "HEIGHT": 256, "FORMAT": fonte.get("formato") or "image/png"}
    if fonte.get("tiled"):
        q["TILED"] = "true"
    return fonte["url"] + "?" + urllib.parse.urlencode(q)


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
        except ErroTerreno:
            raise
        except Exception:
            return z                                          # sem resposta: o download conta a falha
        z -= 1
    return None


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
        im = None
        for tentativa in range(3):                           # o servidor da prefeitura às vezes não entrega na hora (a
            try:                                             # PRATI em Toledo, 21/10: um quadrado cinza na imagem)
                im = _bloco(fonte, z, bx, by, baixar)        # o vazio da fonte fica cinza, como o que falha
                break
            except Exception as e:                           # três falhas: o bloco fica cinza e a imagem sai
                if tentativa == 2:
                    falhas.append(str(e))
                else:
                    time.sleep(0.5 * (tentativa + 1))
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
    if cfg["tipo"] == "wms" and not cfg.get("camada"):
        progresso("procurando a camada da ortofoto no servidor…", 0.03)
        camadas = camadas_do_wms(cfg["url"], baixar)
        candidatas = ortofotos_candidatas(camadas, (t["lat"], t["lon"]))
        if len(candidatas) > 1:
            progresso("procurando a ortofoto que cobre a obra (%d candidatas)…" % len(candidatas), 0.035)
            achada = _a_que_tem_imagem(cfg, candidatas, regiao(t, caixa), baixar)
            if not achada:
                raise ErroTerreno("nenhuma das %d ortofotos do servidor tem imagem no lugar da obra. Escolha outra fonte (a "
                                  "Esri cobre o mundo todo)." % len(candidatas))
        else:
            achada = candidatas[0] if candidatas else None
        if not achada:
            raise ErroTerreno("o servidor tem %d camadas e nenhuma parece a ortofoto: %s. Escreva o nome da camada, ou "
                              "%s" % (len(camadas), ", ".join(c[0] for c in camadas[:12]) or "nenhuma",
                                      COMO_COPIAR[0].lower() + COMO_COPIAR[1:]))
        cfg = dict(cfg, camada=achada)
        t["fonte"] = cfg
        g.tocar(s, terreno=t)                              # a camada achada fica gravada: a próxima vez não pergunta
    # o WMS também em blocos de 256 px no quadriculado do Web Mercator (o geoportal de Cascavel: 0,3 s o bloco, que vem
    # pronto do cache dele, × 40 s um GetMap de 1024 px)
    z0 = zoom_para(reg["lado_m"], reg["lat"], cfg.get("zoom_max", ZOOM_MAX))
    progresso("procurando o nível da imagem…", 0.04)
    z = _nivel_com_imagem(cfg, reg, z0, baixar)
    if z is None:
        if cfg["tipo"] == "wms":
            raise ErroTerreno("a imagem de %s não cobre este lugar (os blocos vêm vazios). Escolha outra fonte — a Esri "
                              "cobre o mundo todo." % (cfg.get("nome") or "WMS"))
        z = z0
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


# ------------------------------------------------------------------ o terreno no IFC

def geo_para_utm(lat: float, lon: float, fuso: Optional[int] = None) -> tuple:
    """(lat, lon) → (leste, norte, fuso, sul) na UTM do GRS80 (SIRGAS 2000); a ida da utm_para_geo."""
    if fuso is None:
        fuso = int((lon + 180) // 6) + 1
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    fi, la = math.radians(lat), math.radians(lon - ((fuso - 1) * 6 - 180 + 3))
    n = a / math.sqrt(1 - e2 * math.sin(fi) ** 2)
    t = math.tan(fi) ** 2
    c = ep2 * math.cos(fi) ** 2
    A = math.cos(fi) * la
    m = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * fi
             - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * fi)
             + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * fi) - (35 * e2 ** 3 / 3072) * math.sin(6 * fi))
    x = k0 * n * (A + (1 - t + c) * A ** 3 / 6 + (5 - 18 * t + t ** 2 + 72 * c - 58 * ep2) * A ** 5 / 120) + 500_000.0
    y = k0 * (m + n * math.tan(fi) * (A ** 2 / 2 + (5 - t + 9 * c + 4 * c ** 2) * A ** 4 / 24
                                       + (61 - 58 * t + t ** 2 + 600 * c - 330 * ep2) * A ** 6 / 720))
    return (x, y + (10_000_000.0 if lat < 0 else 0.0), fuso, lat < 0)


def crs_utm(fuso: int, sul: bool) -> dict:
    """O sistema de coordenadas do mapa: SIRGAS 2000 / UTM (o oficial do Brasil, fusos 18 a 25) ou o WGS 84 / UTM fora dele."""
    if (sul and 18 <= fuso <= 25) or (not sul and 17 <= fuso <= 22):
        codigo = (31960 if sul else 31955) + fuso            # 31978 = 18S … 31985 = 25S; 31972 = 17N … 31977 = 22N
        return {"nome": "EPSG:%d" % codigo, "descricao": "SIRGAS 2000 / UTM zone %d%s" % (fuso, "S" if sul else "N"),
                "datum": "SIRGAS2000", "zona": "%d%s" % (fuso, "S" if sul else "N")}
    codigo = (32700 if sul else 32600) + fuso
    return {"nome": "EPSG:%d" % codigo, "descricao": "WGS 84 / UTM zone %d%s" % (fuso, "S" if sul else "N"),
            "datum": "WGS84", "zona": "%d%s" % (fuso, "S" if sul else "N")}


def para_ifc(t: dict, meta: dict, caminho_jpg: str, deslocamento=(0.0, 0.0, 0.0), z_padrao: float = 0.0,
             foco: Optional[tuple] = None) -> dict:
    """O terreno para o IFC (usuário, 21/10: "montar um IFC com a imagem do terreno da Prati CD para mandar para o
    cliente"): a georreferência (o sítio em latitude e longitude, o norte verdadeiro e a conversão para a UTM do mapa — o
    IfcMapConversion do IFC4) e a placa com a imagem (os quatro cantos dela em mm do modelo, na altura da imagem).

    O IFC põe as peças em `deslocamento` + as coordenadas do modelo (o sítio do modelo importado volta ao lugar da obra):
    a origem do mundo do IFC é o ponto −deslocamento do modelo."""
    dx, dy, _dz = (float(v) for v in (list(deslocamento or ()) + [0.0, 0.0, 0.0])[:3])
    # tudo no ponto de amarração (na obra) e levado até a origem do mundo do IFC pela própria conversão: no modelo
    # importado o mundo começa a milhares de km (o IFC do Revit em UTM, mm) e o plano tangente lá não vale
    px, py = float(t["ponto"][0]), float(t["ponto"][1])
    leste_a, norte_a, fuso, sul = geo_para_utm(t["lat"], t["lon"])
    # o eixo X do IFC no mapa: 100 m dele na UTM — já com a convergência dos meridianos e o fator de escala da UTM
    leste1, norte1, _f, _s = geo_para_utm(*modelo_para_geo(t, px + 100_000.0, py), fuso)
    ax, ay = leste1 - leste_a, norte1 - norte_a
    na = math.hypot(ax, ay) or 1.0
    ca, sa, escala = ax / na, ay / na, 0.001 * na / 100.0
    wx, wy = dx + px, dy + py                                 # a amarração no mundo do IFC (mm)
    leste0 = leste_a - escala * (wx * ca - wy * sa)
    norte0 = norte_a - escala * (wx * sa + wy * ca)
    a = math.radians(float(t.get("norte") or 0.0))
    lat_s, lon_s = modelo_para_geo(t, 0.0, 0.0)              # o sítio: a origem do modelo
    z = float(t["cota"]) if t.get("cota") is not None else float(z_padrao)
    cantos = []
    for mx, my in ((meta["x0"], meta["y0"]), (meta["x1"], meta["y0"]), (meta["x1"], meta["y1"]), (meta["x0"], meta["y1"])):
        x, y = geo_para_modelo(t, *de_mercator(mx, my))
        cantos.append((round(x, 1), round(y, 1), round(z, 1)))
    with open(caminho_jpg, "rb") as f:
        jpg = f.read()
    return {"mosaico": _mosaico(jpg, cantos, foco),
            "lat_sitio": lat_s, "lon_sitio": lon_s, "norte": (-math.sin(a), math.cos(a)),
            "mapa": dict(crs_utm(fuso, sul), leste=leste0, norte=norte0, abscissa=ca, ordenada=sa, escala=escala),
            "cantos": cantos, "jpg": jpg, "fonte": meta.get("fonte") or "", "atribuicao": meta.get("atribuicao") or "",
            "baixada_em": meta.get("baixada_em") or "", "lado_m": meta.get("lado_m")}


MOSAICO_LADO = 1024           # quadrados por lado na resolução fina (até a da imagem: a PRATI, 871 px → 0,54 m)
MOSAICO_CORES = 256
MOSAICO_GROSSO = 4            # fora da obra, quadrados 4 × maiores (a vizinhança: a PRATI, 2,2 m)
MOSAICO_MARGEM_MM = 30_000    # a resolução fina vai até 30 m em volta da obra


def _uv_do_ponto(cantos: list, x: float, y: float) -> tuple:
    """(u, v) do ponto do modelo na placa (0 = sudoeste, 1 = sudeste, 3 = noroeste)."""
    (x0, y0, _z), (x1, y1, _z1), _c2, (x3, y3, _z3) = cantos
    ax, ay, bx, by = x1 - x0, y1 - y0, x3 - x0, y3 - y0
    det = ax * by - ay * bx
    dx, dy = x - x0, y - y0
    return ((dx * by - dy * bx) / det, (ax * dy - ay * dx) / det)


def _mosaico(jpg: bytes, cantos: list, foco: Optional[tuple] = None, lado: int = MOSAICO_LADO,
             cores: int = MOSAICO_CORES, grosso: int = MOSAICO_GROSSO) -> dict:
    """A imagem como um mosaico de quadrados coloridos (21/10, o usuário no Trimble Connect: "não aparece" — o Trimble não
    lê textura de IFC; a cor da superfície, todo programa mostra): faixas de quadrados vizinhos da mesma cor viram um
    retângulo só, e os triângulos se agrupam pela cor (a imagem reduzida a `cores` cores) — um IfcTriangulatedFaceSet com
    a cor dele por grupo. Na obra (`foco` = [x0, y0, x1, y1] mm do modelo, com a margem) a resolução da imagem; fora dela,
    quadrados `grosso` vezes maiores ("abriu, porém a resolução do terreno ficou muito baixa" — o arquivo da PRATI com a
    imagem toda em resolução cheia passava de 900 mil triângulos). Sem `foco`, tudo na resolução fina."""
    from PIL import Image
    im = Image.open(io.BytesIO(jpg)).convert("RGB")
    n = max(grosso, min(lado, im.size[0], im.size[1]))
    n -= n % grosso
    nc = n // grosso
    fina = im.resize((n, n), Image.BOX).quantize(colors=cores, method=Image.Quantize.MEDIANCUT)
    grossa = im.resize((nc, nc), Image.BOX).quantize(palette=fina)
    paleta = fina.getpalette()[:3 * cores]
    df, dg = fina.tobytes(), grossa.tobytes()                 # linha 0 = em cima (o norte)
    if foco:
        uvs = [_uv_do_ponto(cantos, x, y) for x, y in ((foco[0], foco[1]), (foco[2], foco[1]), (foco[2], foco[3]), (foco[0], foco[3]))]
        u0, u1 = max(0.0, min(u for u, _ in uvs)), min(1.0, max(u for u, _ in uvs))
        v0, v1 = max(0.0, min(v for _, v in uvs)), min(1.0, max(v for _, v in uvs))
    else:
        u0, v0, u1, v1 = 0.0, 0.0, 1.0, 1.0

    def no_foco(i_g: int, j_g: int) -> bool:                  # a célula grossa (coluna, linha de baixo para cima) toca a obra?
        return (i_g + 1) / nc > u0 and i_g / nc < u1 and (j_g + 1) / nc > v0 and j_g / nc < v1

    (x0, y0, z), (x1, y1, _z1), _c2, (x3, y3, _z3) = cantos
    pontos, uv, indice = [], [], {}

    def p(i: int, j: int) -> int:                             # o ponto (i, j) da grade fina, 1… (o IFC conta de 1)
        k = indice.get((i, j))
        if k is None:
            u, v = i / n, j / n
            pontos.append((round(x0 + u * (x1 - x0) + v * (x3 - x0), 1), round(y0 + u * (y1 - y0) + v * (y3 - y0), 1), z))
            uv.append((round(u, 5), round(v, 5)))
            k = indice[(i, j)] = len(pontos)
        return k

    grupos: Dict[int, list] = {}

    def retangulo(cor: int, i0: int, j0: int, i1: int, j1: int):
        a, b, c, d = p(i0, j0), p(i1, j0), p(i1, j1), p(i0, j1)
        grupos.setdefault(cor, []).extend(((a, b, c), (a, c, d)))

    for jg in range(nc):                                      # a vizinhança, em quadrados grossos
        linha = nc - 1 - jg
        ig = 0
        while ig < nc:
            if no_foco(ig, jg):
                ig += 1
                continue
            cor, fim = dg[linha * nc + ig], ig + 1
            while fim < nc and not no_foco(fim, jg) and dg[linha * nc + fim] == cor:
                fim += 1
            retangulo(cor, ig * grosso, jg * grosso, fim * grosso, (jg + 1) * grosso)
            ig = fim
    for j in range(n):                                        # a obra, na resolução da imagem
        if not any(no_foco(ig, j // grosso) for ig in range(nc)):
            continue
        linha = n - 1 - j
        i = 0
        while i < n:
            if not no_foco(i // grosso, j // grosso):
                i += 1
                continue
            cor, fim = df[linha * n + i], i + 1
            while fim < n and no_foco(fim // grosso, j // grosso) and df[linha * n + fim] == cor:
                fim += 1
            retangulo(cor, i, j, fim, j + 1)
            i = fim
    return {"n": n, "pontos": pontos, "uv": uv,
            "grupos": [{"cor": tuple(paleta[3 * k:3 * k + 3]), "triangulos": tri} for k, tri in sorted(grupos.items())]}


def terreno_para_ifc(g, s: str, doc) -> Optional[dict]:
    """O terreno do projeto para o exportador (None sem o local ou sem a imagem baixada)."""
    p = g.ler(s)
    t = p.get("terreno")
    meta = _meta_imagem(g.pasta(s))
    if not isinstance(t, dict) or not meta:
        return None
    try:
        cx = doc.caixa()
        z_padrao = float(cx[0][2])                            # sem a altura escolhida: no pé da obra, como na tela
        m = MOSAICO_MARGEM_MM                                 # a resolução fina do mosaico: a obra e 30 m em volta
        foco = (cx[0][0] - m, cx[0][1] - m, cx[1][0] + m, cx[1][1] + m)
    except Exception:
        z_padrao, foco = 0.0, None
    return para_ifc(t, meta, os.path.join(g.pasta(s), PASTA, "imagem.jpg"),
                    (doc.metadados or {}).get("deslocamento_mm") or (0.0, 0.0, 0.0), z_padrao, foco)


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
