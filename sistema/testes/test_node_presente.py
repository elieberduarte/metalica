# -*- coding: utf-8 -*-
"""O Node tem de estar na máquina que confere o sistema (revisão independente de 14/11, reforço B).

Os testes que rodam os módulos da tela (web/) pelo Node pulam quando ele falta — `skipif(shutil.which("node") is None)`
ou `pytest.skip` —, e a conferência (antes_de_publicar.py) só olha o código de saída do pytest: sem o Node eles saíam
pulados em silêncio, e a conferência passava sem conferir a tela. Este teste NÃO pula: falha e diz quais arquivos
seriam pulados. Vale para todos os testes com Node do projeto, os de hoje e os que vierem (a lista é achada no texto
dos arquivos, não escrita aqui)."""
import os
import re
import shutil

AQUI = os.path.dirname(os.path.abspath(__file__))

#: o jeito de os testes chamarem o Node: shutil.which("node"), ou "node" no começo da linha de comando do subprocess
_USA_NODE = re.compile(r"""which\(\s*["']node["']\s*\)|\[\s*["']node["']\s*,""")


def arquivos_com_node():
    out = []
    for nome in sorted(os.listdir(AQUI)):
        if nome.startswith("test_") and nome.endswith(".py") and nome != os.path.basename(__file__):
            with open(os.path.join(AQUI, nome), encoding="utf-8", errors="replace") as f:
                if _USA_NODE.search(f.read()):
                    out.append(nome)
    return out


def test_a_lista_dos_testes_com_node_e_achada():
    """a busca acha os testes com Node que existem (se o jeito de chamar mudar, este teste avisa antes de a lista
    ficar vazia e o de baixo passar sem olhar nada)"""
    achados = arquivos_com_node()
    for nome in ("test_volta_do_3d_montagem.py", "test_cota_mm_inteiro.py", "test_arestas_3d.py"):
        assert nome in achados, nome
    assert len(achados) >= 9, achados                          # 9 em 14/11/2026


def test_o_node_esta_instalado():
    assert shutil.which("node") is not None, (
        "o Node não está no PATH: estes testes seriam PULADOS e a conferência passaria sem conferir a tela — "
        "instalar o Node (nodejs.org) antes de conferir: " + ", ".join(arquivos_com_node()))
