# -*- coding: utf-8 -*-
"""Edição da chapa no 3D e enrijecedor (F10 do levantamento de 14/10/2026):
  Editar chapa — a alça do vértice sob o mouse, mover o vértice, vértice novo no meio do lado, mover e apagar o furo,
  chanfro e raio de canto, apagar o vértice; cada mudança uma entrada do Ctrl+Z;
  Enrijecedor — na W 250, duas chapas entre as mesas (da face da alma à borda da mesa, das faces de dentro das mesas),
  chanfro de 20 nos cantos da alma, 6,3 mm (a alma de 6,1 na comercial acima); no U, só do lado das mesas."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_chapa3d_")
PASTA = os.path.join(DADOS, "ch3d")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Chapa 3D", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_chapa3d_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=ch3d", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('editar_chapa') && editor.ferramentas.get('enrijecedor')"
                                                    " && editor.cena.perfil('W 250×32,7') && editor.cena.perfil('U 3\"×6,1'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    ok(aba.avaliar("!!(document.querySelector('[data-id=\"editar_chapa\"]') && document.querySelector('[data-id=\"enrijecedor\"]'))"),
       "Editar chapa e Enrijecedor estão na barra de ferramentas")
    r = jsj("""const ed = editor, doc = ed.documento;
      const ch = doc.add({ tipo: 'chapa', nome: 'CH', camada: 'Chapas', origem: [0, 0, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [200, 0], [200, 100], [0, 100]], espessura: 9.5, centrada: false, furos: [{ x: 40, y: 50, diametro: 17.5 }], atributos: {} });
      ed.camera.enquadrar([[-50, -50, -50], [250, 150, 50]]); ed.camera.concluirAnimacao();
      ed.selecao.definir([ch.id]); ed.ativarFerramenta('editar_chapa'); const f = ed.ativa;
      // a alça sob o mouse: o vértice 2 projetado na tela
      const al = f._alcas(doc.get(ch.id)).out.find(a => a.tipo === 'vertice' && a.i === 2);
      const t = ed.camera.paraTela(al.p); const sob = f._alcaSob(doc.get(ch.id), [t[0] + 3, t[1] - 2]);
      // mover o vértice 2 para (240, 130)
      f.pego = { tipo: 'vertice', i: 2 }; f._soltar([240, 130]);
      const c1 = doc.get(ch.id).contorno.map(q => q.slice());
      // vértice novo no meio do lado 0 e levado para (100, -20)
      f._alcaSob = () => ({ tipo: 'meio', i: 0 }); f.onPonto({ tela: [0, 0] }); f._soltar([100, -20]);
      const c2 = doc.get(ch.id).contorno.map(q => q.slice());
      delete f._alcaSob;
      // o furo para (150, 60) e depois apagado
      f.pego = { tipo: 'furo', i: 0 }; f._soltar([150, 60]); const furo = doc.get(ch.id).furos[0];
      f.escolhido = { tipo: 'furo', i: 0 }; f.onTecla({ type: 'keydown', key: 'Delete' }); const nf = doc.get(ch.id).furos.length;
      // numa chapa quadrada nova: chanfro de 20 no canto (0, 0) e raio de 30 no canto (0, 100)
      const q = doc.add({ tipo: 'chapa', nome: 'Q', camada: 'Chapas', origem: [0, 500, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [200, 0], [200, 100], [0, 100]], espessura: 9.5, centrada: true, furos: [], atributos: {} });
      f._escolher(doc.get(q.id));
      f.escolhido = { tipo: 'vertice', i: 0 }; f.onValor('ch20'); const c3 = doc.get(q.id).contorno.map(p => p.map(x => Math.round(x * 10) / 10));
      const i100 = doc.get(q.id).contorno.findIndex(p => Math.abs(p[0]) < 1e-6 && Math.abs(p[1] - 100) < 1e-6);
      f.escolhido = { tipo: 'vertice', i: i100 }; f.onValor('r30'); const c4 = doc.get(q.id).contorno;
      // desfazer volta o raio
      ed.desfazer(); const c5 = doc.get(q.id).contorno.length;
      return { sob, c1, c2, furo, nf, c3, n4: c4.length, c5, pertoDoArco: c4.filter(q => Math.hypot(q[0] - 30, q[1] - 70) > 29.9 && Math.hypot(q[0] - 30, q[1] - 70) < 30.1).length };""")
    ok(r and r["sob"] and r["sob"]["tipo"] == "vertice" and r["sob"]["i"] == 2, f"a alça do vértice sob o mouse é achada pela tela: {r and r['sob']}")
    ok(r and r["c1"][2] == [240, 130], f"vértice movido: {r and r['c1']}")
    ok(r and len(r["c2"]) == 5 and r["c2"][1] == [100, -20], f"vértice novo no meio do lado, levado para (100; −20): {r and r['c2']}")
    ok(r and r["furo"]["x"] == 150 and r["furo"]["y"] == 60 and r["nf"] == 0, f"furo movido e depois apagado: {r and (r['furo'], r['nf'])}")
    ok(r and r["c3"][:2] == [[0, 20], [20, 0]] and len(r["c3"]) == 5, f"chanfro de 20 no canto (0; 0): {r and r['c3']}")
    ok(r and r["n4"] == r["c5"] + 8 and r["pertoDoArco"] >= 9, f"raio de 30 no canto (0; 100): {r and r['n4']} vértices, {r and r['pertoDoArco']} no arco; Ctrl+Z volta para {r and r['c5']}")
    aba.avaliar("editor.ativarFerramenta('selecionar'); 1")

    r = jsj("""const ed = editor, doc = ed.documento;
      const w = doc.add({ tipo: 'barra', nome: 'W', perfil: 'W 250×32,7', inicio: [0, 1000, 0], fim: [3000, 1000, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: { marcas: { conjunto: 'V1' } } });
      const u = doc.add({ tipo: 'barra', nome: 'U', perfil: 'U 3"×6,1', inicio: [0, 2000, 0], fim: [3000, 2000, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      ed.ativarFerramenta('enrijecedor'); const f = ed.ativa;
      const n0 = doc.entidades.size; f.colocar(doc.get(w.id), 1500, 1);
      const chs = [...doc.entidades.values()].filter(e => e.tipo === 'chapa' && e.atributos && e.atributos.enrijecedor_de === w.id);
      const geo = chs.map(c => { const xs = c.contorno.map(q => q[0]), ys = c.contorno.map(q => q[1]);
        return { L: Math.max(...xs) - Math.min(...xs), H: Math.max(...ys) - Math.min(...ys), esp: c.espessura, n: c.contorno.length,
                 ox: c.origem[1], conj: (c.atributos.marcas || {}).conjunto, malha: !!ed.cena._geometriaChapa(c).geom }; });
      const n1 = doc.entidades.size; f.colocar(doc.get(u.id), 1500, 1);
      const nu = [...doc.entidades.values()].filter(e => e.tipo === 'chapa' && e.atributos && e.atributos.enrijecedor_de === u.id).length;
      return { novas: n1 - n0, geo, nu };""")
    print("     enrijecedor W:", r and r["geo"])
    g = (r or {}).get("geo") or []
    ok(r and r["novas"] == 2 and all(x["n"] == 6 and x["esp"] == 6.3 and x["conj"] == "V1" and x["malha"] for x in g),
       f"W 250: duas chapas de 6,3 com o canto chanfrado (6 vértices), no conjunto da viga: {r and r['novas']}")
    ok(g and all(abs(x["L"] - (73 - 3.05)) < 3 and abs(x["H"] - (258 - 2 * 9.1)) < 3 for x in g),
       f"W 250: da face da alma à borda da mesa (~70) e entre as faces de dentro das mesas (~240): {[(round(x['L'], 1), round(x['H'], 1)) for x in g]}")
    ok(r and r["nu"] == 1, f"U: só do lado das mesas (as costas da alma não levam): {r and r['nu']}")
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
