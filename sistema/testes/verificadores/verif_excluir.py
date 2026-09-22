# -*- coding: utf-8 -*-
"""Excluir desenhos: diálogo do CAD (marcar detalhamentos → excluir) e × do menu do editor 3D."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8782
DADOS = tempfile.mkdtemp(prefix="metalica_ex_")
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
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ex_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos/compressores/detalhar", {"grupos": ["chapas", "tirantes", "localizacao"]})
    nomes = [d["nome"] for d in r["desenhos"]]
    post("/api/projetos/compressores/vista2d", {"vista": {"padrao": "topo"}, "desenho": "Vistas gerais"})
    lista = get("/api/projetos/compressores/desenhos")
    ok(len(lista) == 4, "4 desenhos no projeto: %s" % [d["nome"] for d in lista])
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1"); aba.console.clear()
    # CAD: abre o desenho de chapas, exclui os detalhamentos pelo diálogo
    aba.navegar(base + "/cad?projeto=compressores&desenho=" + nomes[0], limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 10"): aba.drenar(0.5)
    ok(aba.avaliar("!!document.querySelector('[data-acao=\"excluir-desenhos\"]')"), "CAD tem 'Excluir desenhos…' no menu")
    aba.avaliar("window.cad.dialogoExcluir(); 1"); aba.drenar(1.5)
    n_caixas = aba.avaliar("document.querySelectorAll('dialog[open] input[type=checkbox]').length")
    ok(n_caixas == 4, "diálogo lista os 4 desenhos (%s)" % n_caixas)
    aba.avaliar("[...document.querySelectorAll('dialog[open] button')].find(b => b.textContent === 'Marcar detalhamentos').click(); 1")
    marcados = aba.avaliar("[...document.querySelectorAll('dialog[open] input[type=checkbox]')].filter(c => c.checked).length")
    ok(marcados == 3, "'Marcar detalhamentos' marca os 3 (%s)" % marcados)
    aba.avaliar("document.querySelector('dialog[open] .botao-ok').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 30 and len(get("/api/projetos/compressores/desenhos")) != 1: aba.drenar(0.5)
    resto = get("/api/projetos/compressores/desenhos")
    ok([d["nome"] for d in resto] == ["vistas-gerais"], "só sobrou 'vistas-gerais': %s" % [d["nome"] for d in resto])
    aba.drenar(2.0)
    ok(aba.avaliar("window.cad.nomeDesenho") == "vistas-gerais", "o CAD abriu o desenho que sobrou (%s)" % aba.avaliar("window.cad.nomeDesenho"))
    ok(len([e for e in os.listdir(os.path.join(DADOS, ".lixeira"))]) == 3, "3 arquivos na .lixeira")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erros no console do CAD: %s" % erros[:3])
    # editor 3D: × ao lado do desenho no menu
    aba.console.clear()
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("window.editor && window.editor.projeto === 'compressores' && window.editor.documento && window.editor.documento.tamanho > 10"): aba.drenar(1.0)
    aba.avaliar("window.editor._listarDesenhosNoMenu(); 1"); aba.drenar(2.0)
    ok(aba.avaliar("document.querySelectorAll('.desenhos-salvos [data-excluir]').length") == 1, "menu do editor tem o × do desenho")
    ok(aba.avaliar("!!document.querySelector('[data-acao=\"excluir-desenhos\"]')"), "menu do editor tem 'Excluir desenhos…'")
    aba.avaliar("document.querySelector('.desenhos-salvos [data-excluir]').click(); 1"); aba.drenar(1.0)
    ok(aba.avaliar("!!document.querySelector('dialog[open]')"), "× abre a confirmação")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    t0 = time.time()
    while time.time() - t0 < 20 and get("/api/projetos/compressores/desenhos"): aba.drenar(0.5)
    ok(get("/api/projetos/compressores/desenhos") == [], "desenho excluído pelo ×")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erros no console do editor: %s" % erros[:3])
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(perfil, ignore_errors=True)
print("\n%d falha(s)." % len(falhas))
sys.exit(1 if falhas else 0)
