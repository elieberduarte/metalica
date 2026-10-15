# -*- coding: utf-8 -*-
"""O modelo 3D do projeto guardado em memória enquanto não muda no disco (15/10/2026: ler e montar os 52 MB da PRATI a
cada Editar chapa): cada pedido recebe uma cópia nova, igual à do disco; mexer numa cópia não muda a próxima; gravar
o modelo (o mtime muda) descarta a memória."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app                                   # noqa: E402
from projetos import Projetos                # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402


def _foto(doc):
    return json.dumps(doc.dict(), sort_keys=True, default=str)


class TestModeloEmMemoria(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="memoria_")
        self.antigo = app.PROJETOS
        app.PROJETOS = self.pasta
        self.g = Projetos(self.pasta)
        self.s = self.g.criar("Obra", tipo="desenho")["slug"]
        doc = Documento()
        for k in range(20):
            doc.add(Barra(nome="B%d" % k, inicio=(0, 1000 * k, 0), fim=(6000, 1000 * k, 0), perfil="W 310×38,7", papel="viga"))
        self.g.salvar_modelo(self.s, doc.dict())

    def tearDown(self):
        app.PROJETOS = self.antigo

    def test_a_segunda_leitura_vem_da_memoria_e_e_uma_copia_nova(self):
        a = app._documento3d_do_projeto(self.s)
        caminho = self.g.caminho_modelo(self.s)
        self.assertIn(caminho, app._MODELOS_EM_MEMORIA)
        b = app._documento3d_do_projeto(self.s)
        self.assertEqual(_foto(a), _foto(b))
        self.assertIsNot(a, b)
        self.assertEqual(a._mtime_lido, b._mtime_lido)
        # mexer numa cópia não muda a seguinte
        e = next(iter(b.entidades.values()))
        e.perfil = "W 610×140"
        e.atributos["marcas"] = {"posicao": "P99"}
        c = app._documento3d_do_projeto(self.s)
        self.assertEqual(_foto(a), _foto(c))

    def test_gravar_o_modelo_descarta_a_memoria(self):
        a = app._documento3d_do_projeto(self.s)
        time.sleep(0.02)
        a.add(Barra(nome="nova", inicio=(0, 0, 3000), fim=(6000, 0, 3000), perfil="W 310×38,7", papel="viga"))
        self.g.salvar_modelo(self.s, a.dict())
        b = app._documento3d_do_projeto(self.s)
        self.assertEqual(len(b.entidades), 21)
        self.assertTrue(any(x.nome == "nova" for x in b.entidades.values()))

    def test_no_maximo_duas_obras_em_memoria(self):
        outros = []
        for n in ("Obra 2", "Obra 3"):
            s = self.g.criar(n, tipo="desenho")["slug"]
            self.g.salvar_modelo(s, Documento().dict())
            outros.append(s)
        for s in [self.s] + outros:
            app._documento3d_do_projeto(s)
        self.assertLessEqual(len(app._MODELOS_EM_MEMORIA), 2)
        self.assertNotIn(self.g.caminho_modelo(self.s), app._MODELOS_EM_MEMORIA)


if __name__ == "__main__":
    unittest.main()
