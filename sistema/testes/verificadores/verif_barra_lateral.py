# -*- coding: utf-8 -*-
"""A barra lateral das ferramentas em janela baixa (15/10/2026, item 4 do briefing do editor 3D), com o mouse de verdade
(CDP): na janela alta ela fica normal; mais baixa, compacta e depois em duas colunas, sempre com todas as ferramentas à
vista; muito baixa, a seta de baixo mostra que há mais e o clique nela rola; de volta à janela alta, normal e sem setas."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_barra_")
PASTA = os.path.join(DADOS, "gf")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Barra", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_barra_")
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
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=gf", limite=60)
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

    # a abertura do editor faz um enquadramento animado próprio, que às vezes termina depois do nosso e o desfaz: espera
    # a câmera assentar, enquadra e confere que ela ficou
    pos_cam = lambda: js("const c = editor.camera.ativa.position; return [c.x, c.y, c.z].map(v => Math.round(v * 1000));")
    for _ in range(5):
        aba.drenar(0.8)
        js("""editor.camera.enquadrar([[-1200, -1200, 0], [1200, 1200, 1500]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
        a_ = pos_cam(); aba.drenar(0.8)
        if pos_cam() == a_: break
    aba.drenar(0.5)
    def estado():
        return js("""const b = document.getElementById('barra-ferramentas'), r = b.getBoundingClientRect();
          const bt = [...b.querySelectorAll('.ferramenta')];
          const fora = bt.filter(x => { const q = x.getBoundingClientRect(); return q.top < r.top - 1 || q.bottom > r.bottom + 1; }).length;
          const vis = (c) => { const s = document.querySelector(c); return !!s && !s.hidden; };
          return { modo: b.dataset.modo, n: bt.length, fora, larg: Math.round(r.width), alt: Math.round(r.height),
                   cima: vis('.barra-seta-cima'), baixo: vis('.barra-seta-baixo') };""")

    def altura(h):
        aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=h, deviceScaleFactor=1, mobile=False)
        aba.drenar(0.6)
        return estado()

    e = altura(1400)
    ok(e and e["modo"] == "normal" and e["fora"] == 0 and not e["baixo"] and e["n"] >= 25, f"janela alta: a barra normal, todas à vista: {e}")
    alturas = {}
    for h in (1000, 800, 650):
        e = altura(h); alturas[h] = e
        ok(e and e["fora"] == 0 and not e["baixo"] and not e["cima"], f"janela de {h} px: todas as ferramentas à vista, sem rolar ({e and e['modo']}): {e}")
    # 500 px (a área com 430): cabe ou mostra a seta — nunca esconde sem avisar
    e = altura(500)
    ok(e and (e["fora"] == 0 or e["baixo"]), f"janela de 500 px: cabe tudo ou a seta de baixo avisa: {e}")
    modos = [alturas[h]["modo"] for h in (1000, 800, 650) if alturas.get(h)]
    ok(any(m.startswith("duas-colunas") for m in modos) and any(m == "compacta" or m == "normal" for m in modos),
       f"compacta primeiro, duas colunas só quando precisa: {modos}")
    # muito baixa: setas
    e = altura(330)
    ok(e and e["fora"] > 0 and e["baixo"] and not e["cima"], f"janela muito baixa: a seta de baixo mostra que há mais: {e}")
    xy = js("const s = document.querySelector('.barra-seta-baixo').getBoundingClientRect(); return [Math.round(s.left + s.width / 2), Math.round(s.top + s.height / 2)];")
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=xy[0], y=xy[1], button="left", clickCount=1, buttons=1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=xy[0], y=xy[1], button="left", clickCount=1, buttons=0)
    aba.drenar(1.0)
    e2 = estado()
    rol = js("return document.getElementById('barra-ferramentas').scrollTop;")
    ok(rol and rol > 0 and e2["cima"], f"o clique na seta rola a barra e a seta de cima aparece: scrollTop={rol}, {e2}")
    # volta a crescer: a barra volta ao normal e as setas somem
    e = altura(1400)
    ok(e and e["modo"] == "normal" and not e["cima"] and not e["baixo"], f"de volta à janela alta: normal, sem setas: {e}")
    # a ferramenta continua clicável em duas colunas
    altura(650)
    xy = js("const b = document.querySelector('#barra-ferramentas [data-id=\"dividir\"]').getBoundingClientRect(); return [Math.round(b.left + b.width / 2), Math.round(b.top + b.height / 2)];")
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=xy[0], y=xy[1], button="left", clickCount=1, buttons=1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=xy[0], y=xy[1], button="left", clickCount=1, buttons=0)
    aba.drenar(0.3)
    ok(js("return editor.idAtiva;") == "dividir", f"o clique no Dividir (a última da barra) abre a ferramenta: {js('return editor.idAtiva;')}")
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
