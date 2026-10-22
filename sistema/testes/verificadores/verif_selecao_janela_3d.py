# -*- coding: utf-8 -*-
"""A janela de seleção do editor 3D como no AutoCAD (usuário, 21/10: "se começo a selecionar por área ele não deixa usar
o pan ou mover a janela para o lado quando o mouse chega ao fim da tela, e se dou um alt + tab que volto o selecionar
fica ativo para sempre … se clicar em um ponto vazio … já habilita o selecionar por área não precisa ficar com ele
segurado, e quando clicar em outro ponto ele fecha a área e seleciona o que tem dentro"). O mesmo do CAD 2D
(verif_cad_janela.py), com a navegação do 3D: o botão direito desloca, o do meio orbita.

Mouse de verdade (Input.dispatchMouseEvent), vista de topo, três barras:
  A. clique no vazio abre a janela sem segurar o botão; o segundo clique fecha e seleciona (para a direita, o que está
     inteiro dentro; para a esquerda, o que toca);
  B. clique numa peça seleciona a peça (não abre janela);
  C. com a janela aberta, o direito arrasta a vista e o primeiro canto fica no ponto do modelo clicado;
  D. com a janela aberta, o cursor na borda faz a vista andar sozinha; longe dela, para;
  E. Esc cancela só a janela (a seleção fica); o direito sem arrastar também cancela, sem abrir o menu;
  F. no meio do arrasto com o esquerdo apertado, o direito também arrasta a vista;
  G. Alt+Tab (a janela do programa perde o foco) no meio do arrasto: a janela fica aberta e o próximo clique a fecha.
"""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_janela3d_")
PASTA = os.path.join(DADOS, "jn")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Janela3D", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-21T00:00:00", "alterado": "2026-10-21T00:00:00", "dados": None},
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_janela3d_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=jn", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('selecionar'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    ids = json.loads(aba.avaliar("""(async () => {
      const ed = editor, doc = ed.documento, cena = ed.cena;
      const barra = (nome, a, b) => doc.add({ tipo: 'barra', nome, perfil: 'W 250×32,7', inicio: a, fim: b, rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      const A = barra('A', [0, 0, 0], [1000, 0, 0]), B = barra('B', [3000, 0, 0], [4000, 0, 0]), C = barra('C', [3500, -1500, 0], [3500, 1500, 0]);
      for (let i = 0; i < 40 && ![A, B, C].every(e => cena.objetos.has(e.id)); i++) await new Promise(r => setTimeout(r, 100));
      for (let i = 0; i < 50 && (cena._refinando || cena._pedidoAgendado); i++) await new Promise(r => setTimeout(r, 100));
      await new Promise(r => setTimeout(r, 400));
      return JSON.stringify({ A: A.id, B: B.id, C: C.id }); })()"""))
    nome = {v: k for k, v in ids.items()}

    def preparar(sel=()):
        aba.avaliar("""(async () => { const ed = editor; ed.ativarFerramenta('selecionar');
          ed.camera.vista('topo', [[-1000, -2500, -200], [5000, 2500, 400]]); ed.camera.concluirAnimacao();
          ed.selecao.limpar(); %s
          await new Promise(r => setTimeout(r, 300)); return 1; })()""" % "".join(f"ed.selecao.somar(['{ids[s]}']);" for s in sel))
        aba.drenar(0.3)

    def tela(p):
        return jsj("const ed = editor, r = ed.el.canvas.getBoundingClientRect(); const t = ed.camera.paraTela(%s);"
                   " return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];" % json.dumps(p))

    def evento(tipo, x, y, botao="none", botoes=0, n=1):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=n)

    def clique(p):
        evento("mouseMoved", p[0], p[1]); aba.drenar(0.08)
        evento("mousePressed", p[0], p[1], "left", 1)
        evento("mouseReleased", p[0], p[1], "left", 0)
        aba.drenar(0.25)

    def esc():
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        aba.drenar(0.2)

    sel = lambda: sorted(nome.get(i, i) for i in jsj("return [...editor.selecao.ids];"))
    aberta = lambda: bool(aba.avaliar("!!(editor.ativa && editor.ativa._janela)"))
    retangulo = lambda: bool(aba.avaliar("!editor.el.retangulo.hidden"))
    alvo = lambda: jsj("const a = editor.camera.alvo; return [Math.round(a.x * 1000), Math.round(a.y * 1000)];")
    menu = lambda: bool(aba.avaliar("!!document.querySelector('.menu-contexto')"))

    # A. clique-clique
    preparar()
    clique(tela([2500, 1000, 0]))
    ok(aberta(), "A. clique no vazio abre a janela (sem segurar o botão)")
    p1 = tela([4500, -1000, 0])
    evento("mouseMoved", p1[0] - 100, p1[1] - 50); aba.drenar(0.1); evento("mouseMoved", p1[0], p1[1]); aba.drenar(0.15)
    ok(retangulo(), "A. a janela acompanha o cursor com o botão solto")
    clique(p1)
    ok(sel() == ["B"] and not aberta() and not retangulo(), f"A. o segundo clique fecha e seleciona o que está inteiro dentro: {sel()}")
    preparar()
    clique(tela([4300, 1000, 0])); clique(tela([2000, -1000, 0]))
    ok(sel() == ["B", "C"], f"A. da direita para a esquerda, o que toca: {sel()}")

    # B. clique numa peça
    preparar()
    clique(tela([500, 0, 129]))
    ok(sel() == ["A"] and not aberta(), f"B. clique numa peça seleciona a peça, sem abrir janela: {sel()}")

    # C. pan com o direito com a janela aberta
    preparar()
    clique(tela([2500, 1000, 0]))
    antes = alvo()
    xm, ym = 700, 160
    evento("mouseMoved", xm, ym); evento("mousePressed", xm, ym, "right", 2)
    for k in range(1, 5):
        evento("mouseMoved", xm - 60 * k, ym, "right", 2); aba.drenar(0.05)
    evento("mouseReleased", xm - 240, ym, "right", 0); aba.drenar(0.4)
    ok(alvo() != antes and aberta() and not menu(), f"C. o direito arrasta a vista com a janela aberta, sem menu ({antes} → {alvo()})")
    clique(tela([4500, -1000, 0]))
    ok(sel() == ["B"], f"C. depois do pan, o primeiro canto ficou no ponto do modelo clicado: {sel()}")

    # D. a borda faz a vista andar
    preparar()
    clique(tela([2500, 1000, 0]))
    antes = alvo()
    r = jsj("const r = editor.el.canvas.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom];")
    evento("mouseMoved", r[2] - 4, (r[1] + r[3]) / 2); aba.drenar(0.6)
    depois = alvo()
    ok(depois[0] > antes[0], f"D. na borda direita a vista anda para a direita sozinha ({antes} → {depois})")
    evento("mouseMoved", r[2] - 300, (r[1] + r[3]) / 2); aba.drenar(0.3)
    parado = alvo(); aba.drenar(0.3)
    ok(alvo() == parado, "D. longe da borda, para")
    esc()

    # E. Esc / direito sem arrastar cancelam só a janela
    preparar(sel=("A",))
    clique(tela([2500, 1000, 0]))
    esc()
    ok(not aberta() and not retangulo() and sel() == ["A"], f"E. Esc cancela a janela e a seleção fica: {sel()}")
    clique(tela([2500, 1000, 0]))
    q = tela([2600, 900, 0])
    evento("mouseMoved", q[0], q[1]); evento("mousePressed", q[0], q[1], "right", 2); evento("mouseReleased", q[0], q[1], "right", 0)
    aba.drenar(0.3)
    ok(not aberta() and not retangulo() and not menu() and sel() == ["A"],
       f"E. o direito sem arrastar cancela a janela, sem abrir o menu: aberta={aberta()} menu={menu()} {sel()}")

    # F. o direito no meio do arrasto
    preparar()
    p0 = tela([2500, 1000, 0])
    evento("mouseMoved", p0[0], p0[1]); evento("mousePressed", p0[0], p0[1], "left", 1)
    evento("mouseMoved", p0[0] + 20, p0[1] + 20, "left", 1); aba.drenar(0.05)
    evento("mouseMoved", p0[0] + 40, p0[1] + 40, "left", 1); aba.drenar(0.1)
    antes = alvo()
    for k in range(1, 4):
        evento("mouseMoved", p0[0] + 40 - 60 * k, p0[1] + 40, "left", 3); aba.drenar(0.05)
    aba.drenar(0.2)
    ok(alvo() != antes, f"F. o direito arrasta a vista no meio do arrasto da janela ({antes} → {alvo()})")
    p1 = tela([4500, -1000, 0])
    evento("mouseMoved", p1[0], p1[1], "left", 1); aba.drenar(0.1)
    evento("mouseReleased", p1[0], p1[1], "left", 0); aba.drenar(0.3)
    ok(sel() == ["B"] and not menu(), f"F. e a janela pega o que estava no ponto do modelo do primeiro canto: {sel()}")

    # G. Alt+Tab no meio do arrasto
    preparar()
    p0 = tela([2500, 1000, 0]); p1 = tela([4500, -1000, 0])
    evento("mouseMoved", p0[0], p0[1]); evento("mousePressed", p0[0], p0[1], "left", 1)
    evento("mouseMoved", p0[0] + 30, p0[1] + 30, "left", 1); aba.drenar(0.05)
    evento("mouseMoved", p0[0] + 60, p0[1] + 60, "left", 1); aba.drenar(0.1)
    aba.avaliar("window.dispatchEvent(new Event('blur'))"); aba.drenar(0.2)
    ok(aberta(), "G. Alt+Tab no meio do arrasto: a janela fica aberta (não presa ao botão que se perdeu)")
    evento("mouseMoved", p1[0], p1[1]); aba.drenar(0.15)
    clique(p1)
    ok(sel() == ["B"] and not aberta() and not retangulo(), f"G. ao voltar, o próximo clique fecha a janela e seleciona: {sel()}")
    evento("mouseMoved", p0[0], p0[1]); aba.drenar(0.2)
    ok(not retangulo(), "G. e depois o cursor anda sem janela")

    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
