# -*- coding: utf-8 -*-
"""Caminho inverso: desenho 2D com peças do catálogo vira modelo 3D (e IFC)."""
import math
import os
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo.base import ErroDeDados                     # noqa: E402
from nucleo2d.desenho import Desenho, Linha, Polilinha, Texto   # noqa: E402
from nucleo3d import de_desenho                         # noqa: E402


def _tesoura(vao=12000.0, altura=1200.0, paineis=6) -> Desenho:
    d = Desenho(nome="TESOURA T1")
    d.metadados["pecas_por_camada"] = {
        "BANZOS": {"perfil": "Ue 150×60×20×2,65", "papel": "banzo", "aco": "CIVIL 300"},
        "DIAGONAIS": {"perfil": "L 50×2,25 (FF)", "papel": "diagonal", "aco": "CIVIL 300"},
        "MONTANTES": {"perfil": "L 50×2,25 (FF)", "papel": "montante", "aco": "CIVIL 300"},
    }
    dx = vao / paineis
    inf = [(i * dx, 0.0) for i in range(paineis + 1)]
    sup = [(i * dx, altura) for i in range(paineis + 1)]
    d.add(Linha(camada="BANZOS", a=inf[0], b=inf[-1]))
    d.add(Linha(camada="BANZOS", a=sup[0], b=sup[-1]))
    for i in range(paineis + 1):
        d.add(Linha(camada="MONTANTES", a=inf[i], b=sup[i]))
    for i in range(paineis):
        d.add(Linha(camada="DIAGONAIS", a=inf[i], b=sup[i + 1]))
    d.add(Linha(camada="COTAS", a=(0.0, -500.0), b=(vao, -500.0)))      # anotação
    d.add(Texto(camada="TEXTO", posicao=(0.0, -800.0), texto="T1"))
    return d


def test_conferir():
    info = de_desenho.conferir_desenho(_tesoura())
    assert info["barras"] == 15 and info["com_peca"] == 15
    assert info["anotacao"] == 1               # a cota; o texto não tem trecho reto
    assert info["perfis_desconhecidos"] == []
    assert info["papeis"] == {"banzo": 2, "montante": 7, "diagonal": 6}
    assert info["comprimento_m"] > 40


def test_modelo_com_marcas_por_peca():
    doc = de_desenho.modelo_do_desenho(_tesoura(), plano="frente", repeticoes=3,
                                       espacamento=5000.0, conjunto="M")
    assert len(doc.barras) == 45
    # conjunto por cópia e posição por perfil+comprimento, como num IFC de fábrica
    conjuntos = {b.atributos["marcas"]["conjunto"] for b in doc.barras}
    assert conjuntos == {"M1", "M2", "M3"}
    posicoes = {b.atributos["marcas"]["posicao"] for b in doc.barras}
    assert len(posicoes) == 3                   # banzo, montante e diagonal
    por_posicao = {}
    for b in doc.barras:
        por_posicao.setdefault(b.atributos["marcas"]["posicao"], set()).add(
            (b.perfil, round(b.comprimento)))
    assert all(len(v) == 1 for v in por_posicao.values()), "posição com peças diferentes"
    # cada peça leva perfil, aço, papel e camada do 3D
    banzo = next(b for b in doc.barras if b.papel == "banzo")
    assert banzo.perfil == "Ue 150×60×20×2,65" and banzo.aco == "CIVIL 300"
    assert banzo.camada == "Vigas" and banzo.atributos["peso_kg"] > 0
    assert banzo.atributos["origem"]["desenho"] == "TESOURA T1"
    # o desenho fica em pé: X do desenho → X, Y → Z, cópias ao longo de Y
    (x0, y0, z0), (x1, y1, z1) = doc.caixa()
    assert (x1 - x0) == pytest.approx(12000, abs=1) and (z1 - z0) == pytest.approx(1200, abs=1)
    assert (y1 - y0) == pytest.approx(10000, abs=1)


@pytest.mark.parametrize("plano, eixos", [
    ("frente", ((12000, 0), (0, 1), (1200, 2))),
    ("topo", ((12000, 0), (1200, 1), (0, 2))),
    ("lado", ((0, 0), (12000, 1), (1200, 2))),
])
def test_planos(plano, eixos):
    doc = de_desenho.modelo_do_desenho(_tesoura(), plano=plano, repeticoes=1)
    caixa = doc.caixa()
    for medida, eixo in eixos:
        assert (caixa[1][eixo] - caixa[0][eixo]) == pytest.approx(medida, abs=1)


def test_peca_da_entidade_vence_a_camada():
    d = _tesoura()
    linha = next(e for e in d.entidades.values() if e.camada == "DIAGONAIS")
    linha.atributos = {"peca": {"perfil": "L 2\"×1/4\"", "papel": "diagonal", "aco": "ASTM A36"}}
    doc = de_desenho.modelo_do_desenho(d, repeticoes=1)
    perfis = {b.perfil for b in doc.barras if b.papel == "diagonal"}
    assert perfis == {"L 50×2,25 (FF)", 'L 2"×1/4"'}


def test_polilinha_vira_uma_barra_por_lado():
    d = Desenho(nome="P")
    d.metadados["pecas_por_camada"] = {"BANZOS": {"perfil": "Ue 200×75×20×2,65", "papel": "banzo"}}
    d.add(Polilinha(camada="BANZOS", vertices=[(0, 0), (3000, 500), (6000, 0)]))
    doc = de_desenho.modelo_do_desenho(d, repeticoes=1)
    assert len(doc.barras) == 2
    assert all(b.perfil == "Ue 200×75×20×2,65" for b in doc.barras)


def test_acrescenta_ao_modelo_existente():
    doc = de_desenho.modelo_do_desenho(_tesoura(), repeticoes=1, conjunto="M")
    n = len(doc.entidades)
    doc = de_desenho.modelo_do_desenho(_tesoura(), repeticoes=1, conjunto="N",
                                       origem=(0.0, 8000.0, 0.0), doc=doc)
    assert len(doc.entidades) == 2 * n
    assert {"M", "N"} <= {b.atributos["marcas"]["conjunto"] for b in doc.barras}


def _com_chapa() -> Desenho:
    from nucleo2d.desenho import Circulo
    d = Desenho(nome="NÓ")
    d.metadados["pecas_por_camada"] = {
        "BANZOS": {"perfil": "Ue 200×75×20×2,65", "papel": "banzo", "aco": "CIVIL 300"},
        "CHAPAS": {"perfil": 'CH 9,53 mm (3/8")', "papel": "chapa", "aco": "ASTM A36"},
    }
    d.add(Linha(camada="BANZOS", a=(0.0, 0.0), b=(6000.0, 0.0)))
    d.add(Polilinha(camada="CHAPAS", fechada=True,
                    vertices=[(1400.0, -100.0), (1700.0, -100.0), (1700.0, 100.0), (1400.0, 100.0)]))
    for x in (1450.0, 1650.0):
        for y in (-50.0, 50.0):
            d.add(Circulo(camada="CHAPAS", centro=(x, y), raio=8.5))
    d.add(Circulo(camada="CHAPAS", centro=(3000.0, 0.0), raio=8.5))     # fora da chapa
    return d


def test_chapa_de_no_com_furos():
    d = _com_chapa()
    info = de_desenho.conferir_desenho(d)
    assert info["chapas"] == 1 and info["barras"] == 1
    assert info["area_chapas_m2"] == pytest.approx(0.06, abs=0.001)

    doc = de_desenho.modelo_do_desenho(d, plano="frente", repeticoes=2, espacamento=5000.0)
    assert len(doc.chapas) == 2 and len(doc.barras) == 2
    ch = doc.chapas[0]
    assert ch.espessura == pytest.approx(9.53)
    assert len(ch.furos) == 4, "só os círculos dentro do contorno viram furos"
    assert all(f["diametro"] == pytest.approx(17.0) for f in ch.furos)
    assert ch.aco == "ASTM A36" and ch.camada == "Chapas"
    assert ch.atributos["marcas"]["posicao"].startswith("P")
    assert ch.atributos["peso_kg"] > 0
    # a chapa fica no plano do desenho, em pé
    assert abs(ch.normal[1]) > 0.99


def test_detalhamento_de_modelo_desenhado():
    """Um modelo desenhado tem de detalhar como um importado (barras viram sólidos)."""
    from nucleo2d.detalhar import detalhar
    doc = de_desenho.modelo_do_desenho(_com_chapa(), repeticoes=2, espacamento=5000.0)
    r = detalhar(doc, grupos=["chapas", "barras"], rotular=True)
    assert r["peso_total"] > 0
    marcas = {p["marca"] for p in r["posicoes"]}
    assert len(marcas) == len(r["posicoes"])
    chapa = next(p for p in r["posicoes"] if p["classe"] == "Chapa")
    assert chapa["quantidade"] == 2 and chapa["espessura"] == pytest.approx(9.5, abs=0.1)
    assert chapa["comprimento"] == 300 and chapa["largura"] == 200
    barra = next(p for p in r["posicoes"] if p["classe"] != "Chapa")
    assert barra["comprimento"] == 6000


def test_erros():
    with pytest.raises(ErroDeDados):
        de_desenho.modelo_do_desenho(Desenho(nome="vazio"))          # nada com peça
    d = _tesoura()
    d.metadados["pecas_por_camada"]["BANZOS"]["perfil"] = "Perfil Inexistente 999"
    with pytest.raises(ErroDeDados):
        de_desenho.modelo_do_desenho(d)
    with pytest.raises(ErroDeDados):
        de_desenho.modelo_do_desenho(_tesoura(), plano="diagonal")


def test_ifc_leva_as_marcas(tmp_path):
    """O IFC exportado tem de levar posição, conjunto e perfil — e devolvê-los na volta."""
    from ifc import exportar, importar
    doc = de_desenho.modelo_do_desenho(_tesoura(), repeticoes=2, espacamento=5000.0, conjunto="M")
    caminho = str(tmp_path / "tesoura.ifc")
    exportar.exportar(doc, caminho, projeto_nome="Tesoura desenhada")
    volta = importar.importar(caminho)
    assert len(volta.barras) == len(doc.barras)
    marcas = {(b.atributos.get("marcas") or {}).get("posicao") for b in volta.barras}
    conjuntos = {(b.atributos.get("marcas") or {}).get("conjunto") for b in volta.barras}
    assert None not in marcas and conjuntos == {"M1", "M2"}
    assert {b.papel for b in volta.barras} >= {"banzo"}


def test_calculo_aceita_modelo_desenhado():
    """O modelo desenhado tem de servir ao cálculo como um importado de fábrica."""
    from nucleo3d import calculo_ifc
    doc = de_desenho.modelo_do_desenho(_tesoura(), plano="frente", repeticoes=3,
                                       espacamento=5000.0, conjunto="M")
    nomes = {"tipos": {}, "tipos_conjuntos": {"M1 / M2 / M3": "tesoura"},
             "posicoes": {}, "conjuntos": {"M1 / M2 / M3": "T1"}, "ifc": {}, "ifc_conjuntos": {}}
    g = calculo_ifc.geometria_do_modelo(doc, nomes)
    assert g["tesouras"] == 3 and g["vao_m"] == pytest.approx(12.0, abs=0.1)
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0})
    assert r["ok"] and r["resumo"]["tesouras"] == 3
    assert r["resumo"]["peso_verificado_kg"] > 0
    assert {"banzo", "diagonal", "montante"} & {e["tipo"] for e in r["elementos"].values()}
