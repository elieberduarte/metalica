# -*- coding: utf-8 -*-
"""Atalhos das ferramentas (15/10/2026, decisão do usuário: "Shift+letra + configurável"), com o teclado e o mouse de
verdade (CDP): Shift+E/D/R/N/H/C/P abrem Estender, Dividir, Recortar, Encaixar, Enrijecedor, Editar chapa e Plano; a letra
solta continua a dela (E Escalar, H Chapa) e Shift+letra sem dono vale a letra (Shift+M Mover); no guia (F1) o clique no
atalho troca a tecla, a tecla de outra ferramenta muda de dono, o Z é recusado, a troca fica depois de recarregar e
"Atalhos padrão" volta tudo. E o Furo tem o próprio padrão (linhas × colunas), separado do Parafuso."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_atalhos_")
PASTA = os.path.join(DADOS, "gf")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Atalhos", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_atalhos_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
TECLAS = {"Shift": 16, "Delete": 46, "F1": 112, "ArrowUp": 38, "ArrowRight": 39, "ArrowLeft": 37, "ArrowDown": 40, "Enter": 13, "Escape": 27, "Control": 17, " ": 32}
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
    SHIFT = 8

    def shift(letra):
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Shift", windowsVirtualKeyCode=16, modifiers=SHIFT)
        L = letra.upper()
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=L, windowsVirtualKeyCode=ord(L), text=L, modifiers=SHIFT)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=L, windowsVirtualKeyCode=ord(L), modifiers=SHIFT)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Shift", windowsVirtualKeyCode=16, modifiers=0)
        aba.drenar(0.2)

    def solta():
        tecla("Escape"); tecla(" "); aba.drenar(0.1)

    ativa = lambda: js("return editor.idAtiva;")
    # 1. os padrões Shift+letra
    for letra, fid in [("E", "estender"), ("D", "dividir"), ("R", "recortar"), ("N", "encaixar"), ("H", "enrijecedor"),
                       ("C", "editar_chapa"), ("P", "plano")]:
        solta(); shift(letra)
        ok(ativa() == fid, f"Shift+{letra} abre {fid}: {ativa()}")
    # a letra solta continua a dela; Shift+letra sem dono vale a letra
    for k, fid in [("e", "escalar"), ("h", "chapa"), ("m", "mover")]:
        solta(); tecla(k)
        ok(ativa() == fid, f"{k.upper()} solta abre {fid}: {ativa()}")
    solta(); shift("M")
    ok(ativa() == "mover", f"Shift+M (sem dono) vale o M, Mover: {ativa()}")
    rot = js("return Object.fromEntries(['estender','dividir','barra','selecionar'].map(i => [i, editor.ferramentas.get(i).atalho]));")
    ok(rot == {"estender": "Shift+E", "dividir": "Shift+D", "barra": "B", "selecionar": "Espaço"}, f"rótulos dos atalhos: {rot}")
    lab = js("const b = document.querySelector('#barra-ferramentas [data-id=\"estender\"]'); return b && b.getAttribute('aria-label');")
    ok(lab is None or "Shift+E" in lab, f"o botão da barra mostra o atalho: {lab}")

    # 2. o Furo tem o padrão próprio
    solta()
    p = js("""const P = editor.ferramentas.get('parafuso'), F = editor.ferramentas.get('furo');
      return { proprio: Object.prototype.hasOwnProperty.call(F, 'padrao'), mesmo: P.padrao === F.padrao };""")
    ok(p == {"proprio": True, "mesmo": False}, f"o Furo tem o próprio padrão: {p}")
    tecla("u"); aba.drenar(0.3)
    campo = js("""const i = [...document.querySelectorAll('input[type=number]')].find(x => /atravessados/.test(x.title || ''));
      if (!i) return null; i.value = '3'; i.dispatchEvent(new Event('change')); return 1;""")
    pp = js("return [editor.ferramentas.get('parafuso').padrao.linhas, editor.ferramentas.get('furo').padrao.linhas];")
    ok(campo == 1 and pp == [3, 1], f"3 linhas no Parafuso não mudam o Furo: {campo, pp}")
    solta(); tecla("f"); aba.drenar(0.3)
    v = js("const i = [...document.querySelectorAll('input[type=number]')].find(x => /atravessados/.test(x.title || '')); return i && i.value;")
    ok(v == "1", f"o painel do Furo mostra o padrão dele (1): {v}")
    js("editor.ferramentas.get('parafuso').padrao.linhas = 1; return 1;")
    solta()

    # 3. a troca pelo guia
    def kbd_xy(fid):
        return js(f"""const k = document.querySelector('#guia-ferramentas .guia-linha[data-id="{fid}"] kbd'); if (!k) return null;
          k.scrollIntoView({{ block: 'center' }}); const r = k.getBoundingClientRect(); return [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2)];""")

    def clicar_tela(xy):
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=xy[0], y=xy[1], button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=xy[0], y=xy[1], button="left", clickCount=1, buttons=0)
        aba.drenar(0.25)

    aberto = lambda: js("return !!document.getElementById('guia-ferramentas');")
    kbd_txt = lambda fid: js(f"""const k = document.querySelector('#guia-ferramentas .guia-linha[data-id="{fid}"] kbd'); return k && k.textContent;""")
    aviso = lambda: js("const a = document.querySelector('#guia-ferramentas .guia-aviso-atalho'); return a && a.textContent;")
    tecla("F1")
    clicar_tela(kbd_xy("dividir"))
    cap = js("return document.querySelector('#guia-ferramentas .guia-capturando') ? 1 : 0;")
    ok(aberto() and cap == 1, f"o clique no atalho do Dividir espera a tecla (o guia continua aberto): {aberto(), cap}")
    shift("J")
    ok(kbd_txt("dividir") == "Shift+J" and aberto(), f"Shift+J vira o atalho do Dividir: {kbd_txt('dividir')}")
    # a tecla de outra ferramenta muda de dono
    clicar_tela(kbd_xy("dividir")); tecla("b")
    av = aviso()
    ok(kbd_txt("barra") == "—" and kbd_txt("dividir") == "B" and "Barra" in (av or ""), f"B tirado da Barra, com o aviso: {kbd_txt('barra')!r}, {av!r}")
    # o Z é recusado
    clicar_tela(kbd_xy("plano")); tecla("z")
    av = aviso(); kp = js("return editor.ferramentas.get('plano').atalho;")
    ok(kp == "Shift+P" and "zoom" in (av or ""), f"Z recusado (é o zoom em tudo): {kp}, {av!r}")
    # Esc durante a captura cancela sem fechar o guia; outro Esc fecha
    clicar_tela(kbd_xy("plano")); tecla("Escape")
    ok(aberto() and js("return editor.ferramentas.get('plano').atalho;") == "Shift+P", "Esc na captura cancela e o guia fica")
    tecla("Escape")
    ok(not aberto(), "Esc fecha o guia")
    solta(); tecla("b")
    ok(ativa() == "dividir", f"B agora abre o Dividir: {ativa()}")
    # fica depois de recarregar
    abrir()
    solta(); tecla("b")
    ok(ativa() == "dividir", f"depois de recarregar, B continua o Dividir: {ativa()}")
    solta(); shift("D")
    ok(ativa() == "cotar", f"Shift+D (sem dono agora) vale o D, Cotar: {ativa()}")
    # Atalhos padrão
    solta(); tecla("F1")
    js("const b = [...document.querySelectorAll('#guia-ferramentas button')].find(x => x.textContent === 'Atalhos padrão'); b.click(); return 1;")
    tecla("Escape"); solta(); tecla("b")
    a1 = ativa(); solta(); shift("D")
    ok(a1 == "barra" and ativa() == "dividir", f"Atalhos padrão: B Barra, Shift+D Dividir: {a1}, {ativa()}")
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
