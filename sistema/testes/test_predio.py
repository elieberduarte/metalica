# -*- coding: utf-8 -*-
"""Localização e chumbação de prédio (nucleo2d/detalhe/predio.py): o aço preso em várias lajes sai por pavimento.

Vicente Residence, 21/10 (usuário: "essas duas não ficaram muito legais, não são informações úteis para obra"): a planta
de localização do galpão punha os 12 tipos, os penthouses, o duplex e a cobertura uns sobre os outros numa linha só, com
eixos inventados das caixas, e a planta de chumbação não tinha os 924 chumbadores químicos que a obra fura nas lajes."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Solido          # noqa: E402
from nucleo2d import detalhar as det                    # noqa: E402
from nucleo2d.desenho import Texto                      # noqa: E402
from nucleo2d.detalhe import predio                     # noqa: E402

FACES = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]


def _caixa(nome, x0, y0, z0, x1, y1, z1, camada="Metálica – Tipo", tipo_ifc="IfcMember", marcas=None, material="Aço"):
    s = Solido(nome=nome, camada=camada, material=material,
               vertices=[(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], faces=[list(f) for f in FACES])
    s.atributos["tipo_ifc"] = tipo_ifc
    if marcas:
        s.atributos["marcas"] = dict(marcas)
    return s


def _predio(z0=50000.0):
    """Três lajes (+3, +6, +9 m acima de `z0` — o prédio longe do zero, como o Vicente a +28 m), dois pilares de
    concreto por andar e, debaixo de cada laje, duas caixas (tubo de 3 m + chapa de fixação com dois chumbadores
    químicos). A laje de cima tem uma chapa a mais: outro tipo de pavimento."""
    doc = Documento(nome="prédio")
    niveis = [z0 + 3000.0, z0 + 6000.0, z0 + 9000.0]
    for k, z in enumerate(niveis, 1):
        doc.add(_caixa("L1", -3000, -2000, z - 200, 2000, 10000, z, camada="Piso%d" % k, tipo_ifc="IfcSlab",
                       material="CONCRETO C30"))
        for nome, y in (("P1", 0.0), ("P2", 8000.0)):
            doc.add(_caixa(nome, -1300, y - 150, z - 3000, -1000, y + 150, z - 200, camada="Pilares",
                           tipo_ifc="IfcColumn", material="CONCRETO C30"))
        for i, y in enumerate((500.0, 4500.0)):
            inst = "C1#%d" % (2 * k + i)
            doc.add(_caixa("TUBO", 0, y, z - 312, 100, y + 3000, z - 212,
                           marcas={"posicao": "TB1", "conjunto": "C1", "instancia": inst, "perfil": "TQ 100x100x3"}))
            for j, yc in enumerate((y + 200.0, y + 2800.0)):
                doc.add(_caixa("CHAPA", -50, yc - 100, z - 212, 150, yc + 100, z - 200, tipo_ifc="IfcPlate",
                               marcas={"posicao": "CH1", "conjunto": "C1", "instancia": inst, "perfil": "PL 12"}))
                for dx in (-20.0, 120.0):
                    q = _caixa("CHUMBADOR QUÍMICO HIT-V 12.7x190", dx - 6, yc - 6, z - 230, dx + 6, yc + 6, z - 40,
                               tipo_ifc="IfcMechanicalFastener")
                    q.atributos["parafuso"] = {"d": 12.7, "L": 190.0, "classe": "HIT-V"}
                    q.atributos["chumbador_quimico"] = {"d": 12.7, "L": 190.0, "embutimento": 150.0}
                    doc.add(q)
        if k == 3:
            doc.add(_caixa("CHAPA", 0, 7600, z - 212, 100, 7700, z - 200, tipo_ifc="IfcPlate",
                           marcas={"posicao": "CH9", "conjunto": "CH9", "perfil": "PL 12"}))
    return doc


def test_pavimentos_e_tipos():
    doc = _predio()
    pecas = det._pecas(doc)[0]
    pav = predio.pavimentos(doc, pecas)
    assert pav is not None
    assert [n["nome"] for n in pav["niveis"]] == ["Piso1", "Piso2", "Piso3"]
    # as duas caixas de cada andar estão na laje de cima delas (penduradas debaixo dela)
    assert all(len(n["pecas"]) == 6 for n in pav["niveis"][:2]) and len(pav["niveis"][2]["pecas"]) == 7
    # os químicos (não são peça de produção) vão com a chapa que atravessam: 8 por andar
    assert [len(n["chumbadores"]) for n in pav["niveis"]] == [8, 8, 8]
    # Piso1 = Piso2 (um tipo, 2x); o Piso3 tem a CH9 a mais
    assert sorted(len(t["niveis"]) for t in pav["tipos"]) == [1, 2]


def test_galpao_nao_e_predio():
    from test_detalhar2d import _modelo
    doc = _modelo()
    assert predio.pavimentos(doc, det._pecas(doc)[0]) is None


def _textos(d, vista_contem):
    return [e.texto for e in d.entidades.values() if isinstance(e, Texto)
            and vista_contem in str((e.atributos or {}).get("vista") or "")]


def test_localizacao_por_pavimento():
    doc = _predio()
    r = det.detalhar(doc, grupos=["localizacao"], regra_tercas=False)
    d = r["desenhos"]["localizacao"]
    nomes_v = [v["nome"] for v in d.vistas]
    # nada da planta única do galpão: a fachada com as lajes e uma planta por tipo de pavimento
    assert "PLANTA DE LOCALIZAÇÃO" not in nomes_v
    assert nomes_v[0] == "FACHADA – PAVIMENTOS" and len(nomes_v) == 3 == len(d.metadados["celulas"])
    assert any(n.endswith("– 02x") for n in nomes_v) and any(n.endswith("– 01x") for n in nomes_v)
    fach = _textos(d, "FACHADA")
    assert any(t.startswith("Piso1") and "+53,00" in t for t in fach)
    assert any(t.startswith("Piso3") and "+59,00" in t for t in fach)
    # a planta tem os pilares do concreto (a referência das cotas) e as lajes do tipo no cabeçalho
    pl = _textos(d, "– 02x")
    assert "P1" in pl and "P2" in pl
    assert any("Piso1 (+53,00), Piso2 (+56,00)" in t for t in pl)


def test_chumbacao_com_os_quimicos():
    doc = _predio()
    r = det.detalhar(doc, grupos=["chumbacao"], regra_tercas=False)
    d = r["desenhos"]["chumbacao"]
    assert len(d.metadados["celulas"]) == 2
    tx = _textos(d, "CHUMBAÇÃO")
    # oito químicos por pavimento, em quatro grupos (as quatro CH1), e o total da obra
    assert any(t.startswith("8× CHUMBADOR QUÍMICO HIT-V 12.7x190 por pavimento") for t in tx)
    assert any("4 em CH1" in t for t in tx)
    assert sum(1 for t in tx if "total da obra: 16" in t or "total da obra: 8" in t) == 2
