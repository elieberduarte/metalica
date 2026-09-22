# -*- coding: utf-8 -*-
"""Testes do detalhamento 2D para o CAD (nucleo2d/detalhar.py): posições contadas,
instâncias de conjunto, regra da furação das terças e desenhos gerados."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Solido          # noqa: E402
from nucleo2d import detalhar as det                    # noqa: E402
from nucleo2d.desenho import Cota, Texto                # noqa: E402
from test_detalhamento import chapa_com_furo, perfil_u  # noqa: E402


def _solido(nome, tipo_ifc, verts, faces, posicao, conjunto, perfil, dx=0.0, dy=0.0, dz=0.0):
    s = Solido(nome=nome, camada="Vigas", vertices=[(x + dx, y + dy, z + dz) for x, y, z in verts],
               faces=[list(f) for f in faces])
    s.atributos["tipo_ifc"] = tipo_ifc
    s.atributos["marcas"] = {"posicao": posicao, "conjunto": conjunto, "perfil": perfil}
    s.atributos["propriedades"] = {"Steel & Graphics Common": {"Grade": "CIVIL 300"}}
    return s


def _u_com_furos(L, h, b, t, furos):
    """Perfil U com furos redondos na alma: a alma (z = 0) vira anéis em volta de cada furo
    é complexo demais para o teste; usa-se a chapa com furo como 'alma' equivalente."""
    return perfil_u(L, h, b, t)


def _modelo():
    doc = Documento(nome="teste")
    # 3 chapas iguais P1 (uma por conjunto) + 2 terças soltas M5 (marca = conjunto)
    v, f = chapa_com_furo(130, 50, 3, 13)
    for i in range(3):
        doc.add(_solido("PLATE 130x50x3", "IfcPlate", v, f, "P1", "M%d" % (i + 1), "PLATE 130x50x3", dx=i * 5000))
    v, f = perfil_u(5000, 150, 50, 2.25)
    for i in range(2):
        doc.add(_solido("U150X50X2.25", "IfcBeam", v, f, "M5", "M5", "U150X50X2.25", dy=1000 + i * 1500, dz=3000))
    # conjunto M1..M3: chapa + duas barras encostadas (composição igual, 3 instâncias
    # da mesma marca seria M1 ×3; aqui cada uma tem marca própria)
    v, f = perfil_u(1200, 88, 40, 2.25)
    for i in range(3):
        for k in range(2):
            doc.add(_solido("U88X40X2.25", "IfcBeam", v, f, "P2", "M%d" % (i + 1), "U88X40X2.25",
                            dx=i * 5000, dy=k * 300))
    # M9: 2 instâncias da mesma marca (2 P3 + 1 P4 cada), separadas no espaço; a
    # quantidade de instâncias é o mdc das quantidades por posição (4 e 2 → 2)
    for i in range(2):
        for k in range(2):
            doc.add(_solido("U88X40X2.25", "IfcBeam", v, f, "P3", "M9", "U88X40X2.25",
                            dx=20000 + i * 5000, dy=k * 300))
        doc.add(_solido("U88X40X2.25", "IfcBeam", v, f, "P4", "M9", "U88X40X2.25",
                        dx=20000 + i * 5000, dy=150, dz=90))
    return doc


def test_posicoes_contadas_e_desenhos():
    doc = _modelo()
    r = det.detalhar(doc, regra_tercas=False)
    por = {p["marca"]: p for p in r["posicoes"]}
    assert por["P1"]["quantidade"] == 3 and por["P1"]["classe"] == "Chapa"
    assert por["M5"]["quantidade"] == 2 and por["M5"]["classe"] == "Barra"
    assert por["P2"]["quantidade"] == 6 and por["P3"]["quantidade"] == 4
    assert set(r["desenhos"]) >= {"chapas", "barras", "conjuntos"}
    chapas = r["desenhos"]["chapas"]
    titulos = [e.texto for e in chapas.entidades.values() if isinstance(e, Texto)]
    assert any(t.startswith("P1 – 03x") for t in titulos)
    assert any(isinstance(e, Cota) for e in chapas.entidades.values())
    # M9 tem 2 instâncias pela composição (4 P3 / 2)
    conj = {c["marca"]: c for c in r["conjuntos"]}
    assert conj["M9"]["instancias"] == 2 and conj["M9"]["composicao"] == {"P3": 2, "P4": 1}
    # M1, M2 e M3 têm a mesma geometria: uma célula só, "M1 / M2 / M3 – 03x"
    juntos = conj["M1 / M2 / M3"]
    assert juntos["instancias"] == 3 and juntos["marcas"] == ["M1", "M2", "M3"]
    assert juntos["categoria"] == "CONJUNTOS" and "M1" not in conj
    tit = [e.texto for e in r["desenhos"]["conjuntos"].entidades.values() if isinstance(e, Texto)]
    assert any(t.startswith("M9 – 02x") for t in tit)
    assert any(t.startswith("M1 / M2 / M3 – 03x") for t in tit)
    itens = r["desenhos"]["chapas"].metadados["detalhamento"]["itens"]
    assert itens["P1"]["categoria"] == "CHAPAS"
    itens_b = r["desenhos"]["barras"].metadados["detalhamento"]["itens"]
    assert itens_b["M5"]["categoria"] == "TERÇAS" and itens_b["P2"]["categoria"] == "BARRAS"
    assert abs(r["peso_total"] - sum(p["peso_total"] for p in r["posicoes"])) < 0.5


def test_regra_furacao_terca():
    """Terça com dois furos a 80 mm na vertical vira 50; a chapinha com a mesma furação
    (80 mm, deitada) também; a terça alta vai a 100."""
    pos_terca = det.Posicao(marca="M5", tipo_ifc="IfcBeam", perfil="U150X50X2.25", conjuntos=["M5"])
    pos_terca.classe, pos_terca.L, pos_terca.H = "barra", 5000.0, 150.0
    pos_terca.furos = [det.Furo("redondo", 100.0, 35.0, 13.0), det.Furo("redondo", 100.0, 115.0, 13.0),
                       det.Furo("redondo", 4900.0, 35.0, 13.0), det.Furo("redondo", 4900.0, 115.0, 13.0),
                       det.Furo("oblongo", 2500.0, 75.0, larg=25, alt=13)]
    pos_chapa = det.Posicao(marca="P1", tipo_ifc="IfcPlate", perfil="PLATE 130x50x3")
    pos_chapa.classe, pos_chapa.L, pos_chapa.H = "chapa", 130.0, 50.0
    pos_chapa.furos = [det.Furo("redondo", 25.0, 25.0, 13.0), det.Furo("redondo", 105.0, 25.0, 13.0)]
    pos_banzo = det.Posicao(marca="P9", tipo_ifc="IfcBeam", perfil="U150X50X2.25", conjuntos=["M2"])
    pos_banzo.classe, pos_banzo.L, pos_banzo.H = "barra", 5000.0, 150.0
    pos_banzo.furos = [det.Furo("redondo", 100.0, 35.0, 13.0), det.Furo("redondo", 100.0, 115.0, 13.0)]
    pos_alta = det.Posicao(marca="M6", tipo_ifc="IfcBeam", perfil="C250X85X25X3", conjuntos=["M6"])
    pos_alta.classe, pos_alta.L, pos_alta.H = "barra", 6000.0, 250.0
    pos_alta.furos = [det.Furo("redondo", 100.0, 85.0, 13.0), det.Furo("redondo", 100.0, 165.0, 13.0)]
    pos_outra = det.Posicao(marca="P8", tipo_ifc="IfcBeam", perfil="U150X50X2.25", conjuntos=["M2"])
    pos_outra.classe, pos_outra.L, pos_outra.H = "barra", 5000.0, 150.0
    pos_outra.furos = [det.Furo("redondo", 100.0, 35.0, 17.0), det.Furo("redondo", 100.0, 135.0, 17.0)]
    mud = det.regra_furacao_terca([pos_terca, pos_chapa, pos_banzo, pos_alta, pos_outra], {})
    # o banzo P9 tem a mesma furação original da terça (é onde a terça se liga): entra;
    # P8, com outro passo (100), não é ligação de terça e fica como está
    assert set(mud) == {"M5", "P1", "M6", "P9"}
    ys = sorted(round(f.y) for f in pos_terca.furos if f.tipo == "redondo" and f.x < 200)
    assert ys == [50, 100]                                   # centro em 75, 50 mm entre eixos
    assert round(pos_terca.furos[4].x) == 2500               # o oblongo não muda
    xs = sorted(round(f.x) for f in pos_chapa.furos)
    assert xs == [40, 90]                                    # 80 → 50, centrado em 65
    assert sorted(round(f.y) for f in pos_banzo.furos) == [50, 100]
    assert sorted(round(f.y) for f in pos_outra.furos) == [35, 135]
    assert sorted(round(f.y) for f in pos_alta.furos) == [75, 175]   # ≥ 200 mm: 100 na vertical
    assert "padrao de fabrica" in pos_terca.observacoes[0]


def test_eixos_do_conjunto_orientacao_real():
    v, f = perfil_u(3000, 88, 40, 2.25)
    # barra em pé (eixo z): sai em pé, como montada (vertical do desenho ≈ z)
    s = Solido(nome="x", vertices=[(y, z, x) for x, y, z in v], faces=[list(q) for q in f])
    s.atributos["tipo_ifc"] = "IfcColumn"
    c, u, vv, w = det._eixos_do_conjunto([s])
    assert vv[2] > 0.99 and abs(u[2]) < 0.01
    # barra inclinada a 20° no plano x-z: sai inclinada
    import math
    a = math.radians(20)
    # comprimento e altura (88) no plano x-z, largura (40) em y: a peça fina está de lado, como uma tesoura
    s2 = Solido(nome="y", vertices=[(x * math.cos(a) - y * math.sin(a), z, x * math.sin(a) + y * math.cos(a)) for x, y, z in v], faces=[list(q) for q in f])
    c, u, vv, w = det._eixos_do_conjunto([s2])
    assert abs(vv[2] - 1.0) < 0.02 and abs(u[0] - 1.0) < 0.02
    # conjunto deitado no plano horizontal: o eixo comprido vai para a horizontal
    s3 = Solido(nome="z", vertices=[(x, y, z * 0.01) for x, y, z in v], faces=[list(q) for q in f])
    c, u, vv, w = det._eixos_do_conjunto([s3])
    assert abs(u[0]) > 0.99 and abs(w[2]) > 0.99


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except Exception as e:                    # noqa: BLE001
                falhas += 1
                print(f"  FALHA {nome}: {e}")
    print(f"\n{falhas} falha(s).")
    sys.exit(1 if falhas else 0)
