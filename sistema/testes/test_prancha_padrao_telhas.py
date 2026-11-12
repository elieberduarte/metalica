# -*- coding: utf-8 -*-
"""A PRANCHA PADRÃO DE TELHAS (usuário, 12/11, sobre a revisão à mão da prancha 13 da ME Sooro · Sala de Compressores:
"Fiz uma revisão na prancha para deixar o projeto mais limpo… para criarmos uma prancha padrão para todas as obras" —
"Sim, é assim"; nas outras obras, escolhido por ele: sai a água inclinada e a planta das marcas vai na orientação dos
tipos). nucleo2d/pranchas._prancha_padrao_de_telhas, pelo detalhamento das telhas de verdade de duas obras:

* um quadro largo "TIPOS DE TELHA | TELHAS": a planta dos tipos e, ao lado, a planta das marcas (a FACE 1 a 0°, girada
  −90° para ficar em pé como os tipos, o título de pé); embaixo as fachadas lado a lado (no Depósito, com 7, em mais
  fileiras, sem passar de 1:125);
* à direita os detalhes (MD1, CU1), um embaixo do outro;
* a cobertura inclinada (FACES 2 E 3 a 11° na Sala, FACES 1 E 2 a 4° no Depósito) sai."""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Texto                                      # noqa: E402
from nucleo2d.pranchas import montar_pranchas                                    # noqa: E402

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_cad")
_CACHE = {}


def _prancha(arquivo):
    if arquivo not in _CACHE:
        with gzip.open(os.path.join(DADOS, arquivo), "rt", encoding="utf-8") as f:
            d = Desenho.de_dict(json.load(f))
        folhas = montar_pranchas([{"nome": "detalhamento-telhas", "desenho": d}], formato="A1")
        _CACHE[arquivo] = next(p for p in folhas if any("telha" in str(c.get("id") or c.get("titulo") or "").lower()
                                                         for c in (p.metadados.get("prancha") or {}).get("celulas") or []))
    return _CACHE[arquivo]


def _celulas(p):
    out = {}
    for c in p.metadados["prancha"]["celulas"]:
        t = str(c.get("titulo") or "")
        out[t.split(" – ")[0].strip()] = c
    return out


def _caixa(c):
    x0, y0, x1, y1 = c["caixa"]
    return x0, y0, x1, y1


def test_sala_no_arranjo_aprovado():
    p = _prancha("sala_detalhamento_telhas.json.gz")
    cel = _celulas(p)
    assert {"TIPOS DE TELHA", "FACE 1", "FACE 4", "FACE 5", "MD1", "CU1"} <= set(cel), list(cel)
    assert not any("COBERTURA (11" in str(c.get("titulo")) for c in p.metadados["prancha"]["celulas"])   # a água inclinada saiu
    textos = [str(e.texto or "") for e in p.entidades.values() if isinstance(e, Texto)]
    assert any(t.upper().startswith("TIPOS DE TELHA | TELHAS") for t in textos)                          # o quadro largo
    tipos, face1, f4, f5 = (_caixa(cel[k]) for k in ("TIPOS DE TELHA", "FACE 1", "FACE 4", "FACE 5"))
    # em cima: os tipos e, ao lado, a planta das marcas; embaixo: as fachadas lado a lado
    assert face1[0] > tipos[2] and abs(face1[3] - tipos[3]) < 1.0
    assert f4[3] < min(tipos[1], face1[1]) and abs(f4[3] - f5[3]) < 1.0 and f5[0] > f4[2]
    # à direita, os detalhes, um embaixo do outro
    md1, cu1 = _caixa(cel["MD1"]), _caixa(cel["CU1"])
    assert min(md1[0], cu1[0]) > max(face1[2], f4[2], f5[2]) and cu1[3] < md1[1]
    # a FACE 1 em pé (girada −90°), como os tipos, e o título dela de pé
    assert (face1[3] - face1[1]) > (face1[2] - face1[0])
    tit = next(e for e in p.entidades.values() if isinstance(e, Texto) and str(e.texto or "").startswith("FACE 1 – COBERTURA"))
    assert (tit.angulo or 0.0) % 360.0 == 0.0
    marcas = [e for e in p.entidades.values() if isinstance(e, Texto) and str(e.texto or "").startswith("TL")
              and (e.atributos or {}).get("cel", "").endswith("FACE 1 – COBERTURA (0°) – 100 chapas")]
    assert marcas and any(round((e.angulo or 0.0) % 360.0) in (270.0, 0.0) for e in marcas)


def test_deposito_sem_cobertura_plana():
    p = _prancha("deposito_detalhamento_telhas.json.gz")
    cel = _celulas(p)
    assert not any("COBERTURA" in str(c.get("titulo")) for c in p.metadados["prancha"]["celulas"])        # a de 4° saiu
    fachadas = [c for k, c in cel.items() if k.startswith("FACE")]
    assert len(fachadas) == 7 and all(float(c["escala"]) <= 125.0 for c in fachadas)                     # legíveis
    tipos = _caixa(cel["TIPOS DE TELHA"])
    assert all(_caixa(c)[3] < tipos[1] for c in fachadas)                                               # os tipos em cima
    assert _caixa(cel["CU1"])[0] > max(_caixa(c)[2] for c in fachadas)                                   # o detalhe à direita
