# -*- coding: utf-8 -*-
"""Testes da geometria 3D (`nucleo3d.geometria`).

O teste que pega erro de geometria é o primeiro: a área do contorno de **todos** os
perfis do catálogo tem de bater com a área tabelada dentro de 3 %. Depois vêm a
extrusão (volume = área × comprimento), o peso, a qualidade da malha (faces planas,
área positiva, malha fechada com normais para fora), o push/pull, o offset e as
demais operações de edição.
"""
import math
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from nucleo.base import ErroDeDados                               # noqa: E402
from nucleo.perfis import banco                                   # noqa: E402
from nucleo3d import geometria as g                               # noqa: E402
from nucleo3d.modelo import Barra, Chapa, Solido                  # noqa: E402

TIPOS = ("I", "U", "L", "Ue", "tubo")
TODOS = [p for t in TIPOS for p in banco().lista(t)]

#: Direções de teste: vertical (a singularidade do vetor auxiliar), horizontal ao
#: longo de X e oblíqua qualquer.
ORIENTACOES = (((0, 0, 0), (0, 0, 6000), 90.0),
               ((0, 0, 0), (5000, 0, 0), 0.0),
               ((100, -200, 50), (3100, 3800, 2050), 30.0))


def _cubo(a=100.0) -> Solido:
    return Solido(vertices=[(0, 0, 0), (a, 0, 0), (a, a, 0), (0, a, 0),
                            (0, 0, a), (a, 0, a), (a, a, a), (0, a, a)],
                  faces=[[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5],
                         [2, 3, 7, 6], [3, 0, 4, 7]])


def _arestas_orientadas_ok(faces) -> bool:
    """Malha fechada e orientada: cada aresta aparece uma vez em cada sentido."""
    cont = {}
    for f in faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            cont[(a, b)] = cont.get((a, b), 0) + 1
    return all(n == 1 and cont.get((b, a), 0) == 1 for (a, b), n in cont.items())


def _conferir_solido(caso, vertices, faces, rotulo=""):
    """Faces planas, área positiva, malha fechada e normais para fora."""
    for v in vertices:
        caso.assertTrue(all(math.isfinite(c) for c in v), f"{rotulo}: NaN/inf")
    for f in faces:
        pts = [vertices[i] for i in f]
        caso.assertGreater(g.area_face(pts), 1e-9, f"{rotulo}: face de área nula {f}")
    diag = g.conferir_malha(vertices, faces)
    caso.assertTrue(diag["fechada"], f"{rotulo}: malha aberta {diag['arestas_soltas'][:5]}")
    caso.assertLess(diag["planicidade"], 1e-6, f"{rotulo}: face fora do plano")
    caso.assertTrue(_arestas_orientadas_ok(faces), f"{rotulo}: orientação inconsistente")
    # soma de tetraedros com sinal > 0 só acontece com todas as normais para fora
    caso.assertGreater(g.volume_malha(vertices, faces), 0.0, f"{rotulo}: normais para dentro")


class TestSecoes(unittest.TestCase):

    def test_area_de_todos_os_perfis_do_catalogo(self):
        """Área do contorno (externo menos furo) × área de catálogo, dentro de 3 %."""
        self.assertGreaterEqual(len(TODOS), 120)
        erros = []
        for p in TODOS:
            a = g.area_secao(p) / 100.0                          # mm² -> cm²
            e = abs(a / p.A - 1.0)
            if e > 0.03:
                erros.append(f"{p.nome}: contorno {a:.2f} cm² × catálogo {p.A:.2f} cm²")
        self.assertEqual(erros, [])

    def test_secao_centrada_no_centroide(self):
        for p in TODOS:
            ext, furos = g.secao_com_furos(p)
            a_ext = g.area_assinada(ext)
            cx, cy = g.centroide_contorno(ext)
            sx, sy, at = a_ext * cx, a_ext * cy, a_ext
            for f in furos:
                af = -abs(g.area_assinada(f))
                fx, fy = g.centroide_contorno(f)
                sx, sy, at = sx + af * fx, sy + af * fy, at + af
            self.assertAlmostEqual(sx / at, 0.0, delta=1e-6, msg=p.nome)
            self.assertAlmostEqual(sy / at, 0.0, delta=1e-6, msg=p.nome)

    def test_orientacao_e_dimensoes(self):
        """Externo anti-horário, furo horário; envolvente = bf × d do catálogo."""
        for p in TODOS:
            ext, furos = g.secao_com_furos(p)
            self.assertGreater(g.area_assinada(ext), 0, p.nome)
            for f in furos:
                self.assertLess(g.area_assinada(f), 0, p.nome)
            (x0, y0), (x1, y1) = g.caixa_envolvente(ext)
            if p.tipo in ("I", "U", "Ue"):
                self.assertAlmostEqual(y1 - y0, p.d, delta=0.01, msg=p.nome)
                self.assertAlmostEqual(x1 - x0, p.bf, delta=0.01, msg=p.nome)

    def test_tubos_pelo_tipo_e_nao_pelo_nome(self):
        """O formato vem de dados['tipo']: redondo = 32 lados; retangular = cantos
        arredondados; todo tubo tem o furo interno."""
        tubos = banco().lista("tubo")
        self.assertEqual(len(tubos), 30)
        for p in tubos:
            ext, furos = g.secao_com_furos(p)
            self.assertEqual(len(furos), 1, p.nome)
            (x0, y0), (x1, y1) = g.caixa_envolvente(ext)
            if p.dados.get("tipo") == "redondo":
                self.assertEqual(len(ext), g.LADOS_CIRCULO, p.nome)
                self.assertAlmostEqual(x1 - x0, p.dados["D"], delta=0.01, msg=p.nome)
            else:
                self.assertGreater(len(ext), 4, p.nome)          # cantos arredondados
                self.assertAlmostEqual(x1 - x0, p.dados["b"], delta=0.01, msg=p.nome)
                self.assertAlmostEqual(y1 - y0, p.dados["h"], delta=0.01, msg=p.nome)

    def test_formado_a_frio_com_e_sem_enrijecedor(self):
        """"U … (FF)" não tem enrijecedor; "Ue" tem (e por isso tem mais pontos)."""
        u = g.secao(banco()["U 100×50×2,00 (FF)"])
        ue = g.secao(banco()["Ue 100×50×17×2,00"])
        self.assertGreater(len(ue), len(u))
        self.assertLess(abs(g.area_secao("U 100×50×2,00 (FF)") / 390.0 - 1), 0.03)

    def test_U_e_cantoneira_centroide_fora_do_meio(self):
        """Em U e L o centroide não é o centro do retângulo envolvente."""
        for nome in ('U 6"×12,2', 'L 3"×1/4"'):
            (x0, _), (x1, _) = g.caixa_envolvente(g.secao(nome))
            self.assertGreater(abs(x0 + x1), 1.0, nome)

    def test_barras_redonda_e_chata(self):
        r = g.barra_redonda(25.0)
        self.assertLess(abs(g.area_secao(r) / (math.pi * 25 ** 2 / 4) - 1), 0.01)
        c = g.barra_chata(100.0, 6.35)
        self.assertAlmostEqual(g.area_secao(c), 635.0, places=6)
        # o nome do perfil sintético do orquestrador é reconhecido
        self.assertAlmostEqual(g.resolver_perfil("Barra redonda ø 20 mm").d, 20.0)
        self.assertAlmostEqual(g.resolver_perfil("Barra ø 12,5 mm").d, 12.5)

    def test_perfil_desconhecido_falha_explicito(self):
        with self.assertRaises(ErroDeDados):
            g.secao("W 999×999")


class TestExtrusao(unittest.TestCase):

    def test_volume_igual_area_vezes_comprimento(self):
        for p in TODOS:
            A = g.area_secao(p)
            for ini, fim, rot in ORIENTACOES:
                b = Barra(perfil=p.nome, inicio=ini, fim=fim, rotacao=rot)
                v, f = g.malha_barra(b)
                vol = g.volume_malha(v, f)
                self.assertAlmostEqual(vol / (A * b.comprimento), 1.0, places=9,
                                       msg=f"{p.nome} {ini}->{fim}")

    def test_peso_pela_geometria_bate_com_massa_linear(self):
        """Volume da malha × 7850 kg/m³ contra massa × comprimento, dentro de 3 %."""
        erros = []
        for p in TODOS:
            b = Barra(perfil=p.nome, inicio=(0, 0, 0), fim=(0, 0, 6000), rotacao=90)
            v, f = g.malha_barra(b)
            peso_geo = g.volume_malha(v, f) * g.RHO_MM3
            peso_cat = p.massa * 6.0
            if abs(peso_geo / peso_cat - 1) > 0.03:
                erros.append(f"{p.nome}: {peso_geo:.1f} × {peso_cat:.1f} kg")
        self.assertEqual(erros, [])

    def test_malhas_fechadas_planas_e_para_fora(self):
        for p in TODOS:
            for ini, fim, rot in ORIENTACOES:
                b = Barra(perfil=p.nome, inicio=ini, fim=fim, rotacao=rot)
                v, f = g.malha_barra(b)
                _conferir_solido(self, v, f, f"{p.nome} {rot}")

    def test_eixo_forte_do_pilar_e_da_viga(self):
        """Pilar com rotação 90: alma no plano YZ. Viga horizontal: altura em Z."""
        p = banco()["W 530×85,0"]
        v, _ = g.malha_barra(Barra(perfil=p.nome, inicio=(0, 0, 0), fim=(0, 0, 6000),
                                   rotacao=90))
        (x0, y0, _), (x1, y1, _) = g.caixa_envolvente(v)
        self.assertAlmostEqual(y1 - y0, p.d, delta=0.01)
        self.assertAlmostEqual(x1 - x0, p.bf, delta=0.01)
        v, _ = g.malha_barra(Barra(perfil=p.nome, inicio=(0, 0, 0), fim=(5000, 0, 0)))
        (_, y0, z0), (_, y1, z1) = g.caixa_envolvente(v)
        self.assertAlmostEqual(z1 - z0, p.d, delta=0.01)
        self.assertAlmostEqual(y1 - y0, p.bf, delta=0.01)

    def test_triedro_estavel_perto_da_vertical(self):
        """Direção quase paralela ao vetor auxiliar não gera NaN nem troca de mão."""
        for d in ((0, 0, 1), (0, 0, -1), (1e-9, 0, 1), (0.3, 0, 0.954), (0.31, 0, 0.95)):
            u, v, w = g.base_local(d, 17.0)
            for vec in (u, v, w):
                self.assertTrue(all(math.isfinite(c) for c in vec))
                self.assertAlmostEqual(math.sqrt(sum(c * c for c in vec)), 1.0, places=9)
            cruz = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                    u[0] * v[1] - u[1] * v[0])
            self.assertAlmostEqual(sum(a * b for a, b in zip(cruz, w)), 1.0, places=9)

    def test_recortes_encurtam_a_barra(self):
        b = Barra(perfil="W 310×38,7", inicio=(0, 0, 0), fim=(5000, 0, 0),
                  recorte_inicio=20.0, recorte_fim=30.0)
        v, f = g.malha_barra(b)
        (x0, _, _), (x1, _, _) = g.caixa_envolvente(v)
        self.assertAlmostEqual(x0, 20.0, places=6)
        self.assertAlmostEqual(x1, 4970.0, places=6)

    def test_barra_invalida_falha_explicito(self):
        with self.assertRaises(ErroDeDados):
            g.malha_barra(Barra(perfil="W 310×38,7", inicio=(1, 1, 1), fim=(1, 1, 1)))
        with self.assertRaises(ErroDeDados):
            g.malha_barra(Barra(perfil="W 310×38,7", inicio=(0, 0, 0),
                                fim=(0, 0, float("nan"))))

    def test_extrudar_contorno_com_furo(self):
        ext = [(-50, -50), (50, -50), (50, 50), (-50, 50)]
        furo = [(-20, -20), (-20, 20), (20, 20), (20, -20)]
        s = g.extrudar((ext, [furo]), (0, 1, 1), 200.0, rotacao=15)
        self.assertAlmostEqual(s.volume, (100 * 100 - 40 * 40) * 200, places=4)
        _conferir_solido(self, s.vertices, s.faces, "extrusão com furo")


class TestTriangulacao(unittest.TestCase):

    def test_ear_clipping_convexo_e_concavo(self):
        for cont in ([(0, 0), (4, 0), (4, 3), (0, 3)],
                     [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)],
                     [(0, 0), (5, 2), (10, 0), (8, 5), (10, 10), (5, 8), (0, 10), (2, 5)]):
            for c in (cont, list(reversed(cont))):
                tris = g.triangular(c)
                self.assertEqual(len(tris), len(c) - 2)
                soma = 0.0
                for t in tris:
                    a = g.area_assinada([c[i] for i in t])
                    self.assertGreater(a, 0)                    # sempre anti-horário
                    soma += a
                self.assertAlmostEqual(soma, g.area_contorno(c), places=9)

    def test_triangulacao_de_face_3d(self):
        face = [(0, 0, 0), (100, 0, 50), (100, 100, 50), (0, 100, 0)]
        tris = g.triangular(face)
        self.assertEqual(len(tris), 2)
        soma = sum(g.area_face([face[i] for i in t]) for t in tris)
        self.assertAlmostEqual(soma, g.area_face(face), places=6)

    def test_chapa_com_furos_abertos_de_verdade(self):
        """Nenhum triângulo das tampas cobre o centro de um furo, e o volume desconta
        os furos (polígono de 16 lados)."""
        furos = [{"x": x, "y": y, "diametro": 21.0} for x in (-50, 50)
                 for y in (-250, -150, 150, 250)]
        ch = Chapa(origem=(1000, 2000, 3000), eixo_x=(1, 0, 0), eixo_y=(0, 0, 1),
                   contorno=[(-107, -300), (107, -300), (107, 300), (-107, 300)],
                   espessura=16.0, furos=furos)
        v, f = g.malha_chapa(ch)
        _conferir_solido(self, v, f, "chapa com furos")
        a_furo = g.area_contorno(g.contorno_furo(0, 0, 21.0))
        self.assertAlmostEqual(g.volume_malha(v, f), (214 * 600 - 8 * a_furo) * 16, places=3)
        ext = ch.contorno
        pts = list(ext) + [p for fu in furos
                           for p in g.contorno_furo(fu["x"], fu["y"], fu["diametro"])]
        tris = g.triangular_com_furos(ext, [g.contorno_furo(fu["x"], fu["y"], 21.0)
                                            for fu in furos])
        for fu in furos:
            c = (fu["x"], fu["y"])
            for t in tris:
                a, b, cc = (pts[i] for i in t)
                dentro = (g._cruz(a, b, c) > 1e-9 and g._cruz(b, cc, c) > 1e-9
                          and g._cruz(cc, a, c) > 1e-9)
                self.assertFalse(dentro, f"furo em {c} coberto pelo triângulo {t}")

    def test_chapa_inclinada_centrada(self):
        ch = Chapa(origem=(0, 0, 0), eixo_x=(0, 0.995, 0.0995), eixo_y=(1, 0, 0),
                   contorno=[(0, 0), (1800, 0), (0, -310)], espessura=7.7)
        v, f = g.malha_chapa(ch)
        _conferir_solido(self, v, f, "mísula")
        self.assertAlmostEqual(g.volume_malha(v, f), 1800 * 310 / 2 * 7.7, places=3)

    def test_chapa_invalida(self):
        with self.assertRaises(ErroDeDados):
            g.malha_chapa(Chapa(contorno=[(0, 0), (1, 0)]))


class TestEdicao(unittest.TestCase):

    def test_push_pull_de_topo_nos_dois_sentidos(self):
        cubo = _cubo()
        for d in (50.0, -30.0, 250.0):
            n = g.extrudar_face(cubo, 1, d)
            self.assertAlmostEqual(n.volume, 1e6 + 1e4 * d, places=4)
            _conferir_solido(self, n.vertices, n.faces, f"push/pull {d}")
        self.assertAlmostEqual(cubo.volume, 1e6, places=4)          # original intacto

    def test_push_pull_em_face_de_superficie(self):
        """Triângulo da tampa de uma barra: nasce um ressalto do tamanho da face."""
        s = g.extrudar(g.secao_com_furos("W 310×38,7"), (1, 0, 0), 1000.0)
        topo = next(i for i, f in enumerate(s.faces) if len(f) == 3
                    and g.normal_face([s.vertices[k] for k in f])[0] > 0.99)
        area = g.area_face([s.vertices[k] for k in s.faces[topo]])
        n = g.extrudar_face(s, topo, 40.0)
        self.assertAlmostEqual(n.volume - s.volume, area * 40.0, delta=1e-6 * s.volume)

    def test_offset_convexo(self):
        q = [(0, 0), (100, 0), (100, 100), (0, 100)]
        self.assertAlmostEqual(g.area_contorno(g.offset_contorno(q, 10)), 120 ** 2)
        self.assertAlmostEqual(g.area_contorno(g.offset_contorno(q, -10)), 80 ** 2)
        # sentido horário na entrada: o positivo continua sendo para fora
        self.assertAlmostEqual(g.area_contorno(g.offset_contorno(q[::-1], 10)), 120 ** 2)

    def test_offset_concavo(self):
        L = [(0, 0), (100, 0), (100, 40), (40, 40), (40, 100), (0, 100)]
        fora = g.offset_contorno(L, 5)
        dentro = g.offset_contorno(L, -5)
        self.assertAlmostEqual(g.area_contorno(fora), 110 * 50 + 50 * 60)
        self.assertAlmostEqual(g.area_contorno(dentro), 90 * 30 + 30 * 60)
        self.assertIn((45.0, 45.0), [(round(x, 9), round(y, 9)) for x, y in fora])

    def test_transformacoes_rigidas(self):
        cubo = _cubo()
        m = g.mover(cubo, (10, 20, 30))
        self.assertEqual(m.vertices[0], (10.0, 20.0, 30.0))
        r = g.girar(cubo, (0, 0, 1), (0, 0, 0), 90)
        self.assertAlmostEqual(r.volume, 1e6, places=3)
        self.assertAlmostEqual(r.vertices[1][1], 100.0, places=9)
        e = g.espelhar(cubo, (0, 0, 0), (1, 0, 0))
        _conferir_solido(self, e.vertices, e.faces, "espelhado")
        s = g.escalar(cubo, 2.0)
        self.assertAlmostEqual(s.volume, 8e6, places=3)
        b = Barra(inicio=(0, 0, 0), fim=(1000, 0, 0))
        b2 = g.girar(b, (0, 0, 1), (0, 0, 0), 90)
        self.assertAlmostEqual(b2.fim[1], 1000.0, places=9)
        self.assertEqual(b.fim, (1000, 0, 0))                       # original intacto
        ch = Chapa(eixo_x=(1, 0, 0), eixo_y=(0, 1, 0), contorno=[(0, 0), (1, 0), (0, 1)])
        ch2 = g.girar(ch, (1, 0, 0), (0, 0, 0), 90)
        self.assertAlmostEqual(ch2.eixo_y[2], 1.0, places=9)

    def test_dividir_aresta_mantem_malha_fechada(self):
        d = g.dividir_aresta(_cubo(), (0, 1), (50, 0, 0))
        self.assertEqual(len(d.vertices), 9)
        _conferir_solido(self, d.vertices, d.faces, "aresta dividida")
        with self.assertRaises(ErroDeDados):
            g.dividir_aresta(_cubo(), (0, 6), (50, 50, 50))

    def test_unir_solidos_encostados(self):
        u = g.unir_solidos(_cubo(), g.mover(_cubo(), (100, 0, 0)))
        self.assertEqual(len(u.faces), 10)                          # 12 − 2 de contato
        self.assertAlmostEqual(u.volume, 2e6, places=3)
        self.assertTrue(g.conferir_malha(u.vertices, u.faces)["fechada"])

    def test_secao_plano(self):
        segs = g.secao_plano(_cubo(), ((0, 0, 50), (0, 0, 1)))
        self.assertEqual(len(segs), 4)
        self.assertAlmostEqual(sum(math.dist(a, b) for a, b in segs), 400.0, places=6)
        for a, b in segs:
            self.assertAlmostEqual(a[2], 50.0)
            self.assertAlmostEqual(b[2], 50.0)
        self.assertEqual(g.secao_plano(_cubo(), ((0, 0, 500), (0, 0, 1))), [])


class TestUtilidades(unittest.TestCase):

    def test_normal_area_centroide_caixa(self):
        f = [(0, 0, 0), (2, 0, 0), (2, 3, 0), (0, 3, 0)]
        self.assertEqual(g.normal_face(f), (0.0, 0.0, 1.0))
        self.assertAlmostEqual(g.area_face(f), 6.0)
        self.assertEqual(g.centroide(f), (1.0, 1.5, 0.0))
        self.assertEqual(g.caixa_envolvente(f), ((0, 0, 0), (2, 3, 0)))

    def test_snap(self):
        p = g.interseccao_reta_plano((0, 0, 10), (0, 0, -1), ((0, 0, 0), (0, 0, 1)))
        self.assertEqual(p, (0.0, 0.0, 0.0))
        self.assertIsNone(g.interseccao_reta_plano((0, 0, 10), (1, 0, 0),
                                                   ((0, 0, 0), (0, 0, 1))))
        self.assertEqual(g.ponto_mais_proximo_reta((5, 5, 0), (0, 0, 0), (10, 0, 0)),
                         (5.0, 0.0, 0.0))
        self.assertAlmostEqual(g.distancia_ponto_segmento((5, 5, 0), (0, 0, 0), (10, 0, 0)), 5)
        self.assertAlmostEqual(g.distancia_ponto_segmento((13, 4, 0), (0, 0, 0), (10, 0, 0)), 5)


if __name__ == "__main__":
    unittest.main()
