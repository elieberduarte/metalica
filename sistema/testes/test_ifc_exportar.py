# -*- coding: utf-8 -*-
"""Testes da exportação IFC4 (`ifc/exportar.py`).

O que um teste de IFC precisa provar, em ordem de importância:

1. **Integridade referencial.** Toda referência `#n` citada existe. Um arquivo com
   referência pendurada é o que faz o BIMcollab, o Solibri e o FreeCAD recusarem o
   modelo sem explicar o motivo, e é o defeito mais fácil de introduzir sem perceber.
2. **Sintaxe da parte 21.** Cabeçalho, `DATA;`, uma entidade por linha na forma
   `#n= IFCXXX(...);`, `ENDSEC;` e `END-ISO-10303-21;`.
3. **GlobalId.** 22 caracteres, só o alfabeto do IFC, únicos no arquivo.
4. **Semântica.** Hierarquia espacial, unidades, perfil paramétrico com as dimensões
   do catálogo, furo de chapa saindo como vazio de verdade.

Se `ifcopenshell` estiver instalado, o arquivo também é aberto por ele; se não
estiver, os testes seguem só com a validação sintática e estrutural (e dizem isso).

    python testes/test_ifc_exportar.py
    python -m pytest testes/test_ifc_exportar.py -q
"""
import os
import re
import sys
import tempfile
import time
import unittest
import uuid

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from nucleo.base import ErroDeDados                                   # noqa: E402
from nucleo.perfis import perfil                                      # noqa: E402
from nucleo3d import geometria                                        # noqa: E402
from nucleo3d.modelo import Barra, Chapa, Documento, Grupo, Solido    # noqa: E402
from ifc.importar import importar_texto                               # noqa: E402
from ifc.exportar import (ALFABETO, comprimir_guid, exportar,         # noqa: E402
                          expandir_guid, guid_ifc, para_texto)

try:
    import ifcopenshell                                               # noqa: E402
except Exception:                                                     # pragma: no cover
    ifcopenshell = None


# ------------------------------------------------------------------ leitor de STEP

LINHA = re.compile(r"^#(\d+)= ([A-Z][A-Z0-9_]*)\((.*)\);$")


def sem_textos(linha: str) -> str:
    """Remove as strings da linha, para que um `#` dentro de um nome não vire
    referência falsa na hora de conferir a integridade."""
    return re.sub(r"'(?:''|[^'])*'", "''", linha)


class Arquivo:
    """Leitura mínima de um arquivo da parte 21, só o que os testes precisam."""

    def __init__(self, texto: str):
        self.texto = texto
        self.linhas = texto.split("\n")
        self.entidades = {}          # id -> (tipo, argumentos crus)
        self.por_tipo = {}
        dentro = False
        self.linhas_de_dados = []
        for linha in self.linhas:
            if linha == "DATA;":
                dentro = True
                continue
            if dentro and linha == "ENDSEC;":
                dentro = False
                continue
            if dentro and linha.strip():
                self.linhas_de_dados.append(linha)
                m = LINHA.match(linha)
                if m:
                    n, tipo, args = int(m.group(1)), m.group(2), m.group(3)
                    self.entidades[n] = (tipo, args)
                    self.por_tipo.setdefault(tipo, []).append((n, args))

    def tipo(self, nome: str):
        return self.por_tipo.get(nome.upper(), [])

    def um(self, nome: str):
        itens = self.tipo(nome)
        assert len(itens) == 1, f"esperado um único {nome}, achados {len(itens)}"
        return itens[0][1]

    def referencias(self):
        for linha in self.linhas_de_dados:
            for r in re.findall(r"#(\d+)", sem_textos(linha)):
                yield int(r), linha

    def guids(self):
        for linha in self.linhas_de_dados:
            m = re.match(r"^#\d+= [A-Z0-9_]+\('([^']{22})',#\d+,", linha)
            if m:
                yield m.group(1), linha


def argumentos(crus: str):
    """Separa os argumentos do nível de cima, respeitando parênteses e strings."""
    saida, atual, nivel, dentro = [], "", 0, False
    i = 0
    while i < len(crus):
        c = crus[i]
        if dentro:
            if c == "'":
                if i + 1 < len(crus) and crus[i + 1] == "'":
                    atual += "''"
                    i += 2
                    continue
                dentro = False
            atual += c
        elif c == "'":
            dentro = True
            atual += c
        elif c == "(":
            nivel += 1
            atual += c
        elif c == ")":
            nivel -= 1
            atual += c
        elif c == "," and nivel == 0:
            saida.append(atual)
            atual = ""
        else:
            atual += c
        i += 1
    saida.append(atual)
    return saida


# ------------------------------------------------------------------ modelos de teste

def doc_barra_w() -> Documento:
    doc = Documento(nome="Uma barra")
    doc.add(Barra(nome="V1", inicio=(0, 0, 6000), fim=(0, 10000, 6000),
                  perfil="W 310×38,7", papel="viga", aco="ASTM A572 Gr.50",
                  atributos={"marca": "V1", "razao": 0.78,
                             "critica": "Flexão — flambagem lateral com torção",
                             "norma": "NBR 8800:2008, item 5.4.2"}))
    return doc


def doc_chapa_furada(n_furos=4) -> Documento:
    doc = Documento(nome="Chapa de base")
    furos = [{"x": x, "y": y, "diametro": 26.0}
             for x, y in [(-120, -120), (120, -120), (120, 120), (-120, 120)][:n_furos]]
    doc.add(Chapa(nome="CB1", origem=(0, 0, 0), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0),
                  contorno=[(-175, -175), (175, -175), (175, 175), (-175, 175)],
                  espessura=19.0, furos=furos, aco="ASTM A36",
                  atributos={"marca": "CB1"}))
    return doc


def doc_galpao(vaos=9, terças_por_agua=6) -> Documento:
    """Galpão de duas águas, 20 × 40 m, pé-direito 6 m, com pórticos a cada 5 m.

    `nucleo3d/de_projeto.py` ainda não existe; quando existir, este documento deve
    ser substituído pelo que ele produz a partir de um `ProjetoGalpao` real. O que o
    teste quer aqui é volume: algumas centenas de elementos para medir tempo e
    tamanho de arquivo.
    """
    doc = Documento(nome="Galpão 20×40")
    vao, passo, pe_direito, flecha = 20000.0, 5000.0, 6000.0, 2000.0
    cumeeira = pe_direito + flecha
    for i in range(vaos):
        x = i * passo
        for lado, y in ((0, 0.0), (1, vao)):
            doc.add(Barra(nome=f"P{i + 1}{'AB'[lado]}", inicio=(x, y, 0),
                          fim=(x, y, pe_direito), perfil="W 310×38,7",
                          papel="pilar", camada="Estrutura", rotacao=90.0,
                          atributos={"marca": f"P{lado + 1}", "razao": 0.62}))
        doc.add(Barra(nome=f"V{i + 1}A", inicio=(x, 0.0, pe_direito),
                      fim=(x, vao / 2, cumeeira), perfil="W 310×32,7", papel="viga",
                      atributos={"marca": "V1", "razao": 0.81}))
        doc.add(Barra(nome=f"V{i + 1}B", inicio=(x, vao / 2, cumeeira),
                      fim=(x, vao, pe_direito), perfil="W 310×32,7", papel="viga",
                      atributos={"marca": "V1", "razao": 0.81}))
        # chapa de base dos dois pilares
        for lado, y in ((0, 0.0), (1, vao)):
            doc.add(Chapa(nome=f"CB{i + 1}{'AB'[lado]}", origem=(x, y, 0.0),
                          eixo_x=(1, 0, 0), eixo_y=(0, 1, 0), camada="Chapas",
                          contorno=[(-175, -175), (175, -175), (175, 175), (-175, 175)],
                          espessura=19.0, centrada=False, aco="ASTM A36",
                          furos=[{"x": sx * 120, "y": sy * 120, "diametro": 26.0}
                                 for sx in (-1, 1) for sy in (-1, 1)]))
    # terças das duas águas, vão a vão
    for j in range(terças_por_agua + 1):
        t = j / terças_por_agua
        for agua in (0, 1):
            y = t * vao / 2 if agua == 0 else vao - t * vao / 2
            z = pe_direito + t * flecha
            for i in range(vaos - 1):
                doc.add(Barra(nome=f"T{agua}{j}-{i}", inicio=(i * passo, y, z),
                              fim=((i + 1) * passo, y, z),
                              perfil="Ue 200×75×20×2,65", papel="terça",
                              camada="Terças", aco="ZAR-345",
                              atributos={"marca": "T1", "razao": 0.74}))
    # contraventamento do primeiro e do último vão, nas duas laterais
    for i in (0, vaos - 2):
        for y in (0.0, vao):
            doc.add(Barra(nome=f"CV{i}-{y:.0f}", inicio=(i * passo, y, 0),
                          fim=((i + 1) * passo, y, pe_direito), perfil="TC 33,7×2,65",
                          papel="contraventamento", camada="Contraventamento",
                          aco="ASTM A500 Gr.B", atributos={"marca": "CV1"}))
            doc.add(Barra(nome=f"CV{i}-{y:.0f}b", inicio=((i + 1) * passo, y, 0),
                          fim=(i * passo, y, pe_direito), perfil="TC 33,7×2,65",
                          papel="contraventamento", camada="Contraventamento",
                          aco="ASTM A500 Gr.B", atributos={"marca": "CV1"}))
    return doc


# ------------------------------------------------------------------ testes

class TestGlobalId(unittest.TestCase):

    def test_ida_e_volta(self):
        for _ in range(500):
            u = uuid.uuid4()
            texto = comprimir_guid(u)
            self.assertEqual(len(texto), 22)
            self.assertEqual(expandir_guid(texto), u)

    def test_alfabeto_do_ifc(self):
        """O alfabeto é o do IFC, não o da base64 do RFC 4648."""
        self.assertEqual(len(ALFABETO), 64)
        self.assertEqual(len(set(ALFABETO)), 64)
        self.assertTrue(ALFABETO.endswith("_$"))
        self.assertNotIn("+", ALFABETO)
        self.assertNotIn("/", ALFABETO)
        self.assertNotIn("=", ALFABETO)

    def test_primeiro_digito_carrega_dois_bits(self):
        """128 bits em 22 dígitos base 64: o primeiro dígito só pode ser 0 a 3."""
        for _ in range(200):
            self.assertIn(guid_ifc()[0], "0123")

    def test_valor_conhecido(self):
        """Confere contra a codificação canônica de um UUID conhecido."""
        u = uuid.UUID("2d0b0f4e-9d5f-4b1a-8c3e-7f1a2b3c4d5e")
        texto = comprimir_guid(u)
        self.assertEqual(len(texto), 22)
        self.assertEqual(expandir_guid(texto).int, u.int)
        # a codificação é o inteiro de 128 bits escrito na base 64 do IFC
        n, esperado = u.int, []
        for _ in range(22):
            n, r = divmod(n, 64)
            esperado.append(ALFABETO[r])
        self.assertEqual(texto, "".join(reversed(esperado)))

    def test_recusa_caractere_invalido(self):
        with self.assertRaises(ErroDeDados):
            expandir_guid("!" * 22)
        with self.assertRaises(ErroDeDados):
            expandir_guid("abc")


class TestSintaxeSTEP(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.texto = para_texto(doc_galpao(vaos=3, terças_por_agua=2),
                               projeto_nome="Galpão de teste", autor="Ana Souza",
                               organizacao="Acme Engenharia")
        cls.arq = Arquivo(cls.texto)

    def test_delimitadores(self):
        self.assertTrue(self.texto.startswith("ISO-10303-21;\n"))
        self.assertTrue(self.texto.rstrip().endswith("END-ISO-10303-21;"))
        self.assertIn("\nHEADER;\n", self.texto)
        self.assertIn("\nDATA;\n", self.texto)
        self.assertEqual(self.texto.count("\nENDSEC;\n"), 2)

    def test_cabecalho(self):
        self.assertIn("FILE_DESCRIPTION(('ViewDefinition [DesignTransferView_V1.0]'),"
                      "'2;1');", self.texto)
        self.assertIn("FILE_SCHEMA(('IFC4'));", self.texto)
        m = re.search(r"^FILE_NAME\((.*)\);$", self.texto, re.M)
        self.assertIsNotNone(m, "FILE_NAME ausente")
        args = argumentos(m.group(1))
        self.assertEqual(len(args), 7, "FILE_NAME tem sete argumentos")
        data = args[1].strip("'")
        # data em ISO 8601, como manda a parte 21
        self.assertRegex(data, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        self.assertIn("Ana Souza", args[2])
        self.assertIn("Acme", args[3])

    def test_toda_linha_de_dados_e_uma_entidade(self):
        for linha in self.arq.linhas_de_dados:
            self.assertRegex(linha, LINHA, f"linha fora do formato: {linha[:90]}")

    def test_numeracao_sem_buraco_e_sem_repeticao(self):
        ids = sorted(self.arq.entidades)
        self.assertEqual(ids, list(range(1, len(ids) + 1)))

    def test_integridade_referencial(self):
        """O teste mais importante: nenhuma referência pendurada."""
        faltando = {}
        for ref, linha in self.arq.referencias():
            if ref not in self.arq.entidades:
                faltando.setdefault(ref, linha)
        self.assertEqual(faltando, {}, f"referências inexistentes: {list(faltando)[:10]}")

    def test_parenteses_balanceados(self):
        for linha in self.arq.linhas_de_dados:
            limpa = sem_textos(linha)
            self.assertEqual(limpa.count("("), limpa.count(")"),
                             f"parênteses desbalanceados: {linha[:90]}")

    def test_arquivo_e_ascii_puro(self):
        """O não-ASCII tem que sair escapado em \\X2\\…\\X0\\, não como byte cru."""
        self.texto.encode("ascii")
        self.assertIn("\\X2\\", self.texto, "nenhum escape: o × do catálogo sumiu?")

    def test_guids_validos_e_unicos(self):
        vistos = set()
        permitido = set(ALFABETO)
        n = 0
        for guid, linha in self.arq.guids():
            n += 1
            self.assertEqual(len(guid), 22, linha[:80])
            self.assertTrue(set(guid) <= permitido,
                            f"GlobalId com caractere fora do alfabeto: {guid}")
            self.assertNotIn(guid, vistos, f"GlobalId repetido: {guid}")
            vistos.add(guid)
        self.assertGreater(n, 20, "poucos objetos com GlobalId")


class TestHierarquiaEUnidades(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.arq = Arquivo(para_texto(doc_galpao(vaos=3, terças_por_agua=2)))

    def test_hierarquia_espacial(self):
        for tipo in ("IFCPROJECT", "IFCSITE", "IFCBUILDING", "IFCBUILDINGSTOREY"):
            self.assertEqual(len(self.arq.tipo(tipo)), 1, f"falta um {tipo}")

    def test_agregacao_projeto_sitio_predio_pavimento(self):
        projeto = self.arq.tipo("IFCPROJECT")[0][0]
        sitio = self.arq.tipo("IFCSITE")[0][0]
        predio = self.arq.tipo("IFCBUILDING")[0][0]
        pavimento = self.arq.tipo("IFCBUILDINGSTOREY")[0][0]
        pares = set()
        for _, args in self.arq.tipo("IFCRELAGGREGATES"):
            a = argumentos(args)
            relativo = int(a[4].strip().lstrip("#"))
            for filho in re.findall(r"#(\d+)", a[5]):
                pares.add((relativo, int(filho)))
        self.assertIn((projeto, sitio), pares)
        self.assertIn((sitio, predio), pares)
        self.assertIn((predio, pavimento), pares)

    def test_elementos_contidos_no_pavimento(self):
        pavimento = self.arq.tipo("IFCBUILDINGSTOREY")[0][0]
        contidos = set()
        for _, args in self.arq.tipo("IFCRELCONTAINEDINSPATIALSTRUCTURE"):
            a = argumentos(args)
            self.assertEqual(int(a[5].strip().lstrip("#")), pavimento)
            contidos |= {int(x) for x in re.findall(r"#(\d+)", a[4])}
        elementos = {n for tipo in ("IFCBEAM", "IFCCOLUMN", "IFCMEMBER", "IFCPLATE")
                     for n, _ in self.arq.tipo(tipo)}
        self.assertTrue(elementos, "nenhum elemento exportado")
        self.assertEqual(elementos - contidos, set(),
                         "há elemento fora da estrutura espacial")

    def test_unidades_declaram_milimetro(self):
        atribuicao = self.arq.um("IFCUNITASSIGNMENT")
        refs = {int(x) for x in re.findall(r"#(\d+)", atribuicao)}
        textos = [self.arq.entidades[r][1] for r in refs]
        self.assertTrue(any(".LENGTHUNIT." in t and ".MILLI." in t and ".METRE." in t
                            for t in textos), "milímetro não declarado")
        self.assertTrue(any(".AREAUNIT." in t and ".SQUARE_METRE." in t for t in textos))
        self.assertTrue(any(".VOLUMEUNIT." in t and ".CUBIC_METRE." in t for t in textos))
        self.assertTrue(any(".MASSUNIT." in t and ".KILO." in t for t in textos))
        self.assertTrue(any(".FORCEUNIT." in t and ".NEWTON." in t for t in textos))

    def test_grau_por_unidade_de_conversao(self):
        conv = self.arq.tipo("IFCCONVERSIONBASEDUNIT")
        self.assertEqual(len(conv), 1)
        args = argumentos(conv[0][1])
        self.assertIn(".PLANEANGLEUNIT.", args[1])
        self.assertIn("degree", args[2])
        fator = self.arq.entidades[int(args[3].strip().lstrip("#"))][1]
        valor = float(re.search(r"IFCPLANEANGLEMEASURE\(([^)]+)\)", fator).group(1))
        self.assertAlmostEqual(valor, 3.141592653589793 / 180, places=9)

    def test_contextos_de_representacao(self):
        ctx = self.arq.tipo("IFCGEOMETRICREPRESENTATIONCONTEXT")
        self.assertEqual(len(ctx), 1)
        args = argumentos(ctx[0][1])
        self.assertEqual(args[1], "'Model'")
        self.assertEqual(args[2], "3")
        self.assertAlmostEqual(float(args[3].replace("E", "e")), 1e-5)
        sub = self.arq.tipo("IFCGEOMETRICREPRESENTATIONSUBCONTEXT")
        self.assertEqual(len(sub), 1)
        self.assertIn("'Body'", sub[0][1])
        self.assertIn(".MODEL_VIEW.", sub[0][1])
        self.assertIn(f"#{ctx[0][0]}", sub[0][1])

    def test_placement_encadeado(self):
        """Todo IfcLocalPlacement, menos o do terreno, aponta para outro placement."""
        raizes = 0
        for n, args in self.arq.tipo("IFCLOCALPLACEMENT"):
            a = argumentos(args)
            if a[0].strip() == "$":
                raizes += 1
            else:
                alvo = int(a[0].strip().lstrip("#"))
                self.assertEqual(self.arq.entidades[alvo][0], "IFCLOCALPLACEMENT")
        self.assertEqual(raizes, 1, "deve haver um único placement na raiz (o terreno)")


class TestBarra(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.arq = Arquivo(para_texto(doc_barra_w()))
        cls.p = perfil("W 310×38,7")

    def test_um_unico_elemento_linear(self):
        n = sum(len(self.arq.tipo(t)) for t in ("IFCBEAM", "IFCCOLUMN", "IFCMEMBER"))
        self.assertEqual(n, 1)
        self.assertEqual(len(self.arq.tipo("IFCBEAM")), 1, "papel 'viga' → IfcBeam")

    def test_perfil_parametrico_com_as_dimensoes_do_catalogo(self):
        args = argumentos(self.arq.um("IFCISHAPEPROFILEDEF"))
        self.assertEqual(args[0], ".AREA.")
        self.assertAlmostEqual(float(args[3]), self.p.bf)   # OverallWidth
        self.assertAlmostEqual(float(args[4]), self.p.d)    # OverallDepth
        self.assertAlmostEqual(float(args[5]), self.p.tw)   # WebThickness
        self.assertAlmostEqual(float(args[6]), self.p.tf)   # FlangeThickness

    def test_extrusao_com_a_profundidade_igual_ao_comprimento(self):
        args = argumentos(self.arq.um("IFCEXTRUDEDAREASOLID"))
        perfil_ref = int(args[0].strip().lstrip("#"))
        self.assertEqual(self.arq.entidades[perfil_ref][0], "IFCISHAPEPROFILEDEF")
        direcao = self.arq.entidades[int(args[2].strip().lstrip("#"))][1]
        self.assertEqual(direcao, "(0.,0.,1.)")          # extruda no Z local
        self.assertAlmostEqual(float(args[3]), 10000.0)    # o comprimento da barra

    def test_representacao_body(self):
        args = argumentos(self.arq.um("IFCSHAPEREPRESENTATION"))
        self.assertEqual(args[1], "'Body'")
        self.assertEqual(args[2], "'SweptSolid'")
        sub = self.arq.tipo("IFCGEOMETRICREPRESENTATIONSUBCONTEXT")[0][0]
        self.assertEqual(int(args[0].strip().lstrip("#")), sub)

    def test_eixo_local_acompanha_a_barra(self):
        """Viga na direção +Y: o Z local é +Y e a altura do perfil sai na vertical."""
        args = argumentos(self.arq.tipo("IFCBEAM")[0][1])
        placement = self.arq.entidades[int(args[5].strip().lstrip("#"))][1]
        eixo = self.arq.entidades[int(argumentos(placement)[1].strip().lstrip("#"))][1]
        a = argumentos(eixo)
        local = self.arq.entidades[int(a[0].strip().lstrip("#"))][1]
        self.assertEqual(local, "(0.,0.,6000.)")
        self.assertEqual(self.arq.entidades[int(a[1].strip().lstrip("#"))][1],
                         "(0.,1.,0.)")

    def test_nome_descricao_e_marca(self):
        args = argumentos(self.arq.tipo("IFCBEAM")[0][1])
        self.assertEqual(args[2], "'V1'")                   # Name
        self.assertNotEqual(args[3], "$")                   # Description
        self.assertEqual(args[7], "'V1'")                   # Tag (a marca)

    def test_propriedades_de_calculo(self):
        props = {}
        for _, args in self.arq.tipo("IFCPROPERTYSINGLEVALUE"):
            a = argumentos(args)
            props[a[0].strip("'")] = a[2]
        self.assertIn("Perfil", props)
        self.assertIn("RazaoAproveitamento", props)
        self.assertIn("0.78", props["RazaoAproveitamento"])
        self.assertIn("VerificacaoCritica", props)
        self.assertIn("Norma", props)
        self.assertIn("IsExternal", props)
        self.assertIn("LoadBearing", props)
        self.assertIn("FireRating", props)
        nomes = {argumentos(a)[2].strip("'")
                 for _, a in self.arq.tipo("IFCPROPERTYSET")}
        self.assertIn("Pset_BeamCommon", nomes)
        self.assertIn("Pset_MetalicaCalculo", nomes)

    def test_quantidades(self):
        self.assertEqual(len(self.arq.tipo("IFCELEMENTQUANTITY")), 1)
        for tipo in ("IFCQUANTITYLENGTH", "IFCQUANTITYAREA", "IFCQUANTITYVOLUME",
                     "IFCQUANTITYWEIGHT"):
            self.assertTrue(self.arq.tipo(tipo), f"falta {tipo}")
        peso = argumentos(self.arq.um("IFCQUANTITYWEIGHT"))
        # 38,7 kg/m × 10 m
        self.assertAlmostEqual(float(peso[3]), 387.0, places=3)

    def test_material_associado_com_propriedades(self):
        self.assertEqual(len(self.arq.tipo("IFCMATERIAL")), 1)
        self.assertIn("ASTM A572 Gr.50", self.arq.um("IFCMATERIAL"))
        self.assertEqual(len(self.arq.tipo("IFCRELASSOCIATESMATERIAL")), 1)
        props = self.arq.um("IFCMATERIALPROPERTIES")
        refs = [self.arq.entidades[int(x)][1]
                for x in re.findall(r"#(\d+)", argumentos(props)[2])]
        juntos = " ".join(refs)
        self.assertIn("YieldStress", juntos)
        self.assertIn("UltimateStress", juntos)
        self.assertIn("YoungModulus", juntos)
        self.assertIn("MassDensity", juntos)
        self.assertIn("345.", juntos)          # fy = 34,5 kN/cm² = 345 MPa

    def test_papel_define_o_tipo_ifc(self):
        casos = {"pilar": "IFCCOLUMN", "viga": "IFCBEAM", "terça": "IFCMEMBER",
                 "contraventamento": "IFCMEMBER", "longarina": "IFCMEMBER"}
        for papel, esperado in casos.items():
            doc = Documento()
            doc.add(Barra(nome="X", inicio=(0, 0, 0), fim=(0, 0, 3000),
                          perfil="W 310×38,7", papel=papel))
            arq = Arquivo(para_texto(doc))
            self.assertEqual(len(arq.tipo(esperado)), 1, f"{papel} → {esperado}")


class TestPerfisParametricos(unittest.TestCase):

    def _exporta(self, nome_perfil):
        doc = Documento()
        doc.add(Barra(nome="X", inicio=(0, 0, 0), fim=(5000, 0, 0),
                      perfil=nome_perfil, papel="viga"))
        return Arquivo(para_texto(doc))

    def test_tipos_de_perfil(self):
        casos = [("W 310×38,7", "IFCISHAPEPROFILEDEF"),
                 ("U 6\"×12,2", "IFCUSHAPEPROFILEDEF"),
                 ("L 2\"×1/4\"", "IFCLSHAPEPROFILEDEF"),
                 ("TC 33,7×2,65", "IFCCIRCLEHOLLOWPROFILEDEF"),
                 ("TQ 40×40×2,0", "IFCRECTANGLEHOLLOWPROFILEDEF"),
                 ("Ue 200×75×20×2,65", "IFCARBITRARYCLOSEDPROFILEDEF")]
        for nome, esperado in casos:
            arq = self._exporta(nome)
            self.assertEqual(len(arq.tipo(esperado)), 1,
                             f"{nome} deveria virar {esperado}")

    def test_tubo_circular_usa_o_raio(self):
        arq = self._exporta("TC 33,7×2,65")
        args = argumentos(arq.um("IFCCIRCLEHOLLOWPROFILEDEF"))
        self.assertAlmostEqual(float(args[3]), 33.7 / 2)
        self.assertAlmostEqual(float(args[4]), 2.65)

    def test_formado_a_frio_vira_polilinha_fechada(self):
        arq = self._exporta("Ue 200×75×20×2,65")
        curva = int(argumentos(arq.um("IFCARBITRARYCLOSEDPROFILEDEF"))[2]
                    .strip().lstrip("#"))
        tipo, args = arq.entidades[curva]
        self.assertEqual(tipo, "IFCPOLYLINE")
        pontos = re.findall(r"#(\d+)", args)
        self.assertGreaterEqual(len(pontos), 12)
        self.assertEqual(arq.entidades[int(pontos[0])][1],
                         arq.entidades[int(pontos[-1])][1], "polilinha não fechou")

    def test_barra_chata_e_redonda_fora_do_catalogo(self):
        self.assertEqual(len(self._exporta("CH 200×12,7").tipo("IFCRECTANGLEPROFILEDEF")), 1)
        self.assertEqual(len(self._exporta("Ø20").tipo("IFCCIRCLEPROFILEDEF")), 1)

    def test_perfis_sinteticos_do_orquestrador(self):
        """Os nomes que `nucleo3d.geometria` registra (tirantes, mísulas) também saem.

        O orquestrador do galpão cria perfis fora do catálogo e os registra no
        módulo de geometria; a exportação pergunta a ele antes de recusar o nome.
        """
        try:
            from nucleo3d import geometria
        except ImportError:
            self.skipTest("nucleo3d.geometria ainda não existe")
        if not hasattr(geometria, "resolver_perfil"):
            self.skipTest("geometria sem resolver_perfil")
        for nome, raio in (("Barra redonda ø 20 mm", 10.0),
                           ("Barra redonda ø 25 mm", 12.5)):
            arq = self._exporta(nome)
            args = argumentos(arq.um("IFCCIRCLEPROFILEDEF"))
            self.assertAlmostEqual(float(args[3]), raio, msg=nome)
        arq = self._exporta("Barra chata 200 × 12,7 mm")
        args = argumentos(arq.um("IFCRECTANGLEPROFILEDEF"))
        # como em geometria._dims: largura no X da seção, espessura no Y
        self.assertAlmostEqual(float(args[3]), 200.0)   # XDim = largura
        self.assertAlmostEqual(float(args[4]), 12.7)    # YDim = espessura

    def test_secao_vem_do_modulo_de_geometria(self):
        """O contorno do formado a frio é o mesmo que a tela e o DXF desenham."""
        try:
            from nucleo3d import geometria
        except ImportError:
            self.skipTest("nucleo3d.geometria ainda não existe")
        if not hasattr(geometria, "secao"):
            self.skipTest("geometria sem secao")
        arq = self._exporta("Ue 200×75×20×2,65")
        curva = int(argumentos(arq.um("IFCARBITRARYCLOSEDPROFILEDEF"))[2]
                    .strip().lstrip("#"))
        n = len(re.findall(r"#(\d+)", arq.entidades[curva][1])) - 1   # tira o fecho
        self.assertEqual(n, len(geometria.secao("Ue 200×75×20×2,65")))

    def test_perfil_desconhecido_falha_explicitamente(self):
        with self.assertRaises(ErroDeDados):
            self._exporta("perfil que não existe")


class TestOrientacaoDaSecao(unittest.TestCase):
    """O X do placement no IFC é a direção da mesa na malha do editor.

    A malha vem de `geometria.malha_barra`, a mesma que o editor e os desenhos usam.
    Se o IFC usasse outro triedro, o pilar abriria no Solibri girado em relação ao
    editor e voltaria do importador com outra `rotacao` — foi o defeito que o
    importador achou (o IFC punha o X da seção do pilar em +X, a malha em -Y).
    """

    CASOS = [("vertical", (1000.0, 2000.0, 0.0), (1000.0, 2000.0, 6000.0)),
             ("horizontal", (0.0, 0.0, 6000.0), (0.0, 8000.0, 6000.0)),
             ("inclinada", (0.0, 0.0, 6000.0), (0.0, 10000.0, 8000.0))]
    ROTACOES = (0.0, 30.0)
    PERFIL = "W 310×38,7"

    def _barra(self, ini, fim, rotacao):
        return Barra(nome="B", inicio=ini, fim=fim, perfil=self.PERFIL,
                     papel="pilar", rotacao=rotacao)

    @staticmethod
    def _vetor(arq, ref):
        texto = arq.entidades[int(ref.strip().lstrip("#"))][1]
        return tuple(float(c) for c in texto.strip("()").split(","))

    def _eixos_ifc(self, arq):
        """(Axis, RefDirection) do placement do único elemento linear."""
        elemento = next(a for t in ("IFCCOLUMN", "IFCBEAM", "IFCMEMBER")
                        for _, a in arq.tipo(t))
        pl = arq.entidades[int(argumentos(elemento)[5].strip().lstrip("#"))][1]
        eixo = argumentos(arq.entidades[int(argumentos(pl)[1].strip().lstrip("#"))][1])
        # a extrusão não pode acrescentar giro: o triedro inteiro está no placement
        solido = argumentos(arq.um("IFCEXTRUDEDAREASOLID"))
        pos = argumentos(arq.entidades[int(solido[1].strip().lstrip("#"))][1])
        self.assertEqual([pos[1].strip(), pos[2].strip()], ["$", "$"])
        return self._vetor(arq, eixo[1]), self._vetor(arq, eixo[2])

    def _mesa_na_malha(self, barra):
        """Direção da mesa na malha: da ponta esquerda à direita da mesa inferior.

        Os primeiros vértices da malha são os pontos de `geometria.secao` na mesma
        ordem, levados para a tampa inicial da barra.
        """
        vertices, _faces = geometria.malha_barra(barra)
        pts = geometria.secao(barra.perfil)
        self.assertLessEqual(len(pts), len(vertices))
        ymin = min(q[1] for q in pts)
        mesa = [i for i, q in enumerate(pts) if abs(q[1] - ymin) < 1e-6]
        i0 = min(mesa, key=lambda i: pts[i][0])
        i1 = max(mesa, key=lambda i: pts[i][0])
        d = tuple(vertices[i1][k] - vertices[i0][k] for k in range(3))
        n = sum(c * c for c in d) ** 0.5
        self.assertGreater(n, 100.0, "a mesa inferior deveria ter a largura bf")
        return tuple(c / n for c in d)

    def _assert_mesmo_vetor(self, a, b, msg):
        for k in range(3):
            self.assertAlmostEqual(a[k], b[k], places=9, msg=f"{msg}: {a} != {b}")

    def test_x_do_placement_e_a_mesa_da_malha(self):
        for nome, ini, fim in self.CASOS:
            for rot in self.ROTACOES:
                with self.subTest(barra=nome, rotacao=rot):
                    barra = self._barra(ini, fim, rot)
                    doc = Documento()
                    doc.add(barra)
                    eixo_z, eixo_x = self._eixos_ifc(Arquivo(para_texto(doc)))
                    self._assert_mesmo_vetor(eixo_x, self._mesa_na_malha(barra),
                                             f"{nome} {rot}°: X do IFC x mesa da malha")
                    self._assert_mesmo_vetor(eixo_z, barra.direcao,
                                             f"{nome} {rot}°: Z do IFC x eixo da barra")

    def test_triedro_e_o_de_base_local(self):
        """Confere o placement direto contra `geometria.base_local` (u e w)."""
        for nome, ini, fim in self.CASOS:
            for rot in self.ROTACOES:
                with self.subTest(barra=nome, rotacao=rot):
                    barra = self._barra(ini, fim, rot)
                    doc = Documento()
                    doc.add(barra)
                    eixo_z, eixo_x = self._eixos_ifc(Arquivo(para_texto(doc)))
                    u, _v, w = geometria.base_local(barra.direcao, rot)
                    self._assert_mesmo_vetor(eixo_x, u, f"{nome} {rot}°: u")
                    self._assert_mesmo_vetor(eixo_z, w, f"{nome} {rot}°: w")

    def test_ida_e_volta_pelo_importador_preserva_a_rotacao(self):
        for nome, ini, fim in self.CASOS:
            for rot in self.ROTACOES:
                with self.subTest(barra=nome, rotacao=rot):
                    doc = Documento()
                    doc.add(self._barra(ini, fim, rot))
                    volta = importar_texto(para_texto(doc))
                    self.assertEqual(len(volta.barras), 1,
                                     "o importador deveria reconhecer a barra")
                    b = volta.barras[0]
                    diferenca = ((b.rotacao - rot + 180.0) % 360.0) - 180.0
                    self.assertAlmostEqual(diferenca, 0.0, places=2,
                                           msg=f"{nome}: voltou com {b.rotacao}°")
                    for k in range(3):
                        self.assertAlmostEqual(b.inicio[k], ini[k], places=3)
                        self.assertAlmostEqual(b.fim[k], fim[k], places=3)


class TestChapa(unittest.TestCase):

    def test_furos_saem_como_vazios(self):
        for n in (1, 2, 4):
            arq = Arquivo(para_texto(doc_chapa_furada(n)))
            self.assertEqual(len(arq.tipo("IFCPLATE")), 1)
            args = argumentos(arq.um("IFCARBITRARYPROFILEDEFWITHVOIDS"))
            vazios = re.findall(r"#(\d+)", args[3])
            self.assertEqual(len(vazios), n, f"esperados {n} vazios")
            for v in vazios:
                self.assertEqual(arq.entidades[int(v)][0], "IFCPOLYLINE")

    def test_chapa_sem_furo_usa_perfil_simples(self):
        doc = Documento()
        doc.add(Chapa(nome="G1", origem=(0, 0, 0), eixo_x=(1, 0, 0), eixo_y=(0, 0, 1),
                      contorno=[(0, 0), (214, 0), (214, 760), (0, 760)], espessura=16))
        arq = Arquivo(para_texto(doc))
        self.assertEqual(len(arq.tipo("IFCARBITRARYCLOSEDPROFILEDEF")), 1)
        self.assertEqual(len(arq.tipo("IFCARBITRARYPROFILEDEFWITHVOIDS")), 0)
        self.assertEqual(len(arq.tipo("IFCPLATE")), 1)

    def test_vazio_gira_ao_contrario_do_contorno(self):
        """Contorno anti-horário e furo horário: é assim que o vazio é vazio."""
        arq = Arquivo(para_texto(doc_chapa_furada(1)))
        args = argumentos(arq.um("IFCARBITRARYPROFILEDEFWITHVOIDS"))

        def area(ref):
            pts = []
            for p in re.findall(r"#(\d+)", arq.entidades[int(ref)][1]):
                x, y = arq.entidades[int(p)][1].strip("()").split(",")
                pts.append((float(x), float(y)))
            pts = pts[:-1]
            return sum(pts[i][0] * pts[(i + 1) % len(pts)][1]
                       - pts[(i + 1) % len(pts)][0] * pts[i][1]
                       for i in range(len(pts))) / 2

        self.assertGreater(area(args[2].strip().lstrip("#")), 0)
        self.assertLess(area(re.findall(r"#(\d+)", args[3])[0]), 0)

    def test_espessura_centrada(self):
        doc = Documento()
        doc.add(Chapa(nome="E1", origem=(0, 0, 1000), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0),
                      contorno=[(0, 0), (100, 0), (100, 100), (0, 100)],
                      espessura=12.5, centrada=True))
        arq = Arquivo(para_texto(doc))
        args = argumentos(arq.um("IFCEXTRUDEDAREASOLID"))
        self.assertAlmostEqual(float(args[3]), 12.5)
        eixo = arq.entidades[int(args[1].strip().lstrip("#"))][1]
        ponto = arq.entidades[int(argumentos(eixo)[0].strip().lstrip("#"))][1]
        self.assertEqual(ponto, "(0.,0.,-6.25)")

    def test_chapa_invalida_falha(self):
        doc = Documento()
        doc.add(Chapa(nome="X", contorno=[(0, 0), (1, 0)], espessura=10))
        with self.assertRaises(ErroDeDados):
            para_texto(doc)


class TestSolidoEGrupo(unittest.TestCase):

    def _cubo(self, lado=1000.0):
        v = [(0, 0, 0), (lado, 0, 0), (lado, lado, 0), (0, lado, 0),
             (0, 0, lado), (lado, 0, lado), (lado, lado, lado), (0, lado, lado)]
        f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
             [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
        return Solido(nome="Cubo", vertices=v, faces=f)

    def test_brep_por_padrao(self):
        doc = Documento()
        doc.add(self._cubo())
        arq = Arquivo(para_texto(doc))
        self.assertEqual(len(arq.tipo("IFCBUILDINGELEMENTPROXY")), 1)
        self.assertEqual(len(arq.tipo("IFCFACETEDBREP")), 1)
        self.assertEqual(len(arq.tipo("IFCCLOSEDSHELL")), 1)
        self.assertEqual(len(arq.tipo("IFCFACE")), 6)
        self.assertIn("'Brep'", arq.um("IFCSHAPEREPRESENTATION"))

    def test_tesselacao_opcional(self):
        doc = Documento()
        doc.add(self._cubo())
        arq = Arquivo(para_texto(doc, solidos_como="tesselacao"))
        self.assertEqual(len(arq.tipo("IFCPOLYGONALFACESET")), 1)
        self.assertEqual(len(arq.tipo("IFCINDEXEDPOLYGONALFACE")), 6)
        self.assertIn("'Tessellation'", arq.um("IFCSHAPEREPRESENTATION"))

    def test_tipo_ifc_dos_atributos(self):
        doc = Documento()
        c = self._cubo()
        c.atributos["tipo_ifc"] = "IfcFooting"
        doc.add(c)
        arq = Arquivo(para_texto(doc))
        self.assertEqual(len(arq.tipo("IFCFOOTING")), 1)

    def test_tipo_ifc_desconhecido_vira_proxy(self):
        doc = Documento()
        c = self._cubo()
        c.atributos["tipo_ifc"] = "IfcCoisaQueNaoExiste"
        doc.add(c)
        arq = Arquivo(para_texto(doc))
        self.assertEqual(len(arq.tipo("IFCBUILDINGELEMENTPROXY")), 1)

    def test_grupo_vira_element_assembly(self):
        doc = Documento()
        g = doc.add(Grupo(nome="Treliça TR1", origem=(0.0, 0.0, 6000.0)))
        for i in range(4):
            doc.add(Barra(nome=f"D{i}", inicio=(i * 1000.0, 0, 6000.0),
                          fim=((i + 1) * 1000.0, 0, 6000.0), perfil="L 2\"×1/4\"",
                          papel="barra", grupo=g.id))
        g.filhos = [e.id for e in doc.entidades.values() if e.grupo == g.id]
        arq = Arquivo(para_texto(doc))
        self.assertEqual(len(arq.tipo("IFCELEMENTASSEMBLY")), 1)
        montagem = arq.tipo("IFCELEMENTASSEMBLY")[0][0]
        agregados = [a for _, a in arq.tipo("IFCRELAGGREGATES")
                     if argumentos(a)[4].strip() == f"#{montagem}"]
        self.assertEqual(len(agregados), 1)
        self.assertEqual(len(re.findall(r"#(\d+)", argumentos(agregados[0])[5])), 4)
        # o conjunto é que está contido no pavimento; as peças penduram nele
        contidos = set()
        for _, a in arq.tipo("IFCRELCONTAINEDINSPATIALSTRUCTURE"):
            contidos |= {int(x) for x in re.findall(r"#(\d+)", argumentos(a)[4])}
        self.assertEqual(contidos, {montagem})

    def test_geometria_do_filho_fica_no_lugar(self):
        """Peça dentro de conjunto: placement relativo ao conjunto, sem dobrar a origem."""
        doc = Documento()
        g = doc.add(Grupo(nome="G", origem=(1000.0, 0.0, 0.0)))
        doc.add(Barra(nome="B", inicio=(1000.0, 0.0, 0.0), fim=(1000.0, 0.0, 3000.0),
                      perfil="W 310×38,7", papel="pilar", grupo=g.id))
        arq = Arquivo(para_texto(doc))
        montagem = argumentos(arq.tipo("IFCELEMENTASSEMBLY")[0][1])
        pl_montagem = int(montagem[5].strip().lstrip("#"))
        barra = argumentos(arq.tipo("IFCCOLUMN")[0][1])
        pl_barra = int(barra[5].strip().lstrip("#"))
        a = argumentos(arq.entidades[pl_barra][1])
        self.assertEqual(int(a[0].strip().lstrip("#")), pl_montagem)
        eixo = arq.entidades[int(a[1].strip().lstrip("#"))][1]
        ponto = arq.entidades[int(argumentos(eixo)[0].strip().lstrip("#"))][1]
        self.assertEqual(ponto, "(0.,0.,0.)")     # relativo ao conjunto


def decodificar(bruto: str) -> str:
    """String da parte 21 → texto: tira as aspas e desfaz as aspas dobradas e o
    escape X2 (UTF-16 em hexadecimal) que o exportador usa para o não-ASCII."""
    s = bruto.strip()
    if s.startswith("'") and s.endswith("'"):
        s = s[1:-1]
    s = s.replace("''", "'")
    return re.sub(r"\\X2\\((?:[0-9A-F]{4})+)\\X0\\",
                  lambda m: "".join(chr(int(m.group(1)[i:i + 4], 16))
                                    for i in range(0, len(m.group(1)), 4)), s)


def _ref(texto: str) -> int:
    return int(texto.strip().lstrip("#"))


class TestCamadasECores(unittest.TestCase):
    """Contrato de aparência com o importador (camadas, cores e a reserva no Pset).

    Na ida e volta pelo editor as peças voltavam todas na camada do pavimento, a
    camada oculta voltava visível e o material de aparência voltava como o nome do
    aço. O documento aqui tem três camadas: uma normal, uma oculta e uma bloqueada.
    """

    @classmethod
    def setUpClass(cls):
        doc = Documento(nome="Camadas")
        doc.camadas["Fechamento"].visivel = False
        doc.camadas["Referência"].bloqueada = True
        cls.doc = doc
        doc.add(Barra(nome="P1", inicio=(0, 0, 0), fim=(0, 0, 6000), perfil="W 310×38,7",
                      papel="pilar", rotacao=90.0, camada="Estrutura", material="Aço"))
        doc.add(Barra(nome="V1", inicio=(0, 0, 6000), fim=(0, 10000, 6000),
                      perfil="W 310×38,7", papel="viga", camada="Estrutura",
                      material="Aço"))
        doc.add(Chapa(nome="F1", origem=(0, -100, 0), eixo_x=(1, 0, 0), eixo_y=(0, 0, 1),
                      contorno=[(0, 0), (5000, 0), (5000, 6000), (0, 6000)],
                      espessura=0.5, camada="Fechamento", material="Telha",
                      aco="ZAR-345"))
        v = [(0, 0, 0), (500, 0, 0), (500, 500, 0), (0, 500, 0),
             (0, 0, 500), (500, 0, 500), (500, 500, 500), (0, 500, 500)]
        f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
             [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
        doc.add(Solido(nome="R1", vertices=v, faces=f, camada="Referência",
                       material="Vidro"))
        cls.arq = Arquivo(para_texto(doc))
        cls.camadas = {}
        for _, a in cls.arq.tipo("IFCPRESENTATIONLAYERWITHSTYLE"):
            args = argumentos(a)
            cls.camadas.setdefault(decodificar(args[0]), []).append(args)

    # ---- auxiliares ----
    def _elemento_por_rep(self):
        mapa = {}
        for tipo in ("IFCBEAM", "IFCCOLUMN", "IFCMEMBER", "IFCPLATE") + _TIPOS_ELEMENTO_LIVRE:
            for _, a in self.arq.tipo(tipo):
                args = argumentos(a)
                if args[6].strip() == "$":
                    continue
                forma = argumentos(self.arq.entidades[_ref(args[6])][1])
                for r in re.findall(r"#(\d+)", forma[2]):
                    mapa[int(r)] = decodificar(args[2])
        return mapa

    def _cor_e_transparencia(self, estilo_ref: int):
        tipo, a = self.arq.entidades[estilo_ref]
        self.assertEqual(tipo, "IFCSURFACESTYLE")
        args = argumentos(a)
        self.assertEqual(args[1], ".BOTH.")
        render = re.findall(r"#(\d+)", args[2])
        self.assertEqual(len(render), 1)
        tipo_r, ar = self.arq.entidades[int(render[0])]
        self.assertEqual(tipo_r, "IFCSURFACESTYLERENDERING")
        ar = argumentos(ar)
        rgb = argumentos(self.arq.entidades[_ref(ar[0])][1])
        return decodificar(args[0]), tuple(float(x) for x in rgb[1:4]), float(ar[1])

    @staticmethod
    def _hex(cor):
        cor = cor.lstrip("#")
        return tuple(int(cor[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    # ---- testes ----
    def test_integridade_referencial(self):
        faltando = [r for r, _ in self.arq.referencias() if r not in self.arq.entidades]
        self.assertEqual(faltando, [])

    def test_uma_camada_por_camada_usada(self):
        self.assertEqual(set(self.camadas), {"Estrutura", "Fechamento", "Referência"})
        for nome, lista in self.camadas.items():
            self.assertEqual(len(lista), 1, f"camada {nome} repetida")

    def test_layer_on_frozen_e_blocked(self):
        esperado = {"Estrutura": (".T.", ".F."), "Fechamento": (".F.", ".F."),
                    "Referência": (".T.", ".T.")}
        for nome, (ligada, bloqueada) in esperado.items():
            args = self.camadas[nome][0]
            self.assertEqual(len(args), 8, "IfcPresentationLayerWithStyle tem 8 atributos")
            self.assertEqual(args[4], ligada, f"{nome}: LayerOn")
            self.assertEqual(args[5], ".F.", f"{nome}: LayerFrozen sempre .F.")
            self.assertEqual(args[6], bloqueada, f"{nome}: LayerBlocked")

    def test_representacoes_certas_em_cada_camada(self):
        por_rep = self._elemento_por_rep()
        esperado = {"Estrutura": {"P1", "V1"}, "Fechamento": {"F1"}, "Referência": {"R1"}}
        for nome, elementos in esperado.items():
            reps = [int(r) for r in re.findall(r"#(\d+)", self.camadas[nome][0][2])]
            for r in reps:
                self.assertEqual(self.arq.entidades[r][0], "IFCSHAPEREPRESENTATION")
            self.assertEqual({por_rep[r] for r in reps}, elementos, nome)
        # cada representação está em exatamente uma camada
        todas = [int(r) for lista in self.camadas.values()
                 for r in re.findall(r"#(\d+)", lista[0][2])]
        self.assertEqual(len(todas), len(set(todas)))
        self.assertEqual(set(todas), set(por_rep))

    def test_estilo_da_camada_tem_a_cor_da_camada(self):
        for nome, lista in self.camadas.items():
            estilos = re.findall(r"#(\d+)", lista[0][7])
            self.assertEqual(len(estilos), 1)
            _nome, rgb, transp = self._cor_e_transparencia(int(estilos[0]))
            for a, b in zip(rgb, self._hex(self.doc.camadas[nome].cor)):
                self.assertAlmostEqual(a, b, places=6, msg=nome)
            self.assertEqual(transp, 0.0)

    def test_cor_do_material_em_cada_item_de_geometria(self):
        estilizados = {}
        for _, a in self.arq.tipo("IFCSTYLEDITEM"):
            args = argumentos(a)
            estilos = re.findall(r"#(\d+)", args[1])
            self.assertEqual(len(estilos), 1)
            estilizados.setdefault(_ref(args[0]), []).append(int(estilos[0]))
        itens = [n for t in ("IFCEXTRUDEDAREASOLID", "IFCFACETEDBREP")
                 for n, _ in self.arq.tipo(t)]
        self.assertEqual(len(itens), 4)
        for item in itens:
            self.assertEqual(len(estilizados.get(item, [])), 1, f"item #{item} sem cor")
        # item → elemento → material esperado
        material_de = {"P1": "Aço", "V1": "Aço", "F1": "Telha", "R1": "Vidro"}
        por_rep = self._elemento_por_rep()
        for rep, elemento in por_rep.items():
            rep_args = argumentos(self.arq.entidades[rep][1])
            for item in re.findall(r"#(\d+)", rep_args[3]):
                nome, rgb, transp = self._cor_e_transparencia(estilizados[int(item)][0])
                mat = self.doc.materiais[material_de[elemento]]
                self.assertEqual(nome, mat.nome)
                for a, b in zip(rgb, self._hex(mat.cor)):
                    self.assertAlmostEqual(a, b, places=6)
                self.assertAlmostEqual(transp, 1.0 - mat.opacidade, places=6)

    def test_um_estilo_por_material(self):
        nomes = [decodificar(argumentos(a)[0]) for _, a in self.arq.tipo("IFCSURFACESTYLE")]
        self.assertEqual(nomes.count("Aço"), 1, "duas barras de Aço: um estilo só")
        # 3 materiais usados + 3 camadas
        self.assertEqual(len(nomes), 6, nomes)

    def test_reserva_no_pset_de_calculo(self):
        valores = {}
        for _, a in self.arq.tipo("IFCPROPERTYSET"):
            args = argumentos(a)
            if decodificar(args[2]) != "Pset_MetalicaCalculo":
                continue
            props = {}
            for r in re.findall(r"#(\d+)", args[4]):
                p = argumentos(self.arq.entidades[int(r)][1])
                m = re.match(r"IFCLABEL\((.*)\)$", p[2])
                if m:
                    props[decodificar(p[0])] = decodificar(m.group(1))
            valores[(props.get("Camada"), props.get("MaterialAparencia"))] = True
        for par in (("Estrutura", "Aço"), ("Fechamento", "Telha"), ("Referência", "Vidro")):
            self.assertIn(par, valores, f"Pset_MetalicaCalculo sem {par}")

    def test_ida_e_volta_pelo_importador(self):
        """O defeito do editor: as peças voltavam todas em "Nível 0", a camada oculta
        voltava visível e o material de aparência voltava como o nome do aço."""
        volta = importar_texto(para_texto(self.doc))
        ida = {e.nome: e for e in self.doc.entidades.values()}
        self.assertEqual({e.nome for e in volta.entidades.values()}, set(ida))
        for e in volta.entidades.values():
            self.assertEqual(e.camada, ida[e.nome].camada, f"{e.nome}: camada")
            self.assertEqual(e.material, ida[e.nome].material, f"{e.nome}: material")
        for nome in ("Estrutura", "Fechamento", "Referência"):
            c, original = volta.camadas.get(nome), self.doc.camadas[nome]
            self.assertIsNotNone(c, f"camada {nome} não voltou")
            self.assertEqual(c.visivel, original.visivel, f"{nome}: visível")
            self.assertEqual(c.bloqueada, original.bloqueada, f"{nome}: bloqueada")
            self.assertEqual(c.cor.lower(), original.cor.lower(), f"{nome}: cor")

    def test_galpao_uma_camada_por_camada_usada(self):
        doc = doc_galpao(vaos=3, terças_por_agua=2)
        arq = Arquivo(para_texto(doc))
        usadas = {e.camada for e in doc.entidades.values() if not isinstance(e, Grupo)}
        nomes = [decodificar(argumentos(a)[0])
                 for _, a in arq.tipo("IFCPRESENTATIONLAYERWITHSTYLE")]
        self.assertEqual(sorted(nomes), sorted(usadas))


class TestOpcoes(unittest.TestCase):

    def test_sem_propriedades_e_sem_quantidades(self):
        texto = para_texto(doc_barra_w(), incluir_propriedades=False,
                           incluir_quantidades=False)
        arq = Arquivo(texto)
        self.assertEqual(arq.tipo("IFCPROPERTYSET"), [])
        self.assertEqual(arq.tipo("IFCELEMENTQUANTITY"), [])
        self.assertEqual(len(arq.tipo("IFCBEAM")), 1)
        # sem propriedade o arquivo continua íntegro
        for ref, _ in arq.referencias():
            self.assertIn(ref, arq.entidades)

    def test_documento_vazio_ainda_gera_hierarquia(self):
        arq = Arquivo(para_texto(Documento(nome="Vazio")))
        for tipo in ("IFCPROJECT", "IFCSITE", "IFCBUILDING", "IFCBUILDINGSTOREY"):
            self.assertEqual(len(arq.tipo(tipo)), 1)

    def test_entrada_errada_falha(self):
        with self.assertRaises(ErroDeDados):
            para_texto({"nao": "e um documento"})

    def test_barra_de_comprimento_nulo_falha(self):
        doc = Documento()
        doc.add(Barra(nome="X", inicio=(0, 0, 0), fim=(0, 0, 0), perfil="W 310×38,7"))
        with self.assertRaises(ErroDeDados):
            para_texto(doc)


class TestArquivoEmDisco(unittest.TestCase):

    def test_grava_e_devolve_o_caminho(self):
        doc = doc_barra_w()
        pasta = tempfile.mkdtemp(prefix="ifc_")
        try:
            destino = os.path.join(pasta, "sub", "modelo.ifc")
            devolvido = exportar(doc, destino, projeto_nome="P", autor="A")
            self.assertEqual(devolvido, destino)
            self.assertTrue(os.path.isfile(destino))
            with open(destino, encoding="ascii") as f:
                texto = f.read()
            self.assertTrue(texto.startswith("ISO-10303-21;"))
            self.assertTrue(texto.rstrip().endswith("END-ISO-10303-21;"))
        finally:
            import shutil
            shutil.rmtree(pasta, ignore_errors=True)


class TestGalpaoInteiro(unittest.TestCase):
    """O teste de carga: um galpão inteiro sai rápido e não incha o arquivo."""

    @classmethod
    def setUpClass(cls):
        cls.doc = doc_galpao()
        cls.pasta = tempfile.mkdtemp(prefix="ifc_galpao_")
        cls.caminho = os.path.join(cls.pasta, "galpao.ifc")
        inicio = time.perf_counter()
        exportar(cls.doc, cls.caminho, projeto_nome="Galpão 20×40",
                 autor="Ana Souza", organizacao="Acme Engenharia")
        cls.segundos = time.perf_counter() - inicio
        cls.tamanho = os.path.getsize(cls.caminho)
        with open(cls.caminho, encoding="ascii") as f:
            cls.arq = Arquivo(f.read())

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def test_modelo_tem_porte(self):
        self.assertGreaterEqual(len(self.doc.barras), 100)
        self.assertGreaterEqual(len(self.doc.chapas), 10)

    def test_exporta_em_menos_de_dez_segundos(self):
        self.assertLess(self.segundos, 10.0, f"levou {self.segundos:.1f} s")

    def test_arquivo_abaixo_de_vinte_megabytes(self):
        self.assertLess(self.tamanho, 20 * 1024 * 1024,
                        f"{self.tamanho / 1e6:.1f} MB")

    def test_integridade_referencial(self):
        faltando = [r for r, _ in self.arq.referencias() if r not in self.arq.entidades]
        self.assertEqual(faltando, [])

    def test_todos_os_elementos_sairam(self):
        elementos = sum(len(self.arq.tipo(t)) for t in
                        ("IFCBEAM", "IFCCOLUMN", "IFCMEMBER", "IFCPLATE"))
        self.assertEqual(elementos, len(self.doc.barras) + len(self.doc.chapas))

    def test_guids_unicos_no_arquivo_inteiro(self):
        guids = [g for g, _ in self.arq.guids()]
        self.assertEqual(len(guids), len(set(guids)))

    def test_reaproveita_pontos_e_perfis(self):
        """Terças iguais não podem virar mil perfis iguais no arquivo."""
        self.assertLessEqual(len(self.arq.tipo("IFCISHAPEPROFILEDEF")), 4)
        self.assertLessEqual(len(self.arq.tipo("IFCARBITRARYCLOSEDPROFILEDEF")), 4)


class TestGalpaoDoProjeto(unittest.TestCase):
    """O galpão que `nucleo3d.de_projeto` monta a partir de um cálculo de verdade.

    É o arquivo que o cliente recebe: pilares, vigas, terças, longarinas, tirantes
    "Barra redonda ø …" (perfil sintético, fora do catálogo), chapas e bases.
    """

    @classmethod
    def setUpClass(cls):
        try:
            from nucleo3d import de_projeto
            from nucleo.galpao import dimensionar
            from nucleo.modelo_galpao import DadosGalpao
        except ImportError as e:                                     # pragma: no cover
            raise unittest.SkipTest(f"de_projeto indisponível: {e}")
        projeto = dimensionar(DadosGalpao(
            nome="Galpão 20×40", vao=20.0, comprimento=40.0, pe_direito=6.0,
            espacamento_porticos=5.0, inclinacao=10.0, v0=40.0,
            categoria_rugosidade="II", classe="B"))
        cls.doc = de_projeto.modelo_do_galpao(projeto)
        cls.pasta = tempfile.mkdtemp(prefix="ifc_projeto_")
        cls.caminho = os.path.join(cls.pasta, "galpao.ifc")
        inicio = time.perf_counter()
        exportar(cls.doc, cls.caminho, projeto_nome=cls.doc.nome)
        cls.segundos = time.perf_counter() - inicio
        cls.tamanho = os.path.getsize(cls.caminho)
        with open(cls.caminho, encoding="ascii") as f:
            cls.arq = Arquivo(f.read())

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def test_tempo_e_tamanho(self):
        self.assertLess(self.segundos, 10.0, f"levou {self.segundos:.1f} s")
        self.assertLess(self.tamanho, 20 * 1024 * 1024, f"{self.tamanho / 1e6:.1f} MB")

    def test_integridade_referencial(self):
        faltando = [r for r, _ in self.arq.referencias() if r not in self.arq.entidades]
        self.assertEqual(faltando, [])

    def test_toda_entidade_do_documento_saiu(self):
        elementos = sum(len(v) for k, v in self.arq.por_tipo.items()
                        if k in ("IFCBEAM", "IFCCOLUMN", "IFCMEMBER", "IFCPLATE")
                        or k in _TIPOS_ELEMENTO_LIVRE)
        esperado = len(self.doc.barras) + len(self.doc.chapas) + len(self.doc.solidos)
        self.assertEqual(elementos, esperado)

    def test_tirantes_saem_como_circulo(self):
        tirantes = {b.perfil for b in self.doc.barras
                    if b.perfil.lower().startswith("barra")}
        if not tirantes:
            self.skipTest("o galpão de referência não tem tirantes")
        nomes = {argumentos(a)[1] for _, a in self.arq.tipo("IFCCIRCLEPROFILEDEF")}
        self.assertEqual(len(nomes), len(tirantes), nomes)


#: tipos de elemento que um `Solido` pode virar (ver `_TIPOS_SOLIDO` em exportar.py)
_TIPOS_ELEMENTO_LIVRE = ("IFCBUILDINGELEMENTPROXY", "IFCWALL", "IFCSLAB", "IFCFOOTING",
                         "IFCPILE", "IFCRAILING", "IFCCOVERING", "IFCROOF", "IFCSTAIR",
                         "IFCRAMP", "IFCDISCRETEACCESSORY", "IFCMECHANICALFASTENER")


@unittest.skipIf(ifcopenshell is None, "ifcopenshell não está instalado neste ambiente")
class TestComIfcOpenShell(unittest.TestCase):
    """Validação com biblioteca de verdade, quando ela existe no ambiente.

    Quando `ifcopenshell` não está instalado, estes testes são pulados e a
    validação fica sendo a sintática e estrutural dos testes acima — o que já
    cobre o que costuma quebrar (referência pendurada, GlobalId torto, hierarquia
    incompleta), mas não substitui a conferência do esquema.
    """

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp(prefix="ifc_ios_")
        cls.caminho = os.path.join(cls.pasta, "modelo.ifc")
        exportar(doc_galpao(vaos=3, terças_por_agua=2), cls.caminho)
        cls.modelo = ifcopenshell.open(cls.caminho)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def test_esquema_ifc4(self):
        self.assertEqual(self.modelo.schema, "IFC4")

    def test_hierarquia(self):
        self.assertEqual(len(self.modelo.by_type("IfcProject")), 1)
        self.assertEqual(len(self.modelo.by_type("IfcSite")), 1)
        self.assertEqual(len(self.modelo.by_type("IfcBuilding")), 1)
        self.assertEqual(len(self.modelo.by_type("IfcBuildingStorey")), 1)

    def test_geometria_abre(self):
        import ifcopenshell.geom
        ajustes = ifcopenshell.geom.settings()
        n = 0
        for produto in self.modelo.by_type("IfcBeam") + self.modelo.by_type("IfcColumn"):
            forma = ifcopenshell.geom.create_shape(ajustes, produto)
            self.assertGreater(len(forma.geometry.verts), 0)
            n += 1
            if n >= 10:
                break
        self.assertGreater(n, 0)

    def test_validacao_do_esquema(self):
        try:
            from ifcopenshell import validate
        except Exception:
            self.skipTest("ifcopenshell.validate indisponível")
        jornal = validate.json_logger()
        validate.validate(self.modelo, jornal)
        self.assertEqual(jornal.statements, [], f"{jornal.statements[:5]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
