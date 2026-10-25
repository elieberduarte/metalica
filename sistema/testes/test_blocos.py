# -*- coding: utf-8 -*-
"""Os blocos (24/10; usuário: "Biblioteca da empresa" e "Como no AutoCAD"): a inserção `Bloco` e a definição em
metadados.blocos (nucleo2d/desenho.py), a biblioteca (nucleo2d/blocos.py) e as saídas — o PDF e as folhas pelo desenho
do bloco, o DXF com BLOCK/INSERT. A mesma conta da tela está em web/cad/nucleo/desenho2d.js (verif_cad_blocos)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ezdxf
import pytest

from nucleo.base import ErroDeDados
from nucleo2d.desenho import Desenho, Bloco, Linha, Texto, filhos_do_bloco
from nucleo2d import blocos, dxf_cad, pranchas

DEFS = {
    "PLACA": {"entidades": [
        {"tipo": "linha", "camada": "0", "a": [0, 0], "b": [100, 0]},
        {"tipo": "texto", "camada": "TEXTO", "posicao": [0, 10], "texto": "X", "altura": 2.5},
        {"tipo": "arco", "camada": "0", "centro": [0, 0], "raio": 10, "inicio": 0, "fim": 90},
        {"tipo": "bloco", "nome": "FURO", "posicao": [50, 0]}]},
    "FURO": {"entidades": [{"tipo": "circulo", "camada": "FURO", "centro": [0, 0], "raio": 9}]},
}


def _r(p):
    return tuple(round(v, 6) for v in p)


def test_giro_e_escala():
    b = Bloco(nome="PLACA", camada="VISTA", posicao=(1000.0, 500.0), escala=(2.0, 2.0), angulo=90.0)
    linha, texto, arco, furo = filhos_do_bloco(b, DEFS)
    assert linha.camada == "VISTA", "a camada 0 vai para a da inserção"
    assert (_r(linha.a), _r(linha.b)) == ((1000.0, 500.0), (1000.0, 700.0))
    assert _r(texto.posicao) == (980.0, 500.0) and texto.angulo == 90.0 and texto.altura == 5.0 and texto.camada == "TEXTO"
    assert (round(arco.inicio), round(arco.fim), arco.raio) == (90, 180, 20.0)
    assert _r(furo.centro) == (1000.0, 600.0) and furo.raio == 18.0, "o bloco de dentro também"


def test_espelho():
    linha, texto, arco, _f = filhos_do_bloco(Bloco(nome="PLACA", posicao=(0.0, 0.0), escala=(-1.0, 1.0)), DEFS)
    assert _r(linha.b) == (-100.0, 0.0)
    assert (round(arco.inicio), round(arco.fim)) == (90, 180), "o arco espelhado troca as pontas"
    assert texto.angulo == 0.0, "espelhado, o texto continua legível"


def test_grava_e_le_e_caixa():
    d = Desenho(nome="t", escala=1.0)
    d.metadados["blocos"] = DEFS
    d.add(Bloco(nome="PLACA", posicao=(1000.0, 500.0), escala=(2.0, 2.0), angulo=90.0))
    dd = Desenho.de_dict(d.dict())
    b = list(dd.entidades.values())[0]
    assert isinstance(b, Bloco) and b.escala == (2.0, 2.0) and b.angulo == 90.0
    (x0, y0), (x1, y1) = dd.caixa()
    assert x0 < 1000 and y1 >= 700, "a caixa conta o desenho do bloco, não só o ponto"


def test_bloco_sem_definicao_nao_quebra():
    d = Desenho(nome="t", escala=1.0)
    d.add(Bloco(nome="NAO-EXISTE", posicao=(0.0, 0.0)))
    assert d.blocos_explodidos().tamanho == 0
    with tempfile.TemporaryDirectory() as tmp:
        dxf_cad.exportar(d, os.path.join(tmp, "t.dxf"))


def test_pdf_pelo_desenho_do_bloco():
    """o ponto de inserção fora do trecho e o desenho dentro: o PDF da área leva o bloco (o DXF R12 explodido)"""
    d = Desenho(nome="t", escala=1.0)
    d.metadados["blocos"] = DEFS
    d.add(Bloco(nome="PLACA", posicao=(-80.0, 0.0), escala=(3.0, 3.0)))
    with tempfile.TemporaryDirectory() as tmp:
        r12 = d.para_dxf(1.0, texto_unicode=True).gravar(os.path.join(tmp, "r12.dxf"))
        tipos = sorted({e.dxftype() for e in ezdxf.readfile(r12).modelspace()})
        assert "LINE" in tipos and "CIRCLE" in tipos and "ARC" in tipos and "INSERT" not in tipos
        pdf = pranchas.pdf_da_area(d, os.path.join(tmp, "a.pdf"), ((100.0, -50.0), (300.0, 50.0)), 1)
        assert os.path.getsize(pdf) > 1000


def test_folhas_levam_o_bloco_para_a_prancha():
    d = Desenho(nome="Detalhamento", escala=10.0)
    d.metadados["blocos"] = DEFS
    folha = pranchas.folha_no_desenho("A3", 10.0, (0.0, 0.0))
    for e in folha.entidades.values():
        d.add(e)
    d.add(Bloco(nome="PLACA", posicao=(1000.0, 1500.0), escala=(5.0, 5.0)))
    p = pranchas.pranchas_das_folhas(d, "detalhamento")[0]
    linhas = [e for e in p.entidades.values() if isinstance(e, Linha) and _r(e.a) == (100.0, 150.0)]
    assert linhas and _r(linhas[0].b) == (150.0, 150.0), "a linha do bloco na prancha, reduzida pela escala"


def test_dxf_com_block_e_insert():
    d = Desenho(nome="t", escala=1.0)
    d.metadados["blocos"] = dict(DEFS, **{"A/B": DEFS["FURO"]})
    d.add(Bloco(nome="PLACA", posicao=(1000.0, 500.0), escala=(2.0, 2.0), angulo=90.0))
    d.add(Bloco(nome="PLACA", posicao=(0.0, 0.0)))
    d.add(Bloco(nome="A/B", posicao=(5.0, 5.0)))
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.readfile(dxf_cad.exportar(d, os.path.join(tmp, "t.dxf")))
    ins = [(i.dxf.name, _r(i.dxf.insert)[:2], i.dxf.xscale, i.dxf.rotation) for i in doc.modelspace().query("INSERT")]
    assert ("PLACA", (1000.0, 500.0), 2.0, 90.0) in ins and ("PLACA", (0.0, 0.0), 1.0, 0.0) in ins and ("A_B", (5.0, 5.0), 1.0, 0.0) in ins
    placa = doc.blocks.get("PLACA")
    assert sorted(e.dxftype() for e in placa) == ["ARC", "INSERT", "LINE", "TEXT"], "o BLOCK com o furo de dentro"
    assert [e.dxf.name for e in placa.query("INSERT")] == ["FURO"]


def test_biblioteca():
    with tempfile.TemporaryDirectory() as tmp:
        arq = os.path.join(tmp, blocos.ARQUIVO)
        assert blocos.ler(arq) == {}
        blocos.gravar(arq, "PLACA", {"entidades": DEFS["PLACA"]["entidades"] + [{"tipo": "desconhecido"}], "descricao": "placa de base"})
        lido = blocos.ler(arq)["PLACA"]
        assert len(lido["entidades"]) == 4 and lido["descricao"] == "placa de base" and lido["alterado"]
        assert blocos.rota(arq, {"acao": "gravar", "nome": "FURO", "definicao": DEFS["FURO"]})["blocos"].keys() == {"PLACA", "FURO"}
        assert blocos.rota(arq, {"acao": "excluir", "nome": "PLACA"})["blocos"].keys() == {"FURO"}
        with pytest.raises(ErroDeDados):
            blocos.gravar(arq, "VAZIO", {"entidades": []})
        with pytest.raises(ErroDeDados):
            blocos.gravar(arq, "  ", DEFS["FURO"])
