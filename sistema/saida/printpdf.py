# -*- coding: utf-8 -*-
"""Impressão de HTML em PDF pelo Chrome headless, esperando o Paged.js terminar.

Mesmo mecanismo já validado no manual (`../manual/printpdf.py`), trazido para dentro do
sistema para que os módulos de saída não dependam de uma pasta irmã. A diferença
importante em relação a `chrome --print-to-pdf` é que aqui esperamos o Paged.js sinalizar
o fim da paginação (atributo `data-paged="done"` na raiz) antes de mandar imprimir; sem
essa espera o Chrome imprime no meio da paginação e o PDF sai truncado.

Requer o pacote `websocket-client` (já usado pelo manual) e o Chrome instalado.
"""
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import quote

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Locais onde o Chrome costuma estar no Windows.
CHROMES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

#: Onde procurar o Paged.js: primeiro a cópia local, depois a do manual.
PAGED_JS = [
    os.path.join(_RAIZ, "saida", "lib", "paged.polyfill.js"),
    os.path.join(os.path.dirname(_RAIZ), "manual", "lib", "paged.polyfill.js"),
]


def navegador() -> str:
    """Caminho do Chrome (ou Edge, que usa o mesmo motor). Erro claro se não achar."""
    env = os.environ.get("CHROME")
    if env and os.path.exists(env):
        return env
    for c in CHROMES:
        if c and os.path.exists(c):
            return c
    raise RuntimeError(
        "Chrome não encontrado. Instale o Google Chrome ou aponte a variável de "
        "ambiente CHROME para o executável. Procurado em:\n  " + "\n  ".join(CHROMES))


def paged_js_url() -> str:
    """URL file:// do Paged.js local (a paginação é feita offline, sem internet)."""
    for c in PAGED_JS:
        if os.path.exists(c):
            return "file:///" + quote(os.path.abspath(c).replace("\\", "/"))
    raise RuntimeError(
        "paged.polyfill.js não encontrado. Esperado em:\n  " + "\n  ".join(PAGED_JS))


def porta_livre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http_json(porta: int, caminho: str, tentativas: int = 60):
    url = f"http://127.0.0.1:{porta}/json{caminho}"
    for _ in range(tentativas):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Chrome não respondeu em {url}")


class CDP:
    """Cliente mínimo do Chrome DevTools Protocol."""

    def __init__(self, ws_url):
        import websocket                                   # websocket-client
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
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True,
                     awaitPromise=True)
        return r.get("result", {}).get("value")

    def fecha(self):
        try:
            self.ws.close()
        except Exception:
            pass


def imprimir(html_path: str, pdf_path: str, timeout: int = 900,
             verbose: bool = True) -> int:
    """Imprime `html_path` em `pdf_path` e devolve o número de páginas paginadas."""
    url = "file:///" + quote(os.path.abspath(html_path).replace("\\", "/"))
    porta = porta_livre()
    perfil = os.path.join(os.environ.get("TEMP", "."), f"chrome_pdf_{porta}")
    proc = subprocess.Popen(
        [navegador(), "--headless=new", "--disable-gpu", "--no-sandbox",
         "--hide-scrollbars", "--allow-file-access-from-files", "--disable-extensions",
         "--remote-allow-origins=*", f"--user-data-dir={perfil}",
         f"--remote-debugging-port={porta}", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
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
            if cdp.avalia("document.documentElement.getAttribute('data-paged') === 'done'"):
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
            print(f"\r   paginação concluída: {paginas} páginas "
                  f"({time.time() - t0:.0f}s)      ")

        r = cdp.cmd("Page.printToPDF", printBackground=True, preferCSSPageSize=True,
                    displayHeaderFooter=False, marginTop=0, marginBottom=0,
                    marginLeft=0, marginRight=0, transferMode="ReturnAsBase64")
        os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
        with open(pdf_path, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        cdp.fecha()
        return int(paginas or 0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def envelope(corpo_html: str, css: str, titulo: str, lang: str = "pt-BR") -> str:
    """Documento HTML completo, com o Paged.js local e o sinal de fim de paginação."""
    return f"""<!DOCTYPE html>
<html lang="{lang}"><head><meta charset="utf-8">
<title>{titulo}</title>
<style>{css}</style>
<script>window.PagedConfig={{auto:true, after:function(){{
  document.documentElement.setAttribute("data-paged","done");}}}};</script>
<script src="{paged_js_url()}"></script>
</head><body>
{corpo_html}
</body></html>"""


if __name__ == "__main__":
    n = imprimir(sys.argv[1], sys.argv[2])
    print(f"PDF gravado: {sys.argv[2]} ({n} páginas)")
