# -*- coding: utf-8 -*-
"""O DXF importado com as cores (usuário, 08/10: vinha tudo cinza): a cor da camada pela paleta ACI inteira, a cor
própria do objeto (62 e a cor verdadeira 420), o BYBLOCK do bloco e a volta pela exportação."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import dxf_ler as L  # noqa: E402


def _dxf(entidades, blocos="", camadas=(("COTAS", 140), ("TRELICA", 3))):
    tab = "".join("0\nLAYER\n2\n%s\n70\n0\n62\n%d\n6\nCONTINUOUS\n" % (n, c) for n, c in camadas)
    return ("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n"
            "0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n%s0\nENDTAB\n0\nENDSEC\n"
            "0\nSECTION\n2\nBLOCKS\n%s0\nENDSEC\n"
            "0\nSECTION\n2\nENTITIES\n%s0\nENDSEC\n0\nEOF\n") % (tab, blocos, entidades)


def _linha(camada, extra="", x=0):
    return "0\nLINE\n8\n%s\n%s10\n%d\n20\n0\n30\n0\n11\n%d\n21\n100\n31\n0\n" % (camada, extra, x, x)


def test_cor_da_camada_pela_paleta_inteira():
    des, _ = L.para_desenho(_dxf(_linha("COTAS") + _linha("TRELICA", "", 10)))
    assert des.camadas["COTAS"].cor == L.cor_aci(140) != "#4b5563"      # 140 não estava na tabela curta (cinza)
    assert des.camadas["TRELICA"].cor == L.CORES_ACI[3]
    assert L.cor_aci(256) is None and L.cor_aci(0) is None and L.cor_aci(10) == "#ff0000"


def test_cor_propria_do_objeto():
    ents = (_linha("TRELICA", "62\n1\n", 0) + _linha("TRELICA", "62\n256\n", 10) +
            _linha("TRELICA", "62\n5\n420\n16744448\n", 20) + _linha("TRELICA", "", 30))
    des, _ = L.para_desenho(_dxf(ents))
    cores = {round(e.a[0]): (e.atributos or {}).get("cor") for e in des.entidades.values()}
    assert cores[0] == L.CORES_ACI[1]                 # 62 = 1 (vermelho)
    assert cores[10] is None and cores[30] is None    # BYLAYER e sem código: a da camada
    assert cores[20] == "#ff8000"                     # a cor verdadeira (420) vence o índice


def test_byblock_toma_a_cor_de_quem_insere():
    bloco = "0\nBLOCK\n8\n0\n2\nB1\n70\n0\n10\n0\n20\n0\n30\n0\n" + _linha("0", "62\n0\n") + "0\nENDBLK\n8\n0\n"
    ins = "0\nINSERT\n8\nTRELICA\n62\n30\n2\nB1\n10\n0\n20\n0\n30\n0\n"
    des, _ = L.para_desenho(_dxf(ins, bloco))
    (e,) = list(des.entidades.values())
    assert e.camada == "TRELICA" and e.atributos.get("cor") == L.cor_aci(30)


def test_a_cor_volta_na_exportacao():
    des, _ = L.para_desenho(_dxf(_linha("TRELICA", "62\n1\n")))
    texto = des.para_dxf().dxf()
    volta, _ = L.para_desenho(texto)
    (e,) = [x for x in volta.entidades.values() if x.tipo == "linha"]
    assert e.atributos.get("cor") == L.CORES_ACI[1]
