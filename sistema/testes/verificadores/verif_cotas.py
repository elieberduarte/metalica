# -*- coding: utf-8 -*-
"""Cotas associativas: mover um furo no CAD leva a cota da coluna junto; vínculo chapa → terça
gravado no projeto ao aplicar furos."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8787
DADOS = tempfile.mkdtemp(prefix="metalica_ct_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
def get(rota):
    return json.load(urllib.request.urlopen(base + rota, timeout=600))
def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"}), timeout=600))
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ct_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos/compressores/detalhar", {"grupos": ["chapas", "barras"]})
    nome = [d["nome"] for d in r["desenhos"] if "chapas" in d["nome"]][0]
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1"); aba.console.clear()
    aba.navegar(base + "/cad?projeto=compressores&desenho=" + nome, limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 50"): aba.drenar(0.5)
    # P1: chapa 400x120x13 com 2 furos a 150 (a cadeia de cotas cabe em 1:10). Move o primeiro furo 10 mm em x.
    rotulo = aba.avaliar("(window.cad.doc.metadados.detalhamento.editaveis || []).find(m => m.split(' / ').includes('P1')) || null")
    ok(rotulo is not None, "célula editável da P1 existe (%s)" % rotulo)
    res = aba.avaliar("""(() => { const rot = %s; const cad = window.cad;
        const furos = [...cad.doc.entidades.values()].filter(e => e.camada === 'FURO' && (e.atributos || {}).posicao === rot);
        const f = furos[0]; const cx = f.centro ? f.centro[0] : (Math.min(...f.vertices.map(p => p[0])) + Math.max(...f.vertices.map(p => p[0]))) / 2;
        const cotasAntes = [...cad.doc.entidades.values()].filter(e => e.tipo === 'cota' && e.modo === 'h' && (e.atributos || {}).posicao === rot && (Math.abs(e.p1[0] - cx) < 0.05 || Math.abs(e.p2[0] - cx) < 0.05)).map(e => e.id);
        cad.selecionar([f.id]); cad.ativarFerramenta('mover'); const m = cad.ferramenta;
        m.onPonto([0, 0], {}); m.onPonto([10, 0], {});
        const f2 = cad.doc.get(f.id); const cx2 = f2.centro ? f2.centro[0] : (Math.min(...f2.vertices.map(p => p[0])) + Math.max(...f2.vertices.map(p => p[0]))) / 2;
        const seguiram = cotasAntes.filter(id => { const e = cad.doc.get(id); return Math.abs(e.p1[0] - cx2) < 0.05 || Math.abs(e.p2[0] - cx2) < 0.05; }).length;
        return JSON.stringify({ furos: furos.length, cx, cx2, cotas: cotasAntes.length, seguiram }); })()""" % json.dumps(rotulo))
    res = json.loads(res)
    ok(res["cotas"] >= 1 and res["seguiram"] == res["cotas"] and abs(res["cx2"] - res["cx"] - 10) < 0.01, "cota da coluna do furo acompanhou o furo (%s)" % res)
    # P36 (chapinha do suporte): move um furo 10 mm em x e aplica: as terças ligadas recebem o ajuste (vínculo)
    aba.avaliar("window.cad.desfazer(); 1"); aba.drenar(0.5)
    rotulo = aba.avaliar("(window.cad.doc.metadados.detalhamento.editaveis || []).find(m => m.split(' / ').includes('P36')) || null")
    ok(rotulo is not None, "célula editável da P36 existe (%s)" % rotulo)
    aba.avaliar("""(() => { const rot = %s; const cad = window.cad; const f = [...cad.doc.entidades.values()].filter(e => e.camada === 'FURO' && (e.atributos || {}).posicao === rot)[0];
        cad.selecionar([f.id]); cad.ativarFerramenta('mover'); const m = cad.ferramenta; m.onPonto([0, 0], {}); m.onPonto([10, 0], {}); return 1; })()""" % json.dumps(rotulo))
    aba.avaliar("(() => { const rot = %s; const c = window.cad._contornoDe(rot); window.cad.selecionar([c.id]); window.cad.aplicarFuros(); return 1; })()" % json.dumps(rotulo)); aba.drenar(1.5)
    aba.avaliar("document.querySelector('dialog[open] .botao-ok').click(); 1")
    caminho = os.path.join(DADOS, "compressores", "detalhamento", "ajustes-furos.json")
    t0 = time.time()
    while time.time() - t0 < 60 and not os.path.exists(caminho): aba.drenar(0.5)
    aba.drenar(3.0)
    aj = json.load(open(caminho, encoding="utf-8")) if os.path.exists(caminho) else {}
    ok(len(aj) >= 1, "vínculo gravado: %d terça(s) ajustada(s) %s" % (len(aj), sorted(aj)[:6]))
    if aj:
        primeira = next(iter(aj.values()))
        print("       origem:", primeira.get("origem", "")[:90])
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erros no console: %s" % erros[:3])
    # o detalhamento seguinte das barras aplica o ajuste
    r2 = post("/api/projetos/compressores/detalhar", {"grupos": ["barras"]})
    rel = json.load(open(os.path.join(DADOS, "compressores", "detalhamento", "relatorio.json"), encoding="utf-8"))
    vinculadas = [p["marca"] for p in rel["posicoes"] if any("vinculada" in o for o in p.get("observacoes", []))]
    ok(len(vinculadas) >= 1, "detalhamento das barras aplicou a furação vinculada em %s" % vinculadas[:6])
finally:
    nav.kill(); srv.kill(); shutil.rmtree(perfil, ignore_errors=True)
print("\n%d falha(s)." % len(falhas))
sys.exit(1 if falhas else 0)
