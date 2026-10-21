# -*- coding: utf-8 -*-
"""Identificação para modelagem (20/10/2026) — o servidor: a volta do 3D para a Montagem (Fase 6), a cota da viga de aço
apoiada pela face de baixo na volta do 3D, e a varredura do Hangar Almayer (o projeto de fabricação que o caminho antigo
enfileirou no 3D): a locação, a tesoura e as terças."""
import collections
import copy
import math
import os

import pytest

from nucleo2d.desenho import Desenho, Linha
from nucleo3d import de_planta_estrutura as DPE
from nucleo3d.modelo import Barra, Chapa

HANGAR = os.path.join(os.path.dirname(__file__), "..", "..", "Projeto", "OBRAS", "Hangar-Almayer",
                      "Hangar-Allmayer_Projeto de fabricacao_V5.dxf")
PERFIL = "U 127×50×2,25 (FF)"


def _terca(a, b, z_pe=6454.5, quadro=None):
    at = {"elemento": "viga", "material": "aco", "papel": "terça", "marca": "T.C.1", "secao": {"perfil": PERFIL, "aco": "ASTM A36"},
          "nivel_topo": z_pe, "alinhamento": "base"}
    if quadro:
        at["quadro"] = quadro
    return Linha(camada="ESTRUTURA", a=a, b=b, atributos=at)


def _montagem(giro=0.0):
    des = Desenho(nome="Montagem", escala=1.0)
    q = {"id": "qi", "tipo": "implantacao", "escala": 100.0, "x": 0.0, "y": 0.0, "w": 420, "h": 297,
         "mapa": {"X0": 82226.0, "Y0": -24300.0, "ox": 8.0, "oy": -270.0, "giro": giro}}
    des.metadados = {"montagem": {"versao": 1, "original": "planta-de-lançamento", "quadros": [q]}}
    e = _terca((50.0, -100.0), (104.6, -100.0), quadro="qi")
    des.add(e)
    return des, e.id


def _modelo(des):
    doc, _avisos = DPE.modelo_da_planta(des, [])
    return doc


def test_terca_apoiada_pela_base_nao_sobe_na_volta():
    """sem descontar meio perfil, a volta do 3D lia o eixo da barra como a face de baixo e a terça subia 63,5 mm"""
    des = Desenho(nome="planta", escala=100.0)
    e = _terca((0.0, 0.0), (5460.0, 0.0))
    des.add(e)
    doc = _modelo(des)
    barra = next(b for b in doc.entidades.values() if isinstance(b, Barra))
    assert barra.papel == "terça" and barra.camada == "Terças"
    assert abs(barra.inicio[2] - (6454.5 + 63.5)) < 0.5
    r = DPE.planta_do_modelo(des, doc, [])
    assert r["alteracoes"] == [], r["alteracoes"]
    assert des.entidades[e.id].atributos["nivel_topo"] == 6454.5


@pytest.mark.parametrize("giro", [0.0, 90.0])
def test_montagem_volta_ao_papel(giro):
    des, eid = _montagem(giro)
    doc = _modelo(DPE.planta_real(des))
    antes = copy.deepcopy(des.entidades[eid])
    # nada mudou no 3D: nada muda na Montagem
    r = DPE.montagem_do_modelo(des, doc, [])
    assert r["alteracoes"] == []
    assert des.entidades[eid].a == pytest.approx(antes.a) and des.entidades[eid].b == pytest.approx(antes.b)
    # a terça andou 300 mm ao longo dela e subiu 100 mm no 3D: no papel do quadro (1:100), 3 mm; a cota acompanha
    barra = next(b for b in doc.entidades.values() if isinstance(b, Barra))
    real_antes = DPE.planta_real(des).entidades[eid]
    d = ((real_antes.b[0] - real_antes.a[0]) / 5460.0, (real_antes.b[1] - real_antes.a[1]) / 5460.0)
    barra.inicio = (barra.inicio[0] + 300 * d[0], barra.inicio[1] + 300 * d[1], barra.inicio[2] + 100)
    barra.fim = (barra.fim[0] + 300 * d[0], barra.fim[1] + 300 * d[1], barra.fim[2] + 100)
    r = DPE.montagem_do_modelo(des, doc, [])
    novo = des.entidades[eid]
    assert any("movida 300 mm" in x for x in r["alteracoes"]), r["alteracoes"]
    assert abs(novo.a[0] - antes.a[0] - 3.0) < 0.01 and abs(novo.a[1] - antes.a[1]) < 0.01
    assert novo.atributos["nivel_topo"] == pytest.approx(6554.5, abs=0.6)
    assert novo.atributos["quadro"] == "qi"


def test_montagem_peca_apagada_no_3d_vira_apontamento():
    des, eid = _montagem()
    doc = _modelo(DPE.planta_real(des))
    for k in [k for k, b in doc.entidades.items() if isinstance(b, Barra)]:
        doc.remover(k)
    r = DPE.montagem_do_modelo(des, doc, [])
    assert r["sem_peca"] == ["T.C.1"] and eid in des.entidades


@pytest.fixture(scope="module")
def hangar():
    if not os.path.exists(HANGAR):
        pytest.skip("sem o DXF do Hangar em Projeto/OBRAS/Hangar-Almayer")
    from nucleo3d import identificacao as I, lancamento
    des, _ = lancamento.ler_arquitetonico(open(HANGAR, "rb").read(), "dxf")
    return des, I.varrer(des)


def test_hangar_locacao_e_tesouras(hangar):
    des, v = hangar
    loc = v["locacao"]
    assert loc["folha"] == 12 and "LOCAÇÃO" in loc["titulo"]
    assert [x["nome"] for x in loc["eixos"]["numeros"]] == ["1", "2", "3", "4", "5", "6"]
    assert sorted(x["nome"] for x in loc["eixos"]["letras"]) == ["A", "B"]
    tes = {t["tipo"]: t for t in v["tesouras"]}
    assert tes["T2"]["eixos"] == ["3", "4", "5"] and tes["T1"]["eixos"] == ["6"] and tes["T3"]["eixos"] == ["1"]
    assert tes["T2"]["vista"]["folha"] == 17 and tes["T3"]["vista"]["folha"] == 23


def test_hangar_tesoura_com_a_alma_nas_faces(hangar):
    """a alma em linha simples atravessando o banzo desenhado em contorno: cortada nas faces, a T2 sai com 47 barras (eram 13)"""
    from nucleo3d import identificacao as I, leitura_quadros as LQ
    des, v = hangar
    t2 = next(t for t in v["tesouras"] if t["tipo"] == "T2")
    r = I.tesoura_da_folha(des, t2["vista"]["caixa"])
    assert r["largura"] == pytest.approx(20000.0) and r["altura"] == pytest.approx(1330.0)
    lt, _ap, _el = LQ.ler_tesoura({"id": "c", "tipo": "tesoura", "nome": "T2", "escala": 1, "x": 0.0, "y": 0.0}, r["entidades"])
    assert sum(lt["contagem"].values()) >= 45, lt["contagem"]


def test_hangar_t1_banzo_simples_com_a_alma_em_2l(hangar):
    """o T1 do Hangar (U127 só, alma 2L32/2L25): o desenho sai sem seção dupla nos banzos e com a cantoneira dupla (10º
    campo) na alma; o 3D monta o U com a boca para dentro do vão (2.2) e o par dentro da boca, uma em cada aba (2.5),
    com presilhas, e a regra limpa. 20/10 a alma saía em L simples dentro do U; 21/10 cedo a leitura "alma no plano"
    do corte T1 virava o U com a boca para fora — desfeita pelo usuário ("quando o perfil é simples os banzos devem
    ficar com a boca virada para dentro do vão da tesoura e as cantoneiras duplas soldadas nas laterais internas")"""
    from nucleo2d.desenho import Linha as L_
    from nucleo3d import identificacao as I, regras_trelica as R
    from nucleo3d.geometria import base_local
    des, v = hangar
    t1 = next(t for t in v["tesouras"] if t["tipo"] == "T1")
    perfis = I.perfis_da_tesoura(des, "T1", I.folhas_com_moldura(des))
    assert perfis["banzo"]["mult"] == 1 and perfis["montante"]["mult"] == 2 and perfis["diagonal"]["mult"] == 2
    r = I.desenho_da_tesoura(des, t1["vista"]["caixa"], perfis)
    banzos = [b for b in r["barras"] if b[4] in ("banzo_sup", "banzo_inf", "extremidade")]
    alma = [b for b in r["barras"] if b not in banzos]
    assert banzos and all(b[6] == "" and not b[9] for b in banzos)
    assert alma and all(b[9] for b in alma)
    des3 = Desenho(nome="planta", escala=100.0)
    des3.add(L_(a=(102220.0, -4900.0), b=(102220.0, -24300.0), camada="ESTRUTURA",
                atributos={"elemento": "trelica", "material": "aco", "marca": "T1", "perfis": {}, "cantoneira": "simples",
                           "nivel_base": 5000, "desenho": {"barras": r["barras"], "vao": r["vao"], "altura": r["altura"]}}))
    doc = _modelo(des3)
    bs = [e for e in doc.entidades.values() if isinstance(e, Barra)]
    us = [b for b in bs if b.perfil.startswith("U")]
    ls = [b for b in bs if b.perfil.startswith("L") and b.papel != "presilha"]
    assert len(us) == len(banzos) and len(ls) == 2 * len(alma) and [b for b in bs if b.papel == "presilha"]
    for u in us:
        assert abs(u.inicio[0] - 102220.0) < 0.5                                   # no plano da tesoura
        assert abs(base_local(u.direcao, u.rotacao)[0][0]) < 1e-6                 # a boca no plano, para dentro
    for b in ls:                                       # 2.5: a aba que sai do plano aponta para o centro (o par se olha)
        assert R.lado_da_aba(b, (1.0, 0.0, 0.0)) == (-1 if b.inicio[0] > 102220.0 else 1), b.nome
    assert not [e for e in R.conferir(bs) if e["regra"] in ("2.1", "2.2", "2.3", "2.4", "2.5", "2.9")]


#: os pilares do Hangar no real (o centro de PM1…PM16, 300 × 400; o PM14 é o P07, "A DEFINIR" no projeto)
PILARES_HANGAR = {"PM1": (82895, -4900), "PM2": (82895, -24300), "PM3": (87695, -4900), "PM4": (87695, -24300),
                  "PM5": (92495, -4900), "PM6": (92495, -24300), "PM7": (97295, -4900), "PM8": (97295, -24300),
                  "PM9": (102095, -4900), "PM10": (102095, -24300), "PM11": (102095, -9750), "PM12": (102095, -14600),
                  "PM13": (102095, -19450), "PM14": (102120, -6250), "PM15": (82895, -1300), "PM16": (82895, -27650)}


def _planta_do_hangar():
    from nucleo2d.desenho import Polilinha
    des = Desenho(nome="montagem", escala=1.0)
    for m, (x, y) in PILARES_HANGAR.items():
        des.add(Polilinha(camada="ESTRUTURA", fechada=True, vertices=[(x - 150, y - 200), (x + 150, y - 200), (x + 150, y + 200), (x - 150, y + 200)],
                          atributos={"elemento": "pilar", "material": "concreto", "marca": m, "nivel_base": -1000, "nivel_topo": 5000,
                                     "secao": {"tipo": "retangular", "b": 30, "h": 40}}))
    for x, m in ((82845, "T2-A"), (87695, "T2"), (92495, "T2"), (97295, "T2"), (102220, "T1")):
        des.add(Linha(camada="ESTRUTURA", a=(x, -4900), b=(x, -24300), atributos={"elemento": "trelica", "material": "aco", "marca": m}))
    return des


def test_hangar_apoios_das_tesouras_pela_locacao_dos_chumbadores(hangar):
    """a etapa 5 (21/10): a locação dos chumbadores (folha 35) casada com os pilares, as medidas pelos textos (PB1 #9,50
    25x25, CB1 #8,00 20x20, CHUMBADOR Ø5/8" C=55) e a furação pelo detalhe (folha 36: 4 furos Ø18 a ±95); a CB só onde a
    tesoura apoia, e então o topo do pilar desce a espessura dela; o P07 sem chapa vira apontamento"""
    from nucleo3d import identificacao as I
    des, _v = hangar
    r = I.apoios_das_tesouras(des, I.folhas_com_moldura(des), _planta_do_hangar(), 5000.0)
    assert r["resumo"] == {"A1": 2, "A2": 6, "A3": 2, "C": 2, "D": 1, "E1": 1, "E2": 1}
    por_pilar = {a["pilar"]: a for a in r["apoios"]}
    assert set(por_pilar) == set(PILARES_HANGAR) - {"PM14"}
    for a in r["apoios"]:
        pb = a["pb"]
        assert (pb["marca"], pb["espessura"], pb["largura"], pb["altura"]) == ("PB1", 9.5, 250.0, 250.0)
        assert sorted((f["dx"], f["dy"], f["diametro"]) for f in pb["furos"]) == [(-95, -95, 18), (-95, 95, 18), (95, -95, 18), (95, 95, 18)]
        assert a["chumbadores"]["n"] == 4 and a["chumbadores"]["comprimento"] == 550.0
        assert a["chumbadores"]["diametro"] == pytest.approx(15.875)
        assert math.dist(a["centro"], PILARES_HANGAR[a["pilar"]]) < 1.0
    com_cb = {a["pilar"] for a in r["apoios"] if a["cb"]}
    assert com_cb == {"PM%d" % i for i in range(1, 14)}
    assert all(a["topo_pilar"] == 4992.0 for a in r["apoios"] if a["cb"])
    assert por_pilar["PM15"]["marca"] == "E1" and por_pilar["PM15"]["cq"]["n"] == 2
    assert any("PM14" in av for av in r["avisos"])


def test_apoio_na_planta_vira_chapas_furos_e_chumbadores():
    """o que a etapa 5 lança: a PB e a CB (elemento chapa), os furos da PB (o furo diz a chapa: a CB por cima cobre os
    furos) e o chumbador (parafuso com papel chumbador) — o 3D com a barra redonda de produção, do pé da PB para baixo"""
    from nucleo2d.desenho import Circulo, Polilinha
    from nucleo3d.modelo import Chapa
    des = Desenho(nome="planta", escala=1.0)
    q = lambda c, B: [(c[0] - B / 2, c[1] - B / 2), (c[0] + B / 2, c[1] - B / 2), (c[0] + B / 2, c[1] + B / 2), (c[0] - B / 2, c[1] + B / 2)]
    des.add(Polilinha(camada="E", fechada=True, vertices=q((0, 0), 250), atributos={"elemento": "chapa", "marca": "PB1", "espessura": 9.5, "nivel_topo": 4992}))
    des.add(Polilinha(camada="E", fechada=True, vertices=q((0, 0), 200), atributos={"elemento": "chapa", "marca": "CB1", "espessura": 8, "nivel_topo": 5000}))
    for dx, dy in ((-95, -95), (95, -95), (95, 95), (-95, 95)):
        des.add(Circulo(camada="E", centro=(dx, dy), raio=9, atributos={"elemento": "furo", "diametro": 18, "chapa": "PB1", "marca": "F"}))
        des.add(Circulo(camada="E", centro=(dx, dy), raio=8, atributos={"elemento": "parafuso", "papel": "chumbador", "diametro": 15.875,
                                                                       "comprimento": 550, "bitola": '5/8"', "nivel_topo": 4982.5, "marca": "CH"}))
    doc = _modelo(des)
    chs = {c.atributos["marca"]: c for c in doc.entidades.values() if isinstance(c, Chapa)}
    assert len(chs["PB1"].furos) == 4 and not chs["CB1"].furos
    chumb = [b for b in doc.entidades.values() if isinstance(b, Barra) and b.papel == "chumbador"]
    assert len(chumb) == 4
    for b in chumb:
        assert b.inicio[2] == pytest.approx(4982.5) and b.fim[2] == pytest.approx(4432.5) and "5/8" in b.perfil


def test_hangar_suporte_das_tercas_pelo_projeto(hangar):
    """a etapa 6 (21/10): o ST1 das folhas 4 e 33 — L127×50#3,75 com 150 mm, 84 peças, 4 furos Ø14 (o par a 25 mm da
    ponta de cada terça: ±30 do meio; 38,5 e 88,5 do pé), folga de 10 mm entre as pontas, a perna de 50 A DEFINIR; o SL1
    (L100×50) das terças laterais também é lido"""
    from nucleo3d import identificacao as I
    des, _v = hangar
    r = I.suportes_das_tercas(des, I.folhas_com_moldura(des))
    st = r["suportes"]["ST1"]
    assert (st["perfil"], st["comprimento"], st["quantidade"], st["folga"]) == ("L 127×50×3,75 (FF)", 150.0, 84, 10.0)
    assert sorted((f["ao_longo"], f["altura"], f["d"]) for f in st["furos"]) == [(-30, 38.5, 14), (-30, 88.5, 14), (30, 38.5, 14), (30, 88.5, 14)]
    assert "DEFINIR" in st["a_definir"]
    assert r["suportes"]["SL1"]["perfil"] == "L 100×50×3,75 (FF)"


def test_suporte_das_tercas_no_3d():
    """o 3D com o suporte nas terças: um em cada cruzamento com o banzo de cima (no meio do composto: o U de fora passa
    da ponta da terça), a cantoneira encostada na costa da alma da terça, a perna baixa no pé dela; na emenda as duas
    terças recuam 5 mm (10 mm entre as pontas) e cada uma leva o par de furos a 25 mm da ponta; no fim da linha (o
    oitão) a terça não recua"""
    from nucleo2d.desenho import Linha as L_
    from nucleo3d.modelo import Solido
    from nucleo3d.geometria import base_local, resolver_perfil, secao
    st = {"marca": "ST1", "perfil": "L 127×50×3,75 (FF)", "comprimento": 150.0, "folga": 10.0,
          "furos": [{"ao_longo": a, "altura": h, "d": 14.0} for a in (-30.0, 30.0) for h in (38.5, 88.5)]}
    des = Desenho(nome="planta", escala=1.0)
    barras = [[0, 0, 6000, 0, "banzo_inf"], [0, 600, 6000, 600, "banzo_sup"], [0, 0, 0, 600, "extremidade"],
              [6000, 0, 6000, 600, "extremidade"], [3000, 0, 3000, 600, "montante"], [0, 600, 3000, 0, "diagonal"],
              [3000, 0, 6000, 600, "diagonal"]]
    for x in (0.0, 5000.0, 10000.0):
        des.add(L_(camada="E", a=(x, 0.0), b=(x, 6000.0), atributos={"elemento": "trelica", "material": "aco", "marca": "T",
                    "perfis": {"banzo_sup": "U 127×50×3,00 (FF)", "banzo_inf": "U 127×50×3,00 (FF)", "diagonal": "L 25×3 (FF)"},
                    "nivel_base": 5000, "desenho": {"barras": barras, "vao": 6000, "altura": 600}}))
    z_pe = 5000 + 600 + 63.5 + 1.5                   # sobre o banzo de cima (o eixo dele em +5,600)
    for x0, x1 in ((0.0, 5000.0), (5000.0, 10000.0)):
        des.add(L_(camada="E", a=(x0, 3000.0), b=(x1, 3000.0), atributos={"elemento": "viga", "material": "aco", "papel": "terça",
                    "marca": "TC", "secao": {"perfil": "U 127×50×2,25 (FF)"}, "nivel_topo": z_pe, "alinhamento": "base", "suporte": st}))
    doc = _modelo(des)
    sups = [b for b in doc.entidades.values() if isinstance(b, Barra) and b.papel == "suporte"]
    assert sorted(round((b.inicio[0] + b.fim[0]) / 2) for b in sups) == [0, 5000, 10000]
    tc = sorted((b for b in doc.entidades.values() if isinstance(b, Barra) and b.papel == "terça"), key=lambda b: b.inicio[0])
    assert (tc[0].recorte_inicio, tc[0].recorte_fim, tc[1].recorte_inicio, tc[1].recorte_fim) == (0.0, 5.0, 5.0, 0.0)
    # a cantoneira encostada na costa da alma da terça, do pé dela 127 mm para cima
    def faixa(b, eixo):
        u, v, _ = base_local(b.direcao, b.rotacao)
        m = [(b.inicio[k] + b.fim[k]) / 2 for k in range(3)]
        return [m[eixo] + p[0] * u[eixo] + p[1] * v[eixo] for p in secao(resolver_perfil(b.perfil))]
    s5 = next(b for b in sups if abs((b.inicio[0] + b.fim[0]) / 2 - 5000) < 1)
    yt, ys = faixa(tc[0], 1), faixa(s5, 1)
    assert max(ys) == pytest.approx(min(yt), abs=0.5) or min(ys) == pytest.approx(max(yt), abs=0.5)
    assert min(faixa(s5, 2)) == pytest.approx(min(faixa(tc[0], 2)), abs=0.5) and max(faixa(s5, 2)) - min(faixa(s5, 2)) == pytest.approx(127.0, abs=0.5)
    furos = [s for s in doc.entidades.values() if isinstance(s, Solido) and (s.atributos or {}).get("furo")]
    da = collections.Counter(doc.entidades[f.atributos["furo"]["peca"]].papel for f in furos)
    assert da == {"suporte": 12, "terça": 2 + 2 + 2 + 2}   # 4 em cada suporte; na emenda 2 + 2, em cada oitão 2
    xs = sorted(round(f.atributos["furo"]["ponto"][0] - 5000) for f in furos if doc.entidades[f.atributos["furo"]["peca"]].papel == "terça"
                and abs(f.atributos["furo"]["ponto"][0] - 5000) < 100)
    assert xs == [-30, -30, 30, 30]                  # 25 mm da ponta de cada terça (que recuou 5)


def test_hangar_chapas_da_emenda_e_das_ligacoes_pelo_projeto(hangar):
    """a etapa 7 (21/10): as chapas das folhas 30 e 32/33 — CE1 600×1330 (T2, 8 pç), CL1 600×890 com o recorte dos
    banzos (T2), CE2 450×1330 e CL2 300×890 (T1, aba de um lado só, a 300 mm do eixo como as da T2: os furos das VC a
    110/170 da ponta delas), CE3 220×1330 (T3, "CE3 - 2x - #9,50" com "22x133 - T3" embaixo); furos Ø17; a CE da vista
    geral ("EMENDA - CE1") é a da emenda; os 8 parafusos Ø5/8" da emenda nas alturas 200/500/830/1130 da elevação"""
    from nucleo3d import identificacao as I
    des, _v = hangar
    r = I.chapas_das_emendas(des, I.folhas_com_moldura(des))
    ch = r["chapas"]
    resumo = {m: (c["tesoura"], c["papel"], c["quantidade"], c["espessura"], c["largura"], c["altura"], c["aba"], c["eixo_x"], len(c["furos"]))
              for m, c in ch.items()}
    assert resumo == {"CE1": ("T2", "emenda", 8, 9.5, 600.0, 1330.0, "duas", 300.0, 24),
                      "CL1": ("T2", "ligacao", 8, 9.5, 600.0, 890.0, "duas", 300.0, 16),
                      "CE2": ("T1", "emenda", 2, 9.5, 450.0, 1330.0, "esquerda", 300.0, 16),
                      "CL2": ("T1", "ligacao", 2, 9.5, 300.0, 890.0, "esquerda", 300.0, 8),
                      "CE3": ("T3", "emenda", 2, 9.5, 220.0, 1330.0, "nenhuma", 110.0, 8)}
    assert len(ch["CL1"]["contorno"]) == 12 and {f["d"] for c in ch.values() for f in c["furos"]} == {17.0}
    assert sorted({f["x"] for f in ch["CE1"]["furos"]}) == [30.0, 90.0, 160.0, 440.0, 510.0, 570.0]
    p = r["parafusos_emenda"]
    assert (round(p["diametro"], 2), p["n"], p["alturas"]) == (15.88, 8, [200.0, 500.0, 830.0, 1130.0])


def _tesoura_com_emenda(ce_altura=1030.0):
    """uma tesoura de 6 m partida no meio (o banzo de baixo para a 9,5 mm da junta, como o B1 do Hangar), o montante da
    junta, montantes a 1,5 m das pontas e uma VT chegando no de 1,5 m"""
    from nucleo2d.desenho import Linha as L_
    ce = {"marca": "CE1", "papel": "emenda", "espessura": 9.5, "largura": 300.0, "altura": ce_altura, "aba": "nenhuma",
          "eixo_x": 150.0, "contorno": [[0, 0], [300, 0], [300, ce_altura], [0, ce_altura]],
          "furos": [{"x": x, "y": y, "d": 17.0} for x in (60.0, 240.0) for y in (200.0, 500.0)]}
    cl = {"marca": "CL1", "papel": "ligacao", "espessura": 9.5, "largura": 600.0, "altura": 880.0, "aba": "duas", "eixo_x": 300.0,
          "contorno": [[0, 0], [600, 0], [600, 880], [0, 880]],
          "furos": [{"x": x, "y": y, "d": 17.0} for x in (30.0, 90.0, 510.0, 570.0) for y in (38.5, 88.5)]}
    barras = [[0, 0, 2990.5, 0, "banzo_inf"], [3009.5, 0, 6000, 0, "banzo_inf"], [0, 600, 3000, 900, "banzo_sup"],
              [3000, 900, 6000, 600, "banzo_sup"], [0, 0, 0, 600, "extremidade"], [6000, 0, 6000, 600, "extremidade"],
              [3000, 0, 3000, 900, "montante"], [1500, 0, 1500, 750, "montante"], [4500, 0, 4500, 750, "montante"],
              [0, 600, 1500, 0, "diagonal"], [1500, 750, 3000, 0, "diagonal"], [3000, 0, 4500, 750, "diagonal"],
              [4500, 0, 6000, 600, "diagonal"]]
    des = Desenho(nome="planta", escala=1.0)
    des.add(L_(camada="E", a=(0.0, 0.0), b=(0.0, 6000.0), atributos={"elemento": "trelica", "material": "aco", "marca": "T2",
               "perfis": {"banzo_sup": "U 127×50×3,00 (FF)", "banzo_inf": "U 127×50×3,00 (FF)", "montante": "U 100×50×3,00 (FF)",
                          "diagonal": "U 100×50×3,00 (FF)"},
               "nivel_base": 5000, "desenho": {"barras": barras, "vao": 6000, "altura": 900},
               "chapas": {"emenda": ce, "ligacao": cl, "parafusos_emenda": {"diametro": 15.875, "n": 4, "alturas": [200.0, 500.0]}}}))
    des.add(L_(camada="E", a=(100.0, 1500.0), b=(4000.0, 1500.0), atributos={"elemento": "viga", "material": "aco", "papel": "travamento",
               "marca": "VT", "secao": {"perfil": "U 100×50×2,65 (FF)"}, "nivel_topo": 5000, "alinhamento": "base"}))
    return _modelo(des)


def test_emenda_da_tesoura_no_3d():
    """a emenda no 3D (21/10): uma CE em cada metade, as duas encostadas no meio da junta (9,5 + 9,5), os parafusos da
    emenda nos furos das alturas da elevação atravessando as duas; o montante único da junta vira um em cada metade
    (o M11 do Hangar), com a face na chapa e a boca para o meio do vão (2.3); a diagonal que chega na junta para na face
    do montante; o banzo de cima com o corte em pé na face da chapa; as regras das tesouras sem achado"""
    from nucleo3d.modelo import Solido
    from nucleo3d import regras_trelica as rt
    from nucleo3d.de_planta_estrutura import _faixa_da_secao
    doc = _tesoura_com_emenda()
    ents = list(doc.entidades.values())
    ce = sorted((c for c in ents if isinstance(c, Chapa) and (c.atributos or {}).get("marca") == "CE1"), key=lambda c: c.origem[1])
    assert [round(c.origem[1], 2) for c in ce] == [2995.25, 3004.75] and all(len(c.furos) == 4 for c in ce)
    par = [s for s in ents if isinstance(s, Solido) and (s.atributos or {}).get("parafuso")]
    assert len(par) == 4 and all(abs(s.atributos["parafuso"]["ponto"][1] - 3000.0) < 0.01 for s in par)
    assert {round(s.atributos["parafuso"]["ponto"][2] - min(p.atributos["parafuso"]["ponto"][2] for p in par)) for s in par} == {0, 300}
    mont = [b for b in ents if isinstance(b, Barra) and b.papel == "montante" and (b.atributos or {}).get("junto_da_emenda")]
    assert len(mont) == 2
    faces = sorted(round(b.meio[1] + (_faixa_da_secao(b, (0, 1, 0))[1] if b.meio[1] < 3000 else _faixa_da_secao(b, (0, 1, 0))[0]), 1) for b in mont)
    assert faces == [2990.5, 3009.5]                     # cada um encostado na sua chapa
    assert not any(isinstance(b, Barra) and b.papel == "montante" and abs(b.meio[1] - 3000.0) < 1.0 for b in ents)
    diag = [b for b in ents if isinstance(b, Barra) and b.papel == "diagonal" and any(abs(p[1] - 3000.0) < 1 for p in (b.inicio, b.fim))]
    assert len(diag) == 2 and all(max(b.recorte_inicio, b.recorte_fim) > 50 for b in diag)
    sup = [b for b in ents if isinstance(b, Barra) and b.papel == "banzo" and abs(max(b.inicio[2], b.fim[2]) - 5900.0) < 1]
    assert len(sup) == 2 and all(b.cortes_inicio or b.cortes_fim for b in sup)
    assert rt.conferir(ents) == []


def test_ligacao_da_tesoura_no_3d():
    """a ligação no 3D (21/10): a CL no montante onde a VT chega (encostada nele), os furos da aba furando a VT que está
    na frente (os de baixo; os de cima e os do lado sem viga ficam só na chapa); a CL sem recorte que cruza o banzo vira
    apontamento, e a CE de altura errada também"""
    from nucleo3d.modelo import Solido
    from nucleo3d import de_planta_estrutura as DPE
    from nucleo2d.desenho import Linha as L_
    doc = _tesoura_com_emenda()
    ents = list(doc.entidades.values())
    cl = [c for c in ents if isinstance(c, Chapa) and (c.atributos or {}).get("marca") == "CL1"]
    assert len(cl) == 1 and abs(cl[0].origem[1] - 1500.0) < 60 and len(cl[0].furos) == 8
    vt = next(b for b in ents if isinstance(b, Barra) and b.papel == "travamento")
    fur = [s for s in ents if isinstance(s, Solido) and (s.atributos or {}).get("furo", {}).get("peca") == vt.id]
    assert len(fur) == 4 and sorted({round(s.atributos["furo"]["ponto"][0]) for s in fur}) == [210, 270]
    assert sorted({round(s.atributos["furo"]["ponto"][2] - cl[0].origem[2], 1) for s in fur}) == [38.5, 88.5]
    av = doc.metadados["de_planta_estrutura"]["avisos"]
    assert any("CL1 da T2: a chapa cruza o banzo de baixo" in a for a in av)
    assert any("CE1 da T2: a chapa tem 1030 mm" in a for a in av)


def test_hangar_aletas_dos_contraventos_pelo_projeto(hangar):
    """a etapa 8 (21/10): as aletas da folha 34 — AC1 #6,3 140×119 (corte da T2, 48 pç) e AC2 #6,3 135×127 (corte da
    T1, 16 pç), furo Ø15 a 30 mm da borda de fora e a meia altura; o comprimento de corte de cada contravento (CV1
    L=667 cm …) e a rosca (8 cm, 2 porcas + 2 arruelas por ponta) da folha 5"""
    from nucleo3d import identificacao as I
    des, _v = hangar
    r = I.aletas_dos_contraventos(des, I.folhas_com_moldura(des))
    al = {m: (a["tesoura"], a["quantidade"], a["espessura"], a["largura"], a["altura"], a["furos"]) for m, a in r["aletas"].items()}
    assert al == {"AC1": ("T2", 48, 6.3, 140.0, 119.0, [{"x": 30.0, "y": 59.5, "d": 15.0}]),
                  "AC2": ("T1", 16, 6.3, 135.0, 127.0, [{"x": 30.0, "y": 63.5, "d": 15.0}])}
    assert {k: v["comprimento"] for k, v in r["contraventos"].items()} == {
        "CV1": 6670.0, "CV2": 6630.0, "CV3": 6720.0, "CV4": 6690.0, "CV5": 6660.0, "CV6": 6620.0, "CV7": 6710.0, "CV8": 6680.0}
    assert (r["rosca"]["comprimento"], r["rosca"]["porcas"], r["rosca"]["arruelas"]) == (80.0, 2, 2)


def test_aletas_dos_contraventos_no_3d():
    """as aletas no 3D (21/10): em cada ponta de contravento que chega no banzo, a aleta em pé perpendicular à barra na
    planta, com o furo na ponta dela, a meia altura do banzo (a ponta desce até lá); a barra cresce até o comprimento de
    corte do projeto (passa a aleta até as porcas). A aleta que não encosta no banzo e a mais alta que a face onde
    encosta (o U de boca para dentro, como a T1 do Hangar) viram apontamento: 1 das 2 ali não encosta"""
    from nucleo2d.desenho import Linha as L_
    from nucleo3d import regras_trelica as rt
    aleta = {"marca": "AC1", "espessura": 6.3, "largura": 140.0, "altura": 119.0, "furos": [{"x": 30.0, "y": 59.5, "d": 15.0}]}
    barras = [[0, 0, 6000, 0, "banzo_inf"], [0, 600, 3000, 900, "banzo_sup"], [3000, 900, 6000, 600, "banzo_sup"],
              [0, 0, 0, 600, "extremidade"], [6000, 0, 6000, 600, "extremidade"], [3000, 0, 3000, 900, "montante"],
              [0, 600, 3000, 0, "diagonal"], [3000, 0, 6000, 600, "diagonal"]]
    des = Desenho(nome="planta", escala=1.0)
    des.add(L_(camada="E", a=(0.0, 0.0), b=(0.0, 6000.0), atributos={"elemento": "trelica", "material": "aco", "marca": "T1",
               "perfis": {"banzo_sup": "U 127×50×3,00 (FF)", "banzo_inf": "U 127×50×3,00 (FF)", "diagonal": "L 32×3 (FF)", "montante": "L 32×3 (FF)"},
               "nivel_base": 5000, "desenho": {"barras": barras, "vao": 6000, "altura": 900},
               "aletas": {"aleta": aleta, "contraventos": {"CV1": {"comprimento": 4140.0}, "CV2": {"comprimento": 4140.0}}}}))
    for marca, x0, y0 in (("CV1", 130.0, 1000.0), ("CV2", 141.3, 5000.0)):       # o CV2 encosta (63,5 + 110·cos 45°)
        des.add(L_(camada="E", a=(x0, y0), b=(x0 + 2900.0, y0 + 2900.0 * (1 if y0 < 3000 else -1)),
                   atributos={"elemento": "viga", "material": "aco", "papel": "contraventamento", "marca": marca,
                              "secao": {"perfil": "Barra redonda ø 1/2\""}, "nivel_topo": 5080.0, "alinhamento": "eixo"}))
    doc, av = DPE.modelo_da_planta(des, [])
    ents = list(doc.entidades.values())
    al = [c for c in ents if isinstance(c, Chapa) and (c.atributos or {}).get("papel_chapa") == "aleta"]
    assert len(al) == 2
    banzo = next(b for b in ents if isinstance(b, Barra) and (b.atributos or {}).get("papel_trelica") == "banzo_inf")
    from nucleo3d.de_planta_estrutura import _faixa_da_secao
    zlo, zhi = _faixa_da_secao(banzo, (0, 0, 1))
    zc = banzo.inicio[2] + (zlo + zhi) / 2.0
    for c in al:
        cv = next(b for b in ents if isinstance(b, Barra) and (b.atributos or {}).get("marca") == c.atributos["contravento"])
        d = cv.direcao
        assert abs(c.eixo_x[0] * d[0] + c.eixo_x[1] * d[1]) < 1e-6          # em pé, perpendicular à barra na planta
        furo = tuple(c.origem[k] + c.eixo_x[k] * 30.0 + (0, 0, 1)[k] * 59.5 for k in range(3))
        assert abs(furo[2] - zc) < 0.5                                       # a meia altura do banzo
        ponta = cv.inicio if abs(cv.inicio[0]) < 500 else cv.fim
        perp = [furo[k] - ponta[k] for k in range(3)]
        dot = sum(perp[k] * d[k] for k in range(3))
        assert math.dist([perp[k] - dot * d[k] for k in range(3)], [0, 0, 0]) < 0.5   # a barra passa no furo
        assert abs(cv.comprimento - 4140.0) < 0.5                            # até as porcas
    assert any("AC1 da T1: 1 de 2 aletas não encostam no banzo" in a for a in av)
    assert any("AC1 da T1: a aleta tem 119 mm e a face do banzo onde ela encosta" in a for a in av)
    assert rt.conferir(ents) == []


def test_hangar_tercas_na_planta(hangar):
    from nucleo3d import identificacao as I
    des, v = hangar
    loc = v["locacao"]
    grav = {k: [{"nome": x["nome"], "pos": x["pos"]} for x in loc["eixos"][k]] for k in ("numeros", "letras")}
    tes = [{"tipo": t["tipo"], "eixos": t["eixos"], "caixa": t["vista"]["caixa"]} for t in v["tesouras"] if t["vista"] and t["eixos"]]
    planta = next(f for f in v["tercas"] if "PLANTA" in f["titulo"])
    r = I.tercas_da_planta(des, planta["caixa"], loc, grav, tes, 6000.0, v["folhas"])
    assert collections.Counter(p["marca"] for p in r["pecas"]) == {"T.C.1": 14, "T.C.3": 14, "T.C.2": 12, "T.C.2-A": 8, "T.C.2-B": 8}
    zs = sorted({p["z_pe"] for p in r["pecas"]})
    assert zs[0] == pytest.approx(6454.5, abs=1) and zs[-1] == pytest.approx(7303.1, abs=1)
    assert all(p["perfil"] == PERFIL for p in r["pecas"])


def test_viga_de_aco_inclinada_pelo_nivel_fim():
    """o contravento no plano do telhado: a ponta b na cota dela (nivel_fim), o papel e a camada dele"""
    des = Desenho(nome="planta", escala=100.0)
    des.add(Linha(camada="ESTRUTURA", a=(0.0, 0.0), b=(4600.0, 4700.0), atributos={
        "elemento": "viga", "material": "aco", "papel": "contraventamento", "marca": "CV1",
        "secao": {"perfil": 'Barra redonda ø 1/2"'}, "nivel_topo": 6415.8, "nivel_fim": 6812.0, "alinhamento": "eixo"}))
    doc = _modelo(des)
    b = next(x for x in doc.entidades.values() if isinstance(x, Barra))
    assert b.papel == "contraventamento" and b.camada == "Contraventamento"
    assert b.inicio[2] == pytest.approx(6415.8) and b.fim[2] == pytest.approx(6812.0)


def test_hangar_contraventos_e_vigas(hangar):
    from nucleo3d import identificacao as I
    des, v = hangar
    loc = v["locacao"]
    grav = {k: [{"nome": x["nome"], "pos": x["pos"]} for x in loc["eixos"][k]] for k in ("numeros", "letras")}
    tes = [{"tipo": t["tipo"], "eixos": t["eixos"], "caixa": t["vista"]["caixa"]} for t in v["tesouras"] if t["vista"] and t["eixos"]]
    r = I.outras_pecas(des, v["folhas"], loc, grav, tes, 6000.0)
    cv = [b for b in r["barras"] if b["papel"] == "contraventamento"]
    assert len(cv) == 32 and collections.Counter(b["marca"] for b in cv) == {"CV%d" % i: 4 for i in range(1, 9)}
    assert sum(1 for b in cv if b["plano"] == "sup" and abs(b["z_a"] - b["z_b"]) > 100) == 16
    assert all(b["perfil"] == 'Barra redonda ø 1/2"' for b in cv)
    assert collections.Counter(t["marca"] for t in r["trelicas"]) == {"VC01": 2, "VC02": 1, "VC03": 2, "VC04": 1}
    assert all(len(t["desenho"]["barras"]) >= 15 for t in r["trelicas"])
    assert sum(1 for b in r["barras"] if b["marca"] == "VT") == 6
    assert any("A DEFINIR" in a and "L 25×25" in a for a in r["avisos"])


def test_original_do_projeto_recebido_nao_vai_ao_chao_do_3d():
    """o Original do projeto recebido é o conjunto das folhas (no Hangar, 36 folhas e 226 m de largura) num sistema que não
    é o da obra: ia para o chão do 3D, espalhado longe do hangar (20/10). O arquitetônico do lançamento continua indo."""
    from nucleo3d import lancamento
    recebido = Desenho(nome="planta-de-lançamento", escala=100.0)
    recebido.metadados = {"lancamento": True, "arquitetonico": {"tipo": "dxf", "recebido": True}}
    arq = Desenho(nome="planta-de-lançamento", escala=100.0)
    arq.metadados = {"lancamento": True, "arquitetonico": {"tipo": "dxf"}}
    assert lancamento.fundo_no_3d(recebido) is False
    assert lancamento.fundo_no_3d(arq) is True
