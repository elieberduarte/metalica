# -*- coding: utf-8 -*-
"""Com a obra no terreno desligada (METALICA_TERRENO=0), a rota /terreno responde 404 (14/11, achado pelo
verif_barra_ver_nao_pula na situação "sem terreno"): antes ela caía na rota de baixo e devolvia a ficha do projeto com
200, o modo ver a lia como terreno e mostrava o botão Terreno com dados que não eram do terreno."""
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "testes"))


def test_terreno_desligado_responde_404():
    from verificar_editor import _porta_livre
    dados = tempfile.mkdtemp(prefix="metalica_terreno_desligado_")
    os.makedirs(os.path.join(dados, "obra"))
    with open(os.path.join(dados, "obra", "projeto.json"), "w", encoding="utf-8") as f:
        json.dump({"nome": "Sem terreno", "tipo": "ifc"}, f)
    porta = _porta_livre()
    srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(porta), "--dados", dados],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, METALICA_TERRENO="0"))
    try:
        def pedir(metodo, rota, corpo=None):
            for _ in range(80):
                try:
                    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=30)
                    c.request(metodo, rota, body=corpo, headers={"Content-Type": "application/json"} if corpo else {})
                    r = c.getresponse()
                    return r.status, json.loads(r.read() or b"null")
                except (ConnectionError, OSError):
                    time.sleep(0.25)
            raise AssertionError("o servidor não respondeu")

        st, r = pedir("GET", "/api/projetos/obra/terreno")
        assert st == 404 and "projeto" not in (r or {}), (st, str(r)[:200])
        st, r = pedir("POST", "/api/projetos/obra/terreno", json.dumps({"lat": -23.5, "lon": -46.6}))
        assert st == 404, (st, str(r)[:200])
        st, r = pedir("GET", "/api/projetos/obra")                                # o resto do projeto continua
        assert st == 200 and r["projeto"]["nome"] == "Sem terreno", (st, str(r)[:200])
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:                                                      # noqa: BLE001
            srv.kill()
        shutil.rmtree(dados, ignore_errors=True)
