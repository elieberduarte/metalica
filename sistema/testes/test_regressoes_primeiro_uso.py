# -*- coding: utf-8 -*-
"""Regressões dos testes de primeiro uso (16/10/2026) — os agentes engenheiro-primeiro-uso (DXF → 3D) e
detalhista-primeiro-uso-ifc (IFC → pranchas) usaram o programa pelas telas, com a pasta de projetos vazia, e
anotaram onde travaram (Projeto/BRIEFINGS/Briefing-primeiro-uso*.md). Cada teste falha sem a correção
(ver sistema/testes/REGRESSOES.md, seção "Primeiro uso")."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app                                                   # noqa: E402
from nucleo2d.desenho import Desenho, Linha                  # noqa: E402
from nucleo3d import lancamento                              # noqa: E402
from projetos import Projetos                                # noqa: E402


class _ComProjeto(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="regr_primeiro_uso_")
        self.antigo = app.PROJETOS
        app.PROJETOS = self.pasta
        app._CACHE_REFERENCIA.clear()
        self.g = Projetos(self.pasta)
        self.s = self.g.criar("Portaria", tipo="lancamento")["slug"]

    def tearDown(self):
        app.PROJETOS = self.antigo


class TestEixosGravadosDepoisDaPlanta(_ComProjeto):
    """P04 — "gravei A, B, 1, 2 em Eixos da obra, mas Pilares nos eixos e os balões do 3D continuaram com os antigos":
    a malha da Planta de lançamento (aqui, linhas do DXF importado) sempre vencia os eixos gravados no diálogo.
    Vale a mais recente das duas."""

    def _planta_com_malha(self):
        des = Desenho(nome=lancamento.DESENHO_LANCAMENTO)
        for nome, a, b in (("A", (0, -1000), (0, 7000)), ("B", (4000, -1000), (4000, 7000)), ("1", (-1000, 0), (5000, 0))):
            des.add(Linha(camada="EIXO", a=a, b=b, atributos={"eixo": nome}))
        self.g.salvar_desenho(self.s, lancamento.DESENHO_LANCAMENTO, des.dict())

    def _gravar_no_dialogo(self):
        return app.gravar_eixos_projeto(self.s, {"eixos": {
            "eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "z_base": 0.0,
            "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 4000.0}],
            "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6200.0}]}})

    def _nomes(self):
        return sorted({e["nome"] for e in app.referencia_do_lancamento(self.s)["eixos"]})

    def test_gravados_no_dialogo_depois_da_planta_valem(self):
        self._planta_com_malha()
        self.assertEqual(self._nomes(), ["1", "A", "B"])
        time.sleep(0.05)
        self._gravar_no_dialogo()
        self.assertEqual(self._nomes(), ["1", "2", "A", "B"])

    def test_planta_mexida_depois_volta_a_valer(self):
        self._planta_com_malha()
        self._gravar_no_dialogo()
        time.sleep(0.05)
        self._planta_com_malha()          # o usuário redesenhou a malha na planta depois de gravar
        self.assertEqual(self._nomes(), ["1", "A", "B"])


if __name__ == "__main__":
    unittest.main()
