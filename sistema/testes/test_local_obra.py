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


def _dist_elipsoide(a, b):
    """a distância no elipsoide pela UTM (a do fuso de `a`) dividida pelo fator de escala da UTM ali"""
    e1, n1, fuso, _s = L.geo_para_utm(*a)
    e2, n2, _f, _s = L.geo_para_utm(*b, fuso)
    k = 0.9996 * (1 + ((e1 + e2) / 2 - 500_000) ** 2 / (2 * 6_371_000 ** 2))
    return math.hypot(e2 - e1, n2 - n1) / k


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
        # a distância no mundo é a do modelo (o plano tangente com os raios do elipsoide basta na obra) — medida na UTM
        assert abs(_dist_elipsoide(CASCAVEL, (lat, lon)) - math.hypot(dx, dy) / 1000) < 0.02


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
    with pytest.raises(L.ErroTerreno, match="http"):
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


def _png_ruido(lado=256):
    import random
    from PIL import Image
    im = Image.new("RGB", (lado, lado))
    r = random.Random(1)
    im.putdata([(r.randrange(256), r.randrange(256), r.randrange(256)) for _ in range(lado * lado)])
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def test_imagem_pelo_wms_em_blocos(tmp_path):
    """O WMS em blocos de 256 px no quadriculado do Web Mercator (o geoportal de Cascavel, 20/10: o bloco vem do cache em
    0,3 s; um GetMap de 1024 px levava 40 s)."""
    g, s = _gerente(tmp_path)
    L.gravar(g, s, {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [0, 0], "norte": 0,
                    "fonte": {"tipo": "wms", "url": "https://geo.exemplo.gov.br/geoserver/wms", "camada": "ortofoto2023"}})
    pedidos = []
    png = _png_ruido()

    def falso(url):
        pedidos.append(url)
        return png
    e = L.baixar_imagem(g, s, {"caixa": [-30_000, -20_000, 30_000, 20_000]}, baixar=falso)
    assert pedidos and all("LAYERS=ortofoto2023" in u and "REQUEST=GetMap" in u and "WIDTH=256" in u
                           and "SRS=EPSG%3A3857" in u for u in pedidos)
    assert e["imagem"]["fonte"] == "WMS geo.exemplo.gov.br" and e["imagem"]["zoom"] == 19

    def erro(url):
        return b"<ServiceExceptionReport>camada desconhecida</ServiceExceptionReport>"
    with pytest.raises(L.ErroTerreno, match="camada desconhecida"):
        L.baixar_imagem(g, s, {}, baixar=erro)


def test_wms_que_nao_cobre_o_lugar_avisa(tmp_path):
    from PIL import Image
    g, s = _gerente(tmp_path)
    L.gravar(g, s, {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [0, 0], "norte": 0, "fonte": "cascavel"})

    def transparente(url):
        b = io.BytesIO()
        Image.new("RGBA", (256, 256), (0, 0, 0, 0)).save(b, "PNG")
        return b.getvalue()
    with pytest.raises(L.ErroTerreno, match="não cobre"):
        L.baixar_imagem(g, s, {}, baixar=transparente)


@pytest.mark.parametrize("colado,esperado", [
    # o usuário colou o link da página do geoportal de Cascavel e a camada ficou em branco (20/10): a fonte pronta
    ("https://geocascavel.cascavel.pr.gov.br/geo-view/selecionar/empresa-1.ctm?redirect=https://geocascavel.cascavel.pr.gov"
     ".br/geo-view/index.ctm?mslinkLote=4229086", "cascavel"),
    ("https://geocascavel.cascavel.pr.gov.br/geo-view/index.ctm", "cascavel"),
    # o GetMap copiado do F12 de outro geoportal: a camada vem do LAYERS=
    ("https://sig.outra.pr.gov.br/geoserver/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=base%3Aorto2022&SRS=EPSG"
     "%3A900913&BBOX=1,2,3,4&WIDTH=256&HEIGHT=256", {"tipo": "wms", "url": "https://sig.outra.pr.gov.br/geoserver/wms",
                                                     "camada": "base:orto2022"}),
    # o modelo de blocos
    ("https://tiles.exemplo.com/orto/{z}/{x}/{y}.jpg", {"tipo": "xyz", "url": "https://tiles.exemplo.com/orto/{z}/{x}/{y}.jpg"}),
])
def test_fonte_pelo_que_se_cola(colado, esperado):
    f = L.validar({"lat": -24.9, "lon": -53.4, "ponto": [0, 0], "fonte": {"tipo": "wms", "url": colado}})["fonte"]
    if isinstance(esperado, str):
        assert f == esperado
    else:
        assert {k: f.get(k) for k in esperado} == esperado


def test_camada_achada_no_getcapabilities(tmp_path):
    caps = b"""<?xml version="1.0"?><WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability><Layer><Title>raiz</Title>
      <Layer><Name>cad:lotes</Name><Title>Lotes</Title></Layer>
      <Layer><Name>img:orto2012</Name><Title>Ortofoto 2012</Title></Layer>
      <Layer><Name>img:orto2021</Name><Title>Ortofoto 2021</Title></Layer></Layer></Capability></WMS_Capabilities>"""
    assert L.camada_da_ortofoto(L.camadas_do_wms("https://x/wms", lambda u: caps)) == "img:orto2021"
    g, s = _gerente(tmp_path)
    L.gravar(g, s, {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [0, 0], "norte": 0,
                    "fonte": {"tipo": "wms", "url": "https://x.gov.br/geoserver/wms"}})
    png = _png_ruido()
    e = L.baixar_imagem(g, s, {}, baixar=lambda u: caps if "GetCapabilities" in u else png)
    assert e["terreno"]["fonte"]["camada"] == "img:orto2021"                # gravada: a próxima vez não pergunta
    assert L.camada_da_ortofoto([("a", "Lotes"), ("b", "Ruas")]) is None      # sem adivinhar: pede o nome


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


# o geoportal de Cascavel (IPC, 20/10): o "Lote selecionado" dá a latitude e a longitude em graus/minutos/segundos e o
# canto da tela a UTM SIRGAS 2000 — colados como estão, viram o lugar (antes só os graus decimais do Google Maps)
@pytest.mark.parametrize("texto", [
    'Latitude: 24° 57\' 29.66" S\nLongitude: 53° 29\' 5.18" O',
    "24°57'29.66\"S 53°29'5.18\"W",
    "Latitude: 24º 57’ 29.66” S Longitude: 53º 29’ 5.18” O",
])
def test_coordenada_em_graus_minutos_segundos(texto):
    assert L.coordenada_do_texto(texto) == pytest.approx((-24.958239, -53.484772), abs=1e-6)


def _geo_para_utm(lat, lon, fuso):
    """a conta de ida (Snyder), para conferir a volta do local_obra pela ida e volta"""
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f); ep2 = e2 / (1 - e2)
    fi, la = math.radians(lat), math.radians(lon - ((fuso - 1) * 6 - 180 + 3))
    n = a / math.sqrt(1 - e2 * math.sin(fi) ** 2); t = math.tan(fi) ** 2; c = ep2 * math.cos(fi) ** 2; A = math.cos(fi) * la
    m = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * fi - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * fi)
             + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * fi) - (35 * e2 ** 3 / 3072) * math.sin(6 * fi))
    x = k0 * n * (A + (1 - t + c) * A ** 3 / 6 + (5 - 18 * t + t ** 2 + 72 * c - 58 * ep2) * A ** 5 / 120) + 500_000
    y = k0 * (m + n * math.tan(fi) * (A ** 2 / 2 + (5 - t + 9 * c + 4 * c ** 2) * A ** 4 / 24
                                       + (61 - 58 * t + t ** 2 + 600 * c - 330 * ep2) * A ** 6 / 720))
    return x, y + (10_000_000 if lat < 0 else 0)


@pytest.mark.parametrize("lat,lon,fuso", [(-24.958239, -53.484772, 22), (-25.4284, -49.2733, 22), (-23.5505, -46.6333, 23),
                                          (-3.7319, -38.5267, 24)])
def test_utm_ida_e_volta(lat, lon, fuso):
    x, y = _geo_para_utm(lat, lon, fuso)
    la, lo = L.utm_para_geo(x, y, fuso)
    assert _dist_m((lat, lon), (la, lo)) < 0.01                       # menos de 1 cm


@pytest.mark.parametrize("texto,fuso", [("X: %.4f, Y: %.4f", 22), ("%.4f %.4f 22S", 22), ("E %.0f N %.0f fuso 22", 22)])
def test_coordenada_utm_do_geoportal(texto, fuso):
    x, y = _geo_para_utm(-24.958239, -53.484772, fuso)
    c = L.coordenada_do_texto(texto % (x, y))
    assert _dist_m(c, (-24.958239, -53.484772)) < 1.0                 # o arredondamento do texto
    assert L.coordenada_do_texto("677000 7184000 23K")[1] == pytest.approx(-43.24, abs=0.01)   # o fuso escrito vale
    assert L.coordenada_do_texto("Rua Maranhão 3411, Cascavel") is None


def test_altura_da_imagem():
    """A cota da imagem (o Mercado Conceito com subsolo, 20/10: a imagem no fundo do subsolo deixava a fundação voando)."""
    base = {"lat": -24.9, "lon": -53.4, "ponto": [0, 0]}
    assert "cota" not in L.validar(base)                                   # sem ela: no pé da obra
    assert L.validar(dict(base, cota=0))["cota"] == 0                      # o 0,00 vale (não é "sem cota")
    assert L.validar(dict(base, cota="1500"))["cota"] == 1500
    assert "cota" not in L.validar(dict(base, cota=None)) and "cota" not in L.validar(dict(base, cota=""))
    with pytest.raises(L.ErroTerreno, match="altura"):
        L.validar(dict(base, cota="abc"))


def test_transparencia_da_imagem():
    base = {"lat": -24.9, "lon": -53.4, "ponto": [0, 0]}
    assert "transparencia" not in L.validar(base) and "transparencia" not in L.validar(dict(base, transparencia=0))
    assert L.validar(dict(base, transparencia=0.4))["transparencia"] == 0.4
    assert L.validar(dict(base, transparencia=2))["transparencia"] == 0.9            # nunca some de todo
    assert "transparencia" not in L.validar(dict(base, transparencia="x"))


# ------------------------------------------------------------------ o terreno no IFC (21/10, a PRATI CD para o cliente)

PRATI = {"lat": -24.6224047, "lon": -53.71357133, "ponto": [72587.4, 44714.1], "norte": 86.0}


@pytest.mark.parametrize("desloc", [(0, 0, 0), (7_250_000_000.0, 245_000_000.0, 0)])   # o sítio de um IFC importado
def test_conversao_do_mapa_do_ifc(desloc):
    """Um ponto do modelo pela IfcMapConversion (o que o outro programa faz) cai na UTM do mesmo ponto pela amarração —
    a menos de 2 cm até 150 m da obra; o sítio em graus e o norte verdadeiro também."""
    import tempfile
    from PIL import Image
    d = tempfile.mkdtemp()
    Image.new("RGB", (8, 8), (90, 130, 78)).save(d + "/i.jpg")
    t = dict(PRATI, cota=0)
    reg = L.regiao(t, [0, 0, 146000, 91000])
    tr = L.para_ifc(t, {k: reg[k] for k in ("x0", "y0", "x1", "y1")}, d + "/i.jpg", desloc, 0)
    m = tr["mapa"]
    assert m["nome"] == "EPSG:31982" and m["zona"] == "22S"
    assert abs(m["escala"] / 0.001 - 1.0005) < 0.0003                     # o fator de escala da UTM a 275 km do meridiano
    for x, y in ((0, 0), (146000, 0), (146000, 91000), (72000, 45000), (-20000, 130000)):
        # o mundo do IFC: deslocamento + modelo; a conversão do IFC4 (giro pelo eixo X no mapa e a escala)
        wx, wy = desloc[0] + x, desloc[1] + y
        e = m["leste"] + m["escala"] * (wx * m["abscissa"] - wy * m["ordenada"])
        n = m["norte"] + m["escala"] * (wx * m["ordenada"] + wy * m["abscissa"])
        e2, n2, _f, _s = L.geo_para_utm(*L.modelo_para_geo(t, x, y), 22)
        assert math.hypot(e - e2, n - n2) < 0.02, (x, y, e - e2, n - n2)
    assert tr["lat_sitio"] == pytest.approx(L.modelo_para_geo(t, 0, 0)[0])
    assert tr["norte"] == pytest.approx((-math.sin(math.radians(86)), math.cos(math.radians(86))))
    # a placa: os cantos da imagem, quadrada no chão e na altura escolhida
    c = tr["cantos"]
    assert all(p[2] == 0 for p in c)
    lado1, lado2 = math.dist(c[0][:2], c[1][:2]), math.dist(c[0][:2], c[3][:2])
    m_, n_ = L._raios(t["lat"])
    assert abs(lado2 / lado1 - m_ / n_) < 0.001       # o quadrado do Mercator no chão: o norte–sul encurta M/N (−0,55 %)


def test_ifc_com_o_terreno_e_valido(tmp_path):
    """O IFC com o terreno: o sítio em latitude e longitude, o norte verdadeiro no contexto, a IfcMapConversion para a UTM
    SIRGAS 2000, a placa (IfcGeographicElement TERRAIN) na camada "Terreno" com a imagem dentro (IfcBlobTexture) e o nome
    do arquivo (IfcImageTexture) — válido pelo ifcopenshell quando ele está instalado."""
    from PIL import Image
    from ifc import exportar as E
    from nucleo3d.modelo import Documento
    from test_pacote_celular import _modelo
    Image.effect_noise((64, 64), 60).convert("RGB").save(tmp_path / "i.jpg")
    t = dict(PRATI, ponto=[5000, 3000], cota=0)
    reg = L.regiao(t, [0, 0, 10000, 6000])
    tr = L.para_ifc(t, {k: reg[k] for k in ("x0", "y0", "x1", "y1")} | {"fonte": "Esri", "atribuicao": "Imagem: Esri"},
                    str(tmp_path / "i.jpg"))
    padrao = open(E.exportar(Documento.de_dict(_modelo()), str(tmp_path / "p.ifc"), terreno=tr), encoding="ascii").read()
    assert "IFCBLOBTEXTURE" not in padrao and "IFCIMAGETEXTURE" not in padrao   # o Trimble não abria com textura (21/10)
    caminho = E.exportar(Documento.de_dict(_modelo()), str(tmp_path / "t.ifc"), terreno=dict(tr, textura="dentro"))
    texto = open(caminho, encoding="ascii").read()
    assert texto.count("IFCTRIANGULATEDFACESET(") >= 2                 # o mosaico: um por cor (o Trimble não mostra textura)
    for ent in ("IFCMAPCONVERSION(", "IFCPROJECTEDCRS('EPSG:31982'", "IFCGEOGRAPHICELEMENT(", ".TERRAIN.", "IFCBLOBTEXTURE(",
                "IFCIMAGETEXTURE(", "IFCINDEXEDTRIANGLETEXTUREMAP(", "IFCPRESENTATIONLAYERWITHSTYLE('Terreno'"):
        assert ent in texto, ent
    assert (tmp_path / "i.jpg").read_bytes().hex().upper() in texto        # a imagem inteira dentro do arquivo
    sem = open(E.exportar(Documento.de_dict(_modelo()), str(tmp_path / "s.ifc")), encoding="ascii").read()
    assert "IFCMAPCONVERSION" not in sem and "IFCGEOGRAPHICELEMENT" not in sem   # sem o terreno, como sempre foi
    ifcopenshell = pytest.importorskip("ifcopenshell")
    import ifcopenshell.validate
    f = ifcopenshell.open(caminho)
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log)
    assert not log.statements, log.statements[:3]
    site = f.by_type("IfcSite")[0]
    assert site.RefLatitude[0] == -24 and site.RefLongitude[0] == -53
    assert f.by_type("IfcMapConversion")[0].TargetCRS.Name == "EPSG:31982"


def test_mosaico_de_cores_do_terreno():
    """O Trimble Connect não mostra textura de IFC (21/10: "estou testando o IFC exportado com o terreno no trimble e não
    aparece"): a placa vira um mosaico de quadrados com as cores da imagem, um IfcTriangulatedFaceSet por cor — a metade
    de cima da imagem vermelha e a de baixo azul saem no norte e no sul da placa, nessas cores."""
    import io
    from PIL import Image
    im = Image.new("RGB", (64, 64), (0, 0, 220))
    im.paste((220, 0, 0), (0, 0, 64, 32))                       # em cima (o norte) vermelho
    b = io.BytesIO()
    im.save(b, "PNG")
    cantos = [(0, 0, 0), (64000, 0, 0), (64000, 64000, 0), (0, 64000, 0)]
    m = L._mosaico(b.getvalue(), cantos, lado=16, cores=8, grosso=4)
    assert m["n"] == 16 and len(m["uv"]) == len(m["pontos"])
    pontos = m["pontos"]

    def area(t):
        (ax, ay, _), (bx, by, _), (cx, cy, _) = (pontos[i - 1] for i in t)
        return ((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2
    tris = [t for g in m["grupos"] for t in g["triangulos"]]
    assert all(area(t) > 0 for t in tris)                      # todos virados para cima
    assert abs(sum(area(t) for t in tris) - 64000 ** 2) < 1    # a placa inteira coberta, sem sobrar nem faltar
    assert len(tris) == 2 * 16                                  # cada linha de uma cor só vira uma faixa (16 linhas)
    for g in m["grupos"]:
        ys = [pontos[i - 1][1] for t in g["triangulos"] for i in t]
        r, _g, bl = g["cor"]
        if r > 150:
            assert min(ys) >= 32000 - 1                         # o vermelho só na metade norte
        if bl > 150:
            assert max(ys) <= 32000 + 1                         # o azul só na metade sul


def test_mosaico_fino_na_obra_e_grosso_em_volta():
    """"Abriu, porém a resolução do terreno ficou muito baixa" (21/10, a PRATI no Trimble): na obra (e 30 m em volta) o
    mosaico tem a resolução da imagem; fora, quadrados 4 × maiores — a foto nítida onde importa sem passar de algumas
    centenas de milhares de triângulos."""
    import io
    import random
    from PIL import Image
    r = random.Random(3)
    im = Image.new("RGB", (64, 64))
    im.putdata([(r.randrange(256), r.randrange(256), r.randrange(256)) for _ in range(64 * 64)])   # ruído: nada se junta
    b = io.BytesIO()
    im.save(b, "PNG")
    cantos = [(0, 0, 0), (64000, 0, 0), (64000, 64000, 0), (0, 64000, 0)]
    m = L._mosaico(b.getvalue(), cantos, foco=(16000, 16000, 32000, 32000), lado=64, cores=256, grosso=4)
    pontos = m["pontos"]
    lados = {}
    for g in m["grupos"]:
        for t in g["triangulos"]:
            xs = [pontos[i - 1][0] for i in t]
            ys = [pontos[i - 1][1] for i in t]
            meio = (sum(xs) / 3, sum(ys) / 3)
            dentro = 16000 <= meio[0] <= 32000 and 16000 <= meio[1] <= 32000
            lados.setdefault(dentro, set()).add(round(max(ys) - min(ys)))
    assert lados[True] == {1000}                                # na obra: a célula da imagem (1 m)
    assert lados[False] == {4000}                               # em volta: 4 × maior
    tris = sum(len(g["triangulos"]) for g in m["grupos"])
    assert tris < 2 * 64 * 64 / 2                               # bem menos que a imagem inteira na resolução fina


def test_bloco_que_falha_e_pedido_de_novo(tmp_path, monkeypatch):
    """O servidor da prefeitura às vezes não entrega um bloco na hora (Toledo, 21/10: um quadrado cinza na imagem da
    PRATI): o bloco é pedido de novo, até três vezes, antes de ficar cinza."""
    import io as _io
    from PIL import Image
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    b = _io.BytesIO()
    Image.effect_noise((256, 256), 60).convert("RGB").save(b, "PNG")
    png = b.getvalue()
    pedidos = {}

    def instavel(url):                                       # cada bloco falha na primeira vez
        pedidos[url] = pedidos.get(url, 0) + 1
        if pedidos[url] == 1:
            raise OSError("tempo esgotado")
        return png
    g, s = _gerente(tmp_path)
    L.gravar(g, s, {"lat": CASCAVEL[0], "lon": CASCAVEL[1], "ponto": [0, 0], "norte": 0, "fonte": "cascavel"})
    L.baixar_imagem(g, s, {"caixa": [-10000, -10000, 10000, 10000]}, baixar=instavel)
    from PIL import ImageStat
    im = Image.open(L.os.path.join(g.pasta(s), "terreno", "imagem.jpg")).convert("RGB")
    cinza = sum(1 for x in range(0, im.size[0], 64) for y in range(0, im.size[1], 64)
                if max(ImageStat.Stat(im.crop((x, y, x + 32, y + 32))).stddev) < 3)
    assert cinza == 0 and all(n == 2 for n in pedidos.values())
