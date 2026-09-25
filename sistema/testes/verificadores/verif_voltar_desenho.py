# -*- coding: utf-8 -*-
"""Do desenho 2D para o 3D e de volta: "Modelo 3D" no CAD leva o nome do desenho, e o
"← Desenho 2D" do editor volta a ele."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8797
DADOS = tempfile.mkdtemp(prefix="metalica_voltar_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        return json.load(e)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_voltar_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos", {"nome": "Volta", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    for nome in ("primeiro", "segundo"):
        post(f"/api/projetos/{slug}/desenhos/{nome}", {"desenho": {"nome": nome, "escala": 50, "entidades": [
            {"id": "l1", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [0, 0], "b": [1000, 0]}]}})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + f"/cad?projeto={slug}&desenho=segundo", limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && !!window.cad && window.cad.nomeDesenho === 'segundo'"): aba.drenar(0.5)
    href = aba.avaliar("document.querySelector('#link-editor').getAttribute('href')")
    ok("desenho=segundo" in href, "o 'Modelo 3D' do CAD leva o desenho: " + href)
    aba.avaliar("document.querySelector('#link-editor').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("location.pathname === '/editor' && !!document.querySelector('#link-desenho') && !document.querySelector('#link-desenho').hidden"): aba.drenar(0.5)
    volta = aba.avaliar("document.querySelector('#link-desenho').getAttribute('href')")
    ok(volta == f"/cad?projeto={slug}&desenho=segundo", "o editor mostra '← Desenho 2D' para o mesmo desenho: " + str(volta))
    ok(aba.avaliar("document.querySelector('#link-desenho').textContent.includes('Desenho 2D')"), "rótulo do botão")
    aba.avaliar("document.querySelector('#link-desenho').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("location.pathname === '/cad' && !!window.cad && window.cad.nomeDesenho === 'segundo'"): aba.drenar(0.5)
    ok(aba.avaliar("location.pathname === '/cad' && window.cad.nomeDesenho === 'segundo'"), "voltou ao desenho 'segundo'")
    # aberto direto (sem vir do CAD): volta ao CAD do projeto
    aba.navegar(base + f"/editor?projeto={slug}", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!document.querySelector('#link-desenho') && !document.querySelector('#link-desenho').hidden"): aba.drenar(0.5)
    ok(aba.avaliar("document.querySelector('#link-desenho').getAttribute('href')").startswith(f"/cad?projeto={slug}"),
       "sem desenho conhecido, volta ao CAD do projeto")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
