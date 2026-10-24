# -*- coding: utf-8 -*-
"""As cotas novas do CAD 2D (usuário, 23/10: "pode seguir" — a leva das cotas da lista das ferramentas que faltam),
com o teclado e o mouse de verdade (CDP):
  A. Cota angular (D N): nas duas linhas a 45° → "45°"; o arco no outro setor → "315°";
  B. Raio (D R) e Diâmetro (D I) no furo Ø100 → "R50" e "Ø100"; a alça do número leva a seta pelo círculo;
  C. Ordenada (D O): O e a origem na borda da chapa; os furos a 100 e 300 dela;
  D. Linha de base (D B): da cota de 200, as de 500 e 800 saem do mesmo ponto, cada uma numa linha mais para fora;
  E. Cota rápida (D Q): a janela na chapa com 3 furos → a cadeia 100 | 200 | 200 | 100; com B, a linha de base 100,
     300, 500, 600; com O, as ordenadas;
  F. Propriedades da cota angular; Ctrl+Z desfaz."""
import json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha, Polilinha, Circulo, Cota

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cotasnovas_")
PASTA = os.path.join(DADOS, "obra-cotas")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra cotas", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-23T00:00:00", "alterado": "2026-10-23T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Cotas", escala=10.0)
d.add(Linha(id="l1", a=(0, 0), b=(1000, 0))); d.add(Linha(id="l2", a=(0, 0), b=(707.107, 707.107)))
d.add(Circulo(id="furo", centro=(2000, 0), raio=50))
d.add(Polilinha(id="chapa", vertices=[(3000, 0), (3600, 0), (3600, 400), (3000, 400)], fechada=True))
for i, x in enumerate((3100, 3300, 3500)):
    d.add(Circulo(id="f%d" % i, centro=(x, 100), raio=11))
d.add(Cota(id="cb", modo="h", p1=(4000, 0), p2=(4200, 0), deslocamento=10.0))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "cotas.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cotasnovas_")
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
        x, y = tela(p); ev("mouseMoved", x, y); aba.drenar(0.12)

    def clique(p):
        x, y = tela(p)
        ev("mouseMoved", x, y); ev("mousePressed", x, y, "left", 1); ev("mouseReleased", x, y, "left", 0)
        aba.drenar(0.25)

    def arrastar(a, b):
        x0, y0 = tela(a); x1, y1 = tela(b)
        ev("mouseMoved", x0, y0); ev("mousePressed", x0, y0, "left", 1)
        for t in (0.3, 0.6, 1.0):
            ev("mouseMoved", x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, "left", 1)
        ev("mouseReleased", x1, y1, "left", 0); aba.drenar(0.3)

    COD = {"Enter": (13, "Enter"), "Escape": (27, "Escape")}

    def tecla(k, mods=0):
        code, nome = COD.get(k, (ord(k.upper()) if len(k) == 1 else 0, ("Key" + k.upper()) if k.isalpha() and len(k) == 1 else ("Digit" + k if k.isdigit() else k)))
        texto = k if len(k) == 1 and not (mods & 2) else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=nome, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=nome, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.12)

    def comando(letras):
        """o comando digitado na linha de comando e o espaço (24/10, como no AutoCAD)"""
        for k in letras:
            aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), text=k, unmodifiedText=k)
            aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()))
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=" ", code="Space", windowsVirtualKeyCode=32, text=" ", unmodifiedText=" ")
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=" ", code="Space", windowsVirtualKeyCode=32)
        aba.drenar(0.2)

    def duas(k1, k2):
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), text=k, unmodifiedText=k)
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()))
        # a linha de comando (24/10): as letras vão para ela e o espaço executa, como no AutoCAD
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=" ", code="Space", windowsVirtualKeyCode=32, text=" ", unmodifiedText=" ")
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=" ", code="Space", windowsVirtualKeyCode=32)
        aba.drenar(0.2)

    def esc():
        tecla("Escape"); tecla("Escape")

    ferr = lambda: js("return c.ferramenta.constructor.id;")
    ids = lambda: set(js("return [...c.doc.entidades.keys()];"))
    novas = lambda antes: [js(f"return c.doc.get('{i}');") for i in ids() - antes]
    medida = lambda e: js("return window.__medida(%s);" % json.dumps(e))

    def vista(caixa):
        esc(); js("c.ativarFerramenta('selecionar'); c.selecionar([]); c.tela.enquadrar(%s, 0.05); return 1;" % json.dumps(caixa)); aba.drenar(0.3)

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-cotas&desenho=cotas", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 8", 40), "o CAD abriu o desenho")
    aba.console.clear()
    aba.avaliar("import('/cad/nucleo/cota_especial.js').then(m => { window.__medida = m.medidaDaCotaEspecial; })"); aba.drenar(0.5)

    # ------------------------------------------------------------------ A. angular
    vista([[-200, -300], [1200, 900]])
    duas("d", "n")
    ok(ferr() == "cota_angular", f"A. D N abre a Cota angular ({ferr()})")
    antes = ids()
    clique([600, 0]); clique([424, 424]); clique([450, 180])
    a = [e for e in novas(antes) if e and e["tipo"] == "cota_especial"]
    ok(len(a) == 1 and a[0]["modo"] == "angular" and medida(a[0]) == "45°", f"A. entre as duas linhas: {a and medida(a[0])}")
    antes = ids()
    clique([600, 0]); clique([424, 424]); clique([-150, -150])
    a2 = [e for e in novas(antes) if e and e["tipo"] == "cota_especial"]
    ok(len(a2) == 1 and medida(a2[0]) == "315°", f"A. o arco no outro setor: {a2 and medida(a2[0])}")
    esc()

    # ------------------------------------------------------------------ B. raio e diâmetro
    vista([[1700, -300], [2300, 300]])
    duas("d", "r")
    ok(ferr() == "cota_raio", f"B. D R abre a Cota de raio ({ferr()})")
    antes = ids()
    clique([2050, 0]); clique([2150, 120])
    r = [e for e in novas(antes) if e and e["tipo"] == "cota_especial"]
    ok(len(r) == 1 and r[0]["modo"] == "raio" and medida(r[0]) == "R50", f"B. o raio do furo: {r and medida(r[0])}")
    comando("ddi")          # 24/10: o DI é o DIST do AutoCAD; a cota de diâmetro é DDI
    antes = ids()
    clique([1950, 0]); clique([2000, 20])
    di = [e for e in novas(antes) if e and e["tipo"] == "cota_especial"]
    ok(len(di) == 1 and di[0]["modo"] == "diametro" and medida(di[0]) == "Ø100", f"B. o diâmetro: {di and medida(di[0])}")
    esc()
    # a alça do número do raio: a seta corre pelo círculo
    rid = r[0]["id"] if r else None
    js(f"c.selecionar(['{rid}']); return 1;"); aba.drenar(0.2)
    clique([2150, 120]); mover([1850, -150]); clique([1850, -150])
    rr = js(f"return c.doc.get('{rid}');")
    ok(rr and abs(math.dist(rr["p1"], [2000, 0]) - 50) < 0.01 and rr["p1"][0] < 2000 and rr["p1"][1] < 0,
       f"B. a alça leva o número e a seta vai para o círculo do outro lado: {rr and rr['p1']}")
    esc()

    # ------------------------------------------------------------------ C. ordenada
    vista([[2900, -200], [3700, 900]])
    duas("d", "o")
    ok(ferr() == "cota_ordenada", f"C. D O abre a Cota ordenada ({ferr()})")
    tecla("o"); clique([3000, 0])
    ok(js("return c.doc.metadados.origem_ordenada;") == [3000, 0], f"C. a origem na borda: {js('return c.doc.metadados.origem_ordenada;')}")
    antes = ids()
    clique([3100, 100]); clique([3100, 700]); clique([3300, 100]); clique([3300, 700])
    o = sorted((e for e in novas(antes) if e and e["tipo"] == "cota_especial"), key=lambda e: e["p1"][0])
    ok([medida(e) for e in o] == ["100", "300"] and all(e["eixo"] == "x" for e in o), f"C. os furos a 100 e 300 da borda: {[medida(e) for e in o]}")
    esc()

    # ------------------------------------------------------------------ D. linha de base
    vista([[3900, -300], [5000, 500]])
    js("c.selecionar(['cb']); return 1;")
    duas("d", "b")
    ok(ferr() == "cota_base", f"D. D B abre a Cota por linha de base ({ferr()})")
    antes = ids()
    clique([4500, 0]); clique([4800, 0])
    bs = sorted((e for e in novas(antes) if e and e["tipo"] == "cota"), key=lambda e: e["p2"][0])
    linha_y = lambda e: e["p1"][1] + e["deslocamento"] * 10
    ok(len(bs) == 2 and all(e["p1"] == [4000, 0] for e in bs), f"D. as duas saem do mesmo ponto: {[e['p1'] for e in bs]}")
    ok(len(bs) == 2 and abs(linha_y(bs[0]) - (100 + 70)) < 0.01 and abs(linha_y(bs[1]) - (100 + 140)) < 0.01,
       f"D. cada uma 7 mm de papel mais para fora (y da linha: {[round(linha_y(e), 2) for e in bs]})")
    tecla("z", 2)
    ok(len(set(ids()) - antes) == 1, "D. Ctrl+Z tira a última")
    esc()

    # ------------------------------------------------------------------ E. cota rápida
    vista([[2900, -300], [3700, 900]])
    duas("d", "q")
    ok(ferr() == "cota_rapida", f"E. D Q abre a Cota rápida ({ferr()})")
    arrastar([2950, -50], [3650, 450])
    ok(len(js("return [...c.tela.selecao];") or []) == 4, f"E. a janela pega a chapa e os 3 furos ({len(js('return [...c.tela.selecao];') or [])})")
    antes = ids()
    clique([3300, 700])
    cad = sorted((e for e in novas(antes) if e and e["tipo"] == "cota"), key=lambda e: e["p1"][0])
    vals = [round(abs(e["p2"][0] - e["p1"][0])) for e in cad]
    ok(vals == [100, 200, 200, 100], f"E. em cadeia: {vals}")
    ok(all(abs(e["p1"][1] + e["deslocamento"] * 10 - 700) < 0.5 for e in cad), "E. todas na linha do clique")
    js("c.selecionar(['chapa', 'f0', 'f1', 'f2']); return 1;")
    duas("d", "q"); tecla("b")
    antes = ids()
    clique([3300, -200])
    base = sorted((e for e in novas(antes) if e and e["tipo"] == "cota"), key=lambda e: e["p2"][0])
    vals = [round(abs(e["p2"][0] - e["p1"][0])) for e in base]
    ok(vals == [100, 300, 500, 600] and all(e["p1"][0] == 3000 for e in base), f"E. com B, da linha de base: {vals}")
    js("c.selecionar(['chapa', 'f0', 'f1', 'f2']); return 1;")
    duas("d", "q"); tecla("o")
    antes = ids()
    clique([3300, 750])
    ords = [e for e in novas(antes) if e and e["tipo"] == "cota_especial"]
    ok(sorted(medida(e) for e in ords) == sorted(["100", "300", "500", "600"]), f"E. com O, as ordenadas: {sorted(medida(e) for e in ords)}")
    esc()

    # ------------------------------------------------------------------ F. propriedades
    vista([[-200, -300], [1200, 900]])
    js("c.selecionar(['%s']); return 1;" % a[0]["id"]); aba.drenar(0.3)
    txt = js("return [...document.querySelectorAll('.props')].map(p => p.textContent).join(' ');") or ""
    ok("angular: 45°" in txt, f"F. Propriedades: a cota angular de 45° ({txt[txt.find('Cota'):][:40] if 'Cota' in txt else txt[:60]})")
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
