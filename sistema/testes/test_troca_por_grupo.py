# -*- coding: utf-8 -*-
"""Trocar perfis por grupo (nucleo3d/troca_por_grupo.py) — a ferramenta dos estudos que o usuário pediu na revisão das
regras das tesouras (16/10): mudar de uma vez as terças (maior, cartola), os banzos e pôr cantoneira dupla na alma, "se o
cliente pede para ver uma opção diferente o ajuste é rápido". Depois da troca as treliças tocadas passam pelas regras
(regras_trelica.conferir volta vazio), a terça continua sentada no apoio e as peças novas saem sem posição."""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from nucleo3d import regras_trelica as R                                    # noqa: E402
from nucleo3d import troca_por_grupo as TG                                  # noqa: E402
from nucleo3d.geometria import base_local, malha_barra, resolver_perfil, secao   # noqa: E402
from nucleo3d.modelo import Barra, Documento                                # noqa: E402

U_BZ = "U 100×50×3,00 (FF)"
U_BZ2 = "U 150×60×3,00 (FF)"
U_AL = "U 100×50×3,00 (FF)"
L_AL = "L 40×3 (FF)"
UE_T = "Ue 150×60×20×2,00"
CR_T = "Cr 67×134×30×3,00"


def _modelo(z=0.0, x=0.0):
    """duas tesouras planas (x = x0 e x0 + 5 m), 6 m × 1 m, banzos e alma em U, e três terças por cima; `z`/`x` levam
    tudo para longe da origem (o piso longe do z = 0)"""
    doc = Documento()
    for k, x0 in enumerate((x, x + 5000.0)):
        at = {"origem": {"peca": "T%d" % k}, "marcas": {"conjunto": "T.1"}}

        def b(nome, a, c, perfil, papel, pt=None, pos=None):
            atr = dict(at, marcas=dict(at["marcas"], posicao=pos or nome, perfil=perfil))
            if pt:
                atr["papel_trelica"] = pt
            doc.add(Barra(nome=nome, inicio=(x0, a[0], z + a[1]), fim=(x0, c[0], z + c[1]), perfil=perfil, papel=papel,
                          atributos=atr))
        b("BS", (0, 1000), (6000, 1000), U_BZ, "banzo", "banzo_sup", "P1")
        b("BI", (0, 0), (6000, 0), U_BZ, "banzo", "banzo_inf", "P2")
        for y in (0, 6000):
            b("E%d" % y, (y, 0), (y, 1000), U_BZ, "banzo", "extremidade", "P3")
        for y in (1500, 3000, 4500):
            b("M%d" % y, (y, 0), (y, 1000), U_AL, "montante", "montante", "P4")
        for y0, y1 in ((0, 1500), (1500, 3000), (6000, 4500), (4500, 3000)):
            b("D%d" % y0, (y0, 1000), (y1, 0), U_AL, "diagonal", "diagonal", "P5")
    pu = resolver_perfil(U_BZ)
    pt = resolver_perfil(UE_T)
    zt = z + 1000.0 + float(pu.bf) / 2.0 + float(pt.d) / 2.0     # a terça sentada no banzo de cima (o U de alma no plano)
    for y in (200.0, 3000.0, 5800.0):
        doc.add(Barra(nome="TC", inicio=(x, y, zt), fim=(x + 5000.0, y, zt), perfil=UE_T, papel="terça",
                      atributos={"marcas": {"posicao": "P9", "perfil": UE_T}}))
    R.aplicar(list(doc.entidades.values()))                    # o modelo de partida já dentro das regras
    return doc


def _aplicar_no_doc(doc, r):
    """o que o editor faz com a resposta (remover, alterar, novas)"""
    for i in r["remover"]:
        doc.entidades.pop(i, None)
    for i, campos in r["alterar"].items():
        for k, v in campos.items():
            setattr(doc.entidades[i], k, tuple(v) if k in ("inicio", "fim") else v)
    for d in r["novas"]:
        doc.add(Barra(**{k: (tuple(v) if k in ("inicio", "fim") else v) for k, v in d.items() if k != "tipo"}))


def _barras(doc):
    return [e for e in doc.entidades.values() if isinstance(e, Barra)]


def _troca(doc, trocas):
    """a troca numa cópia, como o editor manda (o documento em dicionário), aplicada de volta no doc"""
    copia = Documento.de_dict(doc.dict())
    r = TG.aplicar(copia, trocas)
    _aplicar_no_doc(doc, r)
    return r


def test_cartola_tem_secao_no_3d_e_no_catalogo():
    from nucleo import catalogo
    p = catalogo.perfil_de(CR_T)
    assert p is not None and p.tipo == "Cr" and p.massa > 0
    pts = secao(resolver_perfil(CR_T))
    ys = [y for _x, y in pts]
    xs = [x for x, _y in pts]
    assert max(ys) - min(ys) == pytest.approx(67.0, abs=0.5)
    assert max(xs) - min(xs) == pytest.approx(134.0 + 2 * (30.0 - 3.0), abs=1.0)  # as abas de apoio para fora (a linha média do cálculo)


def test_grupos_por_papel_e_perfil():
    doc = _modelo()
    g = {x["grupo"]: x for x in TG.grupos(doc)}
    assert set(g) >= {"tercas", "banzo_sup", "banzo_inf", "montantes", "diagonais"}
    assert g["tercas"]["pecas"] == 3 and g["montantes"]["pecas"] == 6 and g["diagonais"]["pecas"] == 8
    assert all(not k.startswith("papel:extremidade") for k in g)                   # a ponta segue o banzo


@pytest.mark.parametrize("z,x", [(0.0, 0.0), (85000.0, -40000.0)])
def test_alma_em_cantoneira_dupla_e_de_volta(z, x):
    doc = _modelo(z, x)
    r = _troca(doc, [{"grupo": "montantes", "forma": "dupla", "para": L_AL},
                     {"grupo": "diagonais", "forma": "dupla", "para": L_AL}])
    bs = _barras(doc)
    pares = [b for b in bs if b.atributos.get("cantoneira_dupla")]
    pres = [b for b in bs if b.papel == "presilha"]
    assert len(pares) == 2 * 14 and len(pres) >= 2 * 14
    assert not [b for b in bs if b.papel in ("montante", "diagonal") and b.perfil == U_AL]
    assert R.conferir(bs) == []                                                  # 2.5 e o encaixe 3.1a
    # cada par: um de cada lado do plano, dentro das abas do banzo
    for t in R.trelicas(bs):
        lados = [l for b, _p in t["barras"] for i, l in t["par"].items() if i == id(b)]
        assert sorted(set(lados)) == [-1, 1]
    # as peças novas sem posição (o Numerar dá), com o conjunto da tesoura
    for d in r["novas"]:
        m = d["atributos"].get("marcas") or {}
        assert "posicao" not in m and m.get("conjunto") == "T.1"
    # e de volta: o par vira um U só, no eixo da alma, sem as presilhas
    _troca(doc, [{"grupo": "montantes", "forma": "simples", "para": U_AL},
                 {"grupo": "diagonais", "forma": "simples", "para": U_AL}])
    bs = _barras(doc)
    assert not [b for b in bs if b.atributos.get("cantoneira_dupla") or b.papel == "presilha"]
    assert len([b for b in bs if b.papel in ("montante", "diagonal")]) == 14
    m = next(b for b in bs if b.papel == "montante" and abs(b.inicio[1] - 1500) < 1 and abs(b.inicio[0] - x) < 1)
    assert m.inicio[0] == pytest.approx(x, abs=0.5)                              # no plano da tesoura
    assert R.conferir(bs) == []


def test_banzo_novo_leva_a_ponta_e_reencaixa_a_alma():
    doc = _modelo()
    _troca(doc, [{"grupo": "banzo_sup", "para": U_BZ2}, {"grupo": "banzo_inf", "para": U_BZ2}])
    bs = _barras(doc)
    assert {b.perfil for b in bs if b.atributos.get("papel_trelica") == "extremidade"} == {U_BZ2}     # 1.4
    assert R.conferir(bs) == []                                                  # 3.1: nada fura o banzo novo
    bz = next(b for b in bs if b.atributos.get("papel_trelica") == "banzo_sup")
    assert bz.atributos.get("marca_a_conferir") and bz.atributos["marcas"]["perfil"] == U_BZ2
    assert bz.atributos["trocas_de_perfil"][-1]["de"] == U_BZ


def _face_de_baixo(b):
    vs, _f = malha_barra(b)
    return min(v[2] for v in vs)


@pytest.mark.parametrize("z", [0.0, 85000.0])
def test_terca_em_cartola_fica_sentada_e_de_chapeu_para_cima(z):
    doc = _modelo(z)
    t0 = next(b for b in _barras(doc) if b.papel == "terça")
    baixo0, kg0 = _face_de_baixo(t0), TG._peso(t0)
    r = _troca(doc, [{"grupo": "tercas", "para": CR_T}])
    t1 = doc.entidades[t0.id]
    assert t1.perfil == CR_T
    assert _face_de_baixo(t1) == pytest.approx(baixo0, abs=0.5)                  # sentada no mesmo apoio
    v = base_local(t1.direcao, t1.rotacao)[1]
    assert v[2] > 0.99                                                           # o chapéu para cima
    assert TG._peso(t1) != pytest.approx(kg0)
    assert r["resumo"]["kg_depois"] != r["resumo"]["kg_antes"]
    # e um Ue maior: continua sentada
    _troca(doc, [{"grupo": "tercas", "para": "Ue 250×85×25×2,65"}])
    t2 = doc.entidades[t0.id]
    assert _face_de_baixo(t2) == pytest.approx(baixo0, abs=0.5)


def test_so_o_perfil_escolhido_do_grupo_muda():
    doc = _modelo()
    m = next(b for b in _barras(doc) if b.papel == "montante")
    m.perfil = "U 150×60×4,75 (FF)"
    _troca(doc, [{"grupo": "montantes", "de": U_AL, "para": "U 100×50×2,25 (FF)"}])
    perfis = {b.perfil for b in _barras(doc) if b.papel == "montante"}
    assert perfis == {"U 150×60×4,75 (FF)", "U 100×50×2,25 (FF)"}


def test_pedidos_errados_sao_recusados():
    from nucleo.base import ErroDeDados
    doc = _modelo()
    with pytest.raises(ErroDeDados):
        TG.aplicar(doc, [{"grupo": "tercas", "forma": "dupla", "para": L_AL}])
    with pytest.raises(ErroDeDados):
        TG.aplicar(doc, [{"grupo": "montantes", "forma": "dupla", "para": U_AL}])
    with pytest.raises(ErroDeDados):
        TG.aplicar(doc, [{"grupo": "tercas", "para": "XYZ 999"}])
    with pytest.raises(ErroDeDados):
        TG.aplicar(doc, [])


def test_rota_do_servidor():
    import app
    doc = _modelo()
    g = app.trocar_perfis_por_grupo({"documento": doc.dict()})
    assert any(x["grupo"] == "tercas" for x in g["grupos"])
    r = app.trocar_perfis_por_grupo({"documento": doc.dict(), "trocas": [{"grupo": "tercas", "para": CR_T}]})
    assert len(r["alterar"]) == 3 and not r["novas"]


def test_tesoura_e_platibanda_separadas_pelo_conjunto():
    """o banzo em U 100×50 é das tesouras (T.n) e das platibandas (P.n) no Mercado: o estudo troca um sem o outro"""
    doc = _modelo()
    for b in _barras(doc):
        if (b.atributos.get("origem") or {}).get("peca") == "T1":
            b.atributos["marcas"]["conjunto"] = "P.1"
    g = {x["grupo"]: x for x in TG.grupos(doc)}
    assert {p["tipo"] for p in g["banzo_sup"]["perfis"]} == {"T", "P"}
    _troca(doc, [{"grupo": "banzo_sup", "de": U_BZ, "tipo": "T", "para": U_BZ2}])
    por_tipo = {(b.atributos["marcas"]["conjunto"], b.perfil) for b in _barras(doc)
                if b.atributos.get("papel_trelica") == "banzo_sup"}
    assert por_tipo == {("T.1", U_BZ2), ("P.1", U_BZ)}
