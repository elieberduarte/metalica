# -*- coding: utf-8 -*-
"""Editor 3D: ferramenta Copiar com ponto de referência — o primeiro clique é a base (um
canto da peça), cada clique seguinte cola uma cópia com a base ali (medida sempre da
mesma referência); Enter aceita o canto da caixa como base; "dx;dy;dz" cola pelo vetor."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8809
DADOS = tempfile.mkdtemp(prefix="metalica_copiar3d_")
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_copiar3d_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("window.editor && window.editor.documento && window.editor.documento.entidades.size > 100"): aba.drenar(0.5)
    r = json.loads(aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, doc = ed.documento;
      const v = [];
      for (const z of [0, 100]) for (const [x, y] of [[70000, 0], [71000, 0], [71000, 100], [70000, 100]]) v.push([x, y, z]);
      const caixa = doc.add({ tipo: 'solido', nome: 'CAIXA', camada: 'Chapas', vertices: v,
        faces: [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]], arestas_vivas: [], atributos: { marcas: { nome: 'CAIXA' } } });
      const antes = doc.entidades.size;
      ed.selecao.definir([caixa.id]);
      ed.ativarFerramenta('copiar');
      const f = ed.ativa;
      const semBase = !f.base;
      // 1) o ponto de referência: o canto de cima da caixa (não cola nada)
      f.onPonto({ entidade: caixa.id, ponto: [71000, 100, 100], normal: [0, 0, 1] });
      const depoisDaBase = doc.entidades.size;
      // 2) dois destinos medidos da mesma referência
      f.onPonto({ entidade: null, ponto: [73000, 100, 100], normal: null });
      f.onPonto({ entidade: null, ponto: [75000, 600, 100], normal: null });
      // 3) e um vetor digitado
      f.onValor('0;0;1000');
      const novas = [...doc.entidades.values()].filter(e => e.nome === 'CAIXA' && e.id !== caixa.id);
      const minimos = novas.map(e => [0, 1, 2].map(a => Math.min(...e.vertices.map(q => q[a])))).sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
      return { semBase, base: f.base, antes, depoisDaBase, n: novas.length, minimos };
    })())"""))
    ok(r["semBase"] and r["depoisDaBase"] == r["antes"] and r["base"] == [71000, 100, 100], f"o primeiro clique é a referência e não cola: {r['semBase']} {r['base']} {r['antes']}→{r['depoisDaBase']}")
    ok(r["n"] == 3 and r["minimos"] == [[70000, 0, 1000], [72000, 0, 0], [74000, 500, 0]], f"três cópias, cada uma com a referência no ponto clicado ou pelo vetor digitado: {r['minimos']}")
    ok(aba.avaliar("window.editor.ativa && window.editor.ativa.constructor.id === 'copiar'"), "a ferramenta continua ativa para mais cópias")
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
