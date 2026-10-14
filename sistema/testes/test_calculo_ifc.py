# -*- coding: utf-8 -*-
"""Cálculo do modelo importado: tesoura sintética de sólidos, terças e troca de perfil."""
import math
import os
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo3d import calculo_ifc                        # noqa: E402
from nucleo3d.modelo import Chapa, Documento, Solido    # noqa: E402


def _caixa(a, b, h=100.0, w=50.0, **marcas):
    """Sólido em caixa com o eixo de a a b (mm), altura h (z) e largura w."""
    d = [b[i] - a[i] for i in range(3)]
    L = math.sqrt(sum(x * x for x in d))
    d = [x / L for x in d]
    up = [0.0, 0.0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0.0, 0.0]
    n = [d[1] * up[2] - d[2] * up[1], d[2] * up[0] - d[0] * up[2], d[0] * up[1] - d[1] * up[0]]
    v = [n[1] * d[2] - n[2] * d[1], n[2] * d[0] - n[0] * d[2], n[0] * d[1] - n[1] * d[0]]
    verts = []
    for p in (a, b):
        for sv, sn in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(tuple(p[i] + v[i] * sv * h / 2 + n[i] * sn * w / 2 for i in range(3)))
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    s = Solido(nome=marcas.get("perfil", "U100X50X3.04"), camada="Vigas", vertices=verts, faces=faces)
    s.atributos = {"tipo_ifc": "IfcBeam", "marcas": marcas}
    return s


def _tesoura(doc, x, conj, vao=6000.0, altura=600.0, paineis=6, deitado=False):
    """Treliça Pratt no plano y·z, em x, banzos contínuos de a a b. Banzo U 100×50 em pé (a
    altura de 100 mm no plano, em z) ou `deitado` (os 100 mm na normal do plano, em x: o U com
    a boca para o miolo, a regra da casa)."""
    dx = vao / paineis
    inf = [(x, i * dx, 0.0) for i in range(paineis + 1)]
    sup = [(x, i * dx, altura) for i in range(paineis + 1)]
    h, w = (50.0, 100.0) if deitado else (100.0, 50.0)
    doc.add(_caixa(inf[0], inf[-1], h=h, w=w, posicao="P1", conjunto=conj, perfil="U100X50X3.04"))
    doc.add(_caixa(sup[0], sup[-1], h=h, w=w, posicao="P2", conjunto=conj, perfil="U100X50X3.04"))
    for i in range(paineis + 1):
        doc.add(_caixa(inf[i], sup[i], h=50, w=50, posicao="P3", conjunto=conj, perfil="L50X50X2.25"))
    for i in range(paineis):
        a, b = (inf[i], sup[i + 1]) if i < paineis // 2 else (sup[i], inf[i + 1])
        doc.add(_caixa(a, b, h=50, w=50, posicao="P4", conjunto=conj, perfil="L50X50X2.25"))
    return sup


def _modelo(deitado=False):
    doc = Documento(nome="teste")
    xs = [0.0, 3000.0, 6000.0]
    topos = [_tesoura(doc, x, "M%d" % (k + 1), deitado=deitado) for k, x in enumerate(xs)]
    # terças ao longo de x sobre cada nó do banzo superior, 100 mm acima do eixo
    for i, no in enumerate(topos[0]):
        a = (-300.0, no[1], no[2] + 100.0)
        b = (6300.0, no[1], no[2] + 100.0)
        doc.add(_caixa(a, b, h=150, w=75, posicao="P10", conjunto="", perfil="C150X75X20X2.25"))
    nomes = {"tipos": {"P10": "terca_cobertura"}, "tipos_conjuntos": {"M1 / M2 / M3": "tesoura"},
             "posicoes": {"P1": "B.1", "P2": "B.2", "P3": "B.3", "P4": "B.4", "P10": "T.C.1"},
             "conjuntos": {"M1 / M2 / M3": "T1"}, "ifc": {}, "ifc_conjuntos": {"M1": "T1", "M2": "T1", "M3": "T1"}}
    return doc, nomes


@pytest.fixture(scope="module")
def modelo():
    return _modelo()


@pytest.fixture(scope="module")
def modelo_deitado():
    """Os mesmos banzos U 100×50×3,04 deitados no plano da tesoura (boca para o miolo)."""
    return _modelo(deitado=True)


def test_geometria(modelo):
    doc, nomes = modelo
    g = calculo_ifc.geometria_do_modelo(doc, nomes)
    assert g["tesouras"] == 3 and g["vao_m"] == pytest.approx(6.0, abs=0.05)
    assert abs(g["inclinacao_graus"]) < 0.5


def test_calculo_completo(modelo):
    doc, nomes = modelo
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0, "sobrecarga": 0.25})
    assert r["ok"] and r["origem"] == "ifc"
    els = r["elementos"]
    assert {"P1", "P2", "P3", "P4", "P10"} <= set(els)
    assert els["P2"]["tipo"] == "banzo" and els["P2"]["posicao"] == "superior"
    assert els["P1"]["posicao"] == "inferior"
    assert els["P10"]["tipo"] == "terca" and els["P10"]["diagrama"]["vao_m"] == pytest.approx(3.0, abs=0.05)
    # o banzo superior comprime sob gravidade; a envoltória guarda o esforço
    assert els["P2"]["dimensionamento"]["N"] > 0
    assert 0 < els["P2"]["aproveitamento"] < 5
    assert els["P2"]["norma"].startswith("NBR 14762")
    assert els["P4"]["norma"].startswith("NBR 8800")
    # uma tesoura típica desenhada, com as barras em coordenadas reais (plano x = 0)
    assert r["portico"]["tesouras"][0]["nome"] == "T1"
    assert len(r["portico"]["barras"]) > 15
    assert all(abs(b["ini"][0] - b["fim"][0]) < 1e-6 for b in r["portico"]["barras"])
    assert r["servico"]["deslocamento"]["criterio"] == "L/250"
    assert r["combinacoes"][0]["chave"] == "envoltoria"
    assert any("banzo inferior" in v.get("dados", {}).get("observacao", "") for v in r["verificacoes"]
               if v["marca"] == "P1")
    assert r["resumo"]["tesouras"] == 3 and r["resumo"]["tercas"] == 1


# ------------------------------------------------------------------ ligações

def test_diagonal_soldada_no_banzo(modelo):
    """Sem chapa de nó no modelo, a ligação da diagonal é a solda dela no banzo — e ela
    entra na troca de perfil: a barra mais fina passa na barra e pode reprovar na solda."""
    doc, nomes = modelo
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0})
    ligs = r["ligacoes"]
    assert ligs, "nenhuma ligação verificada"
    assert {x["tipo"] for x in ligs} == {"soldada no banzo"}
    assert r["resumo"]["ligacoes"] == len(ligs)
    for x in ligs:
        assert x["chapa"] in ("P1", "P2") and x["barra"] in ("P3", "P4")
        assert x["sobreposicao_mm"] > 0 and x["perna_mm"] > 0
        assert 0 <= x["aproveitamento"] < 10
        assert x["ids"], "sem peças para selecionar no modelo"
        assert x["verificacoes"] and x["verificacoes"][0]["titulo"].startswith("Solda de filete")
    # o montante chega ao banzo a 90°: contato = altura do banzo (100 mm)
    mont = next(x for x in ligs if x["tipo_barra"] == "montante")
    assert mont["angulo_graus"] == pytest.approx(90.0, abs=1.0)
    assert mont["sobreposicao_mm"] == pytest.approx(100.0, abs=1.0)
    # a barra sabe da pior ligação dela, e a troca de perfil a reverifica
    el = r["elementos"]["P4"]
    assert el["ligacao"]["tipo"] == "soldada no banzo" and el["entrada"]["ligacao"]["comprimento_cm"] > 0
    a = calculo_ifc.alternativas(r, "P4", limite=8)
    assert a["ligacao"]["chave"] == el["ligacao"]["chave"]
    assert all(c["ligacao"] is not None for c in a["alternativas"])
    assert all(c["ok"] == (c["ok_barra"] and c["ligacao"]["ok"]) for c in a["alternativas"])


def _chapa_no_no(x, y, z, conj, marca="P20", esp=4.8, furos=None, lado=220.0):
    """Chapa de nó quadrada no plano y·z da tesoura, centrada no nó (x, y, z)."""
    ch = Chapa(nome="CH %g" % esp, camada="Chapas",
               origem=(x, y - lado / 2, z - lado / 2), eixo_x=(0.0, 1.0, 0.0), eixo_y=(0.0, 0.0, 1.0),
               contorno=[(0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)], espessura=esp, centrada=True,
               furos=list(furos or []), aco="ASTM A36")
    ch.atributos = {"tipo_ifc": "IfcPlate", "marcas": {"posicao": marca, "conjunto": conj}}
    return ch


@pytest.fixture(scope="module")
def modelo_com_chapas():
    """A mesma tesoura, com chapa de nó em todos os nós do banzo inferior; num deles a
    diagonal é parafusada (dois furos de 13,5 mm ao longo do eixo dela)."""
    doc = Documento(nome="chapas")
    vao, altura, paineis = 6000.0, 600.0, 6
    dx = vao / paineis
    for k, x in enumerate((0.0, 3000.0)):
        conj = "M%d" % (k + 1)
        _tesoura(doc, x, conj, vao, altura, paineis)
        for i in range(paineis + 1):
            furos = None
            if i == 1:
                # diagonal de inf[1] a sup[2]: direção (dx, altura) normalizada, furos a 60 e 120 mm
                L = math.hypot(dx, altura)
                d = (dx / L, altura / L)
                furos = [{"x": 110.0 + d[0] * s, "y": 110.0 + d[1] * s, "diametro": 13.5} for s in (60.0, 120.0)]
            doc.add(_chapa_no_no(x, i * dx, 0.0, conj, marca="P21" if i == 1 else "P20", furos=furos))
    nomes = {"tipos": {}, "tipos_conjuntos": {"M1 / M2": "tesoura"},
             "posicoes": {"P1": "B.1", "P2": "B.2", "P3": "B.3", "P4": "B.4", "P20": "CH.1", "P21": "CH.2"},
             "conjuntos": {"M1 / M2": "T1"}, "ifc": {}, "ifc_conjuntos": {"M1": "T1", "M2": "T1"}}
    return doc, nomes


def test_chapa_de_no_soldada_e_parafusada(modelo_com_chapas):
    doc, nomes = modelo_com_chapas
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0, "parafuso": "ASTM A307"})
    ligs = {x["chave"]: x for x in r["ligacoes"]}
    tipos = {x["tipo"] for x in r["ligacoes"]}
    assert "soldada" in tipos and "parafusada" in tipos, tipos
    # a chapa de nó com furos na faixa da diagonal: parafusada, M12 pelo furo de 13,5
    par = next(x for x in r["ligacoes"] if x["tipo"] == "parafusada")
    assert par["chapa"] == "P21" and par["barra"] == "P4"
    assert par["n_parafusos"] == 2 and par["diametro"] == "M12"
    assert par["espessura_mm"] == pytest.approx(4.8)
    titulos = [v["titulo"] for v in par["verificacoes"]]
    assert any("Whitmore" in t for t in titulos) and any("isalhamento" in t for t in titulos)
    # as chapas sem furo: soldada na chapa, com a sobreposição medida sobre a chapa
    sol = next(x for x in r["ligacoes"] if x["tipo"] == "soldada" and x["barra"] == "P4")
    assert sol["chapa"] == "P20" and 60.0 <= sol["sobreposicao_mm"] <= 230.0
    assert any(v["titulo"].startswith("Solda de filete") for v in sol["verificacoes"])
    # o banzo superior não tem chapa: ali a diagonal continua soldada no banzo
    assert any(x["tipo"] == "soldada no banzo" and x["chapa"] == "P2" for x in r["ligacoes"])
    # a chapa entra nas peças selecionáveis da ligação
    assert any(i.startswith("") for i in par["ids"]) and len(par["ids"]) >= 2
    assert ligs[par["chave"]]["nos"] >= 1


def test_alternativas_verificadas(modelo):
    doc, nomes = modelo
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0})
    assert r["resumo"]["peso_verificado_kg"] > 0
    el = r["elementos"]["P2"]
    assert el["comprimento_total_m"] > 0 and el["peso_kg"] > 0
    assert el["entrada"]["tipo"] == "barra"

    a = calculo_ifc.alternativas(r, "P2", limite=6)
    assert a["perfil"] == el["perfil"] and a["comprimento_total_m"] == el["comprimento_total_m"]
    assert a["alternativas"], "nenhum candidato no catálogo"
    for c in a["alternativas"]:
        assert c["nome"] != el["perfil"]
        assert c["aproveitamento"] > 0 and isinstance(c["ok"], bool)
        # o impacto no peso é a diferença por metro vezes o comprimento da posição
        assert c["delta_peso_kg"] == pytest.approx(c["delta_massa"] * a["comprimento_total_m"], abs=0.2)
    # quem passa vem antes de quem não passa
    ordem = [c["ok"] for c in a["alternativas"]]
    assert ordem == sorted(ordem, reverse=True)
    # e entre os que passam, do mais leve ao mais pesado
    passam = [c["massa"] for c in a["alternativas"] if c["ok"]]
    assert passam == sorted(passam)

    # a terça também tem alternativas, verificadas como terça
    at = calculo_ifc.alternativas(r, "P10", limite=4)
    assert at["alternativas"] and at["tipo"] == "terca"

    with pytest.raises(Exception):
        calculo_ifc.alternativas(r, "não existe")


def test_troca_de_perfil(modelo):
    doc, nomes = modelo
    base = calculo_ifc.calcular(doc, nomes, {"v0": 35.0})
    troca = calculo_ifc.calcular(doc, nomes, {"v0": 35.0, "trocas": {"P2": "U150X60X4.75"}})
    assert troca["elementos"]["P2"]["perfil"] == "U 150×60×4,75 (FF)"
    assert troca["elementos"]["P2"]["aproveitamento"] < base["elementos"]["P2"]["aproveitamento"]
    assert troca["resumo"]["trocas"] == {"P2": "U150X60X4.75"}


def test_sem_detalhamento():
    doc = Documento(nome="vazio")
    with pytest.raises(Exception):
        calculo_ifc.calcular(doc, {}, {})


# ------------------------------------------------ auditoria 30/09, leva 1 (C3, C4)

def test_terca_do_ifc_com_1_kN_e_grupo_do_s3(modelo):
    """C4 — a terça de cobertura do cálculo do IFC é verificada também com 1 kN no meio do
    vão (NBR 6120, 6.4); C3 — o grupo 2 gravado pela tabela de 1988 vira o grupo 3."""
    doc, nomes = modelo
    par = {"v0": 35.0, "grupo": 2}
    r = calculo_ifc.calcular(doc, nomes, par)
    assert par["grupo"] == 3 and par["norma_s3"] == "NBR 6123:2023"   # gravado no dicionário do app
    assert any("tabela de 1988" in a for a in r["avisos"])
    ent = r["elementos"]["P10"]["entrada"]
    assert ent["P_d"] == 1.5 and ent["g_d"] > 0
    # vão curto: o 1 kN governa; a verificação é a mesma na triagem de perfis
    from nucleo.perfis import banco
    ue = banco().candidatos("Ue")[0]
    w = banco().candidatos("I", "W")[0]
    for perfil in (ue, w):
        sem = calculo_ifc._verificar_terca_cobertura(perfil, "ASTM A36", 1.5, 0.3, 0.2, 0, 10.0,
                                                     0.2, 0.1, 180)
        com = calculo_ifc._verificar_terca_cobertura(perfil, "ASTM A36", 1.5, 0.3, 0.2, 0, 10.0,
                                                     0.2, 0.1, 180, P_d=1.5, g_d=0.2)
        assert com.razao > sem.razao, perfil.nome
        assert "carga_concentrada" in [h.chave for h in com.hipoteses]
    # a sobrecarga mínima da NBR 6120 no telhado plano (até 2 %: 0,50 kN/m²)
    assert calculo_ifc.cargas.sobrecarga_cobertura(1.5) == 0.50


# ------------------------------------------------ revisão 14/10: M1, M2, N1, N2

def _banzo_inferior(r):
    return r["elementos"]["P1"]


def test_m1_apoio_padrao_pino_e_rolete(modelo):
    """M1 — o padrão é um pino e um rolete: o banzo inferior da Pratt 6 m × 0,6 m sai com
    N = 20,59 kN (a sucção o comprime; antes, com os dois pinos por padrão, 5,41 kN)."""
    doc, nomes = modelo
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0, "sobrecarga": 0.25})
    assert calculo_ifc.PARAMETROS_PADRAO["apoio"] == "movel"
    assert r["resumo"]["apoio"] == "movel" and r["resumo"]["empuxo_apoios"] is None
    assert _banzo_inferior(r)["dimensionamento"]["N"] == pytest.approx(20.59, abs=0.01)
    assert _banzo_inferior(r)["aproveitamento"] == pytest.approx(3.005, abs=0.002)
    assert not any("empuxo" in a for a in r["avisos"])


def test_m1_rotulado_explicito_mostra_o_empuxo(modelo):
    """Os dois pinos só por escolha: o banzo inferior cai para 5,41 kN e o resultado diz que
    é o empuxo (16,95 kN na gravidade, reações iguais e opostas) que o alivia."""
    doc, nomes = modelo
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0, "sobrecarga": 0.25, "apoio": "rotulado"})
    el = _banzo_inferior(r)
    assert el["dimensionamento"]["N"] == pytest.approx(5.41, abs=0.01)
    emp = r["resumo"]["empuxo_apoios"]
    assert emp["H_kN"] == pytest.approx(16.95, abs=0.01) and emp["caso"] == "C1 gravidade"
    assert emp["reacoes_kN"][0] == pytest.approx(-emp["reacoes_kN"][1], abs=0.01)
    assert el["empuxo_kN"] == pytest.approx(16.95, abs=0.01)
    assert any("empuxo" in a and "16,95" in a and "banzo inferior" in a for a in r["avisos"])
    v = next(v for v in r["verificacoes"] if v["marca"] == "P1")
    assert any(h["chave"] == "apoio_empuxo" and "16,95" in h["texto"] for h in v["hipoteses"])
    assert "empuxo" in v["dados"]["observacao"]
    # o banzo superior não recebe o aviso
    assert r["elementos"]["P2"].get("empuxo_kN") is None


def _pipeline(doc, nomes, par=None):
    """As tesouras montadas e com o modelo de análise, sem calcular (para olhar a inércia)."""
    p = dict(calculo_ifc.PARAMETROS_PADRAO)
    p.update(par or {})
    avisos = []
    pecas, _t, _c, chapas = calculo_ifc._levantar_pecas(doc, nomes, p, avisos)
    tes = calculo_ifc._tesouras(pecas, nomes, chapas, avisos)
    calculo_ifc._definir_apoios(tes, pecas, p)
    for t in tes:
        calculo_ifc._montar_modelo(t)
    return tes


def test_m2_u_deitado_flete_no_eixo_fraco(modelo, modelo_deitado):
    """M2 — o U 100×50×3,04 deitado no plano da tesoura (boca para o miolo, a alma
    perpendicular ao plano): o pórtico plano usa I_y = 14,23 cm⁴ e a flexão é verificada em
    torno de y. O U em pé (alma no plano) continua com I_x = 89,49 cm⁴ e flexão em x."""
    for (doc, nomes), eixo, I_esp in ((modelo_deitado, "fraco", 14.233), (modelo, "forte", 89.485)):
        t = _pipeline(doc, nomes)[0]
        banzos = [k for k, b in enumerate(t.barras) if t.membros[b["membro"]].tipo == "banzo"]
        assert banzos and all(t.membros[t.barras[k]["membro"]].eixo == eixo for k in banzos)
        assert all(t.modelo.barras[k].I == pytest.approx(I_esp, rel=1e-4) for k in banzos)
        # cantoneira de abas iguais não tem lado: fica sem eixo
        assert all(t.membros[b["membro"]].eixo is None for b in t.barras if t.membros[b["membro"]].tipo != "banzo")

    r = calculo_ifc.calcular(modelo_deitado[0], modelo_deitado[1], {"v0": 35.0})
    for m in ("P1", "P2"):
        assert r["elementos"][m]["eixo_flexao"] == "y"
        assert r["elementos"][m]["entrada"]["eixo"] == "fraco"
    v = next(v for v in r["verificacoes"] if v["marca"] == "P2")
    assert v["hipoteses"][0]["chave"] == "eixo_flexao" and "I<sub>y</sub> = 14,2" in v["hipoteses"][0]["texto"]
    assert any(x["titulo"] == "Flexão em torno de y" for x in v["verificacoes"])
    assert not any("em torno de x" in x["titulo"] for x in v["verificacoes"])
    em_pe = calculo_ifc.calcular(modelo[0], modelo[1], {"v0": 35.0})
    assert em_pe["elementos"]["P2"]["eixo_flexao"] == "x"
    assert any("em torno de x" in x["titulo"] for x in
               next(v for v in em_pe["verificacoes"] if v["marca"] == "P2")["verificacoes"])
    # a troca de perfil (alternativas) verifica o candidato deitado do mesmo jeito
    a = calculo_ifc.alternativas(r, "P2", limite=3)
    assert a["alternativas"]


def test_m2_resistencias_do_u_deitado_contra_a_conta_a_mao():
    """U 100×50×3,04 CIVIL 300 (f_y = 30 kN/cm²), N_c = 5 kN, M = 20 kN·cm, painel de 100 cm no
    plano e 300 cm fora dele.

    Deitado — flexão em y (NBR 14762, 9.8.2, sem FLT): M_y = W_y·f_y = 3,943 × 30 = 118,3 kN·cm;
    σ_ℓ da mesa (AL, k = 0,43, b/t = 43,92/3,04) = 37,24 kN/cm² → M_ℓ = 37,24 × 3,943 =
    146,8 kN·cm; λ_ℓ = √(118,3/146,8) = 0,898 > 0,776 → M_Rℓ = (1 − 0,15·1,241^0,4)·1,241^0,4·118,3
    = 107,9 kN·cm; M_Rd = 107,9/1,10 = 98,08 kN·cm. A compressão flamba no plano em torno de y
    (100/1,570 = 63,7) e fora em torno de x (300/3,936 = 76,2): N_c,Rd = 42,98 kN.
    Em pé — flexão em x com FLT em L_b = 300 cm: M_Rd = 219,3 kN·cm; compressão com 300 cm em
    torno de y (191,1): N_c,Rd = 22,82 kN."""
    from nucleo import perfis_fabrica
    p = perfis_fabrica.perfil_de_fabrica("U100X50X3.04")
    r = calculo_ifc._verificar_barra_da_tesoura(p, "CIVIL 300", 5.0, 0.0, 20.0, 100.0, 300.0, 1, "x", [],
                                                eixo="fraco")
    rd = {v.titulo: v.Rd for v in r.verificacoes}
    assert rd["Flexão em torno de y"] == pytest.approx(98.08, abs=0.01)
    assert rd["Compressão centrada (MRD)"] == pytest.approx(42.98, abs=0.01)
    esb = next(v for v in r.verificacoes if v.titulo.startswith("Esbeltez"))
    assert esb.Sd == pytest.approx(300.0 / p.rx, rel=1e-6)
    assert r.dados["eixo_no_plano"] == "y"
    r2 = calculo_ifc._verificar_barra_da_tesoura(p, "CIVIL 300", 5.0, 0.0, 20.0, 100.0, 300.0, 1, "x", [],
                                                 eixo="forte")
    rd2 = {v.titulo: v.Rd for v in r2.verificacoes}
    assert rd2["Flexão em torno de x (MRD)"] == pytest.approx(219.33, abs=0.01)
    assert rd2["Compressão centrada (MRD)"] == pytest.approx(22.82, abs=0.01)
    assert r2.dados["eixo_no_plano"] == "x"
    # orientação não lida: os dois eixos, vale o pior (aqui o em pé, pela compressão)
    r3 = calculo_ifc._verificar_barra_da_tesoura(p, "CIVIL 300", 5.0, 0.0, 20.0, 100.0, 300.0, 1, "x", [],
                                                 eixo="indeterminado")
    assert r3.razao == pytest.approx(max(r.razao, r2.razao))
    assert r3.dados["eixo_indeterminado"] and r3.hipoteses[0].chave == "eixo_flexao"


def test_m2_barra_parametrica_pela_rotacao():
    """Barra do 2D → 3D: a orientação vem do `rotacao` (geometria.base_local, a altura da seção
    em v). Banzo horizontal no plano x·z com rotação 0 → alma vertical, no plano → eixo forte;
    rotação 90 → alma na normal do plano → eixo fraco."""
    from nucleo3d.modelo import Barra
    from nucleo import perfis_fabrica
    p = perfis_fabrica.perfil_de_fabrica("U100X50X3.04")
    w = (0.0, 1.0, 0.0)                     # normal do plano x·z
    for rot, esperado in ((0.0, "forte"), (90.0, "fraco")):
        b = Barra(nome="B", inicio=(0, 0, 0), fim=(6000, 0, 0), perfil="U100X50X3.04", papel="banzo", rotacao=rot)
        corpo = calculo_ifc._CorpoDaBarra(b, p)
        peca = calculo_ifc._Peca(corpo, "B1", "T1", b.perfil, p, "CIVIL 300", "", (b.inicio, b.fim))
        assert calculo_ifc._eixo_de_flexao_no_plano(peca, w) == esperado


def test_n2_pilar_em_cantoneira_pela_esbeltez_equivalente():
    """N2 — L 2"×1/4" A36, 150 cm: pela esbeltez equivalente (NBR 8800, E.1.4.2),
    L/r_x = 150/1,55 = 96,8 > 80 → (KL/r)_ef = 32 + 1,25 × 96,8 = 152,97; N_e = π²·20 000·6,05/152,97²
    = 51,0 kN; λ_0 = √(6,05 × 25/51,0) = 1,721; χ = 0,877/1,721² = 0,296; N_c,Rd = 0,296 × 6,05 × 25/1,10
    = 40,69 kN. Antes, pelos r_x/r_y geométricos sem flexo-torção: 83,9 kN."""
    from nucleo.perfis import perfil
    p = perfil('L 2" × 1/4"')
    r = calculo_ifc._verificar_pilar(p, "ASTM A36", 10.0, 0.0, 0.0, 150.0, 1.0, 150.0, "pilar", [])
    v = next(v for v in r.verificacoes if v.titulo.startswith("Compressão"))
    assert v.Rd == pytest.approx(40.69, abs=0.01)
    esb = next(v for v in r.verificacoes if v.titulo.startswith("Esbeltez"))
    assert esb.Sd == pytest.approx(152.97, abs=0.01)
    # com momento: conferência elástica, não "não verificada"
    rm = calculo_ifc._verificar_pilar(p, "ASTM A36", 10.0, 0.0, 5.0, 150.0, 1.0, 150.0, "pilar", [])
    assert not rm.indeterminada and any("cantoneira" in v.titulo for v in rm.verificacoes)


def _parafuso(centro, eixo, d=12.0, L=35.0, nome=None):
    """Sólido de parafuso (IfcMechanicalFastener) com o corpo de L ao longo de `eixo`."""
    s = _caixa(tuple(centro[i] - eixo[i] * L / 2 for i in range(3)),
               tuple(centro[i] + eixo[i] * L / 2 for i in range(3)), h=d, w=d)
    s.nome = nome or "BOLT %gx%g" % (d, L)
    s.camada = "Parafusos"
    s.atributos = {"tipo_ifc": "IfcMechanicalFastener"}
    return s


def _marcador(ponto, eixo, d, peca, parafuso=None):
    s = _caixa(tuple(ponto), tuple(ponto[i] + eixo[i] * 3.0 for i in range(3)), h=d, w=d)
    s.nome = "FURO"
    s.camada = "Furos"
    s.atributos = {"tipo_ifc": "IfcOpeningElement",
                   "furo": {"d": d, "ponto": list(ponto), "eixo": list(eixo), "profundidade": 3.0, "peca": peca,
                            "parafuso": parafuso}}
    return s


def test_n1_ct_pelos_parafusos_do_modelo():
    """N1 — os parafusos do modelo dão o l_c da ligação: na diagonal P4, dois M12 (sólidos do
    IFC, um deles também com o marcador de furo) a 60 mm → l_c = 6 cm, 2 na linha; no montante
    P3, três marcadores de furo Ø13,5 (parafuso M12 pelo furo-padrão d + 1,5) a 60 mm → l_c =
    12 cm, 3 na linha. O banzo fica sem (contínuo pelos nós: C_t adotado pelo núcleo)."""
    doc, nomes = _modelo()
    pecas = {e.id: e for e in doc.solidos}
    # a primeira diagonal da M1: de (0, 0, 0) a (0, 1000, 600)
    diag = next(e for e in pecas.values() if (e.atributos.get("marcas") or {}).get("posicao") == "P4"
                and (e.atributos["marcas"]["conjunto"] == "M1")
                and min(v[1] for v in e.vertices) < 50.0)
    L = math.hypot(1000.0, 600.0)
    dd = (0.0, 1000.0 / L, 600.0 / L)
    x_ = (1.0, 0.0, 0.0)
    pf = []
    for t_ in (150.0, 210.0):
        pf.append(_parafuso(tuple(dd[i] * t_ for i in range(3)), x_))
        doc.add(pf[-1])
    doc.add(_marcador(tuple(dd[i] * 210.0 - x_[i] * 25.0 for i in range(3)), x_, 13.5, diag.id, parafuso=pf[-1].id))
    # o montante do meio da M1 (em y = 3000): só marcadores de furo
    mont = next(e for e in pecas.values() if (e.atributos.get("marcas") or {}).get("posicao") == "P3"
                and e.atributos["marcas"]["conjunto"] == "M1"
                and abs(sum(v[1] for v in e.vertices) / len(e.vertices) - 3000.0) < 1.0)
    for z in (100.0, 160.0, 220.0):
        doc.add(_marcador((-25.0, 3000.0, z), x_, 13.5, mont.id))
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0})
    lig4 = r["elementos"]["P4"]["entrada"]["ligacao_ct"]
    assert lig4["lc"] == pytest.approx(6.0, abs=0.01) and lig4["n_parafusos"] == 2
    assert lig4["d_parafuso"] == pytest.approx(1.2) and lig4["soldada"] is False
    assert "parafusos do modelo 3D" in lig4["fonte"]
    lig3 = r["elementos"]["P3"]["entrada"]["ligacao_ct"]
    assert lig3["lc"] == pytest.approx(12.0, abs=0.01) and lig3["n_parafusos"] == 3
    assert lig3["d_parafuso"] == pytest.approx(1.2)
    assert r["elementos"]["P1"]["entrada"]["ligacao_ct"] is None
    assert r["elementos"]["P2"]["entrada"]["ligacao_ct"] is None
    # sem parafuso no modelo, nenhuma ligação medida
    limpo = calculo_ifc.calcular(*_modelo(), {"v0": 35.0})
    assert all(el["entrada"].get("ligacao_ct") is None for el in limpo["elementos"].values()
               if el["entrada"].get("tipo") == "barra")


def test_n1_banzo_continuo_ruptura_so_na_ponta(modelo):
    """Contrato do C_t (14/10): a ruptura da seção líquida só vale com a ponta ligada. O banzo
    inferior da Pratt é uma peça contínua de apoio a apoio: a maior tração (20,59 kN) está num
    trecho corrido, verificado com `ponta_ligada = False` (só o escoamento da seção bruta); a
    ruptura entra à parte, com a tração dos trechos que tocam a ponta/apoio (11,36 kN)."""
    doc, nomes = modelo
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0})
    ent = r["elementos"]["P1"]["entrada"]
    assert ent["Nt"] == pytest.approx(20.587, abs=0.01) and ent["Nt_ponta"] == pytest.approx(11.363, abs=0.01)
    v = next(v for v in r["verificacoes"] if v["marca"] == "P1")
    assert v["dados"]["ponta_ligada"] is False
    rup = [x for x in v["verificacoes"] if "ruptura" in x["titulo"].lower()]
    assert len(rup) == 1 and rup[0]["titulo"].endswith("trecho da ponta do banzo")
    assert rup[0]["Sd"] == pytest.approx(11.363, abs=0.01)
    esc = next(x for x in v["verificacoes"] if x["titulo"].startswith("Tração — escoamento"))
    assert esc["Sd"] == pytest.approx(20.587, abs=0.01)
    # diagonal e montante: barra de ponta ligada, sem a separação
    assert r["elementos"]["P4"]["entrada"]["Nt_ponta"] is None
