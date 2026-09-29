# -*- coding: utf-8 -*-
"""Rota /pranchas + diálogo do CAD: monta as pranchas do detalhamento lado a lado num desenho só
("Pranchas", 28/09) e abre esse desenho."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8780
DADOS = tempfile.mkdtemp(prefix="metalica_pr_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "ME SOORO", "local": "", "responsavel": "Elieber",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_pr_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    # grupos por família (0.7.22): as chapas estão no desenho "chaparias" (era "chapas")
    r = post("/api/projetos/compressores/detalhar", {"grupos": ["chaparias", "tercas"]})
    nomes = [d["nome"] for d in r["desenhos"]]
    chaparias = next(d["nome"] for d in r["desenhos"] if d["grupo"] == "chaparias")
    t0 = time.time()
    p = post("/api/projetos/compressores/pranchas", {"desenhos": nomes, "formato": "A1", "carimbo": {"revisao": "01"}})
    # sem folha de índice (28/09): a relação das pranchas vai na faixa da primeira, e as faixas das
    # outras recebem as células pequenas — toda prancha tem células
    cel = [x["celulas"] for x in p["pranchas"]]
    ok(len(p["pranchas"]) >= 1 and sum(cel) >= 30 and all(c > 0 for c in cel),
       "rota montou %d pranchas A1 em %.1f s (células por prancha): %s" % (len(p["pranchas"]), time.time() - t0, [(x["titulo"], x["celulas"]) for x in p["pranchas"]]))
    lista = json.load(urllib.request.urlopen(base + "/api/projetos/compressores/desenhos"))
    n1 = len(lista)
    p2 = post("/api/projetos/compressores/pranchas", {"desenhos": nomes, "formato": "A0"})
    lista = json.load(urllib.request.urlopen(base + "/api/projetos/compressores/desenhos"))
    junto = next((d for d in lista if d["nome"] == p2["desenho"]), None)
    ok(len(lista) == 3 and junto is not None and junto.get("pranchas") == len(p2["pranchas"]),
       "as pranchas lado a lado num desenho só, e substituir apagou o anterior (%d desenhos agora; \"%s\" com %s folhas A0)"
       % (len(lista), p2["desenho"], junto and junto.get("pranchas")))
    try:
        post("/api/projetos/compressores/pranchas", {"desenhos": [p2["desenho"]]})
        ok(False, "prancha de prancha devia falhar")
    except urllib.error.HTTPError as e:
        ok(e.code == 400, "montar prancha a partir de uma prancha é recusado")
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1"); aba.console.clear()
    aba.navegar(base + "/cad?projeto=compressores&desenho=" + chaparias, limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 50"): aba.drenar(0.5)
    # seleciona duas células (P36 e P12) e monta só com elas
    aba.avaliar("window.cad.selecionar([...window.cad.doc.entidades.values()].filter(e => e.atributos && ['P36', 'P12'].includes(e.atributos.posicao)).map(e => e.id)); 1")
    aba.avaliar("window.cad.dialogoPranchas(); 1"); aba.drenar(1.5)
    ok(aba.avaliar("[...document.querySelectorAll('dialog[open] label.linha')].some(l => l.textContent.includes('2 peça(s) selecionada(s)'))"), "diálogo oferece 'só as peças selecionadas' com as 2 posições")
    aba.avaliar("document.querySelector('dialog[open] .botao-ok').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 120 and not aba.avaliar("document.title.startsWith('Prancha')"): aba.drenar(1.0)
    # as chapas ficam no quadro CHAPAS, que pode cair noutra prancha: olha todas. O título da
    # célula agora é o nome de produção (S.A.G.1 – 168x); a posição do modelo vai em "marca"
    # (peças iguais fundidas: "P36 / P40")
    cel = []
    for d in json.load(urllib.request.urlopen(base + "/api/projetos/compressores/desenhos")):
        if d.get("pranchas"):
            for meta in json.load(urllib.request.urlopen(base + "/api/projetos/compressores/desenhos/" + d["nome"]))["desenho"]["metadados"]["pranchas"]:
                cel += [(c["titulo"], c.get("marca")) for c in meta["celulas"] if c["fonte"] == chaparias]
    marcas = sorted(m for _, mc in cel for m in str(mc or "").split(" / ") if m in ("P36", "P12"))
    ok(len(cel) == 2 and marcas == ["P12", "P36"], f"do desenho de chaparias entraram só as células selecionadas (P36 e P12): {cel}")
    aba.avaliar("window.cad.selecionar([]); 1")
    aba.navegar(base + "/cad?projeto=compressores&desenho=" + chaparias, limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 50"): aba.drenar(0.5)
    aba.avaliar("window.cad.dialogoPranchas(); 1"); aba.drenar(1.5)
    campos = aba.avaliar("JSON.stringify([...document.querySelectorAll('dialog[open] input[type=text]')].map(i => i.value))")
    ok('"Compressores"' in campos and '"ME SOORO"' in campos and '"Elieber"' in campos, f"diálogo pré-preenche o carimbo com os dados do projeto: {campos}")
    aba.avaliar("document.querySelector('dialog[open] .botao-ok').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 120 and not aba.avaliar("document.title.startsWith('Prancha')"): aba.drenar(1.0)
    ok(aba.avaliar("document.title").startswith("Pranchas"), "diálogo montou e abriu o desenho das pranchas no CAD: %s" % aba.avaliar("document.title"))
    ok(aba.avaliar("window.cad.doc.escala") == 1, "prancha em escala 1 (mm de papel)")
    n_f = aba.avaliar("(window.cad.doc.metadados.pranchas || []).length")
    x_ult = aba.avaliar("(window.cad.doc.metadados.pranchas || []).slice(-1).map(f => f.origem[0])[0]")
    ok(n_f >= 2 and x_ult and x_ult > 800, "%d folhas lado a lado (a última começa em x = %s mm)" % (n_f, x_ult))
    # o clique na borda de uma folha pega a folha inteira (moldura e carimbo levam `folha`)
    ok(aba.avaliar("(() => { const e = [...window.cad.doc.entidades.values()].find(o => (o.atributos || {}).folha && (o.atributos || {}).prancha_numero === 2); return e ? window.cad.pecaDe(e.id).length > 20 : false; })()"),
       "a moldura da folha 2 é um grupo (o clique pega a folha inteira)")
    # PDF de todas as pranchas pelo CAD
    aba.avaliar("window.__aberto = null; window.open = (u) => { window.__aberto = u; return null; }; window.cad.pdfDasPranchas(); 1")
    t0 = time.time()
    while time.time() - t0 < 180 and not aba.avaliar("window.__aberto"): aba.drenar(1.0)
    u = aba.avaliar("window.__aberto")
    ok(u and u.endswith(".pdf"), f"PDF das pranchas gerado e aberto: {u}")
    if u:
        dados = urllib.request.urlopen(base + u).read()
        ok(dados[:5] == b"%PDF-" and len(dados) > 50000, "PDF servido pela rota /saida (%d kB)" % (len(dados) // 1024))
    aba.drenar(1.0); foto(aba, "prancha_cad.png")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
