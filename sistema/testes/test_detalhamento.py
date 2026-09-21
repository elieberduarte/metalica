# -*- coding: utf-8 -*-
"""Testes do detalhamento de peças a partir da malha (saida/detalhamento.py).

As peças são construídas aqui como malhas fechadas, do jeito que um exportador de
Brep facetado as escreve: chapa com furo, perfil U extrudado, barra redonda dobrada.
O teste de ponta a ponta usa o IFC pequeno de `dados_ifc/`.
"""
import csv
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import detalhamento as det                      # noqa: E402

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_ifc")


# ------------------------------------------------------------------ malhas de teste

def _ring(cx, cy, r, n=8):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def chapa_com_furo(L=130.0, H=50.0, t=3.0, d=13.0, giro=None):
    """Chapa retangular com um furo redondo no centro; as faces de topo são um anel de
    oito quadriláteros em volta do furo, como faz quem exporta sem laços internos."""
    ext = [(0, 0), (L / 2, 0), (L, 0), (L, H / 2), (L, H), (L / 2, H), (0, H), (0, H / 2)]
    furo = _ring(L / 2, H / 2, d / 2)
    # o anel liga cada ponto externo ao ponto do furo mais próximo em ângulo
    furo = sorted(furo, key=lambda p: math.atan2(p[1] - H / 2, p[0] - L / 2))
    ext = sorted(ext, key=lambda p: math.atan2(p[1] - H / 2, p[0] - L / 2))
    v, f = [], []
    def add(p, z):
        v.append((p[0], p[1], z))
        return len(v) - 1
    topo_e = [add(p, t) for p in ext]
    topo_f = [add(p, t) for p in furo]
    base_e = [add(p, 0.0) for p in ext]
    base_f = [add(p, 0.0) for p in furo]
    n = 8
    for i in range(n):
        j = (i + 1) % n
        f.append([topo_e[i], topo_e[j], topo_f[j], topo_f[i]])          # topo, normal +z
        f.append([base_e[j], base_e[i], base_f[i], base_f[j]])          # base, normal -z
        f.append([base_e[i], base_e[j], topo_e[j], topo_e[i]])          # lateral externa
        f.append([topo_f[i], topo_f[j], base_f[j], base_f[i]])          # parede do furo
    if giro:
        c, s = math.cos(giro), math.sin(giro)
        v = [(x * c - y * s, x * s + y * c, z) for x, y, z in v]
    return v, f


def perfil_u(L=740.0, h=88.0, b=40.0, t=2.25):
    """U extrudado ao longo de x, alma no plano z = 0."""
    sec = [(0, 0), (h, 0), (h, b), (h - t, b), (h - t, t), (t, t), (t, b), (0, b)]  # (y, z)
    v = [(0.0, y, z) for y, z in sec] + [(L, y, z) for y, z in sec]
    n = len(sec)
    f = [list(range(n))[::-1], [n + i for i in range(n)]]
    for i in range(n):
        j = (i + 1) % n
        f.append([i, j, n + j, n + i])
    return v, f


def barra_dobrada(a=300.0, b=100.0, d=9.5):
    """Barra redonda em L: perna `a` em x, dobra de 90° e perna `b` em y (junta a meia
    esquadria, sem raio)."""
    r = d / 2
    anel = _ring(0, 0, r)                       # (cos, sin) no plano da seção
    # perna 1 ao longo de +x, perna 2 ao longo de +y; a junta é o plano x + y = a,
    # que passa pelo canto interno (a − r, r) e pelo externo (a + r, −r), e o anel da
    # junta é a geratriz da perna 1 cortada por ele: (a − r·cos t, r·cos t, r·sin t).
    # O volume fecha exato em A·(a + b), como numa dobra sem raio.
    a0 = [(0.0, c, s) for c, s in anel]
    meio = [(a - c, c, s) for c, s in anel]
    b1 = [(a - c, b, s) for c, s in anel]
    v = a0 + meio + b1
    n = 8
    f = [list(range(n))[::-1], [2 * n + i for i in range(n)]]
    for i in range(n):
        j = (i + 1) % n
        f.append([i, j, n + j, n + i])
        f.append([n + i, n + j, 2 * n + j, 2 * n + i])
    return v, f


def _pos(marca, tipo, perfil, malha, **kw):
    v, f = malha
    p = det.Posicao(marca=marca, tipo_ifc=tipo, perfil=perfil, vertices=v, faces=f,
                    material="ASTM A36", quantidade=kw.get("quantidade", 2))
    return det.analisar(p)


# ------------------------------------------------------------------------- nomes

def test_nomes_e_medidas_do_tecnometal():
    assert abs(det._polegadas_mm("FE RED 3/8''") - 9.525) < 1e-6
    assert abs(det._polegadas_mm("L 1 1/2'' X 1/8''") - 38.1) < 1e-6
    assert abs(det._polegadas_mm("BARRA ROSCADA Ø 5/8\r\n''") - 15.875) < 1e-6
    assert det._chapa_nominal("PLATE 130x50x3") == (130.0, 50.0, 3.0)
    assert det._eh_redonda("FE RED 3/8''") and det._eh_redonda("BARRA ROSCADA Ø 5/8")
    assert not det._eh_redonda("U88X40X2.25")
    assert det._eh_telha("TELHA TP40 0.50MM") and not det._eh_telha("PLATE 80x80x8")
    m = det._marcas_da_descricao("Mark:M86 Pos:P93 Material:CIVIL 300")
    assert m == {"Part Mark": "P93", "Assembly Mark": "M86", "Grade": "CIVIL 300"}, m


def test_laco_redondo_oblongo_e_recorte():
    furo = det._classificar_laco(_ring(10, 20, 6.5, 16))
    assert furo.tipo == "redondo" and abs(furo.d - 13) < 0.05 and abs(furo.x - 10) < 1e-6
    # estádio 25 × 13: dois arcos de raio 6,5 ligados por retas
    r, a = 6.5, 6.0
    pts = ([(-a + r * math.cos(t), r * math.sin(t)) for t in
            [math.pi / 2 + k * math.pi / 8 for k in range(9)]] +
           [(a + r * math.cos(t), r * math.sin(t)) for t in
            [-math.pi / 2 + k * math.pi / 8 for k in range(9)]])
    obl = det._classificar_laco(pts)
    assert obl.tipo == "oblongo" and abs(obl.larg - 25) < 0.05 and abs(obl.alt - 13) < 0.05
    rec = det._classificar_laco([(0, 0), (30, 0), (30, 10), (0, 10)])
    assert rec.tipo == "recorte"


# ------------------------------------------------------------------------- chapas

def test_chapa_plana_com_furo():
    p = _pos("P1", "IfcPlate", "PLATE 130x50x3", chapa_com_furo())
    assert p.classe == "chapa", p.observacoes
    assert abs(p.L - 130) < 0.01 and abs(p.H - 50) < 0.01 and abs(p.T - 3) < 0.01
    assert len(p.furos) == 1 and p.furos[0].tipo == "redondo"
    assert abs(p.furos[0].d - 13) < 0.05
    assert abs(p.furos[0].x - 65) < 0.05 and abs(p.furos[0].y - 25) < 0.05
    assert len(p.contorno) >= 4
    volume = 130 * 50 * 3 - 8 * 0.5 * 6.5 ** 2 * math.sin(2 * math.pi / 8) * 3
    assert abs(p.volume - volume) < 1.0
    assert abs(p.peso - volume * det.RHO_ACO) < 1e-6


def test_chapa_girada_no_arquivo_sai_deitada_e_alinhada():
    # girada 37° no plano e com a face para baixo: o desenho não pode depender disso
    v, f = chapa_com_furo(L=80, H=80, d=17, giro=math.radians(37))
    p = _pos("P42", "IfcPlate", "PLATE 80x80x8", (v, f))
    assert p.classe == "chapa"
    assert abs(p.L - 80) < 0.05 and abs(p.H - 80) < 0.05, (p.L, p.H)   # não 113 (diagonal)
    assert abs(p.furos[0].d - 17) < 0.05


def test_chapa_mais_alta_que_larga_gira_para_deitar():
    p = _pos("P2", "IfcPlate", "PLATE 50x130x3", chapa_com_furo(L=50, H=130))
    assert abs(p.L - 130) < 0.01 and abs(p.H - 50) < 0.01


# ------------------------------------------------------------------------- barras

def test_perfil_u_reto():
    p = _pos("P3", "IfcBeam", "U88X40X2.25", perfil_u())
    assert p.classe == "barra", p.observacoes
    assert abs(p.comprimento - 740) < 0.01
    assert abs(p.H - 88) < 0.01 and abs(p.T - 40) < 0.01
    assert len(p.secao) == 1 and len(p.secao[0]) == 8
    area = 88 * 40 - (88 - 2 * 2.25) * (40 - 2.25)
    assert abs(abs(det._area_2d(p.secao[0])) - area) < 0.5
    assert not p.furos and not p.observacoes


def test_perfil_u_inclinado_no_arquivo():
    # a mesma terça, deitada no telhado a 10 % e girada em planta
    v, f = perfil_u()
    ang = math.atan(0.10)
    c, s = math.cos(ang), math.sin(ang)
    v = [(x * c - z * s, y, x * s + z * c) for x, y, z in v]
    c2, s2 = math.cos(0.7), math.sin(0.7)
    v = [(x * c2 - y * s2, x * s2 + y * c2, z) for x, y, z in v]
    p = _pos("P4", "IfcBeam", "U88X40X2.25", (v, f))
    assert p.classe == "barra" and abs(p.comprimento - 740) < 0.05
    assert abs(p.H - 88) < 0.05 and abs(p.T - 40) < 0.05


def test_barra_redonda_dobrada_tem_comprimento_desenvolvido():
    p = _pos("P5", "IfcBeam", "FE RED 3/8''", barra_dobrada())
    assert p.classe == "barra_conformada", (p.classe, p.observacoes)
    # duas pernas de 300 e 100 pelo eixo, menos o que a meia esquadria tira
    assert 370 < p.comprimento < 410, p.comprimento
    assert any("desenvolvido" in o for o in p.observacoes)


def test_barra_redonda_reta():
    anel = _ring(0, 0, 4.7625)
    v = [(0.0, y, z) for y, z in anel] + [(800.0, y, z) for y, z in anel]
    f = [list(range(8))[::-1], [8 + i for i in range(8)]] + \
        [[i, (i + 1) % 8, 8 + (i + 1) % 8, 8 + i] for i in range(8)]
    p = _pos("P6", "IfcBeam", "FE RED 3/8''", (v, f))
    assert p.classe == "barra_redonda" and abs(p.comprimento - 800) < 0.01


def test_sem_geometria_nao_derruba_o_lote():
    p = det.Posicao(marca="X", tipo_ifc="IfcBeam", perfil="?")
    det.analisar(p)
    assert p.classe == "indefinida" and p.observacoes


# ------------------------------------------------------------------------ desenho

def test_folha_e_romaneio():
    pecas = [_pos("P1", "IfcPlate", "PLATE 130x50x3", chapa_com_furo(), quantidade=10),
             _pos("P3", "IfcBeam", "U88X40X2.25", perfil_u(), quantidade=4),
             _pos("P5", "IfcBeam", "FE RED 3/8''", barra_dobrada(), quantidade=1)]
    pecas[0].conjuntos = ["M1", "M2"]
    with tempfile.TemporaryDirectory() as pasta:
        folha = det.montar_folha(pecas, "TESTE")
        dxf = folha.gravar(os.path.join(pasta, "folha.dxf"))
        texto = open(dxf, encoding="cp1252").read()
        assert texto.startswith("0\nSECTION") and texto.rstrip().endswith("EOF")
        for marca in ("P1", "P3", "P5"):
            assert marca in texto
        assert "CIRCLE" in texto and "POLYLINE" in texto
        for camada in ("ACO", "FURO", "COTA", "TEXTO", "AUXILIAR"):
            assert "\n8\n%s\n" % camada in texto
        csv_path = det.gravar_romaneio(os.path.join(pasta, "r.csv"), pecas, {"BOLT 12x35": 7})
        with open(csv_path, encoding="utf-8-sig") as f:
            linhas = list(csv.reader(f, delimiter=";"))
    assert linhas[0][0] == "Posicao" and len(linhas) == 5
    chapa = next(l for l in linhas if l[0] == "P1")
    assert chapa[5] == "10" and chapa[6] == "130" and chapa[7] == "50" and chapa[8] == "3,0"
    assert chapa[9].startswith("1x") and chapa[1] == "M1 M2"
    bolt = linhas[-1]
    assert bolt[3] == "BOLT 12x35" and bolt[5] == "7"


def test_ponta_a_ponta_com_ifc_pequeno():
    ifc = os.path.join(DADOS, "estrutura_mm.ifc")
    with tempfile.TemporaryDirectory() as pasta:
        rel = det.gerar(ifc, pasta)
        assert rel["posicoes"] >= 1 and rel["pecas"] >= rel["posicoes"]
        assert os.path.exists(rel["arquivos"]["dxf"])
        assert os.path.exists(rel["arquivos"]["romaneio"])
        assert os.path.exists(os.path.join(pasta, "relatorio.json"))
        assert rel["peso_total_kg"] > 0


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except Exception as e:
                falhas += 1
                print(f"  FALHA {nome}: {e}")
    print(f"\n{falhas} falha(s).")
    sys.exit(1 if falhas else 0)
