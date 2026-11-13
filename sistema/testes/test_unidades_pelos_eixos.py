# -*- coding: utf-8 -*-
"""O número de cada unidade pela ordem dos eixos da obra (regra aprovada pelo usuário no Posto, 12/11/2026: "TESOURA 1-1
é a do primeiro eixo, a 1-2 a do seguinte" — "Sim pode seguir").

* as unidades se separam pelo que o modelo diz (a cópia da elevação, origem.peca; a instância) e a chapa soldada sem
  chave vai para a unidade em que encosta;
* a ordem: ao longo dos eixos de número (do 1 em diante, mesmo com o eixo 1 no fim da coordenada), depois dos de letra
  (do A em diante — no Posto o A está no fim), depois a altura; sem eixos, x e y;
* o mesmo nome em várias marcas numera junto, na ordem dos eixos (não mais na das marcas);
* alguma marca que não se separa: o nome todo na ordem das marcas, como antes;
* o Controle de produção usa o mesmo número e as peças de cada unidade (o 3D ao lado acende a certa)."""
import gzip
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from nucleo2d.detalhe import unidades as U               # noqa: E402
from producao import controle                            # noqa: E402

#: os eixos do Posto (projeto.json, 13/11): números ao longo de x, letras ao longo de y com o A no fim
EIXOS_POSTO = {"eixo_g": [1.0, 0.0], "z_base": 0.0, "origem": "usuario",
               "numeros": [{"nome": n, "pos": p} for n, p in [("1", 966.7), ("3", 9960.9), ("4", 21370.4), ("5", 25016.0),
                                                            ("6", 28961.0), ("7", 29991.5), ("8", 32991.5), ("9", 33986.5),
                                                            ("10", 34496.6), ("11", 40483.5), ("12", 41815.6), ("13", 49646.5),
                                                            ("14", 51029.8), ("15", 53921.5), ("16", 57302.8), ("17", 59131.8)]],
               "letras": [{"nome": n, "pos": p} for n, p in [("L", 2205.6), ("K", 7953.2), ("J", 13700.7), ("I", 19448.3),
                                                           ("H", 25195.9), ("G", 28695.9), ("F", 32155.9), ("E", 33295.9),
                                                           ("D", 39043.5), ("C", 44791.0), ("B", 50538.6), ("A", 56361.2)]]}


class _P:
    """uma peça: caixa de (x, y, z) a (x+dx, y+dy, z+dz)"""
    n = 0

    def __init__(self, conj, x, y=0.0, z=0.0, dx=100.0, dy=100.0, dz=1000.0, peca=None, instancia=None):
        _P.n += 1
        self.id = "e%d" % _P.n
        self.nome = "P1"
        m = {"conjunto": conj, "posicao": "P1"}
        if instancia:
            m["instancia"] = instancia
        self.atributos = {"marcas": m}
        if peca:
            self.atributos["origem"] = {"peca": peca}
        self.vertices = [(x + a, y + b, z + c) for a in (0, dx) for b in (0, dy) for c in (0, dz)]


def _tesoura(conj, x, peca=None, y=0.0, n=3, **kw):
    """n barras encostadas em x (uma treliça vista de lado)"""
    return [_P(conj, x, y + 90.0 * k, peca=peca, **kw) for k in range(n)]


def _eixos(numeros, letras=(), g=(1.0, 0.0)):
    return {"eixo_g": list(g), "z_base": 0.0, "origem": "usuario",
            "numeros": [{"nome": n, "pos": p} for n, p in numeros], "letras": [{"nome": n, "pos": p} for n, p in letras]}


EIXOS_123 = _eixos([("1", 0.0), ("2", 10000.0), ("3", 20000.0)], [("A", 0.0), ("B", 8000.0)])


def test_o_mesmo_nome_em_varias_marcas_numera_pela_ordem_dos_eixos():
    # a M1 tem duas unidades, uma no eixo 3 e uma no eixo 1; a M2 tem uma, no eixo 2: pela marca seriam M1 → 1 e 2,
    # M2 → 3; pelos eixos, a do eixo 1 é a 1-1, a M2 (eixo 2) a 1-2 e a do eixo 3 a 1-3
    pecas = _tesoura("M1", 20000, "TESOURA 1#a") + _tesoura("M1", 0, "TESOURA 1#b") + _tesoura("M2", 10000, "TESOURA 1#c")
    nomes, lugar = U.numerar([("M1", "TESOURA 1", 2), ("M2", "TESOURA 1", 1)], pecas, EIXOS_123)
    assert nomes == {"M1": ["TESOURA 1-1", "TESOURA 1-3"], "M2": ["TESOURA 1-2"]}
    eixo_1 = sorted(p.id for p in pecas[3:6])
    assert lugar["M1"][0] == {"nome": "TESOURA 1-1", "ids": eixo_1, "meio": [50, 140, 500]}
    assert lugar["M1"][1]["nome"] == "TESOURA 1-3" and lugar["M2"][0]["nome"] == "TESOURA 1-2"


def test_eixo_1_no_fim_da_coordenada_e_letras_do_A():
    pecas = _tesoura("M1", 20000, "T#a") + _tesoura("M1", 0, "T#b")
    # o eixo 1 em x = 20000: a do x = 20000 é a primeira
    nomes, _l = U.numerar([("M1", "T", 2)], pecas, _eixos([("1", 20000.0), ("2", 0.0)]))
    assert U.separar(pecas, 2) is not None
    _n, lugar = U.numerar([("M1", "T", 2)], pecas, _eixos([("1", 20000.0), ("2", 0.0)]))
    assert lugar["M1"][0]["meio"][0] > 10000 and lugar["M1"][0]["nome"] == "T-1"
    # no mesmo eixo de número, pela letra: o A no fim da coordenada (como no Posto) vem primeiro
    pecas = _tesoura("M1", 5000, "T#a", y=0.0) + _tesoura("M1", 5000, "T#b", y=50000.0)
    _n, lugar = U.numerar([("M1", "T", 2)], pecas, EIXOS_POSTO)
    assert lugar["M1"][0]["meio"][1] > 40000 and lugar["M1"][0]["nome"] == "T-1"


def test_chapa_soldada_sem_chave_vai_para_a_unidade_em_que_encosta():
    a, b = _tesoura("M1", 0, "T#a"), _tesoura("M1", 20000, "T#b")
    chapa = _P("M1", 20100, 0.0, dx=10.0, dy=50.0, dz=50.0)          # encostada na de x = 20000, sem origem
    grupos = U.separar(a + b + [chapa], 2)
    assert grupos is not None and any(chapa in g and b[0] in g for g in grupos)
    # e a instância do modelo (o conjunto do IFC) vale como a origem
    c = _tesoura("M3", 0, instancia="i1") + _tesoura("M3", 9000, instancia="i2")
    assert len(U.separar(c, 2)) == 2


def test_sem_chave_separa_pelas_pecas_que_se_tocam_e_sem_eixos_pela_posicao():
    pecas = _tesoura("M1", 30000) + _tesoura("M1", 0) + _tesoura("M1", 15000)
    nomes, lugar = U.numerar([("M1", "TESOURA 9", 3)], pecas, None)
    assert [u["meio"][0] for u in lugar["M1"]] == [50, 15050, 30050]
    assert nomes["M1"] == ["TESOURA 9-1", "TESOURA 9-2", "TESOURA 9-3"]


def test_marca_que_nao_se_separa_numera_o_nome_todo_pela_marca():
    # a M1 diz 3 unidades, mas no modelo só há duas tesouras: nenhuma unidade com lugar; o nome todo como antes
    pecas = _tesoura("M1", 0, "T#a") + _tesoura("M1", 9000, "T#b") + _tesoura("M2", 4000, "T#c")
    nomes, lugar = U.numerar([("M2", "TESOURA 1", 1), ("M1", "TESOURA 1", 3)], pecas, EIXOS_123)
    assert nomes == {"M1": ["TESOURA 1-1", "TESOURA 1-2", "TESOURA 1-3"], "M2": ["TESOURA 1-4"]}
    assert lugar == {}
    # nome com uma unidade só: sem número e sem lugar (não precisa)
    nomes, lugar = U.numerar([("M2", "TRANSIÇÃO 2", 1)], pecas, EIXOS_123)
    assert nomes == {"M2": ["TRANSIÇÃO 2"]} and lugar == {}


def test_o_controle_usa_o_numero_e_as_pecas_de_cada_unidade():
    pecas = _tesoura("M1", 20000, "TESOURA 1#a") + _tesoura("M1", 0, "TESOURA 1#b") + _tesoura("M2", 10000, "TESOURA 1#c")
    _n, lugar = U.numerar([("M1", "TESOURA 1", 2), ("M2", "TESOURA 1", 1)], pecas, EIXOS_123)
    lista = {"posicoes": [], "conjuntos": [
        {"marca": "M1", "nome": "TESOURA 1", "instancias": 2, "peso_total": 200.0, "pecas_unidade": 3, "composicao": {}},
        {"marca": "M2", "nome": "TESOURA 1", "instancias": 1, "peso_total": 100.0, "pecas_unidade": 3, "composicao": {}}]}
    its = controle.itens(lista, {"unidades": lugar})
    por = {x["id"]: x for x in its}
    assert sorted(por) == ["TESOURA 1-1", "TESOURA 1-2", "TESOURA 1-3"]
    assert por["TESOURA 1-1"]["refs"] == ["M1"] and por["TESOURA 1-1"]["pecas3d"] == sorted(p.id for p in pecas[3:6])
    assert por["TESOURA 1-2"]["refs"] == ["M2"]
    # sem o lugar (o nomes.json de antes) ou com outro número de unidades: a contagem pela marca, sem peças
    its = controle.itens(lista, {"unidades": {"M1": lugar["M1"][:1]}})
    assert [x["id"] for x in its if x["refs"] == ["M1"]] == ["TESOURA 1-1", "TESOURA 1-2"]
    assert not any("pecas3d" in x for x in its if x["refs"] == ["M1"])


def test_recorte_do_posto_com_os_eixos_dele():
    """o Detalhar do recorte do Posto com os eixos do projeto: o título da prancha e o lugar dizem o mesmo número, e as
    peças de cada unidade existem no modelo"""
    from nucleo3d.modelo import Documento
    from nucleo2d import detalhar as det
    doc = Documento.de_dict(json.loads(gzip.decompress(open(os.path.join(AQUI, "dados_cad", "posto_conjuntos_instancias.json.gz"), "rb").read())))
    ids_doc = {str(i) for i in doc.entidades}
    r = det.detalhar(doc, eixos=EIXOS_POSTO)
    lugar = r["nomes"].get("unidades") or {}
    assert lugar, "o Detalhar grava o lugar das unidades"
    for marca, uns in lugar.items():
        for u in uns:
            assert u["ids"] and set(u["ids"]) <= ids_doc, (marca, u["nome"])
    # TRELIÇA 9: duas cópias de geometria diferente (M146 e M148): o título de cada desenho é o número do lugar dela,
    # e a primeira é a que está antes nos eixos de número
    t = r["nomes"]["conjuntos"]
    a, b = lugar["M146"][0], lugar["M148"][0]
    assert {t["M146"], t["M148"]} == {"TRELIÇA 9-1", "TRELIÇA 9-2"}
    assert t["M146"] == a["nome"] and t["M148"] == b["nome"]
    primeira = [a, b][U.ordenar([a["meio"], b["meio"]], EIXOS_POSTO)[0]]
    assert primeira["nome"] == "TRELIÇA 9-1"


def test_unidades_de_tamanho_diferente_nao_valem():
    # as 6 T1 do Posto (16 peças cada): pela origem das barras saíam 4 de 8 e 2 de 32 — não são unidades iguais; pelo
    # contato também não separam: o nome fica sem lugar, na ordem das marcas
    pecas = []
    for k in range(4):
        pecas += _tesoura("M157", 3000.0 * k, "PM6#%d" % k, n=2)                 # 8 de 2… e
    pecas += _tesoura("M157", 20000, "PM6#9", n=8) + _tesoura("M157", 20000, "PM6#9", y=5000.0, n=8)
    assert U.separar(pecas, 6) is None
    nomes, lugar = U.numerar([("M157", "T1", 6)], pecas, EIXOS_123)
    assert nomes["M157"] == ["T1-%d" % i for i in range(1, 7)] and lugar == {}


def test_mesmo_eixo_em_cadeia_e_nao_por_faixa():
    # duas tesouras quase no mesmo x (5849 e 5851, dos dois lados de uma faixa de 300 mm) vão pela letra: a do A primeiro
    meios = [(5849.0, 2206.0, 0.0), (5851.0, 56361.0, 0.0), (20000.0, 30000.0, 0.0)]
    assert U.ordenar(meios, EIXOS_POSTO) == [1, 0, 2]
