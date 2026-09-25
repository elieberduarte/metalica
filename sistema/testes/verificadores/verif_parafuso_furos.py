# -*- coding: utf-8 -*-
"""Editor 3D: o parafuso colocado fura as peças que atravessa (Ctrl+Z desfaz tudo junto),
o furo oblongo sai na malha em estádio, a troca de parafuso refaz a peça no mesmo lugar e
os furos do editor com o diâmetro novo, e o quadro (apoio, eixo, pega) de um parafuso do
IFC é lido da malha."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8812
DADOS = tempfile.mkdtemp(prefix="metalica_parafuros_")
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_parafuros_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CAIXA = """const caixa = (x0, y0, z0, x1, y1, z1, nome) => { const v = [];
  for (const z of [z0, z1]) for (const [x, y] of [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]) v.push([x, y, z]);
  return doc.add({ tipo: 'solido', nome, camada: 'Chapas', vertices: v,
    faces: [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]], arestas_vivas: [], atributos: { marcas: { nome } } }); };"""
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
    # 1) parafuso sobre duas chapas empilhadas: as duas ganham o furo Ø13
    r = json.loads(aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, doc = ed.documento; %s
      const cima = caixa(80000, 0, 100, 81000, 100, 106, 'CIMA');
      const baixo = caixa(80000, -200, 90, 81000, 300, 100, 'BAIXO');
      const nv = [cima.vertices.length, baixo.vertices.length];
      ed.ativarFerramenta('parafuso');
      ed.ativa._definir({ d: 12, L: 35, classe: 'A325' });
      ed.ativa.constructor.eixos = false;
      ed.ativa.onPonto({ entidade: cima.id, ponto: [80300, 50, 106], normal: [0, 0, 1], face: 3 });
      const b = [...doc.entidades.values()].find(e => e.atributos && e.atributos.parafuso && e.atributos.parafuso.ponto && e.atributos.parafuso.ponto[0] === 80300);
      const c2 = doc.get(cima.id), b2 = doc.get(baixo.id);
      return { ids: [cima.id, baixo.id, b ? b.id : null], nome: b && b.nome, furos: b && b.atributos.parafuso.furos,
               dv: [c2.vertices.length - nv[0], b2.vertices.length - nv[1]],
               regs: [(c2.atributos.furos_editor || []).map(x => x.d), (b2.atributos.furos_editor || []).map(x => x.d)],
               base: [!!c2.atributos.malha_sem_furos_editor, !!b2.atributos.malha_sem_furos_editor] };
    })())""" % CAIXA))
    ok(r["nome"] == "BOLT (A325) 12x35" and len(r["furos"] or []) == 2, f"parafuso colocado com os furos das 2 peças: {r['nome']} {r['furos']}")
    ok(r["dv"] == [32, 32] and r["regs"] == [[13], [13]] and r["base"] == [True, True], f"cada chapa ganhou o furo Ø13 na malha (32 vértices) e guardou a malha de antes: {r['dv']} {r['regs']} {r['base']}")
    id_cima, id_baixo, id_paraf = r["ids"]
    # a linha do eixo na prévia: atravessa a peça e marca onde cai na de baixo
    r1 = json.loads(aba.avaliar("""JSON.stringify((() => { const ed = window.editor; ed.ativarFerramenta('furo');
      const ex = ed.ativa._linhaDoEixo([80700, 50, 106], [0, 0, 1], '%s');
      return { n: ex.length, rotulos: ex.filter(o => o.userData && o.userData.texto).map(o => o.userData.texto),
               tipos: ex.map(o => o.type) }; })())""" % id_cima))
    ok(r1["n"] >= 2, f"linha do eixo com o ponto na peça de baixo: {r1}")
    # 2) troca de parafuso: M16x40 A307, os furos passam para 17
    r2 = json.loads(aba.avaliar("""(async () => {
      const ed = window.editor, doc = ed.documento;
      ed.ativarFerramenta('selecionar');
      ed.dialogo = async ({ corpo }) => { const s = corpo.querySelectorAll('select'), i = corpo.querySelector('input[type=number]');
        s[0].value = '16'; i.value = '40'; s[1].value = 'A307'; return 'ok'; };
      await ed.dialogoTrocarParafuso(['%s']);
      const { furosDaMalha } = await import('/editor3d/ferramentas/furo.js');
      const b = doc.get('%s'), c = doc.get('%s'), k = doc.get('%s');
      const ext = (e) => [0, 1, 2].map(a => Math.round(Math.max(...e.vertices.map(q => q[a])) - Math.min(...e.vertices.map(q => q[a]))));
      return JSON.stringify({ nome: b.nome, ext: ext(b), furos: [furosDaMalha(c).map(f => Math.round(f.d)), furosDaMalha(k).map(f => Math.round(f.d))],
                              regs: [(c.atributos.furos_editor || []).map(x => x.d), (k.atributos.furos_editor || []).map(x => x.d)] });
    })()""" % (id_paraf, id_paraf, id_cima, id_baixo)))
    ok(r2["nome"] == "BOLT (A307) 16x40", f"parafuso trocado: {r2['nome']} caixa {r2['ext']}")
    ok(r2["regs"] == [[17], [17]] and all(f and abs(f[0] - 17) <= 1 for f in r2["furos"]), f"furos refeitos com Ø17: {r2['furos']} {r2['regs']}")
    # 3) Ctrl+Z duas vezes: volta a troca e depois o parafuso com os furos
    r3 = json.loads(aba.avaliar("""JSON.stringify((() => { const ed = window.editor, doc = ed.documento;
      ed.desfazer(); const n1 = doc.get('%s').nome;
      ed.desfazer(); return [n1, !!doc.get('%s'), doc.get('%s').vertices.length, doc.get('%s').vertices.length]; })())"""
                                 % (id_paraf, id_paraf, id_cima, id_baixo)))
    ok(r3 == ["BOLT (A325) 12x35", False, 8, 8], f"Ctrl+Z desfaz a troca e depois o parafuso com os dois furos: {r3}")
    # 4) furo oblongo 13 × 23 ao longo da peça: laço de 18 pontos (estádio) na face
    r4 = json.loads(aba.avaliar("""(async () => { const ed = window.editor, doc = ed.documento; %s
      const ch = caixa(90000, 0, 100, 91000, 100, 106, 'CHAPA');
      ed.ativarFerramenta('furo');
      ed.ativa._definir(13); ed.ativa.constructor.comp = 23; ed.ativa.constructor.direcao = 'peca'; ed.ativa.constructor.eixos = false;
      ed.ativa.onPonto({ entidade: ch.id, ponto: [90500, 50, 106], normal: [0, 0, 1], face: 1 });
      const e = doc.get(ch.id);
      const { furosDaMalha } = await import('/editor3d/ferramentas/furo.js');
      const f = furosDaMalha(e);
      ed.ativa.constructor.comp = null;
      return JSON.stringify({ dv: e.vertices.length - 8, reg: e.atributos.furos_editor, furos: f.map(x => Math.round(x.d)) }); })()""" % CAIXA))
    reg = (r4["reg"] or [{}])[0]
    ok(r4["dv"] == 36 and reg.get("comp") == 23 and abs(abs(reg.get("dir", [0])[0]) - 1) < 1e-6 and r4["furos"] and r4["furos"][0] == 23,
       f"oblongo 13 × 23 ao longo da peça (x): {r4['dv']} vértices novos, registro {reg.get('comp')}/{reg.get('dir')}, extensão {r4['furos']}")
    # 5) o quadro de um parafuso do IFC: refazendo com o mesmo tamanho, a caixa quase não muda
    r5 = json.loads(aba.avaliar("""(async () => { const ed = window.editor, doc = ed.documento;
      const P = await import('/editor3d/ferramentas/parafuso.js');
      const out = [];
      for (const nome of ['BOLT (A) 12x35', 'BOLT (A) 16x50']) {
        const e = [...doc.entidades.values()].find(x => x.nome === nome);
        const q = P.quadroDoParafuso(e), t = P.tamanhoDoFixador(e);
        const g = P.geometriaDoParafuso(t.d, t.L, q.ponto, q.eixo.map(v => -v), q.pega);
        const cx = (vs) => [0, 1, 2].map(a => [Math.min(...vs.map(p => p[a])), Math.max(...vs.map(p => p[a]))]);
        const a = cx(e.vertices), b = cx(g.vertices);
        out.push({ nome, pega: q.pega && Math.round(q.pega * 10) / 10, desvio: Math.max(...a.flatMap((x, i) => [Math.abs(x[0] - b[i][0]), Math.abs(x[1] - b[i][1])])) });
      }
      return JSON.stringify(out); })()"""))
    for x in r5:
        ok(x["desvio"] < 6 and x["pega"], f"quadro do parafuso do IFC {x['nome']}: pega {x['pega']} mm, a peça refeita fica a {x['desvio']:.1f} mm da original")
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
