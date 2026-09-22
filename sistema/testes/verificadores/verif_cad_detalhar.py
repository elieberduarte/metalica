# -*- coding: utf-8 -*-
"""CAD: menu Vistas do modelo → Detalhar peças e conjuntos… gera e abre o desenho; ETag/no-cache nos estáticos."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8778
DADOS = tempfile.mkdtemp(prefix="metalica_cd_")
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cd_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = urllib.request.urlopen(base + "/cad/cad.js")
    etag = r.headers.get("ETag"); cc = r.headers.get("Cache-Control")
    ok(etag and cc == "no-cache", f"estático com ETag {etag} e Cache-Control {cc}")
    req = urllib.request.Request(base + "/cad/cad.js", headers={"If-None-Match": etag})
    try:
        urllib.request.urlopen(req); ok(False, "304 esperado")
    except urllib.error.HTTPError as e:
        ok(e.code == 304, "revalidação devolve 304")
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/cad?projeto=compressores", limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && !!window.cad"): aba.drenar(0.5)
    ok(aba.avaliar("!!document.querySelector('[data-acao=\"detalhar\"]')"), "menu do CAD tem 'Detalhar peças e conjuntos…'")
    aba.avaliar("window.cad.dialogoDetalhar(); 1"); aba.drenar(1.0)
    ok(aba.avaliar("!!document.querySelector('dialog[open]')"), "diálogo abriu")
    aba.avaliar("document.querySelector('dialog[open] .botao-ok').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 120 and not aba.avaliar("window.cad.doc.tamanho > 100"): aba.drenar(1.0)
    ok(aba.avaliar("window.cad.doc.tamanho") > 100 and aba.avaliar("document.title").startswith("Detalhamento"), "detalhou e abriu o desenho de chapas no CAD: %s" % aba.avaliar("document.title"))
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
