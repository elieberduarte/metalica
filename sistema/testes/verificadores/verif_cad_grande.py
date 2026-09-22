# -*- coding: utf-8 -*-
"""Headless: o CAD abre um desenho de 3 vistas do modelo inteiro (~160 mil objetos)? Quanto demora um quadro?"""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = 8775
DADOS = tempfile.mkdtemp(prefix="metalica_cadg_")
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

chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cadg_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    t0 = time.time()
    r = post("/api/projetos/compressores/vista2d", {"vistas": [{"padrao": k, "rotular": False} for k in ("frente", "topo", "esquerda", "direita", "tras")], "desenho": "Vistas gerais"})
    ok(len(r["vistas"]) == 5, "rota gerou as 5 vistas pelo servidor em %.1f s" % (time.time() - t0))
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    t0 = time.time()
    aba.navegar(base + "/cad?projeto=compressores&desenho=vistas-gerais", limite=120)
    while time.time() - t0 < 180 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 100"): aba.drenar(0.5)
    n = aba.avaliar("window.cad.doc.tamanho")
    ok(isinstance(n, int) and n > 100000, f"CAD abriu o desenho com {n} objetos em {time.time() - t0:.1f} s")
    msi = aba.avaliar("(() => { window.cad.doc._grade = null; const t = performance.now(); const g = window.cad.doc._indice(); return [performance.now() - t, g.celulas.size, [...g.celulas.values()].reduce((s, c) => s + c.ids.size, 0)]; })()")
    print("        índice espacial: %.0f ms, %d células, %d inserções" % tuple(msi))
    # tempo de um quadro (redesenho completo) e de um zoom
    ms = aba.avaliar("(() => { const t = performance.now(); window.cad.tela.desenhar(); return performance.now() - t; })()")
    ok(isinstance(ms, (int, float)) and ms < 1500, "redesenho completo em %.0f ms" % ms)
    ms2 = aba.avaliar("(() => { const t = performance.now(); window.cad.tela.zoom(1.3, [700, 450]); window.cad.tela.desenhar(); return performance.now() - t; })()")
    print("        zoom + redesenho: %.0f ms" % ms2)
    # quadro com só o cursor mudando (o que acontece a cada movimento do mouse): vem do cache
    ms4 = aba.avaliar("(() => { window.cad.tela.cursor = [1234, 567]; const t = performance.now(); window.cad.tela.desenhar(); return performance.now() - t; })()")
    ok(ms4 < 60, "quadro só com o cursor movido (cache) em %.0f ms" % ms4)
    # seleção muda → cache refeito; depois quadro barato de novo
    aba.avaliar("window.cad.selecionar([[...window.cad.doc.entidades.keys()][0]]); window.cad.tela.desenhar(); 1")
    ms5 = aba.avaliar("(() => { window.cad.tela.cursor = [1300, 600]; const t = performance.now(); window.cad.tela.desenhar(); return performance.now() - t; })()")
    ok(ms5 < 60, "quadro após seleção, de novo pelo cache, em %.0f ms" % ms5)
    # passar o mouse sobre um objeto (realce) não refaz o cache
    ms6 = aba.avaliar("(() => { window.cad.tela.realce = [...window.cad.doc.entidades.keys()][5]; const t = performance.now(); window.cad.tela.desenhar(); return performance.now() - t; })()")
    ok(ms6 < 60, "quadro com realce (hover) pelo cache em %.0f ms" % ms6)
    # pan: quadro aproximado imediato; definitivo depois de parado
    ms7 = aba.avaliar("(() => { window.cad.tela.arrastar([40, 25]); const t = performance.now(); window.cad.tela.desenhar(); return performance.now() - t; })()")
    ok(ms7 < 60, "pan: quadro aproximado em %.0f ms" % ms7)
    aba.drenar(0.5)
    ok(aba.avaliar("window.cad.tela._cache.vp.x === window.cad.tela.vp.x"), "quadro definitivo refeito depois do pan parar")
    print("        render completo: %.0f ms, %s desenhadas + %s como ponto" % tuple(aba.avaliar("[window.cad.tela._cache.duracao, window.cad.tela._cache.desenhadas, window.cad.tela._cache.pontos]")))
    # zoom perto: poucas entidades desenhadas
    aba.avaliar("window.cad.tela.zoom(40, [700, 450]); window.cad.tela.desenhar(); 1")
    des = aba.avaliar("window.cad.tela._cache.desenhadas")
    ok(des < n / 4, "com zoom aproximado só %s dos %s objetos entram no quadro" % (des, n))
    aba.avaliar("window.cad.tela.enquadrar(); window.cad.tela.desenhar(); 1")
    px = aba.avaliar("JSON.stringify(window.cad.tela.paraTela([1000, 1000]))")
    ms3 = aba.avaliar(f"(() => {{ const t = performance.now(); window.cad.snap.resolver({px}); return performance.now() - t; }})()")
    ok(ms3 < 300, "snap num ponto em %.0f ms" % ms3)
    aba.drenar(1.0); foto(aba, "cad_5_vistas_gerais.png")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:8]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
