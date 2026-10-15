# -*- coding: utf-8 -*-
"""Alças da barra selecionada (14/10/2026), com o mouse de verdade (CDP): a barra selecionada mostra as alças das
pontas; arrastar a alça para o vazio estica ao longo da barra; até o canto de uma chapa, a ponta vai para o canto (snap);
Ctrl+Z volta; trocar de ferramenta tira as alças."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_alcas_")
PASTA = os.path.join(DADOS, "ac")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Alcas", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_alcas_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=ac", limite=60)
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

    def arrastar(de, para, passos=6):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=de[0], y=de[1], buttons=0); aba.drenar(0.1)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=de[0], y=de[1], button="left", clickCount=1, buttons=1)
        for k in range(1, passos + 1):
            x = round(de[0] + (para[0] - de[0]) * k / passos); y = round(de[1] + (para[1] - de[1]) * k / passos)
            aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="left", buttons=1); aba.drenar(0.06)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=para[0], y=para[1], button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)

    def clicar(p):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=p[0], y=p[1], buttons=0)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=p[0], y=p[1], button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=p[0], y=p[1], button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)

    pos = json.loads(aba.avaliar("""(async () => {
      const ed = editor, doc = ed.documento, cena = ed.cena;
      const v = doc.add({ tipo: 'barra', nome: 'viga', perfil: 'W 250×32,7', inicio: [0, 0, 0], fim: [2000, 0, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      const ch = doc.add({ tipo: 'chapa', nome: 'CH', camada: 'Chapas', origem: [2600, 1200, -10], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [300, 0], [300, 300], [0, 300]], espessura: 10, centrada: false, furos: [], atributos: {} });
      for (let i = 0; i < 40 && !(cena.objetos.has(v.id) && cena.objetos.has(ch.id)); i++) await new Promise(r => setTimeout(r, 100));
      for (let i = 0; i < 50 && (cena._refinando || cena._pedidoAgendado); i++) await new Promise(r => setTimeout(r, 100));
      await new Promise(r => setTimeout(r, 500));
      ed.ativarFerramenta('selecionar');
      ed.camera.vista('topo', [[-500, -1000, -200], [3500, 2000, 200]]); ed.camera.concluirAnimacao && ed.camera.concluirAnimacao();
      await new Promise(r => setTimeout(r, 400));
      const r = ed.el.canvas.getBoundingClientRect();
      const T = (p) => { const t = ed.camera.paraTela(p); return [Math.round(r.left + t[0]), Math.round(r.top + t[1])]; };
      return JSON.stringify({ id: v.id, meio: T([1000, 0, 129]), fim: T([2000, 0, 129]), vazio: T([2600, 0, 129]), canto: T([2600, 1200, 0]) }); })()"""))
    clicar(pos["meio"])
    n_alcas = aba.avaliar("(() => { let n = 0; editor.cena.previa.traverse(x => { if (x.isPoints || (x.isMesh && x.geometry && x.geometry.type === 'SphereGeometry')) n++; }); return editor.cena.previa.children.length ? n || editor.cena.previa.children[0].children.length : 0; })()")
    arrastar(pos["fim"], pos["vazio"])
    r1 = json.loads(aba.avaliar(f"JSON.stringify(editor.documento.get('{pos['id']}').fim.map(Math.round))"))
    arrastar(pos["vazio"], pos["canto"])
    r2 = json.loads(aba.avaliar(f"JSON.stringify(editor.documento.get('{pos['id']}').fim.map(Math.round))"))
    aba.avaliar("editor.desfazer()")
    r3 = json.loads(aba.avaliar(f"JSON.stringify(editor.documento.get('{pos['id']}').fim.map(Math.round))"))
    aba.avaliar("editor.ativarFerramenta('linha')")
    sem = aba.avaliar("editor.cena.previa.children.length")
    print("     ", n_alcas, r1, r2, r3, sem)
    ok(n_alcas and n_alcas >= 2, f"a viga selecionada mostra as alças das pontas: {n_alcas}")
    ok(r1[1] == 0 and r1[2] == 0 and abs(r1[0] - 2600) <= 30, f"arrastar a alça do fim para o vazio estica ao longo da viga (~2600, 0, 0): {r1}")
    ok(r2 == [2600, 1200, 0], f"arrastar até o canto da chapa leva a ponta para o canto (snap): {r2}")
    ok(abs(r3[0] - r1[0]) <= 1 and r3[1] == 0, f"o Ctrl+Z volta a ponta de antes: {r3}")
    ok(sem == 0, f"trocar de ferramenta tira as alças: {sem}")
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
