# -*- coding: utf-8 -*-
"""A ligação feita à mão (15/10/2026), com o mouse, o teclado e os botões da faixa (CDP): B — o pilar e a viga que para
500 antes dele; Estender (botão): a ponta da viga até a face do pilar; Enrijecedor (botão) com um clique na alma; Dividir
(botão) e "/2"; F na face do pilar (o furo); U na mesa de cima da viga, no gabarito (o parafuso); Ctrl+Z até o começo."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo4_")
PASTA = os.path.join(DADOS, "f4")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fluxo4", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo4_")
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
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=f4", limite=60)
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
    barras = lambda: js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => ({ id: e.id, i: e.inicio.map(Math.round), f: e.fim.map(Math.round), papel: e.papel }));")
    # o pilar (B, ↑ 3000) e a viga de x 3000 a 500, a 2500 de altura
    # a montagem não é o que este fluxo testa: o pilar e a viga entram direto no modelo (um clique "no ar" cai no chão)
    js("""const doc = editor.documento;
      doc.add({ tipo: 'barra', nome: '', perfil: 'W 250×32,7', inicio: [0, 0, 0], fim: [0, 0, 3000], rotacao: 0, papel: 'pilar', camada: 'Estrutura', atributos: {} });
      doc.add({ tipo: 'barra', nome: '', perfil: 'W 250×32,7', inicio: [3000, 0, 2500], fim: [500, 0, 2500], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      return 1;""")
    aba.drenar(1.5)
    b = barras()
    ok(b and len(b) == 2 and b[1]["f"][0] in (500, 501, 499), f"o pilar e a viga que para 500 antes dele: {b}")
    pilar, viga = (b[0]["id"], b[1]["id"]) if b and len(b) == 2 else (None, None)
    x0 = b[0]["i"][0] if b else 0
    # a vista de frente (olhando a alma da viga)
    js("""editor.camera.vista('frente', [[-800, -500, 1500], [3300, 500, 3200]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
    aba.drenar(1.0)
    # 1. Estender: a ponta da viga (x 500) até a face do pilar
    at = botao("estender")
    clicar(*tela([700, 0, 2500]))
    clicar(*tela([x0, 0, 2000]))
    tecla("Escape"); tecla("Escape")
    v = [q for q in (barras() or []) if q["id"] == viga]
    ok(at == "estender" and v and 60 <= v[0]["f"][0] - x0 <= 160, f"Estender (botão): a ponta da viga vai até a face do pilar (x ~ {x0} + meia seção): {(at, v)}")
    # 2. Enrijecedor: um clique na alma da viga, no meio
    n0 = js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'chapa').length;")
    at = botao("enrijecedor")
    clicar(*tela([1800, 0, 2500]))
    tecla("Escape"); tecla("Escape")
    n1 = js("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'chapa').length;")
    ok(at == "enrijecedor" and n1 - n0 == 2, f"Enrijecedor (botão) com um clique na alma: as duas chapas entre as mesas: {(at, n0, n1)}")
    # 3. Dividir: /2
    at = botao("dividir")
    mover(*tela([1500, 0, 2500]))
    clicar(*tela([1500, 0, 2500]))
    nb = len(barras() or [])
    if nb == 2:      # o clique não dividiu (passou o mouse): o "/2" divide em duas partes iguais
        digitar("/2")
    tecla("Escape"); tecla("Escape")
    vs = [q for q in (barras() or []) if q["papel"] == "viga"]
    ok(at == "dividir" and len(vs) == 2, f"Dividir (botão): a viga em duas: {(at, vs)}")
    # 4. F: um furo na face do pilar
    nf0 = js("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.furo).length;")
    tecla("f")
    clicar(*tela([x0, 0, 1000]))
    tecla("Escape"); tecla("Escape")
    nf1 = js("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.furo).length;")
    ok(nf1 - nf0 >= 1, f"F na face do pilar: o furo: {(nf0, nf1)}")
    # 5. U: o parafuso na mesa de cima da viga, no gabarito (fora da alma) — na vista de cima
    js("""editor.camera.vista('topo', [[-800, -800, 2000], [3300, 800, 2700]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
    aba.drenar(1.0)
    np0 = js("return [...editor.documento.entidades.values()].filter(e => /^BOLT/.test(e.nome || '')).length;")
    tecla("u")
    clicar(*tela([2300, 40, 2630]))
    tecla("Escape"); tecla("Escape")
    np1 = js("return [...editor.documento.entidades.values()].filter(e => /^BOLT/.test(e.nome || '')).map(e => e.nome);")
    ok(len(np1) - np0 >= 1, f"U na mesa de cima da viga, no gabarito: o parafuso: {np1}")
    # 6. Ctrl+Z até o modelo vazio
    # (o pilar e a viga de partida entraram direto no modelo, fora da pilha: o Ctrl+Z volta até eles)
    for _ in range(40):
        if js("return editor.pilha.feitos.length;") == 0: break
        tecla("z", 2)
    fim_ = barras()
    ok(fim_ and len(fim_) == 2 and fim_[1]["f"] == [500, 0, 2500] and js("return editor.documento.entidades.size;") == 2,
       f"Ctrl+Z desfaz tudo, de volta ao pilar e à viga de partida: {fim_}")
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
