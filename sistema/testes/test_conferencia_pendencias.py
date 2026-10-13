# -*- coding: utf-8 -*-
"""A aba Conferência (13/10): as pendências do resumo da obra com a resposta do usuário gravada no projeto
(conferencias.json, com o histórico de cada uma), e os documentos da obra na pasta documentos/ do projeto."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app                                   # noqa: E402
from nucleo.base import ErroDeDados          # noqa: E402
from projetos import Projetos                # noqa: E402
from saida import resumos                    # noqa: E402


class TestConferencia(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="conf_")
        self.antigo = app.PROJETOS
        app.PROJETOS = self.pasta
        self.g = Projetos(self.pasta)
        self.s = self.g.criar("Obra", tipo="desenho")["slug"]
        self.proj = os.path.join(self.pasta, self.s)

    def tearDown(self):
        app.PROJETOS = self.antigo

    def _resumo_com(self, pendencias):
        det = os.path.join(self.proj, "detalhamento")
        os.makedirs(det, exist_ok=True)
        for x in pendencias:
            x["chave"] = resumos.chave_da_pendencia(x)
        with open(os.path.join(det, resumos.ARQ_NUMEROS), "w", encoding="utf-8") as f:
            json.dump({"numeros": {}, "dimensoes": {}, "pendencias": pendencias}, f)

    def test_sem_resumo_e_depois_com_pendencias(self):
        r = app.conferencias_do_projeto(self.s)
        self.assertTrue(r["sem_resumo"] and r["itens"] == [] and r["abertas"] == 0)
        self._resumo_com([{"peca": "CH7", "perfil": "PLATE 125x110x3", "o_que": "dimensões diferem do nome: conferir", "ids": ["g1"]},
                          {"peca": "T.C.4", "perfil": "U150X50", "o_que": "furo(s) em 12 de 14 peças: conferir"}])
        r = app.conferencias_do_projeto(self.s)
        self.assertEqual(r["abertas"], 2)
        self.assertEqual([i["situacao"] for i in r["itens"]], ["aberta", "aberta"])
        self.assertEqual(r["itens"][0]["ids"], ["g1"])

    def test_responder_resolver_e_historico(self):
        self._resumo_com([{"peca": "CH7", "perfil": "PLATE", "o_que": "dimensões diferem do nome: conferir"},
                          {"peca": "T.C.4", "perfil": "U150X50", "o_que": "furo(s) em 12 de 14 peças: conferir"}])
        k1, k2 = [i["chave"] for i in app.conferencias_do_projeto(self.s)["itens"]]
        r = app.gravar_conferencia(self.s, {"chave": k1, "resposta": "Medida conferida no projeto.", "situacao": "respondida",
                                            "peca": "CH7", "perfil": "PLATE", "o_que": "dimensões diferem do nome: conferir"})
        self.assertEqual(r["abertas"], 2)                          # respondida ainda conta como aberta
        it = next(i for i in r["itens"] if i["chave"] == k1)
        self.assertEqual((it["situacao"], it["resposta"]), ("respondida", "Medida conferida no projeto."))
        self.assertTrue(it["quando"] and it["historico"] == [])
        # resolve: a resposta anterior vai para o histórico
        r = app.gravar_conferencia(self.s, {"chave": k1, "resposta": "Chapa refeita com 215 x 110.", "situacao": "resolvida"})
        it = next(i for i in r["itens"] if i["chave"] == k1)
        self.assertEqual(r["abertas"], 1)
        self.assertEqual(len(it["historico"]), 1)
        self.assertEqual(it["historico"][0]["resposta"], "Medida conferida no projeto.")
        # gravado no projeto, e o que vai para o resumo da obra
        d = json.load(open(os.path.join(self.proj, app.ARQ_CONFERENCIAS), encoding="utf-8"))
        self.assertEqual(d["itens"][k1]["situacao"], "resolvida")
        self.assertEqual(app._conferencias_por_chave(self.s)[k1]["situacao"], "resolvida")
        self.assertNotIn(k2, app._conferencias_por_chave(self.s))
        # a pendência resolvida que sai do resumo fica no histórico (antigas)
        self._resumo_com([{"peca": "T.C.4", "perfil": "U150X50", "o_que": "furo(s) em 13 de 14 peças: conferir"}])
        r = app.conferencias_do_projeto(self.s)
        self.assertEqual([i["chave"] for i in r["itens"]], [k2])    # a chave sobrevive ao número que mudou
        self.assertEqual([a["chave"] for a in r["antigas"]], [k1])
        with self.assertRaises(ErroDeDados):
            app.gravar_conferencia(self.s, {"chave": "", "resposta": "x"})
        with self.assertRaises(ErroDeDados):
            app.gravar_conferencia(self.s, {"chave": k2, "situacao": "feita"})

    def test_documentos_da_obra_na_lista_de_arquivos(self):
        self.assertEqual(app._documentos_da_obra(self.proj), [])
        docs = os.path.join(self.proj, app.PASTA_DOCUMENTOS)
        os.makedirs(docs)
        for nome in ("Comparativo-compras-2026-10-13.pdf", "notas.xlsx", "~$notas.xlsx", "lixo.tmp"):
            with open(os.path.join(docs, nome), "wb") as f:
                f.write(b"x")
        d = app._documentos_da_obra(self.proj)
        self.assertEqual(sorted(x["nome"] for x in d), ["Comparativo-compras-2026-10-13.pdf", "notas.xlsx"])
        self.assertTrue(all(x["url"].startswith("/saida/") and x["url"].endswith(x["nome"]) for x in d))


if __name__ == "__main__":
    unittest.main()
