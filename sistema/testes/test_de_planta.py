# -*- coding: utf-8 -*-
"""Montagem pela planta (nucleo3d/de_planta.py): um projeto recebido pequeno, desenhado
como o do posto — planta estrutural com os nomes nas treliças, elevações com título
"- kX", nota dos perfis e marcas ST, locação dos pilares e planta das terças — vira o
modelo com as quantidades que o próprio desenho pede."""
import math

import pytest

from nucleo2d import reconhecer
from nucleo3d import de_planta

L_TES = 9000.0          # tesoura: 9 m, 1300 de altura numa ponta e 900 na outra
R_PAINEL = 5000.0       # painel curvo: meia volta de raio 5 m
DX_LOC, DY_TER = -100000.0, -60000.0
S_TERCAS = [600.0, 2100.0, 3900.0, 5200.0, 7400.0, 8600.0]   # passo irregular


def linha(a, b, camada="metalica3"):
    return {"tipo": "linha", "camada": camada, "a": [a[0], a[1]], "b": [b[0], b[1]]}


def texto(p, t, altura=2.5, angulo=0.0, camada="REG60-100"):
    return {"tipo": "texto", "camada": camada, "posicao": [p[0], p[1]], "texto": t, "altura": altura,
            "angulo": angulo, "alinhamento": "esquerda", "vertical": "base"}


def ret(x0, y0, x1, y1, camada):
    return {"tipo": "polilinha", "camada": camada, "vertices": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "fechada": True}


def baloes(dx, dy):
    out = []
    for nome, x in (("1", 0.0), ("2", 4500.0), ("3", 9000.0)):
        out += [{"tipo": "circulo", "camada": "Eixo", "centro": [x + dx, 10500.0 + dy], "raio": 250.0},
                texto((x + dx - 80, 10500.0 + dy - 100), nome, camada="Eixo")]
    for nome, y in (("A", 0.0), ("B", 6000.0)):
        out += [{"tipo": "circulo", "camada": "Eixo", "centro": [-3000.0 + dx, y + dy], "raio": 250.0},
                texto((-3000.0 + dx - 80, y + dy - 100), nome, camada="Eixo")]
    return out


def planta():
    ents = []
    for y in (0.0, 6000.0):                    # duas tesouras ao longo de x
        ents += [linha((0.0, y - 50.0), (L_TES, y - 50.0)), linha((0.0, y + 50.0), (L_TES, y + 50.0)),
                 texto((3500.0, y + 150.0), "TESOURA 1")]
    # o painel curvo, da ponta de uma tesoura à outra
    for r in (R_PAINEL - 50.0, R_PAINEL + 50.0):
        ents.append({"tipo": "arco", "camada": "metalica3", "centro": [L_TES, 3000.0], "raio": r,
                     "inicio": 270.0, "fim": 90.0})
    ents.append(texto((L_TES + R_PAINEL + 300.0, 3000.0), "PAINEL 1", angulo=90.0))
    # a viga que liga as pontas das tesouras, do lado reto
    ents += [linha((-100.0, -50.0), (-100.0, 6050.0), "metalica4"), linha((100.0, -50.0), (100.0, 6050.0), "metalica4"),
             texto((-250.0, 1500.0), "VM-2Ue200X70X20X2,65", angulo=90.0)]
    ents.append(texto((2000.0, -4000.0), "PLANTA NO NÍVEL 6,00m", altura=5.0))
    return ents


def locacao():
    ents = []
    for x, y in ((0.0, 0.0), (L_TES, 0.0), (0.0, 6000.0), (L_TES, 6000.0)):
        ents.append(ret(x + DX_LOC - 175, y - 145, x + DX_LOC + 175, y + 145, "Chapas"))
        ents.append(texto((x + DX_LOC + 279, y + 516), "PM1(250X70X25X3,0)"))
    ents.append(texto((2000.0 + DX_LOC, -4000.0), "LOCAÇÃO / CARGAS", altura=5.0))
    return ents


def plantas_das_tercas():
    ents = []
    for s in S_TERCAS:
        # a obra tem a ponta alta da tesoura em x = 9000: a terça que na elevação fica a
        # s da ponta esquerda (a alta) está em x = 9000 − s na planta
        x = L_TES - s
        ents.append(linha((x, -300.0 + DY_TER), (x, 6300.0 + DY_TER), "1-Terça Eixo"))
        ents.append(texto((x + 60.0, 3000.0 + DY_TER), "TC1", angulo=90.0, camada="1-Terça"))
    ents.append(texto((2000.0, -4000.0 + DY_TER), "PLANTA NO NÍVEL DAS TERÇAS", altura=5.0))
    ents.append(texto((-20000.0, -20000.0), "TC1-U100X40X2,65 - 12X"))
    return ents


def elevacao_tesoura(x0, y0):
    """TESOURA 1 - 2X: alta à esquerda (1300), baixa à direita (900)"""
    def topo(x):
        return 1300.0 + (900.0 - 1300.0) * x / L_TES
    ents = [linha((x0, y0), (x0 + L_TES, y0), "metalica3"), linha((x0, y0 + 40), (x0 + L_TES, y0 + 40), "metalica3"),
            linha((x0, y0 + topo(0)), (x0 + L_TES, y0 + topo(L_TES))),
            linha((x0, y0 + topo(0) + 40), (x0 + L_TES, y0 + topo(L_TES) + 40))]
    xs = [0.0, 1500.0, 3000.0, 4500.0, 6000.0, 7500.0, L_TES]
    for i, x in enumerate(xs):
        ents.append(linha((x0 + x, y0 + 40), (x0 + x, y0 + topo(x)), "metalica2"))
        if i + 1 < len(xs):
            ents.append(linha((x0 + x, y0 + 40), (x0 + xs[i + 1], y0 + topo(xs[i + 1])), "metalica2"))
    for s in S_TERCAS:                    # marca ST2 com a chamada até o apoio
        tx, ty = x0 + s - 420.0, y0 + topo(s) + 250.0
        ents.append(texto((tx, ty), "ST2", camada="metalica2"))
        ents.append(linha((tx + 10.0, ty - 20.0), (tx + 360.0, ty - 20.0), "1-Metalica2"))
        ents.append(linha((tx + 360.0, ty - 20.0), (x0 + s, y0 + topo(s) + 45.0), "1-Metalica2"))
    ents += [texto((x0, y0 - 300.0), "BANZO U100X40X2,25"),
             texto((x0, y0 - 450.0), 'DIAGONAIS E MONTANTES 2L 1"X1/8"  3 PRELILHAS L 1"X1/8"'),
             texto((x0, y0 - 700.0), "TESOURA 1 - 2X", altura=3.5)]
    return ents


def elevacao_painel(x0, y0):
    L = math.pi * R_PAINEL
    ents = [linha((x0, y0), (x0 + L, y0)), linha((x0, y0 + 40), (x0 + L, y0 + 40)),
            linha((x0, y0 + 1560), (x0 + L, y0 + 1560)), linha((x0, y0 + 1600), (x0 + L, y0 + 1600))]
    n = 10
    for i in range(n + 1):
        x = L * i / n
        ents.append(linha((x0 + x, y0 + 40), (x0 + x, y0 + 1560), "metalica2"))
    ents += [texto((x0, y0 - 300.0), "BANZO U100X40X2,25"),
             texto((x0, y0 - 450.0), 'DIAGONAIS E MONTANTES 2L 1"X1/8"'),
             texto((x0, y0 - 700.0), "PAINEL 1 - 1X", altura=3.5)]
    return ents


@pytest.fixture(scope="module")
def resultado():
    ents = planta() + locacao() + plantas_das_tercas() + baloes(0, 0) + baloes(DX_LOC, 0) + baloes(0, DY_TER)
    ents += elevacao_tesoura(0.0, -120000.0) + elevacao_painel(20000.0, -120000.0)
    return de_planta.montar(ents, {"nivel": 6000.0, "origem": False})


def test_le_os_perfis_da_nota_da_elevacao():
    r = reconhecer.perfil_do_texto('DIAGONAIS E MONTANTES 2L 1"X1/8"  3 PRELILHAS L 1"X1/8"')
    assert r["mult"] == 2 and r["perfil"] == 'L 1"×1/8"'
    p = reconhecer.perfil_do_texto("PM3(200X70X20X2,65)")
    assert p["perfil"] == "Ue 200×70×20×2,65" and p["papel"] == "pilar"


def test_quantidades_conferem_com_o_titulo(resultado):
    conf = {c["peca"]: c for c in resultado["conferencia"]}
    assert conf["TESOURA 1"]["modelo"] == 2 and conf["TESOURA 1"]["ok"]
    z = resultado["resumo"]
    assert z["pilares"] == 4
    assert z["vigas"] == 1
    assert z["tercas"] == len(S_TERCAS)
    assert z["projeto"]["tercas"] == 12


def test_painel_curvo_sai_calandrado(resultado):
    doc = resultado["doc"]
    cal = [e for e in doc.solidos if (e.atributos or {}).get("calandrada")]
    assert len(cal) == 2                                   # banzo de baixo e de cima
    assert abs(cal[0].atributos["calandrada"]["raio"] - R_PAINEL) < 1.0
    assert cal[0].atributos["marcas"]["perfil"] == "U 100×40×2,25 (FF)"


def test_sentido_da_tesoura_pelas_marcas_de_terca(resultado):
    """as marcas ST caem nos cruzamentos das terças só no sentido invertido: a ponta alta
    (1300) vai para x = 9000, onde a planta das terças diz que ela está"""
    doc = resultado["doc"]
    assert resultado["resumo"]["orientacao"]["pelas_marcas"] >= 2
    banzos = [b for b in doc.barras if b.papel == "banzo" and max(b.inicio[2], b.fim[2]) > 6500.0]
    assert banzos
    b = max(banzos, key=lambda b: b.comprimento)
    alto, baixo = (b.inicio, b.fim) if b.inicio[2] > b.fim[2] else (b.fim, b.inicio)
    assert alto[0] > baixo[0]
    assert abs(alto[2] - 6000.0 - 1300.0) < 30.0


def test_terca_senta_no_banzo_superior(resultado):
    doc = resultado["doc"]
    tercas = [b for b in doc.barras if b.papel == "terça"]
    assert tercas
    t = min(tercas, key=lambda b: abs(b.inicio[0] - (L_TES - S_TERCAS[0])))
    # banzo superior a 1300 − (1300 − 900) · s / L acima do nível, + meio banzo + meia terça
    s = S_TERCAS[0]
    esperado = 6000.0 + 1300.0 + (900.0 - 1300.0) * s / L_TES + 20.0 + 50.0
    assert abs(t.inicio[2] - esperado) < 40.0


def test_pilares_no_lugar_da_planta(resultado):
    doc = resultado["doc"]
    pil = sorted((round(b.inicio[0]), round(b.inicio[1])) for b in doc.barras if b.papel == "pilar")
    assert pil == [(0, 0), (0, 6000), (9000, 0), (9000, 6000)]
    assert all(b.fim[2] == 6000.0 for b in doc.barras if b.papel == "pilar")


def test_modelo_vem_para_perto_da_origem():
    ents = planta() + locacao() + plantas_das_tercas() + baloes(0, 0) + baloes(DX_LOC, 0) + baloes(0, DY_TER)
    ents += elevacao_tesoura(0.0, -120000.0) + elevacao_painel(20000.0, -120000.0)
    longe = [dict(e) for e in ents]
    for e in longe:                       # a obra desenhada a 400 m do zero do DXF
        for k in ("a", "b", "centro", "posicao"):
            if k in e:
                e[k] = [e[k][0] + 400000.0, e[k][1] + 50000.0]
        if "vertices" in e:
            e["vertices"] = [[v[0] + 400000.0, v[1] + 50000.0] for v in e["vertices"]]
    r = de_planta.montar(longe, {"nivel": 6000.0})
    xs = [c for b in r["doc"].barras for c in (b.inicio[0], b.fim[0])]
    ys = [c for b in r["doc"].barras for c in (b.inicio[1], b.fim[1])]
    assert 0.0 <= min(xs) < 1000.0 and 0.0 <= min(ys) < 1000.0
    d = r["doc"].metadados["de_planta"]["deslocamento"]
    assert d["x"] < -390000.0 and d["y"] < -40000.0


def test_outra_planta_no_seu_nivel():
    """o mezanino (outra planta, com balões em comum) entra no nível dele: a viga VM com o
    topo em 3,17 m"""
    DX = 100000.0
    mez = [linha((0.0 + DX, 2950.0), (L_TES + DX, 2950.0), "metalica4"), linha((0.0 + DX, 3050.0), (L_TES + DX, 3050.0), "metalica4"),
           texto((3000.0 + DX, 3150.0), "VM-2Ue150X70X20X2,65"), texto((2000.0 + DX, -4000.0), "PLANTA NO NÍVEL 3,17m", altura=25.0)]
    ents = planta() + locacao() + plantas_das_tercas() + baloes(0, 0) + baloes(DX_LOC, 0) + baloes(0, DY_TER)
    ents += baloes(DX, 0) + mez + elevacao_tesoura(0.0, -120000.0) + elevacao_painel(20000.0, -120000.0)
    r = de_planta.montar(ents, {"nivel": 6000.0, "origem": False,
                                "outras": [{"planta": "PLANTA NO NÍVEL 3,17m", "nivel": 3170.0}]})
    assert r["resumo"]["outras_plantas"] and r["resumo"]["outras_plantas"][0]["baloes"] >= 2
    vigas = [b for b in r["doc"].barras if b.papel == "viga" and abs(b.inicio[1] - 3000.0) < 200.0]
    assert len(vigas) == 2                                  # 2Ue: os dois perfis
    assert all(abs(b.inicio[2] - (3170.0 - 75.0)) < 1.0 for b in vigas)
    assert any(n["nome"] == "NÍVEL 3,17" for n in r["niveis"])


# ------------------------------------------------------------------ leitura mais firme (0.8.36)

def test_trecho_de_cada_nome_entre_dois_nos():
    """o nome perto da ponta (não no meio) fica com o trecho entre dois nós que tem o
    comprimento da elevação; os vizinhos não disputam o mesmo trecho"""
    nos = [0.0, 1500.0, 4000.0, 9000.0]
    faixas = de_planta._escolher_trechos(9000.0, nos, [(200.0, 1500.0), (4300.0, 5000.0)])
    assert faixas == [(0.0, 1500.0), (4000.0, 9000.0)]


def test_dois_paineis_dividem_o_vao_sem_no_no_meio():
    faixas = de_planta._escolher_trechos(8340.0, [0.0, 8340.0], [(700.0, 3500.0), (5000.0, 4600.0)])
    (a0, a1), (b0, b1) = faixas
    assert a0 == 0.0 and abs(a1 - 3500.0) < 1.0 and abs(b1 - 8340.0) < 1.0 and b0 >= a1


def test_viga_segue_pelo_pedaco_sem_nome_e_nao_duplica():
    c = de_planta.Caminho("reta", a=(0.0, 0.0), b=(10000.0, 0.0), largura=100.0)
    pedacos = [de_planta.Caminho("reta", a=(0.0, 0.0), b=(5000.0, 0.0)),
               de_planta.Caminho("reta", a=(5150.0, 0.0), b=(10000.0, 0.0))]
    t1, t2 = {"texto": "VM-2Ue150X70X20X2,65"}, {"texto": "VM-2Ue150X70X20X2,65"}
    rot = [(7000.0, t1["texto"], t1), (7600.0, t2["texto"], t2)]
    f = de_planta._faixas_das_vigas(c, rot, pedacos)
    assert len(f) == 1                                   # o nome repetido não vira outra viga
    assert f[id(t1)] == (0.0, 10000.0)                   # e a viga vai até o pilar do outro lado


def test_terca_termina_no_apoio():
    """a terça que passa 0,8 m da tesoura é aparada nela; a que encosta no painel da borda
    termina na face dele"""
    def trecho(y, familia):
        return de_planta.Trecho(caminho=de_planta.Caminho("reta", a=(-3000.0, y), b=(3000.0, y), largura=100.0),
                                nome=familia + " 1", familia=familia)
    ts = [trecho(0.0, "TESOURA"), trecho(5000.0, "PAINEL")]
    polis = [(t, de_planta._polilinha(t.caminho)) for t in ts]
    caixas = [de_planta._caixa_pts(p, 300.0) for _t, p in polis]
    s0, s1, cruz = de_planta._pontas_da_terca((0.0, -800.0), (0.0, 5200.0), polis, caixas)
    assert abs(s0 - 800.0) < 1.0                          # aparada no eixo da tesoura
    assert abs(s1 - (5800.0 - 50.0)) < 1.0                # na face do painel (meia largura 50)


def test_viga_vm_escrita_duas_vezes_da_uma_viga():
    ents = planta() + [texto((-250.0, 4000.0), "VM-2Ue200X70X20X2,65", angulo=90.0)]
    ents += locacao() + plantas_das_tercas() + baloes(0, 0) + baloes(DX_LOC, 0) + baloes(0, DY_TER)
    ents += elevacao_tesoura(0.0, -120000.0) + elevacao_painel(20000.0, -120000.0)
    r = de_planta.montar(ents, {"nivel": 6000.0, "origem": False})
    vigas = [b for b in r["doc"].barras if b.papel == "viga"]
    assert len(vigas) == 2                                # 2Ue: os dois perfis, uma vez só


def test_barras_da_trelica_sabem_de_qual_trelica_sao(resultado):
    pecas = {(b.atributos or {}).get("origem", {}).get("peca") for b in resultado["doc"].barras if b.camada == "Treliças"}
    assert None not in pecas and len(pecas) == 3          # duas tesouras e o painel


# ------------------------------------------------------------------ prints do Posto CB (0.8.38)

def test_banzo_de_cima_com_as_abas_para_baixo(resultado):
    """o U do banzo fica deitado com as abas para dentro da treliça: o de cima com a alma em
    cima (onde a terça apoia) e as abas para baixo; o de baixo com as abas para cima"""
    from nucleo3d.geometria import base_local
    banzos = [b for b in resultado["doc"].barras if b.papel == "banzo"
              and "TESOURA" in (b.atributos or {}).get("origem", {}).get("peca", "")]
    assert banzos
    for b in banzos:
        u, _v, _w = base_local(tuple(b.fim[i] - b.inicio[i] for i in range(3)), b.rotacao)
        de_cima = (b.inicio[2] + b.fim[2]) / 2 > 6000.0 + 400.0
        assert (u[2] < -0.9) if de_cima else (u[2] > 0.9)   # u: o lado das abas do U


def test_viga_vai_ate_o_pilar_na_linha_dela():
    """a ponta que para 17 cm antes do pilar (e 17 cm de lado) vai até a face dele; a outra
    ponta, com o pilar 38 cm de lado da linha, é do desenho e fica como está"""
    pts = de_planta._viga_ate_o_pilar([(0.0, 0.0), (7000.0, 0.0)], [(7170.0, 175.0, 100.0), (-50.0, 380.0, 100.0)])
    assert abs(pts[1][0] - 7070.0) < 1.0 and abs(pts[1][1]) < 1e-6
    assert pts[0] == (0.0, 0.0)
    # a que já chega no pilar não é puxada até o pilar seguinte
    pts = de_planta._viga_ate_o_pilar([(0.0, 0.0), (7000.0, 0.0)], [(7080.0, 0.0, 100.0), (7400.0, 0.0, 100.0)])
    assert pts[1] == (7000.0, 0.0)


def test_viga_lida_duas_vezes_entra_uma_vez():
    feitas = [([(0.0, 0.0), (7000.0, 0.0)], 3000.0, "Ue 250×70×20×2,65")]
    assert de_planta._viga_repetida([(10.0, 30.0), (6990.0, 20.0)], 3000.0, "Ue 250×70×20×2,65", feitas)
    assert not de_planta._viga_repetida([(0.0, 0.0), (7000.0, 0.0)], 6000.0, "Ue 250×70×20×2,65", feitas)   # outro nível
    assert not de_planta._viga_repetida([(0.0, 400.0), (7000.0, 400.0)], 3000.0, "Ue 250×70×20×2,65", feitas)  # outra linha
    assert not de_planta._viga_repetida([(5000.0, 0.0), (9000.0, 0.0)], 3000.0, "Ue 250×70×20×2,65", feitas)  # só encosta


def test_faixa_de_trelica_vista_de_cima():
    """os dois banzos a 1,5 m e a alma entre eles (montantes e diagonais): é a treliça deitada,
    longe da origem do desenho (o Posto CB fica a 400 m do zero), com o nome da elevação de
    mesma altura e comprimento"""
    X0, Y0 = 400000.0, 50000.0
    ang = math.radians(56.0)
    u, n = (math.cos(ang), math.sin(ang)), (-math.sin(ang), math.cos(ang))

    def P(s, f):
        return (X0 + u[0] * s + n[0] * f, Y0 + u[1] * s + n[1] * f)
    segs = [de_planta._Seg(P(0, 0), P(6000, 0), "m"), de_planta._Seg(P(0, 1500), P(6000, 1500), "m")]
    for k in range(6):
        segs.append(de_planta._Seg(P(k * 1000, 0), P(k * 1000, 1500), "m"))
        segs.append(de_planta._Seg(P(k * 1000, 0), P((k + 1) * 1000, 1500), "m"))
    segs.append(de_planta._Seg(P(6000, 0), P(6000, 1500), "m"))
    el = de_planta.Elevacao(nome="TRELICA 1", familia="TRELICA", qtd=1, comprimento=6000.0)
    el.membros = [de_planta.Membro(0.0, 0.0, 6000.0, 0.0, "banzo"), de_planta.Membro(0.0, 1550.0, 6000.0, 1550.0, "banzo")]
    textos = [{"tipo": "texto", "texto": "TRELIÇA 1", "posicao": P(2500, -300), "angulo": 56.0, "id": "r1"}]
    trs, usados, faixas = de_planta._trelicas_deitadas(segs, textos, {"TRELICA 1": el}, lambda t: "TRELICA 1")
    assert len(faixas) == 1 and abs(faixas[0][4] - faixas[0][3] - 1500.0) < 5.0
    assert [t.nome for t in trs] == ["TRELICA 1"] and abs(trs[0].caminho.comprimento - 6000.0) < 5.0


def test_encaixe_de_cada_bloco_no_vao(resultado):
    """cada treliça entra como a elevação desenha; a diferença para o vão da planta é medida"""
    enc = resultado["encaixe"]
    tes = [e for e in enc if e["peca"] == "TESOURA 1"]
    assert len(tes) == 2 and all(abs(e["vao"] - e["elevacao"]) == abs(e["dif"]) for e in tes)
    z = resultado["resumo"]["encaixe"]
    assert z["blocos"] == len(enc) and z["a_conferir"] == sum(1 for e in enc if e.get("a_conferir"))


def test_baloes_encostados_um_texto_por_balao():
    """eixos 9 e 10 do Posto CB: balões a 51 cm, o texto "10" cabe nos dois — cada um fica com o seu"""
    ents = [{"tipo": "circulo", "camada": "Eixo", "centro": [0.0, 0.0], "raio": 246.0},
            {"tipo": "circulo", "camada": "Eixo", "centro": [510.0, 0.0], "raio": 246.0},
            texto((-102.0, -104.0), "9", camada="Eixo"), texto((245.0, -104.0), "10", camada="Eixo")]
    b = de_planta.baloes(ents, (-1000.0, -1000.0, 1000.0, 1000.0))
    assert b["9"] == (0.0, 0.0) and b["10"] == (510.0, 0.0)


def test_avisos_dizem_os_eixos():
    eixos = {"eixo_g": [1.0, 0.0], "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6000.0}],
             "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 5000.0}]}
    # coordenada do desenho (o modelo é o desenho + desl)
    av = de_planta.avisos_pelos_eixos(["pilar P1 em (106010; 202500) a 7.5 m"], eixos, desl=(-100000.0, -200000.0))
    assert av == ["pilar P1 em (eixo 2 / entre A e B — 6,01; 2,50 m) a 7,5 m"]


def test_trelicas_lidas_cada_elevacao_com_o_desenho_e_as_copias(resultado):
    """a tela Treliças lidas: a elevação no referencial dela (s, h), o desenho do projetista na
    mesma moldura e as cópias colocadas, com os eixos"""
    tl = {t["nome"]: t for t in resultado["trelicas"]}
    t = tl["TESOURA 1"]
    assert t["qtd_projeto"] == 2 and t["no_modelo"] == 2 and t["situacao"] in ("ok", "conferir")
    assert t["membros"] and all(len(m) == 6 for m in t["membros"])
    assert min(min(m[1], m[3]) for m in t["membros"]) >= -1 and max(max(m[1], m[3]) for m in t["membros"]) <= t["comprimento"] + 1
    assert any(d["t"] == "x" and d["s"].startswith("TESOURA 1") for d in t["desenho"])        # o título dela
    assert not any(d["t"] == "x" and d["s"].startswith("PAINEL 1 -") for d in t["desenho"])   # não o de outra
    # (o desenho de teste não tem as linhas dos eixos: "onde" fica vazio e a tela mostra a coordenada)
    assert len(t["colocadas"]) == 2 and all("onde" in c and len(c["ponto"]) == 2 for c in t["colocadas"])
    assert "PAINEL 1" in tl


def _el(membros, banzo=None):
    el = de_planta.Elevacao(nome="TRANSICAO 1", familia="TRANSICAO", qtd=1, comprimento=6000.0)
    el.membros = membros
    el.banzo = banzo
    return el


def test_alma_desenhada_duas_vezes_entra_uma():
    """a 2L com linha dupla de nó a nó e mais uma linha ao lado (a 50 mm) é uma barra; os dois
    montantes da cumeeira, a 150 mm, são dois"""
    M = de_planta.Membro
    el = _el([M(1000, 0, 2000, 1500, "diagonal", 35.0), M(1050, 100, 1950, 1400, "diagonal"),
              M(3000, 0, 3000, 1500, "montante"), M(3150, 0, 3150, 1500, "montante")])
    assert de_planta._alma_lida_duas_vezes(el) == 1
    assert sorted((m.papel, m.altura_linha) for m in el.membros) == [("diagonal", 35.0), ("montante", 0.0), ("montante", 0.0)]


def test_banzo_em_caixao_vira_um_banzo_no_eixo_da_junta():
    """2Ue 250×70: três linhas compridas por caixão (as faces a 140 mm e a junta no meio) → um banzo
    por caixão, no eixo da junta; a base passa a ser o eixo do caixão de baixo"""
    M = de_planta.Membro
    el = _el([M(0, 0, 6000, 0, "banzo", 70.0), M(0, 155, 6000, 155, "banzo", 100.0),
              M(0, 1375, 6000, 1375, "banzo", 100.0), M(0, 1530, 6000, 1530, "banzo", 70.0),
              M(1000, -40, 2000, 1570, "diagonal", 35.0)],
             banzo={"perfil": "Ue 250×70×25×4,75", "mult": 2, "trecho": "2UE 250X70X25X4,75"})
    segs = [((0.0, h), (6000.0, h), "metalica3") for h in (-35.0, 35.0, 105.0, 1425.0, 1495.0, 1565.0)]
    assert de_planta._banzo_em_caixao(el, segs) == 2
    ban = sorted((round(m.h0), round(m.caixa)) for m in el.membros if m.papel == "banzo")
    assert ban == [(0, 140), (1460, 140)] and round(el.y_base) == 35
    assert de_planta._meio_caixao("Ue 250×70×25×4,75") == pytest.approx(51.0, abs=1.0)


def test_largura_da_linha_dupla_decide_o_perfil_da_alma():
    assert de_planta._largura_do_perfil(40.0, "U 100×40×2,25 (FF)")          # o montante de ponta em U
    assert not de_planta._largura_do_perfil(35.0, "Ue 250×70×25×4,75")       # a 2L desenhada dupla


def test_emenda_liga_os_banzos_das_duas_partes():
    M = de_planta.Membro
    el = _el([M(0, 0, 12120, 0, "banzo"), M(12390, 0, 32122, 0, "banzo"), M(0, 1500, 12120, 1500, "banzo")])
    el.comprimento = 32122.0
    de_planta._ligar_emenda(el, 12120.0, 12390.0)
    assert sorted((round(m.s0), round(m.s1)) for m in el.membros if m.h0 == 0) == [(0, 12255), (12255, 32122)]
    assert "duas partes" in el.avisos[-1]


def test_sentido_pelo_cruzamento_na_emenda():
    """a TRANSIÇÃO 2 do Posto CB: a elevação tem a junta dos banzos (emenda de 250 mm) a 9,74 m da
    ponta esquerda; na planta, a TRANSIÇÃO 1 atravessa a linha dela a 9,74 m da ponta sul — a ponta
    esquerda vai para o sul (o encontro dos banzos tinha invertido)"""
    M = de_planta.Membro
    el = de_planta.Elevacao(nome="TRANSICAO 2", familia="TRANSICAO", qtd=1, comprimento=16625.0)
    el.membros = [M(0, 0, 9614, 0, "banzo"), M(9864, 0, 16625, 0, "banzo"), M(9614, 20, 9864, 20, "banzo"),
                  M(0, 700, 9614, 700, "banzo"), M(9864, 700, 16625, 700, "banzo")]
    assert [round(j) for j in de_planta._juntas_dos_banzos(el)] == [9739]
    C = de_planta.Caminho
    t2 = de_planta.Trecho(caminho=C("reta", a=(21370.0, 26333.0), b=(21370.0, 9708.0)), nome="TRANSICAO 2", familia="TRANSICAO", elevacao=el)
    el1 = de_planta.Elevacao(nome="TRANSICAO 1", familia="TRANSICAO", qtd=1, comprimento=35850.0)
    el1.membros = [M(0, 0, 35850, 0, "banzo"), M(0, 1460, 35850, 1460, "banzo")]
    t1 = de_planta.Trecho(caminho=C("reta", a=(1000.0, 19448.0), b=(36850.0, 19448.0)), nome="TRANSICAO 1", familia="TRANSICAO", elevacao=el1)
    assert [round(s) for s in de_planta._cruzamentos(t2, [t1, t2])] == [6885]
    r = de_planta.orientar([t2, t1])
    assert r["pelo_cruzamento"] == 1 and t2.sentido_por == "cruzamento na emenda"
    # a ponta esquerda da elevação (s = 0) na ponta sul (y = 9708)
    assert abs(t2.caminho.ponto(de_planta._s_na_planta(t2, 0.0))[1] - 9708.0) < 1.0


def test_pilar_vai_para_a_secao_da_planta():
    """a planta estrutural desenha a seção do pilar (os dois U de 400 × 200, costas com costas) a
    0,72 m de onde a locação o põe: vale a planta (os três PM6 do Posto CB), com aviso"""
    def u(x0, y0, y1):
        return {"tipo": "polilinha", "camada": "metalica4", "fechada": False,
                "vertices": [[x0 + 50, y0], [x0, y0], [x0, y1], [x0 + 400, y1], [x0 + 400, y0], [x0 + 350, y0]]}
    ents = [u(1000.0, 5000.0, 5200.0), u(1000.0, 5000.0, 4800.0)]           # centro (1200; 5000)
    locados = [{"x": 500.0, "y": 4840.0, "nome": "PM6(400X200X50X3,75)", "perfil": "Ue 400×200×50×3,75"},
               {"x": 9000.0, "y": 9000.0, "nome": "PM3(200X70X20X2,65)", "perfil": "Ue 200×70×20×2,65"}]
    avisos = []
    assert de_planta._pilares_pela_planta(ents, (0.0, 0.0, 20000.0, 20000.0), locados, avisos) == 1
    assert (round(locados[0]["x"]), round(locados[0]["y"])) == (1200, 5000) and "pela_planta" in locados[0]
    assert (locados[1]["x"], locados[1]["y"]) == (9000.0, 9000.0) and len(avisos) == 1


def test_elevacao_desenhada_junto_separa_na_emenda():
    """a elevação "TRANSIÇÃO 2" do Posto CB desenha a TRANSIÇÃO 3 depois da emenda: a parte de
    depois vira a TRANSIÇÃO 3 (com a emenda no começo) e a TRANSIÇÃO 2 fica com a de antes"""
    M = de_planta.Membro
    el = de_planta.Elevacao(nome="TRANSICAO 2", familia="TRANSICAO", qtd=1, comprimento=16625.0)
    el.membros = [M(0, 0, 9614, 0, "banzo"), M(9864, 0, 16625, 0, "banzo"),
                  M(0, 700, 9614, 700, "banzo"), M(9864, 700, 16625, 700, "banzo"),
                  M(1000, 0, 1000, 700, "montante"), M(12000, 0, 12000, 700, "montante")]
    el.marcas_terca = [3000.0, 13000.0]
    elevacoes = {"TRANSICAO 2": el}
    avisos = []
    de_planta._dividir(el, [(0.0, 9614.0), (9864.0, 16625.0)], 1, "TRANSICAO 3", 2, elevacoes, avisos)
    t3 = elevacoes["TRANSICAO 3"]
    assert t3.qtd == 2 and round(t3.comprimento) == 6761 and t3.emenda == "inicio" and t3.parte_de == "TRANSICAO 2"
    assert round(el.comprimento) == 9614 and el.emenda == "fim"
    assert [round(m.s0) for m in t3.membros if m.papel == "montante"] == [2136]
    assert [round(m.s0) for m in el.membros if m.papel == "montante"] == [1000]
    assert [round(s) for s in t3.marcas_terca] == [3136] and el.marcas_terca == [3000.0]


def test_ponta_da_emenda_vai_para_a_trelica_que_passa():
    """a TRANSIÇÃO 3 (emenda no começo da elevação) entre a TRANSIÇÃO 1, que passa por uma ponta
    dela, e o nada: s = 0 fica na ponta da TRANSIÇÃO 1"""
    M = de_planta.Membro
    C = de_planta.Caminho
    el3 = de_planta.Elevacao(nome="TRANSICAO 3", familia="TRANSICAO", qtd=1, comprimento=6761.0)
    el3.membros = [M(0, 0, 6761, 0, "banzo"), M(0, 700, 6761, 700, "banzo")]
    el3.emenda = "inicio"
    t3 = de_planta.Trecho(caminho=C("reta", a=(21370.0, 26333.0), b=(21370.0, 19572.0)), nome="TRANSICAO 3",
                          familia="TRANSICAO", elevacao=el3)
    el1 = de_planta.Elevacao(nome="TRANSICAO 1", familia="TRANSICAO", qtd=1, comprimento=35850.0)
    el1.membros = [M(0, 0, 35850, 0, "banzo"), M(0, 1460, 35850, 1460, "banzo")]
    t1 = de_planta.Trecho(caminho=C("reta", a=(1000.0, 19448.0), b=(36850.0, 19448.0)), nome="TRANSICAO 1",
                          familia="TRANSICAO", elevacao=el1)
    de_planta.orientar([t3, t1])
    assert t3.sentido_por == "emenda na treliça que passa"
    assert abs(t3.caminho.ponto(de_planta._s_na_planta(t3, 0.0))[1] - 19572.0) < 1.0


def test_perfil_de_apoio_das_tercas_dos_dois_lados():
    """a TRANSIÇÃO 1 do Posto CB: a linha dupla inclinada, no caimento do telhado, com a nota
    "U100X40X2,25 NO EIXO DA TRELIÇA" ao lado, não é a tesoura vista ao fundo — volta como o
    apoio das terças, com o perfil da nota"""
    M = de_planta.Membro
    el = _el([M(0, 0, 8600, 0, "banzo"), M(0, 1460, 8600, 1460, "banzo")])
    el.fundo = [M(50, 800, 8670, 1270, "banzo", 40.0), M(2000, 300, 2000, 1400, "montante")]
    notas = [{"texto": "U100X40X2,25", "posicao": [4000.0, 1300.0]}, {"texto": "NO EIXO DA TRELIÇA", "posicao": [4000.0, 1200.0]},
             {"texto": "BANZO 2UE250X70X25X4,75", "posicao": [4000.0, -300.0]}]
    assert de_planta._apoio_das_tercas(el, notas) == 1
    assert el.apoio_terca["perfil"].startswith("U 100") and [m.papel for m in el.membros].count("apoio_terca") == 1
    assert len(el.fundo) == 1 and "um de cada lado" in el.avisos[-1]
    # dos lados: a alma do U encosta na face do banzo (a meia altura do Ue 250 mais o centroide do U)
    assert 125.0 + 5.0 < de_planta._lado_do_apoio("Ue 250×70×25×4,75", "U 100×40×2,25 (FF)") < 125.0 + 20.0
    # sem a nota, fica de fundo
    el2 = _el([])
    el2.fundo = [M(50, 800, 8670, 1270, "banzo", 40.0)]
    assert de_planta._apoio_das_tercas(el2, []) == 0 and el2.apoio_terca is None


def test_camada_de_cada_outra_planta():
    assert de_planta.camada_da_outra("PLANTA NO NÍVEL 3,17m", 3170.0, 6000.0) == "Mezanino"
    assert de_planta.camada_da_outra("PLANTA DA BASE DA CX DÁGUA NIVEL 8,20", 8200.0, 6000.0) == "Caixa d'água 8,20"
    assert de_planta.camada_da_outra("COBERTURA DA CX DÁGUA NIVEL 11,00", 11000.0, 6000.0) == "Caixa d'água 11,00"
    assert de_planta.camada_da_outra("PLANTA NO NÍVEL 9,00", 9000.0, 6000.0) == "Nível 9,00"
    assert de_planta.camada_da_outra("PLANTA NO NÍVEL 3,17m", 3170.0, 6000.0, "Mezanino da loja") == "Mezanino da loja"


def test_emenda_com_a_trelica_que_passa_em_corte():
    """a junta TRANSIÇÃO 2 | 3 do Posto CB: no vão da emenda (9647–9864) a elevação desenha a
    TRANSIÇÃO 1 em corte (lados de −50 a 1410) e, em cima dela, os U de ponta das tesouras (1550 a
    2350); a ponta da viga da TRANSIÇÃO 3 perdeu uma das linhas do U para o lado da treliça em corte"""
    M = de_planta.Membro
    el = de_planta.Elevacao(nome="TRANSICAO 2", familia="TRANSICAO", qtd=1, comprimento=16625.0)
    el.banzo = {"perfil": "U 200×100×6,35 (FF)", "mult": 1}
    el.membros = [M(0, 0, 9614, 0, "banzo"), M(9898, 0, 16625, 0, "banzo"), M(0, 700, 9614, 700, "banzo"),
                  M(9898, 700, 16625, 700, "banzo"), M(1697, 1001, 9647, 2301, "banzo"), M(9864, 2301, 16625, 1001, "banzo"),
                  M(9564, -111, 9564, 750, "montante", 100.0),                   # o U da viga da TRANSIÇÃO 2
                  M(9658, 90, 9658, 1410, "montante"), M(9622, -50, 9622, 1410, "montante"),   # a TRANSIÇÃO 1 em corte
                  M(9855, 90, 9855, 1410, "montante"), M(9890, -50, 9890, 1410, "montante"),
                  M(9689, 1550, 9689, 2350, "montante"), M(9873, 1550, 9873, 2350, "montante"),  # os U em cima
                  M(9998, 50, 9998, 650, "montante"),                              # a linha que sobrou do U da viga
                  M(12000, 0, 12000, 700, "montante")]
    assert de_planta._limpar_emenda(el, 9647.0, 9864.0) == 4
    em_pe = sorted((round(m.s0), round(m.h0), round(m.h1), m.altura_linha) for m in el.membros if m.papel == "montante")
    assert em_pe == [(9564, -111, 750, 100.0), (9689, 1550, 2350, 100.0), (9873, 1550, 2350, 100.0),
                     (9948, 0, 700, 100.0), (12000, 0, 700, 0.0)]


def test_terca_nao_senta_no_frontao_da_elevacao_em_duas_pecas():
    # a TRANSIÇÃO 2 do Posto CB: viga de transição (banzos retos em 0 e 1100) e, em cima dela, a
    # tesoura de duas águas até 2300 — o frontão "revestir com telha ou rufo" (corte BB): a telha
    # passa reta embaixo dele, e a terça senta no topo da viga
    M = de_planta.Membro
    el = de_planta.Elevacao("TRANSIÇÃO 2", "TRANSICAO", 1, 10000.0, membros=[
        M(0, 0, 10000, 0, "banzo"), M(0, 1100, 10000, 1100, "banzo"),
        M(0, 1100, 5000, 2300, "banzo"), M(5000, 2300, 10000, 1100, "banzo"),
        M(2500, 0, 2500, 1100, "montante"), M(2500, 1100, 2500, 1700, "montante")])
    partes = de_planta._partes_da_elevacao(el, True)
    assert [s for s, _ in partes] == ["", " (tesoura de cima)"]
    t = de_planta.Trecho(de_planta.Caminho("reta", a=(0.0, 0.0), b=(10000.0, 0.0)), "TRANSIÇÃO 2", "TRANSICAO", elevacao=el)
    assert de_planta._altura_no_ponto(t, (5000.0, 0.0)) == pytest.approx(1100.0)
    # a elevação de uma peça só continua dando o topo dela
    el1 = de_planta.Elevacao("TESOURA 1", "TESOURA", 1, 10000.0, membros=list(el.membros))
    t1 = de_planta.Trecho(de_planta.Caminho("reta", a=(0.0, 0.0), b=(10000.0, 0.0)), "TESOURA 1", "TESOURA", elevacao=el1)
    assert de_planta._altura_no_ponto(t1, (5000.0, 0.0)) == pytest.approx(2300.0)


def test_peca_de_um_perfil_so_pela_nota_dentro_do_desenho():
    """a viga inclinada "PERFIL 1 - 2X" da cobertura da caixa d'água do Posto CB: a elevação é o
    perfil em linha dupla (a altura dele), subindo 5%, com um dente na ponta baixa (onde a calha
    assenta); a nota "PERFIL 1 2U100X40X2,65" fica dentro do desenho, não embaixo"""
    x0, y0 = 50000.0, -150000.0
    ents = [linha((x0 + 360.0, y0 + 200.0), (x0 + 7600.0, y0 + 563.0), "1-Metalica2"),
            linha((x0 + 460.0, y0 + 105.0), (x0 + 7605.0, y0 + 463.0), "1-Metalica2"),
            linha((x0, y0 + 100.0), (x0 + 360.0, y0 + 100.0), "1-Metalica2"),
            linha((x0, y0), (x0 + 460.0, y0), "1-Metalica2"),
            linha((x0 + 360.0, y0 + 200.0), (x0 + 360.0, y0 + 100.0), "1-Metalica2"),
            linha((x0 + 460.0, y0 + 105.0), (x0 + 460.0, y0), "1-Metalica2"),
            linha((x0, y0 + 100.0), (x0, y0), "1-Metalica2"),
            texto((x0 + 3000.0, y0 + 90.0), "PERFIL 1 2U100X40X2,65"),
            texto((x0, y0 - 700.0), "PERFIL 1 - 2X", altura=3.5)]
    el = de_planta.ler_elevacoes(ents, ["PERFIL"])["PERFIL 1"]
    assert el.qtd == 2 and el.banzo["perfil"] == "U 100×40×2,65 (FF)" and el.banzo["mult"] == 2
    inclinada = max(el.membros, key=lambda m: m.s1 - m.s0)
    assert inclinada.papel == "banzo" and inclinada.altura_linha == pytest.approx(100.0, abs=5)
    assert inclinada.h1 - inclinada.h0 == pytest.approx(363.0, abs=15)


def test_agulha_de_terca_a_terca_em_barra_redonda():
    """a agulha (camada "1-Agulha", "DETALHE TÍPICO DAS AGULHAS": barra redonda Ø 10 rosqueada) liga
    uma terça à vizinha, na altura delas — antes ficava de fora (só "corrente" e "esticador")"""
    xa, xb = L_TES - S_TERCAS[1], L_TES - S_TERCAS[2]
    ag = [linha((xa, 3000.0 + DY_TER), (xb, 3000.0 + DY_TER), "1-Agulha"), texto((-20000.0, -20500.0), "AG 1 COMP. 1470   1X")]
    ents = planta() + locacao() + plantas_das_tercas() + ag + baloes(0, 0) + baloes(DX_LOC, 0) + baloes(0, DY_TER)
    ents += elevacao_tesoura(0.0, -120000.0) + elevacao_painel(20000.0, -120000.0)
    r = de_planta.montar(ents, {"nivel": 6000.0, "origem": False})
    assert r["resumo"]["agulhas"] == 1 and r["resumo"]["projeto"]["agulhas"] == 1
    b = [b for b in r["doc"].barras if b.papel == "corrente" and b.perfil == "Barra redonda 10"]
    assert len(b) == 1
    tercas = [t for t in r["doc"].barras if t.papel == "terça"]
    z_t = {round(t.inicio[0]): t.inicio[2] for t in tercas}
    assert b[0].inicio[2] == pytest.approx(z_t[round(b[0].inicio[0])], abs=60)


# ------------------------------------------------------------------ vigas VM do Posto CB (28/09)

def test_nome_da_viga_marca_o_pedaco_pelo_comeco_do_texto():
    """a linha VM | COMP 27 | VM | COMP 26 | COMP 25 (Posto, x 54,13): cada nome escrito a partir do
    começo do seu pedaço; o meio estimado do nome comprido caía no pedaço da COMP seguinte"""
    c = de_planta.Caminho("reta", a=(0.0, 0.0), b=(14550.0, 0.0), largura=100.0)
    cortes = [(0.0, 3150.0), (3300.0, 6680.0), (6810.0, 10400.0), (10530.0, 13020.0), (13120.0, 14550.0)]
    pedacos = [de_planta.Caminho("reta", a=(a, 0.0), b=(b, 0.0)) for a, b in cortes]
    nomes = [(-100.0, 3900.0, "VM-2Ue100X50X17X2,65"), (4200.0, 5390.0, "COMP.27"), (6930.0, 10930.0, "VM-2Ue100X50X17X2,65"),
             (11080.0, 11960.0, "COMP.26"), (13150.0, 13840.0, "COMP.25")]
    ts = [texto((x, -180.0), t) for x, _s, t in nomes]
    rot = [(s, t, e) for (_x, s, t), e in zip(nomes, ts)]
    f = de_planta._faixas_das_vigas(c, rot, pedacos)
    assert f[id(ts[0])] == (0.0, 3150.0)
    assert f[id(ts[2])] == (6810.0, 10400.0)


def test_nome_de_chamada_nao_toma_o_pedaco_da_tesoura():
    """o "VM-…" escrito sobre a linha de chamada das curvas do canto, 0,53 m ao lado da TESOURA 33,
    não é viga da linha da tesoura (virava uma VM em cima da treliça)"""
    c = de_planta.Caminho("reta", a=(0.0, 0.0), b=(18260.0, 0.0), largura=100.0)
    pedacos = [de_planta.Caminho("reta", a=(a, 0.0), b=(b, 0.0)) for a, b in ((0.0, 2600.0), (2750.0, 10330.0), (10480.0, 18260.0))]
    t22, vm, t33 = texto((6080.0, -400.0), "TESOURA 22"), texto((6950.0, 530.0), "VM-2Ue200X70X20X2,65"), texto((11630.0, -400.0), "TESOURA 33")
    rot = [(8230.0, t22["texto"], t22), (10950.0, vm["texto"], vm), (13780.0, t33["texto"], t33)]
    f = de_planta._faixas_das_vigas(c, rot, pedacos)
    assert id(vm) not in f


def test_viga_curva_sai_calandrada_e_o_esqueleto_passa_pelo_centro_do_par():
    """a VM de borda curva segue o arco da planta (antes era uma corda reta); o 2Ue são dois U
    calandrados, e o esqueleto tem uma linha só, pelo centro deles, com o papel de viga"""
    from nucleo3d import analitico
    ents = [e for e in planta() if not (e.get("camada") == "metalica4" or str(e.get("texto", "")).startswith("VM"))]
    for r in (3000.0 - 100.0, 3000.0 + 100.0):
        ents.append({"tipo": "arco", "camada": "metalica4", "centro": [0.0, 3000.0], "raio": r, "inicio": 90.0, "fim": 270.0})
    ents.append(texto((-3300.0, 1500.0), "VM-2Ue200X70X20X2,65", angulo=90.0))
    ents += locacao() + plantas_das_tercas() + baloes(0, 0) + baloes(DX_LOC, 0) + baloes(0, DY_TER)
    ents += elevacao_tesoura(0.0, -120000.0) + elevacao_painel(20000.0, -120000.0)
    doc = de_planta.montar(ents, {"nivel": 6000.0, "origem": False})["doc"]
    curvas = [e for e in doc.entidades.values() if e.tipo == "solido" and (e.atributos or {}).get("papel") == "viga"]
    assert len(curvas) == 2 and all(abs(e.atributos["calandrada"]["raio"] - 3000.0) < 1.0 for e in curvas)
    assert sum(1 for e in curvas if e.atributos.get("par_de")) == 1
    assert not [b for b in doc.barras if b.papel == "viga"]            # nenhuma corda reta
    # os U ficam a ~36 mm de cada lado do arco de centro, um virado para o outro
    for e in curvas:
        xs = [v[0] for v in e.vertices]
        assert min(xs) < -3000.0 + 100.0
    linhas = [ln for ln in analitico._linhas_do(doc) if ln["papel"] == "viga"]
    assert linhas and all(abs(math.hypot(ln["a"][0], ln["a"][1] - 3000.0) - 3000.0) < 1.0 for ln in linhas)


def test_nome_de_chamada_vai_para_a_curva_onde_a_chamada_termina():
    """o "VM-2Ue200…" das curvas dos cantos do Posto: escrito sobre um sublinhado, com a linha de
    chamada saindo da ponta dele até o arco; o nome é da curva, não da linha paralela mais perto"""
    canto = de_planta.Caminho("arco", centro=(0.0, 0.0), raio=1000.0, ini=90.0, fim=180.0, largura=140.0)
    reta = de_planta.Caminho("reta", a=(-6000.0, 1300.0), b=(3000.0, 1300.0), largura=100.0)
    t = texto((-5000.0, 1600.0), "VM-2Ue200X70X20X2,65")
    ents = [t, linha((-4920.0, 1500.0), (-1920.0, 1500.0), "1-Metalica2"),
            linha((-1920.0, 1500.0), (-707.0, 707.0), "REG60-100")]
    ch = de_planta._chamadas([t], ents, [reta, canto], (-1e5, -1e5, 1e5, 1e5))
    assert ch[id(t)][0] == 1                              # a curva, não a reta ao lado do texto
    assert de_planta._curva_de_canto(canto) and not de_planta._curva_de_canto(reta)
