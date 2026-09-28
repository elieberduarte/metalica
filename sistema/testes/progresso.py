# -*- coding: utf-8 -*-
"""Progresso da conferência antes de publicar, para a barrinha da faixa do modo desenvolvimento.

A conferência roda em processos separados (pytest, os verificadores das telas, a bateria das
obras): cada um conta o seu andamento num arquivo só, `_conferencia.json`, ao lado deste, e o
servidor do modo desenvolvimento o devolve junto da versão (a faixa pergunta a cada 4 s).

    {"inicio", "atualizado", "fim", "ok", "texto",
     "etapas": [{"nome", "est" (s, a duração da rodada anterior), "ini", "fim", "ok", "feito", "total"}]}

Só a conferência (`antes_de_publicar.py`) cria o arquivo e liga `METALICA_CONFERENCIA` para os
processos filhos; o verificador ou a bateria rodados sozinhos não mexem nele.
"""
import json
import os
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
#: a conferência da noite roda numa cópia limpa do repositório e grava o andamento aqui, no do
#: modo desenvolvimento, pela variável (a barrinha do servidor de desenvolvimento acompanha)
ARQ = os.environ.get("METALICA_CONFERENCIA_ARQ") or os.path.join(AQUI, "_conferencia.json")
DURACOES = os.path.join(os.path.dirname(ARQ), "_conferencia_duracoes.json")
#: s, quando não há rodada anterior medida
PADRAO = {"testes automáticos": 90.0, "verificadores das telas": 1000.0, "bateria das obras": 200.0}
_trava = threading.Lock()


def _ler(caminho=None):
    try:
        with open(caminho or ARQ, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _gravar(d, caminho=None):
    caminho = caminho or ARQ
    d["atualizado"] = time.time()
    tmp = caminho + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, caminho)
    except OSError:
        pass                                   # o progresso nunca derruba a conferência


def ativo() -> bool:
    return os.environ.get("METALICA_CONFERENCIA") == "1"


def iniciar(nomes):
    """a conferência começa com estas etapas (na ordem)"""
    dur = _ler(DURACOES) or {}
    d = {"inicio": time.time(), "fim": None, "ok": None, "texto": "",
         "etapas": [{"nome": n, "est": float(dur.get(n) or PADRAO.get(n, 120.0)), "ini": None, "fim": None,
                     "ok": None, "feito": None, "total": None} for n in nomes]}
    with _trava:
        _gravar(d)
    os.environ["METALICA_CONFERENCIA"] = "1"


def _mudar(fn):
    if not ativo():
        return
    with _trava:
        d = _ler()
        if not d or d.get("fim"):
            return
        fn(d)
        _gravar(d)


def _etapa(d, nome):
    return next((e for e in d["etapas"] if e["nome"] == nome), None)


def comecar(nome):
    def fn(d):
        e = _etapa(d, nome)
        if e:
            e["ini"] = time.time()
        d["texto"] = ""
    _mudar(fn)


def passo(nome, feito, total, texto=""):
    """dentro da etapa: `feito` de `total` (verificadores, obras), e o que está rodando"""
    def fn(d):
        e = _etapa(d, nome)
        if e:
            e["ini"] = e["ini"] or time.time()
            e["feito"], e["total"] = int(feito), int(total)
        d["texto"] = texto
    _mudar(fn)


def terminar(nome, ok):
    agora = time.time()
    dur = {}

    def fn(d):
        e = _etapa(d, nome)
        if e:
            e["fim"], e["ok"] = agora, bool(ok)
            if e["ini"]:
                dur[nome] = round(agora - e["ini"], 1)
        d["texto"] = ""
    _mudar(fn)
    if dur:
        todas = _ler(DURACOES) or {}
        todas.update(dur)
        _gravar(todas, DURACOES)


def fim(ok):
    def fn(d):
        d["fim"], d["ok"] = time.time(), bool(ok)
    _mudar(fn)
