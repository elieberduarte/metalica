# -*- coding: utf-8 -*-
"""O 3D do celular no tema escuro do aparelho (19/10).

O usuário, com o Android no tema escuro: a lista e as abas saíam escuras, mas o Modelo 3D abria claro —
o fundo, os botões flutuantes e a contagem de peças. O visor nascia com o fundo claro de fábrica e a
tela do celular nunca lhe passava o tema; os botões tinham o branco fixo no CSS.

Aqui o servidor do celular sobe sozinho no 127.0.0.1, o Chrome finge um aparelho no tema escuro, o 3D
abre, e a conferência é na IMAGEM da tela: o fundo do 3D e um botão flutuante escuros. Depois o
aparelho passa para o claro com o 3D aberto, e o fundo acompanha sem recarregar."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
import pymupdf
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


def tema(aba, valor):
    aba.cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": valor}])


def brilho(aba, x, y):
    """O brilho (0–255) do pixel (x, y) em pixels CSS, da imagem da tela."""
    aba.drenar(0.6)
    png = base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"])
    px = pymupdf.Pixmap(png)
    r, g, b = px.pixel(int(x * DPR), int(y * DPR))[:3]
    return (r + g + b) / 3


DPR = 2
DADOS = tempfile.mkdtemp(prefix="metalica_celtema_")
proj = os.path.join(DADOS, "dados", "obra")
os.makedirs(os.path.join(proj, "detalhamento")); os.makedirs(os.path.join(proj, "comercial"))
open(os.path.join(proj, "comercial", "comercial.json"), "w", encoding="utf-8").write("{}")
json.dump({"nome": "Obra no escuro", "alterado": "2026-10-19T22:12:00"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
json.dump(_modelo(), open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
cel = S.Celular(os.path.join(DADOS, "dados"), os.path.join(DADOS, "trabalho"), porta=_porta_livre(), host="127.0.0.1")
cel.ligar()
base = f"http://127.0.0.1:{cel.porta}"

exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_celtema_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}",
                        "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
        except Exception: pass
        time.sleep(0.5)
    ap = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime"): ap.cmd(f"{dm}.enable")
    ap.cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=DPR, mobile=True)
    tema(ap, "dark")
    ap.navegar(base + "/celular/parear?c=" + cel.novo_codigo()["codigo"], limite=30)
    ok(esperar(ap, "document.querySelectorAll('.projeto').length === 1"), "pareado: a lista abre")
    ap.avaliar("document.querySelector('.projeto').click()")
    ok(esperar(ap, "window.visor && window.visor.fichas && !document.querySelector('.carregando')", 120), "o 3D abre")
    # o canto de baixo à esquerda do palco: só fundo (o modelo fica no meio)
    caixa = ap.avaliar("(() => { const r = document.querySelector('.palco').getBoundingClientRect(); return [r.left, r.bottom]; })()")
    x, y = caixa[0] + 6, caixa[1] - 6
    fundo_escuro = brilho(ap, x, y)
    ok(fundo_escuro < 60, f"no aparelho escuro, o fundo do 3D é escuro (brilho {fundo_escuro:.0f})")
    botao = ap.avaliar("(() => { const r = document.querySelector('.ferramentas button:not(.ligado)').getBoundingClientRect(); return [r.left + 4, r.top + 4]; })()")
    b = brilho(ap, botao[0], botao[1])
    ok(b < 80, f"e os botões flutuantes também (brilho {b:.0f})")
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "celular_7_escuro.png"), "wb").write(
        base64.b64decode(ap.cmd("Page.captureScreenshot", format="png")["data"]))
    cont = ap.avaliar("getComputedStyle(document.querySelector('.contagem')).backgroundColor")
    ok("255, 255, 255" not in cont, f"a contagem de peças sem o branco fixo ({cont})")
    tema(ap, "light")
    fundo_claro = brilho(ap, x, y)
    ok(fundo_claro > 200, f"o aparelho passa para o claro com o 3D aberto: o fundo acompanha (brilho {fundo_claro:.0f})")
finally:
    try: nav.kill()
    except Exception: pass
    cel.desligar()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
