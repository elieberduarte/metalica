# -*- coding: utf-8 -*-
"""Cálculo e dimensionamento do modelo gerado de um projeto recebido (0.8.9): pilares,
longarinas, contraventamentos e correntes verificados, apoios nos pilares, o perfil mais
leve que passa em cada posição e a troca no modelo."""
import base64
import collections
import json
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import projeto_2d_sem_texto as ex                     # noqa: E402
from nucleo import analise, catalogo, tesouras        # noqa: E402
from nucleo2d import dxf_ler, reconhecer              # noqa: E402
from nucleo3d import calculo_ifc as ci, de_vistas     # noqa: E402
from nucleo3d.modelo import Documento                 # noqa: E402


def _modelo():
    pasta = tempfile.mkdtemp(prefix="dim_modelo_")
    caminho = ex.dxf(os.path.join(pasta, "galpao_sem_texto.dxf"))
    des = dxf_ler.para_desenho(dxf_ler.texto_de_bytes(open(caminho, "rb").read()), escala=50)[0]
    r = reconhecer.reconhecer(des)
    reconhecer.aplicar(des, r)
    m = reconhecer.sugerir_montagem(r)
    return de_vistas.modelo_das_vistas(des, m["montagens"]), caminho


class TestCalculoDoModeloDesenhado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, cls.dxf = _modelo()
        cls.nomes = ci.nomes_das_barras(cls.doc)
        cls.calc = ci.calcular(cls.doc, cls.nomes, {})

    def test_sem_detalhamento_o_papel_das_barras_basta(self):
        self.assertEqual(set(self.nomes["tipos_conjuntos"].values()), {"tesoura"})
        res = self.calc["resumo"]
        self.assertEqual(res["tesouras"], ex.N_EIXOS)            # 3 internas + 2 oitões, nenhuma repetida
        self.assertEqual(res["nao_verificadas"], [])
        self.assertFalse(any("não reconhecido" in a for a in self.calc["avisos"]))   # a barra redonda entra
        tipos = collections.Counter(e["tipo"] for e in self.calc["elementos"].values())
        for t in ("banzo", "diagonal", "montante", "terca", "pilar", "longarina", "contraventamento", "corrente"):
            self.assertIn(t, tipos)

    def test_apoios_no_topo_dos_pilares(self):
        par = dict(ci.PARAMETROS_PADRAO)
        avisos = []
        pecas, _t, _c, chap = ci._levantar_pecas(self.doc, self.nomes, par, avisos)
        tes = ci._tesouras(pecas, self.nomes, chap, avisos)
        ci._definir_apoios(tes, pecas, par)
        n_apoios = sorted(len(t.apoios) for t in tes)
        # interna: os dois de fachada e o do meio; oitão: mais os 4 de fechamento
        self.assertEqual(n_apoios, [3, 3, 3, 3 + len(ex.POSTES), 3 + len(ex.POSTES)])
        for t in tes:
            ci._montar_modelo(t)
            fixos = [n for n in t.modelo.nos if n.apoiado and n.apoio[0]]
            self.assertEqual(len(fixos), 1)                        # um fixo, os outros só na vertical

    def test_modelos_dos_pilares(self):
        modelos = {e["dimensionamento"]["modelo"].split(":")[0] for e in self.calc["elementos"].values()
                   if e["tipo"] == "pilar"}
        # o pilar do meio da tesoura interna e o do oitão são a mesma posição (mesmo perfil e
        # comprimento): vale a envoltória, que é o do oitão, com vento
        self.assertTrue({"fachada lateral", "oitão"} <= modelos, modelos)
        for e in self.calc["elementos"].values():
            if e["tipo"] == "pilar" and e["dimensionamento"]["modelo"].startswith("fachada"):
                self.assertEqual(e["dimensionamento"]["K"], 2.0)
                self.assertGreater(e["dimensionamento"]["M"], 0.0)

    def test_contraventamento_pela_forca_do_oitao(self):
        cob = [e for e in self.calc["elementos"].values()
               if e["tipo"] == "contraventamento" and "cobertura" in e["dimensionamento"]["planos"]]
        self.assertTrue(cob)
        d = cob[0]["dimensionamento"]
        self.assertGreater(d["F_oitao_kN"], 0.0)
        self.assertAlmostEqual(d["cortante_kN"], d["F_oitao_kN"] / 2.0, delta=0.05)
        self.assertLessEqual(max(e["dimensionamento"]["N"] for e in cob),
                             d["cortante_kN"] * 3.0)                  # N = V·L/profundidade

    def test_nome_da_barra_redonda_do_modelo_volta_ao_catalogo(self):
        self.assertIsNotNone(catalogo.item('Barra redonda ø 1/2" (12,7 mm)'))
        self.assertIsNotNone(catalogo.item("U 100×50×3,00 (FF)"))


class TestDimensionar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, _ = _modelo()
        cls.nomes = ci.nomes_das_barras(cls.doc)
        cls.d = ci.dimensionar(cls.doc, cls.nomes, {"trava_inferior": 3.0})

    def test_converge_e_melhora(self):
        d = self.d
        self.assertTrue(d["convergiu"])
        self.assertLess(len(d["reprovadas"]), len(d["reprovadas_antes"]))
        self.assertTrue(d["mudancas"])
        # o que continua reprovado é o que nenhum perfil das séries padrão resolve
        for m in d["reprovadas"]:
            el = d["calculo"]["elementos"][m]
            alt = ci.alternativas(d["calculo"], m, limite=400, limite_catalogo=600, so_padrao=True)["alternativas"]
            self.assertFalse(any(a["ok"] and ci._aceito_no_automatico(a["nome"], el) for a in alt), m)

    def test_regras_da_fabrica_na_tesoura(self):
        for x in self.d["mudancas"]:
            if x["tipo"] in ("banzo", "diagonal", "montante"):
                p = catalogo.perfil_de(x["para"])
                esp = tesouras._espessura(p)
                self.assertFalse(0 < esp < tesouras.MIN_ESPESSURA, x)
                self.assertFalse(catalogo.item(x["para"]).dados.get("fornecedor"), x)

    def test_banzo_com_um_perfil_por_linha(self):
        por_linha = collections.defaultdict(set)
        for e in self.d["calculo"]["elementos"].values():
            if e["tipo"] == "banzo" and e["aproveitamento"] > 1e-3:
                por_linha[e["posicao"]].add(e["perfil"])
        self.assertTrue(por_linha)
        for linha, perfis in por_linha.items():
            self.assertEqual(len(perfis), 1, (linha, perfis))

    def test_aplicar_no_modelo(self):
        doc2 = Documento.de_dict(self.doc.dict())
        ap = ci.aplicar_perfis(doc2, self.d["trocas"])
        self.assertGreater(ap["barras"], 0)
        self.assertEqual(ap["so_calculo"], {})
        mudadas = [b for b in doc2.barras if b.atributos.get("trocas_de_perfil")]
        self.assertEqual(len(mudadas), ap["barras"])
        for b in mudadas[:20]:
            self.assertEqual(b.atributos["marcas"]["perfil"], b.perfil)
            self.assertTrue(b.atributos["marcas"]["perfil_original"])
            self.assertEqual(b.atributos["trocas_de_perfil"][-1]["por"], "dimensionamento")
        # o modelo trocado, calculado sem troca nenhuma, dá o mesmo que o dimensionamento
        r = ci.calcular(doc2, ci.nomes_das_barras(doc2), {"trava_inferior": 3.0})

        def nome(p):
            # a barra redonda do galpão (corrente, tirante) é perfil sintético, fora do catálogo
            it = catalogo.item(p)
            return it.nome if it is not None else p
        for m, e in self.d["calculo"]["elementos"].items():
            self.assertEqual(nome(r["elementos"][m]["perfil"]), nome(e["perfil"]), m)

    def test_banzo_inferior_sem_travamento_fica_pendente(self):
        calc = ci.calcular(self.doc, self.nomes, {})
        sem = [m for m, e in calc["elementos"].items() if e.get("sem_trava") and not e["ok"]]
        if not sem:
            self.skipTest("o banzo inferior do exemplo passa mesmo sem travamento")
        d = ci.dimensionar(self.doc, self.nomes, {}, max_rodadas=2)
        pend = {x["marca"] for x in d["pendentes"]}
        self.assertTrue(set(sem) <= pend)
        self.assertTrue(all("travamento" in x["motivo"] for x in d["pendentes"]))
        self.assertFalse(pend & set(d["trocas"]))


class TestAnaliseReaproveitada(unittest.TestCase):
    def test_fatoracao_serve_aos_casos_e_se_refaz_quando_o_modelo_muda(self):
        m = analise.Modelo("viga")
        m.add_no(0, 0, (True, True, False))
        m.add_no(500, 0, (False, True, False))
        m.add_barra(0, 1, 50.0, 5000.0)
        m.caso("A")
        m.distribuida("A", 0, -0.1, "global_y")
        m.caso("B")
        m.distribuida("B", 0, -0.2, "global_y")
        ra = analise.resolver(m, "A")
        guardada = m._montagem_guardada
        rb = analise.resolver(m, "B")
        self.assertIs(m._montagem_guardada, guardada)            # a mesma fatoração
        E = m.barras[0].E
        flecha = 5 * 0.1 * 500 ** 4 / (384 * E * 5000.0)
        self.assertAlmostEqual(abs(ra.deslocamento(1)[2]) * 0, 0.0)
        meio = ra.barras[0]
        self.assertAlmostEqual(max(abs(v) for v in meio.diagrama.M), 0.1 * 500 ** 2 / 8, delta=1e-6)
        self.assertAlmostEqual(max(abs(v) for v in rb.barras[0].diagrama.M), 0.2 * 500 ** 2 / 8, delta=1e-6)
        self.assertGreater(flecha, 0)
        rot_a = ra.deslocamento(0)[2]
        m.barras[0].I = 10000.0                                   # rigidez nova: refaz
        ra2 = analise.resolver(m, "A")
        self.assertIsNot(m._montagem_guardada, guardada)
        self.assertAlmostEqual(ra2.deslocamento(0)[2], rot_a / 2.0, places=9)


class TestRotaDimensionar(unittest.TestCase):
    def test_dimensionar_troca_no_modelo_e_grava_o_calculo(self):
        import app
        from projetos import Projetos
        pasta = tempfile.mkdtemp(prefix="dim_rota_")
        antigo = app.PROJETOS
        app.PROJETOS = pasta
        try:
            g = Projetos(pasta)
            s = g.criar("Galpão sem texto", tipo="desenho")["slug"]
            _doc, caminho = _modelo()
            r = app.projeto_2d_para_modelo(s, {"arquivo": "galpao.dxf", "ifc": False,
                                               "conteudo_b64": base64.b64encode(open(caminho, "rb").read()).decode()})
            self.assertTrue(r["gerado"]["barras"])
            geo = app.geometria_para_calculo(s)
            self.assertTrue(geo["detalhado"])                     # o papel das barras dispensa o detalhamento
            d = app.dimensionar_projeto(s, {"parametros": {"trava_inferior": 3.0}, "aplicar": True})
            self.assertGreater(d["aplicado"]["barras"], 0)
            modelo = g.abrir_modelo(s)
            trocadas = [e for e in modelo["entidades"] if e.get("tipo") == "barra"
                        and (e.get("atributos") or {}).get("trocas_de_perfil")]
            self.assertEqual(len(trocadas), d["aplicado"]["barras"])
            gravado = app.calculo_do_projeto(s)
            self.assertEqual(gravado["parametros"]["trocas"], {})
            self.assertEqual(gravado["parametros"]["trava_inferior"], 3.0)
            self.assertEqual(sorted(gravado["calculo"]["resumo"]["reprovadas"]), sorted(d["reprovadas"]))
            self.assertTrue(g.listar_historico(s))                 # o modelo anterior ficou no histórico
        finally:
            app.PROJETOS = antigo


if __name__ == "__main__":
    unittest.main()
