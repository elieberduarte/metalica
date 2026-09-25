# -*- coding: utf-8 -*-
"""Proteção dos dados (revisão geral de 24/09, 0.8.12): nada se grava por cima do que não
se leu, a operação longa não desfaz a edição do editor, o servidor só obedece às telas do
programa, a lixeira não cresce para sempre."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(AQUI)
sys.path.insert(0, BASE)

import app                                   # noqa: E402
import projetos                              # noqa: E402
from nucleo.base import ErroDeDados          # noqa: E402
from projetos import Projetos                # noqa: E402


class _ComDados(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="protecao_")
        self.antigo = app.PROJETOS
        app.PROJETOS = self.pasta
        self.g = Projetos(self.pasta)
        self.s = self.g.criar("Prot", tipo="desenho")["slug"]
        self.arq = os.path.join(self.pasta, self.s, "projeto.json")

    def tearDown(self):
        app.PROJETOS = self.antigo


class TestProjetoIlegivel(_ComDados):
    def test_nao_regrava_e_guarda_copia(self):
        with open(self.arq, "w", encoding="utf-8") as f:
            f.write('{"nome": "Prot", "dados": {"vao": 20')          # cortado no meio
        antes = open(self.arq, encoding="utf-8").read()
        p = self.g.ler(self.s)
        self.assertTrue(p.get("ilegivel"))
        self.assertEqual(open(self.arq, encoding="utf-8").read(), antes)   # nada por cima
        self.assertTrue(os.path.exists(p["ilegivel"]["copia"]))
        self.assertTrue(self.g.resumo(self.s)["ilegivel"])
        with self.assertRaises(ErroDeDados):
            self.g.salvar_dados(self.s, {"vao": 25})
        self.g.tocar(self.s)                                          # entrega gravada não quebra
        self.assertEqual(open(self.arq, encoding="utf-8").read(), antes)

    def test_gravacoes_simultaneas_nao_perdem_campo(self):
        def gravar(k):
            self.g._atualizar(self.s, **{"campo_%d" % k: k})
        ts = [threading.Thread(target=gravar, args=(k,)) for k in range(20)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        p = json.load(open(self.arq, encoding="utf-8"))
        self.assertEqual(sorted(k for k in p if k.startswith("campo_")), sorted("campo_%d" % k for k in range(20)))


class TestAjustes(_ComDados):
    def test_ajuste_ilegivel_para_com_explicacao(self):
        self.assertEqual(app._nomes_producao(self.s), {})              # ausente: vazio
        pasta = os.path.join(self.pasta, self.s, "detalhamento")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, "ajustes-furos.json"), "w", encoding="utf-8") as f:
            f.write('{"P1": [1, 2')
        with self.assertRaises(ErroDeDados) as c:
            app._ajustes_furos(self.s)
        self.assertIn("furação ajustada", str(c.exception))
        self.assertTrue(any(n.startswith("ajustes-furos.json.ilegivel-") for n in os.listdir(pasta)))
        app._gravar_nomes_producao(self.s, {"posicoes": {"P1": "B.1"}})
        self.assertEqual(app._nomes_producao(self.s)["posicoes"], {"P1": "B.1"})
        self.assertFalse(any(n.endswith(".parcial") for n in os.listdir(pasta)))

    def test_operacao_longa_nao_desfaz_a_edicao_do_editor(self):
        from nucleo3d.modelo import Barra, Documento
        doc = Documento(nome="m")
        doc.add(Barra(nome="W", inicio=(0, 0, 0), fim=(1000, 0, 0), perfil="W 200×26,6"))
        self.g.salvar_modelo(self.s, doc.dict())
        lido = app._documento3d_do_projeto(self.s)                     # a operação lê…
        time.sleep(0.05)
        editado = Documento.de_dict(self.g.abrir_modelo(self.s))       # …o editor grava no meio…
        editado.add(Barra(nome="W", inicio=(0, 0, 0), fim=(0, 1000, 0), perfil="W 200×26,6"))
        self.g.salvar_modelo(self.s, editado.dict())
        with self.assertRaises(app.ModeloMudouNoMeio):                 # …e a operação não grava por cima
            app._regravar_modelo(self.s, lido)
        self.assertEqual(len(self.g.abrir_modelo(self.s)["entidades"]), 2)
        de_novo = app._documento3d_do_projeto(self.s)
        app._regravar_modelo(self.s, de_novo)                          # sem ninguém no meio, grava
        app._regravar_modelo(self.s, de_novo)                          # e pode regravar o que acabou de gravar


class TestLixeiraEEncerramento(unittest.TestCase):
    def test_lixeira_de_desenhos_antigos(self):
        raiz = tempfile.mkdtemp(prefix="lixeira_")
        lixo = os.path.join(raiz, projetos.LIXEIRA)
        os.makedirs(os.path.join(lixo, "projeto-excluido"))
        velho = os.path.join(lixo, "p-velho.desenho.json-20260101-000000")
        novo = os.path.join(lixo, "p-novo.desenho.json-20260924-000000")
        for c in (velho, novo):
            open(c, "w").write("{}")
        antigo = time.time() - 40 * 86400
        os.utime(velho, (antigo, antigo))
        self.assertEqual(projetos.esvaziar_lixeira_antiga(raiz), 1)
        self.assertFalse(os.path.exists(velho))
        self.assertTrue(os.path.exists(novo))
        self.assertTrue(os.path.isdir(os.path.join(lixo, "projeto-excluido")))   # projeto excluído fica

    def test_encerramento_espera_operacao(self):
        self.assertFalse(app._trabalho_em_curso())
        app._em_curso(+1)
        try:
            self.assertTrue(app._trabalho_em_curso())
        finally:
            app._em_curso(-1)
        app.PROGRESSO["x"] = {"etapa": "detalhando", "quando": time.time()}
        try:
            self.assertTrue(app._trabalho_em_curso())
        finally:
            app.PROGRESSO.pop("x", None)


class TestPedidosDeFora(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dados = tempfile.mkdtemp(prefix="defora_")
        cls.porta = 8798
        cls.srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta",
                                    str(cls.porta), "--dados", cls.dados],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen("http://localhost:%d/api/versao" % cls.porta, timeout=2)
                break
            except Exception:                                           # noqa: BLE001
                time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()

    def pedir(self, metodo, rota, cab=None, corpo=None):
        req = urllib.request.Request("http://localhost:%d%s" % (self.porta, rota), method=metodo,
                                     data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers=dict({"Content-Type": "application/json"}, **(cab or {})))
        try:
            return urllib.request.urlopen(req, timeout=10).status
        except urllib.error.HTTPError as e:
            return e.code

    def test_origem_e_host(self):
        self.assertEqual(self.pedir("POST", "/api/projetos", corpo={"nome": "A", "tipo": "desenho"}), 200)
        self.assertEqual(self.pedir("POST", "/api/projetos", {"Origin": "http://localhost:%d" % self.porta},
                                    {"nome": "B", "tipo": "desenho"}), 200)
        self.assertEqual(self.pedir("POST", "/api/projetos", {"Origin": "https://site-qualquer.com"},
                                    {"nome": "C", "tipo": "desenho"}), 403)
        self.assertEqual(self.pedir("GET", "/api/projetos", {"Host": "malicioso.exemplo:%d" % self.porta}), 403)
        self.assertEqual(self.pedir("GET", "/api/projetos"), 200)


if __name__ == "__main__":
    unittest.main()
