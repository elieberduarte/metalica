# -*- coding: utf-8 -*-
"""A prancha é uma fotografia do projeto (usuário, 13/11, Sooro Sala: "não consigo editar/movimentar uma representação nas
pranchas … o que poderíamos fazer para nas pranchas não ter esse vínculo tão direto com o desenho, a prancha seria uma
fotografia do projeto"; escolhido: livre nas pranchas, com um aviso na 1ª vez; nos desenhos de detalhamento a trava
continua). Para nada se perder na próxima montagem, a remontagem guarda também a FORMA mexida à mão — a linha esticada,
o canto recortado, a moldura puxada —, além do que já guardava (movida, apagada, texto trocado, desenhado à mão)."""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, transladar                              # noqa: E402
from nucleo2d import ajustes_pranchas as AP                                   # noqa: E402
from test_ajustes_pranchas import _gerado, _por                               # noqa: E402

A, B = "tesouras|conjunto:M1", "chaparias|posicao:P5"


def test_linha_esticada_volta_na_remontagem():
    g1 = _gerado("g1")
    imp1 = AP.marcar(g1)
    ed = Desenho.de_dict(copy.deepcopy(g1.dict()))
    # na célula A, a linha de baixo esticada 30 mm para a direita (a ponta b andou; a ponta a, a referência, ficou)
    lin = [e for e in _por(ed, A, "linha") if e.a[1] == e.b[1] == 100.0][0]
    lin.b = (lin.b[0] + 30.0, lin.b[1])
    # na célula B, a célula movida e a linha de pé encurtada
    for e in _por(ed, B):
        ed.entidades[e.id] = transladar(e, 10.0, 5.0)
    pe = [e for e in _por(ed, B, "linha") if e.a[0] == e.b[0]][0]
    pe.b = (pe.b[0], pe.b[1] - 8.0)
    aj = AP.aprender(ed, {"impressoes": {"g1": imp1}})
    formas = {c: [k for k, v in (x.get("ents") or {}).items() if "forma" in v] for c, x in aj["celulas"].items()}
    assert len(formas.get(A) or []) == 1 and len(formas.get(B) or []) == 1, formas
    assert not any("montada de outro jeito" in x["ajuste"] for x in aj["diario"])
    g2 = _gerado("g2")
    AP.marcar(g2)
    rel = AP.aplicar(g2, aj)
    assert rel.get("formas") == 2, rel
    la = [e for e in _por(g2, A, "linha") if e.a[1] == e.b[1] == 100.0]
    assert la and max(max(e.a[0], e.b[0]) for e in la) == 230.0                 # 100 + 100 + 30
    lb = [e for e in _por(g2, B, "linha") if e.a[0] == e.b[0]]
    assert lb and lb[0].a == (310.0, 105.0) and lb[0].b == (310.0, 117.0)       # movida (10, 5) e 8 mm mais curta
    # a entidade trocada continua da célula (a próxima gravação a reconhece de novo)
    assert all((e.atributos or {}).get("cel") and (e.atributos or {}).get("g") for e in la + lb)


def test_so_movida_nao_vira_forma():
    """a célula movida, o texto arrastado, a cota com o número arrastado: nada disso é forma mudada"""
    g1 = _gerado("g1")
    imp1 = AP.marcar(g1)
    ed = Desenho.de_dict(copy.deepcopy(g1.dict()))
    for e in _por(ed, A):
        ed.entidades[e.id] = transladar(e, 40.0, -15.0)
    t = _por(ed, B, "texto")[0]
    ed.entidades[t.id] = transladar(t, 12.0, 0.0)
    _por(ed, B, "cota")[0].texto_pos = (360.0, 85.0)
    aj = AP.aprender(ed, {"impressoes": {"g1": imp1}})
    assert not any("forma" in v for x in aj["celulas"].values() for v in (x.get("ents") or {}).values())
