# -*- coding: utf-8 -*-
"""Imprime um HTML em PDF pelo Chrome via DevTools Protocol.

Diferente de --print-to-pdf, aqui esperamos o Paged.js sinalizar que terminou a paginação
(atributo data-paged="done" na raiz) antes de mandar imprimir. Sem isso o Chrome imprime
no meio da paginação e o PDF sai truncado.
"""
import base64, json, os, socket, subprocess, sys, time, urllib.request

import websocket  # websocket-client

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http_json(porta, caminho, tentativas=60):
    url = f"http://127.0.0.1:{porta}/json{caminho}"
    for _ in range(tentativas):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Chrome não respondeu em {url}")


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=600)
        self.id = 0

    def cmd(self, metodo, **params):
        self.id += 1
        self.ws.send(json.dumps({"id": self.id, "method": metodo, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.id:
                if "error" in msg:
                    raise RuntimeError(f"{metodo}: {msg['error']}")
                return msg.get("result", {})

    def avalia(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def fecha(self):
        try:
            self.ws.close()
        except Exception:
            pass


def imprimir(html_path, pdf_path, timeout=900, verbose=True):
    from urllib.parse import quote
    url = "file:///" + quote(os.path.abspath(html_path).replace("\\", "/"))
    porta = porta_livre()
    perfil = os.path.join(os.environ.get("TEMP", "."), f"chrome_pdf_{porta}")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         "--allow-file-access-from-files", "--disable-extensions", "--remote-allow-origins=*",
         f"--user-data-dir={perfil}", f"--remote-debugging-port={porta}", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # o Chrome já foi lançado com a URL: basta achar a aba
        alvo = None
        for _ in range(60):
            paginas = [t for t in http_json(porta, "/list")
                       if t.get("type") == "page" and t.get("url", "").startswith("file:")]
            if paginas:
                alvo = paginas[0]
                break
            time.sleep(0.5)
        if alvo is None:
            raise RuntimeError("Chrome abriu, mas a aba do arquivo não apareceu")
        cdp = CDP(alvo["webSocketDebuggerUrl"])
        cdp.cmd("Page.enable")
        cdp.cmd("Runtime.enable")

        t0 = time.time()
        ultimo = -1
        while True:
            pronto = cdp.avalia("document.documentElement.getAttribute('data-paged') === 'done'")
            if pronto:
                break
            if time.time() - t0 > timeout:
                raise RuntimeError(f"Paged.js não terminou em {timeout}s")
            if verbose:
                n = cdp.avalia("document.querySelectorAll('.pagedjs_page').length") or 0
                if n != ultimo:
                    print(f"\r   paginando... {n} páginas", end="", flush=True)
                    ultimo = n
            time.sleep(1.0)

        paginas = cdp.avalia("document.querySelectorAll('.pagedjs_page').length")
        if verbose:
            print(f"\r   paginação concluída: {paginas} páginas ({time.time()-t0:.0f}s)      ")

        r = cdp.cmd("Page.printToPDF", printBackground=True, preferCSSPageSize=True,
                    displayHeaderFooter=False, marginTop=0, marginBottom=0,
                    marginLeft=0, marginRight=0, transferMode="ReturnAsBase64")
        os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
        with open(pdf_path, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        cdp.fecha()
        return paginas
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    n = imprimir(sys.argv[1], sys.argv[2])
    print(f"PDF gravado: {sys.argv[2]} ({n} páginas)")
