# -*- coding: utf-8 -*-
"""Tab na seleção (14/10/2026, o "Tab" do Revit), com mouse e teclado de verdade (CDP): três vigas empilhadas vistas de
cima; com o mouse parado, Tab passa o destaque para a de trás, Tab de novo para a última, Shift+Tab volta; o clique
seleciona a destacada; mexer o mouse desfaz o ciclo."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_tab_")
PASTA = os.path.join(DADOS, "tb")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Tab", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_tab_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=tb", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('linha'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    def mouse(tipo, x, y, botao="right", n=1):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, clickCount=n, buttons=2 if botao == "right" and tipo != "mouseReleased" else 0)

    def tecla(k, shift=False):
        mods = 8 if shift else 0
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=k, windowsVirtualKeyCode=9 if k == "Tab" else 0, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=k, windowsVirtualKeyCode=9 if k == "Tab" else 0, modifiers=mods)
        aba.drenar(0.15)

    pos = json.loads(aba.avaliar("""(async () => {
      const ed = editor, doc = ed.documento, cena = ed.cena;
      const barra = (nome, z) => doc.add({ tipo: 'barra', nome, perfil: 'W 250×32,7', inicio: [0, 0, z], fim: [3000, 0, z], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      const v = [barra('cima', 2000), barra('meio', 1000), barra('baixo', 0)];
      for (let i = 0; i < 40 && !v.every(e => cena.objetos.has(e.id)); i++) await new Promise(r => setTimeout(r, 100));
      for (let i = 0; i < 50 && (cena._refinando || cena._pedidoAgendado); i++) await new Promise(r => setTimeout(r, 100));
      await new Promise(r => setTimeout(r, 600));
      ed.ativarFerramenta('selecionar');
      ed.camera.vista('topo'); ed.camera.concluirAnimacao && ed.camera.concluirAnimacao();
      await new Promise(r => setTimeout(r, 400));
      const t = ed.camera.paraTela([1500, 0, 2129]), r = ed.el.canvas.getBoundingClientRect();
      return JSON.stringify({ ids: v.map(e => e.id), x: r.left + t[0], y: r.top + t[1] }); })()"""))
    x, y = round(pos["x"]), round(pos["y"])
    cima, meio_, baixo = pos["ids"]
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=0)
    aba.drenar(0.2)
    sobre = lambda: aba.avaliar("editor.selecao.sobre")
    s0 = sobre()
    tecla("Tab"); s1 = sobre()
    tecla("Tab"); s2 = sobre()
    tecla("Tab", shift=True); s3 = sobre()
    dica = aba.avaliar("editor.el.dica.textContent")
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
    aba.drenar(0.3)
    sel = json.loads(aba.avaliar("JSON.stringify([...editor.selecao.ids])"))
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x + 25, y=y, buttons=0); aba.drenar(0.1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=0); aba.drenar(0.2)
    s4 = sobre()
    print("     ", [s0, s1, s2, s3], dica, sel, s4, pos["ids"])
    ok(s0 == cima and s1 == meio_ and s2 == baixo and s3 == meio_, f"Tab desce para a de trás, Tab de novo para a última, Shift+Tab volta: {[s0, s1, s2, s3]}")
    ok("Tab: 2 de 3" in (dica or ""), f"a dica diz qual delas: {dica}")
    ok(sel == [meio_], f"o clique seleciona a destacada (a do meio): {sel}")
    ok(s4 == cima, f"mexer o mouse desfaz o ciclo (de volta à de cima): {s4}")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
