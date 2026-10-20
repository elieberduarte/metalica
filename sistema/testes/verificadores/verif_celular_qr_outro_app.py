# -*- coding: utf-8 -*-
"""O QR code lido pela CÂMERA pareia e já abre a lista de projetos (19/10).

O usuário leu o QR com a câmera do Android: o computador registrou o aparelho, e o celular abriu
"Este aparelho ainda não está ligado ao computador". A câmera entrega o link ao Chrome como
navegação vinda de FORA do site; com o cookie em SameSite=Strict o navegador grava a chave mas não
a manda no redirecionamento logo em seguida (/celular/parear → /celular/), e a primeira tela saía
como se nada tivesse sido pareado. O verif_celular_ui não pegava: lá o pareamento é digitado na
barra do navegador, que conta como navegação do próprio site.

Aqui o link do QR está numa página de OUTRO site (localhost × 127.0.0.1), e o toque nele faz o
caminho da câmera. O servidor do celular sobe sozinho, sem o app.py, só no 127.0.0.1."""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo
from celular import servidor as S

falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.3)
    return False


DADOS = tempfile.mkdtemp(prefix="metalica_celqr_")
proj = os.path.join(DADOS, "dados", "obra")
os.makedirs(os.path.join(proj, "detalhamento")); os.makedirs(os.path.join(proj, "comercial"))
open(os.path.join(proj, "comercial", "comercial.json"), "w", encoding="utf-8").write("{}")
json.dump({"nome": "Obra do QR", "alterado": "2026-10-19T21:27:00"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
json.dump(_modelo(), open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
cel = S.Celular(os.path.join(DADOS, "dados"), os.path.join(DADOS, "trabalho"), porta=_porta_livre(), host="127.0.0.1")
cel.ligar()
codigo = cel.novo_codigo()["codigo"]
LINK = f"http://127.0.0.1:{cel.porta}/celular/parear?c={codigo}"


class OutroSite(http.server.BaseHTTPRequestHandler):
    """A "câmera": uma página de outro site com o link do QR."""
    def do_GET(self):
        corpo = f'<a id="qr" href="{LINK}">QR</a>'.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(corpo)

    def log_message(self, *a): pass


fora = http.server.HTTPServer(("127.0.0.1", _porta_livre()), OutroSite)
threading.Thread(target=fora.serve_forever, daemon=True).start()

exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_celqr_")
nav = subprocess.Popen([exe, "--headless=new", "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}",
                        f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
        except Exception: pass
        time.sleep(0.5)
    ap = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime"): ap.cmd(f"{dm}.enable")
    ap.cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=3, mobile=True)
    # "localhost" e "127.0.0.1" são sites diferentes: o toque no link é a navegação de fora do site
    ap.navegar(f"http://localhost:{fora.server_address[1]}/", limite=20)
    ap.avaliar("document.getElementById('qr').click()")
    ok(esperar(ap, "location.pathname === '/celular/' && document.readyState === 'complete'"), "o QR leva à tela do celular")
    ok(len(cel.aparelhos()) == 1, "o computador registra o aparelho")
    texto = ap.avaliar("document.body ? document.body.innerText : ''") or ""
    ok("ainda não está ligado" not in texto, "a primeira tela depois do QR não diz que o aparelho não está ligado")
    ok(esperar(ap, "document.querySelectorAll('.projeto').length === 1"), "a primeira tela já é a lista de projetos")
finally:
    try: nav.kill()
    except Exception: pass
    fora.shutdown()
    cel.desligar()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
