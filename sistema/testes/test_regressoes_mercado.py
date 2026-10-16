# -*- coding: utf-8 -*-
"""Regressões do Mercado Conceito (16/10/2026) — o IFC do Tekla de um prédio pré-moldado em L, sem malha de eixos, sem
marca de conjunto, com o neoprene de material "STEEL/SHORE A-60" e um pavimento só. Cada teste falha sem a correção
(ver sistema/testes/REGRESSOES.md, seção "Modelo importado do Tekla (pré-moldado)")."""
import inspect
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app                                                   # noqa: E402
from nucleo3d import eixos as E                              # noqa: E402
from nucleo3d.modelo import Chapa, Documento, Solido         # noqa: E402
from nucleo2d.detalhe import base                            # noqa: E402
from nucleo2d.detalhe.celulas import reorientar_chapas       # noqa: E402
from nucleo2d.detalhe.conjuntos import _eixos_do_modelo      # noqa: E402
from nucleo2d.detalhe.fora_do_aco import material_nao_aco    # noqa: E402
from projetos import Projetos                                # noqa: E402

#: a origem longe do zero, como o IFC do Tekla chega (o Mercado: x ~3 a 57 m, y ~35 a 88 m)
X0, Y0 = 3000.0, 35000.0


def caixa(nome, x0, y0, z0, x1, y1, z1, tipo="IfcColumn", material="CONCRETE/Fck-40", ref=""):
    vs = [(x, y, z) for z in (z0, z1) for (x, y) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    fs = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    props = {"Pset_ColumnCommon": {"Reference": ref}} if ref else {}
    return Solido(nome=nome, camada="200 Pré-Fabricado", material=material, vertices=vs, faces=fs,
                  atributos={"tipo_ifc": tipo, "propriedades": props, "marcas": {"perfil": nome}})


def predio_em_l() -> Documento:
    """Pilares numa malha ortogonal (5 × 3 no corpo e uma ala de 2 × 3 que faz o L), com bloco, colarinho e enchimento
    (IfcColumn de 0,6 m) no pé, e vigas — nada com marca de conjunto, como o Tekla mandou."""
    doc = Documento()
    xs, ys = [0, 6000, 12000, 18000, 24000], [0, 7000, 14000]
    ala_x, ala_y = [0, 6000], [21000, 28000, 35000]
    pontos = [(x, y) for x in xs for y in ys] + [(x, y) for x in ala_x for y in ala_y]
    for x, y in pontos:
        x, y = X0 + x, Y0 + y
        doc.add(caixa("Pilar", x - 200, y - 300, -1000, x + 200, y + 300, 7300))
        doc.add(caixa("Bloco", x - 600, y - 600, -1600, x + 600, y + 600, -1000))
    for y in ys:
        doc.add(caixa("Viga L", X0, Y0 + y - 150, 3500, X0 + 24000, Y0 + y + 150, 4200, tipo="IfcBeam"))
    for x in ala_x:
        doc.add(caixa("Viga L", X0 + x - 150, Y0 + 14000, 3500, X0 + x + 150, Y0 + 35000, 4200, tipo="IfcBeam"))
    return doc


class TestEixosPelosPilares(unittest.TestCase):
    """254aacd — "importando com os eixos todos desconfigurados": sem treliça nem marca de conjunto, o eixo do galpão
    saía pela forma do prédio em L, a 51°, com 1 eixo numerado e 51 letras."""

    def test_predio_em_l_sai_ortogonal_nos_pilares(self):
        r = E.identificar_eixos(predio_em_l(), {})
        self.assertEqual(r["eixo_g"], [1.0, 0.0])
        self.assertEqual([round(e["pos"]) for e in r["numeros"]], [round(X0 + x) for x in (0, 6000, 12000, 18000, 24000)])
        self.assertEqual([round(e["pos"]) for e in r["letras"]], [round(Y0 + y) for y in (0, 7000, 14000, 21000, 28000, 35000)])
        self.assertEqual(r["fonte_letras"], "pilares")


class _ComProjeto(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="regr_mercado_")
        self.antigo = app.PROJETOS
        app.PROJETOS = self.pasta
        app._CACHE_NIVEIS_AUTO.clear() if hasattr(app, "_CACHE_NIVEIS_AUTO") else None
        self.g = Projetos(self.pasta)
        self.s = self.g.criar("Mercado", tipo="desenho")["slug"]

    def tearDown(self):
        app.PROJETOS = self.antigo


class TestGravarEixosApagados(_ComProjeto):
    """45cbe33 — "apaguei todos os eixos lançados errados, não tem um botão para salvar": com a lista vazia o Gravar
    no projeto era recusado, e o automático trazia os eixos errados de volta."""

    def test_lista_vazia_grava_sem_eixos_e_a_planta_nao_volta_ao_automatico(self):
        self.g._atualizar(self.s, eixos={"eixo_g": [0.631, 0.776], "z_base": -3500, "origem": "usuario",
                                         "letras": [{"nome": "A", "pos": 0}], "numeros": [{"nome": "1", "pos": 0}]})
        r = app.gravar_eixos_projeto(self.s, {"eixos": {"eixo_g": [0.631, 0.776], "z_base": -3500, "letras": [], "numeros": []}})
        self.assertTrue(r["gravados"])
        lido = app.eixos_do_projeto(self.s)
        self.assertTrue(lido["gravados"] and lido["eixos"].get("vazio"))
        self.assertIsNone(_eixos_do_modelo(predio_em_l(), lido["eixos"], None))


class TestNeopreneNaoEhAco(unittest.TestCase):
    """fef554e, 067405b, a70b3b0 — a faixa "O 3D está fora do padrão de fábrica: Neoprene" a cada abertura do editor:
    o material "STEEL/SHORE A-60" (a dureza Shore) fazia o neoprene entrar como aço — como sólido, como chapa
    paramétrica (convertida num detalhamento de antes) e na migração dos eixos das chapas."""

    NEOPRENE = "STEEL/SHORE A-60"

    def test_solido_de_neoprene(self):
        s = caixa("Neoprene", 0, 0, 0, 160, 140, 10, tipo="IfcPlate", material=self.NEOPRENE)
        self.assertEqual(material_nao_aco(s), ("neoprene", 1250.0))

    def _chapa(self, conferida=False):
        a = {"tipo_ifc": "IfcPlate", "marcas": {"perfil": "Neoprene"}, "convertida_de": "solido"}
        if conferida:
            a["eixos_conferidos"] = True
        return Chapa(nome="Neoprene", camada="200 Pré-Fabricado", material=self.NEOPRENE, aco=self.NEOPRENE,
                     origem=(X0, Y0, -400.0), espessura=10.0, contorno=[(0, 0), (160, 0), (160, 140), (0, 140)], atributos=a)

    def test_chapa_parametrica_de_neoprene_fica_fora_do_aco(self):
        doc = Documento()
        doc.add(self._chapa(conferida=True))
        fora = []
        pecas, _ac = base._pecas(doc, fora_do_aco=fora)
        self.assertEqual([p.nome for p in pecas], [])
        self.assertEqual([c for _e, c, _r in fora], ["neoprene"])

    def test_migracao_dos_eixos_nao_pega_a_chapa_de_neoprene(self):
        doc = Documento()
        doc.add(self._chapa(conferida=False))
        r = reorientar_chapas(doc, Documento())
        self.assertEqual((r["posicoes"], r["chapas"], r["sem_origem"]), (0, 0, []))


class TestNiveisAutomaticos(_ComProjeto):
    """03563c7 — "o projeto importado não está mostrando os níveis": o Tekla manda um pavimento só (Undefined, 0,00)
    e o 3D só mostrava os níveis gravados no projeto."""

    def test_projeto_importado_sem_niveis_gravados_mostra_os_do_modelo(self):
        doc = Documento()
        for k in range(4):
            y = Y0 + 2000 * k
            doc.add(caixa("Viga L", X0, y, -800, X0 + 6000, y + 300, 0, tipo="IfcBeam"))
            doc.add(caixa("Viga L", X0, y, 3500, X0 + 6000, y + 300, 4200, tipo="IfcBeam"))
            doc.add(caixa("Laje Alveolar", X0, y, 7100, X0 + 6000, y + 1250, 7300, tipo="IfcBeam"))
        self.g.salvar_modelo(self.s, doc.dict())
        r = app.referencia_do_lancamento(self.s)
        self.assertTrue(r.get("niveis_automaticos"))
        self.assertEqual([n["z"] for n in r["niveis"]], [0.0, 4200.0, 7300.0])

    def test_niveis_gravados_continuam_valendo(self):
        self.g._atualizar(self.s, niveis=[{"nome": "Térreo ±0,00", "z": 0.0}])
        r = app.referencia_do_lancamento(self.s)
        self.assertEqual([n["nome"] for n in r["niveis"]], ["Térreo ±0,00"])
        self.assertFalse(r.get("niveis_automaticos"))


class TestTelaInicialComDetalhamentoRodando(unittest.TestCase):
    """73a5df4 — "o modo dev fica na tela branca e não carrega os projetos": com o detalhamento automático (conta em
    Python por minutos no mesmo processo) a lista de projetos ia de 0,06 s a 24 s. O servidor sobe com a troca de
    tarefa curta; a medição de verdade (a lista com uma conta pesada ao lado) está no próximo teste."""

    def test_servidor_sobe_com_a_troca_de_tarefa_curta(self):
        fonte = inspect.getsource(app.main)
        import re
        m = re.search(r"setswitchinterval\(([\d.e-]+)\)", fonte)
        self.assertIsNotNone(m, "app.main não ajusta o intervalo de troca de tarefa")
        self.assertLessEqual(float(m.group(1)), 0.0005)

    def test_lista_de_projetos_com_conta_pesada_ao_lado(self):
        import re
        import threading
        import time
        valor = float(re.search(r"setswitchinterval\(([\d.e-]+)\)", inspect.getsource(app.main)).group(1))
        pasta = tempfile.mkdtemp(prefix="regr_lista_")
        g = Projetos(pasta)
        for i in range(25):
            g.criar("Obra %d" % i, tipo="desenho")
        g.listar()
        antes = sys.getswitchinterval()
        parar = []

        def pesada():
            x = 0
            while not parar:
                for i in range(50000):
                    x += i * i
        th = threading.Thread(target=pesada, daemon=True)
        try:
            sys.setswitchinterval(valor)
            th.start()
            time.sleep(0.2)
            t = time.time()
            g.listar()
            dt = time.time() - t
        finally:
            parar.append(1)
            th.join(5)
            sys.setswitchinterval(antes)
        self.assertLess(dt, 3.0, "a lista de 25 projetos levou %.1f s com uma conta pesada ao lado" % dt)


if __name__ == "__main__":
    unittest.main()
