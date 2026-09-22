# -*- coding: utf-8 -*-
"""Verificação headless: modelo importado do TecnoMETAL no editor, camadas por tipo,
ocultar Telhas, colorir por conjunto com legenda."""
import base64, json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, CONTAR_OBJETOS, _json, _porta_livre

porta = int(sys.argv[1]); base_url = f"http://localhost:{porta}"
chrome = next(c for c in CHROMES if os.path.exists(c))
porta_cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_grupos_")
proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader",
    "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
    f"--user-data-dir={perfil}", f"--remote-debugging-port={porta_cdp}", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
codigo = 0
def foto(aba, nome):
    png = aba.cmd("Page.captureScreenshot", format="png")["data"]
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(png))
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{porta_cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)
    aba.navegar(base_url + "/")
    aba.avaliar("localStorage.setItem('galpao.tema', 'claro'); 1")
    aba.console.clear()
    aba.navegar(base_url + "/editor", limite=30)
    aba.drenar(3.0)
    # abre o modelo salvo pelo importador (o mesmo caminho do menu Arquivo → Abrir)
    ok = aba.avaliar("(async () => { const r = await window.editor.api.abrir('compressores-ar');"
                     " window.editor.carregarDocumento(r.documento); return true; })()")
    print("abrir:", ok)
    t0 = time.time(); objetos = -1
    while time.time() - t0 < 120:
        aba.drenar(1.0); objetos = aba.avaliar(CONTAR_OBJETOS)
        if isinstance(objetos, int) and objetos > 4000: aba.drenar(4.0); break
    print("objetos:", objetos, "em %.0f s" % (time.time() - t0))
    camadas = aba.avaliar("JSON.stringify([...window.editor.documento.camadas.keys()])")
    print("camadas:", camadas)
    foto(aba, "grupos_1_importado.png")
    # oculta Telhas pelo botão do painel (o mesmo caminho do clique do usuário)
    r = aba.avaliar("(() => { const linhas = [...document.querySelectorAll('#painel-camadas .linha')];"
                    " const l = linhas.find(x => x.querySelector('.nome') && x.querySelector('.nome').textContent === 'Telhas');"
                    " if (!l) return 'sem linha Telhas'; l.querySelector('button.alternador').click(); return 'ok'; })()")
    print("ocultar Telhas:", r); aba.drenar(2.0)
    print("Telhas visível:", aba.avaliar("window.editor.documento.camadas.get('Telhas').visivel"))
    foto(aba, "grupos_2_sem_telhas.png")
    # colorir por conjunto pelo seletor
    r = aba.avaliar("(() => { const s = document.querySelector('#painel-camadas .cor-por select');"
                    " if (!s) return 'sem seletor'; s.value = 'conjunto'; s.dispatchEvent(new Event('change')); return 'ok'; })()")
    print("colorir por conjunto:", r); aba.drenar(3.0)
    print("grupos na legenda:", aba.avaliar("document.querySelectorAll('#painel-camadas .legenda-grupos .linha').length"),
          "| nota:", aba.avaliar("(document.querySelector('#painel-camadas .nota-grupos')||{}).textContent"))
    foto(aba, "grupos_3_por_conjunto.png")
    # clica num grupo da legenda: seleciona as peças dele
    r = aba.avaliar("(() => { const l = document.querySelectorAll('#painel-camadas .legenda-grupos .linha')[1];"
                    " if (!l) return 'sem linha'; l.dispatchEvent(new MouseEvent('dblclick', {bubbles:true})); return l.querySelector('.nome').textContent; })()")
    aba.drenar(2.0)
    print("grupo clicado:", r, "| selecionadas:", aba.avaliar("window.editor.selecao.ids.size"))
    foto(aba, "grupos_4_selecao_grupo.png")
    # volta ao padrão
    aba.avaliar("(() => { const s = document.querySelector('#painel-camadas .cor-por select'); s.value = 'padrao'; s.dispatchEvent(new Event('change')); return 1; })()")
    aba.drenar(2.0)
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    print("erros de JavaScript:", len(erros))
    for t, x in erros[:10]: print("  [%s] %s" % (t, x[:400]))
    codigo = 1 if erros else 0
    aba.ws.close()
finally:
    proc.terminate()
    try: proc.wait(timeout=10)
    except Exception: proc.kill()
sys.exit(codigo)
