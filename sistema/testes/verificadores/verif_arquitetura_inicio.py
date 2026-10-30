# -*- coding: utf-8 -*-
"""A área "Arquitetura" na tela de projetos (módulo de arquitetura, 30/10/2026), com eventos de verdade:
  1. o menu da marca tem Metálica, Pré-moldado e Arquitetura; na Arquitetura somem os "Novo" da Metálica e aparecem
     "Casa piloto (demonstração)" e "Novo projeto de arquitetura";
  2. o clique em "Casa piloto" monta a casa pelo motor e abre o 3D;
  3. a lista da Arquitetura mostra só a casa; a da Metálica não mostra a casa;
  4. o modo ver abre a casa com as camadas "ARQ — …" e a foto fica em verif_arquitetura_casa.png.
Só no desenvolvimento (o gancho _extensoes_dev do app.py fica fora do git): sem o módulo, o verificador sai sem falha.
Porta livre, nunca a 8765/8766."""
import base64, io, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from PIL import Image
import urllib.request

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_arq_inicio_")
# uma obra da Metálica para a lista não ficar só com a casa
os.makedirs(os.path.join(DADOS, "galpao-qualquer"))
json.dump({"nome": "GALPÃO QUALQUER", "tipo": "ifc", "alterado": "2026-10-30T01:00:00"},
          open(os.path.join(DADOS, "galpao-qualquer", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--dev", "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=60):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


def clicar(aba, seletor):
    """o clique de verdade (mouse) no meio do elemento"""
    r = aba.avaliar(f"(() => {{ const e = document.querySelector({json.dumps(seletor)}); if (!e || e.hidden) return null;"
                    f" const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }})()")
    if not r: return False
    for t in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=t, x=r[0], y=r[1], button="left", clickCount=1)
    return True


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_arq_inicio_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    try:
        urllib.request.urlopen(base + "/api/dev/arquitetura.js", timeout=5).read()
    except Exception:
        print("  (o módulo de arquitetura não está ligado nesta cópia: o gancho _extensoes_dev do app.py fica fora do git)")
        raise SystemExit(0)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    # 1. o menu e os botões da área
    aba.navegar(base + "/?area=arquitetura", limite=30)
    ok(esperar(aba, "!!document.getElementById('btn-arq-piloto')", 30), "a tela de projetos abriu com os botões da Arquitetura")
    ok(aba.avaliar("document.querySelector('.topo .marca h1').textContent.startsWith('Arquitetura')"), "a marca diz Arquitetura")
    vis = aba.avaliar("['btn-arq-piloto','btn-arq-novo','btn-novo','btn-novo-ifc','btn-novo-premoldado']"
                      ".map(i => { const e = document.getElementById(i); return e ? !e.hidden : null; })")
    ok(vis[:2] == [True, True] and not any(vis[2:]), f"só os 'Novo' da Arquitetura aparecem ({vis})")
    clicar(aba, ".topo .marca")
    aba.drenar(0.3)
    nomes = aba.avaliar("[...document.querySelectorAll('.menu-areas b')].map(b => b.textContent)")
    ok(nomes and [n.split("em desenvolvimento")[0] for n in nomes] == ["Metálica", "Pré-moldado", "Arquitetura"],
       f"o menu da marca tem as três áreas ({nomes})")
    clicar(aba, ".topo .marca")      # fecha

    # 2. a casa piloto
    ok(clicar(aba, "#btn-arq-piloto"), "clique em 'Casa piloto (demonstração)'")
    ok(esperar(aba, "location.pathname === '/dividida' && location.search.includes('arquitetura-casa-piloto')", 60),
       f"a casa foi montada e o 3D abriu ({aba.avaliar('location.href')})")
    modelo = json.load(open(os.path.join(DADOS, "arquitetura-casa-piloto", "modelo.json"), encoding="utf-8"))
    arq = [e for e in modelo["entidades"] if (e.get("atributos") or {}).get("arq")]
    ok(len(arq) == len(modelo["entidades"]) and len(arq) >= 60, f"o modelo gravado tem os elementos de arquitetura ({len(arq)})")

    # 3. as listas
    aba.navegar(base + "/?area=arquitetura", limite=30)
    esperar(aba, "document.querySelectorAll('article.cartao').length > 0", 30)
    cartoes = aba.avaliar("[...document.querySelectorAll('article.cartao')].map(c => c.getAttribute('aria-label'))")
    ok(cartoes and len(cartoes) == 1 and "CASA PILOTO" in cartoes[0], f"a lista da Arquitetura só tem a casa ({cartoes})")
    clicar(aba, ".topo .marca"); aba.drenar(0.3)
    clicar(aba, ".menu-areas button:nth-child(1)"); aba.drenar(0.5)
    cartoes = aba.avaliar("[...document.querySelectorAll('article.cartao')].map(c => c.getAttribute('aria-label'))")
    ok(cartoes and not any("CASA PILOTO" in c for c in cartoes) and any("GALPÃO" in c for c in cartoes),
       f"a lista da Metálica não mostra a casa ({cartoes})")
    ok(aba.avaliar("!document.getElementById('btn-novo').hidden && document.getElementById('btn-arq-piloto').hidden"),
       "de volta na Metálica, os botões da Metálica voltam e os da Arquitetura somem")

    # 4. o modo ver
    aba.navegar(base + "/visor3d/ver3d.html?projeto=arquitetura-casa-piloto", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.visor && visor.fichas)", 120),
       f"o modo ver abriu a casa ({aba.avaliar('window.visor && visor.nPecas')} peças)")
    cams = aba.avaliar("visor.cabecalho.camadas.map(c => c.nome)") or []
    ok(cams and all(c.startswith("ARQ — ") for c in cams), f"as camadas são as da arquitetura ({cams})")
    aba.avaliar("visor.enquadrar && visor.enquadrar('iso'); 1")
    aba.drenar(1.5)
    img = Image.open(io.BytesIO(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))).convert("RGB")
    img.save(os.path.join(os.path.dirname(__file__), "verif_arquitetura_casa.png"))

    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.terminate()
    except Exception: pass
    srv.terminate()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS: %d" % len(falhas))
sys.exit(1 if falhas else 0)
