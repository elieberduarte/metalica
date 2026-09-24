# -*- coding: utf-8 -*-
"""Projeto recebido em DXF ou PDF → peças reconhecidas → modelo 3D → IFC."""
import base64
import collections
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import projeto_2d_exemplo as ex                       # noqa: E402
from nucleo2d import dxf_ler, pdf_ler, reconhecer     # noqa: E402
from nucleo2d.reconhecer import perfil_do_texto       # noqa: E402
from nucleo3d import de_vistas                        # noqa: E402

#: o que o galpão de exemplo tem: por pórtico 2 pilares, 3 banzos, 11 montantes e 10
#: diagonais; 5 pórticos; 11 terças partidas em 4 vãos; 8 barras de contraventamento
ESPERADO = {"pilar": 10, "banzo": 15, "montante": 55, "diagonal": 50, "terça": 44, "contraventamento": 8}


class TestPerfilEscrito(unittest.TestCase):
    def casos(self):
        return {
            "U100x50#11": "U 100×50×3,00 (FF)",
            "U200x75x25#13": "Ue 200×75×25×2,25",
            "C150X50X17X2.25": "Ue 150×50×17×2,25",
            "L50X50#3/16\"": 'L 2"×3/16"',
            "W 200 x 19,3": "W 200×19,3",
            "PILAR W 310 x 38,7": "W 310×38,7",
            "Tubo 30x30#1,5mm": "TQ 30×30×1,5",
            "Treliças U100x50x3.04#11": "U 100×50×3,00 (FF)",
            "TERÇA Ue 150x60x20x2,00": "Ue 150×60×20×2,00",
            "FERRO %%c1/2\"": 'Barra redonda ø 1/2"',
        }

    def test_notacoes_da_fabrica_e_do_projetista(self):
        for texto, nome in self.casos().items():
            texto = dxf_ler.codigos_de_texto(texto)
            p = perfil_do_texto(texto)
            self.assertIsNotNone(p, texto)
            self.assertEqual(p["perfil"].replace("ø", "Ø"), nome.replace("ø", "Ø"), texto)

    def test_perfil_duplo_e_papel_pela_palavra(self):
        p = perfil_do_texto("2U75x38#13")
        self.assertEqual(p["mult"], 2)
        self.assertEqual(perfil_do_texto("BS - U 150x60x20#13")["papel"], "banzo")
        self.assertEqual(perfil_do_texto("TERÇA Ue 150x60x20x2,00")["papel"], "terça")
        self.assertEqual(perfil_do_texto("CONTRAVENTO FERRO REDONDO Ø1/2\"")["papel"], "contraventamento")

    def test_nao_e_peca(self):
        for texto in ("FURO Ø14", "PARAFUSOS Ø3/4\" A-325", "60X35", "2500", "L 15050 #9\"", "ESC. 1:50"):
            self.assertIsNone(perfil_do_texto(texto), texto)

    def test_chapa(self):
        p = perfil_do_texto("CH 3/8\"")
        self.assertTrue(p["chapa"])
        self.assertAlmostEqual(p["espessura"], 9.52, places=1)

    def test_valores_de_cota(self):
        v = reconhecer._valores_de_cota
        self.assertEqual(v("6000"), [6000.0])
        self.assertEqual(v("6,00"), [6000.0])        # metro
        self.assertIn(2500.0, v("2.500"))
        self.assertEqual(v("ESC 1:50"), [])


class _Galpao:
    def reconhecido(self, des):
        r = reconhecer.reconhecer(des)
        reconhecer.aplicar(des, r)
        m = reconhecer.sugerir_montagem(r)
        return r, m, de_vistas.modelo_das_vistas(des, m["montagens"])

    def conferir_modelo(self, doc):
        c = collections.Counter(b.papel for b in doc.barras)
        self.assertEqual(dict(c), ESPERADO)
        # tesouras nos cinco eixos da planta, 6 m entre elas
        ys = sorted({round(b.inicio[0]) for b in doc.barras if b.papel == "pilar"})
        self.assertEqual(ys, [0, 6000, 12000, 18000, 24000])
        # pilar de 6 m com o pé em z = 0
        for b in doc.barras:
            if b.papel == "pilar":
                self.assertAlmostEqual(min(b.inicio[2], b.fim[2]), 0.0, delta=1)
                self.assertAlmostEqual(b.comprimento, ex.H_PILAR, delta=2)
        # terças em cima do banzo superior: na beirada, 6000 + 1000 + (150 + 150)/2
        zs = sorted({round(b.inicio[2]) for b in doc.barras if b.papel == "terça"})
        self.assertAlmostEqual(zs[0], ex.H_PILAR + ex.H_APOIO + 150, delta=2)
        self.assertAlmostEqual(zs[-1], ex.H_PILAR + ex.H_CUMEEIRA + 150, delta=2)
        # terça partida no eixo: uma por vão de 6 m
        for b in doc.barras:
            if b.papel == "terça":
                self.assertAlmostEqual(b.comprimento, ex.MODULO, delta=2)
        # tesouras iguais: o mesmo conjunto; pilar, terça e contraventamento: o deles
        conj = collections.defaultdict(set)
        for b in doc.barras:
            conj[b.papel].add(b.atributos["marcas"]["conjunto"])
        self.assertEqual(len(conj["banzo"] | conj["diagonal"] | conj["montante"]), 1)
        self.assertEqual(len(conj["terça"]), 1)


class TestDXF(unittest.TestCase, _Galpao):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp(prefix="proj2d_")

    def ler(self, **kw):
        caminho = ex.dxf(os.path.join(self.pasta, "galpao_%s.dxf" % "_".join(map(str, kw.values()))), **kw)
        texto = dxf_ler.texto_de_bytes(open(caminho, "rb").read())
        return dxf_ler.para_desenho(texto, escala=50)[0]

    def test_vistas_escala_e_eixos(self):
        des = self.ler()
        r = reconhecer.reconhecer(des)
        tipos = {v["tipo"]: v for v in r["vistas"]}
        self.assertEqual(set(tipos), {"planta", "trelica"})
        self.assertEqual(tipos["planta"]["fator"], 1.0)
        self.assertEqual(tipos["planta"]["fator_origem"], "cotas")
        self.assertEqual(sorted(e["rotulo"] for e in tipos["planta"]["eixos"]), ["1", "2", "3", "4", "5", "A", "B"])
        self.assertEqual(r["textos_sem_linha"], [])
        # o que herdou o perfil da camada fica a conferir
        self.assertTrue(any(b["conferir"] for b in r["barras"]))

    def test_modelo_em_mm(self):
        _r, _m, doc = self.reconhecido(self.ler())
        self.conferir_modelo(doc)

    def test_desenho_em_metro_sem_unidade(self):
        # desenhado em metro, $INSUNITS vazio: a escala sai das cotas (6000 escrito em 6 unidades)
        des = self.ler(unidade_m=True, insunits=False)
        r, _m, doc = self.reconhecido(des)
        self.assertEqual({v["fator"] for v in r["vistas"]}, {1000.0})
        self.conferir_modelo(doc)

    def test_fachada_lateral_nos_dois_lados(self):
        des = self.ler(fachada=True)
        r, m, doc = self.reconhecido(des)
        self.assertEqual(r["textos_sem_linha"], [])
        lat = next(x for x in m["montagens"] if x["tipo"] == "lateral")
        self.assertEqual([o[1] for o in lat["origens"]], [0.0, ex.VAO])
        c = collections.Counter(b.papel for b in doc.barras)
        self.assertEqual(c["pilar"], 10)                          # o pilar da fachada é o mesmo do pórtico
        self.assertEqual(doc.metadados["de_desenho"]["repetidas"], 2)
        self.assertEqual(c["longarina"], 2 * 2 * 4)               # duas alturas, dois lados, quatro vãos
        self.assertEqual(c["contraventamento"], 8 + 4)
        alturas = sorted({round(b.inicio[2]) for b in doc.barras if b.papel == "longarina"})
        self.assertEqual(alturas, [round(h) for h in ex.ALTURAS_LONGARINA])

    def test_ifc_ida_e_volta(self):
        from ifc import exportar, importar
        _r, _m, doc = self.reconhecido(self.ler())
        caminho = exportar.exportar(doc, os.path.join(self.pasta, "galpao.ifc"), projeto_nome="Galpão")
        volta = importar.importar(caminho)
        self.assertEqual(len(volta.barras), sum(ESPERADO.values()))
        perfis = collections.Counter(b.perfil for b in volta.barras)
        self.assertEqual(perfis["W 250×25,3"], 10)

    def test_reconhecer_de_novo_substitui(self):
        des = self.ler()
        r = reconhecer.reconhecer(des)
        n1 = len(reconhecer.aplicar(des, r))
        r2 = reconhecer.reconhecer(des)          # as linhas reconhecidas não entram de novo
        n2 = len(reconhecer.aplicar(des, r2))
        self.assertEqual(n1, n2)
        self.assertEqual(sum(1 for e in des.entidades.values() if (e.atributos or {}).get("reconhecido")), n2)


class TestPDF(unittest.TestCase, _Galpao):
    def test_pdf_vetorial(self):
        pasta = tempfile.mkdtemp(prefix="proj2d_pdf_")
        caminho = ex.pdf(os.path.join(pasta, "galpao.pdf"))
        des, lido = pdf_ler.para_desenho(open(caminho, "rb").read())
        self.assertEqual(lido["avisos"], [])
        self.assertEqual(lido["por_tipo"].get("circulo"), 7)            # balões dos eixos
        r, _m, doc = self.reconhecido(des)
        self.assertEqual(sorted(v["fator"] for v in r["vistas"]), [50.0, 100.0])   # 1:50 e 1:100 pelas cotas
        self.conferir_modelo(doc)

    def test_pdf_imagem_avisa(self):
        import pymupdf
        pdf = pymupdf.open()
        pg = pdf.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
        pg.insert_image(pg.rect, pixmap=pix)
        des, lido = pdf_ler.para_desenho(pdf.tobytes())
        self.assertTrue(any("digitalizada" in a for a in lido["avisos"]))

    def test_nao_e_pdf(self):
        from nucleo.base import ErroDeDados
        with self.assertRaises(ErroDeDados):
            pdf_ler.para_desenho(b"nada disso")


class TestRota(unittest.TestCase):
    def test_projeto_recebido_gera_modelo_e_ifc(self):
        import app
        from projetos import Projetos
        pasta = tempfile.mkdtemp(prefix="proj2d_dados_")
        antigo = app.PROJETOS
        app.PROJETOS = pasta
        try:
            g = Projetos(pasta)
            s = g.criar("Galpão recebido", tipo="desenho")["slug"] if "tipo" in g.criar.__code__.co_varnames \
                else g.criar("Galpão recebido")["slug"]
            caminho = ex.dxf(os.path.join(pasta, "galpao.dxf"))
            r = app.projeto_2d_para_modelo(s, {"arquivo": "galpao.dxf",
                                               "conteudo_b64": base64.b64encode(open(caminho, "rb").read()).decode()})
            self.assertEqual(r["gerado"]["barras"], sum(ESPERADO.values()))
            self.assertTrue(r["ifc"]["nome"].endswith(".ifc"))
            self.assertTrue(os.path.exists(os.path.join(pasta, r["ifc"]["url"].split("/saida/", 1)[1])))
            des = g.abrir_desenho(s, r["desenho"])
            self.assertTrue(des["metadados"]["reconhecimento"]["montagens"])
            modelo = g.abrir_modelo(s)
            self.assertEqual(sum(1 for e in modelo["entidades"] if e.get("tipo") == "barra"), sum(ESPERADO.values()))
        finally:
            app.PROJETOS = antigo


if __name__ == "__main__":
    unittest.main()
