# -*- coding: utf-8 -*-
"""Os níveis do projeto nas folhas (Hora Certa · Galpão Existente, montador M14, 29/10): nenhuma das 44 folhas tinha
um nível escrito, e o quadro da chumbação dava "topo −1,389" sem dizer de quê. As elevações da localização ganham as
marcas de nível do projeto e a chumbação diz a referência ("±0,000 = Piso acabado +906,40")."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Solido                                   # noqa: E402
from nucleo3d import eixos as E                                      # noqa: E402
from nucleo2d.desenho import Texto                                   # noqa: E402
from nucleo2d.detalhe.conjuntos import desenho_de_localizacao, desenho_de_chumbacao, referencia_dos_niveis  # noqa: E402
from test_eixos import _modelo                                       # noqa: E402

NIVEIS = [{"nome": "Topo dos blocos +906,20", "z": 5300.0}, {"nome": "Piso acabado +906,40", "z": 0.0},
          {"nome": "Banzo +912,40", "z": 6000.0}, {"nome": "Cobertura existente +930,00", "z": 23600.0}]


def test_referencia_pelo_nivel_zero():
    assert referencia_dos_niveis(NIVEIS) == "±0,000 = Piso acabado +906,40"
    assert referencia_dos_niveis([]) == "" and referencia_dos_niveis(None) == ""


def test_elevacoes_com_os_niveis_e_chumbacao_com_a_referencia():
    doc, nomes = _modelo()                       # banzos a +6000/+7000, chumbadores de +5500 a +5900
    ex = E.identificar_eixos(doc, nomes)
    pecas = [e for e in doc.entidades.values() if isinstance(e, Solido)]
    d = desenho_de_localizacao(doc, pecas, eixos=ex, nomes_producao=nomes, nomes=nomes["ifc"], niveis=NIVEIS)
    marcas = [e for e in d.entidades.values() if isinstance(e, Texto) and "nivel" in (e.atributos or {})]
    por_vista = {}
    for e in marcas:
        por_vista.setdefault(e.atributos["vista"], set()).add(e.texto)
    assert set(por_vista) == {"ELEVAÇÃO LONGITUDINAL", "ELEVAÇÃO TRANSVERSAL"}, por_vista
    for textos in por_vista.values():
        # os níveis na altura das peças (até 0,5 m fora); o piso a 5,5 m abaixo e a cobertura lá em cima não
        assert textos == {"Topo dos blocos +906,20 (+5,300)", "Banzo +912,40 (+6,000)"}, textos
    ch = desenho_de_chumbacao(doc, pecas, nomes, eixos=ex, nomes=nomes["ifc"], niveis=NIVEIS)
    assert any(isinstance(e, Texto) and e.texto.startswith("LOCAÇÃO DOS CHUMBADORES") and "±0,000 = Piso acabado +906,40"
               in e.texto for e in ch.entidades.values())
