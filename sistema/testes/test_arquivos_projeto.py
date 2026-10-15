# -*- coding: utf-8 -*-
"""A aba Arquivos lista o que está no disco (15/10): todo arquivo de entrega da pasta do projeto, de qualquer pasta; os de
trabalho do programa ficam de fora; a versão mais antiga de um documento datado fica marcada."""
import os
import time

from saida import arquivos_projeto as ap


def _gravar(raiz, rel, idade=0.0):
    cam = os.path.join(raiz, *rel.split("/"))
    os.makedirs(os.path.dirname(cam), exist_ok=True)
    with open(cam, "w", encoding="utf-8") as f:
        f.write("x")
    t = time.time() - idade
    os.utime(cam, (t, t))
    return cam


def test_lista_tudo_que_e_entrega_e_marca_a_versao_anterior(tmp_path):
    r = str(tmp_path)
    for rel in ("detalhamento/romaneio.csv", "pranchas/pranchas.pdf", "analise/memorial.pdf", "ifc/modelo.ifc",
                "documentos/Relatorio-2026-10-09.pdf", "documentos/Relatorio-2026-10-14.pdf", "documentos/foto.png",
                "relatorio-solto.pdf"):
        _gravar(r, rel)
    # de trabalho: nunca entram
    for rel in ("modelo.json", "historico/modelo-1.json.gz", "backup-antes/modelo.json", "backup-antes/x.pdf",
                "documentos/.lixeira/velho.pdf", "detalhamento/dossie/foto.png", "detalhamento/miniatura.png",
                "desenhos-2d/pranchas.dxf"):
        _gravar(r, rel)
    a = ap.listar(r, lambda c: "/saida/" + os.path.relpath(c, r).replace("\\", "/"))
    nomes = {(x["pasta"], x["nome"]) for x in a}
    assert nomes == {("detalhamento", "romaneio.csv"), ("pranchas", "pranchas.pdf"), ("analise", "memorial.pdf"),
                     ("ifc", "modelo.ifc"), ("documentos", "Relatorio-2026-10-09.pdf"), ("documentos", "Relatorio-2026-10-14.pdf"),
                     ("documentos", "foto.png"), ("", "relatorio-solto.pdf")}
    por = {x["nome"]: x for x in a}
    assert por["romaneio.csv"]["rotulo"] == "Romaneio" and not por["romaneio.csv"]["documento"]
    assert por["Relatorio-2026-10-14.pdf"]["documento"] and "anterior" not in por["Relatorio-2026-10-14.pdf"]
    assert por["Relatorio-2026-10-09.pdf"]["anterior"] == "Relatorio-2026-10-14.pdf"
    assert por["pranchas.pdf"]["url"] == "/saida/pranchas/pranchas.pdf"


def test_o_mais_novo_primeiro_e_dxf_soltos_so_sem_o_zip(tmp_path):
    r = str(tmp_path)
    _gravar(r, "detalhamento/romaneio.csv", idade=100)
    _gravar(r, "pranchas/pranchas-dxf/01-localizacao.dxf", idade=50)
    novo = ap.listar(r, lambda c: c)
    assert [x["nome"] for x in novo] == ["01-localizacao.dxf", "romaneio.csv"]
    _gravar(r, "pranchas/pranchas-dxf.zip")
    assert [x["nome"] for x in ap.listar(r, lambda c: c)] == ["pranchas-dxf.zip", "romaneio.csv"]
