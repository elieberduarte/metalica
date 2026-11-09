# -*- coding: utf-8 -*-
"""Os documentos da obra numa casa só (usuário, 09/11: "tem arquivo que vai para o OneDrive, tem arquivo que vai para o disco C:,
está bem confuso"; Briefing-documentos-da-obra.md, B1): gravar UMA vez na pasta do padrão, com a revisão anterior para
Obsoleto\\ no mesmo passo; registrar o envio em 05-ENVIADOS; a aba Arquivos lê as pastas do padrão e não lista o Obsoleto."""
import json
import os

import pytest

from saida import arquivos_projeto
from saida import documentos_obra as DO


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("METALICA_DADOS", str(tmp_path))
    return tmp_path


def test_grava_na_pasta_do_padrao_e_a_revisao_anterior_vai_para_o_obsoleto(dados, tmp_path):
    """O GN tinha 26 revisões do RESUMO lado a lado na pasta (e outra cópia no OneDrive): agora só a vigente fica"""
    r1 = DO.gravar("gn", "02", "GalpaoNovo-RESUMO-2026-11-06-rev26.pdf", dados=b"%PDF rev26")
    DO.gravar("gn", "02", "GalpaoNovo-RESUMO-2026-11-06-rev26.docx", dados=b"docx 26")
    assert r1["caminho"] == str(dados / "gn" / "02-ORCAMENTO" / "GalpaoNovo-RESUMO-2026-11-06-rev26.pdf") and r1["obsoletos"] == []
    r2 = DO.gravar("gn", "02-ORCAMENTO", "GalpaoNovo-RESUMO-2026-11-09-rev27.pdf", dados=b"%PDF rev27")
    pasta = dados / "gn" / "02-ORCAMENTO"
    assert sorted(os.listdir(pasta)) == ["GalpaoNovo-RESUMO-2026-11-06-rev26.docx", "GalpaoNovo-RESUMO-2026-11-09-rev27.pdf", "Obsoleto"]
    assert os.listdir(pasta / "Obsoleto") == ["GalpaoNovo-RESUMO-2026-11-06-rev26.pdf"] and len(r2["obsoletos"]) == 1
    # o Word leva o dele quando a revisão nova dele sai
    DO.gravar("gn", "02", "GalpaoNovo-RESUMO-2026-11-09-rev27.docx", dados=b"docx 27")
    assert sorted(os.listdir(pasta / "Obsoleto")) == ["GalpaoNovo-RESUMO-2026-11-06-rev26.docx", "GalpaoNovo-RESUMO-2026-11-06-rev26.pdf"]
    # outra variante (sem preço) e outro documento não saem do lugar
    DO.gravar("gn", "02", "GalpaoNovo-memorial-quantitativo-2026-11-09-rev27-sem-preco.pdf", dados=b"x")
    DO.gravar("gn", "02", "GalpaoNovo-memorial-quantitativo-2026-11-09-rev28.pdf", dados=b"x")
    assert "GalpaoNovo-memorial-quantitativo-2026-11-09-rev27-sem-preco.pdf" in os.listdir(pasta)


def test_a_mesma_revisao_de_novo_fica_no_lugar_e_a_origem_pode_ser_um_arquivo(dados, tmp_path):
    feito = tmp_path / "caderno.pdf"
    feito.write_bytes(b"R06")
    DO.gravar("gn", "04", "GalpaoNovo-caderno-escopo-montagem-2026-11-06-R06.pdf", origem=str(feito))
    feito.write_bytes(b"R06 de novo")
    r = DO.gravar("gn", "04", "GalpaoNovo-caderno-escopo-montagem-2026-11-06-R06.pdf", origem=str(feito), mover=True)
    assert r["obsoletos"] == [] and open(r["caminho"], "rb").read() == b"R06 de novo" and not feito.exists()
    r = DO.gravar("gn", "04", "GalpaoNovo-caderno-escopo-montagem-2026-11-09-R07.pdf", dados=b"R07")
    assert [os.path.basename(c) for c in r["obsoletos"]] == ["GalpaoNovo-caderno-escopo-montagem-2026-11-06-R06.pdf"]


def test_so_as_pastas_do_padrao(dados):
    with pytest.raises(ValueError):
        DO.gravar("gn", "Projeto/OBRAS", "x-2026-11-09-rev1.pdf", dados=b"x")
    with pytest.raises(ValueError):
        DO.gravar("gn", "02", "sub/x.pdf", dados=b"x")
    with pytest.raises(ValueError):
        DO.gravar("gn", "02", "x.pdf")


def test_o_documento_aberto_no_word_fica_com_o_aviso(dados, monkeypatch):
    DO.gravar("gn", "02", "GN-RESUMO-2026-11-06-rev1.docx", dados=b"1")
    real = os.replace

    def preso(a, b):
        if a.endswith("rev1.docx"):
            raise PermissionError("aberto")
        return real(a, b)
    monkeypatch.setattr(os, "replace", preso)
    r = DO.gravar("gn", "02", "GN-RESUMO-2026-11-09-rev2.docx", dados=b"2")
    assert r["obsoletos"] == [] and "rev1.docx" in r["aviso"]


def test_registrar_envio_copia_para_05_enviados_com_o_registro(dados):
    a = DO.gravar("gn", "04", "GN-caderno-escopo-montagem-2026-11-06-R06.pdf", dados=b"R06")["caminho"]
    import datetime
    r = DO.registrar_envio("gn", [a], "Prestador — orçamento: montagem", datetime.date(2026, 11, 9), meio="WhatsApp")
    assert r["pasta"].endswith(os.path.join("05-ENVIADOS", "2026-11-09 Prestador — orçamento- montagem"))
    assert os.path.isfile(a)                                                            # o original fica onde está
    r2 = DO.registrar_envio("gn", [a], "Prestador — orçamento: montagem", datetime.date(2026, 11, 9))
    assert [os.path.basename(c) for c in r2["copiados"]] == ["GN-caderno-escopo-montagem-2026-11-06-R06 (2).pdf"]
    reg = json.load(open(os.path.join(r["pasta"], "envio.json"), encoding="utf-8"))["envios"]
    assert len(reg) == 2 and reg[0]["meio"] == "WhatsApp" and reg[0]["de"] == [os.path.join("04-EXECUCAO", os.path.basename(a))]


def test_a_aba_arquivos_le_as_pastas_do_padrao_sem_o_obsoleto(dados):
    DO.gravar("gn", "02", "GN-RESUMO-2026-11-06-rev1.pdf", dados=b"1")
    DO.gravar("gn", "02", "GN-RESUMO-2026-11-09-rev2.pdf", dados=b"2")
    DO.gravar("gn", "interno", "figura-do-chat.png", dados=b"png")
    DO.gravar("gn", "01", "LEIA-ME.md", dados="recebido")
    lista = arquivos_projeto.listar(str(dados / "gn"), lambda c: c)
    nomes = {a["nome"]: a for a in lista}
    assert set(nomes) == {"GN-RESUMO-2026-11-09-rev2.pdf", "figura-do-chat.png", "LEIA-ME.md"}
    assert nomes["GN-RESUMO-2026-11-09-rev2.pdf"]["documento"] and nomes["GN-RESUMO-2026-11-09-rev2.pdf"]["descricao"] == "Orçamento"
    assert set(arquivos_projeto.PASTAS_DO_PADRAO) == set(DO.NOMES_DAS_PASTAS)
