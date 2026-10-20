# -*- coding: utf-8 -*-
"""A cobertura retrátil aberta e retraída no 3D do celular (pedido do usuário, Kaefer, 19/10).

No computador, "ver aberta/retraída" grava o modelo; o celular só lê. O pacote leva as duas situações
(test_pacote_cobertura_movel) e a tela troca o arquivo que o 3D lê: dois botões no alto, a vista fica onde
estava, as mesmas peças em outro lugar. Projeto sem cobertura retrátil não mostra os botões.

O servidor do celular sobe sozinho no 127.0.0.1 com dois projetos: a cobertura pequena de
test_cobertura_movel (aberta, como o PC gravou) e uma obra comum."""
import base64, hashlib, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo as _modelo_comum
from test_cobertura_movel import PAR, _modelo as _modelo_cobertura
from nucleo3d import cobertura_movel as CM
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


def imagem(aba, foto=None):
    aba.drenar(0.6)
    png = base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"])
    if foto:
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), foto), "wb").write(png)
    return hashlib.sha1(png).hexdigest()


DADOS = tempfile.mkdtemp(prefix="metalica_celcob_")
for slug, nome, modelo in (("cobertura", "Cobertura retrátil", None), ("comum", "Obra comum", _modelo_comum())):
    p = os.path.join(DADOS, "dados", slug)
    os.makedirs(os.path.join(p, "detalhamento")); os.makedirs(os.path.join(p, "comercial"))
    open(os.path.join(p, "comercial", "comercial.json"), "w", encoding="utf-8").write("{}")
    json.dump({"nome": nome, "alterado": "2026-10-19T22:40:00", "analise_parametros": PAR},
              open(os.path.join(p, "projeto.json"), "w", encoding="utf-8"))
    if modelo is None:
        doc = _modelo_cobertura()
        CM.aplicar(doc, PAR, "aberta")
        modelo = doc.dict()
    json.dump(modelo, open(os.path.join(p, "modelo.json"), "w", encoding="utf-8"))
cel = S.Celular(os.path.join(DADOS, "dados"), os.path.join(DADOS, "trabalho"), porta=_porta_livre(), host="127.0.0.1")
cel.ligar()
base = f"http://127.0.0.1:{cel.porta}"

exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_celcob_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}",
                        "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ABERTO = "window.visor && window.visor.fichas && !document.querySelector('.carregando')"
try:
    for _ in range(60):
        try:
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
        except Exception: pass
        time.sleep(0.5)
    ap = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime"): ap.cmd(f"{dm}.enable")
    ap.cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    ap.navegar(base + "/celular/parear?c=" + cel.novo_codigo()["codigo"], limite=30)
    ok(esperar(ap, "document.querySelectorAll('.projeto').length === 2"), "pareado: os dois projetos na lista")

    # ------------------------------------------------------------ a obra comum: sem os botões
    ap.navegar(base + "/celular/#/p/comum/modelo", limite=30)
    ok(esperar(ap, ABERTO, 120), "a obra comum abre o 3D")
    ok(ap.avaliar("!document.querySelector('.situacao')"), "sem cobertura retrátil, sem aberta/retraída")

    # ------------------------------------------------------------ a cobertura retrátil
    ap.navegar(base + "/celular/#/p/cobertura/modelo", limite=30)
    ok(esperar(ap, ABERTO + " && window.visor.nPecas > 50", 120), "a cobertura abre o 3D")
    ok(esperar(ap, "!!document.querySelector('.situacao:not([hidden]) [data-s=aberta].ativa')", 10),
       "os botões aparecem, com Aberta marcada (a situação gravada no PC)")
    pecas = ap.avaliar("window.visor.nPecas")
    ap.avaliar("window.__visorAntes = window.visor; window.visor.camera.position.set(9000, -14000, 12000); "
               "window.visor.controles.update(); window.visor.pedirQuadro()")
    vista = imagem(ap, "celular_8_cobertura_aberta.png")
    camera = ap.avaliar("window.visor.camera.position.toArray().map(Math.round)")
    ap.avaliar("document.querySelector('.situacao [data-s=retraida]').click()")
    ok(esperar(ap, "window.visor !== window.__visorAntes && " + ABERTO, 60), "Retraída: o 3D recarrega com a outra situação")
    ok(ap.avaliar("!!document.querySelector('.situacao [data-s=retraida].ativa')"), "com Retraída marcada")
    ok(ap.avaliar("window.visor.nPecas") == pecas, f"as mesmas peças ({pecas}), só a posição muda")
    ok(ap.avaliar("window.visor.camera.position.toArray().map(Math.round)") == camera, "a vista fica onde estava")
    retraida = imagem(ap, "celular_9_cobertura_retraida.png")
    ok(retraida != vista, "a imagem muda: as tesouras empilhadas na ponta")
    ap.avaliar("document.querySelector('.situacao [data-s=aberta]').click()")
    ok(esperar(ap, "!!document.querySelector('.situacao [data-s=aberta].ativa') && " + ABERTO, 60), "e volta à aberta")
    ok(imagem(ap) == vista, "a mesma imagem de antes da troca")
    st = ap.avaliar("fetch('/celular/dados/cobertura/manifesto.json').then(r => r.json()).then(j => j.cobertura_movel.atual)")
    ok(st == "aberta", f"nada gravado: o projeto continua na situação do PC ({st})")
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
