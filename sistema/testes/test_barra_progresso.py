# -*- coding: utf-8 -*-
"""A barra de andamento padrão das tarefas demoradas (web/progresso.js e app._progresso, 16/10/2026).

Antes: só o texto da etapa na linha de dica ("Pré-moldado: desenhando lajes… (19 s)") — o usuário não sabia quanto
faltava. Agora o servidor conta a fração (a da tarefa, quando ela sabe, e a da etapa pelo "(i de n)") e a barra
mostra a fração do servidor, senão a estimativa pela última duração, senão a da etapa, senão corre sem número.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app  # noqa: E402

WEB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))


class TestProgressoDoServidor(unittest.TestCase):
    def tearDown(self):
        app._fim_progresso("t")

    def test_sem_tarefa(self):
        self.assertEqual(app.progresso_do_projeto("t"), {"etapa": "", "ha_s": 0})

    def test_fracao_da_etapa_pelo_i_de_n_e_a_da_tarefa(self):
        app._progresso("t", "geometria das peças (200 de 800)")
        p = app.progresso_do_projeto("t")
        self.assertEqual(p["fracao_etapa"], 0.25)
        self.assertNotIn("fracao", p)
        app._progresso("t", "desenhando pilares", fracao=0.6)
        p = app.progresso_do_projeto("t")
        self.assertEqual(p["fracao"], 0.6)
        self.assertNotIn("fracao_etapa", p)

    def test_desde_o_comeco_da_tarefa_e_nao_da_etapa(self):
        app._progresso("t", "primeira")
        time.sleep(0.25)
        app._progresso("t", "segunda")
        p = app.progresso_do_projeto("t")
        self.assertGreaterEqual(p["desde_s"], 0.2)
        self.assertLess(p["ha_s"], 0.2)

    def test_fracao_limitada(self):
        app._progresso("t", "x", fracao=1.7)
        self.assertEqual(app.progresso_do_projeto("t")["fracao"], 1.0)

    def test_rodada_de_ate(self):
        app._progresso("t", "dimensionando: rodada 2 de até 5")
        self.assertEqual(app.progresso_do_projeto("t")["fracao_etapa"], 0.4)


class TestTarefaPadrao(unittest.TestCase):
    """Toda rota de projeto começa com uma etapa (a barra sempre tem o que mostrar) e a limpa no fim — o Aplicar furos
    chamava _progresso sem _fim_progresso e a etapa velha ficava pendurada para a próxima tela."""

    def tearDown(self):
        app._fim_progresso("t")

    def test_comeca_e_limpa_inclusive_a_etapa_pendurada(self):
        tarefa = app._tarefa_padrao("/api/projetos/t/desenhos/x/aplicar-furos")
        self.assertEqual(app.progresso_do_projeto("t")["etapa"], "começando…")
        app._progresso("t", "conferindo os eixos das chapas…")         # a rota não chama _fim_progresso
        app._fim_tarefa_padrao(tarefa)
        self.assertEqual(app.progresso_do_projeto("t")["etapa"], "")

    def test_nao_pisa_na_tarefa_em_curso(self):
        app._progresso("t", "detalhando (3 de 10)")                    # a atualização automática rodando
        tarefa = app._tarefa_padrao("/api/projetos/t/modelo")           # a gravação do modelo no meio
        self.assertIsNone(tarefa)
        app._fim_tarefa_padrao(tarefa)
        self.assertEqual(app.progresso_do_projeto("t")["etapa"], "detalhando (3 de 10)")

    def test_so_rota_de_projeto(self):
        self.assertIsNone(app._tarefa_padrao("/api/dimensionar"))
        self.assertIsNone(app._tarefa_padrao("/api/projetos"))


@unittest.skipUnless(shutil.which("node"), "sem Node no computador")
class TestFracaoDaBarra(unittest.TestCase):
    def test_a_ordem_de_preferencia(self):
        pasta = tempfile.mkdtemp(prefix="barra_")
        try:
            script = os.path.join(pasta, "t.mjs")
            url = "file:///" + os.path.join(WEB, "progresso.js").replace("\\", "/")
            open(script, "w", encoding="utf-8").write(
                "import { fracaoDaBarra as f } from %s;\n"
                "console.log(JSON.stringify([f({fracao: 0.4}, 5, 10), f({}, 5, 10), f({}, 30, 10),"
                " f({fracao_etapa: 0.5}, 2, 0), f(null, 2, 0), f({fracao: 3}, 1, 0), f({fracao_etapa: 0.5}, 5, 10)]));\n"
                % json.dumps(url))
            r = subprocess.run(["node", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            a = json.loads(r.stdout)
        finally:
            shutil.rmtree(pasta, ignore_errors=True)
        self.assertEqual(a[0], {"modo": "servidor", "fracao": 0.4})          # a do servidor vence
        self.assertEqual(a[1], {"modo": "estimada", "fracao": 0.5})          # 5 s de uma tarefa que levou 10
        self.assertEqual(a[2], {"modo": "estimada", "fracao": 0.95})         # passou do tempo: para em 95 %
        self.assertEqual(a[3], {"modo": "etapa", "fracao": 0.5})             # a primeira vez: a da etapa
        self.assertEqual(a[4], {"modo": "correndo", "fracao": None})         # sem nada: corre sem número
        self.assertEqual(a[5], {"modo": "servidor", "fracao": 1})
        self.assertEqual(a[6]["modo"], "estimada")                           # com a última duração, ela vence a etapa

    def test_tarefa_pela_rota(self):
        pasta = tempfile.mkdtemp(prefix="barra_")
        try:
            script = os.path.join(pasta, "t.mjs")
            url = "file:///" + os.path.join(WEB, "progresso.js").replace("\\", "/")
            open(script, "w", encoding="utf-8").write(
                "import { tarefaDaChamada as t } from %s;\n"
                "globalThis.location = { href: 'http://localhost:8766/editor' };\n"
                "console.log(JSON.stringify([t('/api/projetos/mercado-conceito/detalhar-premoldado', 'post'),"
                " t('/api/projetos/obra/desenhos/pr%%C3%%A9-moldado-completo/pdf', 'POST'),"
                " t('/api/projetos/obra/progresso'), t('/api/vivo?j=1'), t('/lib/three.module.js'),"
                " t('/api/modelo/ifc/exportar', 'POST')]));\n" % json.dumps(url))
            r = subprocess.run(["node", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            a = json.loads(r.stdout)
        finally:
            shutil.rmtree(pasta, ignore_errors=True)
        self.assertEqual(a[0], {"projeto": "mercado-conceito", "rotulo": "Pré-moldado",
                                "tarefa": "mercado-conceito|POST detalhar-premoldado",
                                "progresso": "/api/projetos/mercado-conceito/progresso"})
        # o desenho sai do nome da tarefa: o PDF de qualquer desenho estima pelo mesmo tempo
        self.assertEqual((a[1]["tarefa"], a[1]["rotulo"]), ("obra|POST desenhos/*/pdf", "Gerando o PDF"))
        self.assertEqual(a[2:5], [None, None, None])                          # as consultas da barra e o que não é /api/
        self.assertEqual((a[5]["projeto"], a[5]["progresso"], a[5]["rotulo"]), ("", "", "Exportando"))


if __name__ == "__main__":
    unittest.main()
