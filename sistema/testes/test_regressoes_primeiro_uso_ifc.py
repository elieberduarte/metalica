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


class TestOQueODetalharMudouNo3D(_SooroDetalhada):
    """Q02 (decisão do usuário, 16/10: o padrão da máquina vence o projeto) — "desliguei a regra e o programa mexeu na
    furação mesmo assim, sem avisar": o Detalhar devolve o que gravou no 3D (etapas e posições) e a versão de antes,
    e o Desfazer volta a ela e para a atualização automática (que refaria o padrão na hora) até o próximo Detalhar."""

    def test_detalhar_diz_o_que_mudou(self):
        m = _SOORO["resposta"].get("mudancas_3d") or {}
        self.assertTrue(m.get("posicoes"))
        self.assertTrue(any("T.O.6" in x for x in m["posicoes"]), m["posicoes"][:10])
        self.assertTrue(any("oblongos" in e for e in m.get("etapas") or []), m.get("etapas"))
        self.assertTrue(any("suporte" in e for e in m.get("etapas") or []), m.get("etapas"))
        self.assertTrue(os.path.exists(os.path.join(self.pasta, SLUG, "historico", m["desfazer"])))
        self.assertIsNone(self.carimbo.get("desfeito"))

    def test_desfazer_volta_o_3d_e_para_a_atualizacao(self):
        copia = SLUG + "-desfazer"
        shutil.copytree(os.path.join(self.pasta, SLUG), os.path.join(self.pasta, copia))
        arquivo = _SOORO["resposta"]["mudancas_3d"]["desfazer"]
        app.desfazer_detalhamento(copia, {"arquivo": arquivo})
        with gzip.open(os.path.join(self.pasta, copia, "historico", arquivo), "rt", encoding="utf-8") as f:
            antes = json.load(f)
        with open(os.path.join(self.pasta, copia, "modelo.json"), encoding="utf-8") as f:
            agora = json.load(f)
        self.assertEqual(len(antes["entidades"]), len(agora["entidades"]))
        self.assertEqual(antes["entidades"][:50], agora["entidades"][:50])
        vivos = app._vivos()
        self.assertEqual(vivos.por_que_velho(copia), "")
        self.assertTrue(vivos.estado(copia, conferir=False).get("desfeito"))
        from nucleo2d.desenho import Desenho
        prancha = Desenho(nome="pranchas")
        prancha.metadados["pranchas"] = []
        with self.assertRaises(ErroDeDados) as c:
            app._conferir_para_emitir(copia, [prancha])
        self.assertIn("desfeito", str(c.exception))


class TestOpcoesDoDetalharValemNaAtualizacao(_SooroDetalhada):
    """Q03 — "o que escolhi no Detalhar se perde": dois minutos depois do Detalhar com "Rotular posições", a
    atualização automática detalhou de novo com os padrões e as pranchas saíram sem rótulo nas barras."""

    @staticmethod
    def _rotulos(pasta):
        with open(os.path.join(pasta, SLUG, "desenhos-2d", "detalhamento-tesouras.desenho.json"), encoding="utf-8") as f:
            d = json.load(f)
        import re
        return sum(1 for e in d["entidades"] if e.get("tipo") == "texto" and re.match(r"^B\.\d+$", str(e.get("texto") or "")))

    def test_opcoes_gravadas_no_projeto(self):
        with open(os.path.join(self.pasta, SLUG, "projeto.json"), encoding="utf-8") as f:
            p = json.load(f)
        self.assertEqual(p.get("opcoes_detalhamento"), {"rotular": True})

    def test_atualizacao_automatica_mantem_o_rotulo(self):
        self.assertGreater(self._rotulos(self.pasta), 0, "o Detalhar com Rotular escreve B.n nas barras da tesoura")
        app.detalhar_projeto(SLUG, {"automatico": True})
        self.assertGreater(self._rotulos(self.pasta), 0, "a atualização automática manteve o Rotular")


class TestCopiaDaChapaNaPranchaDaTesoura(_SooroDetalhada):
    """Q04 (e o N02 do auditor de números) — "a mesma chapa aparece em várias pranchas com quantidades diferentes": a
    cópia local na prancha da tesoura levava a composição de UMA tesoura ("CH2 08x" na T1 03x, que tem 24) e nada dizia
    que era cópia; quem somasse as pranchas fabricava errado."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        g = app._gerente()
        nomes = [d["nome"] for d in g.listar_desenhos(SLUG, contar=False) if d["nome"].startswith("detalhamento-")]
        r = app.montar_pranchas_projeto(SLUG, {"desenhos": nomes, "formato": "A1"})
        from nucleo2d.desenho import Desenho
        cls.pranchas = Desenho.de_dict(g.abrir_desenho(SLUG, r["desenho"]))
        cls.textos = [e.texto for e in cls.pranchas.entidades.values() if getattr(e, "texto", None)]

    def test_quantidade_da_prancha_e_das_tesouras_dela(self):
        self.assertIn("CH2 – 24x (ref.)", self.textos)          # T1 – 03x: 3 × 8
        self.assertIn("CH2 – 16x (ref.)", self.textos)          # T2 – 02x: 2 × 8
        self.assertIn("S.T.1 – 48x (ref.)", self.textos)
        self.assertIn("CH2 – 08x (ref.)", self.textos)          # T3 e T4 – 01x: 1 × 8
        self.assertIn("DP.1.1 – 06x (ref.)", self.textos)       # DP.1 – 03x: 3 × 2 (antes 02x)
        self.assertIn("S.T.2 – 12x (ref.)", self.textos)        # DP.1 – 03x: 3 × 4 (antes 08x)

    def test_copia_diz_onde_se_fabrica(self):
        import re
        refs = [x for x in self.textos if "(ref.)" in x]
        self.assertTrue(refs)
        self.assertTrue(any(re.search(r"24x · total 56x: fabricar pela PR\. \d\d/\d\d", x) for x in self.textos), "a legenda PARA MONTAR")
        self.assertIn("PARA MONTAR (fabricar em outra PR.)", self.textos)

    def test_conferencia_de_consistencia_sem_copia_errada(self):
        try:
            from saida import consistencia
        except ImportError:
            self.skipTest("saida/consistencia.py ainda não está no programa")
        achados = consistencia.conferir(os.path.join(self.pasta, SLUG))
        self.assertTrue(isinstance(achados, list))
        copias = [a["texto"] for a in achados if a.get("conferencia") == "copias"]
        self.assertEqual(copias, [])


class TestCotasQueAFabricaPrecisa(_SooroDetalhada):
    """Q05, Q06 e Q07 — o que faltava nas pranchas para a fábrica: a altura dos furos da terça, os chanfros das chapas, o
    furo da cantoneira até a aba e o "prever emenda" da cantoneira de 29,4 m (célula típica sem furo)."""

    def _desenho(self, nome):
        with open(os.path.join(self.pasta, SLUG, "desenhos-2d", "detalhamento-%s.desenho.json" % nome), encoding="utf-8") as f:
            return json.load(f)["entidades"]

    def _todos(self):
        pasta = os.path.join(self.pasta, SLUG, "desenhos-2d")
        for arq in os.listdir(pasta):
            if arq.startswith("detalhamento-") and "completo" not in arq and arq.endswith(".desenho.json"):
                with open(os.path.join(pasta, arq), encoding="utf-8") as f:
                    yield from json.load(f)["entidades"]

    def test_q05_altura_dos_furos_da_terca(self):
        textos = [e.get("texto") or "" for e in self._desenho("terças") if e.get("tipo") == "texto"]
        notas = [x for x in textos if x.startswith("furos na alma: ")]
        self.assertTrue(notas, "toda terça com furo duplo leva a nota da altura dos furos")
        self.assertIn("furos na alma: 1º a 50 da base, par a 50 (passo da máquina)", notas)

    def test_q06_chanfro_da_chapa(self):
        cotas = [e.get("texto") for e in self._todos() if e.get("tipo") == "cota" and (e.get("atributos") or {}).get("nome") == "CH2"]
        self.assertIn("4x 20×20", cotas)

    def test_q06_furo_da_cantoneira_ate_a_aba(self):
        verticais = [abs(e["p2"][1] - e["p1"][1]) for e in self._todos()
                     if e.get("tipo") == "cota" and e.get("modo") == "v" and (e.get("atributos") or {}).get("nome") == "CH14"]
        self.assertGreaterEqual(sum(1 for v in verticais if abs(v - 32.0) < 1.0), 2, verticais)

    def test_q07_prever_emenda_na_celula_tipica(self):
        # o "COMP=" é texto ou o texto da cota, conforme a versão da célula típica
        textos = [e.get("texto") or "" for e in self._todos() if e.get("tipo") in ("texto", "cota")]
        self.assertTrue(any(x.startswith("A.T.1 COMP=29400mm") and "PREVER EMENDA" in x for x in textos))
        self.assertTrue(any("maiores que a barra comercial de 12 m: prever emenda" in x for x in textos))


class TestParafusosEPorcasNaLista(_SooroDetalhada):
    """Q08 — "lista de parafusos sem classe, com nome cru do IFC" ("BOLT (A) 12x30 264", porcas e arruelas só dos
    chumbadores); N07 do auditor (decisão do usuário 16/10) — o chumbador nunca na regra do parafuso: no projeto recebido
    as porcas do projetista (na Sooro, 2 por perna: faltavam 28 porcas Ø3/4" na compra); no nosso, 2 porcas + 1 arruela."""

    def _acessorios(self):
        with open(os.path.join(self.pasta, SLUG, "detalhamento", "lista-de-materiais.json"), encoding="utf-8") as f:
            return {a["nome"]: a["quantidade"] for a in json.load(f)["acessorios"]}

    def test_q08_parafuso_por_extenso_com_classe_e_porca(self):
        ac = self._acessorios()
        self.assertFalse([k for k in ac if k.startswith("BOLT (")], ac)
        m12 = {k: v for k, v in ac.items() if k.startswith("Parafuso sextavado M12 x ")}
        self.assertTrue(m12 and all("ASTM A307" in k for k in m12), m12)
        self.assertEqual(ac.get("Porca sextavada M12 (dos parafusos)"), sum(m12.values()))
        self.assertEqual(ac.get("Arruela lisa M12 (dos parafusos)"), sum(m12.values()))

    def test_n07_porcas_do_chumbador_recebido_e_nosso(self):
        from nucleo2d.detalhar import levantar
        from nucleo2d.detalhe.base import _pecas, _fixadores, pontas_roscadas, _ids_de_chumbadores
        doc = app._documento3d_do_projeto(SLUG)
        pecas, _ = _pecas(doc, [], [], [])
        pontas, _u = pontas_roscadas(pecas, _fixadores(doc))
        ch = _ids_de_chumbadores(pecas)
        pernas = [p for p in pontas if p["peca"].id in ch and p["bitola"] == '3/4"']
        self.assertEqual(len(pernas), 28)                       # 14 chumbadores em U
        self.assertEqual(self._acessorios().get('Porca sextavada Ø3/4" UNC'), 2 * len(pernas))

        def porcas(origem, tirar=None):
            d = app._documento3d_do_projeto(SLUG)
            if tirar:
                d.remover(tirar) if hasattr(d, "remover") else d.entidades.pop(tirar)
            d.metadados["origem_projeto"] = origem
            return levantar(d, regra_tercas=False)["acessorios"].get('Porca sextavada Ø3/4" UNC')
        # uma porca a menos no chumbador do modelo: o recebido segue o projetista, o nosso, a regra
        self.assertEqual(porcas("recebido"), 56)
        um = next((i for i in pernas[0]["fixadores"] if porcas("recebido", tirar=i) == 55), None)
        self.assertIsNotNone(um, "tirar uma porca do chumbador do modelo tira uma porca da lista do projeto recebido")
        self.assertEqual(porcas("nosso", tirar=um), 56)


class TestFolgaNaPranchaDoProjetoRecebido(_SooroDetalhada):
    """Q16 — "(folga 1 < 1,5)" em toda terça e chapa da prancha: "é erro? fabrico assim?". A folga mínima é para o furo
    que nós calculamos (regra de 15/10: o furo do projetista vale); no projeto recebido sai só a folga, sem o alerta."""

    def test_sem_alerta_na_sooro(self):
        pasta = os.path.join(self.pasta, SLUG, "desenhos-2d")
        textos = []
        for arq in os.listdir(pasta):
            if arq.startswith("detalhamento-") and arq.endswith(".desenho.json"):
                with open(os.path.join(pasta, arq), encoding="utf-8") as f:
                    textos += [e.get("texto") or "" for e in json.load(f)["entidades"] if e.get("tipo") == "texto"]
        self.assertTrue(any("(folga 1)" in x for x in textos))
        self.assertFalse([x for x in textos if "< 1,5" in x][:3])

    def test_alerta_continua_no_projeto_nosso(self):
        from saida.detalhamento import Posicao, Furo
        p = Posicao(marca="CH1", tipo_ifc="IfcPlate")
        p.furos = [Furo(tipo="redondo", x=10, y=10, d=13.0, fixador='parafuso Ø12 mm', fixador_d=12.0)]
        self.assertIn("< 1,5", p.rotulo_furos_fixadores()[0])
        p.furos_do_projeto = True
        self.assertNotIn("< 1,5", p.rotulo_furos_fixadores()[0])


class TestChapaComUmaEspessura(_SooroDetalhada):
    """Q15 — "a chapa tem dois números de espessura": "PLATE 270x120x6 #1/4"" (o 6 do nome do IFC, a peça com 6,35)."""

    def test_uma_espessura_so(self):
        import re
        with open(os.path.join(self.pasta, SLUG, "desenhos-2d", "detalhamento-chaparias.desenho.json"), encoding="utf-8") as f:
            textos = [e.get("texto") or "" for e in json.load(f)["entidades"] if e.get("tipo") == "texto"]
        self.assertIn('PLATE 270x120 #1/4" (6,35 mm)', textos)
        self.assertFalse([x for x in textos if re.search(r"PLATE \d+x\d+x\d+\s+#", x)][:3])


class TestGrafiaDaCantoneira(_SooroDetalhada):
    """Q14 (a grafia; o prefixo CH da cantoneira espera a decisão do usuário) — "L 1 1/2'' X 1/8' '" com as aspas soltas."""

    def test_polegada_escrita_direito(self):
        textos = []
        pasta = os.path.join(self.pasta, SLUG, "desenhos-2d")
        for arq in os.listdir(pasta):
            if arq.startswith("detalhamento-") and "completo" not in arq and arq.endswith(".desenho.json"):
                with open(os.path.join(pasta, arq), encoding="utf-8") as f:
                    textos += [e.get("texto") or "" for e in json.load(f)["entidades"] if e.get("tipo") == "texto"]
        self.assertIn('L 1.1/2" x 1/8"', textos)
        self.assertFalse([x for x in textos if "' '" in x][:3])


class TestLocacaoDosChumbadores(_SooroDetalhada):
    """Q09 — "planta de chumbação sem a locação dos chumbadores": só os eixos e o rótulo CB num pontinho; o CB2 de D1/D7
    fica a ~260 mm do eixo D sem cota (montador M03)."""

    def test_cota_do_grupo_ate_o_eixo(self):
        with open(os.path.join(self.pasta, SLUG, "desenhos-2d", "detalhamento-chumbação.desenho.json"), encoding="utf-8") as f:
            ents = json.load(f)["entidades"]
        loc = [e for e in ents if e.get("tipo") == "cota" and (e.get("atributos") or {}).get("locacao")]
        self.assertTrue(loc)
        cb2 = [int(e["texto"]) for e in loc if (e["atributos"]["locacao"] == "CB2" and e["atributos"].get("eixo") == "D")]
        self.assertTrue(any(250 <= x <= 275 for x in cb2), cb2)


class TestEixosDo3DSaoOsDasPranchas(_SooroDetalhada):
    """Q13 — "os eixos do 3D não são os eixos das pranchas": antes do 1º Detalhar o 3D identificava 16 × 13 eixos (sem as
    tesouras reconhecidas) e as pranchas saíam com 7 × 5; "eixo 12" no 3D não existia na prancha."""

    def test_antes_e_depois_do_detalhar(self):
        novo = SLUG + "-sem-detalhar"
        os.makedirs(os.path.join(self.pasta, novo))
        shutil.copy(os.path.join(SOORO, "projeto.json"), os.path.join(self.pasta, novo, "projeto.json"))
        with gzip.open(os.path.join(SOORO, "modelo-importado.json.gz"), "rb") as f, \
                open(os.path.join(self.pasta, novo, "modelo.json"), "wb") as o:
            shutil.copyfileobj(f, o)

        def nomes(ex):
            return [x["nome"] for x in ex["numeros"]], [x["nome"] for x in ex["letras"]]
        antes = nomes(app.eixos_do_projeto(novo)["eixos"])
        depois = nomes(app.eixos_do_projeto(SLUG)["eixos"])
        self.assertEqual(antes, depois)
        self.assertEqual(antes, (["1", "2", "3", "4", "5", "6", "7"], ["A", "B", "C", "D", "E"]))
        ref = sorted({e.get("nome") for e in app.referencia_do_lancamento(novo).get("eixos", [])})
        self.assertEqual(ref, sorted(antes[0] + antes[1]))


class TestDxfDeCorteDasChapas(_SooroDetalhada):
    """Q19 — "não há DXF de corte das chapas": o DXF do desenho das chaparias juntava cotas, textos, chumbadores e
    tirantes. Agora um DXF por chapa, em mm reais, só o contorno (CORTE) e os furos (FURO), num ZIP."""

    def test_um_dxf_por_chapa_so_contorno_e_furos(self):
        import collections
        import zipfile
        import ezdxf
        r = app.corte_das_chapas(SLUG)
        self.assertGreaterEqual(r["chapas"], 15)
        z = zipfile.ZipFile(os.path.join(self.pasta, SLUG, "detalhamento", "corte-chapas.zip"))
        nomes = z.namelist()
        ch2 = [n for n in nomes if n.startswith("CH2_")]
        self.assertEqual(len(ch2), 1)
        self.assertRegex(ch2[0], r"^CH2_6,\d+mm_56x\.dxf$")
        tmp = tempfile.mkdtemp(prefix="corte_")
        for n in nomes:
            arq = os.path.join(tmp, n)
            with open(arq, "wb") as f:
                f.write(z.read(n))
            msp = ezdxf.readfile(arq).modelspace()
            tipos = collections.Counter((e.dxftype(), e.dxf.layer) for e in msp)
            self.assertEqual(sum(q for (tp, cam), q in tipos.items() if cam == "CORTE"), 1, (n, tipos))
            self.assertFalse([k for k in tipos if k[0] in ("TEXT", "MTEXT", "DIMENSION", "INSERT")], (n, tipos))
            if n == ch2[0]:
                self.assertEqual(tipos.get(("CIRCLE", "FURO")), 2)
                pts = list(next(iter(msp.query("LWPOLYLINE"))).get_points("xy"))
                ext = sorted((max(q[i] for q in pts) - min(q[i] for q in pts)) for i in (0, 1))
                self.assertAlmostEqual(ext[0], 120.0, delta=1.0)                  # 270 × 120 em mm reais
                self.assertAlmostEqual(ext[1], 270.0, delta=1.0)
        shutil.rmtree(tmp, ignore_errors=True)


class TestCarimboLembrado(_SooroDetalhada):
    """Q20 — "o diálogo não lembra o que digitei": o Projetista digitado em Montar pranchas não ficava no projeto e
    a revisão voltava a 00."""

    def test_projetista_e_revisao_ficam_no_projeto(self):
        g = app._gerente()
        nomes = [d["nome"] for d in g.listar_desenhos(SLUG, contar=False) if d["nome"].startswith("detalhamento-chap")]
        app.montar_pranchas_projeto(SLUG, {"desenhos": nomes, "formato": "A1", "titulo": "Pranchas Q20",
                                           "carimbo": {"responsavel": "Eng. Camila", "revisao": "01"}})
        p = g.ler(SLUG)
        self.assertEqual(p.get("responsavel"), "Eng. Camila")
        self.assertEqual((p.get("carimbo_pranchas") or {}).get("revisao"), "01")
        # sem digitar de novo: a revisão gravada vale
        r = app.montar_pranchas_projeto(SLUG, {"desenhos": nomes, "formato": "A1", "titulo": "Pranchas Q20b"})
        from nucleo2d.desenho import Desenho
        d = Desenho.de_dict(g.abrir_desenho(SLUG, r["desenho"]))
        textos = [e.texto for e in d.entidades.values() if getattr(e, "texto", None)]
        self.assertTrue(any("REV. 01" in x for x in textos))
        self.assertIn("ENG. CAMILA", [x.upper() for x in textos])


class TestResumoDaImportacao(_SooroDetalhada):
    """Q21 — "nenhum resumo do que o IFC trouxe": a detalhista juntou os números pelo painel de camadas."""

    def test_resumo_da_sooro(self):
        from nucleo3d.modelo import Documento
        with gzip.open(os.path.join(SOORO, "modelo-importado.json.gz"), "rt", encoding="utf-8") as f:
            doc = Documento.de_dict(json.load(f))
        r = app._resumo_da_importacao(doc)
        self.assertEqual(r["pecas"], 4047)
        self.assertEqual((r["chapas"], r["fixadores"], r["telhas"]), (652, 1342, 968))
        self.assertEqual(r["n_perfis_fora"], 0)
        self.assertGreater(r["marcas"]["pecas"], 100)

    def test_importar_grava_o_resumo_no_projeto(self):
        import base64
        from projetos import Projetos
        s = Projetos(self.pasta).criar("IFC pequeno", tipo="ifc")["slug"]
        ifc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_ifc", "estrutura_mm.ifc")
        with open(ifc, "rb") as f:
            r = app.importar_ifc_no_projeto(s, {"nome": "estrutura_mm.ifc", "conteudo_b64": base64.b64encode(f.read()).decode()})
        self.assertIn("resumo", r)
        self.assertEqual(app._gerente().ler(s).get("importacao_resumo"), r["resumo"])


class TestAjudaComORoteiroDoIfc(unittest.TestCase):
    """Q22 — "a Ajuda não guia o caminho do IFC": texto corrido, sem um roteiro IFC → pranchas. O roteiro no topo, com os
    caminhos da barra (test_ajuda_menus confere que cada caminho em negrito existe)."""

    def test_roteiro(self):
        import re
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "ajuda.html"), encoding="utf-8") as f:
            h = f.read()
        i = h.index('id="ifc-pranchas"')
        bloco = h[i:h.index("<h2", i + 10)]
        for c in ("Novo a partir de IFC", "Detalhamento › Conferir antes de detalhar", "Detalhamento › Detalhar peças e conjuntos",
                  "Detalhamento › Pranchas › Montar pranchas (automático)", "Arquivo › Exportar › PDF de todas as pranchas",
                  "DXF de corte (1:1)"):
            self.assertIn(c, re.sub(r"<[^>]+>", "", bloco))


DEPOSITO = os.path.join(RAIZ, "Projeto", "bateria", "entradas", "me-sooro-depósito-químico")


@unittest.skipUnless(os.path.exists(os.path.join(DEPOSITO, "modelo.json")), "sem a entrada da bateria do Depósito Químico")
class TestPranchasDoDepositoQuimico(unittest.TestCase):
    """Achado da conferência de consistência (agente auditor-de-numeros, 16/10): o Depósito Químico (ME-Sooro, IFC do
    TecnoMETAL) não montava as pranchas — KeyError 'categoria' em _juntar_quase_vazias: a cópia local da montagem
    "DP.1.1 + DP.1.2" saía da célula da família, que não tem categoria."""

    def test_monta_as_pranchas(self):
        antigo = app.PROJETOS
        pasta = tempfile.mkdtemp(prefix="regr_deposito_")
        try:
            slug = os.path.basename(DEPOSITO)
            shutil.copytree(DEPOSITO, os.path.join(pasta, slug))
            app.PROJETOS = pasta
            app.detalhar_projeto(slug, {})
            g = app._gerente()
            nomes = [d["nome"] for d in g.listar_desenhos(slug, contar=False) if d["nome"].startswith("detalhamento-")]
            r = app.montar_pranchas_projeto(slug, {"desenhos": nomes, "formato": "A1"})
            self.assertGreater(len(r["pranchas"]), 5)
        finally:
            app.PROJETOS = antigo
            shutil.rmtree(pasta, ignore_errors=True)



SALA = os.path.join(RAIZ, "Projeto", "bateria", "entradas", "me-sooro-sala-compressores")


@unittest.skipUnless(os.path.exists(os.path.join(SALA, "modelo.json")), "sem a entrada da bateria da Sala dos Compressores")
class TestCopiaNaTesouraDeMetadesDiferentes(unittest.TestCase):
    """Q04 na tesoura montada de metades diferentes (conferência de consistência da bateria, 16/10): na Sala dos
    Compressores, a "T2 – 02x" (M2 + M7) dizia CH3 x1 na composição (são 4 + 2) e a cópia na prancha saía 2x em vez de 12x —
    a composição era contada pelas peças de um exemplar, e a separação das instâncias dava chapas à vizinha."""

    def test_copia_confere_com_as_metades(self):
        from saida import consistencia
        antigo = app.PROJETOS
        pasta = tempfile.mkdtemp(prefix="regr_sala_")
        try:
            slug = os.path.basename(SALA)
            shutil.copytree(SALA, os.path.join(pasta, slug))
            app.PROJETOS = pasta
            app.detalhar_projeto(slug, {})
            g = app._gerente()
            with open(os.path.join(pasta, slug, "desenhos-2d", "detalhamento-tesouras.desenho.json"), encoding="utf-8") as f:
                itens = json.load(f)["metadados"]["detalhamento"]["itens"]
            ch3 = {x["nome"]: x["qtd"] for x in itens["M2 + M7"]["composicao"]}.get("CH3")
            self.assertEqual(ch3, 6)
            nomes = [d["nome"] for d in g.listar_desenhos(slug, contar=False) if d["nome"].startswith("detalhamento-")]
            app.montar_pranchas_projeto(slug, {"desenhos": nomes, "formato": "A1"})
            copias = [a["texto"] for a in consistencia.conferir(os.path.join(pasta, slug)) if a["conferencia"] == "copias"]
            self.assertEqual(copias, [])
        finally:
            app.PROJETOS = antigo
            shutil.rmtree(pasta, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
