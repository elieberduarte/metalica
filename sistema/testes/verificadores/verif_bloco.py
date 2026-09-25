# -*- coding: utf-8 -*-
"""Bloco paramétrico: duplo clique no 3D → detalhe no CAD; furos editados → chapas do
modelo; Ver no 3D; lista de desenhos no menu do CAD; Copiar com base fixa; Offset em arco."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8783
DADOS = tempfile.mkdtemp(prefix="metalica_bl_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
def get(rota):
    return json.load(urllib.request.urlopen(base + rota, timeout=600))
def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
def chapas_p77():
    doc = get("/api/projetos/compressores/modelo")
    ents = doc.get("documento", doc).get("entidades", [])
    return [e for e in ents if e.get("tipo") == "chapa" and ((e.get("atributos") or {}).get("marcas") or {}).get("posicao") == "P77"]
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_bl_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    # 1) rota do detalhe por peça
    t0 = time.time()
    r = post("/api/projetos/compressores/detalhar-posicao", {"marca": "P77"})
    ok(r["convertidas"] == 18 and r["editavel"] and r["furos"] == 4, "detalhar-posicao P77 em %.1f s: %s" % (time.time() - t0, {k: r[k] for k in ("nome", "convertidas", "editavel", "furos")}))
    ok(len(chapas_p77()) == 18, "modelo tem 18 chapas paramétricas P77")
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1"); aba.console.clear()
    # 2) CAD no detalhe: apaga um furo, desenha um redondo, aplica
    aba.navegar(base + "/cad?projeto=compressores&desenho=" + r["nome"], limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 5"): aba.drenar(0.5)
    ok(aba.avaliar("window.cad.doc.metadados.detalhe_posicao.marca") == "P77", "CAD abriu o detalhe editável de P77")
    n_furos = aba.avaliar("[...window.cad.doc.entidades.values()].filter(e => e.camada === 'FURO').length")
    ok(n_furos == 4, "4 furos como entidades marcadas (%s)" % n_furos)
    foto(aba, "_detalhe_p77.png")
    aba.avaliar("""(() => { const f = [...window.cad.doc.entidades.values()].filter(e => e.camada === 'FURO'); window.cad.selecionar([f[0].id]); window.cad.apagarSelecao();
                  window.cad.doc.add({ tipo: 'circulo', camada: 'FURO', centro: [75, 61.5], raio: 8.75 }); return 1; })()""")
    aba.avaliar("window.cad.aplicarFuros(); 1"); aba.drenar(1.5)
    ok(aba.avaliar("!!document.querySelector('dialog[open]')"), "diálogo 'Aplicar furos' abriu")
    aba.avaliar("document.querySelector('dialog[open] .botao-ok').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and not any(len(c.get("furos", [])) == 4 and any("diametro" in f for f in c["furos"]) for c in chapas_p77()): aba.drenar(0.5)
    chs = chapas_p77()
    ok(all(len(c["furos"]) == 4 and sum(1 for f in c["furos"] if f.get("diametro")) == 1 for c in chs), "as 18 chapas do modelo receberam 3 oblongos + 1 redondo")
    aba.drenar(2.0)
    ok(aba.avaliar("[...window.cad.doc.entidades.values()].filter(e => e.camada === 'FURO' && e.tipo === 'circulo').length") == 1, "detalhe regenerado no CAD com o furo redondo")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erros no console do CAD: %s" % erros[:3])
    # 3) menu Desenho lista os desenhos salvos
    aba.avaliar("document.querySelector('.menu[data-menu=\"desenho\"] .menu-botao').click(); 1"); aba.drenar(1.5)
    n = aba.avaliar("document.querySelectorAll('#desenhos-salvos [data-desenho]').length")
    ok(n >= 1, "menu Desenho do CAD lista os desenhos salvos (%s)" % n)
    aba.avaliar("window.cad._fecharMenus(); 1")
    # 4) Copiar com ponto base fixo, Offset em arco
    res = aba.avaliar("""(() => { const l = window.cad.doc.add({ tipo: 'linha', camada: 'VISTA', a: [1000, 0], b: [1100, 0] });
        window.cad.selecionar([l.id]); window.cad.ativarFerramenta('copiar'); const f = window.cad.ferramenta;
        f.onPonto([1000, 0], {}); f.onPonto([1000, 100], {}); f.onPonto([1000, 200], {});
        const ys = [...window.cad.doc.entidades.values()].filter(e => e.tipo === 'linha' && e.a[0] === 1000).map(e => e.a[1]).sort((a, b) => a - b);
        const arc = window.cad.doc.add({ tipo: 'arco', camada: 'VISTA', centro: [2000, 0], raio: 100, inicio: 0, fim: 90 });
        window.cad.selecionar([]); window.cad.ativarFerramenta('offset'); const o = window.cad.ferramenta; o.alvo = arc; o.distancia = 10; o.onPonto([2500, 500], { px: [0, 0] });
        const raios = [...window.cad.doc.entidades.values()].filter(e => e.tipo === 'arco').map(e => e.raio).sort((a, b) => a - b);
        return JSON.stringify({ ys, raios, dist: o.distancia }); })()""")
    res = json.loads(res)
    ok(res["ys"] == [0, 100, 200], "Copiar: destinos medidos do mesmo ponto base → y = 0, 100, 200 (%s)" % res["ys"])
    ok(res["raios"] == [100, 110] and res["dist"] == 10, "Offset em arco: raio 110 e a distância fica para o próximo (%s)" % res)
    # 5) Ver no 3D
    aba.avaliar("window.cad.selecionar([]); window.cad.verNo3D(); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("location.pathname === '/editor' && window.editor && window.editor.documento && window.editor.documento.tamanho > 10 && window.editor.selecao.ids.size > 0"): aba.drenar(1.0)
    sel = aba.avaliar("window.editor.selecao.ids.size")
    ok(sel == 18, "Ver no 3D: editor abriu com as 18 chapas P77 selecionadas (%s)" % sel)
    foto(aba, "_ver3d_p77.png")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erros no console do editor (chapas com oblongos na cena): %s" % erros[:3])
    # 6) duplo clique numa peça → detalhe no CAD
    aba.avaliar("""(() => { const e = [...window.editor.documento.entidades.values()].find(x => x.atributos && x.atributos.marcas && x.atributos.marcas.posicao === 'P42'); window.editor.abrirDetalheDaPeca(e); return 1; })()""")
    # o detalhe é gerado no servidor antes de trocar de tela (location.href): na máquina
    # ocupada passa de 60 s. Espera o CAD ou o aviso de erro do editor, e mostra qual veio.
    erro_det = "(() => { const a = [...document.querySelectorAll('.aviso')].find(x => x.dataset.tipo === 'erro'); return a ? a.textContent : ''; })()"
    t0 = time.time()
    while time.time() - t0 < 240 and not aba.avaliar("(location.pathname === '/cad' && location.search.includes('detalhe-p42')) || (location.pathname === '/editor' && !!" + erro_det + ")"): aba.drenar(1.0)
    onde = aba.avaliar("location.pathname + location.search")
    ok(aba.avaliar("location.pathname === '/cad' && location.search.includes('detalhe-p42')"),
       "duplo clique na peça abre o CAD no detalhe em %.0f s (%s%s)" % (time.time() - t0, onde, (" — " + aba.avaliar(erro_det)) if onde.startswith("/editor") else ""))
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 5"): aba.drenar(0.5)
    ok(aba.avaliar("window.cad.doc.metadados.detalhe_posicao.marca") == "P42", "detalhe de P42 aberto")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(perfil, ignore_errors=True)
print("\n%d falha(s)." % len(falhas))
sys.exit(1 if falhas else 0)
