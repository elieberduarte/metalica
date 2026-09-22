# -*- coding: utf-8 -*-
"""Headless: desenhos 2D salvos aparecem no menu do editor e no cartão do gerenciador; reabrir não gera nada."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = 8776
DADOS = tempfile.mkdtemp(prefix="metalica_reabrir_")
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

chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_reabrir_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    post("/api/projetos/compressores/vista2d", {"vista": {"origem": [0, 30000, 0], "normal": [0, 1, 0], "profundidade": 1500, "cortar": True, "nome": "Corte tesoura", "tipo": "corte"}, "desenho": "Corte tesoura"})
    post("/api/projetos/compressores/vista2d", {"vistas": [{"padrao": "frente"}], "desenho": "Vistas gerais"})
    lista = json.load(urllib.request.urlopen(base + "/api/projetos"))
    p = [x for x in lista if x["slug"] == "compressores"][0]
    ok(sorted(d["nome"] for d in p["desenhos"]) == ["corte-tesoura", "vistas-gerais"], "resumo do projeto lista os 2 desenhos: %s" % [d["titulo"] for d in p["desenhos"]])
    # substituir: gera de novo com substituir=True → continua 1 vista, e o anterior vai para a lixeira
    r = post("/api/projetos/compressores/vista2d", {"vistas": [{"padrao": "topo"}], "desenho": "Vistas gerais", "substituir": True})
    d = json.load(open(os.path.join(DADOS, "compressores", "desenhos-2d", "vistas-gerais.desenho.json"), encoding="utf-8"))
    ok(len(d["vistas"]) == 1 and d["vistas"][0]["tipo"] == "topo", "substituir=True troca o desenho em vez de acrescentar")
    ok(any("vistas-gerais" in a for a in os.listdir(os.path.join(DADOS, ".lixeira"))), "o desenho anterior foi para a lixeira")

    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    # gerenciador: pílulas dos desenhos
    aba.navegar(base + "/", limite=30); aba.drenar(1.5)
    pil = aba.avaliar("JSON.stringify([...document.querySelectorAll('.pilula.desenho')].map(b => b.textContent))")
    ok("Corte tesoura" in pil and "Vistas gerais" in pil, f"cartão do projeto mostra os desenhos: {pil}")
    # editor: menu Desenho 2D lista os desenhos e abre o CAD
    aba.console.clear()
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("window.editor && window.editor.documento && window.editor.documento.entidades.size > 100"): aba.drenar(0.5)
    aba.avaliar("document.querySelector('.menu[data-menu=\"desenho2d\"] .menu-botao').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 10 and not aba.avaliar("document.querySelectorAll('[data-desenho]').length >= 2"): aba.drenar(0.3)
    itens = aba.avaliar("JSON.stringify([...document.querySelectorAll('[data-desenho]')].map(b => [b.dataset.desenho, b.querySelector('small').textContent]))")
    ok('"corte-tesoura"' in itens and '"vistas-gerais"' in itens, f"menu Desenho 2D lista os desenhos salvos: {itens}")
    aba.avaliar("window.__aberto = null; window.open = (u) => { window.__aberto = u; return { focus() {} }; }; document.querySelector('[data-desenho=\"corte-tesoura\"]').click(); 1")
    u = aba.avaliar("window.__aberto")
    ok(u == "/cad?projeto=compressores&desenho=corte-tesoura", f"clicar abre o CAD direto no desenho: {u}")
    # diálogo Vistas 2D: nome existente → substituir marcado
    aba.avaliar("window.editor.dialogoVistasDaSelecao(); 1"); aba.drenar(1.5)
    marcado = aba.avaliar("(() => { const d = document.querySelector('dialog[open]'); const c = [...d.querySelectorAll('input[type=checkbox]')].pop(); return [c.checked, d.querySelector('.aviso-existe').textContent.slice(0, 60)]; })()")
    ok(marcado and marcado[0] and "Já existe" in marcado[1], f"diálogo detecta desenho existente e marca substituir: {marcado}")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
