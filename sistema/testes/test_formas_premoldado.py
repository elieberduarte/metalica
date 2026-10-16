# -*- coding: utf-8 -*-
"""Fôrma das peças pré-moldadas do IFC (nucleo2d/detalhe/premoldado_formas.py, 16/10/2026)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nucleo2d.desenho import Cota, Texto  # noqa: E402
from nucleo2d.detalhe import premoldado_formas as PF  # noqa: E402
from nucleo3d.modelo import Documento, Solido  # noqa: E402


def _caixa(nome, x0, y0, z0, x1, y1, z1, ref="", material="CONCRETE/Fck-40"):
    vs = [(x, y, z) for z in (z0, z1) for (x, y) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    fs = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    props = {"Pset_BeamCommon": {"Reference": ref}} if ref else {}
    return Solido(nome=nome, camada="200 Pré-Fabricado", material=material, vertices=vs, faces=fs,
                  atributos={"propriedades": props, "marcas": {"perfil": nome}})


def _modelo():
    doc = Documento()
    doc.add(_caixa("Pilar", 0, 0, 0, 400, 400, 6000, "P1"))
    doc.add(_caixa("Console", 400, 100, 4000, 700, 300, 4400))
    doc.add(_caixa("Viga L", 400, 0, 4400, 6400, 300, 5000, "VL1"))
    doc.add(_caixa("Viga L", 400, 3000, 4400, 6400, 3300, 5000, "VL1"))
    doc.add(_caixa("Viga L", 400, 6000, 4400, 7400, 6300, 5000, "VL1"))       # a mesma marca, outro comprimento
    doc.add(_caixa("Bloco", -500, -500, -800, 900, 900, 0, "", material="CONCRETE/Fck-25"))
    doc.add(_caixa("Terreno", -9000, -9000, -2000, 9000, 9000, -800))
    doc.add(_caixa("A 100x100x3/8", 0, 0, 6000, 100, 100, 6010, "ACH1", material="STEEL/A36"))
    return doc


def test_familias_e_o_que_fica_fora():
    doc = _modelo()
    fam = {e.nome: PF.familia_de(e) for e in doc.entidades.values()}
    assert fam["Pilar"] == "pilares_vigas" and fam["Viga L"] == "pilares_vigas"
    assert fam["Bloco"] == "fundacoes"
    assert fam["Terreno"] is None and fam["A 100x100x3/8"] is None


def test_console_no_pilar_e_pecas_iguais_contadas():
    reps = PF.agrupar(PF.pecas_do_modelo(_modelo()))
    por = {r.marca: r for r in reps}
    assert por["P1"].consoles == 1 and len(por["P1"].instancias) == 1
    assert round(por["P1"].dims[0]) == 700                     # o console entra na largura da fôrma
    # a mesma marca do Tekla com duas geometrias: /A (a mais usada, 2x) e /B
    assert len(por["VL1/A"].instancias) == 2 and round(por["VL1/A"].dims[0]) == 6000
    assert len(por["VL1/B"].instancias) == 1 and round(por["VL1/B"].dims[0]) == 7000
    # sem marca: a sigla do nome
    assert any(m.startswith("B") for m in por if por[m].nome == "Bloco")
    assert por[next(m for m in por if por[m].nome == "Bloco")].concreto == "fck 25 MPa"


def test_desenho_por_familia_com_titulo_e_cotas():
    ds = PF.desenhos(_modelo())
    assert set(ds) == {"pilares_vigas", "fundacoes"}
    d = ds["pilares_vigas"]
    textos = [e.texto for e in d.entidades.values() if isinstance(e, Texto)]
    assert "VL1/A – 2x" in textos and "P1 – 1x" in textos
    cotas = [e for e in d.entidades.values() if isinstance(e, Cota) and e.atributos.get("posicao") == "P1"]
    alturas = sorted(round(abs(c.p2[1] - c.p1[1])) for c in cotas if c.modo == "v")
    assert 6000 in alturas and 400 in alturas                 # a total e a altura do console na cadeia
    assert all(e.atributos.get("detalhe") == "premoldado" for e in d.entidades.values())
