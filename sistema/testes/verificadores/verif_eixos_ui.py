# -*- coding: utf-8 -*-
"""Editor 3D: diálogo Eixos da obra — abre com as duas tabelas (letras e números) vindas da
análise do modelo, "+ eixo" acrescenta uma linha, e o diálogo fecha sem gravar."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8807
DADOS = tempfile.mkdtemp(prefix="metalica_eixosui_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_eixosui_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("window.editor && window.editor.documento && window.editor.documento.entidades.size > 100"): aba.drenar(0.5)
    aba.avaliar("window.editor.dialogoEixos(); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("window.editor.el.dialogo.open && window.editor.el.dialogoCorpo.querySelectorAll('input').length > 0"): aba.drenar(0.5)
    n_in = aba.avaliar("window.editor.el.dialogoCorpo.querySelectorAll('input').length") or 0
    txt = aba.avaliar("window.editor.el.dialogoCorpo.textContent") or ""
    ok(n_in >= 4 and "Eixos com letra" in txt and "Eixos numerados" in txt, f"diálogo dos eixos com {n_in} campos: " + txt[:120])
    aba.avaliar("[...window.editor.el.dialogoCorpo.querySelectorAll('button')].find(b => b.textContent === '+ eixo').click(); 1")
    n2 = aba.avaliar("window.editor.el.dialogoCorpo.querySelectorAll('input').length") or 0
    ok(n2 == n_in + 2, f"+ eixo acrescenta uma linha ({n2} campos)")
    foto(aba, "_eixos.png")
    aba.avaliar("window.editor.el.dialogo.close('cancelar'); 1")
    aba.drenar(0.5)
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
