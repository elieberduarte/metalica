# -*- coding: utf-8 -*-
"""Correção feita na elevação do conjunto (CAD) volta para o 3D (0.8.17): barra apagada
sai, barra espelhada gira, barra esticada tem a ponta movida, cópia vira peça nova — em
todas as instâncias do conjunto — e a cópia posta na célula de outra tesoura nasce lá."""
import copy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Barra                     # noqa: E402
from nucleo2d import vistas as V                                  # noqa: E402
from nucleo2d.desenho import Desenho, Linha, Polilinha            # noqa: E402
from nucleo2d.detalhe import aplicar_pecas as AP                  # noqa: E402


def _barra(pos, conj, a, b):
    e = Barra(perfil='U 3"×6,1', inicio=a, fim=b, camada="Vigas", papel="banzo")
    e.atributos["marcas"] = {"posicao": pos, "conjunto": conj}
    return e


def _tesoura(doc, conj, x0):
    """Banzo inferior P1 (6 m), banzo superior P2, montante P3 no meio e diagonal P4 da
    ponta esquerda, no plano y = x0 (a elevação olha em +y)."""
    ids = {}
    for pos, a, b in (("P1", (0, x0, 0), (6000, x0, 0)), ("P2", (0, x0, 800), (6000, x0, 800)),
                      ("P3", (3000, x0, 0), (3000, x0, 800)), ("P4", (0, x0, 0), (1500, x0, 800))):
        e = _barra(pos, conj, a, b)
        doc.add(e)
        ids[pos] = e.id
    return ids


def _desenho(doc, celulas):
    """A elevação de cada conjunto como o detalhamento a monta: uma vista por célula,
    linhas com `origem` e `conjunto`, cantos lado a lado."""
    d = Desenho(nome="Detalhamento – tesouras", escala=25.0)
    x = 0.0
    for conj, ids in celulas:
        vista = V.Vista(origem=(3000, 10 ** 6, 400), normal=(0, 1, 0), acima=(0, 0, 1), profundidade=None, cortar=False,
                        entidades=list(ids.values()), rotular=False, nome="Conjunto %s" % conj, tipo="conjunto")
        # origem atrás de tudo, como em desenho_do_conjunto (observador em -w)
        vista.origem = (3000.0, -10.0 + min(doc.entidades[i].inicio[1] for i in ids.values()), 400.0)
        antes = set(d.entidades)
        V.gerar(doc, vista, d, (x, 0.0))
        for k in d.entidades:
            if k not in antes:
                d.entidades[k].atributos = dict(d.entidades[k].atributos or {}, conjunto=conj)
        x += 8000.0
    return d


def _linhas_de(d, origem, conj=None):
    return [e for e in d.entidades.values() if isinstance(e, (Linha, Polilinha)) and (e.atributos or {}).get("origem") == origem
            and (conj is None or (e.atributos or {}).get("conjunto") == conj) and not (e.atributos or {}).get("grupo_copia")]


def _mover_linhas(ents, f):
    for e in ents:
        if isinstance(e, Linha):
            e.a, e.b = f(e.a), f(e.b)
        else:
            e.vertices = [f(p) for p in e.vertices]


def _copiar_linhas(d, ents, f, grupo):
    for e in ents:
        c = copy.deepcopy(e)
        c.id = c.id + "-" + grupo
        c.atributos = dict(c.atributos, grupo_copia=grupo)
        d.add(c)
        _mover_linhas([c], f)


def test_apagar_espelhar_esticar_copiar_em_todas_as_instancias():
    doc = Documento(nome="t")
    a = _tesoura(doc, "M1", 0.0)          # referência (a da célula)
    b = _tesoura(doc, "M1", 6000.0)       # outra instância do mesmo conjunto
    gerado = _desenho(doc, [("M1", a)])
    usuario = copy.deepcopy(gerado)
    # 1. o montante P3 sai; 2. a diagonal P4 espelhada (vai do nó de baixo à direita para o
    # de cima à esquerda... aqui: gira em torno do meio dela); 3. o banzo superior P2
    # esticado 500 mm na ponta direita; 4. cópia da diagonal 3 m à direita
    for e in _linhas_de(usuario, a["P3"]):
        usuario.remover(e.id)
    l4 = _linhas_de(usuario, a["P4"])
    pts = [p for e in l4 for p in (e.vertices if isinstance(e, Polilinha) else [e.a, e.b])]
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    _mover_linhas(l4, lambda p: (2 * cx - p[0], p[1]))                          # espelho vertical pelo centro
    l2 = _linhas_de(usuario, a["P2"])
    _mover_linhas(l2, lambda p: (p[0] + 500.0, p[1]) if p[0] > 3000 else p)   # esticar a ponta direita
    _copiar_linhas(usuario, _linhas_de(usuario, a["P4"]), lambda p: (p[0] + 3000.0, p[1]), "g1")

    r = AP.aplicar_desenho_ao_modelo(doc, usuario, [gerado])
    c = r["celulas"]["M1"]
    assert c["instancias"] == 2 and c["apagadas"] == 2 and c["movidas"] == 2 and c["esticadas"] == 2 and c["copiadas"] == 2, c
    # apagadas nas duas instâncias
    assert a["P3"] not in doc.entidades and b["P3"] not in doc.entidades
    # espelhada: a diagonal continua com 1,5 m de projeção e 0,8 m de altura, mas inclinada ao contrário
    for ids in (a, b):
        p4 = doc.entidades[ids["P4"]]
        dx = p4.fim[0] - p4.inicio[0]
        assert abs(abs(dx) - 1500) < 5 and abs(abs(p4.fim[2] - p4.inicio[2]) - 800) < 5
        assert (p4.fim[2] - p4.inicio[2]) * dx < 0, (p4.inicio, p4.fim)        # sobe para a esquerda agora
        assert abs(p4.inicio[1] - p4.fim[1]) < 1e-6                           # ficou no plano da tesoura
        # esticada: a ponta direita do banzo superior foi a 6 500
        p2 = doc.entidades[ids["P2"]]
        assert abs(max(p2.inicio[0], p2.fim[0]) - 6500) < 5 and abs(min(p2.inicio[0], p2.fim[0])) < 5
    # cópias: uma peça nova por instância, 3 m à direita da diagonal, na profundidade da instância
    novas = [e for e in doc.entidades.values() if (e.atributos or {}).get("copiada_de") == a["P4"]]
    assert len(novas) == 2
    ys = sorted(round(e.inicio[1]) for e in novas)
    assert ys == [0, 6000], ys
    for e in novas:
        assert abs(min(e.inicio[0], e.fim[0]) - (3000 - 1500 + 1500)) < 5 or abs(min(e.inicio[0], e.fim[0]) - 3000) < 5


def test_copia_na_celula_de_outra_tesoura_nasce_na_outra_tesoura():
    doc = Documento(nome="t")
    a = _tesoura(doc, "M1", 0.0)
    b = _tesoura(doc, "M2", 9000.0)       # outro conjunto, célula ao lado
    gerado = _desenho(doc, [("M1", a), ("M2", b)])
    usuario = copy.deepcopy(gerado)
    # a diagonal de M1 copiada para dentro da célula de M2 (8 m à direita), na ponta esquerda de M2
    _copiar_linhas(usuario, _linhas_de(usuario, a["P4"]), lambda p: (p[0] + 8000.0, p[1]), "g2")
    r = AP.aplicar_desenho_ao_modelo(doc, usuario, [gerado])
    assert "M2" in r["celulas"] and r["celulas"]["M2"]["copiadas"] == 1 and "M1" not in r["celulas"], r
    novas = [e for e in doc.entidades.values() if (e.atributos or {}).get("copiada_de") == a["P4"]]
    assert len(novas) == 1
    e = novas[0]
    # no plano da tesoura M2 (a profundidade é a média da instância: até 5 mm de folga)
    assert abs(e.inicio[1] - 9000) < 5 and abs(e.fim[1] - 9000) < 5
    assert abs(min(e.inicio[0], e.fim[0])) < 5                                  # na ponta esquerda dela


def test_sem_mudanca_nao_mexe():
    doc = Documento(nome="t")
    a = _tesoura(doc, "M1", 0.0)
    gerado = _desenho(doc, [("M1", a)])
    antes = {k: (e.inicio, e.fim) for k, e in doc.entidades.items()}
    r = AP.aplicar_desenho_ao_modelo(doc, copy.deepcopy(gerado), [gerado])
    assert r["celulas"] == {} and {k: (e.inicio, e.fim) for k, e in doc.entidades.items()} == antes
