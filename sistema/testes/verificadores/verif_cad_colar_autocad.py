# -*- coding: utf-8 -*-
"""Colar do AutoCAD no CAD 2D (usuário, 23/10: "criar a funcionalidade de copiar elementos de dentro do autocad e colar
na nossa área 2D"), com o teclado e o mouse de verdade (CDP). O servidor de teste lê o copiado de
METALICA_COLAR_TESTE (dados_cad/amostra_autocad.dxf: a peça na camada "PECA CIANO" em x ≈ 50 m) — a área de
transferência de quem roda o teste não é tocada; a leitura dela e a conversão do DWG pelo AutoCAD estão em
test_colar_do_autocad.py.
  A. Ctrl+V: os 4 objetos presos ao cursor pelo canto de baixo à esquerda, a camada nova com a cor do AutoCAD;
  B. o clique solta ali: tudo andou o mesmo tanto, selecionado; Ctrl+Z desfaz num passo só;
  C. Ctrl+V e Enter: nas coordenadas do AutoCAD; Ctrl+V e "100;200": o canto em (100, 200); Esc cancela sem colar;
  D. o item Colar do AutoCAD no menu."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_colar_")
PASTA = os.path.join(DADOS, "obra-colar")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra colar", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-23T00:00:00", "alterado": "2026-10-23T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Destino", escala=10.0)
d.add(Linha(id="ref", a=(0, 0), b=(3000, 0)))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "destino.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
AMOSTRA = os.path.join(BASE, "testes", "dados_cad", "amostra_autocad.dxf")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, METALICA_COLAR_TESTE=AMOSTRA))
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_colar_")
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

    def mover(p):
        x, y = tela(p); aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y); aba.drenar(0.15)

    def clique(p):
        x, y = tela(p)
        for t, b, bs in (("mouseMoved", "none", 0), ("mousePressed", "left", 1), ("mouseReleased", "left", 0)):
            aba.cmd("Input.dispatchMouseEvent", type=t, x=x, y=y, button=b, buttons=bs, clickCount=1)
        aba.drenar(0.3)

    TECLAS = {"Enter": 13, "Escape": 27}

    def tecla(k, mods=0):
        code = TECLAS.get(k) or ord(k.upper())
        texto = k if len(k) == 1 and not (mods & 2) else ""
        nome = ("Key" + k.upper()) if len(k) == 1 and k.isalpha() else ("Digit" + k if k.isdigit() else k)
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=nome, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=nome, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.15)

    coladas = lambda: js("return [...c.doc.entidades.values()].filter(e => e.camada === 'PECA CIANO').map(e => JSON.parse(JSON.stringify(e)));") or []
    ferr = lambda: js("return c.ferramenta.constructor.id;")

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-colar&desenho=destino", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 1", 40), "o CAD abriu o desenho")
    aba.console.clear()
    js("c.tela.enquadrar([[-500, -500], [3500, 1500]]); return 1;"); aba.drenar(0.3)
    mover([1000, 500])

    # A. Ctrl+V
    tecla("v", 2)
    ok(esperar("c.ferramenta.constructor.id === 'colar_autocad'", 30), f"A. Ctrl+V: os objetos presos ao cursor ({ferr()})")
    previa = js("return (c.tela.previa || []).length;")
    ok(previa == 4, f"A. a prévia com os 4 objetos copiados ({previa})")
    cam = js("return c.doc.camadas.get('PECA CIANO');")
    ok(cam and cam["cor"].lower() == "#17a2b8", f"A. a camada do AutoCAD com a cor dela ({cam})")
    # B. o clique solta: o canto de baixo à esquerda (50000, 20000) no ponto clicado
    clique([1000, 500])
    cs = coladas()
    linha = next((e for e in cs if e["tipo"] == "linha"), None)
    ok(len(cs) == 4 and linha and abs(linha["a"][0] - 1000) < 0.5 and abs(linha["a"][1] - 500) < 0.5 and abs(linha["b"][0] - 2200) < 0.5,
       f"B. colado com o canto no clique: a linha de {linha and linha['a']} a {linha and linha['b']}")
    ok(ferr() == "selecionar" and len(js("return [...c.tela.selecao];") or []) == 4, "B. volta ao Selecionar com os colados selecionados")
    tecla("z", 2)
    ok(len(coladas()) == 0, "B. Ctrl+Z desfaz a colagem inteira")

    # C. Enter: nas coordenadas do AutoCAD; "100;200": o canto ali; Esc cancela
    tecla("v", 2); esperar("c.ferramenta.constructor.id === 'colar_autocad'", 30)
    tecla("Enter")
    linha = next((e for e in coladas() if e["tipo"] == "linha"), None)
    ok(linha and abs(linha["a"][0] - 50000) < 0.5 and abs(linha["a"][1] - 20000) < 0.5, f"C. Enter: nas coordenadas do AutoCAD ({linha and linha['a']})")
    tecla("z", 2)
    tecla("v", 2); esperar("c.ferramenta.constructor.id === 'colar_autocad'", 30)
    for ch in "100;200": tecla(ch)
    tecla("Enter")
    linha = next((e for e in coladas() if e["tipo"] == "linha"), None)
    ok(linha and abs(linha["a"][0] - 100) < 0.5 and abs(linha["a"][1] - 200) < 0.5, f"C. digitado 100;200: o canto ali ({linha and linha['a']})")
    tecla("z", 2)
    tecla("v", 2); esperar("c.ferramenta.constructor.id === 'colar_autocad'", 30)
    tecla("Escape")
    ok(len(coladas()) == 0 and ferr() == "selecionar", "C. Esc cancela sem colar")

    # D. o menu
    ok(js("return !!document.querySelector('button[data-acao=\"colar-autocad\"]');"), "D. o item Colar do AutoCAD no menu")
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
