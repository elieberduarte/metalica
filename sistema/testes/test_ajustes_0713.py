# -*- coding: utf-8 -*-
"""0.7.13: peças montadas (suporte soldado, chapa de base com chumbador), furos sem uso
retirados das terças."""
import os

import pytest

from nucleo2d import detalhar as det
from nucleo2d.detalhe.base import _pecas, _fixadores, _marcas
from nucleo2d.detalhe.montagens import grupos_montados, desenho_de_montagem
from nucleo2d.desenho import Desenho
from nucleo3d.modelo import Documento


def _modelo_real():
    import json
    caminho = os.path.join(os.path.dirname(__file__), "..", "projetos", "modelos", "compressores-ar.modelo.json")
    if not os.path.exists(caminho):
        pytest.skip("modelo de exemplo do IFC não está nesta máquina")
    with open(caminho, encoding="utf-8") as f:
        return Documento.de_dict(json.load(f))


def test_pecas_montadas_e_desenho():
    doc = _modelo_real()
    pecas, _ = _pecas(doc)
    grupos = grupos_montados(pecas, _fixadores(doc), lambda m: m)
    assert grupos
    for g in grupos:
        assert len(set(g["marcas"])) >= 2 and g["instancias"] >= 1
        assert g["tipo"] in ("soldadas", "chumbamento")
    g = grupos[0]
    d = Desenho(nome="t", escala=10.0)
    ext = desenho_de_montagem(doc, g, d, 0.0, 0.0, "", {e.id: e for e in pecas})
    assert ext[2] > ext[0] and ext[3] > ext[1]
    assert len(d.vistas) == 3                              # frente, lateral e isométrica
    assert any((e.atributos or {}).get("detalhe") == "montagem" for e in d.entidades.values())


def test_furos_sem_uso_saem_das_tercas():
    doc = _modelo_real()
    r = det.retirar_furos_sem_uso(doc)
    assert r["furos"] >= 1 and r["barras"] >= 1
    assert det.retirar_furos_sem_uso(doc)["furos"] == 0   # repetir não mexe
