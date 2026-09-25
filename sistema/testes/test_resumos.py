# -*- coding: utf-8 -*-
"""Resumo da obra / de materiais: as regras que não dependem de um modelo inteiro — terça de
parede pela orientação da seção, porca/arruela solta pela geometria, descrição comercial
do parafuso e o HTML dos dois documentos a partir de um levantamento mínimo."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Solido                                   # noqa: E402
from nucleo2d.detalhe.base import _parede_da_peca                    # noqa: E402
from saida import resumos                                           # noqa: E402


def _caixa(L, H, B, eixo="x", alma="z", origem=(0.0, 0.0, 0.0)):
    """Caixa L (ao longo de `eixo`) × H (ao longo de `alma`) × B, como a envolvente de um
    perfil U: a alma é a direção de H."""
    pts = []
    for a in (0.0, L):
        for h in (0.0, H):
            for b in (0.0, B):
                p = {"x": 0.0, "y": 0.0, "z": 0.0}
                p[eixo] = a
                p[alma] = h
                resto = ({"x", "y", "z"} - {eixo, alma}).pop()
                p[resto] = b
                pts.append((origem[0] + p["x"], origem[1] + p["y"], origem[2] + p["z"]))
    faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return Solido(nome="c", vertices=pts, faces=faces)


def test_terca_de_parede_pela_orientacao_da_secao():
    galpao = (1.0, 0.0, 0.0)
    lim = (0.0, 40000.0)
    # alma de pé (H vertical): terça de cobertura, seja qual for a altura
    assert _parede_da_peca(_caixa(6000, 150, 75, "x", "z", (10000, 0, 6100)), galpao, lim) is None
    # alma deitada, correndo ao longo do galpão: lateral; atravessada: oitão
    assert _parede_da_peca(_caixa(6000, 150, 75, "x", "y", (10000, 0, 6100)), galpao, lim) == "lateral"
    assert _parede_da_peca(_caixa(6000, 150, 75, "y", "x", (10000, 0, 6100)), galpao, lim) == "oitao"
    # seção quadrada deitada (cantoneira) não diz nada
    assert _parede_da_peca(_caixa(1500, 32, 32, "x", "y", (10000, 0, 7000)), galpao, lim) is None
    # agulhamento em pé: de parede; de oitão quando está na ponta do galpão
    assert _parede_da_peca(_caixa(500, 32, 32, "z", "x", (20000, 0, 6100)), galpao, lim) == "lateral"
    assert _parede_da_peca(_caixa(500, 32, 32, "z", "x", (500, 0, 6100)), galpao, lim) == "oitao"


def test_porca_e_arruela_soltas_pela_geometria():
    # medidas reais do IFC do TecnoMETAL (as três extensões principais, mm)
    assert resumos._fixador_solto([16, 16, 12]) == ('Porca 3/8"', 9.5, False)
    assert resumos._fixador_solto([21, 21, 2]) == ('Arruela 3/8"', 9.5, True)
    assert resumos._fixador_solto([37, 35, 24]) == ('Porca 3/4"', 19.1, False)
    assert resumos._fixador_solto([34, 34, 3]) == ('Arruela 5/8"', 15.9, True)
    assert resumos._fixador_solto([38, 38, 4]) == ('Arruela 3/4"', 19.1, True)
    assert resumos._fixador_solto([31, 29, 19]) == ('Porca 5/8"', 15.9, False)


def test_descricao_comercial_do_parafuso():
    nome, desc, d = resumos.descricao_parafuso("M12x35")
    assert nome == "Parafuso M12x35" and d == 12
    assert 'Ø1/2" x 1.1/2"' in desc and "A307" in desc
    nome, desc, d = resumos.descricao_parafuso("M16x50")
    assert "A325" in desc and 'Ø5/8" x 2"' in desc


def test_html_dos_resumos_com_levantamento_minimo():
    R = {
        "projeto": {"nome": "OBRA X", "origem_ifc": "x.R03"},
        "dados": {"revisao": "R03", "descricao": "Cobertura", "telha": "Telha TP40 #0,50", "data": "25/09/2026"},
        "numeros": {"tesouras": 2, "peso_aco": 1000.0, "ml_telhas": 100.0, "peso_telhas": 500.0, "total": 1500.0,
                    "parafusos": 40, "inclinacao": math.degrees(math.atan(0.2)), "kg_m2": 10.0},
        "dimensoes": {"eixos": "A B", "comprimento_total": 6000.0, "n_tesouras": 2, "nivel_apoio": 6613.0, "apoio_por_chapa": True,
                      "trechos": [{"nome": "Galpão", "eixos": "A a B", "vao": 12300.0, "comprimento": 6000.0, "projecao": (8000.0, 14000.0)}],
                      "projecao": (8000.0, 14000.0), "area_m2": 112.0},
        "tesouras": [{"tipo": "T1", "qtd": 2, "eixos": "A, B", "vao": 12300.0, "comprimento": 14700.0, "flecha": 1230.0, "altura": 2117.0,
                      "banzos": "U100X50X#11", "trelicamento": "U92X40X#13", "kg_un": 300.0, "kg_total": 600.0,
                      "membros": {"T1": 2}, "meias": 2, "composicao": {}, "marcas": ["M1"]}],
        "tercas": {"contagem": {k: {"pecas": 0, "tipos": 0} for k in ("cob", "lat", "oit", "marq")},
                   "linhas": [], "perfil_principal": "C150X75X20X#13", "furos": "OBL 25x13"},
        "grupos_peso": [{"grupo": "Tesouras", "kg": 600.0, "pct": 60.0}, {"grupo": "Terças e longarinas", "kg": 400.0, "pct": 40.0}],
        "telhas": {"descricao": "Telha TP40 #0,50", "itens": [], "trechos": {"cobertura": [
            {"codigo_n": "TL1", "codigo": "TL", "qtd": 10, "comprimento": 10000.0, "ml": 100.0, "kg": 500.0, "cortada": False, "perfil": "TP40"}]},
                   "ml_total": 100.0, "kg_total": 500.0, "ml_por_trecho": {"cobertura": 100.0}, "largura_util": 980.0},
        "parafusos": [{"nome": "Parafuso M12x35", "descricao": "Parafuso sextavado", "qtd": 40, "parafuso": True, "d": 12,
                       "locais": [{"local": "terça de cobertura (T.C.) x tesoura", "qtd": 40, "pecas": ["T.C.1", "T1"]}]}],
        "familias": [{"chave": "tesouras", "titulo": "Tesouras", "n": 2, "composicao": "T1 4x", "perfis": [], "kg": 600.0,
                      "sub": [{"titulo": "T1 (02x) - eixos A, B", "perfis": [{"perfil": "U100X50X#11", "kg": 600.0, "m": 100.0, "pecas": 4}]}]}],
        "chaparia": [{"rotulo": "#1/4\" (6,35 mm)", "kg": 20.0, "pecas": 4, "m2": 0.4}], "chaparia_total": {"kg": 20.0, "pecas": 4},
        "perfis_kg": 980.0, "avisos": ["conjuntos M1, M2 têm a mesma geometria", "2 posição(ões) sem peso teórico"],
    }
    obra = resumos.html_resumo_obra(R)
    assert "RESUMO DA OBRA" in obra and "2 meias-tesouras" in obra and "12,30 m" in obra and "+6,613 m" in obra
    assert "inclinação 20% (11,3°)" in obra
    assert "sem peso teórico" in obra and "mesma geometria" not in obra          # só o aviso que muda número
    materiais = resumos.html_resumo_materiais(R)
    assert "RESUMO DE MATERIAIS" in materiais and "U100X50X#11" in materiais and "Parafuso M12x35" in materiais
    # a versão paginada leva o Paged.js e o sinal de fim de paginação da impressão
    paginado = resumos.html_resumo_obra(R, paginado=True)
    assert "paged.polyfill.js" in paginado and "data-paged" in paginado
