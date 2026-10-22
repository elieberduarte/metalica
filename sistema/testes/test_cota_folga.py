"""A folga do número da cota (usuário, 22/10, ME Sooro: "melhorar o magnetismo do número com a cota, queria que eles
ficassem mais próximos igual a esse modelo e que isso fosse configurável igual ao autocad"). O número a 0,625 mm de
papel da linha (a DIMGAP do AutoCAD no ISO-25; antes 0,55 × a altura do texto), pelo estilo do desenho
(metadados.estilo.folga_texto) e por cota (`folga`) — no PDF (desenho._cota_dxf) e no DXF (DIMGAP) como na tela
(web/cad/nucleo/desenho2d.js textoDaCota, conferida em verificadores/verif_cad_cotas_continuacao.py)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo2d import desenho as D  # noqa: E402
from nucleo2d import dxf_cad  # noqa: E402
from nucleo2d.desenho import Cota, Desenho, FOLGA_TEXTO_COTA  # noqa: E402


class _Papel:
    """O que o _cota_dxf desenha: só os textos interessam."""
    def __init__(self):
        self.textos = []

    def linha(self, *a, **k):
        pass

    def seta(self, *a, **k):
        pass

    def texto(self, x, y, txt, h, camada, **k):
        self.textos.append((x, y, txt, h))


def _base_do_numero(c, k=20.0, estilo=None):
    p = _Papel()
    D._cota_dxf(p, c, k, "COTA", estilo=estilo)
    (x, y, txt, h), = p.textos
    return y - (c.p1[1] + c.deslocamento * k), h       # cota h: a base do número acima da linha


def test_folga_padrao_do_autocad():
    assert FOLGA_TEXTO_COTA == 0.625
    acima, h = _base_do_numero(Cota(modo="h", p1=(0, 0), p2=(2000, 0), deslocamento=10.0, texto="2000"))
    assert acima == pytest.approx(0.625 * 20)              # 12,5 mm no desenho em 1:20 (era 0,55 × 50 = 27,5)
    # com o fator da cota, a folga acompanha (como a ponta e os afastamentos)
    acima, _ = _base_do_numero(Cota(modo="h", p1=(0, 0), p2=(2000, 0), deslocamento=10.0, texto="2000", fator=2.0))
    assert acima == pytest.approx(0.625 * 20 * 2)


def test_folga_do_estilo_e_da_cota():
    c = Cota(modo="h", p1=(0, 0), p2=(2000, 0), deslocamento=10.0, texto="2000")
    assert _base_do_numero(c, estilo={"folga_texto": 1.0})[0] == pytest.approx(20.0)
    c.folga = 0.3                                          # a da cota manda sobre a do desenho
    assert _base_do_numero(c, estilo={"folga_texto": 1.0})[0] == pytest.approx(6.0)
    # volta do JSON com ela
    d = Desenho.de_dict({"nome": "t", "metadados": {"estilo": {"folga_texto": 1.0}},
                         "entidades": [{"tipo": "cota", "id": "c", "p1": [0, 0], "p2": [100, 0], "folga": 0.3}]})
    assert d.entidades["c"].folga == 0.3 and D.folga_da_cota(d.entidades["c"], d.metadados["estilo"]) == 0.3
    assert D.folga_da_cota(Cota(), d.metadados["estilo"]) == 1.0 and D.folga_da_cota(Cota()) == FOLGA_TEXTO_COTA


def test_pdf_com_o_numero_que_nao_cabe_um_degrau_para_fora():
    """o 275 da ME Sooro (fator 1,96, 11 mm entre as chamadas): na tela ele sobe um degrau; no PDF ficava em cima das
    chamadas, na altura de quem cabe"""
    c = Cota(modo="h", p1=(1848.294, 360.729), p2=(1859.283, 374.127), deslocamento=125.17, escala=25.0, fator=1.96)
    acima, h = _base_do_numero(c, k=1.0)
    assert h == pytest.approx(2.5 * 1.96)
    assert acima == pytest.approx(1.9 * h + 0.625 * 1.96)  # o mesmo lugar da tela (textoDaCota)


def test_dxf_dimgap_pela_folga(tmp_path):
    import ezdxf
    d = Desenho(nome="t", metadados={"estilo": {"folga_texto": 1.0}})
    d.add(Cota(id="a", p1=(0.0, 0.0), p2=(1000.0, 0.0), modo="h", deslocamento=10.0, texto="1000"))
    d.add(Cota(id="b", p1=(0.0, 100.0), p2=(1000.0, 100.0), modo="h", deslocamento=10.0, texto="999", folga=0.25, fator=2.0))
    doc = ezdxf.readfile(dxf_cad.exportar(d, str(tmp_path / "f.dxf"), escala=20))
    gaps = {x.dxf.text: x.override().get("dimgap") for x in doc.modelspace().query("DIMENSION")}
    assert gaps["1000"] == pytest.approx(1.0) and gaps["999"] == pytest.approx(0.25 * 2.0)
    assert doc.dimstyles.get("METALICA").dxf.dimgap == pytest.approx(1.0)   # a cota nova no AutoCAD sai com a do desenho
