# -*- coding: utf-8 -*-
"""Editor 3D: Ver → Verificar apoios — o painel abre com os achados por regra (as regras de
nucleo3d/apoios.py), clicar num achado seleciona as peças dele, e o × fecha o painel."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_apoiosui_")
os.makedirs(os.path.join(DADOS, "compressores"))
# o modelo de exemplo com uma viga solta no ar, longe de tudo: um achado garantido
_m = json.load(open(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), encoding="utf-8"))
_ents = _m["entidades"]
_voando = {"id": "viga-voando", "tipo": "barra", "nome": "W 200×19,3", "camada": "Estrutura", "inicio": [0.0, -30000.0, 9000.0],
           "fim": [4000.0, -30000.0, 9000.0], "perfil": "W 200×19,3", "papel": "viga", "rotacao": 0.0, "atributos": {}}
if isinstance(_ents, dict):
    _ents["viga-voando"] = _voando
else:
    _ents.append(_voando)
json.dump(_m, open(os.path.join(DADOS, "compressores", "modelo.json"), "w", encoding="utf-8"))
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_apoiosui_")
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
    aba.avaliar("document.querySelector('[data-acao=verificar-apoios]').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 120 and not aba.avaliar("!!document.querySelector('.painel-apoios')"): aba.drenar(0.5)
    txt = aba.avaliar("(document.querySelector('.painel-apoios') || {}).textContent || ''") or ""
    ok("Verificar apoios" in txt and "achado(s) em" in txt and "voando" in txt, "painel dos apoios aberto: " + txt[:160])
    n_li = aba.avaliar("document.querySelectorAll('.painel-apoios li:not(.mais)').length") or 0
    ok(n_li > 0, f"{n_li} achado(s) listados")
    if n_li:
        aba.avaliar("document.querySelector('.painel-apoios li:not(.mais)').click(); 1")
        aba.drenar(1.0)
        n_sel = aba.avaliar("window.editor.selecao.ids.size") or 0
        ok(n_sel > 0, f"clicar no achado seleciona {n_sel} peça(s)")
    foto(aba, "_apoios.png")
    aba.avaliar("[...document.querySelectorAll('.painel-apoios button')].find(b => b.textContent === '×').click(); 1")
    ok(not aba.avaliar("!!document.querySelector('.painel-apoios')"), "o × fecha o painel")
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
