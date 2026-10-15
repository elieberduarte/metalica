# -*- coding: utf-8 -*-
"""A listagem dos desenhos lê o desenho grande pelos bytes (sem decodificar o JSON): vale para o JSON compacto que o
_gravar_json grava desde 05/10 e para o com espaços do editor (15/10: as pranchas do Vicente saíam com 0 objetos e 0 folhas
e "DXF de todas as pranchas" dizia que o projeto não tinha pranchas)."""
import json
import os

import projetos


def _desenho(n):
    return {"nome": "Pranchas", "unidade": "mm", "escala": 1.0, "camadas": {},
            "entidades": {"e%d" % i: {"id": "e%d" % i, "tipo": "linha", "camada": "0", "texto": "x" * 60} for i in range(n)},
            "vistas": [{"nome": "Folha 1"}], "metadados": {"pranchas": [{"titulo": "Prancha 01"}, {"titulo": "Prancha 02"}]}}


def test_desenho_grande_compacto_e_com_espacos(tmp_path, monkeypatch):
    monkeypatch.setattr(projetos, "DESENHO_GRANDE", 1024)          # força o caminho dos bytes
    d = _desenho(200)
    for nome, texto in (("compacto", json.dumps(d, ensure_ascii=False, separators=(",", ":"))),
                        ("espacos", json.dumps(d, ensure_ascii=False))):
        cam = os.path.join(str(tmp_path), nome + ".desenho.json")
        with open(cam, "w", encoding="utf-8") as f:
            f.write(texto)
        c = projetos._ler_cabecalho_do_desenho(cam)
        assert (c["titulo"], c["entidades"], c["pranchas"], c["vistas"]) == ("Pranchas", 200, 1, ["Folha 1"]), nome
