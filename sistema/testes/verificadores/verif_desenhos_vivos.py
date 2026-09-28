# -*- coding: utf-8 -*-
"""Desenhos que se atualizam sozinhos (desenhos_vivos.py, 28/09): o detalhamento refeito em segundo plano
quando o modelo 3D muda, o CAD aberto recarrega na mesma vista, a gravação por cima do desenho refeito
é recusada, e gravar uma folha refaz o desenho das pranchas."""
import io, json, os, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
DADOS = tempfile.mkdtemp(prefix="metalica_vivos_")
dst = os.path.join(DADOS, "sala")
os.makedirs(dst)
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(dst, "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-28T00:00:00", "alterado": "2026-09-28T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(dst, "projeto.json"), "w", encoding="utf-8"))
mtime_modelo = os.path.getmtime(os.path.join(dst, "modelo.json"))
PORTA = _porta_livre()
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = "http://localhost:%d" % PORTA
def get(r): return json.load(urllib.request.urlopen(base + r, timeout=120))
def post(r, c):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + r, data=json.dumps(c).encode(), headers={"Content-Type": "application/json"}), timeout=300))
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m); (None if c else falhas.append(m))
def esperar(maximo=180):
    t = time.time()
    while time.time() - t < maximo:
        e = get("/api/projetos/sala/desenhos-vivos")
        if not e.get("atualizando"): return e, time.time() - t
        time.sleep(1.5)
    return e, time.time() - t
for _ in range(80):
    try: get("/api/versao"); break
    except Exception: time.sleep(0.5)
try:
    # 1) o detalhamento pelo botão grava o carimbo e a geração de cada desenho
    t0 = time.time()
    post("/api/projetos/sala/detalhar", {})
    mtime_modelo = os.path.getmtime(os.path.join(dst, "modelo.json"))
    e, dt = esperar()
    dt = time.time() - t0
    g1 = (e.get("desenhos") or {}).get("detalhamento-tesouras")
    ok(g1 and not e.get("erro"), "detalhado em %.0f s; geração da tesoura %s; erro: %s" % (dt, g1, e.get("erro")))
    # 2) em dia: não atualiza de novo
    e = get("/api/projetos/sala/desenhos-vivos")
    ok(not e.get("atualizando"), "em dia: nada a fazer")
    # 4) o CAD aberto na tesoura recarrega sozinho quando o modelo muda
    chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_vivos_")
    nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*",
                            f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
            time.sleep(0.5)
        aba = Aba(alvos[0]["webSocketDebuggerUrl"])
        for dm in ("Page", "Runtime"): aba.cmd(f"{dm}.enable")
        aba.navegar(base + "/cad?projeto=sala&desenho=detalhamento-tesouras", limite=60)
        t = time.time()
        while time.time() - t < 60 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 100"): aba.drenar(0.5)
        g_tela = aba.avaliar("window.cad.doc.metadados.geracao")
        aba.avaliar("window.cad.tela.vp.z = 0.123; window.__marca = 'mesma-pagina'; 1")
        ok(g_tela == g1, "CAD abriu a tesoura com a geração %s" % g_tela)
        # 3) o modelo muda (como se o 3D gravasse): a próxima pergunta refaz
        mod = os.path.join(dst, "modelo.json"); time_mod = time.time() + 5; os.utime(mod, (time_mod, time_mod))
        e = get("/api/projetos/sala/desenhos-vivos")
        ok(e.get("atualizando") and "modelo" in (e.get("motivo") or ""), "modelo mudou: atualização começou (%s)" % e.get("motivo"))
        e, dt = esperar()
        g2 = (e.get("desenhos") or {}).get("detalhamento-tesouras")
        ok(g2 and g2 != g1, "refeito em %.0f s: geração nova %s" % (dt, g2))
        ok(abs(os.path.getmtime(mod) - (time_mod)) < 0.01, "a atualização automática não regravou o modelo 3D")
        t = time.time()
        while time.time() - t < 20 and aba.avaliar("window.cad.doc.metadados.geracao") != g2: aba.drenar(0.5)
        ok(aba.avaliar("window.cad.doc.metadados.geracao") == g2 and aba.avaliar("window.__marca") == "mesma-pagina",
           "o CAD recarregou sozinho, sem sair da página")
        ok(abs(aba.avaliar("window.cad.tela.vp.z") - 0.123) < 1e-6, "na mesma vista (zoom mantido)")
        aba.ws.close()
    finally:
        nav.terminate()
    # 5) gravar por cima com a geração velha: recusado
    d = get("/api/projetos/sala/desenhos/detalhamento-tesouras")["desenho"]
    d["metadados"]["geracao"] = g1
    try:
        post("/api/projetos/sala/desenhos/detalhamento-tesouras", {"desenho": d}); ok(False, "gravar por cima devia ser recusado")
    except urllib.error.HTTPError as ex:
        ok("DESENHO_ATUALIZADO" in ex.read().decode("utf-8", "replace"), "gravar por cima do desenho refeito é recusado")
    # 6) folhas: um desenho de trabalho com uma folha, as pranchas das folhas, e gravar a folha refaz as pranchas
    trab = {"nome": "Trabalho", "unidade": "mm", "escala": 25, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}}
    post("/api/projetos/sala/desenhos/trabalho", {"desenho": trab})
    f = post("/api/projetos/sala/desenhos/trabalho/folha", {"formato": "A3", "origem": [0, 0]})
    trab["entidades"] = f["entidades"] + [{"tipo": "linha", "camada": "VISTA", "a": [1000, 1000], "b": [5000, 1000], "atributos": {}}]
    trab["camadas"].update(f["camadas"])
    post("/api/projetos/sala/desenhos/trabalho", {"desenho": trab})
    r = post("/api/projetos/sala/desenhos/trabalho/pranchas-das-folhas", {})
    gp1 = (get("/api/projetos/sala/desenhos-vivos").get("desenhos") or {}).get(r["desenho"])
    ok(gp1, "pranchas das folhas feitas (geração %s)" % gp1)
    trab["entidades"].append({"tipo": "linha", "camada": "VISTA", "a": [1000, 2000], "b": [5000, 2000], "atributos": {}})
    post("/api/projetos/sala/desenhos/trabalho", {"desenho": trab})
    t = time.time(); gp2 = gp1
    while time.time() - t < 40 and gp2 == gp1:
        time.sleep(1.5); gp2 = (get("/api/projetos/sala/desenhos-vivos").get("desenhos") or {}).get(r["desenho"])
    pr = get("/api/projetos/sala/desenhos/" + r["desenho"])["desenho"]
    ok(gp2 != gp1 and pr["metadados"]["pranchas"][0].get("entidades_do_desenho") == 2,
       "gravar a folha refez as pranchas em %.0f s (a linha nova entrou: %s objetos)" % (time.time() - t, pr["metadados"]["pranchas"][0].get("entidades_do_desenho")))
finally:
    srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas))
