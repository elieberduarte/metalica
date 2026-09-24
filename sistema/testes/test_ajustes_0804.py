# -*- coding: utf-8 -*-
"""0.8.4: furo com o diâmetro na célula; barra roscada que atravessa a castanha pelo nome."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.detalhe.base import _nome_passante          # noqa: E402
from nucleo2d.detalhe.celulas import _cabecalho            # noqa: E402
from saida.detalhamento import Furo, Posicao               # noqa: E402


class TestCastanha(unittest.TestCase):
    def test_nome_da_barra(self):
        self.assertEqual(_nome_passante("BARRA ROSCADA Ø 5/8''\r\n\n"), 'barra roscada Ø5/8"')
        self.assertEqual(_nome_passante("FE RED 3/8''"), 'ferro redondo Ø3/8"')

    def test_cabecalho_da_castanha(self):
        pos = Posicao(marca="P42", tipo_ifc="IfcPlate", perfil="PLATE 80x80x8", quantidade=48, classe="chapa",
                      T=8.0, nome="C.S.1")
        pos.espessura = 8.0
        pos.furos = [Furo("redondo", 40.0, 40.0, d=17.0)]
        pos.passantes = {'barra roscada Ø5/8"': 1}
        pos.porcas = 2
        linhas = _cabecalho(pos)
        self.assertIn("furo Ø17", linhas)
        self.assertIn('fixação: barra roscada Ø5/8", 2x porca 5/8"', linhas)
        self.assertFalse(any("sem tamanho no IFC" in l for l in linhas))

    def test_varios_furos(self):
        pos = Posicao(marca="P1", tipo_ifc="IfcPlate", perfil="PLATE 400x120x13", quantidade=11, classe="chapa", T=13.0)
        pos.furos = [Furo("redondo", 40.0, 40.0, d=21.0), Furo("redondo", 360.0, 40.0, d=21.0)]
        pos.porcas = 6
        linhas = _cabecalho(pos)
        self.assertIn("furos: 2x Ø21", linhas)
        self.assertIn("fixação: 6x porca/chumbador", linhas)


if __name__ == "__main__":
    unittest.main()
