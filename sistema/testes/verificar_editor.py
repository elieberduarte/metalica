# -*- coding: utf-8 -*-
"""Verificação de ponta a ponta do editor 3D, pelo protocolo de depuração do Chrome.

Faz o que o usuário faz: grava os dados de um galpão no navegador, na mesma chave que a
interface de dimensionamento usa, abre o editor com `?galpao=1`, espera o modelo
aparecer, salva uma captura de tela e lista os erros de JavaScript.

Não é um teste do pytest (o nome não começa com `test_`), porque depende do servidor no
ar e de um Chrome instalado. Uso, com o servidor rodando:

    python testes/verificar_editor.py --porta 8765
    python testes/verificar_editor.py --porta 8765 --saida projetos/_editor.png --vao 30

Sai com código 1 se houver erro de JavaScript ou se o modelo não carregar.
"""
import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket  # websocket-client

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

CHROMES = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]

CHAVE_ESTADO = "galpao.estado.v1"      # a mesma de web/app.js


def _porta_livre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _json(url, tentativas=60):
    for _ in range(tentativas):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("sem resposta de " + url)


class Aba:
    """Uma aba do Chrome controlada por CDP, guardando as mensagens do console."""

    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=120)
        self.n = 0
        self.console = []
        self.eventos = []

    def _tratar(self, msg):
        metodo = msg.get("method", "")
        if metodo == "Runtime.consoleAPICalled":
            p = msg["params"]
            texto = " ".join(str(a.get("value", a.get("description", "")))
                             for a in p.get("args", []))
            self.console.append((p.get("type", ""), texto))
        elif metodo == "Runtime.exceptionThrown":
            det = msg["params"]["exceptionDetails"]
            exc = det.get("exception", {}) or {}
            self.console.append(("excecao", exc.get("description") or det.get("text", "")))
        elif metodo == "Log.entryAdded":
            e = msg["params"]["entry"]
            if e.get("level") in ("error", "warning"):
                self.console.append((e["level"], e.get("text", "") + " " + e.get("url", "")))
        elif metodo:
            self.eventos.append(metodo)

    def cmd(self, metodo, **params):
        self.n += 1
        meu = self.n
        self.ws.send(json.dumps({"id": meu, "method": metodo, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == meu:
                if "error" in msg:
                    raise RuntimeError(f"{metodo}: {msg['error']}")
                return msg.get("result", {})
            self._tratar(msg)

    def avaliar(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True,
                     awaitPromise=True)
        if r.get("exceptionDetails"):
            return None
        return r.get("result", {}).get("value")

    def esperar_evento(self, nome, limite=30.0):
        fim = time.time() + limite
        self.ws.settimeout(1.0)
        try:
            while time.time() < fim:
                if nome in self.eventos:
                    self.eventos.remove(nome)
                    return True
                try:
                    self._tratar(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
        finally:
            self.ws.settimeout(120)
        return False

    def navegar(self, url, limite=30.0):
        self.eventos.clear()
        self.cmd("Page.navigate", url=url)
        return self.esperar_evento("Page.loadEventFired", limite)

    def drenar(self, segundos):
        """Deixa a página trabalhar, recolhendo mensagens do console."""
        self.esperar_evento("__nunca__", segundos)


# expressão que tenta descobrir quantos objetos o editor carregou, sem depender de um
# único nome de variável; devolve -1 quando não consegue ler
CONTAR_OBJETOS = r"""
(() => {
  const ed = window.editor || window.EDITOR || window.app;
  try {
    const doc = ed && (ed.documento || ed.doc);
    if (doc) {
      const ents = doc.entidades;
      if (ents instanceof Map) return ents.size;
      if (ents) return Object.keys(ents).length;
      if (typeof doc.tamanho === 'number') return doc.tamanho;
    }
  } catch (e) {}
  const txt = document.body ? document.body.innerText : '';
  const m = txt.match(/(\d[\d.\s]*)\s+objetos/i);
  return m ? parseInt(m[1].replace(/\D/g, ''), 10) : -1;
})()
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--saida", default=os.path.join(BASE, "projetos", "_editor.png"))
    ap.add_argument("--largura", type=int, default=1600)
    ap.add_argument("--altura", type=int, default=1000)
    ap.add_argument("--espera", type=float, default=60.0,
                    help="segundos para o modelo aparecer (o primeiro acesso a um servidor "
                         "recém-iniciado é mais lento)")
    ap.add_argument("--vao", type=float, default=20.0)
    ap.add_argument("--comprimento", type=float, default=40.0)
    ap.add_argument("--pe-direito", type=float, default=6.0)
    ap.add_argument("--tema", default="claro", choices=("claro", "escuro"))
    args = ap.parse_args()

    from nucleo.modelo_galpao import DadosGalpao
    dados = DadosGalpao(nome="Verificação do editor", vao=args.vao,
                        comprimento=args.comprimento, pe_direito=args.pe_direito).dict()

    chrome = next((c for c in CHROMES if os.path.exists(c)), None)
    if not chrome:
        print("Chrome ou Edge não encontrado.")
        return 2

    base_url = f"http://localhost:{args.porta}"
    try:
        urllib.request.urlopen(base_url + "/", timeout=3)
    except Exception:
        print(f"Servidor fora do ar em {base_url}. Rode: python app.py --porta {args.porta}")
        return 2

    porta_cdp = _porta_livre()
    perfil = tempfile.mkdtemp(prefix="verif_editor_")
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader",
         "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
         "--remote-allow-origins=*", f"--user-data-dir={perfil}",
         f"--remote-debugging-port={porta_cdp}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    codigo = 0
    try:
        alvo = None
        for _ in range(60):
            alvos = [t for t in _json(f"http://127.0.0.1:{porta_cdp}/json/list")
                     if t.get("type") == "page"]
            if alvos:
                alvo = alvos[0]
                break
            time.sleep(0.5)
        if alvo is None:
            print("O Chrome não abriu uma aba.")
            return 2
        aba = Aba(alvo["webSocketDebuggerUrl"])
        for dominio in ("Page", "Runtime", "Log"):
            aba.cmd(f"{dominio}.enable")
        aba.cmd("Emulation.setDeviceMetricsOverride", width=args.largura,
                height=args.altura, deviceScaleFactor=1, mobile=False)

        # 1) grava os dados do galpão na origem do servidor, como a interface faz
        aba.navegar(base_url + "/")
        gravado = aba.avaliar(
            f"(() => {{ localStorage.setItem({json.dumps(CHAVE_ESTADO)}, "
            f"{json.dumps(json.dumps(dados, ensure_ascii=False))}); "
            f"localStorage.setItem('galpao.tema', {json.dumps(args.tema)}); "
            f"return localStorage.getItem({json.dumps(CHAVE_ESTADO)}) !== null; }})()")
        aba.console.clear()          # erros da interface principal não interessam aqui

        # 2) abre o editor pedindo o galpão e espera o modelo aparecer
        t0 = time.time()
        carregou = aba.navegar(base_url + "/editor?galpao=1", limite=30)
        objetos = -1
        while time.time() - t0 < args.espera:
            aba.drenar(1.0)
            objetos = aba.avaliar(CONTAR_OBJETOS)
            if isinstance(objetos, int) and objetos > 0:
                aba.drenar(2.0)      # deixa a cena terminar de montar as malhas
                break
        webgl = aba.avaliar("(() => { const c = document.querySelector('canvas');"
                            " if (!c) return 'sem canvas';"
                            " const g = c.getContext('webgl2') || c.getContext('webgl');"
                            " return g ? g.getParameter(g.VERSION) : 'contexto indisponível'; })()")

        # 3) captura
        png = aba.cmd("Page.captureScreenshot", format="png")["data"]
        os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
        with open(args.saida, "wb") as f:
            f.write(base64.b64decode(png))

        erros = [c for c in aba.console if c[0] in ("error", "excecao")]
        avisos = [c for c in aba.console if c[0] in ("warning", "warn")]
        print(f"dados gravados no navegador: {gravado}")
        print(f"página do editor carregada: {carregou}")
        print(f"WebGL: {webgl}")
        print(f"objetos no modelo: {objetos} (em {time.time() - t0:.1f} s)")
        print(f"captura: {args.saida}")
        print(f"erros de JavaScript: {len(erros)}")
        for tipo, texto in erros[:15]:
            print(f"   [{tipo}] {texto[:300]}")
        if avisos:
            print(f"avisos do console: {len(avisos)}")
            for tipo, texto in avisos[:5]:
                print(f"   [{tipo}] {texto[:200]}")
        if erros or not (isinstance(objetos, int) and objetos > 0):
            codigo = 1
        aba.ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
