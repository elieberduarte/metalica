# -*- coding: utf-8 -*-
"""0.8.1: terças em colunas (o quadro não fica comprido)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Linha            # noqa: E402
from nucleo2d.detalhe.base import _em_colunas          # noqa: E402


class TestColunas(unittest.TestCase):
    def test_celulas_em_colunas(self):
        d = Desenho(nome="t", escala=25)

        def celula(dd, x, y):
            dd.add(Linha(a=(x, y), b=(x + 6000, y)))
            dd.add(Linha(a=(x, y - 1500), b=(x + 6000, y - 1500)))
            return (x, y - 1500, x + 6000, y)
        _em_colunas(d, [lambda x, y: celula(d, x, y) for _ in range(30)], altura_max_papel=560.0)
        cel = d.metadados["celulas"]
        self.assertEqual(len(cel), 30)
        altura = max(c[3] for c in cel) - min(c[1] for c in cel)
        largura = max(c[2] for c in cel) - min(c[0] for c in cel)
        self.assertLessEqual(altura, 560.0 * 25 + 1)          # nenhuma coluna passa do limite
        self.assertGreater(largura, 6000 * 3)                 # várias colunas lado a lado
        # a ordem desce na coluna: a segunda célula está abaixo da primeira
        self.assertLess(cel[1][3], cel[0][1])
        # sem sobreposição
        for i, a in enumerate(cel):
            for b in cel[i + 1:]:
                self.assertFalse(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])


if __name__ == "__main__":
    unittest.main()
