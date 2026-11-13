# -*- coding: utf-8 -*-
"""A obra compartilhada (13/11/2026, passo 1a): o módulo do PC (obra_compartilhada.py) contra uma nuvem falsa em
memória e o lado do dono (obra_compartilhada_dev.py) contra um SQLite com as mesmas tabelas do D1. O caminho de ponta
a ponta com o Worker de verdade está em verificadores/verif_obra_compartilhada_nuvem.py."""
import json
import os
import sqlite3
import sys

import pytest

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAIZ = os.path.dirname(BASE)
sys.path.insert(0, BASE)

import obra_compartilhada as OC  # noqa: E402

OBRA = "0123456789abcdef0123456789abcdef"


class Nuvem:
    """o Worker em memória: papel por chave, eventos com seq, INSERT OR IGNORE pelo id"""

    def __init__(self):
        self.papel = {"dev": "dono", "fer": "editor", "lei": "leitor"}
        self.pessoa = {"dev": "Elieber", "fer": "Fernando", "lei": "Leitor"}
        self.eventos = []
        self.fora_do_ar = False
        self.eu = "dev"

    def pedir(self, metodo, rota, corpo=None, timeout=6.0):
        if self.fora_do_ar:
            raise OC.ErroObra("sem conexão com a nuvem do Metálica (timed out)")
        papel = self.papel.get(self.eu)
        if not papel:
            raise OC.ErroObra("esta licença não tem acesso a esta obra compartilhada — peça ao responsável", 403)
        base = {"obra_id": OBRA, "papel": papel, "pessoa": self.pessoa[self.eu]}
        if metodo == "GET":
            depois = int(rota.split("depois=")[1])
            evs = [e for e in self.eventos if e["seq"] > depois]
            return dict(base, eventos=evs, ultimo=evs[-1]["seq"] if evs else depois, mais=False)
        if papel not in OC.APONTAM:
            raise OC.ErroObra("o seu papel nesta obra é %s: só vê, não aponta" % papel, 403)
        aceitos, recusados = [], []
        ja = {e["id"] for e in self.eventos}
        for e in corpo["eventos"]:
            if int(e.get("quantidade") or 0) < 1:
                recusados.append({"id": e["id"], "erro": "evento inválido"})
                continue
            aceitos.append(e["id"])
            if e["id"] not in ja:
                self.eventos.append(dict(e, quem=self.pessoa[self.eu], seq=len(self.eventos) + 1, maquina="pc"))
        return {"aceitos": aceitos, "recusados": recusados}


@pytest.fixture
def nuvem(monkeypatch):
    n = Nuvem()
    monkeypatch.setattr(OC, "_pedir", n.pedir)
    monkeypatch.setattr(OC, "_maquina", lambda: "pc-" + n.eu)
    return n


def _projeto(tmp_path, nome, obra_id=OBRA):
    p = tmp_path / nome
    (p / "producao").mkdir(parents=True)
    (p / "projeto.json").write_text(json.dumps({"nome": "POSTO", "compartilhada": {"obra_id": obra_id, "nome": "POSTO"}}), encoding="utf-8")
    return str(p)


_N = [0]


def _apontar(pasta, item, q=1, estorno_de=None):
    _N[0] += 1
    ev = {"id": "e%08d" % _N[0], "quando": "2026-11-13T10:00:00", "data": "2026-11-13", "quem": "o PC diz", "etapa": "producao",
          "item": item, "refs": ["M1"], "quantidade": q, "kg": 5.0 * q, "estorno_de": estorno_de, "obs": ""}
    OC._acrescentar(pasta, [ev])
    OC.na_fila(pasta, ev["id"])
    return ev


def test_obra_sem_obra_id_nao_e_compartilhada(tmp_path):
    p = tmp_path / "x"
    p.mkdir()
    (p / "projeto.json").write_text(json.dumps({"nome": "X", "compartilhada": {"obra_id": "posto"}}), encoding="utf-8")
    assert OC.info(str(p)) is None and OC.estado(str(p)) is None and OC.sincronizar(str(p)) is None
    OC.na_fila(str(p), "e1")                                 # não faz nada
    assert not (p / "producao" / OC.ESTADO).exists()


def test_apontamento_sobe_e_chega_no_outro_pc_no_formato_do_controle(tmp_path, nuvem):
    dev, fer = _projeto(tmp_path, "dev"), _projeto(tmp_path, "fer")
    nuvem.eu = "fer"
    for it in ("TESOURA 14-1", "COMP 18-1", "PAINEL 15"):
        _apontar(fer, it)
    assert OC.estado(fer)["pendentes"] == 3
    r = OC.sincronizar(fer)
    assert (r["enviados"], r["pendentes"], r["papel"], r["erro"]) == (3, 0, "editor", "")
    nuvem.eu = "dev"
    r = OC.sincronizar(dev)
    ls = OC._ler_eventos(dev)
    assert r["recebidos"] == 3 and [x["item"] for x in ls] == ["TESOURA 14-1", "COMP 18-1", "PAINEL 15"]
    assert all(list(x) == list(OC._CAMPOS) for x in ls)        # o formato do apontamentos.jsonl do Controle
    assert {x["quem"] for x in ls} == {"Fernando"}             # o "quem" da nuvem (a licença), não o do PC
    assert OC.sincronizar(dev)["recebidos"] == 0 and len(OC._ler_eventos(dev)) == 3


def test_o_proprio_evento_volta_da_nuvem_sem_duplicar(tmp_path, nuvem):
    dev = _projeto(tmp_path, "dev")
    _apontar(dev, "T1")
    OC.sincronizar(dev)
    OC.sincronizar(dev)
    assert len(OC._ler_eventos(dev)) == 1


def test_sem_internet_fica_na_fila_e_sobe_depois(tmp_path, nuvem):
    fer = _projeto(tmp_path, "fer")
    nuvem.eu = "fer"
    _apontar(fer, "T1")
    nuvem.fora_do_ar = True
    r = OC.sincronizar(fer)
    assert r["pendentes"] == 1 and "sem conexão" in r["erro"]
    nuvem.fora_do_ar = False
    r = OC.sincronizar(fer)
    assert (r["enviados"], r["pendentes"], r["erro"]) == (1, 0, "")


def test_leitor_recebe_mas_nao_aponta(tmp_path, nuvem):
    dev, lei = _projeto(tmp_path, "dev"), _projeto(tmp_path, "lei")
    _apontar(dev, "T1")
    OC.sincronizar(dev)
    nuvem.eu = "lei"
    r = OC.sincronizar(lei)
    assert r["recebidos"] == 1 and r["papel"] == "leitor" and r["pode_apontar"] is False
    _apontar(lei, "T2")
    r = OC.sincronizar(lei)
    assert r["pendentes"] == 1 and "leitor" in r["erro"]
    assert len(nuvem.eventos) == 1


def test_sem_acesso(tmp_path, nuvem):
    fora = _projeto(tmp_path, "fora")
    nuvem.eu = "ninguem"
    nuvem.pessoa["ninguem"] = "?"
    r = OC.sincronizar(fora)
    assert "acesso" in r["erro"] and r["papel"] is None


def test_projeto_que_veio_de_outro_pc_nao_sobe_em_nome_de_quem_recebeu(tmp_path, nuvem):
    import shutil
    fer = _projeto(tmp_path, "fer")
    nuvem.eu = "fer"
    nuvem.fora_do_ar = True
    _apontar(fer, "T1")                                       # ficou na fila do PC do Fernando
    OC.sincronizar(fer)
    outro = str(tmp_path / "outro")
    shutil.copytree(fer, outro)
    nuvem.fora_do_ar = False
    nuvem.eu = "dev"                                          # outro computador
    assert OC.estado(outro)["pendentes"] == 0
    assert OC.sincronizar(outro)["enviados"] == 0 and nuvem.eventos == []


def test_evento_invalido_sai_da_fila(tmp_path, nuvem):
    dev = _projeto(tmp_path, "dev")
    ruim = _apontar(dev, "T1", q=0)
    r = OC.sincronizar(dev)
    assert r["pendentes"] == 0 and ruim["id"] in OC._ler_estado(dev, OBRA)["recusados"]


def test_iniciar_poe_na_fila_o_que_ja_existia(tmp_path, nuvem):
    dev = _projeto(tmp_path, "dev")
    OC._acrescentar(dev, [{"id": "antigo1", "etapa": "producao", "item": "T1", "quantidade": 1},
                          {"id": "antigo2", "etapa": "pintura", "item": "T1", "quantidade": 1}])
    assert OC.estado(dev)["pendentes"] == 0
    OC.iniciar(dev)
    assert OC.estado(dev)["pendentes"] == 2
    assert OC.sincronizar(dev)["enviados"] == 2


# ------------------------------------------------------------------ o lado do dono (dev), num SQLite com as tabelas do D1
@pytest.fixture
def d1(monkeypatch):
    import licencas_dev
    import obra_compartilhada_dev as D
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    for arq in (os.path.join(RAIZ, "servicos", "licencas", "schema.sql"),
                os.path.join(RAIZ, "servicos", "celular", "migracao-obra-compartilhada.sql")):
        db.executescript(open(arq, encoding="utf-8").read())
    db.execute("INSERT INTO licencas (chave, pessoa, maquinas_max, ativa, criada) VALUES ('MTL-DONO', 'Elieber', 2, 1, '2026-11-13'),"
               " ('MTL-FERN', 'Fernando', 2, 1, '2026-11-13'), ('MTL-MATE', 'Mateus', 2, 1, '2026-11-13')")

    def _sql(sql, params=None):
        try:
            cur = db.execute(sql, list(params or []))
        except sqlite3.OperationalError as e:
            raise licencas_dev.ErroLicencas("o banco das licenças recusou: " + str(e))
        db.commit()
        return [dict(r) for r in cur.fetchall()]
    monkeypatch.setattr(licencas_dev, "_sql", _sql)
    monkeypatch.setattr(D, "_minha_chave", lambda: "MTL-DONO")
    monkeypatch.setattr(OC, "sincronizar", lambda pasta, **k: {"ok": True})
    return D, _sql


class Gerente:
    def __init__(self, raiz):
        self.raiz = raiz

    def _existente(self, s):
        return os.path.join(self.raiz, s)

    def ler(self, s):
        return json.load(open(os.path.join(self.raiz, s, "projeto.json"), encoding="utf-8"))

    def _atualizar(self, s, **c):
        p = self.ler(s)
        p.update(c)
        json.dump(p, open(os.path.join(self.raiz, s, "projeto.json"), "w", encoding="utf-8"))

    def listar(self):
        return [{"slug": s, "nome": self.ler(s).get("nome")} for s in sorted(os.listdir(self.raiz))]


def test_dono_compartilha_da_e_tira_acesso(tmp_path, d1):
    D, sql = d1
    for s in ("posto-de-combustivel", "outra"):
        (tmp_path / s / "producao").mkdir(parents=True)
        (tmp_path / s / "projeto.json").write_text(json.dumps({"nome": s.upper()}), encoding="utf-8")
    OC._acrescentar(str(tmp_path / "posto-de-combustivel"), [{"id": "velho1", "etapa": "producao", "item": "T1", "quantidade": 1}])
    g = Gerente(str(tmp_path))
    p = D.painel(g)
    assert p["obras"] == [] and len(p["locais"]) == 2 and len(p["pessoas"]) == 3

    r = D.compartilhar(g, "posto-de-combustivel")
    oid = r["obra_id"]
    assert OC.info(str(tmp_path / "posto-de-combustivel"))["obra_id"] == oid       # o obra_id fixo no projeto.json
    assert OC.estado(str(tmp_path / "posto-de-combustivel"))["pendentes"] == 1      # o que já existia vai subir
    assert D.compartilhar(g, "posto-de-combustivel")["obra_id"] == oid               # compartilhar de novo não troca o código
    D.acesso(oid, "MTL-FERN", "editor")
    p = D.painel(g)
    o = p["obras"][0]
    assert o["slug"] == "posto-de-combustivel" and {(a["pessoa"], a["papel"]) for a in o["acessos"]} == {("Elieber", "dono"), ("Fernando", "editor")}
    D.acesso(oid, "MTL-FERN", "leitor")
    assert sql("SELECT papel FROM obra_acessos WHERE chave = 'MTL-FERN'")[0]["papel"] == "leitor"
    with pytest.raises(ValueError):
        D.acesso(oid, "MTL-DONO", "leitor")                                          # o dono não muda de papel
    with pytest.raises(ValueError):
        D.acesso(oid, "MTL-FERN", "dono")                                            # só um dono
    with pytest.raises(ValueError):
        D.acesso(oid, "MTL-NINGUEM", "editor")
    D.acesso(oid, "MTL-FERN", "")
    assert sql("SELECT COUNT(*) AS n FROM obra_acessos WHERE chave = 'MTL-FERN'")[0]["n"] == 0


def test_painel_sem_as_tabelas_avisa(tmp_path, monkeypatch):
    import licencas_dev
    import obra_compartilhada_dev as D

    def _sql(sql, params=None):
        raise licencas_dev.ErroLicencas("o banco das licenças recusou: no such table: obras")
    monkeypatch.setattr(licencas_dev, "_sql", _sql)
    assert D.painel(Gerente(str(tmp_path)))["sem_tabelas"] is True


# ------------------------------------------------------------------ o gancho no Controle (producao/web.py)
@pytest.fixture
def controle_web(tmp_path, monkeypatch, nuvem):
    """o Controle de dois computadores sobre a mesma obra (pastas diferentes, o mesmo obra_id) e uma obra só local"""
    from producao import web
    from test_producao_controle import _lista
    pastas = {}
    for s, comp in (("dev", True), ("fer", True), ("lei", True), ("local", False)):
        p = tmp_path / s
        (p / "detalhamento").mkdir(parents=True)
        json.dump(_lista(), open(p / "detalhamento" / "lista-de-materiais.json", "w", encoding="utf-8"), ensure_ascii=False)
        pj = {"nome": "OBRA " + s}
        if comp:
            pj["compartilhada"] = {"obra_id": OBRA, "nome": "OBRA"}
        json.dump(pj, open(p / "projeto.json", "w", encoding="utf-8"))
        pastas[s] = str(p)

    class _G:
        @staticmethod
        def ler(s):
            return json.load(open(os.path.join(pastas[s], "projeto.json"), encoding="utf-8"))

        @staticmethod
        def _existente(s):
            return pastas[s]

    class _App:
        @staticmethod
        def _gerente():
            return _G
    monkeypatch.setattr(web, "_app", lambda: _App)
    monkeypatch.setattr(web, "_quem", lambda: nuvem.pessoa.get(nuvem.eu, "?"))
    return web, pastas


def _ver(web, slug):
    from test_producao_controle import _H
    h = _H("/api/producao/controle?projeto=" + slug)
    assert web.rota_get(h, "/api/producao/controle")
    return h.resposta


def _post(web, rota, corpo):
    from test_producao_controle import _H
    h = _H(rota)
    assert web.rota_post(h, rota, corpo)
    return h.resposta


def test_controle_de_obra_so_local_nao_toca_a_nuvem(controle_web, nuvem):
    web, pastas = controle_web
    nuvem.fora_do_ar = True                                  # se tentasse ir à nuvem, daria erro
    assert _ver(web, "local")["nuvem"] is None
    r = _post(web, "/api/producao/apontar", {"projeto": "local", "item": "T38-1", "etapa": "producao", "quantidade": 1})
    assert r["ok"] and r["nuvem"] is None
    assert not os.path.exists(os.path.join(pastas["local"], "producao", OC.ESTADO))


def test_o_que_o_fernando_aponta_aparece_no_controle_do_dev(controle_web, nuvem):
    web, pastas = controle_web
    nuvem.eu = "fer"
    for item in ("T38-1", "T74"):
        r = _post(web, "/api/producao/apontar", {"projeto": "fer", "item": item, "etapa": "producao", "quantidade": 1})
        assert r["nuvem"]["pendentes"] == 0 and r["nuvem"]["papel"] == "editor"
    r = _post(web, "/api/producao/apontar", {"projeto": "fer", "item": "T.C.1", "etapa": "producao", "quantidade": 30})
    assert len(nuvem.eventos) == 3
    nuvem.eu = "dev"
    d = _ver(web, "dev")
    feito = {x["id"]: x["feito"].get("producao", 0) for x in d["itens"]}
    assert (feito["T38-1"], feito["T74"], feito["T.C.1"], feito["T38-2"]) == (1, 1, 30, 0)
    assert d["nuvem"]["papel"] == "dono" and {e["quem"] for e in d["eventos"]} == {"Fernando"}
    # o dev estorna um do Fernando; o estorno chega ao Fernando
    ev = next(e for e in d["eventos"] if e["item"] == "T74")
    _post(web, "/api/producao/estornar", {"projeto": "dev", "evento": ev["id"]})
    nuvem.eu = "fer"
    d = _ver(web, "fer")
    assert {x["id"]: x["feito"].get("producao", 0) for x in d["itens"]}["T74"] == 0


def test_leitor_nao_aponta_pelo_controle(controle_web, nuvem):
    web, pastas = controle_web
    from nucleo.base import ErroDeDados
    nuvem.eu = "lei"
    d = _ver(web, "lei")
    assert d["nuvem"]["papel"] == "leitor" and d["nuvem"]["pode_apontar"] is False
    with pytest.raises(ErroDeDados, match="só vê"):
        _post(web, "/api/producao/apontar", {"projeto": "lei", "item": "T38-1", "etapa": "producao", "quantidade": 1})
    assert OC._ler_eventos(pastas["lei"]) == [] and nuvem.eventos == []


def test_sem_internet_o_controle_aponta_e_a_fila_espera(controle_web, nuvem):
    web, pastas = controle_web
    nuvem.eu = "fer"
    nuvem.fora_do_ar = True
    r = _post(web, "/api/producao/apontar", {"projeto": "fer", "item": "T38-2", "etapa": "pintura", "quantidade": 1})
    assert r["ok"] and r["nuvem"]["pendentes"] == 1 and "sem conexão" in r["nuvem"]["erro"]
    d = _ver(web, "fer")
    assert {x["id"]: x["feito"].get("pintura", 0) for x in d["itens"]}["T38-2"] == 1     # o local segue valendo
    nuvem.fora_do_ar = False
    d = _ver(web, "fer")
    assert d["nuvem"]["pendentes"] == 0 and not d["nuvem"]["erro"] and len(nuvem.eventos) == 1


def test_a_tela_do_controle_mostra_o_selo_e_esconde_apontar_do_leitor():
    js = open(os.path.join(BASE, "web", "producao", "controle.js"), encoding="utf-8").read()
    assert "seloDaNuvem(D.nuvem)" in js and "esperando a internet" in js
    assert js.count("podeApontar()") >= 2                    # Apontar e Estornar
    assert "setInterval" in js and "dialog[open]" in js        # relê a cada minuto, não no meio de um apontamento


def test_a_ancora_viaja_e_volta_no_fim_do_evento_so_quando_existe(tmp_path, nuvem):
    """13/11 (CONTROLE): o apontamento de unidade de conjunto leva "ancora" (ids das peças do 3D) para seguir a peça
    quando o Detalhar muda o nome do item; a nuvem guarda e devolve; o evento sem âncora continua sem a chave"""
    dev, fer = _projeto(tmp_path, "dev"), _projeto(tmp_path, "fer")
    nuvem.eu = "fer"
    com = _apontar(fer, "TESOURA 1-1")
    linhas = OC._ler_eventos(fer)
    linhas[-1]["ancora"] = ["p101", "p102", "p103"]
    open(os.path.join(fer, "producao", OC.EVENTOS), "w", encoding="utf-8").write("".join(json.dumps(x) + "\n" for x in linhas))
    _apontar(fer, "T.C.1")
    OC.sincronizar(fer)
    nuvem.eu = "dev"
    OC.sincronizar(dev)
    a, b = OC._ler_eventos(dev)
    assert a["id"] == com["id"] and list(a)[-1] == "ancora" and a["ancora"] == ["p101", "p102", "p103"]
    assert "ancora" not in b and list(b) == list(OC._CAMPOS)


def test_apontar_varios_sobe_em_lotes_que_cabem_no_d1(tmp_path, nuvem, monkeypatch):
    """O "apontar vários" do Controle (13/11) manda até 2.000 itens de uma vez. Cada evento é uma consulta no D1, e o plano
    gratuito da Cloudflare aceita 50 por chamada: os POSTs levam no máximo 40. Numa sincronização sobe o que cabe no
    prazo; o resto fica na fila e sobe na próxima, sem perder nem repetir."""
    fer = _projeto(tmp_path, "fer")
    nuvem.eu = "fer"
    tamanhos = []
    pedir = nuvem.pedir

    def contando(metodo, rota, corpo=None, timeout=6.0):
        if metodo == "POST":
            tamanhos.append(len(corpo["eventos"]))
        return pedir(metodo, rota, corpo, timeout)
    monkeypatch.setattr(OC, "_pedir", contando)
    evs = [{"id": "v%06d" % i, "quando": "2026-11-13T11:00:00", "data": "2026-11-13", "quem": "x", "etapa": "producao",
            "item": "COMP %d-1" % i, "refs": ["M%d" % i], "quantidade": 1, "kg": 2.0, "estorno_de": None, "obs": ""}
           for i in range(2000)]
    OC._acrescentar(fer, evs)
    for ev in evs:
        OC.na_fila(fer, ev["id"])
    # a nuvem lenta: o prazo acaba depois do 2º lote
    relogio = iter([0.0, 0.0, 1.0, OC.PRAZO_ENVIO + 1] + [10 ** 6] * 100)
    monkeypatch.setattr(OC.time, "monotonic", lambda: next(relogio))
    r = OC.sincronizar(fer)
    assert max(tamanhos) <= 40 and r["enviados"] == 3 * OC.POR_PEDIDO and r["pendentes"] == 2000 - 3 * OC.POR_PEDIDO
    monkeypatch.undo()
    monkeypatch.setattr(OC, "_pedir", contando)
    monkeypatch.setattr(OC, "_maquina", lambda: "pc-fer")
    r = OC.sincronizar(fer)
    assert r["pendentes"] == 0 and max(tamanhos) <= 40
    assert len(nuvem.eventos) == 2000 and len({e["id"] for e in nuvem.eventos}) == 2000
