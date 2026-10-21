# -*- coding: utf-8 -*-
"""Os painéis solares em cima da telha (nucleo3d/paineis_solares.py; Posto V2, 21/10/2026: a PAGINAÇÃO DOS PAINÉIS
SOLARES da folha 12, 350 placas 1200 × 2450 mm)."""
from nucleo3d.modelo import Barra, Documento
from nucleo3d import telhas_cobertura as T
from nucleo3d import paineis_solares as PS


def _terca(doc, x, z, y0=0.0, y1=6000.0):
    b = Barra(inicio=(x, y0, z), fim=(x, y1, z), perfil="U 100×40×2,65 (FF)", papel="terça", camada="Terças")
    b.atributos = {"origem": {"sigla": "TC1"}}
    doc.add(b)


def _duas_aguas():
    """cumeeira em x 4.200: a água da esquerda sobe 5 % até ela, a da direita desce 5 %"""
    doc = Documento()
    for i in range(4):
        _terca(doc, i * 1400.0, 7000.0 + i * 70.0)
    for i in range(4):
        _terca(doc, 4400.0 + i * 1400.0, 7210.0 - i * 70.0)
    T.lancar(doc)
    return doc


def _placa(x, y, comp=2450.0, larg=1200.0):
    return [(x, y), (x + comp, y), (x + comp, y + larg), (x, y + larg)]


def test_placa_assenta_no_plano_da_telha():
    doc = _duas_aguas()
    r = PS.lancar(doc, [_placa(500.0, 1000.0)])
    assert r["placas"] == 1 and r["apontamentos"] == []
    p = [s for s in doc.solidos if s.camada == PS.CAMADA][0]
    base = p.vertices[:4]
    # na inclinação da água (5 %) e acima da crista da telha mais o trilho
    assert abs((base[1][2] - base[0][2]) / 2450.0 - 0.05) < 0.002
    telhas = [s for s in doc.solidos if (s.atributos or {}).get("telha_lancada") and s.camada == "Telhas"]
    def crista_em(x0):
        return max(v[2] for s in telhas for v in s.vertices if abs(v[0] - x0) < 1.0 and v[0] < 4300.0)
    for x, y, z in base:
        x0, x1 = 1400.0 * (x // 1400.0), 1400.0 * (x // 1400.0 + 1)
        crista = crista_em(x0) + (crista_em(x1) - crista_em(x0)) * (x - x0) / 1400.0
        assert z >= crista + PS.ALTURA_TRILHO - 1.0 and z <= crista + PS.ALTURA_TRILHO + 15.0
    # o relançamento tira as de antes
    PS.lancar(doc, [_placa(500.0, 1000.0), _placa(500.0, 2300.0)])
    assert len([s for s in doc.solidos if s.camada == PS.CAMADA]) == 2


def test_apontamentos_da_placa():
    doc = _duas_aguas()
    r = PS.lancar(doc, [_placa(3000.0, 1000.0),          # em cima da cumeeira (x 4.200–4.400)
                        _placa(500.0, 5500.0),           # passa da cobertura (y até 6.000)
                        _placa(500.0, 1000.0), _placa(1000.0, 1500.0)])    # uma em cima da outra
    tipos = {(a["tipo"], a["placa"]) for a in r["apontamentos"]}
    assert ("duas_aguas", 1) in tipos and ("sobre_cumeeira", 1) in tipos
    assert ("fora", 2) in tipos
    assert ("sobreposta", 4) in tipos
    assert not any(a["placa"] == 3 for a in r["apontamentos"])
