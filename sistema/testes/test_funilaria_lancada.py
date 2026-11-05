# -*- coding: utf-8 -*-
"""A calha, o rufo e a cumeeira lançados no modelo (sólidos fora das posições de produção) pesam pela chapa planificada ou
pelo peso gravado no 3D, não pela malha — e no resumo saem em "Rufos e calhas", não em "Gradis…" nem em "Telhas".

SESI Chapecó (auditor-de-numeros, 02/11, N23): as 11 calhas CM1–CM12 tinham `peso_kg` = 2.082,9 kg no 3D (dev. × comp. ×
esp. × 7,85: a CM4, 0,954 × 51,58 m × 1,0 mm = 386,3 kg) e a lista as pesava pela malha, 841,2 kg, em "aço fora das peças";
o resumo as punha em "Gradis, pisos e outras peças de aço — o que o IFC traz", sem peso. Os rufos (IfcCovering) iam para
"Telhas e painéis" com "—", e a malha maciça da cumeeira de 71 m pesava 2.007 kg (a chapa: 167 kg). O "Total geral (aço +
telhas + rufos)" não levava a funilaria."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import detalhar as det                          # noqa: E402
from nucleo3d.modelo import Barra, Documento, Solido          # noqa: E402
from saida import resumos                                     # noqa: E402

FACES = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]


def _caixa(nome, camada, tipo, dx, dy, dz, y0, **atr):
    """A malha da peça: uma caixa maciça (o volume dela NÃO é o da chapa)."""
    v = [(x, y0 + y, z) for x in (0.0, dx) for y in (0.0, dy) for z in (3000.0, 3000.0 + dz)]
    s = Solido(nome=nome, camada=camada, vertices=v, faces=FACES)
    s.material = "Funilaria galv."
    s.atributos["tipo_ifc"] = tipo
    s.atributos.update(atr)
    return s


def _obra():
    doc = Documento(nome="sesi-funilaria")
    doc.add(Barra(nome="W200", camada="Barras", inicio=(0.0, -2000.0, 0.0), fim=(6000.0, -2000.0, 0.0), perfil="W 200 x 19,3",
                  papel="viga"))
    doc.add(_caixa("Calha CM4 (chapa galv. #1,0, corte A)", "Calhas", "IfcPipeSegment", 51580.0, 100.0, 3.0, 0.0,
                   calha_lancada=True, marca="CM4", desenvolvimento=954, comprimento=51580, espessura=1, peso_kg=386.29))
    doc.add(_caixa("Rufo capa 230 (chapa galv. #0,50)", "Rufos", "IfcCovering", 10000.0, 230.0, 0.5, 1000.0,
                   rufo_lancado=True, desenvolvimento=430, comprimento=10000, espessura=0.5))
    doc.add(_caixa("Cumeeira (chapa galv. #0,50, dev. 600)", "Rufos", "IfcCovering", 71011.0, 600.0, 60.0, 2000.0,
                   cumeeira_lancada=True, desenvolvimento=600, comprimento=71011, espessura=0.5))
    doc.add(_caixa("Rufo em pé (sem seção) (chapa galv. #0,50)", "Rufos", "IfcCovering", 9978.0, 146.0, 0.5, 4000.0,
                   rufo_lancado=True, comprimento=9978, espessura=0.5))
    # como o lançamento do Posto V2 e do Madrid grava: o desenvolvimento em "corte" e a espessura só no nome, pela bitola
    doc.add(_caixa("Rufo capa (ch. galv. #26, corte 450)", "Rufos", "IfcCovering", 10243.0, 250.0, 0.45, 5000.0,
                   rufo_lancado=True, rufo="capa", corte=450, comprimento=10243))
    return doc


_LEV = {}


def _lev():
    if "lev" not in _LEV:
        _LEV["lev"] = det.levantar(_obra(), regra_tercas=False)
    return _LEV["lev"]


def _quadro8(nome):
    return next(g for g in _lev()["fora_do_aco"] if g["nome"].startswith(nome))


def test_a_funilaria_lancada_pesa_pela_chapa_ou_pelo_gravado():
    calha, rufo, cumeeira = _quadro8("Calha CM4"), _quadro8("Rufo capa 230"), _quadro8("Cumeeira")
    assert {calha["categoria"], rufo["categoria"], cumeeira["categoria"]} == {"funilaria"}
    assert abs(calha["peso_kg"] - 386.3) < 0.1, calha                         # o gravado (a malha: 121 kg)
    assert abs(rufo["peso_kg"] - 0.430 * 10.0 * 0.5 * 7.85) < 0.1, rufo
    assert abs(cumeeira["peso_kg"] - 0.600 * 71.011 * 0.5 * 7.85) < 0.1, cumeeira   # 167 kg (a malha: 2.007)
    posto = _quadro8("Rufo capa (ch. galv. #26")                              # #26 = 0,45 mm, não 26 mm
    assert abs(posto["peso_kg"] - 0.450 * 10.243 * 0.45 * 7.85) < 0.1, posto
    sem = _quadro8("Rufo em pé")
    assert sem["peso_kg"] == 0.0 and "sem o desenvolvimento" in sem["observacao"], sem


def test_no_resumo_vai_para_rufos_e_calhas():
    lista = {"posicoes": [], "pre_moldados": _lev()["fora_do_aco"]}
    F = resumos.funilaria_da_lista(lista)
    assert [x["tipo"] for x in F][:1] == ["Calha"] and len(F) == 5, F
    assert abs(sum(x["kg"] for x in F) - (386.29 + 16.88 + 167.22 + 16.28)) < 0.5, [(x["nome"], x["kg"]) for x in F]
    assert not resumos._telhas_lancadas(lista), resumos._telhas_lancadas(lista)
    assert not resumos._outros_aco(lista), resumos._outros_aco(lista)
    html = resumos._tabela_funilaria({"funilaria": F})
    assert "Calha CM4" in html and "var." not in html.split("Calha CM4")[1].split("</tr>")[0]
