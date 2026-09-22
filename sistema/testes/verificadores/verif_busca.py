# -*- coding: utf-8 -*-
"""Editor 3D: pesquisa de peças, painel com posição/comprimento/massa, cores por posição sem repetir."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8779
DADOS = tempfile.mkdtemp(prefix="metalica_busca_")
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_busca_")
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
    # pesquisa
    r = aba.avaliar("JSON.stringify((() => { const r = window.editor.pesquisarPecas('U150'); return [r.total, r.grupos.length, r.grupos.slice(0, 3).map(g => [g.chave, g.ids.length, g.detalhe])]; })())")
    r = json.loads(r)
    ok(r[0] > 10 and r[1] >= 3, f"pesquisa 'U150': {r[0]} peças em {r[1]} grupos: {r[2]}")
    r2 = json.loads(aba.avaliar("JSON.stringify((() => { const r = window.editor.pesquisarPecas('P36'); return [r.total, r.grupos.map(g => g.chave)]; })())"))
    ok(r2[0] == 168 and r2[1] == ["P36"], f"pesquisa 'P36': {r2}")
    r3 = json.loads(aba.avaliar("JSON.stringify((() => { const r = window.editor.pesquisarPecas('M2 plate'); return [r.total, r.grupos.length]; })())"))
    ok(r3[0] > 0, f"pesquisa 'M2 plate' (duas palavras): {r3}")
    # pela interface: digita, lista aparece, Enter seleciona e enquadra
    aba.avaliar("const c = document.getElementById('busca-campo'); c.focus(); c.value = 'P36'; c.dispatchEvent(new Event('input')); 1")
    aba.drenar(0.6)
    ok(aba.avaliar("!document.getElementById('busca-resultados').hidden && document.querySelectorAll('#busca-resultados .item').length === 1"), "lista de resultados aparece com 1 grupo")
    foto(aba, "busca_1.png")
    aba.avaliar("document.getElementById('busca-campo').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); 1")
    aba.drenar(0.5)
    ok(aba.avaliar("window.editor.selecao.ids.size") == 168, "Enter selecionou as 168 peças P36")
    # painel: posição, comprimento, massa de um U150
    ids = json.loads(aba.avaliar("JSON.stringify(window.editor.pesquisarPecas('M14').ids.slice(0, 1))"))
    aba.avaliar(f"window.editor.selecao.definir({json.dumps(ids)}); 1"); aba.drenar(0.8)
    painel = aba.avaliar("document.querySelector('#painel-propriedades, .painel-propriedades, [data-painel=\"propriedades\"]')?.textContent || document.body.textContent")
    ok("Posição" in painel and "Comprimento" in painel and "5.105" in painel.replace("5105", "5.105") and "Massa" in painel, "painel mostra posição, comprimento (5105 mm) e massa")
    foto(aba, "busca_2_painel.png")
    # cores por posição: uma cor por posição, sem repetir
    aba.avaliar("window.editor.corPor = 'posicao'; window.editor._aplicarCorPor(); window.editor._agendarPaineis('camadas'); 1"); aba.drenar(1.0)
    n, distintas = json.loads(aba.avaliar("JSON.stringify((() => { const c = window.editor._coresGrupo; return c ? [c.size, new Set(c.values()).size] : [0, 0]; })())"))
    ok(n >= 150 and distintas == n, f"cores por posição: {n} posições, {distintas} cores distintas")
    foto(aba, "busca_3_cores.png")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
