# -*- coding: utf-8 -*-
"""Modelo de obra inteira (a Obra Capitão, do SketchUp): o concreto e o neoprene saem do
aço para a lista de pré-moldados, o terreno fica de fora e a malha solta de aço grande é
medida como "estrutura a conferir" em vez de contada como parafuso."""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import detalhar as det                          # noqa: E402
from nucleo2d.detalhe import fora_do_aco as fa                # noqa: E402
from nucleo3d.modelo import Solido                            # noqa: E402
from saida import lista_producao as lp                        # noqa: E402
from test_detalhamento import perfil_u                        # noqa: E402
from test_detalhar2d import _modelo                           # noqa: E402


def _caixa(L, B, H, dx=0.0, dy=0.0, dz=0.0):
    v = [(x + dx, y + dy, z + dz) for x in (0, L) for y in (0, B) for z in (0, H)]
    f = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return v, f


def _solido(nome, tipo_ifc, v, f, material):
    s = Solido(nome=nome, camada=tipo_ifc, vertices=v, faces=f)
    s.material = material
    s.atributos["tipo_ifc"] = tipo_ifc
    return s


def _obra():
    doc = _modelo()                                           # o aço do teste do detalhamento
    for i in range(3):
        v, f = _caixa(7880.0, 1245.0, 200.0, dy=i * 1300.0)
        doc.add(_solido("LAJE ALVEOLAR", "IfcBeam", v, f, "CONCRETE/FCK 30"))
    v, f = _caixa(250.0, 130.0, 10.0)
    doc.add(_solido("NP4A", "IfcBeam", v, f, "MISCELLANEOUS/NEOPRENE"))
    v, f = _caixa(80000.0, 50000.0, 1000.0, dz=-1000.0)
    doc.add(_solido("SOLO", "IfcSlab", v, f, "CONCRETE/NULO"))
    # a cobertura em malha solta: dois U de 6 m (fechados) e um parafuso pequeno
    vu, fu = perfil_u(6000.0, 127.0, 50.0, 2.0)
    vu2 = vu + [(x, y + 3000.0, z) for x, y, z in vu]
    fu2 = [list(f) for f in fu] + [[k + len(vu) for k in f] for f in fu]
    doc.add(_solido("CPLAN_MATERIAL_PIEZA_METALICA_VIGA0_2550_spec_x", "IfcBuildingElementProxy", vu2, fu2, "<auto>5"))
    v, f = _caixa(35.0, 12.0, 12.0)
    doc.add(_solido("BOLT (A) 12x35", "IfcBuildingElementProxy", v, f, ""))
    return doc


def test_concreto_e_neoprene_fora_do_aco_e_terreno_fora_de_tudo():
    lev = det.levantar(_obra())
    marcas = {p.marca for p in lev["posicoes"]}
    assert "LAJE ALVEOLAR" not in marcas and "NP4A" not in marcas and "SOLO" not in marcas
    pm = {g["nome"]: g for g in lev["fora_do_aco"]}
    assert set(pm) == {"LAJE ALVEOLAR", "NP4A"}
    laje = pm["LAJE ALVEOLAR"]
    assert laje["quantidade"] == 3 and laje["categoria"] == "concreto"
    assert abs(laje["volume_m3"] - 3 * 7.88 * 1.245 * 0.2) < 0.01
    assert abs(laje["peso_kg"] - laje["volume_m3"] * 2500) < 1.0
    assert pm["NP4A"]["categoria"] == "neoprene"
    assert any("não são de aço" in a for a in lev["avisos"])


def test_malha_solta_grande_e_estrutura_a_conferir_e_parafuso_continua_acessorio():
    lev = det.levantar(_obra())
    assert lev["acessorios"] == {"BOLT (A) 12x35": 1}
    ec = lev["estrutura_a_conferir"]
    assert len(ec) == 1 and ec[0]["quantidade"] == 2 and ec[0]["tipo"] == "barra"
    g = ec[0]
    assert g["comprimento"] == 6000 and g["secao"].startswith("127")
    area = 127 * 2 + 2 * (50 - 2) * 2                          # U 127×50×2 em mm²
    assert abs(g["kg_m"] - area * 7.85e-3) < 0.1
    assert "CPLAN_MATERIAL_PIEZA_METALICA_VIGA0_2550" in g["origem"]
    assert any("Estrutura a conferir" in a for a in lev["avisos"])


def test_malha_aberta_nao_ganha_peso():
    vu, fu = perfil_u(6000.0, 127.0, 50.0, 2.0)
    aberta = _solido("CPLAN_X", "IfcBuildingElementProxy", vu, [list(f) for f in fu][:-1], "")
    linhas = fa.estrutura_a_conferir([aberta])
    assert len(linhas) == 1 and linhas[0]["kg_m"] is None and linhas[0]["peso_kg"] is None


def test_lista_grava_pre_moldados_e_estrutura_a_conferir():
    lev = det.levantar(_obra())
    lista = lp.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"], projeto={"nome": "Obra"})
    lista["pre_moldados"] = lev["fora_do_aco"]
    lista["estrutura_a_conferir"] = lev["estrutura_a_conferir"]
    with tempfile.TemporaryDirectory() as tmp:
        arq = lp.gravar(tmp, lista, lev["posicoes"], lev["acessorios"])
        with open(arq["pre_moldados"], encoding="utf-8-sig") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        assert linhas[0][0] == "Nome" and {l[0] for l in linhas[1:]} == {"LAJE ALVEOLAR", "NP4A"}
        assert os.path.exists(arq["estrutura_a_conferir"])
        html = open(arq["html"], encoding="utf-8").read()
        assert "Fora do aço" in html and "Estrutura de aço a conferir" in html
    # o peso de aço não leva o concreto
    assert lista["totais"]["peso"] < 1000


def test_malha_sem_tampas_mede_a_secao_pelo_corte():
    # o U sem as duas tampas (as faces de 8 vértices): o volume não vale, o corte vale
    vu, fu = perfil_u(6000.0, 127.0, 50.0, 2.0)
    laterais = [list(f) for f in fu if len(f) == 4]
    assert len(laterais) < len(fu)
    linhas = fa.estrutura_a_conferir([_solido("CPLAN_X", "IfcBuildingElementProxy", vu, laterais, "")])
    area = 127 * 2 + 2 * (50 - 2) * 2
    assert len(linhas) == 1 and abs(linhas[0]["kg_m"] - area * 7.85e-3) < 0.1
    assert linhas[0]["tipo"] == "barra"


def test_barra_continua_de_30_m_ganha_kg_m_e_aglomerado_nao():
    vu, fu = perfil_u(30000.0, 127.0, 50.0, 2.0)
    linhas = fa.estrutura_a_conferir([_solido("CPLAN_X", "IfcBuildingElementProxy", vu, [list(f) for f in fu], "")])
    assert linhas[0]["tipo"].startswith("barra contínua") and linhas[0]["kg_m"] > 3.0
    # duas barras de 30 m encostadas pela quina (como os banzos da Capitão): dois perfis
    v2 = vu + [(x, y + 127.0, z + 50.0) for x, y, z in vu]
    f2 = [list(f) for f in fu] + [[k + len(vu) for k in f] for f in fu]
    linhas = fa.estrutura_a_conferir([_solido("CPLAN_X", "IfcBuildingElementProxy", v2, f2, "")])
    assert linhas[0]["tipo"].startswith("aglomerado"), linhas
