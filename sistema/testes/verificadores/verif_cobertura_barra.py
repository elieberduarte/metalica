# -*- coding: utf-8 -*-
"""Cobertura retrátil aberta/retraída só no projeto que tem uma (pedido do usuário, Kaefer, 19/10).

"Tirar desse menu, pois essa cobertura retrátil é particular desse projeto, e esse modelo está aparecendo em todos os
projetos agora": os dois itens saíram do menu Modelo e viraram dois botões na barra do 3D (modo ver), que só aparecem
quando a análise declara a cobertura retrátil (ou ela já foi vista numa situação). No editor 3D sozinho, os mesmos
itens do menu dele somem nos outros projetos. Trocar continua gravando o modelo na situação, como antes.

Com o app.py --dev numa porta livre e dois projetos: a cobertura pequena de test_cobertura_movel e uma obra comum."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo as _modelo_comum
from test_cobertura_movel import PAR, _modelo as _modelo_cobertura
from nucleo3d import cobertura_movel as CM

falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.3)
    return False


def situacao_gravada(slug):
    m = json.load(open(os.path.join(DADOS, slug, "modelo.json"), encoding="utf-8"))
    return {(r.get("atributos") or {}).get("cobertura_movel", {}).get("situacao") for r in m["entidades"]} - {None}


PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cobbarra_")
doc = _modelo_cobertura()
CM.aplicar(doc, PAR, "aberta")
for slug, nome, modelo, extra in (
        ("cobertura", "Cobertura retrátil", doc.dict(), {"analise_parametros": dict(PAR, cobertura_movel=True), "cobertura_movel_vista": "aberta"}),
        ("comum", "Obra comum", _modelo_comum(), {})):
    p = os.path.join(DADOS, slug)
    os.makedirs(os.path.join(p, "detalhamento"))
    json.dump(dict({"nome": nome, "alterado": "2026-10-19T23:00:00"}, **extra), open(os.path.join(p, "projeto.json"), "w", encoding="utf-8"))
    json.dump(modelo, open(os.path.join(p, "modelo.json"), "w", encoding="utf-8"))

amb = dict(os.environ, PYTHONIOENCODING="utf-8")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--dev", "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb)
base = f"http://localhost:{PORTA}"
exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cobbarra_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
PRONTO = "!!window.ver3dPronto"
try:
    for _ in range(40):
        try:
            _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        try:
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
        except Exception: pass
        time.sleep(0.5)
    pc = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime"): pc.cmd(f"{dm}.enable")
    pc.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=860, deviceScaleFactor=1, mobile=False)

    # ------------------------------------------------------------ o menu Modelo
    pc.navegar(base + "/dividida.html", limite=20)
    fonte = pc.avaliar("fetch('/barra_unica.js').then(r => r.text())") or ""
    ok("Análise estrutural…" in fonte, "o menu Modelo foi lido")
    ok("Cobertura retrátil: ver aberta" not in fonte and "cobertura-aberta" not in fonte,
       "a cobertura retrátil saiu do menu Modelo (era de um projeto só e aparecia em todos)")

    # ------------------------------------------------------------ o modo ver, na obra comum
    pc.navegar(base + "/visor3d/ver3d.html?projeto=comum", limite=30)
    ok(esperar(pc, PRONTO, 60), "a obra comum abre no modo ver")
    pc.drenar(1.5)
    ok(pc.avaliar("document.getElementById('cobertura').hidden"), "sem cobertura retrátil, sem os botões na barra")

    # ------------------------------------------------------------ o modo ver, na cobertura
    pc.navegar(base + "/visor3d/ver3d.html?projeto=cobertura", limite=30)
    ok(esperar(pc, PRONTO, 60), "a cobertura abre no modo ver")
    ok(esperar(pc, "!document.getElementById('cobertura').hidden && !!document.querySelector('#cobertura [data-situacao=aberta].ligado')", 10),
       "Aberta | Retraída na barra, com Aberta marcada")
    pc.drenar(0.5)
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cobertura_barra.png"), "wb").write(
        __import__("base64").b64decode(pc.cmd("Page.captureScreenshot", format="png")["data"]))
    pc.avaliar("document.querySelector('#cobertura [data-situacao=retraida]').click()")
    time.sleep(1.0)
    ok(esperar(pc, PRONTO + " && !!document.querySelector('#cobertura [data-situacao=retraida].ligado')", 60),
       "Retraída: o 3D recarrega com Retraída marcada")
    ok(situacao_gravada("cobertura") == {"retraida"}, f"e o modelo foi gravado retraído, como antes ({situacao_gravada('cobertura')})")

    # ------------------------------------------------------------ o editor 3D sozinho
    for slug, deve in (("comum", True), ("cobertura", False)):
        pc.navegar(base + f"/editor3d?projeto={slug}", limite=60)
        ok(esperar(pc, "!!document.querySelector('[data-acao=\"cobertura-aberta\"]') && "
                       f"document.querySelector('[data-acao=\"cobertura-aberta\"]').hidden === {str(deve).lower()}", 60),
           ("no editor da obra comum, os itens da cobertura somem" if deve else "no editor da cobertura, continuam"))
finally:
    for p in (nav, srv):
        try: p.kill()
        except Exception: pass
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
