# -*- coding: utf-8 -*-
"""Um vigia do dev só, e o servidor reiniciado nunca numa porta solta (DESEMPENHO N.3, 11/11/2026).

GESTÃO N.7, 11/11: o usuário via "ERR_CONNECTION_REFUSED" no dev. Havia três vigias (dev.py) rodando — o atalho aberto
com o dev no meio de um reinício subia mais um. A cada .py salvo, todos reiniciavam juntos e disputavam a 8766: um ficava
com ela, os outros subiam em porta solta (o log: 53900, 59459, 63885…); e no Windows o SO_REUSEADDR deixava até dois
servidores ouvindo na mesma porta.

- o segundo vigia não sobe servidor: só mostra a janela do que já roda e sai (a trava some quando o primeiro termina);
- o servidor reiniciado (--reaberto) espera a porta dele; se outro Metálica já responde nela, não sobe (e o vigia a
  mais termina junto); só a porta presa por outro programa ainda cai numa porta solta, como antes;
- dois servidores do Metálica não ouvem na mesma porta."""
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import pytest                                                    # noqa: E402
import app                                                        # noqa: E402
import dev                                                        # noqa: E402


class _SemReuso(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True


def _falso(metalica: bool):
    """um servidor na porta: o Metálica de outro vigia (responde /api/versao) ou outro programa qualquer"""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            corpo = json.dumps({"programa": app.versao.NOME if metalica else "outro"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass
    srv = _SemReuso(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class _Parar(Exception):
    pass


@pytest.fixture()
def main_do_reinicio(monkeypatch, tmp_path):
    """roda o app.main() do reinício do dev (--dev --reaberto) na porta de teste, sem abrir janela de verdade nem
    ficar servindo: o servidor criado é anotado e fechado"""
    janelas, criados = [], []
    original = app._servidores

    def servidores(porta):
        s, e = original(porta)
        criados.append(porta)
        for x in [s, *e]:
            x.server_close()
        raise _Parar()

    monkeypatch.setattr(app, "_servidores", servidores)
    monkeypatch.setattr(app, "_abrir_janela", lambda url: janelas.append(url) or object())
    monkeypatch.setattr(app.webbrowser, "open", lambda url, *a, **k: janelas.append(url))
    monkeypatch.setattr(app, "DEV", True)
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["app.py", "--dev", "--reaberto"])
    intervalo = sys.getswitchinterval()

    def rodar(porta):
        monkeypatch.setattr(app, "PORTA_DEV", porta)
        try:
            app.main()
        except _Parar:
            pass
        finally:
            sys.setswitchinterval(intervalo)
        return janelas, criados
    return rodar


def test_o_reinicio_com_outro_metalica_na_porta_nao_sobe(main_do_reinicio):
    """O caso de 11/11: o vigia a mais reinicia o servidor dele e a 8766 já é do outro — não sobe em porta solta e
    não abre outra janela."""
    falso = _falso(True)
    try:
        janelas, criados = main_do_reinicio(falso.server_address[1])
    finally:
        falso.shutdown(); falso.server_close()
    assert criados == [], "subiu um servidor na porta %s" % criados
    assert janelas == []


def test_o_reinicio_espera_a_porta_e_fica_com_ela(main_do_reinicio):
    """O reinício normal: a porta da janela ainda presa pelo servidor que acabou de sair — espera e fica com ela."""
    falso = _falso(False)
    porta = falso.server_address[1]

    def soltar():
        time.sleep(1.0)
        falso.shutdown(); falso.server_close()
    threading.Thread(target=soltar, daemon=True).start()
    janelas, criados = main_do_reinicio(porta)
    assert criados == [porta]
    assert janelas == []                                   # o reinício não abre janela: a de antes continua lá


def test_a_porta_presa_por_outro_programa_ainda_cai_noutra(main_do_reinicio, monkeypatch):
    falso = _falso(False)
    monkeypatch.setattr(app, "ESPERA_PORTA_REINICIO", 1.0)
    try:
        _, criados = main_do_reinicio(falso.server_address[1])
    finally:
        falso.shutdown(); falso.server_close()
    assert len(criados) == 1 and criados[0] != falso.server_address[1]


@pytest.mark.skipif(os.name != "nt", reason="o SO_REUSEADDR do Windows")
def test_dois_servidores_nao_ouvem_na_mesma_porta():
    a = app.Servidor(("127.0.0.1", 0), app.Handler)
    try:
        with pytest.raises(OSError):
            b = app.Servidor(("127.0.0.1", a.server_address[1]), app.Handler)
            b.server_close()
    finally:
        a.server_close()


def _porta_de_teste():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_o_segundo_vigia_nao_sobe_servidor(monkeypatch):
    """Dois vigias na mesma porta: o segundo não sobe servidor nenhum, só mostra a janela do primeiro e sai; quando o
    primeiro termina (até derrubado), a trava fica livre para o próximo."""
    porta = _porta_de_teste()
    primeiro = subprocess.Popen([sys.executable, "-c", textwrap.dedent('''
        import sys, time
        sys.path.insert(0, %r)
        import dev
        t = dev._trancar(%d)
        print("TRAVADO" if t else "SEM TRAVA", flush=True)
        time.sleep(60)
    ''') % (RAIZ, porta)], stdout=subprocess.PIPE, text=True)
    try:
        assert primeiro.stdout.readline().strip() == "TRAVADO"
        subiu, mostrou = [], []
        monkeypatch.setattr(dev, "_subir", lambda reaberto: subiu.append(reaberto) or pytest.fail("subiu um servidor"))
        monkeypatch.setattr(dev, "_mostrar_o_que_ja_roda", lambda p: mostrou.append(p))
        monkeypatch.setattr(sys, "argv", ["dev.py", "--porta", str(porta), "--sem-navegador"])
        monkeypatch.setenv("METALICA_DEV", os.environ.get("METALICA_DEV", "0"))
        dev.main()
        assert subiu == [] and mostrou == [porta]
    finally:
        primeiro.kill(); primeiro.wait()
    t = dev._trancar(porta)                                # o primeiro saiu: a trava é do próximo
    assert t not in (None, True)
    t.close()
