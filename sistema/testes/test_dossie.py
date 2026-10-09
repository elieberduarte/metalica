# -*- coding: utf-8 -*-
"""O dossiê da obra (saida/dossie.py, 09/10): pavimentos pelas camadas, o papel de cada peça e os desenhos."""
from types import SimpleNamespace

from saida import dossie


def _peca(i, camada, z0, z1, x0=0.0, x1=100.0):
    vs = [(x, y, z) for x in (x0, x1) for y in (0.0, 100.0) for z in (z0, z1)]
    return SimpleNamespace(id=i, camada=camada, vertices=vs)


def test_pavimentos_pelas_camadas_e_a_repeticao_pelas_cotas():
    """o Tipo em 3 andares (faixas de cota separadas) é ×3; o duplex com o pilar de 7 m é uma faixa só"""
    pecas = [_peca("t%d" % k, "Metálica – Tipo", 10000 + 3600 * k, 10300 + 3600 * k) for k in range(3)]
    pecas += [_peca("d1", "Metálica – Duplex", 0, 7000), _peca("d2", "Metálica – Duplex", 6800, 6900)]
    varios, pavs, pav_de = dossie.pavimentos_do_modelo(pecas)
    assert varios
    por = {p["nome"]: p for p in pavs}
    assert por["Tipo"]["repete"] == 3 and por["Duplex"]["repete"] == 1
    assert [p["nome"] for p in pavs] == ["Duplex", "Tipo"]                   # na ordem de cota
    assert pav_de["t1"] == "Tipo"


def test_camadas_de_tipo_de_peca_nao_sao_pavimentos():
    """o galpão do IFC tem as camadas Vigas, Telhas, Chapas: é obra de um pavimento"""
    pecas = [_peca("a", "Vigas", 0, 100), _peca("b", "Telhas", 0, 100), _peca("c", "Chapas", 0, 100)]
    varios, pavs, _ = dossie.pavimentos_do_modelo(pecas)
    assert not varios and pavs == []


def test_secao_e_metros():
    assert dossie._secao("TQ 250x250x6,3") == "vigas_tubo" and dossie._secao("TR 250x100x9,5") == "vigas_tubo"
    assert dossie._secao("W200X26.6") == "vigas_i" and dossie._secao("U150X50X2.28") == "vigas_u"
    assert dossie._m(2195) == "2,20 m" and dossie._m(1875) == "1,88 m" and dossie._m(6848) == "6,85 m"


def test_planta_com_eixos_e_cotas_e_o_corte_com_os_pavimentos():
    geo = {"p1": {"papel": "pilares", "seg": ((0, 0, 0), (0, 0, 6000)), "z0": 0, "z1": 6000, "verts": [(0, 0, 0), (0, 0, 6000)]},
           "v1": {"papel": "vigas_tubo", "seg": ((0, 0, 6000), (8000, 0, 6000)), "z0": 6000, "z1": 6000,
                  "verts": [(0, 0, 6000), (8000, 0, 6000)]}}
    eixos = {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 8000.0}],
             "letras": [{"nome": "A", "pos": 0.0}]}
    svg = dossie.planta_svg(geo, eixos)
    assert svg.startswith("<svg") and ">1</text>" in svg and ">2</text>" in svg and ">A</text>" in svg
    assert ">8,00</text>" in svg                                              # a cota entre os eixos 1 e 2
    pavs = [{"nome": "Duplex", "faixas": [(0.0, 6000.0)], "repete": 1, "z0": 0.0, "z1": 6000.0, "cor": "#1f6feb"}]
    corte = dossie.corte_svg(geo, pavs, {"p1": "Duplex", "v1": "Duplex"})
    assert "Duplex" in corte and "+6,00" in corte
