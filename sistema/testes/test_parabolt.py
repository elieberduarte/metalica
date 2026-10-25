# -*- coding: utf-8 -*-
"""O Parabolt na lista de compra (OBRA · SESI CHAPECÓ N.4, 22/10): o fixador "PARABOLT 12.7x102" caía no chumbador
genérico e saía "Chumbador químico HIT-V … com químico HIT-RE 500", entrando na conta dos cartuchos. Parabolt é
chumbador MECÂNICO de expansão: a porca e a arruela vêm no kit e não há químico (como o Hardbolt, PRATI 14/10)."""
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from saida import resumos as rz


def _prisma(id_, nome, x0, y0, z0, x1, y1, z1, atr=None):
    vs = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return NS(id=id_, nome=nome, vertices=vs, faces=[], atributos=atr or {}, tipo="solido", perfil="", ifc_tipo="IfcMechanicalFastener")


def test_parabolt_reconhecido_e_descrito():
    assert rz._eh_parabolt("PARABOLT 12.7x102") and rz._eh_parabolt("x", {"parabolt": True})
    assert not rz._eh_parabolt("CHUMBADOR QUÍMICO HIT-V 12.7x190") and not rz._eh_parabolt("Chumbador Hardbolt 12x150")
    nome, desc = rz.descricao_parabolt(15.875, "152")
    assert nome == 'Parabolt Ø5/8" x 152' and "mecânico" in desc and '(6")' in desc and "HIT" not in desc and "sem químico" in desc


def test_parabolt_na_lista_fora_do_quimico_e_das_porcas():
    """os dois atravessando a chapa (o SESI: o Parabolt com o atributo do químico do modelo, que não vale para ele)"""
    chapa = _prisma("ch", "CH1", 0, 0, 0, 300, 300, 12.5, {"marcas": {"posicao": "CH1"}})
    pb = _prisma("pb", "PARABOLT 12.7x102", 44, 44, -90, 56, 56, 12, {"parabolt": True, "chumbador_quimico": {"embutimento": 90}})
    pb2 = _prisma("pb2", "PARABOLT 12.7x102", 144, 44, -90, 156, 56, 12, {"parabolt": True})
    cq = _prisma("cq", "CHUMBADOR QUÍMICO HIT-V 12.7x190", 244, 244, -150, 256, 256, 40, {"chumbador_quimico": {"embutimento": 150}})
    itens = rz._parafusos_com_local([pb, pb2, cq], [chapa], {"CH1": "chapa"}, {"CH1": "CH1"}, {}, {}, {})
    por_nome = {it["nome"]: it for it in itens}
    p = por_nome['Parabolt Ø1/2" x 102']
    assert p["qtd"] == 2 and p["sem_porca"] and not p.get("embutimento") and "químico de injeção" not in p["descricao"]
    assert por_nome['Chumbador químico HIT-V Ø1/2" x 190']["qtd"] == 1
    C = rz._compra({"perfis": [], "posicoes": []}, itens, {}, {})
    assert dict(C["porcas"]) == {'1/2"': 1} and dict(C["arruelas"]) == {'1/2"': 1}, "só as do HIT-V: as do Parabolt vêm no kit"
    (q,) = C["quimicos"]
    assert q["furos"] == 1, "o químico só nos furos do HIT-V"
