# -*- coding: utf-8 -*-
"""Quantas unidades tem cada conjunto: a lista de materiais (e o romaneio e o Controle de produção, que leem dela) e as
pranchas (o Detalhar) dizem o MESMO número, e é o das cópias do modelo.

Posto de Combustível, 12/11 (a troca para os nomes do projetista): a lista de 09/11 dizia PAINEL 15 = MT97 ×2 de 57
peças, TRANSIÇÃO 1 = T38 ×2, TRELIÇA 9 = T103 ×2… — 38 conjuntos com "meias" unidades, onde o 3D tem uma cópia da
elevação e as pranchas diziam 1. A lista tinha uma conta só dela (o mdc das quantidades e, caindo para 1, a "maioria"
das posições, sem conferir no espaço): na treliça simétrica quase toda diagonal aparece em par e a maioria via duas
metades. Em 3 (PAINEL 2, PAINEL 7, TRELIÇA 6) as pranchas também erravam: o mdc 2 sem nenhum grupo no espaço com a
composição, "desenhado o maior" com n = 2.

O recorte é o do próprio Posto (dados_cad/posto_conjuntos_instancias.json.gz, as barras de 10 conjuntos tiradas do
modelo.json de 09/11), com as cópias que o modelo tem de verdade: o PM6 (T1, 6 unidades em 3 copas) continua 6."""
import collections
import gzip
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from nucleo3d.modelo import Documento            # noqa: E402
from nucleo2d import detalhar as det             # noqa: E402
from nucleo2d.detalhe.base import _marcas        # noqa: E402
from saida import lista_producao as lp           # noqa: E402

RECORTE = os.path.join(AQUI, "dados_cad", "posto_conjuntos_instancias.json.gz")

# conjunto → (nome do projetista, unidades no 3D, peças por unidade)
ESPERADO = {
    "M133": ("PAINEL 15", 1, 115),
    "M146": ("TRELIÇA 9 (uma das cópias)", 1, 79),
    "M148": ("TRELIÇA 9 (a outra)", 1, 79),
    "M68": ("COMP 13", 1, 37),
    "M72": ("COMP 13 (a outra)", 1, 37),
    "M56": ("TRELIÇA 6", 1, 44),
    "M136": ("PAINEL 2", 1, 14),
    "M142": ("PAINEL 7", 1, 14),
    "M156": ("PERFIL 1 (VG1)", 2, 4),
    "M157": ("PM6 (T1, 2 por copa)", 6, 16),
}


def _levantar():
    doc = Documento.de_dict(json.loads(gzip.decompress(open(RECORTE, "rb").read())))
    return det.levantar(doc)


def test_lista_de_materiais_conta_as_unidades_do_modelo():
    lev = _levantar()
    lista = lp.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"])
    conj = {c["marca"]: c for c in lista["conjuntos"]}
    erros = []
    for m, (nome, n, pu) in ESPERADO.items():
        c = conj.get(m)
        if c is None or (c["instancias"], c["pecas_unidade"]) != (n, pu):
            erros.append("%s %s: lista %s × modelo %d × %d peças" % (
                m, nome, c and "%d × %d" % (c["instancias"], c["pecas_unidade"]), n, pu))
    assert not erros, "\n".join(erros)


def test_pranchas_e_lista_decidem_igual():
    lev = _levantar()
    por_conj = collections.defaultdict(list)
    for e in lev["pecas"]:
        c = str(_marcas(e).get("conjunto") or "")
        if c:
            por_conj[c].append(e)
    for m, (nome, n, pu) in ESPERADO.items():
        _inst, n_det, unidade, _aviso = det.decidir_instancias(m, por_conj[m])
        assert (n_det, sum(unidade.values())) == (n, pu), "%s %s: Detalhar %d × %d" % (m, nome, n_det, sum(unidade.values()))
