# -*- coding: utf-8 -*-
"""Corrigir pelas regras (17/10): os modelos antigos (CD Bom Dia, Posto, PRATI, Docas) acusavam no Verificar apoios até
serem remontados — e remontar perde as edições do 3D. regras_trelica.corrigir_modelo passa o modelo como está pelas regras
e devolve as mudanças para o desfazer do editor; aplicadas num outro documento, conferir volta vazio."""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQUI = os.path.dirname(os.path.abspath(__file__))
for p in (RAIZ, AQUI):
    if p not in sys.path:
        sys.path.insert(0, p)

from nucleo3d import regras_trelica as R                                    # noqa: E402
from nucleo3d.modelo import Barra, Documento                                # noqa: E402
from test_regras_trelica import _tesoura_a_mao                              # noqa: E402


def _doc(dx=0.0, dz=0.0, origem_texto=False):
    doc = Documento()
    for b in _tesoura_a_mao(giro_banzo=90.0, giro_alma_u=180.0):
        b.inicio = (b.inicio[0] + dx, b.inicio[1], b.inicio[2] + dz)
        b.fim = (b.fim[0] + dx, b.fim[1], b.fim[2] + dz)
        b.atributos["marcas"] = {"posicao": "P%d" % (len(doc.entidades) + 1), "perfil": b.perfil}
        doc.add(b)
    if origem_texto:
        doc.add(Barra(nome="PILAR", inicio=(dx, 0, dz - 3000), fim=(dx, 0, dz), perfil="W 250×32,7", papel="pilar",
                      atributos={"origem": "PRATI CD - 09.10.2026.dxf"}))
    return doc


def _aplicar(doc, r):
    for i in r["remover"]:
        doc.entidades.pop(i, None)
    for i, campos in r["alterar"].items():
        for k, v in campos.items():
            setattr(doc.entidades[i], k, tuple(v) if k in ("inicio", "fim") else v)


@pytest.mark.parametrize("dx,dz,texto", [(0.0, 0.0, False), (-40000.0, 85000.0, True)])
def test_corrigir_o_modelo_como_esta(dx, dz, texto):
    doc = _doc(dx, dz, texto)
    assert R.conferir(list(doc.entidades.values()))                        # o modelo antigo acusa
    copia = Documento.de_dict(doc.dict())
    r = R.corrigir_modelo(copia)
    assert r["resumo"]["giradas"] > 0 and r["resumo"]["fora_depois"] == 0 and not r["avisos"]
    _aplicar(doc, r)                                                       # o que o editor faz com a resposta
    assert R.conferir(list(doc.entidades.values())) == []
    # a ponta que recebeu o perfil do banzo (1.4): peso refeito, marca a conferir, a troca registrada
    trocadas = [i for i, c in r["alterar"].items() if "perfil" in c]
    for i in trocadas:
        a = doc.entidades[i].atributos
        assert a["marcas"]["perfil"] == doc.entidades[i].perfil and a.get("marca_a_conferir")
        assert a["trocas_de_perfil"][-1]["como"] == "regras das tesouras"


def test_modelo_dentro_da_regra_nao_muda():
    doc = _doc()
    R.corrigir_modelo(doc)
    r = R.corrigir_modelo(Documento.de_dict(doc.dict()))
    assert not r["alterar"] and not r["remover"]


def test_rota():
    import app
    r = app.corrigir_pelas_regras({"documento": _doc().dict()})
    assert r["alterar"] and r["resumo"]["fora_depois"] == 0
