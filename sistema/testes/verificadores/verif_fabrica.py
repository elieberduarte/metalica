# -*- coding: utf-8 -*-
"""Regras da fábrica: validação de perfil dobrado, registro dos perfis da fábrica e a seção no Catálogo."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8787
DADOS = tempfile.mkdtemp(prefix="metalica_fabrica_")
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fabrica_")
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
    import urllib.request
    def post(rota, corpo):
        req = urllib.request.Request(base + rota, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            return json.load(e)
    v = post("/api/fabrica/validar", {"perfil": "U92X30X#13"})
    ok(v.get("ok") and v.get("tipo") == "dobrado" and abs(v.get("desenvolvido", 0) - 144.6) < 0.2, f"U92X30X#13 dobrado, tira 144,6: {v}")
    v = post("/api/fabrica/validar", {"perfil": "U400X150X#8"})
    ok(v.get("ok") is False and "largura" in " ".join(v.get("motivos", [])), f"U400X150X#8 barrado pela largura da tira: {v.get('motivos')}")
    v = post("/api/fabrica/validar", {"perfil": "U100X50X#27"})
    ok(v.get("ok") is False and "bitola #27" in " ".join(v.get("motivos", [])), "bitola #27 desconhecida")
    r = post("/api/fabrica/perfis", {"perfil": "U92X30X#13", "projeto": "compressores"})
    ok(r.get("registro", {}).get("usos") == 1, f"registrado: {r}")
    r = post("/api/fabrica/perfis", {"perfil": "U400X150X#8", "projeto": "compressores"})
    ok("erro" in r, f"não registra perfil barrado: {r}")
    r = post("/api/fabrica/regras", {"regras": {"largura_max_tira": "700", "conferidas": True}})
    ok(r.get("regras", {}).get("largura_max_tira") == 700.0 and r["regras"]["conferidas"], "regras gravadas")
    v = post("/api/fabrica/validar", {"perfil": "U400X150X#8"})
    ok(v.get("ok") is True, "com 700 mm de tira o U400X150X#8 passa")
    # tela do catálogo
    aba.navegar(base + "/catalogo", limite=60)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.querySelectorAll('#fabrica-perfis table tbody tr').length > 0"): aba.drenar(0.4)
    ok(aba.avaliar("document.querySelector('#regra-largura_max_tira').value") == "700", "Catálogo mostra as regras gravadas")
    ok(aba.avaliar("document.querySelector('#fabrica-perfis tbody tr td').textContent") == "U92X30X#13", "Catálogo lista o perfil da fábrica")
    foto(aba, "_fabrica.png")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"sem erros de JavaScript: {erros[:3]}")
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("FALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
