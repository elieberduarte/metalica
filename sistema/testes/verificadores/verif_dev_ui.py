# -*- coding: utf-8 -*-
"""Modo de desenvolvimento (app.py --dev): /api/versao diz dev e o carimbo do código, a atualização
não é oferecida, a tela mostra a faixa laranja e "[DEV]" no título, o rótulo diz "dev", e quando um
arquivo de tela muda no disco o rótulo pede para recarregar. Porta livre, nunca a 8765/8766."""
import base64, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_devui_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--dev", "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_devui_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
css = os.path.join(BASE, "web", "estilo.css")
mtime = os.stat(css).st_mtime
try:
    v = _json(base + "/api/versao")
    ok(v.get("dev") is True and isinstance(v.get("codigo"), int) and v["codigo"] > 0, f"/api/versao: dev={v.get('dev')}, codigo={v.get('codigo')}")
    ok(os.path.normcase(v.get("dados", "")) == os.path.normcase(DADOS), "--dados manda mesmo no --dev")
    a = _json(base + "/api/atualizacao")
    ok(a.get("dev") is True and a.get("nova") is False and a.get("arquivo") is None, f"/api/atualizacao não oferece nada: {a}")
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=800, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/", limite=60)
    t0 = time.time()
    while time.time() - t0 < 20 and not aba.avaliar("!!document.getElementById('faixa-dev')"): aba.drenar(0.5)
    ok(aba.avaliar("!!document.getElementById('faixa-dev')"), "a faixa laranja de desenvolvimento aparece na tela inicial")
    ok(aba.avaliar("document.title.indexOf('[DEV]') === 0"), f"o título começa com [DEV]: {aba.avaliar('document.title')}")
    rot = aba.avaliar("(document.getElementById('versao-programa') || {}).textContent || ''") or ""
    ok(rot.endswith(" dev") and "recarregar" not in rot, f"o rótulo da versão diz dev: {rot!r}")
    ok(not aba.avaliar("!!document.getElementById('btn-atualizar')"), "sem botão Atualizar")
    # um arquivo de tela muda no disco: o rótulo pede para recarregar
    time.sleep(2.5)                                            # o carimbo do servidor é guardado por 2 s
    os.utime(css, (time.time() + 5, time.time() + 5))
    t0 = time.time()
    while time.time() - t0 < 15 and "recarregar" not in (aba.avaliar("(document.getElementById('versao-programa') || {}).textContent || ''") or ""):
        aba.drenar(0.5)
    rot2 = aba.avaliar("(document.getElementById('versao-programa') || {}).textContent || ''") or ""
    ok("código novo" in rot2 and "recarregar" in rot2, f"código de tela novo no disco → o rótulo pede F5: {rot2!r}")
    foto(aba, "_dev.png")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    os.utime(css, (mtime, mtime))
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
