# -*- coding: utf-8 -*-
"""As telhas lançadas em cima das terças (nucleo3d/telhas_cobertura.py, 12/10/2026)."""
from nucleo3d.modelo import Barra, Documento
from nucleo3d import telhas_cobertura as T

PERFIL = "U 100×40×2,65 (FF)"


def _terca(doc, x, z, sigla, y0=0.0, y1=6000.0):
    b = Barra(inicio=(x, y0, z), fim=(x, y1, z), perfil=PERFIL, papel="terça", camada="Terças")
    b.atributos = {"origem": {"sigla": sigla}}
    doc.add(b)
    return b


def _agua(doc, x0, n, z0, inclinacao, passo=1400.0, sigla="TC1"):
    for i in range(n):
        _terca(doc, x0 + i * passo, z0 + i * passo * inclinacao, sigla)


def test_agua_reta_de_5_por_cento():
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)
    r = T.lancar(doc)
    assert r["panos"] == 5
    assert r["fora_do_plano"] == []
    assert [a["caida_pct"] for a in r["aguas"]] == [5.0]
    # a área: 5 vãos de 1,4 m (inclinados) por 6 m
    assert abs(r["area_m2"] - 5 * 1.4017 * 6.0) < 0.1
    assert len([s for s in doc.solidos if s.camada == "Telhas"]) == 5


def test_terca_erguida_no_meio_da_agua():
    doc = Documento()
    _agua(doc, 0.0, 7, 7000.0, 0.05)
    alta = [b for b in doc.barras if abs(b.inicio[0] - 4200.0) < 1][0]
    alta.inicio = (alta.inicio[0], alta.inicio[1], alta.inicio[2] + 80.0)
    alta.fim = (alta.fim[0], alta.fim[1], alta.fim[2] + 80.0)
    r = T.lancar(doc)
    assert len(r["fora_do_plano"]) == 1
    assert 70 <= r["fora_do_plano"][0]["desvio"] <= 90


def test_calha_terca_baixa_e_transicao_no_meio():
    """duas águas que descem para uma calha (a transição em x 7000): a telha não passa por cima dela, e a terça da
    água da direita, encostada na calha 100 mm abaixo do plano dela, é apontada"""
    doc = Documento()
    _agua(doc, 1400.0, 4, 7000.0 + 4 * 1400 * 0.05, -0.05)                  # 1400…5600, descendo até a calha
    _terca(doc, 7100.0, 7000.0 - 0.05 * 100 - 100.0 + 5.0, "TC2")          # junto da calha, 100 mm abaixo
    _agua(doc, 8500.0, 4, 7000.0 + 0.05 * 1500, 0.05, sigla="TC2")         # 8500…12700, subindo
    for z in (6000.0, 6900.0):
        tr = Barra(inicio=(7000.0, -500.0, z), fim=(7000.0, 6500.0, z), perfil="U 150×70×4,75 (FF)", papel="banzo", camada="Treliças")
        tr.atributos = {"origem": {"planta": "TRANSIÇÃO 1", "peca": "TRANSIÇÃO 1#1"}}
        doc.add(tr)
    r = T.lancar(doc)
    # nenhum pano entre x 5600 e 7100 (por cima da transição)
    entre = [s for s in doc.solidos if s.camada == "Telhas" and min(v[0] for v in s.vertices) < 7000 < max(v[0] for v in s.vertices)]
    assert entre == []
    baixas = [f for f in r["fora_do_plano"] if f["sigla"] == "TC2" and abs(f["ponto"][0] - 7100) < 1]
    assert baixas and -110 <= baixas[0]["desvio"] <= -90


def test_relancar_tira_os_panos_anteriores():
    doc = Documento()
    _agua(doc, 0.0, 4, 7000.0, 0.05)
    T.lancar(doc)
    T.lancar(doc)
    assert len([s for s in doc.solidos if (s.atributos or {}).get("telha_lancada")]) == 3
