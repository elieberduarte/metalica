# -*- coding: utf-8 -*-
"""As camadas na tela das cenas antes da foto (usuário, 05/11, Hora Certa · Galpão Existente: "na tela de configuração de
cenas tenham as camadas para poder ocultar e habilitar"). A lista das camadas ficava dentro do corpo da cena, que só aparece
com uma foto aberta: com "(nenhuma cena)" o painel não tinha nada. Agora, pela tela, com cliques de verdade:
  A. sem cena: a lista das camadas aparece (logo abaixo da lista das cenas) e desmarcar uma esconde as peças no 3D;
     recarregada, a página lembra;
  B. a cena nova (o botão Nova cena, o arquivo escolhido) começa com essa camada desligada, gravada na cena, e a lista vai
     para o lugar dela no corpo da cena;
  A2. o sol também (05/11: "não consigo mexer no sol da cena"): sem cena, a direção arrastada com o mouse move o sol do 3D;
     recarregada, a página lembra; a cena nova começa com ele;
  C. sem erro no console.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from PIL import Image
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cena_camadas_")
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-05T00:00:00", "alterado": "2026-11-05T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
FOTO = os.path.join(DADOS, "foto-local.jpg")
Image.new("RGB", (1200, 900), (120, 110, 95)).save(FOTO, "JPEG", quality=90)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.3)
    return False


def clicar_no(aba, sel):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); const sec = b && b.closest('details'); if (sec && !sec.open && b.tagName !== 'SUMMARY') sec.open = true; if (!b || !b.offsetWidth) return null;"
                    f" b.scrollIntoView({{block: 'center'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r: return False
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    return True


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cena_camadas_")
nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
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
    for d in ("Page", "Runtime", "Log", "DOM"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    print("A — sem cena: as camadas no painel")
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=60)
    ok(esperar(aba, "!!window.cenaPronta", 120), "a tela das cenas abriu")
    ok(aba.avaliar("!cenaApi.estado().cena && document.getElementById('corpo').hidden"), "sem cena (o corpo da cena escondido)")
    nome = aba.avaliar("(() => { const v = visor; const i = v.cabecalho.camadas.findIndex((c, k) => v.visivelCamada[k] !== false);"
                       " return i >= 0 ? v.cabecalho.camadas[i].nome : null; })()")
    ok(bool(nome), f"o modelo tem uma camada ligada para o teste ({nome})")
    SEL = f'#camadas input[data-chave="camada:{nome}"]'
    IDX = f"visor.cabecalho.camadas.findIndex(c => c.nome === {json.dumps(nome)})"
    ok(esperar(aba, f"(() => {{ const c = document.querySelector({json.dumps(SEL)}); return !!(c && c.offsetWidth && c.checked); }})()", 10),
       "a lista das camadas aparece, com a camada marcada (antes: vazia até abrir uma foto)")
    ok(clicar_no(aba, SEL), "clique na caixa da camada")
    ok(esperar(aba, f"visor.visivelCamada[{IDX}] === false", 5), "desmarcar esconde a camada no 3D")
    aba.avaliar("location.reload(); 1")
    aba.drenar(1.0)
    ok(esperar(aba, f"!!window.cenaPronta && !document.querySelector({json.dumps(SEL)}).checked && visor.visivelCamada[{IDX}] === false", 120),
       "recarregada, a tela lembra a camada desligada")

    print("A2 — sem cena: o sol (usuário, 05/11: \"não consigo mexer no sol da cena\" — sem cena ele nem aparecia)")
    ok(aba.avaliar("(() => { const d = document.querySelector('#sol-caixa [data-sol=direcao]'); return !!(d && d.offsetWidth); })()"),
       "a direção e a altura do sol aparecem sem cena")
    ok(aba.avaliar("document.getElementById('sombra-chao').closest('label').offsetWidth === 0"), "a sombra no chão (a da foto) fica escondida sem cena")
    sol0 = aba.avaliar("visor._luz.uSol.value.toArray()")
    # arrastar a faixa da direção com o mouse, da ponta esquerda até ~1/4 (90°)
    r = aba.avaliar("(() => { const d = document.querySelector('#sol-caixa [data-sol=direcao]'); d.scrollIntoView({block: 'center'});"
                    " const q = d.getBoundingClientRect(); return [q.x, q.y + q.height / 2, q.width]; })()")
    x0, y0, w = r
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x0 + 2, y=y0, button="left", clickCount=1)
    for k in range(1, 9):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + 2 + (w * 0.25 - 2) * k / 8, y=y0, button="left", buttons=1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x0 + w * 0.25, y=y0, button="left", clickCount=1)
    aba.drenar(0.5)
    dir1 = int(aba.avaliar("document.querySelector('#sol-caixa [data-sol=direcao]').value"))
    sol1 = aba.avaliar("visor._luz.uSol.value.toArray()")
    ok(60 <= dir1 <= 120 and sol1 != sol0, f"arrastada com o mouse, a direção muda ({dir1}°) e o sol do 3D vai junto ({[round(x, 2) for x in sol1]})")
    aba.avaliar("location.reload(); 1")
    aba.drenar(1.0)
    ok(esperar(aba, f"!!window.cenaPronta && +document.querySelector('#sol-caixa [data-sol=direcao]').value === {dir1}", 120),
       "recarregada, a tela lembra o sol")

    print("B — a cena nova começa com as camadas e o sol de agora")
    doc = aba.cmd("DOM.getDocument")["root"]["nodeId"]
    no = aba.cmd("DOM.querySelector", nodeId=doc, selector="#arquivo")["nodeId"]
    aba.cmd("DOM.setFileInputFiles", nodeId=no, files=[FOTO])
    ok(esperar(aba, "!!cenaApi.estado().cena && !document.getElementById('foto').hidden", 60), "a foto virou a cena nova e abriu")
    ok(esperar(aba, f"(cenaApi.estado().cena.desligadas || []).includes({json.dumps('camada:' + nome)})", 10),
       "a cena nova tem a camada desligada")
    gravado = json.loads(urllib.request.urlopen(f"{base}/api/projetos/obra/terreno/cenas/foto-local", timeout=30).read())
    ok(("camada:" + nome) in (gravado.get("desligadas") or []), f"e gravada no servidor ({gravado.get('desligadas')})")
    ok(((gravado.get("sol") or {}).get("direcao")) == dir1, f"e o sol de antes da foto ({(gravado.get('sol') or {}).get('direcao')}°)")
    ok(aba.avaliar("document.getElementById('camadas-caixa').parentElement.id === 'lugar-camadas'"
                   " && document.getElementById('sol-bloco').parentElement.id === 'lugar-sol'"),
       "com a cena aberta, as camadas e o sol vão para o lugar deles no corpo da cena")
    ok(aba.avaliar("document.getElementById('sombra-chao').closest('label').offsetWidth > 0"), "e a sombra no chão aparece")
    ok(aba.avaliar(f"(() => {{ const c = document.querySelector({json.dumps(SEL)}); return !!(c && c.offsetWidth && !c.checked); }})()")
       and aba.avaliar(f"visor.visivelCamada[{IDX}] === false"), "à mostra, desmarcada, e a camada continua escondida")
    # a cena apagada: a lista volta para cima, com as camadas de antes da foto
    aba.avaliar("window.confirm = () => true; 1")
    ok(clicar_no(aba, "#apagar") and esperar(aba, "!cenaApi.estado().cena && document.getElementById('camadas-caixa').parentElement.id === 'lado'", 30),
       "apagada a cena, a lista volta para baixo da lista das cenas")

    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
