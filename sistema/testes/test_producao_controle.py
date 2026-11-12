# -*- coding: utf-8 -*-
"""Controle de produção (producao/controle.py, 12/11/2026): os itens tirados da lista de materiais, o apontamento com
estorno guardado no projeto, o andamento e o que o ERP lê. Decisões do usuário em
Projeto/BRIEFINGS/CHATS/FERRAMENTA-controle-producao.md."""
import datetime
import io
import json
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from producao import controle as C  # noqa: E402


def _lista():
    """uma obra pequena com as situações do Posto V2: tesoura repetida (T38 ×2) com uma peça a mais numa das unidades
    (difere), tesoura única (T74), o mesmo nome em duas marcas (MT71 = M102 ×2 + M103 ×1), terças e contraventos
    avulsos e uma posição que entra na tesoura e também sobra avulsa"""
    pos = [
        {"marca": "P11", "nome": "B.9", "categoria": "BARRAS", "perfil": "L 2\"×3/16\"", "quantidade": 10, "comprimento": 221, "peso": 1.0, "conjuntos": ["M51"]},
        {"marca": "P337", "nome": "B.187", "categoria": "BARRAS", "perfil": "Ue 250", "quantidade": 4, "comprimento": 9000, "peso": 100.0, "conjuntos": ["M51"]},
        {"marca": "P1290", "nome": "B.700", "categoria": "BARRAS", "perfil": "L 2\"", "quantidade": 1, "comprimento": 500, "peso": 2.0, "conjuntos": ["M51"]},
        {"marca": "P9", "nome": "B.8", "categoria": "BARRAS", "perfil": "L 1½\"", "quantidade": 7, "comprimento": 300, "peso": 0.5, "conjuntos": ["M115", "M300"]},
        {"marca": "P5 / P6", "nome": "B.4", "categoria": "BARRAS", "perfil": "L 1½\"", "quantidade": 9, "comprimento": 400, "peso": 0.8, "conjuntos": ["M102", "M103"]},
        {"marca": "P22", "nome": "T.C.1", "categoria": "TERÇAS", "perfil": "U 100×40×2,65 (FF)", "quantidade": 46, "comprimento": 3784, "peso": 13.6, "conjuntos": ["M346"]},
        {"marca": "P241", "nome": "CV.2", "categoria": "TIRANTES", "perfil": "Barra redonda 12,5", "quantidade": 6, "comprimento": 5029, "peso": 4.85, "conjuntos": ["M400"]},
        {"marca": "Gusset G1", "nome": "CH2", "categoria": "CHAPAS", "perfil": "CH 4,76", "quantidade": 106, "comprimento": 300, "peso": 1.12, "conjuntos": []},
    ]
    cj = [
        # 2 tesouras: 5 B.9 + 2 B.187 cada; uma delas leva 1 B.700 a mais (o difere da lista)
        {"marca": "M51", "nome": "T38", "instancias": 2, "pecas_unidade": 7, "composicao": {"P11": 5, "P337": 2},
         "peso_total": 2 * (5 * 1.0 + 2 * 100.0) + 2.0, "difere": ["P1290 (1 em vez de 0)"], "categoria": "TESOURAS"},
        # tesoura única com 4 B.8 (sobram 3 B.8 avulsas)
        {"marca": "M115", "nome": "T74", "instancias": 1, "pecas_unidade": 4, "composicao": {"P9": 4},
         "peso_total": 4 * 0.5, "difere": [], "categoria": "TESOURAS"},
        # o mesmo nome MT71 em duas marcas: 3 unidades no total, 3 B.4 cada
        {"marca": "M102", "nome": "MT71", "instancias": 2, "pecas_unidade": 3, "composicao": {"P5": 3},
         "peso_total": 2 * 3 * 0.8, "difere": [], "categoria": "CONJUNTOS"},
        {"marca": "M103", "nome": "MT71", "instancias": 1, "pecas_unidade": 3, "composicao": {"P6": 3},
         "peso_total": 3 * 0.8, "difere": [], "categoria": "CONJUNTOS"},
    ]
    total = sum(p["quantidade"] * p["peso"] for p in pos)
    return {"gerado": "2026-11-09 14:49", "projeto": {"nome": "Obra de teste"}, "totais": {"peso": round(total, 1)},
            "posicoes": pos, "conjuntos": cj}


NOMES = {"tipos_conjuntos": {"M51": "tesoura", "M115": "tesoura"}}


def _por_id(its):
    return {x["id"]: x for x in its}


# ------------------------------------------------------------------ itens
def test_tesoura_repetida_ganha_numero_e_a_unica_nao():
    its = _por_id(C.itens(_lista(), NOMES))
    assert {"T38-1", "T38-2", "T74"} <= set(its)
    assert "T38" not in its and "T74-1" not in its
    assert its["T38-1"]["quantidade"] == 1 and its["T38-1"]["tipo"] == "tesoura"
    assert its["T38-1"]["refs"] == ["M51"]


def test_mesmo_nome_em_marcas_diferentes_numera_junto():
    its = _por_id(C.itens(_lista(), NOMES))
    assert [k for k in its if k.startswith("MT71")] == ["MT71-1", "MT71-2", "MT71-3"]
    assert its["MT71-3"]["refs"] == ["M103"]


def test_pecas_avulsas_pela_posicao_com_a_quantidade():
    its = _por_id(C.itens(_lista(), NOMES))
    assert its["T.C.1"]["quantidade"] == 46 and its["T.C.1"]["origem"] == "pecas" and its["T.C.1"]["tipo"] == "terça"
    assert its["CV.2"]["quantidade"] == 6 and its["CV.2"]["tipo"] == "contravento"
    assert its["CH2"]["quantidade"] == 106
    # B.8: 7 na lista, 4 na T74 → 3 avulsas; B.9, B.187, B.700 e B.4 vão inteiras nas tesouras
    assert its["B.8"]["quantidade"] == 3
    assert not ({"B.9", "B.187", "B.700", "B.4"} & set(its))


def test_a_soma_dos_itens_fecha_com_o_peso_da_lista():
    L = _lista()
    its = C.itens(L, NOMES)
    assert sum(x["kg"] for x in its) == pytest.approx(L["totais"]["peso"], abs=0.1)


def test_peca_a_mais_do_difere_nao_sobra_avulsa():
    """o difere da lista ("P1290 (1 em vez de 0)") põe a peça dentro da tesoura: sem ele, a B.700 sobrava avulsa e o
    peso contava duas vezes (o Posto V2 passava 484 kg)"""
    its = _por_id(C.itens(_lista(), NOMES))
    assert "B.700" not in its


# ------------------------------------------------------------------ apontar e estornar
def test_apontar_grava_no_projeto_e_soma(tmp_path):
    L = _lista()
    ev = C.apontar(str(tmp_path), L, "T.C.1", "pintura", 30, "Engenharia", nomes=NOMES)
    assert os.path.exists(tmp_path / "producao" / "apontamentos.jsonl")
    assert ev["kg"] == pytest.approx(30 * 13.6)
    C.apontar(str(tmp_path), L, "T38-1", "producao", 1, "Engenharia", nomes=NOMES)
    f = C.feito(C.ler_eventos(str(tmp_path)))
    assert f["T.C.1"]["pintura"] == 30 and f["T38-1"]["producao"] == 1


def test_nao_aponta_mais_do_que_falta(tmp_path):
    L = _lista()
    C.apontar(str(tmp_path), L, "T.C.1", "producao", 40, "E", nomes=NOMES)
    with pytest.raises(C.ErroControle, match="só faltam 6"):
        C.apontar(str(tmp_path), L, "T.C.1", "producao", 7, "E", nomes=NOMES)
    C.apontar(str(tmp_path), L, "T38-2", "producao", 1, "E", nomes=NOMES)
    with pytest.raises(C.ErroControle, match="T38-2 já está completo na produção"):
        C.apontar(str(tmp_path), L, "T38-2", "producao", 1, "E", nomes=NOMES)


@pytest.mark.parametrize("item,etapa,qtd,data,msg", [
    ("T.C.1", "expedicao", 1, None, "etapa desconhecida"),
    ("T99", "producao", 1, None, "não está na lista"),
    ("T.C.1", "producao", 0, None, "1 ou mais"),
    ("T.C.1", "producao", "x", None, "quantidade inválida"),
    ("T.C.1", "producao", 1, "2099-01-01", "depois de hoje"),
    ("T.C.1", "producao", 1, "31/12/2026", "data inválida"),
])
def test_pedidos_recusados(tmp_path, item, etapa, qtd, data, msg):
    with pytest.raises(C.ErroControle, match=msg):
        C.apontar(str(tmp_path), _lista(), item, etapa, qtd, "E", data=data, nomes=NOMES)
    assert C.ler_eventos(str(tmp_path)) == []


def test_data_do_que_foi_feito_ontem(tmp_path):
    ontem = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    ev = C.apontar(str(tmp_path), _lista(), "CV.2", "producao", 6, "E", data=ontem, nomes=NOMES)
    assert ev["data"] == ontem and ev["quando"][:10] == datetime.date.today().isoformat()


def test_estorno_desfaz_sem_apagar(tmp_path):
    L = _lista()
    ev = C.apontar(str(tmp_path), L, "T.C.1", "pintura", 46, "E", nomes=NOMES)
    est = C.estornar(str(tmp_path), ev["id"], "E")
    eventos = C.ler_eventos(str(tmp_path))
    assert [e["id"] for e in eventos] == [ev["id"], est["id"]]          # o original continua no arquivo
    assert C.feito(eventos).get("T.C.1", {}).get("pintura", 0) == 0
    with pytest.raises(C.ErroControle, match="já foi estornado"):
        C.estornar(str(tmp_path), ev["id"], "E")
    with pytest.raises(C.ErroControle, match="já é um estorno"):
        C.estornar(str(tmp_path), est["id"], "E")
    # depois do estorno, a quantidade volta a estar livre
    C.apontar(str(tmp_path), L, "T.C.1", "pintura", 46, "E", nomes=NOMES)


def test_linha_cortada_no_arquivo_nao_derruba_a_leitura(tmp_path):
    C.apontar(str(tmp_path), _lista(), "CV.2", "producao", 2, "E", nomes=NOMES)
    with open(C.caminho(str(tmp_path)), "a", encoding="utf-8") as f:
        f.write('{"id": "meia-lin')
    assert len(C.ler_eventos(str(tmp_path))) == 1


# ------------------------------------------------------------------ andamento e ERP
def test_situacao_andamento_e_fora_da_lista(tmp_path):
    L = _lista()
    C.apontar(str(tmp_path), L, "T38-1", "producao", 1, "E", nomes=NOMES)
    C.apontar(str(tmp_path), L, "T.C.1", "producao", 46, "E", nomes=NOMES)
    eventos = C.ler_eventos(str(tmp_path))
    # um item que sumiu da lista (detalhamento refeito)
    eventos.append({"id": "x1", "item": "T99-1", "etapa": "producao", "quantidade": 1, "kg": 10, "quando": "2026-11-12T08:00"})
    s = C.situacao(L, eventos, NOMES)
    its = _por_id(C.itens(L, NOMES))
    kg = its["T38-1"]["kg"] + 46 * 13.6
    assert s["andamento"]["producao"]["kg"] == pytest.approx(kg, abs=0.1)
    assert s["andamento"]["producao"]["pct"] == pytest.approx(100 * kg / s["total"]["kg"], abs=0.1)
    assert s["andamento"]["producao"]["itens_completos"] == 2
    assert s["andamento"]["pintura"]["kg"] == 0
    assert s["fora_da_lista"] == ["T99-1"]
    assert s["total"]["unidades_conjunto"] == 6
    assert _por_id(s["itens"])["T38-1"]["feito"] == {"producao": 1, "pintura": 0}


def test_o_que_o_erp_le(tmp_path):
    L = _lista()
    a = C.apontar(str(tmp_path), L, "T.C.1", "pintura", 30, "Engenharia", nomes=NOMES)
    r = C.para_erp("obra-teste", "Obra de teste", L, C.ler_eventos(str(tmp_path)), NOMES)
    assert r["obra"] == "obra-teste" and r["etapas"] == ["producao", "pintura"]
    assert set(r["andamento"]) == {"producao", "pintura"}
    tc = next(x for x in r["itens"] if x["marca"] == "T.C.1")
    assert tc == {"marca": "T.C.1", "tipo": "terça", "quantidade": 46, "kg_unidade": 13.6, "producao": 0, "pintura": 30}
    assert r["eventos"][0]["marca"] == "T.C.1" and r["eventos"][0]["quem"] == "Engenharia"
    json.dumps(r)                                                      # vai em JSON
    # desde: só o que veio depois
    assert C.para_erp("obra-teste", "x", L, C.ler_eventos(str(tmp_path)), NOMES, desde=a["quando"])["eventos"] == []


# ------------------------------------------------------------------ a obra piloto (se a pasta estiver nesta máquina)
# a pasta real dos dados (o conftest troca METALICA_DADOS por uma pasta de teste)
def _posto():
    """a pasta do Posto nesta máquina (chamou-se posto-de-combustível-v2; hoje posto-de-combustível)"""
    import glob
    for p in sorted(glob.glob(os.path.join(r"C:\Metálica\dados", "posto-de-combust*"))):
        if os.path.exists(os.path.join(p, "detalhamento", "lista-de-materiais.json")):
            return p
    return os.path.join(r"C:\Metálica\dados", "posto-de-combustível")


POSTO = _posto()


@pytest.mark.skipif(not os.path.exists(os.path.join(POSTO, C.LISTA)), reason="o Posto V2 não está nesta máquina")
def test_posto_v2_fecha_o_peso_e_numera_as_tesouras():
    L = C.ler_lista(POSTO)
    its = C.itens(L, C.ler_nomes(POSTO))
    ids = [x["id"] for x in its]
    assert len(ids) == len(set(ids))
    assert sum(1 for x in its if x["origem"] == "conjunto") == sum(c["instancias"] for c in L["conjuntos"])
    assert sum(x["kg"] for x in its) == pytest.approx(L["totais"]["peso"], abs=1.0)
    # os nomes do projetista (12/11, d9b0365): a T38 ×2 eram duas meias da TRANSIÇÃO 1 (5315b80), a T74 é a TRANSIÇÃO 16, o
    # MT71 são 4 TESOURA 1 + 2 TESOURA 2, e as cópias diferentes do mesmo nome com o número na frente
    assert {"TRANSIÇÃO 1", "TRANSIÇÃO 16", "TESOURA 1-7", "TESOURA 2-2", "TESOURA 14-1", "TESOURA 14-2", "T.C.1",
            "CV.2"} <= set(ids)
    assert not {"T38-1", "T74", "MT71-6", "TESOURA 14"} & set(ids)


# ------------------------------------------------------------------ as rotas (producao/web.py)
class _H:
    def __init__(self, path):
        self.path = path
        self.wfile = io.BytesIO()
        self.cabecalhos = {}
        self.resposta = None

    def send_response(self, c):
        self.status = c

    def send_header(self, k, v):
        self.cabecalhos[k] = v

    def end_headers(self):
        pass

    def _json(self, obj, status=200):
        self.resposta = obj


def test_tela_propria_do_controle_e_a_lista_volta_a_ser_so_a_lista():
    """12/11: o usuário não achou a aba Controle dentro da lista e pediu no menu Produção — virou a tela
    /controle-producao; a lista de materiais não é mais interceptada nem tem o gancho de abas"""
    from producao import web
    assert not web.rota_get(_H("/materiais?projeto=x"), "/materiais")
    h = _H("/controle-producao?projeto=x")
    assert web.rota_get(h, "/controle-producao")
    html = h.wfile.getvalue().decode("utf-8")
    assert '<script src="/api/producao/controle.js"></script>' in html and '<script src="/etapas.js"></script>' in html
    assert 'id="controle-corpo"' in html and "<h1>Controle de produção</h1>" in html
    h = _H("/api/producao/controle.js")
    assert web.rota_get(h, "/api/producao/controle.js")
    js = h.wfile.getvalue().decode("utf-8")
    assert "ABAS_EXTRA" not in js and "function tabela(" in js and "#controle-corpo" in js
    mat = open(os.path.join(os.path.dirname(AQUI), "web", "materiais.js"), encoding="utf-8").read()
    assert "ABAS_EXTRA" not in mat


def test_menu_producao_do_topo_abre_as_duas_telas(monkeypatch):
    from producao import web

    class _App:
        @staticmethod
        def etapas_do_projeto(s):
            return {"projeto": {"slug": s}, "etapas": [
                {"chave": "engenharia", "nome": "Engenharia", "url": "/dividida", "itens": []},
                {"chave": "producao", "nome": "Produção", "url": "/materiais?projeto=%s#geral" % s, "itens": [{"texto": "Lista de materiais"}]}]}

    monkeypatch.setattr(web, "_app", lambda: _App)
    h = _H("/api/projetos/posto-de-combustível/etapas")
    assert web.rota_get(h, "/api/projetos/posto-de-combustível/etapas")
    prod = [e for e in h.resposta["etapas"] if e["chave"] == "producao"][0]
    assert [t["texto"] for t in prod["telas"]] == ["Lista de materiais", "Controle de produção"]
    assert prod["telas"][1]["url"] == "/controle-producao?projeto=posto-de-combust%C3%ADvel"
    assert prod["itens"][-1]["texto"] == "Controle de produção"            # a busca Ctrl+K acha
    assert "telas" not in h.resposta["etapas"][0]
    assert not web.rota_get(_H("/api/projetos/x/etapas/mais"), "/api/projetos/x/etapas/mais")


def test_etapas_js_abre_a_lista_das_telas_e_reconhece_o_controle():
    js = open(os.path.join(os.path.dirname(AQUI), "web", "etapas.js"), encoding="utf-8").read()
    assert "controle-producao" in js
    assert "(e.telas || []).length > 1" in js and "abrirLista(ev.currentTarget, e.telas.map(" in js


def test_nome_da_obra_vem_do_projeto_e_nao_da_lista_antiga(monkeypatch, tmp_path):
    """12/11 (usuário, Posto): trocou o nome do projeto para "POSTO DE COMBUSTÍVEL" e o Controle seguia com
    "POSTO DE COMBUSTÍVEL - V2" no título e na aba — o nome vinha da lista de materiais levantada em 09/11"""
    from producao import web

    class _G:
        @staticmethod
        def ler(s):
            return {"nome": "POSTO DE COMBUSTÍVEL"}

        @staticmethod
        def _existente(s):
            return str(tmp_path)

    class _App:
        @staticmethod
        def _gerente():
            return _G

    monkeypatch.setattr(web, "_app", lambda: _App)
    lista = _lista()
    lista["projeto"] = {"nome": "POSTO DE COMBUSTÍVEL - V2"}
    os.makedirs(tmp_path / "detalhamento")
    json.dump(lista, open(tmp_path / "detalhamento" / "lista-de-materiais.json", "w", encoding="utf-8"), ensure_ascii=False)
    h = _H("/api/producao/controle?projeto=posto")
    assert web.rota_get(h, "/api/producao/controle")
    assert h.resposta["obra"] == "POSTO DE COMBUSTÍVEL"
    h = _H("/api/producao/erp?projeto=posto")
    assert web.rota_get(h, "/api/producao/erp")
    assert h.resposta["nome"] == "POSTO DE COMBUSTÍVEL"
    # sem nome no projeto, o da lista
    monkeypatch.setattr(_G, "ler", staticmethod(lambda s: {}))
    assert web._nome_da_obra("posto", lista) == "POSTO DE COMBUSTÍVEL - V2"


@pytest.mark.parametrize("nome,instancias,esperado", [
    ("TESOURA 14", 2, ["TESOURA 14-1", "TESOURA 14-2"]),
    ("COMP.18", 3, ["COMP.18-1", "COMP.18-2", "COMP.18-3"]),
    ("TRANSIÇÃO 2", 1, ["TRANSIÇÃO 2"]),
])
def test_nomes_do_projetista_com_espaco_e_ponto_numeram_igual(nome, instancias, esperado):
    """12/11 (Posto N.7): as peças e os conjuntos do V2 vão ganhar os nomes do projetista (TESOURA 14, COMP.18,
    TRANSIÇÃO 2…); a regra de 12/11 (número à frente nas unidades iguais) vale igual"""
    lista = {"gerado": "2026-11-12 16:00", "totais": {"peso": 10.0 * instancias},
             "posicoes": [{"marca": "P1", "nome": "P1", "categoria": "BARRAS", "perfil": "L 25x3", "quantidade": 2 * instancias,
                           "comprimento": 1000, "peso": 10.0 * instancias, "conjuntos": [nome]}],
             "conjuntos": [{"marca": "M1", "nome": nome, "instancias": instancias, "pecas_unidade": 2,
                            "composicao": {"P1": 2}, "peso_total": 10.0 * instancias, "categoria": "TESOURAS"}]}
    its = C.itens(lista, {})
    assert [x["id"] for x in its if x["origem"] == "conjunto"] == esperado
    assert not [x for x in its if x["origem"] == "pecas"]
