# -*- coding: utf-8 -*-
"""Testes da leitura de IFC: o leitor STEP (`ifc/step.py`) e o importador
(`ifc/importar.py`).

O que precisa estar provado, em ordem de importância:

1. **Ida e volta.** Um documento exportado por `ifc/exportar.py` e importado de novo
   volta com os mesmos elementos, nas mesmas posições (1 mm), com o mesmo perfil do
   catálogo e o mesmo tipo: barra volta barra, chapa volta chapa. É o que prova que
   um modelo recebido pode ser editado como estrutura.
2. **Sintaxe da parte 21.** Aspas escapadas, `\\X2\\`, listas aninhadas, `$`, `*`,
   instanciação complexa, instruções em várias linhas e comentários.
3. **Unidades e colocação.** Arquivo em metro chega mil vezes maior em milímetro;
   elemento dentro de pavimento deslocado chega na posição global certa.
4. **Geometria.** Volumes conhecidos para extrusão, brep, malhas indexadas, recorte
   por meio-espaço, disco varrido, contorno com vazio e curva composta.
5. **Robustez.** Arquivo truncado, referência inexistente e tipo desconhecido viram
   aviso no relatório, nunca exceção.

Os arquivos de `testes/dados_ifc/` foram escritos à mão e trazem no comentário do
cabeçalho o que se espera deles. O galpão grande é gerado pelo exportador na hora.

    python testes/test_ifc_importar.py
    python -m pytest testes/test_ifc_importar.py -q
"""
import json
import math
import os
import sys
import tempfile
import time
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from ifc.step import (DERIVADO, Enumeracao, ErroStep, Ref, Tipado,     # noqa: E402
                      decodificar_texto, ler, ler_texto)
from ifc.importar import (Importador, base_secao, importar,            # noqa: E402
                          importar_texto, inspecionar, m_de_eixos,
                          m_direcao, m_multiplicar, m_ponto)
from nucleo.perfis import banco                                        # noqa: E402
from nucleo3d.modelo import Barra, Chapa, Documento, Solido            # noqa: E402

try:
    from ifc.exportar import exportar, para_texto                      # noqa: E402
except Exception:                                                      # pragma: no cover
    exportar = para_texto = None

try:
    from nucleo3d.geometria import base_local                          # noqa: E402
except Exception:                                                      # pragma: no cover
    base_local = None

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_ifc")


def dado(nome: str) -> str:
    return os.path.join(DADOS, nome)


def texto_de(nome: str) -> str:
    with open(dado(nome), encoding="utf-8") as f:
        return f.read()


def nome_catalogo(tipo: str, filtro) -> str:
    """Nome de um perfil do catálogo, sem escrever a grafia à mão no teste."""
    for p in banco().lista(tipo):
        if filtro(p):
            return p.nome
    raise unittest.SkipTest("catálogo sem perfil %s adequado ao teste" % tipo)


TUBO = nome_catalogo("tubo", lambda p: p.dados.get("tipo") == "redondo"
                     and abs(p.d - 33.7) < 1e-6)
UE = nome_catalogo("Ue", lambda p: p.nome.startswith("Ue"))
L40 = nome_catalogo("L", lambda p: abs(p.bf - 40) < 1e-6 and abs(p.tw - 4) < 1e-6)


def por_nome(doc: Documento) -> dict:
    return {e.nome: e for e in doc.entidades.values()}


def caixa(pts):
    return (tuple(min(p[i] for p in pts) for i in range(3)),
            tuple(max(p[i] for p in pts) for i in range(3)))


class Asserts(unittest.TestCase):
    def assertPonto(self, a, b, tol=1.0, msg=None):
        self.assertLessEqual(math.dist(a, b), tol, msg or "%s != %s" % (a, b))

    def assertRelativo(self, valor, esperado, tol, msg=None):
        self.assertLessEqual(abs(valor - esperado), tol * abs(esperado),
                             msg or "%g != %g (tol %.1f %%)" % (valor, esperado, tol * 100))


# =================================================================== leitor STEP

class TestLeitorStep(Asserts):
    """`sintaxe.ifc` junta os casos difíceis da parte 21 num arquivo só."""

    @classmethod
    def setUpClass(cls):
        cls.arq = ler(dado("sintaxe.ifc"))

    def test_leitura_sem_avisos(self):
        self.assertEqual(self.arq.avisos, [])
        self.assertEqual(sorted(self.arq.entidades), [1, 2, 3, 4, 5, 6])

    def test_cabecalho(self):
        self.assertEqual(self.arq.schema, "IFC2X3")
        self.assertEqual(self.arq.aplicacao, "Programa X")
        self.assertEqual(self.arq.nome_original, "sintaxe.ifc")
        self.assertEqual(self.arq.descricao[1], "Comentário")
        self.assertEqual(self.arq.cabecalho["FILE_NAME"][2], ["João d'Avila"])

    def test_textos_com_aspas_e_escapes(self):
        t = self.arq.entidades[1].args
        self.assertEqual(t[0], "It's a 'quoted' string")
        self.assertEqual(t[1], "Aço estrutural")                # \X2\ de um caractere
        self.assertEqual(t[2], "café")                          # \S\ (latin-1 + 128)
        self.assertEqual(t[3], "Construção")                    # \X2\ de dois caracteres
        self.assertEqual(t[4], "sorriso \U0001F600")            # \X4\
        self.assertEqual(t[5], "barra \\ invertida")            # \\
        self.assertEqual(t[6], "ponto;e vírgula")               # ';' dentro do texto e \X\
        self.assertEqual(t[7], "/* isto nao e comentario */")
        self.assertEqual(t[8], "")

    def test_decodificacao_direta(self):
        self.assertEqual(decodificar_texto("\\X2\\D83DDE00\\X0\\"), "\U0001F600")  # par UTF-16
        self.assertEqual(decodificar_texto(r"\PA\ol\X\E1"), "olá")
        self.assertEqual(decodificar_texto("sem escape"), "sem escape")

    def test_listas_aninhadas_e_valores_especiais(self):
        a = self.arq.entidades[2].args
        self.assertEqual(a[0], [[1, 2], [3, [4, 5]]])
        self.assertEqual(a[1], [])
        self.assertEqual(a[2], [1, 3])
        self.assertTrue(all(type(r) is Ref for r in a[2]))
        self.assertIsNone(a[3])                                 # $
        self.assertIs(a[4], DERIVADO)                           # *
        self.assertEqual(a[5:8], [True, False, None])           # .T. .F. .U.
        self.assertIsInstance(a[8], Enumeracao)
        self.assertEqual(a[8], "ELEMENT")
        self.assertAlmostEqual(a[9], -1.5e-3)
        self.assertIs(type(a[10]), int)
        self.assertIs(type(a[11]), float)
        self.assertIsInstance(a[12], Tipado)
        self.assertEqual((a[12].tipo, a[12].valor), ("IFCLABEL", "rotulo"))
        self.assertEqual(a[13].valor, 2.5)

    def test_instanciacao_complexa(self):
        e = self.arq.entidades[3]
        self.assertEqual(e.tipos, ["LENGTH_UNIT", "NAMED_UNIT", "SI_UNIT"])
        self.assertEqual(e.parte("SI_UNIT"), ["MILLI", "METRE"])
        self.assertEqual(e.parte("NAMED_UNIT"), [DERIVADO])
        self.assertEqual(e.parte("LENGTH_UNIT"), [])
        self.assertIn(e, self.arq.por_tipo("si_unit"))          # acha por qualquer parte

    def test_instrucao_em_varias_linhas_com_comentario(self):
        self.assertEqual(self.arq.entidades[4].args, ["linha 1", [1.0, 2.0], 3])
        self.assertEqual(self.arq.entidades[5].args, [4, [1, 2], "x"])
        self.assertEqual(self.arq.entidades[6].args, [])

    def test_referencias_e_inversos(self):
        dois = self.arq.entidades[2]
        self.assertIs(self.arq.resolver(dois.args[2][0]), self.arq.entidades[1])
        self.assertIsNone(self.arq.resolver(Ref(12345)))
        quem_aponta_para_1 = {e.id for e in self.arq.inversos(1)}
        self.assertEqual(quem_aponta_para_1, {2, 5})
        self.assertEqual([e.id for e in self.arq.inversos_tipo(4, "IfcEspacado")], [5])

    def test_so_cabecalho(self):
        arq = ler(dado("sintaxe.ifc"), so_cabecalho=True)
        self.assertEqual(arq.schema, "IFC2X3")
        self.assertEqual(len(arq.entidades), 0)

    def test_arquivo_inexistente_falha_explicitamente(self):
        with self.assertRaises(ErroStep):
            ler(dado("nao_existe.ifc"))

    def test_arquivo_grande_por_streaming(self):
        """60 mil entidades em várias linhas físicas: lê inteiro, em poucos segundos."""
        n = 60000
        caminho = os.path.join(tempfile.mkdtemp(prefix="step_"), "grande.ifc")
        with open(caminho, "w", encoding="ascii") as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n")
            for i in range(1, n + 1):
                f.write("#%d=IFCCARTESIANPOINT((%d.,\n  %d.5,0.));\n" % (i, i, i))
            f.write("ENDSEC;\nEND-ISO-10303-21;\n")
        inicio = time.time()
        arq = ler(caminho)
        tempo = time.time() - inicio
        self.assertEqual(len(arq.entidades), n)
        self.assertEqual(arq.entidades[n].args, [[float(n), n + 0.5, 0.0]])
        self.assertLess(tempo, 20.0)


# =================================================================== unidades e colocação

class TestUnidadesEColocacao(Asserts):
    """`caixa_metro.ifc`: caixa 1×2×3 m em (1,1,0) no pavimento +3 m do prédio em (10,20,0)."""

    @classmethod
    def setUpClass(cls):
        cls.doc = importar(dado("caixa_metro.ifc"))
        cls.caixa = cls.doc.solidos[0]

    def test_metro_vira_milimetro(self):
        rel = self.doc.metadados["importacao"]
        self.assertEqual(rel["escala_para_mm"], 1000.0)
        self.assertEqual(rel["unidade_origem"], "metro")

    def test_mesmo_arquivo_em_milimetro_fica_mil_vezes_menor(self):
        texto = texto_de("caixa_metro.ifc").replace(
            "#1=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);",
            "#1=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);")
        em_mm = importar_texto(texto).solidos[0]
        (a0, a1), (b0, b1) = caixa(self.caixa.vertices), caixa(em_mm.vertices)
        for i in range(3):
            self.assertAlmostEqual(a0[i], 1000 * b0[i], places=6)
            self.assertAlmostEqual(a1[i], 1000 * b1[i], places=6)

    def test_unidade_por_conversao(self):
        """Polegada declarada por IfcConversionBasedUnit: 1 unidade = 25,4 mm."""
        texto = texto_de("caixa_metro.ifc").replace(
            "#1=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);",
            "#1=IFCCONVERSIONBASEDUNIT(#200,.LENGTHUNIT.,'INCH',#201);\n"
            "#200=IFCDIMENSIONALEXPONENTS(1,0,0,0,0,0,0);\n"
            "#201=IFCMEASUREWITHUNIT(IFCLENGTHMEASURE(0.0254),#202);\n"
            "#202=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);")
        doc = importar_texto(texto)
        self.assertAlmostEqual(doc.metadados["importacao"]["escala_para_mm"], 25.4)
        self.assertRelativo(doc.solidos[0].volume, 6 * 25.4 ** 3, 1e-9)

    def test_placement_encadeado_chega_na_posicao_global(self):
        minimo, maximo = caixa(self.caixa.vertices)
        self.assertPonto(minimo, (11000.0, 21000.0, 3000.0), 1e-6)
        self.assertPonto(maximo, (12000.0, 23000.0, 6000.0), 1e-6)

    def test_rotacao_no_placement(self):
        """Pavimento girado 90° em torno de Z: o deslocamento local (1,1,0) gira junto."""
        texto = texto_de("caixa_metro.ifc").replace(
            "#18=IFCAXIS2PLACEMENT3D(#17,$,$);",
            "#18=IFCAXIS2PLACEMENT3D(#17,#6,#300);\n#300=IFCDIRECTION((0.,1.,0.));")
        s = importar_texto(texto).solidos[0]
        minimo, maximo = caixa(s.vertices)
        # local x -> global y, local y -> global -x; caixa local de (1,1)..(2,3)
        self.assertPonto(minimo, (10000 - 3000, 20000 + 1000, 3000), 1e-6)
        self.assertPonto(maximo, (10000 - 1000, 20000 + 2000, 6000), 1e-6)

    def test_matrizes_4x4(self):
        m = m_de_eixos((1.0, 2.0, 3.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
        self.assertPonto(m_ponto(m, (1, 0, 0)), (1, 3, 3), 1e-12)
        self.assertPonto(m_ponto(m, (0, 1, 0)), (0, 2, 3), 1e-12)
        self.assertPonto(m_direcao(m, (0, 0, 5)), (0, 0, 5), 1e-12)
        dupla = m_multiplicar(m, m)
        self.assertPonto(m_ponto(dupla, (0, 0, 0)), m_ponto(m, m_ponto(m, (0, 0, 0))), 1e-12)

    def test_hierarquia_origem_e_tipo(self):
        self.assertEqual(self.caixa.camada, "Pavimento Terreo")
        self.assertIn("Pavimento Terreo", self.doc.camadas)
        self.assertEqual(self.caixa.origem_ifc, "3Ehr0Mmq95GgL6yKXVAB05")
        self.assertEqual(self.caixa.atributos["tipo_ifc"], "IfcBuildingElementProxy")
        self.assertEqual(self.caixa.tipo_ifc(), "IfcBuildingElementProxy")

    def test_propriedades_e_quantidades(self):
        props = self.caixa.atributos["propriedades"]
        self.assertEqual(props["Pset_BuildingElementProxyCommon"],
                         {"Reference": "CX-1", "IsExternal": False, "LoadBearing": True})
        self.assertEqual(props["BaseQuantities"], {"GrossVolume": 6.0, "Height": 3.0})

    def test_material_com_cor_do_estilo(self):
        self.assertEqual(self.caixa.material, "Concreto C30")
        m = self.doc.materiais["Concreto C30"]
        self.assertEqual(m.cor, "#b8b2a6")          # (0,72; 0,70; 0,65) × 255
        self.assertEqual(m.metalico, 0.0)


# =================================================================== geometria

class TestGeometria(Asserts):
    """`geometrias_mm.ifc`: um elemento por tipo de geometria, volume no cabeçalho."""

    @classmethod
    def setUpClass(cls):
        cls.doc = importar(dado("geometrias_mm.ifc"), segmentos_circulo=64)
        cls.g = por_nome(cls.doc)
        cls.rel = cls.doc.metadados["importacao"]

    def test_brep_de_caixa_da_volume_de_caixa(self):
        s = importar(dado("caixa_metro.ifc")).solidos[0]
        self.assertRelativo(s.volume, 6e9, 1e-9)
        self.assertEqual(len(s.faces), 6)

    def test_extrusao_de_perfil_retangular(self):
        doc = importar(dado("estrutura_mm.ifc"), estrutural=False)
        chapa = por_nome(doc)["CH1"]
        self.assertIsInstance(chapa, Solido)
        self.assertRelativo(chapa.volume, 200 * 300 * 12.7, 1e-9)

    def test_extrusao_de_perfil_i(self):
        vs = por_nome(importar(dado("estrutura_mm.ifc")))["VS1"]
        area = 2 * 400 * 30 + (1000 - 2 * 30) * 20
        self.assertRelativo(vs.volume, area * 6000, 1e-9)

    def test_recorte_por_meio_espaco(self):
        g1 = self.g["G1"]
        self.assertRelativo(g1.volume, 100 * 100 * 400, 1e-9)
        self.assertAlmostEqual(min(v[2] for v in g1.vertices), 600.0, places=6)

    def test_disco_varrido(self):
        self.assertRelativo(self.g["G2"].volume, math.pi * 50 ** 2 * 1000, 0.02)

    def test_malha_triangulada_e_poligonal(self):
        self.assertRelativo(self.g["G3"].volume, 1e9, 1e-9)
        self.assertRelativo(self.g["G4"].volume, 500 ** 3, 1e-9)

    def test_contorno_com_vazio(self):
        self.assertRelativo(self.g["G5"].volume, (400 ** 2 - 200 ** 2) * 100, 1e-9)
        self.assertEqual(self.g["G5"].atributos["tipo_ifc"], "IfcSlab")

    def test_curva_composta_com_arco(self):
        self.assertRelativo(self.g["G6"].volume, math.pi * 100 ** 2 / 2 * 10, 0.02)

    def test_nao_suportado_vira_caixa_com_aviso(self):
        g7 = self.g["G7"]
        self.assertPonto(caixa(g7.vertices)[1], (200, 300, 400), 1e-6)
        self.assertRelativo(g7.volume, 200 * 300 * 400, 1e-9)
        self.assertEqual(self.rel["nao_suportados"], {"IFCADVANCEDBREP": 1})
        self.assertTrue(any("IFCADVANCEDBREP" in a for a in self.rel["avisos"]))

    def test_nenhum_elemento_sumiu(self):
        self.assertEqual(sorted(self.g), ["G1", "G2", "G3", "G4", "G5", "G6", "G7"])
        for s in self.doc.solidos:
            for v in s.vertices:
                self.assertTrue(all(math.isfinite(c) for c in v))

    def test_item_mapeado_aplica_a_transformacao(self):
        doc = importar(dado("estrutura_mm.ifc"), estrutural=False)
        for nome, x in (("C1", 2000.0), ("C2", 4000.0)):
            minimo, maximo = caixa(por_nome(doc)[nome].vertices)
            self.assertAlmostEqual((minimo[0] + maximo[0]) / 2, x, delta=20.0)
            self.assertAlmostEqual(maximo[2] - minimo[2], 3000.0, places=6)


# =================================================================== reconhecimento estrutural

class TestReconhecimentoEstrutural(Asserts):
    """`estrutura_mm.ifc`: pórtico com pilar, viga, terça, dois contraventamentos por
    item mapeado, uma chapa e um perfil soldado fora do catálogo."""

    @classmethod
    def setUpClass(cls):
        cls.doc = importar(dado("estrutura_mm.ifc"))
        cls.e = por_nome(cls.doc)
        cls.rel = cls.doc.metadados["importacao"]

    def test_o_que_virou_barra_chapa_e_solido(self):
        self.assertEqual(sorted(b.nome for b in self.doc.barras),
                         ["C1", "C2", "P1", "T1", "V1"])
        self.assertEqual([c.nome for c in self.doc.chapas], ["CH1"])
        self.assertEqual([s.nome for s in self.doc.solidos], ["VS1"])
        self.assertEqual((self.rel["barras"], self.rel["chapas"], self.rel["solidos"]),
                         (5, 1, 1))
        self.assertEqual(self.rel["contagem_por_tipo"],
                         {"IfcBeam": 2, "IfcColumn": 1, "IfcMember": 3, "IfcPlate": 1})

    def test_eixo_e_perfil_do_pilar_e_da_viga(self):
        p1, v1 = self.e["P1"], self.e["V1"]
        self.assertEqual((p1.perfil, p1.papel), ("W 310×38,7", "pilar"))
        self.assertPonto(p1.inicio, (0, 0, 0), 1e-6)
        self.assertPonto(p1.fim, (0, 0, 6000), 1e-6)
        self.assertEqual((v1.perfil, v1.papel), ("W 310×38,7", "viga"))
        self.assertPonto(v1.inicio, (0, 0, 6000), 1e-6)
        self.assertPonto(v1.fim, (6000, 0, 6000), 1e-6)
        self.assertAlmostEqual(v1.comprimento, 6000.0, places=6)

    def test_terca_tubular_casada_pelas_dimensoes(self):
        t1 = self.e["T1"]
        p = banco().get(t1.perfil)
        self.assertEqual(t1.perfil, TUBO)
        self.assertAlmostEqual(p.d, 33.7)
        self.assertAlmostEqual(p.tw, 2.65)
        self.assertEqual(t1.papel, "terça")                     # PredefinedType .PURLIN.
        self.assertPonto(t1.fim, (6000, 3000, 6000), 1e-6)

    def test_contraventamento_por_item_mapeado(self):
        for nome, x in (("C1", 2000.0), ("C2", 4000.0)):
            c = self.e[nome]
            self.assertEqual((c.perfil, c.papel), (L40, "contraventamento"))
            self.assertPonto(c.inicio, (x, 0, 0), 1e-6)
            self.assertPonto(c.fim, (x, 0, 3000), 1e-6)

    def test_perfil_fora_do_catalogo_vira_solido_e_fica_no_relatorio(self):
        self.assertIsInstance(self.e["VS1"], Solido)
        sem = self.rel["sem_perfil_no_catalogo"]
        self.assertEqual([s["elemento"] for s in sem], ["VS1"])
        self.assertEqual((sem[0]["d"], sem[0]["bf"]), (1000.0, 400.0))

    def test_registro_do_casamento(self):
        casados = {c["elemento"]: c for c in self.rel["perfis_casados"]}
        self.assertEqual(sorted(casados), ["C1", "C2", "P1", "T1", "V1"])
        for c in casados.values():
            self.assertLessEqual(c["erro_pct"], 5.0)
            self.assertTrue(c["perfil"] and c["familia"])

    def test_casamento_por_dimensao_com_tolerancia_de_5_por_cento(self):
        base = texto_de("estrutura_mm.ifc")
        linha = "#22=IFCISHAPEPROFILEDEF(.AREA.,'W 310x38,7',#21,165.,310.,5.8,9.7,11.,$,$);"
        self.assertIn(linha, base)
        # sem nome, com as medidas 3 % maiores: ainda é o W 310×38,7
        perto = base.replace(linha, "#22=IFCISHAPEPROFILEDEF(.AREA.,$,#21,169.95,319.3,"
                                    "5.974,9.991,$,$,$);")
        v1 = por_nome(importar_texto(perto))["V1"]
        self.assertIsInstance(v1, Barra)
        self.assertEqual(v1.perfil, "W 310×38,7")
        # 8 % maiores: nada casa, vira sólido e aparece no relatório
        longe = base.replace(linha, "#22=IFCISHAPEPROFILEDEF(.AREA.,$,#21,178.2,334.8,"
                                    "6.264,10.476,$,$,$);")
        doc = importar_texto(longe)
        self.assertIsInstance(por_nome(doc)["V1"], Solido)
        self.assertIn("V1", [s["elemento"] for s in
                             doc.metadados["importacao"]["sem_perfil_no_catalogo"]])

    def test_estrutural_desligado_so_gera_solidos(self):
        doc = importar(dado("estrutura_mm.ifc"), estrutural=False)
        self.assertEqual((len(doc.barras), len(doc.chapas), len(doc.solidos)), (0, 0, 7))

    def test_rotacao_reproduz_a_secao_do_arquivo(self):
        """A rotação importada, desenhada pela convenção do editor, dá o X do IFC."""
        for b in self.doc.barras:
            u, _v, _w = base_secao(b.direcao)
            x_ifc = b.atributos["eixos_ifc"]["x"]
            ang = math.radians(b.rotacao)
            _, v0, _ = base_secao(b.direcao)
            x = tuple(u[i] * math.cos(ang) + v0[i] * math.sin(ang) for i in range(3))
            self.assertPonto(x, x_ifc, 1e-9, b.nome)

    @unittest.skipIf(base_local is None, "nucleo3d.geometria indisponível")
    def test_convencao_igual_a_da_geometria(self):
        for d in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0.3), (0.1, 0, 1), (-1, 2, -3)):
            for a, b in zip(base_secao(d), base_local(d, 0.0)):
                self.assertPonto(a, b, 1e-12)

    def test_propriedades_material_e_guid(self):
        v1 = self.e["V1"]
        self.assertEqual(v1.atributos["propriedades"]["Pset_BeamCommon"],
                         {"Reference": "W 310x38,7", "Span": 6000.0, "IsExternal": False})
        self.assertEqual(v1.material, "Aco ASTM A572 Gr.50")
        self.assertIn("Aco ASTM A572 Gr.50", self.doc.materiais)
        self.assertEqual(v1.atributos["origem_ifc"], "3Ehr0Mmq95GgL6yKXVBB06")
        self.assertEqual(v1.atributos["tipo_ifc"], "IfcBeam")
        self.assertEqual(v1.tipo_ifc(), "IfcBeam")

    def test_inversos_acham_as_relacoes_do_elemento(self):
        arq = ler(dado("estrutura_mm.ifc"))
        tipos = {e.tipo for e in arq.inversos(48)}
        self.assertEqual(tipos, {"IFCRELCONTAINEDINSPATIALSTRUCTURE",
                                 "IFCRELASSOCIATESMATERIAL", "IFCRELDEFINESBYPROPERTIES"})

    def test_documento_serializa_em_json(self):
        texto = json.dumps(self.doc.dict(), ensure_ascii=False)
        volta = Documento.de_dict(json.loads(texto))
        self.assertEqual(len(volta.barras), 5)
        self.assertEqual(len(volta.chapas), 1)
        self.assertIn("importacao", volta.metadados)


#: IFC escrito à mão com cinco camadas de apresentação:
#:   Estrutura   com estilo, visível           <- V1 pela representação
#:   Fechamento  com estilo, LayerOn .F.       <- F1 pelo item da representação (oculta)
#:   Referência  com estilo, LayerBlocked .T.  <- E1 (bloqueada, visível)
#:   Congelada   LayerFrozen .T.               <- C1 (oculta: congelada não aparece)
#:   Camada Revit 01, sem estilo (como Revit e ArchiCAD gravam) <- X1
#: T1 não tem camada mas tem Pset_MetalicaCalculo.Camada = 'Terças'; S1 não tem nada
#: e fica no pavimento 'Nível 0'. V1 tem a mesma Pset, mas a camada de apresentação
#: vence. V1 e T1 têm MaterialAparencia = 'Aço galvanizado' e IfcMaterial de aço; F1
#: tem estilo de superfície próprio 'Telha azul'.
IFC_CAMADAS = r"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('camadas.ifc','2026-01-01T00:00:00',('teste'),('sistema'),'sistema','sistema','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#2=IFCUNITASSIGNMENT((#1));
#5=IFCCARTESIANPOINT((0.,0.,0.));
#6=IFCDIRECTION((0.,0.,1.));
#7=IFCDIRECTION((1.,0.,0.));
#8=IFCAXIS2PLACEMENT3D(#5,#6,#7);
#9=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#8,$);
#10=IFCPROJECT('3Ehr0Mmq95GgL6yKXVEB01',$,'Camadas',$,$,$,$,(#9),#2);
#11=IFCLOCALPLACEMENT($,#8);
#12=IFCBUILDINGSTOREY('3Ehr0Mmq95GgL6yKXVEB02',$,'N\X2\00ED\X0\vel 0',$,$,#11,$,$,.ELEMENT.,0.);
#13=IFCRELAGGREGATES('3Ehr0Mmq95GgL6yKXVEB03',$,$,$,#10,(#12));
#14=IFCCARTESIANPOINT((0.,0.));
#15=IFCAXIS2PLACEMENT2D(#14,$);
#16=IFCRECTANGLEPROFILEDEF(.AREA.,$,#15,100.,100.);
#17=IFCISHAPEPROFILEDEF(.AREA.,'W 310x38,7',#15,165.,310.,5.8,9.7,$,$,$);
#18=IFCLSHAPEPROFILEDEF(.AREA.,'L 40x4',#15,40.,40.,4.,$,$,$);
#20=IFCEXTRUDEDAREASOLID(#17,#8,#6,3000.);
#21=IFCSHAPEREPRESENTATION(#9,'Body','SweptSolid',(#20));
#22=IFCPRODUCTDEFINITIONSHAPE($,$,(#21));
#23=IFCBEAM('3Ehr0Mmq95GgL6yKXVEB04',$,'V1',$,'viga',#11,#22,$,.BEAM.);
#30=IFCEXTRUDEDAREASOLID(#16,#8,#6,10.);
#31=IFCSHAPEREPRESENTATION(#9,'Body','SweptSolid',(#30));
#32=IFCPRODUCTDEFINITIONSHAPE($,$,(#31));
#33=IFCCOVERING('3Ehr0Mmq95GgL6yKXVEB05',$,'F1',$,$,#11,#32,$,.ROOFING.);
#34=IFCCOLOURRGB($,0.4,0.6,0.8);
#35=IFCSURFACESTYLESHADING(#34,0.);
#36=IFCSURFACESTYLE('Telha azul',.BOTH.,(#35));
#37=IFCSTYLEDITEM(#30,(#36),$);
#40=IFCEXTRUDEDAREASOLID(#16,#8,#6,20.);
#41=IFCSHAPEREPRESENTATION(#9,'Body','SweptSolid',(#40));
#42=IFCPRODUCTDEFINITIONSHAPE($,$,(#41));
#43=IFCBUILDINGELEMENTPROXY('3Ehr0Mmq95GgL6yKXVEB06',$,'E1',$,$,#11,#42,$,$);
#50=IFCEXTRUDEDAREASOLID(#16,#8,#6,30.);
#51=IFCSHAPEREPRESENTATION(#9,'Body','SweptSolid',(#50));
#52=IFCPRODUCTDEFINITIONSHAPE($,$,(#51));
#53=IFCBUILDINGELEMENTPROXY('3Ehr0Mmq95GgL6yKXVEB07',$,'X1',$,$,#11,#52,$,$);
#60=IFCEXTRUDEDAREASOLID(#18,#8,#6,2000.);
#61=IFCSHAPEREPRESENTATION(#9,'Body','SweptSolid',(#60));
#62=IFCPRODUCTDEFINITIONSHAPE($,$,(#61));
#63=IFCMEMBER('3Ehr0Mmq95GgL6yKXVEB08',$,'T1',$,'contraventamento',#11,#62,$,.BRACE.);
#70=IFCEXTRUDEDAREASOLID(#16,#8,#6,40.);
#71=IFCSHAPEREPRESENTATION(#9,'Body','SweptSolid',(#70));
#72=IFCPRODUCTDEFINITIONSHAPE($,$,(#71));
#73=IFCBUILDINGELEMENTPROXY('3Ehr0Mmq95GgL6yKXVEB09',$,'S1',$,$,#11,#72,$,$);
#74=IFCEXTRUDEDAREASOLID(#16,#8,#6,50.);
#75=IFCSHAPEREPRESENTATION(#9,'Body','SweptSolid',(#74));
#76=IFCPRODUCTDEFINITIONSHAPE($,$,(#75));
#77=IFCBUILDINGELEMENTPROXY('3Ehr0Mmq95GgL6yKXVEB14',$,'C1',$,$,#11,#76,$,$);
#80=IFCCOLOURRGB($,0.2,0.4,0.6);
#81=IFCSURFACESTYLERENDERING(#80,0.,$,$,$,$,$,$,.FLAT.);
#82=IFCSURFACESTYLE('Estrutura',.BOTH.,(#81));
#83=IFCPRESENTATIONLAYERWITHSTYLE('Estrutura',$,(#21),$,.T.,.F.,.F.,(#82));
#84=IFCCOLOURRGB($,0.8,0.8,0.8);
#85=IFCSURFACESTYLESHADING(#84,0.);
#86=IFCSURFACESTYLE('Fechamento',.BOTH.,(#85));
#87=IFCPRESENTATIONLAYERWITHSTYLE('Fechamento',$,(#30),$,.F.,.F.,.F.,(#86));
#88=IFCCOLOURRGB($,1.,0.,0.);
#89=IFCSURFACESTYLESHADING(#88,0.);
#90=IFCSURFACESTYLE('Refer\X2\00EA\X0\ncia',.BOTH.,(#89));
#91=IFCPRESENTATIONLAYERWITHSTYLE('Refer\X2\00EA\X0\ncia',$,(#41),$,.T.,.F.,.T.,(#90));
#92=IFCPRESENTATIONLAYERASSIGNMENT('Camada Revit 01',$,(#51),$);
#93=IFCPRESENTATIONLAYERWITHSTYLE('Congelada',$,(#75),$,.T.,.T.,.F.,());
#100=IFCPROPERTYSINGLEVALUE('Camada',$,IFCLABEL('Ter\X2\00E7\X0\as'),$);
#101=IFCPROPERTYSINGLEVALUE('MaterialAparencia',$,IFCLABEL('A\X2\00E7\X0\o galvanizado'),$);
#102=IFCPROPERTYSINGLEVALUE('Aco',$,IFCLABEL('ASTM A572 Gr.50'),$);
#103=IFCPROPERTYSET('3Ehr0Mmq95GgL6yKXVEB10',$,'Pset_MetalicaCalculo',$,(#100,#101,#102));
#104=IFCRELDEFINESBYPROPERTIES('3Ehr0Mmq95GgL6yKXVEB11',$,$,$,(#23,#63),#103);
#105=IFCMATERIAL('ASTM A572 Gr.50',$,'Steel');
#106=IFCRELASSOCIATESMATERIAL('3Ehr0Mmq95GgL6yKXVEB12',$,$,$,(#23,#63),#105);
#107=IFCRELCONTAINEDINSPATIALSTRUCTURE('3Ehr0Mmq95GgL6yKXVEB13',$,$,$,
  (#23,#33,#43,#53,#63,#73,#77),#12);
ENDSEC;
END-ISO-10303-21;
"""


class TestCamadasEMateriaisDeAparencia(Asserts):

    @classmethod
    def setUpClass(cls):
        cls.doc = importar_texto(IFC_CAMADAS)
        cls.e = por_nome(cls.doc)
        cls.rel = cls.doc.metadados["importacao"]

    def test_atributos_de_cada_camada(self):
        c = self.doc.camadas
        self.assertEqual((c["Estrutura"].cor, c["Estrutura"].visivel,
                          c["Estrutura"].bloqueada), ("#336699", True, False))
        self.assertEqual((c["Fechamento"].cor, c["Fechamento"].visivel,
                          c["Fechamento"].bloqueada), ("#cccccc", False, False))
        self.assertEqual((c["Referência"].cor, c["Referência"].visivel,
                          c["Referência"].bloqueada), ("#ff0000", True, True))
        self.assertEqual((c["Congelada"].visivel, c["Congelada"].bloqueada), (False, False))
        self.assertTrue(c["Camada Revit 01"].visivel)
        self.assertFalse(c["Camada Revit 01"].bloqueada)
        self.assertEqual(len(self.rel["camadas_ifc"]), 5)

    def test_camada_de_cada_peca_com_a_precedencia_certa(self):
        camada = {n: e.camada for n, e in self.e.items()}
        self.assertEqual(camada, {"V1": "Estrutura",           # apresentação vence a Pset
                                  "F1": "Fechamento",          # atribuída pelo item
                                  "E1": "Referência", "X1": "Camada Revit 01",
                                  "C1": "Congelada",
                                  "T1": "Terças",              # Pset_MetalicaCalculo
                                  "S1": "Nível 0"})            # pavimento
        self.assertEqual(self.rel["origem_camada"],
                         {"apresentacao": 5, "pavimento": 1, "pset": 1})

    def test_material_de_aparencia_separado_do_aco(self):
        for nome in ("V1", "T1"):
            b = self.e[nome]
            self.assertIsInstance(b, Barra)
            self.assertEqual((b.material, b.aco), ("Aço galvanizado", "ASTM A572 Gr.50"))
        self.assertNotIn("ASTM A572 Gr.50", self.doc.materiais)
        self.assertEqual(self.e["T1"].papel, "contraventamento")

    def test_estilo_de_superficie_vira_material_de_aparencia(self):
        f1 = self.e["F1"]
        self.assertEqual(f1.material, "Telha azul")
        self.assertEqual(self.doc.materiais["Telha azul"].cor, "#6699cc")

    def test_aco_do_catalogo_sem_aparencia_vira_material_aco(self):
        texto = IFC_CAMADAS.replace("(#100,#101,#102)", "(#102)")
        v1 = por_nome(importar_texto(texto))["V1"]
        self.assertEqual((v1.material, v1.aco), ("Aço", "ASTM A572 Gr.50"))

    def test_inspecionar_lista_as_camadas(self):
        caminho = os.path.join(tempfile.mkdtemp(prefix="ifc_camadas_"), "camadas.ifc")
        with open(caminho, "w", encoding="ascii") as f:
            f.write(IFC_CAMADAS)
        nomes = [c["nome"] for c in inspecionar(caminho)["camadas"]]
        self.assertEqual(sorted(nomes),
                         ["Camada Revit 01", "Congelada", "Estrutura", "Fechamento",
                          "Referência"])


def _exportador_grava_camadas() -> bool:
    """O exportador ainda está passando a gravar camadas; até lá, a ida e volta de
    camadas pelo exportador fica pulada (e diz por quê)."""
    if para_texto is None:
        return False
    doc = Documento(nome="sonda")
    doc.add(Barra(nome="B", inicio=(0, 0, 0), fim=(0, 0, 1000), perfil="W 310×38,7",
                  papel="pilar", camada="Estrutura"))
    try:
        return "IFCPRESENTATIONLAYER" in para_texto(doc)
    except Exception:
        return False


class TestCamadasIdaEVolta(Asserts):
    """Documento com três camadas (uma oculta, uma bloqueada) pelo exportador."""

    @classmethod
    def setUpClass(cls):
        if not _exportador_grava_camadas():
            raise unittest.SkipTest("ifc/exportar.py ainda não grava "
                                    "IfcPresentationLayerAssignment")
        doc = Documento(nome="Três camadas")
        doc.camadas["Estrutura"].cor = "#123456"
        doc.camadas["Fechamento"].visivel = False
        doc.camadas["Referência"].bloqueada = True
        doc.add(Barra(nome="P1", inicio=(0, 0, 0), fim=(0, 0, 6000), perfil="W 310×38,7",
                      papel="pilar", camada="Estrutura", material="Aço galvanizado"))
        doc.add(Chapa(nome="CB1", origem=(0, 0, 0), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0),
                      contorno=[(-175, -175), (175, -175), (175, 175), (-175, 175)],
                      espessura=19.0, camada="Referência", material="Aço"))
        v = [(x, y, z) for z in (0, 10) for y in (0, 1000) for x in (0, 1000)]
        doc.add(Solido(nome="Telha", vertices=v, camada="Fechamento", material="Telha",
                       faces=[[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4],
                              [1, 3, 7, 5], [3, 2, 6, 7], [2, 0, 4, 6]]))
        cls.original = doc
        cls.volta = importar_texto(para_texto(doc))

    def test_camadas_preservadas(self):
        for nome in ("Estrutura", "Fechamento", "Referência"):
            a, b = self.original.camadas[nome], self.volta.camadas[nome]
            self.assertEqual((b.cor, b.visivel, b.bloqueada),
                             (a.cor, a.visivel, a.bloqueada), nome)

    def test_camada_e_material_de_cada_peca(self):
        volta = por_nome(self.volta)
        for e in self.original.entidades.values():
            self.assertEqual(volta[e.nome].camada, e.camada, e.nome)
            self.assertEqual(volta[e.nome].material, e.material, e.nome)


@unittest.skipIf(base_local is None, "nucleo3d.geometria indisponível")
class TestBarraDeSecaoCheia(Asserts):
    """IfcCircleProfileDef e IfcRectangleProfileDef em viga/pilar/membro viram barra
    redonda e barra chata sintéticas de `geometria`, e não sólido morto."""

    LINHA_TUBO = "#23=IFCCIRCLEHOLLOWPROFILEDEF(.AREA.,'TR 33,7x2,65',#21,16.85,2.65);"
    LINHA_W = "#22=IFCISHAPEPROFILEDEF(.AREA.,'W 310x38,7',#21,165.,310.,5.8,9.7,11.,$,$);"

    def _trocar(self, linha, nova, **opcoes):
        base = texto_de("estrutura_mm.ifc")
        self.assertIn(linha, base)
        return importar_texto(base.replace(linha, nova), **opcoes)

    def test_circulo_cheio_vira_barra_redonda(self):
        doc = self._trocar(self.LINHA_TUBO, "#23=IFCCIRCLEPROFILEDEF(.AREA.,$,#21,8.);")
        t1 = por_nome(doc)["T1"]
        self.assertIsInstance(t1, Barra)
        self.assertEqual(t1.perfil, "Barra redonda ø 16 mm")
        self.assertEqual(t1.papel, "terça")                     # .PURLIN.
        self.assertPonto(t1.fim, (6000, 3000, 6000), 1e-6)

    def test_diametro_comercial_em_polegada(self):
        for raio, nome in ((6.35, "Barra redonda ø 12.7 mm"),
                           (15.875, "Barra redonda ø 31.75 mm"),
                           (9.93, "Barra redonda ø 20 mm")):
            doc = self._trocar(self.LINHA_TUBO,
                               "#23=IFCCIRCLEPROFILEDEF(.AREA.,$,#21,%r);" % raio)
            self.assertEqual(por_nome(doc)["T1"].perfil, nome)

    def test_nome_declarado_aceito_pela_geometria_prevalece(self):
        doc = self._trocar(self.LINHA_TUBO,
                           "#23=IFCCIRCLEPROFILEDEF(.AREA.,'Barra \\X2\\00F8\\X0\\ 16 mm',"
                           "#21,8.);")
        self.assertEqual(por_nome(doc)["T1"].perfil, "Barra ø 16 mm")

    def test_retangulo_cheio_vira_barra_chata(self):
        doc = self._trocar(self.LINHA_W,
                           "#22=IFCRECTANGLEPROFILEDEF(.AREA.,$,#21,12.7,101.6);")
        v1 = por_nome(doc)["V1"]
        self.assertIsInstance(v1, Barra)
        self.assertEqual(v1.perfil, "Barra chata 101.6 × 12.7 mm")
        self.assertEqual(v1.papel, "viga")
        # a largura está no Y do perfil IFC: a rotação leva o x da seção até ela
        u, v, _ = base_local(v1.direcao, v1.rotacao)
        self.assertPonto(u, v1.atributos["eixos_ifc"]["y"], 1e-9)

    def test_secao_cheia_grande_ou_de_concreto_fica_solido_com_motivo(self):
        grande = self._trocar(self.LINHA_W,
                              "#22=IFCRECTANGLEPROFILEDEF(.AREA.,$,#21,200.,500.);")
        self.assertIsInstance(por_nome(grande)["V1"], Solido)
        motivos = {b["elemento"]: b["motivo"]
                   for b in grande.metadados["importacao"]["barras_como_solido"]}
        self.assertIn("espesso demais para barra chata", motivos["V1"])
        concreto = importar_texto(texto_de("estrutura_mm.ifc")
                                  .replace(self.LINHA_TUBO,
                                           "#23=IFCCIRCLEPROFILEDEF(.AREA.,$,#21,8.);")
                                  .replace("'Aco ASTM A572 Gr.50'", "'Concreto C30'"))
        self.assertIsInstance(por_nome(concreto)["T1"], Solido)

    def test_toda_barra_que_cai_para_solido_tem_motivo(self):
        rel = importar(dado("estrutura_mm.ifc")).metadados["importacao"]
        self.assertEqual([b["elemento"] for b in rel["barras_como_solido"]], ["VS1"])
        self.assertIn("sem correspondente no catálogo", rel["barras_como_solido"][0]["motivo"])
        self.assertTrue(any("barras_como_solido" in a for a in rel["avisos"]))


@unittest.skipIf(para_texto is None, "ifc/exportar.py indisponível")
class TestGalpaoCapitulo16(Asserts):
    """Ida e volta do galpão real do Capítulo 16, gerado por `de_projeto` a partir do
    dimensionamento: todas as barras voltam barra e todas as chapas voltam chapa."""

    @classmethod
    def setUpClass(cls):
        try:
            from nucleo.galpao import dimensionar
            from nucleo.modelo_galpao import DadosGalpao
            from nucleo3d import de_projeto
        except Exception as erro:                                      # pragma: no cover
            raise unittest.SkipTest("de_projeto indisponível: %s" % erro)
        dados = DadosGalpao(nome="Galpão do Capítulo 16", vao=20.0, comprimento=40.0,
                            pe_direito=6.0, espacamento_porticos=5.0, inclinacao=10.0,
                            v0=40.0, categoria_rugosidade="II", classe="B",
                            telha="trapezoidal 0,50 mm", sobrecarga_cobertura=0.25)
        cls.original = de_projeto.modelo_do_galpao(dimensionar(dados))
        inicio = time.time()
        cls.texto = para_texto(cls.original)
        cls.volta = importar_texto(cls.texto)
        cls.tempo = time.time() - inicio
        cls.rel = cls.volta.metadados["importacao"]

    def test_mesmas_contagens_por_camada(self):
        if "IFCPRESENTATIONLAYER" not in self.texto:
            self.skipTest("ifc/exportar.py ainda não grava IfcPresentationLayerAssignment")
        from collections import Counter
        ida = Counter(e.camada for e in self.original.entidades.values())
        volta = Counter(e.camada for e in self.volta.entidades.values())
        self.assertEqual(volta, ida)
        for nome in ida:
            a, b = self.original.camadas[nome], self.volta.camadas[nome]
            self.assertEqual((b.visivel, b.bloqueada, b.cor),
                             (a.visivel, a.bloqueada, a.cor), nome)

    def test_contagens(self):
        self.assertEqual(len(self.volta.barras), len(self.original.barras))
        self.assertEqual(len(self.volta.chapas), len(self.original.chapas))
        self.assertEqual(len(self.volta.solidos), len(self.original.solidos))
        self.assertEqual(self.rel["barras_como_solido"], [])

    def test_mesmo_perfil_e_mesmo_papel(self):
        from collections import Counter
        ida = Counter((b.perfil, b.papel) for b in self.original.barras)
        volta = Counter((b.perfil, b.papel) for b in self.volta.barras)
        self.assertEqual(volta, ida)

    def test_cada_barra_volta_no_lugar(self):
        restantes = list(self.volta.barras)
        for b in self.original.barras:
            achou = None
            for r in restantes:
                if r.perfil == b.perfil and math.dist(r.inicio, b.inicio) <= 1.0 \
                        and math.dist(r.fim, b.fim) <= 1.0:
                    achou = r
                    break
            self.assertIsNotNone(achou, "%s (%s) não voltou no lugar" % (b.nome, b.perfil))
            restantes.remove(achou)

    def test_correntes_e_contraventamentos_redondos(self):
        redondas = [b for b in self.volta.barras if "ø" in b.perfil]
        self.assertEqual(len(redondas),
                         len([b for b in self.original.barras if "ø" in b.perfil]))
        self.assertGreater(len(redondas), 0)

    def test_rapido(self):
        self.assertLess(self.tempo, 15.0)


class TestChapa(Asserts):

    def test_chapa_de_perfil_retangular(self):
        ch = por_nome(importar(dado("estrutura_mm.ifc")))["CH1"]
        self.assertIsInstance(ch, Chapa)
        self.assertAlmostEqual(ch.espessura, 12.7)
        self.assertAlmostEqual(ch.area, 200 * 300)
        self.assertFalse(ch.centrada)                # colocação na face inferior
        self.assertPonto(ch.origem, (0, 0, 6000), 1e-6)
        self.assertPonto(ch.normal, (0, 0, 1), 1e-12)
        self.assertEqual(caixa([(x, y, 0) for x, y in ch.contorno]),
                         ((-100.0, -150.0, 0), (100.0, 150.0, 0)))

    def test_vazio_nao_circular_mantem_solido(self):
        texto = texto_de("geometrias_mm.ifc").replace(
            "#84=IFCSLAB('3Ehr0Mmq95GgL6yKXVCB08',$,'G5',$,$,#11,#83,$,.FLOOR.);",
            "#84=IFCPLATE('3Ehr0Mmq95GgL6yKXVCB08',$,'G5',$,$,#11,#83,$,.SHEET.);")
        doc = importar_texto(texto)
        g5 = por_nome(doc)["G5"]
        self.assertIsInstance(g5, Solido)
        self.assertTrue(any("não circular" in a
                            for a in doc.metadados["importacao"]["avisos"]))


# =================================================================== ida e volta

@unittest.skipIf(para_texto is None, "ifc/exportar.py indisponível")
class TestIdaEVolta(Asserts):

    @classmethod
    def setUpClass(cls):
        doc = Documento(nome="Ida e volta")
        doc.add(Barra(nome="V0", inicio=(0, 0, 6000), fim=(6000, 0, 6000),
                      perfil="W 310×38,7", papel="viga"))
        doc.add(Barra(nome="V90", inicio=(0, 2000, 6000), fim=(0, 8000, 7000),
                      perfil="W 200×19,3", papel="viga", rotacao=90))
        doc.add(Barra(nome="P1", inicio=(0, 0, 0), fim=(0, 0, 6000),
                      perfil="W 310×38,7", papel="pilar"))
        doc.add(Barra(nome="T1", inicio=(0, 3000, 6500), fim=(6000, 3000, 6500),
                      perfil=UE, papel="terça", aco="ZAR-345", camada="Terças"))
        doc.add(Barra(nome="CV1", inicio=(0, 0, 0), fim=(6000, 0, 6000), perfil=TUBO,
                      papel="contraventamento", camada="Contraventamento"))
        doc.add(Chapa(nome="CB1", origem=(100, 200, 0), eixo_x=(1, 0, 0),
                      eixo_y=(0, 1, 0), espessura=19.0, aco="ASTM A36",
                      contorno=[(-175, -175), (175, -175), (175, 175), (-175, 175)],
                      furos=[{"x": sx * 120, "y": sy * 120, "diametro": 26.0}
                             for sx in (-1, 1) for sy in (-1, 1)]))
        doc.add(Chapa(nome="CT1", origem=(0, 0, 6000), eixo_x=(1, 0, 0),
                      eixo_y=(0, 0, 1), centrada=False, espessura=16,
                      contorno=[(0, 0), (214, 0), (214, 760), (0, 760)]))
        lado = 1000.0
        v = [(x, y, z) for z in (0, lado) for y in (0, lado) for x in (0, lado)]
        v = [(10000 + x, y, z) for x, y, z in v]
        doc.add(Solido(nome="Base", vertices=v, camada="Fechamento",
                       faces=[[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4],
                              [1, 3, 7, 5], [3, 2, 6, 7], [2, 0, 4, 6]],
                       atributos={"tipo_ifc": "IfcFooting"}))
        cls.original = doc
        inicio = time.time()
        cls.texto = para_texto(doc)
        cls.volta = importar_texto(cls.texto)
        cls.tempo = time.time() - inicio
        cls.o, cls.v = por_nome(doc), por_nome(cls.volta)

    def test_contagem_por_tipo(self):
        self.assertEqual(sorted(self.v), sorted(self.o))
        for nome, ent in self.o.items():
            self.assertIs(type(self.v[nome]), type(ent), nome)
        self.assertEqual(self.volta.metadados["importacao"]["avisos"], [])

    def test_barras_voltam_no_lugar_com_o_mesmo_perfil(self):
        for b in self.original.barras:
            r = self.v[b.nome]
            self.assertPonto(r.inicio, b.inicio, 1.0, b.nome)
            self.assertPonto(r.fim, b.fim, 1.0, b.nome)
            self.assertEqual(r.perfil, b.perfil)
            self.assertEqual(r.papel, b.papel)
            self.assertEqual(r.aco, b.aco)

    def test_rotacao_das_barras_horizontais_e_inclinadas(self):
        for nome in ("V0", "V90", "T1", "CV1"):
            diferenca = (self.v[nome].rotacao - self.o[nome].rotacao) % 360
            self.assertAlmostEqual(min(diferenca, 360 - diferenca), 0.0, places=6, msg=nome)

    def test_chapas_voltam_como_chapas(self):
        for c in self.original.chapas:
            r = self.v[c.nome]
            self.assertIsInstance(r, Chapa)
            self.assertPonto(r.origem, c.origem, 1.0)
            self.assertPonto(r.eixo_x, c.eixo_x, 1e-9)
            self.assertPonto(r.eixo_y, c.eixo_y, 1e-9)
            self.assertAlmostEqual(r.espessura, c.espessura, places=6)
            self.assertEqual(r.centrada, c.centrada)
            self.assertAlmostEqual(r.area, c.area, delta=1e-3)
            self.assertEqual(r.aco, c.aco)
            self.assertEqual(len(r.contorno), len(c.contorno))
            self.assertEqual(sorted((round(f["x"], 3), round(f["y"], 3), f["diametro"])
                                    for f in r.furos),
                             sorted((float(f["x"]), float(f["y"]), f["diametro"])
                                    for f in c.furos))

    def test_solido_volta_com_volume_e_tipo(self):
        r = self.v["Base"]
        self.assertIsInstance(r, Solido)
        self.assertRelativo(r.volume, 1e9, 1e-9)
        self.assertEqual(r.tipo_ifc(), "IfcFooting")
        self.assertPonto(caixa(r.vertices)[0], (10000, 0, 0), 1.0)

    def test_rapido(self):
        self.assertLess(self.tempo, 5.0)


@unittest.skipIf(exportar is None, "ifc/exportar.py indisponível")
class TestGalpaoSintetico(Asserts):
    """Galpão de 8 pórticos gerado pelo exportador: dezenas de barras e chapas."""

    @classmethod
    def setUpClass(cls):
        doc = Documento(nome="Galpão sintético")
        vao, passo, pe, flecha, n = 20000.0, 5000.0, 6000.0, 2000.0, 8
        for i in range(n):
            x = i * passo
            for lado, y in (("A", 0.0), ("B", vao)):
                doc.add(Barra(nome=f"P{i}{lado}", inicio=(x, y, 0), fim=(x, y, pe),
                              perfil="W 310×38,7", papel="pilar"))
                doc.add(Chapa(nome=f"CB{i}{lado}", origem=(x, y, 0), eixo_x=(1, 0, 0),
                              eixo_y=(0, 1, 0), camada="Chapas", espessura=19.0,
                              centrada=False,
                              contorno=[(-175, -175), (175, -175), (175, 175),
                                        (-175, 175)],
                              furos=[{"x": sx * 120, "y": sy * 120, "diametro": 26.0}
                                     for sx in (-1, 1) for sy in (-1, 1)]))
            doc.add(Barra(nome=f"V{i}A", inicio=(x, 0, pe), fim=(x, vao / 2, pe + flecha),
                          perfil="W 200×19,3", papel="viga"))
            doc.add(Barra(nome=f"V{i}B", inicio=(x, vao / 2, pe + flecha), fim=(x, vao, pe),
                          perfil="W 200×19,3", papel="viga"))
        for j in range(7):
            t = j / 6
            for y in (t * vao / 2, vao - t * vao / 2):
                for i in range(n - 1):
                    doc.add(Barra(nome=f"T{j}-{y:.0f}-{i}", inicio=(i * passo, y, pe + t * flecha),
                                  fim=((i + 1) * passo, y, pe + t * flecha), perfil=UE,
                                  papel="terça", camada="Terças", aco="ZAR-345"))
        for y in (0.0, vao):
            doc.add(Barra(nome=f"CV-{y:.0f}", inicio=(0, y, 0), fim=(passo, y, pe),
                          perfil=TUBO, papel="contraventamento"))
        cls.original = doc
        pasta = tempfile.mkdtemp(prefix="ifc_galpao_")
        cls.caminho = exportar(doc, os.path.join(pasta, "galpao_sintetico.ifc"))
        inicio = time.time()
        cls.volta = importar(cls.caminho)
        cls.tempo = time.time() - inicio

    def test_tem_dezenas_de_elementos(self):
        self.assertGreater(len(self.original.entidades), 100)

    def test_importa_em_menos_de_15_segundos(self):
        self.assertLess(self.tempo, 15.0)

    def test_tudo_volta_com_o_tipo_certo(self):
        rel = self.volta.metadados["importacao"]
        self.assertEqual(rel["barras"], len(self.original.barras))
        self.assertEqual(rel["chapas"], len(self.original.chapas))
        self.assertEqual(rel["solidos"], 0)
        self.assertEqual(rel["nao_suportados"], {})
        self.assertEqual(rel["avisos"], [])

    def test_posicoes_dentro_de_1_mm(self):
        volta = por_nome(self.volta)
        for b in self.original.barras:
            r = volta[b.nome]
            self.assertPonto(r.inicio, b.inicio, 1.0, b.nome)
            self.assertPonto(r.fim, b.fim, 1.0, b.nome)
            self.assertEqual(r.perfil, b.perfil, b.nome)

    def test_inspecionar_sem_geometria(self):
        info = inspecionar(self.caminho)
        self.assertEqual(info["schema"], "IFC4")
        self.assertEqual(info["total_elementos"], len(self.original.entidades))
        self.assertEqual(info["escala_para_mm"], 1.0)


# =================================================================== robustez e prévia

class TestRobustez(Asserts):
    """`truncado.ifc`: referência pendurada, tipo desconhecido, instrução malformada e
    fim de arquivo no meio de uma entidade."""

    @classmethod
    def setUpClass(cls):
        cls.doc = importar(dado("truncado.ifc"))
        cls.rel = cls.doc.metadados["importacao"]
        cls.avisos = "\n".join(cls.rel["avisos"])

    def test_nao_derruba_e_aproveita_o_que_da(self):
        self.assertEqual(sorted(por_nome(self.doc)), ["R1", "R3", "R4"])
        self.assertRelativo(por_nome(self.doc)["R1"].volume, 100 * 200 * 300, 1e-9)

    def test_truncamento_detectado(self):
        self.assertTrue(self.rel["truncado"])
        self.assertIn("arquivo truncado", self.avisos)

    def test_referencia_inexistente_vira_aviso(self):
        self.assertIn("#999", self.avisos)
        self.assertIn("#998", self.avisos)
        self.assertIn("R2", self.avisos)

    def test_tipo_desconhecido_vira_caixa_com_aviso(self):
        r4 = por_nome(self.doc)["R4"]
        self.assertPonto(caixa(r4.vertices)[1], (500, 250, 125), 1e-6)
        self.assertEqual(self.rel["nao_suportados"], {"IFCSOLIDOFUTURO": 1})

    def test_leitor_guarda_tipo_desconhecido_e_pula_instrucao_malformada(self):
        arq = ler(dado("truncado.ifc"))
        self.assertEqual(arq.entidades[60].tipo, "IFCENTIDADEQUENINGUEMCONHECE")
        self.assertNotIn(61, arq.entidades)
        self.assertNotIn(80, arq.entidades)
        self.assertTrue(any("#61" in a for a in arq.avisos))

    def test_texto_que_nao_e_ifc(self):
        for texto in ("", "isto não é um arquivo STEP", "ISO-10303-21;\nDATA;\n#1=IFCX(",
                      "DATA;\n#1=IFCBEAM('a',$,'x',$,$,#77,#88,$,$);\nENDSEC;"):
            doc = importar_texto(texto)
            self.assertIsInstance(doc, Documento)
            self.assertEqual(len(doc.entidades), 0)

    def test_ciclo_de_placement_nao_trava(self):
        texto = texto_de("caixa_metro.ifc").replace(
            "#11=IFCLOCALPLACEMENT($,#8);", "#11=IFCLOCALPLACEMENT(#23,#8);")
        doc = importar_texto(texto)
        self.assertEqual(len(doc.solidos), 1)


class TestInspecionar(Asserts):

    def test_previa_do_portico(self):
        info = inspecionar(dado("estrutura_mm.ifc"))
        self.assertEqual(info["schema"], "IFC4")
        self.assertEqual(info["unidade_origem"], "milímetro")
        self.assertEqual(info["escala_para_mm"], 1.0)
        self.assertEqual(info["elementos"],
                         {"IfcBeam": 2, "IfcColumn": 1, "IfcMember": 3, "IfcPlate": 1})
        self.assertEqual(info["total_elementos"], 7)
        projeto = info["hierarquia"][0]
        self.assertEqual(projeto["tipo"], "IfcProject")
        terreno = projeto["filhos"][0]
        predio = terreno["filhos"][0]
        pavimento = predio["filhos"][0]
        self.assertEqual([terreno["tipo"], predio["tipo"], pavimento["tipo"]],
                         ["IfcSite", "IfcBuilding", "IfcBuildingStorey"])
        self.assertEqual((pavimento["nome"], pavimento["elementos"]), ("Estrutura", 7))

    def test_elevacao_do_pavimento_em_milimetro(self):
        info = inspecionar(dado("caixa_metro.ifc"))
        pav = info["hierarquia"][0]["filhos"][0]["filhos"][0]["filhos"][0]
        self.assertEqual(pav["elevacao_mm"], 3000.0)
        self.assertEqual(info["contagem_por_tipo"]["IfcBuildingElementProxy"], 1)

    def test_previa_de_arquivo_truncado(self):
        info = inspecionar(dado("truncado.ifc"))
        self.assertTrue(info["truncado"])
        self.assertEqual(info["total_elementos"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ---------------------------------------------------- camadas por tipo e marcas

def test_camada_semantica_para_arquivo_sem_camadas():
    from ifc.importar import camada_semantica, CAMADAS_SEMANTICAS
    # o TecnoMETAL grava telha como viga ou pilar e parafuso como proxy: o nome manda
    assert camada_semantica("IFCBEAM", "TELHA TP40 0.50MM") == "Telhas"
    assert camada_semantica("IFCCOLUMN", "TELHA TP40 0.50MM") == "Telhas"
    assert camada_semantica("IFCBUILDINGELEMENTPROXY", "BOLT (A) 12x35") == "Parafusos"
    assert camada_semantica("IFCMECHANICALFASTENER", "") == "Parafusos"
    assert camada_semantica("IFCPLATE", "PLATE 130x50x3") == "Chapas"
    assert camada_semantica("IFCBEAM", "FE RED 3/8''") == "Tirantes"
    assert camada_semantica("IFCCOLUMN", "U100X60X3.04") == "Pilares"
    assert camada_semantica("IFCBEAM", "U150X50X2.28") == "Vigas"
    assert camada_semantica("IFCMEMBER", "L 2 1/2'' X 1/4''") == "Barras"
    assert camada_semantica("IFCWALL", "Parede") == ""          # cai no pavimento
    for nome in ("Telhas", "Chapas", "Parafusos", "Tirantes", "Pilares", "Vigas", "Barras"):
        assert nome in CAMADAS_SEMANTICAS


def test_marcas_de_pset_e_descricao():
    from ifc.importar import marcas_de
    pset = {"Steel & Graphics Common": {"Part Mark": "P93", "Assembly Mark": "M86",
                                        "Grade": "CIVIL 300", "Profile": "U92X40X2.25"}}
    m = marcas_de("U92X40X2.25", "Mark:M86 Pos:P93 Material:CIVIL 300", pset)
    assert m == {"posicao": "P93", "conjunto": "M86", "perfil": "U92X40X2.25"}, m
    # sem pset, a descrição do TecnoMETAL ainda dá conjunto e posição
    m = marcas_de("PLATE 132x43x3", "Mark:M86 Pos:P76 Material:CIVIL 300", {})
    assert m == {"posicao": "P76", "conjunto": "M86", "perfil": "PLATE 132x43x3"}, m
    # parafuso do TecnoMETAL: "Mark: Pos:" vazio não pode virar conjunto "Pos"
    m = marcas_de("BOLT (A) 12x35", "Mark: Pos:", {})
    assert m == {"perfil": "BOLT (A) 12x35"}, m
    # Tekla
    m = marcas_de("HEA200", "", {"Tekla Common": {"PART_POS": "p12", "ASSEMBLY_POS": "A3"}})
    assert m["posicao"] == "p12" and m["conjunto"] == "A3" and m["perfil"] == "HEA200"
    assert marcas_de("", "", {}) == {}


# ------------------------------------------------- coordenadas de obra → origem

def test_modelo_longe_da_origem_vem_para_a_origem_e_a_exportacao_devolve():
    """Um IFC com a peça a 200 m da origem entra com o canto em (0, 0), guarda o
    deslocamento, e a ida e volta pelo exportador mantém tudo estável."""
    import tempfile
    from ifc import exportar as exp
    from ifc.importar import importar
    from nucleo3d.modelo import Documento, Barra
    doc = Documento(nome="Longe")
    doc.add(Barra(nome="V1", inicio=(210000.0, 66000.0, 4500.0), fim=(217000.0, 66000.0, 4500.0),
                  perfil="W 310×38,7", papel="viga"))
    doc.add(Barra(nome="P1", inicio=(210000.0, 66000.0, 0.0), fim=(210000.0, 66000.0, 4500.0),
                  perfil="W 310×38,7", papel="pilar"))
    with tempfile.TemporaryDirectory() as pasta:
        caminho = exp.exportar(doc, os.path.join(pasta, "longe.ifc"))
        volta = importar(caminho)
        (x0, y0, z0), (x1, y1, z1) = volta.caixa()
        assert abs(x0) < 1.0 and abs(y0) < 1.0, (x0, y0)          # canto em (0, 0)
        assert abs(z0) < 1.0 and abs(z1 - 4500) < 1.0             # cota preservada
        assert abs(x1 - 7000) < 1.0
        d = volta.metadados.get("deslocamento_mm")
        assert d and abs(d[0] - 210000) < 1.0 and abs(d[1] - 66000) < 1.0, d
        assert any("origem" in a for a in volta.metadados["importacao"]["avisos"])
        # exporta de novo: o sítio carrega o deslocamento e a peça volta ao lugar de obra
        caminho2 = exp.exportar(volta, os.path.join(pasta, "longe2.ifc"))
        texto = open(caminho2, encoding="utf-8").read()
        assert "210000." in texto and "66000." in texto
        de_novo = importar(caminho2)
        (x0, y0, _), _ = de_novo.caixa()
        assert abs(x0) < 1.0 and abs(y0) < 1.0
        d2 = de_novo.metadados.get("deslocamento_mm")
        assert d2 and abs(d2[0] - 210000) < 1.0 and abs(d2[1] - 66000) < 1.0, d2


def test_modelo_perto_da_origem_nao_e_mexido():
    from ifc.importar import importar
    doc = importar(os.path.join(DADOS, "estrutura_mm.ifc"))
    assert "deslocamento_mm" not in doc.metadados


def test_pilar_pela_geometria():
    """Montante curto e diagonal deitada não são pilares; a coluna de 3 m em pé é."""
    from ifc.importar import pilar_pela_geometria
    caixa = lambda dx, dy, dz: [(x, y, z) for x in (0, dx) for y in (0, dy) for z in (0, dz)]
    assert pilar_pela_geometria(caixa(150, 150, 3000))
    assert not pilar_pela_geometria(caixa(88, 40, 700))          # montante
    assert not pilar_pela_geometria(caixa(2500, 40, 800))        # diagonal deitada


def test_funilaria_rufos_e_calhas_na_camada_propria():
    """Rufo, calha e cumeeira de funilaria (o TecnoMETAL grava como IfcBeam com o nome do
    perfil) vão para as camadas Rufos e Calhas; a cumeeira de telha continua telha."""
    from ifc.importar import camada_semantica, funilaria, CAMADAS_SEMANTICAS
    assert camada_semantica("IFCBEAM", "RUFO CHAPEU 1") == "Rufos"
    assert camada_semantica("IFCBEAM", "CUMEEIRA I7.5") == "Rufos"
    assert camada_semantica("IFCBEAM", "CONTRARRUFO 2") == "Rufos"
    assert camada_semantica("IFCCOLUMN", "PINGADEIRA 1") == "Rufos"
    assert camada_semantica("IFCBEAM", "CALHA 1") == "Calhas"
    assert camada_semantica("IFCBEAM", "TELHA TP40 CUMEEIRA") == "Telhas"
    assert camada_semantica("IFCBEAM", "CUMEEIRA TP40") == "Telhas"
    assert camada_semantica("IFCBEAM", "VIGA CUMEEIRA") == "Vigas"
    assert funilaria("U150X50X2.28") == "" and funilaria("") == ""
    assert "Rufos" in CAMADAS_SEMANTICAS and "Calhas" in CAMADAS_SEMANTICAS


def test_migracao_das_camadas_de_funilaria_roda_uma_vez():
    """Modelo importado antes da 0.8.24: os rufos saem de Vigas, as camadas nascem, e a
    migração não roda de novo (o usuário que mover um rufo de volta manda)."""
    from ifc.importar import migrar_camadas_de_funilaria
    d = {"camadas": {"Vigas": {"nome": "Vigas", "cor": "#0b3d91", "visivel": True, "bloqueada": False}},
         "entidades": [
             {"id": "a", "tipo": "solido", "nome": "RUFO CHAPEU 1", "camada": "Vigas", "atributos": {"marcas": {"perfil": "RUFO CHAPEU 1"}}},
             {"id": "b", "tipo": "solido", "nome": "CALHA 1", "camada": "Vigas", "atributos": {}},
             {"id": "c", "tipo": "solido", "nome": "U150X50X2.28", "camada": "Vigas", "atributos": {}},
             {"id": "d", "tipo": "solido", "nome": "RUFO CHAPEU 2", "camada": "Minha camada", "atributos": {}},
         ]}
    assert migrar_camadas_de_funilaria(d) == 2
    cam = {e["id"]: e["camada"] for e in d["entidades"]}
    assert cam == {"a": "Rufos", "b": "Calhas", "c": "Vigas", "d": "Minha camada"}
    assert set(d["camadas"]) == {"Vigas", "Rufos", "Calhas"} and d["metadados"]["camadas_funilaria"]
    d["entidades"][0]["camada"] = "Vigas"
    assert migrar_camadas_de_funilaria(d) == 0 and d["entidades"][0]["camada"] == "Vigas"
    # e o Documento lê as camadas novas
    from nucleo3d.modelo import Documento
    doc = Documento.de_dict(dict(d, entidades=[]))
    assert doc.camadas["Rufos"].cor == "#17b8c9"
