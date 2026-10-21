# -*- coding: utf-8 -*-
"""O link de instalação da tela das licenças (licencas_dev.convite, 21/10 — o usuário: "um link direto para enviar para o
usuário baixar o sistema já com a chave ativada"): cria a coluna do convite se o banco não a tem, gera o código uma vez
(o mesmo link a cada clique) e devolve o endereço da página do serviço."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import licencas_dev as L                                    # noqa: E402


class BancoFalso:
    def __init__(self, com_coluna):
        self.com_coluna = com_coluna
        self.licencas = {"MTL-AAAA-BBBB-CCCC": {"chave": "MTL-AAAA-BBBB-CCCC", "pessoa": "Andrey", "convite": None}}
        self.comandos = []

    def sql(self, sql, params=None):
        self.comandos.append(sql)
        if sql.startswith("SELECT convite FROM licencas"):
            if not self.com_coluna:
                raise L.ErroLicencas("no such column: convite")
            return []
        if sql.startswith("ALTER TABLE licencas ADD COLUMN convite"):
            self.com_coluna = True
            return []
        if sql.startswith("CREATE UNIQUE INDEX"):
            return []
        if sql.startswith("SELECT chave, pessoa, convite FROM licencas WHERE chave = ?"):
            l = self.licencas.get(params[0])
            return [dict(l)] if l else []
        if sql.startswith("UPDATE licencas SET convite = ?"):
            self.licencas[params[1]]["convite"] = params[0]
            return []
        if sql.startswith("INSERT INTO eventos"):
            return []
        raise AssertionError("SQL inesperado: " + sql)


@pytest.mark.parametrize("com_coluna", [False, True])
def test_link_de_instalacao(monkeypatch, com_coluna):
    b = BancoFalso(com_coluna)
    monkeypatch.setattr(L, "_sql", b.sql)
    monkeypatch.setattr(L, "_quem", lambda: "teste")
    r = L.convite("MTL-AAAA-BBBB-CCCC")
    assert r["link"].startswith("https://metalica-licencas.elieber-lucas.workers.dev/convite/") and r["pessoa"] == "Andrey"
    codigo = r["link"].rsplit("/", 1)[1]
    assert 12 <= len(codigo) <= 40 and all(c.isalnum() or c in "-_" for c in codigo)   # o que a rota do serviço aceita
    assert any(c.startswith("ALTER TABLE") for c in b.comandos) == (not com_coluna)
    assert L.convite("MTL-AAAA-BBBB-CCCC")["link"] == r["link"]                         # o mesmo link a cada clique
    with pytest.raises(L.ErroLicencas, match="não encontrada"):
        L.convite("MTL-ZZZZ-ZZZZ-ZZZZ")
