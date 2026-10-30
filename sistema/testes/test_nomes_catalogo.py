# -*- coding: utf-8 -*-
"""O padrão dos nomes do catálogo (FERRAMENTA · FÁBRICA N.2, 27/10: "não temos uma padronização de nomes definida").

O combinado com o usuário: polegada `1.1/4"`, espessura com 2 casas, o W com a massa em 1 casa, telha = modelo +
espessura + fabricante curto; o nome antigo gravado nas obras continua achando o mesmo item (nucleo/nomes_catalogo.py).
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo import catalogo                                     # noqa: E402
from nucleo.nomes_catalogo import chave_de_perfil, padrao       # noqa: E402
from nucleo.perfis import _chave as chave_banco, banco          # noqa: E402
from saida.detalhamento import Posicao                          # noqa: E402

#: o de-para combinado em 27/10, um caso de cada regra (antes → depois)
CASOS = [
    ("TC 12,7×0,5", "TC 12,7×0,50"),
    ("TQ 50×50×2,0", "TQ 50×50×2,00"),
    ("TC 168,3×4,5", "TC 168,3×4,50"),
    ('TC 60,3×3,0 (2")', 'TC 60,3×3,00 (2")'),
    ('TC 42,4×2,65 (1½")', 'TC 42,4×2,65 (1.1/2")'),
    ('L 1½"×1/8"', 'L 1.1/2"×1/8"'),
    ("L 50×5", "L 50×5,00"),
    ("L 40×4 (métrica)", "L 40×4,00"),
    ("L 25×2 (FF)", "L 25×2,00 (FF)"),
    ('Barra chata 2½"×1/4"', 'Barra chata 2.1/2"×1/4"'),
    ("CH 2 mm", "CH 2,00 mm"),
    ('CH 12,7 mm (1/2")', 'CH 12,70 mm (1/2")'),
    ("W 610×101", "W 610×101,0"),
    ("TP40 0,43 mm (Isoeste Metálica)", "TP 40 0,43 mm (Isoeste)"),
    ("TMTP-25 0,5 mm (Eternit (telhas metálicas))", "TMTP 25 0,50 mm (Eternit)"),
    ("LR 17 (ArcelorMittal Perfilor)", "LR 17 (Perfilor)"),
]

#: os que já estavam no padrão e não podem mudar
FICAM = ["Ue 200×75×25×2,25", "U 50×25×1,20 (FF)", 'U 4"×7,95', "W 150×13,0", 'I 3"×8,5', "HP 200×53,0",
         'L 1"×1/8"', 'L 1/2"×2,50 mm', 'Barra redonda ø 1.1/16"', "Barra redonda ø 6,3 mm", "ASTM A307 M12",
         "ISO 4.6 M12", 'ASTM F1554 Gr.36 1.1/8"', "CH 0,45 mm", 'CH 6,35 mm (1/4")', "Cr 20×30×12×0,95"]


def test_cada_caso_do_combinado_acha_o_nome_novo():
    for antes, depois in CASOS:
        it = catalogo.item(antes)
        assert it is not None, antes
        assert it.nome == depois, (antes, it.nome)


def test_os_que_ja_estavam_no_padrao_nao_mudam():
    for nome in FICAM:
        it = catalogo.item(nome)
        assert it is not None and it.nome == nome, (nome, it and it.nome)


def test_todo_o_catalogo_no_padrao_e_sem_repetir():
    itens = catalogo.itens()
    fora = [i.nome for i in itens if padrao(i.nome, i.familia, i.dados) != i.nome]
    assert not fora, fora[:10]
    assert not [i.nome for i in itens if "½" in i.nome or "¼" in i.nome or "¾" in i.nome]
    chaves = [catalogo._chave(i.nome) for i in itens]
    assert len(chaves) == len(set(chaves))
    # o W 610×101 e o W 610×101,0 eram o mesmo perfil com dois nomes
    assert [i.nome for i in itens if i.nome.startswith("W 610×101")] == ["W 610×101,0"]


def test_o_nome_antigo_de_cada_item_acha_o_mesmo_item():
    """A obra gravada antes do padrão (apelidos) abre como está: o catálogo e o banco do cálculo acham o item."""
    n = 0
    for it in catalogo.itens():
        for velho in it.dados.get("apelidos") or ():
            assert catalogo.item(velho) is it, velho
            n += 1
    assert n > 2000
    for antes, depois in CASOS:
        p = banco().get(depois)
        if p is not None:
            assert banco().get(antes) is p, antes


def test_chave_do_banco_nao_come_o_zero_do_meio():
    """A chave antiga tirava os zeros do fim do nome inteiro: "W 200×150" e "W 200×15" eram a mesma."""
    assert chave_banco("W 200×150") != chave_banco("W 200×15")
    assert chave_banco("W 360x51") == chave_banco("W 360×51,0")
    assert chave_banco('L 1½"×1/8"') == chave_banco('L 1.1/2"×1/8"')
    assert chave_banco('L 2½"×1/4"') != chave_banco('L 2"×1/4"')


def test_na_obra_antiga_a_barra_com_o_nome_novo_e_a_mesma_peca():
    """A barra lançada depois do padrão ("TQ 50×50×2,00") ao lado da gravada antes ("TQ 50×50×2,0") é a mesma marca."""
    from nucleo2d.detalhe.base import _assinatura_posicao
    assert chave_de_perfil("TQ 50×50×2,0") == chave_de_perfil("TQ 50×50×2,00")
    assert chave_de_perfil("TQ 50×50×2,0") != chave_de_perfil("TQ 50×50×3,0")
    a = Posicao(marca="P1", tipo_ifc="IfcMember", perfil="TQ 50×50×2,0", classe="tubo", L=1000.0, H=50.0, T=50.0)
    b = Posicao(marca="P2", tipo_ifc="IfcMember", perfil="TQ 50×50×2,00", classe="tubo", L=1000.0, H=50.0, T=50.0)
    assert _assinatura_posicao(a) == _assinatura_posicao(b)


def test_o_gerador_refaz_o_catalogo_igual():
    """catalogo.json sai do gerador já no padrão; regerar não volta aos nomes antigos."""
    r = subprocess.run([sys.executable, os.path.join(BASE, "dados", "gerar_catalogo.py"), "--conferir"],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, r.stdout + r.stderr
