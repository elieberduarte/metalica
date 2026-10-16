# -*- coding: utf-8 -*-
"""A Montagem por eixos (11/10/2026, web/cad/implantacao.js): os elementos lançados no quadro da Implantação — em mm de
papel, na escala do quadro — voltam à medida real pelo mapa dele (nucleo3d/de_planta_estrutura.planta_real), e o 3D sai
igual ao da mesma estrutura lançada numa planta comum."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Linha, Polilinha, Texto  # noqa: E402
from nucleo3d import de_planta_estrutura as DPE  # noqa: E402

S = 200.0                                     # a escala do quadro
Q = {"id": "qi", "tipo": "implantacao", "escala": S, "x": 10.0, "y": -40.0, "w": 400.0, "h": 300.0,
     "mapa": {"X0": 0.0, "Y0": 20000.0, "ox": 25.0, "oy": -45.0, "giro": 0.0}}


def papel(g, p, q=Q):
    mp = q["mapa"]
    return (q["x"] + mp["ox"] + (g - mp["X0"]) / q["escala"], q["y"] + mp["oy"] + (p - mp["Y0"]) / q["escala"])


def _montagem(*ents, quadros=(Q,)):
    des = Desenho(nome="Montagem", escala=1.0, metadados={"montagem": {"versao": 1, "quadros": [dict(q) for q in quadros]}})
    for e in ents:
        des.add(e)
    return des


BARRAS = [[0, 0, 20000, 0, "banzo_inf"], [0, 0, 10000, 1500, "banzo_sup"], [10000, 1500, 20000, 0, "banzo_sup"],
          [10000, 0, 10000, 1500, "montante"]]


def _trelica(a, b, quadro="qi"):
    return Linha(a=a, b=b, camada="ESTRUTURA", atributos={
        "elemento": "trelica", "material": "aco", "marca": "T1", "quadro": quadro, "nivel_base": 6000,
        "perfis": {"banzo_sup": "U 150×50×3,0", "banzo_inf": "U 150×50×3,0", "diagonal": "L 50,8×4,76"},
        "desenho": {"barras": BARRAS, "vao": 20000, "altura": 1500}})


def test_planta_real_leva_o_elemento_da_implantacao_a_medida_real():
    t = _trelica(papel(6000, 0), papel(6000, 20000))
    texto = Texto(posicao=papel(0, 0), texto="1", atributos={"quadro": "qi", "gerado": "implantacao"})
    fora = _trelica((0.0, 0.0), (100.0, 0.0), quadro="outro")
    real = DPE.planta_real(_montagem(t, texto, fora))
    assert list(real.entidades) == [t.id]                       # só o elemento da implantação; o gerado e o de fora não
    e = real.entidades[t.id]
    assert math.dist(e.a, (6000, 0)) < 1e-6 and math.dist(e.b, (6000, 20000)) < 1e-6


def test_o_3d_pela_implantacao_e_o_mesmo_da_planta_comum():
    t = _trelica(papel(6000, 0), papel(6000, 20000))
    doc_m, av_m = DPE.modelo_da_planta(_montagem(t), [])
    comum = Desenho(nome="planta", escala=100.0)
    comum.add(Linha(a=(6000.0, 0.0), b=(6000.0, 20000.0), camada="ESTRUTURA", atributos={k: v for k, v in t.atributos.items() if k != "quadro"}))
    doc_c, _ = DPE.modelo_da_planta(comum, [])
    pts = lambda d: sorted((tuple(round(c, 3) for c in b.inicio), tuple(round(c, 3) for c in b.fim)) for b in d.entidades.values())
    assert len(doc_m.entidades) == len(doc_c.entidades) > 0
    assert pts(doc_m) == pts(doc_c)
    zs = [b.inicio[2] for b in doc_m.entidades.values()] + [b.fim[2] for b in doc_m.entidades.values()]
    assert min(zs) >= 6000 - 200 and max(zs) <= 6000 + 1500 + 200


def test_pilar_e_giro_dos_eixos():
    # os eixos girados 90°: o g da implantação corre no Y da planta
    q = dict(Q, mapa=dict(Q["mapa"], giro=90.0))
    lado = 150 / S
    c = papel(6000, 0, q)
    pil = Polilinha(vertices=[(c[0] - lado, c[1] - lado), (c[0] + lado, c[1] - lado), (c[0] + lado, c[1] + lado), (c[0] - lado, c[1] + lado)],
                    fechada=True, camada="ESTRUTURA", atributos={"elemento": "pilar", "material": "aco", "marca": "P1", "quadro": "qi",
                                                                 "secao": {"perfil": "W 200×15", "aco": "ASTM A572 Gr.50"},
                                                                 "nivel_base": 0, "nivel_topo": 6000, "centro": list(c)})
    real = DPE.planta_real(_montagem(pil, quadros=(q,)))
    e = real.entidades[pil.id]
    cx = sum(v[0] for v in e.vertices) / 4
    cy = sum(v[1] for v in e.vertices) / 4
    assert abs(cx - 0.0) < 1e-6 and abs(cy - 6000.0) < 1e-6         # (g, p) = (6000, 0) girado 90° → (0, 6000)
    lados = [math.dist(e.vertices[i], e.vertices[(i + 1) % 4]) for i in range(4)]
    assert all(abs(L - 300.0) < 1e-6 for L in lados)                  # 300 mm reais
    assert math.dist(e.atributos["centro"], (0.0, 6000.0)) < 1e-6


def test_fora_da_montagem_a_planta_e_a_mesma():
    des = Desenho(nome="planta", escala=100.0)
    assert DPE.planta_real(des) is des


def test_banzo_em_linha_de_centro_fica_com_a_boca_para_o_miolo():
    """Regra do usuário (07/10): o U do banzo abre para o miolo da tesoura — também o banzo que chega em linha de
    centro (o esqueleto do leitor do desenho detalhado, sem as duas faces). O de cima abre para baixo, o de baixo
    para cima; antes ele ia pela regra da cantoneira, com a boca para fora do plano (CD Bom Dia, 11/10)."""
    from nucleo3d.geometria import base_local
    comum = Desenho(nome="planta", escala=100.0)
    t = _trelica((6000.0, 0.0), (6000.0, 20000.0))
    comum.add(Linha(a=t.a, b=t.b, camada="ESTRUTURA", atributos={k: v for k, v in t.atributos.items() if k != "quadro"}))
    doc, _ = DPE.modelo_da_planta(comum, [])
    vistos = set()
    for b in doc.entidades.values():
        papel = (b.atributos or {}).get("papel_trelica")
        if papel not in ("banzo_sup", "banzo_inf"):
            continue
        w = tuple(b.fim[c] - b.inicio[c] for c in range(3))
        u, _v, _w = base_local(w, b.rotacao)
        assert (u[2] < -0.9) if papel == "banzo_sup" else (u[2] > 0.9), (papel, b.rotacao, u)
        assert abs(u[0]) < 1e-6                                   # no plano da tesoura (x = 6000)
        vistos.add(papel)
    assert vistos == {"banzo_sup", "banzo_inf"}


def test_tesouras_encostadas_cada_montante_de_ponta_abre_para_a_sua():
    """Duas tesouras no mesmo desenho, encostadas no apoio (o CD Bom Dia: A–B e B–C com os montantes de ponta lado a lado,
    a 330 mm): o U de cada montante de ponta abre para a tesoura dele — o lado das diagonais ligadas —, e não para o
    meio do desenho inteiro."""
    from nucleo3d.geometria import base_local
    barras = []
    for x0, x1 in ((0, 10000), (10330, 20330)):
        barras += [[x0, 0, x1, 0, "banzo_inf"], [x0, 1500, x1, 1500, "banzo_sup"],
                   [x0, 0, x0, 1500, "extremidade"], [x1, 0, x1, 1500, "extremidade"],
                   [x0, 0, x0 + 2500, 1500, "diagonal"], [x1, 0, x1 - 2500, 1500, "diagonal"]]
    comum = Desenho(nome="planta", escala=100.0)
    comum.add(Linha(a=(0.0, 0.0), b=(20330.0, 0.0), camada="ESTRUTURA", atributos={
        "elemento": "trelica", "material": "aco", "marca": "T", "nivel_base": 0,
        "perfis": {"banzo_sup": "U 150×50×3,0", "banzo_inf": "U 150×50×3,0", "diagonal": "L 50,8×4,76"},
        "desenho": {"barras": barras, "vao": 20330, "altura": 1500}}))
    doc, _ = DPE.modelo_da_planta(comum, [])
    abre = {}
    for b in doc.entidades.values():
        if (b.atributos or {}).get("papel_trelica") != "extremidade":
            continue
        w = tuple(b.fim[c] - b.inicio[c] for c in range(3))
        u, v, _w = base_local(w, b.rotacao)
        # a aba (ou a boca) que fica no plano da tesoura; na cantoneira de abas iguais, u ou v (a outra atravessa o plano
        # sempre do mesmo lado: regras_trelica T5, 16/10)
        no_plano = u if abs(u[1]) < 0.5 else v
        abre[round(b.inicio[0])] = round(no_plano[0])
    # as pontas de fora abrem para dentro; no apoio do meio, a de 10000 abre para trás (−x) e a de 10330 para frente (+x)
    assert abre == {0: 1, 10000: -1, 10330: 1, 20330: -1}, abre


def test_montante_em_u_no_meio_da_tesoura_abre_para_o_meio_do_vao():
    """O montante desenhado em U (linha dupla) no meio da tesoura — alma ligada dos dois lados, sem 'miolo' — abre para o
    meio do vão (decisão do usuário, 11/10): os da metade esquerda para a direita, os da direita para a esquerda."""
    from nucleo3d.geometria import base_local
    barras = [[0, 0, 20000, 0, "banzo_inf"], [0, 1500, 20000, 1500, "banzo_sup"],
              [0, 0, 0, 1500, "extremidade"], [20000, 0, 20000, 1500, "extremidade"]]
    for x in (5000, 15000):
        barras += [[x - 30, 0, x - 30, 1500, "montante"], [x + 30, 0, x + 30, 1500, "montante"],       # em linha dupla
                   [x - 2500, 0, x - 30, 1500, "diagonal"], [x + 30, 1500, x + 2500, 0, "diagonal"]]
    comum = Desenho(nome="planta", escala=100.0)
    comum.add(Linha(a=(0.0, 0.0), b=(20000.0, 0.0), camada="ESTRUTURA", atributos={
        "elemento": "trelica", "material": "aco", "marca": "T", "nivel_base": 0,
        "perfis": {"banzo_sup": "U 150×50×3,0", "banzo_inf": "U 150×50×3,0", "diagonal": "L 50,8×4,76"},
        "desenho": {"barras": barras, "vao": 20000, "altura": 1500}}))
    doc, _ = DPE.modelo_da_planta(comum, [])
    abre = {}
    for b in doc.entidades.values():
        if (b.atributos or {}).get("papel_trelica") != "extremidade" or abs(b.inicio[0] - b.fim[0]) > 1:
            continue
        w = tuple(b.fim[c] - b.inicio[c] for c in range(3))
        u, v, _w = base_local(w, b.rotacao)
        # a aba (ou a boca) que fica no plano da tesoura; na cantoneira de abas iguais, u ou v (a outra atravessa o plano
        # sempre do mesmo lado: regras_trelica T5, 16/10)
        no_plano = u if abs(u[1]) < 0.5 else v
        abre[round(b.inicio[0])] = round(no_plano[0])
    assert abre == {0: 1, 5000: 1, 15000: -1, 20000: -1}, abre


def test_perfil_da_barra_e_secao_dupla_da_legenda():
    """A legenda de cores da folha de perfis do projeto (CD Bom Dia, 11/10): cada barra com o perfil dela. O croqui da
    legenda: "COMPOSTO" = dois U de costas, a boca para fora do plano, afastados pela altura do perfil da alma (127 entre
    os Ue 100 da TC1, cuja alma é Ue 127); "DUPLO (CAIXA)" = dois U de boca um para o outro lado a lado no plano. A alma
    em U/Ue tem a altura atravessando o plano (entra entre os U do banzo)."""
    from nucleo3d.geometria import base_local, resolver_perfil, secao
    barras = [[0, 0, 10000, 0, "banzo_inf", "Ue 100×50×17×2,65", "composto"],
              [0, 1500, 10000, 1500, "banzo_sup", "Ue 100×50×17×2,25", ""],
              [0, 0, 0, 1500, "montante", "Ue 127×50×17×2,00", "caixa"],
              [0, 0, 5000, 1500, "diagonal", "Ue 127×50×17×2,00", ""],
              [5000, 1500, 10000, 0, "diagonal"]]
    comum = Desenho(nome="planta", escala=100.0)
    comum.add(Linha(a=(0.0, 0.0), b=(10000.0, 0.0), camada="ESTRUTURA", atributos={
        "elemento": "trelica", "material": "aco", "marca": "T", "nivel_base": 0,
        "perfis": {"banzo_sup": "U 150×50×3,0", "banzo_inf": "U 150×50×3,0", "diagonal": "L 50,8×4,76"},
        "desenho": {"barras": barras, "vao": 10000, "altura": 1500}}))
    doc, _ = DPE.modelo_da_planta(comum, [])
    por = {}
    for b in doc.entidades.values():
        por.setdefault((b.atributos or {}).get("papel_trelica"), []).append(b)
    assert [b.perfil for b in por["banzo_sup"]] == ["Ue 100×50×17×2,25"]
    assert sorted(b.perfil for b in por["diagonal"]) == ["L 50,8×4,76", "Ue 127×50×17×2,00"]   # sem perfil próprio: o do tipo
    # composto: os dois U de costas fora do plano (y), a 127/2 da alma da tesoura (Ue 127) até as costas
    dois = por["banzo_inf"]
    p = resolver_perfil("Ue 100×50×17×2,65")
    xg = -min(q[0] for q in secao(p))
    off = xg + 127.0 / 2
    assert len(dois) == 2 and all(b.atributos.get("secao_dupla") == "composto" for b in dois)
    ys = sorted(round(b.inicio[1], 3) for b in dois)
    assert abs(ys[0] + off) < 0.01 and abs(ys[1] - off) < 0.01, (ys, off)
    for b in dois:
        u, _v, _w = base_local(tuple(b.fim[c] - b.inicio[c] for c in range(3)), b.rotacao)
        assert round(u[1]) == (1 if b.inicio[1] > 0 else -1)                   # a boca para fora
    # caixa (o montante em pé em x = 0): os dois U lado a lado no plano (x), de boca um para o outro
    dois = por["montante"]
    p = resolver_perfil("Ue 127×50×17×2,00")
    xg = -min(q[0] for q in secao(p))
    xs = sorted(round(b.inicio[0], 3) for b in dois)
    assert all(abs(b.inicio[1]) < 1e-6 for b in dois) and abs(xs[0] + (p.bf - xg)) < 0.01 and abs(xs[1] - (p.bf - xg)) < 0.01, xs
    for b in dois:
        u, v, _w = base_local(tuple(b.fim[c] - b.inicio[c] for c in range(3)), b.rotacao)
        assert round(u[0]) == (-1 if b.inicio[0] > 0 else 1) and abs(round(v[1])) == 1   # bocas juntas; a altura atravessa
    # a alma em Ue simples: a altura (eixo v) atravessa o plano, a boca no plano
    d = next(b for b in por["diagonal"] if b.perfil.startswith("Ue"))
    u, v, _w = base_local(tuple(d.fim[c] - d.inicio[c] for c in range(3)), d.rotacao)
    assert abs(abs(v[1]) - 1) < 1e-6 and abs(u[1]) < 1e-6 and u[2] > 0


def test_vao_e_boca_dados_no_painel_perfis_da_tesoura():
    """O painel "Perfis da tesoura" (11/10) grava na barra o vão entre os dois U do composto (b[7], mm) e a boca virada
    (b[8]): o composto se afasta pelo vão dado em vez da altura da alma; virar inverte a boca do banzo simples e a da
    alma."""
    from nucleo3d.geometria import base_local, resolver_perfil, secao
    def montar(extra_inf, extra_sup, extra_dia):
        barras = [[0, 0, 10000, 0, "banzo_inf", "Ue 100×50×17×2,65", "composto", *extra_inf],
                  [0, 1500, 10000, 1500, "banzo_sup", "Ue 100×50×17×2,25", "", *extra_sup],
                  [0, 0, 0, 1500, "montante", "Ue 127×50×17×2,00", ""],
                  [0, 0, 5000, 1500, "diagonal", "Ue 127×50×17×2,00", "", *extra_dia],
                  [5000, 1500, 10000, 0, "diagonal", "Ue 127×50×17×2,00", ""]]
        comum = Desenho(nome="planta", escala=100.0)
        comum.add(Linha(a=(0.0, 0.0), b=(10000.0, 0.0), camada="ESTRUTURA", atributos={
            "elemento": "trelica", "material": "aco", "marca": "T", "nivel_base": 0,
            "perfis": {"banzo_sup": "U 150×50×3,0", "banzo_inf": "U 150×50×3,0", "diagonal": "L 50,8×4,76"},
            "desenho": {"barras": barras, "vao": 10000, "altura": 1500}}))
        doc, _ = DPE.modelo_da_planta(comum, [])
        por = {}
        for b in doc.entidades.values():
            por.setdefault((b.atributos or {}).get("papel_trelica"), []).append(b)
        return por
    eixos = lambda b: base_local(tuple(b.fim[c] - b.inicio[c] for c in range(3)), b.rotacao)
    a = montar([], [], [])
    b = montar([200, ""], [None, 1], [None, 1])
    # o vão dado: as costas a 200 (não a 127 da alma)
    p = resolver_perfil("Ue 100×50×17×2,65")
    xg = -min(q[0] for q in secao(p))
    ys = sorted(round(x.inicio[1], 3) for x in b["banzo_inf"])
    assert abs(ys[0] + xg + 100) < 0.01 and abs(ys[1] - xg - 100) < 0.01, ys
    # vazio = a altura da alma, como antes
    ys = sorted(round(x.inicio[1], 3) for x in a["banzo_inf"])
    assert abs(ys[1] - xg - 63.5) < 0.01, ys
    # a boca virada: o banzo de cima e a diagonal com o eixo u (a boca) ao contrário
    ua, ub = eixos(a["banzo_sup"][0])[0], eixos(b["banzo_sup"][0])[0]
    assert all(abs(ua[c] + ub[c]) < 1e-6 for c in range(3)), (ua, ub)
    da = next(x for x in a["diagonal"] if x.inicio[0] < 1 and x.fim[0] > 4000)
    db = next(x for x in b["diagonal"] if x.inicio[0] < 1 and x.fim[0] > 4000)
    ua, ub = eixos(da)[0], eixos(db)[0]
    assert all(abs(ua[c] + ub[c]) < 1e-6 for c in range(3)), (ua, ub)


# a T1 do Docas: banzos e pontas em linha dupla (a face de dentro 50 mm para dentro), diagonais em linha simples
DOCAS = [
    [0, 350, 0, 0, "montante"], [50, 329, 50, 50, "montante"],
    [0, 0, 4750, 0, "banzo_inf"], [4700, 50, 50, 50, "diagonal"],
    [4750, 1400, 350, 700, "banzo_sup"], [4700, 1341, 374, 653, "diagonal"],
    [350, 700, 0, 350, "diagonal"], [374, 653, 50, 329, "diagonal"],
    [4750, 0, 4750, 1400, "montante"], [4700, 50, 4700, 1341, "montante"],
    [902, 0, 449, 716, "diagonal"], [449, 716, 449, 0, "montante"], [1810, 0, 1356, 860, "diagonal"],
]
PERFIS_DOCAS = {"banzo_sup": "U 150×50×3,00 (FF)", "banzo_inf": "U 150×50×3,00 (FF)", "diagonal": 'L 1½"×1/8"'}


def _docas(cantoneira="simples", **extra):
    des = Desenho(nome="planta")
    des.add(Linha(a=(0.0, 0.0), b=(0.0, 4750.0), camada="ESTRUTURA",
                  atributos={"elemento": "trelica", "material": "aco", "marca": "T1", "perfis": PERFIS_DOCAS, "cantoneira": cantoneira,
                             "nivel_base": 5000, "desenho": {"barras": DOCAS, "vao": 4750, "altura": 1400}, **extra}))
    doc, _ = DPE.modelo_da_planta(des, [])
    return [b for b in doc.entidades.values() if b.tipo == "barra"]


def test_nos_da_alma_no_eixo_do_banzo():
    """NBR 8800:2024, 6.5.2 (usuário, 12/10): a alma chega ao EIXO do banzo, não à face desenhada. Na T1 do Docas o
    desenho leva as cantoneiras à linha de fora / de dentro do banzo inferior (v 0 e 50): o nó vai para o eixo (v 25)."""
    bs = _docas()
    zs = sorted({round(q[2], 1) for b in bs if b.perfil.startswith("L") for q in (b.inicio, b.fim) if q[2] < 5100.0})
    assert zs == [5025.0], zs


def test_nos_espalhados_viram_um_so_no_do_montante():
    """em linha de centro (o esqueleto do leitor), as pontas da alma desenhadas até a face do banzo: o montante e a
    diagonal que chegam a 40 mm um do outro viram um nó só, o do montante, no eixo do banzo"""
    barras = [[0, 0, 4000, 0, "banzo_inf"], [0, 1000, 4000, 1000, "banzo_sup"],
              [1000, 25, 1000, 975, "montante"], [1040, 25, 2000, 975, "diagonal"]]
    des = Desenho(nome="planta")
    des.add(Linha(a=(0.0, 0.0), b=(0.0, 4000.0), camada="ESTRUTURA",
                  atributos={"elemento": "trelica", "material": "aco", "marca": "T", "perfis": PERFIS_DOCAS, "nivel_base": 0,
                             "desenho": {"barras": barras, "vao": 4000, "altura": 1000}}))
    doc, _ = DPE.modelo_da_planta(des, [])
    por = {b.atributos["papel_trelica"]: b for b in doc.entidades.values() if b.tipo == "barra" and not b.atributos["papel_trelica"].startswith("banzo")}
    m, d = por["montante"], por["diagonal"]
    assert sorted(round(q[2], 1) for q in (m.inicio, m.fim)) == [0.0, 1000.0]
    baixo = min((d.inicio, d.fim), key=lambda q: q[2])
    assert abs(baixo[2]) < 0.1 and abs(baixo[1] - 1000.0) < 0.1          # o nó do montante


def test_presilhas_da_cantoneira_dupla_pela_norma():
    """NBR 8800:2024, 5.3.6.1 (usuário, 12/10): as duas cantoneiras ligadas por presilhas igualmente espaçadas entre os
    nós, atravessando o par; pelo menos o mínimo da norma (de_planta._presilhas_pela_norma) e a nota do projeto acima"""
    from nucleo3d.de_planta import _presilhas_pela_norma
    bs = _docas("dupla")
    pares = [b for b in bs if b.atributos.get("cantoneira_dupla") == "a"]
    pres = [b for b in bs if b.papel == "presilha"]
    n_norma = _presilhas_pela_norma(PERFIS_DOCAS["diagonal"])
    assert n_norma >= 2 and len(pres) == n_norma * len(pares)
    for b in pres:
        assert abs(abs(b.direcao[0]) - 1.0) < 1e-6                              # atravessa o plano da tesoura (x)
        assert abs(b.inicio[0] + b.fim[0]) < 0.1 and abs(b.fim[0]) > 52.0
    pres = [b for b in _docas("dupla", presilhas={"qtd": n_norma + 2, "perfil": 'L 1"×1/8"'}) if b.papel == "presilha"]
    assert len(pres) == (n_norma + 2) * len(pares) and {b.perfil for b in pres} == {'L 1"×1/8"'}
