# -*- coding: utf-8 -*-
"""Regras da fábrica: perfil dobrado validado pela bobina, pela tira e pela dobradeira."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fabrica  # noqa: E402


def test_valida_dobrado_catalogo_e_barra_o_que_nao_existe():
    d = tempfile.mkdtemp()
    v = fabrica.validar("U92X30X#13", d)
    assert v["ok"] and v["tipo"] == "dobrado" and abs(v["desenvolvido"] - 144.6) < 0.2
    assert fabrica.validar("U100X50X4.18", d)["ok"]                 # MSG 4,18 = bobina #8
    assert fabrica.validar("W150X13.00", d)["tipo"] == "catalogo"   # laminado do banco de perfis
    assert not fabrica.validar("U400X150X#8", d)["ok"]              # tira de 686 mm > 600
    assert "bitola #27" in fabrica.validar("U100X50X#27", d)["motivos"][0]
    assert not fabrica.validar("U92X8X#13", d)["ok"]                # aba curta para a espessura
    assert not fabrica.validar("X100", d)["ok"]


def test_registro_e_regras():
    d = tempfile.mkdtemp()
    reg = fabrica.registrar(d, "U92X30X#13", "obra", "ana", "pc")
    assert reg["usos"] == 1 and reg["projetos"] == ["obra"]
    assert fabrica.registrar(d, "U92X30X#13", "outra")["usos"] == 2
    try:
        fabrica.registrar(d, "U400X150X#8", "obra")
        assert False, "perfil barrado não pode ser registrado"
    except ValueError:
        pass
    fabrica.gravar_regras(d, {"largura_max_tira": "700", "conferidas": True})
    assert fabrica.validar("U400X150X#8", d)["ok"]
    assert fabrica.remover(d, "U92X30X#13") and not fabrica.perfis(d)
