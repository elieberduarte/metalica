# -*- coding: utf-8 -*-
"""Matriz e grade de furos do CAD 2D (usuário, 23/10: "Sim" — a leva da matriz na lista das ferramentas que faltam),
com o teclado e o mouse de verdade (CDP):
  A. Matriz retangular (A R): "4x3" e o cursor dá o espaçamento → 11 cópias, a última a (3·200, 2·100);
  B. "3x1" e "150;0" digitados: 2 cópias a 150 e 300;
  C. polar (P): o centro e "6": 5 cópias girando 60° em volta; R: sem girar;
  D. por caminho (C): a linha de 1000 e "5": as cópias a cada 250, de ponta a ponta;
  E. Grade de furos (G F): "M16" → Ø17,5 (a folga de 1,5); "2x3" e "60;50": 6 furos na camada FURO a partir do clique;
     C: a grade centrada no clique;
  F. Ctrl+Z desfaz a matriz inteira."""
import json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha, Polilinha, Circulo

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_matriz_")
PASTA = os.path.join(DADOS, "obra-matriz")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra matriz", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-23T00:00:00", "alterado": "2026-10-23T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Matriz", escala=10.0)
d.add(Polilinha(id="r", vertices=[(0, 0), (100, 0), (100, 50), (0, 50)], fechada=True))
d.add(Circulo(id="pc", centro=(2100, 0), raio=20))
d.add(Linha(id="cam", a=(0, 1000), b=(1000, 1000)))
d.add(Polilinha(id="r2", vertices=[(-10, 1490), (10, 1490), (10, 1510), (-10, 1510)], fechada=True))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "matriz.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_matriz_")
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

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ const c = window.cad; {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.3)
        return False

    def tela(p):
        return js("const r = c.el.canvas.getBoundingClientRect(); const t = c.tela.paraTela(%s); return [r.left + t[0], r.top + t[1]];" % json.dumps(p))

    def ev(tipo, x, y, botao="none", botoes=0):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=1)

    def mover(p):
        x, y = tela(p); ev("mouseMoved", x, y); aba.drenar(0.15)

    def clique(p):
        x, y = tela(p)
        ev("mouseMoved", x, y); ev("mousePressed", x, y, "left", 1); ev("mouseReleased", x, y, "left", 0)
        aba.drenar(0.25)

    COD = {"Enter": (13, "Enter"), "Escape": (27, "Escape"), ";": (186, "Semicolon"), "/": (191, "Slash")}

    def tecla(k, mods=0):
        code, nome = COD.get(k, (ord(k.upper()) if len(k) == 1 else 0, ("Key" + k.upper()) if k.isalpha() and len(k) == 1 else ("Digit" + k if k.isdigit() else k)))
        texto = k if len(k) == 1 and not (mods & 2) else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=nome, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=nome, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.1)

    def duas(k1, k2):
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), text=k, unmodifiedText=k)
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()))
        aba.drenar(0.2)

    def digitar(t):
        for ch in t: tecla(ch)
        tecla("Enter"); aba.drenar(0.2)

    def esc():
        tecla("Escape"); tecla("Escape")

    ferr = lambda: js("return c.ferramenta.constructor.id;")
    ids = lambda: set(js("return [...c.doc.entidades.keys()];"))
    novas = lambda antes: [js(f"return c.doc.get('{i}');") for i in ids() - antes]
    canto = lambda e: [min(v[0] for v in e["vertices"]), min(v[1] for v in e["vertices"])]

    def vista(caixa):
        esc(); js("c.ativarFerramenta('selecionar'); c.selecionar([]); c.tela.enquadrar(%s, 0.05); return 1;" % json.dumps(caixa)); aba.drenar(0.3)

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-matriz&desenho=matriz", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 4", 40), "o CAD abriu o desenho")
    aba.console.clear()

    # ------------------------------------------------------------------ A. retangular pelo cursor
    vista([[-100, -100], [1000, 500]])
    js("c.selecionar(['r']); return 1;")
    duas("a", "r")
    ok(ferr() == "matriz", f"A. A R abre a Matriz ({ferr()})")
    digitar("4x3")
    mover([200, 100])
    ok(js("return (c.tela.previa || []).length;") == 11, f"A. a prévia com as 11 cópias ({js('return (c.tela.previa || []).length;')})")
    antes = ids()
    clique([200, 100])
    cs = [e for e in novas(antes) if e and e["tipo"] == "polilinha"]
    cantos = sorted(tuple(round(v) for v in canto(e)) for e in cs)
    ok(len(cs) == 11 and (600, 200) in cantos and (200, 0) in cantos, f"A. 11 cópias, a última em (600, 200): {cantos[-1] if cantos else None}")
    grupos = {(e.get("atributos") or {}).get("grupo_copia") for e in cs}
    ok(len(grupos) == 11, f"A. cada cópia é uma peça ({len(grupos)} grupos)")
    tecla("z", 2)
    ok(not (ids() - antes), "F. Ctrl+Z desfaz a matriz inteira")

    # ------------------------------------------------------------------ B. retangular digitada
    js("c.selecionar(['r']); return 1;")
    duas("a", "r"); digitar("3x1"); antes = ids(); digitar("150;0")
    cs = sorted(canto(e)[0] for e in novas(antes) if e and e["tipo"] == "polilinha")
    ok([round(x) for x in cs] == [150, 300], f"B. \"3x1\" e \"150;0\": 2 cópias a 150 e 300 ({cs})")
    esc()

    # ------------------------------------------------------------------ C. polar
    vista([[1800, -300], [2400, 300]])
    js("c.selecionar(['pc']); return 1;")
    duas("a", "r"); tecla("p")
    clique([2000, 0])
    digitar("6")
    antes = ids(); tecla("Enter"); aba.drenar(0.2)
    cs = [e for e in novas(antes) if e and e["tipo"] == "circulo"]
    angs = sorted(round(math.degrees(math.atan2(e["centro"][1], e["centro"][0] - 2000))) % 360 for e in cs)
    ok(len(cs) == 5 and angs == [60, 120, 180, 240, 300] and all(abs(math.dist(e["centro"], [2000, 0]) - 100) < 0.01 for e in cs),
       f"C. 5 cópias a 60° em volta do centro: {angs}")
    esc()

    # ------------------------------------------------------------------ D. por caminho
    vista([[-100, 900], [1100, 1600]])
    js("c.selecionar(['r2']); return 1;")
    duas("a", "r"); tecla("c")
    clique([500, 1000])
    digitar("5")
    antes = ids(); tecla("Enter"); aba.drenar(0.2)
    cs = [e for e in novas(antes) if e and e["tipo"] == "polilinha"]
    meios = sorted(round(sum(v[0] for v in e["vertices"]) / 4) for e in cs)
    ok(meios == [0, 250, 500, 750, 1000] and all(abs(sum(v[1] for v in e["vertices"]) / 4 - 1000) < 1e-6 for e in cs),
       f"D. 5 cópias ao longo da linha: {meios}")
    esc()

    # ------------------------------------------------------------------ E. grade de furos
    vista([[2900, -200], [3700, 300]])
    duas("g", "f")
    ok(ferr() == "grade_furos", f"E. G F abre a Grade de furos ({ferr()})")
    tecla("m"); digitar("16")
    digitar("2x3"); digitar("60;50")
    antes = ids()
    clique([3000, 0])
    fs = [e for e in novas(antes) if e and e["tipo"] == "circulo"]
    xs = sorted({round(e["centro"][0]) for e in fs}); ys = sorted({round(e["centro"][1]) for e in fs})
    ok(len(fs) == 6 and all(e["camada"] == "FURO" and abs(e["raio"] - 8.75) < 1e-9 for e in fs) and xs == [3000, 3060, 3120] and ys == [0, 50],
       f"E. M16 → Ø17,5; 2 × 3 a cada 60 × 50 a partir do clique ({len(fs)} furos, x {xs}, y {ys})")
    tecla("c")
    antes = ids()
    clique([3500, 0])
    fs = [e for e in novas(antes) if e and e["tipo"] == "circulo"]
    cx = sum(e["centro"][0] for e in fs) / max(1, len(fs)); cy = sum(e["centro"][1] for e in fs) / max(1, len(fs))
    ok(len(fs) == 6 and abs(cx - 3500) < 0.01 and abs(cy) < 0.01, f"E. C: a grade centrada no clique ({cx:.1f}; {cy:.1f})")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
