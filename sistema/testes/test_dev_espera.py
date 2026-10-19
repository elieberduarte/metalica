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


def _servidor_falso(ocupado_nas_primeiras: int):
    """responde /api/dev/ocupado: ocupado nas primeiras n perguntas, depois livre"""
    perguntas = [0]

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            perguntas[0] += 1
            ocup = perguntas[0] <= ocupado_nas_primeiras
            corpo = json.dumps({"ocupado": ocup, "pedidos": [{"rota": "/api/projetos/cd-bom-dia/reanalisar", "ha_s": 40}]
                                if ocup else []}).encode()
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
