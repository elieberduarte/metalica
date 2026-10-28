# -*- coding: utf-8 -*-
"""As instâncias de um conjunto remontadas dos fragmentos (nucleo2d/detalhe/conjuntos._instancias_do_conjunto).

27/10/2026 (SESI Chapecó): o resumo da obra não terminava em mais de 1 h — o conjunto dos brises (CH 60×310 + 8 CH 50×60 +
CH 60×300 por quadro, as chapinhas soltas umas das outras) virava centenas de fragmentos, e a junção varria todos os pares a
cada passo (O(n³), um Counter novo por par). Agora os pares ficam numa fila; o resultado tem de ser o MESMO da varredura."""
import collections
import random
import time

from nucleo3d.modelo import Solido
from nucleo2d.detalhe import conjuntos as C


def _peca(nome, x, y, z, t=10.0):
    vs = [(x + a, y + b, z + c) for a in (0.0, t) for b in (0.0, t) for c in (0.0, t)]
    return Solido(nome=nome, vertices=vs, faces=[])


def _referencia(lista, unidade, folga=60.0):
    """a varredura de antes de 27/10 (todos os pares a cada junção), para comparar o resultado"""
    def comp(g):
        return collections.Counter(C.posicao_base(e) for e in g)

    def cabe(c):
        return all(unidade.get(k, 0) >= q for k, q in c.items())
    grupos = []
    for g in C._instancias(lista, folga=folga):
        k = C._multiplo(g, unidade)
        partes = C._dividir(g, k, unidade) if k > 1 else []
        grupos.extend(partes or [g])
    completos = [g for g in grupos if comp(g) == unidade or not cabe(comp(g))]
    frag = [g for g in grupos if comp(g) != unidade and cabe(comp(g))]
    centros = [C._centro(g) for g in frag]
    comps = [comp(g) for g in frag]
    for _ in range(len(frag)):
        melhor = None
        for i in range(len(frag)):
            for j in range(i + 1, len(frag)):
                if not cabe(comps[i] + comps[j]):
                    continue
                d = sum((centros[i][k] - centros[j][k]) ** 2 for k in range(3))
                if melhor is None or d < melhor[0]:
                    melhor = (d, i, j)
        if melhor is None:
            break
        _, i, j = melhor
        frag[i] = frag[i] + frag[j]
        comps[i] = comps[i] + comps[j]
        centros[i] = C._centro(frag[i])
        del frag[j], comps[j], centros[j]
    return completos + frag


def _brises(n, embaralhar=0.0, semente=1):
    """n quadros do brise, cada um com CH60X310 + 8 CH50X60 + CH60X300 soltas (a 200 mm umas das outras), quadros a 1 m"""
    rnd = random.Random(semente)
    pecas = []
    for q in range(n):
        x0 = q * 1000.0
        nomes = ["CH60X310"] + ["CH50X60"] * 8 + ["CH60X300"]
        for i, nome in enumerate(nomes):
            pecas.append(_peca(nome, x0 + rnd.uniform(-embaralhar, embaralhar), 200.0 * i, rnd.uniform(-embaralhar, embaralhar)))
    rnd.shuffle(pecas)
    return pecas


UNIDADE = collections.Counter({"CH60X310": 1, "CH50X60": 8, "CH60X300": 1})


def _ids(grupos):
    return [sorted(id(e) for e in g) for g in grupos]


def test_mesmo_resultado_da_varredura():
    for semente in range(8):
        pecas = _brises(6, embaralhar=150.0 if semente < 6 else 0.0, semente=semente)   # 6, 7: malha exata, distâncias empatadas
        if semente % 2:
            pecas = pecas[:-3]                       # instâncias incompletas: sobram fragmentos que não fecham a unidade
        assert _ids(C._instancias_do_conjunto(pecas, UNIDADE)) == _ids(_referencia(pecas, UNIDADE))


def test_remonta_os_quadros():
    grupos = C._instancias_do_conjunto(_brises(8), UNIDADE)
    assert len(grupos) == 8
    assert all(collections.Counter(C.posicao_base(e) for e in g) == UNIDADE for g in grupos)


def test_muitos_fragmentos_termina_rapido():
    # 200 quadros = 2.000 chapinhas soltas: a varredura não terminava (no SESI, mais de 1 h no resumo da obra)
    pecas = _brises(200)
    t = time.time()
    grupos = C._instancias_do_conjunto(pecas, UNIDADE)
    assert time.time() - t < 20.0
    assert len(grupos) == 200
