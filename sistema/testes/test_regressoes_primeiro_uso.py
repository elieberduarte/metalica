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


class TestVaoForaDaFaixaComVirgula(unittest.TestCase):
    """P06 — "Não foi possível lançar: Vão: valor 4.0 fora da faixa aceitável (5 a 60 m)": com ponto decimal e sem dizer
    o que fazer. A conta do servidor fala português; a tela avisa antes (verif_lancar_vao_pequeno)."""

    def test_mensagem_com_virgula(self):
        from nucleo.base import ErroDeDados
        from nucleo.modelo_galpao import DadosGalpao
        with self.assertRaises(ErroDeDados) as c:
            DadosGalpao(vao=4.5).validar()
        msg = str(c.exception)
        self.assertIn("4,5", msg)
        self.assertNotIn("4.5", msg)


class TestProjetoRecebidoMudaOTipo(_ComProjeto):
    """P25 — o cartão do projeto dizia "LANÇADO SOBRE O ARQUITETÔNICO" para um projeto recebido (o tipo ficava o do
    começo, escolhido por falta de opção)."""

    def test_lancamento_vira_recebido(self):
        import base64
        import io
        import ezdxf
        d = ezdxf.new("R2010")
        d.modelspace().add_line((0, 0), (6000, 0))
        buf = io.StringIO()
        d.write(buf)
        app.projeto_2d_para_modelo(self.s, {"arquivo": "portaria.dxf", "ifc": False,
                                            "conteudo_b64": base64.b64encode(buf.getvalue().encode()).decode()})
        p = self.g.ler(self.s)
        self.assertEqual(p["tipo"], "recebido")
        cartao = next(c for c in self.g.listar() if c["slug"] == self.s)
        self.assertEqual(cartao["tipo_rotulo"], "Projeto recebido (DXF/PDF)")


class TestFolhasDoDxfGuardado(_ComProjeto):
    """P08 — o passo "2. Ler folhas e considerações de cálculo" abria de novo a janela do Windows pedindo o DXF que o
    passo 1 já tinha importado. O passo 1 guarda o DXF nos documentos da obra e o passo 2 lê dele."""

    def _importar(self, texto, nome="portaria.dxf"):
        import base64
        app.projeto_2d_para_modelo(self.s, {"arquivo": nome, "ifc": False, "conteudo_b64": base64.b64encode(texto.encode("utf-8")).decode()})

    def test_passo_2_le_o_dxf_do_passo_1(self):
        from test_folhas_recebidas import _dxf
        self._importar(_dxf())
        self.assertEqual(app.ler_projeto_recebido(self.s, {"ler": True})["dxf_guardado"], "portaria.dxf")
        r = app.ler_projeto_recebido(self.s, {})                # sem arquivo: o guardado
        self.assertEqual([f["numero"] for f in r["projeto_recebido"]["folhas"]], ["01/03", "02/03", "03/03"])
        self.assertEqual(r["projeto_recebido"]["arquivo"], "portaria.dxf")
        docs = [d["nome"] for d in app._documentos_da_obra(self.g._existente(self.s))]
        self.assertIn("portaria.dxf", docs)                     # aparece na aba Arquivos

    def test_revisao_com_o_mesmo_nome_guarda_a_anterior(self):
        from test_folhas_recebidas import _dxf
        self._importar(_dxf())
        self._importar(_dxf().replace("R02", "R03"))
        lixo = os.path.join(self.g._existente(self.s), app.PASTA_DOCUMENTOS, ".lixeira")
        self.assertEqual(len(os.listdir(lixo)), 1)
        r = app.ler_projeto_recebido(self.s, {})
        self.assertEqual(r["projeto_recebido"]["carimbo"]["revisao"], "R03")


class TestOrigemDosPadroesDaPlanta(_ComProjeto):
    """P26 — o diálogo "Montar o 3D pela planta" mostrava banzo 6,00 m e ASTM A36 como se fossem lidos do desenho (eram
    padrão). O servidor diz de onde vem o aço e o lê das folhas do projeto quando o passo 2 as leu."""

    def _desenho(self):
        from nucleo2d.desenho import Texto
        des = Desenho(nome="Projeto recebido – portaria")
        des.add(Texto(posicao=(0, 0), texto="PLANTA NO NÍVEL DO FORRO"))
        self.g.salvar_desenho(self.s, des.nome, des.dict())
        return des.nome

    def test_aco_padrao_e_dito_padrao(self):
        r = app.montar_pela_planta(self.s, self._desenho(), {"sugerir": True})
        self.assertEqual(r["origem"]["aco"], "padrao")

    def test_aco_lido_das_folhas(self):
        from test_folhas_recebidas import _dxf
        nome = self._desenho()
        app.ler_projeto_recebido(self.s, {"arquivo": "portaria.dxf", "conteudo": _dxf()})
        r = app.montar_pela_planta(self.s, nome, {"sugerir": True})
        self.assertEqual((r["origem"]["aco"], r["padrao"]["aco"]), ("folhas", "ASTM A36"))
        self.assertIn("PERFIS DOBRADOS", r["origem"]["aco_texto"])

    def test_nome_do_catalogo(self):
        self.assertEqual(app._aco_das_folhas({"materiais": ["CHAPAS: AÇO ASTM A36", "PERFIS LAMINADOS: AÇO ASTM A572 GR.50"]}),
                         ("ASTM A572 Gr.50", "PERFIS LAMINADOS: AÇO ASTM A572 GR.50"))
        self.assertIsNone(app._aco_das_folhas({"materiais": ["PARAFUSOS ASTM A325"]}))


class TestPesoDoLancamentoIgualALista(_ComProjeto):
    """P23 — a portaria lançada nos eixos (5 × 6,2 m) dizia 1.874 kg no "Estrutura lançada", 1.886,1 kg na lista de
    materiais e 1,9 t no 3D; e a lista falava em "a barra veio sem o furo no IFC" num modelo que não veio de IFC."""

    def setUp(self):
        super().setUp()
        app._PESOS.clear()
        app.gravar_eixos_projeto(self.s, {"eixos": {
            "eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "z_base": 0.0,
            "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 5000.0}],
            "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6200.0}]}})
        self.r = app.lancar_estrutura(self.s, {"parametros": {}})

    def test_o_mesmo_peso_da_lista(self):
        lista = app.peso_do_projeto(self.s)["aco_kg"]
        self.assertEqual(self.r["resumo"]["peso_kg"], lista)
        self.assertEqual(self.g.ler(self.s)["lancamento"]["resumo"]["peso_kg"], lista)
        self.assertTrue(self.r["resumo"]["peso_modelo_kg"])            # o do modelo fica guardado

    def test_observacoes_sem_ifc(self):
        from nucleo2d import detalhar as det
        lev = det.levantar(app._documento3d_do_projeto(self.s), regra_tercas=False)
        obs = [o for p in lev["posicoes"] for o in (p.observacoes or [])]
        self.assertTrue(any("furo" in o for o in obs))                 # o caso existe neste modelo
        self.assertFalse([o for o in obs if "IFC" in o])


class TestDetalharNaoSeDaPorVelhoNoMeio(_ComProjeto):
    """P24 — logo depois do primeiro Detalhar, a tela dizia "Atualizando os desenhos (o detalhamento do programa
    mudou)…" e refazia tudo: no meio do Detalhar o carimbo só tinha as gerações dos desenhos (sem o código), os
    desenhos "detalhamento-*" já existiam, e a consulta da tela ao estado concluía "o programa mudou"."""

    def test_sem_motivo_durante_e_depois(self):
        import threading
        app.gravar_eixos_projeto(self.s, {"eixos": {
            "eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "z_base": 0.0,
            "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 5000.0}],
            "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6200.0}]}})
        app.lancar_estrutura(self.s, {"parametros": {}})
        vivos = app._vivos()
        grupos = ["tesouras", "conjuntos", "tercas", "contraventamentos", "agulhamentos", "extras", "telhas",
                  "chaparias", "localizacao", "chumbacao", "completo"]            # os do diálogo Detalhar
        fim = threading.Event()
        t = threading.Thread(target=lambda: (app.detalhar_projeto(self.s, {"grupos": grupos}), fim.set()), daemon=True)
        t.start()
        motivos = set()
        while not fim.is_set() and t.is_alive():
            motivos.add(vivos.por_que_velho(self.s))      # o que a tela ouviria ao perguntar o estado
            time.sleep(0.01)
        t.join(600)
        motivos.add(vivos.por_que_velho(self.s))
        self.assertTrue(fim.is_set())
        self.assertEqual(motivos, {""})


if __name__ == "__main__":
    unittest.main()
