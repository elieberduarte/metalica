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
    # P2, P3 e P4 são a mesma barra (U88 de 1200, sem furos): uma posição só, 12 peças
    assert "P2" not in por and por["P2 / P3 / P4"]["quantidade"] == 12 and por["P2 / P3 / P4"]["marcas"] == ["P2", "P3", "P4"]
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
    assert itens_b["M5"]["categoria"] == "TERÇAS" and itens_b["P2 / P3 / P4"]["categoria"] == "BARRAS"
    assert itens_b["P2 / P3 / P4"]["marcas"] == ["P2", "P3", "P4"]
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
    import math
    v, f = perfil_u(3000, 88, 40, 2.25)
    # conjunto linear (uma barra só, tirante com chapinhas): sai deitado na horizontal do
    # papel, para o comprimento total ser lido — mesmo a barra em pé (eixo z)
    s = Solido(nome="x", vertices=[(y, z, x) for x, y, z in v], faces=[list(q) for q in f])
    s.atributos["tipo_ifc"] = "IfcColumn"
    c, u, vv, w = det._eixos_do_conjunto([s])
    assert abs(u[2]) > 0.99 and abs(vv[2]) < 0.01
    a = math.radians(20)
    s2 = Solido(nome="y", vertices=[(x * math.cos(a) - y * math.sin(a), z, x * math.sin(a) + y * math.cos(a)) for x, y, z in v], faces=[list(q) for q in f])
    c, u, vv, w = det._eixos_do_conjunto([s2])
    assert abs(u[2] - math.sin(a)) < 0.02 and vv[2] > 0.9
    # conjunto com altura (duas barras a 20°, afastadas 1000 mm na perpendicular): sai
    # inclinado como está montado — vertical do desenho = z, esquerda → direita = +x
    dz, dx = 1000 * math.cos(a), -1000 * math.sin(a)
    s2b = Solido(nome="y2", vertices=[(p[0] + dx, p[1], p[2] + dz) for p in s2.vertices], faces=[list(q) for q in f])
    c, u, vv, w = det._eixos_do_conjunto([s2, s2b])
    assert abs(vv[2] - 1.0) < 0.02 and abs(u[0] - 1.0) < 0.02
    # o triedro segue a convenção do gerador de vistas: direita = w × v
    cr = det._cruz(w, vv)
    assert all(abs(cr[i] - u[i]) < 1e-6 for i in range(3))
    # conjunto linear deitado no plano horizontal: visto de cima, comprido na horizontal
    s3 = Solido(nome="z", vertices=[(x, y, z * 0.01) for x, y, z in v], faces=[list(q) for q in f])
    c, u, vv, w = det._eixos_do_conjunto([s3])
    assert abs(u[0]) > 0.99 and abs(w[2]) > 0.99


def test_instancias_por_caixas():
    """Duas barras encostadas numa linha (a segunda começa dentro da primeira) são uma
    instância só — a varredura corta pelo x máximo, não pelo y mínimo."""
    v, f = perfil_u(1000, 88, 40, 2.25)
    a = Solido(nome="a", vertices=list(v), faces=[list(q) for q in f])
    b = Solido(nome="b", vertices=[(x + 500, y, z) for x, y, z in v], faces=[list(q) for q in f])
    c = Solido(nome="c", vertices=[(x + 5000, y, z) for x, y, z in v], faces=[list(q) for q in f])
    grupos = det._instancias([a, b, c], folga=8.0)
    assert sorted(len(g) for g in grupos) == [1, 2]
    # grupo com 2 unidades encostadas (águas de um pórtico): divide em duas com a composição unitária
    for s, pos in ((a, "P1"), (b, "P2")):
        s.atributos["marcas"] = {"posicao": pos, "conjunto": "M1"}
    a2 = Solido(nome="a2", vertices=[(x + 1500, y, z) for x, y, z in v], faces=[list(q) for q in f])
    b2 = Solido(nome="b2", vertices=[(x + 2000, y, z) for x, y, z in v], faces=[list(q) for q in f])
    a2.atributos["marcas"] = {"posicao": "P1", "conjunto": "M1"}
    b2.atributos["marcas"] = {"posicao": "P2", "conjunto": "M1"}
    import collections
    unidade = collections.Counter({"P1": 1, "P2": 1})
    assert det._multiplo([a, b, a2, b2], unidade) == 2 and det._multiplo([a, b, a2], unidade) == 0
    partes = det._dividir([a, b, a2, b2], 2, unidade)
    assert len(partes) == 2 and all(len(p) == 2 for p in partes)


def test_planta_de_localizacao():
    doc = _modelo()
    r = det.detalhar(doc, grupos=["localizacao"], regra_tercas=False)
    d = r["desenhos"]["localizacao"]
    assert [v["tipo"] for v in d.vistas] == ["topo", "frente", "lateral"]
    assert len(d.metadados["celulas"]) == 3 and d.metadados["detalhamento"]["grupo"] == "localizacao"
    rot = [e for e in d.entidades.values() if isinstance(e, Texto) and (e.atributos or {}).get("vista")]
    por_vista = {}
    for e in rot:
        por_vista.setdefault(e.atributos["vista"], []).append(e.texto)
    planta = por_vista["PLANTA DE LOCALIZAÇÃO"]
    # os 3 conjuntos M1..M3 e o M9 (2 instâncias) aparecem na planta; as terças M5 (5 m,
    # deitadas) também; a chapa P1 está dentro dos conjuntos, não é rótulo
    assert planta.count("M9") == 2 and {"M1", "M2", "M3"} <= set(planta) and planta.count("M5") == 2
    assert "P1" not in planta
    # todas as peças desenhadas nas três vistas, em linha fina
    assert all(v["pecas_projetadas"] == len(det._pecas(doc)[0]) for v in d.vistas)
    assert d.escala >= 1


def test_chapa_nominal_e_bloco_parametrico():
    """Chapa 130×49,5 com nome PLATE 130x50x3 sai com 50 na cota; vira Chapa paramétrica,
    o detalhe é editável e os furos mexidos no desenho voltam para as 3 chapas — uma
    delas montada espelhada."""
    import math
    from nucleo3d.modelo import Chapa
    from nucleo2d.desenho import Circulo
    v, f = chapa_com_furo(130, 49.5, 3, 13)
    doc = Documento(nome="teste")
    doc.add(_solido("PLATE 130x50x3", "IfcPlate", v, f, "P1", "M1", "PLATE 130x50x3"))
    doc.add(_solido("PLATE 130x50x3", "IfcPlate", v, f, "P1", "M2", "PLATE 130x50x3", dx=1000))
    # a terceira girada de 180° em torno de z (espelhada no plano da chapa)
    doc.add(_solido("PLATE 130x50x3", "IfcPlate", [(-x + 2000, -y, z) for x, y, z in v], [list(reversed(q)) for q in f],
                    "P1", "M3", "PLATE 130x50x3"))
    d, pos = det.detalhar_posicao(doc, "P1")
    assert pos.classe == "chapa" and abs(pos.H - 50.0) < 1e-6 and abs(pos.L - 130.0) < 1e-6
    assert d.metadados["detalhe_posicao"]["editavel"] is False        # ainda sólido
    furos0 = d.metadados["detalhe_posicao"]["furos"]
    assert len(furos0) == 1 and furos0[0]["tipo"] == "redondo" and abs(furos0[0]["d"] - 13) < 0.5
    assert det.converter_chapas(doc, "P1") == 3
    chapas = [e for e in doc.entidades.values() if isinstance(e, Chapa)]
    assert len(chapas) == 3 and all(c.atributos["marcas"]["posicao"] == "P1" for c in chapas)
    assert all(abs(c.espessura - 3.0) < 0.2 and len(c.furos) == 1 for c in chapas)
    # o desenho de detalhe da chapa convertida é editável, com o furo como entidade marcada
    d, pos = det.detalhar_posicao(doc, "P1")
    meta = d.metadados["detalhe_posicao"]
    assert meta["editavel"] and meta["parametrica"] and len(meta["pecas"]) == 3
    furos = [e for e in d.entidades.values() if e.camada == "FURO"]
    assert len(furos) == 1 and isinstance(furos[0], Circulo) and furos[0].atributos.get("furo") == 0
    # edição: move o furo 20 mm em x e acrescenta outro; aplica
    furos[0].centro = (furos[0].centro[0] + 20.0, furos[0].centro[1])
    d.add(Circulo(camada="FURO", centro=(100.0, 25.0), raio=8.75))
    lidos = det.furos_do_desenho(d)
    assert len(lidos) == 2
    r = det.aplicar_furos(doc, "P1", lidos, meta["furos"])
    assert r["chapas"] == 3
    x_orig = furos0[0]["x"]
    for c in chapas:
        xs = sorted(round(f_["x"], 1) for f_ in c.furos)
        u0 = min(x for x, _ in c.contorno)
        # o furo original andou 20 mm no sentido do desenho em cada chapa, espelhada ou não
        assert any(abs(x - u0 - (x_orig + 20.0)) < 1.6 or abs(x - u0 - (130.0 - x_orig - 20.0)) < 1.6 for x in xs)
        assert any(abs(f_["diametro"] - 17.5) < 1e-6 for f_ in c.furos)
    # o detalhe regenerado lê os furos novos, e o modelo sobrevive ao JSON
    d2, _ = det.detalhar_posicao(doc, "P1")
    assert len(d2.metadados["detalhe_posicao"]["furos"]) == 2
    doc2 = Documento.de_dict(doc.dict())
    assert sum(isinstance(e, Chapa) for e in doc2.entidades.values()) == 3
    # o detalhamento geral continua contando a posição (chapas paramétricas entram)
    r = det.detalhar(doc2, grupos=["chapas"], regra_tercas=False)
    assert {p["marca"]: p["quantidade"] for p in r["posicoes"]}["P1"] == 3
    # simetria: identidade quando bate, espelho em x quando é o que leva os furos
    ident = det._simetria([(30.0, 25.0)], [(30.0, 25.0)], 130.0, 50.0)
    assert ident(10.0, 5.0) == (10.0, 5.0)
    esp = det._simetria([(30.0, 25.0)], [(100.0, 25.0)], 130.0, 50.0)
    assert esp(30.0, 25.0) == (100.0, 25.0)


def test_desenho_geral_editavel_e_tamanho():
    """O detalhamento geral converte as chapas planas; a célula tem furos editáveis; os
    furos e um contorno maior lidos do desenho vão para as chapas e a célula é
    regenerada no mesmo lugar, sem furo em dobro."""
    from nucleo3d.modelo import Chapa
    from nucleo2d.desenho import Circulo
    doc = _modelo()
    r = det.detalhar(doc, grupos=["chapas"], regra_tercas=False)
    assert r["convertidas"] == 3
    d = r["desenhos"]["chapas"]
    meta = d.metadados["detalhamento"]
    assert meta["editaveis"] == ["P1"] and len(meta["furos_originais"]["P1"]) == 1
    cont, org = det.contorno_do_desenho(d, "P1")
    assert abs(max(x for x, _ in cont) - 130) < 1e-6 and abs(max(y for _, y in cont) - 50) < 1e-6
    d.add(Circulo(camada="FURO", centro=(org[0] + 100.0, org[1] + 25.0), raio=8.75))
    furos = det.furos_do_desenho(d, "P1", org)
    assert len(furos) == 2 and abs(furos[-1]["x"] - 100.0) < 1e-6
    novo = [(x * 140 / 130, y) for x, y in cont]
    res = det.aplicar_furos(doc, "P1", furos, meta["furos_originais"]["P1"], novo)
    assert res == {"chapas": 3, "furos": 2, "contornos": 3, "parafusos": 0}
    for ch in (e for e in doc.entidades.values() if isinstance(e, Chapa)):
        xs = [p[0] for p in ch.contorno]
        assert abs((max(xs) - min(xs)) - 140) < 1e-6 and len(ch.furos) == 2
    det.regenerar_celula(d, doc, "P1")
    cont2, org2 = det.contorno_do_desenho(d, "P1")
    assert org2 == org and abs(max(x for x, _ in cont2) - 140) < 1e-6
    assert len(det.furos_do_desenho(d, "P1", org2)) == 2          # o desenhado à mão não dobra
    assert sum(1 for c in d.metadados["celulas"] if abs(c[2] - c[0]) > 140) >= 1


def _caixa_solida(L, H, T, dx=0.0, dy=0.0, dz=0.0):
    v = [(x + dx, y + dy, z + dz) for z in (0.0, T) for x, y in ((0, 0), (L, 0), (L, H), (0, H))]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return v, f


def test_furos_pelos_parafusos():
    """Chapa que veio como caixa (sem furo) ganha um furo por parafuso que a atravessa:
    Ø13 para o 12x35 e, para o parafuso sem tamanho, o da porca (entre faces 16 → M10 → Ø11)."""
    doc = Documento(nome="teste")
    v, f = _caixa_solida(200, 100, 10)
    doc.add(_solido("PLATE 200x100x10", "IfcPlate", v, f, "P9", "M1", "PLATE 200x100x10"))
    # parafuso 12x35 em pé no ponto (50, 50), atravessando a chapa
    vb, fb = _caixa_solida(12, 12, 45, dx=44, dy=44, dz=-20)
    b = Solido(nome="BOLT (A) 12x35", vertices=vb, faces=fb)
    b.atributos["tipo_ifc"] = "IfcMechanicalFastener"
    doc.add(b)
    # "porca" achatada 16 × 16 × 12 sem tamanho no nome, em (150, 50), encostada na chapa
    vn, fn = _caixa_solida(16, 16, 12, dx=142, dy=42, dz=10)
    n = Solido(nome="BOLT () 0x0", vertices=vn, faces=fn)
    n.atributos["tipo_ifc"] = "IfcBuildingElementProxy"
    doc.add(n)
    # parafuso fora da chapa: não entra
    vf, ff = _caixa_solida(12, 12, 45, dx=300, dy=44, dz=-20)
    fora = Solido(nome="BOLT (A) 12x35", vertices=vf, faces=ff)
    fora.atributos["tipo_ifc"] = "IfcMechanicalFastener"
    doc.add(fora)
    lev = det.levantar(doc, regra_tercas=False)
    pos = lev["posicoes"][0]
    furos = sorted((f.x, f.y, f.d) for f in pos.furos)
    assert furos == [(50.0, 50.0, 13.0), (150.0, 50.0, 11.0)], furos
    assert any("parafuso" in o for o in pos.observacoes) and any("porca" in o for o in pos.observacoes)
    # a conversão em chapa paramétrica leva os furos inferidos para o 3D
    from nucleo3d.modelo import Chapa
    assert det.converter_chapas(doc, "P9") == 1
    ch = next(e for e in doc.entidades.values() if isinstance(e, Chapa))
    assert sorted(round(f_["diametro"]) for f_ in ch.furos) == [11, 13]
    # o furo do parafuso 12x35 (índice 0, em 50,50) anda 20 mm em x: o parafuso vai junto
    x_antes = sum(v[0] for v in b.vertices) / len(b.vertices)
    i0 = next(i for i, f_ in enumerate(ch.furos) if abs(f_["x"] - 50) < 1e-6)
    furos = [{"tipo": "redondo", "x": 70.0, "y": 50.0, "d": 13.0, "furo": i0},
             {"tipo": "redondo", "x": 150.0, "y": 50.0, "d": 11.0, "furo": 1 - i0}]
    originais = [{"x": f_["x"], "y": f_["y"]} for f_ in ch.furos]
    res = det.aplicar_furos(doc, "P9", furos, originais)
    assert res["parafusos"] == 1
    assert abs(sum(v[0] for v in b.vertices) / len(b.vertices) - x_antes - 20.0) < 1e-6
    assert abs(sum(v[0] for v in fora.vertices) / len(fora.vertices) - 306.0) < 1e-6    # o de fora não mexe


def test_vinculo_chapa_tercas_e_ajustes():
    """A chapinha do suporte muda de 80 para 60 mm entre furos: a terça com a mesma furação
    original (na outra orientação) acompanha; o ajuste guardado volta a ser aplicado."""
    terca = det.Posicao(marca="M5", tipo_ifc="IfcBeam", perfil="U150X50X2.25", conjuntos=["M5"])
    terca.classe, terca.L, terca.H = "barra", 5000.0, 150.0
    terca.furos = [det.Furo("redondo", 100.0, 35.0, 13.0), det.Furo("redondo", 100.0, 115.0, 13.0),
                   det.Furo("redondo", 4900.0, 35.0, 13.0), det.Furo("redondo", 4900.0, 115.0, 13.0)]
    outra = det.Posicao(marca="M6", tipo_ifc="IfcBeam", perfil="U150X50X2.25", conjuntos=["M6"])
    outra.classe, outra.L, outra.H = "barra", 5000.0, 150.0
    outra.furos = [det.Furo("redondo", 100.0, 35.0, 13.0), det.Furo("redondo", 100.0, 135.0, 13.0)]
    originais = [{"tipo": "redondo", "x": 25.0, "y": 25.0, "d": 13.0}, {"tipo": "redondo", "x": 105.0, "y": 25.0, "d": 13.0}]
    novos = [{"tipo": "redondo", "x": 35.0, "y": 25.0, "d": 13.0}, {"tipo": "redondo", "x": 95.0, "y": 25.0, "d": 13.0}]
    vinc = det.vincular_furos_de_ligacao([terca, outra], {}, "P1", originais, novos)
    assert set(vinc) == {"M5"}
    ys = sorted(round(f_["y"]) for f_ in vinc["M5"]["furos"] if f_["x"] < 200)
    assert ys == [45, 105]                       # 80 → 60, centrado em 75
    assert "chapa P1" in vinc["M5"]["origem"]
    # mesma furação de novo: nada muda; passos iguais: nada
    assert det.vincular_furos_de_ligacao([terca], {}, "P1", novos, novos) == {}
    # o ajuste guardado é aplicado no levantamento seguinte
    fresca = det.Posicao(marca="M5", tipo_ifc="IfcBeam", perfil="U150X50X2.25", conjuntos=["M5"])
    fresca.classe, fresca.furos = "barra", [det.Furo("redondo", 100.0, 35.0, 13.0), det.Furo("redondo", 100.0, 115.0, 13.0)]
    assert det.aplicar_ajustes_de_furos([fresca], vinc) == ["M5"]
    assert sorted(round(f_.y) for f_ in fresca.furos if f_.x < 200) == [45, 105]
    assert any("vinculada" in o for o in fresca.observacoes)


def test_furo_oblongo_na_malha():
    from nucleo3d.modelo import Chapa
    from nucleo3d import geometria
    ch = Chapa(contorno=[(0, 0), (150, 0), (150, 123), (0, 123)], espessura=4.8, centrada=False,
               furos=[{"x": 35, "y": 25, "largura": 25, "altura": 13}, {"x": 115, "y": 85, "diametro": 13}])
    v, f = geometria.malha_chapa(ch)
    assert len(v) > 8 and all(len(face) >= 3 for face in f)
    # a área desconta o rasgo (estádio) e o furo redondo
    import math
    esperado = 150 * 123 - ((25 - 13) * 13 + math.pi * 6.5 ** 2) - math.pi * 6.5 ** 2
    assert abs(ch.area - esperado) < 1e-6
    ob = geometria.contorno_oblongo(0, 0, 25, 13)
    xs = [p[0] for p in ob]
    ys = [p[1] for p in ob]
    assert abs(max(xs) - 12.5) < 1e-6 and abs(min(xs) + 12.5) < 1e-6 and abs(max(ys) - 6.5) < 1e-6


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
