# -*- coding: utf-8 -*-
"""0.8.2: classe do parafuso lançado no 3D vai para o nome na lista; atualização sem o
instalador anexado não fica guardada."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _F:
    def __init__(self, nome):
        self.nome = nome


class TestParafuso(unittest.TestCase):
    def test_classe_no_nome(self):
        from nucleo2d.detalhe.base import _nome_do_parafuso
        self.assertEqual(_nome_do_parafuso(_F("BOLT (A325) 16x50"), None), ("M16 x 50 A325", False))
        self.assertEqual(_nome_do_parafuso(_F("BOLT (8.8) 12x35"), None), ("M12 x 35 8.8", False))
        # o "(A)" dos IFC do TecnoMETAL não é classe
        self.assertEqual(_nome_do_parafuso(_F("BOLT (A) 12x35"), None), ("M12 x 35", False))


class TestAtualizacao(unittest.TestCase):
    def test_sem_instalador_nao_guarda(self):
        import json
        import app
        resposta = {"tag_name": "v99.0.0", "html_url": "x", "assets": []}

        class R:
            def __init__(self, d): self.d = d
            def read(self): return json.dumps(self.d).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False
        import urllib.request
        antigo = urllib.request.urlopen
        app._ULTIMA_CONSULTA.update(quando=0, dados=None)
        try:
            urllib.request.urlopen = lambda *a, **k: R(resposta)
            r = app.verificar_atualizacao()
            self.assertTrue(r["nova"])
            self.assertIsNone(r["arquivo"])
            self.assertIsNone(app._ULTIMA_CONSULTA["dados"])       # na próxima consulta pergunta de novo
            resposta["assets"] = [{"name": "Metalica-99.0.0-instalador.exe", "browser_download_url": "u", "size": 1}]
            r = app.verificar_atualizacao()
            self.assertEqual(r["arquivo"], "u")
            self.assertIsNotNone(app._ULTIMA_CONSULTA["dados"])
        finally:
            urllib.request.urlopen = antigo
            app._ULTIMA_CONSULTA.update(quando=0, dados=None)


if __name__ == "__main__":
    unittest.main()
