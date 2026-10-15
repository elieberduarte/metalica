# -*- coding: utf-8 -*-
"""O Escalar pelas alças e a Seção gerando o desenho do corte (15/10/2026, item 7 do briefing do editor 3D), só com o mouse
e o teclado (CDP): na viga, a alça do meio da ponta fica destacada ao passar o mouse, o clique a pega e "6000" estica a
viga; na chapa, o meio da face Y e "400", o canto e
"0,5"; na barra só há as alças das pontas; Ctrl+Z volta tudo; X, X e G abrem o diálogo, e "Gerar e abrir" grava o desenho do corte no projeto."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Chapa, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo_esc_")
PASTA = os.path.join(DADOS, "fe")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "FluxoEscalar", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-15T00:00:00", "alterado": "2026-10-15T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
viga = Barra(nome="viga", inicio=(0.0, 0.0, 0.0), fim=(4000.0, 0.0, 0.0), perfil="W 200×15,0", rotacao=0.0, papel="viga")
chapa = Chapa(nome="CH1", origem=(0.0, 2000.0, 0.0), contorno=[(0.0, 0.0), (300.0, 0.0), (300.0, 200.0), (0.0, 200.0)], espessura=10.0, centrada=False)
doc.add(viga); doc.add(chapa)
VIGA, CHAPA = viga.id, chapa.id
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo_esc_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
TECLAS = {"ArrowUp": 38, "ArrowRight": 39, "ArrowLeft": 37, "ArrowDown": 40, "Enter": 13, "Escape": 27, "Control": 17, " ": 32}
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=1000, deviceScaleFactor=1, mobile=False)

    def abrir():
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=fe", limite=60)
        t0 = time.time()
        while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.cena.perfil && editor.cena.perfil('W 200×15,0') !== undefined)"):
            aba.drenar(0.5)
        aba.drenar(1)

    abrir()
    aba.console.clear()

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def tela(p):
        return js(f"const t = editor.camera.paraTela({json.dumps(p)}), r = editor.el.canvas.getBoundingClientRect(); return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];")

    def mover(x, y, botoes=0):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=botoes); aba.drenar(0.08)

    def clicar(x, y, botao="left", mods=0):
        mover(x, y)
        sobre = aba.avaliar(f"(() => {{ const e = document.elementFromPoint({x}, {y}); return e === editor.el.canvas ? '' : (e ? (e.id || e.className || e.tagName) : 'nada'); }})()")
        if sobre: print(f"     (o clique em {x},{y} caiu em cima de: {sobre})")
        b = 1 if botao == "left" else 2
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=botao, clickCount=1, buttons=b, modifiers=mods)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=botao, clickCount=1, buttons=0, modifiers=mods)
        aba.drenar(0.25)

    def tecla(k, mods=0):
        code = TECLAS.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = k if len(k) == 1 else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, windowsVirtualKeyCode=code, text=texto if not mods else "", modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.15)

    def digitar(t):
        # o primeiro número vai para a caixa de medidas (o editor a foca), o resto entra nela, e Enter manda
        tecla(t[0])
        if len(t) > 1: aba.cmd("Input.insertText", text=t[1:])
        aba.drenar(0.05)
        tecla("Enter")
        aba.drenar(0.3)

    # a abertura do editor faz um enquadramento animado próprio, que às vezes termina depois do nosso e o desfaz: espera
    # a câmera assentar, enquadra e confere que ela ficou
    pos_cam = lambda: js("const c = editor.camera.ativa.position; return [c.x, c.y, c.z].map(v => Math.round(v * 1000));")
    for _ in range(5):
        aba.drenar(0.8)
        js("""editor.camera.enquadrar([[-1500, -1500, -500], [5500, 3500, 1000]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
        a_ = pos_cam(); aba.drenar(0.8)
        if pos_cam() == a_: break
    aba.drenar(0.5)
    ent = lambda i: js(f"return editor.documento.get('{i}');")
    alca_xy = lambda s: js(f"const t = editor.camera.paraTela(editor.ativa.pontoDaAlca({json.dumps(s)})), r = editor.el.canvas.getBoundingClientRect(); return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];")
    sob = lambda: js("const a = editor.ativa.sobAlca; return a ? { nome: a.nome, uniforme: a.uniforme } : null;")

    def selecionar(id_, ponto):
        tecla("Escape"); tecla(" ")
        clicar(*tela(ponto))
        return js("return [...editor.selecao.ids];") == [id_]

    # 1. a viga pela alça do meio da face da ponta (X+): o destaque antes do clique, o clique, "6000"
    ok(selecionar(VIGA, [2000, 0, 100]), "o clique seleciona a viga")
    tecla("e")
    mover(*alca_xy([1, 0, 0]))
    s = sob()
    ok(s == {"nome": "X", "uniforme": False}, f"passando o mouse na alça do meio da ponta: ela fica destacada (só no eixo X): {s}")
    clicar(*alca_xy([1, 0, 0]))
    ok(js("return editor.ativa.alca && editor.ativa.alca.nome;") == "X", "o clique pega a alça do meio da ponta")
    mover(*tela([5000, 0, 0]))
    digitar("6000")
    v = ent(VIGA)
    ok(v and [round(c) for c in v["inicio"]] == [0, 0, 0] and [round(c) for c in v["fim"]] == [6000, 0, 0],
       f"\"6000\": a viga fica com 6000 mm, a ponta de lá parada: {v and (v['inicio'], v['fim'])}")
    # 2. a caixa da viga é o eixo dela: no centro não há alça (as do Y e do Z não mudariam nada e caíam ali, umas em cima
    # das outras), e nas pontas só a do eixo
    tecla("Escape")
    ok(selecionar(VIGA, [3000, 0, 100]), "o clique seleciona a viga de novo")
    tecla("e")
    nomes = js("return editor.ativa.alcas().map(a => a.nome);")
    mover(*tela([3000, 0, 0]))
    ok(nomes == ["X", "X"] and sob() is None, f"na barra, só as duas alças das pontas: {nomes}, no centro: {sob()}")
    tecla("Escape"); tecla("Escape")
    # 3. a chapa: meio da face Y+ e "400"; depois o canto e "0,5"
    ok(selecionar(CHAPA, [150, 2100, 5]), "o clique seleciona a chapa")
    tecla("e")
    mover(*alca_xy([0, 1, 0]))
    clicar(*alca_xy([0, 1, 0]))
    mover(*tela([150, 2500, 0]))
    digitar("400")
    # o tamanho da chapa no mundo (o Escalar pode mexer no contorno ou nos eixos dela)
    lim = lambda: js(f"""const c = editor.documento.get('{CHAPA}'); const w = c.contorno.map(([x, y]) => [0, 1, 2].map(i => c.origem[i] + c.eixo_x[i] * x + c.eixo_y[i] * y));
      const t = (i) => Math.round(Math.max(...w.map(p => p[i])) - Math.min(...w.map(p => p[i]))); return [t(0), t(1), Math.round(Math.min(...w.map(p => p[1])))];""")
    l1 = lim()
    ok(l1 and l1[0] == 300 and l1[1] == 400, f"chapa pelo meio da face Y e \"400\": 300 × 400: {l1}")
    tecla("e")
    mover(*alca_xy([1, 1, 1]))
    s = sob()
    clicar(*alca_xy([1, 1, 1]))
    mover(*tela([0, 2000, 0]))
    digitar("0,5")
    l2 = lim()
    ok(s and s["uniforme"] and l2 and l2[0] == 150 and l2[1] == 200, f"o canto escala por igual, \"0,5\": 150 × 200: {s}, {l2}")
    tecla("Escape"); tecla("Escape")
    # 4. Ctrl+Z volta a chapa e a viga
    for _ in range(3): tecla("z", 2)
    v = ent(VIGA); l3 = lim()
    ok(v and round(v["fim"][0]) == 4000 and l3 and l3[:2] == [300, 200], f"Ctrl+Z ×3 volta a viga (4000) e a chapa (300 × 200): {v and v['fim']}, {l3}")

    # 5. a Seção gerando o desenho do corte: X, Y (o plano), G, o diálogo e "Gerar e abrir"
    tecla(" ")
    js("window.__cad = null; editor._abrirCAD = (n) => { window.__cad = n; }; return 1;")
    # X abre a Seção e, com ela aberta, X de novo põe o plano em X (pelo meio do modelo: corta a viga)
    tecla("x"); tecla("x")
    plano = js("const p = editor.ativa.plano; return p && { n: p.normal.map(Math.round), o: p.origem.map(Math.round) };")
    ok(plano and plano["n"] in ([1, 0, 0], [-1, 0, 0]) and 0 < plano["o"][0] < 4000, f"X e X: o plano de corte em X, atravessando a viga: {plano}")
    tecla("g")
    aba.drenar(0.5)
    dlg = js("return editor.el.dialogo.open;")
    ok(dlg, f"G abre o diálogo do desenho do corte: {dlg}")
    js("const b = [...editor.el.dialogo.querySelectorAll('button')].find(x => /Gerar e abrir/.test(x.textContent)); b && b.click(); return !!b;")
    t0 = time.time()
    while time.time() - t0 < 40 and not js("return window.__cad;"):
        aba.drenar(0.5)
    nome = js("return window.__cad;")
    arq = [f for f in os.listdir(os.path.join(PASTA, "desenhos-2d")) if f != "desenho.desenho.json"]
    n_ent, camadas = 0, set()
    for f in arq:
        try:
            ents = json.load(open(os.path.join(PASTA, "desenhos-2d", f), encoding="utf-8")).get("entidades", [])
            n_ent += len(ents); camadas |= {e.get("camada") for e in ents}
        except Exception: pass
    ok(nome and arq and n_ent >= 3, f"o desenho do corte (com a seção da viga) é gravado no projeto e o CAD é chamado: {nome}, {arq}, {n_ent} entidades, camadas {sorted(c for c in camadas if c)}")
    tecla("Delete"); tecla("Escape")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
