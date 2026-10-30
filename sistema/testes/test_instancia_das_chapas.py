# -*- coding: utf-8 -*-
"""A chapa soldada sem instância vai para a instância da peça em que encosta (Hora Certa · Galpão Existente, 29/10).

Os 5 pilares W530 da Ampliação tinham `marcas.instancia` (AMP-P1…P5), as chapas soldadas neles não: o conjunto PL13 saía
"1 × 3.964,9 kg" com os 5 pilares a 20 m um do outro na mesma prancha, e o DP.3 com os 5 banzos juntos.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from nucleo3d import geometria as geo  # noqa: E402
from nucleo2d.detalhar import _instancias_pelo_grupo  # noqa: E402


def _caixa(nome, x0, y0, z0, dx, dy, dz, posicao, instancia=None):
    s = geo.prisma([(x0, y0, z0), (x0 + dx, y0, z0), (x0 + dx, y0 + dy, z0), (x0, y0 + dy, z0)], (0, 0, dz),
                   nome=nome, camada="Peças", material="Aço")
    m = {"conjunto": "PL13", "posicao": posicao}
    if instancia:
        m["instancia"] = instancia
    s.atributos = {"tipo_ifc": "IfcPlate" if nome.startswith("CH") else "IfcColumn", "marcas": m}
    return s


def _pilares(chapa_na_chapa=False):
    lista = []
    for k in range(3):
        x = 5000.0 * k                                    # 5 m entre pilares: não se tocam
        lista.append(_caixa("W530", x, 0, 0, 200, 530, 11900, "PL13.1", "AMP-P%d" % (k + 1)))
        lista.append(_caixa("CH2", x - 9.5, 100, 6000, 9.5, 200, 300, "CH2"))           # soldada na mesa
        lista.append(_caixa("CH24", x - 150, -100, -32, 500, 800, 32, "CH24"))          # placa de base, sob o pilar
        if chapa_na_chapa:
            lista.append(_caixa("CH35", x - 109.5, 150, 6100, 100, 100, 9.5, "CH35"))   # soldada na CH2, não no pilar
    return lista


def test_chapas_sem_instancia_vao_para_o_pilar_em_que_encostam():
    r = _instancias_pelo_grupo(_pilares())
    assert r is not None
    inst, n, unidade, aviso = r
    assert n == 3 and aviso == ""
    assert dict(unidade) == {"PL13.1": 1, "CH2": 1, "CH24": 1}
    assert len(inst) == 3


def test_chapa_soldada_na_chapa_tambem():
    inst, n, unidade, _ = _instancias_pelo_grupo(_pilares(chapa_na_chapa=True))
    assert n == 3 and dict(unidade) == {"PL13.1": 1, "CH2": 1, "CH24": 1, "CH35": 1}


def test_chapa_solta_longe_de_tudo_mantem_o_comportamento_de_antes():
    lista = _pilares() + [_caixa("CH9", 90000, 0, 0, 100, 100, 10, "CH9")]
    assert _instancias_pelo_grupo(lista) is None


def test_sem_instancia_nenhuma_nada_muda():
    lista = [_caixa("W530", 0, 0, 0, 200, 530, 11900, "PL13.1"), _caixa("CH2", -9.5, 100, 6000, 9.5, 200, 300, "CH2")]
    assert _instancias_pelo_grupo(lista) is None
