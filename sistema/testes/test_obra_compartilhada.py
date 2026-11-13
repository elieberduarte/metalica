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
