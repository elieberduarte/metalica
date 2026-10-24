# -*- coding: utf-8 -*-
"""Os snaps e os rastreamentos do AutoCAD no CAD 2D (24/10, a lista das ferramentas que faltam: "os snaps do AutoCAD —
tangente, extensão, paralelo, FROM, rastreamento polar, '@dx,dy' na Linha"), com o mouse e o teclado de verdade:
  A. tangente: a Linha saindo de um ponto fora do círculo pega o ponto de tangência;
  B. extensão: o cursor parado na ponta da linha a adquire (+); adiante dela, o cursor gruda na continuação (guia);
  C. rastreamento: a guia vertical do ponto adquirido; o cruzamento de duas guias dá o ponto exato;
     com uma linha embaixo do cursor vale o "sobre" (a guia não tira o cursor da linha);
  D. polar (45°): do primeiro ponto da Linha, o cursor gruda a 315°; F10 desliga;
  E. paralelo: o cursor parado sobre a diagonal a adquire; a Linha seguinte gruda na paralela a ela;
  F. FROM: a base no clique (a ponta da linha) e "@200,100" dão o primeiro ponto; "@300<0" o segundo;
  G. "@500,0" e "@0;-100" na Linha: os trechos relativos ao último ponto;
  H. na Selecionar nada é adquirido; Esc esquece os pontos adquiridos."""
import json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from linha_comando_teste import comando
from nucleo2d.desenho import Desenho, Linha, Circulo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_snaps_")
PASTA = os.path.join(DADOS, "obra-snaps")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra snaps", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-24T00:00:00", "alterado": "2026-10-24T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Snaps", escala=1.0)
d.add(Linha(id="h", a=(0, 0), b=(1000, 0)))
d.add(Linha(id="diag", a=(0, 500), b=(400, 800)))
d.add(Circulo(id="c", centro=(2000, 0), raio=200))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "snaps.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_snaps_")
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
            aba.drenar(0.2)
        return False

    def tela(p):
        return js("const r = c.el.canvas.getBoundingClientRect(); const t = c.tela.paraTela(%s); return [r.left + t[0], r.top + t[1]];" % json.dumps(p))

    def ev(tipo, x, y, botao="none", botoes=0):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=1)

    def mover(p, pausa=0.15):
        x, y = tela(p); ev("mouseMoved", x, y); aba.drenar(pausa)

    def clique(p):
        x, y = tela(p)
        ev("mouseMoved", x, y); ev("mousePressed", x, y, "left", 1); ev("mouseReleased", x, y, "left", 0)
        aba.drenar(0.25)

    def tecla(k, mods=0):
        cod = {"Enter": 13, "Escape": 27, "F10": 121, "F11": 122}.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = "\r" if k == "Enter" else (k if len(k) == 1 and not mods else "")
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=k if k.startswith("F") and len(k) > 1 else "", windowsVirtualKeyCode=cod, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=cod, modifiers=mods)
        aba.drenar(0.1)

    def digitar(t):
        """o primeiro caractere vai do desenho para a linha de comando; o resto entra nela; Enter"""
        tecla(t[0])
        if len(t) > 1: aba.cmd("Input.insertText", text=t[1:])
        tecla("Enter"); aba.drenar(0.2)

    def esc():
        tecla("Escape"); tecla("Escape")

    snap = lambda: js("return c.tela.snap ? { tipo: c.tela.snap.tipo, ponto: c.tela.snap.ponto, rotulo: c.tela.snap.rotulo, guias: (c.tela.snap.guias || []).length } : null;")
    adquiridos = lambda: js("return c.snap.adquiridos.length;")
    ids = lambda: set(js("return [...c.doc.entidades.keys()];"))
    linhas_novas = lambda antes: [e for e in (js(f"return c.doc.get('{i}');") for i in ids() - antes) if e and e["tipo"] == "linha"]
    perto = lambda a, b, tol=0.05: a is not None and b is not None and abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-snaps&desenho=snaps", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 3", 40), "o CAD abriu o desenho")
    js("c.tela.enquadrar([[-300, -900], [2500, 1100]], 0.02); return 1;"); aba.drenar(0.3)
    mm_px = js("return c.tela.mmPorPixel;")
    aba.console.clear()

    # ------------------------------------------------------------------ H. na Selecionar nada é adquirido
    mover([1000, 0], 0.8)
    ok(adquiridos() == 0, "H. na Selecionar a pausa na ponta não adquire")

    # ------------------------------------------------------------------ A. tangente
    comando(aba, "l")
    clique([2000, 600])
    al = math.acos(200 / 600)
    q1 = (2000 + 200 * math.cos(math.pi / 2 + al), 200 * math.sin(math.pi / 2 + al))
    mover([q1[0] + 2 * mm_px, q1[1] + 1 * mm_px])
    s = snap()
    ok(s and s["tipo"] == "tangente" and perto(s["ponto"], q1), f"A. tangente ao círculo ({s and s['tipo']}, {s and s['ponto']}, esperado {q1})")
    antes = ids(); clique([q1[0] + 2 * mm_px, q1[1] + 1 * mm_px])
    ls = linhas_novas(antes)
    ok(ls and perto(ls[0]["b"], q1), f"A. a linha termina no ponto de tangência ({ls and ls[0]['b']})")
    esc()

    # ------------------------------------------------------------------ B. extensão
    comando(aba, "l")
    mover([1000, 0], 0.8)
    ok(adquiridos() == 1, f"B. a pausa na ponta da linha a adquire ({adquiridos()})")
    mover([1300, 4 * mm_px])
    s = snap()
    ok(s and s["tipo"] == "extensao" and perto(s["ponto"], [1300, 0], 0.01) and s["guias"] >= 1, f"B. adiante da ponta, a extensão ({s})")

    # ------------------------------------------------------------------ C. rastreamento
    mover([1000 + 3 * mm_px, -300])
    s = snap()
    ok(s and s["tipo"] == "rastreamento" and perto(s["ponto"], [1000, -300], 0.01) and "vertical" in s["rotulo"], f"C. a guia vertical do ponto adquirido ({s})")
    mover([400, 800], 0.8)                                 # a ponta da diagonal: o 2º ponto adquirido
    mover([1000 + 3 * mm_px, 800 - 3 * mm_px])
    s = snap()
    ok(s and s["tipo"] == "rastreamento" and perto(s["ponto"], [1000, 800], 0.01) and "×" in s["rotulo"], f"C. o cruzamento das duas guias ({s})")
    mover([700, 2 * mm_px])
    s = snap()
    ok(s and s["tipo"] == "sobre", f"C. com a linha embaixo do cursor vale o \"sobre\" ({s and s['tipo']})")
    esc()
    ok(adquiridos() == 0, "H. Esc esquece os pontos adquiridos")

    # ------------------------------------------------------------------ D. polar
    comando(aba, "l")
    clique([200, -300])
    alvo = (200 + 300, -300 - 300)
    mover([alvo[0] + 3 * mm_px, alvo[1] + 3 * mm_px])
    s = snap()
    ok(s and s["tipo"] == "polar" and "315" in s["rotulo"], f"D. polar 315° ({s})")
    antes = ids(); clique([alvo[0] + 3 * mm_px, alvo[1] + 3 * mm_px])
    ls = linhas_novas(antes)
    ang = ls and round(math.degrees(math.atan2(ls[0]["b"][1] - ls[0]["a"][1], ls[0]["b"][0] - ls[0]["a"][0])) % 360, 4)
    ok(ls and ang == 315.0, f"D. a linha sai a 315° ({ang})")
    tecla("F10")
    mover([alvo[0] + 300 + 3 * mm_px, alvo[1] + 300 + 3 * mm_px])
    s = snap()
    ok(js("return c.snap.ativos.polar;") is False and not (s and s["tipo"] == "polar"), f"D. F10 desliga o polar ({s})")
    tecla("F10")
    esc()

    # ------------------------------------------------------------------ E. paralelo
    comando(aba, "l")
    mover([100, 575], 0.8)                                  # sobre a diagonal (fora das pontas e do meio)
    clique([700, -500])
    u = (0.8, 0.6)
    alvo = (700 + u[0] * 500 - u[1] * 3 * mm_px, -500 + u[1] * 500 + u[0] * 3 * mm_px)
    mover(alvo)
    s = snap()
    ok(s and s["tipo"] == "paralelo", f"E. a paralela à diagonal a partir do ponto ({s})")
    antes = ids(); clique(alvo)
    ls = linhas_novas(antes)
    dx, dy = (ls[0]["b"][0] - ls[0]["a"][0], ls[0]["b"][1] - ls[0]["a"][1]) if ls else (0, 1)
    ok(ls and abs(dx * u[1] - dy * u[0]) < 1e-6 * math.hypot(dx, dy), f"E. a linha sai paralela ({ls and (round(dx, 3), round(dy, 3))})")
    esc()

    # ------------------------------------------------------------------ F. FROM
    comando(aba, "l")
    comando(aba, "from", "Enter")
    ok(js("return c.ferramenta.constructor.id;") == "linha" and js("return !!c._from;"), "F. FROM no meio da Linha, sem trocar a ferramenta")
    clique([1000, 0])
    antes = ids()
    digitar("@200,100")
    digitar("@300<0")
    ls = linhas_novas(antes)
    ok(ls and perto(ls[0]["a"], [1200, 100], 1e-6) and perto(ls[0]["b"], [1500, 100], 1e-6), f"F. base na ponta + @200,100 e @300<0 ({ls and (ls[0]['a'], ls[0]['b'])})")
    esc()

    # ------------------------------------------------------------------ G. "@dx,dy" na Linha
    comando(aba, "l")
    clique([100, 300])
    antes = ids()
    digitar("@500,0")
    digitar("@0;-100")
    ls = sorted(([tuple(e["a"]), tuple(e["b"])] for e in linhas_novas(antes)), key=lambda l: l[0])
    rel = lambda l: (l[1][0] - l[0][0], l[1][1] - l[0][1])
    ok(len(ls) == 2 and perto(ls[0][0], [100, 300], 0.05) and perto(rel(ls[0]), [500, 0], 1e-6) and perto(rel(ls[1]), [0, -100], 1e-6),
       f"G. @500,0 e @0;-100: os trechos relativos ({ls})")
    esc()

    erros = [x for x in aba.console if x[0] in ("error", "excecao")]
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
