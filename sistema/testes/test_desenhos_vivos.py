# -*- coding: utf-8 -*-
"""O carimbo do detalhamento (desenhos_vivos.py, 28/09): quando os desenhos ficam velhos."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import desenhos_vivos as dv  # noqa: E402


class _Gerente:
    def __init__(self, raiz):
        self.raiz = raiz
        self.eixos = {"x": [0, 6000]}
        self.desenhos = []

    def _existente(self, s):
        return os.path.join(self.raiz, s)

    def ler(self, s):
        return {"eixos": self.eixos}

    def caminho_modelo(self, s):
        return os.path.join(self.raiz, s, "modelo.json")

    def listar_desenhos(self, s, contar=True):
        return self.desenhos


def test_quando_o_detalhamento_fica_velho(tmp_path):
    g = _Gerente(str(tmp_path))
    os.makedirs(tmp_path / "p" / "detalhamento")
    (tmp_path / "p" / "modelo.json").write_text("{}", encoding="utf-8")
    dv.configurar(gerente=lambda: g)
    assert dv.por_que_velho("p") == ""                                # sem detalhamento: o primeiro é pelo botão
    g.desenhos = [{"nome": "detalhamento-tesouras"}]
    assert "antes" in dv.por_que_velho("p")                           # sem carimbo
    c = dv.gravar_carimbo("p", {"detalhamento-tesouras": "g1"})
    assert dv.por_que_velho("p") == "" and c["desenhos"] == {"detalhamento-tesouras": "g1"}
    os.utime(tmp_path / "p" / "modelo.json", (1, 1))
    assert dv.por_que_velho("p") == "o modelo 3D mudou"
    dv.gravar_carimbo("p", {"detalhamento-tesouras": "g2"})
    g.eixos = {"x": [0, 7000]}
    assert dv.por_que_velho("p") == "os eixos mudaram"
    # a atualização parcial só registra as gerações: o carimbo (o que foi usado) continua o de antes
    dv.gravar_carimbo("p", {"detalhamento-terças": "g3"}, completo=False)
    assert dv.por_que_velho("p") == "os eixos mudaram"
    dv.registrar_desenho("p", "pranchas", "g4")
    d = json.loads((tmp_path / "p" / "detalhamento" / "carimbo.json").read_text(encoding="utf-8"))["desenhos"]
    assert d == {"detalhamento-tesouras": "g2", "detalhamento-terças": "g3", "pranchas": "g4"}
