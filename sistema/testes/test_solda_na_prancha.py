# -*- coding: utf-8 -*-
"""O símbolo de solda na prancha é anotação, como a chamada (Sooro, T1 da Sala, 09/11: "não estou conseguindo apagar esse
detalhe da solda"): na tela a trava da peça gerada deixa apagar e mover (verif_trava_pecas, passo 5); aqui, o lado do
servidor — o símbolo apagado dentro da célula continua apagado na próxima montagem, e o copiado para outro lugar fica
como desenho do usuário (antes saía como "peça gerada solta" e sumia na remontagem). Perto do zero e em UTM."""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Linha, Polilinha, Texto, transladar      # noqa: E402
from nucleo2d.detalhe.base import simbolo_solda, _Papel                        # noqa: E402
from nucleo2d import ajustes_pranchas as AP                                    # noqa: E402

SITUACOES = [(0.0, 0.0), (1218181.0, 211836.0)]
CEL = "tesouras|conjunto:M2 + M2"


def _prancha(ox, oy, geracao):
    """A célula da T1 como a montagem deixa: o banzo (peça) e o símbolo de solda acima da cumeeira, todos com a marca
    do conjunto (detalhe/conjunto, como o gerador grava) e a célula."""
    d = Desenho(nome="Pranchas", escala=1.0)
    d.metadados["geracao"] = geracao
    at = {"cel": CEL, "fonte": "tesouras", "prancha_numero": 1, "detalhe": "conjunto", "conjunto": "M2 + M2", "nome": "T1"}
    x0, y0 = ox + 100.0, oy + 100.0
    d.add(Linha(camada="BANZOS", a=(x0, y0), b=(x0 + 300.0, y0 + 40.0), atributos=dict(at)))
    d.add(Linha(camada="BANZOS", a=(x0 + 300.0, y0 + 40.0), b=(x0 + 600.0, y0), atributos=dict(at)))
    d.add(Texto(camada="TEXTO", posicao=(x0, y0 - 30.0), texto="T1 – 03x", altura=3.5, atributos=dict(at)))
    simbolo_solda(_Papel(d, dict(at)), 1.0, x0 + 300.0, y0 + 40.0, x0 + 312.0, y0 + 60.0, 3.0, ambos_lados=True)
    d.metadados["pranchas"] = [{"numero": 1, "celulas": [{"titulo": CEL, "id": CEL, "caixa": [x0, y0 - 40.0, x0 + 600.0, y0 + 90.0]}]}]
    return d


def _solda(d):
    return [e for e in d.entidades.values() if e.camada == "SOLDA"]


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_simbolo_apagado_continua_apagado(ox, oy):
    g1 = _prancha(ox, oy, "g1")
    imp1 = AP.marcar(g1)
    assert _solda(g1) and all((e.atributos or {}).get("cel") == CEL for e in _solda(g1))
    ed = Desenho.de_dict(copy.deepcopy(g1.dict()))
    for e in _solda(ed):
        ed.entidades.pop(e.id)
    aj = AP.aprender(ed, {"impressoes": {"g1": imp1}})
    g2 = _prancha(ox, oy, "g2")
    AP.marcar(g2)
    AP.aplicar(g2, aj)
    assert not _solda(g2)
    assert len([e for e in g2.entidades.values() if e.camada == "BANZOS"]) == 2          # a peça fica


@pytest.mark.parametrize("ox,oy", SITUACOES)
def test_simbolo_copiado_fica_como_desenho_do_usuario(ox, oy):
    """copiado (Ctrl+C/Ctrl+V) para outro nó da tesoura: a cópia perde a célula e guarda a marca do conjunto"""
    g1 = _prancha(ox, oy, "g1")
    imp1 = AP.marcar(g1)
    ed = Desenho.de_dict(copy.deepcopy(g1.dict()))
    for i, e in enumerate(_solda(g1)):
        c = transladar(copy.deepcopy(e), 200.0, 0.0)
        c.id = "copia%d" % i
        c.atributos = {k: v for k, v in (c.atributos or {}).items() if k not in ("cel", "g", "prancha_numero", "fonte")}
        ed.add(c)
    aj = AP.aprender(ed, {"impressoes": {"g1": imp1}})
    guardadas = list(Desenho.de_dict(aj["a_mao"]).entidades.values())
    assert len(guardadas) == len(_solda(g1)) and all(e.camada == "SOLDA" for e in guardadas)
    g2 = _prancha(ox, oy, "g2")
    AP.marcar(g2)
    rel = AP.aplicar(g2, aj)
    assert rel["a_mao"] == len(_solda(g1)) and not rel.get("pecas_soltas")
    assert len(_solda(g2)) == 2 * len(_solda(g1))


def test_a_peca_solta_continua_fora():
    """a geometria da peça (o banzo) copiada solta continua não voltando (02/10)"""
    solto = Polilinha(camada="BANZOS", vertices=[(0.0, 0.0), (5.0, 0.0)], atributos={"detalhe": "conjunto", "conjunto": "M2 + M2"})
    assert AP._peca_solta(solto.atributos, solto)
    solda = Linha(camada="SOLDA", a=(0.0, 0.0), b=(5.0, 0.0), atributos={"detalhe": "conjunto", "conjunto": "M2 + M2"})
    assert not AP._peca_solta(solda.atributos, solda)
