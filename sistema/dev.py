# -*- coding: utf-8 -*-
"""Metálica em modo de desenvolvimento: `python dev.py` (ou o atalho "Metálica (desenvolvimento)").

Sobe `app.py --dev` — porta 8766, os mesmos projetos do programa instalado (Documentos\\Metálica),
faixa DESENVOLVIMENTO nas telas, sem oferecer atualização — e fica vigiando o código: quando um
arquivo .py do motor muda, o servidor é reiniciado sozinho e a janela que está aberta volta a
responder em poucos segundos (o programa reaberto vê o sinal de vida da janela e não abre outra).
Mudança só nas telas (js, html, css) não precisa de reinício: a janela avisa e F5 basta.

Quando o servidor termina por conta própria (o usuário fechou a janela), o vigia termina junto.
Com uma tarefa em curso (o Reanalisar estrutura, o Detalhar, a análise), o reinício espera ela terminar (até
ESPERA_TAREFA): vários chats salvam .py o tempo todo, e o reinício no meio dava "Failed to fetch" na tela (19/10).
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
IGNORAR = {"testes", "projetos", "__pycache__", "web", "saida_pdf", ".git"}
INTERVALO = 1.0            # s entre olhadas no código
ESPERA_PORTA = 8.0         # s para a porta ficar livre depois de derrubar o servidor
ESPERA_TAREFA = 600.0      # s, no máximo, esperando a tarefa em curso terminar antes de reiniciar


def _registro():
    """Sem console (pythonw): o que o vigia diz vai para metalica-dev.log, ao lado do do servidor."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    sys.path.insert(0, BASE)
    try:
        # a mesma pasta que o servidor em --dev usa (o vigia não tem o --dev no argv: sem isto
        # o app resolveria sistema/projetos e o "[dev] …" ia parar noutro arquivo)
        import app
        pasta = app.PROJETOS if "--dados" in sys.argv else os.path.join(app._documentos(), app.versao.NOME)
    except Exception:                                # noqa: BLE001
        pasta = BASE
    try:
        arq = open(os.path.join(pasta, "metalica-dev.log"), "a", encoding="utf-8", buffering=1)
    except OSError:
        arq = open(os.devnull, "w")
    sys.stdout = sys.stdout or arq
    sys.stderr = sys.stderr or arq


def _carimbos() -> dict:
    out = {}
    for raiz, pastas, arquivos in os.walk(BASE):
        pastas[:] = [p for p in pastas if p not in IGNORAR and not p.startswith(".")]
        for a in arquivos:
            if a.endswith(".py"):
                c = os.path.join(raiz, a)
                try:
                    out[c] = os.stat(c).st_mtime
                except OSError:
                    pass
    return out


def _porta_ocupada(porta: int) -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", porta))
        return False
    except OSError:
        return True
    finally:
        s.close()


def _ocupado(porta: int) -> list:
    """os pedidos em curso no servidor (GET /api/dev/ocupado); [] se está livre ou não responde"""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/dev/ocupado" % porta, timeout=3) as r:
            d = json.loads(r.read().decode("utf-8"))
        return list(d.get("pedidos") or []) if d.get("ocupado") else []
    except Exception:                                    # noqa: BLE001 — sem resposta: reinicia como antes
        return []


def _esperar_ocioso(porta: int, limite: float = ESPERA_TAREFA, intervalo: float = 1.0) -> float:
    """espera o servidor ficar sem pedido em curso (no máximo `limite` s); devolve quanto esperou"""
    t0 = time.time()
    avisou = False
    while time.time() - t0 < limite:
        pedidos = _ocupado(porta)
        if not pedidos:
            break
        if not avisou:
            p = pedidos[0]
            print("[dev] %s tarefa em curso (%s, há %.0f s) — o reinício espera ela terminar" % (
                time.strftime("%H:%M:%S"), p.get("rota"), p.get("ha_s") or 0), flush=True)
            avisou = True
        time.sleep(intervalo)
    return time.time() - t0


def _subir(reaberto: bool) -> subprocess.Popen:
    cmd = [sys.executable, os.path.join(BASE, "app.py"), "--dev"] + [a for a in sys.argv[1:] if a != "--dev"]
    if reaberto:
        cmd.append("--reaberto")
    print("[dev] %s subindo o servidor%s" % (time.strftime("%H:%M:%S"), " (reinício)" if reaberto else ""), flush=True)
    return subprocess.Popen(cmd, cwd=BASE)


def main():
    _registro()
    os.environ.setdefault("METALICA_DEV", "1")
    porta = 8766
    if "--porta" in sys.argv:
        porta = int(sys.argv[sys.argv.index("--porta") + 1])
    vistos = _carimbos()
    filho = _subir(reaberto=False)
    while True:
        time.sleep(INTERVALO)
        if filho.poll() is not None:
            # o servidor saiu sozinho: janela fechada (ou já havia um dev rodando e ele só a mostrou)
            print("[dev] o servidor terminou (código %s); vigia encerrado." % filho.returncode, flush=True)
            return
        agora = _carimbos()
        mudados = [c for c, t in agora.items() if vistos.get(c) != t] + [c for c in vistos if c not in agora]
        if not mudados:
            continue
        if _esperar_ocioso(porta) > 0.5:
            agora = _carimbos()                            # o que mais mudou durante a espera entra no mesmo reinício
            mudados = [c for c, t in agora.items() if vistos.get(c) != t] + [c for c in vistos if c not in agora]
        vistos = agora
        print("[dev] %s mudou: %s — reiniciando" % (time.strftime("%H:%M:%S"),
              ", ".join(os.path.relpath(c, BASE) for c in mudados[:4])), flush=True)
        filho.terminate()
        try:
            filho.wait(timeout=6)
        except subprocess.TimeoutExpired:
            filho.kill()
            filho.wait()
        t0 = time.time()
        while _porta_ocupada(porta) and time.time() - t0 < ESPERA_PORTA:
            time.sleep(0.25)
        filho = _subir(reaberto=True)


if __name__ == "__main__":
    main()
