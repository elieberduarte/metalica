# -*- coding: utf-8 -*-
"""A saia da fábrica (a telha de fachada desce 150 mm abaixo da longarina mais baixa) só vale na telha com a ponta de
baixo livre.

Depósito Químico (ME Sooro, IFC do TecnoMETAL, conferência de telhas × compra de 26/10 e 04/11/2026): a platibanda tem
telha nas duas faces. A face de fora (4,95 → 6,50) desce até 150 mm abaixo da longarina de 4,995. A face de dentro
(5,62/5,67 → 6,50) nasce em cima da calha, e o oitão por dentro nasce em cima da telha da cobertura, com a ponta cortada
na inclinação. As duas faces ficam a 230 mm uma da outra, e a saia "fora a fora" (faces juntadas a até 400 mm) levava
as de dentro até 4,845, atravessando a cobertura: +775/+825 mm nas 68 internas e +812 a +1.514 mm nos 44 do oitão. A
lista dava 344,55 ml de fechamento (o certo ≈ 240) e 1.044,6 ml no total, acima dos 999,35 ml comprados.

Os dados são um recorte do modelo do Depósito (o canto das fachadas y = 21,7 e x = 0, com as telhas de fora, de dentro
e do oitão, a cobertura, a calha e as longarinas): testes/dados_telhas/deposito_quimico_canto.json.gz."""
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.detalhe import telhas as T                      # noqa: E402
from nucleo3d.modelo import Documento                         # noqa: E402

CANTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_telhas", "deposito_quimico_canto.json.gz")


def _pecas():
    with gzip.open(CANTO, "rt", encoding="utf-8") as f:
        doc = Documento.de_dict(json.load(f))
    return [e for e in doc.entidades.values() if getattr(e, "vertices", None)]


def _fachadas(pecas):
    """As telhas de fachada do recorte, separadas pelo lugar: fora (y 21,7 e x 0), dentro (y 21,45) e oitão (x 0,2)."""
    fora, dentro, oitao = [], [], []
    for e in pecas:
        if e.camada != "Telhas" or e.nome.endswith("0.65"):
            continue
        xs = [q[0] for q in e.vertices]
        ys = [q[1] for q in e.vertices]
        if min(ys) > 21600 or max(xs) < 150:
            fora.append(e)
        elif 21400 < min(ys) < 21500:
            dentro.append(e)
        elif 200 < min(xs) < 260:
            oitao.append(e)
    return fora, dentro, oitao


def test_face_de_fora_da_platibanda_desce_150_abaixo_da_longarina():
    pecas = _pecas()
    saias = T.saias_de_fachada(pecas)
    fora, _, _ = _fachadas(pecas)
    assert len(fora) == 9
    for e in fora:
        z0 = min(q[2] for q in e.vertices)
        assert round(z0) == 4950
        # y = 21,7: longarina C200 a 4.995 → ponta a 4.845 (+105); x = 0: C100 a 5.020 → 4.870 (+80)
        assert saias.get(e.id) in (105.0, 80.0), (e.id, saias.get(e.id))


def test_face_de_dentro_sobre_a_calha_nao_leva_saia():
    pecas = _pecas()
    saias = T.saias_de_fachada(pecas)
    _, dentro, _ = _fachadas(pecas)
    assert len(dentro) == 5
    assert [saias.get(e.id) for e in dentro] == [None] * 5


def test_oitao_por_dentro_sobre_a_telha_nao_leva_saia():
    pecas = _pecas()
    saias = T.saias_de_fachada(pecas)
    _, _, oitao = _fachadas(pecas)
    assert len(oitao) == 5
    assert [saias.get(e.id) for e in oitao] == [None] * 5


def test_ponta_livre_x_ponta_sobre_a_cobertura():
    """A conta da ponta: a de fora não encosta em nada (a cobertura começa 0,7 m acima); a de dentro encosta na calha."""
    pecas = _pecas()
    fora, dentro, oitao = _fachadas(pecas)
    cob = []
    for e in pecas:
        nome = str(T._marcas(e).get("perfil") or e.nome or "")
        if T._eh_funilaria(e, nome):
            cob.append(("caixa",) + T._caixa(e))
        elif e.camada == "Telhas" and e.nome.endswith("0.65"):
            c, eixos, _ = T._medidas(e)
            cob.append(("plano",) + T._caixa(e) + (c, T._norm(eixos[2])))
    assert not any(T._ponta_sobre_cobertura(e, cob) for e in fora)
    assert all(T._ponta_sobre_cobertura(e, cob) for e in dentro + oitao)
