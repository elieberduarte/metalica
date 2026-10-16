# -*- coding: utf-8 -*-
"""Regressões do desenho "completo" (testes/REGRESSOES.md, seção Desenho completo, 16/10/2026).

1. A planta em 1:125 (ou a localização da metálica em 1:150) entrava no completo em 1:25 com o que é de papel do mesmo
   tamanho em mm de papel: as marcas, os nomes dos eixos e as cotas saíam 5× menores — tracinhos no CAD.
2. "A prancha do 2D gerada pelo detalhamento do pré-fabricado precisaria abrir o projeto completo": o pré-moldado não
   tinha completo; agora tem, com todos os desenhos do pré-moldado do projeto — detalhar uma família só não o deixa
   pela metade.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app  # noqa: E402
from nucleo2d.desenho import Chamada, Cota, Desenho, Hachura, Linha, Texto  # noqa: E402
from nucleo2d.detalhar import _anexar_quadro  # noqa: E402
from nucleo2d.detalhe import premoldado_formas as PF  # noqa: E402
from projetos import Projetos  # noqa: E402
from test_formas_premoldado import _modelo  # noqa: E402


def _banda(escala, nome="planta"):
    b = Desenho(nome=nome, escala=escala)
    b.add(Linha(a=(0.0, 0.0), b=(10000.0, 0.0)))
    b.add(Texto(posicao=(0.0, 100.0), texto="P1", altura=2.5))
    b.add(Cota(p1=(0.0, 0.0), p2=(10000.0, 0.0), modo="h"))
    b.add(Chamada(alvo=(0.0, 0.0), posicao=(500.0, 500.0), texto="VL1", altura=2.5))
    b.add(Hachura(contornos=[[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]], espacamento=2.5))
    return b


def _copiadas(dc, tipo):
    """as entidades que vieram da banda (o título do quadro, "PLANTA", fica de fora)"""
    return [e for e in dc.entidades.values() if isinstance(e, tipo) and (e.atributos or {}).get("faixa") == "PLANTA"
            and getattr(e, "texto", None) != "PLANTA"]


class TestPapelNaEscalaDoCompleto(unittest.TestCase):
    def test_planta_em_1_125_no_completo_em_1_25_fica_do_mesmo_tamanho_na_folha(self):
        dc = Desenho(nome="completo", escala=25.0)
        _anexar_quadro(dc, _banda(125.0), "PLANTA", 0.0)
        self.assertEqual([t.altura for t in _copiadas(dc, Texto)], [12.5])
        self.assertEqual([c.fator for c in _copiadas(dc, Cota)], [5.0])
        self.assertEqual([c.altura for c in _copiadas(dc, Chamada)], [12.5])
        self.assertEqual([h.espacamento for h in _copiadas(dc, Hachura)], [12.5])

    def test_mesma_escala_nao_muda(self):
        dc = Desenho(nome="completo", escala=25.0)
        _anexar_quadro(dc, _banda(25.0), "PLANTA", 0.0)
        self.assertEqual([t.altura for t in _copiadas(dc, Texto)], [2.5])
        self.assertEqual([c.fator for c in _copiadas(dc, Cota)], [None])

    def test_a_banda_original_nao_muda(self):
        b = _banda(125.0)
        _anexar_quadro(Desenho(nome="completo", escala=25.0), b, "PLANTA", 0.0)
        self.assertEqual([e.altura for e in b.entidades.values() if isinstance(e, Texto)], [2.5])


class TestCompletoDoPreMoldado(unittest.TestCase):
    def test_quadros_na_ordem_conjunto_e_depois_formas(self):
        doc = _modelo()
        reps = PF.agrupar(PF.pecas_do_modelo(doc))
        ds = list(PF.desenhos(doc, reps=reps).values()) + list(PF.desenhos_gerais(doc, reps, ["locacao"]).values())
        c = PF.desenho_completo(ds[::-1])
        self.assertEqual(c.nome, "pré-moldado – completo")
        quadros = [e.atributos["quadro"] for e in c.entidades.values() if (e.atributos or {}).get("quadro")]
        self.assertEqual(quadros[0], "PLANTA DE LOCAÇÃO DOS PILARES")
        self.assertIn("PILARES E VIGAS", quadros)
        self.assertLess(quadros.index("PILARES E VIGAS"), quadros.index("FUNDAÇÕES"))
        self.assertEqual(c.metadados["premoldado"]["completo"][0], "locacao")

    def test_sem_desenho_nao_ha_completo(self):
        self.assertIsNone(PF.desenho_completo([]))


class TestFormasRevisadas(unittest.TestCase):
    """A revisão das fôrmas do Mercado Conceito no CAD (16/10)."""

    def test_facetas_do_circulo_viram_um_intervalo_e_o_chanfro_sozinho_fica(self):
        # o furo da estaca no bloco visto de lado: 200 | 22 | 4 | 6 | 5 ... | 212 → 200 | 388 | 212
        pts = [0, 200, 222, 229, 235, 241, 250, 300, 360, 420, 480, 540, 588, 800]
        self.assertEqual(PF._sem_facetas(pts, 100.0), [0, 200, 588, 800])
        # um chanfro de 15 mm entre intervalos grandes não é faceta
        self.assertEqual(PF._sem_facetas([0, 15, 600, 1200], 100.0), [0, 15, 600, 1200])
        # dois miúdos seguidos (um dente) também ficam
        self.assertEqual(PF._sem_facetas([0, 50, 100, 900], 100.0), [0, 50, 100, 900])

    def test_bloco_com_furo_redondo_sem_numeros_empilhados(self):
        import math
        from nucleo3d.modelo import Documento
        from test_formas_premoldado import _caixa
        doc = Documento()
        bloco = _caixa("Bloco", 0, 0, -600, 1700, 800, 0)
        # o furo da estaca: um prisma de 24 lados a mais no fundo do bloco (as facetas que viravam cota)
        n, r, cx, cy = 24, 300.0, 850.0, 400.0
        base = len(bloco.vertices)
        vs = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n), z) for z in (-600.0, -300.0) for k in range(n)]
        bloco.vertices = list(bloco.vertices) + vs
        bloco.faces = list(bloco.faces) + [[base + k, base + (k + 1) % n, base + n + (k + 1) % n, base + n + k] for k in range(n)]
        doc.add(bloco)
        d = list(PF.desenhos(doc).values())[0]
        cotas = [e for e in d.entidades.values() if isinstance(e, Cota)]
        miudas = [c for c in cotas if c.valor() < PF.MIUDO_PAPEL * d.escala]
        # sem a correção, 18 cotas miúdas (as facetas, empilhadas); com ela, as 4 da silhueta do furo, isoladas
        self.assertLessEqual(len(miudas), 4, sorted(round(c.valor()) for c in miudas))

    def test_cotas_da_lateral_nao_entram_na_elevacao(self):
        from nucleo2d.detalhar import _extremos_de
        from nucleo3d.modelo import Documento, Solido
        # a viga L de 3,25 m (como a aba ABVL1): a lateral tem degrau, então leva cadeia e total à esquerda
        L = 3250.0
        sec = [(0, 0), (100, 0), (100, 75), (50, 75), (50, 150), (0, 150)]                # (y, z), a seção da aba
        vs = [(x, y, z) for x in (0.0, L) for (y, z) in sec]
        n = len(sec)
        fs = [list(range(n))[::-1], [n + k for k in range(n)]] + [[k, (k + 1) % n, n + (k + 1) % n, n + k] for k in range(n)]
        doc = Documento()
        doc.add(Solido(nome="Viga L", camada="200 Pré-Fabricado", material="CONCRETE/Fck-40", vertices=vs, faces=fs,
                       atributos={"propriedades": {"Pset_BeamCommon": {"Reference": "VL9"}}, "marcas": {"perfil": "Viga L"}}))
        d = PF.desenhos(doc)["pilares_vigas"]
        cotas_lat = [e for e in d.entidades.values() if isinstance(e, Cota) and e.modo == "v" and e.p1[0] > L]
        self.assertGreaterEqual(len(cotas_lat), 3)                     # a cadeia (75 + 75) e a total
        # a linha de cota (o deslocamento é de papel; positivo = à esquerda, subindo) e o número posto para fora: o CAD
        # desenha o número girado em volta da linha, e na seção de 150 mm ele não cabe entre as pontas — sobrava
        # 175 mm (7 mm de papel) até a ponta da elevação e o "150" caía em cima dela (ABVL1 do Mercado, 16/10)
        xs = [c.p1[0] - c.deslocamento * d.escala * (c.fator or 1.0) for c in cotas_lat]
        xs += [c.texto_pos[0] for c in cotas_lat if c.texto_pos]
        livre = (min(xs) - L) / d.escala
        self.assertGreaterEqual(livre, 8.0, "só %.1f mm de papel entre a elevação e a cota da vista lateral" % livre)
        self.assertGreater(min(q[0] for c in cotas_lat for q in _extremos_de(c, d.escala)), L)

    def test_capa_moldada_no_local_nao_vira_celula_de_forma(self):
        from test_formas_premoldado import _caixa
        doc = _modelo()
        doc.add(_caixa("CAPA", 0, 0, 5000, 54000, 53000, 5050))
        doc.add(_caixa("Laje Alveolar", 0, 0, 4800, 1250, 8000, 5000, "LA1"))
        d = PF.desenhos(doc, ["lajes"])["lajes"]
        textos = [e.texto for e in d.entidades.values() if isinstance(e, Texto)]
        self.assertTrue(any(t.startswith("LA1") for t in textos))
        self.assertFalse(any("CAPA" in t for t in textos), [t for t in textos if "CAPA" in t])


class TestRotaMontaOCompletoComTudo(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="regr_completo_")
        self.antigo = app.PROJETOS
        app.PROJETOS = self.pasta
        self.g = Projetos(self.pasta)
        self.s = self.g.criar("Pré", tipo="ifc")["slug"]
        json.dump(_modelo().dict(), open(os.path.join(self.pasta, self.s, "modelo.json"), "w", encoding="utf-8"))

    def tearDown(self):
        app.PROJETOS = self.antigo

    def _quadros(self):
        d = self.g.abrir_desenho(self.s, "pré-moldado – completo")
        ents = d["entidades"].values() if isinstance(d["entidades"], dict) else d["entidades"]
        return {e["atributos"]["quadro"] for e in ents if (e.get("atributos") or {}).get("quadro")}

    def test_detalhar_uma_familia_so_mantem_as_outras_no_completo(self):
        r = app.detalhar_premoldado(self.s, {"familias": ["pilares_vigas", "fundacoes"], "gerais": []})
        self.assertIn("completo", [d["familia"] for d in r["desenhos"]])
        self.assertTrue({"PILARES E VIGAS", "FUNDAÇÕES"} <= self._quadros())
        app.detalhar_premoldado(self.s, {"familias": ["fundacoes"], "gerais": []})
        self.assertTrue({"PILARES E VIGAS", "FUNDAÇÕES"} <= self._quadros())


if __name__ == "__main__":
    unittest.main()
