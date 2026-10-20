# -*- coding: utf-8 -*-
"""Identificação para modelagem (20/10/2026) — o servidor: a volta do 3D para a Montagem (Fase 6), a cota da viga de aço
apoiada pela face de baixo na volta do 3D, e a varredura do Hangar Almayer (o projeto de fabricação que o caminho antigo
enfileirou no 3D): a locação, a tesoura e as terças."""
import collections
import copy
import os

import pytest

from nucleo2d.desenho import Desenho, Linha
from nucleo3d import de_planta_estrutura as DPE
from nucleo3d.modelo import Barra

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
