# -*- coding: utf-8 -*-
"""O "← 3D" da cena (usuário, 28/10: "quando estou no editor de cenas, se clico para voltar para o 3D ele vai para uma tela
isolada de tudo que fica um looping e não consigo voltar para tela inicial"). Pelo menu Cenas › Cenas da obra…, a cena
abre na janela inteira; o "← 3D" ia ao modo ver solto (/visor3d/ver3d.html, sem a barra de cima), e o Cenas dele voltava
à cena. Agora, na janela inteira, ele volta à área de trabalho do projeto com o 3D; dentro do quadro do 3D (o Cenas do
modo ver), ao modo ver do quadro, com a barra de cima em volta."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cena_voltar_")
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-28T00:00:00", "alterado": "2026-10-28T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
_json(base + "/api/versao")
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


def clicar_no(aba, onde, sel):
    """clique de verdade no meio do elemento; `onde` é o documento em JS (o de cima ou o do quadro)"""
    r = aba.avaliar(f"(() => {{ const d = {onde}; const b = d.querySelector('{sel}'); if (!b) return null; const q = b.getBoundingClientRect();"
                    f" let x = q.x + q.width / 2, y = q.y + q.height / 2; const f = d.defaultView.frameElement;"
                    f" if (f) {{ const g = f.getBoundingClientRect(); x += g.x; y += g.y; }} return [x, y]; }})()")
    if not r:
        return False
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    return True


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cena_voltar_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    print("A — a cena na janela inteira (o menu Cenas › Cenas da obra…)")
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!document.querySelector('#voltar')"), "a cena abriu")
    clicar_no(aba, "document", "#voltar")
    ok(esperar(aba, "location.pathname === '/dividida'", 30), f"o ← 3D volta à área de trabalho do projeto ({aba.avaliar('location.pathname + location.search')})")
    ok(aba.avaliar("new URLSearchParams(location.search).get('vista') === '3d' && new URLSearchParams(location.search).get('projeto') === 'obra'"),
       "com o 3D à mostra, no mesmo projeto")
    ok(esperar(aba, "document.body.dataset.pronto === '1'", 60), "a área de trabalho, com a barra de cima (dela se volta à tela inicial)")

    print("B — a cena dentro do quadro do 3D (o botão Cenas do modo ver)")
    # o botão ganha o clique quando o modo ver termina de abrir o modelo
    ok(esperar(aba, "(() => { try { const b = document.querySelector('#f3d').contentDocument.querySelector('#btn-cenas'); return !!(b && b.onclick && b.offsetWidth); } catch (e) { return false; } })()", 90),
       "o modo ver no quadro, com o botão Cenas")
    clicar_no(aba, "document.querySelector('#f3d').contentDocument", "#btn-cenas")
    ok(esperar(aba, "(() => { try { const d = document.querySelector('#f3d').contentDocument; return d.location.pathname === '/visor3d/cena.html' && !!d.querySelector('#voltar'); } catch (e) { return false; } })()", 30),
       "a cena abre dentro do quadro")
    clicar_no(aba, "document.querySelector('#f3d').contentDocument", "#voltar")
    ok(esperar(aba, "(() => { try { return document.querySelector('#f3d').contentDocument.location.pathname === '/visor3d/ver3d.html'; } catch (e) { return false; } })()", 30),
       "o ← 3D volta ao modo ver do quadro")
    ok(aba.avaliar("location.pathname") == "/dividida", f"e a janela continua a área de trabalho ({aba.avaliar('location.pathname')})")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
