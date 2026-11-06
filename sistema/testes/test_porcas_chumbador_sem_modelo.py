# -*- coding: utf-8 -*-
"""O chumbador sem porca no modelo leva o padrão da fábrica na lista, com aviso (FAB-05, reincidência — Hora Certa ·
Galpão Existente, 30/10, auditor N06).

O modelo montado das folhas do projetista não traz a porca que a folha desenha; com nenhuma porca modelada, o chumbador
não tinha "ponta roscada" e a lista saía sem porca nem arruela para os 218 chumbadores (Ø12, Ø36, ⅝"), no projeto
recebido E no nosso. Agora: 2 porcas + 1 arruela por perna e o aviso para conferir com a folha. O chumbador soldado na
chapa (sem `projecao_mm`) não muda.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest  # noqa: E402

from nucleo3d import geometria as geo  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402
from nucleo2d.detalhar import levantar  # noqa: E402


def _doc(origem, projecao=140.0, perfil="FE RED 5/8''", d=15.875):
    geo.registrar_perfil(geo.barra_redonda(d, perfil))
    doc = Documento(nome="chumbadores")
    doc.metadados = dict(getattr(doc, "metadados", None) or {}, origem_projeto=origem)
    at = {"tipo_ifc": "IfcMember", "elemento": "Chumbador", "funcao": "chumbador"}
    if projecao:
        at["projecao_mm"] = projecao
    for k in range(4):
        doc.add(Barra(nome="Chumbador", inicio=(k * 200.0, 0.0, projecao or 0.0), fim=(k * 200.0, 0.0, -600.0),
                      perfil=perfil, papel="chumbador", material="Aço", aco="ASTM A36", atributos=dict(at)))
    return doc


@pytest.mark.parametrize("origem", ["recebido", "nosso"])
def test_chumbador_sem_porca_leva_o_padrao_e_avisa(origem):
    r = levantar(_doc(origem), regra_tercas=False)
    ac = r["acessorios"]
    assert ac.get('Porca sextavada Ø5/8" UNC') == 8 and ac.get('Arruela lisa Ø5/8"') == 4, ac
    assert any("sem porca no modelo" in a for a in r.get("avisos") or []), r.get("avisos")


def test_chumbador_em_milimetro():
    r = levantar(_doc("recebido", perfil="BARRA REDONDA 36", d=36.0), regra_tercas=False)
    assert r["acessorios"].get("Porca sextavada M36") == 8


def test_chumbador_soldado_sem_projecao_nao_muda():
    r = levantar(_doc("recebido", projecao=None), regra_tercas=False)
    assert not any("orca" in k for k in r["acessorios"]), r["acessorios"]


def _compra_e_lista(doc):
    """A compra do resumo (porcas e arruelas soltas por bitola) e a lista de materiais do mesmo levantamento."""
    from saida.lista_producao import acessorios_da_lista
    from saida.resumos import _compra, _parafusos_com_local
    from nucleo2d.detalhe.base import _fixadores, _so_parafusos
    lev = levantar(doc, regra_tercas=False)
    parafusos = _parafusos_com_local(_so_parafusos(_fixadores(doc)), lev["pecas"], {}, {}, {}, {}, {})
    lista = {"acessorios": acessorios_da_lista(lev["acessorios"])}
    return _compra(lista, parafusos, {}, {}), lista, parafusos


@pytest.mark.parametrize("origem", ["recebido", "nosso"])
def test_a_compra_do_resumo_traz_as_porcas_do_chumbador_sem_porca(origem):
    """FAB-05, reincidência — SESI Chapecó, auditor N30 (02/11): a lista trazia 24 porcas + 12 arruelas Ø1/2" dos 12 CHU1
    (FE RED 1/2", sem porca no modelo) e a compra do resumo, nenhuma — ela refazia as porcas pelo modelo sem o padrão."""
    compra, _lista, _p = _compra_e_lista(_doc(origem))
    assert dict(compra["porcas"]).get('5/8"') == 8 and dict(compra["arruelas"]).get('5/8"') == 4, compra
    compra_m, _l, _p = _compra_e_lista(_doc(origem, perfil="BARRA REDONDA 36", d=36.0))
    assert dict(compra_m["porcas"]).get("M36") == 8 and dict(compra_m["arruelas"]).get("M36") == 4, compra_m


def test_a_conferencia_da_fab05_compara_a_compra_com_a_lista():
    from saida.resumos import conferir_porcas_da_compra
    _compra, lista, parafusos = _compra_e_lista(_doc("nosso"))
    assert conferir_porcas_da_compra(lista, parafusos) == []
    # a compra de antes da correção: sem as porcas soltas do chumbador
    avisos = conferir_porcas_da_compra(lista, [p for p in parafusos if p["parafuso"]])
    assert len(avisos) == 2 and all(a.startswith("FAB-05") for a in avisos), avisos
    assert any("0 porca(s) 5/8\"" in a and "lista de materiais 8" in a for a in avisos), avisos


def test_chumbador_sem_projecao_que_atravessa_a_placa_de_base_leva_o_padrao():
    """FAB-05, 3ª reincidência (Hora Certa · Galpão Novo, 06/11, "porque não está reconhecendo os acessórios"): o 3D montado
    por script põe os 1.106 chumbadores Ø36/Ø33 atravessando a placa de base de 31,8, rentes ao topo dela, SEM `projecao_mm` —
    e a lista saía sem porca nenhuma (ACESSÓRIOS 0). O chumbador que atravessa a placa deitada é chumbamento de pilar: leva o
    padrão (2 porcas + 1 arruela) com o aviso; o solto, sem placa, segue soldado (o teste acima)."""
    from nucleo3d.modelo import Chapa
    doc = _doc("nosso", projecao=None, perfil="Barra redonda ø 36 mm", d=36.0)
    for e in list(doc.entidades.values()):           # o chumbador do GN: do topo da placa (−220) para baixo
        e.inicio, e.fim = (e.inicio[0], 0.0, -220.0), (e.fim[0], 0.0, -1726.0)
    doc.add(Chapa(nome="Placa base 500×800×31,8", origem=(300.0, 0.0, -251.8), contorno=[(-400, -250), (400, -250), (400, 250), (-400, 250)],
                  espessura=31.8, material="Aço", atributos={"tipo_ifc": "IfcPlate", "funcao": "placa de base"}))
    r = levantar(doc, regra_tercas=False)
    assert r["acessorios"].get("Porca sextavada M36") == 8 and r["acessorios"].get("Arruela lisa M36") == 4, r["acessorios"]
    assert any("sem porca no modelo" in a for a in r.get("avisos") or [])
