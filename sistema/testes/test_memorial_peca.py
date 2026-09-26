# -*- coding: utf-8 -*-
"""Memorial de cálculo por peça em quatro camadas (0.8.28): hipóteses e passos de carga da
terça, explicações didáticas cobrindo tudo o que a terça produz, o documento HTML, o
caso de referência da terça T.C.5 da Sala dos Compressores resolvido à mão."""
import math
import os
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo import nbr14762 as cf                      # noqa: E402
from nucleo import verificar                            # noqa: E402
from nucleo.base import E, FONTES_DE_HIPOTESE           # noqa: E402
from nucleo3d import calculo_ifc                        # noqa: E402
from saida import didatica, memorial_peca               # noqa: E402
from testes.test_calculo_ifc import modelo              # noqa: E402,F401  (fixture)


# ------------------------------------------------------------ caso de referência: T.C.5
# Terça U 150×50×2,28 (FF), aço CIVIL 300, vão 4,938 m, largura tributária 1,522 m,
# telha 0,07 kN/m², sobrecarga 0,25 kN/m², sucção −0,7768 kN/m², 4 linhas de correntes,
# telhado a 11,31° (cálculo gravado em 22/09/2026 na obra do usuário). As contas abaixo
# foram feitas à mão, na ordem do memorial, e são o que o usuário confere na trilha.

VAO, LARG, THETA = 4.9384, 1.522, 11.31
G_TELHA, SC, P_SUC = 0.07, 0.25, 0.7768
PP = 4.34 * 9.80665 / 1000.0                    # kN/m (massa do U pela linha média)


def _cargas_a_mao():
    g = G_TELHA * LARG + PP                                       # 0,1491 kN/m
    q_sc = SC * LARG * math.cos(math.radians(THETA))             # 0,3731 kN/m
    q_g = 1.25 * g + 1.5 * q_sc                                  # 0,746 kN/m (sem pressão de vento)
    q_s = 1.4 * P_SUC * LARG - g                                 # 1,506 kN/m
    return g, q_sc, q_g, q_s


def test_cargas_da_terca_a_mao():
    g, q_sc, q_g, q_s = _cargas_a_mao()
    assert g == pytest.approx(0.149, abs=0.002)
    assert q_sc == pytest.approx(0.373, abs=0.002)
    assert q_g == pytest.approx(0.746, abs=0.003)
    assert q_s == pytest.approx(1.506, abs=0.003)


def test_terca_tc5_referencia():
    """A rotina reproduz a estática e as flechas feitas à mão, e a sucção governa."""
    g, q_sc, q_g, q_s = _cargas_a_mao()
    sec = cf.propriedades_u(150, 50, 2.28)
    r = cf.terca(sec, "CIVIL 300", vao=VAO, carga_gravidade=q_g, carga_succao=q_s, n_correntes=4,
                 inclinacao=THETA, carga_servico_gravidade=g + q_sc, carga_servico_succao=P_SUC * LARG - g)
    L = VAO * 100.0
    # estática da viga biapoiada
    assert r.dados["Mx_succao_kNcm"] == pytest.approx(q_s / 100.0 * L ** 2 / 8.0, rel=1e-6)
    assert r.dados["Mx_gravidade_kNcm"] == pytest.approx(q_g / 100.0 * math.cos(math.radians(THETA)) * L ** 2 / 8.0, rel=1e-6)
    assert r.dados["V_Sd_kN"] == pytest.approx(q_s / 100.0 * L / 2.0, rel=1e-6)
    assert r.dados["Lb_cm"] == pytest.approx(L / 5.0) and r.dados["Lt_cm"] == pytest.approx(L)
    # início de escoamento My = Wx·fy e a flecha clássica
    v_suc = next(v for v in r.verificacoes if v.titulo.startswith("Flexão Mx — combinação de sucção"))
    assert "705" in v_suc.passos[0].valor or f"{sec.Wx * 30:.0f}" in v_suc.passos[0].valor.replace(" ", "")
    fl = next(v for v in r.verificacoes if v.titulo.startswith("Flecha — gravidade"))
    w = (g + q_sc) / 100.0
    assert fl.Sd == pytest.approx(5 * w * L ** 4 / (384 * E * sec.Ix), rel=1e-6)
    assert fl.Rd == pytest.approx(L / 180.0)
    # o que governa é a sucção com a mesa inferior livre, e a peça reprova (como no cálculo gravado)
    assert r.critica is v_suc and not r.ok
    assert 1.15 < r.razao < 1.30


def test_terca_traz_hipoteses_e_cargas():
    sec = cf.propriedades_u(150, 50, 2.28)
    r = cf.terca(sec, "CIVIL 300", vao=5.0, carga_gravidade=0.8, carga_succao=1.2, n_correntes=2, inclinacao=10.0)
    chaves = [h.chave for h in r.hipoteses]
    for c in ("modelo_estatico", "secao", "aco", "gravidade_travamento", "succao_travamento", "cb", "flexao_y",
              "apoio", "interacao_mv", "servico"):
        assert c in chaves, c
    assert all(h.fonte in FONTES_DE_HIPOTESE for h in r.hipoteses)
    assert any("L<sub>b</sub> = L/(2 + 1)" in h.texto for h in r.hipoteses)
    textos = [p.texto for p in r.cargas]
    assert any(t.startswith("Momento máximo, sucção") for t in textos)
    assert any(t.startswith("Reação no apoio") for t in textos)
    # o U simples não tem enrijecedor: a hipótese da seção diz isso
    assert any("sem enrijecedor" in h.texto for h in r.hipoteses if h.chave == "secao")
    # serializado para o calculo.json
    d = verificar.serializar_resultado(r)
    assert d["hipoteses"][0]["chave"] == "modelo_estatico" and d["cargas"][0]["conta"]


def test_explicacoes_cobrem_a_terca():
    """Toda verificação e toda hipótese que a rotina da terça produz tem explicação escrita."""
    sec = cf.propriedades_u(150, 50, 2.28)
    r = cf.terca(sec, "CIVIL 300", vao=5.0, carga_gravidade=0.8, carga_succao=1.2, n_correntes=2, inclinacao=10.0)
    for v in r.verificacoes:
        assert didatica.explicar_verificacao(v.titulo), v.titulo
        for p in v.passos:
            assert didatica.explicar_passo(p.texto), p.texto
    for h in r.hipoteses:
        assert didatica.explicar_hipotese(h.chave), h.chave
    for p in r.cargas:
        assert didatica.explicar_passo(p.texto), p.texto
    for chave in ("vao", "largura", "inclinacao", "cargas_area", "vento", "combinacoes", "correntes", "flecha_limite"):
        assert didatica.explicar_hipotese(chave), chave
    assert didatica.explicar_verificacao("Verificação inexistente") is None


# ------------------------------------------------------------ pelo cálculo do IFC

def test_calculo_ifc_grava_hipoteses_da_terca(modelo):        # noqa: F811
    doc, nomes = modelo
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0, "sobrecarga": 0.25})
    v = next(x for x in r["verificacoes"] if x["marca"] == "P10")
    chaves = [h["chave"] for h in v["hipoteses"]]
    # as do modelo vêm antes das da rotina
    assert chaves[:3] == ["vao", "largura", "inclinacao"]
    assert "succao_travamento" in chaves and chaves.index("vento") < chaves.index("modelo_estatico")
    fontes = {h["chave"]: h["fonte"] for h in v["hipoteses"]}
    assert fontes["vao"] == "modelo" and fontes["cargas_area"] == "parametro" and fontes["combinacoes"] == "norma"
    assert v["cargas"][0]["texto"].startswith("Carga permanente por metro")
    # valores por combinação: gravidade e sucção não são mais o mesmo número
    el = r["elementos"]["P10"]
    ent = el["entrada"]
    L = ent["vao_m"]
    assert el["valores"]["C1 gravidade"]["M"] == pytest.approx(ent["q_g"] * L * L / 8.0, abs=0.02)
    assert el["valores"]["C2 sucção 1"]["M"] == pytest.approx(ent["q_s"] * L * L / 8.0, abs=0.02)
    assert el["valores"]["envoltoria"]["M"] == pytest.approx(max(ent["q_g"], ent["q_s"]) * L * L / 8.0, abs=0.02)
    # o memorial da peça sai desse cálculo
    d = memorial_peca.documento(dict(r, parametros={"v0": 35.0}), "P10", didatico=True, obra="Teste")
    assert d["tipo"] == "terca" and "Hipóteses" in d["html"] and "details" in d["html"]
    assert memorial_peca.marca_sugerida(r) == "P10"


def test_inclinacao_ignora_o_joelho(modelo):                  # noqa: F811
    """O ângulo do telhado é o do banzo comprido: uma peça curta e quase vertical classificada
    como banzo superior (o joelho do canto quebrado) não entra na média."""
    from nucleo3d.calculo_ifc import _Tesoura
    doc, nomes = modelo
    g = calculo_ifc.geometria_do_modelo(doc, nomes)
    assert abs(g["inclinacao_graus"]) < 0.5

    class M:
        def __init__(self, a, b):
            self.a, self.b, self.tipo, self.posicao = a, b, "banzo", "superior"
    t = _Tesoura.__new__(_Tesoura)
    t.membros = [M((0.0, 0.0), (8000.0, 1600.0)), M((-300.0, -1100.0), (0.0, 0.0)), M((8000.0, 1600.0), (8300.0, 500.0))]
    t.theta = 0.0
    t._classificar_banzos()
    assert t.theta == pytest.approx(math.degrees(math.atan2(1600.0, 8000.0)), abs=0.01)


# ------------------------------------------------------------ o documento

def _calculo_sintetico():
    sec = cf.propriedades_u(150, 50, 2.28)
    r = cf.terca(sec, "CIVIL 300", vao=5.0, carga_gravidade=0.8, carga_succao=1.2, n_correntes=2, inclinacao=10.0,
                 elemento="M15 T.C.5 · terça · U 150×50×2,28 (FF)")
    v = dict(verificar.serializar_resultado(r), marca="M15", nome="T.C.5", tipo="terca")
    crit = r.critica
    el = {"nome": "T.C.5", "titulo": r.elemento, "tipo": "terca", "perfil": r.perfil, "material": r.material,
          "aproveitamento": round(r.razao, 3), "ok": r.ok, "governa": crit.titulo, "norma": crit.norma,
          "dimensionamento": {"vao_m": 5.0, "largura_m": 1.5, "correntes": 2}}
    return {"elementos": {"M15": el}, "verificacoes": [v], "parametros": {"v0": 40, "flecha_terca": 180}}


def test_documento_quatro_camadas():
    c = _calculo_sintetico()
    d = memorial_peca.documento(c, "M15", didatico=True, obra="Obra teste", quando="2026-09-25 10:00")
    h = d["html"]
    assert d["titulo"] == "Memorial de cálculo — terça M15 (T.C.5)"
    for cap in ("Resumo das terças", "Hipóteses", "Conta", "Para quem está aprendendo"):
        assert cap in h, cap
    assert h.count("<details") >= 12                      # uma explicação por hipótese e por verificação
    assert 'class="fonte modelo"' not in h                # a rotina sozinha não mede o modelo
    assert 'class="fonte rotina"' in h and 'class="fonte catalogo"' in h
    assert "Momento máximo, sucção" in h and "item 9.8.2.2" in h
    assert "Obra teste" in h and "versão didática" in h
    assert [m["marca"] for m in d["marcas"]] == ["M15"]


def test_documento_profissional_sem_camada_4():
    c = _calculo_sintetico()
    d = memorial_peca.documento(c, "M15", didatico=False)
    h = d["html"]
    assert "Para quem está aprendendo" not in h and "<details" not in h and 'class="dica"' not in h
    assert "versão profissional" in h
    assert "Hipóteses" in h and "Conta" in h


def test_documento_peca_inexistente():
    with pytest.raises(KeyError):
        memorial_peca.documento(_calculo_sintetico(), "P99")


def test_html_de_impressao():
    c = _calculo_sintetico()
    html = memorial_peca.montar_html_impressao(c, "M15", didatico=True, obra="Obra teste")
    assert html.startswith("<!DOCTYPE html>") and "<details class=\"explica\" open>" in html
    assert "paged" in html.lower()
