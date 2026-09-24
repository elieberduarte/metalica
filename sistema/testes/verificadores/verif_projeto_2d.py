# -*- coding: utf-8 -*-
"""Projeto recebido em DXF/PDF → modelo 3D e IFC, pela tela do CAD:
1) "Projeto recebido (DXF/PDF) → modelo 3D e IFC" com o DXF do galpão de exemplo;
2) importar o PDF num desenho em branco, reconhecer as peças e gerar o modelo das vistas."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
import projeto_2d_exemplo as ex
PORTA = 8791
DADOS = tempfile.mkdtemp(prefix="metalica_proj2d_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []
TOTAL = 182


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


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


tmp = tempfile.mkdtemp(prefix="proj2d_arq_")
dxf = ex.dxf(os.path.join(tmp, "galpao.dxf"))
pdf = ex.pdf(os.path.join(tmp, "galpao.pdf"))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_proj2d_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos", {"nome": "Galpão recebido", "tipo": "desenho"})
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
    ok(aba.avaliar("!!document.querySelector('[data-acao=\"projeto-2d\"]') && !!document.querySelector('[data-acao=\"reconhecer\"]')"),
       "menus Projeto recebido e Reconhecer presentes")

    # ---- 1. projeto recebido de uma vez
    aba.avaliar("window.__b64 = %s; 1" % json.dumps(base64.b64encode(open(dxf, "rb").read()).decode()))
    aba.avaliar("(() => { const b = atob(window.__b64); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);"
                " window.cad.projetoRecebido(new File([u], 'galpao.dxf')); return 1; })()")
    ok(esperar_dialogo(aba, "Projeto recebido → modelo 3D", 10), "diálogo do projeto recebido abriu")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    ok(esperar_dialogo(aba, "Projeto recebido", 120), "resultado do projeto recebido")
    txt = aba.avaliar("document.querySelector('dialog[open] #dialogo-corpo').textContent")
    ok(("Modelo 3D: %d barra" % TOTAL) in txt, "modelo com %d barras: %s" % (TOTAL, txt[:160]))
    ok(aba.avaliar("!!document.querySelector('dialog[open] a[href$=\".ifc\"]')"), "link do IFC")
    ifc = aba.avaliar("document.querySelector('dialog[open] a[href$=\".ifc\"]').getAttribute('href')")
    try:
        conteudo = urllib.request.urlopen(base + urllib.parse.quote(urllib.parse.unquote(ifc)), timeout=30).read()
        ok(conteudo.startswith(b"ISO-10303-21") and conteudo.count(b"IFCBEAM") + conteudo.count(b"IFCMEMBER") + conteudo.count(b"IFCCOLUMN") >= TOTAL,
           f"IFC baixa ({len(conteudo) // 1024} kB)")
    except Exception as e:  # noqa: BLE001
        ok(False, f"IFC não baixou: {e}")
    ok(aba.avaliar("window.cad.nomeDesenho").startswith("Projeto recebido"), "o desenho do projeto recebido abriu no CAD")
    ok(aba.avaliar("window.cad.doc.camadas.has('PEÇAS RECONHECIDAS') && window.cad.doc.camadas.has('PEÇAS A CONFERIR')"), "camadas das peças")
    foto(aba, "_projeto2d_resultado.png")
    aba.avaliar("document.querySelector('#dialogo-cancelar').click(); 1"); aba.drenar(0.5)
    foto(aba, "_projeto2d_desenho.png")

    # ---- 2. PDF num desenho em branco → reconhecer → gerar
    post(f"/api/projetos/{slug}/desenhos/pdf-teste", {"desenho": {"nome": "pdf-teste", "escala": 1, "entidades": []}})
    aba.navegar(base + f"/cad?projeto={slug}&desenho=pdf-teste", limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && !!window.cad"): aba.drenar(0.5)
    aba.avaliar("window.__b64 = %s; 1" % json.dumps(base64.b64encode(open(pdf, "rb").read()).decode()))
    aba.avaliar("(() => { const b = atob(window.__b64); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);"
                " window.cad.importarPDF(new File([u], 'galpao.pdf')); return 1; })()")
    ok(esperar_dialogo(aba, "Importar PDF", 10), "diálogo do PDF")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and aba.avaliar("window.cad.doc.tamanho") < 100: aba.drenar(0.5)
    ok(aba.avaliar("window.cad.doc.tamanho") > 150, "PDF importado: %s objetos" % aba.avaliar("window.cad.doc.tamanho"))
    aba.avaliar("window.cad.reconhecerPecas(); 1")
    ok(esperar_dialogo(aba, "Peças reconhecidas", 60), "reconhecimento")
    txt = aba.avaliar("document.querySelector('dialog[open] #dialogo-corpo').textContent")
    ok("1:50" in txt and "1:100" in txt, "escalas 1:50 e 1:100 pelas cotas: " + txt[:200])
    foto(aba, "_projeto2d_reconhecido.png")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    ok(esperar_dialogo(aba, "Gerar modelo 3D das vistas", 20), "montagem das vistas")
    ok(aba.avaliar("document.querySelectorAll('dialog[open] fieldset.montagem').length") == 2, "duas vistas na montagem")
    foto(aba, "_projeto2d_montagem.png")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    ok(esperar_dialogo(aba, "Modelo 3D gerado", 90), "modelo gerado")
    txt = aba.avaliar("document.querySelector('dialog[open] #dialogo-corpo').textContent")
    ok(("%d barra" % TOTAL) in txt, "PDF: modelo com %d barras: %s" % (TOTAL, txt[:160]))
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and aba.avaliar("location.pathname") != "/editor": aba.drenar(0.5)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("document.body.dataset.pronto === '1'"): aba.drenar(0.5)
    aba.drenar(3)
    foto(aba, "_projeto2d_3d.png")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
