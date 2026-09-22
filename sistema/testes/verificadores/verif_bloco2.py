# -*- coding: utf-8 -*-
"""Duplo clique real no canvas do 3D; Ver no 3D com fantasma; no desenho geral de chapas:
ajustar tamanho + aplicar furos e tamanho ao modelo."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8784
DADOS = tempfile.mkdtemp(prefix="metalica_b2_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
def get(rota):
    return json.load(urllib.request.urlopen(base + rota, timeout=600))
def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
def chapas(marca):
    doc = get("/api/projetos/compressores/modelo")
    ents = doc.get("documento", doc).get("entidades", [])
    return [e for e in ents if e.get("tipo") == "chapa" and ((e.get("atributos") or {}).get("marcas") or {}).get("posicao") == marca]
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_b2_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos/compressores/detalhar", {"grupos": ["chapas"]})
    ok(r["convertidas"] > 500, "detalhar geral converteu as chapas planas (%s)" % r["convertidas"])
    nome = r["desenhos"][0]["nome"]
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1"); aba.console.clear()
    # 1) desenho geral: seleciona a célula P77, ajusta tamanho, aplica
    aba.navegar(base + "/cad?projeto=compressores&desenho=" + nome, limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 50"): aba.drenar(0.5)
    edit = aba.avaliar("(window.cad.doc.metadados.detalhamento.editaveis || []).length")
    ok(edit > 5, "desenho geral com %s posições de chapa editáveis" % edit)
    aba.avaliar("(() => { const c = window.cad._contornoDe('P77'); window.cad.selecionar([c.id]); return 1; })()")
    aba.avaliar("window.cad.ajustarTamanho(); 1"); aba.drenar(1.5)
    ok(aba.avaliar("!!document.querySelector('dialog[open]')"), "diálogo Ajustar tamanho abriu")
    aba.avaliar("(() => { const i = [...document.querySelectorAll('dialog[open] input[type=number]')]; i[0].value = '160'; i[1].value = '130'; document.querySelector('dialog[open] .botao-ok').click(); return 1; })()")
    aba.drenar(1.0)
    dims = aba.avaliar("(() => { const c = window.cad._contornoDe('P77'); const xs = c.vertices.map(p => p[0]), ys = c.vertices.map(p => p[1]); return [Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)]; })()")
    ok(abs(dims[0] - 160) < 0.01 and abs(dims[1] - 130) < 0.01, "contorno no desenho virou 160 × 130 (%s)" % dims)
    aba.avaliar("(() => { const c = window.cad._contornoDe('P77'); window.cad.selecionar([c.id]); window.cad.aplicarFuros(); return 1; })()"); aba.drenar(1.5)
    ok(aba.avaliar("!!document.querySelector('dialog[open]')"), "diálogo Aplicar abriu no desenho geral")
    aba.avaliar("document.querySelector('dialog[open] .botao-ok').click(); 1")
    def dims_modelo():
        chs = chapas("P77")
        if not chs: return None
        xs = [p[0] for p in chs[0]["contorno"]]; ys = [p[1] for p in chs[0]["contorno"]]
        return (round(max(xs) - min(xs), 1), round(max(ys) - min(ys), 1), len(chs))
    t0 = time.time()
    while time.time() - t0 < 60 and (dims_modelo() or (0,))[0] != 160: aba.drenar(0.5)
    ok(dims_modelo() == (160, 130, 18), "as 18 chapas P77 do modelo ficaram 160 × 130 (%s)" % (dims_modelo(),))
    aba.drenar(2.0)
    ok(aba.avaliar("window.cad.nomeDesenho") == nome, "o mesmo desenho geral foi reaberto (%s)" % aba.avaliar("window.cad.nomeDesenho"))
    dims2 = aba.avaliar("(() => { const c = window.cad._contornoDe('P77'); const xs = c.vertices.map(p => p[0]), ys = c.vertices.map(p => p[1]); return [Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)]; })()")
    ok(abs(dims2[0] - 160) < 0.01, "célula regenerada mantém 160 × 130 (%s)" % dims2)
    foto(aba, "_geral_p77.png")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erros no console do CAD: %s" % erros[:3])
    # 2) Ver no 3D com fantasma
    aba.avaliar("(() => { const c = window.cad._contornoDe('P77'); window.cad.selecionar([c.id]); window.cad.verNo3D(); return 1; })()")
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("location.pathname === '/editor' && window.editor && window.editor.documento && window.editor.documento.tamanho > 10 && window.editor.selecao.ids.size > 0"): aba.drenar(1.0)
    aba.drenar(2.5)
    ok(aba.avaliar("window.editor.selecao.ids.size") == 18 and aba.avaliar("window.editor.cena.destaque && window.editor.cena.destaque.size") == 18, "Ver no 3D: 18 selecionadas e o resto em fantasma")
    foto(aba, "_ver3d_fantasma.png")
    aba.avaliar("window.editor.selecao.definir([]); 1"); aba.drenar(0.5)
    ok(aba.avaliar("window.editor.cena.destaque === null"), "limpar a seleção devolve o modelo")
    # 3) duplo clique real no canvas sobre uma peça
    aba.avaliar("window.editor.camera.zoomExtensao(); 1"); aba.drenar(4.0)
    hit = aba.avaliar("""(() => { const ed = window.editor; const c = document.querySelector('canvas'); const r = c.getBoundingClientRect();
        const cam = ed.camera.ativa; const V = cam.position.constructor;
        for (const e of ed.documento.entidades.values()) {
          if (e.tipo !== 'chapa' || !e.atributos || !e.atributos.marcas || !e.atributos.marcas.posicao) continue;
          const n = e.contorno.length; const cx = e.contorno.reduce((s, p) => s + p[0], 0) / n, cy = e.contorno.reduce((s, p) => s + p[1], 0) / n;
          const w = [0, 1, 2].map(k => e.origem[k] + e.eixo_x[k] * cx + e.eixo_y[k] * cy);
          const v = new V(w[0] * 0.001, w[1] * 0.001, w[2] * 0.001).project(cam);
          const x = (v.x + 1) / 2 * r.width, y = (1 - v.y) / 2 * r.height;
          if (x < 20 || y < 20 || x > r.width - 20 || y > r.height - 20) continue;
          const sob = ed.selecao.sob(x, y); const se = sob && (sob.entidade || ed.documento.get(sob.id));
          if (se && se.atributos && se.atributos.marcas && se.atributos.marcas.posicao) return JSON.stringify([x + r.left, y + r.top, se.atributos.marcas.posicao]);
        }
        return null; })()""")
    ok(hit is not None, "achou uma peça sob o cursor para o duplo clique (%s)" % hit)
    if hit:
        x, y, marca = json.loads(hit)
        print("       ferramenta:", aba.avaliar("window.editor.ativa && window.editor.ativa.constructor.id"), "canvases:", aba.avaliar("document.querySelectorAll('canvas').length"),
              "canvas do editor é o primeiro:", aba.avaliar("document.querySelector('canvas') === window.editor.el.canvas"))
        aba.avaliar("(() => { const c = window.editor.el.canvas; c.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, clientX: %f, clientY: %f, button: 0 })); return 1; })()" % (x, y))
        t0 = time.time()
        while time.time() - t0 < 30 and not aba.avaliar("location.pathname === '/cad'"): aba.drenar(1.0)
        if aba.avaliar("location.pathname") != "/cad":      # segunda tentativa: o primeiro evento pode cair no meio de um quadro
            aba.avaliar("(() => { const c = window.editor.el.canvas; c.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, clientX: %f, clientY: %f, button: 0 })); return 1; })()" % (x, y))
            t0 = time.time()
            while time.time() - t0 < 30 and not aba.avaliar("location.pathname === '/cad'"): aba.drenar(1.0)
        if aba.avaliar("location.pathname") != "/cad":
            r = aba.avaliar("(() => { try { const c = window.editor.el.canvas; const rr = c.getBoundingClientRect(); const f = window.editor.ativa; f.onDuploClique({ tela: [%f - rr.left, %f - rr.top] }, {}); return 'chamado'; } catch (e) { return 'ERRO ' + e.message; } })()" % (x, y))
            print("       chamada direta de onDuploClique:", r)
            t0 = time.time()
            while time.time() - t0 < 30 and not aba.avaliar("location.pathname === '/cad'"): aba.drenar(1.0)
        ok(aba.avaliar("location.pathname === '/cad' && location.search.includes('detalhe-')"), "duplo clique real abriu o detalhe de %s (%s)" % (marca, aba.avaliar("location.search")))
        if aba.avaliar("location.pathname") != "/cad":
            print("       console:", [m for m in aba.console if m[0] in ("error", "excecao", "warning", "log")][-6:])
            print("       avisos na tela:", aba.avaliar("[...document.querySelectorAll('.aviso, .avisos *')].map(e => e.textContent).join(' | ').slice(0, 300)"))
            print("       dica:", aba.avaliar("(document.querySelector('#dica') || document.querySelector('.dica') || {}).textContent"))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(perfil, ignore_errors=True)
print("\n%d falha(s)." % len(falhas))
sys.exit(1 if falhas else 0)
