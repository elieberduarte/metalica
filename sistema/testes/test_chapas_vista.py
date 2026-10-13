# -*- coding: utf-8 -*-
"""A chapa só mostrada fica em cinza (camada CHAPAS-VISTA) e a chapa para o corte continua dourada (CHAPAS): na
elevação do conjunto e nas cópias de detalhe da prancha, a chapa é demonstração; na chaparia, é a que se corta
(pedido do usuário, 13/10)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import detalhar as det                    # noqa: E402
from nucleo2d.desenho import Polilinha, Texto           # noqa: E402
from nucleo2d import pranchas                           # noqa: E402
from test_detalhar2d import _modelo                     # noqa: E402


def _camadas_da_chapa(desenho, marca="P1"):
    ids = {e.id for e in [] }                                                     # noqa: F841 — só para clareza
    return {e.camada for e in desenho.entidades.values()
            if not isinstance(e, Texto) and str((e.atributos or {}).get("posicao") or "") == marca
            and e.camada.startswith("CHAPAS")}


def test_chapa_no_conjunto_e_vista_e_na_chaparia_e_corte():
    r = det.detalhar(_modelo(), regra_tercas=False, grupos=["conjuntos", "chaparias"])
    conj = r["desenhos"]["conjuntos"]
    chap = r["desenhos"]["chaparias"]
    # a chapa P1 desenhada dentro do conjunto M1/M2/M3: cinza
    cam_conj = {e.camada for e in conj.entidades.values() if not isinstance(e, Texto)
                and (e.atributos or {}).get("detalhe") == "conjunto" and e.camada.startswith("CHAPAS")}
    assert cam_conj == {"CHAPAS-VISTA"}, cam_conj
    assert "CHAPAS-VISTA" in conj.camadas
    # a mesma chapa na chaparia (o desenho para o corte): dourada
    cam_chap = {e.camada for e in chap.entidades.values() if not isinstance(e, Texto)
                and (e.atributos or {}).get("detalhe") == "posicao" and e.camada.startswith("CHAPAS")}
    assert cam_chap == {"CHAPAS"}, cam_chap


def test_copia_do_detalhe_na_prancha_e_cinza_e_a_original_nao():
    pl = Polilinha(camada="CHAPAS", vertices=[(0, 0), (100, 0), (100, 50), (0, 50)], fechada=True,
                   atributos={"detalhe": "posicao", "posicao": "P1"})
    tx = Texto(camada="TEXTO", posicao=(0, 60), texto="CH1 – 10x", altura=2.5)
    celula = {"entidades": [pl, tx], "k": 25.0, "w": 10.0, "h": 8.0}
    copia = pranchas._copia_local(celula, 2)
    assert copia["qtd_local"] == 2 and copia["titulo"] == "CH1 – 02x"
    cam_copia = [e.camada for e in copia["entidades"] if isinstance(e, Polilinha)]
    assert cam_copia == ["CHAPAS-VISTA"], cam_copia
    assert pl.camada == "CHAPAS"                       # a original (a da prancha de corte) não muda
