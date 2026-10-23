# -*- coding: utf-8 -*-
"""Contravento × viga: as variantes por nó e o "trocar o tipo" (FERRAMENTA · LIGAÇÕES, 23/10/2026).

O pedido do usuário: o projeto do terceiro marca onde o X chega na viga mas não diz a ligação; "quero só clicar nas
ligações e mudar o tipo (castanha, duas chapas iguais à Sooro, cantoneira cortada…)". O nó é o do print
(Projeto/BRIEFINGS/imagens/ligacoes-contravento-2026-10-23.png): dois tirantes em V no mesmo ponto da viga."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import ErroDeDados  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402
from nucleo3d import ligacoes3d  # noqa: E402

VIGA = "W 310 X 32,7"            # d 313, bf 102, tf 10,8: a mesa de cima em z = 156,5
TOPO = 156.5
VARIANTES = ["castanha_contravento", "duas_chapas_contravento", "cantoneira_contravento"]


def _no():
    viga = Barra(nome="V1", inicio=(0, 0, 0), fim=(7200, 0, 0), perfil=VIGA, papel="viga")
    z = TOPO + 45.0
    t1 = Barra(nome="CV1", inicio=(0, -4300, z), fim=(3600, 0, z), perfil="FE RED 1/2''", papel="contraventamento")
    t2 = Barra(nome="CV2", inicio=(7200, -4300, z), fim=(3600, 0, z), perfil="FE RED 1/2''", papel="contraventamento")
    doc = Documento()
    for e in (viga, t1, t2):
        doc.add(e)
    return doc, viga, t1, t2


def _aplicar(doc, r):
    for i in r.get("remover", []):
        doc.entidades.pop(i, None)
    for i, campos in r.get("alterar", {}).items():
        if i in doc.entidades:
            for k, v in campos.items():
                setattr(doc.entidades[i], k, v)
    for e in Documento.de_dict({"entidades": r.get("novas", [])}).entidades.values():
        doc.add(e)


def _da_ligacao(doc, lid):
    return [e for e in doc.entidades.values() if ((e.atributos or {}).get("ligacao") or {}).get("id") == lid]


@pytest.mark.parametrize("tipo", VARIANTES)
def test_um_no_com_dois_tirantes_e_uma_ligacao_sem_colisao(tipo):
    from nucleo3d import conferencia_producao as CP
    from nucleo3d.producao import _proxy
    doc, viga, t1, t2 = _no()
    r = ligacoes3d.aplicar(doc, tipo, [t1.id, t2.id, viga.id])
    assert len(r["ligacoes"]) == 1
    _aplicar(doc, r)
    lid = r["ligacoes"][0]["id"]
    pecas = _da_ligacao(doc, lid)
    assert pecas and set(pecas[0].atributos["ligacao"]["pecas"]) == {t1.id, t2.id, viga.id}
    # só a ponta do nó andou; as de fora ficaram
    assert tuple(t1.inicio) == (0, -4300, TOPO + 45.0) and tuple(t2.inicio) == (7200, -4300, TOPO + 45.0)
    # as pontas afastadas ao longo da viga, cada uma para o lado de onde o tirante vem
    assert t2.fim[0] - t1.fim[0] > 80
    # nada atravessa a viga nem uma peça a outra (o parafuso e o furo passam, a barra roscada e o tirante nas chapas)
    solidos = [e for e in pecas if e.tipo in ("barra", "chapa") and "parafuso" not in (e.atributos or {})]
    col = CP.colisoes([_proxy(e) for e in [viga] + solidos])["achados"]
    assert col == [], col


def test_trocar_o_tipo_mantem_as_barras_e_apagar_devolve_o_tirante():
    doc, viga, t1, t2 = _no()
    antes = (tuple(t1.fim), tuple(t2.fim))
    r = ligacoes3d.aplicar(doc, "castanha_contravento", [t1.id, t2.id, viga.id])
    _aplicar(doc, r)
    lid = r["ligacoes"][0]["id"]
    n_castanha = len(_da_ligacao(doc, lid))
    for novo in ("duas_chapas_contravento", "cantoneira_contravento", "castanha_contravento"):
        r = ligacoes3d.aplicar(doc, novo, [], ligacao=lid)
        _aplicar(doc, r)
        pecas = _da_ligacao(doc, lid)
        assert pecas and all(e.atributos["ligacao"]["tipo"] == novo for e in pecas)
        assert set(pecas[0].atributos["ligacao"]["pecas"]) == {t1.id, t2.id, viga.id}
        # as peças do tipo de antes saíram: nenhuma peça de outra ligação ficou no nó
        outros = [e for e in doc.entidades.values() if (e.atributos or {}).get("ligacao") and e not in pecas]
        assert outros == []
        # os parâmetros do tipo antigo não passam para o novo
        assert "comprimento_toco" not in pecas[0].atributos["ligacao"]["parametros"] or novo == "duas_chapas_contravento"
    assert len(_da_ligacao(doc, lid)) == n_castanha
    # o "ajustes" guarda o tirante de antes de qualquer ligação: apagar devolve as pontas originais
    _aplicar(doc, ligacoes3d.remover(doc, lid))
    assert (tuple(t1.fim), tuple(t2.fim)) == antes
    assert not [e for e in doc.entidades.values() if (e.atributos or {}).get("ligacao")]


def test_nao_troca_por_tipo_de_outra_familia():
    doc, viga, t1, t2 = _no()
    r = ligacoes3d.aplicar(doc, "castanha_contravento", [t1.id, t2.id, viga.id])
    _aplicar(doc, r)
    with pytest.raises(ErroDeDados):
        ligacoes3d.aplicar(doc, "chapa_simples", [], ligacao=r["ligacoes"][0]["id"])


def test_varios_nos_numa_selecao_e_tirante_sozinho():
    """a seleção com a viga e os tirantes de dois nós dá duas ligações; o nó de um tirante só não afasta a ponta"""
    doc, viga, t1, t2 = _no()
    z = TOPO + 45.0
    t3 = Barra(nome="CV3", inicio=(1000, -4300, z), fim=(6500, 0, z), perfil="FE RED 1/2''", papel="contraventamento")
    doc.add(t3)
    r = ligacoes3d.aplicar(doc, "castanha_contravento", [t1.id, t2.id, t3.id, viga.id])
    assert len(r["ligacoes"]) == 2
    _aplicar(doc, r)
    assert abs(t3.fim[0] - 6500) < 150         # só o recuo da castanha ao longo do tirante, sem o afastamento
    assert {len(lg["barras"]) for lg in r["ligacoes"]} == {2, 3}


def test_trocar_varias_de_uma_vez_numa_resposta_so():
    """as ligações selecionadas trocadas juntas (um desfazer no editor); o documento recebido não muda"""
    import json
    doc, viga, t1, t2 = _no()
    z = TOPO + 45.0
    t3 = Barra(nome="CV3", inicio=(1000, -4300, z), fim=(6500, 0, z), perfil="FE RED 1/2''", papel="contraventamento")
    doc.add(t3)
    r = ligacoes3d.aplicar(doc, "castanha_contravento", [t1.id, t2.id, t3.id, viga.id])
    _aplicar(doc, r)
    lids = [lg["id"] for lg in r["ligacoes"]]
    velhas = {e.id for e in doc.entidades.values() if (e.atributos or {}).get("ligacao")}
    antes = json.dumps(doc.dict(), sort_keys=True, default=str)
    r2 = ligacoes3d.aplicar(doc, "duas_chapas_contravento", [], ligacao=lids)
    assert json.dumps(doc.dict(), sort_keys=True, default=str) == antes
    assert set(r2["remover"]) == velhas and len(r2["ligacoes"]) == 2
    _aplicar(doc, r2)
    for lid in lids:
        pecas = _da_ligacao(doc, lid)
        assert pecas and {e.atributos["ligacao"]["tipo"] for e in pecas} == {"duas_chapas_contravento"}
    assert not [e for e in doc.entidades.values() if (e.atributos or {}).get("ligacao", {}).get("tipo") == "castanha_contravento"]


def test_familia_na_lista_dos_tipos():
    tipos = {t["id"]: t for t in ligacoes3d.tipos()}
    for t in VARIANTES:
        assert tipos[t]["familia"] == "contravento"
    assert tipos["chapa_simples"]["familia"] is None
