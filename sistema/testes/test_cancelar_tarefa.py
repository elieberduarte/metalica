# -*- coding: utf-8 -*-
"""O Cancelar das tarefas em andamento e a etapa que não fica pendurada (DESEMPENHO N.3, 11/11/2026).

Usuário, 11/11: "Não consigo cancelar um processo quando está em andamento, preciso que crie um botão para fazer esse
cancelamento" — o cartão da COBERTURA FILIPN - GOIOÊRE dizia "Atualizando… gravando a lista e os CSVs… · 5 min 29 s".
Não era tarefa rodando: a lista tinha sido feita por um GET (abrir a aba sem a lista gravada), que não limpava a etapa,
e ela ficou pendurada no servidor (a volta do Aplicar furos de 16/10, corrigido só no POST — TestTarefaPadrao).

- a etapa tem dono (o fio da tarefa): o fim do pedido, GET ou POST, a tira; a de um fio que acabou sai sozinha;
- o Cancelar para a tarefa no próximo _progresso, antes de ela gravar no projeto (o projeto fica como estava); já
  gravando, ela termina (nunca pela metade); a de outro processo (um script) para pelo cancelar.json."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.parse import quote

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import pytest                                                    # noqa: E402
import app                                                        # noqa: E402
from projetos import ATUALIZANDO                                  # noqa: E402


@pytest.fixture()
def dados(monkeypatch):
    raiz = tempfile.mkdtemp(prefix="metalica_cancelar_")
    monkeypatch.setattr(app, "PROJETOS", raiz)
    guardado = dict(app.PROGRESSO)
    app.PROGRESSO.clear()
    getattr(app, "_CANCELAR", {}).clear()
    yield raiz
    app.PROGRESSO.clear()
    app.PROGRESSO.update(guardado)
    getattr(app, "_CANCELAR", {}).clear()


@pytest.fixture()
def servidor(dados):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _pedir(url, corpo=None):
    dados_ = None if corpo is None else json.dumps(corpo).encode("utf-8")
    r = urllib.request.Request(url, data=dados_, method="GET" if corpo is None else "POST",
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def _projeto(dados):
    """um projeto com o 3D de uma tesoura (a de test_reanalise)"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_reanalise import _tesoura
    g = app._gerente()
    s = g.criar("Cobertura Filipin")["slug"]
    doc, _ = _tesoura(222913.0, 251770.0, 12000.0, False)
    with open(g.caminho_modelo(s), "w", encoding="utf-8") as f:
        json.dump(doc.dict(), f)
    return s


def _levantar_devagar(passos, pausa, gravar_em=None):
    """o levantamento da lista no lugar do de verdade: `passos` etapas com `pausa` s cada (como as 3.734 peças do Filipin)"""
    def levantar(doc, avisar=None, **_):
        for i in range(passos):
            if gravar_em and i == passos // 2:
                with open(gravar_em, "w", encoding="utf-8") as f:     # uma gravação sem dizer "gravando…"
                    f.write("x")
            avisar("%d peças em 112 posições" % ((i + 1) * 100))
            time.sleep(pausa)
        return {"posicoes": [], "categorias": {}, "acessorios": {}, "pecas": [], "fora_do_aco": [], "estrutura_a_conferir": []}
    return levantar


# ------------------------------------------------------------------ a etapa não fica pendurada

def test_a_lista_feita_pelo_get_nao_deixa_a_etapa_pendurada(servidor, dados):
    """O caso do Filipin: a aba Lista aberta sem a lista gravada levanta pelo GET; acabou, o cartão não fica
    "Atualizando… gravando a lista e os CSVs…" e a marca atualizando.json sai."""
    s = _projeto(dados)
    st, lista = _pedir("%s/api/projetos/%s/materiais" % (servidor, quote(s)))
    assert st == 200, lista
    assert os.path.exists(os.path.join(dados, s, "detalhamento", "lista-de-materiais.json"))
    for _ in range(40):                     # o fim do pedido (finally do do_GET) roda logo depois de a resposta sair
        if s not in app.PROGRESSO:
            break
        time.sleep(0.05)
    assert app.progresso_do_projeto(s)["etapa"] == "", app.PROGRESSO.get(s)
    assert s not in app.PROGRESSO
    assert app._gerente().atualizando(s) is None
    assert app._tarefa_padrao("/api/projetos/%s/materiais" % s) is not None   # a próxima tarefa é dona da etapa dela


def test_a_etapa_de_um_fio_que_acabou_sai_sozinha(dados):
    """Qualquer caminho que deixe a etapa para trás (uma tarefa em segundo plano que morreu): o fio acabou, ela sai."""
    s = _projeto(dados)
    t = threading.Thread(target=lambda: app._progresso(s, "gravando a lista e os CSVs…", fracao=0.9))
    t.start(); t.join()
    assert os.path.exists(os.path.join(dados, s, ATUALIZANDO))        # o cartão diria "Atualizando…"
    assert app.progresso_do_projeto(s)["etapa"] == ""
    assert not os.path.exists(os.path.join(dados, s, ATUALIZANDO))
    # e pela lista de projetos (o cartão), sem ninguém perguntar o andamento antes
    t = threading.Thread(target=lambda: app._progresso(s, "x", fracao=0.5))
    t.start(); t.join()
    app._limpar_progresso_orfao()
    assert app._gerente().resumo(s)["atualizando"] is None


def test_a_tarefa_viva_nao_e_tirada(dados):
    s = _projeto(dados)
    solta = threading.Event()
    t = threading.Thread(target=lambda: (app._progresso(s, "detalhando (3 de 10)"), solta.wait(10)))
    t.start()
    time.sleep(0.2)
    try:
        assert app.progresso_do_projeto(s)["etapa"] == "detalhando (3 de 10)"
        assert app._tarefa_padrao("/api/projetos/%s/modelo" % s) is None   # não pisa na tarefa em curso
    finally:
        solta.set(); t.join()


# ------------------------------------------------------------------ o Cancelar

def test_cancelar_a_lista_no_meio_deixa_a_de_antes(servidor, dados, monkeypatch):
    """Cancelar no meio do levantamento: a rota responde "cancelada", a lista e os CSVs ficam os de antes, a etapa e a
    marca saem, o projeto abre."""
    import nucleo2d.detalhar as D
    s = _projeto(dados)
    pasta = os.path.join(dados, s, "detalhamento")
    os.makedirs(pasta, exist_ok=True)
    antes = {"posicoes": [], "titulo": "a lista de ontem, 17:40"}
    with open(os.path.join(pasta, "lista-de-materiais.json"), "w", encoding="utf-8") as f:
        json.dump(antes, f)
    with open(os.path.join(pasta, "romaneio.csv"), "w", encoding="utf-8") as f:
        f.write("o romaneio de ontem\n")
    monkeypatch.setattr(D, "levantar", _levantar_devagar(60, 0.1))
    resposta = {}
    t = threading.Thread(target=lambda: resposta.update(r=_pedir("%s/api/projetos/%s/materiais" % (servidor, quote(s)), {})))
    t.start()
    for _ in range(100):
        if "peças" in app.progresso_do_projeto(s).get("etapa", ""):
            break
        time.sleep(0.05)
    st, c = _pedir("%s/api/projetos/%s/cancelar" % (servidor, quote(s)), {})
    assert st == 200 and c["cancelando"] and not c["gravando"] and c["onde"] == "este", c
    t.join(30)
    assert not t.is_alive()
    st, corpo = resposta["r"]
    assert st == 409 and corpo.get("cancelada"), corpo
    with open(os.path.join(pasta, "lista-de-materiais.json"), encoding="utf-8") as f:
        assert json.load(f) == antes
    with open(os.path.join(pasta, "romaneio.csv"), encoding="utf-8") as f:
        assert f.read() == "o romaneio de ontem\n"
    assert app.progresso_do_projeto(s)["etapa"] == "" and app._gerente().atualizando(s) is None
    assert not app._CANCELAR
    # a próxima tarefa não herda o pedido: vai até o fim
    monkeypatch.setattr(D, "levantar", _levantar_devagar(2, 0.01))
    st, lista = _pedir("%s/api/projetos/%s/materiais" % (servidor, quote(s)), {})
    assert st == 200 and "posicoes" in lista or "perfis" in lista, lista


def test_ja_gravando_termina_inteira(dados):
    """O pedido que chega com a tarefa já gravando ("gravando …", ou um arquivo do projeto já mudado): ela termina,
    nunca pela metade, e a resposta do Cancelar diz que ela já gravava."""
    s = _projeto(dados)
    feitos = []

    def tarefa(gravar_arquivo):
        try:
            app._progresso(s, "levantando…")
            time.sleep(0.3)
            if gravar_arquivo:
                with open(os.path.join(dados, s, "modelo.json"), "w", encoding="utf-8") as f:
                    f.write("{}")
                app._progresso(s, "conferindo as marcas…")
            else:
                app._progresso(s, "gravando o modelo…")
            time.sleep(0.6)
            app._progresso(s, "últimos ajustes…")
            feitos.append("inteira")
        except app.TarefaCancelada:
            feitos.append("cancelada")
        finally:
            app._fim_progresso(s)

    for gravar_arquivo in (False, True):
        feitos.clear()
        t = threading.Thread(target=tarefa, args=(gravar_arquivo,))
        t.start()
        time.sleep(0.6)
        r = app.cancelar_tarefa(s)
        assert r["cancelando"], r
        t.join(10)
        assert feitos == ["inteira"], (gravar_arquivo, feitos)


def test_sem_tarefa_nada_a_cancelar_e_a_marca_que_sobrou_sai(dados):
    s = _projeto(dados)
    assert app.cancelar_tarefa(s) == {"cancelando": False, "gravando": False, "onde": ""}
    app._gerente().marcar_atualizando(s, "gravando a lista e os CSVs…")   # sobrou deste programa, sem tarefa
    assert app._gerente().atualizando(s)
    app.cancelar_tarefa(s)
    assert app._gerente().atualizando(s) is None


def test_cancelar_a_tarefa_de_outro_processo(dados):
    """O Cancelar do cartão para o script de obra que usa o _progresso (a remontagem do Posto, do SESI…)."""
    s = _projeto(dados)
    script = textwrap.dedent('''
        import sys, time
        sys.path.insert(0, %r)
        import app
        app.PROJETOS = %r
        try:
            for i in range(600):
                app._progresso(%r, "remontando (%%d de 600)" %% i)
                time.sleep(0.05)
            print("INTEIRA")
        except app.TarefaCancelada:
            print("CANCELADA")
    ''') % (RAIZ, dados, s)
    p = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        for _ in range(200):
            a = app._gerente().atualizando(s)
            if a and not a["este_processo"]:
                break
            time.sleep(0.1)
        else:
            pytest.fail("o script não marcou o projeto")
        r = app.cancelar_tarefa(s)
        assert r == {"cancelando": True, "gravando": False, "onde": "outro"}, r
        saida, _ = p.communicate(timeout=30)
    finally:
        if p.poll() is None:
            p.kill()
    assert saida.strip() == "CANCELADA", saida
    from projetos import CANCELAR
    assert not os.path.exists(os.path.join(dados, s, CANCELAR))       # o pedido foi consumido
