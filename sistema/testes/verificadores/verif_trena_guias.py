# -*- coding: utf-8 -*-
"""Trena (14/10/2026): começando na aresta, a guia paralela a ela no afastamento digitado (a terça a 150 da borda),
como no SketchUp; a guia entre dois pontos continua; o painel apaga todas as guias e o Ctrl+Z volta."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_trena_")
PASTA = os.path.join(DADOS, "tr")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Trena", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_trena_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=tr", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('medir'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    r = jsj("""const ed = editor, doc = ed.documento;
      const guias = () => [...doc.entidades.values()].filter(e => e.atributos && e.atributos.tipo === 'construcao');
      ed.ativarFerramenta('medir'); const f = ed.ativa;
      f.onPonto({ ponto: [1000, 0, 0], tipoSnap: 'sobre_aresta', aresta: [[0, 0, 0], [2000, 0, 0]], entidade: null, tela: [0, 0] });
      const modo = !!f.aresta;
      f.onMover({ ponto: [1200, 300, 40], tipoSnap: 'plano_base', tela: [0, 0] });
      const medida = ed.el && ed.el.medida ? (ed.el.medida.value || ed.el.medida.textContent || '') : '';
      f.onValor('150');
      const g1 = guias()[0];
      // a guia de dois pontos (como antes)
      f.onPonto({ ponto: [0, 0, 0], tipoSnap: 'extremidade', tela: [0, 0] });
      f.onPonto({ ponto: [0, 0, 500], tipoSnap: 'extremidade', tela: [0, 0] });
      f.onTecla({ type: 'keydown', key: 'Enter' });
      const n2 = guias().length;
      f.apagarGuias(); const n0 = guias().length;
      ed.desfazer(); const nv = guias().length;
      return { modo, medida, g1: g1 && { v: g1.vertices.map(p => p.map(Math.round)), af: g1.atributos.afastamento, exp: g1.atributos.exportar }, n2, n0, nv };""")
    print("     ", r)
    ok(r and r["modo"], "começar na aresta liga a guia paralela")
    ok(r and r["g1"] and r["g1"]["v"] == [[-1000, 149, 20], [3000, 149, 20]] and r["g1"]["af"] == 150 and r["g1"]["exp"] is False,
       f"digitado 150: a guia paralela à aresta, a 150 dela, para o lado do mouse (y 300, z 40 → 149/20), esticada 1 m para cada lado, fora do IFC: {r and r['g1']}")
    ok(r and r["n2"] == 2, f"a guia de dois pontos com Enter continua: {r and r['n2']}")
    ok(r and r["n0"] == 0 and r["nv"] == 2, f"apagar as guias (e o Ctrl+Z volta): {r and (r['n0'], r['nv'])}")
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
