# -*- coding: utf-8 -*-
"""O detalhe do usuário (F14, 14/10/2026): a ligação montada no 3D salva como modelo, no sistema da ponta da barra de
referência, e aplicada de novo em outras barras — no lugar certo, com o corte da ponta, a solda, a marca e o conjunto."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import ErroDeDados  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402
from nucleo3d import detalhe_usuario as DU, ligacoes3d, producao  # noqa: E402

W = "W 310×38,7"


def _doc(*ents):
    d = Documento()
    for e in ents:
        d.add(e)
    return d


def _aplicar(doc, r):
    for i in r.get("remover", []):
        doc.entidades.pop(i, None)
    for i, campos in r.get("alterar", {}).items():
        for k, v in campos.items():
            setattr(doc.entidades[i], k, v)
    for e in Documento.de_dict({"entidades": r.get("novas", [])}).entidades.values():
        doc.add(e)


def _numerar(doc):
    for i, patch in producao.numerar(doc)["mudancas"].items():
        a = dict(doc.entidades[i].atributos or {})
        for k, v in patch.items():
            if v is None:
                a.pop(k, None)
            else:
                a[k] = v
        doc.entidades[i].atributos = a


def _modelo_com_chapa_de_topo():
    p1 = Barra(nome="p1", inicio=(0, 0, 0), fim=(0, 0, 4000), perfil=W, rotacao=90, papel="pilar")
    v1 = Barra(nome="v1", inicio=(0, 0, 3500), fim=(0, 6000, 3500), perfil=W, papel="viga")
    doc = _doc(p1, v1)
    r = ligacoes3d.aplicar(doc, "chapa_topo_joelho", [v1.id, p1.id])
    _aplicar(doc, r)
    # o detalhe "à mão": as peças viram peças soltas do modelo (sem o registro da ligação paramétrica)
    for e in doc.entidades.values():
        if (e.atributos or {}).get("ligacao"):
            e.atributos = {k: v for k, v in e.atributos.items() if k != "ligacao"}
    _numerar(doc)
    pecas = [e.id for e in doc.entidades.values() if e.id not in (p1.id, v1.id)]
    return doc, p1, v1, pecas


def test_salvar_e_aplicar_a_chapa_de_topo_numa_viga_girada():
    doc, p1, v1, pecas = _modelo_com_chapa_de_topo()
    defin = DU.montar(doc, pecas + [v1.id, p1.id], [p1.id, v1.id], "Chapa de topo W310")   # a ordem das referências não importa
    assert defin["n_refs"] == 2 and len(defin["pecas"]) == 9 and defin["ref"]["perfil"] == W
    assert defin["ref"]["cortes"] and defin["ref"]["soldas"]
    # um segundo pórtico girado 90° em planta: a viga chega na mesa do pilar ao longo de +x
    p2 = Barra(nome="p2", inicio=(20000, 0, 0), fim=(20000, 0, 4000), perfil=W, rotacao=0, papel="pilar")  # d em X
    v2 = Barra(nome="v2", inicio=(26000, 0, 3500), fim=(20000, 0, 3500), perfil=W, papel="viga")           # chega pelo fim
    doc.add(p2)
    doc.add(v2)
    import json
    antes = json.dumps(doc.dict(), sort_keys=True, default=str)
    r = DU.aplicar(doc, defin, [v2.id, p2.id])
    assert json.dumps(doc.dict(), sort_keys=True, default=str) == antes       # o recebido não muda
    _aplicar(doc, r)
    novas = [e for e in doc.entidades.values() if ((e.atributos or {}).get("detalhe_usuario") or {}).get("barra") == v2.id]
    chapa = next(e for e in novas if e.tipo == "chapa")
    assert len(novas) == 9
    assert abs(chapa.origem[0] - (20000 + 155)) < 0.01                  # encostada na mesa do pilar novo
    xs = [n_ for n_ in (abs(c["normal"][0]) for c in v2.cortes_fim)]
    assert v2.cortes_fim and xs[0] == pytest.approx(1.0) and abs(v2.cortes_fim[0]["ponto"][0] - (155 + 25.4)) < 0.01
    # a peça igual fica com a marca dela; o conjunto da viga nova é o mesmo M da primeira (mesma composição)
    original = next(e for e in doc.entidades.values() if e.tipo == "chapa" and e is not chapa)
    assert chapa.atributos["marcas"]["posicao"] == original.atributos["marcas"]["posicao"]
    assert v2.atributos["marcas"]["conjunto"] == v1.atributos["marcas"]["conjunto"]
    assert chapa.atributos["marcas"]["posicao"] in v2.atributos["soldas"]
    pars = [e for e in novas if e.tipo == "solido"]
    assert all(abs(abs(p.atributos["parafuso"]["eixo"][0]) - 1) < 1e-6 for p in pars)          # ao longo de X agora


def test_detalhe_de_base_vai_no_pe_do_pilar():
    p1 = Barra(inicio=(0, 0, 0), fim=(0, 0, 4000), perfil=W, rotacao=90, papel="pilar")
    doc = _doc(p1)
    _aplicar(doc, ligacoes3d.aplicar(doc, "placa_base_rotulada", [p1.id]))
    for e in doc.entidades.values():
        if (e.atributos or {}).get("ligacao"):
            e.atributos = {k: v for k, v in e.atributos.items() if k != "ligacao"}
    _numerar(doc)
    pecas = [e.id for e in doc.entidades.values() if e.id != p1.id]
    defin = DU.montar(doc, pecas, [p1.id], "Base rotulada W310")
    assert defin["ref"]["vertical"] and not defin["ref"]["ponta_alta"]
    p2 = Barra(inicio=(9000, 5000, 4000), fim=(9000, 5000, 200), perfil=W, rotacao=90, papel="pilar")   # desenhado de cima para baixo
    doc.add(p2)
    _aplicar(doc, DU.aplicar(doc, defin, [p2.id]))
    placa = next(e for e in doc.entidades.values() if e.tipo == "chapa" and abs(e.origem[0] - 9000) < 500)
    assert abs(placa.origem[2] - 200) < 0.01 and len(placa.furos) == 2           # no pé (z 200), não no topo
    assert p2.recorte_fim == pytest.approx(25.4)                                   # o pé do p2 é o fim


def test_biblioteca_grava_lista_e_exclui(tmp_path):
    doc, p1, v1, pecas = _modelo_com_chapa_de_topo()
    defin = DU.montar(doc, pecas, [v1.id, p1.id], "CT W310")
    DU.salvar(str(tmp_path), defin)
    assert [d["nome"] for d in DU.resumo(str(tmp_path))] == ["CT W310"]
    assert DU.obter(str(tmp_path), defin["id"])["pecas"]
    assert DU.excluir(str(tmp_path), defin["id"]) and DU.resumo(str(tmp_path)) == []


def test_recusa_sem_referencia_ou_sem_pecas():
    doc, p1, v1, pecas = _modelo_com_chapa_de_topo()
    with pytest.raises(ErroDeDados):
        DU.montar(doc, pecas, [], "x")
    with pytest.raises(ErroDeDados):
        DU.montar(doc, [v1.id], [v1.id], "x")
