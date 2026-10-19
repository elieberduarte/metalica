# -*- coding: utf-8 -*-
"""A conferência da cobertura (nucleo3d/conferencia_3d.cobertura — as regras da cobertura aprovadas pelo usuário no
Mercado Hermes, 19/10/2026: "está aprovado o modelo ficou íntegro, pode tornar regra"): toda borda de telhado fechada
(calha, rufo, fechamento, parede ou o telhado de cima), telha encostada em parede com rufo, e nenhuma chapa de calha ou
rufo passando por dentro de peça."""
from nucleo3d import conferencia_3d as C
from nucleo3d import telhas_cobertura as T
from nucleo3d.modelo import Barra, Documento, Solido


def _terca(doc, x, z, y0=0.0, y1=6000.0):
    b = Barra(inicio=(x, y0, z), fim=(x, y1, z), perfil="U 100×40×2,65 (FF)", papel="terça", camada="Terças")
    b.atributos = {"origem": {"sigla": "TC1"}}
    doc.add(b)


def _platibanda(doc, peca, a, b, z_inf=6600.0, z_sup=8600.0):
    for z in (z_inf, z_sup):
        br = Barra(inicio=(a[0], a[1], z), fim=(b[0], b[1], z), perfil="U 100×50×3,00 (FF)", papel="banzo",
                   camada="Platibanda", rotacao=270.0)
        br.atributos = {"origem": {"peca": peca}, "conjunto": peca}
        doc.add(br)


def _caixa_fechada(lados=("P.1", "P.2", "P.3", "P.4")):
    """um telhado de 5 % (x 0 → 7000, y 0 → 6000) com platibanda nos lados pedidos"""
    doc = Documento()
    for i in range(6):
        _terca(doc, i * 1400.0, 7000.0 + i * 1400.0 * 0.05)
    cantos = {"P.1": ((-200.0, -200.0), (-200.0, 6200.0)), "P.2": ((-200.0, 6200.0), (7200.0, 6200.0)),
              "P.3": ((7200.0, 6200.0), (7200.0, -200.0)), "P.4": ((7200.0, -200.0), (-200.0, -200.0))}
    for p in lados:
        _platibanda(doc, p, *cantos[p])
    T.lancar(doc)
    return doc


def test_telhado_com_platibanda_em_volta_esta_integro():
    """calha na borda baixa, encosto na alta e nos lados, capas em meia-esquadria: nada a apontar"""
    doc = _caixa_fechada()
    assert C.cobertura(doc) == []


def test_borda_sem_platibanda_fica_aberta():
    """sem a platibanda da borda alta (x 7000), a borda fica aberta (sem calha, rufo, fechamento nem parede)"""
    doc = _caixa_fechada(("P.1", "P.2", "P.4"))
    aps = C.cobertura(doc)
    abertas = [a for a in aps if a["tipo"] == "borda_aberta"]
    assert abertas and all(abs(a["ponto"][0] - 7000.0) < 200.0 for a in abertas)
    assert abertas[0]["mm"] >= 5000


def test_telha_encostada_na_parede_sem_rufo():
    """a borda alta encostada num sólido (a parede de concreto) sem rufo: sem_rufo — a regra do encosto em parede"""
    doc = _caixa_fechada(("P.1", "P.2", "P.4"))
    x0, x1, y0, y1, z0, z1 = 7050.0, 7200.0, -200.0, 6200.0, 6000.0, 9000.0
    vs = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    fs = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
    doc.add(Solido(nome="Parede", camada="3 Arquitetura", vertices=vs, faces=fs))
    aps = C.cobertura(doc)
    assert [a["tipo"] for a in aps] == ["sem_rufo"]


def test_rufo_atravessando_peca():
    """uma barra passando por dentro da capa da platibanda: rufo_choque"""
    doc = _caixa_fechada()
    capa = [s for s in doc.solidos if (s.atributos or {}).get("rufo") == "capa" and s.atributos["painel"] == "P.2"][0]
    z = max(v[2] for v in capa.vertices) - 3.0
    doc.add(Barra(inicio=(3000.0, 5800.0, z), fim=(3000.0, 6600.0, z), perfil="U 100×50×3,00 (FF)", papel="viga",
                  camada="Teste"))
    aps = C.cobertura(doc)
    assert any(a["tipo"] == "rufo_choque" and "capa da P.2" in a["texto"] for a in aps)
