# -*- coding: utf-8 -*-
"""Viga-caixa de tubos (4 tubos nos cantos e anéis de travessas — o suporte da porta de correr do Vicente Residence,
08/10) no detalhamento: as instâncias certas mesmo com a composição de mdc 2, cada viga na sua célula (não uma
"tesoura montada" com os andares empilhados no mesmo plano), e a cadeia das travessas curtas cotada."""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Barra  # noqa: E402
from nucleo2d import detalhar as D  # noqa: E402
from nucleo2d.detalhe import base, conjuntos  # noqa: E402
from nucleo2d.desenho import Desenho  # noqa: E402

TQ = "TQ 50x50x3,0"
POSICOES = [25.0, 462.0, 900.0, 1338.0, 1776.0, 2176.0, 2400.0]     # centros das travessas; a última a 100 da ponta
L = 2500.0


def _viga(doc, z0, instancia="", x0=0.0):
    def barra(a, b, pos):
        br = Barra(inicio=a, fim=b, perfil=TQ, papel="barra", nome=pos)
        marcas = {"posicao": pos, "conjunto": "V1", "perfil": TQ}
        if instancia:
            marcas["instancia"] = instancia
        br.atributos = {"marcas": marcas, "tipo_ifc": "IfcMember"}
        doc.add(br)
    for yy in (-100.0, 100.0):
        for zz in (-25.0, -225.0):
            barra((x0, yy, z0 + zz), (x0 + L, yy, z0 + zz), "TQ-L")
    for p in POSICOES:
        x = x0 + p
        for zz in (-25.0, -225.0):
            barra((x, -73.0, z0 + zz), (x, 73.0, z0 + zz), "TQ2")
        for yy in (-100.0, 100.0):
            barra((x, yy, z0 - 52.0), (x, yy, z0 - 198.0), "TQ2")


def _documento(instancias=False):
    doc = Documento(nome="viga-caixa")
    for k in range(3):                       # três andares, a mesma viga no mesmo plano vertical
        _viga(doc, k * 3050.0, "V1#%d" % k if instancias else "")
    return doc


def test_tres_instancias_mesmo_com_mdc_2():
    # por viga: 4 tubos e 28 travessas (mdc 4) — a conta das quantidades dava "um quarto de viga"
    for marcadas in (False, True):
        r = D.detalhar(_documento(marcadas), grupos=["tesouras"], regra_tercas=False, converter=False)
        (c,) = [c for c in r["conjuntos"] if c["marca"] == "V1"]
        assert c["instancias"] == 3, (marcadas, c)
        assert c["composicao"] == {"TQ-L": 4, "TQ2": 28}


def test_andares_no_mesmo_plano_nao_viram_uma_tesoura_montada():
    doc = _documento()
    pecas, _ = base._pecas(doc)
    lista = [e for e in pecas if base._marcas(e).get("conjunto") == "V1"]
    unidade = collections.Counter({"TQ-L": 4, "TQ2": 28})
    montadas, cobertas = conjuntos.tesouras_montadas([("V1", lista, unidade)])
    assert montadas == [] and cobertas == set()


def test_cadeia_das_travessas_curtas():
    doc = Documento(nome="uma")
    _viga(doc, 0.0)
    pecas, _ = base._pecas(doc)
    d = Desenho(nome="t", escala=25.0)
    conjuntos.desenho_do_conjunto(doc, "V1", pecas, 1, d, 0.0, 0.0, False, nome="V1", tipo="tesoura")
    medidas = sorted(round(e.medida()) for e in d.entidades.values() if e.tipo == "cota")
    # a cadeia dos nós (as travessas de 146 mm param na face do tubo, 27 mm antes do eixo; a da ponta, a 25 mm, é a
    # ponta) e a última travessa a 100 mm da ponta como nó próprio (não fundida com a ponta)
    for v in (462, 438, 400, 224, 100):
        assert v in medidas, (v, medidas)
    assert L in medidas


def test_uma_instancia_so_marcada():
    # uma viga só, com a marca da instância: é uma instância (a conta das quantidades dava 4 de um quarto de viga)
    doc = Documento(nome="uma")
    _viga(doc, 0.0, "V1#0")
    r = D.detalhar(doc, grupos=["tesouras"], regra_tercas=False, converter=False)
    (c,) = [c for c in r["conjuntos"] if c["marca"] == "V1"]
    assert c["instancias"] == 1 and c["composicao"] == {"TQ-L": 4, "TQ2": 28}
