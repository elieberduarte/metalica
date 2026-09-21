# -*- coding: utf-8 -*-
"""Testes do modelo 3D do galpão (`nucleo3d.de_projeto`).

O caso de referência é o galpão do Capítulo 16 do manual (20 m de vão, 40 m de
comprimento, pé-direito 6 m, pórticos a cada 5 m, inclinação de 10 %), dimensionado
pelo orquestrador. As contagens esperadas são recalculadas aqui pelas mesmas regras
das pranchas (`saida.desenhos`), e não copiadas do módulo testado.
"""
import copy
import math
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from nucleo.galpao import dimensionar                                     # noqa: E402
from nucleo.modelo_galpao import DadosGalpao                              # noqa: E402
from nucleo3d import de_projeto as dp                                     # noqa: E402
from nucleo3d import geometria as g                                       # noqa: E402
from nucleo3d.modelo import Barra, Chapa, Documento, Solido               # noqa: E402


def _cap16(**ajustes) -> DadosGalpao:
    base = dict(nome="Galpão do Capítulo 16", vao=20.0, comprimento=40.0,
                pe_direito=6.0, espacamento_porticos=5.0, inclinacao=10.0,
                v0=40.0, categoria_rugosidade="II", classe="B",
                telha="trapezoidal 0,50 mm", sobrecarga_cobertura=0.25)
    base.update(ajustes)
    return DadosGalpao(**base)


def _vaos_contraventados(n_porticos: int) -> int:
    n_vaos = n_porticos - 1
    return len({0, n_vaos - 1, max(0, (n_vaos - 1) // 2)}) if n_vaos >= 2 else 1


def _pontos(e):
    if isinstance(e, Barra):
        return [e.inicio, e.fim]
    if isinstance(e, Chapa):
        return [e.origem, e.eixo_x, e.eixo_y] + [(x, y, 0.0) for x, y in e.contorno]
    if isinstance(e, Solido):
        return list(e.vertices)
    return []


class TestGalpaoCap16(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.projeto = dimensionar(_cap16())
        assert cls.projeto.erros == [], cls.projeto.erros
        cls.doc = dp.modelo_do_galpao(cls.projeto)
        cls.d = cls.projeto.dados

    def _por_marca(self, marca):
        return [e for e in self.doc.entidades.values() if e.nome == marca]

    def test_pilares_dois_por_portico(self):
        pil = [b for b in self.doc.barras if b.papel == "pilar"]
        self.assertEqual(self.d.n_porticos, 9)
        self.assertEqual(len(pil), 2 * self.d.n_porticos)
        perfil = self.projeto.elemento("Pilar").perfil
        for b in pil:
            self.assertEqual(b.perfil, perfil)
            self.assertEqual(b.nome, "P1")
            self.assertAlmostEqual(b.comprimento, 6000.0, places=6)
            self.assertTrue(b.vertical)

    def test_vigas_duas_aguas_e_misulas(self):
        vig = [b for b in self.doc.barras if b.papel == "viga"]
        self.assertEqual(len(vig), 2 * self.d.n_porticos)
        for b in vig:
            self.assertAlmostEqual(b.comprimento, self.d.comprimento_agua * 1000, places=3)
        self.assertEqual(len(self._por_marca("M1")), 2 * self.d.n_porticos)
        self.assertEqual(len(self._por_marca("M2")), 2 * self.d.n_porticos)

    def test_tercas_no_espacamento_real(self):
        terca = self.projeto.elemento("Terça")
        linhas = terca.geometria["linhas"]                   # por água
        tercas = [b for b in self.doc.barras if b.papel == "terça"]
        self.assertEqual(len(tercas), linhas * 2 * (self.d.n_porticos - 1))
        for b in tercas:
            self.assertEqual(b.camada, "Terças")
            self.assertEqual(b.perfil, terca.perfil)
        # mesmas posições da planta de cobertura: 200 mm do beiral, 250 mm da cumeeira
        passo = self.doc.metadados["passo_tercas_mm"]
        util = 10000.0 - 200.0 - 250.0
        n = math.ceil(util / (self.projeto.cargas["espacamento_tercas_real"] * 1000) - 1e-6)
        self.assertAlmostEqual(passo, util / n, places=1)
        self.assertLessEqual(passo, self.projeto.cargas["espacamento_tercas_real"] * 1000)

    def test_contraventamentos_nos_paineis_do_calculo(self):
        """Vãos, painéis e quantidade vêm do cálculo quando ele os publica; senão, da
        regra das pranchas (vãos extremos e central, round(vão/espaçamento) painéis)."""
        gc = self.projeto.elemento("Contraventamento de cobertura").geometria
        gv = self.projeto.elemento("Contraventamento vertical").geometria
        cob = [b for b in self.doc.barras if b.nome == "CC"]
        ver = [b for b in self.doc.barras if b.nome == "CV"]
        if gc.get("vaos_contraventados"):
            vaos_esp = {v - 1 for v in gc["vaos_contraventados"]}
            n_pain = gc["paineis"]
            self.assertEqual(len(cob), gc["quantidade"])
        else:
            vaos_esp = {0, 3, 7}                               # extremos e central
            n_pain = max(2, round(self.d.vao / self.d.espacamento_porticos))
        self.assertEqual(len(vaos_esp), _vaos_contraventados(self.d.n_porticos))
        self.assertEqual(len(cob), len(vaos_esp) * n_pain * 2)
        if gv.get("vaos_contraventados"):
            self.assertEqual(len(ver), gv["quantidade"])
        else:
            self.assertEqual(len(ver), len(vaos_esp) * 2 * 2)  # 2 paredes × X
        xs = self.doc.metadados["porticos_x_mm"]
        vaos = {(round(min(b.inicio[0], b.fim[0]) / 5000)) for b in cob}
        self.assertEqual(vaos, vaos_esp)
        self.assertEqual(self.doc.metadados["paineis_cobertura"], n_pain)
        perfil = self.projeto.elemento("Contraventamento de cobertura").perfil
        for b in cob + ver:
            self.assertEqual(b.papel, "contraventamento")
            self.assertEqual(b.camada, "Contraventamento")
        self.assertEqual(cob[0].perfil, perfil)
        self.assertEqual(len(xs), self.d.n_porticos)

    def test_contraventamento_segue_a_geometria_publicada(self):
        """Contrato do cálculo: `paineis`, `vaos_contraventados` (a partir de 1) e
        `quantidade`. Aqui o cálculo pede mais painéis que a regra das pranchas (6 em
        vez de 4) e só os vãos extremos, e o 3D tem de obedecer."""
        p = copy.deepcopy(self.projeto)
        p.elemento("Contraventamento de cobertura").geometria.update(
            {"paineis": 6, "vaos_contraventados": [1, 8], "quantidade": 24})
        p.elemento("Contraventamento vertical").geometria.update(
            {"vaos_contraventados": [1, 8], "quantidade": 8})
        doc = dp.modelo_do_galpao(p, com_fechamento=False)
        cob = [b for b in doc.barras if b.nome == "CC"]
        ver = [b for b in doc.barras if b.nome == "CV"]
        self.assertEqual(len(cob), 24)                         # 2 vãos × 6 painéis × X
        self.assertEqual(len(ver), 8)                          # 2 vãos × 2 paredes × X
        self.assertEqual({round(min(b.inicio[0], b.fim[0]) / 5000) for b in cob}, {0, 7})
        # 6 painéis: nós a cada vão/6 no sentido do vão
        ys = sorted({round(min(b.inicio[1], b.fim[1]), 3) for b in cob})
        self.assertEqual(len(ys), 6)
        self.assertAlmostEqual(ys[1] - ys[0], 20000.0 / 6, places=3)
        self.assertEqual(doc.metadados["vaos_contraventados"], [1, 8])
        # a versão antiga do cálculo, sem `vaos_contraventados`, não é lida
        q = copy.deepcopy(self.projeto)
        q.elemento("Contraventamento de cobertura").geometria = {"paineis": 2}
        doc_q = dp.modelo_do_galpao(q, com_fechamento=False)
        self.assertEqual(doc_q.metadados["paineis_cobertura"], 4)

    def test_correntes_e_longarinas(self):
        terca = self.projeto.elemento("Terça")
        n_corr = terca.geometria["n_correntes"]
        linhas = terca.geometria["linhas"]
        tc = self._por_marca("TC")
        # por vão e por linha de corrente: (linhas − 1) trechos + 1 tirante, por água
        self.assertEqual(len(tc), (self.d.n_porticos - 1) * n_corr * 2 * linhas)
        lg = [b for b in self.doc.barras if b.papel == "longarina"]
        geo_l = self.projeto.elemento("Longarina").geometria
        # as fiadas ficam nas alturas publicadas pelo cálculo, no meio de cada faixa de
        # parede, as mesmas da elevação longitudinal
        self.assertEqual(len(lg), geo_l["fiadas_por_lado"] * 2 * (self.d.n_porticos - 1))
        cotas_mm = [round(c * 1000) for c in geo_l["cotas_fiadas_m"]]
        self.assertEqual(sorted({round(b.inicio[2]) for b in lg}), cotas_mm)

    def test_chapas_com_furos(self):
        base = self._por_marca("CH3")
        self.assertEqual(len(base), 2 * self.d.n_porticos)
        n_ch = self.projeto.base.dados["n_chumbadores"]
        geo_base = self.projeto.base.dados["geometria"]
        for ch in base:
            self.assertEqual(len(ch.furos), n_ch)
            self.assertAlmostEqual(ch.espessura, geo_base["t_mm"])
            (x0, y0), (x1, y1) = g.caixa_envolvente(ch.contorno)
            self.assertAlmostEqual(x1 - x0, geo_base["B_mm"], places=3)
            for f in ch.furos:
                self.assertAlmostEqual(f["diametro"], self.projeto.base.dados["furo_placa_mm"])
        for marca in ("CH1", "CH2"):
            chapas = self._por_marca(marca)
            self.assertEqual(len(chapas), 2 * self.d.n_porticos)
            for ch in chapas:
                self.assertEqual(len(ch.furos), 8)             # 4 fileiras × 2
        lig = self.projeto.ligacoes["viga-pilar"].dados
        ch = self._por_marca("CH1")[0]
        self.assertAlmostEqual(ch.espessura, lig["t_chapa"] * 10)
        xs_furo = sorted({round(f["x"], 3) for f in ch.furos})
        self.assertAlmostEqual(xs_furo[1] - xs_furo[0], lig["gabarito"] * 10, places=3)
        # furo aberto de verdade: a malha desconta o furo
        v, f = g.malha_chapa(ch)
        bruto = g.area_contorno(ch.contorno) * ch.espessura
        self.assertLess(g.volume_malha(v, f), bruto - 1.0)

    def test_pedestais_e_fechamento(self):
        ped = self._por_marca("PD")
        self.assertEqual(len(ped), 2 * self.d.n_porticos)
        for s in ped:
            self.assertEqual(s.camada, "Referência")
            self.assertNotIn("peso_kg", s.atributos)
            self.assertAlmostEqual(s.atributos["peso_concreto_kg"],
                                   s.atributos["volume_m3"] * dp.RHO_CONCRETO, delta=1.0)
            self.assertEqual(s.material, "Concreto")
            self.assertLessEqual(max(v[2] for v in s.vertices), 0.0)
        fech = [e for e in self.doc.entidades.values() if e.camada == "Fechamento"]
        self.assertEqual(len(fech), 6)                         # 2 águas, 2 laterais, 2 oitões
        sem = dp.modelo_do_galpao(self.projeto, com_fechamento=False)
        self.assertEqual(len([e for e in sem.entidades.values()
                              if e.camada == "Fechamento"]), 0)

    def test_caixa_envolvente(self):
        """Pórtico: vão × comprimento × altura de cumeeira dentro de 1 %."""
        (x0, y0, z0), (x1, y1, z1) = dp.caixa_do_portico(self.doc)
        self.assertLess(abs((x1 - x0) / (self.d.comprimento * 1000) - 1), 0.01)
        self.assertLess(abs((y1 - y0) / (self.d.vao * 1000) - 1), 0.01)
        self.assertLess(abs((z1 - z0) / (self.d.altura_cumeeira * 1000) - 1), 0.01)
        # o documento inteiro só passa disso pelo que tem de passar (terça, telha,
        # longarina, placa de base, pedestal): menos de 10 % em cada direção
        (X0, Y0, Z0), (X1, Y1, Z1) = self.doc.caixa()
        self.assertLess((X1 - X0) / (x1 - x0), 1.10)
        self.assertLess((Y1 - Y0) / (y1 - y0), 1.10)
        self.assertLess((Z1 - Z0) / (z1 - z0), 1.20)
        self.assertAlmostEqual(Z0, -dp.ALTURA_PEDESTAL)

    def test_peso_bate_com_resumo_do_projeto(self):
        """Peso de **aço** do 3D × resumo_pesos dentro de 10 %.

        Só o aço entra na soma: o pedestal de concreto não tem `peso_kg` (tem
        `volume_m3` e `peso_concreto_kg`), senão o modelo pesaria três vezes o galpão.
        A diferença que sobra, perto de 8 % no Capítulo 16, é esperada: o resumo estima
        chapas (5 %) e parafusos (3 %) sobre o peso dos perfis, e o 3D tem as mísulas e
        as chapas modeladas de verdade (cerca de 2,8 t) e nenhum parafuso. Os perfis
        principais e as correntes, esses, têm de bater com a lista de material.
        """
        p3d = dp.pesos(self.doc)
        total = self.projeto.resumo_pesos["total_kg"]
        self.assertLess(abs(p3d["total_aco_kg"] / total - 1), 0.10,
                        f"3D {p3d['total_aco_kg']} × resumo {total}")
        lista = {pc.marca: pc.peso_total_kg for pc in self.projeto.lista_material}
        for marca in ("P1", "V1", "T1", "L1"):
            self.assertLess(abs(p3d[marca] / lista[marca] - 1), 0.01, marca)
        # correntes: mesma quantidade e mesmo ø 16 (kg/m) da lista. O total não bate
        # peça a peça porque a lista usa o espaçamento de cálculo (1,675 m) para toda
        # corrente, e o 3D mede cada trecho entre terças na posição da planta
        # (≈ 1,60 m) e o tirante de cumeeira, que é mais curto.
        tc = [b for b in self.doc.barras if b.nome == "TC"]
        peca = next(pc for pc in self.projeto.lista_material if pc.marca == "TC")
        self.assertEqual(len(tc), peca.quantidade)
        kg_m_3d = sum(b.atributos["peso_kg"] for b in tc) / sum(b.comprimento for b in tc) * 1000
        kg_m_lista = peca.peso_unit_kg / peca.comprimento_m
        self.assertLess(abs(kg_m_3d / kg_m_lista - 1), 0.01)

    def test_peso_pela_geometria_das_barras(self):
        """Peso de atributo (catálogo) × volume da malha, dentro de 3 %."""
        vistos = set()
        for b in self.doc.barras:
            if b.perfil in vistos:
                continue
            vistos.add(b.perfil)
            v, f = g.malha_barra(b)
            peso_geo = g.volume_malha(v, f) * g.RHO_MM3
            self.assertLess(abs(peso_geo / b.atributos["peso_kg"] - 1), 0.03, b.perfil)

    def test_atributos_nome_camada_material(self):
        for e in self.doc.entidades.values():
            self.assertTrue(e.nome, e)
            self.assertEqual(e.atributos.get("marca"), e.nome)
            self.assertTrue(e.atributos.get("elemento"), e.nome)
            self.assertIn(e.camada, self.doc.camadas)
            self.assertIn(e.material, self.doc.materiais)
            if e.camada in ("Referência", "Fechamento"):
                # concreto e fechamento: volume, nunca peso de aço
                self.assertNotIn("peso_kg", e.atributos, e.nome)
                self.assertGreater(e.atributos.get("volume_m3", 0), 0, e.nome)
            else:
                self.assertGreater(e.atributos.get("peso_kg", 0), 0, e.nome)

    def test_nenhuma_coordenada_invalida(self):
        for e in self.doc.entidades.values():
            for p in _pontos(e):
                self.assertTrue(all(math.isfinite(c) for c in p), (e.nome, p))
            v, f = g.malha(e)
            for p in v:
                self.assertTrue(all(math.isfinite(c) for c in p), e.nome)

    def test_malhas_fechadas_e_para_fora(self):
        vistos = set()
        for e in self.doc.entidades.values():
            chave = (e.nome, getattr(e, "perfil", ""))
            if chave in vistos and e.nome not in ("CC", "TL", "FC"):
                continue
            vistos.add(chave)
            v, f = g.malha(e)
            diag = g.conferir_malha(v, f)
            self.assertTrue(diag["fechada"], e.nome)
            self.assertGreater(diag["volume"], 0, e.nome)

    def test_serializacao_ida_e_volta(self):
        de_novo = Documento.de_dict(self.doc.dict())
        self.assertEqual(de_novo.estatisticas(), self.doc.estatisticas())
        self.assertEqual(dp.pesos(de_novo), dp.pesos(self.doc))
        b = de_novo.barras[0]
        v, f = g.malha_barra(b)
        self.assertTrue(g.conferir_malha(v, f)["fechada"])


class TestOutrosGalpoes(unittest.TestCase):

    def test_sem_misula_base_engastada(self):
        p = dimensionar(_cap16(vao=12.0, comprimento=24.0, pe_direito=5.0,
                               espacamento_porticos=6.0, inclinacao=8.0,
                               com_misula=False, base_rotulada=False))
        doc = dp.modelo_do_galpao(p)
        self.assertEqual([e for e in doc.entidades.values() if e.nome == "M1"], [])
        base = [e for e in doc.chapas if e.nome == "CH3"]
        self.assertTrue(base)
        self.assertGreaterEqual(len(base[0].furos), 4)
        (x0, y0, z0), (x1, y1, z1) = dp.caixa_do_portico(doc)
        self.assertAlmostEqual(y1 - y0, 12000.0, places=3)
        self.assertAlmostEqual(z1, 5000 + 6000 * 0.08, places=3)

    def test_exemplo_sem_dimensionamento(self):
        doc = dp.exemplo()
        est = doc.estatisticas()
        self.assertGreater(est["barras"], 50)
        self.assertEqual(len([b for b in doc.barras if b.papel == "pilar"]), 2 * 6)
        self.assertFalse(doc.metadados["dimensionado"])
        for e in doc.entidades.values():
            v, _ = g.malha(e)
            self.assertTrue(all(math.isfinite(c) for p in v for c in p))

    def test_modelo_vazio(self):
        doc = dp.modelo_vazio("Novo")
        self.assertEqual(doc.nome, "Novo")
        self.assertEqual(doc.estatisticas()["entidades"], 0)
        self.assertIn("Estrutura", doc.camadas)


if __name__ == "__main__":
    unittest.main()
