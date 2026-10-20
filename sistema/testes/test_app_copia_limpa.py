# -*- coding: utf-8 -*-
"""O programa na cópia limpa do git (a da conferência da noite): o gancho das extensões do desenvolvimento
(`_extensoes_dev`, `EXTENSOES_DEV`) fica só no app.py de trabalho, fora do git. O d074600 levou para o git o laço
`for ext in EXTENSOES_DEV` do POST sem a definição, e na cópia limpa TODO POST dava 500 ("name 'EXTENSOES_DEV' is not
defined": criar projeto, gravar desenho...). Aqui o programa sobe de verdade e um POST a uma rota que não existe tem de
dar 404 — na cópia de trabalho o nome existe e o teste passa de qualquer jeito; na cópia limpa ele pega o defeito."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_post_sem_as_extensoes_do_desenvolvimento_responde():
    porta = _porta_livre()
    with tempfile.TemporaryDirectory() as dados:
        srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(porta), "--dados", dados],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/versao", timeout=2)
                    break
                except Exception:
                    time.sleep(0.5)
            req = urllib.request.Request(f"http://127.0.0.1:{porta}/api/rota-que-nao-existe", data=b"{}",
                                         headers={"Content-Type": "application/json"}, method="POST")
            try:
                urllib.request.urlopen(req, timeout=10)
                codigo, corpo = 200, {}
            except urllib.error.HTTPError as e:
                codigo, corpo = e.code, json.loads(e.read() or b"{}")
            assert codigo == 404, f"POST deu {codigo}: {corpo.get('erro')}"
        finally:
            srv.kill()
            srv.wait(10)
