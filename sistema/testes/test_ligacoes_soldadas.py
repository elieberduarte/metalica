# -*- coding: utf-8 -*-
"""As ligações soldadas de prédio (nucleo3d/ligacoes3d.py, 29/10/2026): as típicas da 902 do Edifício Administrativo da
Hora Certa (AKMX, EN 1993-1-8), casos A–C aprovados pelo usuário — a viga soldada na face do apoio com a cantoneira
80×80×8 × 200 de montagem embaixo; os enrijecedores do pilar nas mesas da viga; a placa de topo do pilar que termina;
a placa de transição (com mísulas sobre viga). Medidas e cotas da obra: topo do aço a +4.930 (z do piso acabado 905,17)."""
import pytest

from nucleo3d import ligacoes3d as LG
from nucleo3d.geometria import resolver_perfil
from nucleo3d.modelo import Barra, Documento

TOPO = 4930.0


def _b(doc, a, b, perfil, papel, nome, rot=0.0):
    e = Barra(nome=nome, inicio=a, fim=b, perfil=perfil, papel=papel, rotacao=rot, camada="Teste")
    e.atributos = {"funcao": papel, "origem": {"peca": nome}}
    doc.add(e)
    return e


def _no():
    """P19 do 1º pav: W530×138 com a alma em x (rot 0); a W530×66 chega pela mesa (ao longo de x) e a W410×60 pela alma
    (ao longo de y); a W250×17,9 apoiada na alma da W530×66 e a W530×66 de mesma altura na outra"""
    doc = Documento()
    hv = float(resolver_perfil("W 530×66,0").d)
    zv = TOPO - hv / 2.0
    P = _b(doc, (17950.0, 7.0, -672.0), (17950.0, 7.0, TOPO), "W 530×138,0", "pilar", "P19-1 pilar")
    Vm = _b(doc, (24350.0, 7.0, zv), (17950.0, 7.0, zv), "W 530×66,0", "viga", "V1.20 viga")
    hw = float(resolver_perfil("W 410×60,0").d)
    Va = _b(doc, (17950.0, 7.0, TOPO - hw / 2.0), (17950.0, 8552.0, TOPO - hw / 2.0), "W 410×60,0", "viga", "V1.30 viga")
    hs = float(resolver_perfil("W 250×17,9").d)
    Vs = _b(doc, (21000.0, 7.0, TOPO - hs / 2.0), (21000.0, 4000.0, TOPO - hs / 2.0), "W 250×17,9", "viga", "V1.40 viga")
    Vi = _b(doc, (22000.0, 7.0, zv), (22000.0, -4000.0, zv), "W 530×66,0", "viga", "V1.41 viga")
    return doc, P, Vm, Va, Vs, Vi


def _novas(r, nome):
    return [n for n in r["novas"] if n["nome"] == nome]


def test_viga_na_mesa_do_pilar_soldada_com_cantoneira_de_montagem():
    doc, P, Vm, *_ = _no()
    r = LG.aplicar(doc, "viga_soldada_cantoneira", [Vm.id, P.id])
    L = _novas(r, "Cantoneira de apoio de montagem")
    assert len(L) == 1 and "80" in L[0]["perfil"]
    # a viga cortada na face da mesa do pilar (d/2 = 274,5 do eixo), soldada nele na obra, penetração total
    corte = r["alterar"][Vm.id]["cortes_fim"][0]
    assert abs(abs(corte["ponto"][0]) - float(resolver_perfil("W 530×138,0").d) / 2.0) < 1.0
    sold_v = r["alterar"][Vm.id]["atributos"]["soldas"]
    assert any(s["tipo"] == "penetracao" and s["local"] == "obra" for s in sold_v.values())
    assert r["alterar"][P.id]["atributos"]["soldas"]                 # o pilar também sabe das soldas
    # a cantoneira embaixo da viga, encostada na face (as abas: 80 para fora da face e 80 para baixo do fundo)
    doc2 = Documento.de_dict({"entidades": r["novas"]})
    from nucleo3d.geometria import malha_barra
    v, _f = malha_barra(next(iter(doc2.entidades.values())))
    zs, xs = [q[2] for q in v], [q[0] for q in v]
    fundo = TOPO - float(resolver_perfil("W 530×66,0").d)
    assert abs(max(zs) - fundo) < 1.0 and abs(min(zs) - (fundo - 80.0)) < 1.0
    face = 17950.0 + float(resolver_perfil("W 530×138,0").d) / 2.0
    assert abs(min(xs) - face) < 1.0 and abs(max(xs) - (face + 80.0)) < 1.0


def test_viga_sobre_viga_com_cantoneira_e_de_mesma_altura_so_a_solda():
    doc, P, Vm, Va, Vs, Vi = _no()
    r = LG.aplicar(doc, "viga_soldada_cantoneira", [Vs.id, Vm.id])
    assert len(_novas(r, "Cantoneira de apoio de montagem")) == 1           # a W250 pendurada na alma da W530
    r2 = LG.aplicar(doc, "viga_soldada_cantoneira", [Vi.id, Vm.id])
    assert not _novas(r2, "Cantoneira de apoio de montagem")                # a W530 na W530: não cabe (902: só a solda)
    assert r2["alterar"][Vi.id]["recortes"]                                 # as mesas recortadas


def test_enrijecedores_so_para_a_viga_da_mesa_e_placa_de_topo_no_pilar_que_termina():
    doc, P, Vm, Va, *_ = _no()
    r = LG.aplicar(doc, "enrijecedores_pilar", [P.id, Vm.id, Va.id])
    e = _novas(r, "Enrijecedor do pilar")
    assert len(e) == 4 and all(abs(x["espessura"] - 12.5) < 1e-6 for x in e)  # 2 mesas × 2 lados; a W410 chega pela alma
    r = LG.aplicar(doc, "enrijecedores_pilar", [P.id, Vm.id, Va.id], {"topo_livre": True})
    assert len(_novas(r, "Enrijecedor do pilar")) == 2                       # a mesa de cima fica com a placa de topo
    t = LG.aplicar(doc, "placa_topo_pilar", [P.id])
    pl = _novas(t, "Placa de topo do pilar")
    assert len(pl) == 1 and abs(pl[0]["espessura"] - 12.5) < 1e-6
    assert abs(t["alterar"][P.id]["recorte_fim"] - 12.5) < 1e-6             # o pilar desce a espessura da placa


def test_placa_de_transicao_sobre_viga_com_misulas_e_na_troca_de_perfil():
    doc = Documento()
    hv = float(resolver_perfil("W 530×66,0").d)
    V = _b(doc, (17000.0, 1161.0, TOPO - hv / 2.0), (19000.0, 1161.0, TOPO - hv / 2.0), "W 530×66,0", "viga", "V2.10 viga")
    Pc = _b(doc, (17943.0, 1161.0, TOPO), (17943.0, 1161.0, TOPO + 4450.0), "W 530×138,0", "pilar", "P19-3 pilar")
    r = LG.aplicar(doc, "placa_transicao_pilar", [Pc.id, V.id])
    assert len(_novas(r, "Placa de transição")) == 1 and len(_novas(r, "Mísula da transição")) == 2
    assert abs(r["alterar"][Pc.id]["recorte_inicio"] - 16.0) < 1e-6
    Pb = _b(doc, (0.0, 0.0, -672.0), (0.0, 0.0, TOPO), "W 610×174,0", "pilar", "P20-2 pilar")
    Pa = _b(doc, (0.0, 0.0, TOPO), (0.0, 0.0, TOPO + 4400.0), "W 530×138,0", "pilar", "P20-3 pilar")
    r = LG.aplicar(doc, "placa_transicao_pilar", [Pa.id, Pb.id])
    pl = _novas(r, "Placa de transição")
    assert len(pl) == 1 and not _novas(r, "Mísula da transição")
    # do tamanho do maior (o W610) + 50
    xs = [q[0] for q in pl[0]["contorno"]]
    assert abs(max(xs) - min(xs) - (float(resolver_perfil("W 610×174,0").bf) + 50.0)) < 1.0


def test_lote_numera_uma_vez_e_a_recusada_nao_para_as_outras():
    """o prédio tem ~800 ligações: o lote gera todas e numera no fim (uma a uma, o `aplicar` numerava o modelo inteiro a
    cada ligação — mais de 10 min por ligação no modelo de 4.651 peças sem marcas)"""
    doc, P, Vm, Va, Vs, Vi = _no()
    r = LG.aplicar_lote(doc, [("viga_soldada_cantoneira", [Vm.id, P.id], {}),
                              ("viga_soldada_cantoneira", [Va.id, P.id], {}),
                              ("enrijecedores_pilar", [P.id, Vm.id, Va.id], {"topo_livre": True}),
                              ("enrijecedores_pilar", [P.id, Va.id], {}),            # pela alma só: recusada
                              ("placa_topo_pilar", [P.id], {})], numerar_tudo=True)
    assert len(r["ligacoes"]) == 4 and len(r["recusadas"]) == 1
    assert all(((n.get("atributos") or {}).get("marcas") or {}).get("posicao") for n in r["novas"])
    # numerar_tudo: a viga de fora das ligações também ganha marca
    assert ((r["alterar"].get(Vs.id, {}).get("atributos") or {}).get("marcas") or {}).get("posicao")
    # a cantoneira e o enrijecedor sabem da solda com o pilar, e o pilar com eles
    sold_p = r["alterar"][P.id]["atributos"]["soldas"]
    assert len(sold_p) >= 3


def test_os_tipos_novos_aparecem_na_lista_da_tela():
    ids = {t["id"] for t in LG.tipos()}
    assert {"viga_soldada_cantoneira", "enrijecedores_pilar", "placa_topo_pilar", "placa_transicao_pilar"} <= ids
