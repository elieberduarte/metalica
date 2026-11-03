# -*- coding: utf-8 -*-
"""O cartão de um projeto de módulo que esta versão não tem (02/11/2026), com eventos de verdade.

O dev e o instalado usam a mesma pasta (Documentos\\Metálica): a casa piloto da arquitetura (tipo "arquitetura", só no
dev) aparecia na lista do instalado, o clique no cartão abria /dimensionar (o galpão 20 × 40) e a tela gravava o
formulário padrão no projeto.json. Servidor sem --dev, como o instalado:
  1. o clique no cartão abre a área de trabalho (/dividida, no 3D), não /dimensionar;
  2. alguns segundos depois o projeto.json continua sem "dados";
  3. o galpão do configurador continua abrindo /dimensionar.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cartao_tipo_")
os.makedirs(os.path.join(DADOS, "casa-piloto"))
json.dump({"formato": 1, "nome": "ARQUITETURA - CASA PILOTO", "tipo": "arquitetura", "area": "arquitetura",
           "alterado": "2026-11-02T10:00:00", "dados": None},
          open(os.path.join(DADOS, "casa-piloto", "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "casa", "unidade": "mm", "entidades": {}, "camadas": {}, "materiais": {}},
          open(os.path.join(DADOS, "casa-piloto", "modelo.json"), "w", encoding="utf-8"))
os.makedirs(os.path.join(DADOS, "galpao-novo"))
json.dump({"formato": 1, "nome": "GALPÃO NOVO", "tipo": "galpao", "alterado": "2026-11-01T10:00:00", "dados": None},
          open(os.path.join(DADOS, "galpao-novo", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
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
        aba.drenar(0.25)
    return False


def clicar(aba, seletor):
    """o clique de verdade (mouse) no meio do elemento"""
    r = aba.avaliar(f"(() => {{ const e = document.querySelector({json.dumps(seletor)}); if (!e) return null;"
                    f" const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + Math.min(b.height / 2, 30)]; }})()")
    if not r: return False
    for t in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=t, x=r[0], y=r[1], button="left", clickCount=1)
    return True


def abrir_pelo_cartao(aba, slug):
    aba.navegar(base + "/", limite=30)
    seletor = f"article.cartao[data-slug='{slug}']"
    if not esperar(aba, f"!!document.querySelector({json.dumps(seletor)})"):
        return None
    clicar(aba, seletor)
    esperar(aba, "location.pathname !== '/'", 20)
    return aba.avaliar("location.pathname + location.search")


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cartao_tipo_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    # 1. a casa abre na área de trabalho
    url = abrir_pelo_cartao(aba, "casa-piloto")
    ok(url is not None, "a tela de projetos mostra o cartão da casa (tipo que esta versão não tem)")
    ok(bool(url) and url.startswith("/dividida") and "vista=3d" in url, f"o clique no cartão abre o 3D da área de trabalho ({url})")
    ok(bool(url) and not url.startswith("/dimensionar"), "o clique no cartão não abre a configuração do galpão")

    # 2. nada gravado no projeto.json (a tela do galpão gravava 1,5 s depois de abrir)
    aba.drenar(4)
    p = json.load(open(os.path.join(DADOS, "casa-piloto", "projeto.json"), encoding="utf-8"))
    ok(not p.get("dados"), "o projeto.json da casa continua sem o formulário do galpão")
    ok(p.get("tipo") == "arquitetura", "o tipo do projeto não mudou")

    # 3. o galpão continua na configuração
    url = abrir_pelo_cartao(aba, "galpao-novo")
    ok(bool(url) and url.startswith("/dimensionar"), f"o galpão do configurador abre /dimensionar ({url})")
finally:
    nav.terminate(); srv.terminate()
    try: nav.wait(10); srv.wait(10)
    except Exception: pass
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
