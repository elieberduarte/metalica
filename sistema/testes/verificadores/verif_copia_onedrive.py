# -*- coding: utf-8 -*-
"""O selo da cópia no OneDrive na tela inicial (DESEMPENHO N.3, 11/11/2026; usuário: "Preciso que continue salvando os
arquivos no OneDrive, tem arquivo que está sendo salvo só no disco C").

Servidor próprio numa pasta temporária (nunca a 8765/8766), a cópia indo para outra pasta temporária:
1. desligada: o selo não aparece;
2. ligada sem cópia ainda: "nenhuma cópia ainda" (amarelo); o clique copia agora → "cópia agora há pouco";
3. a cópia que falhou: vermelho, com o motivo no texto de ajuda;
4. sem cópia há 3 h: amarelo "sem cópia há 3 h".
As fotos (copia_1..4.png) vão para a folha mostrada ao usuário antes de ligar."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
import copia_onedrive as C
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_copia_")
DESTINO = os.path.join(tempfile.mkdtemp(prefix="onedrive_"), "Backup Metálica", "dados")
os.makedirs(os.path.join(DADOS, "cobertura-filipn-goioêre", "05-ENVIADOS"))
with open(os.path.join(DADOS, "cobertura-filipn-goioêre", "05-ENVIADOS", "Proposta R00.pdf"), "w") as f:
    f.write("pdf")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
for _ in range(80):
    try:
        urllib.request.urlopen(base + "/api/versao", timeout=2); break
    except Exception:
        time.sleep(0.5)
falhas = []
FOTOS = os.path.dirname(os.path.abspath(__file__))


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=20.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


def foto(aba, nome):
    try:
        d = aba.cmd("Page.captureScreenshot", format="png", clip={"x": 0, "y": 0, "width": 1400, "height": 120, "scale": 1})
        with open(os.path.join(FOTOS, nome), "wb") as f:
            f.write(base64.b64decode(d["data"] if "data" in d else d["result"]["data"]))
    except Exception:                               # noqa: BLE001
        pass


SELO = "document.querySelector('#selo-copia')"


def abrir(aba):
    aba.navegar(base + "/", limite=60)
    aba.drenar(1.5)


def texto(aba):
    return aba.avaliar(f"({SELO} || {{}}).textContent || ''")


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_copia_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    print("1 — desligada")
    abrir(aba)
    ok(aba.avaliar(f"!!{SELO} && {SELO}.hidden"), "desligada, o selo não aparece")

    print("2 — ligada, nenhuma cópia ainda; o clique copia agora")
    C.ligar(DADOS, True, DESTINO)
    abrir(aba)
    ok(esperar(aba, f"!{SELO}.hidden && /nenhuma cópia ainda/.test({SELO}.textContent)"), f"amarelo: nenhuma cópia ainda ({texto(aba)})")
    ok(aba.avaliar(f"{SELO}.dataset.sit") == "atrasada", "situação atrasada (amarelo)")
    foto(aba, "copia_1_nenhuma.png")
    r = aba.avaliar(f"(() => {{ const q = {SELO}.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; }})()")
    for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1, buttons=1 if tipo == "mousePressed" else 0)
    ok(esperar(aba, f"/cópia agora há pouco/.test({SELO}.textContent)", 30), f"o clique copiou: {texto(aba)}")
    ok(os.path.exists(os.path.join(DESTINO, "cobertura-filipn-goioêre", "05-ENVIADOS", "Proposta R00.pdf")), "a proposta está no OneDrive")
    titulo = aba.avaliar(f"{SELO}.title")
    ok(DESTINO in titulo and "A cada hora" in titulo, f"a ajuda diz para onde e quando ({titulo[:100]}…)")
    foto(aba, "copia_2_ok.png")

    print("3 — a cópia que falhou")
    C._gravar_estado(DADOS, erro="O sistema não pode encontrar o caminho especificado (OneDrive desconectado?)", falhou_em=time.time() - 300,
                    ultima_ok=time.time() - 3600)          # a boa foi há 1 h; a das 5 min atrás falhou
    abrir(aba)
    ok(esperar(aba, f"/a cópia falhou há 5 min/.test({SELO}.textContent)"), f"vermelho: a cópia falhou há 5 min ({texto(aba)})")
    ok(aba.avaliar(f"{SELO}.dataset.sit") == "falhou", "situação falhou (vermelho)")
    ok("OneDrive desconectado" in aba.avaliar(f"{SELO}.title"), "o motivo está na ajuda do selo")
    foto(aba, "copia_3_falhou.png")

    print("4 — sem cópia há 3 h")
    C._gravar_estado(DADOS, erro="", ultima_ok=time.time() - 3 * 3600)
    abrir(aba)
    ok(esperar(aba, f"/sem cópia há 3 h/.test({SELO}.textContent)"), f"amarelo: sem cópia há 3 h ({texto(aba)})")
    foto(aba, "copia_4_atrasada.png")

    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)
    shutil.rmtree(os.path.dirname(os.path.dirname(DESTINO)), ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
