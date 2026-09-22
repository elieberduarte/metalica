# -*- coding: utf-8 -*-
"""Abrir um projeto pela URL com um "último modelo" gravado no localStorage: o projeto tem
de ficar aberto (o modelo antigo não pode entrar por cima)."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8792
DADOS = tempfile.mkdtemp(prefix="metalica_ul_")
os.makedirs(os.path.join(DADOS, "p")); os.makedirs(os.path.join(DADOS, "modelos"))
# modelo "antigo" com nome, na pasta de modelos; projeto pequeno com 3 caixas
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "modelos", "antigo.modelo.json"))
ents = []
for i in range(3):
    v = [(x + i * 3000, y, z) for z in (0.0, 100.0) for x, y in ((0, 0), (1000, 0), (1000, 200), (0, 200))]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    ents.append({"id": "c%d" % i, "tipo": "solido", "nome": "caixa", "camada": "Vigas", "material": "", "visivel": True, "bloqueada": False, "grupo": "",
                 "atributos": {"tipo_ifc": "IfcBeam", "marcas": {"posicao": "P%d" % i}}, "vertices": v, "faces": f, "arestas_vivas": [], "origem_ifc": ""})
json.dump({"formato": 1, "nome": "pequeno", "unidade": "mm", "escala": 1, "camadas": {}, "entidades": ents, "vistas": [], "metadados": {}},
          open(os.path.join(DADOS, "p", "modelo.json"), "w", encoding="utf-8"))
json.dump({"formato": 1, "nome": "Pequeno", "tipo": "ifc", "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None},
          open(os.path.join(DADOS, "p", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ul_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1200, height=800, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.editor.ultimo', 'antigo'); 1")
    aba.navegar(base + "/editor?projeto=p", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("document.body.dataset.pronto === '1'"): aba.drenar(0.5)
    aba.drenar(4.0)
    n = aba.avaliar("window.editor.documento.tamanho")
    ok(n == 3, "o projeto continua aberto depois de pronto (%s objetos, esperado 3)" % n)
    ok(aba.avaliar("window.editor.projeto === 'p'"), "editor.projeto é o da URL")
    # sem projeto na URL, o último modelo volta
    aba.navegar(base + "/editor", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("document.body.dataset.pronto === '1'"): aba.drenar(0.5)
    aba.drenar(3.0)
    n2 = aba.avaliar("window.editor.documento.tamanho")
    ok(n2 and n2 > 100, "sem pedido na URL, o último modelo (antigo) volta (%s objetos)" % n2)
finally:
    nav.kill(); srv.kill(); shutil.rmtree(perfil, ignore_errors=True); shutil.rmtree(DADOS, ignore_errors=True)
print("\n%d falha(s)." % len(falhas))
sys.exit(1 if falhas else 0)
