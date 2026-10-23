# -*- coding: utf-8 -*-
"""A passarela de manutenção pela planta dela (nucleo3d/passarela.py; Posto CB, folha 14, 23/10/2026 — o jeito aprovado
pelo usuário: piso a +7,60, a borda de dentro encostada no PAINEL, o pilarete do CH9 sobre a telha, o guarda-corpo só
nas bordas soltas, os pórticos em balanço)."""
import math

from nucleo3d import passarela as PS
from nucleo3d.modelo import Barra, Documento


def _ret(x0, y0, w, h):
    return {"tipo": "polilinha", "fechada": True, "camada": "m",
            "vertices": [[x0, y0, 0], [x0 + w, y0, 0], [x0 + w, y0 + h, 0], [x0, y0 + h, 0]]}


def _planta():
    """uma faixa de 1.200 × 6.000 ao longo de x = 0 (o painel), 4 travessas, 2 pilaretes com o CH9 na borda de fora e um
    pórtico de 1.200 saindo da estrutura em x = 1.200"""
    e = [{"tipo": "hachura", "camada": "piso", "contornos": [[[0, 0, 0], [1200, 0, 0], [1200, 6000, 0], [0, 6000, 0]]]}]
    e += [_ret(40, y, 1120, 40) for y in (500, 2000, 3500, 5000)]
    for y in (1500, 4500):
        e += [_ret(1100, y - 20, 100, 40), _ret(1100, y - 50, 100, 100)]
    e.append(_ret(0, 3000, 1200, 80))
    return e


def test_le_a_planta_da_passarela():
    r = PS.ler(_planta(), (-5000, -5000, 10000, 10000))
    assert len(r["piso"]) == 4 and len(r["travessas"]) == 4 and len(r["pilaretes"]) == 2 and len(r["porticos"]) == 1


def test_monta_a_passarela():
    doc = Documento()
    painel = Barra(nome="p", inicio=(-30.0, -500.0, 6000.0), fim=(-30.0, 6500.0, 6000.0), perfil="U 100×40×2,25 (FF)", papel="banzo")
    doc.add(painel)
    tercas = [Barra(nome="t", inicio=(x, -500.0, 7300.0), fim=(x, 6500.0, 7300.0), perfil="U 100×40×2,25 (FF)", papel="terça")
              for x in (600.0, 1800.0)]
    for t in tercas:
        doc.add(t)
    postas, chapas, avisos = [], [], []

    def barra(p0, p1, perfil, papel, camada, conjunto=None, rot=0.0, origem=None):
        b = Barra(nome=perfil, inicio=tuple(p0), fim=tuple(p1), perfil=perfil, papel=papel, camada=camada, rotacao=rot)
        b.atributos = {"origem": dict(origem or {})}
        doc.add(b)
        postas.append(b)
        return b
    lido = PS.ler(_planta(), (-5000, -5000, 10000, 10000))
    n = PS.lancar(doc, lido, lambda q: q, 7600.0, [painel], tercas, barra, "ASTM A36", chapas, avisos)
    assert n["longarinas"] == 4 and n["travessas"] == 4 and n["pilaretes"] == 2 and n["ch9"] == 2 and n["porticos"] == 1
    # o piso por cima de tudo: o topo a +7,60
    piso = next(c for c in chapas if c.nome.startswith("Piso"))
    assert abs(piso.origem[2] + piso.espessura - 7600.0) < 1e-6
    # o pilarete do CH9 (em cima da telha: as terças + 40 + a borracha + o CH9) até o fundo da longarina
    pil = [b for b in postas if b.papel == "pilar"]
    z_telha = 7300.0 + 50.0 + 40.0
    assert all(abs(min(b.inicio[2], b.fim[2]) - (z_telha + 5.0 + 4.76)) < 1.0 for b in pil)
    assert all(abs(max(b.inicio[2], b.fim[2]) - (7600.0 - 6.35 - 100.0)) < 1.0 for b in pil)
    # o guarda-corpo: nas três bordas soltas, nunca na que encosta no painel (x = 0)
    tubos = [b for b in postas if b.papel == "corrimao"]
    assert len(tubos) == 3 * 3 and not any(abs(b.inicio[0] - 20.0) < 1.0 and abs(b.fim[0] - 20.0) < 1.0 for b in tubos)
    assert {round(b.inicio[2] - 7600.0) for b in tubos} == {504, 804, 1104}
