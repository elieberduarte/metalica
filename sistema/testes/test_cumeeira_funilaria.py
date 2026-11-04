# -*- coding: utf-8 -*-
"""A cumeeira de telha que o modelo traz como uma barra de funilaria corrida vira a cumeeira CU, com o detalhe.

Depósito Químico (ME Sooro, IFC do TecnoMETAL, 04/11/2026 — o usuário: "Não tem o detalhe da cumeeira"): o TecnoMETAL
grava a cumeeira como uma barra só, "CUMEEIRA I7.5" (camada Rufos, 33,31 m, a seção de uma chapa lisa com 250 mm de
cada lado da crista). O detalhamento a tratava como o rufo RF2 (1 × 33.310 mm, prancha dos rufos) e não havia o quadro
CUMEEIRAS. A compra é "Cumeeira TP40 — 34 peças": uma por telha da água, dobrada na cumeeira, como a da Sala de
Compressores (CU1, pernas 300 + 300).

Os dados são um recorte do modelo do Depósito: a barra da cumeeira inteira e as telhas das duas águas (7,5 % e 7,11 %)
dos primeiros 4,2 m — testes/dados_telhas/deposito_quimico_cumeeira.json.gz."""
import copy
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.detalhe import telhas as T                      # noqa: E402
from nucleo3d.modelo import Documento                         # noqa: E402

RECORTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_telhas", "deposito_quimico_cumeeira.json.gz")


def _bruto():
    with gzip.open(RECORTE, "rt", encoding="utf-8") as f:
        return json.load(f)


def _pecas(bruto=None):
    doc = Documento.de_dict(bruto if bruto is not None else _bruto())
    return [e for e in doc.entidades.values() if getattr(e, "vertices", None)]


def _telhas_por_agua(pecas):
    tl = [e for e in pecas if e.nome.endswith("0.65")]
    meio = sum(q[1] for e in pecas if e.nome.startswith("CUMEEIRA") for q in e.vertices) / 20.0
    lados = [sum(1 for e in tl if (min(q[1] for q in e.vertices) < meio) == lado) for lado in (True, False)]
    return lados


def test_barra_de_funilaria_vira_a_cumeeira_cu():
    pecas = _pecas()
    md = T.multidobras(pecas)
    cms = [c for c in md["cumeeiras"] if c.get("de_funilaria")]
    assert len(cms) == 1, md["cumeeiras"]
    cm = cms[0]
    assert cm["conjunto"] == "CUMEEIRA I7.5"
    # uma por telha da água (no modelo inteiro, 34: a compra)
    assert cm["instancias"] == max(_telhas_por_agua(pecas))
    # as pernas modeladas (250, da crista até cada ponta) vão no padrão da fábrica: 300
    assert (cm["perna1"], cm["perna2"]) == (300.0, 300.0)
    assert cm["pernas_modelo"] == [250.0, 250.0]
    # a dobra pelas águas de baixo: 180 − (4,29° + 4,07°)
    assert abs(cm["angulo"] - 171.6) < 0.15
    assert cm["perfil"] == "TELHA TP40 ESP.0.65"
    assert 3.5 < cm["peso"] < 4.1
    # a barra sai dos rufos (a lista e as pranchas a tiram pelo md["funilaria"])
    assert md["funilaria"] == {"CUMEEIRA I7.5"}
    assert "CUMEEIRA I7.5" in md["posicoes"]


def test_desenho_da_cumeeira_de_funilaria():
    from nucleo2d.desenho import Desenho
    cm = next(c for c in T.multidobras(_pecas())["cumeeiras"] if c.get("de_funilaria"))
    d = Desenho(nome="t", escala=20.0)
    T.desenho_da_cumeeira(cm, d, 0.0, 0.0, "CU1")
    ents = list(d.entidades.values()) if isinstance(d.entidades, dict) else list(d.entidades)
    textos = [getattr(e, "texto", "") or "" for e in ents]
    assert any(t.startswith("CU1 – %02dx" % cm["instancias"]) for t in textos), textos
    assert any("pernas 300 + 300 mm" in t for t in textos), textos


def _so_cumeeira(bruto, **mudar):
    b = copy.deepcopy(bruto)
    for e in b["entidades"]:
        if str(e.get("nome") or "").startswith("CUMEEIRA"):
            for k, v in mudar.items():
                if k == "atributos":
                    e.setdefault("atributos", {}).update(v)
                else:
                    e[k] = v
    return b


def test_chapa_lisa_lancada_ou_fora_dos_rufos_continua_rufo():
    bruto = _bruto()
    # a cumeeira de chapa lisa (o SESI: "Cumeeira (chapa galv. #0,50, dev. 600)") é rufo de verdade
    b = _so_cumeeira(bruto, nome="Cumeeira (chapa galv. #0,50, dev. 600)",
                     atributos={"marcas": {"perfil": "Cumeeira (chapa galv. #0,50, dev. 600)"}})
    assert not T.cumeeiras_de_funilaria(_pecas(b))["cumeeiras"]
    # a lançada pelo sistema tem a regra dela
    b = _so_cumeeira(bruto, atributos={"cumeeira_lancada": True})
    assert not T.cumeeiras_de_funilaria(_pecas(b))["cumeeiras"]
    # fora da camada Rufos (a do arquitetônico, a do Tekla na camada das telhas) fica como está
    b = _so_cumeeira(bruto, camada="ARQ — Cobertura e instalações")
    assert not T.cumeeiras_de_funilaria(_pecas(b))["cumeeiras"]


def test_sem_telha_das_duas_aguas_nao_e_cumeeira():
    bruto = _bruto()
    meio = None
    for e in bruto["entidades"]:
        if str(e.get("nome") or "").startswith("CUMEEIRA"):
            vs = e["vertices"] if not isinstance(e["vertices"], str) else json.loads(e["vertices"])
            meio = sum(q[1] for q in vs) / len(vs)
    b = copy.deepcopy(bruto)

    def _y(e):
        vs = e["vertices"] if not isinstance(e["vertices"], str) else json.loads(e["vertices"])
        return min(q[1] for q in vs)
    b["entidades"] = [e for e in b["entidades"] if str(e.get("nome") or "").startswith("CUMEEIRA") or _y(e) < meio]
    assert not T.cumeeiras_de_funilaria(_pecas(b))["cumeeiras"]
