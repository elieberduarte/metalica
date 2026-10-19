# -*- coding: utf-8 -*-
"""Reanalisar estrutura (19/10/2026): o modelo antigo pelas regras de hoje, sem remontar. O usuário mostrou no CD Bom Dia os
erros de concepção que os modelos novos já não têm — tocos soltos abaixo e acima da TF1, diagonais de 532 mm penduradas nos
nós, a diagonal da TC1 passando do banzo de baixo, montantes repetidos — e nenhuma conferência os corrigia sem remontar.

A tesoura de teste tem um defeito de cada; roda na origem, longe dela (as coordenadas do CD Bom Dia: x 222.913, y 251.770,
z +12.000) e com os banzos em cantoneira dupla (os eixos a 81 mm do plano da alma, como na TC1)."""
import math
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from nucleo3d import reanalise as RA                                       # noqa: E402
from nucleo3d.modelo import Barra, Documento                               # noqa: E402

PERFIL = "Ue 127×50×17×2,00"
SITUACOES = {
    "na origem": (0.0, 0.0, 0.0, False),
    "longe da origem (CD Bom Dia)": (222913.0, 251770.0, 12000.0, False),
    "banzo em cantoneira dupla": (222913.0, 251770.0, 12000.0, True),
}
SEM_TESOURAS = ["repetidas", "tocos", "pontas_soltas", "peso"]


def _tesoura(dx, dy, dz, dupla):
    """a tesoura plana em x = dx, de y = 0 a 12 m, 1,5 m de altura, painéis de 1,5 m, e os defeitos marcados pelo nome"""
    doc = Documento()

    def b(nome, papel, p0, p1, **kw):
        e = Barra(nome=nome, papel=papel, perfil=PERFIL,
                  inicio=(dx + p0[0], dy + p0[1], dz + p0[2]), fim=(dx + p1[0], dy + p1[1], dz + p1[2]), **kw)
        e.atributos.setdefault("conjunto", "T1")
        doc.add(e)
        return e

    for z, nome in ((0.0, "banzo inferior"), (1500.0, "banzo superior")):
        for lado in ((-81.0, 81.0) if dupla else (0.0,)):
            b("T1 %s" % nome, "banzo", (lado, 0, z), (lado, 12000, z))
    for i in range(9):
        b("T1 montante %d" % i, "montante", (0, 1500 * i, 0), (0, 1500 * i, 1500),
          atributos={"marcas": {"posicao": "M%d" % i}})
    for i in range(8):
        if i in (5, 7):
            continue                                       # o 5 tem a diagonal que passa do banzo; o 7, a do peso velho
        y0 = 1500 * i
        b("T1 diagonal %d" % i, "diagonal", (0, y0, 0), (0, y0 + 1500, 1500))
    # os defeitos do CD Bom Dia
    d = {}
    d["toco"] = b("T1 diagonal toco", "diagonal", (0, 3000, -300), (0, 3200, -480))            # 278 mm, não toca nada
    d["toco_acima"] = b("T1 diagonal toco acima", "diagonal", (0, 6100, 1700), (0, 6200, 2100))
    d["pendurada"] = b("T1 diagonal pendurada", "diagonal", (0, 4500, 0), (0, 4700, 450))      # do nó para o painel
    d["passa"] = b("T1 diagonal passa", "diagonal", (0, 7500, 1500), (0, 9450, -450))          # passa 636 mm do banzo
    d["sai"] = b("T1 diagonal sai do no", "diagonal", (0, 10500, 0), (0, 10200, -400))         # do nó para fora
    d["repetida"] = b("T1 montante 3", "montante", (0, 4500, 0), (0, 4500, 1500))              # sobre o montante 3
    d["bloqueada"] = b("T1 diagonal toco bloqueado", "diagonal", (0, 1000, -300), (0, 1200, -480), bloqueada=True)
    # o que NÃO é sobra: o montante da ponta descendo até o apoio que não está no modelo (o pilar de concreto)
    d["ponta"] = b("T1 montante de extremidade", "montante", (0, 12000, 0), (0, 12000, -800))
    b("P1", "pilar", (0, -6000, -4000), (0, -6000, -1000))   # o chão do modelo mais embaixo: o montante fica no ar
    d["peso"] = b("T1 diagonal 0 peso velho", "diagonal", (0, 10500, 0), (0, 12000, 1500), atributos={"peso_kg": 1.0})
    return doc, d


def _aplicar(doc, r):
    for i in r["remover"]:
        doc.entidades.pop(i, None)
    for i, campos in r["alterar"].items():
        for k, v in campos.items():
            setattr(doc.entidades[i], k, tuple(v) if k in ("inicio", "fim") else v)


def _regra(r, chave):
    return next(g for g in r["regras"] if g["chave"] == chave)


@pytest.mark.parametrize("situacao", list(SITUACOES))
def test_os_defeitos_do_cd_bom_dia_saem(situacao):
    dx, dy, dz, dupla = SITUACOES[situacao]
    doc, d = _tesoura(dx, dy, dz, dupla)
    copia = Documento.de_dict(doc.dict())
    r = RA.reanalisar(copia, quais=SEM_TESOURAS)
    sai = set(r["remover"])
    assert d["toco"].id in sai and d["toco_acima"].id in sai, "os tocos soltos saem"
    assert d["pendurada"].id in sai, "a diagonal pendurada no nó, com a ponta solta no painel, sai"
    assert d["sai"].id in sai, "a diagonal que sai do nó para fora da treliça sai"
    marcada = next(e for e in doc.entidades.values() if e.nome == "T1 montante 3" and e is not d["repetida"])
    assert d["repetida"].id in sai and marcada.id not in sai, "das duas repetidas, sai a sem marca"
    # a diagonal que passa do banzo é cortada no eixo dele (z do banzo de baixo, y 9.000)
    assert d["passa"].id in r["alterar"], "a diagonal que passava do banzo foi cortada"
    fim = r["alterar"][d["passa"].id]["fim"]
    assert math.dist(fim, (dx, dy + 9000.0, dz)) < 2.0, fim
    # o que não se toca
    assert d["bloqueada"].id not in sai and d["bloqueada"].id not in r["alterar"], "peça bloqueada não é tocada"
    assert d["ponta"].id not in sai, "o montante da ponta da treliça (apoio fora do modelo) fica"
    assert any(d["ponta"].id in a["ids"] for a in _regra(r, "pontas_a_conferir")["achados"]), "e vai para o a conferir"
    # o peso gravado pela regra de hoje
    assert d["peso"].id in r["alterar"] and r["alterar"][d["peso"].id]["atributos"]["peso_kg"] > 1.0
    # cada achado aponta as peças (a prévia clica nelas)
    for g in r["regras"]:
        for a in g["achados"]:
            assert a["ids"] and len(a["ponto"]) == 3


@pytest.mark.parametrize("situacao", list(SITUACOES))
def test_reanalisar_de_novo_nao_acha_mais_nada(situacao):
    """aplicada a reanálise, a segunda não corrige mais nada (as correções não criam defeitos novos)"""
    doc, _d = _tesoura(*SITUACOES[situacao])
    r = RA.reanalisar(Documento.de_dict(doc.dict()), quais=SEM_TESOURAS)
    _aplicar(doc, r)
    r2 = RA.reanalisar(Documento.de_dict(doc.dict()), quais=SEM_TESOURAS)
    assert not r2["remover"] and not r2["alterar"], (r2["remover"], list(r2["alterar"]))
    assert all(_regra(r2, k)["n"] == 0 for k in SEM_TESOURAS)


def test_regra_desmarcada_nao_muda_nada():
    doc, d = _tesoura(222913.0, 251770.0, 12000.0, False)
    r = RA.reanalisar(Documento.de_dict(doc.dict()), quais=["pontas_soltas"])
    sai = set(r["remover"])
    assert d["pendurada"].id in sai and d["sai"].id in sai
    assert d["toco"].id not in sai and d["repetida"].id not in sai, "os tocos e as repetidas ficam (regras desmarcadas)"
    assert _regra(r, "tocos")["n"] == 0 and _regra(r, "repetidas")["n"] == 0
    assert all(_regra(r, k)["tipo"] in ("corrige", "aponta") for k, *_ in RA.REGRAS)


def test_com_as_regras_das_tesouras_e_o_carimbo():
    """a reanálise inteira (com as regras de montagem das tesouras) tira os mesmos defeitos e devolve o carimbo da versão"""
    doc, d = _tesoura(222913.0, 251770.0, 12000.0, False)
    r = RA.reanalisar(Documento.de_dict(doc.dict()))
    sai = set(r["remover"])
    assert {d["toco"].id, d["pendurada"].id, d["sai"].id} <= sai
    assert r["carimbo"]["versao"] == RA.VERSAO_REGRAS
    assert RA.precisa({}) and not RA.precisa({"reanalise": r["carimbo"]})
