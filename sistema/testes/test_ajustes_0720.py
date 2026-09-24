# -*- coding: utf-8 -*-
"""0.7.20: legenda enxuta, cotas da terça pelos furos duplos, contraventamento sem linhas
de chamada."""
from nucleo2d.desenho import Desenho, Cota
from nucleo2d.detalhe.base import _Papel
from nucleo2d.detalhe.celulas import _cabecalho, _cotas_da_terca
from saida.detalhamento import Posicao, Furo


def _cotas(d):
    return [e for e in d.entidades.values() if isinstance(e, Cota)]


def test_cotas_da_terca_duplos_e_simples():
    d = Desenho(nome="t", escala=25.0)
    p = _Papel(d, {}, 0.0, 0.0)
    furos = [Furo("oblongo", 25.0, 30.0, larg=25, alt=13), Furo("oblongo", 25.0, 80.0, larg=25, alt=13),
             Furo("oblongo", 135.0, 55.0, larg=25, alt=13),
             Furo("oblongo", 2462.0, 30.0, larg=25, alt=13), Furo("oblongo", 2462.4, 80.0, larg=25, alt=13),
             Furo("oblongo", 2362.0, 55.0, larg=25, alt=13), Furo("oblongo", 2562.0, 55.0, larg=25, alt=13)]
    assert _cotas_da_terca(p, furos, 4925.0, 10.0, 20.0) == ("dupla", 0)
    cotas = _cotas(d)
    # cadeia dos duplos: 0|25|2462|4925 (3 trechos) + 3 simples a partir do duplo mais perto
    xs = sorted((round(min(c.p1[0], c.p2[0])), round(max(c.p1[0], c.p2[0])), c.deslocamento) for c in cotas)
    assert (0, 25, -10.0) in xs and (25, 2462, -10.0) in xs and (2462, 4925, -10.0) in xs
    simples = [c for c in xs if c[2] != -10.0]
    # os dois simples do duplo do meio (100 | 100) na mesma linha, numa cadeia só (0.7.21)
    assert len(simples) == 3 and (25, 135, -26.0) in simples and (2362, 2462, -26.0) in simples
    assert (2462, 2562, -26.0) in simples
    # sem furo duplo não se aplica
    d2 = Desenho(nome="t", escala=25.0)
    assert _cotas_da_terca(_Papel(d2, {}, 0.0, 0.0), furos[2:3], 4925.0, 10.0, 20.0) is False
    assert not _cotas(d2)


def test_legenda_enxuta():
    pos = Posicao(marca="M13", tipo_ifc="IfcMember", perfil="U150X50X2.28", material="CIVIL 300", quantidade=28,
                  classe="barra", L=4925.0, H=150.0, T=2.28, nome="T.C.1", tipo_nome="terca_cobertura")
    pos.comprimento = 4925.0
    pos.furos = [Furo("oblongo", 25.0, 30.0, larg=25, alt=13)]
    pos.parafusos = {"M12 x 30": 2}
    pos.peso = 21.6
    pos.observacoes.append("furacao no padrao de fabrica")
    linhas = _cabecalho(pos)
    # espessura pela bitola, como a fábrica escreve (2,28 = #13 MSG)
    assert linhas[0] == "T.C.1 – 28x   L = 4925 mm" and linhas[1] == "U150X50X#13"
    # 0.8.4: o tamanho do furo voltou (a fábrica precisa dele), numa linha só
    assert linhas[2] == "furo OBL 25x13"
    assert linhas[3] == "parafusos: 2x M12 x 30" and linhas[4].startswith("21,6 kg/pç")
    txt = "\n".join(linhas)
    for fora in ("TERÇA", "(M13)", "CIVIL", "padrao"):
        assert fora not in txt
