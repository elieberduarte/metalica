"""O que a Kaefer do engenheiro (15/10/2026) pediu do motor: a parede de lona que não desce até o chão
(`parede_z_inferior`) e a viga do topo recebendo a faixa de cima (`parede_nas_vigas`); a longarina presa no pilar por
onde passa; o chumbador fora do esqueleto; o pé do montante de apoio sobre a viga alta; o tirante só à tração na 2ª
ordem; o tubo circular fora do catálogo pelas fórmulas."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo import perfis_fabrica as PF  # noqa: E402
from nucleo3d import analise_estrutural as AE  # noqa: E402
from nucleo3d import analitico as AN  # noqa: E402
from nucleo3d import segunda_ordem as SO  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402

from test_analise_bordas import PAR, UE, W, _galpao, _q_do_galpao  # noqa: E402


def _longarinas_da_face(M, y, z):
    return [i for i, br in enumerate(M["barras"]) if br["papel"] == "longarina"
            and abs(M["nos"][br["a"]][1] - y) < 1e-6 and abs(M["nos"][br["a"]][2] - z) < 1e-6]


def test_parede_que_comeca_acima_do_chao_tira_a_faixa_de_baixo():
    """longarinas a +2,00 e +4,00, beiral +6,00: com a parede desde o chão a fiada de +2,00 leva 0 → 3 m; com a lona
    começando a +2,00 ela leva só 2 → 3 m (1 m). A de +4,00 continua com 3 → 6 m. V→ C_pi +0,2, barlavento (y = 0):
    w = (0,7 − 0,2)·q·faixa"""
    q = _q_do_galpao()
    for z_inf, faixa2 in ((0.0, 3.0), (2.0, 1.0)):
        M = AE.montar(_galpao(longarinas=True), dict(PAR, parede_z_inferior=z_inf))
        casos, info, _ = AE.cargas(M)
        assert info["vento"]["paredes"]["z_inferior"] == pytest.approx(z_inf)
        d = casos["V→ cpi+0,2"]["dist"]
        for i in _longarinas_da_face(M, 0.0, 2.0):
            assert d[i][1] == pytest.approx(0.5 * q * faixa2, rel=1e-9)
        for i in _longarinas_da_face(M, 0.0, 4.0):
            assert d[i][1] == pytest.approx(0.5 * q * 3.0, rel=1e-9)


def test_viga_do_topo_da_parede_recebe_a_faixa_de_cima():
    """com uma viga no alinhamento da face (y = 0, +6,00) e `parede_nas_vigas`, a fiada de +4,00 leva 3 → 5 m e a viga
    5 → 6 m (o beiral); sem a opção, a de +4,00 leva 3 → 6 m e a viga nada"""
    q = _q_do_galpao()
    doc = _galpao(longarinas=True)
    for x0, x1 in ((0.0, 6000.0), (6000.0, 12000.0), (12000.0, 18000.0)):
        doc.add(Barra(inicio=(x0, 0.0, 6000.0), fim=(x1, 0.0, 6000.0), perfil=W, papel="viga"))
    for nas_vigas, faixa4, faixa_viga in ((False, 3.0, None), (True, 2.0, 1.0)):
        M = AE.montar(doc, dict(PAR, parede_nas_vigas=nas_vigas))
        casos, info, _ = AE.cargas(M)
        d = casos["V→ cpi+0,2"]["dist"]
        for i in _longarinas_da_face(M, 0.0, 4.0):
            assert d[i][1] == pytest.approx(0.5 * q * faixa4, rel=1e-9)
        vigas = [i for i, br in enumerate(M["barras"]) if br["papel"] == "viga" and abs(M["nos"][br["a"]][1]) < 1e-6]
        assert vigas
        if faixa_viga is None:
            assert all(i not in d for i in vigas)
        else:
            assert info["vento"]["paredes"]["vigas_na_parede"] == len(vigas)
            for i in vigas:
                assert d[i][1] == pytest.approx(0.5 * q * faixa_viga, rel=1e-9)


def _dois_pilares_com_travessa(chumbador=False):
    """dois pilares de 6 m inteiros (sem nó no meio) e uma longarina de um ao outro a +3,00"""
    doc = Documento(nome="travessa")
    for x in (0.0, 5000.0):
        doc.add(Barra(inicio=(x, 0.0, 0.0), fim=(x, 0.0, 6000.0), perfil=W, papel="pilar"))
    doc.add(Barra(inicio=(0.0, 0.0, 6000.0), fim=(5000.0, 0.0, 6000.0), perfil=W, papel="viga"))
    doc.add(Barra(inicio=(0.0, 0.0, 3000.0), fim=(5000.0, 0.0, 3000.0), perfil=UE, papel="longarina"))
    if chumbador:
        doc.add(Barra(inicio=(100.0, 0.0, 60.0), fim=(100.0, 0.0, -800.0), perfil="Barra redonda ø 20 mm", papel="chumbador"))
    return doc


def test_longarina_presa_no_pilar_por_onde_passa():
    """a ponta da longarina no eixo do pilar contínuo parte o pilar ali (antes ela ficava solta: só se prendia onde um
    contraventamento criava o nó)"""
    A = AN.analitico(_dois_pilares_com_travessa())
    assert A["resumo"]["soltas"] == 0
    nos = A["nos"]
    pil = [b for b in A["barras"] if b["papel"] == "pilar"]
    assert len(pil) == 4                                     # cada pilar em dois trechos
    lon = next(b for b in A["barras"] if b["papel"] == "longarina")
    for k in ("a", "b"):
        assert nos[lon[k]][2] == pytest.approx(3000.0)
        assert sum(1 for b in pil if lon[k] in (b["a"], b["b"])) == 2


def test_chumbador_fica_fora_do_esqueleto():
    A = AN.analitico(_dois_pilares_com_travessa(chumbador=True))
    assert A["resumo"]["soltas"] == 0
    assert not [b for b in A["barras"] if b["papel"] == "chumbador"]


def test_pe_do_montante_apoia_na_viga_alta_e_nao_na_propria_diagonal():
    """a tesoura apoiada em cima da W410 (eixo 204 mm abaixo do pé do montante) com a diagonal da própria tesoura
    chegando 176 mm acima do pé: o pé desce até a viga"""
    doc = Documento(nome="apoio")
    doc.add(Barra(inicio=(0.0, -2000.0, 7796.5), fim=(0.0, 2000.0, 7796.5), perfil="W 410×60,0", papel="viga"))
    t = {"elemento": "trelica", "origem": {"peca": "T1"}, "marca": "T1"}
    doc.add(Barra(inicio=(0.0, 0.0, 8000.0), fim=(0.0, 0.0, 9000.0), perfil="TQ 50×50×2,0", papel="montante",
                  atributos=dict(t, papel_trelica="montante")))
    doc.add(Barra(inicio=(600.0, 0.0, 8800.0), fim=(0.0, 0.0, 8176.0), perfil="TQ 50×50×2,0", papel="diagonal",
                  atributos=dict(t, papel_trelica="diagonal")))
    doc.add(Barra(inicio=(0.0, 0.0, 8800.0), fim=(3000.0, 0.0, 8800.0), perfil="TQ 50×50×2,0", papel="banzo",
                  atributos=dict(t, papel_trelica="banzo_inf")))
    doc.add(Barra(inicio=(0.0, 0.0, 9000.0), fim=(3000.0, 0.0, 9300.0), perfil="TQ 50×50×2,0", papel="banzo",
                  atributos=dict(t, papel_trelica="banzo_sup")))
    A = AN.analitico(doc)
    nos = A["nos"]
    mont = [b for b in A["barras"] if b["papel"] == "montante"]
    pe = min((b[k] for b in mont for k in ("a", "b")), key=lambda n: nos[n][2])
    assert nos[pe][2] == pytest.approx(7796.5)
    assert any(b["papel"] == "viga" and pe in (b["a"], b["b"]) for b in A["barras"])


def test_tubo_circular_fora_do_catalogo_pelas_formulas():
    p = PF.perfil_de_fabrica("TC 180×6,3")
    assert p is not None and p.tipo == "tubo"
    De, Di = 18.0, 18.0 - 2 * 0.63
    assert p.dados["A"] == pytest.approx(math.pi * (De ** 2 - Di ** 2) / 4, rel=1e-3)
    assert p.dados["Ix"] == pytest.approx(math.pi * (De ** 4 - Di ** 4) / 64, rel=1e-3)
    # o do catálogo continua vindo da tabela; as fórmulas batem com ela
    s_tab = AE._secao("TC 168,3×6,4", False, {})
    q = PF.tubo_circular_de("168.3X6.4", "x")
    assert q.dados["A"] == pytest.approx(s_tab["A"] * 1e4, rel=0.01)
    assert AE._secao("TC 180×6,3", False, {}) is not None


def _quadro_com_x(so_tracao):
    """quadro de 4 × 4 m: pilares muito flexíveis engastados na base (quase sem rigidez lateral), viga rotulada, X de
    barra redonda Ø16; força H no topo. Só tração: a diagonal comprimida sai e a tracionada leva ≈ H/cos θ"""
    nos = np.array([[0, 0, 0], [4, 0, 0], [0, 0, 4], [4, 0, 4]], float)
    sec = {"A": 0.01, "Iz": 1e-8, "Iy": 1e-8, "J": 1e-8, "Wz": 1e-5, "Wy": 1e-5, "kg_m": 0.0, "tipo": "I"}
    d16 = math.pi * 0.016 ** 2 / 4
    tir = {"A": d16, "Iz": d16 ** 2 / (4 * math.pi), "Iy": d16 ** 2 / (4 * math.pi), "J": 1e-12, "Wz": 1e-9, "Wy": 1e-9,
           "kg_m": 0.0, "tipo": "barra", "redonda": True}
    rot = [4, 5, 10, 11]

    def br(a, b, s, papel, soltos):
        return {"a": a, "b": b, "L": float(np.linalg.norm(nos[b] - nos[a])), "papel": papel, "sec": s,
                "R": AE._eixos(nos[a], nos[b], 0.0), "soltos": soltos, "papel_trelica": None, "elemento": None,
                "grupo": None, "marca": None, "perfil": "", "ids": [], "aco": "ASTM A36"}
    bs = [br(0, 2, sec, "pilar", []), br(1, 3, sec, "pilar", []), br(2, 3, sec, "viga", rot),
          br(0, 3, tir, "contraventamento", rot), br(1, 2, tir, "contraventamento", rot)]
    M = {"nos": nos, "barras": bs, "apoios": [{"no": 0, "tipo": "engastada", "chave": "0,0"},
                                              {"no": 1, "tipo": "engastada", "chave": "4000,0"}],
         "par": dict(AE.PARAMETROS_PADRAO, tirantes_so_tracao=so_tracao)}
    casos = {"G": {"dist": {}, "nodal": {}, "nos": {2: np.array([0, 0, -1.0]), 3: np.array([0, 0, -1.0])}},
             "V": {"dist": {}, "nodal": {}, "nos": {2: np.array([10.0, 0, 0])}}}
    sol = AE.resolver(M, casos)
    combs = {"ELU V": {"tipo": "ELU", "fatores": {"G": 1.0, "V": 1.0}, "descricao": ""}}
    return SO.analisar(M, sol, combs)["ELU V"]


def test_tirante_so_tracao_na_segunda_ordem():
    r = _quadro_com_x(True)
    assert r["instavel"] is None and r["convergiu"]
    assert r["tirantes_desligados"] == 1
    N = -r["pontas"][:, 0]
    assert N[3] == pytest.approx(10.0 * math.sqrt(2), rel=0.03)          # a que vai do pé (0) ao topo (3): tracionada
    assert abs(N[4]) < 1e-6                                              # a comprimida fora
    # com as duas trabalhando, a força divide (o modelo de antes)
    r2 = _quadro_com_x(False)
    N2 = -r2["pontas"][:, 0]
    assert r2["tirantes_desligados"] == 0
    assert N2[3] == pytest.approx(-N2[4], rel=0.05) and N2[3] < 0.6 * N[3]


def test_tubo_retangular_fora_do_catalogo_e_o_do_catalogo_batem():
    p = PF.perfil_de_fabrica("TR 127×100×2,0")
    assert p is not None and p.dados["tipo"] == "retangular" and (p.dados["h"], p.dados["b"]) == (127.0, 100.0)
    assert p.dados["A"] == pytest.approx(12.7 * 10.0 - 12.3 * 9.6, rel=1e-3)
    q = PF.tubo_retangular_de("100X40X1.5", "x")
    s_tab = AE._secao("TR 100×40×1,5", False, {})              # o do catálogo (cantos arredondados): perto
    assert q.dados["A"] == pytest.approx(s_tab["A"] * 1e4, rel=0.03)


def test_perfil_de_calculo_da_peca_vale_na_analise():
    """os 2 U boca com boca (a travessa da Kaefer) com perfil_calculo = o tubo que eles formam: a análise usa o tubo,
    uma barra só (não o par dobrado), e guarda o perfil modelado"""
    doc = _dois_pilares_com_travessa()
    lon = next(e for e in doc.entidades.values() if e.papel == "longarina")
    doc.remover(lon.id)
    for s, rot in ((1.0, 180.0), (-1.0, 0.0)):
        doc.add(Barra(inicio=(0.0, 38.1 * s, 3000.0), fim=(5000.0, 38.1 * s, 3000.0), perfil="U 127×50×2,00 (FF)",
                      rotacao=rot, papel="longarina",
                      atributos={"origem": {"peca": "TR1"}, "perfil_calculo": "TR 127×100×2,0"}))
    M = AE.montar(doc, PAR)
    lon = [br for br in M["barras"] if br["papel"] == "longarina"]
    assert lon and all(br["perfil"] == "TR 127×100×2,0" and not br["duplo"] and br["perfil_modelo"] == "U 127×50×2,00 (FF)"
                       for br in lon)
    assert lon[0]["sec"]["Iy"] == pytest.approx(AE._secao("TR 127×100×2,0", False, {})["Iy"])


def test_sanfona_do_3d_para_no_pe_da_tesoura_sobre_viga_alta():
    """a tesoura em cima da viga alta (eixo 204 mm abaixo do pé): a sanfona do 3D não desce até o eixo da viga"""
    from nucleo3d import cobertura_movel as CM
    from test_cobertura_movel import PAR as PAR_CM, _modelo
    doc = _modelo()
    for e in list(doc.entidades.values()):
        if e.papel == "viga":
            e.perfil = "W 410×60,0"
            e.inicio, e.fim = (e.inicio[0], e.inicio[1], 4796.5), (e.fim[0], e.fim[1], 4796.5)
        elif e.papel == "pilar":
            e.fim = (e.fim[0], e.fim[1], 4580.5)
    CM.aplicar(doc, PAR_CM, "aberta")
    zs = [min(e.inicio[2], e.fim[2]) for e in doc.entidades.values() if (e.atributos or {}).get("elemento") == "sanfona"]
    assert zs and min(zs) == pytest.approx(5000.0)
