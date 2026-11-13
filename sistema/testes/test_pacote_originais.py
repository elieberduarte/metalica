# -*- coding: utf-8 -*-
"""As pranchas do projetista no pacote do celular (saida/pacote_celular.originais, 13/11 — usuário: "Preciso ver na versão
mobile para mostrar as pranchas originais, isso não aparece atualmente").

Antes o pacote só levava o pranchas.pdf do CAD: os PDFs que o projetista mandou (no Posto, documentos/pranchas-do-projetista-R02/,
15 folhas) não chegavam ao celular. Agora entram os de documentos/*projetista*/, 01-RECEBIDOS/ e origem/, só a revisão em
vigor; Obsoleto/, .lixeira e os relatórios soltos em documentos/ nunca."""
import json
import os
import sys

import pymupdf
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida.pacote_celular import gerar_pacote, originais        # noqa: E402

PASTA_R02 = "documentos/pranchas-do-projetista-R02"


def _pdf(caminho, paginas=1):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    doc = pymupdf.open()
    for _ in range(paginas):
        doc.new_page(width=842, height=595)
    doc.save(caminho)
    doc.close()


@pytest.fixture
def obra(tmp_path):
    """Uma obra como o Posto: as folhas R02 em vigor e tudo o que não pode ir junto."""
    p = tmp_path / "posto"
    p.mkdir()
    (p / "projeto.json").write_text(json.dumps({"nome": "Posto Teste"}), encoding="utf-8")
    d = str(p)
    for n in ("MET_PE_PHD_POSTO_LOC_01.15_R02.pdf", "MET_PE_PHD_POSTO_PLAN_INTER_02.15_R02.pdf",
              "MET_PE_PHD_POSTO_TERÇAS_11.15_R02.pdf"):
        _pdf(os.path.join(d, PASTA_R02, n))
    _pdf(os.path.join(d, PASTA_R02, "MET_PE_PHD_POSTO_CORTES_05.15_R01.pdf"))      # a mesma folha em duas revisões:
    _pdf(os.path.join(d, PASTA_R02, "MET_PE_PHD_POSTO_CORTES_05.15_R02.pdf"), 2)   # só a R02
    _pdf(os.path.join(d, "documentos/pranchas-do-projetista-R01/MET_PE_PHD_POSTO_LOC_01.15_R01.pdf"))   # pasta da revisão velha
    _pdf(os.path.join(d, "documentos/Obsoleto/pranchas-do-projetista-R00/MET_PE_PHD_POSTO_LOC_01.15_R00.pdf"))
    _pdf(os.path.join(d, PASTA_R02, "Obsoleto/MET_PE_PHD_POSTO_PASSARELA_14.15_R01.pdf"))
    _pdf(os.path.join(d, "documentos/.lixeira/pranchas-do-projetista/APAGADA_R02.pdf"))
    _pdf(os.path.join(d, "documentos/Posto-pranchas-do-projetista-x-DXF-2026-10-21.pdf"))   # relatório do sistema
    _pdf(os.path.join(d, "documentos/pranchas-do-projetista-R02/../outra/solta.pdf"))
    _pdf(os.path.join(d, "01-RECEBIDOS/MEMORIAL-DESCRITIVO-R01.pdf"))
    _pdf(os.path.join(d, "01-RECEBIDOS/Obsoleto/MEMORIAL-DESCRITIVO-R00.pdf"))
    _pdf(os.path.join(d, "origem/ESCADAS - R00.pdf"))
    with open(os.path.join(d, PASTA_R02, "vazio_R02.pdf"), "wb"):
        pass                                                                          # 0 bytes: a cópia interrompida
    return d


def test_so_a_revisao_em_vigor_e_nunca_obsoleto_ou_lixeira(obra):
    lista = originais(obra)
    rels = [a["rel"] for a in lista]
    assert not any("Obsoleto" in r or ".lixeira" in r or "R01/" in r or "_R01" in r for r in rels), rels
    assert not any("R00" in r for r in rels if not r.startswith("origem/")), rels
    assert not any(r.startswith("documentos/Posto-") or "/outra/" in r or "vazio" in r for r in rels), rels
    projetista = [a for a in lista if a["rel"].startswith(PASTA_R02)]
    # na ordem das folhas, com a folha e o título sem o começo comum
    assert [(a["folha"], a["titulo"], a["revisao"]) for a in projetista] == [
        ("01/15", "LOC", "R02"), ("02/15", "PLAN INTER", "R02"), ("05/15", "CORTES", "R02"), ("11/15", "TERÇAS", "R02")]
    assert "01-RECEBIDOS/MEMORIAL-DESCRITIVO-R01.pdf" in rels
    assert "origem/ESCADAS - R00.pdf" in rels
    assert len(lista) == 6


def test_obra_sem_originais_nao_tem_o_grupo(tmp_path):
    (tmp_path / "projeto.json").write_text("{}", encoding="utf-8")
    _pdf(str(tmp_path / "documentos" / "relatorio-2026-11-13.pdf"))
    m = gerar_pacote(str(tmp_path), str(tmp_path / "pacote"), "vazia")
    assert "originais" not in m and not os.path.exists(tmp_path / "pacote" / "originais")


def test_entram_no_pacote_e_saem_quando_saem_da_obra(obra, tmp_path):
    destino = str(tmp_path / "pacote")
    m = gerar_pacote(obra, destino, "posto")
    orig = m["originais"]
    assert m["numeros"]["originais"] == 6
    assert orig[0]["arquivo"] == "originais/01.pdf" and orig[0]["titulo"] == "LOC" and orig[0]["folha"] == "01/15"
    cortes = next(o for o in orig if o["titulo"] == "CORTES")
    assert cortes["paginas"] == 2 and cortes["nome"] == "MET_PE_PHD_POSTO_CORTES_05.15_R02.pdf"
    nomes = {a["nome"] for a in m["arquivos"]}
    for o in orig:                                   # o celular só baixa o que o manifesto lista
        assert o["arquivo"] in nomes and o["miniatura"] in nomes
    assert not any("Obsoleto" in n or "lixeira" in n for n in nomes)
    # a folha 02 foi para o Obsoleto no PC: some do pacote na próxima geração
    os.makedirs(os.path.join(obra, PASTA_R02, "Obsoleto"), exist_ok=True)
    os.replace(os.path.join(obra, PASTA_R02, "MET_PE_PHD_POSTO_PLAN_INTER_02.15_R02.pdf"),
               os.path.join(obra, PASTA_R02, "Obsoleto", "MET_PE_PHD_POSTO_PLAN_INTER_02.15_R02.pdf"))
    m2 = gerar_pacote(obra, destino, "posto")
    assert [o["titulo"] for o in m2["originais"] if o["folha"]] == ["LOC", "CORTES", "TERÇAS"]
    assert len(os.listdir(os.path.join(destino, "originais"))) == 2 * len(m2["originais"])


def test_original_novo_deixa_o_pacote_velho(obra, tmp_path):
    from celular import servidor as S
    dados = os.path.dirname(obra)
    c = S.Celular(dados, str(tmp_path / "trabalho"), porta=0, host="127.0.0.1")
    c.gerar_agora("posto")
    assert not c.velho("posto")
    _pdf(os.path.join(obra, PASTA_R02, "MET_PE_PHD_POSTO_PASSARELA_14.15_R02.pdf"))
    assert c.velho("posto")
    c.gerar_agora("posto")
    m = c._manifesto("posto")
    assert "PASSARELA" in [o["titulo"] for o in m["originais"]]
