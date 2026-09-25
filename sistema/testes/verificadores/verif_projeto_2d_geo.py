# -*- coding: utf-8 -*-
"""Projeto recebido sem perfil escrito (DXF só de linhas, em cm), pela tela do CAD:
1) "Projeto recebido" gera o 3D com os perfis padrão por papel e avisa;
2) "Gerar modelo 3D do desenho…" pede um perfil por papel, e o escolhido vai para o modelo."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
import projeto_2d_sem_texto as ex
PORTA = 8794
DADOS = tempfile.mkdtemp(prefix="metalica_proj2dgeo_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def pedir(rota):
    return json.load(urllib.request.urlopen(base + urllib.parse.quote(rota), timeout=60))


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        return json.load(e)


def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def esperar_dialogo(aba, titulo, limite=90):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar("(() => { const d = document.querySelector('dialog[open]'); return !!d && d.querySelector('#dialogo-titulo').textContent === %s; })()" % json.dumps(titulo)):
            return True
        aba.drenar(0.5)
    return False


tmp = tempfile.mkdtemp(prefix="proj2dgeo_arq_")
dxf = ex.dxf(os.path.join(tmp, "galpao_sem_texto.dxf"))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_proj2dgeo_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos", {"nome": "Galpão sem texto", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    ok(bool(slug), f"projeto criado: {slug}")
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/cad?projeto=" + slug, limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && !!window.cad"): aba.drenar(0.5)

    # ---- 1. projeto recebido de uma vez: perfis padrão
    aba.avaliar("window.__b64 = %s; 1" % json.dumps(base64.b64encode(open(dxf, "rb").read()).decode()))
    aba.avaliar("(() => { const b = atob(window.__b64); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);"
                " window.cad.projetoRecebido(new File([u], 'galpao_sem_texto.dxf')); return 1; })()")
    ok(esperar_dialogo(aba, "Projeto recebido → modelo 3D", 10), "diálogo do projeto recebido abriu")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    ok(esperar_dialogo(aba, "Projeto recebido", 120), "resultado do projeto recebido")
    txt = aba.avaliar("document.querySelector('dialog[open] #dialogo-corpo').textContent")
    ok("Modelo 3D:" in txt and "barra" in txt, "modelo gerado: " + txt[:120])
    ok("só pela forma" in txt and "pilar → W 250" in txt, "aviso dos perfis padrão por papel")
    ok("centímetros" in txt, "aviso do desenho em centímetros")
    ok("desenho em cm" in txt, "escala das vistas: desenho em cm")
    foto(aba, "_projeto2dgeo_resultado.png")
    aba.avaliar("document.querySelector('#dialogo-cancelar').click(); 1"); aba.drenar(0.5)
    modelo = pedir(f"/api/projetos/{slug}/modelo")
    ents = (modelo.get("documento") or {}).get("entidades") or []
    pilares = [e for e in ents if e.get("tipo") == "barra" and e.get("papel") == "pilar"]
    ok(len(pilares) == 3 * ex.N_EIXOS + 2 * len(ex.POSTES), f"{len(pilares)} pilares no modelo")
    ok(pilares and all(e.get("perfil") == "W 250×32,7" for e in pilares), "pilares com o perfil padrão")

    # ---- 2. gerar de novo pelo diálogo, escolhendo o perfil do pilar
    aba.avaliar("window.cad.dialogoGerar3D(); 1")
    ok(esperar_dialogo(aba, "Gerar modelo 3D das vistas", 30), "diálogo da montagem")
    n_campos = aba.avaliar("document.querySelectorAll('dialog[open] input[list=\"perfis-por-papel\"]').length")
    ok(n_campos >= 7, f"{n_campos} campos de perfil por papel")
    ok(aba.avaliar("(() => { const l = [...document.querySelectorAll('dialog[open] .montagem label')].find(x => x.textContent.startsWith('pilar'));"
                   " return !!l && l.nextElementSibling.value === 'W 250 x 32,7'; })()"), "campo do pilar com a sugestão")
    foto(aba, "_projeto2dgeo_montagem.png")
    aba.avaliar("(() => { const l = [...document.querySelectorAll('dialog[open] .montagem label')].find(x => x.textContent.startsWith('pilar'));"
                " l.nextElementSibling.value = 'W 200 x 26,6'; return 1; })()")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    ok(esperar_dialogo(aba, "Modelo 3D gerado", 90), "modelo gerado de novo")
    aba.avaliar("document.querySelector('#dialogo-cancelar').click(); 1"); aba.drenar(0.5)
    modelo = pedir(f"/api/projetos/{slug}/modelo")
    ents = (modelo.get("documento") or {}).get("entidades") or []
    pilares = [e for e in ents if e.get("tipo") == "barra" and e.get("papel") == "pilar"]
    ok(pilares and all(e.get("perfil") == "W 200×26,6" for e in pilares), "pilares com o perfil escolhido no diálogo")
    ok(aba.avaliar("(window.cad.doc.metadados.reconhecimento.perfis || {}).pilar") == "W 200 x 26,6", "o perfil escolhido fica guardado no desenho")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
