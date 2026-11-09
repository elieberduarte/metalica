# -*- coding: utf-8 -*-
"""O modo dev não reinicia no meio da tarefa (19/10/2026): o Reanalisar estrutura do CD Bom Dia (80 s) dava "Failed to
fetch" porque outro chat salvou um .py e o vigia (dev.py) derrubou o servidor no meio da conta. Agora o servidor em --dev
diz os pedidos em curso (GET /api/dev/ocupado) e o vigia espera eles terminarem antes de reiniciar."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQUI = os.path.dirname(os.path.abspath(__file__))
for p in (RAIZ, AQUI):
    if p not in sys.path:
        sys.path.insert(0, p)

import dev                                                                    # noqa: E402


def _porta():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _servidor_falso(ocupado_nas_primeiras: int, andamento=None):
    """responde /api/dev/ocupado: ocupado nas primeiras n perguntas, depois livre; `andamento`: s desde o último
    _progresso da tarefa (sem ele, o servidor de antes de 29/10)"""
    perguntas = [0]

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            perguntas[0] += 1
            ocup = perguntas[0] <= ocupado_nas_primeiras
            d = {"ocupado": ocup, "pedidos": [{"rota": "/api/projetos/cd-bom-dia/reanalisar", "ha_s": 40}] if ocup else []}
            if andamento is not None:
                d["andamento_ha_s"] = andamento
            corpo = json.dumps(d).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, perguntas


def test_o_vigia_espera_a_tarefa_terminar():
    srv, perguntas = _servidor_falso(3)
    try:
        esperou = dev._esperar_ocioso(srv.server_address[1], limite=20, intervalo=0.1)
    finally:
        srv.shutdown()
    assert perguntas[0] >= 4, "perguntou até ficar livre"
    assert 0.2 < esperou < 5.0, esperou


def test_o_vigia_nao_espera_alem_do_limite_nem_sem_servidor():
    srv, _ = _servidor_falso(10 ** 6)
    try:
        esperou = dev._esperar_ocioso(srv.server_address[1], limite=0.6, intervalo=0.1)
    finally:
        srv.shutdown()
    assert 0.5 < esperou < 3.0, "o limite vale (a tarefa travada não segura o reinício para sempre)"
    t0 = time.time()
    dev._esperar_ocioso(_porta(), limite=5, intervalo=0.1)            # porta sem servidor: reinicia como antes
    assert time.time() - t0 < 4.5


def test_a_tarefa_que_anda_segura_o_reinicio_alem_do_limite():
    """Edifício Administrativo (29/10): o Detalhar de 41 min era derrubado aos 14 (o limite de 10 min de espera), com a
    tarefa dizendo o andamento. A que anda segura o reinício até terminar (no máximo o teto); a parada, não."""
    srv, perguntas = _servidor_falso(14, andamento=0.2)              # ocupada ~1,4 s, com andamento recente
    try:
        esperou = dev._esperar_ocioso(srv.server_address[1], limite=0.5, intervalo=0.1)
    finally:
        srv.shutdown()
    assert perguntas[0] >= 15 and esperou > 1.2, "esperou a tarefa que anda terminar, além do limite (%.1f s)" % esperou
    srv, _ = _servidor_falso(10 ** 6, andamento=999.0)               # parada: sem andamento há mais que o limite
    try:
        esperou = dev._esperar_ocioso(srv.server_address[1], limite=0.5, intervalo=0.1)
    finally:
        srv.shutdown()
    assert 0.4 < esperou < 2.5, "a parada não segura além do limite (%.1f s)" % esperou
    srv, _ = _servidor_falso(10 ** 6, andamento=0.2)                 # anda para sempre: o teto vale
    try:
        esperou = dev._esperar_ocioso(srv.server_address[1], limite=0.3, intervalo=0.1, teto=1.0)
    finally:
        srv.shutdown()
    assert 0.9 < esperou < 3.0, "o teto vale (%.1f s)" % esperou


def test_o_servidor_dev_diz_o_andamento():
    """/api/dev/ocupado traz há quanto tempo uma tarefa chamou o _progresso (nenhuma: None)"""
    import app
    guardado = dict(app.PROGRESSO)
    try:
        app.PROGRESSO.clear()
        assert app._ocupado()["andamento_ha_s"] is None
        app.PROGRESSO["obra-a"] = {"etapa": "desenhando conjuntos (3 de 82)…", "quando": time.time() - 40.0}
        app.PROGRESSO["obra-b"] = {"etapa": "lista…", "quando": time.time() - 5.0}
        assert 4.0 <= app._ocupado()["andamento_ha_s"] < 15.0, "o andamento mais recente"
    finally:
        app.PROGRESSO.clear()
        app.PROGRESSO.update(guardado)


def test_o_servidor_dev_diz_o_pedido_em_curso():
    """o app.py --dev de verdade: durante a reanálise de um modelo grande, /api/dev/ocupado diz a rota; depois, livre"""
    from test_reanalise import _tesoura
    from nucleo3d.modelo import Documento
    grande = Documento()
    for k in range(60):                                                   # 60 tesouras de 28 peças, 6 m entre elas
        d, _ = _tesoura(222913.0 + 6000.0 * k, 251770.0, 12000.0, k % 2 == 1)
        for e in d.entidades.values():
            grande.add(e)
    corpo = json.dumps({"documento": grande.dict()}).encode("utf-8")
    porta = _porta()
    dados = tempfile.mkdtemp(prefix="metalica_dev_espera_")
    srv = subprocess.Popen([sys.executable, os.path.join(RAIZ, "app.py"), "--dev", "--sem-navegador", "--porta", str(porta),
                            "--dados", dados], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = "http://127.0.0.1:%d" % porta
        for _ in range(80):
            try:
                urllib.request.urlopen(url + "/api/versao", timeout=2).read()
                break
            except Exception:                                             # noqa: BLE001
                time.sleep(0.25)
        assert dev._ocupado(porta) == [], "livre antes"
        resultado = {}

        def pedir():
            req = urllib.request.Request(url + "/api/modelo/reanalisar", data=corpo,
                                         headers={"Content-Type": "application/json; charset=utf-8"})
            resultado["r"] = json.loads(urllib.request.urlopen(req, timeout=300).read().decode("utf-8"))
        t = threading.Thread(target=pedir)
        t.start()
        visto = []
        while t.is_alive() and not visto:
            visto = dev._ocupado(porta)
            time.sleep(0.05)
        t.join()
        assert visto and visto[0]["rota"] == "/api/modelo/reanalisar", visto
        assert resultado.get("r", {}).get("regras"), "a reanálise terminou"
        assert dev._ocupado(porta) == [], "livre depois"
    finally:
        srv.kill()


def _servidor_do_app():
    """responde /api/dev/ocupado com o app._ocupado() deste processo (o mesmo da rota do app.py --dev)"""
    import app

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            corpo = json.dumps(app._ocupado()).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_a_atualizacao_em_segundo_plano_segura_o_reinicio(tmp_path):
    """Vicente, 04/11 (pelo GESTÃO): "a atualização dos desenhos de detalhamento foi interrompida 3 vezes seguidas: o
    programa fechou ou reiniciou no meio" — a atualização automática (desenhos_vivos) roda numa thread, sem pedido aberto,
    e o /api/dev/ocupado dizia "livre": o vigia reiniciava a cada .py salvo por outro chat. Agora ela conta como em curso,
    e o vigia espera ela terminar."""
    import app
    import desenhos_vivos as dv
    from test_desenhos_vivos import _Gerente
    g = _Gerente(str(tmp_path))
    os.makedirs(tmp_path / "vicente" / "detalhamento")
    (tmp_path / "vicente" / "modelo.json").write_text("{}", encoding="utf-8")
    comecou, soltar = threading.Event(), threading.Event()

    def detalhar(s):                                  # o Detalhar longo, sem pedido HTTP aberto
        comecou.set()
        soltar.wait(30)
    guardado_funcoes, guardado_progresso = dict(dv._funcoes), dict(app.PROGRESSO)
    app.PROGRESSO.clear()
    dv.configurar(gerente=lambda: g, detalhar=detalhar, pranchas=None, resumos=None)
    srv = _servidor_do_app()
    try:
        assert app._ocupado()["ocupado"] is False
        assert dv.atualizar("vicente", "o modelo 3D mudou") is True
        assert comecou.wait(10)
        d = app._ocupado()
        assert d["ocupado"] is True and "vicente" in d["pedidos"][0]["rota"], d
        threading.Timer(1.5, soltar.set).start()      # termina 1,5 s depois do .py salvo
        esperou = dev._esperar_ocioso(srv.server_address[1], limite=20, intervalo=0.1)
        assert 1.0 < esperou < 15.0, "o vigia esperou a atualização (%.1f s)" % esperou
        assert not dv.em_curso()
    finally:
        soltar.set()
        srv.shutdown()
        dv._funcoes.clear()
        dv._funcoes.update(guardado_funcoes)
        dv._estado.pop("vicente", None)
        app.PROGRESSO.clear()
        app.PROGRESSO.update(guardado_progresso)


def test_a_tarefa_sem_pedido_que_anda_conta_como_em_curso():
    """a tarefa que dá andamento (_progresso) sem pedido aberto — em segundo plano — conta para o vigia; a que parou de
    andar há mais de FUNDO_RECENTE (sobrou de uma tarefa que morreu) não segura o reinício"""
    import app
    guardado = dict(app.PROGRESSO)
    try:
        app.PROGRESSO.clear()
        agora = time.time()
        app.PROGRESSO["obra-a"] = {"etapa": "pranchas (3 de 40)…", "quando": agora - 2.0, "inicio": agora - 300.0}
        d = app._ocupado()
        assert d["ocupado"] is True and "obra-a" in d["pedidos"][0]["rota"] and d["pedidos"][0]["ha_s"] >= 299
        app.PROGRESSO["obra-a"]["quando"] = agora - app.FUNDO_RECENTE - 5.0
        assert app._ocupado()["ocupado"] is False
    finally:
        app.PROGRESSO.clear()
        app.PROGRESSO.update(guardado)
