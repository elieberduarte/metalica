# -*- coding: utf-8 -*-
"""Seleção e edição pelo uso de verdade (15/10/2026), com o mouse e o teclado (CDP): E no canto de uma caixa de 1 m e "2"
(dobra); a janela arrastada da esquerda para a direita pega só o que está inteiro dentro, da direita para a esquerda
também o que encosta; Dividir (botão) uma barra e Juntar peças (menu) de volta; Ctrl+Z até o começo."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo6_")
PASTA = os.path.join(DADOS, "f6")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fluxo6", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo6_")
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
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=f6", limite=60)
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
    barras = lambda: js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => ({ id: e.id, i: e.inicio.map(Math.round), f: e.fim.map(Math.round) }));")
    def arrastar(de, para):
        mover(*de)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=de[0], y=de[1], button="left", clickCount=1, buttons=1)
        for k in range(1, 7):
            x = round(de[0] + (para[0] - de[0]) * k / 6); y = round(de[1] + (para[1] - de[1]) * k / 6)
            aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="left", buttons=1); aba.drenar(0.05)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=para[0], y=para[1], button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)
    js("""const doc = editor.documento;
      const V = [[0,0,0],[1000,0,0],[1000,1000,0],[0,1000,0],[0,0,1000],[1000,0,1000],[1000,1000,1000],[0,1000,1000]];
      const F = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]];
      doc.add({ tipo: 'solido', nome: 'Caixa', camada: 'Estrutura', vertices: V, faces: F, arestas_vivas: [], atributos: {} });
      doc.add({ tipo: 'barra', nome: '', perfil: 'W 250×32,7', inicio: [3000, 0, 0], fim: [5000, 0, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      doc.add({ tipo: 'barra', nome: '', perfil: 'W 250×32,7', inicio: [3000, 1500, 0], fim: [7000, 1500, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      return 1;""")
    aba.drenar(1.5)
    caixa_id = js("return [...editor.documento.entidades.values()].find(e => e.nome === 'Caixa').id;")
    A, B = [q["id"] for q in barras()]
    js("""editor.camera.vista('topo', [[-1000, -1500, -200], [8000, 2500, 1200]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
    aba.drenar(1.0)
    # 1. E no canto de cima da caixa e "2": a caixa dobra
    tecla(" ")
    js(f"editor.selecao.definir(['{caixa_id}']); return 1;")
    tecla("e")
    clicar(*tela([1000, 1000, 1000]))
    digitar("2")
    tecla("Escape"); tecla("Escape")
    lim = js(f"const v = editor.documento.get('{caixa_id}').vertices; return [0, 1, 2].map(i => Math.round(Math.max(...v.map(p => p[i])) - Math.min(...v.map(p => p[i]))));")
    ok(lim == [2000, 2000, 2000], f"E no canto da caixa e 2: ela dobra (2 m de lado): {lim}")
    # 2. a janela da esquerda para a direita: só a barra A, inteira dentro
    tecla(" ")
    js("editor.selecao.limpar(); return 1;")
    a1, a2 = tela([2700, -400, 0]), tela([5300, 400, 0])
    arrastar((min(a1[0], a2[0]), min(a1[1], a2[1])), (max(a1[0], a2[0]), max(a1[1], a2[1])))
    sel1 = js("return [...editor.selecao.ids];")
    ok(sel1 == [A], f"a janela da esquerda para a direita pega só a barra inteira dentro: {sel1}")
    # 3. a janela da direita para a esquerda, que encosta na B: as duas
    js("editor.selecao.limpar(); return 1;")
    b1, b2 = tela([5300, 1800, 0]), tela([3500, -400, 0])
    arrastar((max(b1[0], b2[0]), min(b1[1], b2[1])), (min(b1[0], b2[0]), max(b1[1], b2[1])))
    sel2 = sorted(js("return [...editor.selecao.ids];") or [])
    ok(sel2 == sorted([A, B]), f"a janela da direita para a esquerda pega também a que só encosta: {sel2}")
    # 4. Dividir a barra B no meio e Juntar peças de volta
    at = js("const b = document.querySelector('#barra-ferramentas [data-id=\"dividir\"]'); b.click(); return editor.idAtiva;")
    mover(*tela([5000, 1500, 125]))
    clicar(*tela([5000, 1500, 125]))
    tecla("Escape"); tecla("Escape")
    partes = [q for q in barras() if q["i"][1] == 1500]
    tecla(" ")
    js("editor.selecao.definir(" + json.dumps([q["id"] for q in partes]) + "); document.querySelector('[data-acao=\"juntar\"]').click(); return 1;")
    aba.drenar(0.4)
    juntas = [q for q in barras() if q["i"][1] == 1500]
    ok(at == "dividir" and len(partes) == 2 and len(juntas) == 1 and abs(juntas[0]["f"][0] - juntas[0]["i"][0]) == 4000 and juntas[0]["id"] == B,
       f"Dividir (botão) a barra em duas e Juntar peças (menu) de volta numa só de 4 m, com o id da original: {(at, partes, juntas)}")
    # 5. Ctrl+Z até o começo
    for _ in range(30):
        if js("return editor.pilha.feitos.length;") == 0: break
        tecla("z", 2)
    fim_b = barras()
    lim0 = js(f"const v = editor.documento.get('{caixa_id}').vertices; return [0, 1, 2].map(i => Math.round(Math.max(...v.map(p => p[i])) - Math.min(...v.map(p => p[i]))));")
    ok(len(fim_b) == 2 and lim0 == [1000, 1000, 1000], f"Ctrl+Z desfaz tudo: a caixa de 1 m e as duas barras de partida: {(fim_b, lim0)}")
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
