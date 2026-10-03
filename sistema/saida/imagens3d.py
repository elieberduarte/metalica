# -*- coding: utf-8 -*-
"""Imagens do modelo 3D para a proposta comercial: o editor 3D em modo apresentação
(``/editor?projeto=<slug>&render=1``, ver ``web/editor3d/modulos/diagnostico.js``) aberto num
Chrome sem janela, que fotografa o modelo de alguns ângulos (``window.__render``).

O servidor do programa precisa estar no ar (é ele quem serve o editor e o modelo). As imagens
ficam em ``<projeto>/proposta/imagens/<angulo>.jpg``; quem chama decide quais ângulos.
"""
import base64
import os
import subprocess
import time
from typing import Dict, List, Optional, Sequence
from urllib.parse import quote

from saida.printpdf import CDP, http_json, navegador, porta_livre

#: Os ângulos que o editor sabe (diagnostico.js, ANGULOS) — na ordem em que a proposta usa.
ANGULOS = ("aerea_frente", "aerea_tras", "perspectiva", "lateral", "topo")


def fotografar(porta_servidor: int, slug: str, pasta: str, angulos: Sequence[str] = ANGULOS,
               largura: int = 1600, altura: int = 1000, escala: float = 1.5, timeout: float = 240.0,
               avisar=None, capa: Optional[str] = "aerea_frente") -> Dict[str, str]:
    """Abre o modelo do projeto e grava uma imagem por ângulo. Devolve {ângulo: caminho}. Com `capa`, grava
    também ``capa.jpg``: o mesmo ângulo num quadro quase quadrado, do tamanho da foto da capa da proposta."""
    avisar = avisar or (lambda *a: None)
    os.makedirs(pasta, exist_ok=True)
    porta = porta_livre()
    perfil = os.path.join(os.environ.get("TEMP", "."), "chrome_render_%d" % porta)
    url = "http://127.0.0.1:%d/editor?projeto=%s&render=1" % (porta_servidor, quote(slug))
    proc = subprocess.Popen(
        [navegador(), "--headless=new", "--hide-scrollbars", "--no-sandbox", "--disable-extensions",
         "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--remote-allow-origins=*",
         "--user-data-dir=%s" % perfil, "--remote-debugging-port=%d" % porta,
         "--window-size=%d,%d" % (largura, altura), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        alvo = None
        for _ in range(60):
            paginas = [t for t in http_json(porta, "/list") if t.get("type") == "page"]
            if paginas:
                alvo = paginas[0]
                break
            time.sleep(0.5)
        if alvo is None:
            raise RuntimeError("o Chrome abriu, mas a página não apareceu")
        cdp = CDP(alvo["webSocketDebuggerUrl"])
        cdp.cmd("Page.enable")
        cdp.cmd("Runtime.enable")
        cdp.cmd("Emulation.setDeviceMetricsOverride", width=largura, height=altura, deviceScaleFactor=escala, mobile=False)
        cdp.cmd("Page.navigate", url=url)
        avisar("abrindo o modelo 3D…")
        t0 = time.time()
        while not cdp.avalia("window.__renderPronto === true"):
            erro = cdp.avalia("(document.querySelector('.erro-fatal, #erro-fatal') || {}).textContent || ''")
            if erro:
                raise RuntimeError("o editor 3D não abriu o modelo: %s" % str(erro)[:200])
            if time.time() - t0 > timeout:
                raise RuntimeError("o modelo 3D não ficou pronto em %d s" % timeout)
            time.sleep(1.0)
        avisar("fotografando o modelo (%d ângulos)…" % len(angulos))
        r = cdp.cmd("Runtime.evaluate", expression="window.__render(%s)" % list(angulos).__repr__().replace("'", '"'),
                    returnByValue=True, awaitPromise=True, timeout=int(timeout * 1000))
        resultado = (r.get("result") or {}).get("value") or []
        if capa:
            cdp.cmd("Emulation.setDeviceMetricsOverride", width=1240, height=1160, deviceScaleFactor=escala, mobile=False)
            time.sleep(1.0)
            r2 = cdp.cmd("Runtime.evaluate", expression='window.__render(["%s"])' % capa, returnByValue=True, awaitPromise=True,
                         timeout=int(timeout * 1000))
            for item in (r2.get("result") or {}).get("value") or []:
                item["nome"] = "capa"
                resultado.append(item)
        saida: Dict[str, str] = {}
        for item in resultado:
            dados = str(item.get("imagem") or "")
            if "," not in dados:
                continue
            ext = "png" if dados.startswith("data:image/png") else "jpg"
            caminho = os.path.join(pasta, "%s.%s" % (item.get("nome"), ext))
            with open(caminho, "wb") as f:
                f.write(base64.b64decode(dados.split(",", 1)[1]))
            saida[str(item.get("nome"))] = caminho
        cdp.fecha()
        if not saida:
            raise RuntimeError("o editor não devolveu imagens")
        return saida
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:                                   # noqa: BLE001
            proc.kill()
