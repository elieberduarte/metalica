# -*- coding: utf-8 -*-
"""As cotas das pranchas pelas regras de 26/10 (usuário, na T1 da Sala de Compressores ajustada à mão):

* o texto das cotas e das chamadas das pranchas geradas é de 5 mm de papel (era 2,5 e 2,0);
* na cadeia dos nós do banzo de cima, o vão entre duas terças dividido ao meio por um nó só (773 + 773) não leva as
  duas cotas — a fábrica divide na montagem; a metade desigual (754 + 792, 773 + 875 na cumeeira) fica.

Conferido na Sala de Compressores (T1–T4): saem os pares 773 + 773; ficam 754/792 (T3), 799/747 e 755/791 (T4) e
773/875 na cumeeira de todas.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Chamada, Cota, Desenho  # noqa: E402
from nucleo2d.detalhe.base import ALTURA_CHAMADA, ALTURA_COTA, _Papel  # noqa: E402
from nucleo2d.detalhe.conjuntos import sem_metades_iguais  # noqa: E402


def _cadeia(d, xs, inclinacao=0.2):
    """Cotas alinhadas entre os nós xs, numa reta inclinada (como o banzo de cima), e as chaves delas."""
    k = math.hypot(1.0, inclinacao)
    chaves = []
    for a, b in zip(xs, xs[1:]):
        c = Cota(modo="alinhada", p1=(a, a * inclinacao), p2=(b, b * inclinacao), deslocamento=10.0)
        d.add(c)
        chaves.append(c.id)
    return chaves, k


def _medidas(d, chaves):
    return [round(math.dist(d.entidades[k].p1, d.entidades[k].p2)) for k in chaves if k in d.entidades]


def test_metades_iguais_entre_tercas_saem_e_as_desiguais_ficam():
    d = Desenho(escala=25.0)
    # os nós, na abscissa da planta (a reta tem inclinação 0,2: a cota mede na reta, × 1,0198)
    k = math.hypot(1.0, 0.2)
    m = lambda mm: mm / k                                  # noqa: E731 — o mm medido na reta → abscissa
    x = [0.0]
    for vao in (773, 773, 754, 792, 773, 772, 773, 875):
        x.append(x[-1] + m(vao))
    chaves, _ = _cadeia(d, x)
    # as terças: de dois em dois nós (o vão de 1.546)
    tercas = [x[0], x[2], x[4], x[6], x[8]]
    tiradas = sem_metades_iguais(d, chaves, [tercas])
    assert tiradas == 4
    # ficam a metade desigual (754/792) e a da cumeeira (773/875); saem 773/773 e 773/772 (até 1 mm)
    assert _medidas(d, chaves) == [754, 792, 773, 875]


def test_sem_terca_cotada_nada_sai():
    d = Desenho(escala=25.0)
    chaves, _ = _cadeia(d, [0.0, 773.0, 1546.0])
    assert sem_metades_iguais(d, chaves, []) == 0
    assert len(_medidas(d, chaves)) == 2


def test_dois_nos_entre_tercas_ficam():
    d = Desenho(escala=25.0)
    chaves, _ = _cadeia(d, [0.0, 515.0, 1030.0, 1545.0], inclinacao=0.0)
    assert sem_metades_iguais(d, chaves, [[0.0, 1545.0]]) == 0


def test_texto_das_cotas_e_chamadas_das_pranchas_em_5_mm():
    assert ALTURA_COTA == 5.0 and ALTURA_CHAMADA == 5.0
    d = Desenho(escala=25.0)
    p = _Papel(d, {}, 0.0, 0.0)
    p.cota_h(0.0, 1000.0, 0.0, -10.0)
    p.cota_v(0.0, 700.0, 0.0, 10.0)
    p.cadeia_alinhada(((0.0, 0.0), (8000.0, 1600.0)), [0.0, 773.0, 1546.0], 10.0)
    p.chamada(0.0, 0.0, 200.0, 200.0, "CH3")
    cotas = [e for e in d.entidades.values() if isinstance(e, Cota)]
    assert cotas and all(c.altura == 5.0 for c in cotas)
    assert [e.altura for e in d.entidades.values() if isinstance(e, Chamada)] == [5.0]


def _chapa(nome, x, y):
    from nucleo3d.modelo import Solido
    vs = [(x + dx, y + dy, dz) for dx in (0.0, 100.0) for dy in (0.0, 100.0) for dz in (0.0, 10.0)]
    return Solido(vertices=vs, faces=[], atributos={"tipo_ifc": "IfcPlate", "marcas": {"posicao": nome}})


def test_chamada_das_chapas_em_toda_ocorrencia_com_ramo_so_para_perto():
    """A CH9 das duas pontas da tesoura (16 m uma da outra): uma chamada em cada (antes, só a do meio); o suporte
    CH3 repetido a 800 mm: uma chamada com uma seta a mais; a chapinha de cada terça (6 vezes): uma chamada só."""
    from nucleo2d.detalhe.conjuntos import chamadas_das_chapas
    d = Desenho(escala=25.0)
    p = _Papel(d, {}, 0.0, 0.0)
    pecas = [_chapa("P9", 0.0, 0.0), _chapa("P9", 16000.0, 0.0), _chapa("P3", 5000.0, 2000.0), _chapa("P3", 5800.0, 2150.0)]
    pecas += [_chapa("P1", 1000.0 + 1546.0 * i, 800.0 + 300.0 * i) for i in range(6)]
    nomes = {"P9": "CH9", "P3": "CH3", "P1": "CH1"}
    chamadas_das_chapas(p, pecas, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 0.0, 0.0, 25.0, nomes.get)
    ch = [e for e in d.entidades.values() if isinstance(e, Chamada)]
    por = {}
    for c in ch:
        por.setdefault(c.texto, []).append(len(c.ramos))
    assert sorted(por["CH9"]) == [0, 0]
    assert por["CH3"] == [1]
    assert por["CH1"] == [0]


def test_chamada_do_suporte_de_terca_com_o_nome_do_suporte():
    """Usuário, 30/10, na T1 da Sala: "Essas devem ser marcado o nome do suporte de terça e não as chapas se é o S.T.1,
    ou S.T.2". Saía "CH1 + CH3" e "CH2" separadas (a CH1 juntava com a CH3 do lado e a CH2, do mesmo suporte, ficava
    sozinha). O S.T.1 é a CH1 soldada na CH2 (a chave "P11 + P12" da nomeação); a CH3 ao lado não é dele e segue com o
    nome dela; a chapa que é o suporte sozinha (S.T.2 = "P20") também troca."""
    from nucleo2d.detalhe.conjuntos import chamadas_das_chapas
    d = Desenho(escala=25.0)
    p = _Papel(d, {}, 0.0, 0.0)
    pecas = []
    for i in range(6):                                   # o suporte em cada terça: CH2 a 40 mm da CH1 (como na Sala)
        x, y = 1000.0 + 1546.0 * i, 800.0 + 300.0 * i
        pecas += [_chapa("P12", x - 22.0, y + 33.0), _chapa("P11", x, y)]
    pecas += [_chapa("P13", 1135.0, 788.0)]              # a CH3 a 135 mm da CH1 da primeira terça
    pecas += [_chapa("P20", 12000.0, 0.0)]
    nomes = {"P11": "CH1", "P12": "CH2", "P13": "CH3", "P20": "CH7"}
    chamadas_das_chapas(p, pecas, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 0.0, 0.0, 25.0, nomes.get,
                        suportes={"P11 + P12": "S.T.1", "P20": "S.T.2"})
    textos = sorted(e.texto for e in d.entidades.values() if isinstance(e, Chamada))
    assert textos == ["CH3 + S.T.1", "S.T.1", "S.T.2"], textos
    assert not any("CH1" in t or "CH2" in t or "CH7" in t for t in textos)


def test_mover_a_celula_leva_as_setas_a_mais_da_chamada():
    """O detalhamento translada cada célula para o lugar dela na folha (base._mover): as setas a mais iam ficando no lugar
    antigo, atravessando a prancha (visto na T1 da Sala de Compressores, 26/10)."""
    from nucleo2d.detalhe.base import _mover
    c = Chamada(alvo=(0.0, 0.0), posicao=(10.0, 10.0), texto="CH3", ramos=[{"de": 1.0, "alvo": (5.0, 0.0)}])
    _mover(c, 100.0, 50.0)
    assert c.alvo == (100.0, 50.0) and c.posicao == (110.0, 60.0)
    assert tuple(c.ramos[0]["alvo"]) == (105.0, 50.0)


def test_uniao_das_chapas_ao_mm_com_a_espessura_do_pacote():
    """As duas chapas de topo de 9,5 mm encostadas no meio, com a malha a 9,55 do centro: o pacote sai 19, centrado."""
    from nucleo2d.desenho import Linha
    from nucleo2d.detalhe.conjuntos import uniao_das_chapas
    d = Desenho(escala=25.0)
    for x in (990.45, 1000.0, 1009.55):
        d.add(Linha(camada="CHAPAS-VISTA", a=(x, 0.0), b=(x, 300.0), atributos={"conjunto": "T"}))
    lo, hi = uniao_das_chapas(d, "T", 1000.0)
    assert hi - lo == 19.0 and lo == 991.0
    assert uniao_das_chapas(Desenho(), "T", 1000.0) is None


# ---------------------------------------------------------------- na Sala de Compressores, como veio do TecnoMETAL
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SALA = os.path.join(RAIZ, "Projeto", "OBRAS", "ME-Sooro", "Compressores de Ar Comprimido", "teste-primeiro-uso",
                    "modelo-importado.json.gz")
_TESOURAS = {}


def _tesouras_da_sala():
    if "d" not in _TESOURAS:
        import gzip
        import json
        from nucleo3d.modelo import Documento
        from nucleo2d.detalhar import detalhar
        with gzip.open(SALA, "rt", encoding="utf-8") as f:
            doc = Documento.de_dict(json.load(f))
        _TESOURAS["d"] = detalhar(doc, grupos=["tesouras"])["desenhos"]["tesouras"]
    return _TESOURAS["d"]


def _cadeias(d, conjunto):
    por = {}
    for c in sorted((e for e in d.entidades.values() if isinstance(e, Cota) and (e.atributos or {}).get("conjunto") == conjunto
                     and (e.atributos or {}).get("detalhe") == "conjunto"), key=lambda c: c.p1[0]):
        por.setdefault((c.modo, round(c.deslocamento, 1)), []).append(round(math.dist(c.p1, c.p2)))
    return por


import pytest  # noqa: E402


@pytest.mark.skipif(not os.path.exists(SALA), reason="sem o modelo da Sala (outra máquina)")
def test_tesoura_montada_da_sala_cotada_ate_o_centro_e_a_uniao_das_chapas():
    """Usuário, 26/10, na T1 da Sala: a tesoura é montada com as chapas de união no lugar — a cadeia de baixo vai até o
    centro geométrico (780 | 420 | 7130, antes 7126 + uma folga de 8 que não existe) e a da cumeeira até a face das
    chapas (853 | 19 | 852, antes 858 | 8 | 858)."""
    d = _tesouras_da_sala()
    montadas = {(e.atributos or {}).get("conjunto") for e in d.entidades.values()
                if " + " in str((e.atributos or {}).get("conjunto") or "")}
    assert montadas
    for cj in montadas:
        c = _cadeias(d, cj)
        baixo = c.get(("h", -10.0)) or []
        assert 8 not in baixo, (cj, baixo)
        assert 19 in (c.get(("h", -20.0)) or []), (cj, c.get(("h", -20.0)))
    t1 = _cadeias(d, "M2 + M2")
    # no modelo como veio do TecnoMETAL (na obra, depois dos ajustes: 780 | 420 | 7130 e 853 | 19 | 852)
    assert t1[("h", -10.0)][2:4] == [7130, 7130]
    assert t1[("h", -20.0)] == [858, 19, 857]


@pytest.mark.skipif(not os.path.exists(SALA), reason="sem o modelo da Sala (outra máquina)")
def test_tesouras_da_sala_chamam_o_suporte_de_terca_pelo_s_t():
    """No modelo como veio do TecnoMETAL, só com as tesouras pedidas: o S.T.1 aparece nas chamadas das quatro tesouras e
    nenhuma chamada junta só as duas chapas dele (CH1 + CH10 nesse modelo, a chave "P11 + P12")."""
    from nucleo2d.desenho import Chamada as Ch
    d = _tesouras_da_sala()
    por = {}
    for e in d.entidades.values():
        if isinstance(e, Ch) and str((e.atributos or {}).get("nome") or "").startswith("T"):
            por.setdefault(e.atributos["nome"], []).append(e.texto)
    assert set(por) >= {"T1", "T2", "T3", "T4"}
    for t, textos in por.items():
        assert any("S.T.1" in x for x in textos), (t, textos)
        assert "CH1 + CH10" not in textos and "CH1 + CH2" not in textos, (t, textos)


@pytest.mark.skipif(not os.path.exists(SALA), reason="sem o modelo da Sala (outra máquina)")
def test_tesouras_da_sala_sem_as_metades_iguais_entre_tercas():
    d = _tesouras_da_sala()
    nos = lambda cj: _cadeias(d, cj).get(("alinhada", 10.0)) or []      # noqa: E731
    assert nos("M2 + M2").count(773) == 2                                 # só os da cumeeira (773 | 875)
    assert 750 in nos("M5 + M6") and 796 in nos("M5 + M6")               # a metade desigual fica
    assert {798, 748, 750, 796} <= set(nos("M8 + M9"))
