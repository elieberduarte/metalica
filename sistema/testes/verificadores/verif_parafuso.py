# -*- coding: utf-8 -*-
"""Editor 3D: ferramenta Parafuso — carrega, põe um parafuso na alma de uma barra (P80) com o
tamanho digitado, e a chapa paramétrica aceita o Empurrar/Puxar num lado."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8783
DADOS = tempfile.mkdtemp(prefix="metalica_paraf_")
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
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_paraf_")
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
    ok(aba.avaliar("window.editor.ferramentas.has('parafuso')"), "ferramenta Parafuso carregada")
    ok(aba.avaliar("window.editor.ativarFerramenta('parafuso')"), "ativou")
    aba.avaliar("window.editor.ativa.onValor('M16x40'); 1")
    t = json.loads(aba.avaliar("JSON.stringify(window.editor.ativa.tamanho)"))
    ok(t["d"] == 16 and t["L"] == 40, f"tamanho digitado M16x40: {t}")
    # painel de propriedades: o parafuso a lançar, com a classe e os já usados no modelo
    aba.drenar(0.8)
    txt = aba.avaliar("window.editor.el.props.textContent")
    ok("Parafuso a lançar" in txt and "Já usados no modelo" in txt and "M12x35" in txt, "painel do parafuso: " + txt[:160])
    ok("porca/chumbador" in txt, "os fixadores sem tamanho do IFC (BOLT () 0x0) também aparecem, pela rosca da porca")
    t = json.loads(aba.avaliar("JSON.stringify(window.editor.ativa._usadosNoModelo().map(u => u.rotulo))"))
    print("     usados:", t, aba.avaliar("JSON.stringify(window.editor.ativa._usadosNoModelo().map(u => u.n))"))
    aba.avaliar("(() => { const s = [...window.editor.el.props.querySelectorAll('select')].find(x => [...x.options].some(o => o.value === 'A490')); s.value = 'A490'; s.dispatchEvent(new Event('change')); return 1; })()")
    ok(aba.avaliar("window.editor.ativa.nomeAtual") == "BOLT (A490) 16x40", "classe escolhida no painel vai para o nome: " + aba.avaliar("window.editor.ativa.nomeAtual"))
    # eixos da face: caixa 1000 × 100 × 50, clique a 6 mm da linha de centro da face de cima
    r = json.loads(aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor;
      const v = []; for (const z of [0, 50]) for (const [x, y] of [[0,0],[1000,0],[1000,100],[0,100]]) v.push([x + 90000, y, z]);
      const cx = ed.documento.add({ tipo: 'solido', nome: 'CAIXA', camada: 'Chapas', vertices: v,
        faces: [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]], arestas_vivas: [], atributos: {} });
      const aj = ed.ativa.ajustar({ entidade: cx.id, ponto: [90300, 56, 50], normal: [0, 0, 1] }, [0, 0, 1]);
      const longe = ed.ativa.ajustar({ entidade: cx.id, ponto: [90300, 85, 50], normal: [0, 0, 1] }, [0, 0, 1]);
      return [aj.ponto.map(Math.round), aj.extra.length, longe.ponto.map(Math.round)];
    })())"""))
    ok(r[0] == [90300, 50, 50] and r[1] >= 4, f"prende na linha de centro da face e desenha os eixos: {r}")
    ok(r[2] == [90300, 85, 50], f"longe do eixo fica onde clicou: {r[2]}")
    # peça de baixo: terça (aba de 60) em cima de um banzo atravessado de 50 mm de largura;
    # perto dos dois eixos, o parafuso vai para o cruzamento deles
    r = json.loads(aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, doc = ed.documento;
      const caixa = (x0, y0, z0, x1, y1, z1, nome) => { const v = [];
        for (const z of [z0, z1]) for (const [x, y] of [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]) v.push([x, y, z]);
        return doc.add({ tipo: 'solido', nome, camada: 'Vigas', vertices: v,
          faces: [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]], arestas_vivas: [],
          atributos: { marcas: { nome } } }); };
      const terca = caixa(80000, 0, 100, 81000, 60, 105, 'TERCA');
      caixa(80275, -500, 0, 80325, 500, 100, 'BANZO');
      ed.ativa._caixas = new Map();
      const aj = ed.ativa.ajustar({ entidade: terca.id, ponto: [80304, 32, 105], normal: [0, 0, 1] }, [0, 0, 1]);
      const longe = ed.ativa.ajustar({ entidade: terca.id, ponto: [80340, 32, 105], normal: [0, 0, 1] }, [0, 0, 1]);
      return [aj.ponto.map(Math.round), aj.extra.length, longe.ponto.map(Math.round), longe.extra.length];
    })())"""))
    ok(r[0] == [80300, 30, 105] and r[1] >= 6, f"eixo da terça e do banzo de baixo: vai ao cruzamento {r[:2]}")
    ok(r[2][0] == 80340 and r[3] >= 6, f"longe do eixo do banzo: mostra a distância e não prende {r[2:]}")
    aba.avaliar("window.editor.ativa._definir({ d: 16, L: 40, classe: '' }); 1")
    # ponto no meio da P80, normal pela menor extensão (a alma)
    r = aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, doc = ed.documento;
      const e = [...doc.entidades.values()].find(x => x.atributos && x.atributos.marcas && x.atributos.marcas.posicao === 'P80');
      const vs = e.vertices; const c = [0,1,2].map(i => vs.reduce((s, v) => s + v[i], 0) / vs.length);
      const n0 = doc.entidades.size;
      ed.ativa.onPonto({ entidade: e.id, ponto: c, normal: [0, 1, 0] });
      const novo = [...doc.entidades.values()].find(x => x.atributos && x.atributos.criado_no_editor);
      return [doc.entidades.size - n0, novo ? novo.camada : null, novo ? novo.atributos.tipo_ifc : null, novo ? novo.vertices.length : 0];
    })())""")
    r = json.loads(r)
    ok(r[0] == 1 and r[1] == "Parafusos" and r[2] == "IfcMechanicalFastener" and r[3] == 48, f"parafuso criado: {r}")
    ok(aba.avaliar("(window.editor.desfazer(), [...window.editor.documento.entidades.values()].every(x => !(x.atributos && x.atributos.criado_no_editor)))"), "Ctrl+Z desfaz")
    # empurrar/puxar na chapa P77: lado do contorno anda 20 mm
    r = aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, doc = ed.documento;
      // chapa paramétrica de teste, 150 × 120 × 6,3, deitada
      const ch = doc.add({ tipo: 'chapa', origem: [0, 0, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
                           contorno: [[0, 0], [150, 0], [150, 120], [0, 120]], espessura: 6.3, centrada: true, furos: [], camada: 'Chapas' });
      ed.ativarFerramenta('pushpull');
      const [a, b] = [ch.contorno[0], ch.contorno[1]];
      const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
      const p = [0,1,2].map(i => ch.origem[i] + ch.eixo_x[i] * mx + ch.eixo_y[i] * my);
      const antes = JSON.stringify(ch.contorno);
      ed.ativa.iniciar({ entidade: ch.id, ponto: p, normal: [0, 0, 1] });
      ed.ativa.aplicar(20);
      const depois = doc.get(ch.id).contorno;
      const L = (q, r) => Math.hypot(q[0] - r[0], q[1] - r[1]);
      return [antes !== JSON.stringify(depois), Math.round(L(depois[1], depois[2]) - L(JSON.parse(antes)[1], JSON.parse(antes)[2]))];
    })())""")
    ok(json.loads(r)[0] is True and json.loads(r)[1] == 20, f"chapa esticada 20 mm pelo lado: {r}")
    # chapa: arestas das duas faces e as verticais (4 lados → 12 arestas), para o snap
    r = json.loads(aba.avaliar("""JSON.stringify((() => {
      const doc = window.editor.documento;
      const ch = [...doc.entidades.values()].find(x => x.tipo === 'chapa');
      return ch ? [ch.contorno.length, doc.constructor.name] : null;
    })())"""))
    ok(r is not None, f"chapa de teste existe: {r}")
    # Shift sobre uma aresta inclinada trava paralelo a ela; o Mover anda nessa direção
    r = aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, inf = ed.inferencia;
      ed.ativarFerramenta('mover');
      inf.definirAncora([0, 0, 0]);
      inf.ultimo = { tipoSnap: 'sobre_aresta', aresta: [[0, 0, 0], [1000, 0, 200]] };
      const tratou = inf.onTecla({ type: 'keydown', key: 'Shift' });
      const trava = inf.travado, desc = inf.descricaoTrava;
      ed.ativa.base = [0, 0, 0];
      ed.ativa.onMover({ ponto: [500, 300, 0] }, {});
      const d = ed.ativa.delta;
      inf.onTecla({ type: 'keyup', key: 'Shift' });
      return [tratou, trava, desc, d.map(v => Math.round(v)), inf.travado];
    })())""")
    r = json.loads(r)
    # projeção de (500, 300, 0) na direção (1000, 0, 200): k = 500000/1040000 → (481, 0, 96)
    ok(r[0] and r[1] == "aresta" and r[3] == [481, 0, 96] and r[4] is None, f"Shift trava paralelo à aresta e o Mover segue: {r}")
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
