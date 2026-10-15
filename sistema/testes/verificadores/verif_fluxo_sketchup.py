# -*- coding: utf-8 -*-
"""O fluxo do SketchUp no editor 3D (15/10/2026), só com o mouse e o teclado (CDP): R e "3000;2000"; P e "1000", logo
depois "1500" (corrige); O na face de cima e "200"; L, → "1000", ← "500" e Enter; C, "300" e logo depois "500"; T na aresta
de cima e "150" (a guia paralela); X, Z (o plano de seção), "700" e Delete; Ctrl+Z até o modelo vazio."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo3_")
PASTA = os.path.join(DADOS, "f3")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fluxo3", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-15T00:00:00", "alterado": "2026-10-15T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
json.dump(Documento().dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo3_")
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
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=f3", limite=60)
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

    js("""editor.camera.enquadrar([[-5000, -6000, -500], [11000, 8000, 3000]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
    aba.drenar(0.5)
    barras = lambda: js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => ({ id: e.id, i: e.inicio.map(Math.round), f: e.fim.map(Math.round), papel: e.papel }));")

    solidos = lambda: js("""return [...editor.documento.entidades.values()].filter(e => e.tipo === 'solido' && !(e.atributos && (e.atributos.cota || e.atributos.tipo === 'construcao'))).map(e => {
      const v = e.vertices; const lim = [0, 1, 2].map(i => [Math.round(Math.min(...v.map(p => p[i]))), Math.round(Math.max(...v.map(p => p[i])))]);
      return { nome: e.nome, nv: v.length, nf: (e.faces || []).length, lim, raio: e.atributos && e.atributos.raio }; });""")
    # 1. R e 3000;2000
    tecla("r")
    clicar(*tela([0, 0, 0]))
    mover(*tela([1000, 800, 0]))
    digitar("3000;2000")
    tecla("Escape")
    s1 = solidos()
    ok(s1 and len(s1) == 1 and s1[0]["lim"][0][1] - s1[0]["lim"][0][0] == 3000 and s1[0]["lim"][1][1] - s1[0]["lim"][1][0] == 2000,
       f"R e 3000;2000: o retângulo: {s1}")
    o = [s1[0]["lim"][0][0], s1[0]["lim"][1][0], 0] if s1 else [0, 0, 0]
    # 2. P na face, 1000 e logo depois 1500
    tecla("p")
    clicar(*tela([o[0] + 1500, o[1] + 1000, 0]))
    digitar("1000")
    h1 = (solidos() or [{}])[0].get("lim")
    digitar("1500")
    h2 = (solidos() or [{}])[0].get("lim")
    tecla("Escape")
    ok(h1 and h1[2] == [0, 1000] and h2 and h2[2] == [0, 1500] and len(solidos()) == 1, f"P na face: 1000 e o 1500 logo depois corrige: {(h1 and h1[2], h2 and h2[2])}")
    # 3. O na face de cima e 200
    tecla("o")
    clicar(*tela([o[0] + 1500, o[1] + 1000, 1500]))
    digitar("200")
    tecla("Escape")
    off = [q for q in (solidos() or []) if q["nome"] == "Deslocamento"]
    ok(len(off) == 1 and sorted([off[0]["lim"][0][1] - off[0]["lim"][0][0], off[0]["lim"][1][1] - off[0]["lim"][1][0]]) in ([2400, 3400], [1600, 2600]),
       f"O na face de cima e 200: o contorno paralelo: {off}")
    # 4. L, → 1000, ← 500 e Enter (a polilinha)
    tecla("l")
    clicar(*tela([o[0], o[1] - 1500, 0]))
    tecla("ArrowRight"); digitar("1000")
    tecla("ArrowLeft"); digitar("500")
    tecla("Enter"); tecla("Escape")
    lin = js("""return [...editor.documento.entidades.values()].filter(e => e.tipo === 'solido' && !(e.faces || []).length && (e.arestas_vivas || []).length && !(e.atributos && (e.atributos.cota || e.atributos.tipo === 'construcao'))).map(e => e.vertices.map(p => p.map(Math.round)));""")
    ok(lin and len(lin) == 1 and len(lin[0]) == 3 and lin[0][1][0] - lin[0][0][0] == 1000 and abs(lin[0][2][1] - lin[0][1][1]) == 500,
       f"L, → 1000, ← 500 e Enter: a polilinha de dois segmentos: {lin}")
    # 5. C, 300 e logo depois 500
    tecla("c")
    clicar(*tela([o[0] + 5000, o[1] + 1000, 0]))
    mover(*tela([o[0] + 5200, o[1] + 1000, 0]))
    digitar("300")
    digitar("500")
    tecla("Escape")
    circ = [q["raio"] for q in (solidos() or []) if q["nome"] == "Círculo"]
    ok(circ == [500], f"C, 300 e o 500 logo depois corrige (um círculo só): {circ}")
    # 6. T na aresta de cima da caixa e 150 (a guia paralela)
    tecla("t")
    ar = js(f"""const r = editor.el.canvas.getBoundingClientRect();
      for (const [x, y] of [[{o[0] + 1000}, {o[1]}], [{o[0] + 1000}, {o[1] + 2000}], [{o[0]}, {o[1] + 700}], [{o[0] + 3000}, {o[1] + 700}]]) {{
        const t = editor.camera.paraTela([x, y, 1500]); const s = editor.inferencia.resolver(t[0], t[1], {{}});
        if (s.tipoSnap === 'sobre_aresta') return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];
      }} return null;""")
    if ar:
        clicar(*ar)
        mover(ar[0] + 30, ar[1] + 40)
        digitar("150")
    tecla("Escape")
    guia = js("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.tipo === 'construcao').map(e => e.atributos.afastamento);")
    ok(ar and guia == [150], f"T na aresta de cima e 150: a guia paralela a 150: {(ar, guia)}")
    # 7. X, Z (o plano de seção pelo meio do modelo), 700 e Delete
    tecla("x")
    tecla("z")
    p0 = js("return editor.cena.planoCorte && editor.cena.planoCorte.origem.map(Math.round);")
    digitar("700")
    p1 = js("return editor.cena.planoCorte && editor.cena.planoCorte.origem.map(Math.round);")
    tecla("Delete")
    p2 = js("return editor.cena.planoCorte;")
    tecla("Escape")
    ok(p0 and p1 and p1[2] - p0[2] == 700 and p2 is None, f"X, Z: o plano de seção; 700 o desloca; Delete tira: {(p0, p1, p2)}")
    # 8. Ctrl+Z até o modelo vazio
    for _ in range(30):
        if js("return editor.documento.entidades.size;") == 0: break
        tecla("z", 2)
    ok(js("return editor.documento.entidades.size;") == 0, "Ctrl+Z desfaz tudo, até o modelo vazio")
    erros_1 = []
    erros = erros_1 + [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
