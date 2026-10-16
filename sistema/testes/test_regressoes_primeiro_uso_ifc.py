# -*- coding: utf-8 -*-
"""Regressões do teste de primeiro uso IFC → pranchas (16/10/2026): a Eng. Camila (agente detalhista-primeiro-uso-ifc)
abriu o IFC da ME-Sooro exportado do TecnoMETAL e tentou tirar as pranchas pelas telas
(Projeto/BRIEFINGS/Briefing-primeiro-uso-ifc.md, achados Q01–Q24). Cada teste falha sem a correção (ver
sistema/testes/REGRESSOES.md, seção "Primeiro uso").

Os testes rodam na forma de modelo em que os defeitos apareceram: a ME-Sooro como veio do TecnoMETAL (4.047 peças,
marcas M/P, terças ligadas sem chapa nos banzos), guardada do histórico do teste em
Projeto/OBRAS/ME-Sooro/teste-primeiro-uso/modelo-importado.json.gz. Sem o arquivo (outra máquina), pulam."""
import gzip
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app                                                   # noqa: E402
from nucleo.base import ErroDeDados                         # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOORO = os.path.join(RAIZ, "Projeto", "OBRAS", "ME-Sooro", "teste-primeiro-uso")
SLUG = "me-sooro"


def _copiar_sooro(pasta: str) -> None:
    os.makedirs(os.path.join(pasta, SLUG))
    shutil.copy(os.path.join(SOORO, "projeto.json"), os.path.join(pasta, SLUG, "projeto.json"))
    with gzip.open(os.path.join(SOORO, "modelo-importado.json.gz"), "rb") as f, \
            open(os.path.join(pasta, SLUG, "modelo.json"), "wb") as o:
        shutil.copyfileobj(f, o)


_TEM_SOORO = os.path.exists(os.path.join(SOORO, "modelo-importado.json.gz"))
SEM_SUPORTE = "me-sooro-sem-suporte"
_SOORO = {}


def _tirar_suportes_da_to6(pasta: str) -> None:
    """A ME-Sooro sem os suportes de terça da T.O.6 (M92), os parafusos ficando: a terça ligada direto, sem chapa — o
    caso que o padrão de fábrica no 3D não resolve sozinho e que tem de levar à peça (Q01) e aparecer no Conferir (Q17)."""
    from nucleo3d.geometria import malha
    from nucleo3d.modelo import Documento
    os.makedirs(os.path.join(pasta, SEM_SUPORTE))
    shutil.copy(os.path.join(SOORO, "projeto.json"), os.path.join(pasta, SEM_SUPORTE, "projeto.json"))
    with gzip.open(os.path.join(SOORO, "modelo-importado.json.gz"), "rt", encoding="utf-8") as f:
        m = json.load(f)
    doc = Documento.de_dict(m)
    tipos = app._tipos_de_producao(SEM_SUPORTE, doc)
    sup = {x.strip() for k, v in tipos.items() if v == "suporte_terca" for x in k.split("/")}

    def caixa(e):
        vs = malha(e)[0]
        return [min(v[i] for v in vs) - 5 for i in range(3)], [max(v[i] for v in vs) + 5 for i in range(3)]

    def cruza(a, b):
        return all(a[0][i] <= b[1][i] and b[0][i] <= a[1][i] for i in range(3))

    def pos(e):
        return ((e.atributos or {}).get("marcas") or {}).get("posicao")
    tercas = [caixa(e) for e in doc.entidades.values() if pos(e) == "M92"]
    tirar = {e.id for e in doc.entidades.values() if pos(e) in sup and any(cruza(caixa(e), c) for c in tercas)}
    assert tirar, "a T.O.6 da ME-Sooro tem suportes"
    m["entidades"] = [x for x in m["entidades"] if x["id"] not in tirar]
    with open(os.path.join(pasta, SEM_SUPORTE, "modelo.json"), "w", encoding="utf-8") as f:
        json.dump(m, f)


def setUpModule():
    """A ME-Sooro detalhada uma vez para o arquivo todo (≈1 min cada), como a Camila fez: Detalhar peças e conjuntos
    com o padrão de fábrica e "Rotular posições"; e a mesma sem os suportes da T.O.6."""
    if not _TEM_SOORO:
        return
    _SOORO["antigo"] = app.PROJETOS
    _SOORO["pasta"] = tempfile.mkdtemp(prefix="regr_primeiro_uso_ifc_")
    app.PROJETOS = _SOORO["pasta"]
    app._CACHE_REFERENCIA.clear()
    _copiar_sooro(_SOORO["pasta"])
    _tirar_suportes_da_to6(_SOORO["pasta"])
    _SOORO["resposta"] = app.detalhar_projeto(SLUG, {"rotular": True})
    _SOORO["resposta_sem_suporte"] = app.detalhar_projeto(SEM_SUPORTE, {})


def tearDownModule():
    if _SOORO:
        app.PROJETOS = _SOORO["antigo"]
        shutil.rmtree(_SOORO["pasta"], ignore_errors=True)


@unittest.skipUnless(_TEM_SOORO, "sem a ME-Sooro do teste de primeiro uso")
class _SooroDetalhada(unittest.TestCase):
    slug = SLUG

    @classmethod
    def setUpClass(cls):
        cls.pasta = _SOORO["pasta"]
        app.PROJETOS = cls.pasta
        cls.carimbo = app._vivos().ler_carimbo(cls.slug)

    def modelo(self) -> dict:
        with open(os.path.join(self.pasta, self.slug, "modelo.json"), encoding="utf-8") as f:
            return json.load(f)


class TestPrimeiroDetalharNoPassoDaMaquina(_SooroDetalhada):
    """Q01 — "O PDF das pranchas é recusado (T.O.2/3/5/6 a 60 mm, T.C.4 e T.L.2… a 80 mm) e nada me leva a resolver".
    A causa: o suporte de terça só ia ao passo da máquina quando o projeto já tinha os tipos de produção (nomes.json,
    gravado pelo próprio Detalhar). No 1º Detalhar de um IFC novo as 17 terças ficavam fora do passo e só o 2º as
    acertava. Agora os tipos vêm antes (app._tipos_de_producao)."""

    def test_primeiro_detalhar_deixa_as_tercas_no_passo(self):
        self.assertEqual(self.carimbo.get("fora_da_maquina"), [])

    def test_as_pranchas_podem_ser_emitidas(self):
        from nucleo2d.desenho import Desenho
        prancha = Desenho(nome="pranchas")
        prancha.metadados["pranchas"] = []
        vivos = app._vivos()
        antes = vivos.por_que_velho
        vivos.por_que_velho = lambda s: ""                 # a atualização automática não é o assunto aqui
        try:
            app._conferir_para_emitir(SLUG, [prancha])
        finally:
            vivos.por_que_velho = antes

    def test_segundo_padrao_nao_muda_nada(self):
        doc = app._documento3d_do_projeto(SLUG)
        r = app._padronizar_3d(SLUG, doc, regra=True, converter=True)
        self.assertFalse(r["mudou"], r["posicoes"])


class TestPdfRecusadoLevaAPeca(_SooroDetalhada):
    """Q01 — "O PDF das pranchas é recusado e nada me leva a resolver": o erro dizia "T.O.6: furos a 60 mm…" e a busca
    não achava T.O.6. Na terça ligada de verdade sem chapa (a ME-Sooro sem os suportes da T.O.6), cada terça vem com as
    peças do 3D (todas as cópias) e a barra em que se liga, para o "Ver no 3D" do erro e do aviso amarelo."""
    slug = SEM_SUPORTE

    def test_carimbo_traz_as_pecas_de_cada_terca(self):
        pecas = self.carimbo.get("fora_da_maquina_pecas") or []
        self.assertTrue(pecas, "a ME-Sooro tem terças ligadas sem chapa fora do passo da máquina")
        self.assertEqual([p["texto"] for p in pecas], self.carimbo.get("fora_da_maquina"))
        ents = {e["id"]: e for e in self.modelo()["entidades"]}
        nomes = {p["nome"] for p in pecas}
        self.assertIn("T.O.6", nomes)
        for p in pecas:
            self.assertTrue(p["ids"], p["nome"])
            for i in p["ids"]:
                self.assertIn(i, ents)
                self.assertEqual(((ents[i].get("atributos") or {}).get("marcas") or {}).get("nome"), p["nome"])
        # a terça sem chapa está ligada direto no banzo: a barra aparece junto no "Ver no 3D"
        self.assertTrue(any(p.get("ligadas") for p in pecas))

    def test_erro_do_pdf_traz_as_pecas_e_o_que_fazer(self):
        from nucleo2d.desenho import Desenho
        prancha = Desenho(nome="pranchas")
        prancha.metadados["pranchas"] = []
        with self.assertRaises(ErroDeDados) as c:
            app._conferir_para_emitir(SEM_SUPORTE, [prancha])
        e = c.exception
        self.assertIn("chapa de ligação", str(e))
        self.assertTrue(getattr(e, "pecas", None))
        self.assertTrue(all(p["ids"] for p in e.pecas))

    def test_estado_do_cad_traz_as_pecas(self):
        e = app._vivos().estado(SEM_SUPORTE, conferir=False)
        self.assertTrue(e.get("fora_da_maquina_pecas"))


class TestConferirAcusaOQueTravaOPdf(_SooroDetalhada):
    """Q17 — "Conferir antes de detalhar não acusa o que impede o PDF e não diz qual parafuso": 44 achados sem a
    furação fora da máquina, e 9 linhas iguais "não há espaço para a chave…". Na ME-Sooro sem os suportes da T.O.6."""
    slug = SEM_SUPORTE

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        corpo = {"documento": cls.modelo(cls), "projeto": SEM_SUPORTE, "quais": ["execucao", "producao"]}
        cls.conf = app.conferir_modelo(corpo)

    def test_regra_da_maquina_na_conferencia(self):
        maq = [a for a in self.conf["achados"] if a["regra"] == "maquina"]
        self.assertEqual(len(maq), len(self.carimbo["fora_da_maquina"]))
        self.assertTrue(any(a["texto"].startswith("T.O.6") for a in maq))
        self.assertTrue(all(a["ids"] for a in maq))
        self.assertIn("maquina", self.conf["regras"])

    def test_peca_maior_que_a_barra_comercial(self):
        bc = [a for a in self.conf["achados"] if a["regra"] == "barra_comercial"]
        self.assertTrue(any("29.400" in a["texto"] and "emenda" in a["texto"] for a in bc), [a["texto"] for a in bc])

    def test_chave_diz_qual_parafuso_e_quais_pecas(self):
        chave = [a for a in self.conf["achados"] if a["regra"] == "chave"]
        self.assertTrue(chave, "a ME-Sooro tem parafusos sem espaço para a chave")
        for a in chave:
            self.assertRegex(a["texto"], r"^parafuso M\d+ × \d+")
            self.assertNotEqual(a["texto"], "não há espaço para a chave: a peça vizinha ocupa o lugar da cabeça ou da porca")
        self.assertTrue(any(" em " in a["texto"] for a in chave))
        # depois do Detalhar, o nome de produção com a marca do IFC
        self.assertTrue(any("(" in a["texto"] for a in chave))


if __name__ == "__main__":
    unittest.main()
