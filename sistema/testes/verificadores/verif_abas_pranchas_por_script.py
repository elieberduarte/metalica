# -*- coding: utf-8 -*-
"""As abas Original | Montagem | Pranchas embaixo do CAD com pranchas feitas por script (04/11/2026, WE Coqueiral · Escadas, o
usuário: "quando clico no original não consigo voltar para a prancha da DEZN"). As EX-01…09 do executivo têm
metadados.prancha mas não se chamam "pranchas…": a aba Pranchas não aparecia (montagem.js só olhava o nome) e, no Original,
a única volta era Arquivo › Trocar de desenho. Com a correção, prancha é o que a listagem do servidor conta (`pranchas` > 0):
  · com o Original (planta de lançamento) e a EX-01 no projeto, as três abas aparecem e a EX-01 acende "Pranchas";
  · no Original, a aba Pranchas continua; clicada, abre a primeira prancha pelo nome (EX-01);
  · a prancha chamada "pranchas…" do sistema continua valendo (a mais nova)."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_abas_pranchas_")
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=120))


def desenho(nome, prancha=False, recebido=False):
    d = {"nome": nome, "unidade": "mm", "escala": 1.0, "camadas": {}, "vistas": [], "metadados": {},
         "entidades": [{"id": "l1", "tipo": "linha", "camada": "VISTA", "a": [0, 0], "b": [1000, 0], "atributos": {"origem": "pdf" if recebido else "cad"}}]}
    if prancha:
        d["metadados"]["prancha"] = {"formato": "A1", "numero": 1, "total": 1, "titulo": nome}
    if recebido:
        d["metadados"]["arquitetonico"] = {"recebido": True, "arquivo": "x.pdf", "tipo": "pdf", "escala": "1:25"}
    return d


srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_abas_pranchas_")
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

    def esperar(expr, limite=60.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if aba.avaliar(expr): return True
            aba.drenar(0.3)
        return False

    def clicar(seletor):
        r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; }})()")
        if not r: raise RuntimeError("não achei " + seletor)
        for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1, buttons=1 if tipo == "mousePressed" else 0)
        aba.drenar(0.3)

    s = urllib.parse.quote(post("/api/projetos", {"nome": "Escadas por script", "tipo": "recebido"})["slug"])
    post(f"/api/projetos/{s}/desenhos/planta-de-lan%C3%A7amento", {"desenho": desenho("Planta de lançamento", recebido=True)})
    post(f"/api/projetos/{s}/desenhos/ex-02-conjunto", {"desenho": desenho("EX-02 Conjunto", prancha=True)})
    post(f"/api/projetos/{s}/desenhos/ex-01-loca%C3%A7%C3%A3o", {"desenho": desenho("EX-01 Locação", prancha=True)})
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar("window.cad && document.body.dataset.pronto === '1'")
    aba.console.clear()
    aba.avaliar("window.cad.abrirDesenho('ex-02-conjunto')")
    ok(esperar("window.cad.nomeDesenho === 'ex-02-conjunto'", 30), "a EX-02 (prancha por script) abriu")
    aba.avaliar("window.montagem.aoTrocar()")
    aba.drenar(1.5)
    vis = aba.avaliar("[...document.querySelectorAll('button[data-aba]')].filter(b => !b.hidden).map(b => b.dataset.aba)")
    ok(vis and "original" in vis and "pranchas" in vis, f"as abas Original e Pranchas aparecem com a EX aberta: {vis}")
    ok(aba.avaliar("(document.querySelector('button[data-aba=pranchas]') || {}).classList.contains('on')"), "a EX-02 acende a aba Pranchas")
    clicar("button[data-aba=original]")
    ok(esperar("window.cad.nomeDesenho === 'planta-de-lançamento'", 30), f"o Original abre: {aba.avaliar('window.cad.nomeDesenho')}")
    ok(esperar("!document.querySelector('button[data-aba=pranchas]').hidden", 10), "no Original, a aba Pranchas continua (dá para voltar)")
    clicar("button[data-aba=pranchas]")
    ok(esperar("window.cad.nomeDesenho === 'ex-01-locação'", 30), f"Pranchas abre a primeira pelo nome (EX-01): {aba.avaliar('window.cad.nomeDesenho')}")
    # o jogo "pranchas…" do sistema continua valendo e tem preferência
    post(f"/api/projetos/{s}/desenhos/pranchas-2026", {"desenho": desenho("Pranchas 2026", prancha=True)})
    clicar("button[data-aba=original]")
    esperar("window.cad.nomeDesenho === 'planta-de-lançamento'", 30)
    clicar("button[data-aba=pranchas]")
    ok(esperar("window.cad.nomeDesenho === 'pranchas-2026'", 30), f"com o jogo 'pranchas…', a aba abre ele: {aba.avaliar('window.cad.nomeDesenho')}")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
