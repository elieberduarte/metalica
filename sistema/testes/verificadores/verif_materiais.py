# -*- coding: utf-8 -*-
"""Rotas /materiais + tela: detalha o modelo dos compressores, abre a lista de materiais,
recalcula com barra de 12 m, gera o PDF e confere a navegação 3D → 2D na mesma janela."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8781
DADOS = tempfile.mkdtemp(prefix="metalica_mat_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "ME SOORO", "local": "", "responsavel": "Elieber",
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_mat_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    # 1) sem detalhamento: GET levanta do modelo na hora
    t0 = time.time()
    L = get("/api/projetos/compressores/materiais")
    ok(L["totais"]["pecas"] > 100 and L["perfis"] and L["chapas"] and L["conjuntos"],
       "GET /materiais levantou do modelo em %.1f s: %d peças, %d posições, %d perfis, %d chapas, %d conjuntos, %.0f kg" %
       (time.time() - t0, L["totais"]["pecas"], L["totais"]["posicoes"], len(L["perfis"]), len(L["chapas"]), len(L["conjuntos"]), L["totais"]["peso"]))
    ok(all(k in L["arquivos"] for k in ("json", "romaneio", "perfis", "chapas", "conjuntos", "html")), "arquivos gravados: %s" % sorted(L["arquivos"]))
    ok(L["projeto"]["nome"] == "Compressores" and L["projeto"]["slug"] == "compressores", "identificação do projeto na lista")
    p = get("/api/projetos")
    ok(any(x["slug"] == "compressores" and x.get("tem_materiais") for x in p), "gerenciador sabe que o projeto tem lista (tem_materiais)")
    for g in L["perfis"][:6]:
        print("       ", g["perfil"], g["material"], g["categoria"], g["pecas"], "pç", g["comprimento_m"], "m", g["peso"], "kg", g["barras"])
    for c in L["conjuntos"][:5]:
        print("       ", c["marca"], c["instancias"], "x", c["composicao_texto"], c["peso_unitario"], "kg")
    # 2) detalhar grava a lista de novo (com a regra das terças)
    r = post("/api/projetos/compressores/detalhar", {"grupos": ["chapas", "barras"]})
    ok("materiais" in r and "json" in r["materiais"], "rota /detalhar devolve os arquivos da lista: %s" % sorted(r["materiais"]))
    # 3) recalcular com barra de 12 m
    L12 = post("/api/projetos/compressores/materiais", {"barra": 12000})
    b6 = sum(g["barras"]["quantidade"] for g in L["perfis"]); b12 = sum(g["barras"]["quantidade"] for g in L12["perfis"])
    ok(all(g["barras"]["comprimento"] == 12000 for g in L12["perfis"]) and b12 < b6, "barra de 12 m: %d barras (6 m: %d)" % (b12, b6))
    # 4) PDF
    t0 = time.time()
    pdf = post("/api/projetos/compressores/materiais/pdf", {})
    ok(pdf["pdf"]["tamanho_kb"] > 20, "PDF gerado em %.1f s: %s kB" % (time.time() - t0, pdf["pdf"]["tamanho_kb"]))
    # 5) tela
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=1000, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1"); aba.console.clear()
    aba.navegar(base + "/materiais?projeto=compressores", limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.querySelectorAll('.materiais table').length >= 4"): aba.drenar(0.5)
    ok(aba.avaliar("document.querySelectorAll('.materiais table').length") >= 5, "tela mostra os quadros")
    ok(aba.avaliar("document.querySelector('#sub-projeto').textContent") == "Compressores", "cabeçalho com o nome do projeto")
    ok(aba.avaliar("document.querySelectorAll('#arquivos a').length") >= 6, "links dos arquivos (CSV, HTML, PDF)")
    foto(aba, "_materiais.png")
    aba.avaliar("document.querySelector('#filtro').value = 'P36'; document.querySelector('#filtro').dispatchEvent(new Event('input')); 1")
    vis = aba.avaliar("[...document.querySelectorAll('.materiais tbody tr')].filter(tr => !tr.classList.contains('oculta')).length")
    ok(0 < vis < 40, "filtro 'P36' deixa %d linhas visíveis" % vis)
    aba.avaliar("document.querySelector('#filtro').value = ''; document.querySelector('#filtro').dispatchEvent(new Event('input')); 1")
    # ordenar por peso
    aba.avaliar("[...document.querySelectorAll('.materiais th')].find(t => t.textContent.startsWith('Peso (kg)')).click(); 1")
    ok(aba.avaliar("document.querySelector('.materiais th.ordem-asc, .materiais th.ordem-desc') !== null"), "clique no cabeçalho ordena")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erros no console da tela: %s" % erros[:3])
    # 6) navegação: editor 3D → CAD na mesma janela (sem window.open)
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("window.editor && window.editor.projeto === 'compressores' && window.editor.documento && window.editor.documento.tamanho > 10"): aba.drenar(1.0)
    aba.avaliar("window.__aberto = null; window.open = (u) => { window.__aberto = u; return null; }; window.editor._abrirCAD(); 1")
    t0 = time.time()
    while time.time() - t0 < 20 and not aba.avaliar("location.pathname === '/cad'"): aba.drenar(0.5)
    ok(aba.avaliar("location.pathname === '/cad' && location.search.includes('projeto=compressores')"), "Desenho 2D troca de tela na mesma janela (%s)" % aba.avaliar("location.pathname + location.search"))
    t0 = time.time()
    while time.time() - t0 < 20 and not aba.avaliar("document.body.dataset.pronto === '1'"): aba.drenar(0.5)
    ok(aba.avaliar("document.querySelector('#link-editor').getAttribute('href')") == "/editor?projeto=compressores", "CAD tem o link de volta ao modelo 3D")
    ok(aba.avaliar("!!document.querySelector('[data-acao=materiais]')"), "CAD tem 'Lista de materiais…' no menu")
    aba.avaliar("document.querySelector('[data-acao=materiais]').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 20 and not aba.avaliar("location.pathname === '/materiais'"): aba.drenar(0.5)
    ok(aba.avaliar("location.pathname === '/materiais'"), "menu do CAD leva à lista de materiais")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(perfil, ignore_errors=True)
print("\n%d falha(s)." % len(falhas))
sys.exit(1 if falhas else 0)
