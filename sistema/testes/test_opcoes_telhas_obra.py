# -*- coding: utf-8 -*-
"""A saia da telha de fachada e a chapa da cumeeira são decisões por obra (opções do projeto), sem mudar o padrão.

Depósito Químico (ME Sooro, 12/11/2026): o usuário pediu a relação de fabricação das telhas e decidiu, para esta obra,
o fechamento externo com 1,55 m, como o projetista, sem a saia de 150 mm da fábrica, e a cumeeira com 50 cm
desenvolvidos (250 + 250). Depois: "Os projetos 2D não tiveram as telhas atualizadas". O 2D saía pelo padrão, com
TL1 93 × 1.655 (com a saia) e CU1 300 + 300 = 600, diferente da relação. A Sala de Compressores decidiu o contrário
(com saia). REGRAS N.4: opção por projeto, sem mudar a COB-20 nem o PERNAS_CUMEEIRA.

Os dados são os recortes do modelo do Depósito: a cumeeira com as telhas das duas águas
(dados_telhas/deposito_quimico_cumeeira.json.gz) e o canto das fachadas (dados_telhas/deposito_quimico_canto.json.gz)."""
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.detalhe import telhas as T                      # noqa: E402
from nucleo3d.modelo import Documento                         # noqa: E402

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_telhas")


def _doc(nome):
    with gzip.open(os.path.join(DADOS, nome), "rt", encoding="utf-8") as f:
        return Documento.de_dict(json.load(f))


def _pecas(doc):
    return [e for e in doc.entidades.values() if getattr(e, "vertices", None)]


def _cumeeira(md):
    return next(c for c in md["cumeeiras"] if c.get("de_funilaria"))


def test_cumeeira_padrao_e_a_da_obra():
    pecas = _pecas(_doc("deposito_quimico_cumeeira.json.gz"))
    padrao = _cumeeira(T.multidobras(pecas))
    assert (padrao["perna1"], padrao["perna2"], padrao["desenv"]) == (300.0, 300.0, 600.0)
    obra = _cumeeira(T.multidobras(pecas, 500))
    assert (obra["perna1"], obra["perna2"], obra["desenv"]) == (250.0, 250.0, 500.0)
    assert obra["angulo"] == padrao["angulo"]
    # o peso acompanha a chapa: 500/600
    assert abs(obra["peso"] / padrao["peso"] - 500.0 / 600.0) < 0.01
    # o padrão do catálogo não muda
    assert T.PERNAS_CUMEEIRA == (300.0, 500.0)


def test_desenho_e_lista_com_a_cumeeira_da_obra():
    from nucleo2d.desenho import Desenho
    from nucleo2d.detalhar import detalhar
    from nucleo2d.detalhe.base import _categoria
    from saida import lista_producao
    doc = _doc("deposito_quimico_cumeeira.json.gz")
    cm = _cumeeira(T.multidobras(_pecas(doc), 500))
    d = Desenho(nome="t", escala=20.0)
    T.desenho_da_cumeeira(cm, d, 0.0, 0.0, "CU1")
    ents = list(d.entidades.values()) if isinstance(d.entidades, dict) else list(d.entidades)
    assert any("pernas 250 + 250 mm" in (getattr(e, "texto", "") or "") for e in ents)
    r = detalhar(doc, grupos=["localizacao"], converter=False)
    cat = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    for opcao, comp in ((None, 600), (500.0, 500)):
        lista = lista_producao.montar(r["objetos_posicoes"], cat, r["acessorios"], pecas=r["objetos_pecas"],
                                      cumeeira_desenvolvida=opcao)
        cu = [li for li in lista["posicoes"] if li.get("classe") == "Cumeeira"]
        assert len(cu) == 1 and cu[0]["comprimento"] == comp, (opcao, cu)


def test_saia_da_fabrica_desligada_na_obra():
    from nucleo2d.detalhar import levantar
    doc = _doc("deposito_quimico_canto.json.gz")
    com = levantar(doc, regra_tercas=False)
    assert com["saias"], "o padrão leva a saia nas telhas de fora da platibanda"
    assert any(getattr(p, "saia", 0.0) for p in com["posicoes"] if p.classe == "telha")
    doc = _doc("deposito_quimico_canto.json.gz")
    doc.metadados["saia_telha"] = False
    sem = levantar(doc, regra_tercas=False)
    assert sem["saias"] == {}
    assert not any(getattr(p, "saia", 0.0) for p in sem["posicoes"] if p.classe == "telha")
