# -*- coding: utf-8 -*-
"""A chapa expandida na lista (OBRA · POSTO N.3, 23/10): o piso da passarela do Posto V2 é chapa expandida #1/4"
(87 m², ~11 kg/m² pela lista do projetista: 957 kg) e entrava como chapa cheia de 6,35 — o Detalhar pesava ~4,3 t e a
mandava para o plano de corte. Agora é item de compra por m², com o peso pela massa por m² do fabricante."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nucleo3d.modelo import Documento, Chapa
from nucleo2d.detalhar import levantar
from saida import resumos as rz


def _piso(i, massa=11.0):
    c = Chapa(nome='Piso da passarela (chapa expandida #1/4")', origem=(i * 3000.0, 0.0, 0.0), eixo_x=(1.0, 0.0, 0.0),
              eixo_y=(0.0, 1.0, 0.0), contorno=[(0.0, 0.0), (3000.0, 0.0), (3000.0, 1000.0), (0.0, 1000.0)], espessura=6.35,
              centrada=False)
    c.atributos = {"tipo_ifc": "IfcPlate", "origem": {"piso": 'chapa expandida #1/4"'}}
    if massa:
        c.atributos["massa_m2"] = massa
    return c


def _doc(massa=11.0):
    doc = Documento()
    for i in range(3):
        doc.add(_piso(i, massa))
    ch = Chapa(nome="CH9", origem=(0.0, 5000.0, 0.0), eixo_x=(1.0, 0.0, 0.0), eixo_y=(0.0, 1.0, 0.0),
               contorno=[(0.0, 0.0), (300.0, 0.0), (300.0, 200.0), (0.0, 200.0)], espessura=9.5, centrada=False)
    ch.atributos = {"tipo_ifc": "IfcPlate"}
    doc.add(ch)
    return doc


def test_fora_das_posicoes_e_pesada_por_m2():
    lev = levantar(_doc(), regra_tercas=False)
    assert [p.perfil for p in lev["posicoes"]] == ["CH 9,5"], "a chapa expandida não é posição de produção (nem de corte)"
    (f,) = [f for f in lev["fora_do_aco"] if f["categoria"] == "chapa expandida"]
    assert f["quantidade"] == 3 and abs(f["area_m2"] - 9.0) < 1e-6 and abs(f["peso_kg"] - 99.0) < 1e-6
    assert abs(f["comprimento_m"] - 9.0) < 1e-6


def test_sem_a_massa_por_m2_fica_sem_peso_e_avisa():
    lev = levantar(_doc(massa=None), regra_tercas=False)
    (f,) = [f for f in lev["fora_do_aco"] if f["categoria"] == "chapa expandida"]
    assert f["peso_kg"] == 0.0 and "sem a massa por m²" in f["observacao"]


def test_na_compra_a_tabela_da_chapa_expandida():
    lev = levantar(_doc(), regra_tercas=False)
    C = rz._compra({"perfis": [], "posicoes": [], "pre_moldados": lev["fora_do_aco"]}, [], {}, {})
    (x,) = C["chapas_expandidas"]
    assert x["pecas"] == 3 and abs(x["m2"] - 9.0) < 1e-6 and abs(x["kg"] - 99.0) < 1e-6
    assert not C["outros_aco"], "não cai nos gradis sem peso"
    html = rz._html_compra({"compra": C})
    assert "Chapa expandida" in html and "99,0" in html


def test_a_passarela_grava_a_massa_do_piso():
    from nucleo3d import passarela
    assert passarela.MASSA_PISO_KG_M2 == 11.0
