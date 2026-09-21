# -*- coding: utf-8 -*-
"""Rótulos das tabelas de esforços, geometria e dados adotados do memorial."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import memorial as M  # noqa: E402


class TestRotuloGrandeza(unittest.TestCase):
    def test_simbolo_mantem_a_caixa(self):
        # t (espessura) e T (força de tração) são grandezas diferentes
        self.assertEqual(M._rotulo_grandeza("t"), "t")
        self.assertEqual(M._rotulo_grandeza("T"), "T")
        self.assertEqual(M._rotulo_grandeza("fck"), "f<sub>ck</sub>")

    def test_indices_vao_para_o_subscrito(self):
        self.assertEqual(M._rotulo_grandeza("M_Rd_FLT"), "M<sub>Rd,FLT</sub>")
        self.assertEqual(M._rotulo_grandeza("Mx_Rd"), "M<sub>x,Rd</sub>")
        self.assertEqual(M._rotulo_grandeza("Ag"), "A<sub>g</sub>")
        self.assertEqual(M._rotulo_grandeza("sigma_c_Rd"), "σ<sub>c,Rd</sub>")
        self.assertEqual(M._rotulo_grandeza("lambda_0"), "λ<sub>0</sub>")

    def test_unidade_da_chave_vai_para_o_parentese(self):
        self.assertEqual(M._rotulo_grandeza("V_Sd_kN"), "V<sub>Sd</sub> (kN)")
        self.assertEqual(M._rotulo_grandeza("Mx_succao_kNcm"), "M<sub>x</sub> sucção (kN·cm)")
        self.assertEqual(M._rotulo_grandeza("peso_kg"), "Peso (kg)")

    def test_palavra_ganha_acento_e_maiuscula(self):
        self.assertEqual(M._rotulo_grandeza("interacao"), "Interação")
        self.assertEqual(M._rotulo_grandeza("aco_placa"), "Aço da placa")

    def test_tabela_nao_repete_momento_nem_linhas(self):
        html = M._dic_tabela({"M_kNm": 12.5, "M_kNcm": 1250.0, "linhas": 7, "por_agua": 7,
                              "cotas_fiadas_m": [1.0, 3.0, 5.0]})
        self.assertIn("kN·m", html)
        self.assertNotIn("kN·cm", html)
        self.assertEqual(html.count("Linhas por água"), 1)
        self.assertIn("1,00; 3,00; 5,00", html)


class TestMemorialSemChavesCruas(unittest.TestCase):
    def test_memorial_do_galpao_padrao(self):
        from nucleo.galpao import dimensionar
        from nucleo.modelo_galpao import DadosGalpao
        html = M.montar_html(dimensionar(DadosGalpao()))
        for crua in ("q_pressao_kN_m", "cotas_fiadas_m", "Mx_gravidade_kNcm", "Lt_cm",
                     "inclinacao_graus", "massa_kg_m", "T_por_parafuso", "p_tributario"):
            self.assertNotIn(f">{crua}<", html, crua)


if __name__ == "__main__":
    unittest.main()
