# -*- coding: utf-8 -*-
"""Módulo de arquitetura — a estatística da prancha da prefeitura (Cascavel, Aprova Fácil; 02/11/2026): área do terreno,
área a construir (fechada + coberta aberta, por andar), taxas de ocupação, permeabilidade e impermeabilização e o
coeficiente de aproveitamento. Contas feitas à mão nos comentários."""
import pytest

pytest.importorskip("shapely")

from arquitetura import estatistica as E
from arquitetura import modelo as M
from arquitetura.piloto import montar_casa
from nucleo3d.modelo import Documento

NIVEIS = [{"nome": "Térreo", "cota": 0, "laje": 100}, {"nome": "Superior", "cota": 3000, "laje": 150},
          {"nome": "Cobertura", "cota": 6000, "laje": 150}]


def _casinha(sacada=False):
    """lote 12 × 30 = 360 m²; casa 8 × 10 pela face de fora (paredes de 20 pelo eixo); a laje do superior avança 1,5 m
    na frente (o alpendre do térreo); jardim de 12 × 10 nos fundos"""
    d = Documento(nome="teste")
    M.definir_niveis(d, NIVEIS)
    M.novo_lote(d, [(0, 0), (12000, 0), (12000, 30000), (0, 30000)],
                permeaveis=[[(0, 20000), (12000, 20000), (12000, 30000), (0, 30000)]])
    cantos = [(2100, 5100), (9900, 5100), (9900, 14900), (2100, 14900)]
    for a, b in zip(cantos, cantos[1:] + cantos[:1]):
        M.nova_parede(d, a, b, "EXT20", "Térreo", "Superior")
    M.novo_ambiente(d, "Sala", (2000, 10000, 5000, 15000), "Térreo")
    M.nova_laje(d, [(2000, 3500), (10000, 3500), (10000, 15000), (2000, 15000)], "Superior")
    if sacada:
        # o superior com a sacada de 1,5 m que não tem nada em cima
        for a, b in zip(cantos, cantos[1:] + cantos[:1]):
            M.nova_parede(d, a, b, "EXT20", "Superior", "Cobertura")
        M.novo_ambiente(d, "Quarto", (2000, 10000, 5000, 15000), "Superior")
        M.nova_laje(d, [(2000, 5000), (10000, 5000), (10000, 15000), (2000, 15000)], "Cobertura")
    M.regenerar(d)
    return d


def test_area_fechada_e_coberta_aberta():
    """fechada 8 × 10 = 80; o alpendre 8 × 1,5 = 12 conta como coberta aberta: 92 m². TO = 92 / 360 = 25,6 %;
    TP = 120 / 360 = 33,3 %; TI = 66,7 %; CA = 92 / 360 = 0,26"""
    r = E.calcular(_casinha())
    assert r["terreno"] == 360 and r["construir"] == 92
    assert r["andares"] == [{"andar": "Térreo", "fechada": 80, "coberta_aberta": 12, "area": 92}]
    assert (r["taxa_ocupacao"], r["taxa_permeabilidade"], r["taxa_impermeabilizacao"], r["coeficiente"]) == \
           (25.6, 33.3, 66.7, 0.26)
    assert dict(E.quadro(r))["Área do terreno"] == "360,00 m²"
    assert dict(E.quadro(r))["Taxa de ocupação"] == "25,6 %"


def test_sacada_descoberta_nao_conta_no_andar_de_cima():
    """o superior: fechada 80, coberto pela laje da cobertura só até a face (y 5000) — a sacada não entra: 92 + 80"""
    r = E.calcular(_casinha(sacada=True))
    assert [a["area"] for a in r["andares"]] == [92, 80]
    assert r["construir"] == 172 and r["projecao"] == 92 and r["coeficiente"] == pytest.approx(0.48)


def test_sem_lote_avisa():
    d = Documento(nome="teste")
    M.definir_niveis(d, NIVEIS)
    with pytest.raises(ValueError, match="lote"):
        E.calcular(d)


def test_lote_aparece_no_3d_na_camada_do_terreno():
    d = _casinha()
    lt = next(e for e in d.entidades.values() if e.atributos["arq"]["elemento"] == "lote")
    assert lt.camada == "ARQ — Terreno" and lt.vertices and lt.faces
    zs = [v[2] for v in lt.vertices]
    assert (min(zs), max(zs)) == (-10, 20)         # o jardim 1 cm abaixo, a divisa 2 cm acima


def test_casa_piloto():
    """o lote de 30,5 × 34,8 = 1061,40 m². Garagem (−0,35) e térreo são um andar só: fechada 128,8 + 59,5 + 24 (estúdio)
    = 212,30, e coberto pela laje do superior (com a sacada da frente de 1,8 m e a dos fundos), pela do terraço (com a
    marquise da entrada) e pela do estúdio: 287,76. Superior: fechada 14 × 10,4 = 145,60 + a varanda coberta pela
    cobertura (14 × 0,6 = 8,40) = 154,00. A casinha das caixas não é andar (sem ambiente)"""
    r = E.calcular(montar_casa())
    assert r["terreno"] == pytest.approx(1061.40)
    assert [(a["fechada"], a["coberta_aberta"], a["area"]) for a in r["andares"]] == \
           [(212.30, 75.46, 287.76), (145.60, 8.40, 154.00)]
    assert r["construir"] == pytest.approx(441.76) and r["projecao"] == pytest.approx(287.76)
    assert (r["taxa_ocupacao"], r["taxa_permeabilidade"], r["coeficiente"]) == (27.1, 41.2, 0.42)
