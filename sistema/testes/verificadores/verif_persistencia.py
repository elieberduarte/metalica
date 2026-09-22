# -*- coding: utf-8 -*-
"""Headless: modelo recentrado cabe na grade; mudança grava no servidor; recarregar a
página traz o último modelo de volta."""
import base64, json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, CONTAR_OBJETOS, _json, _porta_livre

porta = int(sys.argv[1]); base_url = f"http://localhost:{porta}"
chrome = next(c for c in CHROMES if os.path.exists(c))
porta_cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_persist_")
proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader",
    "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
    f"--user-data-dir={perfil}", f"--remote-debugging-port={porta_cdp}", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
arquivo_modelo = os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json")
codigo = 0
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
def esperar_objetos(aba, minimo, limite=120):
    t0 = time.time(); n = -1
    while time.time() - t0 < limite:
        aba.drenar(1.0); n = aba.avaliar(CONTAR_OBJETOS)
        if isinstance(n, int) and n >= minimo: aba.drenar(3.0); return n
    return n
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{porta_cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)
    aba.navegar(base_url + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); localStorage.removeItem('galpao.editor.ultimo'); 1")
    aba.console.clear()
    aba.navegar(base_url + "/editor", limite=30); aba.drenar(3.0)
    print("sem último modelo, objetos ao abrir:", aba.avaliar(CONTAR_OBJETOS))
    aba.avaliar("window.editor.abrirModelo('compressores-ar')")
    print("objetos após abrir:", esperar_objetos(aba, 4000))
    print("caixa (mm):", aba.avaliar("JSON.stringify(window.editor.documento.caixa())"))
    print("último lembrado:", aba.avaliar("localStorage.getItem('galpao.editor.ultimo')"))
    foto(aba, "persist_1_aberto.png")
    # muda algo (oculta Telhas) e espera a gravação automática
    mtime0 = os.path.getmtime(arquivo_modelo)
    aba.avaliar("(() => { const l = [...document.querySelectorAll('#painel-camadas .linha')].find(x => x.querySelector('.nome') && x.querySelector('.nome').textContent === 'Telhas'); l.querySelector('button.alternador').click(); return 1; })()")
    print("após o clique: Telhas visível =", aba.avaliar("window.editor.documento.camadas.get('Telhas').visivel"),
          "| pendente =", aba.avaliar("!!window.editor._autosavePendente"), "| timer =", aba.avaliar("!!window.editor._autosaveTimer"))
    t0 = time.time(); gravou = False; ultimo = mtime0
    while time.time() - t0 < 60:
        aba.drenar(1.0)
        m = os.path.getmtime(arquivo_modelo)
        if m > ultimo:
            ultimo = m
            vis = json.load(open(arquivo_modelo, encoding="utf-8"))["camadas"]["Telhas"]["visivel"]
            print("  arquivo regravado aos %.0f s, Telhas visível no arquivo = %s" % (time.time() - t0, vis))
            if vis is False: gravou = True; break
    print("gravação automática com a mudança:", gravou)
    aba.drenar(1.0)
    # recarrega a página: tem de voltar o mesmo modelo com Telhas oculta
    aba.console.clear()
    aba.navegar(base_url + "/editor", limite=30)
    n = esperar_objetos(aba, 4000)
    print("objetos após recarregar:", n)
    print("Telhas visível após recarregar:", aba.avaliar("(window.editor.documento.camadas.get('Telhas')||{}).visivel"))
    print("nome do modelo:", aba.avaliar("window.editor.documento.nome"))
    foto(aba, "persist_2_recarregado.png")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    print("erros de JavaScript:", len(erros))
    for t, x in erros[:10]: print("  [%s] %s" % (t, x[:300]))
    codigo = 0 if (gravou and n == 4047 and not erros) else 1
    aba.ws.close()
finally:
    proc.terminate()
    try: proc.wait(timeout=10)
    except Exception: proc.kill()
sys.exit(codigo)
