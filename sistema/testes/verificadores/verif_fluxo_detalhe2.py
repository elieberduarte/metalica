# -*- coding: utf-8 -*-
"""As ferramentas de detalhe que faltavam pelo uso de verdade (15/10/2026), com o mouse, o teclado e o painel (CDP): U com o
padrão 2×2 a cada 100 (painel) e um clique na chapa de 16 (quatro M12x35); F, "22" e um clique (o furo de 22); Editar
chapa (botão): o canto e "50;0"; D entre dois cantos; T entre dois pontos e Enter (a guia); G e "300" (o polígono);
Ctrl+Z até o começo."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo7_")
PASTA = os.path.join(DADOS, "f7")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fluxo7", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo7_")
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
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=f7", limite=60)
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
    conta = lambda filtro: js(f"return [...editor.documento.entidades.values()].filter(e => {filtro}).length;")
    js("""editor.documento.add({ tipo: 'chapa', nome: 'CH16', camada: 'Chapas', origem: [-200, -200, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [400, 0], [400, 400], [0, 400]], espessura: 16, centrada: false, furos: [], atributos: {} }); return 1;""")
    aba.drenar(1.5)
    ch = js("return [...editor.documento.entidades.values()].find(e => e.tipo === 'chapa').id;")
    js("""editor.camera.vista('topo', [[-1500, -900, -100], [1500, 900, 300]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;""")
    aba.drenar(1.0)
    # 1. U, o padrão 2×2 a cada 100 no painel, e um clique no meio da chapa
    tecla("u")
    aba.drenar(0.3)
    pn = js("""const campos = [...document.querySelectorAll('input[type=number]')];
      const achar = (t) => campos.find(i => (i.title || '').startsWith(t));
      const pares = [['Quantos atravessados', '2'], ['Distância entre eles na largura', '100'], ['Quantos ao longo', '2'], ['Distância entre eles ao longo', '100']];
      let n = 0; for (const [t, v] of pares) { const i = achar(t); if (i) { i.value = v; i.dispatchEvent(new Event('change', { bubbles: true })); n++; } }
      return n;""")
    clicar(*tela([0, 0, 16]))
    tecla("Escape"); tecla("Escape")
    bolts = js("return [...editor.documento.entidades.values()].filter(e => /^BOLT/.test(e.nome || '')).map(e => e.nome);")
    ok(pn == 4 and bolts and len(bolts) == 4 and all(b == "BOLT (A325) 12x35" for b in bolts), f"U com o padrão 2×2 (painel) e um clique na chapa de 16: quatro M12x35: {(pn, bolts)}")
    # 2. F, "22" e um clique (fora dos parafusos)
    nf0 = conta("e.atributos && e.atributos.furo")
    tecla("f")
    digitar("22")
    clicar(*tela([-130, -130, 16]))
    tecla("Escape"); tecla("Escape")
    furos = js(f"const c = editor.documento.get('{ch}'); return (c.furos || []).map(f => f.d || f.diametro);")
    ok(furos and any(abs((d or 0) - 22) < 0.01 for d in furos), f"F, 22 e um clique: o furo de 22 na chapa: {furos}")
    # 3. Editar chapa: o canto (200, 200) e "50;0"
    tecla(" ")
    js(f"editor.selecao.definir(['{ch}']); return 1;")
    at = js("const b = document.querySelector('#barra-ferramentas [data-id=\"editar_chapa\"]'); b.click(); return editor.idAtiva;")
    aba.drenar(0.3)
    clicar(*tela([200, 200, 16]))
    digitar("50;0")
    tecla("Escape"); tecla("Escape")
    cont = js(f"return editor.documento.get('{ch}').contorno.map(p => p.map(Math.round));")
    ok(at == "editar_chapa" and cont and [450, 400] in cont, f"Editar chapa (botão): o canto e 50;0 — o canto andou 50: {(at, cont)}")
    # 4. D entre dois cantos e o afastamento
    tecla("d")
    clicar(*tela([-200, -200, 16]))
    clicar(*tela([-200, 200, 16]))
    mover(*tela([-400, 0, 16])); clicar(*tela([-400, 0, 16]))
    tecla("Escape"); tecla("Escape")
    cotas = js("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.cota).map(e => e.atributos.cota.texto);")
    ok(cotas == ["400 mm"], f"D entre dois cantos e o afastamento: a cota de 400: {cotas}")
    # 5. T entre dois pontos e Enter (a guia)
    tecla("t")
    clicar(*tela([-200, -200, 16]))
    clicar(*tela([250, 200, 16]))
    tecla("Enter"); tecla("Escape")
    guias = conta("e.atributos && e.atributos.tipo === 'construcao'")
    ok(guias == 1, f"T entre dois pontos e Enter: a linha de construção: {guias}")
    # 6. G e 300 (o polígono)
    tecla("g")
    clicar(*tela([900, 0, 0]))
    mover(*tela([1000, 0, 0]))
    digitar("300")
    tecla("Escape")
    pol = js("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.forma === 'poligono').map(e => [e.atributos.raio, e.atributos.lados]);")
    ok(pol and len(pol) == 1 and pol[0][0] == 300, f"G e 300: o polígono de raio 300: {pol}")
    # 7. Ctrl+Z até o começo
    for _ in range(40):
        if js("return editor.pilha.feitos.length;") == 0: break
        tecla("z", 2)
    fim_ = js(f"const c = editor.documento.get('{ch}'); return {{ n: editor.documento.entidades.size, furos: (c.furos || []).length, cont: c.contorno }};")
    ok(fim_ and fim_["n"] == 1 and fim_["furos"] == 0 and fim_["cont"] == [[0, 0], [400, 0], [400, 400], [0, 400]], f"Ctrl+Z desfaz tudo: só a chapa de partida, sem furos e com o contorno de antes: {fim_}")
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
