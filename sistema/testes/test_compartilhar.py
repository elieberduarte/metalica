# -*- coding: utf-8 -*-
"""Uma obra para outro usuário (compartilhar.py, 21/10 — o usuário: "enviar o projeto para outro usuário por dentro do
sistema sem precisar exportar o pacote da obra"): o pacote sobe em partes, a pessoa vê em recebidos, abre (as partes
conferidas pelo SHA-1, o projeto importado como novo, nunca por cima) e a nuvem apaga; recusar também apaga. A nuvem aqui
é um dublê em memória com as regras do Worker (servicos/celular/src/celular.js, rotas /pc/envio…, /pc/recebidos…)."""
import hashlib
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compartilhar as C                                    # noqa: E402
from projetos import Projetos                               # noqa: E402


class Nuvem:
    """o Worker em memória: partes no "R2", envios no "banco"; quem pede é a licença `eu`"""
    def __init__(self):
        self.partes, self.envios, self.eu = {}, [], "A"
        self.pessoas = {"pa": ("A", "Elieber"), "pb": ("B", "Andrey")}

    def pedir(self, metodo, rota, corpo=None, tipo="application/json", timeout=60.0, bruto=False):
        if rota == "/pc/pessoas":
            return {"pessoas": [{"id": i, "pessoa": n, "eu": c == self.eu} for i, (c, n) in self.pessoas.items()]}
        if rota == "/pc/envio/faltam":
            return {"faltam": [s for s in corpo["sha1s"] if s not in self.partes]}
        m = re.match(r"^/pc/envio/parte/([0-9a-f]{40})$", rota)
        if m:
            assert hashlib.sha1(corpo).hexdigest() == m.group(1) and len(corpo) <= C.PARTE
            self.partes[m.group(1)] = bytes(corpo)
            return {"ok": True}
        if rota == "/pc/envios":
            alvo = self.pessoas.get(corpo["para"])
            if not alvo:
                raise C.ErroCompartilhar("pessoa não encontrada")
            assert all(p["sha1"] in self.partes for p in corpo["partes"])
            self.envios.append(dict(corpo, id=len(self.envios) + 1, de=self.pessoas["pa"][1] if self.eu == "A" else "?",
                                    para_chave=alvo[0], estado="pendente", bytes=sum(p["bytes"] for p in corpo["partes"])))
            return {"id": len(self.envios), "para": alvo[1], "eu": alvo[0] == self.eu}
        if rota.startswith("/pc/recebidos") and metodo == "GET" and "/parte/" not in rota:
            return {"recebidos": [e for e in self.envios if e["para_chave"] == self.eu and e["estado"] == "pendente"]}
        m = re.match(r"^/pc/recebidos/(\d+)(?:/parte/([0-9a-f]{40})|/(recebido|recusar))$", rota)
        if m:
            e = self.envios[int(m.group(1)) - 1]
            if m.group(2):
                return self.partes[m.group(2)]
            e["estado"] = "recebido" if m.group(3) == "recebido" else "recusado"
            usadas = {p["sha1"] for x in self.envios if x["estado"] == "pendente" for p in x["partes"]}
            for p in e["partes"]:
                if p["sha1"] not in usadas:
                    self.partes.pop(p["sha1"], None)
            return {"ok": True}
        raise AssertionError("rota inesperada " + rota)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    nuvem = Nuvem()
    monkeypatch.setattr(C, "_pedir", nuvem.pedir)
    monkeypatch.setattr(C, "PARTE", 4096)                      # partes pequenas: o pacote sai em várias
    remetente, destinatario = Projetos(str(tmp_path / "a")), Projetos(str(tmp_path / "b"))
    os.makedirs(tmp_path / "a"); os.makedirs(tmp_path / "b")
    s = remetente.criar("PRATI CD - COMPLETO")["slug"]
    with open(os.path.join(remetente.pasta(s), "modelo.json"), "w", encoding="utf-8") as f:
        json.dump({"nome": "PRATI", "dados": os.urandom(30000).hex()}, f)      # ~60 kB: muitas partes
    return nuvem, remetente, destinatario, s


def test_enviar_e_abrir_do_outro_lado(ambiente):
    nuvem, a, b, s = ambiente
    assert [p["pessoa"] for p in C.pessoas()] == ["Elieber", "Andrey"]
    etapas = []
    r = C.enviar(a, s, "pb", lambda et, fr=None: etapas.append(et))
    assert r["para"] == "Andrey" and len(nuvem.envios[0]["partes"]) > 3
    assert any("enviando a obra" in e for e in etapas)        # a barra de andamento
    nuvem.eu = "B"                                             # agora no computador do Andrey
    rec = C.recebidos()
    assert len(rec) == 1 and rec[0]["nome"] == "PRATI CD - COMPLETO"
    resumo = C.abrir(b, rec[0]["id"])
    assert resumo["nome"] == "PRATI CD - COMPLETO" and resumo["recebido_de"] == "Elieber"
    copia = os.path.join(b.pasta(resumo["slug"]), "modelo.json")
    assert open(copia, encoding="utf-8").read() == open(os.path.join(a.pasta(s), "modelo.json"), encoding="utf-8").read()
    assert C.recebidos() == [] and nuvem.partes == {}         # recebido: a nuvem apagou o pacote
    # o mesmo nome de novo: vira outro projeto, nunca por cima
    nuvem.eu = "A"
    C.enviar(a, s, "pb")
    nuvem.eu = "B"
    r2 = C.abrir(b, C.recebidos()[0]["id"])
    assert r2["slug"] != resumo["slug"] and os.path.isdir(b.pasta(resumo["slug"]))


def test_parte_estragada_nao_importa(ambiente):
    nuvem, a, b, s = ambiente
    C.enviar(a, s, "pb")
    nuvem.eu = "B"
    sha = nuvem.envios[0]["partes"][1]["sha1"]
    nuvem.partes[sha] = b"x" + nuvem.partes[sha][1:]
    with pytest.raises(C.ErroCompartilhar, match="diferente"):
        C.abrir(b, C.recebidos()[0]["id"])
    assert [n for n in os.listdir(b.raiz) if not n.startswith(".")] == []   # nada importado
    assert len(C.recebidos()) == 1                            # e o envio continua lá para tentar de novo


def test_recusar_apaga_da_nuvem(ambiente):
    nuvem, a, b, s = ambiente
    C.enviar(a, s, "pb")
    nuvem.eu = "B"
    C.recusar(C.recebidos()[0]["id"])
    assert C.recebidos() == [] and nuvem.partes == {}


def test_sem_licenca_avisa(monkeypatch):
    monkeypatch.setattr(C.licenca, "token", lambda: "")
    with pytest.raises(C.ErroCompartilhar, match="licença"):
        C._pedir("GET", "/pc/pessoas")


def _modelo(g, s, texto):
    with open(os.path.join(g.pasta(s), "modelo.json"), "w", encoding="utf-8") as f:
        json.dump({"nome": "PRATI", "rev": texto}, f)


def _ler_modelo(g, s):
    with open(os.path.join(g.pasta(s), "modelo.json"), encoding="utf-8") as f:
        return json.load(f)["rev"]


def test_enviar_atualizacao_substitui_a_copia_e_guarda_a_de_antes(ambiente):
    """28/10, o usuário (a obra enviada à Mariana): "criar uma opção de enviar revisão ou enviar atualização, para esses
    ajustes que estamos fazendo enviar para o projeto dela também, não automaticamente". A 2ª remessa da mesma obra
    aparece com a cópia dela; "Atualizar" põe a versão nova no lugar (mesma pasta, mesmo nome na lista) e a de antes
    — com o que ela mexeu — fica num projeto arquivado. Nada se perde."""
    nuvem, a, b, s = ambiente
    _modelo(a, s, "R0")
    C.enviar(a, s, "pb")
    assert [x["pessoa"] for x in a.ler(s)["envios"]] == ["Andrey"]          # a quem a obra já foi
    nuvem.eu = "B"
    copia = C.abrir(b, C.recebidos()[0]["id"])["slug"]
    with open(os.path.join(b.pasta(copia), "anotacao-da-mariana.txt"), "w", encoding="utf-8") as f:
        f.write("mexi aqui")
    # o remetente valida um ajuste no modelo e manda a atualização, com o que mudou
    nuvem.eu = "A"
    _modelo(a, s, "R1")
    C.enviar(a, s, "pb", nota="SP5 dos brises da fachada G")
    assert len(a.ler(s)["envios"]) == 1 and a.ler(s)["envios"][0]["nota"] == "SP5 dos brises da fachada G"
    nuvem.eu = "B"
    rec = C.recebidos_com_copias(b)
    assert [c["slug"] for c in rec[0]["copias"]] == [copia]               # a tela oferece "Atualizar a minha cópia"
    r = C.abrir(b, rec[0]["id"], atualizar=copia)
    assert r["slug"] == copia and r["nota"] == "SP5 dos brises da fachada G"
    assert _ler_modelo(b, copia) == "R1"                                  # a versão nova no lugar
    assert b.ler(copia)["importado"]["atualizacoes"] == 1 and not b.ler(copia).get("arquivado")
    guardada = r["copia_anterior"]
    assert _ler_modelo(b, guardada) == "R0" and b.ler(guardada).get("arquivado")
    assert os.path.isfile(os.path.join(b.pasta(guardada), "anotacao-da-mariana.txt"))
    assert "antes da atualização" in b.ler(guardada)["nome"]
    assert C.recebidos() == [] and nuvem.partes == {}
    assert [c["slug"] for c in b.copias_de(s)] == [copia]                 # a guardada (arquivada) não é mais oferecida


def test_atualizacao_recusa_obra_aberta_e_obra_de_outra_origem(ambiente):
    nuvem, a, b, s = ambiente
    _modelo(a, s, "R0")
    C.enviar(a, s, "pb")
    nuvem.eu = "B"
    copia = C.abrir(b, C.recebidos()[0]["id"])["slug"]
    nuvem.eu = "A"
    _modelo(a, s, "R1")
    C.enviar(a, s, "pb")
    nuvem.eu = "B"
    envio = C.recebidos()[0]["id"]
    b.marcar_aberto(copia, "PC-MARIANA", "mariana")                        # aberta numa janela: não mexe
    with pytest.raises(C.ErroCompartilhar, match="aberta"):
        C.abrir(b, envio, atualizar=copia)
    os.remove(os.path.join(b.pasta(copia), "aberto.json"))
    b._atualizar(copia, criado="2020-01-01 00:00:00")                      # uma obra homônima de outra origem
    with pytest.raises(Exception, match="não é a mesma"):
        C.abrir(b, envio, atualizar=copia)
    assert _ler_modelo(b, copia) == "R0"                                  # a cópia ficou como estava
    assert sorted(n for n in os.listdir(b.raiz) if not n.startswith(".")) == [copia]   # e nada sobrou ao lado
    assert len(C.recebidos()) == 1                                        # o envio continua para abrir como novo


def test_a_obra_recebida_nao_chega_travada_em_atualizando(ambiente, tmp_path):
    """28/10 (achado no verif_compartilhar_ui, na atualização da obra enviada à Mariana): o envio empacota a obra com a
    barra de andamento ligada — o atualizando.json ("empacotando a obra…") ia dentro do pacote, e do outro lado a cópia
    aparecia "Atualizando…", sem Abrir e recusando gravar, até 15 min depois do envio. Nem o pacote novo leva a marca,
    nem o pacote antigo que a tenha deixa a marca na obra importada."""
    import zipfile
    nuvem, a, b, s = ambiente
    a.marcar_atualizando(s, "empacotando a obra…", 0.02, quem="enviar")    # como o _progresso do servidor no envio
    pacote = a.exportar(s)["caminho"]
    with zipfile.ZipFile(pacote) as z:
        assert "atualizando.json" not in z.namelist()
    # um pacote de antes desta correção, com a marca dentro
    antigo = str(tmp_path / "antigo.metalica.zip")
    with zipfile.ZipFile(pacote) as z, zipfile.ZipFile(antigo, "w") as w:
        for n in z.namelist():
            w.writestr(n, z.read(n))
        w.writestr("atualizando.json", open(os.path.join(a.pasta(s), "atualizando.json"), "rb").read())
        w.writestr("aberto.json", json.dumps({"quando": __import__("time").time(), "maquina": "PC-ELIEBER", "usuario": "e"}))
    novo = b.importar_pacote(antigo)["slug"]
    assert b.atualizando(novo) is None and b.aberto_por(novo) is None
    assert not os.path.exists(os.path.join(b.pasta(novo), "atualizando.json"))
