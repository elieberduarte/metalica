# -*- coding: utf-8 -*-
"""Verificação do mapa de esforços no editor 3D (script temporário de sessão)."""
import base64, json, os, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, CHAVE_ESTADO, CONTAR_OBJETOS, _json, _porta_livre
from nucleo.modelo_galpao import DadosGalpao

porta = int(sys.argv[1]); saida = sys.argv[2]; tema = sys.argv[3] if len(sys.argv) > 3 else "claro"
base_url = f"http://localhost:{porta}"
dados = DadosGalpao(nome="Verificação do mapa").dict()
chrome = next(c for c in CHROMES if os.path.exists(c))
porta_cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_mapa_")
proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader",
    "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
    f"--user-data-dir={perfil}", f"--remote-debugging-port={porta_cdp}", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
codigo = 0
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{porta_cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)
    aba.navegar(base_url + "/")
    aba.avaliar(f"localStorage.setItem({json.dumps(CHAVE_ESTADO)}, {json.dumps(json.dumps(dados, ensure_ascii=False))});"
                f"localStorage.setItem('galpao.tema', {json.dumps(tema)}); 1")
    aba.console.clear()
    aba.navegar(base_url + "/editor?galpao=1", limite=30)
    t0 = time.time(); objetos = -1
    while time.time() - t0 < 60:
        aba.drenar(1.0); objetos = aba.avaliar(CONTAR_OBJETOS)
        if isinstance(objetos, int) and objetos > 0: aba.drenar(2.0); break
    print("objetos:", objetos)
    ok = aba.avaliar("window.editor.calcularEstrutura()")
    print("calcularEstrutura ->", ok)
    aba.drenar(3.0)
    estado = aba.avaliar("JSON.stringify({ligado: window.editor.analiseEstado && window.editor.analiseEstado.ligado,"
                         " mapa: !!window.editor.mapa, painel: !window.editor.el.painelAnalise.hidden,"
                         " elementos: Object.keys(window.editor.analise.elementos).length,"
                         " dica: document.body.innerText.match(/Análise pronta[^\n]*/) && document.body.innerText.match(/Análise pronta[^\n]*/)[0]})")
    print("estado:", estado)
    png = aba.cmd("Page.captureScreenshot", format="png")["data"]
    open(saida, "wb").write(base64.b64decode(png))
    # segunda captura: deformada e cargas ligadas, grandeza M, 3 pórticos
    aba.avaliar("(() => { const e = window.editor; e.analiseEstado.camadas.deformada = true;"
                " e.analiseEstado.camadas.cargas = true; e.analiseEstado.camadas.porticos = 3;"
                " e.analiseEstado.grandeza = 'M'; e._aplicarAoMapa(); e._agendarPaineis('analise'); return 1; })()")
    aba.drenar(2.0)
    png = aba.cmd("Page.captureScreenshot", format="png")["data"]
    open(saida.replace(".png", "_M.png"), "wb").write(base64.b64decode(png))
    # desliga e religa: nada deve quebrar
    aba.avaliar("window.editor.alternarAnalise()"); aba.drenar(1.0)
    aba.avaliar("window.editor.alternarAnalise()"); aba.drenar(1.0)
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    print("erros de JavaScript:", len(erros))
    for t, x in erros[:15]: print("  [%s] %s" % (t, x[:400]))
    codigo = 1 if erros else 0
    aba.ws.close()
finally:
    proc.terminate()
    try: proc.wait(timeout=10)
    except Exception: proc.kill()
sys.exit(codigo)
