# -*- coding: utf-8 -*-
"""Testes dos desenhos de detalhamento (`saida.desenhos`).

O que se verifica em cada desenho:
  1. o DXF grava e reabre com `saida.dxf_render.ler_dxf`, com entidades nas camadas
     que aquele desenho obrigatoriamente usa;
  2. nenhuma coordenada é NaN ou infinita;
  3. os extremos batem com a geometria pedida (vão, comprimento, pé-direito), e as
     cotas e textos correspondentes estão escritos no desenho;
  4. tudo isso em três galpões diferentes — vão de 12, 20 e 30 m, com e sem mísula,
     base rotulada e engastada.

O galpão de 20 m reproduz o exemplo do Capítulo 16 do manual.
"""
import math
import os
import shutil
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from nucleo.modelo_galpao import DadosGalpao          # noqa: E402
from nucleo.perfis import banco                       # noqa: E402
from saida import desenhos                            # noqa: E402
from saida.dxf import Desenho                         # noqa: E402
from saida.dxf_render import ler_dxf                  # noqa: E402


# ---------------------------------------------------------------- geometrias de teste

#: (rótulo, DadosGalpao). Cobrem vão pequeno/médio/grande, com e sem mísula e os dois
#: tipos de base.
GALPOES = [
    ("12 m sem misula, base engastada",
     DadosGalpao(nome="G12", vao=12.0, comprimento=24.0, pe_direito=5.0,
                 espacamento_porticos=6.0, inclinacao=8.0, com_misula=False,
                 base_rotulada=False, espacamento_tercas=1.8, linhas_correntes=1)),
    ("20 m com misula, base rotulada (Cap. 16)",
     DadosGalpao(nome="G20", vao=20.0, comprimento=40.0, pe_direito=6.0,
                 espacamento_porticos=5.0, inclinacao=10.0, com_misula=True,
                 comprimento_misula=1.8, base_rotulada=True,
                 espacamento_tercas=1.6, linhas_correntes=1)),
    ("30 m com misula, base engastada",
     DadosGalpao(nome="G30", vao=30.0, comprimento=60.0, pe_direito=8.0,
                 espacamento_porticos=6.0, inclinacao=12.0, com_misula=True,
                 comprimento_misula=3.0, base_rotulada=False,
                 espacamento_tercas=1.5, linhas_correntes=2)),
]


# ---------------------------------------------------------------- utilidades

def _gravar_e_ler(d: Desenho, pasta: str, nome: str) -> dict:
    caminho = os.path.join(pasta, f"{nome}.dxf")
    d.gravar(caminho)
    doc = ler_dxf(caminho)
    doc["caminho"] = caminho
    return doc


def _pontos(doc, camadas=None):
    """Todas as coordenadas (x, y) das entidades, opcionalmente filtrando camadas."""
    for e in doc["entidades"]:
        if camadas is not None and e.get("camada", "0") not in camadas:
            continue
        if e["tipo"] == "POLYLINE":
            for x, y in e["pontos"]:
                yield x, y
        elif e["tipo"] == "CIRCLE":
            r = e.get(40, 0.0)
            yield e.get(10, 0.0) - r, e.get(20, 0.0) - r
            yield e.get(10, 0.0) + r, e.get(20, 0.0) + r
        else:
            for cx, cy in ((10, 20), (11, 21), (12, 22), (13, 23)):
                if cx in e or cy in e:
                    yield e.get(cx, 0.0), e.get(cy, 0.0)


def _caixa(doc, camadas=None):
    xs, ys = [], []
    for x, y in _pontos(doc, camadas):
        xs.append(x)
        ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _camadas_usadas(doc) -> set:
    return {e.get("camada", "0") for e in doc["entidades"]}


def _textos(doc) -> list:
    return [e.get("texto", "") for e in doc["entidades"] if e["tipo"] == "TEXT"]


def _numeros_finitos(doc):
    """Devolve a lista de valores não finitos encontrados (deve ser vazia)."""
    ruins = []
    for e in doc["entidades"]:
        if e["tipo"] == "POLYLINE":
            for x, y in e["pontos"]:
                if not (math.isfinite(x) and math.isfinite(y)):
                    ruins.append((e["tipo"], x, y))
            continue
        for cod, val in e.items():
            if isinstance(cod, int) and isinstance(val, float):
                if not math.isfinite(val):
                    ruins.append((e["tipo"], cod, val))
    return ruins


def _projeto_com(dg, *elementos):
    """ProjetoGalpao com os elementos dados como (nome, perfil, geometria)."""
    from nucleo.modelo_galpao import ProjetoGalpao, ElementoDimensionado
    p = ProjetoGalpao(dados=dg)
    for nome, perfil, geo in elementos:
        p.elementos.append(ElementoDimensionado(nome=nome, perfil=perfil, material="",
                                                geometria=dict(geo)))
    return p


class _Base(unittest.TestCase):
    """Grava os DXF numa pasta temporária única para a classe toda."""

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp(prefix="desenhos_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def conferir(self, doc, camadas_obrigatorias, rotulo=""):
        """Checagens comuns a todo desenho: camadas, finitude e conteúdo mínimo."""
        self.assertGreater(len(doc["entidades"]), 50,
                           f"{rotulo}: desenho praticamente vazio")
        usadas = _camadas_usadas(doc)
        for c in camadas_obrigatorias:
            self.assertIn(c, usadas, f"{rotulo}: falta entidade na camada {c}")
        ruins = _numeros_finitos(doc)
        self.assertEqual(ruins, [], f"{rotulo}: coordenadas nao finitas: {ruins[:5]}")
        self.assertTrue(any(t.strip() for t in _textos(doc)),
                        f"{rotulo}: desenho sem nenhum texto")


# ---------------------------------------------------------------- 1. pórtico

class TestPortico(_Base):

    def test_portico_geometria_e_camadas(self):
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                d = desenhos.portico(dg)
                doc = _gravar_e_ler(d, self.pasta, f"portico_{dg.nome}")
                self.conferir(doc, ["ACO", "COTA", "TEXTO", "EIXO", "CONCRETO"], rotulo)

                vao_mm = dg.vao * 1000.0
                cx = _caixa(doc, {"ACO", "ACO-FINO"})
                self.assertIsNotNone(cx)
                larg = cx[2] - cx[0]
                # a estrutura ocupa o vão mais a profundidade dos dois meios-pilares
                self.assertGreaterEqual(larg, vao_mm * 0.98, rotulo)
                self.assertLessEqual(larg, vao_mm * 1.10, rotulo)

                # altura: da base do pedestal ao topo da cumeeira
                alt_estr = cx[3] - cx[1]
                hc = dg.altura_cumeeira * 1000.0
                self.assertGreaterEqual(alt_estr, hc * 0.98, rotulo)
                self.assertLessEqual(alt_estr, hc * 1.15, rotulo)

                # as cotas pedidas estão escritas
                txt = _textos(doc)
                self.assertTrue(any(f"{vao_mm:.0f}" in t for t in txt),
                                f"{rotulo}: falta a cota do vao")
                self.assertTrue(any(f"{dg.pe_direito * 1000:.0f}" in t for t in txt),
                                f"{rotulo}: falta a cota do pe-direito")
                self.assertTrue(any(f"{hc:.0f}" in t for t in txt),
                                f"{rotulo}: falta a cota da cumeeira")
                self.assertTrue(any("N1" == t for t in txt), f"{rotulo}: falta o no N1")
                self.assertTrue(any("N3" == t for t in txt), f"{rotulo}: falta o no N3")

                # perfis nomeados
                g = desenhos._Geo(dg)
                self.assertTrue(any(g.pilar.nome.replace("×", "x") in t.replace("×", "x")
                                    for t in txt), f"{rotulo}: perfil do pilar ausente")
                self.assertTrue(any(g.viga.nome.replace("×", "x") in t.replace("×", "x")
                                    for t in txt), f"{rotulo}: perfil da viga ausente")

    def test_portico_misula_so_quando_pedida(self):
        com = desenhos.portico(GALPOES[1][1])
        sem = desenhos.portico(GALPOES[0][1])
        doc_com = _gravar_e_ler(com, self.pasta, "misula_sim")
        doc_sem = _gravar_e_ler(sem, self.pasta, "misula_nao")
        self.assertTrue(any("MISULA" in t for t in _textos(doc_com)))
        self.assertFalse(any("MISULA" in t for t in _textos(doc_sem)))

    def test_portico_base_rotulada_ou_engastada(self):
        doc_rot = _gravar_e_ler(desenhos.portico(GALPOES[1][1]), self.pasta, "base_rot")
        doc_eng = _gravar_e_ler(desenhos.portico(GALPOES[2][1]), self.pasta, "base_eng")
        self.assertTrue(any("ROTULADA" in t for t in _textos(doc_rot)))
        self.assertTrue(any("ENGASTADA" in t for t in _textos(doc_eng)))


# ---------------------------------------------------------------- 2. planta

class TestPlantaCobertura(_Base):

    def test_planta(self):
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                doc = _gravar_e_ler(desenhos.planta_cobertura(dg), self.pasta,
                                    f"planta_{dg.nome}")
                self.conferir(doc, ["ACO", "ACO-FINO", "COTA", "TEXTO", "EIXO",
                                    "AUXILIAR"], rotulo)

                C = dg.comprimento * 1000.0
                V = dg.vao * 1000.0
                cx = _caixa(doc, {"ACO", "ACO-FINO"})
                self.assertAlmostEqual((cx[2] - cx[0]) / C, 1.0, delta=0.03, msg=rotulo)
                self.assertAlmostEqual((cx[3] - cx[1]) / V, 1.0, delta=0.05, msg=rotulo)

                txt = _textos(doc)
                self.assertTrue(any(f"{C:.0f}" in t for t in txt), rotulo)
                self.assertTrue(any(f"{V:.0f}" in t for t in txt), rotulo)
                self.assertIn("CUMEEIRA", txt, rotulo)
                self.assertIn(f"P{dg.n_porticos}", txt, rotulo)
                # espaçamento de terças cotado e dentro do alvo do usuário
                g = desenhos._Geo(dg)
                self.assertTrue(any(" x " in t and "=" in t for t in txt),
                                f"{rotulo}: falta a cota do espacamento de tercas")

    @staticmethod
    def _espacamento_na_nota(doc):
        nota = [t for t in _textos(doc) if "linhas de terca" in t]
        return nota, (int(nota[0].split("a cada ")[1].split(" ")[0]) if nota else None)

    def test_tercas_sem_calculo_nao_passam_do_alvo(self):
        """Sem o elemento calculado vale a regra do cálculo: 200 mm do beiral e 250 mm
        da cumeeira ao longo da água, vãos arredondados para cima."""
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                doc = _gravar_e_ler(desenhos.planta_cobertura(dg), self.pasta,
                                    f"terca_{dg.nome}")
                util = dg.comprimento_agua * 1000.0 - 450.0
                n_esp = math.ceil(util / (dg.espacamento_tercas * 1000.0) - 1e-9)
                nota, valor = self._espacamento_na_nota(doc)
                self.assertTrue(nota, rotulo)
                self.assertIn(f"{2 * (n_esp + 1)} linhas de terca", nota[0], rotulo)
                self.assertAlmostEqual(valor, util / n_esp, delta=1.0, msg=rotulo)
                self.assertLessEqual(valor, dg.espacamento_tercas * 1000.0 + 0.5, rotulo)

    def test_tercas_usam_exatamente_o_publicado(self):
        """Com o cálculo real: o espaçamento publicado não passa do alvo, e o desenho
        mostra exatamente esse valor (ao longo da água e projetado na planta)."""
        try:
            from nucleo.galpao import dimensionar
        except ImportError:
            self.skipTest("nucleo.galpao ainda nao disponivel")
        dg = GALPOES[1][1]
        p = dimensionar(dg)
        geo = p.elemento("Terça").geometria
        esp = geo["espacamento_m"] * 1000.0
        self.assertLessEqual(esp, dg.espacamento_tercas * 1000.0 + 0.5,
                             "o calculo publicou espacamento acima do alvo")
        doc = _gravar_e_ler(desenhos.planta_cobertura(p), self.pasta, "terca_calc")
        nota, valor = self._espacamento_na_nota(doc)
        self.assertEqual(valor, round(esp))
        self.assertIn(f"{2 * geo['linhas']} linhas de terca", nota[0])
        em_planta = round(esp * math.cos(math.atan(dg.inclinacao / 100.0)))
        self.assertTrue(any(t.startswith(f"{geo['linhas'] - 1} x {em_planta} =")
                            for t in _textos(doc)), "cota em planta nao e esp x cos")

    def test_planta_le_o_calculo(self):
        """Terças, correntes, perfil e vãos do X de cobertura vêm dos elementos."""
        p = _projeto_com(
            GALPOES[1][1],
            ("Terça", "Ue 200×75×20×2,65",
             {"linhas": 8, "espacamento_m": 1.3714, "recuo_beiral_m": 0.2,
              "recuo_cumeeira_m": 0.25, "n_correntes": 2}),
            ("Contraventamento de cobertura", "Barra redonda ø 22 mm",
             {"paineis": 6, "vaos_contraventados": [1, 8], "quantidade": 24}))
        doc = _gravar_e_ler(desenhos.planta_cobertura(p), self.pasta, "planta_calc")
        txt = _textos(doc)
        self.assertTrue(any("tirante %%c22,2 mm" in t for t in txt), "perfil do CC")
        self.assertFalse(any("%%c20 mm" in t for t in txt), "sobrou o padrao de 20 mm")
        self.assertTrue(any("6 paineis" in t for t in txt))
        self.assertTrue(any("16 linhas a cada 1371 mm" in t for t in txt))
        self.assertTrue(any("2 linha(s) por vao" in t for t in txt))
        self.assertIn("CC-8", txt)
        self.assertNotIn("CC-4", txt)


# ---------------------------------------------------------------- 3. elevação

class TestElevacaoLongitudinal(_Base):

    def test_elevacao(self):
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                doc = _gravar_e_ler(desenhos.elevacao_longitudinal(dg), self.pasta,
                                    f"elev_{dg.nome}")
                self.conferir(doc, ["ACO", "ACO-FINO", "COTA", "TEXTO", "EIXO",
                                    "CONCRETO"], rotulo)
                C = dg.comprimento * 1000.0
                cx = _caixa(doc, {"ACO", "ACO-FINO"})
                self.assertAlmostEqual((cx[2] - cx[0]) / C, 1.0, delta=0.03, msg=rotulo)

                txt = _textos(doc)
                self.assertTrue(any(f"{C:.0f}" in t for t in txt), rotulo)
                self.assertTrue(any(f"{dg.pe_direito * 1000:.0f}" in t for t in txt),
                                rotulo)
                self.assertTrue(any("LONGARINA" in t for t in txt), rotulo)
                self.assertTrue(any("CONTRAVENTAMENTO" in t for t in txt), rotulo)

    def test_contraventamento_vertical_segue_o_calculo(self):
        """Tirante: chamada com ø e esticador, sem a nota de flambagem; cantoneira: o
        perfil L com gussets e a nota do cruzamento."""
        geo = {"vaos_contraventados": [1, 8], "quantidade": 8}
        tir = _projeto_com(GALPOES[1][1],
                           ("Contraventamento vertical", "Barra redonda ø 16 mm", geo))
        doc = _gravar_e_ler(desenhos.elevacao_longitudinal(tir), self.pasta, "elev_tir")
        txt = _textos(doc)
        self.assertTrue(any("TIRANTE %%c16 mm" in t for t in txt))
        self.assertTrue(any("esticador" in t for t in txt))
        self.assertTrue(any("so a tracao" in t for t in txt))
        self.assertFalse(any("flambagem" in t for t in txt))
        self.assertFalse(any('L 3"' in t for t in txt), "sobrou a cantoneira padrao")
        self.assertIn("CV-8", txt)
        self.assertNotIn("CV-4", txt)

        cant = _projeto_com(GALPOES[1][1],
                            ("Contraventamento vertical", 'L 3"×1/4"', geo))
        doc = _gravar_e_ler(desenhos.elevacao_longitudinal(cant), self.pasta, "elev_L")
        txt = _textos(doc)
        self.assertTrue(any('L 3"x1/4"' in t for t in txt))
        self.assertTrue(any("gussets" in t for t in txt))
        self.assertTrue(any("flambagem" in t for t in txt))


# ---------------------------------------------------------------- 4 e 5. ligações

class TestLigacoes(_Base):

    def test_ligacao_viga_pilar_com_projeto(self):
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                doc = _gravar_e_ler(desenhos.ligacao_viga_pilar(dg), self.pasta,
                                    f"joelho_{dg.nome}")
                self.conferir(doc, ["ACO", "COTA", "TEXTO", "FURO", "PARAFUSO",
                                    "SOLDA", "HACHURA", "OCULTA"], rotulo)
                txt = _textos(doc)
                self.assertTrue(any("PARAFUSOS" in t for t in txt), rotulo)
                self.assertTrue(any("hb =" in t for t in txt), rotulo)
                self.assertTrue(any(t.startswith("CH ") for t in txt), rotulo)
                # 8 furos na vista da chapa (4 fileiras de 2)
                furos = [e for e in doc["entidades"]
                         if e["tipo"] == "CIRCLE" and e.get("camada") == "FURO"]
                self.assertEqual(len(furos), 8, rotulo)

    def test_ligacao_viga_pilar_com_dicionario_minimo(self):
        d = desenhos.ligacao_viga_pilar({"perfil_pilar": "W 410×46,1",
                                         "perfil_viga": "W 360×32,9",
                                         "com_misula": False, "inclinacao": 10.0})
        doc = _gravar_e_ler(d, self.pasta, "joelho_dict")
        self.conferir(doc, ["ACO", "COTA", "TEXTO", "FURO", "PARAFUSO", "SOLDA"])
        self.assertFalse(any("MISULA" in t for t in _textos(doc)))

    def test_ligacao_cumeeira(self):
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                doc = _gravar_e_ler(desenhos.ligacao_cumeeira(dg), self.pasta,
                                    f"cumeeira_{dg.nome}")
                self.conferir(doc, ["ACO", "COTA", "TEXTO", "FURO", "PARAFUSO",
                                    "SOLDA", "HACHURA"], rotulo)
                txt = _textos(doc)
                self.assertTrue(any("CH " in t for t in txt), rotulo)
                self.assertTrue(any("%%d" in t or "%" in t for t in txt),
                                f"{rotulo}: falta a inclinacao do telhado")
                furos = [e for e in doc["entidades"]
                         if e["tipo"] == "CIRCLE" and e.get("camada") == "FURO"]
                self.assertEqual(len(furos), 8, rotulo)

    def test_chapa_de_topo_cresce_com_a_viga(self):
        alturas = []
        for _, dg in GALPOES:
            d = desenhos.ligacao_cumeeira(dg)
            doc = _gravar_e_ler(d, self.pasta, f"chapa_{dg.nome}")
            txt = [t for t in _textos(doc) if t.startswith("2 CH ")]
            self.assertTrue(txt)
            alturas.append(float(txt[0].split(" x ")[1]))
        self.assertTrue(alturas[0] < alturas[2],
                        "a chapa de topo devia crescer com a altura da viga")


# ---------------------------------------------------------------- 6. base

class TestBasePilar(_Base):

    def test_base_com_projeto(self):
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                doc = _gravar_e_ler(desenhos.base_pilar(dg), self.pasta,
                                    f"base_{dg.nome}")
                self.conferir(doc, ["ACO", "COTA", "TEXTO", "CONCRETO", "FURO",
                                    "PARAFUSO", "HACHURA", "EIXO"], rotulo)
                txt = _textos(doc)
                self.assertTrue(any("PLACA DE BASE" in t for t in txt), rotulo)
                self.assertTrue(any("CHUMBADORES" in t for t in txt), rotulo)
                self.assertTrue(any("GROUT" in t for t in txt), rotulo)
                self.assertTrue(any(t.startswith("B = ") for t in txt), rotulo)
                self.assertTrue(any(t.startswith("L = ") for t in txt), rotulo)
                self.assertTrue(any("gabarito" in t for t in txt), rotulo)

    def test_numero_de_chumbadores_segue_o_tipo_de_base(self):
        rot = desenhos.base_pilar(GALPOES[1][1])       # rotulada
        eng = desenhos.base_pilar(GALPOES[2][1])       # engastada
        d_rot = _gravar_e_ler(rot, self.pasta, "base_rotulada")
        d_eng = _gravar_e_ler(eng, self.pasta, "base_engastada")
        n_rot = len([e for e in d_rot["entidades"]
                     if e["tipo"] == "CIRCLE" and e.get("camada") == "FURO"])
        n_eng = len([e for e in d_eng["entidades"]
                     if e["tipo"] == "CIRCLE" and e.get("camada") == "FURO"])
        self.assertEqual(n_rot, 2)
        self.assertEqual(n_eng, 4)
        self.assertTrue(any("rotulada" in t.lower() for t in _textos(d_rot)))
        self.assertTrue(any("engastada" in t.lower() for t in _textos(d_eng)))

    def test_furos_dentro_da_placa(self):
        """Os chumbadores têm que caber na placa, inclusive na base engastada."""
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                doc = _gravar_e_ler(desenhos.base_pilar(dg), self.pasta,
                                    f"furos_{dg.nome}")
                txt = _textos(doc)
                B = float([t for t in txt if t.startswith("B = ")][0][4:])
                L = float([t for t in txt if t.startswith("L = ")][0][4:])
                # a planta é o bloco de ACO mais à direita; basta comparar tamanhos
                furos = [e for e in doc["entidades"]
                         if e["tipo"] == "CIRCLE" and e.get("camada") == "FURO"]
                xs = [e[10] for e in furos]
                ys = [e[20] for e in furos]
                self.assertLessEqual(max(xs) - min(xs), B - 60.0, rotulo)
                self.assertLessEqual(max(ys) - min(ys), L - 60.0, rotulo)

    def test_base_com_dicionario_minimo(self):
        d = desenhos.base_pilar({"perfil_pilar": "W 310×38,7", "placa_B": 320.0,
                                 "placa_L": 380.0, "placa_t": 16.0,
                                 "rotulada": True})
        doc = _gravar_e_ler(d, self.pasta, "base_dict")
        self.conferir(doc, ["ACO", "COTA", "TEXTO", "CONCRETO", "FURO"])
        self.assertTrue(any("B = 320" in t for t in _textos(doc)))


# ---------------------------------------------------------------- 7. terça

class TestDetalheTerca(_Base):

    def test_terca(self):
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                doc = _gravar_e_ler(desenhos.detalhe_terca(dg), self.pasta,
                                    f"terca_det_{dg.nome}")
                self.conferir(doc, ["ACO", "COTA", "TEXTO", "FURO", "PARAFUSO",
                                    "SOLDA", "HACHURA", "EIXO"], rotulo)
                txt = _textos(doc)
                self.assertTrue(any("OBLONGO" in t for t in txt), rotulo)
                self.assertTrue(any("ESTICADOR" in t for t in txt), rotulo)
                self.assertTrue(any("CHAPA DOBRADA" in t for t in txt), rotulo)
                self.assertTrue(any("hch =" in t for t in txt), rotulo)
                self.assertTrue(any("CORRENTE" in t for t in txt), rotulo)

    def test_altura_da_chapa_entre_70_e_80_por_cento_da_terca(self):
        dg = GALPOES[1][1]
        doc = _gravar_e_ler(desenhos.detalhe_terca(dg), self.pasta, "terca_hch")
        hch = float([t for t in _textos(doc) if t.startswith("hch =")][0].split("= ")[1])
        ht = desenhos._Geo(dg).terca.d
        self.assertGreaterEqual(hch / ht, 0.68)
        self.assertLessEqual(hch / ht, 0.82)

    def test_terca_com_dicionario_minimo(self):
        d = desenhos.detalhe_terca({"perfil_terca": "Ue 250×85×25×3,00",
                                    "perfil_viga": "W 410×46,1",
                                    "d_parafuso": 15.875})
        doc = _gravar_e_ler(d, self.pasta, "terca_dict")
        self.conferir(doc, ["ACO", "COTA", "TEXTO", "FURO", "PARAFUSO", "SOLDA"])


# ---------------------------------------------------------------- 8. contraventamento

class TestContraventamento(_Base):

    def test_no_tirante(self):
        """Sem o cálculo vale o padrão, que é a solução do cálculo: tirante ø 20 mm."""
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                doc = _gravar_e_ler(desenhos.detalhe_contraventamento(dg), self.pasta,
                                    f"cv_{dg.nome}")
                self.conferir(doc, ["ACO", "COTA", "TEXTO", "PARAFUSO", "SOLDA",
                                    "EIXO", "OCULTA", "HACHURA"], rotulo)
                txt = _textos(doc)
                for termo in ("PONTO DE TRABALHO", "GUSSET", "ORELHA",
                              "TIRANTE %%c20 mm", "ESTICADOR", "CONTRAPORCA",
                              "ROSCA M20", "FURO %%c22", "ESCORA", "CORTE B-B"):
                    self.assertTrue(any(termo in t for t in txt), f"{rotulo}: falta {termo}")
                self.assertFalse(any("parafusos %%c" in t for t in txt),
                                 f"{rotulo}: sobrou a ligacao parafusada de cantoneira")

    def test_no_segue_o_perfil_do_calculo(self):
        geo = {"paineis": 4, "vaos_contraventados": [1, 8], "quantidade": 16}
        tir = _projeto_com(GALPOES[1][1],
                           ("Contraventamento de cobertura", "Barra redonda ø 25 mm", geo))
        txt = _textos(_gravar_e_ler(desenhos.detalhe_contraventamento(tir), self.pasta,
                                    "cv_tir25"))
        self.assertTrue(any("TIRANTE %%c25,4 mm" in t for t in txt))
        self.assertTrue(any('ROSCA 1" UNC' in t for t in txt))

        cant = _projeto_com(GALPOES[1][1],
                            ("Contraventamento de cobertura", 'L 2"×3/16"', geo))
        doc = _gravar_e_ler(desenhos.detalhe_contraventamento(cant), self.pasta, "cv_L")
        self.assertTrue(any("DIAGONAIS  L 2" in t for t in _textos(doc)))
        # 2 diagonais x 2 parafusos = 4 furos
        furos = [e for e in doc["entidades"]
                 if e["tipo"] == "CIRCLE" and e.get("camada") == "FURO"]
        self.assertEqual(len(furos), 4)

    def test_no_com_dicionario_minimo(self):
        d = desenhos.detalhe_contraventamento({"perfil_viga": "W 310×38,7",
                                               "perfil_diagonal": 'L 2½"×1/4"',
                                               "angulo": 40.0, "n_parafusos": 3})
        doc = _gravar_e_ler(d, self.pasta, "cv_dict")
        self.conferir(doc, ["ACO", "COTA", "TEXTO", "FURO", "PARAFUSO"])
        furos = [e for e in doc["entidades"]
                 if e["tipo"] == "CIRCLE" and e.get("camada") == "FURO"]
        self.assertEqual(len(furos), 6)


# ---------------------------------------------------------------- 9. seção de perfil

class TestDesenharPerfil(_Base):

    NOMES = ["W 360×44,6", 'U 8"×17,1', "Ue 200×75×20×2,65", 'L 3"×1/4"',
             'TC 88,9×3,2 (3")', "TQ 100×100×4,0"]

    def test_cada_tipo_de_perfil(self):
        for nome in self.NOMES:
            with self.subTest(nome):
                p = banco()[nome]
                d = desenhos.desenhar_perfil(p)
                doc = _gravar_e_ler(d, self.pasta,
                                    "perfil_" + nome.replace("/", "_")
                                    .replace('"', "").replace("×", "x")
                                    .replace(" ", "").replace(",", "")
                                    .replace("(", "").replace(")", ""))
                self.conferir(doc, ["ACO", "HACHURA", "COTA", "TEXTO", "EIXO"], nome)

                g = desenhos._dims_perfil(p)
                cx = _caixa(doc, {"ACO"})
                self.assertAlmostEqual(cx[3] - cx[1], g["h"], delta=1.0, msg=nome)
                self.assertAlmostEqual(cx[2] - cx[0], g["b"], delta=1.0, msg=nome)

                txt = _textos(doc)
                self.assertIn(f"{g['h']:.0f}", txt, f"{nome}: falta a cota de altura")
                self.assertIn(f"{g['b']:.0f}", txt, f"{nome}: falta a cota de largura")
                self.assertTrue(any(nome.split()[0] in t for t in txt),
                                f"{nome}: falta o nome do perfil")

    def test_barra_redonda_do_calculo(self):
        """"Barra redonda ø N mm" não está no catálogo: não pode virar outro perfil."""
        p = desenhos._perfil("Barra redonda ø 20 mm")
        self.assertEqual(p.tipo, "barra")
        self.assertAlmostEqual(desenhos._perfil("Barra redonda ø 13 mm").d, 12.7)
        doc = _gravar_e_ler(desenhos.desenhar_perfil(p), self.pasta, "perfil_barra")
        self.assertTrue({"ACO", "HACHURA", "COTA", "TEXTO"} <= _camadas_usadas(doc))
        self.assertIn("%%c20", _textos(doc))
        cx = _caixa(doc, {"ACO"})
        self.assertAlmostEqual(cx[2] - cx[0], 20.0, delta=0.5)

    def test_secoes_mostram_os_tirantes(self):
        doc = _gravar_e_ler(desenhos.secoes_perfis(GALPOES[1][1]), self.pasta, "secoes")
        txt = _textos(doc)
        self.assertTrue(any(t.startswith("Barra redonda") for t in txt))
        self.assertNotIn("W 310x38,7", txt, "tirante caiu no perfil de reserva")

    def test_sem_corte_nao_hachura(self):
        d = desenhos.desenhar_perfil("W 360×44,6", corte=False)
        doc = _gravar_e_ler(d, self.pasta, "perfil_sem_corte")
        self.assertNotIn("HACHURA", _camadas_usadas(doc))

    def test_aceita_nome_ou_objeto_e_posicao(self):
        d1 = desenhos.desenhar_perfil("W 360×44,6", 0.0, 0.0)
        d2 = desenhos.desenhar_perfil(banco()["W 360×44,6"], 1000.0, 500.0)
        self.assertAlmostEqual(d2.largura, d1.largura, delta=1.0)
        self.assertAlmostEqual(d2.extremos[0] - d1.extremos[0], 1000.0, delta=1.0)

    def test_reaproveitamento_num_mesmo_desenho(self):
        d = Desenho("quadro")
        desenhos.desenhar_perfil("W 360×44,6", 0.0, 0.0, desenho=d)
        n1 = len(d.entidades)
        desenhos.desenhar_perfil("Ue 200×75×20×2,65", 800.0, 0.0, desenho=d)
        self.assertGreater(len(d.entidades), n1)


# ---------------------------------------------------------------- 10. gerar_todos

class TestGerarTodos(_Base):

    def test_gera_todos_os_arquivos(self):
        for rotulo, dg in GALPOES:
            with self.subTest(rotulo):
                destino = os.path.join(self.pasta, f"todos_{dg.nome}")
                itens = desenhos.gerar_todos(dg, destino)
                self.assertEqual(len(itens), len(desenhos.CATALOGO), rotulo)
                nomes = [i["nome"] for i in itens]
                self.assertIn("01-PORTICO", nomes)
                self.assertIn("06-BASE-PILAR", nomes)
                for item in itens:
                    self.assertTrue(os.path.isfile(item["arquivo"]), item["nome"])
                    self.assertTrue(item["titulo"], item["nome"])
                    self.assertTrue(item["escala"].startswith("1:"), item["nome"])
                    self.assertGreater(item["largura_mm"], 0.0, item["nome"])
                    doc = ler_dxf(item["arquivo"])
                    self.assertEqual(_numeros_finitos(doc), [], item["nome"])
                    self.assertIn("ACO", _camadas_usadas(doc))
                    self.assertIn("TEXTO", _camadas_usadas(doc))

    def test_aceita_dicionario_de_geometria(self):
        destino = os.path.join(self.pasta, "todos_dict")
        itens = desenhos.gerar_todos({"vao": 15.0, "comprimento": 30.0,
                                      "pe_direito": 5.5, "inclinacao": 10.0}, destino)
        self.assertEqual(len(itens), len(desenhos.CATALOGO))
        doc = ler_dxf([i for i in itens if i["nome"] == "01-PORTICO"][0]["arquivo"])
        self.assertTrue(any("15000" in t for t in _textos(doc)))


# ---------------------------------------------------------------- robustez

class TestRobustez(_Base):

    def test_nenhum_desenho_tem_coordenada_absurda(self):
        """Nada pode escapar de um envelope compatível com a escala do desenho."""
        limites = {"01-PORTICO": 2.0e5, "02-PLANTA-COBERTURA": 3.0e5,
                   "03-ELEVACAO-LONGITUDINAL": 3.0e5}
        destino = os.path.join(self.pasta, "envelope")
        for item in desenhos.gerar_todos(GALPOES[2][1], destino):
            doc = ler_dxf(item["arquivo"])
            lim = limites.get(item["nome"], 5.0e4)
            for x, y in _pontos(doc):
                self.assertLess(abs(x), lim, f"{item['nome']}: x fora de escala")
                self.assertLess(abs(y), lim, f"{item['nome']}: y fora de escala")

    def test_perfil_desconhecido_nao_quebra_o_desenho(self):
        d = desenhos.ligacao_viga_pilar({"perfil_pilar": "PERFIL INEXISTENTE",
                                         "perfil_viga": "W 360×32,9"})
        doc = _gravar_e_ler(d, self.pasta, "perfil_invalido")
        self.assertEqual(_numeros_finitos(doc), [])

    def test_inclinacao_pequena_e_grande(self):
        for incl in (2.0, 10.0, 40.0):
            with self.subTest(incl=incl):
                dg = DadosGalpao(vao=20.0, comprimento=40.0, inclinacao=incl)
                doc = _gravar_e_ler(desenhos.portico(dg), self.pasta,
                                    f"incl_{incl:.0f}")
                self.assertEqual(_numeros_finitos(doc), [])
                hc = dg.altura_cumeeira * 1000.0
                self.assertTrue(any(f"{hc:.0f}" in t for t in _textos(doc)))


class TestIntegracaoComONucleo(_Base):
    """A geometria calculada por `nucleo.ligacoes` e `nucleo.bases` (em cm) tem que
    chegar ao desenho (em mm) sem troca de unidade."""

    def test_chapa_de_topo_do_nucleo(self):
        try:
            from nucleo import ligacoes as lig
        except ImportError:
            self.skipTest("nucleo.ligacoes ainda nao disponivel")
        from nucleo.perfis import perfil
        from nucleo.modelo_galpao import ProjetoGalpao

        r = lig.chapa_de_topo(perfil("W 360×32,9"), M_Sd=19010.0, V_Sd=59.3,
                              N_Sd=27.8, t_chapa=2.24, gabarito=10.0,
                              pilar=perfil("W 360×44,6"))
        v = desenhos._ligacao_do_resultado(r)
        self.assertAlmostEqual(v["chapa_esp"], r.dados["t_chapa"] * 10, places=3)
        self.assertAlmostEqual(v["gabarito"], r.dados["gabarito"] * 10, places=3)
        self.assertAlmostEqual(v["d_parafuso"], 19.05, places=2)

        p = ProjetoGalpao(dados=GALPOES[1][1])
        p.ligacoes["viga-pilar"] = r
        doc = _gravar_e_ler(desenhos.ligacao_viga_pilar(p), self.pasta, "int_joelho")
        self.conferir(doc, ["ACO", "COTA", "FURO", "PARAFUSO", "SOLDA"])
        # a chapa desenhada é a chapa calculada
        txt = [t for t in _textos(doc) if t.startswith("CH ")][0]
        self.assertIn(f"{r.dados['largura_chapa'] * 10:.0f}", txt)

    def test_base_do_nucleo(self):
        try:
            from nucleo import bases
        except ImportError:
            self.skipTest("nucleo.bases ainda nao disponivel")
        from nucleo.perfis import perfil
        from nucleo.modelo_galpao import ProjetoGalpao

        b = bases.dimensionar_base(perfil("W 360×44,6"), N_Sd=33.9, M_Sd=0.0,
                                   H_Sd=41.5, N_Sd_min=-61.8, n_chumbadores=2)
        v = desenhos._base_do_resultado(b)
        geo = b.dados["geometria"]
        self.assertAlmostEqual(v["placa_B"], geo["B_mm"], places=3)
        self.assertAlmostEqual(v["placa_L"], geo["L_mm"], places=3)
        self.assertAlmostEqual(v["placa_t"], geo["t_mm"], places=3)
        self.assertEqual(v["n_chumbadores"], 2)

        p = ProjetoGalpao(dados=GALPOES[1][1])
        p.base = b
        doc = _gravar_e_ler(desenhos.base_pilar(p), self.pasta, "int_base")
        self.conferir(doc, ["ACO", "COTA", "CONCRETO", "FURO", "PARAFUSO"])
        txt = _textos(doc)
        self.assertTrue(any(f"B = {geo['B_mm']:.0f}" == t for t in txt),
                        "a placa desenhada nao e a placa calculada")


if __name__ == "__main__":
    unittest.main(verbosity=2)
