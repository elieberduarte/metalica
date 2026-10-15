# -*- coding: utf-8 -*-
"""O fluxo de uso de verdade das ferramentas de detalhe (15/10/2026), só com o mouse e o teclado (CDP): a base de um pilar —
H e clique no chão, "400;400", a espessura "25" e quatro furos digitados; B em cima da chapa, ↑ e "3000" (o pilar nasce
nela); P na face de cima, "6" e logo depois "5" (corrige); a chapa selecionada, Q, ↑, no pé do pilar, "45" e logo depois "90";
V com Ctrl no pilar (180°); W, a cópia espelhada; Ctrl+Z até o modelo vazio. Nenhum erro no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo2_")
PASTA = os.path.join(DADOS, "f2")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fluxo2", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo2_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    def abrir():
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=f2", limite=60)
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

    js("""editor.camera.enquadrar([[-1200, -1200, 0], [1200, 1200, 1500]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
    aba.drenar(0.5)
    barras = lambda: js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => ({ id: e.id, i: e.inicio.map(Math.round), f: e.fim.map(Math.round), papel: e.papel }));")

    chapas = lambda: js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'chapa').map(e => ({ id: e.id, esp: e.espessura, furos: (e.furos || []).length, o: e.origem.map(Math.round), ex: e.eixo_x.map(v => Math.round(v * 1000) / 1000), cont: e.contorno }));")
    # 1. a chapa de base: H, clique no chão, 400;400, espessura 25 e os quatro furos
    tecla("h")
    x, y = tela([-200, -200, 0])
    clicar(x, y)
    mover(*tela([100, 100, 0]))
    digitar("400;400")
    digitar("25")
    for f in ("50;50", "350;50", "50;350", "350;350"):
        digitar(f)
    tecla("Enter"); tecla("Escape"); tecla("Escape")
    c = chapas()
    ok(c and len(c) == 1 and c[0]["esp"] == 25 and c[0]["furos"] == 4, f"H, 400;400, espessura 25 e quatro furos digitados: {c}")
    ch = c[0] if c else None
    # o meio da chapa e o topo dela
    meio_ch = js(f"const e = editor.documento.get('{ch['id']}'), n = [e.eixo_x[1]*e.eixo_y[2]-e.eixo_x[2]*e.eixo_y[1], e.eixo_x[2]*e.eixo_y[0]-e.eixo_x[0]*e.eixo_y[2], e.eixo_x[0]*e.eixo_y[1]-e.eixo_x[1]*e.eixo_y[0]];"
                 "const xs = e.contorno.map(p => p[0]), ys = e.contorno.map(p => p[1]); const u = (Math.min(...xs) + Math.max(...xs)) / 2, v = (Math.min(...ys) + Math.max(...ys)) / 2;"
                 "const z0 = e.centrada === false ? e.espessura : e.espessura / 2;"
                 "return [0, 1, 2].map(i => e.origem[i] + e.eixo_x[i] * u + e.eixo_y[i] * v + n[i] * z0);") if ch else [0, 0, 12.5]
    # 2. o pilar em cima da chapa: B, clique no meio dela, ↑ e 3000
    tecla("b")
    clicar(*tela(meio_ch))
    tecla("ArrowUp")
    digitar("3000")
    tecla("Escape"); tecla("Escape")
    b = js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => ({ id: e.id, i: e.inicio.map(Math.round), f: e.fim.map(Math.round), papel: e.papel, rot: e.rotacao }));")
    ok(b and len(b) == 1 and b[0]["papel"] == "pilar" and abs(b[0]["i"][2] - round(meio_ch[2])) <= 1 and b[0]["f"][2] - b[0]["i"][2] == 3000,
       f"B no meio da chapa, ↑ e 3000: o pilar nasce em cima dela ({round(meio_ch[2])}): {b}")
    pilar = b[0]["id"] if b else None
    # 3. P na face de cima da chapa (fora do pilar): 6 e logo depois 5
    tecla("p")
    # um ponto da face de cima longe dos furos (a 50 da borda) e do pilar
    clicar(*tela([meio_ch[0], meio_ch[1] - 170, meio_ch[2]]))
    digitar("6")
    e1 = chapas()[0]["esp"]
    digitar("5")
    e2 = chapas()[0]["esp"]
    tecla("Escape"); tecla("Escape")
    ok(e1 == 31 and e2 == 30, f"P na face de cima: 6 (25 → 31) e o 5 logo depois corrige (→ 30): {(e1, e2)}")
    # 4. a chapa selecionada, Q no pé do pilar, 45 e logo depois 90
    tecla(" ")
    js(f"editor.selecao.definir(['{ch['id']}']); return 1;")
    tecla("q")
    tecla("ArrowUp")      # o giro em torno da vertical (o plano perpendicular a Z), como no SketchUp
    pe = b[0]["i"] if b else [0, 0, 0]
    clicar(*tela(pe))
    clicar(*tela([pe[0] + 300, pe[1], pe[2]]))
    digitar("45")
    g1 = chapas()[0]["ex"]
    digitar("90")
    g2 = chapas()[0]["ex"]
    tecla("Escape"); tecla("Escape")
    ok(abs(abs(g1[0]) - 0.707) < 0.01 and abs(abs(g1[1]) - 0.707) < 0.01 and abs(g2[0]) < 0.01 and abs(abs(g2[1]) - 1) < 0.01,
       f"Q no pé do pilar: 45° e o 90 logo depois corrige (o X da chapa): {(g1, g2)}")
    # 5. V com Ctrl no pilar: 180°
    tecla("v")
    clicar(*tela([pe[0], pe[1], pe[2] + 1500]), mods=2)
    rot = js(f"return editor.documento.get('{pilar}').rotacao;")
    tecla("Escape")
    ok(rot == 180, f"V com Ctrl no pilar: virado 180°: {rot}")
    # 6. W: a cópia espelhada do pilar e da chapa no plano x = 1000 (dois pontos)
    tecla(" ")
    js(f"editor.selecao.definir(['{pilar}', '{ch['id']}']); return 1;")
    n_antes = js("return editor.documento.entidades.size;")
    tecla("w")
    clicar(*tela([1000, -500, 0]))
    clicar(*tela([1000, 500, 0]))
    n_dep = js("return editor.documento.entidades.size;")
    esp = js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => Math.round(e.inicio[0]));")
    tecla("Escape"); tecla("Escape")
    ok(n_dep == n_antes + 2 and esp and any(abs(v - (2000 - pe[0])) <= 2 for v in esp), f"W com dois pontos: a cópia espelhada do pilar e da chapa do outro lado de x = 1000: {(n_antes, n_dep, esp)}")
    # 7. Ctrl+Z até o modelo vazio
    for _ in range(25):
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
