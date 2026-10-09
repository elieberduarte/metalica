# -*- coding: utf-8 -*-
"""O Detalhar completo tira a família que não sai mais do modelo (o "detalhamento-agulhamentos" do Vicente Residence
ficou da rodada em que o concreto do TQS entrava como aço, e as pranchas o montavam — 09/10); o desenho com o mesmo
começo de nome que não foi o Detalhar que fez fica, e a rodada de só algumas famílias não apaga as outras."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Linha                    # noqa: E402
from test_detalhar2d import _modelo                           # noqa: E402


def test_familia_que_nao_sai_mais_vai_para_a_lixeira(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    s = g.criar("Obra limpeza", tipo="ifc")["slug"]
    g.salvar_modelo(s, _modelo().dict())

    def desenho(nome, gerado):
        d = Desenho(nome=nome, escala=25.0)
        d.add(Linha(a=(0, 0), b=(100, 0)))
        if gerado:
            d.metadados["gerado_por"] = "detalhamento"
        g.salvar_desenho(s, nome, d.dict())

    desenho("detalhamento-agulhamentos", True)                 # a família velha
    desenho("detalhamento-meu", False)                         # feito à mão, com o mesmo começo de nome
    r = app.detalhar_projeto(s, {"grupos": ["chapas"]})        # só uma família: não mexe nas outras
    nomes = {d["nome"] for d in g.listar_desenhos(s, contar=False)}
    assert "detalhamento-agulhamentos" in nomes and "detalhamento-meu" in nomes
    r = app.detalhar_projeto(s, {})
    nomes = {d["nome"] for d in g.listar_desenhos(s, contar=False)}
    assert "detalhamento-agulhamentos" not in nomes, nomes
    assert "detalhamento-meu" in nomes
    assert all(d["nome"] in nomes for d in r["desenhos"])      # os de agora ficam
    assert any("agulhamentos" in str(a) for a in r.get("avisos") or [])


def test_celula_tipica_das_tercas_leva_as_marcas():
    """A célula "TÍPICO U…" das terças sem furo leva as marcas das terças: o clique nela acha as peças no 3D (o
    "TÍPICO U75X40X2.25" do Depósito Químico não achava nada, 09/10)."""
    from nucleo3d.modelo import Documento, Barra
    from nucleo2d import detalhar as det
    doc = Documento(nome="tercas")
    for i, (pos, L) in enumerate((("T1", 4000.0), ("T2", 5000.0), ("T2", 5000.0))):
        b = Barra(inicio=(0.0, i * 1500.0, 0.0), fim=(L, i * 1500.0, 0.0), perfil="U75X40X2.25", papel="terca", nome=pos)
        b.atributos = {"marcas": {"posicao": pos, "perfil": "U75X40X2.25"}, "tipo_ifc": "IfcMember"}
        doc.add(b)
    r = det.detalhar(doc, grupos=["barras"], regra_tercas=False, converter=False,
                     nomes={"tipos": {"T1": "terca", "T2": "terca"}})
    tipicas = [e for d in r["desenhos"].values() for e in d.entidades.values()
               if str((e.atributos or {}).get("conjunto", "")).startswith("TÍPICO")]
    assert tipicas, "sem célula típica"
    marcas = {m for e in tipicas for m in str(e.atributos.get("posicao", "")).split(" / ") if m}
    assert {"T1", "T2"} <= marcas, marcas
