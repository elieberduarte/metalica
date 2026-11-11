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
A tarefa que segue dizendo o andamento (_progresso) segura o reinício além disso, até ESPERA_MAXIMA: o Detalhar do
Edifício Administrativo (41 min) era derrubado aos 14 min (29/10).

O vigia é um só por porta (_trancar): o atalho aberto com o dev no meio de um reinício subia um segundo vigia, e a cada .py
salvo os dois (chegaram a três) reiniciavam juntos e disputavam a 8766 — um ficava com ela, os outros subiam em porta
solta e a janela dava "ERR_CONNECTION_REFUSED" (11/11). O segundo agora só mostra a janela do que já roda e sai.
"""
import os
import subprocess
import sys
import tempfile
import time

BASE = os.path.dirname(os.path.abspath(__file__))
IGNORAR = {"testes", "projetos", "__pycache__", "web", "saida_pdf", ".git"}
INTERVALO = 1.0            # s entre olhadas no código
ESPERA_PORTA = 8.0         # s para a porta ficar livre depois de derrubar o servidor
ESPERA_TAREFA = 600.0      # s esperando a tarefa em curso terminar; depois, só se ela deu andamento nesse tempo
ESPERA_MAXIMA = 3600.0     # s, no máximo, mesmo com a tarefa dando andamento


def _registro():
    """Sem console (pythonw): o que o vigia diz vai para metalica-dev.log, ao lado do do servidor."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    sys.path.insert(0, BASE)
    try:
        # a mesma pasta que o servidor em --dev usa (o vigia não tem o --dev no argv: sem isto
        # o app resolveria sistema/projetos e o "[dev] …" ia parar noutro arquivo)
        import app
        # com METALICA_DADOS (a pasta de dados fora do OneDrive, opção A de 03/11) o app já resolve a pasta certa
        pasta = app.PROJETOS if ("--dados" in sys.argv or os.environ.get("METALICA_DADOS")) else os.path.join(app._documentos(), app.versao.NOME)
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


def _consultar(porta: int) -> tuple:
    """(pedidos em curso, s desde o último andamento de uma tarefa ou None) pelo GET /api/dev/ocupado; ([], None) se está
    livre ou não responde"""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/dev/ocupado" % porta, timeout=3) as r:
            d = json.loads(r.read().decode("utf-8"))
        if not d.get("ocupado"):
            return [], None
        andamento = d.get("andamento_ha_s")
        return list(d.get("pedidos") or []), (None if andamento is None else float(andamento))
    except Exception:                                    # noqa: BLE001 — sem resposta: reinicia como antes
        return [], None


def _ocupado(porta: int) -> list:
    """os pedidos em curso no servidor (GET /api/dev/ocupado); [] se está livre ou não responde"""
    return _consultar(porta)[0]


def _esperar_ocioso(porta: int, limite: float = ESPERA_TAREFA, intervalo: float = 1.0,
                    teto: float = ESPERA_MAXIMA) -> float:
    """espera o servidor ficar sem pedido em curso; devolve quanto esperou. Desiste depois de `limite` s, a não ser que a
    tarefa tenha dado andamento nos últimos `limite` s (o Detalhar de 41 min, 29/10) — e aí no máximo `teto` s"""
    t0 = time.time()
    avisou = False
    while True:
        pedidos, andamento = _consultar(porta)
        if not pedidos:
            break
        esperou = time.time() - t0
        if esperou >= teto or (esperou >= limite and (andamento is None or andamento >= limite)):
            print("[dev] %s a tarefa segue em curso há %.0f s de espera%s — reiniciando assim mesmo" % (
                time.strftime("%H:%M:%S"), esperou, "" if andamento is None else
                " (último andamento há %.0f s)" % andamento), flush=True)
            break
        if not avisou:
            p = pedidos[0]
            print("[dev] %s tarefa em curso (%s, há %.0f s) — o reinício espera ela terminar" % (
                time.strftime("%H:%M:%S"), p.get("rota"), p.get("ha_s") or 0), flush=True)
            avisou = True
        time.sleep(intervalo)
    return time.time() - t0


def _trancar(porta: int):
    """A trava do vigia desta porta: um arquivo travado enquanto o processo vive (o Windows a solta quando ele termina,
    mesmo derrubado). Devolve o arquivo aberto, que precisa ficar vivo, ou None se outro vigia já a tem."""
    pasta = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "Metalica")
    try:
        os.makedirs(pasta, exist_ok=True)
        f = open(os.path.join(pasta, "dev-vigia-%d.trava" % porta), "a+b")
    except OSError:
        return True                                      # sem onde travar: segue como antes
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def _mostrar_o_que_ja_roda(porta: int):
    """O segundo clique no atalho: o vigia que já roda segue com o servidor dele; este só abre a janela (esperando o
    servidor responder, se ele está no meio de um reinício) e sai."""
    print("[dev] %s já há um vigia na porta %d — este só mostra a janela e sai" % (time.strftime("%H:%M:%S"), porta),
          flush=True)
    if "--sem-navegador" in sys.argv:
        return
    sys.path.insert(0, BASE)
    import app
    t0 = time.time()
    while time.time() - t0 < 90 and not app._ja_esta_rodando(porta):
        time.sleep(0.5)
    url = "http://localhost:%d/" % porta
    if app._abrir_janela(url) is None:
        import webbrowser
        webbrowser.open(url)


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
    trava = _trancar(porta)                                # fica viva até o vigia terminar
    if trava is None:
        _mostrar_o_que_ja_roda(porta)
        return
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
