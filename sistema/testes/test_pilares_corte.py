# -*- coding: utf-8 -*-
"""Pilares com corte próprio (nucleo3d/pilares_corte.py): o título "PMn - kX" com as vistas
rotuladas dá o pilar — reto com copa e mão-francesa, ou inclinado — sem misturar com o desenho
vizinho, e a linha dupla da cantoneira vira uma barra só."""
import math
from nucleo3d import pilares_corte as pc


def _linha(a, b, camada="metalica3", id_=None):
    return {"id": id_ or "l%d%d%d%d" % (round(a[0]), round(a[1]), round(b[0]), round(b[1])), "tipo": "linha",
            "camada": camada, "a": list(a), "b": list(b)}


def _texto(t, p, id_=None):
    return {"id": id_ or "t" + t.replace(" ", ""), "tipo": "texto", "camada": "TEXTO", "texto": t, "posicao": list(p), "altura": 12.5}


def desenho_pm6(tx=100000.0, ty=50000.0):
    """PM6 - 1X: pilar reto de 5000 (duas bordas, 400 de largura) e, em cima, uma viga em cruz
    de 1500 para cada lado; a mão-francesa de cada lado desenhada em cantoneira dupla (duas
    linhas paralelas a 40 mm); a vista superior com a cruz; um desenho vizinho à direita que
    não pode entrar"""
    ents = [_texto("PM6 - 1X", (tx, ty)), _texto("VISTA LATERAL", (tx, ty + 500)), _texto("VISTA SUPERIOR", (tx, ty + 9000)),
            _texto("BANZO U150X70X4,75", (tx + 3000, ty + 8000)), _texto('DIAG/MONT 2L 2"X1/8"  3 PRES. L 1.1/2"X1/8"', (tx + 3000, ty + 7700))]
    x0, y0 = tx + 1000.0, ty + 1000.0                        # base do pilar
    for dx in (-200.0, 200.0):
        ents.append(_linha((x0 + dx, y0), (x0 + dx, y0 + 5000.0)))
    topo = y0 + 5000.0
    ents.append(_linha((x0 - 1500.0, topo), (x0 + 1500.0, topo)))            # a viga em cruz, vista de lado
    ents.append(_linha((x0 - 1500.0, topo + 150.0), (x0 + 1500.0, topo + 150.0)))
    for lado in (-1.0, 1.0):
        # a mão-francesa: uma diagonal do pilar (1200 abaixo do topo) à ponta do braço, em linha dupla
        a = (x0 + lado * 200.0, topo - 1200.0)
        b = (x0 + lado * 1450.0, topo - 30.0)
        n = (-(b[1] - a[1]), b[0] - a[0])
        L = math.hypot(*n)
        n = (n[0] / L * 20.0, n[1] / L * 20.0)
        ents.append(_linha((a[0] + n[0], a[1] + n[1]), (b[0] + n[0], b[1] + n[1]), "metalica2"))
        ents.append(_linha((a[0] - n[0], a[1] - n[1]), (b[0] - n[0], b[1] - n[1]), "metalica2"))
    # vista superior: a cruz, 1500 para cada lado
    cx, cy = tx + 1000.0, ty + 10500.0
    for dy in (-75.0, 75.0):
        ents.append(_linha((cx - 1500.0, cy + dy), (cx + 1500.0, cy + dy)))
    for dx in (-75.0, 75.0):
        ents.append(_linha((cx + dx, cy - 1500.0), (cx + dx, cy + 1500.0)))
    # o vizinho: uma treliça a 2 m à direita da copa, na mesma altura (não é deste pilar)
    vx = x0 + 4000.0
    ents.append(_linha((vx, topo), (vx + 3000.0, topo)))
    ents.append(_linha((vx, topo + 800.0), (vx + 3000.0, topo + 800.0)))
    for k in range(4):
        ents.append(_linha((vx + k * 1000.0, topo), (vx + k * 1000.0 + 500.0, topo + 800.0)))
    return ents


def desenho_pm8(tx=200000.0, ty=50000.0):
    """PM8 - 1X: perfil duplo inclinado a 50° (três linhas paralelas de 8000), e a vista frontal
    com duas bordas a 250 mm"""
    # a vista frontal a 9 m da lateral, como na folha (a inclinada sobe até x +5,3 m)
    ents = [_texto("PM8 - 1X", (tx, ty)), _texto("VISTA LATERAL", (tx, ty + 500)), _texto("VISTA FRONTAL", (tx + 9000, ty + 500)),
            _texto("2Ue 250X125X25X4,75", (tx + 2000, ty + 4000))]
    ang = math.radians(50.0)
    for k in range(3):
        a = (tx + 200.0 + k * 125.0, ty + 1000.0)
        ents.append(_linha(a, (a[0] + 8000.0 * math.cos(ang), a[1] + 8000.0 * math.sin(ang))))
    for dx in (0.0, 250.0):
        ents.append(_linha((tx + 9000.0 + dx, ty + 1000.0), (tx + 9000.0 + dx, ty + 6000.0)))
    return ents


def test_arco_usa_os_angulos_inicio_e_fim_do_desenho():
    """o desenho guarda os ângulos do arco em "inicio"/"fim" (graus): do 2º quadrante só saem
    pontos com x ≤ 0 e y ≥ 0 — com a chave errada o arco começava em 0° e virava cordas fantasmas"""
    pts = pc._pts({"tipo": "arco", "centro": [0.0, 0.0], "raio": 1000.0, "inicio": 90.0, "fim": 180.0})
    assert len(pts) >= 5
    assert all(p[0] <= 1e-6 and p[1] >= -1e-6 for p in pts)
    assert abs(pts[0][1] - 1000.0) < 1e-6 and abs(pts[-1][0] + 1000.0) < 1e-6


def test_le_o_pilar_reto_com_copa_e_mao_francesa():
    ents = desenho_pm6()
    textos = [e for e in ents if e["tipo"] == "texto"]
    cortes = pc.ler_cortes_de_pilar(ents, textos)
    assert "PM6" in cortes and cortes["PM6"]["qtd"] == 1
    r = pc.interpretar(cortes["PM6"])
    assert r["tipo"] == "reto"
    assert abs(r["pilar"]["L"] - 5000.0) < 1.0 and abs(r["pilar"]["largura"] - 400.0) < 1.0
    copa = r["copa"]
    assert copa["altura"] == 0.0                                      # uma altura só (as duas linhas do perfil)
    assert abs(copa["esq"] + 1500.0) < 1.0 and abs(copa["dir"] - 1500.0) < 1.0   # o vizinho não entrou
    assert len(copa["maos"][1]) == 1 and len(copa["maos"][-1]) == 1  # a linha dupla virou uma
    s0, dz0, s1, dz1 = copa["maos"][1][0]
    assert abs(min(dz0, dz1) + 1200.0) < 1.0 and abs(max(s0, s1) - 1450.0) < 1.0
    assert r["bracos"] == {"x": (-1500.0, 1500.0), "y": (-1500.0, 1500.0)}
    assert r["perfis"]["banzo"]["perfil"].startswith("U 150") and r["perfis"]["alma"]["mult"] == 2


def test_le_o_pilar_inclinado():
    ents = desenho_pm8()
    textos = [e for e in ents if e["tipo"] == "texto"]
    r = pc.interpretar(pc.ler_cortes_de_pilar(ents, textos)["PM8"])
    assert r["tipo"] == "inclinado"
    assert abs(r["pilar"]["ang"] - 50.0) < 0.5 and abs(r["pilar"]["L"] - 8000.0) < 1.0
    assert abs(r["afastamento"] - 250.0) < 1.0
    assert r["perfis"]["pilar"]["mult"] == 2


def test_monta_copa_em_cruz_e_inclinado():
    """a montagem: a copa em cruz nos quatro braços com as mãos-francesas, e o inclinado saindo
    da placa no sentido do lado comprido, para o lado da estrutura"""
    ents = desenho_pm6() + desenho_pm8()
    textos = [e for e in ents if e["tipo"] == "texto"]
    cortes = pc.ler_cortes_de_pilar(ents, textos)
    barras = []

    def barra(p0, p1, perfil, papel, camada, conjunto=None, rot=0.0, origem=None):
        barras.append((p0, p1, perfil, papel, conjunto, origem or {}, camada))
        return True
    locados = [{"x": 0.0, "y": 0.0, "rot": 0.0, "nome": "PM6(400X200X50X3,75)", "perfil": "Ue 400×200×50×3,75"},
               {"x": 10000.0, "y": 0.0, "rot": 0.0, "nome": "PM8(250X125X25X4,75)", "perfil": "Ue 250×125×25×4,75"}]
    # a placa do PM8 na "locação": 900 × 400, lado comprido ao longo de x
    placa = [{"id": "ch", "tipo": "polilinha", "camada": "Chapas", "fechada": True,
              "vertices": [[9550.0, -200.0], [10450.0, -200.0], [10450.0, 200.0], [9550.0, 200.0]]}]
    avisos = []
    r = pc.montar(cortes, locados, barra, 6000.0, 0.0, lambda p: abs(p[0] - 14000.0) + abs(p[1]), placa, lambda p: p, avisos)
    assert r["inclinados"] == {"PM8(250X125X25X4,75)"}
    copa = [b for b in barras if b[3] == "banzo"]
    assert len(copa) == 4                                            # quatro braços, uma altura só
    pontas = sorted((round(b[1][0]), round(b[1][1])) for b in copa)
    assert pontas == [(-1500, 0), (0, -1500), (0, 1500), (1500, 0)]
    assert all(abs(b[0][2] - 5000.0) < 1.0 for b in copa)            # em cima do pilar de 5 m
    maos = [b for b in barras if b[3] in ("diagonal", "montante") and b[5].get("mao_francesa")]
    assert len(maos) == 4
    incl = [b for b in barras if b[3] == "pilar"]
    assert len(incl) == 2                                            # perfil duplo
    p0, p1 = incl[0][0], incl[0][1]
    assert p1[0] > p0[0] + 4000.0 and abs(p1[1] - p0[1]) < 200.0   # inclina em +x, para a estrutura em x=14000
    assert abs(p1[2] - 8000.0 * math.sin(math.radians(50.0))) < 5.0
    assert any("inclinado" in a for a in avisos) and any("cruz" in a for a in avisos)
    assert {b[6] for b in barras} == {"Pilares"}                  # a copa e as mãos-francesas vão com o pilar
