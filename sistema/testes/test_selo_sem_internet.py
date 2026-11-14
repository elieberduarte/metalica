# -*- coding: utf-8 -*-
"""Sem internet, o selo da obra compartilhada no Controle diz a frase do programa, não o texto do Windows (14/11/2026,
GESTÃO · CHATS N.10 pela medição do CONTROLE N.2).

Antes: "☁ Obra compartilhada · você é Editor — sem conexão com a nuvem do Metálica ([WinError 10061] Nenhuma conexão pôde
ser feita porque a máquina de destino as recusou)" — o erro do urllib (obra_compartilhada._pedir) ia cru para a tela do
Fernando. Agora (controle.js, textoDoSelo): "— sem internet: 3 apontamentos guardados aqui; sobem quando a conexão voltar";
o detalhe técnico fica só no balão (title). Com internet, o selo de sempre.

Roda a função de verdade do controle.js no Node (sem DOM: ela só monta o texto)."""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

JS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "producao", "controle.js"))
WIN = "sem conexão com a nuvem do Metálica ([WinError 10061] Nenhuma conexão pôde ser feita porque a máquina de destino as r)"


def _funcao(fonte, nome):
    i = fonte.index(f"function {nome}(")
    j = fonte.index("\n  }\n", i)
    return fonte[i:j + 4]


def _rodar(casos):
    node = shutil.which("node")
    if not node:
        pytest.skip("sem o Node nesta máquina")
    fonte = open(JS, encoding="utf-8").read()
    prog = ("const n = (v) => Number(v).toLocaleString('pt-BR'); const horaBR = (s) => String(s).slice(11, 16);\n"
            + _funcao(fonte, "textoDoSelo") + "\n"
            + f"console.log(JSON.stringify({json.dumps(casos, ensure_ascii=False)}.map(textoDoSelo)));\n")
    with tempfile.TemporaryDirectory() as d:
        arq = os.path.join(d, "selo.mjs")
        open(arq, "w", encoding="utf-8").write(prog)
        r = subprocess.run([node, arq], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_sem_internet_frase_do_programa():
    tres, nenhum, um = _rodar([{"papel_nome": "Editor", "pendentes": 3, "erro": WIN},
                               {"papel_nome": "Editor", "pendentes": 0, "erro": WIN},
                               {"papel_nome": "Editor", "pendentes": 1, "erro": WIN}])
    for s in (tres, nenhum, um):
        assert "WinError" not in s["texto"] and "máquina de destino" not in s["texto"], s["texto"]
        assert "sem internet" in s["texto"]
        assert "WinError 10061" in s["dica"]                 # o detalhe fica no balão, para o suporte
    assert tres["texto"] == "☁ Obra compartilhada · você é Editor — sem internet: 3 apontamentos guardados aqui; sobem quando a conexão voltar"
    assert nenhum["texto"].endswith("— sem internet: os apontamentos ficam guardados aqui e sobem quando a conexão voltar")
    assert um["texto"].endswith("— sem internet: 1 apontamento guardado aqui; sobe quando a conexão voltar")


def test_com_internet_o_selo_de_sempre():
    em_dia, fila, recusou = _rodar([{"papel_nome": "Leitor", "pendentes": 0, "erro": "", "quando": "2026-11-14T09:51:00"},
                                    {"papel_nome": "Editor", "pendentes": 2, "erro": ""},
                                    {"papel_nome": "Editor", "pendentes": 0, "erro": "a nuvem recusou o pedido (500)"}])
    assert em_dia["texto"] == "☁ Obra compartilhada · você é Leitor · em dia com a nuvem (09:51)"
    assert fila["texto"] == "☁ Obra compartilhada · você é Editor · 2 apontamentos esperando a internet"
    assert recusou["texto"].endswith("— a nuvem recusou o pedido (500)")    # os outros recados da nuvem seguem como estão
