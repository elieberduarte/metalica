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


# ------------------------------------------------------------------ COB-01: a cobertura não tem fresta nem buraco
# (catálogo sistema/testes/REGRAS.md; usuário, 21/10: "o sistema fica andando em círculos" — no Posto V2 a conta do chat
# da obra achou 53 buracos e 43 frestas com toda a conferência passando)
import json
import os

import pytest

POSTO_V2 = os.path.join(os.path.dirname(__file__), "..", "..", "Projeto", "bateria", "entradas", "posto-v2-cobertura")


def _placa(doc, x0, y0, x1, y1, z=7000.0, camada="Telhas"):
    """uma chapa plana de 6 mm (a telha em planta)"""
    vs = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), (x0, y0, z + 6), (x1, y0, z + 6), (x1, y1, z + 6), (x0, y1, z + 6)]
    fs = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    doc.add(Solido(nome="Telha", camada=camada, vertices=vs, faces=fs))


def _telhado_com_vao(doc, vao=(3000.0, 3000.0, 5000.0, 5000.0)):
    """um telhado de 8 × 8 m em quatro chapas em volta de um vão (x0, y0, x1, y1)"""
    x0, y0, x1, y1 = vao
    _placa(doc, 0.0, 0.0, 8000.0, y0)
    _placa(doc, 0.0, y1, 8000.0, 8000.0)
    _placa(doc, 0.0, y0, x0, y1)
    _placa(doc, x1, y0, 8000.0, y1)


@pytest.mark.xfail(strict=True, reason="achado aberto 21/10 (COB-01): no canto da calha com o encosto lateral sobra "
                   "197 × 104 mm sem nada (o encosto começa em x 293, a calha acaba em x 96) — pedido ao dono do gerador")
def test_cob01_telhado_lancado_integro_sem_fresta_nem_buraco():
    doc = _caixa_fechada()
    assert C.cobertura_continua(doc) == []


def test_cob01_canto_da_calha_com_o_encosto_e_o_unico_achado_do_telhado_lancado():
    """enquanto o canto não é fechado no gerador: só as duas frestas dele (nada mais aparece no telhado de exemplo)"""
    doc = _caixa_fechada()
    aps = C.cobertura_continua(doc)
    assert [a["tipo"] for a in aps] == ["fresta", "fresta"]
    assert all(abs(a["ponto"][0] - 195) < 100 and (abs(a["ponto"][1] - 6038) < 100 or abs(a["ponto"][1] + 38) < 100) for a in aps)


def test_cob01_chapa_que_falta_e_buraco():
    """tirar uma chapa do meio do telhado lançado: buraco (o pedaço de telhado sem telha)"""
    doc = _caixa_fechada()
    tel = [s for s in doc.solidos if (s.atributos or {}).get("telha_lancada") and not s.atributos.get("fechamento")]
    meio = min(tel, key=lambda s: abs(sum(v[0] for v in s.vertices) / len(s.vertices) - 3500.0)
               + abs(sum(v[1] for v in s.vertices) / len(s.vertices) - 3000.0))
    doc.remover(meio.id)
    buracos = [a for a in C.cobertura_continua(doc) if a["tipo"] == "buraco"]
    assert len(buracos) == 1 and buracos[0]["area_m2"] > 0.5


def test_cob01_fresta_entre_chapas_vizinhas():
    """duas chapas com 30 mm entre elas: fresta (e não buraco — o estreito é fresta)"""
    doc = Documento()
    _placa(doc, 0.0, 0.0, 3000.0, 6000.0)
    _placa(doc, 3030.0, 0.0, 6000.0, 6000.0)
    _placa(doc, -500.0, -500.0, 6500.0, 0.0, camada="Calhas")          # as bordas fechadas: a fresta fica de dentro
    _placa(doc, -500.0, 6000.0, 6500.0, 6500.0, camada="Calhas")
    aps = C.cobertura_continua(doc)
    assert [a["tipo"] for a in aps] == ["fresta"]
    assert 5900 <= aps[0]["mm"] <= 6100
    # encostadas, nada
    doc2 = Documento()
    _placa(doc2, 0.0, 0.0, 3000.0, 6000.0)
    _placa(doc2, 3000.0, 0.0, 6000.0, 6000.0)
    assert C.cobertura_continua(doc2) == []


def test_cob01_abertura_cercada_de_platibanda_e_de_projeto():
    """o vão de 2 × 2 m com platibanda em volta (a abertura oval do Posto) é de projeto; sem a platibanda, é buraco"""
    doc = Documento()
    _telhado_com_vao(doc)
    aps = C.cobertura_continua(doc)
    assert [a["tipo"] for a in aps] == ["buraco"]
    for peca, a, b in (("P.1", (3000.0, 3000.0), (5000.0, 3000.0)), ("P.2", (5000.0, 3000.0), (5000.0, 5000.0)),
                       ("P.3", (5000.0, 5000.0), (3000.0, 5000.0)), ("P.4", (3000.0, 5000.0), (3000.0, 3000.0))):
        _platibanda(doc, peca, a, b)
    assert C.cobertura_continua(doc) == []


def test_cob01_entra_na_conferencia_e_no_verificar_apoios():
    from nucleo3d import apoios
    doc = Documento()
    _placa(doc, 0.0, 0.0, 3000.0, 6000.0)
    _placa(doc, 3030.0, 0.0, 6000.0, 6000.0)
    _placa(doc, -500.0, -500.0, 6500.0, 0.0, camada="Calhas")
    _placa(doc, -500.0, 6000.0, 6500.0, 6500.0, camada="Calhas")
    conf = C.conferir(doc)
    assert conf["contagens"]["cobertura_frestas"] == 1
    assert "1 fresta(s)" in C.avisos(conf)[0]
    import inspect
    assert '"fresta": "cobertura_fresta"' in inspect.getsource(apoios)


@pytest.mark.skipif(not os.path.isdir(POSTO_V2), reason="sem as entradas congeladas do Posto V2 (Projeto/bateria)")
def test_cob01_posto_v2_antes_e_depois_da_rodada_das_telhas():
    """a forma em que o defeito apareceu: o modelo gravado do Posto V2 antes da rodada das telhas (a conta do chat da
    obra: 53 buracos, 43 frestas — 30 buracos estreitos são as mesmas frestas, e a abertura oval é de projeto) e depois
    do c8f1e1f"""
    from nucleo3d.modelo import Documento as D

    def conta(nome):
        doc = D.de_dict(json.load(open(os.path.join(POSTO_V2, nome), encoding="utf-8")))
        c = C.conferir(doc, telha=False, soltas=False, posicao=False)["contagens"]
        return c["cobertura_buracos"], c["cobertura_frestas"]
    assert conta("antes-c8f1e1f.json") == (23, 43)
    b, f = conta("depois-c8f1e1f.json")
    assert (b, f) == (7, 17)             # o que ficou: a classificar pela obra (defeito ou vão de projeto)
