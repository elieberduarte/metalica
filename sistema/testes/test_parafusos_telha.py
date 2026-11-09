# -*- coding: utf-8 -*-
"""Parafusos de telha pela contagem do 3D — regra COM-05 (usuário, 09/11/2026; sistema/testes/REGRAS.md).

OA 2.3/8" (TP40 simples na cobertura; PIR 30 4", PIR 50 5", isopainel 2"), OB 3/4" (fechamento, TP25, forro), costura 7/8" =
(OA + OB) ÷ 4 por cor sem o isopainel; OA/OB no múltiplo de 50, costura no de 5; cabeça na cor da telha; aviso fora de ±30 % da
mediana Hermes nas linhas ≥ 1.000 ml; fechamento em sanduíche vira pendência.
Fixações por telha (usuário, 09/11, critério C para todas as obras — o caso B da Sooro, 5 nas pontas e 2,5 no meio, saiu):
3 por telha em cada apoio, terça da cobertura (OA) e longarina do fechamento e do forro (OB); recorte sem apoio = 1 apoio; telha estreita proporcional à largura útil. Os pedaços da mesma faixa (as facetas do
beiral curvo R450 e a saia em pé, que o IFC parte) são uma telha só; os dois lados da cumeeira, duas.
Antes o sistema só tinha "Autobrocante 12-14 × 1"" a 2,2/m² (nucleo/acessorios.py), que nenhuma obra da Hermes usa, e o resumo
de compra não trazia parafuso de telha nenhum."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

from nucleo3d.modelo import Barra, Documento, Solido  # noqa: E402
from nucleo3d import geometria as G  # noqa: E402
from saida import parafusos_telha as PT  # noqa: E402

FACES = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]


def _caixa(nome, x0, x1, y0, y1, z0, z1, camada="Telhas", **atr):
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    s = Solido(nome=nome, camada=camada, vertices=v, faces=FACES)
    s.atributos.update(atr)
    return s


def _placa(nome, a, b, y0, y1, esp=40.0, camada="Telhas"):
    """Telha de a → b (pontos no plano xz) e de y0 a y1, com a espessura para cima da linha a–b."""
    a, b = np.array(a, float), np.array(b, float)
    d = (b - a) / np.linalg.norm(b - a)
    n = np.array([-d[1], d[0]])
    if n[1] < 0:
        n = -n
    cantos = [a, b, b + esp * n, a + esp * n]
    v = [(float(p[0]), y, float(p[1])) for p in (cantos[0], cantos[1], cantos[3], cantos[2]) for y in (y0, y1)]
    # vértices na ordem da _caixa: (x0,y0,z0) (x0,y1,z0) (x0,y0,z1) ...: aqui só importa a nuvem de pontos
    return Solido(nome=nome, camada=camada, vertices=v, faces=FACES)


def test_exemplos_aprovados_das_duas_obras_da_sooro():
    """Os números do critério C (usuário, 09/11, 3 por telha em cada apoio), conferidos pelo chat da Sooro: Sala de Compressores
    64 faixas × 8 terças = 512 apoios × 3 = 1.536 → 1.550 OA; OB (121 do oitão + 92 × 2 + 8 × 1 do forro) = 313 × 3 = 939 → 950;
    costura (1.550 + 950) ÷ 4 = 625. Depósito Químico 68 telhas × 8 terças × 3 = 1.632 → 1.650 OA; OB 398 × 3 = 1.194 → 1.200;
    costura (1.650 + 1.200) ÷ 4 = 712,5 → 715. No caso B (5 nas pontas, 2,5 no meio) a Sala dava 1.600 / 800 / 600."""
    faixa = {"apoios": 8, "pontas": 2, "largura": 1031}
    assert PT.fixacoes_da_telha(faixa, "OA") == 24.0
    assert PT.arredondar(64 * PT.fixacoes_da_telha(faixa, "OA"), 50) == 1550
    assert PT.arredondar((121 + 92 * 2 + 8) * PT.FIX_FECHAMENTO, 50) == 950 and PT.costura(1550, 950) == 625
    assert PT.arredondar(68 * PT.fixacoes_da_telha(faixa, "OA"), 50) == 1650
    assert PT.arredondar(398 * PT.FIX_FECHAMENTO, 50) == 1200 and PT.costura(1650, 1200) == 715
    # o exemplo da regra (Padrao-quantitativo-orcamento.md): (1.725 + 980) ÷ 4 = 676,25 → 680
    assert PT.costura(1725, 980) == 680
    assert PT.arredondar(1725, 50) == 1750 and PT.arredondar(0, 50) == 0 and PT.arredondar(676.25, 5) == 680


def test_fixacoes_por_telha():
    assert PT.fixacoes_da_telha({"apoios": 2, "pontas": 2}, "OA") == 6.0            # beiral e cumeeira: 3 + 3
    assert PT.fixacoes_da_telha({"apoios": 4, "pontas": 2}, "OA") == 12.0           # a do meio leva 3 como a da ponta
    assert PT.fixacoes_da_telha({"apoios": 0, "pontas": 0}, "OA") == 3.0            # recorte sem apoio = 1 apoio
    assert PT.fixacoes_da_telha({"apoios": 3, "pontas": 2}, "OB") == 9.0            # 3 em toda longarina
    assert PT.fixacoes_da_telha({"apoios": 0, "pontas": 0}, "OB") == 3.0
    assert PT.fixacoes_da_telha({"apoios": 8, "pontas": 2, "largura": 490}, "OA") == 12.0   # meia telha: metade


def test_comprimento_pela_telha_e_pelo_uso():
    assert PT.parafuso_da_telha("cobertura", PT.tipo_da_telha("Telha TP40 0,50 bege"))[:2] == ("OA", '2.3/8"')
    assert PT.parafuso_da_telha("cobertura", PT.tipo_da_telha("TP40 + PIR 30 branca"))[:2] == ("OA", '4"')
    assert PT.parafuso_da_telha("cobertura", PT.tipo_da_telha("Telha TP40 #0,50 + PIR 50 + bandeja"))[:2] == ("OA", '5"')
    assert PT.parafuso_da_telha("cobertura", PT.tipo_da_telha("Isopainel EPS 50"))[:2] == ("OA", '2"')
    assert PT.parafuso_da_telha("fechamento", PT.tipo_da_telha("TP40 0,43"))[:2] == ("OB", '3/4"')
    assert PT.parafuso_da_telha("fechamento", PT.tipo_da_telha("TP25 0,43 interno"))[:2] == ("OB", '3/4"')
    assert PT.parafuso_da_telha("forro", PT.tipo_da_telha("TP40 forro"))[:2] == ("OB", '3/4"')
    tp, comp, pend = PT.parafuso_da_telha("fechamento", PT.tipo_da_telha("Telha TP40 PIR 50 branca"))
    assert tp is None and comp is None and "perguntar ao usuário" in pend           # sem comprimento chutado


def test_cor_da_cabeca_e_a_da_telha():
    assert PT.cor_da_telha("Telha TL01 TP40 PIR 50 0,43/0,43 branca RAL 9003") == "branca RAL 9003"
    assert PT.cor_da_telha("Telha TP40 #0,50 (aço nat.)") == "natural"
    assert PT.cor_da_telha("TR40 0,50 mm Galvalume") == "natural"
    assert PT.cor_da_telha("TELHA TP40 ESP.0.50") == ""
    T = [{"id": "t", "nome": "TELHA TP40 ESP.0.50", "camada": "Telhas", "texto": "TELHA TP40 ESP.0.50", "uso": "cobertura",
          "ml": 6.0, "apoios": 4, "pontas": 2}]
    L = PT.parafusos_de_telha(None, T, telha_dos_dados="TP40 0,50 bege RAL 1015")["linhas"]
    assert all(x["cor"] == "bege RAL 1015" for x in L), L                         # a cor dos dados quando o IFC não traz


def test_aviso_fora_da_mediana_hermes():
    poucos = [{"id": str(i), "nome": "TP40 0,50 natural", "camada": "Telhas", "texto": "TP40 0,50 aço nat.", "uso": "cobertura",
               "ml": 10.0, "apoios": 2, "pontas": 2} for i in range(100)]          # 600 / 1.000 ml = 0,6 pç/ml
    R = PT.parafusos_de_telha(None, poucos)
    assert any("mediana Hermes" in a for a in R["avisos"]), R["avisos"]
    certos = [dict(t, apoios=7) for t in poucos]                                  # 100 × 21 / 1.000 ml = 2,1 pç/ml
    assert not any("mediana Hermes" in a for a in PT.parafusos_de_telha(None, certos)["avisos"])


def _obra():
    """Cobertura plana de 4 telhas TP40 (980 × 6.000) sobre 4 terças Ue 150 (uma transpassada: 2 barras na mesma linha), um banzo
    paralelo à telha embaixo das terças e um montante; uma telha de fechamento em pé numa longarina; uma telha solta, sem apoio."""
    doc = Documento(nome="parafusos-telha")
    xs = (200.0, 2000.0, 4000.0, 5800.0)
    tercas = []
    for x in xs:
        tercas.append(Barra(nome="TC", camada="Terças", inicio=(x, -500.0, 3000.0), fim=(x, 4500.0, 3000.0),
                            perfil="Ue 150×60×20×2,25", papel="terça"))
    tercas.append(Barra(nome="TC", camada="Terças", inicio=(2000.0, 3000.0, 3000.0), fim=(2000.0, 8000.0, 3000.0),
                        perfil="Ue 150×60×20×2,25", papel="terça"))                  # transpasse da terça de x = 2.000
    for b in tercas:
        doc.add(b)
    topo = max(v[2] for v in G.malha(tercas[0])[0])
    doc.add(Barra(nome="BS", camada="Tesouras", inicio=(0.0, 1000.0, topo - 400.0), fim=(6000.0, 1000.0, topo - 400.0),
                  perfil="U 150×50×2,65 (FF)", papel="banzo"))
    doc.add(Barra(nome="MT", camada="Tesouras", inicio=(3000.0, 1000.0, topo - 1200.0), fim=(3000.0, 1000.0, topo),
                  perfil="L 50×3 (FF)", papel="montante"))
    for k in range(4):
        doc.add(_caixa("Telha TP40 0,50 bege RAL 1015", 0.0, 6000.0, 980.0 * k, 980.0 * (k + 1), topo, topo + 40.0))
    # fechamento: telha em pé (plano x = 10.000) encostada numa longarina horizontal
    lg = Barra(nome="LG", camada="Longarinas", inicio=(10000.0, -500.0, 1500.0), fim=(10000.0, 2000.0, 1500.0),
               perfil="Ue 150×60×20×2,25", papel="longarina")
    doc.add(lg)
    Vl = np.asarray(G.malha(lg)[0], float)
    xf = Vl[:, 0].max()
    doc.add(_caixa("Telha TP40 0,43 bege RAL 1015 (fechamento)", xf, xf + 40.0, 0.0, 980.0, 0.0, 3000.0, camada="Telhas — fechamento"))
    doc.add(_caixa("Telha TP40 0,50 bege RAL 1015", 20000.0, 26000.0, 0.0, 980.0, 9000.0, 9040.0))          # solta
    return doc


def test_contagem_pelo_3d():
    T = PT.apoios_por_telha(_obra())
    cob = sorted((t["apoios"], t["pontas"]) for t in T if t["uso"] == "cobertura")
    assert cob == [(0, 0), (4, 2), (4, 2), (4, 2), (4, 2)], T     # o transpasse conta 1; banzo e montante não; a solta 0
    fech = [t for t in T if t["uso"] == "fechamento"]
    assert len(fech) == 1 and fech[0]["apoios"] == 1, fech
    R = PT.parafusos_de_telha(None, T)
    por = {x["item"]: x for x in R["linhas"]}
    assert por['OA 2.3/8"']["qtd"] == 100 and por['OA 2.3/8"']["apoios"] == 16      # 4 × 4 × 3 + 3 = 51 → 100
    assert por['OB 3/4"']["qtd"] == 50                                                # 3 → 50
    assert por['Costura 7/8"']["qtd"] == 40                                           # (100 + 50) ÷ 4 = 37,5 → 40
    assert all(x["cor"] == "bege RAL 1015" and "bege RAL 1015" in x["descricao"] for x in R["linhas"])
    assert any("sem apoio achado" in a for a in R["avisos"]), R["avisos"]


def _cobertura_de_beiral_curvo():
    """Como a Sala de Compressores da Sooro (IFC do TecnoMETAL): duas águas de 10 % com cumeeira em x = 8.000; em cada água a telha
    principal sobre 4 terças, a ponta da cumeeira (0,25 m) à parte com a terça da cumeeira, e o beiral curvo partido em 3 facetas
    de 0,1 m até a saia em pé de 0,9 m, presa em 2 longarinas. Uma faixa só por água: 4 + 1 + 2 = 7 apoios, 2 de ponta."""
    doc = Documento(nome="beiral-curvo")
    inc = 0.1
    z = lambda x: 5000.0 + inc * (x if x <= 8000.0 else 16000.0 - x)       # noqa: E731 — face de baixo da telha
    for lado in (+1, -1):
        X = (lambda x: x) if lado > 0 else (lambda x: 16000.0 - x)          # noqa: E731
        # terças: 4 sob a principal + 1 sob a ponta da cumeeira; a mesa de cima encostada na telha
        for xt in (1000.0, 3000.0, 5000.0, 7000.0, 7900.0):
            xx = X(xt)
            t = Barra(nome="TC", camada="Terças", inicio=(xx, -500.0, 0.0), fim=(xx, 1500.0, 0.0), perfil="Ue 150×60×20×2,25", papel="terça")
            topo = max(v[2] for v in G.malha(t)[0])
            dz = z(xx) - topo
            t.inicio, t.fim = (xx, -500.0, dz), (xx, 1500.0, dz)
            doc.add(t)
        # a principal (500 → 7.750) e a ponta da cumeeira (7.750 → 8.000)
        doc.add(_placa("TELHA TP40 0.65MM", (X(500.0), z(X(500.0))), (X(7750.0), z(X(7750.0))), 0.0, 1031.0))
        doc.add(_placa("TELHA TP40 0.65MM", (X(7750.0), z(X(7750.0))), (X(8000.0), z(X(8000.0))), 0.0, 1031.0))
        # o beiral curvo: 3 facetas descendo de x = 500 até x = 300, e a saia em pé de x = 300
        pts = [(500.0, z(500.0)), (430.0, z(500.0) - 40.0), (360.0, z(500.0) - 110.0), (300.0, z(500.0) - 200.0)]
        for a, b in zip(pts, pts[1:]):
            doc.add(_placa("TELHA TP40 0.65MM", (X(a[0]), a[1]), (X(b[0]), b[1]), 0.0, 1031.0))
        zs = pts[-1][1]
        saia = _placa("TELHA TP40 0.65MM", (X(300.0), zs - 900.0), (X(300.0), zs), 0.0, 1031.0)
        doc.add(saia)
        xs_face = min(v[0] for v in saia.vertices) if lado > 0 else max(v[0] for v in saia.vertices)
        for zl in (zs - 700.0, zs - 300.0):
            lg = Barra(nome="LG", camada="Longarinas", inicio=(0.0, -500.0, zl), fim=(0.0, 1500.0, zl), perfil="Ue 150×60×20×2,25",
                       papel="longarina")
            V = np.asarray(G.malha(lg)[0], float)
            dx = (xs_face - V[:, 0].max()) if lado > 0 else (xs_face - V[:, 0].min())
            lg.inicio, lg.fim = (dx, -500.0, zl), (dx, 1500.0, zl)
            doc.add(lg)
    return doc


def test_beiral_curvo_e_cumeeira_uma_faixa_por_agua():
    T = PT.apoios_por_telha(_cobertura_de_beiral_curvo())
    cob = sorted((t["apoios"], t["pontas"], t["pedacos"]) for t in T)
    assert cob == [(7, 2, 6), (7, 2, 6)], T                 # 2 faixas (uma por água), cada uma com os 6 pedaços dela
    assert [t["apoios_em_pe"] for t in T] == [2, 2], T      # as 2 longarinas da saia em pé
    R = PT.parafusos_de_telha(None, T)
    # OA ou OB pela posição da telha em cada apoio (usuário 09/11, "na vertical entra como fechamento"): as 5 terças da parte
    # deitada OA (2 × 5 × 3 = 30 → 50), as 2 longarinas da saia em pé OB (2 × 2 × 3 = 12 → 50); costura 100 ÷ 4 = 25
    assert {x["item"]: x["qtd"] for x in R["linhas"]} == {'OA 2.3/8"': 50, 'OB 3/4"': 50, 'Costura 7/8"': 25}
    por = {x["item"]: x for x in R["linhas"]}
    assert por['OA 2.3/8"']["apoios"] == 10 and por['OB 3/4"']["apoios"] == 4


def test_oa_ou_ob_pela_posicao_da_telha_em_cada_apoio():
    """Os 3 casos do REGRAS (1ad1b48). 1: a Sala de Compressores — faixa da multidobra com 8 apoios, 6 terças deitadas (OA) e
    2 longarinas da saia em pé (OB): 64 faixas → OA 64 × 6 × 3 = 1.152 → 1.200; OB (313 + 128) × 3 = 1.323 → 1.350; costura
    (1.200 + 1.350) ÷ 4 = 637,5 → 640 (antes, tudo OA: 1.550 / 950 / 625). 2: o oitão (fechamento), todo OB. 3: a telha reta da
    cobertura, toda OA. O recorte sem apoio em pé vai como fechamento."""
    multi = {"id": "m", "nome": "TELHA TP40 0.50MM", "camada": "Telhas", "texto": "TELHA TP40 0.50MM", "uso": "cobertura",
             "ml": 10.0, "largura": 1031, "apoios": 8, "pontas": 2, "apoios_em_pe": 2, "ml_em_pe": 0.9}
    (d, ud), (p, up) = PT._partes(multi)
    assert (ud, d["apoios"], up, p["apoios"]) == ("cobertura", 6, "fechamento", 2)
    assert PT.arredondar(64 * PT.fixacoes_da_telha(d, "OA"), 50) == 1200
    assert PT.arredondar(313 * PT.FIX_FECHAMENTO + 64 * PT.fixacoes_da_telha(p, "OB"), 50) == 1350
    assert PT.costura(1200, 1350) == 640
    oitao = dict(multi, uso="fechamento", apoios=4, apoios_em_pe=4)
    assert [u for _t, u in PT._partes(oitao)] == ["fechamento"]
    reta = dict(multi, apoios=4, apoios_em_pe=0)
    assert [u for _t, u in PT._partes(reta)] == ["cobertura"]
    assert [u for _t, u in PT._partes(dict(multi, apoios=0, apoios_em_pe=0, em_pe=True))] == ["fechamento"]


def test_no_resumo_de_compra():
    """O resumo de compra traz as linhas (e a aba do xlsx), e os avisos da COM-05 vão para os avisos do resumo."""
    from nucleo2d.detalhar import detalhar
    from nucleo2d.detalhe.base import _categoria
    from saida import lista_producao, resumos
    doc = _obra()
    r = detalhar(doc, grupos=["localizacao"], converter=False)
    cat = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    lista = lista_producao.montar(r["objetos_posicoes"], cat, r["acessorios"], pecas=r["objetos_pecas"], projeto={"nome": "pt"})
    lev = {"posicoes": r["objetos_posicoes"], "pecas": r["objetos_pecas"], "acessorios": r["acessorios"], "avisos": r["avisos"]}
    R = resumos.levantar_resumos(doc, lev, lista, r.get("nomes") or {}, {})
    itens = {x["item"]: x["qtd"] for x in R["compra"]["parafusos_telha"]}
    assert itens == {'OA 2.3/8"': 100, 'OB 3/4"': 50, 'Costura 7/8"': 40}, itens
    assert any(a.startswith("COM-05") for a in R["avisos"])
    assert "Parafusos de telha" in resumos.html_resumo_materiais(R)


def test_biblioteca_de_acessorios_na_regra_nova():
    """O item "Fixação da telha na terça" da biblioteca saía "Autobrocante 12-14 × 1"" a 2,2/m² — agora a COM-05."""
    from nucleo import acessorios as A
    r = A.montar("fixacao_telha", {"telhas": 100, "apoios": 9})
    d = {p["descricao"]: p["qtd"] for p in r["pecas"]}
    assert d == {'Parafuso autobrocante OA 2.3/8" – na cor da telha (com arruela de vedação)': 2700,       # 100 × 9 × 3
                 'Parafuso autobrocante de costura 7/8" – na cor da telha': 675}, d
    assert not any("12-14" in k or '1"' in k for k in d)


def test_biblioteca_aceita_os_parametros_antigos():
    """Compatibilidade (GESTÃO N.6, 09/11): o b083a50 tirou "area" e "densidade" do fixacao_telha e o quantitativos_dados.py
    do Galpão Novo, que lia o padrão da densidade no REGISTRO, parou (StopIteration). Os dois voltam como parâmetros sem uso:
    quem lê ou passa não quebra, e a conta segue a COM-05."""
    from nucleo import acessorios as A
    pr = {x.chave: x.padrao for x in A.REGISTRO["fixacao_telha"].parametros}
    assert float(pr["densidade"]) == 2.2 and float(pr["area"]) == 450
    r = A.montar("fixacao_telha", {"telhas": 100, "apoios": 9, "area": 1000, "densidade": 2.2})
    d = {p["descricao"]: p["qtd"] for p in r["pecas"]}
    assert d['Parafuso autobrocante OA 2.3/8" – na cor da telha (com arruela de vedação)'] == 2700, d
