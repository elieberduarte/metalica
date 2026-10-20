# -*- coding: utf-8 -*-
"""O rodapé do desenvolvimento diz de onde o código saiu (20/10/2026: "v0.8.65 dev" havia nove dias e ~318 commits,
porque o número só sobe quando a conferência da noite cria a versão): a última versão + os commits depois dela + o
commit atual, como o git describe; fora do git (o programa instalado), nada."""
import re
import tempfile

import versao


def test_descricao_dev_no_repositorio():
    d = versao.descricao_dev(validade=0)
    assert d is not None
    assert d["base"] == versao.VERSAO
    assert isinstance(d["commits"], int) and d["commits"] >= 0
    assert re.fullmatch(r"[0-9a-f]{7,}", d["commit"])
    assert re.fullmatch(r"\d\d/\d\d \d\d:\d\d", d["data"])
    assert isinstance(d["alterado"], bool)


def test_descricao_dev_fora_do_git():
    assert versao.descricao_dev(tempfile.mkdtemp(), validade=0) is None
