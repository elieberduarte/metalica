# -*- coding: utf-8 -*-
"""D02 (agente usuario-desastrado, 13/11; o defeito é de 27/09): o servidor caído no "gravando os desenhos…" do Detalhar
deixava a obra SEM o desenho — o de antes já tinha ido para a lixeira e o novo ainda não estava gravado. O que foi desenhado
à mão nele ficava só na lixeira (3 cópias por desenho: depois de 3 Detalhar, perdido), e o Detalhar seguinte, sem o
desenho na pasta, não o mantinha. Agora o de antes vai para a lixeira como CÓPIA e fica no lugar até o novo ser gravado
por cima, de uma vez (Projetos.guardar_na_lixeira, usado em toda troca de desenho por outro com o mesmo nome)."""
import json
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from nucleo2d.desenho import Desenho, Linha                    # noqa: E402
from test_detalhar2d import _modelo                           # noqa: E402


class Queda(BaseException):
    """O servidor que morre no meio: nada do caminho a pega."""


def _entidades(caminho):
    with open(caminho, encoding="utf-8") as f:
        return len(json.load(f).get("entidades") or [])


def test_queda_no_meio_da_gravacao_deixa_os_desenhos_de_antes(tmp_path, monkeypatch):
    import app
    import projetos
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    s = g.criar("Obra queda", tipo="ifc")["slug"]
    g.salvar_modelo(s, _modelo().dict())
    r = app.detalhar_projeto(s, {})
    nomes = [d["nome"] for d in r["desenhos"]]
    assert len(nomes) >= 2, nomes

    # o desenhado à mão num dos desenhos (o último a ser regravado e o primeiro, para pegar a ordem que for)
    antes = {}
    for nome in (nomes[0], nomes[-1]):
        d = Desenho.de_dict(g.abrir_desenho(s, nome))
        d.add(Linha(a=(0, 0), b=(1234, 0)))
        g.salvar_desenho(s, nome, d.dict())
    for nome in nomes:
        antes[nome] = _entidades(g._caminho_desenho(s, nome))

    original = projetos.Projetos.salvar_desenho

    def cai(self, s_, nome, desenho):
        raise Queda("o servidor caiu no gravando os desenhos…")

    monkeypatch.setattr(projetos.Projetos, "salvar_desenho", cai)
    with pytest.raises(Queda):
        app.detalhar_projeto(s, {})
    monkeypatch.setattr(projetos.Projetos, "salvar_desenho", original)

    for nome in nomes:                                         # nenhum sumiu, e o desenhado à mão está lá
        caminho = g._caminho_desenho(s, nome)
        assert os.path.isfile(caminho), "%s sumiu da pasta (só na lixeira)" % nome
        assert _entidades(caminho) == antes[nome], nome


def test_guardar_na_lixeira_copia_e_deixa_no_lugar(tmp_path):
    from projetos import LIXEIRA, Projetos
    g = Projetos(str(tmp_path))
    s = g.criar("Obra")["slug"]
    d = Desenho(nome="Detalhamento – completo", escala=25.0)
    d.add(Linha(a=(0, 0), b=(100, 0)))
    g.salvar_desenho(s, d.nome, d.dict())
    g.guardar_na_lixeira(s, d.nome)
    assert os.path.isfile(g._caminho_desenho(s, d.nome))
    copias = [a for a in os.listdir(os.path.join(str(tmp_path), LIXEIRA)) if "completo" in a]
    assert len(copias) == 1
    g.guardar_na_lixeira(s, "nao-existe")                     # sem desenho: nada


def _modelo_com_telhas():
    """o recorte do Depósito Químico com as telhas das duas águas e a cumeeira (o de test_telhas_fornecedor)"""
    import gzip
    from nucleo3d.modelo import Documento
    with gzip.open(os.path.join(AQUI, "dados_telhas", "deposito_quimico_cumeeira.json.gz"), "rt", encoding="utf-8") as f:
        return Documento.de_dict(json.load(f))


# "com telhas": a carona do "Telhas para o fornecedor" (corrigida pelo CAD 2D em 14/11; era xfail estrito)
@pytest.mark.parametrize("modelo", ["sem telhas", "com telhas"])
def test_detalhar_duas_vezes_com_substituir_nao_duplica_desenhos(tmp_path, monkeypatch, modelo):
    """o verif_detalhar_rota, sem o Chrome (conferência da 0.9.4, 14/11): Detalhar tudo, depois só um grupo com
    substituir — a lista de desenhos da obra é a mesma, e o 2º Detalhar devolve só o grupo pedido. Sem telhas é a guarda
    do D02 (o de antes vai para a lixeira como cópia e o novo grava por cima: nenhum nome novo). Com telhas, o desenho
    "Telhas para o fornecedor" vinha de carona em qualquer pedido (o Detalhar monta os grupos-base por dentro)"""
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    s = g.criar("Obra substituir", tipo="ifc")["slug"]
    g.salvar_modelo(s, (_modelo() if modelo == "sem telhas" else _modelo_com_telhas()).dict())
    r = app.detalhar_projeto(s, {})
    nomes = sorted(d["nome"] for d in g.listar_desenhos(s))
    assert nomes == sorted(d["nome"] for d in r["desenhos"]) and nomes, nomes
    if modelo == "com telhas":
        assert "telhas_fornecedor" in {d["grupo"] for d in r["desenhos"]}            # o caso existe
    outro = next((d["grupo"] for d in r["desenhos"] if d["grupo"] not in ("telhas", "telhas_fornecedor")), "chaparias")
    r2 = app.detalhar_projeto(s, {"grupos": [outro], "substituir": True})
    assert sorted(d["nome"] for d in g.listar_desenhos(s)) == nomes
    assert {d["grupo"] for d in r2["desenhos"]} <= {outro}, [d["grupo"] for d in r2["desenhos"]]
