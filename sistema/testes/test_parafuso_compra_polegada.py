# -*- coding: utf-8 -*-
"""O comprimento do parafuso na compra em polegada não fica curto nem sobe à toa, e o autobrocante não leva porca.

SESI Chapecó (auditor-de-numeros, 28/10 e 02/11, N03): os 3.130 "BOLT (A325) 12.7x38" e os 48 "15.875x38" saíam na compra
como "Ø1/2" x 1.3/4"" (38 mm = 1½"): a tabela não tinha o 38 e ia para a chave mais próxima (40 → 1¾"). Os 1.641
autobrocantes "BOLT (PB8-18) 4.2x12" da costura do deck saíam "Parafuso sextavado ØM4.2 x 1" + porca e arruela", com
1.641 porcas e 1.641 arruelas M4.2 que não existem."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from nucleo3d.modelo import Barra, Chapa, Documento  # noqa: E402
from nucleo3d import ligacoes3d as L3  # noqa: E402
from nucleo2d.detalhar import levantar  # noqa: E402
from nucleo2d.detalhe.base import _fixadores  # noqa: E402
from saida import resumos  # noqa: E402
from saida.lista_producao import acessorios_da_lista  # noqa: E402


def _pol(txt):
    """'1.3/4"' → 1,75; '1/2"' → 0,5; '2"' → 2."""
    t = txt.rstrip('"')
    inteiro, _, frac = t.partition(".") if "/" in t and "." in t else (("0", "", t) if "/" in t else (t, "", ""))
    v = float(inteiro)
    if frac:
        a, b = frac.split("/")
        v += float(a) / float(b)
    return v


def test_o_menor_quarto_que_nao_fica_curto():
    """e a regra do usuário de 05/11 (via GESTÃO): nunca mais curto que o projeto — a tabela antiga comprava 45 → 1.3/4",
    65 → 2.1/2", 80 → 3" e 90 → 3.1/2" (o GE: 48 de 5/8" × 45; o Vicente: 724 de 1/2" × 80)"""
    for L in range(10, 201):
        mm = 25.4 * _pol(resumos.comprimento_em_polegada(L))
        assert mm >= L - 0.5 and mm - L <= 6.35, (L, resumos.comprimento_em_polegada(L))
    assert resumos.comprimento_em_polegada(38) == '1.1/2"' and resumos.comprimento_em_polegada(12) == '1/2"'
    assert resumos.comprimento_em_polegada(44) == '1.3/4"' and resumos.comprimento_em_polegada(35) == '1.1/2"'
    for L, pol in ((45, '2"'), (65, '2.3/4"'), (80, '3.1/4"'), (90, '3.3/4"'), (70, '2.3/4"'), (25, '1"'), (50, '2"'), (100, '4"')):
        assert resumos.comprimento_em_polegada(L) == pol, (L, resumos.comprimento_em_polegada(L))
    assert "x 1.1/2\" ASTM A325" in resumos.descricao_parafuso("M12.7x38", "A325")[1]


def test_lista_o_autobrocante_sem_porca_e_o_38_em_um_e_meio():
    a = {x["nome"]: x["quantidade"] for x in acessorios_da_lista({"BOLT (PB8-18) 4.2x12": 1641, "BOLT (A325) 12.7x38": 3130,
                                                                   "BOLT (A325) 15.875x38": 48})}
    assert a["Parafuso autobrocante PB8-18 Ø4,2 x 12 mm (sem porca e arruela)"] == 1641, a
    assert a['Parafuso sextavado M12.7 x 38 – ASTM A325 (na compra: Ø1/2" x 1.1/2") + porca e arruela'] == 3130, a
    assert a['Parafuso sextavado M15.875 x 38 – ASTM A325 (na compra: Ø5/8" x 1.1/2") + porca e arruela'] == 48, a
    assert not [k for k in a if "M4.2" in k and ("orca" in k or "rruela" in k)], a
    assert a["Porca sextavada M12.7 (dos parafusos)"] == 3130


def test_no_resumo_o_autobrocante_e_compra_sem_porca():
    d = Documento()
    d.add(Barra(nome="Viga", inicio=(0, 0, 0), fim=(1000, 0, 0), perfil="W 150×13,0", papel="viga", camada="Vigas",
                material="Aço", aco="ASTM A572", atributos={"tipo_ifc": "IfcBeam"}))
    d.add(Chapa(nome="Chapa", origem=(900, -60, 150), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0),
                contorno=[(0, 0), (100, 0), (100, 120), (0, 120)], espessura=8, centrada=False,
                camada="Chapas", material="Aço", aco="ASTM A36", atributos={"tipo_ifc": "IfcPlate"}))
    for y in (-30, 30):
        p = L3._parafuso((950, y, 150), (0, 0, 1), 4.2, 8.0, "PB8-18")
        p.nome = "BOLT (PB8-18) 4.2x12"
        d.add(p)
    r = resumos._parafusos_com_local(_fixadores(d), levantar(d)["pecas"], {}, {}, {}, {}, {})
    pb = [x for x in r if x.get("parafuso")]
    assert [(x["nome"], x["qtd"], x["sem_porca"]) for x in pb] == [("Autobrocante PB8-18 4,2x12", 2, True)], pb
    assert "autobrocante" in pb[0]["descricao"] and "porca e arruela)" in pb[0]["descricao"]
    assert not [x for x in r if not x.get("parafuso")], r                     # nenhuma porca nem arruela solta
