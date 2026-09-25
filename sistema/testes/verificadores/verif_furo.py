# -*- coding: utf-8 -*-
"""Editor 3D: ferramenta Furo — carrega, diâmetro digitado (14, M12), painel com os
diâmetros do modelo, furo na alma da barra P80 vira o marcador (camada Furos,
IfcOpeningElement, não exportado), furo na chapa paramétrica entra em `furos`, Ctrl+Z."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8784
DADOS = tempfile.mkdtemp(prefix="metalica_furo_")
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_furo_")
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
    ok(aba.avaliar("window.editor.ferramentas.has('furo')"), "ferramenta Furo carregada")
    ok(aba.avaliar("window.editor.atalhos.get('f')") == "furo", "atalho F")
    ok(aba.avaliar("window.editor.ativarFerramenta('furo')"), "ativou")
    aba.avaliar("window.editor.ativa.onValor('17,5'); 1")
    ok(aba.avaliar("window.editor.ativa.diametro") == 17.5, "diâmetro digitado 17,5: " + str(aba.avaliar("window.editor.ativa.diametro")))
    aba.avaliar("window.editor.ativa.onValor('M12'); 1")
    ok(aba.avaliar("window.editor.ativa.diametro") == 13, "M12 dá o furo de 13")
    aba.drenar(0.8)
    txt = aba.avaliar("window.editor.el.props.textContent")
    ok("Furo a fazer" in txt and "Já usados no modelo" in txt and "Ø13" in txt, "painel do furo: " + txt[:160])
    aba.avaliar("window.editor.ativa._definir(14); 1")
    # a alma da P80: o marcador nasce na face, com a profundidade da parede e o eixo para dentro
    r = json.loads(aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, doc = ed.documento;
      const e = [...doc.entidades.values()].find(x => x.atributos && x.atributos.marcas && x.atributos.marcas.posicao === 'P80');
      const vs = e.vertices; const c = [0,1,2].map(i => vs.reduce((s, v) => s + v[i], 0) / vs.length);
      const n0 = doc.entidades.size;
      ed.ativa.onPonto({ entidade: e.id, ponto: c, normal: [0, 1, 0] });
      const novo = [...doc.entidades.values()].find(x => x.atributos && x.atributos.furo);
      const fu = novo && novo.atributos.furo;
      return [doc.entidades.size - n0, novo ? novo.camada : null, novo ? novo.atributos.tipo_ifc : null, novo ? novo.atributos.exportar : null,
              fu ? fu.d : null, fu ? fu.eixo.map(v => Math.round(v * 100) / 100) : null, fu ? Math.round(fu.profundidade * 10) / 10 : null, novo ? novo.vertices.length : 0];
    })())"""))
    ok(r[0] == 1 and r[1] == "Furos" and r[2] == "IfcOpeningElement" and r[3] is False and r[4] == 14 and r[7] == 32, f"marcador criado: {r}")
    ok(r[5] == [0, -1, 0] and r[6] is not None and 0 < r[6] <= 60, f"eixo para dentro da face e profundidade da parede: {r[5]} {r[6]}")
    ok(aba.avaliar("(window.editor.desfazer(), [...window.editor.documento.entidades.values()].every(x => !(x.atributos && x.atributos.furo)))"), "Ctrl+Z desfaz")
    # furo de verdade na malha: caixa 1000 × 100 × 6 (uma chapa deitada), clique na face de
    # cima com o índice da face → a face e a de trás ganham o laço costurado e a parede o cilindro
    r = json.loads(aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, doc = ed.documento;
      const caixa = (x0, y0, z0, x1, y1, z1, nome) => { const v = [];
        for (const z of [z0, z1]) for (const [x, y] of [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]) v.push([x, y, z]);
        return doc.add({ tipo: 'solido', nome, camada: 'Chapas', vertices: v,
          faces: [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]], arestas_vivas: [], atributos: { marcas: { nome } } }); };
      const cima = caixa(60000, 0, 100, 61000, 100, 106, 'CIMA');
      const baixo = caixa(60000, -200, 50, 61000, 300, 100, 'BAIXO');      // parede de 50: a face de trás é reconhecida
      ed.ativarFerramenta('furo');
      ed.ativa._definir(14);
      ed.ativa._caixas = new Map();
      const iFace = cima.faces.findIndex(f => f.every(i => cima.vertices[i][2] === 106));
      const nv = cima.vertices.length, nf = cima.faces.length;
      ed.ativa.onPonto({ entidade: cima.id, ponto: [60300, 50, 106], normal: [0, 0, 1], face: iFace });
      const e = doc.get(cima.id);
      const furos = ed.ferramentas.get('furo') ? null : null;
      return [e.vertices.length - nv, e.faces.length - nf, (e.atributos.furos_editor || []).length, e.faces[iFace].length, cima.id, baixo.id];
    })())"""))
    ok(r[0] == 32 and r[1] == 16 and r[2] == 1 and r[3] == 4 + 16 + 2, f"furo aberto na malha (32 vértices, 16 faces da parede, laço costurado): {r}")
    id_cima, id_baixo = r[4], r[5]
    # os furos da malha são lidos de volta; um furo na peça de baixo alinha o de cima
    bruto = aba.avaliar("""JSON.stringify((() => { try {
      const ed = window.editor, doc = ed.documento;
      const cima = doc.get('%s'), baixo = doc.get('%s');
      const iTopo = baixo.faces.findIndex(f => f.every(i => baixo.vertices[i][2] === 100));
      ed.ativa.onPonto({ entidade: baixo.id, ponto: [60700, 40, 100], normal: [0, 0, 1], face: iTopo });
      ed.ativa._caixas = new Map();
      const aj = ed.ativa.ajustar({ entidade: cima.id, ponto: [60706, 44, 106], normal: [0, 0, 1] }, [0, 0, 1]);
      const longe = ed.ativa.ajustar({ entidade: cima.id, ponto: [60800, 20, 106], normal: [0, 0, 1] }, [0, 0, 1]);
      return [aj.ponto.map(Math.round), longe.ponto.map(Math.round), doc.get(baixo.id).atributos.furos_editor.length];
    } catch (e) { return { erro: String(e), stack: String(e.stack).slice(0, 400) }; } })())""" % (id_cima, id_baixo))
    r = json.loads(bruto) if bruto else {"erro": "avaliação sem resultado"}
    if isinstance(r, dict):
        print("     ERRO JS:", r)
        r = [None, None, None]
    # o furo de baixo foi para y = 50 (a linha de centro da peça larga prendeu o clique em 40); o de cima
    # cai em x = 60700 (o furo) e y = 50 (o furo e a linha de centro da terça coincidem)
    ok(r[0] == [60700, 50, 106] and r[2] == 1, f"perto do furo de baixo o furo de cima prende no alinhamento: {r}")
    ok(r[1] == [60800, 20, 106], f"longe dele fica onde clicou: {r[1]}")
    ok(aba.avaliar("(window.editor.desfazer(), window.editor.desfazer(), [...window.editor.documento.entidades.values()].every(x => !(x.atributos && x.atributos.furos_editor)))"), "Ctrl+Z devolve as malhas")
    # chapa paramétrica: o furo entra na própria chapa
    r = json.loads(aba.avaliar("""JSON.stringify((() => {
      const ed = window.editor, doc = ed.documento;
      const ch = doc.add({ tipo: 'chapa', origem: [70000, 0, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
                           contorno: [[0, 0], [200, 0], [200, 120], [0, 120]], espessura: 6.3, centrada: true, furos: [], camada: 'Chapas' });
      ed.ativarFerramenta('furo');
      ed.ativa._definir(18);
      ed.ativa.onPonto({ entidade: ch.id, ponto: [70050, 60, 3.15], normal: [0, 0, 1] });
      const f = doc.get(ch.id).furos;
      return [f.length, f[0] ? [Math.round(f[0].x), Math.round(f[0].y), f[0].diametro] : null];
    })())"""))
    ok(r[0] == 1 and r[1] == [50, 60, 18], f"furo na chapa paramétrica entra em furos: {r}")
    foto(aba, "_furo.png")
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
