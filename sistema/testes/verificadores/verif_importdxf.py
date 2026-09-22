# -*- coding: utf-8 -*-
"""CAD: importar DXF (a tesoura do exemplo) num desenho novo, desfazer, refazer."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8781
DADOS = tempfile.mkdtemp(prefix="metalica_idxf_")
os.makedirs(os.path.join(DADOS, "compressores"))
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_idxf_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/cad?projeto=compressores", limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && !!window.cad"): aba.drenar(0.5)
    ok(aba.avaliar("!!document.querySelector('[data-acao=\"importar-dxf\"]') && !!document.getElementById('arquivo-dxf')"), "menu e seletor de arquivo presentes")
    texto = open(os.path.join(SCR, "det2d", "exemplo_tesoura_import.dxf"), encoding="cp1252").read()
    aba.avaliar("window.__dxf = %s; 1" % json.dumps(texto))
    antes = aba.avaliar("window.cad.doc.tamanho")
    # chama a importação com um File construído em JS; aceita o diálogo automaticamente
    aba.avaliar("window.cad.importarDXF(new File([window.__dxf], 'tesoura.dxf', { type: 'application/dxf' })); 1")
    aba.drenar(1.0)
    ok(aba.avaliar("!!document.querySelector('dialog[open]')"), "diálogo de importação abriu")
    aba.avaliar("document.querySelector('dialog[open] .botao-ok').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and aba.avaliar("window.cad.doc.tamanho") <= antes: aba.drenar(0.5)
    n = aba.avaliar("window.cad.doc.tamanho")
    ok(n - antes > 300, f"importou {n - antes} objetos (tesoura do exemplo)")
    ok(aba.avaliar("window.cad.tela.selecao.size") == n - antes, "os objetos importados ficaram selecionados")
    aba.avaliar("window.cad.desfazer(); 1"); aba.drenar(0.3)
    ok(aba.avaliar("window.cad.doc.tamanho") == antes, "desfazer remove a importação")
    aba.avaliar("window.cad.refazer(); 1"); aba.drenar(0.3)
    ok(aba.avaliar("window.cad.doc.tamanho") == n, "refazer devolve")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
