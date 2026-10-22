# -*- coding: utf-8 -*-
"""A janela de seleção do CAD como no AutoCAD (usuário, 21/10, no Vicente Residence: "se começo a selecionar por área
ele não deixa usar o pan ou mover a janela para o lado quando o mouse chega ao fim da tela, e se dou um alt + tab que
volto o selecionar fica ativo para sempre … se clicar em um ponto vazio … já habilita o selecionar por área não precisa
ficar com ele segurado, e quando clicar em outro ponto ele fecha a área e seleciona o que tem dentro").

Eventos de mouse de verdade (Input.dispatchMouseEvent), servidor de teste com pasta vazia:
  A. clique num ponto vazio abre a janela sem segurar o botão; o segundo clique fecha e seleciona (para a direita, o que
     está inteiro dentro); da direita para a esquerda, o que toca;
  B. clique numa peça continua selecionando a peça (não abre janela);
  C. com a janela aberta, o botão do meio arrasta a vista e o primeiro canto fica no ponto do desenho clicado;
  D. com a janela aberta, o cursor na borda faz o desenho andar sozinho;
  E. Esc cancela só a janela;
  F. no meio do arrasto com o botão apertado, o botão do meio também arrasta a vista;
  G. Alt+Tab (a janela do programa perde o foco) no meio do arrasto: a janela fica aberta, e o próximo clique a fecha.
"""
import json, os, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cadjanela_")
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
    return json.load(urllib.request.urlopen(req, timeout=60))


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


def L(id_, a, b):
    return {"id": id_, "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": a, "b": b}


ents = [L("wa", [0, 0], [100, 0]), L("wb", [1000, 0], [1100, 0]), L("wc", [1050, -300], [1050, 300])]
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cadjanela_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos", {"nome": "Janela", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    post(f"/api/projetos/{slug}/desenhos/janela", {"desenho": {"nome": "Janela", "escala": 25, "entidades": ents}})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + f"/cad?projeto={slug}&desenho=janela", limite=30)
    ok(esperar(aba, "document.body.dataset.pronto === '1' && !!window.cad && window.cad.doc.tamanho === 3"), "desenho aberto")
    js = lambda s: aba.avaliar("(() => { const c = window.cad; " + s + " })()")

    def preparar():
        js("c.tela.enquadrar([[-500, -1000], [1600, 1000]]); c.ativarFerramenta('selecionar'); c.selecionar([]); return 1;")
        aba.drenar(0.3)

    def tela(p):
        x, y = json.loads(js("""const cv = c.el.canvas; const r = cv.getBoundingClientRect(); const t = c.tela.paraTela(%s);
                                return JSON.stringify([r.left + t[0], r.top + t[1]]);""" % json.dumps(p)))
        return x, y

    def evento(tipo, x, y, botao="none", botoes=0, n=1):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=n)

    def clique(x, y):
        evento("mouseMoved", x, y)
        evento("mousePressed", x, y, "left", 1)
        evento("mouseReleased", x, y, "left", 0)
        aba.drenar(0.15)

    sel = lambda: sorted(json.loads(js("return JSON.stringify([...c.tela.selecao]);")))
    aberta = lambda: js("return !!c._janela;")
    vp = lambda: json.loads(js("return JSON.stringify([c.tela.vp.x, c.tela.vp.y]);"))

    # A. clique-clique
    preparar()
    x0, y0 = tela([900, 200]); x1, y1 = tela([1200, -200])
    clique(x0, y0)
    ok(aberta(), "A. clique num ponto vazio abre a janela (sem segurar o botão)")
    evento("mouseMoved", (x0 + x1) / 2, (y0 + y1) / 2); evento("mouseMoved", x1, y1); aba.drenar(0.15)
    ok(js("return !!c.tela.retangulo;"), "A. a janela acompanha o cursor com o botão solto")
    clique(x1, y1)
    ok(sel() == ["wb"] and not aberta() and not js("return !!c.tela.retangulo;"),
       f"A. o segundo clique fecha e seleciona o que está inteiro dentro: {sel()}")
    preparar()
    xa, ya = tela([1080, 200]); xb, yb = tela([700, -200])
    clique(xa, ya); evento("mouseMoved", xb, yb); clique(xb, yb)
    ok(sel() == ["wb", "wc"], f"A. da direita para a esquerda, o que toca: {sel()}")

    # B. clique numa peça seleciona a peça
    preparar()
    xp, yp = tela([50, 0]); clique(xp, yp)
    ok(sel() == ["wa"] and not aberta(), f"B. clique numa peça seleciona a peça, sem abrir janela: {sel()}")

    # C. pan com o botão do meio com a janela aberta
    preparar()
    clique(*tela([900, 200]))
    antes = vp()
    xm, ym = 700, 450
    evento("mousePressed", xm, ym, "middle", 4); evento("mouseMoved", xm - 120, ym, "middle", 4); evento("mouseMoved", xm - 240, ym, "middle", 4)
    evento("mouseReleased", xm - 240, ym, "middle", 0); aba.drenar(0.2)
    ok(vp() != antes and aberta(), f"C. o botão do meio arrasta a vista com a janela aberta ({antes} → {vp()})")
    clique(*tela([1200, -200]))
    ok(sel() == ["wb"], f"C. depois do pan, o primeiro canto ficou no ponto do desenho clicado: {sel()}")

    # D. o cursor na borda faz o desenho andar
    preparar()
    clique(*tela([900, 200]))
    antes = vp()
    largura = js("return c.el.canvas.getBoundingClientRect().right;")
    meio_y = js("const r = c.el.canvas.getBoundingClientRect(); return r.top + r.height / 2;")
    evento("mouseMoved", largura - 4, meio_y); aba.drenar(0.6)
    depois = vp()
    ok(depois[0] > antes[0], f"D. na borda direita a vista anda para a direita sozinha ({antes} → {depois})")
    evento("mouseMoved", largura - 300, meio_y); aba.drenar(0.3)
    parado = vp(); aba.drenar(0.3)
    ok(vp() == parado, "D. longe da borda, para")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.drenar(0.2)

    # E. Esc cancela só a janela
    preparar(); js("c.selecionar(['wa']); return 1;")
    clique(*tela([900, 200]))
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.drenar(0.2)
    ok(not aberta() and not js("return !!c.tela.retangulo;") and sel() == ["wa"], f"E. Esc cancela a janela e a seleção fica: {sel()}")

    # F. o botão do meio no meio do arrasto da janela
    preparar()
    x0, y0 = tela([900, 200]); x1, y1 = tela([1200, -200])
    evento("mouseMoved", x0, y0); evento("mousePressed", x0, y0, "left", 1)
    evento("mouseMoved", x0 + 20, y0 - 20, "left", 1); evento("mouseMoved", x0 + 40, y0 - 40, "left", 1)
    antes = vp()
    evento("mouseMoved", x0 - 100, y0 - 40, "left", 5); evento("mouseMoved", x0 - 200, y0 - 40, "left", 5)
    ok(vp() != antes, f"F. o botão do meio arrasta a vista no meio do arrasto da janela ({antes} → {vp()})")
    x1, y1 = tela([1200, -200])
    evento("mouseMoved", x1, y1, "left", 1); evento("mouseReleased", x1, y1, "left", 0); aba.drenar(0.2)
    ok(sel() == ["wb"], f"F. e a janela pega o que estava no ponto do desenho do primeiro canto: {sel()}")

    # G. Alt+Tab no meio do arrasto
    preparar()
    x0, y0 = tela([900, 200]); x1, y1 = tela([1200, -200])
    evento("mouseMoved", x0, y0); evento("mousePressed", x0, y0, "left", 1)
    evento("mouseMoved", x0 + 30, y0 - 30, "left", 1); evento("mouseMoved", x0 + 60, y0 - 60, "left", 1)
    js("window.dispatchEvent(new Event('blur')); return 1;")
    aba.drenar(0.2)
    ok(aberta(), "G. Alt+Tab no meio do arrasto: a janela fica aberta (não presa ao botão que se perdeu)")
    evento("mouseMoved", x1, y1); aba.drenar(0.1)
    clique(x1, y1)
    ok(sel() == ["wb"] and not aberta() and not js("return !!c.tela.retangulo;"),
       f"G. ao voltar, o próximo clique fecha a janela e seleciona: {sel()}")
    evento("mouseMoved", x0, y0); aba.drenar(0.2)
    ok(not js("return !!c.tela.retangulo;"), "G. e depois o cursor anda sem janela")

    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.terminate()
    except Exception: pass
    srv.terminate()

print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
