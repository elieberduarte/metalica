# -*- coding: utf-8 -*-
"""A cumeeira com pernas de 500 em todas as obras e o desenvolvido da multidobra no mm de cima (DET-03).

Sala de Compressores (ME Sooro, IFC do TecnoMETAL), 12/11/2026. O chat da obra perguntou ao usuário: "Para o 2D sair igual
à relação, o programa precisa mudar para todas as obras. Confirma?" Resposta: "Sim: 500 e 2.224".
- A cumeeira de telha sai com pernas de 500 + 500 (a chapa aberta de 1.000), qualquer que seja a dobra (Sala 157,2°,
  Depósito 171,6°). Antes: o menor de 300/500 que cobrisse a perna modelada (CU1 300 + 300). O 1º commit (9254571) leu
  os "50 cm" como o total (250 + 250); o usuário corrigiu no mesmo dia: "o desenvolvimento da cumeeira é 50cm para cada
  lado".
- A multidobra MD1 tem 2.223,2 mm desenvolvidos por fora: o 2D, a lista e os textos diziam 2.223 ("desenvolvida: ext. 2223
  mm", "MD1: 2223"); a relação de fabricação já dizia 2.224. Pela DET-03 (mm inteiro, o MAIOR), 2.224. É a 1ª reincidência
  da DET-03 (a regra é de 26/10, nas cotas; o desenvolvido da telha ficou de fora).

Os dados são um recorte do modelo da Sala: uma multidobra MD1 (12 peças), as terças e longarinas em volta e uma cumeeira
(as duas pernas) — testes/dados_telhas/sala_compressores_md1.json.gz."""
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.detalhe import telhas as T                      # noqa: E402
from nucleo3d.modelo import Documento                         # noqa: E402

RECORTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_telhas", "sala_compressores_md1.json.gz")


def _doc():
    with gzip.open(RECORTE, "rt", encoding="utf-8") as f:
        return Documento.de_dict(json.load(f))


def _pecas(doc):
    return [e for e in doc.entidades.values() if getattr(e, "vertices", None)]


def _textos(d):
    ents = list(d.entidades.values()) if isinstance(d.entidades, dict) else list(d.entidades)
    return [getattr(e, "texto", "") or "" for e in ents]


def test_multidobra_da_sala_sai_com_2224():
    md = T.multidobras(_pecas(_doc()))
    assert len(md["telhas"]) == 1
    t = md["telhas"][0]
    # o desenvolvido pela conta é 2.223,2 (retas + o arco de R490 por fora): o corte é 2.224
    assert t["desenv_ext"] == 2224.0, t["desenv_ext"]
    assert t["desenv_int"] == float(int(t["desenv_int"])) and t["desenv_int"] < t["desenv_ext"]
    from nucleo2d.desenho import Desenho
    d = Desenho(nome="t", escala=20.0)
    T.desenho_da_multidobra(t, d, 0.0, 0.0, "MD1")
    textos = _textos(d)
    assert any("desenvolvida: ext. 2224 mm" in x for x in textos), textos
    assert any(x.startswith("2,224 m") for x in textos), textos
    assert not any("2223" in x or "2,223" in x for x in textos), textos


def test_paginacao_e_lista_com_2224():
    from nucleo2d.detalhar import detalhar
    from nucleo2d.detalhe.base import _categoria
    from saida import lista_producao
    doc = _doc()
    r = detalhar(doc, grupos=["localizacao"], converter=False)
    cat = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    lista = lista_producao.montar(r["objetos_posicoes"], cat, r["acessorios"], pecas=r["objetos_pecas"])
    md = [li for li in lista["posicoes"] if li.get("classe") == "Telha multi-dobra"]
    assert md and all(li["comprimento"] == 2224 for li in md), md
    faces = T.faces_de_telhas(_pecas(doc), T.multidobras(_pecas(doc)))
    comps = [ch["comprimento"] for f in faces for ch in f["chapas"] if ch.get("multidobra")]
    assert comps and all(round(c) == 2224 for c in comps), comps


def test_cumeeira_da_sala_com_500():
    md = T.multidobras(_pecas(_doc()))
    assert len(md["cumeeiras"]) == 1
    cm = md["cumeeiras"][0]
    assert abs(cm["angulo"] - 157.2) < 0.15
    assert (cm["perna1"], cm["perna2"], cm["desenv"]) == (500.0, 500.0, 1000.0)
    from nucleo2d.desenho import Desenho
    d = Desenho(nome="t", escala=20.0)
    T.desenho_da_cumeeira(cm, d, 0.0, 0.0, "CU1")
    assert any("pernas 500 + 500 mm" in x and "desenvolvida 1000 mm" in x for x in _textos(d)), _textos(d)


def test_mm_o_maior():
    assert T.mm_o_maior(2223.2) == 2224.0
    assert T.mm_o_maior(2223.0) == 2223.0
    assert T.mm_o_maior(2223.04) == 2223.0        # ruído de conta não sobe
    assert T.mm_o_maior(2223.06) == 2224.0
