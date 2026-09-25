# -*- coding: utf-8 -*-
"""Rota /detalhar no projeto do cliente + diálogo do editor + CAD abrindo o desenho gerado."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = 8777
DADOS = tempfile.mkdtemp(prefix="metalica_det_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
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

chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_det_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    t0 = time.time()
    r = post("/api/projetos/compressores/detalhar", {})
    # as 162 marcas do IFC viram ~125 posições (as peças iguais de marcas diferentes se fundem)
    dt = time.time() - t0
    ok(100 <= r["posicoes"] <= 162 and r["pecas"] == 2705 and dt < 120,
       "rota detalhou em %.1f s: %s peças, %s posições, %s conjuntos, %s kg" % (dt, r["pecas"], r["posicoes"], r["conjuntos"], r["peso_total"]))
    grupos = [d["grupo"] for d in r["desenhos"]]
    ok({"tesouras", "chaparias", "localizacao", "completo"} <= set(grupos),
       "desenhos por família: %s" % [(d["nome"], d["entidades"]) for d in r["desenhos"]])
    ok(len(r["regra_tercas"]) >= 20, "regra das terças em %d posições" % len(r["regra_tercas"]))
    ok(os.path.exists(os.path.join(DADOS, "compressores", "detalhamento", "romaneio.csv")), "romaneio gravado")
    lista = json.load(urllib.request.urlopen(base + "/api/projetos/compressores/desenhos"))
    n_desenhos = len(r["desenhos"])
    ok(len(lista) == n_desenhos, "desenhos listados no projeto: %d" % len(lista))
    # de novo com substituir: continua o mesmo número
    r2 = post("/api/projetos/compressores/detalhar", {"grupos": ["chaparias"], "substituir": True})
    lista = json.load(urllib.request.urlopen(base + "/api/projetos/compressores/desenhos"))
    ok(len(lista) == n_desenhos and len(r2["desenhos"]) == 1, "repetir com substituir não duplica desenhos")

    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1"); aba.console.clear()
    # CAD abre o desenho de chaparias gerado
    nome = [d["nome"] for d in r["desenhos"] if d["grupo"] == "chaparias"][0]
    aba.navegar(base + f"/cad?projeto=compressores&desenho={nome}", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 50"): aba.drenar(0.5)
    n = aba.avaliar("window.cad.doc.tamanho")
    cotas = aba.avaliar("[...window.cad.doc.entidades.values()].filter(e => e.tipo === 'cota').length")
    ok(n > 100 and cotas > 30, f"CAD abriu o detalhamento de chapas: {n} objetos, {cotas} cotas editáveis")
    aba.avaliar("window.cad.tela.enquadrar(); 1"); aba.drenar(1.0); foto(aba, "det_1_chapas_cad.png")
    # zoom numa célula
    aba.avaliar("const c = window.cad.doc.metadados.celulas[3]; window.cad.tela.enquadrar([[c[0], c[1]], [c[2], c[3]]], 0.1); 1"); aba.drenar(1.0); foto(aba, "det_2_celula.png")
    # editor: diálogo Detalhar existe e dispara a rota
    aba.console.clear()
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("window.editor && window.editor.documento && window.editor.documento.entidades.size > 100"): aba.drenar(0.5)
    ok(aba.avaliar("!!document.querySelector('[data-acao=\"detalhar-pecas\"]')"), "item de menu 'Detalhar peças e conjuntos…' presente")
    # o editor abre o CAD na mesma janela (location.href), não numa janela nova
    aba.avaliar("window.editor.dialogoDetalharPecas(); 1")
    aba.drenar(1.0)
    aba.avaliar("document.querySelector('dialog[open] .botao-ok, dialog[open] button[value=ok], dialog[open] form button:last-child').click(); 1")
    t0 = time.time()
    u = ""
    while time.time() - t0 < 180:
        try:
            u = aba.avaliar("location.pathname + location.search") or ""
        except Exception:                                  # noqa: BLE001 — a página trocando
            u = ""
        if u.startswith("/cad?projeto=compressores&desenho="):
            break
        aba.drenar(1.0)
    ok(u.startswith("/cad?projeto=compressores&desenho="), f"diálogo do editor detalhou e abriu o CAD: {u}")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
