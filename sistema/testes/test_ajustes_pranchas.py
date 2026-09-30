# -*- coding: utf-8 -*-
"""Os ajustes do usuário nas pranchas voltam na próxima geração (nucleo2d.ajustes_pranchas, 29/09): célula
movida e escalada, texto e número de cota arrastados, entidade apagada, desenho à mão — aprendidos do desenho
gravado e aplicados na geração nova, pela identidade da célula e a assinatura da entidade."""
import copy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Linha, Texto, Cota, transladar          # noqa: E402
from nucleo2d import ajustes_pranchas as AP                                  # noqa: E402


def _gerado(geracao="g1"):
    """Três células numa prancha, como a montagem as deixa (cel e a caixa com a origem)."""
    d = Desenho(nome="Pranchas", escala=1.0)
    d.metadados["geracao"] = geracao
    celulas = []
    for cel, (x0, y0) in (("tesouras|conjunto:M1", (100.0, 100.0)), ("chaparias|posicao:P5", (300.0, 100.0)),
                          ("terças|posicao:M18", (100.0, 300.0))):
        celulas.append({"titulo": cel, "id": cel, "caixa": [x0, y0, x0 + 150.0, y0 + 80.0]})
        at = {"cel": cel, "fonte": cel.split("|")[0], "prancha_numero": 1}
        d.add(Linha(camada="VISTA", a=(x0, y0), b=(x0 + 100.0, y0), atributos=dict(at)))
        d.add(Linha(camada="VISTA", a=(x0, y0 + 20.0), b=(x0 + 100.0, y0 + 20.0), atributos=dict(at)))
        d.add(Linha(camada="VISTA", a=(x0, y0), b=(x0, y0 + 20.0), atributos=dict(at)))
        d.add(Texto(camada="TEXTO", posicao=(x0, y0 + 40.0), texto="TITULO " + cel, altura=3.5, atributos=dict(at)))
        d.add(Cota(camada="COTA", p1=(x0, y0), p2=(x0 + 100.0, y0), modo="h", deslocamento=-10.0, atributos=dict(at)))
    d.add(Texto(camada="TEXTO", posicao=(10.0, 10.0), texto="CARIMBO", altura=2.0, atributos={"prancha": "carimbo", "prancha_numero": 1}))
    d.metadados["pranchas"] = [{"numero": 1, "celulas": celulas}]
    return d


def _por(d, cel, tipo=None, texto=None):
    return [e for e in d.entidades.values() if (e.atributos or {}).get("cel") == cel
            and (tipo is None or e.tipo == tipo) and (texto is None or getattr(e, "texto", None) == texto)]


def test_ajustes_voltam_na_proxima_geracao():
    g1 = _gerado("g1")
    imp1 = AP.marcar(g1)
    assert all("g" in (e.atributos or {}) for e in g1.entidades.values() if (e.atributos or {}).get("cel"))
    assert all("s" not in v for v in g1.metadados["ajustaveis"].values())   # as assinaturas ficam fora do desenho
    assert len(imp1) == 3 and all(v["s"] for v in imp1.values())
    # o que o usuário fez na prancha gravada
    ed = Desenho.de_dict(copy.deepcopy(g1.dict()))
    A, B, C = "tesouras|conjunto:M1", "chaparias|posicao:P5", "terças|posicao:M18"
    for e in _por(ed, A):                                   # célula A movida 40, −15
        ed.entidades[e.id] = transladar(e, 40.0, -15.0)
    o = (300.0, 100.0)                                      # célula B escalada 1,5 em volta da origem dela
    for e in _por(ed, B):
        AP._transformar(e, lambda p: (o[0] + 1.5 * (p[0] - o[0]), o[1] + 1.5 * (p[1] - o[1])), 1.5)
    t = _por(ed, C, "texto")[0]                             # na C: o título arrastado 12 mm para a direita
    ed.entidades[t.id] = transladar(t, 12.0, 0.0)
    cota = _por(ed, C, "cota")[0]
    cota.texto_pos = (160.0, 285.0)                         # o número da cota arrastado
    apagada = [e for e in _por(ed, C, "linha") if e.a[1] == e.b[1] and e.a[1] > 310.0][0]
    ed.entidades.pop(apagada.id)                            # a linha de cima da C apagada
    ed.add(Texto(camada="TEXTO", posicao=(500.0, 500.0), texto="NOTA À MÃO", altura=2.5))
    aj = AP.aprender(ed, {"impressoes": {"g1": imp1}})
    assert set(aj["celulas"]) == {A, B, C}, aj["celulas"].keys()
    assert aj["celulas"][A]["d"] == [40.0, -15.0] and aj["celulas"][A]["s"] == 1.0
    assert abs(aj["celulas"][B]["s"] - 1.5) < 1e-6
    assert len(aj["celulas"][C]["apagadas"]) == 1 and len(aj["celulas"][C]["ents"]) == 2
    assert aj["diario"] and aj["a_mao"]
    # a geração nova (pura, com ids novos) recebe tudo
    g2 = _gerado("g2")
    imp2 = AP.marcar(g2)
    rel = AP.aplicar(g2, aj)
    assert rel["apagadas"] == 1 and rel["a_mao"] == 1 and rel["sem_alvo"] == 0, rel
    la = _por(g2, A, "linha")
    assert min(e.a[0] for e in la) == 140.0 and min(e.a[1] for e in la) == 85.0
    lb = _por(g2, B, "linha")
    assert max(max(e.a[0], e.b[0]) for e in lb) == 450.0                  # 300 + 1,5 × 100
    assert abs(_por(g2, B, "texto")[0].altura - 5.25) < 1e-6
    assert _por(g2, C, "texto")[0].posicao == (112.0, 340.0)
    assert _por(g2, C, "cota")[0].texto_pos == (160.0, 285.0)
    assert len(_por(g2, C, "linha")) == 2
    assert any(getattr(e, "texto", "") == "NOTA À MÃO" for e in g2.entidades.values())
    # a segunda rodada mede de novo o ajuste inteiro (as impressões são do gerado puro): nada muda
    aj2 = AP.aprender(Desenho.de_dict(copy.deepcopy(g2.dict())), dict(aj, impressoes={"g2": imp2}))
    assert aj2["celulas"][A]["d"] == [40.0, -15.0]
    assert abs(aj2["celulas"][B]["s"] - 1.5) < 1e-6
    assert len(aj2["celulas"][C]["apagadas"]) == 1
    g3 = _gerado("g3")
    AP.marcar(g3)
    AP.aplicar(g3, aj2)
    assert sum(1 for e in g3.entidades.values() if getattr(e, "texto", "") == "NOTA À MÃO") == 1


def test_celula_montada_de_outro_jeito_nao_e_aprendida():
    """A célula que saiu noutra escala/arranjo entre as gerações (quase tudo "movido dentro dela") não é
    ajuste do usuário: nada é aprendido dela, e a célula de fato mexida ao lado continua aprendida."""
    g1 = _gerado("g1")
    imp1 = AP.marcar(g1)
    ed = Desenho.de_dict(copy.deepcopy(g1.dict()))
    A, B = "tesouras|conjunto:M1", "chaparias|posicao:P5"
    o = (300.0, 100.0)
    for e in _por(ed, B):                                   # B: a geometria noutra escala, as cotas e o texto não
        if e.tipo == "linha":
            AP._transformar(e, lambda p: (o[0] + 1.3 * (p[0] - o[0]) + 7.0, o[1] + 1.3 * (p[1] - o[1]) - 4.0), 1.3)
        else:
            ed.entidades[e.id] = transladar(e, 9.0, 0.0)
    for e in _por(ed, A):                                   # A: movida inteira, um ajuste de verdade
        ed.entidades[e.id] = transladar(e, 20.0, 0.0)
    aj = AP.aprender(ed, {"impressoes": {"g1": imp1}})
    assert B not in aj["celulas"] and aj["celulas"][A]["d"] == [20.0, 0.0]
    assert any("montada de outro jeito" in x["ajuste"] and x["celula"] == B for x in aj["diario"])
    g2 = _gerado("g2")
    AP.marcar(g2)
    antes = {e.id: copy.deepcopy(e) for e in _por(g2, B)}
    AP.aplicar(g2, aj)
    assert all(math.dist(AP._ref(e), AP._ref(antes[e.id])) < 1e-9 for e in _por(g2, B))


def test_sem_ajuste_nao_muda_nada():
    g1 = _gerado("g1")
    imp1 = AP.marcar(g1)
    aj = AP.aprender(Desenho.de_dict(copy.deepcopy(g1.dict())), {"impressoes": {"g1": imp1}})
    assert not aj.get("celulas") and not aj.get("a_mao")
    g2 = _gerado("g2")
    AP.marcar(g2)
    antes = {e.id: copy.deepcopy(e) for e in g2.entidades.values()}
    AP.aplicar(g2, aj)
    assert all(math.dist(AP._ref(e), AP._ref(antes[e.id])) < 1e-9 for e in g2.entidades.values())


def test_repeticao_no_mesmo_lugar_nao_vira_desenho_a_mao():
    """A mesma entidade gerada mais vezes do que a impressão conta, em cima da original, é o gerador repetindo
    a peça (as tesouras projetadas umas sobre as outras na elevação): não vira desenho à mão — guardada, voltava
    em toda geração por cima do desenho novo (9366 entidades no depósito, 30/09). A cópia fora do lugar,
    feita pelo usuário, continua guardada."""
    from nucleo2d.desenho import novo_id
    g1 = _gerado("g1")
    imp1 = AP.marcar(g1)
    ed = Desenho.de_dict(copy.deepcopy(g1.dict()))
    A = "tesouras|conjunto:M1"
    linha = _por(ed, A, "linha")[0]
    em_cima = copy.deepcopy(linha)
    em_cima.id = novo_id()
    ed.add(em_cima)
    copia = transladar(copy.deepcopy(linha), 0.0, 50.0)
    copia.id = novo_id()
    ed.add(copia)
    aj = AP.aprender(ed, {"impressoes": {"g1": imp1}})
    guardadas = list(Desenho.de_dict(aj["a_mao"]).entidades.values())
    assert len(guardadas) == 1 and abs(AP._ref(guardadas[0])[1] - (AP._ref(linha)[1] + 50.0)) < 1e-6
