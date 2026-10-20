# -*- coding: utf-8 -*-
"""A cobertura retrátil aberta e retraída no 3D do celular (pedido do usuário, Kaefer, 19/10).

No computador, "ver aberta/retraída" grava o modelo; o celular só lê. O pacote leva as duas situações
(test_pacote_cobertura_movel) e a tela troca o arquivo que o 3D lê: dois botões no alto, a vista fica onde
estava, as mesmas peças em outro lugar. Projeto sem cobertura retrátil não mostra os botões.

A troca mora no menu Vistas (pedido do usuário, 19/10: "para não precisar criar um menu novo só para isso").
O pacote velho (de antes da cobertura no celular) é refeito: o formato do pacote entra na assinatura dele.

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
    ap.avaliar("document.querySelector('.ferramentas [data-f=vistas]').click()")
    ok(esperar(ap, "!document.getElementById('folha').hidden && !!document.querySelector('#folha [data-v=iso]')", 5), "o menu Vistas abre")
    ok(ap.avaliar("!document.querySelector('#folha [data-s]')"), "sem cobertura retrátil, o menu Vistas não tem aberta/retraída")

    # ------------------------------------------------------------ a cobertura retrátil
    ap.navegar(base + "/celular/#/p/cobertura/modelo", limite=30)
    ok(esperar(ap, ABERTO + " && window.visor.nPecas > 50", 120), "a cobertura abre o 3D")
    ap.avaliar("document.querySelector('.ferramentas [data-f=vistas]').click()")
    ok(esperar(ap, "!!document.querySelector('#folha .cobertura [data-s=aberta].forte')", 10),
       "no menu Vistas, a cobertura retrátil com Aberta marcada (a situação gravada no PC)")
    imagem(ap, "celular_8_vistas_cobertura.png")
    ap.avaliar("document.querySelector('#folha [data-v=iso]').click()")
    pecas = ap.avaliar("window.visor.nPecas")
    ap.avaliar("window.__visorAntes = window.visor; window.visor.camera.position.set(9000, -14000, 12000); "
               "window.visor.controles.update(); window.visor.pedirQuadro()")
    vista = imagem(ap, "celular_8_cobertura_aberta.png")
    camera = ap.avaliar("window.visor.camera.position.toArray().map(Math.round)")
    ap.avaliar("document.querySelector('.ferramentas [data-f=vistas]').click()")
    esperar(ap, "!!document.querySelector('#folha [data-s=retraida]')", 5)
    ap.avaliar("document.querySelector('#folha [data-s=retraida]').click()")
    ok(esperar(ap, "window.visor !== window.__visorAntes && " + ABERTO, 60), "Retraída: o 3D recarrega com a outra situação")
    ap.avaliar("document.querySelector('.ferramentas [data-f=vistas]').click()")
    ok(esperar(ap, "!!document.querySelector('#folha [data-s=retraida].forte')", 5), "e no menu Vistas, Retraída marcada")
    ap.avaliar("document.querySelector('#folha [data-s=retraida]').click()")      # a marcada: só fecha
    ok(ap.avaliar("window.visor.nPecas") == pecas, f"as mesmas peças ({pecas}), só a posição muda")
    ok(ap.avaliar("window.visor.camera.position.toArray().map(Math.round)") == camera, "a vista fica onde estava")
    retraida = imagem(ap, "celular_9_cobertura_retraida.png")
    ok(retraida != vista, "a imagem muda: as tesouras empilhadas na ponta")
    ok(esperar(ap, "document.getElementById('folha').hidden"), "tocar na situação marcada só fecha o menu")
    ap.avaliar("window.__visorAntes = window.visor; document.querySelector('.ferramentas [data-f=vistas]').click()")
    esperar(ap, "!!document.querySelector('#folha [data-s=aberta]')", 5)
    ap.avaliar("document.querySelector('#folha [data-s=aberta]').click()")
    ok(esperar(ap, "window.visor !== window.__visorAntes && " + ABERTO, 60), "e volta à aberta")
    ok(imagem(ap) == vista, "a mesma imagem de antes da troca")
    # ------------------------------------------------------------ as camadas desligadas ficam desligadas (19/10)
    # "se eu desativo a lona, quando mudo de retraída para aberta a lona volta — isso vale para os outros modelos também"
    VIS = "(n => { const v = window.visor; const i = v.cabecalho.camadas.findIndex(c => c.nome === n); return v.visivelCamada[i] !== false; })"
    ap.avaliar("document.querySelector('.ferramentas [data-f=camadas]').click()")
    esperar(ap, "!!document.querySelector('#folha .camada')", 5)
    nome = ap.avaliar("(() => { const el = [...document.querySelectorAll('#folha .camada')].find(x => x.textContent.includes('Contraventamento'));"
                      " el.click(); return 'Contraventamento'; })()")
    ok(ap.avaliar(f"{VIS}('{nome}')") is False, "a camada do contraventamento (a sanfona) desligada")
    ap.avaliar("window.__visorAntes = window.visor; document.querySelector('.ferramentas [data-f=vistas]').click()")
    esperar(ap, "!!document.querySelector('#folha [data-s=retraida]')", 5)
    ap.avaliar("document.querySelector('#folha [data-s=retraida]').click()")
    ok(esperar(ap, "window.visor !== window.__visorAntes && " + ABERTO, 60), "troca para Retraída")
    ok(ap.avaliar(f"{VIS}('{nome}')") is False, "a camada continua desligada depois de trocar a situação")
    ap.navegar(base + "/celular/#/", limite=30)
    esperar(ap, "document.querySelectorAll('.projeto').length === 2")
    ap.navegar(base + "/celular/#/p/cobertura/modelo", limite=30)
    ok(esperar(ap, ABERTO, 60) and ap.avaliar(f"{VIS}('{nome}')") is False, "e depois de sair e voltar ao projeto")
    ap.avaliar("location.reload()")
    ok(esperar(ap, ABERTO, 60) and ap.avaliar(f"{VIS}('{nome}')") is False, "e depois de recarregar (guardada no aparelho)")
    ap.navegar(base + "/celular/#/p/comum/modelo", limite=30)
    ok(esperar(ap, ABERTO, 60) and ap.avaliar("window.visor.visivelCamada.every((x, i) => (x !== false) === (window.visor.cabecalho.camadas[i].visivel !== false))"),
       "a escolha é do projeto: a obra comum abre com as camadas como o modelo dela traz")
    ap.navegar(base + "/celular/#/p/cobertura/modelo", limite=30)
    esperar(ap, ABERTO, 60)
    ap.avaliar("document.querySelector('.ferramentas [data-f=camadas]').click()")
    esperar(ap, "!!document.querySelector('#folha .camada')", 5)
    ap.avaliar("[...document.querySelectorAll('#folha .camada')].find(x => x.textContent.includes('Contraventamento')).click()")
    ok(ap.avaliar(f"{VIS}('{nome}')") is True, "religar também fica (a camada volta)")

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
