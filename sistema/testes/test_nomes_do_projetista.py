# -*- coding: utf-8 -*-
"""O conjunto com o nome que o projetista deu (regra aprovada pelo usuário no Posto de Combustível, 12/11/2026: "o nome
das peças deve ser o mesmo que o projetista utilizou no projeto original; os conjuntos devem ser os mesmos, para não
ocorrer erros nos apontamentos").

* o nome vem da elevação de onde as barras saíram no 3D (origem.planta) e vence a numeração da fábrica e o nomes.json;
  título de vista ("PLANTA DAS BASES…") e peça sem origem (o PM6) ficam com o nome da fábrica;
* cópias de geometria diferente do mesmo nome: o mesmo nome com o número na frente, TESOURA 14-1 e 14-2 ("Sim, esse
  padrão sugerido"); o desenho que junta dois nomes (o MT71: TESOURA 1 e TESOURA 2) segue o mesmo padrão;
* a tesoura de cima da transição montada em duas peças vai fabricada com a transição, um conjunto só ("vai fabricado
  uma peça só, pode juntar os nomes");
* o Controle de produção e o título da prancha dão o mesmo número a cada unidade."""
import gzip
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from nucleo3d.modelo import Documento                     # noqa: E402
from nucleo3d import de_planta                            # noqa: E402
from nucleo2d import detalhar as det                      # noqa: E402
from nucleo2d.detalhe import nomes as nm                  # noqa: E402
from producao import controle                             # noqa: E402

RECORTE = os.path.join(AQUI, "dados_cad", "posto_conjuntos_instancias.json.gz")


def _doc():
    return Documento.de_dict(json.loads(gzip.decompress(open(RECORTE, "rb").read())))


def test_conjuntos_com_o_nome_do_projetista_no_posto():
    # o nomes.json de antes (o Detalhar de 09/11) dava MT97, T103, T105, DP.7…: o nome do projetista vence
    antigos = {"conjuntos": {"M133": "MT97", "M146": "T103", "M148": "T105", "M68 / M72": "DP.7", "M157": "T1"},
               "posicoes": {}}
    r = det.detalhar(_doc(), nomes=antigos)
    titulo = r["nomes"]["conjuntos"]
    por_marca = r["nomes"]["ifc_conjuntos"]
    assert titulo["M133"] == "PAINEL 15"
    # a TRELIÇA 9 tem duas cópias de geometria diferente: dois desenhos, o número na frente
    assert (titulo["M146"], titulo["M148"]) == ("TRELIÇA 9-1", "TRELIÇA 9-2")
    assert por_marca["M146"] == por_marca["M148"] == "TRELIÇA 9"
    # as duas cópias iguais do COMP 13 num desenho só (2X)
    assert titulo["M68 / M72"] == "COMP 13" and por_marca["M68"] == por_marca["M72"] == "COMP 13"
    assert titulo["M156"] == "PERFIL 1"
    # o PM6 não tem elevação com título no projeto: o nome da fábrica
    assert titulo["M157"] == "T1"


def test_nome_de_vista_e_tesoura_de_cima():
    class _P:
        def __init__(self, conj, planta):
            self.atributos = {"marcas": {"conjunto": conj, "posicao": "P1"}, "origem": {"planta": planta}}
            self.nome, self.id = "P1", conj + planta
    pecas = [_P("M1", "TRANSIÇÃO 2")] * 3 + [_P("M1", "TRANSIÇÃO 2 (tesoura de cima)")] * 2 \
        + [_P("M2", "PLANTA DAS BASES DE CAIXA DÁGUA")] * 4 + [_P("M3", "TESOURA 14")]
    assert nm._conjuntos_do_projeto(pecas) == {"M1": "TRANSIÇÃO 2", "M3": "TESOURA 14"}
    # e o gerador: as duas partes da transição em duas peças são um conjunto de fabricação
    assert de_planta.conjunto_de_fabrica("TRANSICAO 2 (tesoura de cima)#3") == "TRANSICAO 2#3"
    assert de_planta.conjunto_de_fabrica("TRANSICAO 2#3") == "TRANSICAO 2#3"
    # e o modelo já montado (o Posto em produção, sem remontar): a tesoura de cima passa ao conjunto da transição
    from nucleo3d.modelo import Barra
    doc = Documento()
    for i, (peca, conj, nome) in enumerate([("TRANSICAO 2#126", "M91", "MT62")] * 3
                                           + [("TRANSICAO 2 (tesoura de cima)#126", "M92", "MT63")] * 2
                                           + [("TRANSICAO 5 (tesoura de cima)#124", "M88", "MT59")]):
        b = Barra(inicio=(0, i * 100.0, 0), fim=(1000, i * 100.0, 0), perfil="L 2\"×3/16\"")
        b.atributos = {"origem": {"peca": peca}, "marcas": {"conjunto": conj, "nome_conjunto": nome, "posicao": "P1"}}
        doc.add(b)
    assert de_planta.juntar_tesouras_de_cima(doc) == 2                 # a da TRANSIÇÃO 5 sem a de baixo fica
    conjs = sorted((e.atributos["origem"]["peca"], e.atributos["marcas"]["conjunto"]) for e in doc.entidades.values())
    assert {c for p, c in conjs if p.startswith("TRANSICAO 2")} == {"M91"}
    assert {c for p, c in conjs if p.startswith("TRANSICAO 5")} == {"M88"}


def test_numeracao_das_unidades_igual_no_controle_e_na_prancha():
    # o Posto: TESOURA 1 em 5 conjuntos (M25, M27, M103 ×2, M104 ×2, M122) e TESOURA 2 (M102 ×2), TESOURA 14 em dois
    conj = [("M104", "TESOURA 1", 2), ("M25", "TESOURA 1", 1), ("M102", "TESOURA 2", 2), ("M122", "TESOURA 1", 1),
            ("M103", "TESOURA 1", 2), ("M27", "TESOURA 1", 1), ("M112", "TESOURA 14", 1), ("M111", "TESOURA 14", 1),
            ("M91", "TRANSIÇÃO 2", 1)]
    u = nm.numerar_unidades(conj)
    assert u["M25"] == ["TESOURA 1-1"] and u["M27"] == ["TESOURA 1-2"] and u["M103"] == ["TESOURA 1-3", "TESOURA 1-4"]
    assert u["M104"] == ["TESOURA 1-5", "TESOURA 1-6"] and u["M122"] == ["TESOURA 1-7"]
    assert u["M102"] == ["TESOURA 2-1", "TESOURA 2-2"]
    assert (u["M111"], u["M112"]) == (["TESOURA 14-1"], ["TESOURA 14-2"])
    assert u["M91"] == ["TRANSIÇÃO 2"]                       # sozinha, sem número
    assert nm._rotulo_das_unidades(u["M103"] + u["M104"]) == "TESOURA 1-3 A 6"
    # o Controle dá os mesmos números, mesmo com a lista na ordem do peso (a M112, mais pesada, vem antes)
    lista = {"posicoes": [], "conjuntos": [
        {"marca": "M112", "nome": "TESOURA 14", "instancias": 1, "peso_total": 228.8, "pecas_unidade": 66, "composicao": {}},
        {"marca": "M111", "nome": "TESOURA 14", "instancias": 1, "peso_total": 228.1, "pecas_unidade": 66, "composicao": {}}]}
    ids = {tuple(i["refs"]): i["id"] for i in controle.itens(lista)}
    assert ids[("M111",)] == "TESOURA 14-1" and ids[("M112",)] == "TESOURA 14-2"


# os 8 rótulos "BASE1" da planta das bases do DXF do Posto (folha 15, "BASE 1 - 8X"), nas coordenadas do modelo: o y do
# desenho menos 28.533,5 (o encaixe dos 4 locais do 3D nos pares de rótulos; resto < 1 mm), o x no meio das bases
ROTULOS_BASES = [(2042.0, y - 28533.5, "BASE1") for y in (79863, 78281, 68368, 66786, 48773, 47190, 37278, 35695)]


def test_bases_das_caixas_uma_por_rotulo():
    """Posto: as bases das caixas d'água são 8 ("BASE 1 - 8X", um rótulo em cada), duas por local, encostadas no meio
    (as pontas dos 2U se tocam). O grupo das peças que se tocam juntava as duas: a lista e as pranchas diziam 4 × 16
    barras (e a lista antiga 16 × 4). Cada barra vai para a base do rótulo mais perto, com a instância e o nome dela."""
    from saida import lista_producao as lp
    doc = Documento.de_dict(json.loads(gzip.decompress(open(os.path.join(AQUI, "dados_cad", "posto_bases_caixas.json.gz"),
                                                            "rb").read())))
    assert de_planta.bases_pelos_rotulos(doc, ROTULOS_BASES) == 64
    assert de_planta.bases_pelos_rotulos(doc, ROTULOS_BASES) == 0           # de novo: nada muda
    por_base = {}
    for e in doc.entidades.values():
        por_base.setdefault(e.atributos["marcas"]["instancia"], []).append(e.atributos["marcas"]["posicao"])
    assert len(por_base) == 8 and all(sorted(v) == ["P35"] * 4 + ["P85"] * 2 + ["P87"] * 2 for v in por_base.values())
    lev = det.levantar(doc)
    lista = lp.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"])
    c = lista["conjuntos"][0]
    assert (c["instancias"], c["pecas_unidade"]) == (8, 8)
    assert nm._conjuntos_do_projeto(lev["pecas"]) == {"M158": "BASE 1"}
