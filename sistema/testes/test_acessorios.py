# -*- coding: utf-8 -*-
"""Biblioteca de ligações e acessórios (0.8.30): todos os tipos montam com os padrões e
passam na verificação (menos o agulhamento da Sooro, que é acusado pela esbeltez de propósito),
pesos e furos conferidos à mão, desenho sem texto fora da moldura, classificação das peças
reais das obras, e as ligações geradas no modelo lançado chegando ao detalhamento."""
import collections
import math
import os
import re
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo import acessorios as A                   # noqa: E402
from nucleo.base import ErroDeDados                   # noqa: E402


def test_todos_os_tipos_montam():
    ids = [t["id"] for t in A.lista()]
    assert len(ids) >= 20 and len(set(ids)) == len(ids)
    cats = {c for c, _n in A.CATEGORIAS}
    for t in A.lista():
        assert t["categoria"] in cats, t["id"]
        r = A.montar(t["id"])
        assert r["svg"].startswith("<svg") and "viewBox" in r["svg"], t["id"]
        if t["verifica"]:
            v = r["verificacao"]
            assert v and v["verificacoes"], t["id"]
            assert not v["indeterminada"], (t["id"], [x.get("observacao") for x in v["verificacoes"] if x.get("indeterminada")])
            if t["id"] != "agulhamento_rigido":
                assert v["ok"], (t["id"], [(x["titulo"], x["razao"]) for x in v["verificacoes"] if not x["ok"]])


def test_agulhamento_da_sooro_acusa_esbeltez():
    r = A.montar("agulhamento_rigido")
    ruins = [x["titulo"] for x in r["verificacao"]["verificacoes"] if not x["ok"]]
    assert ruins == ["Esbeltez da barra comprimida"]
    assert any("200" in n for n in r["notas"])
    # com cantoneira maior, passa
    assert A.montar("agulhamento_rigido", {"cantoneira": "L 2'' X 1/8''"})["verificacao"]["ok"]


def test_cadeirinha_pecas_e_pesos_a_mao():
    r = A.montar("suporte_terca_cadeirinha")
    chapa, base, par = r["pecas"]
    # 150 × 145 × 4,75 menos 4 oblongos de 13,5 × 25,5 (M12 + 1,5 mm; +12 mm de rasgo)
    w, c = 13.5, 25.5
    area = 150 * 145 - 4 * (w * (c - w) + math.pi * w * w / 4)
    assert chapa["peso_unit"] == pytest.approx(area * 4.75 * 7.85e-6, abs=1e-3)
    assert base["peso_unit"] == pytest.approx(153 * 44 * 3.0 * 7.85e-6, abs=1e-3)
    assert par["qtd"] == 4 and "M12" in par["descricao"]
    assert chapa["furos"] == "4× oblongo 14×26"


def test_regra_da_furacao_da_fabrica_na_nota():
    r = A.montar("suporte_terca_cadeirinha")
    assert any("50 mm na vertical" in n for n in r["notas"])


def test_esforco_maior_reprova():
    r = A.montar("suporte_terca_cadeirinha", {}, {"R_Sd": 60.0})
    assert not r["verificacao"]["ok"]


def test_parametro_invalido_avisa():
    with pytest.raises(ErroDeDados):
        A.montar("tipo_que_nao_existe")
    with pytest.raises(ErroDeDados):
        A.montar("suporte_terca_cadeirinha", {"parafuso": "M99"})


def test_desenho_texto_dentro_da_moldura():
    """O texto entra na caixa do desenho: nenhum <text> começa fora do viewBox."""
    for tid in ("suporte_terca_cadeirinha", "contravento_tirante", "apoio_tesoura_concreto", "placa_base_engastada"):
        svg = A.montar(tid)["svg"]
        x0, y0, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split())
        for x, y in re.findall(r'<text [^>]*x="([-\d.]+)" y="([-\d.]+)"', svg):
            assert x0 - 1 <= float(x) <= x0 + w + 1 and y0 - 1 <= float(y) <= y0 + h + 1, (tid, x, y)


def test_classificacao_das_pecas_reais():
    c = A.classificar_peca
    assert c("suporte_terca", "PLATE 150x145x5", "4x OBL 25x13", "4x M12 x 35") == "suporte_terca_cadeirinha"
    assert c("suporte_terca", "PLATE 153x44x3", "", "") == "suporte_terca_cadeirinha"
    assert c("suporte_terca", "PLATE 270x120x6", "2x Ø17", "1x M16 x 40") == "suporte_terca_chapa"
    assert c("castanha", "PLATE 200x76x6", "1x Ø17", "1x M16 x 40") == "contravento_tirante"
    assert c("suporte_agulhamento", "PLATE 130x50x3", "2x OBL 13x25", "") == "agulhamento_rigido"
    assert c("gancho", "FE RED 3/8''", "", "") == "agulhamento_diagonal"
    assert c("chumbador", "FE RED 3/4''", "", "") == "chumbador_gancho"
    assert c("chapa", "PLATE 400x120x13", "2x Ø21", "6x porca/chumbador") == "apoio_tesoura_concreto"
    assert c("telha", "TELHA TP40", "", "") is None


def test_exemplos_das_obras(tmp_path):
    import json
    d = tmp_path / "obra" / "detalhamento"
    d.mkdir(parents=True)
    json.dump({"projeto": {"nome": "Obra X"}, "posicoes": [
        {"marca": "P1", "nome": "CH1", "perfil": "PLATE 150x145x5", "classe": "Chapa", "comprimento": 150, "largura": 145,
         "espessura": 4.8, "furos": "4x OBL 25x13", "parafusos": "4x M12 x 35", "quantidade": 12, "peso": 0.7}],
        "conjuntos": []}, open(d / "lista-de-materiais.json", "w", encoding="utf-8"))
    json.dump({"tipos": {"P1": "suporte_terca"}, "tipos_conjuntos": {}}, open(d / "nomes.json", "w", encoding="utf-8"))
    ex = A.exemplos_das_obras(str(tmp_path))
    assert ex["suporte_terca_cadeirinha"][0]["obra"] == "Obra X" and ex["suporte_terca_cadeirinha"][0]["qtd"] == 12


# ------------------------------------------------------------ ligações no modelo lançado

@pytest.fixture(scope="module")
def lancado():
    from nucleo3d import lancamento as L
    ex = L.eixos_do_desenho(L.malha_de_eixos((150.0, 150.0), "5x6000", "15000", escala=100))
    return L.lancar(ex, {"sistema": "treliçado"})


def test_ligacoes_geradas_no_lancamento(lancado):
    s = lancado["resumo"]["ligacoes"]
    doc = lancado["doc"]
    n_tercas = len({round(b.inicio[1]) for b in doc.barras if b.papel == "terça" and b.atributos.get("vao") == 1})
    assert s["suportes_terca"] == 6 * n_tercas                 # um por cruzamento terça × tesoura
    assert s["apoios_tesoura"] == 12 and s["chumbadores"] == 48
    assert s["parafusos"] == 4 * s["suportes_terca"] + 4 * s["apoios_tesoura"]
    marcas = collections.Counter((c.atributos or {}).get("marca") for c in doc.chapas)
    assert marcas["CH7"] == marcas["CH8"] == s["suportes_terca"] and marcas["CH5"] == marcas["CH6"] == 12
    # a chapa em pé do suporte tem os 4 oblongos da regra da fábrica (terça < 200 mm: 50 × 60)
    ch7 = next(c for c in doc.chapas if c.atributos.get("marca") == "CH7")
    ys = sorted({round(f["y"]) for f in ch7.furos}); xs = sorted({round(f["x"]) for f in ch7.furos})
    assert len(ch7.furos) == 4 and (ys[1] - ys[0], xs[1] - xs[0]) in ((50, 60), (100, 60))
    # suportes e apoio da tesoura no conjunto da tesoura; chapa de topo no do pilar
    conj_tes = {b.atributos["marcas"]["conjunto"] for b in doc.barras if b.papel == "banzo"}
    conj_pil = {b.atributos["marcas"]["conjunto"] for b in doc.barras if b.papel == "pilar"}
    assert {c.atributos["marcas"]["conjunto"] for c in doc.chapas if c.atributos.get("marca") in ("CH6", "CH7", "CH8")} == conj_tes
    assert {c.atributos["marcas"]["conjunto"] for c in doc.chapas if c.atributos.get("marca") == "CH5"} == conj_pil
    # o pilar termina na chapa de topo
    pil = next(b for b in doc.barras if b.papel == "pilar")
    ch5 = min((c for c in doc.chapas if c.atributos.get("marca") == "CH5"),
              key=lambda c: math.dist(c.origem[:2], max(pil.inicio, pil.fim, key=lambda p: p[2])[:2]))
    assert max(pil.inicio[2], pil.fim[2]) == pytest.approx(ch5.origem[2], abs=0.5)


def test_parafusos_e_chumbadores_no_detalhamento(lancado):
    """O detalhamento conta os parafusos que atravessam cada chapa e reconhece o chumbador
    (a barra paramétrica não é mais tomada por chapa)."""
    from nucleo2d.detalhe.base import _pecas
    from nucleo2d.detalhe.montagens import grupos_montados
    doc = lancado["doc"]
    pecas, acessorios = _pecas(doc)
    assert acessorios.get("BOLT (A307) 12x25") and acessorios.get("BOLT (A325) 16x50")
    grupos = grupos_montados(pecas, (), lambda m: m)
    assert any(g["tipo"] == "chumbamento" for g in grupos)
