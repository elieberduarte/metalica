# -*- coding: utf-8 -*-
"""O IFC do export PADRÃO do Tekla (Mezanino Drugovich, 11/11/2026; OBRA · MEZANINO DRUGOVICH).

O trecho `dados_ifc/tekla_drugovich_trecho.ifc` (Tekla 2025 SP7, IFC2x3 CoordinationView, Assemblies:On) tem os conjuntos
0065A (viga W250×17,9 + chapa CH22 + 1 grupo de parafusos), 0029A (viga W310×38,7 com os enrijecedores CH1 recortados), 0044A
(pilar W150×18 com a placa de base e os "só furo") e 0001A (o parabolt PBA_1/2"X5"_ANCORA) com a porca e a arruela soltas dele.

Antes da correção: o perfil vinha do Name ("VIGA", "COLUNA", "CHAPA") — a lista saía sem perfil e sem conjunto, "VIGA
15.594 kg"; o enrijecedor de 150 × 288 vinha com os eixos a 45° e o retângulo de corte (o bruto) 249 × 281 — a CH8×150 com
927 kg na obra, no lugar de 565; o grupo de 3 parafusos era 1 sólido sem tamanho; o "só furo" e as 1.261 soldas viravam porca
e arruela soltas; o parabolt era barra redonda de 0 kg, com a porca e a arruela do kit como peças de aço."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from ifc.importar import importar  # noqa: E402
from nucleo3d.modelo import Chapa  # noqa: E402

TRECHO = os.path.join(AQUI, "dados_ifc", "tekla_drugovich_trecho.ifc")


def _fix(e):
    return (e.atributos or {}).get("tipo_ifc") == "IfcMechanicalFastener"


class TestTeklaPadrao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = importar(TRECHO)
        cls.ents = list(cls.doc.entidades.values())

    def test_perfil_posicao_e_conjunto_pelo_description_e_tag(self):
        vigas = {(e.atributos.get("marcas") or {}).get("posicao"): e.atributos["marcas"] for e in self.ents
                 if (e.atributos or {}).get("tipo_ifc") in ("IfcBeam", "IfcColumn") and not _fix(e)}
        self.assertEqual(vigas["W18"]["perfil"], "W 250×17,9")
        self.assertEqual(vigas["W18"]["conjunto"], "0065A")
        self.assertEqual(vigas["W33"]["perfil"], "W 310×38,7")
        self.assertEqual(vigas["W33"]["conjunto"], "0029A")
        self.assertEqual(vigas["W10"]["perfil"], "W 150×18,0")

    def test_chapa_com_o_conjunto_e_sem_o_id_interno_como_posicao(self):
        chapas = [e for e in self.ents if isinstance(e, Chapa)]
        self.assertTrue(chapas)
        for c in chapas:
            mk = c.atributos.get("marcas") or {}
            self.assertIn(mk.get("conjunto"), ("0065A", "0029A", "0044A"))
            self.assertFalse(str(mk.get("posicao") or "").startswith("ID"), mk)

    def test_enrijecedor_recortado_com_os_eixos_nos_lados(self):
        # o CH1 de 150 × 288 (recortado nos cantos): o retângulo do contorno, nos eixos da chapa, é 150 × 288
        ch1 = [e for e in self.ents if isinstance(e, Chapa) and (e.atributos.get("marcas") or {}).get("perfil") == "CH 8x150"]
        self.assertEqual(len(ch1), 18)
        for c in ch1:
            xs = [p[0] for p in c.contorno]
            ys = [p[1] for p in c.contorno]
            self.assertEqual(sorted((round(max(xs) - min(xs)), round(max(ys) - min(ys)))), [150, 288])

    def test_grupo_de_parafusos_vira_um_por_parafuso(self):
        par = [e for e in self.ents if _fix(e) and (e.atributos or {}).get("parafuso")]
        self.assertEqual(len(par), 12)                     # 2 grupos do trecho (o "Bolt count" deles)
        for p in par:
            self.assertEqual(p.nome, "BOLT (A325N) 12.7x44.5")
            self.assertEqual(p.atributos["parafuso"]["d"], 12.7)
        self.assertEqual(self.doc.metadados["importacao"]["tekla"]["furos_sem_parafuso"], 4)

    def test_parabolt_com_o_kit_e_sem_as_soldas(self):
        pb = [e for e in self.ents if _fix(e) and (e.atributos or {}).get("parabolt")]
        self.assertEqual([e.nome for e in pb], ["PARABOLT 12.7x127"])
        nomes = {str(e.nome).upper() for e in self.ents}
        self.assertFalse({"PORCA", "ARRUELA", "WELD"} & nomes)
        t = self.doc.metadados["importacao"]["tekla"]
        self.assertEqual((t["porcas_arruelas_do_kit"], t["soldas"]), (2, 68))

    def test_lista_de_materiais(self):
        from nucleo2d import detalhar
        L = detalhar.levantar(self.doc, regra_tercas=False)
        ac = L.get("acessorios") or {}
        self.assertEqual(ac.get("BOLT (A325N) 12.7x44.5"), 12)
        self.assertEqual(ac.get("PARABOLT 12.7x127"), 1)
        self.assertFalse([k for k in ac if k.startswith(("Porca", "Arruela"))], ac)
        pesos = {}
        for p in L["posicoes"]:
            pesos[str(p.perfil)] = pesos.get(str(p.perfil), 0.0) + float(p.peso_total or 0)
        self.assertAlmostEqual(pesos["CH 8x150"], 18 * 0.150 * 0.288 * 8 * 7.85, delta=0.5)   # o bruto 150 × 288, não 249 × 281
        self.assertNotIn("VIGA", pesos)


class TestFuncoes(unittest.TestCase):
    def test_angulo_do_retangulo_girado(self):
        import math
        from ifc.importar import angulo_do_menor_retangulo
        c, s = math.cos(math.radians(45)), math.sin(math.radians(45))
        ret = [(0, 0), (150, 0), (150, 288), (0, 288)]
        girado = [(x * c - y * s, x * s + y * c) for x, y in ret]
        self.assertAlmostEqual(abs(angulo_do_menor_retangulo(girado)), math.radians(45), places=6)
        self.assertEqual(angulo_do_menor_retangulo(ret), 0.0)

    def test_medidas_em_polegada(self):
        from ifc.importar import bitola_nominal, medida_do_chumbador_tekla
        self.assertEqual(bitola_nominal(15.9, 'PARAF_5/8"X1"3/4_A325'), 15.875)
        self.assertEqual(medida_do_chumbador_tekla('PBA_1/2"X5"_ANCORA', {}), (12.7, 127.0))


if __name__ == "__main__":
    unittest.main()
