# -*- coding: utf-8 -*-
"""A obra no terreno (saida/local_obra.py, 20/10): as contas modelo ↔ mundo, a região e o nível da imagem, a coordenada
colada do Google Maps, a busca de endereço e a imagem montada (fonte de teste e WMS, sem internet)."""
import io
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import local_obra as L                       # noqa: E402
from projetos import Projetos                           # noqa: E402

CASCAVEL = (-24.9555, -53.4552)


def _dist_m(a, b):
    """haversine (m)"""
    f1, f2 = math.radians(a[0]), math.radians(b[0])
    df, dl = f2 - f1, math.radians(b[1] - a[1])
    h = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * L.R_TERRA * math.asin(math.sqrt(h))


# o modelo perto da origem, o importado de outro programa (coordenadas de milhões de mm) e o muito pequeno
SITUACOES = [
    {"ponto": [0.0, 0.0], "norte": 0.0},
    {"ponto": [25000.0, 12000.0], "norte": 33.5},
    {"ponto": [7_250_000_000.0, 245_000_000.0], "norte": -120.0},      # UTM em mm (IFC do Revit/Tekla)
    {"ponto": [150.0, 80.0], "norte": 179.9},
]


@pytest.mark.parametrize("sit", SITUACOES)
def test_ida_e_volta(sit):
    t = {"lat": CASCAVEL[0], "lon": CASCAVEL[1], **sit}
    for dx, dy in ((0, 0), (100_000, 0), (0, -250_000), (-40_000, 75_000)):
        x, y = sit["ponto"][0] + dx, sit["ponto"][1] + dy
        lat, lon = L.modelo_para_geo(t, x, y)
        x2, y2 = L.geo_para_modelo(t, lat, lon)
        assert abs(x2 - x) < 1 and abs(y2 - y) < 1                     # menos de 1 mm
        # a distância no mundo é a do modelo (o plano tangente basta na obra)
        assert abs(_dist_m(CASCAVEL, (lat, lon)) - math.hypot(dx, dy) / 1000) < 0.05


def test_o_norte_gira_o_modelo():
    t = {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [0, 0], "norte": 0.0}
    lat, lon = L.modelo_para_geo(t, 0, 100_000)                       # +Y = norte
    assert lat > CASCAVEL[0] and abs(lon - CASCAVEL[1]) < 1e-9
    t["norte"] = 90.0                                                 # o +Y do modelo aponta para o leste
    lat, lon = L.modelo_para_geo(t, 0, 100_000)
    assert abs(lat - CASCAVEL[0]) < 1e-9 and lon > CASCAVEL[1]
    lat, lon = L.modelo_para_geo(t, 100_000, 0)                       # e o +X para o sul
    assert lat < CASCAVEL[0]


@pytest.mark.parametrize("norte", [0.0, 45.0, -73.0])
def test_regiao_cobre_a_obra_em_qualquer_giro(norte):
    t = {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [30_000, 10_000], "norte": norte}
    caixa = [0, 0, 60_000, 20_000]                                    # galpão de 60 × 20 m
    r = L.regiao(t, caixa)
    for x, y in ((0, 0), (60_000, 0), (60_000, 20_000), (0, 20_000)):
        mx, my = L.mercator(*L.modelo_para_geo(t, x, y))
        assert r["x0"] + 50 < mx < r["x1"] - 50 and r["y0"] + 50 < my < r["y1"] - 50   # com folga
    z = L.zoom_para(r["lado_m"], r["lat"])
    px = r["lado_m"] / L.metros_por_pixel(r["lat"], z)
    # o nível mais fino que cabe; numa obra pequena, o mais fino da fonte (o 19 da Esri, ~30 cm por pixel)
    assert px <= L.PIXELS_MAX and (px > L.PIXELS_MAX / 2 or z == L.ZOOM_MAX)


def test_obra_grande_nao_passa_do_lado_maximo():
    t = {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [0, 0], "norte": 0}
    r = L.regiao(t, [0, 0, 400_000, 250_000])                          # 400 × 250 m (CD)
    z = L.zoom_para(r["lado_m"], r["lat"])
    assert r["lado_m"] / L.metros_por_pixel(r["lat"], z) <= L.PIXELS_MAX
    assert z <= L.ZOOM_MAX


@pytest.mark.parametrize("texto,esperado", [
    ("-24.955512, -53.455201", (-24.955512, -53.455201)),             # botão direito do Google Maps
    ("-24,9555 -53,4552", (-24.9555, -53.4552)),                       # vírgula decimal
    ("-24.9555;-53.4552", (-24.9555, -53.4552)),
    ("https://www.google.com/maps/place/X/@-24.9561,-53.4570,17z/data=!3d-24.955512!4d-53.455201",
     (-24.955512, -53.455201)),                                        # o !3d!4d é o do lugar, o @ é a câmera
    ("https://www.google.com/maps/@-24.9561,-53.4570,180m/data=!3m1", (-24.9561, -53.457)),
    ("Rua Paraná, 1000, Cascavel", None),
    ("-24,9555, -53,4552", None),                                      # ambíguo: não adivinha
    ("95.0, 10.0", None),
])
def test_coordenada_colada(texto, esperado):
    c = L.coordenada_do_texto(texto)
    if esperado is None:
        assert c is None
    else:
        assert c == pytest.approx(esperado)


def test_busca_de_endereco_sem_internet():
    pedidos = []

    def falso(url):
        pedidos.append(url)
        return json.dumps([{"display_name": "Cascavel, Paraná, Brasil", "lat": "-24.95", "lon": "-53.45"}]).encode()
    r = L.buscar_endereco("Cascavel PR", baixar=falso)
    assert r["resultados"][0]["lat"] == -24.95 and "countrycodes=br" in pedidos[0]
    # a coordenada colada não vai à internet
    assert L.buscar_endereco("-24.9, -53.4", baixar=lambda u: pytest.fail("foi à internet"))["resultados"][0]["lon"] == -53.4

    def caiu(url):
        raise OSError("sem rede")
    with pytest.raises(L.ErroTerreno, match="cole a coordenada"):
        L.buscar_endereco("Cascavel", baixar=caiu)


def test_validar():
    t = L.validar({"lat": "-24.9", "lon": -53.4, "ponto": [1, 2], "norte": 370})
    assert t["norte"] == 10 and t["fonte"] == "esri"
    t = L.validar({"lat": -24.9, "lon": -53.4, "ponto": [1, 2], "norte": 190})
    assert t["norte"] == -170
    with pytest.raises(L.ErroTerreno):
        L.validar({"lat": -24.9, "lon": -53.4})
    with pytest.raises(L.ErroTerreno):
        L.validar({"lat": 120, "lon": -53.4, "ponto": [0, 0]})
    with pytest.raises(L.ErroTerreno, match="WMS"):
        L.validar({"lat": -24.9, "lon": -53.4, "ponto": [0, 0], "fonte": {"tipo": "wms", "url": "ftp://x"}})
    w = L.validar({"lat": -24.9, "lon": -53.4, "ponto": [0, 0],
                   "fonte": {"tipo": "wms", "url": "https://geo.x.gov.br/geoserver/wms?service=WMS", "camada": "orto"}})
    assert w["fonte"]["url"] == "https://geo.x.gov.br/geoserver/wms"


def _gerente(tmp_path):
    g = Projetos(str(tmp_path))
    r = g.criar("Obra Terreno")
    return g, (r.get("slug") or r.get("id") or "obra-terreno")


def test_gravar_e_baixar_a_imagem_de_teste(tmp_path, monkeypatch):
    monkeypatch.setitem(L.FONTES, "teste", {"nome": "Teste", "tipo": "teste", "zoom_max": 19, "atribuicao": "Teste"})
    g, s = _gerente(tmp_path)
    assert L.estado(g, s)["terreno"] is None
    L.rota_post(g, s, [], {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [30_000, 10_000], "norte": 20,
                           "fonte": "teste", "endereco": "Cascavel"}, lambda *a: None)
    etapas = []
    e = L.rota_post(g, s, ["baixar-imagem"], {"caixa": [0, 0, 60_000, 20_000]}, lambda et, fr=None: etapas.append((et, fr)))
    im = e["imagem"]
    assert im and im["largura"] == im["altura"] <= L.PIXELS_MAX
    # os limites gravados são os dos pixels do recorte (no nível dele): o 3D põe a imagem no lugar certo
    assert abs((im["x1"] - im["x0"]) / im["largura"] - 2 * math.pi * L.R_TERRA / (256 * 2 ** im["zoom"])) < 1e-6
    assert abs((im["x1"] - im["x0"]) - (im["y1"] - im["y0"])) < 1e-6
    assert e["terreno"]["caixa"] == [0, 0, 60_000, 20_000]
    assert any("blocos" in et for et, _ in etapas) and etapas[-1][1] >= 0.9       # a barra de andamento
    caminho = L.rota_get(g, s, ["imagem.jpg"], {})["arquivo"]
    from PIL import Image
    assert Image.open(caminho).size == (im["largura"], im["altura"])
    # o meio da imagem cai no meio da obra (a região é em volta dele), a menos de um pixel (o recorte é em pixels inteiros)
    lat, lon = L.de_mercator((im["x0"] + im["x1"]) / 2, (im["y0"] + im["y1"]) / 2)
    x, y = L.geo_para_modelo(e["terreno"], lat, lon)
    assert abs(x - 30_000) < 400 and abs(y - 10_000) < 400
    # tirar o local
    assert L.rota_post(g, s, ["esquecer"], {}, lambda *a: None)["terreno"] is None


def test_imagem_pelo_wms(tmp_path):
    from PIL import Image
    g, s = _gerente(tmp_path)
    L.gravar(g, s, {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [0, 0], "norte": 0,
                    "fonte": {"tipo": "wms", "url": "https://geo.exemplo.gov.br/geoserver/wms", "camada": "ortofoto2023"}})
    pedidos = []

    def falso(url):
        pedidos.append(url)
        b = io.BytesIO()
        Image.new("RGB", (64, 64), (10, 120, 30)).save(b, "JPEG")
        return b.getvalue()
    e = L.baixar_imagem(g, s, {"caixa": [-30_000, -20_000, 30_000, 20_000]}, baixar=falso)
    assert pedidos and all("CRS=EPSG%3A3857" in u and "LAYERS=ortofoto2023" in u and "REQUEST=GetMap" in u for u in pedidos)
    assert e["imagem"]["fonte"] == "WMS"

    def erro(url):
        return b"<ServiceExceptionReport>camada desconhecida</ServiceExceptionReport>"
    with pytest.raises(L.ErroTerreno, match="camada desconhecida"):
        L.baixar_imagem(g, s, {}, baixar=erro)


def test_sem_local_nao_baixa(tmp_path):
    g, s = _gerente(tmp_path)
    with pytest.raises(L.ErroTerreno, match="local da obra"):
        L.baixar_imagem(g, s, {})


def test_fonte_sem_o_nivel_desce_ate_ter_imagem(tmp_path, monkeypatch):
    """No centro de Cascavel (20/10) a Esri não tem o nível 19: os blocos vinham "Map data not yet available" (cinza
    liso) e a obra ficava num chão cinza. O programa desce de nível até achar a imagem."""
    from PIL import Image
    assert L._vazio(Image.new("RGB", (256, 256), (205, 205, 205)))
    assert not L._vazio(L._bloco_teste(18, 1, 2))
    monkeypatch.setitem(L.FONTES, "teste", {"nome": "Teste", "tipo": "teste", "zoom_max": 19, "zoom_real": 17,
                                             "atribuicao": "Teste"})
    g, s = _gerente(tmp_path)
    L.gravar(g, s, {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [0, 0], "norte": 0, "fonte": "teste"})
    im = L.baixar_imagem(g, s, {"caixa": [-30_000, -20_000, 30_000, 20_000]})["imagem"]
    assert im["zoom"] == 17
