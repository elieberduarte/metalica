# -*- coding: utf-8 -*-
"""A PRANCHA PADRÃO DE TELHAS (usuário, 12/11, sobre a revisão à mão da prancha 13 da ME Sooro · Sala de Compressores:
"Fiz uma revisão na prancha para deixar o projeto mais limpo… para criarmos uma prancha padrão para todas as obras" —
"Sim, é assim"; nas outras obras, escolhido por ele: sai a água inclinada e a planta das marcas vai na orientação dos
tipos). nucleo2d/pranchas._prancha_padrao_de_telhas, pelo detalhamento das telhas de verdade de duas obras:

* à esquerda o quadro "TIPOS DE TELHA | TELHAS": a planta dos tipos e, ao lado, a planta das marcas (a FACE 1 a 0°,
  girada −90° para ficar em pé como os tipos, o título de pé); embaixo os detalhes (a MD1 e, ao lado, a CU1) — rodada 2,
  12/11 ("Tentar encaixar esse detalhe aqui em baixo", "Esse levar para o lado");
* à direita as fachadas, uma embaixo da outra ("Esses dois levar para a lateral"); no Depósito, com 7, as pequenas lado a
  lado, sem passar de 1:125 nem a planta dos tipos de 1:250;
* a relação dos parafusos de telha no quadro de baixo ("Colocar a relação de parafusos aqui");
* a cobertura inclinada (FACES 2 E 3 a 11° na Sala, FACES 1 E 2 a 4° no Depósito) sai.

Os dados são o detalhamento das telhas das duas obras (o da Sala com o forro de cotas nas pontas e a TL18)."""
import gzip
import json
import os
import re
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
    assert {"TIPOS DE TELHA", "FACE 1", "FACE 4", "FACE 5", "MD1", "CU1", "RELAÇÃO DE PARAFUSOS DAS TELHAS"} <= set(cel), list(cel)
    assert not any("COBERTURA (11" in str(c.get("titulo")) for c in p.metadados["prancha"]["celulas"])   # a água inclinada saiu
    textos = [str(e.texto or "") for e in p.entidades.values() if isinstance(e, Texto)]
    assert any(t.upper().startswith("TIPOS DE TELHA | TELHAS") for t in textos)                          # o quadro da esquerda
    tipos, face1, f4, f5 = (_caixa(cel[k]) for k in ("TIPOS DE TELHA", "FACE 1", "FACE 4", "FACE 5"))
    md1, cu1, paraf = _caixa(cel["MD1"]), _caixa(cel["CU1"]), _caixa(cel["RELAÇÃO DE PARAFUSOS DAS TELHAS"])
    # em cima: os tipos e, ao lado, a planta das marcas
    assert face1[0] > tipos[2] and abs(face1[3] - tipos[3]) < 1.0
    # embaixo deles, a MD1 e, ao lado, a CU1
    assert md1[3] < min(tipos[1], face1[1]) and cu1[0] > md1[2] and abs(cu1[3] - md1[3]) < 1.0
    # à direita de tudo, as fachadas, uma embaixo da outra
    assert min(f4[0], f5[0]) > max(face1[2], cu1[2]) and f5[3] < f4[1]
    assert all(float(cel[k]["escala"]) <= 125.0 for k in ("FACE 4", "FACE 5"))
    # o detalhe do beiral (exemplo A, 1:20) embaixo das fachadas, na coluna da direita
    beiral = next(c for k, c in cel.items() if k.startswith("DETALHE DO BEIRAL"))
    bb = _caixa(beiral)
    assert bb[3] < f5[1] and bb[0] > max(face1[2], cu1[2])
    assert any(t.startswith("ESC. 1:20") for t in textos)
    # o corte da cobertura (13/11, exemplo B) e o detalhe da cumeeira também na coluna da direita, embaixo das fachadas
    corte = next(c for k, c in cel.items() if k.startswith("CORTE DA COBERTURA"))
    cume = next(c for k, c in cel.items() if k.startswith("DETALHE DA CUMEEIRA"))
    for c_ in (corte, cume):
        cx_ = _caixa(c_)
        assert cx_[3] < f5[1] and cx_[0] > max(face1[2], cu1[2]), c_["titulo"]
    assert float(corte["escala"]) <= 100.0 and float(cel["FACE 4"]["escala"]) <= 125.0
    # a relação dos parafusos no quadro de baixo, abaixo de tudo
    assert paraf[3] < min(md1[1], cu1[1], bb[1], _caixa(corte)[1], _caixa(cume)[1])
    assert any(t.startswith("OA ") for t in textos) and any(t.startswith('Costura 7/8"') for t in textos)
    # a FACE 1 em pé (girada −90°), como os tipos, e o título dela de pé
    assert (face1[3] - face1[1]) > (face1[2] - face1[0])
    tit = next(e for e in p.entidades.values() if isinstance(e, Texto) and str(e.texto or "").startswith("FACE 1 – COBERTURA"))
    assert (tit.angulo or 0.0) % 360.0 == 0.0
    # a TL que continua a multidobra na legenda (o detalhe dela diz "telha complementar TL18")
    assert any(t.startswith("TL18") for t in textos) and not any("MD1-C" in t for t in textos)


def test_forro_girado_sem_numero_em_cima_do_nome():
    """o forro girado para a prancha: o número da cota de cada ponta não cai em cima de nenhum nome TL (a linha da cota
    no meio, o número fixo de um lado e o nome do outro giram juntos)"""
    p = _prancha("sala_detalhamento_telhas.json.gz")
    face1 = next(c for c in p.metadados["prancha"]["celulas"] if str(c.get("titulo")).startswith("FACE 1"))
    ents = [e for e in p.entidades.values() if (e.atributos or {}).get("cel") == face1["id"]]
    from nucleo2d.desenho import Cota
    cotas = [e for e in ents if isinstance(e, Cota) and e.texto == "960"]
    nomes = [e for e in ents if isinstance(e, Texto) and e.texto == "TL2"]
    assert 4 <= len(cotas) <= 10 and len(nomes) > 50, (len(cotas), len(nomes))
    for c in cotas:
        assert c.texto_pos is not None
        d = min(((n.posicao[0] - c.texto_pos[0]) ** 2 + (n.posicao[1] - c.texto_pos[1]) ** 2) ** 0.5 for n in nomes)
        assert d > 2.5, (c.texto_pos, d)                                   # mm de papel


def test_deposito_sem_cobertura_plana():
    p = _prancha("deposito_detalhamento_telhas.json.gz")
    cel = _celulas(p)
    assert not any("– COBERTURA" in str(c.get("titulo")) for c in p.metadados["prancha"]["celulas"])      # a de 4° saiu
    fachadas = [c for k, c in cel.items() if k.startswith("FACE")]
    assert len(fachadas) == 7 and all(float(c["escala"]) <= 125.0 for c in fachadas)                     # legíveis
    tipos = _caixa(cel["TIPOS DE TELHA"])
    assert float(cel["TIPOS DE TELHA"]["escala"]) <= 250.0                                              # os tipos também
    assert all(_caixa(c)[0] > tipos[2] for c in fachadas)                                               # à direita
    assert _caixa(cel["CU1"])[3] < tipos[1]                                                            # o detalhe embaixo
    assert "RELAÇÃO DE PARAFUSOS DAS TELHAS" in cel
    # o corte da cobertura (sem multidobra: as retas do Depósito) e a cumeeira, à direita, sem os tipos a 1:500
    corte = next(c for k, c in cel.items() if k.startswith("CORTE DA COBERTURA"))
    assert _caixa(corte)[0] > tipos[2] and float(corte["escala"]) <= 250.0
    assert any(k.startswith("DETALHE DA CUMEEIRA") for k in cel)


def test_chamada_do_canto_girada_sem_linhas_encavaladas():
    """a chamada do canto do forro ("CANTO 45° – corte na obra / TL2 – 960 (ponta cortada) / TL16 – 960 / TL17 – 670"),
    girada com a planta das marcas e reduzida de 1:50 para 1:125: as linhas de pé saíam umas em cima das outras (o
    reespaçamento das pilhas de texto só via as deitadas)"""
    p = _prancha("sala_detalhamento_telhas.json.gz")
    face1 = next(c for c in p.metadados["prancha"]["celulas"] if str(c.get("titulo")).startswith("FACE 1"))
    ents = [e for e in p.entidades.values() if isinstance(e, Texto) and (e.atributos or {}).get("cel") == face1["id"]]
    cantos = [e for e in ents if str(e.texto or "").startswith("CANTO 45°")]
    assert len(cantos) == 4
    linhas = [e for e in ents if re.match(r"^TL\d+ – \d+", str(e.texto or ""))]
    for c in cantos:
        da = [e for e in linhas if abs((e.angulo or 0.0) - (c.angulo or 0.0)) < 1e-3
              and ((e.posicao[0] - c.posicao[0]) ** 2 + (e.posicao[1] - c.posicao[1]) ** 2) ** 0.5 < 15.0]
        pilha = [c] + da
        assert len(pilha) >= 3, [e.texto for e in pilha]
        for i, a in enumerate(pilha):
            for b in pilha[i + 1:]:
                d = ((a.posicao[0] - b.posicao[0]) ** 2 + (a.posicao[1] - b.posicao[1]) ** 2) ** 0.5
                assert d >= 1.2 * a.altura, (a.texto, b.texto, d)          # uma linha de letra, ao menos, entre elas
