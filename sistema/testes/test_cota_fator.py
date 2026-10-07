"""O fator de tamanho da cota (07/10): a cota feita sobre um desenho importado em outra escala acompanha o tamanho das
cotas dele — texto, ponta e afastamentos juntos × fator. Sem fator, nada muda (as pranchas e os desenhos de antes)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo2d import dxf_cad  # noqa: E402
from nucleo2d.desenho import Cota, Desenho  # noqa: E402


def _dim(tmp_path, fator):
    import ezdxf
    d = Desenho(nome="t")
    d.add(Cota(p1=(0.0, 0.0), p2=(1000.0, 0.0), modo="h", deslocamento=10.0, altura=2.5, fator=fator))
    arq = dxf_cad.exportar(d, str(tmp_path / ("c%s.dxf" % fator)), escala=20)
    doc = ezdxf.readfile(arq)
    dims = [e for e in doc.modelspace() if e.dxftype() == "DIMENSION"]
    assert len(dims) == 1
    return dims[0].get_dxf_attrib("dimstyle"), dims[0].override()


def test_dxf_com_e_sem_fator(tmp_path):
    _e, o1 = _dim(tmp_path, None)
    _e, o4 = _dim(tmp_path, 0.4)
    assert o1.get("dimtxt") == pytest.approx(2.5) and o1.get("dimexe") in (None, 2.0)
    assert o4.get("dimtxt") == pytest.approx(1.0) and o4.get("dimasz") == pytest.approx(0.4 * o1.get("dimasz"))
    assert o4.get("dimexe") == pytest.approx(0.8) and o4.get("dimexo") == pytest.approx(0.6)


def test_cota_le_o_fator_do_desenho_salvo():
    d = Desenho.de_dict({"nome": "t", "entidades": [{"tipo": "cota", "camada": "COTA", "p1": [0, 0], "p2": [100, 0], "fator": 0.5},
                                                    {"tipo": "cota", "camada": "COTA", "p1": [0, 0], "p2": [100, 0]}]})
    cs = [e for e in d.entidades if isinstance(e, Cota)] if isinstance(d.entidades, list) else [e for e in d.entidades.values() if isinstance(e, Cota)]
    assert sorted((c.fator or 1.0) for c in cs) == [0.5, 1.0]
