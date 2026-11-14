# -*- coding: utf-8 -*-
"""O desenho "Telhas para o fornecedor" no Detalhar e nas pranchas (conferência da 0.9.4, 14/11, pelo GESTÃO N.10).

O Detalhar monta por dentro todos os grupos-base, as telhas também, e o desenho do fornecedor ia junto qualquer que fosse o
pedido: o Detalhar só das "chaparias" gravava também o das telhas (o verif_excluir via 5 desenhos em vez de 4; o
verif_detalhar_rota, 2 desenhos no 2º Detalhar). E ele não é folha de prancha: é o DXF 1:1 que vai ao fornecedor.

  1. só sai quando as telhas são pedidas (ou o pedido é tudo);
  2. a lista dos desenhos diz de onde ele veio (gerado_por = detalhamento) e que é do fornecedor: o "Marcar detalhamentos"
     do CAD marca pela origem, não pelo nome, e o diálogo das pranchas não o oferece;
  3. a limpeza do Detalhar o leva para a lixeira quando o modelo perde as telhas;
  4. a montagem das pranchas o deixa de fora, com o aviso; só ele, a montagem recusa com a mensagem."""
import gzip
import json
import os

import pytest

from nucleo2d.detalhe import telhas_fornecedor as F

RECORTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_telhas", "deposito_quimico_cumeeira.json.gz")


def _documento():
    from nucleo3d.modelo import Documento
    with gzip.open(RECORTE, "rt", encoding="utf-8") as f:
        return Documento.de_dict(json.load(f))


@pytest.mark.parametrize("grupos, sai", [
    (["chaparias"], False),          # antes: saía de carona
    (["tercas", "chaparias"], False),
    (["telhas"], True),
    (None, True),                    # tudo
    ([], True),
])
def test_o_desenho_do_fornecedor_so_sai_quando_as_telhas_sao_pedidas(grupos, sai):
    from nucleo2d import detalhar as det
    r = det.detalhar(_documento(), grupos=grupos)
    assert ("telhas_fornecedor" in r["desenhos"]) is sai, sorted(r["desenhos"])


@pytest.fixture()
def projeto(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    r = g.criar("Depósito recorte", tipo="ifc")
    s = r.get("slug") or r.get("id") or r.get("nome")
    with gzip.open(RECORTE, "rt", encoding="utf-8") as f:
        g.salvar_modelo(s, json.load(f))
    return app, g, s


def test_a_lista_diz_a_origem_e_que_e_do_fornecedor(projeto):
    app, g, s = projeto
    app.detalhar_projeto(s, {})
    lista = {d["nome"]: d for d in g.listar_desenhos(s)}
    fo = lista[app._slug(F.NOME_DESENHO)]
    assert fo.get("gerado_por") == "detalhamento" and fo.get("fornecedor") is True
    tl = next(d for n, d in lista.items() if n.startswith("detalhamento-telhas"))
    assert tl.get("gerado_por") == "detalhamento" and not tl.get("fornecedor")


def test_sem_as_telhas_no_modelo_o_desenho_do_fornecedor_vai_para_a_lixeira(projeto):
    app, g, s = projeto
    app.detalhar_projeto(s, {})
    nome = app._slug(F.NOME_DESENHO)
    assert nome in {d["nome"] for d in g.listar_desenhos(s)}
    # o modelo perde as telhas (fica o rufo)
    with gzip.open(RECORTE, "rt", encoding="utf-8") as f:
        m = json.load(f)
    ents = m["entidades"]
    m["entidades"] = [e for e in (ents if isinstance(ents, list) else ents.values()) if e.get("camada") != "Telhas"]
    g.salvar_modelo(s, m)
    r = app.detalhar_projeto(s, {})
    assert nome not in {d["nome"] for d in g.listar_desenhos(s)}
    assert any(nome in a and "lixeira" in a for a in r.get("avisos") or []), r.get("avisos")


def test_as_pranchas_deixam_de_fora_o_desenho_do_fornecedor(projeto):
    app, g, s = projeto
    r = app.detalhar_projeto(s, {})
    todos = [d["nome"] for d in r["desenhos"]]                  # como o verif_pranchas_rota: tudo o que o Detalhar fez
    nome = app._slug(F.NOME_DESENHO)
    assert nome in todos
    p = app.montar_pranchas_projeto(s, {"desenhos": todos, "formato": "A1"})
    fontes = {fo for f in g.abrir_desenho(s, p["desenho"])["metadados"]["pranchas"] for fo in (f.get("fontes") or [])}
    assert F.NOME_DESENHO not in fontes and nome not in fontes, fontes
    assert "fornecedor" in (p.get("aviso") or ""), p.get("aviso")
    # só ele: a montagem recusa e diz por quê (não um 500)
    with pytest.raises(app.ErroDeDados) as e:
        app.montar_pranchas_projeto(s, {"desenhos": [nome], "formato": "A1"})
    assert "fornecedor" in str(e.value)


def test_a_cota_especial_nao_derruba_a_montagem_das_pranchas(projeto):
    # a causa do 500 (ajustes_pranchas._pontos não conhecia a CotaEspecial: _ref None no marcar): vale para qualquer
    # desenho com ela, não só para o do fornecedor — o mesmo desenho, sem a marca do fornecedor, entra nas pranchas
    from nucleo2d.desenho import CotaEspecial, Desenho
    app, g, s = projeto
    app.detalhar_projeto(s, {"grupos": ["telhas"]})
    d = Desenho.de_dict(g.abrir_desenho(s, app._slug(F.NOME_DESENHO)))
    assert any(isinstance(e, CotaEspecial) for e in d.entidades.values())
    d.metadados.pop("fornecedor", None)
    d.nome = "Corte com cota especial"
    g.salvar_desenho(s, d.nome, d.dict())
    p = app.montar_pranchas_projeto(s, {"desenhos": [app._slug(d.nome)], "formato": "A1"})
    assert len(p["pranchas"]) == 1
