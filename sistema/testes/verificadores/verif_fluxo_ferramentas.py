# -*- coding: utf-8 -*-
"""O fluxo de uso de verdade das ferramentas do editor 3D (15/10/2026), só com o mouse e o teclado (CDP), como o usuário:
um pórtico — B, clique no chão, ↑ e "3000" (o pilar); a Barra continua da ponta: → e "6000" (a viga); a seleção do
pilar, M com Ctrl, → e "6000" (a cópia do pilar); D na aresta da viga (a cota dela); o botão direito na viga: a caixa
de corte e tirar; Ctrl+Z até o modelo vazio, Ctrl+Y de volta; Ctrl+S, recarregar a página e o modelo inteiro de volta.
Cada passo confere o modelo; nenhum erro no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo_")
PASTA = os.path.join(DADOS, "fx")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fluxo", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo_")
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
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=fx", limite=60)
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

    js("""editor.camera.enquadrar([[-1500, -2500, 0], [7500, 2500, 3500]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
    aba.drenar(0.5)
    barras = lambda: js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => ({ id: e.id, i: e.inicio.map(Math.round), f: e.fim.map(Math.round), papel: e.papel }));")

    # 1. o pilar: B, clique no chão, ↑ e 3000
    tecla("b")
    x, y = tela([0, 0, 0])
    clicar(x, y)
    tecla("ArrowUp")
    digitar("3000")
    b = barras()
    ok(b and len(b) == 1 and b[0]["f"][2] - b[0]["i"][2] == 3000 and b[0]["f"][:2] == b[0]["i"][:2],
       f"o pilar: B, clique, ↑ e 3000 — uma barra vertical de 3 m: {b}")
    base = b[0]["i"] if b else [0, 0, 0]
    # 2. a Barra continua da ponta: → e 6000 (a viga)
    tecla("ArrowRight")
    digitar("6000")
    b = barras()
    ok(b and len(b) == 2 and b[1]["i"] == b[0]["f"] and b[1]["f"][0] - b[1]["i"][0] == 6000 and b[1]["f"][1:] == b[1]["i"][1:],
       f"a viga: a Barra continua do topo do pilar, → e 6000: {b and b[1:]}")
    tecla("Escape"); tecla("Escape"); tecla(" ")
    ativa = js("return editor.idAtiva;")
    ok(ativa == "selecionar", f"Esc e Espaço voltam à Seleção: {ativa}")
    pilar, viga = (b[0]["id"], b[1]["id"]) if b and len(b) >= 2 else (None, None)

    # 3. a cópia do pilar: clique nele, M, Ctrl, clique na base, → e 6000
    x, y = tela([base[0], base[1], 1500])
    clicar(x, y)
    sel = js("return [...editor.selecao.ids];")
    ok(sel == [pilar], f"o clique no pilar o seleciona: {sel}")
    tecla("m")
    x, y = tela(base)
    clicar(x, y)
    tecla("Control")
    tecla("ArrowRight")
    digitar("6000")
    b = barras()
    novos = [q for q in (b or []) if q["id"] not in (pilar, viga)]
    ok(len(novos) == 1 and novos[0]["i"][0] - base[0] == 6000 and novos[0]["f"][2] - novos[0]["i"][2] == 3000,
       f"M, Ctrl, → e 6000: a cópia do pilar na outra ponta da viga: {novos}")
    papeis = [q["papel"] for q in (barras() or [])]
    ok(papeis == ["pilar", "viga", "pilar"], f"o papel pela direção (sem escolher): o que está em pé é pilar, o deitado viga: {papeis}")
    tecla("Escape"); tecla(" ")

    # 4. a cota da viga: D e um clique na aresta de cima dela, depois afastar e clicar
    tecla("d")
    topo = base[2] + 3000
    ar = js(f"""const v = editor.documento.get('{viga}'); const r = editor.el.canvas.getBoundingClientRect();
      // a aresta de cima, do lado da câmera: procura o ponto do meio da viga em que o snap dá "Sobre aresta"
      for (const dy of [-73, 73]) for (const dz of [129, -129]) {{
        const p = [v.inicio[0] + 2700, v.inicio[1] + dy, v.inicio[2] + dz], t = editor.camera.paraTela(p);
        const s = editor.inferencia.resolver(t[0], t[1], {{}});
        if (s.tipoSnap === 'sobre_aresta' && s.entidade === v.id) return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];
      }}
      return null;""")
    ok(ar is not None, f"achou a aresta da viga na tela: {ar}")
    if ar:
        clicar(ar[0], ar[1])
        x, y = ar[0], ar[1] + 60
        mover(x, y)
        clicar(x, y)
    cota = js("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.cota).map(e => ({ t: e.atributos.cota.texto, refs: (e.atributos.cota.refs || []).filter(Boolean).length }));")
    ok(cota and len(cota) == 1 and cota[0]["t"] in ("6,00 m", "6,000 m", "6 m") and cota[0]["refs"] == 2, f"D na aresta da viga: a cota de 6 m presa à viga: {cota}")
    tecla("Escape"); tecla("Escape"); tecla(" ")

    # 5. o botão direito na viga: caixa de corte; no vazio: tirar
    x, y = tela([base[0] + 3000, base[1], topo])
    clicar(x, y, "right")
    itens = js("return [...document.querySelectorAll('.menu-contexto button span')].map(s => s.textContent);")
    ok(itens and "Caixa de corte na seleção" in itens, f"o botão direito na viga abre o menu: {itens}")
    js("[...document.querySelectorAll('.menu-contexto button')].find(b => b.textContent.startsWith('Caixa de corte')).click(); return 1;")
    aba.drenar(0.6)
    caixa = js("return !!editor.cena.caixaCorte;")
    ok(caixa, "a caixa de corte ligada pelo menu")
    vazio = js("""const r = editor.el.canvas.getBoundingClientRect();
      for (let fy = 0.15; fy < 0.9; fy += 0.05) for (let fx = 0.1; fx < 0.9; fx += 0.05) { const px = r.left + r.width * fx, py = r.top + r.height * fy;
        if (document.elementFromPoint(px, py) === editor.el.canvas && !editor.selecao.sob(px - r.left, py - r.top)) return [Math.round(px), Math.round(py)]; }
      return null;""")
    if vazio:
        clicar(vazio[0], vazio[1], "right")
        js("const b = [...document.querySelectorAll('.menu-contexto button')].find(b => b.textContent.startsWith('Tirar a caixa')); if (b) b.click(); return 1;")
    ok(not js("return !!editor.cena.caixaCorte;"), "no vazio, o menu tira a caixa de corte")

    # 6. Ctrl+Z até o modelo vazio e Ctrl+Y de volta
    n0 = js("return editor.documento.entidades.size;")
    for _ in range(12):
        if js("return editor.documento.entidades.size;") == 0: break
        tecla("z", 2)
    vazio_ = js("return editor.documento.entidades.size;")
    for _ in range(12):
        if js("return editor.documento.entidades.size;") == n0: break
        tecla("y", 2)
    volta = js("return editor.documento.entidades.size;")
    ok(vazio_ == 0 and volta == n0, f"Ctrl+Z até o modelo vazio e Ctrl+Y de volta: {n0} → {vazio_} → {volta}")

    # 7. Ctrl+S, recarregar e o modelo de volta
    tecla("s", 2)
    t0 = time.time()
    while time.time() - t0 < 20 and js("return !!editor._sujo || !!(editor.documento && editor.documento.alterado);"):
        aba.drenar(0.5)
    aba.drenar(1.5)
    antes = js("return { n: editor.documento.entidades.size, b: [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').length };")
    erros_1 = [m for m in aba.console if m[0] in ("error", "excecao")]
    abrir()
    depois = js("return { n: editor.documento.entidades.size, b: [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').length };")
    ok(antes and depois and depois == antes and antes["b"] == 3, f"Ctrl+S e recarregar: o pórtico inteiro de volta: {antes} → {depois}")
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
