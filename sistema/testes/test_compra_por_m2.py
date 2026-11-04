# -*- coding: utf-8 -*-
"""FAB-09 (REGRAS.md): o que se compra por m² (telha, painel, chapa expandida) pesa pela massa por m² do fabricante, não
pelo volume da malha × 7.850 — e a funilaria (calha, rufo) do IFC sai como funilaria também quando só a camada diz.

Reincidência (04/11/2026, Mall Av. Londrina, IFC4 do SteelX): as 150 Isotelhas RB PIR/PIR 30 mm vinham como IfcMember e
pesavam como aço maciço — 1.774,5 kg cada, 266 t na lista, que devia dar 20,3 t. A 1ª vez foi a chapa expandida do Posto
V2 (24/10: 4,3 t como chapa cheia). A FAB-09 não tinha conferência: agora o levantamento avisa o item por m² com mais de
30 kg/m². E as calhas "cl." e os rufos "rft" do SteelX (o nome não diz o que são; a camada Calhas/Rufos, que a leitura
põe pela função do pset, diz) saíam como BARRAS de aço.

Os casos vêm do trecho do arquivo do projetista (testes/dados_ifc/steelx_mall_trecho.ifc)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ifc.importar import importar                             # noqa: E402
from nucleo2d import detalhar as det                          # noqa: E402
from nucleo2d.detalhe.base import _categoria                  # noqa: E402
from nucleo2d.detalhe.fora_do_aco import KG_M2_MAXIMO, conferir_compra_por_m2  # noqa: E402
from saida import detalhamento as dt                          # noqa: E402

TRECHO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_ifc", "steelx_mall_trecho.ifc")
_LEV = {}


def _lev():
    if "lev" not in _LEV:
        _LEV["lev"] = det.levantar(importar(TRECHO))
    return _LEV["lev"]


def _pos(perfil):
    return next(p for p in _lev()["posicoes"] if p.perfil == perfil)


def test_isotelha_nao_pesa_como_aco_macico():
    p = _pos("ISOTELHA RB - PIR/PIR AP 30mm")
    assert p.classe == "telha"
    area = p.L * p.H * 1e-6                                    # 7,25 × 1,07 m
    assert p.peso <= KG_M2_MAXIMO * area, "%.1f kg em %.2f m²" % (p.peso, area)   # antes: 1.774,5 kg (229 kg/m²)
    assert any("massa por m²" in o for o in p.observacoes), p.observacoes


def test_a_conferencia_da_fab09_avisa_o_que_pesa_como_aco_macico():
    p = dt.Posicao(marca="p.", tipo_ifc="IfcMember", perfil="ISOTELHA RB - PIR/PIR AP 30mm")
    p.classe, p.L, p.H, p.peso, p.quantidade = "telha", 7250.0, 1069.0, 1774.5, 150
    avisos = conferir_compra_por_m2([p], [])
    assert len(avisos) == 1 and "p." in avisos[0] and "229" in avisos[0], avisos
    # o Quadro 8 também: a chapa expandida pesada como chapa cheia
    exp = {"nome": "Chapa expandida #1/4\"", "categoria": "chapa expandida", "area_m2": 87.0, "peso_kg": 4300.0}
    assert len(conferir_compra_por_m2([], [exp])) == 1
    # a telha de aço de uma chapa (TP 25 0,50) passa: ~5 kg/m²
    t = dt.Posicao(marca="TL1", tipo_ifc="IfcMember", perfil="TP 25 0,50 mm")
    t.classe, t.L, t.H, t.peso, t.quantidade = "telha", 6000.0, 1000.0, 29.4, 10
    assert conferir_compra_por_m2([t], []) == []


def test_o_levantamento_do_mall_passa_na_conferencia():
    assert not [a for a in _lev()["avisos"] if "FAB-09" in a], _lev()["avisos"]


def test_calha_e_rufo_do_steelx_saem_como_funilaria():
    lev = _lev()
    for perfil in ("cl.", "rft"):
        p = _pos(perfil)
        assert _categoria(p, lev["camadas"].get(p.marca, "")) == "RUFOS", perfil
        assert lev["categorias"][p.marca] == "RUFOS", perfil


def test_a_telha_de_aco_de_uma_chapa_continua_pelo_volume():
    """A telha que é só a chapa de aço (o TP 25 do Tekla) continua pesando pelo volume: lá o volume é o aço."""
    v = [(x, y, z) for x in (0.0, 6000.0) for y in (0.0, 1000.0) for z in (0.0, 0.5)]
    f = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    p = dt.Posicao(marca="TL1", tipo_ifc="IfcMember", perfil="TP 25 0,50 mm", vertices=v, faces=f)
    dt.analisar(p)
    assert p.classe == "telha" and abs(p.peso - 6.0 * 1.0 * 0.0005 * 7850) < 1.0


def test_telha_em_bloco_macico_sem_nome_de_painel():
    """Mercado Conceito (Tekla): "Telha cobertura" e "Telha fech externo" exportadas como bloco de 40 mm — 314 kg/m²,
    886 t na lista. Achado pela conferência da FAB-09 no dia em que ela entrou (04/11)."""
    from nucleo2d.detalhe.base import aplicar_peso_teorico
    v = [(x, y, z) for x in (0.0, 9000.0) for y in (0.0, 1000.0) for z in (0.0, 40.0)]
    f = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    p = dt.Posicao(marca="Telha cobertura", tipo_ifc="IfcPlate", perfil="Telha cobertura", vertices=v, faces=f)
    dt.analisar(p)
    p.classe = "telha"                               # como o levantamento a classifica pelo nome
    p.quantidade = 308
    aplicar_peso_teorico([p])
    assert p.peso == 0.0 and p.peso_malha > 2000.0
    assert conferir_compra_por_m2([p], []) == []
