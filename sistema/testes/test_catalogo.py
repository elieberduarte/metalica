# -*- coding: utf-8 -*-
"""Catálogo de peças: famílias, busca, alternativas de troca e perfil de cálculo."""
import os
import subprocess
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo import catalogo                       # noqa: E402
from nucleo.base import ErroDeDados               # noqa: E402


def test_familias_e_resumo():
    r = catalogo.resumo()
    assert r["itens"] > 400
    for fam in ("I", "U", "Ue", "L", "tubo", "chapa", "barra_redonda", "barra_chata", "parafuso"):
        assert r["familias"].get(fam, 0) > 0, fam
    # cada item diz se veio de tabela de fabricante ou de cálculo
    assert set(r["origens"]) == {"tabela", "calculado"}
    fams = {f["familia"]: f for f in catalogo.familias()}
    assert fams["Ue"]["peca"] == "barra" and fams["chapa"]["peca"] == "chapa"
    assert "terça" in fams["Ue"]["papeis"]


def test_nomes_unicos_e_tabela_vence():
    nomes = [catalogo._chave(i.nome) for i in catalogo.itens()]
    assert len(nomes) == len(set(nomes)), "nome repetido no catálogo"
    # este Ue está na tabela do manual e também na série calculada: vale o da tabela
    it = catalogo.item("Ue 150×60×20×2,00")
    assert it is not None and it.origem == "tabela"


@pytest.mark.parametrize("texto", ["Ue 150×60×20×2,65", "ue150x60x20x2,65",
                                   "UE 150X60X20X2.65", " Ue 150×60×20×2,65 "])
def test_busca_tolerante(texto):
    assert catalogo.item(texto).nome == "Ue 150×60×20×2,65"


def test_polegada_com_fracao_nao_se_confunde():
    # ½ e ¼ têm de sobreviver à normalização, senão 2½"×1/4" vira 2"×1/4"
    a, b = catalogo.item('L 2½"×1/4"'), catalogo.item('L 2"×1/4"')
    assert a is not None and b is not None and a.nome != b.nome
    assert a.massa > b.massa


def test_buscar_por_dimensao():
    achados = [i.nome for i in catalogo.buscar("150x60")]
    assert achados and all("150" in n and "60" in n for n in achados)


def test_alternativas_vizinhas():
    atual = catalogo.item("Ue 150×60×20×2,65")
    alt = catalogo.alternativas(atual.nome, limite=8)
    assert alt and all(a["nome"] != atual.nome for a in alt)
    # só famílias que se trocam de verdade (Ue vira Ue ou U, nunca cantoneira)
    assert {a["familia"] for a in alt} <= {"Ue", "U"}
    assert any(a["mais_leve"] for a in alt) and any(not a["mais_leve"] for a in alt)
    for a in alt:
        assert a["delta_massa"] == pytest.approx(a["massa"] - atual.massa, abs=0.02)
        assert 0.5 * atual.altura - 1 <= a["altura"] <= 2.0 * atual.altura + 1


def test_alternativas_de_chapa_e_redonda():
    alt = catalogo.alternativas('CH 9,53 mm (3/8")', limite=4)
    assert alt and all(a["familia"] == "chapa" for a in alt)
    assert all(a["massa_m2"] for a in alt)
    alt = catalogo.alternativas("Barra redonda ø 16 mm", limite=4)
    assert alt and all(a["familia"] == "barra_redonda" for a in alt)


def test_alternativas_mesma_altura_e_erro():
    alt = catalogo.alternativas("Ue 200×75×20×2,65", mesma_altura=True, limite=10)
    assert alt and all(abs(a["altura"] - 200) < 1.5 for a in alt)
    with pytest.raises(ErroDeDados):
        catalogo.alternativas("perfil que não existe")


def test_perfil_de_calculo():
    from nucleo import nbr14762, nbr8800
    p = catalogo.perfil_de("Ue 200×75×20×2,65")           # tabelado
    assert p is not None and p.A > 0
    p = catalogo.perfil_de("Ue 150×75×20×2,25")           # calculado na série
    assert p is not None and p.tipo == "Ue"
    assert nbr14762.secao_do_perfil(p).A > 0
    p = catalogo.perfil_de("W 310×38,7")
    assert nbr8800.compressao(p, "ASTM A572 Gr.50", Lx=300, N_Sd=100).razao > 0
    # nome de fábrica fora do catálogo continua funcionando
    assert catalogo.perfil_de("U92X40X2.25").nome == "U 92×40×2,25 (FF)"
    assert catalogo.perfil_de("CH 9,53 mm (3/8\")") is None      # chapa não é barra


def test_arquivo_bate_com_o_gerador():
    """O catálogo gravado tem de ser o que o gerador produz — senão alguém editou à mão."""
    r = subprocess.run([sys.executable, os.path.join(BASE, "dados", "gerar_catalogo.py"), "--conferir"],
                       capture_output=True, text=True, cwd=BASE)
    assert r.returncode == 0, r.stdout + r.stderr
