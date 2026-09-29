# -*- coding: utf-8 -*-
"""Eixos da obra (nucleo3d.eixos): numerados nas tesouras e com letra nos chumbadores,
identificados de um modelo sintético; as linhas em 3D; a validação do que o usuário grava;
as plantas de localização e de chumbação com os eixos (bolinhas, nomes, cotas) e a
referência 2D que leva um ponto do papel de volta ao 3D."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Solido                        # noqa: E402
from nucleo3d import eixos as E                                      # noqa: E402
from nucleo2d.desenho import Circulo, Texto, Cota                    # noqa: E402
from nucleo2d.detalhe.conjuntos import desenho_de_localizacao, desenho_de_chumbacao   # noqa: E402


def _caixa(x0, y0, z0, x1, y1, z1, nome, posicao, conjunto=""):
    v = [(x, y, z) for z in (z0, z1) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return Solido(nome=nome, camada="Vigas", vertices=v, faces=f,
                  atributos={"tipo_ifc": "IfcBeam", "marcas": {"posicao": posicao, "conjunto": conjunto or posicao, "perfil": nome}})


def _modelo():
    """3 tesouras (barras ao longo de x, em y = 0, 6000, 12000) apoiadas em chumbadores nas
    pontas (x = 0 e x = 15000): eixos 1, 2, 3 nas tesouras e A, B nos apoios."""
    doc = Documento(nome="eixos")
    for k, y in enumerate((0.0, 6000.0, 12000.0)):
        conj = "M%d" % (k + 1)
        doc.add(_caixa(0, y - 50, 6000, 15000, y + 50, 6100, "U100X50X3.04", "P1", conj))       # banzo
        doc.add(_caixa(0, y - 50, 7000, 15000, y + 50, 7100, "U100X50X3.04", "P2", conj))
        for x in (0.0, 15000.0):
            doc.add(_caixa(x - 30, y - 30, 5500, x + 30, y + 30, 5900, "FE RED 3/4''", "M9"))   # chumbador
    nomes = {"tipos": {"M9": "chumbador", "P1": "barra", "P2": "barra"},
             "tipos_conjuntos": {"M1": "tesoura", "M2": "tesoura", "M3": "tesoura"},
             "ifc": {"M9": "CB1", "P1": "B.1", "P2": "B.2"}}
    return doc, nomes


def test_identifica_numeros_nas_tesouras_e_letras_nos_apoios():
    doc, nomes = _modelo()
    ex = E.identificar_eixos(doc, nomes)
    assert abs(abs(ex["eixo_g"][1]) - 1.0) < 1e-3                       # o galpão corre em y
    assert [n["nome"] for n in ex["numeros"]] == ["1", "2", "3"]
    assert [round(n["pos"]) for n in ex["numeros"]] == [0, 6000, 12000]
    assert [n["nome"] for n in ex["letras"]] == ["A", "B"] and ex["fonte_letras"] == "chumbadores"
    xs = sorted(abs(n["pos"]) for n in ex["letras"])
    assert [round(x) for x in xs] == [0, 15000]
    assert abs(ex["z_base"] - 5500.0) < 1e-6
    segs = E.segmentos(ex)
    assert len(segs) == 5 and {s["tipo"] for s in segs} == {"numero", "letra"}
    # o eixo numerado corre atravessado: do primeiro ao último eixo com letra, mais a folga
    s1 = next(s for s in segs if s["nome"] == "1")
    assert abs(math.dist(s1["a"], s1["b"]) - (15000 + 2 * E.FOLGA_EIXO)) < 1.0


def test_trelicas_pela_geometria_sem_a_categoria_tesouras():
    """O depósito químico (29/09): o IFC sem a categoria TESOURAS — as treliças vêm como conjunto
    comum. Os eixos numerados saem das treliças pela geometria (plano vertical com altura), sem
    inclinação; os com letra só das chapas de apoio do nível de baixo (as deitadas dos nós, mais
    acima, davam uma letra cada); o eixo vai ao centro do apoio; a terça no caimento não é treliça;
    o pilar do oitão ganha a sua letra."""
    doc = Documento(nome="deposito")
    xs = (0.0, 9000.0, 14000.0)
    for k, x in enumerate(xs):
        conj = "M%d" % (k + 1)
        doc.add(_caixa(x - 40, 0, 5000, x + 40, 20000, 5100, "U100", "P1", conj))            # banzo de baixo
        doc.add(_caixa(x - 40, 0, 6400, x + 40, 20000, 6500, "U100", "P2", conj))            # banzo de cima
        for y in (2000.0, 6000.0, 10000.0, 14000.0, 18000.0):
            doc.add(_caixa(x - 40, y - 40, 5100, x + 40, y + 40, 6400, "U75", "P3", conj))   # montantes
            doc.add(_caixa(x - 60, y - 100, 5700, x + 60, y + 100, 5708, "CH11", "P4", conj))  # chapa deitada no nó
        for y in (2500.0, 17500.0):
            doc.add(_caixa(x + 20 - 105, y - 200, 4992, x + 20 + 105, y + 200, 5000, "CH17", "P5", "C%d" % k))  # apoio
    doc.add(_caixa(14020 - 105, 10000 - 113, 4992, 14020 + 105, 10000 + 113, 5000, "CH23", "P5", "C9"))  # oitão
    for k, y in enumerate((1000.0, 5000.0, 9000.0)):          # a terça no plano inclinado, em conjunto
        doc.add(_caixa(4000, y - 40, 6500 + y * 0.1, 12000, y + 40, 6600 + y * 0.1, "U150", "P6", "T%d" % k))
    nomes = {"tipos": {"P1": "parte", "P2": "parte", "P3": "parte", "P4": "chapa", "P5": "chapa", "P6": "barra"},
             "tipos_conjuntos": {"M1": "conjunto", "M2": "conjunto", "M3": "conjunto"}}
    ex = E.identificar_eixos(doc, nomes)
    assert ex["eixo_g"] == [1.0, 0.0]
    assert [round(n["pos"]) for n in ex["numeros"]] == [20, 9020, 14020]
    assert [round(n["pos"]) for n in ex["letras"]] == [2500, 10000, 17500] and ex["fonte_letras"] == "chapas de base"
    assert abs(ex["z_base"] - 4992.0) < 1e-6


def test_de_dict_valida_e_ordena():
    assert E.de_dict(None) is None and E.de_dict({"eixo_g": [0, 0]}) is None
    d = E.de_dict({"eixo_g": [0, 2], "numeros": [{"nome": "2", "pos": 6000}, {"nome": "1", "pos": 0}], "letras": [], "z_base": 10})
    assert d["eixo_g"] == [0.0, 1.0] and d["perp_g"] == [-1.0, 0.0]
    assert [n["nome"] for n in d["numeros"]] == ["1", "2"] and d["origem"] == "usuario"


def test_plantas_com_eixos_e_referencia_2d():
    doc, nomes = _modelo()
    ex = E.identificar_eixos(doc, nomes)
    pecas = [e for e in doc.entidades.values() if isinstance(e, Solido)]
    d = desenho_de_localizacao(doc, pecas, eixos=ex, nomes_producao=nomes, nomes=nomes["ifc"])
    eixo = [e for e in d.entidades.values() if e.camada == "EIXO"]
    assert sum(1 for e in eixo if isinstance(e, Circulo)) == 10                # 5 eixos × 2 bolinhas
    nomes_bolinhas = sorted(e.texto for e in eixo if isinstance(e, Texto))
    assert nomes_bolinhas == ["1", "1", "2", "2", "3", "3", "A", "A", "B", "B"]
    assert any(isinstance(e, Cota) for e in d.entidades.values())
    topo = next(v for v in d.vistas if v["tipo"] == "topo")
    assert topo.get("ref2d") and d.metadados.get("eixos")
    # a bolinha do eixo 1 volta ao 3D em cima da linha do eixo 1 (a inversão que o CAD usa)
    from nucleo2d.vistas import Vista
    u, v, w = Vista(origem=tuple(topo["origem"]), normal=tuple(topo["normal"]), acima=tuple(topo["acima"])).eixos()
    t1 = next(e for e in eixo if isinstance(e, Texto) and e.texto == "1")
    c1 = min((e for e in eixo if isinstance(e, Circulo)), key=lambda e: math.dist(e.centro, t1.posicao))
    X, Y = c1.centro
    lu, lv = X - topo["canto"][0] + topo["ref2d"][0], Y - topo["canto"][1] + topo["ref2d"][1]
    q = tuple(topo["origem"][i] + u[i] * lu + v[i] * lv for i in range(3))
    g = q[0] * ex["eixo_g"][0] + q[1] * ex["eixo_g"][1]
    assert abs(g - ex["numeros"][0]["pos"]) < 5.0, (g, ex["numeros"][0]["pos"])
    # planta de chumbação: os 6 chumbadores rotulados, os eixos e a referência 2D
    ch = desenho_de_chumbacao(doc, pecas, nomes, eixos=ex, nomes=nomes["ifc"])
    assert sum(1 for e in ch.entidades.values() if isinstance(e, Texto) and e.texto == "CB1") == 6
    assert sum(1 for e in ch.entidades.values() if e.camada == "EIXO" and isinstance(e, Circulo)) == 10
    assert ch.vistas and ch.vistas[0]["tipo"] == "topo" and ch.vistas[0].get("ref2d")
    assert ch.metadados["detalhamento"]["grupo"] == "chumbacao"


def test_br_com_bitola_e_barra_redonda():
    """"BR3/4''" (o chumbador do depósito químico, 29/09) é barra redonda — sem isso o chumbador não
    era achado e a chumbação tomava as chapas deitadas por chumbador; "BRACE"/"BRISE" não."""
    from saida.detalhamento import _eh_redonda
    from nucleo2d.detalhe.base import _eh_redonda_perfil
    for f in (_eh_redonda, _eh_redonda_perfil):
        assert f("BR3/4''") and f("BR 5/8''") and f("FE RED 1/2''")
        assert not f("BRACE L2") and not f("BRISE 100") and not f("W250X32.70")


def test_chumbador_de_parede_na_chapa_em_pe():
    """A tesoura do eixo 1 do depósito químico (29/09) presa na parede: chapa em pé na face do concreto
    com barras redondas curtas deitadas atravessando, quase todas do lado de dentro — é chumbamento; a
    mesma barra centrada na chapa (passa dos dois lados por igual) não é."""
    from nucleo2d.detalhe.montagens import grupos_montados
    chapa = _caixa(160, 4900, 5250, 173, 5150, 5500, "PLATE 268x249x13", "P1", "M1")
    chapa.atributos["tipo_ifc"] = "IfcPlate"
    barras = [_caixa(0, y - 8, z - 8, 200, y + 8, z + 8, "BR5/8''", "P2", "M1") for y in (4925.0, 5075.0) for z in (5290.0, 5430.0)]
    gs = grupos_montados([chapa] + barras, (), lambda m: m)
    assert [g["tipo"] for g in gs] == ["chumbamento"] and len(gs[0]["pecas"]) == 5
    centrada = [_caixa(66, y - 8, 5282, 266, y + 8, 5298, "BR5/8''", "P2", "M1") for y in (4925.0, 5075.0)]
    assert not grupos_montados([chapa] + centrada, (), lambda m: m)
