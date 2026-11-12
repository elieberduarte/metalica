# -*- coding: utf-8 -*-
"""As cenas do 3D no modo ver (usuário, 11/11: "Não tem a opção de criar cena, não tem uma opção para salvar cena…";
cenas3d.js, aprovado nas amostras de Projeto/BRIEFINGS/imagens/cenas-3d/). Pela tela, com cliques e teclas de verdade:
  A. "+ Cena" no rodapé → a caixa do nome → Enter: a aba aparece e o servidor guarda a cena do 3D (câmera, camadas, estilo);
  B. outra vista (Topo), uma camada desligada no painel Camadas e as arestas desligadas → a segunda cena;
  C. clicar a 1ª aba volta a câmera, liga a camada e as arestas; a 2ª aba desliga de novo;
  D. botão direito na aba: Atualizar com a vista atual (a câmera nova no servidor), Renomear, Mover para a esquerda;
  E. recarregada, as abas voltam na ordem; Alt+1 e PageDown trocam de cena;
  F. o painel Cenas (botão Cenas): a lista, e "A cena guarda" sem a câmera → ir para a cena não mexe na câmera;
  G. a cena por foto aparece como aba 📷; a tela das Cenas (cena.html) lista também as cenas do 3D e abre a do 3D ali
     (REGRESSÃO 11/11: "as cenas criadas não aparecem aqui");
  I. o menu Cenas da barra de cima (Cenas da obra…) e o painel Cenas do modo ver levam à tela das Cenas;
  H. apagar pelo menu (a caixa confirma): a aba sai; sem erro no console.
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
DADOS = tempfile.mkdtemp(prefix="metalica_cenas3d_")
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-11T00:00:00", "alterado": "2026-11-11T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
# uma cena por foto de antes (sem "ordem"): vira a aba 📷
FOTO_DIR = os.path.join(DADOS, "obra", "cenas", "dados", "quadra")
os.makedirs(FOTO_DIR)
Image.new("RGB", (120, 90), (120, 110, 95)).save(os.path.join(FOTO_DIR, "foto.jpg"), "JPEG")
json.dump({"id": "quadra", "nome": "Quadra", "foto": "foto.jpg", "px": [120, 90], "pares": [], "camera": None, "opacidade": 1.0,
           "criada": "2026-11-01T08:00:00", "alterada": "2026-11-01T08:00:00"},
          open(os.path.join(FOTO_DIR, "cena.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
API = f"{base}/api/projetos/obra/terreno/cenas"
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


def centro(aba, sel):
    return aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); const sec = b && b.closest('details'); if (sec && !sec.open && b.tagName !== 'SUMMARY') sec.open = true; if (!b || !b.offsetWidth) return null;"
                       f" b.scrollIntoView({{block: 'nearest'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")


def clicar_no(aba, sel, botao="left"):
    r = centro(aba, sel)
    if not r: return False
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button=botao, clickCount=1)
    aba.drenar(0.2)
    return True


def tecla(aba, key, code=None, mod=0, vk=0):
    for tipo in ("rawKeyDown", "keyUp"):
        aba.cmd("Input.dispatchKeyEvent", type=tipo, key=key, code=code or key, modifiers=mod, windowsVirtualKeyCode=vk)
    aba.drenar(0.2)


def escrever_na_caixa(aba, texto):
    """A caixa da cena está aberta com o campo escolhido: troca o texto e confirma com Enter."""
    ok(esperar(aba, "!!document.querySelector('#caixa-cena input') && document.activeElement === document.querySelector('#caixa-cena input')", 5),
       "a caixa do nome abre com o campo pronto para escrever")
    aba.cmd("Input.insertText", text=texto)
    tecla(aba, "Enter", vk=13)


def servidor():
    return json.loads(urllib.request.urlopen(API, timeout=30).read())["cenas"]


def camera(aba):
    return aba.avaliar("visor.lerCamera()")


def perto(a, b, tol=50):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def abas(aba):
    return aba.avaliar("[...document.querySelectorAll('#abas-cenas .aba-cena:not(.aba-mais)')].map(b => b.textContent)")


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cenas3d_")
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

    print("A — + Cena grava a vista atual com nome")
    aba.navegar(f"{base}/visor3d/ver3d.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.ver3dPronto && !!window.cenas3d", 180), "o modo ver abriu com as cenas")
    ok(esperar(aba, "document.querySelectorAll('#abas-cenas .aba-cena').length === 2", 15), "as abas no rodapé: a da foto e o + Cena")
    ok(abas(aba) == ["📷 Quadra"], f"a cena por foto é uma aba 📷 ({abas(aba)})")
    clicar_no(aba, "[data-vista=frente]"); aba.drenar(0.5)
    cam_a = camera(aba)
    ok(clicar_no(aba, "#abas-cenas .aba-mais"), "clique no + Cena")
    escrever_na_caixa(aba, "Fachada frontal")
    ok(esperar(aba, "[...document.querySelectorAll('#abas-cenas .aba-cena.ativa')].map(b => b.textContent).join() === 'Fachada frontal'", 10),
       "a aba nova aparece, em destaque")
    s = servidor()
    a = next((c for c in s if c["nome"] == "Fachada frontal"), None)
    ok(a is not None and a.get("tipo") == "3d", "gravada no servidor como cena do 3D")
    ok(a is not None and perto(a["camera"]["posicao"], cam_a["posicao"], 2) and perto(a["camera"]["alvo"], cam_a["alvo"], 2),
       "com a câmera da tela")
    escondidas = aba.avaliar("visor.cabecalho.camadas.filter((c, i) => c.pecas && visor.visivelCamada[i] === false).map(c => 'camada:' + c.nome)")
    ok(a is not None and a.get("arestas") is True and sorted(a.get("desligadas") or []) == sorted(escondidas),
       f"com as arestas ligadas e as camadas escondidas da tela ({escondidas})")

    print("B — outra vista, uma camada e as arestas desligadas: a segunda cena")
    nome = aba.avaliar("(() => { const v = visor; const i = v.cabecalho.camadas.findIndex((c, k) => c.pecas && v.visivelCamada[k] !== false);"
                       " return i >= 0 ? v.cabecalho.camadas[i].nome : null; })()")
    IDX = f"visor.cabecalho.camadas.findIndex(c => c.nome === {json.dumps(nome)})"
    ok(bool(nome), f"o modelo tem uma camada para o teste ({nome})")
    clicar_no(aba, "[data-vista=topo]"); aba.drenar(0.5)
    clicar_no(aba, "[data-painel=camadas]")
    ok(clicar_no(aba, f"#painel-corpo input[data-c=\"{aba.avaliar(IDX)}\"]"), "clique na camada no painel Camadas")
    ok(esperar(aba, f"visor.visivelCamada[{IDX}] === false", 5), "a camada some")
    clicar_no(aba, "#btn-arestas")
    cam_b = camera(aba)
    clicar_no(aba, "#abas-cenas .aba-mais")
    escrever_na_caixa(aba, "Planta")
    ok(esperar(aba, "document.querySelectorAll('#abas-cenas .aba-cena:not(.aba-mais)').length === 3", 10), "a segunda aba aparece")
    b = next((c for c in servidor() if c["nome"] == "Planta"), {})
    ok(("camada:" + nome) in (b.get("desligadas") or []) and b.get("arestas") is False, f"gravada com a camada e as arestas desligadas ({b.get('desligadas')})")

    print("C — clicar a aba volta à cena")
    clicar_no(aba, "#abas-cenas [data-cena=fachada-frontal]")
    aba.drenar(1.2)
    ok(perto(camera(aba)["posicao"], cam_a["posicao"]) and perto(camera(aba)["alvo"], cam_a["alvo"]), "a câmera anda até a da Fachada frontal")
    ok(aba.avaliar(f"visor.visivelCamada[{IDX}] !== false"), "a camada volta a aparecer")
    ok(aba.avaliar("document.getElementById('btn-arestas').classList.contains('ligado')"), "as arestas voltam")
    ok(aba.avaliar("document.querySelector('#painel-corpo input[data-c=\"' + " + IDX + " + '\"]').checked"), "o painel Camadas acompanha")
    clicar_no(aba, "#abas-cenas [data-cena=planta]")
    aba.drenar(1.2)
    ok(perto(camera(aba)["posicao"], cam_b["posicao"]) and aba.avaliar(f"visor.visivelCamada[{IDX}] === false")
       and not aba.avaliar("document.getElementById('btn-arestas').classList.contains('ligado')"),
       "a Planta: a câmera de cima, a camada e as arestas desligadas")

    print("D — botão direito na aba: atualizar, renomear, mover")
    clicar_no(aba, "[data-vista=lado]"); aba.drenar(0.5)
    cam_d = camera(aba)
    clicar_no(aba, "#abas-cenas [data-cena=planta]", "right")
    ok(esperar(aba, "!!document.querySelector('#menu-cena')", 5), "o menu da aba abre")
    clicar_no(aba, "#menu-cena [data-acao='Atualizar com a vista atual']")
    aba.drenar(1.0)
    pl = next((c for c in servidor() if c["id"] == "planta"), None)
    ok(pl is not None and perto(pl["camera"]["posicao"], cam_d["posicao"], 2), "atualizada com a câmera de agora")
    clicar_no(aba, "#abas-cenas [data-cena=planta]", "right")
    clicar_no(aba, "#menu-cena [data-acao='Renomear…']")
    aba.avaliar("document.querySelector('#caixa-cena input').select(); 1")
    escrever_na_caixa(aba, "Planta de cobertura")
    ok(esperar(aba, "[...document.querySelectorAll('#abas-cenas .aba-cena')].some(b => b.textContent === 'Planta de cobertura')", 10),
       "renomeada (a aba e o servidor)")
    clicar_no(aba, "#abas-cenas [data-cena=planta]", "right")
    clicar_no(aba, "#menu-cena [data-acao='Mover para a esquerda']")
    ok(esperar(aba, "JSON.stringify([...document.querySelectorAll('#abas-cenas .aba-cena:not(.aba-mais)')].map(b => b.dataset.cena))"
                    " === JSON.stringify(['quadra', 'planta', 'fachada-frontal'])", 10), f"movida para a esquerda ({abas(aba)})")
    ok([c["id"] for c in servidor()] == ["quadra", "planta", "fachada-frontal"], "a ordem gravada no servidor")

    print("E — recarregada: as abas voltam; Alt+1 e PageDown")
    aba.avaliar("location.reload(); 1")
    aba.drenar(1.0)
    ok(esperar(aba, "!!window.ver3dPronto && document.querySelectorAll('#abas-cenas .aba-cena').length === 4", 180),
       f"as abas voltam ({abas(aba)})")
    aba.avaliar("document.activeElement && document.activeElement.blur(); 1")
    tecla(aba, "3", "Digit3", mod=1, vk=51)                  # Alt+3: a 3ª aba (Fachada frontal)
    aba.drenar(1.2)
    ok(perto(camera(aba)["posicao"], cam_a["posicao"]) and aba.avaliar("cenas3d.ativa()") == "fachada-frontal", "Alt+3 vai à Fachada frontal")
    tecla(aba, "PageDown", vk=34)
    aba.drenar(1.2)
    ok(aba.avaliar("cenas3d.ativa()") == "planta" and perto(camera(aba)["posicao"], cam_d["posicao"]),
       "PageDown vai à seguinte do 3D (pula a da foto)")

    print("F — o painel Cenas: a lista e o que a cena guarda")
    ok(clicar_no(aba, "#btn-cenas") and esperar(aba, "document.getElementById('painel').dataset.painel === 'cenas' && !document.getElementById('painel').hidden", 5),
       "o botão Cenas abre o painel (antes ia direto à página da foto)")
    ok(aba.avaliar("document.querySelectorAll('#painel-corpo .linha-cena').length") == 3, "a lista com as três cenas")
    ok(clicar_no(aba, "#painel-corpo input[data-guarda=camera]"), "desmarca 'Câmera' na cena escolhida")
    aba.drenar(0.8)
    ok(next((c for c in servidor() if c["id"] == "planta"), {}).get("guarda", {}).get("camera") is False, "gravado: a cena não guarda a câmera")
    clicar_no(aba, "[data-vista=frente]"); aba.drenar(0.5)
    cam_f = camera(aba)
    clicar_no(aba, "#painel-corpo [data-ir=planta]")
    aba.drenar(1.0)
    ok(perto(camera(aba)["posicao"], cam_f["posicao"], 1), "ir para a cena sem a câmera não mexe na vista")

    print("G — a tela das Cenas lista também as cenas do 3D e abre a do 3D ali mesmo")
    # REGRESSÃO 11/11 (usuário, Cobertura Filipin: "a ferramenta de cenas não estão se conversando, as cenas criadas não
    # aparecem aqui"): a página da foto filtrava as cenas do 3D. Agora ela é a tela das Cenas (cena.html) com todas
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=60)
    ok(esperar(aba, "!!window.cenaPronta", 120), "a tela das Cenas abriu")
    cartoes = aba.avaliar("[...document.querySelectorAll('#cartoes .cartao-cena')].map(b => b.dataset.cena)")
    ok(cartoes == ["quadra", "planta", "fachada-frontal"], f"os cartões: a da foto e as do 3D, na ordem das abas ({cartoes})")
    aba.avaliar("document.querySelector('#cartoes [data-cena=fachada-frontal]').click(); 1")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'fachada-frontal' && !document.getElementById('quadro').hidden", 30),
       "o cartão da cena do 3D a abre na tela, com o quadro")
    aba.drenar(1.0)
    ok(perto(aba.avaliar("visor.lerCamera().posicao"), cam_a["posicao"]), "com a câmera da cena")

    print("I — o menu Cenas da barra de cima leva à tela das Cenas")
    aba.navegar(f"{base}/dividida?projeto=obra&vista=3d", limite=90)
    F3D = "(document.querySelector('#f3d') && document.querySelector('#f3d').contentWindow)"
    ok(esperar(aba, f"(() => {{ try {{ return !!{F3D}.cenas3d; }} catch (e) {{ return false; }} }})()", 180), "a área de trabalho com o modo ver")
    MENU = "#menus-unicos .menu[data-nome=\"Cenas\"]"
    itens = aba.avaliar(f"""(() => {{ const b = document.querySelector('{MENU} .menu-botao'); b.click();
        const t = [...document.querySelectorAll('{MENU} .menu-lista button')].map(e => e.textContent.trim()); b.click(); return t; }})()""")
    ok(any(x.startswith("Cenas da obra") for x in itens) and any(x.startswith("Nova cena pela vista atual") for x in itens)
       and any(x.startswith("Nova cena pela foto") for x in itens), f"o menu tem as cenas da obra, a nova pela vista e a nova pela foto ({itens})")
    aba.avaliar(f"""(() => {{ document.querySelector('{MENU} .menu-botao').click();
        [...document.querySelectorAll('{MENU} .menu-lista button')].find(e => e.textContent.trim().startsWith('Cenas da obra')).click(); }})(); 1""")
    ok(esperar(aba, "location.pathname === '/visor3d/cena.html' && !!window.cenaPronta && document.querySelectorAll('#cartoes .cartao-cena').length === 3", 120),
       "Cenas da obra… abre a tela das Cenas, com as três")
    # o painel Cenas do modo ver também leva à tela
    aba.navegar(f"{base}/visor3d/ver3d.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.ver3dPronto && !!window.cenas3d", 180), "o modo ver de novo")
    aba.avaliar("cenas3d.painel(); 1")
    ok(esperar(aba, "!!document.querySelector('#cena-tela')", 5), "o painel Cenas tem \"Abrir a tela das Cenas…\"")

    print("H — apagar pelo menu da aba")
    aba.navegar(f"{base}/visor3d/ver3d.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.ver3dPronto && document.querySelectorAll('#abas-cenas .aba-cena').length === 4", 180), "o modo ver de novo")
    clicar_no(aba, "#abas-cenas [data-cena=fachada-frontal]", "right")
    clicar_no(aba, "#menu-cena [data-acao='Apagar…']")
    ok(esperar(aba, "!!document.querySelector('#caixa-cena [data-r=ok]')", 5), "a caixa pergunta antes de apagar")
    clicar_no(aba, "#caixa-cena [data-r=ok]")
    ok(esperar(aba, "!document.querySelector('#abas-cenas [data-cena=fachada-frontal]')", 10), "a aba sai")
    ok([c["id"] for c in servidor()] == ["quadra", "planta"], "e a cena sai do servidor")

    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
