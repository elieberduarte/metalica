# -*- coding: utf-8 -*-
"""O guia rápido das ferramentas (15/10/2026, pedido do usuário), com o teclado e o mouse de verdade (CDP): F1 no 3D abre o
guia com todas as ferramentas registradas (atalho, como usar, as que estão fora da barra lateral), os comandos de modelar
pela seleção e as teclas gerais; a busca filtra; o clique numa ferramenta a abre; Esc fecha; e o menu ? da barra única
(a tela dividida) abre o mesmo guia no 3D."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_guia_")
PASTA = os.path.join(DADOS, "gf")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Guia", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_guia_")
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
    aberto = lambda: js("return !!document.getElementById('guia-ferramentas');")
    tecla("F1")
    g = js("""const g = document.getElementById('guia-ferramentas'); if (!g) return null;
      const linhas = [...g.querySelectorAll('.guia-linha')];
      return { n: linhas.filter(l => l.dataset.id).length, total: editor.ferramentas.size, cmds: linhas.filter(l => !l.dataset.id).length,
               fora: [...g.querySelectorAll('.guia-fora')].length, teclas: g.querySelectorAll('.guia-teclas kbd').length,
               semComo: linhas.filter(l => l.dataset.id && !l.querySelector('.guia-como').textContent.trim()).map(l => l.dataset.id) };""")
    ok(g and g["n"] == g["total"] and g["total"] >= 25 and not g["semComo"], f"F1 abre o guia com todas as ferramentas registradas, cada uma com o como usar: {g}")
    ok(g and g["cmds"] >= 1 and g["teclas"] >= 15, f"…os comandos de modelar pela seleção e as teclas gerais: {g and (g['cmds'], g['teclas'])}")
    # a busca filtra
    aba.cmd("Input.insertText", text="parafuso"); aba.drenar(0.2)
    f = js("return [...document.querySelectorAll('#guia-ferramentas .guia-linha')].map(l => l.dataset.id || 'cmd');")
    ok(f and "parafuso" in f and len(f) < 8, f"a busca 'parafuso' filtra: {f}")
    # o clique numa ferramenta (fora da busca: limpa e clica no Dividir) a abre e fecha o guia
    js("const b = document.querySelector('#guia-ferramentas .guia-busca'); b.value = ''; b.dispatchEvent(new Event('input')); return 1;")
    xy = js("const l = document.querySelector('#guia-ferramentas .guia-linha[data-id=\"dividir\"]'); l.scrollIntoView({ block: 'center' }); const r = l.getBoundingClientRect(); return [Math.round(r.left + 60), Math.round(r.top + r.height / 2)];")
    if xy:
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=xy[0], y=xy[1], button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=xy[0], y=xy[1], button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)
    ok(js("return editor.idAtiva;") == "dividir" and not aberto(), f"o clique no Dividir abre a ferramenta e fecha o guia: {js('return editor.idAtiva;')}")
    # F1 de novo e Esc fecha
    tecla("Escape"); tecla("F1")
    a1 = aberto()
    tecla("Escape")
    ok(a1 and not aberto(), "F1 abre de novo e Esc fecha")
    # o menu ? da barra única (a tela dividida) abre o guia no 3D
    aba.navegar(f"http://localhost:{PORTA}/dividida?projeto=gf", limite=90)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("[...document.querySelectorAll('iframe')].some(f => { try { return !!(f.contentWindow.editor && f.contentWindow.abrirGuiaFerramentas); } catch (e) { return false; } })"):
        aba.drenar(0.5)
    aba.avaliar("(() => { const b = document.querySelector('#menus-unicos .menu[data-nome=\"?\"] .menu-botao'); if (b) b.click(); return 1; })()")
    aba.drenar(0.3)
    item = aba.avaliar("""(() => { const it =[...document.querySelectorAll('button, a, li, div')].find(e => e.children.length <= 3 && /^Guia rápido das ferramentas/.test((e.textContent || '').trim()));
      if (!it) return 'sem item'; it.click(); return 'ok'; })()""")
    t0 = time.time(); viu = False
    while time.time() - t0 < 20 and not viu:
        viu = aba.avaliar("[...document.querySelectorAll('iframe')].some(f => { try { return !!f.contentDocument.getElementById('guia-ferramentas'); } catch (e) { return false; } })")
        aba.drenar(0.3)
    ok(item == "ok" and viu, f"o menu ? da barra única abre o guia no 3D: {(item, viu)}")
    erros_1 = []
    # o visor da tela dividida pede o "3D leve" de um projeto sem ele (404) e cai para o normal: não é erro do guia
    erros = erros_1 + [m for m in aba.console if m[0] in ("error", "excecao") and "3d-leve" not in m[1]]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
