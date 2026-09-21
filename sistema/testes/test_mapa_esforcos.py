# -*- coding: utf-8 -*-
"""Mapa de esforços entregue ao editor 3D: `nucleo3d/mapa_esforcos.py`.

O que se garante aqui é o contrato com o editor — chaves, unidades e coordenadas — e,
principalmente, que os números do mapa são os mesmos que dimensionaram as peças. Um
mapa bonito com esforço diferente do memorial seria pior do que não ter mapa.
"""
import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.galpao import dimensionar          # noqa: E402
from nucleo.modelo_galpao import DadosGalpao   # noqa: E402
from nucleo3d import mapa_esforcos as me       # noqa: E402


class BaseMapa(unittest.TestCase):
    """Dimensiona um galpão uma única vez para toda a classe: é a parte cara."""

    @classmethod
    def setUpClass(cls):
        cls.projeto = dimensionar(DadosGalpao())
        cls.mapa = me.mapa_de_esforcos(cls.projeto)


class TestContrato(BaseMapa):
    def test_estrutura_e_serializavel(self):
        self.assertTrue(self.mapa["ok"])
        json.dumps(self.mapa, ensure_ascii=False)      # o editor recebe por JSON
        for chave in ("unidades", "grandezas", "combinacoes", "elementos", "portico",
                      "deformada", "cargas", "servico"):
            self.assertIn(chave, self.mapa)

    def test_combinacoes_comecam_pela_envoltoria(self):
        combos = self.mapa["combinacoes"]
        self.assertEqual(combos[0]["chave"], me.ENVOLTORIA)
        tipos = {c["tipo"] for c in combos}
        self.assertIn("ultima", tipos)
        self.assertIn("servico", tipos)
        for c in combos[1:]:
            self.assertTrue(c["descricao"], f"combinação sem descrição: {c['chave']}")

    def test_um_verbete_por_elemento_dimensionado(self):
        nomes = {e.nome for e in self.projeto.elementos}
        self.assertEqual(set(self.mapa["elementos"]), nomes)

    def test_sem_analise_explica_o_motivo(self):
        vazio = me.mapa_de_esforcos(type("P", (), {"esforcos": {}, "elementos": []})())
        self.assertFalse(vazio["ok"])
        self.assertIn("galpão dimensionado", vazio["motivo"])


class TestValoresBatemComOCalculo(BaseMapa):
    """O mapa não pode contar uma história diferente da do memorial."""

    def test_pilar_e_viga_iguais_a_envoltoria_do_calculo(self):
        esf = self.projeto.esforcos
        viga = self.mapa["elementos"]["Viga do pórtico"]["valores"][me.ENVOLTORIA]
        pilar = self.mapa["elementos"]["Pilar"]["valores"][me.ENVOLTORIA]
        self.assertAlmostEqual(viga["M"], esf["viga"]["M"] / 100.0, delta=0.5)
        self.assertAlmostEqual(viga["V"], esf["viga"]["V"], delta=0.5)
        self.assertAlmostEqual(pilar["M"], esf["pilar"]["M"] / 100.0, delta=0.5)
        self.assertAlmostEqual(pilar["N"], esf["pilar"]["N"], delta=0.5)

    def test_viga_nao_conta_o_momento_da_misula(self):
        # a mísula tem seção maior e é verificada com a ligação de joelho; se entrasse
        # na conta da viga, o painel mostraria o momento do joelho no lugar do da viga
        viga = self.mapa["elementos"]["Viga do pórtico"]["valores"][me.ENVOLTORIA]["M"]
        joelho = self.projeto.esforcos["joelho_kNm"]
        self.assertLess(viga, 1.6 * joelho)
        self.assertIn("misula_esq", self.mapa["elementos"]["Viga do pórtico"]["barras"])

    def test_aproveitamento_e_o_do_dimensionamento(self):
        for e in self.projeto.elementos:
            self.assertAlmostEqual(self.mapa["elementos"][e.nome]["aproveitamento"],
                                   round(e.razao, 3), places=3)

    def test_terca_e_longarina_trazem_momento_e_cortante(self):
        # esses elementos não guardam M em `esforcos`: vêm dos dados da verificação
        for nome in ("Terça", "Longarina de fechamento"):
            d = self.mapa["elementos"][nome]["dimensionamento"]
            self.assertGreater(d["M"], 0.0, nome)
            self.assertGreater(d["V"], 0.0, nome)

    def test_terca_e_longarina_tem_diagrama_proprio(self):
        """Fora do pórtico, cada peça leva o seu diagrama de viga biapoiada.

        O pico tem de fechar com o momento que dimensionou a peça (q·L²/8): é a mesma
        conta, e divergir significaria desenhar na tela algo que o memorial não diz.
        """
        for nome in ("Terça", "Longarina de fechamento"):
            d = self.mapa["elementos"][nome]["diagrama"]
            self.assertIsNotNone(d, nome)
            self.assertEqual(d["modelo"], "viga biapoiada")
            self.assertEqual(len(d["s"]), me.ESTACOES)
            self.assertEqual(d["s"][0], 0.0)
            self.assertEqual(d["s"][-1], 1.0)
            self.assertAlmostEqual(d["M"][0], 0.0, places=6, msg="apoio não tem momento")
            self.assertAlmostEqual(d["M"][-1], 0.0, places=6)
            pico = max(d["M"])
            self.assertAlmostEqual(pico, self.mapa["elementos"][nome]["dimensionamento"]["M"],
                                   delta=max(0.05, pico * 0.02), msg=nome)
            # cortante máximo nos apoios, com sinais opostos, e nulo no meio
            self.assertAlmostEqual(d["V"][0], -d["V"][-1], places=6)
            self.assertAlmostEqual(d["V"][me.ESTACOES // 2], 0.0, places=6)
            self.assertIn(d["caso"], ("gravidade", "sucção", "pressão do vento"))

    def test_pecas_do_portico_nao_repetem_diagrama(self):
        # pilar e viga já têm o seu em `portico.barras`; repetir aqui seria outra fonte
        for nome in ("Pilar", "Viga do pórtico"):
            self.assertIsNone(self.mapa["elementos"][nome]["diagrama"], nome)

    def test_contraventamento_nao_inventa_diagrama(self):
        # só trabalham à tração: uma faixa de normal constante não diria nada
        for nome in ("Contraventamento de cobertura", "Contraventamento vertical"):
            self.assertIsNone(self.mapa["elementos"][nome]["diagrama"], nome)

    def test_contraventamento_traz_a_tracao(self):
        for nome in ("Contraventamento de cobertura", "Contraventamento vertical"):
            self.assertGreater(self.mapa["elementos"][nome]["dimensionamento"]["N"], 0.0)


class TestPorticoEDiagramas(BaseMapa):
    def test_geometria_em_milimetros_no_plano_do_portico(self):
        g = self.projeto.dados
        barras = {b["rotulo"]: b for b in self.mapa["portico"]["barras"]}
        pilar = barras["pilar_esq"]
        self.assertEqual(pilar["ini"], [0.0, 0.0, 0.0])
        self.assertAlmostEqual(pilar["fim"][2], g.pe_direito * 1000, delta=1.0)
        self.assertEqual(pilar["fim"][0], 0.0)            # o pórtico vem no plano x = 0
        # a cumeeira está no meio do vão, mais alta pela inclinação
        viga = barras["viga_esq"]
        self.assertAlmostEqual(viga["fim"][1], g.vao * 1000 / 2, delta=1.0)
        self.assertGreater(viga["fim"][2], g.pe_direito * 1000)

    def test_normal_unitaria_e_perpendicular(self):
        for b in self.mapa["portico"]["barras"]:
            n = b["normal"]
            self.assertAlmostEqual(math.hypot(n[1], n[2]), 1.0, places=3)
            d = (b["fim"][1] - b["ini"][1], b["fim"][2] - b["ini"][2])
            L = math.hypot(*d) or 1.0
            self.assertAlmostEqual((d[0] * n[1] + d[1] * n[2]) / L, 0.0, places=3)

    def test_um_portico_por_posicao_ao_longo_do_galpao(self):
        xs = self.mapa["portico"]["xs_mm"]
        self.assertEqual(len(xs), self.projeto.dados.n_porticos)
        self.assertEqual(xs[0], 0.0)
        self.assertAlmostEqual(xs[-1], self.projeto.dados.comprimento * 1000, delta=1.0)

    def test_diagramas_amostrados_de_ponta_a_ponta(self):
        for b in self.mapa["portico"]["barras"]:
            d = b["diagramas"]["C1 gravidade"]
            self.assertEqual(len(d["s"]), me.ESTACOES)
            self.assertEqual(d["s"][0], 0.0)
            self.assertEqual(d["s"][-1], 1.0)
            for g in ("M", "V", "N"):
                self.assertEqual(len(d[g]), me.ESTACOES)

    def test_envoltoria_envolve_as_combinacoes(self):
        ultimas = [c["chave"] for c in self.mapa["combinacoes"] if c["tipo"] == "ultima"]
        for b in self.mapa["portico"]["barras"]:
            env = b["diagramas"][me.ENVOLTORIA]
            for i in range(me.ESTACOES):
                for g in ("M", "V", "N"):
                    valores = [b["diagramas"][c][g][i] for c in ultimas]
                    self.assertLessEqual(env[g + "_min"][i], min(valores) + 1e-6)
                    self.assertGreaterEqual(env[g + "_max"][i], max(valores) - 1e-6)

    def test_momento_da_viga_tem_sinal_dos_dois_lados(self):
        # gravidade traciona embaixo no meio do vão e em cima no joelho: o diagrama
        # precisa mudar de sinal, senão o desenho estaria de um lado só
        d = {b["rotulo"]: b for b in self.mapa["portico"]["barras"]}["viga_esq"]
        M = d["diagramas"]["C1 gravidade"]["M"]
        self.assertLess(min(M), 0.0)
        self.assertGreater(max(M), 0.0)


class TestDeformadaECargas(BaseMapa):
    def test_deformada_presa_nos_apoios(self):
        d = self.mapa["deformada"]["C1 gravidade"]
        barras = {b["rotulo"]: b for b in d["barras"]}
        base = barras["pilar_esq"]["d"][0]                # base rotulada: não anda
        self.assertAlmostEqual(math.hypot(base[1], base[2]), 0.0, places=3)
        self.assertGreater(d["maior_mm"], 0.0)
        self.assertGreaterEqual(d["escala_sugerida"], 1.0)

    def test_viga_desce_sob_gravidade(self):
        barras = {b["rotulo"]: b
                  for b in self.mapa["deformada"]["C1 gravidade"]["barras"]}
        meio = barras["viga_esq"]["d"][me.ESTACOES // 2]
        self.assertLess(meio[2], 0.0, "a viga deveria descer na combinação de gravidade")

    def test_flecha_da_viga_na_ordem_de_grandeza_do_vao(self):
        # nada de deformada absurda: a flecha fica entre L/1000 e L/100
        vao_mm = self.projeto.dados.vao * 1000
        maior = self.mapa["deformada"]["C1 gravidade"]["maior_mm"]
        self.assertGreater(maior, vao_mm / 1000.0)
        self.assertLess(maior, vao_mm / 100.0)

    def test_cargas_por_barra_em_kn_por_metro(self):
        cargas = self.mapa["cargas"]["C1 gravidade"]
        vigas = [c for c in cargas if c["barra"].startswith("viga")]
        self.assertTrue(vigas)
        for c in vigas:
            self.assertLess(c["q_kN_m"], 0.0, "gravidade aponta para baixo")
            self.assertLess(abs(c["q_kN_m"]), 100.0, "kN/m, não kN/cm")
            self.assertTrue(c["descricao"])

    def test_cada_carga_traz_a_direcao_no_espaco_do_editor(self):
        # o modelo do pórtico é plano (x = vão, y = altura); no editor isso é Y e Z.
        # Sem o vetor pronto, "global_y" (a vertical) seria desenhado deitado.
        for caso, cargas in self.mapa["cargas"].items():
            for c in cargas:
                eixo = c["eixo"]
                self.assertEqual(eixo[0], 0.0, "o pórtico é plano")
                self.assertAlmostEqual(math.hypot(eixo[1], eixo[2]), 1.0, places=3)
                if c["direcao"] == "global_y":
                    self.assertEqual(eixo, [0.0, 0.0, 1.0], caso)
                if c["direcao"] == "global_x":
                    self.assertEqual(eixo, [0.0, 1.0, 0.0], caso)

    def test_peso_proprio_aponta_para_baixo(self):
        for c in self.mapa["cargas"]["C1 gravidade"]:
            z = c["q_kN_m"] * c["eixo"][2]
            self.assertLess(z, 0.0, f"{c['barra']} {c['direcao']}")

    def test_perpendicular_e_o_eixo_local_do_solver(self):
        # a normal dos diagramas aponta para a face tracionada; a da carga
        # perpendicular é o eixo local y do solver, que é o oposto dela
        barras = {b["rotulo"]: b for b in self.mapa["portico"]["barras"]}
        chave = next(c["chave"] for c in self.mapa["combinacoes"]
                     if c["chave"].startswith("C2"))
        perpendiculares = [c for c in self.mapa["cargas"][chave]
                           if c["direcao"] == "perpendicular"]
        self.assertTrue(perpendiculares, "o vento no telhado é perpendicular à água")
        for c in perpendiculares:
            normal = barras[c["barra"]]["normal"]
            self.assertAlmostEqual(c["eixo"][1], -normal[1], places=3)
            self.assertAlmostEqual(c["eixo"][2], -normal[2], places=3)

    def test_vento_aparece_na_combinacao_de_succao(self):
        chave = next(c["chave"] for c in self.mapa["combinacoes"]
                     if c["chave"].startswith("C2"))
        barras = {c["barra"] for c in self.mapa["cargas"][chave]}
        self.assertTrue({"pilar_esq", "pilar_dir"} & barras)

    def test_servico_traz_o_deslocamento_e_o_limite(self):
        d = self.mapa["servico"]["deslocamento"]
        self.assertIn("u_cm", d)
        self.assertIn("limite_cm", d)
        self.assertTrue(d["criterio"].startswith("H/"))


if __name__ == "__main__":
    unittest.main()
