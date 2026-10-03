# -*- coding: utf-8 -*-
"""A barra do projeto (web/etapas.js + saida/etapas_projeto.py): as seis etapas da obra (decisão de 03/10/2026),
a situação de cada uma tirada dos arquivos, os atalhos apontando para itens que existem na barra única, e a barra
presente em todas as telas de projeto."""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import etapas_projeto as E           # noqa: E402

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def _ler(*p):
    with open(os.path.join(WEB, *p), encoding="utf-8") as f:
        return f.read()


def test_seis_etapas_na_ordem_e_situacao_pelos_arquivos():
    with tempfile.TemporaryDirectory() as pasta:
        et = E.etapas("obra x", pasta, {"tipo": "ifc"})
        assert [e["nome"] for e in et] == ["Entrada", "Modelo 3D", "Comercial", "Detalhamento", "Produção", "Obra"]
        assert all(e["situacao"] == "" for e in et)
        assert et[1]["url"] == "/dividida?projeto=obra%20x&vista=3d" and et[2]["url"].startswith("/comercial?projeto=obra%20x")
        open(os.path.join(pasta, "modelo.json"), "w").write("{}")
        os.makedirs(os.path.join(pasta, "detalhamento"))
        open(os.path.join(pasta, "detalhamento", "lista-de-materiais.json"), "w").write("{}")
        os.makedirs(os.path.join(pasta, "comercial"))
        json.dump({"proposta": {"numero": "2026-001"}, "contrato": {"situacao": "minuta"},
                   "etapas": {"montagem": {"situacao": "andamento"}}}, open(os.path.join(pasta, "comercial", "comercial.json"), "w"))
        s = {e["chave"]: e["situacao"] for e in E.etapas("obra x", pasta, {"tipo": "ifc"})}
        assert s == {"entrada": "feita", "modelo": "feita", "comercial": "andamento", "detalhamento": "",
                     "producao": "andamento", "obra": "andamento"}
        json.dump({"proposta": {"numero": "2026-001"}, "contrato": {"situacao": "assinado"},
                   "etapas": {"entrega": {"situacao": "concluida"}}}, open(os.path.join(pasta, "comercial", "comercial.json"), "w"))
        s = {e["chave"]: e["situacao"] for e in E.etapas("obra x", pasta, {"tipo": "ifc"})}
        assert s["comercial"] == "feita" and s["obra"] == "feita"
        galpao = E.etapas("g", pasta, {"tipo": "galpao"})
        assert galpao[1]["url"] == "/dimensionar?projeto=g"


def test_atalhos_apontam_para_itens_da_barra_unica():
    js = _ler("barra_unica.js")
    menus = re.findall(r"^    \{ nome: '([^']+)', itens: \[", js, re.M)
    with tempfile.TemporaryDirectory() as pasta:
        for e in E.etapas("x", pasta, {}):
            for it in e["itens"]:
                if "menu" in it:
                    caminho = it["menu"]
                    assert caminho[0] in menus, (e["nome"], caminho)
                    for parte in caminho[1:]:
                        assert ("'%s'" % parte) in js, (e["nome"], caminho, parte)
                else:
                    assert it["link"].startswith("/"), it


def test_barra_em_todas_as_telas_de_projeto():
    for tela in ("dividida.html", "materiais.html", "comercial.html", "analise.html", "memorial.html", "esforcos.html", "trelicas.html"):
        assert '<script src="/etapas.js"></script>' in _ler(tela), tela
    # nos quadros 2D e 3D da área de trabalho, não (seriam duas barras)
    assert "/etapas.js" not in _ler("cad", "cad.html") and "/etapas.js" not in _ler("editor3d", "editor.html")
    js = _ler("etapas.js")
    assert "window.top !== window" in js and "'/api/projetos/' + encodeURIComponent(PROJETO) + '/etapas'" in js
    # a barra única carregada fora da área de trabalho (só pelo mapa) não monta nada
    assert "if (!document.getElementById('menus-unicos')) return;" in _ler("barra_unica.js")


def test_cartao_do_projeto_traz_as_etapas():
    from projetos import Projetos
    with tempfile.TemporaryDirectory() as raiz:
        g = Projetos(raiz)
        p = g.criar("Obra teste", tipo="ifc")
        slug = p.get("slug") or os.listdir(raiz)[0]
        r = g.resumo(slug)
        assert [e["chave"] for e in r["etapas"]] == ["entrada", "modelo", "comercial", "detalhamento", "producao", "obra"]
        assert set(r["etapas"][0]) == {"chave", "nome", "situacao", "url"}
