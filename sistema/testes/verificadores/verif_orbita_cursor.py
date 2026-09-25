# -*- coding: utf-8 -*-
"""Editor 3D: órbita com o botão do meio em volta do ponto da peça sob o cursor — com uma
barra comprida selecionada, arrastar com o meio na ponta dela gira em volta da ponta (o
ponto fica parado na tela), e a câmera não vai para o meio da barra. No vazio, a órbita
continua a do OrbitControls. Eventos de mouse de verdade (CDP)."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8811
DADOS = tempfile.mkdtemp(prefix="metalica_orbita_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_orbita_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def mouse(aba, tipo, x, y, botao="middle", botoes=4):
    aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=1 if tipo == "mousePressed" else 0, modifiers=0)

try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("window.editor && window.editor.documento && window.editor.documento.entidades.size > 100"): aba.drenar(0.5)
    aba.drenar(2.0)
    # a barra mais comprida do modelo, selecionada e enquadrada; o ponto de mira é a 10 % do comprimento
    info = json.loads(aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, doc = ed.documento;
      let melhor = null, L = 0;
      for (const e of doc.entidades.values()) {
        if (e.tipo !== 'solido' || !e.vertices || e.vertices.length < 8) continue;
        const xs = [0, 1, 2].map(a => Math.max(...e.vertices.map(v => v[a])) - Math.min(...e.vertices.map(v => v[a])));
        const m = Math.max(...xs);
        if (m > L && Math.min(...xs) > 40) { L = m; melhor = e; }
      }
      ed.selecao.definir([melhor.id]);
      ed.camera.enquadrar(doc.caixa([melhor.id]));
      return { id: melhor.id, L };
    })())"""))
    aba.drenar(1.0)
    # procura, ao longo da barra, um pixel em que o raio acerta a própria barra, perto de uma ponta
    alvo = json.loads(aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, c = ed.camera, e = ed.documento.get('%s');
      const r = ed.el.canvas.getBoundingClientRect();
      const lo = [0, 1, 2].map(a => Math.min(...e.vertices.map(v => v[a]))), hi = [0, 1, 2].map(a => Math.max(...e.vertices.map(v => v[a])));
      for (const f of [0.08, 0.12, 0.16, 0.2, 0.9, 0.85]) {
        const p = [0, 1, 2].map(a => lo[a] + (hi[a] - lo[a]) * (a === [0, 1, 2].reduce((m, b) => (hi[b] - lo[b] > hi[m] - lo[m] ? b : m), 0) ? f : 0.5));
        const [x, y] = c.paraTela(p);
        const ndc = c._ndcDoEvento({ clientX: r.left + x, clientY: r.top + y });
        c._focoDoCursor(ndc);
        if (c.apoioDoZoom === 'peça') return { x: r.left + x, y: r.top + y, f };
      }
      return null;
    })())""" % info["id"]))
    ok(alvo is not None, f"achou um ponto da barra na tela: {alvo}")
    x, y = round(alvo["x"]), round(alvo["y"])
    antes = json.loads(aba.avaliar("""JSON.stringify((() => { const c = window.editor.camera, s = c.cena.documento.caixa(window.editor.selecao ? [...(window.editor.selecao.ids || [])] : []);
      return { pos: c.ativa.position.toArray(), alvo: c.controles.target.toArray() }; })())"""))
    mouse(aba, "mousePressed", x, y)
    aba.drenar(0.2)
    for k in range(1, 9):
        mouse(aba, "mouseMoved", x + 12 * k, y + 5 * k)
        aba.drenar(0.05)
    mouse(aba, "mouseReleased", x + 96, y + 40, botoes=0)
    aba.drenar(0.5)
    depois = json.loads(aba.avaliar("""JSON.stringify((() => { const c = window.editor.camera; const p = c.pivoDaOrbita;
      const ESC = c.paraTela([0, 0, 0]) && null;
      const mm = p ? [p.x, p.y, p.z].map(v => v / %s) : null;
      const r = window.editor.el.canvas.getBoundingClientRect();
      const t = mm ? c.paraTela(mm) : null;
      return { pos: c.ativa.position.toArray(), alvo: c.controles.target.toArray(), pivo: mm, pivoNaTela: t ? [r.left + t[0], r.top + t[1]] : null }; })())""" % "0.001"))
    ok(depois["pivo"] is not None, f"pivô no ponto da peça sob o cursor: {depois['pivo']}")
    if depois["pivoNaTela"]:
        dx, dy = depois["pivoNaTela"][0] - x, depois["pivoNaTela"][1] - y
        ok(abs(dx) < 3 and abs(dy) < 3, f"o ponto sob o cursor ficou parado na tela (desvio {dx:.1f}, {dy:.1f} px)")
    mudou = sum((a - b) ** 2 for a, b in zip(antes["pos"], depois["pos"])) ** 0.5
    ok(mudou > 1e-3, f"a câmera girou (andou {mudou:.3f} unidades)")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
