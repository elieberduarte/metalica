# -*- coding: utf-8 -*-
"""Projeto recebido sem perfil escrito: reconhecimento pela geometria (0.8.8)."""
import collections
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import projeto_2d_sem_texto as ex                     # noqa: E402
from nucleo2d import dxf_ler, reconhecer              # noqa: E402
from nucleo2d.reconhecer_geo import PERFIS_PADRAO     # noqa: E402
from nucleo3d import de_vistas                        # noqa: E402


class TestGeometria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp(prefix="proj2d_geo_")
        caminho = ex.dxf(os.path.join(cls.pasta, "galpao_sem_texto.dxf"))
        texto = dxf_ler.texto_de_bytes(open(caminho, "rb").read())
        cls.des = dxf_ler.para_desenho(texto, escala=50)[0]
        cls.r = reconhecer.reconhecer(cls.des)
        reconhecer.aplicar(cls.des, cls.r)
        cls.m = reconhecer.sugerir_montagem(cls.r)

    def test_unidade_em_cm_e_tipos_das_vistas(self):
        r = self.r
        self.assertTrue(any("centímetros" in a for a in r["avisos"]))
        self.assertEqual({v["fator"] for v in r["vistas"]}, {10.0})
        self.assertEqual({v["fator_origem"] for v in r["vistas"]}, {"cm"})
        tipos = collections.Counter(v["tipo"] for v in r["vistas"])
        self.assertEqual(tipos["planta"], 1)
        self.assertEqual(tipos["elevacao"], 2)          # o interno e o oitão; o repetido fica de fora
        self.assertEqual(tipos["lateral"], 1)
        self.assertEqual(r["resumo"]["repetidas"], 1)
        self.assertEqual(r["resumo"]["textos_de_perfil"], 0)

    def test_eixos_da_planta_pelas_marcas(self):
        planta = next(v for v in self.r["vistas"] if v["tipo"] == "planta")
        rot = sorted(e["rotulo"] for e in planta["eixos"])
        self.assertEqual(rot, ["1", "2", "3", "4", "5", "A", "B", "C"])
        ys = sorted(e["pos"] for e in planta["eixos"] if e["rotulo"].isdigit())
        self.assertEqual(ys, [i * ex.MODULO for i in range(ex.N_EIXOS)])

    def test_papeis_sem_perfil(self):
        r = self.r
        por = collections.defaultdict(collections.Counter)
        for b in r["barras"]:
            self.assertEqual(b["perfil"], "")
            self.assertEqual(b["fonte"], "geometria")
            por[b["vista"]][b["papel"]] += 1
        tipo = {v["id"]: v["tipo"] for v in r["vistas"]}
        interno = min((vid for vid in por if tipo[vid] == "elevacao"), key=lambda vid: por[vid]["pilar"])
        oitao = max((vid for vid in por if tipo[vid] == "elevacao"), key=lambda vid: por[vid]["pilar"])
        self.assertEqual(por[interno]["pilar"], 3)      # a linha de cota em pé não é pilar
        self.assertEqual(por[interno]["banzo"], 3)
        self.assertEqual(por[interno]["montante"], 15)
        self.assertEqual(por[interno]["diagonal"], 14)
        self.assertEqual(por[oitao]["pilar"], 3 + len(ex.POSTES))
        self.assertEqual(por[oitao]["longarina"], len(ex.GIRTS))
        self.assertEqual(por[oitao]["contraventamento"], 4)
        planta = next(vid for vid in por if tipo[vid] == "planta")
        self.assertEqual(por[planta]["terça"], 11)
        self.assertEqual(por[planta]["contraventamento"], 8)
        self.assertEqual(por[planta]["corrente"], 4 * 10)    # 4 linhas de meio de vão partidas nas 9 terças
        lateral = next(vid for vid in por if tipo[vid] == "lateral")
        self.assertEqual(por[lateral]["pilar"], 5)
        self.assertEqual(por[lateral]["longarina"], 2)
        self.assertEqual(por[lateral]["contraventamento"], 2)
        self.assertEqual(set(r["resumo"]["sem_perfil"]), {"pilar", "banzo", "montante", "diagonal", "terça",
                                                          "contraventamento", "corrente", "longarina"})
        rec = self.des.metadados["reconhecimento"]
        self.assertEqual(rec["perfis_padrao"]["pilar"], PERFIS_PADRAO["pilar"])

    def test_montagem_interno_em_todos_os_eixos_e_oitao_nas_pontas(self):
        m = self.m
        em_pe = [x for x in m["montagens"] if x["tipo"] == "elevacao"]
        self.assertEqual([x["usar"] for x in em_pe], [True, True])
        self.assertEqual(len(em_pe[0]["origens"]), ex.N_EIXOS)
        self.assertEqual([o[1] for o in em_pe[1]["origens"]], [0.0, ex.COMPRIMENTO * 10])
        planta = next(x for x in m["montagens"] if x["tipo"] == "planta")
        self.assertTrue(planta["cobertura"])
        self.assertEqual(len(planta["eixos_corte"]), ex.N_EIXOS)

    def test_modelo_com_perfis_padrao_e_escolhidos(self):
        doc = de_vistas.modelo_das_vistas(self.des, self.m["montagens"])
        c = collections.Counter(b.papel for b in doc.barras)
        self.assertEqual(c["pilar"], 3 * ex.N_EIXOS + 2 * len(ex.POSTES))
        self.assertEqual(c["terça"], 11 * (ex.N_EIXOS - 1))
        self.assertEqual(c["banzo"], 3 * ex.N_EIXOS)
        self.assertEqual(c["longarina"], 2 * 2 * (ex.N_EIXOS - 1) + len(ex.GIRTS) * 2)
        ys = sorted({round(b.inicio[1]) for b in doc.barras if b.papel == "pilar"})
        self.assertEqual(ys, [round(i * ex.MODULO * 10) for i in range(ex.N_EIXOS)])
        for b in doc.barras:
            if b.papel == "pilar" and abs(b.inicio[0]) < 1 and b.inicio[1] < 1:
                self.assertAlmostEqual(b.comprimento, ex.H_PILAR * 10, delta=2)
            if b.papel == "terça":
                self.assertAlmostEqual(b.comprimento, ex.MODULO * 10, delta=2)
        zs = sorted({round(b.inicio[2]) for b in doc.barras if b.papel == "terça"})
        self.assertGreater(zs[-1] - zs[0], 1000)             # sobem com a cobertura
        perfis = collections.Counter(b.perfil for b in doc.barras if b.papel == "pilar")
        self.assertEqual(list(perfis), ["W 250×32,7"])
        doc2 = de_vistas.modelo_das_vistas(self.des, self.m["montagens"], perfis={"pilar": "W 200 x 26,6"})
        self.assertEqual({b.perfil for b in doc2.barras if b.papel == "pilar"}, {"W 200×26,6"})
        self.assertEqual(doc2.metadados["de_desenho"]["perfis_por_papel"], {"pilar": "W 200 x 26,6"})
        from nucleo.base import ErroDeDados
        with self.assertRaises(ErroDeDados):
            de_vistas.modelo_das_vistas(self.des, self.m["montagens"], perfis={"pilar": "XYZ 1"})

    def test_ifc(self):
        from ifc import exportar, importar
        doc = de_vistas.modelo_das_vistas(self.des, self.m["montagens"])
        caminho = exportar.exportar(doc, os.path.join(self.pasta, "galpao_geo.ifc"), projeto_nome="Galpão")
        volta = importar.importar(caminho)
        self.assertEqual(len(volta.barras), len(doc.barras))


if __name__ == "__main__":
    unittest.main()
