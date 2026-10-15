# -*- coding: utf-8 -*-
"""Mais ferramentas pelo uso de verdade (15/10/2026), com o mouse, o teclado e os botões da faixa (CDP): Recortar (botão)
a viga que entra no pilar; Encaixar (botão) a diagonal na face do pilar; K — copiar e colar o pilar; Q com ↑, Ctrl, "90"
e "*3" — as quatro vigas em volta do pilar; A — o arco com a flecha digitada; Plano de trabalho (botão) numa face e Z
de volta ao chão; Ctrl+Z até o começo."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo5_")
PASTA = os.path.join(DADOS, "f5")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fluxo5", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo5_")
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
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=f5", limite=60)
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
    barras = lambda: js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => ({ id: e.id, i: e.inicio.map(Math.round), f: e.fim.map(Math.round), papel: e.papel }));")

    def botao(id_):
        r = js(f"const b = document.querySelector('#barra-ferramentas [data-id=\"{id_}\"]'); if (!b) return null; b.click(); return editor.idAtiva;")
        aba.drenar(0.2)
        return r
    barras = lambda: js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => ({ id: e.id, i: e.inicio.map(Math.round), f: e.fim.map(Math.round), papel: e.papel, rec: (e.recortes || []).length, cortes: (e.cortes_inicio || []).length + (e.cortes_fim || []).length }));")
    js("""const doc = editor.documento;
      doc.add({ tipo: 'barra', nome: '', perfil: 'W 250×32,7', inicio: [0, 0, 0], fim: [0, 0, 3000], rotacao: 0, papel: 'pilar', camada: 'Estrutura', atributos: {} });
      doc.add({ tipo: 'barra', nome: '', perfil: 'W 250×32,7', inicio: [3000, 0, 2500], fim: [0, 0, 2500], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      doc.add({ tipo: 'barra', nome: '', perfil: 'L 63,5×6,35', inicio: [1500, 0, 300], fim: [400, 0, 1400], rotacao: 0, papel: 'diagonal', camada: 'Estrutura', atributos: {} });
      return 1;""")
    aba.drenar(1.5)
    pilar, viga, diag = [q["id"] for q in barras()]
    js("""editor.camera.vista('frente', [[-800, -500, 0], [3300, 500, 3200]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
    aba.drenar(1.0)
    # 1. Recortar: a viga perto da ponta que entra no pilar, depois o pilar
    at = botao("recortar")
    clicar(*tela([350, 0, 2500]))
    clicar(*tela([0, 0, 1800]))
    tecla("Escape"); tecla("Escape")
    v = [q for q in barras() if q["id"] == viga][0]
    ok(at == "recortar" and v["rec"] >= 1, f"Recortar (botão): a viga que entra no pilar ganha o recorte de encaixe da mesa: {(at, v)}")
    # 2. Encaixar: a diagonal, depois a face do pilar virada para ela (procurada na tela: a face de normal +x)
    face = js("""const r = editor.el.canvas.getBoundingClientRect();
      for (let z = 900; z <= 1700; z += 100) for (let x = 60; x <= 200; x += 10) {
        const t = editor.camera.paraTela([x, -60, z]); const s = editor.selecao.sob(t[0], t[1]);
        if (s && s.id === '%s' && s.normal[0] > 0.9) return [Math.round(r.left + t[0]), Math.round(r.top + t[1])]; }
      return null;""" % pilar)
    if not face:
        js("""editor.camera.vista('isometrica', [[-800, -800, 0], [1800, 800, 3000]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
        aba.drenar(1.0)
        face = js("""const r = editor.el.canvas.getBoundingClientRect();
          for (let z = 900; z <= 1700; z += 100) for (let y = -60; y <= 60; y += 20) for (let x = 100; x <= 200; x += 10) {
            const t = editor.camera.paraTela([x, y, z]); const s = editor.selecao.sob(t[0], t[1]);
            if (s && s.id === '%s' && s.normal[0] > 0.9) return [Math.round(r.left + t[0]), Math.round(r.top + t[1])]; }
          return null;""" % pilar)
    at = botao("encaixar")
    clicar(*tela([900, 0, 900]))      # na diagonal (de 1500;300 a 400;1400, x 900 é z 900)
    if face: clicar(*face)
    tecla("Escape"); tecla("Escape")
    d = [q for q in barras() if q["id"] == diag][0]
    ok(at == "encaixar" and face and d["cortes"] >= 1, f"Encaixar (botão): a diagonal cortada na face do pilar: {(at, face, d)}")
    # 3. K: copiar o pilar e colar a 6 m
    js("""editor.camera.vista('isometrica', [[-1500, -1500, 0], [7500, 1500, 3200]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
    aba.drenar(1.0)
    tecla(" ")
    js(f"editor.selecao.definir(['{pilar}']); return 1;")
    tecla("k")
    clicar(*tela([0, 0, 0]))
    clicar(*tela([6000, 0, 0]))
    tecla("Escape"); tecla("Escape")
    cop = [q for q in barras() if q["papel"] == "pilar" and q["id"] != pilar]
    ok(len(cop) == 1 and abs(cop[0]["i"][0] - 6000) <= 30 and cop[0]["f"][2] - cop[0]["i"][2] == 3000, f"K: o pilar copiado e colado a 6 m: {cop}")
    # 4. Q com ↑, Ctrl, 90 e *3: as vigas em volta do pilar
    tecla(" ")
    js(f"editor.selecao.definir(['{viga}']); return 1;")
    tecla("q"); tecla("ArrowUp")
    clicar(*tela([0, 0, 0]))
    clicar(*tela([1000, 0, 0]))
    tecla("Control")
    digitar("90")
    tecla("*")
    aba.cmd("Input.insertText", text="3"); aba.drenar(0.05); tecla("Enter"); aba.drenar(0.3)
    tecla("Escape"); tecla("Escape")
    vg = [q for q in barras() if q["papel"] == "viga"]
    ok(len(vg) == 4, f"Q, ↑, Ctrl, 90 e *3: quatro vigas em volta do pilar: {[(q['i'], q['f']) for q in vg]}")
    # 5. A: o arco no chão com a flecha digitada
    tecla("a")
    clicar(*tela([2000, 2000, 0]))
    clicar(*tela([4000, 2000, 0]))
    mover(*tela([3000, 2600, 0]))
    digitar("300")
    tecla("Escape")
    arco = js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'solido' && /arco/i.test((e.nome || '') + ' ' + JSON.stringify(e.atributos || {}))).map(e => e.vertices.length);")
    ok(arco and len(arco) == 1 and arco[0] >= 3, f"A, dois cliques e a flecha 300: o arco: {arco}")
    # 6. Plano de trabalho (botão) numa face do pilar copiado, e Z de volta ao chão
    at = botao("plano")
    clicar(*tela([6000, 0, 1500]))
    pl = js("return editor.inferencia.planoTrabalho && editor.inferencia.planoTrabalho.nome;")
    tecla("z")
    pl2 = js("return editor.inferencia.planoTrabalho;")
    tecla("Escape")
    ok(at == "plano" and pl == "vertical" and pl2 is None, f"Plano de trabalho (botão) na face do pilar (vertical) e Z de volta ao chão: {(at, pl, pl2)}")
    # 7. Ctrl+Z até o começo
    for _ in range(40):
        if js("return editor.pilha.feitos.length;") == 0: break
        tecla("z", 2)
    b = barras()
    ok(b and len(b) == 3 and js("return editor.documento.entidades.size;") == 3 and all(q["rec"] == 0 and q["cortes"] == 0 for q in b),
       f"Ctrl+Z desfaz tudo, de volta às três barras de partida: {b}")
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
